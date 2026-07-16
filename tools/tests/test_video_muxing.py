"""The muxing contract (§6.2) — `time_range=`, `cut=`, `format=`, `scenes=`, and
`stream_id=` composition — plus its engine-versioned caching (§6.3/§6.4).

Self-contained: fixture clips are generated with ffmpeg lavfi inside this file (the
`test_video.py` pattern); no shared conftest fixtures are added. Offline tests (parsing,
validation, engine-label parsing) run unconditionally; behavioral tests that shell out to
ffmpeg are gated on `ffmpeg`/`ffprobe` being on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import frontmatter
import pytest
from PIL import Image

from corpus import functional_uri as furi
from corpus import paths, records, resolver
from corpus.transforms import image as image_tf
from corpus.transforms import video as video_tf

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# ---------- fixture clip generation (module-scoped: built once) ---------- #


def _ffmpeg(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, Path]:
    if not _HAVE_FFMPEG:
        return {}
    d = tmp_path_factory.mktemp("muxing-clips")

    # Sparse-keyframe video+audio clip (one keyframe over 6s @ 10fps, `-g 600`) so
    # `cut=copy`'s keyframe snap is observable against `cut=precise`'s frame-accurate cut.
    sparse = d / "sparse.mp4"
    _ffmpeg([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=6:size=160x120:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-g", "600", "-shortest", str(sparse),
    ])

    # Two video streams, no declared primary — the ambiguity case for default-member
    # resolution, and the target of explicit `stream_id=` selection.
    twostream = d / "twostream.mp4"
    _ffmpeg([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=5",
        "-f", "lavfi", "-i", "testsrc2=duration=2:size=160x120:rate=5",
        "-map", "0:v", "-map", "1:v", "-shortest", str(twostream),
    ])

    # Two-scene clip — a hard color cut at the 2s join — for `scenes=`.
    scenes_clip = d / "scenes.mp4"
    _ffmpeg([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:size=160x120:duration=2:rate=10",
        "-f", "lavfi", "-i", "color=c=blue:size=160x120:duration=2:rate=10",
        "-filter_complex", "concat=n=2:v=1:a=0", str(scenes_clip),
    ])

    # Audio-only container (mp3) — `time_range=`/`format=` on the "audio" working kind.
    audio_only = d / "audio.mp3"
    _ffmpeg([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:a", "libmp3lame", str(audio_only),
    ])

    return {"sparse": sparse, "twostream": twostream, "scenes": scenes_clip, "audio": audio_only}


# ---------- record scaffolding ---------- #


def _make_record(root: Path, rid: str, src: Path, *, mime: str) -> Path:
    (root / "records").mkdir(parents=True, exist_ok=True)
    (root / "schema").mkdir(exist_ok=True)
    ext = src.suffix.lstrip(".")
    art = paths.artifact_path(root, rid, ext)
    paths.ensure_parent(art)
    art.write_bytes(src.read_bytes())
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime=mime, fields={"title": "clip"})
    records.append_origin_block(
        post, uri=f"https://e.com/{rid}.{ext}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))
    return art


def _ffprobe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


def _decodes_cleanly(path: Path) -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode == 0


# ---------- offline unit tests (no ffmpeg invoked) ---------- #


def test_parse_time_ranges_single():
    assert video_tf._parse_time_ranges("12:04-12:09") == [(724.0, 729.0)]


def test_parse_time_ranges_multi():
    assert video_tf._parse_time_ranges("1-3,5-7") == [(1.0, 3.0), (5.0, 7.0)]


def test_parse_time_ranges_rejects_end_before_start():
    with pytest.raises(ValueError, match="end precedes start"):
        video_tf._parse_time_ranges("5-2")


def test_parse_time_ranges_rejects_missing_dash():
    with pytest.raises(ValueError, match="expects"):
        video_tf._parse_time_ranges("120")


def test_time_range_requires_value():
    with pytest.raises(ValueError):
        video_tf.time_range_video(Path("/v.mp4"), None, {})


def test_format_requires_value():
    with pytest.raises(ValueError):
        video_tf.format_video(Path("/v.mp4"), None, {})


def test_format_rejects_unsupported_token():
    with pytest.raises(ValueError, match="not supported"):
        video_tf.format_video(Path("/v.mp4"), "avi", {})


def test_format_audio_source_rejects_gif():
    # audio→gif is atom-incompatible — the spec's audio→png hard-error example, generalized:
    # an audio source has no visual content to animate.
    with pytest.raises(ValueError, match="atom-incompatible"):
        video_tf.format_audio(Path("/a.mp3"), "gif", {})


def test_scenes_requires_value():
    with pytest.raises(ValueError):
        video_tf.scenes(Path("/v.mp4"), None, {})


def test_scenes_rejects_out_of_range_threshold():
    with pytest.raises(ValueError, match=r"\(0.0, 1.0\)"):
        video_tf.scenes(Path("/v.mp4"), "1.5", {})


def test_cut_mode_rejects_bad_value():
    with pytest.raises(ValueError, match="'precise' or 'copy'"):
        video_tf._cut_one(Path("/v.mp4"), (0.0, 1.0), "fast", [], "mp4")


def test_format_png_identity_on_image_kind():
    img = Image.new("RGB", (2, 2))
    assert image_tf.format_image(img, "png", {}) is img


def test_format_rejects_non_png_on_image_kind():
    img = Image.new("RGB", (2, 2))
    with pytest.raises(ValueError, match="not supported on an image"):
        image_tf.format_image(img, "gif", {})


def test_ffmpeg_engine_label_parses_version(monkeypatch):
    """Engine-label parsing, unit-tested without needing a second real ffmpeg install:
    stub `subprocess.run`'s output and confirm the label — and hence the resolver's cache
    key for `time_range=`/`format=`/`scenes=` (§6.3/§6.4) — tracks it."""
    video_tf.ffmpeg_engine_label.cache_clear()

    class _FakeProc:
        stdout = "ffmpeg version 6.1.1-fake Copyright (c) 2000-2026 the FFmpeg developers\n"

    monkeypatch.setattr(video_tf.subprocess, "run", lambda *a, **k: _FakeProc())
    try:
        assert video_tf.ffmpeg_engine_label() == "ffmpeg@6.1.1-fake"
    finally:
        video_tf.ffmpeg_engine_label.cache_clear()


def test_ffmpeg_engine_label_falls_back_when_unavailable(monkeypatch):
    video_tf.ffmpeg_engine_label.cache_clear()

    def _raise(*a, **k):
        raise OSError("no ffmpeg on PATH")

    monkeypatch.setattr(video_tf.subprocess, "run", _raise)
    try:
        assert video_tf.ffmpeg_engine_label() == "ffmpeg@unknown"
    finally:
        video_tf.ffmpeg_engine_label.cache_clear()


# ---------- behavioral tests (real ffmpeg; gated) ---------- #


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_cut_copy_and_precise_both_decodable_and_differ(tmp_path, clips):
    root = tmp_path / "c"
    rid = "a1" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    precise = resolver.resolve(f"corpus://{rid}?time_range=2-4", root)
    copy_ = resolver.resolve(f"corpus://{rid}?time_range=2-4&cut=copy", root)

    assert _decodes_cleanly(precise)
    assert _decodes_cleanly(copy_)

    precise_dur = _ffprobe_duration(precise)
    copy_dur = _ffprobe_duration(copy_)
    # precise (default; re-encode) lands close to the requested 2s span.
    assert abs(precise_dur - 2.0) < 0.3
    # copy (stream copy) can only snap to the nearest preceding keyframe — the fixture's
    # single keyframe sits at t=0, so the copy cut's bounds widen versus the precise cut
    # (§6.2 "disclosed" — never silently drifts, but is allowed to widen).
    assert copy_dur >= precise_dur


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_cut_default_is_precise(tmp_path, clips):
    """`cut=` defaults to `precise` when omitted (§6.2)."""
    root = tmp_path / "c"
    rid = "a2" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    default_ = resolver.resolve(f"corpus://{rid}?time_range=2-4", root, regenerate=True)
    explicit = resolver.resolve(
        f"corpus://{rid}?time_range=2-4&cut=precise", root, regenerate=True
    )
    assert abs(_ffprobe_duration(default_) - _ffprobe_duration(explicit)) < 0.05


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_multi_cut_concatenates_in_order(tmp_path, clips):
    root = tmp_path / "c"
    rid = "a3" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    out = resolver.resolve(f"corpus://{rid}?time_range=0-1,2-3", root)
    assert _decodes_cleanly(out)
    # Two one-second spans concatenated ~= 2 seconds.
    assert abs(_ffprobe_duration(out) - 2.0) < 0.3


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_time_range_on_audio_only_container(tmp_path, clips):
    root = tmp_path / "c"
    rid = "a4" * 32
    _make_record(root, rid, clips["audio"], mime="audio/mpeg")

    out = resolver.resolve(f"corpus://{rid}?time_range=1-3", root)
    assert _decodes_cleanly(out)
    assert abs(_ffprobe_duration(out) - 2.0) < 0.3


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_format_gif_yields_gif_magic_bytes(tmp_path, clips):
    root = tmp_path / "c"
    rid = "b1" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    out = resolver.resolve(f"corpus://{rid}?format=gif", root)
    assert out.read_bytes()[:3] == b"GIF"


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_format_composes_after_cut(tmp_path, clips):
    """`time_range=…&format=gif` — cut, then convert (§6.2 canonical order)."""
    root = tmp_path / "c"
    rid = "b2" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    out = resolver.resolve(f"corpus://{rid}?time_range=1-3&format=gif", root)
    assert out.read_bytes()[:3] == b"GIF"


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_format_png_after_frame(tmp_path, clips):
    """`frame=<t>&format=png` — the frame-context reading of `format=` (§6.2 "png (frame
    contexts aside)"), composing through the image working kind rather than muxing."""
    root = tmp_path / "c"
    rid = "b4" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    out = resolver.resolve(f"corpus://{rid}?frame=1&format=png", root)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_format_audio_token_yields_decodable_audio(tmp_path, clips):
    root = tmp_path / "c"
    rid = "b3" * 32
    _make_record(root, rid, clips["audio"], mime="audio/mpeg")

    out = resolver.resolve(f"corpus://{rid}?format=wav", root)
    assert out.suffix == ".wav"
    assert _decodes_cleanly(out)


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_scenes_finds_boundary_near_join(tmp_path, clips):
    root = tmp_path / "c"
    rid = "c1" * 32
    _make_record(root, rid, clips["scenes"], mime="video/mp4")

    out = resolver.resolve(f"corpus://{rid}?scenes=0.3", root)
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    timestamps = [float(ln) for ln in lines]
    assert len(timestamps) >= 1
    assert any(abs(t - 2.0) < 0.5 for t in timestamps)


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_stream_id_default_ambiguous_video_streams_fails(tmp_path, clips):
    """Two video streams, no declared primary — default-member resolution fails stating
    the ambiguity rather than guessing (§6.2)."""
    root = tmp_path / "c"
    rid = "d1" * 32
    _make_record(root, rid, clips["twostream"], mime="video/mp4")

    with pytest.raises(Exception, match="ambiguous"):
        resolver.resolve(f"corpus://{rid}?time_range=0-1", root)


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_stream_id_disambiguates_and_composes_with_time_range(tmp_path, clips):
    root = tmp_path / "c"
    rid = "d2" * 32
    _make_record(root, rid, clips["twostream"], mime="video/mp4")

    out = resolver.resolve(f"corpus://{rid}?stream_id=0&time_range=0-1", root)
    assert _decodes_cleanly(out)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=index", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert len(json.loads(probe.stdout)["streams"]) == 1  # only the selected stream rode


@pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_cache_key_includes_engine_version(tmp_path, monkeypatch, clips):
    """The muxing ops' cache key folds in the ffmpeg engine label exactly like `transcribe`
    folds in its adapter's `engine` (§6.3/§6.4) — verified by swapping the (monkeypatched)
    label between two resolves of the SAME canonical URI and observing two distinct cache
    files, without needing a second real ffmpeg install."""
    root = tmp_path / "c"
    rid = "e1" * 32
    _make_record(root, rid, clips["sparse"], mime="video/mp4")

    video_tf.ffmpeg_engine_label.cache_clear()
    monkeypatch.setattr(video_tf, "ffmpeg_engine_label", lambda: "ffmpeg@fake-1")
    out1 = resolver.resolve(f"corpus://{rid}?time_range=0-1", root)
    sidecar1 = json.loads(furi.cache_sidecar_path(out1).read_text())

    monkeypatch.setattr(video_tf, "ffmpeg_engine_label", lambda: "ffmpeg@fake-2")
    out2 = resolver.resolve(f"corpus://{rid}?time_range=0-1", root)
    sidecar2 = json.loads(furi.cache_sidecar_path(out2).read_text())

    assert out1 != out2  # distinct engine label -> distinct cache key/path
    assert sidecar1["engine"] == "ffmpeg@fake-1"
    assert sidecar2["engine"] == "ffmpeg@fake-2"
