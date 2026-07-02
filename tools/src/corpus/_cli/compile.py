"""Rebuild a record from a decomposed working dir."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus import lint as _lint
from corpus import paths, recordbuild, records, segments, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workdir", type=Path, help="Decomposed working dir.")
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model id whose run this compile carries (records a combined touch).",
    )
    parser.add_argument(
        "--no-lint",
        action="store_true",
        help="Skip the lint gate (allow writes even when findings are present).",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    workdir: Path = args.workdir
    rebuilt = recordbuild.read_workdir(workdir, root)
    # Append the compile touch.
    base = touches.script_identifier("compile")
    touch_id = f"{base}+{args.model}" if args.model else base
    touches.record_touch(rebuilt, touch_id)

    # Lint gate.
    blocks = segments.iter_blocks(rebuilt.content or "")
    findings = _lint.lint(rebuilt, blocks, root)
    if findings and not args.no_lint:
        for f in findings:
            print(f"  {f.severity.upper()} {f.rule_id}: {f.message}", file=sys.stderr)
        if any(f.severity == "error" for f in findings):
            print("compile aborted: lint errors above. Re-run with --no-lint to override.", file=sys.stderr)
            return 1

    # Write back.
    record_id = rebuilt.metadata.get("id", "")
    record_file = paths.record_path(root, record_id)
    records.dump(rebuilt, record_file)
    print(f"compiled → {record_file}")
    return 0
