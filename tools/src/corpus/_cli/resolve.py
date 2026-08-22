"""Materialise a `corpus://...` functional URI → cached file path."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys

from corpus import functional_uri as furi
from corpus import resolver
from corpus._cli._common import add_corpus_root_arg, attach_transform_grammar, resolved_corpus_root
from corpus.store import ArtifactMissing


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("uri", help="A `corpus://<hash>?<params>` URI.")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Bypass the cache and re-run the transform chain.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the cache sidecar JSON instead of just the path.",
    )
    parser.add_argument(
        "--print",
        dest="print_content",
        action="store_true",
        help="Print the resolved file's content to stdout (for text/json ops like "
        "page=N&text, words, probe, outline). Binary outputs (images) print the path.",
    )
    add_corpus_root_arg(parser)
    attach_transform_grammar(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    try:
        out = resolver.resolve(args.uri, corpus_root, regenerate=args.regenerate)
    except ArtifactMissing as e:
        sys.exit(str(e))
    except (FileNotFoundError, ValueError, NotImplementedError) as e:
        sys.exit(str(e))

    base_form = _base_form(corpus_root, args.uri)

    if args.json:
        sidecar = furi.cache_sidecar_path(out)
        payload = None
        if sidecar.is_file():
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(sidecar.read_text("utf-8"))
        if not isinstance(payload, dict):
            payload = {"path": str(out)}
        # Stdout-additive (spec §6.2): a leaf's base form, when it has one — never changes
        # an existing key, so `--json` stays backward compatible for every other shape.
        if base_form:
            payload["base_form"] = base_form
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.print_content:
        if out.suffix in (".txt", ".json"):
            print(out.read_text("utf-8").rstrip("\n"))
        else:
            # Binary (image/audio/bytes): no meaningful stdout dump — print the path.
            print(out)
            print(f"(binary {out.suffix} output — printed path, not bytes)", file=sys.stderr)
    else:
        print(out)
        # A leaf's base form (spec §6.2's route unification): `corpus://<leaf>` and
        # `corpus://<container>?stream_id=<n>` name the same bytes by the identity
        # equation (§2) — disclosed here so the equivalence is visible, not merely true.
        if base_form:
            print(f"≡ {base_form}")
    return 0


def _base_form(corpus_root, uri: str) -> str | None:
    """`corpus://<container>?stream_id=<n>` for a bare `corpus://<leaf>` uri, or None.

    Only for a BARE leaf reference — a URI that already names `stream_id=` or any other
    op is already explicit about what it's resolving, and the base form would just repeat
    it back. Tolerant of a leaf whose lineage can't be read (a record the resolve call
    itself already succeeded against) — the disclosure is a courtesy, never load-bearing."""
    from corpus import cut as cut_mod
    from corpus import paths, records

    try:
        parsed = furi.parse(uri)
    except ValueError:
        return None
    if not parsed.is_bare:
        return None
    try:
        post = records.load(paths.record_path(corpus_root, parsed.hash))
    except (FileNotFoundError, OSError):
        return None
    lineage = cut_mod.stream_lineage(post)
    if lineage is None:
        return None
    container_id, stream_address = lineage
    return f"corpus://{container_id}?{stream_address}"
