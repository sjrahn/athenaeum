"""The generic mapping-driven `conversation` shaper (spec §7.8, §12.5.0, §12.18 step 4).

Reads a JSON producer's messages via the origin overlay's `form.mapping` (§7.2) and emits the
`form/conversation` decomposition (§7.8): a `<!--section conversation-->` carrying the
authorship-ordered `participants:` codebook, one `text/message` per message at `turn=<N>`
(codebook `participant:` index, source-stated timestamp, in-record `reply_to`), `text/metadata`
for platform events, attachment markers at `turn=<N>&att=<M>` (no embed — lineage-resolvable,
§4.3.1.4), and `<!--segment structural-->` topic byte-marks. One shaper serves Discord /
Google Chat / Facebook / Instagram / Threads and any future JSON chat producer — the difference
is the overlay's mapping, not code.

Mapping keys consumed: `messages` (dotted path to the unit array), `author_id`, `author_name`,
`timestamp`, `text`, `message_id`, `reply_to`, `attachments`, `attachment_url`, plus the three
§12.18 step-4 capabilities:

- `kind` (dotted path) + `event_kinds` (list of verbatim values): a unit whose `kind` value is
  in `event_kinds` is a **platform event** — emitted as `text/metadata` EVEN WHEN AUTHORED
  (DCE's `Call` / `RecipientAdd` / `ChannelPinnedMessage` all carry an author, so the author-less
  test never fires for them). An authored event KEEPS its `participant:` codebook index (the
  caller / pinner is a fact) and carries the verbatim discriminator on the `text/metadata`
  overlay's declared `event:` field — the mapping key `kind` names where the discriminator lives
  in the SOURCE; the envelope reuses the established overlay field. A non-event unit gets no
  `event:` field (a reply is already expressed by `reply_to`).
- `topic` (dotted path): the source's own topic/thread id (Google Chat's `topic_id`). At the
  first unit carrying a topic value NOT seen earlier in the record, a `<!--segment structural-->`
  byte-mark (level 1, `entry:` = the verbatim topic value) is emitted at that unit's `turn=<N>`
  address — a producer-declared boundary (§4.3.2.3), the TOC unit for a topic directory.
- `timestamp_style` (optional mapping scalar): absent = the timestamp is kept VERBATIM (the DCE
  case). The one supported style, `google-takeout-en-utc`, normalizes Google's fixed
  English-locale UTC takeout strings to ISO-8601; anything that doesn't match stays verbatim. An
  EMPTY timestamp value (a blank `created_date`) omits the envelope field entirely.

**Topic-mark address decision.** The mark shares its `turn=<N>` address with that turn's
`text/message` segment. This is legal: `segment-address-duplicate` keys on `(opener-id, address)`,
and a `structural` mark's opener-id differs from `text/message` (spec §4.3.2.2 pair-uniqueness).
The mark is emitted at **first appearance of each distinct topic value**: the producer declares
topic MEMBERSHIP per message (not switch events), so one mark per topic at its birth is the honest
declared boundary — the TOC unit for a topic directory — and per-turn membership stays
byte-recoverable via the `turn=` unit op. A topic that recurs later adds no second mark.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter

from corpus import recordbuild
from corpus.shape import register_shaper, units

_IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|webp|avif|bmp|tiff?|heic|heif)(\?|$)", re.IGNORECASE)
_VIDEO_EXT = re.compile(r"\.(mp4|webm|mov|mkv|avi|m4v)(\?|$)", re.IGNORECASE)
_AUDIO_EXT = re.compile(r"\.(mp3|m4a|ogg|opus|wav|flac|aac)(\?|$)", re.IGNORECASE)

# The one supported `timestamp_style` — Google's fixed English-locale UTC takeout format.
# Named for its narrowness: it is NOT a general datetime parser (spec §12.18 step 4).
_TAKEOUT_EN_UTC = "google-takeout-en-utc"
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August",
         "September", "October", "November", "December"],
        start=1,
    )
}
# `Wednesday, January 8, 2014 at 6:26:59 AM UTC` — weekday ignored (redundant), day/hour
# non-zero-padded, a trailing `UTC` required (a non-UTC value stays verbatim). Every inter-token
# separator is `\s+`, NOT a literal space: Google's real takeout strings put a NARROW NO-BREAK
# SPACE (U+202F) before AM/PM (and use it in other date renderings too), which Python's Unicode
# `\s` matches — a plain-space pattern falls back verbatim on every real value.
_TAKEOUT_RE = re.compile(
    r"^[A-Za-z]+,\s+(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})\s+at\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})\s+(?P<ampm>AM|PM)\s+UTC$"
)


def _codebook_entry(display: Any, durable: Any) -> str:
    """The `<display> <durable-id>` codebook entry (§7.3), tolerant of a missing half."""
    d = str(display).strip() if display is not None else ""
    i = str(durable).strip() if durable is not None else ""
    return f"{d} {i}".strip() or "unknown"


def _attachment_atom(url: Any) -> str:
    """The content atom for an attachment, sniffed from its URL/filename extension. Unknown
    falls back to `image` (the dominant case in chat exports); the normalizer's description
    disambiguates. The marker is faithful either way — the asset is lineage-resolvable."""
    s = str(url or "")
    if _VIDEO_EXT.search(s):
        return "video"
    if _AUDIO_EXT.search(s):
        return "audio"
    return "image"


def _normalize_timestamp(raw: str, style: Any) -> str:
    """The timestamp envelope value. With no `timestamp_style` (the DCE case) or an unrecognized
    style, the source string is kept VERBATIM. The one supported style, `google-takeout-en-utc`,
    parses Google's fixed English-locale UTC takeout format
    (`Wednesday, January 8, 2014 at 6:26:59 AM UTC`, whose real bytes separate seconds from AM/PM
    with a NARROW NO-BREAK SPACE U+202F) to ISO-8601 (`2014-01-08T06:26:59Z`) with a
    locale-independent regex whose separators are Unicode `\\s+`; a value that doesn't match that
    shape (or isn't UTC-suffixed) stays verbatim — a zone-less or unparseable source is never
    guessed at (spec: zone-less sources stay zone-less)."""
    if str(style or "") != _TAKEOUT_EN_UTC:
        return raw
    m = _TAKEOUT_RE.match(raw.strip())
    if m is None:
        return raw
    month = _MONTHS.get(m.group("month"))
    if month is None:
        return raw
    hour = int(m.group("hour")) % 12
    if m.group("ampm") == "PM":
        hour += 12
    return (
        f"{int(m.group('year')):04d}-{month:02d}-{int(m.group('day')):02d}"
        f"T{hour:02d}:{m.group('minute')}:{m.group('second')}Z"
    )


@register_shaper("conversation")
def shape_conversation(
    build: recordbuild.Build,
    post: frontmatter.Post,
    corpus_root: Path,
    mapping: dict[str, Any],
) -> None:
    """Build the `conversation` content zone on `build` from the record's JSON artifact."""
    data = units.load_json_artifact(corpus_root, post)
    messages = units.unit_array(data, mapping)
    event_kinds = {str(k) for k in (mapping.get("event_kinds") or [])}
    ts_style = mapping.get("timestamp_style")

    # First pass: the authorship-ordered codebook (distinct authors, first-appearance order)
    # and the message-id → turn map (for resolving in-record replies). An authored platform
    # event's author IS a participant (the caller / pinner), so it earns a codebook slot too —
    # the author-present test below already includes it.
    codebook: list[str] = []
    index_by_entry: dict[str, int] = {}
    turn_by_msgid: dict[str, int] = {}
    for n, msg in enumerate(messages, start=1):
        mid = units.field(msg, mapping, "message_id")
        if mid is not None:
            turn_by_msgid.setdefault(str(mid), n)
        author_id = units.field(msg, mapping, "author_id")
        author_name = units.field(msg, mapping, "author_name")
        if author_id is None and author_name is None:
            continue  # an author-less platform event — no codebook slot
        entry = _codebook_entry(author_name, author_id)
        if entry not in index_by_entry:
            index_by_entry[entry] = len(codebook)
            codebook.append(entry)

    # A whole-record form section (address omitted, §4.3.2.1) carrying the codebook.
    recordbuild.open_section(build, form="conversation", fields={"participants": codebook})

    seen_topics: set[str] = set()
    for n, msg in enumerate(messages, start=1):
        author_id = units.field(msg, mapping, "author_id")
        author_name = units.field(msg, mapping, "author_name")
        author_present = author_id is not None or author_name is not None
        text = units.field(msg, mapping, "text")
        body = str(text) if text is not None else ""
        timestamp = units.field(msg, mapping, "timestamp")

        # A kind-declared platform event is `text/metadata` even when authored.
        kind_value = units.field(msg, mapping, "kind")
        is_kind_event = kind_value is not None and str(kind_value) in event_kinds
        is_event = (not author_present) or is_kind_event

        # Topic byte-mark at the first unit carrying a not-yet-seen topic value (§4.3.2.3):
        # the producer declares topic MEMBERSHIP per message, so one mark per topic at its
        # birth is the honest declared boundary — per-turn membership stays byte-recoverable
        # via the `turn=` unit op. A topic that recurs adds no second mark.
        topic = units.field(msg, mapping, "topic")
        if topic is not None:
            tkey = str(topic)
            if tkey not in seen_topics:
                seen_topics.add(tkey)
                recordbuild.add_structural(build, address=f"turn={n}", level=1, entry=tkey)

        envelope: dict[str, Any] = {}
        if is_event:
            overlay = "text/metadata"
            if author_present:  # an authored event (a DCE Call/pin) keeps its actor
                envelope["participant"] = index_by_entry[_codebook_entry(author_name, author_id)]
            if is_kind_event:  # the verbatim producer discriminator on the declared field
                envelope["event"] = str(kind_value)
        else:
            overlay = "text/message"
            envelope["participant"] = index_by_entry[_codebook_entry(author_name, author_id)]
        # An empty timestamp value omits the field entirely (a zone-less/blank source is not a
        # timestamp — e.g. Google Chat system messages with an empty created_date).
        if timestamp is not None and str(timestamp).strip():
            envelope["timestamp"] = _normalize_timestamp(str(timestamp), ts_style)
        reply_ref = units.field(msg, mapping, "reply_to")
        if reply_ref is not None and str(reply_ref) in turn_by_msgid:
            envelope["reply_to"] = f"turn={turn_by_msgid[str(reply_ref)]}"

        recordbuild.add_segment(
            build, atom="text", overlay=overlay, address=f"turn={n}",
            body=body or None, extra=envelope,
        )

        # Attachment markers at turn=<N>&att=<M> — body-empty, no embed (lineage-resolvable).
        for m, att in enumerate(units.attachments(msg, mapping), start=1):
            url = units.field(att, mapping, "attachment_url") if isinstance(att, dict) else att
            recordbuild.add_segment(
                build, atom=_attachment_atom(url), address=f"turn={n}&att={m}",
            )
