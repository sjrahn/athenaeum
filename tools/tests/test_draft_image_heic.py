"""`image/heic` joins the bundled image family (v41): sniffed by brand, drafted by the
shared image drafter once `pillow-heif` (the `media` extra) registers its opener. Skips
honestly without the extra — a base install cannot open a HEIC, and says so."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

from corpus import _pil, hashing, mime, paths, records, resolver, schemas
from corpus._cli import ingest as ingest_cli

pytestmark = pytest.mark.skipif(not _pil.HEIF_AVAILABLE, reason="needs pillow-heif (media extra)")


def _heic() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 6), (10, 20, 30)).save(buf, format="HEIF")
    return buf.getvalue()


def test_heic_sniffs_by_brand_and_maps_extension_and_kind():
    data = _heic()
    assert data[4:12] == b"ftypheic"
    assert mime.sniff_head(data[:512], "IMG_0001.HEIC") == "image/heic"
    assert mime.extension_for("image/heic") == "heic"
    assert mime.extension_for("image/heif") == "heif"
    assert resolver._INITIAL_KIND_FOR_MIME["image/heic"] == "image"


def test_heic_ingests_and_attests_like_any_still(tmp_path: Path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    src = tmp_path / "IMG_0001.HEIC"
    src.write_bytes(_heic())
    cap = root / "capture"
    cap.mkdir()
    shutil.copy(src, cap / src.name)
    assert ingest_cli._ingest_one(root, cap / src.name) == 0

    rid = hashing.hash_file(src)["blake3"]
    post = records.load(paths.record_path(root, rid))
    assert records.media_type_for(post) == "image/heic"
    fields = (records.artifact_block(post) or {}).get("fields") or {}
    assert (fields.get("width"), fields.get("height")) == (8, 6)
    assert fields.get("format") == "HEIF"
    # The frame axis: a still HEIF attests `frame_count: 1`, the count the schema's
    # `whole_address: single_unit_only` gate reads.
    assert fields.get("frame_count") == 1
    assert schemas.load_mime_schema(root, "image/heic")["whole_address"] == "single_unit_only"
