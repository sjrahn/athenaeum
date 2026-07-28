"""*(3.8, spec §7.2)* Origin-overlay `regions:` and `exemplars:`.

The exemplar mechanism exists because prose under-determines shape: a rule can say *a table's
title is its `<caption>`* and leave a dozen renderings conformant. The failure it replaces is
worse than vagueness — a pass with no blessed example takes its shape from whatever record it
happens to open, which during any lazy migration is a record in the RETIRED grammar. So the
tests that matter here are the ones about the pin and the scope, not the happy path.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import paths, records, schemas, segments

OVERLAY = """\
id: example.com
kind: interpretive
applies_to:
  host_pattern: example.com
regions:
  - role: breadcrumb
    selector: div.crumb
    renders: framing
  - role: vehicle
    selector: div.vehicle
    renders: never
    lifts_to: vehicle
  - role: article
    selector: div.article
    renders: subject
"""


def _root(tmp_path: Path, overlay: str = OVERLAY) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema" / "origin" / "web").mkdir(parents=True)
    (root / "schema" / "origin" / "web" / "example.com.yaml").write_text(overlay, encoding="utf-8")
    schemas.cache_clear()
    return root


def _record(root: Path, rid: str, body: str, *, origin_id: str | None = "example.com",
            uri: str = "https://example.com/p") -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata["id"] = rid
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-01-01T00:00:00Z")
    if origin_id:
        # The block view is live, so stamping the id here is what a qualified opener would
        # be — verified rather than assumed: the foreign/lineage tests below are only
        # meaningful if this actually persists.
        for blk in records.iter_origin_blocks(post):
            blk["id"] = origin_id
    post.content = body
    records.dump(post, paths.record_path(root, rid))
    return post


# ---------- regions ---------- #


def test_regions_read_in_declaration_order(tmp_path):
    """Declaration order IS the order framing regions take in the trailing span (§4.3.2.1's
    cross-span significance rule), so a reader that sorted them would be losing a decision."""
    rows = schemas.origin_regions(_root(tmp_path), "example.com")
    assert [r["role"] for r in rows] == ["breadcrumb", "vehicle", "article"]
    assert [r["renders"] for r in rows] == ["framing", "never", "subject"]
    assert rows[1]["lifts_to"] == "vehicle"


def test_a_malformed_region_is_dropped_rather_than_guessed_at(tmp_path):
    """A region declaration decides what does and does not enter a body. A row with no
    `renders` must not silently become `subject` — that would put chrome in the record."""
    root = _root(tmp_path, OVERLAY + "  - role: mystery\n    selector: div.x\n")
    assert [r["role"] for r in schemas.origin_regions(root, "example.com")] == [
        "breadcrumb", "vehicle", "article"
    ]
    errs = schemas.origin_declaration_errors(root, "example.com")
    assert any("mystery" in e and "renders" in e for e in errs)


def test_a_region_with_no_selector_is_reported(tmp_path):
    root = _root(tmp_path, OVERLAY + "  - role: nowhere\n    renders: subject\n")
    assert any("no `selector`" in e for e in schemas.origin_declaration_errors(root, "example.com"))


# ---------- the pin ---------- #


def test_the_pin_covers_the_content_zone_not_the_file(tmp_path):
    """A `touch` entry appends on every pass. If the pin were over the file, an unrelated
    migration would mark every exemplar stale — and a gate that cries wolf gets turned off."""
    root = _root(tmp_path)
    post = _record(root, "a" * 64, "<!--segment text-->\n\nhello\n")
    before = schemas.content_pin(post)

    post.metadata["touch"] = ["corpus.migrate.something@0.1.0"]
    records.dump(post, paths.record_path(root, "a" * 64))
    after = schemas.content_pin(records.load(paths.record_path(root, "a" * 64)))
    assert before == after, "a touch append is not a change in what the exemplar teaches"


def test_the_pin_moves_when_the_shape_moves(tmp_path):
    root = _root(tmp_path)
    post = _record(root, "a" * 64, "<!--segment text-->\n\nhello\n")
    before = schemas.content_pin(post)
    post.content = segments.emit(
        [segments.Segment(atom="text", overlay="text/data-table", body="| a |\n|---|\n| 1 |")]
    )
    assert schemas.content_pin(post) != before


def test_a_drifted_exemplar_is_stale_and_that_is_an_error(tmp_path):
    """The whole design. A drifted exemplar teaches a shape the corpus has moved off, with the
    full authority of a blessed one — worse than having no example at all."""
    root = _root(tmp_path)
    post = _record(root, "a" * 64, "<!--segment text-->\n\nhello\n")
    pin = schemas.content_pin(post)
    row = {"record": "a" * 64, "content": pin, "shows": "x"}
    assert schemas.exemplar_status(root, "example.com", row)[0] == "ok"

    post.content = "<!--segment text-->\n\nmoved on\n"
    records.dump(post, paths.record_path(root, "a" * 64))
    state, detail = schemas.exemplar_status(root, "example.com", row)
    assert state == "stale"
    assert "re-pin" in detail


def test_an_unpinned_exemplar_is_reported_rather_than_trusted(tmp_path):
    root = _root(tmp_path)
    _record(root, "a" * 64, "hello")
    row = {"record": "a" * 64, "content": "", "shows": "x"}
    assert schemas.exemplar_status(root, "example.com", row)[0] == "unpinned"


def test_a_missing_exemplar_is_reported(tmp_path):
    root = _root(tmp_path)
    row = {"record": "b" * 64, "content": "blake3:00", "shows": "x"}
    assert schemas.exemplar_status(root, "example.com", row)[0] == "missing"


# ---------- scope: same origin, through lineage ---------- #


def test_a_foreign_origins_record_may_not_be_an_exemplar(tmp_path):
    """Shape judgments are origin-specific, and same-origin is also what keeps an exemplar
    inside one hub — so tenancy holds with no second mechanism."""
    root = _root(tmp_path)
    _record(root, "a" * 64, "hello", origin_id="other.test", uri="https://other.test/p")
    row = {"record": "a" * 64, "content": "x", "shows": "x"}
    assert schemas.exemplar_status(root, "example.com", row)[0] == "foreign"


def test_a_promoted_member_reaches_its_origin_through_lineage(tmp_path):
    """A promoted leaf carries NO host origin — its `uri:` is the containment lineage. Taken
    literally that makes a leaf permanently ineligible, and leaves are exactly where the
    host-specific shape judgments land. §8.1 already says a container's origin is legitimate
    context for what its member is, so the walk follows it."""
    root = _root(tmp_path)
    parent = "a" * 64
    leaf = "b" * 64
    _record(root, parent, "<!--segment placement\naddress: el=1\n-->\n")
    _record(root, leaf, "<!--segment text-->\n\nleaf\n",
            origin_id=None, uri=f"corpus://{parent}?el=1")

    post = records.load(paths.record_path(root, leaf))
    assert not [b.get("id") for b in records.iter_origin_blocks(post) if b.get("id")]
    assert "example.com" in schemas._origin_ids_through_lineage(root, post)

    row = {"record": leaf, "content": schemas.content_pin(post), "shows": "x"}
    assert schemas.exemplar_status(root, "example.com", row)[0] == "ok"
