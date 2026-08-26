"""Presence claims (spec/ledger.md §5.5): `presence: "none" | "some"` in place of
a claim's `value`/`object`.

Covers shape validation (`ledger.check`), demand satisfaction (`ledger.demands`),
invariant matching (`ledger.invariants`), the harvest-must-not-mint rule
(`ledger.harvest`), and canonical-hash determinism (`ledger.model`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.demands import evaluate_demands
from ledger.harvest import HarvestError, load_rules
from ledger.invariants import evaluate as evaluate_invariants
from ledger.model import canonical_claim_state

H1 = "a" * 64


def _fact(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    return tmp_path


def _check(root: Path):
    return run_check(root, CorpusJoin([]), {}, no_corpus=True)


def _presence_claim(fact_id: str, short: str, presence: str, **over) -> dict:
    c = {
        "id": f"{fact_id}:{short}", "predicate": short.replace("-", "_"),
        "presence": presence, "status": "confirmed", "asof": "2026-08-25",
        "evidence": [{"source": "s1", "kind": "authoritative"}],
    }
    c.update(over)
    return c


# ================================================================== shape (check)


def test_presence_none_is_well_formed(ledger: Path) -> None:
    _fact(ledger, "person", {
        "id": "elizabeth-i", "type": "person", "name": "Elizabeth I",
        "sources": {"s1": {"record": H1}},
        "claims": [_presence_claim("elizabeth-i", "child", "none")],
    })
    rep = _check(ledger)
    assert rep.ok, rep.errors


def test_presence_some_is_well_formed(ledger: Path) -> None:
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [_presence_claim("x", "father", "some")],
    })
    rep = _check(ledger)
    assert rep.ok, rep.errors


def test_bad_presence_value_is_an_error(ledger: Path) -> None:
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [_presence_claim("x", "father", "unknown")],
    })
    rep = _check(ledger)
    assert any("presence 'unknown' must be one of" in e for e in rep.errors)


def test_presence_with_value_is_an_error(ledger: Path) -> None:
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [_presence_claim("x", "father", "some", value="bob")],
    })
    rep = _check(ledger)
    assert any("exactly one of value, object, or presence" in e for e in rep.errors)


def test_presence_with_object_is_an_error(ledger: Path) -> None:
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [_presence_claim("x", "father", "some", object="bob")],
    })
    rep = _check(ledger)
    assert any("exactly one of value, object, or presence" in e for e in rep.errors)


def test_element_binding_illegal_on_presence_claim(ledger: Path) -> None:
    c = _presence_claim("x", "father", "some")
    c["evidence"] = [{"source": "s1", "kind": "authoritative", "element": 0}]
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [c],
    })
    rep = _check(ledger)
    assert any("element" in e and "not an array" in e for e in rep.errors)


def test_confirmed_presence_claim_clears_the_bar_on_one_authoritative_source(
    ledger: Path,
) -> None:
    """The §5.4 bar applies unchanged — no per-element logic, since there's no
    array — so one authoritative source is enough to confirm."""
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [_presence_claim("x", "father", "none")],
    })
    rep = _check(ledger)
    assert rep.ok, rep.errors


def test_unconfirmed_presence_claim_without_bar_coverage_is_an_error(ledger: Path) -> None:
    c = _presence_claim("x", "father", "none")
    c["evidence"] = [{"source": "s1", "kind": "incidental"}]
    _fact(ledger, "person", {
        "id": "x", "type": "person", "name": "X",
        "sources": {"s1": {"record": H1}},
        "claims": [c],
    })
    rep = _check(ledger)
    assert any("fails the authentication bar for `confirmed`" in e for e in rep.errors)


# ============================================================================ demands


_HAT_RULE = {
    "hat-colour": {
        "id": "hat-colour", "description": "An asserted hat owes its colour.",
        "when": {"claim": {"predicate": "wearing", "value": {"in": ["hat", "cap", "beanie"]}}},
        "owes": [{"field": "hat_colour"}],
    }
}


def test_presence_claim_satisfies_a_demand_exactly_as_a_value_claim_does() -> None:
    fact = {"id": "bob", "type": "person", "claims": [
        {"predicate": "wearing", "value": "hat"},
        {"predicate": "hat_colour", "presence": "none", "id": "bob:colour"},
    ]}
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[],
    )
    assert len(demands) == 1
    assert demands[0]["state"] == "satisfied"
    assert demands[0]["satisfied_by"] == "bob:colour"


# ========================================================================= invariants


def test_presence_claims_count_as_matching_for_invariants() -> None:
    inv = {
        "id": "one-platform", "description": "d",
        "applies_to": {"type": "vehicle", "predicate": "platform"},
        "constraint": "unique", "severity": "error",
    }
    fact = {
        "id": "v", "type": "vehicle", "name": "V",
        "claims": [
            {"id": "v:p1", "predicate": "platform", "presence": "some", "status": "confirmed"},
            {"id": "v:p2", "predicate": "platform", "presence": "none", "status": "confirmed"},
        ],
    }
    findings = evaluate_invariants([inv], {Path("v.json"): fact})
    assert any("one-platform" in msg and "2 matching claims" in msg for _sev, msg in findings)


# =========================================================================== harvest


def test_harvest_rule_minting_presence_is_rejected(tmp_path: Path) -> None:
    hdir = tmp_path / "harvest"
    hdir.mkdir()
    rule = {
        "id": "bad-rule", "description": "d",
        "match": {"origin.host": {"equals": "example.com"}},
        "mint": {
            "concept": {"id": "band-{origin.path[0]}", "type": "band", "name": "{origin.path[0]}"},
            "claims": [{"predicate": "has-member", "presence": "some"}],
        },
    }
    (hdir / "bad-rule.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    with pytest.raises(HarvestError, match="MUST NOT mint presence claims"):
        load_rules(tmp_path)


def test_harvest_rule_minting_ordinary_value_claim_still_loads(tmp_path: Path) -> None:
    hdir = tmp_path / "harvest"
    hdir.mkdir()
    rule = {
        "id": "ok-rule", "description": "d",
        "match": {"origin.host": {"equals": "example.com"}},
        "mint": {
            "concept": {"id": "band-{origin.path[0]}", "type": "band", "name": "{origin.path[0]}"},
            "claims": [{"predicate": "genre", "value": "death metal"}],
        },
    }
    (hdir / "ok-rule.yaml").write_text(yaml.safe_dump(rule), encoding="utf-8")
    rules = load_rules(tmp_path)
    assert len(rules) == 1


# ======================================================================= canonical hash


def test_presence_claim_hashes_deterministically() -> None:
    claim = {
        "id": "x:father", "predicate": "father", "presence": "some",
        "status": "confirmed", "asof": "2026-08-25",
        "evidence": [{"source": "s1", "kind": "authoritative"}],
    }
    sources = {"s1": {"record": H1}}
    h1 = canonical_claim_state(claim, sources)
    h2 = canonical_claim_state(dict(claim), dict(sources))
    assert h1 == h2
    assert h1.startswith("blake3:")


def test_presence_none_and_some_hash_differently() -> None:
    base = {
        "id": "x:father", "predicate": "father",
        "status": "confirmed", "asof": "2026-08-25",
        "evidence": [{"source": "s1", "kind": "authoritative"}],
    }
    sources = {"s1": {"record": H1}}
    none_claim = {**base, "presence": "none"}
    some_claim = {**base, "presence": "some"}
    assert canonical_claim_state(none_claim, sources) != canonical_claim_state(
        some_claim, sources
    )
