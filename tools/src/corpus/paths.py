"""Corpus path conventions.

A corpus root holds `records/` and `schema/` (the two TRACKED dirs) plus the untracked
`artifacts/`, `capture/`, `cache/`, `export/`. Records and artifacts are sharded by the
first two hex characters of the blake3 id, e.g. `records/a7/a7f3b2c1….md` and
`artifacts/a7/a7f3b2c1….pdf`.

`find_corpus_root` keys on the presence of both `records/` and `schema/`; an empty
`schema/` is a valid marker for a corpus that vendors no local schemas and relies on
the package's bundled universals. Precedence mirrors `ath.manifest.find_root` (Part I
§2.1: "$ATHENAEUM_ROOT overrides"): an explicit start wins, else `$ATHENAEUM_ROOT/corpus`
when the variable is set, else the walk up from cwd.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SHARD_LEN = 2

# The instance-root override and the instance's corpus directory. Both duplicate
# `ath.manifest` (`ROOT_ENV`, `Instance.corpus_root`) on purpose: the corpus layer
# never imports `ath` (the layers are read-only downstream of the config, never the
# other way — the same rule `corpus.assets` follows for the manifest filename).
ROOT_ENV = "ATHENAEUM_ROOT"
CORPUS_DIRNAME = "corpus"

# Minimum hex prefix accepted as a short-hash record reference. Four hex chars give
# 16^4 = 65,536 distinct prefixes — collisions in a corpus of a few thousand records
# are real but rare. When a prefix is ambiguous, `resolve_record` exits with the
# full collision list so the caller can lengthen on demand.
MIN_HASH_PREFIX = 4


def is_corpus_root(path: Path) -> bool:
    """True when `path` carries the two tracked marker dirs, `records/` + `schema/`."""
    return (path / "records").is_dir() and (path / "schema").is_dir()


def find_corpus_root(start: Path | None = None) -> Path:
    """The corpus root: `$ATHENAEUM_ROOT/corpus` when the variable is set and no
    `start` is given, else walk upward from `start` (default: cwd) until a directory
    containing both `records/` and `schema/` is found.

    An `$ATHENAEUM_ROOT` that names no corpus is a loud `FileNotFoundError`, never a
    silent fall-through to the walk — the operator said where the instance is."""
    env = os.environ.get(ROOT_ENV)
    if env and start is None:
        root = (Path(env) / CORPUS_DIRNAME).resolve()
        if is_corpus_root(root):
            return root
        raise FileNotFoundError(
            f"{ROOT_ENV}={env}: {root} is not a corpus root (looking for records/ + schema/)"
        )
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if is_corpus_root(candidate):
            return candidate
    raise FileNotFoundError(f"No corpus root found above {here} (looking for records/ + schema/)")


def shard(record_id: str) -> str:
    return record_id[:SHARD_LEN]


def record_path(corpus_root: Path, record_id: str) -> Path:
    return corpus_root / "records" / shard(record_id) / f"{record_id}.md"


def artifact_path(corpus_root: Path, record_id: str, extension: str) -> Path:
    ext = extension.lstrip(".")
    return corpus_root / "artifacts" / shard(record_id) / f"{record_id}.{ext}"


def cache_dir(corpus_root: Path) -> Path:
    """The corpus's derived-output scratch space, created if absent.

    Callers that need a *large* temporary — muxing a track out of a container, say — should
    place it here rather than in the system temp: it sits on the same filesystem as the
    artifacts it is derived from, and `corpus gc` already knows how to sweep it."""
    d = corpus_root / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(path: Path, text: str) -> Path:
    """Write `text` to `path` atomically: stage a sibling temp file then `os.replace`
    (atomic on POSIX within one filesystem). A crash mid-write leaves the original
    record intact rather than a truncated `.md`. Used by the write API (region save)."""
    ensure_parent(path)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def resolve_record(corpus_root: Path, target: str) -> tuple[str, Path]:
    """Resolve `target` to a `(record_id, record_file)` pair.

    Accepted forms:

    - Path to a record `.md` file — returned as-is; record_id is the stem.
    - 64-char lowercase hex — direct lookup at `records/<shard>/<id>.md`.
    - 4-63 char hex prefix — shard-scoped glob; resolves only if exactly one record
      matches. Multiple matches exit with a warning naming every collision so the
      caller can lengthen on demand.

    Exits the process with a clear message on no-match, ambiguous match, or invalid
    input. Callers don't need to handle these themselves.
    """
    candidate = Path(target)
    if candidate.is_file() and candidate.suffix == ".md":
        record_file = candidate.resolve()
        return record_file.stem, record_file

    if not target:
        sys.exit("empty target")

    record_id = target.lower()
    if not all(c in "0123456789abcdef" for c in record_id):
        sys.exit(f"target is neither a record path nor a hex hash: {target!r}")

    if len(record_id) == 64:
        record_file = record_path(corpus_root, record_id)
        if not record_file.is_file():
            sys.exit(f"no record at {record_file}")
        return record_id, record_file

    if len(record_id) < MIN_HASH_PREFIX:
        sys.exit(
            f"hash prefix too short: {target!r} ({len(record_id)} chars; "
            f"need ≥{MIN_HASH_PREFIX})"
        )

    shard_dir = corpus_root / "records" / shard(record_id)
    if not shard_dir.is_dir():
        sys.exit(f"no record matching prefix {target!r}")
    matches = sorted(shard_dir.glob(f"{record_id}*.md"))
    if not matches:
        sys.exit(f"no record matching prefix {target!r}")
    if len(matches) > 1:
        collision_list = "\n  ".join(m.stem for m in matches)
        sys.exit(
            f"WARNING: prefix {target!r} matches {len(matches)} records:\n  "
            f"{collision_list}\nUse a longer prefix or the full hash."
        )
    return matches[0].stem, matches[0]
