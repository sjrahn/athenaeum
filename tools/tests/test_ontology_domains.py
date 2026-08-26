"""The domain layer (spec/ledger.md §15.4): `ledger.ontology`'s pure graph
functions, `ledger.schemas.load_domain_schemas` (domain type senses), and
`ledger.check`'s Ontology block — every guard §13.1's Ontology paragraph
names, exercised end to end over small synthetic ledgers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger import ontology
from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.schemas import load_domain_schemas


def _fact(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _write_schema(root: Path, name: str, text: str) -> None:
    d = root / "schemas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def _write_domain_schema(root: Path, domain: str, name: str, text: str) -> None:
    d = root / "schemas" / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def _check(root: Path):
    return run_check(root, CorpusJoin([]), {}, no_corpus=True)


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    return tmp_path


def _resolver(live: dict[str, dict], lineage: dict[str, str] | None = None):
    from ledger.scope import make_resolver

    return make_resolver(live, lineage or {})


# ============================================================== ontology.py unit


def test_load_domains_finds_ontology_blocks() -> None:
    facts = {
        "bsg": {"id": "bsg", "type": "continuity", "ontology": {"commitment": "conditional"}},
        "plain": {"id": "plain", "type": "person"},
    }
    assert ontology.load_domains(facts) == {"bsg": {"commitment": "conditional"}}


def test_import_closure_is_transitive_and_cycle_safe() -> None:
    domains = {
        "a": {"imports": ["b"]},
        "b": {"imports": ["c"]},
        "c": {"imports": ["a"]},  # cycle back to a
    }
    resolve_id = _resolver({k: {} for k in domains})
    assert ontology.import_closure("a", domains, resolve_id) == {"a", "b", "c"}


def test_commitment_for_fact_conditional_vs_real() -> None:
    domains = {
        "bsg": {"commitment": "conditional"},
        "real-domain": {"commitment": "real"},
    }
    live = {"bsg": {}, "real-domain": {}}
    resolve_id = _resolver(live)
    assert ontology.commitment_for_fact({"domain": "bsg"}, domains, resolve_id) == "conditional"
    assert ontology.commitment_for_fact({"domain": "real-domain"}, domains, resolve_id) == "real"
    assert ontology.commitment_for_fact({}, domains, resolve_id) == "real"
    assert ontology.commitment_for_fact({"domain": "nope"}, domains, resolve_id) == "real"


def test_domain_types_merges_across_closure() -> None:
    domains = {
        "a": {"types": {"vessel": {"extends": "cco:Artifact"}}},
        "b": {"imports": ["a"], "types": {"gadget": {}}},
    }
    resolve_id = _resolver({"a": {}, "b": {}})
    closure = ontology.import_closure("b", domains, resolve_id)
    types = ontology.domain_types(closure, domains)
    assert set(types) == {"vessel", "gadget"}


def test_type_chain_walks_domain_then_shared_then_spine() -> None:
    schemas = {"artifact-ish": {"extends": "cco:Artifact"}}
    dtypes = {"vessel": {"extends": "artifact-ish"}}
    assert ontology.type_chain("vessel", schemas, dtypes) == [
        "vessel", "artifact-ish", "cco:Artifact",
    ]


def test_type_chain_stops_at_frontier() -> None:
    assert ontology.type_chain("orphan", {}, {}) == ["orphan"]


# ============================================================ load_domain_schemas


def test_load_domain_schema_ok(tmp_path: Path) -> None:
    _write_domain_schema(tmp_path, "bsg-reimagined", "vessel", (
        "type: vessel\ndescription: An in-universe craft.\ndomain: bsg-reimagined\n"
        'extends: "cco:Artifact"\n'
    ))
    schemas, errors = load_domain_schemas(tmp_path)
    assert errors == []
    assert schemas["bsg-reimagined"]["vessel"]["domain"] == "bsg-reimagined"


def test_load_domain_schema_mismatched_domain_key_is_an_error(tmp_path: Path) -> None:
    _write_domain_schema(tmp_path, "bsg-reimagined", "vessel", (
        "type: vessel\ndescription: d\ndomain: some-other-domain\n"
    ))
    _, errors = load_domain_schemas(tmp_path)
    assert any("domain 'some-other-domain' != parent directory 'bsg-reimagined'" in e
               for e in errors)


def test_load_domain_schema_values_directory_excluded(tmp_path: Path) -> None:
    """`schemas/values/` is the value-kinds directory (§4.5) — never a domain."""
    d = tmp_path / "schemas" / "values"
    d.mkdir(parents=True)
    (d / "money.yaml").write_text("kind: money\nshape: {}\n", encoding="utf-8")
    schemas, errors = load_domain_schemas(tmp_path)
    assert schemas == {} and errors == []


def test_two_domains_may_mint_the_same_type_name(tmp_path: Path) -> None:
    _write_domain_schema(tmp_path, "bsg-reimagined", "vessel", (
        "type: vessel\ndescription: d\ndomain: bsg-reimagined\n"
    ))
    _write_domain_schema(tmp_path, "star-trek", "vessel", (
        "type: vessel\ndescription: d\ndomain: star-trek\n"
    ))
    schemas, errors = load_domain_schemas(tmp_path)
    assert errors == []
    assert set(schemas) == {"bsg-reimagined", "star-trek"}
    assert "vessel" in schemas["bsg-reimagined"] and "vessel" in schemas["star-trek"]


# ==================================================================== check: valid


def test_valid_domain_and_member_is_clean(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg-reimagined", "type": "continuity", "name": "BSG",
        "ontology": {"commitment": "conditional", "imports": [], "types": {
            "vessel": {"extends": "cco:Artifact", "description": "An in-universe craft."},
        }},
    })
    _fact(ledger, "vessel", {
        "id": "galactica", "type": "vessel", "name": "Galactica", "domain": "bsg-reimagined",
    })
    rep = _check(ledger)
    assert rep.ok, rep.errors


def test_conditional_commitment_read_back_via_ontology(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg-reimagined", "type": "continuity", "name": "BSG",
        "ontology": {"commitment": "conditional"},
    })
    _fact(ledger, "character", {
        "id": "adama", "type": "character", "name": "Adama", "domain": "bsg-reimagined",
    })
    from ledger.model import load_json_dir

    raw, _ = load_json_dir(ledger, "facts/*/*.json")
    live = {o["id"]: o for o in raw.values()}
    domains = ontology.load_domains(live)
    resolve_id = _resolver(live)
    assert ontology.commitment_for_fact(live["adama"], domains, resolve_id) == "conditional"


# =================================================================== check: guards


def test_imports_dag_cycle_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "a", "type": "continuity", "name": "A",
        "ontology": {"imports": ["b"]},
    })
    _fact(ledger, "continuity", {
        "id": "b", "type": "continuity", "name": "B",
        "ontology": {"imports": ["a"]},
    })
    rep = _check(ledger)
    assert any("import cycle" in e for e in rep.errors)


def test_import_naming_a_non_domain_concept_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"imports": ["steven"]},
    })
    _fact(ledger, "person", {"id": "steven", "type": "person", "name": "Steven"})
    rep = _check(ledger)
    assert any("carries no ontology: block" in e for e in rep.errors)


def test_shared_tier_shadowing_is_an_error(ledger: Path) -> None:
    _write_schema(ledger, "vessel", "type: vessel\ndescription: A shared vessel type.\n")
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {"description": "shadowed"}}},
    })
    rep = _check(ledger)
    assert any("already resolves in the shared tier" in e for e in rep.errors)


def test_ambiguous_type_across_import_closure_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "hub", "type": "continuity", "name": "Hub",
        "ontology": {"imports": ["a", "b"]},
    })
    _fact(ledger, "continuity", {
        "id": "a", "type": "continuity", "name": "A",
        "ontology": {"types": {"gadget": {}}},
    })
    _fact(ledger, "continuity", {
        "id": "b", "type": "continuity", "name": "B",
        "ontology": {"types": {"gadget": {}}},
    })
    rep = _check(ledger)
    assert any("ambiguous across this domain's import closure" in e for e in rep.errors)


def test_self_anchoring_own_type_inside_own_closure_is_an_error(ledger: Path) -> None:
    """A domain concept's own type must resolve OUTSIDE its own closure."""
    _fact(ledger, "gadget", {
        "id": "bsg", "type": "gadget", "name": "BSG",
        "ontology": {"types": {"gadget": {}}},
    })
    rep = _check(ledger)
    assert any("no self-anchoring" in e and "own type" in e for e in rep.errors)


def test_self_anchoring_own_domain_inside_own_closure_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG", "domain": "bsg",
        "ontology": {},
    })
    rep = _check(ledger)
    assert any("no self-anchoring" in e and "own domain:" in e for e in rep.errors)


def test_domain_minted_type_without_membership_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {}}},
    })
    _fact(ledger, "vessel", {"id": "galactica", "type": "vessel", "name": "Galactica"})
    rep = _check(ledger)
    assert any("is domain-minted" in e and "carries no domain:" in e for e in rep.errors)


def test_domain_minted_type_with_wrong_domain_membership_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {}}},
    })
    _fact(ledger, "continuity", {
        "id": "other", "type": "continuity", "name": "Other", "ontology": {},
    })
    _fact(ledger, "vessel", {
        "id": "galactica", "type": "vessel", "name": "Galactica", "domain": "other",
    })
    rep = _check(ledger)
    assert any("import closure does not declare it" in e for e in rep.errors)


def test_domain_field_resolving_to_non_domain_concept_is_an_error(ledger: Path) -> None:
    _fact(ledger, "person", {"id": "steven", "type": "person", "name": "Steven"})
    _fact(ledger, "vessel", {
        "id": "galactica", "type": "vessel", "name": "Galactica", "domain": "steven",
    })
    rep = _check(ledger)
    assert any("membership names a domain" in e for e in rep.errors)


def test_dangling_domain_field_is_an_error(ledger: Path) -> None:
    _fact(ledger, "vessel", {
        "id": "galactica", "type": "vessel", "name": "Galactica", "domain": "nope",
    })
    rep = _check(ledger)
    assert any("does not resolve to a living fact" in e for e in rep.errors)


def test_bad_commitment_value_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"commitment": "maybe"},
    })
    rep = _check(ledger)
    assert any("commitment must be one of" in e for e in rep.errors)


def test_unknown_ontology_key_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"bogus": True},
    })
    rep = _check(ledger)
    assert any("unknown keys" in e and "bogus" in e for e in rep.errors)


def test_requires_domain_interplay_with_domain_minted_type(ledger: Path) -> None:
    """A shared-tier type declaring `requires_domain: true` AND happening to
    also be minted by a domain is doubly owed — both guards fire
    independently, which is fine; this just confirms neither one crashes
    the other."""
    _write_schema(ledger, "character", "type: character\ndescription: d\n"
                                       "requires_domain: true\n")
    _fact(ledger, "character", {"id": "adama", "type": "character", "name": "Adama"})
    rep = _check(ledger)
    assert any("requires_domain: true" in e for e in rep.errors)


# ============================================================= harvest domain mint


def test_harvest_mint_domain_resolves_cleanly(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {}}},
    })
    d = ledger / "harvest"
    d.mkdir()
    (d / "vessels.yaml").write_text(
        "id: vessels\ndescription: d\n"
        "match: { origin.host: { equals: example.com } }\n"
        "mint:\n  concept: { id: 'vessel-{origin.path[1]}', type: vessel, "
        "name: '{origin.path[1]}', domain: bsg }\n",
        encoding="utf-8",
    )
    rep = _check(ledger)
    assert not any("mint.concept" in e for e in rep.errors)


def test_harvest_mint_domain_dangling_is_an_error(ledger: Path) -> None:
    d = ledger / "harvest"
    d.mkdir()
    (d / "vessels.yaml").write_text(
        "id: vessels\ndescription: d\n"
        "match: { origin.host: { equals: example.com } }\n"
        "mint:\n  concept: { id: 'vessel-{origin.path[1]}', type: vessel, "
        "name: '{origin.path[1]}', domain: nope }\n",
        encoding="utf-8",
    )
    rep = _check(ledger)
    assert any("mint.concept.domain 'nope' does not resolve" in e for e in rep.errors)


def test_harvest_mint_domain_type_outside_closure_is_an_error(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG", "ontology": {},
    })
    _fact(ledger, "continuity", {
        "id": "other", "type": "continuity", "name": "Other",
        "ontology": {"types": {"vessel": {}}},
    })
    d = ledger / "harvest"
    d.mkdir()
    (d / "vessels.yaml").write_text(
        "id: vessels\ndescription: d\n"
        "match: { origin.host: { equals: example.com } }\n"
        "mint:\n  concept: { id: 'vessel-{origin.path[1]}', type: vessel, "
        "name: '{origin.path[1]}', domain: bsg }\n",
        encoding="utf-8",
    )
    rep = _check(ledger)
    assert any("is domain-minted" in e and "not within domain 'bsg'" in e for e in rep.errors)


# ================================================================ domain-sense schema


def test_domain_sense_schema_validates_claims(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {}}},
    })
    _write_domain_schema(ledger, "bsg", "vessel", (
        "type: vessel\ndescription: d\ndomain: bsg\n"
        "fields:\n  callsign: { values: [galactica, pegasus] }\n"
    ))
    _fact(ledger, "vessel", {
        "id": "ship", "type": "vessel", "name": "Ship", "domain": "bsg",
        "sources": {"s1": {"record": "a" * 64}},
        "claims": [{
            "id": "ship:callsign", "predicate": "callsign", "value": "not-a-real-ship",
            "status": "provisional", "asof": "2026-08-25",
            "evidence": [{"source": "s1", "kind": "direct"}],
        }],
    })
    rep = _check(ledger)
    assert any("not among declared values" in e for e in rep.errors)


def test_domain_sense_schema_roster_roles(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {}}},
    })
    _write_domain_schema(ledger, "bsg", "vessel", (
        "type: vessel\ndescription: d\ndomain: bsg\nroster_roles: [manifests]\n"
    ))
    _fact(ledger, "vessel", {
        "id": "ship", "type": "vessel", "name": "Ship", "domain": "bsg",
        "artifacts": [{"uri": f"corpus://{'a' * 64}", "role": "documents"}],
    })
    rep = _check(ledger)
    assert any("not among the 'vessel' schema's roster_roles" in e for e in rep.errors)


# =============================================================== field-attached invariants


def test_field_attached_invariant_fires(ledger: Path) -> None:
    _write_schema(ledger, "person", (
        "type: person\ndescription: d\nfields:\n"
        "  residence:\n"
        "    target: place\n"
        "    invariants:\n"
        "      - constraint: temporal-no-overlap\n"
        "        severity: error\n"
    ))
    _fact(ledger, "place", {"id": "nyc", "type": "place", "name": "NYC"})
    _fact(ledger, "place", {"id": "la", "type": "place", "name": "LA"})
    _fact(ledger, "person", {
        "id": "bob", "type": "person", "name": "Bob",
        "sources": {"s1": {"record": "a" * 64}},
        "claims": [
            {"id": "bob:residence", "predicate": "residence", "object": "nyc",
             "period": "2020/2022", "status": "provisional", "asof": "2026-08-25",
             "evidence": [{"source": "s1", "kind": "direct"}]},
            {"id": "bob:residence-2", "predicate": "residence", "object": "la",
             "period": "2021/2023", "status": "provisional", "asof": "2026-08-25",
             "evidence": [{"source": "s1", "kind": "direct"}]},
        ],
    })
    rep = _check(ledger)
    assert any("overlapping periods" in e for e in rep.errors)
    assert any(e.startswith("invariant field:person.residence[0]:") for e in rep.errors)


def test_field_attached_invariant_bad_constraint_is_an_error(ledger: Path) -> None:
    _write_schema(ledger, "person", (
        "type: person\ndescription: d\nfields:\n"
        "  residence:\n"
        "    target: place\n"
        "    invariants:\n"
        "      - constraint: bogus\n"
    ))
    rep = _check(ledger)
    assert any("constraint must be one of" in e for e in rep.errors)


def test_field_attached_invariant_on_domain_schema(ledger: Path) -> None:
    _fact(ledger, "continuity", {
        "id": "bsg", "type": "continuity", "name": "BSG",
        "ontology": {"types": {"vessel": {}}},
    })
    _write_domain_schema(ledger, "bsg", "vessel", (
        "type: vessel\ndescription: d\ndomain: bsg\nfields:\n"
        "  designation:\n"
        "    invariants:\n"
        "      - constraint: unique\n"
    ))
    _fact(ledger, "vessel", {
        "id": "ship", "type": "vessel", "name": "Ship", "domain": "bsg",
        "sources": {"s1": {"record": "a" * 64}},
        "claims": [
            {"id": "ship:designation", "predicate": "designation", "value": "BS-75",
             "status": "provisional", "asof": "2026-08-25",
             "evidence": [{"source": "s1", "kind": "direct"}]},
            {"id": "ship:designation-2", "predicate": "designation", "value": "BS-76",
             "status": "provisional", "asof": "2026-08-25",
             "evidence": [{"source": "s1", "kind": "direct"}]},
        ],
    })
    rep = _check(ledger)
    assert any("2 matching claims" in e for e in rep.errors)


# ==================================================================== effective_schema


def test_effective_schema_prefers_domain_sense() -> None:
    schemas = {"vessel": {"type": "vessel", "fields": {"shared_field": {}}}}
    domain_schemas = {"bsg": {"vessel": {"type": "vessel", "domain": "bsg",
                                        "fields": {"domain_field": {}}}}}
    fact = {"type": "vessel", "domain": "bsg"}
    got = ontology.effective_schema(fact, schemas, domain_schemas)
    assert "domain_field" in got["fields"]
    assert "shared_field" not in got.get("fields", {})


def test_effective_schema_falls_back_to_shared_tier() -> None:
    schemas = {"vessel": {"type": "vessel", "fields": {"shared_field": {}}}}
    fact = {"type": "vessel"}
    got = ontology.effective_schema(fact, schemas, {})
    assert "shared_field" in got["fields"]
