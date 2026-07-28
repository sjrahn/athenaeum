"""Content-zone block grammar — emit + parse Sections and Segments.

Per spec/corpus.md §4.3, the record body has three zones. This module owns the
**content** zone: sections and segments. The **metadata** zone — including
`<!--embed--><br>` blocks — is owned by `records.py` (reconciliation #1 vs the reference,
which routed embeds through this module).

Content-zone grammar (§4.3.2):

- A `<!--section <form-id>-->` opens a **form span** (spec §4.3.2.1, 3.0): the qualified
  opener carries the record-scope form id (`conversation`, `statement`, `receipt`), exactly
  as a segment opener carries its atom id. The header carries the form overlay's codebook /
  envelope fields (e.g. `participants:`) — and *(3.7)* nothing else: the span envelope is
  DERIVED from the children (`section_address`, §12.29), never stored, so a form declaring no
  fields takes the one-line BARE OPENER `<!--section index-->`, which is the ordinary shape.
  `entry` + `description` read tolerantly until the 3.5 sweep reaches a record. Sections contain
  segments; they have no body of their own. Closer is followed directly by the first child
  segment opener — prose between is a parse error. A **bare** `<!--section-->` (no form id) is
  the 2.x TOC grouping unit — retired in place (§4.3.2.1); it reads tolerantly (form=None,
  contributes no `form/*` classification) so 2.x records round-trip until the grammar sweep.

- A `<!--segment <atom>-->` or `<!--segment <atom>/<overlay-id>-->` opens an atomic
  content block. `atom ∈ {text, image, audio, video}`, on the opener line; an
  atomic-overlay id (e.g. `text/data-table`, `image/photo`) may stand in place of the
  bare atom. Header: `address:` required; optional `perceptual`, `description`,
  `speaker`, `entry` (only when top-level). Only `text`-atom segments may carry a
  non-empty body; image/audio/video segments are body-empty positioning markers (§4.3.2.2).
  *(3.4 retired the per-asset embed description; 3.5 retires `description:` here too — the
  field is still read and round-tripped until the sweep lands.)*

- A `<!--segment structural-->` (spec §4.3.2.3, 3.0) is the fifth segment kind — the
  **byte-mark**: a body-empty mark recording that the source itself declares a structural
  boundary (a heading, an outline entry, a chapter mark, a topic boundary) at an `address`,
  with a `level:` (int; the source's own hierarchy, else 1) and an optional `mark:` (the
  mark's own text, verbatim — spelled `entry:` before 3.5, still read, re-emitted as `mark:`).
  It carries no content atom and no body, takes no atom overlay, and is excluded from
  `token_counts.body` (§9.6). Its identity is (`structural`, address), stacking beside content
  segments at the same address per the standard rule; unlike a content segment, a structural
  mark MAY carry its label inside a form section.

A record's content zone is a flat run of segments (the default), one or more sections, or —
the mixed-artifact case (§4.3.2.1) — formless top-level segments BEFORE the first section
opener, then the section(s) (a statement PDF's page-1 cover letter as bare segments, then a
`statement` section over pages 2-6). A segment after a section opener is that section's child
(the positional span), never a top-level sibling — so top-level mixing is admissible only in
the before-only direction. *(3.5)* A record MAY carry several sections. *(3.7: and the
whole-record special case is gone with the stored envelope — every span claims exactly its
children's extent, so there is no "claims the entire zone" to stand alone, §12.29.)*
Nesting depth = 1: sections contain segments; segments contain nothing; sections don't nest.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import yaml

_SECTION_OPENER = "<!--section"
_OPENER = "<!--segment"  # legacy form (atom in header) — accepted on read
_OPENER_PREFIX = "<!--segment "  # canonical form: `<!--segment <atom>`
_SUB_OPENER = "<!--sub-segment"  # legacy form — accepted on read
_SUB_OPENER_PREFIX = "<!--sub-segment "  # legacy form: `<!--sub-segment <atom>`
_CLOSER = "-->"

# Per spec §1.3: four atoms. Only `text` segments carry bodies; image/audio/video
# segments are body-empty positioning markers whose whole-asset descriptions live on
# the matching embed.
_VALID_ATOMS = frozenset({"text", "image", "audio", "video"})
# Per spec §4.3.2.3 (3.0): the fifth segment kind. Not an atom — carries no body, takes no
# atom overlay, is excluded from `token_counts.body`. Its opener-id is bare `structural`.
_STRUCTURAL = "structural"
# Every recognized segment opener-id axis: the four atoms plus the structural byte-mark.
_VALID_SEGMENT_KINDS = _VALID_ATOMS | {_STRUCTURAL}


@dataclass
class Segment:
    """Atomic content block — the universal primitive.

    `atom` is `text` / `image` / `audio` / `video`, named on the opener line
    (`<!--segment <atom>-->` or with an atomic overlay id like
    `<!--segment text/data-table-->`). Identity within a record is the pair
    (opener-id, address): the same source region may be re-projected through
    multiple atomic overlays, each as its own segment (spec §1.3, §4.3.2.2).

    `address` is a single address string OR an ordered list of address strings when the
    segment spans multiple non-contiguous source regions (in reading order).

    `perceptual` carries a per-segment fingerprint when produced (spec §7.7). Encoded
    `<algo>:<hex>` (e.g. `simhash:a4f1c9...`, `phash:...`, `chromaprint:...`).
    Production may be suspended in a given pipeline; existing values still round-trip.

    `entry` is a short authored leaf label — for a top-level segment in a multi-block
    record, OR for a segment inside a form section's span (spec §4.3.2.2; nesting
    admitted 2026-07-17, and the `segment-entry-in-section` lint rule retired with it,
    because a generic form span wraps an already-labeled rendering whole and the label's
    meaning never depended on being top-level). A record whose content zone is a single
    block carries none. *(3.5: retiring — an authored label with no consumer since 3.0
    moved the TOC to structural marks. Read and round-tripped; the sweep removes it.)*

    `mark` is the STRUCTURAL byte-mark's own text — the source's heading/outline/chapter
    text, verbatim (§4.3.2.3), checkable against the artifact like any attested fact.
    Set only when `is_structural`; never on a content segment. *(3.5: this was spelled
    `entry:` through 3.4, sharing a name with the authored label above while meaning the
    opposite — a value the source supplies rather than one a pass chose. `entry:` is still
    READ on a structural block for back-compat, and re-emits as `mark:`.)*

    `body` is the segment body. Only `text`-atom segments may carry a non-empty body;
    that body is a faithful, lossless rendering of the addressed content. Image,
    audio, and video segments are body-empty positioning markers.

    `description` is an optional scope-specific, normalizer-written description of
    what this segment represents — distinct from the embed's whole-asset description.

    Other header fields appear on `extra`. Order is preserved on emit. The legacy v0.3
    `mode:` field is stripped silently on read and never emitted.
    """

    atom: str
    address: str | list[str]
    perceptual: str | list[str] | None = None  # §7.6: scalar or list (multi-region)
    entry: str | None = None
    #: The structural byte-mark's own verbatim source text (§4.3.2.3, 3.5). Structural
    #: segments ONLY — a content segment carrying one is a grammar error, because the
    #: field's whole meaning is "the source said this."
    mark: str | None = None
    description: str | None = None
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    # The atomic-overlay id on the opener line, when more specific than the bare atom —
    # e.g. "text/data-table", "image/photo". On disk: `<atom>/<id>`; bundled schema
    # filename flattens to `schema/atom/<atom>/<atom>_<id>.yaml`.
    overlay: str | None = None
    # The structural byte-mark's own hierarchy level (§4.3.2.3), set ONLY on a
    # `atom == "structural"` segment (else None, never emitted). The source's declared depth
    # (h1-h6, outline depth, nav nesting), else 1.
    level: int | None = None

    @property
    def is_structural(self) -> bool:
        """True for the fifth segment kind — the `<!--segment structural-->` byte-mark
        (§4.3.2.3), which carries no content atom and no body."""
        return self.atom == _STRUCTURAL

    def to_header_dict(self) -> dict[str, Any]:
        """Return the dict that would be YAML-dumped between the header comment
        delimiters. `atom` (and any atomic overlay) sits on the opener line itself.

        A structural byte-mark emits `address`, then `level`, then `mark` (§4.3.2.3, 3.5):
        no body, no atom overlay, no perceptual/description, and never `entry`.

        Conversion is therefore one-way but NOT incidental: it happens wherever the content
        zone is re-emitted through `emit` (recordbuild / compile / shape / attest), and not
        on an ordinary `records.dumps`, which passes the parsed content zone through
        verbatim. A record touched only for a frontmatter or metadata-block change keeps
        its legacy spelling until something deliberately reconstructs it (§12.27)."""
        out: dict[str, Any] = {"address": self.address}
        if self.level is not None:
            out["level"] = self.level
        if self.perceptual is not None:
            out["perceptual"] = self.perceptual
        if self.mark is not None:
            out["mark"] = self.mark
        if self.entry is not None:
            out["entry"] = self.entry
        if self.description is not None:
            out["description"] = self.description
        extras = dict(self.extra)
        extras.pop("mode", None)  # legacy field, removed by our spec
        out.update(extras)
        return out


@dataclass
class Section:
    """The **form span** — a positional span over the content zone carrying a form id
    (spec §4.3.2.1, 3.0).

    A section declares that a span of the content zone has a named structural **form**
    (`conversation`, `statement`, `receipt`). The qualified opener carries the form id;
    the header carries the form overlay's codebook / envelope fields (on `extra`), an
    optional `address` (the span envelope — OMITTED on a whole-record form section), and
    optional `entry` + `description`. The section has no atom and no body of its own; its
    closer is followed directly by the first child segment opener.

    `form` is the form id on the opener (`<!--section conversation-->`); a **bare**
    `<!--section-->` has form=None — the 2.x TOC grouping unit, retired in place (§4.3.2.1)
    and read tolerantly so 2.x records round-trip until the grammar sweep. A qualified opener
    contributes `form/<id>` to the derived classifications view (§9.1).

    `description` is normalizer-written prose describing what this span IS.
    """

    address: str | list[str] | None = None
    entry: str | None = None
    form: str | None = None
    description: str | None = None
    segments: list[Segment] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_header_dict(self) -> dict[str, Any]:
        """*(3.7)* `address` is NOT emitted: a span's envelope is its children's, derived by
        every reader (`section_address`), so storing it would be a second copy of a fact the
        children already state — the construction §12.29 removes. `address` stays on the
        dataclass as the DERIVED value `iter_blocks` computes, for the consumers that want the
        span; it is simply never serialized. A temporal section states its bounds through its
        form's own declared field (on `extra`), which is why that case is unaffected."""
        out: dict[str, Any] = {}
        if self.entry is not None:
            out["entry"] = self.entry
        if self.description is not None:
            out["description"] = self.description
        out.update(self.extra)
        return out

    @classmethod
    def spanning(
        cls,
        segments: list[Segment],
        *,
        entry: str | None = None,
        form: str | None = None,
        description: str | None = None,
        fields: dict[str, Any] | None = None,
        el_paths: bool = False,
    ) -> Section:
        """Build a Section whose `address` is DERIVED as the envelope of `segments`' own
        addresses, in their discrete-index scheme (`page=`→`pages=`, `spine=`→`spines=`,
        `block=`, `sheet=`; `el=` under the 3.6 path algebra when `el_paths` is True — the
        caller reads the record's `addressing:` stamp, §6.1.1). The single place a section
        span is computed: drafters build sections this way instead of hand-formatting the
        range, and the `section-address-span` lint rule re-derives the same value to guard
        drift.

        `segments` must be non-empty and share one registered scheme. Raises ValueError when
        the span can't be derived (empty, heterogeneous, or an unrecognized/temporal scheme)
        — temporal (`time_range=`) sections are structural intervals, not content envelopes,
        and are built directly, not via this factory."""
        address = section_address(segments, el_paths=el_paths)
        if address is None:
            raise ValueError(
                "cannot derive a section address from these segments' addresses "
                "(empty, heterogeneous, or unrecognized scheme); pass non-empty children "
                "sharing one discrete-index scheme (page=/spine=/block=/sheet=)"
            )
        return cls(
            address=address,
            entry=entry,
            form=form,
            description=description,
            segments=list(segments),
            extra=dict(fields or {}),
        )


type Block = Section | Segment


# ---------- section-address derivation (spec §4.3.2.1) ---------- #


def _iter_addr_strings(address: str | list[str]) -> Iterator[str]:
    if isinstance(address, list):
        for a in address:
            if isinstance(a, str):
                yield a
    elif isinstance(address, str):
        yield address


def _leading_param(addr: str) -> tuple[str, str]:
    """Split an address into its leading `<param>=<value>`, dropping any `&`-joined
    sub-selectors (`page=5&bbox=…` → `("page", "5")`)."""
    head = addr.split("&", 1)[0]
    param, _eq, value = head.partition("=")
    return param.strip(), value.strip()


class _IntSpan:
    """Discrete integer scheme: child `<point>=N` (or an already-ranged `<sec>=A-B`) →
    section `<section_param>=lo-hi`, collapsing to `<section_param>=N` when lo==hi.
    `page`→`pages`, `spine`→`spines`, `block`→`block`."""

    def __init__(self, section_param: str) -> None:
        self.section_param = section_param

    def __call__(self, values: list[str]) -> str | None:
        lo: int | None = None
        hi: int | None = None
        for v in values:
            parts = v.split("-")
            try:
                a, b = int(parts[0]), int(parts[-1])
            except ValueError:
                return None
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)
        if lo is None or hi is None:
            return None
        return f"{self.section_param}={lo}" if lo == hi else f"{self.section_param}={lo}-{hi}"


class _NameSpan:
    """Single-key scheme: every child shares one `<param>=<name>` (e.g. an xlsx sheet)."""

    def __init__(self, section_param: str) -> None:
        self.section_param = section_param

    def __call__(self, values: list[str]) -> str | None:
        if len(set(values)) != 1:
            return None
        return f"{self.section_param}={values[0]}"


# Keyed by a CHILD segment's leading address param; the value formats the section's range
# form. Discrete-index schemes only — temporal `time_range=` sections are structurally
# bounded (chapter / speaker-run edges), not content envelopes, so they have no strategy and
# `section_address` returns None for them (a caller/linter treats None as "not applicable").
_SPAN_STRATEGIES: dict[str, Any] = {
    "page": _IntSpan("pages"),
    "spine": _IntSpan("spines"),
    "block": _IntSpan("block"),
    "sheet": _NameSpan("sheet"),
    # *(3.5)* `el` and `turn` — the two dominant families in the fleet, and both unsupported
    # until a record needed MORE THAN ONE span (§4.3.2.1). While every formed record carried a
    # single whole-record section the omission was invisible: that section omits its envelope
    # by definition, so nothing ever asked for one. Narrowing those sections to span scope, and
    # placing a second span beside them, both require it.
    #
    # *(3.6)* The `el` entry below is the LEGACY (pre-remap) form only: min-max over the
    # retired filtered index, kept for unstamped records. A record stamped with `addressing:`
    # derives through the path algebra instead (`_el_path_envelope` — subtree / sibling range /
    # list, §6.1.1), which a caller selects via `section_address(..., el_paths=True)`. The
    # min-max form is exactly the over-claiming envelope the amendment retires: a child whose
    # stored address is over-wide drags the envelope across content it does not hold.
    "el": _IntSpan("el"),
    "turn": _IntSpan("turn"),
}


def _el_path_envelope(values: list[str]) -> str | list[str] | None:
    """The §6.1.1 envelope over children's `el=` path values, by pure address algebra —
    no artifact access. Claims contained in another claim drop (a subtree is one
    address); one surviving claim IS the envelope; contiguous point-siblings of one
    parent collapse to the sibling-range form; anything else is the ordered list, which
    is what a region crossing subtree boundaries structurally is. Returns None when any
    value fails the path grammar (the caller treats None as not-derivable)."""
    from corpus import functional_uri as furi

    try:
        claims = [furi.parse_el_path(v) for v in values]
    except ValueError:
        return None
    unique: list[Any] = []
    for c in claims:
        if c not in unique:
            unique.append(c)
    tops = [
        c for c in unique
        if not any(o != c and furi.el_path_contains(o, c) for o in unique)
    ]
    tops.sort(key=furi.el_path_sort_key)
    if len(tops) == 1:
        return f"el={furi.format_el_path(tops[0])}"
    if all(t.sibling_range is None for t in tops):
        parents = {t.components[:-1] for t in tops}
        if len(parents) == 1:
            parent = tops[0].components[:-1]
            idxs = sorted(t.components[-1] for t in tops)
            if parent and idxs == list(range(idxs[0], idxs[-1] + 1)):
                stem = ".".join(str(c) for c in parent)
                return f"el={stem}.[{idxs[0]}-{idxs[-1]}]"
    return [f"el={furi.format_el_path(t)}" for t in tops]


def section_address(
    children: list[Segment], *, el_paths: bool = False
) -> str | list[str] | None:
    """Derive a section's address as the envelope of `children`'s addresses, in their own
    discrete-index scheme. Returns None when it can't be derived — no children, a
    heterogeneous mix of address families, or an unrecognized/temporal scheme.

    `el_paths` selects the 3.6 path algebra for the `el` family (§6.1.1); the caller
    reads it off the record's `addressing:` stamp (`records.el_addressing`) — a bare
    integer value means different things under the two grammars, so the record, never
    the value, decides.

    The single source of truth for a section span: `Section.spanning` builds with it and the
    `section-address-span` lint rule re-derives with it to catch drift."""
    families: dict[str, list[str]] = {}
    for seg in children:
        for addr in _iter_addr_strings(seg.address):
            param, value = _leading_param(addr)
            families.setdefault(param, []).append(value)
    if len(families) != 1:
        return None
    ((param, values),) = families.items()
    if param == "el" and el_paths:
        return _el_path_envelope(values)
    strategy = _SPAN_STRATEGIES.get(param)
    if strategy is None:
        return None
    return strategy(values)


# ---------- emit ---------- #


def emit(blocks: list[Block]) -> str:
    """Return a content-zone string built from `blocks` in order.

    A Section emits its header then walks `blk.segments` to emit each child. A
    top-level Segment (sectionless record) emits its header + body directly.

    Adjacent blocks separated by a blank line.
    """
    parts: list[str] = []
    for blk in blocks:
        if isinstance(blk, Section):
            parts.append(_emit_section(blk))
            for child in blk.segments:
                parts.append(_emit_segment(child))
        else:
            parts.append(_emit_segment(blk))
    return "\n".join(parts)


def _emit_section(sec: Section) -> str:
    header = sec.to_header_dict()
    opener = (
        _SECTION_OPENER if sec.form is None else f"{_SECTION_OPENER} {sec.form}"
    )
    if not header:
        # *(3.7)* No fields at all — the bare opener §4.3.2.1 describes, on one line. Since
        # the envelope is derived and 3.5 retired the universal fields, this is what most
        # sections look like: `<!--section document-->`.
        return f"{opener}{_CLOSER}\n"
    header_yaml = yaml.safe_dump(
        header,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    ).rstrip("\n")
    return f"{opener}\n{header_yaml}\n{_CLOSER}\n"


def _emit_segment(seg: Segment) -> str:
    """Render a Segment.

    The atom (or atom/overlay) sits on the opener line; the YAML header below carries
    everything else. Body-empty segments (image/audio/video positioning markers) render
    without a trailing body section.
    """
    header_yaml = yaml.safe_dump(
        seg.to_header_dict(),
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    ).rstrip("\n")
    opener_id = seg.overlay or seg.atom
    body = seg.body.rstrip("\n")
    if body:
        return f"{_OPENER_PREFIX}{opener_id}\n{header_yaml}\n{_CLOSER}\n\n{body}\n"
    return f"{_OPENER_PREFIX}{opener_id}\n{header_yaml}\n{_CLOSER}\n"


# ---------- axis addressing (anchor lookup, e.g. `corpus body --anchor turn=4`) ---------- #

_AXIS_SPAN_RE = re.compile(r"^(\d+)(?:-(\d+))?$")

# Address params `ledger.verify.scoped_text` always treats as `unchecked` — never
# resolved to body text, even when a value happens to be integer-range shaped
# (`time_range=0-30`); an anchor on one of these always falls back to the whole record.
# Mirrored here (not imported — this package stays free of a ledger-ward dependency) so
# `--anchor` never claims to scope a param verify itself would never scope.
_UNCHECKED_AXES = frozenset({"time_range", "frame", "bbox", "path", "region", "rotate"})


def parse_axis_span(value: str) -> tuple[int, int] | None:
    """A bare integer-span value (`4`, or a range `4-8`) → `(lo, hi)`; `None` if `value`
    isn't shaped that way (a temporal/bbox/path value is not an integer-span axis)."""
    m = _AXIS_SPAN_RE.match(value.strip())
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return lo, hi


def address_axis_spans(address: str | list[str] | None) -> list[tuple[str, int, int]]:
    """A segment's `address` → `[(axis, lo, hi)]` for every integer-span param it
    carries. A compound address (`el=5&bbox=0,0,10,10`) registers only the int-span,
    checkable parts. This is the same address grammar `ledger.verify.scoped_text` scopes
    an evidence anchor against — an axis this finds is exactly an axis
    `corpus body --anchor <axis>=<N>` can target."""
    out: list[tuple[str, int, int]] = []
    if address is None:
        return out
    addrs = address if isinstance(address, list) else [address]
    for a in addrs:
        if not isinstance(a, str) or "=" not in a:
            continue
        for part in a.split("&"):
            axis, _, value = part.partition("=")
            axis = axis.strip()
            if axis in _UNCHECKED_AXES:
                continue
            span = parse_axis_span(value)
            if span is not None:
                out.append((axis, *span))
    return out


def leaf_segments(blocks: list[Block]) -> Iterator[Segment]:
    """Every addressable leaf `Segment` in document order: top-level segments, and each
    section's children. A section itself carries no body of its own to anchor into
    (§4.3.2.1) — its span, when it has one, is the envelope of its children under a
    pluralized axis name (`page`→`pages`, ...), distinct from the children's own axis, so
    leaf-only matching never collides with a section-level span."""
    for b in blocks:
        if isinstance(b, Section):
            yield from b.segments
        else:
            yield b


def render_segment(seg: Segment) -> str:
    """Render one segment exactly as `emit` would: its opener, header (address plus
    every attribution field it carries — sender/timestamp on a message, name on a vcard
    field, ...), and body. Used to reprint a single `--anchor`-addressed segment with its
    attribution context intact."""
    return _emit_segment(seg)


# ---------- parse ---------- #


def iter_blocks(body: str) -> list[Block]:
    """Parse `body` (the content zone only) into an ordered list of top-level blocks.

    The content zone is a bare flat run of `Segment`s (the default), or one or more
    `Section`s, or — the mixed-artifact case (§4.3.2.1) — **formless top-level segments
    before the first section opener**, then the section(s): a statement PDF whose page-1
    cover letter rides as bare `page=1` segments, then `<!--section statement
    address: pages=2-6-->` over the statement proper. For a section, its `segments` list is
    populated from the segments that follow its header (until the next section opener or EOF),
    so a segment AFTER a section opener is that section's child (its positional span, §4.3.2.1),
    never a top-level formless sibling — the **before-only** rule (see below).

    Recognized openers:
    - `<!--section [<namespace>/<id>]` — top-level section
    - `<!--segment <atom>` (canonical form) — segment
    - `<!--segment` with `atom:` in header (legacy v0.3 form) — segment
    - `<!--sub-segment <atom>` / `<!--sub-segment` (legacy form) — parses as ordinary
      segment opener

    Rejects:
    - A top-level formless segment AFTER a section opener (the between/after mixed case). The
      spec's positional-span rule (§4.3.2.1: a section's span runs to the next opener or the end
      of the zone) makes such a segment the preceding section's child, not a sibling — so a
      top-level formless segment is admissible only BEFORE the first section (**before-only**;
      the between/after case is genuinely ambiguous in the spec text — §4.3.2.1 line 379 names
      only the before case — and no real record needs it). In practice this reject is a guard:
      a post-section segment is consumed as a child before the top level sees it.
    - A whole-record section (`address` omitted) alongside ANY sibling block. *(3.5: several
      SPAN-scope sections are fine — what cannot coexist with a sibling is a section claiming
      the whole zone, §4.3.2.1.)*
    - Prose between a section's closer and its first child segment opener.
    - `entry:` field on a segment inside a section.
    - Unknown atom.

    NOTE: `body` here MUST be content-zone text only. Metadata-zone blocks
    (artifact / origin / classify / embed) and annotation-zone blocks (issue) are
    extracted by `records.py` before this function sees the slice.
    """
    lines = body.splitlines()
    blocks: list[Block] = []
    seen_section = False  # set once any section opener is parsed (before-only rule)

    i = 0
    while i < len(lines):
        kind = _opener_kind(lines[i])
        if kind is None:
            i += 1
            continue

        if kind == "section":
            seen_section = True
            section, after_header = _parse_section_header(lines, i, line_no=i + 1)
            cursor = after_header
            # Reject prose between section closer and first child opener.
            scan = cursor
            while scan < len(lines):
                if lines[scan].strip() == "":
                    scan += 1
                    continue
                peek = _opener_kind(lines[scan])
                if peek == "section":
                    break  # empty section
                if peek == "segment":
                    cursor = scan
                    break
                raise ValueError(
                    f"section at line {i + 1}: prose found between section "
                    f"closer and first child segment opener at line {scan + 1} "
                    f"(sections have no body region)"
                )
            while cursor < len(lines):
                peek = _opener_kind(lines[cursor])
                if peek == "section":
                    break
                if peek == "segment":
                    child, cursor = _parse_segment_block(lines, cursor, line_no=cursor + 1)
                    # A content segment's `entry:` (an authored leaf label, §4.3.2.2) is valid
                    # inside a form section as well as at top level (relaxed 2026-07-17, the
                    # form-adopt-32 migration): a generic form span wraps an already-labeled
                    # multi-block rendering whole, and the label identifies the child among
                    # its siblings exactly as it did at top level. A structural byte-mark's
                    # `entry:` (the source's own mark text, §4.3.2.3) was always valid here.
                    section.segments.append(child)
                else:
                    cursor += 1
            blocks.append(section)
            i = cursor

        else:  # kind == "segment"
            if seen_section:
                # A top-level formless segment after a section is the between/after mixed case
                # (§4.3.2.1): unsupported — formless segments are admissible only before the
                # first section opener. (Normally unreachable: a post-section segment is
                # consumed as the section's child above.)
                raise ValueError(
                    f"formless segment at line {i + 1} follows a section: a top-level segment "
                    f"is only valid before the first section opener (§4.3.2.1)"
                )
            seg, i = _parse_segment_block(lines, i, line_no=i + 1)
            blocks.append(seg)

    # *(3.7)* The whole-record section's sibling prohibition retires with the spelling it was
    # keyed on. It fired when a section carried no `address`, meaning "this form governs
    # everything here" — a claim two blocks could not both make. A section no longer STORES an
    # address at all, so there is no absence to read: every span's extent is exactly its
    # children's, and two sections can only overlap if their children do, which the address
    # grammar and `segment-address-duplicate` already decide at the segment grain (§12.29).
    #
    # *(3.5 lifted the prohibition for multi-span records; 3.7 removes the last remnant.)*
    blocks = _collapse_adjacent_same_form(blocks)

    for blk in blocks:
        if isinstance(blk, Section) and blk.address is None and blk.segments:
            blk.address = section_address(blk.segments, el_paths=_el_path_children(blk.segments))

    return blocks


def _collapse_adjacent_same_form(blocks: list[Block]) -> list[Block]:
    """Merge adjacent sections that say the same thing (spec §4.3.2.1, 3.7).

    Two neighbouring spans under the SAME form whose declared header fields are equal are one
    span written twice: the form is the only judgment a section makes, the fields are the only
    facts it carries, and position within the merged span still holds the source's order. So
    the grammar declines to represent the split — it parses as one section, and re-emitting
    writes one.

    **Field equality is what makes this safe, and it is why the rule is form-dependent in
    effect without being form-specific in statement.** `form/index` declares nothing, so its
    adjacent spans always merge. `form/statement` declares `account`/`period`; two statement
    spans in one PDF differ there and never merge — which is correct, because those fields are
    what distinguish the two statements. The same holds for a workbook's per-worksheet spans
    and a multi-sheet schematic's per-sheet ones: their declared fields differ, so they stand
    apart. No form id is named here; the forms' own declarations decide.

    Legacy `entry`/`description` (retired, read tolerantly) must also match — an unswept record
    with two differently-labelled spans keeps them rather than silently losing a label."""
    out: list[Block] = []
    for blk in blocks:
        prev = out[-1] if out else None
        if (
            isinstance(blk, Section)
            and isinstance(prev, Section)
            and blk.form is not None
            and prev.form == blk.form
            and prev.extra == blk.extra
            and prev.entry == blk.entry
            and prev.description == blk.description
        ):
            prev.segments.extend(blk.segments)
            prev.address = None  # re-derived below, over the merged children
            continue
        out.append(blk)
    return out


def _el_path_children(children: list[Segment]) -> bool:
    """Whether these children's `el=` addresses are 3.6 PATHS rather than legacy flat indexes.

    `section_address` needs the grammar because a bare integer is valid in both and the two
    envelope spellings differ (`el=[3-5]` vs `el=3-5`). The record's `addressing:` stamp is the
    authority (§6.1.1) and callers holding the post should pass it; a bare `iter_blocks` has
    only the body, so it decides from the values themselves — exactly, not heuristically: a
    legacy flat range (`el=3-7`) is not valid 3.6 grammar and a 3.6 dotted path or sibling
    range is not valid legacy, so either form present settles it. Bare integers alone are the
    one overlap, and paths are the answer there — post-migration every stamped record uses
    them, and the unstamped remainder that would differ is three frozen non-HTML records
    storing `el=` on vcard/ndjson (§12.28's holds)."""
    for seg in children:
        for addr in _iter_addr_strings(seg.address):
            param, value = _leading_param(addr)
            if param != "el":
                continue
            if _LEGACY_FLAT_RANGE_RE.fullmatch(value):
                return False
    return True


_LEGACY_FLAT_RANGE_RE = re.compile(r"\d+-\d+")


def _opener_kind(line: str) -> str | None:
    """Return 'section', 'segment', or None for a given line.

    Embed lines are *not* recognized here — they belong to the metadata zone and are
    extracted by `records.py` before the content-zone slice reaches this function.
    """
    stripped = line.rstrip()
    # *(3.7)* `<!--section-->` and `<!--section index-->` — the one-line BARE OPENER, now the
    # ordinary shape (§4.3.2.1, §12.29) — close on the opener line, so the recognizer admits
    # the closer directly after the keyword as well as after a space-separated form id.
    if (
        stripped == _SECTION_OPENER
        or stripped.startswith(_SECTION_OPENER + " ")
        or stripped == _SECTION_OPENER + _CLOSER
    ):
        return "section"
    if stripped.startswith(_SUB_OPENER_PREFIX) or stripped == _SUB_OPENER:
        return "segment"
    if stripped.startswith(_OPENER_PREFIX) or stripped == _OPENER:
        return "segment"
    return None


def _opener_id(line: str) -> str | None:
    """Extract the opener id from a canonical-form segment opener line, or None for the
    legacy form (where the atom lives in the header).

    The opener id is either a bare atom (`text`, `image`, `audio`, `video`) or an
    atomic-overlay id (`text/data-table`, `image/photo`, etc.). Callers split on the
    first `/` to recover the atom.
    """
    stripped = line.rstrip()
    if stripped.startswith(_SUB_OPENER_PREFIX):
        return stripped.removeprefix(_SUB_OPENER_PREFIX).strip()
    if stripped.startswith(_OPENER_PREFIX):
        return stripped.removeprefix(_OPENER_PREFIX).strip()
    return None


def _parse_section_header(
    lines: list[str], start: int, *, line_no: int
) -> tuple[Section, int]:
    """Parse a `<!--section-->` block's header and return the constructed Section plus
    the index of the line after the header closer."""
    # The form id on a qualified opener (`<!--section conversation-->`, §4.3.2.1). A bare
    # `<!--section-->` (the retired 2.x TOC grouping) has form=None.
    opener_suffix = lines[start].rstrip().removeprefix(_SECTION_OPENER).strip()

    # *(3.7)* The BARE OPENER, closed on its own line: `<!--section index-->`. With the
    # envelope derived (§12.29) and 3.5's universal fields retired, a form that declares
    # nothing has no header at all — which is the ordinary case now, not the exception — and
    # §4.3.2.1 spells that exactly this way. A two-line block with an empty body would read
    # like a field went missing.
    if opener_suffix.endswith(_CLOSER):
        form = opener_suffix.removesuffix(_CLOSER).strip() or None
        return Section(form=form), start + 1

    form = opener_suffix or None

    header_start = start + 1
    j = header_start
    while j < len(lines) and lines[j].rstrip() != _CLOSER:
        j += 1
    if j >= len(lines):
        raise ValueError(f"unterminated section header at line {line_no}")
    header_yaml = "\n".join(lines[header_start:j])
    try:
        header = yaml.safe_load(header_yaml) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"malformed section header at line {line_no}: {e}") from e
    if not isinstance(header, dict):
        raise ValueError(f"section header at line {line_no} is not a mapping: {header!r}")

    # `address` is the span envelope — OMITTED on a whole-record form section (§4.3.2.1),
    # so it is optional (None when absent) rather than required as in 2.x.
    address_raw = header.pop("address", None)
    address: str | list[str] | None
    if address_raw in (None, ""):
        address = None
    else:
        address = _normalize_address(address_raw, what="section", line_no=line_no)
    entry_raw = header.pop("entry", None)
    entry = str(entry_raw).strip() if entry_raw is not None else None
    description_raw = header.pop("description", None)
    description = str(description_raw) if description_raw is not None else None

    return (
        Section(
            address=address,
            entry=entry,
            form=form,
            description=description,
            extra=header,
        ),
        j + 1,
    )


def _parse_segment_block(
    lines: list[str], start: int, *, line_no: int
) -> tuple[Segment, int]:
    """Parse one segment block starting at `lines[start]`.

    Returns the constructed Segment and the index of the line just after this block's
    body (i.e. where the next opener or EOF sits). The block's body extends from after
    the closer up to the next line that is any opener.
    """
    opener_token = _opener_id(lines[start])
    header_start = start + 1
    j = header_start
    while j < len(lines) and lines[j].rstrip() != _CLOSER:
        j += 1
    if j >= len(lines):
        raise ValueError(f"unterminated segment header at line {line_no}")
    header_yaml = "\n".join(lines[header_start:j])
    try:
        header = yaml.safe_load(header_yaml) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"malformed segment header at line {line_no}: {e}") from e
    if not isinstance(header, dict):
        raise ValueError(f"segment header at line {line_no} is not a mapping: {header!r}")

    body_start = j + 1
    k = body_start
    while k < len(lines):
        if _opener_kind(lines[k]) is not None:
            break
        k += 1
    body_lines = lines[body_start:k]
    while body_lines and body_lines[0].strip() == "":
        body_lines.pop(0)
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()
    body_text = "\n".join(body_lines)

    legacy_atom = str(header.pop("atom", "")).strip()
    # Split the opener token into (atom, overlay).
    overlay: str | None = None
    if opener_token is not None and "/" in opener_token:
        atom_from_opener = opener_token.split("/", 1)[0]
        overlay = opener_token
    else:
        atom_from_opener = opener_token or ""
    if atom_from_opener and legacy_atom and atom_from_opener != legacy_atom:
        raise ValueError(
            f"segment at line {line_no}: opener atom {atom_from_opener!r} disagrees "
            f"with header `atom: {legacy_atom}`"
        )
    atom = atom_from_opener or legacy_atom

    # The structural byte-mark (§4.3.2.3) — the fifth segment kind. Not an atom: it takes no
    # overlay and carries `address` + `level` + optional `entry`, no body.
    if atom == _STRUCTURAL:
        if overlay is not None:
            raise ValueError(
                f"segment at line {line_no}: `structural` takes no atom overlay"
            )
        address = _normalize_address(
            header.pop("address", ""), what="segment", line_no=line_no
        )
        level_raw = header.pop("level", 1)
        try:
            level = int(level_raw)
        except (TypeError, ValueError):
            raise ValueError(
                f"structural segment at line {line_no}: `level` must be an integer, "
                f"got {level_raw!r}"
            ) from None
        # *(3.5)* `mark:` is the field; `entry:` is read for back-compat and converts on
        # write. `mark:` wins where a record somehow carries both.
        mark_raw = header.pop("mark", None)
        legacy_raw = header.pop("entry", None)
        if mark_raw is None:
            mark_raw = legacy_raw
        mark = str(mark_raw).strip() if mark_raw is not None else None
        header.pop("mode", None)
        return (
            Segment(
                atom=_STRUCTURAL,
                address=address,
                mark=mark,
                body="",
                extra=header,
                level=level,
            ),
            k,
        )

    if atom not in _VALID_ATOMS:
        raise ValueError(
            f"segment at line {line_no}: atom {atom!r} not one of {sorted(_VALID_ATOMS)}"
        )

    address = _normalize_address(header.pop("address", ""), what="segment", line_no=line_no)
    # v1.0 `perceptual:` (`<algo>:<hex>`) preferred; v0.3 `fingerprint:` (bare hex)
    # accepted on read for back-compat.
    perceptual_raw = header.pop("perceptual", None)
    if perceptual_raw is None:
        perceptual_raw = header.pop("fingerprint", None)
    # §7.6: a perceptual field is scalar OR a list (multi-region segment); preserve the
    # list shape rather than stringifying it.
    if isinstance(perceptual_raw, list):
        perceptual = [str(x).strip() for x in perceptual_raw]
    elif perceptual_raw is not None:
        perceptual = str(perceptual_raw).strip()
    else:
        perceptual = None
    entry_raw = header.pop("entry", None)
    entry = str(entry_raw).strip() if entry_raw is not None else None
    # *(3.5)* `mark:` means "the source said this, verbatim" and is checkable against the
    # artifact. A content segment offers no such guarantee, so the field is refused here
    # rather than tolerated — the point of the rename is that the two are not the same field.
    if "mark" in header:
        raise ValueError(
            f"segment at line {line_no}: `mark:` is the structural byte-mark's verbatim "
            f"source text (§4.3.2.3) and is not valid on a `{atom}` segment"
        )
    description_raw = header.pop("description", None)
    description = str(description_raw) if description_raw is not None else None
    # v0.3 segment headers carried inline `issues:`, `classifications:`, and `mode:`
    # — our spec removes all three. Strip silently for back-compat read; emit writes
    # the canonical shape.
    header.pop("issues", None)
    header.pop("classifications", None)
    header.pop("mode", None)

    return (
        Segment(
            atom=atom,
            address=address,
            perceptual=perceptual,
            entry=entry,
            description=description,
            body=body_text,
            extra=header,
            overlay=overlay,
        ),
        k,
    )


def _normalize_address(
    raw: Any, *, what: str, line_no: int
) -> str | list[str]:
    """Validate + canonicalize an `address:` header value (string or list)."""
    if isinstance(raw, list):
        addrs = [str(x).strip() for x in raw if str(x).strip()]
        if not addrs:
            raise ValueError(f"{what} header at line {line_no} has empty address list")
        return addrs
    if isinstance(raw, str):
        v = raw.strip()
        if not v:
            raise ValueError(f"{what} header at line {line_no} missing required address")
        return v
    raise ValueError(
        f"{what} header at line {line_no} has invalid address type: {type(raw).__name__}"
    )
