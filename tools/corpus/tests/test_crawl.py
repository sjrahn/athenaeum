"""`corpus crawl` — state round-trip, link extraction, and offline dry-run BFS.

The live capture path needs Playwright + network (covered by the network-marked
capture e2e). Here we drive crawl with `--dry-run`, which never launches a
browser: it finds the already-present seed via the URI index, expands its
same-domain links into the frontier, and reports — all offline.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import paths, records
from corpus._cli import dispatch
from corpus._cli.crawl import CrawlState, _extract_links, _sidecar_path


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


ID_SEED = "a1" * 32


# ---------- state + helpers ---------- #


def test_crawl_state_roundtrip():
    state = CrawlState(
        seed="https://e.com/",
        normalized_seed="https://e.com",
        seed_host="e.com",
        depth_cap=2,
        count_cap=50,
        include_subdomains=True,
        visited=["https://e.com"],
        frontier=[("https://e.com/a", 1)],
        failed=[("https://e.com/bad", "boom")],
        skipped=[("https://e.com/no", "robots-disallowed")],
    )
    restored = CrawlState.from_dict(state.to_dict())
    assert restored == state
    # Tuples survive the JSON list round-trip.
    assert restored.frontier == [("https://e.com/a", 1)]


def test_sidecar_path_deterministic(tmp_path):
    cap = tmp_path / "capture"
    a = _sidecar_path(cap, "https://e.com/seed")
    b = _sidecar_path(cap, "https://e.com/seed")
    c = _sidecar_path(cap, "https://e.com/other")
    assert a == b
    assert a != c
    assert a.name.startswith("crawl-") and a.suffix == ".json"


def test_extract_links_filters(tmp_path):
    art = tmp_path / "a.html"
    art.write_text(
        "<html><body>"
        '<a href="https://e.com/x">x</a>'
        '<a href="/rel">rel</a>'
        '<a href="#frag">frag</a>'              # bare in-page anchor -> dropped
        '<a href="#">empty-frag</a>'            # bare anchor -> dropped
        '<a href="#/vehicle/46076">route</a>'   # client-side route -> KEPT
        '<a href="#!/legacy/route">bang</a>'    # hashbang route -> KEPT
        '<a href="mailto:a@b.com">m</a>'
        '<a href="javascript:void(0)">j</a>'
        "<a>noisy</a>"
        "</body></html>",
        encoding="utf-8",
    )
    links = _extract_links(art, "https://e.com/")
    assert "https://e.com/x" in links
    assert "/rel" in links
    # Hash-routed SPA links are routes, not anchors — they must survive extraction.
    assert "#/vehicle/46076" in links
    assert "#!/legacy/route" in links
    # Bare anchors + non-navigational schemes are still dropped.
    assert "#frag" not in links and "#" not in links
    assert not any(h.startswith(("mailto:", "javascript:")) for h in links)


# ---------- offline dry-run BFS ---------- #


def test_crawl_dry_run_expands_same_domain(tmp_path, capsys):
    root = _make_corpus(tmp_path)
    seed_html = (
        "<html><body>"
        '<a href="https://example.com/page-b">b</a>'
        '<a href="https://example.com/page-c">c</a>'
        '<a href="https://other.com/x">off-domain</a>'
        "</body></html>"
    )
    _make_html_record(root, ID_SEED, "https://example.com/page-a", seed_html)

    rc = dispatch([
        "crawl",
        "https://example.com/page-a",
        "--dry-run",
        "--depth", "1",
        "--corpus-root", str(root),
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "https://example.com/page-b" in err
    assert "https://example.com/page-c" in err
    assert "https://other.com/x" not in err  # off-domain excluded from frontier


def test_crawl_dry_run_missing_seed_empty_frontier(tmp_path, capsys):
    """Dry-run against a URL not in the corpus: nothing to expand, clean exit."""
    root = _make_corpus(tmp_path)
    rc = dispatch([
        "crawl",
        "https://example.com/unknown",
        "--dry-run",
        "--depth", "1",
        "--corpus-root", str(root),
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "frontier:" in err
