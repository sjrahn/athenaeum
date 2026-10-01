"""A Sony ARW is its own type (v51, owner ruling 2026-10-01): TIFF by magic, but its IFD0
is an old-style-JPEG thumbnail and its picture undeveloped sensor data, so it is typed
`image/x-sony-arw` by extension and drafted from the TIFF directory entries alone — never
decoded — into a terminal record. A DNG (and any bare TIFF) stays `image/tiff`."""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

import pytest

from corpus import contact_sheet as cs
from corpus import lint, mime, paths, records, resolver, schemas, segments
from corpus._cli import ingest as ingest_cli

_REAL = Path("/mnt/slow/staging/camera/sd-57A4-DE38-2026-10-01/card/DCIM/10051104/DSC08130.ARW")


def _ifd(entries: list[tuple[int, int, int, bytes]], at: int) -> tuple[bytes, bytes]:
    """One little-endian IFD at offset `at`: (directory bytes, overflow value bytes that
    follow it). Each entry is (tag, type, count, raw value bytes)."""
    n = len(entries)
    data_at = at + 2 + 12 * n + 4
    head, tail = struct.pack("<H", n), b""
    for tag, typ, count, raw in sorted(entries):
        if len(raw) <= 4:
            head += struct.pack("<HHI", tag, typ, count) + raw.ljust(4, b"\0")
        else:
            head += struct.pack("<HHII", tag, typ, count, data_at + len(tail))
            tail += raw + (b"\0" if len(raw) % 2 else b"")
    return head + struct.pack("<I", 0), tail


def _ascii(tag: int, text: str) -> tuple[int, int, int, bytes]:
    raw = text.encode() + b"\0"
    return (tag, 2, len(raw), raw)


def _long(tag: int, value: int) -> tuple[int, int, int, bytes]:
    return (tag, 4, 1, struct.pack("<I", value))


def _arw() -> bytes:
    """A minimal ARW-shaped TIFF: IFD0 an old-JPEG (compression 6) thumbnail with
    Make/Model/DateTime, a SubIFD holding 14-bit raw dimensions, an EXIF IFD with the
    picture size, capture time and lens. No pixel data a decoder could open."""
    exif_at, sub_at = 400, 600
    ifd0, ifd0_tail = _ifd([
        (259, 3, 1, struct.pack("<H", 6)),
        _ascii(271, "SONY"), _ascii(272, "ILCE-7CR"), _ascii(306, "2025:11:04 10:32:12"),
        _long(330, sub_at), _long(34665, exif_at),
    ], 8)
    exif, exif_tail = _ifd([
        _ascii(36867, "2025:11:04 10:31:59"), _long(40962, 9504), _long(40963, 6336),
        _ascii(42036, "FE 20-70mm F4 G"),
    ], exif_at)
    sub, _ = _ifd([_long(256, 9600), _long(257, 6376), (259, 3, 1, struct.pack("<H", 1))], sub_at)
    buf = bytearray(b"II*\0" + struct.pack("<I", 8))
    buf += ifd0 + ifd0_tail
    assert len(buf) <= exif_at
    buf += b"\0" * (exif_at - len(buf)) + exif + exif_tail
    assert len(buf) <= sub_at
    buf += b"\0" * (sub_at - len(buf)) + sub
    return bytes(buf)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def test_arw_types_apart_from_tiff_by_extension_only(tmp_path: Path):
    data = _arw()
    assert mime.sniff_head(data[:512], "DCIM/100MSDCF/DSC08130.ARW") == "image/x-sony-arw"
    assert mime.sniff_head(data[:512], "scan.tif") == "image/tiff"
    assert mime.sniff_head(data[:512]) == "image/tiff"  # bytes alone never refine
    for name, want in (("DSC08130.ARW", "image/x-sony-arw"), ("a.dng", "image/tiff")):
        (tmp_path / name).write_bytes(data)
        assert mime.detect(tmp_path / name) == want
    assert mime.extension_for("image/x-sony-arw") == "arw"


def test_arw_schema_is_terminal_with_no_pipeline(tmp_path: Path):
    root = _corpus(tmp_path)
    s = schemas.load_mime_schema(root, "image/x-sony-arw")
    assert s["form"]["id"] == "passthrough"
    assert s["address_scheme"] == []
    assert s["extended_fields"]["width"]["required"] is False
    assert resolver.working_kind_for(root, "image/x-sony-arw") is None


def test_arw_ingests_from_directory_entries_never_decoded(tmp_path: Path):
    root = _corpus(tmp_path)
    cap = root / "capture"
    cap.mkdir()
    src = cap / "DSC08130.ARW"
    src.write_bytes(_arw())
    assert ingest_cli._ingest_one(root, src) == 0

    rid = next(p.stem for p in (root / "records").rglob("*.md"))
    post = records.load(paths.record_path(root, rid))
    assert records.media_type_for(post) == "image/x-sony-arw"
    fields = (records.artifact_block(post) or {}).get("fields") or {}
    assert fields["format"] == "ARW"
    assert (fields["width"], fields["height"]) == (9504, 6336)  # the declared picture size
    assert fields["exif_make"] == "SONY" and fields["exif_model"] == "ILCE-7CR"
    assert fields["exif_datetime"] == "2025:11:04 10:31:59"  # DateTimeOriginal wins
    assert fields["exif_lens"] == "FE 20-70mm F4 G"
    assert not list(segments.leaf_segments(segments.iter_blocks(post.content or "")))
    errors = [
        f for f in lint.lint(post, segments.iter_blocks(post.content or ""), root)
        if f.severity == "error"
    ]
    assert errors == []
    with pytest.raises(NotImplementedError):
        resolver.resolve(f"corpus://{rid}?bbox=0,0,1,1", root)


def test_contact_sheet_passes_an_arw_over_as_other():
    members = [
        {"address": "path=DSC08130.ARW", "media_type": "image/x-sony-arw"},
        {"address": "path=DSC08130.HIF", "media_type": "image/heic"},
    ]
    chosen, skipped = cs.select(members)
    assert [m["address"] for m in chosen] == ["path=DSC08130.HIF"]
    assert skipped == {"other": 1}


@pytest.mark.skipif(not _REAL.exists(), reason="needs the R-0060 SD-card dump")
def test_a_real_arw_drafts(tmp_path: Path):
    root = _corpus(tmp_path)
    cap = root / "capture"
    cap.mkdir()
    shutil.copy(_REAL, cap / _REAL.name)
    assert ingest_cli._ingest_one(root, cap / _REAL.name) == 0
    rid = next(p.stem for p in (root / "records").rglob("*.md"))
    fields = (records.artifact_block(records.load(paths.record_path(root, rid))) or {})["fields"]
    assert fields["exif_model"] == "ILCE-7CR"
    assert (fields["width"], fields["height"]) == (9504, 6336)
