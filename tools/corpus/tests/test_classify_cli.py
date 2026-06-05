"""`corpus classify` / `corpus reclassify` (deterministic auto-classification CLI).

Builds a tmp corpus with a `source/majority-report` overlay whose `classify_when` keys on
(mime, ytdlp_channel_id). Covers: single-record classify (+ `--json`, `--dry-run` writes
nothing), bulk reclassify with convergence, an asserted block surviving, and a non-matching
record left untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import paths, records
from corpus._cli import dispatch

CHANNEL = "UC-3jIAlnQmbbVMV6gR7K8aQ"
MR_ID = "aa" * 32
OTHER_ID = "bb" * 32

_BASE = "kind: interpretive\ndescription: src.\napplies_at: [record]\nextended_fields: {}\n"
_MR = (
    "kind: interpretive\n"
    "description: The Majority Report livestream.\n"
    "applies_at: [record]\n"
    "classify_when:\n"
    "  all_of:\n"
    "    - mime: {equals: video/mp4}\n"
    f"    - media.channel_id: {{equals: {CHANNEL}}}\n"
)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    src = root / "schema" / "composite" / "source"
    src.mkdir(parents=True)
    (src / "source.yaml").write_text(_BASE, encoding="utf-8")
    (src / "majority-report.yaml").write_text(_MR, encoding="utf-8")
    return root


def _video(root: Path, rid: str, channel: str) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="video/mp4")
    records.append_origin_block(
        post, uri=f"https://www.youtube.com/watch?v={rid[:6]}", snapshot="2026-06-05T00:00:00Z"
    )
    records.merge_origin_fields(post, {"ytdlp_channel_id": channel})
    post.metadata["status"] = "draft"
    records.dump(post, paths.record_path(root, rid))


# ---------- corpus classify ---------- #


def test_classify_stamps_match(tmp_path, capsys):
    root = _corpus(tmp_path)
    _video(root, MR_ID, CHANNEL)
    rc = dispatch(["classify", MR_ID, "--json", "--corpus-root", str(root)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["added"] == ["source/majority-report"]
    assert out["why"]["source/majority-report"]  # a non-empty satisfying-fact summary
    post = records.load(paths.record_path(root, MR_ID))
    assert "source/majority-report" in records.derived_classifications(post)


def test_classify_non_match_no_change(tmp_path):
    root = _corpus(tmp_path)
    _video(root, OTHER_ID, "UC-different")
    rc = dispatch(["classify", OTHER_ID, "--corpus-root", str(root)])
    assert rc == 0
    post = records.load(paths.record_path(root, OTHER_ID))
    assert list(records.iter_classify_blocks(post)) == []


def test_classify_dry_run_writes_nothing(tmp_path):
    root = _corpus(tmp_path)
    _video(root, MR_ID, CHANNEL)
    before = paths.record_path(root, MR_ID).read_bytes()
    dispatch(["classify", MR_ID, "--dry-run", "--corpus-root", str(root)])
    assert paths.record_path(root, MR_ID).read_bytes() == before


def test_classify_preserves_asserted_block(tmp_path):
    root = _corpus(tmp_path)
    _video(root, MR_ID, CHANNEL)
    post = records.load(paths.record_path(root, MR_ID))
    records.append_classify_block(post, namespace="document", id="document", fields={})
    records.dump(post, paths.record_path(root, MR_ID))

    dispatch(["classify", MR_ID, "--corpus-root", str(root)])
    derived = records.derived_classifications(records.load(paths.record_path(root, MR_ID)))
    assert "source/majority-report" in derived  # auto added
    assert "document" in derived  # asserted survived


# ---------- corpus reclassify ---------- #


def test_reclassify_sweep_and_convergence(tmp_path, capsys):
    root = _corpus(tmp_path)
    _video(root, MR_ID, CHANNEL)
    _video(root, OTHER_ID, "UC-different")

    # Dry run reports exactly the one record that would change, writes nothing.
    before = paths.record_path(root, MR_ID).read_bytes()
    rc = dispatch(["reclassify", "--dry-run", "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 changed, 1 unchanged" in out
    assert paths.record_path(root, MR_ID).read_bytes() == before

    # Real sweep applies it.
    dispatch(["reclassify", "--corpus-root", str(root)])
    assert "source/majority-report" in records.derived_classifications(
        records.load(paths.record_path(root, MR_ID))
    )

    # Convergence: a second sweep changes nothing.
    capsys.readouterr()
    dispatch(["reclassify", "--corpus-root", str(root)])
    assert "0 changed, 2 unchanged" in capsys.readouterr().out


def test_reclassify_classification_filter(tmp_path, capsys):
    root = _corpus(tmp_path)
    _video(root, MR_ID, CHANNEL)
    _video(root, OTHER_ID, "UC-different")
    # Filter to records already carrying the youtube mime — both qualify by mime, only MR matches.
    dispatch(["reclassify", "--mime", "video/mp4", "--corpus-root", str(root)])
    assert "1 changed" in capsys.readouterr().out
