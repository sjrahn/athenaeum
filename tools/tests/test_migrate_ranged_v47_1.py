"""v47.1 `ath ledger migrate-ranged`: fold version-split claims into one ranged claim.

The synthetic work mirrors `isometric--standard`'s shapes:
- `-v2-1` spans 2-1-0 and the patch-2.1.2 recapture, with a prose "Superseded at patch"
  marker;
- `-v2-2` (the draft) carries authored identity notes;
- `-v2-2-0` (the certified text) is a fresh transcription the classifier matches.
"""

from __future__ import annotations

import json
from pathlib import Path

from ledger._cli import main as ledger_main
from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.migrate_ranged import apply_fold, plan_fold
from ledger.ranged import (
    ATTESTED,
    PENDING,
    compute_holding,
    load_reference_context,
    read_roster,
    resolve_reference,
)
from tests.test_ledger_check import (  # noqa: F401 — `system` is a fixture
    H_BOTH,
    H_NO_STATUS,
    H_PUB,
    H_PUB2,
    _check,
    _fact,
    system,
)

ROSTER = [
    {"uri": f"corpus://{H_PUB}", "role": "authoritative-version",
     "expression": "v2-1", "revision": "2-1-0"},
    {"uri": f"corpus://{H_PUB2}", "role": "authoritative-version",
     "expression": "v2-1", "revision": "2-1-2", "against": "2-1-0"},
    {"uri": f"corpus://{H_BOTH}", "role": "authoritative-version",
     "expression": "v2-2", "revision": "d2026-10-27", "against": "2-1-2"},
    {"uri": f"corpus://{H_NO_STATUS}", "role": "authoritative-version",
     "expression": "v2-2", "revision": "2-2-0", "against": "d2026-10-27"},
]
SOURCES = {"s1": {"record": H_PUB}, "s2": {"record": H_PUB2},
           "s3": {"record": H_BOTH}, "s5": {"record": H_NO_STATUS}}
SCHEMA = ("type: ruleset\nfields:\n  program-rule:\n    ranged: true\n    elements:\n"
          "      value: { verbatim: true }\n      ref: { locator: true }\n")


def _el(rule: str, note: str, **kw) -> dict:
    return {"rule": rule, "note": note, **kw}


def _ev(src: str, i: int, quote: str, note: str = "") -> dict:
    e = {"source": src, "element": i, "kind": "authoritative", "quote": quote}
    if note:
        e["note"] = note
    return e


def _claims() -> list[dict]:
    v21 = {
        "id": "std:program-rule-v2-1", "predicate": "program-rule",
        "qualifiers": {"version": "2.1"}, "status": "confirmed", "asof": "2026-10-27",
        "reasoning": "one element per rule",
        "value": [
            _el("flat fee", "§1.2 Principles, el=964", value="10", ref="§1.2"),
            _el("Projects disclose", "§5.7 Hopping, el=4204"),
            _el("Projects disclose audits",
                "§5.7 Hopping, el=4204; Superseded at patch 2.1.2 by element 4."),
            _el("annual report", "§6 Reports, el=5000"),
            _el("Proponents disclose audits", "§5.7 Hopping, el=4402; new at patch 2.1.2"),
        ],
        "evidence": [
            _ev("s1", 0, "the number of Credits", "§1.2 Principles, el=964"),
            _ev("s1", 1, "Projects disclose", "§5.7 Hopping, el=4204"),
            _ev("s1", 2, "Projects disclose audits", "§5.7 Hopping, el=4204"),
            _ev("s1", 3, "annual report", "§6 Reports, el=5000"),
            _ev("s2", 4, "Proponents disclose audits", "§5.7 Hopping, el=4402"),
        ],
    }
    v22 = {
        "id": "std:program-rule-v2-2", "predicate": "program-rule",
        "qualifiers": {"version": "2.2"}, "status": "provisional", "asof": "2026-10-27",
        "reasoning": "draft transcription",
        "value": [
            _el("flat fee", "§1.2 Principles, el=[1-9]; as v2.1 element 0", value="10"),
            _el("Projects shall disclose", "§5.8, el=[10-12]; changed from v2.1 element 1: "
                "modal tightened"),
            _el("EAC certificates", "§2.1, el=[20-22]; new in v2.2"),
            _el("Proponents disclose audits", "§5.8, el=[13-14]; as v2.1 element 4"),
        ],
        "evidence": [
            _ev("s3", 0, "the number of Certificates", "§1.2 Principles, el=[1-9]"),
            _ev("s3", 1, "Projects shall disclose", "§5.8, el=[10-12]"),
            _ev("s3", 2, "EAC certificates", "§2.1, el=[20-22]"),
            _ev("s3", 3, "Proponents disclose audits", "§5.8, el=[13-14]"),
        ],
    }
    v220 = {
        "id": "std:program-rule-v2-2-0", "predicate": "program-rule",
        "qualifiers": {"version": "2.2.0"}, "status": "provisional", "asof": "2026-10-28",
        "reasoning": "certified transcription",
        "value": [
            _el("flat fee", "§1.2, el=7", value="10"),             # auto-merge with #0
            _el("Projects must disclose", "§5.8, el=9"),           # quote-equal only
            _el("Proponents disclose audits", "§5.8, el=11"),      # value-equal only
        ],
        "evidence": [
            _ev("s5", 0, "the number of Certificates"),
            _ev("s5", 1, "Projects shall disclose"),
            _ev("s5", 2, "Proponents must disclose audits"),
        ],
    }
    return [v21, v22, v220]


def _setup(system: Path, claims: list[dict] | None = None, roster=None) -> Path:  # noqa: F811
    (system / "ledger" / "schemas").mkdir(exist_ok=True)
    (system / "ledger" / "schemas" / "ruleset.yaml").write_text(SCHEMA)
    _fact(system, "ruleset", {"id": "std", "type": "ruleset", "name": "Std",
                              "artifacts": roster or ROSTER, "sources": SOURCES,
                              "claims": claims if claims is not None else _claims()})
    return system / "ledger"


def test_fold_plans_clean_and_checks(system: Path) -> None:  # noqa: F811
    ledger = _setup(system)
    assert _check(system).errors == []  # three unfolded claims: frontier only
    plan = plan_fold(ledger, "std", "program-rule")
    assert plan["errors"] == []
    c = plan["claim"]
    assert c["id"] == "std:program-rule" and "qualifiers" not in c
    assert [r["revision"] for r in c["revisions"]] == ["2-1-0", "2-1-2", "d2026-10-27",
                                                      "2-2-0"]
    assert [r["mode"] for r in c["revisions"]] == ["transcribed", "diffed", "transcribed",
                                                  "transcribed"]
    assert c["status"] == "provisional"
    # the oldest claim keeps its indices; the draft maps by its notes
    assert plan["rows"]["std:program-rule-v2-1"]["elements"] == {str(i): i for i in range(5)}
    assert plan["rows"]["std:program-rule-v2-2"]["elements"] == {"0": 0, "1": 5, "2": 6,
                                                                "3": 4}
    assert plan["rows"]["std:program-rule-v2-2-0"]["elements"] == {"0": 0, "1": 7, "2": 8}
    assert plan["rows"]["std:program-rule-v2-1"]["projection"] == "v2-1/2-1-2"
    assert plan["rows"]["std:program-rule-v2-2"]["projection"] == "v2-2/d2026-10-27"
    assert plan["rows"]["std:program-rule-v2-2-0"]["qualifier"] == "2.2.0"
    closures = {(cl["element"], cl["revision"]): cl for cl in c["closures"]}
    assert closures[(2, "2-1-2")]["replaced_by"] == [4]                # prose marker
    assert closures[(1, "d2026-10-27")]["replaced_by"] == [5]          # changed from
    assert "basis" not in closures[(3, "d2026-10-27")]                 # authored absence
    assert closures[(5, "2-2-0")]["basis"] == "migration"              # unmatched
    assert plan["report"]["auto_merge"] == 1
    assert len(plan["report"]["adjudicate"]) == 2
    # locators moved onto evidence; consumed note parts dropped, nothing else lost
    assert "ref" not in c["value"][0] and "note" not in c["value"][0]
    assert all(e.get("locators") == {"ref": "§1.2"} for e in c["evidence"]
               if e["element"] == 0 and e["source"] == "s1")
    fact = {"artifacts": ROSTER, "sources": SOURCES, "claims": [c]}
    h = compute_holding(c, fact, read_roster(fact))
    assert h.modes["2-2-0"][0] == ATTESTED and h.modes["2-2-0"][5] == PENDING
    assert 1 not in h.modes["d2026-10-27"] and 3 not in h.modes["d2026-10-27"]


def test_byte_invariant_holds_for_every_row(system: Path) -> None:  # noqa: F811
    ledger = _setup(system)
    plan = plan_fold(ledger, "std", "program-rule")
    olds = {c["id"]: c for c in _claims()}
    for cid, row in plan["rows"].items():
        for old, new in row["elements"].items():
            o, n = olds[cid]["value"][int(old)], plan["claim"]["value"][new]
            assert o.get("value") == n.get("value"), (cid, old, new)


def test_apply_writes_behind_the_gate_and_refs_resolve(system: Path) -> None:  # noqa: F811
    ledger = _setup(system)
    plan = plan_fold(ledger, "std", "program-rule")
    apply_fold(ledger, plan, CorpusJoin([]), {})
    fact = json.loads((ledger / "facts" / "ruleset" / "std.json").read_text())
    assert [c["id"] for c in fact["claims"]] == ["std:program-rule"]
    rows = json.loads((ledger / "facts" / "LINEAGE.json").read_text())
    assert rows["std:program-rule-v2-2"]["reason"] == "ranged"
    assert run_check(ledger, CorpusJoin([]), {}, no_corpus=True).errors == []
    ctx = load_reference_context(ledger)
    r = resolve_reference("ledger://std:program-rule-v2-2#3", *ctx)
    assert r.error == "" and r.revision == "d2026-10-27" and r.element == 4
    r = resolve_reference("std:program-rule-v2-1#2", *ctx)  # superseded at the patch
    assert "does not hold at '2-1-2'" in r.error
    assert ledger_main(["projections", "--json", "--root", str(system)]) == 0


def test_refusals(system: Path) -> None:  # noqa: F811
    ledger = _setup(system, roster=ROSTER[:3])  # 2-2-0's record unrostered
    plan = plan_fold(ledger, "std", "program-rule")
    assert any("rostered at no revision" in e for e in plan["errors"])
    ledger = _setup(system)
    (ledger / "schemas" / "ruleset.yaml").write_text("type: ruleset\nfields: {}\n")
    assert any("not declared `ranged: true`" in e
               for e in plan_fold(ledger, "std", "program-rule")["errors"])


def test_cli_dry_run_and_report(system: Path, tmp_path: Path) -> None:  # noqa: F811
    _setup(system)
    report = tmp_path / "fold.json"
    assert ledger_main(["migrate-ranged", "std", "program-rule", "--root", str(system),
                        "--report", str(report)]) == 0
    doc = json.loads(report.read_text())
    assert doc["projections"] == {"2.1": "v2-1/2-1-2", "2.2": "v2-2/d2026-10-27",
                                  "2.2.0": "v2-2/2-2-0"}
    # dry run: nothing written
    fact = json.loads((system / "ledger" / "facts" / "ruleset" / "std.json").read_text())
    assert len(fact["claims"]) == 3


def test_revision_diff_is_derived(system: Path) -> None:  # noqa: F811
    from ledger.ranged import revision_diff

    ledger = _setup(system)
    plan = plan_fold(ledger, "std", "program-rule")
    c = plan["claim"]
    fact = {"artifacts": ROSTER, "sources": SOURCES, "claims": [c]}
    d = revision_diff(c, fact, read_roster(fact), "2-1-2", "d2026-10-27")
    assert d["opened"] == [5, 6]
    assert [x["element"] for x in d["closed"]] == [1, 3]
    assert d["kept"] == [0, 4]
    apply_fold(ledger, plan, CorpusJoin([]), {})
    assert ledger_main(["revision-diff", "std:program-rule", "d2026-10-27", "2-2-0",
                        "--root", str(system)]) == 0


def test_carry_reanchors_unchanged_quotes(tmp_path: Path) -> None:
    from ledger.carry import apply_carry, plan_carry
    from ledger.corpora import RegisteredCorpus
    from tests.test_ledger_v47 import RID, _statement

    root = _statement(tmp_path)
    old = "6" * 64
    ledger = tmp_path / "ledger"
    (ledger / "facts" / "doc").mkdir(parents=True)
    (ledger / "schemas").mkdir()
    (ledger / "schemas" / "doc.yaml").write_text("type: doc\nfields:\n  terms:\n"
                                                 "    ranged: true\n")
    fact = {
        "id": "card", "type": "doc", "name": "Card",
        "artifacts": [{"uri": f"corpus://{old}", "role": "documents", "revision": "r1"},
                      {"uri": f"corpus://{RID}", "role": "documents", "revision": "r2",
                       "against": "r1"}],
        "sources": {"s1": {"record": old}, "s2": {"record": RID}},
        "claims": [{
            "id": "card:terms", "predicate": "terms", "status": "provisional",
            "asof": "2026-03-05", "value": [{"t": "balance"}, {"t": "gone"}],
            "revisions": [
                {"revision": "r1", "mode": "transcribed", "source": "s1",
                 "status": "provisional"},
                {"revision": "r2", "against": "r1", "mode": "diffed", "source": "s2",
                 "status": "provisional"}],
            "evidence": [
                {"source": "s1", "element": 0, "kind": "direct",
                 "quote": "New balance 92.18"},
                {"source": "s1", "element": 1, "kind": "direct",
                 "quote": "printed nowhere in r2"}],
        }],
    }
    (ledger / "facts" / "doc" / "card.json").write_text(json.dumps(fact))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    plan = plan_carry(ledger, join, "card:terms", "r2")
    assert plan["errors"] == []
    # the anchor is the stored address in verify's canonical spelling: it resolves
    # exactly as the stored one does
    assert plan["carried"] == [{"element": 0, "anchor": "page=1&bbox=0.0,0.1,1.0,0.2"}]
    assert [a["element"] for a in plan["to_author"]] == [1]
    apply_carry(ledger, plan)
    c = json.loads((ledger / "facts" / "doc" / "card.json").read_text())["claims"][0]
    f2 = {**fact, "claims": [c]}
    h = compute_holding(c, f2, read_roster(f2))
    assert h.modes["r2"] == {0: ATTESTED, 1: "carried"}
