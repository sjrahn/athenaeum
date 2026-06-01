"""Run the conformance linter against a record (or all records in the corpus)."""

from __future__ import annotations

import argparse
import sys

from corpus import lint as _lint
from corpus import paths, records, segments
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Hash, hex prefix, or record file path. If omitted, lints every "
            "record in the corpus."
        ),
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    if args.target is None:
        return _lint_all(root)
    record_id, record_file = paths.resolve_record(root, args.target)
    return _lint_one(root, record_id, record_file)


def _lint_one(root, record_id, record_file) -> int:
    post = records.load(record_file)
    blocks = segments.iter_blocks(post.content or "")
    findings = _lint.lint(post, blocks, root)
    if not findings:
        print(f"{record_id}: clean")
        return 0
    err = 0
    for f in findings:
        if f.severity == "error":
            err += 1
        loc = f" [{f.address}]" if f.address else ""
        print(f"{record_id}: {f.severity.upper()} {f.rule_id}{loc}: {f.message}")
    return 1 if err else 0


def _lint_all(root) -> int:
    records_dir = root / "records"
    if not records_dir.is_dir():
        print("no records/ dir")
        return 0
    any_err = 0
    any_record = False
    for md in records.iter_record_paths(root):
        any_record = True
        try:
            post = records.load(md)
            blocks = segments.iter_blocks(post.content or "")
            findings = _lint.lint(post, blocks, root)
        except Exception as e:
            print(f"{md.stem}: ERROR loading: {e}", file=sys.stderr)
            any_err = 1
            continue
        for f in findings:
            if f.severity == "error":
                any_err = 1
            loc = f" [{f.address}]" if f.address else ""
            print(f"{md.stem}: {f.severity.upper()} {f.rule_id}{loc}: {f.message}")
    if not any_record:
        print("no records to lint")
    return any_err
