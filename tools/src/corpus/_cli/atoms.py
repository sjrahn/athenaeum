"""List atomic overlays + their body/lossless contract."""

from __future__ import annotations

import argparse

from corpus import schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--atom",
        choices=list(schemas.VALID_ATOMS),
        help="Restrict to one atom (text/image/audio/video).",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    ids = schemas.list_atomic_overlays(root, args.atom)
    if not ids:
        print("no atomic overlays declared.")
        return 0
    for slash_id in ids:
        atom, _, _sub = slash_id.partition("/")
        overlay = schemas.load_atomic_overlay(root, atom, slash_id)
        lossless = (overlay or {}).get("enables_lossless") if overlay else False
        marker = "lossless" if lossless else "non-lossless"
        desc = (overlay or {}).get("description", "").strip().splitlines()[0:1]
        head = desc[0][:70] if desc else ""
        print(f"  {slash_id:<32}  [{marker:<13}]  {head}")
    return 0
