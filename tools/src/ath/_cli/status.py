"""`ath status` — working-tree state of the orchestrator repo and every member."""

from __future__ import annotations

from collections.abc import Sequence

from ath._cli._common import base_parser, git, resolve_root, upstream_counts
from ath.manifest import load


def run(argv: Sequence[str]) -> int:
    ap = base_parser("ath status", __doc__)
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)
    rows = [("athenaeum", root)] + [(m.name, m.path) for m in load(root)]
    width = max(len(name) for name, _ in rows)
    missing = 0
    for name, path in rows:
        if not (path / ".git").exists():
            print(f"{name:<{width}}  MISSING — run `ath sync`")
            missing += 1
            continue
        branch = git(path, "branch", "--show-current").stdout.strip() or "?"
        dirty = sum(1 for ln in git(path, "status", "--porcelain").stdout.splitlines() if ln)
        ahead, behind = upstream_counts(path)
        state = f"dirty({dirty})" if dirty else "clean"
        print(f"{name:<{width}}  {branch}  {state}  ↑{ahead} ↓{behind}")
    return 1 if missing else 0
