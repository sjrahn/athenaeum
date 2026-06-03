"""yt-dlp `.info.json` → origin-block enrichment fields (deterministic).

A yt-dlp capture writes a companion `.info.json` (title, caption/description, uploader,
view/like/comment/repost counts, track, and — when `getcomments` is on — the top
comments). Ingest stages it at `capture/<hash>.info.json`; the audio/video drafters read
it here so the rich post metadata enters the record instead of being orphaned on disk.

**The principle (sjrahn):** the *primary artifact* is the downloaded media. Its intrinsic
facts (codec / dimensions / streams from ffprobe) belong to the artifact block, and its
only body content is the transcript (from the media's own audio). Everything the info.json
adds comes from a *non-primary source* (the source page), so it goes to a **metadata
block** — never the body, the artifact block, or the frontmatter `description`.
Mechanically: the info.json keys are lifted into the **origin block** (the "where it came
from" block) as flat `ytdlp_<key>` fields, and `comments[]` becomes a `ytdlp_comments`
list there. `webpage_url`/`original_url` fold into the origin `uri:` alias list.

Mechanical and host-agnostic: any yt-dlp capture has this sidecar. The lifted key set is
schema-driven (the mime schema's `sidecar.ytdlp_keys`); `_YTDLP_KEYS` is the fallback.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TypedDict

log = logging.getLogger(__name__)

# Fallback info.json keys lifted into the origin block as `ytdlp_<key>` fields
# (present-only), used when the mime schema declares no `sidecar.ytdlp_keys`. The schema
# is the source of truth (see `_ytdlp_keys_for`); this keeps the drafter working for a
# corpus whose schema predates the declaration.
_YTDLP_KEYS = (
    "title",
    "description",
    "uploader",
    "uploader_id",
    "uploader_url",
    "channel",
    "channel_id",
    "channel_url",
    "upload_date",
    "view_count",
    "like_count",
    "comment_count",
    "repost_count",
    "track",
    "artists",
)


class SidecarResult(TypedDict):
    # Flat `ytdlp_<key>` fields (+ `ytdlp_comments`) merged into the origin block.
    origin_fields: dict[str, Any]
    # webpage_url / original_url, folded into the origin block's uri: alias list.
    origin_aliases: list[str]


def _empty() -> SidecarResult:
    return {"origin_fields": {}, "origin_aliases": []}


def info_json_path(corpus_root: Path, record_id: str) -> Path:
    """The yt-dlp `.info.json` enrichment sidecar: staged in `capture/<hash>.info.json`,
    read at draft, then deleted (`_cli/draft._cleanup_enrichment`). The artifact is the
    only `<hash>`-named file under `artifacts/`."""
    return corpus_root / "capture" / f"{record_id}.info.json"


def parse_info_json_for_record(
    corpus_root: Path, record_id: str, record_metadata: dict[str, Any] | None = None
) -> SidecarResult:
    """Read `capture/<id>.info.json` (if present) → `ytdlp_*` origin fields + aliases.

    The lifted key set is schema-driven: declared on the record's mime schema
    (`sidecar.ytdlp_keys`), resolved from `record_metadata`. Tolerant: a missing /
    unparseable sidecar returns the empty result (no crash) — most captures
    (HTML/image/pdf) have no sidecar at all."""
    path = info_json_path(corpus_root, record_id)
    if not path.is_file():
        return _empty()
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("unreadable info.json sidecar %s: %s", path, exc)
        return _empty()
    if not isinstance(info, dict):
        return _empty()
    return _map_info(info, _ytdlp_keys_for(corpus_root, record_metadata))


def _ytdlp_keys_for(
    corpus_root: Path, record_metadata: dict[str, Any] | None
) -> tuple[str, ...]:
    """The info.json keys lifted into `ytdlp_*` origin fields, declared on the record's
    mime schema (`sidecar.ytdlp_keys`); falls back to `_YTDLP_KEYS`."""
    from corpus import schemas

    media_type = ((record_metadata or {}).get("_artifact") or {}).get("mime")
    if media_type:
        schema = schemas.load_mime_schema(corpus_root, str(media_type)) or {}
        keys = (schema.get("sidecar") or {}).get("ytdlp_keys")
        if keys:
            return tuple(str(k) for k in keys)
    return _YTDLP_KEYS


def _map_info(info: dict[str, Any], keys: tuple[str, ...]) -> SidecarResult:
    out = _empty()

    fields: dict[str, Any] = {
        f"ytdlp_{k}": info[k] for k in keys if info.get(k) not in (None, "", [])
    }
    comments = _comments(info.get("comments"))
    if comments:
        fields["ytdlp_comments"] = comments
    out["origin_fields"] = fields

    aliases = [
        str(info[k])
        for k in ("webpage_url", "original_url")
        if info.get(k) and str(info[k]).strip()
    ]
    out["origin_aliases"] = list(dict.fromkeys(aliases))  # de-dupe, keep order
    return out


def _comments(comments: Any) -> list[dict[str, Any]]:
    """yt-dlp `comments[]` → a present-only list of `{text, author?, like_count?,
    timestamp?}` for the `ytdlp_comments` origin field. Non-primary content kept as
    metadata, never body (yt-dlp returns no list for TikTok — mainly YouTube etc.)."""
    if not isinstance(comments, list) or not comments:
        return []
    out: list[dict[str, Any]] = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        text = c.get("text")
        if not text or not str(text).strip():
            continue
        entry: dict[str, Any] = {"text": str(text).strip()}
        for key in ("author", "like_count", "timestamp"):
            if c.get(key) not in (None, ""):
                entry[key] = c[key]
        out.append(entry)
    if out:
        log.info("info.json: %d comment(s) → ytdlp_comments", len(out))
    return out
