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

3. Parse the `[Speaker N] (HH:MM:SS)` transcript into one Section per speaker run.
   Each section holds one `text/transcript` Segment per checkpoint (verbatim
   utterance as body, speaker carried on `extra`), bookended by body-empty
   `image` positioning markers at the run's start/end frames (when the source has a
   video stream). `text/transcript` is the lossless atomic overlay (spec §7.3) — the
   body losslessly transcribes the addressed time-range; the adapter's output is
   approximate and the normalizer corrects it.

Registered for every bundled `video/*` mime-schema id; a corpus with a custom video
mime schema registers its own drafter for that id.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from corpus import resolver, touches
from corpus.draft import DrafterResult, register
from corpus.segments import Section, Segment
from corpus.transcription import TranscriptionUnavailable

log = logging.getLogger(__name__)

_VIDEO_SCHEMA_IDS = (
    "video/video_mp4",
    "video/video_webm",
    "video/video_quicktime",
    "video/video_x-matroska",
)

# Transcript segment header: `[Speaker N] (HH:MM:SS)` (or bare `(HH:MM:SS)`).
_SEGMENT_HEADER_RE = re.compile(
    r"^\[(?P<speaker>[^\]]+)\]\s+\((?P<timestamp>\d+:\d{2}:\d{2})\)\s*$",
    flags=re.MULTILINE,
)
_SPEAKER_LABEL_RE = re.compile(r"Speaker\s+(\d+)", re.IGNORECASE)


def draft(
    video_path: Path,
    *,
    corpus_root: Path,
    record_id: str,
    record_metadata: dict[str, Any] | None = None,
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
    try:
        transcript_path = resolver.resolve(
            f"corpus://{record_id}?extract_audio&transcribe", corpus_root
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
            streams = probe["streams"]
            audio_count = sum(1 for s in streams.values() if s.get("kind") == "audio")
            video_count = sum(1 for s in streams.values() if s.get("kind") == "video")
            sections = _parse_transcript_sections(
                transcript,
                audio_stream_id=probe["audio_stream_id"] or "a0",
                video_stream_id=probe["video_stream_id"],
                multi_audio=audio_count > 1,
                multi_video=video_count > 1,
            )
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
        "title": None,
        "issues": issues,
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


# ---------- transcript parsing ---------- #


def _seconds_to_timecode(s: float) -> str:
    """Render seconds as `HH:MM:SS` (or `MM:SS` when hours are zero) — the form the
    transcript headers use, so segment addresses read consistently with the source."""
    total = int(s)
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"


def _speaker_label_to_index(label: str) -> int | None:
    """`Speaker 2` → 2; None for unlabeled segments."""
    if not label:
        return None
    m = _SPEAKER_LABEL_RE.search(label)
    return int(m.group(1)) if m else None


def _parse_transcript_sections(
    transcript: str,
    *,
    audio_stream_id: str,
    video_stream_id: str | None,
    multi_audio: bool,
    multi_video: bool,
) -> list[Section]:
    """One Section per speaker run. Each holds one `text/transcript` Segment per
    checkpoint (utterance body, speaker on `extra`), bookended by body-empty `image`
    framegrab markers (when the source has a video stream).

    A speaker change is a section boundary at draft time; the normalizer later merges
    across speaker boundaries into topic-grain sections.
    """
    headers: list[tuple[str, float, int]] = []
    for m in _SEGMENT_HEADER_RE.finditer(transcript):
        ts = m.group("timestamp")
        h, mm, s = (int(p) for p in ts.split(":"))
        headers.append((m.group("speaker"), float(h * 3600 + mm * 60 + s), m.end()))
    if not headers:
        return []

    # Per-header text body slice.
    texts: list[str] = []
    for idx, (_speaker, _start, body_start) in enumerate(headers):
        if idx + 1 < len(headers):
            next_pos = transcript.find(f"[{headers[idx + 1][0]}]", body_start)
            body_end = transcript.rfind("\n", body_start, next_pos)
            texts.append(transcript[body_start:body_end].strip())
        else:
            texts.append(transcript[body_start:].strip())

    # Group consecutive headers by speaker into runs.
    runs: list[tuple[str, float, float, list[tuple[float, str]]]] = []
    run_start = 0
    for i in range(1, len(headers) + 1):
        if i < len(headers) and headers[i][0] == headers[run_start][0]:
            continue
        speaker = headers[run_start][0]
        start = headers[run_start][1]
        end = headers[i][1] if i < len(headers) else headers[-1][1] + 0.001
        checkpoints = [(headers[j][1], texts[j]) for j in range(run_start, i) if texts[j]]
        runs.append((speaker, start, end, checkpoints))
        run_start = i

    sections: list[Section] = []
    for speaker, run_begin, run_end, checkpoints in runs:
        if not checkpoints:
            continue
        speaker_idx = _speaker_label_to_index(speaker)
        section_address = (
            f"time_range={_seconds_to_timecode(run_begin)}-{_seconds_to_timecode(run_end)}"
        )
        if multi_audio:
            section_address += f"&stream_id={audio_stream_id}"

        segs: list[Segment] = []
        if video_stream_id:
            segs.append(_frame_segment(run_begin, video_stream_id, multi_video))
        for i, (cp_start, cp_text) in enumerate(checkpoints):
            cp_end = checkpoints[i + 1][0] if i + 1 < len(checkpoints) else run_end
            addr = f"time_range={_seconds_to_timecode(cp_start)}-{_seconds_to_timecode(cp_end)}"
            if multi_audio:
                addr += f"&stream_id={audio_stream_id}"
            extra: dict[str, Any] = {}
            if speaker_idx is not None:
                extra["speaker"] = speaker_idx
            segs.append(
                Segment(
                    atom="text",
                    overlay="text/transcript",
                    address=addr,
                    body=cp_text,
                    extra=extra,
                )
            )
        if video_stream_id and run_end > run_begin:
            segs.append(_frame_segment(run_end, video_stream_id, multi_video))

        sections.append(Section(address=section_address, entry=None, segments=segs))
    return sections


def _frame_segment(t: float, video_stream_id: str, multi_video: bool) -> Segment:
    """Body-empty image positioning marker at `frame=<t>` (spec §4.3.2.2)."""
    addr = f"frame={_seconds_to_timecode(t)}"
    if multi_video:
        addr += f"&stream_id={video_stream_id}"
    return Segment(atom="image", address=addr, body="")
