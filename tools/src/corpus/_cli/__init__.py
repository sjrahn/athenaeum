"""Unified `corpus` CLI dispatcher.

Adding a subcommand: drop a module `corpus._cli.<name>` exposing `configure(parser)`
and `run(args)`, then register the name in `_COMMANDS` below. Modules are
lazy-imported per invocation so cold start stays cheap.
"""

from __future__ import annotations

import argparse
import importlib
import keyword
import sys
from collections.abc import Sequence

__all__ = ["dispatch", "main"]


# (group, one-line help). Order within a group preserved at render time.
_COMMANDS: dict[str, tuple[str, str]] = {
    # Scaffolding (P1)
    "init":            ("Scaffolding",            "Scaffold a new corpus tree (records/ + schema/)"),
    # Capture & ingest (P2; capture added P4)
    "capture":         ("Capture & ingest",       "Capture a URL into capture/, then ingest to a record stub"),
    "session":         ("Capture & ingest",       "Capture a Claude Code session (bundle → ingest → draft); list sessions"),
    "check":           ("Capture & ingest",       "Read-only: is a URL already captured? (resolves short links)"),
    "ingest":          ("Capture & ingest",       "Ingest a capture/ file → records/<shard>/<hash>.md"),
    "promote":         ("Capture & ingest",       "Mint a record for a container member (corpus://<id>?<member-address>)"),
    "assemble":        ("Capture & ingest",       "Repackage delivered export archives into one containment-friendly bundle"),
    "draft":           ("Capture & ingest",       "Run the deterministic drafter (stub → draft)"),
    "resolve":         ("Capture & ingest",       "Materialise a corpus:// functional URI → cached file path"),
    "re-stub":         ("Capture & ingest",       "Reset a record to status: stub, preserving byte + provenance"),
    "reattest":        ("Capture & ingest",       "Bulk re-derive the attested layer from artifacts (never touches the authored layer)"),
    "redraft":         ("Capture & ingest",       "Bulk re-derive whole records (2.x; superseded by reattest for the attested layer)"),
    # Normalization queue (P6) — request/claim contract for the interpretive normalize stage (spec §8.5)
    "enqueue":         ("Normalize",              "Request a (re-)normalization pass for a record"),
    "drain":           ("Normalize",              "Claim the next queued record (prints its id; empty queue → exit 1)"),
    "finalize":        ("Normalize",              "Close a claimed pass (gated on status: normalized + lint-clean)"),
    "release":         ("Normalize",              "Return a claimed record to the queue (or --failed)"),
    "await":           ("Normalize",              "Block until a record's requested normalization pass settles"),
    "queue":           ("Normalize",              "List the normalization queue (requested + claimed)"),
    # Crawl & discovery (P4)
    "crawl":           ("Crawl & discovery",      "Same-domain BFS over a seed URL (captures each page)"),
    "links":           ("Crawl & discovery",      "List outbound URLs from a record's HTML artifact"),
    # Inspect (P1)
    "show":            ("Inspect",                "Compact record summary (frontmatter + content blocks)"),
    "diagnose":        ("Inspect",                "Per-record one-pager: lint + derived views + block TOC (normalizer's first call)"),
    "guidance":        ("Inspect",                "Print the normalization guidance for a record's mime + applied overlays"),
    "workflow":        ("Inspect",                "Operating-mode runbooks for the tooling (loop modes, queue lifecycle)"),
    "overlay":         ("Inspect",                "Show an origin overlay's declarations + normalization tactics"),
    "preview":         ("Inspect",                "Render an artifact with bbox marks, fit to a model's input budget (the cropping loop's eyes)"),
    "toc":             ("Inspect",                "Top-level block table of contents"),
    "body":            ("Inspect",                "Stream a record's body (stored, else the derived `body` op)"),
    "lint":            ("Inspect",                "Conformance check (the verification gate)"),
    "health":          ("Inspect",                "Offline corpus-wide health signals (JSON or --summary)"),
    # Edit (P1)
    "decompose":       ("Edit",                   "Explode a record into a working dir (manifest + body/desc files)"),
    "compile":         ("Edit",                   "Rebuild a record from a decomposed working dir"),
    # Storage (P3)
    "store":           ("Storage",                "Status / push / pull / fetch against the configured ArtifactStore"),
    # Maintenance — derived-data hygiene + deliberate record removal
    "gc":              ("Maintenance",            "Prune regenerable data (cache / staging / orphan artifacts / export)"),
    "rm":              ("Maintenance",            "Remove a record (.md + artifact + empty shard dirs); ref-checked, dry-run by default"),
    "forget-origin":   ("Maintenance",            "Drop one origin alias from a record (keeps the record)"),
    "continuity":      ("Maintenance",            "Prove whether one record's content is preserved in another (supersession check)"),
    # Query (P1)
    "find":            ("Query",                  "List records matching status / mime / origin"),
    "atoms":           ("Query",                  "List atomic overlays + their body / lossless contract"),
    "hosts":           ("Query",                  "Count records by origin host"),
    "schemas":         ("Query",                  "List packaged + corpus-local schemas (debug)"),
}

# Render groups in this order in `corpus --help`.
_GROUP_ORDER: tuple[str, ...] = (
    "Scaffolding",
    "Capture & ingest",
    "Normalize",
    "Crawl & discovery",
    "Inspect",
    "Edit",
    "Storage",
    "Maintenance",
    "Query",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        _print_top_help()
        return 0
    if args[0] in ("--version", "-V"):
        from corpus import __version__

        print(__version__)
        return 0
    cmd = args[0]
    if cmd not in _COMMANDS:
        print(f"corpus: unknown command {cmd!r}", file=sys.stderr)
        print("Run 'corpus --help' to see available commands.", file=sys.stderr)
        return 2
    return dispatch([cmd, *args[1:]])


def dispatch(argv: Sequence[str]) -> int:
    """Dispatch a fully-formed argv (subcommand first)."""
    if not argv:
        _print_top_help()
        return 0
    cmd, *rest = argv
    if cmd not in _COMMANDS:
        print(f"corpus: unknown command {cmd!r}", file=sys.stderr)
        return 2
    try:
        module = importlib.import_module(f"corpus._cli.{_module_name(cmd)}")
    except ImportError as e:
        print(f"corpus: subcommand {cmd!r} not yet implemented: {e}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(
        prog=f"corpus {cmd}",
        description=(module.__doc__ or "").strip() or None,
    )
    module.configure(parser)
    args = parser.parse_args(rest)
    return int(module.run(args) or 0)


# ---------- internals ---------- #


def _module_name(cmd: str) -> str:
    """Map a subcommand name to its module name (dashes → underscores). A name that
    collides with a Python keyword (e.g. `await`) gets a trailing underscore so the
    module file is importable (`await_.py`)."""
    name = cmd.replace("-", "_").replace(".", "_")
    if keyword.iskeyword(name):
        name += "_"
    return name


def _print_top_help() -> None:
    """Render the grouped help banner for `corpus --help`."""
    print("usage: corpus <command> [options...]")
    print()
    print("Corpus tooling — parse, lint, draft, resolve, derive views.")
    print()
    by_group: dict[str, list[tuple[str, str]]] = {}
    for cmd, (group, help_text) in _COMMANDS.items():
        by_group.setdefault(group, []).append((cmd, help_text))
    width = max(len(c) for c in _COMMANDS) + 2
    for group in _GROUP_ORDER:
        items = by_group.get(group)
        if not items:
            continue
        print(f"{group}:")
        for name, help_text in items:
            print(f"  {name:<{width}}{help_text}")
        print()
    print("Use 'corpus <command> --help' for command-specific options.")
