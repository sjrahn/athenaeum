"""`corpus hash-index` — maintenance over the derived hash index (spec §12.9.1).

Subcommands:

- `backfill [--hydrate] [--ids …]` — fill missing index rows for the fleet. Runs the
  record-sync pass first (mirrors record-resident `hash:` values into the index — no
  bytes touched), then, for every record's resolved recipe set, computes and upserts
  whatever rows are still missing. Bytes are read only where they're already local —
  standalone artifact first, else through containment (§2, §12.9) — except against a
  remote store backend, where a record whose bytes aren't already local is skipped
  and counted unless `--hydrate` authorizes the remote pull. Resumable by
  construction: already-present rows are never recomputed, so re-running only ever
  does the work a prior run left undone.
"""

from __future__ import annotations

import argparse

from corpus import containment, hashindex, hashing, mime, paths, records, schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.hashing import RecipeError
from corpus.store import ArtifactMissing, ArtifactStore, LocalArtifactStore, get_store


class _NoRemoteStore:
    """Wraps a real `ArtifactStore` so a resolution attempt through it never pulls bytes
    from a remote backend — `ensure_local` raises `ArtifactMissing` instead of hydrating
    when the file isn't already local. Used for the default (non `--hydrate`) backfill
    pass so containment resolution (which may recurse through a promoted member's
    container) never touches the network on its own, matching §12.9.1's "nothing pulls
    bytes solely to hash"."""

    def __init__(self, inner: ArtifactStore) -> None:
        self._inner = inner

    def local_path(self, record_id: str, ext: str):
        return self._inner.local_path(record_id, ext)

    def is_local(self, record_id: str, ext: str) -> bool:
        return self._inner.is_local(record_id, ext)

    def exists(self, record_id: str, ext: str) -> bool:
        return self._inner.is_local(record_id, ext)

    def ensure_local(self, record_id: str, ext: str):
        if self._inner.is_local(record_id, ext):
            return self._inner.local_path(record_id, ext)
        raise ArtifactMissing(
            f"{record_id} is not local — remote hydration needs --hydrate"
        )

    def put(self, record_id: str, ext: str, src) -> None:
        self._inner.put(record_id, ext, src)

    def list_local(self) -> set[str]:
        return self._inner.list_local()

    def list_remote(self) -> set[str]:
        return self._inner.list_remote()


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_backfill = sub.add_parser(
        "backfill", help="Fill missing derived-hash index rows for the fleet."
    )
    p_backfill.add_argument(
        "--hydrate",
        action="store_true",
        help="authorize pulling bytes from a remote store backend when not already local.",
    )
    p_backfill.add_argument(
        "--ids",
        default=None,
        metavar="ID,...",
        help="comma-separated record(s) (hash / hex prefix / path) to scope to (default: whole corpus).",
    )
    add_corpus_root_arg(p_backfill)


def run(args: argparse.Namespace) -> int:
    if args.action == "backfill":
        return _backfill(args)
    print(f"unknown action: {args.action}")
    return 2


def _backfill(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)

    # (a) Record sync first — mirrors record-resident `hash:` values into the index,
    # no bytes needed. Unconditional and corpus-wide, regardless of --ids scoping.
    all_refs = list(records.load_all(corpus_root))
    synced = hashindex.sync_from_records(
        corpus_root,
        ((str(post.metadata.get("id") or md.stem), post) for md, post in all_refs),
    )
    print(f"hash-index backfill: record-sync mirrored {synced} row(s)")

    if args.ids:
        targets = [t.strip() for t in args.ids.split(",") if t.strip()]
        candidates = []
        for t in targets:
            _, rf = paths.resolve_record(corpus_root, t)
            candidates.append(rf)
    else:
        candidates = [md for md, _ in all_refs]

    # (b) Resolve each record's effective recipe set.
    recipes_by_record: dict[str, tuple[hashing.Recipe, ...]] = {}
    mime_by_record: dict[str, str] = {}
    unknown_recipe_skips = 0

    for rf in candidates:
        post = records.load(rf)
        rid = str(post.metadata.get("id") or rf.stem)
        media_type = records.media_type_for(post)
        mime_schema = schemas.load_mime_schema(corpus_root, media_type)
        uris = list(records.iter_origin_uris(post))
        overlays = [sch for _id, sch in schemas.origin_overlays_for_uris(corpus_root, uris)]
        try:
            recipes = hashing.resolve_recipes(mime_schema, origin_overlays=overlays)
        except RecipeError as exc:
            print(f"  skip {rid[:12]}: unknown recipe id in schema: {exc}")
            unknown_recipe_skips += 1
            continue
        recipes_by_record[rid] = recipes
        mime_by_record[rid] = media_type

    # (c) Missing rows, batched by identical resolved recipe-id sets (the common case —
    # records of the same mime + origin share a recipe set) rather than one query per
    # record.
    groups: dict[tuple[str, ...], list[str]] = {}
    for rid, recipes in recipes_by_record.items():
        key = tuple(sorted(r.id for r in recipes))
        groups.setdefault(key, []).append(rid)

    missing_by_record: dict[str, list[str]] = {}
    with hashindex.open_index(corpus_root) as conn:
        for key, rids in groups.items():
            if not key:
                continue
            missing_by_record.update(hashindex.missing(conn, rids, list(key)))

    if not missing_by_record:
        print(
            f"hash-index backfill: {len(recipes_by_record)} record(s) already fully "
            f"indexed; nothing to compute"
        )
        return 0

    # (d) Locate bytes + compute only the missing recipes' values.
    store = get_store(corpus_root)
    is_local_backend = isinstance(store, LocalArtifactStore)
    resolve_store = store if (args.hydrate or is_local_backend) else _NoRemoteStore(store)
    member_index = containment.build_member_index(corpus_root)

    rows_written = 0
    skipped_remote = 0
    skipped_unresolvable = 0

    with hashindex.open_index(corpus_root) as conn:
        for rid, missing_ids in missing_by_record.items():
            media_type = mime_by_record[rid]
            ext = mime.extension_for(media_type)
            need = [r for r in recipes_by_record[rid] if r.id in missing_ids]
            if not need:
                continue

            try:
                artifact_path = containment.ensure_local_bytes(
                    corpus_root, rid, ext, store=resolve_store, member_index=member_index
                )
            except ArtifactMissing as exc:
                if not args.hydrate and not is_local_backend and (
                    store.exists(rid, ext) or rid in member_index
                ):
                    print(f"  skip {rid[:12]}: remote-only, use --hydrate to pull ({exc})")
                    skipped_remote += 1
                else:
                    print(f"  skip {rid[:12]}: unresolvable ({exc})")
                    skipped_unresolvable += 1
                continue
            except Exception as exc:
                # container is that record's data problem (health's ground, e.g. a stale
                # el= path); one record must never kill a fleet pass. Reported, counted,
                # never silent (§12.9.1).
                print(f"  skip {rid[:12]}: unresolvable ({type(exc).__name__}: {exc})")
                skipped_unresolvable += 1
                continue

            try:
                values = hashing.compute_hashes(artifact_path, need)
            except Exception as exc:
                print(f"  skip {rid[:12]}: compute failed ({type(exc).__name__}: {exc})")
                skipped_unresolvable += 1
                continue
            rows = [
                hashindex.HashRow(
                    record_id=rid, recipe=v.recipe, algo=v.tag, value=v.hex, param=v.param
                )
                for v in values
            ]
            rows_written += hashindex.upsert_rows(conn, rows)

        # Re-check, over just the records touched above, which are now fully indexed —
        # a tiny file whose ladder never reaches a rung legitimately stays "missing"
        # forever (spec §7.9), so this is a re-query rather than inferred from output.
        attempted_groups: dict[tuple[str, ...], list[str]] = {}
        for rid in missing_by_record:
            key = tuple(sorted(r.id for r in recipes_by_record[rid]))
            attempted_groups.setdefault(key, []).append(rid)
        still_missing: dict[str, list[str]] = {}
        for key, rids in attempted_groups.items():
            still_missing.update(hashindex.missing(conn, rids, list(key)))

    fully_indexed = len(missing_by_record) - len(still_missing)

    summary = (
        f"hash-index backfill: {rows_written} row(s) written; "
        f"{fully_indexed} record(s) now fully indexed"
    )
    if still_missing:
        summary += f"; {len(still_missing)} record(s) still incomplete"
    if skipped_remote:
        summary += f"; {skipped_remote} skipped (remote-only, retry with --hydrate)"
    if skipped_unresolvable:
        summary += f"; {skipped_unresolvable} skipped (unresolvable)"
    if unknown_recipe_skips:
        summary += f"; {unknown_recipe_skips} record(s) skipped (unknown recipe id)"
    print(summary)
    return 0
