"""Export-job bundle assembler — repackage delivered export archives into ONE
self-describing, containment-friendly zip per export job (spec §2.1 containment, §12.4).

A vendor delivers an export job as one or more transient archives (a Google Takeout
`takeout-<stamp>-<part>.tgz`, an Instagram `.zip`) behind an ephemeral download link.
The delivery envelope is disposable — Google deletes the job after ~7 days and there is
no live lineage to the archive file itself — so the archival objects are the MEMBERS plus
any out-of-band report. This engine decompresses the delivered part archive(s) and
recompresses their union into one **indexed** zip (a solid-stream tgz dies; a
central-directory zip lives): members promotable on demand (§8.1), byte-identical to the
originals, resolvable member-by-member without decompressing the whole.

The engine is **generic** — every vendor-shaped fact (which files are declared additions,
how the internal tree may be restructured, the zstd level) is passed in by the caller from
the origin overlay's `capture.assembly` config; nothing here knows "Takeout" or "Instagram".

Two layers, kept separate so the writer is reusable: the **writer core** (`BundleMember` +
`write_bundle`) is pure bytes-in/bundle-out — it knows nothing of source archives, overlays, or
sidecars — and is shared with the planned `corpus pack` verb (spec §12.8), which will feed it
members named by record id with bytes streamed from the artifact store. The **assemble
frontend** (`assemble`) is everything parts/overlay/sidecar-shaped.

**The bundle format** (pinned):
- zip64-capable; members written in SORTED path order; member paths VERBATIM from the
  sources (never renamed unless a declared rewrite says so); member mtimes copied from the
  source archive's member metadata.
- Per-member compression: `ZIP_ZSTANDARD` (method 93) at `level` (default 19 — a one-time
  archival compress; zstd *decompress* is essentially level-independent). A member whose
  extension is already-compressed (`_ALREADY_COMPRESSED`) goes `ZIP_STORED` — recompressing
  jpeg/mp4/zip bytes only burns CPU.
- Additions (non-original files, e.g. a report) land at the bundle ROOT, outside the
  original tree, so the original structure is untouched.
- The zip archive COMMENT is stamped with the job identity (the `zip-manifest` drafter
  surfaces it as the artifact block's `comment`).

**Deterministic**: same inputs + same config → byte-identical bundle. No wall-clock reaches
the output — member mtimes come from the sources (UTC-decomposed, so the DOS timestamp does
not depend on the assembling machine's timezone), and `create_system` is pinned to Unix so a
bundle built on macOS matches one built on Linux. The one residual caveat is the **zstd
library version**: a future libzstd whose level-19 encoder emits different (still-valid)
bytes would change the compressed frames. Member *identity* (each member's blake3, recorded
on its embed) is unaffected — the decompressed bytes are byte-identical regardless.

**Streaming throughout**: a multi-GB member never loads whole into RAM (1 MiB chunks). A
solid tgz is not random-access, so its members are staged to a temp dir once (streamed +
hashed in the same pass) and read back in sorted order; a zip source is central-directory
random-access, so its members stream straight through with no staging.

**Deliberate exception to the tolerant-parse principle (spec §1.5).** Everywhere else the
pipeline logs and skips an unreadable record; assembly does NOT. A bundle must be complete or
absent — a silently-dropped member would make the retired originals the only copy of bytes
the bundle claims to hold — so an unreadable source member is a HARD ERROR that aborts the
whole assembly, leaving no partial bundle behind.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import IO

import blake3

from . import tararchive, ziparchive

# Stream members in 1 MiB chunks so a multi-GB member is never held whole in RAM.
_CHUNK = 1 << 20

# Archival default: one-time compress at a high level (decompress is level-independent).
DEFAULT_LEVEL = 19

# Member extensions whose bytes are already compressed — recompressing them with zstd only
# burns CPU for no gain, so they are stored (method 0). Module-level constant, extension-keyed
# (lowercase, no dot). Kept deliberately static — a content sniff would cost a read of every
# member; the extension is the cheap, faithful signal for a delivery archive.
_ALREADY_COMPRESSED: frozenset[str] = frozenset(
    {
        # raster images
        "jpeg", "jpg", "png", "gif", "webp", "heic", "heif", "avif",
        # video
        "mp4", "mov", "avi", "mkv", "webm", "m4v",
        # audio
        "mp3", "m4a", "aac", "ogg", "opus", "flac",
        # already-compressed archives / containers
        "zip", "gz", "tgz", "bz2", "xz", "zst", "zstd", "7z", "rar", "lz4", "br",
        # zip-based document/package formats (OOXML / OpenDocument / epub / jar)
        "docx", "xlsx", "pptx", "epub", "jar", "odt", "ods", "odp",
    }
)

# Unix create_system, pinned so a bundle's bytes don't depend on the OS that built it (the
# ZipInfo default is 3 on POSIX but 0 on Windows).
_CREATE_SYSTEM_UNIX = 3

# Above this member size the local-file-header + central-directory entry needs zip64 extra
# fields. Forced per-member from the known size so the streaming write path never has to guess.
_ZIP64_LIMIT = (1 << 32) - 1


class AssemblyError(Exception):
    """A source member could not be read, a declared conflict fired, or the config was
    contradictory. Raised loudly — a bundle is complete or absent (module docstring)."""


@dataclass(frozen=True)
class SourcePart:
    """One delivered source archive. `label` is the tombstone filename recorded in
    `source_parts` (the original delivery name when known — e.g. `takeout-<stamp>-<part>.tgz`
    — else the stored path's basename); `path` is where its bytes actually live now."""

    path: Path
    label: str


@dataclass
class AssemblyResult:
    out_path: Path
    bundle_bytes: int
    member_count: int  # original members + additions written to the bundle
    services: list[str]  # top-level dirs under the original members' common root
    source_parts: list[tuple[str, str]]  # (label, blake3-hex) tombstone per source archive
    rewrites_applied: list[tuple[str, str]] = field(default_factory=list)  # (from, to)
    member_addresses: list[str] = field(default_factory=list)  # sorted path= member paths


# ---------- the member plan ---------- #


@dataclass
class _Planned:
    """One member destined for the bundle: its bundle path, its zip date_time tuple, its size,
    the blake3 of its bytes (for dedup / conflict), and a byte source pass 2 re-opens."""

    out_path: str
    date_time: tuple[int, int, int, int, int, int]
    size: int
    digest: str
    source: _ByteSource


class _ByteSource:
    """A re-openable byte source for pass 2 — a staged temp file (a tar member decompressed
    once), a zip member (central-directory random access), or an addition file on disk."""

    def open(self) -> AbstractContextManager[IO[bytes]]:  # pragma: no cover - overridden
        raise NotImplementedError


class _FileSource(_ByteSource):
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def open(self) -> Iterator[IO[bytes]]:
        with self.path.open("rb") as fp:
            yield fp


class _ZipMemberSource(_ByteSource):
    def __init__(self, zip_path: Path, member: str) -> None:
        self.zip_path = zip_path
        self.member = member

    @contextmanager
    def open(self) -> Iterator[IO[bytes]]:
        with zipfile.ZipFile(self.zip_path) as zf, zf.open(self.member) as fp:
            yield fp


# ---------- top-level assembly ---------- #


def assemble(
    sources: list[SourcePart],
    additions: list[Path],
    out_path: Path,
    *,
    level: int = DEFAULT_LEVEL,
    merge_parts: bool = True,
    conflict: str = "error",
    rewrites: list[dict] | None = None,
    comment: str = "",
    staging_dir: Path | None = None,
) -> AssemblyResult:
    """Assemble `sources` (+ root-level `additions`) into one deterministic zip at `out_path`.

    `merge_parts` unions a multi-part delivery into one tree (the split is delivery, not
    structure); with it false, more than one source is a hard error. `conflict` governs a
    same-path collision across parts: `error` (the default and only declared value) raises on
    differing bytes; identical bytes always dedup silently. `rewrites` is the declared
    `[{from, to}]` restructure mapping (empty is the norm — verbatim preservation). `comment`
    is the job-identity string stamped on the zip. Raises `AssemblyError` on any unreadable
    member or fired conflict, leaving no partial bundle."""
    if not sources:
        raise AssemblyError("no source archives given")
    if len(sources) > 1 and not merge_parts:
        raise AssemblyError(
            f"{len(sources)} source parts given but merge_parts is not enabled — refusing to "
            f"guess whether the split is structural (declare merge_parts: true to union them)."
        )
    rules = list(rewrites or [])

    staging_root = staging_dir or out_path.parent
    staging_root.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(_mkdtemp(staging_root))
    try:
        by_path: dict[str, _Planned] = {}
        rewrites_applied: list[tuple[str, str]] = []
        original_relpaths: list[str] = []
        source_parts: list[tuple[str, str]] = []

        for part in sources:
            source_parts.append((part.label, _hash_file(part.path)))
            for relpath, date_time, size, digest, byte_src in _iter_source_members(
                part.path, tmpdir
            ):
                original_relpaths.append(relpath)
                out_rel, applied = _apply_rewrites(relpath, rules)
                if applied:
                    rewrites_applied.append((relpath, out_rel))
                _place(by_path, out_rel, date_time, size, digest, byte_src, conflict, kind="member")

        for add in additions:
            digest, size = _hash_and_size(add)
            _place(
                by_path,
                add.name,  # additions land at the bundle ROOT (basename only)
                epoch_to_dostuple(_safe_mtime(add)),
                size,
                digest,
                _FileSource(add),
                conflict,
                kind="addition",
            )

        planned = sorted(by_path.values(), key=lambda p: p.out_path)
        # Hand the resolved plan to the reusable writer core (bytes-in, bundle-out).
        members = [
            BundleMember(
                path=pm.out_path,
                open_stream=pm.source.open,
                date_time=pm.date_time,
                size=pm.size,
            )
            for pm in planned
        ]
        bundle_bytes = write_bundle(members, out_path, level=level, comment=comment)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return AssemblyResult(
        out_path=out_path,
        bundle_bytes=bundle_bytes,
        member_count=len(planned),
        services=_derive_services(original_relpaths),
        source_parts=source_parts,
        rewrites_applied=rewrites_applied,
        member_addresses=[f"path={p.out_path}" for p in planned],
    )


# ---------- member enumeration (dispatch by source family) ---------- #


def _iter_source_members(
    path: Path, tmpdir: Path
) -> Iterator[tuple[str, tuple[int, int, int, int, int, int], int, str, _ByteSource]]:
    """Yield `(relpath, date_time, size, blake3-hex, byte_source)` for each FILE member of a
    source archive. A tar/tgz is a solid stream, so each member is staged to `tmpdir` once
    (streamed + hashed in the same pass) and read back later; a zip is random-access, so its
    members stream straight through with no staging. An unreadable member aborts (raises)."""
    if _is_zip(path):
        yield from _iter_zip_members(path)
    else:
        yield from _iter_tar_members(path, tmpdir)


def _iter_zip_members(path: Path):
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                try:
                    with zf.open(info) as fp:
                        digest, _ = _stream_digest(fp)
                except (RuntimeError, zipfile.BadZipFile, OSError) as e:
                    raise AssemblyError(
                        f"unreadable member {info.filename!r} in {path.name}: {e}"
                    ) from e
                yield (
                    info.filename,
                    tuple(info.date_time),  # verbatim (a zip already stores a DOS tuple)
                    info.file_size,
                    digest,
                    _ZipMemberSource(path, info.filename),
                )
    except zipfile.BadZipFile as e:
        raise AssemblyError(f"unreadable source archive {path.name}: {e}") from e


def _iter_tar_members(path: Path, tmpdir: Path):
    try:
        with tararchive.open_archive(path) as tf:
            for n, info in enumerate(tf):
                if not info.isfile():
                    continue
                fp = tf.extractfile(info)
                if fp is None:  # a "file" tarfile can't hand back a stream for
                    raise AssemblyError(
                        f"unreadable member {info.name!r} in {path.name}: no stream"
                    )
                staged = tmpdir / f"m{n}.part"
                digest = _stage_and_hash(fp, staged)
                yield (
                    info.name,
                    epoch_to_dostuple(info.mtime),
                    info.size,
                    digest,
                    _FileSource(staged),
                )
    except (tarfile.TarError, OSError) as e:
        raise AssemblyError(f"unreadable source archive {path.name}: {e}") from e


# ---------- placement, rewrites, conflict / dedup ---------- #


def _place(
    by_path: dict[str, _Planned],
    out_rel: str,
    date_time: tuple[int, int, int, int, int, int],
    size: int,
    digest: str,
    byte_src: _ByteSource,
    conflict: str,
    *,
    kind: str,
) -> None:
    """Insert a planned member, resolving a same-path collision: identical bytes dedup
    silently (the multi-part split re-delivered the same file); differing bytes fire the
    `conflict` policy — `error` (raise) is the only declared value, so anything else is
    treated as `error` too (fail loud rather than silently pick a winner)."""
    existing = by_path.get(out_rel)
    if existing is None:
        by_path[out_rel] = _Planned(out_rel, date_time, size, digest, byte_src)
        return
    if existing.digest == digest:
        return  # identical bytes across parts — dedup
    raise AssemblyError(
        f"conflict at {out_rel!r}: two {kind}s with different bytes "
        f"(blake3 {existing.digest[:12]} vs {digest[:12]}); conflict policy is {conflict!r}."
    )


def _apply_rewrites(relpath: str, rules: list[dict]) -> tuple[str, bool]:
    """Apply the declared restructure rules to a member path. A rule `{from, to}` matches when
    `from` equals `relpath` or globs it (`fnmatch`); `to` ending in `/` moves the member into
    that dir (basename appended), otherwise `to` is the literal new path. First matching rule
    wins; no rule → verbatim (the norm). Returns `(out_path, was_rewritten)`."""
    for rule in rules:
        frm = str(rule.get("from") or "")
        to = str(rule.get("to") or "")
        if not frm or not to:
            continue
        if relpath == frm or fnmatch(relpath, frm):
            out = to + relpath.rsplit("/", 1)[-1] if to.endswith("/") else to
            return out, True
    return relpath, False


def _derive_services(original_relpaths: list[str]) -> list[str]:
    """The distinct top-level dirs under the original members' common root — the export's
    service slices (`Mail`, `Calendar`, …). Mechanical from the member paths (there is no
    declared manifest); when the members share a single wrapper root (`Takeout/`), the service
    is the FIRST component beneath it, else the first path component itself."""
    if not original_relpaths:
        return []
    root = ziparchive.common_root(original_relpaths)
    services: list[str] = []
    for rel in original_relpaths:
        stripped = ziparchive.relpath(rel, root)
        head = stripped.split("/", 1)[0]
        if head and head not in services:
            services.append(head)
    return sorted(services)


# ============================================================================================
# THE WRITER CORE — a standalone, reusable deterministic zip64 writer (bytes-in, bundle-out).
#
# Knows NOTHING about source archives, overlays, sidecars, or any vendor: it takes an ordered
# series of `BundleMember`s (a member path + a re-openable byte stream + an mtime + an optional
# compression hint) plus an archive comment, and produces the deterministic bundle. The
# `assemble` frontend below is one caller; the planned `corpus pack` verb (spec §12.8 — folding
# thousands of standalone corpus artifacts into a handful of collection containers) is the
# other, feeding members named by record id with bytes streamed from the artifact store. Keep
# this core free of any "source is an archive" assumption.
# ============================================================================================


@dataclass(frozen=True)
class BundleMember:
    """One member for the writer core. `open_stream` is a re-openable byte source (called once,
    streamed in 1 MiB chunks); `date_time` is the zip DOS mtime 6-tuple (`epoch_to_dostuple`
    converts a POSIX epoch); `size` is the uncompressed byte count (the zip64 decision).
    `compression` overrides the extension-based routing: `store` | `zstd` | None (auto)."""

    path: str
    open_stream: Callable[[], AbstractContextManager[IO[bytes]]]
    date_time: tuple[int, int, int, int, int, int]
    size: int
    compression: str | None = None


def write_bundle(
    members: list[BundleMember], out_path: Path, *, level: int = DEFAULT_LEVEL, comment: str = ""
) -> int:
    """Write `members` into ONE deterministic zip64 bundle at `out_path`, returning its byte
    size. Members are written in SORTED path order (enforced here — the caller need not
    pre-sort), each streamed (1 MiB chunks) so a multi-GB member never loads whole, per-member
    zstd(`level`)/stored routing (extension-based, overridable per member), member mtimes
    copied, the archive `comment` stamped. Deterministic: `create_system` pinned to Unix and no
    wall-clock touches the output. Atomic: writes a temp sibling then `os.replace`, cleaning up
    the partial on any failure. Pure bytes-in/bundle-out — shared with the future `corpus pack`
    verb (see the writer-core banner)."""
    ordered = sorted(members, key=lambda m: m.path)
    partial = out_path.with_name(out_path.name + f".partial.{os.getpid()}")
    try:
        with zipfile.ZipFile(partial, "w", allowZip64=True) as zf:
            if comment:
                zf.comment = comment.encode("utf-8")
            for m in ordered:
                zi = zipfile.ZipInfo(m.path)
                zi.date_time = m.date_time
                zi.file_size = m.size
                zi.create_system = _CREATE_SYSTEM_UNIX
                if _member_stored(m):
                    zi.compress_type = zipfile.ZIP_STORED
                else:
                    zi.compress_type = zipfile.ZIP_ZSTANDARD
                    zi.compress_level = level  # per-member level (the ZipInfo default is None)
                force64 = m.size >= _ZIP64_LIMIT
                with m.open_stream() as src, zf.open(zi, "w", force_zip64=force64) as dst:
                    shutil.copyfileobj(src, dst, _CHUNK)
        os.replace(partial, out_path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return out_path.stat().st_size


def _member_stored(m: BundleMember) -> bool:
    """Whether a member is stored (uncompressed): an explicit `store`/`zstd` hint wins, else
    the extension-based `_is_stored` routing (already-compressed bytes → stored)."""
    if m.compression == "store":
        return True
    if m.compression == "zstd":
        return False
    return _is_stored(m.path)


def epoch_to_dostuple(epoch: float) -> tuple[int, int, int, int, int, int]:
    """A POSIX epoch → a zip DOS `date_time` 6-tuple, decomposed in **UTC** (not local time) so
    the stored timestamp is independent of the machine that wrote it. Floors below the DOS epoch
    (1980) as zip requires. Public — a writer-core caller (`pack`) converts artifact mtimes."""
    dt = datetime.fromtimestamp(int(epoch), UTC)
    year = max(dt.year, 1980)
    return (year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _is_stored(out_path: str) -> bool:
    base = out_path.rsplit("/", 1)[-1]
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    return ext in _ALREADY_COMPRESSED


# ---------- byte / hash helpers ---------- #


def _stream_digest(fp: IO[bytes]) -> tuple[str, int]:
    """blake3 + byte count of a member, streaming `fp` (never materialized whole)."""
    b3 = blake3.blake3()
    total = 0
    while chunk := fp.read(_CHUNK):
        b3.update(chunk)
        total += len(chunk)
    return b3.hexdigest(), total


def _stage_and_hash(fp: IO[bytes], dest: Path) -> str:
    """Stream a solid-stream (tar) member to `dest` while hashing it, in one pass — so the tgz
    is decompressed exactly once and the member is random-access for the sorted write pass."""
    b3 = blake3.blake3()
    with dest.open("wb") as out:
        while chunk := fp.read(_CHUNK):
            b3.update(chunk)
            out.write(chunk)
    return b3.hexdigest()


def _hash_file(path: Path) -> str:
    """Streaming blake3 of a whole file — the source archive's tombstone hash (its own
    content-address; the retired originals resolve to it in `source_parts`)."""
    with path.open("rb") as fp:
        return _stream_digest(fp)[0]


def _hash_and_size(path: Path) -> tuple[str, int]:
    with path.open("rb") as fp:
        return _stream_digest(fp)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _is_zip(path: Path) -> bool:
    """True when `path` is a raw zip (local-file-header magic). A tar/tgz is anything else this
    engine accepts — `tarfile` in `r|*` mode auto-detects gzip, so a `.tar` and a `.tgz` route
    the same. Reads only the first four bytes."""
    try:
        with path.open("rb") as fp:
            return fp.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def _mkdtemp(parent: Path) -> str:
    import tempfile

    return tempfile.mkdtemp(prefix=".assemble-", dir=str(parent))
