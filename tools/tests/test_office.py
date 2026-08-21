"""Office drafters — docx / xlsx / xls.

Each format is drafted through the real `corpus draft` path and then `corpus lint`-ed
(exit 0), proving the output conforms: heading/sheet sections, text simhash on data
segments, and segment-scope issues lifted to address-scoped §4.3.3.1 `format-loss`
blocks (reconciliation #2). docx uses only the stdlib; xlsx/xls importorskip their
`[office]` deps (present in the dev group).
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import frontmatter

from corpus import paths, records
from corpus._cli import dispatch

_DATA = Path(__file__).parent / "data"


def _setup(tmp_path: Path, rid: str, ext: str, mime: str, src: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    art = paths.artifact_path(root, rid, ext)
    paths.ensure_parent(art)
    shutil.copyfile(src, art)
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime=mime, fields={"title": "t"})
    records.append_origin_block(post, uri="https://e.com/f", snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return root


def _draft_then_lint(root: Path, rid: str) -> tuple[int, int]:
    from tests._draftlib import draft_for_test

    draft_rc = draft_for_test(root, rid)
    lint_rc = dispatch(["lint", rid, "--corpus-root", str(root)])
    return draft_rc, lint_rc


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLS_MIME = "application/vnd.ms-excel"


# ---------- docx (stdlib) ---------- #

_DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>My Document</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Introduction</w:t></w:r></w:p>
    <w:p><w:r><w:t>This is the first paragraph.</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>2</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Conclusion</w:t></w:r></w:p>
    <w:p><w:r><w:t>The end.</w:t></w:r></w:p>
  </w:body>
</w:document>
"""


def _make_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", _DOCUMENT_XML)
        zf.writestr(
            "docProps/core.xml",
            '<?xml version="1.0"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
            ' xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>My Document</dc:title></cp:coreProperties>",
        )


def test_docx_draft_and_lint(tmp_path):
    src = tmp_path / "doc.docx"
    _make_docx(src)
    rid = "d0" * 32
    root = _setup(tmp_path, rid, "docx", _DOCX_MIME, src)

    draft_rc, lint_rc = _draft_then_lint(root, rid)
    assert draft_rc == 0
    assert lint_rc == 0

    post = records.load(paths.record_path(root, rid))
    from corpus import segments as seg_mod

    blocks = list(seg_mod.iter_blocks(post.content))
    # No `Section` is ever asserted (spec §7.8/§4.3.2.1) — flat structural marks + content.
    assert not any(isinstance(b, seg_mod.Section) for b in blocks)
    marks = [b for b in blocks if b.is_structural]
    assert [m.body for m in marks] == ["Introduction", "Conclusion"]
    # Content before the first heading gets no fabricated "Preamble" label — no mark at all.
    assert len(marks) == 2
    # The docx drafter's marks + segments are formless content — stored content with no
    # governing form is the `rendered` derived state (§4.1).
    assert records.derived_state(post) == "rendered"
    assert post.metadata["_artifact"]["fields"].get("title") == "My Document"
    # Fingerprinting is opt-in (default off) — data segments carry no perceptual here.
    intro_idx = next(i for i, b in enumerate(blocks) if getattr(b, "body", None) == "Introduction")
    intro_content = blocks[intro_idx + 1]
    assert intro_content.atom == "text" and intro_content.perceptual is None


def test_docx_fingerprint_opt_in(tmp_path, run_drafter):
    """docx text segments carry a `simhash:` only when the `fingerprint` knob is on."""
    from corpus.draft import docx as docx_mod

    src = tmp_path / "doc.docx"
    _make_docx(src)

    def _text_segs(blocks):
        out = []
        for blk in blocks:
            out.extend(getattr(blk, "segments", [blk]))
        return [s for s in out if s.atom == "text"]

    _, off = run_drafter(docx_mod.draft, src, record_id="d0" * 32)
    assert all(s.perceptual is None for s in _text_segs(off))

    _, on = run_drafter(docx_mod.draft, src, record_id="d0" * 32, fingerprint=True)
    assert any((s.perceptual or "").startswith("simhash:") for s in _text_segs(on))


# ---------- xlsx (openpyxl) ---------- #


def test_xlsx_draft_and_lint(tmp_path):
    import pytest

    openpyxl = pytest.importorskip("openpyxl")
    src = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Name", "Qty"])
    ws.append(["apples", 3])
    ws.append(["pears", 5])
    calc = wb.create_sheet("Calc")
    calc["A1"] = "=SUM(1,2)"
    wb.create_sheet("Empty")
    wb.save(src)

    rid = "e0" * 32
    root = _setup(tmp_path, rid, "xlsx", _XLSX_MIME, src)
    draft_rc, lint_rc = _draft_then_lint(root, rid)
    assert draft_rc == 0
    assert lint_rc == 0

    post = records.load(paths.record_path(root, rid))
    from corpus import segments as seg_mod

    blocks = list(seg_mod.iter_blocks(post.content))
    # No `Section` is ever asserted (spec §7.8/§4.3.2.1) — a structural mark carrying each
    # sheet's own name verbatim, then its rendered content.
    assert not any(isinstance(b, seg_mod.Section) for b in blocks)
    marks = [b for b in blocks if b.is_structural]
    assert {m.body for m in marks} == {"Data", "Calc", "Empty"}

    issues = list(records.iter_issue_blocks(post))
    by_addr = {i["fields"].get("address"): i for i in issues}
    # Calc (formula) → warning; Empty → info. Both address-scoped, format-loss.
    assert all(i["id"] == "format-loss" for i in issues)
    assert by_addr["sheet=Calc"]["fields"]["severity"] == "warning"
    assert by_addr["sheet=Empty"]["fields"]["severity"] == "info"


# ---------- xls (xlrd; committed fixture) ---------- #


def test_xls_draft_and_lint(tmp_path):
    import pytest

    pytest.importorskip("xlrd")
    fixture = _DATA / "sample.xls"
    assert fixture.is_file(), "tests/data/sample.xls fixture missing"

    rid = "f1" * 32
    root = _setup(tmp_path, rid, "xls", _XLS_MIME, fixture)
    draft_rc, lint_rc = _draft_then_lint(root, rid)
    assert draft_rc == 0
    assert lint_rc == 0

    post = records.load(paths.record_path(root, rid))
    from corpus import segments as seg_mod

    blocks = list(seg_mod.iter_blocks(post.content))
    # No `Section` is ever asserted (spec §7.8/§4.3.2.1) — a structural mark carrying the
    # sheet's own name verbatim, then its rendered content, per sheet.
    assert not any(isinstance(b, seg_mod.Section) for b in blocks)
    marks = [b for b in blocks if b.is_structural]
    assert {m.body for m in marks} == {"Data", "Empty"}
    # The Empty sheet contributes an info format-loss issue.
    issues = list(records.iter_issue_blocks(post))
    assert any(i["fields"].get("address") == "sheet=Empty" for i in issues)


def test_xls_cell_value_time_only_cell_does_not_raise():
    """A time-only cell (no date component, e.g. a clock-time or duration column) must
    render as a bare `time`, not raise. `xldate_as_tuple` zeroes the date part for these
    (`(0, 0, 0, H, M, S)`), and `datetime(0, 0, 0, ...)` is invalid — the fix special-cases
    an all-zero date part to a `datetime.time` instead."""
    import datetime as dt

    import pytest

    pytest.importorskip("xlrd")
    from corpus.draft import xls as xls_mod

    class _FakeBook:
        datemode = 0

    class _FakeCell:
        ctype = 3  # xlrd.XL_CELL_DATE
        value = 0.5  # 12:00:00, no date component

    class _FakeSheet:
        book = _FakeBook()

        def cell(self, row, col):
            return _FakeCell()

    assert xls_mod._cell_value(_FakeSheet(), 0, 0) == dt.time(12, 0, 0)
