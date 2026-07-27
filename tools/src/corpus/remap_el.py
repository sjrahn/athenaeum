"""The §12.28 addressing remap: old filtered-index `el=` values → total child-index paths.

The migration engine for ATH-CORPUS 3.6 (spec §6.1.1). Old index → new path is a pure
function of an immutable artifact: walk the old filtered enumeration (the FROZEN
`legacy_is_addressable` whitelist) and the new total tree over the same bytes, pair them
positionally, rewrite — and prove the rewrite by re-resolving every produced address to
the IDENTICAL element the old one named. No judgment enters anywhere.

Surfaces rewritten, per record:

- content-zone section / segment / structural addresses,
- member (embed) roster rows,
- annotation-zone context blocks (`issue` / legacy `relation` / `reference`) — by far the
  largest population (the related-information rails; ~77k addresses), and the one the
  §12.28 sample proof did not cover: the mapping function is identical, and every one is
  verified here the same way.

The record is then stamped with the attested `addressing:` key (§7.1 — parser identity +
element count), which is what flips the resolver's grammar dispatch for it. A record
already stamped is skipped (idempotent); a record the engine cannot remap mechanically is
HELD with a reason, never guessed at.

What deliberately does NOT happen here: no re-attest, no members-block conversion, no
description drop — the diff a remap writes is addresses + the stamp + a touch, nothing
else, so the fleet review reads as exactly the migration and the 3.4 lazy conversion
stays lazy.

Range mapping (the retired flat `el=<lo>-<hi>`) maps to **the tightest §6.1.1 address
that contains the interval**: a subtree path when one endpoint holds the other or both
land in one child of their nearest common ancestor, else the sibling range
`el=<parent>.[<a>-<b>]` over the endpoints' slots in that ancestor. Never a list of the
endpoints — the flat form was an interval over the document, not a set of its bounds
(§12.28.1). The two forms differ exactly where it matters: the interval's whole reason
for existing was to cover prose with no element of its own, which lives BETWEEN the
bounds, so a list would name the two landmarks the prose is not in, alias the point
addresses those landmarks already carry, and narrow the claim. Parity is exact on the
resolution axis too — a legacy range and a 3.6 sibling range are both
`NotMaterializable`, so no address gains or loses a byte surface in the migration.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from corpus import containment, lint, records, segments, touches
from corpus import functional_uri as furi
from corpus import mime as mime_mod
from corpus.transforms.html import (
    EL_PARSER_ID,
    element_path,
    iter_element_children,
    legacy_is_addressable,
    path_root,
    resolve_element_path,
    total_element_count,
)

#: Touch identifier stamped on every record the remap actually rewrites.
TOUCH_ID = "migrate.el-path-36"

_POINT_RE = re.compile(r"^\d+$")
_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


class RemapHold(ValueError):
    """The record cannot be remapped mechanically — held with a reason, never guessed."""


@dataclass
class RecordRemap:
    """One record's remap outcome. `changed` means a rewrite was produced (and applied,
    when the caller asked for apply); `hold` carries the refusal reason when not."""

    record_id: str
    relpath: str
    changed: bool = False
    skipped: str | None = None          # already stamped / no el addresses
    hold: str | None = None             # mechanical refusal, with reason
    elements: int = 0                   # attested total element count
    emit_normalized: bool = False       # re-emit normalizes surface form (disclosed rider)
    mappings: list[dict[str, Any]] = dataclass_field(default_factory=list)
    forms: dict[str, int] = dataclass_field(default_factory=dict)
    new_text: str | None = None         # the rewritten record, when changed


def _tally(report: RecordRemap, where: str, old: str, new: str | list[str], form: str) -> None:
    report.mappings.append({"where": where, "old": old, "new": new, "form": form})
    report.forms[form] = report.forms.get(form, 0) + 1


def map_el_value(
    value: str, old_elements: list[Tag], root: Tag
) -> tuple[str | list[str], str]:
    """Map one old `el=` VALUE (`"5"` / `"3-7"`) to its §6.1.1 replacement, returning
    `(new_value_or_values, form)` where form ∈ point | subtree | sibling |
    fallback-wrapper. Every produced point path is verified by resolving it back to the
    IDENTICAL element the old enumeration named, and every produced envelope by proving
    it CONTAINS both of the interval's endpoints — the §12.28 self-proof. Raises
    `RemapHold` on anything that does not verify (out-of-range index, element outside
    the path root, identity miss, an envelope with no §6.1.1 spelling)."""

    def path_of(tag: Tag, label: str) -> str:
        p = element_path(tag, root)
        if p is None:
            raise RemapHold(f"el={label}: element sits outside the path root (<body>)")
        back = resolve_element_path(root, furi.parse_el_path(p))
        if back is not tag:
            raise RemapHold(f"el={label}: path {p} did not re-resolve to the same element")
        return p

    if _POINT_RE.match(value):
        n = int(value)
        if n == 1 and not old_elements:
            # The documented drafter fallback (§12.25/§12.28): a zero-element legacy
            # enumeration forced a guaranteed-unresolvable `el=1` placeholder onto the
            # whole-document wrapper. Under the total space the prose takes the path of
            # the elements that actually contain it — the body's element children.
            kids = iter_element_children(root)
            if not kids:
                raise RemapHold(
                    "el=1 fallback on a body with no element children — nothing to "
                    "re-point it at"
                )
            paths = [path_of(t, "1[fallback]") for t in kids]
            if len(paths) == 1:
                return paths[0], "fallback-wrapper"
            return paths, "fallback-wrapper"
        if not (1 <= n <= len(old_elements)):
            raise RemapHold(
                f"el={value}: out of range (the legacy enumeration has "
                f"{len(old_elements)} elements)"
            )
        return path_of(old_elements[n - 1], value), "point"

    m = _RANGE_RE.match(value)
    if m is None:
        raise RemapHold(f"el={value}: unrecognized legacy value shape")
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi or lo < 1 or hi > len(old_elements):
        raise RemapHold(
            f"el={value}: range out of bounds (the legacy enumeration has "
            f"{len(old_elements)} elements)"
        )
    first, last = old_elements[lo - 1], old_elements[hi - 1]
    first_path, last_path = path_of(first, value), path_of(last, value)

    # The retired flat form was an INTERVAL over the document — first element through
    # last, inclusive of whatever lay between, which is precisely why normalizers
    # reached for it to cover prose with no element of its own. So its §6.1.1
    # replacement is the tightest address that CONTAINS that interval, never a set of
    # its endpoints: an ancestor's subtree when one endpoint holds the other or both
    # sit in one child, else the sibling range over the endpoints' slots in their
    # nearest common ancestor.
    if first is last or furi.el_path_contains(
        furi.parse_el_path(first_path), furi.parse_el_path(last_path)
    ):
        return first_path, "subtree"
    if furi.el_path_contains(
        furi.parse_el_path(last_path), furi.parse_el_path(first_path)
    ):
        return last_path, "subtree"

    ancestors = {id(t): t for t in first.parents}
    anc = next((p for p in last.parents if id(p) in ancestors), None)
    if anc is None:
        raise RemapHold(f"el={value}: the range's endpoints share no common ancestor")

    def slot_of(tag: Tag, kids: list[Tag]) -> int:
        branch = tag
        while branch.parent is not None and branch.parent is not anc:
            branch = branch.parent
        # By IDENTITY, never `.index()`: bs4's Tag equality is structural, and these
        # documents are full of interchangeable siblings (`<br/>`, repeated wrapper
        # `<div>`s), so a value search silently returns the first look-alike's slot.
        slot = next((i for i, k in enumerate(kids, start=1) if k is branch), None)
        if slot is None:
            raise RemapHold(
                f"el={value}: endpoint's branch is not a child of the common ancestor"
            )
        return slot

    kids = iter_element_children(anc)
    a, b = slot_of(first, kids), slot_of(last, kids)
    if a == b:  # both endpoints inside one child of the ancestor: that child's subtree
        return path_of(kids[a - 1], value), "subtree"
    anc_path = element_path(anc, root)
    if a == 1 and b == len(kids) and anc_path is not None:
        # The interval spans every child of the ancestor, so the ancestor's own path
        # covers it exactly — and §6.1.1 is emphatic that a span which IS a subtree is
        # spelled as that subtree, not as a range over its full child list. One extent,
        # one spelling; it also keeps the address shorter.
        return anc_path, "subtree"
    if anc_path is None:
        # The nearest common ancestor is the path root itself, and §6.1.1's sibling
        # range is spelled `el=<parent>.[a-b]` — a root-level envelope has no address.
        # The interval covers the whole body, so re-scoping it is a judgment, not a
        # rewrite.
        raise RemapHold(
            f"el={value}: the range spans the path root's own children, which has no "
            f"§6.1.1 sibling-range spelling — re-scope this address deliberately"
        )
    new = f"{anc_path}.[{a}-{b}]"
    envelope = furi.parse_el_path(new)
    for label, p in (("first", first_path), ("last", last_path)):
        if not furi.el_path_contains(envelope, furi.parse_el_path(p)):
            raise RemapHold(
                f"el={value}: {new} does not contain its {label} element ({p})"
            )
    return new, "sibling"


def check_override(new: str, root: Tag) -> None:
    """Validate a deliberate re-address before it enters a record.

    An override is a judgment the engine cannot make, but it is not exempt from being an
    ADDRESS: it must parse as §6.1.1 and name something that exists in this document. A
    sibling range is unmaterializable by design, so what is checked is its parent — the
    slots must be real children, which is what catches a range copied from another record.
    """
    value = new[3:] if new.startswith("el=") else new
    value = value.split("&", 1)[0].split("/", 1)[0]
    try:
        path = furi.parse_el_path(value)
    except ValueError as exc:
        raise RemapHold(f"override {new!r} is not a §6.1.1 address: {exc}") from exc
    try:
        node = resolve_element_path(root, furi.ElPath(path.components))
    except ValueError as exc:
        # The walk names the exact component that ran past its parent — a better message
        # than anything reconstructed here.
        raise RemapHold(f"override {new!r}: resolves to no element — {exc}") from exc
    if node is None:
        dotted = ".".join(str(c) for c in path.components)
        raise RemapHold(f"override {new!r}: {dotted} resolves to no element")
    if path.sibling_range is not None:
        kids = iter_element_children(node)
        lo, hi = path.sibling_range
        if not (1 <= lo < hi <= len(kids)):
            raise RemapHold(
                f"override {new!r}: the sibling range [{lo}-{hi}] is not within its "
                f"parent's {len(kids)} children"
            )


def _map_address_strings(
    addrs: list[str],
    old_elements: list[Tag],
    root: Tag,
    report: RecordRemap,
    where: str,
    overrides: dict[str, str] | None = None,
) -> tuple[list[str], bool]:
    """Map every `el=`-leading string in an address's string list, leaving other axes
    untouched. Chained ops after the el value (`el=4&bbox=…` on two issue blocks;
    `el=55-56&part=2` on three merged-capture listings) ride along verbatim — a range
    that maps to a LIST distributes them onto every component, since each component
    claims the same qualified region the flat form did."""
    out: list[str] = []
    changed = False
    for a in addrs:
        if not a.startswith("el="):
            out.append(a)
            continue
        if overrides and a in overrides:
            # A deliberate re-address: the legacy form could not express this region (it is
            # why the record held), so the engine has nothing to map and the operator says
            # what it is. Verified as an address, then subject to the same neutrality gate.
            deliberate = overrides[a]
            check_override(deliberate, root)
            out.append(deliberate)
            _tally(report, where, a, deliberate, "override")
            changed = True
            continue
        rest = a[3:]
        for sep in ("&", "/"):
            cut = rest.find(sep)
            if cut != -1:
                value, suffix = rest[:cut], rest[cut:]
                break
        else:
            value, suffix = rest, ""
        new, form = map_el_value(value, old_elements, root)
        if isinstance(new, list):
            produced: str | list[str] = [f"el={v}{suffix}" for v in new]
            out.extend(produced)
        else:
            produced = f"el={new}{suffix}"
            out.append(produced)
        _tally(report, where, a, produced, form)
        changed = True
    return out, changed


def _fold(addrs: list[str], was_list: bool) -> str | list[str]:
    if len(addrs) == 1 and not was_list:
        return addrs[0]
    return addrs


def _lint_tally(findings: list[lint.Finding]) -> Counter[str]:
    return Counter(f.rule_id for f in findings)


def _lint_neutrality_hold(
    new_text: str, before: Counter[str], corpus_root: Path
) -> str | None:
    """Return a hold reason when the rewritten record would lint WORSE than the original
    — any rule whose finding count rises — else None. Counts, not addresses: every
    address changes by design, so only the rules' verdicts are comparable."""
    try:
        after_post = records.loads(new_text)
        after = _lint_tally(
            lint.lint(after_post, segments.iter_blocks(after_post.content or ""), corpus_root)
        )
    except Exception as exc:  # a record whose rewrite cannot even be linted is a hold
        return f"post-remap lint did not run: {exc}"
    risen = {r: (before.get(r, 0), c) for r, c in after.items() if c > before.get(r, 0)}
    if not risen:
        return None
    detail = ", ".join(f"{r} {b}→{a}" for r, (b, a) in sorted(risen.items()))
    return (
        f"the rewrite would introduce new lint findings ({detail}) — the legacy "
        f"addresses alias under §6.1.1; re-address this record deliberately"
    )


def remap_record(
    record_file: Path, corpus_root: Path, overrides: dict[str, str] | None = None
) -> RecordRemap:
    """Compute (never write) the remap of one record. The caller applies
    `report.new_text` when `report.changed`; a `hold` means hands off. Raises nothing
    remap-specific — every refusal lands in the report.

    `overrides` maps a stored legacy address string to the §6.1.1 address it should BECOME
    — the deliberate re-addressing a held record needs. The engine holds a record whose
    legacy addresses alias under §6.1.1, and it is right to: an over-wide interval that
    collapses onto its container is a claim the legacy grammar could not state precisely,
    so no mapping recovers what it meant. What it covers is a reading of the document, and
    a reading is the operator's to supply. Everything else about the record still migrates
    mechanically, through this same function, so a deliberately re-addressed record differs
    from a swept one only in the addresses a human chose — and the neutrality gate runs
    afterwards either way, so a bad override still holds."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = RecordRemap(
        record_id=rid, relpath=str(record_file.relative_to(corpus_root))
    )

    if records.el_addressing(post) is not None:
        report.skipped = "already stamped (3.6 addresses)"
        return report

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    def _addr_strings(value: Any) -> list[str]:
        return [a for a in segments._iter_addr_strings(value)]

    def _has_el(value: Any) -> bool:
        return any(a.startswith("el=") for a in _addr_strings(value))

    zone_has_el = any(
        _has_el(b.address)
        or (isinstance(b, segments.Section) and any(_has_el(s.address) for s in b.segments))
        for b in blocks
    )
    rows_have_el = any(
        _has_el(row.get("address")) for row in records.iter_members(post)
    )
    ctx_have_el = any(
        _has_el((ctx.get("fields") or {}).get("address"))
        for ctx in post.metadata.get("_contexts") or []
    )
    if not (zone_has_el or rows_have_el or ctx_have_el):
        report.skipped = "no el= addresses"
        return report

    media_type = records.media_type_for(post)
    if not media_type.startswith("text/html"):
        report.hold = f"el= addresses on a non-HTML mime ({media_type or 'none'})"
        return report

    # Serializer stability FIRST: the rewrite goes through the real serializer, so the
    # only differences it may introduce must be intended or disclosed (the bbox-sweep
    # rule). Frontmatter/metadata blocks must round-trip byte-stable; the content zone
    # must round-trip LOSSLESSLY — emit is allowed to normalize surface form (header key
    # order; the 3.5 structural `entry:`→`mark:` dual-read conversion), and when it
    # does, the manifest discloses it (`emit_normalized`), but a round-trip that parses
    # to different BLOCKS is a hold, never a shrug.
    if records.dumps(post) != original:
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
        report.hold = "content zone does not survive an emit round-trip losslessly"
        return report
    report.emit_normalized = emitted.rstrip("\n") != content.rstrip("\n")
    trailing = content[len(content.rstrip("\n")):]

    try:
        binary = containment.ensure_local_bytes(
            corpus_root, rid, mime_mod.extension_for(media_type)
        )
    except Exception as exc:
        report.hold = f"artifact bytes not resident: {exc}"
        return report

    soup = BeautifulSoup(binary.read_bytes(), "html.parser")
    old_elements = [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]
    root = path_root(soup)
    report.elements = total_element_count(soup)

    # Baseline for the neutrality gate below — taken BEFORE any address mutates.
    before_findings = _lint_tally(lint.lint(post, blocks, corpus_root))

    try:
        # Content zone.
        zone_changed = False
        for b in blocks:
            targets = [b] + (list(b.segments) if isinstance(b, segments.Section) else [])
            for t in targets:
                if t.address is None:
                    continue
                was_list = isinstance(t.address, list)
                mapped, ch = _map_address_strings(
                    _addr_strings(t.address), old_elements, root, report,
                    "section" if isinstance(t, segments.Section) else
                    ("structural" if getattr(t, "is_structural", False) else "segment"),
                    overrides,
                )
                if ch:
                    t.address = _fold(mapped, was_list)
                    zone_changed = True

        # Member roster rows (legacy embed blocks or a members block alike — the rows
        # are the same dicts either way; their FORM is untouched).
        for row in list(records.iter_members(post)):
            value = row.get("address")
            if value is None:
                continue
            was_list = isinstance(value, list)
            mapped, ch = _map_address_strings(
                _addr_strings(value), old_elements, root, report, "member", overrides
            )
            if ch:
                row["address"] = _fold(mapped, was_list)

        # Annotation zone (context blocks): `address` rides in the block's fields.
        for ctx in post.metadata.get("_contexts") or []:
            fields = ctx.get("fields") or {}
            value = fields.get("address")
            if value is None:
                continue
            was_list = isinstance(value, list)
            mapped, ch = _map_address_strings(
                _addr_strings(value), old_elements, root, report,
                f"context:{ctx.get('namespace') or 'issue'}", overrides,
            )
            if ch:
                fields["address"] = _fold(mapped, was_list)

        # §12.28 rider: when the drafter's `el=1` zero-element fallback re-pointed to
        # the body's real children, the `unaddressable-content` issue it provoked is no
        # longer true of the record — the issue retires by deletion, disclosed here.
        if report.forms.get("fallback-wrapper"):
            contexts = post.metadata.get("_contexts") or []
            kept = [
                c for c in contexts
                if not (
                    c.get("namespace") == "issue"
                    and c.get("id") == "partial-content"
                    and c.get("subtype") == "unaddressable-content"
                )
            ]
            if len(kept) != len(contexts):
                post.metadata["_contexts"] = kept
                report.mappings.append({
                    "where": "context:issue",
                    "old": "partial-content/unaddressable-content",
                    "new": None,
                    "form": "issue-retired",
                })
    except RemapHold as exc:
        report.hold = str(exc)
        return report

    if zone_changed:
        post.content = segments.emit(blocks).rstrip("\n") + trailing

    # The §7.1 stamp — the resolver's grammar dispatch for this record from now on.
    artifact = records.artifact_block(post) or {"mime": media_type, "fields": {}}
    fields = dict(artifact.get("fields") or {})
    fields["addressing"] = {"parser": EL_PARSER_ID, "elements": report.elements}
    records.set_artifact_block(post, mime=artifact.get("mime") or media_type, fields=fields)

    touches.record_touch(post, touches.script_identifier(TOUCH_ID))
    new_text = records.dumps(post)

    # THE NEUTRALITY GATE. A migration of addresses must not make the gate say anything
    # it did not say before: the record is linted before and after, and any rule whose
    # count RISES holds the record. This is deliberately the whole rule set rather than
    # a hand-picked few — the failure it exists to catch is the one nobody predicted.
    #
    # What it catches is real and pre-existing: a legacy flat interval could claim a
    # span wider than the content it held (§12.24 / §12.25 / §12.27's over-wide
    # addresses), and several such intervals on one record collapse onto the single
    # container that actually holds them — so `el=1-14` and `el=2-11` become the same
    # address, which is the truth about them and a duplicate-claim error. §6.1.1 cannot
    # represent the over-claim, which is the point; it also cannot represent it
    # SILENTLY, which is why those records stay on the legacy grammar (unstamped
    # records resolve exactly as before) and go to a worklist for deliberate
    # re-addressing instead of being migrated into a red gate.
    lint_hold = _lint_neutrality_hold(new_text, before_findings, corpus_root)
    if lint_hold is not None:
        report.hold = lint_hold
        return report

    report.new_text = new_text
    report.changed = True

    # Final self-check: every address the remap produced is grammar-valid under §6.1.1
    # (identity against the artifact was already proven per value in `map_el_value`).
    for m in report.mappings:
        if m["form"] == "issue-retired":
            continue
        produced = m["new"] if isinstance(m["new"], list) else [m["new"]]
        for v in produced:
            value = str(v)[3:] if str(v).startswith("el=") else str(v)
            furi.parse_el_path(value.split("&", 1)[0].split("/", 1)[0])

    return report
