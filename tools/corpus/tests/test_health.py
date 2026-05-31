"""Offline health signals + the `corpus health` CLI.

Builds a small fixture corpus spanning the lifecycle (stub / draft / normalized, an
open issue, a missing artifact, a structurally-invalid record) and asserts each
signal surfaces the right records. No network.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import health, paths, records
from corpus._cli import dispatch

A = "a0" * 32  # stub image, no artifact
B = "b0" * 32  # draft pdf, with artifact
C = "c0" * 32  # normalized image, empty description
D = "d0" * 32  # draft image, open warning issue
E = "e0" * 32  # draft image, no origin block (invalid)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write(
    root: Path,
    rid: str,
    *,
    status: str,
    mime: str,
    description: str = "",
    origin: bool = True,
    ext: str | None = None,
    artifact: bool = False,
    issue: dict | None = None,
) -> None:
    fm = records.stub_frontmatter(
        record_id=rid, touch_id="corpus.ingest@0.1.0", description=description
    )
    fm["status"] = status
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime=mime, fields={"title": rid[:4]})
    if origin:
        records.append_origin_block(
            post, uri=f"https://e.com/{rid[:4]}", snapshot="2026-05-31T00:00:00Z"
        )
    if issue:
        records.append_issue_block(
            post,
            id=issue["id"],
            severity=issue["severity"],
            resolution=issue.get("resolution", "open"),
            detector=issue["detector"],
            address=issue.get("address"),
        )
    records.dump(post, paths.record_path(root, rid))
    if artifact and ext:
        art = paths.artifact_path(root, rid, ext)
        paths.ensure_parent(art)
        art.write_bytes(b"\x89PNG\r\n\x1a\n")


def _populate(tmp_path: Path) -> Path:
    root = _corpus(tmp_path)
    _write(root, A, status="stub", mime="image/png")  # no artifact → missing
    _write(root, B, status="draft", mime="application/pdf", ext="pdf", artifact=True)
    _write(root, C, status="normalized", mime="image/png", ext="png", artifact=True)
    _write(
        root, D, status="draft", mime="image/png", ext="png", artifact=True,
        issue={
            "id": "format-loss",
            "severity": "warning",
            "detector": "corpus.draft.image@0.1.0",
            "address": "bbox=0,0,1,1",
        },
    )
    _write(root, E, status="draft", mime="image/png", ext="png", artifact=True, origin=False)
    return root


def _ids(items: list[dict]) -> set[str]:
    return {i["id"] for i in items}


def test_records_by_status(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    counts = health.records_by_status(refs)
    assert counts["stub"] == 1
    assert counts["draft"] == 3
    assert counts["normalized"] == 1


def test_stuck_at_stub_supported(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.stuck_at_stub(refs, root)
    assert _ids(items) == {A}
    assert items[0]["supported_draft"] is True  # image drafter is registered


def test_pending_normalize(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    assert _ids(health.pending_normalize(refs)) == {B, D, E}


def test_empty_description_normalized(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    assert _ids(health.empty_description_normalized(refs)) == {C}


def test_unresolved_issues_grouped(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    groups = health.unresolved_issues(refs)
    assert "warning" in groups
    assert {e["id"] for e in groups["warning"]} == {D}


def test_missing_artifacts(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.missing_artifacts(refs, root)
    assert A in _ids(items)  # stub with no artifact
    assert B not in _ids(items)  # has its pdf


def test_validity_violations_no_origin(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.validity_violations(refs)
    by_id = {i["id"]: i for i in items}
    assert E in by_id
    assert any("origin" in p for p in by_id[E]["problems"])


# ---------- CLI ---------- #


def test_health_cli_json(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(["health", "--corpus-root", str(root)])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total_records"] == 5
    assert "records_by_status" in report


def test_health_cli_summary_and_filter(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(
        ["health", "--summary", "--filter", "records_by_status,stuck_at_stub",
         "--corpus-root", str(root)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "corpus health — 5 record(s)" in out
    assert "stuck_at_stub:" in out
