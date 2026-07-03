"""Describe an origin overlay — the tactics lookup for the normalizer.

`corpus overlay <host>` describes an **origin** overlay (`schema/origin/<host>.yaml`): its
host match, the operational sections it declares (capture/transcription/canonical/metadata),
and its `normalization.guidance` — so the normalizer can read a host's guidance at normalize
time without opening the yaml (the same guidance `corpus guidance <id>` shows once an origin
overlay is applied to a record).

Markdown to stdout; non-zero when no origin overlay matches.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from corpus import schemas
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "overlay_id", help="origin overlay id, e.g. `my.alldata.com`, `imessage-export`."
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    origin = schemas.load_origin_overlay_by_id(corpus_root, args.overlay_id)
    if origin is None:
        sys.exit(
            f"no origin overlay {args.overlay_id!r} (schema/origin/{args.overlay_id}.yaml)."
        )
    return _run_origin(corpus_root, args.overlay_id, origin)


def _run_origin(corpus_root, oid: str, overlay: dict[str, Any]) -> int:
    print(f"# overlay {oid}  (origin)\n")
    print(f"_source: `{_origin_relpath(corpus_root, oid)}`_\n")

    print("## applies_to\n")
    applies = overlay.get("applies_to") or {}
    pats = [str(applies["host_pattern"])] if applies.get("host_pattern") else []
    pats += [str(p) for p in (applies.get("host_patterns") or [])]
    if pats:
        print(f"- host: {', '.join(pats)}")
        if applies.get("include_subdomains"):
            print("- include_subdomains: true")
    else:
        print(f"- _(matched by id `{oid}` — no host pattern declared)_")
    print()

    declared = [
        k
        for k in ("capture", "transcription", "canonical", "metadata")
        if isinstance(overlay.get(k), dict) and overlay.get(k)
    ]
    if declared:
        print("## declares\n")
        print("_Operational sections (capture/draft pathways), not normalizer fields:_\n")
        for k in declared:
            print(f"- `{k}`")
        print()

    print("## normalization.guidance\n")
    print(
        "_The tactical guidance to apply when normalizing a record from this origin — "
        "read it here rather than opening the yaml._\n"
    )
    guid = _guidance(overlay)
    print(guid if guid else "_(no `normalization.guidance` declared)_")
    print()
    return 0


def _origin_relpath(corpus_root, oid: str) -> str:
    """Athenaeum's flat `origin/<id>.yaml`, falling back to the back-compat `web/`/`otherwise/`."""
    base = corpus_root / "schema" / "origin"
    for sub in ("", "web", "otherwise"):
        cand = (base / sub / f"{oid}.yaml") if sub else (base / f"{oid}.yaml")
        if cand.is_file():
            return str(cand.relative_to(corpus_root))
    return f"schema/origin/{oid}.yaml"


def _guidance(schema: dict[str, Any] | None) -> str:
    if not isinstance(schema, dict):
        return ""
    norm = schema.get("normalization")
    return str(norm.get("guidance") or "").strip() if isinstance(norm, dict) else ""
