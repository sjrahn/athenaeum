"""`corpus.export` — the single-record §10 portable-export engine.

Fixture strategy: draft a small two-image HTML article through the real drafter (as
`test_view_cli.py` does) so `el=3`/`el=6` are genuinely resolvable image addresses backed
by real PNG bytes and real `members` alt text — then REPLACE the drafted content zone with
a hand-authored one that exercises every segment kind the engine has to handle (a
structural mark, plain text, a `text/equation` segment, the two real image addresses, an
`audio` and a `video` positioning marker, a `placement`, and a deliberately duplicated
address to seed a `corpus.lint` finding for the annotated-mode test). Only the `image`
segments' addresses need to resolve for real; every other segment's address is inert as
far as the engine is concerned (pass-through segments are never resolved).
"""

from __future__ import annotations

import base64
import io
import shutil
from pathlib import Path

import frontmatter
import pytest
from PIL import Image

from corpus import export as export_mod
from corpus import hashing, paths, records, segments
from corpus._cli import dispatch
from corpus.store import LocalArtifactStore
from tests._draftlib import draft_for_test

_HAVE_TYPST = shutil.which("typst") is not None
needs_typst = pytest.mark.skipif(not _HAVE_TYPST, reason="typst binary not installed")


def _png_data_uri(w: int, h: int, color: tuple[int, int, int]) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _stage_kitchen_sink(tmp_path: Path) -> tuple[Path, str]:
    """A corpus with one record whose content zone carries one of every segment kind
    `corpus.export` has to handle. Returns `(corpus_root, record_id)`."""
    html_str = (
        "<html><body><p>lede</p>"
        f'<figure><img src="{_png_data_uri(10, 8, (10, 20, 30))}" alt="Chart one"></figure>'
        "<p>middle</p>"
        f'<figure><img src="{_png_data_uri(20, 16, (200, 90, 10))}" alt="Chart two"></figure>'
        "</body></html>"
    )
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    src = tmp_path / "two-images.html"
    src.write_text(html_str, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "transport": f"sha256:{h['sha256']}",
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/text/html@0.1.0"],
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(
        post, uri="https://example.com/article", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))
    assert draft_for_test(root, rid) == 0  # real drafter run — el=3 / el=6 now resolvable

    # Replace the drafted content zone with a hand-authored one exercising every kind.
    post = records.load(paths.record_path(root, rid))
    blocks = [
        segments.Segment(atom="structural", address="el=1", level=1, body="Introduction"),
        segments.Segment(atom="text", address="el=1", body="Lede paragraph text."),
        segments.Segment(atom="image", address="el=3"),
        segments.Segment(atom="text", address="el=4", body="Middle paragraph text."),
        segments.Segment(atom="image", address="el=6", description="fallback alt"),
        segments.Segment(
            atom="text", overlay="text/equation", address="el=7", body="x^2 + y^2 = z^2"
        ),
        segments.Segment(atom="audio", address="time_range=00:00-00:05"),
        segments.Segment(atom="video", address="time_range=00:05-00:10"),
        segments.Segment(atom="placement", address="path=other-member.bin"),
        # Deliberate duplicate of the FIRST text segment's (atom, address) pair — seeds
        # `corpus.lint`'s `segment-address-duplicate` finding for the annotated-mode test.
        segments.Segment(atom="text", address="el=1", body="Duplicate-address segment."),
    ]
    post.content = segments.emit(blocks)
    records.dump(post, paths.record_path(root, rid))
    return root, rid


# ---------- base (plain) export ---------- #


def test_md_export_materializes_images_with_content_addressed_names(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root)

    assert result.md_path is not None and result.md_path.is_file()
    md = result.md_path.read_text(encoding="utf-8")

    assert len(result.assets) == 2
    for asset in result.assets:
        # named by blake3(canonical functional URI) — not by sequence number
        assert len(asset.urihash) == 64
        assert all(c in "0123456789abcdef" for c in asset.urihash)
        assert asset.path.is_file()
        assert f"![{asset.alt}]({asset.filename})" in md

    alts = {a.alt for a in result.assets}
    assert alts == {"Chart one", "Chart two"}  # from the `members` derivation, spec §10


def test_asset_filenames_are_deduplicated_within_a_record(tmp_path):
    """Two segments addressing the SAME surface must materialize to one file, referenced
    twice — the reuse the resolver's own cache naming already gives us for free."""
    root, rid = _stage_kitchen_sink(tmp_path)
    post = records.load(paths.record_path(root, rid))
    blocks = list(segments.iter_blocks(post.content))
    # Duplicate the el=3 image segment so the SAME surface is addressed twice.
    blocks.append(segments.Segment(atom="image", address="el=3"))
    post.content = segments.emit(blocks)
    records.dump(post, paths.record_path(root, rid))

    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    el3_assets = [a for a in result.assets if a.address == "el=3"]
    assert len(el3_assets) == 1  # deduplicated, not two files
    md = result.md_path.read_text(encoding="utf-8")
    assert md.count(el3_assets[0].filename) == 2  # referenced from both segments


def test_structural_mark_becomes_a_heading(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    md = result.md_path.read_text(encoding="utf-8")
    assert "# Introduction" in md


def test_equation_segment_wrapped_as_display_math(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    md = result.md_path.read_text(encoding="utf-8")
    assert "$$x^2 + y^2 = z^2$$" in md


def test_audio_video_and_placement_are_passthrough_placeholders(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    md = result.md_path.read_text(encoding="utf-8")

    kinds = {p.kind for p in result.passthroughs}
    assert {"audio", "video", "placement"} <= kinds

    assert "> [!PASSTHROUGH] time_range=00:00-00:05" in md
    assert "> [!PASSTHROUGH] time_range=00:05-00:10" in md
    assert "> [!PLACEMENT] path=other-member.bin" in md
    # honest — never silently drops what it declines to render
    audio_note = next(p for p in result.passthroughs if p.kind == "audio")
    assert "corpus resolve" in audio_note.detail


def test_frontmatter_carries_title_and_source(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    md = result.md_path.read_text(encoding="utf-8")
    assert md.startswith("---\n")
    assert f"record_id: {rid}" in md
    assert "https://example.com/article" in md


def test_no_typst_or_pdf_written_when_not_requested(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    assert result.typ_path is None
    assert result.pdf_path is None


# ---------- typst / pdf ---------- #


def test_typst_output_renders_without_error(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(
        rid, paths.record_path(root, rid), root, formats=("md", "typst")
    )
    assert result.typ_path is not None and result.typ_path.is_file()
    typ = result.typ_path.read_text(encoding="utf-8")
    assert "#set page" in typ  # standalone preamble
    assert "= Introduction" in typ
    assert "$ x^(2) + y^(2) = z^(2) $" in typ
    for asset in result.assets:
        assert f'image("{asset.filename}"' in typ


def test_pdf_step_self_skips_without_typst_binary(tmp_path, monkeypatch):
    """Honest degradation: the .typ still lands, PDF is skipped with a warning — never a
    crash — following the repo's existing `needs_ffmpeg`-style self-skip discipline."""
    from corpus import typeset as typeset_mod

    monkeypatch.setattr(typeset_mod, "typst_available", lambda: False)
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(
        rid, paths.record_path(root, rid), root, formats=("md", "typst", "pdf")
    )
    assert result.typ_path is not None and result.typ_path.is_file()
    assert result.pdf_path is None
    assert any("typst" in w and "PATH" in w for w in result.warnings)


@needs_typst
def test_pdf_compiles_when_typst_is_available(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(
        rid, paths.record_path(root, rid), root, formats=("md", "typst", "pdf")
    )
    assert result.pdf_path is not None and result.pdf_path.is_file()
    assert result.pdf_path.read_bytes()[:5] == b"%PDF-"


# ---------- annotated mode ---------- #


def test_annotated_metadata_front_block(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(
        rid, paths.record_path(root, rid), root, annotated=True
    )
    md = result.md_path.read_text(encoding="utf-8")
    assert "## export metadata (annotated)" in md
    assert f"`{rid}`" in md
    assert "`text/html`" in md
    assert "https://example.com/article" in md
    assert "corpus.ingest@0.1.0" in md and "corpus.draft.mime/text/html@0.1.0" in md


def test_annotated_segment_labels(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(
        rid, paths.record_path(root, rid), root, annotated=True
    )
    md = result.md_path.read_text(encoding="utf-8")
    assert "`[text/equation @ el=7]`" in md
    assert "`[image @ el=3]`" in md
    assert "`[structural @ el=1]`" in md


def test_annotated_mode_renders_seeded_lint_finding_as_redline(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(
        rid, paths.record_path(root, rid), root, annotated=True
    )
    md = result.md_path.read_text(encoding="utf-8")
    assert "[!LINT-ERROR] segment-address-duplicate" in md
    assert "el=1" in md.split("[!LINT-ERROR] segment-address-duplicate", 1)[1][:60]


def test_plain_export_has_no_annotated_scaffolding(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    result = export_mod.export_record(rid, paths.record_path(root, rid), root, annotated=False)
    md = result.md_path.read_text(encoding="utf-8")
    assert "export metadata (annotated)" not in md
    assert "[!LINT-" not in md
    assert "`[image @" not in md


def test_annotated_and_plain_outputs_coexist(tmp_path):
    """`.annotated` suffix keeps the debug variant from clobbering the plain one, so a
    caller who wants both just runs the command twice."""
    root, rid = _stage_kitchen_sink(tmp_path)
    plain = export_mod.export_record(rid, paths.record_path(root, rid), root)
    annotated = export_mod.export_record(
        rid, paths.record_path(root, rid), root, annotated=True
    )
    assert plain.md_path != annotated.md_path
    assert plain.md_path.is_file() and annotated.md_path.is_file()


# ---------- terminal / proxy records (no content to render) ---------- #


def test_terminal_passthrough_record(tmp_path):
    """A `form/passthrough`-governed record with nothing stored AND nothing derivable
    (no drafter registered for its mime) renders a whole-record pass-through notice
    rather than an empty document. `form/passthrough` itself ships in `schemas_default/`
    (the packaged fallback `test_terminal_forms.py` also relies on) — the only schema
    this test needs to author is the mime-level `form:` default pointing an unregistered
    made-up mime at it, so `derive_body` genuinely has nothing to run (a real registered
    image mime's generic drafter would happily materialize the bytes as an image instead
    — a legitimate, better export for that case, and not what this test is after)."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    (root / "schema" / "mime" / "application").mkdir(parents=True)
    (root / "schema" / "mime" / "application" / "application_x-terminal-test.yaml").write_text(
        "applies_to:\n  content_types: [application/x-terminal-test]\nform:\n  id: passthrough\n",
        encoding="utf-8",
    )
    from corpus import schemas

    schemas.cache_clear()

    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\x00\x01\x02opaque terminal bytes\x03")
    h = hashing.hash_file(blob)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "bin", blob)

    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "description": "", "transport": f"sha256:{h['sha256']}",
         "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/x-terminal-test", fields={})
    records.append_origin_block(
        post, uri="https://example.com/blob.bin", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))

    result = export_mod.export_record(rid, paths.record_path(root, rid), root)
    md = result.md_path.read_text(encoding="utf-8")
    assert "[!PASSTHROUGH]" in md
    assert "terminal form contract" in md
    assert any(p.kind == "record" for p in result.passthroughs)


# ---------- CLI ---------- #


def test_cli_default_format_is_md(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    rc = dispatch(["export", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = root / "export" / rid / f"{rid}.md"
    assert out.is_file()


def test_cli_out_dir_and_formats(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    out_dir = tmp_path / "somewhere"
    rc = dispatch(
        ["export", rid, "--format", "md,typst", "--out", str(out_dir), "--corpus-root", str(root)]
    )
    assert rc == 0
    assert (out_dir / f"{rid}.md").is_file()
    assert (out_dir / f"{rid}.typ").is_file()


def test_cli_rejects_unknown_format(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    rc = dispatch(["export", rid, "--format", "docx", "--corpus-root", str(root)])
    assert rc == 2


def test_cli_annotated_flag(tmp_path):
    root, rid = _stage_kitchen_sink(tmp_path)
    rc = dispatch(["export", rid, "--annotated", "--corpus-root", str(root)])
    assert rc == 0
    out = root / "export" / rid / f"{rid}.annotated.md"
    assert out.is_file()
    assert "export metadata (annotated)" in out.read_text(encoding="utf-8")
