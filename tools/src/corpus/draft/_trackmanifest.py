"""Media-container track-manifest attestation (deterministic, no LLM; spec §12.20 items 1-2).

Shared core for `draft/video.py` and `draft/audio.py`: attest one manifest embed per
elementary stream of an ISOBMFF media container (mp4/m4a/mov) via `corpus.streams` — the
phase-1 pinned identity-extraction module (see there for the per-codec framing this module
hashes). This module owns none of that extraction logic; it only turns
`streams.probe_streams` + `mux.mux_stream` into the drafter's `embeds`/`issues`
result-shape (spec §4.3.1.4, §8.1) — one embed per extractable stream, one info-severity
issue per stream this increment's pinned extraction can't produce (declared honestly, per
§12.20 item 2: a stream whose codec the mux refuses is still a track fact).

Non-ISOBMFF containers (webm/mkv) and non-container audio (mp3/wav) are not media containers
this module can probe — `streams.probe_streams` raises `ValueError` for both (no `moov` box /
an EBML header), caught here and treated as "no track manifest this run" (parse-tolerant per
house doctrine; the container's existing artifact facts / body are untouched either way — this
is purely additive attestation, §12.20 item 2's "upgrades an existing video record
additively").
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import blake3

from corpus import mux, records, streams, touches

log = logging.getLogger(__name__)

_DETECTOR = touches.script_identifier("draft.track-manifest")

# The single-track container's conventional filename suffix (3.12) — set on each embed's
# `fields.filename` so `corpus promote`'s streamed-head MIME sniff (`_sniff_and_hash`) has a
# real extension to resolve against. It follows the track KIND, not the codec, because since
# 3.12 that is what the member's bytes are: a video-only mp4 or an audio-only m4a.
#
# Before 3.12 this keyed on codec and named elementary suffixes (`h264`/`h265`/`adts`/`opus`),
# because no reliable magic bytes exist for a bare Annex-B or opus-framed stream. That problem
# dissolves here — an ISOBMFF member sniffs cleanly on its `ftyp` brand — so the extension is
# now a convenience for humans rather than the disambiguator identity leaned on.
_EXTENSION_BY_KIND = {
    "video": "mp4",
    "audio": "m4a",
    "subtitle": "mp4",
}

_CHUNK = 1 << 20


def attest_track_manifest(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Probe `path` for elementary streams; return `(embeds, issues)` (spec §12.20 item 2).

    One embed per stream `corpus.mux` can produce, addressed `stream_id=<n>`,
    `transport:` the blake3 of the pinned extraction — computed by streaming the extraction
    exactly once, chunk by chunk, so a large track is never materialized in memory. A stream
    the extraction refuses — an unsupported codec (`StreamInfo.media_type is None`), or a
    structurally-refused track (e.g. a multi-entry `stsd`, `NotImplementedError` at extraction
    time) — is skipped as an embed and recorded as an `info`-severity `partial-content` issue
    instead: still a declared track fact (kind + codec, read from the container's own sample
    description), just not one this increment can pin a transport hash for.

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
        ext = _EXTENSION_BY_KIND.get(track.kind)
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
    """Mux the track once — blake3 transport digest + byte length — without materializing it
    whole. The digest is over the 3.12 pinned form (a single-track container of the source's
    own family, `corpus.mux`), which is what the roster row's `transport:` names."""
    b3 = blake3.blake3()
    length = 0
    for chunk in mux.mux_stream(path, stream_id):
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
        "resolution": "open",
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
    structural-->` per chapter, addressed `time=<HH:MM:SS>`, `level: 1`, `mark:` the
    chapter's own title. This is the **sidecar path** (§12.20 item 2(b)) — the mp4 chapter
    atom (`chpl`/`chap`-track) path is a named gap this increment does not implement; see the
    module notes in `draft/video.py`.

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
