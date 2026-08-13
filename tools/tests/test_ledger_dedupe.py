"""The coalescence proposer — `ath ledger dedupe` (#177)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ledger._cli import main as ledger_main
from ledger.dedupe import propose

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


def _schema(root: Path, type_: str, obj: dict) -> Path:
    p = root / "schemas" / f"{type_}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(obj), encoding="utf-8")
    return p


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    return tmp_path


def _claim(cid: str, pred: str, *, value: object = None, object_: object = None,
           status: str = "confirmed") -> dict:
    c: dict = {"id": cid, "predicate": pred, "status": status, "asof": "2026-08-01"}
    if value is not None:
        c["value"] = value
    if object_ is not None:
        c["object"] = object_
    return c


# --------------------------------------------------------------------- concepts


def test_name_collision_pair_found(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    _fact(ledger, "part", {"id": "bcm2", "type": "part", "name": "Body Control Module"})
    report = propose(ledger)
    groups = [c for c in report["concepts"] if c["basis"] == "name-collision"]
    assert len(groups) == 1
    assert groups[0]["ids"] == ["bcm", "bcm2"]
    assert groups[0]["key"] == "body control module"


def test_alias_collision_pair_found(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "BCM Alpha",
                            "aliases": ["Body Control Module"]})
    _fact(ledger, "part", {"id": "bcm2", "type": "part", "name": "Body Control Module"})
    report = propose(ledger)
    groups = [c for c in report["concepts"] if c["basis"] == "name-collision"]
    assert len(groups) == 1
    assert sorted(groups[0]["ids"]) == ["bcm", "bcm2"]


def test_id_containment_same_type_found(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bilresa", "type": "part", "name": "Bilresa"})
    _fact(ledger, "part", {
        "id": "bilresa-remote-control-with-scroll-wheel", "type": "part",
        "name": "Bilresa RC Scroll",
    })
    report = propose(ledger)
    groups = [c for c in report["concepts"] if c["basis"] == "id-containment"]
    assert len(groups) == 1
    assert groups[0]["ids"] == ["bilresa", "bilresa-remote-control-with-scroll-wheel"]
    assert groups[0]["type"] == "part"


def test_id_containment_not_reported_across_different_types(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bilresa", "type": "part", "name": "Bilresa"})
    _fact(ledger, "component", {
        "id": "bilresa-remote-control-with-scroll-wheel", "type": "component",
        "name": "Bilresa RC Scroll",
    })
    report = propose(ledger)
    groups = [c for c in report["concepts"] if c["basis"] == "id-containment"]
    assert groups == []


def test_id_containment_skipped_when_already_a_name_collision(ledger: Path) -> None:
    # "bcm" and "bcm-old" collide by name AND bcm's tokens are a subset of
    # bcm-old's — the id-containment pair must not ALSO be reported.
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Widget"})
    _fact(ledger, "part", {"id": "bcm-old", "type": "part", "name": "Widget"})
    report = propose(ledger)
    bases = [c["basis"] for c in report["concepts"]]
    assert bases.count("name-collision") == 1
    assert "id-containment" not in bases


def test_shared_external_id_pair_found_singleton_not(ledger: Path) -> None:
    _fact(ledger, "vehicle", {
        "id": "veh-a", "type": "vehicle", "name": "Car A",
        "claims": [_claim("veh-a:vin", "vin_id", value="1G1ZZZZZZ12345678")],
    })
    _fact(ledger, "vehicle", {
        "id": "veh-b", "type": "vehicle", "name": "Car B",
        "claims": [_claim("veh-b:vin", "vin_id", value="1G1ZZZZZZ12345678")],
    })
    _fact(ledger, "vehicle", {
        "id": "veh-c", "type": "vehicle", "name": "Car C",
        "claims": [_claim("veh-c:vin", "vin", value="9UNIQUE999")],
    })
    report = propose(ledger)
    groups = [c for c in report["concepts"] if c["basis"] == "shared-external-id"]
    assert len(groups) == 1
    assert sorted(groups[0]["ids"]) == ["veh-a", "veh-b"]
    assert groups[0]["key"].startswith("vin_id=")


def test_shared_external_id_ignores_empty_values(ledger: Path) -> None:
    _fact(ledger, "vehicle", {
        "id": "veh-a", "type": "vehicle", "name": "Car A",
        "claims": [_claim("veh-a:vin", "vin_id", value="")],
    })
    _fact(ledger, "vehicle", {
        "id": "veh-b", "type": "vehicle", "name": "Car B",
        "claims": [_claim("veh-b:vin", "vin_id", value="")],
    })
    report = propose(ledger)
    assert [c for c in report["concepts"] if c["basis"] == "shared-external-id"] == []


def test_tombstone_never_in_a_concept_group(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    _fact(ledger, "part", {"id": "bcm-old", "type": "part", "merged_into": "bcm"})
    _fact(ledger, "part", {"id": "bcm2", "type": "part", "name": "Body Control Module"})
    report = propose(ledger)
    all_ids = {i for c in report["concepts"] for i in c["ids"]}
    assert "bcm-old" not in all_ids


def test_interpretation_never_in_a_concept_group(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Widget"})
    _interp(ledger, {
        "id": "widget-hyp", "kind": "hypothesis", "about": ["bcm"],
        "statement": "s", "based_on": [f"corpus://{H1}"], "status": "open",
        "asof": "2026-08-01",
    })
    report = propose(ledger)
    all_ids = {i for c in report["concepts"] for i in c["ids"]}
    assert "widget-hyp" not in all_ids


# ------------------------------------------------------------------- predicates


def test_predicate_one_token_substitution_found(ledger: Path) -> None:
    _fact(ledger, "system", {
        "id": "sys-a", "type": "system", "name": "Sys A",
        "claims": [_claim("sys-a:p1", "shares_service_information_with", object_="sys-b")],
    })
    _fact(ledger, "system", {
        "id": "sys-b", "type": "system", "name": "Sys B",
        "claims": [_claim("sys-b:p1", "shares_service_manual_with", object_="sys-a")],
    })
    report = propose(ledger)
    pair = {frozenset((p["a"], p["b"])) for p in report["predicates"]
            if p["basis"] == "one-token-diff"}
    assert frozenset(("shares_service_information_with", "shares_service_manual_with")) in pair


def test_predicate_token_subset_found(ledger: Path) -> None:
    _fact(ledger, "system", {
        "id": "sys-a", "type": "system", "name": "Sys A",
        "claims": [_claim("sys-a:p1", "located_at", object_="place-1")],
    })
    _fact(ledger, "system", {
        "id": "sys-b", "type": "system", "name": "Sys B",
        "claims": [_claim("sys-b:p1", "located_at_dealer", object_="place-2")],
    })
    report = propose(ledger)
    hits = [p for p in report["predicates"] if p["basis"] == "token-subset"]
    assert any(p["a"] == "located_at" and p["b"] == "located_at_dealer" for p in hits)


def test_predicate_counts_reported(ledger: Path) -> None:
    for i in range(3):
        _fact(ledger, "system", {
            "id": f"sys-{i}", "type": "system", "name": f"Sys {i}",
            "claims": [_claim(f"sys-{i}:p1", "located_at", object_="place-1")],
        })
    _fact(ledger, "system", {
        "id": "sys-x", "type": "system", "name": "Sys X",
        "claims": [_claim("sys-x:p1", "located_at_dealer", object_="place-2")],
    })
    report = propose(ledger)
    hit = next(p for p in report["predicates"] if p["basis"] == "token-subset")
    assert hit["count_a"] == 3
    assert hit["count_b"] == 1


def test_predicate_not_paired_with_itself(ledger: Path) -> None:
    _fact(ledger, "system", {
        "id": "sys-a", "type": "system", "name": "Sys A",
        "claims": [_claim("sys-a:p1", "located_at", object_="place-1")],
    })
    report = propose(ledger)
    assert report["predicates"] == []


# --------------------------------------------------------------------- schemas


def test_schema_field_and_role_usage(ledger: Path) -> None:
    _schema(ledger, "part", {
        "type": "part", "description": "d",
        "fields": {"fitted_to": {}, "unused_field": {}},
        "roster_roles": ["photo", "manual"],
    })
    _fact(ledger, "part", {
        "id": "bcm", "type": "part", "name": "BCM",
        "claims": [_claim("bcm:f", "fitted_to", object_="veh-1")],
        "artifacts": [{"uri": f"corpus://{H1}", "role": "photo"}],
    })
    report = propose(ledger)
    r = next(s for s in report["schemas"]["reports"] if s["type"] == "part")
    assert r["fact_count"] == 1
    assert r["fields"] == {"fitted_to": 1, "unused_field": 0}
    assert r["unused_fields"] == ["unused_field"]
    assert r["roster_roles"] == {"photo": 1, "manual": 0}
    assert r["unused_roles"] == ["manual"]
    assert r["all_fields_unused"] is False


def test_schema_all_fields_unused(ledger: Path) -> None:
    _schema(ledger, "part", {
        "type": "part", "description": "d",
        "fields": {"a": {}, "b": {}},
    })
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    report = propose(ledger)
    r = next(s for s in report["schemas"]["reports"] if s["type"] == "part")
    assert r["all_fields_unused"] is True


def test_schemaless_type_census(ledger: Path) -> None:
    _fact(ledger, "gremlin", {"id": "g1", "type": "gremlin", "name": "G1"})
    _fact(ledger, "gremlin", {"id": "g2", "type": "gremlin", "name": "G2"})
    report = propose(ledger)
    rows = {s["type"]: s["fact_count"] for s in report["schemas"]["schemaless_types"]}
    assert rows["gremlin"] == 2


def test_unparseable_schema_lands_in_skipped_without_error(ledger: Path) -> None:
    (ledger / "schemas").mkdir()
    (ledger / "schemas" / "broken.yaml").write_text("type: [unclosed", encoding="utf-8")
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    report = propose(ledger)
    assert any("broken.yaml" in s for s in report["skipped"])


def test_unparseable_fact_lands_in_skipped_without_error(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    bad = ledger / "facts" / "part" / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    report = propose(ledger)
    assert any("broken.json" in s for s in report["skipped"])


# ------------------------------------------------------------------------- CLI


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    """A full manifest system (`ath ledger` resolves through it) — mirrors
    `test_ledger_check.py`'s fixture, trimmed to what `_system()` needs."""
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "org: https://example.test/org\n"
        "corpora:\n"
        "  corpus:\n"
        "    visibility: public\n"
        "ledger:\n"
        "  ledger:\n"
    )
    (root / "corpora" / "corpus" / "records").mkdir(parents=True)
    ledger_dir = root / "ledger"
    (ledger_dir / "facts").mkdir(parents=True)
    (ledger_dir / "interpretations").mkdir()
    (ledger_dir / "ledger.yaml").write_text("name: ledger\ncorpora: [corpus]\n")
    return root


def test_cli_json_and_section(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger_dir = system / "ledger"
    _fact(ledger_dir, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    _fact(ledger_dir, "part", {"id": "bcm2", "type": "part", "name": "Body Control Module"})

    rc = ledger_main(["dedupe", "--root", str(system), "--json", "--section", "concepts"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "concepts" in payload
    assert "predicates" not in payload
    assert any(c["basis"] == "name-collision" for c in payload["concepts"])


def test_cli_human_readable_default(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fact(system / "ledger", "part", {"id": "bcm", "type": "part", "name": "BCM"})

    rc = ledger_main(["dedupe", "--root", str(system)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "== concepts" in out
    assert "== predicates" in out
    assert "== schemas" in out
