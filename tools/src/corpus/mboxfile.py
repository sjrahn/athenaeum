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
from datetime import UTC, datetime
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


def normalize_strip_headers(names: list[str] | tuple[str, ...] | None) -> frozenset[bytes] | None:
    """Header names → the lowercase `name:`-prefixed byte forms `HeaderStrip` matches on,
    or None when the list is empty/absent (no stripping)."""
    if not names:
        return None
    return frozenset(n.strip().lower().encode() + b":" for n in names if n.strip())


def normalize_exclude_members(
    predicates: list[dict[str, object]] | None,
) -> dict[bytes, frozenset[str]] | None:
    """Predicate list (spec v37: `[{header: <name>, contains: [<label>, ...]}, ...]`) →
    `{lowercased "name:" byte prefix: frozenset(labels)}` for `MemberExcluder`, or None
    when the list is empty/absent (no exclusion). Uses the SAME byte-prefix convention as
    `normalize_strip_headers` so both filters walk the header zone identically. Multiple
    predicate entries naming the same header pool their labels."""
    if not predicates:
        return None
    by_header: dict[bytes, set[str]] = {}
    for entry in predicates:
        name = str((entry or {}).get("header") or "").strip()
        if not name:
            continue
        key = name.lower().encode() + b":"
        labels = (entry or {}).get("contains") or ()
        by_header.setdefault(key, set()).update(str(v).strip() for v in labels if str(v).strip())
    if not by_header:
        return None
    return {k: frozenset(v) for k, v in by_header.items()}


class MemberExcluder:
    """Per-member evaluator for the `exclude_members` predicate (spec v37, §12.3.13): a
    POLICY filter, not canonicalization — a member whose named header's value contains
    any declared label is excluded (captured nowhere, by design). Watches the declared
    header name(s) in the header zone with the SAME zone/continuation tracking as
    `HeaderStrip`, but `observe()` is called on the un-stuffed line BEFORE `HeaderStrip.
    keep()` runs on it — read-then-strip, one pass — so a header that strip ALSO removes
    is still seen. Call `reset()` at each member's separator; `observe(data)` on every
    un-stuffed line in the header zone, in caller order, ahead of the stripper."""

    def __init__(self, by_header: dict[bytes, frozenset[str]]) -> None:
        self._by_header = by_header
        self._in_header = True
        self._capturing: bytes | None = None
        self._values: dict[bytes, bytearray] = {}

    def reset(self) -> None:
        self._in_header = True
        self._capturing = None
        self._values = {}

    def observe(self, data: bytes) -> None:
        if not self._in_header:
            return
        if data in (b"\r\n", b"\n"):
            self._in_header = False
            self._capturing = None
            return
        if self._capturing is not None and data[:1] in (b" ", b"\t"):
            # RFC 5322 unfolding: the fold (CRLF) is what's dropped, the continuation's
            # own content joins with a single space — good enough for a comma-split
            # label list, which is the only shape this predicate matches against.
            self._values[self._capturing] += b" " + data.strip()
            return
        self._capturing = None
        lowered = data.lower()
        for name in self._by_header:
            if lowered.startswith(name):
                self._values[name] = bytearray(data[len(name) :].strip())
                self._capturing = name
                return

    @property
    def excluded(self) -> bool:
        for name, buf in self._values.items():
            declared = self._by_header.get(name, frozenset())
            found = {p.strip() for p in buf.decode("utf-8", "replace").split(",")}
            if found & declared:
                return True
        return False


class HeaderStrip:
    """Per-member filter dropping the declared headers (spec §12.3.13, the mailbox chrome
    strip): a matching header line and its folded continuations are removed from the
    HEADER ZONE ONLY — a body line that happens to start with the name is never touched.
    Call `reset()` at each member's separator; `keep(data)` on each un-stuffed line."""

    def __init__(self, names: frozenset[bytes]) -> None:
        self._names = names
        self._in_header = True
        self._skipping = False
        self.dropped = 0  # lines dropped for the CURRENT member (read before reset)

    def reset(self) -> None:
        self._in_header = True
        self._skipping = False
        self.dropped = 0

    def keep(self, data: bytes) -> bool:
        if not self._in_header:
            return True
        if data in (b"\r\n", b"\n"):
            self._in_header = False
            self._skipping = False
            return True
        if self._skipping and data[:1] in (b" ", b"\t"):
            self.dropped += 1
            return False
        self._skipping = False
        lowered = data.lower()
        for name in self._names:
            if lowered.startswith(name):
                self._skipping = True
                self.dropped += 1
                return False
        return True


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


def extract_raw_members(
    mbox_path: Path,
    ordinals: set[int] | frozenset[int],
    out: IO[bytes],
    *,
    strip: frozenset[bytes] | None = None,
) -> int:
    """Copy the 1-indexed `ordinals` members RAW — separator line plus stuffed message
    lines, verbatim, in file order — onto `out`, producing a valid mboxrd whose members
    keep byte-for-byte the identities the source held (spec §12.3.13: the window bundle's
    emit path; un-stuffed member blake3 is unchanged by the copy). With `strip`
    (`normalize_strip_headers` output), declared header lines are dropped from each
    emitted member — the mailbox chrome strip; the keep-decision reads the un-stuffed
    line, the emission writes the raw line. One streaming pass; returns the number of
    members written. Raises `ValueError` when an ordinal doesn't exist."""
    wanted = frozenset(ordinals)
    if any(n < 1 for n in wanted):
        raise ValueError("ordinals are 1-indexed (>= 1)")
    stripper = HeaderStrip(strip) if strip else None
    written = 0
    copying = False
    total = 0
    with mbox_path.open("rb") as fh:
        for line in fh:
            if _SEP_RE.match(line):
                total += 1
                copying = total in wanted
                if copying:
                    written += 1
                    if stripper:
                        stripper.reset()
                    out.write(line)
                continue
            if copying:
                if stripper and not stripper.keep(_unstuff(line)):
                    continue
                out.write(line)
    missing = sorted(n for n in wanted if n > total)
    if missing:
        raise ValueError(
            f"mbox holds {total} message(s); requested ordinal(s) out of range: {missing}"
        )
    return written


def demux_raw_members(
    mbox_path: Path,
    sinks: dict[int, IO[bytes]],
    *,
    strip: frozenset[bytes] | None = None,
) -> int:
    """Route each 1-indexed member — separator line plus raw lines, with `strip` applied
    exactly as in `extract_raw_members` — to its ordinal's sink, in ONE streaming pass:
    the year-split demux (spec §12.3.13). Ordinals absent from `sinks` are skipped.
    Returns the number of members written."""
    stripper = HeaderStrip(strip) if strip else None
    out: IO[bytes] | None = None
    total = 0
    written = 0
    with mbox_path.open("rb") as fh:
        for line in fh:
            if _SEP_RE.match(line):
                total += 1
                out = sinks.get(total)
                if out is not None:
                    written += 1
                    if stripper:
                        stripper.reset()
                    out.write(line)
                continue
            if out is not None:
                if stripper and not stripper.keep(_unstuff(line)):
                    continue
                out.write(line)
    return written


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
    the requested messages, and the first/last separator lines (for the mailbox date span).
    `stripped_members` counts members the header strip touched (0 when no strip ran).
    `excluded_ordinals` holds the 1-indexed ordinals the `exclude_members` predicate (spec
    v37) matched — a policy filter, evaluated BEFORE the strip on the same pass, so it
    still sees a header the strip also removes; empty when no predicate ran. `facts` still
    holds an entry for an excluded ordinal (its blake3/bytes are computed the same as any
    other member) — callers decide what "excluded" means for their own output, `scan`
    only reports the verdict."""

    count: int
    facts: dict[int, MessageFacts]
    first_sep: bytes | None
    last_sep: bytes | None
    stripped_members: int = 0
    excluded_ordinals: frozenset[int] = frozenset()


def scan(
    mbox_path: Path,
    ordinals: set[int] | frozenset[int] | None,
    *,
    strip: frozenset[bytes] | None = None,
    exclude: dict[bytes, frozenset[str]] | None = None,
) -> MboxScan:
    """One streaming pass over the mailbox: count every message, capture the first/last
    separator lines, and for each requested 1-indexed `ordinal` compute the un-stuffed
    member's blake3 + byte length and parse its Date / From / Subject headers. `None`
    requests facts for EVERY message — the full enumeration the window-reduction dedup
    (spec §12.3.13) keys on. With `strip` (`normalize_strip_headers` output), the declared
    headers are dropped before hashing — facts describe the member AS-IF-STRIPPED, which
    is how a pre-strip snapshot serves as lineage across the strip boundary. With `exclude`
    (`normalize_exclude_members` output), each member's declared header is evaluated
    BEFORE the strip removes it (read-then-strip, one pass, spec v37) and a match's
    ordinal lands in `MboxScan.excluded_ordinals`. Never holds the mailbox (or a whole
    message) in RAM. Raises `ValueError` when a requested ordinal exceeds the message
    count."""
    wanted = None if ordinals is None else frozenset(ordinals)
    stripper = HeaderStrip(strip) if strip else None
    excluder = MemberExcluder(exclude) if exclude else None
    facts: dict[int, MessageFacts] = {}
    total = 0
    stripped_members = 0
    excluded_ordinals: set[int] = set()
    first_sep: bytes | None = None
    last_sep: bytes | None = None
    cur: dict | None = None

    def _close(acc: dict) -> None:
        nonlocal stripped_members
        facts[acc["ordinal"]] = _finalize(acc)
        if stripper and stripper.dropped:
            stripped_members += 1
        if excluder and excluder.excluded:
            excluded_ordinals.add(acc["ordinal"])

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
                if wanted is None or total in wanted:
                    if stripper:
                        stripper.reset()
                    if excluder:
                        excluder.reset()
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
                if excluder:
                    excluder.observe(data)
                if stripper and not stripper.keep(data):
                    continue
                cur["b3"].update(data)
                cur["bytes"] += len(data)
                if cur["header_open"]:
                    if data in (b"\r\n", b"\n"):
                        cur["header_open"] = False
                    elif len(cur["header"]) < _HEADER_CAP:
                        cur["header"] += data
        if cur is not None:
            _close(cur)

    if wanted is not None:
        missing = sorted(n for n in wanted if n not in facts)
        if missing:
            raise ValueError(
                f"mbox holds {total} message(s); requested ordinal(s) out of range: {missing}"
            )
    return MboxScan(
        count=total,
        facts=facts,
        first_sep=first_sep,
        last_sep=last_sep,
        stripped_members=stripped_members,
        excluded_ordinals=frozenset(excluded_ordinals),
    )


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
    # `_SEP_DATE_FORMATS` mixes a tz-aware and a naive spelling — one mailbox's first/last
    # separator can parse to one of each (e.g. a Gmail export with an offset on some envelope
    # lines and none on others), and comparing an aware/naive pair raises TypeError. Order by
    # a UTC-normalized key (naive treated as already-UTC) but return the ORIGINAL parsed
    # values, unconverted, so the reported span still reflects what was actually on the line.
    lo, hi = sorted((a, b), key=lambda dt: dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC))
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
