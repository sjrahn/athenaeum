"""Form triage packets (spec §8.5, v50): what a classifier needs to propose a record's form.

A formless record is complete (§4.1), but where an obvious form fits, the normalize pass should
follow it — and the pass is better for being told which. Triage is the cheap look that says so,
over many records at once. It never decides and never writes: this module reads a record and
its bytes into a small **packet** of already-cheap probe features, and a model (the triage
agent, which batches packets against the form catalog) proposes `form/<id>`, a terminal
contract, or defer. A proposal reaches the normalizer only as a queue hint on a record some
consumer already asked about (`corpus enqueue --hint`, the proposes/disposes seam) — never as
a request of its own, because normalization runs only under demand (§8.5).

The features are arbre-ath-steven's 2026-09-28 prototype's, measured on 255 labelled records
(Sonnet 5.5 low at confidence >= 0.7: 70% decided, 97% strict precision): the record's mime,
origin, and role-marked fields; for HTML its `<title>`, structural tag counts, and opening text;
for a PDF its probe (pages, outline, image coverage, characters per page, invisible text) and
the opening text of pages 1-2; for OOXML its document text. In-process, so a batch pays one
start-up, not one per `corpus resolve`.
"""

from __future__ import annotations

import html as _html
import re
import zipfile
from pathlib import Path
from typing import Any

import frontmatter

from corpus import records, schemas

TEXT_CHARS = 1500
# A PDF's probe reads at most this many pages: the shape of a document shows in its opening.
PROBE_PAGES = 12

_KEEP_FIELDS = ("uri", "filename", "title", "author", "producer", "page_count", "subject")
_HTML_TAGS = ("a", "li", "ol", "ul", "h1", "h2", "h3", "table", "article", "img", "p", "form")


def eligible(post: frontmatter.Post, corpus_root: Path, *, proxy_only: bool) -> bool:
    """A record triage may propose a form for: not formed, and no contract governs it (no
    origin form, no mime terminal, no manifest derivation — `shape.governing_form`). With
    `proxy_only`, additionally one storing no rendering at all (the proxy population)."""
    from corpus import shape

    if records.is_formed(post) or shape.governing_form(post, corpus_root) is not None:
        return False
    return not (proxy_only and records.has_stored_rendering(post))


def form_catalog(corpus_root: Path) -> list[dict[str, Any]]:
    """Every form the corpus can name — id, whether it is terminal, and its description."""
    out = []
    for form_id in schemas.list_form_overlays(corpus_root):
        overlay = schemas.load_form_overlay(corpus_root, form_id) or {}
        out.append(
            {
                "form": form_id,
                "terminal": schemas.is_terminal_form(corpus_root, form_id),
                "description": " ".join(str(overlay.get("description") or "").split()),
            }
        )
    return out


def packet(post: frontmatter.Post, corpus_root: Path) -> dict[str, Any]:
    """One record's triage packet. Byte-reading features degrade silently to absent — a
    packet without them is still a packet."""
    rid = str(post.metadata.get("id") or "")
    mime = records.media_type_for(post)
    art = records.artifact_block(post) or {}
    fields = {k: v for k, v in (art.get("fields") or {}).items() if k in _KEEP_FIELDS}
    origins = []
    for block in records.iter_origin_blocks(post):
        of = block.get("fields") or {}
        keep = {k: _short(v) for k, v in of.items() if k in _KEEP_FIELDS}
        origins.append({"id": block.get("id"), **keep})
    out: dict[str, Any] = {
        "id": rid,
        "mime": mime,
        "fields": {k: _short(v) for k, v in fields.items()},
        "origins": origins,
    }
    try:
        from corpus import mime as _mime
        from corpus.containment import ensure_local_bytes

        path = ensure_local_bytes(corpus_root, rid, _mime.extension_for(mime))
    except Exception:
        return out
    try:
        if mime == "text/html":
            out.update(_html_features(path))
        elif mime == "application/pdf":
            out.update(_pdf_features(path))
        elif mime.startswith("application/vnd.openxmlformats-officedocument"):
            out.update(_ooxml_features(path))
        elif mime.startswith("text/"):
            out["text"] = _clip(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    return out


def _short(value: Any) -> Any:
    if isinstance(value, list):
        return [str(v)[:160] for v in value[:3]]
    return str(value)[:160]


def _clip(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:TEXT_CHARS]


def _html_features(path: Path) -> dict[str, Any]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    counts = {t: len(soup.find_all(t)) for t in _HTML_TAGS}
    for dead in soup(["script", "style", "noscript", "template", "head"]):
        dead.decompose()
    text = soup.get_text(" ", strip=True)
    return {
        "html_title": _html.unescape(title)[:160],
        "html_counts": counts,
        "text_chars": len(text),
        "text": _clip(text),
    }


def _pdf_features(path: Path) -> dict[str, Any]:
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    from corpus import pdf_introspect

    reader = PdfReader(str(path))
    doc = pdfium.PdfDocument(str(path))
    try:
        n = len(reader.pages)
        pages = [pdf_introspect.probe_page(reader, doc, i) for i in range(min(n, PROBE_PAGES))]
        text = " ".join(pdf_introspect.extract_page_text(reader, i) for i in range(min(n, 2)))
        hints = [p["shape_hint"] for p in pages]
        return {
            "page_count": n,
            "has_outline": bool(pdf_introspect.read_outline_tree(doc)),
            "shape_summary": pdf_introspect._summarize_shape(hints),
            "mean_image_coverage": round(
                sum(p["image_coverage"] for p in pages) / max(1, len(pages)), 3
            ),
            "chars_per_page": round(
                sum(p["text_char_count"] for p in pages) / max(1, len(pages))
            ),
            "invisible_text": any(p["has_invisible_text"] for p in pages),
            "info": pdf_introspect.document_info(reader),
            "text": _clip(text),
        }
    finally:
        doc.close()


def _ooxml_features(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as z:
        names = [
            n for n in z.namelist()
            if re.match(r"(word/document|ppt/slides/slide\d+|xl/sharedStrings)\.xml$", n)
        ]
        text = " ".join(
            re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace")) for n in names
        )
    return {"text": _clip(text)}
