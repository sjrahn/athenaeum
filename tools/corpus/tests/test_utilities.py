"""Sanity tests for the dependency-free utility modules."""

from __future__ import annotations

import frontmatter
import pytest

from corpus import hashing, mime, paths, touches, urls


def test_hash_file_and_bytes_agree(tmp_path):
    data = b"hello, corpus\n"
    f = tmp_path / "blob"
    f.write_bytes(data)
    from_file = hashing.hash_file(f)
    from_bytes = hashing.hash_bytes(data)
    assert from_file["blake3"] == from_bytes["blake3"]
    assert from_file["sha256"] == from_bytes["sha256"]
    assert len(from_file["blake3"]) == 64  # lowercase hex per spec


def test_find_corpus_root(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    (root / "records" / "ab").mkdir()
    nested = root / "records" / "ab"
    assert paths.find_corpus_root(nested) == root.resolve()


def test_find_corpus_root_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        paths.find_corpus_root(tmp_path)


def test_shard_and_record_path(tmp_path):
    rid = "ab" + "0" * 62
    assert paths.shard(rid) == "ab"
    assert paths.record_path(tmp_path, rid).name == f"{rid}.md"
    assert paths.record_path(tmp_path, rid).parent.name == "ab"


def test_mime_detects_pdf_and_png(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert mime.detect(pdf) == "application/pdf"
    png = tmp_path / "a.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert mime.detect(png) == "image/png"


def test_mime_extension_for():
    assert mime.extension_for("application/pdf") == "pdf"
    assert mime.extension_for("image/jpeg") == "jpg"
    assert mime.extension_for("application/x-ndjson") == "jsonl"


def test_urls_normalize_sorts_query_strips_fragment():
    a = urls.normalize("HTTPS://Example.COM:443/p?b=2&a=1#frag")
    b = urls.normalize("https://example.com/p?a=1&b=2")
    assert a == b
    assert "#" not in a


def test_urls_same_domain_subdomain_match():
    assert urls.same_domain("https://x.example.com/p", "www.example.com", include_subdomains=True)
    assert not urls.same_domain("https://evilexample.com/p", "example.com", include_subdomains=True)


def test_touches_coalesce_and_list_shape():
    post = frontmatter.Post("body")
    ident = touches.script_identifier("ingest")
    touches.record_touch(post, ident)
    assert post.metadata["touch"] == ident  # bare string when one entry
    touches.record_touch(post, ident)
    assert post.metadata["touch"] == f"{ident}_2"  # coalesced in place; still one entry
    other = touches.script_identifier("draft.mime/text/html")
    touches.record_touch(post, other)
    chain = post.metadata["touch"]
    assert isinstance(chain, list)
    assert chain == [f"{ident}_2", other]
    # Reset of suffix when identifier changes, then re-coalesce on repeat:
    touches.record_touch(post, other)
    assert post.metadata["touch"] == [f"{ident}_2", f"{other}_2"]


def test_touches_script_identifier_keeps_corpus_prefix():
    """Reconciliation #5: lint touch regex hardcodes the `corpus.` prefix; we keep it."""
    assert touches.script_identifier("ingest").startswith("corpus.")
