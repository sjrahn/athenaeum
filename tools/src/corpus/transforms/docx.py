"""DOCX transforms — the resolution side of the `block=` axis (spec §7.1 OOXML, v47.1).

- `block=<N>` / `block=<a>-<b>` (docx → docxblock) — selects block-level elements of
  `word/document.xml` in document order (`<w:sdt>` unwrapped), the axis the drafter
  addresses its segments on. A terminal `docxblock` renders to the blocks' markdown exactly
  as the drafter writes it (`resolver.resolve`'s `docxblock` → `text` step), so a stored
  `address: block=N` resolves to its own text.
- `el=<K>` (docxblock → bytes) — the K-th embedded part block N references
  (`draft.docx.member_refs`: pictures and OLE objects, document order, `mc:Fallback`
  skipped), served verbatim. It is a member axis: the resolver re-detects the part's own
  type, so a further op continues in the member's pipeline.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .. import functional_uri as furi
from ..draft import docx as docx_draft
from . import RenderContext, register

# Folded into the cache key of every resolution on a docx record (`resolver.resolve`).
ENGINE_VERSION = "docx-block@1"


@dataclass
class DocxBlockRef:
    """Selected blocks, the `docx` → `docxblock` working value."""

    path: Path
    blocks: list[tuple[str, ET.Element]]  # the selected blocks, in order
    start: int  # the first selected block's ordinal, for error messages


@register("docx", "block", "docxblock")
def select_block(path: Path, value: str | None, ctx: RenderContext) -> DocxBlockRef:
    """`?block=N` or `?block=a-b` — 1-indexed block-level elements in document order."""
    with zipfile.ZipFile(path) as zf:
        doc_xml = zf.read("word/document.xml") if "word/document.xml" in zf.namelist() \
            else b""
    blocks = docx_draft.read_blocks(doc_xml)
    low, high = furi.parse_index_span("block", value, count=len(blocks), noun="document")
    return DocxBlockRef(path=path, blocks=blocks[low - 1:high], start=low)


def render(ref: DocxBlockRef) -> str:
    """A terminal `block=` — the selected blocks' markdown, joined as the drafter joins
    them in a segment body."""
    parts = [docx_draft.render_block(kind, el) for kind, el in ref.blocks]
    return "\n\n".join(p for p in parts if p).strip() + "\n"


@register("docxblock", "el", "bytes")
def extract_member(ref: DocxBlockRef, value: str | None, ctx: RenderContext) -> bytes:
    """`?block=N&el=K` — the K-th embedded part block N references, its bytes verbatim."""
    if len(ref.blocks) != 1:
        raise ValueError(f"block={ref.start}-…: el= needs a single block, not a span")
    with zipfile.ZipFile(ref.path) as zf:
        rels = docx_draft.read_rels(zf)
        refs = docx_draft.member_refs(ref.blocks[0][1], rels)
        low, high = furi.parse_index_span("el", value, count=len(refs),
                                          noun=f"block {ref.start}")
        if low != high:
            raise ValueError(f"el={low}-{high}: a span of members has no single byte surface")
        part = rels[refs[low - 1]]
        if part not in zf.namelist():
            raise ValueError(f"block={ref.start}&el={low}: relationship {refs[low - 1]!r} "
                             f"names {part!r}, which the package does not hold")
        data = zf.read(part)
    ctx["member_name"] = part.rsplit("/", 1)[-1]
    return data
