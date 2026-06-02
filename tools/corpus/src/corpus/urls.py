"""URL canonicalization for corpus dedup.

The corpus uses exact-string match for origin URI comparison, so the crawler and
ingestor must canonicalize URLs before checking. The transformations here are
deliberately conservative — only those whose semantic equivalence is universal
across HTTP servers. Path-case and trailing slashes on non-bare paths are *not*
normalized because some servers distinguish them.
"""

from __future__ import annotations

from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urlsplit,
    urlunsplit,
)

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
