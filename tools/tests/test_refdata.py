"""The `refdata` reference-dataset resolver (spec/ledger.md §6.5): snapshot
materialization (`path:` override vs. corpus artifact store, spec/athenaeum.md
§2.3 v18) and the `zim` format adapter. All tests need the optional `libzim`
dependency (the `zim` extra) — gated at module scope so environments without
it report a clean skip, not a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

libzim = pytest.importorskip("libzim")

import libzim.writer as zw  # noqa: E402

import refdata  # noqa: E402
from ath.manifest import Reference, Snapshot  # noqa: E402
from refdata import (  # noqa: E402
    AdapterUnavailable,
    EntryNotFound,
    MirrorCorrupt,
    MirrorUnavailable,
    UnknownTag,
    adapter_available,
    materialize,
    resolve,
    search,
)

_HOME_HTML = "<html><body><h1>Home</h1><p>Hello   world,\nthis is home.</p></body></html>"
_OTHER_HTML = "<html><body><p>Another article entirely.</p></body></html>"
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class _Item(zw.Item):
    def __init__(self, path: str, title: str, content: str | bytes, mimetype: str):
        super().__init__()
        self._path = path
        self._title = title
        self._content = content
        self._mimetype = mimetype

    def get_path(self) -> str:
        return self._path

    def get_title(self) -> str:
        return self._title

    def get_mimetype(self) -> str:
        return self._mimetype

    def get_contentprovider(self) -> zw.ContentProvider:
        return zw.StringProvider(self._content)

    def get_hints(self) -> dict:
        return {zw.Hint.FRONT_ARTICLE: 1}


def _build_zim(path: Path) -> None:
    """A tiny fixture ZIM: two HTML articles, one redirect, one non-text
    (image) entry — enough surface for exact-path resolution, redirect
    following, HTML->text extraction, and the no-text-projection case."""
    with zw.Creator(str(path)) as creator:
        creator.add_item(_Item("home", "Home", _HOME_HTML, "text/html"))
        creator.add_item(_Item("other", "Other", _OTHER_HTML, "text/html"))
        creator.add_item(_Item("picture.png", "A picture", _PNG_BYTES, "image/png"))
        creator.add_redirection("redirect-to-home", "Redirect", "home", {})
        creator.set_mainpath("home")


@pytest.fixture
def zim_path(tmp_path: Path) -> Path:
    p = tmp_path / "mirror.zim"
    _build_zim(p)
    return p


def _ref(
    tag: str, artifact: str, *, path: str | None = None, latest: str | None = None
) -> Reference:
    return Reference(
        dataset="testwiki", description="test mirror", adapter="zim",
        latest=latest or tag, snapshots={tag: Snapshot(artifact=artifact, path=path)},
    )


def test_adapter_available() -> None:
    assert adapter_available("zim") is True
    assert adapter_available("no-such-adapter") is False


def test_resolve_by_exact_path(zim_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(zim_path))
    entry = resolve(ref, "other")
    assert entry.dataset == "testwiki"
    assert entry.tag == "t"
    assert entry.artifact == "a" * 64
    assert entry.native_id == "other"
    assert entry.canonical_id == "other"
    assert entry.title == "Other"
    assert entry.content_type == "text/html"
    assert entry.text == "Another article entirely."


def test_resolve_follows_redirect_reports_canonical_id(zim_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(zim_path))
    entry = resolve(ref, "redirect-to-home")
    assert entry.native_id == "redirect-to-home"
    assert entry.canonical_id == "home"
    assert entry.title == "Home"
    assert "Hello world, this is home." in entry.text


def test_html_to_text_collapses_whitespace(zim_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(zim_path))
    entry = resolve(ref, "home")
    assert "  " not in entry.text
    assert "\n" not in entry.text


def test_non_text_entry_has_no_text_projection(zim_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(zim_path))
    entry = resolve(ref, "picture.png")
    assert entry.content_type == "image/png"
    assert entry.text is None


def test_entry_not_found(zim_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(zim_path))
    with pytest.raises(EntryNotFound):
        resolve(ref, "does-not-exist")


def test_mirror_unavailable_when_neither_path_nor_store_has_bytes() -> None:
    ref = _ref("t", "a" * 64)  # no path:, no corpora_roots given
    assert materialize(ref, "t") is None
    with pytest.raises(MirrorUnavailable):
        resolve(ref, "home", corpora_roots=())


def test_path_override_wins_over_store(tmp_path: Path) -> None:
    """Two distinct mirrors — one entry each, disjoint ids — prove the
    override is actually preferred rather than merely present: resolving the
    override-only id succeeds, so the store copy (which lacks that id) was
    never consulted."""
    override_zim = tmp_path / "override.zim"
    with zw.Creator(str(override_zim)) as creator:
        creator.add_item(_Item("only-in-override", "Override", "override content", "text/plain"))
        creator.set_mainpath("only-in-override")

    artifact = "b" * 64
    store_root = tmp_path / "corpus"
    store_zim = store_root / "artifacts" / artifact[:2] / f"{artifact}.zim"
    store_zim.parent.mkdir(parents=True)
    with zw.Creator(str(store_zim)) as creator:
        creator.add_item(_Item("only-in-store", "Store", "store content", "text/plain"))
        creator.set_mainpath("only-in-store")

    ref = _ref("t", artifact, path=str(override_zim))
    resolved_path = materialize(ref, "t", corpora_roots=(store_root,))
    assert resolved_path == override_zim
    entry = resolve(ref, "only-in-override", corpora_roots=(store_root,))
    assert entry.text == "override content"


# --- search ----------------------------------------------------------------
#
# `zim_path` (above) is built with a plain `zw.Creator` — no
# `config_indexing(True, "eng")` — so its archive carries a title index
# (built unconditionally from each item's non-empty title, on a text/*-ish
# entry) but *not* a full-text index. `search()` therefore exercises the
# suggestion (title) path here, never the full-text fallback; a fixture that
# needs the fallback path builds its own archive with `config_indexing` set
# before the `Creator` is entered (libzim raises if it's set after).


def test_search_returns_hit_by_title_word(zim_path: Path) -> None:
    ref = _ref("t", "a" * 64, path=str(zim_path))
    hits = search(ref, "Home")
    assert any(h.native_id == "home" and h.title == "Home" for h in hits)


def test_search_limit_respected(tmp_path: Path) -> None:
    p = tmp_path / "many.zim"
    with zw.Creator(str(p)) as creator:
        for i in range(5):
            creator.add_item(
                _Item(f"widget-{i}", f"Widget {i}", f"Widget number {i}.", "text/plain")
            )
        creator.set_mainpath("widget-0")
    ref = _ref("t", "b" * 64, path=str(p))
    hits = search(ref, "Widget", limit=2)
    assert len(hits) == 2


class _UnindexedItem(zw.Item):
    """An item with no title, a non-text mimetype, and *no* FRONT_ARTICLE
    hint — unlike `_Item` above, which always sets that hint (and so is
    title-indexed even with an empty title). Empirically, dropping the hint
    is what actually suppresses the title index; content merely being
    non-text is not enough by itself."""

    def get_path(self) -> str:
        return "blob"

    def get_title(self) -> str:
        return ""

    def get_mimetype(self) -> str:
        return "image/png"

    def get_contentprovider(self) -> zw.ContentProvider:
        return zw.StringProvider(_PNG_BYTES)

    def get_hints(self) -> dict:
        return {}


def test_search_no_index_returns_empty_list(tmp_path: Path) -> None:
    """No FRONT_ARTICLE hint + empty title + non-text content builds neither
    a title nor a full-text index (empirically verified against the
    installed libzim: `Archive.has_title_index` and `has_fulltext_index` both
    False) — absence of an index is a property of the mirror, not a search
    failure."""
    p = tmp_path / "noindex.zim"
    with zw.Creator(str(p)) as creator:
        creator.add_item(_UnindexedItem())
        creator.set_mainpath("blob")
    ref = _ref("t", "c" * 64, path=str(p))
    assert search(ref, "anything") == []


def test_search_unknown_tag() -> None:
    ref = _ref("t", "a" * 64)
    with pytest.raises(UnknownTag):
        search(ref, "home", tag="nope")


def test_search_adapter_unavailable() -> None:
    ref = Reference(
        dataset="testwiki", description="test", adapter="not-a-real-adapter",
        latest="t", snapshots={"t": Snapshot(artifact="a" * 64)},
    )
    with pytest.raises(AdapterUnavailable):
        search(ref, "home")


def test_search_mirror_unavailable() -> None:
    ref = _ref("t", "a" * 64)  # no path:, no corpora_roots given
    with pytest.raises(MirrorUnavailable):
        search(ref, "home", corpora_roots=())


def test_store_fallback_when_no_path_override(tmp_path: Path) -> None:
    """No `path:` on the snapshot — materialize falls through to the corpus
    artifact store, fabricated here per the on-disk shape
    `artifacts/<shard>/<hash>.<ext>` (`corpus/paths.py`)."""
    artifact = "c" * 64
    store_root = tmp_path / "corpus"
    store_zim = store_root / "artifacts" / artifact[:2] / f"{artifact}.zim"
    store_zim.parent.mkdir(parents=True)
    with zw.Creator(str(store_zim)) as creator:
        creator.add_item(_Item("home", "Home", _HOME_HTML, "text/html"))
        creator.set_mainpath("home")

    ref = _ref("t", artifact)  # no path: override
    resolved_path = materialize(ref, "t", corpora_roots=(store_root,))
    assert resolved_path == store_zim
    entry = resolve(ref, "home", corpora_roots=(store_root,))
    assert entry.title == "Home"


# --- corrupted mirror (increment 2) -----------------------------------------


def test_mirror_corrupt_on_resolve_and_search(tmp_path: Path) -> None:
    """Garbage bytes at a `.zim`-named path — standing in for a truncated
    mid-download or genuinely corrupted mirror (empirically reproduced
    against a real half-downloaded ZIM: libzim's `Archive()` construction
    raises a raw `RuntimeError`, wrapped as `MirrorCorrupt` by the zim
    adapter's `open_archive`). Both `resolve` and `search` share the same
    `_resolve_handle` preamble, so both must raise it identically; the
    handle cache must hold no entry for the failed path afterward — a
    later retry (mirror finishes downloading) should open fresh, not
    replay the cached failure."""
    bad = tmp_path / "corrupt.zim"
    bad.write_bytes(b"not a zim file, just garbage" * 100)
    ref = _ref("t", "e" * 64, path=str(bad))
    cache_key = ("zim", str(bad.resolve()))

    with pytest.raises(MirrorCorrupt):
        resolve(ref, "home")
    assert cache_key not in refdata._HANDLES

    with pytest.raises(MirrorCorrupt):
        search(ref, "home")
    assert cache_key not in refdata._HANDLES


# --- search modes: blend / suggest / fulltext (increment 1) ----------------
#
# `zim_path` (module-top) carries a title index but no full-text index — the
# blend/suggest cases against it above already prove blend degrades to the
# title tier alone when full-text is absent. The fixture below is built
# *with* `config_indexing(True, "eng")` (must run before the `Creator`
# context is entered — libzim raises if set after) so it carries both
# indexes, exercising the tiers this dispatch adds.


def _build_indexed_zim(path: Path) -> None:
    """Two articles: `home`'s title contains "Home" and its body separately
    contains "gadget" nowhere; `gizmo`'s title carries no search-relevant
    word at all, but its body repeats "gadget" — a body-only match the
    title (suggestion) index cannot find, only full-text can. `home`'s body
    also says "Home" again, so a title-word query for "Home" hits `home` via
    *both* tiers — the blend dedupe case."""
    creator = zw.Creator(str(path))
    creator.config_indexing(True, "eng")
    with creator as c:
        c.add_item(_Item(
            "home", "Home Base",
            "<html><body><p>Hello world, this is home, the home page.</p></body></html>",
            "text/html",
        ))
        c.add_item(_Item(
            "gizmo", "Totally Unrelated Title",
            "<html><body><p>This page mentions gadget several times: gadget, "
            "gadget, gadget.</p></body></html>",
            "text/html",
        ))
        c.set_mainpath("home")


@pytest.fixture
def indexed_zim_path(tmp_path: Path) -> Path:
    p = tmp_path / "indexed.zim"
    _build_indexed_zim(p)
    return p


def test_search_blend_surfaces_body_only_match(indexed_zim_path: Path) -> None:
    ref = _ref("t", "f" * 64, path=str(indexed_zim_path))
    hits = search(ref, "gadget", mode="blend")
    assert any(h.native_id == "gizmo" for h in hits)


def test_search_suggest_excludes_body_only_match(indexed_zim_path: Path) -> None:
    """The same body-only word, `mode="suggest"` — title index has no
    match, so this must come back empty, unlike blend above."""
    ref = _ref("t", "f" * 64, path=str(indexed_zim_path))
    assert search(ref, "gadget", mode="suggest") == []


def test_search_fulltext_mode_finds_body_only_match(indexed_zim_path: Path) -> None:
    ref = _ref("t", "f" * 64, path=str(indexed_zim_path))
    hits = search(ref, "gadget", mode="fulltext")
    assert any(h.native_id == "gizmo" for h in hits)


def test_search_fulltext_mode_on_no_fulltext_archive_returns_empty(zim_path: Path) -> None:
    """`zim_path` (module-top fixture) carries no full-text index (no
    `config_indexing` at write time) — `mode="fulltext"` there is a
    legitimate absence, `[]`, not an error."""
    ref = _ref("t", "a" * 64, path=str(zim_path))
    assert search(ref, "home", mode="fulltext") == []


def test_search_blend_dedupes_title_hit_first(indexed_zim_path: Path) -> None:
    """"Home" is a title word (suggestion match) *and* appears in `home`'s
    body (full-text match too) — both tiers find the same path. Blend must
    return it once, and — since suggestion hits are placed ahead of
    full-text hits in the pre-dedupe concatenation — it must be first."""
    ref = _ref("t", "f" * 64, path=str(indexed_zim_path))
    hits = search(ref, "Home", mode="blend")
    home_hits = [h for h in hits if h.native_id == "home"]
    assert len(home_hits) == 1
    assert hits[0].native_id == "home"


def test_search_invalid_mode_raises(indexed_zim_path: Path) -> None:
    ref = _ref("t", "f" * 64, path=str(indexed_zim_path))
    with pytest.raises(ValueError):
        search(ref, "home", mode="not-a-real-mode")
