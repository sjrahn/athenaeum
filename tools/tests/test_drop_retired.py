"""The §12.27 field sweep (ATH-CORPUS 3.5) — `corpus.drop_retired`.

What these pin: the sweep removes exactly the retired surfaces and nothing else; it is
idempotent; the structural byte-mark's own field survives (it was never the content
segment's `entry:`); and the two refusals hold rather than guess — a `relation` block with
no restored index span, and any rewrite that would lint worse.
"""

from __future__ import annotations

import frontmatter
import pytest

from corpus import drop_retired, hashing, paths, records, schemas, segments
from corpus.segments import Section, Segment
from corpus.store import LocalArtifactStore

_DOC = (
    "<html><head><title>Page Title - SITE</title></head><body>"
    "<div><h1>Heading</h1><p>One.</p><p>Two.</p></div>"
    "</body></html>"
)


def _make_corpus(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _record(tmp_path, blocks, *, contexts=(), canonical=True):
    root = _make_corpus(tmp_path)
    src = root / "page.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    if canonical:
        post.metadata["canonical"] = f"blake3:{rid}"
    records.set_artifact_block(post, mime="text/html", fields={"title": "Page Title - SITE"})
    records.append_origin_block(post, uri="https://x.test/p", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit(blocks)
    for ctx in contexts:
        post.metadata.setdefault("_contexts", []).append(ctx)
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf


def _relation(address="el=1.2"):
    return {
        "namespace": "relation",
        "id": "related-information",
        "subtype": None,
        "fields": {"address": address, "target_text": "Elsewhere", "target_url": "https://x/e"},
    }


def test_sweep_drops_every_retired_surface_and_nothing_else(tmp_path):
    section = Section(
        form="document",
        address="el=1.1",
        description="A vouch that 3.5 retired.",
        entry="A TOC label.",
        extra={"title": "An authored title."},
        segments=[
            Segment(atom="text", address="el=1.1.2", entry="One", description="prose", body="One."),
            Segment(atom="structural", address="el=1.1.1", level=1, body="Heading"),
        ],
    )
    root, rf = _record(tmp_path, [section])
    before = rf.read_text(encoding="utf-8")
    assert "canonical:" in before

    report = drop_retired.sweep_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert dict(report.counts) == {
        "frontmatter canonical": 1,
        "section description": 1,
        "section entry": 1,
        "section title": 1,
        "segment description": 1,
        "segment entry": 1,
    }
    rf.write_text(report.new_text, encoding="utf-8")

    post = records.load(rf)
    assert "canonical" not in post.metadata
    blocks = segments.iter_blocks(post.content)
    sec = blocks[0]
    # *(3.7)* The envelope is derived from the children, so it is what they actually cover —
    # `el=1.1.[1-2]`, not the `el=1.1` the fixture stored, which over-claimed the parent.
    assert sec.form == "document" and sec.address == "el=1.1.[1-2]"
    assert sec.description is None and sec.entry is None and "title" not in sec.extra
    text_seg, structural = sec.segments
    # The content segment loses both retired fields; its BODY is untouched.
    assert text_seg.description is None and text_seg.entry is None
    assert text_seg.body.strip() == "One."
    # The byte-mark's own field was never the same field (§4.3.2.3).
    assert structural.body == "Heading" and structural.level == 1
    touch = post.metadata["touch"]
    touch = touch if isinstance(touch, list) else [touch]
    assert any(t.startswith(f"corpus.{drop_retired.TOUCH_ID}") for t in touch)


def test_sweep_is_idempotent(tmp_path):
    root, rf = _record(
        tmp_path,
        [Section(form="document", address="el=1.1", description="d",
                 segments=[Segment(atom="text", address="el=1.1.2", body="One.")])],
    )
    first = drop_retired.sweep_record(rf, root)
    rf.write_text(first.new_text, encoding="utf-8")
    second = drop_retired.sweep_record(rf, root)
    assert second.changed is False
    assert second.skipped == "carries nothing 3.5/3.7 retired"


def test_sweep_reports_the_derived_pair_either_side(tmp_path):
    """The one VISIBLE consequence a formed record's sweep can have: its title was
    resolving off the form layer, and the section field is what 3.5 retires (§4.2.3). The
    manifest carries both readings so a display change never lands unannounced. (This
    fixture declares no form overlay, so the ladder resolves the artifact layer on both
    sides — the reporting path is what is pinned here; the real fleet's transition is
    measured by the dry-run's `--titles`.)"""
    root, rf = _record(
        tmp_path,
        [Section(form="document", address="el=1.1", extra={"title": "Page Title"},
                 segments=[Segment(atom="text", address="el=1.1.2", body="One.")])],
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed
    assert report.title_before == "Page Title - SITE"
    assert report.title_after == "Page Title - SITE"


def test_a_relation_block_with_no_restored_index_span_holds(tmp_path):
    """Dropping the rail before it comes home is data loss, not a sweep (§12.27)."""
    root, rf = _record(
        tmp_path,
        [Section(form="document", address="el=1.1", description="d",
                 segments=[Segment(atom="text", address="el=1.1.2", body="One.")])],
        contexts=[_relation()],
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed is False
    assert "no `form/index` span claims" in (report.hold or "")

    allowed = drop_retired.sweep_record(rf, root, allow_unrestored=True)
    assert allowed.changed
    assert allowed.counts["context relation"] == 1


def test_a_restored_index_span_lets_the_relation_blocks_go(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            Section(form="document", address="el=1.1", description="d",
                    segments=[Segment(atom="text", address="el=1.1.2", body="One.")]),
            Section(form="index", address="el=1.2",
                    segments=[Segment(atom="text", address="el=1.2", body="- Elsewhere")]),
        ],
        contexts=[_relation("el=1.2.3")],  # inside the restored span, by §6.1.1 containment
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed, report.hold
    assert report.counts["context relation"] == 1


def test_a_whole_record_index_section_does_not_count_as_restored(tmp_path):
    """The loose reading — "the record has an index span somewhere" — is wrong on a real
    population: 786 alldata records were fitted WHOLE-RECORD to `form/index` by the 3.2
    form-adopt sweep, so an index section exists while nothing renders the rail. Under 3.7
    that section derives the envelope of the content it actually holds, which is nowhere near
    the rail — so per-block containment still refuses, now for a reason visible in the
    address rather than in an absent field."""
    root, rf = _record(
        tmp_path,
        [Section(form="index", description="d",
                 segments=[Segment(atom="text", address="el=1.1.2", body="One.")])],
        contexts=[_relation("el=1.2.3")],
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed is False
    assert "no `form/index` span claims" in (report.hold or "")


def test_a_relation_block_outside_the_restored_span_still_holds(tmp_path):
    """Per-BLOCK containment, not per-record: one link that came home does not license
    dropping a sibling that did not."""
    root, rf = _record(
        tmp_path,
        [Section(form="index", address="el=1.2",
                 segments=[Segment(atom="text", address="el=1.2", body="- Elsewhere")])],
        contexts=[_relation("el=1.2.3"), _relation("el=1.9.1")],
        canonical=False,
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed is False
    assert "1 of 2 `relation` block(s)" in (report.hold or "")


def test_generic_title_verdicts_go_but_real_issues_stay(tmp_path):
    """A detector's verdict about a DERIVED value is a health query (§12.21); a genuine
    capture-fidelity observation is an annotation and survives."""
    keep = {
        "namespace": "issue", "id": "partial-content", "subtype": None,
        "fields": {"address": "el=1.1.2", "severity": "warning"},
    }
    drop = {
        "namespace": "issue", "id": "generic-title", "subtype": None,
        "fields": {"severity": "info"},
    }
    root, rf = _record(
        tmp_path,
        [Section(form="document", address="el=1.1", description="d",
                 segments=[Segment(atom="text", address="el=1.1.2", body="One.")])],
        contexts=[keep, drop],
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed, report.hold
    assert report.counts["context issue/generic-title"] == 1
    rf.write_text(report.new_text, encoding="utf-8")
    remaining = records.load(rf).metadata["_contexts"]
    assert [c["id"] for c in remaining] == ["partial-content"]


def test_the_neutrality_gate_holds_a_rewrite_that_would_lint_worse(tmp_path):
    """`text/data-table-dynamic` opts out of lossless (`enables_lossless: false`), so it is
    a body-empty marker whose `description` `segment-description-required` still asks for.
    Dropping it raises that rule's count — the gate holds the record rather than trading a
    retired field for a new finding (the §12.28 lesson: the whole rule set, deliberately)."""
    root, rf = _record(
        tmp_path,
        [Section(form="document", address="el=1.1", segments=[
            Segment(atom="text", overlay="text/data-table-dynamic", address="el=1.1.2",
                    description="A live table the capture could not resolve."),
        ])],
        canonical=False,
    )
    report = drop_retired.sweep_record(rf, root)
    assert report.changed is False
    assert "segment-description-required" in (report.hold or ""), report.hold


@pytest.mark.parametrize("field_name", ["description", "entry"])
def test_a_section_carrying_only_one_retired_field_still_sweeps(tmp_path, field_name):
    section = Section(
        form="document", address="el=1.1",
        segments=[Segment(atom="text", address="el=1.1.2", body="One.")],
    )
    setattr(section, field_name, "value")
    root, rf = _record(tmp_path, [section], canonical=False)
    report = drop_retired.sweep_record(rf, root)
    assert report.changed, report.hold
    assert dict(report.counts) == {f"section {field_name}": 1}
