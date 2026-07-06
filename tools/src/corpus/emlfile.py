"""Shared message/rfc822 (email) helpers — the common axis between the eml drafter
(`draft/eml.py`), the `part=<N>` member transform (`transforms/message.py`), and containment
streaming (`containment.open_member_stream` for a message/rfc822 container). The eml sibling
of `mboxfile` / `ziparchive` / `tararchive`.

**Pinned `part=<N>` addressing (spec §12.11).** N is the 1-indexed position of an
*addressable part* in **depth-first pre-order**: every leaf part, plus every nested
`message/rfc822` part counted as a whole (its sub-message is NOT descended into).
Multipart containers are structure, not addressable — they get no ordinal. A part's member
bytes are its **CTE-decoded** payload (identity is the decoded bytes, not the base64/QP
transfer text; a nested message is its serialized sub-message), so `corpus://<eml>?part=<N>`
round-trips to exactly what `promote` mints. The drafter and the transform share this one
enumeration, so an ordinal is a stable structural coordinate regardless of which parts the
body rendering consumed.
"""

from __future__ import annotations

from email import message_from_bytes, policy
from email.message import EmailMessage, Message
from typing import Any

# A fixed serialization policy for a nested message's decoded bytes — deterministic (CRLF),
# so a nested-message embed's blake3 is stable across drafter and transform.
_SUBMSG_POLICY = policy.SMTP


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


def part_decoded_bytes(part: Message) -> bytes:
    """A part's CTE-decoded payload bytes — the member identity. A nested `message/rfc822`
    part serializes its sub-message deterministically (CRLF); every other part is
    transfer-decoded (base64 / quoted-printable / 7bit / 8bit) to its raw payload."""
    if part.get_content_type() == "message/rfc822":
        try:
            sub = part.get_content()
        except Exception:
            sub = part.get_payload(0)
        if isinstance(sub, Message):
            return sub.as_bytes(policy=_SUBMSG_POLICY)
        return b""
    payload = part.get_payload(decode=True)
    return payload if isinstance(payload, (bytes, bytearray)) else b""


def resolve_part(raw: bytes, ordinal: int) -> bytes:
    """The 1-indexed `ordinal` addressable part's CTE-decoded bytes. Raises `ValueError` when
    the ordinal doesn't exist — the transform surfaces a clean error."""
    if ordinal < 1:
        raise ValueError(f"part={ordinal}: parts are 1-indexed")
    parts = addressable_parts(parse(raw))
    if ordinal > len(parts):
        raise ValueError(
            f"part={ordinal}: no such part (message has {len(parts)} addressable part(s))"
        )
    return part_decoded_bytes(parts[ordinal - 1])


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
