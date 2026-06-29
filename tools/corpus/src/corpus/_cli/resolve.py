"""Materialise a `corpus://...` functional URI → cached file path."""

from __future__ import annotations

import argparse
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
    if args.json:
        sidecar = furi.cache_sidecar_path(out)
        if sidecar.is_file():
            print(sidecar.read_text("utf-8").rstrip("\n"))
        else:
            print(json.dumps({"path": str(out)}, indent=2))
    elif args.print_content:
        if out.suffix in (".txt", ".json"):
            print(out.read_text("utf-8").rstrip("\n"))
        else:
            # Binary (image/audio/bytes): no meaningful stdout dump — print the path.
            print(out)
            print(f"(binary {out.suffix} output — printed path, not bytes)", file=sys.stderr)
    else:
        print(out)
    return 0
