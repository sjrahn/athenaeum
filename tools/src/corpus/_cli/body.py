"""Stream the content-zone body to stdout."""

from __future__ import annotations

import argparse
import sys

from corpus import paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    _, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)
    sys.stdout.write(post.content or "")
    if not (post.content or "").endswith("\n"):
        sys.stdout.write("\n")
    return 0
