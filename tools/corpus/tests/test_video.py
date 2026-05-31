"""P5a — video/audio transforms, the resolver AV plumbing, and the video drafter.

All offline. The audio `transcribe` transform is driven with a stub adapter; the
drafter's `transcription-unavailable` mapping is exercised by monkeypatching the
resolver. The real ffmpeg round-trip is gated on ffmpeg being installed; the full
whisper round-trip is network-marked and skipped by default.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import frontmatter
import pytest

from corpus import paths, records, resolver
from corpus.draft import video as video_mod
from corpus.transcription import TranscriptionResult, TranscriptionUnavailable
from corpus.transforms import audio as audio_tf
from corpus.transforms import video as video_tf

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None


# ---------- stub adapters ---------- #


class _StubTranscriber:
    def __init__(self, text: str, payload: dict | None = None) -> None:
        self._text = text
        self._payload = payload

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        return TranscriptionResult(text=self._text, payload=self._payload)

    def render_payload(self, payload: dict) -> str:
        return self._text


class _FailTranscriber:
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        raise TranscriptionUnavailable("backend down")

    def render_payload(self, payload: dict) -> str:
        raise TranscriptionUnavailable("backend down")


# ---------- audio transcribe transform ---------- #


def test_transcribe_transform_uses_ctx_transcriber(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00\x01")
    ctx = {"transcriber": _StubTranscriber("[Speaker 1] (00:00:00)\nHi.\n", payload={"k": 1})}
    out = audio_tf.transcribe(audio, None, ctx)
    assert out == "[Speaker 1] (00:00:00)\nHi.\n"
    assert ctx["transcription_payload"] == {"k": 1}  # stashed for re-render


def test_transcribe_transform_propagates_unavailable(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00")
    with pytest.raises(TranscriptionUnavailable):
        audio_tf.transcribe(audio, None, {"transcriber": _FailTranscriber()})


def test_transcribe_transform_no_adapter_raises():
    with pytest.raises(TranscriptionUnavailable):
        audio_tf.transcribe(Path("/nope.mp3"), None, {})


def test_transcribe_transform_rejects_value(tmp_path):
    with pytest.raises(ValueError):
        audio_tf.transcribe(tmp_path / "a.mp3", "x", {"transcriber": _StubTranscriber("t")})


# ---------- video transform validation (no ffmpeg needed) ---------- #


def test_extract_audio_rejects_value():
    with pytest.raises(ValueError):
        video_tf.extract_audio(Path("/v.mp4"), "x", {})


def test_frame_requires_value():
    with pytest.raises(ValueError):
        video_tf.frame(Path("/v.mp4"), None, {})


def test_frame_rejects_past_duration():
    with pytest.raises(ValueError, match="past the end"):
        video_tf.frame(Path("/v.mp4"), "120", {"video_duration_seconds": 60.0})


@pytest.mark.parametrize(
    "spec,seconds",
    [("120", 120.0), ("12.5", 12.5), ("02:00", 120.0), ("01:30:45", 5445.0)],
)
def test_parse_timecode(spec, seconds):
    assert video_tf._parse_timecode_to_seconds(spec) == seconds


# ---------- resolver AV plumbing (offline, stub transcriber) ---------- #


def _make_audio_record(root: Path, rid: str) -> None:
    art = paths.artifact_path(root, rid, "mp3")
    paths.ensure_parent(art)
    art.write_bytes(b"ID3fake-audio-bytes")
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="audio/mpeg", fields={"title": "clip"})
    records.append_origin_block(post, uri="https://e.com/clip.mp3", snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))


def test_resolver_audio_transcribe_with_stub(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    rid = "aa" * 32
    _make_audio_record(root, rid)

    out = resolver.resolve(
        f"corpus://{rid}?transcribe",
        root,
        transcriber=_StubTranscriber("[Speaker 1] (00:00:03)\nHello.\n"),
    )
    assert out.is_file()
    assert out.read_text(encoding="utf-8") == "[Speaker 1] (00:00:03)\nHello.\n"
    assert out.suffix == ".txt"


def test_resolver_audio_transcribe_noop_raises(tmp_path, monkeypatch):
    for k in ("CORPUS_TRANSCRIBE", "WHISPER_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    rid = "bb" * 32
    _make_audio_record(root, rid)
    # No transcriber passed → defaults to the configured one (NoOp, no config).
    with pytest.raises(TranscriptionUnavailable):
        resolver.resolve(f"corpus://{rid}?transcribe", root)


# ---------- video drafter ---------- #

_TRANSCRIPT = (
    "[Speaker 1] (00:00:07)\nHello everyone.\n\n"
    "[Speaker 1] (00:00:12)\nToday, three topics.\n\n"
    "[Speaker 2] (00:00:21)\nSo how does it work?\n"
)


def test_parse_transcript_sections_speaker_runs():
    secs = video_mod._parse_transcript_sections(
        _TRANSCRIPT,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    assert len(secs) == 2  # Speaker 1 run, Speaker 2 run
    first = secs[0]
    transcripts = [s for s in first.segments if s.overlay == "text/transcript"]
    assert len(transcripts) == 2
    assert all(s.extra.get("speaker") == 1 for s in transcripts)
    # Bookended by image framegrab markers (body-empty).
    assert first.segments[0].atom == "image" and first.segments[0].body == ""
    assert first.address.startswith("time_range=00:07-")


def test_parse_transcript_sections_no_video_stream_omits_frames():
    secs = video_mod._parse_transcript_sections(
        _TRANSCRIPT,
        audio_stream_id="a0",
        video_stream_id=None,
        multi_audio=False,
        multi_video=False,
    )
    assert all(seg.atom == "text" for sec in secs for seg in sec.segments)


def test_parse_transcript_multi_audio_adds_stream_id():
    secs = video_mod._parse_transcript_sections(
        _TRANSCRIPT, audio_stream_id="a1", video_stream_id=None, multi_audio=True, multi_video=False
    )
    assert "&stream_id=a1" in secs[0].address


@pytest.mark.parametrize("s,tc", [(7, "00:07"), (75, "01:15"), (3661, "01:01:01")])
def test_seconds_to_timecode(s, tc):
    assert video_mod._seconds_to_timecode(s) == tc


def test_speaker_label_to_index():
    assert video_mod._speaker_label_to_index("Speaker 3") == 3
    assert video_mod._speaker_label_to_index("narrator") is None


def test_unavailable_issue_is_spec_shaped():
    from corpus.lint import _TOUCH_RE

    iss = video_mod._unavailable_issue("warning", "no adapter")
    assert iss["id"] == "transcription-unavailable"
    assert iss["severity"] == "warning"
    assert iss["resolution"] == "open"
    assert _TOUCH_RE.match(iss["detector"])


def _make_video_record_file(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    rid = "cc" * 32
    vid = paths.artifact_path(root, rid, "mp4")
    paths.ensure_parent(vid)
    vid.write_bytes(b"\x00\x00\x00\x18ftypmp42not-a-real-video")
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="video/mp4", fields={"title": "v"})
    records.append_origin_block(post, uri="https://e.com/v.mp4", snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return root, vid, rid


def test_video_draft_transcription_unavailable(tmp_path, monkeypatch):
    """NoOp/unavailable transcription → record with a warning issue, no sections."""
    root, vid, rid = _make_video_record_file(tmp_path)

    def _raise(uri, corpus_root, **kw):
        raise TranscriptionUnavailable("no adapter")

    monkeypatch.setattr(resolver, "resolve", _raise)
    result = video_mod.draft(vid, corpus_root=root, record_id=rid)
    assert result["segments"] == []
    issues = result["issues"]
    assert len(issues) == 1
    assert issues[0]["id"] == "transcription-unavailable"
    assert issues[0]["severity"] == "warning"


def test_video_draft_empty_transcript_info_issue(tmp_path, monkeypatch):
    root, vid, rid = _make_video_record_file(tmp_path)
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(resolver, "resolve", lambda *a, **k: empty)
    result = video_mod.draft(vid, corpus_root=root, record_id=rid)
    assert result["segments"] == []
    assert result["issues"][0]["severity"] == "info"


def test_video_draft_with_transcript_builds_sections(tmp_path, monkeypatch):
    root, vid, rid = _make_video_record_file(tmp_path)
    tx = tmp_path / "tx.txt"
    tx.write_text(_TRANSCRIPT, encoding="utf-8")
    monkeypatch.setattr(resolver, "resolve", lambda *a, **k: tx)
    result = video_mod.draft(vid, corpus_root=root, record_id=rid)
    assert result["issues"] == []
    assert len(result["segments"]) == 2
    assert result["fields"]["is_diarized"] is True
    assert {sp["id"] for sp in result["fields"]["speakers"]} == {1, 2}


# ---------- real ffmpeg round-trip (gated) ---------- #


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")
def test_ffmpeg_extract_audio_and_frame(tmp_path):
    src = tmp_path / "test.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-shortest", str(src),
        ],
        check=True,
    )
    out_audio = video_tf.extract_audio(src, None, {})
    assert out_audio.is_file() and out_audio.stat().st_size > 0
    out_audio.unlink(missing_ok=True)

    img = video_tf.frame(src, "0", {})
    assert img.width == 160 and img.height == 120
