"""Shared tar-archive helpers — the tar/tgz sibling of `ziparchive` (spec §12.4).

The tar family (`.tar`, `.tgz`) drafts via the same embed-manifest representation as zip: a
member is a transport addressed `path=<relpath>`, its bytes resolved back through this module
so a recorded address round-trips byte-identically. A `.tgz` is a **solid gzip stream** — a
member's bytes can't be reached without decompressing everything before it — so every access
here streams (`tarfile` mode `r|*`, which auto-detects gzip) rather than random-seeks, and the
resolver cache absorbs the one-time decompress cost (spec §12.9). The wrapper-root re-derivation
(`common_root` / `relpath`) is shared with `ziparchive` so both families address members alike.
"""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from .ziparchive import ENGINE_VERSION, common_root, relpath

__all__ = [
    "ENGINE_VERSION",
    "common_root",
    "compression",
    "member_source_modified",
    "open_archive",
    "open_member",
    "relpath",
    "resolve_member",
]


@contextmanager
def open_archive(tar_path: Path) -> Iterator[tarfile.TarFile]:
    """Open `tar_path` for sequential streaming (`r|*` — gzip auto-detected). In this mode a
    member's data must be read before the iterator advances; the manifest drafter reads each
    member's bytes (to digest them) before moving on, so this is exactly right for it."""
    with tarfile.open(tar_path, "r|*") as tf:
        yield tf


def _name_matches(name: str, rel: str) -> bool:
    """True when archive member `name` is the one a rendered `path=<rel>` address names —
    exact (the un-stripped default), or `rel` after a single wrapper-dir prefix (a
    root-stripped address). Mirrors `ziparchive`'s exact-then-re-derived-root resolution
    without needing the full member list (unavailable in a streaming pass)."""
    return name == rel or ("/" in name and name.split("/", 1)[1] == rel)


@contextmanager
def open_member(tar_path: Path, rel: str) -> Iterator[IO[bytes]]:
    """Stream a member's bytes without materializing it whole — the streaming counterpart of
    `resolve_member`, for the store-fallback / promote paths where a member can be multi-GB
    (spec §12.9). Iterates the solid stream and stops at the target, so only the bytes up to
    (and including) the member are decompressed. Yields a binary file-like; raises `ValueError`
    when no member matches."""
    with open_archive(tar_path) as tf:
        for member in tf:
            if member.isfile() and _name_matches(member.name, rel):
                fp = tf.extractfile(member)
                if fp is None:  # defensive: isfile() should guarantee a stream
                    raise ValueError(f"path={rel}: member is not a regular file")
                yield fp
                return
    raise ValueError(f"path={rel}: no such member in archive")


def resolve_member(tar_path: Path, rel: str) -> bytes:
    """Resolve a (possibly root-stripped) rendered member path back to its bytes. Streams to
    the member and reads it whole — so a `?path=<small-member>` of a large tgz decompresses
    only up to that member, not the entire archive. Raises `ValueError` when none matches."""
    with open_member(tar_path, rel) as fp:
        return fp.read()


def member_source_modified(tar_path: Path, rel: str) -> str | None:
    """The member's mtime as an ISO-8601 UTC string, or None when unreadable — the durable
    `source_modified` provenance a promoted record's origin block carries (spec §7.2, §8.1).
    Unlike zip's naive DOS timestamp, a tar member records a real epoch mtime."""
    try:
        with open_archive(tar_path) as tf:
            for member in tf:
                if member.isfile() and _name_matches(member.name, rel):
                    return (
                        datetime.fromtimestamp(member.mtime, UTC)
                        .isoformat(timespec="seconds")
                        .replace("+00:00", "Z")
                    )
    except (tarfile.TarError, OSError):
        return None
    return None


def compression(tar_path: Path) -> str:
    """`gzip` when the archive is gzip-wrapped (a `.tgz`), else `none` (a plain `.tar`). Read
    from the leading magic bytes — a generic zip fact for the manifest artifact block."""
    try:
        with tar_path.open("rb") as fh:
            return "gzip" if fh.read(2) == b"\x1f\x8b" else "none"
    except OSError:
        return "none"
