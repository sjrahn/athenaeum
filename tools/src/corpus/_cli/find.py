"""List records matching filters."""

from __future__ import annotations

import argparse
import json
import sys

from corpus import records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", help="Filter by status: stub | draft | normalized.")
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
        status = post.metadata.get("status", "")
        mime = records.media_type_for(post)
        if args.status and status != args.status:
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
                "status": status,
                "mime": mime,
                "title": records.title_for(post),
                "uri": records.primary_origin_uri(post),
            }
        )
    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for r in rows:
            t = r["title"][:40] if r["title"] else ""
            print(f"  {r['id'][:12]}  {r['status']:<10}  {r['mime']:<28}  {t}")
        print(f"\n{len(rows)} record(s)")
    return 0
