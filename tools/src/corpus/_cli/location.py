"""`corpus location` — verbs over `[[corpus.location]]` byte roots (spec §12.1.1,
§12.9.2, v21).

Subcommands:

- `attest NAME` — walk the named location's tree and bring `cache/locations.db` up to
  date (§12.1.1's attest pass): unchanged files are left alone, new/changed files are
  blake3-hashed, vanished files' rows are removed. Prints running progress every 500
  files to stderr, then the final counts.
- `list` — one row per configured location: name, kind, path, indexed row count, stale
  row count.
"""

from __future__ import annotations

import argparse
import sys

from corpus import config as config_mod
from corpus import locationindex
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_attest = sub.add_parser(
        "attest", help="Attest a configured location's tree into locations.db."
    )
    p_attest.add_argument("name", help="Location name (corpus.toml [[corpus.location]] name=).")
    add_corpus_root_arg(p_attest)

    p_list = sub.add_parser("list", help="List configured locations + index status.")
    add_corpus_root_arg(p_list)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    if args.action == "attest":
        return _attest(corpus_root, args.name)
    if args.action == "list":
        return _list(corpus_root)
    print(f"unknown action: {args.action}", file=sys.stderr)
    return 2


# ---------- handlers ---------- #


def _resolve_location(corpus_root, name: str) -> config_mod.LocationConfig | None:
    cfg = config_mod.load_config(corpus_root)
    by_name = {loc.name: loc for loc in cfg.locations}
    return by_name.get(name)


def _attest(corpus_root, name: str) -> int:
    cfg = config_mod.load_config(corpus_root)
    if not cfg.locations:
        sys.exit(
            "corpus location attest: no locations configured — add a "
            "[[corpus.location]] table to corpus.toml (spec §12.1.1)."
        )
    location = next((loc for loc in cfg.locations if loc.name == name), None)
    if location is None:
        configured = ", ".join(sorted(loc.name for loc in cfg.locations))
        sys.exit(
            f"corpus location attest: no location named {name!r}; configured: {configured}"
        )

    def _progress(n: int) -> None:
        print(f"  ...{n} files scanned", file=sys.stderr)

    counts = locationindex.attest_location(corpus_root, location, progress=_progress)
    print(
        f"location {name!r}: {counts['files']} file(s) seen, "
        f"{counts['hashed']} hashed, {counts['unchanged']} unchanged, "
        f"{counts['removed']} removed"
    )
    return 0


def _list(corpus_root) -> int:
    cfg = config_mod.load_config(corpus_root)
    if not cfg.locations:
        print("no locations configured (corpus.toml [[corpus.location]])")
        return 0
    stale_by_location: dict[str, int] = {}
    for loc_name, _relpath, _hash in locationindex.stale_rows(corpus_root):
        stale_by_location[loc_name] = stale_by_location.get(loc_name, 0) + 1
    for loc in cfg.locations:
        rows = locationindex.row_count(corpus_root, loc.name)
        stale = stale_by_location.get(loc.name, 0)
        print(f"{loc.name}  kind={loc.kind}  path={loc.path}  rows={rows}  stale={stale}")
    return 0
