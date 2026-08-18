"""`corpus locate <blake3>` — the residency query (spec §12.1.1, §12.9.2, v24
"Residency query" amendment): for a bare, full blake3 hash, where do those bytes
reside — across every route this pass covers — and does a record exist for them?
Read-only, and works for hashes the corpus has never minted: an external hash can be
checked against every attached residence without moving a byte.

This wave searches: a `records/` entry for the hash; a co-located or store-location
artifact (`corpus.maintenance`'s own artifact-finding helper, which already covers
store locations); and every row in the attached-location index (`locations.db`),
computed and presented alike, each stamped current or stale via
`locationindex.pins_match`. It deliberately does NOT search containment/the member
index or remote objects (spec §12.1.1 (24) names both as later ground) — `--json`'s
`searched` field names exactly what ran, so a caller never has to guess.

A hash with multiple residencies is the dedup surface (see also `corpus health`'s
`shadowed_copies` / `duplicate_residencies` signals, which surface the fleet-wide
version of the same fact); this command answers it for one hash on demand.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_SEARCHED = ("record", "co-located + store artifacts", "attached-location index")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("hash", help="Full 64-hex blake3 hash (bare hex, no prefixes).")
    parser.add_argument("--json", action="store_true", help="structured JSON output")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import config as config_mod
    from corpus import locationindex, paths
    from corpus.maintenance import _find_artifact

    corpus_root = resolved_corpus_root(args)
    hash_ = str(args.hash).strip().lower()
    if not _HEX64.match(hash_):
        sys.exit(
            f"corpus locate: {args.hash!r} is not a full 64-hex blake3 hash — a short "
            f"prefix isn't accepted here (locate answers residency for one exact "
            f"hash; `corpus find`/`corpus inspect` resolve a prefix first)."
        )

    result: dict[str, Any] = {
        "hash": hash_,
        "searched": list(_SEARCHED),
        "record": None,
        "artifact": None,
        "attached": [],
    }

    rpath = paths.record_path(corpus_root, hash_)
    if rpath.is_file():
        result["record"] = str(rpath.relative_to(corpus_root))

    apath, asize, aloc = _find_artifact(corpus_root, hash_)
    if apath is not None:
        result["artifact"] = {
            "path": str(apath) if aloc else str(apath.relative_to(corpus_root)),
            "location": aloc,  # None = co-located artifacts/ tree
            "size": asize,
        }

    by_name = {loc.name: loc.path for loc in config_mod.load_config(corpus_root).locations}
    with locationindex.open_index(corpus_root) as conn:
        rows = conn.execute(
            "SELECT location, relpath, size, mtime, source FROM locations WHERE hash = ?",
            (hash_,),
        ).fetchall()
    for loc_name, relpath, size, mtime, source in rows:
        base = by_name.get(loc_name)
        current = False
        if base is not None:
            candidate = base / relpath
            try:
                st = candidate.stat()
            except OSError:
                st = None
            if st is not None:
                current = locationindex.pins_match(
                    size, mtime, st.st_size, st.st_mtime_ns, source
                )
        result["attached"].append(
            {
                "location": loc_name,
                "relpath": relpath,
                "source": source,
                "status": "current" if current else "stale",
            }
        )

    found = bool(result["record"] or result["artifact"] or result["attached"])

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_human(result)

    return 0 if found else 1


def _print_human(result: dict[str, Any]) -> None:
    print(f"locate {result['hash']}")
    print(f"  record: {result['record'] or 'no record'}")
    if result["artifact"]:
        a = result["artifact"]
        where = a["location"] or "co-located artifacts/"
        print(f"  artifact: {a['path']} ({where}, {a['size']} bytes)")
    else:
        print("  artifact: none")
    if result["attached"]:
        print(f"  attached rows ({len(result['attached'])}):")
        for row in result["attached"]:
            print(
                f"    {row['location']}/{row['relpath']}  source={row['source']}  "
                f"{row['status']}"
            )
    else:
        print("  attached rows: none")
    if not (result["record"] or result["artifact"] or result["attached"]):
        print(f"nothing found anywhere for {result['hash']} (searched: "
              f"{', '.join(result['searched'])})")
