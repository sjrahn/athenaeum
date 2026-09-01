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

Compressed single-member envelope collapse (spec §2, the payload-identity principle,
v32): a bare gzip stream, or a zip holding exactly one non-directory unencrypted
member, mints under the PAYLOAD's identity — the envelope unwraps before identity is
computed, so the same content delivered bare or wrapped mints the same record. The
envelope's own transport hash attests as delivery provenance in frontmatter `hash:`
(`_collapse_compressed_envelope`, below).
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

    # `orig_src` stays pinned to the file exactly as staged — the compressed-envelope
    # collapse below (spec §2, v32) may rename `src` to the recovered inner filename
    # (needed for correct mime re-detection, since a stale wrapper extension like
    # `.zip` would otherwise misdetect the unwrapped bytes), so every sidecar lookup
    # keyed to the AS-STAGED path (the `.capture.yaml` sidecar, a yt-dlp `.info.json`
    # companion) reads `orig_src`, never the post-collapse `src`.
    orig_src = src
    sidecar = _read_sidecar(orig_src)

    media_type = mime.detect(src, corpus_root)

    # Compressed single-member envelope collapse (spec §2, the payload-identity
    # principle, v32) — BEFORE mime-schema resolution and the mbox/json chrome strips,
    # so the unwrapped payload composes with whatever ingest does next exactly as its
    # bare delivery would (§2's "every wrapper removed"). Runs first because a bare
    # gzip stream has no mime schema of its own at all — there is nothing to resolve
    # until the payload is in hand. `src` may come back renamed (never moved out of
    # its staging directory) or replaced in place; either way it now holds the fully-
    # unwrapped bytes.
    src, media_type, envelope_hash_values, envelope_fields = _collapse_compressed_envelope(
        corpus_root, src, media_type
    )

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

    origin_uri, origin_at, origin_fields, origin_schema = _derive_capture_origin(
        src, sidecar, media_type
    )
    origin_fields.update(strip_provenance)
    origin_fields.update(envelope_fields)

    if record_file.is_file():
        post = records.load(record_file)
        appended = _append_origin_if_new(
            post, origin_uri, origin_at, origin_fields, origin_schema
        )
        if envelope_hash_values:
            # A collapsed-envelope re-encounter (spec §2, v32) — the payload was already
            # ingested bare (or via a different envelope) and this delivery folds into it
            # exactly as re-capturing identical bytes folds today; the envelope's own
            # transport hash still attests as delivery provenance on THIS delivery.
            records.set_record_hashes(post, envelope_hash_values)
        touches.record_touch(post, touches.script_identifier("ingest"))
        records.dump(post, record_file)
        src.unlink()
        _cleanup_sidecar(orig_src)
        _relocate_info_sidecar(orig_src, record_id)
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
        if envelope_hash_values:
            # The envelope's transport hash (spec §2, v32) — attested onto the freshly
            # built stub's `hash:` field here (not via `hash_values` above, which is the
            # §7.9 derived-hash recipe union machinery and its own hash-index write; the
            # envelope hash is ad hoc delivery provenance, the mbox `source_transport`
            # shape (§12.3.13) pointed at `hash:` instead of an origin field).
            records.set_record_hashes(post, envelope_hash_values)
        _emit_sidecar_issues(post, sidecar)
        # Stage an enrichment sidecar (a yt-dlp `.info.json`) as `capture/<hash>.info.json`
        # BEFORE attestation so the sidecar-lift can consume it (spec §7.2, §8.1).
        _relocate_info_sidecar(orig_src, record_id)

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

    _cleanup_sidecar(orig_src)
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


# The §7.6 tag for the envelope's transport hash (below): a bare algorithm id — the
# value is byte-stable (raw blake3 of the as-delivered bytes, no canonicalization) and
# directly verifiable against the delivered file, exactly the mbox `source_transport`
# shape. Scope-qualified (`blake3-<qualifier>`, the `blake3-64k`/`blake3-4k` idiom)
# rather than bare `blake3`: unlike `source_transport` (its own named origin field),
# `hash:` is a shared multi-purpose field, and a bare `blake3` entry there would read
# as a second copy of the record's own `id` (§7.6: "the primary blake3 … lives on `id`
# and is not duplicated here") rather than the envelope's DIFFERENT bytes.
_ENVELOPE_HASH_TAG = "blake3-envelope"

_ENVELOPE_CHUNK = 1 << 20


def _collapse_compressed_envelope(
    corpus_root: Path, src: Path, media_type: str
) -> tuple[Path, str, dict[str, str], dict[str, Any]]:
    """Ingest-time compressed single-member envelope collapse (spec §2, the
    payload-identity principle, v32): a gzip'd single stream, or a zip holding exactly
    one non-directory, unencrypted member, mints under the *payload's* identity — the
    envelope is packaging, never identity (the §1.2 pure-envelope rule, pulled forward
    to ingest for the compressed case, where the same content delivered bare or
    wrapped must mint the same record). Repeatedly unwraps `src` in place — recursing
    while the freshly-unwrapped bytes are themselves a further collapsible envelope (a
    zip-of-one holding a `.gz`, say) — per §2's "every wrapper removed."

    Returns `(final_src, final_media_type, envelope_hash_values, origin_fields)`:

    - `final_src` — `src` unchanged when nothing collapsed; otherwise the file now
      holding the fully-unwrapped payload bytes, possibly RENAMED (never moved out of
      its staging directory) to the recovered inner filename — needed for correct
      mime re-detection, since the stale wrapper name (a `.zip` extension over what is
      now, say, extensionless JSON) would otherwise misdetect the payload, or worse,
      silently misattribute it to the wrapper's own type via the `mimetypes` fallback.
    - `envelope_hash_values` — `{}` when nothing collapsed; otherwise
      `{_ENVELOPE_HASH_TAG: <hex>}`, the AS-DELIVERED envelope's blake3 (computed once,
      before any unwrap — later nested layers are packaging over packaging and are not
      separately attested) for the caller to merge into frontmatter `hash:`.
    - `origin_fields` — `{}` when nothing collapsed; otherwise `envelope_kind`
      (`"gzip"` | `"zip"`, or a list across nested layers, outermost first) and, where
      recovered, `envelope_filename` (the gzip FNAME field or the zip member's archive
      path — the delivery's own name for the payload) in the same scalar-or-list
      shape, kept as the "original filename provenance" the amendment calls for.

    A media container (single-track or otherwise) is explicitly out of scope here — it
    reduces via the §1.2 one-row-manifest rule at promotion time, a parallel
    concern this function never touches. Neither is a plain (uncompressed) `.tar` or a
    gzip-wrapped `.tgz`: `mime.detect` already resolves a gzip-wrapped tar straight to
    `application/x-tar` (§12.3.2) before this function ever sees it — tar's member
    concatenation is not itself a compression wrapper, so the tool-version-drift
    rationale this collapse exists for (§2) doesn't reach it; a single-member tar
    stays the ordinary tar-manifest path, unchanged, reducible only at promotion.

    Multi-member archives are untouched (the ordinary manifest path); an encrypted zip
    member, a directory-only "member", a non-empty archive comment (declared content,
    not packaging — a `corpus session capture` single-transcript bundle among them),
    or a corrupt/truncated stream leave `src` byte-identical and print a note — no
    collapse, ingest proceeds exactly as before this amendment (the edge law). So does
    a payload whose fully-unwrapped type has no
    mime schema at all: a zip-manifest ingest of a member type that isn't independently
    ingestable today must keep working exactly as it does today — collapsing into an
    unmintable stub would be a regression, not a faithful reading of "the same content
    mints the same record" (there is no bare-ingest route to compare against when the
    payload's own type can't be ingested at all). The whole chain therefore runs over a
    SCRATCH copy first, committed onto the real `src` only once the final payload type
    is confirmed to resolve a schema; nothing touches `src` itself otherwise."""
    from corpus import hashing, mime, schemas

    if media_type not in ("application/gzip", "application/zip"):
        return src, media_type, {}, {}

    delivered = hashing.hash_file(src, also=())["blake3"]  # as-staged, before any unwrap

    import shutil

    # A PREFIX, not a suffix: mime re-detection's `mimetypes` fallback (below, when no
    # layer recovers a rename-worthy filename) reads the trailing extension chain — a
    # scratch copy named `export.json.gz.envelope-scratch` would break the exact
    # compound-suffix stripping (`.gz` → `.json` → `application/json`) that lets a
    # conventionally-named `.json.gz` detect correctly with no FNAME at all.
    scratch = src.with_name("envelope-scratch~" + src.name)
    shutil.copy2(src, scratch)

    layers: list[dict[str, str]] = []
    current = scratch
    current_media_type = media_type
    while True:
        if current_media_type == "application/gzip":
            result = _try_unwrap_gzip(current)
        elif current_media_type == "application/zip":
            result = _try_unwrap_single_member_zip(current)
        else:
            result = None
        if result is None:
            break
        current, layer = result
        layers.append(layer)
        current_media_type = mime.detect(current, corpus_root)

    if not layers or schemas.load_mime_schema(corpus_root, current_media_type) is None:
        current.unlink(missing_ok=True)  # discard the scratch chain; `src` is untouched
        return src, media_type, {}, {}

    # Commit: the scratch chain's final file replaces `src` for real.
    src.unlink(missing_ok=True)
    if current == scratch:  # no layer recovered a rename-worthy filename
        scratch.replace(src)
        current = src
    src = current

    kinds = [layer["kind"] for layer in layers]
    filenames = [layer["filename"] for layer in layers if layer.get("filename")]
    origin_fields: dict[str, Any] = {"envelope_kind": kinds[0] if len(kinds) == 1 else kinds}
    if filenames:
        origin_fields["envelope_filename"] = filenames[0] if len(filenames) == 1 else filenames
    print(
        f"  envelope collapse ({'→'.join(kinds)}): payload identity minted "
        f"(delivered {_ENVELOPE_HASH_TAG}:{delivered[:12]}…)"
    )
    return src, current_media_type, {_ENVELOPE_HASH_TAG: delivered}, origin_fields


def _place_unwrapped(src: Path, tmp: Path, recovered_name: str | None) -> Path:
    """Move freshly-unwrapped bytes at `tmp` into place, named for correct mime
    re-detection: the recovered inner filename's BASENAME (directory components
    stripped, so a zip member's archive path or a gzip FNAME value can never escape
    the staging directory — no zip-slip surface) when one exists and doesn't collide
    with an unrelated file already staged beside `src`; otherwise `src`'s own name
    (best-effort — an extensionless payload still gets a fair shot at magic-byte
    detection). Consumes `tmp`; removes the old `src` when the target differs from it.
    Returns the final path."""
    target = src
    if recovered_name:
        base = Path(recovered_name).name.strip()
        if base and base not in (".", ".."):
            candidate = src.with_name(base)
            if candidate == src or not candidate.exists():
                target = candidate
    tmp.replace(target)
    if target != src:
        src.unlink(missing_ok=True)
    return target


def _try_unwrap_gzip(src: Path) -> tuple[Path, dict[str, str]] | None:
    """One gzip-unwrap step (spec §2, v32): decompresses `src`, streaming (a tmp file,
    then `_place_unwrapped`) — the tmp-then-replace pattern the mbox/json strip
    helpers use. A gzip stream is a single compressed stream by nature — no member
    count to check, unlike zip. Returns `(new_path, {"kind": "gzip", ...})`, with
    `"filename"` present when the stream's optional FNAME header (RFC 1952 — stdlib's
    `gzip` module reads and discards it; `_gzip_header_filename` hand-parses it back)
    names the original file. Returns `None` — no collapse, `src` untouched, ingest
    proceeds against the gzip bytes exactly as before this amendment — on a corrupt or
    truncated stream, or an empty decompressed result (gzip has no encrypted-archive
    analogue, so those are the only two failure modes here)."""
    import gzip
    import zlib

    filename = _gzip_header_filename(src)
    tmp = src.with_name(src.name + ".envelope-unwrapped")
    try:
        with gzip.open(src, "rb") as gz, tmp.open("wb") as out:
            while chunk := gz.read(_ENVELOPE_CHUNK):
                out.write(chunk)
    except (OSError, EOFError, zlib.error) as exc:
        tmp.unlink(missing_ok=True)
        print(
            f"  envelope collapse: {src.name} is not a well-formed gzip stream ({exc})"
            " — ingesting the envelope as-is",
            file=sys.stderr,
        )
        return None
    if tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        print(
            f"  envelope collapse: {src.name} decompressed to zero bytes — "
            "ingesting the envelope as-is",
            file=sys.stderr,
        )
        return None
    new_path = _place_unwrapped(src, tmp, filename)
    layer: dict[str, str] = {"kind": "gzip"}
    if filename:
        layer["filename"] = filename
    return new_path, layer


def _try_unwrap_single_member_zip(src: Path) -> tuple[Path, dict[str, str]] | None:
    """One zip-unwrap step (spec §2, v32): a raw (unrefined) `application/zip` holding
    exactly one member collapses to that member's bytes when it's a regular file, not
    a directory, and not password-protected — a structured zip (docx/xlsx/epub/jar/…)
    never reaches here, since `mime.detect` refines it to its own MIME first (§1.2:
    "never reduces regardless of count"). Extracts the member (the same tmp-then-
    place pattern) and returns `(new_path, {"kind": "zip", "filename": <member path>})`.
    Returns `None` — no collapse; `src` untouched; ingest proceeds against the zip as
    the ordinary zip-manifest it already is today — for a multi-member archive (the
    common case, unchanged), a lone directory-only entry, an encrypted member, a
    corrupt/unreadable archive, or a NON-EMPTY archive comment (the edge law; a
    comment is declared content, not packaging — `application_zip.yaml`'s own
    `extended_fields.comment` role-marks it `title`, the identity string the corpus's
    own assembly/session-capture tooling stamps there, e.g. a single-transcript
    `corpus session capture` bundle — collapsing would silently discard it)."""
    import zipfile

    try:
        with zipfile.ZipFile(src) as zf:
            if zf.comment.strip():
                print(
                    f"  envelope collapse: {src.name} carries a non-empty archive "
                    "comment (declared content, not packaging) — ingesting the zip as "
                    "a manifest",
                    file=sys.stderr,
                )
                return None
            infolist = zf.infolist()
            if len(infolist) != 1:
                return None
            entry = infolist[0]
            if entry.is_dir():
                print(
                    f"  envelope collapse: {src.name}'s one entry is a directory — "
                    "ingesting the zip as a manifest",
                    file=sys.stderr,
                )
                return None
            if entry.flag_bits & 0x1:  # general-purpose bit 0: member is encrypted
                print(
                    f"  envelope collapse: {src.name}'s one member is encrypted — "
                    "ingesting the zip as a manifest",
                    file=sys.stderr,
                )
                return None
            data = zf.read(entry)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
        print(
            f"  envelope collapse: {src.name} could not be unwrapped ({exc}) — "
            "ingesting the zip as a manifest",
            file=sys.stderr,
        )
        return None

    tmp = src.with_name(src.name + ".envelope-unwrapped")
    tmp.write_bytes(data)
    new_path = _place_unwrapped(src, tmp, entry.filename)
    return new_path, {"kind": "zip", "filename": entry.filename}


def _gzip_header_filename(path: Path) -> str | None:
    """Best-effort recovery of a gzip stream's optional FNAME header field (RFC 1952)
    — stdlib's `gzip` module reads and discards it (no public accessor), so a small
    hand-parse of the fixed 10-byte header plus optional fields recovers it for
    envelope provenance. Pure stdlib, deterministic. `None` when the stream carries no
    FNAME (the common case — most producers don't set it), is truncated before the
    header completes, or isn't gzip-magic'd at all."""
    import struct

    FEXTRA = 0x04
    FNAME = 0x08
    try:
        with path.open("rb") as fh:
            header = fh.read(10)
            if len(header) < 10 or header[:2] != b"\x1f\x8b":
                return None
            flag = header[3]
            if flag & FEXTRA:
                raw = fh.read(2)
                if len(raw) < 2:
                    return None
                (xlen,) = struct.unpack("<H", raw)
                fh.read(xlen)
            if not flag & FNAME:
                return None
            name = bytearray()
            while True:
                b = fh.read(1)
                if not b or b == b"\x00":
                    break
                name += b
    except OSError:
        return None
    return name.decode("latin-1") or None


def _canonicalize_mbox(corpus_root: Path, src: Path, media_type: str) -> dict[str, Any]:
    """The mailbox chrome strip AND the `exclude_members` policy filter (spec §12.3.13,
    v37) at ingest — canonicalize-at-entry, one pass. Resolves both through the ORIGIN
    chain — the staged file's sidecar `origin_schema` stamp (when present) namespace-
    walked, else the mime schema's `default_origin` binding walked the same way
    (`schemas.resolve_strip_headers` / `schemas.resolve_exclude_members`) — and, for an
    `application/mbox` staged file, rewrites it in place: declared headers dropped from
    every member's header zone, and any member the exclusion predicate matches (read
    BEFORE the strip removes its header — same pass) dropped ENTIRELY — the surviving,
    stripped bytes are the stored bytes, identity is computed over them. Returns the
    origin-field provenance (`stripped_headers`/`stripped_members` and/or
    `policy_excluded_count`, plus `source_transport`, the delivered bytes' blake3, so the
    pre-canonicalization identity is never silently lost). Returns `{}` when neither a
    strip nor an exclusion is declared, the file holds no messages (parse tolerance), or
    neither touched anything (already canonical — e.g. a window bundle emitted stripped
    with nothing to exclude)."""
    if media_type != "application/mbox":
        return {}
    from corpus import hashing, mboxfile, records, schemas

    origin_id = _sidecar_origin_schema(src)
    names = schemas.resolve_strip_headers(corpus_root, media_type, origin_id=origin_id)
    predicates = schemas.resolve_exclude_members(corpus_root, media_type, origin_id=origin_id)
    strip = mboxfile.normalize_strip_headers(names)
    exclude = mboxfile.normalize_exclude_members(predicates)
    if not names and not exclude:
        return {}
    resolved_origin_id = origin_id or schemas.resolve_default_origin(corpus_root, media_type)
    scan = mboxfile.scan(src, None, strip=strip, exclude=exclude)
    if not scan.count or (not scan.stripped_members and not scan.excluded_ordinals):
        return {}
    delivered = hashing.hash_file(src)["blake3"]
    keep_ordinals = set(range(1, scan.count + 1)) - scan.excluded_ordinals
    tmp = src.with_name(src.name + ".canonical")
    with tmp.open("wb") as out:
        mboxfile.extract_raw_members(src, keep_ordinals, out, strip=strip)
    tmp.replace(src)
    notes = []
    fields: dict[str, Any] = {}
    if names and scan.stripped_members:
        notes.append(
            f"{', '.join(names)} removed from {scan.stripped_members}/{scan.count} member(s)"
        )
        fields["stripped_headers"] = list(names)
        fields["stripped_members"] = scan.stripped_members
    if scan.excluded_ordinals:
        notes.append(f"{len(scan.excluded_ordinals)}/{scan.count} member(s) policy-excluded")
        fields["policy_excluded_count"] = len(scan.excluded_ordinals)
    print(
        f"  chrome-strip/exclude_members active (origin {resolved_origin_id}): "
        f"{'; '.join(notes)} (delivered blake3:{delivered[:12]}…)"
    )
    fields["source_transport"] = records.format_hash("blake3", delivered)
    return fields


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
    `imessage-export` carrying `chat_name`/`phone_number`/`period`.

    A web capture's `snapshot_engine:` (spec §12.3.6 — the resolved SingleFile asset
    identity, or the disclosed rendered-DOM degrade) rides the same sidecar and lands
    here as an ordinary extended field, exactly like an `origin_fields:` declaration."""
    from corpus import singlefile, touches

    uri = str(sidecar.get("source_url") or "").strip()
    discovered_at = str(sidecar.get("fetched_at") or "").strip() or touches.now_iso()
    schema_id = str(sidecar.get("origin_schema") or "").strip() or None
    declared = sidecar.get("origin_fields")
    extra: dict[str, Any] = {str(k): v for k, v in declared.items()} if isinstance(declared, dict) else {}
    snapshot_engine = str(sidecar.get("snapshot_engine") or "").strip()
    if snapshot_engine:
        extra["snapshot_engine"] = snapshot_engine
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
            detector=str(detector),
            fields=entry.get("fields") or None,
        )
