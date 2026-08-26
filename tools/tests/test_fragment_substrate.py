"""The `--split` fragment substrate (parallel section-workers) + address-parsing hardening.

`decompose --split` shards a record's content zone into one `fragments/<ord>-<slug>.corpus`
per top-level block, leaving `manifest.corpus` with only the `record` line, the members
roster, an `include` per fragment, and the issue/context ops. `corpus validate-fragment`
lints a single fragment (or a whole working dir) write-free, so a section-worker can
self-check without being trusted with the record write. See `recordbuild.write_workdir`,
`recordbuild.read_fragment`, and `lint.FRAGMENT_RULES`.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import lint, recordbuild, records, schemas, segments
from corpus._cli import dispatch

_ID = "a" * 64


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _make_two_section_record(root: Path) -> Path:
    """A record with two top-level sections, each holding two segments — enough top-level
    blocks to exercise `--split` across several fragments."""
    p = root / "records" / "aa" / (_ID + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": _ID,
            "description": "Two-section fixture.",
            "hash": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0"],
        }
    )
    records.set_artifact_block(post, mime="application/pdf", fields={"page_count": 4})
    records.append_origin_block(
        post, uri="https://example.com/two.pdf", snapshot="2026-05-31T00:00:00Z"
    )
    sec1 = segments.Section(
        address="pages=1-2",
        segments=[
            segments.Segment(atom="text", address="page=1", body="Section one, page one."),
            segments.Segment(atom="text", address="page=2", body="Section one, page two."),
        ],
    )
    sec2 = segments.Section(
        address="pages=3-4",
        segments=[
            segments.Segment(atom="text", address="page=3", body="Section two, page three."),
            segments.Segment(atom="text", address="page=4", body="Section two, page four."),
        ],
    )
    post.content = segments.emit([sec1, sec2])
    records.dump(post, p)
    return p


# ---------------------------------------------------------------------------
# decompose --split / include resolution / round trip
# ---------------------------------------------------------------------------


def test_split_manifest_reduced_to_record_roster_includes_and_issues(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _make_two_section_record(root)
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")

    workdir = tmp_path / "work"
    workdir.mkdir()
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x", split=True
    )

    assert (workdir / "fragments").is_dir()
    fragments = sorted((workdir / "fragments").glob("*.corpus"))
    assert len(fragments) == 2  # one per top-level section

    manifest = (workdir / "manifest.corpus").read_text("utf-8")
    assert "\nrecord id=" in manifest
    assert manifest.count("include fragments/") == 2
    # The split manifest carries no inline section/seg ops of its own — every content-zone
    # op lives in a fragment, spliced in via `include`.
    assert "\nsection" not in manifest
    assert "\nseg " not in manifest

    # Each fragment holds one section's own `section` + `seg` lines.
    frag_text = fragments[0].read_text("utf-8")
    assert frag_text.startswith("section")
    assert frag_text.count("\nseg ") + (1 if frag_text.startswith("seg ") else 0) >= 1


def test_split_compile_matches_monolithic_compile(tmp_path):
    """A split working dir and its equivalent monolithic one compile to the identical
    record — splitting is purely a layout choice for delegation, never a content change."""
    root = _make_corpus(tmp_path)
    rec = _make_two_section_record(root)
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")

    split_dir = tmp_path / "split"
    split_dir.mkdir()
    recordbuild.write_workdir(
        post, blocks, split_dir, source=str(rec), orig_sha256="sha256:x", split=True
    )

    mono_dir = tmp_path / "mono"
    mono_dir.mkdir()
    recordbuild.write_workdir(
        post, blocks, mono_dir, source=str(rec), orig_sha256="sha256:x", split=False
    )

    from_split = records.dumps(recordbuild.read_workdir(split_dir, root))
    from_mono = records.dumps(recordbuild.read_workdir(mono_dir, root))
    assert from_split == from_mono == rec.read_text("utf-8")


def test_read_fragment_resolves_bodies_against_workdir_root(tmp_path):
    """`@bodies/..` inside a `fragments/*.corpus` file resolves against the working-dir
    ROOT, not the `fragments/` subdirectory — the rule the module docstring states."""
    root = _make_corpus(tmp_path)
    rec = _make_two_section_record(root)
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")

    workdir = tmp_path / "work"
    workdir.mkdir()
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x", split=True
    )

    fragment = sorted((workdir / "fragments").glob("*.corpus"))[0]
    frag_post = recordbuild.read_fragment(fragment, root)
    frag_blocks = segments.iter_blocks(frag_post.content or "")
    assert len(frag_blocks) == 1
    sec = frag_blocks[0]
    assert isinstance(sec, segments.Section)
    bodies = [seg.body for seg in sec.segments]
    assert "Section one, page one." in bodies
    assert "Section one, page two." in bodies


def test_edit_fragment_body_then_compile_reflects_the_edit(tmp_path):
    """decompose --split -> edit one fragment's body sidecar -> compile -> the record
    reflects exactly that edit, with every other segment untouched."""
    root = _make_corpus(tmp_path)
    rec = _make_two_section_record(root)
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")

    workdir = tmp_path / "work"
    workdir.mkdir()
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x", split=True
    )

    # A worker owning fragment 1 edits its own body sidecar in place.
    body_files = sorted((workdir / "bodies").glob("*.md"))
    target = next(f for f in body_files if "page one" in f.read_text("utf-8"))
    target.write_text("Section one, page one — REFINED.", encoding="utf-8")

    rebuilt = recordbuild.read_workdir(workdir, root)
    rebuilt_blocks = segments.iter_blocks(rebuilt.content or "")
    all_bodies = [seg.body for blk in rebuilt_blocks for seg in blk.segments]
    assert "Section one, page one — REFINED." in all_bodies
    assert "Section one, page two." in all_bodies  # untouched sibling
    assert "Section two, page three." in all_bodies  # untouched other fragment
    assert "Section two, page four." in all_bodies


# ---------------------------------------------------------------------------
# validate-fragment: write-free, and catches what it should
# ---------------------------------------------------------------------------


def test_validate_fragment_clean_fragment_exits_zero(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _make_two_section_record(root)
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")

    workdir = tmp_path / "work"
    workdir.mkdir()
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x", split=True
    )
    fragment = sorted((workdir / "fragments").glob("*.corpus"))[0]

    assert dispatch(["validate-fragment", str(fragment), "--corpus-root", str(root)]) == 0


def test_validate_fragment_catches_structural_level_invalid(tmp_path, capsys):
    """A fragment carrying a `seg structural` op with a non-positive `level` is exactly the
    residue `atom-invalid`/construction-time checks let through (recordbuild does not
    itself validate level positivity — only the lint rule does), so it is a real
    isolation-meaningful check for `validate-fragment` to run."""
    root = _make_corpus(tmp_path)
    (root / "fragments_scratch").mkdir()
    fragment = root / "fragments_scratch" / "0001-bad.corpus"
    fragment.write_text("seg structural addr=page=1 level=0\n", encoding="utf-8")

    rc = dispatch(["validate-fragment", str(fragment), "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "structural-level-invalid" in out


def test_validate_fragment_never_writes(tmp_path):
    """Write-free: running `validate-fragment` over a whole decomposed working dir must not
    touch the on-disk record, nor anything in the working dir itself."""
    root = _make_corpus(tmp_path)
    rec = _make_two_section_record(root)
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")

    workdir = tmp_path / "work"
    workdir.mkdir()
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x", split=True
    )

    rec_before = rec.read_bytes()
    rec_mtime_before = rec.stat().st_mtime_ns
    workdir_mtimes_before = {
        f: f.stat().st_mtime_ns for f in workdir.rglob("*") if f.is_file()
    }

    dispatch(["validate-fragment", str(workdir), "--corpus-root", str(root)])

    assert rec.read_bytes() == rec_before
    assert rec.stat().st_mtime_ns == rec_mtime_before
    workdir_mtimes_after = {
        f: f.stat().st_mtime_ns for f in workdir.rglob("*") if f.is_file()
    }
    assert workdir_mtimes_after == workdir_mtimes_before


# ---------------------------------------------------------------------------
# FRAGMENT_RULES — isolation-meaningful subset sanity
# ---------------------------------------------------------------------------


def test_fragment_rules_are_all_registered():
    known = {rid for rid, _fn in lint._REGISTRY}
    assert set(lint.FRAGMENT_RULES) <= known


def test_fragment_rules_exclude_record_scope_only_rules():
    """Frontmatter, metadata-zone (roster/origins/artifact), artifact-backed, and
    annotations-zone rules need whole-record state a lone fragment never carries — they
    must stay out of the fragment-scope subset."""
    excluded = {
        "id-format",
        "touch-format",
        "artifact-block-missing",
        "origins-empty",
        "member-row-unknown-key",
        "issue-shape",
        "context-shape",
        "sweep-shape",
        "embed-unreferenced",
        "embed-missing-target",
        "segment-address-fidelity",
        "subject-link-flattened",
        "terminal-stored-rendering",
    }
    assert not (excluded & set(lint.FRAGMENT_RULES))


def test_fragment_rules_lint_call_runs_without_root_dependent_state(tmp_path):
    """The fragment-scope rule set actually runs clean against a bare `read_fragment`
    post (no frontmatter, no roster) — proving these rules don't secretly need it."""
    root = _make_corpus(tmp_path)
    frag_dir = tmp_path / "frag"
    frag_dir.mkdir()
    fragment = frag_dir / "0001-ok.corpus"
    (frag_dir / "body.md").write_text("Some faithful body text.", encoding="utf-8")
    fragment.write_text("seg text addr=page=1 body=@body.md\n", encoding="utf-8")

    post = recordbuild.read_fragment(fragment, root)
    blocks = segments.iter_blocks(post.content or "")
    findings = lint.lint(post, blocks, root, rules=lint.FRAGMENT_RULES)
    assert findings == []


# ---------------------------------------------------------------------------
# address-pipe-scalar lint rule
# ---------------------------------------------------------------------------


def test_address_pipe_scalar_fires_on_joined_scalar(tmp_path):
    root = _make_corpus(tmp_path)
    seg = segments.Segment(
        atom="text",
        address="page=1&bbox=0,0,1,0.5|page=2&bbox=0,0,1,0.5",
        body="x",
    )
    findings = lint.lint(frontmatter.Post(""), [seg], root, rules=["address-pipe-scalar"])
    assert len(findings) == 1
    assert findings[0].rule_id == "address-pipe-scalar"
    assert findings[0].severity == "error"


def test_address_pipe_scalar_silent_on_proper_list(tmp_path):
    root = _make_corpus(tmp_path)
    seg = segments.Segment(
        atom="text",
        address=["page=1&bbox=0,0,1,0.5", "page=2&bbox=0,0,1,0.5"],
        body="x",
    )
    findings = lint.lint(frontmatter.Post(""), [seg], root, rules=["address-pipe-scalar"])
    assert findings == []


def test_address_pipe_scalar_silent_on_single_region_address(tmp_path):
    root = _make_corpus(tmp_path)
    seg = segments.Segment(atom="text", address="page=1&bbox=0,0,1,0.5", body="x")
    findings = lint.lint(frontmatter.Post(""), [seg], root, rules=["address-pipe-scalar"])
    assert findings == []


# ---------------------------------------------------------------------------
# comma-corruption guard in _parse_addr
# ---------------------------------------------------------------------------


def test_parse_addr_raises_on_comma_joined_bracket_form():
    with pytest.raises(ValueError, match="comma-joins"):
        recordbuild._parse_addr(
            "[page=1&bbox=0.1,0.2,0.3,0.4,page=2&bbox=0.5,0.6,0.7,0.8]"
        )


def test_parse_addr_raises_on_comma_joined_bare_scalar():
    with pytest.raises(ValueError, match="comma-joins"):
        recordbuild._parse_addr("page=1&bbox=0.1,0.2,0.3,0.4,page=2&bbox=0.5,0.6,0.7,0.8")


def test_parse_addr_error_names_the_pipe_separated_fix():
    with pytest.raises(ValueError, match=r"\[page=1&bbox=0\.1,0\.2,0\.3,0\.4\|page=2\]"):
        recordbuild._parse_addr("page=1&bbox=0.1,0.2,0.3,0.4,page=2")


def test_parse_addr_accepts_legitimate_bbox_comma():
    assert (
        recordbuild._parse_addr("page=1&bbox=0.1,0.2,0.3,0.4")
        == "page=1&bbox=0.1,0.2,0.3,0.4"
    )


def test_parse_addr_accepts_proper_bracket_pipe_list():
    assert recordbuild._parse_addr("[page=1|page=2]") == ["page=1", "page=2"]


def test_parse_addr_manifest_line_surfaces_as_manifest_error(tmp_path):
    """The guard fires through the real manifest-reading path too, annotated with the
    offending file + line (`ManifestError`, a `ValueError` subclass)."""
    root = _make_corpus(tmp_path)
    frag_dir = tmp_path / "frag"
    frag_dir.mkdir()
    fragment = frag_dir / "0001-bad.corpus"
    fragment.write_text(
        "seg text addr=page=1&bbox=0.1,0.2,0.3,0.4,page=2&bbox=0.5,0.6,0.7,0.8\n",
        encoding="utf-8",
    )
    with pytest.raises(recordbuild.ManifestError, match="comma-joins"):
        recordbuild.read_fragment(fragment, root)
