"""Record connection graph — the data behind the record workbench's *graph* mode.

A record's connections are: its **origins** and **embeds** (always resolved), the corpus
records it **shares a classification** with (resolved; computed by the API from its
in-memory index), and the **outbound links** found in its normalized body. An outbound link
is *captured* when its URL already maps to a corpus record (a cross-reference) and
*uncaptured* otherwise — the uncaptured ones are what the submit phase will later ingest.

Pure: stdlib + the `corpus` library (no API, no HTTP). The API layer (`corpus.api.index`)
adds the classification-shared records and serializes the node shape.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from corpus import records, segments
from corpus import urls as urls_mod

# A liberal http(s) URL match; trailing punctuation (sentence/markdown delimiters) is
# stripped afterwards so `(https://x.org).` and `[…](https://x.org)` yield a clean URL.
_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]}]+", re.I)
_TRAILING = ".,;:!?)]}>\"'`*"


def iter_content_urls(post: Any) -> list[str]:
    """Every distinct http(s) URL appearing in the record's segment bodies, in order."""
    seen: dict[str, None] = {}
    for block in segments.iter_blocks(post.content or ""):
        segs = block.segments if isinstance(block, segments.Section) else [block]
        for seg in segs:
            for raw in _URL_RE.findall(seg.body or ""):
                url = raw.rstrip(_TRAILING)
                if url and url not in seen:
                    seen[url] = None
    return list(seen)


def build_links(
    corpus_root: Path, post: Any, *, uri_index: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Resolve the record's outbound body URLs against the corpus URI index.

    Returns one entry per link: ``{"url", "host", "recId"}`` where ``recId`` is the id of
    the corpus record that URL maps to (a *captured* cross-reference) or ``None`` (an
    *uncaptured* link the submit phase can ingest). The record's own origin / self-references
    are dropped — they show as origin nodes, not outbound links.
    """
    rid = str(post.metadata.get("id") or "")
    own = {_safe_key(corpus_root, u, uri_index) for u in records.iter_origin_uris(post)}
    out: list[dict[str, Any]] = []
    for url in iter_content_urls(post):
        if _safe_key(corpus_root, url, uri_index) in own:
            continue  # the record citing its own origin URL — not an outbound edge
        rec = _safe_find(corpus_root, url, uri_index)
        if rec and rec == rid:
            continue  # self-reference
        out.append({"url": url, "host": urls_mod.host_of(url) or url, "recId": rec})
    return out


def _safe_find(corpus_root: Path, url: str, index: dict[str, str] | None) -> str | None:
    try:
        return records.find_by_uri(url, corpus_root=corpus_root, index=index)
    except Exception:  # tolerant: a malformed URL never breaks the graph
        return None


def _safe_key(corpus_root: Path, url: str, index: dict[str, str] | None) -> str:
    """The identity key for `url` (best-effort), used to suppress own-origin links even
    when they aren't in the index. Falls back to the raw URL on any failure."""
    from corpus.capture import recipes as _recipes

    try:
        return _recipes.identity_key_for_url(corpus_root, url)
    except Exception:
        return url
