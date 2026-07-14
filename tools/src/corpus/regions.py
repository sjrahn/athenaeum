"""Crop-region save — persist user-drawn bbox regions into a record's content zone.

This is the library behind `POST /v1/{corpus}/records/{id}/regions` (the crop editor's
save). It is an *edit*, not a re-derivation: it loads the record, replaces its
bbox-addressed segments with the posted set (preserving every non-bbox segment, every
section, and the whole metadata zone), and re-emits through the canonical construction
ops so the grammar is validated before any write.

Each drawn region becomes a **body-empty, bbox-addressed segment** (spec §4.3.2.2 marker
case); the bytes materialize on demand via the resolver self-slice (spec §4.3.1.4 — a
`bbox` into the record's own single-image/PDF artifact needs no embed). The save path
goes `records.load` → rebuild content blocks → `recordbuild.begin_from_post` /
`add_blocks` / `finish` → `records.dumps` → atomic write. It never touches
`recordbuild.write_workdir`'s `_CORE` serialization, so the frontmatter `title` and the
rest of the metadata zone are preserved untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from corpus import paths, recordbuild, records, schemas, segments, touches

_VALID_ATOMS = frozenset({"text", "image", "audio", "video"})


class RegionSaveError(ValueError):
    """A region payload that can't be persisted (bad box, unknown overlay, a region whose
    page has no containing section, or a rebuilt record that fails grammar validation).
    The API maps this to a 400."""


# ---------- address / box formatting ---------- #


def _fmt_coord(c: float) -> str:
    """Format a bbox coordinate the way the cropper does (3-dp, no trailing zeros) so the
    written address is stable/diffable and matches `boxAddr` in rw-cropper.ts."""
    v = round(float(c), 3)
    if v == int(v):
        return str(int(v))
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _validate_box(box: Any) -> tuple[float, float, float, float]:
    if not (isinstance(box, (list, tuple)) and len(box) == 4):
        raise RegionSaveError("box must be [x, y, w, h]")
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError) as exc:
        raise RegionSaveError("box coordinates must be numbers") from exc
    eps = 1e-6
    for v in (x, y, w, h):
        if v < -eps or v > 1 + eps:
            raise RegionSaveError("box coordinates must lie in [0, 1]")
    if w <= 0 or h <= 0:
        raise RegionSaveError("box width and height must be > 0")
    if x + w > 1 + eps or y + h > 1 + eps:
        raise RegionSaveError("box must stay within the unit square (x+w<=1, y+h<=1)")
    return x, y, w, h


def region_address(box: Any, page: int | None, *, paged: bool) -> str:
    """Canonical segment address for a drawn region: `page=N&bbox=x,y,w,h` (paged) else
    `bbox=x,y,w,h`. Matches the cropper's `boxAddr`."""
    x, y, w, h = _validate_box(box)
    coords = ",".join(_fmt_coord(c) for c in (x, y, w, h))
    if paged:
        if page is None or int(page) < 1:
            raise RegionSaveError("a paged artifact requires page >= 1 for each region")
        return f"page={int(page)}&bbox={coords}"
    return f"bbox={coords}"


# ---------- overlay normalization ---------- #


def _normalize_overlay(corpus_root: Path, atom: str, overlay: str) -> str | None:
    """Return the canonical `<atom>/<id>` overlay for a segment, or None for a bare atom.

    Accepts either a bare suffix (`data-table`, the cropper's form) or a full slash id
    (`text/data-table`). Validates that the overlay actually resolves to a bundled/local
    atomic-overlay schema — this rejects the cropper's historical `caption` typo (the
    bundled overlay is `captions`)."""
    overlay = (overlay or "").strip()
    if not overlay:
        return None
    suffix = overlay.split("/", 1)[1] if "/" in overlay else overlay
    if schemas.load_atomic_overlay(corpus_root, atom, suffix) is None:
        raise RegionSaveError(
            f"unknown atomic overlay '{atom}/{suffix}' (no schema atom/{atom}/{atom}_{suffix}.yaml)"
        )
    return f"{atom}/{suffix}"


# ---------- bbox / section helpers ---------- #


def _addr_strings(address: Any) -> list[str]:
    if isinstance(address, list):
        return [a for a in address if isinstance(a, str)]
    return [address] if isinstance(address, str) else []


def _is_bbox_segment(seg: segments.Segment) -> bool:
    return any("bbox=" in a for a in _addr_strings(seg.address))


def _page_range(addr: str) -> tuple[int, int] | None:
    """Parse a section address's leading `pages=lo-hi` / `pages=N` (or `page=N`) into an
    inclusive (lo, hi). Sub-selectors after `&` are ignored; non-page schemes return None."""
    head = addr.split("&", 1)[0]
    param, _, value = head.partition("=")
    if param.strip() not in ("page", "pages"):
        return None
    parts = value.strip().split("-")
    try:
        lo, hi = int(parts[0]), int(parts[-1])
    except ValueError:
        return None
    return (lo, hi) if lo <= hi else (hi, lo)


def _section_for_page(sections: list[segments.Section], page: int) -> segments.Section | None:
    for sec in sections:
        for a in _addr_strings(sec.address):
            rng = _page_range(a)
            if rng and rng[0] <= page <= rng[1]:
                return sec
    return None


def _count_segments(blocks: list[Any]) -> int:
    total = 0
    for blk in blocks:
        if isinstance(blk, segments.Section):
            total += len(blk.segments)
        else:
            total += 1
    return total


def _merge_bbox(
    existing: list[Any], new_segments: list[tuple[int | None, segments.Segment]]
) -> list[Any]:
    """Replace bbox-addressed segments with `new_segments`, preserving everything else.

    Handles the mixed-artifact record (§4.3.2.1): formless top-level segments (a statement's
    page-1 cover letter) coexisting with sections (the statement proper). Existing non-bbox
    top-level segments are PRESERVED — never dropped. Each new region lands in the section whose
    page-envelope contains its page; a region on a **formless page** (no containing section — the
    cover-letter case) rides at the top level, which is not an error. The reassembly keeps the
    before-only order (formless top-level segments precede the sections, §4.3.2.1); a whole-record
    section that thereby gains a sibling is caught by `finish`'s grammar re-parse in the caller."""
    sections = [b for b in existing if isinstance(b, segments.Section)]
    top_level = [
        b for b in existing if isinstance(b, segments.Segment) and not _is_bbox_segment(b)
    ]
    for sec in sections:
        sec.segments = [s for s in sec.segments if not _is_bbox_segment(s)]

    new_top: list[segments.Segment] = []
    for page, seg in new_segments:
        sec = _section_for_page(sections, page) if page is not None else None
        if sec is not None:
            seg.entry = None  # in-section segments can't carry a TOC entry
            sec.segments.append(seg)
        else:
            new_top.append(seg)  # a region on a formless page → top-level (not an error)

    return [*top_level, *new_top, *sections]


# ---------- the save entry point ---------- #


def save_regions(
    corpus_root: Path, record_id: str, regions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Persist `regions` (each `{page?, box:[x,y,w,h], atom, overlay?, entry?}`) into the
    record's content zone and return a summary dict. Raises `RegionSaveError` on invalid
    input or a record that fails grammar validation — nothing is written in that case."""
    path = paths.record_path(corpus_root, record_id)
    if not path.is_file():
        raise FileNotFoundError(f"record {record_id} not found")
    post = records.load(path)

    mime = records.media_type_for(post)
    afields = (records.artifact_block(post) or {}).get("fields") or {}
    page_count = afields.get("page_count") or afields.get("pages")
    paged = (not mime.startswith("image/")) and bool(page_count)

    new_segments: list[tuple[int | None, segments.Segment]] = []
    addresses: list[str] = []
    for r in regions:
        atom = r.get("atom")
        if atom not in _VALID_ATOMS:
            raise RegionSaveError(f"atom must be one of {sorted(_VALID_ATOMS)}, got {atom!r}")
        overlay = _normalize_overlay(corpus_root, atom, r.get("overlay") or "")
        page = r.get("page")
        addr = region_address(r.get("box"), page if paged else None, paged=paged)
        addresses.append(addr)
        entry = (r.get("entry") or "").strip() or None
        new_segments.append(
            (int(page) if (paged and page is not None) else None,
             segments.Segment(atom=atom, address=addr, overlay=overlay, entry=entry))
        )

    existing = segments.iter_blocks(post.content or "")
    merged = _merge_bbox(existing, new_segments)

    build = recordbuild.begin_from_post(post, corpus_root)
    recordbuild.add_blocks(build, merged)
    try:
        recordbuild.finish(build)
    except ValueError as exc:  # grammar / homogeneity failures from the construction path
        raise RegionSaveError(str(exc)) from exc

    touches.record_touch(post, touches.script_identifier("regions"))
    paths.atomic_write_text(path, records.dumps(post))

    return {
        "record_id": record_id,
        "segment_count": _count_segments(merged),
        "bbox_segment_count": len(new_segments),
        "addresses": addresses,
        "status": post.metadata.get("status"),
        "touch": touches.touch_list(post),
    }
