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
        "--namespace",
        "-n",
        required=True,
        help="Composite namespace id to seed (e.g. `document`).",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing records/ or schema/ contents.",
    )


def run(args: argparse.Namespace) -> int:
    out = scaffold.scaffold(Path(args.target), namespace=args.namespace, force=args.force)
    print(f"scaffolded corpus at {out}")
    print(f"  records/                          (empty)")
    print(f"  schema/origin/origin.yaml         (universal — corpus-local)")
    print(f"  schema/composite/{args.namespace}/  (stub)")
    print(f"  .gitignore, README.md")
    print()
    print("Universal mime/atom/composite-issue schemas resolve from the package.")
    return 0
