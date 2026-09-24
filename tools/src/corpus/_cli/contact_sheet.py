"""`corpus contact-sheet` — a labelled grid over a container's image and video members (spec
§12.9.3, v45/v46). An instrument: it shows an investigator which frames to open, and every tile names the
member address to open (or cite) next. Never an anchor, never stored.

    corpus contact-sheet <container>                                  sheet 1, roster order
    corpus contact-sheet <container> --page 3                         the third sheet
    corpus contact-sheet <container> --where osx_persons~Erasmas \\
        --sort osx_date_original --label osx_date_original             the cat, by date
    corpus contact-sheet <container> --where osx_kind!~screenshot     no screenshots
    corpus contact-sheet <container> --glob 'IMG_14*'                 by member path
    corpus contact-sheet <container> --video-at 5                     video tiles at 5 s
    corpus contact-sheet <container> --no-video                       stills only

A video member is tiled by one still (`frame=<secs>`, badged ▶; the legend records the
instant); a video another member references by address (a live photo's motion twin) is its
companion and is passed over, disclosed as `companion`.

`--where FIELD<op>VALUE` runs over the container's `members` descriptors (`corpus resolve
'corpus://<container>?members'` shows them) — for a container whose origin declares a member
sidecar (§7.2), those carry each frame's lifted fields. Ops: `~` contains, `!~` lacks, `=`,
`!=`, `>=`, `<=` (dates compare on the value's own face). Repeatable; all must hold.
"""

from __future__ import annotations

import argparse
import json
import sys

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    from corpus import contact_sheet as cs

    parser.add_argument(
        "container", help="container record: id, hex prefix, path, or corpus://<id>"
    )
    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        metavar="PATTERN",
        help="keep members whose path matches (fnmatch; repeatable, any may match)",
    )
    parser.add_argument(
        "--where",
        action="append",
        default=[],
        metavar="FIELD<op>VALUE",
        help="keep members whose descriptor field satisfies this (repeatable, all)",
    )
    parser.add_argument(
        "--sort",
        metavar="FIELD",
        default=None,
        help="order by a descriptor field (dates, then numbers, then text; "
        "members lacking it go last). Default: roster order.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="FIELD",
        help="print this descriptor field under each tile (repeatable)",
    )
    parser.add_argument("--page", type=int, default=1, help="which sheet (1-based)")
    parser.add_argument("--columns", type=int, default=cs.DEFAULT_COLUMNS)
    parser.add_argument("--rows", type=int, default=cs.DEFAULT_ROWS)
    parser.add_argument("--tile", type=int, default=cs.DEFAULT_TILE, help="tile box, px")
    parser.add_argument(
        "--video-at",
        default=cs.DEFAULT_VIDEO_AT,
        metavar="SECS",
        help="the instant a video tile shows (seconds or MM:SS; default %(default)s; "
        "a shorter clip falls back to its first frame)",
    )
    parser.add_argument(
        "--no-video", action="store_true", help="tile image members only (videos disclosed)"
    )
    parser.add_argument(
        "--full", action="store_true", help="skip the final fit to the `llm` budget"
    )
    parser.add_argument("--jobs", type=int, default=None, help="parallel tile renders")
    parser.add_argument("--regenerate", action="store_true", help="bypass the sheet cache")
    parser.add_argument("--json", action="store_true", help="print the legend as JSON")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import contact_sheet as cs

    root = resolved_corpus_root(args)
    try:
        container_id = cs.resolve_container(root, args.container)
        preds = [cs.parse_where(w) for w in args.where]
        sheet = cs.build(
            root,
            container_id,
            globs=args.glob,
            where=preds,
            sort=args.sort,
            labels=args.label,
            page=args.page,
            columns=args.columns,
            rows=args.rows,
            tile=args.tile,
            video=not args.no_video,
            video_at=args.video_at,
            fit_llm=not args.full,
            jobs=args.jobs,
            regenerate=args.regenerate,
        )
    except (cs.SheetError, ValueError) as exc:
        print(f"contact-sheet: {exc}", file=sys.stderr)
        return 2
    legend = sheet.legend
    if args.json:
        print(json.dumps({"path": str(sheet.path), **legend}, indent=2, ensure_ascii=False))
        return 0
    print(sheet.path)
    skipped = ", ".join(f"{v} {k}" for k, v in sorted(legend.get("skipped", {}).items()))
    print(
        f"sheet {legend['page']}/{legend['pages']} · {len(legend['tiles'])} of "
        f"{legend['selected']} selected member(s)"
        + (f" · passed over: {skipped}" if skipped else "")
        + f" · corpus://{container_id}"
        + (" · (cached)" if sheet.cached else "")
    )
    for t in legend["tiles"]:
        extra = "  ".join(f"{k}={v}" for k, v in t["labels"].items())
        err = f"  [unreadable: {t['error']}]" if t.get("error") else ""
        vid = f"  [video @ {t['frame']}s]" if t.get("frame") is not None else (
            "  [video]" if t.get("video") else ""
        )
        print(f"  {t['n']:>4}  {t['address']}" + vid + (f"  {extra}" if extra else "") + err)
    return 0
