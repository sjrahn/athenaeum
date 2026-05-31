"""Image draft extraction (deterministic).

Reads file metadata from an image artifact (dimensions, format, mode, size) and any
EXIF tags Pillow can parse. Emits a single body-empty `<!--segment image-->`
positioning marker at `bbox=0,0,1,1` (spec §4.3.2.2 — image-atom segments carry no
body). The whole-image description is normalizer-populated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

from corpus import content_hash
from corpus.draft import DrafterResult, register
from corpus.segments import Segment

# Register the same drafter for every bundled image MIME schema. A custom
# corpus mime schema can be added by registering a new drafter for that schema id.
_IMAGE_SCHEMA_IDS = (
    "image/image_png",
    "image/image_jpeg",
    "image/image_gif",
    "image/image_webp",
    "image/image_avif",
)

_EXIF_FIELDS: tuple[tuple[str, str], ...] = (
    ("Make", "exif_make"),
    ("Model", "exif_model"),
    ("DateTimeOriginal", "exif_datetime"),
    ("DateTime", "exif_datetime"),
)


def draft(
    image_path: Path,
    *,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
) -> DrafterResult:
    fields: dict[str, Any] = {
        "image_size_bytes": image_path.stat().st_size,
        "description": "",  # normalizer-populated
    }

    with Image.open(image_path) as im:
        fields["image_width"] = im.width
        fields["image_height"] = im.height
        fields["image_format"] = im.format or ""
        fields["image_mode"] = im.mode

        try:
            exif = im.getexif()
        except Exception:
            exif = None

        if exif:
            tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            for src, dst in _EXIF_FIELDS:
                if src in tag_map and dst not in fields:
                    value = _str(tag_map[src])
                    if value:
                        fields[dst] = value

            gps = _gps_from_exif(exif)
            if gps:
                fields["exif_gps"] = gps

    segments = [Segment(atom="image", address="bbox=0,0,1,1", body="")]
    canonical = f"blake3:{content_hash.compute('blake3-canonical-image', image_path)}"

    return {
        "fields": fields,
        "segments": segments,
        "embeds": [],
        "title": None,
        "issues": [],
        "canonical": canonical,
    }


# Register for each bundled image schema id.
for _sid in _IMAGE_SCHEMA_IDS:
    register(_sid)(draft)


# ---------- helpers ---------- #


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.rstrip(b"\x00").decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
    return str(value).strip().rstrip("\x00").strip()


def _gps_from_exif(exif: Any) -> str:
    """Extract decimal-degree GPS from EXIF, if both lat and lon are present."""
    try:
        gps_ifd = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
    except Exception:
        gps_ifd = None
    if not gps_ifd:
        return ""

    gps_tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
    lat = _dms_to_decimal(gps_tags.get("GPSLatitude"), gps_tags.get("GPSLatitudeRef"))
    lon = _dms_to_decimal(gps_tags.get("GPSLongitude"), gps_tags.get("GPSLongitudeRef"))
    if lat is None or lon is None:
        return ""
    return f"{lat:.6f},{lon:.6f}"


def _dms_to_decimal(dms: Any, ref: Any) -> float | None:
    if not dms or not ref:
        return None
    try:
        d, m, s = (float(v) for v in dms)
    except (TypeError, ValueError):
        return None
    decimal = d + m / 60.0 + s / 3600.0
    ref_str = _str(ref).upper()
    if ref_str in ("S", "W"):
        decimal = -decimal
    return decimal
