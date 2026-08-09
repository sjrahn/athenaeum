"""`segment-address-fidelity` — the #159 address-fidelity gate registered in `corpus.lint`'s
default rule set. Stamped records only (an unstamped `el=` speaks the frozen pre-3.6 index),
and parse-tolerant: a missing artifact or a stamp attesting a different tree silently does
not fire."""

from __future__ import annotations

import frontmatter
from bs4 import BeautifulSoup

from corpus import hashing, lint, paths, records, segments
from corpus.store import LocalArtifactStore
from corpus.transforms.html import EL_PARSER_ID, total_element_count

_HTML = (
    "<html><body><div>"
    "<h1>Brake System</h1><h2>Caliper Removal</h2><h3>Torque Values</h3>"
    "</div><div><p>An unrelated note about the water pump.</p></div>"
    "</body></html>"
)


def _record(tmp_path, blocks: list, *, stamp: dict | None = "auto", with_artifact: bool = True):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    src = root / "page.html"
    src.write_text(_HTML, encoding="utf-8")
    rid = hashing.hash_file(src)["blake3"]
    if with_artifact:
        LocalArtifactStore(root).put(rid, "html", src)

    if stamp == "auto":
        stamp = {
            "parser": EL_PARSER_ID,
            "elements": total_element_count(BeautifulSoup(_HTML, EL_PARSER_ID)),
        }
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(
        post, mime="text/html", fields={"addressing": stamp} if stamp else {}
    )
    records.append_origin_block(
        post, uri="https://fidelity.example.com/p", snapshot="2026-01-01T00:00:00Z",
        schema_id="fidelity.example.com",
    )
    post.content = segments.emit(blocks)
    records.dump(post, paths.record_path(root, rid))
    return post, root


def _findings(post, root):
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root) if f.rule_id == "segment-address-fidelity"]


def _faithful() -> list:
    return [
        segments.Segment(
            atom="text",
            address="el=1.[1-3]",
            body="# Brake System\n\n## Caliper Removal\n\n### Torque Values",
        )
    ]


def test_faithful_record_yields_nothing(tmp_path):
    post, root = _record(tmp_path, _faithful())
    assert _findings(post, root) == []


def test_dropped_heading_warns_and_names_the_element(tmp_path):
    blocks = [
        segments.Segment(
            atom="text", address="el=1.[1-3]", body="# Brake System\n\n## Caliper Removal"
        )
    ]
    post, root = _record(tmp_path, blocks)
    findings = _findings(post, root)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].subtype == "dropped"
    assert findings[0].fields["count"] == 1
    assert "Torque Values" in findings[0].message and "#159" in findings[0].message


def test_borrowed_text_is_an_error(tmp_path):
    blocks = [
        segments.Segment(
            atom="text", address="el=1", body="An unrelated note about the water pump."
        )
    ]
    post, root = _record(tmp_path, blocks)
    kinds = {f.subtype: f for f in _findings(post, root)}
    assert kinds["misplaced"].severity == "error"
    assert "water pump" in kinds["misplaced"].message


def test_unresolvable_address_is_an_error(tmp_path):
    blocks = [segments.Segment(atom="text", address="el=1.9", body="# Brake System")]
    post, root = _record(tmp_path, blocks)
    kinds = {f.subtype: f for f in _findings(post, root)}
    assert kinds["unresolvable"].severity == "error"


def test_unstamped_record_is_never_judged(tmp_path):
    """An unstamped `el=` value speaks the frozen pre-3.6 filtered index (§12.28) — resolving
    it through the path walk would compare against the wrong element entirely."""
    blocks = [segments.Segment(atom="text", address="el=1.[1-3]", body="Nothing like the DOM.")]
    post, root = _record(tmp_path, blocks, stamp=None)
    assert _findings(post, root) == []


def test_stamp_attesting_a_different_tree_does_not_fire(tmp_path):
    """A disagreeing element count means this parse is not the tree the addresses were
    computed against — every address resolves somewhere else, so anything said here is noise
    (and another gate's finding)."""
    blocks = [segments.Segment(atom="text", address="el=1", body="Nothing like the DOM.")]
    post, root = _record(tmp_path, blocks, stamp={"parser": EL_PARSER_ID, "elements": 999})
    assert _findings(post, root) == []


def test_missing_artifact_does_not_fire(tmp_path):
    blocks = [segments.Segment(atom="text", address="el=1", body="Nothing like the DOM.")]
    post, root = _record(tmp_path, blocks, with_artifact=False)
    assert _findings(post, root) == []
