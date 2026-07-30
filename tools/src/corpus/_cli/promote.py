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
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import blake3
import frontmatter

from corpus import containment, mime, paths, records, schemas, touches
from corpus import functional_uri as furi
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

# Read a generous head for MIME sniffing — enough to reach the tar `ustar` magic at offset 257
# (mime._SNIFF_BYTES). A member smaller than this streams whole into the head buffer.
_HEAD = 512
_CHUNK = 1 << 20


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
    basename = meta.get("filename") or member_address.rsplit("=", 1)[-1].rsplit("/", 1)[-1]

    # 4. Stream the member once: sniff MIME + compute blake3 (and the member schema's aux
    #    transport_algos). Never loads the member whole (spec §8.1 / §12.9).
    try:
        media_type, computed_id, aux = _sniff_and_hash(
            corpus_root,
            container_path,
            container_media_type,
            member_address,
            basename,
            el_addressing=el_addressing,
        )
    except (ValueError, OSError) as e:
        sys.exit(f"could not read member {member_address!r} from container: {e}")

    # A member whose bytes name no type — a raw elementary media stream is the case, having
    # neither magic nor a filename (`stream_id=` is a position, so `member_source_metadata`
    # deliberately yields none) — takes the type the roster already attested for it. The sniff
    # still wins wherever it concludes: it read the actual bytes, where the row is a record of
    # what attestation found in the container's own tables.
    if media_type == "unknown":
        declared = str(embed.get("media_type") or "").strip()
        if declared:
            media_type = declared

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

    record_file = paths.record_path(corpus_root, computed_id)
    if record_file.is_file():
        outcome = _fold_into_existing(
            record_file, containment_uri, origin_fields, cutting_stamp=cutting_stamp
        )
    else:
        outcome = _mint_stub(
            record_file, computed_id, media_type, aux, containment_uri, origin_fields,
            cutting_stamp=cutting_stamp,
        )

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
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{outcome}: {record_file.relative_to(corpus_root)}")
        print(f"  id:         {computed_id}")
        print(f"  media_type: {media_type}")
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
    basename: str,
    *,
    el_addressing: dict | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Stream the member once → `(media_type, blake3_hex, {aux_algo: hex})`. Sniffs MIME from
    the leading bytes (so the member's schema — hence its `transport_algos` — is known before
    the pass completes), then digests the whole member (head + rest) with blake3 and each
    declared aux algorithm in the same pass. Never materializes the member whole."""
    with containment.open_member_stream(
        container_path, container_media_type, member_address, el_addressing=el_addressing
    ) as fp:
        head = fp.read(_HEAD)
        media_type = mime.sniff_head(head, basename)
        # The member's own schema decides the aux byte-hashes to record (like ingest); a member
        # with no schema is tolerated (blake3 id only) rather than refused.
        schema = schemas.load_mime_schema(corpus_root, media_type) or {}
        algos = tuple(str(a) for a in schema.get("transport_algos", []) if a and str(a) != "blake3")
        b3 = blake3.blake3()
        aux = {a: hashlib.new(a) for a in algos}
        b3.update(head)
        for h in aux.values():
            h.update(head)
        while chunk := fp.read(_CHUNK):
            b3.update(chunk)
            for h in aux.values():
                h.update(chunk)
    return media_type, b3.hexdigest(), {a: h.hexdigest() for a, h in aux.items()}


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
) -> str:
    """A record with this id already exists (a prior promote, or a standalone ingest of the
    same bytes): fold the containment origin into it rather than erroring (spec §5.2)."""
    post = records.load(record_file)
    # Only ever ADDS the stamp — an existing one is left exactly as it is. Overwriting would
    # be a fresh resolution silently replacing the one this record's addresses were computed
    # under, which §7.2.1 gives to `corpus cut` (compare-before-write) and to nothing else.
    if cutting_stamp is not None and records.cutting(post) is None:
        _stamp_cutting(post, cutting_stamp)
    if _origin_already_present(post, containment_uri):
        touches.record_touch(post, touches.script_identifier("promote"))
        records.dump(post, record_file)
        return "already-promoted"
    records.append_origin_block(
        post,
        uri=containment_uri,
        snapshot=touches.now_iso(),
        fields=origin_fields or None,
    )
    touches.record_touch(post, touches.script_identifier("promote"))
    records.dump(post, record_file)
    return "folded"


def _stamp_cutting(post: frontmatter.Post, stamp: dict[str, Any]) -> None:
    """Write the resolved `cutting:` stamp onto the leaf's artifact block, preserving whatever
    else the block carries."""
    artifact = records.artifact_block(post) or {
        "mime": records.media_type_for(post), "fields": {}
    }
    fields = dict(artifact.get("fields") or {})
    fields["cutting"] = stamp
    records.set_artifact_block(post, mime=str(artifact.get("mime") or ""), fields=fields)


def _mint_stub(
    record_file: Path,
    record_id: str,
    media_type: str,
    aux: dict[str, str],
    containment_uri: str,
    origin_fields: dict[str, Any],
    *,
    cutting_stamp: dict[str, Any] | None = None,
) -> str:
    """Emit a fresh promoted stub — the artifact's proxy (§4.1), `touch[0]` the promote pass,
    first origin the containment lineage. Bytes are NOT written to `artifacts/`; they stay in
    the container."""
    transport = [records.format_hash(algo, hexval) for algo, hexval in aux.items()]
    transport_value: str | list[str] | None
    if not transport:
        transport_value = None
    elif len(transport) == 1:
        transport_value = transport[0]
    else:
        transport_value = transport

    fm = records.stub_frontmatter(
        record_id=record_id,
        transport=transport_value,
        touch_id=touches.script_identifier("promote"),
    )
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(
        post, mime=media_type, fields={"cutting": cutting_stamp} if cutting_stamp else {}
    )
    records.append_origin_block(
        post,
        uri=containment_uri,
        snapshot=touches.now_iso(),
        fields=origin_fields or None,
    )
    records.dump(post, record_file)
    return "promoted"
