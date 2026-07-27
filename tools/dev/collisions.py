"""For each held record: print only the addresses that COLLIDE after mapping, with labels."""
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from corpus import containment, paths, records, segments
from corpus import mime as mime_mod
from corpus.remap_el import RemapHold, map_el_value
from corpus.transforms.html import legacy_is_addressable, path_root

root = Path(sys.argv[1])
for target in sys.argv[2:]:
    rid, rf = paths.resolve_record(root, target)
    post = records.load(rf)
    mt = records.media_type_for(post)
    binary = containment.ensure_local_bytes(root, rid, mime_mod.extension_for(mt))
    soup = BeautifulSoup(binary.read_bytes(), "html.parser")
    elements = [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]
    proot = path_root(soup)
    by_new = {}
    for blk in segments.iter_blocks(post.content or ""):
        for kind, b in [("section", blk)] + [("seg", s) for s in getattr(blk, "segments", [])]:
            for a in segments._iter_addr_strings(getattr(b, "address", None) or ""):
                if not a.startswith("el="):
                    continue
                val = a[3:].split("&")[0].split("/")[0]
                try:
                    new, _ = map_el_value(val, elements, proot)
                except RemapHold:
                    continue
                if isinstance(new, list):
                    continue
                by_new.setdefault(new, []).append(
                    (a, kind, str(getattr(b, "entry", "") or getattr(b, "atom", "") or "")[:52])
                )
    dupes = {k: v for k, v in by_new.items() if len(v) > 1}
    print(f"\n══ {rid[:12]}  elements={len(elements)} collisions={len(dupes)}")
    for new, rows in dupes.items():
        print(f"  → {new}")
        for a, kind, label in rows:
            print(f"      {kind:7} {a:<18} {label}")
