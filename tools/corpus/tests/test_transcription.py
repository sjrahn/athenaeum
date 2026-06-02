"""Transcription adapter tests: NoOp default, HTTPWhisper round-trip."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from corpus.transcription import (
    HTTPWhisperTranscriber,
    NoOpTranscriber,
    TranscriptionAdapter,
    TranscriptionResult,
    TranscriptionUnavailable,
    get_transcriber,
)

# ---------- NoOp ---------- #


def test_noop_satisfies_protocol():
    assert isinstance(NoOpTranscriber(), TranscriptionAdapter)


def test_noop_transcribe_raises(tmp_path):
    fake_audio = tmp_path / "a.wav"
    fake_audio.write_bytes(b"\x00" * 16)
    with pytest.raises(TranscriptionUnavailable) as ei:
        NoOpTranscriber().transcribe(fake_audio)
    assert "no transcription adapter configured" in str(ei.value)


def test_noop_render_payload_also_raises():
    with pytest.raises(TranscriptionUnavailable):
        NoOpTranscriber().render_payload({"result": {"segments": []}})


# ---------- get_transcriber dispatch ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def test_get_transcriber_returns_noop_by_default(tmp_path, monkeypatch):
    for k in ("CORPUS_TRANSCRIBE", "WHISPER_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    root = _make_corpus(tmp_path)
    t = get_transcriber(root)
    assert isinstance(t, NoOpTranscriber)


def test_get_transcriber_returns_http_whisper_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_TRANSCRIBE", "http-whisper")
    monkeypatch.setenv("WHISPER_BASE_URL", "http://example.test:9000")
    root = _make_corpus(tmp_path)
    t = get_transcriber(root)
    assert isinstance(t, HTTPWhisperTranscriber)
    assert t.base_url == "http://example.test:9000"


def test_get_transcriber_http_whisper_requires_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_TRANSCRIBE", "http-whisper")
    monkeypatch.delenv("WHISPER_BASE_URL", raising=False)
    root = _make_corpus(tmp_path)
    with pytest.raises(ValueError, match="base_url"):
        get_transcriber(root)


def test_get_transcriber_overrides_select_backend(tmp_path, monkeypatch):
    # Global default is noop; a per-host override picks http-whisper.
    for k in ("CORPUS_TRANSCRIBE", "WHISPER_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    root = _make_corpus(tmp_path)
    t = get_transcriber(root, overrides={"adapter": "http-whisper", "base_url": "http://h:9000"})
    assert isinstance(t, HTTPWhisperTranscriber) and t.base_url == "http://h:9000"


# ---------- per-host transcription decision (draft-time) ---------- #


def _overlay_corpus(tmp_path: Path, **overlays: str) -> Path:
    root = _make_corpus(tmp_path)
    d = root / "schema" / "origin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "origin.yaml").write_text("description: t\nextended_fields: {}\n", encoding="utf-8")
    for name, body in overlays.items():
        (d / f"{name}.yaml").write_text(body, encoding="utf-8")
    return root


def _meta(uri: str) -> dict[str, Any]:
    return {"_origins": [{"fields": {"uri": uri}}]}


def test_resolve_transcription_global_when_no_section(tmp_path):
    from corpus.draft._hostcfg import resolve_transcription

    root = _overlay_corpus(tmp_path)
    mode, t = resolve_transcription(root, _meta("https://example.com/v"))
    assert mode == "global" and t is None


def test_resolve_transcription_disabled(tmp_path):
    from corpus.draft._hostcfg import resolve_transcription

    root = _overlay_corpus(
        tmp_path,
        ex="applies_to: {host_pattern: example.com}\ntranscription: {enabled: false}\n",
    )
    mode, t = resolve_transcription(root, _meta("https://example.com/v"))
    assert mode == "disabled" and t is None


def test_resolve_transcription_per_host_override(tmp_path, monkeypatch):
    for k in ("CORPUS_TRANSCRIBE", "WHISPER_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    from corpus.draft._hostcfg import resolve_transcription

    root = _overlay_corpus(
        tmp_path,
        ex="applies_to: {host_pattern: example.com}\n"
        "transcription: {adapter: http-whisper, base_url: 'http://h:9000'}\n",
    )
    mode, t = resolve_transcription(root, _meta("https://example.com/v"))
    assert mode == "override"
    assert isinstance(t, HTTPWhisperTranscriber) and t.base_url == "http://h:9000"


# ---------- HTTPWhisper render contract (pure) ---------- #


def test_render_payload_format_speakers_remapped_and_timestamped():
    """The rendered format is the drafter-parsing contract — pin it."""
    transcriber = HTTPWhisperTranscriber(base_url="http://unused.test")
    payload = {
        "result": {
            "segments": [
                {"speaker": "SPEAKER_07", "start": 7.0, "text": "Hello, everyone."},
                {"speaker": "SPEAKER_07", "start": 14.5, "text": "Welcome."},
                {"speaker": "SPEAKER_02", "start": 21.0, "text": "Thanks for joining."},
                {"speaker": "SPEAKER_07", "start": 31.0, "text": "Today's topic is…"},
            ]
        }
    }
    text = transcriber.render_payload(payload)
    # First-appearance order: SPEAKER_07 → Speaker 1, SPEAKER_02 → Speaker 2.
    assert "[Speaker 1] (00:00:07)\nHello, everyone." in text
    assert "[Speaker 1] (00:00:14)\nWelcome." in text
    assert "[Speaker 2] (00:00:21)\nThanks for joining." in text
    assert "[Speaker 1] (00:00:31)\nToday's topic is…" in text
    # Blocks separated by blank lines.
    assert "\n\n" in text


def test_render_payload_missing_speaker_emits_timestamp_only():
    transcriber = HTTPWhisperTranscriber(base_url="http://unused.test")
    payload = {
        "result": {
            "segments": [{"start": 83.0, "text": "Standalone snippet."}]
        }
    }
    text = transcriber.render_payload(payload)
    assert text.startswith("(00:01:23)\nStandalone snippet.")


def test_render_payload_empty_segments():
    transcriber = HTTPWhisperTranscriber(base_url="http://unused.test")
    assert transcriber.render_payload({"result": {"segments": []}}) == ""
    assert transcriber.render_payload({}) == ""


# ---------- HTTPWhisper full round-trip against an in-process mock server ---------- #


class _FakeWhisperHandler(BaseHTTPRequestHandler):
    """Mock /transcribe + /result endpoints. Returns a queued state once then done."""

    JOB_ID = "job-abc-123"
    POLL_COUNT: ClassVar[dict[str, int]] = {"n": 0}
    RESULT_PAYLOAD: ClassVar[dict[str, Any]] = {
        "status": "done",
        "result": {
            "segments": [
                {"speaker": "SPEAKER_01", "start": 0.0, "text": "Mock transcript."},
                {"speaker": "SPEAKER_01", "start": 5.0, "text": "Second segment."},
            ]
        },
    }

    def do_POST(self):
        if self.path == "/transcribe":
            content_length = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(content_length)  # drain the body
            body = json.dumps({"job_id": self.JOB_ID, "status": "queued"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_GET(self):
        if self.path == f"/result/{self.JOB_ID}":
            self.POLL_COUNT["n"] += 1
            # Return "processing" once, then "done".
            if self.POLL_COUNT["n"] == 1:
                payload: dict[str, Any] = {"status": "processing"}
            else:
                payload = self.RESULT_PAYLOAD
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format, *args):
        pass


def _spawn_fake_whisper() -> tuple[HTTPServer, str]:
    """Start an in-process HTTP server on a random port. Returns (server, base_url)."""
    _FakeWhisperHandler.POLL_COUNT["n"] = 0
    server = HTTPServer(("127.0.0.1", 0), _FakeWhisperHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def test_http_whisper_transcribe_round_trip(tmp_path):
    server, base_url = _spawn_fake_whisper()
    try:
        transcriber = HTTPWhisperTranscriber(
            base_url=base_url,
            poll_interval_s=0.01,
            poll_max_s=5.0,
        )
        audio = tmp_path / "clip.wav"
        audio.write_bytes(b"\x00\x01\x02" * 32)
        result = transcriber.transcribe(audio)
    finally:
        server.shutdown()
    assert isinstance(result, TranscriptionResult)
    assert "[Speaker 1] (00:00:00)\nMock transcript." in result.text
    assert "[Speaker 1] (00:00:05)\nSecond segment." in result.text
    assert result.payload is not None
    assert result.payload["status"] == "done"


def test_http_whisper_unreachable_raises_transcription_unavailable(tmp_path):
    """A closed port → URLError → TranscriptionUnavailable."""
    transcriber = HTTPWhisperTranscriber(
        base_url="http://127.0.0.1:1",  # unlikely to be bound
        submit_timeout_s=0.3,
        poll_interval_s=0.01,
        poll_max_s=1.0,
    )
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"\x00")
    with pytest.raises(TranscriptionUnavailable):
        transcriber.transcribe(audio)
