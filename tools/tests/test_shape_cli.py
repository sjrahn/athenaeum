"""`corpus shape` — the CLI verb driving `corpus.shape.shape_record` (spec §12.5.0, §8.1).

Uses the bundled `conversation` shaper against a synthetic JSON chat producer: an origin overlay
declares `form: {id: conversation, mapping}`, and the verb shapes the stub's content zone,
appends the `shape.conversation` touch WITHOUT authoring the vouch (title/description stay
empty — shaping is only half the normalize pass, §8.1), and reports `shaped`. A record whose
origin declares no form is reported `skipped` (not an error). Batch + stdin driving covered.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import frontmatter

from corpus import hashing, paths, records, schemas, segments
from corpus._cli import shape as shape_cli
from corpus.store import LocalArtifactStore

_OVERLAY = """\
applies_to:
  schemes: [convexport]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    message_id: id
    author_id: author.id
    author_name: author.name
    timestamp: timestamp
    text: content
"""

_PLAIN_OVERLAY = "applies_to:\n  schemes: [plainx]\nkind: interpretive\n"

_CHAT = {
    "messages": [
        {"id": "m1", "author": {"id": "u1", "name": "Andy"}, "timestamp": "t0", "content": "Yo"},
        {"id": "m2", "author": {"id": "u2", "name": "Bea"}, "timestamp": "t1", "content": "hi"},
    ]
}


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "conv-export.yaml").write_text(_OVERLAY, encoding="utf-8")
    (odir / "plain.yaml").write_text(_PLAIN_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def _ingest_chat(root: Path, schema_id: str = "conv-export") -> str:
    raw = json.dumps(_CHAT).encode()
    src = root / "chat.json"
    src.write_bytes(raw)
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "json", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                schema_id=schema_id, fields={"filename": "chat.json"})
    records.dump(post, paths.record_path(root, rid))
    return rid


def _run(root: Path, *targets: str) -> int:
    return shape_cli.run(argparse.Namespace(targets=list(targets), corpus_root=str(root)))


# ---------- happy path: shape a declared form ---------- #


def test_shape_builds_form_and_leaves_vouch_unauthored(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)

    assert _run(root, rid) == 0
    out = capsys.readouterr().out
    assert f"shaped {rid[:12]} (conversation)" in out

    post = records.load(paths.record_path(root, rid))
    # The content zone was shaped (a conversation section with two turns).
    (sec,) = segments.iter_blocks(post.content or "")
    assert isinstance(sec, segments.Section) and sec.form == "conversation"
    assert [s.address for s in sec.segments] == ["turn=1", "turn=2"]
    assert records.derived_state(post) == "formed"
    # The shape touch was appended; the vouch is UNCHANGED — shaping is only half the
    # normalize pass (§8.1); title/description are the interpretive agent's remaining work.
    chain = post.metadata["touch"]
    chain = chain if isinstance(chain, list) else [chain]
    assert any("shape.conversation" in t for t in chain)
    assert not records.is_authored(post)


# ---------- skip path: no declared form ---------- #


def test_shape_skips_formless_record(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root, schema_id="plain")  # origin declares no form
    assert _run(root, rid) == 0
    out = capsys.readouterr().out
    assert f"skipped {rid[:12]} (no declared form)" in out
    # Not shaped: the content zone stays empty.
    assert not (records.load(paths.record_path(root, rid)).content or "").strip()


# ---------- batch + stdin driving ---------- #


def test_shape_batch_multiple_ids(tmp_path, capsys):
    root = _corpus(tmp_path)
    r1 = _ingest_chat(root)
    # A second record with different bytes (distinct id) via a tweaked chat.
    raw2 = json.dumps({"messages": [{"id": "x", "author": {"id": "u9", "name": "Zed"},
                                     "timestamp": "t", "content": "sup"}]}).encode()
    src = root / "chat2.json"
    src.write_bytes(raw2)
    h = hashing.hash_file(src)
    r2 = h["blake3"]
    LocalArtifactStore(root).put(r2, "json", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update({"id": r2, "title": "", "description": "",
                          "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                schema_id="conv-export", fields={"filename": "chat2.json"})
    records.dump(post, paths.record_path(root, r2))

    assert _run(root, r1, r2) == 0
    out = capsys.readouterr().out
    assert f"shaped {r1[:12]} (conversation)" in out
    assert f"shaped {r2[:12]} (conversation)" in out
    assert "shaped 2 record(s)" in out


def test_shape_reads_ids_from_stdin(tmp_path, capsys, monkeypatch):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{rid}\n"))
    assert _run(root, "-") == 0
    assert f"shaped {rid[:12]} (conversation)" in capsys.readouterr().out


# ---------- hard error: a missing record exits nonzero, batch continues ---------- #


def test_missing_record_is_a_hard_error_but_batch_continues(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)
    missing = "0" * 64
    assert _run(root, missing, rid) == 1  # nonzero because one target was missing
    err = capsys.readouterr()
    assert "shaped" in err.out  # the good record still shaped
    assert "error" in err.err  # the missing one reported to stderr
