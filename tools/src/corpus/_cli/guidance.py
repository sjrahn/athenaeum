"""Print the normalization guidance that applies to a record — deterministically.

`corpus guidance <hash>` resolves a record, reads its `<!--artifact-->` MIME and its qualified
`<!--origin-->` overlays, and prints, for each, the schema file path plus that schema's
`normalization.guidance` prose. So the normalizer never has to guess a schema filename or walk
`schema/` by hand — schema yaml stays a library implementation detail.

For one overlay's field-spec + guidance in isolation use `corpus overlay <id>`. Markdown to
stdout.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from corpus import paths, records, schemas
from corpus import queue as _queue
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("hash", help="record id or unambiguous prefix.")
    parser.add_argument(
        "--mime-only",
        action="store_true",
        help="print only the mime-schema guidance (skip applied origin overlays).",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    record_id, path = paths.resolve_record(corpus_root, args.hash)
    post = records.load(path)
    mime = records.media_type_for(post)

    print(f"# guidance for {record_id[:12]}…  (mime: {mime or '?'})")
    print()

    _print_enqueue_hint(corpus_root, record_id)

    stem = schemas.mime_schema_id_for(corpus_root, mime) if mime else None
    if stem is None:
        print(f"## mime schema\n\n_No mime schema declares `{mime}`._\n")
    else:
        schema = schemas.load_mime_schema(corpus_root, mime) or {}
        _print_guidance_block("mime schema", f"schema/mime/{stem}.yaml", schema)

    if args.mime_only:
        return 0

    origins = [b for b in records.iter_origin_blocks(post) if b.get("id")]
    if origins:
        print("## applied origin overlays\n")
        for blk in origins:
            oid = str(blk.get("id"))
            ov = schemas.load_origin_overlay_by_id(corpus_root, oid) or {}
            _print_guidance_block(f"origin {oid}", _origin_overlay_relpath(corpus_root, oid), ov, level=3)

    return 0


def _print_enqueue_hint(corpus_root: Path, record_id: str) -> None:
    """Surface a live queue entry's requester hint (§8.5, 3.3) — the proposes/disposes
    seam: a reader may propose what a record looks like without authoring anything; the
    normalizer disposes against the bytes. Printed only when a pending or claimed queue
    entry for this record actually carries a hint; omitted entirely otherwise (no empty
    section), since most records have no live entry at all."""
    st = _queue.state(corpus_root, record_id)
    hint = st.get("hint")
    if st.get("state") not in ("requested", "claimed") or not hint:
        return
    print("## enqueue hint\n")
    print(f"_requester context ({st['state']}) — a proposal, not an assertion:_\n")
    print(hint)
    print()


def _guidance_text(schema: dict[str, Any]) -> str:
    norm = schema.get("normalization") if isinstance(schema, dict) else None
    return str(norm.get("guidance") or "").strip() if isinstance(norm, dict) else ""


def _print_guidance_block(label: str, relpath: str, schema: dict[str, Any], *, level: int = 2) -> None:
    print(f"{'#' * level} {label}\n")
    print(f"_source: `{relpath}`_\n")
    text = _guidance_text(schema)
    print(text if text else "_(no `normalization.guidance` declared)_")
    print()


def _origin_overlay_relpath(corpus_root: Path, oid: str) -> str:
    """Athenaeum's flat `origin/<id>.yaml`, falling back to the back-compat `web/`/`otherwise/`."""
    base = corpus_root / "schema" / "origin"
    for sub in ("", "web", "otherwise"):
        cand = (base / sub / f"{oid}.yaml") if sub else (base / f"{oid}.yaml")
        if cand.is_file():
            return str(cand.relative_to(corpus_root))
    return f"schema/origin/{oid}.yaml"
