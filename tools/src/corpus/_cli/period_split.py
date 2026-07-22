"""File-grain temporal stratification — `corpus period-split` (spec §12.3.14).

The file-grain sibling of `mbox-split` (§12.3.13): a producer that re-delivers
date-addressable FILES — a photo-library export, a message-platform per-item dump —
rather than a flat mbox gets the same closed-period / rolling / undated shape, one
member file at a time instead of one mbox member at a time.

`<source>` is a directory tree or a zip archive of member files, some of which may carry
a paired JSON sidecar (recon target: the `osxphotos-export` origin in `corpus-private` —
a media file `<name>.<ext>` pairs with a PhotoInfo sidecar named exactly `<name>.<ext>.json`
when one exists; an `_edited.jpeg` derivative render has NO sidecar of its own — under the
`sidecar:` date axis it therefore has nothing to read a date from and lands in the undated
bucket, a disclosed limitation, not a bug). The pairing rule is a small, swappable function
(`_osxphotos_sidecar_for`) — a future producer's different convention replaces just that
one function, never the bucketing logic around it.

Unlike `mbox-split`, there is no legacy no-schedule behavior to fall back to: a generic
zip/tree has no honest media-type `default_origin` binding, so `--origin` is REQUIRED, and
a producer with no `partition:` schedule declared on that origin's ladder is a hard exit
pointing at the spec §12.3.14 measurement gate (the two-export diff that earns a
closed-period byte-stability claim in the first place).

Bucketing mirrors `mbox-split`'s schedule interpretation exactly (`schemas.grain_for_year`
— eras at their own grain, the top-level grain past every era, `--current-period YYYY-MM`
for deterministic testing) but the OUTPUT shape differs: each closed period becomes its
OWN standalone zip (`<stem>-<period>.zip`) rather than one member inside a shared
container — there is no single "container" here, since file-grain members don't need a
shared promotable envelope the way mbox members do. `ZipInfo.date_time` for every written
entry is the member's OWN mtime (never "now", never the source's mtime) — cross-export
byte-stability of these zips depends entirely on the producer PRESERVING bytes and mtimes
across export runs, which is exactly what the §12.3.14 measurement is required to
establish before a schedule is declared at all.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from corpus._cli._common import add_corpus_root_arg, parse_current_period, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="path to a directory tree or zip of member files.")
    parser.add_argument(
        "--origin",
        required=True,
        metavar="OVERLAY-ID",
        help=(
            "origin overlay id (REQUIRED — a generic zip/tree has no honest media-type "
            "`default_origin` binding, so the producer must be named here). Namespace-"
            "walked for the `partition:` schedule declaration and stamped verbatim as "
            "`origin_schema:` on every emitted sidecar."
        ),
    )
    parser.add_argument(
        "--date-from",
        required=True,
        metavar="SPEC",
        dest="date_from",
        help=(
            "the per-member date axis: `mtime` (the member file's own mtime) or "
            "`sidecar:<dotted-path>` (read from the member's paired sidecar JSON at "
            "that key path, e.g. `sidecar:date` for an osxphotos PhotoInfo export). A "
            "member with no parseable date on this axis goes to the undated bucket."
        ),
    )
    parser.add_argument(
        "--current-period",
        default=None,
        metavar="YYYY-MM",
        help="the month treated as open (default: the current UTC year-month); months "
        "(or, under a year-grain era, years) strictly before it are closed and each "
        "become their own zip.",
    )
    add_corpus_root_arg(parser)


# ---------- sidecar pairing convention (osxphotos, first of possibly several) ------- #


def _osxphotos_sidecar_for(member: str, name_set: set[str]) -> str | None:
    """The osxphotos pairing convention (recon: `corpus-private`'s `osxphotos-export`
    containers — `IMG_0918.HEIC` pairs with `IMG_0918.HEIC.json`, whether or not the
    dialect's media name itself carries an `_Original` suffix): a media member's
    PhotoInfo sidecar is `<member>.json`, when that exact path exists among the
    export's members. An `_edited.jpeg` derivative has none of its own — deliberately
    NOT resolved here (no invented fallback to the original's sidecar); a small,
    swappable function, so a future producer's different convention replaces just this
    one, never the bucketing logic around it."""
    candidate = f"{member}.json"
    return candidate if candidate in name_set else None


# ---------- uniform read access over a directory tree OR a zip source --------------- #


class _Source:
    def names(self) -> list[str]:
        raise NotImplementedError

    def read(self, name: str) -> bytes:
        raise NotImplementedError

    def mtime(self, name: str) -> datetime:
        raise NotImplementedError

    def close(self) -> None:
        pass


class _DirSource(_Source):
    def __init__(self, root: Path) -> None:
        self._root = root
        self._names = sorted(
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
        )

    def names(self) -> list[str]:
        return list(self._names)

    def read(self, name: str) -> bytes:
        return (self._root / name).read_bytes()

    def mtime(self, name: str) -> datetime:
        ts = (self._root / name).stat().st_mtime
        return datetime.fromtimestamp(ts, UTC)


class _ZipSource(_Source):
    def __init__(self, path: Path) -> None:
        self._zip = zipfile.ZipFile(path)
        self._names = sorted(
            info.filename for info in self._zip.infolist() if not info.is_dir()
        )

    def names(self) -> list[str]:
        return list(self._names)

    def read(self, name: str) -> bytes:
        return self._zip.read(name)

    def mtime(self, name: str) -> datetime:
        # ZipInfo.date_time is a naive (year, month, day, hour, minute, second) 6-tuple —
        # exactly the shape a written ZipInfo wants back, no timezone to reconcile.
        return datetime(*self._zip.getinfo(name).date_time)

    def close(self) -> None:
        self._zip.close()


def _open_source(path: Path) -> _Source:
    if path.is_dir():
        return _DirSource(path)
    if zipfile.is_zipfile(path):
        return _ZipSource(path)
    sys.exit(f"{path}: not a directory or a zip file")
    raise AssertionError("unreachable")  # sys.exit always raises; satisfies type-checkers


# ---------- date axis ---------- #


def _parse_date_axis(spec: str) -> tuple[str, str | None]:
    text = (spec or "").strip()
    if text == "mtime":
        return "mtime", None
    if text.startswith("sidecar:"):
        dotted = text[len("sidecar:") :].strip()
        if not dotted:
            sys.exit("--date-from sidecar:<dotted-path> needs a non-empty path")
        return "sidecar", dotted
    sys.exit(f"--date-from: expected 'mtime' or 'sidecar:<dotted-path>', got {spec!r}")
    raise AssertionError("unreachable")


def _sidecar_date_year_month(data: bytes, dotted_path: str) -> tuple[int, int] | None:
    """Read a date value at `dotted_path` from sidecar JSON `data` and return its
    `(year, month)` — tolerant throughout: malformed JSON, a missing/non-object
    intermediate segment, a non-string or unparseable value all read as "no date"
    (undated), never an error that would abort the whole split."""
    try:
        doc = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    value: Any = doc
    for seg in dotted_path.split("."):
        if not isinstance(value, dict) or seg not in value:
            return None
        value = value[seg]
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt.year, dt.month


def _resolve_date(
    src: _Source, primary: str, sidecar_name: str | None, axis: tuple[str, str | None]
) -> tuple[int, int] | None:
    kind, dotted_path = axis
    if kind == "mtime":
        dt = src.mtime(primary)
        return dt.year, dt.month
    if sidecar_name is None:
        return None
    assert dotted_path is not None
    return _sidecar_date_year_month(src.read(sidecar_name), dotted_path)


# ---------- run ---------- #


def run(args: argparse.Namespace) -> int:
    from corpus import hashing, schemas

    corpus_root = resolved_corpus_root(args)
    source_path = Path(args.source)
    if not source_path.exists():
        sys.exit(f"source not found: {source_path}")

    schedule = schemas.resolve_partition(corpus_root, "application/zip", origin_id=args.origin)
    if schedule is None:
        sys.exit(
            f"no partition schedule declared for origin {args.origin!r} (spec §12.3.14) "
            "— period-split has no legacy no-schedule fallback: author the two-export "
            "measurement and a `partition:` block on the origin overlay's ladder first."
        )
    grain_default = str(schedule.get("grain") or "month")
    eras = list(schedule.get("eras") or [])
    undated_mode = str(schedule.get("undated") or "standing")

    current_period = parse_current_period(getattr(args, "current_period", None))
    axis = _parse_date_axis(args.date_from)

    src = _open_source(source_path)
    try:
        names = src.names()
        if not names:
            sys.exit(f"{source_path.name}: no members found")
        name_set = set(names)

        sidecar_of: dict[str, str] = {}
        for n in names:
            sc = _osxphotos_sidecar_for(n, name_set)
            if sc:
                sidecar_of[n] = sc
        is_sidecar = set(sidecar_of.values())
        primaries = [n for n in names if n not in is_sidecar]
        sidecar_of = {p: sidecar_of[p] for p in primaries if p in sidecar_of}
        if not primaries:
            sys.exit(f"{source_path.name}: no primary members found (only sidecars?)")

        bucket_of: dict[str, str] = {}
        undated = 0
        for p in primaries:
            ym = _resolve_date(src, p, sidecar_of.get(p), axis)
            if ym is None:
                undated += 1
                bucket_of[p] = "undated" if undated_mode == "standing" else "current"
                continue
            year, month = ym
            grain = schemas.grain_for_year(eras, grain_default, year)
            if grain == "month":
                is_current = (year, month) >= current_period
                key = f"{year:04d}-{month:02d}"
            else:
                is_current = year >= current_period[0]
                key = str(year)
            bucket_of[p] = "current" if is_current else key

        closed_keys = sorted({b for b in bucket_of.values() if b not in ("current", "undated")})
        current_primaries = [p for p in primaries if bucket_of[p] == "current"]
        undated_primaries = [p for p in primaries if bucket_of[p] == "undated"]

        stem = source_path.stem if source_path.is_file() else source_path.name
        capture_dir = corpus_root / "capture"
        capture_dir.mkdir(exist_ok=True)

        bucket_targets = {key: capture_dir / f"{stem}-{key}.zip" for key in closed_keys}
        current_period_str = f"{current_period[0]:04d}-{current_period[1]:02d}"
        current_target = capture_dir / f"{stem}-current-{current_period_str}.zip"
        undated_target = capture_dir / f"{stem}-undated.zip"

        all_targets = [*bucket_targets.values(), current_target]
        if undated_primaries:
            all_targets.append(undated_target)
        for target in all_targets:
            if target.exists():
                sys.exit(f"refusing to overwrite existing {target}")

        source_transport: str | None = None
        if source_path.is_file():
            source_transport = f"blake3:{hashing.hash_file(source_path)['blake3']}"

        def _bucket_entries(bucket_primaries: list[str]) -> list[str]:
            entries: list[str] = []
            for p in bucket_primaries:
                entries.append(p)
                if p in sidecar_of:
                    entries.append(sidecar_of[p])
            return sorted(entries)

        def _write_bucket_zip(
            target: Path,
            bucket_primaries: list[str],
            period: str | None,
            extra_fields: dict[str, Any],
        ) -> None:
            entries = _bucket_entries(bucket_primaries)
            tmp = target.with_suffix(".zip.part")
            with zipfile.ZipFile(tmp, "w") as z:
                for name in entries:
                    dt = src.mtime(name)
                    zi = zipfile.ZipInfo(
                        name, date_time=(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
                    )
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(zi, src.read(name))
            tmp.rename(target)

            sidecar_count = sum(1 for p in bucket_primaries if p in sidecar_of)
            origin_fields: dict[str, Any] = {
                "source_export": source_path.name,
                "member_count": len(bucket_primaries),
                "sidecar_count": sidecar_count,
                "date_axis": args.date_from,
            }
            if period is not None:
                origin_fields["period"] = period
            if source_transport:
                origin_fields["source_transport"] = source_transport
            origin_fields.update(extra_fields)
            sidecar_yaml: dict[str, Any] = {
                "origin_schema": args.origin,
                "origin_fields": origin_fields,
            }
            target.with_suffix(target.suffix + ".capture.yaml").write_text(
                yaml.safe_dump(sidecar_yaml, sort_keys=False), encoding="utf-8"
            )

        for key in closed_keys:
            bucket_primaries = [p for p in primaries if bucket_of[p] == key]
            _write_bucket_zip(bucket_targets[key], bucket_primaries, key, {})

        current_extra: dict[str, Any] = {}
        if undated_mode == "rolling" and undated:
            current_extra["undated_count"] = undated
        _write_bucket_zip(current_target, current_primaries, current_period_str, current_extra)

        if undated_primaries:
            # NO `period` field, ever — the undated bucket must never resolve a
            # period-driven title template; it falls through to role marks instead.
            _write_bucket_zip(undated_target, undated_primaries, None, {})

        closed_total = len(primaries) - len(current_primaries) - len(undated_primaries)
        if closed_keys:
            print(
                f"{len(primaries)} member(s): {closed_total} across {len(closed_keys)} "
                f"closed period(s) ({closed_keys[0]}-{closed_keys[-1]}) → "
                f"{len(closed_keys)} zip(s)"
            )
        else:
            print(f"{len(primaries)} member(s): no closed periods this run")
        print(f"  current → {current_target.name} ({len(current_primaries)} member(s))")
        if undated_primaries:
            print(f"  undated → {undated_target.name} ({len(undated_primaries)} member(s))")
        print(
            "  next: corpus ingest each emitted zip; promote closed-period members as "
            "needed."
        )
        print(
            "  rolling lifecycle: ingest the current-period zip; if a prior rolling "
            "record exists for this stream, run `corpus continuity <old> <new>` then "
            "ledger supersede — never delete anything automatically, an operator "
            "confirms the rm."
        )
        return 0
    finally:
        src.close()
