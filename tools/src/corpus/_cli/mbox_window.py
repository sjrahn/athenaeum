"""Mailbox window reduction — `corpus mbox-window` (spec §12.3.13).

Reduces a transient full-mailbox export (a provider that re-delivers the whole mailbox
every time, e.g. a Takeout All-Mail mbox) to a **window bundle**: a valid mboxrd staged
into `capture/` holding ONLY the members not already persisted in the named lineage. The
full export is then discarded, never ingested — its identity survives on the bundle's
origin fields, tombstone-style.

Dedup keys on the un-stuffed member blake3 (§12.11 — the promotable identity), never on
ordinals, which scatter across exports. The exclusion set is derived at run time, never
stored: full streaming enumeration of each lineage record's artifact bytes where locally
present; the declared `msg=` embed transports as the (warned, subset) fallback; plus every
standalone `message/rfc822` record in the corpus. `--against` expands transitively through
each named record's own `window_against` origin field, so naming the latest window reaches
the whole chain back to its baseline snapshot.

Post-ingest convention: `corpus reattest <id> --messages 1-<N>` declares every member, so
the manifest doubles as the window's human delta index and the machine dedup-set the next
window subtracts without re-scanning artifact bytes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

from corpus import containment, mboxfile, mime, paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root
from corpus.draft import mbox_manifest
from corpus.store import ArtifactMissing

_MBOX_MIME = "application/mbox"
_RFC822_MIME = "message/rfc822"


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="path to the full-mailbox export (mboxrd) to reduce.")
    parser.add_argument(
        "--against",
        action="append",
        required=True,
        metavar="RECORD",
        help=(
            "a lineage record (hash / hex prefix) whose persisted members are excluded; "
            "repeatable, and each expands transitively through its own `window_against` "
            "origin field — naming the latest window reaches the whole chain."
        ),
    )
    parser.add_argument(
        "--origin",
        default=None,
        metavar="OVERLAY-ID",
        help="origin overlay id to stamp on the sidecar (`origin_schema:`), as `assemble` takes it.",
    )
    parser.add_argument(
        "--strip",
        action="append",
        default=None,
        metavar="HEADER",
        help=(
            "mailbox chrome strip OVERRIDE (§12.3.13; repeatable, comma lists accepted). "
            "Normally the corpus's application/mbox schema `strip_headers` declaration "
            "resolves automatically (the same config ingest applies) — pass this only to "
            "deviate from it. Applied to the source, the emitted bundle, AND lineage "
            "artifact enumeration, so a pre-strip snapshot still serves as lineage."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the reduction (counts + would-be bundle name), writing nothing.",
    )
    add_corpus_root_arg(parser)


def _expand_lineage(corpus_root: Path, targets: list[str]) -> list[tuple[str, object]]:
    """Resolve `targets` and transitively expand each through its `window_against` origin
    field. Returns `(record_id, post)` pairs in first-seen order; exits on a non-mbox
    target or an unresolvable transitive ref (a broken lineage should be loud, not
    silently under-excluded — under-exclusion re-admits members and defeats the window)."""
    out: list[tuple[str, object]] = []
    seen: set[str] = set()
    queue = list(targets)
    while queue:
        target = queue.pop(0)
        rid, rf = paths.resolve_record(corpus_root, target)
        if rid in seen:
            continue
        seen.add(rid)
        post = records.load(rf)
        if records.media_type_for(post) != _MBOX_MIME:
            sys.exit(f"--against {rid[:12]}: not an mbox record ({records.media_type_for(post)}).")
        out.append((rid, post))
        for block in records.iter_origin_blocks(post):
            against = (block.get("fields") or {}).get("window_against")
            if isinstance(against, str):
                against = against.split()
            for ref in against or []:
                if str(ref) not in seen:
                    queue.append(str(ref))
    return out


def _exclusion_set(
    corpus_root: Path,
    lineage: list[tuple[str, object]],
    strip: frozenset[bytes] | None = None,
) -> set[str]:
    """The union of member blake3 hashes already persisted: full artifact enumeration per
    lineage record where the bytes are locally present, declared `msg=` transports as the
    warned fallback, plus every standalone `message/rfc822` record id. With `strip`,
    artifact enumeration hashes members as-if-stripped — a pre-strip snapshot serves as
    lineage across the strip boundary; the declared-embed fallback cannot (its hashes
    predate the strip), which its warning states."""
    excluded: set[str] = set()
    for rid, post in lineage:
        try:
            local = containment.ensure_local_bytes(
                corpus_root, rid, mime.extension_for(_MBOX_MIME)
            )
            scan = mboxfile.scan(local, None, strip=strip)
            note = (
                f" ({scan.stripped_members} hashed as-if-stripped)"
                if strip and scan.stripped_members
                else ""
            )
            print(
                f"  lineage {rid[:12]}: {scan.count} member(s) enumerated from artifact bytes{note}"
            )
            excluded.update(f.blake3 for f in scan.facts.values())
        except ArtifactMissing:
            declared = mbox_manifest.declared_transports(post)
            hashes = {
                t.split(":", 1)[1] for t in declared.values() if t.startswith("blake3:")
            }
            excluded.update(hashes)
            boundary = (
                " — and, with --strip active, embeds declared BEFORE the strip convention "
                "will not match (under-exclusion risk)"
                if strip
                else ""
            )
            print(
                f"  lineage {rid[:12]}: artifact bytes unavailable — falling back to "
                f"{len(hashes)} declared embed(s), a SUBSET of its members for a "
                f"selectively-declared mailbox{boundary}",
                file=sys.stderr,
            )
    rfc822 = 0
    for rf in records.iter_record_paths(corpus_root):
        post = records.load(rf)
        if records.media_type_for(post) == _RFC822_MIME:
            excluded.add(str(post.metadata.get("id") or rf.stem))
            rfc822 += 1
    if rfc822:
        print(f"  standalone message/rfc822 records: {rfc822}")
    return excluded


def _window_bounds(dates: list[str]) -> tuple[datetime, datetime] | None:
    parsed = []
    for raw in dates:
        try:
            parsed.append(parsedate_to_datetime(raw))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return None
    naive = [d.replace(tzinfo=UTC) if d.tzinfo is None else d for d in parsed]
    return min(naive), max(naive)


def _source_modified_iso(src: Path) -> str | None:
    try:
        ts = src.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    source = Path(args.source)
    if not source.is_file():
        sys.exit(f"source not found: {source}")

    from corpus import schemas

    cli_strip = None
    if getattr(args, "strip", None):
        cli_strip = [n.strip() for v in args.strip for n in v.split(",") if n.strip()]
        if not cli_strip:
            sys.exit("--strip: no header names given")
    strip_names = schemas.resolve_strip_headers(corpus_root, _MBOX_MIME, cli_strip) or None
    strip = mboxfile.normalize_strip_headers(strip_names)
    if strip_names:
        print(f"  chrome-strip active: {', '.join(strip_names)}")

    lineage = _expand_lineage(corpus_root, list(args.against))
    excluded_set = _exclusion_set(corpus_root, lineage, strip=strip)

    scan = mboxfile.scan(source, None, strip=strip)
    selected: list[int] = []
    seen_in_source: set[str] = set()
    excluded = duplicates = 0
    for n in range(1, scan.count + 1):
        b3 = scan.facts[n].blake3
        if b3 in excluded_set:
            excluded += 1
        elif b3 in seen_in_source:
            duplicates += 1
        else:
            seen_in_source.add(b3)
            selected.append(n)

    summary = (
        f"{scan.count} member(s) in source: {len(selected)} new, "
        f"{excluded} already persisted, {duplicates} within-source duplicate(s)"
    )
    if not selected:
        print(f"{summary} — empty delta, nothing to emit.")
        return 0

    bounds = _window_bounds([scan.facts[n].date or "" for n in selected])
    stem = source.stem + "-window"
    if bounds:
        stem += f"-{bounds[0]:%Y%m%d}-{bounds[1]:%Y%m%d}"
    capture_dir = corpus_root / "capture"
    bundle = capture_dir / (stem + ".mbox")
    if bundle.exists():
        sys.exit(f"refusing to overwrite existing {bundle}")

    if args.dry_run:
        print(f"{summary} — would write {bundle.name}")
        return 0

    capture_dir.mkdir(exist_ok=True)
    tmp = bundle.with_suffix(".mbox.part")
    with tmp.open("wb") as out:
        written = mboxfile.extract_raw_members(source, set(selected), out, strip=strip)
    tmp.rename(bundle)

    origin_fields: dict[str, object] = {
        "source_export": source.name,
        "source_message_count": scan.count,
        "window_count": written,
        "excluded_count": excluded,
        "duplicate_count": duplicates,
        "window_against": [rid for rid, _ in lineage],
    }
    if mtime := _source_modified_iso(source):
        origin_fields["source_modified"] = mtime
    if bounds:
        origin_fields["window_start"] = bounds[0].isoformat()
        origin_fields["window_end"] = bounds[1].isoformat()
    if strip_names:
        origin_fields["stripped_headers"] = strip_names
        origin_fields["stripped_members"] = scan.stripped_members
    sidecar: dict[str, object] = {"origin_fields": origin_fields}
    if args.origin:
        sidecar["origin_schema"] = args.origin
    sidecar_path = bundle.with_suffix(bundle.suffix + ".capture.yaml")
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")

    print(f"{summary} — wrote {bundle.relative_to(corpus_root)} (+ sidecar)")
    print(f"  after ingest, declare fully: corpus reattest <id> --messages 1-{written}")
    return 0
