"""Closed-period snapshot split — `corpus mbox-split` (spec §12.3.13, §12.3.14).

The re-baseline shape for a full-mailbox export: partition the canonicalized members by
Date-header period into per-period mboxes — CLOSED periods only (strictly before the
current period at each member's own grain; an unparseable Date is never falsely closed,
it stays with the current residue or, under a `standing` undated policy, its own bucket)
— and assemble them into ONE deterministic zip container staged for ordinary ingest. The
container ingests as a zip-manifest record whose `<bucket>.mbox` members are each
promotable (§8.1) to a first-class mbox record; the current period's members emit as a
residue mbox handed to `corpus mbox-window`, never to the container.

The chrome strip resolves the same chain ingest does (spec §12.3.13): `strip_headers`
declared on the producer's origin overlay, namespace-walked from `--origin` (or, when
`--origin` is omitted, from the mime schema's `default_origin` binding); `--strip`
overrides either. So a closed period's stripped mbox is byte-identical in every future
full export — the next re-baseline's promoted members re-encounter instead of re-minting.

**Schedule-driven bucketing (spec §12.3.14).** A producer origin overlay may declare a
`partition:` block — the same resolution chain as the strip (no CLI override point):
`grain` (`month` | `year`), optional `eras` (historical strata at their OWN grain, each
`{until: <year>, grain: ...}`), and `undated` (`standing` — its own bucket — or
`rolling` — rides the current residue, the default). A member's YEAR selects its era (the
first, sorted by `until` ascending, whose boundary the year doesn't exceed; past every
era, the schedule's top-level `grain` applies) — so ONE export can split 2005-2025 by
YEAR (re-encountering already-promoted year records) and 2026+ by MONTH, in one
container. With NO schedule declared, behavior is EXACTLY the pre-schedule year-grain split
(undated rides the residue) — existing corpora are unaffected.

**The UTC boundary (spec §12.3.14, v34 owner ruling).** Every bucket boundary — a
member's own period AND the open/closed comparison against `--current-period` /
`--current-year` — is a UTC calendar boundary. A Date: header carrying an offset
converts to UTC before its year/month is read; a naive header (no offset in the bytes)
buckets at face value. There is no per-source timezone knob.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import yaml

from corpus import hashing, mboxfile, schemas
from corpus._cli._common import (
    add_corpus_root_arg,
    bucket_year_month,
    parse_current_period,
    resolved_corpus_root,
)

# The pre-schedule (no partition declared) behavior, expressed as a schedule: pure
# year grain, no historical eras, undated rides the current residue.
_DEFAULT_SCHEDULE: dict[str, Any] = {"grain": "year", "eras": [], "undated": "rolling"}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="path to the full-mailbox export (mboxrd) to split.")
    parser.add_argument(
        "--current-year",
        type=int,
        default=None,
        metavar="YYYY",
        help="the year treated as open for YEAR-grain buckets (default: the current UTC "
        "year); years strictly before it are closed and go to the container. Every "
        "member's own year is read at the UTC boundary too (spec §12.3.14) — an "
        "offset-bearing Date: header converts to UTC first; a naive one buckets at face "
        "value.",
    )
    parser.add_argument(
        "--current-period",
        default=None,
        metavar="YYYY-MM",
        help="the month treated as open for MONTH-grain buckets (default: the current "
        "UTC year-month); months strictly before it are closed and go to the container. "
        "Only meaningful when a partition schedule (spec §12.3.14) resolves month grain. "
        "Every member's own month is read at the UTC boundary too — an offset-bearing "
        "Date: header converts to UTC first; a naive one buckets at face value.",
    )
    parser.add_argument(
        "--origin",
        default=None,
        metavar="OVERLAY-ID",
        help=(
            "origin overlay id to stamp on the container/residue/undated sidecars "
            "(`origin_schema:`) and to namespace-walk for the chrome-strip and "
            "partition-schedule declarations; when omitted, resolves from the mime "
            "schema's `default_origin` binding and auto-stamps that instead."
        ),
    )
    parser.add_argument(
        "--strip",
        action="append",
        default=None,
        metavar="HEADER",
        help="chrome-strip override (repeatable; comma lists) — normally resolved from "
        "the producer's origin overlay (namespace-walked via --origin, or the mime "
        "schema's `default_origin` binding).",
    )
    add_corpus_root_arg(parser)


def _member_date_parts(date_header: str | None) -> tuple[int, int] | None:
    """Return `(year, month)` parsed from a Date: header, or None if unparseable — per
    the UTC boundary rule (spec §12.3.14, v34 owner ruling): an offset-bearing header
    converts to UTC before its year/month is read; `parsedate_to_datetime` returns a
    NAIVE datetime for a `-0000`-style header (no offset in the bytes), which buckets at
    face value rather than an invented UTC."""
    if not date_header:
        return None
    try:
        dt = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
    return bucket_year_month(dt)


def _source_modified_iso(src: Path) -> str | None:
    try:
        ts = src.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_split_sidecar(
    path: Path, origin_fields: dict[str, Any], effective_origin: str | None
) -> None:
    sidecar: dict[str, Any] = {"origin_fields": origin_fields}
    if effective_origin:
        sidecar["origin_schema"] = effective_origin
    sidecar_path = path.with_suffix(path.suffix + ".capture.yaml")
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    source = Path(args.source)
    if not source.is_file():
        sys.exit(f"source not found: {source}")
    current_year = args.current_year or datetime.now(UTC).year
    current_period = parse_current_period(getattr(args, "current_period", None))

    cli_strip = None
    if getattr(args, "strip", None):
        cli_strip = [n.strip() for v in args.strip for n in v.split(",") if n.strip()]
    strip_names = schemas.resolve_strip_headers(
        corpus_root, "application/mbox", cli_strip, origin_id=args.origin
    ) or None
    strip = mboxfile.normalize_strip_headers(strip_names)
    if strip_names:
        print(f"  chrome-strip active: {', '.join(strip_names)}")

    try:
        schedule = schemas.resolve_partition(corpus_root, "application/mbox", origin_id=args.origin)
    except ValueError as exc:
        sys.exit(str(exc))
    schedule_declared = schedule is not None
    if schedule_declared:
        eras_note = f", {len(schedule.get('eras') or [])} era(s)" if schedule.get("eras") else ""
        print(f"  partition schedule active: grain={schedule.get('grain')}{eras_note}")
    else:
        schedule = _DEFAULT_SCHEDULE
    grain_default = str(schedule.get("grain") or "year")
    eras = list(schedule.get("eras") or [])
    undated_mode = str(schedule.get("undated") or "standing")

    scan = mboxfile.scan(source, None, strip=strip)
    if not scan.count:
        sys.exit(f"{source.name}: no messages found — not an mboxrd?")

    # Bucket every ordinal: a closed period (at ITS OWN era's grain), the current residue,
    # or — under a `standing` undated policy — the separate undated bucket.
    bucket_of: dict[int, str] = {}
    undated = 0
    for n, facts in scan.facts.items():
        parts = _member_date_parts(facts.date)
        if parts is None:
            undated += 1
            bucket_of[n] = "undated" if undated_mode == "standing" else "current"
            continue
        year, month = parts
        grain = schemas.grain_for_year(eras, grain_default, year)
        if grain == "month":
            is_current = (year, month) >= current_period
            key = f"{year:04d}-{month:02d}"
        else:
            is_current = year >= current_year
            key = str(year)
        bucket_of[n] = "current" if is_current else key

    closed_keys = sorted({b for b in bucket_of.values() if b not in ("current", "undated")})
    current_count = sum(1 for b in bucket_of.values() if b == "current")
    undated_standing_count = sum(1 for b in bucket_of.values() if b == "undated")
    if not closed_keys:
        if not schedule_declared:
            sys.exit(f"no closed-year members (current year {current_year}) — nothing to split.")
        sys.exit("no closed-period members — nothing to split.")

    has_month_grain = any("-" in k for k in closed_keys)
    residue_grain = grain_default

    capture_dir = corpus_root / "capture"
    capture_dir.mkdir(exist_ok=True)
    stem_word = "periods" if has_month_grain else "years"
    container = capture_dir / f"{source.stem}-{stem_word}-{closed_keys[0]}-{closed_keys[-1]}.zip"
    if residue_grain == "month":
        residue_name = f"{source.stem}-current-{current_period[0]:04d}-{current_period[1]:02d}.mbox"
    else:
        residue_name = f"{source.stem}-current-{current_year}.mbox"
    residue = capture_dir / residue_name
    undated_bundle = capture_dir / f"{source.stem}-undated.mbox"
    targets = [container, residue, *([undated_bundle] if undated_standing_count else [])]
    for target in targets:
        if target.exists():
            sys.exit(f"refusing to overwrite existing {target}")

    # One demux pass into per-bucket temp files, then deterministic zip assembly.
    tmpdir = capture_dir / ".mbox-split-tmp"
    tmpdir.mkdir(exist_ok=True)
    try:
        buckets = [*closed_keys, "current", *(["undated"] if undated_standing_count else [])]
        handles: dict[str, object] = {}
        try:
            for bucket in buckets:
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
            for key in closed_keys:
                zi = zipfile.ZipInfo(f"{key}.mbox", date_time=zi_date)
                zi.compress_type = zipfile.ZIP_DEFLATED
                with (tmpdir / f"{key}.mbox").open("rb") as r, z.open(zi, "w") as w:
                    shutil.copyfileobj(r, w, 1 << 20)
            grain_word = "period" if has_month_grain else "year"
            z.comment = f"mail {grain_word}-split of {source.name} (closed, stripped)".encode()
        tmp_zip.rename(container)
        shutil.move(tmpdir / "current.mbox", residue)
        if undated_standing_count:
            shutil.move(tmpdir / "undated.mbox", undated_bundle)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    period_counts = {k: sum(1 for b in bucket_of.values() if b == k) for k in closed_keys}
    year_keys = [k for k in closed_keys if "-" not in k]
    origin_fields: dict[str, Any] = {
        "source_export": source.name,
        "source_message_count": scan.count,
        "source_transport": f"blake3:{hashing.hash_file(source)['blake3']}",
        "split_by": "period" if has_month_grain else "year",
        "periods": period_counts,
        "periods_start": closed_keys[0],
        "periods_end": closed_keys[-1],
        "export_date": datetime.fromtimestamp(source.stat().st_mtime, UTC).date().isoformat(),
        "current_year": current_year,
        "current_count": current_count,
        "undated_count": undated,
    }
    if residue_grain == "month":
        origin_fields["current_period"] = f"{current_period[0]:04d}-{current_period[1]:02d}"
    if year_keys:
        origin_fields["years"] = {k: period_counts[k] for k in year_keys}
        origin_fields["years_start"] = year_keys[0]
        origin_fields["years_end"] = year_keys[-1]
    if strip_names:
        origin_fields["stripped_headers"] = strip_names
        origin_fields["stripped_members"] = scan.stripped_members
    if mtime := _source_modified_iso(source):
        origin_fields["source_modified"] = mtime

    effective_origin = args.origin or schemas.resolve_default_origin(
        corpus_root, "application/mbox"
    )
    if effective_origin and not args.origin:
        print(f"  origin auto-stamped from default_origin: {effective_origin}")
    _write_split_sidecar(container, origin_fields, effective_origin)

    # The rolling residue gets its OWN sidecar (the rolling record's title composes from
    # `period`, spec §12.3.14 — "Mail — {period}" — under month grain only; a year-grain
    # residue carries no `period`, exactly as it never did pre-schedule).
    residue_fields: dict[str, Any] = {
        "source_export": source.name,
        "source_message_count": current_count,
    }
    if residue_grain == "month":
        residue_fields["period"] = f"{current_period[0]:04d}-{current_period[1]:02d}"
    if undated_mode == "rolling" and undated:
        residue_fields["undated_count"] = undated
    _write_split_sidecar(residue, residue_fields, effective_origin)

    if undated_standing_count:
        # NO `period` field, ever — an undated bucket must never resolve a period-driven
        # title template; it falls through to role marks (or stays untitled) instead.
        undated_fields: dict[str, Any] = {
            "source_export": source.name,
            "source_message_count": undated_standing_count,
        }
        _write_split_sidecar(undated_bundle, undated_fields, effective_origin)

    closed_total = scan.count - current_count - undated_standing_count
    summary = (
        f"{scan.count} member(s): {closed_total} across {len(closed_keys)} closed period(s) "
        f"({closed_keys[0]}-{closed_keys[-1]}) → {container.name}; "
        f"{current_count} current → {residue.name}"
    )
    if undated_standing_count:
        summary += f"; {undated_standing_count} undated → {undated_bundle.name}"
    print(summary)
    print(
        f"  next: corpus ingest {container.relative_to(corpus_root)}; promote the closed "
        f"period members; then mbox-window (or re-split) the residue."
    )
    print(
        "  rolling lifecycle: ingest the residue; if a prior rolling record exists for "
        "this stream, run `corpus continuity <old> <new>` then ledger supersede — never "
        "delete anything automatically, an operator confirms the rm."
    )
    return 0
