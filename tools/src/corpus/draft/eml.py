"""message/rfc822 draft extraction (deterministic, no LLM; spec §12.11).

Mechanical drafter for a single email message — one promoted out of an mbox
(`corpus://<mbox-id>?msg=<N>`, §8.1) or ingested standalone as an `.eml`. Three moves:

1. **Headers → artifact block** (RFC2047-decoded, single-line, omit-empty): subject (also the
   `title` candidate), from, to / cc / bcc (string-or-list: split per mailbox — a str for one
   recipient, a str[] for several), date, message_id, in_reply_to, references (list, file
   order), thread_id (Gmail `X-GM-THRID`). Thread reconstruction is then a frontmatter
   query — references / in_reply_to ↔ message_id joins across siblings, thread_id groups them.
2. **Body = the reply text only.** Renders the `text/plain` part (else `text/html` reduced to
   text) and mechanically trims trailing **quoted history** (the prior thread lives as its own
   records; raw bytes retain everything) via `corpus.emlfile.body_text` — shared with the
   `block=<N>` resolve transform (`transforms/message.py`, spec §6.2), so a stored `block=`
   address resolves against the SAME extraction its segment was authored from. See
   `emlfile._trim_quoted_history` for the pinned, conservative markers — it prefers false
   negatives (keeps everything when no marker matches confidently). Signatures are part of
   the reply and kept.
3. **Every non-body MIME part → an embed** (the HTML/EPUB embed model). Each attachment, inline
   image, and nested `message/rfc822` becomes a `part=<N>` embed (`transport` = blake3 over the
   CTE-decoded payload, `bytes` = decoded size, plus filename / disposition / content_id), so it
   is promotable (§8.1). The text alternatives the body consumed are skipped (they are content,
   not members). Enumeration + addressing live in `corpus.emlfile` (shared with the transform).

Tolerates the multipart shapes real mail takes: `multipart/alternative` nested in
`multipart/mixed` / `multipart/related`, base64 / quoted-printable, non-UTF-8 charsets.
"""

from __future__ import annotations

import re
from email.utils import getaddresses
from pathlib import Path
from typing import Any

import blake3

from corpus import emlfile, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

_DETECTOR = touches.script_identifier("draft.message/message_rfc822")

# Headers lifted onto the artifact block as `field: value`, RFC2047-decoded, single-line.
# Recipient headers (to/cc/bcc) are string-or-list: split per mailbox, so a roster is
# queryable without re-parsing RFC5322 comma rules downstream.
_SCALAR_HEADERS = (
    ("subject", "Subject"),
    ("from", "From"),
    ("to", "To"),
    ("cc", "Cc"),
    ("bcc", "Bcc"),
    ("date", "Date"),
    ("message_id", "Message-ID"),
    ("in_reply_to", "In-Reply-To"),
)
_ADDRESS_FIELDS = frozenset({"to", "cc", "bcc"})


@register("message/message_rfc822")
def draft(
    binary_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    raw = binary_path.read_bytes()
    try:
        msg = emlfile.parse(raw)
    except Exception:
        return {"issues": [_partial("message could not be parsed as RFC822/MIME.")]}

    fields = _artifact_fields(msg)
    text = emlfile.body_text(msg)
    embeds = _part_embeds(raw, msg)

    if text:
        text_algos = algos_for_atom("text", fingerprint)
        recordbuild.add_blocks(
            build,
            [
                Segment(
                    atom="text",
                    address="block=1",
                    perceptual=text_fingerprints(text, text_algos),
                    body=text,
                )
            ],
        )

    issues: list[dict[str, Any]] = []
    if not text:
        issues.append(
            _partial(
                "message carries no text body (headers on the artifact block, parts as embeds).",
                severity="info",
            )
        )
    return {"fields": fields, "embeds": embeds, "issues": issues}


# ---------- headers → artifact block ---------- #


def _artifact_fields(msg) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, header in _SCALAR_HEADERS:
        value = _addresses(msg, header) if key in _ADDRESS_FIELDS else _header(msg, header)
        if value:
            fields[key] = value
    if subject := fields.get("subject"):
        fields["title"] = subject  # title candidate; the normalizer authors frontmatter title
    if refs := _references(msg):
        fields["references"] = refs
    if thread_id := _header(msg, "X-GM-THRID"):
        fields["thread_id"] = thread_id
    return fields


_NAME_SPECIALS = re.compile(r'[][\\()<>@,:;".]')
_NAME_ESCAPES = re.compile(r'[\\"]')


def _addresses(msg, name: str) -> str | list[str] | None:
    """A recipient header split per mailbox — a str for one address, a str[] for several
    (the corpus string-or-list convention). `getaddresses` does the RFC5322 split, so a comma
    inside a quoted display name (`"Rahn, Steven" <s@x>`) is never a split point. Falls back
    to the raw single-line value when no mailbox parses out (tolerant, never lossy)."""
    value = _header(msg, name)
    if value is None:
        return None
    mailboxes = [_format_mailbox(n, a) for n, a in getaddresses([value]) if (n, a) != ("", "")]
    if not mailboxes:
        return value
    return mailboxes[0] if len(mailboxes) == 1 else mailboxes


def _format_mailbox(name: str, addr: str) -> str:
    """`Name <addr>` with RFC5322 display-name quoting, keeping the name unicode-VERBATIM —
    stdlib `formataddr` would RFC2047-re-encode a non-ASCII name, and the artifact block
    stores decoded values."""
    if not name:
        return addr
    escaped = _NAME_ESCAPES.sub(r"\\\g<0>", name)
    if _NAME_SPECIALS.search(name):
        return f'"{escaped}" <{addr}>'
    return f"{escaped} <{addr}>"


def _header(msg, name: str) -> str | None:
    """A single-line, RFC2047-decoded header value (`policy.default` decodes + unfolds), or
    None. Whitespace collapsed so a folded header reads as one line."""
    value = msg[name]
    if value is None:
        return None
    collapsed = " ".join(str(value).split())
    return collapsed or None


def _references(msg) -> list[str] | None:
    """The `References` message-ids as a list in file order (the thread-join key)."""
    raw = msg["References"]
    if raw is None:
        return None
    ids = re.findall(r"<[^>]+>", str(raw))
    return ids or None


# ---------- non-body parts → embeds ---------- #


def _part_embeds(raw: bytes, msg) -> list[dict[str, Any]]:
    """One embed per addressable part the body did NOT consume — attachments, inline images,
    nested messages. Addressed `part=<N>` over the shared enumeration; `transport` is blake3 of
    the CTE-decoded payload (the promotable member identity)."""
    skip = emlfile.body_skip_ids(msg)
    embeds: list[dict[str, Any]] = []
    parts_and_bytes = emlfile.parts_with_decoded_bytes(raw, msg)
    for ordinal, (part, decoded) in enumerate(parts_and_bytes, start=1):
        if id(part) in skip:
            continue
        media_type, part_fields = emlfile.part_facts(part, decoded)
        embeds.append(
            {
                "media_type": media_type,
                "address": f"part={ordinal}",
                "transport": records.format_hash("blake3", blake3.blake3(decoded).hexdigest()),
                "fields": part_fields,
            }
        )
    return embeds


# ---------- issues ---------- #


def _partial(description: str, *, severity: str = "blocking") -> dict[str, Any]:
    issue: dict[str, Any] = {
        "id": "partial-content",
        "severity": severity,
        "resolution": "open",
        "detector": _DETECTOR,
        "fields": {"description": description},
    }
    if severity == "blocking":
        issue["subtype"] = "empty-body"
    return issue
