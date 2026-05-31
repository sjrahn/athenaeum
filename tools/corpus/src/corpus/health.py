"""Offline corpus health signals.

A read-only, fully-offline scan that surfaces what a corpus operator (or a curation
skill) wants to triage: how many records sit at each lifecycle status, which are
stuck, which carry unresolved issues, which are missing their bytes, and which fail
basic structural validity. `scan_all` returns a structured report; the `corpus
health` CLI renders it as JSON or a summary.

Generalized from the reference: the CarbonAi domain signals (vertical-coverage
keywords, keyword cross-referencing, classification cue-matching, v0.3 migration
residue, legacy PDF page-markers) are dropped; `missing_artifacts` routes through the
configured `ArtifactStore` instead of a hardcoded Azure lookup. Records are loaded as
`frontmatter.Post`s and read through the `records` accessors — no shadow parsing.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter

from . import records, touches

_REQUIRED_KEYS = ("id", "description", "status", "touch")
_VALID_STATUSES = {"stub", "draft", "normalized"}


@dataclass
class RecordRef:
    """A loaded record: its path plus the parsed `frontmatter.Post` (with the unified
    `_artifact` / `_origins` / `_issues` metadata view from `records.load`)."""

    path: Path
    post: frontmatter.Post

    @property
    def record_id(self) -> str:
        return str(self.post.metadata.get("id") or self.path.stem)


def load_all_records(corpus_root: Path) -> list[RecordRef]:
    """Load every record under `records/` in one glob pass. Unparseable records are
    skipped (parse-tolerantly)."""
    out: list[RecordRef] = []
    for f in sorted((corpus_root / "records").glob("*/*.md")):
        try:
            out.append(RecordRef(path=f, post=records.load(f)))
        except Exception:
            continue
    return out


def build_uri_index(refs: list[RecordRef]) -> dict[str, str]:
    """Map canonical origin URI → owning record id, from already-loaded refs (the
    in-memory complement to `records.build_uri_index`, which re-reads from disk)."""
    from . import urls as _urls

    index: dict[str, str] = {}
    for r in refs:
        for uri in records.iter_origin_uris(r.post):
            try:
                key = _urls.normalize(uri)
            except Exception:
                continue
            if key:
                index[key] = r.record_id
    return index


# ---------- signals ---------- #


def records_by_status(refs: list[RecordRef]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for r in refs:
        out[str(r.post.metadata.get("status", "unknown"))] += 1
    return dict(out)


def records_by_mime(refs: list[RecordRef]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for r in refs:
        out[records.media_type_for(r.post) or "unknown"] += 1
    return dict(out)


def pending_normalize(refs: list[RecordRef], *, limit: int = 50) -> list[dict[str, Any]]:
    """Records in `draft` status (awaiting normalize). Sorted by id — the touch chain
    carries no timestamps, so recency isn't recoverable from the record alone."""
    drafts = sorted(
        (r for r in refs if r.post.metadata.get("status") == "draft"), key=lambda r: r.record_id
    )
    return [
        {
            "id": r.record_id,
            "title": records.title_for(r.post),
            "media_type": records.media_type_for(r.post),
        }
        for r in drafts[:limit]
    ]


def stuck_at_stub(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Records still at `stub`. `supported_draft` is True when a drafter is registered
    for the record's mime — i.e. `corpus draft` would advance it."""
    from . import draft as draft_pkg
    from . import schemas

    out: list[dict[str, Any]] = []
    for r in refs:
        if r.post.metadata.get("status") != "stub":
            continue
        mime = records.media_type_for(r.post)
        schema_id = schemas.mime_schema_id_for(corpus_root, mime) if mime else None
        supported = bool(schema_id and draft_pkg.get_drafter(schema_id))
        out.append(
            {
                "id": r.record_id,
                "title": records.title_for(r.post),
                "media_type": mime,
                "supported_draft": supported,
            }
        )
    return out[:limit]


def unresolved_issues(
    refs: list[RecordRef], *, limit: int = 50
) -> dict[str, list[dict[str, Any]]]:
    """Open `<!--issue-->` blocks grouped by severity (`blocking|warning|info`)."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in refs:
        for issue in records.iter_issue_blocks(r.post):
            fields = issue.get("fields") or {}
            if str(fields.get("resolution", "open")).lower() != "open":
                continue
            severity = str(fields.get("severity") or "unknown")
            id_ = issue.get("id") or ""
            subtype = issue.get("subtype")
            grouped[severity].append(
                {
                    "id": r.record_id,
                    "type": f"{id_}/{subtype}" if subtype else id_,
                    "detector": fields.get("detector"),
                    "address": fields.get("address"),
                }
            )
    return {sev: items[:limit] for sev, items in grouped.items()}


def missing_artifacts(
    refs: list[RecordRef],
    corpus_root: Path,
    *,
    limit: int = 50,
    skip_remote_check: bool = False,
) -> list[dict[str, Any]]:
    """Records whose bytes are absent locally. `category`: `not_hydrated` (present in
    the configured remote store), `lost` (absent there too), or `unknown` (remote not
    checked). Routes through the `ArtifactStore`, so it works on any backend."""
    from . import mime as mime_mod
    from . import paths
    from .store import get_store

    store = get_store(corpus_root)
    remote: set[str] | None = None
    if not skip_remote_check:
        try:
            remote = store.list_remote()
        except Exception:
            remote = None

    out: list[dict[str, Any]] = []
    for r in refs:
        mime = records.media_type_for(r.post)
        if not mime:
            continue
        ext = mime_mod.extension_for(mime)
        if not ext or ext == "bin":
            continue
        if store.is_local(r.record_id, ext):
            continue
        blob = f"{paths.shard(r.record_id)}/{r.record_id}.{ext.lstrip('.')}"
        if remote is None:
            category = "unknown"
        elif blob in remote:
            category = "not_hydrated"
        else:
            category = "lost"
        expected = paths.artifact_path(corpus_root, r.record_id, ext).relative_to(corpus_root)
        out.append(
            {
                "id": r.record_id,
                "title": records.title_for(r.post),
                "media_type": mime,
                "expected_path": str(expected),
                "category": category,
            }
        )
    return out[:limit]


def empty_description_normalized(refs: list[RecordRef], *, limit: int = 50) -> list[dict[str, Any]]:
    """Normalized records with an empty `description` (the one-line summary should be
    populated by normalize)."""
    out: list[dict[str, Any]] = []
    for r in refs:
        if r.post.metadata.get("status") != "normalized":
            continue
        if str(r.post.metadata.get("description") or "").strip():
            continue
        out.append({"id": r.record_id, "title": records.title_for(r.post)})
    return out[:limit]


def validity_violations(refs: list[RecordRef], *, limit: int = 50) -> list[dict[str, Any]]:
    """A quick structural sanity check (a subset of `corpus lint`): required keys,
    id==filename, valid status, non-empty touch, artifact block past stub, ≥1 origin."""
    out: list[dict[str, Any]] = []
    for r in refs:
        m = r.post.metadata
        problems: list[str] = []
        for k in _REQUIRED_KEYS:
            if k not in m:
                problems.append(f"missing required key: {k}")
        rid = m.get("id")
        if rid and rid != r.path.stem:
            problems.append(f"id != filename ({rid} vs {r.path.stem})")
        if m.get("status") not in _VALID_STATUSES:
            problems.append(f"invalid status: {m.get('status')!r}")
        if not touches.touch_list(r.post):
            problems.append("touch[] is empty")
        artifact = m.get("_artifact")
        past_stub = m.get("status") in ("draft", "normalized")
        if past_stub and (not artifact or not artifact.get("mime")):
            problems.append("missing <!--artifact--> block (mime unset)")
        if not (m.get("_origins") or []):
            problems.append("no <!--origin--> blocks")
        if problems:
            out.append(
                {"id": r.record_id, "title": records.title_for(r.post), "problems": problems}
            )
    return out[:limit]


# ---------- aggregator ---------- #


SIGNAL_NAMES = (
    "records_by_status",
    "records_by_mime",
    "pending_normalize",
    "stuck_at_stub",
    "unresolved_issues",
    "missing_artifacts",
    "empty_description_normalized",
    "validity_violations",
)


def scan_all(
    corpus_root: Path,
    *,
    limit: int = 50,
    only: list[str] | None = None,
    skip_remote_check: bool = False,
) -> dict[str, Any]:
    """Run every selected signal and return a structured report."""
    refs = load_all_records(corpus_root)
    selected = set(only) if only else set(SIGNAL_NAMES)

    report: dict[str, Any] = {"spec_version": "1.0", "total_records": len(refs)}
    if "records_by_status" in selected:
        report["records_by_status"] = records_by_status(refs)
    if "records_by_mime" in selected:
        report["records_by_mime"] = records_by_mime(refs)
    if "pending_normalize" in selected:
        report["pending_normalize"] = pending_normalize(refs, limit=limit)
    if "stuck_at_stub" in selected:
        report["stuck_at_stub"] = stuck_at_stub(refs, corpus_root, limit=limit)
    if "unresolved_issues" in selected:
        report["unresolved_issues"] = unresolved_issues(refs, limit=limit)
    if "missing_artifacts" in selected:
        report["missing_artifacts"] = missing_artifacts(
            refs, corpus_root, limit=limit, skip_remote_check=skip_remote_check
        )
    if "empty_description_normalized" in selected:
        report["empty_description_normalized"] = empty_description_normalized(refs, limit=limit)
    if "validity_violations" in selected:
        report["validity_violations"] = validity_violations(refs, limit=limit)
    return report
