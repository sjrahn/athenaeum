"""A QuickTime (.MOV) container attests its track manifest like an MP4 (2026-09-25,
codex-steven R-0039).

QuickTime's SoundDescription shares ISOBMFF's 28-byte AudioSampleEntry prefix but its
`version` field extends it (v1: +16 bytes, v2: +36), and it nests the AAC `esds` inside a
`wave` atom. `corpus.streams` read every sound entry at the ISOBMFF offset, so an iPhone
.MOV's AAC track (version 1) parsed `samplesPerPacket` as a box header, the whole container
failed, and the drafter attested an EMPTY manifest in silence — no `stream_id=` member to
promote, so frame OCR had no video track to land on. ffmpeg's own `.mov` muxer writes the
same layout (`ftypqt`, a version-1 `mp4a`, `wave` → `esds`), so these fixtures reproduce it.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from corpus import paths, records, streams
from corpus.draft import _trackmanifest
from tests.test_track_manifest import _corpus, _ingest, _make_clip, _promote

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg not installed",
)


@pytest.fixture(scope="module")
def mov_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("qt") / "IMG_0001.MOV"
    return _make_clip(out, vcodec="libx264", acodec="aac", extra=["-f", "mov"])


def _mp4a_version_offset(data: bytes) -> int:
    """Byte offset of the `mp4a` sample entry's SoundDescription `version` u16."""
    i = data.find(b"mp4a")
    assert i > 0
    return i + 4 + 8  # past the type, then reserved(6) + data_reference_index(2)


@needs_ffmpeg
def test_the_fixture_is_the_quicktime_layout(mov_clip):
    data = mov_clip.read_bytes()
    assert data[4:12] == b"ftypqt  "
    off = _mp4a_version_offset(data)
    assert struct.unpack(">H", data[off : off + 2])[0] == 1
    assert b"wave" in data and b"esds" in data


@needs_ffmpeg
def test_mov_track_manifest_names_both_tracks(mov_clip):
    embeds, issues = _trackmanifest.attest_track_manifest(mov_clip)
    assert [(e["address"], e["media_type"]) for e in embeds] == [
        ("stream_id=0", "video/h264"),
        ("stream_id=1", "audio/aac"),
    ]
    assert issues == []
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=nb_frames", "-of", "csv=p=0",
         str(mov_clip)],
        capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
    ).stdout.split()
    assert [streams.sample_count(mov_clip, i) for i in (0, 1)] == [int(n) for n in probe]


@needs_ffmpeg
def test_mov_payload_is_the_same_bytes_an_mp4_remux_carries(mov_clip, tmp_path):
    # payload identity (§2): the raw samples do not depend on which ISOBMFF sibling holds them
    mp4 = tmp_path / "remux.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mov_clip), "-c", "copy", str(mp4)],
        check=True, stdin=subprocess.DEVNULL,
    )
    for sid in (0, 1):
        assert streams.payload_blake3(mov_clip, sid) == streams.payload_blake3(mp4, sid)


@needs_ffmpeg
def test_a_mov_record_promotes_its_video_track(mov_clip, tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, mov_clip)
    post = records.load(paths.record_path(root, rid))
    assert records.artifact_block(post)["mime"] == "video/quicktime"
    rows = {e["address"]: e["media_type"] for e in records.iter_embed_blocks(post)}
    assert rows == {"stream_id=0": "video/h264", "stream_id=1": "audio/aac"}
    assert _promote(root, f"corpus://{rid}?stream_id=0") == 0


@needs_ffmpeg
def test_an_unreadable_manifest_is_an_issue_not_a_silent_empty_roster(mov_clip, tmp_path):
    data = bytearray(mov_clip.read_bytes())
    off = _mp4a_version_offset(data)
    data[off : off + 2] = struct.pack(">H", 7)  # no QuickTime sound layout has version 7
    bad = tmp_path / "bad.mov"
    bad.write_bytes(bytes(data))
    embeds, issues = _trackmanifest.attest_track_manifest(bad)
    assert embeds == []
    assert [(i["id"], i["subtype"], i["severity"]) for i in issues] == [
        ("partial-content", "track-manifest-unreadable", "warning")
    ]
    assert "version 7" in issues[0]["fields"]["description"]


def test_a_non_isobmff_file_stays_a_silent_noop(tmp_path):
    ebml = tmp_path / "x.mkv"
    ebml.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)
    assert _trackmanifest.attest_track_manifest(ebml) == ([], [])
    no_moov = tmp_path / "x.mp4"
    no_moov.write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
    assert _trackmanifest.attest_track_manifest(no_moov) == ([], [])
