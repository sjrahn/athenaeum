"""Shared plumbing for the ath system verbs."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ath.manifest import MANIFEST_NAME, ManifestError, find_root


def base_parser(prog: str, description: str | None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=description)
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help=f"orchestrator repo root (default: walk up for {MANIFEST_NAME})",
    )
    return ap


def resolve_root(root: Path | None) -> Path:
    if root is None:
        return find_root()
    root = root.resolve()
    if not (root / MANIFEST_NAME).is_file():
        raise ManifestError(f"{root} does not contain {MANIFEST_NAME}")
    return root


def git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)


def upstream_counts(path: Path) -> tuple[str, str]:
    """(ahead, behind) vs upstream, or ("?", "?") when there is no upstream."""
    res = git(path, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if res.returncode != 0:
        return "?", "?"
    behind, ahead = res.stdout.split()
    return ahead, behind
