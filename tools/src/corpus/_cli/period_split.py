"""File-grain temporal stratification — `corpus period-split` (spec §12.3.14).

The file-grain sibling of `mbox-split` (§12.3.13): a producer that re-delivers
date-addressable FILES — a photo-library export, a message-platform per-item dump —
rather than a flat mbox gets the same closed-period / rolling / undated shape, one
member file at a time instead of one mbox member at a time.

`<source>` is a directory tree or a zip archive of member files, some of which may carry
a paired JSON sidecar. The member<->sidecar pairing is PRODUCER-DECLARED — read from the
`--origin` overlay ladder's `sidecar.pairing` declaration (spec §7.2, v41; v36 carried it
as a code registry, now retired): a `template` such as `"{member}.json"` (a photo
library: `IMG_0918.HEIC` pairs with `IMG_0918.HEIC.json`) or `"{stem}.metadata.json"`
(a mail export: `<id>.eml` pairs with `<id>.metadata.json`), expanded against the
export's member names and PRESENT-ONLY — a member whose expansion names nothing has no
sidecar (an `_edited.jpeg` render has none of its own; under the `sidecar:` date axis
it therefore has nothing to read a date from and lands in the undated bucket, a
disclosed limitation, not a bug). Nothing here knows which producer it is splitting:
a new producer joins by declaration alone. The same declaration MAY name EXPORT-LEVEL
metadata files that pair with no member at all (`pairing.export_level`, e.g. a
`labels.json` naming every label an account has) — excluded from bucketing entirely
and disclosed in the split's summary, never bucketed as an undated primary.

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

**The UTC boundary (spec §12.3.14, v34 owner ruling).** Every bucket boundary — a
member's own period AND the open/closed comparison against `--current-period` — is a
UTC calendar boundary. On the `sidecar:` date axis, an offset-bearing ISO value converts
to UTC before its year/month is read; a naive value (no offset in the bytes) buckets at
face value UNLESS a `render_timezone` applies (v38, the rendered-local axis class —
§12.3.14) — either `--render-timezone` on THIS run (final, ahead of everything: the
render zone is an export-RUN property, not a machine constant, so a divergent export
converts through the zone it was actually measured to) or the resolved origin overlay's
standing `render_timezone:` declaration — in which case the naive value is attached to
the applicable zone and converted through it, DST-aware, before the UTC read (see
`schemas.resolve_render_timezone` / `_common.bucket_rendered_local`). Tooling cannot
detect a rendered-local axis on its own — only a declaration or override distinguishes
it from an ordinary naive value, so an undeclared, unoverridden naive value stays
face-value, exactly as before. There is no per-source timezone knob for anything else
beyond this axis. The `mtime` axis is unaffected
by any of this: a directory source's mtime is already read as UTC, and a zip source's
`ZipInfo.date_time` is naive by format (no offset ever present) — both already bucket
correctly under the rule as written.

**The index-file axis (spec §7.2 `date_index:` / §12.3.14, v44).** A producer whose
members carry NO per-member sidecar, and whose dates live in ONE index file keyed by
member path (a Meta export: `stories.json` is `{ig_stories: [{uri, creation_timestamp,
…}]}`, `posts_N.json` a top-level list of posts each with `media: [{uri,
creation_timestamp}]`), declares the index on its origin overlay — `file` (a glob over
member paths), `entries` (the dotted path to the entry array; arrays along the way are
traversed), `key` (the entry field holding the member path) — and the split reads each
member's date from ITS entry at `--date-from index:<dotted-path>`. Every value rule
above applies unchanged: an epoch integer is UTC by definition, an offset-bearing ISO
string converts, a naive one is face-value unless a `render_timezone` applies. The
index files are members of the export but never PRIMARIES — like `pairing.export_level`
they are excluded from bucketing and disclosed (`date_index_files`); an entry naming no
member is counted (`date_index_unmatched`), a member path two entries date differently
buckets undated rather than by guess (`date_index_conflicts`), and a member with no
entry at all lands undated exactly as a sidecar-less member does on the sidecar axis.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from corpus import sidecar
from corpus._cli._common import (
    add_corpus_root_arg,
    bucket_rendered_local,
    bucket_year_month,
    parse_current_period,
    resolved_corpus_root,
)


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
            "the per-member date axis: `mtime` (the member file's own mtime); "
            "`sidecar:<dotted-path>` (read from the member's paired sidecar JSON at "
            "that key path, e.g. `sidecar:date` for a photo library's per-item JSON, "
            "`sidecar:Payload.Time` for a mail export's epoch field; the pairing itself is "
            "the origin overlay's `sidecar.pairing` declaration, spec §7.2); or "
            "`index:<dotted-path>` (v44: read from the member's entry in the export's "
            "index file(s) at that key path, e.g. `index:creation_timestamp` for a Meta "
            "export's `stories.json` / `posts_N.json`; which files, which entry array "
            "and which entry field names the member path is the origin overlay's "
            "`date_index:` declaration, spec §7.2). A sidecar or index "
            "value may "
            "be an ISO string or an epoch-seconds INTEGER (v36) — the integer form is "
            "UTC by definition. A member with no parseable date on this axis goes to "
            "the undated bucket."
        ),
    )
    parser.add_argument(
        "--render-timezone",
        default=None,
        metavar="IANA-ZONE",
        dest="render_timezone",
        help=(
            "rendered-local axis OVERRIDE (spec §12.3.14, v38; final, ahead of the "
            "origin overlay's `render_timezone:` declaration) — the render zone is an "
            "export-RUN property, not a machine constant, so a divergent export (the "
            "producing machine's automatic timezone put it somewhere else this run) "
            "converts through the zone THIS export was measured to, not the overlay's "
            "standing declaration. Validated the same way either source is: an unknown "
            "IANA zone is a hard error."
        ),
    )
    parser.add_argument(
        "--current-period",
        default=None,
        metavar="YYYY-MM",
        help="the month treated as open (default: the current UTC year-month); months "
        "(or, under a year-grain era, years) strictly before it are closed and each "
        "become their own zip. Every member's own period is read at the UTC boundary "
        "too (spec §12.3.14) — on the sidecar axis, an offset-bearing ISO value "
        "converts to UTC first; a naive one buckets at face value.",
    )
    add_corpus_root_arg(parser)


# ---------- sidecar pairing (producer-declared, spec §7.2 `sidecar:` — v41) ---------- #
#
# The pairing is the overlay's `sidecar.pairing` declaration, resolved through the same
# `--origin` id-prefix namespace walk `partition:` uses (`corpus.sidecar.
# resolve_declaration`). The v36 per-producer function registry that lived here is
# retired: the declaration IS the convention, and `corpus promote` reads the very same one
# to project the sidecar into the promoted record — one declaration, two consumers, no
# producer name anywhere in this module.


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
    if text.startswith("index:"):
        dotted = text[len("index:") :].strip()
        if not dotted:
            sys.exit("--date-from index:<dotted-path> needs a non-empty path")
        return "index", dotted
    sys.exit(
        f"--date-from: expected 'mtime', 'sidecar:<dotted-path>' or 'index:<dotted-path>', "
        f"got {spec!r}"
    )
    raise AssertionError("unreachable")


def _sidecar_date_year_month(
    data: bytes, dotted_path: str, render_zone: ZoneInfo | None = None
) -> tuple[int, int] | None:
    """Read a date value at `dotted_path` from sidecar JSON `data` and return its
    `(year, month)` — tolerant throughout: malformed JSON, a missing/non-object
    intermediate segment, a non-numeric/non-string or unparseable value all read as "no
    date" (undated), never an error that would abort the whole split.

    Two value SHAPES (v36): a **string**, read per the UTC boundary rule (spec §12.3.14,
    v34 owner ruling) — an offset-bearing ISO value converts to UTC before its
    year/month is read; a NAIVE value (no offset in the bytes) buckets at face value
    UNLESS `render_zone` is given (v38, the rendered-local axis class), in which case it
    is attached to `render_zone` and converted through it — see
    `_common.bucket_rendered_local`; or an **epoch-seconds integer** (a mail export's
    `Payload.Time`) — UTC BY DEFINITION, so `render_zone` never applies to it (the v34
    boundary question doesn't even arise). `bool` is deliberately excluded even though
    it is an `int` subclass in Python — never a legitimate date value. A negative epoch
    (pre-1970) or one large enough to overflow `datetime`'s year-9999 ceiling is rejected
    outright (undated) rather than bucketed into a bogus year — a producer's numeric date
    axis is never a place to guess."""
    try:
        doc = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return _date_value_year_month(_walk(doc, dotted_path), render_zone)


def _walk(doc: Any, dotted_path: str) -> Any:
    """`doc` walked by `dotted_path` through nested objects; None when any segment is
    absent or the value at it is not an object."""
    value: Any = doc
    for seg in dotted_path.split("."):
        if not isinstance(value, dict) or seg not in value:
            return None
        value = value[seg]
    return value


def _date_value_year_month(
    value: Any, render_zone: ZoneInfo | None = None
) -> tuple[int, int] | None:
    """One date-axis VALUE (a sidecar field, an index entry field) → `(year, month)` under
    the rules `_sidecar_date_year_month` documents, or None. Shared by the sidecar and
    index axes so both read a value identically — the v34 boundary rule, the v36 epoch
    form and the v38 rendered-local class are properties of the value, not of where it
    was found."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value < 0:
            return None
        try:
            dt = datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
        return bucket_year_month(dt)
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None and render_zone is not None:
        return bucket_rendered_local(dt, render_zone)
    return bucket_year_month(dt)


# ---------- the index-file axis (spec §7.2 `date_index:`, v44) ---------- #


@dataclass
class _DateIndex:
    """Every member path an export's index file(s) date, resolved once up front. `dates`
    maps member path → `(year, month)` (None: the entry's date value was unparseable —
    undated, never guessed); `files` are the index members themselves (excluded from
    bucketing, disclosed); `unmatched` counts entries naming no member of this export;
    `conflicts` counts member paths two entries dated DIFFERENTLY (such a member buckets
    undated — the index disagrees with itself, and the split does not pick a side)."""

    dates: dict[str, tuple[int, int] | None] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    unmatched: int = 0
    conflicts: int = 0


def _index_entries(doc: Any, entries_path: str) -> list[dict[str, Any]]:
    """The entry objects an index document yields at `entries_path`: walk each dotted
    segment through objects, mapping over any array met on the way (a top-level list
    of posts, each carrying a `media` array, yields every post's media entries at
    `media`); `[]` suffixes are accepted as the strip_fields notation and mean the
    same traversal. Only objects are entries — anything else at the end is ignored."""
    nodes: list[Any] = [doc]
    for seg in [s for s in entries_path.split(".") if s]:
        key = seg
        while key.endswith("[]"):
            key = key[:-2]
        if not key:  # a bare `[]` segment: traverse only, no key step
            nodes = _flatten(nodes)
            continue
        nxt: list[Any] = []
        for n in _flatten(nodes):
            if isinstance(n, dict) and key in n:
                nxt.append(n[key])
        nodes = nxt
    return [n for n in _flatten(nodes) if isinstance(n, dict)]


def _flatten(nodes: list[Any]) -> list[Any]:
    out: list[Any] = []
    for n in nodes:
        if isinstance(n, list):
            out.extend(_flatten(n))
        else:
            out.append(n)
    return out


def _load_date_index(
    src: _Source,
    names: list[str],
    declarations: list[dict[str, str]],
    date_path: str,
    render_zone: ZoneInfo | None,
) -> _DateIndex:
    """Read every declared index file present in the export and resolve each entry's
    member path → date. An index file that does not parse as JSON is a hard exit (the
    declaration named it as the axis; silently dating nothing would send the whole
    export undated with no signal)."""
    index = _DateIndex()
    name_set = set(names)
    # member path → the distinct parsed dates its entries carry (order-independent: an
    # unparseable entry contributes nothing, so it never manufactures a conflict).
    seen: dict[str, set[tuple[int, int]]] = {}
    for decl in declarations:
        matched = sorted(n for n in names if fnmatch.fnmatchcase(n, decl["file"]))
        for idx_name in matched:
            if idx_name not in index.files:
                index.files.append(idx_name)
            try:
                doc = json.loads(src.read(idx_name))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                sys.exit(f"{idx_name}: declared date_index file is not JSON: {exc}")
            for entry in _index_entries(doc, decl["entries"]):
                member = _walk(entry, decl["key"])
                if not isinstance(member, str) or member not in name_set:
                    index.unmatched += 1
                    continue
                ym = _date_value_year_month(_walk(entry, date_path), render_zone)
                dates = seen.setdefault(member, set())
                if ym is not None:
                    dates.add(ym)
    index.files.sort()
    for member, dates in seen.items():
        if len(dates) > 1:
            index.conflicts += 1
            index.dates[member] = None
        else:
            index.dates[member] = next(iter(dates), None)
    return index


def _resolve_date(
    src: _Source,
    primary: str,
    sidecar_name: str | None,
    axis: tuple[str, str | None],
    render_zone: ZoneInfo | None,
    date_index: _DateIndex | None = None,
) -> tuple[int, int] | None:
    kind, dotted_path = axis
    if kind == "mtime":
        dt = src.mtime(primary)
        return dt.year, dt.month
    if kind == "index":
        assert date_index is not None
        return date_index.dates.get(primary)
    if sidecar_name is None:
        return None
    assert dotted_path is not None
    return _sidecar_date_year_month(src.read(sidecar_name), dotted_path, render_zone)


# ---------- run ---------- #


def run(args: argparse.Namespace) -> int:
    from corpus import hashing, schemas

    corpus_root = resolved_corpus_root(args)
    source_path = Path(args.source)
    if not source_path.exists():
        sys.exit(f"source not found: {source_path}")

    try:
        schedule = schemas.resolve_partition(corpus_root, "application/zip", origin_id=args.origin)
        render_zone_name = schemas.resolve_render_timezone(
            corpus_root,
            "application/zip",
            getattr(args, "render_timezone", None),
            origin_id=args.origin,
        )
    except ValueError as exc:
        sys.exit(str(exc))
    render_zone = ZoneInfo(render_zone_name) if render_zone_name else None
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

    try:
        declaration = sidecar.resolve_declaration(corpus_root, args.origin)
    except sidecar.DeclarationError as exc:
        sys.exit(str(exc))
    if declaration is None and axis[0] == "sidecar":
        sys.exit(
            f"--origin {args.origin!r} declares no `sidecar:` on its overlay ladder "
            f"(spec §7.2) — --date-from sidecar:… needs its `pairing.template` to find "
            f"each member's sidecar (spec §12.3.14); a producer with no sidecar "
            f"declaration can still use --date-from mtime."
        )
    index_declarations: list[dict[str, str]] | None = None
    if axis[0] == "index":
        try:
            index_declarations = schemas.resolve_date_index(
                corpus_root, "application/zip", origin_id=args.origin
            )
        except ValueError as exc:
            sys.exit(str(exc))
        if index_declarations is None:
            sys.exit(
                f"--origin {args.origin!r} declares no `date_index:` on its overlay ladder "
                f"(spec §7.2, v44) — --date-from index:… needs its `file`/`entries`/`key` "
                f"to find each member's entry (spec §12.3.14); a producer with no index "
                f"declaration can still use --date-from mtime."
            )
    export_level_names = declaration.export_level if declaration is not None else frozenset()

    src = _open_source(source_path)
    try:
        all_names = src.names()
        if not all_names:
            sys.exit(f"{source_path.name}: no members found")
        excluded_export_level = sorted(n for n in all_names if n in export_level_names)
        names = [n for n in all_names if n not in export_level_names]
        date_index: _DateIndex | None = None
        if index_declarations is not None:
            assert axis[1] is not None
            date_index = _load_date_index(src, names, index_declarations, axis[1], render_zone)
            if not date_index.files:
                sys.exit(
                    f"{source_path.name}: no member matches the declared date_index "
                    f"file(s) {[d['file'] for d in index_declarations]} — nothing to "
                    f"read dates from (spec §12.3.14)"
                )
            index_files = set(date_index.files)
            names = [n for n in names if n not in index_files]
        if not names:
            sys.exit(f"{source_path.name}: no members found (only export-level metadata?)")
        name_set = set(names)

        sidecar_of: dict[str, str] = {}
        if declaration is not None:
            for n in names:
                sc = declaration.sidecar_for(n, name_set)
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
            ym = _resolve_date(src, p, sidecar_of.get(p), axis, render_zone, date_index)
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
            if render_zone_name:
                # Disclosed so the rendered-local bucketing is reproducible from the
                # sidecar alone — the zone that converted this bucket's naive values.
                origin_fields["render_timezone"] = render_zone_name
            if period is not None:
                origin_fields["period"] = period
            if source_transport:
                origin_fields["source_transport"] = source_transport
            if excluded_export_level:
                # An export-wide fact (like `source_export`/`date_axis` above), disclosed
                # on every emitted bucket rather than picking one to own it.
                origin_fields["export_level_metadata"] = excluded_export_level
            if date_index is not None:
                # The index axis's own disclosure (v44), export-wide like the above: which
                # members were the index, how many entries named nothing here, and how
                # many members the index dated two ways (bucketed undated, never guessed).
                origin_fields["date_index_files"] = list(date_index.files)
                if date_index.unmatched:
                    origin_fields["date_index_unmatched"] = date_index.unmatched
                if date_index.conflicts:
                    origin_fields["date_index_conflicts"] = date_index.conflicts
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
        if excluded_export_level:
            print(
                f"  export-level metadata (excluded from bucketing): "
                f"{', '.join(excluded_export_level)}"
            )
        if date_index is not None:
            print(
                f"  date index (excluded from bucketing): {', '.join(date_index.files)} — "
                f"{sum(1 for v in date_index.dates.values() if v is not None)} member(s) "
                f"dated, {date_index.unmatched} entr(y/ies) naming no member, "
                f"{date_index.conflicts} conflict(s)"
            )
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
