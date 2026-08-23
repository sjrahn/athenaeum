"""The v35 addressing remap: dotted child-index paths (and any remaining pre-3.6 legacy
stragglers) → document-order ordinals (spec §6.1.1, CHANGELOG v35).

The migration engine for ATH-CORPUS v35, in the `remap_el.py` mold (the §12.28 engine for
3.6): a pure mechanical mapping over an immutable artifact, proven by re-resolving every
produced address to the IDENTICAL element the old grammar named, held with a reason
whenever it cannot be proven, idempotent (an already ordinal-stamped record is a no-op),
dry-run by default.

**Two source generations, one target.** Unlike the 3.6 engine (which mapped between two
DIFFERENT enumerations over the same tree — the filtered whitelist and the total walk),
dotted paths and ordinals name positions in the *same* total tree, so a DOTTED-stamped
record's mapping needs no artifact re-walk beyond the one parse: resolve the old path to
its element, read that element's ordinal. A LEGACY-unstamped straggler (a record the 3.6
sweep never reached) is handled directly here too — straight to ordinal, never staged
through an intermediate dotted rewrite — using the same "tightest containing address"
range logic `remap_el.map_el_value` established, spelled in ordinals instead of paths.

Surfaces rewritten, per record (`remap_el.py`'s list, extended):

- content-zone section / segment / structural / placement addresses,
- member (embed/placement) roster rows,
- annotation-zone context blocks (`issue` / legacy `relation` / `reference`),
- **origin-block lineage URIs** (`uri: corpus://<container>?el=<value>`, §8.1) — new for
  v35. A promoted member leaf's origin cites an address in its CONTAINER's space, not its
  own, so this surface is mapped against the container's tree, resolved by hash. The
  caller (the CLI sweep) supplies a `container_pairings` cache built and consulted the
  same way across the WHOLE fleet run, in a single read-only pass BEFORE any record is
  written — see `ContainerPairing`/`container_pairing` below — so a container's OWN stamp
  never changes out from under a leaf record that cites it, regardless of which record the
  sweep visits first.

The record is then restamped `addressing: {parser, elements, scheme: ordinal}` (parser +
element count carried over unchanged — the artifact's bytes never move) and the migration
touch appended. A record already ordinal-stamped is skipped (idempotent). A record the
engine cannot remap mechanically — unreachable artifact bytes, a drifted parse, an
unprovable/unmappable address — is HELD with a reason, zero partial writes.

**A markup record with a pre-ordinal stamp but ZERO stored/cited el= addresses is not
"nothing to do".** The bare route and `?annotated` (§6.1, §6.1.1) key off the STAMP, not
off whether anything has addressed the artifact yet — a page nobody has drafted `el=`
segments for yet is exactly the one a scribe most needs the annotated view for. Such a
record gets a STAMP-ONLY remap: the same parser-identity + element-count drift checks run
against the artifact (flipping the scheme still asserts the ordinal space is computable
under the attested parse), then it is restamped and touched with zero address mappings —
reported via `RecordRemap.stamp_only` so the manifest stays honest about what actually
moved (distinct from `skipped`, which is reserved for a record this engine has no
business touching at all — a non-HTML mime with no el= anywhere)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from corpus import containment, lint, paths, records, segments, touches
from corpus import functional_uri as furi
from corpus import mime as mime_mod
from corpus.transforms.html import (
    EL_PARSER_ID,
    element_ordinal,
    iter_element_children,
    legacy_is_addressable,
    ordinal_interval,
    ordinals_are_siblings,
    path_root,
    resolve_element_path,
    resolve_ordinal,
    total_element_count,
)

#: Touch identifier stamped on every record the remap actually rewrites.
TOUCH_ID = "migrate.el-ordinal-35"

_POINT_RE = re.compile(r"^\d+$")
_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


class RemapHold(ValueError):
    """The record (or one address on it) cannot be remapped mechanically — held with a
    reason, never guessed."""


@dataclass
class RecordRemap:
    """One record's remap outcome. `changed` means a rewrite was produced (and applied,
    when the caller asked for apply); `hold` carries the refusal reason when not."""

    record_id: str
    relpath: str
    changed: bool = False
    skipped: str | None = None          # already ordinal-stamped / no el addresses, non-HTML
    hold: str | None = None             # mechanical refusal, with reason
    generation: str | None = None       # "dotted" | "legacy" — the source grammar
    elements: int = 0                   # attested total element count
    emit_normalized: bool = False       # re-emit normalizes surface form (disclosed rider)
    stamp_only: bool = False            # restamped with zero address mappings — see below
    mappings: list[dict[str, Any]] = dataclass_field(default_factory=list)
    forms: dict[str, int] = dataclass_field(default_factory=dict)
    new_text: str | None = None         # the rewritten record, when changed


def _tally(report: RecordRemap, where: str, old: str, new: str | list[str], form: str) -> None:
    report.mappings.append({"where": where, "old": old, "new": new, "form": form})
    report.forms[form] = report.forms.get(form, 0) + 1


# ---------- ordinal-producing point/range mapping ---------- #


def _ordinal_of(tag: Tag, root: Tag, label: str) -> int:
    """The ordinal of `tag` under `root`, verified by re-resolution — the same
    identity-proof discipline `remap_el.map_el_value`'s `path_of` applies."""
    n = element_ordinal(tag, root)
    if n is None:
        raise RemapHold(f"el={label}: element sits outside the ordinal root (<body>)")
    back = resolve_ordinal(root, n)
    if back is not tag:
        raise RemapHold(f"el={label}: ordinal {n} did not re-resolve to the same element")
    return n


def _tightest_ordinal_range(first: Tag, last: Tag, root: Tag, label: str) -> tuple[str, str]:
    """The tightest §6.1.1 ordinal address containing the interval `[first, last]` —
    `remap_el.map_el_value`'s range algorithm, spelled in ordinals: a subtree's own
    ordinal when one endpoint's subtree holds the other or both land in one child of
    their nearest common ancestor, else the sibling range `[A-B]` over the endpoints'
    slots in that ancestor. Raises `RemapHold` exactly where the 3.6 engine does — no
    common ancestor, spans the ordinal root's own children (no sibling-range spelling),
    or a produced range whose endpoints fail the sibling proof."""
    if first is last:
        return str(_ordinal_of(first, root, label)), "subtree"

    fi, li = ordinal_interval(first, root), ordinal_interval(last, root)
    if fi is not None and li is not None:
        if fi[0] <= li[0] and li[1] <= fi[1]:
            return str(_ordinal_of(first, root, label)), "subtree"
        if li[0] <= fi[0] and fi[1] <= li[1]:
            return str(_ordinal_of(last, root, label)), "subtree"

    ancestors = {id(t): t for t in first.parents}
    anc = next((p for p in last.parents if id(p) in ancestors), None)
    if anc is None:
        raise RemapHold(f"el={label}: the range's endpoints share no common ancestor")

    def slot_of(tag: Tag, kids: list[Tag]) -> int:
        branch = tag
        while branch.parent is not None and branch.parent is not anc:
            branch = branch.parent
        slot = next((i for i, k in enumerate(kids, start=1) if k is branch), None)
        if slot is None:
            raise RemapHold(
                f"el={label}: endpoint's branch is not a child of the common ancestor"
            )
        return slot

    kids = iter_element_children(anc)
    a, b = slot_of(first, kids), slot_of(last, kids)
    if a == b:  # both endpoints inside one child of the ancestor: that child's subtree
        return str(_ordinal_of(kids[a - 1], root, label)), "subtree"
    anc_ordinal = element_ordinal(anc, root)
    if a == 1 and b == len(kids) and anc_ordinal is not None:
        # The interval spans every child of the ancestor — its own ordinal covers it
        # exactly, the same "one extent, one spelling" rule as the dotted engine.
        return str(anc_ordinal), "subtree"
    if anc_ordinal is None:
        # The nearest common ancestor is the ordinal root itself — no §6.1.1 spelling for
        # a range over the root's own children; re-scoping is a judgment, not a rewrite.
        raise RemapHold(
            f"el={label}: the range spans the ordinal root's own children, which has no "
            f"§6.1.1 sibling-range spelling — re-scope this address deliberately"
        )
    lo_ord, hi_ord = element_ordinal(kids[a - 1], root), element_ordinal(kids[b - 1], root)
    if lo_ord is None or hi_ord is None or not ordinals_are_siblings(root, lo_ord, hi_ord):
        raise RemapHold(
            f"el={label}: computed sibling range failed the siblinghood proof — engine "
            f"invariant violated, refusing to emit an invalid address"
        )
    return f"[{lo_ord}-{hi_ord}]", "sibling"


def map_dotted_value_to_ordinal(value: str, root: Tag) -> tuple[str, str]:
    """Map one DOTTED `el=` value (`"1.3.2"` / `"1.3.[2-9]"`) to its v35 ordinal
    replacement: a point path resolves to its element, whose ordinal IS the mapping
    (proven by re-resolution); a dotted sibling range `P.[a-b]` maps to `[A-B]`, the
    ordinals of P's a-th and b-th element children (siblings by construction — proven
    anyway, the same discipline as every other produced address here)."""
    try:
        path = furi.parse_el_path(value)
    except ValueError as exc:
        raise RemapHold(f"el={value}: not a valid dotted address: {exc}") from exc

    if path.sibling_range is None:
        try:
            tag = resolve_element_path(root, path)
        except ValueError as exc:
            raise RemapHold(f"el={value}: does not resolve: {exc}") from exc
        return str(_ordinal_of(tag, root, value)), "point"

    parent_path = furi.ElPath(components=path.components)
    try:
        parent = resolve_element_path(root, parent_path)
    except ValueError as exc:
        raise RemapHold(f"el={value}: parent path does not resolve: {exc}") from exc
    kids = iter_element_children(parent)
    a, b = path.sibling_range
    if not (1 <= a < b <= len(kids)):
        raise RemapHold(
            f"el={value}: sibling range [{a}-{b}] is not within the parent's "
            f"{len(kids)} children"
        )
    ta, tb = kids[a - 1], kids[b - 1]
    oa, ob = _ordinal_of(ta, root, value), _ordinal_of(tb, root, value)
    if not ordinals_are_siblings(root, oa, ob):
        raise RemapHold(
            f"el={value}: mapped ordinals [{oa}-{ob}] failed the siblinghood proof — "
            f"engine invariant violated"
        )
    return f"[{oa}-{ob}]", "sibling"


def map_legacy_value_to_ordinal(
    value: str, old_elements: list[Tag], root: Tag
) -> tuple[str | list[str], str]:
    """Map one pre-3.6 LEGACY `el=` value (`"5"` / `"3-7"`) straight to its v35 ordinal
    replacement — `remap_el.map_el_value`'s point/range/fallback-wrapper algorithm,
    spelled in ordinals instead of dotted paths."""
    if _POINT_RE.match(value):
        n = int(value)
        if n == 1 and not old_elements:
            # The documented drafter fallback (§12.25/§12.28), carried forward: a
            # zero-element legacy enumeration forced a guaranteed-unresolvable `el=1`
            # placeholder onto the whole-document wrapper. Under the total space the
            # prose takes the ordinals of the elements that actually contain it.
            kids = iter_element_children(root)
            if not kids:
                raise RemapHold(
                    "el=1 fallback on a body with no element children — nothing to "
                    "re-point it at"
                )
            ords = [str(_ordinal_of(t, root, "1[fallback]")) for t in kids]
            if len(ords) == 1:
                return ords[0], "fallback-wrapper"
            return ords, "fallback-wrapper"
        if not (1 <= n <= len(old_elements)):
            raise RemapHold(
                f"el={value}: out of range (the legacy enumeration has "
                f"{len(old_elements)} elements)"
            )
        return str(_ordinal_of(old_elements[n - 1], root, value)), "point"

    m = _RANGE_RE.match(value)
    if m is None:
        raise RemapHold(f"el={value}: unrecognized legacy value shape")
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi or lo < 1 or hi > len(old_elements):
        raise RemapHold(
            f"el={value}: range out of bounds (the legacy enumeration has "
            f"{len(old_elements)} elements)"
        )
    new, form = _tightest_ordinal_range(old_elements[lo - 1], old_elements[hi - 1], root, value)
    return new, form


def check_override(new: str, root: Tag) -> None:
    """Validate a deliberate re-address before it enters a record — the ordinal-space
    counterpart of `remap_el.check_override`."""
    value = new[3:] if new.startswith("el=") else new
    value = value.split("&", 1)[0].split("/", 1)[0]
    try:
        ordinal = furi.parse_el_ordinal(value)
    except ValueError as exc:
        raise RemapHold(f"override {new!r} is not a §6.1.1 ordinal address: {exc}") from exc
    if ordinal.sibling_range is None:
        try:
            resolve_ordinal(root, ordinal.point)
        except ValueError as exc:
            raise RemapHold(f"override {new!r}: resolves to no element — {exc}") from exc
        return
    a, b = ordinal.sibling_range
    try:
        siblings = ordinals_are_siblings(root, a, b)
    except ValueError as exc:
        raise RemapHold(f"override {new!r}: resolves to no element — {exc}") from exc
    if not siblings:
        raise RemapHold(f"override {new!r}: ordinals {a} and {b} are not siblings")


# ---------- surface sweep ---------- #


def _map_address_strings(
    addrs: list[str],
    generation: str,
    old_elements: list[Tag],
    root: Tag,
    report: RecordRemap,
    where: str,
    overrides: dict[str, str] | None = None,
) -> tuple[list[str], bool]:
    """Map every `el=`-leading string in an address's string list under the record's
    GENERATION (dotted or legacy), leaving other axes and chained-op suffixes untouched
    — `remap_el._map_address_strings`'s exact shape."""
    out: list[str] = []
    changed = False
    for a in addrs:
        if not a.startswith("el="):
            out.append(a)
            continue
        if overrides and a in overrides:
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
        if generation == "dotted":
            new, form = map_dotted_value_to_ordinal(value, root)
        else:
            new, form = map_legacy_value_to_ordinal(value, old_elements, root)
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


#: The one lint rule the neutrality gate cannot compare across THIS rewrite, for the same
#: reason `remap_el._DEFERRED_RULE` defers it: `segment-address-fidelity` judges stamped
#: records under WHICHEVER live grammar they carry, and its dispatch itself changes here
#: (dotted branch -> ordinal branch, or absent -> present for a legacy straggler) — its
#: count is not comparable before/after by construction, so a rise measures the record
#: becoming legible under the new dispatch, not the rewrite making it worse.
_DEFERRED_RULE = "segment-address-fidelity"


def _lint_neutrality_hold(new_text: str, before: Counter[str], corpus_root: Path) -> str | None:
    """Return a hold reason when the rewritten record would lint WORSE than the original
    — any rule whose finding count rises (minus `_DEFERRED_RULE`) — else None."""
    try:
        after_post = records.loads(new_text)
        after = _lint_tally(
            lint.lint(after_post, segments.iter_blocks(after_post.content or ""), corpus_root)
        )
    except Exception as exc:
        return f"post-remap lint did not run: {exc}"
    risen = {
        r: (before.get(r, 0), c)
        for r, c in after.items()
        if c > before.get(r, 0) and r != _DEFERRED_RULE
    }
    if not risen:
        return None
    detail = ", ".join(f"{r} {b}→{a}" for r, (b, a) in sorted(risen.items()))
    return (
        f"the rewrite would introduce new lint findings ({detail}) — the legacy/dotted "
        f"addresses alias under §6.1.1's ordinal space; re-address this record "
        f"deliberately"
    )


# ---------- cross-record: origin lineage URIs ---------- #


@dataclass
class ContainerPairing:
    """A container's tree, as it stood BEFORE this migration touched it — resolved once,
    cached, and shared across the whole fleet sweep so an origin URI on ONE record is
    always mapped against the container's PRE-migration grammar, regardless of whether
    the sweep visits the container before or after the record citing it (the sweep never
    writes during the pass that builds this cache — see `remap_record`'s
    `container_pairings` parameter)."""

    generation: str  # "dotted" | "legacy"
    old_elements: list[Tag]  # only populated for "legacy"; empty for "dotted"
    root: Tag


def container_pairing(container_hash: str, corpus_root: Path) -> ContainerPairing | str:
    """Build (uncached) the pairing for `container_hash`, or a string reason it cannot be
    built — the record resolves in this corpus, is HTML, is not already ordinal-stamped
    (an ordinal container needs no mapping — its citing URIs are handled by the SKIP
    path in `remap_origin_uris`, never routed here), and its artifact is resident."""
    try:
        rf = paths.record_path(corpus_root, container_hash)
        if not rf.is_file():
            return "container record does not exist in this corpus"
        post = records.load(rf)
    except Exception as exc:
        return f"container record could not be loaded: {exc}"
    media_type = records.media_type_for(post)
    if not media_type.startswith("text/html"):
        return f"container is a non-HTML mime ({media_type or 'none'})"
    stamp = records.el_addressing(post)
    generation = "dotted" if stamp is not None else "legacy"
    if stamp is not None and stamp.get("scheme") == "ordinal":
        return "container is already ordinal-stamped"
    try:
        binary = containment.ensure_local_bytes(
            corpus_root, container_hash, mime_mod.extension_for(media_type)
        )
        soup = BeautifulSoup(binary.read_bytes(), EL_PARSER_ID)
    except Exception as exc:
        return f"container artifact bytes not resident: {exc}"
    root = path_root(soup)
    old_elements = (
        [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]
        if generation == "legacy" else []
    )
    return ContainerPairing(generation=generation, old_elements=old_elements, root=root)


_ORIGIN_URI_RE = re.compile(r"^corpus://([0-9a-f]{64})\?(.*)$")


def _remap_origin_uri(
    uri: str, corpus_root: Path, cache: dict[str, ContainerPairing | str]
) -> tuple[str, str | None, str | None]:
    """Map one origin-block `uri:` string. Returns `(possibly-new uri, form|None,
    hold-reason|None)` — a non-`el=`-leading URI (any other lineage citation, or a plain
    http(s) URL) returns unchanged with no form and no hold, which is the common case."""
    m = _ORIGIN_URI_RE.match(uri)
    if not m:
        return uri, None, None
    container_hash, tail = m.group(1), m.group(2)
    fragment = ""
    if "#" in tail:
        tail, frag = tail.split("#", 1)
        fragment = f"#{frag}"
    chunks = tail.split("&")
    key, _, value = chunks[0].partition("=")
    if key != "el" or not value:
        return uri, None, None

    pairing = cache.get(container_hash)
    if pairing is None:
        pairing = container_pairing(container_hash, corpus_root)
        cache[container_hash] = pairing
    if isinstance(pairing, str):
        if pairing == "container is already ordinal-stamped":
            return uri, None, None  # nothing to do — already speaks this grammar
        return uri, None, pairing

    try:
        if pairing.generation == "dotted":
            new_value, form = map_dotted_value_to_ordinal(value, pairing.root)
        else:
            new_value, form = map_legacy_value_to_ordinal(value, pairing.old_elements, pairing.root)
    except RemapHold as exc:
        return uri, None, str(exc)
    if isinstance(new_value, list):
        return uri, None, (
            "maps to an address list (a region crossing subtree boundaries) — a lineage "
            "URI is one address; re-anchor interpretively"
        )
    new_uri = f"corpus://{container_hash}?{'&'.join(['el=' + new_value, *chunks[1:]])}{fragment}"
    return new_uri, form, None


def remap_origin_uris(
    post: Any, corpus_root: Path, cache: dict[str, ContainerPairing | str], report: RecordRemap
) -> bool:
    """Rewrite every `el=`-leading `corpus://<container>?el=…` origin lineage URI on
    `post` in place. Returns whether anything changed. Holds land on `report.hold` (the
    caller checks it and refuses the whole record — an origin lineage citation is
    provenance, not something this engine may leave half-mapped)."""
    changed = False
    for origin in records.iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        uris = fields.get("uri")
        if isinstance(uris, list):
            for i, uri in enumerate(uris):
                if not isinstance(uri, str):
                    continue
                new_uri, form, hold = _remap_origin_uri(uri, corpus_root, cache)
                if hold is not None:
                    report.hold = f"origin uri {uri!r}: {hold}"
                    return changed
                if new_uri != uri:
                    uris[i] = new_uri
                    _tally(report, "origin", uri, new_uri, form or "point")
                    changed = True
        elif isinstance(uris, str):
            # The polymorphic scalar form (spec §4.3.2's str|list[str] convention) — a
            # record with exactly one origin URI stores it bare, not as a one-item list.
            new_uri, form, hold = _remap_origin_uri(uris, corpus_root, cache)
            if hold is not None:
                report.hold = f"origin uri {uris!r}: {hold}"
                return changed
            if new_uri != uris:
                fields["uri"] = new_uri
                _tally(report, "origin", uris, new_uri, form or "point")
                changed = True
    return changed


# ---------- per-record engine ---------- #


def remap_record(
    record_file: Path,
    corpus_root: Path,
    overrides: dict[str, str] | None = None,
    container_pairings: dict[str, ContainerPairing | str] | None = None,
) -> RecordRemap:
    """Compute (never write) the v35 remap of one record. The caller applies
    `report.new_text` when `report.changed`; a `hold` means hands off.

    `container_pairings` is the fleet-shared cache `remap_origin_uris` reads/builds —
    pass the SAME dict across an entire sweep (never written to during the sweep, only
    read from disk on first access per container) so origin lineage URIs map against
    every cited container's PRE-migration state regardless of visit order."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = RecordRemap(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))
    cache = container_pairings if container_pairings is not None else {}

    stamp = records.el_addressing(post)
    if stamp is not None and stamp.get("scheme") == "ordinal":
        report.skipped = "already stamped (v35 ordinal addresses)"
        return report
    generation = "dotted" if stamp is not None else "legacy"
    report.generation = generation

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    def _addr_strings(value: Any) -> list[str]:
        return list(segments._iter_addr_strings(value))

    def _has_el(value: Any) -> bool:
        return any(a.startswith("el=") for a in _addr_strings(value))

    zone_has_el = any(
        _has_el(b.address)
        or (isinstance(b, segments.Section) and any(_has_el(s.address) for s in b.segments))
        for b in blocks
    )
    rows_have_el = any(_has_el(row.get("address")) for row in records.iter_members(post))
    ctx_have_el = any(
        _has_el((ctx.get("fields") or {}).get("address"))
        for ctx in post.metadata.get("_contexts") or []
    )
    origin_has_el = any(
        _ORIGIN_URI_RE.match(u) and "el=" in u.split("?", 1)[-1]
        for u in records.iter_origin_uris(post)
    )
    has_any_el = zone_has_el or rows_have_el or ctx_have_el or origin_has_el

    media_type = records.media_type_for(post)
    is_html_record = media_type.startswith("text/html")

    # A markup-family record with a pre-ordinal stamp (dotted, or no stamp at all) but
    # ZERO stored/cited el= addresses ANYWHERE is not "nothing to do": the ordinal space
    # becomes the record's live grammar the moment its stamp says so, and the bare route
    # / `?annotated` delivery (§6.1) depend on that stamp regardless of whether anything
    # has addressed the artifact yet — the exact page a scribe most needs the annotated
    # view for. This is a STAMP-ONLY remap: same drift checks against the artifact, zero
    # address mappings, reported distinctly (`report.stamp_only`) so the manifest stays
    # honest about what actually moved.
    stamp_only = is_html_record and not has_any_el
    report.stamp_only = stamp_only

    if not has_any_el and not is_html_record:
        report.skipped = "no el= addresses"
        return report
    if (zone_has_el or rows_have_el or ctx_have_el) and not is_html_record:
        report.hold = f"el= addresses on a non-HTML mime ({media_type or 'none'})"
        return report

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

    root: Tag | None = None
    old_elements: list[Tag] = []
    soup: BeautifulSoup | None = None
    if is_html_record and (zone_has_el or rows_have_el or ctx_have_el or stamp_only):
        try:
            binary = containment.ensure_local_bytes(
                corpus_root, rid, mime_mod.extension_for(media_type)
            )
        except Exception as exc:
            report.hold = f"artifact bytes not resident: {exc}"
            return report
        soup = BeautifulSoup(binary.read_bytes(), EL_PARSER_ID)
        parser = str((stamp or {}).get("parser") or "")
        if parser and parser != EL_PARSER_ID:
            report.hold = (
                f"record's el= addresses were computed under parser {parser!r}; this "
                f"toolchain resolves with {EL_PARSER_ID!r} (§6.1.1)"
            )
            return report
        actual = total_element_count(soup)
        attested = (stamp or {}).get("elements")
        if attested is not None and int(attested) != actual:
            report.hold = (
                f"element-count mismatch: the record attests {attested} elements, this "
                f"parse yields {actual} — the trees disagree (§6.1.1); re-attest first"
            )
            return report
        report.elements = actual
        root = path_root(soup)
        if generation == "legacy":
            old_elements = [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]

    before_findings = _lint_tally(lint.lint(post, blocks, corpus_root))

    try:
        zone_changed = False
        if root is not None:
            for b in blocks:
                targets = [b] + (list(b.segments) if isinstance(b, segments.Section) else [])
                for t in targets:
                    if t.address is None:
                        continue
                    was_list = isinstance(t.address, list)
                    mapped, ch = _map_address_strings(
                        _addr_strings(t.address), generation, old_elements, root, report,
                        "section" if isinstance(t, segments.Section) else
                        ("structural" if getattr(t, "is_structural", False) else "segment"),
                        overrides,
                    )
                    if ch:
                        t.address = _fold(mapped, was_list)
                        zone_changed = True

            for row in list(records.iter_members(post)):
                value = row.get("address")
                if value is None:
                    continue
                was_list = isinstance(value, list)
                mapped, ch = _map_address_strings(
                    _addr_strings(value), generation, old_elements, root, report,
                    "member", overrides,
                )
                if ch:
                    row["address"] = _fold(mapped, was_list)

            for ctx in post.metadata.get("_contexts") or []:
                fields = ctx.get("fields") or {}
                value = fields.get("address")
                if value is None:
                    continue
                was_list = isinstance(value, list)
                mapped, ch = _map_address_strings(
                    _addr_strings(value), generation, old_elements, root, report,
                    f"context:{ctx.get('namespace') or 'issue'}", overrides,
                )
                if ch:
                    fields["address"] = _fold(mapped, was_list)

            if generation == "legacy" and report.forms.get("fallback-wrapper"):
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
                        "where": "context:issue", "old": "partial-content/unaddressable-content",
                        "new": None, "form": "issue-retired",
                    })

        origin_changed = remap_origin_uris(post, corpus_root, cache, report)
        if report.hold:
            return report
    except RemapHold as exc:
        report.hold = str(exc)
        return report

    if not (zone_changed or origin_changed or root is not None):
        # The only way to reach here with nothing to do: a non-HTML leaf record whose
        # sole el= carrier was an origin lineage URI that turned out to need no rewrite
        # (its container is already ordinal-stamped). `root is not None` covers every
        # other has-el= case, since that always means a stamp write follows below.
        report.skipped = "el= references already resolved under the ordinal grammar"
        return report

    if zone_changed:
        post.content = segments.emit(blocks).rstrip("\n") + trailing

    if root is not None:
        artifact = records.artifact_block(post) or {"mime": media_type, "fields": {}}
        fields = dict(artifact.get("fields") or {})
        fields["addressing"] = {
            "parser": EL_PARSER_ID, "elements": report.elements, "scheme": "ordinal",
        }
        records.set_artifact_block(post, mime=artifact.get("mime") or media_type, fields=fields)

    touches.record_touch(post, touches.script_identifier(TOUCH_ID))
    new_text = records.dumps(post)

    lint_hold = _lint_neutrality_hold(new_text, before_findings, corpus_root)
    if lint_hold is not None:
        report.hold = lint_hold
        return report

    report.new_text = new_text
    report.changed = True

    # Final self-check: every ordinal address the remap produced is grammar-valid under
    # §6.1.1 (identity against the artifact was already proven per value, above). Origin
    # lineage URIs are skipped here — `_remap_origin_uri` already proves them the same
    # way, and re-parsing a full `corpus://` string (fragment and all) is redundant work
    # this loop would only get subtly wrong.
    for m in report.mappings:
        if m["where"] == "origin" or m["form"] == "issue-retired":
            continue
        produced = m["new"] if isinstance(m["new"], list) else [m["new"]]
        for v in produced:
            if v is None:
                continue
            value = str(v)
            value = value[3:] if value.startswith("el=") else value
            furi.parse_el_ordinal(value.split("&", 1)[0].split("/", 1)[0])

    return report
