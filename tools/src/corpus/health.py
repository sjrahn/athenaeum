"""Offline corpus health signals.

A read-only, fully-offline scan that surfaces what a corpus operator (or a curation
skill) wants to triage: how records sit across the derived layers (spec §4.1 —
formed / rendered / proxy, plus derived-editorial coverage, §4.2.3/§12.21), which carry
unresolved issues, which are missing their bytes, and which fail basic structural
validity. `scan_all` returns a structured report; the `corpus health` CLI renders it as
JSON or a summary.

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

# *(3.2)* `description` drops out — it is no longer a stored, birth-required field (spec
# §4.2, §12.3.4): the display description is derived, and the frontmatter key survives only
# as an optional override, absent in the steady state.
_REQUIRED_KEYS = ("id", "touch")


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


def layer_presence(refs: list[RecordRef], corpus_root: Path) -> dict[str, int]:
    """Layer-presence census (spec §4.1, §12.19 — succeeding the 3.0 status census): how the
    fleet sits across the derived-state enum, plus **derived-editorial coverage** (3.2,
    §12.21 step 1, succeeding the retired `authored` tally) and a transitional legacy-status
    count. `rendered` is `derived_state == "rendered"` — a stored rendering with no governing
    form, the grandfathered population (§12.18 step 3). `terminal` *(3.3)* is
    `derived_state == "terminal"` — a terminal contract governs and no rendering is stored
    (§7.8); it narrows what `proxy` means to genuinely unassessed-or-awaiting. `titled`/
    `untitled` count records whose derived title (spec §4.2.3) is non-empty vs. empty — the
    empty set is the §12.21 role-marking worklist, not a defect tally. The queue is standing
    demand, not backlog (§8.5), so this reports layer presence only — not how many records
    "need" a pass."""
    formed = terminal = rendered = proxy = titled = untitled = legacy_status = 0
    for r in refs:
        state = records.derived_state(r.post, corpus_root)
        if state == "formed":
            formed += 1
        elif state == "terminal":
            terminal += 1
        elif state == "rendered":
            rendered += 1
        else:
            proxy += 1
        if records.title_for(r.post, corpus_root):
            titled += 1
        else:
            untitled += 1
        if "status" in r.post.metadata:
            legacy_status += 1
    return {
        "formed": formed,
        "terminal": terminal,
        "rendered": rendered,
        "proxy": proxy,
        "titled": titled,
        "untitled": untitled,
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
    *(3.3)* `proxy` here EXCLUDES `terminal` records — a terminal contract (§7.8) already
    answers "will this ever get a rendering?" with no, so it never appears in this list;
    `proxy` narrows to genuinely unassessed-or-awaiting. `shapable` is True when the
    record's origin declares a form with a registered mechanical shaper (`corpus shape`
    would advance it) — the 3.1 successor of the 2.x `stuck_at_stub` "supported_draft"
    signal, re-keyed from the retired draft-strategy registry to the shape registry (spec
    §12.5.0). A `proxy` record with `shapable: false` is not necessarily stuck — most of
    the remaining population is formless-for-now, awaiting identification, authorship, or
    a worthwhile pass (§7.8)."""
    from . import shape as shape_pkg

    out: list[dict[str, Any]] = []
    for r in refs:
        if records.derived_state(r.post, corpus_root) != "proxy":
            continue
        resolved = shape_pkg.form_for_record(r.post, corpus_root)
        shapable = bool(
            resolved
            and (shape_pkg.get_shaper(resolved[0]) or shape_pkg.get_shaper(resolved[1]))
        )
        out.append(
            {
                "id": r.record_id,
                "title": records.title_for(r.post, corpus_root),
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
    from . import containment, paths, placement
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
        # *(22)* A standalone copy in a store location (spec §12.1.1) is present, not
        # missing — it just isn't the co-located copy the store's own is_local checks.
        if placement.find_in_stores(corpus_root, r.record_id, ext) is not None:
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
                "title": records.title_for(r.post, corpus_root),
                "media_type": mime,
                "expected_path": str(expected),
                "category": category,
            }
        )
    return out[:limit]


def _find_store_location_name(corpus_root: Path, record_id: str, ext: str) -> str | None:
    """Which configured `kind = "store"` location currently holds a standalone copy
    of `record_id`, or `None` — display-only companion to `placement.find_in_stores`
    (same declaration-order walk, name instead of path)."""
    from . import placement

    for loc in placement.store_locations(corpus_root):
        if placement.location_artifact_path(loc, record_id, ext).is_file():
            return loc.name
    return None


def shadowed_copies(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Records holding BOTH a store copy (co-located `artifacts/`, or any configured
    store location) AND a **current** attached-location index row (spec §12.1.1's
    "Adoption" paragraph, v23) — dedup/reclaim candidates. Adoption is
    non-destructive by design: the store copy already serves every consumer
    (resolution order shadows the attached row with no further mechanism), while the
    attached row persists honestly — "invisible in use but surfacable" is this
    signal's whole reason to exist, and the spec also notes the pair counts toward a
    redundancy floor as two genuinely distinct copies, not one.

    A stale attached row (size/mtime drift, a vanished file, or a location dropped
    from `corpus.toml`) is excluded — `locationindex.current_rows_by_hash` already
    screens those out, and a stale row resolves nowhere regardless of whether a
    store copy also exists. Zero byte reads: an index join against each record's own
    resolution (`store.is_local` / a store-location file-existence check), reusing
    the staleness pins `attest` already computed."""
    from . import locationindex
    from . import mime as mime_mod
    from .store import get_store

    by_hash = locationindex.current_rows_by_hash(corpus_root)
    if not by_hash:
        return []

    store = get_store(corpus_root)
    out: list[dict[str, Any]] = []
    for r in refs:
        rows = by_hash.get(r.record_id)
        if not rows:
            continue
        mime = records.media_type_for(r.post)
        if not mime:
            continue
        ext = mime_mod.extension_for(mime)
        if store.is_local(r.record_id, ext):
            store_location = "corpus"
        else:
            store_location = _find_store_location_name(corpus_root, r.record_id, ext)
            if store_location is None:
                continue  # attached-only (or containment-only) — nothing shadowed
        out.append(
            {
                "id": r.record_id,
                "title": records.title_for(r.post, corpus_root),
                "store_location": store_location,
                "attached_rows": [{"location": loc, "relpath": rp} for loc, rp in rows],
            }
        )
    return out[:limit]


def validity_violations(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50
) -> list[dict[str, Any]]:
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
                {
                    "id": r.record_id,
                    "title": records.title_for(r.post, corpus_root),
                    "problems": problems,
                }
            )
    return out[:limit]


def canonical_duplicate_clusters(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50, **_kw: Any
) -> dict[str, Any]:
    """Records that are the SAME delivered document captured twice — joined on the
    `html-stampfree@1` recipe (spec §7.9, §12.9.1), the capture-invariant identity a
    `text/html` record earns by neutralizing only the corpus's own capture-injected
    stamps. Zero artifact reads: this is a pure index join (`hashindex.values_by_algo`)
    over rows ingest/reattest/backfill already computed while bytes were in hand — the
    inert predecessor here keyed on `records.content_key()` (a retired `canonical:`
    content-canonical hash, §7.1, §4.2.1), which no record has populated since 3.5, so
    this signal covered zero ground fleet-wide until now.

    A cluster is 2+ *currently live* record ids sharing one `html-stampfree@1` value —
    restricted to `refs` (the scanned population) so a hash orphaned by a since-removed
    record never phantom-joins. `unindexed_ids` names `text/html` records with no
    `html-stampfree@1` row yet (the `corpus hash-index backfill` worklist) — reported,
    never silently skipped, per the index's "absent is unindexed, not a failure"
    contract (spec §12.9.1)."""
    from . import hashindex

    html_ids = {r.record_id for r in refs if records.media_type_for(r.post) == "text/html"}
    if not html_ids:
        return {"clusters": [], "total_clusters": 0, "unindexed_count": 0, "unindexed_ids": []}

    db_path = hashindex.db_path(corpus_root)
    if not db_path.exists():
        ids = sorted(html_ids)
        return {
            "clusters": [],
            "total_clusters": 0,
            "unindexed_count": len(ids),
            "unindexed_ids": ids[:limit],
        }

    live_ids = {r.record_id for r in refs}
    with hashindex.open_index(corpus_root) as conn:
        by_value = hashindex.values_by_algo(conn, "html-stampfree@1")

    indexed_ids: set[str] = set()
    clusters: list[dict[str, Any]] = []
    for value, ids in by_value.items():
        indexed_ids.update(ids)
        present = sorted(rid for rid in ids if rid in live_ids)
        if len(present) > 1:
            clusters.append({"digest": value, "count": len(present), "ids": present})
    clusters.sort(key=lambda c: (-c["count"], c["digest"]))

    unindexed_ids = sorted(html_ids - indexed_ids)
    return {
        "clusters": clusters[:limit],
        "total_clusters": len(clusters),
        "unindexed_count": len(unindexed_ids),
        "unindexed_ids": unindexed_ids[:limit],
    }


def dangling_origin_refs(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50
) -> dict[str, list[dict[str, Any]]]:
    """Origin blocks whose `uri:` points at a `corpus://<hash>` container that no longer
    exists **in this corpus** (spec §5.2 — origin blocks are append-only history; §12.8 —
    `corpus rm` retires a superseded container). Resolution is same-corpus only — a hash is
    checked against `records/<shard>/<hash>.md` under `corpus_root` and never across the
    tenant boundary (spec's repo-boundary rule).

    Severity keys on WHICH origin block carries the dead reference, not merely that one
    exists: a record's origin blocks are ordered by capture time, so the LAST block (or the
    only one) is its live lineage — a dead hash there means the record's current lineage is
    genuinely broken (`warning`). A dead hash in an earlier, superseded block is honest
    history of a since-retired container — the record's live lineage is unaffected
    (`info`). Each entry names the record, the dead hash, and the origin block's index (0 =
    first) plus whether it was the latest."""
    from . import functional_uri as furi
    from . import paths as _paths

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in refs:
        origins = list(records.iter_origin_blocks(r.post))
        if not origins:
            continue
        last_index = len(origins) - 1
        for i, origin in enumerate(origins):
            fields = origin.get("fields") or {}
            uri = fields.get("uri")
            uris = uri if isinstance(uri, list) else ([uri] if uri else [])
            for raw in uris:
                candidate = str(raw or "").strip()
                if not candidate.startswith("corpus://"):
                    continue
                try:
                    parsed = furi.parse(candidate)
                except ValueError:
                    continue
                dead_hash = parsed.hash
                if _paths.record_path(corpus_root, dead_hash).is_file():
                    continue
                latest = i == last_index
                severity = "warning" if latest else "info"
                grouped[severity].append(
                    {
                        "id": r.record_id,
                        "title": records.title_for(r.post, corpus_root),
                        "dead_hash": dead_hash,
                        "block_index": i,
                        "block_subtype": origin.get("subtype"),
                        "latest": latest,
                        "uri": candidate,
                        "message": (
                            f"record {r.record_id} origin block {i}"
                            f"{'/' + origin['subtype'] if origin.get('subtype') else ''} "
                            f"cites dead corpus://{dead_hash} — "
                            + (
                                "live lineage broken"
                                if latest
                                else "retired-container history (non-latest block)"
                            )
                        ),
                    }
                )
    return {sev: items[:limit] for sev, items in grouped.items()}


_CONFIRM_CHUNK = 1 << 20  # 1 MiB — matches `hashing.CHUNK`


def _confirm_prefix(path_a: Path, path_b: Path) -> tuple[str, bool] | None:
    """Stream `path_a`/`path_b` in lockstep, bounded chunks — confirming (or rejecting)
    what the index screen only admitted as a candidate (spec §7.9: "a screen, not a
    proof"). Never loads a whole file and never holds both files' bytes at once — the
    motivating OOM measurement (§12.9.1) was one same-filename group holding 9 GB in
    memory simultaneously.

    Which file is shorter is discovered here, not assumed from the screen (the ladder's
    rung count only orders files that cross a *different* number of rungs; two files
    tied on rung count can still differ in true length beyond the highest common rung).
    Returns `(kind, a_is_shorter)`: `kind` is `"identical"` (equal length, every byte
    equal) or `"prefix"` (the shorter is a byte-prefix of the longer); `a_is_shorter`
    says which input that was. Returns `None` when the streams diverge before either
    ends — a screen false-positive (a rung match without proof), not a match.
    """
    with path_a.open("rb") as fa, path_b.open("rb") as fb:
        while True:
            ca = fa.read(_CONFIRM_CHUNK)
            cb = fb.read(_CONFIRM_CHUNK)
            n = min(len(ca), len(cb))
            if ca[:n] != cb[:n]:
                return None
            if len(ca) == len(cb):
                if not ca:
                    return "identical", True
                continue  # both still going, matched so far — keep streaming
            # A `read()` returns fewer bytes than requested only at EOF, so whichever
            # chunk came back shorter marks that file's true end — decided at most one
            # `_CONFIRM_CHUNK` past where the ladder's rungs ran out.
            return "prefix", len(ca) < len(cb)


def prefix_duplicate_artifacts(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50, **_kw: Any
) -> dict[str, Any]:
    """Distinct records that are the SAME source document captured twice — one artifact
    byte-identical to another, or a byte-prefix of it. The live case is a producer
    re-emitting a grown export file into a later bundle (an iMessage window one message
    longer, #147): two blake3-distinct records, one conversation — which the ledger's
    two-independent-records evidence bar cannot see.

    Candidates are joined on the origin `filename:` (a re-emission keeps its name, as
    before), then screened via the `blake3-prefix-ladder` index rows (spec §7.9,
    §12.9.1) before any byte is read: two files are prefix-candidates iff every ladder
    rung *both* reach agrees (rungs nest — 64k implies 4k — so the rungs one file lacks
    say nothing, and the rungs both share are the only ones a mismatch could hide in).
    Only screen survivors are confirmed, by `_confirm_prefix`'s bounded streaming
    compare — never a whole-group `read_bytes()`. This replaces the byte-reading
    predecessor that read 19.75 GB across 251 same-filename groups on the 25k-record /
    157 GB corpus and held one group's 9 GB in memory at once, dying on the OOM killer
    (exit 137); index-joined, the steady state costs zero artifact reads until a
    candidate actually needs confirming.

    A record with NO index rows at all is `unindexed` — reported (with a count and its
    ids), never silently skipped or read around (spec §12.9.1's "absent is unindexed,
    not a failure"); it never enters screening. A screen-passing pair whose bytes
    aren't locally resident is `unconfirmed` — nothing here pulls remote bytes to
    confirm a health signal (spec §12.9.1's flush/hydrate economics are an operator's
    deliberate choice, not a side effect of a scan)."""
    from . import hashindex, placement
    from . import mime as mime_mod
    from .store import get_store

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in refs:
        blocks = list(records.iter_origin_blocks(r.post))
        fields = (blocks[0].get("fields") or {}) if blocks else {}
        filename = str(fields.get("filename") or "")
        if filename:
            groups[(records.media_type_for(r.post), filename)].append(r.record_id)

    multi = {k: ids for k, ids in groups.items() if len(ids) > 1}
    empty: dict[str, Any] = {
        "groups_scanned": 0,
        "pairs_compared": 0,
        "pairs": [],
        "total_pairs": 0,
        "unindexed_count": 0,
        "unindexed_ids": [],
        "unconfirmed_count": 0,
        "unconfirmed": [],
    }
    if not multi:
        return empty

    db_path = hashindex.db_path(corpus_root)
    if not db_path.exists():
        # Fresh-clone case (spec §12.9.1): nothing to screen against — every candidate
        # is unindexed, zero reads, fast.
        unindexed_ids = sorted({rid for ids in multi.values() for rid in ids})
        return {
            **empty,
            "groups_scanned": len(multi),
            "unindexed_count": len(unindexed_ids),
            "unindexed_ids": unindexed_ids[:limit],
        }

    store = get_store(corpus_root)
    ext_by_mime: dict[str, str] = {}

    def _ext(media_type: str) -> str:
        if media_type not in ext_by_mime:
            ext_by_mime[media_type] = mime_mod.extension_for(media_type)
        return ext_by_mime[media_type]

    pairs: list[dict[str, Any]] = []
    unconfirmed: list[dict[str, Any]] = []
    unindexed_ids: set[str] = set()
    screened = 0

    with hashindex.open_index(corpus_root) as conn:
        for (media_type, filename), ids in sorted(multi.items()):
            rung_by_id: dict[str, dict[str, str]] = {}
            for rid in ids:
                rows = hashindex.rows_for(conn, rid)
                if not rows:
                    unindexed_ids.add(rid)
                    continue
                rung_by_id[rid] = {
                    row.algo: row.value for row in rows if row.recipe == "blake3-prefix-ladder"
                }
            screenable = sorted(rung_by_id)
            ext = _ext(media_type)
            for i in range(len(screenable)):
                for j in range(i + 1, len(screenable)):
                    a_id, b_id = screenable[i], screenable[j]
                    a_rungs, b_rungs = rung_by_id[a_id], rung_by_id[b_id]
                    common = set(a_rungs) & set(b_rungs)
                    if any(a_rungs[tag] != b_rungs[tag] for tag in common):
                        continue  # screen rejects — definitively unrelated
                    screened += 1
                    # *(22)* "locally resident" now also covers a standalone copy parked
                    # in a store location (spec §12.1.1) — a co-located miss falls back
                    # to `placement.find_in_stores` before counting the pair unconfirmed.
                    a_path = (
                        store.local_path(a_id, ext)
                        if store.is_local(a_id, ext)
                        else placement.find_in_stores(corpus_root, a_id, ext)
                    )
                    b_path = (
                        store.local_path(b_id, ext)
                        if store.is_local(b_id, ext)
                        else placement.find_in_stores(corpus_root, b_id, ext)
                    )
                    if a_path is None or b_path is None:
                        unconfirmed.append({"filename": filename, "ids": sorted([a_id, b_id])})
                        continue
                    result = _confirm_prefix(a_path, b_path)
                    if result is None:
                        continue  # screen false-positive — confirm rejected it
                    kind, a_is_shorter = result
                    shorter, longer = (a_id, b_id) if a_is_shorter else (b_id, a_id)
                    pairs.append(
                        {"kind": kind, "filename": filename, "shorter": shorter, "longer": longer}
                    )

    return {
        "groups_scanned": len(multi),
        "pairs_compared": screened,
        "pairs": pairs[:limit],
        "total_pairs": len(pairs),
        "unindexed_count": len(unindexed_ids),
        "unindexed_ids": sorted(unindexed_ids)[:limit],
        "unconfirmed_count": len(unconfirmed),
        "unconfirmed": unconfirmed[:limit],
    }


# ---------- aggregator ---------- #


SIGNAL_NAMES = (
    "layer_presence",
    "records_by_mime",
    "unshaped",
    "unresolved_issues",
    "missing_artifacts",
    "validity_violations",
    "canonical_duplicate_clusters",
    "dangling_origin_refs",
    "normalization_pressure",
    "overlay_declarations",
    "prefix_duplicate_artifacts",
    "shadowed_copies",
)


def overlay_declarations(refs: list[RecordRef], corpus_root: Path, **_kw: Any) -> dict[str, Any]:
    """*(3.8, spec §7.2)* Malformed `regions:` rows and non-`ok` `exemplars:` across every
    origin overlay a record in this corpus actually carries.

    Here rather than in `corpus lint` because the defect is the OVERLAY's, not any record's:
    a stale exemplar is one bad line in one yaml, and reporting it on each of the 7,046
    records of that origin would be 7,046 findings for one fix. Health is where a corpus-wide
    fact belongs.

    Scoped to origins in USE — an overlay nothing has been captured under yet is a plan, not a
    defect."""
    from corpus import schemas

    in_use: set[str] = set()
    for ref in refs:
        for blk in records.iter_origin_blocks(ref.post):
            if oid := str(blk.get("id") or "").strip():
                in_use.add(oid)
    problems: dict[str, list[str]] = {}
    for oid in sorted(in_use):
        if msgs := schemas.origin_declaration_errors(corpus_root, oid):
            problems[oid] = msgs
    return {"origins_checked": len(in_use), "problems": problems}


def normalization_pressure(
    refs: list[RecordRef], corpus_root: Path, *, limit: int = 50
) -> dict[str, Any]:
    """*(3.8, spec §8.5)* Demand on promoted members, derived: how many records **place** each
    member whose own record has not rendered it yet (§4.3.2.4).

    This is not a defect list and nothing gates on it — a leaf standing as its artifact's proxy
    is a complete record (§4.1). It is the second demand source on the queue's one mechanism,
    beside the ledger's citation demand, and its whole value is the RANKING: rendering a member
    that 668 records place is 668 records improved by one pass, which is a materially different
    proposition from rendering one a single record places. Derived from the placements and the
    roster, never stored — a field would be a count that could disagree with the records.

    A member with no record at all is deliberately absent: that is the parent's error
    (`placed-member-not-promoted`), not demand on a record that does not exist.

    **What counts as awaiting is not the derived state**, and the first cut got this exactly
    backwards. `image/*` declares `form: passthrough` at the mime grain, so a promoted image
    with no rendering resolves as `terminal` — "complete, never enters the queue" — while one
    that HAS been transcribed resolves as `rendered`. Reading the enum therefore put all the
    demand on the members already read and none on the ones waiting. The distinction that
    matters is §7.8's own: a **declared default** at the mime grain is not a judgment about
    *this* PNG, whereas a **per-record assertion** (a `<!--section passthrough-->` in its
    content zone) is. So a leaf carries pressure when it stores no rendering AND asserts no
    form — an unread table image counts, a deliberately-judged photo does not, and the judgment
    is what silences it rather than the media type it happens to share.
    """
    pressure: dict[str, int] = {}
    placed_by: dict[str, set[str]] = {}
    for ref in refs:
        try:
            blocks = _segments_module().iter_blocks(ref.post.content or "")
        except Exception:
            continue
        addrs: set[str] = set()
        for blk in blocks:
            kids = blk.segments if hasattr(blk, "segments") else [blk]
            for seg in kids:
                if getattr(seg, "is_placement", False):
                    value = seg.address
                    addrs.update(value if isinstance(value, list) else [str(value)])
        if not addrs:
            continue
        for row in records.iter_members(ref.post):
            row_addrs = row.get("address")
            row_addrs = row_addrs if isinstance(row_addrs, list) else [row_addrs]
            if not any(str(a) in addrs for a in row_addrs):
                continue
            hexval = str(row.get("transport") or "").partition(":")[2]
            if hexval:
                placed_by.setdefault(hexval, set()).add(ref.record_id)

    from . import paths as _paths

    for hexval, parents in placed_by.items():
        leaf = _paths.record_path(corpus_root, hexval)
        if not leaf.is_file():
            continue  # the parent's error, reported by lint — not demand
        try:
            leaf_post = records.load(leaf)
            waiting = not records.has_stored_rendering(leaf_post) and not records.is_formed(
                leaf_post
            )
        except Exception:
            continue
        if waiting:
            pressure[hexval] = len(parents)

    ranked = sorted(pressure.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "members_awaiting": len(ranked),
        "total_pressure": sum(pressure.values()),
        "top": [{"member": h, "placed_by": n} for h, n in ranked[:limit]],
    }


def _segments_module():
    from . import segments as _segments

    return _segments


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
        report["layer_presence"] = layer_presence(refs, corpus_root)
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
    if "validity_violations" in selected:
        report["validity_violations"] = validity_violations(refs, corpus_root, limit=limit)
    if "canonical_duplicate_clusters" in selected:
        report["canonical_duplicate_clusters"] = canonical_duplicate_clusters(
            refs, corpus_root, limit=limit
        )
    if "dangling_origin_refs" in selected:
        report["dangling_origin_refs"] = dangling_origin_refs(refs, corpus_root, limit=limit)
    if "normalization_pressure" in selected:
        report["normalization_pressure"] = normalization_pressure(refs, corpus_root, limit=limit)
    if "overlay_declarations" in selected:
        report["overlay_declarations"] = overlay_declarations(refs, corpus_root)
    if "prefix_duplicate_artifacts" in selected:
        report["prefix_duplicate_artifacts"] = prefix_duplicate_artifacts(
            refs, corpus_root, limit=limit
        )
    if "shadowed_copies" in selected:
        report["shadowed_copies"] = shadowed_copies(refs, corpus_root, limit=limit)
    return report
