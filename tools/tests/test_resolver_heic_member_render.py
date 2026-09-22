"""A HEIC/HEIF container member renders to a viewable PNG through the image ops it already
has (codex-steven R-0036, 2026-09-22).

The R-0035 photo-library pilot shelled every HEIC to `heif-convert` + `magick` because
`corpus resolve '…?path=IMG_x.HEIC'` hands back the member's raw bytes. That is §6.2's
member re-chaining rule working as written — a TERMINAL member address never re-encodes
what no op asked to transform — and the other half of the same rule is the answer: chain
any image op and the member re-enters the image pipeline (`image/heic` → working kind
`image`, v41), so `…&format=png` / `…&auto_orient&fit=llm` are the viewable rendering,
cached and engine-pinned like every other derived surface. No new op; this file pins
the route so it cannot silently regress, and `_common.TRANSFORM_GRAMMAR` now says so.

Orientation parity, established on the real osxphotos container (ath-steven, IMG_1438.HEIC,
sidecar `orientation: 6`, `width: 6048`, `height: 8064`): pillow-heif decodes to the
DISPLAY frame (6048x8064 — the same frame `heif-convert` writes and the sidecar's
`width`/`height` describe), reports the source tag as `original_orientation`, and resets
the EXIF tag to 1 — so `auto_orient` is a safe no-op, never a double turn. The test below
asserts the resolver's frame is exactly Pillow's frame for the member bytes.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import frontmatter
import pytest
from PIL import Image, ImageOps

from corpus import _pil, hashing, paths, records, resolver, schemas
from corpus import functional_uri as furi
from corpus import mime as mime_mod
from corpus.store import LocalArtifactStore

pytestmark = pytest.mark.skipif(not _pil.HEIF_AVAILABLE, reason="needs pillow-heif (media extra)")


def _heic(size: tuple[int, int] = (16, 12)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buf, format="HEIF")
    return buf.getvalue()


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _stage_zip(root: Path, members: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    import zipfile

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
        snapshot="2026-09-22T00:00:00Z",
        fields={"filename": "export.zip", "source_modified": ""},
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_bare_heic_member_is_the_raw_bytes(tmp_path):
    """The terminal address serves the member verbatim — the half of the rule the pilot
    hit. Extension and sidecar mime say what it is, so a reader learns to chain an op."""
    root = _corpus(tmp_path)
    heic = _heic()
    rid = _stage_zip(root, {"IMG_0001.HEIC": heic})
    out = resolver.resolve(f"corpus://{rid}?path=IMG_0001.HEIC", root)
    assert out.read_bytes() == heic
    assert out.suffix == "." + mime_mod.extension_for("image/heic")
    sidecar = json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))
    assert sidecar["mime"] == "image/heic"


def test_heic_member_format_png_is_a_viewable_full_frame_rendering(tmp_path):
    root = _corpus(tmp_path)
    heic = _heic((16, 12))
    rid = _stage_zip(root, {"IMG_0001.HEIC": heic})
    out = resolver.resolve(f"corpus://{rid}?path=IMG_0001.HEIC&format=png", root)
    assert out.suffix == ".png"
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(out) as png, Image.open(io.BytesIO(heic)) as decoded:
        # the resolver's frame IS Pillow's display frame for these bytes — no extra turn
        assert png.size == decoded.size == (16, 12)
        assert ImageOps.exif_transpose(decoded).size == decoded.size
    sidecar = json.loads(furi.cache_sidecar_path(out).read_text("utf-8"))
    assert sidecar["mime"] == "image/png"


def test_heic_member_auto_orient_fit_is_bounded_and_aspect_preserving(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_zip(root, {"IMG_0001.HEIC": _heic((16, 12))})
    out = resolver.resolve(f"corpus://{rid}?path=IMG_0001.HEIC&auto_orient&fit=8x8", root)
    assert out.suffix == ".png"
    with Image.open(out) as png:
        assert png.size == (8, 6)


def test_heic_member_rendering_is_cached_under_the_canonical_uri(tmp_path):
    """Same URI → same cache file (spec §6.4); a different view op is a different surface."""
    root = _corpus(tmp_path)
    rid = _stage_zip(root, {"IMG_0001.HEIC": _heic()})
    a = resolver.resolve(f"corpus://{rid}?path=IMG_0001.HEIC&fit=8x8", root)
    b = resolver.resolve(f"corpus://{rid}?path=IMG_0001.HEIC&fit=8x8", root)
    c = resolver.resolve(f"corpus://{rid}?path=IMG_0001.HEIC&format=png", root)
    assert a == b
    assert a != c
