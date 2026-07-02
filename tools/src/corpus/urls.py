"""URL canonicalization for corpus dedup.

The corpus compares origin URIs by a canonical key, so the crawler and ingestor must
canonicalize URLs before checking. `normalize` does the conservative, universally-safe
transformations — only those whose semantic equivalence holds across HTTP servers.
Path-case and trailing slashes on non-bare paths are *not* normalized because some
servers distinguish them.

`identity_key` layers an **opt-in, per-host** equivalence step on top of `normalize`
(overlay-declared `url_equivalent` rules — spec §7.2): two URLs denote the same resource
iff their identity keys are equal. Absent any host rules it is exactly `normalize`, so the
layer is inert by default. Identity is computed for comparison only — it never changes which
bytes are fetched (that is `url_rewrite` / `interactions`).
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urlsplit,
    urlunsplit,
)

log = logging.getLogger("corpus.urls")

_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def normalize(url: str) -> str:
    """Canonicalize `url` for content-addressed corpus dedup.

    Transformations:
    - Scheme and host lowercased.
    - Default port (80 for http, 443 for https) stripped.
    - Plain anchor fragments dropped; client-side routing fragments preserved (see
      `_normalize_fragment`).
    - Query parameters parsed and re-emitted in sorted (key, value) order; preserves
      repeated keys, preserves empty values.
    - Bare-host paths (`""` or `"/"`) collapsed to `""`; other paths left as-is.
    - Percent-encoding normalized to uppercase hex via decode-then-encode round-trip.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = _normalize_netloc(parts.hostname, parts.port, parts.username, parts.password, scheme)
    path = _normalize_path(parts.path)
    query = _normalize_query(parts.query)
    fragment = _normalize_fragment(parts.fragment)
    return urlunsplit((scheme, netloc, path, query, fragment))


def apply_rewrite_rules(url: str, rules: Any) -> str:
    """Apply ordered ``{pattern, replacement}`` regex rules to `url` via ``re.sub``.

    Returns `url` unchanged when no rule matches. A rule with no `pattern` is skipped; a bad
    pattern is logged and skipped (best-effort, never raises). Shared by capture's
    ``url_rewrite`` (rewrites the *fetched* URL) and ``url_equivalent`` (rewrites the
    *identity key*) — one rule shape, two uses. `rules` is the raw overlay value; a non-list
    is treated as no rules.
    """
    out = url
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict) or not (pattern := rule.get("pattern")):
            continue
        try:
            out = re.sub(str(pattern), str(rule.get("replacement") or ""), out)
        except re.error as exc:
            log.warning("rewrite rule: bad pattern %r: %s", pattern, exc)
    return out


def normalize_equivalence(raw: Any) -> dict[str, Any] | None:
    """Coerce an overlay ``url_equivalent`` value to a canonical config, or None when absent.

    Two declared forms (spec §7.2):
    - a **list** of ``{pattern, replacement}`` rules → ``{query: keep, rules, on_rewritten: False}``
    - a **map** ``{query: keep|drop, rules: [...], on_rewritten: bool}`` → the same shape.

    Anything falsy or of the wrong type → None (no equivalence; identity stays `normalize`).
    """
    if isinstance(raw, list):
        return {"query": "keep", "rules": raw, "on_rewritten": False}
    if isinstance(raw, dict):
        query = str(raw.get("query") or "keep").lower()
        if query not in ("keep", "drop"):
            log.warning("url_equivalent: unknown query=%r (using 'keep')", raw.get("query"))
            query = "keep"
        rules = raw.get("rules")
        return {
            "query": query,
            "rules": rules if isinstance(rules, list) else [],
            "on_rewritten": bool(raw.get("on_rewritten")),
        }
    return None


def identity_key(url: str, equivalent: Any = None, *, url_rewrite: Any = None) -> str:
    """Compute `url`'s identity key for resource-equality comparison (spec §7.2).

    Two URLs denote the same resource iff their identity keys are equal. The key is the
    conservative `normalize`, optionally folded over the host's declared ``url_equivalent``
    rules. With no `equivalent` config this is exactly ``normalize(url)`` — today's string
    identity — so the layer is strictly **opt-in** per host.

    Algorithm: resolve the config (absent → ``normalize(url)``); if ``on_rewritten``, apply
    the host's ``url_rewrite`` rules first so identity is computed from the fetched form;
    `normalize`; if ``query: drop`` strip the whole query; apply the ``url_equivalent`` rules
    in order; tidy a dangling ``?``/``&`` a rule may have left; finally fold a **sub-path
    trailing slash** (``…/a/b/`` ≡ ``…/a/b``). The trailing-slash fold lives here, NOT in
    `normalize`, on purpose: `normalize`'s output is the URL a crawl re-fetches, and stripping
    a slash there could change what is fetched — but an identity *comparison* key may fold it.
    A practical consequence: a naive first-page rule (``…/page-1 → \\1``) folds to the same key
    as the recorded slashed origin (``…/slug.id/``), so rules need not chase the slash.

    **Identity-only**: this never influences which bytes are fetched (that is ``url_rewrite``
    / ``interactions``) — only what counts as the same resource.
    """
    cfg = normalize_equivalence(equivalent)
    if cfg is None:
        return normalize(url)
    src = apply_rewrite_rules(url, url_rewrite) if cfg["on_rewritten"] else url
    base = normalize(src)
    if cfg["query"] == "drop":
        base = _strip_query(base)
    base = apply_rewrite_rules(base, cfg["rules"])
    return _fold_trailing_slash(_tidy(base))


def _strip_query(url: str) -> str:
    """Drop the entire query component (robust reparse, not a regex)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))


def _fold_trailing_slash(url: str) -> str:
    """Fold a sub-path trailing slash for IDENTITY only (``…/a/b/`` ≡ ``…/a/b``).

    Applied in the identity-key path, never in `normalize` — `normalize` feeds the crawl's
    fetch target, and a server may distinguish ``/a/b`` from ``/a/b/``, so the fetched form
    must keep its slash; a comparison key may fold it. Leaves the fragment (an SPA route)
    untouched, and never strips the bare-host root (`normalize` already empties ``/``)."""
    parts = urlsplit(url)
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        stripped = path.rstrip("/") or "/"
        return urlunsplit((parts.scheme, parts.netloc, stripped, parts.query, parts.fragment))
    return url


def _tidy(url: str) -> str:
    """Collapse a dangling query delimiter a `url_equivalent` rule may have left behind."""
    url = re.sub(r"\?&+", "?", url)  # "?&" -> "?"
    url = re.sub(r"&&+", "&", url)  # "&&" -> "&"
    return re.sub(r"[?&]+$", "", url)  # trailing "?" / "&"


def host_of(url: str) -> str:
    """Return the lowercased host of `url`, or empty string if absent."""
    return (urlsplit(url).hostname or "").lower()


def same_domain(url: str, seed_host: str, *, include_subdomains: bool = False) -> bool:
    """Decide whether `url` shares the seed host.

    Apex and `www` are treated as the same site by default — a leading `www.` is stripped
    from BOTH the candidate host and the seed before comparing, so a crawl seeded at
    `example.com` follows `www.example.com` links and vice-versa (the most common same-site
    variation, and consistent with capture's redirect-drift www-normalization). With
    `include_subdomains`, any deeper subdomain under that root also matches
    (`x.example.com`) — but never a different registrable name (`evilexample.com`).

    The `www.`-strip is a heuristic that covers the common case without pulling in a
    public-suffix library.
    """
    host = host_of(url)
    if not host:
        return False
    h = host[4:] if host.startswith("www.") else host
    root = seed_host[4:] if seed_host.startswith("www.") else seed_host
    if h == root:
        return True
    if not include_subdomains:
        return False
    return h.endswith("." + root)


def is_crawlable_href(href: str) -> bool:
    """Decide whether an `<a href>` is a navigable link worth resolving + normalizing.

    Rejects empty/whitespace hrefs, the non-navigational schemes (`javascript:`,
    `mailto:`, `tel:`), and bare in-page anchor fragments (`#`, `#section`, `#top`).
    KEEPS hash-routed SPA routes (`#/vehicle/46076`, hashbang `#!/path`): on a
    client-side-routed site the fragment IS the route to a *distinct* resource, so it
    must survive to be `urljoin`-resolved and normalized — mirrors the `/`-or-`!`
    discriminator in `_normalize_fragment`. Everything else (relative paths, absolute
    http(s) URLs, including absolute URLs that carry a `#/route`) is crawlable.

    The shared filter behind `corpus links` / `corpus crawl` link extraction — keeping
    it in one place is what stops the two extractors from re-drifting (they previously
    each dropped every `#`-prefixed href, discarding SPA routes before normalize ran).
    """
    href = href.strip()
    if not href:
        return False
    if href.startswith(("javascript:", "mailto:", "tel:")):
        return False
    if href.startswith("#"):
        return href[1:2] in ("/", "!")
    return True


def _normalize_netloc(
    host: str | None,
    port: int | None,
    user: str | None,
    password: str | None,
    scheme: str,
) -> str:
    if not host:
        return ""
    netloc = host.lower()
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{netloc}:{port}"
    if user is not None:
        creds = user
        if password is not None:
            creds = f"{creds}:{password}"
        netloc = f"{creds}@{netloc}"
    return netloc


def _normalize_path(path: str) -> str:
    if path in ("", "/"):
        return ""
    return quote(unquote(path), safe="/-._~!$&'()*+,;=:@%")


def _normalize_fragment(fragment: str) -> str:
    """Drop plain anchor fragments; preserve client-side routing fragments.

    A fragment like `#section` / `#top` is an in-page element id — it addresses the
    same resource, so it's dropped for dedup. But a hash-routed SPA encodes the actual
    route in the fragment (`#/vehicle/46076`, hashbang `#!/path`), so the fragment
    identifies a *distinct* resource and MUST survive canonicalization — both so the
    captured page navigates to the right route and so two routes don't dedup to one
    record. The discriminator: a routing fragment begins with `/` or `!` (no HTML
    element id does), an anchor fragment does not.
    """
    return fragment if fragment[:1] in ("/", "!") else ""


def _normalize_query(query: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    pairs.sort()
    return urlencode(pairs, doseq=True)
