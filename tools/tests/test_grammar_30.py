"""ATH-CORPUS 3.0 grammar — qualified form sections, the structural byte-mark segment,
and the two-status lifecycle (spec §4.3.2.1, §4.3.2.3, §9.1).

These exercise the parser/emitter round-trips (`segments.emit`/`iter_blocks`,
`records.dump`/`load`) and the decompose↔compile substrate (`recordbuild`) that
shapers and the normalize pass build on."""

from __future__ import annotations

import hashlib
from pathlib import Path

import frontmatter
import pytest

from corpus import recordbuild, records, segments

# ---------- structural byte-mark segment (§4.3.2.3) ---------- #


def test_structural_segment_emit_parse_roundtrip():
    mark = segments.Segment(atom="structural", address="el=3", level=2, body="Chapter 2")
    text = segments.emit([mark])
    assert "<!--segment structural" in text
    assert "level: 2" in text
    # *(3.8, §12.32)* the mark's own text is the BODY, never a header field
    assert "mark:" not in text
    assert "\n\nChapter 2\n" in text
    (parsed,) = segments.iter_blocks(text)
    assert parsed.is_structural
    assert parsed.atom == "structural"
    assert parsed.address == "el=3"
    assert parsed.level == 2
    assert parsed.body == "Chapter 2"
    assert parsed.entry is None


def test_legacy_structural_entry_reads_as_mark_and_converts_on_write():
    """Both retired spellings still READ and fold into the body. `entry:` was the byte-mark's
    field through 3.4 and `mark:` through 3.7; §12.32 moved the text into the body because a
    scalar cannot hold what a heading renders. `emit` writes neither field, so a record
    converts the moment its content zone is reconstructed. One-way, and deliberately not
    incidental: `records.dumps` passes the zone through (§12.27)."""
    legacy = "<!--segment structural\naddress: el=7\nlevel: 1\nentry: Diagnostic Aids\n-->\n"
    (parsed,) = segments.iter_blocks(legacy)
    assert parsed.body == "Diagnostic Aids"
    assert parsed.entry is None, "the legacy spelling must not also land on the content field"

    out = segments.emit([parsed])
    assert "mark:" not in out and "entry:" not in out
    assert "Diagnostic Aids" in out
    # ...and the converted form re-reads identically: the conversion is idempotent.
    (again,) = segments.iter_blocks(out)
    assert (again.address, again.level, again.body) == ("el=7", 1, "Diagnostic Aids")


def test_mark_on_a_content_segment_is_refused():
    """`mark:` asserts *the source said this, verbatim* and is checkable against the
    artifact; a content segment offers no such guarantee. Refused rather than tolerated —
    the whole point of the rename is that the two fields are not interchangeable."""
    bad = "<!--segment text\naddress: el=1\nmark: not a byte-mark\n-->\n\nbody\n"
    with pytest.raises(ValueError, match="mark"):
        segments.iter_blocks(bad)


def test_both_spellings_present_prefers_mark():
    """Defensive: a hand-edited record carrying both folds the NEWER field into the body."""
    both = "<!--segment structural\naddress: el=2\nlevel: 1\nmark: New\nentry: Old\n-->\n"
    (parsed,) = segments.iter_blocks(both)
    assert parsed.body == "New"


def test_a_body_beats_a_legacy_field_because_it_can_hold_more():
    """*(3.8, §12.32)* The whole reason the text moved. A body can carry the links a heading
    renders; the scalar never could. So where a migrated record carries both, the body wins —
    it is the value holding what the field had to drop."""
    both = (
        "<!--segment structural\naddress: el=2\nlevel: 1\n"
        "mark: Transmission Control Module (TCM)\n-->\n"
        "\n[Transmission Control Module](#/c/421) ( [TCM](#/c/421) )\n"
    )
    (parsed,) = segments.iter_blocks(both)
    assert parsed.body == "[Transmission Control Module](#/c/421) ( [TCM](#/c/421) )"
    assert "mark:" not in segments.emit([parsed])


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
        segments.Segment(atom="structural", address="el=1", level=1, body="Heading"),
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


def test_form_section_envelope_is_derived_never_stored():
    seg = segments.Segment(atom="text", address="turn=1", body="hi")
    sec = segments.Section(form="conversation", segments=[seg])  # no address
    text = segments.emit([sec])
    section_header = text.split("<!--segment", 1)[0]
    assert section_header.startswith("<!--section conversation")
    assert "address:" not in section_header  # *(3.7)* NO section stores its envelope
    (parsed,) = segments.iter_blocks(text)
    assert parsed.form == "conversation"
    # It is DERIVED on read, from the children that define it (§12.29) — so the value is
    # available to every consumer and cannot disagree with the span it describes.
    assert parsed.address == "turn=1"


def test_bare_2x_section_reads_tolerantly():
    """A bare `<!--section-->` (2.x TOC grouping) has no form and contributes no
    `form/*` classification, but still round-trips."""
    text = "<!--section\naddress: page=1-2\nentry: Front matter\n-->\n\n" + segments.emit(
        [segments.Segment(atom="text", address="page=1", body="x")]
    )
    (sec,) = [b for b in segments.iter_blocks(text) if isinstance(b, segments.Section)]
    assert sec.form is None
    assert sec.address == "page=1-2"


def test_structural_mark_inside_form_section_carries_mark():
    """A structural byte-mark inside a form span MAY carry `mark:` (the source's own
    mark text) — unlike a content segment (§4.3.2.3)."""
    blocks_in = [
        segments.Section(
            address="turn=1",
            form="conversation",
            segments=[
                segments.Segment(atom="structural", address="turn=1", level=1, body="Topic A"),
                segments.Segment(atom="text", address="turn=1", body="msg"),
            ],
        )
    ]
    text = segments.emit(blocks_in)
    (sec,) = segments.iter_blocks(text)
    assert sec.segments[0].is_structural
    assert sec.segments[0].body == "Topic A"


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
                segments.Segment(atom="structural", address="turn=1", level=1, body="Start"),
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


# ---------- 3.5: replay fidelity + the retired-field census ---------- #


def test_add_blocks_replays_every_field():
    """`add_blocks` claims byte-identical replay — pin it, because a field-by-field replay
    loop is exactly the shape that loses a field silently when a rule changes.

    This caught a live one: the loop carried `entry=seg.entry if seg.is_structural else None`
    — the top-level-only rule §4.3.2.2 retired on 2026-07-17, surviving in this one path and
    destroying every in-span authored label written through it (`regions.save_regions` is a
    real caller). Nothing failed; the labels were simply gone from the next write."""
    blocks = [
        segments.Section(
            address="el=1-6",
            form="document",
            entry="Span label",
            description="what this span is",
            segments=[
                segments.Segment(atom="structural", address="el=1", level=1, body="Heading"),
                segments.Segment(atom="text", address="el=2", entry="Inspect", body="a"),
                segments.Segment(
                    atom="image", address="el=3", entry="Fig 1", description="a diagram"
                ),
                segments.Segment(atom="text", address="el=4", perceptual="simhash:ab", body="b"),
            ],
        ),
        segments.Segment(atom="text", address="el=9", entry="Top-level", body="c"),
    ]
    expected = segments.emit(blocks)

    build = recordbuild.begin_from_post(frontmatter.Post(""), None)
    recordbuild.add_blocks(build, blocks)
    assert segments.emit(build.blocks) == expected


def test_pending_retired_fields_finds_each_concern():
    """The one census the 3.5 sweeps count against and health reads — so *what a sweep is
    about to remove* and *what remains unswept* can never be two disagreeing computations."""
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "title": "override", "canonical": "blake3:ab"})
    post.content = segments.emit(
        [
            segments.Section(
                form="index",
                description="a summary of this record",
                extra={"title": "A Title"},
                segments=[
                    segments.Segment(atom="structural", address="el=1", level=1, body="H"),
                    segments.Segment(atom="image", address="el=2", description="a logo"),
                    segments.Segment(atom="text", address="el=3", entry="Label", body="x"),
                ],
            )
        ]
    )
    pending = records.pending_retired_fields(post)

    assert sorted(pending["frontmatter"]) == ["canonical", "title"]
    # *(3.7)* The locator names the span the field sits on. There is no "whole-record" scope
    # any more — a section's extent is its children's — so a section with no stored address
    # is located by its derived envelope (§12.29).
    assert pending["section_description"] == ["['el=1', 'el=2', 'el=3']"]
    assert pending["section_title"] == ["['el=1', 'el=2', 'el=3']"]
    assert pending["segment_description"] == ["el=2"]
    assert pending["segment_entry"] == ["el=3"]
    # a byte-mark already on the current spelling is NOT pending — nothing to sweep
    assert "structural_entry" not in pending


def test_pending_retired_fields_is_empty_on_a_conformant_record():
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64})
    post.content = segments.emit(
        [
            segments.Segment(atom="structural", address="el=1", level=1, body="Heading"),
            segments.Segment(atom="text", address="el=2", body="faithful text"),
            segments.Segment(atom="image", address="el=3"),
        ]
    )
    assert records.pending_retired_fields(post) == {}


# ---------- 3.5: several form spans in one record (§4.3.2.1) ---------- #


def test_a_record_may_carry_several_span_scope_sections():
    """*(3.5)* The shape the whole amendment is for: a page that is an article AND an index
    of sibling links. Before 3.5 a record held one form, so the second half had nowhere to go
    and 77,310 alldata rail links were exiled to the annotations zone (§12.27)."""
    blocks = [
        segments.Section(
            address="el=1-7",
            form="document",
            segments=[segments.Segment(atom="text", address="el=1-7", body="the article")],
        ),
        segments.Section(
            address="el=8-9",
            form="index",
            segments=[segments.Segment(atom="text", address="el=8-9", body="- [Sibling](#/x)")],
        ),
    ]
    text = segments.emit(blocks)
    parsed = segments.iter_blocks(text)
    assert [b.form for b in parsed] == ["document", "index"]
    assert [b.address for b in parsed] == ["el=1-7", "el=8-9"]
    assert segments.emit(parsed) == text


def test_two_form_sections_parse_with_derived_envelopes():
    """*(3.7, §12.29)* The whole-record sibling prohibition is gone with its spelling. A
    section carried no `address` to mean "this form governs everything here"; a section
    stores no address at all now, so there is nothing to read as that claim. Two spans sit
    side by side and each derives exactly what its children cover."""
    text = segments.emit(
        [
            segments.Section(
                form="document",
                segments=[segments.Segment(atom="text", address="el=1", body="a")],
            ),
            segments.Section(
                form="index",
                segments=[segments.Segment(atom="text", address="el=2", body="b")],
            ),
        ]
    )
    a, b = segments.iter_blocks(text)
    assert (a.form, a.address) == ("document", "el=1")
    assert (b.form, b.address) == ("index", "el=2")

def test_section_address_derives_el_and_turn_envelopes():
    """`el` and `turn` had no span strategy until a record needed more than one span —
    invisible while every formed record carried a single whole-record section, which omits
    its envelope by definition."""
    el_kids = [
        segments.Segment(atom="text", address="el=3", body="a"),
        segments.Segment(atom="image", address="el=9"),
    ]
    assert segments.section_address(el_kids) == "el=3-9"

    turn_kids = [
        segments.Segment(atom="text", address="turn=1", body="hi"),
        segments.Segment(atom="text", address="turn=74", body="bye"),
    ]
    assert segments.section_address(turn_kids) == "turn=1-74"

    # a single child collapses rather than emitting a degenerate range
    one = [segments.Segment(atom="text", address="el=5", body="x")]
    assert segments.section_address(one) == "el=5"

    # a heterogeneous mix is still underivable — the envelope has no single scheme
    mixed = [
        segments.Segment(atom="text", address="el=1", body="a"),
        segments.Segment(atom="text", address="page=2", body="b"),
    ]
    assert segments.section_address(mixed) is None


def test_adjacent_same_form_sections_collapse():
    """*(3.7)* Two neighbouring spans under one form with equal declared fields are one span
    written twice — the form is the only judgment a section makes, so the grammar declines to
    represent the split. sjrahn, on a selector page that came out with two `index` spans:
    "i would consider contiguous same form segments to be collapsible"."""
    text = segments.emit(
        [
            segments.Section(
                form="index",
                segments=[segments.Segment(atom="text", address="el=1.1", body="a")],
            ),
            segments.Section(
                form="index",
                segments=[segments.Segment(atom="text", address="el=1.2", body="b")],
            ),
        ]
    )
    (sec,) = segments.iter_blocks(text)
    assert sec.form == "index"
    assert [s.address for s in sec.segments] == ["el=1.1", "el=1.2"]
    assert sec.address == "el=1.[1-2]"


def test_adjacent_sections_whose_declared_fields_differ_do_not_collapse():
    """The safety is field equality, and it is what makes the rule form-dependent in effect
    without naming a form: two `statement` spans in one PDF differ in `account`/`period`, and
    those fields are exactly what distinguishes the two statements."""
    text = segments.emit(
        [
            segments.Section(
                form="statement", extra={"account": "a", "period": "2026-01"},
                segments=[segments.Segment(atom="text", address="page=1", body="a")],
            ),
            segments.Section(
                form="statement", extra={"account": "a", "period": "2026-02"},
                segments=[segments.Segment(atom="text", address="page=2", body="b")],
            ),
        ]
    )
    a, b = segments.iter_blocks(text)
    assert (a.extra["period"], b.extra["period"]) == ("2026-01", "2026-02")


def test_different_forms_never_collapse():
    text = segments.emit(
        [
            segments.Section(
                form="document",
                segments=[segments.Segment(atom="text", address="el=1.1", body="a")],
            ),
            segments.Section(
                form="index",
                segments=[segments.Segment(atom="text", address="el=1.2", body="b")],
            ),
        ]
    )
    a, b = segments.iter_blocks(text)
    assert (a.form, b.form) == ("document", "index")
