"""Scan the corpus for offline health signals.

Read-only and entirely offline (except the optional remote-store lookup behind
`missing_artifacts`, which `--skip-remote-check` disables). stdout: JSON (default) or
a summary digest (`--summary`); stderr: logs. Per-signal lists are capped by
`--limit` (default 50; `0` disables the cap).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    from corpus import health

    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = "Available signals:\n  " + "\n  ".join(health.SIGNAL_NAMES)
    parser.add_argument(
        "--summary", action="store_true", help="human-readable digest instead of JSON"
    )
    parser.add_argument(
        "--filter", default="", help="comma-separated signal names to run (default: all)"
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="max items per signal list (default 50; 0 = no cap)"
    )
    parser.add_argument("--snapshot", default="", help="also write the JSON report to this path")
    parser.add_argument(
        "--skip-remote-check",
        action="store_true",
        help="skip the remote-store lookup for missing_artifacts (entries → category=unknown)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import health

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    corpus_root = resolved_corpus_root(args)
    only = _parse_filter(args.filter, list(health.SIGNAL_NAMES))
    effective_limit = args.limit if args.limit > 0 else 10**6

    logging.info("scanning corpus at %s", corpus_root)
    report = health.scan_all(
        corpus_root, limit=effective_limit, only=only, skip_remote_check=args.skip_remote_check
    )
    logging.info("scanned %d record(s)", report["total_records"])

    if args.snapshot:
        snapshot = Path(args.snapshot)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        logging.info("wrote snapshot to %s", snapshot)

    if args.summary:
        sys.stdout.write(_format_summary(report))
    else:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


def _parse_filter(raw: str, known: list[str]) -> list[str] | None:
    if not raw:
        return None
    names = [s.strip() for s in raw.split(",") if s.strip()]
    if unknown := [n for n in names if n not in known]:
        sys.exit(f"unknown signal(s): {', '.join(unknown)}")
    return names


def _format_summary(report: dict[str, Any]) -> str:
    lines = [f"corpus health — {report['total_records']} record(s)", ""]

    if "layer_presence" in report:
        lp = report["layer_presence"]
        parts = ", ".join(
            f"{k}: {v}" for k, v in lp.items() if k in ("formed", "rendered", "proxy")
        )
        lines.append(f"layers: {parts}")
        lines.append(f"titled: {lp.get('titled', 0)}  untitled: {lp.get('untitled', 0)}")
        if lp.get("legacy_status"):
            lines.append(f"legacy_status: {lp['legacy_status']} (pending migration sweep)")
    if "records_by_mime" in report:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(report["records_by_mime"].items()))
        lines.append(f"mime: {parts}")
    if "unshaped" in report:
        items = report["unshaped"]
        shapable = sum(1 for i in items if i["shapable"])
        lines.append(f"unshaped: {len(items)} ({shapable} shapable)")
    if "unresolved_issues" in report:
        groups = report["unresolved_issues"]
        total = sum(len(v) for v in groups.values())
        bysev = ", ".join(f"{k}: {len(v)}" for k, v in sorted(groups.items()))
        lines.append(f"unresolved_issues: {total}" + (f" ({bysev})" if bysev else ""))
    if "missing_artifacts" in report:
        items = report["missing_artifacts"]
        by_cat: Counter[str] = Counter(i.get("category", "unknown") for i in items)
        bycat = ", ".join(f"{k}: {v}" for k, v in sorted(by_cat.items()))
        lines.append(f"missing_artifacts: {len(items)}" + (f" ({bycat})" if bycat else ""))
    if "validity_violations" in report:
        items = report["validity_violations"]
        lines.append(f"validity_violations: {len(items)}")
        for item in items[:5]:
            lines.append(f"  - {item['id'][:8]}… {item['problems'][0]}")

    return "\n".join(lines) + "\n"
