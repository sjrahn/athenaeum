"""`ath ledger supersede` — rewriting corpus citations when a record is re-captured.

Builds two real session records (an old capture and a grown / rewritten re-capture) in a
temp private corpus, a ledger fact whose claim evidence cites a session member (via the
sources-table shape), and asserts:
  - a citation whose content is PRESERVED (contained) rewrites the sources entry's `record`
    in place, tail intact, and `--retire` reclaims the old bytes;
  - a citation whose content DIVERGED is left untouched, reported, and `--retire` refused;
  - a sources entry shared by two evidence entries with mixed verdicts SPLITS: the preserved
    entry repoints to a fresh sources entry on `new`, the diverged entry stays on the old key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corpus import ccsession, hashing, paths
from corpus._cli import dispatch
from ledger._cli import main as ledger_main
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.model import CORPUS_URI_RE
from ledger.supersede import SupersedeError, resolve_hash_arg, supersede


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
    from tests._draftlib import draft_for_test
    draft_for_test(priv, rid)
    return rid


def _fact(ledger: Path, fact_id: str, cite_uri: str) -> Path:
    """A fact with one claim whose evidence cites `cite_uri` — through the
    sources table, per the amendment: the hash lands on a `sources` entry, the
    evidence carries `source` + (bare) `anchor`."""
    m = CORPUS_URI_RE.match(cite_uri)
    assert m, cite_uri
    h = m.group(1)
    tail = m.group(2) or ""
    anchor = tail[1:] if tail[:1] in ("?", "#") else tail
    ev = {"source": "s1", "quote": "q", "kind": "direct"}
    if anchor:
        ev["anchor"] = anchor
    fp = ledger / "facts" / "place" / f"{fact_id}.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(
            {
                "id": fact_id,
                "type": "place",
                "name": "X",
                "sources": {"s1": {"record": h}},
                "claims": [
                    {
                        "id": f"{fact_id}:c",
                        "predicate": "p",
                        "value": "v",
                        "status": "provisional",
                        "evidence": [ev],
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
    # the sources entry now targets the new record; the evidence's `source`
    # key and `anchor` are untouched — the record it resolves through moved
    fact = json.loads(fp.read_text())
    assert fact["sources"]["s1"]["record"] == new
    ev = fact["claims"][0]["evidence"][0]
    assert ev["source"] == "s1"
    assert ev["anchor"] == "path=s.jsonl"
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
    assert fact["sources"]["s1"]["record"] == old
    assert fact["claims"][0]["evidence"][0]["source"] == "s1"
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
    assert fact["sources"]["s1"]["record"] == new
    assert "anchor" not in fact["claims"][0]["evidence"][0]


def test_supersede_splits_shared_source_on_mixed_verdicts(tmp_path):
    """One sources entry cited by two evidence entries with different
    addresses — a bare (whole-record) citation that's preserved, and a
    path-scoped citation of a member the new capture never carried (so its
    verdict is ABSENT, i.e. diverged): the preserved entry repoints to a
    FRESH sources entry targeting `new`; the diverged entry stays on the old
    key, which keeps citing `old`."""
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    grown = [*BASE, {"type": "user", "sessionId": "s", "timestamp": "2026-07-01T00:10:00.000Z"}]
    new = _session_record(priv, projects, "s", grown)

    fp = ledger / "facts" / "place" / "x.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps({
        "id": "x", "type": "place", "name": "X",
        "sources": {"s1": {"record": old}},
        "claims": [
            {"id": "x:whole", "predicate": "p", "value": "v", "status": "provisional",
             "evidence": [{"source": "s1", "quote": "q", "kind": "direct"}]},
            {"id": "x:member", "predicate": "p2", "value": "v2", "status": "provisional",
             "evidence": [{"source": "s1", "anchor": "path=does-not-exist.txt",
                           "quote": "q2", "kind": "direct"}]},
        ],
    }, indent=2) + "\n", encoding="utf-8")

    res = supersede(ledger, old, new, join, retire=True)

    fact = json.loads(fp.read_text())
    whole = next(c for c in fact["claims"] if c["id"] == "x:whole")["evidence"][0]
    member = next(c for c in fact["claims"] if c["id"] == "x:member")["evidence"][0]
    new_key = whole["source"]
    assert new_key != "s1"
    assert fact["sources"][new_key] == {"record": new}
    assert member["source"] == "s1"
    assert fact["sources"]["s1"] == {"record": old}
    assert len(res.rewrites) == 1
    assert len(res.divergences) == 1
    assert not res.retired  # a diverged citation still references `old`
    assert paths.record_path(priv, old).is_file()


def test_supersede_rewrites_a_diverged_roster_row_unconditionally(tmp_path):
    """A roster row (`artifacts[].uri`) is IDENTITY ASSIGNMENT, not a quote — there is no span
    to diverge, so it rewrites old → new regardless of what `corpus.continuity` says about the
    whole-record pair. This is the exact scenario a real re-capture migration hit: EVERY roster
    row reported "DIVERGED … (whole record)" under the (former) continuity gate, because a
    re-mint's full bytes essentially never satisfy IDENTICAL/CONTAINED — a roster row citing
    a rewritten capture is the common case, not the exception."""
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    rewritten = [
        {"type": "user", "sessionId": "s", "timestamp": "2026-07-02T00:00:00.000Z", "x": 9},
        {"type": "assistant", "sessionId": "s", "timestamp": "2026-07-02T00:00:01.000Z"},
    ]
    new = _session_record(priv, projects, "s", rewritten)

    fp = ledger / "facts" / "place" / "x.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(
            {
                "id": "x",
                "type": "place",
                "name": "X",
                "artifacts": [{"uri": f"corpus://{old}", "role": "primary"}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    res = supersede(ledger, old, new, join, retire=True)

    assert res.ok
    assert len(res.rewrites) == 1
    assert res.rewrites[0].old_uri == f"corpus://{old}"
    assert res.rewrites[0].new_uri == f"corpus://{new}"
    assert res.divergences == []  # a roster row is never reported diverged
    fact = json.loads(fp.read_text())
    assert fact["artifacts"][0]["uri"] == f"corpus://{new}"
    assert res.retired  # nothing diverged, so retirement proceeds
    assert not paths.record_path(priv, old).is_file()


def test_supersede_rewrites_derived_from_alongside_its_uri(tmp_path):
    """`derived_from` on one roster entry must always equal some OTHER entry's `uri` in the
    same fact (`ledger.check`'s invariant) — so when that other entry's `uri` moves, every
    `derived_from` naming it has to move with it, in the same unconditional pass."""
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    grown = [*BASE, {"type": "user", "sessionId": "s", "timestamp": "2026-07-01T00:10:00.000Z"}]
    new = _session_record(priv, projects, "s", grown)

    fp = ledger / "facts" / "place" / "x.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(
            {
                "id": "x",
                "type": "place",
                "name": "X",
                "artifacts": [
                    {"uri": f"corpus://{old}", "role": "primary"},
                    {
                        "uri": "corpus://" + "1" * 64,
                        "role": "derived",
                        "derived_from": f"corpus://{old}",
                        "derivation": "thumbnail@0.1.0",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    res = supersede(ledger, old, new, join, retire=False)

    fact = json.loads(fp.read_text())
    assert fact["artifacts"][0]["uri"] == f"corpus://{new}"
    assert fact["artifacts"][1]["derived_from"] == f"corpus://{new}"
    assert fact["artifacts"][1]["uri"] == "corpus://" + "1" * 64  # unrelated entry, untouched
    assert len(res.rewrites) == 2


def test_supersede_roster_row_unconditional_but_quote_citation_still_gated(tmp_path):
    """The two citation kinds in ONE fact, judged independently in one pass: the roster row
    rewrites regardless of continuity, while a claim's quote-bearing evidence citation of a
    member the new capture never carried still diverges and is left on `old`, reported."""
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    rewritten = [
        {"type": "user", "sessionId": "s", "timestamp": "2026-07-02T00:00:00.000Z", "x": 9},
        {"type": "assistant", "sessionId": "s", "timestamp": "2026-07-02T00:00:01.000Z"},
    ]
    new = _session_record(priv, projects, "s", rewritten)

    fp = ledger / "facts" / "place" / "x.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(
            {
                "id": "x",
                "type": "place",
                "name": "X",
                "artifacts": [{"uri": f"corpus://{old}", "role": "primary"}],
                "sources": {"s1": {"record": old}},
                "claims": [
                    {
                        "id": "x:c",
                        "predicate": "p",
                        "value": "v",
                        "status": "provisional",
                        "evidence": [
                            {
                                "source": "s1",
                                "anchor": "path=s.jsonl",
                                "quote": "q",
                                "kind": "direct",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    res = supersede(ledger, old, new, join, retire=True)

    fact = json.loads(fp.read_text())
    # the roster row moved unconditionally
    assert fact["artifacts"][0]["uri"] == f"corpus://{new}"
    # the quote citation stayed on `old` — its content diverged
    assert fact["sources"]["s1"]["record"] == old
    assert fact["claims"][0]["evidence"][0]["source"] == "s1"
    assert any(r.old_uri == f"corpus://{old}" and r.new_uri == f"corpus://{new}"
               for r in res.rewrites)
    assert len(res.divergences) == 1
    assert res.divergences[0].address == "path=s.jsonl"
    # a diverged (quote) citation still refuses retirement, even though the roster moved
    assert not res.retired
    assert paths.record_path(priv, old).is_file()


def test_supersede_errors_when_new_unresolved(tmp_path):
    priv, ledger, join = _system(tmp_path)
    projects = tmp_path / "projects"
    old = _session_record(priv, projects, "s", BASE)
    res = supersede(ledger, old, "f" * 64, join)
    assert not res.ok
    assert "resolves in no registered corpus" in res.note


def _bare_record(priv: Path, h: str) -> None:
    """A minimal record file, just enough to exist at its shard path — full
    session/capture machinery isn't needed to exercise prefix resolution."""
    p = priv / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: {h}\ntitle: ''\nstatus: normalized\n---\n\n"
                 "<!--artifact text/plain\n-->\n", encoding="utf-8")


def test_resolve_hash_arg_expands_unambiguous_prefix(tmp_path):
    """`ath ledger supersede` accepts a short hash prefix, same as every corpus
    verb (`corpus.paths.resolve_record`'s MIN_HASH_PREFIX convenience) —
    supersede's own CLI entry used to require the full 64-char hash."""
    priv, _ledger, join = _system(tmp_path)
    h = "a" * 64
    _bare_record(priv, h)
    assert resolve_hash_arg(join, h[:12]) == h


def test_resolve_hash_arg_ambiguous_prefix_lists_collisions(tmp_path):
    priv, _ledger, join = _system(tmp_path)
    h1 = "abcd" + "1" * 60
    h2 = "abcd" + "2" * 60
    _bare_record(priv, h1)
    _bare_record(priv, h2)
    with pytest.raises(SupersedeError) as exc_info:
        resolve_hash_arg(join, "abcd")
    assert h1 in str(exc_info.value) and h2 in str(exc_info.value)


def test_resolve_hash_arg_full_hash_passes_through_unchanged(tmp_path):
    """A full 64-char hash is returned as-is, whether or not it resolves yet
    (e.g. `new`, a fresh capture not necessarily indexed by prefix lookup) —
    `supersede()` itself is what validates existence."""
    _priv, _ledger, join = _system(tmp_path)
    h = "c" * 64
    assert resolve_hash_arg(join, h) == h


def test_resolve_hash_arg_no_match(tmp_path):
    _priv, _ledger, join = _system(tmp_path)
    with pytest.raises(SupersedeError, match="resolves in no registered corpus"):
        resolve_hash_arg(join, "deadbeef")


def test_resolve_hash_arg_prefix_too_short(tmp_path):
    _priv, _ledger, join = _system(tmp_path)
    with pytest.raises(SupersedeError, match="too short"):
        resolve_hash_arg(join, "ab")


def test_cli_supersede_accepts_hash_prefixes(tmp_path: Path) -> None:
    """`ath ledger supersede` end to end with 12-char prefixes for both
    arguments — the CLI entry, not just the resolver helper, must expand
    them before handing off to `supersede()` (which used to require the
    full 64-char hash and errored "resolves in no registered corpus")."""
    root = tmp_path
    (root / "athenaeum.yaml").write_text("name: t\nvisibility: public\n")
    corpus_root = root / "corpus"
    old = "1" * 64
    new = "2" * 64
    for h in (old, new):
        p = corpus_root / "records" / h[:2] / f"{h}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\nid: {h}\ntitle: ''\nstatus: normalized\n---\n\n"
                     "<!--artifact text/plain\n-->\n", encoding="utf-8")
    (root / "ledger" / "facts").mkdir(parents=True)
    rc = ledger_main(["supersede", old[:12], new[:12], "--root", str(root)])
    assert rc == 0
