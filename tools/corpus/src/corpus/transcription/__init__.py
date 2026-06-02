"""TranscriptionAdapter — pluggable audio transcription for the video drafter.

Audio→text is one of the few places the corpus pipeline reaches out to a backend
that isn't local-deterministic (the drafter would otherwise be a pure function of
the artifact's bytes). The Protocol lets a corpus plug in whichever transcription
service it has access to — or disable it entirely (NoOp default).

Surface:

- `transcribe(audio_path) → TranscriptionResult` — synchronous; raises
  `TranscriptionUnavailable` when the adapter cannot transcribe.
- `render_payload(payload) → str` — render a previously-fetched raw payload to the
  drafter-parsing format. Lets the resolver's payload-cache short-circuit a renderer
  change without re-hitting the backend.

`TranscriptionResult.text` is rendered in the canonical format the video drafter
parses (`[Speaker N] (HH:MM:SS)` block headers). `TranscriptionResult.payload` is
the raw backend payload (the resolver caches it alongside the rendered output).

P3 ships `NoOpTranscriber` (the default; raises `TranscriptionUnavailable`) and
`HTTPWhisperTranscriber` (generalized from the reference `whisper.py` — `base_url`
injected at construction, no hardcoded URLs).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "HTTPWhisperTranscriber",
    "NoOpTranscriber",
    "TranscriptionAdapter",
    "TranscriptionResult",
    "TranscriptionUnavailable",
    "get_transcriber",
]


class TranscriptionUnavailable(Exception):
    """The configured adapter cannot transcribe (NoOp, backend down, missing config).
    The video drafter catches this and emits a `transcription-unavailable` issue."""


@dataclass(frozen=True)
class TranscriptionResult:
    """Adapter-neutral result.

    `text` is rendered in the corpus's canonical format (see `render_payload`).
    `payload` is the raw backend payload (used for the resolver's payload cache).
    """

    text: str
    payload: dict[str, Any] | None = None


@runtime_checkable
class TranscriptionAdapter(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Synchronous transcribe. Raises `TranscriptionUnavailable` on failure."""
        ...

    def render_payload(self, payload: dict[str, Any]) -> str:
        """Render a previously-fetched raw payload to the canonical text format.

        Pure — no I/O, no network. The resolver caches `payload` alongside the
        rendered output so a renderer change can re-render without re-hitting the
        backend.
        """
        ...


# Imported here so `corpus.transcription.NoOpTranscriber` / `HTTPWhisperTranscriber`
# remain the public surface, while their definitions live in submodules.
from .http_whisper import HTTPWhisperTranscriber  # noqa: E402
from .noop import NoOpTranscriber  # noqa: E402


def get_transcriber(
    corpus_root: Path, *, overrides: dict[str, Any] | None = None
) -> TranscriptionAdapter:
    """Resolve the configured transcriber for `corpus_root`.

    Defaults to `NoOpTranscriber`. Reads `corpus.toml` + env to dispatch to
    `HTTPWhisperTranscriber` when configured (`CORPUS_TRANSCRIBE=http-whisper`,
    `WHISPER_BASE_URL=…` or `[corpus.transcription] base_url = …` in corpus.toml).

    `overrides` (a per-host origin-overlay `transcription:` section — `adapter` /
    `base_url`) layer over the global config before instantiation, so a host can
    select its own backend even when the corpus default is `noop`.
    """
    from corpus.config import load_config

    cfg = dict(load_config(corpus_root).transcription)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    adapter = cfg["adapter"]
    if adapter == "noop":
        return NoOpTranscriber()
    if adapter == "http-whisper":
        base_url = cfg.get("base_url")
        if not base_url:
            raise ValueError(
                "transcription.adapter = 'http-whisper' requires `base_url` "
                "(set [corpus.transcription] base_url in corpus.toml or "
                "export WHISPER_BASE_URL=…)"
            )
        return HTTPWhisperTranscriber(base_url=str(base_url))
    raise ValueError(f"unknown transcription adapter: {adapter!r}")
