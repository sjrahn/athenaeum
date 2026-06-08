"""The `concept` annotation namespace (spec §4.3.3.4) + the `concepts` derived view (§9.7).

Covers: concept context-block round-trip (segment-scoped mention + record-scoped aboutness);
the `concepts()` projection and that it never leaks into `issues()`; the `iter_concept_blocks`
projection; and that `concept` resolves as a known context namespace (no unknown-namespace lint).
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import concepts, derived_views, lint, paths, records, segments

RID = "a1" * 32

# A span-level mention (the YouTube-chip case) and a record-level aboutness block.
_MENTION = {
    "address": "time_range=212-240",
    "quote": "the second law of thermodynamics",
    "concept": "wikidata:Q11465",
    "label": "Second law of thermodynamics",
    "url": "https://en.wikipedia.org/wiki/Second_law_of_thermodynamics",
}
_ABOUTNESS = {
    "concept": "wikidata:Q11473",
    "label": "Thermodynamics",
    "url": "https://en.wikipedia.org/wiki/Thermodynamics",
}


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _post(rid: str = RID) -> frontmatter.Post:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    records.append_origin_block(post, uri="https://example.com/a", snapshot="2026-06-05T00:00:00Z")
    post.metadata["status"] = "draft"
    return post


def _with_concepts() -> frontmatter.Post:
    post = _post()
    records.append_context_block(post, namespace="concept", id="concept", fields=dict(_MENTION))
    records.append_context_block(post, namespace="concept", id="concept", fields=dict(_ABOUTNESS))
    return post


def _lint(post, root):
    return lint.lint(post, segments.iter_blocks(post.content or ""), root)


# ---------- parse / emit round-trip ---------- #


def test_concept_block_round_trips(tmp_path):
    root = _corpus(tmp_path)
    post = _with_concepts()
    p = paths.record_path(root, RID)
    records.dump(post, p)
    raw = p.read_text("utf-8")
    assert "<!--context concept" in raw  # bare namespace collapse (id == namespace)
    assert "/concept" not in raw  # never qualified as concept/concept

    loaded = records.load(p)
    ctx = [c for c in records.iter_context_blocks(loaded) if c["namespace"] == "concept"]
    assert [c["fields"] for c in ctx] == [_MENTION, _ABOUTNESS]


# ---------- derived view ---------- #


def test_concepts_view_projects_concept_namespace(tmp_path):
    post = _with_concepts()
    # Also add an issue + a reference, to prove the projection is namespace-scoped.
    records.append_issue_block(
        post, id="paywall", severity="warning", resolution="open", detector="corpus.ingest@0.1.0"
    )
    records.append_context_block(
        post, namespace="reference", id="reference", fields={"attribution_text": "Capital"}
    )
    assert derived_views.concepts(post) == [_MENTION, _ABOUTNESS]
    # concepts() must not leak into issues(), and vice-versa.
    assert all(c.get("concept") for c in derived_views.concepts(post))
    assert derived_views.issues(post) == [
        {
            "id": "paywall",
            "severity": "warning",
            "resolution": "open",
            "detector": "corpus.ingest@0.1.0",
        }
    ]


def test_iter_concept_blocks_shape(tmp_path):
    post = _with_concepts()
    blocks = list(records.iter_concept_blocks(post))
    assert blocks == [
        {"subtype": None, "fields": _MENTION},
        {"subtype": None, "fields": _ABOUTNESS},
    ]


def test_mention_vs_aboutness_scope():
    post = _with_concepts()
    cs = derived_views.concepts(post)
    mentions = [c for c in cs if "address" in c]
    aboutness = [c for c in cs if "address" not in c]
    assert len(mentions) == 1 and mentions[0]["concept"] == "wikidata:Q11465"
    assert len(aboutness) == 1 and aboutness[0]["concept"] == "wikidata:Q11473"


# ---------- lint: concept is a known, bundled namespace ---------- #


def test_concept_namespace_is_known(tmp_path):
    root = _corpus(tmp_path)
    post = _with_concepts()
    findings = _lint(post, root)
    assert not any(f.rule_id == "context-namespace-unknown" for f in findings)


# ---------- corpus-local custom concepts (concepts.py, no KB) ---------- #


def _write_local(root: Path) -> None:
    cdir = root / "concepts"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "athenaeum.yaml").write_text(
        "label: Athenaeum\n"
        "aliases: [the corpus system, ath]\n"
        "description: The local knowledge system this corpus belongs to.\n",
        encoding="utf-8",
    )
    # id derived from same_as cross-link; slug from filename.
    (cdir / "sjrahn.yaml").write_text(
        "id: local:sjrahn\nlabel: sjrahn\nsame_as: wikidata:Q0\n",
        encoding="utf-8",
    )
    concepts.clear_cache()


def test_load_local_concepts(tmp_path):
    root = _corpus(tmp_path)
    _write_local(root)
    reg = concepts.load_local_concepts(root)
    assert set(reg) == {"local:athenaeum", "local:sjrahn"}
    assert reg["local:athenaeum"].aliases == ("the corpus system", "ath")


def test_resolver_local_search_first_and_get(tmp_path):
    root = _corpus(tmp_path)
    _write_local(root)
    r = concepts.ConceptResolver(corpus_root=root, kb=None)
    hits = r.search("ath", limit=5)
    assert hits and hits[0].source == "local" and hits[0].id == "local:athenaeum"

    got = r.get("local:sjrahn")
    assert got is not None and got.source == "local" and got.qid == "wikidata:Q0"
    # A Wikipedia id with no KB resolves to nothing, gracefully.
    assert r.get("wikidata:Q42") is None
    assert r.get("local:nope") is None
