"""The local Wikipedia KB (`corpus.wiki`) over a Kiwix ZIM.

Builds a tiny fixture ZIM with `libzim.writer` (no download), then exercises full-text search,
article read, summary + best-effort QID extraction, and the canonical-id ladder. Skipped wholesale
when the `wiki` extra (libzim) is absent — mirroring how the API tests importorskip fastapi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

libzim = pytest.importorskip("libzim")

from corpus import wiki  # noqa: E402  (after importorskip)

# An article WITH an embedded Wikidata id, and one WITHOUT (to exercise the enwiki: fallback).
_ENTROPY = (
    "<html><head><title>Entropy</title>"
    '<link rel="canonical" href="https://www.wikidata.org/wiki/Q11465"></head>'
    "<body><p>Entropy is a scientific concept and measurable physical property "
    "associated with a state of disorder in thermodynamics.</p>"
    "<p>The second law applies.</p></body></html>"
)
_THERMO = (
    "<html><head><title>Thermodynamics</title></head>"
    "<body><p>Thermodynamics is a branch of physics that deals with heat, work, "
    "and temperature.</p></body></html>"
)


def _build_zim(path: Path) -> None:
    from libzim.writer import Creator, Hint, Item, StringProvider

    class _Html(Item):
        def __init__(self, p: str, t: str, c: str):
            super().__init__()
            self._p, self._t, self._c = p, t, c

        def get_path(self):
            return self._p

        def get_title(self):
            return self._t

        def get_mimetype(self):
            return "text/html"

        def get_contentprovider(self):
            return StringProvider(self._c)

        def get_hints(self):
            return {Hint.FRONT_ARTICLE: True}

    with Creator(str(path)).config_indexing(True, "eng") as creator:
        creator.add_item(_Html("Entropy", "Entropy", _ENTROPY))
        creator.add_item(_Html("Thermodynamics", "Thermodynamics", _THERMO))
        creator.set_mainpath("Entropy")
        creator.add_metadata("Title", "Test Wiki")


@pytest.fixture(scope="module")
def kb(tmp_path_factory) -> wiki.WikiKB:
    zim = tmp_path_factory.mktemp("wiki") / "test.zim"
    _build_zim(zim)
    return wiki.WikiKB(zim)


# ---------- pure helpers (no ZIM) ---------- #


def test_extract_qid_shapes():
    assert wiki._extract_qid('href="https://www.wikidata.org/wiki/Q42"') == "wikidata:Q42"
    assert wiki._extract_qid('"wgWikibaseItemId":"Q11465"') == "wikidata:Q11465"
    assert wiki._extract_qid("<p>no id here</p>") is None


def test_first_paragraph_strips_tags():
    out = wiki._first_paragraph("<div><p>Hello <b>bold</b> world that is long enough.</p></div>")
    assert out == "Hello bold world that is long enough."


def test_enwiki_id_and_url():
    assert wiki.enwiki_id("Second law of thermodynamics") == "enwiki:Second_law_of_thermodynamics"
    assert wiki._title_to_url("Entropy") == "https://en.wikipedia.org/wiki/Entropy"


# ---------- against the fixture ZIM ---------- #


def test_search_finds_by_fulltext(kb):
    hits = kb.search("disorder", limit=5)
    titles = [h.title for h in hits]
    assert "Entropy" in titles
    hit = next(h for h in hits if h.title == "Entropy")
    assert hit.id == "enwiki:Entropy"
    assert hit.url == "https://en.wikipedia.org/wiki/Entropy"


def test_search_empty_query_returns_nothing(kb):
    assert kb.search("   ") == []


def test_get_extracts_qid_and_summary(kb):
    art = kb.get("Entropy")
    assert art is not None
    assert art.qid == "wikidata:Q11465"
    assert art.id == "wikidata:Q11465"  # qid wins the canonical id
    assert art.summary.startswith("Entropy is a scientific concept")
    assert art.url == "https://en.wikipedia.org/wiki/Entropy"


def test_get_falls_back_to_enwiki_id_without_qid(kb):
    art = kb.get("Thermodynamics")
    assert art is not None
    assert art.qid is None
    assert art.id == "enwiki:Thermodynamics"


def test_get_by_enwiki_ref_resolves(kb):
    art = kb.get("enwiki:Entropy")
    assert art is not None and art.title == "Entropy"


def test_get_unknown_returns_none(kb):
    assert kb.get("No Such Article Here") is None
    assert kb.get("wikidata:Q99999") is None  # not resolvable against the ZIM alone


def test_read_returns_html(kb):
    html = kb.read("Entropy")
    assert html is not None and "<p>" in html


# ---------- unavailability ---------- #


def test_missing_zim_raises_wiki_unavailable(tmp_path):
    kb = wiki.WikiKB(tmp_path / "nope.zim")
    with pytest.raises(wiki.WikiUnavailable):
        kb.search("anything")


def test_open_kb_without_config_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ATH_WIKI_ZIM", raising=False)
    with pytest.raises(wiki.WikiUnavailable):
        wiki.open_kb(corpus_root=tmp_path)


# ---------- resolver spanning local registry + KB ---------- #


def test_resolver_local_then_wikipedia(kb, tmp_path):
    from corpus import concepts

    cdir = tmp_path / "concepts"
    cdir.mkdir()
    (cdir / "entropy_pool.yaml").write_text(
        "label: Entropy Pool\naliases: [entropy budget]\ndescription: an internal term.\n",
        encoding="utf-8",
    )
    concepts.clear_cache()
    r = concepts.ConceptResolver(corpus_root=tmp_path, kb=kb)

    # "entropy" matches both the local concept (substring) and the Wikipedia article;
    # the local hit comes first, the Wikipedia hit is included too.
    hits = r.search("entropy", limit=5)
    sources = [h.source for h in hits]
    assert sources[0] == "local"
    assert "wikipedia" in sources

    # get() delegates to the KB for a Wikipedia id.
    got = r.get("Entropy")
    assert got is not None and got.source == "wikipedia" and got.qid == "wikidata:Q11465"


# ---------- CLI (corpus wiki / corpus concept) ---------- #


def test_cli_wiki_search_and_read(kb, capsys):
    from corpus import _cli

    rc = _cli.dispatch(["wiki", "search", "disorder", "--zim", str(kb.zim_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "Entropy" in out

    rc = _cli.dispatch(["wiki", "read", "Entropy", "--zim", str(kb.zim_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "wikidata:Q11465" in out and "Entropy is a scientific" in out


def test_cli_concept_link_writes_block(kb, tmp_path):
    import frontmatter

    from corpus import _cli, derived_views, paths, records

    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    rid = "a1" * 32
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    records.append_origin_block(post, uri="https://example.com/a", snapshot="2026-06-05T00:00:00Z")
    p = paths.record_path(root, rid)
    records.dump(post, p)

    rc = _cli.dispatch(
        [
            "concept", "link", rid,
            "--concept", "Entropy",
            "--address", "el=3",
            "--quote", "entropy",
            "--corpus-root", str(root),
            "--zim", str(kb.zim_path),
        ]
    )
    assert rc == 0
    cs = derived_views.concepts(records.load(p))
    assert cs == [
        {
            "address": "el=3",
            "quote": "entropy",
            "label": "Entropy",
            "url": "https://en.wikipedia.org/wiki/Entropy",
            "concept": "wikidata:Q11465",
        }
    ]
