"""Assemble delivered export archives into ONE containment-friendly bundle (spec §2.1, §12.4).

    corpus assemble --origin <overlay-id> <source-archive>... [--add <file>]...

Repackages an export job's delivered part(s) — tar/tgz (Google Takeout), zip (Instagram),
or a loose directory tree (DiscordChatExporter) — plus any declared out-of-band additions
(a report) into one deterministic, indexed zip staged in the corpus `capture/` dir, ready
for `corpus ingest`. The byte mechanics live in the generic `corpus.assembly` engine; THIS
module reads the vendor-shaped config from the origin overlay (`capture.assembly`) and mints
the capture sidecar so ingest binds the `google-takeout` (or other) overlay and its fields
(spec §7.2, §12.3, §12.8 sidecars).

**No vendor knowledge is hardcoded here.** Which files are allowed additions, whether/how the
internal tree may be restructured, and the mechanical field-derivation patterns (the report's
account/job regexes, the delivery-filename convention) ALL come from the overlay's
`capture.assembly` config — so a new vendor is a new overlay, not new code. CLI flags
(`--account`, `--job`, `--exported-at`) override any derivation.

**The sidecar** (`<bundle>.capture.yaml`, consumed + removed by ingest, §12.3) carries
`origin_schema: <overlay-id>` and uri-less `origin_fields`: `account`, `exported_at`,
`services`, `job`, and `source_parts` (each retired source archive as `<name> blake3:<hash>` —
its tombstone, since the originals get retired after the bundle proves out).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

from corpus import assembly, schemas
from corpus._cli._common import add_corpus_root_arg, human_bytes, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "sources", nargs="+", type=Path,
        help="Source part(s): tar/tgz or zip archive(s), or loose directory tree(s).",
    )
    parser.add_argument(
        "--origin", required=True, help="Origin overlay id declaring capture.assembly (e.g. google-takeout)."
    )
    parser.add_argument(
        "--add", dest="additions", action="append", default=[], type=Path,
        help="A declared addition placed at the bundle root (repeatable; e.g. the report).",
    )
    parser.add_argument("--account", help="Override the derived account.")
    parser.add_argument("--job", help="Override the derived export-job id.")
    parser.add_argument("--exported-at", dest="exported_at", help="Override the derived export timestamp (ISO-8601).")
    parser.add_argument(
        "--source-name",
        help="Logical original filename for a single source (used for filename-convention "
        "derivation AND the source_parts tombstone label; default: the path's basename).",
    )
    parser.add_argument("--level", type=int, default=None, help="zstd level (default: overlay's, else 19).")
    parser.add_argument("--out", type=Path, default=None, help="Output path (default: capture/<derived-name>.zip).")
    parser.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)

    overlay = schemas.load_origin_overlay_by_id(corpus_root, args.origin)
    if overlay is None:
        sys.exit(f"no origin overlay {args.origin!r} (author schema/origin/**/{args.origin}.yaml first).")
    cfg = ((overlay.get("capture") or {}).get("assembly")) or {}
    if not cfg:
        sys.exit(f"overlay {args.origin!r} declares no capture.assembly config — nothing to assemble by.")

    sources = [p.resolve() for p in args.sources]
    additions = [p.resolve() for p in args.additions]
    for p in sources:
        if not (p.is_file() or p.is_dir()):
            sys.exit(f"not a file or directory: {p}")
    for p in additions:
        if not p.is_file():
            sys.exit(f"not a file: {p}")

    # Additions are a declared allowlist (by basename): the original tree is never restructured
    # by an undeclared file (spec §12.8 restructure rule). An --add not in the overlay is refused.
    declared = {str(a) for a in (cfg.get("additions") or [])}
    for add in additions:
        if add.name not in declared:
            sys.exit(
                f"addition {add.name!r} is not declared in {args.origin}'s capture.assembly.additions "
                f"({sorted(declared) or 'none'}) — declare it in the overlay to place it in the bundle."
            )

    if args.source_name and len(sources) > 1:
        sys.exit("--source-name applies to a single source; with several, each uses its own basename.")
    parts = [
        assembly.SourcePart(p, args.source_name if (args.source_name and len(sources) == 1) else p.name)
        for p in sources
    ]

    # Mechanical field derivation (overlay-declared patterns) + CLI overrides.
    additions_by_name = {p.name: p for p in additions}
    derived = _derive_fields(cfg, parts, additions_by_name)
    account = args.account or derived.get("account")
    job = args.job or derived.get("job")
    exported_at = args.exported_at or derived.get("exported_at")

    # `name_fields`: overlay-declared derived-field values that join the bundle's identity —
    # sanitized into its filename, verbatim into its comment (e.g. a discord export's guild).
    name_values = [derived[f] for f in (cfg.get("name_fields") or []) if derived.get(f)]

    level = args.level if args.level is not None else int(cfg.get("level", assembly.DEFAULT_LEVEL))
    comment = _job_comment(args.origin, job, account, exported_at, name_values)

    out_path = (
        args.out.resolve()
        if args.out
        else (corpus_root / "capture" / _bundle_name(args.origin, exported_at, job, name_values))
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = assembly.assemble(
            parts,
            additions,
            out_path,
            level=level,
            merge_parts=bool(cfg.get("merge_parts", True)),
            conflict=str(cfg.get("conflict", "error")),
            rewrites=list(cfg.get("rewrites") or []),
            excludes=list(cfg.get("excludes") or []),
            comment=comment,
        )
    except assembly.AssemblyError as e:
        sys.exit(f"assembly failed: {e}")

    # The uri-less local-file origin fields the sidecar seeds at ingest (spec §7.2).
    services: str | list[str] = result.services[0] if len(result.services) == 1 else result.services
    origin_fields: dict[str, Any] = {}
    if account:
        origin_fields["account"] = account
    if exported_at:
        origin_fields["exported_at"] = exported_at
    # `services` is takeout-vocabulary; seed it only where the overlay declares the field
    # (a media-tree export's top-level dirs are layout, not service slices).
    if services and "services" in (overlay.get("extended_fields") or {}):
        origin_fields["services"] = services
    if job:
        origin_fields["job"] = job
    # `seed_fields`: overlay-declared derived fields beyond the canonical trio that ride into
    # the sidecar (e.g. guild/guild_id). Named-group derivation alone deliberately does NOT
    # seed — takeout's `part` group is per-slice identity its bundle must dissolve.
    for name in cfg.get("seed_fields") or []:
        val = derived.get(str(name))
        if val and str(name) not in origin_fields:
            origin_fields[str(name)] = val
    if result.source_parts:
        origin_fields["source_parts"] = [f"{label} blake3:{h}" for label, h in result.source_parts]

    sidecar_path = _write_sidecar(out_path, args.origin, origin_fields)

    payload = {
        "bundle": str(out_path),
        "bundle_bytes": result.bundle_bytes,
        "member_count": result.member_count,
        "services": result.services,
        "job": job,
        "account": account,
        "exported_at": exported_at,
        "source_parts": [f"{label} blake3:{h}" for label, h in result.source_parts],
        "rewrites_applied": [{"from": f, "to": t} for f, t in result.rewrites_applied],
        "excluded": result.excluded,
        "sidecar": str(sidecar_path),
        "comment": comment,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"bundle: {out_path}")
    print(f"  size:      {human_bytes(result.bundle_bytes)} ({result.bundle_bytes} bytes)")
    print(f"  members:   {result.member_count} ({', '.join(result.services) or 'no services'})")
    print(f"  comment:   {comment}")
    for label, h in result.source_parts:
        print(f"  source:    {label} blake3:{h}")
    for frm, to in result.rewrites_applied:
        print(f"  rewrite:   {frm} -> {to}")
    for rel in result.excluded:
        print(f"  excluded:  {rel}")
    print(f"  sidecar:   {sidecar_path.name}")
    print(f"  next:      corpus ingest {out_path}")
    return 0


# ---------- overlay-declared field derivation ---------- #


def _derive_fields(
    cfg: dict[str, Any], parts: list[assembly.SourcePart], additions: dict[str, Path]
) -> dict[str, str]:
    """Apply the overlay's `capture.assembly.derive` patterns (all vendor-shaped knowledge) to
    the source filenames, addition bytes, and member heads. Three declared shapes, all
    optional:

    - `from_source_name: <regex>` — matched against each source's logical filename; every named
      group becomes a field of that name, except `exported_stamp`, decoded compact-ISO →
      `exported_at`. The first matching source wins (a multi-part job shares its stamp).
    - `from_additions: {<filename>: {<field>: <regex>}}` — each regex's group 1 over a present
      addition's UTF-8 text sets `<field>`.
    - `from_member_head: {glob, bytes, fields: {<field>: <regex>}}` — DIRECTORY sources only:
      each regex's group 1 over the first `bytes` (default 4096) of every member whose relpath
      fnmatches `glob`; across members the lexicographically GREATEST value wins — an
      order-independent choice that lands on the run's completion stamp for ISO timestamps
      and is a no-op for values every member states identically (a guild name).

    Returns the derived fields; the caller lets CLI flags override."""
    derive = cfg.get("derive") or {}
    out: dict[str, str] = {}

    pat = derive.get("from_source_name")
    if pat:
        rx = re.compile(str(pat))
        for part in parts:
            m = rx.search(part.label)
            if not m:
                continue
            for key, val in (m.groupdict() or {}).items():
                if not val:
                    continue
                if key == "exported_stamp":
                    iso = _compact_iso(val)
                    if iso:
                        out.setdefault("exported_at", iso)
                else:
                    out.setdefault(key, val)
            break

    for fname, field_patterns in (derive.get("from_additions") or {}).items():
        add = additions.get(str(fname))
        if add is None or not isinstance(field_patterns, dict):
            continue
        text = add.read_text(encoding="utf-8", errors="replace")
        for field, regex in field_patterns.items():
            match = re.search(str(regex), text)
            if match and match.group(1):
                out.setdefault(str(field), match.group(1).strip())

    head_cfg = derive.get("from_member_head") or {}
    if head_cfg:
        for field, value in _derive_from_member_heads(head_cfg, parts).items():
            out.setdefault(field, value)
    return out


def _derive_from_member_heads(
    head_cfg: dict[str, Any], parts: list[assembly.SourcePart]
) -> dict[str, str]:
    """The `from_member_head` shape (see `_derive_fields`). Walks directory sources only —
    an archive's members would need a decompression pass just to derive, and every archive
    vendor so far states its facts out-of-band (filename convention, report addition)."""
    glob = str(head_cfg.get("glob") or "*")
    head_bytes = int(head_cfg.get("bytes", 4096))
    field_patterns = head_cfg.get("fields") or {}
    if not isinstance(field_patterns, dict):
        return {}
    best: dict[str, str] = {}
    for part in parts:
        if not part.path.is_dir():
            continue
        for member in sorted(p for p in part.path.rglob("*") if p.is_file()):
            rel = member.relative_to(part.path).as_posix()
            if not (fnmatch(rel, glob) or fnmatch(rel.rsplit("/", 1)[-1], glob)):
                continue
            with member.open("rb") as fp:
                text = fp.read(head_bytes).decode("utf-8", errors="replace")
            for field, regex in field_patterns.items():
                match = re.search(str(regex), text)
                if match and match.group(1):
                    val = match.group(1).strip()
                    if val > best.get(str(field), ""):
                        best[str(field)] = val
    return best


def _compact_iso(stamp: str) -> str | None:
    """`20260703T165759Z` → `2026-07-03T16:57:59Z`. None when it isn't that compact shape."""
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", stamp)
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}Z"


def _compact_stamp(exported_at: str) -> str:
    """`2026-07-03T16:57:59Z` → `20260703T165759Z` — the stable, self-describing filename token
    (only the `-`/`:` separators are dropped; the `T` and any `Z` survive). A producer stamp
    carrying fractional seconds or a UTC offset (DCE's `…35.01719-06:00`) is truncated to
    whole seconds for the FILENAME only — the sidecar field keeps the verbatim value."""
    compact = re.sub(r"[-:]", "", exported_at)
    m = re.match(r"^(\d{8}T\d{6})", compact)
    if m:
        return m.group(1) + ("Z" if exported_at.endswith("Z") else "")
    return compact


def _name_token(value: str) -> str:
    """A derived-field value → a filename-safe token: runs of anything outside
    `[A-Za-z0-9._]` collapse to `-` (`RPG nights with random blokes` →
    `RPG-nights-with-random-blokes`)."""
    return re.sub(r"[^A-Za-z0-9._]+", "-", value).strip("-")


def _bundle_name(
    origin: str, exported_at: str | None, job: str | None, name_values: list[str] | None = None
) -> str:
    """`<overlay-id>[-<name-tokens>][-<exported-stamp>][-<job8>].zip` — stable and
    self-describing. Falls back to the pieces that are known (a bare `<overlay-id>.zip` if
    nothing else). `name_values` are the overlay's `name_fields` values, sanitized."""
    parts = [origin]
    for value in name_values or []:
        token = _name_token(value)
        if token:
            parts.append(token)
    if exported_at:
        parts.append(_compact_stamp(exported_at))
    if job:
        parts.append(job.split("-", 1)[0])
    return "-".join(parts) + ".zip"


def _job_comment(
    origin: str,
    job: str | None,
    account: str | None,
    exported_at: str | None,
    name_values: list[str] | None = None,
) -> str:
    """The zip archive comment stamped with the job identity (the `zip-manifest` drafter
    surfaces it as the artifact block's `comment`). `name_fields` values ride verbatim —
    they ARE the job's identity where no job id exists (a discord export's guild)."""
    bits = [origin]
    for value in name_values or []:
        bits.append(value)
    if job:
        bits.append(f"job {job}")
    if account:
        bits.append(account)
    if exported_at:
        bits.append(f"exported {exported_at}")
    return " · ".join(bits)


def _write_sidecar(out_path: Path, origin: str, origin_fields: dict[str, Any]) -> Path:
    """Write the ingest capture sidecar next to the bundle: a uri-less local-file origin that
    stamps `origin_schema` + `origin_fields` (spec §7.2, §12.3). No `source_url` — the bundle
    is a produced local file, not a retrieval."""
    sidecar_path = out_path.with_name(out_path.name + ".capture.yaml")
    doc = {"origin_schema": origin, "origin_fields": origin_fields}
    sidecar_path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return sidecar_path
