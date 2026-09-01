"""Media-container track-manifest attestation (deterministic, no LLM; spec §2, §4.3.1.4).

Shared core for `draft/video.py` and `draft/audio.py`: attest one manifest embed per
elementary stream of an ISOBMFF media container (mp4/m4a/mov) via `corpus.streams` — the
payload-identity module (v32, §2): the embed's `transport:` is the blake3 of the RAW
CODEC PAYLOAD (`streams.extract_stream`), the same bytes a promotion of that address
mints as a leaf id, so `corpus://<leaf> ≡ corpus://<container>?stream_id=<n>` holds from
the moment the container is drafted. This module owns none of the extraction logic; it
only turns `streams.probe_streams` + `streams.extract_stream` into the drafter's
`embeds`/`issues` result-shape (spec §4.3.1.4, §8.1) — one embed per extractable stream,
one info-severity issue per stream whose codec this module can't name a leaf mime for
(declared honestly: a stream whose codec extraction doesn't recognize is still a track
fact).

Non-ISOBMFF containers (webm/mkv) and non-container audio (mp3/wav) are not media containers
this module can probe — `streams.probe_streams` raises `ValueError` for both (no `moov` box /
an EBML header), caught here and treated as "no track manifest this run" (parse-tolerant per
house doctrine; the container's existing artifact facts / body are untouched either way — this
is purely additive attestation).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import blake3

from corpus import mime as mime_mod
from corpus import records, streams, touches

log = logging.getLogger(__name__)

_DETECTOR = touches.script_identifier("draft.track-manifest")

# The promoted leaf's conventional filename suffix — set on each embed's `fields.filename`.
# Since v32 the leaf's mime is codec-derived (`StreamInfo.media_type`), so the extension
# follows `mime.extension_for` on that mime rather than the track KIND: a payload has no
# reliable magic bytes of its own (§2 — that is what "not reframed" means), so
# `corpus promote`'s leaf mime comes from the roster row's `media_type` (this embed's), not
# from sniffing the streamed bytes — the filename hint is a human convenience only.
_CHUNK = 1 << 20


def attest_track_manifest(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Probe `path` for elementary streams; return `(embeds, issues)` (spec §4.3.1.4).

    One embed per stream this module can name a leaf mime for, addressed `stream_id=<n>`,
    `transport:` the blake3 of the PAYLOAD-IDENTITY extraction (`streams.extract_stream`,
    §2) — computed by streaming the extraction exactly once, chunk by chunk, so a large
    track is never materialized in memory. A stream extraction refuses — an unrecognized
    codec (`StreamInfo.media_type is None`), or a structurally-refused track (e.g. a
    multi-entry `stsd`, `NotImplementedError` at extraction time) — is skipped as an embed
    and recorded as an `info`-severity `partial-content` issue instead: still a declared
    track fact (kind + codec, read from the container's own sample description), just not
    one this module can pin a transport hash for.

    Returns `([], [])` for a non-ISOBMFF container or any file `streams.probe_streams` can't
    read (`ValueError`) — not every video/audio mime schema names a media container this
    module can probe (webm/mkv; bare mp3/wav)."""
    try:
        tracks = streams.probe_streams(path)
    except (ValueError, NotImplementedError) as exc:
        # ValueError: non-ISOBMFF container, or a malformed/incomplete track.
        # NotImplementedError: a structurally-refused track ANYWHERE in the container (e.g. a
        # multi-entry `stsd`, §12.20.1's "never guess") — `probe_streams` parses every track
        # eagerly, so one bad track blocks the whole container's manifest this run, a
        # limitation inherited from phase 1 (`corpus.streams`), not routed around here.
        log.debug("no track manifest for %s: %s", path, exc)
        return [], []

    embeds: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for track in tracks:
        if track.media_type is None:
            issues.append(
                _unsupported_track_issue(track, "codec not supported by the pinned extraction")
            )
            continue
        try:
            digest, length = _hash_extraction(path, track.index)
        except (NotImplementedError, ValueError) as exc:
            issues.append(_unsupported_track_issue(track, str(exc)))
            continue
        fields: dict[str, Any] = {"bytes": length}
        ext = mime_mod.extension_for(track.media_type, fallback="")
        if ext:
            fields["filename"] = f"stream_id={track.index}.{ext}"
        embeds.append(
            {
                "media_type": track.media_type,
                "address": f"stream_id={track.index}",
                "transport": records.format_hash("blake3", digest),
                "fields": fields,
            }
        )
    return embeds, issues


def _hash_extraction(path: Path, stream_id: int) -> tuple[str, int]:
    """Extract the track's payload once — blake3 transport digest + byte length — without
    materializing it whole. The digest is over the v32 payload-identity bytes
    (`streams.extract_stream`, §2), which is what the roster row's `transport:` names —
    and what a `promote` of this address later mints as the leaf's own id."""
    b3 = blake3.blake3()
    length = 0
    for chunk in streams.extract_stream(path, stream_id):
        b3.update(chunk)
        length += len(chunk)
    return b3.hexdigest(), length


def _unsupported_track_issue(track: streams.StreamInfo, reason: str) -> dict[str, Any]:
    """spec §4.3.3.2-shaped `partial-content` issue for a track fact ingest can declare (kind +
    codec, from the container's own sample description) but not embed — no transport hash
    without a pinned extraction (§12.20 item 2: "declare it honestly... skip the embed and
    log/emit a record-level note")."""
    return {
        "id": "partial-content",
        "subtype": "unsupported-track",
        "severity": "info",
        "detector": _DETECTOR,
        "fields": {
            "description": (
                f"stream_id={track.index} ({track.kind}, codec {track.codec!r}): {reason} — "
                f"declared as a track fact, not embedded."
            ),
            "stream_id": track.index,
            "kind": track.kind,
            "codec": track.codec,
        },
    }


# ---------- chapters → structural byte-marks (spec §4.3.2.3, §12.20 item 2) ---------- #


def chapter_structural_segments(
    chapters: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """`_sidecar.py`'s yt-dlp `chapters[]` (`[{start, end?, title}, …]`) → the media
    container's chapter byte-marks (§4.3.2.3's worked example): one `<!--segment
    structural-->` per chapter, addressed `time=<HH:MM:SS>`, `level: 1`, carrying the
    chapter's own title as its text. This is the **sidecar path** (§12.20 item 2(b)) — the
    mp4 chapter atom (`chpl`/`chap`-track) path is a named gap this increment does not
    implement; see the module notes in `draft/video.py`.

    None/empty input returns an empty list (no chapters declared, or the sidecar path found
    none)."""
    if not chapters:
        return []
    marks: list[dict[str, Any]] = []
    for c in chapters:
        start = c.get("start")
        title = c.get("title")
        if start is None or not title:
            continue
        marks.append(
            {
                "address": f"time={_format_timecode(float(start))}",
                "level": 1,
                # `"mark"` here is this INTERMEDIATE producer dict's key, not a stored
                # header field: `derive._apply_structural_segments` (derive.py ~178-183)
                # reads it straight into `Segment(body=...)` — the mark's text lives in the
                # segment BODY (spec §4.3.2.3, 3.8 §12.32), never a scalar header. Nothing
                # here writes `mark:` onto a record.
                "mark": str(title),
            }
        )
    return marks


def _format_timecode(seconds: float) -> str:
    """Seconds → `HH:MM:SS` (§4.3.2.3's worked example format: `time=00:12:31`)."""
    total = max(0, round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
