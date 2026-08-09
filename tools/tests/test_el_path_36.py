"""ATH-CORPUS 3.6 — the addressing amendment (spec §6.1.1, §12.28).

Pins the total child-index path space end to end: the grammar, the shared walk, the
resolver's stamp-keyed grammar dispatch (the bare-integer ambiguity — the one silent
failure mode the migration design exists to prevent), the attest guard that keeps a
legacy record from being stamped out from under its stored integers, the path-algebra
section envelope, and the §12.28 remap engine's self-proving rewrite.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup

from corpus import derive, paths, records, remap_el, schemas, segments
from corpus import functional_uri as furi
from corpus.segments import Segment
from corpus.store import LocalArtifactStore
from corpus.transforms import NotMaterializable
from corpus.transforms import html as thtml

# ---------- grammar ---------- #


def test_el_path_grammar_round_trips_and_rejects():
    p = furi.parse_el_path("1.3.2")
    assert p.components == (1, 3, 2) and p.sibling_range is None and p.is_point
    r = furi.parse_el_path("1.3.[2-9]")
    assert r.components == (1, 3) and r.sibling_range == (2, 9) and not r.is_point
    assert furi.format_el_path(p) == "1.3.2"
    assert furi.format_el_path(r) == "1.3.[2-9]"
    # One spelling per address, forever: the space is permanent.
    for bad in ("", "0.2", "1.03", "1..2", "1.", ".1", "[2-9]", "1.[5-5]", "1.[9-2]", "a.b"):
        with pytest.raises(ValueError):
            furi.parse_el_path(bad)


def test_el_path_flat_range_gets_the_migration_message():
    with pytest.raises(ValueError, match=r"retired 3\.5 form"):
        furi.parse_el_path("1-8")


def test_el_path_containment_is_a_prefix_test():
    P = furi.parse_el_path
    assert furi.el_path_contains(P("1.3"), P("1.3.2"))
    assert furi.el_path_contains(P("1.3"), P("1.3"))  # inclusive
    assert not furi.el_path_contains(P("1.3"), P("1.30"))  # §6.1.1's named trap
    assert furi.el_path_contains(P("1.3.[2-9]"), P("1.3.2.5"))
    assert not furi.el_path_contains(P("1.3.[2-9]"), P("1.3.10"))
    assert furi.el_path_contains(P("1.3.[2-9]"), P("1.3.[3-4]"))
    assert not furi.el_path_contains(P("1.3.2"), P("1.3"))


def test_el_path_order_is_numeric_not_lexical():
    P = furi.parse_el_path
    values = ["1.10", "1.9", "1.2.1"]
    ordered = sorted(values, key=lambda v: furi.el_path_sort_key(P(v)))
    assert ordered == ["1.2.1", "1.9", "1.10"]  # a string sort would put 1.10 first


# ---------- the shared walk ---------- #

_DOC = (
    "<html><head><title>t</title></head><body>"
    "<div><p>a</p><p>b</p></div>"
    "<ul><li>x</li></ul>"
    "</body></html>"
)


def test_element_path_and_resolve_are_inverse():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    for tag in root.find_all(True):
        p = thtml.element_path(tag, root)
        assert p is not None
        assert thtml.resolve_element_path(root, furi.parse_el_path(p)) is tag
    # The root itself has no path — a whole-content claim is the addressless section.
    assert thtml.element_path(root, root) is None
    # A <head> element is outside the body-rooted space.
    title = soup.find("title")
    assert thtml.element_path(title, root) is None


def test_resolve_element_path_bounds_name_the_failing_component():
    soup = BeautifulSoup(_DOC, "html.parser")
    root = thtml.path_root(soup)
    with pytest.raises(ValueError, match="child 9"):
        thtml.resolve_element_path(root, furi.parse_el_path("1.9"))
    with pytest.raises(ValueError, match="sibling range"):
        thtml.resolve_element_path(root, furi.parse_el_path("1.[2-5]"))


# ---------- resolver dispatch: the record decides the grammar ---------- #


def test_extract_el_same_spelling_two_grammars():
    """`el=2` on this document is the first <p> under the legacy whitelist (2nd
    addressable element) but the <ul> under the path grammar (body's 2nd element
    child). The RECORD's stamp decides which — value sniffing would silently resolve
    to the wrong element, which is exactly what §12.28 forbids."""
    soup = BeautifulSoup(_DOC, "html.parser")
    legacy = thtml.extract_el(soup, "2", {})
    assert legacy.tag.name == "p"  # p(1), p(2), ul(3) in the filtered enumeration
    stamped = thtml.extract_el(
        soup, "2", {"el_addressing": {"parser": "html.parser", "elements": 9}}
    )
    assert stamped.tag.name == "ul"  # body's children: div(1), ul(2)


def test_extract_el_stamped_checks_the_two_attested_facts():
    soup = BeautifulSoup(_DOC, "html.parser")
    with pytest.raises(ValueError, match="parser"):
        thtml.extract_el(soup, "1", {"el_addressing": {"parser": "lxml", "elements": 8}})
    with pytest.raises(ValueError, match="element-count mismatch"):
        thtml.extract_el(
            soup, "1", {"el_addressing": {"parser": "html.parser", "elements": 999}}
        )


def test_extract_el_sibling_range_bounds_then_not_materializable():
    soup = BeautifulSoup(_DOC, "html.parser")
    ctx = {"el_addressing": {"parser": "html.parser", "elements": 9}}
    # In-bounds range: a real envelope, no single byte surface (the #61 order kept).
    with pytest.raises(NotMaterializable):
        thtml.extract_el(soup, "1.[1-2]", ctx)
    # Out-of-bounds range: a defect, reported as one.
    with pytest.raises(ValueError, match="element children"):
        try:
            thtml.extract_el(soup, "1.[1-9]", ctx)
        except NotMaterializable:  # pragma: no cover - wrong path
            pytest.fail("bounds must be checked before materializability")


# ---------- section envelope: the path algebra ---------- #


def test_section_address_el_path_algebra():
    def segs(*addrs):
        return [Segment(atom="text", address=a) for a in addrs]

    # Contained claims drop; a single survivor IS the envelope.
    assert segments.section_address(segs("el=1.2", "el=1.2.9"), el_paths=True) == "el=1.2"
    # Contiguous point-siblings collapse to the sibling range.
    assert (
        segments.section_address(segs("el=1.2", "el=1.3", "el=1.4"), el_paths=True)
        == "el=1.[2-4]"
    )
    # Cross-subtree stays the ordered list — there is deliberately no flat form.
    assert segments.section_address(segs("el=2.7", "el=1.2"), el_paths=True) == [
        "el=1.2",
        "el=2.7",
    ]
    # Body-level children have no parent path, so no bare range form: the list.
    assert segments.section_address(segs("el=1", "el=2"), el_paths=True) == ["el=1", "el=2"]
    # Legacy (unstamped) records keep the min-max envelope untouched.
    assert segments.section_address(segs("el=3", "el=7")) == "el=3-7"


# ---------- attest guard + remap engine, end to end ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


_LEGACY_DOC = (
    "<html><head><title>Legacy</title></head><body>"
    "<div><h1>Title</h1><p>One.</p><p>Two.</p><p>Three.</p></div>"
    "<div><p>Coda.</p></div>"
    "</body></html>"
)


def _ingest_legacy_record(tmp_path: Path) -> tuple[Path, Path, str]:
    """A record shaped like the pre-3.6 fleet: integer el= addresses (point, flat range,
    a context-block address), NO addressing stamp."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "legacy.html"
    src.write_text(_LEGACY_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x.test/legacy", snapshot="2026-01-01T00:00:00Z")
    # Legacy enumeration: h1(1), p(2), p(3), p(4), p(5).
    post.content = segments.emit([
        Segment(atom="text", address="el=1", body="# Title"),
        Segment(atom="text", address="el=2-4", body="One. Two. Three."),
        Segment(atom="text", address="el=5", body="Coda."),
    ])
    records.append_issue_block(
        post, id="partial-content", severity="warning",
        detector="corpus.test@0", address="el=3",
    )
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf, rid


def test_attest_refuses_an_unstamped_record_with_legacy_addresses(tmp_path):
    root, rf, _rid = _ingest_legacy_record(tmp_path)
    post = records.load(rf)
    with pytest.raises(derive.DeriveError, match="remap"):
        derive.attest(post, root, strip=True)


def test_remap_engine_rewrites_verifies_and_stamps(tmp_path):
    root, rf, _rid = _ingest_legacy_record(tmp_path)
    report = remap_el.remap_record(rf, root)
    assert report.hold is None and report.skipped is None and report.changed
    rf.write_text(report.new_text, encoding="utf-8")

    post = records.load(rf)
    stamp = records.el_addressing(post)
    raw_soup = BeautifulSoup(_LEGACY_DOC, "html.parser")
    assert stamp == {
        "parser": "html.parser",
        "elements": len(raw_soup.find_all(True)),
    }
    blocks = segments.iter_blocks(post.content or "")
    addrs = [b.address for b in blocks]
    # h1 -> body's 1st div's 1st child; the flat range el=2-4 is a contiguous, complete
    # sibling run -> the §6.1.1 sibling form; el=5 -> the 2nd div's child.
    assert addrs == ["el=1.1", "el=1.[2-4]", "el=2.1"]
    # The context-block address converted with everything else.
    ctx = (post.metadata.get("_contexts") or [])[0]
    assert (ctx.get("fields") or {}).get("address") == "el=1.3"
    # The migration touch is on the chain.
    chain = post.metadata.get("touch")
    chain = chain if isinstance(chain, list) else [chain]
    assert any("migrate.el-path-36" in str(t) for t in chain)
    # Every new address resolves on the raw artifact to a real element.
    root_el = thtml.path_root(raw_soup)
    assert thtml.resolve_element_path(root_el, furi.parse_el_path("1.1")).name == "h1"
    assert thtml.resolve_element_path(root_el, furi.parse_el_path("2.1")).name == "p"

    # Idempotent: a second pass skips (already stamped).
    again = remap_el.remap_record(rf, root)
    assert again.skipped == "already stamped (3.6 addresses)" and not again.changed

    # And the attest guard now passes: the record is stamped, so re-attest may proceed
    # (it would run the real drafter; asserting the guard is enough here).
    post2 = records.load(rf)
    assert records.el_addressing(post2) is not None
    assert derive._content_zone_has_el(post2)  # addresses present, stamped — no refusal


_ALIASING_DOC = (
    "<html><head><title>Alias</title></head><body><main>"
    "<div><p>One.</p><p>Two.</p></div>"
    "<div><p>Three.</p></div>"
    "</main></body></html>"
)


def test_remap_holds_when_legacy_intervals_alias_to_one_address(tmp_path):
    """The neutrality gate. A flat interval could claim a span wider than the content it
    held, and two such intervals on one record can name the SAME §6.1.1 container — the
    truth about them, and a duplicate claim. §6.1.1 cannot represent the over-claim,
    which is the point; the record stays on the legacy grammar (unstamped resolves
    exactly as before) and goes to a worklist, rather than migrating into a red gate."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "alias.html"
    src.write_text(_ALIASING_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x.test/a", snapshot="2026-01-01T00:00:00Z")
    # Legacy enumeration: p(1), p(2), p(3). Both intervals span from inside div one to
    # inside div two, so both collapse onto <main> — one address, claimed twice.
    post.content = segments.emit([
        Segment(atom="text", address="el=1-3", body="One. Two. Three."),
        Segment(atom="text", address="el=2-3", body="Two. Three."),
    ])
    rf = paths.record_path(root, rid)
    records.dump(post, rf)

    report = remap_el.remap_record(rf, root)
    assert report.hold is not None
    assert "segment-address-duplicate" in report.hold
    assert not report.changed and report.new_text is None
    # And the record on disk is untouched — a hold writes nothing.
    assert records.el_addressing(records.load(rf)) is None


def _aliasing_record(tmp_path):
    """The held record of the test above, returned for the override tests to resolve."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "alias.html"
    src.write_text(_ALIASING_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x.test/a", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([
        Segment(atom="text", address="el=1-3", body="One. Two. Three."),
        Segment(atom="text", address="el=2-3", body="Two. Three."),
    ])
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf


def test_an_override_resolves_a_held_record_and_the_rest_still_maps(tmp_path):
    """The #65 pattern for §12.28: the engine cannot know what an over-wide interval
    covered, so the operator says — and everything else about the record still migrates
    through the same mechanical path, including the stamp."""
    root, rf = _aliasing_record(tmp_path)
    # The second interval's prose is the second div; the first spans both divs.
    report = remap_el.remap_record(rf, root, {"el=2-3": "el=1.[1-2]"})
    assert report.hold is None
    assert report.changed
    forms = report.forms
    assert forms.get("override") == 1
    assert sum(v for k, v in forms.items() if k != "override") >= 1  # the rest is mechanical
    assert "el=1.[1-2]" in report.new_text
    # The stamp lands exactly as it does on a swept record.
    rf.write_text(report.new_text, encoding="utf-8")
    assert records.el_addressing(records.load(rf)) is not None


def test_an_override_that_is_not_an_address_is_refused(tmp_path):
    root, rf = _aliasing_record(tmp_path)
    report = remap_el.remap_record(rf, root, {"el=2-3": "el=1-2"})  # a retired flat range
    assert report.hold is not None and "not a §6.1.1 address" in report.hold
    assert not report.changed


def test_an_override_naming_nothing_in_this_document_is_refused(tmp_path):
    """A range copied from another record must not land — the parent's real children are
    what a sibling range is checked against, since the range itself is unmaterializable."""
    root, rf = _aliasing_record(tmp_path)
    report = remap_el.remap_record(rf, root, {"el=2-3": "el=1.[1-9]"})
    assert report.hold is not None and "not within its parent" in report.hold
    report = remap_el.remap_record(rf, root, {"el=2-3": "el=7.4.2"})
    assert report.hold is not None and "resolves to no element" in report.hold


def test_an_override_that_does_not_clear_the_collision_still_holds(tmp_path):
    """The neutrality gate is not bypassed by a deliberate re-address — it runs after."""
    root, rf = _aliasing_record(tmp_path)
    report = remap_el.remap_record(rf, root, {"el=2-3": "el=1"})  # still <main>, still a dupe
    assert report.hold is not None and "segment-address-duplicate" in report.hold
    assert not report.changed


def test_remap_engine_holds_on_out_of_range(tmp_path):
    root, rf, _rid = _ingest_legacy_record(tmp_path)
    post = records.load(rf)
    blocks = segments.iter_blocks(post.content or "")
    blocks[0].address = "el=99"  # fabricate a drifted address
    post.content = segments.emit(blocks)
    records.dump(post, rf)
    report = remap_el.remap_record(rf, root)
    assert report.hold is not None and "out of range" in report.hold
    assert not report.changed and report.new_text is None


def test_the_fidelity_gate_never_holds_a_remap(tmp_path):
    """#159's `segment-address-fidelity` judges STAMPED records only, and stamping is what
    this migration does — so its count is 0 before every remap by construction, and a rise
    measures the record becoming legible to the rule rather than the rewrite making it worse.
    `_DEFERRED_RULE` is what keeps a rendering the remap neither authored nor can repair from
    holding an address translation; the finalize gate still refuses it.

    The record here renders only the second and third paragraphs while its remapped address
    covers all three, so the fidelity rule genuinely fires afterwards — deferred, not
    silenced."""
    from corpus import hashing, lint
    from corpus.store import LocalArtifactStore

    root = _make_corpus(tmp_path)
    src = root / "alias.html"
    src.write_text(_ALIASING_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri="https://x.test/a", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([Segment(atom="text", address="el=2-3", body="Two. Three.")])
    rf = paths.record_path(root, rid)
    records.dump(post, rf)

    report = remap_el.remap_record(rf, root, {"el=2-3": "el=1.[1-2]"})
    assert report.hold is None and report.new_text

    after = records.loads(report.new_text)
    findings = lint.lint(after, segments.iter_blocks(after.content or ""), root)
    fidelity = [f for f in findings if f.rule_id == "segment-address-fidelity"]
    assert fidelity, "the fixture must actually trip the rule, else it proves nothing"
    assert any("One." in s for f in fidelity for s in f.fields["sample"])
