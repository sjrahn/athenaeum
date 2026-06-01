"""Count records by origin URI host."""

from __future__ import annotations

import argparse
from collections import Counter

from corpus import records, urls
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    counter: Counter[str] = Counter()
    for _md, post in records.load_all(root):
        for ob in records.iter_origin_blocks(post):
            uri = (ob.get("fields") or {}).get("uri")
            uri_list = uri if isinstance(uri, list) else [uri]
            for u in uri_list:
                if not u:
                    continue
                host = urls.host_of(str(u))
                if host:
                    counter[host] += 1
    for host, n in counter.most_common():
        print(f"  {n:>5}  {host}")
    return 0
