"""`ath ledger supersede` — rewriting corpus citations when a record is re-captured.

Builds two real session records (an old capture and a grown / rewritten re-capture) in a
temp private corpus, a ledger fact that cites a session member, and asserts:
  - a citation whose content is PRESERVED (contained) rewrites old→new, tail intact, and
    `--retire` reclaims the old bytes;
  - a citation whose content DIVERGED is left untouched, reported, and `--retire` refused.
"""

from __future__ import annotations

import json
from pathlib import Path

from corpus import ccsession, hashing, paths
from corpus._cli import dispatch
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.supersede import supersede


def _session_record(priv: Path, projects: Path, sid: str, lines) -> str:
    proj = projects / "-p"
    proj.mkdir(parents=True, exist_ok=True)
    tr = proj / f"{sid}.jsonl"
    tr.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    sp = ccsession.find_session(str(tr))
    stats = ccsession.session_stats(sp)
    zip_path = priv / "capture" / f"{sid}.zip"
    ccsession.build_bundle(
        ccsession.collect_members(sp), zip_path, comment=ccsession.bundle_comment(sp, stats)
    )
    rid = hashing.hash_file(zip_path, also=())["blake3"]
    ccsession.write_sidecar(
        zip_path,
        ccsession.origin_fields(sp, stats, captured_at="2026-01-01T00:00:00Z"),
        snapshot=stats.activity_end or "2026-01-01T00:00:00Z",
    )
    dispatch(["ingest", str(zip_path), "--corpus-root", str(priv)])
    dispatch(["draft", rid, "--corpus-root", str(priv)])
    return rid


def _fact(ledger: Path, fact_id: str, cite_uri: str) -> Path:
    fp = ledger / "facts" / "place" / f"{fact_id}.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(
            {
                "id": fact_id,
                "type": "place",
                "name": "X",
                "claims": [
                    {
                        "id": f"{fact_id}:c",
                        "predicate": "p",
                        "value": "v",
                        "status": "provisional",
                        "evidence": [{"uri": cite_uri, "quote": "q", "kind": "direct"}],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return fp


def _system(tmp_path: Path):
    priv = tmp_path / "corpora" / "corpus-private"
    (priv / "records").mkdir(parents=True)
    (priv / "schema").mkdir()
    ledger = tmp_path / "ledger"
    (ledger / "facts").mkdir(parents=True)
    join = CorpusJoin([RegisteredCorpus(name="corpus-private", root=priv, private=True)])
    return priv, ledger, join


BASE = [
    {"type": "user", "sessionId": "s", "timestamp": "2026-07-01T00:00:00.000Z"},
    {"type": "assistant", "sessionId": "s", "timestamp": "2026-07-01T00:00:01.000Z"},
]


def test_supersede_rewrites_preserved_citation_and_retires(tmp_path):
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    grown = [*BASE, {"type": "user", "sessionId": "s", "timestamp": "2026-07-01T00:10:00.000Z"}]
    new = _session_record(priv, projects, "s", grown)
    assert old != new

    fp = _fact(ledger, "x", f"corpus://{old}?path=s.jsonl")
    res = supersede(ledger, old, new, join, retire=True)

    assert res.ok
    assert len(res.rewrites) == 1
    assert res.divergences == []
    assert res.retired
    # the fact now cites the new record, tail preserved
    fact = json.loads(fp.read_text())
    assert fact["claims"][0]["evidence"][0]["uri"] == f"corpus://{new}?path=s.jsonl"
    # old bytes reclaimed
    assert not paths.record_path(priv, old).is_file()
    assert paths.record_path(priv, new).is_file()


def test_supersede_leaves_diverged_and_refuses_retire(tmp_path):
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    rewritten = [
        {"type": "user", "sessionId": "s", "timestamp": "2026-07-02T00:00:00.000Z", "x": 9},
        {"type": "assistant", "sessionId": "s", "timestamp": "2026-07-02T00:00:01.000Z"},
    ]
    new = _session_record(priv, projects, "s", rewritten)

    fp = _fact(ledger, "x", f"corpus://{old}?path=s.jsonl")
    res = supersede(ledger, old, new, join, retire=True)

    assert res.rewrites == []
    assert len(res.divergences) == 1
    assert res.divergences[0].address == "path=s.jsonl"
    assert not res.retired  # refused: a diverged citation still points at old
    # the citation is untouched, and old is still present
    fact = json.loads(fp.read_text())
    assert fact["claims"][0]["evidence"][0]["uri"] == f"corpus://{old}?path=s.jsonl"
    assert paths.record_path(priv, old).is_file()


def test_supersede_bare_whole_record_citation(tmp_path):
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    grown = [*BASE, {"type": "user", "sessionId": "s", "timestamp": "2026-07-01T00:10:00.000Z"}]
    new = _session_record(priv, projects, "s", grown)

    fp = _fact(ledger, "x", f"corpus://{old}")
    res = supersede(ledger, old, new, join, retire=False)

    assert len(res.rewrites) == 1
    fact = json.loads(fp.read_text())
    assert fact["claims"][0]["evidence"][0]["uri"] == f"corpus://{new}"


def test_supersede_errors_when_new_unresolved(tmp_path):
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    res = supersede(ledger, old, "f" * 64, join)
    assert not res.ok
    assert "resolves in no registered corpus" in res.note
