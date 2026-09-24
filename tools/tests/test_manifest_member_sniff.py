"""An archive member whose extension the platform table doesn't know is typed by its magic
bytes (2026-09-24): an osxphotos `.DNG` is TIFF, so its roster row says `image/tiff` and the
contact sheet (which selects image/video members by media type) tiles it."""

from __future__ import annotations

import io
import zipfile

from PIL import Image

from corpus import recordbuild, schemas
from corpus.draft import _manifest, zip_manifest
from tests.test_zip_manifest import _MIME, _make_corpus


def _tiff() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 6), (1, 2, 3)).save(buf, format="TIFF")
    return buf.getvalue()


def test_unknown_extension_binary_is_sniffed():
    assert _manifest.media_type("IMG_0001.DNG", False, _tiff()) == "image/tiff"


def test_known_extension_wins_and_opaque_stays_octet_stream():
    assert _manifest.media_type("a.png", False, b"not a png") == "image/png"
    assert _manifest.media_type("blob.bin", False, b"\x00\x01\x02opaque") == (
        "application/octet-stream"
    )
    assert _manifest.media_type("blob.zzqq", False, None) == "application/octet-stream"


def test_zip_roster_types_a_dng_member_as_tiff(tmp_path):
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("IMG_0001.DNG", _tiff())
        zf.writestr("data.zzqq", b"\x00\x01opaque")
    root = _make_corpus(tmp_path)
    schema = schemas.load_mime_schema(root, _MIME)
    build = recordbuild.begin({}, root)
    result = zip_manifest.draft(z, build=build, corpus_root=root, mime_schema=schema)
    embeds = {e["address"]: e["media_type"] for e in result["embeds"]}
    assert embeds["path=IMG_0001.DNG"] == "image/tiff"
    assert embeds["path=data.zzqq"] == "application/octet-stream"
