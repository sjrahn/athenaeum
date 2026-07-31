"""#52 acceptance check — would a normalize pass over the queued alldata records come out right?

The sweep is 1,470 records. Its cost is not the problem (8.5 MB of drafted body, p50 3.2 KB);
what is unproven is whether ONE pass produces the target shape. The arc's standing lesson is
that guidance saying a thing is not evidence the fleet does it — the html schema has carried
"keep `<a href>` as `[text](url)`" since 43598b0 (2026-05-31), which is before every one of
the records #118 says were flattened.

So: four checks, one per defect a 1,470-record sweep would otherwise repeat 1,470 times.

  links   #118  the source's inline auto-links, flattened out of the body
  crumb   #89   where the page's own framing lives — nowhere / inline / homed in a trailing span
  order   #121  blocks emitted out of the source's presented order
  form    #90   `form/index` adopted over a body that lists nothing

EVERY CHECK VALIDATES ITSELF against a figure the tracker already published, and prints the
comparison. That is not ceremony: my first attempt at the links check reported ~100%
flattening across every normalizer generation, and the record sjrahn originally found the
defect on (`4a03eb5`) turned out to have its link present and 24 body links. An unexpected
extreme is a hypothesis about the detector before it is a fact about the corpus, and a
detector that cannot reproduce a known number has no business gating a fleet run.

The detection RULES here are lifted from the scripts that earned those published numbers
rather than re-derived — `census_via_module.py` for flattening (note `flattened` requires the
anchor TEXT to survive in the body while the link does not: an element that was never placed
at all is not a flattening), and `crumbline.py` for the breadcrumb (>=2 crumb labels chained
in order on one line, with a literal `>` — coverage-fraction tests are fuzzy because the
fleet substitutes the vehicle name for the "Vehicle" crumb).

Usage:
    accept_alldata.py <corpus-root> [--ids FILE] [--json OUT] [--limit N]

`--ids` restricts to a newline-separated id list, which is how a pilot's output gets compared
against the baseline this produces over the already-normalized fleet.
"""

from __future__ import annotations

import argparse
import collections
import html as _html
import json
import re
import sys
from contextlib import suppress
from itertools import pairwise
from pathlib import Path
from typing import Any

from corpus import functional_uri as furi
from corpus import records, schemas, segments
from corpus.regionmap import resolve as resolve_regions

HOST = "my.alldata.com"

ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
TAG = re.compile(r"<[^>]+>")
MDLINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# Anchor texts that are the page's own UI, not the publisher naming a component. Carried
# over verbatim from the census that produced #118's published figure — changing this set
# changes the number, so it is not a place to improvise.
CHROME_TEXT = {"open in new tab", "zoom/print", "click for full-size image", "print"}

# What the tracker already says. A check that cannot land on its own row is not trusted.
PUBLISHED = {
    "links": ("#118 (post-#120 rescope)", 16_883, 2_176),
    "order": ("#121", None, 185),
    "form": ("#90", None, 121),
    "crumb": ("#89 — records carrying a breadcrumb LINE", None, 95),
}


# Entity handling is NOT a detail here — it moves the links figure by ~45%. The census that
# produced #118's published number replaced the literal `&nbsp;` and decoded nothing else, so
# any anchor text carrying `&amp;` / `&#8212;` / `&rsquo;` failed to match the record body
# (which holds decoded characters) and was scored NOT flattened. Decoding is the correct
# comparison; the published figure is therefore an under-count. Both are computed so the
# difference is a stated quantity rather than a silent improvement.
LEGACY_TEXT = False


def plain(fragment: str) -> str:
    stripped = TAG.sub(" ", fragment)
    if LEGACY_TEXT:
        return " ".join(stripped.replace("&nbsp;", " ").split())
    return " ".join(_html.unescape(stripped).replace("\xa0", " ").split())


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def el_paths(address: Any) -> list[furi.ElPath]:
    """Every `el=` path an address names — scalar or list, ignoring other axes."""
    vals = address if isinstance(address, list) else [address]
    out: list[furi.ElPath] = []
    for a in vals:
        if not isinstance(a, str):
            continue
        key, _, value = a.split("&", 1)[0].partition("=")
        if key.strip() != "el" or not value.strip():
            continue
        with suppress(ValueError):  # a legacy/malformed address simply has no el= claim
            out.append(furi.parse_el_path(value.strip()))
    return out


# ---------- check 1: #118, flattened inline auto-links ---------- #


def check_links(html: str, body: str, rmap: Any) -> dict[str, Any]:
    """Anchors inside a SUBJECT region whose text survived into the body but whose link
    did not. `renders_at` implements §7.2's innermost-wins, so a rail link nested inside
    `ad-repair-article` scores as framing (#120's correction) and never lands here."""
    linked = {t for t, _u in MDLINK.findall(body)}
    flattened: list[str] = []
    total_subject = 0
    for m in ANCHOR.finditer(html):
        text = plain(m.group(2))
        if not text or text.lower() in CHROME_TEXT:
            continue
        hm = HREF.search(m.group(1))
        href = next((g for g in (hm.groups() if hm else ()) if g), "") if hm else ""
        if not href:
            continue
        if rmap.renders_at(m.start()) != "subject":
            continue
        total_subject += 1
        # The text has to still BE there. An anchor whose whole element was never placed
        # is an omission judgment, not a flattening — conflating them is what inflated
        # this census twice.
        if text not in linked and re.search(r"(?<!\w)" + re.escape(text) + r"(?!\w)", body):
            flattened.append(text)
    return {
        "subject_anchors": total_subject,
        "flattened": len(flattened),
        "sample": flattened[:5],
        "pass": not flattened,
    }


# ---------- check 2: #89, where the page's framing lives ---------- #


def crumb_labels(html: str, rmap: Any) -> list[str]:
    """The breadcrumb's own crumb labels, in source order, from the framing region the
    overlay declares. Read off the artifact so the check never depends on the record
    having got it right."""
    spans = [r for r in rmap.spans("framing") if "breadcrumb" in (r.role or "")]
    if not spans:
        return []
    frag = html[spans[0].start : spans[0].end]
    labels = [plain(m.group(2)) for m in ANCHOR.finditer(frag)]
    tail = plain(ANCHOR.sub(" ", frag))
    if tail:
        labels.append(tail)
    return [norm(x) for x in labels if x.strip()]


def check_crumb(html: str, post: Any, blocks: list[Any], rmap: Any) -> dict[str, Any]:
    """Three outcomes, and they are #89's three populations exactly:

      absent  the artifact has a breadcrumb, the record renders it nowhere
      inline  it is rendered, but loose in the content — not in the trailing span
      homed   it is rendered inside the trailing `<!--section index-->` (the target shape)
    """
    labels = [x for x in crumb_labels(html, rmap) if x]
    if len(labels) < 2:
        return {"verdict": "n/a", "pass": None}

    top = list(blocks)
    trailing = top[-1] if top else None
    trailing_is_index = bool(
        trailing is not None and getattr(trailing, "form", None) == "index"
    )
    trailing_segments = set()
    if trailing_is_index:
        trailing_segments = {id(s) for s in segments.leaf_segments([trailing])}

    for seg in segments.leaf_segments(top):
        if getattr(seg, "is_structural", False) or seg.atom != "text":
            continue
        for raw_line in (seg.body or "").strip().split("\n")[:3]:
            if ">" not in raw_line:
                continue
            line = norm(raw_line)
            if not line:
                continue
            # Chained IN ORDER *and adjacent across the separator*. Chaining alone is not
            # enough: this host's procedural prose is full of cross-references like
            # "Refer to Strut Assembly Replacement (See: Suspension > Strut / Shock)",
            # which chains two crumb labels around an unrelated `>` and scored as a
            # breadcrumb on 1,096 records. A crumb trail's defining property is that
            # NOTHING but the separator sits between consecutive labels.
            pos, chained, run, run_start, best_start = -1, 0, 0, 0, 0
            for label in labels:
                j = line.find(label, pos + 1)
                if j <= pos:
                    continue
                gap = line[pos + 1 : j] if pos >= 0 else ""
                if pos < 0 or not re.sub(r"[\s>:*|/-]+", "", gap):
                    run += 1
                else:
                    run, run_start = 1, j
                if run > chained:
                    chained, best_start = run, run_start
                pos = j + len(label) - 1
            # And the trail must OPEN the line. A breadcrumb is the first thing on its
            # line, allowing this fleet's (non-conforming, #74 item 3) vehicle-name
            # prefix; a chain that starts mid-sentence is procedural prose quoting a
            # navigation path, which is the last false-positive class.
            if chained >= 2 and line[:best_start].count(" ") <= 10:
                homed = id(seg) in trailing_segments
                return {
                    "verdict": "homed" if homed else "inline",
                    "chained": chained,
                    "of": len(labels),
                    "line": raw_line.strip()[:120],
                    "pass": homed,
                }
    return {"verdict": "absent", "of": len(labels), "pass": False}


# ---------- check 3: #121, presented order ---------- #


def check_order(blocks: list[Any]) -> dict[str, Any]:
    """Consecutive leaf segments whose addresses are DISJOINT must not run backwards.

    Containment is not mis-ordering — a figure at `el=…49.3` inside a prose span
    `el=…[49-81]` is nested, and order is only defined between disjoint addresses. The
    naive lexicographic test called 1,054 records; that is the trap this skips.
    """
    seq: list[tuple[furi.ElPath, furi.ElPath]] = []
    for seg in segments.leaf_segments(blocks):
        paths = el_paths(seg.address)
        if paths:
            key = furi.el_path_sort_key
            seq.append((min(paths, key=key), max(paths, key=key)))
    inversions = 0
    for (_lo_a, hi_a), (lo_b, _hi_b) in pairwise(seq):
        if furi.el_path_contains(hi_a, lo_b) or furi.el_path_contains(lo_b, hi_a):
            continue  # nested, not ordered
        if furi.el_path_sort_key(lo_b) < furi.el_path_sort_key(hi_a):
            inversions += 1
    return {"addressed_segments": len(seq), "inversions": inversions, "pass": not inversions}


# ---------- check 4: #90, form/index over a body that lists nothing ---------- #

_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", re.M)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)


def check_form(post: Any, blocks: list[Any]) -> dict[str, Any]:
    """`form/index`'s own contract: *a page is an index when removing its entries would
    leave nothing*. Answerable from the record alone, which is why #90 calls the rule its
    own worklist."""
    forms = {getattr(b, "form", None) for b in blocks} - {None}
    if "index" not in forms:
        return {"verdict": "n/a" if forms else "formless", "forms": sorted(forms), "pass": None}
    entries = 0
    for seg in segments.leaf_segments(blocks):
        body = seg.body or ""
        rows = [r for r in _TABLE_ROW.findall(body) if not re.match(r"^\s*\|[\s|:-]+\|\s*$", r)]
        entries += len(_LIST_ITEM.findall(body)) + max(0, len(rows) - 1)
    return {"verdict": "index", "entries": entries, "pass": entries > 0}


# ---------- driver ---------- #


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_root", type=Path)
    ap.add_argument("--ids", type=Path, help="restrict to these record ids (one per line)")
    ap.add_argument("--json", type=Path, help="write per-record results here")
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--legacy-text",
        action="store_true",
        help="score anchor text the way #118's published census did (no entity decoding) — "
        "the switch that reproduces 16,883/2,176",
    )
    args = ap.parse_args()
    if args.legacy_text:
        globals()["LEGACY_TEXT"] = True

    root = args.corpus_root
    wanted: set[str] | None = None
    if args.ids:
        wanted = {ln.strip() for ln in args.ids.read_text().split() if ln.strip()}

    decl = schemas.origin_regions(root, HOST)
    print(f"region declarations for {HOST}: {len(decl)}", file=sys.stderr)

    out: list[dict[str, Any]] = []
    counts: collections.Counter[str] = collections.Counter()
    totals: collections.Counter[str] = collections.Counter()
    scanned = 0

    for path in sorted(root.joinpath("records").rglob("*.md")):
        if wanted is not None and not any(path.stem.startswith(w) for w in wanted):
            continue
        try:
            post = records.load(path)
        except Exception:
            continue
        if not any((b.get("id") or "") == HOST for b in records.iter_origin_blocks(post)):
            continue
        rid = str(post.metadata.get("id") or path.stem)
        art = root / "artifacts" / rid[:2] / f"{rid}.html"
        if not art.is_file():
            continue
        scanned += 1
        if args.limit and scanned > args.limit:
            break

        html = art.read_text(encoding="utf-8", errors="replace")
        body = post.content or ""
        blocks = segments.iter_blocks(body)
        rmap = resolve_regions(html, decl)

        row = {
            "id": rid,
            "state": records.derived_state(post, root),
            "authored": any(
                str(t).startswith("corpus.compile") and "+" in str(t)
                for t in (post.metadata.get("touch") or [])
            ),
            "links": check_links(html, body, rmap),
            "crumb": check_crumb(html, post, blocks, rmap),
            "order": check_order(blocks),
            "form": check_form(post, blocks),
        }
        out.append(row)

        totals["links.flattened"] += row["links"]["flattened"]
        totals["order.inversions"] += row["order"]["inversions"]
        if row["links"]["flattened"]:
            counts["links.records"] += 1
        if row["order"]["inversions"]:
            counts["order.records"] += 1
        counts[f"crumb.{row['crumb']['verdict']}"] += 1
        if row["form"]["verdict"] == "index" and not row["form"]["pass"]:
            counts["form.empty_index"] += 1
        if scanned % 500 == 0:
            print(f"  … {scanned} scanned", file=sys.stderr, flush=True)

    print(f"\nscanned {scanned} {HOST} records with a resident artifact\n")
    authored = sum(1 for r in out if r["authored"])
    print(f"  authored (compile carries a model tag): {authored}")
    print(f"  never authored:                         {len(out) - authored}\n")

    def row_out(check: str, records_n: int, anchors_n: int | None) -> None:
        label, exp_a, exp_r = PUBLISHED[check]
        got = f"{records_n} records"
        if anchors_n is not None:
            got = f"{anchors_n:,} anchors / {got}"
        exp = f"{exp_r} records"
        if exp_a is not None:
            exp = f"{exp_a:,} anchors / {exp}"
        ok = records_n == exp_r and (exp_a is None or anchors_n == exp_a)
        print(f"  {check:<7} {got:<34} published {label}: {exp:<34} {'MATCH' if ok else 'DIFFERS'}")

    print("detector validation — against figures the tracker already published:")
    row_out("links", counts["links.records"], totals["links.flattened"])
    row_out("order", counts["order.records"], None)
    row_out("form", counts["form.empty_index"], None)
    row_out("crumb", counts["crumb.inline"], None)

    print("\ncrumb — where the page's own framing lives:")
    for verdict in ("homed", "inline", "absent", "n/a"):
        print(f"  {counts[f'crumb.{verdict}']:6}  {verdict}")

    if args.json:
        args.json.write_text(json.dumps(out, indent=1))
        print(f"\nper-record results → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
