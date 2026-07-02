"""Capture-time pagination reconciliation — walk → merge → one artifact.

Pure-function units (BeautifulSoup over fixture HTML) plus integration tests that drive
`capture_and_ingest` with the browser `capture()` monkeypatched to canned per-page HTML —
all deterministic, no browser/network. See `docs/PAGINATION-RECONCILE.md`.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup

import corpus.capture as capture_mod
from corpus import hashing, paths, records
from corpus._cli import dispatch
from corpus.capture import pagination

SEED = "https://forum.test/thread/1"


def _page(posts, *, next_href: str | None = None, reply_count: str = "6 replies") -> str:
    """A XenForo-shaped page: <link rel=next> in <head>, an id-keyed `.posts` container,
    and an identical (framework) reply-count footer."""
    nl = f'<link rel="next" href="{next_href}">' if next_href else ""
    arts = "".join(
        f'<article id="post-{i}"><div class="msg">Post {i} body text here.</div></article>'
        for i in posts
    )
    return (
        f"<html><head>{nl}</head><body>"
        f'<div id="content"><div class="posts">{arts}</div></div>'
        f'<div class="reply-count">{reply_count}</div>'
        "</body></html>"
    )


# ---------- config ---------- #


def test_normalize_config_bool_and_map():
    assert pagination.normalize_config(True) == pagination.PaginationConfig()
    assert pagination.normalize_config(False) is None
    assert pagination.normalize_config(None) is None
    assert pagination.normalize_config("nonsense") is None
    c = pagination.normalize_config(
        {
            "content_selector": ".x",
            "next": {"rel": False, "selector": "a.n"},
            "max_pages": 5,
            "expect_count": {"selector": ".c"},
        }
    )
    assert c == pagination.PaginationConfig(
        content_selector=".x",
        follow_rel=False,
        next_selector="a.n",
        max_pages=5,
        expect_selector=".c",
    )


# ---------- next-page enumeration ---------- #


def test_extract_next_rel_link():
    nxt = pagination.extract_next_url(
        _page([1], next_href="?page=2"), base_url=SEED, cfg=pagination.PaginationConfig()
    )
    assert nxt == "https://forum.test/thread/1?page=2"


def test_extract_next_a_rel():
    html = "<html><body><a rel='next' href='/thread/1/page-2'>next</a></body></html>"
    nxt = pagination.extract_next_url(html, base_url=SEED, cfg=pagination.PaginationConfig())
    assert nxt == "https://forum.test/thread/1/page-2"


def test_extract_next_selector_override():
    html = "<html><body><a class='nav-next' href='?page=2'>n</a></body></html>"
    cfg = pagination.PaginationConfig(follow_rel=False, next_selector="a.nav-next")
    assert pagination.extract_next_url(html, base_url=SEED, cfg=cfg) == "https://forum.test/thread/1?page=2"


def test_extract_next_none_when_absent():
    cfg = pagination.PaginationConfig()
    assert pagination.extract_next_url(_page([1]), base_url=SEED, cfg=cfg) is None


# ---------- region detection ---------- #


def test_detect_region_picks_posts_container():
    s1 = BeautifulSoup(_page([1, 2], next_href="?page=2"), "html.parser")
    s2 = BeautifulSoup(_page([3, 4]), "html.parser")
    path = pagination.detect_region(s1, s2)
    region = pagination.locate_region(s1, path)
    assert region is not None and region.get("class") == ["posts"]


def test_detect_region_none_when_identical():
    s = BeautifulSoup(_page([1]), "html.parser")
    assert pagination.detect_region(s, BeautifulSoup(_page([1]), "html.parser")) is None


# ---------- merge ---------- #


def test_merge_pages_lossless_auto_detect():
    pages = [_page([1, 2], next_href="?page=2"), _page([3, 4], next_href="?page=3"), _page([5, 6])]
    merged, posts = pagination.merge_pages(pages)
    assert posts == 6
    ids = [a["id"] for a in BeautifulSoup(merged, "html.parser").select(".posts > article")]
    assert ids == [f"post-{i}" for i in range(1, 7)]


def test_merge_dedup_by_id():
    p1 = _page([1, 2], next_href="?page=2")
    p2 = _page([2, 3])  # post-2 repeats
    merged, posts = pagination.merge_pages([p1, p2], content_selector=".posts")
    assert posts == 3
    ids = [a["id"] for a in BeautifulSoup(merged, "html.parser").select(".posts > article")]
    assert ids == ["post-1", "post-2", "post-3"]


def test_merge_dedup_idless_by_subtree():
    def page(bodies, nh=None):
        nl = f'<link rel="next" href="{nh}">' if nh else ""
        arts = "".join(f"<article><p>{b}</p></article>" for b in bodies)
        return f"<html><head>{nl}</head><body><div class='posts'>{arts}</div></body></html>"

    merged, posts = pagination.merge_pages(
        [page(["A", "B"], nh="?page=2"), page(["B", "C"])], content_selector=".posts"
    )
    assert posts == 3  # A, B (deduped), C
    texts = [a.get_text() for a in BeautifulSoup(merged, "html.parser").select(".posts > article")]
    assert texts == ["A", "B", "C"]


def test_merge_promotes_lazy_img():
    p1 = _page([1], next_href="?page=2")
    p2 = (
        "<html><body><div class='posts'>"
        "<article id='post-2'><img data-src='https://img/2.jpg'></article>"
        "</div></body></html>"
    )
    merged, _ = pagination.merge_pages([p1, p2], content_selector=".posts")
    img = BeautifulSoup(merged, "html.parser").select_one("#post-2 img")
    assert img["src"] == "https://img/2.jpg"


def test_merge_zero_new_children_stops():
    # Page 2 is a duplicate of page 1's content -> contributes nothing -> walk stops cleanly.
    p1 = _page([1, 2], next_href="?page=2")
    pages = [p1, _page([1, 2]), _page([3, 4])]
    _, posts = pagination.merge_pages(pages, content_selector=".posts")
    assert posts == 2  # stopped at the all-duplicate page 2, never reached page 3


def test_merge_count_excludes_idless_framework():
    # An id-less framework node (page-nav) rides inside the content region on every page: it
    # dedups to one copy and is NOT counted as an item — `posts` reports the 4 id'd posts.
    def page(ids, *, nh=None):
        nl = f'<link rel="next" href="{nh}">' if nh else ""
        fw = '<div class="page-nav">paging</div>'
        arts = "".join(f'<article id="post-{i}">P{i}</article>' for i in ids)
        return f"<html><head>{nl}</head><body><div class='posts'>{fw}{arts}</div></body></html>"

    pages = [page([1, 2], nh="?page=2"), page([3, 4])]
    merged, posts = pagination.merge_pages(pages, content_selector=".posts")
    assert posts == 4  # framework div excluded from the item count
    soup = BeautifulSoup(merged, "html.parser")
    assert len(soup.select(".posts > .page-nav")) == 1  # framework deduped to a single copy
    assert [a["id"] for a in soup.select(".posts > article")] == [f"post-{i}" for i in range(1, 5)]


def test_merge_region_unresolved_raises():
    p = _page([1], next_href="?page=2")
    with pytest.raises(pagination.RegionUnresolved):
        pagination.merge_pages([p, p])  # identical -> nothing differs -> no region


# ---------- expected-count ---------- #


def test_expected_count_parses_int():
    html = _page([1], reply_count="1,234 replies")
    cfg = pagination.PaginationConfig(expect_selector=".reply-count")
    assert pagination.expected_count(html, cfg=cfg) == 1234
    assert pagination.expected_count(html, cfg=pagination.PaginationConfig()) is None


# ---------- integration (capture monkeypatched) ---------- #


def _init_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    assert dispatch(["init", str(root), "--namespace", "document"]) == 0
    return root


def _overlay(root: Path, body: str) -> None:
    d = root / "schema" / "origin" / "web"
    d.mkdir(parents=True, exist_ok=True)
    (d / "forum.test.yaml").write_text(body, encoding="utf-8")


def _fake_capture(monkeypatch, pages: dict[int, str]) -> None:
    """Replace the browser `capture()` with one that stages a canned page per `?page=N`.

    Faithfully stages to the real `_sanitize_filename` path (which drops the query, so all
    pages share one name) — the reconcile loop reads each into memory and unlinks it before
    the next capture, so the collision never bites. No browser."""
    from urllib.parse import parse_qs, urlparse

    def _cap(url, *, corpus_root, opts=None):
        n = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
        cap_dir = corpus_root / "capture"
        cap_dir.mkdir(parents=True, exist_ok=True)
        path = cap_dir / f"{capture_mod._sanitize_filename(url)}.html"
        path.write_text(pages[n], encoding="utf-8")
        return capture_mod.CaptureResult(capture_path=path, used_video=False, issues=[])

    monkeypatch.setattr(capture_mod, "capture", _cap)


def test_reconcile_merges_and_records_provenance(tmp_path, monkeypatch):
    root = _init_corpus(tmp_path)
    _overlay(
        root,
        "applies_to: {host_pattern: forum.test}\n"
        "capture:\n"
        "  url_rewrite:\n"
        # A path-changing pin: bare and pinned forms differ under `normalize`, so BOTH are
        # recorded. (A fragment-only pin like `#flat` would collapse to the bare form under
        # identity — see test_url_equivalent; that is the minimal-origin-block behavior.)
        "    - {pattern: '/thread/1', replacement: '/thread/1/flat'}\n"
        "  pagination: true\n",
    )
    _fake_capture(
        monkeypatch,
        {
            1: _page([1, 2], next_href="?page=2"),
            2: _page([3, 4], next_href="?page=3"),
            3: _page([5, 6]),
        },
    )

    rec = capture_mod.capture_and_ingest(SEED, corpus_root=root)
    assert rec is not None
    post = records.load(rec)

    origin = list(records.iter_origin_blocks(post))[-1]["fields"]
    assert origin["pagination"] == {
        "pages": 3,
        "form": "https://forum.test/thread/1/flat",
        "posts": 6,
    }

    uris = set(records.iter_origin_uris(post))
    assert SEED in uris  # clean seed = primary origin
    # bare constituent forms (what a crawl finds) AND distinct pinned nav forms both recorded
    assert {"https://forum.test/thread/1?page=2", "https://forum.test/thread/1?page=3"} <= uris
    assert {
        "https://forum.test/thread/1/flat",
        "https://forum.test/thread/1/flat?page=2",
    } <= uris

    assert not [i for i in records.iter_issue_blocks(post) if i["id"] == "pagination-incomplete"]


def test_reconcile_flags_incomplete(tmp_path, monkeypatch):
    root = _init_corpus(tmp_path)
    _overlay(
        root,
        "applies_to: {host_pattern: forum.test}\n"
        "capture:\n"
        "  pagination:\n"
        "    content_selector: '.posts'\n"
        "    expect_count: {selector: '.reply-count'}\n",
    )
    _fake_capture(
        monkeypatch,
        {
            1: _page([1, 2], next_href="?page=2", reply_count="99 replies"),
            2: _page([3, 4], next_href="?page=3", reply_count="99 replies"),
            3: _page([5, 6], reply_count="99 replies"),
        },
    )

    rec = capture_mod.capture_and_ingest(SEED, corpus_root=root)
    post = records.load(rec)
    issues = [i for i in records.iter_issue_blocks(post) if i["id"] == "pagination-incomplete"]
    assert issues and issues[0]["fields"]["posts"] == 6 and issues[0]["fields"]["expected"] == 99


def test_reconcile_single_page_byte_identical(tmp_path, monkeypatch):
    root = _init_corpus(tmp_path)
    _overlay(root, "applies_to: {host_pattern: forum.test}\ncapture: {pagination: true}\n")
    html1 = _page([1, 2])  # no rel=next -> single page
    _fake_capture(monkeypatch, {1: html1})

    rec = capture_mod.capture_and_ingest(SEED, corpus_root=root)
    assert rec is not None
    # The record id is blake3 of the verbatim page-1 bytes (no BeautifulSoup round-trip).
    ref = tmp_path / "ref.html"
    ref.write_text(html1, encoding="utf-8")
    assert rec.stem == hashing.hash_file(ref)["blake3"]

    post = records.load(rec)
    assert "pagination" not in list(records.iter_origin_blocks(post))[-1]["fields"]
    assert not list(records.iter_issue_blocks(post))


# ---------- crawl frontier exclusion ---------- #


def test_expand_excludes_paginated_constituents(tmp_path, capsys):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    rid = "ab" * 32
    art_html = (
        "<html><body>"
        '<a href="https://forum.test/thread/1?page=2">next page</a>'
        '<a href="https://forum.test/thread/9">other thread</a>'
        "</body></html>"
    )
    art = paths.artifact_path(root, rid, "html")
    paths.ensure_parent(art)
    art.write_text(art_html, encoding="utf-8")
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(
        post,
        uri=["https://forum.test/thread/1", "https://forum.test/thread/1?page=2"],
        snapshot="2026-05-31T00:00:00Z",
    )
    records.dump(post, paths.record_path(root, rid))

    rc = dispatch(
        ["crawl", SEED, "--dry-run", "--depth", "1", "--corpus-root", str(root)]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "https://forum.test/thread/9" in err  # genuine content link kept
    assert "page=2" not in err  # own constituent page excluded from the frontier
