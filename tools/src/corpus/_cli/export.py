"""Single-record portable export per spec §10 — markdown/typst/pdf rendering of one
record, with every addressed surface materialized alongside it (`corpus.export`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus import export as export_mod
from corpus import paths
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

_ALL_FORMATS = ("md", "typst", "pdf")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--format",
        default="md",
        metavar="FMT[,FMT...]",
        help=(
            "Comma-separated output formats: md, typst, pdf (default: md). typst/pdf "
            "both write the .typ source; pdf additionally shells out to the system "
            "`typst` binary — skipped with a warning (the .typ still lands) when it "
            "is not on PATH."
        ),
    )
    parser.add_argument(
        "--annotated",
        action="store_true",
        help=(
            "Render the annotated/debug variant instead of the plain one: a metadata "
            "front block (record id, mime, origin, hash, touch chain), a per-segment "
            "atom+address label, and `corpus lint` findings rendered as redlines at "
            "their addressed positions. Output files carry an `.annotated` suffix, so "
            "running once plain and once --annotated produces both side by side."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="Output directory (default: <corpus-root>/export/<record-id>/).",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Bypass the resolver cache when materializing addressed surfaces.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    try:
        record_id, record_path = paths.resolve_record(root, args.target)
    except Exception as exc:  # tolerant by contract: report, never traceback
        print(f"corpus export: {exc}", file=sys.stderr)
        return 1

    formats = tuple(f.strip() for f in args.format.split(",") if f.strip())
    bad = [f for f in formats if f not in _ALL_FORMATS]
    if bad or not formats:
        print(
            f"corpus export: unknown format(s) {bad or ['']} — choose from {_ALL_FORMATS}",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out).expanduser() if args.out else None
    result = export_mod.export_record(
        record_id,
        record_path,
        root,
        formats=formats,
        annotated=args.annotated,
        out_dir=out_dir,
        regenerate=args.regenerate,
    )

    for path in (result.md_path, result.typ_path, result.pdf_path):
        if path:
            print(path)
    if result.assets:
        print(f"  {len(result.assets)} surface(s) materialized")
    if result.passthroughs:
        print(f"  {len(result.passthroughs)} pass-through placeholder(s)")
    for warning in result.warnings:
        print(f"  WARNING: {warning}", file=sys.stderr)
    return 0
