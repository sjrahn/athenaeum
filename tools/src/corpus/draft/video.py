"""Video draft extraction (deterministic, no LLM).

Produces a `draft`-status body from a video CONTAINER artifact. *(3.11, #131)* The
container itself never transcribes — that moved to the audio stream leaf's own drafter
(`draft/audio.py`, §1.2), since a container rendering a member's bytes has been a
violation since 3.8 (§4.3.2.2, `disposition: manifest`, §65). What this drafter still
owns:

1. Probe the file via `ffprobe` for duration / dimensions / codecs / per-stream
   metadata (tolerant — a missing or failing ffprobe yields no metadata, not a
   crash; per-stream data lifts to a `streams:` map keyed `v0`/`a0`/…).

2. Track-manifest attestation (spec §12.20 items 1-2, `draft/_trackmanifest.py`): one embed
   per elementary stream for an ISOBMFF container (mp4/quicktime), additive to the facts
   above — a no-op for webm/mkv (Matroska/EBML support is a deferred item).

3. Chapter marks: yt-dlp `.info.json`'s `chapters[]` (the **sidecar path only** —
   `_sidecar.py`) land as structural byte-marks (§4.3.2.3), each carrying the chapter's own
   title verbatim — a boundary the source declares about the whole container, and the one
   content-zone inhabitant a `disposition: manifest` record is allowed (§65). The mp4
   chapter-atom path (`chpl` box / `chap`-track) is a **named gap**: not implemented this
   increment, so a chaptered mp4 with no yt-dlp sidecar (e.g. a plain capture, not a yt-dlp
   download) attests no structural marks even though the container bytes may carry them.

Registered for every bundled `video/*` mime-schema id; a corpus with a custom video
mime schema registers its own drafter for that id.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from corpus import recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.draft._sidecar import parse_info_json_for_record
from corpus.draft._trackmanifest import attest_track_manifest, chapter_structural_segments
from corpus.segments import Section

log = logging.getLogger(__name__)

_VIDEO_SCHEMA_IDS = (
    "video/video_mp4",
    "video/video_webm",
    "video/video_quicktime",
    "video/video_x-matroska",
)


def draft(
    video_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path,
    record_id: str,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,  # transcript is text; frames body-empty
) -> DrafterResult:
    # *(3.12)* A promoted track leaf now carries the SAME mime as the container it came out
    # of (`video/mp4`), because its bytes are a single-track container of that family. Mime
    # no longer separates the two, so this drafter dispatches on the fact that does: a leaf
    # carries a `cutting:` stamp, resolved once at promotion (§7.2.1), and a container never
    # does. Before 3.12 the leaf's elementary mime routed it to its own registered drafter.
    if _is_promoted_stream_leaf(record_metadata):
        from corpus.draft import video_stream

        return video_stream.draft(
            video_path,
            build=build,
            corpus_root=corpus_root,
            record_id=record_id,
            record_metadata=record_metadata,
            canonical_algo=canonical_algo,
            fingerprint=fingerprint,
        )
    fields: dict[str, Any] = {
        "size_bytes": video_path.stat().st_size,
        "format": _format_for_extension(video_path.suffix),
    }
    probe = _probe_video(video_path)
    fields.update(probe["root"])
    if probe["streams"]:
        fields["streams"] = probe["streams"]

    issues: list[dict[str, Any]] = []
    # A container's content zone holds chapter marks and nothing else (§65, §4.3.2.3). `sections`
    # stays because the shape is a list of blocks either way; it is simply always empty now.
    sections: list[Section] = []

    # yt-dlp .info.json is non-primary-source enrichment → it goes to the origin block as
    # `ytdlp_*` fields, never the body/artifact/frontmatter. Its `chapters[]` are the one
    # structural exception: they section the body (a section's `entry` TOC label + address
    # are metadata structure, not body content), so a chaptered video is sectioned by its
    # chapters in preference to the speaker-run heuristic.
    sidecar = parse_info_json_for_record(corpus_root, record_id, record_metadata)
    chapters = sidecar.get("chapters")

    # *(3.11, #131)* The container does NOT transcribe. It used to resolve
    # `?extract_audio&transcribe` against ITSELF and write `text/transcript` sections into its
    # own content zone — the parent authoring a rendering of a member's bytes, which §4.3.2.2
    # has called a violation rather than a style since 3.8. It survived here only because no
    # video schema ever declared `disposition: manifest` (§65's conformance gap, closed in
    # 3.11), so nothing recognized the container as a container.
    #
    # The transcript is the AUDIO STREAM LEAF's own content, produced by the audio drafter over
    # the leaf's pinned ADTS/Opus bytes — not over an mp3 `extract_audio` re-encoded from the
    # container. Diarization (`speakers:`, `is_diarized`) goes with it: those are facts about an
    # audio stream, not about the container that carries it.
    #
    # What stays here is what is genuinely the container's: the per-stream probe facts, the
    # track manifest, and the chapter marks — chapters are byte-marks OF the container
    # (§4.3.2.3, §12.20 item 2b), a boundary the source declares about the whole, which is why
    # they remain a legal content-zone inhabitant of a `manifest` record while a rendering is
    # not. A leaf reaches them through lineage at read time (§1.2), never by copy.

    # Track-manifest attestation (spec §12.20 items 1-2): one embed per elementary stream, on
    # top of the existing container facts above (additive — "corpus reattest upgrades an
    # existing video record additively", §12.20 item 2). ISOBMFF only; a no-op (empty result)
    # for webm/mkv until Matroska/EBML support lands (§12.20's deferred item).
    track_embeds, track_issues = attest_track_manifest(video_path)
    issues.extend(track_issues)

    # Chapter marks → structural byte-marks (§4.3.2.3, §12.20 item 2(b) — the sidecar path;
    # the mp4 chapter-atom path is a named gap, see the module docstring). Reuses the same
    # `chapters` the section-by-chapters heuristic above already lifted from the yt-dlp
    # sidecar — no second sidecar read.
    structural_segments = chapter_structural_segments(chapters)

    recordbuild.add_blocks(build, sections)
    return {
        "fields": fields,
        "embeds": track_embeds,
        "issues": issues,
        "origin_fields": sidecar["origin_fields"],
        "origin_uri_aliases": sidecar["origin_aliases"],
        "structural_segments": structural_segments,
    }


for _sid in _VIDEO_SCHEMA_IDS:
    register(_sid)(draft)


# ---------- issue helper ---------- #


def _unavailable_issue(severity: str, reason: str) -> dict[str, Any]:
    """Spec §4.3.3.1-shaped `transcription-unavailable` issue."""
    return {
        "id": "transcription-unavailable",
        "severity": severity,
        "resolution": "open",
        "detector": touches.script_identifier("draft.video"),
        "fields": {"reason": reason},
    }


# ---------- ffprobe (tolerant) ---------- #


def _probe_video(video_path: Path) -> dict[str, Any]:
    """Run ffprobe; return root-level + per-stream metadata. Tolerant: ffprobe
    missing or failing returns the empty structure (no metadata, no crash)."""
    empty: dict[str, Any] = {
        "root": {},
        "streams": {},
        "audio_stream_id": None,
        "video_stream_id": None,
        "audio_count": 0,
        "video_count": 0,
    }
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        log.info("ffprobe not on PATH — skipping video metadata")
        return empty
    if proc.returncode != 0:
        # Tolerated (module docstring: "missing or failing ffprobe yields no metadata, not
        # a crash"). DEBUG, not WARNING: the latter hits Python's stderr "handler of last
        # resort" whenever the CLI hasn't configured logging (`corpus reattest` doesn't),
        # dumping ffprobe's raw stderr onto an otherwise-clean pass.
        log.debug("ffprobe failed (%s) — skipping video metadata", proc.stderr.strip())
        return empty
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return empty

    root: dict[str, Any] = {}
    if (duration := data.get("format", {}).get("duration")) is not None:
        with contextlib.suppress(TypeError, ValueError):
            root["duration"] = round(float(duration), 2)

    streams_map: dict[str, dict[str, Any]] = {}
    video_count = audio_count = 0
    audio_stream_id: str | None = None
    video_stream_id: str | None = None
    primary_video_seen = False

    for s in data.get("streams") or []:
        codec_type = s.get("codec_type")
        if codec_type == "video":
            sid = f"v{video_count}"
            video_count += 1
            meta: dict[str, Any] = {"kind": "video"}
            if codec := s.get("codec_name"):
                meta["codec"] = codec
            if "width" in s:
                meta["width"] = int(s["width"])
            if "height" in s:
                meta["height"] = int(s["height"])
            if (fr := s.get("avg_frame_rate")) and (rate := _frame_rate(fr)) is not None:
                meta["frame_rate"] = rate
            streams_map[sid] = meta
            if not primary_video_seen:
                for k_src, k_dst in (
                    ("width", "width"),
                    ("height", "height"),
                    ("codec", "codec"),
                    ("frame_rate", "frame_rate"),
                ):
                    if k_src in meta:
                        root[k_dst] = meta[k_src]
                primary_video_seen = True
            if video_stream_id is None:
                video_stream_id = sid
        elif codec_type == "audio":
            sid = f"a{audio_count}"
            audio_count += 1
            meta = {"kind": "audio"}
            if codec := s.get("codec_name"):
                meta["codec"] = codec
            if (sr := _as_int(s.get("sample_rate"))) is not None:
                meta["sampling_rate"] = sr
            if (ch := _as_int(s.get("channels"))) is not None:
                meta["channels"] = ch
            if lang := (s.get("tags") or {}).get("language"):
                meta["language"] = str(lang)
            streams_map[sid] = meta
            if audio_stream_id is None:
                audio_stream_id = sid

    return {
        "root": root,
        "streams": streams_map,
        "audio_stream_id": audio_stream_id,
        "video_stream_id": video_stream_id,
        "audio_count": audio_count,
        "video_count": video_count,
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame_rate(spec: str) -> float | None:
    if "/" in spec:
        num, _, den = spec.partition("/")
        try:
            n, d = float(num), float(den)
            return round(n / d, 3) if d else None
        except ValueError:
            return None
    try:
        return float(spec)
    except ValueError:
        return None


def _format_for_extension(suffix: str) -> str:
    return suffix.lower().lstrip(".") or "mp4"


def _is_promoted_stream_leaf(record_metadata: dict[str, Any] | None) -> bool:
    """Whether this record is a promoted single-track leaf rather than a container.

    Keyed on the `cutting:` stamp because that is what promotion writes and attestation
    never does — a positive fact about how the record came to exist, rather than an absence
    (no roster) that an un-attested container would also satisfy.

    Reads it through `records.cutting` rather than reaching into the metadata dict directly:
    the stamp's location is that module's business, and a second hand-rolled path here would
    be one more thing to keep in step with it.
    """
    if not record_metadata:
        return False
    import frontmatter

    return records.cutting(frontmatter.Post("", **dict(record_metadata))) is not None
