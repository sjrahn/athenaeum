"""Decompose ↔ compile round-trip tests, including roster-in-metadata-zone routing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import frontmatter

from corpus import recordbuild, records, restub, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _make_golden_record_file(corpus_root: Path) -> Path:
    p = corpus_root / "records" / "aa" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "description": "Round-trip golden.",
            "status": "draft",
            "hash": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(
        post, mime="application/pdf", fields={"title": "G", "page_count": 2}
    )
    records.append_origin_block(
        post,
        uri="https://example.com/g.pdf",
        snapshot="2026-05-31T00:00:00Z",
    )
    post.metadata.setdefault("_classifies", []).append(
        {"namespace": "document", "id": "document", "subtype": None, "fields": {}}
    )
    records.append_member(
        post,
        media_type="image/png",
        address="page=1&bbox=0.1,0.1,0.5,0.5",
        transport="blake3:" + "c" * 64,
        fields={"bytes": 4118, "alt": "Cover"},
    )
    sec = segments.Section(
        address="pages=1-2",
        entry="Pages",
        segments=[
            segments.Segment(atom="text", address="page=1", body="One."),
            segments.Segment(atom="text", address="page=2", body="Two."),
        ],
    )
    post.content = segments.emit([sec])
    records.append_issue_block(
        post,
        id="format-loss",
        severity="warning",
        detector="corpus.draft.mime/application/pdf@0.1.0",
    )
    records.dump(post, p)
    return p


def test_decompose_compile_roundtrip_preserves_every_block(tmp_path):
    """A record decomposed and recompiled is byte-identical to the original
    (modulo canonical ordering)."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    original_text = rec.read_text("utf-8")
    original_sha = hashlib.sha256(rec.read_bytes()).hexdigest()

    # Decompose.
    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256=f"sha256:{original_sha}"
    )

    # Manifest must list the roster (metadata zone) before any section/seg.
    manifest = (workdir / "manifest.corpus").read_text("utf-8")
    member_pos = manifest.index("\nmember ")
    section_pos = manifest.index("\nsection ")
    seg_pos = manifest.index("\nseg ")
    assert member_pos < section_pos < seg_pos
    # *(3.4)* The manifest line carries only the closed shape — no `desc=` spill, and none of
    # the descriptive fields the caller passed (spec §4.3.1.4). The substrate must not offer an
    # edit the grammar forbids.
    member_line = manifest[member_pos + 1 : manifest.index("\n", member_pos + 1)]
    assert "bytes=4118" in member_line
    assert "alt=" not in member_line and "desc=" not in member_line

    # Compile.
    rebuilt = recordbuild.read_workdir(workdir, root)
    records.dump(rebuilt, rec)
    rebuilt_text = rec.read_text("utf-8")
    assert rebuilt_text == original_text, "decompose→compile must round-trip byte-identically"


def test_decompose_compile_preserves_frontmatter_title(tmp_path):
    """Regression (curator gotcha #27): a record with a non-empty frontmatter `title`
    must keep it through decompose -> compile. Before the `_CORE` fix the title was
    silently dropped because `write_workdir` serialized only `_CORE` (which omitted
    `title`); `corpus show` masked it via the `title_for` artifact fallback."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    # Promote the golden to a normalized record carrying a real frontmatter title.
    post = records.load(rec)
    post.metadata["title"] = "Power Brake Assist — Parts and Labor"
    records.dump(post, rec)
    original_text = rec.read_text("utf-8")

    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x"
    )
    # The title must survive into the decomposed meta.yaml.
    assert "Power Brake Assist" in (workdir / "meta.yaml").read_text("utf-8")

    rebuilt = recordbuild.read_workdir(workdir, root)
    assert rebuilt.metadata.get("title") == "Power Brake Assist — Parts and Labor"
    records.dump(rebuilt, rec)
    assert rec.read_text("utf-8") == original_text, (
        "decompose->compile must round-trip the frontmatter title byte-identically"
    )
    assert (
        records.title_for(records.load(rec), root) == "Power Brake Assist — Parts and Labor"
    )


def test_manifest_record_line_never_emits_status(tmp_path):
    """*(3.1, §4.1/§12.19)* `status` is retired — `write_workdir` never emits a `status=` key
    on the manifest `record` line (or anywhere else), regardless of what a legacy record's
    frontmatter carried on read."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)  # legacy fixture in-memory carries status: draft
    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    assert "status" not in post.metadata  # dumps() already dropped it when the fixture wrote
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(post, blocks, workdir, source=str(rec), orig_sha256="sha256:x")

    manifest_path = workdir / "manifest.corpus"
    meta_text = (workdir / "meta.yaml").read_text("utf-8")
    record_line = next(
        line for line in manifest_path.read_text("utf-8").splitlines()
        if line.startswith("record ")
    )
    assert "status=" not in record_line
    assert "status:" not in meta_text


def test_manifest_record_line_tolerates_and_ignores_legacy_status(tmp_path):
    """A hand-edited (or pre-3.1) manifest's `record id=<hex> status=<s>` line reads
    parse-tolerantly — `status=` is accepted and silently ignored, never landing on the
    compiled record's metadata."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(post, blocks, workdir, source=str(rec), orig_sha256="sha256:x")

    manifest_path = workdir / "manifest.corpus"
    rid = post.metadata["id"]
    manifest_path.write_text(
        manifest_path.read_text("utf-8").replace(
            f"record id={rid}", f"record id={rid} status=normalized"
        ),
        encoding="utf-8",
    )
    rebuilt = recordbuild.read_workdir(workdir, root)
    assert "status" not in rebuilt.metadata


def test_multiline_description_round_trips_as_block_literal(tmp_path):
    """A multi-line description emits as a YAML block literal in meta.yaml (clearly multi-line,
    quote-free, hand-edit-safe) — never a single-quoted scalar whose first line reads as a
    truncated stump — and still round-trips the exact string."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    nasty = 'Line one: a value\n- "quoted": then #hash, ends with a backslash \\ and @at *star'
    post = records.load(rec)
    post.metadata["description"] = nasty
    records.dump(post, rec)
    original_text = rec.read_text("utf-8")

    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(post, blocks, workdir, source=str(rec), orig_sha256="sha256:x")

    meta_text = (workdir / "meta.yaml").read_text("utf-8")
    assert "description: |" in meta_text  # block literal, not `description: '…`
    assert "description: '" not in meta_text

    rebuilt = recordbuild.read_workdir(workdir, root)
    assert rebuilt.metadata.get("description") == nasty  # exact value preserved
    records.dump(rebuilt, rec)
    assert rec.read_text("utf-8") == original_text  # full round-trip byte-identical


def test_compile_routes_members_to_metadata_zone(tmp_path):
    """Reconciliation #1: `member` ops produce the metadata-zone roster; the content
    body holds only sections/segments."""
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    workdir = tmp_path / "work"
    workdir.mkdir()
    post = records.load(rec)
    blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(
        post, blocks, workdir, source=str(rec), orig_sha256="sha256:x"
    )
    rebuilt = recordbuild.read_workdir(workdir, root)
    assert len(list(records.iter_members(rebuilt))) == 1
    assert "<!--members" not in (rebuilt.content or "")


def test_restub_preserves_byte_and_provenance_state(tmp_path):
    root = _make_corpus(tmp_path)
    rec = _make_golden_record_file(root)
    original_id = "a" * 64

    returned_id = restub.restub(rec)
    assert returned_id == original_id

    re_loaded = records.load(rec)
    # Survives:
    assert re_loaded.metadata["id"] == original_id
    assert re_loaded.metadata["hash"] == "sha256:" + "b" * 64
    assert records.media_type_for(re_loaded) == "application/pdf"
    origins = list(records.iter_origin_blocks(re_loaded))
    assert len(origins) == 1
    assert origins[0]["fields"]["uri"] == "https://example.com/g.pdf"
    # Resets:
    assert "status" not in re_loaded.metadata
    assert "description" not in re_loaded.metadata  # dropped entirely, spec §12.3.4
    # Artifact body fields (incl. the namespaced `title` candidate) reset — re-derived
    # at the next draft; so there's no title candidate and `title_for` is empty.
    assert (records.artifact_block(re_loaded).get("fields") or {}) == {}
    assert records.title_for(re_loaded, root) == ""
    assert list(records.iter_classify_blocks(re_loaded)) == []
    assert list(records.iter_members(re_loaded)) == []
    assert list(records.iter_issue_blocks(re_loaded)) == []
    assert (re_loaded.content or "").strip() == ""
    # Touch chain: first entry kept + re-stub touch appended.
    chain = re_loaded.metadata["touch"]
    assert isinstance(chain, list)
    assert chain[0] == "corpus.ingest@0.1.0"
    assert chain[-1].startswith("corpus.re-stub@")


def _assert_add_blocks_roundtrips(blocks):
    """`recordbuild.add_blocks` + `finish()` must emit byte-identically to the direct
    `segments.emit(blocks)` path drafters used to take."""
    direct = segments.emit(blocks)
    build = recordbuild.begin_from_post(frontmatter.Post(""), None)
    recordbuild.add_blocks(build, blocks)
    recordbuild.finish(build)
    assert build.post.content == direct


def test_add_blocks_matches_segments_emit_sections():
    """Part D, sections-only (pdf-outline / video-transcript shape): nested segments,
    a lead image keyframe marker, and a per-segment perceptual all round-trip."""
    _assert_add_blocks_roundtrips(
        [
            segments.Section(
                address="pages=1-2",
                entry="Intro",
                segments=[
                    segments.Segment(atom="image", address="frame=00:00:00", body=""),
                    segments.Segment(
                        atom="text",
                        address="page=1",
                        body="hello",
                        perceptual="simhash:" + "a" * 16,
                    ),
                ],
            ),
            segments.Section(
                address="pages=3-4",
                entry="Body",
                segments=[segments.Segment(atom="text", address="page=3", body="world")],
            ),
        ]
    )


def test_add_blocks_matches_segments_emit_flat_segments():
    """Part D, top-level segments (html-wrapper / pdf-flat shape), incl. a body-empty
    image marker and a perceptual hash."""
    _assert_add_blocks_roundtrips(
        [
            segments.Segment(
                atom="text",
                address="el=1-3",
                body="lede paragraph",
                perceptual="simhash:" + "b" * 16,
            ),
            segments.Segment(atom="image", address="bbox=0,0,1,1", body=""),
        ]
    )


def test_list_valued_extra_round_trips_through_manifest(tmp_path):
    """A form codebook (`speakers:`, `participants:` — `type: list` on the form overlay)
    must be hand-authorable in a manifest and round-trip decompose→compile: emitted in
    `_fmt_addr`'s bracket-pipe convention (`[a|b]`), parsed back element-wise typed.
    The transcript pilot's finding — before this, only a shaper could build one."""
    root = _make_corpus(tmp_path)
    p = root / "records" / "aa" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "title": "",
            "description": "",
            "hash": "sha256:" + "b" * 64,
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="audio/opus", fields={})
    sec = segments.Section(
        form="transcript",
        extra={"speakers": ["Speaker 1 diarization:1", "Speaker 2 diarization:2"]},
        segments=[
            segments.Segment(
                atom="text",
                overlay="text/transcript",
                address="time_range=00:00-00:06",
                body="Hello.",
                extra={"speaker": 0},
            ),
            segments.Segment(
                atom="text",
                overlay="text/transcript",
                address="time_range=00:06-00:09",
                body="Hi again.",
                extra={"speaker": 1},
            ),
        ],
    )
    post.content = segments.emit([sec])
    records.dump(post, p)
    original_text = p.read_text("utf-8")

    workdir = tmp_path / "work"
    workdir.mkdir()
    loaded = records.load(p)
    blocks = segments.iter_blocks(loaded.content or "")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    recordbuild.write_workdir(loaded, blocks, workdir, source=str(p), orig_sha256=f"sha256:{sha}")

    manifest = (workdir / "manifest.corpus").read_text("utf-8")
    assert "speakers='[Speaker 1 diarization:1|Speaker 2 diarization:2]'" in manifest

    rebuilt = recordbuild.read_workdir(workdir, root)
    rebuilt_secs = [
        b for b in segments.iter_blocks(rebuilt.content or "") if isinstance(b, segments.Section)
    ]
    assert rebuilt_secs[0].extra["speakers"] == [
        "Speaker 1 diarization:1",
        "Speaker 2 diarization:2",
    ]
    assert [s.extra["speaker"] for s in rebuilt_secs[0].segments] == [0, 1]
    records.dump(rebuilt, p)
    assert p.read_text("utf-8") == original_text


def test_typed_and_fmt_scalar_list_symmetry():
    """`_typed` inverts `_fmt_scalar` for lists: element-wise typing, empty list, and
    the single-entry codebook case."""
    import shlex as _shlex

    for value in (["Speaker 1 diarization:1"], [1, 2, 3], ["a b", "c"], []):
        emitted = recordbuild._fmt_scalar(value)
        parsed = recordbuild._typed(_shlex.split(f"k={emitted}")[0].partition("=")[2])
        assert parsed == value, value
