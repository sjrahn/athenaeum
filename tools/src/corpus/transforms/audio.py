"""Audio transformations: transcribe.

`transcribe` hands the audio file to the configured `TranscriptionAdapter` (pulled
from the render context, where the resolver placed it) and returns the rendered
transcript text in the canonical `[Speaker N] (HH:MM:SS)` format the video drafter
parses. The adapter is pluggable (NoOp default, HTTPWhisper opt-in) — see
`corpus.transcription`.

The transform also stashes the adapter's raw payload in `ctx["transcription_payload"]`
so a future resolver enhancement can persist it next to the rendered cache file (the
adapter's `render_payload` re-renders a cached payload without re-hitting the backend).

**Stream isolation (§6.2, v32).** When the resolver has redirected a promoted media-stream
leaf's `?transcribe` through its container (`corpus://<container>?stream_id=<n>&transcribe`,
route unification), `ctx["stream_ids"]` names exactly the one audio track this call is
about. Transcribing the raw multi-track container file directly would feed the transcriber
whatever track ffmpeg happens to default to — wrong when the container carries more than
one audio track, and imprecise even when it doesn't. So this module isolates that track
FIRST, via `corpus.mux` (a lossless `-c copy` remux, never `extract_audio`'s re-encode) —
the transcriber then runs on the same payload bytes the leaf's own id names, not a lossy
derivative of them.
"""

from __future__ import annotations

import contextlib
import logging
import tempfile
from pathlib import Path

from ..transcription import TranscriptionUnavailable
from . import RenderContext, register

log = logging.getLogger(__name__)


@register("audio", "transcribe", "text")
def transcribe(audio_path: Path, value: str | None, ctx: RenderContext) -> str:
    """Transcribe `audio_path` via the context's adapter; return canonical text.

    Flag-style (no value). Raises `TranscriptionUnavailable` when no adapter is
    available or the backend fails — the video drafter catches it and emits a
    spec-shaped `transcription-unavailable` issue.
    """
    if value is not None:
        raise ValueError(f"transcribe is flag-style and takes no value, got {value!r}")
    transcriber = ctx.get("transcriber")
    if transcriber is None:
        raise TranscriptionUnavailable(
            "no transcription adapter in the render context (resolver wiring error)"
        )
    with _isolated_stream(audio_path, ctx) as isolated:
        log.info("transcribe: %s", isolated)
        result = transcriber.transcribe(isolated)  # may raise TranscriptionUnavailable
    if result.payload is not None:
        ctx["transcription_payload"] = result.payload
    return result.text


@contextlib.contextmanager
def _isolated_stream(audio_path: Path, ctx: RenderContext):
    """Yield `audio_path` unchanged, unless the render context names exactly one
    `stream_ids` entry AND `audio_path` IS the multi-track artifact those ids select from
    (`ctx["artifact_path"]`, the same gate `transforms.video._stream_map_args` uses) — in
    which case yield a temp single-track remux of just that stream (module docstring)."""
    artifact_path = ctx.get("artifact_path")
    stream_ids = ctx.get("stream_ids")
    if not stream_ids or artifact_path is None or Path(audio_path) != Path(artifact_path):
        yield audio_path
        return
    if len(stream_ids) != 1:
        raise ValueError("transcribe operates on a single audio stream — pass one stream_id=")
    from .. import mux

    with tempfile.TemporaryDirectory(prefix="corpus-transcribe-") as tmpdir:
        dest = Path(tmpdir) / f"stream.{mux.extension_for_kind('audio')}"
        mux.mux_stream_to(Path(audio_path), int(stream_ids[0]), dest)
        yield dest
