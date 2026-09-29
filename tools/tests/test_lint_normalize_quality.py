"""The normalize-quality warnings (arbre-ath-steven's 96-run PDF eval, 2026-09-28): trailing
whitespace, unreflowed hard wraps, unescaped masked digits, duplicated bodies, and per-page
text coverage. Each fires on the defect the eval found and stays quiet on the faithful case
the fleet calibration showed is common — a message's own spaces, an OCR'd sign's own lines, a
resent message, a band the record deliberately leaves out."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import coverage, lint, records, segments

# Two pages of distinct words, enough for the coverage floor (MIN_PAGE_TOKENS).
_P1 = [f"alpha{i} bravo{i} charlie{i} delta{i}" for i in range(12)]
_P3 = [f"echo{i} foxtrot{i} golf{i} hotel{i}" for i in range(12)]


def _pdf(pages: list[list[str]]) -> bytes:
    """A hand-built PDF, one Helvetica line per string, top to bottom."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    kids = []
    font_ref = 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for lines in pages:
        ops = ["BT /F1 11 Tf 72 740 Td 14 TL"]
        for ln in lines:
            ops.append(f"({ln}) Tj T*")
        ops.append("ET")
        content = " ".join(ops).encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        content_ref = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (font_ref, content_ref)
        )
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        " ".join(f"{k} 0 R" for k in kids).encode(),
        len(kids),
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def _post(mime: str, content: str) -> frontmatter.Post:
    post = frontmatter.Post(content)
    post.metadata.update({"id": "a" * 64, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(post, uri="https://example.com/p", snapshot="2026-09-28T00:00:00Z")
    return post


def _seg(body: str, address: str = "page=1", overlay: str | None = None) -> str:
    opener = f"text/{overlay}" if overlay else "text"
    return f"<!--segment {opener}\naddress: {address}\n-->\n{body}\n<!--/segment-->\n"


def _ids(mime: str, content: str, root: Path, rule: str) -> list[lint.Finding]:
    post = _post(mime, content)
    blocks = segments.iter_blocks(post.content)
    return [f for f in lint.lint(post, blocks, root) if f.rule_id == rule]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "c"
    (r / "records").mkdir(parents=True)
    (r / "schema").mkdir()
    return r


# ---------- trailing whitespace ---------- #


def test_trailing_whitespace_in_a_pdf_body_warns(root):
    found = _ids("application/pdf", _seg("First line.   \nSecond line.\t\nThird."), root,
                 "body-trailing-whitespace")
    assert [f.fields["lines"] for f in found] == [2]
    assert found[0].severity == "warning"


def test_a_text_native_sources_own_spaces_are_faithful(root):
    body = "hello there   \nsecond"
    assert _ids("application/json", _seg(body, "turn=1", "message"), root,
                "body-trailing-whitespace") == []
    assert _ids("application/pdf", _seg("```\ncode   \n```", overlay="code"), root,
                "body-trailing-whitespace") == []


# ---------- hard wraps ---------- #


def test_a_column_wrap_left_in_a_pdf_body_warns(root):
    body = (
        "The developer reserves the right to modify the floor plans and\n"
        "architectural features without notice to or recourse by the renter,\n"
        "and all renderings are provided for illustration."
    )
    found = _ids("application/pdf", _seg(body), root, "body-hard-wrap")
    assert [f.fields["wraps"] for f in found] == [2]


def test_reflowed_prose_lists_tables_and_ocr_lines_are_quiet(root):
    body = (
        "One sentence ends here.\n\nA list follows:\n- item one\n- item two\n\n"
        "| a | b |\n| --- | --- |\n| x | y |\n"
    )
    assert _ids("application/pdf", _seg(body), root, "body-hard-wrap") == []
    labels = "eufy\nby Anker\n\na. Display\nb. [Memory] button\nc. [Forward/Backward] buttons"
    assert _ids("application/pdf", _seg(labels), root, "body-hard-wrap") == []
    sign = "Treat your hangover\nwith a free poutine"
    assert _ids("application/pdf", _seg(sign, overlay="ocr"), root, "body-hard-wrap") == []
    assert _ids("image/jpeg", _seg(sign, "bbox=0,0,1,1"), root, "body-hard-wrap") == []


# ---------- masked digits ---------- #


def test_an_unescaped_masked_number_warns(root):
    found = _ids("application/pdf", _seg("Card ending ****1234 and ***5678."), root,
                 "body-masked-digits-unescaped")
    assert [f.fields["count"] for f in found] == [2]


def test_escaped_masks_bold_numbers_and_code_are_quiet(root):
    body = r"Card \*\*\*\*1234, total **1234**, and `****9999` in code."
    assert _ids("application/pdf", _seg(body), root, "body-masked-digits-unescaped") == []


def test_masked_digits_is_a_fragment_rule():
    assert "body-masked-digits-unescaped" in lint.FRAGMENT_RULES


# ---------- duplicated bodies ---------- #

_TABLE = "| Date | Description | Amount |\n| --- | --- | --- |\n" + "".join(
    f"| 2026-09-{d:02d} | Purchase at store number {d} downtown | ${d}.00 |\n" for d in range(1, 9)
)


def test_a_body_copied_onto_another_page_warns(root):
    content = _seg(_TABLE, "page=1") + _seg(_TABLE, "page=3")
    found = _ids("application/pdf", content, root, "segment-body-duplicated")
    assert len(found) == 1
    assert found[0].address == "page=3" and found[0].fields["duplicate_of"] == "page=1"


def test_short_bodies_and_resent_messages_are_quiet(root):
    assert _ids("application/pdf", _seg("Page 1 of 4", "page=1") + _seg("Page 1 of 4", "page=2"),
                root, "segment-body-duplicated") == []
    msg = "x" * 50 + " the same long message sent twice " * 10
    content = _seg(msg, "turn=1", "message") + _seg(msg, "turn=2", "message")
    assert _ids("application/json", content, root, "segment-body-duplicated") == []


# ---------- per-page coverage ---------- #


@pytest.fixture()
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "doc.pdf"
    path.write_bytes(_pdf([_P1, ["short page"], _P3]))
    return path


def _segs(content: str) -> list[segments.Segment]:
    return [b for b in segments.iter_blocks(content) if isinstance(b, segments.Segment)]


def test_a_page_rendered_in_full_is_covered(pdf):
    got = coverage.page_coverage(_segs(_seg("\n".join(_P1), "page=1")), pdf)
    assert [(c.page, c.coverage) for c in got] == [(1, 1.0)]


def test_a_page_rendered_as_another_pages_copy_is_not(pdf):
    """The eval's critical failure: page 3 carries page 1's content."""
    content = _seg("\n".join(_P1), "page=1") + _seg("\n".join(_P1), "page=3")
    got = {c.page: c.coverage for c in coverage.page_coverage(_segs(content), pdf)}
    assert got[1] == 1.0 and got[3] == 0.0


def test_only_the_addressed_band_counts(pdf):
    """A band over page 3's first eleven lines owes only those lines' words, not the twelfth."""
    top = _P3[:11]
    got = coverage.page_coverage(_segs(_seg("\n".join(top), "page=3&bbox=0,0,1,0.245")), pdf)
    assert [(c.page, c.coverage, c.tokens) for c in got] == [(3, 1.0, 44)]


def test_a_page_with_too_little_text_is_not_judged(pdf):
    assert coverage.page_coverage(_segs(_seg("nothing", "page=2")), pdf) == []


def test_the_rule_warns_on_the_uncovered_page(root, pdf, monkeypatch):
    import corpus.containment as containment

    monkeypatch.setattr(containment, "ensure_local_bytes", lambda *a, **k: pdf)
    content = _seg("\n".join(_P1), "page=1") + _seg("\n".join(_P1), "page=3")
    found = _ids("application/pdf", content, root, "segment-page-coverage")
    assert [(f.address, f.severity) for f in found] == [("page=3", "warning")]


def test_the_rule_is_silent_without_the_bytes(root, monkeypatch):
    import corpus.containment as containment

    def missing(*a, **k):
        raise FileNotFoundError("no bytes")

    monkeypatch.setattr(containment, "ensure_local_bytes", missing)
    assert _ids("application/pdf", _seg("anything", "page=3"), root,
                "segment-page-coverage") == []


def test_unspaced_scripts_compare_as_character_bigrams():
    """Thai and CJK carry no spaces between words, so the text layer and a faithful
    rendering break their runs differently; bigrams make the two comparable."""
    layer = coverage.tokens("กระแสไฟขาออก 10件宜家智能产品")
    rendered = coverage.tokens("กระแสไฟ ขาออก 10件 宜家智能 产品")
    # Only a bigram straddling a break the other side lacks is lost; as whole-run tokens the
    # two would share nothing at all.
    assert len(layer & rendered) / len(layer) >= 0.8


def test_a_table_the_source_itself_prints_twice_is_not_a_duplicate(root, tmp_path, monkeypatch):
    """v50 validation: a deployment table printed on pages 2 and 6 renders twice, faithfully.
    The regions' own text layers match, so the repetition is the source's."""
    import corpus.containment as containment

    path = tmp_path / "twice.pdf"
    path.write_bytes(_pdf([_P1, _P3, _P1]))
    monkeypatch.setattr(containment, "ensure_local_bytes", lambda *a, **k: path)
    body = "\n".join(_P1) + "\n" + _TABLE
    content = _seg(body, "page=1") + _seg(body, "page=3")
    assert _ids("application/pdf", content, root, "segment-body-duplicated") == []


def test_a_copy_over_a_page_that_says_otherwise_still_warns(root, pdf, monkeypatch):
    """The eval's critical failure, with the bytes in hand: page 3's text layer is its own."""
    import corpus.containment as containment

    monkeypatch.setattr(containment, "ensure_local_bytes", lambda *a, **k: pdf)
    content = _seg(_TABLE, "page=1") + _seg(_TABLE, "page=3")
    assert len(_ids("application/pdf", content, root, "segment-body-duplicated")) == 1
