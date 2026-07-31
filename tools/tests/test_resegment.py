"""`corpus.resegment` — the #88 re-segment, extended to the fleet.

Two repairs share one discriminator (`reseat.reads_off_the_member`, reused rather than
re-derived: it is the test #88 itself proved) and one bucketing rule: every borrowed segment
locates to a container element; a container one segment holds alone is a **retarget** (tight)
or a **hold** (loose, §6.1.1's documented limit); a container two or more segments share is
always a **merge**, in the container's own reading order."""

from __future__ import annotations

import frontmatter

from corpus import records, resegment, segments
from corpus.transforms.html import EL_PARSER_ID, element_path, path_root


def _post(*, member_address: str = "el=1.1.1", media_type: str = "image/png") -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata["id"] = "a" * 64
    records.append_member(
        post,
        media_type=media_type,
        address=member_address,
        transport="blake3:" + "b" * 64,
        fields={"bytes": 1},
    )
    return post


def _artifact(tmp_path, html: str):
    p = tmp_path / "page.html"
    p.write_text(html, encoding="utf-8")
    return p


def _container_address(html: str, selector: str) -> str:
    """The §6.1.1 address of the first element `selector` finds — computed independently, the
    same way the module does, so a test can assert plan_record found the SAME element without
    hard-coding a path string that would break the moment the fixture HTML changes shape."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, EL_PARSER_ID)
    root = path_root(soup)
    tag = soup.select_one(selector)
    return f"el={element_path(tag, root)}"


_PROCEDURE = "Grasp the console trim plate and pull upward on it firmly to release it."
_PART_ONE = "First step is to disconnect the wiring harness from the connector housing here."
_PART_TWO = "Second step is to test continuity across all six pins on the connector now."
_LEGEND = "Engine Control Module Connector A43 pin out diagram legend for the harness only."


# ---------- the tight repair: retarget, no body change ---------- #


def test_a_tight_container_is_a_plain_retarget_no_body_change(tmp_path):
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"<p>{_PROCEDURE}</p>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == []
    assert len(plan.retargets) == 1
    r = plan.retargets[0]
    assert r.old_address == "el=1.1.1"
    assert r.new_address == _container_address(html, "p")
    assert r.new_address != "el=1.1.1"

    ok, problems = resegment.apply_record(plan, blocks)
    assert ok, problems
    _img, text = blocks
    assert text.address == r.new_address
    assert text.body == _PROCEDURE  # untouched — a retarget never rewrites a body


def test_already_correct_is_not_a_retarget(tmp_path):
    """A segment already sitting at its own tight address is not this migration's business —
    it does not share the member's `el=` in the first place, so it is never even a candidate."""
    html = f"<html><body><div><img src='x.png'></div><p>{_PROCEDURE}</p></body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    tight_addr = _container_address(html, "p")
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address=tight_addr, body=_PROCEDURE),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == [] and plan.retargets == []
    assert plan.skipped == "no bare text segment borrows a member's address"


# ---------- the loose repair: merge, in document order ---------- #


def test_two_loose_prose_segments_merge_into_one_at_their_shared_container(tmp_path):
    """Neither sentence has an element of its own — both are direct text nodes of one `<div>`,
    exactly the flat-`<div>`-soup shape #88 exists for. Merging them is the only tight address
    either can ever get."""
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.retargets == []
    assert len(plan.merges) == 1
    group = plan.merges[0]
    assert group.address == _container_address(html, "div")
    assert [m.body for m in group.members] == [_PART_ONE, _PART_TWO]

    ok, problems = resegment.apply_record(plan, blocks)
    assert ok, problems
    leaves = list(segments.leaf_segments(blocks))
    assert len(leaves) == 2  # the image marker, and ONE merged prose segment
    merged = next(s for s in leaves if s.atom == "text")
    assert merged.address == group.address
    assert merged.body == f"{_PART_ONE}\n\n{_PART_TWO}"


def test_merge_orders_by_the_document_not_by_declaration_order(tmp_path):
    """The record declares the second sentence first; the document prints it second. The merge
    must read in the SOURCE's order (§4.3.2.1), not the order segments happen to appear in the
    content zone."""
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),  # declared FIRST
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_ONE),  # declared SECOND
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert len(plan.merges) == 1
    assert [m.body for m in plan.merges[0].members] == [_PART_ONE, _PART_TWO]


# ---------- the discriminator, reused not re-derived ---------- #


def test_a_pixel_reading_is_left_alone_for_reseat(tmp_path):
    """Words found NOWHERE in the document are a reading of the member's bytes — #101's
    placement arc, not this migration's. Nothing is planned for it."""
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        "<p>Some unrelated paragraph the page actually prints today.</p>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_LEGEND),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == [] and plan.retargets == []
    assert plan.holds["pixel reading — corpus reseat's population, not this migration's"] == 1


def test_a_typed_overlay_segment_is_never_a_candidate(tmp_path):
    """A declared overlay (`text/ocr`, `text/data-table`, …) asserts it IS a shaped
    transcription of the member — always population A, whatever the words say. It never enters
    this migration's candidate pool at all."""
    html = f"<html><body><div><img src='x.png'></div>{_PROCEDURE}</body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(
            atom="text", overlay="text/ocr", address="el=1.1.1", body=_PROCEDURE
        ),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.skipped == "no bare text segment borrows a member's address"
    assert plan.merges == [] and plan.retargets == []


def test_no_members_is_skipped(tmp_path):
    post = frontmatter.Post("")
    post.metadata["id"] = "a" * 64
    art = _artifact(tmp_path, "<html><body><p>hello</p></body></html>")
    blocks = [segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE)]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.skipped == "no members"


# ---------- refusals: named, never a guess ---------- #


def test_a_multi_region_address_is_out_of_scope(tmp_path):
    html = f"<html><body><div><img src='x.png'></div>{_PROCEDURE}</body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(
            atom="text", address=["el=1.1.1", "el=1.2.1"], body=_PROCEDURE
        ),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == [] and plan.retargets == []
    assert plan.holds["multi-region address — out of scope"] == 1


def test_a_borrowed_address_carrying_params_is_held(tmp_path):
    """A `bbox=` is stated on the PICTURE's own surface — its presence outweighs the
    word-presence test, so this is left for #101 rather than treated as borrowed prose."""
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1&bbox=0,0,1,1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.holds["borrowed address carries params (image-relative; not this population)"] == 1
    # the OTHER segment lost its merge partner but is not silently dropped WITH it — alone
    # against the (now smaller) container it is tight enough on its own merits, so it still
    # gets its own repair. Guards hold what they name; they never sink an unrelated sibling.
    assert plan.merges == []
    assert len(plan.retargets) == 1 and plan.retargets[0].segment.body == _PART_TWO


def test_container_also_holding_a_stranger_holds_the_merge(tmp_path):
    """A third sentence sits in the same `<div>` but belongs to a DIFFERENT segment (a typed
    overlay elsewhere, in this fixture) — merging the two prose segments would still leave the
    container claiming the stranger's text too. Held, not under-merged."""
    stranger = "Third stranger sentence about a torque spec value for this fastener here."
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>{stranger}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
        segments.Segment(
            atom="text", overlay="text/ocr", address="el=9.9.9", body=stranger
        ),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == []
    assert plan.holds["container also holds a non-member segment"] == 2


def test_a_loose_group_still_too_big_for_its_own_combined_text_is_the_documented_limit(tmp_path):
    """Alldata's bulletins are routinely ONE flat `<div>` for the WHOLE document — thousands of
    characters, every paragraph a bare `<b>` label plus text plus `<br>`, so an unwrapped pair
    of stray sentences still locates to that same div. Checking tightness against the GROUP's
    own combined text (not just whether the container also holds something else) is what tells
    this apart from a genuine small flat-prose wrapper, and names it accurately as §6.1.1's
    limit rather than merely "the container holds a stranger."""
    padding = (
        "Lots of additional boilerplate unrelated filler text padding the container element "
        "well beyond the tightness threshold on purpose for this test scenario about padding "
        "content that keeps going for a while to build up sufficient length margin here today "
        "so that the combined pair of sentences below is nowhere near the container's own size."
    )
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>{padding}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == []
    assert plan.holds["no tight container (envelope only) — §6.1.1's documented limit"] == 2


def test_a_field_would_be_silently_dropped_holds_the_merge(tmp_path):
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(
            atom="text", address="el=1.1.1", body=_PART_ONE, description="a normalizer note"
        ),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == []
    assert plan.holds["a field would be silently dropped by the merge"] == 2


def test_a_ledger_cited_address_is_never_moved(tmp_path):
    html = f"<html><body><div><img src='x.png'><p>{_PROCEDURE}</p></div></body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
    ]
    plan = resegment.plan_record(post, art, blocks, cited=frozenset({"el=1.1.1"}))
    assert plan.merges == [] and plan.retargets == []
    assert plan.holds["ledger cites this address"] == 1


def test_a_new_address_already_claimed_holds_the_retarget(tmp_path):
    """The exact `(opener-id, address)` key `segment-address-duplicate` uses — computed here
    the same way, so this guard and that gate cannot disagree."""
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"<p>{_PROCEDURE}</p>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    target = _container_address(html, "p")
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
        # a decoy already sitting on the tight target the retarget would otherwise choose
        segments.Segment(atom="text", address=target, body="already here"),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.retargets == []
    assert plan.holds["new address already claimed in this record"] == 1


def test_a_new_address_already_claimed_holds_the_merge(tmp_path):
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    target = _container_address(html, "div")
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
        # a decoy already sitting on the container the merge would otherwise target
        segments.Segment(atom="text", address=target, body="already here"),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == []
    assert plan.holds["new address already claimed in this record"] == 2


def test_moving_the_only_reference_to_a_member_holds_the_retarget(tmp_path):
    """No `image`/`placement` marker exists for this member in the content zone — the borrowed
    text body is, today, the ONLY segment satisfying `embed-unreferenced` for it. Retargeting
    it away would silently trade one lint finding for another."""
    html = f"<html><body><div><img src='x.png'><p>{_PROCEDURE}</p></div></body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        # no image/placement marker at all — only the borrowed text references el=1.1.1
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.retargets == []
    assert plan.holds["moving this would leave the member's embed unreferenced"] == 1


def test_moving_the_only_reference_to_a_member_holds_the_merge(tmp_path):
    html = (
        "<html><body><div>"
        '<img src="x.png">'
        f"{_PART_ONE}<br>{_PART_TWO}<br>"
        "</div></body></html>"
    )
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.1.1", body=_PART_TWO),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == []
    assert plan.holds["moving this would leave the member's embed unreferenced"] == 2


def test_no_tight_container_alone_is_the_documented_limit(tmp_path):
    """One borrowed segment, a loose container, and no merge partner: §6.1.1 records why this
    has no tight address — text in no element has no tight address. Held, not guessed at."""
    padding = (
        "Lots of additional boilerplate unrelated filler text padding the container element "
        "well beyond the tightness threshold on purpose for this test scenario about padding "
        "content that keeps going for a while to build up sufficient length margin here today."
    )
    short = "Short note about wiring the connector housing today."
    html = f"<html><body><div><img src='x.png'>{short}<br>{padding}</div></body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=short),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == [] and plan.retargets == []
    assert plan.holds["no tight container (envelope only) — §6.1.1's documented limit"] == 1


def test_no_judgeable_probe_is_held(tmp_path):
    """A body with no line of 5+ words gives the discriminator nothing to test presence with —
    `reads_off_the_member` treats it as borrowed (undecidable, biased toward leaving it put),
    and this migration cannot locate it either. Both hold for the same underlying reason."""
    html = "<html><body><div><img src='x.png'>Fig 3</div></body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body="Fig 3"),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == [] and plan.retargets == []
    assert plan.holds["no judgeable probe (body too short to locate)"] == 1


def test_a_probe_with_no_addressable_ancestor_is_held(tmp_path):
    """The prose sits as a DIRECT text child of `<body>` itself — present in the document (so
    `reads_off_the_member` calls it borrowed), but no element NARROWER than the root carries
    it, and the root itself has no §6.1.1 address (§4.3.2.1's whole-record span). Held, not
    guessed at."""
    html = f"<html><body><img src='x.png'>{_PROCEDURE}</body></html>"
    art = _artifact(tmp_path, html)
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert plan.merges == [] and plan.retargets == []
    assert plan.holds["no probe locatable as any element's own text"] == 1


def test_artifact_missing_refuses_the_whole_record(tmp_path):
    post = _post()
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
    ]
    plan = resegment.plan_record(post, tmp_path / "missing.html", blocks)
    assert plan.refused is not None and "missing" in plan.refused


# ---------- apply_record: identity, atomicity, and both repairs together ---------- #


def test_apply_writes_a_retarget_and_a_merge_together(tmp_path):
    html = (
        "<html><body>"
        f"<div><img src='x.png'><p>{_PROCEDURE}</p></div>"
        f"<div><img src='y.png'>{_PART_ONE}<br>{_PART_TWO}<br></div>"
        "</body></html>"
    )
    art = _artifact(tmp_path, html)
    post = frontmatter.Post("")
    post.metadata["id"] = "a" * 64
    records.append_member(
        post, media_type="image/png", address="el=1.1.1",
        transport="blake3:" + "b" * 64, fields={"bytes": 1},
    )
    records.append_member(
        post, media_type="image/png", address="el=1.2.1",
        transport="blake3:" + "c" * 64, fields={"bytes": 1},
    )
    blocks = [
        segments.Segment(atom="image", address="el=1.1.1"),
        segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
        segments.Segment(atom="image", address="el=1.2.1"),
        segments.Segment(atom="text", address="el=1.2.1", body=_PART_ONE),
        segments.Segment(atom="text", address="el=1.2.1", body=_PART_TWO),
    ]
    plan = resegment.plan_record(post, art, blocks)
    assert len(plan.retargets) == 1 and len(plan.merges) == 1

    before_leaves = len(list(segments.leaf_segments(blocks)))
    ok, problems = resegment.apply_record(plan, blocks)
    assert ok, problems
    after_leaves = list(segments.leaf_segments(blocks))
    assert len(after_leaves) == before_leaves - plan.expected_leaf_drop == 4

    rendered = segments.emit(blocks)
    reparsed = list(segments.leaf_segments(segments.iter_blocks(rendered)))
    bodies = [s.body for s in reparsed if (s.body or "").strip()]
    assert _PROCEDURE in bodies
    assert f"{_PART_ONE}\n\n{_PART_TWO}" in bodies
    # neither image marker moved
    assert {s.address for s in reparsed if s.atom == "image"} == {"el=1.1.1", "el=1.2.1"}


def test_apply_is_atomic_a_failing_merge_leaves_every_prior_edit_untouched(tmp_path):
    """A merge group's body-survival check runs for EVERY group before anything mutates — a
    late failure must not leave an earlier retarget half-applied. Exercised directly against
    `apply_record` (a plan built by hand, not by `plan_record`, since a body that fails to
    survive its own merge cannot arise from the module's own construction — this is the
    defence the historical ghost-object bug earned, kept even though `plan_record` cannot
    trigger it today)."""
    seg_retarget = segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE)
    seg_a = segments.Segment(atom="text", address="el=1.2.1", body=_PART_ONE)
    seg_b = segments.Segment(atom="text", address="el=1.2.1", body=_PART_TWO)
    blocks = [seg_retarget, seg_a, seg_b]

    plan = resegment.RecordPlan(
        retargets=[
            resegment.Retarget(segment=seg_retarget, old_address="el=1.1.1", new_address="el=9.9")
        ],
        merges=[resegment.MergeGroup(address="el=9.8", members=[seg_a, seg_b])],
    )
    # Force the merge to fail its own body-survival check without touching plan_record's logic:
    # a merge group whose declared members do not match what merge_bodies would actually join.
    seg_b.body = "totally different text the group's own merge_bodies never produced"
    original_merge_bodies = resegment.merge_bodies
    resegment.merge_bodies = lambda members: (members[0].body or "").strip()
    try:
        ok, problems = resegment.apply_record(plan, blocks)
    finally:
        resegment.merge_bodies = original_merge_bodies

    assert ok is False and problems
    assert seg_retarget.address == "el=1.1.1"  # NOT retargeted — the merge failed first
    assert seg_a.body == _PART_ONE and seg_b.body == (
        "totally different text the group's own merge_bodies never produced"
    )
