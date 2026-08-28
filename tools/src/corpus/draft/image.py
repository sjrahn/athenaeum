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

import corpus._pil  # noqa: F401 — registers the optional HEIF opener (v41)
from corpus import content_hash, recordbuild, records
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, image_fingerprints
from corpus.segments import Segment

# Register the same drafter for every bundled image MIME schema. A custom
# corpus mime schema can be added by registering a new drafter for that schema id.
_IMAGE_SCHEMA_IDS = (
    "image/image_png",
    "image/image_jpeg",
    "image/image_gif",
    "image/image_webp",
    "image/image_avif",
    "image/image_heic",
)

_EXIF_FIELDS: tuple[tuple[str, str], ...] = (
    ("Make", "exif_make"),
    ("Model", "exif_model"),
    ("DateTimeOriginal", "exif_datetime"),
    ("DateTime", "exif_datetime"),
)

# (3.10 §4.3.2.2) The formats whose bytes decide whether they are a still or a sequence.
# Their schemas declare `whole_address: single_unit_only` with `whole_address_count:
# frame_count`, so the gate compares this attested number and never decodes.
_ANIMATION_CAPABLE = {"GIF", "WEBP", "AVIF", "HEIF", "HEIC"}


def _gif_frame_count(data: bytes) -> int | None:
    """Frames in a GIF, by walking its block structure.

    Counting 0x2C bytes naively would hit colour-table and LZW payload bytes, so this
    walks the stream properly: header, optional global colour table, then blocks until
    the trailer."""
    if data[:3] != b"GIF":
        return None
    i = 13
    if len(data) > 10 and data[10] & 0x80:
        i += 3 * (2 ** ((data[10] & 0x07) + 1))
    n = 0
    try:
        while i < len(data):
            marker = data[i]
            if marker == 0x3B:                          # trailer
                break
            if marker == 0x21:                          # extension block
                i += 2
                while data[i]:
                    i += data[i] + 1
                i += 1
            elif marker == 0x2C:                        # image descriptor
                n += 1
                flags = data[i + 9]
                i += 10
                if flags & 0x80:                        # local colour table
                    i += 3 * (2 ** ((flags & 0x07) + 1))
                i += 1                                  # LZW minimum code size
                while data[i]:
                    i += data[i] + 1
                i += 1
            else:
                break
    except IndexError:
        return n or None
    return n or None


def _webp_frame_count(data: bytes) -> int | None:
    """Frames in a WebP, by counting `ANMF` chunks in the RIFF container.

    Deliberately structural rather than `PIL.n_frames`: Pillow returns 1 both for a still
    AND for an animation it cannot decode, and `features.check('webp_anim')` is false in
    some builds — so the decoder's answer is indistinguishable from blindness. The
    container says so without a codec."""
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    n = data.count(b"ANMF")
    return n if n else 1


def _frame_count(path: Path, fmt: str, im: Image.Image) -> int | None:
    """The artifact's frame count, or None when the format has no frame axis.

    Structural readers first, decoder second — an attested fact must not vary with which
    optional codecs the ingesting host happens to have installed."""
    if fmt not in _ANIMATION_CAPABLE:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if fmt == "GIF" and (n := _gif_frame_count(data)) is not None:
        return n
    if fmt == "WEBP" and (n := _webp_frame_count(data)) is not None:
        return n
    try:                                    # AVIF/HEIF: no structural reader yet
        return int(getattr(im, "n_frames", 1))
    except Exception:
        return None


def draft(
    image_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,  # phash/dhash/ahash/whash (needs [fingerprint])
) -> DrafterResult:
    fields: dict[str, Any] = {
        "size_bytes": image_path.stat().st_size,
        "description": "",  # normalizer-populated
    }

    with Image.open(image_path) as im:
        fields["width"] = im.width
        fields["height"] = im.height
        fields["format"] = im.format or ""
        fields["mode"] = im.mode

        # (3.10 §7.2.1) The count `whole_address: single_unit_only` is gated on. Stamped
        # only for the formats that can hold a sequence — on a PNG the field would be a
        # constant 1 asserting nothing.
        frames = _frame_count(image_path, (im.format or "").upper(), im)
        if frames is not None:
            fields["frame_count"] = frames

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

    # Perceptual fingerprint on the single image-atom segment (opt-in via the schema
    # `fingerprint` knob; the image is its own self-artifact, so no embed is needed).
    perceptual = image_fingerprints(image_path, algos_for_atom("image", fingerprint))
    recordbuild.add_blocks(
        build, [Segment(atom="image", address="bbox=0,0,1,1", perceptual=perceptual, body="")]
    )
    # Canonical hash per the mime schema's `canonical_strategy.algo`; the strategy id
    # encodes its hash family (e.g. `blake3-canonical-image` → `blake3:`).
    algo = canonical_algo or "blake3-canonical-image"
    canonical = records.format_hash(algo.split("-", 1)[0], content_hash.compute(algo, image_path))

    return {
        "fields": fields,
        "embeds": [],
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
