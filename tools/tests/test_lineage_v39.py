"""The v39 lineage row object form — `facts/LINEAGE.json` (spec/ledger.md §4.1):
`"old-id": {"to": "survivor-id", "reason": "merged" | "renamed"}`.

Covers the loader (`ledger.model.load_lineage`/`load_lineage_rows`), the writer
(`ledger.merge`), and `ledger.check`'s Graph-block validation of the new shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.merge import apply_merge, plan_merge
from ledger.model import LINEAGE_REASONS, load_lineage, load_lineage_rows

# ============================================================ load_lineage(_rows)


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_lineage(tmp_path) == ({}, [])
    assert load_lineage_rows(tmp_path) == ({}, [])


def _write(root: Path, obj: object) -> None:
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "facts" / "LINEAGE.json").write_text(json.dumps(obj), encoding="utf-8")


def test_v39_object_row_resolves_and_carries_reason(tmp_path: Path) -> None:
    _write(tmp_path, {"old": {"to": "survivor", "reason": "merged"}})
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {"old": "survivor"}
    assert errors == []
    rows, row_errors = load_lineage_rows(tmp_path)
    assert rows == {"old": {"to": "survivor", "reason": "merged"}}
    assert row_errors == []


def test_renamed_reason_accepted(tmp_path: Path) -> None:
    _write(tmp_path, {"old": {"to": "new", "reason": "renamed"}})
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {"old": "new"}
    assert errors == []


def test_legacy_flat_string_row_still_resolves_but_errors(tmp_path: Path) -> None:
    """Tooling stays operable while red: a pre-v39 flat-string row still
    populates the resolution map, but is reported as needing migration."""
    _write(tmp_path, {"old": "survivor"})
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {"old": "survivor"}
    assert len(errors) == 1
    assert "not in v39 object form" in errors[0]
    assert '"to"' in errors[0] and '"reason"' in errors[0]


def test_unknown_reason_is_an_error_and_row_is_dropped(tmp_path: Path) -> None:
    _write(tmp_path, {"old": {"to": "survivor", "reason": "bogus"}})
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {}
    assert any("reason 'bogus' not in" in e for e in errors)


def test_missing_to_is_an_error_and_row_is_dropped(tmp_path: Path) -> None:
    _write(tmp_path, {"old": {"reason": "merged"}})
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {}
    assert any("missing string `to`" in e for e in errors)


def test_non_object_non_string_row_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path, {"old": 42})
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {}
    assert any("must be an object" in e for e in errors)


def test_unknown_row_keys_are_an_error(tmp_path: Path) -> None:
    _write(tmp_path, {"old": {"to": "survivor", "reason": "merged", "bogus": 1}})
    _, errors = load_lineage_rows(tmp_path)
    assert any("unknown keys ['bogus']" in e for e in errors)


def test_non_object_top_level_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path, ["not", "a", "map"])
    lineage, errors = load_lineage(tmp_path)
    assert lineage == {}
    assert any("top level must be a JSON object" in e for e in errors)


def test_lineage_reasons_closed_vocabulary() -> None:
    assert {"merged", "renamed"} == LINEAGE_REASONS


# ============================================================================ check


def _fact(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _check(root: Path):
    return run_check(root, CorpusJoin([]), {}, no_corpus=True)


def test_check_accepts_v39_object_rows(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _fact(tmp_path, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _write(tmp_path, {"old": {"to": "survivor", "reason": "merged"}})
    rep = _check(tmp_path)
    assert not any("LINEAGE" in e for e in rep.errors)


def test_check_flags_unknown_reason(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _fact(tmp_path, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _write(tmp_path, {"old": {"to": "survivor", "reason": "bogus"}})
    rep = _check(tmp_path)
    assert any("reason 'bogus' not in" in e for e in rep.errors)


def test_check_flags_legacy_flat_row(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _fact(tmp_path, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _write(tmp_path, {"old": "survivor"})
    rep = _check(tmp_path)
    assert any("not in v39 object form" in e for e in rep.errors)


# ============================================================================ merge


def _part(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def test_merge_writes_object_row_reason_merged(tmp_path: Path) -> None:
    (tmp_path / "interpretations").mkdir()
    _part(tmp_path, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    _part(tmp_path, "part", {"id": "bcm-old", "type": "part", "name": "BCM Old"})
    plan = plan_merge(tmp_path, None, "bcm-old", "bcm")
    assert plan["errors"] == []
    assert plan["lineage_row"] == {"bcm-old": {"to": "bcm", "reason": "merged"}}
    apply_merge(tmp_path, plan)
    lineage = json.loads((tmp_path / "facts" / "LINEAGE.json").read_text(encoding="utf-8"))
    assert lineage == {"bcm-old": {"to": "bcm", "reason": "merged"}}
