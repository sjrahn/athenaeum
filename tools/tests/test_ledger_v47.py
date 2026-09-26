"""v47 (owner rulings 2026-09-25, codex-steven R-0039 items 4-5):

- **Row-precise citation** (ledger §13.2): a region anchor scopes to the stored segment(s) AT
  it — or, when it is no stored address, to the page segments its region overlaps — never
  the whole page; a quote carrying `|` cells must match within ONE table row; a free-text
  anchor is a check error (§6.2 already called it a defect).
- **Mint proposals** (ledger §7.2): a hypothesis carries `proposes_new: {id, type, name,
  claims}` for a fact not yet minted; check refuses a taken id; `promote` mints it and lands
  its drafts, validating everything before writing anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pytest

from corpus import paths, records, schemas, segments
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.promote import PromoteError, promote
from ledger.verify import _quote_in_one_row, verify_ledger
from tests.test_ledger_check import (  # noqa: F401 — `system` is a fixture
    H_PUB,
    _check,
    _claim,
    _fact,
    _interp,
    _regen,
    system,
)

_TABLE = (
    "| Date | Description | Amount |\n"
    "|---|---|---|\n"
    "| Mar 04 | SAFEWAY #4907 | 52.18 |\n"
    "| Mar 05 | SHELL C01234 | 40.00 |"
)
_SUMMARY_ADDR = "page=1&bbox=0,0.1,1,0.2"
_TABLE_ADDR = "page=1&bbox=0,0.4,1,0.4"
RID = "5" * 64


def _statement(tmp_path: Path, extra: tuple = ()) -> Path:
    """A formed card statement: a summary segment and a transactions table on page 1."""
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=RID, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="application/pdf", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([
        segments.Segment(atom="text", overlay="text/ocr", address=_SUMMARY_ADDR,
                         body="New balance 92.18 due Apr 01"),
        segments.Segment(atom="text", overlay="text/data-table", address=_TABLE_ADDR,
                         body=_TABLE),
        *extra,
    ])
    records.dump(post, paths.record_path(root, RID))
    return root


def _verify(tmp_path: Path, anchor: str | None, quote: str, extra: tuple = ()):
    root = _statement(tmp_path, extra)
    ledger = tmp_path / "ledger"
    (ledger / "facts" / "doc").mkdir(parents=True)
    evidence = {"source": "s1", "quote": quote, "kind": "authoritative"}
    if anchor is not None:
        evidence["anchor"] = anchor
    (ledger / "facts" / "doc" / "card.json").write_text(json.dumps({
        "id": "card", "type": "doc", "name": "Card",
        "sources": {"s1": {"record": RID}},
        "claims": [{"id": "card:spend", "predicate": "spent", "value": "x",
                    "status": "confirmed", "asof": "2026-03-05", "evidence": [evidence]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    return verify_ledger(ledger, join, {}, stamp=False)


# ---------- item 4: the anchor scopes to its segment ---------- #


def test_a_stored_region_anchor_scopes_to_its_segment_not_its_page(tmp_path):
    ok = _verify(tmp_path / "a", _TABLE_ADDR, "Mar 04 | SAFEWAY #4907 | 52.18")
    assert ok.errors == [] and ok.verified == 1
    # the summary's words are on page 1 too — but not in the table segment the anchor names
    res = _verify(tmp_path / "b", _TABLE_ADDR, "New balance 92.18")
    assert len(res.errors) == 1 and "NOT at the cited anchor" in res.errors[0]


def test_an_unstored_region_scopes_to_the_segments_it_overlaps(tmp_path):
    inside = "page=1&bbox=0,0.5,1,0.05"  # a strip through the table
    assert _verify(tmp_path / "a", inside, "SHELL C01234 | 40.00").verified == 1
    res = _verify(tmp_path / "b", inside, "New balance 92.18")
    assert len(res.errors) == 1 and "NOT at the cited anchor" in res.errors[0]
    res = _verify(tmp_path / "c", "page=1&bbox=0,0.9,1,0.05", "Mar 04")  # overlaps nothing
    assert len(res.errors) == 1 and "does not resolve" in res.errors[0]


def test_a_textless_stored_region_still_resolves(tmp_path):
    # an image region with no text of its own: a quote-less cite of it resolves (§6.2)
    # instead of reading as "overlaps nothing" beside the page's text segments
    figure = "page=1&bbox=0,0.85,0.5,0.1"
    extra = (segments.Segment(atom="image", overlay="image/figure", address=figure, body=""),)
    res = _verify(tmp_path, figure, "", extra)
    assert res.errors == []


def test_section_and_schema_declared_axes_are_not_prose():
    from ledger.check import _anchor_unknown_param

    for anchor in ("pages=2-4", "spines=1-3", "line=3&jsonpath=$.a"):
        assert _anchor_unknown_param(anchor) is None, anchor
    assert _anchor_unknown_param("Purchases table, page 2") is not None


def test_a_bare_page_anchor_still_names_the_whole_page(tmp_path):
    assert _verify(tmp_path, "page=1", "New balance 92.18").verified == 1


def test_a_cell_quote_verifies_within_one_row_only(tmp_path):
    # one row's date joined to the next row's amount: in document order, so the old
    # in-order match verified it
    res = _verify(tmp_path / "a", _TABLE_ADDR, "Mar 04 | 40.00")
    assert len(res.errors) == 1 and "one table row" in res.errors[0]
    # a record-level cite holds a cell quote to the same rule
    res = _verify(tmp_path / "b", None, "SAFEWAY #4907 | 40.00")
    assert len(res.errors) == 1 and "one table row" in res.errors[0]
    assert _verify(tmp_path / "c", None, "Mar 05 | 40.00").verified == 1


def test_an_html_table_row_is_a_row():
    html = "<table><tr><td>Mar 04</td><td>52.18</td></tr><tr><td>Mar 05</td><td>40.00</td></tr>"
    assert _quote_in_one_row("Mar 05 | 40.00", html)
    assert not _quote_in_one_row("Mar 04 | 40.00", html)


def test_a_free_text_anchor_is_a_check_error(system):  # noqa: F811
    _fact(system, "doc", {
        "id": "stmt", "type": "doc", "name": "Statement",
        "claims": [_claim("stmt", "spend", evidence=[
            {"_record": H_PUB, "kind": "direct",
             "anchor": "Purchases data-table, page 2 (2025-03 statement)"},
            {"_record": H_PUB, "kind": "direct", "anchor": "page=2&bbox=0,0.2,1,0.5"},
            {"_record": H_PUB, "kind": "direct", "anchor": "#page-2"},
        ])],
    })
    _regen(system)
    errors = _check(system).errors
    assert len(errors) == 1
    assert "not a functional-URI address" in errors[0] and "Purchases data-table" in errors[0]


# ---------- item 5: proposes_new ---------- #


def _trip(root: Path) -> None:
    _fact(root, "trip", {"id": "banff-2022-11", "type": "trip", "name": "Banff, Nov 2022"})


def _mint_hypothesis(**over) -> dict:
    h = {
        "id": "banff-2022-11-was-beerfest", "kind": "hypothesis",
        "about": ["banff-2022-11"],
        "statement": "The Banff trip was for Banff Beerfest 2022.",
        "confidence": "plausible", "reasoning": "a festival wristband charge",
        "based_on": [f"corpus://{H_PUB}"],
        "proposes_new": {
            "id": "banff-beerfest-2022", "type": "event", "name": "Banff Beerfest 2022",
            "claims": [{"id": "banff-beerfest-2022:held-in", "predicate": "held_in",
                        "value": "Banff", "evidence": [
                            {"uri": f"corpus://{H_PUB}", "kind": "direct"}]}],
        },
        "proposes": {"id": "banff-2022-11:attended", "predicate": "attended",
                     "object": "banff-beerfest-2022",
                     "evidence": [{"uri": f"corpus://{H_PUB}", "kind": "direct"}]},
        "status": "open", "asof": "2026-09-25",
    }
    h.update(over)
    return h


def test_a_mint_proposal_checks_clean(system):  # noqa: F811
    _trip(system)
    _interp(system, _mint_hypothesis())
    _regen(system)
    assert _check(system).errors == []


def test_proposes_naming_an_unminted_fact_points_at_proposes_new(system):  # noqa: F811
    _trip(system)
    h = _mint_hypothesis()
    del h["proposes_new"]
    _interp(system, h)
    _regen(system)
    errors = _check(system).errors
    assert len(errors) == 1
    assert "object 'banff-beerfest-2022' names no fact" in errors[0]
    assert "proposes_new" in errors[0]


def test_a_mint_of_a_taken_id_or_a_stray_claim_is_refused(system):  # noqa: F811
    _trip(system)
    h = _mint_hypothesis()
    h["proposes_new"]["id"] = "banff-2022-11"  # the trip itself: taken
    h["proposes_new"]["claims"][0]["id"] = "banff-2022-11:held-in"
    h["proposes"]["object"] = "banff-2022-11"
    _interp(system, h)
    _regen(system)
    assert any("already exists" in e for e in _check(system).errors)

    h = _mint_hypothesis()
    h["proposes_new"]["claims"][0]["id"] = "banff-2022-11:held-in"  # not on the mint
    _interp(system, h)
    _regen(system)
    assert any("must target the minted fact" in e for e in _check(system).errors)


def test_promote_mints_the_fact_and_lands_every_draft(system):  # noqa: F811
    _trip(system)
    _interp(system, _mint_hypothesis())
    ledger = system / "ledger"
    out = promote(ledger, "banff-2022-11-was-beerfest")
    assert out.startswith("minted banff-beerfest-2022; ")
    minted = json.loads((ledger / "facts" / "event" / "banff-beerfest-2022.json").read_text())
    assert (minted["id"], minted["type"], minted["name"]) == (
        "banff-beerfest-2022", "event", "Banff Beerfest 2022"
    )
    assert [c["id"] for c in minted["claims"]] == ["banff-beerfest-2022:held-in"]
    trip = json.loads((ledger / "facts" / "trip" / "banff-2022-11.json").read_text())
    assert trip["claims"][0]["object"] == "banff-beerfest-2022"
    interp = json.loads(
        (ledger / "interpretations" / "banff-2022-11-was-beerfest.json").read_text()
    )
    assert interp["status"] == "promoted" and interp["resolution"] == "banff-2022-11:attended"
    _regen(system)
    assert _check(system).errors == []


def test_a_promotion_that_cannot_land_whole_writes_nothing(system):  # noqa: F811
    # no trip fact: the `proposes` target is missing, so the mint must not happen either
    _interp(system, _mint_hypothesis())
    ledger = system / "ledger"
    with pytest.raises(PromoteError, match="no fact file"):
        promote(ledger, "banff-2022-11-was-beerfest")
    assert not (ledger / "facts" / "event").exists()
    interp = json.loads(
        (ledger / "interpretations" / "banff-2022-11-was-beerfest.json").read_text()
    )
    assert interp["status"] == "open"


def test_a_scope_with_no_table_keeps_the_plain_separator():
    # OCR'd signage that sets words apart with pipes: no rows, no cells to straddle
    assert _quote_in_one_row("ABF EXHIBITOR | MEDIA", "ABF\nEXHIBITOR | MEDIA | VOLUNTEER")
