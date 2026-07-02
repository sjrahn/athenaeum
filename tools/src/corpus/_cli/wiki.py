"""Search / read the local Wikipedia knowledge base (the concept KB).

    corpus wiki search "<query>" [--zim PATH] [--limit N]
    corpus wiki read   "<ref>"   [--zim PATH] [--full]

`<ref>` is a ZIM path, an `enwiki:<Title>`, or a bare article title. The ZIM path is resolved
explicit `--zim` > `ATH_WIKI_ZIM` > `[corpus.wiki].zim` in corpus.toml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus import paths, wiki
from corpus._cli._common import add_corpus_root_arg


def _common_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    add_corpus_root_arg(parent)
    parent.add_argument(
        "--zim",
        default=None,
        help="Path to the Wikipedia ZIM (else ATH_WIKI_ZIM / corpus.toml [corpus.wiki].zim).",
    )
    return parent


def configure(parser: argparse.ArgumentParser) -> None:
    parent = _common_parent()
    sub = parser.add_subparsers(dest="action", required=True)

    s = sub.add_parser("search", parents=[parent], help="Full-text search the KB.")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)

    r = sub.add_parser("read", parents=[parent], help="Resolve + print a concept article.")
    r.add_argument("ref", help="ZIM path, enwiki:<Title>, or an article title.")
    r.add_argument(
        "--full", action="store_true", help="Print the full article HTML instead of the summary."
    )


def _optional_root(args: argparse.Namespace) -> Path | None:
    explicit = getattr(args, "corpus_root", None)
    if explicit:
        return Path(explicit).resolve()
    try:
        return paths.find_corpus_root()
    except FileNotFoundError:
        return None


def _open(args: argparse.Namespace) -> wiki.WikiKB:
    return wiki.open_kb(zim=args.zim, corpus_root=_optional_root(args))


def run(args: argparse.Namespace) -> int:
    try:
        kb = _open(args)
        if args.action == "search":
            hits = kb.search(args.query, limit=args.limit)
            if not hits:
                print("(no matches)")
                return 0
            for h in hits:
                print(f"{h.title}\n    {h.id}    {h.url}")
            return 0
        # read
        if args.full:
            html = kb.read(args.ref)
            if html is None:
                print(f"(could not resolve {args.ref!r})", file=sys.stderr)
                return 1
            print(html)
            return 0
        art = kb.get(args.ref)
        if art is None:
            print(f"(could not resolve {args.ref!r})", file=sys.stderr)
            return 1
        print(f"title:   {art.title}")
        print(f"id:      {art.id}")
        if art.qid:
            print(f"qid:     {art.qid}")
        print(f"url:     {art.url}")
        print(f"summary: {art.summary}")
        return 0
    except wiki.WikiUnavailable as exc:
        print(f"wiki KB unavailable: {exc}", file=sys.stderr)
        return 1
