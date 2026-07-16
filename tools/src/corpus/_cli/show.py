"""Compact record summary."""

from __future__ import annotations

import argparse

from corpus import paths, records, segments
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)

    title_field = records.derived_editorial_field(post, root, "title")
    desc_field = records.derived_editorial_field(post, root, "description")
    print(f"id:          {record_id}")
    print(f"state:       {records.derived_state(post)}")
    print(f"title:       {title_field.value}  (layer: {title_field.layer or 'none'})")
    print(f"description: {desc_field.value[:200]}  (layer: {desc_field.layer or 'none'})")
    print(f"mime:        {records.media_type_for(post)}")
    transport = post.metadata.get("transport")
    if transport:
        print(f"transport:   {transport}")
    canonical = post.metadata.get("canonical")
    if canonical:
        print(f"canonical:   {canonical}")
    touch = post.metadata.get("touch")
    if isinstance(touch, list):
        print(f"touch[{len(touch)}]:")
        for t in touch:
            print(f"  - {t}")
    else:
        print(f"touch:       {touch}")

    origins = list(records.iter_origin_blocks(post))
    print(f"\norigins ({len(origins)}):")
    for ob in origins:
        oid = ob.get("id") or "(bare)"
        uri = (ob.get("fields") or {}).get("uri")
        snap = (ob.get("fields") or {}).get("snapshot")
        print(f"  [{oid}] {uri}  snapshot={snap}")

    classifies = list(records.iter_classify_blocks(post))
    if classifies:
        print(f"\nclassifies ({len(classifies)}): LEGACY — retired in ATH-CORPUS 2.0; see `corpus lint`")

    embeds = list(records.iter_embed_blocks(post))
    if embeds:
        print(f"\nembeds ({len(embeds)}):")
        for em in embeds:
            print(
                f"  {em.get('media_type')}  address={em.get('address')}  "
                f"transport={em.get('transport')}"
            )

    blocks = segments.iter_blocks(post.content or "")
    seg_count = sum(
        len(b.segments) if isinstance(b, segments.Section) else 1 for b in blocks
    )
    section_count = sum(1 for b in blocks if isinstance(b, segments.Section))
    print(f"\ncontent: {section_count} section(s), {seg_count} segment(s)")

    contexts = list(records.iter_context_blocks(post))
    if contexts:
        print(f"\ncontext ({len(contexts)}):")
        for ctx in contexts:
            ns = ctx.get("namespace") or ""
            cid = ctx.get("id") or ""
            label = cid if cid == ns else f"{ns}/{cid}"
            if ctx.get("subtype"):
                label += f"/{ctx['subtype']}"
            fields = ctx.get("fields") or {}
            if ns == "issue":
                detail = f"severity={fields.get('severity')}  resolution={fields.get('resolution')}"
            elif ns == "reference":
                rung = fields.get("source_uri") or fields.get("source_url") or fields.get("attribution_text")
                detail = f"→ {rung}" if rung else ""
            else:
                detail = ""
            addr = fields.get("address")
            if addr:
                detail = (detail + "  " if detail else "") + f"@{addr}"
            print(f"  [{label}]  {detail}".rstrip())

    derived = records.derived_classifications(post)
    if derived:
        print(f"\nderived classifications ({len(derived)}):")
        for d in derived:
            print(f"  - {d}")

    return 0
