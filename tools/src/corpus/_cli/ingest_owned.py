"""Ingest a capture/ file ONLY under an owner-sourced origin the instance opens to consumers.

The consumer ingest lane (spec/athenaeum.md §2.3 `consumer_ingest:`, spec/corpus.md §12.3,
v49): the one mutating corpus verb a consumer's permission list can allow outright. It takes
no origin argument. The allowed origin ids come from the instance config
(`consumer_ingest: {origins: [...]}` in `athenaeum.yaml`), which the resident sets and a
consumer cannot edit. Before ANYTHING is read into the store, or the staged bytes are
touched, it refuses unless:

- the instance opens a lane at all;
- the staged file's `<file>.capture.yaml` sidecar DECLARES an origin (`origin_schema:`) that
  the lane lists and that resolves to an overlay;
- that origin is uri-less: a producer-declared local-file origin. A retrieval origin (a
  sidecar `source_url`, a SingleFile banner) is the web lane's (`corpus capture`), where host
  overlays apply;
- every field the overlay marks `required` is declared (`origin_fields:`) — the provenance
  is the point.

It then ingests exactly as `corpus ingest` does (identity, dedup, derived hashes, sidecar
cleanup). If the bytes are already in the corpus, the declared owner-sourced origin block is
appended to the existing record, as any re-encounter does. It never touches the ledger.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, help="Path to a file in capture/ with its "
                                                "<file>.capture.yaml sidecar")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import paths

    src = args.file.resolve()
    if not src.is_file():
        sys.exit(f"not a file: {src}")
    try:
        corpus_root = resolved_corpus_root(args)
    except SystemExit:
        try:
            corpus_root = paths.find_corpus_root(src.parent)
        except FileNotFoundError as e:
            sys.exit(str(e))
    refusal = refuse(corpus_root, src)
    if refusal:
        sys.exit(f"ingest-owned: refused — {refusal}. Nothing was written.")
    from corpus._cli import ingest

    return ingest._ingest_one(corpus_root, src)


def refuse(corpus_root: Path, src: Path) -> str | None:
    """Why the lane refuses `src`, or None when it may ingest. Read-only."""
    from corpus import consumer_lane, mime, schemas
    from corpus._cli import ingest

    try:
        allowed = consumer_lane.load_consumer_origins(corpus_root)
    except consumer_lane.ConsumerLaneError as e:
        return str(e)
    if not allowed:
        return ("this instance opens no consumer ingest lane (athenaeum.yaml "
                "`consumer_ingest: {origins: [...]}`)")
    sidecar = ingest._read_sidecar(src)
    schema_id = str(sidecar.get("origin_schema") or "").strip()
    if not schema_id:
        return (f"{src.name} declares no origin (its .capture.yaml sidecar has no "
                "`origin_schema:`) — the lane ingests only a declared owner-sourced origin")
    if schema_id not in allowed:
        return (f"origin {schema_id!r} is not one the lane opens "
                f"({', '.join(sorted(allowed))})")
    overlay = schemas.load_origin_overlay_by_id(corpus_root, schema_id)
    if overlay is None:
        return f"origin {schema_id!r} resolves to no overlay (schema/origin/{schema_id}.yaml)"
    uri, _at, fields, _schema = ingest._derive_capture_origin(
        src, sidecar, mime.detect(src, corpus_root)
    )
    if uri:
        return (f"{src.name} carries a retrieval origin ({uri}) — a web page goes through "
                "`corpus capture`, where its host overlay applies")
    declared = fields
    ext = overlay.get("extended_fields") or {}
    missing = sorted(
        name for name, spec in ext.items()
        if isinstance(spec, dict) and spec.get("required") and declared.get(name) in (None, "")
    )
    if missing:
        return (f"origin {schema_id!r} requires {', '.join(missing)} — declare them under the "
                "sidecar's `origin_fields:`")
    return None
