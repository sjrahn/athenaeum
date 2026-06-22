"""Shared zip-archive helpers — the common axis between the `zip-manifest` drafter
(`draft/zip_manifest.py`) and the `path=` member-extraction transform
(`transforms/zip.py`).

The drafter renders member paths (optionally root-stripped) into segment / embed
addresses; the transform re-resolves a rendered `path=<rel>` back to the actual zip
member bytes. Both go through this module so a recorded address round-trips to
byte-identical content — the same drafter↔transform contract the EPUB pair shares via
`corpus.epub.addressable_image_bytes`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def member_names(zf: zipfile.ZipFile) -> list[str]:
    """The archive's file members (directories excluded), in central-directory order."""
    return [i.filename for i in zf.infolist() if not i.is_dir()]


def common_root(names: list[str]) -> str | None:
    """Return the single `<dir>/` every member sits under, or None when they don't share
    one. A diagnostics/backup bundle typically wraps everything in one
    `<host>-<kind>-<timestamp>/` dir; root-stripping renders (and addresses) members
    relative to it so the address is stable across bundles."""
    if not names:
        return None
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        return next(iter(tops)) + "/"
    return None


def relpath(name: str, root: str | None) -> str:
    """The member name with `root` stripped, when it sits under it."""
    return name[len(root):] if root and name.startswith(root) else name


def resolve_member(zip_path: Path, rel: str) -> bytes:
    """Resolve a (possibly root-stripped) rendered member path back to its bytes.

    Tries an exact member match first (no root-strip, or a `flat` manifest), then
    re-derives the common root and prepends it (the `root_strip` case). Raises
    `ValueError` when no member matches — so the resolver surfaces a clean 4xx rather
    than an opaque KeyError."""
    rel = rel.strip()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(member_names(zf))
        if rel in names:
            return zf.read(rel)
        root = common_root(list(names))
        if root and (root + rel) in names:
            return zf.read(root + rel)
    raise ValueError(f"path={rel}: no such member in archive")
