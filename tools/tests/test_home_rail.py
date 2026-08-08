"""The §89 rail restoration — `corpus.home_rail`.

What these pin: the rail renders as markdown links, grouped by the source's own addresses, in
the source's own order, into a TRAILING `<!--section nav-->` — joining the crumb's span where
`corpus home-crumb` already built one (re-spelling it to `nav` if it is still the pre-#89
`index` spelling), appending a new one after a formed span (including, since `form/nav` ended
the merge overload with `form/index`, a record whose only top-level block IS a `form/index`
span — the population this module used to refuse), and standing alone on a formless record;
self-edges are dropped and a record whose whole rail is self-edges is REFUSED rather than left
with an empty span; the `relation` blocks are left exactly where they are (`corpus drop-retired`
owns their removal); and both the neutrality gate and the positive landing check refuse a
rewrite rather than write one — the landing check because a prior migration reported 641
merges while writing nothing and its neutrality gate passed.
"""

from __future__ import annotations

import frontmatter
import pytest

from corpus import hashing, home_rail, paths, records, schemas, segments
from corpus.segments import Section, Segment

HOST = "my.alldata.com"

_OVERLAY_YAML = """\
regions:
  - role: breadcrumb-component
    selector: ad-repair-breadcrumb
    renders: framing
  - role: related-information
    selector: ad-repair-related-information
    renders: framing
  - role: article
    selector: ad-repair-article
    renders: subject
"""

#: The record's own route — every self-edge test points an entry back at it.
_OWN_URI = f"https://{HOST}/repair/#/vehicle/46076/component/8/itype/16/isSelfReferenceLink/false"
_OWN_ROUTE = "#/vehicle/46076/component/8/itype/16/isSelfReferenceLink/false"

_RAIL_ADDR_A = "el=1.2.2.1.2.2.1.3.2.1.1.2.1.2.2"
_RAIL_ADDR_B = "el=1.2.2.1.2.2.1.3.2.1.1.2.1.3.2.2"

#: Two address groups, deliberately NOT in address order — the rail is a nested accordion and
#: the migration must keep the SOURCE's order, both of groups and of entries within one.
_RAIL = [
    (_RAIL_ADDR_B, "Repair Tips", "#/vehicle/46076/component/8/itype/110"),
    (_RAIL_ADDR_A, "All Technical Service Bulletins", "#/vehicle/46076/component/8/itype/100"),
    (_RAIL_ADDR_B, "Customer Interest Bulletins", "#/vehicle/46076/component/8/itype/109"),
]


def _make_corpus(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    overlay_dir = root / "schema" / "origin" / "web"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / f"{HOST}.yaml").write_text(_OVERLAY_YAML, encoding="utf-8")
    schemas.cache_clear()
    return root


def _record(
    tmp_path,
    blocks,
    *,
    rail=_RAIL,
    origin_host: str | None = HOST,
    uris=None,
):
    """A record carrying `rail` as retired `relation/related-information` context blocks.

    No artifact is put in the store, deliberately: the rail is already lifted INTO the record,
    so this migration reads context blocks and origin blocks and never opens the bytes — which
    is why it can restore a record whose artifact is not resident."""
    root = _make_corpus(tmp_path)
    src = root / "page.html"
    src.write_text("<html><body>irrelevant</body></html>", encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post,
        mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": 140}},
    )
    if origin_host:
        records.append_origin_block(
            post,
            uri=uris if uris is not None else _OWN_URI,
            snapshot="2026-01-01T00:00:00Z",
            schema_id=origin_host,
        )
    post.content = segments.emit(blocks)
    for address, text, url in rail:
        records.append_context_block(
            post,
            namespace="relation",
            id="related-information",
            fields={"address": address, "target_text": text, "target_url": url},
        )
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf


def _article(*, entry=None):
    return Section(
        form="article",
        segments=[
            Segment(
                atom="text",
                address="el=1.2.2.1",
                entry=entry,
                body="Removal: 1. Disconnect the battery. 2. Remove the cover.",
            )
        ],
    )


def _trailing(new_text):
    blocks = segments.iter_blocks(records.loads(new_text).content)
    return blocks, blocks[-1]


# ---------- the three placement cases ---------- #


def test_append_a_new_trailing_nav_span_after_a_form_article_span(tmp_path):
    """The bulk case (3,842 records): the record ends in a formed subject span, so the rail
    takes a NEW trailing `nav` span after it. `form/article` and `form/nav` are different form
    ids, so nothing merges regardless of what either declares."""
    root, rf = _record(tmp_path, [_article()])
    report = home_rail.home_rail_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert report.counts["placement: append"] == 1
    assert report.counts["entries rendered"] == 3
    assert report.counts["addresses"] == 2

    blocks, trailing = _trailing(report.new_text)
    assert [b.form for b in blocks] == ["article", "nav"]
    assert [s.address for s in trailing.segments] == [_RAIL_ADDR_B, _RAIL_ADDR_A]


def test_join_the_existing_trailing_span_the_crumb_migration_built(tmp_path):
    """The 113 records `corpus home-crumb` already homed: a trailing BARE `nav` span on a
    record with other blocks. The rail joins it — crumb first, rail after, because the
    overlay declares `breadcrumb-component` before `related-information` and §7.2 makes
    declaration order the order framing regions take in that span. One framing span, not two."""
    crumb = Segment(
        atom="text",
        address="el=1.2.2.1.1.2.1",
        body="Vehicle > Technical Service Bulletins > Some Bulletin",
    )
    root, rf = _record(tmp_path, [_article(), Section(form="nav", segments=[crumb])])
    report = home_rail.home_rail_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert report.counts["placement: join"] == 1

    blocks, trailing = _trailing(report.new_text)
    assert [b.form for b in blocks] == ["article", "nav"]  # joined, not a second span
    assert [s.address for s in trailing.segments] == [
        "el=1.2.2.1.1.2.1",  # the crumb, first
        _RAIL_ADDR_B,
        _RAIL_ADDR_A,
    ]


def test_join_re_spells_a_legacy_index_spelled_crumb_span_to_nav(tmp_path):
    """A crumb span a PRE-#89 `corpus home-crumb` run built still carries the old
    `<!--section index-->` opener. The rail's join re-spells it to `nav` as part of the same
    write — the convergence path, gated the same as any other rewrite."""
    crumb = Segment(
        atom="text",
        address="el=1.2.2.1.1.2.1",
        body="Vehicle > Technical Service Bulletins > Some Bulletin",
    )
    root, rf = _record(tmp_path, [_article(), Section(form="index", segments=[crumb])])
    report = home_rail.home_rail_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert report.counts["placement: join"] == 1

    blocks, _ = _trailing(report.new_text)
    assert [b.form for b in blocks] == ["article", "nav"]  # re-spelled, not left as index


def test_a_formless_record_gets_the_trailing_span_as_its_only_span(tmp_path):
    """The 241 formless records: bare top-level segments, so the new `nav` span is the
    record's only one and sits after them (§4.3.2.1 admits formless segments before the first
    section opener — which is exactly the shape trailing produces)."""
    root, rf = _record(
        tmp_path,
        [Segment(atom="text", address="el=1.2.2.1", body="Some loose prose, no form.")],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert report.counts["placement: formless"] == 1

    blocks, trailing = _trailing(report.new_text)
    assert isinstance(blocks[0], Segment)
    assert isinstance(trailing, Section) and trailing.form == "nav"


# ---------- the rendering ---------- #


def test_entries_group_by_address_in_source_order_within_each_group(tmp_path):
    """One segment per ADDRESS — entries sharing one are siblings of one accordion group, and
    a segment per entry would state a structure the source does not have. Groups keep
    first-appearance order; entries keep source order within a group."""
    root, rf = _record(tmp_path, [_article()])
    report = home_rail.home_rail_record(rf, root)
    _, trailing = _trailing(report.new_text)

    bodies = {s.address: s.body.strip() for s in trailing.segments}
    assert bodies[_RAIL_ADDR_B] == (
        "- [Repair Tips](#/vehicle/46076/component/8/itype/110)\n"
        "- [Customer Interest Bulletins](#/vehicle/46076/component/8/itype/109)"
    )
    assert bodies[_RAIL_ADDR_A] == (
        "- [All Technical Service Bulletins](#/vehicle/46076/component/8/itype/100)"
    )
    # The span's envelope is DERIVED from its children, never hand-written (§6.1.1) — the
    # ordered address list, in the §6.1.1 path order the derivation puts them in, not in the
    # segments' emit order.
    assert trailing.address == [_RAIL_ADDR_A, _RAIL_ADDR_B]


def test_the_relation_blocks_are_left_exactly_where_they_are(tmp_path):
    """Additive only. `corpus drop-retired` owns the removal, and its hold releases once this
    span claims the address — two halves, each independently verifiable."""
    root, rf = _record(tmp_path, [_article()])
    report = home_rail.home_rail_record(rf, root)
    after = records.loads(report.new_text)
    assert len(home_rail.rail_blocks(after)) == 3
    assert report.new_text.count("<!--context relation/related-information") == 3


def test_no_corpus_uri_is_ever_written(tmp_path):
    """The overlay's rule: at the corpus layer records link only via URLs, and whether a
    target is captured is resolved at read time (§12.4.7)."""
    root, rf = _record(tmp_path, [_article()])
    report = home_rail.home_rail_record(rf, root)
    assert "corpus://" not in records.loads(report.new_text).content


def test_a_stored_corpus_uri_target_is_held_not_rendered(tmp_path):
    root, rf = _record(
        tmp_path,
        [_article()],
        rail=[(_RAIL_ADDR_A, "Repair Tips", "corpus://deadbeef")],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "corpus://" in (report.hold or "")


def test_idempotent_a_second_pass_is_a_clean_skip(tmp_path):
    root, rf = _record(tmp_path, [_article()])
    first = home_rail.home_rail_record(rf, root)
    assert first.changed, first.hold
    rf.write_text(first.new_text, encoding="utf-8")

    second = home_rail.home_rail_record(rf, root)
    assert second.changed is False
    assert second.skipped == "already restored — the rail sits in the trailing framing span"


# ---------- self-edges ---------- #


def test_a_self_edge_is_dropped_and_the_rest_of_the_group_survives(tmp_path):
    """"Drop any entry pointing back at this same page" — matched on the ROUTE (the fragment
    after `#`), against every uri the origin blocks carry, aliases included: the dedup fold
    writes a record's alternate names into the same list, so an entry pointing at an alias
    points at this page."""
    root, rf = _record(
        tmp_path,
        [_article()],
        rail=[
            (_RAIL_ADDR_A, "This Very Page", _OWN_ROUTE),
            (_RAIL_ADDR_A, "Repair Tips", "#/vehicle/46076/component/8/itype/110"),
        ],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.changed, report.hold
    assert report.counts["self-edges dropped"] == 1
    assert report.counts["entries rendered"] == 1

    _, trailing = _trailing(report.new_text)
    (seg,) = trailing.segments
    assert seg.body.strip() == "- [Repair Tips](#/vehicle/46076/component/8/itype/110)"


def test_a_self_edge_through_a_folded_alias_uri_is_dropped_too(tmp_path):
    alias = f"https://{HOST}/repair/#/article/46076/component/8/itype/16"
    root, rf = _record(
        tmp_path,
        [_article()],
        uris=[_OWN_URI, alias],
        rail=[
            (_RAIL_ADDR_A, "The Alias Of This Page", "#/article/46076/component/8/itype/16"),
            (_RAIL_ADDR_A, "Repair Tips", "#/vehicle/46076/component/8/itype/110"),
        ],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.changed, report.hold
    assert report.counts["self-edges dropped"] == 1


def test_a_rail_that_is_entirely_self_edges_is_refused_never_left_empty(tmp_path):
    """Two records corpus-wide. An empty framing span states something the source does not, so
    the refusal is the point: never write one."""
    root, rf = _record(
        tmp_path,
        [_article()],
        rail=[(_RAIL_ADDR_A, "This Very Page", _OWN_ROUTE)],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "self-edge" in (report.hold or "") and "empty" in (report.hold or "")


# ---------- the disarmed merge trap (#89) ---------- #


def test_a_sole_form_index_block_now_restores_a_trailing_nav_span(tmp_path):
    """584 records, every one its record's SOLE top-level block — the population this module
    used to refuse outright. Before `form/nav`, `form/index` declared no fields, so §4.3.2.1's
    equality test would have made two adjacent bare index spans ONE span on the next parse.
    `form/nav` ends the overload: appending a trailing `nav` span here never merges with the
    `index` span ahead of it, whatever fields either declares — so this now restores, the
    `relation` blocks left exactly where they are for `drop-retired` to sweep."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                description="A link index for the cooling system.",
                segments=[Segment(atom="text", address="el=1.2.2.1", body="- [Link](#/a)")],
            )
        ],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert report.counts["placement: append"] == 1

    blocks, _ = _trailing(report.new_text)
    assert [b.form for b in blocks] == ["index", "nav"]
    after = records.loads(report.new_text)
    assert len(home_rail.rail_blocks(after)) == 3


def test_a_bare_sole_form_index_block_restores_too(tmp_path):
    """The 2 records that would have merged TODAY rather than after the sweep — same
    resolution, and it does not depend on whether a distinguishing field happens to be
    present, because the new span is a different form id either way."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="index",
                segments=[Segment(atom="text", address="el=1.2.2.1", body="- [L](#/a)")],
            )
        ],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    blocks, _ = _trailing(report.new_text)
    assert [b.form for b in blocks] == ["index", "nav"]


def test_an_unparseable_rail_address_is_held(tmp_path):
    root, rf = _record(
        tmp_path,
        [_article()],
        rail=[("el=not-a-path", "Repair Tips", "#/vehicle/46076/component/8/itype/110")],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "does not parse" in (report.hold or "")


def test_a_rail_entry_missing_a_field_is_held(tmp_path):
    root, rf = _record(tmp_path, [_article()], rail=[])
    post = records.load(rf)
    records.append_context_block(
        post,
        namespace="relation",
        id="related-information",
        fields={"address": _RAIL_ADDR_A, "target_text": "Repair Tips"},  # no target_url
    )
    records.dump(post, rf)
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "missing one of" in (report.hold or "")


def test_a_partially_restored_record_is_held_not_completed(tmp_path):
    """One group already in the trailing span and one not — someone else's pass, mid-flight.
    Refusing to finish it: which half is authoritative is a question, not a rewrite."""
    root, rf = _record(tmp_path, [_article()])
    first = home_rail.home_rail_record(rf, root)
    blocks = segments.iter_blocks(records.loads(first.new_text).content)
    blocks[-1].segments = blocks[-1].segments[:1]  # keep only the first group
    post = records.loads(first.new_text)
    post.content = segments.emit(blocks)
    rf.write_text(records.dumps(post), encoding="utf-8")

    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "partial restoration" in (report.hold or "")


def test_a_record_whose_content_zone_does_not_parse_is_held(tmp_path):
    root, rf = _record(tmp_path, [_article()])
    post = records.load(rf)
    post.content = "<!--segment nonsense\naddress: el=1\n-->\n\nbody\n"
    rf.write_text(records.dumps(post), encoding="utf-8")
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "content zone does not parse" in (report.hold or "")


# ---------- the two gates ---------- #


def test_the_neutrality_gate_refuses_a_rewrite_that_raises_any_lint_rule(tmp_path):
    """The rail's address is already claimed by a content segment (§12.27 measured 6 such
    records corpus-wide). Restoring it would mint a duplicate `(opener-id, address)` pair —
    an error no rule of this module's own would have looked for, which is exactly why the gate
    diffs the WHOLE rule set rather than a predicted one."""
    root, rf = _record(
        tmp_path,
        [
            Section(
                form="article",
                segments=[
                    Segment(atom="text", address="el=1.2.2.1", body="Article prose."),
                    Segment(atom="text", address=_RAIL_ADDR_A, body="The rail's own region."),
                ],
            )
        ],
        rail=[(_RAIL_ADDR_A, "Repair Tips", "#/vehicle/46076/component/8/itype/110")],
    )
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "segment-address-duplicate" in (report.hold or "")


def test_the_landing_check_refuses_a_rewrite_that_wrote_nothing(tmp_path, monkeypatch):
    """The lesson a prior migration paid for: it reported 641 merges while writing nothing and
    its neutrality gate passed, because a rewrite that changes nothing regresses nothing. Here
    the serializer is made to drop the trailing span; every other gate is happy — the content
    zone parses, round-trips, and lints identically — and only the positive landing check
    notices that what the verb claims to have done is not in the bytes."""
    real_emit = segments.emit

    def _emit_dropping_the_new_span(blocks):
        keep = [b for b in blocks if not (isinstance(b, Section) and b.form == "nav")]
        return real_emit(keep or blocks)

    monkeypatch.setattr(home_rail.segments, "emit", _emit_dropping_the_new_span)
    root, rf = _record(tmp_path, [_article()])
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "internal:" in (report.hold or "")


def test_the_landing_check_refuses_when_a_relation_block_went_missing(tmp_path, monkeypatch):
    """The additive half staying additive is a claim, so it is checked rather than assumed."""
    root, rf = _record(tmp_path, [_article()])
    real = home_rail.rail_blocks
    calls = {"n": 0}

    def _losing_one(post):
        calls["n"] += 1
        out = real(post)
        return out[:-1] if calls["n"] > 1 else out

    monkeypatch.setattr(home_rail, "rail_blocks", _losing_one)
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "went missing" in (report.hold or "")


def test_a_record_that_is_not_dumps_stable_is_held(tmp_path):
    """The §12.28 rule: the rewrite goes through the real serializer, so a difference the
    serializer would introduce on its own must be disclosed before this migration adds one.
    Here the id is stored quoted and the serializer would unquote it — a change nobody asked
    for, riding in on a rail commit."""
    root, rf = _record(tmp_path, [_article()])
    text = rf.read_text(encoding="utf-8")
    rid = records.load(rf).metadata["id"]
    rf.write_text(text.replace(f"id: {rid}", f"id: '{rid}'", 1), encoding="utf-8")
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert "dumps-stable" in (report.hold or "")


# ---------- the skips (not this migration's population) ---------- #


def test_a_different_origin_is_skipped(tmp_path):
    root, rf = _record(tmp_path, [_article()], origin_host="example.com")
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert report.skipped == f"not a {HOST} record"


def test_a_record_with_no_rail_is_skipped(tmp_path):
    root, rf = _record(tmp_path, [_article()], rail=[])
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert report.skipped == "no related-information rail on this record"


@pytest.mark.parametrize(
    "text,url",
    [("Repair [Tips]", "#/a"), ("Repair Tips", "#/a (b)"), ("", "#/a"), ("Repair Tips", "")],
)
def test_an_unrenderable_entry_is_held_rather_than_mangled(tmp_path, text, url):
    """A markdown link that cannot be read back is a fabrication, not a formatting problem.
    The live corpus carries none of these (0 of 74,795) — the guard is why that stays true."""
    root, rf = _record(tmp_path, [_article()], rail=[(_RAIL_ADDR_A, text, url)])
    report = home_rail.home_rail_record(rf, root)
    assert report.changed is False
    assert report.hold
