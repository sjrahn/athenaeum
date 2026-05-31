"""PDF transforms — `page=N` (PDF → image at the configured DPI).

DPI is read from the render context; default 200 if absent.
"""

from __future__ import annotations

from typing import Any

from . import RenderContext, register

_DEFAULT_DPI = 200
_PDF_USER_SPACE_DPI = 72  # PDF coordinate space; pypdfium2 scale = target / 72


@register("pdf", "page", "image")
def render_page(pdf: Any, value: str | None, ctx: RenderContext) -> Any:
    """Render page N (1-indexed) to a PIL Image at the configured DPI.

    `pdf` is a pypdfium2.PdfDocument. Output is a PIL Image (RGB).
    """
    if value is None:
        raise ValueError("page= requires a value (the 1-indexed page number)")
    try:
        n = int(value)
    except ValueError as exc:
        raise ValueError(f"page= value must be an integer, got {value!r}") from exc

    if n < 1 or n > len(pdf):
        raise ValueError(f"page {n} out of range (PDF has {len(pdf)} pages)")

    dpi = ctx.get("dpi", _DEFAULT_DPI)
    scale = dpi / _PDF_USER_SPACE_DPI

    page = pdf[n - 1]
    bitmap = page.render(scale=scale)
    return bitmap.to_pil()
