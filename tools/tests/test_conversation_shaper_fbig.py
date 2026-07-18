"""The FB/IG-arc additions to the generic `conversation` shaper (2026-07-17): `order:
newest-first` (Meta's Facebook/Instagram/Threads `messages[]` is newest-first — reversed so
`turn=1` is always the OLDEST unit), list-valued `attachments:` (Meta's five parallel per-kind
arrays unioned into one virtual attachment list), and `text_encoding: meta-mojibake` (Meta's
UTF-8-read-as-Latin-1 export bug, mechanically reversible).

Each capability lives in `corpus.shape.units` (`unit_array`, `attachments`,
`text_encoding_repair`) — shared by this shaper AND the resolver's `turn=` unit op, so a single
addition covers both consumers with no per-consumer reversal/union/repair logic.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import hashing, lint, paths, records, resolver, schemas, segments
from corpus import shape as shape_pkg
from corpus.shape import units
from corpus.store import LocalArtifactStore

# Meta's real mis-encoding, reproduced mechanically (never hand-typed — Unicode mojibake is
# easy to transcribe wrong): the correct name's UTF-8 bytes misread as Latin-1 codepoints.
_CORRECT_NAME = "Grabiński"
_MANGLED_NAME = _CORRECT_NAME.encode("utf-8").decode("latin-1")


def _corpus(tmp_path: Path, overlay_yaml: str) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "conv-export.yaml").write_text(overlay_yaml, encoding="utf-8")
    schemas.cache_clear()
    return root


def _shaped(tmp_path: Path, overlay_yaml: str, chat: dict) -> tuple[Path, str, frontmatter.Post]:
    root = _corpus(tmp_path, overlay_yaml)
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
                                schema_id="conv-export", fields={"filename": "chat.json"})
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    post = records.load(rf)
    assert shape_pkg.shape_record(post, root) is True
    records.dump(post, rf)
    return root, rid, records.load(rf)


def _section(post: frontmatter.Post) -> segments.Section:
    (sec,) = segments.iter_blocks(post.content or "")
    assert isinstance(sec, segments.Section)
    return sec


def _lint_errors(post, root):
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root) if f.severity == "error"]


# ====================================================================== #
# units.py pure-function coverage
# ====================================================================== #


def test_unit_array_no_order_key_is_unchanged():
    data = {"messages": [{"n": 1}, {"n": 2}, {"n": 3}]}
    assert units.unit_array(data, {"messages": "messages"}) == data["messages"]


def test_unit_array_newest_first_reverses():
    data = {"messages": [{"n": 3}, {"n": 2}, {"n": 1}]}  # newest (3) first, like Meta's export
    mapping = {"messages": "messages", "order": "newest-first"}
    assert [m["n"] for m in units.unit_array(data, mapping)] == [1, 2, 3]


def test_unit_array_unrecognized_order_value_is_inert():
    data = {"messages": [{"n": 3}, {"n": 1}]}
    mapping = {"messages": "messages", "order": "oldest-first"}
    assert units.unit_array(data, mapping) == data["messages"]  # unchanged, not reversed


def test_attachments_single_path_backward_compatible():
    msg = {"attachments": [{"url": "a"}, {"url": "b"}]}
    assert units.attachments(msg, {"attachments": "attachments"}) == msg["attachments"]


def test_attachments_list_of_paths_unions_in_declaration_order():
    msg = {
        "photos": [{"uri": "p1.jpg"}],
        "videos": [{"uri": "v1.mp4"}],
        "gifs": [{"uri": "g1.gif"}, {"uri": "g2.gif"}],
        "audio_files": [{"uri": "a1.mp3"}],
        "files": [{"uri": "f1.pdf"}],
    }
    mapping = {"attachments": ["photos", "videos", "gifs", "audio_files", "files"]}
    result = units.attachments(msg, mapping)
    assert [a["uri"] for a in result] == [
        "p1.jpg", "v1.mp4", "g1.gif", "g2.gif", "a1.mp3", "f1.pdf",
    ]


def test_attachments_list_of_paths_missing_kind_contributes_nothing():
    msg = {"photos": [{"uri": "p1.jpg"}]}  # no videos/gifs/etc. on this message
    mapping = {"attachments": ["photos", "videos", "gifs"]}
    assert [a["uri"] for a in units.attachments(msg, mapping)] == ["p1.jpg"]


def test_text_encoding_repair_meta_mojibake():
    mapping = {"text_encoding": "meta-mojibake"}
    assert _MANGLED_NAME != _CORRECT_NAME  # sanity: this IS mangled, not already-correct
    assert units.text_encoding_repair(_MANGLED_NAME, mapping) == _CORRECT_NAME


def test_text_encoding_repair_no_key_is_noop():
    assert units.text_encoding_repair(_MANGLED_NAME, {}) == _MANGLED_NAME


def test_text_encoding_repair_falls_back_on_undecodable_bytes():
    mapping = {"text_encoding": "meta-mojibake"}
    # A string with a character that ISN'T Latin-1 encodable at all (so the round-trip's first
    # step, .encode('latin-1'), raises) — the guard falls back to the original, untouched.
    s = "hello 中文"
    assert units.text_encoding_repair(s, mapping) == s


def test_text_encoding_repair_non_string_passthrough():
    mapping = {"text_encoding": "meta-mojibake"}
    assert units.text_encoding_repair(None, mapping) is None
    assert units.text_encoding_repair(42, mapping) == 42


# ====================================================================== #
# Integration: shape_conversation honors order + attachments + text_encoding together
# (the Meta/Facebook/Instagram producer shape)
# ====================================================================== #

_META_OVERLAY = """\
applies_to:
  schemes: [convexport]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    author_name: sender_name
    timestamp: timestamp_ms
    text: content
    order: newest-first
    attachments: [photos, videos]
    attachment_url: uri
    text_encoding: meta-mojibake
"""


def _meta_chat() -> dict:
    # Meta's messages[] is newest-first: index [0] is the chronologically LAST message.
    return {
        "messages": [
            {"sender_name": "Andy", "timestamp_ms": 3000, "content": "back"},
            {"sender_name": "Steven", "timestamp_ms": 2000, "content": "hey",
             "photos": [{"uri": "photos/1.jpg"}], "videos": [{"uri": "videos/1.mp4"}]},
            {"sender_name": _MANGLED_NAME, "timestamp_ms": 1000, "content": "Yo"},
        ]
    }


def test_meta_shape_reorders_repairs_mojibake_and_unions_attachments(tmp_path):
    root, rid, post = _shaped(tmp_path, _META_OVERLAY, _meta_chat())
    sec = _section(post)

    # turn=1 is now the OLDEST message (timestamp_ms=1000, the reversed array's first entry),
    # and its mojibake-mangled sender name is repaired in the codebook.
    assert sec.extra["participants"] == [_CORRECT_NAME, "Steven", "Andy"]

    segs = sec.segments
    msgs = [s for s in segs if s.overlay == "text/message"]
    assert [s.address for s in msgs] == ["turn=1", "turn=2", "turn=3"]
    assert [s.body for s in msgs] == ["Yo", "hey", "back"]
    assert [s.extra["timestamp"] for s in msgs] == ["1000", "2000", "3000"]

    # turn=2's attachments: photos then videos, unioned in declaration order.
    atts = [s for s in segs if s.address.startswith("turn=2&att=")]
    assert [(a.address, a.atom) for a in atts] == [
        ("turn=2&att=1", "image"),
        ("turn=2&att=2", "video"),
    ]

    assert not _lint_errors(post, root)

    # The resolver's turn= unit op shares unit_array/attachments — turn=1 is the same OLDEST
    # message there too, and turn=2&att=2 addresses the videos-array entry.
    out = resolver.resolve(f"corpus://{rid}?turn=1", root)
    unit = json.loads(out.read_text("utf-8"))
    assert unit["content"] == "Yo"  # verbatim mojibake in the raw unit — repair is shaper-side
    out2 = resolver.resolve(f"corpus://{rid}?turn=2", root)
    assert json.loads(out2.read_text("utf-8"))["content"] == "hey"
