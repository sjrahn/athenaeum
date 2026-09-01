"""Audio draft extraction (deterministic, no LLM).

Produces a `draft`-status body from an audio artifact:

1. Probe the file via `ffprobe` for duration / codec / sampling rate / channels
   (tolerant — a missing or failing ffprobe yields no metadata, not a crash).

2. Resolve `corpus://<id>?transcribe` through the functional-URI resolver. That runs
   the configured `TranscriptionAdapter` (NoOp default, HTTPWhisper opt-in), cached by
   urihash. When no adapter is available — or the backend fails — the resolver raises
   `TranscriptionUnavailable`; the drafter still produces a record, just with no segments
   and a spec-shaped `transcription-unavailable` issue.

3. Parse the `[Speaker N] (HH:MM:SS)` transcript into a flat list of `text/transcript`
   segments, one per speaker run, via the shared `_transcript` splitter
   (video_stream_id=None → transcript-only, no frame markers). No `Section` is asserted
   (§7.8, §4.3.2.1) — a speaker run carries no source-stated label.

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

import frontmatter

from corpus import recordbuild, resolver, touches
from corpus.draft import DrafterResult, register
from corpus.draft._hostcfg import resolve_transcription
from corpus.draft._sidecar import parse_info_json_for_record
from corpus.draft._trackmanifest import attest_track_manifest
from corpus.draft._transcript import parse_transcript_sections
from corpus.segments import Segment
from corpus.transcription import TranscriptionUnavailable

log = logging.getLogger(__name__)

_AUDIO_SCHEMA_IDS = (
    "audio/audio_mpeg",
    "audio/audio_x-wav",
    "audio/audio_mp4",
    # *(3.11, #131)* The promoted-track leaf types. This is where a media container's transcript
    # now comes from: the audio-track record owns it (§1.2), not the container that carries the
    # track. Before this, `draft/video.py` resolved `?extract_audio&transcribe` against the
    # CONTAINER and wrote `text/transcript` into the container's own body — a parent rendering a
    # member's bytes, which §4.3.2.2 has forbidden since 3.8 and which survived only because no
    # video schema declared `disposition: manifest` (§65's gap, closed in 3.11).
    #
    # Transcribing the leaf is also better input, not merely better placement: the leaf's own
    # id names its payload-identity bytes (§2, v32), and `?transcribe` on it isolates the SAME
    # bytes losslessly (route unification, §6.2), where `extract_audio` on the container
    # re-encodes to 64 kbps mono mp3. The old path transcribed a lossy derivative of the member.
    "audio/audio_aac",
    "audio/audio_opus",
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
        "size_bytes": audio_path.stat().st_size,
        "format": _format_for_extension(audio_path.suffix),
    }
    probe = _probe_audio(audio_path)
    if not probe["root"].get("duration"):
        # *(v32, §2)* A promoted media-stream leaf's own bytes are the raw payload —
        # deliberately not playable, so ffprobe reads nothing from them directly (`probe`
        # above degrades to empty, tolerantly). `duration` is a REQUIRED field
        # (audio.yaml), and the container's is the honest answer: it's the same
        # measurement the transcript itself will be read against (route unification,
        # §6.2 — `?transcribe` on this leaf runs against the same container).
        fallback_duration = _duration_via_container_lineage(corpus_root, record_metadata)
        if fallback_duration is not None:
            probe["root"]["duration"] = fallback_duration
    fields.update(probe["root"])
    if probe["audio_count"] > 1 and probe["streams"]:
        fields["streams"] = probe["streams"]

    issues: list[dict[str, Any]] = []
    segs: list[Segment] = []
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
            # Tolerated like every other branch here (the record still drafts, with an
            # issue recording it): a v32 media-stream leaf routing `?transcribe` through
            # its container is a known route limitation (§6.2), not an operator-actionable
            # failure, so this stays below the default WARNING floor (Python's logging
            # "handler of last resort" prints WARNING+ straight to stderr when the CLI
            # hasn't configured a handler — `corpus reattest` doesn't) rather than reading
            # as a crash on an otherwise-clean pass.
            log.debug("transcript resolution failed: %s", exc)
            issues.append(_unavailable_issue("warning", f"transcript resolution failed: {exc}"))
        else:
            if transcript.strip():
                segs = parse_transcript_sections(
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
            for seg in segs
            if seg.overlay == "text/transcript" and seg.extra.get("speaker") is not None
        }
    )
    if distinct_speakers:
        fields["speakers"] = [{"id": idx, "name": None} for idx in distinct_speakers]
        fields["is_diarized"] = True

    # yt-dlp .info.json is non-primary-source enrichment → it goes to the origin block as
    # `ytdlp_*` fields, never the body/artifact/frontmatter. The body stays transcript-only.
    sidecar = parse_info_json_for_record(corpus_root, record_id, record_metadata)

    # Track-manifest attestation (spec §12.20 items 1-2): one embed per elementary stream, for
    # an ISOBMFF container (audio/mp4, i.e. .m4a/.m4b) — additive, a no-op for mp3/wav (no
    # `moov` box to probe). No chapter-mark wiring here: unlike the video capturer, the audio
    # path has no established chapters-bearing sidecar consumer in this increment.
    track_embeds, track_issues = attest_track_manifest(audio_path)
    issues.extend(track_issues)

    recordbuild.add_blocks(build, segs)
    return {
        "fields": fields,
        "embeds": track_embeds,
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
        "detector": touches.script_identifier("draft.audio"),
        "fields": {"reason": reason},
    }


# ---------- container-lineage fallback (v32, §2) ---------- #


def _duration_via_container_lineage(
    corpus_root: Path, record_metadata: dict[str, Any] | None
) -> float | None:
    """The leaf's containing timeline's duration, via containment lineage — the fallback for
    a v32 payload leaf whose own bytes ffprobe cannot read at all. None when the record
    carries no lineage, or the container can't be read either (never fatal — the same
    tolerant contract `_probe_audio` has)."""
    from corpus import containment, paths, records
    from corpus import cut as cut_mod
    from corpus import mime as mime_mod
    from corpus.store import ArtifactMissing

    post = frontmatter.Post("", **dict(record_metadata or {}))
    lineage = cut_mod.stream_lineage(post)
    if lineage is None:
        return None
    container_id, _stream_address = lineage
    try:
        container_post = records.load(paths.record_path(corpus_root, container_id))
        container_ext = mime_mod.extension_for(records.media_type_for(container_post))
        container_path = containment.ensure_local_bytes(corpus_root, container_id, container_ext)
    except (FileNotFoundError, ArtifactMissing, OSError):
        return None
    try:
        return cut_mod.container_duration(container_post, container_path)
    except cut_mod.Unresolved:
        return None


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
        # Tolerated (module docstring: "missing or failing ffprobe yields no metadata, not
        # a crash") — expected for a v32 leaf's raw payload bytes (no container to probe).
        # DEBUG, not WARNING: the latter hits Python's stderr "handler of last resort"
        # whenever the CLI hasn't configured logging (`corpus reattest` doesn't), dumping
        # ffprobe's raw stderr (e.g. "moov atom not found") onto an otherwise-clean pass.
        log.debug("ffprobe failed (%s) — skipping audio metadata", proc.stderr.strip())
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
                ("codec", "codec"),
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
