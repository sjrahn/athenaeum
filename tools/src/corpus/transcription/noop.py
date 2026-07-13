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
    #: Engine id for §6.4 version-labeling of the `transcribe` op's cache. Carries an
    #: `@<version>` component so an upgrade of the (no-op) contract is a distinct cache key.
    engine = "noop@1"

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


class DisabledTranscriber:
    """The transcriber for a host that declares `transcription.enabled: false` (§7.2). The
    `transcribe` op **skips** — raising a clear disabled signal rather than falling through to
    the global backend. Distinct engine id so a disabled result never shares a cache entry with
    a real transcription."""

    engine = "disabled@1"

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        raise TranscriptionUnavailable(
            "transcription disabled for this origin (transcription.enabled: false, §7.2)."
        )

    def render_payload(self, payload: dict[str, Any]) -> str:
        raise TranscriptionUnavailable("transcription disabled for this origin.")
