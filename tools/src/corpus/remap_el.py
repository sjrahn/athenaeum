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

Range mapping (the retired flat `el=<lo>-<hi>`) follows §6.1.1's preference order: the
range's top-level members (nested ones drop — a subtree is one address) collapse to a
single subtree path when one contains the rest, to a sibling range
`el=<parent>.[<a>-<b>]` when they are a contiguous, complete run of one parent's element
children, else to the ordered address list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from corpus import containment, records, segments, touches
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
    `(new_value_or_values, form)` where form ∈ point | subtree | sibling | list. Every
    produced path is verified by resolving it back to the IDENTICAL element the old
    enumeration named — the §12.28 self-proof. Raises `RemapHold` on anything that does
    not verify (out-of-range index, element outside the path root, identity miss)."""

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
    members = old_elements[lo - 1 : hi]
    member_ids = {id(t) for t in members}
    tops = [
        t for t in members
        if not any(id(p) in member_ids for p in t.parents)
    ]
    if len(tops) == 1:
        return path_of(tops[0], value), "subtree"
    parents = {id(t.parent) for t in tops}
    if len(parents) == 1 and tops[0].parent is not None:
        parent = tops[0].parent
        kids = iter_element_children(parent)
        idxs = [kids.index(t) + 1 for t in tops]
        a, b = min(idxs), max(idxs)
        if sorted(idxs) == list(range(a, b + 1)) and kids[a - 1 : b] == tops:
            parent_path = element_path(parent, root)
            if parent_path is not None:
                return f"{parent_path}.[{a}-{b}]", "sibling"
    return [path_of(t, f"{value}[member]") for t in tops], "list"


def _map_address_strings(
    addrs: list[str],
    old_elements: list[Tag],
    root: Tag,
    report: RecordRemap,
    where: str,
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


def remap_record(record_file: Path, corpus_root: Path) -> RecordRemap:
    """Compute (never write) the remap of one record. The caller applies
    `report.new_text` when `report.changed`; a `hold` means hands off. Raises nothing
    remap-specific — every refusal lands in the report."""
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
                _addr_strings(value), old_elements, root, report, "member"
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
                f"context:{ctx.get('namespace') or 'issue'}",
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
    report.new_text = records.dumps(post)
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
