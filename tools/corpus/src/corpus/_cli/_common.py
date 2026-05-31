"""Shared CLI helpers — corpus-root discovery, record resolution, output formatting."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus import paths


def resolved_corpus_root(args: argparse.Namespace) -> Path:
    """Get the corpus root from `args.corpus_root` (set via --corpus-root) or by
    discovery from cwd. Exits with a friendly message if neither works."""
    explicit = getattr(args, "corpus_root", None)
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "records").is_dir() or not (root / "schema").is_dir():
            sys.exit(
                f"--corpus-root {root} does not look like a corpus "
                f"(missing records/ or schema/)"
            )
        return root
    try:
        return paths.find_corpus_root()
    except FileNotFoundError as e:
        sys.exit(str(e))


def add_corpus_root_arg(parser: argparse.ArgumentParser) -> None:
    """Add the `--corpus-root <path>` option to a subcommand parser."""
    parser.add_argument(
        "--corpus-root",
        dest="corpus_root",
        default=None,
        help="Path to corpus root (default: walk up from cwd to find records/+schema/).",
    )
