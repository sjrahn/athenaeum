"""`corpus session` — Claude Code session capture, stats, bundling, and supersession.

Covers the domain module (`corpus.ccsession`) and the CLI wiring end to end against a
fabricated `~/.claude/projects` tree and a temp corpus: discovery, stats, deterministic
bundling, the uri-less producer-export sidecar, prior-record scanning, and the
continuity-gated supersession decision (grow → supersedes; rewrite → keeps both).
"""

from __future__ import annotations

import json
from pathlib import Path

from corpus import ccsession, hashing, paths, records, ziparchive
from corpus._cli import dispatch


def _overlay_path() -> Path:
    """The live claude-code-session overlay, resolved through the MANIFEST —
    member locations are path-overridable (spec/athenaeum.md §2.3), so no test
    may hardcode one. Falls back to a non-existent path when no member holds
    the overlay; the fixture guards with `.is_file()` either way."""
    try:
        from ath import manifest

        root = manifest.find_root(Path(__file__).resolve().parent)
        for m in manifest.load(root):
            if m.layer == "corpora":
                p = m.path / "schema/origin/claude-code-session.yaml"
                if p.is_file():
                    return p
    except Exception:
        pass
    return Path("/nonexistent/claude-code-session.yaml")


OVERLAY = _overlay_path()


# --------------------------------------------------------------------------- helpers


def _scaffold(tmp_path: Path) -> Path:
    """A minimal corpus that can ingest+draft a zip and bind the session overlay."""
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    origin_dir = root / "schema" / "origin"
    origin_dir.mkdir(parents=True)
    if OVERLAY.is_file():
        (origin_dir / OVERLAY.name).write_text(OVERLAY.read_text())
    return root


def _write_session(
    projects: Path,
    session_id: str,
    *,
    project: str = "-proj",
    lines: list[dict] | None = None,
    subagents: dict[str, list[dict]] | None = None,
    tool_results: dict[str, str] | None = None,
) -> Path:
    """Write a fabricated session tree; return the transcript path."""
    proj = projects / project
    proj.mkdir(parents=True, exist_ok=True)
    transcript = proj / f"{session_id}.jsonl"
    lines = lines or [
        {"type": "user", "sessionId": session_id, "cwd": "/w", "version": "2.1.0",
         "timestamp": "2026-07-01T00:00:00.000Z"},
        {"type": "assistant", "sessionId": session_id, "cwd": "/w", "version": "2.1.0",
         "timestamp": "2026-07-01T00:00:01.000Z"},
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    for name, recs in (subagents or {}).items():
        sub = proj / session_id / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8"
        )
        (sub / f"{name}.meta.json").write_text(json.dumps({"agent": name}), encoding="utf-8")
    for fname, text in (tool_results or {}).items():
        tr = proj / session_id / "tool-results"
        tr.mkdir(parents=True, exist_ok=True)
        (tr / fname).write_text(text, encoding="utf-8")
    return transcript


def _capture(root: Path, transcript: Path) -> str:
    """Bundle + ingest + draft a session (by direct transcript path) → record id."""
    sp = ccsession.find_session(str(transcript))
    stats = ccsession.session_stats(sp)
    zip_path = root / "capture" / f"{sp.session_id}.zip"
    members = ccsession.collect_members(sp)
    ccsession.build_bundle(members, zip_path, comment=ccsession.bundle_comment(sp, stats))
    rid = hashing.hash_file(zip_path, also=())["blake3"]
    already = paths.record_path(root, rid).is_file()
    ccsession.write_sidecar(
        zip_path,
        ccsession.origin_fields(sp, stats, captured_at="2026-01-01T00:00:00Z"),
        snapshot=stats.activity_end or "2026-01-01T00:00:00Z",
    )
    assert dispatch(["ingest", str(zip_path), "--corpus-root", str(root)]) == 0
    if not paths.record_path(root, rid).is_file():
        raise AssertionError("ingest did not create the record")
    if not already:  # re-derive only a fresh capture; the mechanical body leaves it a stub
        from tests._draftlib import draft_for_test
        draft_for_test(root, rid)
    return rid


# --------------------------------------------------------------------------- discovery + stats


def test_find_session_by_id_and_path(tmp_path):
    projects = tmp_path / "projects"
    tr = _write_session(projects, "sid-1")
    by_id = ccsession.find_session("sid-1", projects_dir=projects)
    assert by_id.session_id == "sid-1"
    assert by_id.transcript == tr.resolve()
    assert by_id.project_dir == "-proj"
    by_path = ccsession.find_session(str(tr))
    assert by_path.session_id == "sid-1"


def test_find_session_ambiguous_raises(tmp_path):
    projects = tmp_path / "projects"
    _write_session(projects, "dup", project="-a")
    _write_session(projects, "dup", project="-b")
    import pytest

    with pytest.raises(ValueError, match="ambiguous"):
        ccsession.find_session("dup", projects_dir=projects)


def test_stats_counts(tmp_path):
    projects = tmp_path / "projects"
    lines = [
        {"type": "user", "sessionId": "s", "cwd": "/w", "version": "2.1.5",
         "timestamp": "2026-07-01T00:00:00.000Z"},
        {"type": "assistant", "sessionId": "s", "cwd": "/w", "version": "2.1.6",
         "timestamp": "2026-07-01T00:05:00.000Z"},
        {"type": "system", "sessionId": "s", "cwd": "/w"},
    ]
    tr = _write_session(
        projects, "s", lines=lines, subagents={"agent-a1": [{"type": "user"}]}
    )
    st = ccsession.session_stats(ccsession.find_session(str(tr)))
    assert st.record_count == 3
    assert st.message_count == 2
    assert st.subagent_count == 1
    assert st.claude_code_version == "2.1.6"
    assert st.cwd == "/w"
    assert st.activity_start == "2026-07-01T00:00:00.000Z"
    assert st.activity_end == "2026-07-01T00:05:00.000Z"


def test_collect_members_mirrors_tree(tmp_path):
    projects = tmp_path / "projects"
    tr = _write_session(
        projects, "s", subagents={"agent-a1": [{}]}, tool_results={"r.txt": "x"}
    )
    members = ccsession.collect_members(ccsession.find_session(str(tr)))
    rels = {rel for rel, _ in members}
    assert "s.jsonl" in rels
    assert "s/subagents/agent-a1.jsonl" in rels
    assert "s/subagents/agent-a1.meta.json" in rels
    assert "s/tool-results/r.txt" in rels


# --------------------------------------------------------------------------- bundle


def test_bundle_is_deterministic_and_faithful(tmp_path):
    projects = tmp_path / "projects"
    tr = _write_session(projects, "s", subagents={"agent-a1": [{"k": 1}]})
    sp = ccsession.find_session(str(tr))
    stats = ccsession.session_stats(sp)
    members = ccsession.collect_members(sp)
    comment = ccsession.bundle_comment(sp, stats)
    a = tmp_path / "a.zip"
    b = tmp_path / "b.zip"
    ccsession.build_bundle(members, a, comment=comment)
    ccsession.build_bundle(members, b, comment=comment)
    assert a.read_bytes() == b.read_bytes()  # deterministic
    # a member round-trips byte-faithful
    assert ziparchive.resolve_member(a, "s.jsonl") == tr.read_bytes()


def test_origin_fields_and_sidecar(tmp_path):
    projects = tmp_path / "projects"
    tr = _write_session(projects, "s")
    sp = ccsession.find_session(str(tr))
    stats = ccsession.session_stats(sp)
    fields = ccsession.origin_fields(sp, stats, captured_at="2026-01-01T00:00:00Z")
    assert fields["session_id"] == "s"
    assert fields["record_count"] == 2
    assert fields["host"] == sp.host
    zip_path = tmp_path / "s.zip"
    zip_path.write_bytes(b"PK")
    sidecar = ccsession.write_sidecar(zip_path, fields, snapshot="2026-07-01T00:00:01.000Z")
    import yaml

    payload = yaml.safe_load(sidecar.read_text())
    assert payload["origin_schema"] == "claude-code-session"
    assert payload["fetched_at"] == "2026-07-01T00:00:01.000Z"
    assert "source_url" not in payload  # uri-less
    assert payload["origin_fields"]["session_id"] == "s"


# --------------------------------------------------------------------------- capture + supersession


def test_capture_creates_clean_record_and_reencounters(tmp_path):
    root = _scaffold(tmp_path)
    projects = tmp_path / "projects"
    tr = _write_session(projects, "sid-x", subagents={"agent-a1": [{"k": 1}]})
    rid = _capture(root, tr)
    post = records.load(paths.record_path(root, rid))
    assert records.derived_state(post) == "proxy"
    # origin bound to the producer overlay, uri-less
    origins = list(records.iter_origin_blocks(post))
    assert origins and origins[0]["id"] == "claude-code-session"
    assert (origins[0]["fields"] or {}).get("session_id") == "sid-x"
    # members are embeds, content zone empty (never transcribed)
    addrs = {e["address"] for e in records.iter_embed_blocks(post)}
    assert "path=sid-x.jsonl" in addrs
    # lint clean
    assert dispatch(["lint", rid, "--corpus-root", str(root)]) == 0
    # re-capture of the unchanged session → same id (deterministic bundle → re-encounter)
    rid2 = _capture(root, tr)
    assert rid2 == rid


def test_find_prior_sessions(tmp_path):
    root = _scaffold(tmp_path)
    projects = tmp_path / "projects"
    tr = _write_session(projects, "sid-p")
    rid = _capture(root, tr)
    sp = ccsession.find_session(str(tr))
    priors = ccsession.find_prior_sessions(root, "sid-p", sp.host)
    assert [p.record_id for p in priors] == [rid]
    assert priors[0].record_count == 2
    # a different session id does not match
    assert ccsession.find_prior_sessions(root, "other", sp.host) == []


def test_supersession_grow_contains_prior(tmp_path):
    from corpus import continuity

    root = _scaffold(tmp_path)
    projects = tmp_path / "projects"
    base = [
        {"type": "user", "sessionId": "g", "timestamp": "2026-07-01T00:00:00.000Z"},
        {"type": "assistant", "sessionId": "g", "timestamp": "2026-07-01T00:00:01.000Z"},
    ]
    tr = _write_session(projects, "g", lines=base, subagents={"agent-a1": [{"k": 1}]})
    rid_a = _capture(root, tr)
    # the session grows: append more turns (append-only, as Claude Code writes it)
    grown = [
        *base,
        {"type": "user", "sessionId": "g", "timestamp": "2026-07-01T00:10:00.000Z"},
        {"type": "assistant", "sessionId": "g", "timestamp": "2026-07-01T00:10:01.000Z"},
    ]
    tr.write_text("".join(json.dumps(r) + "\n" for r in grown), encoding="utf-8")
    rid_b = _capture(root, tr)
    assert rid_b != rid_a
    cont = continuity.continuity(root, rid_a, rid_b)
    assert cont.contains_a  # B fully contains A → safe to supersede
    assert cont.diverged == []


def test_supersession_refused_when_transcript_rewritten(tmp_path):
    from corpus import continuity

    root = _scaffold(tmp_path)
    projects = tmp_path / "projects"
    base = [
        {"type": "user", "sessionId": "c", "timestamp": "2026-07-01T00:00:00.000Z"},
        {"type": "assistant", "sessionId": "c", "timestamp": "2026-07-01T00:00:01.000Z"},
    ]
    tr = _write_session(projects, "c", lines=base)
    rid_a = _capture(root, tr)
    # a compaction / rewrite: the transcript is NOT a superset of the old one
    rewritten = [
        {"type": "user", "sessionId": "c", "timestamp": "2026-07-02T00:00:00.000Z",
         "isCompactSummary": True},
        {"type": "assistant", "sessionId": "c", "timestamp": "2026-07-02T00:00:01.000Z"},
    ]
    tr.write_text("".join(json.dumps(r) + "\n" for r in rewritten), encoding="utf-8")
    rid_b = _capture(root, tr)
    cont = continuity.continuity(root, rid_a, rid_b)
    assert not cont.contains_a  # diverged main transcript → keep both, do not supersede
    assert any(m.address == "path=c.jsonl" for m in cont.diverged)
