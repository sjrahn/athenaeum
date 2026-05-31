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
    - Fragment dropped.
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
    return urlunsplit((scheme, netloc, path, query, ""))


def host_of(url: str) -> str:
    """Return the lowercased host of `url`, or empty string if absent."""
    return (urlsplit(url).hostname or "").lower()


def same_domain(url: str, seed_host: str, *, include_subdomains: bool = False) -> bool:
    """Decide whether `url` shares the seed host.

    Default is host-exact. With `include_subdomains`, the registered root is derived
    by stripping a leading `www.` from the seed host (a heuristic that covers the
    common case without pulling in a public-suffix library), then any host equal to
    or under that root matches. So `www.example.com` with subdomains accepts
    `example.com`, `www.example.com`, and any `*.example.com` — but not
    `evilexample.com`.
    """
    host = host_of(url)
    if not host:
        return False
    if host == seed_host:
        return True
    if not include_subdomains:
        return False
    root = seed_host[4:] if seed_host.startswith("www.") else seed_host
    return host == root or host.endswith("." + root)


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


def _normalize_query(query: str) -> str:
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    pairs.sort()
    return urlencode(pairs, doseq=True)
