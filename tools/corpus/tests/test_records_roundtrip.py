"""Records round-trip + embed-in-metadata-zone (reconciliation #1) tests."""

from __future__ import annotations

import frontmatter

from corpus import records, segments


def _make_golden(tmp_path):
    """Hand-author a small spec-conformant record with one of every block family."""
    p = tmp_path / "ab" / ("a" * 64 + ".md")
    p.parent.mkdir(parents=True)
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": "a" * 64,
            "description": "Test golden record exercising every block family.",
            "status": "draft",
            "transport": "sha256:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(
        post,
        mime="application/pdf",
        fields={"pdf_title": "Golden", "pdf_page_count": 2},
    )
    records.append_origin_block(
        post,
        uri="https://example.com/golden.pdf",
        snapshot="2026-05-31T00:00:00Z",
        schema_id="example.com",
    )
    records.append_classify_block(post, namespace="document", id="document")
    # Reconciliation #1: embed lives in the METADATA zone.
    records.append_embed_block(
        post,
        media_type="image/png",
        address="page=1&bbox=0.1,0.1,0.5,0.5",
        transport="blake3:" + "c" * 64,
        fields={"alt": "Cover figure"},
    )
    # Content zone — one sectionless segment.
    seg = segments.Segment(atom="text", address="page=1", body="First page text.")
    post.content = segments.emit([seg])
    # Annotation — one record-scope issue, in OUR spec's shape.
    records.append_issue_block(
        post,
        id="encoding-artifact",
        severity="warning",
        resolution="open",
        detector="corpus.draft.mime/application/pdf@0.1.0",
    )
    return post, p


def test_dump_then_load_roundtrips_every_block(tmp_path):
    post, p = _make_golden(tmp_path)
    records.dump(post, p)
    raw = p.read_text("utf-8")

    # Sanity: embed line appears BEFORE any section/segment line (metadata zone).
    embed_pos = raw.index("<!--embed")
    segment_pos = raw.index("<!--segment")
    assert embed_pos < segment_pos, "embed must precede content zone (reconciliation #1)"
    # And issue is in the annotation zone, after content.
    issue_pos = raw.index("<!--issue")
    assert segment_pos < issue_pos

    loaded = records.load(p)
    # Core frontmatter preserved.
    for k in ("id", "description", "status", "transport"):
        assert loaded.metadata[k] == post.metadata[k]
    assert loaded.metadata["touch"] == post.metadata["touch"]

    # Metadata-zone blocks preserved.
    assert records.media_type_for(loaded) == "application/pdf"
    assert records.title_for(loaded) == "Golden"

    origins = list(records.iter_origin_blocks(loaded))
    assert len(origins) == 1
    assert origins[0]["id"] == "example.com"
    assert origins[0]["fields"]["uri"] == "https://example.com/golden.pdf"

    classifies = list(records.iter_classify_blocks(loaded))
    assert len(classifies) == 1
    assert classifies[0]["namespace"] == "document"
    assert classifies[0]["id"] == "document"

    # The embed re-homing: embed is parsed FROM the metadata zone.
    embeds = list(records.iter_embed_blocks(loaded))
    assert len(embeds) == 1
    e = embeds[0]
    assert e["media_type"] == "image/png"
    assert e["address"] == "page=1&bbox=0.1,0.1,0.5,0.5"
    assert e["transport"].startswith("blake3:")
    assert e["fields"]["alt"] == "Cover figure"

    # Content zone is segments only — no embed leaked into it.
    assert "<!--embed" not in (loaded.content or "")
    content_blocks = segments.iter_blocks(loaded.content or "")
    assert len(content_blocks) == 1
    assert isinstance(content_blocks[0], segments.Segment)
    assert content_blocks[0].body == "First page text."

    # Annotation zone preserved.
    issues = list(records.iter_issue_blocks(loaded))
    assert len(issues) == 1
    assert issues[0]["id"] == "encoding-artifact"
    assert issues[0]["fields"]["severity"] == "warning"
    assert issues[0]["fields"]["resolution"] == "open"
    assert issues[0]["fields"]["detector"].startswith("corpus.")


def test_derived_classifications_view(tmp_path):
    post, p = _make_golden(tmp_path)
    records.dump(post, p)
    loaded = records.load(p)
    derived = records.derived_classifications(loaded)
    # Per spec §9.1: mime, origin, classify contribute; embeds and issues do not.
    assert derived == [
        "mime/application/pdf",
        "origin/example.com",
        "document",
    ]


def test_segments_module_does_not_recognize_embed_openers():
    """Reconciliation #1: embeds belong to records.py, not segments.py."""
    body = "<!--embed image/png\naddress: page=1\ntransport: blake3:abc\n-->\n"
    blocks = segments.iter_blocks(body)
    # The embed line isn't an opener in the content-zone grammar — nothing parses.
    assert blocks == []


def test_dump_emits_canonical_frontmatter_field_order(tmp_path):
    post, p = _make_golden(tmp_path)
    records.dump(post, p)
    raw = p.read_text("utf-8")
    # The 8 core fields appear in spec order before the closing `---`.
    pre = raw.split("---", 2)[1]
    indices = []
    for key in ["id", "description", "status", "transport", "touch"]:
        indices.append(pre.index(f"{key}:"))
    assert indices == sorted(indices)
