"""Materialise a `corpus://...` functional URI → cached file path."""

from __future__ import annotations

import argparse
import json
import sys

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
        sidecar = out.with_suffix(".json")
        if sidecar.is_file():
            print(sidecar.read_text("utf-8").rstrip("\n"))
        else:
            print(json.dumps({"path": str(out)}, indent=2))
    else:
        print(out)
    return 0
