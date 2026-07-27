"""For one held record: print every el= address and what §6.1.1 maps it to."""
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from corpus import containment, paths, records, segments
from corpus import mime as mime_mod
from corpus.remap_el import RemapHold, map_el_value
from corpus.transforms.html import legacy_is_addressable, path_root

root, target = Path(sys.argv[1]), sys.argv[2]
rid, rf = paths.resolve_record(root, target)
post = records.load(rf)
mt = records.media_type_for(post)
binary = containment.ensure_local_bytes(root, rid, mime_mod.extension_for(mt))
soup = BeautifulSoup(binary.read_bytes(), "html.parser")
elements = [t for t in soup.find_all(legacy_is_addressable) if isinstance(t, Tag)]
proot = path_root(soup)
print(f"{rid[:12]}  mime={mt}  legacy elements={len(elements)}")

seen = {}
for blk in segments.iter_blocks(post.content or ""):
    rows = [("section", blk)] + [("seg", s) for s in getattr(blk, "segments", [])]
    for kind, b in rows:
        addr = getattr(b, "address", None)
        if not addr or not str(addr).startswith("el="):
            continue
        val = str(addr)[3:]
        try:
            new, form = map_el_value(val, elements, proot)
        except RemapHold as e:
            new, form = f"HOLD({e})", "-"
        label = getattr(b, "entry", None) or getattr(b, "atom", None) or ""
        tag = ""
        if isinstance(new, str) and new in seen:
            tag = f"   <<< COLLIDES with {seen[new]}"
        elif isinstance(new, str):
            seen[new] = f"{kind} el={val}"
        print(f"  {kind:8} el={val:<12} → {new!s:<28} [{form}] {str(label)[:38]}{tag}")
