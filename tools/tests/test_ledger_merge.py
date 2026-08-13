"""The merge verb — `ath ledger merge` (#176, spec/ledger.md §4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.merge import MergeError, apply_merge, plan_merge
from ledger.model import canonical_claim_state

H1 = "a" * 64
H2 = "b" * 64


def _fact(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _interp(root: Path, obj: dict) -> Path:
    p = root / "interpretations" / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _lineage(root: Path, mapping: dict[str, str]) -> Path:
    p = root / "facts" / "LINEAGE.json"
    existing = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    existing.update(mapping)
    p.write_text(json.dumps(existing, indent=1), encoding="utf-8")
    return p


def _read(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def _claim_by_id(fact: dict, cid: str) -> dict:
    return next(c for c in fact["claims"] if c["id"] == cid)


def _snapshot(root: Path) -> dict[str, str]:
    """Every fact/interp/lineage file's raw bytes, for a dry-run identity check."""
    out = {}
    for pattern in ("facts/**/*.json", "interpretations/**/*.json"):
        for p in root.glob(pattern):
            out[str(p.relative_to(root))] = p.read_text(encoding="utf-8")
    return out


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    return tmp_path


# ---------------------------------------------------------------- happy path


def test_happy_merge_end_to_end(ledger: Path) -> None:
    _fact(ledger, "part", {
        "id": "bcm", "type": "part", "name": "Body Control Module",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "bcm:price", "predicate": "price", "value": "50",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    })
    _fact(ledger, "part", {
        "id": "bcm-old", "type": "part", "name": "BCM Old", "aliases": ["BCM"],
        "sources": {"s1": {"record": H2}},
        "claims": [{"id": "bcm-old:weight", "predicate": "weight", "value": "2kg",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    })
    _fact(ledger, "part", {
        "id": "harness", "type": "part", "name": "Harness",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "harness:connects", "predicate": "connects_to",
                    "object": "bcm-old", "value": "see [[bcm-old]] for pinout",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    })
    _fact(ledger, "event", {
        "id": "install", "type": "event", "name": "Install",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "install:parts", "predicate": "parts",
                    "value": [{"entity": "bcm-old", "role": "installed"}],
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    })
    _interp(ledger, {
        "id": "bcm-old-note", "kind": "assessment", "about": ["bcm-old"],
        "statement": "worth a closer look", "reasoning": "…",
        "based_on": ["bcm-old:weight"], "status": "standing", "asof": "2026-01-01",
    })

    plan = plan_merge(ledger, None, "bcm-old", "bcm")
    assert plan["errors"] == []
    apply_merge(ledger, plan)

    assert not (ledger / "facts" / "part" / "bcm-old.json").exists()
    bcm = _read(ledger, "facts/part/bcm.json")
    assert {c["id"] for c in bcm["claims"]} == {"bcm:price", "bcm:weight"}
    assert "BCM Old" in bcm["aliases"] and "BCM" in bcm["aliases"]
    weight = _claim_by_id(bcm, "bcm:weight")
    # the loser's source (a distinct hash) landed under a fresh key, remapped
    assert bcm["sources"][weight["evidence"][0]["source"]]["record"] == H2

    harness = _read(ledger, "facts/part/harness.json")
    hc = harness["claims"][0]
    assert hc["object"] == "bcm"
    assert hc["value"] == "see [[bcm]] for pinout"

    install = _read(ledger, "facts/event/install.json")
    assert install["claims"][0]["value"][0]["entity"] == "bcm"

    note = _read(ledger, "interpretations/bcm-old-note.json")
    assert note["about"] == ["bcm"]
    assert note["based_on"] == ["bcm:weight"]

    lineage = _read(ledger, "facts/LINEAGE.json")
    assert lineage == {"bcm-old": "bcm"}

    from ledger.check import run_check
    from ledger.corpora import CorpusJoin
    rep = run_check(ledger, CorpusJoin([]), set(), no_corpus=True)
    assert rep.ok, rep.errors


# -------------------------------------------------------------- collisions


def test_short_collision_renamed_and_surfaced(ledger: Path) -> None:
    _fact(ledger, "part", {
        "id": "bcm", "type": "part", "name": "BCM",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "bcm:weight", "predicate": "weight", "value": "1kg",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    })
    _fact(ledger, "part", {
        "id": "bcm-old", "type": "part", "name": "BCM Old",
        "sources": {"s1": {"record": H2}},
        "claims": [{"id": "bcm-old:weight", "predicate": "weight", "value": "2kg",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    })
    plan = plan_merge(ledger, None, "bcm-old", "bcm")
    assert plan["errors"] == []
    assert plan["claim_renames"] == [{"old": "bcm-old:weight", "new": "bcm:weight-2"}]
    assert {"old": "bcm-old:weight", "new": "bcm:weight-2"} in plan["claims_moved"]

    apply_merge(ledger, plan)
    bcm = _read(ledger, "facts/part/bcm.json")
    assert {c["id"] for c in bcm["claims"]} == {"bcm:weight", "bcm:weight-2"}


# ---------------------------------------------------------------- lineage


def test_existing_lineage_row_retargeted(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "b", "type": "part", "name": "B"})
    _fact(ledger, "part", {"id": "c", "type": "part", "name": "C"})
    _lineage(ledger, {"a-old": "b"})

    plan = plan_merge(ledger, None, "b", "c")
    assert plan["errors"] == []
    assert plan["lineage_retargeted"] == [
        {"key": "a-old", "old_target": "b", "new_target": "c"}
    ]
    apply_merge(ledger, plan)
    lineage = _read(ledger, "facts/LINEAGE.json")
    assert lineage == {"a-old": "c", "b": "c"}


# ---------------------------------------------------------------- refusals


def test_cross_type_merge_refused(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "widget", "type": "part", "name": "Widget"})
    _fact(ledger, "vehicle", {"id": "car", "type": "vehicle", "name": "Car"})
    plan = plan_merge(ledger, None, "widget", "car")
    assert any("cross-type merge" in e for e in plan["errors"])
    with pytest.raises(MergeError):
        apply_merge(ledger, plan)


def test_interpretation_refused(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "widget", "type": "part", "name": "Widget"})
    _interp(ledger, {
        "id": "some-hypothesis", "kind": "hypothesis", "about": ["widget"],
        "statement": "…", "confidence": "plausible", "based_on": [f"corpus://{H1}"],
        "status": "open", "asof": "2026-01-01",
    })
    plan = plan_merge(ledger, None, "some-hypothesis", "widget")
    assert any("is an interpretation" in e for e in plan["errors"])


# ---------------------------------------------------------------- dry run


def test_dry_run_writes_nothing(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    _fact(ledger, "part", {"id": "bcm-old", "type": "part", "name": "BCM Old"})
    before = _snapshot(ledger)
    plan = plan_merge(ledger, None, "bcm-old", "bcm")
    assert plan["errors"] == []
    after = _snapshot(ledger)
    assert before == after
    assert not (ledger / "facts" / "LINEAGE.json").exists()


# -------------------------------------------------------------- sources


def test_sources_same_target_unification_remaps_evidence(ledger: Path) -> None:
    _fact(ledger, "part", {
        "id": "bcm", "type": "part", "name": "BCM",
        "sources": {"s1": {"record": H1, "verified": {"touch": "survivor-touch"}}},
        "claims": [],
    })
    _fact(ledger, "part", {
        "id": "bcm-old", "type": "part", "name": "BCM Old",
        "sources": {"s5": {"record": H1, "verified": {"touch": "loser-touch"}}},
        "claims": [{"id": "bcm-old:weight", "predicate": "weight", "value": "2kg",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s5", "kind": "direct"}]}],
    })
    plan = plan_merge(ledger, None, "bcm-old", "bcm")
    assert plan["errors"] == []
    assert plan["sources_unified"] == [
        {"loser_key": "s5", "survivor_key": "s1", "target": f"record:{H1}",
         "note": "verified binding differs — kept the existing entry's stamp"}
    ]
    apply_merge(ledger, plan)
    bcm = _read(ledger, "facts/part/bcm.json")
    assert list(bcm["sources"].keys()) == ["s1"]
    assert bcm["sources"]["s1"]["verified"]["touch"] == "survivor-touch"
    weight = _claim_by_id(bcm, "bcm:weight")
    assert weight["evidence"][0]["source"] == "s1"


# ----------------------------------------------------------- sensitivity


def test_sensitivity_upward_only(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    _fact(ledger, "part", {"id": "bcm-old", "type": "part", "name": "BCM Old",
                           "sensitivity": "private"})
    plan = plan_merge(ledger, None, "bcm-old", "bcm")
    assert plan["errors"] == []
    assert plan["sensitivity"]
    apply_merge(ledger, plan)
    bcm = _read(ledger, "facts/part/bcm.json")
    assert bcm["sensitivity"] == "private"


# --------------------------------------------------------- challenges pin


def test_challenges_claim_rewritten_and_repinned(ledger: Path) -> None:
    old_claim = {"id": "widget-old:spec", "predicate": "spec", "value": "5mm",
                "status": "disputed", "asof": "2026-01-01",
                "evidence": [{"source": "s1", "kind": "direct"}]}
    old_sources = {"s1": {"record": H1}}
    old_state = canonical_claim_state(old_claim, old_sources)

    _fact(ledger, "widget", {"id": "widget", "type": "widget", "name": "Widget",
                             "claims": []})
    _fact(ledger, "widget", {
        "id": "widget-old", "type": "widget", "name": "Widget Old",
        "sources": old_sources, "claims": [old_claim],
    })
    _interp(ledger, {
        "id": "widget-old-wrong", "kind": "correction", "about": ["widget-old"],
        "statement": "5mm is wrong", "reasoning": "measured 6mm",
        "based_on": [f"corpus://{H1}"],
        "challenges": {"claim": "widget-old:spec", "state": old_state},
        "status": "standing", "asof": "2026-01-01",
    })

    plan = plan_merge(ledger, None, "widget-old", "widget")
    assert plan["errors"] == []
    assert plan["challenges_repinned"]
    row = plan["challenges_repinned"][0]
    assert row["claim"] == "widget:spec"
    assert row["old_state"] == old_state
    assert row["new_state"] != old_state

    apply_merge(ledger, plan)
    widget = _read(ledger, "facts/widget/widget.json")
    new_claim = _claim_by_id(widget, "widget:spec")
    assert new_claim["status"] == "disputed"
    correction = _read(ledger, "interpretations/widget-old-wrong.json")
    assert correction["challenges"]["claim"] == "widget:spec"
    assert correction["challenges"]["state"] == canonical_claim_state(
        new_claim, widget.get("sources", {})
    )
    assert correction["challenges"]["state"] == row["new_state"]

    from ledger.check import run_check
    from ledger.corpora import CorpusJoin
    rep = run_check(ledger, CorpusJoin([]), set(), no_corpus=True)
    assert rep.ok, rep.errors
