"""List atomic overlays + their body/lossless contract — and, for one, print it in full.

*(3.8)* The listing alone was the whole command, and that was a delivery hole rather than a
terseness choice: an atom overlay's `normalization.guidance` is **authoring law** — what shape a
`text/data-table` body takes, when a table needs the HTML form, that a table's title is its
`<caption>` — and nothing printed it. The normalizer brief tells a pass to run `corpus atoms` for
each atom's contract and never to hand-read schema yaml, so law this command did not surface was
law invisible to the worker it governs (the standing §19-style rule: ask what command *delivers*
a contract before calling it landed).

Naming an id prints the whole contract: the description, the lossless verdict, the declared
extended fields, and the normalization guidance verbatim.
"""

from __future__ import annotations

import argparse
from typing import Any

from corpus import schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "class_id",
        nargs="?",
        default=None,
        metavar="CLASS-ID",
        help=(
            "An atomic class id (`text/data-table`) — print its full contract and "
            "normalization guidance. Omit to list."
        ),
    )
    parser.add_argument(
        "--atom",
        choices=list(schemas.VALID_ATOMS),
        help="Restrict the listing to one atom (text/image/audio/video).",
    )
    add_corpus_root_arg(parser)


def _block(text: str, indent: str = "  ") -> str:
    """Guidance is authored as prose with deliberate paragraph breaks — reprint it as written
    rather than re-flowing it, indented so it reads as a quoted block."""
    return "\n".join(f"{indent}{line}".rstrip() for line in text.rstrip().splitlines())


def _show(root, class_id: str) -> int:
    atom, _, _sub = class_id.partition("/")
    if atom not in schemas.VALID_ATOMS:
        print(f"unknown atom {atom!r}; expected one of {sorted(schemas.VALID_ATOMS)}")
        return 1
    overlay: dict[str, Any] | None = schemas.load_atomic_overlay(root, atom, class_id)
    if not overlay:
        print(f"no atomic overlay declared for {class_id!r}.")
        return 1

    lossless = bool(overlay.get("enables_lossless"))
    print(f"{class_id}   [{'lossless' if lossless else 'non-lossless'}]")
    print(
        "  body: a faithful, lossless rendering of the addressed region"
        if lossless
        else "  body: EMPTY — a typed marker; the overlay id carries what the region is"
    )
    if desc := str(overlay.get("description") or "").strip():
        print("\ndescription:")
        print(_block(desc))
    fields = overlay.get("extended_fields") or {}
    if fields:
        print("\nextended fields:")
        for name, spec in fields.items():
            spec = spec or {}
            req = "required" if spec.get("required") else "optional"
            print(f"  {name} ({spec.get('type', 'string')}, {req})")
            if fdesc := str(spec.get("description") or "").strip():
                print(_block(fdesc, "      "))
    guidance = str(((overlay.get("normalization") or {}).get("guidance")) or "").strip()
    if guidance:
        print("\nnormalization guidance:")
        print(_block(guidance))
    return 0


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    if args.class_id:
        return _show(root, args.class_id)
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
    print("\n  `corpus atoms <class-id>` prints one overlay's full contract + guidance.")
    return 0
