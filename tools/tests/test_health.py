"""Offline health signals + the `corpus health` CLI.

Builds a small fixture corpus spanning the derived-state layers (spec §4.1 — proxy /
rendered / formed, plus derived-editorial coverage, §4.2.3), an open issue, a missing
artifact, a structurally-invalid record, and a stray legacy `status:` key. Asserts each
signal surfaces the right records. No network.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import health, paths, records, segments
from corpus._cli import dispatch

A = "a0" * 32  # proxy, UNTITLED (no title candidate anywhere), missing artifact, legacy `status:`
B = "b0" * 32  # rendered (stored content, no form), titled (frontmatter override), has its pdf
C = "c0" * 32  # formed, titled via the artifact layer (text/html's packaged `role: title`)
D = "d0" * 32  # formed, titled (frontmatter override), open warning issue
E = "e0" * 32  # no origin block (invalid), titled via the artifact layer (text/html)


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
    artifact_title: bool = True,
    issue: dict | None = None,
    content_blocks: list | None = None,
    legacy_status: str | None = None,
) -> None:
    fm = records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    if title:
        fm["title"] = title
    if description:
        fm["description"] = description
    post = frontmatter.Post(content="", **fm)
    artifact_fields = {"title": rid[:4]} if artifact_title else {}
    records.set_artifact_block(post, mime=mime, fields=artifact_fields)
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
    # No artifact title candidate, no origin, no override → genuinely untitled (spec §4.2.3).
    _write(root, A, mime="image/png", artifact_title=False, legacy_status="stub")
    _write(
        root, B, mime="application/pdf", ext="pdf", artifact=True,
        title="A Bulletin", description="A rendered bulletin with no governing form.",
        content_blocks=[segments.Segment(atom="text", address="page=1", body="hello")],
    )
    _write(
        root, C, mime="text/html", ext="html", artifact=True,
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
    _write(root, E, mime="text/html", ext="html", artifact=True, origin=False)
    return root


def _ids(items: list[dict]) -> set[str]:
    return {i["id"] for i in items}


def test_layer_presence(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    counts = health.layer_presence(refs, root)
    assert counts["proxy"] == 2  # A, E
    assert counts["rendered"] == 1  # B
    assert counts["formed"] == 2  # C, D
    # B, D carry a frontmatter override; C, E derive a title via the artifact layer
    # (text/html's packaged `role: title` mark on its bare `title` field, §12.21 step 2);
    # A has no title candidate anywhere — genuinely untitled (spec §4.2.3).
    assert counts["titled"] == 4  # B, C, D, E
    assert counts["untitled"] == 1  # A
    assert counts["legacy_status"] == 1  # A only


def test_unshaped(tmp_path):
    root = _populate(tmp_path)
    refs = health.load_all_records(root)
    items = health.unshaped(refs, root)
    assert _ids(items) == {A, E}
    # Neither A nor E has an origin overlay declaring a form, so neither is shapable.
    assert all(i["shapable"] is False for i in items)


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
    items = health.validity_violations(refs, root)
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
