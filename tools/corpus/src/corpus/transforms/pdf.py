"""PDF transforms — a page selector plus per-page sub-ops, and doc-level introspection.

Grammar (selector + sub-op):

    page=N            select page N (1-indexed)                        -> pdfpage
    page=N&render     render the selected page to an image            -> image
    page=N&text       the page's embedded text layer                  -> text
    page=N&words      per-word boxes ([{text, bbox}], JSON)           -> json
    page=N&probe      per-page structural probe (JSON)                -> json
    probe             whole-document structural probe (JSON)          -> json
    outline           the PDF outline / TOC tree (JSON)               -> json

`page=N` yields an intermediate `pdfpage` working value so a following sub-op can read the
PDF page directly (the embedded text layer, char boxes) rather than OCR'ing a raster. A
**terminal** `pdfpage`, or an image-kind op after it (`bbox`, `mark`, `fit`, `rotate`, …),
auto-renders to image in the resolver — so existing `page=N` and `page=N&bbox=...` URIs and
`address: page=N` segment markers resolve to the page image exactly as before. `render` is
the explicit form of that promotion.

DPI for rendering is read from the render context (default 200).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from corpus import pdf_introspect

from . import RenderContext, register

_DEFAULT_DPI = 200
_PDF_USER_SPACE_DPI = 72  # PDF coordinate space; pypdfium2 scale = target / 72


@dataclass
class PdfPageRef:
    """A selected PDF page. `doc` is the resolver-owned pypdfium2 document (closed by the
    resolver); `index0` is the 0-indexed page; `path` is the artifact on disk (pypdf reads
    the text layer / content stream from it)."""

    doc: Any
    index0: int
    path: Path | None


def _page_number(value: str | None, page_count: int) -> int:
    if value is None:
        raise ValueError("page= requires a value (the 1-indexed page number)")
    try:
        n = int(value)
    except ValueError as exc:
        raise ValueError(f"page= value must be an integer, got {value!r}") from exc
    if n < 1 or n > page_count:
        raise ValueError(f"page {n} out of range (PDF has {page_count} pages)")
    return n


def _reader(ref: PdfPageRef):
    if ref.path is None:
        raise ValueError("page text introspection needs the source artifact path")
    from pypdf import PdfReader

    return PdfReader(str(ref.path))


def _no_value(value: str | None, name: str) -> None:
    if value is not None:
        raise ValueError(f"{name} is flag-style and takes no value (select the page with page=N)")


@register("pdf", "page", "pdfpage")
def select_page(pdf: Any, value: str | None, ctx: RenderContext) -> PdfPageRef:
    """Select page N (1-indexed). Yields a `pdfpage`; a terminal `pdfpage` renders."""
    n = _page_number(value, len(pdf))
    return PdfPageRef(doc=pdf, index0=n - 1, path=ctx.get("artifact_path"))


def render_pdfpage(ref: PdfPageRef, ctx: RenderContext) -> Any:
    """Render the selected page to a PIL Image at the configured DPI. Shared by the
    explicit `render` op and the resolver's auto-promotion of a terminal `pdfpage`."""
    dpi = ctx.get("dpi", _DEFAULT_DPI)
    scale = dpi / _PDF_USER_SPACE_DPI
    page = ref.doc[ref.index0]
    return page.render(scale=scale).to_pil()


@register("pdfpage", "render", "image")
def render(ref: PdfPageRef, value: str | None, ctx: RenderContext) -> Any:
    _no_value(value, "render")
    return render_pdfpage(ref, ctx)


@register("pdfpage", "text", "text")
def page_text(ref: PdfPageRef, value: str | None, ctx: RenderContext) -> str:
    """The page's embedded text layer (pypdf). Empty string when the page carries none."""
    _no_value(value, "text")
    return pdf_introspect.extract_page_text(_reader(ref), ref.index0)


@register("pdfpage", "words", "json")
def page_words(ref: PdfPageRef, value: str | None, ctx: RenderContext) -> str:
    """Per-word boxes for the page's text layer, as JSON."""
    _no_value(value, "words")
    return json.dumps(pdf_introspect.page_words(ref.doc, ref.index0), ensure_ascii=False, indent=2)


@register("pdfpage", "probe", "json")
def page_probe(ref: PdfPageRef, value: str | None, ctx: RenderContext) -> str:
    """Per-page structural probe (dims, rotation, text/image stats, shape hint), as JSON."""
    _no_value(value, "probe")
    data = pdf_introspect.probe_page(_reader(ref), ref.doc, ref.index0)
    return json.dumps(data, ensure_ascii=False, indent=2)


@register("pdf", "probe", "json")
def doc_probe(pdf: Any, value: str | None, ctx: RenderContext) -> str:
    """Whole-document probe (per-page table + /Info + outline flag + shape summary), JSON.
    Per-page is `page=N&probe`."""
    if value is not None:
        raise ValueError("probe is flag-style (whole-document); per-page is page=N&probe")
    path = ctx.get("artifact_path")
    if path is None:
        raise ValueError("probe needs the source artifact path")
    from pypdf import PdfReader

    data = pdf_introspect.probe_document(PdfReader(str(path)), pdf)
    return json.dumps(data, ensure_ascii=False, indent=2)


@register("pdf", "outline", "json")
def doc_outline(pdf: Any, value: str | None, ctx: RenderContext) -> str:
    """The PDF outline / TOC tree, as JSON."""
    if value is not None:
        raise ValueError("outline is flag-style and takes no value")
    return json.dumps(pdf_introspect.read_outline_tree(pdf), ensure_ascii=False, indent=2)
