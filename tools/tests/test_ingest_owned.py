"""`corpus ingest-owned` — the consumer ingest lane (spec/athenaeum.md §2.3 `consumer_ingest:`,
v49; owner ruling 2026-09-28, codex-steven R-0052).

A consumer (ita) may capture the owner's own statements without a request per statement, and
nothing else: the verb takes no origin argument. Its allowlist lives in the instance config,
which a consumer cannot edit, because a caller-supplied `--allow-origin` would be extended by
appending another flag after a prefix-matched permission rule.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from corpus import records, schemas
from corpus._cli import ingest_owned

_OVERLAY = """\
description: One statement the owner made.
extended_fields:
  channel:
    type: string
    required: true
  channel_ref:
    type: string
    required: true
"""


@pytest.fixture()
def instance(tmp_path: Path) -> Path:
    (tmp_path / "athenaeum.yaml").write_text(
        "name: t\nconsumer_ingest:\n  origins: [owner-statement]\n", encoding="utf-8")
    corpus = tmp_path / "corpus"
    (corpus / "records").mkdir(parents=True)
    (corpus / "capture").mkdir()
    for oid in ("owner-statement", "bank-statement"):
        (corpus / "schema" / "origin").mkdir(parents=True, exist_ok=True)
        (corpus / "schema" / "origin" / f"{oid}.yaml").write_text(_OVERLAY, encoding="utf-8")
    (corpus / "schema" / "mime" / "text").mkdir(parents=True)
    (corpus / "schema" / "mime" / "text" / "text_plain.yaml").write_text(
        "applies_to:\n  content_types: [text/plain]\n", encoding="utf-8")
    schemas.cache_clear()
    return tmp_path


def _stage(instance: Path, sidecar: dict | None, text: str = "Yes, the Banff trip was for "
           "the beer festival.\n") -> Path:
    src = instance / "corpus" / "capture" / "statement.txt"
    src.write_text(text, encoding="utf-8")
    if sidecar is not None:
        Path(f"{src}.capture.yaml").write_text(yaml.safe_dump(sidecar), encoding="utf-8")
    return src


def _run(instance: Path, src: Path) -> int:
    return ingest_owned.run(argparse.Namespace(
        file=src, corpus_root=str(instance / "corpus")))


_GOOD = {"origin_schema": "owner-statement",
         "origin_fields": {"channel": "chat", "channel_ref": "codex-steven session d41d msg 5e"}}


def _records(instance: Path) -> list[Path]:
    return list((instance / "corpus" / "records").rglob("*.md"))


@pytest.mark.parametrize(("sidecar", "said"), [
    (None, "declares no origin"),
    ({"origin_schema": "bank-statement", "origin_fields": _GOOD["origin_fields"]},
     "not one the lane opens"),
    ({**_GOOD, "source_url": "https://example.org/x"}, "retrieval origin"),
    ({"origin_schema": "owner-statement", "origin_fields": {"channel": "chat"}},
     "requires channel_ref"),
])
def test_the_lane_refuses_before_anything_is_written(instance, sidecar, said):
    src = _stage(instance, sidecar)
    before = src.read_bytes()
    with pytest.raises(SystemExit, match=said):
        _run(instance, src)
    assert _records(instance) == []
    assert src.read_bytes() == before  # the staged bytes are untouched


def test_a_closed_lane_refuses_everything(instance):
    (instance / "athenaeum.yaml").write_text("name: t\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="opens no consumer ingest lane"):
        _run(instance, _stage(instance, _GOOD))


def test_a_declared_owner_statement_is_ingested_with_its_provenance(instance):
    assert _run(instance, _stage(instance, _GOOD)) == 0
    (rec,) = _records(instance)
    (block,) = list(records.iter_origin_blocks(records.load(rec)))
    assert block["id"] == "owner-statement"
    assert block["fields"]["channel_ref"] == "codex-steven session d41d msg 5e"
    assert not (instance / "corpus" / "capture" / "statement.txt").exists()
