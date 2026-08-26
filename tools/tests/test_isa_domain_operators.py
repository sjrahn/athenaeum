"""The §15.5 condition-grammar growth: the `domain:` fact axis and the
`isa:` operator on `type:`, exercised at the shared implementation
(`ledger.ontology.isa_matches`/`domain_axis_values`/`resolve_domain_operand`)
and through every engine that grows the grammar — demands, scope seeds,
invariants `applies_to` — plus scope's `commitment` parameter.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ath.manifest import Reference, Snapshot
from ledger import ontology
from ledger.demands import (
    _validate_condition,
    condition_matches,
    evaluate_demands,
)
from ledger.invariants import evaluate as evaluate_invariants
from ledger.scope import evaluate_scope, make_resolver

H = "a" * 64

# ============================================================ ontology.isa_matches


def test_isa_matches_own_type() -> None:
    fact = {"type": "vessel"}
    assert ontology.isa_matches(fact, "vessel", schemas={})


def test_isa_matches_shared_tier_chain() -> None:
    schemas = {
        "vessel": {"extends": "artifact-ish"},
        "artifact-ish": {"extends": "cco:Artifact"},
    }
    fact = {"type": "vessel"}
    assert ontology.isa_matches(fact, "artifact-ish", schemas=schemas)
    assert ontology.isa_matches(fact, "cco:Artifact", schemas=schemas)
    assert not ontology.isa_matches(fact, "cco:SomethingElse", schemas=schemas)


def test_isa_matches_domain_minted_chain() -> None:
    domains = {"bsg": {"types": {"vessel": {"extends": "cco:Artifact"}}}}
    live = {"bsg": {}}
    resolve_id = make_resolver(live, {})
    fact = {"type": "vessel", "domain": "bsg"}
    assert ontology.isa_matches(
        fact, "cco:Artifact", schemas={}, domains=domains, resolve_id=resolve_id,
    )


def test_isa_no_match_without_context() -> None:
    fact = {"type": "vessel", "domain": "bsg"}
    # no domains/resolve_id given — only literal/shared-tier chain applies
    assert not ontology.isa_matches(fact, "cco:Artifact", schemas={})


# ------------------------------------------------------------ spine unification


_BFO_OWL = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://purl.obolibrary.org/obo/bfo/"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_0000029">
        <rdfs:label xml:lang="en">site</rdfs:label>
    </owl:Class>
</rdf:RDF>
"""
_BFO_ARTIFACT = "b" * 64


@pytest.fixture()
def bfo_ref(tmp_path: Path) -> Reference:
    p = tmp_path / "bfo.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("BFO-2020-master/21838-2/owl/bfo-core.owl", _BFO_OWL)
    return Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT, path=str(p))},
    )


def test_isa_matches_spine_operand_literal_match_needs_no_mirror() -> None:
    """The chain itself declares the exact spine string the operand names —
    literal comparison succeeds with no references/mirrors at all."""
    schemas = {"vessel": {"extends": "bfo:BFO_0000029"}}
    fact = {"type": "vessel"}
    assert ontology.isa_matches(fact, "bfo:BFO_0000029", schemas=schemas)


def test_isa_matches_spine_operand_unifies_label_and_native_id(bfo_ref: Reference) -> None:
    """The declared chain carries the native id; the operand names the
    label. Literal comparison misses, so unification via
    `refdata.spine.resolve_term` is what makes this match — proven by it
    failing with no references given."""
    schemas = {"vessel": {"extends": "bfo:BFO_0000029"}}
    fact = {"type": "vessel"}
    assert not ontology.isa_matches(fact, "bfo:site", schemas=schemas)  # no references — miss
    assert ontology.isa_matches(
        fact, "bfo:site", schemas=schemas, references=[bfo_ref], corpora_roots=(),
    )


def test_isa_matches_spine_operand_unresolvable_mirror_is_honest_miss(tmp_path: Path) -> None:
    """No mirror bytes materialized anywhere — unification can't run, but
    that's a miss, never a crash (§15.5/§15.2's honestly-unverifiable idiom
    lives at the check layer; isa_matches itself just doesn't match)."""
    ref = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT)},  # no path:, no roots
    )
    schemas = {"vessel": {"extends": "bfo:BFO_0000029"}}
    fact = {"type": "vessel"}
    assert not ontology.isa_matches(fact, "bfo:site", schemas=schemas, references=[ref])


# ===================================================================== domain axis


def test_domain_axis_values_and_operand_resolve_through_lineage() -> None:
    lineage = {"old-name": "bsg-survivor"}
    # fact carries the retired name; domain_axis_values resolves it forward
    assert ontology.domain_axis_values({"domain": "old-name"}, lineage) == ["bsg-survivor"]
    # a rule's operand naming the retired id resolves the same way
    resolved = ontology.resolve_domain_operand({"equals": "old-name"}, lineage)
    assert resolved == {"equals": "bsg-survivor"}


def test_domain_axis_values_empty_when_absent() -> None:
    assert ontology.domain_axis_values({}, {}) == []


# ============================================================================ demands


def test_validate_condition_accepts_isa_only_under_type() -> None:
    assert _validate_condition({"type": {"isa": "cco:Artifact"}}, "when") == []
    # isa is meaningless anywhere else — an unknown operator there
    errors = _validate_condition({"claim": {"predicate": "p", "value": {"isa": "x"}}}, "when")
    assert any("unknown operator 'isa'" in e for e in errors)


def test_validate_condition_accepts_domain_axis() -> None:
    assert _validate_condition({"domain": {"equals": "bsg-reimagined"}}, "when") == []
    assert _validate_condition({"domain": {"in": ["a", "b"]}}, "when") == []


def test_condition_matches_isa_with_ctx() -> None:
    schemas = {"vessel": {"extends": "cco:Artifact"}}
    fact = {"id": "galactica", "type": "vessel"}
    ctx = {"schemas": schemas}
    assert condition_matches({"type": {"isa": "cco:Artifact"}}, fact, [], {"galactica": fact},
                             ctx=ctx)
    assert not condition_matches({"type": {"isa": "cco:Nope"}}, fact, [], {"galactica": fact},
                                 ctx=ctx)


def test_condition_matches_isa_without_ctx_never_matches() -> None:
    fact = {"id": "galactica", "type": "vessel"}
    assert not condition_matches({"type": {"isa": "vessel"}}, fact, [], {"galactica": fact})


def test_condition_matches_domain_axis() -> None:
    fact = {"id": "adama", "type": "character", "domain": "bsg-reimagined"}
    assert condition_matches({"domain": {"equals": "bsg-reimagined"}}, fact, [],
                             {"adama": fact})
    assert not condition_matches({"domain": {"equals": "star-trek"}}, fact, [],
                                 {"adama": fact})
    assert condition_matches({"domain": {"in": ["star-trek", "bsg-reimagined"]}}, fact, [],
                             {"adama": fact})


def test_evaluate_demands_rule_using_isa_and_domain(tmp_path: Path) -> None:
    schemas = {"vessel": {"extends": "cco:Artifact"}}
    domains = {"bsg": {"commitment": "conditional"}}
    facts_by_id = {
        "bsg": {"id": "bsg", "type": "continuity", "ontology": domains["bsg"]},
        "galactica": {"id": "galactica", "type": "vessel", "domain": "bsg"},
    }
    rules = {
        "vessel-needs-class": {
            "id": "vessel-needs-class",
            "when": {"all_of": [
                {"type": {"isa": "cco:Artifact"}},
                {"domain": {"equals": "bsg"}},
            ]},
            "owes": [{"field": "vessel_class"}],
        },
    }
    demands = evaluate_demands(
        facts_by_id["galactica"], rules=rules, schemas=schemas, kinds={},
        facts_by_id=facts_by_id, edges=[], interps=[], domains=domains,
    )
    assert any(d["rule"] == "vessel-needs-class" and d["state"] == "open" for d in demands)

    # a non-vessel, non-domain fact never matches the rule at all
    other = {"id": "steven", "type": "person"}
    facts_by_id2 = dict(facts_by_id, steven=other)
    demands2 = evaluate_demands(
        other, rules=rules, schemas=schemas, kinds={}, facts_by_id=facts_by_id2,
        edges=[], interps=[], domains=domains,
    )
    assert not any(d["rule"] == "vessel-needs-class" for d in demands2)


# ======================================================================= scope


def _write(root: Path, ftype: str, obj: dict) -> None:
    d = root / "facts" / ftype
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{obj['id']}.json").write_text(json.dumps(obj), encoding="utf-8")


def _write_schema(root: Path, name: str, text: str) -> None:
    d = root / "schemas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_scope_seed_match_isa(tmp_path: Path) -> None:
    _write_schema(tmp_path, "vessel", "type: vessel\ndescription: d\nextends: cco:Artifact\n")
    _write(tmp_path, "vessel", {"id": "galactica", "type": "vessel", "name": "Galactica"})
    _write(tmp_path, "person", {"id": "steven", "type": "person", "name": "Steven"})
    result = evaluate_scope(tmp_path, {
        "seed": {"match": {"type": {"isa": "cco:Artifact"}}}, "follow": [],
    })
    assert {m["id"] for m in result["members"]} == {"galactica"}


def test_scope_seed_match_domain_axis(tmp_path: Path) -> None:
    _write(tmp_path, "continuity", {"id": "bsg", "type": "continuity", "name": "BSG",
                                    "ontology": {"commitment": "conditional"}})
    _write(tmp_path, "character", {"id": "adama", "type": "character", "name": "Adama",
                                   "domain": "bsg"})
    _write(tmp_path, "character", {"id": "steven", "type": "character", "name": "Steven"})
    result = evaluate_scope(tmp_path, {
        "seed": {"match": {"domain": {"equals": "bsg"}}}, "follow": [],
    })
    assert {m["id"] for m in result["members"]} == {"adama"}


def test_scope_commitment_include_default_carries_bracket(tmp_path: Path) -> None:
    _write(tmp_path, "continuity", {"id": "bsg", "type": "continuity", "name": "BSG",
                                    "ontology": {"commitment": "conditional"}})
    _write(tmp_path, "character", {"id": "adama", "type": "character", "name": "Adama",
                                   "domain": "bsg"})
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["adama"]}, "follow": []})
    assert result["commitment"]["adama"] == "conditional"
    member = next(m for m in result["members"] if m["id"] == "adama")
    assert member["commitment"] == "conditional"


def test_scope_commitment_exclude_drops_conditional_facts(tmp_path: Path) -> None:
    _write(tmp_path, "continuity", {"id": "bsg", "type": "continuity", "name": "BSG",
                                    "ontology": {"commitment": "conditional"}})
    _write(tmp_path, "character", {"id": "adama", "type": "character", "name": "Adama",
                                   "domain": "bsg"})
    _write(tmp_path, "character", {"id": "steven", "type": "character", "name": "Steven"})
    result = evaluate_scope(tmp_path, {
        "seed": {"type": "character"}, "follow": [], "commitment": "exclude",
    })
    assert {m["id"] for m in result["members"]} == {"steven"}
    assert result["commitment"] == {"steven": "real"}


def test_scope_invalid_commitment_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="commitment"):
        evaluate_scope(tmp_path, {"seed": {"ids": ["a"]}, "commitment": "bogus"})


# ===================================================================== invariants


def test_invariant_applies_to_isa() -> None:
    schemas = {"vessel": {"extends": "cco:Artifact"}}
    inv = {
        "id": "no-dup-class", "constraint": "unique", "severity": "error",
        "applies_to": {"type": {"isa": "cco:Artifact"}, "predicate": "class"},
    }
    fact = {
        "id": "galactica", "type": "vessel",
        "claims": [
            {"id": "galactica:class-1", "predicate": "class", "value": "battlestar"},
            {"id": "galactica:class-2", "predicate": "class", "value": "battlestar"},
        ],
    }
    findings = evaluate_invariants([inv], {Path("v.json"): fact}, schemas=schemas)
    assert any("2 matching claims" in msg for _sev, msg in findings)

    other = {"id": "steven", "type": "person", "claims": []}
    findings2 = evaluate_invariants(
        [inv], {Path("v.json"): fact, Path("p.json"): other}, schemas=schemas,
    )
    # `steven` (a person, not isa cco:Artifact) never contributes a finding
    assert all("steven" not in msg for _sev, msg in findings2)


def test_invariant_applies_to_domain_axis() -> None:
    domains = {"bsg": {"commitment": "conditional"}}
    inv = {
        "id": "bsg-only", "constraint": "unique", "severity": "error",
        "applies_to": {"domain": {"equals": "bsg"}, "predicate": "rank"},
    }
    member = {
        "id": "adama", "type": "character", "domain": "bsg",
        "claims": [
            {"id": "adama:rank-1", "predicate": "rank", "value": "admiral"},
            {"id": "adama:rank-2", "predicate": "rank", "value": "commander"},
        ],
    }
    non_member = {
        "id": "steven", "type": "character",
        "claims": [
            {"id": "steven:rank-1", "predicate": "rank", "value": "a"},
            {"id": "steven:rank-2", "predicate": "rank", "value": "b"},
        ],
    }
    facts = {Path("bsg.json"): {"id": "bsg", "type": "continuity", "ontology": domains["bsg"]},
             Path("adama.json"): member, Path("steven.json"): non_member}
    findings = evaluate_invariants([inv], facts, domains=domains)
    assert any("adama" in msg for _sev, msg in findings)
    assert all("steven" not in msg for _sev, msg in findings)
