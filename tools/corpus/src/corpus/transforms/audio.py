"""Audio transformations: transcribe.

`transcribe` hands the audio file to the configured `TranscriptionAdapter` (pulled
from the render context, where the resolver placed it) and returns the rendered
transcript text in the canonical `[Speaker N] (HH:MM:SS)` format the video drafter
parses. The adapter is pluggable (NoOp default, HTTPWhisper opt-in) — see
`corpus.transcription`.

The transform also stashes the adapter's raw payload in `ctx["transcription_payload"]`
so a future resolver enhancement can persist it next to the rendered cache file (the
adapter's `render_payload` re-renders a cached payload without re-hitting the backend).
"""

from __future__ import annotations

import logging
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
    log.info("transcribe: %s", audio_path)
    result = transcriber.transcribe(audio_path)  # may raise TranscriptionUnavailable
    if result.payload is not None:
        ctx["transcription_payload"] = result.payload
    return result.text
