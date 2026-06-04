"""Overlay-declared URL equivalence — identity keys (spec §7.2, docs/URL-EQUIVALENCE.md).

Pure-function units for `urls.identity_key` / `normalize_equivalence` / `apply_rewrite_rules`,
plus integration over a tmp corpus + origin overlay (no browser/network): the recipe resolver,
the `find_by_uri` short-circuit, `add_origin_uri_alias` minimal recording, and the crawl
frontier exclusion. Opt-in is proven by the with-overlay / without-overlay contrast.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import paths, records, urls
from corpus._cli import dispatch
from corpus.capture import recipes

SEED = "https://forum.test/thread/1"

# g8board-shaped equivalence: /page-1 == bare thread; every query param is view/affiliate noise.
_EQUIV_MAP = {
    "query": "drop",
    "rules": [{"pattern": r"/page-1(?=[/?#]|$)", "replacement": ""}],
}

_OVERLAY = (
    "applies_to: {host_pattern: forum.test}\n"
    "capture:\n"
    "  url_equivalent:\n"
    "    query: drop\n"
    "    rules:\n"
    "      - {pattern: '/page-1(?=[/?#]|$)', replacement: ''}\n"
)


# ---------- pure units ---------- #


def test_identity_key_no_config_is_normalize():
    u = "HTTPS://Forum.Test/thread/1?b=2&a=1#frag"
    assert urls.identity_key(u) == urls.normalize(u)
    assert urls.identity_key(u, None) == urls.normalize(u)


def test_normalize_equivalence_shapes():
    assert urls.normalize_equivalence(None) is None
    assert urls.normalize_equivalence(False) is None
    assert urls.normalize_equivalence("nonsense") is None
    rules = [{"pattern": "a", "replacement": "b"}]
    assert urls.normalize_equivalence(rules) == {
        "query": "keep",
        "rules": rules,
        "on_rewritten": False,
    }
    assert urls.normalize_equivalence({"query": "drop", "on_rewritten": True}) == {
        "query": "drop",
        "rules": [],
        "on_rewritten": True,
    }
    assert urls.normalize_equivalence({"query": "weird"})["query"] == "keep"  # unknown → keep


def test_apply_rewrite_rules():
    rules = [{"pattern": "a", "replacement": "X"}, {"pattern": "b", "replacement": "Y"}]
    assert urls.apply_rewrite_rules("ab", rules) == "XY"
    assert urls.apply_rewrite_rules("z", rules) == "z"  # no match
    assert urls.apply_rewrite_rules("z", None) == "z"  # no rules
    assert urls.apply_rewrite_rules("z", "garbage") == "z"  # non-list ignored
    assert urls.apply_rewrite_rules("z", [{"pattern": "(", "replacement": ""}]) == "z"  # bad regex


def test_identity_key_query_drop_strips_all_params():
    bare = "https://forum.test/thread/1/page-2"
    noisy = "https://forum.test/thread/1/page-2?nested_view=1&affiliate-data=x"
    assert urls.identity_key(noisy, _EQUIV_MAP) == "https://forum.test/thread/1/page-2"
    assert urls.identity_key(noisy, _EQUIV_MAP) == urls.identity_key(bare, _EQUIV_MAP)


def test_identity_key_page1_folds_to_bare():
    bare = "https://forum.test/thread/1"
    page1 = "https://forum.test/thread/1/page-1"
    assert urls.identity_key(page1, _EQUIV_MAP) == urls.identity_key(bare, _EQUIV_MAP)
    # bare-list (rules-only) form works too
    rules_only = [{"pattern": r"/page-1(?=[/?#]|$)", "replacement": ""}]
    assert urls.identity_key(page1, rules_only) == urls.normalize(bare)


def test_identity_key_keeps_distinct_pages():
    a = urls.identity_key("https://forum.test/thread/1/page-2?nested_view=1", _EQUIV_MAP)
    b = urls.identity_key("https://forum.test/thread/1/page-3?nested_view=1", _EQUIV_MAP)
    assert a != b  # only page-1 folds; page-2 ≠ page-3


def test_identity_key_on_rewritten_uses_fetched_form():
    eq = {"on_rewritten": True}
    rw = [{"pattern": r"/v/(.+)$", "replacement": r"/article/\1"}]
    assert urls.identity_key("https://h.test/v/123", eq, url_rewrite=rw) == "https://h.test/article/123"
    # without on_rewritten, identity stays on the inbound form
    assert urls.identity_key("https://h.test/v/123", {}, url_rewrite=rw) == "https://h.test/v/123"


def test_identity_key_bad_regex_is_skipped_not_raised():
    eq = [{"pattern": "([", "replacement": ""}]  # invalid regex
    assert urls.identity_key("https://h.test/p", eq) == urls.normalize("https://h.test/p")


def test_identity_key_tidies_dangling_delimiter():
    # a rule that strips a param's value but leaves the lone '?' — tidy collapses it
    eq = [{"pattern": "utm=[^&]*", "replacement": ""}]
    assert urls.identity_key("https://h.test/p?utm=1", eq) == "https://h.test/p"


# ---------- integration: corpus + overlay ---------- #


def _corpus(tmp_path: Path, *, overlay: str | None, name: str = "c") -> Path:
    root = tmp_path / name
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    if overlay is not None:
        d = root / "schema" / "origin" / "web"
        d.mkdir(parents=True, exist_ok=True)
        (d / "forum.test.yaml").write_text(overlay, encoding="utf-8")
    return root


def _record(root: Path, record_id: str, uri, *, touch_id: str = "t") -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=record_id, touch_id=touch_id)
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, record_id))


def test_url_equivalent_for_url_resolves_map_and_list(tmp_path):
    root = _corpus(tmp_path, overlay=_OVERLAY)
    assert recipes.url_equivalent_for_url(root, SEED) == {
        "query": "drop",
        "rules": [{"pattern": "/page-1(?=[/?#]|$)", "replacement": ""}],
    }
    # the recipe-aware resolver honors it
    key = recipes.identity_key_for_url(root, SEED + "/page-1?nested_view=1")
    assert key == urls.normalize(SEED)

    list_overlay = (
        "applies_to: {host_pattern: forum.test}\n"
        "capture:\n"
        "  url_equivalent:\n"
        "    - {pattern: '/page-1', replacement: ''}\n"
    )
    root2 = _corpus(tmp_path, overlay=list_overlay, name="c2")
    assert recipes.url_equivalent_for_url(root2, SEED) == [
        {"pattern": "/page-1", "replacement": ""}
    ]


def test_find_by_uri_matches_equivalent_with_overlay(tmp_path):
    root = _corpus(tmp_path, overlay=_OVERLAY)
    _record(root, "ab" * 32, "https://forum.test/thread/1/page-2")
    _record(root, "cd" * 32, "https://forum.test/thread/2")
    # query-noise variant of a stored page matches
    noisy = "https://forum.test/thread/1/page-2?nested_view=1"
    assert records.find_by_uri(noisy, corpus_root=root) == "ab" * 32
    # /page-1 of a bare thread matches the bare stored form
    assert records.find_by_uri("https://forum.test/thread/2/page-1", corpus_root=root) == "cd" * 32


def test_find_by_uri_opt_in_misses_without_overlay(tmp_path):
    root = _corpus(tmp_path, overlay=None)  # no url_equivalent declared
    _record(root, "ab" * 32, "https://forum.test/thread/2")
    # without equivalence rules, /page-1 is a distinct resource (string identity) → miss
    assert records.find_by_uri("https://forum.test/thread/2/page-1", corpus_root=root) is None
    # the conservative `normalize` still matches (query order / trailing differences)
    assert records.find_by_uri("https://forum.test/thread/2", corpus_root=root) == "ab" * 32


def test_add_origin_uri_alias_minimal_with_corpus_root(tmp_path):
    root = _corpus(tmp_path, overlay=_OVERLAY)
    fm = records.stub_frontmatter(record_id="ab" * 32, touch_id="t")
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(
        post, uri="https://forum.test/thread/1/page-2", snapshot="2026-06-04T00:00:00Z"
    )
    # an equivalent spelling is NOT appended when corpus_root is given (minimal origin block)
    noisy = "https://forum.test/thread/1/page-2?nested_view=1"
    distinct = "https://forum.test/thread/1/page-3"
    assert records.add_origin_uri_alias(post, noisy, corpus_root=root) is False
    assert records.add_origin_uri_alias(post, distinct, corpus_root=root) is True  # distinct page
    # without corpus_root the dedup is exact-string (back-compat) → the variant appends
    assert records.add_origin_uri_alias(post, noisy) is True


def test_expand_excludes_equivalent_variant_of_own_uri(tmp_path, capsys):
    root = _corpus(tmp_path, overlay=_OVERLAY)
    rid = "ab" * 32
    art_html = (
        "<html><body>"
        '<a href="https://forum.test/thread/1/page-1?nested_view=1">same thread (equivalent)</a>'
        '<a href="https://forum.test/thread/9">other thread</a>'
        "</body></html>"
    )
    art = paths.artifact_path(root, rid, "html")
    paths.ensure_parent(art)
    art.write_text(art_html, encoding="utf-8")
    _record(root, rid, "https://forum.test/thread/1", touch_id="corpus.ingest@0.1.0")

    rc = dispatch(["crawl", SEED, "--dry-run", "--depth", "1", "--corpus-root", str(root)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "https://forum.test/thread/9" in err  # genuine content link kept
    assert "page-1" not in err and "nested_view" not in err  # equivalent of own uri excluded
