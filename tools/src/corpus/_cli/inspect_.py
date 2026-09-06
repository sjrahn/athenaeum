"""`corpus inspect <hash-or-prefix-or-path>` — the one-stop card for an agent that comes
across a bare blake3: identity, artifact, origins, addressable axes, and the resolver ops
its mime supports.

That knowledge is otherwise scattered: `show` covers origins/state, `diagnose` covers
artifact/lint, `toc` dumps raw per-segment detail, and the resolver's transform registry is
only discoverable via a failed `corpus resolve` (an error naming what it ISN'T). This is the
read-only, terse, agent-readable card that puts identity + artifact + origins + content axes
+ resolver ops on one screen. Every section prints honestly when empty — never omitted
silently, so an agent can trust an absent line means "checked, nothing there."

Read-only: never writes, never touches cache, never hydrates. Parses tolerantly — a
malformed section degrades to a `(parse error: ...)` note rather than crashing the card.
"""

from __future__ import annotations

import argparse

from corpus import derived_views, paths, records, resolver, segments, shape
from corpus import mime as _mime
from corpus._cli._common import add_corpus_root_arg, human_bytes, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)

    print(f"corpus inspect {record_id[:12]}\n")
    _print_identity(root, record_id, post)
    _print_artifact(root, record_id, post)
    _print_origins(root, post)
    _print_content_axes(post)
    _print_resolver_ops(root, post)
    return 0


# ---------- 1. identity ---------- #


def _print_identity(root, record_id, post) -> None:
    print("== identity ==")
    print(f"record:      {record_id}")
    print(f"state:       {records.derived_state(post, root)}")

    try:
        resolved_gov = shape.governing_form(post, root)
    except Exception as e:
        print(f"governing:   (parse error: {e})")
    else:
        if resolved_gov is None:
            print("governing:   none — no contract governs this record (genuinely formless)")
        else:
            form_id, is_terminal = resolved_gov
            contract_kind = "terminal contract" if is_terminal else "rendering contract"
            source = ""
            try:
                declared = shape.form_for_record(post, root)
            except Exception:
                declared = None
            if declared is not None and declared[1] == form_id:
                source = f"  (declared: origin '{declared[0]}')"
            print(f"governing:   {form_id} — {contract_kind}{source}")

    print(f"citable:     {_citability_line(root, post)}")

    title_field = records.derived_editorial_field(post, root, "title")
    desc_field = records.derived_editorial_field(post, root, "description")
    print(f"title:       {title_field.value or '(none)'}  (layer: {title_field.layer or 'none'})")
    desc_display = desc_field.value[:200] or "(none)"
    print(f"description: {desc_display}  (layer: {desc_field.layer or 'none'})")
    print()


def _iter_content_blocks(post) -> list:
    """Parse the content zone into blocks (shared by the citability line and the content
    axes section) — raises on malformed grammar; callers degrade as they see fit."""
    return segments.iter_blocks(post.content or "")


def _persisted_segment_count(blocks: list) -> int:
    return sum(len(b.segments) if isinstance(b, segments.Section) else 1 for b in blocks)


def _citability_line(root, post) -> str:
    """The record's honest citability (§7.1 `citation_surface:`, ledger.md §6.3/§13.2):
    a `segments`-class record (HTML by built-in default — presentation soup, not honest
    line-of-sight content) is citable only once persisted segments exist; a `raw`-class
    record's derived body IS faithful content, so record-wide quotes are honest even with
    zero persisted segments."""
    media_type = records.media_type_for(post)
    if not media_type:
        return "n/a — no <!--artifact--> block"

    surface = _mime.citation_surface(media_type, root)
    try:
        seg_count = _persisted_segment_count(_iter_content_blocks(post))
    except Exception:
        seg_count = 0

    if surface == "segments":
        if seg_count == 0:
            return "no — segments required, none persisted (enqueue for normalize; ledger.md §13.2)"
        return f"yes (segments: {seg_count})"

    base = "yes (raw surface — record-wide quotes are honest"
    return f"{base}; segments: {seg_count})" if seg_count > 0 else f"{base})"


# ---------- 2. artifact ---------- #


def _print_artifact(root, record_id, post) -> None:
    print("== artifact ==")
    media_type = records.media_type_for(post)
    if not media_type:
        print("mime:        none — no <!--artifact--> block")
        print()
        return
    print(f"mime:        {media_type}")
    try:
        ext = _mime.extension_for(media_type)
    except Exception:
        ext = ""
    if not ext or ext == "bin":
        print(f"store:       n/a — no known extension for mime {media_type!r}")
        print()
        return
    expected = paths.artifact_path(root, record_id, ext)
    local = expected.is_file()
    print(f"expected:    {expected.relative_to(root)}")
    if local:
        size = expected.stat().st_size
        print(f"local:       present ({human_bytes(size)})")
    else:
        print(f"local:       MISSING — run: corpus store fetch {record_id[:12]}")
    print()


# ---------- 3. origins ---------- #


def _print_origins(root, post) -> None:
    origins = list(records.iter_origin_blocks(post))
    print(f"== origins ({len(origins)}) ==")
    if not origins:
        print("none")
    for ob in origins:
        oid = ob.get("id") or "(bare)"
        if ob.get("id") and ob.get("subtype"):
            oid = f"{ob['id']}/{ob['subtype']}"
        uri = (ob.get("fields") or {}).get("uri")
        snap = (ob.get("fields") or {}).get("snapshot")
        print(f"  [{oid}] {uri}  snapshot={snap}")
        _print_sidecar_lift(root, ob)
    print()


def _short(value) -> str:
    text = str(value)
    return text if len(text) <= 48 else text[:45] + "…"


def _print_sidecar_lift(root, origin_block) -> None:
    """*(v41, §7.2)* The container-member sidecar lift on a qualified origin block: the
    declaration its `<id>/<subtype>` ladder resolves to names the prefix, so the lifted
    fields and the sibling references can be told apart from the block's other fields
    without knowing what any of them mean. Silent for a block whose ladder declares no
    `sidecar:`; a malformed declaration is printed, never swallowed."""
    from corpus import sidecar as _sidecar

    if not origin_block.get("id"):
        return
    try:
        decl = _sidecar.resolve_declaration(
            root, str(origin_block["id"]), origin_block.get("subtype") or None
        )
    except _sidecar.DeclarationError as e:
        print(f"    sidecar:     (declaration error: {e})")
        return
    if decl is None or not decl.prefix:
        return
    fields = origin_block.get("fields") or {}
    refs = decl.reference_names()
    lifted = [(k, v) for k, v in fields.items() if str(k).startswith(decl.prefix) and k not in refs]
    referenced = [(k, v) for k, v in fields.items() if k in refs]
    print(
        f"    lifted ({decl.prefix}*, {len(lifted)}): "
        + (", ".join(f"{k}={_short(v)}" for k, v in lifted) or "none")
    )
    print(
        f"    references ({len(referenced)}): "
        + (", ".join(f"{k}={_short(v)}" for k, v in referenced) or "none")
    )


# ---------- 4. content axes ---------- #


def _print_content_axes(post) -> None:
    """Print the content-zone summary: section/segment counts, the compressed per-axis
    addressing summary, and the embed (container-member) count."""
    print("== content axes ==")
    try:
        blocks = _iter_content_blocks(post)
    except Exception as e:
        print(f"(parse error: {e})")
        print()
        return

    seg_count = _persisted_segment_count(blocks)
    section_count = sum(1 for b in blocks if isinstance(b, segments.Section))
    print(f"sections:    {section_count} section(s), {seg_count} segment(s)")

    axis_lines = _axis_summary(blocks)
    print(f"axes:        {' · '.join(axis_lines) if axis_lines else 'none'}")

    embeds = list(records.iter_embed_blocks(post))
    if embeds:
        print(f"embeds:      {len(embeds)} (container)")
    else:
        print("embeds:      none")

    bands = derived_views.swept_bands(post)
    if bands:
        parts = [
            f"{kind} ({', '.join(a or 'whole transport' for a in addrs)})"
            for kind, addrs in sorted(bands.items())
        ]
        print(f"sweeps:      {' · '.join(parts)}")
    else:
        print("sweeps:      none (sparse — spec §4.3.3.6)")
    print()


def _axis_summary(blocks: list) -> list[str]:
    """One compressed entry per addressable segment axis (`turn=1-1846 (1846 segments)`,
    `att sparse (12)`) — dense (contiguous, one point per integer in range) renders as a
    range; anything else (gaps, or a repeated/compound value) renders as `sparse (<n>)`."""
    per_axis: dict[str, list[tuple[int, int]]] = {}
    for seg in segments.leaf_segments(blocks):
        for axis, lo, hi in segments.address_axis_spans(seg.address):
            per_axis.setdefault(axis, []).append((lo, hi))

    lines: list[str] = []
    for axis in sorted(per_axis):
        spans = per_axis[axis]
        count = len(spans)
        lo_all = min(s[0] for s in spans)
        hi_all = max(s[1] for s in spans)
        dense = count == (hi_all - lo_all + 1) and all(lo == hi for lo, hi in spans)
        if dense:
            rng = f"{lo_all}" if lo_all == hi_all else f"{lo_all}-{hi_all}"
            noun = "segment" if count == 1 else "segments"
            lines.append(f"{axis}={rng} ({count} {noun})")
        else:
            lines.append(f"{axis} sparse ({count})")
    return lines


# ---------- 5. resolver ops ---------- #


def _print_resolver_ops(root, post) -> None:
    print("== resolver ops ==")
    media_type = records.media_type_for(post)

    # Record-level derivation ops (spec §6.2) — `body`/`members`/`turn=` are fixed,
    # universal ops the resolver handles BEFORE any mime-pipeline dispatch (`resolver.py`'s
    # `_resolve_body`/`_resolve_members`/`_resolve_turn`); they're not entries in
    # `transforms.REGISTRY`, so `ops_for_media_type` can't (and shouldn't) surface them —
    # named directly here instead, per spec §6.2's fixed table.
    record_level: list[str] = []
    if media_type:
        record_level.append("body -> markdown [reading]")
        embed_count = len(list(records.iter_embed_blocks(post)))
        record_level.append(f"members -> json ({embed_count} embed(s)) [reading]")
    try:
        declared = shape.form_for_record(post, root)
    except Exception:
        declared = None
    if declared is not None:
        _origin_id, form_id, mapping = declared
        # The turn= unit op needs the mapping's unit grammar (`units.unit_array` reads
        # `messages`/per-unit field paths from it) — a bare `form: {id}` declaration with no
        # mapping (contact-card) addresses by its own segment axes, and `?turn=` would fail.
        if mapping:
            # turn=/att= are RECORD-LEVEL ops (`resolver._resolve_turn`) that bypass
            # `transforms.REGISTRY` entirely, so they're not `ops_for_media_type`-reachable —
            # named directly here, same as `body`/`members` above; the pin comes off the same
            # `engine_version_for_param` lookup `ops_for_media_type` uses for a registry op, so
            # it can never drift from what `resolve()` actually keys on (spec §6.4).
            turn_engine = resolver.engine_version_for_param("turn")
            engine_suffix = f" [engine: {turn_engine}]" if turn_engine else ""
            record_level.append(f"turn=<N> -> json  (form: {form_id}){engine_suffix} [address]")
            record_level.append(
                f"turn=<N>&att=<M> -> bytes  (lineage-chained){engine_suffix} [address]"
            )
    print("  record-level: " + (" · ".join(record_level) if record_level else "none"))

    if not media_type:
        print("  mime pipeline: n/a — no <!--artifact--> block")
        print()
        return

    ops = resolver.ops_for_media_type(root, media_type)
    if not ops:
        print(
            f"  mime pipeline: none registered for media_type {media_type!r} "
            f"(no `working_kind:` declared on its mime schema, and no built-in fallback)"
        )
        print()
        return

    initial_kind = resolver.working_kind_for(root, media_type)
    print(f"  mime pipeline (initial kind: {initial_kind}):")
    by_kind: dict[str, list] = {}
    for op in ops:
        by_kind.setdefault(op.from_kind, []).append(op)
    for kind, kind_ops in by_kind.items():
        parts = []
        for op in kind_ops:
            engine = f" [engine: {op.engine_version}]" if op.engine_version else ""
            # The op's class is its PLACE (spec §6.2 op classes): address/reading may be
            # stored (address) or cited (both); view/instrument/engine are tools — never
            # an anchor, never a stored address.
            parts.append(f"{op.param}= -> {op.output_kind}{engine} [{op.op_class}]")
        print(f"    from {kind}: " + " · ".join(parts))
    print(
        "  op classes: address = names a place (storable, citable) · reading = the place's "
        "text (citable) · view / instrument / engine = tools, never anchors (spec §6.2)"
    )

    if initial_kind in ("zip", "tar"):
        print(
            "  note: a `path=<member>` extracted from a kept-whole archive re-chains into "
            "the member's own sniffed-mime pipeline when a further param follows (spec §6.2 "
            "'Member re-chaining'); a TERMINAL path= serves the member's raw bytes (decoded "
            "text for an already-textual JSON/text member)."
        )
    print()
