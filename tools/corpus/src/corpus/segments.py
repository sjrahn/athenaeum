"""Content-zone block grammar — emit + parse Sections and Segments.

Per spec-corpus.md §4.3, the record body has three zones. This module owns the
**content** zone: sections and segments. The **metadata** zone — including
`<!--embed--><br>` blocks — is owned by `records.py` (reconciliation #1 vs the reference,
which routed embeds through this module).

Content-zone grammar (§4.3.2):

- A `<!--section [<namespace>/<id>]-->` opens a structural grouping. The header carries
  `address` (scoped to the media's axis — `time_range=` for temporal, `page=` for PDF,
  `sheet=` for xlsx, `turn=` for sessions), and optional `entry` (the TOC label) +
  `description`. Sections contain segments; they have no body of their own. Closer is
  followed directly by the first child segment opener — prose between is a parse error.

- A `<!--segment <atom>-->` or `<!--segment <atom>/<overlay-id>-->` opens an atomic
  content block. `atom ∈ {text, image, audio, video}`, on the opener line; an
  atomic-overlay id (e.g. `text/data-table`, `image/photo`) may stand in place of the
  bare atom. Header: `address:` required; optional `perceptual`, `description`,
  `speaker`, `entry` (only when top-level). Only `text`-atom segments may carry a
  non-empty body; image/audio/video segments are body-empty positioning markers whose
  whole-asset descriptions live on the matching embed (§4.3.2.2).

A record's content zone is homogeneous at the top level: all sections OR all segments.
Nesting depth = 1: sections contain segments; segments contain nothing; sections don't
nest.
"""

from __future__ import annotations

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
    perceptual: str | None = None
    entry: str | None = None
    description: str | None = None
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    # The atomic-overlay id on the opener line, when more specific than the bare atom —
    # e.g. "text/data-table", "image/photo". On disk: `<atom>/<id>`; bundled schema
    # filename flattens to `schema/atom/<atom>/<atom>_<id>.yaml`.
    overlay: str | None = None

    @property
    def fingerprint(self) -> str | None:
        """Back-compat alias for callers reading the v0.3 field name."""
        return self.perceptual

    def to_header_dict(self) -> dict[str, Any]:
        """Return the dict that would be YAML-dumped between the header comment
        delimiters. `atom` (and any atomic overlay) sits on the opener line itself."""
        out: dict[str, Any] = {"address": self.address}
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
    """Structural grouping primitive — universal TOC unit (spec §4.3.2.1).

    A section groups segments under an axis-scoped address and an optional TOC `entry`.
    Used wherever a media has natural section boundaries: video speaker runs, PDF
    outline entries, HTML h1 headings, xlsx sheets, claude session user turns.

    A section has no atom and no body — it's purely structural. Its closer is followed
    directly by the first child segment opener.

    `classification` carries an optional composite id on the opener (e.g.
    `<!--section <namespace>/<id>-->`); bare `<!--section-->` has classification=None.

    `description` is normalizer-written prose used when the section's address is an
    artifact-self-slice with no matching embed (spec §4.3.1.4 carve-out).
    """

    address: str | list[str]
    entry: str | None = None
    classification: str | None = None
    description: str | None = None
    segments: list[Segment] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_header_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"address": self.address}
        if self.entry is not None:
            out["entry"] = self.entry
        if self.description is not None:
            out["description"] = self.description
        out.update(self.extra)
        return out


type Block = Section | Segment


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
    header_yaml = yaml.safe_dump(
        sec.to_header_dict(),
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    ).rstrip("\n")
    opener = (
        _SECTION_OPENER
        if sec.classification is None
        else f"{_SECTION_OPENER} {sec.classification}"
    )
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

    A record's content zone is homogeneous at the top: all `Section`s or all
    `Segment`s. Mixed top-level raises `ValueError`. For a section-shaped record,
    each section's `segments` list is populated from the segments that follow its
    header (until the next section opener or EOF).

    Recognized openers:
    - `<!--section [<namespace>/<id>]` — top-level section
    - `<!--segment <atom>` (canonical form) — segment
    - `<!--segment` with `atom:` in header (legacy v0.3 form) — segment
    - `<!--sub-segment <atom>` / `<!--sub-segment` (legacy form) — parses as ordinary
      segment opener

    Rejects:
    - Mixed top-level (sections + segments at the top).
    - Prose between a section's closer and its first child segment opener.
    - `entry:` field on a segment inside a section.
    - Unknown atom.

    NOTE: `body` here MUST be content-zone text only. Metadata-zone blocks
    (artifact / origin / classify / embed) and annotation-zone blocks (issue) are
    extracted by `records.py` before this function sees the slice.
    """
    lines = body.splitlines()
    blocks: list[Block] = []
    top_kind: str | None = None  # "section" or "segment", set on first block

    i = 0
    while i < len(lines):
        kind = _opener_kind(lines[i])
        if kind is None:
            i += 1
            continue

        if kind == "section":
            if top_kind is None:
                top_kind = "section"
            elif top_kind != "section":
                raise ValueError(
                    f"record top-level is heterogeneous at line {i + 1}: "
                    f"sections and segments cannot mix"
                )
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
                    if child.entry is not None:
                        raise ValueError(
                            f"segment inside section at line {cursor}: `entry:` is "
                            f"only valid on top-level segments"
                        )
                    section.segments.append(child)
                else:
                    cursor += 1
            blocks.append(section)
            i = cursor

        else:  # kind == "segment"
            if top_kind is None:
                top_kind = "segment"
            elif top_kind != "segment":
                raise ValueError(
                    f"record top-level is heterogeneous at line {i + 1}: "
                    f"sections and segments cannot mix"
                )
            seg, i = _parse_segment_block(lines, i, line_no=i + 1)
            blocks.append(seg)

    return blocks


# Deprecated alias kept for any caller that still uses the v0.3 name.
def iter_segments(body: str) -> list[Block]:
    """Deprecated alias for `iter_blocks`."""
    return iter_blocks(body)


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
    # Optional composite id on the opener: `<!--section <ns>/<id>`. Bare carries None.
    opener_suffix = lines[start].rstrip().removeprefix(_SECTION_OPENER).strip()
    classification = opener_suffix or None

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

    address = _normalize_address(header.pop("address", ""), what="section", line_no=line_no)
    entry_raw = header.pop("entry", None)
    entry = str(entry_raw).strip() if entry_raw is not None else None
    description_raw = header.pop("description", None)
    description = str(description_raw) if description_raw is not None else None

    return (
        Section(
            address=address,
            entry=entry,
            classification=classification,
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
    perceptual = str(perceptual_raw).strip() if perceptual_raw is not None else None
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
