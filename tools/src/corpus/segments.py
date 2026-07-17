"""Content-zone block grammar — emit + parse Sections and Segments.

Per spec/corpus.md §4.3, the record body has three zones. This module owns the
**content** zone: sections and segments. The **metadata** zone — including
`<!--embed--><br>` blocks — is owned by `records.py` (reconciliation #1 vs the reference,
which routed embeds through this module).

Content-zone grammar (§4.3.2):

- A `<!--section <form-id>-->` opens a **form span** (spec §4.3.2.1, 3.0): the qualified
  opener carries the record-scope form id (`conversation`, `statement`, `receipt`), exactly
  as a segment opener carries its atom id. The header carries the form overlay's codebook /
  envelope fields (e.g. `participants:`), an optional `address` (the span envelope — OMITTED
  on a whole-record form section), and optional `entry` + `description`. Sections contain
  segments; they have no body of their own. Closer is followed directly by the first child
  segment opener — prose between is a parse error. A **bare** `<!--section-->` (no form id) is
  the 2.x TOC grouping unit — retired in place (§4.3.2.1); it reads tolerantly (form=None,
  contributes no `form/*` classification) so 2.x records round-trip until the grammar sweep.

- A `<!--segment <atom>-->` or `<!--segment <atom>/<overlay-id>-->` opens an atomic
  content block. `atom ∈ {text, image, audio, video}`, on the opener line; an
  atomic-overlay id (e.g. `text/data-table`, `image/photo`) may stand in place of the
  bare atom. Header: `address:` required; optional `perceptual`, `description`,
  `speaker`, `entry` (only when top-level). Only `text`-atom segments may carry a
  non-empty body; image/audio/video segments are body-empty positioning markers whose
  whole-asset descriptions live on the matching embed (§4.3.2.2).

- A `<!--segment structural-->` (spec §4.3.2.3, 3.0) is the fifth segment kind — the
  **byte-mark**: a body-empty mark recording that the source itself declares a structural
  boundary (a heading, an outline entry, a chapter mark, a topic boundary) at an `address`,
  with a `level:` (int; the source's own hierarchy, else 1) and an optional `entry:` (the
  mark's own text, verbatim). It carries no content atom and no body, takes no atom overlay,
  and is excluded from `token_counts.body` (§9.6). Its identity is (`structural`, address),
  stacking beside content segments at the same address per the standard rule; unlike a
  content segment, a structural mark MAY carry `entry:` inside a form section.

A record's content zone is a flat run of segments (the default), one or more sections, or —
the mixed-artifact case (§4.3.2.1) — formless top-level segments BEFORE the first section
opener, then the section(s) (a statement PDF's page-1 cover letter as bare segments, then a
`statement` section over pages 2-6). A segment after a section opener is that section's child
(the positional span), never a top-level sibling — so top-level mixing is admissible only in
the before-only direction. A whole-record section (no `address`) admits no sibling of either
kind. Nesting depth = 1: sections contain segments; segments contain nothing; sections don't nest.
"""

from __future__ import annotations

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

    `entry` is a short TOC label, only valid on top-level segments (sectionless
    records). In-section segments don't carry it (the section is the TOC unit).

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

        A structural byte-mark emits `address`, then `level`, then `entry` (§4.3.2.3):
        no body, no atom overlay, no perceptual/description."""
        out: dict[str, Any] = {"address": self.address}
        if self.level is not None:
            out["level"] = self.level
        if self.perceptual is not None:
            out["perceptual"] = self.perceptual
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
        out: dict[str, Any] = {}
        if self.address is not None:
            out["address"] = self.address
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
    ) -> Section:
        """Build a Section whose `address` is DERIVED as the envelope (min-max span)
        of `segments`' own addresses, in their discrete-index scheme (`page=`→`pages=`,
        `spine=`→`spines=`, `block=`, `sheet=`). The single place a section span is computed:
        drafters build sections this way instead of hand-formatting the range, and the
        `section-address-span` lint rule re-derives the same value to guard drift.

        `segments` must be non-empty and share one registered scheme. Raises ValueError when
        the span can't be derived (empty, heterogeneous, or an unrecognized/temporal scheme)
        — temporal (`time_range=`) sections are structural intervals, not content envelopes,
        and are built directly, not via this factory."""
        address = section_address(segments)
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
}


def section_address(children: list[Segment]) -> str | list[str] | None:
    """Derive a section's address as the envelope of `children`'s addresses, in their own
    discrete-index scheme. Returns None when it can't be derived — no children, a
    heterogeneous mix of address families, or an unrecognized/temporal scheme.

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
        # A whole-record form section may carry no header fields at all (no envelope,
        # no codebook): emit an empty header block rather than a stray blank line.
        return f"{opener}\n{_CLOSER}\n"
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
    - A whole-record section (`address` omitted, one section over the entire zone) with ANY
      sibling block, of either kind (§4.3.2.2: it admits no siblings).
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

    # A whole-record section (address omitted) spans the entire content zone, so it admits no
    # sibling of either kind — no formless segments before it, no other section (§4.3.2.2).
    if any(isinstance(b, Section) and b.address is None for b in blocks) and len(blocks) > 1:
        raise ValueError(
            "a whole-record section (no `address`) admits no sibling blocks (§4.3.2.2); "
            f"found {len(blocks)} top-level blocks"
        )

    return blocks


def _opener_kind(line: str) -> str | None:
    """Return 'section', 'segment', or None for a given line.

    Embed lines are *not* recognized here — they belong to the metadata zone and are
    extracted by `records.py` before the content-zone slice reaches this function.
    """
    stripped = line.rstrip()
    if stripped == _SECTION_OPENER or stripped.startswith(_SECTION_OPENER + " "):
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
        entry_raw = header.pop("entry", None)
        entry = str(entry_raw).strip() if entry_raw is not None else None
        header.pop("mode", None)
        return (
            Segment(
                atom=_STRUCTURAL,
                address=address,
                entry=entry,
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
