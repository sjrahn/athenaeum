"""Store-location placement (spec §12.1.1, v22/v23 placement amendments).

A **store** location is a content-addressed `<shard>/<hash>.<ext>` tree the corpus
writes at another root — §12.1's layout, relocated. This module answers the two
questions that layout raises: given a media type (and, v23, the origin overlay the
minting origin resolved to), which store location (if any) is a new artifact's
destination (`ingest_destination`) — the most specific claim wins: an origin claim
beats a format claim beats the `ingest = true` default, the co-located `artifacts/`
tree the fallback when nothing matches — and, for byte resolution, whether an EXISTING
standalone copy already lives in one (`find_in_stores`). `put_at` is the write side: it
lands bytes at a store location's content-addressed path without ever leaving a
half-written file at the final name.

Local paths only this wave — a `remote =` key is rejected at config load (ticket #204),
so every `LocationConfig` reaching this module has a real local `path`.
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

import blake3 as _blake3

from . import config as config_mod
from . import paths

_COPY_CHUNK = 1 << 20  # 1 MiB — mirrors hashing.CHUNK


def store_locations(corpus_root: Path) -> tuple[config_mod.LocationConfig, ...]:
    """Every `kind = "store"` location configured for `corpus_root`, in declaration
    order (spec §12.1.1) — the order `ingest_destination` and `find_in_stores` both
    walk, so a corpus.toml's location order is itself the tie-break."""
    return tuple(
        loc for loc in config_mod.load_config(corpus_root).locations if loc.kind == "store"
    )


def location_artifact_path(loc: config_mod.LocationConfig, record_id: str, extension: str) -> Path:
    """`<loc.path>/<shard>/<record_id>.<ext>` — `paths.artifact_path`'s content-
    addressed layout, rooted at `loc` instead of the corpus's co-located `artifacts/`
    tree (spec §12.1.1: "§12.1's layout at another root")."""
    ext = extension.lstrip(".")
    return loc.path / paths.shard(record_id) / f"{record_id}.{ext}"


def find_in_stores(corpus_root: Path, record_id: str, extension: str) -> Path | None:
    """The first store location holding a standalone copy of `record_id`'s bytes under
    `extension`, or `None` (spec §12.1.1's route order: co-located store → OTHER store
    locations → attached-location index → member index → remote hydration). Several
    locations may hold the same bytes; any route yields identical bytes (§2), so
    declaration order alone decides which is returned."""
    for loc in store_locations(corpus_root):
        candidate = location_artifact_path(loc, record_id, extension)
        if candidate.is_file():
            return candidate
    return None


def ingest_destination(
    corpus_root: Path, media_type: str, *, origin_schema: str | None = None
) -> config_mod.LocationConfig | None:
    """Which store location a NEW artifact of `media_type` should land in (spec
    §12.1.1, v22/v23) — the **most specific claim wins**, most specific first: an
    **origin claim** (the first location, declaration order, whose `ingest_origins`
    contains `origin_schema` — the origin overlay id the minting origin resolved to,
    §7.2), else a **format claim** (the first location whose `ingest_types` names
    `media_type`), else the location declaring `ingest = true` (the corpus-wide default
    destination — config load already guarantees at most one), else `None`. `None`
    means the co-located `artifacts/` tree is the destination — the fallback when no
    location claims anything.

    `origin_schema=None` (no matched origin overlay, or the caller has none to offer)
    skips the origin axis entirely — an artifact minted with no matched origin overlay
    can never satisfy an origin claim (spec §12.1.1 (23))."""
    locs = store_locations(corpus_root)
    if origin_schema is not None:
        for loc in locs:
            if origin_schema in loc.ingest_origins:
                return loc
    default: config_mod.LocationConfig | None = None
    for loc in locs:
        if media_type in loc.ingest_types:
            return loc
        if loc.ingest_default:
            default = loc
    return default


def put_at(loc: config_mod.LocationConfig, record_id: str, extension: str, src: Path) -> Path:
    """Write `src`'s bytes into `loc` at its content-addressed path (spec §12.1.1) and
    return the destination. Same-device: `src` is renamed straight onto a `.part`
    temp name — `src` is GONE afterward. Cross-device (`EXDEV`): `src` is copied to
    the temp name instead and left in place for the caller to remove. Either way the
    temp name is `os.replace`d onto the final name last, so a crash mid-write leaves at
    worst a `.part` sibling — never a half-written file at the final name."""
    dst = paths.ensure_parent(location_artifact_path(loc, record_id, extension))
    tmp = dst.with_name(f"{dst.name}.part")
    try:
        os.rename(src, tmp)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    return dst


class MoveVerificationError(Exception):
    """Raised by `copy_verified` when the freshly-copied bytes don't hash to the
    expected record id (spec §12.1.1 "Move semantics"). The `.part` temp is already
    deleted and `src` is untouched by the time this reaches the caller — `expected`/
    `actual` let the caller report both hashes."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"copy hashed to {actual}, expected {expected}")


def copy_verified(src: Path, dst: Path, record_id: str) -> None:
    """Copy `src`'s bytes to `dst` the way `corpus location move` requires (spec
    §12.1.1): stream through a `.part` temp name at `dst`'s final path, hashing blake3
    as the bytes are written, and verify the full digest against `record_id` BEFORE
    `os.replace` unveils `dst` — at no instant does `dst` exist with unverified
    content. A mismatch deletes the temp and raises `MoveVerificationError`; `src` and
    any prior `dst` are untouched either way. The caller decides what happens to `src`
    afterward (`move` removes it only once this returns clean)."""
    dst = paths.ensure_parent(dst)
    tmp = dst.with_name(f"{dst.name}.part")
    hasher = _blake3.blake3()
    with src.open("rb") as fh_in, tmp.open("wb") as fh_out:
        while chunk := fh_in.read(_COPY_CHUNK):
            hasher.update(chunk)
            fh_out.write(chunk)
    digest = hasher.hexdigest()
    if digest != record_id:
        tmp.unlink(missing_ok=True)
        raise MoveVerificationError(record_id, digest)
    os.replace(tmp, dst)
