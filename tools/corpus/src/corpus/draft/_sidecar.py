"""yt-dlp `.info.json` → record fields + content segments (deterministic).

A yt-dlp capture writes a companion `.info.json` (title, caption/description, uploader,
view/like/comment/repost counts, track, and — when `getcomments` is on — the top
comments). `corpus.capture._move_video_sidecar` relocates it to
`artifacts/<shard>/<id>.info.json`. The audio/video drafters read it here so the rich
post metadata enters the record instead of being orphaned on disk.

Mechanical and host-agnostic: any yt-dlp capture has this sidecar. The mapping is:

- `title`          → the refined artifact title (replaces the sanitized-filename fallback).
- `description`    → the `description` field AND a caption `text` segment (so a no-audio
                     record still has body content — the caption *is* a post's text).
- social fields    → a `social:` field map (uploader/channel/dates/engagement/track).
- `comments[]`     → one `text` segment per comment (author/like_count/timestamp on `extra`).
- `webpage_url`    → origin-URI alias candidates (folded into the origin block on merge).

Caption and comments are each wrapped in their own `<!--section-->` so the content zone
stays homogeneous (all sections) when transcript sections are also present. Their
`address` is on a `sidecar=` axis — these are companion-metadata content, not byte-slices
of the media (spec §4.3.2 address axes).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TypedDict

from corpus.segments import Section, Segment

log = logging.getLogger(__name__)

# Fallback info.json keys lifted into the record's `social:` field map (present-only),
# used when the mime schema declares no `extended_fields.social.sidecar_keys`. The schema
# is the source of truth (see `_social_keys_for`); this keeps the drafter working for a
# corpus whose schema predates the declaration.
_SOCIAL_KEYS = (
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
    title: str | None
    description: str | None
    fields: dict[str, Any]
    caption_sections: list[Section]
    comment_sections: list[Section]
    origin_aliases: list[str]


def _empty() -> SidecarResult:
    return {
        "title": None,
        "description": None,
        "fields": {},
        "caption_sections": [],
        "comment_sections": [],
        "origin_aliases": [],
    }


def info_json_path(corpus_root: Path, record_id: str) -> Path:
    """The yt-dlp `.info.json` enrichment sidecar: staged in `capture/<hash>.info.json`,
    read at draft, then deleted (`_cli/draft._cleanup_enrichment`). The artifact is the
    only `<hash>`-named file under `artifacts/`."""
    return corpus_root / "capture" / f"{record_id}.info.json"


def parse_info_json_for_record(
    corpus_root: Path, record_id: str, record_metadata: dict[str, Any] | None = None
) -> SidecarResult:
    """Read `capture/<id>.info.json` (if present) → fields + caption/comment sections.

    The `social:` field set is schema-driven: the keys copied from the info.json are
    declared on the record's mime schema (`extended_fields.social.sidecar_keys`), resolved
    from `record_metadata`. Tolerant: a missing/unparseable sidecar returns the empty
    result (no crash) — most captures (HTML/image/pdf) have no sidecar at all."""
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
    return _map_info(info, _social_keys_for(corpus_root, record_metadata))


def _social_keys_for(
    corpus_root: Path, record_metadata: dict[str, Any] | None
) -> tuple[str, ...]:
    """The info.json keys mapped into `social:`, declared on the record's mime schema
    (`extended_fields.social.sidecar_keys`); falls back to `_SOCIAL_KEYS`."""
    from corpus import schemas

    media_type = ((record_metadata or {}).get("_artifact") or {}).get("mime")
    if media_type:
        schema = schemas.load_mime_schema(corpus_root, str(media_type)) or {}
        keys = ((schema.get("extended_fields") or {}).get("social") or {}).get("sidecar_keys")
        if keys:
            return tuple(str(k) for k in keys)
    return _SOCIAL_KEYS


def _map_info(info: dict[str, Any], social_keys: tuple[str, ...]) -> SidecarResult:
    out = _empty()

    title = info.get("title")
    out["title"] = str(title) if title else None

    description = info.get("description")
    out["description"] = str(description) if description else None

    social = {k: info[k] for k in social_keys if info.get(k) not in (None, "", [])}
    if social:
        out["fields"] = {"social": social}

    if description:
        out["caption_sections"] = [
            Section(
                address="sidecar=info.json",
                entry="Caption",
                segments=[
                    Segment(atom="text", address="sidecar=description", body=str(description))
                ],
            )
        ]

    out["comment_sections"] = _comment_sections(info.get("comments"))

    aliases = [
        str(info[k])
        for k in ("webpage_url", "original_url")
        if info.get(k) and str(info[k]).strip()
    ]
    out["origin_aliases"] = list(dict.fromkeys(aliases))  # de-dupe, keep order
    return out


def _comment_sections(comments: Any) -> list[Section]:
    if not isinstance(comments, list) or not comments:
        return []
    segs: list[Segment] = []
    for i, c in enumerate(comments):
        if not isinstance(c, dict):
            continue
        text = c.get("text")
        if not text or not str(text).strip():
            continue
        extra: dict[str, Any] = {}
        for key in ("author", "like_count", "timestamp"):
            if c.get(key) not in (None, ""):
                extra[key] = c[key]
        segs.append(
            Segment(
                atom="text",
                address=f"sidecar=comment/{i}",  # index keeps the address unique
                body=str(text).strip(),
                extra=extra,
            )
        )
    if not segs:
        return []
    log.info("info.json: %d comment segment(s)", len(segs))
    return [Section(address="sidecar=comments", entry="Comments", segments=segs)]
