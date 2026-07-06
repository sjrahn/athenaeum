"""Shared mbox helpers — the common axis between the `mbox-manifest` drafter
(`draft/mbox_manifest.py`), the `msg=<N>` member transform (`transforms/mbox.py`), and
containment streaming (`containment.open_member_stream`). The mbox sibling of
`ziparchive` / `tararchive`.

An mbox is a flat concatenation of RFC822 messages, each introduced by a `From `
separator line (mboxrd). This module owns the **pinned extraction semantics** (spec
§12.11), so a message's member bytes are deterministic and promotable (§8.1):

- A **separator** is any line beginning with `From ` (mboxrd). Ordinals are 1-indexed in
  file order.
- Message N's bytes are everything AFTER separator line N (the separator line and its
  terminator excluded) up to but NOT including separator line N+1 (or EOF) — verbatim,
  including a trailing blank line before the next separator; line terminators preserved
  (this corpus's real export is CRLF).
- **Un-stuffing** (mboxrd): within the message bytes, a line matching `^>+From ` loses
  exactly one leading `>`. Member bytes — hence the member blake3 — are computed over the
  UN-STUFFED bytes, so a promoted message round-trips as a standalone `message/rfc822`.

Every scan streams line-by-line — a mailbox can be multiple GB and a single message tens
of MB — so nothing here ever materializes the whole mailbox (or a whole message) in RAM.
"""

from __future__ import annotations

import email
import io
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import IO

import blake3

# A separator is any line starting with `From ` (mboxrd, spec §12.11). Binary line
# iteration keeps the terminator, so `^From ` on the raw line bytes is exact.
_SEP_RE = re.compile(rb"^From ")
# mboxrd stuffing: one-or-more `>` immediately before `From ` — un-stuff by dropping one `>`.
_STUFF_RE = re.compile(rb"^>+From ")

# Cap the header buffer so a malformed message with no header/body boundary can't grow the
# accumulator without bound (headers are small; a real message reaches a blank line fast).
_HEADER_CAP = 1 << 20
# asctime shapes the `From ` envelope date takes — with or without a timezone (Gmail adds
# `+0000`); parsed only for the mailbox summary's date span.
_SEP_DATE_FORMATS = ("%a %b %d %H:%M:%S %z %Y", "%a %b %d %H:%M:%S %Y")


def _unstuff(line: bytes) -> bytes:
    """Drop exactly one leading `>` from a `^>+From ` line (mboxrd un-stuffing); else
    return the line unchanged. Applied to every message line so member bytes are the true
    RFC822 bytes."""
    return line[1:] if _STUFF_RE.match(line) else line


# ---------- streaming member access (containment / transform) ---------- #


def _message_body_lines(line_iter: Iterator[bytes]) -> Iterator[bytes]:
    """Yield the un-stuffed line bytes of the current message — everything up to (but not
    including) the next separator line. Assumes `line_iter` is positioned just after the
    message's own separator."""
    for line in line_iter:
        if _SEP_RE.match(line):
            return
        yield _unstuff(line)


class _MemberReader(io.RawIOBase):
    """A read-only raw stream over an iterator of message line-bytes — lets the un-stuffed
    member bytes flow through `read()` without ever holding the whole message. Wrapped in a
    `BufferedReader` by `open_member` so callers get exact-length reads."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buf = b""
        self._eof = False

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        want = len(b)
        while len(self._buf) < want and not self._eof:
            try:
                self._buf += next(self._chunks)
            except StopIteration:
                self._eof = True
        n = min(want, len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


@contextmanager
def open_member(mbox_path: Path, ordinal: int) -> Iterator[IO[bytes]]:
    """Stream the 1-indexed `ordinal` message's un-stuffed bytes as `message/rfc822`
    (spec §12.11). Scans the mailbox to separator N (reading and discarding earlier lines),
    then yields a binary reader over message N that stops at separator N+1 — so only the
    bytes up to and including the target message are ever touched. Raises `ValueError` when
    the ordinal doesn't exist."""
    if ordinal < 1:
        raise ValueError(f"msg={ordinal}: ordinals are 1-indexed")
    with mbox_path.open("rb") as fh:
        line_iter = iter(fh)
        seen = 0
        for line in line_iter:
            if _SEP_RE.match(line):
                seen += 1
                if seen == ordinal:
                    break
        else:
            raise ValueError(f"msg={ordinal}: no such message (mbox holds {seen} message(s))")
        reader = io.BufferedReader(_MemberReader(_message_body_lines(line_iter)))
        yield reader


def resolve_member(mbox_path: Path, ordinal: int) -> bytes:
    """The 1-indexed `ordinal` message's un-stuffed bytes, whole. Streams to the message and
    reads it (a single message is bounded; the mailbox is never loaded whole). Raises
    `ValueError` when the ordinal doesn't exist — the transform surfaces a clean error."""
    with open_member(mbox_path, ordinal) as fp:
        return fp.read()


# ---------- single-pass scan (drafter) ---------- #


@dataclass
class MessageFacts:
    """The per-message facts the manifest drafter records: the un-stuffed member's blake3
    identity + byte length, plus the RFC2047-decoded, single-line Date / From / Subject."""

    ordinal: int
    blake3: str
    bytes: int
    date: str | None
    sender: str | None
    subject: str | None


@dataclass
class MboxScan:
    """The result of one streaming pass: the total message count, the per-ordinal facts for
    the requested messages, and the first/last separator lines (for the mailbox date span)."""

    count: int
    facts: dict[int, MessageFacts]
    first_sep: bytes | None
    last_sep: bytes | None


def scan(mbox_path: Path, ordinals: set[int] | frozenset[int]) -> MboxScan:
    """One streaming pass over the mailbox: count every message, capture the first/last
    separator lines, and for each requested 1-indexed `ordinal` compute the un-stuffed
    member's blake3 + byte length and parse its Date / From / Subject headers. Never holds
    the mailbox (or a whole message) in RAM. Raises `ValueError` when a requested ordinal
    exceeds the message count."""
    wanted = frozenset(ordinals)
    facts: dict[int, MessageFacts] = {}
    total = 0
    first_sep: bytes | None = None
    last_sep: bytes | None = None
    cur: dict | None = None

    def _close(acc: dict) -> None:
        facts[acc["ordinal"]] = _finalize(acc)

    with mbox_path.open("rb") as fh:
        for line in fh:
            if _SEP_RE.match(line):
                if cur is not None:
                    _close(cur)
                    cur = None
                total += 1
                if first_sep is None:
                    first_sep = line
                last_sep = line
                if total in wanted:
                    cur = {
                        "ordinal": total,
                        "b3": blake3.blake3(),
                        "bytes": 0,
                        "header": bytearray(),
                        "header_open": True,
                    }
                continue
            if cur is not None:
                data = _unstuff(line)
                cur["b3"].update(data)
                cur["bytes"] += len(data)
                if cur["header_open"]:
                    if data in (b"\r\n", b"\n"):
                        cur["header_open"] = False
                    elif len(cur["header"]) < _HEADER_CAP:
                        cur["header"] += data
        if cur is not None:
            _close(cur)

    missing = sorted(n for n in wanted if n not in facts)
    if missing:
        raise ValueError(
            f"mbox holds {total} message(s); requested ordinal(s) out of range: {missing}"
        )
    return MboxScan(count=total, facts=facts, first_sep=first_sep, last_sep=last_sep)


def _finalize(acc: dict) -> MessageFacts:
    msg = BytesParser(policy=policy.compat32).parsebytes(bytes(acc["header"]), headersonly=True)
    return MessageFacts(
        ordinal=acc["ordinal"],
        blake3=acc["b3"].hexdigest(),
        bytes=acc["bytes"],
        date=_decode_header(msg.get("Date")),
        sender=_decode_header(msg.get("From")),
        subject=_decode_header(msg.get("Subject")),
    )


def _decode_header(value: str | None) -> str | None:
    """RFC2047-decode a header to a single line (collapsing folded whitespace), or None."""
    if not value:
        return None
    try:
        decoded = str(email.header.make_header(email.header.decode_header(value)))
    except Exception:
        decoded = value
    collapsed = " ".join(decoded.split())
    return collapsed or None


# ---------- mailbox summary (drafter) ---------- #


def date_span(first_sep: bytes | None, last_sep: bytes | None) -> tuple[str, str] | None:
    """The mailbox's (start, end) ISO-8601 date range parsed from the first/last `From `
    separator lines, or None when either can't be parsed. Cheap — the separator date is on
    the envelope line itself, so no message body is read (spec §12.11 summary)."""
    a = _parse_sep_date(first_sep)
    b = _parse_sep_date(last_sep)
    if a is None or b is None:
        return None
    lo, hi = sorted((a, b))
    return lo.isoformat(), hi.isoformat()


def _parse_sep_date(sep_line: bytes | None) -> datetime | None:
    """Parse the trailing asctime date off a `From <sender> <date>` separator line."""
    if not sep_line:
        return None
    text = sep_line.decode("utf-8", "replace").rstrip("\r\n")
    parts = text.split(None, 2)
    if len(parts) < 3:
        return None
    raw = parts[2].strip()
    for fmt in _SEP_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None
