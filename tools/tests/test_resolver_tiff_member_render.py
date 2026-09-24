"""A TIFF container member — and so a DNG, which IS TIFF — renders to a viewable PNG
through the image ops it already has (2026-09-24, the R-0035 photo-library fan-out).

`image/tiff` was sniffed (#149) but had no mime schema, so a DNG member fell to working
kind `bytes` and every image op was refused ("transform 'auto_orient' not applicable to
working kind 'bytes'"). The `image_tiff` schema gives it the image pipeline. Pillow reads
IFD0, which for an iPhone ProRAW DNG is the producer's full-size RGB rendering
(ath-steven IMG_0124.DNG: 3024x4032) — the raw sensor data in its SubIFDs is never
developed here.

The drafter's `frame_count` walks the TOP-LEVEL IFD chain structurally: a multi-page TIFF
counts its pages, a DNG counts 1 (its raw + reduced previews live in SubIFDs, which are
alternate representations of one image, not pages).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import frontmatter
from PIL import Image

from corpus import functional_uri as furi
from corpus import hashing, paths, records, resolver, schemas
from corpus.draft.image import _tiff_frame_count
from corpus.store import LocalArtifactStore


def _tiff(size: tuple[int, int] = (16, 12), pages: int = 1) -> bytes:
    buf = io.BytesIO()
    frames = [Image.new("RGB", size, (10 * i, 20, 30)) for i in range(pages)]
    frames[0].save(buf, format="TIFF", save_all=pages > 1, append_images=frames[1:])
    return buf.getvalue()


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _stage_zip(root: Path, members: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    src = root.parent / "export.zip"
    src.write_bytes(buf.getvalue())
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, "zip", src)
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_origin_block(
        post,
        snapshot="2026-09-24T00:00:00Z",
        fields={"filename": "export.zip", "source_modified": ""},
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_tiff_schema_gives_the_image_working_kind(tmp_path):
    root = _corpus(tmp_path)
    assert resolver.working_kind_for(root, "image/tiff") == "image"


def test_bare_dng_member_is_the_raw_bytes(tmp_path):
    root = _corpus(tmp_path)
    tif = _tiff()
    rid = _stage_zip(root, {"IMG_0124.DNG": tif})
    out = resolver.resolve(f"corpus://{rid}?path=IMG_0124.DNG", root)
    assert out.read_bytes() == tif
    sidecar = json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))
    assert sidecar["mime"] == "image/tiff"


def test_dng_member_auto_orient_fit_is_a_viewable_png(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_zip(root, {"IMG_0124.DNG": _tiff((16, 12))})
    out = resolver.resolve(f"corpus://{rid}?path=IMG_0124.DNG&auto_orient&fit=8x8", root)
    assert out.suffix == ".png"
    with Image.open(out) as png:
        assert png.size == (8, 6)


def test_tiff_member_format_png(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_zip(root, {"scan.tif": _tiff((16, 12))})
    out = resolver.resolve(f"corpus://{rid}?path=scan.tif&format=png", root)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_tiff_frame_count_walks_the_top_level_ifd_chain():
    assert _tiff_frame_count(_tiff()) == 1
    assert _tiff_frame_count(_tiff(pages=3)) == 3
    assert _tiff_frame_count(b"\x89PNG\r\n\x1a\n") is None


def test_tiff_frame_count_survives_a_looping_chain():
    # IFD0 at offset 8, zero entries, next-IFD pointer back to 8 → counted once, no hang.
    le = "little"
    data = b"II*\x00" + (8).to_bytes(4, le) + (0).to_bytes(2, le) + (8).to_bytes(4, le)
    assert _tiff_frame_count(data) == 1
