"""PDF exposable members at `attachment=<N>` (spec corpus §7.1 PDF row, §12.11).

A PDF's embedded files and portfolio members (an Acrobat portfolio is a cover page plus
its members in the EmbeddedFiles name tree) are rostered, resolvable, re-chainable (an
embedded PDF takes `page=`/`text`), and promotable through containment. Before this, the
spec promised the axis but nothing implemented it: a portfolio drafted as its cover page
alone, with its members unreachable.
"""

from __future__ import annotations

import io

import pypdfium2 as pdfium
import pytest

from corpus import containment, resolver
from corpus.draft import pdf as pdf_draft
from tests.test_html_text_and_cid import _corpus, _stage_record
from tests.test_pdf_words_rotation import _pdf

_INNER = _pdf()  # one page: "HEADERWORD" + "body line text"
_NOTE = b"errata: none\n"


def _portfolio() -> bytes:
    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    for name, data in (("Protocol_V2.1.pdf", _INNER), ("notes.txt", _NOTE),
                       ("notes-copy.txt", _NOTE)):
        att = doc.new_attachment(name)
        att.set_data(data)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def portfolio(tmp_path):
    root = _corpus(tmp_path)
    data = _portfolio()
    rid = _stage_record(root, data, mime="application/pdf", name="package.pdf")
    src = root.parent / "package.pdf"
    return root, rid, src


def test_drafter_rosters_every_embedded_file(portfolio, run_drafter):
    _root, _rid, src = portfolio
    result, _blocks = run_drafter(pdf_draft.draft, src)
    rows = {r["fields"]["filename"]: r for r in result["embeds"]}
    # the name tree's key order (`-` sorts before `.`), and identical bytes share one row
    # named by its first address
    assert set(rows) == {"Protocol_V2.1.pdf", "notes-copy.txt"}
    assert rows["Protocol_V2.1.pdf"]["address"] == "attachment=1"
    assert rows["Protocol_V2.1.pdf"]["media_type"] == "application/pdf"
    assert rows["Protocol_V2.1.pdf"]["fields"]["bytes"] == len(_INNER)
    assert rows["notes-copy.txt"]["address"] == ["attachment=2", "attachment=3"]


def test_attachment_resolves_and_rechains_into_the_member(portfolio):
    root, rid, _src = portfolio
    out = resolver.resolve(f"corpus://{rid}?attachment=1", root)
    assert out.read_bytes() == _INNER and out.suffix == ".pdf"
    text = resolver.resolve(f"corpus://{rid}?attachment=1&page=1&text", root)
    assert "HEADERWORD" in text.read_text("utf-8")
    assert resolver.resolve(f"corpus://{rid}?attachment=3", root).read_text() == \
        _NOTE.decode()
    with pytest.raises(Exception, match="out of range"):
        resolver.resolve(f"corpus://{rid}?attachment=4", root)
    assert resolver.engine_version_for_param("attachment") == "pdf-attachment@1"


def test_members_stream_through_containment_for_promotion(portfolio):
    _root, _rid, src = portfolio
    with containment.open_member_stream(src, "application/pdf", "attachment=1") as fp:
        assert fp.read() == _INNER
    meta = containment.member_source_metadata(src, "application/pdf", "attachment=1")
    assert meta == {"filename": "Protocol_V2.1.pdf"}
