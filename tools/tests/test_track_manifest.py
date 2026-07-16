"""Track-manifest attestation, promotion, and bare `stream_id=` identity resolution
(spec §12.20 items 2-4) — phase 2 of the media-ops increment.

Self-contained: fixture clips are generated with ffmpeg lavfi inside this file (the
`test_streams.py` / `test_video_muxing.py` pattern); no shared conftest fixtures are added.
Offline tests (chapter-mark mapping, mime sniffing, capture config) run unconditionally;
behavioral tests that shell out to ffmpeg are gated on `ffmpeg` being on PATH, and the hevc
variant additionally on `libx265`.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import blake3
import pytest

from corpus import containment, mime, paths, records, resolver, streams, touches
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus._cli import reattest as reattest_cli
from corpus.capture import _build_ydl_opts
from corpus.draft import _trackmanifest

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")

_HAVE_LIBX265 = False
if _HAVE_FFMPEG:
    _enc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False
    )
    _HAVE_LIBX265 = "libx265" in _enc.stdout
needs_libx265 = pytest.mark.skipif(not _HAVE_LIBX265, reason="libx265 not installed")


# ---------- fixture clip generation (module-scoped: built once) ---------- #


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
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


@pytest.fixture(scope="module")
def h264_aac_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("trackmanifest") / "h264_aac.mp4"
    return _make_clip(out, vcodec="libx264", acodec="aac")


@pytest.fixture(scope="module")
def h264_opus_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("trackmanifest") / "h264_opus.mp4"
    return _make_clip(out, vcodec="libx264", acodec="libopus", extra=["-f", "mp4"])


@pytest.fixture(scope="module")
def hevc_aac_clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("trackmanifest") / "hevc_aac.mp4"
    extra = ["-tag:v", "hvc1", "-x265-params", "log-level=error"]
    return _make_clip(out, vcodec="libx265", acodec="aac", extra=extra)


@pytest.fixture(scope="module")
def h264_subtitle_clip(tmp_path_factory) -> Path:
    """h264 video, no audio, one `mov_text` subtitle track — the "unsupported track" case
    (a real codec `streams.probe_streams` names but this increment's pinned extraction does
    not cover): a text-atom track is a track fact, never an embed (§12.20 item 2)."""
    d = tmp_path_factory.mktemp("trackmanifest")
    srt = d / "sub.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    out = d / "h264_subtitle.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=5",
        "-i", str(srt),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:s", "mov_text",
        "-an",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


# ---------- corpus scaffolding (the test_promote.py pattern) ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    return root


def _ingest(root: Path, src: Path, *, staged_name: str | None = None) -> str:
    """Stage `src` into `root/capture/` and ingest it; return the minted record id."""
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / (staged_name or src.name)
    shutil.copy(src, staged)
    from corpus import hashing

    rid = hashing.hash_file(src)["blake3"]
    assert ingest_cli._ingest_one(root, staged) == 0
    return rid


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


# ---------- offline: chapter marks (§4.3.2.3, §12.20 item 2(b)) ---------- #


def test_chapter_structural_segments_maps_start_and_title():
    marks = _trackmanifest.chapter_structural_segments(
        [{"start": 0.0, "end": 30.0, "title": "Opening"}, {"start": 751.4, "title": "The heist"}]
    )
    assert marks == [
        {"address": "time=00:00:00", "level": 1, "entry": "Opening"},
        {"address": "time=00:12:31", "level": 1, "entry": "The heist"},
    ]


def test_chapter_structural_segments_empty_input():
    assert _trackmanifest.chapter_structural_segments(None) == []
    assert _trackmanifest.chapter_structural_segments([]) == []


def test_chapter_structural_segments_skips_malformed_entries():
    marks = _trackmanifest.chapter_structural_segments(
        [
            {"start": None, "title": "no start"},
            {"start": 1.0, "title": ""},
            {"title": "no start key"},
        ]
    )
    assert marks == []


def test_format_timecode_rounds_and_pads():
    assert _trackmanifest._format_timecode(0) == "00:00:00"
    assert _trackmanifest._format_timecode(59.6) == "00:01:00"
    assert _trackmanifest._format_timecode(3661) == "01:01:01"


# ---------- offline: mime sniffing for the pinned track-extraction forms ---------- #


def test_sniff_head_adts_by_magic():
    # `\xff\xf1` is the fixed prefix our ADTS synthesis always emits (ID=MPEG-4, no CRC).
    assert mime.sniff_head(b"\xff\xf1\x50\x80", None) == "audio/aac"


@pytest.mark.parametrize(
    "head,filename,expected",
    [
        (b"\x00\x00\x00\x01\x67", "stream_id=0.h264", "video/h264"),
        (b"\x00\x00\x00\x01\x40\x01", "stream_id=0.h265", "video/hevc"),
        (b"\x00", "stream_id=1.opus", "audio/opus"),
    ],
)
def test_sniff_head_extension_hint_disambiguates(head, filename, expected):
    assert mime.sniff_head(head, filename) == expected


# ---------- offline: capture config (--embed-chapters equivalent) ---------- #


def test_ytdlp_opts_embed_chapters_by_default():
    opts = _build_ydl_opts(
        outtmpl="out/%(id)s.%(ext)s", include_comments=True, cookiefile=None, ytdlp_opts=None
    )
    pps = opts["postprocessors"]
    assert any(
        pp.get("key") == "FFmpegMetadata" and pp.get("add_chapters") is True for pp in pps
    )


def test_ytdlp_opts_overlay_can_override_postprocessors():
    opts = _build_ydl_opts(
        outtmpl="out/%(id)s.%(ext)s",
        include_comments=True,
        cookiefile=None,
        ytdlp_opts={"postprocessors": []},
    )
    assert opts["postprocessors"] == []


# ---------- offline: bare stream_id= validation (no real file touched) ---------- #


def test_resolve_stream_identity_rejects_multiple_ids(tmp_path):
    fake = tmp_path / "x.mp4"
    fake.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="exactly one track id"):
        resolver._resolve_stream_identity(
            tmp_path, "corpus://deadbeef?stream_id=0&stream_id=1", "deadbeef", fake,
            [("stream_id", "0"), ("stream_id", "1")], regenerate=False,
        )


def test_resolve_stream_identity_rejects_comma_list(tmp_path):
    fake = tmp_path / "x.mp4"
    fake.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="exactly one track id"):
        resolver._resolve_stream_identity(
            tmp_path, "corpus://deadbeef?stream_id=0,1", "deadbeef", fake,
            [("stream_id", "0,1")], regenerate=False,
        )


# ---------- attest_track_manifest() directly (no ingest needed) ---------- #


@needs_ffmpeg
def test_attest_track_manifest_h264_aac(h264_aac_clip):
    embeds, issues = _trackmanifest.attest_track_manifest(h264_aac_clip)
    assert issues == []
    by_media = {e["media_type"]: e for e in embeds}
    assert set(by_media) == {"video/h264", "audio/aac"}
    for media_type, ext in (("video/h264", "h264"), ("audio/aac", "adts")):
        e = by_media[media_type]
        assert e["address"].startswith("stream_id=")
        idx = int(e["address"].removeprefix("stream_id="))
        expected = blake3.blake3()
        length = 0
        for chunk in streams.extract_stream(h264_aac_clip, idx):
            expected.update(chunk)
            length += len(chunk)
        assert e["transport"] == f"blake3:{expected.hexdigest()}"
        assert e["fields"]["bytes"] == length
        assert e["fields"]["filename"] == f"stream_id={idx}.{ext}"


@needs_ffmpeg
def test_attest_track_manifest_double_run_byte_identical(h264_aac_clip):
    """Determinism contract (§12.20 item 1): two attestation passes over the same bytes
    produce byte-identical transports."""
    embeds1, _ = _trackmanifest.attest_track_manifest(h264_aac_clip)
    embeds2, _ = _trackmanifest.attest_track_manifest(h264_aac_clip)

    def _addr(e: dict) -> str:
        return e["address"]

    assert sorted(embeds1, key=_addr) == sorted(embeds2, key=_addr)


@needs_ffmpeg
def test_attest_track_manifest_opus(h264_opus_clip):
    embeds, issues = _trackmanifest.attest_track_manifest(h264_opus_clip)
    assert issues == []
    by_media = {e["media_type"]: e for e in embeds}
    assert "audio/opus" in by_media
    opus = by_media["audio/opus"]
    assert opus["fields"]["filename"].endswith(".opus")


@needs_libx265
def test_attest_track_manifest_hevc(hevc_aac_clip):
    embeds, issues = _trackmanifest.attest_track_manifest(hevc_aac_clip)
    assert issues == []
    by_media = {e["media_type"]: e for e in embeds}
    assert "video/hevc" in by_media
    assert by_media["video/hevc"]["fields"]["filename"].endswith(".h265")


@needs_ffmpeg
def test_attest_track_manifest_unsupported_track_declared_not_embedded(h264_subtitle_clip):
    embeds, issues = _trackmanifest.attest_track_manifest(h264_subtitle_clip)
    media_types = {e["media_type"] for e in embeds}
    assert "video/h264" in media_types
    # The subtitle track is a declared fact, not an embed: no transport hash for it.
    assert len(issues) == 1
    issue = issues[0]
    assert issue["id"] == "partial-content"
    assert issue["subtype"] == "unsupported-track"
    assert issue["severity"] == "info"
    assert issue["fields"]["kind"] == "subtitle"


@needs_ffmpeg
def test_attest_track_manifest_non_isobmff_is_a_noop(tmp_path):
    webm = tmp_path / "x.webm"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=5",
            "-c:v", "libvpx-vp9",
            str(webm),
        ],
        check=True, capture_output=True, text=True,
    )
    embeds, issues = _trackmanifest.attest_track_manifest(webm)
    assert embeds == []
    assert issues == []


# ---------- full ingest round trip ---------- #


@needs_ffmpeg
def test_ingest_h264_aac_record_carries_stream_embeds(h264_aac_clip):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        rid = _ingest(root, h264_aac_clip)
        post = records.load(paths.record_path(root, rid))

        embeds_by_media = {
            e.get("media_type"): e for e in records.iter_embed_blocks(post)
        }
        assert "video/h264" in embeds_by_media
        assert "audio/aac" in embeds_by_media

        # The container's existing artifact facts (ffprobe duration/codec/etc) stay as-is —
        # additive attestation, never a replacement.
        artifact = records.artifact_block(post)
        assert artifact["mime"] == "video/mp4"
        assert "duration" in (artifact.get("fields") or {})


@needs_ffmpeg
def test_reattest_is_idempotent(h264_aac_clip):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        rid = _ingest(root, h264_aac_clip)
        rf = paths.record_path(root, rid)

        first = reattest_cli.reattest_record(rf, root)
        second = reattest_cli.reattest_record(rf, root)
        assert first == second

        # Embeds don't double: exactly one per elementary stream.
        tmp_rf = root / "records" / "reparsed.md"
        tmp_rf.parent.mkdir(parents=True, exist_ok=True)
        tmp_rf.write_text(first, encoding="utf-8")
        loaded = records.load(tmp_rf)
        stream_embeds = [
            e for e in records.iter_embed_blocks(loaded)
            if str(e.get("address") or "").startswith("stream_id=")
        ]
        assert len(stream_embeds) == 2  # video + audio, no duplicates


@needs_ffmpeg
def test_promote_stream_mints_record_with_lineage(h264_aac_clip):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        rid = _ingest(root, h264_aac_clip)
        post = records.load(paths.record_path(root, rid))
        video_embed = next(
            e for e in records.iter_embed_blocks(post) if e.get("media_type") == "video/h264"
        )
        stream_id = str(video_embed["address"]).removeprefix("stream_id=")
        uri = f"corpus://{rid}?stream_id={stream_id}"

        assert _promote(root, uri) == 0

        expected_pid = str(video_embed["transport"]).removeprefix("blake3:")
        promoted_post = records.load(paths.record_path(root, expected_pid))
        assert promoted_post.metadata["id"] == expected_pid
        assert records.derived_state(promoted_post) == "proxy"
        assert records.media_type_for(promoted_post) == "video/h264"
        origins = list(records.iter_origin_blocks(promoted_post))
        assert origins[0]["fields"]["uri"] == uri
        assert touches.touch_list(promoted_post) == [touches.script_identifier("promote")]

        # Resolved bytes stream through the container and blake3-match the transport.
        resolved = containment.ensure_local_bytes(root, expected_pid, "h264")
        digest = blake3.blake3(resolved.read_bytes()).hexdigest()
        assert digest == expected_pid


@needs_ffmpeg
def test_promote_opus_stream_mime_via_extension_hint(h264_opus_clip):
    """Opus has no reliable magic bytes at all — this exercises the extension-hint MIME
    resolution path (`fields.filename`) end to end through the real promote flow."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        rid = _ingest(root, h264_opus_clip)
        post = records.load(paths.record_path(root, rid))
        opus_embed = next(
            e for e in records.iter_embed_blocks(post) if e.get("media_type") == "audio/opus"
        )
        stream_id = str(opus_embed["address"]).removeprefix("stream_id=")
        uri = f"corpus://{rid}?stream_id={stream_id}"
        assert _promote(root, uri) == 0

        expected_pid = str(opus_embed["transport"]).removeprefix("blake3:")
        promoted_post = records.load(paths.record_path(root, expected_pid))
        assert records.media_type_for(promoted_post) == "audio/opus"


# ---------- bare stream_id= identity resolution ---------- #


@needs_ffmpeg
def test_bare_stream_id_resolves_to_pinned_identity_bytes(h264_aac_clip):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        rid = _ingest(root, h264_aac_clip)
        post = records.load(paths.record_path(root, rid))
        video_embed = next(
            e for e in records.iter_embed_blocks(post) if e.get("media_type") == "video/h264"
        )
        stream_id = str(video_embed["address"]).removeprefix("stream_id=")

        out = resolver.resolve(f"corpus://{rid}?stream_id={stream_id}", root)
        resolved_bytes = out.read_bytes()

        direct = b"".join(streams.extract_stream(h264_aac_clip, int(stream_id)))
        assert resolved_bytes == direct
        assert out.suffix == ".h264"

        # A second resolve is a cache hit — same path, no re-extraction needed.
        out2 = resolver.resolve(f"corpus://{rid}?stream_id={stream_id}", root)
        assert out2 == out


@needs_ffmpeg
def test_bare_stream_id_does_not_return_raw_container(h264_aac_clip):
    """Regression guard for the bug this item fixes: before §12.20 item 4, a bare
    `stream_id=` fell through the generic no-op branch and returned the whole container."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        rid = _ingest(root, h264_aac_clip)
        post = records.load(paths.record_path(root, rid))
        video_embed = next(
            e for e in records.iter_embed_blocks(post) if e.get("media_type") == "video/h264"
        )
        stream_id = str(video_embed["address"]).removeprefix("stream_id=")
        out = resolver.resolve(f"corpus://{rid}?stream_id={stream_id}", root)
        assert out.stat().st_size != h264_aac_clip.stat().st_size
        assert out.read_bytes() != h264_aac_clip.read_bytes()


# ---------- chapters → structural segments, at ingest ---------- #


@needs_ffmpeg
def test_sidecar_chapters_land_as_structural_segments(h264_aac_clip):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _corpus(Path(td))
        cap = root / "capture"
        cap.mkdir(parents=True)
        staged = cap / "clip.mp4"
        shutil.copy(h264_aac_clip, staged)
        (cap / "clip.info.json").write_text(
            '{"chapters": ['
            '{"start_time": 0.0, "end_time": 0.6, "title": "Intro"},'
            '{"start_time": 0.6, "title": "Outro"}'
            "]}",
            encoding="utf-8",
        )
        from corpus import hashing

        rid = hashing.hash_file(h264_aac_clip)["blake3"]
        assert ingest_cli._ingest_one(root, staged) == 0

        post = records.load(paths.record_path(root, rid))
        from corpus import segments as segs_mod

        blocks = segs_mod.iter_blocks(post.content or "")
        marks = [
            b for b in blocks
            if isinstance(b, segs_mod.Segment) and b.is_structural
        ]
        assert [(m.address, m.entry) for m in marks] == [
            ("time=00:00:00", "Intro"),
            ("time=00:00:01", "Outro"),
        ]

        # The chapters sidecar is one-shot (consumed + deleted at ingest, like `ytdlp_*`
        # fields), so re-attest can never re-derive it — the marks must PERSIST rather than
        # being stripped-and-regenerated (a strip-then-regenerate design would silently lose
        # them, since there is nothing left to regenerate from). Two reattest passes back to
        # back are the correct idempotency check: comparing against the raw post-ingest text
        # is not, because the transcription-unavailable issue's `reason:` text legitimately
        # differs between ingest time (record not yet on disk) and reattest time (configured-
        # adapter check) — a pre-existing characteristic unrelated to this increment.
        rf = paths.record_path(root, rid)
        first_reattest = reattest_cli.reattest_record(rf, root)
        rf.write_text(first_reattest, encoding="utf-8")
        second_reattest = reattest_cli.reattest_record(rf, root)
        assert second_reattest == first_reattest

        reloaded = records.load(rf)
        reloaded_marks = [
            b for b in segs_mod.iter_blocks(reloaded.content or "")
            if isinstance(b, segs_mod.Segment) and b.is_structural
        ]
        assert [(m.address, m.entry) for m in reloaded_marks] == [
            ("time=00:00:00", "Intro"),
            ("time=00:00:01", "Outro"),
        ]
