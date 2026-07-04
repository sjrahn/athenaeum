"""Derived-data hygiene (`corpus gc`) + deliberate record removal (`corpus rm` /
`corpus forget-origin`).

Two distinct risk classes, kept apart on purpose (the proposal's clean split):

- `sweep` (`corpus gc`) — an age-gated, idempotent prune of **regenerable** data only,
  **never** a tracked record: the resolver `cache/`, leftover `capture/` staging, orphan
  artifacts (bytes under `artifacts/` with no owning record), and `export/` bundles.
  Generalizes the pattern `queue --prune` (a GC of the queue's coordination markers)
  to the other derived dirs. Safe on a cron tick.
- `remove_records` (`corpus rm`) — a deliberate removal of one tracked **record**: its
  `.md`, its content-addressed artifact, and now-empty shard dirs. Ref-checked (refuses
  when another record cites the target, unless forced) and reproducibility-warned (the
  artifact is gitignored, so dropping it is undoable only by re-capture). It does **not**
  touch the resolver cache — cache is keyed by functional-URI hash, not the record's
  artifact hash, so there is no clean per-record cache slice to delete; `gc` reclaims it.
- `forget_origin` (`corpus forget-origin`) — drop a single origin **alias** from a record
  without removing the record (the many-to-one provenance case: a wrong URL alias).

All functions are parse-tolerant and operate through the existing `records` / `paths`
accessors — no shadow parsing of the on-disk layout.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from . import functional_uri, paths, records, touches

__all__ = [
    "DEFAULT_GC_DAYS",
    "GC_CATEGORIES",
    "ForgetResult",
    "Referrer",
    "RemovalPlan",
    "RemovalResult",
    "SweepItem",
    "SweepResult",
    "forget_origin",
    "inbound_references",
    "plan_removal",
    "records_holding_url",
    "remove_records",
    "sweep",
]

# A derived file older than this (days) is prunable by `gc`. Mirrors the queue's
# `DEFAULT_PRUNE_DAYS` grace window — generous beyond any in-flight capture/draft, so the
# sweep never races a fresh artifact written just before its record (ingest writes the
# artifact, then the `.md`). `older_than_days=0` prunes everything now.
DEFAULT_GC_DAYS = 7.0

# The regenerable dirs `gc` may sweep. `cache`/`staging`/`export` are pruned by file age;
# `orphans` is the inverse of health's `missing_artifacts` (artifacts → no record).
GC_CATEGORIES: tuple[str, ...] = ("cache", "staging", "orphans", "export")

_CATEGORY_DIRS = {"cache": "cache", "staging": "capture", "export": "export"}


# ---------- gc / sweep ---------- #


@dataclass
class SweepItem:
    """One regenerable file the sweep removed (or, on a dry run, would remove)."""

    category: str
    path: str  # relative to corpus_root
    size: int


@dataclass
class SweepResult:
    dry_run: bool
    older_than_days: float
    categories: tuple[str, ...]
    items: list[SweepItem] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(i.size for i in self.items)

    def by_category(self) -> dict[str, list[SweepItem]]:
        out: dict[str, list[SweepItem]] = {c: [] for c in self.categories}
        for item in self.items:
            out.setdefault(item.category, []).append(item)
        return out


def _validate_include(include: list[str] | None) -> tuple[str, ...]:
    if not include:
        return GC_CATEGORIES
    cats = tuple(c.strip() for c in include if c.strip())
    unknown = [c for c in cats if c not in GC_CATEGORIES]
    if unknown:
        raise ValueError(
            f"unknown gc category: {', '.join(unknown)} "
            f"(choose from {', '.join(GC_CATEGORIES)})"
        )
    return cats


def _cutoff(older_than_days: float, now: datetime.datetime | None) -> float:
    """Return the POSIX-timestamp cutoff; files with mtime <= cutoff are prunable."""
    now = now or datetime.datetime.now(datetime.UTC)
    return (now - datetime.timedelta(days=older_than_days)).timestamp()


def _prune_empty_dir(d: Path) -> None:
    """Remove `d` if it is now an empty directory. Best-effort."""
    try:
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass


def _sweep_dir(
    corpus_root: Path,
    target: Path,
    category: str,
    cutoff: float,
    dry_run: bool,
    out: list[SweepItem],
) -> None:
    """Prune every file under `target` older than `cutoff` (recursively). The dir's
    whole contents are regenerable, so the only gate is age."""
    if not target.is_dir():
        return
    empties: set[Path] = set()
    for f in sorted(target.rglob("*")):
        if not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_mtime > cutoff:
            continue
        out.append(SweepItem(category, str(f.relative_to(corpus_root)), st.st_size))
        if not dry_run:
            f.unlink(missing_ok=True)
            empties.add(f.parent)
    # Tidy now-empty shard dirs left behind (deepest first), but keep `target` itself.
    for d in sorted(empties, key=lambda p: len(p.parts), reverse=True):
        if d != target:
            _prune_empty_dir(d)


def _sweep_orphans(
    corpus_root: Path, cutoff: float, dry_run: bool, out: list[SweepItem]
) -> None:
    """Prune artifacts with no owning record — the inverse of health's `missing_artifacts`
    (records → no artifact). An artifact is content-addressed at `artifacts/<shard>/<id>.<ext>`,
    so it is an orphan iff `records/<shard>/<id>.md` does not exist (ingest is the only writer
    of `artifacts/`; embeds/derived slices never land there). Age-gated, so the brief window
    in ingest between writing the artifact and its record never trips it."""
    artifacts_root = corpus_root / "artifacts"
    if not artifacts_root.is_dir():
        return
    known = {p.stem for p in records.iter_record_paths(corpus_root)}
    empties: set[Path] = set()
    for shard_dir in sorted(artifacts_root.iterdir()):
        if not shard_dir.is_dir() or len(shard_dir.name) != paths.SHARD_LEN:
            continue
        for f in sorted(shard_dir.iterdir()):
            if not f.is_file():
                continue
            record_id = f.name.split(".", 1)[0]
            if record_id in known:
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime > cutoff:
                continue
            out.append(SweepItem("orphans", str(f.relative_to(corpus_root)), st.st_size))
            if not dry_run:
                f.unlink(missing_ok=True)
                empties.add(shard_dir)
    for d in empties:
        _prune_empty_dir(d)


def sweep(
    corpus_root: Path,
    *,
    older_than_days: float = DEFAULT_GC_DAYS,
    include: list[str] | None = None,
    dry_run: bool = True,
    now: datetime.datetime | None = None,
) -> SweepResult:
    """Prune regenerable data older than `older_than_days`. Idempotent.

    `include` restricts to a subset of `GC_CATEGORIES` (default: all). `dry_run=True`
    (the default) computes the plan without deleting. Never touches a tracked record,
    a live queue entry, or any artifact that still has an owning record.
    """
    cats = _validate_include(include)
    cutoff = _cutoff(older_than_days, now)
    out: list[SweepItem] = []
    for cat in cats:
        if cat == "orphans":
            _sweep_orphans(corpus_root, cutoff, dry_run, out)
        else:
            _sweep_dir(corpus_root, corpus_root / _CATEGORY_DIRS[cat], cat, cutoff, dry_run, out)
    return SweepResult(dry_run=dry_run, older_than_days=older_than_days, categories=cats, items=out)


# ---------- rm / record removal ---------- #


@dataclass
class Referrer:
    """Another record that cites the one being removed (a would-be dangling pointer)."""

    record_id: str
    via: str  # e.g. "reference/manual"
    pointer: str  # the source_uri / source_url value


@dataclass
class RemovalPlan:
    record_id: str
    exists: bool
    record_path: str | None  # relative to corpus_root
    artifact_path: str | None  # relative to corpus_root
    artifact_size: int
    referrers: list[Referrer] = field(default_factory=list)
    # Promoted member records this record is a CONTAINER for (spec §12.8, fourth guard):
    # removing it strands their bytes. Named, and refused without --force.
    contained_promoted: list[str] = field(default_factory=list)


@dataclass
class RemovalResult:
    dry_run: bool
    keep_artifact: bool
    force: bool
    plans: list[RemovalPlan] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # ids removed (or, dry-run, would remove)
    blocked: list[str] = field(default_factory=list)  # refused: referenced + not forced


def _corpus_uri_id(value: object) -> str | None:
    """Extract the record id from a tier-3 `source_uri: corpus://<id>[?params]` via the
    shared functional-URI parser (validates the 64-hex hash; a malformed pointer → None)."""
    s = str(value or "").strip()
    if not s.startswith("corpus://"):
        return None
    try:
        return functional_uri.parse(s).hash
    except ValueError:
        return None


def inbound_references(
    corpus_root: Path, targets: set[str], *, index: dict[str, str] | None = None
) -> dict[str, list[Referrer]]:
    """Map each target record id → the records that cite it via a `reference` block.

    Covers both citation tiers: a tier-3 `source_uri: corpus://<id>` (direct), and a tier-2
    `source_url` that currently resolves to a target (`find_by_uri`). A record citing itself
    is not a dangling pointer, so it is skipped. O(N) scan — fine at curation cadence.
    """
    if not targets:
        return {}
    if index is None:
        index = records.build_uri_index(corpus_root)
    out: dict[str, list[Referrer]] = {t: [] for t in targets}
    for md, post in records.load_all(corpus_root):
        rid = str(post.metadata.get("id") or md.stem)
        if rid in targets:
            continue
        for ref in records.iter_reference_blocks(post):
            fields = ref.get("fields") or {}
            via = f"reference/{ref.get('subtype')}" if ref.get("subtype") else "reference"
            tid = _corpus_uri_id(fields.get("source_uri"))
            if tid and tid in targets:
                out[tid].append(Referrer(rid, via, str(fields.get("source_uri"))))
                continue
            url = fields.get("source_url")
            if url:
                owner = records.find_by_uri(str(url), corpus_root=corpus_root, index=index)
                if owner in targets:
                    out[owner].append(Referrer(rid, via, str(url)))
    return out


def _contained_promoted(corpus_root: Path, record_id: str) -> list[str]:
    """Ids of promoted member records this record is a **container** for — existing records
    whose id is one of this record's declared embed members (spec §2, §12.8). Removing the
    container strands their bytes (they have no `artifacts/` entry of their own), so `rm`
    names them and refuses without `--force`. Parse-tolerant: an unreadable target contributes
    nothing rather than crashing the plan."""
    from . import containment

    rpath = paths.record_path(corpus_root, record_id)
    if not rpath.is_file():
        return []
    try:
        post = records.load(rpath)
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for member_hex in containment.member_hashes(post):
        if member_hex == record_id or member_hex in seen:
            continue
        seen.add(member_hex)
        if paths.record_path(corpus_root, member_hex).is_file():
            out.append(member_hex)
    return out


def _find_artifact(corpus_root: Path, record_id: str) -> tuple[Path | None, int]:
    """Return the content-addressed artifact path + size for `record_id`, or (None, 0)."""
    shard_dir = corpus_root / "artifacts" / paths.shard(record_id)
    if shard_dir.is_dir():
        for f in sorted(shard_dir.iterdir()):
            if f.is_file() and f.name.split(".", 1)[0] == record_id:
                try:
                    return f, f.stat().st_size
                except OSError:
                    return f, 0
    return None, 0


def plan_removal(
    corpus_root: Path, ids: list[str], *, index: dict[str, str] | None = None
) -> list[RemovalPlan]:
    """Compute, without deleting, what removing each `id` entails: its record/artifact
    paths + sizes and the records that would be left citing it."""
    inbound = inbound_references(corpus_root, set(ids), index=index)
    plans: list[RemovalPlan] = []
    for rid in ids:
        rpath = paths.record_path(corpus_root, rid)
        exists = rpath.is_file()
        apath, asize = _find_artifact(corpus_root, rid)
        plans.append(
            RemovalPlan(
                record_id=rid,
                exists=exists,
                record_path=str(rpath.relative_to(corpus_root)) if exists else None,
                artifact_path=str(apath.relative_to(corpus_root)) if apath else None,
                artifact_size=asize,
                referrers=inbound.get(rid, []),
                contained_promoted=_contained_promoted(corpus_root, rid),
            )
        )
    return plans


def remove_records(
    corpus_root: Path,
    ids: list[str],
    *,
    keep_artifact: bool = False,
    force: bool = False,
    execute: bool = False,
    index: dict[str, str] | None = None,
) -> RemovalResult:
    """Remove one or more records: the `.md`, the content-addressed artifact (unless
    `keep_artifact`), and now-empty shard dirs. Records cited by another record are
    refused (reported in `blocked`) unless `force`. `execute=False` (the default) is a
    dry run — it computes the same plan and `removed`/`blocked` split but deletes nothing.
    The resolver cache is intentionally left alone (see module docstring)."""
    plans = plan_removal(corpus_root, ids, index=index)
    removed: list[str] = []
    blocked: list[str] = []
    for plan in plans:
        if not plan.exists:
            continue
        # Refuse a cited record (dangling referrer) or a container of promoted members
        # (stranded bytes, spec §12.8) unless forced.
        if (plan.referrers or plan.contained_promoted) and not force:
            blocked.append(plan.record_id)
            continue
        if execute:
            rpath = paths.record_path(corpus_root, plan.record_id)
            rpath.unlink(missing_ok=True)
            _prune_empty_dir(rpath.parent)
            if not keep_artifact and plan.artifact_path:
                apath = corpus_root / plan.artifact_path
                apath.unlink(missing_ok=True)
                _prune_empty_dir(apath.parent)
        removed.append(plan.record_id)
    return RemovalResult(
        dry_run=not execute,
        keep_artifact=keep_artifact,
        force=force,
        plans=plans,
        removed=removed,
        blocked=blocked,
    )


def records_holding_url(corpus_root: Path, url: str) -> list[str]:
    """Ids of every record whose origin URIs include `url` (by identity key). Usually one,
    but supersession debris (a `--force` re-capture) can leave several. The set `capture
    --force --replace` retires."""
    keyer = records.identity_keyer(corpus_root)

    def _key(u: str) -> str:
        try:
            return keyer(u)
        except Exception:
            return u

    target = _key(url)
    out: list[str] = []
    for md, post in records.load_all(corpus_root):
        rid = str(post.metadata.get("id") or md.stem)
        for uri in records.iter_origin_uris(post):
            if _key(uri) == target:
                out.append(rid)
                break
    return out


# ---------- forget-origin / alias surgery ---------- #


@dataclass
class ForgetResult:
    record_id: str
    uri: str
    dropped: bool
    remaining: int
    reason: str | None  # None | "not_present" | "last_origin"
    dry_run: bool


def forget_origin(
    corpus_root: Path, record_id: str, uri: str, *, execute: bool = True
) -> ForgetResult:
    """Drop the origin alias `uri` from `record_id` without removing the record.

    Matches by identity key (the host's `url_equivalent` rules), so a query-noise / `/page-1`
    spelling of the alias still matches. Refuses (`reason="last_origin"`) if `uri` is the
    record's only origin — that's an `rm`, not a forget. No-op (`reason="not_present"`) if the
    uri isn't among the record's origins. An origin block whose every uri was forgotten is
    dropped entirely.
    """
    keyer = records.identity_keyer(corpus_root)

    def key(u: str) -> str:
        try:
            return keyer(u)
        except Exception:
            return u

    target_key = key(uri)
    rpath = paths.record_path(corpus_root, record_id)
    post = records.load(rpath)
    origins = post.metadata.get("_origins") or []

    all_uris: list[str] = []
    for blk in origins:
        u = (blk.get("fields") or {}).get("uri")
        lst = u if isinstance(u, list) else ([u] if u else [])
        all_uris.extend(str(x) for x in lst if x)

    matches = [u for u in all_uris if key(u) == target_key]
    if not matches:
        return ForgetResult(record_id, uri, False, len(all_uris), "not_present", not execute)
    remaining = [u for u in all_uris if key(u) != target_key]
    if not remaining:
        return ForgetResult(record_id, uri, False, len(all_uris), "last_origin", not execute)

    if execute:
        new_origins: list[dict] = []
        for blk in origins:
            fields = blk.get("fields") or {}
            u = fields.get("uri")
            lst = u if isinstance(u, list) else ([u] if u else [])
            kept = [str(x) for x in lst if x and key(str(x)) != target_key]
            if not kept:
                continue  # the block's only uri(s) were forgotten — drop the block
            fields["uri"] = kept[0] if len(kept) == 1 else kept
            blk["fields"] = fields
            new_origins.append(blk)
        post.metadata["_origins"] = new_origins
        touches.record_touch(post, touches.script_identifier("forget-origin"))
        records.dump(post, rpath)

    return ForgetResult(record_id, uri, True, len(remaining), None, not execute)
