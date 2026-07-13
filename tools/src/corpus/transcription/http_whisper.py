"""HTTPWhisperTranscriber — thin client for a FastAPI/whisperx server.

Generalized from the reference `whisper.py`: `base_url` is injected at construction
(no hardcoded URLs). The server's API:

    POST /transcribe        # multipart `file`; returns {job_id, status}
    GET  /result/{job_id}   # returns {status, result, error, ...}
    GET  /health

Transcription is asynchronous: POST returns a `job_id` immediately, then the client
polls `/result/{job_id}` until `status` leaves `"processing"`. On `status: "done"`,
the response carries `result.segments` and `result.word_segments` in whisperx-
compatible shape, including per-segment `speaker` labels with whole-file diarization.

The `render_payload` output is a stable contract — the video drafter (P5) parses
this exact `[Speaker N] (HH:MM:SS)` format. Changes to the rendering must keep that
contract or update the drafter.

Long audio is chunked and re-assembled server-side; this client submits whatever
duration the caller hands it in a single shot.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from . import TranscriptionResult, TranscriptionUnavailable

log = logging.getLogger(__name__)


class HTTPWhisperTranscriber:
    """Whisperx-compatible HTTP transcription backend.

    `base_url` is required at construction; no defaults. `poll_interval_s` and
    `poll_max_s` may be tuned for short-or-fast test setups. `submit_timeout_s`
    bounds the POST/GET request timeouts.
    """

    #: Adapter-contract version — bumped when the request/response handling or canonical
    #: text rendering changes, so an upgrade invalidates the version-labeled cache (§6.4).
    ADAPTER_VERSION = "1"

    def __init__(
        self,
        *,
        base_url: str,
        model: str | None = None,
        submit_timeout_s: float = 30.0,
        poll_interval_s: float = 5.0,
        poll_max_s: float = 60 * 60 * 2,  # 2h ceiling
    ):
        if not base_url:
            raise ValueError("HTTPWhisperTranscriber requires a base_url")
        self._base_url = base_url.rstrip("/")
        self._model = str(model).strip() if model else None
        self._timeout = submit_timeout_s
        self._poll_interval = poll_interval_s
        self._poll_max = poll_max_s

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def engine(self) -> str:
        """Engine id for §6.4 version-labeling of the `transcribe` op's cache:
        `http-whisper/<model>@<version>` when the corpus declares a `transcription.model`, else
        `http-whisper@<version>`. The version is the adapter contract's; a model-version
        component appears only where the operator names the model (the remote backend does not
        report it — the stated model-version-granularity deferral)."""
        stem = f"http-whisper/{self._model}" if self._model else "http-whisper"
        return f"{stem}@{self.ADAPTER_VERSION}"

    # ---- TranscriptionAdapter surface ---- #

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        try:
            payload = self._fetch_payload(audio_path)
        except urllib.error.URLError as exc:
            raise TranscriptionUnavailable(
                f"whisper backend unreachable at {self._base_url}: {exc}"
            ) from exc
        text = self.render_payload(payload)
        return TranscriptionResult(text=text, payload=payload)

    def render_payload(self, payload: dict[str, Any]) -> str:
        """Render the server's response into the canonical text format.

        Output is segment-granular: one block per Whisper segment, each block
        carrying its own `[Speaker N] (HH:MM:SS)` header. Speaker IDs are
        remapped to 1-indexed labels in order of first appearance.

        Segments without a speaker render with the timestamp header alone:

            (00:01:23)
            <segment text>
        """
        result = payload.get("result") or {}
        segments = result.get("segments") or []
        if not segments:
            return ""

        speaker_index: dict[str, int] = {}
        blocks: list[str] = []
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            start = seg.get("start", 0.0) or 0.0
            speaker_raw = seg.get("speaker")
            if speaker_raw:
                if speaker_raw not in speaker_index:
                    speaker_index[speaker_raw] = len(speaker_index) + 1
                label = f"[Speaker {speaker_index[speaker_raw]}]"
            else:
                label = ""
            timestamp = _format_timestamp(start)
            header = f"{label} ({timestamp})" if label else f"({timestamp})"
            blocks.append(f"{header}\n{text}")
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    # ---- internals ---- #

    def _fetch_payload(self, audio_path: Path) -> dict[str, Any]:
        log.info("whisper: submitting %s", audio_path.name)
        job_id = self._submit(audio_path)
        log.info("whisper: job %s queued", job_id)
        return self._poll(job_id)

    def _submit(self, audio_path: Path) -> str:
        body, content_type = _build_multipart(audio_path)
        req = urllib.request.Request(
            f"{self._base_url}/transcribe",
            data=body,
            method="POST",
            headers={"Content-Type": content_type, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            excerpt = exc.read().decode("utf-8", "replace")[:512]
            raise TranscriptionUnavailable(
                f"transcribe POST failed: HTTP {exc.code}: {excerpt}"
            ) from exc
        job_id = payload.get("job_id")
        if not job_id:
            raise TranscriptionUnavailable(
                f"transcribe POST returned no job_id: {payload!r}"
            )
        return str(job_id)

    def _poll(self, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._poll_max
        url = f"{self._base_url}/result/{job_id}"
        while True:
            try:
                with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                excerpt = exc.read().decode("utf-8", "replace")[:512]
                raise TranscriptionUnavailable(
                    f"result GET failed: HTTP {exc.code}: {excerpt}"
                ) from exc

            status = payload.get("status")
            if status == "done":
                log.info("whisper: job %s done", job_id)
                return payload
            if status in {"error", "failed"}:
                err = payload.get("error") or "<no detail>"
                raise TranscriptionUnavailable(f"transcription failed: {err}")
            if status not in {"processing", "queued"}:
                raise TranscriptionUnavailable(
                    f"unexpected status from server: {status!r}"
                )
            if time.monotonic() > deadline:
                raise TranscriptionUnavailable(
                    f"transcription job {job_id} did not complete within {self._poll_max}s"
                )
            time.sleep(self._poll_interval)


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _build_multipart(audio_path: Path) -> tuple[bytes, str]:
    """Hand-built multipart/form-data body with a single `file` field."""
    boundary = f"----corpus-whisper-{uuid.uuid4().hex}"
    content_type, _ = mimetypes.guess_type(audio_path.name)
    content_type = content_type or "application/octet-stream"
    file_bytes = audio_path.read_bytes()

    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        (
            f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"
