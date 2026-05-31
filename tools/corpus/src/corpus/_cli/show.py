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

    print(f"id:          {record_id}")
    print(f"status:      {post.metadata.get('status')}")
    print(f"description: {(post.metadata.get('description') or '').strip()[:200]}")
    print(f"mime:        {records.media_type_for(post)}")
    print(f"title:       {records.title_for(post)}")
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
        print(f"\nclassifies ({len(classifies)}):")
        for cb in classifies:
            ns = cb.get("namespace")
            cid = cb.get("id")
            sub = cb.get("subtype") or ""
            print(f"  {ns}/{cid}{('/' + sub) if sub else ''}")

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

    issues = list(records.iter_issue_blocks(post))
    if issues:
        print(f"\nissues ({len(issues)}):")
        for iss in issues:
            fields = iss.get("fields") or {}
            print(
                f"  [{iss.get('id')}]  severity={fields.get('severity')}  "
                f"resolution={fields.get('resolution')}"
            )

    derived = records.derived_classifications(post)
    if derived:
        print(f"\nderived classifications ({len(derived)}):")
        for d in derived:
            print(f"  - {d}")

    return 0
