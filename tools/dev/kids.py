"""List the element children of a §6.1.1 path with their index and text preview."""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from corpus import containment, paths, records
from corpus import functional_uri as furi
from corpus import mime as mime_mod
from corpus.transforms.html import iter_element_children, path_root, resolve_element_path


def norm(s): return re.sub(r"\s+", " ", s).strip()

root, target, path = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lo = int(sys.argv[4]) if len(sys.argv) > 4 else 1
hi = int(sys.argv[5]) if len(sys.argv) > 5 else 10**9
rid, rf = paths.resolve_record(root, target)
post = records.load(rf)
mt = records.media_type_for(post)
binary = containment.ensure_local_bytes(root, rid, mime_mod.extension_for(mt))
soup = BeautifulSoup(binary.read_bytes(), "html.parser")
node = resolve_element_path(path_root(soup), furi.parse_el_path(path))
kids = iter_element_children(node)
print(f"{path} <{node.name}> has {len(kids)} element children")
for i, k in enumerate(kids, start=1):
    if not (lo <= i <= hi):
        continue
    t = norm(k.get_text())
    img = " [IMG]" if k.name == "img" or k.find("img") else ""
    print(f"  {i:>4} <{k.name}>{img} {t[:110]}")
