"""Schema `extends:` + `requires_domain:` (spec/ledger.md §15.3, §4.4) —
structural half: type-level and field-level `extends:` parsing, the chain
lint (acyclic, spine-terminated where declared), the `spine_references` seam,
and `requires_domain: true` (string-presence only — resolving `domain:` to a
domain concept is out of scope here)."""

from __future__ import annotations

import json
from pathlib import Path

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.schemas import extends_chain_errors, load_schemas, spine_references

# =============================================================== load_schemas


def _write_schema(root: Path, name: str, text: str) -> None:
    d = root / "schemas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_minimal_schema_with_extends_only_is_legal(tmp_path: Path) -> None:
    _write_schema(tmp_path, "song", (
        "type: song\ndescription: A recorded work.\n"
        'extends: "bfo:generically dependent continuant"\n'
    ))
    schemas, errors = load_schemas(tmp_path)
    assert errors == []
    assert schemas["song"]["extends"] == "bfo:generically dependent continuant"


def test_extends_naming_another_declared_type(tmp_path: Path) -> None:
    _write_schema(tmp_path, "vehicle", (
        'type: vehicle\ndescription: A vehicle.\nextends: "cco:Artifact"\n'
    ))
    _write_schema(tmp_path, "car", (
        "type: car\ndescription: A car.\nextends: vehicle\n"
    ))
    schemas, errors = load_schemas(tmp_path)
    assert errors == []
    assert schemas["car"]["extends"] == "vehicle"


def test_extends_must_be_a_non_empty_string(tmp_path: Path) -> None:
    _write_schema(tmp_path, "song", "type: song\ndescription: d\nextends: 42\n")
    _, errors = load_schemas(tmp_path)
    assert any("extends must be a non-empty string" in e for e in errors)


def test_requires_domain_must_be_a_bool(tmp_path: Path) -> None:
    _write_schema(tmp_path, "vessel", (
        "type: vessel\ndescription: d\nrequires_domain: yes-please\n"
    ))
    _, errors = load_schemas(tmp_path)
    assert any("requires_domain must be a bool" in e for e in errors)


def test_requires_domain_true_loads_clean(tmp_path: Path) -> None:
    _write_schema(tmp_path, "character", (
        "type: character\ndescription: d\nrequires_domain: true\n"
    ))
    schemas, errors = load_schemas(tmp_path)
    assert errors == []
    assert schemas["character"]["requires_domain"] is True


def test_field_level_extends_parses(tmp_path: Path) -> None:
    _write_schema(tmp_path, "person", (
        "type: person\ndescription: d\nfields:\n"
        '  father: { target: person, extends: "cco:has_father" }\n'
    ))
    schemas, errors = load_schemas(tmp_path)
    assert errors == []
    assert schemas["person"]["fields"]["father"]["extends"] == "cco:has_father"


def test_field_level_extends_must_be_a_non_empty_string(tmp_path: Path) -> None:
    _write_schema(tmp_path, "person", (
        "type: person\ndescription: d\nfields:\n"
        "  father: { target: person, extends: 7 }\n"
    ))
    _, errors = load_schemas(tmp_path)
    assert any("field 'father' extends must be a non-empty string" in e for e in errors)


# ============================================================== spine_references


def test_spine_references_gathers_type_and_field_level() -> None:
    schemas = {
        "song": {"type": "song", "extends": "bfo:generically dependent continuant"},
        "car": {"type": "car", "extends": "vehicle"},  # not spine-form — excluded
        "person": {
            "type": "person",
            "fields": {"father": {"target": "person", "extends": "cco:has_father"}},
        },
    }
    assert spine_references(schemas) == {
        "bfo:generically dependent continuant", "cco:has_father",
    }


def test_spine_references_empty_when_none_declared() -> None:
    schemas = {"car": {"type": "car", "extends": "vehicle"}}
    assert spine_references(schemas) == set()


# =========================================================== extends_chain_errors


def test_chain_acyclic_and_spine_terminated_is_clean() -> None:
    schemas = {
        "vehicle": {"type": "vehicle", "extends": "cco:Artifact"},
        "car": {"type": "car", "extends": "vehicle"},
    }
    assert extends_chain_errors(schemas) == []


def test_missing_extends_is_not_flagged() -> None:
    """A type with no `extends:` at all is frontier — not this function's business."""
    schemas = {"vehicle": {"type": "vehicle"}}
    assert extends_chain_errors(schemas) == []


def test_chain_running_out_at_a_frontier_type_is_not_an_error() -> None:
    """`car` extends `vehicle`, which itself declares no `extends:` yet — the
    chain is merely incomplete (vehicle's own frontier), not a check error."""
    schemas = {
        "vehicle": {"type": "vehicle"},
        "car": {"type": "car", "extends": "vehicle"},
    }
    assert extends_chain_errors(schemas) == []


def test_self_loop_is_cyclic() -> None:
    schemas = {"car": {"type": "car", "extends": "car"}}
    errors = extends_chain_errors(schemas)
    assert any("cyclic" in e for e in errors)


def test_two_type_cycle_is_cyclic() -> None:
    schemas = {
        "a": {"type": "a", "extends": "b"},
        "b": {"type": "b", "extends": "a"},
    }
    errors = extends_chain_errors(schemas)
    assert len(errors) == 2  # reported from each entry point
    assert all("cyclic" in e for e in errors)


def test_undeclared_non_spine_parent_is_an_error() -> None:
    schemas = {"car": {"type": "car", "extends": "nonexistent-type"}}
    errors = extends_chain_errors(schemas)
    assert any("names neither a declared type nor a spine reference" in e for e in errors)


# ============================================================================ check


def _fact(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _check(root: Path):
    return run_check(root, CorpusJoin([]), {}, no_corpus=True)


def test_check_surfaces_cyclic_extends_chain(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _write_schema(tmp_path, "a", "type: a\ndescription: d\nextends: b\n")
    _write_schema(tmp_path, "b", "type: b\ndescription: d\nextends: a\n")
    rep = _check(tmp_path)
    assert any("cyclic" in e for e in rep.errors)


def test_check_requires_domain_missing_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _write_schema(tmp_path, "character", "type: character\ndescription: d\nrequires_domain: true\n")
    _fact(tmp_path, "character", {"id": "adama", "type": "character", "name": "Adama"})
    rep = _check(tmp_path)
    assert any("requires_domain: true" in e and "no top-level domain:" in e
               for e in rep.errors)


def test_check_requires_domain_satisfied_by_domain_key(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _write_schema(tmp_path, "character", "type: character\ndescription: d\nrequires_domain: true\n")
    _fact(tmp_path, "character", {
        "id": "adama", "type": "character", "name": "Adama", "domain": "bsg-reimagined",
    })
    rep = _check(tmp_path)
    assert not any("requires_domain" in e for e in rep.errors)


def test_check_requires_domain_false_or_absent_imposes_nothing(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _write_schema(tmp_path, "person", "type: person\ndescription: d\n")
    _fact(tmp_path, "person", {"id": "steven", "type": "person", "name": "Steven"})
    rep = _check(tmp_path)
    assert rep.ok, rep.errors
