"""ATH-CORPUS 3.0 grammar — qualified form sections, the structural byte-mark segment,
and the two-status lifecycle (spec §4.3.2.1, §4.3.2.3, §9.1).

These exercise the parser/emitter round-trips (`segments.emit`/`iter_blocks`,
`records.dump`/`load`) and the decompose↔compile substrate (`recordbuild`) that
shapers and the normalize pass build on."""

from __future__ import annotations

import hashlib
from pathlib import Path

import frontmatter

from corpus import recordbuild, records, segments

# ---------- structural byte-mark segment (§4.3.2.3) ---------- #


def test_structural_segment_emit_parse_roundtrip():
    mark = segments.Segment(atom="structural", address="el=3", level=2, entry="Chapter 2")
    text = segments.emit([mark])
    assert "<!--segment structural" in text
    assert "level: 2" in text
    assert "entry: Chapter 2" in text
    (parsed,) = segments.iter_blocks(text)
    assert parsed.is_structural
    assert parsed.atom == "structural"
    assert parsed.address == "el=3"
    assert parsed.level == 2
    assert parsed.entry == "Chapter 2"
    assert parsed.body == ""


def test_structural_segment_default_level_one():
    mark = segments.Segment(atom="structural", address="page=1")
    text = "<!--segment structural\naddress: page=1\n-->\n"
    (parsed,) = segments.iter_blocks(text)
    assert parsed.level == 1  # source states no hierarchy → level 1
    # emitted with an explicit level so the byte-mark is self-describing
    assert "level: 1" in segments.emit([mark]) or "level:" in segments.emit(
        [segments.Segment(atom="structural", address="page=1", level=1)]
    )


def test_structural_takes_no_atom_overlay():
    import pytest

    with pytest.raises(ValueError, match="structural"):
        segments.iter_blocks("<!--segment structural/foo\naddress: el=1\n-->\n")


def test_structural_excluded_from_body_tokens():
    from corpus import tokens

    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "description": "d", "status": "stub"})
    blocks = [
        segments.Segment(atom="structural", address="el=1", level=1, entry="Heading"),
        segments.Segment(atom="text", address="el=2", body="the body text"),
    ]
    post.content = segments.emit(blocks)
    counts = tokens.token_counts(post)
    # Only the text segment's body counts toward `body`; the byte-mark contributes nothing.
    assert counts["body"] > 0
    assert counts["blocks"] >= counts["body"]


# ---------- qualified form section (§4.3.2.1) ---------- #


def test_form_section_emit_parse_roundtrip():
    seg = segments.Segment(atom="text", address="turn=1", body="Yo")
    sec = segments.Section(
        address="turn=1",
        form="conversation",
        segments=[seg],
        extra={"participants": ["Andy <a@x>", "Steven <s@y>"]},
    )
    text = segments.emit([sec])
    assert text.startswith("<!--section conversation")
    assert "participants:" in text
    (parsed,) = segments.iter_blocks(text)
    assert isinstance(parsed, segments.Section)
    assert parsed.form == "conversation"
    assert parsed.address == "turn=1"
    assert parsed.extra["participants"] == ["Andy <a@x>", "Steven <s@y>"]
    assert len(parsed.segments) == 1


def test_whole_record_form_section_omits_address():
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    sec = segments.Section(form="conversation", segments=[seg])  # no address
    text = segments.emit([sec])
    section_header = text.split("<!--segment", 1)[0]
    assert section_header.startswith("<!--section conversation")
    assert "address:" not in section_header  # whole-record form section omits it
    (parsed,) = segments.iter_blocks(text)
    assert parsed.form == "conversation"
    assert parsed.address is None


def test_bare_2x_section_reads_tolerantly():
    """A bare `<!--section-->` (2.x TOC grouping) has no form and contributes no
    `form/*` classification, but still round-trips."""
    text = "<!--section\naddress: page=1-2\nentry: Front matter\n-->\n\n" + segments.emit(
        [segments.Segment(atom="text", address="page=1", body="x")]
    )
    (sec,) = [b for b in segments.iter_blocks(text) if isinstance(b, segments.Section)]
    assert sec.form is None
    assert sec.address == "page=1-2"


def test_structural_mark_inside_form_section_carries_entry():
    """A structural byte-mark inside a form span MAY carry `entry:` (the source's own
    mark text) — unlike a content segment (§4.3.2.3)."""
    blocks_in = [
        segments.Section(
            address="turn=1",
            form="conversation",
            segments=[
                segments.Segment(atom="structural", address="turn=1", level=1, entry="Topic A"),
                segments.Segment(atom="text", address="turn=1", body="msg"),
            ],
        )
    ]
    text = segments.emit(blocks_in)
    (sec,) = segments.iter_blocks(text)
    assert sec.segments[0].is_structural
    assert sec.segments[0].entry == "Topic A"


def test_content_segment_inside_form_section_carries_entry():
    """A content segment's `entry:` (an authored leaf label, §4.3.2.2) is valid inside a
    form span too — relaxed 2026-07-17 for form-adopt-32: a generic form section wraps an
    already-labeled multi-block rendering whole, and the label identifies the child among
    its siblings exactly as it did at top level. Round-trips through emit → parse."""
    blocks_in = [
        segments.Section(
            form="procedure",
            segments=[
                segments.Segment(atom="text", address="el=1-2", entry="Removal", body="steps"),
                segments.Segment(atom="image", address="el=3", entry="Figure: lever lock"),
            ],
        )
    ]
    text = segments.emit(blocks_in)
    (sec,) = segments.iter_blocks(text)
    assert not sec.segments[0].is_structural
    assert sec.segments[0].entry == "Removal"
    assert sec.segments[1].entry == "Figure: lever lock"
    assert segments.emit(segments.iter_blocks(text)) == text


def test_form_section_yields_form_classification(tmp_path):
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "description": "d", "status": "stub"})
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x/y", snapshot="2026-01-01T00:00:00Z")
    sec = segments.Section(
        form="conversation",
        segments=[segments.Segment(atom="text", address="turn=1", body="hi")],
    )
    post.content = segments.emit([sec])
    assert "form/conversation" in records.derived_classifications(post)


# ---------- decompose ↔ compile substrate (§12.4.2) ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def test_decompose_compile_roundtrips_form_and_structural(tmp_path):
    root = _make_corpus(tmp_path)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "title": "",
            "description": "d",
            "status": "normalized",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x/y", snapshot="2026-01-01T00:00:00Z")
    blocks = [
        segments.Section(
            form="conversation",
            segments=[
                segments.Segment(atom="structural", address="turn=1", level=1, entry="Start"),
                segments.Segment(atom="text", address="turn=1", body="first message"),
                segments.Segment(atom="text", address="turn=2", body="second message"),
            ],
        )
    ]
    post.content = segments.emit(blocks)

    md = root / "records" / "aa" / ("a" * 64 + ".md")
    records.dump(post, md)
    orig = md.read_text("utf-8")

    work = tmp_path / "work"
    parsed_blocks = segments.iter_blocks(post.content or "")
    recordbuild.write_workdir(
        post,
        parsed_blocks,
        work,
        source=str(md),
        orig_sha256=hashlib.sha256(orig.encode()).hexdigest(),
    )
    manifest = (work / "manifest.corpus").read_text("utf-8")
    assert "form=conversation" in manifest
    assert "seg structural" in manifest
    assert "level=1" in manifest

    rebuilt = recordbuild.read_workdir(work, root)
    records.dump(rebuilt, md)
    assert md.read_text("utf-8") == orig  # byte-identical decompose → compile
