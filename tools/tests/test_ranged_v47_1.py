"""v47.1 (owner ruling 2026-10-28): version-ranged claims — stage 1, the roster's
revision stratum and the schema flags (spec/ledger.md §4.2, §4.4, §13.1).

- The roster gains `revision` (a text state, named by its tag) and `against` (its
  predecessor). An omitted `revision` is the expression's sole text state, named by the
  expression slug.
- Schemas gain field `ranged:`/`expression_ledger:` and element `verbatim:`/`locator:`.
  The expression ledger's elements name rostered expressions, and a `change_summary`
  is evidence-bound.
"""

from __future__ import annotations

from pathlib import Path

from ledger.ranged import read_roster
from tests.test_ledger_check import (  # noqa: F401 — `system` is a fixture
    H_BOTH,
    H_PUB,
    H_PUB2,
    _check,
    _claim,
    _fact,
    system,
)

R1, R2, R3, R4 = ("1" * 64, "2" * 64, "3" * 64, "4" * 64)


def _e(rec: str, **kw) -> dict:
    return {"uri": f"corpus://{rec}", "role": "authoritative-version", **kw}


def _errs(*entries: dict) -> list[str]:
    return read_roster({"artifacts": list(entries)}).errors


# ------------------------------------------------------------------ the roster stratum


def test_roster_reads_revisions_against_and_records() -> None:
    rr = read_roster({"artifacts": [
        _e(R1, expression="v2-1", revision="2-1-0"),
        _e(R2, expression="v2-1", revision="2-1-2", against="2-1-0"),
        {**_e(R2, expression="v2-1", revision="2-1-2"), "role": "landing-page"},
        _e(R3, expression="v2-2", revision="d2026-10-27", against="2-1-2"),
        _e(R4, expression="v2-2", revision="2-2-0", against="d2026-10-27"),
    ]})
    assert rr.errors == []
    assert rr.names == {"2-1-0", "2-1-2", "d2026-10-27", "2-2-0"}
    assert rr.expressions == {"v2-1", "v2-2"}
    assert rr.record_revision == {R1: "2-1-0", R2: "2-1-2", R3: "d2026-10-27", R4: "2-2-0"}
    assert rr.ancestors("2-2-0") == ["d2026-10-27", "2-1-2", "2-1-0"]
    assert rr.precedes("2-1-0", "2-2-0") and not rr.precedes("2-2-0", "2-1-0")
    assert rr.expression_of["d2026-10-27"] == "v2-2"


def test_sole_state_expression_names_its_revision() -> None:
    rr = read_roster({"artifacts": [_e(R1, expression="v1-3"),
                                    _e(R2, expression="v1-4", against="v1-3")]})
    assert rr.errors == []
    assert rr.record_revision == {R1: "v1-3", R2: "v1-4"}
    assert rr.against == {"v1-4": "v1-3"}


def test_unversioned_work_is_a_tag_chain() -> None:
    rr = read_roster({"artifacts": [
        _e(R1, revision="t2026-10-28T15:20Z"),
        _e(R2, revision="t2026-10-29T09:00", against="t2026-10-28T15:20Z"),
    ]})
    assert rr.errors == []
    assert rr.expression_of == {"t2026-10-28T15:20Z": None, "t2026-10-29T09:00": None}


def test_tag_grammar() -> None:
    assert any("is not a tag" in m for m in _errs(_e(R1, revision="2.1 draft")))
    assert any("is not a tag" in m for m in _errs(_e(R1, revision="v2-1/2-1-0")))
    assert _errs(_e(R1, revision="t2026-10-28T15:20+01:00")) == []


def test_tag_colliding_with_an_expression_slug() -> None:
    errs = _errs(_e(R1, expression="v2-1", revision="v2-2"), _e(R2, expression="v2-2"))
    assert any("collides with an expression slug" in m for m in errs)


def test_one_tag_under_two_expressions() -> None:
    errs = _errs(_e(R1, expression="v2-1", revision="r1"),
                 _e(R2, expression="v2-2", revision="r1"))
    assert any("appears under expressions" in m for m in errs)


def test_mixed_omission_within_an_expression() -> None:
    errs = _errs(_e(R1, expression="v2-1"), _e(R2, expression="v2-1", revision="2-1-2"))
    assert any("SOLE text state" in m for m in errs)


def test_record_witnesses_one_revision() -> None:
    errs = _errs(_e(R1, expression="v2-1", revision="2-1-0"),
                 {**_e(R1, expression="v2-1", revision="2-1-2"), "role": "landing-page"})
    assert any("disagreeing on (expression, revision)" in m for m in errs)


def test_against_must_agree_name_a_witnessed_revision_and_be_acyclic() -> None:
    assert any("disagree on `against`" in m for m in _errs(
        _e(R1, revision="a"), _e(R2, revision="b"),
        _e(R3, revision="c", against="a"),
        {**_e(R4, revision="c", against="b"), "role": "supporting"}))
    assert any("which no roster entry" in m for m in _errs(_e(R1, revision="a", against="z")))
    assert any("`against` itself" in m for m in _errs(_e(R1, revision="a", against="a")))
    assert any("cyclic" in m for m in _errs(_e(R1, revision="a", against="b"),
                                           _e(R2, revision="b", against="a")))
    assert any("naming no revision" in m for m in _errs(
        _e(R1, revision="a"), _e(R2, against="a")))


def test_entries_naming_no_revision_are_inert() -> None:
    """A landing page with neither field witnesses no revision; it is not an error."""
    rr = read_roster({"artifacts": [_e(R1, expression="v2-1", revision="2-1-0"),
                                    {"uri": f"corpus://{R2}", "role": "landing-page"}]})
    assert rr.errors == [] and R2 not in rr.record_revision


def test_check_reports_roster_revision_errors(system: Path) -> None:  # noqa: F811
    _fact(system, "ruleset", {
        "id": "std", "type": "ruleset", "name": "Std",
        "artifacts": [
            {"uri": f"corpus://{H_PUB}", "role": "authoritative-version",
             "expression": "v2-1", "revision": "2-1-0"},
            {"uri": f"corpus://{H_PUB2}", "role": "authoritative-version",
             "expression": "v2-1", "revision": "2-1-2", "against": "2-1-0"},
        ],
    })
    assert _check(system).errors == []
    _fact(system, "ruleset", {
        "id": "std", "type": "ruleset", "name": "Std",
        "artifacts": [
            {"uri": f"corpus://{H_PUB}", "role": "authoritative-version",
             "expression": "v2-1", "revision": "2-1-0"},
            {"uri": f"corpus://{H_PUB2}", "role": "authoritative-version",
             "expression": "v2-1", "revision": "2-1-2", "against": "2-0-9"},
        ],
    })
    assert any("which no roster entry" in e for e in _check(system).errors)


# ------------------------------------------------------------------ schema flags


def _schema(system: Path, body: str) -> None:  # noqa: F811
    d = system / "ledger" / "schemas"
    d.mkdir(exist_ok=True)
    (d / "ruleset.yaml").write_text(body, encoding="utf-8")


def test_schema_flags_admitted(system: Path) -> None:  # noqa: F811
    _schema(system, (
        "type: ruleset\n"
        "fields:\n"
        "  program-rule:\n    ranged: true\n"
        "  quantification-equation:\n    ranged: true\n    elements:\n"
        "      symbol: { verbatim: true }\n      ref: { locator: true }\n"
        "  versions:\n    expression_ledger: true\n"
    ))
    assert _check(system).errors == []


def test_schema_flag_conflicts(system: Path) -> None:  # noqa: F811
    _schema(system, (
        "type: ruleset\n"
        "fields:\n"
        "  a:\n    ranged: true\n    expression_ledger: true\n"
        "  b:\n    expression_ledger: true\n"
        "  c:\n    ranged: 'yes'\n    elements:\n"
        "      k: { verbatim: true, locator: true }\n"
    ))
    errs = _check(system).errors
    assert any("both ranged and the expression ledger" in e for e in errs)
    assert any("all declare expression_ledger" in e for e in errs)
    assert any("ranged must be a bool" in e for e in errs)
    assert any("both verbatim and a locator" in e for e in errs)


def test_expression_ledger_elements(system: Path) -> None:  # noqa: F811
    _schema(system, "type: ruleset\nfields:\n  versions:\n    expression_ledger: true\n")
    base = {
        "id": "std", "type": "ruleset", "name": "Std",
        "artifacts": [{"uri": f"corpus://{H_PUB}", "role": "authoritative-version",
                       "expression": "v2-1"}],
    }
    good = _claim("std", "versions", predicate="versions", value=[
        {"expression": "v2-1", "display": "2.1", "change_summary": "Adds EACs."}],
        evidence=[{"_record": H_BOTH, "kind": "direct", "element": 0}])
    _fact(system, "ruleset", {**base, "claims": [good]})
    assert _check(system).errors == []
    bad = _claim("std", "versions", predicate="versions", value=[
        {"display": "2.0"},
        {"expression": "v9-9"},
        {"expression": "v2-1", "change_summary": "derived"}],
        evidence=[{"_record": H_BOTH, "kind": "direct", "element": 0}])
    _fact(system, "ruleset", {**base, "claims": [bad]})
    errs = _check(system).errors
    assert any("element 0 names no `expression`" in e for e in errs)
    assert any("expression 'v9-9' is not rostered" in e for e in errs)
    assert any("element 2 change_summary carries no evidence" in e for e in errs)


# ------------------------------------------------------------------ stage 2: ranged claims

from ledger.ranged import (  # noqa: E402
    ATTESTED,
    CARRIED,
    PENDING,
    compute_holding,
    project,
    select_revision,
)
from tests.test_ledger_check import H_NO_STATUS  # noqa: E402

RANGED_SCHEMA = ("type: ruleset\nfields:\n  program-rule:\n    ranged: true\n"
                 "  versions:\n    expression_ledger: true\n")
# 2-1-0 → 2-1-2 (patch) → d2026-10-27 (draft of 2.2) → 2-2-0 (certified)
STD_ROSTER = [
    {"uri": f"corpus://{H_PUB}", "role": "authoritative-version",
     "expression": "v2-1", "revision": "2-1-0"},
    {"uri": f"corpus://{H_PUB2}", "role": "authoritative-version",
     "expression": "v2-1", "revision": "2-1-2", "against": "2-1-0"},
    {"uri": f"corpus://{H_BOTH}", "role": "authoritative-version",
     "expression": "v2-2", "revision": "d2026-10-27", "against": "2-1-2"},
    {"uri": f"corpus://{H_NO_STATUS}", "role": "authoritative-version",
     "expression": "v2-2", "revision": "2-2-0", "against": "d2026-10-27"},
]
STD_SOURCES = {"s1": {"record": H_PUB}, "s2": {"record": H_PUB2},
               "s3": {"record": H_BOTH}, "s5": {"record": H_NO_STATUS}}


def _ev(src: str, el: int, **kw) -> dict:
    return {"source": src, "element": el, "kind": "authoritative", **kw}


def _ranged_claim(**over) -> dict:
    """The spec §5.6 example in miniature: element 0 attested at 2-1-0 and the draft,
    carried at the two diffed revisions; 1 closed at 2-1-2 and replaced by 2; 3 new in
    the draft."""
    c = {
        "id": "std:program-rule", "predicate": "program-rule",
        "status": "provisional", "asof": "2026-10-28", "reasoning": "method only",
        "revisions": [
            {"revision": "2-1-0", "mode": "transcribed", "source": "s1",
             "status": "confirmed"},
            {"revision": "2-1-2", "against": "2-1-0", "mode": "diffed", "source": "s2",
             "status": "confirmed"},
            {"revision": "d2026-10-27", "against": "2-1-2", "mode": "transcribed",
             "source": "s3", "status": "provisional"},
            {"revision": "2-2-0", "against": "d2026-10-27", "mode": "diffed",
             "source": "s5", "status": "provisional"},
        ],
        "value": [{"rule": "flat fee"}, {"rule": "Projects disclose"},
                  {"rule": "Proponents disclose"}, {"rule": "three certificate types"}],
        "evidence": [
            _ev("s1", 0, quote="Credits", locators={"ref": "§1.2"}),
            _ev("s1", 1, quote="Projects"),
            _ev("s2", 2, quote="Proponents"),
            _ev("s3", 0, quote="Certificates", locators={"ref": "§1.3"}),
            _ev("s3", 2, quote="Proponents"),
            _ev("s3", 3, quote="EACs"),
        ],
        "closures": [{"element": 1, "revision": "2-1-2", "source": "s2",
                      "quote": "Proponents", "note": "obligated party changed",
                      "replaced_by": [2]}],
    }
    c.update(over)
    return c


def _std(system: Path, claim: dict, roster: list | None = None) -> None:  # noqa: F811
    _schema(system, RANGED_SCHEMA)
    _fact(system, "ruleset", {"id": "std", "type": "ruleset", "name": "Std",
                              "artifacts": roster or STD_ROSTER,
                              "sources": STD_SOURCES, "claims": [claim]})


def _fact_obj(claim: dict) -> dict:
    return {"artifacts": STD_ROSTER, "sources": STD_SOURCES, "claims": [claim]}


def test_holding_attested_carried_closed() -> None:
    fact = _fact_obj(_ranged_claim())
    h = compute_holding(fact["claims"][0], fact, read_roster(fact))
    assert h.modes["2-1-0"] == {0: ATTESTED, 1: ATTESTED}
    assert h.modes["2-1-2"] == {0: CARRIED, 2: ATTESTED}
    assert h.modes["d2026-10-27"] == {0: ATTESTED, 2: ATTESTED, 3: ATTESTED}
    assert h.modes["2-2-0"] == {0: CARRIED, 2: CARRIED, 3: CARRIED}


def test_projection_and_selection() -> None:
    fact = _fact_obj(_ranged_claim())
    rr = read_roster(fact)
    assert select_revision("v2-1", rr) == ("2-1-2", "")  # terminal of the expression
    assert select_revision("v2-2/d2026-10-27", rr) == ("d2026-10-27", "")
    assert select_revision("v2-2/2-1-0", rr)[0] is None
    assert select_revision("2-1-0", rr)[0] is None  # a versioned work takes @expression
    p, why = project(fact["claims"][0], fact, rr, "2-2-0")
    assert why == "" and p is not None
    assert sorted(p.elements) == [0, 2, 3]
    assert p.elements[0][0] == CARRIED and p.elements[0][2] == {"ref": "§1.3"}
    assert p.status == "provisional" and p.evidence == [] and p.closures == []
    assert p.through == ["2-2-0", "d2026-10-27"]
    p, _ = project(fact["claims"][0], fact, rr, "2-1-2")
    assert sorted(p.elements) == [0, 2] and p.elements[0][2] == {"ref": "§1.2"}
    assert [c["element"] for c in p.closures] == [1]
    assert project(fact["claims"][0], fact, rr, "nope")[0] is None


def test_folded_claim_checks_clean(system: Path) -> None:  # noqa: F811
    _std(system, _ranged_claim())
    assert _check(system).errors == []


def test_unfolded_claim_is_frontier_not_error(system: Path) -> None:  # noqa: F811
    _std(system, {"id": "std:program-rule-v2-1", "predicate": "program-rule",
                  "qualifiers": {"version": "2.1"}, "status": "provisional",
                  "asof": "2026-10-28", "value": [{"rule": "x"}],
                  "evidence": [_ev("s1", 0)]})
    rep = _check(system)
    assert rep.errors == []
    assert rep.counts.get("unfolded_claims") == 1


def test_completeness_under_transcribed(system: Path) -> None:  # noqa: F811
    c = _ranged_claim()
    c["evidence"] = [e for e in c["evidence"] if not (e["source"] == "s3"
                                                      and e["element"] == 2)]
    _std(system, c)
    errs = _check(system).errors
    assert any("'d2026-10-27' is `transcribed`" in e and "element(s) 2" in e for e in errs)


def test_migration_closure_keeps_holding_as_pending(system: Path) -> None:  # noqa: F811
    c = _ranged_claim()
    c["evidence"] = [e for e in c["evidence"] if not (e["source"] == "s3"
                                                      and e["element"] == 2)]
    c["closures"].append({"element": 2, "revision": "d2026-10-27", "source": "s3",
                          "note": "migration: unmatched", "basis": "migration"})
    _std(system, c)
    assert _check(system).errors == []
    fact = _fact_obj(c)
    h = compute_holding(c, fact, read_roster(fact))
    assert h.modes["d2026-10-27"][2] == PENDING
    assert h.modes["2-2-0"][2] == CARRIED


def test_status_must_be_the_weakest(system: Path) -> None:  # noqa: F811
    _std(system, _ranged_claim(status="confirmed"))
    assert any("must equal its weakest revision's, 'provisional'" in e
               for e in _check(system).errors)


def test_reconciliation_and_evidence_scoping(system: Path) -> None:  # noqa: F811
    c = _ranged_claim()
    c["revisions"][1] = {"revision": "2-1-2", "mode": "diffed", "source": "s1",
                         "status": "confirmed"}
    c["evidence"].append({"source": "s9", "element": 0, "kind": "direct"})
    _std(system, c)
    errs = _check(system).errors
    assert any("`diffed` with no `against`" in e for e in errs)
    assert any("source 's1' does not witness '2-1-2'" in e for e in errs)
    assert any("omits `against`, but the roster orders it after" in e for e in errs)


def test_unrostered_evidence_and_qualifier_ban(system: Path) -> None:  # noqa: F811
    roster = [*STD_ROSTER[:3]]  # 2-2-0's record is no longer rostered
    c = _ranged_claim(qualifiers={"version": "2.2"})
    c["revisions"] = c["revisions"][:3]
    c["evidence"].append(_ev("s5", 0))
    _std(system, c, roster)
    errs = _check(system).errors
    assert any("rostered at no revision of this fact" in e for e in errs)
    assert any("qualifier version='2.2'" in e for e in errs)


def test_closure_rules(system: Path) -> None:  # noqa: F811
    c = _ranged_claim()
    c["closures"] = [
        {"element": 0, "revision": "2-1-2", "source": "s1", "note": "x"},
        {"element": 3, "revision": "2-1-2", "source": "s2", "note": "x"},
        {"element": 2, "revision": "d2026-10-27", "source": "s3", "note": "x"},
        {"element": 1, "revision": "2-1-2", "source": "s2", "note": "x",
         "basis": "migration", "replaced_by": [9]},
    ]
    _std(system, c)
    errs = _check(system).errors
    assert any("closures[0] source 's1' does not witness" in e for e in errs)
    assert any("closures[1] closes element 3 at '2-1-2', but it does not hold" in e
               for e in errs)
    assert any("closures[2] closes element 2 at 'd2026-10-27', where evidence attests"
               in e for e in errs)
    assert any("closures[3] is a migration closure on a 'diffed'" in e for e in errs)
    assert any("closures[3] replaced_by 9 is out of range" in e for e in errs)


def test_per_revision_bar(system: Path) -> None:  # noqa: F811
    c = _ranged_claim()
    c["evidence"][2]["kind"] = "direct"  # element 2 at 2-1-2: one direct source
    _std(system, c)
    errs = _check(system).errors
    assert any("revision '2-1-2' is `confirmed` but fails" in e and "element(s) 2" in e
               for e in errs)


def test_ranged_keys_on_an_unranged_field(system: Path) -> None:  # noqa: F811
    _schema(system, "type: ruleset\nfields:\n  program-rule: {}\n")
    _fact(system, "ruleset", {"id": "std", "type": "ruleset", "name": "Std",
                              "artifacts": STD_ROSTER, "sources": STD_SOURCES,
                              "claims": [_ranged_claim()]})
    assert any("is not a ranged field" in e for e in _check(system).errors)


def _lineage_rows(system: Path, rows: dict) -> None:  # noqa: F811
    import json
    (system / "ledger" / "facts" / "LINEAGE.json").write_text(json.dumps(rows))


def test_ranged_lineage_rows(system: Path) -> None:  # noqa: F811
    _std(system, _ranged_claim())
    _lineage_rows(system, {"std:program-rule-v2-1": {
        "to": "std:program-rule", "reason": "ranged", "elements": {"0": 0, "1": 1},
        "projection": "v2-1", "qualifier": "2.1"}})
    assert _check(system).errors == []
    _lineage_rows(system, {
        "std:program-rule-v2-1": {"to": "std", "reason": "ranged"},
        "std:program-rule-v2-2": {"to": "std:program-rule", "reason": "ranged",
                                  "elements": {"0": 9, "x": 1}, "projection": "a/b/c"},
        "std:other": {"to": "std:program-rule", "reason": "split", "elements": {}},
    })
    errs = _check(system).errors
    assert any("must be the living ranged claim" in e for e in errs)
    assert any("projection 'a/b/c'" in e for e in errs)
    assert any("'0' → 9 is out of range" in e for e in errs)
    assert any("'x': 1 is not" in e for e in errs)
    assert any("'std:other' unknown keys ['elements']" in e for e in errs)


def test_element_pin_survives_a_new_revision() -> None:
    from ledger.ranged import challenge_state, stamp_revisions

    c = _ranged_claim()
    c["revisions"] = c["revisions"][:3]
    c["evidence"] = [e for e in c["evidence"] if e["source"] != "s3" or e["element"] != 0]
    c["closures"] = []
    fact = _fact_obj(c)
    ch = {"claim": c["id"], "element": 0, "revisions": stamp_revisions(c)}
    before = challenge_state(ch, c, fact)
    # a new revision attests element 0 again: the pin does not move
    c["evidence"].append(_ev("s5", 0, quote="again"))
    c["revisions"].append({"revision": "2-2-0", "against": "d2026-10-27",
                           "mode": "diffed", "source": "s5", "status": "provisional"})
    assert challenge_state(ch, c, fact) == before
    # an edit to an examined quote does
    c["evidence"][0]["quote"] = "edited"
    assert challenge_state(ch, c, fact) != before


def test_reference_resolution_through_a_ranged_row(system: Path) -> None:  # noqa: F811

    from ledger._cli import main as ledger_main
    from ledger.ranged import load_reference_context, resolve_reference

    _std(system, _ranged_claim())
    _lineage_rows(system, {
        "std:program-rule-v2-1": {"to": "std:program-rule", "reason": "ranged",
                                  "elements": {"0": 0, "1": 1, "5": 2},
                                  "projection": "v2-1", "qualifier": "2.1"},
        "std:program-rule-v2-2": {"to": "std:program-rule", "reason": "ranged",
                                  "elements": {"0": 3}, "projection": "v2-2/d2026-10-27",
                                  "qualifier": "2.2"}})
    ctx = load_reference_context(system / "ledger")

    def res(ref: str):
        return resolve_reference(ref, *ctx)

    r = res("ledger://std:program-rule-v2-1#5")  # → #2 at the terminal v2-1 revision
    assert r.error == "" and r.revision == "2-1-2" and r.element == 2
    assert res("std:program-rule-v2-1#7").error.startswith("#7 is not carried")
    assert "does not hold at '2-1-2'" in res("std:program-rule-v2-1#1").error  # closed
    r = res("std:program-rule-v2-2#0")
    assert r.revision == "d2026-10-27" and r.element == 3 and r.error == ""
    assert res("std:program-rule@v2-1/2-1-0#1").error == ""
    assert "has revisions" not in res("std:program-rule@v2-2").error
    assert res("std:program-rule@v2-2").revision == "2-2-0"
    assert "read through a projection" in res("std:program-rule").error
    assert ledger_main(["project", "std:program-rule@v2-1#0", "--root", str(system)]) == 0
    assert ledger_main(["project", "std:program-rule@v2-1#1", "--root", str(system)]) == 1
    assert ledger_main(["projections", "--json", "--root", str(system)]) == 0


def test_projections_table() -> None:
    from ledger.ranged import projection_table

    assert projection_table({
        "a:r-v1": {"to": "a:r", "reason": "ranged", "qualifier": "1.0", "projection": "v1-0"},
        "a:r-v2": {"to": "a:r", "reason": "ranged", "qualifier": "2.0", "projection": "v2-0"},
        "b:x": {"to": "c:x", "reason": "split"},
    }) == {"a": {"1.0": "v1-0", "2.0": "v2-0"}}


def test_projection_visibility_is_per_revision(system: Path) -> None:  # noqa: F811
    from ledger import tenancy
    from tests.test_ledger_check import H_PRIV, _join

    roster = [*STD_ROSTER[:2],
              {"uri": f"corpus://{H_PRIV}", "role": "authoritative-version",
               "expression": "v2-2", "revision": "d2026-10-27", "against": "2-1-2"}]
    c = _ranged_claim()
    c["revisions"] = c["revisions"][:3]
    fact = {"artifacts": roster, "claims": [c],
            "sources": {**STD_SOURCES, "s3": {"record": H_PRIV}}}
    join = _join(system)
    pub = frozenset({"public"})
    assert tenancy.projection_visible(c, fact, "2-1-2", join, {}, pub)
    assert not tenancy.projection_visible(c, fact, "d2026-10-27", join, {}, pub)
    assert not tenancy.claim_visible(c, fact["sources"], join, {}, pub)


def test_a_closure_quote_is_verified_like_evidence(tmp_path: Path) -> None:
    import json

    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger
    from tests.test_ledger_v47 import _SUMMARY_ADDR, RID, _statement

    def run(closure_quote: str):
        base = tmp_path / closure_quote.replace(" ", "_")
        root = _statement(base)
        ledger = base / "ledger"
        (ledger / "facts" / "doc").mkdir(parents=True)
        (ledger / "facts" / "doc" / "card.json").write_text(json.dumps({
            "id": "card", "type": "doc", "name": "Card",
            "sources": {"s1": {"record": RID}},
            "claims": [{
                "id": "card:terms", "predicate": "terms", "status": "confirmed",
                "asof": "2026-03-05", "value": [{"t": "a"}],
                "evidence": [{"source": "s1", "element": 0, "kind": "authoritative",
                              "anchor": _SUMMARY_ADDR, "quote": "New balance 92.18"}],
                "closures": [{"element": 0, "revision": "r", "source": "s1",
                              "anchor": _SUMMARY_ADDR, "quote": closure_quote,
                              "note": "x"}],
            }],
        }))
        join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
        return verify_ledger(ledger, join, {}, stamp=False)

    ok = run("due Apr 01")
    assert ok.errors == [] and ok.verified == 2
    bad = run("not printed anywhere")
    assert len(bad.errors) == 1


def test_each_fact_is_checked_against_its_own_roster(system: Path) -> None:  # noqa: F811
    """Regression (dev-corpus, 2026-10-29): the claims pass read the roster of the LAST
    fact the fact-file pass visited, so a folded claim on any other fact failed every
    revision and source check."""
    _std(system, _ranged_claim())
    # a second fact, iterated after `std`, with a roster of its own
    _fact(system, "ruleset", {"id": "zz-other", "type": "ruleset", "name": "Other",
                              "artifacts": [{"uri": f"corpus://{H_PUB}",
                                             "role": "documents",
                                             "revision": "v2026-10-22"}]})
    assert _check(system).errors == []
