"""Bulk re-attest — `corpus reattest` (spec §12.4.6, §8.3).

Re-derives the **attested layer** — the byte-facts ingest stamps: the artifact block's
extended fields, the manifest/exposable embeds, and the drafter's mechanical issues — from a
record's retained artifact + the current schemas/tooling, **never touching the authored
layer** (the stored content zone, embed/segment descriptions, editorial fields, asserted
issues). It is the deterministic recompile of just the attested facts: `git diff records/`
surfaces exactly which records a schema / overlay / tooling change affected.

Unlike the 2.x `corpus redraft` (which re-derived the whole record and so refused an
authored record), re-attest preserves the authored layer, so it needs no authored-refusal
guard and sweeps every derived state by default. **Idempotent**: a record whose attested
facts re-derive byte-for-byte is not rewritten and appends no touch (the pass only records
itself when it actually changed something). `--dry-run` reports the set without writing.

Distinct from `corpus compile`, which reassembles a record from a decomposed *manifest*
(the normalize edit substrate) rather than from the source *artifact*.

*(v20)* Also the derived-hash index's per-record refresh point (spec §12.9.1): as each
record's artifact is streamed for attestation, its resolved derived-hash recipe union
(§7.9) is recomputed and every value upserted into the index. A `residency: record`
byte-stable recipe MISSING from the record's `hash:` field is filled in — the same free
moment ingest had, arriving late for a record ingested before the recipe existed. An
EXISTING `hash:` entry is never overwritten: a byte-stable hash that disagrees with the
freshly recomputed one is surfaced loudly (the bytes or the record changed — a serious
integrity signal) rather than silently rewritten. Procedure-versioned values never reach
`hash:` here — index-only; flushing them is `corpus hash flush`'s deliberate act.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from corpus import derive, records, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.derive import DeriveError
from corpus.draft import mbox_manifest
from corpus.mux import MuxFailed
from corpus.store import ArtifactMissing


def reattest_record(
    record_file: Path,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
    dry_run: bool = False,
) -> str:
    """Re-derive the attested layer of the record at `record_file`, **in memory**; return
    the serialized record (NOT written). Strips + re-derives the attested layer while
    preserving the authored layer (`derive.attest(strip=True)`), then refreshes the derived
    hash index and fills any missing byte-stable `hash:` entry (`_refresh_hashes`, spec
    §12.9.1). `messages` is the mbox selective declaration (§12.11, the re-homed
    `--messages`). Idempotent: when the attested facts AND the resolved hash values re-derive
    identically the original text is returned unchanged — no touch appended, no rewrite.
    `dry_run` skips the index write (a query cache, but "writing nothing" means nothing).
    Raises `DeriveError` / `ArtifactMissing`.

    A pre-3.4 record converts here: its per-asset blocks are deleted and the members block
    replaces them, so the `description`s they carried are **dropped** (§4.3.1.4, §12.26).
    Reported, not blocked — nothing migrates, but a record silently shedding 52 descriptions is
    the kind of thing an operator should see happen."""
    post = records.load(record_file)
    dropped = records.pending_member_descriptions(post)
    if dropped:
        print(
            f"  note {record_file.stem[:12]}: dropping {len(dropped)} retired member "
            f"description(s) at {', '.join(a for a, _ in dropped[:5])}"
            f"{f' (+{len(dropped) - 5} more)' if len(dropped) > 5 else ''}"
        )
    before = records.dumps(post)
    mime_schema_id = derive.attest(
        post, corpus_root, fingerprint_cli=fingerprint_cli, strip=True, messages=messages
    )
    record_id = str(post.metadata.get("id") or "")
    if record_id:
        _refresh_hashes(post, corpus_root, record_id, dry_run=dry_run)
    after = records.dumps(post)
    if after == before:
        return before  # attested layer + resolved hashes unchanged — the pass records nothing
    touches.record_touch(post, touches.script_identifier("attest." + (mime_schema_id or "unknown")))
    return records.dumps(post)


def _refresh_hashes(
    post, corpus_root: Path, record_id: str, *, dry_run: bool = False
) -> None:
    """The reattest-time hash-index refresh point (spec §12.9.1, §2): recompute the record's
    resolved derived-hash recipe union (§7.9) over its artifact and upsert every value into the
    index — the same free moment ingest had, arriving late for a record ingested (or an
    origin/mime schema written) before the recipe existed.

    Mutates `post` in place to fill a MISSING `residency: record` byte-stable `hash:` entry
    only. An EXISTING entry is never overwritten: the record is content-addressed, so a
    byte-stable hash disagreeing with the freshly recomputed one over the SAME bytes means the
    stored value or the record itself changed by some other route — a serious integrity signal,
    surfaced loudly (printed) rather than silently rewritten. Procedure-versioned values never
    reach `hash:` here — index-only; `corpus hash flush` is the deliberate write (§12.9.1).

    Best-effort like the rest of re-attest: unresolvable bytes (`ArtifactMissing`) skip the
    refresh entirely, and an index write failure is reported and swallowed rather than failing
    the pass — the index is deployment state, never authoritative."""
    from corpus import containment, hashindex, hashing, schemas
    from corpus import mime as mime_mod
    from corpus.store import ArtifactMissing

    media_type = records.media_type_for(post)
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    overlay_schemas = [
        schema
        for _id, schema in schemas.origin_overlays_for_uris(
            corpus_root, list(records.iter_origin_uris(post))
        )
    ]
    recipes = hashing.resolve_recipes(mt_schema, overlay_schemas)

    try:
        bytes_path = containment.ensure_local_bytes(
            corpus_root, record_id, mime_mod.extension_for(media_type)
        )
    except ArtifactMissing:
        return

    values = hashing.compute_hashes(bytes_path, recipes)
    if not values:
        return

    existing = records.record_hashes(post)
    to_fill: dict[str, str] = {}
    for v in values:
        if not v.record_resident:
            continue
        prior = existing.get(v.tag)
        if prior is None:
            to_fill[v.tag] = v.hex
        elif prior != v.hex:
            print(
                f"  MISMATCH {record_id[:12]}…: stored hash {v.tag}:{prior[:12]}… != "
                f"recomputed {v.tag}:{v.hex[:12]}… — the bytes or the record changed; "
                f"NOT rewritten (a byte-stable hash can never legitimately drift, spec §2)",
                file=sys.stderr,
            )
    if to_fill:
        records.set_record_hashes(post, to_fill)

    if dry_run:
        return
    try:
        with hashindex.open_index(corpus_root) as conn:
            hashindex.upsert_rows(
                conn,
                [
                    hashindex.HashRow(
                        record_id=record_id, recipe=v.recipe, algo=v.tag, value=v.hex, param=v.param
                    )
                    for v in values
                ],
            )
    except Exception as exc:  # deployment state (§12.9.1) — never fails reattest
        print(f"  note {record_id[:12]}…: hash-index update failed ({exc}) — continuing", file=sys.stderr)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="a single record (hash / hex prefix / path); omit to sweep the whole corpus.",
    )
    parser.add_argument("--mime", default=None, help="only records whose artifact MIME equals this.")
    parser.add_argument(
        "--host", default=None, help="only records with an origin URI on this host (subdomains included)."
    )
    parser.add_argument(
        "--state",
        choices=("proxy", "terminal", "rendered", "formed", "any"),
        default="any",
        help=(
            "which derived states (spec §4.1) to consider (default: any — the attested "
            "layer is state-independent)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report which records would change, writing nothing.",
    )
    parser.add_argument(
        "--fingerprint",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="force perceptual fingerprinting on/off for every re-attested record (else the schema decides).",
    )
    parser.add_argument(
        "--messages",
        default=None,
        metavar="SPEC",
        help=(
            "mbox only (single target): declare the 1-indexed messages to manifest as "
            "`message/rfc822` embeds — a comma list of ordinals and `lo-hi` ranges "
            "(e.g. `5,12,90-95`). Cumulative: unions with the already-declared set (§12.11). "
            "The re-homed successor of the 2.x `corpus draft --messages`."
        ),
    )
    add_corpus_root_arg(parser)


def _origin_hosts(post) -> set[str]:
    hosts: set[str] = set()
    for uri in records.iter_origin_uris(post):
        host = (urlparse(str(uri)).hostname or "").lower()
        if host:
            hosts.add(host)
    return hosts


def _host_matches(post, want: str) -> bool:
    want = want.lower()
    return any(h == want or h.endswith("." + want) for h in _origin_hosts(post))


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    corpus_root = resolved_corpus_root(args)

    messages_spec = getattr(args, "messages", None)
    if messages_spec is not None and not args.target:
        sys.exit("--messages requires a single target record (an mbox).")
    ordinals: list[int] | None = None
    if messages_spec:
        from corpus import schemas

        try:
            ordinals = mbox_manifest.parse_message_spec(messages_spec)
        except ValueError as exc:
            sys.exit(str(exc))
        _, rf = paths.resolve_record(corpus_root, args.target)
        mt = schemas.normalize_pipeline_keys(
            schemas.load_mime_schema(corpus_root, records.media_type_for(records.load(rf))) or {}
        )
        if str((mt.get("draft") or {}).get("strategy") or "") != "mbox-manifest":
            sys.exit("--messages is only valid for an mbox record.")

    if args.target:
        _, rf = paths.resolve_record(corpus_root, args.target)
        candidates = [rf]
    else:
        candidates = sorted(records.iter_record_paths(corpus_root))

    fp = getattr(args, "fingerprint", None)
    changed = unchanged = failed = 0

    for rf in candidates:
        post = records.load(rf)
        if args.state != "any" and records.derived_state(post, corpus_root) != args.state:
            continue
        if args.mime and records.media_type_for(post) != args.mime:
            continue
        if args.host and not _host_matches(post, args.host):
            continue

        rid = str(post.metadata.get("id") or "")[:12]
        try:
            new_text = reattest_record(
                rf, corpus_root, fingerprint_cli=fp, messages=ordinals, dry_run=args.dry_run
            )
        except mbox_manifest.MessageHashConflict as exc:
            sys.exit(str(exc))  # stale declaration — a hard error (§12.11), never papered over
        except (DeriveError, ArtifactMissing, MuxFailed) as exc:
            # MuxFailed: a member extraction the current mux can't perform (e.g. a codec
            # its container family refuses) — a per-record condition, never a fleet-stopper.
            print(f"  skip {rid}: {exc}", file=sys.stderr)
            failed += 1
            continue

        if new_text == rf.read_text(encoding="utf-8"):
            unchanged += 1
            continue
        changed += 1
        if not args.dry_run:
            rf.write_text(new_text, encoding="utf-8")
        verb = "would change" if args.dry_run else "changed"
        print(f"  {verb}: {rf.relative_to(corpus_root)}")

    verb = "would re-attest" if args.dry_run else "re-attested"
    summary = f"{verb} {changed + unchanged} record(s); {changed} changed, {unchanged} unchanged"
    if failed:
        summary += f", {failed} failed"
    print(summary)
    return 0
