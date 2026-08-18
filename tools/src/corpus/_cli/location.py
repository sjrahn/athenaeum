"""`corpus location` — verbs over `[[corpus.location]]` byte roots (spec §12.1.1,
§12.9.2, v21).

Subcommands:

- `attest NAME` — walk the named location's tree and bring `cache/locations.db` up to
  date (§12.1.1's attest pass): unchanged files are left alone, new/changed files are
  blake3-hashed, vanished files' rows are removed. Prints running progress every 500
  files to stderr, then the final counts.
- `list` — one row per configured location: attached locations show name, kind, path,
  indexed row count, stale row count; store locations show name, kind, path, and their
  placement role (§12.1.1's `ingest_types` / `ingest_default`).
- `promote NAME RELPATH` (or `--all-matching GLOB`) — mint a corpus record for one (or a
  batch of) already-attested location file(s), bytes staying in place (§12.1.1: "promotion
  mints records without moving bytes"). See `_promote_one` for the full contract.
- `move RECORD DEST` (or `--all-from SOURCE DEST`) — relocate a record's **standalone
  copy** between store locations, the co-located `artifacts/` tree counting as one
  (`DEST`/`SOURCE` are a store location name, or the literal `corpus`).
  Copy-verify-then-remove per §12.1.1's "Move semantics": see `_move` for the
  single-record contract, `_move_batch` for the batch form (v23).
- `adopt NAME DEST [RELPATH]` — copy an attested attached-location file's bytes into a
  store, **non-destructively**: the attached original and its location-index row stay
  in place (shadowed by resolution order), and a `--reclaim` flag opts into removing
  the original afterward. RELPATH absent = every current row of NAME. §12.1.1's
  "Adoption" paragraph (v23): see `_adopt_one` for the full contract.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from corpus import config as config_mod
from corpus import locationindex, paths, placement
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


class LocationPromoteError(Exception):
    """One file's promotion failed — caught per-file by `_promote` so a `--all-matching`
    batch keeps going rather than aborting on the first bad file."""


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_attest = sub.add_parser(
        "attest", help="Attest a configured location's tree into locations.db."
    )
    p_attest.add_argument("name", help="Location name (corpus.toml [[corpus.location]] name=).")
    add_corpus_root_arg(p_attest)

    p_list = sub.add_parser("list", help="List configured locations + index status.")
    add_corpus_root_arg(p_list)

    p_promote = sub.add_parser(
        "promote",
        help="Mint a record for an attested location file, bytes staying in place.",
    )
    p_promote.add_argument("name", help="Location name (corpus.toml [[corpus.location]] name=).")
    p_promote.add_argument(
        "relpath", nargs="?", help="Path relative to the location's root (mutually "
        "exclusive with --all-matching)."
    )
    p_promote.add_argument(
        "--all-matching",
        metavar="GLOB",
        help="Promote every attested relpath under NAME matching this fnmatch glob "
        "(e.g. '*.zim'), instead of a single RELPATH.",
    )
    p_promote.add_argument(
        "--source-url",
        action="append",
        default=[],
        dest="source_urls",
        metavar="URL",
        help="Record this URL as an additional origin uri alongside the location's "
        "file:// provenance (repeatable). Only valid with a single RELPATH — a batch "
        "promotion (--all-matching) records location provenance only.",
    )
    add_corpus_root_arg(p_promote)

    p_move = sub.add_parser(
        "move",
        help="Relocate a record's standalone copy between store locations (or `corpus`).",
    )
    p_move.add_argument(
        "record",
        nargs="?",
        help="Record id, hex prefix, or path to a record .md file (mutually exclusive "
        "with --all-from).",
    )
    p_move.add_argument(
        "dest",
        help="Destination: a store location name (corpus.toml [[corpus.location]] "
        "name=), or the literal `corpus` for the co-located artifacts/ tree.",
    )
    p_move.add_argument(
        "--all-from",
        dest="all_from",
        metavar="SOURCE",
        help="Move every record whose standalone copy resides at SOURCE (a store "
        "location name, or `corpus`) to DEST, instead of a single RECORD.",
    )
    add_corpus_root_arg(p_move)

    p_adopt = sub.add_parser(
        "adopt",
        help="Copy an attached location file's bytes into a store, non-destructively "
        "(spec §12.1.1 adoption).",
    )
    p_adopt.add_argument("name", help="Attached location name (corpus.toml [[corpus.location]] name=).")
    p_adopt.add_argument(
        "dest",
        help="Destination: a store location name (corpus.toml [[corpus.location]] "
        "name=), or the literal `corpus` for the co-located artifacts/ tree.",
    )
    p_adopt.add_argument(
        "relpath", nargs="?", help="Path relative to NAME's root; omitted = every "
        "current row of NAME."
    )
    p_adopt.add_argument(
        "--reclaim",
        action="store_true",
        help="Remove the attached original after the store copy verifies (never the "
        "default; a read-only attached tree is reported, not fatal).",
    )
    add_corpus_root_arg(p_adopt)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    if args.action == "attest":
        return _attest(corpus_root, args.name)
    if args.action == "list":
        return _list(corpus_root)
    if args.action == "promote":
        return _promote(corpus_root, args.name, args.relpath, args.all_matching, args.source_urls)
    if args.action == "move":
        all_from = getattr(args, "all_from", None)
        if all_from:
            if args.record:
                sys.exit("corpus location move: give RECORD or --all-from SOURCE, not both.")
            return _move_batch(corpus_root, all_from, args.dest)
        if not args.record:
            sys.exit("corpus location move: give RECORD or --all-from SOURCE.")
        return _move(corpus_root, args.record, args.dest)
    if args.action == "adopt":
        return _adopt(corpus_root, args.name, args.dest, args.relpath, args.reclaim)
    print(f"unknown action: {args.action}", file=sys.stderr)
    return 2


# ---------- handlers ---------- #


def _resolve_location(corpus_root, name: str) -> config_mod.LocationConfig | None:
    cfg = config_mod.load_config(corpus_root)
    by_name = {loc.name: loc for loc in cfg.locations}
    return by_name.get(name)


def _attest(corpus_root, name: str) -> int:
    cfg = config_mod.load_config(corpus_root)
    if not cfg.locations:
        sys.exit(
            "corpus location attest: no locations configured — add a "
            "[[corpus.location]] table to corpus.toml (spec §12.1.1)."
        )
    location = next((loc for loc in cfg.locations if loc.name == name), None)
    if location is None:
        configured = ", ".join(sorted(loc.name for loc in cfg.locations))
        sys.exit(
            f"corpus location attest: no location named {name!r}; configured: {configured}"
        )

    def _progress(n: int) -> None:
        print(f"  ...{n} files scanned", file=sys.stderr)

    counts = locationindex.attest_location(corpus_root, location, progress=_progress)
    print(
        f"location {name!r}: {counts['files']} file(s) seen, "
        f"{counts['hashed']} hashed, {counts['unchanged']} unchanged, "
        f"{counts['removed']} removed"
    )
    return 0


def _list(corpus_root) -> int:
    cfg = config_mod.load_config(corpus_root)
    if not cfg.locations:
        print("no locations configured (corpus.toml [[corpus.location]])")
        return 0
    stale_by_location: dict[str, int] = {}
    for loc_name, _relpath, _hash in locationindex.stale_rows(corpus_root):
        stale_by_location[loc_name] = stale_by_location.get(loc_name, 0) + 1
    for loc in cfg.locations:
        if loc.kind == "store":
            print(f"{loc.name}  kind=store  path={loc.path}{_store_role(loc)}")
            continue
        rows = locationindex.row_count(corpus_root, loc.name)
        stale = stale_by_location.get(loc.name, 0)
        print(f"{loc.name}  kind={loc.kind}  path={loc.path}  rows={rows}  stale={stale}")
    return 0


def _store_role(loc: config_mod.LocationConfig) -> str:
    """The placement-role suffix for a `list` row (spec §12.1.1, v22): the location's
    claimed format list, `ingest: default`, or nothing at all when it holds neither —
    a store location resolved only, never a write destination (`placement.py`)."""
    if loc.ingest_types:
        return f"  ingest: {', '.join(loc.ingest_types)}"
    if loc.ingest_default:
        return "  ingest: default"
    return ""


# ---------- promote ---------- #


def _promote(
    corpus_root: Path,
    name: str,
    relpath: str | None,
    all_matching: str | None,
    source_urls: list[str],
) -> int:
    cfg = config_mod.load_config(corpus_root)
    location = next((loc for loc in cfg.locations if loc.name == name), None)
    if location is None:
        configured = ", ".join(sorted(loc.name for loc in cfg.locations)) or "(none configured)"
        sys.exit(f"corpus location promote: no location named {name!r}; configured: {configured}")

    if bool(relpath) == bool(all_matching):
        sys.exit(
            "corpus location promote: give exactly one of RELPATH or --all-matching GLOB."
        )
    if all_matching and source_urls:
        sys.exit(
            "corpus location promote: --source-url is only valid promoting a single "
            "RELPATH, not --all-matching (a batch promotion records location provenance "
            "only — attach source URLs later via the normal origin-fold machinery)."
        )

    if all_matching:
        relpaths = _matching_relpaths(corpus_root, name, all_matching)
        if not relpaths:
            print(f"no attested file under location {name!r} matches {all_matching!r}")
            return 0
    else:
        relpaths = [relpath]  # type: ignore[list-item]

    exit_code = 0
    for rp in relpaths:
        try:
            outcome = _promote_one(corpus_root, location, rp, source_urls)
        except LocationPromoteError as e:
            print(f"error: {e}", file=sys.stderr)
            exit_code = 1
            continue
        print(outcome)
    return exit_code


def _matching_relpaths(corpus_root: Path, location_name: str, glob: str) -> list[str]:
    """Attested relpaths under `location_name` matching `glob` (fnmatch, spec §12.1.1's
    attest pass is the source of truth for what's promotable — an un-attested file never
    appears here regardless of whether it matches)."""
    with locationindex.open_index(corpus_root) as conn:
        rows = conn.execute(
            "SELECT relpath FROM locations WHERE location = ?", (location_name,)
        ).fetchall()
    return sorted(rp for (rp,) in rows if fnmatch.fnmatch(rp, glob))


def _promote_one(
    corpus_root: Path,
    location: config_mod.LocationConfig,
    relpath: str,
    source_urls: list[str],
) -> str:
    """Mint a record for one attested location file, bytes staying in place (spec
    §12.1.1, §12.9.2). Re-verifies identity in full against the index row (§12.9.2: "the
    index proposes, the hash disposes") before minting — a stale pin or a genuine hash
    mismatch both refuse loudly rather than mint a record under a wrong id.

    The origin block's `uri` carries the `file://<absolute path>` location provenance
    (§12.1.1, §7.2) plus, when given, every `--source-url` as an additional alias in the
    SAME block — the true source, whose web-host overlay may carry tenancy. Recipe
    resolution (§7.9) layers any origin overlay(s) those source URLs match; a bare
    `file://` uri matches no overlay (it is provenance, not a producer).

    Reuses `corpus._cli.ingest.mint_stub` for the actual minting (identical shape to an
    `ingest`-minted record except origin content) — the ONLY difference is `store_bytes=
    False`: the artifact-store `put` is skipped, so bytes never leave the location.
    """
    from corpus import hashing, mime, paths, schemas, touches
    from corpus._cli.ingest import mint_stub

    abs_path = location.path / relpath

    with locationindex.open_index(corpus_root) as conn:
        row = conn.execute(
            "SELECT hash, size, mtime FROM locations WHERE location = ? AND relpath = ?",
            (location.name, relpath),
        ).fetchone()
    if row is None:
        raise LocationPromoteError(
            f"{relpath!r} has no attested row in location {location.name!r} — run "
            f"`corpus location attest {location.name}` first."
        )
    indexed_hash, indexed_size, indexed_mtime = row

    try:
        st = abs_path.stat()
    except OSError as e:
        raise LocationPromoteError(
            f"{relpath!r}: {e} — the attested file is unreadable; re-attest with "
            f"`corpus location attest {location.name}` once it's back."
        ) from e

    if st.st_size != indexed_size or st.st_mtime_ns != indexed_mtime:
        raise LocationPromoteError(
            f"{relpath!r}: stale in the location index (size/mtime changed since "
            f"attest) — run `corpus location attest {location.name}` to re-attest "
            f"before promoting."
        )

    # Identity re-verified in full at mint (spec §12.1.1) — the stat pins above are cheap
    # staleness screening, not a substitute for the hash itself.
    actual_hash = hashing.hash_file(abs_path, also=())["blake3"]
    if actual_hash != indexed_hash:
        raise LocationPromoteError(
            f"{relpath!r}: hash mismatch (index says {indexed_hash[:12]}…, bytes "
            f"now hash {actual_hash[:12]}…) — refusing to mint a record with the "
            f"wrong id; run `corpus location attest {location.name}` to re-attest."
        )
    record_id = actual_hash

    media_type = mime.detect(abs_path, corpus_root)
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if mt_schema is None:
        raise LocationPromoteError(
            f"{relpath!r}: no mime schema for {media_type!r} — author "
            f"schema/mime/<axis>/<axis>_<subtype>.yaml first, then re-run."
        )

    extension = mime.extension_for(media_type, fallback=abs_path.suffix.lstrip(".") or "bin")
    record_file = paths.record_path(corpus_root, record_id)

    file_uri = abs_path.as_uri()
    uris = [file_uri, *source_urls]

    overlay_schemas = (
        [schema for _id, schema in schemas.origin_overlays_for_uris(corpus_root, source_urls)]
        if source_urls
        else []
    )
    recipes = hashing.resolve_recipes(mt_schema, overlay_schemas)
    hash_values = hashing.compute_hashes(abs_path, recipes)

    if record_file.is_file():
        return _fold_existing(corpus_root, record_file, uris)

    mint_stub(
        corpus_root,
        abs_path,
        record_id=record_id,
        media_type=media_type,
        extension=extension,
        record_file=record_file,
        hash_values=hash_values,
        origin_uri=uris[0] if len(uris) == 1 else uris,
        origin_snapshot=touches.now_iso(),
        origin_fields=None,
        origin_schema=None,
        touch_script="location.promote",
        store_bytes=False,
    )
    return f"promoted: {record_file.relative_to(corpus_root)}"


def _fold_existing(corpus_root: Path, record_file: Path, uris_to_add: list[str]) -> str:
    """A record with this id already exists (a prior promote, a standalone ingest of the
    same bytes, or a container promote): fold like a re-encounter (spec §5.2) — touch-
    stamped either way, with any URI in `uris_to_add` not already on the record added as
    an alias (`records.add_origin_uri_alias`) to its most-recent origin block, or as a
    fresh bare origin block when the record carries none yet."""
    from corpus import records, touches

    post = records.load(record_file)
    existing = set(records.iter_origin_uris(post))
    added_any = False
    for uri in uris_to_add:
        if uri in existing:
            continue
        if not records.add_origin_uri_alias(post, uri, corpus_root=corpus_root):
            records.append_origin_block(post, uri=uri, snapshot=touches.now_iso())
        added_any = True
        existing.add(uri)
    touches.record_touch(post, touches.script_identifier("location.promote"))
    records.dump(post, record_file)
    outcome = "aliased" if added_any else "already-promoted"
    return f"{outcome}: {record_file.relative_to(corpus_root)}"


# ---------- move ---------- #


def _move(corpus_root: Path, record_arg: str, dest_name: str) -> int:
    """`corpus location move RECORD DEST` (spec §12.1.1's "Move semantics" paragraph,
    v22): relocate a record's **standalone copy** — the co-located `artifacts/` tree
    counting as one location alongside the configured store locations — between store
    locations (or back to `corpus`), copy-verify-then-remove.

    Route order for the source: co-located tree first, then store locations in
    declaration order (`placement.find_in_stores`'s own order). Attached-location
    files and containment-only members have no standalone copy and refuse outright —
    attached files are operator-managed (never moved by this command); a
    containment-only member's standalone copy would have to be materialized first,
    which is `corpus replicate`'s job, not `move`'s.

    The destination is verified content-addressed: bytes stream to a `.part` temp name
    and the full blake3 is checked against the record id BEFORE the rename unveils the
    final name, so the id is resolvable through the route being replaced at every
    instant up to that point. A destination that already holds the bytes is an
    idempotent success (verify, then drop the source); a destination holding DIFFERENT
    bytes is refused as corruption, touching nothing.
    """
    from corpus import hashing, mime, records

    record_id, record_file = paths.resolve_record(corpus_root, record_arg)
    post = records.load(record_file)
    media_type = records.media_type_for(post)
    extension = mime.extension_for(media_type)

    src, src_display = _find_standalone(corpus_root, record_id, extension)
    if src is None:
        if locationindex.route_for(corpus_root, record_id) is not None:
            sys.exit(
                f"corpus location move: {record_id} has no standalone copy — it "
                f"resolves only through an attached location, and attached-location "
                f"files never move (operator-managed, spec §12.1.1)."
            )
        sys.exit(
            f"corpus location move: {record_id} has no standalone copy — it is a "
            f"containment-only member; materializing one is `corpus replicate`'s "
            f"job, not `move`'s (spec §12.1.1)."
        )

    dest, dest_display = _resolve_move_dest(corpus_root, dest_name, record_id, extension)

    if src.resolve() == dest.resolve():
        print(f"{record_id}.{extension} already at {dest_display}: no-op")
        return 0

    if dest.is_file():
        dest_hash = hashing.hash_file(dest, also=())["blake3"]
        if dest_hash == record_id:
            src.unlink()
            print(
                f"moved {record_id}.{extension}: {src_display} -> {dest_display} "
                f"(destination already held identical bytes; source removed)"
            )
            return 0
        sys.exit(
            f"corpus location move: destination {dest} already holds DIFFERENT "
            f"bytes (hash {dest_hash}, expected {record_id}) — refusing, nothing "
            f"touched (source left at {src})"
        )

    try:
        placement.copy_verified(src, dest, record_id)
    except placement.MoveVerificationError as e:
        sys.exit(
            f"corpus location move: copy failed to verify (expected {e.expected}, "
            f"got {e.actual}) — temp removed, source untouched at {src}"
        )
    src.unlink()
    print(f"moved {record_id}.{extension}: {src_display} -> {dest_display}")
    return 0


def _find_standalone(
    corpus_root: Path, record_id: str, extension: str
) -> tuple[Path | None, str | None]:
    """The record's standalone copy and a display name for where it lives — co-located
    `artifacts/` tree first (`"corpus"`), then store locations in declaration order
    (spec §12.1.1). `(None, None)` when no standalone copy exists at all."""
    co_located = paths.artifact_path(corpus_root, record_id, extension)
    if co_located.is_file():
        return co_located, "corpus"
    for loc in placement.store_locations(corpus_root):
        candidate = placement.location_artifact_path(loc, record_id, extension)
        if candidate.is_file():
            return candidate, loc.name
    return None, None


def _resolve_move_dest(
    corpus_root: Path, dest_name: str, record_id: str, extension: str
) -> tuple[Path, str]:
    """DEST's content-addressed path and display name — `paths.artifact_path` for the
    literal `corpus`, else a configured `kind = "store"` location's path (spec
    §12.1.1). Exits with an actionable message for an unknown name or an attached
    location (move only ever targets `corpus` or a store)."""
    if dest_name == "corpus":
        return paths.artifact_path(corpus_root, record_id, extension), "corpus"
    loc = _resolve_location(corpus_root, dest_name)
    if loc is None:
        cfg = config_mod.load_config(corpus_root)
        configured = ", ".join(sorted(loc2.name for loc2 in cfg.locations)) or "(none configured)"
        sys.exit(
            f"corpus location move: no location named {dest_name!r}; configured: "
            f"{configured} (or use `corpus` for the co-located tree)"
        )
    if loc.kind != "store":
        sys.exit(
            f"corpus location move: {dest_name!r} is a {loc.kind!r} location, not a "
            f"store — move only targets `corpus` or a `kind = \"store\"` location."
        )
    return placement.location_artifact_path(loc, record_id, extension), dest_name


def _move_batch(corpus_root: Path, source_name: str, dest_name: str) -> int:
    """`corpus location move --all-from SOURCE DEST` (spec §12.1.1's batch-move
    sentence, v23): every record whose standalone copy resides at SOURCE moves to
    DEST — SOURCE's own content-addressed tree is walked directly
    (`<shard>/<hash>.<ext>`, skipping `.part` temp files) rather than trusting any
    index, mapping each file's stem back to an already-promoted record; a stem with
    no matching record is silently not a record to move (the batch form only ever
    moves records, spec §12.1.1). Each candidate is relocated via the single-record
    `_move` path — its own refusals (dest holds different bytes, source fails to
    verify, …) are caught here and reported per-record rather than aborting the
    batch, in `promote --all-matching`'s mold.
    """
    if source_name == "corpus":
        root = corpus_root / "artifacts"
    else:
        loc = _resolve_location(corpus_root, source_name)
        if loc is None:
            cfg = config_mod.load_config(corpus_root)
            configured = ", ".join(sorted(loc2.name for loc2 in cfg.locations)) or "(none configured)"
            sys.exit(
                f"corpus location move: no location named {source_name!r}; configured: "
                f"{configured} (or use `corpus` for the co-located tree)"
            )
        if loc.kind != "store":
            sys.exit(
                f"corpus location move: {source_name!r} is a {loc.kind!r} location, "
                f"not a store — --all-from only sources `corpus` or a "
                f"`kind = \"store\"` location (attached files never move, spec "
                f"§12.1.1)."
            )
        root = loc.path

    if not root.is_dir():
        print(f"no records found at {source_name!r} ({root} does not exist)")
        return 0

    record_ids: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.endswith(".part"):
            continue
        record_id = path.stem
        if paths.record_path(corpus_root, record_id).is_file():
            record_ids.append(record_id)

    if not record_ids:
        print(f"no records found at {source_name!r}")
        return 0

    exit_code = 0
    for record_id in record_ids:
        try:
            rc = _move(corpus_root, record_id, dest_name)
        except SystemExit as e:
            print(f"error: {record_id}: {e.code}", file=sys.stderr)
            exit_code = 1
            continue
        if rc != 0:
            exit_code = 1
    return exit_code


# ---------- adopt ---------- #


class LocationAdoptError(Exception):
    """One file's adoption failed — caught per-file by `_adopt` so an all-rows batch
    keeps going rather than aborting on the first bad file."""


def _adopt(
    corpus_root: Path, name: str, dest_name: str, relpath: str | None, reclaim: bool
) -> int:
    """`corpus location adopt NAME DEST [RELPATH]` (spec §12.1.1's "Adoption"
    paragraph, v23): dispatch to `_adopt_one` for a single RELPATH, or every current
    row of NAME's location index when RELPATH is omitted — per-file outcomes,
    continuing past failures, exit 1 if any failed (`promote --all-matching`'s
    mold)."""
    location = _resolve_location(corpus_root, name)
    if location is None:
        cfg = config_mod.load_config(corpus_root)
        configured = ", ".join(sorted(loc.name for loc in cfg.locations)) or "(none configured)"
        sys.exit(f"corpus location adopt: no location named {name!r}; configured: {configured}")
    if location.kind != "attached":
        sys.exit(
            f"corpus location adopt: {name!r} is a {location.kind!r} location, not "
            f"attached — adoption transfers custody FROM an attached location (spec "
            f"§12.1.1)."
        )

    if relpath:
        relpaths = [relpath]
    else:
        with locationindex.open_index(corpus_root) as conn:
            rows = conn.execute(
                "SELECT relpath FROM locations WHERE location = ?", (name,)
            ).fetchall()
        relpaths = sorted(rp for (rp,) in rows)
        if not relpaths:
            print(f"no attested file under location {name!r}")
            return 0

    exit_code = 0
    for rp in relpaths:
        try:
            outcome = _adopt_one(corpus_root, location, rp, dest_name, reclaim)
        except LocationAdoptError as e:
            print(f"error: {e}", file=sys.stderr)
            exit_code = 1
            continue
        print(outcome)
    return exit_code


def _adopt_one(
    corpus_root: Path,
    location: config_mod.LocationConfig,
    relpath: str,
    dest_name: str,
    reclaim: bool,
) -> str:
    """Adopt one attested attached-location file into a store (spec §12.1.1's
    "Adoption" paragraph, v23): the destination store gains a copy under `move`'s
    copy-verify-then-rename contract (`placement.copy_verified` — a temp name, full
    blake3 verified against the record id before the rename unveils it), and the
    attached original stays exactly where it is, untouched — the location-index row
    is never cleared, staying honestly in place as the health-surfacable shadowed
    copy (spec's own phrase). A destination already holding verified identical bytes
    is idempotent success.

    Refused (raising `LocationAdoptError`, caught per-file by `_adopt`): no attested
    row for RELPATH (attest first); a stale row — size/mtime drift since attest
    (re-attest first, exactly as promotion refuses it); no promoted record for the
    file's hash (adoption transfers custody of a record's bytes, it does not mint —
    promote first); a destination already holding DIFFERENT bytes.

    `--reclaim` removes the original only after the store copy verifies, and its
    failure (a read-only attached tree, most commonly) is reported but never turns
    an otherwise-successful adoption into a failure — spec's own ruling: "for a
    read-only attached tree never possible at all" is a property of reclaim, not of
    adoption.
    """
    from corpus import hashing, mime, records

    abs_path = location.path / relpath

    with locationindex.open_index(corpus_root) as conn:
        row = conn.execute(
            "SELECT hash, size, mtime FROM locations WHERE location = ? AND relpath = ?",
            (location.name, relpath),
        ).fetchone()
    if row is None:
        raise LocationAdoptError(
            f"{relpath!r} has no attested row in location {location.name!r} — run "
            f"`corpus location attest {location.name}` first."
        )
    indexed_hash, indexed_size, indexed_mtime = row

    try:
        st = abs_path.stat()
    except OSError as e:
        raise LocationAdoptError(
            f"{relpath!r}: {e} — the attested file is unreadable; re-attest with "
            f"`corpus location attest {location.name}` once it's back."
        ) from e

    if st.st_size != indexed_size or st.st_mtime_ns != indexed_mtime:
        raise LocationAdoptError(
            f"{relpath!r}: stale in the location index (size/mtime changed since "
            f"attest) — run `corpus location attest {location.name}` to re-attest "
            f"before adopting."
        )

    record_id = indexed_hash
    record_file = paths.record_path(corpus_root, record_id)
    if not record_file.is_file():
        raise LocationAdoptError(
            f"{relpath!r}: no promoted record for {record_id} — adoption transfers "
            f"custody of a record's bytes, it does not mint one; run `corpus "
            f"location promote {location.name} {relpath}` first."
        )

    post = records.load(record_file)
    media_type = records.media_type_for(post)
    extension = mime.extension_for(media_type)

    dest, dest_display = _resolve_move_dest(corpus_root, dest_name, record_id, extension)

    if dest.is_file():
        dest_hash = hashing.hash_file(dest, also=())["blake3"]
        if dest_hash != record_id:
            raise LocationAdoptError(
                f"{relpath!r}: destination {dest} already holds DIFFERENT bytes "
                f"(hash {dest_hash}, expected {record_id}) — refusing, nothing touched."
            )
        outcome = (
            f"adopted: {location.name}/{relpath} -> {dest_display} "
            f"(already present, idempotent)"
        )
    else:
        try:
            placement.copy_verified(abs_path, dest, record_id)
        except placement.MoveVerificationError as e:
            raise LocationAdoptError(
                f"{relpath!r}: copy failed to verify (expected {e.expected}, got "
                f"{e.actual}) — temp removed, original untouched."
            ) from e
        outcome = f"adopted: {location.name}/{relpath} -> {dest_display}"

    if reclaim:
        try:
            abs_path.unlink()
            outcome += " (original reclaimed)"
        except OSError as e:
            print(
                f"warning: {relpath!r}: adoption succeeded but --reclaim failed to "
                f"remove the original ({e}) — left in place.",
                file=sys.stderr,
            )
            outcome += " (reclaim failed: original left in place)"

    return outcome
