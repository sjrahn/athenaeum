"""`ath sync` — clone missing members per the manifest; fetch + report the rest.

Sync never rewrites a working tree: existing members are fetched and their
ahead/behind reported; `--pull` opts into a fast-forward-only pull. Members
are living data repos, so the manifest records *membership*, not pins.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from ath._cli._common import base_parser, git, resolve_root, upstream_counts
from ath.manifest import load


def run(argv: Sequence[str]) -> int:
    ap = base_parser("ath sync", __doc__)
    ap.add_argument(
        "--pull",
        action="store_true",
        help="fast-forward existing members after the fetch (default: fetch + report only)",
    )
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)
    failures = 0
    for m in load(root):
        if not (m.path / ".git").exists():
            m.path.parent.mkdir(parents=True, exist_ok=True)
            print(f"{m.name}: cloning {m.remote}")
            if subprocess.run(["git", "clone", m.remote, str(m.path)]).returncode != 0:
                print(f"{m.name}: CLONE FAILED")
                failures += 1
            continue
        fetch = git(m.path, "fetch", "--quiet")
        if fetch.returncode != 0:
            print(f"{m.name}: fetch failed — {fetch.stderr.strip()}")
            failures += 1
            continue
        ahead, behind = upstream_counts(m.path)
        if ns.pull and behind not in ("0", "?"):
            pulled = git(m.path, "pull", "--ff-only")
            if pulled.returncode != 0:
                print(f"{m.name}: pull blocked — {pulled.stderr.strip()}")
                failures += 1
            else:
                print(f"{m.name}: pulled ({behind} behind → ff)")
            continue
        print(f"{m.name}: ok (↑{ahead} ↓{behind})")
    return 1 if failures else 0
