"""The normalization queue (spec §8.5).

External, untracked request/claim state that lets any actor request a
(re-)normalization pass for a record and await its outcome. The queue is **standing
demand, never a backlog** (§8.5, 3.1): an entry exists because some consumer wants a pass,
not because the record owes one. The queue **never writes records** — `touch[]` and body
are owned by ingest and the normalize pass; queue operations are read-only on records. State
lives under
`<root>/queue/` as per-id marker files:

    <id>.req      pending request          (idle → requested)
    <id>.claim    claimed by a loop session (requested → claimed; in flight)
    <id>.result   last terminal outcome     (completed | failed)

A claim is taken by an atomic `rename(.req → .claim)`, so concurrent drains
never double-claim a fresh request. A stale `.claim` (a dead loop session) is
reclaimable once its lease lapses — best-effort, since a duplicate normalization
pass is merely wasteful, not unsafe.

The marker layout is an implementation detail (spec §8.5 is layout-agnostic);
callers go through this module, never the files directly.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_PRUNE_DAYS",
    "QueueError",
    "complete",
    "drain",
    "enqueue",
    "entries",
    "fail",
    "prune",
    "queue_dir",
    "requeue",
    "state",
]

# A claim older than this (seconds) is reclaimable by `drain` — the owning loop
# session is presumed dead. 30 min comfortably exceeds any single normalize pass.
DEFAULT_LEASE_SECONDS = 1800

# A settled `.result` older than this (days) is prunable. A `.result` is
# coordination state for a requester's `await`, not history — the record's own
# `touch[]` is durable — so once this grace window passes, any awaiter is
# long done and the marker is spent. A week is generously beyond any await.
DEFAULT_PRUNE_DAYS = 7


class QueueError(RuntimeError):
    """A queue operation was invoked against an incompatible entry state."""


# ---------- paths ---------- #


def queue_dir(root: Path) -> Path:
    return root / "queue"


def _req(root: Path, rid: str) -> Path:
    return queue_dir(root) / f"{rid}.req"


def _claim(root: Path, rid: str) -> Path:
    return queue_dir(root) / f"{rid}.claim"


def _result(root: Path, rid: str) -> Path:
    return queue_dir(root) / f"{rid}.result"


# ---------- marker io ---------- #


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _write_json(path: Path, data: dict) -> None:
    """Write a marker atomically (temp sibling + os.replace), like records do."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def _parse_dt(value: object) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(value) if value else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _mtime(path: Path) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.UTC)


# ---------- request / claim / settle ---------- #


def enqueue(root: Path, rid: str, by: str | None = None) -> str:
    """Request a (re-)normalization pass for `rid`. Status-independent (§8.5) — the
    caller decides a record wants normalizing; the queue does not inspect it.

    Idempotent: a request that arrives while one is already pending or in flight
    joins it. Returns ``"requested"`` | ``"already-requested"`` | ``"in-flight"``.
    """
    if _claim(root, rid).exists():
        return "in-flight"
    if _req(root, rid).exists():
        return "already-requested"
    _write_json(_req(root, rid), {"id": rid, "requested_at": _now(), "requested_by": by})
    return "requested"


def drain(root: Path, by: str | None = None, lease: int = DEFAULT_LEASE_SECONDS) -> str | None:
    """Atomically claim the next pending request (FIFO by `requested_at`) and return
    its id, or ``None`` when the queue is empty — the loop's stop signal.

    The claim is lock-free: `rename(.req → .claim)` is atomic, so when two drains
    race for the same request exactly one wins and the loser moves on. Before
    giving up, a stale `.claim` (claimed longer ago than `lease`) is reclaimed.
    """
    qd = queue_dir(root)
    if not qd.is_dir():
        return None

    # Two passes: fresh requests first; if none claimable, reclaim stale claims and retry.
    for attempt in range(2):
        claimed = _try_claim_next(root, qd, by)
        if claimed is not None:
            return claimed
        if attempt == 0 and _reclaim_stale(root, qd, lease):
            continue
        break
    return None


def _try_claim_next(root: Path, qd: Path, by: str | None) -> str | None:
    def _ts(p: Path) -> str:
        return (_read_json(p) or {}).get("requested_at", "")

    for req_path in sorted(qd.glob("*.req"), key=_ts):
        rid = req_path.name[: -len(".req")]
        claim_path = _claim(root, rid)
        try:
            os.rename(req_path, claim_path)  # atomic claim — decides ownership
        except OSError:
            continue  # lost the race (or transient) — try the next request
        data = _read_json(claim_path) or {"id": rid}
        data["claimed_at"] = _now()
        data["claimed_by"] = by
        _write_json(claim_path, data)
        return rid
    return None


def _reclaim_stale(root: Path, qd: Path, lease: int) -> bool:
    """Return any claim older than `lease` to the pending pool. Best-effort."""
    now = datetime.datetime.now(datetime.UTC)
    reclaimed = False
    for claim_path in qd.glob("*.claim"):
        data = _read_json(claim_path) or {}
        claimed_at = data.get("claimed_at")
        try:
            when = datetime.datetime.fromisoformat(claimed_at) if claimed_at else None
        except (TypeError, ValueError):
            when = None
        if when is None:
            when = datetime.datetime.fromtimestamp(claim_path.stat().st_mtime, datetime.UTC)
        if (now - when).total_seconds() < lease:
            continue
        rid = claim_path.name[: -len(".claim")]
        try:
            os.rename(claim_path, _req(root, rid))  # atomic return-to-pending
            reclaimed = True
        except OSError:
            pass
    return reclaimed


def complete(root: Path, rid: str, by: str | None = None) -> None:
    """Close a claimed pass as completed. Raises QueueError if `rid` is not claimed."""
    if not _claim(root, rid).exists():
        raise QueueError(f"{rid[:12]} is not claimed")
    _write_json(
        _result(root, rid),
        {"id": rid, "outcome": "completed", "finished_at": _now(), "by": by},
    )
    _claim(root, rid).unlink(missing_ok=True)


def fail(root: Path, rid: str, reason: str | None = None, by: str | None = None) -> None:
    """Close a claimed pass as failed. Raises QueueError if `rid` is not claimed."""
    if not _claim(root, rid).exists():
        raise QueueError(f"{rid[:12]} is not claimed")
    _write_json(
        _result(root, rid),
        {"id": rid, "outcome": "failed", "reason": reason, "finished_at": _now(), "by": by},
    )
    _claim(root, rid).unlink(missing_ok=True)


def requeue(root: Path, rid: str) -> None:
    """Return a claimed pass to the pending pool (e.g. a loop shutting down cleanly).
    Atomic `rename(.claim → .req)`; raises QueueError if `rid` is not claimed."""
    try:
        os.rename(_claim(root, rid), _req(root, rid))
    except FileNotFoundError as e:
        raise QueueError(f"{rid[:12]} is not claimed") from e


# ---------- read ---------- #


def state(root: Path, rid: str) -> dict:
    """Current queue state for one record: ``state`` is ``requested`` | ``claimed`` |
    ``idle``, plus the entry's fields (and, when idle, the last ``result`` if any)."""
    if _claim(root, rid).exists():
        return {"state": "claimed", **(_read_json(_claim(root, rid)) or {})}
    if _req(root, rid).exists():
        return {"state": "requested", **(_read_json(_req(root, rid)) or {})}
    return {"state": "idle", "result": _read_json(_result(root, rid))}


def is_pending(st: dict) -> bool:
    """A queue state with a pass not yet settled (await keeps waiting on these)."""
    return st.get("state") in ("requested", "claimed")


def entries(root: Path) -> list[dict]:
    """All non-idle entries — claimed first, then requested. For listing/observability."""
    qd = queue_dir(root)
    if not qd.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(qd.glob("*.claim")):
        out.append({"state": "claimed", "id": p.name[: -len(".claim")], **(_read_json(p) or {})})
    for p in sorted(qd.glob("*.req")):
        out.append({"state": "requested", "id": p.name[: -len(".req")], **(_read_json(p) or {})})
    return out


# ---------- prune / gc ---------- #


def prune(root: Path, older_than_days: float = DEFAULT_PRUNE_DAYS) -> dict[str, list[str]]:
    """Remove settled `.result` markers (and orphaned `.tmp.*` write scratch) older
    than `older_than_days`. A `.result` is coordination state for a requester's
    `await`, not history (the record's `touch[]` is durable), so an aged one
    is spent. Only `.result`/`.tmp.*` are touched — live `.req`/`.claim` entries are
    never removed, so this never races an in-flight pass. Idempotent.

    `older_than_days=0` prunes every settled result now. Returns
    ``{"results": [ids], "temp": [names]}`` of what was removed.
    """
    qd = queue_dir(root)
    removed: dict[str, list[str]] = {"results": [], "temp": []}
    if not qd.is_dir():
        return removed
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=older_than_days)

    for result_path in qd.glob("*.result"):
        when = _parse_dt((_read_json(result_path) or {}).get("finished_at")) or _mtime(result_path)
        if when <= cutoff:
            result_path.unlink(missing_ok=True)
            removed["results"].append(result_path.name[: -len(".result")])

    for tmp_path in qd.glob("*.tmp.*"):  # crash-orphaned atomic-write scratch
        if _mtime(tmp_path) <= cutoff:
            tmp_path.unlink(missing_ok=True)
            removed["temp"].append(tmp_path.name)

    return removed
