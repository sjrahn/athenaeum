"""`corpus.continuity` — the content-continuity supersession check.

Builds real zip-manifest session records in a temp corpus and asserts the four member
verdicts (identical / contained / diverged / absent) and the `contains_a` bottom line that
gates `B supersedes A` and citation rewrites, plus the whole-artifact fallback for records
that are not container manifests.
"""

from __future__ import annotations

import json
from pathlib import Path

from corpus import ccsession, continuity, hashing, paths
from corpus._cli import dispatch


def _session_record(root: Path, projects: Path, sid: str, lines, *, subagents=None) -> str:
    proj = projects / "-p"
    proj.mkdir(parents=True, exist_ok=True)
    tr = proj / f"{sid}.jsonl"
    tr.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    for name, recs in (subagents or {}).items():
        sub = proj / sid / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8"
        )
    sp = ccsession.find_session(str(tr))
    stats = ccsession.session_stats(sp)
    zip_path = root / "capture" / f"{sid}.zip"
    ccsession.build_bundle(
        ccsession.collect_members(sp), zip_path, comment=ccsession.bundle_comment(sp, stats)
    )
    rid = hashing.hash_file(zip_path, also=())["blake3"]
    ccsession.write_sidecar(
        zip_path,
        ccsession.origin_fields(sp, stats, captured_at="2026-01-01T00:00:00Z"),
        snapshot=stats.activity_end or "2026-01-01T00:00:00Z",
    )
    dispatch(["ingest", str(zip_path), "--corpus-root", str(root)])
    from tests._draftlib import draft_for_test
    draft_for_test(root, rid)
    return rid


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def test_identical_same_record(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    rid = _session_record(root, projects, "s", [{"type": "user", "i": 1}])
    cont = continuity.continuity(root, rid, rid)
    assert cont.contains_a
    assert cont.members[0].status == continuity.IDENTICAL


def test_contained_when_appended(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    base = [{"type": "user", "i": 1}, {"type": "assistant", "i": 2}]
    a = _session_record(root, projects, "s", base, subagents={"agent-x": [{"z": 1}]})
    grown = [*base, {"type": "user", "i": 3}]  # append-only growth
    b = _session_record(root, projects, "s", grown, subagents={"agent-x": [{"z": 1}]})
    cont = continuity.continuity(root, a, b)
    assert cont.contains_a
    statuses = {m.address: m.status for m in cont.members}
    assert statuses["path=s.jsonl"] == continuity.CONTAINED  # grew by append
    assert statuses["path=s/subagents/agent-x.jsonl"] == continuity.IDENTICAL  # unchanged


def test_diverged_when_rewritten(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    a = _session_record(root, projects, "s", [{"type": "user", "i": 1}])
    b = _session_record(root, projects, "s", [{"type": "user", "i": 999}])  # first line differs
    cont = continuity.continuity(root, a, b)
    assert not cont.contains_a
    assert cont.status_for("path=s.jsonl") == continuity.DIVERGED


def test_absent_when_member_dropped(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    line = [{"type": "user", "i": 1}]
    a = _session_record(root, projects, "s", line, subagents={"agent-x": [{"z": 1}]})
    # remove the subagent, keep the transcript identical
    import shutil

    shutil.rmtree(projects / "-p" / "s")
    b = _session_record(root, projects, "s", line)
    cont = continuity.continuity(root, a, b)
    assert not cont.contains_a
    assert cont.status_for("path=s/subagents/agent-x.jsonl") == continuity.ABSENT
    assert cont.status_for("path=s.jsonl") == continuity.IDENTICAL


def test_non_container_fallback(tmp_path):
    """Two records with no `path=` embeds never continue into each other unless identical —
    their whole-artifact identity is their id, which already differs."""
    import frontmatter

    from corpus import records

    root = _corpus(tmp_path)
    ids = ["aa" * 32, "bb" * 32]
    for rid in ids:
        post = frontmatter.Post(
            "", **records.stub_frontmatter(record_id=rid, touch_id="t@0.1.0")
        )
        rp = paths.record_path(root, rid)
        rp.parent.mkdir(parents=True, exist_ok=True)
        records.dump(post, rp)
    cont = continuity.continuity(root, ids[0], ids[1])
    assert not cont.contains_a
    assert cont.members and cont.members[0].status == continuity.DIVERGED
