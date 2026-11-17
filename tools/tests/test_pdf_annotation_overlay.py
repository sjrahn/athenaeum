"""A PDF page that draws annotations over its content gets `format-loss/annotation-overlay`
at `page=<N>`: the drafted body is the text layer, which holds none of what they draw and
still holds what they cover (a CAR report's typed correction over a white box read, in the
text layer, as the value it replaced)."""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText, Link, Rectangle

from corpus.draft import pdf as pdf_draft
from tests.test_pdf_words_rotation import _pdf


def _annotated(tmp_path, *annots) -> PdfReader:
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(_pdf())))
    for a in annots:
        w.add_annotation(page_number=0, annotation=a)
    out = tmp_path / "a.pdf"
    w.write(out)
    return PdfReader(out)


def test_a_correction_over_a_box_flags_the_page(tmp_path):
    reader = _annotated(tmp_path, Rectangle(rect=(70, 715, 300, 745)),
                        FreeText(text="11,211", rect=(70, 715, 300, 745)))
    [issue] = pdf_draft._annotation_overlay_issues(reader)
    assert issue["id"] == "format-loss" and issue["subtype"] == "annotation-overlay"
    assert issue["address"] == "page=1" and issue["severity"] == "warning"
    assert issue["fields"] == {"annotation_subtypes": ["FreeText", "Square"],
                               "annotation_count": 2}


def test_links_and_unannotated_pages_raise_nothing(tmp_path):
    assert pdf_draft._annotation_overlay_issues(PdfReader(io.BytesIO(_pdf()))) == []
    reader = _annotated(tmp_path, Link(rect=(0, 0, 10, 10), url="https://example.com"))
    assert pdf_draft._annotation_overlay_issues(reader) == []


def test_drafter_emits_it(tmp_path, run_drafter):
    _annotated(tmp_path, FreeText(text="x", rect=(70, 715, 300, 745)))
    result, _ = run_drafter(pdf_draft.draft, tmp_path / "a.pdf")
    assert [i["subtype"] for i in result["issues"]] == ["annotation-overlay"]
