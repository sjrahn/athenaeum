#!/usr/bin/env python3
"""#149 — retype the records that a man-page extension typed as troff.

304 records across the two hubs (260 public, 44 private) carry
`mime: application/x-troff-man` over bytes that are nothing of the kind — inline SVG
documents in the public hub, Apple ProRAW DNGs (TIFF family) in the private one.
Nothing about the bytes said troff. The type was invented from a NAME that was never a
name: a promoted `el=` member with no declared filename had its element address folded
into one (`el=1.2.2.1.3.3` → `1.2.2.1.3.3`), and `mimetypes` reads a trailing `.1`
through `.9` as a man-page section. The sniffer had no SVG or TIFF signature to answer
with first, so the filename fallback won — over the roster's own correct declaration.

All three halves of that are fixed in the package (`corpus.mime._looks_like_svg`, the
TIFF rows in `_SIGNATURES`, `corpus.containment.member_sniff_name`), which stops the
next one. This sweep is for the records already minted.

**Every retype is proved against the bytes, per record, twice.** The type is not taken
from the roster, from the extension, or from this script's expectation of what it will
find:

  1. the member's bytes are streamed back out of its container and blake3'd — they must
     hash to the record's own id, or the record is not what it says it is and is refused;
  2. the fixed sniffer, given those bytes and NO filename, must independently answer a
     concrete type — a record whose bytes it cannot name (`unknown`) is refused and
     reported, because a sweep that cannot prove the new type has no business writing it.

A record failing either check is left exactly as it is. Failures are per-record and
never abort the sweep (parse-tolerantly, the project rule): 304 records is a population,
not a transaction, and a container that has gone missing must not hide the other 303.

The write is a two-field edit through the real serializer — artifact mime, plus the
`touch:` chain — and is refused on any record the serializer would not round-trip
unchanged (`records.dumps` != disk, the §12.28 rule reseat uses): a migration that
introduces unrelated diffs is not a migration.

Usage:
    retype_troff_svg.py --corpus-root <root> [--apply] [--json OUT]

Dry-run by default: it examines, verifies, and reports what `--apply` would write.
Idempotent — a retyped record leaves the population, so a second run finds nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import blake3
import frontmatter

from corpus import containment, mime, paths, records, touches
from corpus import functional_uri as furi
from corpus.store import ArtifactMissing

WRONG_TYPE = "application/x-troff-man"

#: Touch stamped on every record this sweep rewrites (`corpus.migrate.retype-149@<version>`).
TOUCH_ID = "migrate.retype-149"

# Enough to reach every signature `corpus.mime` scans for (its own `_SNIFF_BYTES`).
_HEAD = 512


class Refused(Exception):
    """A record this sweep will not retype, carrying the reason it is reported under."""

    def __init__(self, reason: str, kind: str = "other") -> None:
        super().__init__(reason)
        self.kind = kind


def member_bytes(corpus_root: Path, post: frontmatter.Post) -> bytes:
    """The record's bytes, resolved through containment exactly as `corpus promote` does:
    the first origin names the container and the member address, the container record
    supplies its media type and (for an `el=` address) the `addressing:` stamp that
    dispatches the address grammar, and the member streams out of the container's bytes."""
    uri = next(records.iter_origin_uris(post), None)
    if not uri:
        raise Refused("record carries no origin uri")
    try:
        parsed = furi.parse(uri)
    except ValueError as exc:
        raise Refused(f"first origin {uri!r} is not a corpus URI: {exc}") from exc
    if parsed.is_bare:
        raise Refused(f"first origin {uri!r} names no container member")

    container_file = paths.record_path(corpus_root, parsed.hash)
    if not container_file.is_file():
        raise Refused(f"no container record for {parsed.hash[:12]}…")
    container_post = records.load(container_file)
    container_media_type = records.media_type_for(container_post)

    # Reserved chars decoded (§6.1) — the address as `open_member_stream` matches it.
    address = "&".join(
        k if v is None else f"{k}={furi.unquote_value(v)}" for k, v in parsed.params
    )
    try:
        container_path = containment.ensure_local_bytes(
            corpus_root, parsed.hash, mime.extension_for(container_media_type)
        )
    except ArtifactMissing as exc:
        raise Refused(f"container bytes unresolvable: {exc}") from exc

    with containment.open_member_stream(
        container_path,
        container_media_type,
        address,
        el_addressing=records.el_addressing(container_post),
    ) as fp:
        return fp.read()


def retype(post: frontmatter.Post, to_type: str) -> None:
    """Rewrite the artifact block's mime and append this pass to the touch chain. Whatever
    else the artifact block carries (an `addressing:` stamp, `fields:`) is preserved — only
    the mime is wrong."""
    artifact = records.artifact_block(post) or {}
    records.set_artifact_block(post, mime=to_type, fields=dict(artifact.get("fields") or {}))
    touches.record_touch(post, touches.script_identifier(TOUCH_ID))


def process(
    corpus_root: Path,
    path: Path,
    original: str,
    post: frontmatter.Post,
    *,
    apply: bool,
) -> dict[str, Any]:
    """One record, independently. Returns its row; raises `Refused` for a record left alone.
    `original` is the text `post` was parsed from — the baseline the dumps-stability check
    compares a rewrite against."""
    rid = str(post.metadata.get("id") or path.stem)
    row: dict[str, Any] = {"id": rid, "record": str(path.relative_to(corpus_root))}

    data = member_bytes(corpus_root, post)
    computed = blake3.blake3(data).hexdigest()
    if computed != rid:
        raise Refused(
            f"member streams to blake3 {computed[:12]}… but the record's id is {rid[:12]}… — "
            f"these are not the bytes this record stands for",
            kind="hash",
        )
    sniffed = mime.sniff_head(data[:_HEAD], None)
    if sniffed in ("unknown", WRONG_TYPE):
        raise Refused(
            f"the bytes sniff as {sniffed} with no filename — the troff type is wrong but "
            f"this sweep cannot prove what is right, so it writes nothing",
            kind="sniff",
        )
    row["bytes"] = len(data)
    row["type"] = sniffed

    if not apply:
        return row
    if records.dumps(post) != original:
        raise Refused(
            "record is not dumps-stable — the serializer would introduce changes unrelated "
            "to the retype",
            kind="unstable",
        )
    retype(post, sniffed)
    records.dump(post, path)
    row["retyped"] = True
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus-root", type=Path, required=True)
    ap.add_argument(
        "--apply", action="store_true", help="write the retypes (default: report only)"
    )
    ap.add_argument("--json", type=Path, help="write the per-record results + counts here")
    args = ap.parse_args()

    root = args.corpus_root.resolve()
    if not (root / "records").is_dir():
        sys.exit(f"{root} has no records/ directory — not a corpus root")

    rows: list[dict[str, Any]] = []
    refused: list[dict[str, str]] = []
    counts = dict.fromkeys(
        ("examined", "verified", "retyped", "refused-hash", "refused-sniff",
         "refused-unstable", "refused-other", "errored"),
        0,
    )

    for path in sorted(root.joinpath("records").rglob("*.md")):
        try:
            original = path.read_text(encoding="utf-8")
            post = records.loads(original)
        except Exception as exc:  # an unloadable record is not this sweep's business
            print(f"  skip {path.name}: unreadable ({exc})", file=sys.stderr)
            continue
        if records.media_type_for(post) != WRONG_TYPE:
            continue
        counts["examined"] += 1
        rid = str(post.metadata.get("id") or path.stem)
        try:
            row = process(root, path, original, post, apply=args.apply)
        except Refused as exc:
            counts[f"refused-{exc.kind}"] += 1
            refused.append({"id": rid, "outcome": f"refused-{exc.kind}", "reason": str(exc)})
            continue
        except Exception as exc:  # log and keep going — one bad record is not the population
            counts["errored"] += 1
            refused.append(
                {"id": rid, "outcome": "errored", "reason": f"{type(exc).__name__}: {exc}"}
            )
            continue
        counts["verified"] += 1
        if row.get("retyped"):
            counts["retyped"] += 1
        rows.append(row)

    mode = "APPLY" if args.apply else "dry run (nothing written)"
    print(f"\n{root} — {mode}\n")
    print(f"  {counts['examined']:6}  examined ({WRONG_TYPE} records)")
    print(f"  {counts['verified']:6}  verified (bytes hash to the id AND sniff to a type)")
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    for t, n in sorted(by_type.items()):
        print(f"  {n:6}    → {t}")
    print(f"  {counts['retyped']:6}  retyped")
    for kind in ("hash", "sniff", "unstable", "other"):
        print(f"  {counts[f'refused-{kind}']:6}  refused ({kind})")
    print(f"  {counts['errored']:6}  errored")

    if refused:
        print("\nleft alone — every one, with its reason:")
        for entry in refused:
            print(f"  {entry['id'][:12]}…  {entry['outcome']:16}  {entry['reason']}")
    if not args.apply and counts["verified"]:
        print(f"\n{counts['verified']} records would be retyped. Re-run with --apply to write.")

    if args.json:
        args.json.write_text(
            json.dumps({"root": str(root), "applied": args.apply, "counts": counts,
                        "records": rows, "refused": refused}, indent=1),
            encoding="utf-8",
        )
        print(f"\nresults → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
