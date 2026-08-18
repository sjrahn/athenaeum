"""Ingest a single file from capture/ → records/<shard>/<hash>.md.

Computes blake3 (the artifact's identity, `id`) plus the resolved derived-hash recipe
union — the corpus-wide default set (`sha256`/`md5` record-resident; the blake3
prefix ladder index-only) additively layered with the matching mime schema's and
matched origin overlay's `derived_hashes:` (spec §7.9) — while the staged bytes are
still in hand. `residency: record` byte-stable values land in frontmatter `hash:`
*and* the derived hash index; everything else is index-only (§2, §12.3.3, §12.9.1).
MIME detect → `<!--artifact <mime>-->` opener. Every transport is self-contained (spec
§1.2, 2.1): a raw archive lands as one record and drafts as an embed manifest; its
members are reachable by promotion (`corpus promote`, §8.1), not by exploding at
ingest.

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
from collections.abc import Callable
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
    from corpus import hashing, mime, paths, placement, records, schemas, touches
    from corpus.store import get_store

    media_type = mime.detect(src, corpus_root)
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if mt_schema is None:
        sys.exit(
            f"no mime schema for {media_type!r} (file: {src}). "
            f"Author schema/mime/<axis>/<axis>_<subtype>.yaml first, then re-run."
        )

    # Mailbox chrome strip (spec §12.3.13) / JSON-family field strip (spec §12.3.14):
    # where the origin chain declares `strip_headers` (mbox) or `strip_fields` (json),
    # the staged bytes are canonicalized BEFORE identity — config-driven, so no operator
    # verb ordering can leak provider workflow-state churn into member identity. Each
    # helper no-ops immediately for the wrong media type, so exactly one ever does work.
    strip_provenance = _canonicalize_mbox(corpus_root, src, media_type) or _canonicalize_json(
        corpus_root, src, media_type
    )

    # Spec §1.2 (2.1): every transport is self-contained — there is no `artifact_kind`
    # disposition anymore, and no explode-at-ingest path. A raw archive is ingested as one
    # record and drafts as an embed manifest; a schema still declaring `artifact_kind` is
    # ignored (tolerant parsing, §7.1 / §12.17). Members become records via `corpus promote`.
    #
    # Identity (blake3) is computed separately from the recipe union (spec §7.9): `hash_file`
    # is the identity path (unchanged API other callsites depend on, `hashing.py`'s own
    # docstring), `compute_hashes` the recipes-over-staged-bytes path — both read the staged
    # file while it is still in hand, before `store.put` persists it and `src.unlink()` drops
    # the staging copy.
    record_id = hashing.hash_file(src, also=())["blake3"]

    extension = mime.extension_for(media_type, fallback=src.suffix.lstrip(".") or "bin")
    record_file = paths.record_path(corpus_root, record_id)
    store = get_store(corpus_root)

    sidecar = _read_sidecar(src)
    origin_uri, origin_at, origin_fields, origin_schema = _derive_capture_origin(
        src, sidecar, media_type
    )
    origin_fields.update(strip_provenance)

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

    # The derived-hash recipe union (spec §7.9): corpus-wide default set, additively layered
    # with this mime schema's `derived_hashes:` and the matched origin overlay's — computed
    # NOW, while `src` still holds the staged bytes (§8.1's free moment), before the store
    # persists them and the staging copy is unlinked.
    overlay_schemas = _origin_overlay_schemas(corpus_root, origin_schema, origin_uri)
    recipes = hashing.resolve_recipes(mt_schema, overlay_schemas)
    hash_values = hashing.compute_hashes(src, recipes)

    # The origin overlay id the minting origin resolved to (spec §12.1.1 (23)) — computed
    # ONCE here and threaded into both `mint_stub`'s put decision and this function's own
    # display recomputation below, so the two `placement.ingest_destination` calls see
    # identical inputs and can never disagree on where the bytes landed.
    origin_overlay_id = _resolve_origin_overlay_id(corpus_root, origin_schema, origin_uri)

    def _pre_attest(post: frontmatter.Post) -> None:
        _emit_sidecar_issues(post, sidecar)
        # Stage an enrichment sidecar (a yt-dlp `.info.json`) as `capture/<hash>.info.json`
        # BEFORE attestation so the sidecar-lift can consume it (spec §7.2, §8.1).
        _relocate_info_sidecar(src, record_id)

    mint_stub(
        corpus_root,
        src,
        record_id=record_id,
        media_type=media_type,
        extension=extension,
        record_file=record_file,
        hash_values=hash_values,
        origin_uri=origin_uri,
        origin_snapshot=origin_at,
        origin_fields=origin_fields,
        origin_schema=origin_schema,
        touch_script="ingest",
        store_bytes=True,
        pre_attest=_pre_attest,
        origin_overlay_id=origin_overlay_id,
    )

    _cleanup_sidecar(src)
    _cleanup_enrichment(corpus_root, record_id)

    # The placement decision (spec §12.1.1, v22/v23) is recomputed here — cheap (config-only,
    # no I/O) and deterministic — purely to report where `mint_stub` actually put the
    # bytes. `origin_overlay_id` is the SAME value passed to `mint_stub` above, so this call
    # and mint_stub's internal one see identical inputs and agree by construction. A
    # claiming store location's path is outside corpus_root in general, so it prints
    # `{location}:{absolute path}` rather than `.relative_to(corpus_root)`, which would
    # raise ValueError on it; the co-located case keeps its familiar relative form.
    dest_loc = placement.ingest_destination(corpus_root, media_type, origin_schema=origin_overlay_id)
    if dest_loc is not None:
        binary_display = f"{dest_loc.name}:{placement.location_artifact_path(dest_loc, record_id, extension)}"
    else:
        binary_display = str(store.local_path(record_id, extension).relative_to(corpus_root))

    print(f"new stub: {record_file.relative_to(corpus_root)}")
    print(f"  hash:       {record_id}")
    print(f"  media_type: {media_type}")
    print(f"  binary:     {binary_display}")
    if hash_values:
        print(f"  hashes:     {', '.join(v.encoded() for v in hash_values)}")
    return 0


def mint_stub(
    corpus_root: Path,
    src: Path,
    *,
    record_id: str,
    media_type: str,
    extension: str,
    record_file: Path,
    hash_values: list,
    origin_uri: str | list[str] | None,
    origin_snapshot: str,
    origin_fields: dict[str, Any] | None,
    origin_schema: str | None,
    touch_script: str,
    store_bytes: bool = True,
    pre_attest: Callable[[frontmatter.Post], None] | None = None,
    origin_overlay_id: str | None = None,
) -> frontmatter.Post:
    """The shared record-minting core (spec §8.1) for a materialized file whose identity
    and recipe union the caller has already resolved: frontmatter `hash:`, artifact block,
    first origin block, byte-fact attestation (`derive.attest`, best-effort), and hash-index
    rows (spec §12.9.1). Used by both `corpus ingest` (`store_bytes=True`: `src` is persisted
    via `placement.ingest_destination` — a claiming store location (§12.1.1, v22) when one
    exists, else `store.put` into the co-located tree — and the staging copy unlinked) and
    `corpus location promote` (`store_bytes=False`, spec §12.1.1: `src` stays exactly where
    it is — bytes stay resident at their attached-location path, never copied into
    `artifacts/`).
    `store_bytes` is the ONLY behavioral difference between the two callers. Attestation
    reads the record's bytes back through `containment.ensure_local_bytes`, which for a
    `store_bytes=False` mint resolves them through the location index (§12.1.1) rather than
    the store — no special-casing needed here.

    `pre_attest`, when given, runs on the freshly-built post BEFORE attestation — ingest's
    hook for capture-sidecar issue replay + info-sidecar relocation, concerns a location
    promotion has none of.

    `origin_overlay_id` (spec §12.1.1 (23)) is the origin overlay id the minting origin
    resolved to — the value `placement.ingest_destination`'s origin axis matches
    `ingest_origins` against, threaded through by the caller (`_resolve_origin_overlay_id`
    in this module) so it agrees by construction with any display-side recomputation of
    the same placement decision. `None` (a location-promotion caller has no minting
    origin to resolve, or ingest matched no overlay) skips the origin axis entirely —
    only the format claim / default / co-located fallback apply.

    Never folds into an existing record — the caller checks `record_file.is_file()` first;
    each caller has its own fold/re-encounter convention, since their origin shapes differ
    enough (capture URL vs. containment lineage vs. `file://` location provenance) that a
    shared fold path is not the right reuse boundary."""
    from corpus import placement, records, touches
    from corpus.store import get_store

    if store_bytes:
        dest_loc = placement.ingest_destination(
            corpus_root, media_type, origin_schema=origin_overlay_id
        )
        if dest_loc is not None:
            # A claiming store location (spec §12.1.1, v22) — format list or the
            # corpus-wide default — is the destination instead of the co-located tree.
            # `put_at` may RENAME `src` away (same-device), so the unlink below is
            # tolerant of it already being gone.
            placement.put_at(dest_loc, record_id, extension, src)
        else:
            store = get_store(corpus_root)
            store.put(record_id, extension, src)
        src.unlink(missing_ok=True)

    record_hash_entries = {v.tag: v.hex for v in hash_values if v.record_resident}

    fm = records.stub_frontmatter(
        record_id=record_id,
        touch_id=touches.script_identifier(touch_script),
    )
    post = frontmatter.Post(content="", **fm)
    if record_hash_entries:
        records.set_record_hashes(post, record_hash_entries)
    # The artifact block carries no generic `title`: a capture-sidecar title (e.g. a yt-dlp
    # title) is non-primary-source metadata whose home is the origin block's `ytdlp_title`,
    # merged at draft. The frontmatter carries no `title`/`description` at birth at all
    # (spec §12.3.4) — the display pair is derived from role-marked fields (§4.2.3); see
    # `records.title_for` / `records.derived_editorial`.
    records.set_artifact_block(post, mime=media_type, fields={})
    records.append_origin_block(
        post,
        uri=origin_uri,
        snapshot=origin_snapshot,
        schema_id=origin_schema,
        fields=origin_fields or None,
    )
    if pre_attest is not None:
        pre_attest(post)
    # 3.0: attest the byte-facts at stub time (§8.1) — artifact-block fields, manifest/
    # exposable embeds, sidecar-lifted origin fields, drafter issues. The body is NOT stored
    # (the `body` op derives it on demand). Best-effort: a type with no drafter or unreadable
    # bytes stays a bare stub, attestable later via `corpus reattest`.
    _attest_stub(post, corpus_root, record_id)
    records.dump(post, record_file)

    # Record-resident values land in the index too (spec §2/§7.9); every other resolved value
    # is index-ONLY. Best-effort: the index is deployment state (§12.9.1), never authoritative
    # — a write failure here must never fail a mint that otherwise succeeded.
    _write_hash_index_rows(corpus_root, record_id, hash_values)
    return post


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


def _origin_overlay_schemas(
    corpus_root: Path, origin_schema: str | None, origin_uri: str | None
) -> list[dict[str, Any]]:
    """The origin overlay schema(s) whose `derived_hashes:` layers into the ingest-time
    recipe union (spec §7.9's third layer, producer knowledge). The sidecar-declared overlay
    id wins when present — the same resolution the chrome-strip declaration already uses
    (`_sidecar_origin_schema`, §12.3.13) — otherwise every overlay the capture URI matches
    (`schemas.origin_overlays_for_uris`). Neither present yields no overlay layer at all: the
    mime schema + corpus-wide default set is the correct floor (§7.9) for a uri-less local
    file or an undeclared producer."""
    from corpus import schemas

    if origin_schema:
        overlay = schemas.load_origin_overlay_by_id(corpus_root, origin_schema)
        return [overlay] if overlay else []
    if origin_uri:
        return [schema for _id, schema in schemas.origin_overlays_for_uris(corpus_root, [origin_uri])]
    return []


def _resolve_origin_overlay_id(
    corpus_root: Path, origin_schema: str | None, origin_uri: str | None
) -> str | None:
    """The origin overlay id the minting origin resolved to (spec §12.1.1 (23)) — the
    value `placement.ingest_destination`'s origin axis matches a location's
    `ingest_origins` against. The overlay IS the origin's identity (no second pattern
    syntax), so this mirrors `_origin_overlay_schemas`'s resolution — sidecar-declared
    overlay id wins when present, else the first overlay the capture URI matches
    (`schemas.origin_overlays_for_uris`'s declaration order) — but returns the id
    itself rather than the schema bodies `_origin_overlay_schemas` layers for hashing.
    A sidecar-declared id that doesn't resolve to a real overlay, or no uri/schema at
    all, yields `None`: an artifact minted with no matched origin overlay can never
    satisfy an origin claim."""
    from corpus import schemas

    if origin_schema:
        return origin_schema if schemas.load_origin_overlay_by_id(corpus_root, origin_schema) else None
    if origin_uri:
        matches = schemas.origin_overlays_for_uris(corpus_root, [origin_uri])
        if matches:
            return matches[0][0]
    return None


def _write_hash_index_rows(corpus_root: Path, record_id: str, hash_values: list) -> None:
    """Mirror every resolved recipe value into the derived hash index (spec §12.9.1) —
    record-resident and index-only alike, since the index is a superset view over both. The
    index is deployment state in the resolver-cache mold: untracked, never authoritative, so a
    write failure here is reported and swallowed rather than failing an otherwise-successful
    ingest."""
    if not hash_values:
        return
    from corpus import hashindex

    try:
        with hashindex.open_index(corpus_root) as conn:
            hashindex.upsert_rows(
                conn,
                [
                    hashindex.HashRow(
                        record_id=record_id, recipe=v.recipe, algo=v.tag, value=v.hex, param=v.param
                    )
                    for v in hash_values
                ],
            )
    except Exception as exc:  # deployment state (§12.9.1) — never fails ingest
        print(f"  note: hash-index write failed for {record_id[:12]}…: {exc}", file=sys.stderr)


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


def _sidecar_origin_schema(src: Path) -> str | None:
    """Best-effort, READ-ONLY peek at the staged sidecar's `origin_schema` value — used
    only to namespace-walk the chrome-strip declaration (spec §12.3.13). Tolerant of an
    absent or malformed sidecar (treated as no stamp); does NOT consume the sidecar —
    `_read_sidecar` re-reads it moments later for the origin-block seed proper."""
    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    if not sidecar_path.is_file():
        return None
    try:
        with sidecar_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    value = str(data.get("origin_schema") or "").strip()
    return value or None


def _canonicalize_mbox(corpus_root: Path, src: Path, media_type: str) -> dict[str, Any]:
    """The mailbox chrome strip at ingest (spec §12.3.13). Resolves `strip_headers`
    through the ORIGIN chain — the staged file's sidecar `origin_schema` stamp (when
    present) namespace-walked, else the mime schema's `default_origin` binding walked
    the same way (`schemas.resolve_strip_headers`) — and, for an `application/mbox`
    staged file with a non-empty result, rewrites it in place with those headers removed
    from every member's header zone — the stripped bytes are the stored bytes, identity
    is computed over them — and returns the origin-field provenance
    (`stripped_headers`, `stripped_members`, and `source_transport`, the delivered
    bytes' blake3, so the pre-strip identity is never silently lost). Returns `{}` when
    no strip is declared, the file holds no messages (parse tolerance), or no member
    carries a declared header (already canonical — e.g. a window bundle emitted
    stripped)."""
    if media_type != "application/mbox":
        return {}
    from corpus import hashing, mboxfile, records, schemas

    origin_id = _sidecar_origin_schema(src)
    names = schemas.resolve_strip_headers(corpus_root, media_type, origin_id=origin_id)
    if not names:
        return {}
    resolved_origin_id = origin_id or schemas.resolve_default_origin(corpus_root, media_type)
    strip = mboxfile.normalize_strip_headers(names)
    scan = mboxfile.scan(src, None, strip=strip)
    if not scan.count or not scan.stripped_members:
        return {}
    delivered = hashing.hash_file(src)["blake3"]
    tmp = src.with_name(src.name + ".canonical")
    with tmp.open("wb") as out:
        mboxfile.extract_raw_members(src, set(range(1, scan.count + 1)), out, strip=strip)
    tmp.replace(src)
    print(
        f"  chrome-strip active (origin {resolved_origin_id}): {', '.join(names)} removed "
        f"from {scan.stripped_members}/{scan.count} member(s) "
        f"(delivered blake3:{delivered[:12]}…)"
    )
    return {
        "stripped_headers": list(names),
        "stripped_members": scan.stripped_members,
        "source_transport": records.format_hash("blake3", delivered),
    }


def _canonicalize_json(corpus_root: Path, src: Path, media_type: str) -> dict[str, Any]:
    """The JSON-family field strip at ingest (spec §12.3.14) — the mailbox chrome strip's
    amendment, for a STANDALONE `application/json` staged file. Mirrors
    `_canonicalize_mbox` exactly: resolves `strip_fields` through the same origin chain
    (the staged file's sidecar `origin_schema` stamp namespace-walked, else the mime
    schema's `default_origin` binding walked the same way,
    `schemas.resolve_strip_fields`), and for a non-empty result rewrites the file in
    place with those dotted-path key spans removed SPAN-SURGICALLY (`jsonfields.
    strip_spans`) — the stripped bytes are the stored bytes, identity is computed over
    them — returning the origin-field provenance (`stripped_fields`,
    `stripped_field_count`, and `source_transport`, the delivered bytes' blake3, so the
    pre-strip identity is never silently lost). Returns `{}` when no strip is declared,
    the staged file isn't valid JSON at all (parse tolerance — a malformed document is
    left byte-identical, never repaired; ordinary ingest still proceeds against it), or
    nothing in the document matches (already canonical — e.g. a re-drop of already-
    stripped bytes).

    Container members are NOT touched here — extraction/staging is where canonicalization
    happens (carried over verbatim from the mbox caveat, §12.3.13): a JSON document
    living inside an ingested archive stays byte-identical to its container route;
    assemble-time wiring for a JSON-family container (the real Discord/Meta export tree
    shape) lands with that onboarding."""
    if media_type != "application/json":
        return {}
    from corpus import hashing, jsonfields, records, schemas

    origin_id = _sidecar_origin_schema(src)
    paths = schemas.resolve_strip_fields(corpus_root, media_type, origin_id=origin_id)
    if not paths:
        return {}
    matchers = jsonfields.normalize_strip_fields(paths)
    if not matchers:
        return {}
    resolved_origin_id = origin_id or schemas.resolve_default_origin(corpus_root, media_type)
    try:
        data = src.read_bytes()
        stripped, removed = jsonfields.strip_spans(data, matchers)
    except jsonfields.JSONParseError as exc:
        print(f"  strip-fields: {src.name} is not valid JSON ({exc}) — left as-is", file=sys.stderr)
        return {}
    if not removed:
        return {}
    delivered = hashing.hash_file(src)["blake3"]
    tmp = src.with_name(src.name + ".canonical")
    tmp.write_bytes(stripped)
    tmp.replace(src)
    print(
        f"  strip-fields active (origin {resolved_origin_id}): {', '.join(paths)} — "
        f"{removed} field(s) removed (delivered blake3:{delivered[:12]}…)"
    )
    return {
        "stripped_fields": list(paths),
        "stripped_field_count": removed,
        "source_transport": records.format_hash("blake3", delivered),
    }


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
