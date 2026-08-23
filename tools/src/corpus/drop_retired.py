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

The sixth retirement is the `relation` rail's **restoration** as a trailing `form/nav` span
(#89 — `form/index` before it, on a record no re-spell has reached yet), and it is
deliberately NOT here: it is additive, per-host, and needs the origin overlay's region
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
from corpus import lint, records, retired, segments, touches

#: Touch identifier stamped on every record the sweep rewrites.
TOUCH_ID = "migrate.faithfulness-35"

# WHAT is retired lives in `corpus.retired` — one definition, shared with the write-side
# gate that keeps this sweep from being undone by the next compile (#116). This module owns
# only the removal: what may be taken out mechanically, and what must be held instead.


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


_FRONTMATTER_BLOCK_RE = re.compile(r"\A(---\n)(.*?\n)(---\n)", re.DOTALL)
_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):", re.M)


def _license_v20_frontmatter_rename(text: str) -> str:
    """*(v20)* `records.dumps()` now UNCONDITIONALLY folds a legacy `transport:` key
    into `hash:` and drops `canonical:`/`perceptual:` (spec §4.2.1) — a difference it
    introduces on every load→dump cycle of a record still carrying those keys, not
    something this sweep asked for. That is exactly the kind of intended, disclosed
    difference `_outside_section_headers` already licenses for a section's `address:`
    line (§12.28's rule: "the only differences the serializer may introduce must be
    intended or disclosed") — this licenses the other one, on the RAW-disk side of the
    stability comparison, so a record merely carrying legacy frontmatter fields doesn't
    itself trip the guard before the sweep does anything. `retired.census`'s own
    accounting reads the true `original` text separately and is unaffected.

    Operates only within the frontmatter delimiter span (`---\\n...\\n---\\n`) — a
    member row's own `transport:` field (§2, unchanged vocabulary) lives in the body
    and is never touched.
    """
    m = _FRONTMATTER_BLOCK_RE.match(text)
    if not m:
        return text
    fm = m.group(2)
    starts = [mm.start() for mm in _TOP_LEVEL_KEY_RE.finditer(fm)] + [len(fm)]
    spans = [fm[starts[i] : starts[i + 1]] for i in range(len(starts) - 1)]
    has_hash = any(s.startswith("hash:") for s in spans)
    kept: list[str] = []
    for span in spans:
        if span.startswith("canonical:") or span.startswith("perceptual:"):
            continue
        if span.startswith("transport:"):
            if has_hash:
                continue  # dumps() drops a redundant legacy transport: outright
            span = "hash:" + span[len("transport:") :]
        kept.append(span)
    return text[: m.start(2)] + "".join(kept) + text[m.end(2) :]


def _outside_section_headers(text: str) -> str:
    """`text` with every section-header block removed entirely.

    The textual stability guard's job is to catch drift the engine did not intend. After 3.7 the
    section header is exactly where intended change lands — the `address:` line goes, an emptied
    header collapses to a one-line bare opener, and two adjacent same-form spans become one — so
    the guard compares everything ELSE byte-for-byte and leaves the headers to the block-level
    round-trip check, which is stricter about what a header MEANS than any line diff could be:
    it compares parsed Sections and Segments, field for field."""
    return re.sub(
        r"^<!--section(?: [^\n>]*?)?(?:-->|\n(?:[^\n]*\n)*?-->)\n?",
        "",
        text,
        flags=re.M,
    )


def _content_is_stale(text: str) -> bool:
    """Whether the record's stored content zone differs from what the current grammar emits —
    the canonicalizations 3.7 introduced (bare opener, no envelope, adjacent same-form spans
    merged). Parse-tolerant: a zone that will not parse is not stale, it is broken, and the
    round-trip check below says so with a better message."""
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    try:
        blocks = segments.iter_blocks(records.loads(text).content or "")
    except Exception:
        return False
    if not blocks:
        return False
    try:
        emitted = segments.emit(blocks)
    except Exception:
        return False
    stored = (records.loads(text).content or "")
    del body
    return emitted.rstrip("\n") != stored.rstrip("\n")


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


def _el_paths(value: Any) -> list[furi.ElPath]:
    """Every `el=` address in `value` (scalar or list) as a parsed §6.1.1 DOTTED path. A
    non-`el=` axis or an unparseable value contributes nothing — containment is only
    meaningful within one axis. Frozen-grammar only; see `_el_claims` for the
    record-dispatched version `_restored` actually uses."""
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


def _el_claims(value: Any, ordinal_scheme: bool) -> list[furi.ElPath | furi.ElOrdinal]:
    """Every `el=` address in `value` as a parsed §6.1.1 claim, under the RECORD's own
    grammar (`ordinal_scheme`, read off `records.el_addressing`, never sniffed from the
    value) — `furi.ElOrdinal` (v35) or the frozen dotted `furi.ElPath`. A non-`el=` axis
    or an unparseable value contributes nothing."""
    if ordinal_scheme:
        out: list[furi.ElOrdinal] = []
        for raw in segments._iter_addr_strings(value):
            head, _, tail = str(raw).partition("=")
            if head != "el":
                continue
            try:
                out.append(furi.parse_el_ordinal(tail.split("&", 1)[0]))
            except Exception:
                continue
        return out
    return _el_paths(value)


def _el_claims_contain(outer: Any, inner: Any) -> bool:
    """Whether `outer`'s claim contains `inner`'s — dispatched by the claim TYPE (both are
    always parsed under the same record's single grammar, so this is a type check, not
    value-sniffing). The ordinal side has no tree access here (`_restored` operates on
    stored address text alone, no artifact), so it is the conservative NUMERIC proxy
    (`furi.ordinal_contains`, §6.1.1: "not decidable from two addresses alone") — sound,
    never a false positive, possibly missing a genuine ancestor relationship the numbers
    alone can't show."""
    if isinstance(outer, furi.ElOrdinal) and isinstance(inner, furi.ElOrdinal):
        return furi.ordinal_contains(outer, inner)
    if isinstance(outer, furi.ElPath) and isinstance(inner, furi.ElPath):
        return furi.el_path_contains(outer, inner)
    return False


#: The form ids a framing restoration span may carry (#89): `nav` going forward, `index` for a
#: record `corpus home-rail` / `corpus home-crumb` restored before `form/nav` existed and
#: nothing has yet re-spelled. Keyed explicitly to these two rather than to "any form" — the
#: claim test is about recognizing the rail's own home, not about tolerating an address
#: collision with unrelated content.
_RESTORED_FORMS = ("nav", "index")


def _restored(
    ctx: dict[str, Any], sections: list[segments.Section], *, ordinal_scheme: bool = False
) -> bool:
    """Whether this retired `relation` block's address is claimed by a framing-restoration
    span (`form/nav`, or the pre-#89 `form/index` spelling) — the §6.1.1 containment test
    against the span's own address and its child segments'. A record-scoped block (no address)
    can never be shown to have come home, and a whole-record section with no address claims
    nothing in particular, so neither counts: both are exactly the pre-restoration shape.

    `ordinal_scheme` (v35) is the RECORD's own grammar (`records.el_addressing`, never
    sniffed) — every claim here, target and candidate alike, is parsed under it via
    `_el_claims`, and compared via `_el_claims_contain`."""
    targets = _el_claims((ctx.get("fields") or {}).get("address"), ordinal_scheme)
    if not targets:
        return False
    claims: list[Any] = []
    for sec in sections:
        if sec.form not in _RESTORED_FORMS or sec.address is None:
            continue
        claims.extend(_el_claims(sec.address, ordinal_scheme))
        for child in sec.segments:
            claims.extend(_el_claims(child.address, ordinal_scheme))
    return all(any(_el_claims_contain(c, t) for c in claims) for t in targets)


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

    # The census is the shared definition of what 3.5/3.7 retired (`corpus.retired`); this
    # engine's job is what it may then DO about it. Taken off the record as it stands, before
    # any mutation, so the same counts serve the skip test above and the manifest below.
    carried = retired.census(post, original)
    doomed_contexts = retired.retired_contexts(post)

    all_segments = [
        seg
        for blk in blocks
        for seg in ([blk] if isinstance(blk, segments.Segment) else list(blk.segments))
    ]
    sections = [b for b in blocks if isinstance(b, segments.Section)]

    stale_headers = _reserialized_section_headers(original)

    canonicalizes = _content_is_stale(original)

    if not (carried or stale_headers or canonicalizes):
        report.skipped = "carries nothing 3.5/3.7 retired"
        return report

    # The rail's restoration is additive and lives elsewhere (§12.27). Dropping a
    # `relation` block on a record whose links never came home is data loss, not a sweep.
    #
    # "Came home" is tested per BLOCK, by §6.1.1 containment against the addresses a `nav`
    # (or as-yet-unconverged legacy `index`) span actually claims — not by "the record has a
    # framing span somewhere". The weaker test is wrong on a real and large population: 786
    # alldata records were fitted WHOLE-RECORD to `form/index` by the 3.2 form-adopt sweep, so
    # an index span exists on them while nothing renders the rail at all, and the loose reading
    # would have dropped 9,182 rail links from records that never restored one.
    if not allow_unrestored:
        el_addressing = records.el_addressing(post)
        ordinal_scheme = bool(el_addressing) and el_addressing.get("scheme") == "ordinal"
        relations = [c for c in doomed_contexts if str(c.get("namespace")) == "relation"]
        homeless = [
            c for c in relations if not _restored(c, sections, ordinal_scheme=ordinal_scheme)
        ]
        if homeless:
            report.hold = (
                f"{len(homeless)} of {len(relations)} `relation` block(s) sit at an address no "
                f"`form/nav` span claims — restore the rail first (§12.27), or pass "
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
    normalized_original = _license_v20_frontmatter_rename(original)
    if _outside_section_headers(baseline) != _outside_section_headers(normalized_original):
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
    if report.emit_normalized:
        # The content zone as the CURRENT grammar spells it differs from what is stored. That
        # difference is this verb's business, not an accident: it is the bare opener, the
        # dropped envelope, and 3.7's collapse of adjacent same-form spans (§4.3.2.1) — each a
        # canonicalization the grammar implies rather than a judgment anyone makes. Writing it
        # is what makes the sweep leave a record in the shape a fresh parse would produce.
        stored_sections = len(retired.SECTION_OPENER_RE.findall(content))
        parsed_sections = sum(1 for b in blocks if isinstance(b, segments.Section))
        if stored_sections > parsed_sections:
            report.counts["sections collapsed"] += stored_sections - parsed_sections
    trailing = content[len(content.rstrip("\n")) :]

    before_findings = _lint_tally(lint.lint(post, blocks, corpus_root))
    report.title_before, report.description_before = _derived_pair(post, corpus_root)

    # ---- the subtraction ----
    # The census already said what comes off, label for label — including the section
    # `address:`, which needs no mutation at all (the serializer omits it and `iter_blocks`
    # derives it) and is counted so the manifest says so rather than leaving it to a diff.
    report.counts.update(carried)
    if stale_headers:
        report.counts["section header → bare opener"] += stale_headers

    for key in retired.FRONTMATTER_FIELDS:
        post.metadata.pop(key, None)

    for sec in sections:
        sec.description = None
        sec.entry = None
        for key in retired.SECTION_EXTRA_FIELDS:
            sec.extra.pop(key, None)

    for seg in all_segments:
        seg.description = None
        # The structural byte-mark's field is not this one (§4.3.2.3) and stays.
        if not seg.is_structural:
            seg.entry = None

    if doomed_contexts:
        keep = [c for c in (post.metadata.get("_contexts") or []) if c not in doomed_contexts]
        post.metadata["_contexts"] = keep

    # An issue's free-prose `description` (§4.3.3.2, 3.5) comes off the FIELD, not the block:
    # id/severity/resolution/detector are a real issue and stay — only the prose the spec
    # says an issue never carries goes, same as `census`'s "issue description" count above.
    for ctx in post.metadata.get("_contexts") or []:
        if str(ctx.get("namespace") or "") == "issue":
            (ctx.get("fields") or {}).pop("description", None)

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
