"""JSON-family field strip — the span-surgical remover (spec §12.3.14, the mailbox chrome
strip's amendment to any JSON-family export).

A producer origin overlay may declare `strip_fields`: a declarative list of dotted key
paths (`a.b`, `[]` permitted for array traversal — `messages[].callEndedTimestamp`)
removed from a JSON document **before identity**. Removal is SPAN-SURGICAL: the matched
object member's `"key": <value>` bytes are deleted in place, plus exactly one adjacent
comma (the trailing comma when the member isn't last, else the preceding one) — every
byte the producer did not name stays exactly where it was, precisely as the mailbox
header strip leaves body lines untouched. The document is NEVER re-parsed-and-
re-serialized, re-ordered, or re-encoded: `json.loads` + `json.dumps` would renormalize
whitespace/key order/number formatting and silently destroy the "everything else
untouched" guarantee, so this module hand-rolls a byte-offset-preserving scanner instead
of going through the stdlib decoder.

Removal always targets an OBJECT MEMBER — never a bare array element — matching every
`strip_fields` example in the spec (`exportedAt`, `guild.iconUrl`,
`messages[].callEndedTimestamp`): a dotted path's segments are all navigation (descend
into a key, optionally iterating an array of objects via trailing `[]`) except the LAST,
which names the key actually removed within whatever object the navigation reached.

Parse-tolerant at the PATH level (a segment naming a key that doesn't exist, or descending
through a non-object/non-array where one was expected, is a silent no-op — the producer's
declaration may simply not match this particular document) but NOT at the JSON level: a
malformed document raises `JSONParseError` — the caller decides whether that's fatal or a
"leave it alone" signal (ingest treats it as not-canonicalizable, §12.3.14).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_WS = b" \t\n\r"
_SIMPLE_ESCAPES = {
    0x22: 0x22,  # \"
    0x5C: 0x5C,  # \\
    0x2F: 0x2F,  # \/
    0x62: 0x08,  # \b
    0x66: 0x0C,  # \f
    0x6E: 0x0A,  # \n
    0x72: 0x0D,  # \r
    0x74: 0x09,  # \t
}


class JSONParseError(ValueError):
    """Raised when `parse()` hits malformed JSON. Carries the byte offset in its message
    so a caller can report *where* the document broke."""


# ---------- byte-offset-preserving scanner ---------- #


@dataclass
class Member:
    """One object member — the removal unit. `key_start` is the offset of the key's
    opening quote; `value_end` is one past the last byte of the value. `comma_before` /
    `comma_after` are the offsets of the adjacent commas (within the parent object),
    or None when this member is first / last respectively."""

    key: str
    key_start: int
    value_end: int
    value: Node
    comma_before: int | None = None
    comma_after: int | None = None


@dataclass
class Node:
    """One parsed JSON value. `kind` is `object` | `array` | `scalar` (string / number /
    boolean / null — scalars carry no further structure, only their byte span, since
    `strip_fields` never needs to inspect a value's content). `start`/`end` bound the
    value's own bytes (`data[start:end]`)."""

    kind: str
    start: int
    end: int
    members: list[Member] = field(default_factory=list)  # kind == "object"
    elements: list[Node] = field(default_factory=list)  # kind == "array"


class _Parser:
    __slots__ = ("data", "i", "n")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.n = len(data)
        self.i = 0

    def _error(self, msg: str) -> None:
        raise JSONParseError(f"malformed JSON at byte {self.i}: {msg}")

    def _skip_ws(self) -> None:
        data, n = self.data, self.n
        i = self.i
        while i < n and data[i] in _WS:
            i += 1
        self.i = i

    def parse_value(self) -> Node:
        self._skip_ws()
        if self.i >= self.n:
            self._error("unexpected end of input")
        c = self.data[self.i]
        if c == 0x7B:  # {
            return self._parse_object()
        if c == 0x5B:  # [
            return self._parse_array()
        if c == 0x22:  # "
            start = self.i
            self._parse_string()
            return Node("scalar", start, self.i)
        if c == 0x2D or 0x30 <= c <= 0x39:  # '-' or digit
            start = self.i
            self._skip_number()
            return Node("scalar", start, self.i)
        if self.data[self.i : self.i + 4] == b"true":
            start = self.i
            self.i += 4
            return Node("scalar", start, self.i)
        if self.data[self.i : self.i + 5] == b"false":
            start = self.i
            self.i += 5
            return Node("scalar", start, self.i)
        if self.data[self.i : self.i + 4] == b"null":
            start = self.i
            self.i += 4
            return Node("scalar", start, self.i)
        self._error(f"unexpected byte {chr(c)!r}")
        raise AssertionError("unreachable")  # _error always raises; satisfies type-checkers

    def _parse_string(self) -> str:
        """Parse a JSON string starting at the opening quote (`self.i`); returns the
        DECODED content (escapes resolved, `\\uXXXX` surrogate pairs combined, raw UTF-8
        bytes decoded) — used for both keys (compared against path segments) and value
        strings (decoded value discarded by callers that only need the span)."""
        self.i += 1  # opening quote
        raw = bytearray()
        pending_high: int | None = None
        data, n = self.data, self.n
        while True:
            if self.i >= n:
                self._error("unterminated string")
            c = data[self.i]
            if c == 0x22:  # closing quote
                self.i += 1
                break
            if c == 0x5C:  # backslash
                self.i += 1
                if self.i >= n:
                    self._error("unterminated escape")
                esc = data[self.i]
                if esc == 0x75:  # \u
                    self.i += 1
                    hex4 = data[self.i : self.i + 4]
                    if len(hex4) != 4:
                        self._error("truncated \\u escape")
                    try:
                        codepoint = int(hex4, 16)
                    except ValueError:
                        self._error("invalid \\u escape")
                    self.i += 4
                    if 0xD800 <= codepoint <= 0xDBFF:
                        pending_high = codepoint
                        continue
                    if 0xDC00 <= codepoint <= 0xDFFF and pending_high is not None:
                        combined = 0x10000 + (pending_high - 0xD800) * 0x400 + (codepoint - 0xDC00)
                        raw.extend(chr(combined).encode("utf-8"))
                        pending_high = None
                        continue
                    pending_high = None
                    raw.extend(chr(codepoint).encode("utf-8", errors="surrogatepass"))
                    continue
                simple = _SIMPLE_ESCAPES.get(esc)
                if simple is None:
                    self._error(f"invalid escape '\\{chr(esc)}'")
                raw.append(simple)
                self.i += 1
                continue
            if c < 0x20:
                self._error("unescaped control character in string")
            raw.append(c)
            self.i += 1
        return bytes(raw).decode("utf-8", errors="surrogatepass")

    def _skip_number(self) -> None:
        data, n = self.data, self.n
        start = self.i
        if self.i < n and data[self.i] == 0x2D:  # '-'
            self.i += 1
        if self.i >= n or not (0x30 <= data[self.i] <= 0x39):
            self._error("invalid number")
        if data[self.i] == 0x30:  # leading zero: exactly one digit
            self.i += 1
        else:
            while self.i < n and 0x30 <= data[self.i] <= 0x39:
                self.i += 1
        if self.i < n and data[self.i] == 0x2E:  # '.'
            self.i += 1
            if self.i >= n or not (0x30 <= data[self.i] <= 0x39):
                self._error("invalid number (fraction)")
            while self.i < n and 0x30 <= data[self.i] <= 0x39:
                self.i += 1
        if self.i < n and data[self.i] in (0x65, 0x45):  # e / E
            self.i += 1
            if self.i < n and data[self.i] in (0x2B, 0x2D):
                self.i += 1
            if self.i >= n or not (0x30 <= data[self.i] <= 0x39):
                self._error("invalid number (exponent)")
            while self.i < n and 0x30 <= data[self.i] <= 0x39:
                self.i += 1
        if self.i == start:
            self._error("invalid number")

    def _parse_object(self) -> Node:
        start = self.i
        self.i += 1  # '{'
        members: list[Member] = []
        self._skip_ws()
        if self.i < self.n and self.data[self.i] == 0x7D:
            self.i += 1
            return Node("object", start, self.i, members=members)
        prev_comma: int | None = None
        while True:
            self._skip_ws()
            if self.i >= self.n or self.data[self.i] != 0x22:
                self._error("expected string key")
            key_start = self.i
            key = self._parse_string()
            self._skip_ws()
            if self.i >= self.n or self.data[self.i] != 0x3A:  # ':'
                self._error("expected ':' after key")
            self.i += 1
            self._skip_ws()
            value_node = self.parse_value()
            member = Member(
                key=key,
                key_start=key_start,
                value_end=self.i,
                value=value_node,
                comma_before=prev_comma,
            )
            members.append(member)
            self._skip_ws()
            if self.i >= self.n:
                self._error("unterminated object")
            c = self.data[self.i]
            if c == 0x2C:  # ','
                member.comma_after = self.i
                prev_comma = self.i
                self.i += 1
                continue
            if c == 0x7D:  # '}'
                self.i += 1
                break
            self._error("expected ',' or '}'")
        return Node("object", start, self.i, members=members)

    def _parse_array(self) -> Node:
        start = self.i
        self.i += 1  # '['
        elements: list[Node] = []
        self._skip_ws()
        if self.i < self.n and self.data[self.i] == 0x5D:
            self.i += 1
            return Node("array", start, self.i, elements=elements)
        while True:
            self._skip_ws()
            elements.append(self.parse_value())
            self._skip_ws()
            if self.i >= self.n:
                self._error("unterminated array")
            c = self.data[self.i]
            if c == 0x2C:
                self.i += 1
                continue
            if c == 0x5D:
                self.i += 1
                break
            self._error("expected ',' or ']'")
        return Node("array", start, self.i, elements=elements)


def parse(data: bytes) -> Node:
    """Parse `data` into a byte-offset-preserving `Node` tree. Raises `JSONParseError` on
    any malformed input (unterminated string/object/array, bad escape, bad number,
    trailing garbage after the top-level value, empty input)."""
    parser = _Parser(data)
    node = parser.parse_value()
    parser._skip_ws()
    if parser.i != parser.n:
        parser._error("trailing content after JSON value")
    return node


# ---------- dotted-path declarations ---------- #


@dataclass(frozen=True)
class _PathStep:
    key: str
    array_depth: int  # number of trailing "[]" markers on this segment (usually 0 or 1)


def _parse_dotted_path(path: str) -> tuple[_PathStep, ...] | None:
    """Parse one `strip_fields` entry (`a.b`, `a[].b`) into steps, or None when the path
    is structurally empty/malformed (an empty segment, or a segment that's ONLY `[]` with
    no key) — a bad path entry is a silent no-op, not a raise (declarative-list
    tolerance; one bad entry can't break the others)."""
    steps: list[_PathStep] = []
    for seg in path.split("."):
        key = seg
        depth = 0
        while key.endswith("[]"):
            key = key[:-2]
            depth += 1
        if not key:
            return None
        steps.append(_PathStep(key=key, array_depth=depth))
    return tuple(steps) if steps else None


def normalize_strip_fields(
    paths: list[str] | tuple[str, ...] | None,
) -> list[tuple[_PathStep, ...]] | None:
    """Dotted path strings → parsed matchers, or None when `paths` is empty/absent (no
    stripping) or every entry is structurally malformed."""
    if not paths:
        return None
    parsed: list[tuple[_PathStep, ...]] = []
    for raw in paths:
        text = str(raw).strip()
        if not text:
            continue
        steps = _parse_dotted_path(text)
        if steps is not None:
            parsed.append(steps)
    return parsed or None


def _collect_removals(
    node: Node, steps: tuple[_PathStep, ...], out: list[tuple[Node, int]]
) -> None:
    """Walk `node` along `steps`, appending every matched removal target as
    `(parent_object_node, member_index)` to `out` — the index (not just the `Member`
    itself) is what lets `strip_spans` later group CONSECUTIVE removed siblings into
    runs (needed to get comma removal right when neighbors are removed together, e.g.
    the last two members of an object both stripped). Tolerant throughout: a step whose
    key is absent, or that descends through a non-object/non-array where the path
    expects one, simply contributes nothing further — the declaration may not apply to
    this particular document. Duplicate keys at any level all match (every occurrence is
    collected)."""
    if not steps or node.kind != "object":
        return
    step, rest = steps[0], steps[1:]
    for idx, member in enumerate(node.members):
        if member.key != step.key:
            continue
        if not rest and step.array_depth == 0:
            out.append((node, idx))
            continue
        if not rest:
            # A trailing "[]" naming no further key removes nothing (every spec example
            # terminates in a bare key) — deliberate no-op, not an error.
            continue
        targets: list[Node] = [member.value]
        for _ in range(step.array_depth):
            nxt: list[Node] = []
            for t in targets:
                if t.kind == "array":
                    nxt.extend(t.elements)
            targets = nxt
        for t in targets:
            _collect_removals(t, rest, out)


def strip_spans(
    data: bytes, matchers: list[tuple[_PathStep, ...]] | None
) -> tuple[bytes, int]:
    """Remove every `strip_fields` match from `data`, span-surgically. Returns
    `(stripped_bytes, removed_count)` — `removed_count` is the number of DISTINCT object
    members actually removed (across every matcher, every duplicate key, every array
    element `[]` fanned out to); `(data, 0)` when nothing matches (or `matchers` is
    empty/None) — the caller reads a `0` count as "already canonical, no rewrite needed."

    Raises `JSONParseError` on malformed JSON — this function never repairs bytes, only
    removes declared spans from a document it can fully parse.

    Removed members are grouped into CONSECUTIVE runs per parent object before cutting:
    a lone removed member takes its own trailing comma (or, if it's the object's last
    member, the preceding one) exactly as the contract describes; but when two or more
    ADJACENT siblings are removed together, only the RUN's outer edges matter — the
    comma after the run's last member (if a surviving sibling follows) or the comma
    before the run's first member (if the run reaches the object's end) — never both,
    and never a per-member decision that could strand a comma nothing separates anymore
    (independent per-member cuts would otherwise leave a dangling trailing comma when
    the run absorbs the object's last member).
    """
    if not matchers:
        return data, 0
    root = parse(data)
    hits: list[tuple[Node, int]] = []
    for steps in matchers:
        _collect_removals(root, steps, hits)
    if not hits:
        return data, 0

    by_node: dict[int, tuple[Node, set[int]]] = {}
    for node, idx in hits:
        key = id(node)
        if key not in by_node:
            by_node[key] = (node, set())
        by_node[key][1].add(idx)

    cuts: list[list[int]] = []
    removed_count = 0
    for node, idx_set in by_node.values():
        indices = sorted(idx_set)
        removed_count += len(indices)
        run: list[int] = [indices[0]]
        for idx in indices[1:]:
            if idx == run[-1] + 1:
                run.append(idx)
                continue
            cuts.append(_run_cut(node, run))
            run = [idx]
        cuts.append(_run_cut(node, run))
    cuts.sort()

    # Merge overlapping/touching cuts across DIFFERENT parent objects at the same nesting
    # level (can't happen structurally, but merging defensively costs nothing) into
    # contiguous delete ranges; `removed_count` still counts members, not merged ranges.
    merged: list[list[int]] = []
    for start, end in cuts:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    out = bytearray()
    pos = 0
    for start, end in merged:
        out += data[pos:start]
        pos = end
    out += data[pos:]
    return bytes(out), removed_count


def _run_cut(node: Node, run: list[int]) -> list[int]:
    """The `[start, end)` byte range to delete for one run of consecutive removed
    member indices within `node.members`: the trailing comma when a surviving member
    follows the run, else the preceding comma when the run reaches the object's start,
    else (the run is every member) no comma at all."""
    first_m, last_m = node.members[run[0]], node.members[run[-1]]
    start, end = first_m.key_start, last_m.value_end
    if last_m.comma_after is not None:
        end = last_m.comma_after + 1
    elif first_m.comma_before is not None:
        start = first_m.comma_before
    return [start, end]
