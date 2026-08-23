"""ATH-CORPUS v35 — the ordinal return (spec §6.1.1, CHANGELOG v35).

Pins the total document-order ordinal address space end to end: the grammar, the shared
pre-order walk, the sibling-range constraint, the resolver's per-record grammar dispatch
(now three generations sharing the bare-integer spelling), the tree-backed section
envelope, the drafter's ordinal emission + `scheme: ordinal` stamp, the
`address-el-range-invalid` lint, and the ledger's conservative numeric fallback where no
parse is reachable.

Does not touch `test_el_path_36.py` — the frozen dotted branch's own suite.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup

from corpus import functional_uri as furi
from corpus import lint, paths, records, schemas, segments
from corpus.segments import Segment
from corpus.store import LocalArtifactStore
from corpus.transforms import NotMaterializable
from corpus.transforms import html as thtml

# ---------- grammar ---------- #


def test_el_ordinal_grammar_round_trips_and_rejects():
    p = furi.parse_el_ordinal("7")
    assert p.point == 7 and p.sibling_range is None and p.is_point
    r = furi.parse_el_ordinal("[12-19]")
    assert r.point is None and r.sibling_range == (12, 19) and not r.is_point
    assert furi.format_el_ordinal(p) == "7"
    assert furi.format_el_ordinal(r) == "[12-19]"
    # One spelling per address, forever: the space is permanent.
    for bad in ("", "0", "07", "[9-2]", "[5-5]", "[07-19]", "a", "[1-2", "1-2]"):
        with pytest.raises(ValueError):
            furi.parse_el_ordinal(bad)


def test_el_ordinal_flat_range_gets_the_retired_form_message():
    with pytest.raises(ValueError, match=r"retired 3\.5 form"):
        furi.parse_el_ordinal("7-19")


def test_el_ordinal_dotted_value_points_at_the_v35_remap():
    with pytest.raises(ValueError, match=r"v35 remap"):
        furi.parse_el_ordinal("1.3.2")


def test_el_ordinal_sort_key_is_numeric():
    P = furi.parse_el_ordinal
    values = ["10", "9", "[2-3]"]
    ordered = sorted(values, key=lambda v: furi.el_ordinal_sort_key(P(v)))
    assert ordered == ["[2-3]", "9", "10"]


# ---------- the conservative numeric proxy (no parse access) ---------- #


def test_ordinal_bounds_and_overlap_and_contains():
    P = furi.parse_el_ordinal
    assert furi.ordinal_bounds(P("7")) == (7, 7)
    assert furi.ordinal_bounds(P("[12-19]")) == (12, 19)
    # Overlap: a point equals a point; a range's bounds are its own literal numbers.
    assert furi.ordinal_overlaps(P("7"), P("7"))
    assert not furi.ordinal_overlaps(P("7"), P("8"))
    assert furi.ordinal_overlaps(P("14"), P("[12-19]"))
    assert not furi.ordinal_overlaps(P("20"), P("[12-19]"))
    # Containment is directed and the same conservative proxy.
    assert furi.ordinal_contains(P("[12-19]"), P("14"))
    assert not furi.ordinal_contains(P("14"), P("[12-19]"))
    assert not furi.ordinal_contains(P("[12-19]"), P("25"))


# ---------- the shared pre-order walk ---------- #

_DOC = (
    "<html><head><title>t</title></head><body>"
    "<div><p>a</p><p>b</p></div>"
    "<ul><li>x</li></ul>"
    "</body></html>"
)


def test_iter_elements_preorder_excludes_root_and_is_document_order():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    names = [t.name for t in thtml.iter_elements_preorder(root)]
    assert names == ["div", "p", "p", "ul", "li"]  # div(1) p(2) p(3) ul(4) li(5)
    assert root not in thtml.iter_elements_preorder(root)  # the root has no ordinal


def test_element_ordinal_and_resolve_ordinal_are_inverse():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    for tag in thtml.iter_elements_preorder(root):
        n = thtml.element_ordinal(tag, root)
        assert n is not None
        assert thtml.resolve_ordinal(root, n) is tag
    # The root itself has no ordinal — a whole-transport claim is the ABSENT address.
    assert thtml.element_ordinal(root, root) is None
    # A <head> element is outside the body-rooted space.
    title = soup.find("title")
    assert thtml.element_ordinal(title, root) is None
    # `element_ordinals` (the one-walk batch form) agrees with the per-call version.
    batch = thtml.element_ordinals(root)
    for tag in thtml.iter_elements_preorder(root):
        assert batch[id(tag)] == thtml.element_ordinal(tag, root)


def test_resolve_ordinal_bounds_name_the_walk_length():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    with pytest.raises(ValueError, match="yields 5 elements"):
        thtml.resolve_ordinal(root, 6)
    with pytest.raises(ValueError, match="yields 5 elements"):
        thtml.resolve_ordinal(root, 0)


def test_ordinal_interval_is_the_subtree_span():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    div = soup.find("div")
    ul = soup.find("ul")
    # div(1) covers itself + its two <p> children: ordinals 1..3.
    assert thtml.ordinal_interval(div, root) == (1, 3)
    # ul(4) covers itself + <li>: ordinals 4..5.
    assert thtml.ordinal_interval(ul, root) == (4, 5)
    # A leaf's interval is itself alone.
    assert thtml.ordinal_interval(soup.find("li"), root) == (5, 5)
    assert thtml.ordinal_interval(root, root) is None  # not under itself


# ---------- richer tree for sibling / envelope tests ---------- #
#
# 1 div#root
#   2 section#a        (covers 2-4)
#     3 p (A1)
#     4 p (A2)
#   5 section#b         (covers 5-6)
#     6 p (B1)
#   7 section#c         (covers 7-10)
#     8 p (C1)
#     9 p (C2)
#     10 p (C3)
# 11 footer

_TREE_DOC = (
    "<html><body>"
    '<div id="root">'
    '<section id="a"><p>A1</p><p>A2</p></section>'
    '<section id="b"><p>B1</p></section>'
    '<section id="c"><p>C1</p><p>C2</p><p>C3</p></section>'
    "</div>"
    "<footer>F</footer>"
    "</body></html>"
)


def _tree_root() -> tuple[BeautifulSoup, object]:
    soup = BeautifulSoup(_TREE_DOC, "html.parser")
    return soup, thtml.path_root(soup)


def test_ordinals_are_siblings_valid_run():
    _soup, root = _tree_root()
    # p(A1)=3, p(A2)=4 — both children of section#a.
    assert thtml.ordinals_are_siblings(root, 3, 4)
    # section#a=2, section#b=5, section#c=7 — all children of div#root.
    assert thtml.ordinals_are_siblings(root, 2, 5)
    assert thtml.ordinals_are_siblings(root, 5, 7)


def test_ordinals_are_siblings_rejects_non_siblings_same_depth():
    _soup, root = _tree_root()
    # p(A1)=3 (under section#a) and p(B1)=6 (under section#b) — same depth, different parent.
    assert not thtml.ordinals_are_siblings(root, 3, 6)


def test_ordinals_are_siblings_rejects_different_depths():
    _soup, root = _tree_root()
    # section#a=2 (depth 2) and p(A1)=3 (depth 3, section#a's own child).
    assert not thtml.ordinals_are_siblings(root, 2, 3)


def test_ordinals_are_siblings_bounds_checks_first():
    _soup, root = _tree_root()
    with pytest.raises(ValueError, match="out of range"):
        thtml.ordinals_are_siblings(root, 3, 999)


# ---------- three grammar generations, one spelling ---------- #


def test_extract_el_same_spelling_three_grammars():
    """`el=2` on `_DOC` names three different elements depending ONLY on the record's
    stamp — never the value. Legacy: the 2nd WHITELISTED element (p "b"). Dotted (3.6):
    body's 2nd direct child (<ul>). Ordinal (v35): the 2nd element in document-order
    pre-order (p "a"). Sniffing the value would silently pick the wrong one — the exact
    failure all three generations of this dispatch exist to end."""
    soup = BeautifulSoup(_DOC, "html.parser")
    legacy = thtml.extract_el(soup, "2", {})
    assert legacy.tag.name == "p" and legacy.tag.get_text() == "b"

    dotted = thtml.extract_el(
        soup, "2", {"el_addressing": {"parser": "html.parser", "elements": 9}}
    )
    assert dotted.tag.name == "ul"

    ordinal = thtml.extract_el(
        soup, "2",
        {"el_addressing": {"parser": "html.parser", "elements": 9, "scheme": "ordinal"}},
    )
    assert ordinal.tag.name == "p" and ordinal.tag.get_text() == "a"


def test_extract_el_ordinal_stamped_checks_the_two_attested_facts_first():
    soup = BeautifulSoup(_DOC, "html.parser")
    with pytest.raises(ValueError, match="parser"):
        thtml.extract_el(
            soup, "1",
            {"el_addressing": {"parser": "lxml", "elements": 5, "scheme": "ordinal"}},
        )
    with pytest.raises(ValueError, match="element-count mismatch"):
        thtml.extract_el(
            soup, "1",
            {"el_addressing": {"parser": "html.parser", "elements": 999, "scheme": "ordinal"}},
        )


def test_extract_el_ordinal_sibling_range_bounds_then_sibling_check_then_not_materializable():
    soup, _root = _tree_root()
    ctx = {
        "el_addressing": {
            "parser": "html.parser",
            "elements": thtml.total_element_count(soup),
            "scheme": "ordinal",
        }
    }
    # Out-of-bounds endpoint: a defect, reported as one — before siblinghood is even asked.
    with pytest.raises(ValueError, match="out of range"):
        thtml.extract_el(soup, "[3-999]", ctx)
    # In-bounds but not siblings: an INVALID address (not a materialization gap).
    with pytest.raises(ValueError, match="not siblings"):
        thtml.extract_el(soup, "[3-6]", ctx)  # p(A1) under section#a, p(B1) under section#b
    # In-bounds, real siblings: a valid envelope with no single byte surface.
    with pytest.raises(NotMaterializable):
        thtml.extract_el(soup, "[2-5]", ctx)  # section#a, section#b — siblings under div#root


# ---------- envelope derivation: the tree algebra ---------- #


def _segs(*addrs: str) -> list[Segment]:
    return [Segment(atom="text", address=a) for a in addrs]


def test_el_ordinal_envelope_single_survivor():
    _soup, root = _tree_root()
    # section#a (el=2) contains p A1 (el=3): the wider claim survives alone.
    assert segments.section_address(_segs("el=2", "el=3"), el_ordinal_root=root) == "el=2"


def test_el_ordinal_envelope_contiguous_sibling_run_of_leaves():
    _soup, root = _tree_root()
    # p(A1)=3, p(A2)=4 — contiguous children of section#a.
    assert segments.section_address(_segs("el=3", "el=4"), el_ordinal_root=root) == "el=[3-4]"


def test_el_ordinal_envelope_sibling_positions_not_ordinal_adjacency():
    """The distinction the ordinal space's own doc names explicitly: section#b (el=5) and
    section#c (el=7) are CONSECUTIVE SIBLINGS of div#root (positions 1 and 2 among its
    children) even though their ORDINALS are not adjacent integers — ordinal 6 belongs to
    section#b's own child, not to any element "between" them. The envelope still collapses
    to the sibling-range form, spelled with the two claims' own ordinals."""
    _soup, root = _tree_root()
    assert segments.section_address(_segs("el=5", "el=7"), el_ordinal_root=root) == "el=[5-7]"


def test_el_ordinal_envelope_non_sibling_takes_the_lowest_common_container():
    _soup, root = _tree_root()
    # p(A2)=4 under section#a, p(B1)=6 under section#b: not siblings, no contiguous
    # collapse applies — "address up, never across" takes the LCA's own ordinal.
    assert segments.section_address(_segs("el=4", "el=6"), el_ordinal_root=root) == "el=1"


def test_el_ordinal_envelope_falls_back_when_no_parse_is_threaded():
    """No `el_ordinal_root` given (the artifact is unreachable to this caller): rather
    than guess at the ordinal algebra, the derivation falls through to the legacy min-max
    int-span reading — exactly what an unstamped/no-soup caller has always had. A refactor
    that started silently treating bare ordinals as the ordinal grammar without a parse
    would change this value, which is the point of pinning it."""
    assert segments.section_address(_segs("el=3", "el=4")) == "el=3-4"


def test_el_ordinal_envelope_malformed_value_is_not_derivable():
    _soup, root = _tree_root()
    assert segments.section_address(_segs("el=3", "el=1.2"), el_ordinal_root=root) is None


# ---------- the drafter: ordinal emission + the scheme stamp ---------- #


def test_html_drafter_emits_ordinal_addresses_and_scheme_stamp(tmp_path, run_drafter):
    from corpus import draft

    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()

    p = tmp_path / "glossary.html"
    p.write_text(
        "<html><head><title>Glossary</title></head><body>"
        '<h1 id="t">Glossary</h1>'
        "<p>Intro.</p>"
        '<dl id="terms"><dt>Corpus</dt><dd>A content-addressed archive.</dd></dl>'
        "<p>Outro.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    drafter = draft.get_drafter("text/text_html")
    result, segs = run_drafter(drafter, p, record_id="0" * 64)

    stamp = (result.get("fields") or {})["addressing"]
    assert stamp["scheme"] == "ordinal"
    assert stamp["parser"] == "html.parser"

    # h1(1), p(2), dl(3), dt(4), dd(5), p(6) — the wrapper claims the body's direct
    # children by ORDINAL, not by sibling position: the trailing <p> is 6, not 4, because
    # <dl>'s own children occupy 4 and 5 first.
    assert len(segs) == 1
    assert segs[0].address == ["el=1", "el=2", "el=3", "el=6"]

    body = BeautifulSoup(segs[0].body, "html.parser")
    assert body.find("dl").get("data-el") == "3"
    assert body.find_all("p")[-1].get("data-el") == "6"

    # And the emitted addresses actually resolve, on the raw artifact, to what they claim.
    raw_soup = BeautifulSoup(p.read_bytes(), "html.parser")
    raw_root = thtml.path_root(raw_soup)
    assert thtml.resolve_ordinal(raw_root, 3).name == "dl"
    assert thtml.resolve_ordinal(raw_root, 6).name == "p"


# ---------- lint: address-el-range-invalid ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ordinal_record(tmp_path: Path, range_value: str) -> tuple[Path, Path]:
    """An ordinal-stamped record over `_TREE_DOC`, one segment carrying `range_value` as
    its `el=` address — for the lint rule to judge."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "tree.html"
    src.write_text(_TREE_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    soup = BeautifulSoup(_TREE_DOC, "html.parser")
    total = thtml.total_element_count(soup)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": total, "scheme": "ordinal"}},
    )
    records.append_origin_block(post, uri="https://x.test/tree", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([Segment(atom="text", address=range_value, body="stub")])
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf


def test_address_el_range_invalid_fires_on_non_siblings(tmp_path):
    # el=3 (p A1, under section#a) .. el=6 (p B1, under section#b): in bounds, not siblings.
    root, rf = _ordinal_record(tmp_path, "el=[3-6]")
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    findings = [
        f for f in lint.lint(post, blocks, root) if f.rule_id == "address-el-range-invalid"
    ]
    assert findings and "not siblings" in findings[0].message


def test_address_el_range_invalid_fires_on_out_of_bounds(tmp_path):
    root, rf = _ordinal_record(tmp_path, "el=[2-999]")
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    findings = [
        f for f in lint.lint(post, blocks, root) if f.rule_id == "address-el-range-invalid"
    ]
    assert findings and "exceeds the record's attested" in findings[0].message


def test_address_el_range_invalid_silent_on_a_valid_sibling_range(tmp_path):
    # el=2 (section#a) .. el=5 (section#b): real siblings, in bounds.
    root, rf = _ordinal_record(tmp_path, "el=[2-5]")
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    findings = [
        f for f in lint.lint(post, blocks, root) if f.rule_id == "address-el-range-invalid"
    ]
    assert findings == []


def test_address_el_range_invalid_scoped_to_ordinal_records_only():
    """A dotted-stamped (schemeless) record's `el=` ranges speak a different grammar
    entirely and are never judged by this rule — `parse_el_ordinal` would misread them."""
    post = frontmatter.Post("")
    post.metadata.update({"id": "0" * 64})
    records.set_artifact_block(
        post, mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": 5}},  # no scheme key
    )
    blocks = segments.iter_blocks(
        segments.emit([Segment(atom="text", address="el=1.[2-9]", body="x")])
    )
    from corpus.lint import _rule_address_el_range_grammar

    assert list(_rule_address_el_range_grammar(post, blocks, Path("/nonexistent"))) == []


# ---------- verify: the conservative numeric fallback (no parse access) ---------- #


def test_ledger_verify_ordinal_scoping_exact_and_range(tmp_path):
    from corpus import hashing
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import load_record_content, scoped_text

    root = _make_corpus(tmp_path)
    src = root / "tree.html"
    src.write_text(_TREE_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    soup = BeautifulSoup(_TREE_DOC, "html.parser")
    total = thtml.total_element_count(soup)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": total, "scheme": "ordinal"}},
    )
    records.append_origin_block(post, uri="https://x.test/tree", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([Segment(atom="text", address="el=[5-7]", body="B1 C1 C2 C3")])
    records.dump(post, paths.record_path(root, rid))

    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    content = load_record_content(join, rid)
    assert content is not None and content.el_scheme == "ordinal"

    # A citation naming a point ordinal the stored range's literal bounds cover: ok.
    text, status = scoped_text(content, [("el", "6")])
    assert status == "ok" and text == "B1 C1 C2 C3"
    # A citation naming ground the stored range never claims: bad-anchor, not silently ok.
    text, status = scoped_text(content, [("el", "20")])
    assert status == "bad-anchor"
