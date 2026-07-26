"""Debug listing: every schema visible from both sources."""

from __future__ import annotations

import argparse

from corpus import schemas as _schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    _schemas._sources.cache_clear()
    sources = _schemas._sources(root)
    print("Schema sources (resolved corpus-local-first):")
    for s in sources:
        print(f"  [{s.label}] {s.backend}")
    print()
    print("MIME schemas (any subtype yaml in mime/<axis>/<axis>_<sub>.yaml):")
    seen: dict[str, str] = {}
    for s in sources:
        for relpath in s.iter_yaml("mime"):
            seen.setdefault(relpath, s.label)
    for rel, label in sorted(seen.items()):
        print(f"  [{label}] {rel}")
    print()
    print("Atomic overlays:")
    for slash in _schemas.list_atomic_overlays(root):
        print(f"  {slash}")
    print()
    print("Form contracts (the shape-contract library — these files ARE the registry):")
    for form_id in _schemas.list_form_ids(root):
        overlay = _schemas.load_form_overlay(root, form_id) or {}
        first_line = (overlay.get("description") or "").strip().split("\n")[0]
        print(f"  {form_id:<16} {first_line[:96]}")
    print()
    print("Issue ids:")
    for iid in _schemas.list_issue_ids(root):
        print(f"  {iid}")
    return 0
