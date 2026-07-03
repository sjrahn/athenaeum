"""Scaffold a new corpus tree."""

from __future__ import annotations

import argparse
from pathlib import Path

from corpus import scaffold


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target directory for the new corpus (default: cwd).",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing records/ or schema/ contents.",
    )


def run(args: argparse.Namespace) -> int:
    out = scaffold.scaffold(Path(args.target), force=args.force)
    print(f"scaffolded corpus at {out}")
    print("  records/                          (empty)")
    print("  schema/origin/origin.yaml          (universal — corpus-local)")
    print("  schema/origin/web/example.com.yaml (per-host overlay + `capture:` template)")
    print("  capturers/example.py              (corpus-local capturer template)")
    print("  .gitignore, README.md")
    print()
    print("Universal mime/atom/context-issue schemas resolve from the package.")
    return 0
