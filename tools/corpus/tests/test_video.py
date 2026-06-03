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
from corpus.draft import _transcript as transcript_mod
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
    secs = transcript_mod.parse_transcript_sections(
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
    # Each section leads with a body-empty image framegrab marker.
    assert first.segments[0].atom == "image" and first.segments[0].body == ""
    assert first.address.startswith("time_range=00:07-")


def test_parse_transcript_sections_frames_unique_lead_and_final_close():
    # Regression: a boundary instant is shared by adjacent speaker runs (run k's end ==
    # run k+1's begin). Each `frame=<t>` address must appear once (§4.3.2.2) — the old
    # code bookended every run, emitting the boundary frame twice and failing lint.
    transcript = (
        "[Speaker 1] (00:00:00)\nA.\n\n"
        "[Speaker 2] (00:00:10)\nB.\n\n"
        "[Speaker 2] (00:00:15)\nC.\n"
    )
    secs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    frames = [seg.address for sec in secs for seg in sec.segments if seg.atom == "image"]
    # No duplicate at the 00:10 boundary; the final section closes with the last frame.
    assert frames == ["frame=00:00", "frame=00:10", "frame=00:15"]
    assert len(frames) == len(set(frames))
    # Every section leads with its keyframe; the final section also closes with one.
    assert all(sec.segments[0].atom == "image" for sec in secs)
    assert secs[-1].segments[-1].atom == "image"


def test_parse_chaptered_sections_uses_chapter_outline():
    # A video that ships chapter markers is sectioned by them (the uploader's outline),
    # the chapter title riding as each section's `entry` TOC label (§4.3.2.2).
    transcript = (
        "[Speaker 1] (00:00:00)\nIntro line.\n\n"
        "[Speaker 1] (00:00:20)\nFirst topic.\n\n"
        "[Speaker 2] (00:00:50)\nSecond topic question.\n\n"
        "[Speaker 1] (00:01:10)\nWrapping up.\n"
    )
    chapters = [
        {"start": 0.0, "end": 40.0, "title": "Intro"},
        {"start": 40.0, "end": 60.0, "title": "Discussion"},
        {"start": 60.0, "end": 80.0, "title": "Outro"},
    ]
    secs = transcript_mod.parse_chaptered_sections(
        transcript,
        chapters,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    # One section per chapter, titled by the chapter.
    assert [s.entry for s in secs] == ["Intro", "Discussion", "Outro"]
    # Chapter time-ranges become the section addresses (contiguous; the last runs to the
    # final checkpoint rather than its declared end_time).
    assert secs[0].address == "time_range=00:00-00:40"
    assert secs[1].address == "time_range=00:40-01:00"
    assert secs[2].address.startswith("time_range=01:00-")
    # Each checkpoint lands in the chapter containing its start.
    def _txt(sec):
        return [g.body for g in sec.segments if g.overlay == "text/transcript"]

    def _spk(sec):
        return [g.extra.get("speaker") for g in sec.segments if g.overlay == "text/transcript"]

    assert _txt(secs[0]) == ["Intro line.", "First topic."]  # 0s, 20s → Intro [0,40)
    assert _txt(secs[1]) == ["Second topic question."]  # 50s → Discussion [40,60)
    # A chapter spanning two speakers keeps each segment's own speaker.
    assert _spk(secs[1]) == [2] and _spk(secs[2]) == [1]
    # Frame markers stay unique and each section leads with one (§4.3.2.2).
    frames = [g.address for s in secs for g in s.segments if g.atom == "image"]
    assert len(frames) == len(set(frames))
    assert all(s.segments[0].atom == "image" for s in secs)


def test_parse_chaptered_sections_no_chapters_with_text_still_emits_lead_frame():
    # A chapter that contains no speech is still a structural section (kept, not dropped),
    # carrying its lead keyframe.
    transcript = "[Speaker 1] (00:00:05)\nOnly in the first chapter.\n"
    chapters = [
        {"start": 0.0, "end": 10.0, "title": "Talk"},
        {"start": 10.0, "end": 20.0, "title": "Silence"},
    ]
    secs = transcript_mod.parse_chaptered_sections(
        transcript,
        chapters,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    assert [s.entry for s in secs] == ["Talk", "Silence"]
    # The speechless chapter has its lead frame but no transcript segment.
    assert all(g.overlay != "text/transcript" for g in secs[1].segments)
    assert secs[1].segments[0].atom == "image"


def test_parse_transcript_sections_no_video_stream_omits_frames():
    secs = transcript_mod.parse_transcript_sections(
        _TRANSCRIPT,
        audio_stream_id="a0",
        video_stream_id=None,
        multi_audio=False,
        multi_video=False,
    )
    assert all(seg.atom == "text" for sec in secs for seg in sec.segments)


def test_parse_transcript_multi_audio_adds_stream_id():
    secs = transcript_mod.parse_transcript_sections(
        _TRANSCRIPT, audio_stream_id="a1", video_stream_id=None, multi_audio=True, multi_video=False
    )
    assert "&stream_id=a1" in secs[0].address


@pytest.mark.parametrize("s,tc", [(7, "00:07"), (75, "01:15"), (3661, "01:01:01")])
def test_seconds_to_timecode(s, tc):
    assert transcript_mod.seconds_to_timecode(s) == tc


def test_speaker_label_to_index():
    assert transcript_mod.speaker_label_to_index("Speaker 3") == 3
    assert transcript_mod.speaker_label_to_index("narrator") is None


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
