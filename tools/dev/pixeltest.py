"""Is a segment at a member's address a TRANSCRIPTION of it, or prose that borrowed it?

The two look identical in the record — a text segment sitting at an `<img>`'s address — and
they want opposite repairs. The artifact separates them in one question: **is this text in
the DOM?**

  not in the DOM anywhere   → read off the pixels. A transcription; if its marker is missing
                              the marker belongs back (#73).
  in the addressed ELEMENT  → correctly addressed and faithful. The member is not always an
                              `<img>` — an `<a href="data:…">` attachment carrier has its own
                              text, and transcribing it is right.
  in the DOM but NOT in the
  addressed element         → page prose that took the member's address because the legacy
                              `el=` enumeration gave it no spelling of its own. A mis-address;
                              the repair is a §6.1.1 sibling range over its real slots.

Two ways this test lied while it was being written, both worth keeping in mind:
  * Tokenize BOTH sides the same way. Filtering short words out of the segment body but not
    out of the DOM text made every alldata procedure record read as a transcription.
  * Check the addressed element before the document. Without it, faithful transcription of an
    element's own text is indistinguishable from prose that borrowed the address.

  python tools/dev/pixeltest.py <corpus-root> [record…]      # default: the whole hub
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from corpus import containment, paths, records, segments
from corpus import functional_uri as furi
from corpus import mime as mime_mod
from corpus.transforms.html import path_root, resolve_element_path


def toks(s: str) -> list[str]:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return [w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if len(w) > 3]


def addr_strings(addr):
    if isinstance(addr, list):
        return [a for a in addr if isinstance(a, str)]
    return [addr] if isinstance(addr, str) else []


root = Path(sys.argv[1])
targets = sys.argv[2:]
paths_iter = (
    [paths.resolve_record(root, t)[1] for t in targets]
    if targets
    else records.iter_record_paths(root)
)

for rf in paths_iter:
    post = records.load(rf)
    member_addrs = {a for m in records.iter_members(post) for a in addr_strings(m.get("address"))}
    if not member_addrs:
        continue
    segs = [s for s in segments.leaf_segments(segments.iter_blocks(post.content))
            if not s.is_structural and s.atom == "text"]
    hits = [(a, s) for s in segs for a in addr_strings(s.address) if a in member_addrs]
    if not hits:
        continue
    try:
        binary = containment.ensure_local_bytes(
            root, rf.stem, mime_mod.extension_for(records.media_type_for(post))
        )
        soup = BeautifulSoup(binary.read_bytes(), "html.parser")
        proot = path_root(soup)
        doc = " ".join(toks(soup.get_text(" ")))
    except Exception as exc:
        print(f"{rf.stem[:12]}  ARTIFACT UNAVAILABLE: {exc}")
        continue
    stamped = bool(records.el_addressing(post))
    for a, s in hits:
        inner = ""
        axis, _, value = a.split("&", 1)[0].partition("=")
        if stamped and axis == "el":
            try:
                node = resolve_element_path(
                    proot, furi.ElPath(furi.parse_el_path(value).components)
                )
                inner = " ".join(toks(node.get_text(" ")))
            except Exception:
                inner = ""
        w = toks(s.body)
        wins = [" ".join(w[i:i + 5]) for i in range(0, max(1, len(w) - 4), 5)]
        own = sum(1 for x in wins if x in inner)
        hit = sum(1 for x in wins if x in doc)
        if wins and own * 2 >= len(wins):
            verdict = "own-text (faithful)"
        elif wins and hit * 2 >= len(wins):
            verdict = "BORROWED (re-address)"
        else:
            verdict = "transcription"
        sid = getattr(s, "overlay", None) or s.atom
        print(
            f"{rf.stem[:12]}  {a:<34} {sid:<16} "
            f"elem {own:>3}/{len(wins):<3} doc {hit:>3}/{len(wins):<3}  {verdict}"
        )
