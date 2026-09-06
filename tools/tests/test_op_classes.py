"""Op classes (spec §6.2, v43): every op has exactly one declared place — address /
reading / view / instrument / engine — and the two normative consequences hold:

- a stored address is address-class only (lint `address-op-class`, error);
- an evidence anchor is address-class ops optionally ending in one reading; a view,
  instrument, or engine op in an anchor is a citation defect at the claim's severity,
  refused BEFORE any resolver call — never the honest-unverifiable path.

`register` refuses an unclassified param, so the per-mime op list `corpus inspect` prints
is complete by construction; `ops_for_media_type` exposes the class beside the pin.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pytest

from corpus import hashing, lint, paths, records, resolver, schemas, transforms
from corpus import mime as mime_mod
from corpus.store import LocalArtifactStore

_BORN_TEXT_PDF = Path(__file__).parent / "data" / "born_text.pdf"


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _stage_record(root: Path, data: bytes, *, mime: str, name: str, body: str = "") -> str:
    src = root.parent / name
    src.write_bytes(data)
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, mime_mod.extension_for(mime), src)
    post = frontmatter.Post(body)
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(
        post, snapshot="2026-07-18T00:00:00Z", fields={"filename": name, "source_modified": ""}
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


# ---------- the table is total over the registry, and classes are the five ---------- #


def test_every_registered_op_carries_a_declared_class():
    for (_kind, param), handler in transforms.REGISTRY.items():
        assert handler.op_class in transforms.OP_CLASSES_ALL, param
        assert transforms.op_class(param) == handler.op_class


def test_register_refuses_an_unclassified_param():
    with pytest.raises(ValueError, match="has no op class"):
        transforms.register("image", "hologram", "image")(lambda w, v, c: w)


@pytest.mark.parametrize(
    ("param", "cls"),
    [
        ("page", "address"), ("el", "address"), ("bbox", "address"), ("rotate", "address"),
        ("cover", "address"), ("msg", "address"), ("part", "address"), ("prop", "address"),
        ("turn", "address"), ("time_range", "address"),
        ("text", "reading"), ("body", "reading"), ("members", "reading"), ("outline", "reading"),
        ("render", "view"), ("fit", "view"), ("mark", "view"), ("dpi", "view"),
        ("annotated", "view"), ("raw", "view"), ("format", "view"),
        ("probe", "instrument"), ("words", "instrument"), ("geometry", "instrument"),
        ("scene", "instrument"), ("scenes", "instrument"),
        ("transcribe", "engine"),
    ],
)
def test_declared_places(param, cls):
    assert transforms.op_class(param) == cls
    assert resolver.op_class_for_param(param) == cls


def test_unknown_param_has_no_class():
    assert transforms.op_class("fragment") is None


def test_ops_for_media_type_exposes_class_beside_pin(tmp_path):
    root = _corpus(tmp_path)
    pdf = {
        (op.from_kind, op.param): op
        for op in resolver.ops_for_media_type(root, "application/pdf")
    }
    assert pdf[("pdf", "page")].op_class == "address"
    assert pdf[("pdfpage", "text")].op_class == "reading"
    assert pdf[("pdfpage", "geometry")].op_class == "instrument"
    assert pdf[("pdfpage", "render")].op_class == "view"
    audio = {op.param: op for op in resolver.ops_for_media_type(root, "audio/mpeg")}
    assert audio["transcribe"].op_class == "engine"


def test_anchor_class_defects_names_only_tool_ops():
    ok = [("msg", "2"), ("part", "1"), ("text", "")]
    assert transforms.anchor_class_defects(ok) == []
    bad = [("page", "1"), ("mark", "0,0,1,1"), ("probe", ""), ("transcribe", ""), ("zzz", "")]
    assert transforms.anchor_class_defects(bad) == [
        ("mark", "view"), ("probe", "instrument"), ("transcribe", "engine")
    ]


# ---------- lint: a stored address is address-class only ---------- #


def _lint_ids(root: Path, rid: str) -> dict[str, list]:
    from corpus import segments

    post = records.load(paths.record_path(root, rid))
    blocks = list(segments.iter_blocks(post.content or ""))
    out: dict[str, list] = {}
    for f in lint.lint(post, blocks, root):
        out.setdefault(f.rule_id, []).append(f)
    return out


def test_lint_flags_a_view_op_in_a_stored_address(tmp_path):
    root = _corpus(tmp_path)
    body = (
        "<!--segment image\naddress: page=1&bbox=0,0,1,0.5&fit=800x600\n-->\n\n"
        "<!--segment image\naddress: rotate=90&bbox=0,0,1,0.5\n-->\n\n"
        "<!--segment text\naddress: page=1&bbox=0,0.5,1,0.5&cover=0,0,0.1,0.1\n-->\n\nsome text\n"
    )
    rid = _stage_record(root, _BORN_TEXT_PDF.read_bytes(), mime="application/pdf",
                        name="doc.pdf", body=body)
    found = _lint_ids(root, rid).get("address-op-class", [])
    assert len(found) == 1
    (f,) = found
    assert f.severity == "error"
    assert f.fields == {"param": "fit", "op_class": "view"}
    assert "fit=800x600" in f.address


# ---------- ledger: an anchor never carries a tool op ---------- #


def _fact(ledger: Path, rid: str, anchor: str, quote: str, status: str = "confirmed") -> Path:
    (ledger / "facts" / "doc").mkdir(parents=True, exist_ok=True)
    f = ledger / "facts" / "doc" / "d.json"
    f.write_text(json.dumps({
        "id": "d", "type": "doc", "name": "D",
        "sources": {"s1": {"record": rid}},
        "claims": [{"id": "d:x", "predicate": "says", "value": "x",
                    "status": status, "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": anchor, "quote": quote,
                                  "kind": "authoritative"}]}],
    }))
    return f


@pytest.mark.parametrize(
    ("anchor", "expect"),
    [
        ("page=1&geometry", "`geometry` (instrument)"),
        ("page=1&mark=0,0,1,1", "`mark` (view)"),
        ("probe", "`probe` (instrument)"),
    ],
)
def test_verify_refuses_tool_ops_in_an_anchor_as_a_defect(tmp_path, anchor, expect):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage_record(root, _BORN_TEXT_PDF.read_bytes(), mime="application/pdf", name="doc.pdf")
    ledger = root.parent / "ledger"
    _fact(ledger, rid, anchor, "Hello born-digital vector text")
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.unverifiable == 0 and res.verified == 0
    assert len(res.errors) == 1 and expect in res.errors[0]
    assert "never tools" in res.errors[0]


def test_verify_engine_op_in_anchor_points_at_stored_transcript(tmp_path):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage_record(root, b"\xff\xfb\x90\x00" + bytes(64), mime="audio/mpeg", name="a.mp3")
    ledger = root.parent / "ledger"
    _fact(ledger, rid, "transcribe", "hello", status="provisional")
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.unverifiable == 0
    assert len(res.warnings) == 1  # provisional → warning severity
    assert "`transcribe` (engine)" in res.warnings[0]
    assert "stored transcript" in res.warnings[0]


def test_verify_still_resolves_an_address_plus_reading_anchor(tmp_path):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage_record(root, _BORN_TEXT_PDF.read_bytes(), mime="application/pdf", name="doc.pdf")
    ledger = root.parent / "ledger"
    _fact(ledger, rid, "page=1&text", "Hello born-digital vector text")
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert not res.errors and res.unverifiable == 0, (res.errors, res.notes)
    assert res.verified == 1 and res.derived_resolved == 1


# ---------- inspect prints the place ---------- #


def test_inspect_prints_each_ops_class(tmp_path, capsys):
    import argparse

    from corpus._cli import inspect_ as inspect_cli

    root = _corpus(tmp_path)
    rid = _stage_record(root, _BORN_TEXT_PDF.read_bytes(), mime="application/pdf", name="doc.pdf")
    parser = argparse.ArgumentParser()
    inspect_cli.configure(parser)
    rc = inspect_cli.run(parser.parse_args([rid, "--corpus-root", str(root)]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "page= -> pdfpage [address]" in out
    assert "text= -> text [reading]" in out
    assert "geometry= -> json [instrument]" in out
    assert "render= -> image [view]" in out
    assert "body -> markdown [reading]" in out
