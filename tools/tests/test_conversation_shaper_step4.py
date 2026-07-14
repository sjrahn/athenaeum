"""The §12.18 step-4 additions to the generic `conversation` shaper: `kind`/`event_kinds`
(authored platform events → `text/metadata` keeping `participant:`, verbatim kind on `kind:`),
`topic` (Google Chat `topic_id` → `<!--segment structural-->` byte-marks, first-appearance),
and `timestamp_style` (Google takeout en-locale UTC strings → ISO, else verbatim).

Each capability is driven by an origin overlay mapping and zero per-producer code.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import hashing, lint, paths, records, schemas, segments
from corpus import shape as shape_pkg
from corpus.shape import conversation
from corpus.store import LocalArtifactStore


def _corpus(tmp_path: Path, overlay_yaml: str) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "conv-export.yaml").write_text(overlay_yaml, encoding="utf-8")
    schemas.cache_clear()
    return root


def _shaped(tmp_path: Path, overlay_yaml: str, chat: dict) -> tuple[Path, frontmatter.Post]:
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
    return root, records.load(rf)


def _section(post: frontmatter.Post) -> segments.Section:
    (sec,) = segments.iter_blocks(post.content or "")
    assert isinstance(sec, segments.Section)
    return sec


def _lint_errors(post, root):
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root) if f.severity == "error"]


# ====================================================================== #
# 1. kind + event_kinds — authored platform events
# ====================================================================== #

_EVENT_OVERLAY = """\
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
    text: content
    kind: type
    event_kinds: [Call, RecipientAdd]
"""

_EVENT_CHAT = {
    "messages": [
        {"id": "m1", "author": {"id": "u1", "name": "Andy"}, "type": "Default", "content": "Yo"},
        # An AUTHORED event: type Call, carries an author (the caller).
        {"id": "m2", "author": {"id": "u2", "name": "Bea"}, "type": "Call",
         "content": "Bea started a call"},
        # An author-LESS event whose kind is in event_kinds.
        {"id": "e1", "type": "RecipientAdd", "content": "Cy was added"},
        {"id": "m3", "author": {"id": "u1", "name": "Andy"}, "type": "Default", "content": "back"},
    ]
}


def test_authored_event_is_metadata_keeps_participant_and_kind(tmp_path):
    root, post = _shaped(tmp_path, _EVENT_OVERLAY, _EVENT_CHAT)
    sec = _section(post)
    # Bea (the caller of the authored Call event) earns a codebook slot — she is a participant.
    assert sec.extra["participants"] == ["Andy u1", "Bea u2"]

    segs = sec.segments
    m1, m2, e1, m3 = segs[0], segs[1], segs[2], segs[3]
    # turn 1: a plain message — text/message, no kind field.
    assert (m1.overlay, m1.address) == ("text/message", "turn=1")
    assert "kind" not in m1.extra
    # turn 2: authored Call → text/metadata, KEEPS participant (Bea=1), verbatim kind.
    assert (m2.overlay, m2.address) == ("text/metadata", "turn=2")
    assert m2.extra["participant"] == 1
    assert m2.extra["kind"] == "Call"
    # turn 3: author-less RecipientAdd → text/metadata, no participant, kind carried.
    assert (e1.overlay, e1.address) == ("text/metadata", "turn=3")
    assert "participant" not in e1.extra
    assert e1.extra["kind"] == "RecipientAdd"
    # turn 4: plain message again.
    assert (m3.overlay, m3.extra.get("participant")) == ("text/message", 0)

    assert not _lint_errors(post, root)


# ====================================================================== #
# 2. topic — structural byte-marks at first appearance
# ====================================================================== #

_TOPIC_OVERLAY = """\
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
    text: content
    topic: topic_id
"""

_TOPIC_CHAT = {
    "messages": [
        {"id": "1", "author": {"id": "u1", "name": "A"}, "topic_id": "T-A", "content": "a1"},
        {"id": "2", "author": {"id": "u1", "name": "A"}, "topic_id": "T-B", "content": "b1"},
        # T-A recurs (interleaved threads) — the topic is already declared, so NO second mark.
        {"id": "3", "author": {"id": "u1", "name": "A"}, "topic_id": "T-A", "content": "a2"},
        {"id": "4", "author": {"id": "u1", "name": "A"}, "topic_id": "T-C", "content": "c1"},
    ]
}


def test_topic_marks_first_appearance_share_turn_address(tmp_path):
    root, post = _shaped(tmp_path, _TOPIC_OVERLAY, _TOPIC_CHAT)
    sec = _section(post)
    marks = [s for s in sec.segments if s.is_structural]
    # One mark per DISTINCT topic at its birth (T-A recurring at turn 3 adds none): T-A(1),
    # T-B(2), T-C(4). Topic MEMBERSHIP per message stays byte-recoverable via the turn= op.
    assert [(m.address, m.entry, m.level) for m in marks] == [
        ("turn=1", "T-A", 1),
        ("turn=2", "T-B", 1),
        ("turn=4", "T-C", 1),
    ]
    # Each mark shares its turn= address with that turn's message segment (legal: distinct
    # opener-ids, §4.3.2.2) — the message segments are all still present.
    msgs = [s for s in sec.segments if not s.is_structural and s.overlay == "text/message"]
    assert [s.address for s in msgs] == ["turn=1", "turn=2", "turn=3", "turn=4"]
    # The mark precedes its turn's message in reading order.
    assert sec.segments[0].is_structural and sec.segments[1].address == "turn=1"

    assert not _lint_errors(post, root)


# ====================================================================== #
# 3. timestamp_style — google takeout en-locale UTC
# ====================================================================== #

_TS_OVERLAY = """\
applies_to:
  schemes: [convexport]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    author_id: author.id
    author_name: author.name
    text: content
    timestamp: created
    timestamp_style: google-takeout-en-utc
"""

_TS_CHAT = {
    "messages": [
        {"author": {"id": "u1", "name": "A"}, "content": "x",
         "created": "Wednesday, January 8, 2014 at 6:26:59 AM UTC"},
        {"author": {"id": "u1", "name": "A"}, "content": "noon",
         "created": "Wednesday, January 8, 2014 at 12:00:00 PM UTC"},
        {"author": {"id": "u1", "name": "A"}, "content": "midnight-half",
         "created": "Wednesday, January 8, 2014 at 12:30:00 AM UTC"},
        {"author": {"id": "u1", "name": "A"}, "content": "junk", "created": "sometime yesterday"},
        # An EMPTY created_date (34 real GChat system messages have this) → omit the field.
        {"author": {"id": "u1", "name": "A"}, "content": "no-ts", "created": ""},
        # Google's REAL bytes separate seconds from AM/PM with a NARROW NO-BREAK SPACE (U+202F),
        # not a plain space — the fleet-wide format. Must still normalize.
        {"author": {"id": "u1", "name": "A"}, "content": "real",
         "created": "Wednesday, January 8, 2014 at 6:26:59\u202fAM UTC"},
    ]
}


def test_takeout_timestamps_normalize_else_verbatim(tmp_path):
    root, post = _shaped(tmp_path, _TS_OVERLAY, _TS_CHAT)
    segs = _section(post).segments
    assert segs[0].extra["timestamp"] == "2014-01-08T06:26:59Z"
    assert segs[1].extra["timestamp"] == "2014-01-08T12:00:00Z"  # 12 PM → 12:00
    assert segs[2].extra["timestamp"] == "2014-01-08T00:30:00Z"  # 12:30 AM → 00:30
    assert segs[3].extra["timestamp"] == "sometime yesterday"  # unparseable → verbatim
    assert "timestamp" not in segs[4].extra  # empty value → field omitted entirely
    assert segs[5].extra["timestamp"] == "2014-01-08T06:26:59Z"  # U+202F separator → normalized
    assert not _lint_errors(post, root)


# ---------- _normalize_timestamp unit coverage (DCE verbatim + non-UTC) ---------- #


def test_normalize_timestamp_style_gating():
    ts = "Wednesday, January 8, 2014 at 6:26:59 AM UTC"
    # No style (the DCE case) → verbatim, never guessed at.
    assert conversation._normalize_timestamp(ts, None) == ts
    assert conversation._normalize_timestamp("2014-03-04T00:09:34Z", None) == "2014-03-04T00:09:34Z"
    # The takeout style parses the fixed shape…
    assert conversation._normalize_timestamp(ts, "google-takeout-en-utc") == "2014-01-08T06:26:59Z"
    # …including Google's REAL bytes, which put a NARROW NO-BREAK SPACE (U+202F) before AM/PM
    # (the pattern's separators are Unicode `\s+`, which matches it) — the fleet-wide format.
    real = "Wednesday, January 8, 2014 at 6:26:59\u202fAM\u202fUTC"
    assert (
        conversation._normalize_timestamp(real, "google-takeout-en-utc") == "2014-01-08T06:26:59Z"
    )
    # …but a non-UTC-suffixed value stays verbatim (tolerant, faithful).
    pst = "Wednesday, January 8, 2014 at 6:26:59 AM PST"
    assert conversation._normalize_timestamp(pst, "google-takeout-en-utc") == pst
    # An unknown style name is inert.
    assert conversation._normalize_timestamp(ts, "some-other-style") == ts
