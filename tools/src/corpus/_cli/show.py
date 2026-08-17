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
    print(f"state:       {records.derived_state(post, root)}")
    print(f"title:       {title_field.value}  (layer: {title_field.layer or 'none'})")
    print(f"description: {desc_field.value[:200]}  (layer: {desc_field.layer or 'none'})")
    print(f"mime:        {records.media_type_for(post)}")
    hash_value = post.metadata.get("hash")
    if hash_value:
        print(f"hash:        {hash_value}")
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

    blocks = segments.iter_blocks(post.content or "")

    members = list(records.iter_members(post))
    if members:
        # Whether the body PLACES a member is the fact a reader wants from this listing — an
        # unplaced member is an asset the record declares and does not show. Same reference
        # semantics as lint's `embed-unreferenced`: segment addresses plus the chain closure,
        # so a crop at `el=3&bbox=…` counts as placing `el=3`.
        placed: set[str] = set()
        for blk in blocks:
            children = blk.segments if isinstance(blk, segments.Section) else [blk]
            for seg in children:
                raw = getattr(seg, "address", None)
                for addr in (raw if isinstance(raw, list) else [raw] if raw else []):
                    placed.add(str(addr))
                    if "&" in str(addr):
                        placed.add(str(addr).split("&", 1)[0])

        def _addrs(raw):
            return [str(a) for a in (raw if isinstance(raw, list) else [raw]) if a]

        unplaced = [m for m in members if not any(a in placed for a in _addrs(m.get("address")))]
        total_bytes = sum(int((m.get("fields") or {}).get("bytes") or 0) for m in members)
        # A record with no content zone is a container: the roster IS the content (§7.8
        # `form/manifest`), so there is nothing for a member to be "unplaced" relative to —
        # which is why lint's `embed-unreferenced` skips these records too.
        is_roster_as_content = not blocks
        if is_roster_as_content:
            summary = "the roster is the content"
        else:
            summary = f"{len(members) - len(unplaced)} placed, {len(unplaced)} unplaced"
        if total_bytes:
            summary += f", {total_bytes:,} bytes"
        print(f"\nmembers ({len(members)}): {summary}")
        for em in members:
            size = (em.get("fields") or {}).get("bytes")
            where = (
                "member  " if is_roster_as_content
                else "placed  " if em not in unplaced
                else "UNPLACED"
            )
            print(
                f"  [{where}] {em.get('media_type')}  address={em.get('address')}  "
                f"transport={em.get('transport')}"
                + (f"  bytes={int(size):,}" if size is not None else "")
            )

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
