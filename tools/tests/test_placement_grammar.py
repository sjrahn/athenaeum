"""The 3.8 grammar additions: the placement segment and the whole-transport address.

Two primitives, and the tests are about what each one REFUSES as much as what it accepts —
the sixth segment kind exists for what it withholds (§4.3.2.4), and an absent address is a
statement rather than a default (§4.3.2.2), which is only true if the guards hold.
"""

from __future__ import annotations

import pytest

from corpus import segments

# ---------- the placement (§4.3.2.4) ---------- #


def test_a_placement_round_trips_with_only_its_address():
    text = "<!--segment placement\naddress: el=1.2.3\n-->\n"
    (seg,) = segments.iter_blocks(text)
    assert seg.atom == "placement" and seg.is_placement
    assert seg.address == "el=1.2.3"
    assert seg.body == "" and seg.overlay is None and seg.level is None
    assert segments.emit([seg]) == text


def test_a_placement_is_not_a_content_segment_and_not_a_byte_mark():
    """The three-way split every consumer keys on: `is_content` for the four atoms,
    `is_structural` for the byte-mark, `is_placement` for this. `not is_structural` was the
    old spelling of "content" and silently admits placements now that there are six kinds."""
    p = segments.Segment(atom="placement", address="el=3")
    assert p.is_placement and not p.is_structural and not p.is_content
    m = segments.Segment(atom="structural", address="el=3", level=1)
    assert m.is_structural and not m.is_placement and not m.is_content
    t = segments.Segment(atom="text", address="el=3", body="x")
    assert t.is_content and not t.is_placement and not t.is_structural


def test_a_placement_takes_no_atom_overlay():
    with pytest.raises(ValueError, match="takes no atom overlay"):
        segments.iter_blocks("<!--segment placement/figure\naddress: el=3\n-->\n")


def test_a_placement_takes_no_body():
    """A body would be the parent rendering the member — the exact thing the kind exists to
    make unstatable (§4.3.2.4)."""
    with pytest.raises(ValueError, match="carries no body"):
        segments.iter_blocks("<!--segment placement\naddress: el=3\n-->\n\nsome prose\n")


def test_a_placement_requires_an_address():
    """It names its member BY the address, so an address-less one names nothing."""
    with pytest.raises(ValueError, match="missing required address"):
        segments.iter_blocks("<!--segment placement-->\n")


def test_a_placement_stacks_beside_a_byte_mark_at_one_address():
    """Identity is (opener-id, address), so a source-declared boundary and a member position
    at the same address are two distinct segments — which is right: the mark is a fact about
    this transport whatever sits there."""
    text = (
        "<!--segment structural\naddress: el=3\nlevel: 2\nmark: Figure 1\n-->\n\n"
        "<!--segment placement\naddress: el=3\n-->\n"
    )
    blocks = segments.iter_blocks(text)
    assert [b.atom for b in blocks] == ["structural", "placement"]


# ---------- the whole-transport address (§4.3.2.2) ---------- #


def test_a_text_segment_may_omit_its_address_and_round_trips_as_the_bare_opener():
    text = "<!--segment text/data-table-->\n\n| a |\n|---|\n"
    (seg,) = segments.iter_blocks(text)
    assert seg.address is None and seg.overlay == "text/data-table"
    assert seg.body.strip() == "| a |\n|---|"
    # The omission IS the statement, so it serializes as an omission — never `address: null`.
    out = segments.emit([seg])
    assert "address" not in out
    assert out.startswith("<!--segment text/data-table-->")


def test_an_address_less_bodyless_text_segment_is_the_one_line_opener():
    seg = segments.Segment(atom="text", overlay="text/data-table-dynamic")
    assert segments.emit([seg]) == "<!--segment text/data-table-dynamic-->\n"


@pytest.mark.parametrize("atom", ["image", "audio", "video"])
def test_a_positioning_marker_may_never_be_address_less(atom):
    """A marker's whole content is *where*; a marker positioning the record's own bytes
    within the record's own flow states nothing (§4.3.2.2)."""
    with pytest.raises(ValueError, match="missing required address"):
        segments.iter_blocks(f"<!--segment {atom}-->\n")


def test_a_byte_mark_may_never_be_address_less():
    with pytest.raises(ValueError, match="missing required address"):
        segments.iter_blocks("<!--segment structural\nlevel: 1\nmark: X\n-->\n")


def test_an_address_less_segment_coexists_with_addressed_extractions_of_parts():
    """The identity rule does the bounding: `(opener-id, None)` is one value like any other,
    so a whole-transport rendering and a `bbox=` extraction of part of the same artifact stand
    side by side exactly as two addressed segments would."""
    text = (
        "<!--segment text/data-table-->\n\n| whole |\n|---|\n\n"
        "<!--segment text/ocr\naddress: bbox=0,0.8,1,0.2\n-->\n\nLEGEND\n"
    )
    blocks = segments.iter_blocks(text)
    assert [(b.overlay, b.address) for b in blocks] == [
        ("text/data-table", None),
        ("text/ocr", "bbox=0,0.8,1,0.2"),
    ]
    assert segments.emit(blocks).rstrip("\n") == text.rstrip("\n")


def test_a_span_of_placements_still_derives_its_envelope():
    """A form span whose children are all placements is the conforming schematic shape after
    3.8, and the envelope derivation is unaffected — it reads addresses, and placements have
    them (here two non-adjacent siblings, so the envelope is the ordered list rather than a
    range, which is what §6.1.1 says a genuinely disjoint span is)."""
    text = (
        "<!--section schematic-->\n\n"
        "<!--segment placement\naddress: el=1.3\n-->\n\n"
        "<!--segment placement\naddress: el=1.5\n-->\n"
    )
    (sec,) = segments.iter_blocks(text)
    assert sec.form == "schematic"
    assert [s.address for s in sec.segments] == ["el=1.3", "el=1.5"]
    assert sec.address == ["el=1.3", "el=1.5"]

    contiguous = segments.iter_blocks(
        "<!--section schematic-->\n\n"
        "<!--segment placement\naddress: el=1.3\n-->\n\n"
        "<!--segment placement\naddress: el=1.4\n-->\n"
    )
    assert contiguous[0].address == "el=1.[3-4]"
