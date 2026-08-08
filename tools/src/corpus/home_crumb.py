"""#89: the breadcrumb comes home — one trailing `<!--section nav-->` (ATH-CORPUS 3.5's
framing restoration, unblocked by 3.9's region-nesting rule and the `my.alldata.com` origin
overlay's 2026-07-27 `regions:` declaration, spec §7.2).

The overlay names the breadcrumb (`div.article-breadcrumb` / `ad-repair-breadcrumb`) a
`framing` region and says where it belongs: **content first, the framing after, in one
trailing span** (§4.3.2.1's cross-span significance order). #52's acceptance check
(`tools/scripts/accept_alldata.py`) measured the fleet against that shape and found three
populations sharing one symptom — "the breadcrumb line renders somewhere in the body, not
inside a trailing framing span" — for three DIFFERENT reasons, and only one of them is a move:

- **alone in its own segment, verbatim** — the segment's whole body IS the crumb trail and
  nothing else, spelled exactly as the artifact's own crumb labels chain. Re-parenting it
  changes nothing about what it SAYS, only where it sits. This is the population this module
  moves.
- **alone in its own segment, but prefixed** — #89's own third defect: nearly every sampled
  hit glues the vehicle header string onto the front (`"2009 Pontiac G8 V8-6.0L: Vehicle >
  …"` against an artifact crumb that reads `"vehicle > …"`). The overlay is explicit that the
  first crumb is literally the word "Vehicle" and must never be substituted or prefixed
  (spec §12.24/§12.25 — writing bytes at an address they do not appear at is fabrication).
  Moving this text verbatim would carry the fabrication into the newly-blessed trailing span
  instead of removing it, so it is REFUSED, not moved: fixing the text is re-authoring, a
  different pass than this one.
- **mixed into a larger content segment** — the crumb line is real but shares a segment with
  procedure prose, a labor table, or other content. Splitting it out is a re-segmentation
  judgment (§12.33), not a block move, so it is REFUSED too.

**The population this module used to refuse outright, now resolved by `form/nav`:** 397 of the
525 candidates carry the crumb as one child of a `form/index` span that is the record's own
sole top-level block — a genuine link-index page (the overlay's "the link list IS the
content") that happens to co-locate the crumb. Moving the crumb out used to mean appending a
new trailing `form/index` span, and since `form/index` declares no fields (§7.8), that new
span would merge with the one left behind on the very next parse (§4.3.2.1's adjacent-same-form
rule) — so this module refused rather than write a shape whose correctness would silently
expire. `form/nav` ends the overload: the crumb now moves into a trailing `nav` span, a
different form id from the `index` span it leaves behind, and the two can never merge
regardless of what either declares. `home_rail` made and refused the identical trap for the
same population; its refusal disarms the same way (see `home_rail`'s module docstring).

**Convergence, additionally:** a record this module already homed under the pre-#89 spelling
carries its crumb in a trailing bare `<!--section index-->` rather than `<!--section nav-->`.
Re-running now finds that span and RE-SPELLS its opener to `nav` — reported as a change, not a
skip — through the same round-trip and neutrality gates as any other rewrite. This is how the
~113 already-homed records converge to the one spelling; no separate script does it.

Same discipline as `reseat.py` / `drop_retired.py`: compute, never write; the record's own
dumps-stability and an emit round-trip gate every rewrite; the **neutrality gate** holds any
record whose rewrite would raise a lint rule's finding count; and — the lesson a prior
migration paid for in blood (a neutrality gate that passed on a run which reported 641
"merges" while writing nothing) — a **positive landing check** confirms the crumb segment
actually IS the trailing span's only child and is no longer anywhere else, not merely that
nothing got worse.

The crumb-label extraction and line-matching algorithm below is ported from
`tools/scripts/accept_alldata.py`'s `crumb_labels` / `check_crumb` (the #52/#89 validated
detector, hand-verified against 25 sampled records) rather than re-derived: this module's
job is to find the exact segment the acceptance check's `crumb` verdict already certifies as
`inline`, not a different one that happens to agree today. Three conditions are ADDED beyond
that detector's own "opens the line" verdict test, because a verdict of `inline` only needs
to prove the crumb is *present and loose*, while a migration that moves text verbatim needs
to prove the segment *is nothing else*:

1. the segment's whole body, stripped, is the matched line and nothing more (not mixed);
2. the matched label chain starts at the very first character of the line (not prefixed —
   note `check_crumb`'s own `best_start` bookkeeping never assigns on the chain's first-ever
   label match, so it cannot answer this question; this module tracks the label's TRUE start
   position separately for exactly that reason);
3. the chain consumes every label the artifact declares and reaches to the end of the line
   (no partial trail, no trailing residue).
"""

from __future__ import annotations

import html as _html
import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from corpus import lint, mime, records, schemas, segments, touches
from corpus.containment import ArtifactMissing, ensure_local_bytes
from corpus.regionmap import RegionMap
from corpus.regionmap import resolve as resolve_regions

#: Touch identifier stamped on every record this migration rewrites.
TOUCH_ID = "migrate.crumb-89"

#: The one origin this migration knows how to handle — its overlay is what names the
#: breadcrumb a framing region and states the trailing-span target shape (spec §7.2).
HOST = "my.alldata.com"

_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_SEPARATOR_GAP = re.compile(r"[\s>:*|/-]+")


# ---------- crumb-label extraction (ported from accept_alldata.py) ---------- #


def _plain(fragment: str) -> str:
    """Strip tags and decode entities — the same treatment `accept_alldata.plain()` applies
    with entity decoding on (its corrected default, not its `--legacy-text` mode)."""
    stripped = _TAG.sub(" ", fragment)
    return " ".join(_html.unescape(stripped).replace("\xa0", " ").split())


def _norm(s: str) -> str:
    """Lowercase alphanumeric words, single-spaced — `accept_alldata.norm()` verbatim."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def crumb_labels(html: str, rmap: RegionMap) -> list[str]:
    """The breadcrumb's own crumb labels, in source order, read off the artifact's `framing`
    region(s) whose role names "breadcrumb" — `accept_alldata.crumb_labels()` verbatim."""
    spans = [r for r in rmap.spans("framing") if "breadcrumb" in (r.role or "")]
    if not spans:
        return []
    frag = html[spans[0].start : spans[0].end]
    labels = [_plain(m.group(2)) for m in _ANCHOR.finditer(frag)]
    tail = _plain(_ANCHOR.sub(" ", frag))
    if tail:
        labels.append(tail)
    return [_norm(x) for x in labels if x.strip()]


# ---------- the segment locator ---------- #


@dataclass
class _Match:
    """One body line this record renders that chains >=2 crumb labels adjacently and opens
    the line — `check_crumb`'s own detection, plus the bookkeeping a migration needs that a
    verdict does not: the label chain's TRUE start (not `check_crumb`'s `best_start`, which
    is never assigned on the chain's first-ever label and so cannot see a prefix), whether it
    covers every label, and whether it reaches the line's end."""

    segment: segments.Segment
    container: segments.Section | None
    line: str
    chained: int
    true_start: int
    #: Whether the winning chain's last label ends exactly at the (normalized) line's end —
    #: computed where the normalized line is in scope, since `line` above is the RAW text
    #: (needed for `is_pure`'s exact-body comparison) and comparing a normalized-string index
    #: against the raw string's length would be a units mismatch.
    consumes_line: bool

    @property
    def is_pure(self) -> bool:
        """The segment's WHOLE body is this line and nothing else — the block-move precondition.
        A segment with more content before or after the crumb line needs splitting (#12.33),
        not a move."""
        return (self.segment.body or "").strip() == self.line


def _find_crumb_matches(
    blocks: list[segments.Block], labels: list[str]
) -> list[_Match]:
    """Every body line in `blocks` that chains >=2 of `labels` adjacently and opens the line —
    `check_crumb`'s own scan, run over every candidate line rather than stopping at the
    first, so an ambiguous record (more than one line qualifying) is visible to the caller
    rather than silently resolved by scan order."""
    out: list[_Match] = []
    for blk in blocks:
        container = blk if isinstance(blk, segments.Section) else None
        for seg in blk.segments if isinstance(blk, segments.Section) else [blk]:
            if not isinstance(seg, segments.Segment):
                continue
            if seg.is_structural or seg.atom != "text":
                continue
            for raw_line in (seg.body or "").strip().split("\n")[:3]:
                if ">" not in raw_line:
                    continue
                line = _norm(raw_line)
                if not line:
                    continue
                # `check_crumb`'s own chain scan, verbatim — plus `true_start`/`best_end`,
                # tracked correctly (see module docstring point 2).
                pos, chained, run, run_start, best_start = -1, 0, 0, 0, 0
                true_start: int | None = None
                best_true_start = 0
                best_end = -1
                for label in labels:
                    j = line.find(label, pos + 1)
                    if j <= pos:
                        continue
                    gap = line[pos + 1 : j] if pos >= 0 else ""
                    if pos < 0 or not _SEPARATOR_GAP.sub("", gap):
                        run += 1
                        if true_start is None:
                            true_start = j
                    else:
                        run, run_start = 1, j
                        true_start = j
                    if run > chained:
                        chained, best_start = run, run_start
                        best_true_start, best_end = true_start, j + len(label)
                    pos = j + len(label) - 1
                if chained >= 2 and line[:best_start].count(" ") <= 10:
                    out.append(
                        _Match(
                            segment=seg,
                            container=container,
                            line=raw_line.strip(),
                            chained=chained,
                            true_start=best_true_start,
                            consumes_line=best_end == len(line),
                        )
                    )
                    break  # one match per segment — `check_crumb` only ever looks at 3 lines
    return out


# ---------- the migration ---------- #


class CrumbHold(ValueError):
    """A record this migration refuses to touch. Carries the reason."""


@dataclass
class CrumbHome:
    record_id: str
    relpath: str
    changed: bool = False
    #: not this origin / no artifact / fewer than 2 labels / no breadcrumb rendered.
    skipped: str | None = None
    hold: str | None = None
    counts: Counter[str] = dataclass_field(default_factory=Counter)
    new_text: str | None = None


def _emit_and_gate(
    post: Any,
    blocks: list[segments.Block],
    before: Counter[str],
    corpus_root: Path,
    report: CrumbHome,
) -> tuple[str, list[segments.Block]] | None:
    """Emit `blocks`, stamp the touch, and run the round-trip + neutrality gates shared by
    every rewrite this module makes — a move or a bare re-spell alike. Returns
    `(new_text, reparsed_blocks)` on success; on failure sets `report.hold` and returns None."""
    post.content = segments.emit(blocks).rstrip("\n") + "\n"
    touches.record_touch(post, touches.script_identifier(TOUCH_ID))
    new_text = records.dumps(post)

    # Round-trip on the TEXT: a section's `address` is derived from its children (§4.3.2.1,
    # §12.29), so the in-memory envelope is stale by construction here — the reparse is the
    # check that matters (the same discipline `reseat.py` and `drop_retired.py` apply).
    try:
        reparsed = segments.iter_blocks(post.content)
    except ValueError as exc:
        report.hold = f"rewritten content zone does not parse: {exc}"
        return None
    if segments.emit(reparsed).rstrip("\n") != post.content.rstrip("\n"):
        report.hold = "rewritten content zone does not survive an emit round-trip losslessly"
        return None

    # The neutrality gate (§12.28): the whole rule set, deliberately — the failure worth
    # catching is the unpredicted one.
    after = Counter(f.rule_id for f in lint.lint(post, reparsed, corpus_root))
    worse = sorted(rule for rule in set(before) | set(after) if after[rule] > before.get(rule, 0))
    if worse:
        report.hold = (
            "rewrite would raise lint findings ("
            + ", ".join(f"{r}: {before.get(r, 0)}→{after[r]}" for r in worse)
            + ")"
        )
        return None
    return new_text, reparsed


def home_crumb_record(record_file: Path, corpus_root: Path) -> CrumbHome:
    """Compute (never write) the §89 crumb-homing move for one record. The caller applies
    `report.new_text` when `report.changed`; a `hold` means hands off."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = CrumbHome(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))

    if not any((b.get("id") or "") == HOST for b in records.iter_origin_blocks(post)):
        report.skipped = f"not a {HOST} record"
        return report

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    # Serializer stability, the §12.28 rule: the rewrite goes through the real serializer, so
    # a difference it would introduce on its own must be disclosed before we add ours.
    if records.dumps(post) != original:
        report.hold = "record is not dumps-stable; the serializer would introduce unrelated changes"
        return report

    media_type = records.media_type_for(post)
    ext = mime.extension_for(media_type)
    try:
        artifact_path = ensure_local_bytes(corpus_root, rid, ext)
    except ArtifactMissing as exc:
        report.hold = f"no resident artifact — cannot verify the crumb labels: {exc}"
        return report
    html = artifact_path.read_text(encoding="utf-8", errors="replace")

    decl = schemas.origin_regions(corpus_root, HOST)
    rmap = resolve_regions(html, decl)
    labels = [x for x in crumb_labels(html, rmap) if x]
    if len(labels) < 2:
        report.skipped = "fewer than 2 crumb labels on the artifact — nothing to home"
        return report

    matches = _find_crumb_matches(blocks, labels)
    if not matches:
        report.skipped = "no breadcrumb line rendered in the body"
        return report
    if len(matches) > 1:
        report.hold = (
            f"{len(matches)} segments in this record match the breadcrumb pattern — "
            f"ambiguous, refusing to guess which one is home"
        )
        return report

    (m,) = matches
    # Already the target shape — `check_crumb`'s own "homed" test: the match sits inside a
    # trailing bare framing span. Re-running a completed move must be inert, not a hold: the
    # single-child span this move just created would otherwise trip the "no children left"
    # guard below on a SECOND pass over the same record.
    already_homed = (
        m.container is not None
        and m.container.form in ("nav", "index")
        and len(blocks) > 1
        and blocks[-1] is m.container
    )
    if already_homed and m.container.form == "nav":
        report.skipped = "already homed — the breadcrumb sits in the trailing nav span"
        return report
    if already_homed:
        # The pre-#89 spelling: this record was homed by a prior run before `form/nav` existed.
        # Re-spell the opener in place — nothing else about the record changes — through the
        # same round-trip and neutrality gates as any other rewrite (#89's convergence: no
        # separate script re-spells the ~113 already-homed records, this pass does).
        before = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))
        m.container.form = "nav"
        gated = _emit_and_gate(post, blocks, before, corpus_root, report)
        if gated is None:
            return report
        new_text, reparsed = gated
        trailing = reparsed[-1] if reparsed else None
        if not (isinstance(trailing, segments.Section) and trailing.form == "nav"):
            report.hold = "internal: re-spelled span did not land as trailing form/nav"
            return report
        report.counts["framing span re-spelled: index -> nav"] += 1
        report.new_text = new_text
        report.changed = True
        return report
    if not m.is_pure:
        report.hold = (
            "the breadcrumb line shares a segment with other content (mixed in, not alone) — "
            "splitting it out is re-segmentation (#12.33), out of scope for a block move"
        )
        return report
    if m.true_start != 0:
        report.hold = (
            "the breadcrumb segment carries text before the crumb trail (the vehicle-name "
            "prefix defect, #89's third defect) — fixing the text is re-authoring, out of "
            "scope for a pure block move"
        )
        return report
    if m.chained != len(labels):
        report.hold = (
            f"only {m.chained} of {len(labels)} crumb labels chain on this line — a partial "
            f"trail, refusing to guess the rest"
        )
        return report
    if not m.consumes_line:
        report.hold = (
            "text follows the crumb trail on its line — refusing to guess whether it belongs "
            "to the breadcrumb"
        )
        return report

    seg = m.segment
    container = m.container
    if container is not None and len(container.segments) == 1:
        report.hold = (
            f"removing the breadcrumb would leave its `form/{container.form}` span with no "
            f"children — what the form governs is now a question, not a rewrite"
        )
        return report

    before = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))

    # ---- the move: re-parent `seg`, in place, at the record's end ---- #
    new_blocks: list[segments.Block] = []
    for blk in blocks:
        if isinstance(blk, segments.Section):
            if blk is container:
                blk.segments = [s for s in blk.segments if s is not seg]
            new_blocks.append(blk)
        elif blk is seg:
            continue  # the top-level formless case — dropped here, re-added below
        else:
            new_blocks.append(blk)

    # Before #89, a bare `form/index` span declared no fields (§7.8) — nothing distinguished
    # it from another bare `form/index` span, so appending a new trailing index span here
    # would have merged with whatever `form/index` span the crumb's removal left behind
    # (§4.3.2.1's adjacent-same-form rule) — 397 of the 525 pure-verbatim candidates are their
    # record's SOLE top-level block, so this was not a corner case. `form/nav` ends the
    # overload: the new trailing span below is a different form id from anything it might
    # follow, so it can never merge, whatever the remaining content's form declares or omits.

    new_blocks.append(segments.Section(form="nav", segments=[seg]))

    gated = _emit_and_gate(post, new_blocks, before, corpus_root, report)
    if gated is None:
        return report
    new_text, reparsed = gated

    # The positive landing check (the lesson a prior migration paid for: a neutrality gate
    # that passed on a run reporting 641 merges while writing nothing). Assert the move
    # actually landed — a trailing `form/nav` span exists, holds exactly this crumb body
    # and nothing else, and the crumb body is nowhere else in the record.
    trailing = reparsed[-1] if reparsed else None
    if not (isinstance(trailing, segments.Section) and trailing.form == "nav"):
        report.hold = "internal: no trailing form/nav span in the rewritten record"
        return report
    trailing_bodies = [s.body.strip() for s in trailing.segments if isinstance(s, segments.Segment)]
    if trailing_bodies.count(m.line) != 1:
        report.hold = (
            f"internal: the trailing span carries the crumb body {trailing_bodies.count(m.line)} "
            f"times, not exactly once — refusing a dangling or duplicated move"
        )
        return report
    elsewhere = sum(
        1
        for blk in reparsed[:-1]
        for s in (blk.segments if isinstance(blk, segments.Section) else [blk])
        if isinstance(s, segments.Segment) and (s.body or "").strip() == m.line
    )
    if elsewhere:
        report.hold = (
            f"internal: the crumb body still appears {elsewhere} time(s) outside the "
            f"trailing span — refusing a copy in place of a move"
        )
        return report

    report.counts["breadcrumb homed"] += 1
    report.new_text = new_text
    report.changed = True
    return report
