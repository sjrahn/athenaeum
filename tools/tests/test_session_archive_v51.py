"""A session archive holds everything the session saw, supersedes despite its live state,
and retires without stranding what was promoted out of it; every capture can say who asked
(spec v51 — codex-steven R-0059)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import blake3
import pytest
import yaml

from corpus import capturectx, ccsession, continuity, hashing, paths, records, schemas
from corpus._cli import dispatch
from corpus._cli import promote as promote_cli
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.supersede import supersede

SID = "5e55a0a1-0000-4000-8000-000000000001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _home(tmp_path: Path, lines: list[dict], *, state: str = "working") -> Path:
    """A synthetic `~/.claude` holding one background session and every per-session store."""
    home = tmp_path / "claude"
    proj = home / "projects" / "-w"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{SID}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8"
    )
    (proj / SID / "subagents").mkdir(parents=True, exist_ok=True)
    (proj / SID / "subagents" / "agent-a.jsonl").write_text("{}\n", encoding="utf-8")
    up = home / "uploads" / SID
    up.mkdir(parents=True, exist_ok=True)
    (up / "1111-image.png").write_bytes(PNG)
    fh = home / "file-history" / SID
    fh.mkdir(parents=True, exist_ok=True)
    (fh / "abc@v1").write_text("before\n", encoding="utf-8")
    tasks = home / "tasks" / f"session-{SID[:8]}"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "1.json").write_text('{"status": "pending"}', encoding="utf-8")
    job = home / "jobs" / "j0b"
    (job / "tmp").mkdir(parents=True, exist_ok=True)
    (job / "state.json").write_text(
        json.dumps({"sessionId": "other", "resumeSessionId": SID, "state": state}),
        encoding="utf-8",
    )
    (job / "tmp" / "scratch.bin").write_bytes(b"scratch")
    stranger = home / "jobs" / "n0pe"
    stranger.mkdir(parents=True, exist_ok=True)
    (stranger / "state.json").write_text('{"sessionId": "someone-else"}', encoding="utf-8")
    plans = home / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "a-plan.md").write_text("# plan\n", encoding="utf-8")
    (plans / "unnamed.md").write_text("# not this one\n", encoding="utf-8")
    cache = home / "paste-cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "aaaa1111bbbb2222.txt").write_text("pasted\u00a0as pasted  \n", encoding="utf-8")
    (cache / "cccc3333dddd4444.txt").write_text("another session's paste\n", encoding="utf-8")
    history = [
        {"display": "[Pasted text #1]", "sessionId": SID,
         "pastedContents": {"1": {"id": 1, "type": "text", "contentHash": "aaaa1111bbbb2222"}}},
        {"display": "small", "sessionId": SID,
         "pastedContents": {"1": {"id": 1, "type": "text", "content": "inline"}}},
        {"display": "[Pasted text #1]", "sessionId": "someone-else",
         "pastedContents": {"1": {"id": 1, "type": "text", "contentHash": "cccc3333dddd4444"}}},
        {"display": "bad", "sessionId": SID,
         "pastedContents": {"1": {"id": 1, "type": "text", "contentHash": "../../etc/passwd"}}},
    ]
    (home / "history.jsonl").write_text(
        "".join(json.dumps(h) + "\n" for h in history) + "not json " + SID + "\n",
        encoding="utf-8",
    )
    return home


LINES = [
    {"type": "user", "uuid": "u-1", "sessionId": SID, "timestamp": "2026-10-01T00:00:00Z",
     "message": {"content": "see ~/.claude/plans/a-plan.md"}},
    {"type": "assistant", "uuid": "a-1", "sessionId": SID, "timestamp": "2026-10-01T00:00:01Z"},
]


def _sp(home: Path) -> ccsession.SessionPaths:
    return ccsession.find_session(str(home / "projects" / "-w" / f"{SID}.jsonl"))


def test_the_bundle_takes_every_per_session_store(tmp_path):
    members = {rel for rel, _ in ccsession.collect_members(_sp(_home(tmp_path, LINES)))}
    assert members == {
        f"{SID}.jsonl",
        f"{SID}/subagents/agent-a.jsonl",
        "uploads/1111-image.png",  # the file as sent, not the transcript's downscaled copy
        "file-history/abc@v1",
        "tasks/1.json",
        "job/state.json",  # found through `resumeSessionId`; another session's job is not
        "plans/a-plan.md",  # named by the transcript; an unnamed plan is not
        # the cached original of a paste the session's prompt history names; another
        # session's paste is not, an inline one is already in the transcript, and a hash
        # that is not plain hex is never followed
        "pastes/aaaa1111bbbb2222.txt",
    }


def test_job_scratch_is_never_bundled(tmp_path):
    members = {r for r, _ in ccsession.collect_members(_sp(_home(tmp_path, LINES)))}
    assert not any(r.startswith("job/tmp/") for r in members)


# ---------- capture, supersession, retirement ---------- #


def _corpus(tmp_path: Path, *, volatile: list[str] | None) -> Path:
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "capture").mkdir()
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    overlay = {"description": "a session", "extended_fields": {}}
    if volatile is not None:
        overlay["volatile"] = volatile
    (odir / "claude-code-session.yaml").write_text(yaml.safe_dump(overlay), encoding="utf-8")
    schemas.cache_clear()
    return root


def _capture(root: Path, home: Path, *, context: dict | None = None) -> str:
    sp = _sp(home)
    stats = ccsession.session_stats(sp)
    zip_path = root / "capture" / f"{SID}.zip"
    ccsession.build_bundle(
        ccsession.collect_members(sp), zip_path, comment=ccsession.bundle_comment(sp, stats)
    )
    rid = hashing.hash_file(zip_path, also=())["blake3"]
    ccsession.write_sidecar(
        zip_path, ccsession.origin_fields(sp, stats, captured_at="2026-10-01T00:00:00Z"),
        snapshot="2026-10-01T00:00:00Z", context=context,
    )
    assert dispatch(["ingest", str(zip_path), "--corpus-root", str(root)]) == 0
    return rid


def _grow(tmp_path: Path) -> Path:
    grown = [*LINES, {"type": "user", "uuid": "u-2", "sessionId": SID,
                      "timestamp": "2026-10-01T00:15:00Z"}]
    return _home(tmp_path, grown, state="done")  # the job's state.json is rewritten


def test_live_state_blocks_supersession_until_declared_volatile(tmp_path):
    root = _corpus(tmp_path, volatile=None)
    old = _capture(root, _home(tmp_path, LINES))
    new = _capture(root, _grow(tmp_path))
    cont = continuity.continuity(root, old, new)
    assert not cont.contains_a
    assert cont.status_for("path=job/state.json") == continuity.DIVERGED

    (root / "schema" / "origin" / "claude-code-session.yaml").write_text(
        yaml.safe_dump({"description": "s", "volatile": ["job/state.json", "tasks/**"]}),
        encoding="utf-8",
    )
    schemas.cache_clear()
    cont = continuity.continuity(root, old, new)
    assert cont.contains_a
    assert cont.status_for("path=job/state.json") == continuity.VOLATILE
    assert cont.status_for(f"path={SID}.jsonl") == continuity.CONTAINED


def test_retiring_the_old_capture_extends_what_was_promoted_out_of_it(tmp_path):
    root = _corpus(tmp_path, volatile=["job/state.json"])
    old = _capture(root, _home(tmp_path, LINES))
    rc = promote_cli.run(argparse.Namespace(
        uri=f"corpus://{old}?path=uploads/1111-image.png", json=False, corpus_root=str(root)))
    assert rc == 0
    upload = blake3.blake3(PNG).hexdigest()
    new = _capture(root, _grow(tmp_path))

    ledger = tmp_path / "ledger"
    (ledger / "facts").mkdir(parents=True)
    join = CorpusJoin([RegisteredCorpus(name="corpus-private", root=root, private=True)])
    res = supersede(ledger, old, new, join, retire=True)
    assert res.retired, res.note
    assert not paths.record_path(root, old).is_file()
    # the upload lives on, re-pointed into the new capture — no husk on a dead container
    post = records.load(paths.record_path(root, upload))
    uris = [str((b.get("fields") or {}).get("uri")) for b in records.iter_origin_blocks(post)]
    assert uris[-1] == f"corpus://{new}?path=uploads/1111-image.png"


# ---------- who asked ---------- #


def test_capture_context_lands_on_the_origin_block(tmp_path):
    root = _corpus(tmp_path, volatile=None)
    ctx = capturectx.fields({"session_id": "eb33", "host": "arbre", "message_uuids": ["m-1"],
                             "request": "R-0059", "actor": "ita"})
    rid = _capture(root, _home(tmp_path, LINES), context=ctx)
    block = next(records.iter_origin_blocks(records.load(paths.record_path(root, rid))))
    f = block["fields"]
    assert (f["capture_session"], f["capture_messages"], f["capture_request"]) == (
        "eb33", "m-1", "R-0059")
    assert f["capture_actor"] == "ita" and f["session_id"] == SID  # the producer's own, apart


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ({"session": "x"}, "unknown key"),
        ({"message_uuids": ["m"]}, "give session_id"),
        ({"request": ["R-1"]}, "expected a string"),
    ],
)
def test_a_malformed_context_is_refused(raw, match):
    with pytest.raises(capturectx.ContextError, match=match):
        capturectx.fields(raw)


def test_the_environment_carries_context_to_promote(tmp_path, monkeypatch):
    root = _corpus(tmp_path, volatile=None)
    cid = _capture(root, _home(tmp_path, LINES))
    monkeypatch.setenv(capturectx.ENV, json.dumps({"trigger": "watcher:vault", "actor": "ita"}))
    rc = promote_cli.run(argparse.Namespace(
        uri=f"corpus://{cid}?path=file-history/abc@v1", json=False, corpus_root=str(root)))
    assert rc == 0
    leaf = records.load(paths.record_path(root, blake3.blake3(b"before\n").hexdigest()))
    f = next(records.iter_origin_blocks(leaf))["fields"]
    assert f["capture_trigger"] == "watcher:vault" and f["capture_actor"] == "ita"

    monkeypatch.setenv(capturectx.ENV, '{"bogus": 1}')
    with pytest.raises(SystemExit, match="refused"):
        promote_cli.run(argparse.Namespace(
            uri=f"corpus://{cid}?path=tasks/1.json", json=False, corpus_root=str(root)))
