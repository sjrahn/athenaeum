"""Top-level block table of contents for a record."""

from __future__ import annotations

import argparse

from corpus import paths, records, segments
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    _, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)
    blocks = segments.iter_blocks(post.content or "")
    ord_ = 0
    for blk in blocks:
        ord_ += 1
        if isinstance(blk, segments.Section):
            entry = blk.entry or ""
            print(f"  {ord_:>3}. section  addr={blk.address}  entry={entry!r}")
            for child in blk.segments:
                ord_ += 1
                opener = child.overlay or child.atom
                print(f"  {ord_:>3}.   seg {opener}  addr={child.address}")
        else:
            opener = blk.overlay or blk.atom
            entry = blk.entry or ""
            print(f"  {ord_:>3}. seg {opener}  addr={blk.address}  entry={entry!r}")
    return 0
