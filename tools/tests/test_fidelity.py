"""`corpus.fidelity.check_fidelity` — the #159 address-fidelity gate, pinned against the four
defect classes the #52 drain measured and the false-positive shapes real bodies produce
(module docstring)."""

from __future__ import annotations

from corpus.fidelity import check_fidelity, el_paths
from corpus.segments import Section, Segment

_STAMP = {"parser": "html.parser"}


def _scan(html: str, blocks: list) -> dict:
    return check_fidelity(html, blocks, _STAMP)


def _kinds(result: dict, kind: str) -> list[dict]:
    return [f for f in result["findings"] if f["kind"] == kind]


# ---------- clean shapes ---------- #


def test_point_address_body_matches_element():
    html = "<body><div><p>The caliper bolts torque to 22 ft-lb.</p></div></body>"
    blocks = [Segment(atom="text", address="el=1.1", body="The caliper bolts torque to 22 ft-lb.")]
    result = _scan(html, blocks)
    assert result["pass"] is True
    assert result["segments"] == 1 and result["lines"] == 1
    assert result["findings"] == []


def test_sibling_range_with_every_child_rendered_passes():
    html = (
        "<body><div>"
        "<h1>Brake System</h1><h2>Caliper Removal</h2><h3>Torque Values</h3>"
        "</div></body>"
    )
    blocks = [
        Segment(
            atom="text",
            address="el=1.[1-3]",
            body="# Brake System\n\n## Caliper Removal\n\n### Torque Values",
        )
    ]
    result = _scan(html, blocks)
    assert result["pass"] is True
    assert result["dropped"] == 0


def test_multi_address_segment_reads_as_one_union():
    """A segment spanning several addresses renders their UNION (§4.3.2.2) — the forward
    check concatenates the element texts rather than demanding each line sit in each."""
    html = "<body><p>First part of the note.</p><p>Second part of the note.</p></body>"
    blocks = [
        Segment(
            atom="text",
            address=["el=1", "el=2"],
            body="First part of the note. Second part of the note.",
        )
    ]
    result = _scan(html, blocks)
    assert result["pass"] is True and result["unsourced"] == 0


def test_address_carrying_other_axes_still_finds_the_el_component():
    html = "<body><p>The caliper bolts torque to 22 ft-lb.</p></body>"
    blocks = [
        Segment(
            atom="text",
            address="el=1&region=0.0,0.0,1.0,1.0",
            body="The caliper bolts torque to 22 ft-lb.",
        )
    ]
    assert _scan(html, blocks)["segments"] == 1


# ---------- the four defect classes ---------- #


def test_missing_h3_is_dropped_and_the_finding_names_it():
    """The measured missing-h3 signature: a sibling range swallows a heading whose text
    never reaches the body. The forward direction is entirely clean — ONE short child
    missing is the whole defect, so it must not be ratio'd away."""
    html = (
        "<body><div>"
        "<h1>Brake System</h1><h2>Caliper Removal</h2><h3>Torque Values</h3>"
        "</div></body>"
    )
    blocks = [
        Segment(atom="text", address="el=1.[1-3]", body="# Brake System\n\n## Caliper Removal")
    ]
    result = _scan(html, blocks)
    assert result["pass"] is False
    assert result["misplaced"] == 0 and result["unsourced"] == 0
    dropped = _kinds(result, "dropped")
    assert len(dropped) == 1 and result["dropped"] == 1
    assert "h3" in dropped[0]["sample"][0] and "Torque Values" in dropped[0]["sample"][0]


def test_borrowed_text_is_misplaced_not_unsourced():
    """A body whose text is in truth from a different region of the artifact — container
    fabrication and off-by-one sibling addresses both look like this from here."""
    html = (
        "<body>"
        "<div><p>Alpha section prose about the alternator.</p></div>"
        "<div><p>Beta section prose about the water pump.</p></div>"
        "</body>"
    )
    blocks = [
        Segment(atom="text", address="el=1", body="Beta section prose about the water pump.")
    ]
    result = _scan(html, blocks)
    assert result["pass"] is False
    assert result["misplaced"] == 1 and result["unsourced"] == 0
    assert "water pump" in _kinds(result, "misplaced")[0]["sample"][0]


def test_unsourced_line_alone_does_not_fail_the_record():
    """Text the artifact's DOM carries nowhere is the honest residue class — a caption, an
    `alt`, a normalizer's own table header. Reported, never a failure."""
    html = "<body><p>Real prose from the source document.</p></body>"
    blocks = [
        Segment(
            atom="text",
            address="el=1",
            body="Real prose from the source document.\nAn editor invented this sentence.",
        )
    ]
    result = _scan(html, blocks)
    assert result["pass"] is True
    assert result["unsourced"] == 1 and result["misplaced"] == 0 and result["dropped"] == 0


def test_unresolvable_address_is_reported_not_raised():
    html = "<body><div><p>Only one child here.</p></div></body>"
    blocks = [Segment(atom="text", address="el=1.9", body="Only one child here.")]
    result = _scan(html, blocks)
    assert result["pass"] is False
    assert result["unresolvable"] == 1
    assert "el=1.9" in _kinds(result, "unresolvable")[0]["sample"][0]


def test_malformed_el_value_is_unresolvable_too():
    """A retired 3.5 flat range on a STAMPED record names nothing under §6.1.1 — the same
    "this address resolves to no element" judgment, not a crash."""
    html = "<body><p>Prose.</p></body>"
    blocks = [Segment(atom="text", address="el=1-8", body="Some rendered prose here.")]
    result = _scan(html, blocks)
    assert result["unresolvable"] == 1 and result["pass"] is False


# ---------- markdown-vs-DOM tolerance ---------- #


def test_markdown_table_body_matches_html_table_element():
    html = (
        "<body><table>"
        "<thead><tr><th>Fastener</th><th>Torque</th></tr></thead>"
        "<tr><td>Head bolts</td><td>22 ft-lb</td></tr>"
        "<tr><td>Wheel lug nuts</td><td>100 ft-lb</td></tr>"
        "</table></body>"
    )
    body = (
        "| Fastener | Torque |\n"
        "|---|---|\n"
        "| Head bolts | 22 ft-lb |\n"
        "| Wheel lug nuts | 100 ft-lb |"
    )
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    assert result["pass"] is True
    assert result["unsourced"] == 0
    assert result["lines"] == 3  # the `|---|---|` separator row is pure syntax, not a line


def test_markdown_link_and_emphasis_match_plain_element_text():
    html = '<body><p>See the <a href="/torque">Torque Spec</a> for <b>details</b>.</p></body>'
    blocks = [
        Segment(
            atom="text",
            address="el=1",
            body="See the [Torque Spec](/torque) for **details**.",
        )
    ]
    assert _scan(html, blocks)["pass"] is True


def test_heading_hashes_and_list_markers_are_shed_before_comparison():
    """`textnorm.norm` strips INLINE markup only; without shedding the leading block syntax
    every faithful heading and ordered-list item scores against a DOM that carries none."""
    html = (
        "<body><div><h2>Removal Procedure</h2>"
        "<ol><li>Disconnect the battery.</li><li>Remove the splash shield.</li></ol>"
        "</div></body>"
    )
    body = "## Removal Procedure\n\n1. Disconnect the battery.\n2. Remove the splash shield."
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    assert result["pass"] is True and result["unsourced"] == 0


def test_short_lines_are_skipped():
    html = "<body><p>Detailed prose about the brake caliper assembly.</p></body>"
    body = "Detailed prose about the brake caliper assembly.\n-\nxy\n---"
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    assert result["lines"] == 1
    assert result["pass"] is True and result["unsourced"] == 0


def test_entity_and_typographic_folding_survives_the_round_trip():
    html = "<body><p>Rock&rsquo;s Auto &amp; Parts — open today</p></body>"
    blocks = [Segment(atom="text", address="el=1", body="Rock's Auto & Parts — open today")]
    assert _scan(html, blocks)["pass"] is True


# ---------- scope ---------- #


def test_segments_without_an_el_address_are_out_of_scope():
    html = "<body><p>Anything at all.</p></body>"
    blocks = [
        Segment(atom="text", address="page=1", body="Text from a paginated artifact."),
        Segment(atom="text", address=None, body="A whole-transport rendering."),
    ]
    result = _scan(html, blocks)
    assert result["segments"] == 0 and result["findings"] == []


def test_structural_placement_and_body_empty_segments_are_out_of_scope():
    html = "<body><h2>A Heading</h2><img src='data:,'/></body>"
    blocks = [
        Segment(atom="structural", address="el=1", body="A Heading", level=2),
        Segment(atom="image", address="el=2"),
        Segment(atom="placement", address="el=2"),
    ]
    result = _scan(html, blocks)
    assert result["segments"] == 0 and result["findings"] == []


def test_section_children_are_judged_and_the_envelope_is_not():
    """`leaf_segments` walks into a section, so a section's children are judged exactly like
    top-level segments — the section's own derived envelope (§12.29) never is."""
    html = "<body><p>Crumb: Vehicle &gt; Brakes</p></body>"
    blocks = [
        Section(
            form="nav",
            address="el=1",
            segments=[Segment(atom="text", address="el=1", body="Crumb: Vehicle > Brakes")],
        )
    ]
    result = _scan(html, blocks)
    assert result["segments"] == 1 and result["pass"] is True


def test_samples_are_capped_per_kind_per_segment():
    html = "<body><p>Source prose.</p></body>"
    body = "\n".join(f"Invented sentence number {i} here." for i in range(8))
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    unsourced = _kinds(result, "unsourced")
    assert result["unsourced"] == 8
    assert len(unsourced) == 1 and len(unsourced[0]["sample"]) == 5


# ---------- address parsing ---------- #


def test_el_paths_reads_scalar_list_and_mixed_axis_addresses():
    assert el_paths("el=1.3") == [("el=1.3", "1.3")]
    assert el_paths(["el=1", "el=2.[3-4]"]) == [("el=1", "1"), ("el=2.[3-4]", "2.[3-4]")]
    assert el_paths("region=0,0,1,1&el=4") == [("region=0,0,1,1&el=4", "4")]
    assert el_paths("page=1") == []
    assert el_paths(None) == []


def test_a_stamp_attesting_a_different_tree_is_refused():
    """The stamp's two attested facts are checked before any comparison — under a different
    tree every address resolves elsewhere, and the defects reported would be the scan's own."""
    import pytest

    html = "<body><p>Prose.</p></body>"
    blocks = [Segment(atom="text", address="el=1", body="Prose here.")]
    with pytest.raises(ValueError, match="element-count mismatch"):
        check_fidelity(html, blocks, {"parser": "html.parser", "elements": 999})
    with pytest.raises(ValueError, match="parser"):
        check_fidelity(html, blocks, {"parser": "lxml"})


def test_a_heading_rendered_as_a_structural_byte_mark_is_not_dropped():
    """A heading's text lands in a STRUCTURAL byte-mark's body (§4.3.2.3/§12.32 — a mark's
    own text IS its body), in a segment of its own. The element is faithfully rendered by the
    record; scoring `dropped` per-segment called that a defect on real drained records."""
    html = "<body><div><h2>Removal Procedure</h2><p>Disconnect the battery.</p></div></body>"
    blocks = [
        Segment(atom="structural", address="el=1.1", body="Removal Procedure", level=2),
        Segment(atom="text", address="el=1", body="Disconnect the battery."),
    ]
    result = _scan(html, blocks)
    assert result["dropped"] == 0 and result["pass"] is True


def test_a_sibling_segment_rendering_the_text_is_not_dropped_either():
    """#89's restoration moves a page's breadcrumb into a trailing `form/nav` span of its
    own, while an enclosing address range still covers the crumb element."""
    html = (
        "<body><div><p>Vehicle &gt; Brakes</p>"
        "<p>The caliper bolts torque to 22 ft-lb.</p></div></body>"
    )
    blocks = [
        Segment(atom="text", address="el=1", body="The caliper bolts torque to 22 ft-lb."),
        Section(form="nav", segments=[Segment(atom="text", body="Vehicle > Brakes")]),
    ]
    result = _scan(html, blocks)
    assert result["dropped"] == 0


def test_an_index_entry_rendered_with_its_category_is_not_misplaced():
    """The alldata index convention: the source nests an entry under a category heading, and
    the entry alone means nothing out of that tree, so a faithful rendering composes
    `- [Category / Entry](url)`. The address names where the ENTRY is — correctly — and the
    category comes from an ancestor."""
    html = (
        "<body><div><h4>Application and ID</h4>"
        "<ul><li>Components</li><li>Connector Views</li></ul></div></body>"
    )
    body = (
        "- [Application and ID / Components](#/c/1)\n"
        "- [Application and ID / Connector Views](#/c/2)"
    )
    result = _scan(html, [Segment(atom="text", address="el=1.2", body=body)])
    assert result["misplaced"] == 0 and result["unsourced"] == 0


def test_context_added_around_an_entry_does_not_excuse_a_stale_body():
    """The allowance admits a line built AROUND text the address really names — it must not
    admit a body from a different subtree entirely."""
    html = (
        "<body><div><h3>Symptoms - Engine Mechanical</h3></div>"
        "<div><p>Strategy based diagnostics is a uniform approach to repair.</p></div></body>"
    )
    blocks = [
        Segment(
            atom="text",
            address="el=1.1",
            body="Strategy based diagnostics is a uniform approach to repair.",
        )
    ]
    result = _scan(html, blocks)
    assert result["misplaced"] == 1 and result["pass"] is False


# ---------- calibration: the three false-positive families (#159 review) ---------- #


def test_a_title_cased_header_matches_an_uppercase_dom_thead():
    """A source that shouts `<th>TSB NUMBER</th>` and a body that renders "TSB Number" carry
    the same content; scoring the difference put a paired dropped + unsourced on every such
    table in the drained set."""
    html = (
        "<body><table>"
        "<thead><tr><th>TSB NUMBER</th><th>TSB DATE</th></tr></thead>"
        "<tr><td>20-NA-026</td><td>2020/07/22</td></tr>"
        "</table></body>"
    )
    body = "| TSB Number | TSB Date |\n|---|---|\n| 20-NA-026 | 2020/07/22 |"
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    assert result["pass"] is True
    assert result["dropped"] == 0 and result["unsourced"] == 0


def test_trademark_marks_compare_across_their_two_spellings():
    html = "<body><p>Read the codes with Tech 2® or GDS 2 before starting.</p></body>"
    blocks = [
        Segment(
            atom="text",
            address="el=1",
            body="Read the codes with Tech 2(R) or GDS 2 before starting.",
        )
    ]
    assert _scan(html, blocks)["pass"] is True


def test_children_whose_whole_text_is_anchor_text_are_never_dropped():
    """Whether an anchor's text survives is `subject-link-flattened`'s question (#118) —
    fidelity counting the same omission again is two gates claiming one defect. A figure
    viewer's chrome is anchors, which is why it needs no hardcoded exclusion list."""
    html = (
        "<body><div>"
        "<p>The caliper bolts torque to 22 ft-lb.</p>"
        '<div><a href="/z">Open In New Tab</a><a href="/p">Zoom/Print</a>'
        '<a href="/f">Click for full-size image</a></div>'
        "</div></body>"
    )
    blocks = [Segment(atom="text", address="el=1", body="The caliper bolts torque to 22 ft-lb.")]
    result = _scan(html, blocks)
    assert result["dropped"] == 0 and result["pass"] is True


def test_a_child_with_text_outside_its_anchors_still_fires():
    """The exclusion must not silence the class the check exists for: a heading, a `<thead>`,
    a prose paragraph all carry their text outside anchors."""
    html = (
        "<body><div>"
        "<p>The caliper bolts torque to 22 ft-lb.</p>"
        '<h3>Torque Values <a href="/ref">(reference)</a></h3>'
        "</div></body>"
    )
    blocks = [Segment(atom="text", address="el=1", body="The caliper bolts torque to 22 ft-lb.")]
    result = _scan(html, blocks)
    assert result["dropped"] == 1
    assert "Torque Values" in _kinds(result, "dropped")[0]["sample"][0]


def test_an_entry_shorter_than_its_category_is_still_an_exact_fragment():
    """The one-third floor rejected entries whose category happened to be the longer half —
    "Description and Operation / Components" is 10 characters of entry against a 12-character
    floor. Exact fragment equality is the honest test of the convention."""
    html = (
        "<body><div><h4>Description and Operation</h4>"
        "<ul><li>Components</li></ul></div></body>"
    )
    result = _scan(
        html,
        [
            Segment(
                atom="text",
                address="el=1.2",
                body="- [Description and Operation / Components](#/c)",
            )
        ],
    )
    assert result["misplaced"] == 0 and result["unsourced"] == 0


def test_a_whole_line_equal_to_a_unit_renders_it():
    html = "<body><div><ul><li>By Symptom</li><li>Recalls and Campaigns</li></ul></div></body>"
    result = _scan(
        html,
        [Segment(atom="text", address="el=1.1", body="- By Symptom\n- Recalls and Campaigns")],
    )
    assert result["pass"] is True and result["misplaced"] == 0


def test_a_joinerless_prose_line_cannot_borrow_an_exact_fragment():
    """A prose line has no joiner to split on, so its only fragment is the whole line — which
    equals no unit. Containing a unit's word is not rendering it."""
    html = (
        "<body><div><ul><li>Vehicle</li></ul></div>"
        "<div><p>All diagnosis on a Vehicle should follow a logical repair process.</p></div>"
        "</body>"
    )
    blocks = [
        Segment(
            atom="text",
            address="el=1.1",
            body="All diagnosis on a Vehicle should follow a logical repair process.",
        )
    ]
    result = _scan(html, blocks)
    assert result["misplaced"] == 1 and result["pass"] is False


def test_a_container_interleaving_rendered_content_no_longer_false_fires():
    """The reverse direction probes LEAVES, not containers. A container's first `_PROBE`
    characters span a heading and the paragraph after it, so any body that renders other
    content between the two — which a faithful rendering of a section does — broke the match
    for the container as a whole (measured on 347055ce)."""
    html = (
        "<body><div><section>"
        "<h3>Bulletin 07-06-01-016C: Internal Engine Noise</h3>"
        "<p>Subject: Information on internal engine noise after oil filter replacement.</p>"
        "</section></div></body>"
    )
    body = (
        "### Bulletin 07-06-01-016C: Internal Engine Noise\n"
        "\n"
        "*An interleaved line the container prefix does not contain.*\n"
        "\n"
        "Subject: Information on internal engine noise after oil filter replacement."
    )
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    assert result["dropped"] == 0


def test_a_leaf_the_record_never_renders_still_fires_from_inside_a_container():
    """Per-leaf probing must not weaken the class: a heading nested two levels down whose
    text reaches no segment is still dropped, and the finding names it."""
    html = (
        "<body><div><section>"
        "<h3>Removal Procedure</h3><p>Disconnect the battery first.</p>"
        "<h3>Torque Values</h3>"
        "</section></div></body>"
    )
    body = "### Removal Procedure\n\nDisconnect the battery first."
    result = _scan(html, [Segment(atom="text", address="el=1", body=body)])
    assert result["dropped"] == 1
    assert "Torque Values" in _kinds(result, "dropped")[0]["sample"][0]


def test_an_anchor_mid_sentence_splits_runs_rather_than_splicing():
    """Deleting an anchor from the middle of a sentence and comparing the remainder joins two
    halves that were never adjacent — "See the for details." appears in no faithful body. Each
    side of the anchor is probed as its own run."""
    html = '<body><p>See the <a href="/t">Torque Spec</a> for details of the job.</p></body>'
    blocks = [
        Segment(
            atom="text",
            address="el=1",
            body="See the [Torque Spec](/t) for details of the job.",
        )
    ]
    result = _scan(html, blocks)
    assert result["dropped"] == 0 and result["pass"] is True


def test_a_heading_carrying_an_inline_link_is_still_probed():
    """An inline `<a>` must not stop its parent being a leaf — the shape #159's missing-h3
    class routinely arrives in. The heading's own text is the run that gets asked for."""
    html = (
        "<body><div><p>Disconnect the battery first.</p>"
        '<h3>Torque <b>Values</b> <a href="/ref">(reference)</a></h3></div></body>'
    )
    blocks = [Segment(atom="text", address="el=1", body="Disconnect the battery first.")]
    result = _scan(html, blocks)
    assert result["dropped"] == 1
    assert "Torque Values" in _kinds(result, "dropped")[0]["sample"][0]


def test_a_sibling_range_covers_the_text_between_its_elements():
    """`el=` components count ELEMENTS (§6.1.1), but the REGION a sibling range names is
    everything between its endpoints — and on a service bulletin that is where the content
    is: `<b>Date</b>February 14, 2013<br>` puts the LABEL in an element and the VALUE in a
    bare text node. Collecting only the elements' own text scored every rendered value as
    borrowed from elsewhere."""
    html = (
        "<body><div>"
        "<b>Bulletin No.:</b>10-08-45-001D<br>"
        "<b>Date</b>February 14, 2013<br>"
        "<b>Subject:</b>Electrical Ground Repair<br>"
        "</div></body>"
    )
    body = (
        "**Bulletin No.:** 10-08-45-001D\n\n"
        "**Date** February 14, 2013\n\n"
        "**Subject:** Electrical Ground Repair"
    )
    result = _scan(html, [Segment(atom="text", address="el=1.[1-6]", body=body)])
    assert result["misplaced"] == 0 and result["unsourced"] == 0


def test_identical_br_siblings_do_not_confuse_the_range_slice():
    """bs4 compares tags STRUCTURALLY, so `contents.index(<br/>)` finds the first `<br/>` in
    the parent rather than the one meant — and a run of `<br>` is exactly what these bulletin
    addresses are made of. The slice is taken by identity."""
    html = "<body><div><br><br><b>Third</b>tail text<br><b>Fifth</b></div></body>"
    result = _scan(html, [Segment(atom="text", address="el=1.[3-4]", body="Third tail text")])
    assert result["misplaced"] == 0 and result["unsourced"] == 0


# ---------- never-regions, and the colon (#159 final calibration) ---------- #

_NEVER = [
    {"role": "print-affordance", "selector": "div.printing-not-ready-message", "renders": "never"},
    {"role": "related-information", "selector": "ad-repair-related-information",
     "renders": "framing"},
    {"role": "article", "selector": "ad-repair-article", "renders": "subject"},
]


def test_a_leaf_inside_a_never_region_is_never_dropped():
    """§7.2: a region the overlay declares `renders: never` is not owed by any rendering, so
    its text is nobody's to have dropped. The print-affordance banner is advice about the
    READER's browser, not a statement the document makes — 64 of the 446 drained records led
    with it as their first dropped finding."""
    html = (
        "<body><div>"
        "<p>The caliper bolts torque to 22 ft-lb.</p>"
        '<div class="printing-not-ready-message">When using the browser Print Button, '
        "images do not preload when first loading the page.</div>"
        "</div></body>"
    )
    blocks = [Segment(atom="text", address="el=1", body="The caliper bolts torque to 22 ft-lb.")]
    assert check_fidelity(html, blocks, _STAMP, _NEVER)["dropped"] == 0
    # Without the declaration the same banner is judged — the exclusion is config-driven,
    # never a hardcoded string, so an undeclared host is still judged in full.
    assert check_fidelity(html, blocks, _STAMP)["dropped"] == 1


def test_a_subject_region_leaf_still_drops():
    """Only `renders: never` is excluded; a subject region's text is exactly what a rendering
    owes, and a swallowed heading inside one still fires."""
    html = (
        "<body><div>"
        "<p>The caliper bolts torque to 22 ft-lb.</p>"
        "<ad-repair-article><h3>Torque Values</h3></ad-repair-article>"
        "</div></body>"
    )
    blocks = [Segment(atom="text", address="el=1", body="The caliper bolts torque to 22 ft-lb.")]
    result = check_fidelity(html, blocks, _STAMP, _NEVER)
    assert result["dropped"] == 1
    assert "Torque Values" in _kinds(result, "dropped")[0]["sample"][0]


def test_never_regions_do_not_soften_the_forward_direction():
    """The exclusion is reverse-direction only. A body line lifted out of a never-region is
    still text the segment took from somewhere it does not address."""
    html = (
        "<body><div><p>Real prose from the addressed element.</p></div>"
        '<div><div class="printing-not-ready-message">Borrowed banner text entirely.</div></div>'
        "</body>"
    )
    blocks = [Segment(atom="text", address="el=1", body="Borrowed banner text entirely.")]
    result = check_fidelity(html, blocks, _STAMP, _NEVER)
    assert result["misplaced"] == 1


def test_a_label_leafs_trailing_colon_folds():
    """`<b>Subject:</b>` against a body that renders the header as a markdown table loses the
    colon on the way — 32 drained records led with exactly that as a dropped finding."""
    html = (
        "<body><div><b>Subject:</b>Hydraulic Power Steering System Leak<br>"
        "<b>Models:</b>2014 and Prior GM Passenger Cars</div></body>"
    )
    body = (
        "| Field | Value |\n|---|---|\n"
        "| Subject | Hydraulic Power Steering System Leak |\n"
        "| Models | 2014 and Prior GM Passenger Cars |"
    )
    result = _scan(html, [Segment(atom="text", address="el=1.[1-4]", body=body)])
    assert result["dropped"] == 0


def test_a_framing_regions_heading_is_not_owed_by_the_transcription():
    """§7.2/#89: a framing region renders under its OWN contract — the crumb line, the
    grouped rail links in a trailing `form/nav` span — not as a verbatim transcription of its
    DOM. The rail's own "Related Information" label was never rendered, corpus-wide, under
    sjrahn's ruling, so the reverse direction must not ask for it back."""
    html = (
        "<body><div>"
        "<p>The caliper bolts torque to 22 ft-lb.</p>"
        "<ad-repair-related-information><h3>Related Information</h3>"
        '<ul><li><a href="/x">Steering Gear</a></li></ul>'
        "</ad-repair-related-information>"
        "</div></body>"
    )
    blocks = [
        Segment(atom="text", address="el=1", body="The caliper bolts torque to 22 ft-lb."),
        Section(form="nav", segments=[Segment(atom="text", body="- [Steering Gear](/x)")]),
    ]
    result = check_fidelity(html, blocks, _STAMP, _NEVER)
    assert result["dropped"] == 0 and result["pass"] is True
    # The same heading inside a SUBJECT region is owed, and still drops.
    subject = html.replace("ad-repair-related-information", "ad-repair-article")
    dropped = check_fidelity(subject, blocks, _STAMP, _NEVER)
    assert dropped["dropped"] == 1
    assert "Related Information" in _kinds(dropped, "dropped")[0]["sample"][0]


def test_a_thousand_deep_unclosed_li_chain_does_not_blow_the_stack():
    """This host emits unclosed `<li>` tags, which `html.parser` nests each inside the
    last — real pages reach ~1,000 elements deep, past Python's recursion limit. The
    gate must MEASURE such a record, not die (or worse: get silently skipped by a
    tolerant caller)."""
    depth = 1200
    html = "<body><div>" + "<li>entry text here " * depth + "</div></body>"
    blocks = [Segment(atom="text", address="el=1", body="entry text here")]
    result = _scan(html, blocks)
    assert result["segments"] == 1
    assert result["unresolvable"] == 0
