"""`corpus location` — verbs over `[[corpus.location]]` byte roots (spec §12.1.1,
§12.9.2, v21).

Subcommands:

- `attest NAME` — walk the named location's tree and bring `cache/locations.db` up to
  date (§12.1.1's attest pass): unchanged files are left alone, new/changed files are
  blake3-hashed, vanished files' rows are removed. Prints running progress every 500
  files to stderr, then the final counts.
- `list` — one row per configured location: name, kind, path, indexed row count, stale
  row count.
- `promote NAME RELPATH` (or `--all-matching GLOB`) — mint a corpus record for one (or a
  batch of) already-attested location file(s), bytes staying in place (§12.1.1: "promotion
  mints records without moving bytes"). See `_promote_one` for the full contract.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from corpus import config as config_mod
from corpus import locationindex
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


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    if args.action == "attest":
        return _attest(corpus_root, args.name)
    if args.action == "list":
        return _list(corpus_root)
    if args.action == "promote":
        return _promote(corpus_root, args.name, args.relpath, args.all_matching, args.source_urls)
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
        rows = locationindex.row_count(corpus_root, loc.name)
        stale = stale_by_location.get(loc.name, 0)
        print(f"{loc.name}  kind={loc.kind}  path={loc.path}  rows={rows}  stale={stale}")
    return 0


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
