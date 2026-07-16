"""Ingest a single file from capture/ → records/<shard>/<hash>.md.

Computes blake3 + auxiliary byte hashes declared by the matching mime schema's
`transport_algos`. MIME detect → `<!--artifact <mime>-->` opener. Every transport is
self-contained (spec §1.2, 2.1): a raw archive lands as one record and drafts as an
embed manifest; its members are reachable by promotion (`corpus promote`, §8.1), not
by exploding at ingest.

If the file's bytes are already in the corpus, this is an idempotent re-encounter:
the existing record gains a touch entry. If the capture URL differs from any
existing origin's `uri:`, a new origin block is appended.

Capture-time metadata sidecar: a `<file>.capture.yaml` alongside the input carries
capture metadata (`source_url`, `fetched_at`). On fresh ingest these seed the first
origin block; after ingest the sidecar is removed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, help="Path to a file in capture/")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    src = args.file.resolve()
    if not src.is_file():
        sys.exit(f"not a file: {src}")
    try:
        corpus_root = resolved_corpus_root(args)
    except SystemExit:
        # Fall back to discovering from the file's parent.
        from corpus import paths

        try:
            corpus_root = paths.find_corpus_root(src.parent)
        except FileNotFoundError as e:
            sys.exit(str(e))
    return _ingest_one(corpus_root, src)


def _ingest_one(corpus_root: Path, src: Path) -> int:
    from corpus import hashing, mime, paths, records, schemas, touches
    from corpus.store import get_store

    media_type = mime.detect(src, corpus_root)
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if mt_schema is None:
        sys.exit(
            f"no mime schema for {media_type!r} (file: {src}). "
            f"Author schema/mime/<axis>/<axis>_<subtype>.yaml first, then re-run."
        )

    # Spec §1.2 (2.1): every transport is self-contained — there is no `artifact_kind`
    # disposition anymore, and no explode-at-ingest path. A raw archive is ingested as one
    # record and drafts as an embed manifest; a schema still declaring `artifact_kind` is
    # ignored (tolerant parsing, §7.1 / §12.17). Members become records via `corpus promote`.
    aux_algos = tuple(str(a) for a in mt_schema.get("transport_algos", []) if a)
    digests = hashing.hash_file(src, also=aux_algos)
    record_id = digests["blake3"]
    transport_hashes = [
        records.format_hash(algo, digests[algo])
        for algo in aux_algos
        if algo in digests and algo.lower() != "blake3"
    ]

    extension = mime.extension_for(media_type, fallback=src.suffix.lstrip(".") or "bin")
    record_file = paths.record_path(corpus_root, record_id)
    store = get_store(corpus_root)

    sidecar = _read_sidecar(src)
    origin_uri, origin_at, origin_fields, origin_schema = _derive_capture_origin(
        src, sidecar, media_type
    )

    if record_file.is_file():
        post = records.load(record_file)
        appended = _append_origin_if_new(
            post, origin_uri, origin_at, origin_fields, origin_schema
        )
        touches.record_touch(post, touches.script_identifier("ingest"))
        records.dump(post, record_file)
        src.unlink()
        _cleanup_sidecar(src)
        _relocate_info_sidecar(src, record_id)
        print(f"re-encounter: {record_file.relative_to(corpus_root)}")
        if appended:
            print(f"  +origin: {origin_uri or origin_fields.get('filename', '(local file)')}")
        return 0

    # Persist bytes via the store, then unlink the staging file.
    store.put(record_id, extension, src)
    src.unlink()

    transport_value: str | list[str] | None
    if not transport_hashes:
        transport_value = None
    elif len(transport_hashes) == 1:
        transport_value = transport_hashes[0]
    else:
        transport_value = transport_hashes

    fm = records.stub_frontmatter(
        record_id=record_id,
        transport=transport_value,
        touch_id=touches.script_identifier("ingest"),
    )
    post = frontmatter.Post(content="", **fm)
    # The artifact block carries no generic `title`: a capture-sidecar title (e.g. a yt-dlp
    # title) is non-primary-source metadata whose home is the origin block's `ytdlp_title`,
    # merged at draft. The frontmatter carries no `title`/`description` at birth at all
    # (spec §12.3.4) — the display pair is derived from role-marked fields (§4.2.3); see
    # `records.title_for` / `records.derived_editorial`.
    records.set_artifact_block(post, mime=media_type, fields={})
    records.append_origin_block(
        post,
        uri=origin_uri,
        snapshot=origin_at,
        schema_id=origin_schema,
        fields=origin_fields or None,
    )
    _emit_sidecar_issues(post, sidecar)

    # Stage an enrichment sidecar (a yt-dlp `.info.json`) as `capture/<hash>.info.json` BEFORE
    # attestation so the sidecar-lift can consume it (spec §7.2, §8.1).
    _relocate_info_sidecar(src, record_id)
    # 3.0: attest the byte-facts at stub time (§8.1) — artifact-block fields, manifest/
    # exposable embeds, sidecar-lifted origin fields, drafter issues. The body is NOT stored
    # (the `body` op derives it on demand). Best-effort: a type with no drafter or unreadable
    # bytes stays a bare stub, attestable later via `corpus reattest`.
    _attest_stub(post, corpus_root, record_id)
    records.dump(post, record_file)

    _cleanup_sidecar(src)
    _cleanup_enrichment(corpus_root, record_id)

    print(f"new stub: {record_file.relative_to(corpus_root)}")
    print(f"  hash:       {record_id}")
    print(f"  media_type: {media_type}")
    print(f"  binary:     {store.local_path(record_id, extension).relative_to(corpus_root)}")
    return 0


def _attest_stub(post: frontmatter.Post, corpus_root: Path, record_id: str) -> None:
    """Attest byte-facts onto a fresh stub at ingest (§8.1) via the shared `derive.attest`.
    Best-effort — a type with no registered drafter or unreadable bytes leaves a bare stub
    (attestable later with `corpus reattest`). The stub's empty content zone is unchanged
    (the body is derived on demand, §6.2) — it stays the artifact's proxy (§4.1) until a form
    is stamped or the vouch is authored."""
    import logging

    from corpus import derive

    try:
        derive.attest(post, corpus_root, strip=False)
    except Exception as exc:  # attest is best-effort at ingest (no drafter / unreadable bytes)
        logging.getLogger("corpus.ingest").debug(
            "no attestation for %s: %s", record_id[:12], exc
        )


def _cleanup_enrichment(corpus_root: Path, record_id: str) -> None:
    """Delete the record's enrichment sidecars from `capture/` once attestation consumed them
    (a yt-dlp `.info.json`, and any `<hash>.*` a capturer staged). One-shot — the lifted
    fields already persist on the record. Best-effort; `capture/` is staging-only."""
    capture_dir = corpus_root / "capture"
    if not capture_dir.is_dir():
        return
    for p in capture_dir.glob(f"{record_id}.*"):
        p.unlink(missing_ok=True)


def _append_origin_if_new(
    post,
    uri: str | None,
    snapshot: str,
    fields: dict[str, Any] | None = None,
    schema_id: str | None = None,
) -> bool:
    from corpus import records
    from corpus import urls as urlcanon

    if not snapshot:
        return False

    # Local-file origin (no retrieval uri): dedup by filename — re-dropping the same-named
    # file's bytes appends no duplicate, while the same bytes under a DIFFERENT name is a
    # distinct local source (its own origin). Matches any existing origin carrying that
    # filename, including one that later gained a folded-in retrieval uri.
    if not uri:
        fields = fields or {}
        fname = fields.get("filename")
        for origin in records.iter_origin_blocks(post):
            if fname and (origin.get("fields") or {}).get("filename") == fname:
                return False
        records.append_origin_block(
            post, uri=None, snapshot=snapshot, schema_id=schema_id, fields=fields or None
        )
        return True

    try:
        canon_new = urlcanon.normalize(uri)
    except Exception:
        canon_new = uri

    for origin in records.iter_origin_blocks(post):
        existing = (origin.get("fields") or {}).get("uri")
        candidates = existing if isinstance(existing, list) else [existing] if existing else []
        for c in candidates:
            try:
                canon_existing = urlcanon.normalize(str(c))
            except Exception:
                canon_existing = str(c)
            if canon_existing == canon_new:
                return False
    records.append_origin_block(
        post, uri=uri, snapshot=snapshot, schema_id=schema_id, fields=fields or None
    )
    return True


def _read_sidecar(src: Path) -> dict:
    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    if not sidecar_path.is_file():
        return {}
    try:
        with sidecar_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError:
        return {}


def _derive_capture_origin(
    src: Path, sidecar: dict, media_type: str | None = None
) -> tuple[str | None, str, dict[str, Any], str | None]:
    """Origin seed for an ingested artifact — `(uri|None, snapshot, fields, schema_id|None)`.

    Three tiers, most-authoritative first:

    1. A capture sidecar with a `source_url` yields a *retrieval* origin (uri + snapshot).
    2. Otherwise, an HTML file carrying a **SingleFile banner** (a manual save dropped
       straight into `capture/` and ingested with no capture step) yields a retrieval origin
       from the banner: `uri:` = the banner URL, `snapshot:` = the banner saved date (parsed
       to ISO-8601 with its numeric offset preserved — the moment the human saved it, spec
       §12.3.4). The banner is scanned only in a bounded head.
    3. Otherwise a bare dropped-in file has no retrieval source — the staging path is unlinked
       moments later, so a `uri:` would be a reference dead on arrival — so it yields a
       uri-less *local-file* origin carrying durable metadata instead: `filename` (basename)
       + `source_modified` (mtime, best-effort) (spec §7.2).

    A producer may also DECLARE an overlay (spec §7.2): the sidecar's `origin_schema:` (the
    overlay id stamped on the block, the only way a uri-less origin binds an overlay) and
    `origin_fields:` (its extended fields) are consumed here for either origin shape — e.g. an
    `imessage-export` carrying `chat_name`/`phone_number`/`period`."""
    from corpus import singlefile, touches

    uri = str(sidecar.get("source_url") or "").strip()
    discovered_at = str(sidecar.get("fetched_at") or "").strip() or touches.now_iso()
    schema_id = str(sidecar.get("origin_schema") or "").strip() or None
    declared = sidecar.get("origin_fields")
    extra: dict[str, Any] = {str(k): v for k, v in declared.items()} if isinstance(declared, dict) else {}
    if uri:
        return uri, discovered_at, dict(extra), schema_id
    # Tier 2 — the SingleFile banner (HTML only; explicit sidecar above still wins).
    if media_type == "text/html":
        if banner := singlefile.banner_origin(src):
            banner_uri, banner_at = banner
            return banner_uri, banner_at, dict(extra), schema_id
    fields: dict[str, Any] = {"filename": src.name}
    mtime = _source_modified_iso(src)
    if mtime:
        fields["source_modified"] = mtime
    fields.update(extra)
    return None, discovered_at, fields, schema_id


def _source_modified_iso(src: Path) -> str | None:
    """ISO-8601 UTC (seconds) of the file's mtime, or None when unreadable. The durable
    provenance for a dropped-in file — typically when it was authored / scanned / exported."""
    from datetime import UTC, datetime

    try:
        ts = src.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _cleanup_sidecar(src: Path) -> None:
    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    if sidecar_path.is_file():
        sidecar_path.unlink()


def _relocate_info_sidecar(src: Path, record_id: str) -> None:
    """Rename a yt-dlp `.info.json` companion of `src` to `capture/<hash>.info.json`.

    It STAYS in the staging dir (`capture/`) — it is draft-time-only enrichment that the
    drafter reads and then deletes. The hash name lets the drafter find it; the artifact
    is the only `<hash>`-named file under `artifacts/`. No-op when absent (most mimes)."""
    info_src = src.with_suffix(".info.json")
    if info_src.is_file():
        info_src.rename(src.parent / f"{record_id}.info.json")


def _emit_sidecar_issues(post: frontmatter.Post, sidecar: dict) -> None:
    """Replay capture-stage issues onto the record as <!--issue--> blocks."""
    from corpus import records

    entries = sidecar.get("capture_issues") or []
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        issue_id = entry.get("id")
        severity = entry.get("severity")
        detector = entry.get("detector")
        if not (issue_id and severity and detector):
            continue
        records.append_issue_block(
            post,
            id=str(issue_id),
            subtype=entry.get("subtype"),
            severity=str(severity),
            resolution=str(entry.get("resolution") or "open"),
            detector=str(detector),
            fields=entry.get("fields") or None,
        )
