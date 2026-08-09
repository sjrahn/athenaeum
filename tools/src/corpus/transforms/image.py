"""Image transforms: bbox/crop (relative), resize (absolute), fit (relative,
aspect-preserving), mark (annotate region on the full image), grayscale (spec §6.2).

All operate on `PIL.Image.Image` instances.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from corpus import functional_uri as furi

from . import NotMaterializable, RenderContext, register

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


@register("image", "format", "image")
def format_image(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`format=png` in a frame context (§6.2: "png (frame contexts aside)") — an already-
    selected image (a `frame=`/`page=` render) is always cache-written as PNG, so this is
    an identity confirmation, not a conversion. The muxing contract's video/audio targets
    (mp4/webm/gif/m4a/ogg/wav) live on the `video`/`audio` working kinds instead
    (`corpus.transforms.video`) — an image working value has no muxing to do."""
    if value is None or value.strip().lower() != "png":
        raise ValueError(
            f"format={value!r} not supported on an image working value (only 'png' — "
            f"the muxing contract's media targets apply to video/audio, not a "
            f"already-selected frame/page render)"
        )
    return img


@register("image", "frame", "image")
def frame(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`frame=<N>` — select one 1-based frame of an animated raster (GIF, animated
    WebP/AVIF), so the image transforms downstream (`bbox=`, `mark=`, `fit=`) operate on
    that frame (#124; spec §6.2 — the IMAGE reading of the polymorphic `frame=` axis: an
    ordinal, where the video working kind reads a timecode).

    Reads the source artifact (`ctx["artifact_path"]`), not the working value: the
    resolver's initial image load decodes a single composited frame and closes the file,
    so the sequence is only reachable from the bytes. That makes `frame=` a LEADING
    param by construction — chain it first (`frame=3&bbox=…`), as §6.2 requires; any
    transform applied before it is discarded with the working value.

    A SPAN (`frame=1-8`) is a legitimate stored address — the whole-sequence assertion
    of §4.3.2.2 — but names no single byte surface, so it does not materialize; bounds
    are still checked first (`parse_index_span`: bounds are a property of the address,
    not of whether it materializes)."""
    low, high = furi.parse_index_span("frame", value, noun="the artifact")
    src = ctx.get("artifact_path")
    if src is None:
        raise ValueError("frame= requires the source artifact (resolver supplies artifact_path)")
    with Image.open(src) as im:
        count = getattr(im, "n_frames", 1)
        furi.parse_index_span("frame", value, count=count, noun="this image")
        if low != high:
            raise NotMaterializable(
                f"frame={low}-{high} names a span of the sequence, not a renderable "
                f"unit — resolve a single frame"
            )
        im.seek(low - 1)
        im.load()
        return im.copy()


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


@register("image", "cover", "image")
def cover(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`cover=x,y,w,h[;x,y,w,h...]` — paint the region(s) OUT, filling each with the
    background colour sampled from the pixels immediately around it. Does not crop.

    The chrome remover. Where a capture baked a viewer's own controls into the artifact
    (AllData's schematic sheets carry a column of navigation icons at the top right), the
    obvious fix is to crop them off — but a rectangle only works when nothing real shares
    the chrome's x-range, and on a wide drawing the sheet's own labels usually do, at some
    other height. Covering removes the chrome *in place*, so content that merely sits
    beside it survives; chain a `crop=`/`bbox=` afterwards when a crop is also wanted.

    The fill is SAMPLED, never assumed white: the modal colour of a one-region-thick ring
    just outside the box, so a tinted or scanned background stays consistent and the patch
    does not announce itself. Each value is a float in [0, 1] (a fraction of the image),
    origin top-left; multiple regions are `;`-separated.

    This is a lossy op by nature — it deletes pixels. It rides the address, so the
    deletion is disclosed wherever the surface is cited (§6.2): a reader sees the region
    was covered and can resolve the same address without the op to see what was removed.
    Use it for chrome, never to make an inconvenient part of the artifact go away."""
    if value is None:
        raise ValueError("cover= requires at least one x,y,w,h region (fractions in [0,1])")
    boxes = [_parse_box(chunk) for chunk in value.split(";") if chunk]
    if not boxes:
        raise ValueError("cover= requires at least one x,y,w,h region (fractions in [0,1])")

    out = img.convert("RGB")
    draw = ImageDraw.Draw(out)
    iw, ih = out.size
    for x, y, w, h in boxes:
        left, top = round(x * iw), round(y * ih)
        right, bottom = round((x + w) * iw), round((y + h) * ih)
        if right <= left or bottom <= top:
            continue
        fill = _ring_modal_colour(out, left, top, right, bottom)
        draw.rectangle((left, top, right - 1, bottom - 1), fill=fill)
    return out


def _ring_modal_colour(
    img: Image.Image, left: int, top: int, right: int, bottom: int
) -> tuple[int, int, int]:
    """The modal colour of a thin ring just OUTSIDE the box — the local background.

    Sampling around the region rather than globally is what keeps the patch invisible on a
    page whose background is not uniform. A box flush against the image edge simply has
    less ring to sample; an empty ring (the box covers everything) falls back to white,
    which is the only defensible guess left."""
    iw, ih = img.size
    pad = max(2, round(min(iw, ih) * 0.004))
    counts: dict[tuple[int, int, int], int] = {}
    px = img.load()
    ring_x = range(max(0, left - pad), min(iw, right + pad))
    ring_y = range(max(0, top - pad), min(ih, bottom + pad))
    for yy in (range(max(0, top - pad), top), range(bottom, min(ih, bottom + pad))):
        for y in yy:
            for x in ring_x:
                counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    for xx in (range(max(0, left - pad), left), range(right, min(iw, right + pad))):
        for x in xx:
            for y in ring_y:
                counts[px[x, y]] = counts.get(px[x, y], 0) + 1
    if not counts:
        return (255, 255, 255)
    return max(counts.items(), key=lambda kv: kv[1])[0]


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


# Quarter-turns map to lossless transposes (PIL's ROTATE_* are counter-clockwise;
# `rotate=` is clockwise, so a clockwise N° turn uses the (360-N) transpose).
_ROTATE_CW = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}


@register("image", "rotate", "image")
def rotate(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`rotate=90|180|270` — rotate clockwise by a quarter turn (lossless transpose;
    90/270 swap width and height). For righting a sideways or upside-down scan/photo;
    arbitrary-angle deskew is out of scope."""
    if value is None:
        raise ValueError("rotate= requires a value: 90, 180, or 270 (degrees clockwise)")
    try:
        deg = int(value)
    except ValueError as exc:
        raise ValueError(f"rotate= must be an integer, got {value!r}") from exc
    if deg not in _ROTATE_CW:
        raise ValueError(f"rotate= must be 90, 180, or 270 (degrees clockwise), got {deg}")
    return img.transpose(_ROTATE_CW[deg])


@register("image", "auto_orient", "image")
def auto_orient(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`auto_orient` — apply the EXIF orientation tag so a sideways/flipped phone photo
    or scan displays upright. Flag-style (no value). A no-op when the image carries no
    orientation tag, so it is always safe to prepend."""
    if value is not None:
        raise ValueError(f"auto_orient is flag-style and takes no value, got {value!r}")
    return ImageOps.exif_transpose(img)


@register("image", "autocontrast", "image")
def autocontrast(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`autocontrast` — stretch the per-channel histogram to full range (1% cutoff to
    ignore outliers). Flag-style. Pulls faint/low-contrast scans toward readable."""
    if value is not None:
        raise ValueError(f"autocontrast is flag-style and takes no value, got {value!r}")
    base = img if img.mode in ("RGB", "L") else img.convert("RGB")
    return ImageOps.autocontrast(base, cutoff=1)


@register("image", "contrast", "image")
def contrast(img: Image.Image, value: str | None, ctx: RenderContext) -> Image.Image:
    """`contrast=<factor>` — scale contrast by a float (1.0 = unchanged, >1 stronger,
    <1 flatter). For a faint scan try 1.5-2.5. Use `autocontrast` when you'd rather not
    pick a number."""
    if value is None:
        raise ValueError("contrast= requires a float factor (1.0 = unchanged)")
    try:
        factor = float(value)
    except ValueError as exc:
        raise ValueError(f"contrast= must be a float, got {value!r}") from exc
    if factor < 0:
        raise ValueError(f"contrast= must be >= 0, got {factor}")
    return ImageEnhance.Contrast(img).enhance(factor)


# ---------- helpers ---------- #


def _parse_box(value: str) -> tuple[float, float, float, float]:
    """Parse one `x,y,w,h` region of relative floats in [0, 1]. Shared by `crop=`,
    `mark=`, and `cover=`.

    Delegates to `functional_uri.parse_region` — the ONE definition of the region
    grammar, so the render path and `corpus lint` cannot drift apart on what an
    authored address is allowed to say."""
    return furi.parse_region(value)


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
