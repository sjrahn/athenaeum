"""Deterministic ISOBMFF elementary-stream extraction (spec §12.20.1, `corpus.streams`).

Real ffmpeg-produced fixtures exercise the sample-table parsing and per-codec
reframing end to end (h264+aac, h264+opus, and a bonus hevc+aac clip since libx265 is
available); a couple of hand-built minimal box trees exercise the two "never guess"
refusal paths (`stsd entry_count > 1`, non-ISOBMFF containers) without needing ffmpeg
at all. ffmpeg is used here to *generate* and *round-trip-decode* fixtures only — never
inside `corpus.streams` itself.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import blake3
import pytest

from corpus import streams

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None
_HAVE_LIBX265 = False
if _HAVE_FFMPEG:
    _enc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False
    )
    _HAVE_LIBX265 = "libx265" in _enc.stdout

needs_ffmpeg = pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")
needs_libx265 = pytest.mark.skipif(
    not (_HAVE_FFMPEG and _HAVE_LIBX265), reason="ffmpeg/libx265 not installed"
)


# ---------- ffmpeg fixture generation ---------- #


def _make_clip(out: Path, *, vcodec: str, acodec: str, extra: list[str] | None = None) -> Path:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", vcodec, "-pix_fmt", "yuv420p",
        "-c:a", acodec,
        "-shortest",
        *(extra or []),
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


@pytest.fixture(scope="module")
def h264_aac_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("streams") / "h264_aac.mp4"
    return _make_clip(out, vcodec="libx264", acodec="aac")


@pytest.fixture(scope="module")
def h264_opus_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("streams") / "h264_opus.mp4"
    return _make_clip(out, vcodec="libx264", acodec="libopus", extra=["-f", "mp4"])


@pytest.fixture(scope="module")
def hevc_aac_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("streams") / "hevc_aac.mp4"
    extra = ["-tag:v", "hvc1", "-x265-params", "log-level=error"]
    return _make_clip(out, vcodec="libx265", acodec="aac", extra=extra)


def _by_kind(infos: list[streams.StreamInfo], kind: str) -> streams.StreamInfo:
    matches = [s for s in infos if s.kind == kind]
    assert len(matches) == 1, f"expected exactly one {kind!r} stream, got {matches}"
    return matches[0]


def _hash_chunks(chunks) -> str:
    h = blake3.blake3()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


# ---------- probe_streams ---------- #


@needs_ffmpeg
def test_probe_streams_h264_aac(h264_aac_clip):
    infos = streams.probe_streams(h264_aac_clip)
    assert len(infos) == 2
    video = _by_kind(infos, "video")
    audio = _by_kind(infos, "audio")
    assert video.codec == "h264"
    # 3.12: the promoted member is a single-track CONTAINER, so its MIME is the
    # container type for the kind — never the elementary-stream type the codec names.
    assert video.media_type == "video/mp4"
    assert audio.codec == "aac"
    assert audio.media_type == "audio/mp4"
    # index is 0-based track order — the two indices are distinct and both valid.
    assert {video.index, audio.index} == {0, 1}


@needs_ffmpeg
def test_probe_streams_h264_opus(h264_opus_clip):
    infos = streams.probe_streams(h264_opus_clip)
    assert len(infos) == 2
    video = _by_kind(infos, "video")
    audio = _by_kind(infos, "audio")
    assert video.codec == "h264"
    assert video.media_type == "video/mp4"
    assert audio.codec == "opus"
    assert audio.media_type == "audio/mp4"


@needs_libx265
def test_probe_streams_hevc_aac(hevc_aac_clip):
    infos = streams.probe_streams(hevc_aac_clip)
    video = _by_kind(infos, "video")
    audio = _by_kind(infos, "audio")
    assert video.codec == "hevc"
    assert video.media_type == "video/mp4"
    assert audio.codec == "aac"
    assert audio.media_type == "audio/mp4"


# ---------- sample_count: the engine-free oracle ---------- #
#
# 3.12 moved member production out of this module (`corpus.mux` owns the muxer) and left
# it the job of CHECKING that producer — see tests/test_mux.py for the identity path
# itself. What used to live here was a battery pinning the elementary forms: Annex-B
# start codes, synthesized ADTS sync words, the corpus-defined Opus framing. Those forms
# no longer name any promoted record, and the function that built ADTS headers is the
# very one that could not encode `audioObjectType=29`. What this module still owes is a
# sample count that is right and that ffmpeg had no hand in.


@needs_ffmpeg
def test_sample_count_matches_the_container_frame_count(h264_aac_clip):
    """The count is the number the `framing:` stamp carries, so it has to be the real
    one — checked against the container's own reported frame count, which is derived by
    a different reader (ffprobe) from a different table."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1",
         str(h264_aac_clip)],
        check=True, capture_output=True, text=True,
    )
    video = _by_kind(streams.probe_streams(h264_aac_clip), "video")
    assert streams.sample_count(h264_aac_clip, video.index) == int(probe.stdout.strip())


@needs_ffmpeg
def test_sample_count_is_stable_across_runs(h264_aac_clip):
    video = _by_kind(streams.probe_streams(h264_aac_clip), "video")
    counts = {streams.sample_count(h264_aac_clip, video.index) for _ in range(3)}
    assert len(counts) == 1


@needs_ffmpeg
def test_sample_count_distinguishes_the_two_tracks(h264_aac_clip):
    """A count that came back identical for every track would satisfy every other
    assertion in this file while measuring nothing — the degenerate-input trap."""
    infos = streams.probe_streams(h264_aac_clip)
    video = streams.sample_count(h264_aac_clip, _by_kind(infos, "video").index)
    audio = streams.sample_count(h264_aac_clip, _by_kind(infos, "audio").index)
    assert video > 0 and audio > 0
    assert video != audio


@needs_ffmpeg
def test_sample_count_bad_id_raises(h264_aac_clip):
    with pytest.raises(ValueError, match="no such track"):
        streams.sample_count(h264_aac_clip, 99)


@needs_ffmpeg
def test_this_module_no_longer_produces_member_bytes(h264_aac_clip):
    """The supersession, pinned. `extract_stream` produced elementary-stream bytes and is
    gone at 3.12; anything still calling it is calling for a form no record carries."""
    assert not hasattr(streams, "extract_stream")


# ---------- synthetic box tree: stsd entry_count > 1 refusal ---------- #


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, box_type) + payload


def _build_multi_entry_stsd_container() -> bytes:
    """A minimal `ftyp`+`moov`/`trak`/`mdia`/`hdlr`+`minf`/`stbl`/`stsd` tree whose stsd
    declares two sample-description entries — enough to reach and exercise
    `_parse_stsd`'s refusal without needing stsz/stsc/stco (the refusal fires first)."""
    hdlr = _box(b"hdlr", b"\x00" * 4 + b"\x00" * 4 + b"vide" + b"\x00" * 12)
    entry = _box(b"avc1", b"\x00" * 4)  # opaque — never parsed, entry_count check fires first
    stsd = _box(b"stsd", b"\x00" * 4 + struct.pack(">I", 2) + entry + entry)
    stbl = _box(b"stbl", stsd)
    minf = _box(b"minf", stbl)
    mdia = _box(b"mdia", hdlr + minf)
    trak = _box(b"trak", mdia)
    moov = _box(b"moov", trak)
    ftyp = _box(b"ftyp", b"isom" + b"\x00" * 4 + b"isom" + b"mp41")
    return ftyp + moov


def test_stsd_multi_entry_refuses(tmp_path):
    path = tmp_path / "multi_entry.mp4"
    path.write_bytes(_build_multi_entry_stsd_container())
    with pytest.raises(NotImplementedError, match="entry_count"):
        streams.probe_streams(path)
