"""`tools/scripts/migrate_evidence_sources.py` — the inline-`uri` → per-fact
sources-table migration. The script has no package `__init__.py` (it is run
standalone via `uv run --no-sync python scripts/migrate_evidence_sources.py`),
so it is imported here via a `sys.path` insert rather than a package import."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from migrate_evidence_sources import main, migrate_fact

from ledger.check import run_check
from ledger.corpora import CorpusJoin
from ledger.model import canonical_claim_state

H1 = "1" * 64


def _old_fact() -> dict:
    """A fact in the pre-migration shape: two claims repeat the SAME record
    (different anchors — the table's whole reason to exist), one cites a
    `ref://` dataset."""
    return {
        "id": "x", "type": "artist", "name": "X",
        "claims": [
            {"id": "x:a", "predicate": "a", "value": "1", "status": "provisional",
             "evidence": [{"uri": f"corpus://{H1}?el=1", "quote": "q1", "kind": "direct"}]},
            {"id": "x:b", "predicate": "b", "value": "2", "status": "provisional",
             "evidence": [{"uri": f"corpus://{H1}?el=5", "quote": "q2",
                           "kind": "authoritative"}]},
            {"id": "x:c", "predicate": "c", "value": "3", "status": "provisional",
             "evidence": [{"uri": f"ref://musicbrainz/artist/{'9' * 8}",
                           "kind": "authoritative"}]},
        ],
    }


def test_migrate_dedupes_repeated_record_and_handles_ref() -> None:
    fact = _old_fact()
    changed = migrate_fact(fact, where="facts/artist/x.json")
    assert changed is True

    record_entries = [v for v in fact["sources"].values() if "record" in v]
    ref_entries = [v for v in fact["sources"].values() if "ref" in v]
    assert len(record_entries) == 1 and record_entries[0]["record"] == H1
    assert len(ref_entries) == 1
    assert ref_entries[0]["ref"] == f"musicbrainz/artist/{'9' * 8}"

    a_ev, b_ev, c_ev = (c["evidence"][0] for c in fact["claims"])
    assert a_ev["source"] == b_ev["source"]  # same record → deduped to one source
    assert a_ev["anchor"] == "el=1"
    assert b_ev["anchor"] == "el=5"
    assert c_ev["source"] != a_ev["source"]
    assert "anchor" not in c_ev

    for c in fact["claims"]:
        for e in c["evidence"]:
            assert "uri" not in e
            assert "verified" not in e


def test_migrate_is_idempotent() -> None:
    fact = _old_fact()
    migrate_fact(fact, where="facts/artist/x.json")
    snapshot = json.loads(json.dumps(fact))
    changed_again = migrate_fact(fact, where="facts/artist/x.json")
    assert changed_again is False
    assert fact == snapshot


def test_migrate_hoists_newest_verified_stamp(capsys: object) -> None:
    fact = {
        "id": "x", "type": "artist", "name": "X",
        "claims": [
            {"id": "x:a", "predicate": "a", "value": "1", "status": "provisional",
             "evidence": [{"uri": f"corpus://{H1}?el=1", "kind": "direct",
                           "verified": {"touch": "t1", "at": "2026-06-01"}}]},
            {"id": "x:b", "predicate": "b", "value": "2", "status": "provisional",
             "evidence": [{"uri": f"corpus://{H1}?el=2", "kind": "direct",
                           "verified": {"touch": "t2", "at": "2026-07-01"}}]},
        ],
    }
    migrate_fact(fact, where="facts/artist/x.json")
    (key,) = fact["sources"].keys()
    assert fact["sources"][key]["verified"] == {"touch": "t2", "at": "2026-07-01"}
    err = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "differing verified stamps" in err


def test_migrate_json_round_trips() -> None:
    fact = _old_fact()
    migrate_fact(fact, where="facts/artist/x.json")
    text = json.dumps(fact, indent=2, ensure_ascii=False) + "\n"
    reloaded = json.loads(text)
    assert reloaded == fact
    assert "sources" in reloaded
    for c in reloaded["claims"]:
        for e in c["evidence"]:
            assert "uri" not in e
            assert "verified" not in e


def test_migration_preserves_challenge_pins(tmp_path: Path) -> None:
    """The canonical claim-state hash resolves evidence through the DERIVED
    uri regardless of shape (inline `uri` pre-migration, source-keyed after)
    — a standing correction's pin, filed against the pre-migration fact,
    must still hold post-migration with zero re-stamping."""
    claim = {
        "id": "x:wrong", "predicate": "wrong", "value": "v", "status": "disputed",
        "asof": "2026-07-02",
        "evidence": [{"uri": f"corpus://{H1}?el=1", "kind": "direct"}],
    }
    fact = {"id": "x", "type": "artist", "name": "X", "claims": [claim]}
    state_before = canonical_claim_state(claim, {})

    changed = migrate_fact(fact, where="facts/artist/x.json")
    assert changed is True
    state_after = canonical_claim_state(fact["claims"][0], fact["sources"])
    assert state_before == state_after

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "artist").mkdir(parents=True)
    (ledger / "interpretations").mkdir()
    (ledger / "facts" / "artist" / "x.json").write_text(
        json.dumps(fact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ledger / "interpretations" / "x-wrong-challenge.json").write_text(
        json.dumps({
            "id": "x-wrong-challenge", "kind": "correction", "about": ["x"],
            "statement": "claim x:wrong misreads the source.", "reasoning": "r",
            "based_on": [f"corpus://{H1}"],
            "challenges": {"claim": "x:wrong", "state": state_before},
            "status": "standing", "asof": "2026-07-02",
        }),
        encoding="utf-8",
    )
    (ledger / "ledger.yaml").write_text("name: ledger\ncorpora: []\n")

    rep = run_check(ledger, CorpusJoin([]), {}, no_corpus=True)
    assert not any("re-review" in w for w in rep.warnings)


def test_migrate_leaves_unparseable_uri_bare() -> None:
    """A malformed inline uri (neither corpus:// nor ref://) is dropped bare
    rather than raising — check flags the resulting sourceless entry, same as
    any other malformed evidence (parse tolerantly, author strictly)."""
    fact = {
        "id": "x", "type": "artist", "name": "X",
        "claims": [{"id": "x:a", "predicate": "a", "value": "1", "status": "provisional",
                    "evidence": [{"uri": "https://example.com", "kind": "direct"}]}],
    }
    changed = migrate_fact(fact, where="facts/artist/x.json")
    assert changed is True
    ev = fact["claims"][0]["evidence"][0]
    assert "uri" not in ev and "source" not in ev


def test_main_cli_migrates_a_ledger_tree(tmp_path: Path, capsys: object) -> None:
    ledger = tmp_path / "ledger"
    (ledger / "facts" / "artist").mkdir(parents=True)
    (ledger / "facts" / "artist" / "x.json").write_text(
        json.dumps(_old_fact(), indent=2) + "\n", encoding="utf-8")
    (ledger / "facts" / "artist" / "already-clean.json").write_text(
        json.dumps({"id": "already-clean", "type": "artist", "name": "Y"}, indent=2) + "\n",
        encoding="utf-8")

    rc = main(["--ledger-root", str(ledger)])
    assert rc == 0
    err = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "1 of 2 fact files migrated" in err

    migrated = json.loads((ledger / "facts" / "artist" / "x.json").read_text())
    assert "sources" in migrated
    for c in migrated["claims"]:
        for e in c["evidence"]:
            assert "uri" not in e

    # a second run is a full no-op — the migration converges
    rc2 = main(["--ledger-root", str(ledger)])
    assert rc2 == 0
    err2 = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "0 of 2 fact files migrated" in err2


def test_main_cli_dry_run_writes_nothing(tmp_path: Path, capsys: object) -> None:
    ledger = tmp_path / "ledger"
    (ledger / "facts" / "artist").mkdir(parents=True)
    fp = ledger / "facts" / "artist" / "x.json"
    original = json.dumps(_old_fact(), indent=2) + "\n"
    fp.write_text(original, encoding="utf-8")

    rc = main(["--ledger-root", str(ledger), "--dry-run"])
    assert rc == 0
    assert fp.read_text() == original  # untouched
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "would migrate" in out
