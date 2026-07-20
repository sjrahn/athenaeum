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
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO

#: Versioned op id (spec §6.4 / `ledger.md` §13.2's op-version pin) for the `path=` archive-
#: member axis (spec §12.11) — pinned member-path resolution (incl. wrapper-root re-derivation)
#: and the terminal textual decode a re-chained already-textual member takes (spec §6.2 "Member
#: re-chaining"). Kept-whole zip AND tar/tgz share ONE id — the extraction contract this module
#: documents is byte-identical between them — so `transforms/zip.py` and `transforms/tar.py`
#: both re-export this constant as their own `ENGINE_VERSION` rather than duplicating it. Folded
#: into the resolver's cache key exactly like `transforms.csv.ENGINE_VERSION`: a later change to
#: member-path resolution or decode semantics is a NEW id, never a silent reinterpretation of an
#: already-resolved (and potentially already-cited, `ledger.md` §13.2) result.
ENGINE_VERSION = "archive-path@1"


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
    with zipfile.ZipFile(zip_path) as zf:
        names = set(member_names(zf))
        if rel in names:
            return zf.read(rel)
        root = common_root(list(names))
        if root and (root + rel) in names:
            return zf.read(root + rel)
    raise ValueError(f"path={rel}: no such member in archive")


def _actual_member(zf: zipfile.ZipFile, rel: str) -> str:
    """Map a rendered (possibly root-stripped) member path back to the archive's actual
    member name — exact match first, else the re-derived-root form. `ValueError` if none."""
    names = set(member_names(zf))
    if rel in names:
        return rel
    root = common_root(list(names))
    if root and (root + rel) in names:
        return root + rel
    raise ValueError(f"path={rel}: no such member in archive")


@contextmanager
def open_member(zip_path: Path, rel: str) -> Iterator[IO[bytes]]:
    """Stream a member's bytes without materializing it whole — the streaming counterpart of
    `resolve_member`, for the store-fallback / promote paths where a member can be multi-GB
    (spec §12.9). A zip's central directory is random-access, so opening one member is cheap
    regardless of archive size. Yields a binary file-like open for the life of the `with`."""
    with zipfile.ZipFile(zip_path) as zf:
        name = _actual_member(zf, rel)
        with zf.open(name) as fp:
            yield fp


def member_source_modified(zip_path: Path, rel: str) -> str | None:
    """The member's modification time as an ISO-8601 string (local, no tz — a zip stores a
    naive DOS timestamp), or None when unreadable. The durable `source_modified` provenance a
    promoted record's origin block carries (spec §7.2, §8.1)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            info = zf.getinfo(_actual_member(zf, rel))
            return datetime(*info.date_time).isoformat(timespec="seconds")
    except (ValueError, OSError):
        return None
