"""Value kinds — `schemas/values/{kind}.yaml` (spec/ledger.md §4.5): declared
typed-value shapes, their check-time enforcement (§13.1 "Value kinds"), and
the shipped adoptable import templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ledger.check import run_check
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.model import ensure_source
from ledger.values import PRIMITIVES, load_kinds, validate_array_value, validate_value

# ---------------------------------------------------------------- primitives


def _kind(constraint: str, **extra) -> dict:
    """A one-field kind declaration `{f: <constraint>}`, `f` required."""
    return {"kind": "k", "description": "d", "shape": {"f": {"constraint": constraint, **extra}},
            "required": ["f"]}


@pytest.mark.parametrize(("constraint", "extra", "good", "bad"), [
    ("string", {}, "hello", 123),
    ("boolean", {}, True, "true"),
    ("number", {}, 3.5, True),          # bool is NOT a number
    ("number", {}, 3, "3"),
    ("integer", {}, 3, 3.5),
    ("integer", {}, 3, True),           # bool is NOT an integer
    ("decimal", {}, "12.50", 12.50),    # a decimal STRING — never a JSON float
    ("decimal", {}, "-3", "abc"),
    ("enum", {"values": ["a", "b"]}, "a", "c"),
    ("pattern", {"pattern": r"^[a-z]+$"}, "abc", "ABC"),
    ("pattern", {"pattern": r"^[a-z]+$"}, "abc", 123),
    ("range", {"min": 0, "max": 10}, 5, 15),
    ("range", {"min": 0, "max": 10}, 0, -1),
    ("iso-date", {}, "2024-01-01", "not-a-date"),
    ("iso-date", {}, "2024-06-15", "2024-13-01"),
    ("iso-instant", {}, "2024-01-01T12:00:00", "2024-01-01"),   # bare date rejected
    ("iso-instant", {}, "2024-01-01T12:00:00Z", "not-an-instant"),
    ("iana-zone", {}, "America/New_York", "Fake/Zone"),
    ("iso-4217", {}, "USD", "US"),
    ("iso-4217", {}, "EUR", "usd"),
    ("iso-4217", {}, "JPY", "ZZZ"),      # well-formed shape, unknown code
    ("latitude", {}, 45.0, 100),
    ("latitude", {}, -90, -90.1),
    ("longitude", {}, -122.4, 200),
    ("longitude", {}, 180, -181),
])
def test_primitive_accepts_and_rejects(constraint, extra, good, bad):
    kind = _kind(constraint, **extra)
    assert validate_value(kind, {"f": good}) == []
    assert validate_value(kind, {"f": bad}) != []


def test_all_primitives_covered_by_the_closed_vocabulary():
    # every primitive named in spec §4.5 is in the closed set the checker knows
    expected = {
        "string", "number", "integer", "boolean", "decimal", "enum", "pattern", "range",
        "iso-instant", "iso-date", "iana-zone", "iso-4217", "latitude", "longitude",
    }
    assert expected == PRIMITIVES


def test_validate_value_reports_missing_required_and_undeclared_fields():
    kind = {"kind": "money", "description": "d",
            "shape": {"amount": {"constraint": "decimal"},
                      "currency": {"constraint": "iso-4217"}},
            "required": ["amount", "currency"]}
    issues = validate_value(kind, {"amount": "5.00", "bogus": 1})
    assert any("missing required field 'currency'" in i for i in issues)
    assert any("undeclared field 'bogus'" in i for i in issues)


def test_validate_value_requires_an_object():
    kind = _kind("string")
    issues = validate_value(kind, "not-a-dict")
    assert issues and "must be an object" in issues[0]


def test_validate_array_value_reports_per_index():
    kind = _kind("string")
    issues = validate_array_value(kind, [{"f": "ok"}, {"f": 5}])
    assert not any(i.startswith("[0]") for i in issues)
    assert any(i.startswith("[1]") for i in issues)


# ---------------------------------------------------------- declaration shape


def _write_kind(root: Path, name: str, text: str) -> None:
    d = root / "schemas" / "values"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_load_kinds_empty_when_no_dir(tmp_path: Path):
    kinds, errors = load_kinds(tmp_path)
    assert kinds == {} and errors == []


def test_load_kinds_well_formed(tmp_path: Path):
    _write_kind(tmp_path, "money", (
        "kind: money\ndescription: An amount of a currency.\n"
        "shape:\n  amount: { constraint: decimal }\n  currency: { constraint: iso-4217 }\n"
        "required: [amount, currency]\n"
    ))
    kinds, errors = load_kinds(tmp_path)
    assert errors == []
    assert set(kinds) == {"money"}
    assert kinds["money"]["description"] == "An amount of a currency."


def test_kind_stem_mismatch_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "money", "kind: wrong-name\ndescription: d\nshape: {}\n")
    kinds, errors = load_kinds(tmp_path)
    assert "money" not in kinds
    assert any("!= filename stem" in e for e in errors)


def test_unknown_constraint_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "bogus", (
        "kind: bogus\ndescription: d\n"
        "shape:\n  f: { constraint: frobnicated }\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("not a known primitive" in e for e in errors)


def test_enum_without_values_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "bad-enum", (
        "kind: bad-enum\ndescription: d\nshape:\n  f: { constraint: enum }\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("enum constraint requires values" in e for e in errors)


def test_values_on_non_enum_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "odd", (
        "kind: odd\ndescription: d\n"
        "shape:\n  f: { constraint: string, values: [a, b] }\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("only admissible on an enum constraint" in e for e in errors)


def test_pattern_without_pattern_key_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "bad-pattern", (
        "kind: bad-pattern\ndescription: d\nshape:\n  f: { constraint: pattern }\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("pattern constraint requires pattern" in e for e in errors)


def test_invalid_regex_pattern_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "bad-regex", (
        "kind: bad-regex\ndescription: d\n"
        "shape:\n  f: { constraint: pattern, pattern: '[' }\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("is not a valid regex" in e for e in errors)


def test_min_max_only_on_range_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "odd-range", (
        "kind: odd-range\ndescription: d\n"
        "shape:\n  f: { constraint: number, min: 0 }\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("min/max is only admissible on a range constraint" in e for e in errors)


def test_required_naming_undeclared_field_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "bad-required", (
        "kind: bad-required\ndescription: d\n"
        "shape:\n  f: { constraint: string }\nrequired: [f, ghost]\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("required names undeclared shape field 'ghost'" in e for e in errors)


def test_unknown_top_level_key_is_an_error(tmp_path: Path):
    _write_kind(tmp_path, "extra-key", (
        "kind: extra-key\ndescription: d\nshape: {}\nbogus: true\n"
    ))
    _, errors = load_kinds(tmp_path)
    assert any("unknown keys ['bogus']" in e for e in errors)


def test_bad_kind_file_is_dropped_tolerantly(tmp_path: Path):
    """One malformed kind file draws an error string but doesn't crash the
    load or take down other, well-formed kinds (parse tolerantly)."""
    _write_kind(tmp_path, "good", (
        "kind: good\ndescription: d\nshape:\n  f: { constraint: string }\n"
    ))
    _write_kind(tmp_path, "junk", "not: [valid, yaml, :::\n")
    kinds, errors = load_kinds(tmp_path)
    assert "good" in kinds
    assert "junk" not in kinds
    assert any("invalid YAML" in e for e in errors)


# --------------------------------------------------------- check integration


H_PUB = "a" * 64
OPENQ_SKELETON = (
    "# Open questions\n\n<!--worklist:begin-->\n<!--worklist:end-->\n\n## Curated\n"
)


def _record(corpus_root: Path, h: str) -> None:
    p = corpus_root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: {h}\ntitle: t\nstatus: normalized\n---\n\nbody\n", encoding="utf-8")


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    root = tmp_path
    inst = root / "corpus"
    _record(inst, H_PUB)
    pub = root / "corpora" / "corpus"
    _record(pub, H_PUB)
    ledger = root / "ledger"
    (ledger / "facts").mkdir(parents=True)
    (ledger / "interpretations").mkdir()
    (ledger / "schemas" / "values").mkdir(parents=True)
    (ledger / "open-questions.md").write_text(OPENQ_SKELETON)
    return root


def _resolve_sources(obj: dict) -> dict:
    sources = obj.setdefault("sources", {})
    for c in obj.get("claims") or []:
        if not isinstance(c, dict):
            continue
        for e in c.get("evidence") or []:
            if not isinstance(e, dict) or "source" in e or "uri" in e:
                continue
            record = e.pop("_record", None)
            if record is not None:
                e["source"] = ensure_source(obj, record=record)
    if not sources:
        del obj["sources"]
    return obj


def _fact(root: Path, type_: str, obj: dict) -> Path:
    obj = _resolve_sources(dict(obj))
    p = root / "ledger" / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _claim(fact_id: str, short: str, **over) -> dict:
    c = {
        "id": f"{fact_id}:{short}",
        "predicate": short.replace("-", "_"),
        "value": "x",
        "status": "provisional",
        "asof": "2026-07-02",
        "evidence": [{"_record": H_PUB, "kind": "direct"}],
    }
    c.update(over)
    return c


def _join(root: Path) -> CorpusJoin:
    return CorpusJoin([RegisteredCorpus("corpus", root / "corpora" / "corpus", private=False)])


def _check(root: Path, **kw):
    return run_check(root / "ledger", _join(root), {}, **kw)


def _schema(root: Path, name: str, text: str) -> None:
    d = root / "ledger" / "schemas"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text, encoding="utf-8")


def _kind_file(root: Path, name: str, text: str) -> None:
    (root / "ledger" / "schemas" / "values" / f"{name}.yaml").write_text(text, encoding="utf-8")


_MONEY_KIND = (
    "kind: money\ndescription: An amount of a currency.\n"
    "shape:\n  amount: { constraint: decimal }\n  currency: { constraint: iso-4217 }\n"
    "required: [amount, currency]\n"
)


def test_typed_field_conforming_value_passes(system: Path):
    _kind_file(system, "money", _MONEY_KIND)
    _schema(system, "purchase", (
        "type: purchase\ndescription: a purchase\n"
        "fields:\n  price: { value: money }\n"
    ))
    _fact(system, "purchase", {
        "id": "p", "type": "purchase", "name": "P",
        "claims": [_claim("p", "price", value={"amount": "12.50", "currency": "USD"})],
    })
    rep = _check(system)
    assert not any("price" in e for e in rep.errors)


def test_typed_field_nonconforming_value_is_an_error_naming_the_claim(system: Path):
    _kind_file(system, "money", _MONEY_KIND)
    _schema(system, "purchase", (
        "type: purchase\ndescription: a purchase\n"
        "fields:\n  price: { value: money }\n"
    ))
    _fact(system, "purchase", {
        "id": "p", "type": "purchase", "name": "P",
        "claims": [_claim("p", "price", value={"amount": 12.5, "currency": "usd"})],
    })
    rep = _check(system)
    price_errors = [e for e in rep.errors if "p:price" in e]
    assert price_errors
    assert any("decimal" in e for e in price_errors)
    assert any("iso-4217" in e or "'usd'" in e for e in price_errors)


def test_typed_field_missing_is_not_an_error(system: Path):
    """A missing typed field is frontier, never an error (§4.4, §14)."""
    _kind_file(system, "money", _MONEY_KIND)
    _schema(system, "purchase", (
        "type: purchase\ndescription: a purchase\n"
        "fields:\n  price: { value: money }\n"
    ))
    _fact(system, "purchase", {
        "id": "p", "type": "purchase", "name": "P",
        "claims": [_claim("p", "note", predicate="note", value="no price yet")],
    })
    rep = _check(system)
    assert not any("price" in e for e in rep.errors)


def test_value_referencing_undeclared_kind_is_an_error(system: Path):
    _schema(system, "purchase", (
        "type: purchase\ndescription: a purchase\n"
        "fields:\n  price: { value: money }\n"
    ))
    _fact(system, "purchase", {"id": "p", "type": "purchase", "name": "P"})
    rep = _check(system)
    assert any("undeclared value kind" in e and "money" in e for e in rep.errors)


def test_element_level_value_validated_inside_arrays(system: Path):
    _kind_file(system, "money", _MONEY_KIND)
    _schema(system, "event", (
        "type: event\ndescription: an event\n"
        "fields:\n"
        "  ticket_prices:\n"
        "    elements:\n"
        "      cost: { value: money }\n"
    ))
    _fact(system, "event", {
        "id": "e", "type": "event", "name": "E",
        "claims": [_claim("e", "prices", predicate="ticket_prices", value=[
            {"cost": {"amount": "10.00", "currency": "USD"}},
            {"cost": {"amount": "not-a-decimal", "currency": "USD"}},
            {"handle": "no cost key here"},
        ])],
    })
    rep = _check(system)
    element_errors = [e for e in rep.errors if "e:prices" in e and "element 'cost'" in e]
    assert element_errors
    assert any("decimal" in e for e in element_errors)


# ---------------------------------------------------- shipped kind templates


_TEMPLATES_DIR = (Path(__file__).parent.parent / "src" / "ath" / "templates" / "value-kinds")


def test_shipped_templates_are_well_formed_kind_declarations(tmp_path: Path):
    """The shipped templates (money, quantity, instant, duration, coordinate)
    are adoptable imports — copy-and-rename into an instance's own
    schemas/values/ — so they must load clean as ordinary kind declarations."""
    names = {"money", "quantity", "instant", "duration", "coordinate"}
    files = {f.stem for f in _TEMPLATES_DIR.glob("*.yaml")}
    assert files == names
    dest = tmp_path / "schemas" / "values"
    dest.mkdir(parents=True)
    for f in _TEMPLATES_DIR.glob("*.yaml"):
        (dest / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    kinds, errors = load_kinds(tmp_path)
    assert errors == []
    assert set(kinds) == names


def test_shipped_templates_carry_the_adoption_header_comment():
    for f in _TEMPLATES_DIR.glob("*.yaml"):
        text = f.read_text(encoding="utf-8")
        assert "Adoptable import template (spec/ledger.md §4.5)" in text
        assert "adoption is a visible diff" in text


def test_money_template_validates_a_conforming_and_nonconforming_value():
    kind = yaml.safe_load((_TEMPLATES_DIR / "money.yaml").read_text(encoding="utf-8"))
    assert validate_value(kind, {"amount": "9.99", "currency": "EUR"}) == []
    assert validate_value(kind, {"amount": 9.99, "currency": "EUR"}) != []


def test_instant_template_validates_required_fields():
    kind = yaml.safe_load((_TEMPLATES_DIR / "instant.yaml").read_text(encoding="utf-8"))
    good = {"at": "2026-01-01T00:00:00Z", "zone": "UTC", "precision": "day"}
    assert validate_value(kind, good) == []
    assert validate_value(kind, {"at": "2026-01-01T00:00:00Z"}) != []  # missing precision
