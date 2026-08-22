"""Shared message/rfc822 (email) helpers — the common axis between the eml drafter
(`draft/eml.py`), the `part=<N>` member transform (`transforms/message.py`), and containment
streaming (`containment.open_member_stream` for a message/rfc822 container). The eml sibling
of `mboxfile` / `ziparchive` / `tararchive`.

**Pinned `part=<N>` addressing (spec §12.11).** N is the 1-indexed position of an
*addressable part* in **depth-first pre-order**: every leaf part, plus every nested
`message/rfc822` part counted as a whole (its sub-message is NOT descended into).
Multipart containers are structure, not addressable — they get no ordinal. A part's member
bytes are its **CTE-decoded** payload — the payload-identity principle (spec §2, v32): a
nested `message/rfc822` part's CTE is 7bit/8bit/binary (RFC 2046 forbids base64/QP on it), so
its CTE-decoded payload is the **verbatim embedded bytes**, sliced straight out of the
container's own bytes with no re-serialization engine in the identity path — unwrapping is a
pure function of the container bytes, exactly as the identity equation demands. Every other
part is transfer-decoded (base64 / quoted-printable / 7bit / 8bit) by the stdlib, which is
fine there because that decode is a fully-specified pure function too. So
`corpus://<eml>?part=<N>` round-trips to exactly what `promote` mints. The drafter and the
transform share this one enumeration, so an ordinal is a stable structural coordinate
regardless of which parts the body rendering consumed.
"""

from __future__ import annotations

import re
from email import message_from_bytes, policy
from email.message import EmailMessage, Message
from itertools import zip_longest
from typing import Any


def parse(raw: bytes) -> EmailMessage:
    """Parse raw message bytes into an `EmailMessage` (policy.default — decoded headers,
    convenient body/attachment access)."""
    return message_from_bytes(raw, policy=policy.default)


# ---------- addressable-part enumeration (the `part=<N>` axis) ---------- #


def addressable_parts(msg: Message) -> list[Message]:
    """The message's addressable parts in depth-first pre-order: every leaf part, plus every
    `message/rfc822` part as a whole (not descended). Multipart containers are skipped."""
    out: list[Message] = []

    def _rec(part: Message) -> None:
        if part.get_content_type() == "message/rfc822":
            out.append(part)  # a nested message is one addressable unit
            return
        if part.is_multipart():
            for child in part.iter_parts():
                _rec(child)
            return
        out.append(part)

    _rec(msg)
    return out


def part_decoded_bytes(part: Message, *, raw_span: bytes | None = None) -> bytes:
    """A part's CTE-decoded payload bytes — the member identity. A nested `message/rfc822`
    part's identity is `raw_span`: the verbatim bytes as they sit embedded in the container
    (see `_iter_part_spans`) — callers that have the original raw message bytes MUST supply
    it; there is no re-serialization fallback (that would put an engine back in the identity
    path). Every other part is transfer-decoded (base64 / quoted-printable / 7bit / 8bit) to
    its raw payload, which is a fully-specified pure function of the part's own bytes."""
    if part.get_content_type() == "message/rfc822":
        if raw_span is None:
            raise ValueError(
                "part_decoded_bytes: a message/rfc822 part's identity requires raw_span "
                "(the verbatim embedded bytes) — use resolve_part or parts_with_decoded_bytes"
            )
        return raw_span
    payload = part.get_payload(decode=True)
    return payload if isinstance(payload, (bytes, bytearray)) else b""


def _decoded_bytes_for(raw: bytes, part: Message, start: int, end: int) -> bytes:
    """`part_decoded_bytes` given the `(start, end)` span `_iter_part_spans` located for
    `part` — the span IS the raw_span for a message/rfc822 part, and is unused otherwise."""
    span = raw[start:end] if part.get_content_type() == "message/rfc822" else None
    return part_decoded_bytes(part, raw_span=span)


def parts_with_decoded_bytes(raw: bytes, msg: Message) -> list[tuple[Message, bytes]]:
    """`(part, decoded_bytes)` pairs aligned 1:1 with `addressable_parts(msg)` — the
    raw-span-aware decode (a message/rfc822 part's identity sliced verbatim from `raw`, spec
    §2's payload-identity principle) shared by `resolve_part` and the eml drafter's embeds."""
    return [
        (part, _decoded_bytes_for(raw, part, start, end))
        for part, start, end in _iter_part_spans(raw, msg)
    ]


def resolve_part(raw: bytes, ordinal: int) -> bytes:
    """The 1-indexed `ordinal` addressable part's CTE-decoded bytes. Raises `ValueError` when
    the ordinal doesn't exist — the transform surfaces a clean error."""
    if ordinal < 1:
        raise ValueError(f"part={ordinal}: parts are 1-indexed")
    triples = _iter_part_spans(raw, parse(raw))
    if ordinal > len(triples):
        raise ValueError(
            f"part={ordinal}: no such part (message has {len(triples)} addressable part(s))"
        )
    part, start, end = triples[ordinal - 1]
    return _decoded_bytes_for(raw, part, start, end)


# ---------- raw-span location (verbatim bytes for a message/rfc822 part) ---------- #


def _header_body_split(raw: bytes, start: int, end: int) -> int:
    """The byte offset in `[start, end)` where this part's body begins — right after the
    first blank line terminating its own header block (CRLF-CRLF or LF-LF, per RFC 5322/2046).
    No blank line found means an empty body (`end`)."""
    idx = start
    while idx < end:
        eol = raw.find(b"\n", idx, end)
        if eol == -1:
            return end
        line_end = eol + 1
        if raw[idx:line_end] in (b"\r\n", b"\n"):
            return line_end
        idx = line_end
    return end


def _strip_trailing_eol(raw: bytes, start: int, end: int) -> int:
    """`end`, moved back over one trailing CRLF/LF if `[start, end)` ends with one — RFC 2046:
    the line ending immediately before a boundary delimiter belongs to the delimiter, not to
    the preceding part's body."""
    if end - start >= 2 and raw[end - 2 : end] == b"\r\n":
        return end - 2
    if end - start >= 1 and raw[end - 1 : end] == b"\n":
        return end - 1
    return end


def _split_multipart(
    raw: bytes, body_start: int, body_end: int, boundary: str
) -> list[tuple[int, int]]:
    """The `(start, end)` byte span of each part between `--boundary` delimiter lines in
    `raw[body_start:body_end]` (RFC 2046), tolerant of a missing terminal boundary (the last
    part then runs to `body_end`). A span's `end` excludes the CRLF/LF that precedes the next
    delimiter line (see `_strip_trailing_eol`)."""
    boundary_bytes = boundary.encode("ascii", "surrogateescape")
    delim_re = re.compile(
        rb"^--" + re.escape(boundary_bytes) + rb"(--)?[ \t]*(?:\r\n|\n|\Z)", re.MULTILINE
    )
    matches = list(delim_re.finditer(raw, body_start, body_end))
    spans: list[tuple[int, int]] = []
    for i, m in enumerate(matches):
        if m.group(1) is not None:
            break  # close-delimiter: no part begins here
        part_start = m.end()
        next_start = matches[i + 1].start() if i + 1 < len(matches) else body_end
        spans.append((part_start, _strip_trailing_eol(raw, part_start, next_start)))
    return spans


def _iter_part_spans(raw: bytes, msg: Message) -> list[tuple[Message, int, int]]:
    """Depth-first pre-order `(part, start, end)` triples aligned with `addressable_parts(msg)`
    — `raw[start:end]` is that part's payload exactly as it sits in the container: the bytes
    after its own header block, up to (not including) the line ending that precedes the
    enclosing boundary's delimiter. This is the engine-free slice a nested `message/rfc822`
    part's identity is built from (spec §2's payload-identity principle); other parts' spans
    are computed too (kept aligned/simple) but go unused — their identity is the stdlib
    CTE-decode of their own parsed bytes, a fully-specified pure function already."""
    out: list[tuple[Message, int, int]] = []

    def _rec(part: Message, start: int, end: int) -> None:
        body_start = _header_body_split(raw, start, end)
        if part.get_content_type() == "message/rfc822":
            out.append((part, body_start, end))
            return
        if part.is_multipart():
            boundary = part.get_boundary()
            children = list(part.iter_parts())
            child_spans = _split_multipart(raw, body_start, end, boundary) if boundary else []
            for child, child_span in zip_longest(children, child_spans):
                _rec(child, *(child_span if child_span is not None else (end, end)))
            return
        out.append((part, body_start, end))

    _rec(msg, 0, len(raw))
    return out


def part_filename(raw: bytes, ordinal: int) -> str | None:
    """The declared filename of the `ordinal` addressable part, or None — a promoted part's
    origin carries it (spec §7.2 / §8.1) when the attachment names itself."""
    parts = addressable_parts(parse(raw))
    if 1 <= ordinal <= len(parts):
        return parts[ordinal - 1].get_filename()
    return None


# ---------- body selection (which parts the rendered body consumes) ---------- #


def body_part(msg: Message) -> Message | None:
    """The part the body renders from — `text/plain` preferred, else `text/html`."""
    return msg.get_body(preferencelist=("plain", "html"))


def _parent_map(msg: Message) -> dict[int, Message]:
    """Map `id(child) → parent` over the part tree, descending through multipart containers
    but NOT into a nested `message/rfc822` (its sub-tree is opaque)."""
    parents: dict[int, Message] = {}

    def _rec(part: Message) -> None:
        if part.get_content_type() == "message/rfc822":
            return
        if part.is_multipart():
            for child in part.iter_parts():
                parents[id(child)] = part
                _rec(child)

    _rec(msg)
    return parents


def body_skip_ids(msg: Message) -> set[int]:
    """The `id()`s of the parts consumed by rendering the body — skipped as embeds: the chosen
    `text/plain`/`text/html`, plus the text display leaf of each sibling branch of its enclosing
    `multipart/alternative` (the alternative the reader would pick instead). Inline media inside
    an alternative branch is NOT skipped — it stays an embed."""
    body = body_part(msg)
    if body is None:
        return set()
    skip = {id(body)}
    parents = _parent_map(msg)
    node: Message | None = parents.get(id(body))
    while node is not None and node.get_content_type() != "multipart/alternative":
        node = parents.get(id(node))
    if node is not None:
        for branch in node.iter_parts():
            display = branch if not branch.is_multipart() else branch.get_body(
                preferencelist=("html", "plain")
            )
            if (
                display is not None
                and display.get_content_type() in ("text/plain", "text/html")
                and display.get_content_disposition() != "attachment"
            ):
                skip.add(id(display))
    return skip


# ---------- per-part facts (the embed body) ---------- #


def part_facts(part: Message, decoded: bytes) -> tuple[str, dict[str, Any]]:
    """`(media_type, fields)` for a part's embed. `media_type` is the declared content-type,
    refined by a cheap magic sniff only when declared as the generic `application/octet-stream`.
    `fields` carries `bytes` (decoded size), `disposition` (inline|attachment — inferred from a
    Content-ID when undeclared), and `filename` / `content_id` when present."""
    media_type = part.get_content_type()
    if media_type == "application/octet-stream":
        from . import mime as mime_mod

        sniffed = mime_mod.sniff_head(decoded[:512], part.get_filename() or "")
        if sniffed != "unknown":
            media_type = sniffed

    disposition = part.get_content_disposition()
    if disposition is None:
        disposition = "inline" if part.get("Content-ID") else "attachment"

    fields: dict[str, Any] = {"bytes": len(decoded), "disposition": disposition}
    if filename := part.get_filename():
        fields["filename"] = filename
    if cid := part.get("Content-ID"):
        fields["content_id"] = str(cid).strip().lstrip("<").rstrip(">")
    return media_type, fields
