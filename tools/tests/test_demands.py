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
from ledger.demands import (
    blockable_ids,
    condition_matches,
    evaluate_demands,
    format_shape,
    load_demand_rules,
    named_expectations,
    schema_expectation_satisfaction,
)
from ledger.schemas import expectation_selects, load_schemas
from tests.test_ledger_check import H_PUB, _check, _claim, _fact, _interp, _regen
from tests.test_ledger_check import system as system  # re-exported pytest fixture

# ============================================================== rule loading


def _write_rule(root: Path, name: str, text: str) -> None:
    d = root / "demands"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def _write_schema(root: Path, name: str, text: str) -> None:
    d = root / "schemas"
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


# ------------------------------------------------- schema expectation `id:` (§4.4, v29)


def test_expectation_id_accepted_when_slug_shaped(tmp_path: Path) -> None:
    _write_schema(tmp_path, "person", (
        "type: person\ndescription: d\nfields:\n  date_of_birth: {}\n"
        "expectations:\n  - id: person-dob\n    expect: [date_of_birth]\n"
    ))
    schemas, errors = load_schemas(tmp_path)
    assert errors == []
    assert schemas["person"]["expectations"][0]["id"] == "person-dob"


def test_expectation_id_must_be_a_readable_slug(tmp_path: Path) -> None:
    _write_schema(tmp_path, "person", (
        "type: person\ndescription: d\nfields:\n  date_of_birth: {}\n"
        "expectations:\n  - id: Not A Slug!\n    expect: [date_of_birth]\n"
    ))
    _, errors = load_schemas(tmp_path)
    assert any("id 'Not A Slug!' is not a readable slug" in e for e in errors)


def test_duplicate_expectation_id_within_one_schema_is_an_error(tmp_path: Path) -> None:
    _write_schema(tmp_path, "person", (
        "type: person\ndescription: d\nfields:\n  date_of_birth: {}\n  email: {}\n"
        "expectations:\n"
        "  - id: dup\n    expect: [date_of_birth]\n"
        "  - id: dup\n    expect: [email]\n"
    ))
    _, errors = load_schemas(tmp_path)
    assert any("id 'dup' duplicates expectations[0]" in e for e in errors)


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


# ------------------------------------------------------ `id:` grammar (v30, §14)


def test_when_id_unknown_operator_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { id: { bogus: x } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("unknown operator 'bogus'" in e for e in errors)


def test_when_id_in_operator_requires_a_list(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { id: { in: x } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("'in' operator requires a list" in e for e in errors)


def test_when_id_bare_scalar_is_legitimate(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { id: steven-rahn }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert errors == []


# ------------------------------------------------- `related:` grammar (v30, §14)


def test_when_related_requires_via(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { related: {} }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.via: must be one of" in e for e in errors)


def test_when_related_via_must_be_a_known_kind(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { related: { via: bogus } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.via: must be one of" in e for e in errors)


def test_when_related_unknown_key_is_an_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { related: { via: object, bogus: 1 } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related: unknown keys ['bogus']" in e for e in errors)


def test_when_related_edge_only_admissible_under_via_edge(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: object, edge: { relationship: {} } } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.edge: only admissible under via: edge" in e for e in errors)


def test_when_related_edge_selector_reuses_the_edge_condition_grammar(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: edge, edge: { relationship: { bogus: 1 } } } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.edge.relationship: unknown keys ['bogus']" in e for e in errors)


def test_when_related_edge_must_carry_exactly_one_type(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: edge, edge: { a: {}, b: {} } } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.edge: must be {edge-type" in e for e in errors)


def test_malformed_related_edge_selector_is_dropped_not_kept(tmp_path: Path) -> None:
    """A rule whose `related.edge` selector fails the shape check must be
    DROPPED, not merely reported-and-kept — kept, it would crash
    `_edge_neighbors`'s `(etype, sel), = edge_sel.items()` the first time a
    fact actually reaches evaluation (the bug this regression-tests: a
    2-key edge selector unpacked into a 1-tuple target)."""
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: edge, edge: { met: {}, knew: {} } } }\n"
        "owes: [{ field: f }]\n"
    ))
    rules, errors = load_demand_rules(tmp_path)
    assert "r" not in rules
    assert any("related.edge: must be {edge-type" in e for e in errors)
    # and even a hand-built condition with the same malformed shape (bypassing
    # the loader entirely) must not crash evaluation — it simply never matches
    fact = {"id": "x", "type": "person"}
    edge = {"id": "e", "type": "met", "participants": ["x", "y"]}
    assert not condition_matches(
        {"related": {"via": "edge", "edge": {"met": {}, "knew": {}}}},
        fact, [edge], {"x": fact},
    )


def test_when_related_where_parses_the_condition_grammar(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: object, where: { bogus: 1 } } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.where: unknown condition key" in e for e in errors)


def test_when_related_where_cannot_nest_related(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: object, "
        "where: { related: { via: entity } } } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    msg = next(e for e in errors if "related.where.related" in e)
    assert "not allowed inside a where" in msg
    assert "one hop is deliberate" in msg


def test_when_related_where_cannot_nest_related_inside_a_group(tmp_path: Path) -> None:
    """The ban holds at any depth inside `where` — not just the top level."""
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: object, "
        "where: { all_of: [{ type: person }, { related: { via: entity } }] } } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("not allowed inside a where" in e for e in errors)


def test_when_related_exists_must_be_a_bool(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: object, exists: yes-please } }\nowes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.exists: must be a bool" in e for e in errors)


def test_when_related_well_formed_is_clean(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\n"
        "when: { related: { via: edge, edge: { relationship: { kind: [sibling] } }, "
        "where: { type: person }, exists: true } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert errors == []


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


def test_condition_edge_matches_on_subject_not_only_participants() -> None:
    """spec/ledger.md §4.3: "A file is an edge when it carries `subject`
    and/or `participants`." `edge:` conditions used to read only
    `participants`, so a rule keyed on edge participation quietly never
    fired for the subject side — matching finding 12's exact repro."""
    person_a = {"id": "person-a", "type": "person"}
    edge = {"id": "e1", "type": "residence", "subject": "person-a",
           "participants": ["place-b"]}
    facts_by_id = {"person-a": person_a}
    assert condition_matches({"edge": {"residence": {}}}, person_a, [edge], facts_by_id)
    # `related: {via: edge}` already got this right — same fact, same answer
    assert condition_matches(
        {"related": {"via": "edge", "edge": {"residence": {}}}},
        person_a, [edge], facts_by_id)


def test_condition_edge_with_resolves_participants_through_lineage() -> None:
    """The `edge:` condition's `with:` used to compare raw, unresolved
    participant strings — a retired co-participant id never matched even
    though `related: {via: edge}`'s equivalent selector already resolves
    through lineage (§4.1). Mirrors
    `test_related_via_edge_hop_resolves_participants_through_lineage`."""
    steven = {"id": "steven", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship",
           "participants": ["steven", "kat-rahn"]}  # names the retired id
    lineage = {"kat-rahn": "kat-rahn-jr"}
    cond = {"edge": {"relationship": {"with": "kat-rahn-jr"}}}
    assert not condition_matches(cond, steven, [edge], {}, lineage=None)
    assert condition_matches(cond, steven, [edge], {}, lineage=lineage)


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


# ============================================================ `id:` condition (v30)


def test_condition_id_equals() -> None:
    fact = {"id": "steven-rahn", "type": "person"}
    assert condition_matches({"id": {"equals": "steven-rahn"}}, fact, [], {})
    assert not condition_matches({"id": {"equals": "kat-rahn"}}, fact, [], {})


def test_condition_id_bare_scalar_is_implicit_equals() -> None:
    fact = {"id": "steven-rahn", "type": "person"}
    assert condition_matches({"id": "steven-rahn"}, fact, [], {})
    assert not condition_matches({"id": "kat-rahn"}, fact, [], {})


def test_condition_id_in() -> None:
    fact = {"id": "kat-rahn", "type": "person"}
    assert condition_matches({"id": {"in": ["steven-rahn", "kat-rahn"]}}, fact, [], {})
    assert not condition_matches({"id": {"in": ["steven-rahn"]}}, fact, [], {})


def test_condition_id_glob() -> None:
    fact = {"id": "steven-rahn", "type": "person"}
    assert condition_matches({"id": {"glob": "steven-*"}}, fact, [], {})
    assert not condition_matches({"id": {"glob": "kat-*"}}, fact, [], {})


def test_condition_id_matches_regex() -> None:
    fact = {"id": "steven-rahn", "type": "person"}
    assert condition_matches({"id": {"matches": "^steven-"}}, fact, [], {})
    assert not condition_matches({"id": {"matches": "^kat-"}}, fact, [], {})


def test_condition_id_equals_operand_resolves_through_lineage() -> None:
    """A rule naming a retired id still matches the living successor it
    merged into (§4.1, §14)."""
    fact = {"id": "steven-rahn-jr", "type": "person"}  # the survivor
    lineage = {"steve-rahn": "steven-rahn-jr"}
    assert condition_matches({"id": {"equals": "steve-rahn"}}, fact, [], {}, lineage=lineage)
    # without the lineage map on hand, the retired id no longer names the fact
    assert not condition_matches({"id": {"equals": "steve-rahn"}}, fact, [], {})


def test_condition_id_in_operand_resolves_through_lineage() -> None:
    fact = {"id": "steven-rahn-jr", "type": "person"}
    lineage = {"steve-rahn": "steven-rahn-jr"}
    assert condition_matches(
        {"id": {"in": ["kat-rahn", "steve-rahn"]}}, fact, [], {}, lineage=lineage)
    assert not condition_matches({"id": {"in": ["kat-rahn", "steve-rahn"]}}, fact, [], {})


def test_condition_id_glob_matches_living_id_no_resolution() -> None:
    """`glob`/`matches` test the living id as written — the operand is never
    resolved through lineage, unlike `equals`/`in` (§14)."""
    fact = {"id": "steven-rahn-jr", "type": "person"}
    lineage = {"steve-rahn": "steven-rahn-jr"}
    assert not condition_matches(
        {"id": {"glob": "steve-rahn"}}, fact, [], {}, lineage=lineage)
    assert condition_matches(
        {"id": {"glob": "steven-rahn-*"}}, fact, [], {}, lineage=lineage)


def test_condition_id_matches_regex_no_resolution() -> None:
    fact = {"id": "steven-rahn-jr", "type": "person"}
    lineage = {"steve-rahn": "steven-rahn-jr"}
    assert not condition_matches(
        {"id": {"matches": "^steve-rahn$"}}, fact, [], {}, lineage=lineage)


def test_id_perspective_idiom_none_of_excludes_the_hosting_fact() -> None:
    """The #205 specimen shape: a rule owing something of whoever *hosts* an
    appointment excludes the graph's visiting subject with `none_of:
    [{id: {equals: …}}]` (§14) — data, visible in the rule, honest about
    whom it exempts."""
    cond = {
        "all_of": [
            {"claim": {"predicate": "appointment"}},
            {"none_of": [{"id": {"equals": "steven-rahn"}}]},
        ],
    }
    host = {"id": "dr-smith", "type": "person",
           "claims": [{"predicate": "appointment", "value": "2026-09-01"}]}
    visitor = {"id": "steven-rahn", "type": "person",
              "claims": [{"predicate": "appointment", "value": "2026-09-01"}]}
    assert condition_matches(cond, host, [], {})
    assert not condition_matches(cond, visitor, [], {})


# ======================================================= `related:` condition (v30)


def test_related_via_object_exists_true_default() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    assert condition_matches({"related": {"via": "object"}}, steven, [], facts_by_id)


def test_related_via_object_where_matches_neighbor() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    assert condition_matches(
        {"related": {"via": "object", "where": {"type": "organization"}}}, steven, [],
        facts_by_id)
    assert not condition_matches(
        {"related": {"via": "object", "where": {"type": "person"}}}, steven, [], facts_by_id)


def test_related_where_nests_ordinary_condition_keys() -> None:
    """`where` is the same condition grammar — several keys compose as an
    implicit `all_of`, same as any top-level `when`."""
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization",
           "claims": [{"predicate": "industry", "value": "tech"}]}
    facts_by_id = {"steven": steven, "acme": acme}
    cond = {"related": {"via": "object", "where": {
        "type": "organization", "claim": {"predicate": "industry", "value": "tech"},
    }}}
    assert condition_matches(cond, steven, [], facts_by_id)
    cond_wrong = {"related": {"via": "object", "where": {
        "type": "organization", "claim": {"predicate": "industry", "value": "finance"},
    }}}
    assert not condition_matches(cond_wrong, steven, [], facts_by_id)


def test_related_via_entity() -> None:
    event = {"id": "concert", "type": "event",
            "claims": [{"predicate": "attendance",
                       "value": [{"entity": "steven"}, {"entity": "kat"}]}]}
    steven = {"id": "steven", "type": "person"}
    kat = {"id": "kat", "type": "person",
          "claims": [{"predicate": "role", "value": "organizer"}]}
    facts_by_id = {"concert": event, "steven": steven, "kat": kat}
    cond = {"related": {"via": "entity",
                        "where": {"claim": {"predicate": "role", "value": "organizer"}}}}
    assert condition_matches(cond, event, [], facts_by_id)
    cond_none = {"related": {"via": "entity",
                            "where": {"claim": {"predicate": "role", "value": "headliner"}}}}
    assert not condition_matches(cond_none, event, [], facts_by_id)


def test_related_via_wikilink() -> None:
    a = {"id": "a", "type": "person",
        "claims": [{"predicate": "note", "value": "friends with [[b]]"}]}
    b = {"id": "b", "type": "person",
        "claims": [{"predicate": "role", "value": "friend"}]}
    facts_by_id = {"a": a, "b": b}
    cond = {"related": {"via": "wikilink",
                        "where": {"claim": {"predicate": "role", "value": "friend"}}}}
    assert condition_matches(cond, a, [], facts_by_id)


def test_related_via_roster_is_malformed(tmp_path: Path) -> None:
    """The artifact roster targets corpus records, never facts (§4.2) — a
    roster `via` could never hold, so it is malformed, not vacuous (§14)."""
    _write_rule(tmp_path, "r", (
        "id: r\ndescription: d\nwhen: { related: { via: roster } }\n"
        "owes: [{ field: f }]\n"
    ))
    _, errors = load_demand_rules(tmp_path)
    assert any("related.via: must be one of" in e for e in errors)


def test_related_via_edge_basic() -> None:
    steven = {"id": "steven", "type": "person"}
    kat = {"id": "kat", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"],
           "claims": [{"predicate": "kind", "value": "sibling"}]}
    facts_by_id = {"steven": steven, "kat": kat}
    cond = {"related": {"via": "edge",
                        "where": {"claim": {"predicate": "kind", "value": "sibling"}}}}
    assert condition_matches(cond, steven, [edge], facts_by_id)


def test_related_via_edge_where_evaluates_the_edge_fact_itself() -> None:
    """The neighbor `where` tests under `via: edge` is the edge fact, not a
    co-participant (§14)."""
    steven = {"id": "steven", "type": "person"}
    kat = {"id": "kat", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"]}
    facts_by_id = {"steven": steven, "kat": kat}
    assert condition_matches(
        {"related": {"via": "edge", "where": {"type": "relationship"}}}, steven, [edge],
        facts_by_id)
    assert not condition_matches(
        {"related": {"via": "edge", "where": {"type": "person"}}}, steven, [edge], facts_by_id)


def test_related_via_edge_narrowed_by_selector() -> None:
    steven = {"id": "steven", "type": "person"}
    kat = {"id": "kat", "type": "person"}
    acme = {"id": "acme", "type": "organization"}
    sibling = {"id": "steven--kat", "type": "relationship",
              "participants": ["steven", "kat"],
              "claims": [{"predicate": "kind", "value": "sibling"}]}
    employment = {"id": "steven--acme", "type": "employment", "participants": ["steven", "acme"]}
    facts_by_id = {"steven": steven, "kat": kat, "acme": acme}
    edges = [sibling, employment]
    assert condition_matches(
        {"related": {"via": "edge", "edge": {"relationship": {"kind": ["sibling"]}}}},
        steven, edges, facts_by_id)
    assert not condition_matches(
        {"related": {"via": "edge", "edge": {"relationship": {"kind": ["father-of"]}}}},
        steven, edges, facts_by_id)
    # target_type narrows to the employment edge's organization co-participant
    assert condition_matches(
        {"related": {"via": "edge",
                    "edge": {"employment": {"target_type": "organization"}}}},
        steven, edges, facts_by_id)


def test_related_via_edge_never_selected_by_with_naming_itself() -> None:
    steven = {"id": "steven", "type": "person"}
    kat = {"id": "kat", "type": "person"}
    edge = {"id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"]}
    facts_by_id = {"steven": steven, "kat": kat}
    assert not condition_matches(
        {"related": {"via": "edge", "edge": {"relationship": {"with": "steven"}}}},
        steven, [edge], facts_by_id)


def test_related_via_edge_hop_resolves_participants_through_lineage() -> None:
    steven = {"id": "steven", "type": "person"}
    kat_jr = {"id": "kat-rahn-jr", "type": "person"}  # the survivor
    edge = {"id": "steven--kat", "type": "relationship",
           "participants": ["steven", "kat-rahn"]}  # names the retired id
    facts_by_id = {"steven": steven, "kat-rahn-jr": kat_jr}
    lineage = {"kat-rahn": "kat-rahn-jr"}
    cond = {"related": {"via": "edge", "edge": {"relationship": {"with": "kat-rahn-jr"}}}}
    assert condition_matches(cond, steven, [edge], facts_by_id, lineage=lineage)
    assert not condition_matches(cond, steven, [edge], facts_by_id)


def test_related_exists_true_without_where_any_neighbor_suffices() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    assert condition_matches({"related": {"via": "object"}}, steven, [], facts_by_id)


def test_related_exists_false_without_where_holds_only_absent_neighbors() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    assert not condition_matches(
        {"related": {"via": "object", "exists": False}}, steven, [], facts_by_id)
    lonely = {"id": "lonely", "type": "person"}
    assert condition_matches(
        {"related": {"via": "object", "exists": False}}, lonely, [], {"lonely": lonely})


def test_related_no_neighbors_fails_exists_true_and_passes_exists_false() -> None:
    """Missing-is-false throughout: a fact with no neighbors along `via`
    fails `exists: true` and passes `exists: false` (§14)."""
    lonely = {"id": "lonely", "type": "person"}
    facts_by_id = {"lonely": lonely}
    assert not condition_matches({"related": {"via": "object"}}, lonely, [], facts_by_id)
    assert condition_matches(
        {"related": {"via": "object", "exists": False}}, lonely, [], facts_by_id)


def test_related_exists_false_holds_when_no_neighbor_matches_where() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    assert condition_matches(
        {"related": {"via": "object", "where": {"type": "person"}, "exists": False}},
        steven, [], facts_by_id)


def test_related_via_object_hop_resolves_through_lineage() -> None:
    """A claim `object` naming a since-merged id still reaches the living
    successor (§4.1, §12.1, §14)."""
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "old-acme"}]}
    acme = {"id": "acme-inc", "type": "organization"}
    facts_by_id = {"steven": steven, "acme-inc": acme}
    lineage = {"old-acme": "acme-inc"}
    cond = {"related": {"via": "object", "where": {"type": "organization"}}}
    assert condition_matches(cond, steven, [], facts_by_id, lineage=lineage)
    assert not condition_matches(cond, steven, [], facts_by_id)  # no lineage — dangling


def test_related_unresolvable_reference_contributes_no_neighbor() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "ghost-corp"}]}
    facts_by_id = {"steven": steven}
    assert not condition_matches({"related": {"via": "object"}}, steven, [], facts_by_id)


def test_related_is_deterministic() -> None:
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"},
                       {"predicate": "member_of", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    cond = {"related": {"via": "object", "where": {"type": "organization"}}}
    assert condition_matches(cond, steven, [], facts_by_id) is True
    assert condition_matches(cond, steven, [], facts_by_id) is True


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
        {"predicate": "hat_colour", "value": "red", "id": "bob:colour"},
    ]}
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[],
    )
    assert len(demands) == 1
    assert demands[0]["state"] == "satisfied"
    assert demands[0]["satisfied_by"] == "bob:colour"
    assert "need" not in demands[0]


def test_evaluate_demands_satisfied_by_is_the_first_claim_under_the_predicate() -> None:
    """Deterministic, not "whichever wins" — first by claim-list order."""
    fact = {"id": "bob", "type": "person", "claims": [
        {"predicate": "wearing", "value": "hat"},
        {"predicate": "hat_colour", "value": "red", "id": "first"},
        {"predicate": "hat_colour", "value": "blue", "id": "second"},
    ]}
    demands = evaluate_demands(
        fact, rules=_HAT_RULE, schemas={}, kinds={}, facts_by_id={"bob": fact}, edges=[],
        interps=[],
    )
    assert demands[0]["satisfied_by"] == "first"


def test_evaluate_demands_satisfied_by_absent_for_the_reserved_period_field() -> None:
    """`period` is the fact's own timebox, not a claim — nothing to point at."""
    schemas = {"event": {"type": "event", "fields": {}}}
    rules = {"r": {"id": "r", "description": "d", "when": {"type": "event"},
                  "owes": [{"field": "period"}]}}
    fact = {"id": "e1", "type": "event", "period": "2026"}
    demands = evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds={}, facts_by_id={"e1": fact}, edges=[],
        interps=[],
    )
    assert demands[0]["state"] == "satisfied"
    assert "satisfied_by" not in demands[0]


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


def test_expectation_selects_on_subject_not_only_participants() -> None:
    """`schemas.expectation_selects` carried the identical participants-only
    blind spot `_edge_matches` did (§4.3: a file is an edge by subject
    and/or participants) — a named expectation keyed on an edge type never
    fired for the subject side."""
    schemas = {
        "person": {
            "type": "person", "fields": {"date_of_birth": {}},
            "expectations": [{"when": {"residence": {}}, "expect": ["date_of_birth"]}],
        }
    }
    person_a = {"id": "person-a", "type": "person"}
    edge = {"id": "e1", "type": "residence", "subject": "person-a", "participants": ["place-b"]}
    demands = evaluate_demands(
        person_a, rules={}, schemas=schemas, kinds={}, facts_by_id={"person-a": person_a},
        edges=[edge], interps=[],
    )
    assert any(d["field"] == "date_of_birth" for d in demands)


def test_expectation_selects_malformed_when_never_crashes() -> None:
    """A `when` that fails the shape check (dropped by `load_schemas`, per
    the regression above) must not crash `expectation_selects` even when
    handed to it directly — arity/isinstance-guarded, never
    `(edge_type, sel), = when.items()` on a 2-key or non-dict `when`."""
    fact = {"id": "x", "type": "person"}
    assert expectation_selects({"when": {"a": {}, "b": {}}, "expect": ["f"]}, fact, []) is False
    assert expectation_selects({"when": "not-a-dict", "expect": ["f"]}, fact, []) is False
    assert expectation_selects({"when": {"a": "not-a-dict"}, "expect": ["f"]}, fact, []) is False


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


# --------------------------------------------------------- named expectation ids (v29)


def test_named_expectation_uses_its_id_as_the_rule() -> None:
    """A named `id:` replaces the positional display id (§4.4) — the demand's
    `rule` carries the stable name, not `expectation:{type}[{i}]`."""
    schemas = {"person": {"type": "person", "fields": {"date_of_birth": {}},
                         "expectations": [{"id": "person-dob", "description": "d",
                                          "expect": ["date_of_birth"]}]}}
    fact = {"id": "kat", "type": "person"}
    demands = evaluate_demands(
        fact, rules={}, schemas=schemas, kinds={}, facts_by_id={"kat": fact}, edges=[],
        interps=[],
    )
    assert len(demands) == 1
    assert demands[0]["rule"] == "person-dob"


def test_named_expectation_blocks_via_its_own_id() -> None:
    """The evaluator honors a needs entry naming a named expectation's `id:`
    (§14) — the ruling's positive case."""
    schemas = {"person": {"type": "person", "fields": {"date_of_birth": {}},
                         "expectations": [{"id": "person-dob", "description": "d",
                                          "expect": ["date_of_birth"]}]}}
    fact = {"id": "kat", "type": "person"}
    interp = {
        "id": "gap", "status": "open", "about": ["kat"],
        "needs": [{"action": "search", "demand": "person-dob", "why": "no source yet"}],
    }
    demands = evaluate_demands(
        fact, rules={}, schemas=schemas, kinds={}, facts_by_id={"kat": fact}, edges=[],
        interps=[interp],
    )
    assert demands[0]["state"] == "blocked"
    assert demands[0]["need"]["interpretation"] == "gap"


def test_positional_expectation_reference_never_blocks() -> None:
    """The v28 seam this amendment closes: a needs entry naming the
    *positional* display id no longer derives blocked (§14: "a positional
    display id is never a blocking target") — it stays open until the field
    is satisfied, however many needs entries claim to name it."""
    schemas = {"person": {"type": "person", "fields": {"date_of_birth": {}},
                         "expectations": [{"description": "d",
                                          "expect": ["date_of_birth"]}]}}
    fact = {"id": "kat", "type": "person"}
    interp = {
        "id": "gap", "status": "open", "about": ["kat"],
        "needs": [{"action": "search", "demand": "expectation:person[0]",
                  "why": "no source yet"}],
    }
    demands = evaluate_demands(
        fact, rules={}, schemas=schemas, kinds={}, facts_by_id={"kat": fact}, edges=[],
        interps=[interp],
    )
    assert demands[0]["rule"] == "expectation:person[0]"
    assert demands[0]["state"] == "open"
    assert "need" not in demands[0]


def test_expected_true_field_reference_never_blocks() -> None:
    """`expected:{type}.{field}` is likewise outside the blockable namespace
    (§13.1: only declared rules and named expectations) — naming it in a
    needs entry doesn't derive blocked either."""
    schemas = {"song": {"type": "song",
                        "fields": {"appears_on": {"target": "album", "expected": True}}}}
    fact = {"id": "s1", "type": "song"}
    interp = {
        "id": "gap", "status": "open", "about": ["s1"],
        "needs": [{"action": "search", "demand": "expected:song.appears_on", "why": "…"}],
    }
    demands = evaluate_demands(
        fact, rules={}, schemas=schemas, kinds={}, facts_by_id={"s1": fact}, edges=[],
        interps=[interp],
    )
    assert demands[0]["state"] == "open"


def test_named_expectations_helper_collects_ids_across_schemas() -> None:
    schemas = {
        "person": {"type": "person", "expectations": [
            {"id": "person-dob", "expect": ["date_of_birth"]},
            {"expect": ["email"]},  # unnamed — not collected
        ]},
        "song": {"type": "song", "expectations": [
            {"id": "song-album", "expect": ["appears_on"]},
        ]},
    }
    named = named_expectations(schemas)
    assert set(named) == {"person-dob", "song-album"}
    assert named["person-dob"][0] == "person"
    assert named["song-album"][0] == "song"


def test_blockable_ids_is_declared_rules_plus_named_expectations_only() -> None:
    rules = {"hat-colour": {"id": "hat-colour", "when": {"type": "person"},
                            "owes": [{"field": "hat_colour"}]}}
    schemas = {"person": {"type": "person", "expectations": [
        {"id": "person-dob", "expect": ["date_of_birth"]},
        {"expect": ["email"]},
    ]}}
    ids = blockable_ids(rules, schemas)
    assert ids == {"hat-colour", "person-dob"}
    assert "expectation:person[1]" not in ids


# ------------------------------------- schema expectation satisfaction (regen feedback, v32)


def test_schema_expectation_satisfaction_counts_across_the_type() -> None:
    """Two `song` concepts, one fully satisfying the schema's one expectation
    and one not — the roll-up totals both expectation-owed rows and the
    distinct concepts an expectation ever selected (regen's feedback line)."""
    schemas = {"song": {"type": "song", "expectations": [
        {"id": "song-album", "expect": ["appears_on"]},
    ]}}
    facts_by_id = {
        "s1": {"id": "s1", "type": "song",
               "claims": [{"id": "s1:appears_on", "predicate": "appears_on", "value": "x"}]},
        "s2": {"id": "s2", "type": "song", "claims": []},
    }
    summary = schema_expectation_satisfaction(
        schemas, facts_by_id, rules={}, kinds={}, edges=[], interps=[],
    )
    assert summary["song"] == {"total": 2, "satisfied": 1, "concepts": 2}


def test_schema_expectation_satisfaction_zero_when_type_absent() -> None:
    """A schema declaring `expectations:` with no concept of its type in the
    population binds zero — distinct from an all-satisfied roll-up, which
    also has `total == satisfied` but `concepts > 0`."""
    schemas = {"widget": {"type": "widget", "expectations": [
        {"id": "widget-color", "expect": ["color"]},
    ]}}
    summary = schema_expectation_satisfaction(
        schemas, {}, rules={}, kinds={}, edges=[], interps=[],
    )
    assert summary["widget"] == {"total": 0, "satisfied": 0, "concepts": 0}


def test_schema_expectation_satisfaction_is_domain_aware() -> None:
    """A domain sense's own `expectations:` (§15.4) roll up too — a distinct
    declared shape, never merged with (or falling back to) a shared-tier
    schema of the same name (`ontology.effective_schema`'s reading). No
    shared-tier `vessel` schema exists at all here, so without
    *domain_schemas* this type would be invisible to the roll-up entirely —
    the gap the previous wave flagged."""
    domain_schemas = {
        "bsg-reimagined": {
            "vessel": {"type": "vessel", "domain": "bsg-reimagined", "expectations": [
                {"id": "vessel-class", "expect": ["vessel_class"]},
            ]},
        },
    }
    facts_by_id = {
        "galactica": {
            "id": "galactica", "type": "vessel", "domain": "bsg-reimagined",
            "claims": [{"id": "galactica:vc", "predicate": "vessel_class",
                       "value": "battlestar"}],
        },
        "pegasus": {"id": "pegasus", "type": "vessel", "domain": "bsg-reimagined",
                   "claims": []},
    }
    summary = schema_expectation_satisfaction(
        {}, facts_by_id, rules={}, kinds={}, edges=[], interps=[],
        domain_schemas=domain_schemas,
    )
    assert summary["vessel @ bsg-reimagined"] == {"total": 2, "satisfied": 1, "concepts": 2}
    assert "vessel" not in summary  # no shared-tier schema declares expectations


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


# --------------------------------------------------------------- format_shape


def test_format_shape_values_vocab() -> None:
    assert format_shape({"values": ["black", "brown", "grey"]}) == "one of: black, brown, grey"


def test_format_shape_relational_target() -> None:
    assert format_shape({"target": "organization"}) == "target: organization"


def test_format_shape_relational_target_list() -> None:
    assert format_shape({"target": ["organization", "system"]}) == "target: organization|system"


def test_format_shape_value_kind() -> None:
    money = {"kind": "money", "description": "d",
            "shape": {"amount": {"constraint": "decimal"},
                      "currency": {"constraint": "iso-4217"}},
            "required": ["amount", "currency"]}
    assert format_shape({"value": "money", "kind": money}) == (
        "shape: money {amount: decimal, currency: iso-4217} required: amount, currency")


def test_format_shape_unresolved_kind_reference_degrades_to_the_name() -> None:
    """A `value:` kind name the caller couldn't resolve (not in the loaded
    set) still renders something, rather than nothing."""
    assert format_shape({"value": "money"}) == "shape: money"


def test_format_shape_empty_is_omitted() -> None:
    assert format_shape({}) == ""


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


# --------------------------------------------------- `id:`/`related:` in a real rule


def test_evaluate_demands_when_uses_id_condition_with_lineage() -> None:
    """The `evaluate_demands` `when` match threads *lineage* through to
    `id:` conditions, not just the standalone `condition_matches` entry
    point (§14)."""
    rule = {"r": {"id": "r", "description": "d", "when": {"id": {"equals": "old-id"}},
                 "owes": [{"field": "f"}]}}
    fact = {"id": "new-id", "type": "person"}
    demands = evaluate_demands(
        fact, rules=rule, schemas={}, kinds={}, facts_by_id={"new-id": fact}, edges=[],
        interps=[], lineage={"old-id": "new-id"},
    )
    assert len(demands) == 1
    assert demands[0]["state"] == "open"
    # without the lineage map, the retired id no longer selects the fact
    assert evaluate_demands(
        fact, rules=rule, schemas={}, kinds={}, facts_by_id={"new-id": fact}, edges=[],
        interps=[],
    ) == []


def test_evaluate_demands_when_uses_related_condition() -> None:
    rule = {
        "r": {"id": "r", "description": "d",
             "when": {"related": {"via": "object", "where": {"type": "organization"}}},
             "owes": [{"field": "job_title"}]},
    }
    steven = {"id": "steven", "type": "person",
             "claims": [{"predicate": "employed_by", "object": "acme"}]}
    acme = {"id": "acme", "type": "organization"}
    facts_by_id = {"steven": steven, "acme": acme}
    demands = evaluate_demands(
        steven, rules=rule, schemas={}, kinds={}, facts_by_id=facts_by_id, edges=[],
        interps=[],
    )
    assert len(demands) == 1
    assert demands[0]["field"] == "job_title"
    assert demands[0]["state"] == "open"
    # a person with no employer neighbor owes nothing under this rule
    lonely = {"id": "lonely", "type": "person"}
    assert evaluate_demands(
        lonely, rules=rule, schemas={}, kinds={}, facts_by_id={"lonely": lonely}, edges=[],
        interps=[],
    ) == []


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


def test_check_needs_demand_naming_a_named_expectation_is_clean(system: Path) -> None:
    """A needs entry may name a schema expectation's `id:` (§4.4, §13.1) —
    the demand-rule namespace, not just declared `demands/` rules."""
    _write_schema(system / "ledger", "artist", (
        "type: artist\ndescription: d\nfields:\n  genre: {}\n"
        "expectations:\n  - id: artist-genre\n    expect: [genre]\n"
    ))
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _interp(system, {
        "id": "gap", "kind": "assessment", "about": ["x"], "statement": "s", "reasoning": "r",
        "based_on": [f"corpus://{H_PUB}"], "status": "standing", "asof": "2026-07-02",
        "needs": [{"action": "search", "demand": "artist-genre", "why": "…"}],
    })
    rep = _check(system)
    assert not any("undeclared demand rule" in e for e in rep.errors)
    assert not any("positional display id" in e for e in rep.errors)


def test_check_positional_expectation_demand_gets_the_pointer_error(system: Path) -> None:
    """A needs entry naming the positional display id gets a dedicated error
    naming the one-line fix (§14), not the generic undeclared-rule message."""
    _write_schema(system / "ledger", "artist", (
        "type: artist\ndescription: d\nfields:\n  genre: {}\n"
        "expectations:\n  - expect: [genre]\n"
    ))
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _interp(system, {
        "id": "gap", "kind": "assessment", "about": ["x"], "statement": "s", "reasoning": "r",
        "based_on": [f"corpus://{H_PUB}"], "status": "standing", "asof": "2026-07-02",
        "needs": [{"action": "search", "demand": "expectation:artist[0]", "why": "…"}],
    })
    rep = _check(system)
    assert not any("undeclared demand rule" in e for e in rep.errors)
    msg = next(e for e in rep.errors if "positional display id" in e)
    assert "expectation:artist[0]" in msg
    assert "never a blocking target" in msg
    assert "schemas/artist.yaml" in msg
    assert "demands/<slug>.yaml" in msg


def test_check_expectation_id_colliding_with_a_declared_rule_is_an_error(system: Path) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\nwhen: { type: artist }\nowes: [{ field: f }]\n"
    ))
    _write_schema(system / "ledger", "artist", (
        "type: artist\ndescription: d\nfields:\n  f: {}\n"
        "expectations:\n  - id: hat-colour\n    expect: [f]\n"
    ))
    rep = _check(system)
    assert any("collides with declared demand rule" in e and "hat-colour" in e
              for e in rep.errors)


def test_expectation_id_declared_in_two_schemas_is_an_error(system: Path) -> None:
    _write_schema(system / "ledger", "artist", (
        "type: artist\ndescription: d\nfields:\n  f: {}\n"
        "expectations:\n  - id: shared-id\n    expect: [f]\n"
    ))
    _write_schema(system / "ledger", "album", (
        "type: album\ndescription: d\nfields:\n  g: {}\n"
        "expectations:\n  - id: shared-id\n    expect: [g]\n"
    ))
    rep = _check(system)
    assert any("declared in more than one schema" in e and "shared-id" in e
              for e in rep.errors)


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


def test_regen_vocab_demand_rules_section_lists_named_expectations(system: Path) -> None:
    """A named expectation (§4.4) shares the "Demand rules" section with
    declared rules (§13.1) — same matching-fact count semantics, definition
    marked as a schema expectation rather than a hand-curated cell."""
    _write_schema(system / "ledger", "artist", (
        "type: artist\ndescription: d\nfields:\n  genre: {}\n"
        "expectations:\n"
        "  - id: artist-genre\n    description: every artist owes a genre\n"
        "    expect: [genre]\n"
    ))
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _fact(system, "artist", {"id": "y", "type": "artist", "name": "Y",
                             "claims": [_claim("y", "g", predicate="genre")]})
    _regen(system)
    vocab = (system / "ledger" / "facts" / "VOCAB.md").read_text()
    assert "## Demand rules" in vocab
    assert ("| `artist-genre` | 2 | every artist owes a genre "
            "(schema expectation) |") in vocab


# ---------------------------------------------- `id:`/`related:` check integration (v30)


def test_check_related_bad_via_is_an_error(system: Path) -> None:
    _rule(system, "bad", (
        "id: bad\ndescription: d\nwhen: { related: { via: bogus } }\nowes: [{ field: f }]\n"
    ))
    rep = _check(system)
    assert any("related.via: must be one of" in e for e in rep.errors)


def test_check_related_edge_only_under_via_edge_is_an_error(system: Path) -> None:
    _rule(system, "bad", (
        "id: bad\ndescription: d\n"
        "when: { related: { via: object, edge: { relationship: {} } } }\n"
        "owes: [{ field: f }]\n"
    ))
    rep = _check(system)
    assert any("related.edge: only admissible under via: edge" in e for e in rep.errors)


def test_check_related_nested_related_in_where_is_an_error(system: Path) -> None:
    _rule(system, "bad", (
        "id: bad\ndescription: d\n"
        "when: { related: { via: object, where: { related: { via: entity } } } }\n"
        "owes: [{ field: f }]\n"
    ))
    rep = _check(system)
    assert any("not allowed inside a where" in e for e in rep.errors)


def test_check_id_condition_bad_operator_is_an_error(system: Path) -> None:
    _rule(system, "bad", (
        "id: bad\ndescription: d\nwhen: { id: { bogus: x } }\nowes: [{ field: f }]\n"
    ))
    rep = _check(system)
    assert any("unknown operator 'bogus'" in e for e in rep.errors)


def test_check_well_formed_id_and_related_rules_are_clean(system: Path) -> None:
    _rule(system, "hosts-appointment", (
        "id: hosts-appointment\ndescription: d\n"
        "when: { all_of: [{ claim: { predicate: appointment } }, "
        "{ none_of: [{ id: { equals: steven-rahn } }] }] }\n"
        "owes: [{ field: location }]\n"
    ))
    _rule(system, "employed", (
        "id: employed\ndescription: d\n"
        "when: { related: { via: object, where: { type: organization } } }\n"
        "owes: [{ field: job_title }]\n"
    ))
    _fact(system, "person", {
        "id": "dr-smith", "type": "person", "name": "Dr Smith",
        "claims": [_claim("dr-smith", "appt", predicate="appointment", value="2026-09-01")],
    })
    rep = _check(system)
    assert not any("hosts-appointment" in e or "employed" in e for e in rep.errors)


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
    assert out.strip() == "all 1 demands satisfied"  # footer, not silence
    rc = ledger_main(["demands", "bob", "--all", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SATISFIED" in out
    assert "← bob:colour" in out  # names the satisfying claim


def test_cli_demands_no_demands_apply_footer(system: Path, capsys) -> None:
    """No rule/expectation/expected-field fires for this fact at all — a
    fully-satisfied evaluation and a no-demands-apply one must read
    differently, and neither prints silently (both scribes hit that)."""
    _fact(system, "person", {"id": "bob", "type": "person", "name": "Bob"})
    rc = ledger_main(["demands", "bob", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "no demands apply"


def test_cli_demands_renders_the_shape(system: Path, capsys) -> None:
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "relationship.yaml").write_text(
        "type: relationship\ndescription: a tie\n"
        "fields:\n  kind: { values: [friend, sibling] }\n"
    )
    _rule(system, "kind-rule", (
        "id: kind-rule\ndescription: d\nwhen: { type: relationship }\n"
        "owes: [{ field: kind }]\n"
    ))
    _fact(system, "person", {"id": "a", "type": "person", "name": "A",
                             "claims": [_claim("a", "email", predicate="email")]})
    _fact(system, "person", {"id": "b", "type": "person", "name": "B",
                             "claims": [_claim("b", "email", predicate="email")]})
    _fact(system, "relationship", {"id": "a--b", "type": "relationship",
                                   "participants": ["a", "b"]})
    rc = ledger_main(["demands", "a--b", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "one of: friend, sibling" in out  # the shape, rendered — no YAML dump needed


def test_cli_demands_omits_shape_line_when_nothing_declared(system: Path, capsys) -> None:
    _rule(system, "hat-colour", (
        "id: hat-colour\ndescription: d\n"
        "when: { claim: { predicate: wearing } }\nowes: [{ field: hat_colour }]\n"
    ))
    _fact(system, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "claims": [_claim("bob", "wearing", predicate="wearing", value="hat")],
    })
    rc = ledger_main(["demands", "bob", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "shape:" not in out  # no declared shape — no "shape: none" noise


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


# --------------------------------------------- normalization_intent trailer (v31)


def test_cli_demands_prints_normalization_intent_trailer(system: Path, capsys) -> None:
    """The type's declared `normalization_intent` (§4.4) surfaces at the
    demand surface (§6.3's enqueue-with-intent seam is agent-side; this is
    just making the intent readable where the fields it's owed for live)."""
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "person.yaml").write_text(
        "type: person\ndescription: d\n"
        "normalization_intent: |\n"
        "  Transcriptions want per-track structural marks.\n"
    )
    _fact(system, "person", {"id": "bob", "type": "person", "name": "Bob"})
    rc = ledger_main(["demands", "bob", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "normalization_intent (schemas/person.yaml):" in out
    assert "Transcriptions want per-track structural marks." in out


def test_cli_demands_omits_intent_trailer_when_undeclared(system: Path, capsys) -> None:
    _fact(system, "person", {"id": "bob", "type": "person", "name": "Bob"})
    rc = ledger_main(["demands", "bob", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "normalization_intent" not in out


def test_cli_demands_draft_prints_normalization_intent_trailer(
    system: Path, tmp_path: Path, capsys,
) -> None:
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "person.yaml").write_text(
        "type: person\ndescription: d\nnormalization_intent: intent prose\n"
    )
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({"id": "future-bob", "type": "person"}), encoding="utf-8")
    rc = ledger_main(["demands", "--draft", str(draft), "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "normalization_intent (schemas/person.yaml):" in out
    assert "intent prose" in out


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


# ------------------------------- `ath ledger regen` expectation-satisfaction feedback (v32)


def test_cli_regen_prints_satisfaction_line_when_population_fully_satisfies(
    system: Path, capsys,
) -> None:
    """The live-instance finding: minting a schema whose expectations the
    population already satisfies produces silence everywhere else (the
    §7.4 frontier only ever lists open/blocked demands) — `regen` now
    surfaces it directly."""
    _write_schema(system / "ledger", "artist", (
        "type: artist\ndescription: d\nfields:\n  genre: {}\n"
        "expectations:\n  - id: artist-genre\n    expect: [genre]\n"
    ))
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [_claim("x", "genre", predicate="genre", value="jazz")],
    })
    rc = ledger_main(["regen", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "artist: 1/1 expectations satisfied (1 concept)" in out


def test_cli_regen_prints_zero_concepts_bound_distinctly_from_satisfied(
    system: Path, capsys,
) -> None:
    """A schema whose `expectations:` matches no concept in the population
    (here: no `widget` concept exists at all) must not read like the
    all-satisfied case above — a bare "0/0" would look identical to it."""
    _write_schema(system / "ledger", "widget", (
        "type: widget\ndescription: d\nfields:\n  color: {}\n"
        "expectations:\n  - id: widget-color\n    expect: [color]\n"
    ))
    rc = ledger_main(["regen", "--root", str(system)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "widget: expectations bind 0 concepts" in out
    assert "widget: 0/0" not in out
