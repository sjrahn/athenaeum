"""Reset a record to its attested baseline (spec §8.4)."""

from __future__ import annotations

import argparse

from corpus import paths, restub
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    _, record_file = paths.resolve_record(root, args.target)
    rid = restub.restub(record_file)
    print(f"re-stubbed {rid[:12]} (attested baseline; title/description/canonical/embeds/issues cleared)")
    return 0
