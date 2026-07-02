"""List composite namespaces declared in the corpus (interpretive overlays)."""

from __future__ import annotations

import argparse

from corpus import schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    namespaces = schemas.list_classifications(root)
    if not namespaces:
        print("no composite namespaces declared in schema/composite/.")
        print("Bootstrap one with: corpus init . --namespace <name>")
        return 0
    for ns in namespaces:
        schema = schemas.load_classification_schema(root, ns) or {}
        kind = schema.get("kind", "?")
        desc = (schema.get("description") or "").strip().splitlines()[0:1]
        head = desc[0][:70] if desc else ""
        print(f"  {ns:<24}  [{kind:<12}]  {head}")
        for sub_id in schemas.list_classification_subclasses(root, ns):
            print(f"    └─ {ns}/{sub_id}")
    return 0
