"""Follow HTTP redirects to resolve a short link to its final URL — WITHOUT downloading
the artifact.

`urls.normalize` / `urls.identity_key` canonicalize a URL *string* but never touch the
network, so an opaque short link (`https://vt.tiktok.com/XXXX/`) is a different identity key
from the canonical `https://www.tiktok.com/@user/video/<id>` it 301s to. The byte-level
re-encounter on ingest eventually catches the duplicate, but only *after* the (expensive,
esp. video) download. This module closes that gap: it resolves a URL's final location by
following redirects with a HEAD (falling back to a body-less GET) so the capture short-circuit
and the read-only `corpus check` command can match a fresh short link to an already-captured
canonical *before* fetching.

Generic, not host-specific: it follows whatever `Location` headers the server returns, capped
at `MAX_HOPS`. `is_probably_short_link` is a cheap, conservative heuristic that gates the
network round-trip on the capture hot path — a normal canonical URL (a path that already looks
like content) is never probed; only opaque short forms (a bare host, a single short opaque path
segment, or a known link-shortener host) are. The probe is best-effort: any network/parse
failure returns the input unchanged (parse-tolerantly — log and skip), so resolution never
*breaks* capture, it only *improves* dedup when it succeeds.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger("corpus.redirects")

# Cap on chained redirects we follow before giving up. A legitimate short link
# resolves in 1-3 hops; anything longer is a redirect loop or tracking gauntlet.
MAX_HOPS = 8

# Per-hop network timeout (seconds). A HEAD/GET to resolve a Location header is fast;
# keep this tight so a hung host never stalls the capture hot path for long.
DEFAULT_TIMEOUT_S = 10.0

# Browser-ish UA — some shorteners (TikTok's `vt.`/`vm.` hosts among them) serve a
# different / no redirect to an obvious bot. Mirrors capture's DEFAULT_USER_AGENT.
_RESOLVE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Hosts (and any subdomain of them) that are URL shorteners / link-wrappers — always
# worth a redirect probe even when the path doesn't look opaque. Not exhaustive and not
# load-bearing: the path-shape heuristic below catches most short links generically; this
# list just removes false negatives for the common wrappers. TikTok's `vt.`/`vm.` share
# the apex `tiktok.com`, so they're matched by the `vt.`/`vm.` subdomain check, not here.
_SHORTENER_HOSTS = frozenset(
    {
        "t.co",
        "bit.ly",
        "tinyurl.com",
        "goo.gl",
        "ow.ly",
        "buff.ly",
        "youtu.be",
        "redd.it",
        "fb.me",
        "t.me",
        "lnkd.in",
        "dlvr.it",
        "trib.al",
        "rb.gy",
        "is.gd",
        "cutt.ly",
        "shorturl.at",
    }
)

# Subdomain labels that signal a host's short-link surface (e.g. `vt.tiktok.com`,
# `vm.tiktok.com`, `g.co`-style). Matched as the leading label of the host.
_SHORTENER_SUBDOMAINS = frozenset({"vt", "vm"})


def is_probably_short_link(url: str) -> bool:
    """Cheap, conservative guess at whether `url` is an opaque short link worth a redirect
    probe. Used to gate the network round-trip on the capture hot path so a normal canonical
    URL is never probed.

    True when ANY of:
      - the host (or its apex) is a known link-shortener (`_SHORTENER_HOSTS`),
      - the leading host label is a short-link subdomain (`vt.`/`vm.` — TikTok et al.),
      - the path is a single short, opaque segment (no further `/`, no `.`, <= 16 chars,
        e.g. `/ZSQdnsm4M`) — the classic shortener shape.

    False for a bare host with no path, or a path that already looks like real content
    (multiple segments, a recognizable slug, a file extension). Errs toward False: a false
    negative just misses the pre-download dedup (the byte re-encounter still catches it),
    while a false positive only costs one wasted HEAD.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False

    if host in _SHORTENER_HOSTS or _apex(host) in _SHORTENER_HOSTS:
        return True
    label = host.split(".", 1)[0]
    if label in _SHORTENER_SUBDOMAINS:
        return True

    # Path-shape: a single short opaque segment with no dot is the canonical shortener form.
    path = parts.path.strip("/")
    if not path:
        return False
    if "/" in path:
        return False  # multiple segments → already looks like a content path
    return "." not in path and 0 < len(path) <= 16


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop urllib from auto-following redirects so we can walk the chain ourselves and
    cap the hop count (urllib's default follows silently, with its own limit and no way to
    inspect intermediate hops or to avoid downloading the final body)."""

    def redirect_request(self, *_args, **_kwargs):  # type: ignore[override]
        return None


def resolve_final_url(
    url: str, *, timeout_s: float = DEFAULT_TIMEOUT_S, max_hops: int = MAX_HOPS
) -> str:
    """Follow HTTP redirects from `url` and return the final URL, WITHOUT downloading the
    artifact body.

    Issues a HEAD per hop (falling back to a body-less GET when a host rejects HEAD with
    405/501) and follows `Location` headers up to `max_hops`. Returns the resolved final URL,
    or `url` unchanged on any failure (no network, non-redirect status, redirect loop, hop
    cap, malformed Location) — parse-tolerantly, so a probe never breaks the caller.

    Never reads a response body: a 2xx terminal response ends the walk on its status line +
    headers alone, so even when the final URL serves a multi-megabyte video the probe stays
    cheap. The opener is built with redirect auto-following disabled (`_NoRedirect`) so we
    control the chain and the body is never fetched.
    """
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    seen: set[str] = set()
    for _ in range(max_hops):
        if current in seen:  # redirect loop
            log.debug("redirect loop at %s — stopping", current)
            return url
        seen.add(current)
        location = _one_hop(opener, current, timeout_s=timeout_s)
        if location is None:
            return current  # terminal (2xx/4xx) or unresolvable — current is final
        nxt = _join_location(current, location)
        if not nxt or nxt == current:
            return current
        log.debug("redirect: %s -> %s", current, nxt)
        current = nxt
    log.debug("redirect: hop cap (%d) reached from %s", max_hops, url)
    return current


def _one_hop(
    opener: urllib.request.OpenerDirector, url: str, *, timeout_s: float
) -> str | None:
    """Probe `url` with a HEAD (then a body-less GET fallback) and return its `Location`
    header when it's a redirect, else None (terminal response or failure). Never reads a
    body."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url,
                method=method,
                headers={"User-Agent": _RESOLVE_USER_AGENT, "Accept": "*/*"},
            )
            with opener.open(req, timeout=timeout_s) as resp:
                # A non-redirect (2xx/3xx-without-Location) terminates the walk; we never
                # read resp.read(), so the body — possibly a large video — is not fetched.
                return resp.headers.get("Location")
        except urllib.error.HTTPError as e:
            # `_NoRedirect` makes a 3xx raise HTTPError; its Location header is the next hop.
            if e.code in (301, 302, 303, 307, 308):
                return e.headers.get("Location")
            if method == "HEAD" and e.code in (405, 501):
                continue  # host refused HEAD — retry once as GET
            return None  # 4xx/5xx terminal — `url` is as far as we resolve
        except (urllib.error.URLError, ValueError, OSError) as e:
            log.debug("redirect probe %s %s failed: %s", method, url, e)
            return None
    return None


def _join_location(base: str, location: str) -> str:
    """Resolve a possibly-relative `Location` against `base`. Returns "" when the result
    isn't an absolute http(s) URL (a `Location` to a non-web scheme ends the walk)."""
    from urllib.parse import urljoin

    try:
        joined = urljoin(base, location.strip())
    except ValueError:
        return ""
    parts = urlsplit(joined)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return joined


def _apex(host: str) -> str:
    """Best-effort registrable apex (last two labels). A heuristic, not a public-suffix
    lookup — good enough to spot `bit.ly` behind a `www.bit.ly`."""
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host
