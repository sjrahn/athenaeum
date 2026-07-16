"""Offline health signals + the `corpus health` CLI.

Builds a small fixture corpus spanning the derived-state layers (spec §4.1 — proxy /
rendered / formed, plus the orthogonal authored vouch), an open issue, a missing artifact,
a structurally-invalid record, and a stray legacy `status:` key. Asserts each signal
surfaces the right records. No network.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import health, paths, records, segments
from corpus._cli import dispatch

A = "a0" * 32  # proxy, unauthored, missing artifact, carries a legacy `status:` key
B = "b0" * 32  # rendered (stored content, no form), authored, has its pdf
C = "c0" * 32  # formed, UNauthored (empty vouch) — the formed_unauthored target
D = "d0" * 32  # formed, authored, open warning issue
E = "e0" * 32  # no origin block (invalid)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write(
    root: Path,
    rid: str,
    *,
    mime: str,
    title: str = "",
    description: str = "",
    origin: bool = True,
    ext: str | None = None,
    artifact: bool = False,
    issue: dict | None = None,
    content_blocks: list | None = None,
    legacy_status: str | None = None,
) -> None:
    fm = records.stub_frontmatter(
        record_id=rid, touch_id="corpus.ingest@0.1.0", description=description
    )
    fm["title"] = title
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime=mime, fields={"title": rid[:4]})
    if origin:
        records.append_origin_block(
            post, uri=f"https://e.com/{rid[:4]}", snapshot="2026-05-31T00:00:00Z"
        )
    if content_blocks:
        post.content = segments.emit(content_blocks)
    if issue:
        records.append_issue_block(
            post,
            id=issue["id"],
            severity=issue["severity"],
            resolution=issue.get("resolution", "open"),
            detector=issue["detector"],
            address=issue.get("address"),
        )
    record_path = paths.record_path(root, rid)
    records.dump(post, record_path)
    if legacy_status:
        # `dumps()` never emits `status:` (spec §4.1) — even from an in-memory Post that
        # carries one — so simulating a pre-3.1 record that missed the migration sweep
        # means patching the written frontmatter text directly, after the fact.
        text = record_path.read_text(encoding="utf-8")
        record_path.write_text(
            text.replace("\n---\n", f"\nstatus: {legacy_status}\n---\n", 1),
            encoding="utf-8",
        )
    if artifact and ext:
        art = paths.artifact_path(root, rid, ext)
        paths.ensure_parent(art)
        art.write_bytes(b"\x89PNG\r\n\x1a\n")


def _populate(tmp_path: Path) -> Path:
    root = _corpus(tmp_path)
    _write(root, A, mime="image/png", legacy_status="stub")  # no artifact → missing
    _write(
        root, B, mime="application/pdf", ext="pdf", artifact=True,
        title="A Bulletin", description="A rendered bulletin with no governing form.",
        content_blocks=[segments.Segment(atom="text", address="page=1", body="hello")],
    )
    _write(
        root, C, mime="image/png", ext="png", artifact=True,
        content_blocks=[
            segments.Section(
                form="conversation",
                segments=[segments.Segment(atom="text", address="turn=1", body="hi")],
            )
        ],
    )
    _write(
        root, D, mime="image/png", ext="png", artifact=True,
        title="A Photo", description="A described, formed photo record.",
        content_blocks=[
            segments.Section(
                form="conversation",
                segments=[segments.Segment(atom="text", address="turn=1", body="hi")],
            )
        ],
        issue={
            "id": "format-loss",
            "severity": "warning",
            "detector": "corpus.draft.image@0.1.0",
            "address": "bbox=0,0,1,1",
        },
    )
    _write(root, E, mime="image/png", ext="png", artifact=True, origin=False)
    return root


def _ids(items: list[dict]) -> set[str]:
    return {i["id"] for i in items}


def test_layer_presence(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    counts = health.layer_presence(refs)
    assert counts["proxy"] == 2  # A, E
    assert counts["rendered"] == 1  # B
    assert counts["formed"] == 2  # C, D
    assert counts["authored"] == 2  # B, D (title + description both set)
    assert counts["legacy_status"] == 1  # A only


def test_unshaped(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.unshaped(refs, root)
    assert _ids(items) == {A, E}
    # Neither A nor E has an origin overlay declaring a form, so neither is shapable.
    assert all(i["shapable"] is False for i in items)


def test_formed_unauthored(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    assert _ids(health.formed_unauthored(refs)) == {C}


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
    assert A in _ids(items)  # no artifact
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
    assert "layer_presence" in report


def test_health_cli_summary_and_filter(tmp_path, capsys):
    root = _populate(tmp_path)
    rc = dispatch(
        ["health", "--summary", "--filter", "layer_presence,unshaped",
         "--corpus-root", str(root)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "corpus health — 5 record(s)" in out
    assert "unshaped:" in out
