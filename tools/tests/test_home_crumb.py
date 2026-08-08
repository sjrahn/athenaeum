"""The §89 crumb-homing migration — `corpus.home_crumb`.

What these pin: the migration only moves a breadcrumb segment that is ALONE in its own
segment and spelled verbatim (chain starts at the line's first character, uses every label,
runs to the line's end) into a new trailing `<!--section nav-->`; it REFUSES rather than
guesses on the three populations #52's acceptance check found sharing one symptom — mixed into
a larger segment, prefixed with the vehicle-name string (#89's third defect), and a
partial/residue chain; it never leaves a form span childless; it is idempotent; the positive
landing check actually confirms the move landed (not merely that lint didn't get worse) — the
lesson a prior migration paid for when a neutrality gate passed on a run that reported hundreds
of "merges" while writing nothing; the population it used to refuse outright — the crumb
leading a `form/index` span that is the record's whole content — now moves too, since `nav`
and `index` are different form ids and can never merge (#89); and a record a prior run already
homed under the pre-#89 `index` spelling gets that span's opener RE-SPELLED to `nav`, gated the
same as any other rewrite, rather than skipped.
"""

from __future__ import annotations

import frontmatter

from corpus import hashing, home_crumb, paths, records, schemas, segments
from corpus.segments import Section, Segment
from corpus.store import LocalArtifactStore

HOST = "my.alldata.com"

_OVERLAY_YAML = """\
regions:
  - role: breadcrumb
    selector: div.article-breadcrumb
    renders: framing
  - role: article
    selector: div.article-body
    renders: subject
"""

# Three real crumb labels, matching the host's own shape: two anchors plus a trailing plain
# leaf (the overlay: "the first crumb is literally the word 'Vehicle'... does NOT name the
# car"). `crumb_labels` reads these off the artifact, never off the record.
_CRUMB_HTML = (
    '<div class="article-breadcrumb">'
    '<a href="#/vehicle/1">Vehicle</a> &gt; '
    '<a href="#/vehicle/1/component/2">Technical Service Bulletins</a> &gt; '
    "Some Bulletin Title"
    "</div>"
)
_VERBATIM_CRUMB = "Vehicle > Technical Service Bulletins > Some Bulletin Title"


def _make_corpus(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    overlay_dir = root / "schema" / "origin" / "web"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / f"{HOST}.yaml").write_text(_OVERLAY_YAML, encoding="utf-8")
    schemas.cache_clear()
    return root


def _element_count(src):
    from bs4 import BeautifulSoup

    from corpus.transforms import html as html_tf

    soup = BeautifulSoup(src.read_bytes(), html_tf.EL_PARSER_ID)
    return html_tf.total_element_count(soup)


def _record(
    tmp_path,
    blocks,
    *,
    crumb_html: str | None = _CRUMB_HTML,
    origin_host: str | None = HOST,
    with_artifact: bool = True,
):
    root = _make_corpus(tmp_path)
    src = root / "page.html"
    body_html = crumb_html or ""
    doc = (
        "<html><head><title>Some Bulletin Title - ALLDATA diy</title></head><body>"
        f"{body_html}"
        '<div class="article-body">Unrelated article prose that fills the subject region.</div>'
        "</body></html>"
    )
    src.write_text(doc, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    if with_artifact:
        LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post,
        mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": _element_count(src)}},
    )
    if origin_host:
        records.append_origin_block(
            post,
            uri="https://my.alldata.com/repair/#/vehicle/1/component/2/itype/10",
            snapshot="2026-01-01T00:00:00Z",
            schema_id=origin_host,
        )
    post.content = segments.emit(blocks)
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf


# ---------- the happy path ---------- #


def test_a_verbatim_crumb_inside_an_article_span_moves_into_a_new_trailing_nav_span(
    tmp_path,
):
    """The genuinely handleable shape (116 of 525): the crumb sits as the first child of a
    `form/article` span alongside the genuine article content. It moves out, untouched
    byte-for-byte, into a NEW trailing `<!--section nav-->`."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="article",
                segments=[
                    Segment(atom="text", address="el=1.2.1", body=_VERBATIM_CRUMB),
                    Segment(
                        atom="text",
                        address="el=1.2.2",
                        body="Removal: 1. Disconnect the battery. 2. Remove the cover.",
                    ),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert dict(report.counts) == {"breadcrumb homed": 1}

    blocks = segments.iter_blocks(records.loads(report.new_text).content)  # type: ignore[arg-type]
    # The original span kept its other child, minus the crumb.
    assert blocks[0].form == "article"
    assert [s.body for s in blocks[0].segments] == [
        "Removal: 1. Disconnect the battery. 2. Remove the cover."
    ]
    # A NEW trailing span carries the crumb, verbatim, and nothing else.
    assert blocks[-1].form == "nav"
    (crumb_seg,) = blocks[-1].segments
    assert crumb_seg.body.strip() == _VERBATIM_CRUMB
    assert crumb_seg.address == "el=1.2.1"  # untouched — a pure move, not a re-address


def test_a_markdown_linked_crumb_line_still_matches(tmp_path):
    """A faithfully-rendered crumb keeps its hrefs — `[Vehicle](url) > …`. The matcher
    strips markdown links to their text before normalizing; without that, the URL residue
    sits in the inter-label gap and the adjacency test calls a real crumb absent (found
    when the #52 pilot's fleet started rendering crumbs linked)."""
    linked = (
        "[Vehicle](#/carids/46076/components/1) > "
        "[Technical Service Bulletins](#/carids/46076/itypes/13) > Some Bulletin Title"
    )
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="article",
                segments=[
                    Segment(atom="text", address="el=1.2.1", body=linked),
                    Segment(atom="text", address="el=1.2.2", body="Prose body."),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert dict(report.counts) == {"breadcrumb homed": 1}
    blocks = segments.iter_blocks(records.loads(report.new_text).content)  # type: ignore[arg-type]
    assert blocks[-1].form == "nav"
    (crumb_seg,) = blocks[-1].segments
    assert crumb_seg.body.strip() == linked  # moved byte-for-byte, links intact


def test_a_crumb_leading_a_bare_index_span_that_is_the_whole_record_now_moves(tmp_path):
    """The commonest real shape (397 of 525), and the one this module used to refuse outright:
    a bare `form/index` span declares no fields, so before #89 it was indistinguishable from
    another bare `form/index` span, and §4.3.2.1's own adjacent-same-form rule would have
    merged two of them on sight — every one of these records is its own sole top-level block, a
    link-index page (the overlay's "the link list IS the content") that happens to carry the
    crumb as a co-located entry. `form/nav` ends the overload: the crumb now moves into a
    trailing `nav` span, a different form id from the `index` span it leaves behind, so the two
    can never merge, whatever the remaining span declares."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(atom="text", address="el=1.1.1", body=_VERBATIM_CRUMB),
                    Segment(
                        atom="text",
                        address="el=1.1.2",
                        body="- [First Link](https://my.alldata.com/a)\n"
                        "- [Second Link](https://my.alldata.com/b)",
                    ),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    blocks = segments.iter_blocks(records.loads(report.new_text).content)
    assert [b.form for b in blocks] == ["index", "nav"]
    assert blocks[-1].segments[0].body.strip() == _VERBATIM_CRUMB


def test_an_index_span_carrying_LEGACY_fields_now_moves_too(tmp_path):
    """Before #89, this was the trap: 396 of the 509 live candidates are index spans still
    carrying legacy `title:`/`description:`. Those fields DID satisfy §4.3.2.1's equality
    test, so a trailing index span genuinely stayed separate from them — until `corpus
    drop-retired` swept the fields and the two spans became identical and merged, a shape
    whose correctness EXPIRED silently. `form/nav` ends it: the new trailing span is a
    different form id regardless of what the remaining span declares, so the field's presence
    or removal no longer matters."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                description="A link index for the cooling system.",
                segments=[
                    Segment(atom="text", address="el=1.1.1", body=_VERBATIM_CRUMB),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    blocks = segments.iter_blocks(records.loads(report.new_text).content)
    assert [b.form for b in blocks] == ["index", "nav"]


def test_a_crumb_leading_a_bare_index_span_still_moves_when_another_span_follows(tmp_path):
    """The same `form/index` container as the tests above, but it is NOT the record's last
    top-level block — an unrelated `form/article` span sits between it and the new trailing
    `nav` span. Moves the same way regardless (the form id split makes adjacency moot too)."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(atom="text", address="el=1.1.1", body=_VERBATIM_CRUMB),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            ),
            Section(
                form="article",
                segments=[Segment(atom="text", address="el=2.1", body="Unrelated content.")],
            ),
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed, report.hold
    blocks = segments.iter_blocks(records.loads(report.new_text).content)
    assert [b.form for b in blocks] == ["index", "article", "nav"]
    assert blocks[-1].segments[0].body.strip() == _VERBATIM_CRUMB


def test_idempotent_a_second_pass_is_a_clean_skip(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="article",
                segments=[
                    Segment(atom="text", address="el=1.1.1", body=_VERBATIM_CRUMB),
                    Segment(atom="text", address="el=1.1.2", body="Genuine article content."),
                ],
            )
        ],
    )
    first = home_crumb.home_crumb_record(rf, root)
    assert first.changed, first.hold
    rf.write_text(first.new_text, encoding="utf-8")

    second = home_crumb.home_crumb_record(rf, root)
    assert second.changed is False
    assert second.skipped == "already homed — the breadcrumb sits in the trailing nav span"


def test_a_legacy_index_spelled_homed_crumb_is_re_spelled_to_nav(tmp_path):
    """A record `corpus home-crumb` homed before `form/nav` existed still carries its crumb in
    a trailing bare `<!--section index-->`. Re-running now finds it already homed under the OLD
    spelling and RE-SPELLS the opener to `nav` — reported as a change, not a skip — through the
    same round-trip and neutrality gates as any other rewrite (#89's convergence: the ~113
    already-homed records converge this way, with no separate script)."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="article",
                segments=[
                    Segment(atom="text", address="el=1.1.1", body="Genuine article content."),
                ],
            ),
            Section(
                form="index",
                segments=[Segment(atom="text", address="el=1.1.2", body=_VERBATIM_CRUMB)],
            ),
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert dict(report.counts) == {"framing span re-spelled: index -> nav": 1}

    blocks = segments.iter_blocks(records.loads(report.new_text).content)
    assert [b.form for b in blocks] == ["article", "nav"]
    assert blocks[-1].segments[0].body.strip() == _VERBATIM_CRUMB


# ---------- the refusals ---------- #


def test_a_crumb_mixed_into_a_larger_segment_is_held(tmp_path):
    """351-population analog: the crumb line is real, but the segment carries other content
    too — splitting it out is re-segmentation (#12.33), not a block move."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(
                        atom="text",
                        address="el=1.1.1",
                        body=f"{_VERBATIM_CRUMB}\n\nSome further prose that is not the crumb.",
                    ),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "mixed" in (report.hold or "")


def test_a_vehicle_name_prefixed_crumb_is_held_not_rewritten(tmp_path):
    """#89's third defect: nearly every sampled `inline` hit glues the vehicle header string
    onto the front. The overlay's VERBATIM rule forbids it, and fixing the text is
    re-authoring — a pure block move must refuse rather than carry the fabrication into the
    newly-blessed trailing span."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(
                        atom="text",
                        address="el=1.1.1",
                        body=f"2009 Pontiac G8 V8-6.0L: {_VERBATIM_CRUMB}",
                    ),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "vehicle-name prefix" in (report.hold or "")


def test_a_partial_label_chain_is_held(tmp_path):
    """The artifact declares 3 labels; the body chains only 2 — refusing to guess the rest
    rather than treating a truncated trail as verbatim."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(
                        atom="text",
                        address="el=1.1.1",
                        body="Vehicle > Technical Service Bulletins",
                    ),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "partial trail" in (report.hold or "")


def test_trailing_residue_after_the_full_chain_is_held(tmp_path):
    """All 3 labels chain, but the line keeps going afterward — refusing to guess whether the
    tail belongs to the breadcrumb."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(
                        atom="text",
                        address="el=1.1.1",
                        body=f"{_VERBATIM_CRUMB} (continued)",
                    ),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "follows the crumb trail" in (report.hold or "")


def test_two_matching_segments_is_ambiguous_and_held(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            Segment(atom="text", address="el=1.1", body=_VERBATIM_CRUMB),
            Segment(atom="text", address="el=1.2", body=_VERBATIM_CRUMB),
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "ambiguous" in (report.hold or "")


def test_a_lone_child_span_is_held_rather_than_left_empty(tmp_path):
    """The crumb is the ONLY child of its span — removing it would leave a form with nothing
    to govern, which is a question for a human, not a mechanical rewrite (mirrors
    `reseat.py`'s guard for the same situation)."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[Segment(atom="text", address="el=1.1", body=_VERBATIM_CRUMB)],
            )
        ],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "no children" in (report.hold or "")


def test_no_resident_artifact_is_held(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[
                    Segment(atom="text", address="el=1.1.1", body=_VERBATIM_CRUMB),
                    Segment(atom="text", address="el=1.1.2", body="- [Link](https://x/a)"),
                ],
            )
        ],
        with_artifact=False,
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "no resident artifact" in (report.hold or "")


# ---------- the skips (not this migration's population) ---------- #


def test_a_different_origin_is_skipped(tmp_path):
    root, rf = _record(
        tmp_path,
        [Segment(atom="text", address="el=1.1", body=_VERBATIM_CRUMB)],
        origin_host="example.com",
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert report.skipped == f"not a {HOST} record"


def test_fewer_than_two_crumb_labels_is_skipped(tmp_path):
    root, rf = _record(
        tmp_path,
        [Segment(atom="text", address="el=1.1", body="Vehicle")],
        crumb_html='<div class="article-breadcrumb"><a href="#/vehicle/1">Vehicle</a></div>',
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert "fewer than 2" in (report.skipped or "")


def test_no_breadcrumb_rendered_is_skipped(tmp_path):
    """The 5,715-population analog: the artifact carries a real breadcrumb but the record
    renders it nowhere — out of scope (needs rendering from the artifact, not a move)."""
    root, rf = _record(
        tmp_path,
        [Segment(atom="text", address="el=1.1", body="Some unrelated content, no crumb here.")],
    )
    report = home_crumb.home_crumb_record(rf, root)
    assert report.changed is False
    assert report.skipped == "no breadcrumb line rendered in the body"
