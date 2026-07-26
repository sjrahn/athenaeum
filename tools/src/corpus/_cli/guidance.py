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

from corpus import paths, records, schemas, segments, shape
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

    _print_form_contract(corpus_root, post)

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


def _print_form_contract(corpus_root: Path, post: Any) -> None:
    """The record's GOVERNING RENDERING CONTRACT, printed FIRST — its definition, its normal
    form, the checks lint will run, and its authoring guidance.

    This section exists because the form overlay is where a shape's real authoring law now
    lives (spec §7.8), and `guidance` is the one command the normalize pass is told to
    consult. Printing only mime + origin left that law reachable solely by hand-reading a
    schema yaml — which the pass is told never to do, so in practice a form's decomposition
    and checks were invisible to the worker they govern.

    Sections the pass carries anyway are also surfaced, so a span-scope form (one section
    per sheet, per statement) is not missed just because the whole-record slot is empty."""
    governing = shape.governing_form(post, corpus_root)
    asserted = sorted({
        b.form for b in segments.iter_blocks(post.content or "")
        if isinstance(b, segments.Section) and b.form
    })
    ids = [governing[0]] if governing else []
    ids += [f for f in asserted if f not in ids]
    if not ids:
        print("## governing contract\n")
        print("_None — this record stands under the zeroth form (formless, spec §7.8). "
              "Nothing prescribes a shape; adopt one only when it is identified or authored._\n")
        return
    for form_id in ids:
        overlay = schemas.load_form_overlay(corpus_root, form_id)
        terminal = bool(governing and governing[0] == form_id and governing[1])
        label = f"governing contract — form/{form_id}" + (" (TERMINAL)" if terminal else "")
        print(f"## {label}\n")
        print(f"_source: `schema/form/{form_id}.yaml` (packaged unless shadowed)_\n")
        if not overlay:
            print(f"_No `form/{form_id}` overlay resolves — coherence cannot be checked._\n")
            continue
        for key, heading in (
            ("description", "what this shape is"),
            ("decomposition", "normal form"),
        ):
            text = str(overlay.get(key) or "").strip()
            if text:
                print(f"### {heading}\n")
                print(text)
                print()
        checks = overlay.get("checks") or {}
        if checks:
            print("### checks lint will run\n")
            for key, value in checks.items():
                print(f"- `{key}`: {value}")
            print()
        text = _guidance_text(overlay)
        if text:
            print("### authoring guidance\n")
            print(text)
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
