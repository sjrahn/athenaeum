"""Find the tightest §6.1.1 element path whose text contains a snippet.

The re-addressing question for every held record is the same: this segment transcribes
THIS prose — which element is exactly that prose? Legacy could only pin it between two
landmarks; 3.6 addresses every element, so the element exists. Deepest match wins, and
the text-length ratio says whether the element is the region or merely contains it.
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from corpus import containment, paths, records
from corpus import mime as mime_mod
from corpus.transforms.html import element_path, path_root


def norm(s): return re.sub(r"\s+", " ", s).strip()

root, target, snippet = Path(sys.argv[1]), sys.argv[2], norm(sys.argv[3])
rid, rf = paths.resolve_record(root, target)
post = records.load(rf)
mt = records.media_type_for(post)
binary = containment.ensure_local_bytes(root, rid, mime_mod.extension_for(mt))
soup = BeautifulSoup(binary.read_bytes(), "html.parser")
proot = path_root(soup)

hits = []
for tag in soup.find_all(True):
    if not isinstance(tag, Tag):
        continue
    text = norm(tag.get_text())
    if snippet in text:
        p = element_path(tag, proot)
        if p:
            hits.append((len(p.split(".")), len(text), p, tag.name, text))
if not hits:
    print("no element contains that snippet")
    sys.exit(1)
hits.sort(key=lambda h: (-h[0], h[1]))
for depth, tlen, p, name, text in hits[:6]:
    print(f"  el={p:<34} <{name}> depth={depth} textlen={tlen}")
    print(f"      {text[:150]}")
