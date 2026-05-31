"""DOCX draft extraction (deterministic, no LLM).

OOXML word-processing documents are zip containers of XML parts. The drafter reads
them with the standard library alone (no `python-docx`):

- Frontmatter from `docProps/core.xml` + `docProps/app.xml` via ElementTree.
- Walks `word/document.xml`'s body in document order, unwrapping `<w:sdt>` content
  controls. Each top-level block is a paragraph (`<w:p>`) or table (`<w:tbl>`).
- Groups content into one `Section` per top-level heading (a paragraph styled
  `Heading1` or carrying `outlineLvl 0`). Pre-heading content becomes a synthetic
  `entry: Preamble` section. Each section holds one `atom: text` segment whose body is
  rendered markdown (sub-headings → `##`/`###`, paragraphs as prose, tables as GFM
  tables). A document with no headings emits a single flat top-level segment.

Address scheme: `block=<N>` (or `block=<start>-<end>`) — the 1-indexed ordinal of a
block-level element in document order (Word has no fixed pages in the XML). Mode is
`body-draft`; the body is faithful (no interpretation). Tables markdown can't express
(merged/nested cells) are rendered best-effort; the normalizer upgrades to HTML.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from corpus.draft import DrafterResult, register
from corpus.fingerprint import text as text_fp
from corpus.segments import Section, Segment

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {
    "w": _W,
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
}

# Level-1 headings are section boundaries; level ≥2 render as sub-headings inside the
# current section. Built-in Word style ids are `Heading1`..`Heading9`.
_HEADING_RE = re.compile(r"^Heading\s*([1-9])$", re.IGNORECASE)
_TITLE_RE = re.compile(r"^Title", re.IGNORECASE)

_DOCX_SCHEMA_ID = (
    "application/application_vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _local(tag: str) -> str:
    return re.sub(r"^\{[^}]+\}", "", tag)


def _q(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def draft(
    docx_path: Path,
    *,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
) -> DrafterResult:
    fields: dict[str, Any] = {}

    with zipfile.ZipFile(docx_path) as zf:
        members = set(zf.namelist())
        doc_xml = zf.read("word/document.xml") if "word/document.xml" in members else b""
        if "docProps/core.xml" in members:
            fields.update(_read_core_props(zf))
        if "docProps/app.xml" in members:
            fields.update(_read_app_props(zf))
        fields["has_images"] = any(m.startswith("word/media/") for m in members)

    blocks: list[tuple[str, ET.Element]] = []
    if doc_xml:
        body = ET.fromstring(doc_xml).find(_q("body"))
        if body is not None:
            blocks = list(_iter_block_items(body))

    fields["paragraph_count"] = sum(1 for kind, _ in blocks if kind == "para")
    fields["table_count"] = sum(1 for kind, _ in blocks if kind == "table")

    return {
        "fields": fields,
        "segments": _build_segments(blocks),
        "embeds": [],
        "title": fields.get("docx_title") or None,
        "issues": [],
    }


register(_DOCX_SCHEMA_ID)(draft)


# ---------- body walk + section assembly ---------- #


def _iter_block_items(parent: ET.Element):
    """Yield (`para`|`table`, element) for each block-level child in document order,
    transparently unwrapping `<w:sdt>` content controls."""
    for child in parent:
        tag = _local(child.tag)
        if tag == "p":
            yield ("para", child)
        elif tag == "tbl":
            yield ("table", child)
        elif tag == "sdt":
            content = child.find(_q("sdtContent"))
            if content is not None:
                yield from _iter_block_items(content)


class _SectionAcc:
    def __init__(self, entry: str | None, start: int) -> None:
        self.entry = entry
        self.start = start
        self.end = start
        self.lines: list[str] = []

    def add(self, markdown: str, ordinal: int) -> None:
        if markdown:
            self.lines.append(markdown)
        self.end = ordinal

    def body(self) -> str:
        return "\n\n".join(self.lines).strip()


def _build_segments(blocks: list[tuple[str, ET.Element]]) -> list[Section | Segment]:
    """Heading-driven sections, or a single flat segment when there are no headings."""
    accs: list[_SectionAcc] = []
    current = _SectionAcc(entry=None, start=1)
    saw_heading = False

    for ordinal, (kind, el) in enumerate(blocks, start=1):
        if kind == "table":
            current.add(_render_table(el), ordinal)
            continue
        style = _para_style(el)
        level = _heading_level(el, style)
        text = _collapse(_para_text(el))
        if level == 1:
            if current.lines:
                if current.entry is None:
                    current.entry = "Preamble"
                accs.append(current)
            current = _SectionAcc(entry=text or "Section", start=ordinal)
            saw_heading = True
            if text:
                current.add(f"## {text}", ordinal)
            else:
                current.end = ordinal
            continue
        current.add(_render_para(el, style, level, text), ordinal)

    if current.lines:
        if saw_heading and current.entry is None:
            current.entry = "Preamble"
        accs.append(current)

    if not accs:
        return []

    if not saw_heading:
        acc = accs[0]
        body = acc.body()
        return [
            Segment(
                atom="text",
                address=_block_address(acc.start, acc.end),
                perceptual=text_fp.fingerprint_text(body),
                body=body,
            )
        ]

    sections: list[Section] = []
    for acc in accs:
        body = acc.body()
        addr = _block_address(acc.start, acc.end)
        child = Segment(
            atom="text", address=addr, perceptual=text_fp.fingerprint_text(body), body=body
        )
        sections.append(Section(address=addr, entry=acc.entry, segments=[child]))
    return sections


def _block_address(start: int, end: int) -> str:
    return f"block={start}" if end <= start else f"block={start}-{end}"


# ---------- paragraph + table rendering ---------- #


def _para_style(p: ET.Element) -> str | None:
    pPr = p.find(_q("pPr"))
    if pPr is None:
        return None
    pStyle = pPr.find(_q("pStyle"))
    return pStyle.get(_q("val")) if pStyle is not None else None


def _heading_level(p: ET.Element, style: str | None) -> int:
    """Heading level (1 = top-level section boundary), or 0. Style-name match first,
    then the paragraph's `<w:outlineLvl>` (0-indexed → level+1)."""
    if style:
        m = _HEADING_RE.match(style)
        if m:
            return int(m.group(1))
    pPr = p.find(_q("pPr"))
    if pPr is not None:
        lvl = pPr.find(_q("outlineLvl"))
        if lvl is not None:
            val = lvl.get(_q("val"))
            if val is not None and val.isdigit():
                return int(val) + 1
    return 0


def _render_para(p: ET.Element, style: str | None, level: int, text: str) -> str:
    if not text:
        return ""
    if level >= 2:
        return f"{'#' * min(level + 1, 6)} {text}"
    if style and _TITLE_RE.match(style):
        return f"# {text}"
    if _is_list_item(p):
        return f"- {text}"
    return text


def _is_list_item(p: ET.Element) -> bool:
    pPr = p.find(_q("pPr"))
    return pPr is not None and pPr.find(_q("numPr")) is not None


def _para_text(p: ET.Element) -> str:
    """Concatenate visible text in document order — runs, hyperlinks, run-level sdt.
    `<w:tab>` → tab, `<w:br>`/`<w:cr>` → newline (collapsed by `_collapse`)."""
    parts: list[str] = []
    for node in p.iter():
        tag = _local(node.tag)
        if tag == "t":
            parts.append(node.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag in ("br", "cr"):
            parts.append("\n")
    return "".join(parts)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _render_table(tbl: ET.Element) -> str:
    """Render a `<w:tbl>` to a GFM table. First row is the header; `gridSpan` expands
    to blank placeholders so widths stay aligned. Nested tables aren't descended."""
    rows: list[list[str]] = []
    for tr in tbl.findall(_q("tr")):
        cells: list[str] = []
        for tc in tr.findall(_q("tc")):
            texts = [_collapse(_para_text(p)) for p in tc.findall(_q("p"))]
            cells.append(_escape_cell("<br>".join(t for t in texts if t)))
            for _ in range(_grid_span(tc) - 1):
                cells.append("")
        rows.append(cells)

    while rows and not any(c for c in rows[-1]):
        rows.pop()
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join(out)


def _grid_span(tc: ET.Element) -> int:
    tcPr = tc.find(_q("tcPr"))
    if tcPr is None:
        return 1
    gs = tcPr.find(_q("gridSpan"))
    if gs is None:
        return 1
    val = gs.get(_q("val"))
    return max(1, int(val)) if val and val.isdigit() else 1


def _escape_cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").strip()


# ---------- frontmatter extraction ---------- #


def _read_core_props(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        with zf.open("docProps/core.xml") as fh:
            root = ET.parse(fh).getroot()
    except (ET.ParseError, KeyError):
        return {}
    out: dict[str, Any] = {}
    for qname, key in (
        ("dc:title", "docx_title"),
        ("dc:creator", "docx_creator"),
        ("cp:lastModifiedBy", "docx_modified_by"),
        ("dcterms:created", "docx_created_at"),
        ("dcterms:modified", "docx_modified_at"),
    ):
        if v := _text(root, qname):
            out[key] = v
    return out


def _read_app_props(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        with zf.open("docProps/app.xml") as fh:
            root = ET.parse(fh).getroot()
    except (ET.ParseError, KeyError):
        return {}
    out: dict[str, Any] = {}
    for el in root.iter():
        local = _local(el.tag)
        text = (el.text or "").strip()
        if not text:
            continue
        if local == "Application":
            out["docx_application"] = text
        elif local == "Template":
            out["docx_template"] = text
        elif local == "Pages" and text.isdigit():
            out["page_count"] = int(text)
        elif local == "Words" and text.isdigit():
            out["word_count"] = int(text)
    return out


def _text(root: ET.Element, qname: str) -> str:
    el = root.find(qname, _NS)
    return el.text.strip() if el is not None and el.text is not None else ""
