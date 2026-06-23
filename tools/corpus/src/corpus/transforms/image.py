"""Image transforms: bbox/crop (relative), resize (absolute), fit (relative,
aspect-preserving), mark (annotate region on the full image), grayscale (spec §6.2).

All operate on `PIL.Image.Image` instances.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from . import RenderContext, register

# ---- fit= presets ---------------------------------------------------------- #
# The `llm` preset bounds an image to a vision-model's input budget. These numbers
# are Claude-current and intentionally live HERE, not in the normative spec (§6.2
# describes `fit=` generically) — model input limits drift, and the spec must stay
# model-agnostic. (long_edge_px, max_pixels). Long edge ≤ 1568px and total pixels
# capped keep a resolved image inside the no-server-side-downscale, token-efficient
# range; both bounds are applied (the smaller scale wins).
LLM_MAX_EDGE = 1568
LLM_MAX_PIXELS = 1_150_000
_FIT_PRESETS: dict[str, tuple[int, int]] = {"llm": (LLM_MAX_EDGE, LLM_MAX_PIXELS)}

# High-visibility stroke colors, cycled across multiple marked regions.
_MARK_COLORS: tuple[tuple[int, int, int], ...] = (
    (230, 25, 25),
    (25, 120, 230),
    (30, 170, 70),
    (200, 120, 0),
    (170, 40, 200),
)


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
    x, y, w, h = _parse_box(value)
    iw, ih = img.size
    box = (
        round(x * iw),
        round(y * ih),
        round((x + w) * iw),
        round((y + h) * ih),
    )
    return img.crop(box)


@register("image", "mark", "image")
def mark(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`mark=x,y,w,h[;x,y,w,h...]` — draw the region(s) onto the FULL image (does
    NOT crop). The inspection dual of `crop=`: it shows where a region sits in
    context so an agent can judge the fit and adjust before committing a segment
    address. Each value is a float in [0, 1] (a fraction of the image), origin
    top-left; multiple regions are `;`-separated and auto-labeled 1..N."""
    if value is None:
        raise ValueError("mark= requires at least one x,y,w,h region (fractions in [0,1])")
    boxes = [_parse_box(chunk) for chunk in value.split(";") if chunk]
    if not boxes:
        raise ValueError("mark= requires at least one x,y,w,h region (fractions in [0,1])")

    out = img.convert("RGB")  # a colored stroke needs RGB; also detaches from the source
    draw = ImageDraw.Draw(out)
    iw, ih = out.size
    stroke = max(2, round(min(iw, ih) * 0.004))
    font = _label_font(max(11, round(min(iw, ih) * 0.022)))
    for i, (x, y, w, h) in enumerate(boxes):
        color = _MARK_COLORS[i % len(_MARK_COLORS)]
        left, top = round(x * iw), round(y * ih)
        right, bottom = round((x + w) * iw), round((y + h) * ih)
        draw.rectangle((left, top, max(left, right - 1), max(top, bottom - 1)),
                       outline=color, width=stroke)
        _draw_label(draw, str(i + 1), left, top, color, font)
    return out


@register("image", "resize", "image")
def resize(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """Resize to absolute pixel dimensions: `resize=WxH`. Forces both dimensions
    (may distort aspect, may enlarge) — use `fit=` to scale within a box."""
    if value is None:
        raise ValueError("resize= requires a value of the form WxH (pixels)")
    w, h = _parse_dims(value, "resize=")
    return img.resize((w, h), Image.LANCZOS)


@register("image", "fit", "image")
def fit(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`fit=<W>x<H>` or `fit=<preset>` — downscale to fit within a bounding box
    while preserving aspect ratio. Reduces only; never enlarges (an image already
    within bounds passes through untouched). Unlike `resize=` (exact, distorting),
    `fit=` keeps proportions. The `llm` preset bounds the image to a vision-model's
    input budget (long edge + total pixels)."""
    if value is None:
        raise ValueError("fit= requires a value: <W>x<H> or a preset name (e.g. llm)")
    iw, ih = img.size
    if iw < 1 or ih < 1:
        return img
    if value in _FIT_PRESETS:
        max_edge, max_pixels = _FIT_PRESETS[value]
        scale = min(1.0, max_edge / max(iw, ih), (max_pixels / (iw * ih)) ** 0.5)
    else:
        bw, bh = _parse_dims(value, "fit=")
        scale = min(1.0, bw / iw, bh / ih)
    if scale >= 1.0:
        return img  # already within budget — downscale-only
    return img.resize((max(1, round(iw * scale)), max(1, round(ih * scale))), Image.LANCZOS)


@register("image", "grayscale", "image")
def grayscale(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """Convert to single-channel grayscale. Flag-style (no value)."""
    if value is not None:
        raise ValueError(f"grayscale is flag-style and takes no value, got {value!r}")
    return img.convert("L")


# ---------- helpers ---------- #


def _parse_box(value: str) -> tuple[float, float, float, float]:
    """Parse one `x,y,w,h` region of relative floats in [0, 1], bounds-checked so
    the region stays inside the image. Shared by `crop=` and `mark=`."""
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError(f"region must have 4 comma-separated values, got {value!r}")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"region values must be floats, got {value!r}") from exc
    for label, val in (("x", x), ("y", y), ("w", w), ("h", h)):
        if val < 0.0 or val > 1.0:
            raise ValueError(f"region {label}={val} out of [0.0, 1.0]")
    if x + w > 1.0 + 1e-9 or y + h > 1.0 + 1e-9:
        raise ValueError(f"region extends beyond image bounds: {value!r}")
    return x, y, w, h


def _parse_dims(value: str, prefix: str) -> tuple[int, int]:
    """Parse `WxH` absolute pixel dimensions. Shared by `resize=` and `fit=`."""
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"{prefix} must be of the form WxH, got {value!r}")
    try:
        w, h = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"{prefix} values must be integers, got {value!r}") from exc
    if w < 1 or h < 1:
        raise ValueError(f"{prefix} dimensions must be positive, got {w}x{h}")
    return w, h


def _label_font(size: int) -> ImageFont.ImageFont:
    """The default bitmap font, sized when the Pillow build supports it."""
    try:
        return ImageFont.load_default(size)
    except TypeError:  # older Pillow: load_default takes no size
        return ImageFont.load_default()


def _draw_label(
    draw: ImageDraw.ImageDraw,
    text: str,
    left: int,
    top: int,
    color: tuple[int, int, int],
    font: ImageFont.ImageFont,
) -> None:
    """Draw a small solid index chip at the box's top-left corner."""
    try:
        tb = draw.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
    except Exception:
        tw, th = 8 * len(text), 12
    pad = 2
    draw.rectangle((left, top, left + tw + 2 * pad, top + th + 2 * pad), fill=color)
    draw.text((left + pad, top + pad), text, fill=(255, 255, 255), font=font)
