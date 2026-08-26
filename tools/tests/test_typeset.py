"""`corpus.typeset` — the ported LaTeX-math translator + markdown->Typst emitter."""

from __future__ import annotations

import shutil

import pytest

from corpus import typeset

_HAVE_TYPST = shutil.which("typst") is not None
needs_typst = pytest.mark.skipif(not _HAVE_TYPST, reason="typst binary not installed")


# ---------- math translator ---------- #


def test_greek_and_operators():
    assert typeset.latex_to_typst_math(r"\alpha \leq \beta \times \gamma") == (
        "alpha <= beta times gamma"
    )


def test_frac_and_subscript_superscript():
    assert typeset.latex_to_typst_math(r"\frac{a}{b}") == "frac(a, b)"
    assert typeset.latex_to_typst_math("x_i^2") == 'x_(i)^(2)'


def test_sum_glues_subscript_to_base():
    # The symbol-spacing pass inserts a space after `sum`; the subscript-glue pass must
    # remove it again so `sum_(i=1)` isn't `sum _(i=1)` (invalid as a Typst base+script).
    conv = typeset.latex_to_typst_math(r"\sum_{i=1}^n x_i")
    assert "sum_(i=1)" in conv
    assert "sum _(i=1)" not in conv


def test_sqrt_and_nth_root():
    assert typeset.latex_to_typst_math(r"\sqrt{2}") == "sqrt(2)"
    assert typeset.latex_to_typst_math(r"\sqrt[3]{8}") == "root(3, 8)"


def test_matrix_environment():
    conv = typeset.latex_to_typst_math(r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}")
    assert conv is not None
    assert conv.startswith('mat(delim: "[",')
    assert "1 & 2" in conv and "3 & 4" in conv


def test_cases_environment():
    conv = typeset.latex_to_typst_math(r"\begin{cases} 1 & x > 0 \\ 0 & x \leq 0 \end{cases}")
    assert conv is not None
    assert conv.startswith("cases(")


def test_unmapped_command_falls_back_to_none():
    # `\varinjlim` isn't in any translation table — the caller (markdown_to_typst / the
    # inline math span) is responsible for the verbatim fallback; the pure translator
    # itself just reports "I don't know this one" rather than guessing.
    assert typeset.latex_to_typst_math(r"\varinjlim_{n} x_n") is None


def test_verbatim_fallback_in_inline_math():
    out = typeset.markdown_to_typst(r"before $\varinjlim x$ after")
    assert r"`$\varinjlim x$`" in out


# ---------- markdown -> typst emitter ---------- #


def test_heading_levels():
    out = typeset.markdown_to_typst("# One\n\n### Three\n")
    assert "= One" in out
    assert "=== Three" in out


def test_bold_and_code_and_link():
    out = typeset.markdown_to_typst("**bold** and `code` and [text](https://example.com)")
    assert "*bold*" in out
    assert "`code`" in out
    assert '#link("https://example.com")[text]' in out


def test_display_math_block():
    out = typeset.markdown_to_typst("$$\n\\alpha + \\beta\n$$\n")
    assert "$ alpha + beta $" in out


def test_fenced_code_untouched():
    out = typeset.markdown_to_typst("```python\nprint(1)\n```\n")
    assert "```python" in out and "print(1)" in out


def test_image_line_becomes_figure():
    out = typeset.markdown_to_typst("![a chart](assets/x.png)\n")
    assert '#figure(image("assets/x.png", width: 90%), caption: [a chart])' in out


def test_html_table_conversion():
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>\n"
    out = typeset.markdown_to_typst(html)
    assert "#table(" in out
    assert "[*A*]" in out or "[A]" in out  # header cell present either way
    assert "[1]" in out and "[2]" in out


def test_markdown_pipe_table_conversion():
    """Our own `text/data-table` segments may emit a markdown pipe table rather than a
    literal HTML `<table>` — the adaptation this port made beyond the fork's original."""
    out = typeset.markdown_to_typst("| A | B |\n|---|---|\n| 1 | 2 |\n")
    assert "#table(" in out
    assert "columns: 2" in out
    assert "[*A*]" in out and "[*B*]" in out
    assert "[1]" in out and "[2]" in out


def test_markdown_pipe_table_pads_ragged_rows():
    out = typeset.markdown_to_typst("| A | B | C |\n|---|---|---|\n| 1 | 2 |\n")
    assert "columns: 3" in out
    # a ragged row pads to an empty trailing cell rather than raising or misaligning
    assert out.count("[") >= 6


def test_plain_blockquote_is_a_quote():
    out = typeset.markdown_to_typst("> just a quote\n> continued\n")
    assert "#quote(block: true)" in out
    assert "[!" not in out


def test_admonition_blockquote_is_a_colored_block():
    out = typeset.markdown_to_typst("> [!PASSTHROUGH] page=3\n> the detail here\n")
    assert "#quote" not in out
    assert "#block(" in out
    assert "stroke: (left: 2.5pt + gray)" in out
    assert "page=3" in out
    assert "the detail here" in out


def test_admonition_colors_by_kind():
    err = typeset.markdown_to_typst("> [!LINT-ERROR] rule-x\n> message\n")
    warn = typeset.markdown_to_typst("> [!LINT-WARNING] rule-y\n> message\n")
    info = typeset.markdown_to_typst("> [!LINT-INFO] rule-z\n> message\n")
    assert "+ red)" in err
    assert "+ orange)" in warn
    assert "+ blue)" in info


def test_unknown_admonition_kind_defaults_to_gray():
    out = typeset.markdown_to_typst("> [!SOMETHING-NEW] title\n> body\n")
    assert "+ gray)" in out


# ---------- frontmatter / title block / compile ---------- #


def test_record_typst_includes_title_and_source():
    md = "---\ntitle: My Record\nsource: https://example.com/x\n---\n\nBody text.\n"
    out = typeset.record_typst(md, standalone=True)
    assert "My Record" in out
    assert 'link("https://example.com/x")' in out
    assert "Body text." in out
    assert out.startswith("#set page")  # standalone carries the preamble


def test_record_typst_body_only_when_not_standalone():
    md = "---\ntitle: T\n---\n\nBody.\n"
    out = typeset.record_typst(md, standalone=False)
    assert "#set page" not in out


def test_typst_available_reflects_path(monkeypatch):
    monkeypatch.setattr(typeset.shutil, "which", lambda _name: None)
    assert typeset.typst_available() is False
    monkeypatch.setattr(typeset.shutil, "which", lambda _name: "/usr/bin/typst")
    assert typeset.typst_available() is True


@needs_typst
def test_compile_pdf_produces_a_real_pdf(tmp_path):
    typ = tmp_path / "doc.typ"
    typ.write_text(typeset._PREAMBLE + "\n= Hello\n\nWorld.\n", encoding="utf-8")
    pdf = tmp_path / "doc.pdf"
    assert typeset.compile_pdf(typ, pdf, root=tmp_path) is True
    assert pdf.is_file()
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_compile_pdf_returns_false_without_typst(tmp_path, monkeypatch):
    monkeypatch.setattr(typeset, "typst_available", lambda: False)
    typ = tmp_path / "doc.typ"
    typ.write_text("= Hello\n", encoding="utf-8")
    pdf = tmp_path / "doc.pdf"
    assert typeset.compile_pdf(typ, pdf, root=tmp_path) is False
    assert not pdf.exists()
