"""Render an artifact for an agent's eyes — outline region(s) on the full image, right
its orientation, boost faint contrast, and fit the result to a vision-model's budget.

The inspection surface for the cropping / normalization loop: an agent proposes a bbox,
previews where it lands *in context* on the full page, adjusts, then commits the segment
address. Builds a `corpus://<id>?[page=N&][dpi=D&][auto_orient&][rotate=R&][autocontrast&]
mark=...&fit=llm` URI and resolves it (spec §6.2). Read-only — never writes the record.

`--from-segments` flips it around: instead of ad-hoc coordinates, it draws the record's
*already-committed* bbox segments on the image, so the normalizer can VERIFY that every
written address frames the span it meant (the check nothing else surfaces).

Fits to the `llm` preset by default because this render IS going into a model's context;
pass --full to render at native resolution.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from corpus import functional_uri as furi
from corpus import paths, records, segments
from corpus._cli._common import add_corpus_root_arg, attach_transform_grammar, resolved_corpus_root
from corpus.store import ArtifactMissing


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="A record id, hex prefix, record path, or corpus://<id> URI.")
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        help="For a paged artifact (PDF): render this 1-indexed page first.",
    )
    parser.add_argument(
        "--frame",
        type=int,
        default=None,
        help="For an animated raster (GIF/WebP): render this 1-indexed frame first "
        "(#124; the image reading of the polymorphic frame= axis).",
    )
    parser.add_argument(
        "--mark",
        action="append",
        default=[],
        metavar="X,Y,W,H",
        help="Outline a bbox region (fractions in [0,1]; x,y,WIDTH,HEIGHT, not corners) on "
        "the full image. Repeatable — each box is auto-labeled 1..N.",
    )
    parser.add_argument(
        "--from-segments",
        action="store_true",
        help="Draw the record's already-committed bbox segments instead of --mark coords "
        "(the verify-what-I-wrote view). Pick a page with --page for a paged artifact.",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        default=None,
        metavar="90|180|270",
        help="Rotate clockwise (right a sideways scan).",
    )
    parser.add_argument(
        "--auto-orient",
        action="store_true",
        help="Apply the EXIF orientation tag (right a sideways/flipped phone photo).",
    )
    parser.add_argument(
        "--autocontrast",
        action="store_true",
        help="Stretch contrast to full range (pull a faint scan toward readable).",
    )
    parser.add_argument(
        "--fit",
        default="llm",
        metavar="WxH|PRESET",
        help="Downscale-to-fit budget (default: llm). Aspect-preserving, reduce-only.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Skip fitting — render at native resolution.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Rasterization DPI for --page (default 200). Higher = sharper fine print.",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Copy the rendered PNG here (else print the resolver cache path).",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Bypass the resolver cache and re-render.",
    )
    add_corpus_root_arg(parser)
    attach_transform_grammar(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    rid = _record_id(corpus_root, args.target)

    page = args.page
    frame = args.frame
    marks = list(args.mark)
    if args.from_segments:
        seg_marks, seg_unit = _segment_marks(corpus_root, rid, page if frame is None else frame)
        if not seg_marks:
            where = f" on page {page}" if page is not None else ""
            print(f"no committed bbox segments{where} in {rid[:12]}", file=sys.stderr)
            return 1
        marks = seg_marks + marks
        if page is None and frame is None:
            page = seg_unit

    params: list[str] = []
    if frame is not None:
        # frame= leads the chain: it selects the surface every later param operates on
        params.append(f"frame={frame}")
    if page is not None:
        params.append(f"page={page}")
    if args.dpi is not None:
        params.append(f"dpi={args.dpi}")
    if args.auto_orient:
        params.append("auto_orient")
    if args.rotate is not None:
        params.append(f"rotate={args.rotate}")
    if args.autocontrast:
        params.append("autocontrast")
    if marks:
        params.append("mark=" + ";".join(m.strip() for m in marks))
    if not args.full:
        params.append(f"fit={args.fit}")

    uri = f"corpus://{rid}" + ("?" + "&".join(params) if params else "")
    try:
        out = resolve_uri(args, uri, corpus_root)
    except ArtifactMissing as e:
        print(str(e), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, NotImplementedError) as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, args.out)
        print(args.out)
    else:
        print(out)
    return 0


def resolve_uri(args: argparse.Namespace, uri: str, corpus_root: Path) -> Path:
    from corpus import resolver

    return resolver.resolve(uri, corpus_root, regenerate=args.regenerate)


def _record_id(corpus_root: Path, target: str) -> str:
    if target.startswith("corpus://"):
        return furi.parse(target).hash
    rid, _ = paths.resolve_record(corpus_root, target)
    return rid


def _segment_marks(
    corpus_root: Path, rid: str, page: int | None
) -> tuple[list[str], int | None]:
    """Collect committed bbox addresses as `x,y,w,h` mark strings. For a paged record,
    restrict to `page` (or the first page that has boxes); returns (marks, page)."""
    post = records.load(paths.record_path(corpus_root, rid))
    by_page: dict[int | None, list[str]] = {}
    for blk in segments.iter_blocks(post.content or ""):
        segs = blk.segments if isinstance(blk, segments.Section) else [blk]
        for seg in segs:
            addrs = seg.address if isinstance(seg.address, list) else [seg.address]
            for addr in addrs:
                if not isinstance(addr, str):
                    continue
                p, box = _parse_addr(addr)
                if box is not None:
                    by_page.setdefault(p, []).append(box)
    if not by_page:
        return [], page
    if page is not None:
        return by_page.get(page, []), page
    # No page requested: a single-image record keys on None; a paged record picks the
    # lowest page that carries boxes.
    if None in by_page:
        return by_page[None], None
    first = min(p for p in by_page if p is not None)
    return by_page[first], first


def _parse_addr(addr: str) -> tuple[int | None, str | None]:
    """(unit, box): the address's 1-based unit index — its `page=` or, for an animated
    raster, its `frame=` (the two axes never co-occur on one medium) — and its bbox."""
    unit: int | None = None
    box: str | None = None
    for part in addr.split("&"):
        key, _, value = part.partition("=")
        if key in ("page", "frame"):
            try:
                unit = int(value)
            except ValueError:
                pass                     # a frame span or timecode — not a unit index
        elif key == "bbox":
            box = value
    return unit, box
