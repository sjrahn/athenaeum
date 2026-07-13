"""The generic mapping-driven `conversation` shaper (spec §7.8, §12.5.0).

A synthetic JSON chat producer: an origin overlay declares `form: {id: conversation, mapping}`,
and the shaper turns the producer's messages into the `form/conversation` decomposition. Proves
one shaper serves any JSON chat producer through its overlay mapping — zero code per platform."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import hashing, lint, paths, records, schemas, segments
from corpus import shape as shape_pkg
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
    reply_to: reply_to
    attachments: attachments
    attachment_url: url
"""

_CHAT = {
    "messages": [
        {"id": "m1", "author": {"id": "u1", "name": "Andy"},
         "timestamp": "2014-03-04T00:09:34Z", "content": "Yo"},
        {"id": "m2", "author": {"id": "u2", "name": "Steven"},
         "timestamp": "2014-03-04T00:11:02Z", "content": "hey", "reply_to": "m1",
         "attachments": [{"url": "https://cdn.example/pic.png"}]},
        {"id": "e1", "content": "Steven joined the channel"},  # event: no author
        {"id": "m3", "author": {"id": "u1", "name": "Andy"},
         "timestamp": "2014-03-04T00:12:00Z", "content": "back"},
    ]
}


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "conv-export.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def _ingest_chat(root: Path) -> str:
    raw = json.dumps(_CHAT).encode()
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
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_conversation_shaper_builds_form_decomposition(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest_chat(root)
    rf = paths.record_path(root, rid)
    post = records.load(rf)

    assert shape_pkg.shape_record(post, root) is True
    records.dump(post, rf)
    post = records.load(rf)

    blocks = segments.iter_blocks(post.content or "")
    (sec,) = blocks
    assert isinstance(sec, segments.Section)
    assert sec.form == "conversation"
    # Codebook: distinct authors in first-appearance order; the event has no slot.
    assert sec.extra["participants"] == ["Andy u1", "Steven u2"]

    segs = sec.segments
    # turn 1: Andy, participant 0.
    assert (segs[0].overlay, segs[0].address, segs[0].body) == ("text/message", "turn=1", "Yo")
    assert segs[0].extra["participant"] == 0
    assert segs[0].extra["timestamp"] == "2014-03-04T00:09:34Z"
    # turn 2: Steven, participant 1, reply to turn 1, + an image attachment marker.
    msg2 = segs[1]
    assert msg2.extra["participant"] == 1
    assert msg2.extra["reply_to"] == "turn=1"
    att = segs[2]
    assert (att.atom, att.address, att.body) == ("image", "turn=2&att=1", "")
    # turn 3: the platform event → text/metadata, no participant.
    evt = segs[3]
    assert evt.overlay == "text/metadata"
    assert "participant" not in evt.extra
    assert evt.body == "Steven joined the channel"

    # The shape touch was appended.
    touch = post.metadata["touch"]
    chain = touch if isinstance(touch, list) else [touch]
    assert any("shape.conversation" in t for t in chain)

    # Form-coherence: the shaped record lints clean (no errors).
    findings = lint.lint(post, blocks, root)
    assert not [f for f in findings if f.severity == "error"], [f.rule_id for f in findings]
    assert "form/conversation" in records.derived_classifications(post)


def test_shape_record_noop_without_form(tmp_path):
    """A record whose origin declares no form is not shaped."""
    root = _corpus(tmp_path)
    (root / "schema" / "origin" / "plain.yaml").write_text(
        "applies_to:\n  schemes: [plainx]\nkind: interpretive\n", encoding="utf-8"
    )
    schemas.cache_clear()
    rid = _ingest_chat(root)
    post = records.load(paths.record_path(root, rid))
    # Re-stamp the origin to the form-less overlay.
    post.metadata["_origins"][0]["id"] = "plain"
    assert shape_pkg.shape_record(post, root) is False
