"""`corpus.textnorm` — the tolerant matcher `ath ledger verify` and the corpus
address-fidelity gate (#159) share. The document-order cases are ported verbatim from
`tests/test_ledger_tools.py::test_quote_found_requires_document_order`, which is the
behavior the factor-out had to preserve exactly."""

from __future__ import annotations

from corpus.textnorm import norm, quote_found, squash

_TABLE = ("<tr><td>Head bolts</td><td>22 ft-lb</td></tr>"
          "<tr><td>Wheel lug nuts</td><td>100 ft-lb</td></tr>")


def test_verify_is_a_thin_alias_onto_this_module():
    """`ledger.verify._norm` / `_quote_found` keep their historical names for verify's own
    call sites — as aliases, so there is exactly one definition to drift."""
    from ledger import verify

    assert verify._norm is norm
    assert verify._quote_found is quote_found


def test_quote_found_requires_document_order():
    """Ported from the ledger suite: fragments must be a FORWARD reading of the record —
    backward assembly of true substrings is refuted (the anti- "Head bolts | 100 ft-lb"
    rule)."""
    assert quote_found("Head bolts | 22 ft-lb", _TABLE)
    assert quote_found("Head bolts ... lug nuts", _TABLE)
    assert not quote_found("100 ft-lb | Head bolts", _TABLE)
    assert not quote_found("lug nuts ... Head bolts", _TABLE)


def test_norm_decodes_entities_folds_quotes_and_collapses_whitespace():
    assert norm("<p>Rock&rsquo;s   Auto &amp; Parts</p>") == "Rock's Auto & Parts"
    assert norm("a\xa0b") == "a b"  # a NO-BREAK SPACE folds to a plain one


def test_norm_strips_markdown_only_when_asked():
    assert norm("See the [Torque Spec](/t) for **details**") == "See the Torque Spec for details"
    assert norm("a <3 b", strip_markup=False) == "a <3 b"
    assert norm("| a | b |") == "a b"


def test_norm_leaves_a_stray_bracket_alone():
    """The 1.5 defect: `<[^>]+>` swallowed everything up to the next unrelated `>` anywhere
    later in the document, silently deleting spans of a derived surface."""
    assert norm("x < y and later > z", strip_markup=False) == "x < y and later > z"


def test_squash_absorbs_separators_for_the_retry():
    assert squash("Head bolts - 22 ft-lb") == "Headbolts22ftlb"
    assert quote_found("Headbolts", "<b>Head</b> bolts")


def test_comparison_operators_in_prose_survive_tag_stripping():
    """The third generation of the tag-regex defect (2026-08-14 scribe find):
    a bracket-free prose span between `<` and `>` — clinical text's paired
    comparison operators — must NOT be eaten as a tag. Only tag-shaped runs
    (`<` + letter or `/`) strip."""
    from corpus.textnorm import norm, quote_found

    hay = (
        "patients >=65 years old and <65 years old. THE MECHANISM PARAGRAPH. "
        "In controlled clinical trials in >900 patients, the efficacy was evaluated."
    )
    assert "THE MECHANISM PARAGRAPH" in norm(hay)
    assert quote_found("THE MECHANISM PARAGRAPH", hay)
    assert quote_found("<65 years old", hay)
    # real inline tags still vanish without splitting the word
    assert norm("under<u>line</u>d") == "underlined"
    assert norm("a <span class='x'>b</span> c") == "a b c"
