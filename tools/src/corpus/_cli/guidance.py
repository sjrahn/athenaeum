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
            _print_regions(corpus_root, oid)
            _print_exemplars(corpus_root, oid)

    return 0


def _print_regions(corpus_root: Path, origin_id: str) -> None:
    """The overlay's declared regions (spec §7.2, 3.8) — what enters the body, what lands in
    the trailing framing span, and what is chrome.

    Printed because the declaration exists to state a host-wide judgment ONCE: a pass that
    cannot see it re-decides per record which index-like regions belong, which is how one
    judgment comes out ten thousand slightly different ways."""
    rows = schemas.origin_regions(corpus_root, origin_id)
    if not rows:
        return
    print("#### declared regions\n")
    print("_The overlay's standing judgment; a region it does not name is omitted._\n")
    print("| role | renders | selector | lifts to |")
    print("| --- | --- | --- | --- |")
    for r in rows:
        print(
            f"| {r['role'] or '—'} | {r['renders']} | `{r['selector']}` "
            f"| {r.get('lifts_to') or '—'} |"
        )
    print()
    # The nesting rule is printed WITH the table, not left to the spec, because reading this
    # table without it is exactly the misreading 3.9 exists to end: an envelope row and a
    # breadcrumb row sit side by side here while in the markup one contains the other.
    print(
        "**These regions nest, and the innermost one wins** (§7.2, 3.9). A byte belongs to "
        "exactly ONE region: the smallest declared region containing it. So a `framing` or "
        "`never` region sitting inside a `subject` envelope is still framing or never — do "
        "not read the outer row as claiming its bytes — and a `subject` envelope inside "
        "another renders its content once, not twice. Containment is a fact about *this "
        "record's artifact*, never about the order of rows above.\n"
    )


def _print_exemplars(corpus_root: Path, origin_id: str) -> None:
    """The overlay's blessed exemplars (spec §7.2, 3.8).

    THIS is the delivery half, and it is the half that is easy to skip. Authoring law the
    command a normalizer runs does not print is law invisible to the worker it governs — the
    standing debt `_cli/atoms.py` names. An exemplar list sitting in a yaml nobody is allowed
    to hand-read would be exactly that.

    Ids and hints only, never the record bodies: an exemplar is a whole record, and inlining
    several would spend the pass's context before it read its own artifact. A stale or
    foreign one is printed WITH ITS FAULT rather than dropped — silently withholding it would
    look identical to an origin that declares none, and the pass would go on unexampled
    without ever learning why."""
    rows = schemas.origin_exemplars(corpus_root, origin_id)
    if not rows:
        return
    print("#### exemplars\n")
    print(
        "_Handcrafted records of this origin, showing shapes this guidance describes. "
        "Read one with `corpus view <id>` or `corpus show <id>`. They show what conformance "
        "LOOKS like; they cannot state a prohibition, so the guidance above still rules._\n"
    )
    for row in rows:
        state, detail = schemas.exemplar_status(corpus_root, origin_id, row)
        mark = "" if state == "ok" else f"  **[{state.upper()}]**"
        where = f" (`{row['address']}`)" if row.get("address") else ""
        print(f"- `{row['record'][:12]}…`{where}{mark} — {row['shows'] or '_no hint given_'}")
        if state != "ok":
            print(f"    - _DO NOT COPY THIS SHAPE: {detail}_")
    print()


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
