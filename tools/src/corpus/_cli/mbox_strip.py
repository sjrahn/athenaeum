"""Mailbox chrome strip — `corpus mbox-strip` (spec §12.3.13).

The pre-ingest pass for a FULL mailbox snapshot: streams the export once and writes into
`capture/` a copy with the declared provider-metadata headers removed from every member's
header zone (folded continuations included; body lines never touched). The stripped bytes
are the stored bytes — member blake3 over them is the one identity — so workflow-state
churn the provider writes into the export (Gmail's `X-Gmail-Labels`: read state,
categories, importance, user labels) can never move a member's address. The HTML
chrome-strip precedent (§12.3.6) on the mail axis: declarative header list only, no eval.

The strip is disclosed on the capture sidecar (`stripped_headers` + the member count
touched) alongside the source export's identity. Thin window bundles apply the same
filter via `corpus mbox-window --strip`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from corpus import mboxfile
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="path to the full-mailbox export (mboxrd) to strip.")
    parser.add_argument(
        "--strip",
        action="append",
        required=True,
        metavar="HEADER",
        help=(
            "header name to remove from every member (repeatable; comma lists accepted), "
            "e.g. --strip X-Gmail-Labels. Folded continuations go with the header; body "
            "lines are never touched."
        ),
    )
    parser.add_argument(
        "--origin",
        default=None,
        metavar="OVERLAY-ID",
        help="origin overlay id to stamp on the sidecar (`origin_schema:`).",
    )
    add_corpus_root_arg(parser)


def parse_strip_args(values: list[str]) -> list[str]:
    names = [n.strip() for v in values for n in v.split(",") if n.strip()]
    if not names:
        sys.exit("--strip: no header names given")
    return names


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
    names = parse_strip_args(list(args.strip))
    strip = mboxfile.normalize_strip_headers(names)

    capture_dir = corpus_root / "capture"
    out_path = capture_dir / (source.stem + "-stripped.mbox")
    if out_path.exists():
        sys.exit(f"refusing to overwrite existing {out_path}")
    capture_dir.mkdir(exist_ok=True)

    # One counting pass (facts as-if-stripped), then one emit pass copying every member
    # raw minus the declared headers. Two streams over the source, nothing held in RAM.
    scan = mboxfile.scan(source, None, strip=strip)
    if scan.count == 0:
        sys.exit(f"{source.name}: no messages found — not an mboxrd?")
    tmp = out_path.with_suffix(".mbox.part")
    with tmp.open("wb") as out:
        written = mboxfile.extract_raw_members(
            source, set(range(1, scan.count + 1)), out, strip=strip
        )
    tmp.rename(out_path)

    origin_fields: dict[str, object] = {
        "source_export": source.name,
        "source_message_count": scan.count,
        "stripped_headers": names,
        "stripped_members": scan.stripped_members,
    }
    if mtime := _source_modified_iso(source):
        origin_fields["source_modified"] = mtime
    sidecar: dict[str, object] = {"origin_fields": origin_fields}
    if args.origin:
        sidecar["origin_schema"] = args.origin
    sidecar_path = out_path.with_suffix(out_path.suffix + ".capture.yaml")
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")

    print(
        f"{written} member(s) written, {scan.stripped_members} carried stripped header(s) "
        f"({', '.join(names)}) — wrote {out_path.relative_to(corpus_root)} (+ sidecar)"
    )
    return 0
