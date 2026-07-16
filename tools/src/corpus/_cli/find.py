"""List records matching filters."""

from __future__ import annotations

import argparse
import json
import sys

from corpus import records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

_STATE_CHOICES = ("proxy", "rendered", "formed", "untitled", "any")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state",
        choices=_STATE_CHOICES,
        default="any",
        help=(
            "Filter by derived state (spec §4.1): proxy | rendered | formed. `untitled` "
            "filters on the derived editorial title instead (spec §4.2.3) — it is ORTHOGONAL "
            "to the state enum (a record can derive an empty title at any of "
            "proxy/rendered/formed), so `--state untitled` matches any record whose derived "
            "title is empty — the §12.21 role-marking worklist — regardless of "
            "proxy/rendered/formed."
        ),
    )
    parser.add_argument("--mime", help="Filter by artifact MIME type.")
    parser.add_argument("--host", help="Filter by origin URI host (substring match).")
    parser.add_argument("--classification", help="Filter by derived classification id (mime/* or origin/*).")
    parser.add_argument("--json", action="store_true", help="JSON output.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    rows: list[dict] = []
    for md in records.iter_record_paths(root):
        try:
            post = records.load(md)
        except Exception as e:
            print(f"WARN: load failed for {md}: {e}", file=sys.stderr)
            continue
        state = records.derived_state(post)
        title = records.derived_editorial_field(post, root, "title")
        mime = records.media_type_for(post)
        if args.state == "untitled" and title.value:
            continue
        if args.state not in ("any", "untitled") and state != args.state:
            continue
        if args.mime and mime != args.mime:
            continue
        if args.host:
            uri = records.primary_origin_uri(post)
            if args.host not in uri:
                continue
        if args.classification:
            if args.classification not in records.derived_classifications(post):
                continue
        rows.append(
            {
                "id": post.metadata.get("id", md.stem),
                "state": state,
                "mime": mime,
                "title": title.value,
                "title_layer": title.layer,
                "uri": records.primary_origin_uri(post),
            }
        )
    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for r in rows:
            t = r["title"][:40] if r["title"] else ""
            layer = f"[{r['title_layer']}]" if r["title_layer"] else "[none]"
            print(f"  {r['id'][:12]}  {r['state']:<9} {layer:<11} {r['mime']:<28}  {t}")
        print(f"\n{len(rows)} record(s)")
    return 0
