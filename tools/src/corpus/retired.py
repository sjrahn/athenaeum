"""What ATH-CORPUS 3.5 and 3.7 retired from the record grammar — the ONE definition.

A retired field has no successor (§12.27), so recognizing one is a pure question about a
record: which constructs does it carry that the grammar no longer admits? Two callers ask
it, for opposite reasons —

- `drop_retired` removes them from the records that already carry them (§12.27/§12.29) —
  the migration;
- `corpus compile` refuses a rebuild that **acquires** one (#116) — the contract.

Retirement needs both. The sweep alone is undone by the next write: a 20-record normalize
pilot (2026-08-07) wrote **+17** retired `entry:` fields against -2 removed — roughly one
per record — every one of them through `compile` and past `lint` at zero errors. Two
definitions of "retired" would drift the same way one sweep and no gate did, so the census
lives here, once, and both callers read it.

The census counts; it never judges. Whether carrying a retired field is fine (it is —
~7,300 records do), whether it may be removed mechanically (the sweep's holds), and whether
acquiring one is refusable (the gate) are all the caller's business.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from corpus import records, segments

#: Context-block namespaces 3.5 retired outright (§4.3.3.3, §4.3.3.5).
RETIRED_NAMESPACES = frozenset({"relation", "reference"})

#: Stored detector verdicts about a DERIVED value — a health query, not an annotation
#: (§12.21). Matched on the `issue` namespace's block id.
RETIRED_ISSUE_IDS = frozenset({"generic-title"})

#: Section header fields the universal-slot retirement removes (§4.3.2.1). `entry` and
#: `description` are dataclass fields; `title` rides `Section.extra`.
SECTION_EXTRA_FIELDS = ("title",)

#: Frontmatter fields with no successor: the `canonical:` hash and the editorial override
#: pair, retired with the interpretive rung they belonged to (§4.2.1).
FRONTMATTER_FIELDS = ("canonical", "title", "description")

#: Where each label's construct left the grammar — the amendment and the section that says
#: so. A refusal that names the field without naming the retirement is an assertion; this
#: makes it a citation. Keys are exactly the labels `census` emits.
RETIRED_AT: dict[str, tuple[str, str]] = {
    "frontmatter canonical": ("3.5", "§4.2.1"),
    "frontmatter title": ("3.5", "§4.2.1"),
    "frontmatter description": ("3.5", "§4.2.1"),
    "section title": ("3.5", "§4.3.2.1"),
    "section description": ("3.5", "§4.3.2.1"),
    "section entry": ("3.5", "§4.3.2.1"),
    "section address": ("3.7", "§4.3.2.1"),
    "segment description": ("3.5", "§4.3.2.2"),
    "segment entry": ("3.5", "§4.3.2.2"),
    "context reference": ("3.5", "§4.3.3.3"),
    "context relation": ("3.5", "§4.3.3.5"),
    "context issue/generic-title": ("3.5", "§12.21"),
}

SECTION_OPENER_RE = re.compile(r"^<!--section(?: |$)", re.M)
_CLOSER = "-->"


def cite(label: str) -> str:
    """`"3.5, §4.3.2.1"` for a census label — the amendment that retired it and where the
    spec says so. Empty for a label the table does not know, which is a caller's bug rather
    than a record's problem, so it degrades quietly."""
    at = RETIRED_AT.get(label)
    return f"{at[0]}, {at[1]}" if at else ""


def stored_section_addresses(text: str) -> int:
    """How many section headers in `text` still carry the retired `address:` field (§12.29).
    Counted off the raw bytes, because once parsed the stored value is indistinguishable from
    the derived one that replaced it."""
    count = 0
    for opener in SECTION_OPENER_RE.finditer(text):
        end = text.find(_CLOSER, opener.end())
        if end == -1:
            continue
        if re.search(r"^address:", text[opener.end() : end], re.M):
            count += 1
    return count


def retired_contexts(post: Any) -> list[dict[str, Any]]:
    """The record's context blocks whose namespace — or, for `issue`, whose block id — 3.5
    retired, in record order."""
    out = []
    for ctx in post.metadata.get("_contexts") or []:
        ns = str(ctx.get("namespace") or "")
        if ns in RETIRED_NAMESPACES or (
            ns == "issue" and str(ctx.get("id") or "") in RETIRED_ISSUE_IDS
        ):
            out.append(ctx)
    return out


def census(post: Any, text: str = "") -> Counter[str]:
    """Every retired construct `post` carries, under stable labels. Pure: reads, counts,
    mutates nothing.

    `text` is the record's serialized bytes, needed only for the construct that becomes
    invisible once parsed — a section's stored `address:`, which `iter_blocks` re-derives
    from the children (§12.29). Omit it when the caller holds only a parsed record; that one
    count is then simply not taken.

    A label appears only when its count is non-zero, so an empty Counter means "carries
    nothing retired" and reads as false.
    """
    counts: Counter[str] = Counter()

    for key in FRONTMATTER_FIELDS:
        if key in post.metadata:
            counts[f"frontmatter {key}"] += 1

    for ctx in retired_contexts(post):
        ns, cid = str(ctx.get("namespace") or ""), str(ctx.get("id") or "")
        counts[f"context {ns}/{cid}" if ns == "issue" else f"context {ns}"] += 1

    # Parse tolerantly: a content zone that will not parse carries no countable header
    # fields, and saying WHY belongs to the caller, which can say it far better than a
    # count can (the sweep holds the record; compile's parse raises where it always did).
    try:
        blocks = segments.iter_blocks(post.content or "")
    except Exception:
        blocks = []

    for blk in blocks:
        if isinstance(blk, segments.Section):
            if blk.description is not None:
                counts["section description"] += 1
            if blk.entry is not None:
                counts["section entry"] += 1
            for key in SECTION_EXTRA_FIELDS:
                if key in blk.extra:
                    counts[f"section {key}"] += 1
        for seg in blk.segments if isinstance(blk, segments.Section) else [blk]:
            if seg.description is not None:
                counts["segment description"] += 1
            # The structural byte-mark's own field is untouched: it was never the content
            # segment's `entry:` (§4.3.2.3), and the parser folds it into the body anyway.
            if seg.entry is not None and not seg.is_structural:
                counts["segment entry"] += 1

    if text:
        stored = stored_section_addresses(text)
        if stored:
            counts["section address"] += stored

    return counts


def census_text(text: str) -> Counter[str]:
    """`census` of a record's serialized bytes. A text that will not even load as a record
    carries nothing this can see — the caller that needs to say so has better standing."""
    if not text.strip():
        return Counter()
    try:
        post = records.loads(text)
    except Exception:
        return Counter()
    return census(post, text)


def gained(before: Counter[str], after: Counter[str]) -> dict[str, tuple[int, int]]:
    """Labels whose count ROSE, as `label → (before, after)`.

    The asymmetry is the whole gate: acquiring a retired field is refusable, carrying one is
    not. ~7,300 records carry one today and every one of them must still compile."""
    return {k: (before.get(k, 0), c) for k, c in after.items() if c > before.get(k, 0)}
