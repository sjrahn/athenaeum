"""NoOpTranscriber — the default. Raises `TranscriptionUnavailable`.

The video drafter (P5) catches the exception and emits a spec-shaped
`transcription-unavailable` issue rather than crashing. Lets a corpus operate
fully without configuring a transcription backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import TranscriptionResult, TranscriptionUnavailable


class NoOpTranscriber:
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        raise TranscriptionUnavailable(
            "no transcription adapter configured — set [corpus.transcription] "
            "adapter = 'http-whisper' with base_url in corpus.toml, or export "
            "CORPUS_TRANSCRIBE=http-whisper WHISPER_BASE_URL=… ."
        )

    def render_payload(self, payload: dict[str, Any]) -> str:
        # Never invoked in practice — NoOp.transcribe raised before any payload
        # was produced. Defensive: same exception message.
        raise TranscriptionUnavailable(
            "no transcription adapter configured to render this payload."
        )
