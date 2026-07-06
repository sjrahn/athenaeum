"""Normalizer-support commands — `diagnose` / `guidance` / `overlay` + `lint --json`.

Smoke each command over a tmp corpus: the markdown carries its expected sections;
`corpus overlay <host>` resolves an origin overlay; and `lint --json` emits a single
JSON array of findings.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import paths, records, schemas, segments
from corpus._cli import dispatch

RID = "a1" * 32


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _record(root: Path) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=RID, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="video/mp4")
    records.append_origin_block(
        post, uri="https://youtube.com/watch?v=x", snapshot="2026-06-05T00:00:00Z"
    )
    post.content = segments.emit(
        [
            segments.Segment(atom="text", address="el=1", body="sam seder news"),
            # a second entry-less top block so entry-missing fires (single-block records
            # are exempt — the record is its own TOC line)
            segments.Segment(atom="text", address="el=2", body="more news"),
        ]
    )
    post.metadata["status"] = "draft"
    records.dump(post, paths.record_path(root, RID))


def test_diagnose_one_pager(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)
    rc = dispatch(["diagnose", RID, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    for section in ("## Lint", "## Derived views", "## Content-zone"):
        assert section in out
    assert "## Candidate" not in out  # candidate ranking retired with the composite umbrella


def test_diagnose_json(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)
    dispatch(["diagnose", RID, "--json", "--corpus-root", str(root)])
    obj = json.loads(capsys.readouterr().out)
    assert obj["record"] == RID and obj["mime"] == "video/mp4"
    assert "candidates" not in obj  # retired with the composite umbrella


def test_guidance(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)
    od = root / "schema" / "origin" / "web"
    od.mkdir(parents=True)
    (od / "youtube.com.yaml").write_text(
        "applies_to:\n  host_pattern: youtube.com\n  include_subdomains: true\n"
        "normalization:\n  guidance: |\n    Treat the transcript as the primary text.\n",
        encoding="utf-8",
    )
    schemas.cache_clear()
    # Qualify the record's origin block so the overlay counts as applied.
    path = paths.record_path(root, RID)
    post = records.load(path)
    records.set_origin_schema_id(post, "youtube.com")
    records.dump(post, path)
    dispatch(["guidance", RID, "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "## mime schema" in out
    assert "Treat the transcript as the primary text" in out  # applied origin guidance


def test_overlay_resolves_origin_overlay(tmp_path, capsys):
    """`corpus overlay <host>` resolves an origin overlay so the normalizer can read a
    host's origin guidance at normalize time."""
    root = _corpus(tmp_path)
    od = root / "schema" / "origin"
    od.mkdir(parents=True)
    (od / "youtube.com.yaml").write_text(
        "applies_to:\n  host_pattern: youtube.com\n  include_subdomains: true\n"
        "capture:\n  capturer: video\n"
        "normalization:\n  guidance: |\n    Treat the transcript as the primary text.\n",
        encoding="utf-8",
    )
    schemas.cache_clear()
    rc = dispatch(["overlay", "youtube.com", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# overlay youtube.com  (origin)" in out
    assert "Treat the transcript as the primary text" in out  # origin normalization.guidance
    assert "youtube.com" in out and "`capture`" in out  # host match + declared section


def test_overlay_unknown_is_error(tmp_path):
    root = _corpus(tmp_path)
    try:
        dispatch(["overlay", "nope.example", "--corpus-root", str(root)])
    except SystemExit as e:
        assert e.code  # no such origin overlay → non-zero exit
    else:
        raise AssertionError("expected SystemExit for an unknown overlay")


def test_lint_json(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)  # a draft segment with no entry → entry-missing warning
    dispatch(["lint", RID, "--json", "--corpus-root", str(root)])
    findings = json.loads(capsys.readouterr().out)  # a single JSON array, not NDJSON
    assert isinstance(findings, list) and findings
    assert all({"rule_id", "severity", "message", "record_id"} <= set(o) for o in findings)
    assert any(o["rule_id"] == "entry-missing" for o in findings)
