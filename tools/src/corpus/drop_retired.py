"""The §12.27/§12.29 field sweep: remove what ATH-CORPUS 3.5 and 3.7 retired.

The subtractive half of the faithfulness amendment's migration (spec §12.27). Six things
came out of the record grammar in 3.5, and five of them are pure subtraction — a field or
a block family with **no successor**, which is exactly why the sweep needs no judgment
anywhere:

- the frontmatter `canonical:` hash (disabled on the write path 2026-06-28, never swept),
- the section header's editorial fields — `title:`, `description:`, `entry:` — retired with
  the universal-section-field slot itself (§4.3.2.1: a section declares a form and binds
  its contract, nothing more),
- the segment header's `description:` (§4.3.2.2: a segment cannot narrate its own region),
- the segment header's `entry:` on CONTENT segments — the 1.0-2.x TOC-label fossil
  (§4.3.2.2). The structural byte-mark's field is untouched: it was never the same field,
  and `segments` already reads it tolerantly and re-emits it as `mark:` (§4.3.2.3),
- the annotation zone's retired namespaces — `relation` and `reference` context blocks
  (§4.3.3.3/§4.3.3.5) — plus `issue/generic-title`, a detector's verdict about a *derived*
  value that computes on demand (§12.21).

And *(3.7, §12.29)* two more of the same kind:

- the frontmatter editorial **override** pair (`title:` / `description:`), retired in 3.5
  alongside the interpretive rung it belonged to (§4.2.1) and missed by this engine's first
  cut — two records across both hubs carried one;
- the section header's **`address:`**, the span envelope that is now derived from the
  children who define it (§4.3.2.1). This one needs no mutation at all: the serializer
  stopped writing it, so re-serializing the record removes it. What the engine adds is the
  accounting — the count, and a stability guard that licenses *that* difference and nothing
  else.

The sixth retirement is the `relation` rail's **restoration** as a trailing index span, and
it is deliberately NOT here: it is additive, per-host, and needs the origin overlay's region
declaration (§7.2). Run it first where it applies — this verb refuses a record whose rail
would otherwise be dropped without having come home (`--allow-unrestored` to override, for
the populations where the overlay names no rail region).

An abolished field has no successor, so subtraction needs no re-homing decision per record
(the 3.4 precedent, restated in §12.27). Two consequences are worth naming rather than
discovering:

- **A dropped description is not migrated anywhere.** Where prose was standing in front of
  an untranscribed region, the honest residue is a typed `issue` at that address, which is
  a closable worklist item rather than a paragraph — `--issue-unrendered` writes them.
- **Derived title/description change.** Both were resolving off the form layer on a formed
  record (§4.2.3's ladder); with the section fields gone they fall to the origin or artifact
  layer. That is the correct answer — but it is visible, so the manifest records the before
  and after for every record whose derived title moves.

Same discipline as the §12.28 remap this follows: compute, never write; refuse rather than
guess; and **the neutrality gate** — a record whose rewrite would raise ANY lint rule's
finding count is HELD, not swept.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from corpus import functional_uri as furi
from corpus import lint, records, segments, touches

#: Touch identifier stamped on every record the sweep rewrites.
TOUCH_ID = "migrate.faithfulness-35"

#: Context-block namespaces 3.5 retired outright (§4.3.3.3, §4.3.3.5).
RETIRED_NAMESPACES = frozenset({"relation", "reference"})

#: Stored detector verdicts about a DERIVED value — a health query, not an annotation
#: (§12.21). Matched on the `issue` namespace's block id.
RETIRED_ISSUE_IDS = frozenset({"generic-title"})

#: Section header fields the universal-slot retirement removes (§4.3.2.1). `entry` and
#: `description` are dataclass fields; `title` rides `Section.extra`.
_SECTION_EXTRA_DROPS = ("title",)

#: Frontmatter editorial overrides — retired in 3.5 with the interpretive rung (§4.2.1).
_FRONTMATTER_DROPS = ("canonical", "title", "description")


class DropHold(ValueError):
    """The record cannot be swept mechanically — held with a reason, never guessed."""


@dataclass
class RecordDrop:
    """One record's sweep outcome. `changed` means a rewrite was produced (and applied,
    when the caller asked for apply); `hold` carries the refusal reason when not."""

    record_id: str
    relpath: str
    changed: bool = False
    skipped: str | None = None
    hold: str | None = None
    counts: Counter[str] = dataclass_field(default_factory=Counter)
    title_before: str = ""
    title_after: str = ""
    description_before: str = ""
    emit_normalized: bool = False
    new_text: str | None = None


_SECTION_OPENER_RE = re.compile(r"^<!--section(?: |$)", re.M)
_CLOSER = "-->"


def _stored_section_fields(text: str) -> int:
    """How many section headers in `text` still carry the retired `address:` field (§12.29).
    Counted off the raw bytes, because once parsed the stored value is indistinguishable from
    the derived one that replaced it."""
    count = 0
    for opener in _SECTION_OPENER_RE.finditer(text):
        end = text.find(_CLOSER, opener.end())
        if end == -1:
            continue
        if re.search(r"^address:", text[opener.end() : end], re.M):
            count += 1
    return count


def _reserialized_section_headers(text: str) -> int:
    """How many section headers `text` spells in the pre-3.7 multi-line form where the
    current serializer would write the one-line bare opener (`<!--section index-->`). Not a
    field removal — the shape a removed field leaves behind — but it is the same change and it
    is disclosed the same way."""
    count = 0
    for m in re.finditer(r"^<!--section(?: [^\n>]*)?\n(?:[^\n]*\n)*?-->$", text, re.M):
        body = m.group(0).split("\n")[1:-1]
        if not [ln for ln in body if ln.strip()]:
            count += 1
    return count


def _outside_section_headers(text: str) -> str:
    """`text` with every section-header block replaced by its form id alone.

    The textual stability guard's job is to catch drift the engine did not intend. After 3.7
    the section header is exactly where intended change lands — the `address:` line goes and
    an emptied header collapses to a one-line bare opener — so the guard compares everything
    ELSE byte-for-byte and leaves the header to the block-level round-trip check, which is
    stricter about what a header may mean than any line diff could be."""
    return re.sub(
        r"^<!--section(?: [^\n>]*?)?(?:-->|\n(?:[^\n]*\n)*?-->)$",
        lambda m: "<!--section " + (m.group(0).split("\n")[0]
                                    .removeprefix("<!--section").removesuffix("-->").strip()),
        text,
        flags=re.M,
    )


def _lint_tally(findings: list[lint.Finding]) -> Counter[str]:
    return Counter(f.rule_id for f in findings)


def _neutrality_hold(new_text: str, before: Counter[str], corpus_root: Path) -> str | None:
    """Return a hold reason when the rewritten record would lint WORSE than the original —
    any rule whose finding count rises — else None. The whole rule set deliberately: the
    failure worth catching is the unpredicted one (the §12.28 lesson)."""
    try:
        after_post = records.loads(new_text)
        after = _lint_tally(
            lint.lint(after_post, segments.iter_blocks(after_post.content or ""), corpus_root)
        )
    except Exception as exc:  # a record whose rewrite cannot even be linted is a hold
        return f"post-sweep lint did not run: {exc}"
    risen = {r: (before.get(r, 0), c) for r, c in after.items() if c > before.get(r, 0)}
    if not risen:
        return None
    detail = ", ".join(f"{r} {b}→{a}" for r, (b, a) in sorted(risen.items()))
    return f"the rewrite would introduce new lint findings ({detail})"


def _retired_contexts(post: Any) -> list[dict[str, Any]]:
    """The context blocks this sweep removes, in record order."""
    out = []
    for ctx in post.metadata.get("_contexts") or []:
        ns = str(ctx.get("namespace") or "")
        if ns in RETIRED_NAMESPACES or (
            ns == "issue" and str(ctx.get("id") or "") in RETIRED_ISSUE_IDS
        ):
            out.append(ctx)
    return out


def _el_paths(value: Any) -> list[furi.ElPath]:
    """Every `el=` address in `value` (scalar or list) as a parsed §6.1.1 path. A non-`el=`
    axis or an unparseable value contributes nothing — containment is only meaningful
    within one axis."""
    out = []
    for raw in segments._iter_addr_strings(value):
        head, _, tail = str(raw).partition("=")
        if head != "el":
            continue
        try:
            out.append(furi.parse_el_path(tail.split("&", 1)[0]))
        except Exception:
            continue
    return out


def _restored(ctx: dict[str, Any], sections: list[segments.Section]) -> bool:
    """Whether this retired `relation` block's address is claimed by an `index` span — the
    §6.1.1 containment test against the span's own address and its child segments'. A
    record-scoped block (no address) can never be shown to have come home, and a
    whole-record `index` section (no address) claims nothing in particular, so neither
    counts: both are exactly the pre-restoration shape."""
    targets = _el_paths((ctx.get("fields") or {}).get("address"))
    if not targets:
        return False
    claims: list[furi.ElPath] = []
    for sec in sections:
        if sec.form != "index" or sec.address is None:
            continue
        claims.extend(_el_paths(sec.address))
        for child in sec.segments:
            claims.extend(_el_paths(child.address))
    return all(any(furi.el_path_contains(c, t) for c in claims) for t in targets)


def _derived_pair(post: Any, corpus_root: Path) -> tuple[str, str]:
    """`(title, description)` as the §4.2.3 ladder resolves them — read before and after so
    the manifest can disclose a display change instead of letting one land unannounced."""
    try:
        title, description = records.derived_editorial(post, corpus_root)
    except Exception:
        return "", ""
    return str(title or ""), str(description or "")


def sweep_record(
    record_file: Path,
    corpus_root: Path,
    *,
    allow_unrestored: bool = False,
) -> RecordDrop:
    """Compute (never write) the §12.27 sweep of one record. The caller applies
    `report.new_text` when `report.changed`; a `hold` means hands off."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = RecordDrop(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    doomed_contexts = _retired_contexts(post)
    doomed_frontmatter = [k for k in _FRONTMATTER_DROPS if k in post.metadata]

    def _section_carries(sec: segments.Section) -> bool:
        return bool(
            sec.description is not None
            or sec.entry is not None
            or any(k in sec.extra for k in _SECTION_EXTRA_DROPS)
        )

    def _segment_carries(seg: segments.Segment) -> bool:
        if seg.description is not None:
            return True
        return seg.entry is not None and not seg.is_structural

    all_segments = [
        seg
        for blk in blocks
        for seg in ([blk] if isinstance(blk, segments.Segment) else list(blk.segments))
    ]
    sections = [b for b in blocks if isinstance(b, segments.Section)]

    stored_addresses = _stored_section_fields(original)
    stale_headers = _reserialized_section_headers(original)

    if not (
        doomed_contexts
        or doomed_frontmatter
        or stored_addresses
        or stale_headers
        or any(_section_carries(s) for s in sections)
        or any(_segment_carries(s) for s in all_segments)
    ):
        report.skipped = "carries nothing 3.5/3.7 retired"
        return report

    # The rail's restoration is additive and lives elsewhere (§12.27). Dropping a
    # `relation` block on a record whose links never came home is data loss, not a sweep.
    #
    # "Came home" is tested per BLOCK, by §6.1.1 containment against the addresses an
    # `index` span actually claims — not by "the record has an index span somewhere". The
    # weaker test is wrong on a real and large population: 786 alldata records were fitted
    # WHOLE-RECORD to `form/index` by the 3.2 form-adopt sweep, so an index span exists on
    # them while nothing renders the rail at all, and the loose reading would have dropped
    # 9,182 rail links from records that never restored one.
    if not allow_unrestored:
        relations = [c for c in doomed_contexts if str(c.get("namespace")) == "relation"]
        homeless = [c for c in relations if not _restored(c, sections)]
        if homeless:
            report.hold = (
                f"{len(homeless)} of {len(relations)} `relation` block(s) sit at an address no "
                f"`form/index` span claims — restore the rail first (§12.27), or pass "
                f"--allow-unrestored"
            )
            return report

    # Serializer stability: the rewrite goes through the real serializer, so the only
    # differences it may introduce must be intended or disclosed (the §12.28 rule).
    #
    # *(3.7)* One difference is now intended on every legacy record — the serializer no longer
    # writes a section's `address:`, because the envelope is derived (§12.29). So the baseline
    # is the record's own canonical re-serialization, and the ONLY licensed difference between
    # it and the bytes on disk is the removal of `address:` lines from section headers. Any
    # other drift is still a hold.
    baseline = records.dumps(post)
    if _outside_section_headers(baseline) != _outside_section_headers(original):
        report.hold = "record is not dumps-stable; the serializer would introduce unrelated changes"
        return report
    content = post.content or ""
    emitted = segments.emit(blocks) if blocks else ""
    try:
        reparsed = segments.iter_blocks(emitted)
    except ValueError as exc:
        report.hold = f"content zone does not survive an emit round-trip: {exc}"
        return report
    if reparsed != blocks:
        # *(3.7)* The commonest instance of this is worth naming rather than shrugging at: a
        # section whose STORED envelope is not the one its children derive. Dropping the field
        # then changes a claim instead of removing a duplicate of it, which is a deliberate
        # re-addressing (the §12.28 `--override` precedent), not a sweep.
        drifted = [
            (str(a.address), str(b.address))
            for a, b in zip(blocks, reparsed, strict=False)
            if isinstance(a, segments.Section) and a.address != b.address
        ]
        if drifted:
            detail = "; ".join(f"stored `{o}` vs derived `{n}`" for o, n in drifted)
            report.hold = (
                f"stored section envelope is not what its children derive ({detail}) — the "
                f"stored value over- or under-claims, so removing it changes a claim; "
                f"re-address the span deliberately (§12.29)"
            )
        else:
            report.hold = "content zone does not survive an emit round-trip losslessly"
        return report
    report.emit_normalized = emitted.rstrip("\n") != content.rstrip("\n")
    trailing = content[len(content.rstrip("\n")) :]

    before_findings = _lint_tally(lint.lint(post, blocks, corpus_root))
    report.title_before, report.description_before = _derived_pair(post, corpus_root)

    # ---- the subtraction ----
    if stored_addresses:
        # Nothing to mutate: the serializer already omits it and `iter_blocks` derives it.
        # Counted so the manifest says what came off rather than leaving it to a diff.
        report.counts["section address"] += stored_addresses
    if stale_headers:
        report.counts["section header → bare opener"] += stale_headers

    for key in doomed_frontmatter:
        post.metadata.pop(key, None)
        report.counts[f"frontmatter {key}"] += 1

    for sec in sections:
        if sec.description is not None:
            sec.description = None
            report.counts["section description"] += 1
        if sec.entry is not None:
            sec.entry = None
            report.counts["section entry"] += 1
        for key in _SECTION_EXTRA_DROPS:
            if key in sec.extra:
                sec.extra.pop(key)
                report.counts[f"section {key}"] += 1

    for seg in all_segments:
        if seg.description is not None:
            seg.description = None
            report.counts["segment description"] += 1
        if seg.entry is not None and not seg.is_structural:
            seg.entry = None
            report.counts["segment entry"] += 1

    if doomed_contexts:
        keep = [c for c in (post.metadata.get("_contexts") or []) if c not in doomed_contexts]
        post.metadata["_contexts"] = keep
        for ctx in doomed_contexts:
            ns, cid = str(ctx.get("namespace") or ""), str(ctx.get("id") or "")
            report.counts[f"context {ns}/{cid}" if ns == "issue" else f"context {ns}"] += 1

    post.content = segments.emit(blocks).rstrip("\n") + trailing
    touches.record_touch(post, touches.script_identifier(TOUCH_ID))
    new_text = records.dumps(post)

    hold = _neutrality_hold(new_text, before_findings, corpus_root)
    if hold:
        report.hold = hold
        return report

    report.title_after, _ = _derived_pair(records.loads(new_text), corpus_root)
    report.changed = True
    report.new_text = new_text
    return report
