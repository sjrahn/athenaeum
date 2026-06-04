"""Spec §9 derived-views tests against a golden our-spec record."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

from corpus import derived_views, records, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _make_golden_record(corpus_root: Path) -> Path:
    """Same golden record as test_records_roundtrip, but located inside a corpus
    with `document` composite namespace registered so derived_views can resolve it."""
    # Register a local `document` composite namespace.
    ns_dir = corpus_root / "schema" / "composite" / "document"
    ns_dir.mkdir(parents=True)
    (ns_dir / "document.yaml").write_text(
        yaml.safe_dump(
            {
                "kind": "interpretive",
                "description": "Generic document classification.",
                "applies_at": ["record"],
                "extended_fields": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    p = corpus_root / "records" / "aa" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "description": "Golden",
            "status": "draft",
            "transport": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(
        post,
        mime="application/pdf",
        fields={"title": "Golden", "page_count": 2, "creation_date": "2024-01-15T10:00:00Z"},
    )
    records.append_origin_block(
        post,
        uri="https://example.com/golden.pdf",
        snapshot="2026-05-31T00:00:00Z",
    )
    records.append_classify_block(post, namespace="document", id="document")
    records.append_embed_block(
        post,
        media_type="image/png",
        address="page=1&bbox=0.1,0.1,0.5,0.5",
        transport="blake3:" + "c" * 64,
    )
    seg = segments.Segment(atom="text", address="page=1", body="First page text.")
    post.content = segments.emit([seg])
    records.append_issue_block(
        post,
        id="encoding-artifact",
        severity="warning",
        resolution="open",
        detector="corpus.draft.mime/application/pdf@0.1.0",
    )
    records.dump(post, p)
    return p


def test_classifications_view(tmp_path):
    root = _make_corpus(tmp_path)
    p = _make_golden_record(root)
    post = records.load(p)
    derived = derived_views.classifications(post)
    # §9.1: mime + classify (origin is bare → contributes nothing).
    assert derived == ["mime/application/pdf", "document"]


def test_issues_view_returns_structured(tmp_path):
    root = _make_corpus(tmp_path)
    p = _make_golden_record(root)
    post = records.load(p)
    iss = derived_views.issues(post)
    assert len(iss) == 1
    e = iss[0]
    assert e["id"] == "encoding-artifact"
    assert e["severity"] == "warning"
    assert e["resolution"] == "open"
    assert e["detector"].startswith("corpus.")


def test_uris_view_aggregates_origin_and_tagged_fields(tmp_path):
    root = _make_corpus(tmp_path)
    p = _make_golden_record(root)
    post = records.load(p)
    u = derived_views.uris(root, post)
    # Origin uri is included.
    assert "https://example.com/golden.pdf" in u


def test_timeline_view_includes_origin_snapshot(tmp_path):
    root = _make_corpus(tmp_path)
    p = _make_golden_record(root)
    post = records.load(p)
    t = derived_views.timeline(root, post)
    sources = {row[1] for row in t}
    assert "origin.snapshot" in sources
    # The PDF schema's creation_date is tagged semantic_type: timestamp.
    # If it is, the value should appear too.
    assert any("2024-01-15T10:00:00Z" in str(row[2]) for row in t), (
        "creation_date timestamp field should appear in the timeline view"
    )


def test_identifiers_view_includes_record_id(tmp_path):
    root = _make_corpus(tmp_path)
    p = _make_golden_record(root)
    post = records.load(p)
    ids = derived_views.identifiers(root, post)
    assert ids[0] == ("id", "a" * 64)
