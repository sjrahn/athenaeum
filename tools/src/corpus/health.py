"""Offline corpus health signals.

A read-only, fully-offline scan that surfaces what a corpus operator (or a curation
skill) wants to triage: how records sit across the derived layers (spec §4.1 —
formed / rendered / proxy, plus the authored vouch), which carry unresolved issues,
which are missing their bytes, and which fail basic structural validity. `scan_all`
returns a structured report; the `corpus health` CLI renders it as JSON or a summary.

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

_REQUIRED_KEYS = ("id", "description", "touch")


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
    """Load every record under `records/`. Unparseable records are skipped (tolerantly).
    Shares the one discovery path in `records.load_all`."""
    return [RecordRef(path=md, post=post) for md, post in records.load_all(corpus_root)]


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


def layer_presence(refs: list[RecordRef]) -> dict[str, int]:
    """Layer-presence census (spec §4.1, §12.19 — succeeding the 3.0 status census): how the
    fleet sits across the derived-state enum, plus the orthogonal authored vouch and a
    transitional legacy-status count. `rendered` is `derived_state == "rendered"` — a stored
    rendering with no governing form, the grandfathered population (§12.18 step 3). The queue
    is standing demand, not backlog (§8.5), so this reports layer presence only — not how many
    records "need" a pass."""
    formed = rendered = proxy = authored = legacy_status = 0
    for r in refs:
        state = records.derived_state(r.post)
        if state == "formed":
            formed += 1
        elif state == "rendered":
            rendered += 1
        else:
            proxy += 1
        if records.is_authored(r.post):
            authored += 1
        if "status" in r.post.metadata:
            legacy_status += 1
    return {
        "formed": formed,
        "rendered": rendered,
        "proxy": proxy,
        "authored": authored,
        "legacy_status": legacy_status,
    }


def records_by_mime(refs: list[RecordRef]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for r in refs:
        out[records.media_type_for(r.post) or "unknown"] += 1
    return dict(out)


def unshaped(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Records at the `proxy` derived state (spec §4.1 — no stored rendering, not formed).
    `shapable` is True when the record's origin declares a form with a registered mechanical
    shaper (`corpus shape` would advance it) — the 3.1 successor of the 2.x `stuck_at_stub`
    "supported_draft" signal, re-keyed from the retired draft-strategy registry to the shape
    registry (spec §12.5.0). A `proxy` record with `shapable: false` is not necessarily stuck
    — most of the population is formless-permanently by design (§7.8) and correctly so."""
    from . import shape as shape_pkg

    out: list[dict[str, Any]] = []
    for r in refs:
        if records.derived_state(r.post) != "proxy":
            continue
        resolved = shape_pkg.form_for_record(r.post, corpus_root)
        shapable = bool(
            resolved
            and (shape_pkg.get_shaper(resolved[0]) or shape_pkg.get_shaper(resolved[1]))
        )
        out.append(
            {
                "id": r.record_id,
                "title": records.title_for(r.post),
                "media_type": records.media_type_for(r.post),
                "shapable": shapable,
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
    """Records **unresolvable by any route** (spec §12.17): no standalone file AND not
    resolvable through a container. A promoted record (bytes resident inside its container,
    no `artifacts/` entry) is NOT missing — it resolves via the member index (§2/§12.9), so it
    is skipped here. For a genuinely absent standalone, `category`: `not_hydrated` (present in
    the configured remote store), `lost` (absent there too), or `unknown` (remote not
    checked). Cheap — an index lookup, never byte streaming. Routes through the `ArtifactStore`,
    so it works on any backend."""
    from . import containment, paths
    from . import mime as mime_mod
    from .store import get_store

    store = get_store(corpus_root)
    # A record whose id is any other record's declared embed member is container-resolvable
    # (spec §2). Built from the already-loaded refs — an index lookup, no byte streaming.
    container_resolvable: set[str] = set()
    for r in refs:
        container_resolvable.update(containment.member_hashes(r.post))

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
        # `extension_for` falls back to "bin" for an unknown MIME; the artifact was stored
        # with that same fallback at ingest, so a record whose bytes are genuinely lost is
        # still checkable — don't skip it just because its MIME has no canonical extension.
        ext = mime_mod.extension_for(mime)
        if store.is_local(r.record_id, ext):
            continue
        if r.record_id in container_resolvable:
            continue  # no standalone file, but resolvable through its container (§12.9)
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


def formed_unauthored(refs: list[RecordRef], *, limit: int = 50) -> list[dict[str, Any]]:
    """Formed records (a form section governs the content zone, spec §4.1) whose vouch isn't
    written yet — the interpretive half of the normalize pass (title/description) still
    outstanding. Succeeds the 3.0 `empty_description_normalized` signal, which conflated
    formed+authored under one `status: normalized` flag; formed and authored are now
    orthogonal, so this reports specifically the formed-but-not-authored gap."""
    out: list[dict[str, Any]] = []
    for r in refs:
        if records.derived_state(r.post) != "formed" or records.is_authored(r.post):
            continue
        out.append({"id": r.record_id, "title": records.title_for(r.post)})
    return out[:limit]


def validity_violations(refs: list[RecordRef], *, limit: int = 50) -> list[dict[str, Any]]:
    """A quick structural sanity check (a subset of `corpus lint`): required keys,
    id==filename, non-empty touch, artifact block present, ≥1 origin.

    *(3.1)* No more status validity check (the field is retired, §4.1) and no more
    past-stub gate on the artifact-block check: attestation — including the artifact block —
    is the universal baseline written at ingest (§4.1's "attested | always" row), so every
    record is expected to carry one from birth, not only "past" some lifecycle marker."""
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
        if not touches.touch_list(r.post):
            problems.append("touch[] is empty")
        artifact = m.get("_artifact")
        if not artifact or not artifact.get("mime"):
            problems.append("missing <!--artifact--> block (mime unset)")
        if not (m.get("_origins") or []):
            problems.append("no <!--origin--> blocks")
        if problems:
            out.append(
                {"id": r.record_id, "title": records.title_for(r.post), "problems": problems}
            )
    return out[:limit]


def canonical_duplicate_clusters(refs: list[RecordRef], *, limit: int = 50) -> list[dict[str, Any]]:
    """Records that share a content identity (same `canonical:` hash AND the same embed
    set) yet live as separate records — the same content reached by different URLs that
    wasn't collapsed into one record. The draft step auto-merges these going forward
    (folding the duplicate's URL into the original); this surfaces any that predate that
    feature or slipped through. Each cluster lists its member ids for an operator to
    merge. Undrafted stubs (no `canonical:`) are excluded — they aren't dedup-able yet."""
    clusters: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    for r in refs:
        key = records.content_key(r.post)
        if key is not None:
            clusters[key].append(r.record_id)
    out = [
        {"canonical": canonical, "count": len(ids), "ids": sorted(ids)}
        for (canonical, _embeds), ids in clusters.items()
        if len(ids) > 1
    ]
    return out[:limit]


# ---------- aggregator ---------- #


SIGNAL_NAMES = (
    "layer_presence",
    "records_by_mime",
    "unshaped",
    "unresolved_issues",
    "missing_artifacts",
    "formed_unauthored",
    "validity_violations",
    "canonical_duplicate_clusters",
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
    if "layer_presence" in selected:
        report["layer_presence"] = layer_presence(refs)
    if "records_by_mime" in selected:
        report["records_by_mime"] = records_by_mime(refs)
    if "unshaped" in selected:
        report["unshaped"] = unshaped(refs, corpus_root, limit=limit)
    if "unresolved_issues" in selected:
        report["unresolved_issues"] = unresolved_issues(refs, limit=limit)
    if "missing_artifacts" in selected:
        report["missing_artifacts"] = missing_artifacts(
            refs, corpus_root, limit=limit, skip_remote_check=skip_remote_check
        )
    if "formed_unauthored" in selected:
        report["formed_unauthored"] = formed_unauthored(refs, limit=limit)
    if "validity_violations" in selected:
        report["validity_violations"] = validity_violations(refs, limit=limit)
    if "canonical_duplicate_clusters" in selected:
        report["canonical_duplicate_clusters"] = canonical_duplicate_clusters(refs, limit=limit)
    return report
