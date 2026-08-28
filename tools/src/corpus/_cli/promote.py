"""Promote a container member to a first-class record (spec §8.1).

    corpus promote 'corpus://<container-id>?<member-address>'

Mints a record for bytes that already live inside a container, WITHOUT copying them: the
member is located by its embed declaration on the container's record (container id + member
address, §2), its bytes streamed and blake3-verified against the embed's recorded `transport:`
hash (a hard error on mismatch — a promoted `id` must equal the member's true blake3), MIME
detected from the streamed head, and a stub emitted whose first origin block records the
containment lineage **as history** — `uri: corpus://<container-id>?<member-address>` plus the
universal `filename` / `source_modified` from the archive metadata. The bytes stay in the
container, resolvable by the promoted `id` through the member index (§12.9).

Re-promoting the same member folds like a re-capture (§5.2): if a record with that id already
exists — a prior promote, or a standalone ingest of the same bytes — the containment origin is
appended to it rather than erroring. Streaming throughout, so a multi-GB member never loads
whole.

*(v41, §7.2)* When the CONTAINER's origin overlay declares a `sidecar:`, the member's paired
sidecar (a sibling roster member, found by the declared pairing template) is read out of the
container, projected per the declared lift map onto the lineage origin block as
`<prefix><field>` fields plus roster-resolved sibling references, and the block is qualified
`<id>/<subtype>`. A consumed sidecar's own address is refused — it is never a record of its
own. The engine is producer-agnostic: what pairs with what, and what lifts where, is entirely
the declaration's (`corpus.sidecar`); `corpus reattest` regenerates the lift from the container.

The same stream also computes the member's resolved derived-hash recipe union (§7.9): the
corpus-wide default set layered with the member's own mime schema's `derived_hashes:` — no
origin overlay layer, since a promoted member's origin is containment lineage, never a producer
URI. `residency: record` values land on the minted stub's `hash:`; every resolved value lands
in the derived hash index (§12.9.1), best-effort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import IO, Any

import blake3
import frontmatter

from corpus import (
    containment,
    hashindex,
    hashing,
    mime,
    paths,
    records,
    schemas,
    sidecar,
    streams,
    touches,
)
from corpus import functional_uri as furi
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

# Read a generous head for MIME sniffing — enough to reach the tar `ustar` magic at offset 257
# (mime._SNIFF_BYTES). A member smaller than this streams whole into the head buffer.
_HEAD = 512
_CHUNK = 1 << 20

# The prefix-ladder rungs (spec §7.9's registry table) — mirrored here rather than imported
# from `corpus.hashing` (private there) because a container member is never a standalone Path:
# it is streamed straight out of the container, so its recipe values are computed in the SAME
# pass as the identity blake3 (`_sniff_and_hash` below) rather than via `hashing.compute_hashes`
# (which needs a materialized file) — a second pass over a multi-GB member is exactly what the
# streaming design exists to avoid.
_LADDER_RUNGS: tuple[tuple[int, str], ...] = (
    (4 * 1024, "blake3-4k"),
    (64 * 1024, "blake3-64k"),
    (1024 * 1024, "blake3-1m"),
)


def _stream_identity_and_recipe_hashes(
    head: bytes, fp: IO[bytes], recipes: tuple[hashing.Recipe, ...]
) -> tuple[str, list[hashing.HashValue]]:
    """Stream `head` + the rest of `fp` exactly once, computing the blake3 identity digest
    (spec §2) alongside every value of `recipes` (spec §7.9) — the member-stream analogue of
    `hashing.hash_file` + `hashing.compute_hashes` combined (both need a standalone Path; a
    container member is never one — it is streamed straight out of the container, so identity
    and recipes share this one pass rather than two, spec §8.1's "while the bytes are in
    hand"). `html-stampfree@1` is the one recipe that needs the whole member buffered
    (mirroring `compute_hashes`'s own note: HTML members are not the multi-gigabyte population
    this streams for)."""
    hashlib_recipes = [r for r in recipes if r.residency == "byte-stable" and not r.multivalue]
    want_ladder = any(r.multivalue for r in recipes)
    want_stampfree = any(r.id == "html-stampfree@1" for r in recipes)

    b3 = blake3.blake3()
    aux = {r.id: hashlib.new(r.id) for r in hashlib_recipes}
    ladder = {length: blake3.blake3() for length, _tag in _LADDER_RUNGS} if want_ladder else {}
    buf = bytearray() if want_stampfree else None

    def _chunks():
        if head:
            yield head
        while chunk := fp.read(_CHUNK):
            yield chunk

    bytes_read = 0
    for chunk in _chunks():
        start, end = bytes_read, bytes_read + len(chunk)
        b3.update(chunk)
        for h in aux.values():
            h.update(chunk)
        for length, hasher in ladder.items():
            if start >= length:
                continue
            take = min(length, end) - start
            if take > 0:
                hasher.update(chunk[:take])
        if buf is not None:
            buf.extend(chunk)
        bytes_read = end
    file_size = bytes_read

    values: list[hashing.HashValue] = [
        hashing.HashValue(
            recipe=r.id, tag=r.id, hex=aux[r.id].hexdigest(), record_resident=r.record_resident
        )
        for r in hashlib_recipes
    ]
    if want_ladder:
        for length, tag in _LADDER_RUNGS:
            if file_size >= length:
                values.append(
                    hashing.HashValue(
                        recipe="blake3-prefix-ladder",
                        tag=tag,
                        hex=ladder[length].hexdigest(),
                        param=str(length),
                    )
                )
    if want_stampfree:
        values.append(
            hashing.HashValue(
                recipe="html-stampfree@1",
                tag="html-stampfree@1",
                hex=hashing.html_stampfree_digest(bytes(buf or b"")),
            )
        )
    return b3.hexdigest(), values


def _write_hash_index_rows(
    corpus_root: Path, record_id: str, hash_values: list[hashing.HashValue]
) -> None:
    """Mirror `hash_values` into the derived hash index (spec §12.9.1) — best-effort
    deployment state, never authoritative: a write failure here is reported and swallowed
    rather than failing an otherwise-successful promote."""
    if not hash_values:
        return
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
    except Exception as exc:  # deployment state (§12.9.1) — never fails promote
        print(f"  note: hash-index write failed for {record_id[:12]}…: {exc}", file=sys.stderr)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "uri",
        help="A container member URI: corpus://<container-id>?<member-address> "
        "(e.g. ?path=Takeout/Mail/foo.mbox).",
    )
    parser.add_argument("--json", action="store_true", help="emit the result as JSON.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    try:
        parsed = furi.parse(args.uri)
    except ValueError as e:
        sys.exit(str(e))
    if parsed.is_bare:
        sys.exit(
            "promote needs a member address: corpus://<container-id>?<member-address> "
            "(a bare corpus://<id> names no member)."
        )
    container_id = parsed.hash
    containment_uri = furi.canonical(parsed)
    # The address to match against the embed + extract by — reserved chars decoded (§6.1).
    member_address = "&".join(
        k if v is None else f"{k}={furi.unquote_value(v)}" for k, v in parsed.params
    )

    # 1. The container record + the declared member embed.
    container_file = paths.record_path(corpus_root, container_id)
    if not container_file.is_file():
        sys.exit(f"no container record for {container_id} at {container_file}")
    container_post = records.load(container_file)
    container_media_type = records.media_type_for(container_post)
    embed = _find_embed(container_post, member_address)
    if embed is None:
        sys.exit(
            f"container {container_id[:12]} has no embed at {member_address!r} "
            f"(nothing to promote)."
        )
    expected_algo, _, expected_hex = str(embed.get("transport") or "").partition(":")
    if expected_algo != "blake3" or not expected_hex:
        sys.exit(
            f"embed at {member_address!r} has no blake3 transport hash "
            f"(got {embed.get('transport')!r}); cannot verify a promoted id."
        )

    # 1b. *(v41, §7.2)* The container's origin overlay MAY declare a `sidecar:` — a member
    #     whose export pairs each primary with a companion metadata member. A consumed
    #     sidecar is never a record of its own: refuse its address here, naming the primary
    #     it belongs to, BEFORE a single byte is streamed. The engine is producer-agnostic —
    #     the declaration says what pairs with what; nothing here knows what the members are.
    try:
        sidecar_decl = sidecar.declaration_for_container(corpus_root, container_post)
    except sidecar.DeclarationError as e:
        sys.exit(f"container {container_id[:12]}: {e}")
    member_path = (
        member_address[len("path=") :]
        if member_address.startswith("path=") and "&" not in member_address
        else None
    )
    roster = sidecar.container_roster(container_post) if sidecar_decl is not None else ()
    if sidecar_decl is not None and member_path is not None:
        primary = sidecar_decl.primary_of(member_path, roster)
        if primary is not None:
            sys.exit(
                f"{member_address!r} is the consumed sidecar of member {primary!r} under "
                f"the container's `sidecar:` declaration (spec §7.2 — a sidecar member is "
                f"never a record of its own): promote "
                f"corpus://{container_id}?path={primary} instead; the sidecar projects "
                f"into that record's origin block."
            )

    # 2. The container's bytes (standalone, or streamed out of a nested container).
    from corpus.store import ArtifactMissing

    try:
        container_ext = mime.extension_for(container_media_type)
        container_path = containment.ensure_local_bytes(corpus_root, container_id, container_ext)
    except ArtifactMissing as e:
        sys.exit(str(e))

    # 3. The member's durable provenance, read from the CONTAINER (§7.2, §8.1). Taken before
    #    the sniff because its `filename` is also the sniff name: an ordinal address (`part=3`)
    #    carries no extension, and the extension is what refines a zip-magic member within its
    #    family (a docx part sniffs as bare `application/zip` without it).
    #    *(3.4)* This used to read a `filename` cached on the roster row. The container is the
    #    authoritative source — a cached copy can only ever agree with it or be stale — and the
    #    3.4 roster is closed to four keys (spec §4.3.1.4), so the hint comes from the bytes.
    #    *(3.8)* An `el=` member needs the container's `addressing:` stamp to be located at
    #    all — the stamp is the grammar dispatch (§6.1.1), and resolving under the wrong
    #    grammar would mint a record for a different element.
    el_addressing = records.el_addressing(container_post)
    meta = containment.member_source_metadata(
        container_path, container_media_type, member_address, el_addressing=el_addressing
    )
    basename = containment.member_sniff_name(member_address, meta.get("filename"))

    # 4. Stream the member once: sniff MIME + compute blake3 identity plus the member schema's
    #    resolved derived-hash recipe union (spec §7.9). Never loads the member whole (§8.1 /
    #    §12.9).
    try:
        media_type, computed_id, hash_values = _sniff_and_hash(
            corpus_root,
            container_path,
            container_media_type,
            member_address,
            basename,
            el_addressing=el_addressing,
        )
    except (ValueError, OSError) as e:
        sys.exit(f"could not read member {member_address!r} from container: {e}")

    # A member whose bytes name no type takes the type the roster already attested for it.
    # The sniff still wins wherever it concludes: it read the actual bytes, where the row is
    # a record of what attestation found in the container's own tables.
    declared = str(embed.get("media_type") or "").strip()
    if media_type == "unknown" and declared:
        media_type = declared

    # *(v32, §2)* A track member's bytes are now the raw codec payload, which has no
    # reliable magic of its own by design (that is what "not reframed" means) — so for a
    # `stream_id=` address the sniff is EXPECTED to come back `unknown`, and the roster
    # row's codec-derived mime (written at attestation by `draft/_trackmanifest.py`) is
    # the real answer, already applied by the `declared` fallback above.

    # 5. Verify: a promoted id MUST equal the roster's recorded byte identity (spec §8.1).
    if computed_id != expected_hex:
        sys.exit(
            f"hash mismatch: streamed member blake3 {computed_id} != member transport "
            f"{expected_hex} — the container's declaration is stale or the bytes differ; "
            f"refusing to mint a record with a wrong id."
        )

    # 6. The containment-lineage origin block (history — never consulted for lookup, §12.9).
    origin_fields: dict[str, Any] = {}
    if meta.get("filename"):
        origin_fields["filename"] = meta["filename"]
    if meta.get("source_modified"):
        origin_fields["source_modified"] = meta["source_modified"]

    # 6a. *(v41, §7.2)* The container-member sidecar lift — resolved HERE for the same reason
    #     `cutting:` is (6b, below): this is the one moment both records are in hand. The
    #     paired sidecar member is streamed out of the container, parsed, and projected per
    #     the declaration onto the lineage origin block, which is then qualified with the
    #     declared subtype. Present-only, never invented; a member with no paired sidecar
    #     lifts nothing and stays bare. A sidecar that will not parse is a note, never a
    #     failed promote — the bytes are what promotion is for — and `corpus reattest`
    #     regenerates the lift from the container later (§12.4.6).
    sidecar_path: str | None = None
    lifted: dict[str, Any] = {}
    lift_schema_id: str | None = None
    if sidecar_decl is not None and member_path is not None:
        sidecar_path = sidecar_decl.sidecar_for(member_path, roster)
    if sidecar_path is not None:
        try:
            doc = sidecar.read_sidecar(
                container_path, container_media_type, sidecar_path, el_addressing=el_addressing
            )
        except (ValueError, OSError) as e:
            print(f"  note: sidecar {sidecar_path!r} not lifted ({e})", file=sys.stderr)
            sidecar_path = None
        else:
            lifted = sidecar.project(sidecar_decl, doc, member_path, roster)
            origin_fields.update(lifted)
            lift_schema_id = sidecar_decl.qualified_id

    # 6b. *(3.11 §7.2.1)* A promoted VIDEO STREAM's cut strategy is resolved HERE, because this
    #     is the one moment both records are in hand: the leaf's own origin
    #     `corpus://<container>?stream_id=<N>` is capture lineage and never a lookup route
    #     (§12.15), so nothing downstream could walk to the container's overlay to resolve it.
    #     The stamp is written on the leaf, which is thereafter self-describing. A failure to
    #     resolve leaves the leaf unstamped — unresolved, not defaulted — and never fails the
    #     promote: the bytes are what promotion is for.
    cutting_stamp: dict[str, Any] | None = None
    cutting_note = ""
    if media_type.startswith("video/") and member_address.startswith("stream_id="):
        from corpus._cli.cut import cut_leaf_stamp

        cutting_stamp, cutting_note = cut_leaf_stamp(
            corpus_root, container_post, container_id, member_address,
            container_path=container_path,
        )

    # 6c. *(v32, §7.1)* A track member's bytes are a table-driven sample concatenation with
    #     no producer to attest (§2) — the retired `framing:` stamp's engine is gone, and
    #     with it the reason to name one. What the leaf's artifact block MAY still attest is
    #     `samples:` — the engine-free count, computed by this package's own reader
    #     (`corpus.streams.sample_count`) from the SOURCE container's tables. It is the same
    #     self-check `cutting:` and stored markers compare against, computed here because
    #     this is the one moment the container is in hand. Never fatal — the same rule as
    #     `cutting:` above: the bytes are what promotion is for, and a leaf whose count
    #     could not be resolved is honestly unstamped.
    samples_stamp: int | None = None
    if member_address.startswith("stream_id="):
        try:
            samples_stamp = streams.sample_count(
                container_path, int(member_address.split("=", 1)[1])
            )
        except (ValueError, NotImplementedError, OSError) as e:
            print(f"  note: no samples stamp ({e})", file=sys.stderr)

    record_file = paths.record_path(corpus_root, computed_id)
    if record_file.is_file():
        outcome = _fold_into_existing(
            record_file, containment_uri, origin_fields,
            cutting_stamp=cutting_stamp, samples_stamp=samples_stamp,
            sidecar_decl=sidecar_decl if sidecar_path is not None else None, lifted=lifted,
        )
    else:
        outcome = _mint_stub(
            record_file, computed_id, media_type, hash_values, containment_uri, origin_fields,
            corpus_root=corpus_root, cutting_stamp=cutting_stamp, samples_stamp=samples_stamp,
            origin_schema_id=lift_schema_id,
        )
    # Bytes were in hand for THIS pass regardless of outcome (verified above) — the index is
    # deployment state (§12.9.1), so it's kept warm on a re-promote fold too, not just a mint.
    _write_hash_index_rows(corpus_root, computed_id, hash_values)

    result = {
        "id": computed_id,
        "media_type": media_type,
        "container": container_id,
        "member": member_address,
        "outcome": outcome,
        "record": str(record_file.relative_to(corpus_root)),
    }
    if cutting_note:
        result["cutting"] = cutting_note
    if sidecar_path is not None:
        result["sidecar"] = f"path={sidecar_path}"
        result["lifted"] = sorted(lifted)
        if lift_schema_id:
            result["origin_schema"] = lift_schema_id
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{outcome}: {record_file.relative_to(corpus_root)}")
        print(f"  id:         {computed_id}")
        print(f"  media_type: {media_type}")
        if sidecar_path is not None:
            print(
                f"  sidecar:    path={sidecar_path} → {len(lifted)} field(s) lifted onto "
                f"<!--origin {lift_schema_id or ''}-->"
            )
        print(f"  bytes:      resident in {container_id[:12]} (not copied; resolves via §12.9)")
    return 0


# ---------- internals ---------- #


def _find_embed(post: frontmatter.Post, member_address: str) -> dict[str, Any] | None:
    """The container's embed whose `address` names `member_address` (scalar or list member)."""
    for embed in records.iter_embed_blocks(post):
        addr = embed.get("address")
        addrs = addr if isinstance(addr, list) else [addr]
        if member_address in [str(a) for a in addrs]:
            return embed
    return None


def _sniff_and_hash(
    corpus_root: Path,
    container_path: Path,
    container_media_type: str,
    member_address: str,
    basename: str | None,
    *,
    el_addressing: dict | None = None,
) -> tuple[str, str, list[hashing.HashValue]]:
    """Stream the member once → `(media_type, blake3_hex, hash_values)`. Sniffs MIME from the
    leading bytes (so the member's schema — hence its resolved recipe union, spec §7.9 — is
    known before the pass completes), then digests the whole member (head + rest) with blake3
    identity plus every resolved recipe in the same pass. Never materializes the member whole
    (`_stream_recipe_hashes`'s one exception, `html-stampfree@1`, buffers only when a member's
    own mime schema declares it — never the default case).

    No origin overlay layers in here (spec §7.9's third layer): a promoted member's origin is
    containment lineage (`corpus://<container>?<address>`), never a producer URI, so there is
    no overlay to match — the mime schema + corpus-wide default set is the correct floor."""
    with containment.open_member_stream(
        container_path, container_media_type, member_address, el_addressing=el_addressing
    ) as fp:
        head = fp.read(_HEAD)
        media_type = mime.sniff_head(head, basename)
        # A member with no schema is tolerated (blake3 id only) rather than refused.
        schema = schemas.load_mime_schema(corpus_root, media_type) or {}
        recipes = hashing.resolve_recipes(schema, ())
        computed_id, recipe_values = _stream_identity_and_recipe_hashes(head, fp, recipes)
    return media_type, computed_id, recipe_values


def _origin_already_present(post: frontmatter.Post, containment_uri: str) -> bool:
    """True when `containment_uri` already appears among the record's origin uris — a
    corpus:// URI is exact-string identity (no host equivalence to apply)."""
    return containment_uri in set(records.iter_origin_uris(post))


def _fold_into_existing(
    record_file: Path,
    containment_uri: str,
    origin_fields: dict[str, Any],
    *,
    cutting_stamp: dict[str, Any] | None = None,
    samples_stamp: int | None = None,
    sidecar_decl: sidecar.Declaration | None = None,
    lifted: dict[str, Any] | None = None,
) -> str:
    """A record with this id already exists (a prior promote, or a standalone ingest of the
    same bytes): fold the containment origin into it rather than erroring (spec §5.2).

    *(v41, §7.2)* With a `sidecar_decl` (the container's declaration, given only when the
    member's sidecar was read) the lift is applied either way: a NEW lineage block is
    appended already carrying `origin_fields` (the projection included) and qualified with
    the declared subtype; an EXISTING lineage block is refreshed in place — the declaration-
    owned names stripped and regenerated, every other field left as it is (§12.4.6)."""
    post = records.load(record_file)
    # Only ever ADDS the stamp — an existing one is left exactly as it is. Overwriting would
    # be a fresh resolution silently replacing the one this record's addresses were computed
    # under, which §7.2.1 gives to `corpus cut` (compare-before-write) and to nothing else.
    if cutting_stamp is not None and records.cutting(post) is None:
        _stamp_artifact_field(post, "cutting", cutting_stamp)
    # `samples:` is add-only for the same reason: the record is content-addressed, so an
    # existing count describes THESE bytes and a re-derived one can only agree with it or be
    # wrong. Filling a blank is the useful case — a leaf promoted before v32 (or before
    # attestation carried a count at all), or one folded in from a standalone ingest.
    if samples_stamp is not None and records.samples(post) is None:
        _stamp_artifact_field(post, "samples", samples_stamp)
    if _origin_already_present(post, containment_uri):
        if sidecar_decl is not None:
            for block in records.iter_origin_blocks(post):
                uri = (block.get("fields") or {}).get("uri")
                uris = uri if isinstance(uri, list) else [uri]
                if containment_uri in [str(u) for u in uris if u]:
                    sidecar.apply_lift(block.setdefault("fields", {}), sidecar_decl, lifted or {})
                    sidecar.qualify_block(block, sidecar_decl)
        touches.record_touch(post, touches.script_identifier("promote"))
        records.dump(post, record_file)
        return "already-promoted"
    records.append_origin_block(
        post,
        uri=containment_uri,
        snapshot=touches.now_iso(),
        schema_id=sidecar_decl.qualified_id if sidecar_decl is not None else None,
        fields=origin_fields or None,
    )
    touches.record_touch(post, touches.script_identifier("promote"))
    records.dump(post, record_file)
    return "folded"


def _stamp_artifact_field(post: frontmatter.Post, key: str, stamp: Any) -> None:
    """Write one §7.2.1 stamp onto the leaf's artifact block, preserving whatever else the
    block carries."""
    artifact = records.artifact_block(post) or {
        "mime": records.media_type_for(post), "fields": {}
    }
    fields = dict(artifact.get("fields") or {})
    fields[key] = stamp
    records.set_artifact_block(post, mime=str(artifact.get("mime") or ""), fields=fields)


def _mint_stub(
    record_file: Path,
    record_id: str,
    media_type: str,
    hash_values: list[hashing.HashValue],
    containment_uri: str,
    origin_fields: dict[str, Any],
    *,
    corpus_root: Path,
    cutting_stamp: dict[str, Any] | None = None,
    samples_stamp: int | None = None,
    origin_schema_id: str | None = None,
) -> str:
    """Emit a fresh promoted stub — the artifact's proxy (§4.1), `touch[0]` the promote pass,
    first origin the containment lineage — qualified `<id>/<subtype>` by `origin_schema_id`
    when a container-member sidecar was lifted into `origin_fields` (§7.2, v41). Bytes are NOT written to `artifacts/`; they stay in
    the container. Attested immediately (spec §8.1), the SAME best-effort call a fresh
    `corpus ingest` stub gets (`ingest._attest_stub`) — a promoted record's attested fields
    (an eml's Subject/From/Date and its own `part=` embeds, a manifest's members, ...) must
    equal what a direct ingest of the same bytes would attest: one extraction, shared via
    `derive.attest` (already containment-aware, §2/§12.9), never a promote-side copy."""
    fm = records.stub_frontmatter(
        record_id=record_id,
        touch_id=touches.script_identifier("promote"),
    )
    post = frontmatter.Post(content="", **fm)
    record_hash_entries = {v.tag: v.hex for v in hash_values if v.record_resident}
    if record_hash_entries:
        records.set_record_hashes(post, record_hash_entries)
    # Declaration order: `samples:` (an engine-free byte-fact about these bytes) ahead of
    # `cutting:` (a resolution computed over them), so a diff of two leaves reads top to
    # bottom in that order.
    stamps: dict[str, Any] = {}
    if samples_stamp is not None:
        stamps["samples"] = samples_stamp
    if cutting_stamp:
        stamps["cutting"] = cutting_stamp
    records.set_artifact_block(post, mime=media_type, fields=stamps)
    records.append_origin_block(
        post,
        uri=containment_uri,
        snapshot=touches.now_iso(),
        schema_id=origin_schema_id,
        fields=origin_fields or None,
    )
    _attest_promoted_stub(post, corpus_root, record_id)
    records.dump(post, record_file)
    return "promoted"


def _attest_promoted_stub(post: frontmatter.Post, corpus_root: Path, record_id: str) -> None:
    """Attest byte-facts onto a fresh promoted stub (spec §8.1) — mirrors `ingest.
    _attest_stub`'s best-effort call to the SAME shared `derive.attest`, so a promoted
    record's attested layer equals a direct ingest's. `derive.attest`/`build_content_zone`
    already resolve a promoted record's bytes through its container (`containment.
    ensure_local_bytes`, §2/§12.9) exactly as `corpus reattest` would later — nothing
    promote-specific to wire up. A type with no registered drafter, or unreadable bytes,
    silently leaves a bare stub, attestable later via `corpus reattest`."""
    import logging

    from corpus import derive

    try:
        derive.attest(post, corpus_root, strip=False)
    except Exception as exc:  # attest is best-effort at promote (no drafter / unreadable bytes)
        logging.getLogger("corpus.promote").debug(
            "no attestation for %s: %s", record_id[:12], exc
        )
