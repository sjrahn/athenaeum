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
    assert video.media_type == "video/h264"
    assert audio.codec == "aac"
    assert audio.media_type == "audio/aac"
    # index is 0-based track order — the two indices are distinct and both valid.
    assert {video.index, audio.index} == {0, 1}


@needs_ffmpeg
def test_probe_streams_h264_opus(h264_opus_clip):
    infos = streams.probe_streams(h264_opus_clip)
    assert len(infos) == 2
    video = _by_kind(infos, "video")
    audio = _by_kind(infos, "audio")
    assert video.codec == "h264"
    assert video.media_type == "video/h264"
    assert audio.codec == "opus"
    assert audio.media_type == "audio/opus"


@needs_libx265
def test_probe_streams_hevc_aac(hevc_aac_clip):
    infos = streams.probe_streams(hevc_aac_clip)
    video = _by_kind(infos, "video")
    audio = _by_kind(infos, "audio")
    assert video.codec == "hevc"
    assert video.media_type == "video/hevc"
    assert audio.codec == "aac"
    assert audio.media_type == "audio/aac"


# ---------- double-run byte identity ---------- #


@needs_ffmpeg
def test_extract_stream_double_run_identical_h264(h264_aac_clip):
    video = _by_kind(streams.probe_streams(h264_aac_clip), "video")
    first = _hash_chunks(streams.extract_stream(h264_aac_clip, video.index))
    second = _hash_chunks(streams.extract_stream(h264_aac_clip, video.index))
    assert first == second


@needs_ffmpeg
def test_extract_stream_double_run_identical_aac(h264_aac_clip):
    audio = _by_kind(streams.probe_streams(h264_aac_clip), "audio")
    first = _hash_chunks(streams.extract_stream(h264_aac_clip, audio.index))
    second = _hash_chunks(streams.extract_stream(h264_aac_clip, audio.index))
    assert first == second


@needs_ffmpeg
def test_extract_stream_double_run_identical_opus(h264_opus_clip):
    audio = _by_kind(streams.probe_streams(h264_opus_clip), "audio")
    first = _hash_chunks(streams.extract_stream(h264_opus_clip, audio.index))
    second = _hash_chunks(streams.extract_stream(h264_opus_clip, audio.index))
    assert first == second


@needs_libx265
def test_extract_stream_double_run_identical_hevc(hevc_aac_clip):
    video = _by_kind(streams.probe_streams(hevc_aac_clip), "video")
    first = _hash_chunks(streams.extract_stream(hevc_aac_clip, video.index))
    second = _hash_chunks(streams.extract_stream(hevc_aac_clip, video.index))
    assert first == second


# ---------- per-codec framing shape ---------- #


@needs_ffmpeg
def test_extract_h264_starts_with_start_code_and_sps(h264_aac_clip):
    video = _by_kind(streams.probe_streams(h264_aac_clip), "video")
    chunks = list(streams.extract_stream(h264_aac_clip, video.index))
    assert chunks[0].startswith(b"\x00\x00\x00\x01")
    nal_type = chunks[0][4] & 0x1F
    assert nal_type == 7, "first NAL after the start code must be an SPS (nal_unit_type 7)"


@needs_ffmpeg
def test_extract_aac_starts_with_adts_sync(h264_aac_clip):
    audio = _by_kind(streams.probe_streams(h264_aac_clip), "audio")
    chunks = list(streams.extract_stream(h264_aac_clip, audio.index))
    assert len(chunks) > 0
    first = chunks[0]
    assert first[0] == 0xFF
    assert (first[1] & 0xF0) == 0xF0, "ADTS syncword is 0xFFF (12 bits)"


@needs_ffmpeg
def test_extract_opus_framing_walks_exactly(h264_opus_clip):
    audio = _by_kind(streams.probe_streams(h264_opus_clip), "audio")
    chunks = list(streams.extract_stream(h264_opus_clip, audio.index))
    assert len(chunks) > 1  # dOps payload + at least one packet
    dops_len = len(chunks[0])
    assert dops_len >= 11  # Version+ChannelCount+PreSkip+SampleRate+Gain+MappingFamily

    blob = b"".join(chunks)
    pos = dops_len
    packet_count = 0
    while pos < len(blob):
        (packet_len,) = struct.unpack(">I", blob[pos : pos + 4])
        pos += 4 + packet_len
        packet_count += 1
    assert pos == len(blob), "walking the length prefixes must consume the byte stream exactly"
    assert packet_count == len(chunks) - 1


# ---------- round-trip sanity via ffmpeg (conventional forms only) ---------- #


@needs_ffmpeg
def test_extract_h264_roundtrip_decodes(tmp_path, h264_aac_clip):
    video = _by_kind(streams.probe_streams(h264_aac_clip), "video")
    out = tmp_path / "extracted.h264"
    out.write_bytes(b"".join(streams.extract_stream(h264_aac_clip, video.index)))
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "h264", "-i", str(out), "-f", "null", "-"],
    )
    assert result.returncode == 0


@needs_ffmpeg
def test_extract_aac_roundtrip_decodes(tmp_path, h264_aac_clip):
    audio = _by_kind(streams.probe_streams(h264_aac_clip), "audio")
    out = tmp_path / "extracted.aac"
    out.write_bytes(b"".join(streams.extract_stream(h264_aac_clip, audio.index)))
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "aac", "-i", str(out), "-f", "null", "-"],
    )
    assert result.returncode == 0


# ---------- error paths: never guess ---------- #


@needs_ffmpeg
def test_extract_stream_bad_id_raises(h264_aac_clip):
    with pytest.raises(ValueError, match="no such track"):
        list(streams.extract_stream(h264_aac_clip, 99))


def test_probe_streams_non_isobmff_container_raises(tmp_path):
    fake_mkv = tmp_path / "fake.mkv"
    fake_mkv.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 32)
    with pytest.raises(ValueError, match="Matroska"):
        streams.probe_streams(fake_mkv)


def test_probe_streams_no_moov_raises(tmp_path):
    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(b"\x00\x00\x00\x08free" + b"\x00" * 16)
    with pytest.raises(ValueError, match="moov"):
        streams.probe_streams(garbage)


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
