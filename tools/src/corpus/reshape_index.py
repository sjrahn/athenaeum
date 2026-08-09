"""Deterministic re-authoring of the alldata index template (#164) — the runner around
`corpus.shape`'s `index` shaper.

`shape_record` is the authoring engine and it needs no adaptation for this population: it
seeds a Build with an EMPTY block list and `finish` assigns `post.content` outright, so a
record that already carries a rendering is re-authored rather than appended to. What it does
NOT carry is any notion of whether the result is an improvement — it writes the shaper's
output and stamps `shape.<form>`, full stop. On a `proxy` record with nothing to lose that is
the right contract; over 136 records that are already `state: formed`, replacing a stored
rendering with an unchecked one is how a migration destroys work.

So this module is the gate layer, and it is deliberately the same gate layer the #89 verbs
already run (`home_crumb` / `home_rail` / `drop_retired`), plus one more that this arc earned:

- **dumps-stability** — the rewrite goes through the real serializer, so any change the
  serializer would make on its own is disclosed before this pass adds its own (§12.28).
- **round-trip** — the emitted zone must re-parse and re-emit identically. A section's
  `address` is derived from its children (§12.29), so the in-memory envelope is stale by
  construction and only the reparse is evidence.
- **neutrality** — no lint rule's finding count may rise. The whole rule set, deliberately:
  the failure worth catching is the unpredicted one.
- **the fidelity gate, POSITIVELY** (#159) — `check_fidelity` must PASS on the rewritten
  record. This is the one that makes the whole ticket safe to run without an agent: a
  mechanical rendering whose addresses and text disagree is exactly what #159 measures, and a
  shaper that cannot satisfy its own acceptance check has no business writing 136 records.
  Neutrality alone would not catch it — a record whose old body was ALSO bad shows no rise.

Nothing here writes. `reshape_record` computes `new_text` and the caller decides, exactly as
`home_crumb_record` does; `corpus reshape-index` is dry-run by default.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from corpus import lint, mime, records, schemas, segments, shape
from corpus.containment import ArtifactMissing, ensure_local_bytes
from corpus.fidelity import check_fidelity

#: The origin this shaper's template belongs to. A record of any other host is skipped
#: outright — the form id alone is not evidence that THIS DOM is what the record holds.
HOST = "my.alldata.com"
#: The form id whose shaper this verb runs.
FORM = "index"


@dataclass
class IndexReshape:
    record_id: str
    relpath: str
    changed: bool = False
    #: not this origin / not the index form / already identical — nothing to do, not a fault.
    skipped: str | None = None
    hold: str | None = None
    counts: Counter[str] = dataclass_field(default_factory=Counter)
    new_text: str | None = None


def fidelity_hold(
    post: Any, blocks: list[segments.Block], corpus_root: Path, record_id: str
) -> str | None:
    """The positive landing check: does the REWRITE satisfy #159's gate? Returns a hold
    reason, or None when the rendering and its addresses describe the same content."""
    try:
        ext = mime.extension_for(records.media_type_for(post))
        artifact = ensure_local_bytes(corpus_root, record_id, ext)
    except ArtifactMissing as exc:
        return f"no resident artifact — cannot verify the rewrite: {exc}"
    stamp = records.el_addressing(post)
    if stamp is None:
        return "record carries no `addressing:` stamp — its addresses are not judgeable"
    regions = schemas.origin_regions(corpus_root, HOST)
    try:
        result = check_fidelity(
            artifact.read_text(encoding="utf-8", errors="replace"), blocks, stamp, regions
        )
    except ValueError as exc:
        return f"fidelity gate could not run on the rewrite: {exc}"
    if result["pass"]:
        return None
    detail = ", ".join(
        f"{kind} {result[kind]}" for kind in ("misplaced", "dropped", "unresolvable")
        if result[kind]
    )
    samples = [s for f in result["findings"] for s in f["sample"][:1]][:3]
    return f"rewrite does not satisfy the #159 fidelity gate ({detail}): {'; '.join(samples)}"


def reshape_record(record_file: Path, corpus_root: Path) -> IndexReshape:
    """Compute (never write) the deterministic re-authoring of one index record. The caller
    applies `report.new_text` when `report.changed`; a `hold` means hands off."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = IndexReshape(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))

    if not any((b.get("id") or "") == HOST for b in records.iter_origin_blocks(post)):
        report.skipped = f"not a {HOST} record"
        return report

    resolved = shape.form_for_record(post, corpus_root)
    if resolved is not None:
        if resolved[1] != FORM:
            report.skipped = f"origin overlay routes this record to form/{resolved[1]}, not {FORM}"
            return report
    elif shape.asserted_form(post) != FORM:
        # §7.8 precedence (b): no overlay declaration, so the record's own asserted
        # whole-record section is what governs — the bare-itype index pages arrive this
        # way, since their URL shape cannot safely declare a form (#164).
        report.skipped = f"record neither routes to nor asserts form/{FORM}"
        return report

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    if records.dumps(post) != original:
        report.hold = "record is not dumps-stable; the serializer would introduce unrelated changes"
        return report

    before = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))

    # The authoring itself — `shape_record` dispatches through the registry and stamps the
    # `shape.index` touch, so this pass leaves the same mark any other shaping run would.
    try:
        if not shape.shape_record(post, corpus_root):
            report.skipped = f"no shaper registered for form/{FORM}"
            return report
    except Exception as exc:  # a template the shaper refuses, or unreadable artifact bytes
        report.hold = f"{type(exc).__name__}: {exc}"
        return report

    new_text = records.dumps(post)
    if new_text == original:
        report.skipped = "already the shaper's own rendering — nothing to rewrite"
        return report

    try:
        reparsed = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"rewritten content zone does not parse: {exc}"
        return report
    if segments.emit(reparsed).rstrip("\n") != (post.content or "").rstrip("\n"):
        report.hold = "rewritten content zone does not survive an emit round-trip losslessly"
        return report

    after = Counter(f.rule_id for f in lint.lint(post, reparsed, corpus_root))
    worse = sorted(rule for rule in set(before) | set(after) if after[rule] > before.get(rule, 0))
    if worse:
        report.hold = (
            "rewrite would raise lint findings ("
            + ", ".join(f"{r}: {before.get(r, 0)}→{after[r]}" for r in worse)
            + ")"
        )
        return report

    held = fidelity_hold(post, reparsed, corpus_root, rid)
    if held is not None:
        report.hold = held
        return report

    report.counts["segments"] = sum(1 for _ in segments.leaf_segments(reparsed))
    report.counts["lint_before"] = sum(before.values())
    report.counts["lint_after"] = sum(after.values())
    report.changed = True
    report.new_text = new_text
    return report
