"""Record connection graph (`corpus.graph`) — outbound-link extraction + captured/uncaptured
resolution against the corpus URI index. Pure-library (no `[api]` extra)."""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import graph, records, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _record(root: Path, ch: str, *, origin: str, body: str, title: str = "T") -> str:
    rid = ch * 64
    p = root / "records" / (ch * 2) / f"{rid}.md"
    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "title": title,
            "status": "normalized",
            "transport": "blake3:" + "b" * 64,
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=origin, snapshot="2026-06-01T00:00:00Z")
    post.content = segments.emit([segments.Segment(atom="text", address="el=1", body=body)])
    records.dump(post, p)
    return rid


def _load(root: Path, ch: str):
    return records.load(root / "records" / (ch * 2) / f"{ch * 64}.md")


def test_iter_content_urls_strips_punct_and_dedupes(tmp_path):
    root = _make_corpus(tmp_path)
    _record(
        root,
        "a",
        origin="https://e.example/o",
        body="A (https://x.org/p), and https://x.org/p again; then https://y.org.",
    )
    urls = graph.iter_content_urls(_load(root, "a"))
    assert urls == ["https://x.org/p", "https://y.org"]


def test_build_links_captured_vs_uncaptured(tmp_path):
    root = _make_corpus(tmp_path)
    _record(root, "b", origin="https://example.com/peer", body="peer body")
    _record(
        root,
        "a",
        origin="https://example.com/self",
        body=(
            "See https://example.com/peer and https://external.example/news for context. "
            "Also https://example.com/self again."
        ),
    )
    index = records.build_uri_index(root)
    links = graph.build_links(root, _load(root, "a"), uri_index=index)
    by_url = {link["url"]: link for link in links}

    # the body URL that maps to another corpus record is a captured cross-reference
    assert by_url["https://example.com/peer"]["recId"] == "b" * 64
    # the external URL stays uncaptured
    assert by_url["https://external.example/news"]["recId"] is None
    assert by_url["https://external.example/news"]["host"] == "external.example"
    # the record citing its own origin URL is not an outbound edge
    assert "https://example.com/self" not in by_url


def test_build_links_empty_when_no_urls(tmp_path):
    root = _make_corpus(tmp_path)
    _record(root, "a", origin="https://e.example/o", body="no links here.")
    assert graph.build_links(root, _load(root, "a"), uri_index=records.build_uri_index(root)) == []
