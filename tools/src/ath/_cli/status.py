"""`ath status` — instance working-tree state and config summary."""

from __future__ import annotations

from collections.abc import Sequence

from ath._cli._common import base_parser, git, resolve_root, upstream_counts
from ath.manifest import load_instance, load_references, load_tracker


def run(argv: Sequence[str]) -> int:
    ap = base_parser("ath status", __doc__)
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)
    instance = load_instance(root)

    label = instance.name or root.name
    if (root / ".git").exists():
        branch = git(root, "branch", "--show-current").stdout.strip() or "?"
        dirty = sum(1 for ln in git(root, "status", "--porcelain").stdout.splitlines() if ln)
        ahead, behind = upstream_counts(root)
        state = f"dirty({dirty})" if dirty else "clean"
        print(f"{label}  {branch}  {state}  ↑{ahead} ↓{behind}  ({root})")
    else:
        print(f"{label}  NOT A GIT REPO  ({root})")

    missing = 0
    for layer, path, marker in (
        ("corpus", instance.corpus_root, "records"),
        ("ledger", instance.ledger_root, "facts"),
    ):
        if (path / marker).is_dir():
            print(f"  {layer}: ok ({path})")
        else:
            print(f"  {layer}: MISSING {marker}/ ({path})")
            missing += 1

    print(f"  visibility floor: {instance.visibility}")
    try:
        tracker = load_tracker(root)
        print(f"  tracker: {tracker.owner}/{tracker.repo} → {tracker.snapshot}")
    except Exception:
        print("  tracker: (none configured)")
    refs = load_references(root)
    if refs:
        tags = sum(len(r.snapshots) for r in refs)
        print(f"  references: {len(refs)} datasets, {tags} snapshots")
    return 1 if missing else 0
