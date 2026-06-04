"""Audio draft extraction (deterministic, no LLM).

Produces a `draft`-status body from an audio artifact:

1. Probe the file via `ffprobe` for duration / codec / sampling rate / channels
   (tolerant — a missing or failing ffprobe yields no metadata, not a crash).

2. Resolve `corpus://<id>?transcribe` through the functional-URI resolver. That runs
   the configured `TranscriptionAdapter` (NoOp default, HTTPWhisper opt-in), cached by
   urihash. When no adapter is available — or the backend fails — the resolver raises
   `TranscriptionUnavailable`; the drafter still produces a record, just with no sections
   and a spec-shaped `transcription-unavailable` issue.

3. Parse the `[Speaker N] (HH:MM:SS)` transcript into one Section per speaker run via the
   shared `_transcript` splitter (video_stream_id=None → transcript-only, no frame markers).

Registered for every bundled `audio/*` mime-schema id; a corpus with a custom audio mime
schema registers its own drafter for that id.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from corpus import recordbuild, resolver, touches
from corpus.draft import DrafterResult, register
from corpus.draft._hostcfg import resolve_transcription
from corpus.draft._sidecar import parse_info_json_for_record
from corpus.draft._transcript import parse_transcript_sections
from corpus.segments import Section
from corpus.transcription import TranscriptionUnavailable

log = logging.getLogger(__name__)

_AUDIO_SCHEMA_IDS = (
    "audio/audio_mpeg",
    "audio/audio_x-wav",
    "audio/audio_mp4",
)


def draft(
    audio_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path,
    record_id: str,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,  # transcript body is text; audio-atom fp not wired
) -> DrafterResult:
    fields: dict[str, Any] = {
        "audio_size_bytes": audio_path.stat().st_size,
        "audio_format": _format_for_extension(audio_path.suffix),
    }
    probe = _probe_audio(audio_path)
    fields.update(probe["root"])
    if probe["audio_count"] > 1 and probe["streams"]:
        fields["streams"] = probe["streams"]

    issues: list[dict[str, Any]] = []
    sections: list[Section] = []
    transcript = ""
    mode, per_host_transcriber = resolve_transcription(corpus_root, record_metadata)
    if mode == "disabled":
        log.info("transcription disabled for this origin host")
        issues.append(_unavailable_issue("info", "transcription disabled for this origin host"))
    else:
        try:
            transcript_path = resolver.resolve(
                f"corpus://{record_id}?transcribe",
                corpus_root,
                transcriber=per_host_transcriber,
            )
            transcript = transcript_path.read_text(encoding="utf-8")
        except TranscriptionUnavailable as exc:
            log.info("transcription unavailable: %s", exc)
            issues.append(_unavailable_issue("warning", str(exc)))
        except Exception as exc:  # ffmpeg/resolve failure — still produce a record
            log.warning("transcript resolution failed: %s", exc)
            issues.append(_unavailable_issue("warning", f"transcript resolution failed: {exc}"))
        else:
            if transcript.strip():
                sections = parse_transcript_sections(
                    transcript,
                    audio_stream_id=probe["audio_stream_id"] or "a0",
                    video_stream_id=None,
                    multi_audio=probe["audio_count"] > 1,
                    multi_video=False,
                    media_duration=probe["root"].get("duration"),
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

    # yt-dlp .info.json is non-primary-source enrichment → it goes to the origin block as
    # `ytdlp_*` fields, never the body/artifact/frontmatter. The body stays transcript-only.
    sidecar = parse_info_json_for_record(corpus_root, record_id, record_metadata)

    recordbuild.add_blocks(build, sections)
    return {
        "fields": fields,
        "embeds": [],
        "issues": issues,
        "origin_fields": sidecar["origin_fields"],
        "origin_uri_aliases": sidecar["origin_aliases"],
    }


for _sid in _AUDIO_SCHEMA_IDS:
    register(_sid)(draft)


# ---------- issue helper ---------- #


def _unavailable_issue(severity: str, reason: str) -> dict[str, Any]:
    """Spec §4.3.3.1-shaped `transcription-unavailable` issue."""
    return {
        "id": "transcription-unavailable",
        "severity": severity,
        "resolution": "open",
        "detector": touches.script_identifier("draft.audio"),
        "fields": {"reason": reason},
    }


# ---------- ffprobe (tolerant) ---------- #


def _probe_audio(audio_path: Path) -> dict[str, Any]:
    """Run ffprobe; return root-level + per-stream audio metadata. Tolerant: ffprobe
    missing or failing returns the empty structure (no metadata, no crash)."""
    empty: dict[str, Any] = {
        "root": {},
        "streams": {},
        "audio_stream_id": None,
        "audio_count": 0,
    }
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(audio_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        log.info("ffprobe not on PATH — skipping audio metadata")
        return empty
    if proc.returncode != 0:
        log.warning("ffprobe failed (%s) — skipping audio metadata", proc.stderr.strip())
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
    audio_count = 0
    audio_stream_id: str | None = None
    for s in data.get("streams") or []:
        if s.get("codec_type") != "audio":
            continue
        sid = f"a{audio_count}"
        audio_count += 1
        meta: dict[str, Any] = {"kind": "audio"}
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
            # Lift the primary audio stream's metadata to the root fields.
            stream_to_root = (
                ("codec", "audio_codec"),
                ("sampling_rate", "sampling_rate"),
                ("channels", "channels"),
            )
            for k_src, k_dst in stream_to_root:
                if k_src in meta:
                    root[k_dst] = meta[k_src]

    return {
        "root": root,
        "streams": streams_map,
        "audio_stream_id": audio_stream_id,
        "audio_count": audio_count,
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_for_extension(suffix: str) -> str:
    return suffix.lower().lstrip(".") or "mp3"
