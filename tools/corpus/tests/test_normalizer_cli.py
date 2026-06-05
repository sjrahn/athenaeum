"""Normalizer-support commands — `diagnose` / `guidance` / `overlay` + `lint --json`.

Smoke each command over a tmp corpus: the markdown carries its expected sections / field table /
candidate footer, and `lint --json` emits one NDJSON object per finding.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import paths, records, schemas, segments
from corpus._cli import dispatch

RID = "a1" * 32
_BASE = "kind: interpretive\ndescription: src.\napplies_at: [record]\nextended_fields: {}\n"
_MR = (
    "kind: interpretive\n"
    "description: The Majority Report.\n"
    "applies_at: [record]\n"
    "applies_to:\n  content_types: [video/mp4]\n  cues:\n    body_contains: [seder]\n"
    "normalization:\n  guidance: |\n    Segment by news topic, not chapter marker.\n"
    "extended_fields:\n  episode_date: {type: string, required: true}\n"
)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    d = root / "schema" / "composite" / "source"
    d.mkdir(parents=True)
    (d / "source.yaml").write_text(_BASE, encoding="utf-8")
    (d / "mr.yaml").write_text(_MR, encoding="utf-8")
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
        [segments.Segment(atom="text", address="el=1", body="sam seder news")]
    )
    post.metadata["status"] = "draft"
    records.dump(post, paths.record_path(root, RID))


def test_diagnose_one_pager(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)
    rc = dispatch(["diagnose", RID, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    for section in ("## Lint", "## Derived views", "## Candidate", "## Content-zone"):
        assert section in out
    assert "source/mr" in out  # the cue-matching candidate surfaces
    assert "corpus classify <hash> <id>" in out  # the apply footer


def test_diagnose_json(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)
    dispatch(["diagnose", RID, "--json", "--corpus-root", str(root)])
    obj = json.loads(capsys.readouterr().out)
    assert obj["record"] == RID and obj["mime"] == "video/mp4"
    assert any(c["overlay_id"] == "source/mr" for c in obj["candidates"])


def test_guidance(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)
    # Apply the overlay so its guidance shows under "applied classification overlays".
    dispatch(["classify", RID, "source/mr", "--field", "episode_date=2026-06-05",
              "--corpus-root", str(root)])
    capsys.readouterr()
    dispatch(["guidance", RID, "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "## mime schema" in out
    assert "Segment by news topic" in out  # the subclass guidance prose


def test_overlay_field_table(tmp_path, capsys):
    root = _corpus(tmp_path)
    dispatch(["overlay", "source/mr", "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "# overlay source/mr" in out
    assert "| field | type | required" in out
    assert "episode_date" in out and "Segment by news topic" in out


def test_lint_json(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root)  # a draft segment with no entry → entry-missing warning
    dispatch(["lint", RID, "--json", "--corpus-root", str(root)])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines and all({"rule_id", "severity", "message", "record_id"} <= set(o) for o in lines)
    assert any(o["rule_id"] == "entry-missing" for o in lines)
