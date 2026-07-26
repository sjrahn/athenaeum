"""Per-record token counts — a derived view (spec §9; never persisted).

Three cumulative tiers, sized for "how much context window does this record cost":

    body   — the content-zone text only (text-atom segment bodies).
    blocks — the whole record markdown: frontmatter + metadata/annotation blocks + body
             (i.e. `records.dumps(post)`). Always >= body.
    full   — blocks + an estimate for imagery (embedded images + an image artifact).

Text is counted with a local Claude-proxy tokenizer (`tiktoken` `o200k_base`). There is no
official *local* Claude tokenizer for Python; tiktoken's modern BPE is a close, fully-offline,
deterministic stand-in. Image tokens use Anthropic's documented estimate (~ w*h / 750, with the
~1.15 MP resize cap). Everything degrades gracefully:

  * tiktoken is **lazy-imported** inside `_encode_len` — importing this module (and `corpus.draft`)
    never pulls it in, so the base-install import guard (gotcha #24) stays green. Install it via the
    `tokens` extra to get real counts; without it we fall back to a chars/4 heuristic.
  * parse-tolerant: a malformed record yields a best-effort count, never an exception.

Note: `o200k_base` fetches its BPE vocab from the web on first use, then caches under
`TIKTOKEN_CACHE_DIR`. Warm the cache once (or vendor the vocab) for offline runs.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from corpus import records, segments

log = logging.getLogger(__name__)

# ~1.15 MP: Anthropic downsizes larger images before counting, so tokens saturate there.
_IMG_PIXEL_CAP = 1_150_000
_IMG_PIXELS_PER_TOKEN = 750

# Cached encoder: a tiktoken Encoding, or the string "heuristic" when tiktoken is unavailable.
_ENCODER: Any = None


def _encoder() -> Any:
    """Lazily resolve the tokenizer. Returns a tiktoken Encoding or the sentinel "heuristic"."""
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER
    try:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("o200k_base")
    except Exception as exc:  # ImportError, or vocab fetch failure offline
        log.warning("tiktoken unavailable (%s); using chars/4 heuristic for token counts", exc)
        _ENCODER = "heuristic"
    return _ENCODER


def tokenizer_name() -> str:
    """Which counting path is live — "o200k_base" or "heuristic". For diagnostics/tests."""
    enc = _encoder()
    return "heuristic" if enc == "heuristic" else "o200k_base"


def _encode_len(text: str) -> int:
    if not text:
        return 0
    enc = _encoder()
    if enc == "heuristic":
        return math.ceil(len(text) / 4)
    try:
        return len(enc.encode(text))
    except Exception:
        return math.ceil(len(text) / 4)


def image_tokens(width: Any, height: Any) -> int:
    """Anthropic's image-token estimate from pixel dimensions; 0 when unknown."""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return 0
    if w <= 0 or h <= 0:
        return 0
    return math.ceil(min(w * h, _IMG_PIXEL_CAP) / _IMG_PIXELS_PER_TOKEN)


def _body_text(post: Any) -> str:
    """Concatenate the content-zone text-atom segment bodies, in reading order."""
    parts: list[str] = []
    try:
        for block in segments.iter_blocks(post.content or ""):
            children = block.segments if isinstance(block, segments.Section) else [block]
            for seg in children:
                if seg.atom == "text" and seg.body:
                    parts.append(seg.body)
    except Exception:  # parse-tolerant: a bad content zone shouldn't sink the count
        return ""
    return "\n".join(parts)


def _image_token_total(post: Any) -> int:
    """Image-token estimate for an image ARTIFACT (spec §9.6's `full` tier).

    *(3.4)* Image **members** no longer contribute. Their pixel dimensions are not stored — the
    members roster is closed to `address`/`media_type`/`transport`/`bytes` (spec §4.3.1.4) — so
    the only honest sources are the `members` derivation (§6.2) or decoding the bytes, and
    neither is a thing this pure `post`-only function may reach. `full` is declared an estimate
    precisely so it may degrade here rather than lie or fail; the alternative considered and
    rejected was scoring members from `bytes`, which for a compressed image says nothing about
    pixel count and would read as authoritative while being arbitrary.

    When this needs to be exact, take it from the `members` derivation behind the resolver
    cache — `token_counts` already accepts a `corpus_root` for exactly that kind of widening.
    """
    total = 0
    try:
        artifact = records.artifact_block(post)
        if artifact and str(artifact.get("mime") or "").startswith("image/"):
            fields = artifact.get("fields") or {}
            total += image_tokens(fields.get("width"), fields.get("height"))
    except Exception:
        pass
    return total


def token_counts(post: Any, *, corpus_root: Any = None) -> dict[str, int]:
    """The three cumulative tiers for a loaded record `post`. `corpus_root` is unused today
    (kept for signature parity with the other derived views, which resolve assets)."""
    body = _encode_len(_body_text(post))
    try:
        blocks = _encode_len(records.dumps(post))
    except Exception:
        blocks = body  # canonical re-serialization failed; floor at the body count
    blocks = max(blocks, body)
    full = blocks + _image_token_total(post)
    return {"body": body, "blocks": blocks, "full": full}
