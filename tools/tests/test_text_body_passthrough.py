"""A textual record's body is its own text, and a record-level quote into it verifies
(arbre-ath-steven, 2026-09-28: `corpus body` failed on every `text/markdown` record, so
`ath ledger verify` failed each record-level cite into the owner statements).

- spec/corpus.md §6.2 and its per-format inventory: a markdown or plain record's `body` is
  passthrough. Any `text/*` type with no id-keyed drafter or declared strategy now drafts as
  its own verbatim text (`corpus.draft.text`).
- spec/ledger.md §6.3 and §13.2.4: on a `raw`-surface record, a record-wide quote is
  legitimate. A record that stores no rendering (formless, or `form/passthrough`) carries its
  text only in the derived body, so a record-level quote is checked there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from corpus import derive, records, schemas
from corpus._cli import ingest
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.verify import verify_ledger

_STATEMENT = "# Note\n\n<!-- not structure -->\n5616 is my triangle card with my phone\n"


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "capture").mkdir()
    (root / "schema" / "mime" / "text").mkdir(parents=True)
    (root / "schema" / "mime" / "text" / "text_markdown.yaml").write_text(
        "description: Markdown.\napplies_to:\n  content_types: [text/markdown]\n"
        "whole_address: admissible\nform:\n  id: passthrough\n", encoding="utf-8")
    schemas.cache_clear()
    return root


def _ingest(root: Path, text: str = _STATEMENT) -> str:
    src = root / "capture" / "statement.md"
    src.write_text(text, encoding="utf-8")
    assert ingest._ingest_one(root, src) == 0
    (rec,) = (root / "records").rglob("*.md")
    return rec.stem


def test_a_markdown_body_is_its_own_text(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root)
    post = records.load(next((root / "records").rglob("*.md")))
    assert post.content.strip() == ""  # passthrough: nothing stored
    body = derive.derive_body(post, root)
    assert "language: markdown" in body
    assert _STATEMENT.rstrip("\n") in body
    assert rid


def test_a_specialized_drafter_still_wins_over_the_family_default(tmp_path):
    root = _corpus(tmp_path)
    drafter, _strategy, sid, _mt = derive.resolve_drafter(root, "text/html")
    assert sid == "text/text_html" and drafter.__module__ == "corpus.draft.html"
    app = root / "schema" / "mime" / "application"
    app.mkdir()
    (app / "application_x-thing.yaml").write_text(
        "description: A binary.\napplies_to:\n  content_types: [application/x-thing]\n",
        encoding="utf-8")
    schemas.cache_clear()
    with pytest.raises(derive.DeriveError, match="no drafter registered"):
        derive.resolve_drafter(root, "application/x-thing")  # the default is text/* only


def _verify(tmp_path: Path, root: Path, rid: str, quote: str):
    ledger = tmp_path / "ledger"
    (ledger / "facts" / "account").mkdir(parents=True, exist_ok=True)
    (ledger / "facts" / "account" / "card.json").write_text(json.dumps({
        "id": "card", "type": "account", "name": "Card",
        "sources": {"s1": {"record": rid}},
        "claims": [{"id": "card:number", "predicate": "number", "value": "5616",
                    "status": "confirmed", "asof": "2026-09-27",
                    "evidence": [{"source": "s1", "quote": quote, "kind": "direct"}]}],
    }), encoding="utf-8")
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    return verify_ledger(ledger, join, {}, stamp=False)


def test_a_record_level_quote_verifies_against_the_derived_body(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root)
    res = _verify(tmp_path, root, rid, "5616 is my triangle card with my phone")
    assert res.errors == [] and res.verified == 1


def test_a_wrong_quote_still_fails(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root)
    res = _verify(tmp_path, root, rid, "5617 is my triangle card")
    assert any("quote not found verbatim" in e for e in res.errors)
