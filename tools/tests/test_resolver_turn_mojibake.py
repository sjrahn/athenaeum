"""Regression: `corpus resolve ...?turn=N` must apply the mapping's declared `text_encoding`
repair (spec §7.2) exactly like the `conversation` shaper's per-turn envelope rendering
(`shape/conversation.py`) — the same repair, shared via `shape/units.py`.

Defect: a `turn=N` resolve on a Meta (Facebook/Instagram/Threads) conversation record printed
double-encoded mojibake bytes (`"...Iâ\\x80\\x99m going..."`, i.e. `"â€™"`) where `corpus body`
(which runs through the shaper) printed clean text (`"...I'm going..."`). The repair — Meta's
UTF-8-read-as-Latin-1 export bug, `text_encoding: meta-mojibake` — existed in `units.py` but
the resolver's `_resolve_turn` never applied it, only the shaper did. Fixed by
`shape/units.repair_json_strings`, applied to the whole unit object before it's cached/returned
(not just the two mapped fields) — Meta's export bug corrupts the WHOLE JSON payload uniformly,
not only `author_name`/`text`.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import hashing, paths, records, resolver, schemas
from corpus.store import LocalArtifactStore

# Meta's real mis-encoding, reproduced mechanically (never hand-typed — Unicode mojibake is
# easy to transcribe wrong): the correct text's UTF-8 bytes misread as Latin-1 codepoints, the
# exact "â€™" pattern the defect report calls out (an apostrophe, U+2019, UTF-8 bytes E2 80 99,
# each byte misread as its own Latin-1 codepoint then re-encoded as UTF-8 — C3 A2 C2 80 C2 99).
_CORRECT_TEXT = "I" + chr(0x2019) + "m going to school"  # U+2019 apostrophe (ruff RUF001)
_MANGLED_TEXT = _CORRECT_TEXT.encode("utf-8").decode("latin-1")
_CORRECT_NAME = "Grabiński"
_MANGLED_NAME = _CORRECT_NAME.encode("utf-8").decode("latin-1")

_META_OVERLAY = """\
applies_to:
  schemes: [convexport]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    author_name: sender_name
    text: content
    text_encoding: meta-mojibake
    attachments: attachments
    attachment_url: uri
"""

_CHAT = {
    "messages": [
        {"sender_name": _CORRECT_NAME, "content": "Yo"},
        {"sender_name": "Steven", "content": _MANGLED_TEXT},
    ]
}


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "meta-export.yaml").write_text(_META_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def _ingest_chat(root: Path, chat: dict) -> str:
    raw = json.dumps(chat).encode()
    src = root / "chat.json"
    src.write_bytes(raw)
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "json", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                schema_id="meta-export", fields={"filename": "chat.json"})
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_turn_repairs_meta_mojibake_in_the_text_field(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root, _CHAT)
    assert _MANGLED_TEXT != _CORRECT_TEXT  # sanity: this fixture IS mangled

    out = resolver.resolve(f"corpus://{rid}?turn=2", root)
    unit = json.loads(out.read_text("utf-8"))
    assert unit["content"] == _CORRECT_TEXT
    # The raw bytes on disk must be the clean UTF-8 encoding too — never the double-encoded
    # mojibake bytes the defect report identified (`"â€™"`, C3 A2 C2 80 C2 99).
    assert "â€™" not in out.read_bytes().decode("utf-8")


def test_turn_repairs_meta_mojibake_in_the_author_name_field(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root, _CHAT)
    out = resolver.resolve(f"corpus://{rid}?turn=1", root)
    unit = json.loads(out.read_text("utf-8"))
    assert unit["sender_name"] == _CORRECT_NAME


def test_turn_without_text_encoding_mapping_is_a_noop(tmp_path):
    """Absent `text_encoding` on the mapping, `turn=` must NOT alter the raw text (no silent
    global heuristic — the repair is a disclosed, per-producer opt-in, spec §7.2)."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "plain-export.yaml").write_text(
        """\
applies_to:
  schemes: [convexport2]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    author_name: sender_name
    text: content
""",
        encoding="utf-8",
    )
    schemas.cache_clear()
    raw = json.dumps({"messages": [{"sender_name": "Andy", "content": _MANGLED_TEXT}]}).encode()
    src = root / "chat2.json"
    src.write_bytes(raw)
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "json", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "", "status": "stub",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                schema_id="plain-export", fields={"filename": "chat2.json"})
    records.dump(post, paths.record_path(root, rid))

    out = resolver.resolve(f"corpus://{rid}?turn=1", root)
    unit = json.loads(out.read_text("utf-8"))
    assert unit["content"] == _MANGLED_TEXT  # left exactly as the source declared it
