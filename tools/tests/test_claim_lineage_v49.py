"""Claim-grain lineage rows (spec/ledger.md §4.1, v49; owner ruling 2026-09-28, codex-steven
R-0057).

A claim may leave a file that lives on — a `card_transaction` claim becoming its own
`transaction` fact (R-0055), or a claim re-keyed onto a sibling series concept (R-0001). Its
old id retires into `facts/LINEAGE.json` as its own key, `"file:short" → {to: fact[:short],
reason: split|rekeyed}`. The key resolves before the file-grain row, one hop only, and stays
occupied forever. `ath ledger move-claim` performs the move.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.merge import apply_merge, plan_merge
from ledger.model import (
    load_claim_lineage_rows,
    load_lineage,
    load_lineage_rows,
    resolve_claim_ref,
)
from ledger.moveclaim import MoveError, apply_move, apply_moves, plan_move, preview_moves
from ledger.worklist import worklist

H1 = "a" * 64
H2 = "b" * 64


def _fact(root: Path, type_: str, obj: dict) -> None:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _read(root: Path, type_: str, fid: str) -> dict:
    return json.loads((root / "facts" / type_ / f"{fid}.json").read_text(encoding="utf-8"))


def _claim(fid: str, short: str, source: str = "s1", **over) -> dict:
    return {"id": f"{fid}:{short}", "predicate": short.replace("-", "_"), "value": "x",
            "status": "provisional", "asof": "2026-01-01",
            "evidence": [{"source": source, "kind": "direct"}], **over}


def _rows(root: Path, rows: dict) -> None:
    (root / "facts" / "LINEAGE.json").write_text(json.dumps(rows), encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return run_check(root, CorpusJoin([]), {}, no_corpus=True).errors


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    _fact(tmp_path, "account-ledger", {
        "id": "visa-ledger", "type": "account-ledger", "name": "Visa ledger",
        "sources": {"s1": {"record": H1}, "s2": {"record": H2}},
        "claims": [_claim("visa-ledger", "txn-0304"),
                   _claim("visa-ledger", "txn-0305", source="s2")],
    })
    _fact(tmp_path, "transaction", {
        "id": "safeway-2026-03-04", "type": "transaction", "name": "Safeway, Mar 4",
        "sources": {"s1": {"record": H2}},
        "claims": [_claim("safeway-2026-03-04", "amount")],
    })
    return tmp_path


# ---------- the row shape ---------- #


def test_claim_rows_parse_apart_from_file_rows_with_their_own_reasons(ledger):
    _rows(ledger, {
        "old-concept": {"to": "visa-ledger", "reason": "merged"},
        "visa-ledger:txn-0101": {"to": "safeway-2026-03-04", "reason": "split"},
        "visa-ledger:txn-0102": {"to": "safeway-2026-03-04:amount", "reason": "rekeyed"},
        "visa-ledger:txn-0103": {"to": "safeway-2026-03-04", "reason": "merged"},
        "old-2": {"to": "visa-ledger", "reason": "split"},
    })
    rows, errors = load_lineage_rows(ledger)
    assert set(rows) == {"old-concept"}  # the fact-id map never sees a claim key
    assert set(load_claim_lineage_rows(ledger)) == {"visa-ledger:txn-0101",
                                                    "visa-ledger:txn-0102"}
    assert any("txn-0103" in e and "claim-grain row" in e for e in errors)
    assert any("'old-2'" in e and "file-grain row" in e for e in errors)


def test_a_claim_row_resolves_before_its_files_row_one_hop():
    claim_lineage = {"old:a": "new-fact"}
    lineage = {"old": "survivor"}
    assert resolve_claim_ref("old:a", claim_lineage, lineage) == "new-fact"
    assert resolve_claim_ref("old:b", claim_lineage, lineage) == "survivor:b"
    assert resolve_claim_ref("live:c", claim_lineage, lineage) == "live:c"


# ---------- check ---------- #


def test_check_holds_a_claim_row_to_the_occupancy_and_one_hop_rules(ledger):
    _rows(ledger, {"visa-ledger:txn-0101": {"to": "safeway-2026-03-04", "reason": "split"}})
    assert _errors(ledger) == []

    _rows(ledger, {
        "visa-ledger:txn-0304": {"to": "safeway-2026-03-04", "reason": "split"},  # living
        "visa-ledger:txn-0101": {"to": "nowhere", "reason": "split"},
        "visa-ledger:txn-0102": {"to": "safeway-2026-03-04:gone", "reason": "split"},
        "visa-ledger:txn-0103": {"to": "visa-ledger:txn-0101", "reason": "split"},  # chain
    })
    errors = " | ".join(_errors(ledger))
    assert "collides with a living claim" in errors
    assert "'nowhere' does not exist" in errors
    assert "no living claim 'safeway-2026-03-04:gone'" in errors
    assert "is itself retired" in errors


# ---------- move-claim ---------- #


def test_moving_a_claim_to_a_claim_id_rehoists_sources_and_rewrites_references(ledger):
    (ledger / "interpretations" / "note.json").write_text(json.dumps({
        "id": "note", "kind": "assessment", "status": "standing", "about": ["visa-ledger"],
        "statement": "s", "based_on": ["visa-ledger:txn-0305"], "asof": "2026-01-01",
    }), encoding="utf-8")
    plan = plan_move(ledger, "visa-ledger:txn-0305", "safeway-2026-03-04:card-charge",
                     "split")
    assert plan["errors"] == []
    apply_move(ledger, plan)

    src = _read(ledger, "account-ledger", "visa-ledger")
    assert [c["id"] for c in src["claims"]] == ["visa-ledger:txn-0304"]
    assert set(src["sources"]) == {"s1"}  # s2 left with the only claim citing it
    dest = _read(ledger, "transaction", "safeway-2026-03-04")
    moved = next(c for c in dest["claims"] if c["id"] == "safeway-2026-03-04:card-charge")
    assert dest["sources"][moved["evidence"][0]["source"]] == {"record": H2}  # reused s1
    note = json.loads((ledger / "interpretations" / "note.json").read_text())
    assert note["based_on"] == ["safeway-2026-03-04:card-charge"]
    assert load_claim_lineage_rows(ledger) == {
        "visa-ledger:txn-0305": {"to": "safeway-2026-03-04:card-charge", "reason": "split"}}
    assert _errors(ledger) == []
    assert worklist(ledger, "visa-ledger:txn-0305") == [
        "retired visa-ledger:txn-0305 → safeway-2026-03-04:card-charge "
        "(split, facts/LINEAGE.json)"]


def test_a_claim_that_became_a_fact_lands_nowhere_and_refuses_a_live_citation(ledger):
    (ledger / "interpretations" / "note.json").write_text(json.dumps({
        "id": "note", "kind": "assessment", "status": "standing", "about": ["visa-ledger"],
        "statement": "s", "based_on": ["visa-ledger:txn-0304"], "asof": "2026-01-01",
    }), encoding="utf-8")
    plan = plan_move(ledger, "visa-ledger:txn-0304", "safeway-2026-03-04", "split")
    assert any("based_on names" in e for e in plan["errors"])

    (ledger / "interpretations" / "note.json").unlink()
    plan = plan_move(ledger, "visa-ledger:txn-0304", "safeway-2026-03-04", "split")
    assert plan["errors"] == [] and any("NOT carried" in w for w in plan["warnings"])
    apply_move(ledger, plan)
    src = _read(ledger, "account-ledger", "visa-ledger")
    assert [c["id"] for c in src["claims"]] == ["visa-ledger:txn-0305"]
    assert _errors(ledger) == []


def test_a_move_refuses_an_occupied_destination(ledger):
    _rows(ledger, {"safeway-2026-03-04:old": {"to": "visa-ledger", "reason": "split"}})
    for to in ("safeway-2026-03-04:amount", "safeway-2026-03-04:old"):
        plan = plan_move(ledger, "visa-ledger:txn-0304", to, "split")
        assert plan["errors"], to


# ---------- merge keeps and follows claim rows ---------- #


def test_a_merge_keeps_claim_rows_and_retargets_those_into_the_loser(ledger):
    _fact(ledger, "transaction", {
        "id": "safeway-dup", "type": "transaction", "name": "Safeway dup",
        "sources": {"s1": {"record": H2}},
        "claims": [_claim("safeway-dup", "card-charge")],
    })
    _rows(ledger, {
        "visa-ledger:txn-0101": {"to": "safeway-dup", "reason": "split"},
        "visa-ledger:txn-0102": {"to": "safeway-dup:card-charge", "reason": "split"},
        "safeway-2026-03-04:amount-2": {"to": "visa-ledger", "reason": "rekeyed"},
    })
    plan = plan_merge(ledger, None, "safeway-dup", "safeway-2026-03-04")
    apply_merge(ledger, plan)
    claim_rows = load_claim_lineage_rows(ledger)
    assert claim_rows["visa-ledger:txn-0101"]["to"] == "safeway-2026-03-04"
    assert claim_rows["visa-ledger:txn-0102"]["to"] == "safeway-2026-03-04:card-charge"
    assert "safeway-2026-03-04:amount-2" in claim_rows  # untouched, still occupied
    assert load_lineage(ledger)[0]["safeway-dup"] == "safeway-2026-03-04"


# ---------- a batch of moves behind one gate (arbre-ath-steven, R-0055: 74 moves) ---------- #


_CHAIN = [
    ("visa-ledger:txn-0305", "safeway-2026-03-04:card-charge", "split"),
    # planned against the ledger the first move left: this claim exists only after it
    ("safeway-2026-03-04:card-charge", "visa-ledger:charge-0305", "rekeyed"),
]


def _snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*.json"))}


def test_a_preview_plans_in_sequence_and_touches_nothing(ledger):
    before = _snapshot(ledger)
    plans = preview_moves(ledger, _CHAIN)
    assert [p["errors"] for p in plans] == [[], []]
    assert plans[1]["lineage_retargeted"] == [{
        "key": "visa-ledger:txn-0305", "old_target": "safeway-2026-03-04:card-charge",
        "new_target": "visa-ledger:charge-0305"}]
    assert _snapshot(ledger) == before


def test_a_batch_applies_every_move_behind_one_gate(ledger):
    apply_moves(ledger, _CHAIN)
    assert load_claim_lineage_rows(ledger) == {
        "visa-ledger:txn-0305": {"to": "visa-ledger:charge-0305", "reason": "split"},
        "safeway-2026-03-04:card-charge": {"to": "visa-ledger:charge-0305",
                                           "reason": "rekeyed"},
    }
    assert _errors(ledger) == []


def test_a_refused_move_rolls_the_whole_batch_back(ledger):
    before = _snapshot(ledger)
    with pytest.raises(MoveError, match="rolled back all 2"):
        apply_moves(ledger, [_CHAIN[0], ("visa-ledger:txn-9999", "safeway-2026-03-04:x",
                                         "split")])
    assert _snapshot(ledger) == before


def test_the_batch_file_reads_claim_to_and_an_optional_reason(tmp_path):
    from ledger._cli import _read_move_batch

    f = tmp_path / "moves.txt"
    f.write_text("# R-0055\nvisa-ledger:txn-0304 safeway-2026-03-04\n\n"
                 "a:b c:d rekeyed  # inline\n", encoding="utf-8")
    assert _read_move_batch(f, "split") == [
        ("visa-ledger:txn-0304", "safeway-2026-03-04", "split"), ("a:b", "c:d", "rekeyed")]
    with pytest.raises(ValueError, match="no REASON"):
        _read_move_batch(f, None)
