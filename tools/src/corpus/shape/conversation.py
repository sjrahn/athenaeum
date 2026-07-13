"""The generic mapping-driven `conversation` shaper (spec §7.8, §12.5.0, §12.18 step 4).

Reads a JSON producer's messages via the origin overlay's `form.mapping` (§7.2) and emits the
`form/conversation` decomposition (§7.8): a `<!--section conversation-->` carrying the
authorship-ordered `participants:` codebook, one `text/message` per message at `turn=<N>`
(codebook `participant:` index, source-stated timestamp, in-record `reply_to`), `text/metadata`
for author-less platform events, and attachment markers at `turn=<N>&att=<M>` (no embed —
lineage-resolvable, §4.3.1.4). One shaper serves Discord / Google Chat / Facebook / Instagram /
Threads and any future JSON chat producer — the difference is the overlay's mapping, not code.

Mapping keys consumed: `messages` (dotted path to the unit array), `author_id`, `author_name`,
`timestamp`, `text`, `message_id`, `reply_to`, `attachments`, `attachment_url`.
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

    # First pass: the authorship-ordered codebook (distinct authors, first-appearance order)
    # and the message-id → turn map (for resolving in-record replies).
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
            continue  # a platform event — not an authored message, no codebook slot
        entry = _codebook_entry(author_name, author_id)
        if entry not in index_by_entry:
            index_by_entry[entry] = len(codebook)
            codebook.append(entry)

    # A whole-record form section (address omitted, §4.3.2.1) carrying the codebook.
    recordbuild.open_section(build, form="conversation", fields={"participants": codebook})

    for n, msg in enumerate(messages, start=1):
        author_id = units.field(msg, mapping, "author_id")
        author_name = units.field(msg, mapping, "author_name")
        text = units.field(msg, mapping, "text")
        body = str(text) if text is not None else ""
        timestamp = units.field(msg, mapping, "timestamp")

        envelope: dict[str, Any] = {}
        is_event = author_id is None and author_name is None
        if is_event:
            overlay = "text/metadata"
        else:
            overlay = "text/message"
            envelope["participant"] = index_by_entry[_codebook_entry(author_name, author_id)]
        if timestamp is not None:
            envelope["timestamp"] = str(timestamp)
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
