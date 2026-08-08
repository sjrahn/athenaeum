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
    segs = transcript_mod.parse_transcript_sections(
        _TRANSCRIPT,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    # A speaker change carries no source-stated label — no structural mark anywhere.
    assert not any(s.is_structural for s in segs)
    transcripts = [s for s in segs if s.overlay == "text/transcript"]
    assert len(transcripts) == 3
    assert [t.extra.get("speaker") for t in transcripts] == [1, 1, 2]
    # Each speaker run leads with a body-empty image framegrab marker.
    frames = [s for s in segs if s.atom == "image"]
    assert [f.address for f in frames] == ["frame=00:07", "frame=00:21"]
    assert all(f.body == "" for f in frames)
    assert segs[0].address == "frame=00:07"
    assert segs[1].address == "time_range=00:07-00:12"


def test_parse_transcript_sections_frames_unique_lead_and_final_close():
    # Regression: a boundary instant is shared by adjacent speaker runs (run k's end ==
    # run k+1's begin). Each `frame=<t>` address must appear once (§4.3.2.2) — the old
    # code bookended every run, emitting the boundary frame twice and failing lint.
    transcript = (
        "[Speaker 1] (00:00:00)\nA.\n\n"
        "[Speaker 2] (00:00:10)\nB.\n\n"
        "[Speaker 2] (00:00:15)\nC.\n"
    )
    segs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    frames = [seg.address for seg in segs if seg.atom == "image"]
    # No duplicate at the 00:10 boundary; the final run closes with the last frame.
    assert frames == ["frame=00:00", "frame=00:10", "frame=00:15"]
    assert len(frames) == len(set(frames))
    # The very last segment is the closing keyframe.
    assert segs[-1].atom == "image"


def test_parse_transcript_sections_single_segment_spans_media_duration():
    # Regression (gotcha): a short continuous-speech clip can come back from whisper as a
    # SINGLE segment at start=0. Without the probed media duration the lone speaker run's
    # end fell back to last_cp + 0.001 → a degenerate `00:00-00:00` range. media_duration
    # bounds it to the true clip length so it reads `00:00-<duration>`.
    transcript = "[Speaker 1] (00:00:00)\nA continuous rant with no pauses.\n"
    segs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
        media_duration=22.13,
    )
    transcripts = [s for s in segs if s.overlay == "text/transcript"]
    assert len(transcripts) == 1
    assert transcripts[0].address == "time_range=00:00-00:22"
    # The lone run bookends: lead frame at 0, closing frame at the true end.
    frames = [g.address for g in segs if g.atom == "image"]
    assert frames == ["frame=00:00", "frame=00:22"]


def test_parse_transcript_sections_single_segment_without_duration_falls_back():
    # No media_duration → preserve the legacy near-zero end (no regression for callers
    # that don't pass a duration; the audio/video drafters now always do).
    transcript = "[Speaker 1] (00:00:00)\nShort.\n"
    segs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id=None,
        multi_audio=False,
        multi_video=False,
    )
    assert segs[0].address == "time_range=00:00-00:00"


def _transcript_addresses(segs):
    return [s.address for s in segs if s.overlay == "text/transcript"]


def _duplicate_findings(segs):
    # Run the real `segment-address-duplicate` lint rule over the emitted blocks. The rule
    # only reads `blocks`, so pass empty post/root — it's the record-global (opener-id,
    # address) uniqueness check the drafter must satisfy (§4.3.2.2).
    from corpus.lint import _rule_segment_address_duplicate

    return list(_rule_segment_address_duplicate(None, list(segs), None))


def test_parse_transcript_sections_zero_width_collision_merges():
    # Regression (real case): whisper occasionally returns consecutive same-speaker segments
    # whose start AND end both round to the SAME whole second (zero-width, `S-S`). A 2.6h
    # livestream had exactly one such pair ("Oh, sorry." then "Yeah."), both landing at
    # `time_range=02:14:56-02:14:56` — identical (opener-id, address), failing
    # `segment-address-duplicate`. The drafter must fold the second into the first
    # (concatenated text, one segment), mirroring the hand-fix. Here both checkpoints sit
    # at the same second and the lone speaker run (no media_duration) ends at the same
    # second, so both render `02:30-02:30`.
    transcript = "[Speaker 1] (00:02:30)\nOh, sorry.\n\n[Speaker 1] (00:02:30)\nYeah.\n"
    segs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    ts = [s for s in segs if s.overlay == "text/transcript"]
    assert len(ts) == 1  # the colliding pair merged into one segment
    assert ts[0].address == "time_range=02:30-02:30"
    assert ts[0].body == "Oh, sorry. Yeah."  # verbatim text concatenated with a space
    assert ts[0].extra.get("speaker") == 1  # same-speaker merge keeps attribution
    # No two segments share a (opener-id, address); lint is clean.
    addrs = _transcript_addresses(segs)
    assert len(addrs) == len(set(addrs))
    assert _duplicate_findings(segs) == []


def test_parse_transcript_sections_three_in_a_row_collision_merges():
    # Three consecutive same-second same-speaker zero-width checkpoints fold one-by-one into
    # a single running segment (the rare 3+ collision).
    transcript = (
        "[Speaker 1] (00:02:30)\nOh, sorry.\n\n"
        "[Speaker 1] (00:02:30)\nYeah.\n\n"
        "[Speaker 1] (00:02:30)\nRight.\n"
    )
    segs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    ts = [s for s in segs if s.overlay == "text/transcript"]
    assert len(ts) == 1
    assert ts[0].body == "Oh, sorry. Yeah. Right."
    addrs = _transcript_addresses(segs)
    assert len(addrs) == len(set(addrs))
    assert _duplicate_findings(segs) == []


def test_parse_transcript_sections_cross_speaker_collision_dedups_globally():
    # Pathological: a diarization flip at one zero-width instant lands two segments at the
    # same `S-S` address in ADJACENT runs (speaker change is a grouping boundary). The
    # record-global ledger still folds the second into the first; because the merged span
    # genuinely spans two speakers, its `speaker` is dropped (like a multi-speaker chapter),
    # and the now-emptied trailing run contributes nothing — no phantom marker, no
    # duplicate address.
    transcript = "[Speaker 1] (00:02:30)\nOh, sorry.\n\n[Speaker 2] (00:02:30)\nYeah.\n"
    segs = transcript_mod.parse_transcript_sections(
        transcript,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    ts = [s for s in segs if s.overlay == "text/transcript"]
    assert len(ts) == 1
    assert ts[0].body == "Oh, sorry. Yeah."
    assert "speaker" not in ts[0].extra  # spans two speakers → no single attribution
    assert len(segs) == 2  # the lead frame + the one merged transcript segment
    addrs = _transcript_addresses(segs)
    assert len(addrs) == len(set(addrs))
    assert _duplicate_findings(segs) == []


def test_parse_chaptered_sections_zero_width_collision_merges():
    # The chaptered path runs through the same `_emit_sections` choke point: two same-second
    # checkpoints inside one chapter must merge too.
    transcript = "[Speaker 1] (00:00:05)\nOne.\n\n[Speaker 1] (00:00:05)\nTwo.\n"
    chapters = [{"start": 0.0, "end": 5.0, "title": "Only"}]
    segs = transcript_mod.parse_chaptered_sections(
        transcript,
        chapters,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    ts = [s for s in segs if s.overlay == "text/transcript"]
    assert [s.body for s in ts] == ["One. Two."]
    assert _duplicate_findings(segs) == []


def test_parse_chaptered_sections_uses_chapter_outline():
    # A video that ships chapter markers is grouped by them (the uploader's outline), each
    # chapter's own title becoming a leading structural mark (§4.3.2.3) rather than a
    # Section's `entry`.
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
    segs = transcript_mod.parse_chaptered_sections(
        transcript,
        chapters,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    # One mark per chapter, titled by the chapter, at the chapter's own start instant.
    marks = [s for s in segs if s.is_structural]
    assert [(m.body, m.address) for m in marks] == [
        ("Intro", "time=00:00"),
        ("Discussion", "time=00:40"),
        ("Outro", "time=01:00"),
    ]
    # Each checkpoint lands in the chapter containing its start, in reading order, and a
    # chapter spanning two speakers keeps each segment's own speaker.
    ts = [s for s in segs if s.overlay == "text/transcript"]
    assert [t.body for t in ts] == [
        "Intro line.", "First topic.", "Second topic question.", "Wrapping up.",
    ]
    assert [t.extra.get("speaker") for t in ts] == [1, 1, 2, 1]
    # The exact flat reading order: each chapter's mark leads its own frame and content.
    assert [(s.atom, s.address) for s in segs] == [
        ("structural", "time=00:00"),
        ("image", "frame=00:00"),
        ("text", "time_range=00:00-00:20"),
        ("text", "time_range=00:20-00:40"),
        ("structural", "time=00:40"),
        ("image", "frame=00:40"),
        ("text", "time_range=00:50-01:00"),
        ("structural", "time=01:00"),
        ("image", "frame=01:00"),
        ("text", "time_range=01:10-01:10"),
        ("image", "frame=01:10"),
    ]
    # Frame markers stay unique (§4.3.2.2).
    frames = [s.address for s in segs if s.atom == "image"]
    assert len(frames) == len(set(frames))


def test_parse_chaptered_sections_no_chapters_with_text_still_emits_lead_frame():
    # A chapter that contains no speech is still a structural unit (kept, not dropped),
    # carrying its mark and lead keyframe.
    transcript = "[Speaker 1] (00:00:05)\nOnly in the first chapter.\n"
    chapters = [
        {"start": 0.0, "end": 10.0, "title": "Talk"},
        {"start": 10.0, "end": 20.0, "title": "Silence"},
    ]
    segs = transcript_mod.parse_chaptered_sections(
        transcript,
        chapters,
        audio_stream_id="a0",
        video_stream_id="v0",
        multi_audio=False,
        multi_video=False,
    )
    marks = [s for s in segs if s.is_structural]
    assert [m.body for m in marks] == ["Talk", "Silence"]
    # The speechless chapter's mark is still followed by its lead frame, no transcript.
    silence_idx = segs.index(marks[1])
    assert segs[silence_idx + 1].atom == "image"
    assert not any(s.overlay == "text/transcript" for s in segs[silence_idx:])


def test_parse_transcript_sections_no_video_stream_omits_frames():
    segs = transcript_mod.parse_transcript_sections(
        _TRANSCRIPT,
        audio_stream_id="a0",
        video_stream_id=None,
        multi_audio=False,
        multi_video=False,
    )
    assert all(seg.atom == "text" for seg in segs)


def test_parse_transcript_multi_audio_adds_stream_id():
    segs = transcript_mod.parse_transcript_sections(
        _TRANSCRIPT, audio_stream_id="a1", video_stream_id=None, multi_audio=True, multi_video=False
    )
    assert "&stream_id=a1" in segs[0].address


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


# ---------- (3.11, #131) the container does NOT transcribe ---------- #
#
# These three replace the tests that pinned the OPPOSITE contract. Until 3.11 the video drafter
# resolved `?extract_audio&transcribe` against the container and wrote `text/transcript` sections
# into the container's own content zone — the parent rendering a member's bytes, forbidden by
# §4.3.2.2 since 3.8 and surviving only because no video schema declared `disposition: manifest`.
# The transcript is the audio stream leaf's own content now (`draft/audio.py`, §1.2), so the
# assertions invert: the container must produce NO sections, NO diarization fields, and — this is
# the part worth pinning — must not so much as ASK the transcriber.


def test_the_container_never_calls_the_transcriber(tmp_path, monkeypatch, run_drafter):
    """The strongest form of the rule. A drafter that called `transcribe` and discarded the
    result would pass a "no sections" assertion while still burning a whisper run per container
    — and would re-emit onto the container whatever #134's migration moved off it."""
    root, vid, rid = _make_video_record_file(tmp_path)
    calls: list[str] = []

    def _spy(uri, corpus_root, **kw):
        calls.append(uri)
        raise AssertionError(f"the container drafter resolved {uri!r}")

    monkeypatch.setattr(resolver, "resolve", _spy)
    result, blocks = run_drafter(video_mod.draft, vid, corpus_root=root, record_id=rid)
    assert calls == []
    assert blocks == []
    assert result["issues"] == []


def test_the_container_reports_no_transcription_issues(tmp_path, monkeypatch, run_drafter):
    """`transcription-unavailable` was a fact about the container's own drafting. It is now the
    audio leaf's to report — a container that never transcribes cannot fail to."""
    root, vid, rid = _make_video_record_file(tmp_path)

    def _raise(uri, corpus_root, **kw):
        raise TranscriptionUnavailable("no adapter")

    monkeypatch.setattr(resolver, "resolve", _raise)
    result, _blocks = run_drafter(video_mod.draft, vid, corpus_root=root, record_id=rid)
    assert [i["id"] for i in result["issues"]] == []


def test_the_container_attests_no_diarization(tmp_path, monkeypatch, run_drafter):
    """`speakers:` / `is_diarized` are facts about an audio STREAM, not about the container that
    carries it — they move with the transcript."""
    root, vid, rid = _make_video_record_file(tmp_path)
    tx = tmp_path / "tx.txt"
    tx.write_text(_TRANSCRIPT, encoding="utf-8")
    monkeypatch.setattr(resolver, "resolve", lambda *a, **k: tx)
    result, blocks = run_drafter(video_mod.draft, vid, corpus_root=root, record_id=rid)
    assert blocks == []
    assert "speakers" not in result["fields"]
    assert "is_diarized" not in result["fields"]
    # …but the container's OWN facts are untouched.
    assert result["fields"]["format"] == "mp4"


def test_the_audio_leaf_types_have_a_drafter(tmp_path):
    """The other half of the move: `audio/aac` and `audio/opus` are the promoted-track leaf
    types, and before 3.11 no drafter was registered for either — so a promoted audio track
    would have transcribed nothing anywhere."""
    from corpus import draft as draft_pkg

    for sid in ("audio/audio_aac", "audio/audio_opus"):
        assert draft_pkg.get_drafter(sid) is not None, sid


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
