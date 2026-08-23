"""The `index` shaper (#164, spec §7.8, §12.5.0) — my.alldata.com's category/link-list
template, authored deterministically from the artifact DOM.

Covers the three renderings the template decomposes into (the `h3.repair-page-title` byte-mark,
the linked entry list at the `div.itype-container` run, the verbatim breadcrumb in a trailing
`form/nav` span), the banner dedup, the template guard, and — the acceptance check the ticket
turns on — that `check_fidelity` (#159) passes on the shaper's own output.
"""

from __future__ import annotations

import frontmatter
import pytest
from bs4 import BeautifulSoup

from corpus import hashing, paths, recordbuild, records, schemas, segments
from corpus.fidelity import check_fidelity
from corpus.shape import alldata_index, get_shaper, shape_record
from corpus.store import LocalArtifactStore
from corpus.transforms.html import EL_PARSER_ID, total_element_count

HOST = "my.alldata.com"

_OVERLAY = """\
applies_to:
  host_pattern: my\\.alldata\\.com
form:
  - match: '/itype/13/isSelfReferenceLink'
    id: index
regions:
  - role: breadcrumb-component
    selector: ad-repair-breadcrumb
    renders: framing
  - role: itype
    selector: ad-repair-itype
    renders: subject
"""


def _page(entries: list[tuple[str, str]], *, title: str = "Technical Service Bulletins") -> str:
    """One index page in the shape all 136 queue records present."""
    crumbs = (
        '<li><a href="#/vehicle/46076"><span class="p-menuitem-text">Vehicle</span></a>'
        '<li><a href="#/vehicle/46076/component/8"><span class="p-menuitem-text">Engine</span></a>'
        f'<li><a><span class="p-menuitem-text">{title}</span></a>'
    )
    items = "".join(
        f'<div class="itype-container"><a href="{href}">{label}</a></div>'
        for label, href in entries
    )
    return (
        "<html><body><ad-repair-itype><div class='view-content'>"
        f'<h3 class="repair-page-title">{title}</h3>'
        f'<ad-repair-breadcrumb><div class="breadcrumb-container"><ol>{crumbs}</ol></div>'
        "</ad-repair-breadcrumb>"
        f'<div class="content"><div class="page-header-banner">{title}</div>{items}</div>'
        "</div></ad-repair-itype></body></html>"
    )


def _record(tmp_path, html: str, *, uri_itype: str = "13"):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    overlay_dir = root / "schema" / "origin" / "web"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / f"{HOST}.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()

    src = root / "page.html"
    src.write_text(html, encoding="utf-8")
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(
        post,
        mime="text/html",
        fields={
            "addressing": {
                "parser": EL_PARSER_ID,
                "elements": total_element_count(BeautifulSoup(html, EL_PARSER_ID)),
            }
        },
    )
    records.append_origin_block(
        post,
        uri=f"https://{HOST}/repair/#/vehicle/46076/component/421/itype/{uri_itype}/"
        f"isSelfReferenceLink/false",
        snapshot="2026-01-01T00:00:00Z",
        schema_id=HOST,
    )
    records.dump(post, paths.record_path(root, rid))
    return post, root


_ENTRIES = [
    ("All Technical Service Bulletins", "#/vehicle/46076/component/421/itype/100/tsbs/x"),
    ("Customer Interest Bulletins", "#/vehicle/46076/component/421/itype/109/x"),
    ("Repair Tips", "#/vehicle/46076/component/421/itype/110/x"),
]


def _shape(tmp_path, html: str):
    post, root = _record(tmp_path, html)
    assert shape_record(post, root) is True
    return post, root, segments.iter_blocks(post.content or "")


def test_the_shaper_is_registered_on_the_form_id():
    assert get_shaper("index") is alldata_index.shape_alldata_index


def test_the_title_becomes_a_structural_byte_mark(tmp_path):
    """#159's missing-h3 class, closed mechanically: the source's own declared boundary is a
    byte-mark carrying its verbatim text (§4.3.2.3/§12.32), not prose and not nothing."""
    _post, _root, blocks = _shape(tmp_path, _page(_ENTRIES))
    index = blocks[0]
    assert index.form == "index"
    mark = index.segments[0]
    assert mark.is_structural and mark.level == 3
    assert mark.body == "Technical Service Bulletins"
    assert mark.address == "el=1.1.1"


def test_the_entries_render_as_a_linked_list_at_the_container_run(tmp_path):
    _post, _root, blocks = _shape(tmp_path, _page(_ENTRIES))
    entries = blocks[0].segments[1]
    assert entries.atom == "text"
    assert entries.address == "el=1.1.3.[2-4]"
    assert entries.body.splitlines() == [
        "- [All Technical Service Bulletins](#/vehicle/46076/component/421/itype/100/tsbs/x)",
        "- [Customer Interest Bulletins](#/vehicle/46076/component/421/itype/109/x)",
        "- [Repair Tips](#/vehicle/46076/component/421/itype/110/x)",
    ]


def test_the_banner_is_not_rendered_twice(tmp_path):
    """`div.page-header-banner` carries the title again on 136/136 records. The addressed run
    opens at the FIRST itype-container, so the banner's own address is never claimed and its
    duplicate of the title never enters the record — the title arrives once, as the mark."""
    _post, _root, blocks = _shape(tmp_path, _page(_ENTRIES))
    addressed = {s.address for s in segments.leaf_segments(blocks)}
    assert "el=1.1.3.1" not in addressed  # the banner
    assert blocks[0].segments[1].address == "el=1.1.3.[2-4]"


def test_the_breadcrumb_is_verbatim_in_a_trailing_nav_span(tmp_path):
    """#89's law: the framing takes ONE trailing `form/nav` span, the labels exactly as they
    read, the linkless leaf (this page) plain."""
    _post, _root, blocks = _shape(tmp_path, _page(_ENTRIES))
    nav = blocks[-1]
    assert nav.form == "nav" and len(blocks) == 2
    crumb = nav.segments[0]
    assert crumb.address == "el=1.1.2"
    assert crumb.body == (
        "[Vehicle](#/vehicle/46076) > [Engine](#/vehicle/46076/component/8) > "
        "Technical Service Bulletins"
    )


def test_the_shaped_record_passes_the_fidelity_gate(tmp_path):
    """The ticket's acceptance check: a mechanical rendering whose addresses and text disagree
    is exactly what #159 measures, so the shaper must satisfy it on its own output."""
    post, root, blocks = _shape(tmp_path, _page(_ENTRIES))
    html = (root / "page.html").read_text(encoding="utf-8")
    result = check_fidelity(
        html, blocks, records.el_addressing(post), schemas.origin_regions(root, HOST)
    )
    assert result["pass"] is True
    assert result["misplaced"] == 0 and result["dropped"] == 0 and result["unresolvable"] == 0


def test_a_single_entry_takes_a_point_address_not_a_range(tmp_path):
    """§6.1.1: a single child IS its own point path — `[n-n]` is not a legal range."""
    _post, _root, blocks = _shape(tmp_path, _page(_ENTRIES[:1]))
    assert blocks[0].segments[1].address == "el=1.1.3.2"


def test_a_page_that_is_not_the_template_is_refused(tmp_path):
    """Authoring a plausible rendering over an unrecognised page is the fabrication the
    fidelity gate exists to catch — the shaper refuses instead."""
    html = (
        "<html><body><ad-repair-itype><div class='other'>Nothing here</div>"
        "</ad-repair-itype></body></html>"
    )
    post, root = _record(tmp_path, html)
    with pytest.raises(alldata_index.TemplateMismatch, match="view-content"):
        shape_record(post, root)


def test_a_stamp_attesting_a_different_tree_is_refused(tmp_path):
    """Every address the shaper writes is a walk over the parsed tree; a stamp that disagrees
    means those addresses would name other elements entirely (§6.1.1)."""
    post, root = _record(tmp_path, _page(_ENTRIES))
    records.set_artifact_block(
        post, mime="text/html", fields={"addressing": {"parser": EL_PARSER_ID, "elements": 999}}
    )
    with pytest.raises(alldata_index.TemplateMismatch, match="element-count mismatch"):
        shape_record(post, root)


def test_an_unstamped_record_is_refused(tmp_path):
    post, root = _record(tmp_path, _page(_ENTRIES))
    records.set_artifact_block(post, mime="text/html", fields={})
    with pytest.raises(alldata_index.TemplateMismatch, match="addressing"):
        shape_record(post, root)


def test_a_record_the_overlay_does_not_route_to_index_is_not_shaped(tmp_path):
    """`shape_record` dispatches on the overlay's own route rules — an article URI matches no
    `index` rule, so this shaper never sees it."""
    post, root = _record(tmp_path, _page(_ENTRIES), uri_itype="105")
    assert shape_record(post, root) is False


def test_the_build_ops_are_the_shapers_only_surface(tmp_path):
    """The shaper populates a Build through the recordbuild ops and nothing else — the same
    contract `contact_card` honours, which is what lets `shape_record` own emit + touch."""
    post, root = _record(tmp_path, _page(_ENTRIES))
    build = recordbuild.begin_from_post(post, root)
    alldata_index.shape_alldata_index(build, post, root, {})
    assert [type(b).__name__ for b in build.blocks] == ["Section", "Section"]
    assert post.content == ""  # untouched until `finish`


def test_an_asserted_index_section_governs_when_no_route_matches(tmp_path):
    """§7.8 precedence (b): a bare-itype index page's URL shape cannot safely declare a
    form — the same route covers both a list and a single-entry article jump (#164) — so
    the record's own asserted first section is what licenses the shaper."""
    post, root = _record(tmp_path, _page(_ENTRIES), uri_itype="104")
    post.content = (
        "<!--section index-->\n\n<!--segment text\naddress: el=1\n-->\n\nstale rendering\n"
    )
    assert shape_record(post, root) is True
    blocks = segments.iter_blocks(post.content or "")
    sections = [b for b in blocks if isinstance(b, segments.Section)]
    assert [s.form for s in sections] == ["index", "nav"]


def test_a_formless_unrouted_record_is_still_not_shaped(tmp_path):
    """The asserted-form fallback needs an actual assertion — a record with no route AND
    no form section stays unshaped, exactly as before the widening."""
    post, root = _record(tmp_path, _page(_ENTRIES), uri_itype="105")
    assert post.content == ""
    assert shape_record(post, root) is False


def test_reshape_accepts_an_asserted_form_record(tmp_path):
    """`reshape_record`'s gate admits the asserted-form population the same way the
    dispatch does — declared-or-asserted, never URL guesswork."""
    from corpus import reshape_index

    post, root = _record(tmp_path, _page(_ENTRIES), uri_itype="104")
    post.content = (
        "<!--section index-->\n\n<!--segment text\naddress: el=1.1.1\n-->\n\n"
        "Technical Service Bulletins\n"
    )
    rid = str(post.metadata["id"])
    record_file = paths.record_path(root, rid)
    records.dump(post, record_file)
    report = reshape_index.reshape_record(record_file, root)
    assert report.hold is None
    assert report.changed is True


def test_reshape_skips_a_record_that_neither_routes_nor_asserts(tmp_path):
    from corpus import reshape_index

    post, root = _record(tmp_path, _page(_ENTRIES), uri_itype="105")
    rid = str(post.metadata["id"])
    record_file = paths.record_path(root, rid)
    records.dump(post, record_file)
    report = reshape_index.reshape_record(record_file, root)
    assert report.skipped is not None
    assert "neither routes to nor asserts" in report.skipped


# ---------- v35: ordinal authoring ---------- #


def _ordinal_record(tmp_path, html: str, *, uri_itype: str = "13"):
    """`_record`'s ordinal-stamped counterpart — the only difference is the
    `addressing:` fields, so any drift between the two authoring paths shows up as a
    real test failure rather than a fixture difference."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    overlay_dir = root / "schema" / "origin" / "web"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / f"{HOST}.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()

    src = root / "page.html"
    src.write_text(html, encoding="utf-8")
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(
        post,
        mime="text/html",
        fields={
            "addressing": {
                "parser": EL_PARSER_ID,
                "elements": total_element_count(BeautifulSoup(html, EL_PARSER_ID)),
                "scheme": "ordinal",
            }
        },
    )
    records.append_origin_block(
        post,
        uri=f"https://{HOST}/repair/#/vehicle/46076/component/421/itype/{uri_itype}/"
        f"isSelfReferenceLink/false",
        snapshot="2026-01-01T00:00:00Z",
        schema_id=HOST,
    )
    records.dump(post, paths.record_path(root, rid))
    return post, root


def _shape_ordinal(tmp_path, html: str):
    post, root = _ordinal_record(tmp_path, html)
    assert shape_record(post, root) is True
    return post, root, segments.iter_blocks(post.content or "")


def test_ordinal_title_is_a_structural_byte_mark_at_its_own_ordinal(tmp_path):
    _post, _root, blocks = _shape_ordinal(tmp_path, _page(_ENTRIES))
    index = blocks[0]
    mark = index.segments[0]
    assert mark.is_structural and mark.level == 3
    assert mark.body == "Technical Service Bulletins"
    assert mark.address == "el=3"  # h3, verified against the raw tree (see module note)


def test_ordinal_entries_take_the_sibling_range_over_their_own_ordinals(tmp_path):
    """The sibling-position-vs-ordinal-adjacency distinction, live: the three
    itype-containers sit at ordinals 18, 20, 22 (each carrying an `<a>` child that pushes
    the next one two ahead) — not 18, 19, 20 — yet they ARE a contiguous sibling run of
    `div.content`, so the range is `el=[18-22]`, not refused as non-contiguous."""
    _post, _root, blocks = _shape_ordinal(tmp_path, _page(_ENTRIES))
    entries = blocks[0].segments[1]
    assert entries.address == "el=[18-22]"
    assert entries.body.splitlines() == [
        "- [All Technical Service Bulletins](#/vehicle/46076/component/421/itype/100/tsbs/x)",
        "- [Customer Interest Bulletins](#/vehicle/46076/component/421/itype/109/x)",
        "- [Repair Tips](#/vehicle/46076/component/421/itype/110/x)",
    ]


def test_ordinal_single_entry_takes_a_point_not_a_range(tmp_path):
    _post, _root, blocks = _shape_ordinal(tmp_path, _page(_ENTRIES[:1]))
    assert blocks[0].segments[1].address == "el=18"


def test_ordinal_breadcrumb_is_verbatim_in_a_trailing_nav_span(tmp_path):
    _post, _root, blocks = _shape_ordinal(tmp_path, _page(_ENTRIES))
    nav = blocks[-1]
    assert nav.form == "nav"
    crumb = nav.segments[0]
    assert crumb.address == "el=4"
    assert crumb.body == (
        "[Vehicle](#/vehicle/46076) > [Engine](#/vehicle/46076/component/8) > "
        "Technical Service Bulletins"
    )


def test_ordinal_shaped_record_passes_the_fidelity_gate(tmp_path):
    post, root, blocks = _shape_ordinal(tmp_path, _page(_ENTRIES))
    html = (root / "page.html").read_text(encoding="utf-8")
    result = check_fidelity(
        html, blocks, records.el_addressing(post), schemas.origin_regions(root, HOST)
    )
    assert result["pass"] is True
    assert result["misplaced"] == 0 and result["dropped"] == 0 and result["unresolvable"] == 0
