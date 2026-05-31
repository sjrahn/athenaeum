"""Image transforms: bbox/crop (relative), resize (absolute), grayscale (spec §6.2).

All operate on `PIL.Image.Image` instances.
"""

from __future__ import annotations

from PIL import Image

from . import RenderContext, register


@register("image", "bbox", "image")
def bbox(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`bbox=x,y,w,h` — synonym for `crop=`. Matches the address-scheme param
    declared by PDF and image media-type schemas."""
    return crop(img, value, ctx)


@register("image", "crop", "image")
def crop(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """Crop a relative region: `crop=x,y,w,h` with each value a float in [0, 1]
    representing a fraction of the current image's dimensions. Origin top-left."""
    if value is None:
        raise ValueError("crop= requires a value of the form x,y,w,h (fractions in [0,1])")
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError(f"crop= must have 4 comma-separated values, got {value!r}")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"crop= values must be floats, got {value!r}") from exc

    for label, val in (("x", x), ("y", y), ("w", w), ("h", h)):
        if val < 0.0 or val > 1.0:
            raise ValueError(f"crop= {label}={val} out of [0.0, 1.0]")
    if x + w > 1.0 + 1e-9 or y + h > 1.0 + 1e-9:
        raise ValueError(f"crop= region extends beyond image bounds: {value!r}")

    iw, ih = img.size
    box = (
        round(x * iw),
        round(y * ih),
        round((x + w) * iw),
        round((y + h) * ih),
    )
    return img.crop(box)


@register("image", "resize", "image")
def resize(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """Resize to absolute pixel dimensions: `resize=WxH`."""
    if value is None:
        raise ValueError("resize= requires a value of the form WxH (pixels)")
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"resize= must be of the form WxH, got {value!r}")
    try:
        w, h = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"resize= values must be integers, got {value!r}") from exc
    if w < 1 or h < 1:
        raise ValueError(f"resize= dimensions must be positive, got {w}x{h}")
    return img.resize((w, h), Image.LANCZOS)


@register("image", "grayscale", "image")
def grayscale(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """Convert to single-channel grayscale. Flag-style (no value)."""
    if value is not None:
        raise ValueError(f"grayscale is flag-style and takes no value, got {value!r}")
    return img.convert("L")
