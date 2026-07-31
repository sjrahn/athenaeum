"""§12.33's re-segment (ATH-CORPUS 3.9, #88) — the fleet extension.

**The shape.** A `member-rendered-on-parent` finding fires whenever a content-atom segment
stands at a member's own `el=`. Two unlike things share that signature (#101's measurement,
2026-07-31): a bare `text` body whose words are nowhere in the document is a genuine reading of
the member's pixels — leave it for `corpus.reseat`, the placement migration. A bare `text` body
whose words ARE in the document is the article's own prose, pinned to a neighbouring picture's
address because the paragraph had no element of its own — that is this migration's business,
and `reseat.reads_off_the_member` is the ONE test for which is which, reused rather than
re-derived (it is the test #88 itself proved).

**Two repairs for the borrowed population, unchanged from the sample that was proved and
applied** (corpus `c50013581` + `fbab00e5e`, §12.33):

- a **tight container** — one element whose own text is close to the segment's own body
  (within `TIGHTNESS`x) — gets a plain **re-address** (§12.28's rule: the tightest §6.1.1
  address containing the interval). Nothing about the body changes.
- **two or more** segments sharing one LOOSE container — none tight enough alone, because the
  prose has no element of its own — **merge** into one segment at that container's address,
  in the container's own reading order (§4.3.2.1: a span that is a subtree IS that subtree's
  own address). This is an AUTHORED change: it rewrites a body, not just an address.
- a segment whose only locatable container is loose AND it is alone there has no tight address
  and no merge partner. §6.1.1 records why: text in no element has no tight address. It is held,
  not guessed at — that population is #6.1.1's documented limit, not a bug in this migration.

One bucketing rule decides which repair applies, unlike the two separate passes the sample was
proved with: every borrowed segment locates to a container FIRST; a container claimed by
exactly one segment is a retarget candidate (tight) or a hold (loose); a container two or more
segments share is always a merge candidate, tight or not, because a shared address the retarget
alone can only give to one of them is the collision the sample's second apply had to add a
guard for after the fact (see guard D below) — bucketing this way removes the seam instead of
guarding it.

**Refusals over guesses, the §12.28 rule.** Every guard below exists because a prior run of
this same migration tripped it:

- a borrowed address carrying `&` params (a `bbox=`/`after=`/…) is left alone — that suffix is
  stated on the PICTURE's own surface and its presence means the segment is more likely a
  genuine crop-reading than borrowed prose, whatever the word-presence test said;
- a multi-region address (a list, naming more than one position at once) is out of scope —
  splitting one body's repair across two positions is a judgement this migration does not make;
- a merge group whose container ALSO covers a segment outside the group would under-merge and
  still collide;
- a merge or retarget target already claimed by another segment in the record — computed with
  the SAME `(opener-id, address)` key `segment-address-duplicate` uses, so the guard and the
  lint gate cannot disagree (a guard computed its own way missed this once: 11 collisions
  landed on records the re-segment had just merged prose onto, caught only by the after-gate);
- a member whose body would not literally survive inside the merged text;
- a move that would leave a member's roster row referenced by NO segment at all — a borrowed
  text body was, on some legacy records with no `image`/`placement` marker of its own,
  incidentally the ONLY thing satisfying `embed-unreferenced` for that member; moving it away
  blind would trade one finding for another, which the fleet measurement caught (net
  `embed-unreferenced` count rose before this guard existed).

**The positive-landing lesson, paid for once already.** A neutrality gate — "no new lint
findings" — cannot distinguish "changed nothing harmful" from "changed nothing at all"; the
first run of this migration reported 641 merges while writing zero bytes, and passed a
before/after lint diff by doing so, because `plan_record` and `apply_record` each parsed their
own fresh set of `Segment` objects and the drop-set/mutations addressed ghosts. The fix is
structural, not a bolt-on check: `plan_record` is handed the exact `blocks` list `apply_record`
will mutate, so identity holds end to end. Callers additionally assert the leaf-segment count
fell by exactly the expected amount and that every merged body survived (`RecordPlan` exists to
make that assertion cheap — see `tools/scripts/resegment_88.py`).
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from corpus import records, segments
from corpus.reseat import JUDGEABLE_WORDS, bare_words, reads_off_the_member
from corpus.transforms.html import EL_PARSER_ID, element_path, path_root

#: Touch identifier stamped on every record this migration rewrites.
TOUCH_ID = "migrate.resegment-88"

#: A candidate container may hold at most this many times a segment's own text before it is
#: "envelope only" rather than a tight address — §12.33's guard, unchanged from the sample that
#: was measured and proved (held population's ratios: median 15x, p90 58x — nowhere near this
#: margin).
TIGHTNESS = 3.0


@dataclass
class MergeGroup:
    """Two or more borrowed-prose segments sharing one loose container, in the container's own
    reading order — the merge repair."""

    address: str
    members: list[segments.Segment]


@dataclass
class Retarget:
    """One borrowed-prose segment whose located container is tight enough to be its own
    address outright — the re-address repair. No body changes."""

    segment: segments.Segment
    old_address: str
    new_address: str


@dataclass
class RecordPlan:
    """What this migration would do to one record — always built before anything is written."""

    merges: list[MergeGroup] = dataclass_field(default_factory=list)
    retargets: list[Retarget] = dataclass_field(default_factory=list)
    #: Reason -> count of segments held for it. Never a guess; always named.
    holds: collections.Counter = dataclass_field(default_factory=collections.Counter)
    #: Set when the WHOLE record is refused before any per-segment work (no members, artifact
    #: missing, …) — distinct from `holds`, which is per-segment within a record that proceeds.
    refused: str | None = None
    #: Set when the record has nothing for this migration at all — not a refusal, just no work.
    skipped: str | None = None

    @property
    def expected_leaf_drop(self) -> int:
        """How many fewer leaf segments the record should carry after `apply_record` — the
        positive-landing assertion's expected value (merges drop `len(members) - 1` each;
        retargets change an address, not the count)."""
        return sum(len(g.members) - 1 for g in self.merges)


def _member_addresses(post: Any) -> set[str]:
    """Every address a roster row claims (§4.3.1.4) — the same population
    `member-rendered-on-parent` itself keys off, built from the public roster reader rather
    than the lint rule's private map, so this migration needs no lint internals to agree with
    lint's own verdict."""
    out: set[str] = set()
    for row in records.iter_members(post):
        out.update(segments._iter_addr_strings(row.get("address") or ""))
    return out


def _addr_strings(value: Any) -> list[str]:
    return list(segments._iter_addr_strings(value or ""))


def _claim_key(seg: segments.Segment) -> str:
    return seg.overlay or seg.atom


def _collides(addr: str, kind: str, leaves: list[segments.Segment], exclude: set[int]) -> bool:
    """Would `(kind, addr)` collide with an EXISTING segment's claim, once `exclude` is out of
    the picture? The exact `segment-address-duplicate` key (`lint._rule_segment_address_duplicate`:
    `(opener-id, address)`, opener-id = `overlay or atom`) — computed here the same way so this
    guard and that gate cannot disagree."""
    for s in leaves:
        if id(s) in exclude or not isinstance(s, segments.Segment):
            continue
        if _claim_key(s) != kind:
            continue
        if addr in _addr_strings(s.address):
            return True
    return False


def _still_referenced(addr: str, leaves: list[segments.Segment], exclude: set[int]) -> bool:
    """Would the member roster row at *addr* still be referenced by SOME segment once
    `exclude` moves off it — `lint._rule_embed_unreferenced`'s own test (an exact address, or
    the base of a chained one, e.g. `el=3&bbox=…` references `el=3`), computed the same way so
    this guard and that gate cannot disagree. A borrowed text body was, incidentally, ALSO the
    only thing referencing its neighbour's embed on some legacy records with no `image`/
    `placement` marker segment of their own; moving it away without checking would silently
    turn `member-rendered-on-parent` into a NEW `embed-unreferenced` — trading one finding for
    another is not the improvement this migration exists to make."""
    for s in leaves:
        if id(s) in exclude or not isinstance(s, segments.Segment):
            continue
        for a in _addr_strings(s.address):
            if a == addr or a.split("&", 1)[0] == addr:
                return True
    return False


def _judgeable_probes(body: str) -> list[str]:
    """Every judgeable line of *body*, longest-first, each truncated to the same first-12-word
    window `reads_off_the_member` itself matches on. Locating a DOM element is a STRICTER
    operation than judging presence — a single top-probe missed the element in three-quarters
    of the cases a full-body-normalized search found instantly — so every judgeable line is
    tried, not only the longest."""
    seen: set[str] = set()
    out: list[str] = []
    for line in (body or "").splitlines():
        words = bare_words(line).split()
        if len(words) < JUDGEABLE_WORDS:
            continue
        probe = " ".join(words[:12])
        if probe not in seen:
            seen.add(probe)
            out.append(probe)
    return sorted(out, key=len, reverse=True)


def _deepest_carrier(root: Tag, needle: str) -> Tag | None:
    """The smallest element whose OWN rendered text contains *needle* — the tightest-carrier
    search #88's element-granular retarget and re-segment both used.

    Ties go to the LATER candidate, not the first. `root.find_all(True)` walks in document
    order — an ancestor before its children — so a `<div>` wrapping one `<img>` (no text) and
    one `<p>` (all the text) ties the `<p>` exactly: same length, ancestor found first. A
    strict "shorter wins" comparison would keep the div and report the whole wrapper as the
    tightest address for text that a single child already carries alone."""
    best: Tag | None = None
    best_len: int | None = None
    for el in root.find_all(True):
        if needle in bare_words(el.get_text()):
            n = len(el.get_text())
            if best is None or n <= best_len:  # type: ignore[operator]
                best, best_len = el, n
    return best


def _locate(root: Tag, probes: list[str]) -> tuple[Tag, str] | tuple[None, None]:
    for p in probes:
        el = _deepest_carrier(root, p)
        if el is not None:
            return el, p
    return None, None


def merge_bodies(members: list[segments.Segment]) -> str:
    """The merged body, members already in the container's reading order."""
    return "\n\n".join((s.body or "").strip() for s in members)


def plan_record(
    post: Any,
    artifact_path: Path,
    blocks: list[segments.Block],
    *,
    cited: frozenset[str] = frozenset(),
) -> RecordPlan:
    """The merges and retargets for one record, or an empty/refused/skipped plan.

    `blocks` MUST be the very list the caller will pass to `apply_record` — planning over a
    fresh parse produced `Segment` objects that were not the ones in the emitted tree once
    already (the migration wrote nothing while reporting 641 merges; see the module docstring).

    `cited` is the set of addresses THIS record's evidence cites in the ledger (exact address
    strings, as `lint`/`segments` compare them) — any borrowed segment sitting on one is held,
    never moved, however tight its container.
    """
    plan = RecordPlan()
    member_addrs = _member_addresses(post)
    if not member_addrs:
        plan.skipped = "no members"
        return plan

    leaves = list(segments.leaf_segments(blocks))
    candidates = [
        s
        for s in leaves
        if s.is_content
        and (s.body or "").strip()
        and s.overlay is None
        and s.atom == "text"
    ]
    bare = []
    for s in candidates:
        if not isinstance(s.address, str):
            if any(a.split("&", 1)[0] in member_addrs for a in _addr_strings(s.address)):
                plan.holds["multi-region address — out of scope"] += 1
            continue
        if s.address.split("&", 1)[0] not in member_addrs:
            continue
        if "&" in s.address:
            plan.holds["borrowed address carries params (image-relative; not this population)"] += 1
            continue
        bare.append(s)

    if not bare:
        plan.skipped = "no bare text segment borrows a member's address"
        return plan

    if not artifact_path.is_file():
        plan.refused = f"artifact missing at {artifact_path}"
        return plan
    soup = BeautifulSoup(artifact_path.read_bytes(), EL_PARSER_ID)
    root = path_root(soup)
    document = bare_words(soup.get_text(" "))

    # `reads_off_the_member` reused verbatim — a "yes" (words absent from the document) is a
    # genuine pixel reading and #101's business, not ours.
    borrowed = [s for s in bare if not reads_off_the_member(s.body, document)]
    plan.holds["pixel reading — corpus reseat's population, not this migration's"] += (
        len(bare) - len(borrowed)
    )
    if not borrowed:
        return plan

    container_map: dict[str, list[tuple[segments.Segment, Tag, str]]] = collections.defaultdict(
        list
    )
    for s in borrowed:
        probes = _judgeable_probes(s.body)
        if not probes:
            plan.holds["no judgeable probe (body too short to locate)"] += 1
            continue
        el, hit = _locate(root, probes)
        if el is None:
            plan.holds["no probe locatable as any element's own text"] += 1
            continue
        p = element_path(el, root)
        if not p:
            plan.holds["container has no §6.1.1 address"] += 1
            continue
        container_map[f"el={p}"].append((s, el, hit))  # type: ignore[arg-type]

    for addr, entries in container_map.items():
        segs = [e[0] for e in entries]
        el = entries[0][1]
        cited_here = [s for s in segs if s.address in cited]
        if cited_here:
            plan.holds["ledger cites this address"] += len(cited_here)
            entries = [e for e in entries if e[0] not in cited_here]
            segs = [e[0] for e in entries]
            if not segs:
                continue

        if len(segs) == 1:
            s = segs[0]
            container_text = bare_words(el.get_text())
            tight = len(container_text) <= TIGHTNESS * max(len(bare_words(s.body)), 1)
            if not tight:
                plan.holds["no tight container (envelope only) — §6.1.1's documented limit"] += 1
                continue
            if addr == s.address:
                continue  # already correct
            if _collides(addr, _claim_key(s), leaves, exclude={id(s)}):
                plan.holds["new address already claimed in this record"] += 1
                continue
            if not _still_referenced(s.address, leaves, exclude={id(s)}):
                plan.holds["moving this would leave the member's embed unreferenced"] += 1
                continue
            plan.retargets.append(Retarget(segment=s, old_address=s.address, new_address=addr))
            continue

        # merge candidate: two or more borrowed segments share one loose container. Every
        # candidate here is already bare `text`/no-overlay (the `candidates` filter above), so
        # a merge group can never mix atoms or overlays the way the sample's broader
        # "any non-picture atom" population could — that guard is structural now, not runtime.
        if any(s.extra for s in segs) or any(s.description for s in segs):
            plan.holds["a field would be silently dropped by the merge"] += len(segs)
            continue

        container_text = bare_words(el.get_text())
        # tightness against the GROUP's combined text — a container two-plus segments share is
        # not automatically a good merge target: alldata's flat-`<div>` bulletins are routinely
        # ONE div for the whole document (thousands of characters, every paragraph a bare `<b>`
        # label + text + `<br>`), so an unwrapped pair of stray sentences still locates there.
        # Checking only per-segment tightness (the len(segs) == 1 branch) would let such a
        # group fall through to the stranger-check below and be held for the wrong reason —
        # true, but it obscures that the real defect is §6.1.1's documented limit, not merely
        # that the container happens to hold something else too.
        combined_len = len(bare_words(merge_bodies(segs)))
        if len(container_text) > TIGHTNESS * max(combined_len, 1):
            plan.holds["no tight container (envelope only) — §6.1.1's documented limit"] += len(
                segs
            )
            continue
        exclude_ids = {id(s) for s in segs}
        outside = [
            o
            for o in leaves
            if id(o) not in exclude_ids
            and (o.body or "").strip()
            and any(p in container_text for p in _judgeable_probes(o.body))
        ]
        if outside:
            plan.holds["container also holds a non-member segment"] += len(segs)
            continue

        positions = {id(s): container_text.find(hit) for s, _el, hit in entries}
        if any(pos < 0 for pos in positions.values()):
            plan.holds["merge order: probe not found in container text"] += len(segs)
            continue
        ordered = sorted(segs, key=lambda s: positions[id(s)])

        if _collides(addr, _claim_key(ordered[0]), leaves, exclude=exclude_ids):
            plan.holds["new address already claimed in this record"] += len(segs)
            continue
        # a group's members may borrow DIFFERENT neighbouring members' addresses (two stray
        # paragraphs each pinned to a different nearby image), so every one of them is checked
        old_addrs = {s.address for s in segs}
        if any(not _still_referenced(a, leaves, exclude=exclude_ids) for a in old_addrs):
            plan.holds["moving this would leave the member's embed unreferenced"] += len(segs)
            continue

        plan.merges.append(MergeGroup(address=addr, members=ordered))

    return plan


def apply_record(
    plan: RecordPlan, blocks: list[segments.Block]
) -> tuple[bool, list[str]]:
    """Rewrite `blocks` in place over the SAME objects `plan` was built from. Returns
    `(ok, problems)`; on failure `blocks` and every segment in it are untouched — the
    body-survival check runs for every merge group BEFORE any mutation starts, precisely so a
    late-discovered problem cannot leave an earlier retarget or merge half-applied."""
    problems: list[str] = []
    merged_bodies: dict[int, str] = {}
    for g in plan.merges:
        merged = merge_bodies(g.members)
        merged_bodies[id(g)] = merged
        for m in g.members:
            if (m.body or "").strip() and (m.body or "").strip() not in merged:
                problems.append(f"{g.address}: a member body did not survive the merge")
    if problems:
        return False, problems

    for r in plan.retargets:
        r.segment.address = r.new_address

    drop: set[int] = set()
    for g in plan.merges:
        keep, rest = g.members[0], g.members[1:]
        keep.address = g.address
        keep.body = merged_bodies[id(g)]
        drop.update(id(m) for m in rest)

    if not drop:
        return True, []

    def prune(bs: list[segments.Block]) -> list[segments.Block]:
        out: list[segments.Block] = []
        for b in bs:
            if isinstance(b, segments.Section):
                b.segments = prune(list(b.segments))
                out.append(b)
            elif id(b) in drop:
                continue
            else:
                out.append(b)
        return out

    blocks[:] = prune(list(blocks))
    return True, []
