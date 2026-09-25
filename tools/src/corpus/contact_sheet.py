"""The contact sheet — a labelled grid over a container's image and video members (spec
§12.9.3, v45; video tiles v46; codex-steven R-0037/R-0038).

An **instrument** (§6.2 op classes): a tool's view ABOUT a container, for an investigator
deciding which frames to open — never an anchor, never stored, never a surface a claim cites.
One sheet replaces a resolve per frame when the question is "which of these hundred photos
show the cat", and every tile names the exact member address the follow-up resolve (or the
evidence anchor) uses.

Generic by construction: the sheet reads the container's `members` derivation (§6.2), so it
works on any record whose members include images — a photo-library zip, a tar, a mail
message's attachments — and its selection predicates run over the member DESCRIPTORS, which
for a container declaring a `sidecar:` (§7.2) carry the frame's lifted fields. Nothing here
knows what any field means.

Each tile is the frame's own rendering, `corpus://<container>?<address>&auto_orient&fit=
<T>x<T>` — resolved (and cached) through the ordinary resolver, so a tile is exactly the
frame an investigator gets on opening it, upright. The sheet itself is cached under the
resolver cache, keyed on its full selection + layout + `ENGINE_VERSION`, with a JSON legend
beside it (tile number → member address → label values).

A video member is tiled by ONE still — `corpus://<container>?<address>&frame=<T>&auto_orient&
fit=…`, the video kind's own frame grab (v46) — marked as video on the sheet and in the
legend, which records the instant shown. A video member that another member's descriptor
names by address (a sibling reference — a live photo's motion twin, lifted from the still's
sidecar) is that member's companion, not a frame of its own: it is passed over and disclosed
as `companion`, so the still stands for the pair. The rule reads addresses only, never a
field's meaning.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from corpus import functional_uri as furi
from corpus import paths

ENGINE_VERSION = "contact-sheet@2"

# Layout defaults: 5 x 4 tiles of 208 px with a two-line label strip lands a sheet inside the
# `fit=llm` budget (transforms.image LLM_MAX_EDGE / LLM_MAX_PIXELS) without a final downscale,
# so the labels stay legible. Implementation-defined, like the `fit=` presets (§6.2).
DEFAULT_COLUMNS = 5
DEFAULT_ROWS = 4
DEFAULT_TILE = 208
# The instant a video tile shows, in seconds — past a clip's opening black/fade, and inside
# the ~3 s motion of a live photo. A clip too short for it falls back to its first frame.
DEFAULT_VIDEO_AT = "1"
_GAP = 8
_BG = (255, 255, 255)
_CELL_BG = (236, 236, 236)
_INK = (20, 20, 20)
_MUTED = (90, 90, 90)
_OPS = ("!~", "!=", ">=", "<=", "~", "=")


class SheetError(ValueError):
    """A sheet that cannot be built as asked (no image members, a page past the end, a
    malformed predicate) — reported to the caller, never a partial sheet."""


# ---------- selection ---------- #


@dataclass(frozen=True)
class Predicate:
    field: str
    op: str
    value: str

    def __str__(self) -> str:
        return f"{self.field}{self.op}{self.value}"


def parse_where(expr: str) -> Predicate:
    """`FIELD<op>VALUE` with op one of `~` (contains; any item of a list), `!~`, `=` (equals;
    any item of a list), `!=`, `>=`, `<=` (datetime, then number, then text comparison)."""
    for op in _OPS:
        name, sep, value = expr.partition(op)
        if sep and name.strip() and not any(o in name for o in ("!", ">", "<", "~", "=")):
            return Predicate(field=name.strip(), op=op, value=value.strip())
    raise SheetError(
        f"--where {expr!r}: expected FIELD<op>VALUE with op one of {', '.join(_OPS)} "
        f"(e.g. osx_persons~Erasmas, osx_date_original>=2024-12-24)"
    )


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A date bound compares against the value's own face (its local wall time, in the offset
    # it was recorded in) — "taken on 2024-12-24" means the photo's date, not UTC's.
    return dt.replace(tzinfo=None)


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _ordered(actual: Any, bound: str, op: str) -> bool:
    a_dt, b_dt = _as_datetime(actual), _as_datetime(bound)
    if a_dt is not None and b_dt is not None:
        a, b = a_dt, b_dt
    else:
        a_n, b_n = _as_number(actual), _as_number(bound)
        if a_n is not None and b_n is not None:
            a, b = a_n, b_n  # type: ignore[assignment]
        else:
            a, b = str(actual), bound  # type: ignore[assignment]
    return a >= b if op == ">=" else a <= b  # type: ignore[operator]


def matches(member: dict[str, Any], pred: Predicate) -> bool:
    actual = member.get(pred.field)
    items = actual if isinstance(actual, list) else ([] if actual is None else [actual])
    needle = pred.value.casefold()
    if pred.op == "~":
        return any(needle in str(i).casefold() for i in items)
    if pred.op == "!~":
        return not any(needle in str(i).casefold() for i in items)
    if pred.op == "=":
        return any(str(i) == pred.value for i in items)
    if pred.op == "!=":
        return not any(str(i) == pred.value for i in items)
    return any(_ordered(i, pred.value, pred.op) for i in items)


def _member_name(address: str) -> str:
    _key, _, value = address.partition("=")
    return value


def is_video(member: dict[str, Any]) -> bool:
    return str(member.get("media_type") or "").startswith("video/")


def _referenced_addresses(members: Sequence[dict[str, Any]]) -> set[str]:
    """Every member address some OTHER member's descriptor names as a field value (a sibling
    reference, §7.2) — read structurally, whatever the field is called."""
    addresses = {str(m.get("address") or "") for m in members}
    named: set[str] = set()
    for m in members:
        own = m.get("address")
        for k, v in m.items():
            if k == "address":
                continue
            for item in v if isinstance(v, list) else [v]:
                if isinstance(item, str) and item != own and item in addresses:
                    named.add(item)
    return named


def select(
    members: Iterable[dict[str, Any]],
    *,
    globs: Sequence[str] = (),
    where: Sequence[Predicate] = (),
    sort: str | None = None,
    video: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The image and video members a sheet shows, in order, plus the counts of what it
    passed over by family (`companion` — a video another member references; `video` when
    `video=False`; `other`) — a sheet discloses what it is not showing."""
    members = list(members)
    companions = _referenced_addresses(members)
    chosen: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for m in members:
        mt = str(m.get("media_type") or "")
        family = None
        if mt.startswith("video/"):
            if str(m.get("address") or "") in companions:
                family = "companion"
            elif not video:
                family = "video"
        elif not mt.startswith("image/"):
            family = "other"
        if family:
            skipped[family] = skipped.get(family, 0) + 1
            continue
        name = _member_name(str(m.get("address") or ""))
        if globs and not any(fnmatch.fnmatchcase(name, g) for g in globs):
            continue
        if all(matches(m, p) for p in where):
            chosen.append(m)
    if sort:
        present = [m for m in chosen if m.get(sort) not in (None, "", [])]
        absent = [m for m in chosen if m.get(sort) in (None, "", [])]

        def key(m: dict[str, Any]) -> tuple[int, Any]:
            v = m.get(sort)
            v = v[0] if isinstance(v, list) else v
            dt = _as_datetime(v)
            if dt is not None:
                return (0, dt.isoformat())
            n = _as_number(v)
            return (1, f"{n:020.6f}") if n is not None else (2, str(v))

        chosen = sorted(present, key=key) + absent
    return chosen, skipped


# ---------- the sheet ---------- #


@dataclass
class Sheet:
    path: Path
    legend: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


def _label_font(size: int):
    from corpus.transforms.image import _label_font as font

    return font(size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _play_badge(draw: ImageDraw.ImageDraw, x0: int, y0: int, tile: int) -> None:
    """A play triangle in the tile's corner — this tile is one still of a video."""
    r = max(8, tile // 9)
    cx, cy = x0 + r + 4, y0 + r + 4
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0), outline=(255, 255, 255))
    h = r * 0.55
    tri = [(cx - h * 0.6, cy - h), (cx - h * 0.6, cy + h), (cx + h, cy)]
    draw.polygon(tri, fill=(255, 255, 255))


def _label_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def video_instant(value: str) -> str:
    """The sheet's video instant, validated with the video kind's own `frame=` parser and
    spelled in canonical seconds (`00:01`, `1.0`, `1` → `1`), so one instant is one cache
    key and one legend value. A bad instant refuses the sheet — it never silently becomes
    some other frame."""
    from corpus.transforms.video import _parse_timecode_to_seconds

    try:
        seconds = _parse_timecode_to_seconds(str(value).strip())
    except ValueError as exc:
        raise SheetError(f"--video-at: {exc}") from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise SheetError(f"--video-at must be a finite, non-negative instant, got {value!r}")
    return f"{seconds:.3f}".rstrip("0").rstrip(".")


def _tile_uri(container_id: str, address: str, tile: int, at: str | None = None) -> str:
    key, _, value = address.partition("=")
    params: tuple[tuple[str, str | None], ...] = (
        (key, value),
        *((("frame", at),) if at is not None else ()),
        ("auto_orient", None),
        ("fit", f"{tile}x{tile}"),
    )
    return furi.canonical(furi.ParsedURI(hash=container_id, params=params))


def build(
    corpus_root: Path,
    container_id: str,
    *,
    globs: Sequence[str] = (),
    where: Sequence[Predicate] = (),
    sort: str | None = None,
    labels: Sequence[str] = (),
    page: int = 1,
    columns: int = DEFAULT_COLUMNS,
    rows: int = DEFAULT_ROWS,
    tile: int = DEFAULT_TILE,
    video: bool = True,
    video_at: str = DEFAULT_VIDEO_AT,
    fit_llm: bool = True,
    jobs: int | None = None,
    regenerate: bool = False,
) -> Sheet:
    """Build (or fetch from cache) one page of a container's contact sheet."""
    from corpus import resolver
    from corpus.transforms.video import FramePastEnd

    if columns < 1 or rows < 1 or tile < 32:
        raise SheetError("columns and rows must be >= 1 and the tile >= 32 px")
    if page < 1:
        raise SheetError(f"--page must be >= 1, got {page}")
    instant = video_instant(video_at) if video else None

    selection = {
        "container": container_id,
        "glob": list(globs),
        "where": [str(p) for p in where],
        "sort": sort,
        "labels": list(labels),
        "columns": columns,
        "rows": rows,
        "tile": tile,
        "video": instant if instant is not None else False,
        "fit": "llm" if fit_llm else "full",
        "page": page,
    }
    key = json.dumps({"engine": ENGINE_VERSION, **selection}, sort_keys=True)
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=32).hexdigest()
    out = furi.cache_path(corpus_root, digest, "png")
    legend_path = furi.cache_sidecar_path(out)
    if out.is_file() and legend_path.is_file() and not regenerate:
        return Sheet(out.resolve(), json.loads(legend_path.read_text("utf-8")), cached=True)

    members_path = resolver.resolve(f"corpus://{container_id}?members", corpus_root)
    payload = json.loads(members_path.read_text("utf-8"))
    chosen, skipped = select(
        payload.get("members") or [], globs=globs, where=where, sort=sort, video=video
    )
    per = columns * rows
    total = len(chosen)
    if total == 0:
        raise SheetError(
            f"no image or video member of corpus://{container_id[:12]}… matches the "
            f"selection ({sum(skipped.values())} other member(s) passed over)"
        )
    pages = math.ceil(total / per)
    if page > pages:
        raise SheetError(f"--page {page} is past the end: {total} frame(s) make {pages} sheet(s)")
    shown = chosen[(page - 1) * per : page * per]

    def render(m: dict[str, Any]) -> tuple[Image.Image | None, str | None, str | None]:
        # a video tries the sheet's instant, then — only when that instant is past its
        # end (a clip shorter than it) — its first frame
        instants: tuple[str | None, ...] = (
            ((instant, "0") if instant != "0" else ("0",)) if is_video(m) else (None,)
        )
        error = None
        for t in instants:
            uri = _tile_uri(container_id, str(m["address"]), tile, t)
            try:
                with Image.open(resolver.resolve(uri, corpus_root)) as im:
                    im.load()
                    return im.convert("RGB"), None, t
            except FramePastEnd as exc:
                error = f"{type(exc).__name__}: {exc}"
            except Exception as exc:  # one unreadable frame: a marked tile, never a lost sheet
                return None, f"{type(exc).__name__}: {exc}", None
        return None, error, None

    workers = jobs or min(8, os.cpu_count() or 1)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rendered = list(pool.map(render, shown))

    font_size = max(11, tile // 15)
    font = _label_font(font_size)
    line_h = font_size + 4
    strip = line_h * (1 + len(labels)) + 6
    cell_w, cell_h = tile, tile + strip
    used_rows = math.ceil(len(shown) / columns)
    width = columns * cell_w + (columns + 1) * _GAP
    height = used_rows * cell_h + (used_rows + 1) * _GAP
    sheet = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(sheet)

    tiles: list[dict[str, Any]] = []
    for i, (m, (im, error, at)) in enumerate(zip(shown, rendered, strict=True)):
        n = (page - 1) * per + i + 1
        col, row = i % columns, i // columns
        x0 = _GAP + col * (cell_w + _GAP)
        y0 = _GAP + row * (cell_h + _GAP)
        draw.rectangle((x0, y0, x0 + tile - 1, y0 + tile - 1), fill=_CELL_BG)
        if im is not None:
            sheet.paste(im, (x0 + (tile - im.width) // 2, y0 + (tile - im.height) // 2))
        else:
            draw.text((x0 + 6, y0 + tile // 2 - line_h), "unreadable", fill=_MUTED, font=font)
        if is_video(m):
            _play_badge(draw, x0, y0, tile)
        name = _member_name(str(m["address"]))
        ty = y0 + tile + 3
        draw.text((x0, ty), _fit_text(draw, f"{n}  {name}", font, tile), fill=_INK, font=font)
        values: dict[str, str] = {}
        for j, lab in enumerate(labels):
            v = _label_value(m.get(lab))
            values[lab] = v
            draw.text(
                (x0, ty + line_h * (j + 1)),
                _fit_text(draw, v or "-", font, tile),
                fill=_MUTED,
                font=font,
            )
        entry: dict[str, Any] = {"n": n, "address": m["address"], "labels": values}
        if is_video(m):
            entry["video"] = True
            if at is not None:
                entry["frame"] = at  # the instant shown; open more of it with frame=<secs>
        if error:
            entry["error"] = error
        tiles.append(entry)

    if fit_llm:
        from corpus.transforms.image import LLM_MAX_EDGE, LLM_MAX_PIXELS

        scale = min(
            1.0, LLM_MAX_EDGE / max(width, height), (LLM_MAX_PIXELS / (width * height)) ** 0.5
        )
        if scale < 1.0:
            sheet = sheet.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS
            )

    legend: dict[str, Any] = {
        "engine": ENGINE_VERSION,
        "class": "instrument",
        "selection": selection,
        "page": page,
        "pages": pages,
        "selected": total,
        "skipped": skipped,
        "size": list(sheet.size),
        "tiles": tiles,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.tmp.{os.getpid()}")
    try:
        sheet.save(tmp, format="PNG")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    legend_path.write_text(json.dumps(legend, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return Sheet(out.resolve(), legend)


def resolve_container(corpus_root: Path, target: str) -> str:
    """A record id from a hex prefix, a record path, or a `corpus://<id>` URI."""
    if target.startswith(f"{furi.SCHEME}://"):
        parsed = furi.parse(target)
        if parsed.params:
            raise SheetError(
                "give the container itself (corpus://<id>); narrow with --glob/--where"
            )
        target = parsed.hash
    record_id, _record_file = paths.resolve_record(corpus_root, target)
    return record_id
