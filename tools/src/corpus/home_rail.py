"""#89: the related-information rail comes home — a trailing `<!--section nav-->` (ATH-CORPUS
3.5's framing restoration, §4.3.2.1/§12.27, licensed for this host by the `my.alldata.com`
origin overlay's `regions:` declaration of `related-information` as `renders: framing`).

The sibling of `home_crumb`, and the other half of the same restoration. Where that module
MOVES a breadcrumb line the record already renders, this one RENDERS a rail the record does
not: the page's cross-link sidebar sits in retired `<!--context relation/related-information-->`
blocks — a side-channel, because a record could once hold only one form and a page that is an
article *and* an index had nowhere to put the second half (§12.27). Lifting the whole-record
section's sibling prohibition removes the reason, and the rail's links, labels, order, and
addresses all come from the artifact, so the restored span is verifiable against the same
bytes the record already attests rather than authored from memory.

**Additive only, deliberately.** The `relation` blocks are left exactly where they are.
`corpus drop-retired` owns their removal (§12.27) and already refuses to drop a rail that has
not come home — 4,781 records held on precisely that reason. Two halves, each independently
verifiable: this verb writes the span, that one releases its own hold once the span claims the
address. A single verb doing both would have no state in which the restoration could be
checked before the source of truth for it was deleted.

**The rendering is the overlay's, stated once and read here:**

> Render each entry as a markdown link, source order, the source's own labels, at the rail's
> own address. **Never write a `corpus://<id>`** — at the corpus layer records link only via
> URLs, and whether a target is captured is resolved at read time (spec §12.4.7). Drop any
> entry pointing back at this same page (no self-edges).

Entries group by ADDRESS, and the grouping is the source's own: the rail is a nested
accordion, so a typical record carries ~13 entries across ~6 addresses, and entries sharing an
address are siblings in one group. One `<!--segment text-->` per address, its body the group's
bullet list, in first-appearance order of addresses and source order within each group. The
span's envelope is then the ordered address list its segments derive (§6.1.1) — never
hand-written.

**Placement — trailing is the ordering rule, not a preference** (§4.3.2.1: within a span the
source's presented order, across spans significance order; the rail is the page's frame, not
its subject). Three cases, and the population splits across all three:

- **join** (113) — the record already carries a trailing bare framing span, the one
  `corpus home-crumb` built for its breadcrumb (`<!--section nav-->` going forward, or the
  as-yet-unconverged `<!--section index-->` a prior run left — this verb re-spells that
  opener to `nav` as part of the join, converging it). The rail joins it, after the crumb:
  the overlay declares `breadcrumb-component` before `related-information`, and §7.2 says
  declaration order is the order framing regions take in that span. One framing span per
  record, which is what the overlay asks for.
- **append** (3,842 + the 584 below) — the record ends in some other span: a `form/article` /
  `procedure` / `document` / `schematic` span, or — since #89 minted `form/nav` — a
  `form/index` span too, bare or not, alone or not. A new trailing `nav` span goes after it;
  `nav` and `index` are different form ids, so §4.3.2.1's adjacent-same-form rule never arms
  between them, no matter what the preceding span declares.
- **formless** (241) — the record's content zone is bare top-level segments. The new trailing
  nav span is its only span, appended after them (§4.3.2.1's before-only rule admits
  formless segments ahead of a section). **This one has a visible consequence and it is not a
  lint finding, so no gate here can see it:** `derived_state` reads `formed` off the presence
  of any qualified form section (§4.1), so these records move `rendered` → `formed` on the
  commit that writes the span — 237 of them on the public hub — while their SUBJECT content is
  still formless. The record is not lying (a form section does govern a span of it), but a
  worklist that reads the layer census as "has this record been through a forming pass" will
  stop seeing them. Disclosed here rather than discovered in a health diff.

**The case this used to REFUSE, now resolved** (584 records, every one of them measured as
its record's SOLE top-level block): the record's whole content zone is one `form/index` span.
Before #89, the rail's own restoration wrote a trailing `form/index` span too, and `form/index`
declares no fields (§7.8), so two adjacent bare index spans satisfy §4.3.2.1's equality test
and the grammar merges them on sight — appending there would not have created a second,
distinguishable span, it would have produced one span mixing the page's own link list with its
framing indistinguishably. `form/nav` ends the overload: an index span and a nav span are
never equal under §4.3.2.1 regardless of what either declares, so the append case above now
covers this population outright — no field, no `drop-retired` ordering, no trap. #89 is the
record of the resolution; `home_crumb` made and refused the identical trap for the same
population, and its refusal disarms the same way.

Same discipline as `home_crumb` / `drop_retired`: compute, never write; the record's own
dumps-stability and an emit round-trip gate every rewrite; the **neutrality gate** holds any
record whose rewrite would raise ANY lint rule's finding count (not just a rule we predicted —
a prior migration traded one finding for another and only an all-rules diff caught it); and a
**positive landing check** proves the span actually landed, trailing, carrying every
non-self-edge entry at its own address, with the `relation` blocks still intact. Not "nothing
got worse": a previous migration reported 641 merges while writing nothing, and its neutrality
gate passed.
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

#: Touch identifier stamped on every record this migration rewrites.
TOUCH_ID = "migrate.rail-89"

#: The one origin this migration knows how to handle — its overlay is what names the rail a
#: framing region and states the rendering contract quoted above (spec §7.2).
HOST = "my.alldata.com"

#: The retired context predicate the rail lives in today (§4.3.3.5).
NAMESPACE = "relation"
PREDICATE = "related-information"

#: Characters that would make a markdown link ambiguous rather than merely ugly. The corpus
#: carries none of them today (measured: 0 of 74,795 entries) — the guard is here because a
#: rendering that cannot be read back is a fabrication, not a formatting problem.
_UNSAFE_TEXT = re.compile(r"[\[\]\n\r]")
_UNSAFE_URL = re.compile(r"[()\s<>\n\r]")


class RailHold(ValueError):
    """A record this migration refuses to touch. Carries the reason."""


@dataclass
class RailHome:
    record_id: str
    relpath: str
    changed: bool = False
    #: not this origin / no rail / already restored.
    skipped: str | None = None
    hold: str | None = None
    counts: Counter[str] = dataclass_field(default_factory=Counter)
    new_text: str | None = None


# ---------- reading the rail off the record ---------- #


def rail_blocks(post: Any) -> list[dict[str, Any]]:
    """The record's `relation/related-information` context blocks, in record order — which is
    the source's own order, since the lift wrote them as it walked the rail.

    Read through `records.iter_context_blocks`, i.e. as parsed YAML, never off the raw bytes:
    every `target_url` on this host is YAML-quoted (`'#/vehicle/…'`) and a regex would carry
    the quotes into the link."""
    return [
        ctx
        for ctx in records.iter_context_blocks(post)
        if str(ctx.get("namespace") or "") == NAMESPACE
        and str(ctx.get("id") or "") == PREDICATE
    ]


def _own_routes(post: Any) -> set[str]:
    """Every route this record's own origin blocks name — the fragment after `#`, which is the
    whole of the identity on a hash-routed SPA.

    ALL of them, aliases included, not just the primary: the dedup fold writes a record's
    alternate names into the same `uri:` list, and a rail entry pointing at an alias points at
    THIS page. That is what makes the test sufficient without inventing a normalization —
    comparing raw fragments against the full alias set finds exactly the 43 self-edges a
    normalized comparison finds."""
    out: set[str] = set()
    for blk in records.iter_origin_blocks(post):
        uri = (blk.get("fields") or {}).get("uri")
        for value in uri if isinstance(uri, list) else [uri]:
            if isinstance(value, str) and value.strip():
                frag = value.split("#", 1)[1] if "#" in value else value
                out.add(frag.rstrip("/"))
    return out


def _grouped(entries: list[dict[str, Any]]) -> list[tuple[str, list[tuple[str, str]]]]:
    """`[(address, [(text, url), …]), …]` — addresses in first-appearance order, entries in
    source order within each address. The rail is a nested accordion, so entries sharing an
    address are siblings of one group and belong in one segment; the alternative (a segment
    per entry) would state a structure the source does not have."""
    order: list[str] = []
    groups: dict[str, list[tuple[str, str]]] = {}
    for ctx in entries:
        fields = ctx.get("fields") or {}
        address = fields.get("address")
        text = fields.get("target_text")
        url = fields.get("target_url")
        if not isinstance(address, str) or not isinstance(text, str) or not isinstance(url, str):
            raise RailHold(
                "a `relation` block is missing one of address / target_text / target_url, or "
                "carries a non-scalar — refusing to render an entry we cannot read"
            )
        if address not in groups:
            order.append(address)
            groups[address] = []
        groups[address].append((text.strip(), url.strip()))
    return [(a, groups[a]) for a in order]


def _check_address(address: str) -> None:
    """Refuse an address this rewrite cannot address with. `el=` is validated against the
    §6.1.1 path grammar (every rail address in the corpus is one); any other axis is accepted
    as an opaque single-line scalar, which is all the segment header needs of it."""
    if not address.strip() or "\n" in address:
        raise RailHold(f"a rail address is empty or multi-line ({address!r})")
    head, sep, tail = address.partition("=")
    if not sep:
        raise RailHold(f"a rail address names no axis ({address!r})")
    if head == "el":
        try:
            furi.parse_el_path(tail.split("&", 1)[0])
        except Exception as exc:
            raise RailHold(f"a rail address does not parse ({address!r}: {exc})") from exc


def _bullet(text: str, url: str) -> str:
    """One rail entry as a markdown link. The overlay's rule, enforced rather than assumed:
    never a `corpus://` target — at the corpus layer records link only via URLs, and whether a
    target is captured is a read-time resolution (§12.4.7)."""
    if not text:
        raise RailHold("a rail entry carries an empty `target_text` — nothing to label it with")
    if not url:
        raise RailHold(f"the rail entry {text!r} carries an empty `target_url`")
    if url.startswith("corpus://"):
        raise RailHold(
            f"the rail entry {text!r} already targets a `corpus://` id — the overlay forbids "
            f"writing one (§12.4.7); the stored value needs correcting, not rendering"
        )
    if _UNSAFE_TEXT.search(text):
        raise RailHold(f"the rail entry {text!r} carries brackets or a newline — unrenderable")
    if _UNSAFE_URL.search(url):
        raise RailHold(f"the rail entry {text!r} has a url with spaces or parens: {url!r}")
    return f"- [{text}]({url})"


# ---------- the migration ---------- #


def _placement(blocks: list[segments.Block]) -> tuple[str, segments.Section | None]:
    """Where the rail's span goes: `("join", section)` / `("append", None)` /
    `("formless", None)`.

    The join case is the framing span `home_crumb` built and nothing else — a **bare**
    span (no declared fields at all), trailing, on a record that has other blocks, spelled
    `nav` (the current shape) or `index` (a prior run's spelling, not yet converged — the join
    re-spells it). That is exactly `home_crumb`'s own "already homed" test.

    Everything else appends a fresh trailing `form/nav` span, including a record whose last
    block is a `form/index` span that is NOT the crumb's bare home (carries its own fields, or
    is the record's sole block, or both): `nav` and `index` are different form ids, so
    §4.3.2.1's adjacent-same-form rule cannot arm between them, no matter what either span
    declares — the case this migration used to refuse outright (see the module docstring)."""
    if not blocks:
        raise RailHold("the record has an empty content zone — nothing to place a rail after")
    last = blocks[-1]
    if not isinstance(last, segments.Section):
        return "formless", None
    if last.form == "nav":
        return "join", last
    if last.form != "index":
        return "append", None
    bare = not last.extra and last.entry is None and last.description is None
    if bare and len(blocks) > 1:
        return "join", last  # old spelling — the join re-spells it to `nav`
    return "append", None


def home_rail_record(record_file: Path, corpus_root: Path) -> RailHome:
    """Compute (never write) the §89 rail restoration for one record. The caller applies
    `report.new_text` when `report.changed`; a `hold` means hands off."""
    original = record_file.read_text(encoding="utf-8")
    post = records.load(record_file)
    rid = str(post.metadata.get("id") or record_file.stem)
    report = RailHome(record_id=rid, relpath=str(record_file.relative_to(corpus_root)))

    if not any((b.get("id") or "") == HOST for b in records.iter_origin_blocks(post)):
        report.skipped = f"not a {HOST} record"
        return report

    entries = rail_blocks(post)
    if not entries:
        report.skipped = "no related-information rail on this record"
        return report

    try:
        blocks = segments.iter_blocks(post.content or "")
    except ValueError as exc:
        report.hold = f"content zone does not parse: {exc}"
        return report

    # Serializer stability, the §12.28 rule: the rewrite goes through the real serializer, so a
    # difference it would introduce on its own must be disclosed before we add ours. All 4,780
    # rail records pass this strictly, so the gate costs nothing and is worth keeping strict.
    if records.dumps(post) != original:
        report.hold = "record is not dumps-stable; the serializer would introduce unrelated changes"
        return report

    # The rail's own reading, and every refusal it can raise, before anything is built.
    try:
        groups = _grouped(entries)
        own = _own_routes(post)
        rendered: list[tuple[str, str]] = []  # (address, body)
        dropped = 0
        for address, items in groups:
            _check_address(address)
            lines = []
            for text, url in items:
                if (url.split("#", 1)[1] if "#" in url else url).rstrip("/") in own:
                    dropped += 1  # a self-edge: the rail pointing back at this same page
                    continue
                lines.append(_bullet(text, url))
            if lines:
                rendered.append((address, "\n".join(lines)))
        placement, join_target = _placement(blocks)
    except RailHold as exc:
        report.hold = str(exc)
        return report

    if not rendered:
        report.hold = (
            f"every one of this record's {len(entries)} rail entries is a self-edge back at "
            f"this same page — the restored span would be empty, and an empty framing span "
            f"states something the source does not"
        )
        return report

    # Already restored — a completed pass must be inert, not a hold, because the span this
    # move creates is indistinguishable from one it would create again. Tested structurally
    # (the trailing span already carries each group at its own address) rather than off the
    # touch, so a record restored by hand reads the same as one restored by this verb.
    trailing_now = blocks[-1] if isinstance(blocks[-1], segments.Section) else None
    if trailing_now is not None:
        have = {
            (str(s.address), (s.body or "").strip())
            for s in trailing_now.segments
            if isinstance(s, segments.Segment)
        }
        want = {(a, b) for a, b in rendered}
        if want <= have:
            report.skipped = "already restored — the rail sits in the trailing framing span"
            return report
        if want & have:
            report.hold = (
                f"{len(want & have)} of {len(want)} rail groups are already in the trailing "
                f"span and the rest are not — a partial restoration, refusing to complete "
                f"someone else's pass"
            )
            return report

    before = Counter(f.rule_id for f in lint.lint(post, blocks, corpus_root))

    # ---- the restoration: one text segment per address, in a trailing nav span ---- #
    new_segments = [
        segments.Segment(atom="text", address=address, body=body) for address, body in rendered
    ]
    new_blocks = list(blocks)
    if placement == "join" and join_target is not None:
        # The crumb first, the rail after: the overlay declares `breadcrumb-component` before
        # `related-information`, and §7.2 makes declaration order the order framing regions
        # take in the trailing span. Re-spelling the opener to `nav` is idempotent when it is
        # already `nav`, and is exactly the convergence a legacy `index`-spelled crumb span
        # needs — one write, gated the same as any other.
        join_target.segments = list(join_target.segments) + new_segments
        join_target.form = "nav"
        join_target.address = None  # re-derived over the widened child set (§4.3.2.1)
    else:
        new_blocks.append(segments.Section(form="nav", segments=new_segments))

    post.content = segments.emit(new_blocks).rstrip("\n") + "\n"
    touches.record_touch(post, touches.script_identifier(TOUCH_ID))
    new_text = records.dumps(post)

    # Round-trip on the TEXT: a section's `address` is derived from its children (§4.3.2.1,
    # §12.29), so the in-memory envelope is stale by construction here — the reparse is the
    # check that matters (the same discipline `home_crumb` and `drop_retired` apply).
    try:
        reparsed = segments.iter_blocks(post.content)
    except ValueError as exc:
        report.hold = f"rewritten content zone does not parse: {exc}"
        return report
    if segments.emit(reparsed).rstrip("\n") != post.content.rstrip("\n"):
        report.hold = (
            "rewritten content zone does not survive an emit round-trip losslessly (the "
            "commonest cause is a trailing span the parse merges into its neighbour)"
        )
        return report

    # The neutrality gate (§12.28): the whole rule set, deliberately — the failure worth
    # catching is the unpredicted one. It is also what catches the rail whose address a
    # content segment already claims (`segment-address-duplicate`), which §12.27 measured at
    # 6 occurrences corpus-wide and which no rule of this module's own would have seen.
    after_post = records.loads(new_text)
    after = Counter(f.rule_id for f in lint.lint(after_post, reparsed, corpus_root))
    worse = sorted(rule for rule in set(before) | set(after) if after[rule] > before.get(rule, 0))
    if worse:
        report.hold = (
            "rewrite would raise lint findings ("
            + ", ".join(f"{r}: {before.get(r, 0)}→{after[r]}" for r in worse)
            + ")"
        )
        return report

    # The positive landing check. A neutrality gate cannot tell a landed rewrite from no
    # rewrite at all — a prior migration reported 641 merges while writing nothing and passed
    # its gate — so this asserts what the verb CLAIMS, not merely that nothing regressed.
    hold = _landed(reparsed, rendered, after_post, len(entries))
    if hold:
        report.hold = hold
        return report

    report.counts["rail restored"] += 1
    report.counts[f"placement: {placement}"] += 1
    report.counts["entries rendered"] += sum(b.count("\n") + 1 for _, b in rendered)
    report.counts["addresses"] += len(rendered)
    if dropped:
        report.counts["self-edges dropped"] += dropped
    report.new_text = new_text
    report.changed = True
    return report


def _landed(
    reparsed: list[segments.Block],
    rendered: list[tuple[str, str]],
    after_post: Any,
    rail_entries: int,
) -> str | None:
    """Return a hold reason when the rewrite did not actually land what it says it did.

    Four claims, each checked on the RE-PARSED record rather than on the objects we built:
    the span is trailing and is a `nav` span; it carries every rendered group at its own
    address, exactly once; no group leaked into a block ahead of it; and the `relation` blocks
    are all still there, because this half of §12.27 is additive and `drop-retired` owns the
    other half."""
    trailing = reparsed[-1] if reparsed else None
    if not (isinstance(trailing, segments.Section) and trailing.form == "nav"):
        return "internal: no trailing form/nav span in the rewritten record"
    landed = [
        (str(s.address), (s.body or "").strip())
        for s in trailing.segments
        if isinstance(s, segments.Segment)
    ]
    for address, body in rendered:
        n = landed.count((address, body))
        if n != 1:
            return (
                f"internal: the trailing span carries the rail group at `{address}` {n} times, "
                f"not exactly once — refusing a dangling or duplicated restoration"
            )
    ahead = {
        (str(s.address), (s.body or "").strip())
        for blk in reparsed[:-1]
        for s in (blk.segments if isinstance(blk, segments.Section) else [blk])
        if isinstance(s, segments.Segment)
    }
    stray = sorted(a for a, b in rendered if (a, b) in ahead)
    if stray:
        return (
            f"internal: {len(stray)} rail group(s) also appear ahead of the trailing span "
            f"({stray[0]}…) — the framing must trail the content (§4.3.2.1)"
        )
    kept = len(rail_blocks(after_post))
    if kept != rail_entries:
        return (
            f"internal: {rail_entries - kept} `relation` block(s) went missing — this half of "
            f"§12.27 is additive; `corpus drop-retired` removes them, not this verb"
        )
    return None
