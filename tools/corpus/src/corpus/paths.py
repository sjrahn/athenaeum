"""Corpus path conventions.

A corpus root holds `records/` and `schema/` (the two TRACKED dirs) plus the untracked
`artifacts/`, `capture/`, `cache/`, `export/`. Records and artifacts are sharded by the
first two hex characters of the blake3 id, e.g. `records/a7/a7f3b2c1….md` and
`artifacts/a7/a7f3b2c1….pdf`.

`find_corpus_root` keys on the presence of both `records/` and `schema/`; an empty
`schema/` is a valid marker for a corpus that vendors no local schemas and relies on
the package's bundled universals.
"""

from __future__ import annotations

import sys
from pathlib import Path

SHARD_LEN = 2

# Minimum hex prefix accepted as a short-hash record reference. Four hex chars give
# 16^4 = 65,536 distinct prefixes — collisions in a corpus of a few thousand records
# are real but rare. When a prefix is ambiguous, `resolve_record` exits with the
# full collision list so the caller can lengthen on demand.
MIN_HASH_PREFIX = 4


def find_corpus_root(start: Path | None = None) -> Path:
    """Walk upward from `start` (default: cwd) until a directory containing both
    `records/` and `schema/` is found. That's the corpus root."""
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "records").is_dir() and (candidate / "schema").is_dir():
            return candidate
    raise FileNotFoundError(f"No corpus root found above {here} (looking for records/ + schema/)")


def shard(record_id: str) -> str:
    return record_id[:SHARD_LEN]


def record_path(corpus_root: Path, record_id: str) -> Path:
    return corpus_root / "records" / shard(record_id) / f"{record_id}.md"


def artifact_path(corpus_root: Path, record_id: str, extension: str) -> Path:
    ext = extension.lstrip(".")
    return corpus_root / "artifacts" / shard(record_id) / f"{record_id}.{ext}"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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
