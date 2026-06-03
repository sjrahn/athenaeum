"""Video draft extraction (deterministic, no LLM).

Produces a `draft`-status body from a video artifact:

1. Probe the file via `ffprobe` for duration / dimensions / codecs / per-stream
   metadata (tolerant — a missing or failing ffprobe yields no metadata, not a
   crash; per-stream data lifts to a `streams:` map keyed `v0`/`a0`/…).

2. Resolve `corpus://<id>?extract_audio&transcribe` through the functional-URI
   resolver. That runs ffmpeg → the configured `TranscriptionAdapter` (NoOp default,
   HTTPWhisper opt-in), cached by urihash. When no adapter is available — or the
   backend fails — the resolver raises `TranscriptionUnavailable`; the drafter still
   produces a record, just with no sections and a spec-shaped
   `transcription-unavailable` issue (reconciliation #2 vs the reference's
   CarbonAi `format_loss` shape).

3. Parse the `[Speaker N] (HH:MM:SS)` transcript into Sections. Default: one Section
   per speaker run. When the capture's `.info.json` ships chapter markers, section by
   the chapters instead (the uploader's outline beats the speaker-run heuristic) — the
   chapter title becomes the section `entry` TOC label (§4.3.2.2; metadata structure,
   not body content). Each section holds one `text/transcript` Segment per checkpoint
   (verbatim utterance as body, speaker carried on `extra`), led by a body-empty `image`
   keyframe marker at the section's start frame — the final section also closes with
   one at the video's last frame (when the source has a video stream). Interior
   boundary frames are shared between adjacent sections, so each is emitted once
   (§4.3.2.2). `text/transcript` is the lossless atomic overlay (spec §7.3) — the
   body losslessly transcribes the addressed time-range; the adapter's output is
   approximate and the normalizer corrects it.

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

from corpus import resolver, touches
from corpus.draft import DrafterResult, register
from corpus.draft._hostcfg import resolve_transcription
from corpus.draft._sidecar import parse_info_json_for_record
from corpus.draft._transcript import parse_chaptered_sections, parse_transcript_sections
from corpus.segments import Section
from corpus.transcription import TranscriptionUnavailable

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
    corpus_root: Path,
    record_id: str,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
) -> DrafterResult:
    fields: dict[str, Any] = {
        "video_size_bytes": video_path.stat().st_size,
        "video_format": _format_for_extension(video_path.suffix),
    }
    probe = _probe_video(video_path)
    fields.update(probe["root"])
    if probe["streams"]:
        fields["streams"] = probe["streams"]

    issues: list[dict[str, Any]] = []
    sections: list[Section] = []
    transcript = ""

    # yt-dlp .info.json is non-primary-source enrichment → it goes to the origin block as
    # `ytdlp_*` fields, never the body/artifact/frontmatter. Its `chapters[]` are the one
    # structural exception: they section the body (a section's `entry` TOC label + address
    # are metadata structure, not body content), so a chaptered video is sectioned by its
    # chapters in preference to the speaker-run heuristic.
    sidecar = parse_info_json_for_record(corpus_root, record_id, record_metadata)
    chapters = sidecar.get("chapters")

    mode, per_host_transcriber = resolve_transcription(corpus_root, record_metadata)
    if mode == "disabled":
        log.info("transcription disabled for this origin host")
        issues.append(_unavailable_issue("info", "transcription disabled for this origin host"))
    else:
        try:
            transcript_path = resolver.resolve(
                f"corpus://{record_id}?extract_audio&transcribe",
                corpus_root,
                transcriber=per_host_transcriber,
            )
            transcript = transcript_path.read_text(encoding="utf-8")
        except TranscriptionUnavailable as exc:
            log.info("transcription unavailable: %s", exc)
            issues.append(_unavailable_issue("warning", str(exc)))
        except Exception as exc:  # ffmpeg/probe/resolve failure — still produce a record
            log.warning("transcript resolution failed: %s", exc)
            issues.append(_unavailable_issue("warning", f"transcript resolution failed: {exc}"))
        else:
            if transcript.strip():
                common = {
                    "audio_stream_id": probe["audio_stream_id"] or "a0",
                    "video_stream_id": probe["video_stream_id"],
                    "multi_audio": probe["audio_count"] > 1,
                    "multi_video": probe["video_count"] > 1,
                    "media_duration": probe["root"].get("duration"),
                }
                if chapters:
                    sections = parse_chaptered_sections(transcript, chapters, **common)
                    log.info("sectioned by %d chapter marker(s)", len(chapters))
                else:
                    sections = parse_transcript_sections(transcript, **common)
            else:
                issues.append(
                    _unavailable_issue("info", "empty transcript (no detectable speech)")
                )

    distinct_speakers = sorted(
        {
            seg.extra.get("speaker")
            for sec in sections
            for seg in sec.segments
            if seg.overlay == "text/transcript" and seg.extra.get("speaker") is not None
        }
    )
    if distinct_speakers:
        fields["speakers"] = [{"id": idx, "name": None} for idx in distinct_speakers]
        fields["is_diarized"] = True

    return {
        "fields": fields,
        "segments": sections,
        "embeds": [],
        "issues": issues,
        "origin_fields": sidecar["origin_fields"],
        "origin_uri_aliases": sidecar["origin_aliases"],
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
        log.warning("ffprobe failed (%s) — skipping video metadata", proc.stderr.strip())
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
                    ("codec", "video_codec"),
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
