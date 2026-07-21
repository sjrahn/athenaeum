"""Closed-year snapshot split — `corpus mbox-split` (spec §12.3.13).

The re-baseline shape for a full-mailbox export: partition the canonicalized members by
Date-header year into per-year mboxes — CLOSED years only (strictly before the current
year; an unparseable Date is never falsely closed, it stays with the current residue) —
and assemble them into ONE deterministic zip container staged for ordinary ingest. The
container ingests as a zip-manifest record whose `<YYYY>.mbox` members are each
promotable (§8.1) to a first-class mbox record; the current year's members emit as a
residue mbox handed to `corpus mbox-window`, never to the container.

The chrome strip resolves from the same schema declaration ingest applies
(`strip_headers` on the corpus's application/mbox schema; `--strip` overrides), so a
closed year's stripped mbox is byte-identical in every future full export — the next
re-baseline's promoted year members re-encounter instead of re-minting.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

from corpus import hashing, mboxfile, schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="path to the full-mailbox export (mboxrd) to split.")
    parser.add_argument(
        "--current-year",
        type=int,
        default=None,
        metavar="YYYY",
        help="the year treated as open (default: the current UTC year); years strictly "
        "before it are closed and go to the container.",
    )
    parser.add_argument(
        "--origin",
        default=None,
        metavar="OVERLAY-ID",
        help="origin overlay id to stamp on the container sidecar (`origin_schema:`).",
    )
    parser.add_argument(
        "--strip",
        action="append",
        default=None,
        metavar="HEADER",
        help="chrome-strip override (repeatable; comma lists) — normally resolved from "
        "the corpus's application/mbox schema `strip_headers` declaration.",
    )
    add_corpus_root_arg(parser)


def _member_year(date_header: str | None) -> int | None:
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header).year
    except (TypeError, ValueError):
        return None


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
    current_year = args.current_year or datetime.now(UTC).year

    cli_strip = None
    if getattr(args, "strip", None):
        cli_strip = [n.strip() for v in args.strip for n in v.split(",") if n.strip()]
    strip_names = schemas.resolve_strip_headers(corpus_root, "application/mbox", cli_strip) or None
    strip = mboxfile.normalize_strip_headers(strip_names)
    if strip_names:
        print(f"  chrome-strip active: {', '.join(strip_names)}")

    scan = mboxfile.scan(source, None, strip=strip)
    if not scan.count:
        sys.exit(f"{source.name}: no messages found — not an mboxrd?")

    # Bucket every ordinal: closed year, or the current residue (current year + undated).
    bucket_of: dict[int, int | str] = {}
    undated = 0
    for n, facts in scan.facts.items():
        year = _member_year(facts.date)
        if year is None:
            undated += 1
            bucket_of[n] = "current"
        elif year >= current_year:
            bucket_of[n] = "current"
        else:
            bucket_of[n] = year
    closed_years = sorted({b for b in bucket_of.values() if isinstance(b, int)})
    current_count = sum(1 for b in bucket_of.values() if b == "current")
    if not closed_years:
        sys.exit(f"no closed-year members (current year {current_year}) — nothing to split.")

    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(exist_ok=True)
    container = capture_dir / f"{source.stem}-years-{closed_years[0]}-{closed_years[-1]}.zip"
    residue = capture_dir / f"{source.stem}-current-{current_year}.mbox"
    for target in (container, residue):
        if target.exists():
            sys.exit(f"refusing to overwrite existing {target}")

    # One demux pass into per-bucket temp files, then deterministic zip assembly.
    tmpdir = capture_dir / ".mbox-split-tmp"
    tmpdir.mkdir(exist_ok=True)
    try:
        handles: dict[int | str, object] = {}
        try:
            for bucket in [*closed_years, "current"]:
                handles[bucket] = (tmpdir / f"{bucket}.mbox").open("wb")
            sinks = {n: handles[b] for n, b in bucket_of.items()}
            mboxfile.demux_raw_members(source, sinks, strip=strip)
        finally:
            for fh in handles.values():
                fh.close()

        src_mtime = datetime.fromtimestamp(source.stat().st_mtime, UTC)
        zi_date = (src_mtime.year, src_mtime.month, src_mtime.day, 0, 0, 0)
        tmp_zip = container.with_suffix(".zip.part")
        with zipfile.ZipFile(tmp_zip, "w") as z:
            for year in closed_years:
                zi = zipfile.ZipInfo(f"{year}.mbox", date_time=zi_date)
                zi.compress_type = zipfile.ZIP_DEFLATED
                with (tmpdir / f"{year}.mbox").open("rb") as r, z.open(zi, "w") as w:
                    shutil.copyfileobj(r, w, 1 << 20)
            z.comment = f"mail year-split of {source.name} (closed years, stripped)".encode()
        tmp_zip.rename(container)
        shutil.move(tmpdir / "current.mbox", residue)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    year_counts = {
        str(y): sum(1 for b in bucket_of.values() if b == y) for y in closed_years
    }
    origin_fields: dict[str, object] = {
        "source_export": source.name,
        "source_message_count": scan.count,
        "source_transport": f"blake3:{hashing.hash_file(source)['blake3']}",
        "split_by": "year",
        "years": year_counts,
        "current_year": current_year,
        "current_count": current_count,
        "undated_count": undated,
    }
    if strip_names:
        origin_fields["stripped_headers"] = strip_names
        origin_fields["stripped_members"] = scan.stripped_members
    if mtime := _source_modified_iso(source):
        origin_fields["source_modified"] = mtime
    sidecar: dict[str, object] = {"origin_fields": origin_fields}
    if args.origin:
        sidecar["origin_schema"] = args.origin
    sidecar_path = container.with_suffix(container.suffix + ".capture.yaml")
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")

    closed_total = scan.count - current_count
    print(
        f"{scan.count} member(s): {closed_total} across {len(closed_years)} closed year(s) "
        f"({closed_years[0]}-{closed_years[-1]}) → {container.name}; "
        f"{current_count} current/undated ({undated} undated) → {residue.name}"
    )
    print(f"  next: corpus ingest {container.relative_to(corpus_root)}; promote the year "
          f"members; then mbox-window the residue against them.")
    return 0
