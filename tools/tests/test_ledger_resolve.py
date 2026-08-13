"""The uncommitted derived index + `ath ledger resolve` (spec/ledger.md; #174)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from ledger.index import build_index, is_fresh, load_or_build, resolve_query

H1 = "a" * 64
H2 = "b" * 64
H3 = "c" * 64


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


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    return tmp_path


def _ids(cands: list[dict]) -> list[str]:
    return [c["id"] for c in cands]


# --------------------------------------------------------------------- basis


def test_exact_id_match(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "body-control-module", "type": "part", "name": "BCM"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "body-control-module")
    assert cands[0]["id"] == "body-control-module"
    assert cands[0]["basis"] == "id"


def test_slugified_query_matches_id(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "body-control-module", "type": "part", "name": "BCM"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "Body Control Module")
    assert cands[0]["id"] == "body-control-module"
    assert cands[0]["basis"] == "id"


def test_alias_exact_match(ledger: Path) -> None:
    _fact(ledger, "part", {
        "id": "body-control-module", "type": "part", "name": "Body Control Module",
        "aliases": ["BCM"],
    })
    idx = build_index(ledger)
    cands = resolve_query(idx, "BCM")
    assert cands[0]["id"] == "body-control-module"
    assert cands[0]["basis"] == "alias"


def test_token_subset_match(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "control body")  # order-independent, subset of tokens
    assert cands and cands[0]["id"] == "bcm"
    assert cands[0]["basis"] == "tokens"


def test_id_prefix_match(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "body-control-module", "type": "part", "name": "BCM"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "body-control")
    assert cands and cands[0]["id"] == "body-control-module"
    assert cands[0]["basis"] == "id-prefix"


def test_substring_match(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module Assembly"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "control module")
    assert cands and cands[0]["id"] == "bcm"
    assert cands[0]["basis"] == "substring"


def test_no_match_returns_empty(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    idx = build_index(ledger)
    assert resolve_query(idx, "nonexistent-thingamajig") == []


# ---------------------------------------------------------------------- filters


def test_type_filter(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    _fact(ledger, "gremlin", {"id": "bcm2", "type": "gremlin", "name": "Body Control Module"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "Body Control Module", type_filter="part")
    assert _ids(cands) == ["bcm"]


def test_interpretations_excluded_by_default_and_included_with_flag(ledger: Path) -> None:
    _interp(ledger, {
        "id": "torque-hypothesis", "kind": "hypothesis",
        "about": ["bcm"], "statement": "s", "based_on": [f"corpus://{H1}"],
        "status": "open", "asof": "2026-08-01",
    })
    idx = build_index(ledger)
    assert resolve_query(idx, "torque-hypothesis") == []
    cands = resolve_query(idx, "torque-hypothesis", include_interpretations=True)
    assert _ids(cands) == ["torque-hypothesis"]
    assert cands[0]["kind"] == "interpretation"


# ---------------------------------------------------------------------- redirects


def test_redirect_chases_to_survivor_and_loser_never_surfaces(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    _fact(ledger, "part", {"id": "bcm-old", "type": "part", "merged_into": "bcm"})
    idx = build_index(ledger)

    cands = resolve_query(idx, "bcm-old")
    assert len(cands) == 1
    assert cands[0]["id"] == "bcm"
    assert cands[0]["basis"] == "redirect"
    assert "bcm-old" in cands[0]["note"]

    # the tombstone id never appears as a candidate under any query
    all_cands = resolve_query(idx, "Body Control Module")
    assert "bcm-old" not in _ids(all_cands)


# -------------------------------------------------------------------------- dedupe


def test_dedupe_keeps_strongest_basis(ledger: Path) -> None:
    # id "bcm" AND name "bcm" both point at the same fact — id (rank 0) wins
    # over the substring/tokens bases the name text would otherwise produce.
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "bcm"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "bcm")
    assert len(cands) == 1
    assert cands[0]["basis"] == "id"


def test_resolve_query_limit(ledger: Path) -> None:
    for i in range(5):
        _fact(ledger, "part", {"id": f"widget-{i}", "type": "part", "name": f"Widget {i}"})
    idx = build_index(ledger)
    cands = resolve_query(idx, "widget", limit=2)
    assert len(cands) == 2


# ------------------------------------------------------------------------ citations


def test_citations_map(ledger: Path) -> None:
    _fact(ledger, "part", {
        "id": "bcm", "type": "part", "name": "Body Control Module",
        "sources": {"s1": {"record": H1}},
        "claims": [{
            "id": "bcm:location", "predicate": "location", "value": "under dash",
            "status": "confirmed", "asof": "2026-08-01",
            "evidence": [{"source": "s1", "kind": "direct"}],
        }],
        "artifacts": [{"uri": f"corpus://{H1}", "role": "documents"}],
    })
    _interp(ledger, {
        "id": "bcm-guess", "kind": "hypothesis", "about": ["bcm"], "statement": "s",
        "based_on": [f"corpus://{H1}?el=2"], "status": "open", "asof": "2026-08-01",
    })
    idx = build_index(ledger)
    bucket = idx["citations"][H1]
    assert bucket["claims"] == ["bcm:location"]
    assert bucket["rosters"] == ["bcm"]
    assert bucket["based_on"] == ["bcm-guess"]


# --------------------------------------------------------------------- tolerance


def test_unparseable_file_skipped_without_error(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    bad = ledger / "facts" / "part" / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    idx = build_index(ledger)
    assert "bcm" in idx["entries"]
    assert any("broken.json" in s for s in idx["skipped"])


# ----------------------------------------------------------------------- caching


def test_staleness_triggers_rebuild(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    idx1 = load_or_build(ledger)
    assert "bcm" in idx1["entries"]

    p = _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "New Name"})
    # bump mtime unambiguously past whatever the first write landed at, since
    # some filesystems have coarse mtime resolution.
    future = time.time() + 5
    os.utime(p, (future, future))

    assert not is_fresh(ledger)
    idx2 = load_or_build(ledger)
    assert idx2["entries"]["bcm"]["name"] == "New Name"


def test_unchanged_tree_loads_from_cache(ledger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    load_or_build(ledger)
    assert is_fresh(ledger)

    calls = []
    import ledger.index as index_mod
    real_build = index_mod.build_index
    monkeypatch.setattr(index_mod, "build_index",
                        lambda root: (calls.append(1), real_build(root))[1])
    load_or_build(ledger)
    assert calls == []  # cache hit — build_index never called again


def test_unwritable_cache_degrades_gracefully(ledger: Path) -> None:
    _fact(ledger, "part", {"id": "bcm", "type": "part", "name": "Body Control Module"})
    cache_dir = ledger / ".cache"
    cache_dir.mkdir()
    cache_dir.chmod(0o500)  # read+execute, no write
    try:
        idx = load_or_build(ledger)
        assert "bcm" in idx["entries"]
        assert not (cache_dir / "ledger-index.json").exists()
    finally:
        cache_dir.chmod(0o700)
