"""Demands — the completeness rule layer (`spec/ledger.md` §14): rule
loading + well-formedness, the `when` condition grammar, state derivation
(open/satisfied/blocked), the expectations-sugar/`expected:true` parity with
declared rules, shape attachment, check integration, and the `ath ledger
demands` CLI surface.

Reuses `test_ledger_check`'s `system` fixture and authoring sugar for the
check/CLI-integration half, rather than duplicating the corpus/ledger
scaffolding — the same pattern `test_needs_promote.py` follows.
"""

from __future__ import annotations

import json
from pathlib import Path

from ledger._cli import main as ledger_main
from ledger.demands import condition_matches, evaluate_demands, load_demand_rules
from tests.test_ledger_check import H_PUB, _check, _claim, _fact, _interp, _regen
from tests.test_ledger_check import system as system  # re-exported pytest fixture

# ============================================================== rule loading


def _write_rule(root: Path, name: str, text: str) -> None:
    d = root / "demands"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_load_demand_rules_empty_when_no_dir(tmp_path: Path) -> None:
    rules, errors = load_demand_rules(tmp_path)
    assert rules == {} and errors == []


def test_load_demand_rules_well_formed(tmp_path: Path) -> None:
    _write_rule(tmp_path, "hat-colour", (
        "id: hat-colour\ndescription: An asserted hat owes its colour.\n"
        "when:\n  claim: { predicate: wearing, value: { in: [hat, cap, beanie] } }\n"
        "owes:\n  - field: hat_colour\n"
    ))
    rules, errors = load_demand_rules(tmp_path)
    assert errors == []
    assert set(rules) == {"hat-colour"}
    assert rules["hat-colour"]["description"] == "An asserted hat owes its colour."


def test_rule_stem_mismatch_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "hat-colour", (
        "id: wrong-name\ndescription: d\nwhen: { type: person }\nowes: [{ field: f }]\n"
    ))
    rules, errors = load_demand_rules(tmp_path)
    assert "hat-colour" not in rules
    assert any("!= filename stem" in e for e in errors)


def test_unknown_top_level_key_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { type: person }\nowes: [{ field: f }]\nbogus: true\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("unknown keys ['bogus']" in e for e in errors)


def test_missing_when_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", "id: r\ndescription: d\nowes: [{ field: f }]\n")
    _, errors = load_demand_rules(tmp_path)
    assert any("when is required" in e for e in errors)


def test_owes_must_be_a_non_empty_list(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", "id: r\ndescription: d\nwhen: { type: person }\nowes: []\n")
    _, errors = load_demand_rules(tmp_path)
    assert any("owes must be a non-empty list" in e for e in errors)


def test_owes_entry_requires_field(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { type: person }\nowes:\n  - description: no field\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("field is required" in e for e in errors)


def test_owes_entry_unknown_keys(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { type: person }\nowes:\n  - field: f\n    bogus: 1\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("owes[0] unknown keys" in e for e in errors)


def test_bad_rule_file_is_dropped_tolerantly(tmp_path: Path) -> None:
    _write_rule(tmp_path, "good", (
        "id: good\ndescription: d\nwhen: { type: person }\nowes: [{ field: f }]\n"
    ))
    _write_rule(tmp_path, "junk", "not: [valid, yaml, :::\n")
    rules, errors = load_demand_rules(tmp_path)
    assert "good" in rules
    assert "junk" not in rules
    assert any("invalid YAML" in e for e in errors)


# ------------------------------------------------------ `when` grammar errors


def test_when_claim_missing_predicate_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { claim: { value: x } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("predicate is required" in e for e in errors)


def test_when_claim_unknown_key_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { claim: { predicate: p, bogus: 1 } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("claim: unknown keys" in e for e in errors)


def test_when_roster_unknown_key_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { roster: { bogus: 1 } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("roster: unknown keys" in e for e in errors)


def test_when_edge_selector_must_carry_exactly_one_type(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { edge: { a: {}, b: {} } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("edge: must be {edge-type" in e for e in errors)


def test_when_edge_unknown_selector_key_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { edge: { relationship: { bogus: 1 } } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("edge.relationship: unknown keys" in e for e in errors)


def test_when_type_wrong_shape_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", "id: r\ndescription: d\nwhen: { type: 5 }\nowes: [{ field: f }]\n")
    _, errors = load_demand_rules(tmp_path)
    assert any("type: must be a string" in e for e in errors)


def test_when_unknown_operator_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { claim: { predicate: p, value: { bogus: 1 } } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("unknown operator 'bogus'" in e for e in errors)


def test_when_in_operator_requires_a_list(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { claim: { predicate: p, value: { in: x } } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("'in' operator requires a list" in e for e in errors)


def test_when_matches_invalid_regex_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { claim: { predicate: p, value: { matches: '[' } } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("not a valid regex" in e for e in errors)


def test_when_group_must_be_a_non_empty_list(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { all_of: [] }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("all_of: must be a non-empty list" in e for e in errors)


def test_when_unknown_condition_key_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", "id: r\ndescription: d\nwhen: { bogus: 1 }\nowes: [{ field: f }]\n")
    _, errors = load_demand_rules(tmp_path)
    assert any("unknown condition key" in e for e in errors)


# ============================================================= condition grammar


def test_condition_type_scalar() -> None:
    fact = {"id": "x", "type": "person"}
    assert condition_matches({"type": "person"}, fact, [], {})
    assert not condition_matches({"type": "artist"}, fact, [], {})


def test_condition_type_in() -> None:
    fact = {"id": "x", "type": "person"}
    assert condition_matches({"type": {"in": ["person", "artist"]}}, fact, [], {})
    assert not condition_matches({"type": {"in": ["artist"]}}, fact, [], {})


def test_condition_claim_value_equals_scalar() -> None:
    fact = {"id": "x", "type": "t", "claims": [{"predicate": "wearing", "value": "hat"}]}
    assert condition_matches({"claim": {"predicate": "wearing", "value": "hat"}}, fact, [], {})
    assert not condition_matches({"claim": {"predicate": "wearing", "value": "cap"}}, fact, [], {})


def test_condition_claim_value_in() -> None:
    fact = {"id": "x", "type": "t", "claims": [{"predicate": "wearing", "value": "cap"}]}
    cond = {"claim": {"predicate": "wearing", "value": {"in": ["hat", "cap", "beanie"]}}}
    assert condition_matches(cond, fact, [], {})
    assert not condition_matches(
        {"claim": {"predicate": "wearing", "value": {"in": ["hat", "beanie"]}}}, fact, [], {})


def test_condition_claim_value_glob() -> None:
    fact = {"id": "x", "type": "t", "claims": [{"predicate": "name", "value": "Nostalgia"}]}
    assert condition_matches(
        {"claim": {"predicate": "name", "value": {"glob": "Nostalg*"}}}, fact, [], {})
    assert not condition_matches(
        {"claim": {"predicate": "name", "value": {"glob": "Obscura*"}}}, fact, [], {})


def test_condition_claim_value_matches_regex() -> None:
    fact = {"id": "x", "type": "t", "claims": [{"predicate": "name", "value": "Obscura"}]}
    assert condition_matches(
        {"claim": {"predicate": "name", "value": {"matches": "^Obscura$"}}}, fact, [], {})
    assert not condition_matches(
        {"claim": {"predicate": "name", "value": {"matches": "^Nostalgia$"}}}, fact, [], {})


def test_condition_claim_value_exists() -> None:
    """`exists` on `value`/`object` presupposes a claim under the predicate
    (per the grammar's own wording, "matches when the fact carries a claim
    under that predicate whose value … satisfies the operator") — it then
    tests presence of that side on the claim that was found, not absence of
    the claim itself (that's `none_of: [{claim: {predicate: …}}]`)."""
    with_value = {"id": "x", "type": "t", "claims": [{"predicate": "length", "value": "5:00"}]}
    relational_only = {"id": "y", "type": "t",
                       "claims": [{"predicate": "length", "object": "other-fact"}]}
    no_claim = {"id": "z", "type": "t", "claims": []}
    cond_true = {"claim": {"predicate": "length", "value": {"exists": True}}}
    cond_false = {"claim": {"predicate": "length", "value": {"exists": False}}}
    assert condition_matches(cond_true, with_value, [], {})
    assert not condition_matches(cond_true, relational_only, [], {})
    assert not condition_matches(cond_true, no_claim, [], {})
    assert condition_matches(cond_false, relational_only, [], {})
    assert not condition_matches(cond_false, with_value, [], {})
    assert not condition_matches(cond_false, no_claim, [], {})


def test_condition_claim_object() -> None:
    fact = {"id": "x", "type": "t", "claims": [{"predicate": "employed_by", "object": "acme"}]}
    assert condition_matches(
        {"claim": {"predicate": "employed_by", "object": "acme"}}, fact, [], {})
    assert not condition_matches(
        {"claim": {"predicate": "employed_by", "object": "other"}}, fact, [], {})


def test_condition_claim_value_and_object_must_be_the_same_claim() -> None:
    """One claim must satisfy both sides — a value match on a DIFFERENT
    claim under the predicate must not falsely satisfy the object side."""
    fact = {"id": "x", "type": "t", "claims": [
        {"predicate": "role", "value": "friend", "object": "a"},
        {"predicate": "role", "value": "enemy", "object": "b"},
    ]}
    assert condition_matches(
        {"claim": {"predicate": "role", "value": "friend", "object": "a"}}, fact, [], {})
    assert not condition_matches(
        {"claim": {"predicate": "role", "value": "friend", "object": "b"}}, fact, [], {})


def test_condition_claim_array_value_matches_any_element() -> None:
    """For array claim values, a value op matches if ANY element (or its
    string form) satisfies it (§14)."""
    fact = {"id": "x", "type": "t",
           "claims": [{"predicate": "genres", "value": ["death-metal", "black-metal"]}]}
    assert condition_matches(
        {"claim": {"predicate": "genres", "value": "black-metal"}}, fact, [], {})
    assert condition_matches(
        {"claim": {"predicate": "genres", "value": {"in": ["prog", "black-metal"]}}}, fact, [], {})
    assert not condition_matches({"claim": {"predicate": "genres", "value": "prog"}}, fact, [], {})


def test_condition_roster_role() -> None:
    fact = {"id": "x", "type": "t", "artifacts": [{"uri": "corpus://a", "role": "documents"}]}
    assert condition_matches({"roster": {"role": "documents"}}, fact, [], {})
    assert not condition_matches({"roster": {"role": "interview"}}, fact, [], {})


def test_condition_roster_exists() -> None:
    empty = {"id": "x", "type": "t"}
    present = {"id": "y", "type": "t", "artifacts": [{"uri": "corpus://a", "role": "documents"}]}
    assert condition_matches({"roster": {"exists": True}}, present, [], {})
    assert condition_matches({"roster": {"exists": False}}, empty, [], {})
    assert not condition_matches({"roster": {"exists": True}}, empty, [], {})


def test_condition_roster_role_with_exists_false_means_absence_of_that_role() -> None:
    fact = {"id": "x", "type": "t", "artifacts": [{"uri": "corpus://a", "role": "documents"}]}
    assert condition_matches({"roster": {"role": "photo", "exists": False}}, fact, [], {})
    assert not condition_matches({"roster": {"role": "documents", "exists": False}}, fact, [], {})


def test_condition_edge_basic() -> None:
    fact = {"id": "steven", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"],
           "claims": [{"predicate": "kind", "value": "sibling"}]}
    assert condition_matches({"edge": {"relationship": {}}}, fact, [edge], {})
    assert not condition_matches({"edge": {"employment": {}}}, fact, [edge], {})


def test_condition_edge_kind_filter() -> None:
    fact = {"id": "steven", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"],
           "claims": [{"predicate": "kind", "value": "sibling"}]}
    assert condition_matches({"edge": {"relationship": {"kind": ["sibling"]}}}, fact, [edge], {})
    assert not condition_matches(
        {"edge": {"relationship": {"kind": ["father-of"]}}}, fact, [edge], {})


def test_condition_edge_with() -> None:
    fact = {"id": "steven", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"]}
    assert condition_matches({"edge": {"relationship": {"with": "kat"}}}, fact, [edge], {})
    assert not condition_matches({"edge": {"relationship": {"with": "stranger"}}}, fact, [edge], {})
    # never selected by with: naming itself
    assert not condition_matches({"edge": {"relationship": {"with": "steven"}}}, fact, [edge], {})


def test_condition_edge_target_type() -> None:
    steven = {"id": "steven", "type": "person"}
    acme = {"id": "acme", "type": "organization"}
    edge = {"id": "steven--acme", "type": "employment", "participants": ["steven", "acme"]}
    facts_by_id = {"steven": steven, "acme": acme}
    assert condition_matches(
        {"edge": {"employment": {"target_type": "organization"}}}, steven, [edge], facts_by_id)
    assert not condition_matches(
        {"edge": {"employment": {"target_type": "person"}}}, steven, [edge], facts_by_id)


def test_condition_all_of() -> None:
    fact = {"id": "x", "type": "person", "claims": [{"predicate": "p", "value": "v"}]}
    assert condition_matches(
        {"all_of": [{"type": "person"}, {"claim": {"predicate": "p"}}]}, fact, [], {})
    assert not condition_matches(
        {"all_of": [{"type": "person"}, {"claim": {"predicate": "q"}}]}, fact, [], {})


def test_condition_any_of() -> None:
    fact = {"id": "x", "type": "person"}
    assert condition_matches({"any_of": [{"type": "artist"}, {"type": "person"}]}, fact, [], {})
    assert not condition_matches({"any_of": [{"type": "artist"}, {"type": "album"}]}, fact, [], {})


def test_condition_none_of() -> None:
    fact = {"id": "x", "type": "person"}
    assert condition_matches({"none_of": [{"type": "artist"}]}, fact, [], {})
    assert not condition_matches({"none_of": [{"type": "person"}]}, fact, [], {})


def test_condition_implicit_all_of() -> None:
    """A bare mapping with several keys is an implicit `all_of`."""
    fact = {"id": "x", "type": "person", "claims": [{"predicate": "p", "value": "v"}]}
    assert condition_matches({"type": "person", "claim": {"predicate": "p"}}, fact, [], {})
    assert not condition_matches({"type": "artist", "claim": {"predicate": "p"}}, fact, [], {})


def test_condition_missing_is_false() -> None:
    fact = {"id": "x", "type": "person"}
    assert not condition_matches({"claim": {"predicate": "nope"}}, fact, [], {})
    assert not condition_matches({}, fact, [], {})


# ================================================================ evaluate_demands


_HAT_RULE = {
    "hat-colour": {
        "id": "hat-colour", "description": "An asserted hat owes its colour.",
        "when": {"claim": {"predicate": "wearing", "value": {"in": ["hat", "cap", "beanie"]}}},
        "owes": [{"field": "hat_colour"}],
    }
}


def test_evaluate_demands_open_when_field_missing() -> None:
    fact = {"id": "bob", "type": "person", "claims": [{"predicate": "wearing", "value": "hat"}]}
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[],
    )
    assert demands == [{
        "rule": "hat-colour", "fact": "bob", "field": "hat_colour", "state": "open",
        "why": "An asserted hat owes its colour.", "shape": {},
    }]


def test_evaluate_demands_satisfied_when_claim_present() -> None:
    fact = {"id": "bob", "type": "person", "claims": [
        {"predicate": "wearing", "value": "hat"},
        {"predicate": "hat_colour", "value": "red"},
    ]}
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[],
    )
    assert len(demands) == 1
    assert demands[0]["state"] == "satisfied"
    assert "need" not in demands[0]


def test_evaluate_demands_blocked_via_open_interp_naming_the_rule() -> None:
    fact = {"id": "bob", "type": "person", "claims": [{"predicate": "wearing", "value": "hat"}]}
    interp = {
        "id": "no-source", "status": "open", "about": ["bob"],
        "needs": [{"action": "search", "demand": "hat-colour", "why": "no source names it"}],
    }
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[interp],
    )
    assert len(demands) == 1
    d = demands[0]
    assert d["state"] == "blocked"
    assert d["need"]["action"] == "search"
    assert d["need"]["why"] == "no source names it"
    assert d["need"]["interpretation"] == "no-source"


def test_evaluate_demands_standing_interp_also_blocks() -> None:
    fact = {"id": "bob", "type": "person", "claims": [{"predicate": "wearing", "value": "hat"}]}
    interp = {
        "id": "gap", "status": "standing", "about": ["bob"],
        "needs": [{"action": "capture", "demand": "hat-colour", "why": "…"}],
    }
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[interp],
    )
    assert demands[0]["state"] == "blocked"


def test_evaluate_demands_refuted_interp_does_not_block() -> None:
    """A promoted/refuted/retired interpretation no longer blocks (§14)."""
    fact = {"id": "bob", "type": "person", "claims": [{"predicate": "wearing", "value": "hat"}]}
    interp = {
        "id": "no-source", "status": "refuted", "about": ["bob"], "resolution": "abandoned",
        "needs": [{"action": "search", "demand": "hat-colour", "why": "…"}],
    }
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[interp],
    )
    assert demands[0]["state"] == "open"


def test_evaluate_demands_retired_interp_does_not_block() -> None:
    fact = {"id": "bob", "type": "person", "claims": [{"predicate": "wearing", "value": "hat"}]}
    interp = {
        "id": "gap", "status": "retired", "about": ["bob"],
        "needs": [{"action": "capture", "demand": "hat-colour", "why": "…"}],
    }
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[interp],
    )
    assert demands[0]["state"] == "open"


def test_evaluate_demands_interps_may_be_a_dict() -> None:
    """Callers may pass either a list or the {path: obj} shape `load_json_dir`
    returns — evaluate_demands normalizes either way."""
    fact = {"id": "bob", "type": "person", "claims": [{"predicate": "wearing", "value": "hat"}]}
    interp = {
        "id": "no-source", "status": "open", "about": ["bob"],
        "needs": [{"action": "search", "demand": "hat-colour", "why": "…"}],
    }
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps={Path("x.json"): interp},
    )
    assert demands[0]["state"] == "blocked"


def test_evaluate_demands_no_rule_no_demand() -> None:
    fact = {"id": "bob", "type": "person", "claims": []}
    assert evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[],
    ) == []


# ---------------------------------------------- expectations sugar + expected:true


def test_expectation_sugar_emits_a_demand_identical_in_shape_to_an_equivalent_rule() -> None:
    schemas = {
        "person": {
            "type": "person",
            "fields": {"date_of_birth": {}},
            "expectations": [
                {"description": "family birthdays are chase-worthy",
                 "when": {"relationship": {"kind": ["sibling"], "with": "steven"}},
                 "expect": ["date_of_birth"]},
            ],
        }
    }
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"],
           "claims": [{"predicate": "kind", "value": "sibling"}]}
    kat = {"id": "kat", "type": "person"}
    demands = evaluate_demands(
        kat, rules={}, schemas=schemas, kinds={}, facts_by_id={"kat": kat, "steven": {}},
        edges=[edge], interps=[],
    )
    assert len(demands) == 1
    d = demands[0]
    assert d["rule"] == "expectation:person[0]"
    assert d["fact"] == "kat"
    assert d["field"] == "date_of_birth"
    assert d["why"] == "family birthdays are chase-worthy"
    assert d["state"] == "open"
    assert d["shape"] == {}

    # equivalent as a declared rule (a `claim` condition standing in for the
    # edge selector isn't identical grammar, but the demand SHAPE the two
    # produce is what parity is about — same dict keys, same state derivation)
    rule = {"kid": {"id": "kid", "description": "family birthdays are chase-worthy",
                    "when": {"edge": {"relationship": {"kind": ["sibling"], "with": "steven"}}},
                    "owes": [{"field": "date_of_birth"}]}}
    rule_demands = evaluate_demands(
        kat, rules=rule, schemas=schemas, kinds={}, facts_by_id={"kat": kat, "steven": {}},
        edges=[edge], interps=[],
    )
    # the schema also fires its own expectation, so filter to the rule-based one
    rule_only = [d for d in rule_demands if d["rule"] == "kid"]
    assert len(rule_only) == 1
    assert {k: v for k, v in rule_only[0].items() if k != "rule"} == \
        {k: v for k, v in d.items() if k != "rule"}


def test_expectation_selects_excludes_the_with_fact_itself() -> None:
    schemas = {
        "person": {
            "type": "person", "fields": {"date_of_birth": {}},
            "expectations": [{"when": {"relationship": {"with": "steven"}},
                              "expect": ["date_of_birth"]}],
        }
    }
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"]}
    steven = {"id": "steven", "type": "person"}
    demands = evaluate_demands(
        steven, rules={}, schemas=schemas, kinds={}, facts_by_id={"steven": steven}, edges=[edge],
        interps=[],
    )
    assert demands == []


def test_expected_true_field_emits_a_demand() -> None:
    schemas = {"song": {"type": "song",
                        "fields": {"appears_on": {"target": "album", "expected": True}}}}
    fact = {"id": "s1", "type": "song"}
    demands = evaluate_demands(
        fact, rules={}, schemas=schemas, kinds={}, facts_by_id={"s1": fact}, edges=[], interps=[],
    )
    assert len(demands) == 1
    assert demands[0]["rule"] == "expected:song.appears_on"
    assert demands[0]["field"] == "appears_on"
    assert demands[0]["shape"] == {"target": "album"}
    assert demands[0]["state"] == "open"


def test_unmarked_field_owes_no_demand() -> None:
    schemas = {"song": {"type": "song", "fields": {"covered_by": {"target": "artist"}}}}
    fact = {"id": "s1", "type": "song"}
    assert evaluate_demands(
        fact, rules={}, schemas=schemas, kinds={}, facts_by_id={"s1": fact}, edges=[], interps=[],
    ) == []


# --------------------------------------------------------------- shape attachment


def test_shape_is_the_field_own_values_vocabulary() -> None:
    schemas = {"relationship": {"type": "relationship",
                                "fields": {"kind": {"values": ["friend", "sibling"]}}}}
    rules = {"r": {"id": "r", "description": "d", "when": {"type": "relationship"},
                  "owes": [{"field": "kind"}]}}
    fact = {"id": "e1", "type": "relationship"}
    demands = evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds={}, facts_by_id={"e1": fact}, edges=[],
        interps=[],
    )
    assert demands[0]["shape"] == {"values": ["friend", "sibling"]}


def test_shape_is_the_field_own_value_kind_declaration() -> None:
    money = {"kind": "money", "description": "d",
            "shape": {"amount": {"constraint": "decimal"}}, "required": ["amount"]}
    schemas = {"purchase": {"type": "purchase", "fields": {"price": {"value": "money"}}}}
    rules = {"r": {"id": "r", "description": "d", "when": {"type": "purchase"},
                  "owes": [{"field": "price"}]}}
    fact = {"id": "p1", "type": "purchase"}
    demands = evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds={"money": money}, facts_by_id={"p1": fact},
        edges=[], interps=[],
    )
    assert demands[0]["shape"] == {"value": "money", "kind": money}


def test_shape_is_the_field_own_relational_target() -> None:
    schemas = {"song": {"type": "song", "fields": {"appears_on": {"target": "album"}}}}
    rules = {"r": {"id": "r", "description": "d", "when": {"type": "song"},
                  "owes": [{"field": "appears_on"}]}}
    fact = {"id": "s1", "type": "song"}
    demands = evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds={}, facts_by_id={"s1": fact}, edges=[],
        interps=[],
    )
    assert demands[0]["shape"] == {"target": "album"}


def test_shape_is_empty_for_an_undeclared_field() -> None:
    """`period` — the reserved timebox name — carries no schema field
    declaration, so its shape is `{}`."""
    schemas = {"event": {"type": "event", "fields": {}}}
    rules = {"r": {"id": "r", "description": "d", "when": {"type": "event"},
                  "owes": [{"field": "period"}]}}
    fact = {"id": "e1", "type": "event"}
    demands = evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds={}, facts_by_id={"e1": fact}, edges=[],
        interps=[],
    )
    assert demands[0]["shape"] == {}
    assert demands[0]["state"] == "open"
    fact["period"] = "2026"
    demands = evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds={}, facts_by_id={"e1": fact}, edges=[],
        interps=[],
    )
    assert demands[0]["state"] == "satisfied"


# ------------------------------------------------------------------ determinism


def test_evaluate_demands_is_deterministic() -> None:
    rules = {
        "b-rule": {"id": "b-rule", "description": "d", "when": {"type": "person"},
                  "owes": [{"field": "f1"}]},
        "a-rule": {"id": "a-rule", "description": "d", "when": {"type": "person"},
                  "owes": [{"field": "f2"}]},
    }
    fact = {"id": "p1", "type": "person"}
    d1 = evaluate_demands(
        fact, rules=rules, schemas={}, kinds={}, facts_by_id={"p1": fact}, edges=[], interps=[],
    )
    d2 = evaluate_demands(
        fact, rules=rules, schemas={}, kinds={}, facts_by_id={"p1": fact}, edges=[], interps=[],
    )
    assert d1 == d2
    assert [d["rule"] for d in d1] == ["a-rule", "b-rule"]  # sorted, not authoring order


# =================================================================== check integration


def _rule(root: Path, name: str, text: str) -> None:
    d = root / "ledger" / "demands"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_check_bad_rule_is_an_error(system: Path) -> None:
    _rule(system, "bad", "id: bad\ndescription: d\nwhen: { bogus: 1 }\nowes: [{ field: f }]\n")
    rep = _check(system)
    assert any("unknown condition key" in e for e in rep.errors)


def test_check_needs_demand_naming_unknown_rule_is_an_error(system: Path) -> None:
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _interp(system, {
        "id": "gap", "kind": "assessment", "about": ["x"], "statement": "s", "reasoning": "r",
        "based_on": [f"corpus://{H_PUB}"], "status": "standing", "asof": "2026-07-02",
        "needs": [{"action": "search", "demand": "no-such-rule", "why": "…"}],
    })
    rep = _check(system)
    assert any("undeclared demand rule" in e and "no-such-rule" in e for e in rep.errors)


def test_check_needs_demand_naming_a_declared_rule_is_clean(system: Path) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\nwhen: { type: artist }\nowes: [{ field: f }]\n"
    ))
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _interp(system, {
        "id": "gap", "kind": "assessment", "about": ["x"], "statement": "s", "reasoning": "r",
        "based_on": [f"corpus://{H_PUB}"], "status": "standing", "asof": "2026-07-02",
        "needs": [{"action": "search", "demand": "hat-colour", "why": "…"}],
    })
    rep = _check(system)
    assert not any("undeclared demand rule" in e for e in rep.errors)


def test_open_demands_contribute_nothing_to_check(system: Path) -> None:
    """Filing is never denied, and demand evaluation itself emits no
    errors/warnings (§13.1 "Demands") — an unmet demand is frontier, visible
    only on the work-list."""
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [_claim("bob", "wearing", predicate="wearing", value="hat")],
    })
    _regen(system)
    rep = _check(system)
    assert rep.errors == []
    assert rep.warnings == []


def test_regen_open_questions_lists_the_open_demand(system: Path) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: needs a colour\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [_claim("bob", "wearing", predicate="wearing", value="hat")],
    })
    _regen(system)
    openq = (system / "ledger" / "open-questions.md").read_text()
    assert "### Demands (§14)" in openq
    assert "`bob`" in openq
    assert "hat_colour" in openq and "hat-colour" in openq


def test_regen_vocab_lists_demand_rule_with_match_count(system: Path) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: needs a colour\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [_claim("bob", "wearing", predicate="wearing", value="hat")],
    })
    _fact(system, "person", {
        "id": "kat", "type": "person", "name": "Kat",
        "claims": [_claim("kat", "email", predicate="email")],
    })
    _regen(system)
    vocab = (system / "ledger" / "facts" / "VOCAB.md").read_text()
    assert "## Demand rules" in vocab
    assert "`hat-colour`" in vocab
    assert "| `hat-colour` | 1 | needs a colour |" in vocab


# ====================================================================== CLI surface


def test_cli_demands_for_a_fact_id(system: Path, capsys) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: needs a colour\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [_claim("bob", "wearing", predicate="wearing", value="hat")],
    })
    rc = ledger_main(["demands", "bob", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0  # open demands never fail the command
    assert "OPEN" in out
    assert "hat_colour" in out and "hat-colour" in out


def test_cli_demands_hides_satisfied_unless_all(system: Path, capsys) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [
            _claim("bob", "wearing", predicate="wearing", value="hat"),
            _claim("bob", "colour", predicate="hat_colour", value="red"),
        ],
    })
    rc = ledger_main(["demands", "bob", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SATISFIED" not in out
    rc = ledger_main(["demands", "bob", "--all", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SATISFIED" in out


def test_cli_demands_draft_evaluates_a_not_yet_landed_fact(
    system: Path, tmp_path: Path, capsys,
) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({
        "id": "future-bob", "type": "person",
        "claims": [{"predicate": "wearing", "value": "hat"}],
    }), encoding="utf-8")
    rc = ledger_main(["demands", "--draft", str(draft), "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "future-bob" in out and "hat_colour" in out


def test_cli_demands_no_arg_prints_ledger_wide_summary(system: Path, capsys) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [_claim("bob", "wearing", predicate="wearing", value="hat")],
    })
    rc = ledger_main(["demands", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hat-colour" in out
    assert "open=1" in out


def test_cli_demands_unknown_fact_id_is_a_usage_error(system: Path, capsys) -> None:
    rc = ledger_main(["demands", "no-such-fact", "--root", str(system)])
    assert rc == 1
