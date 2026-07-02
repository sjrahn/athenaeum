"""`corpus links` + the URI-index helpers it relies on.

Builds a tiny fixture corpus (two HTML records + artifacts, no network) and
checks that link discovery: resolves relative hrefs, filters to same-domain,
drops already-captured URLs, and respects --all-domains / --show-captured.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import paths, records
from corpus._cli import dispatch


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _make_html_record(root: Path, rid: str, uri: str, artifact_html: str) -> None:
    art = paths.artifact_path(root, rid, "html")
    paths.ensure_parent(art)
    art.write_text(artifact_html, encoding="utf-8")
    post = frontmatter.Post(
        content="",
        **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"),
    )
    records.set_artifact_block(post, mime="text/html", fields={"title": rid[:6]})
    records.append_origin_block(post, uri=uri, snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))


ID_A = "a1" * 32
ID_B = "b2" * 32


# ---------- URI index unit ---------- #


def test_build_uri_index_and_find_by_uri(tmp_path):
    root = _make_corpus(tmp_path)
    _make_html_record(root, ID_A, "https://example.com/page-a", "<html></html>")
    _make_html_record(root, ID_B, "https://example.com/page-b", "<html></html>")

    idx = records.build_uri_index(root)
    assert idx["https://example.com/page-a"] == ID_A
    assert idx["https://example.com/page-b"] == ID_B

    # find_by_uri canonicalizes — trailing query reorder / case on host still hits.
    assert records.find_by_uri("https://EXAMPLE.com/page-a", corpus_root=root) == ID_A
    assert records.find_by_uri("https://example.com/missing", corpus_root=root) is None

    # A prebuilt index is consulted directly (no rebuild) — the bulk-lookup affordance.
    assert records.find_by_uri("https://example.com/page-b", corpus_root=root, index=idx) == ID_B
    assert records.find_by_uri("https://example.com/page-a", corpus_root=root, index={}) is None


def test_iter_origin_uris_flattens_list(tmp_path):
    root = _make_corpus(tmp_path)
    rid = "c3" * 32
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    records.append_origin_block(
        post,
        uri=["https://e.com/canonical", "https://e.com/shortlink"],
        snapshot="2026-05-31T00:00:00Z",
    )
    records.dump(post, paths.record_path(root, rid))
    loaded = records.load(paths.record_path(root, rid))
    assert list(records.iter_origin_uris(loaded)) == [
        "https://e.com/canonical",
        "https://e.com/shortlink",
    ]


# ---------- corpus links ---------- #


def test_links_same_domain_new_only(tmp_path, capsys):
    root = _make_corpus(tmp_path)
    seed_html = (
        "<html><body>"
        '<a href="https://example.com/page-b">already captured</a>'
        '<a href="https://example.com/page-c">new same-domain</a>'
        '<a href="https://other.com/x">off-domain</a>'
        '<a href="#frag">anchor</a>'
        '<a href="mailto:a@b.com">mail</a>'
        "</body></html>"
    )
    _make_html_record(root, ID_A, "https://example.com/page-a", seed_html)
    _make_html_record(root, ID_B, "https://example.com/page-b", "<html></html>")

    rc = dispatch(["links", ID_A, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "https://example.com/page-c" in out
    assert "https://example.com/page-b" not in out  # already captured → dropped
    assert "https://other.com/x" not in out  # off-domain → dropped
    assert "mailto" not in out and "#frag" not in out


def test_links_show_captured(tmp_path, capsys):
    root = _make_corpus(tmp_path)
    seed_html = (
        "<html><body>"
        '<a href="https://example.com/page-b">b</a>'
        '<a href="https://example.com/page-c">c</a>'
        "</body></html>"
    )
    _make_html_record(root, ID_A, "https://example.com/page-a", seed_html)
    _make_html_record(root, ID_B, "https://example.com/page-b", "<html></html>")

    dispatch(["links", ID_A, "--show-captured", "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "https://example.com/page-b [captured]" in out
    assert "https://example.com/page-c" in out


def test_links_all_domains(tmp_path, capsys):
    root = _make_corpus(tmp_path)
    seed_html = '<html><body><a href="https://other.com/x">x</a></body></html>'
    _make_html_record(root, ID_A, "https://example.com/page-a", seed_html)

    dispatch(["links", ID_A, "--all-domains", "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "https://other.com/x" in out


def test_links_hash_routed_spa(tmp_path, capsys):
    """Hash-routed SPA: every link is `#/route`. The route is the resource identity, so
    relative routes resolve against the record's hash-route origin, reconcile against the
    uri-index (captured vs. frontier), and bare anchors are still dropped."""
    root = _make_corpus(tmp_path)
    seed_html = (
        "<html><body>"
        '<a href="#/page/b">captured sibling</a>'   # resolves to record B's origin
        '<a href="#/page/c">frontier</a>'           # not captured -> a candidate
        '<a href="#section">in-page anchor</a>'     # bare anchor -> dropped
        "</body></html>"
    )
    _make_html_record(root, ID_A, "https://spa.example.com/app/#/page/a", seed_html)
    _make_html_record(root, ID_B, "https://spa.example.com/app/#/page/b", "<html></html>")

    dispatch(["links", ID_A, "--show-captured", "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "https://spa.example.com/app/#/page/b [captured]" in out
    assert "https://spa.example.com/app/#/page/c" in out
    assert "#section" not in out  # bare anchor never becomes a candidate
