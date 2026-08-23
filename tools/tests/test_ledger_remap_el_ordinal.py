"""`ath ledger remap-el-ordinal` — the anchor-side v35 remap (`ledger.remap_el_ordinal`).

The mapping itself is `corpus.remap_el_ordinal.map_dotted_value_to_ordinal` /
`map_legacy_value_to_ordinal` (pinned in test_el_ordinal_remap_35); what this file pins is
the LEDGER grammar and the manifest-driven generation record around it: only el-leading
param strings rewrite, chained ops ride along, a manifest is REQUIRED (unlike a bare
eligibility set, it must carry each record's source GENERATION — a fact the record's own
post-migration stamp can no longer answer), and a held/skipped/un-migrated record's
anchors are left exactly as stored.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pytest
from bs4 import BeautifulSoup, Tag

from corpus import functional_uri as furi
from corpus import paths as corpus_paths
from corpus import records, schemas, segments
from corpus import remap_el_ordinal as corpus_remap
from corpus.remap_el_ordinal import RemapHold
from corpus.segments import Segment
from corpus.store import LocalArtifactStore
from corpus.transforms.html import (
    legacy_is_addressable,
    path_root,
    resolve_element_path,
    resolve_ordinal,
)
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.remap_el_ordinal import (
    _Pairing,
    _rewrite_params,
    load_migration_generations,
    remap_ledger_el_ordinal,
)

_DOC = (
    "<html><body><main>"
    "<div><h1>T</h1><p>a</p><p>b</p></div>"
    "<div><p>c</p></div>"
    "<div><p>d</p></div>"
    "</main></body></html>"
)

#: The endpoints' nearest common ancestor is <body> itself — no `el=[a-b]` spelling.
_ROOT_LEVEL_DOC = (
    "<html><body><div><h1>T</h1><p>a</p><p>b</p></div><div><p>c</p></div></body></html>"
)


def _dotted_pairing(doc: str = _DOC):
    soup = BeautifulSoup(doc, "html.parser")
    return corpus_remap.ContainerPairing(generation="dotted", old_elements=[], root=path_root(soup))


def _legacy_pairing(doc: str = _DOC):
    soup = BeautifulSoup(doc, "html.parser")
    old = [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]
    return corpus_remap.ContainerPairing(
        generation="legacy", old_elements=old, root=path_root(soup)
    )


# ---------- pure mapping (both source generations) ---------- #


def test_el_leading_anchor_rewrites_and_carries_ops_dotted():
    pairing = _dotted_pairing()
    # main(1) div(1.1) h1(1.1.1) p(1.1.2) p(1.1.3); div(1.2) p(1.2.1); div(1.3) p(1.3.1)
    assert _rewrite_params("el=1.1.1&bbox=0,0,1,1", pairing)[0].startswith("el=")
    new, form = _rewrite_params("el=1.1.[2-3]", pairing)
    assert form == "sibling" and new.startswith("el=[")


def test_el_leading_anchor_rewrites_legacy():
    pairing = _legacy_pairing()
    # legacy: h1(1), p a(2), p b(3), p c(4), p d(5)
    _new, form = _rewrite_params("el=4", pairing)
    assert form == "point"
    new2, form2 = _rewrite_params("el=2-3", pairing)
    assert form2 == "sibling" and new2.startswith("el=[")


def test_non_el_leading_strings_stay_untouched():
    pairing = _legacy_pairing()
    assert _rewrite_params("page=3", pairing) is None
    assert _rewrite_params("spine=2&el=3", pairing) is None  # the EPUB axis is not ours
    assert _rewrite_params("turn=5", pairing) is None


def test_root_level_interval_holds_for_deliberate_rescope():
    pairing = _legacy_pairing(_ROOT_LEVEL_DOC)
    with pytest.raises(RemapHold, match=r"no .*sibling\-range spelling"):
        _rewrite_params("el=1-4", pairing)


# ---------- the manifest is the generation record, not just an eligibility set ---------- #


class _StubJoin:
    def holders(self, record_hash):
        return [object()]


def test_manifest_supplies_eligibility_and_generation(tmp_path):
    m = tmp_path / "remap.jsonl"
    m.write_text(
        "\n".join([
            json.dumps({"record": "aaa", "changed": True, "generation": "dotted"}),
            json.dumps({"record": "bbb", "changed": True, "generation": "legacy"}),
            json.dumps({"record": "ccc", "changed": False, "hold": "addresses alias"}),
            json.dumps({"record": "ddd", "changed": False, "skipped": "already ordinal"}),
            "",
        ]),
        encoding="utf-8",
    )
    generations = load_migration_generations([m])
    assert generations == {"aaa": "dotted", "bbb": "legacy"}

    pairings = _Pairing(_StubJoin(), generations)
    assert pairings.get("ccc") == "NOT-MIGRATED"
    assert pairings.get("ddd") == "NOT-MIGRATED"
    assert pairings.get("never-seen") == "NOT-MIGRATED"


# ---------- end to end: a real corpus + fact file ---------- #


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_dotted_record(root: Path, name: str) -> str:
    from corpus import hashing

    src = root / f"{name}.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html", fields={"addressing": {"parser": "html.parser", "elements": 11}}
    )
    records.append_origin_block(post, uri=f"https://x.test/{name}", snapshot="2026-01-01T00:00:00Z")
    post.content = segments.emit([
        Segment(atom="text", address="el=1.1.1", body="T"),
    ])
    records.dump(post, corpus_paths.record_path(root, rid))
    return rid


def _write_fact(ledger_root: Path, fact_id: str, record_hash: str, anchor: str) -> Path:
    facts_dir = ledger_root / "facts" / "test"
    facts_dir.mkdir(parents=True, exist_ok=True)
    fact = {
        "id": fact_id,
        "sources": {"s1": {"record": record_hash}},
        "claims": [
            {"field": "x", "value": "y",
             "evidence": [{"source": "s1", "anchor": anchor, "kind": "direct"}]}
        ],
    }
    p = facts_dir / f"{fact_id}.json"
    p.write_text(json.dumps(fact, indent=2) + "\n", encoding="utf-8")
    return p


def test_end_to_end_anchor_rewrite_after_the_corpus_remap(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_dotted_record(root, "e2e")
    _, rf = corpus_paths.resolve_record(root, rid)

    # Run the CORPUS remap first — its manifest is what the ledger pass needs.
    manifest = tmp_path / "remap.jsonl"
    report = corpus_remap.remap_record(rf, root)
    assert report.changed
    manifest.write_text(json.dumps({
        "record": report.record_id, "changed": report.changed,
        "generation": report.generation,
    }) + "\n", encoding="utf-8")
    rf.write_text(report.new_text, encoding="utf-8")
    assert records.el_addressing(records.load(rf))["scheme"] == "ordinal"

    # Now the ledger side: an evidence anchor citing the record's DOTTED address (the
    # anchor need not be one the record itself stores — that's the whole point of an
    # anchor being independently addressable).
    ledger_root = tmp_path / "ledger"
    fact_path = _write_fact(ledger_root, "fact1", rid, "el=1.1.2")  # p "a"

    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    generations = load_migration_generations([manifest])
    result = remap_ledger_el_ordinal(ledger_root, join, apply=True, generations=generations)
    assert not result.holds
    assert result.skipped_not_migrated == 0
    assert len(result.rewrites) == 1

    rewritten = json.loads(fact_path.read_text())
    new_anchor = rewritten["claims"][0]["evidence"][0]["anchor"]
    assert new_anchor != "el=1.1.2" and new_anchor.startswith("el=")
    # The rewritten ordinal resolves, on the SAME artifact, to the identical element the
    # dotted anchor named.
    soup = BeautifulSoup(_DOC, "html.parser")
    root_el = path_root(soup)
    old_tag = resolve_element_path(root_el, furi.parse_el_path("1.1.2"))
    new_ordinal = int(new_anchor[3:])
    assert resolve_ordinal(root_el, new_ordinal) is old_tag


def test_anchor_on_a_not_yet_migrated_record_is_skipped_not_guessed(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_dotted_record(root, "unmigrated")
    ledger_root = tmp_path / "ledger"
    _write_fact(ledger_root, "fact2", rid, "el=1.1.2")

    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    # No manifest entry for `rid` at all — it has not been migrated by the corpus pass.
    result = remap_ledger_el_ordinal(ledger_root, join, apply=True, generations={})
    assert not result.rewrites
    assert result.skipped_not_migrated == 1
    assert not result.holds

    # Quote/anchor text on disk is untouched.
    fact = json.loads((ledger_root / "facts" / "test" / "fact2.json").read_text())
    assert fact["claims"][0]["evidence"][0]["anchor"] == "el=1.1.2"
