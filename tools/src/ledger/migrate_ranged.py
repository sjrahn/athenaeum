"""`ath ledger migrate-ranged FACT PREDICATE` — fold version-split claims into one ranged
claim (spec/ledger.md v47.1, §4.1 `ranged` rows, §5.6; CHANGELOG v47.1 Migration).

Under v47 each version of a text got its own claim per predicate (`program-rule-v2-1`,
`-v2-2`, …), with the version in a qualifier and the short. `plan_fold` turns them into ONE
claim under the bare short. It does not write anything:

- **Revisions** come from the roster alone. The roster's `revision`/`against` must be
  backfilled first: every evidence record of every folded claim must be rostered at a
  revision, or the fold refuses. Nothing is inferred.
- **The oldest claim survives** with its indices: `old#k → #k`. A claim that already spans
  several revisions (a patch recapture appended to it) yields one `transcribed`
  reconciliation, then a `diffed` one per later revision. Its prose lifecycle markers
  ("Superseded at patch 2.1.2 by element 155.", "Not printed at patch …") become
  structured closures.
- **Each later claim**, in roster order, is matched against the elements holding at its
  `against`:
  - **authored identity notes**, where the transcription wrote them, override the
    classifier. "as v2.1 element N" continues element N. "changed from v2.1 element N: …"
    closes N and appends the new element. A predecessor element the notes never name was
    deliberately not printed, so it gets a real closure.
  - **auto-merge**: the element is value-equal (excluding `note` and locator keys) AND
    quote-set-equal to exactly one unmatched candidate. Its evidence is appended there.
  - **adjudicate** (exactly one of the two equal) and **append-and-close** (neither): a new
    element is appended, and the unmatched predecessor gets an INERT closure (`basis:
    migration`). It keeps holding as `pending-closure` until a human adjudicates.
  The later revision is `transcribed` at the claim's own status.
- **Lineage**: one `ranged` claim-grain row per retired claim id, with its full `elements`
  remap, the `projection` it stood for, and its version `qualifier`. A fact that survived a
  merge also gets the same row under each retired file id's spelling.
- **The byte invariant**, checked before any plan is returned: for every row and every
  remapped index, the element's `verbatim: true` keys (§4.4) are byte-identical old and new.
  The oldest claim's elements are identical outright, apart from the consumed `note` parts
  and the locator keys moved onto evidence.

`apply_fold` writes a refusal-free plan behind the same `ath ledger check` gate `merge`
and `move-claim` use: any NEW check error rolls every write back.
"""

from __future__ import annotations

import copy
import json
import re
from itertools import pairwise
from pathlib import Path

from ledger import ontology
from ledger import ranged as ranged_mod
from ledger.merge import MergeError, _dump, apply_merge
from ledger.model import (
    is_redirect,
    load_claim_lineage_rows,
    load_json_dir,
    load_lineage_rows,
)
from ledger.schemas import load_domain_schemas, load_schemas

FoldError = MergeError

# authored identity notes (the instance's v47 transcription convention)
_AS_RE = re.compile(r"\bas v(?P<ver>[\d.]+) element (?P<n>\d+)\b")
_CHANGED_RE = re.compile(r"\bchanged from v(?P<ver>[\d.]+) element (?P<n>\d+)\b:?\s*(?P<what>.*)")
_NEW_RE = re.compile(r"\bnew (?:in v[\d.]+|at patch [\d.]+)\b")
# prose lifecycle markers inside one claim spanning a patch recapture
_SUPERSEDED_RE = re.compile(
    r"\bSuperseded at patch (?P<ver>[\d.]+) by elements? (?P<ns>\d+(?:(?:,\s*|\s+and\s+)\d+)*)\.?")
_ABSENT_RE = re.compile(r"\bNot printed at patch (?P<ver>[\d.]+)\b[^;]*")

_ROW_KEYS_ORDER = ("to", "reason", "elements", "projection", "qualifier")


def _version_tag(ver: str, names: set[str]) -> str | None:
    """A printed patch number `2.1.2` → the rostered tag `2-1-2`, if the roster has it."""
    tag = ver.replace(".", "-")
    return tag if tag in names else None


def _strip(el: object, drop: set[str]) -> object:
    return {k: v for k, v in el.items() if k not in drop} if isinstance(el, dict) else el


def _note_parts(note: object) -> list[str]:
    return [p.strip() for p in note.split(";")] if isinstance(note, str) else []


def _clean_note(el: dict, ev_notes: set[str]) -> tuple[dict, list[str]]:
    """Drop the `note` parts the fold consumes. Those are the revision-local locator that
    the element's evidence notes already carry (§5.6: a locator never rides the value),
    the identity notes, and the lifecycle markers. Returns (element, the parts dropped).
    Whatever else the note said stays."""
    if "note" not in el:
        return el, []
    keep, dropped = [], []
    for part in _note_parts(el["note"]):
        if (part in ev_notes or _AS_RE.search(part) or _CHANGED_RE.search(part)
                or _NEW_RE.search(part) or _SUPERSEDED_RE.search(part)
                or _ABSENT_RE.search(part) or not part):
            dropped.append(part)
        else:
            keep.append(part)
    out = {k: v for k, v in el.items() if k != "note"}
    if keep:
        out["note"] = "; ".join(keep)
    return out, dropped


def _quotes_at(claim: dict, fact: dict, rr: ranged_mod.RosterRevisions,
               h: ranged_mod.Holding, rev: str | None, i: int) -> frozenset[str]:
    """Element *i*'s quotes in the revision that last attested it, walking back from *rev*
    along the claim's `against` chain."""
    for r in h.chain(rev) if rev else []:
        if i in h.attested.get(r, set()):
            return frozenset(str(e.get("quote")) for e in claim.get("evidence") or []
                             if isinstance(e, dict) and e.get("element") == i
                             and e.get("quote") and ranged_mod.source_revision(
                                 fact, rr, e.get("source")) == r)
    return frozenset()


def _quotes(claim: dict, i: int) -> frozenset[str]:
    return frozenset(str(e.get("quote")) for e in claim.get("evidence") or []
                     if isinstance(e, dict) and e.get("element") == i and e.get("quote"))


class _Fold:
    """Mutable working state of one fold (one fact, one predicate)."""

    def __init__(self, fact: dict, rr: ranged_mod.RosterRevisions, verbatim: set[str],
                 locators: set[str]):
        self.fact = fact
        self.rr = rr
        self.verbatim = verbatim
        self.locators = locators
        self.claim: dict = {"value": [], "evidence": [], "revisions": [], "closures": []}
        self.maps: dict[str, dict[int, int]] = {}
        self.errors: list[str] = []
        self.report: dict = {"auto_merge": 0, "authored_continue": 0, "authored_changed": 0,
                             "appended": 0, "adjudicate": [], "migration_closures": 0,
                             "authored_closures": 0, "lifecycle_closures": 0,
                             "note_parts_dropped": 0, "locators_moved": 0,
                             "followed_supersession": [], "authored_unmarked": []}

    # -- revisions

    def rev_source(self, claim: dict, rev: str) -> str | None:
        for e in claim.get("evidence") or []:
            if isinstance(e, dict) and ranged_mod.source_revision(
                    self.fact, self.rr, e.get("source")) == rev:
                return e.get("source")
        return None

    def nearest_reconciled(self, rev: str) -> str | None:
        listed = {r["revision"] for r in self.claim["revisions"]}
        return next((a for a in self.rr.ancestors(rev) if a in listed), None)

    def add_revisions(self, claim: dict, revs: list[str]) -> None:
        for k, rev in enumerate(revs):
            ent: dict = {"revision": rev,
                         "mode": "transcribed" if k == 0 else "diffed",
                         "source": self.rev_source(claim, rev),
                         "status": claim.get("status")}
            ag = self.nearest_reconciled(rev) if k == 0 else revs[k - 1]
            if ag is not None:
                ent = {"revision": rev, "against": ag, **{
                    k2: v for k2, v in ent.items() if k2 != "revision"}}
            if k == 0 and isinstance(claim.get("reasoning"), str):
                ent["note"] = f"folded from {claim.get('id')}: {claim['reasoning']}"
            self.claim["revisions"].append(ent)

    def follow(self, i: int, holding: set[int]) -> int | None:
        """Chase *i*'s closures' `replaced_by` to the one element in *holding* that
        succeeds it. Returns None when there is none, or more than one."""
        seen, frontier = {i}, [i]
        while frontier:
            nxt: list[int] = []
            for x in frontier:
                for cl in self.claim["closures"]:
                    if cl["element"] == x:
                        nxt.extend(r for r in cl.get("replaced_by") or [] if r not in seen)
            found = sorted({x for x in nxt if x in holding})
            if found:
                return found[0] if len(found) == 1 else None
            seen.update(nxt)
            frontier = nxt
        return None

    # -- elements

    def append(self, claim: dict, j: int) -> int:
        """Append old element *j* of *claim* as a new element; returns its index."""
        el = claim["value"][j]
        ev_notes = {str(e.get("note")) for e in claim.get("evidence") or []
                    if isinstance(e, dict) and e.get("element") == j and e.get("note")}
        if isinstance(el, dict):
            el, dropped = _clean_note(el, ev_notes)
            self.report["note_parts_dropped"] += len(dropped)
            el = _strip(el, self.locators)
        self.claim["value"].append(copy.deepcopy(el))
        return len(self.claim["value"]) - 1

    def move_evidence(self, claim: dict, j: int, to: int) -> None:
        el = claim["value"][j]
        locs = {k: str(el[k]) for k in self.locators
                if isinstance(el, dict) and k in el and el[k] is not None}
        for e in claim.get("evidence") or []:
            if isinstance(e, dict) and e.get("element") == j:
                e2 = {**e, "element": to}
                if locs:
                    e2["locators"] = {**locs, **(e.get("locators") or {})}
                    self.report["locators_moved"] += 1
                self.claim["evidence"].append(e2)

    def close(self, i: int, rev: str, claim: dict, note: str, *, migration: bool,
              replaced_by: list[int] | None = None) -> None:
        for cl in self.claim["closures"]:
            if cl["element"] == i and cl["revision"] == rev:
                if replaced_by:
                    cl.setdefault("replaced_by", [])
                    cl["replaced_by"] = sorted({*cl["replaced_by"], *replaced_by})
                return
        cl: dict = {"element": i, "revision": rev, "source": self.rev_source(claim, rev),
                    "note": note}
        if replaced_by:
            cl["replaced_by"] = sorted(replaced_by)
        if migration:
            cl["basis"] = "migration"
        self.claim["closures"].append(cl)


def _claim_revisions(fact: dict, rr: ranged_mod.RosterRevisions, claim: dict,
                     errors: list[str]) -> list[str]:
    """The revisions a v47 claim's evidence speaks for, in roster order."""
    revs: set[str] = set()
    for k, e in enumerate(claim.get("evidence") or []):
        if not isinstance(e, dict):
            continue
        rev = ranged_mod.source_revision(fact, rr, e.get("source"))
        if rev is None:
            src = (fact.get("sources") or {}).get(e.get("source"))
            errors.append(f"{claim.get('id')} evidence[{k}] (source {e.get('source')!r} → "
                          f"{json.dumps(src)}) is rostered at no revision — backfill the "
                          "roster's `revision` first; the fold never infers one")
            continue
        revs.add(rev)
    ordered = sorted(revs, key=lambda r: len(rr.ancestors(r)))
    for a, b in pairwise(ordered):
        if not rr.precedes(a, b):
            errors.append(f"{claim.get('id')} spans revisions {a!r} and {b!r}, which the "
                          "roster's `against` order does not chain")
    return ordered


def plan_fold(ledger_root: Path, fact_id: str, predicate: str,
              short: str | None = None) -> dict:
    """Compute the whole fold of *fact_id*'s version-split *predicate* claims without
    writing. Returns a plan: `errors` (refusals), `claim` (the folded claim), `rows` (the
    lineage rows), `report`, and `_writes`/`_originals` for `apply_fold`."""
    plan: dict = {"fact": fact_id, "predicate": predicate, "errors": [], "rows": {},
                  "retired": [], "report": {}, "projections": {}}

    def refuse(msg: str) -> dict:
        plan["errors"].append(msg)
        return plan

    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    found = [(p, o) for p, o in facts.items()
             if isinstance(o, dict) and o.get("id") == fact_id and not is_redirect(o)]
    if not found:
        return refuse(f"no living fact {fact_id!r}")
    fact_path, fact = found[0]
    schemas, _ = load_schemas(ledger_root)
    domain_schemas, _ = load_domain_schemas(ledger_root)
    fspec = (ontology.effective_schema(fact, schemas, domain_schemas).get("fields")
             or {}).get(predicate)
    if not (isinstance(fspec, dict) and fspec.get("ranged") is True):
        return refuse(f"{fact.get('type')}.{predicate} is not declared `ranged: true` "
                      "(§4.4) — declare it in the schema first")
    decls = fspec.get("elements") if isinstance(fspec.get("elements"), dict) else {}
    verbatim = {k for k, d in decls.items() if isinstance(d, dict) and d.get("verbatim")}
    locators = {k for k, d in decls.items() if isinstance(d, dict) and d.get("locator")}
    rr = ranged_mod.read_roster(fact)
    if rr.errors:
        return refuse("roster: " + "; ".join(rr.errors))
    olds = [c for c in fact.get("claims") or []
            if isinstance(c, dict) and c.get("predicate") == predicate]
    if any(ranged_mod.is_folded(c) for c in olds):
        return refuse(f"{fact_id} already holds a folded {predicate!r} claim — folding "
                      "into an existing ranged claim is not supported; reconcile by hand")
    if not olds:
        return refuse(f"{fact_id} has no {predicate!r} claims")
    if any(c.get("provenance") == "auto" for c in olds):
        return refuse("harvested (`provenance: auto`) claims are re-minted by harvest, "
                      "never folded")
    sshort = short or predicate
    survivor_id = f"{fact_id}:{sshort}"
    old_ids = [str(c.get("id")) for c in olds]
    living = {str(c.get("id")) for c in fact.get("claims") or [] if isinstance(c, dict)}
    if survivor_id in living and survivor_id not in old_ids:
        return refuse(f"{survivor_id!r} is a living claim outside the fold — pass --short")
    claim_rows = load_claim_lineage_rows(ledger_root)
    if survivor_id in claim_rows:
        return refuse(f"{survivor_id!r} is a retired claim id (occupied forever, §4.1) — "
                      "pass --short")

    # identity-bearing qualifiers other than the version must agree (§5.1)
    others = {json.dumps({k: v for k, v in (c.get("qualifiers") or {}).items()
                          if k != "version" and not (isinstance(v, str)
                                                     and v in rr.names | rr.expressions)},
                         sort_keys=True) for c in olds}
    if len(others) > 1:
        return refuse(f"the {predicate!r} claims differ in identity-bearing qualifiers "
                      f"{sorted(others)} — they are different claims; fold each set apart")
    span: dict[str, list[str]] = {}
    for c in olds:
        span[str(c.get("id"))] = _claim_revisions(fact, rr, c, plan["errors"])
        if not span[str(c.get("id"))]:
            plan["errors"].append(f"{c.get('id')} carries no evidence to scope it")
    if plan["errors"]:
        return plan
    olds.sort(key=lambda c: len(rr.ancestors(span[str(c.get("id"))][0])))
    firsts = [span[str(c.get("id"))][0] for c in olds]
    for a, b in pairwise(firsts):
        if a == b or not rr.precedes(a, b):
            return refuse(f"claims starting at {a!r} and {b!r} are not ordered by the "
                          "roster's `against` chain — fold needs one text order")

    fold = _Fold(fact, rr, verbatim, locators)
    # version display (`qualifiers.version`) → the old claim that carried it, for the
    # authored notes' "v2.1 element N"
    by_version = {str((c.get("qualifiers") or {}).get("version")): c for c in olds}

    for ci, c in enumerate(olds):
        cid = str(c.get("id"))
        value = c.get("value")
        if not isinstance(value, list):
            return refuse(f"{cid}: only array-valued claims fold mechanically (scalar "
                          "ranged claims are reconciled by hand)")
        revs = span[cid]
        cmap: dict[int, int] = {}
        if ci == 0:
            fold.add_revisions(c, revs)
            for j in range(len(value)):
                cmap[j] = fold.append(c, j)
                fold.move_evidence(c, j, cmap[j])
        else:
            ag = fold.nearest_reconciled(revs[0])
            fold.add_revisions(c, revs)
            rev0 = revs[0]
            h = ranged_mod.compute_holding(fold.claim, fact, rr)
            candidates = sorted(h.modes.get(ag, {})) if ag else []
            matched: set[int] = set()
            authored = any(isinstance(el, dict) and (
                _AS_RE.search(str(el.get("note", ""))) or _CHANGED_RE.search(
                    str(el.get("note", ""))) or _NEW_RE.search(str(el.get("note", ""))))
                for el in value)
            changed: list[tuple[int, int, str]] = []  # (old survivor idx, new idx, note)
            for j, el in enumerate(value):
                note = str(el.get("note", "")) if isinstance(el, dict) else ""
                target = None
                if authored:
                    am, cm = _AS_RE.search(note), _CHANGED_RE.search(note)
                    ref = am or cm
                    if ref is None and not _NEW_RE.search(note):
                        # authored mode is all-or-nothing per claim: an element carrying
                        # no identity note is appended as new, and so the predecessor it
                        # may continue gets a REAL closure. Name every one, loudly.
                        fold.report["authored_unmarked"].append(
                            {"claim": cid, "element": j})
                    if ref is not None:
                        src = by_version.get(ref.group("ver"))
                        n = int(ref.group("n"))
                        m_idx = fold.maps.get(str(src.get("id")), {}).get(n) \
                            if src is not None else None
                        # the note may name an element a patch already superseded: the
                        # transcriber compared against the version's claim, not its last
                        # text. Follow the closure's `replaced_by` to what holds at `ag`.
                        if m_idx is not None and m_idx not in candidates:
                            followed = fold.follow(m_idx, set(candidates))
                            if followed is not None:
                                fold.report["followed_supersession"].append(
                                    {"claim": cid, "element": j, "named": m_idx,
                                     "followed": followed})
                                m_idx = followed
                        if m_idx is None:
                            fold.errors.append(f"{cid}#{j}: note names v{ref.group('ver')} "
                                               f"element {n}, which the fold cannot place")
                        elif am is not None and m_idx in candidates and m_idx not in matched \
                                and all(_get(el, k) == _get(fold.claim["value"][m_idx], k)
                                        for k in verbatim):
                            target = m_idx
                            fold.report["authored_continue"] += 1
                        else:
                            what = (cm.group("what").strip() if cm is not None else
                                    "printed differently (verbatim keys changed)")
                            changed.append((m_idx, -1, what))
                else:
                    cand = [m for m in candidates if m not in matched]
                    ve = [m for m in cand
                          if _strip(_strip(fold.claim["value"][m], {"note"}), locators)
                          == _strip(_strip(el, {"note"}), locators)]
                    qe = [m for m in cand
                          if (q := _quotes_at(fold.claim, fact, rr, h, ag, m))
                          and q == _quotes(c, j)]
                    both = [m for m in ve if m in qe]
                    if len(both) == 1:
                        target = both[0]
                        fold.report["auto_merge"] += 1
                    elif ve or qe:
                        fold.report["adjudicate"].append({
                            "claim": cid, "element": j,
                            "value_equal": ve, "quote_equal": qe})
                if target is not None:
                    matched.add(target)
                    cmap[j] = target
                    fold.move_evidence(c, j, target)
                    continue
                cmap[j] = fold.append(c, j)
                fold.move_evidence(c, j, cmap[j])
                fold.report["appended"] += 1
                if changed and changed[-1][1] == -1:
                    changed[-1] = (changed[-1][0], cmap[j], changed[-1][2])
            for old_i, new_i, what in changed:
                if old_i in matched:
                    continue  # another element continued it; the change is an addition
                if old_i not in candidates:
                    fold.errors.append(f"{cid}: a note says element #{new_i} changed from "
                                       f"#{old_i}, which does not hold at {ag!r}")
                    continue
                fold.close(old_i, rev0, c, f"changed at {rev0}: {what}" if what
                           else f"changed at {rev0}", migration=False, replaced_by=[new_i])
                matched.add(old_i)
                fold.report["authored_changed"] += 1
            adj_by_old: dict[int, list[int]] = {}
            for a in fold.report["adjudicate"]:
                if a["claim"] == cid:
                    for m in {*a["value_equal"], *a["quote_equal"]}:
                        adj_by_old.setdefault(m, []).append(cmap[a["element"]])
            for m in candidates:
                if m in matched:
                    continue
                if authored:
                    fold.close(m, rev0, c, f"not printed at {rev0} (the {cid} transcription "
                               "carries no element continuing it)", migration=False)
                    fold.report["authored_closures"] += 1
                else:
                    fold.close(m, rev0, c, "migration: unmatched", migration=True,
                               replaced_by=adj_by_old.get(m))
                    fold.report["migration_closures"] += 1
        # prose lifecycle markers within this claim (a patch recapture appended to it)
        for j, el in enumerate(value):
            note = str(el.get("note", "")) if isinstance(el, dict) else ""
            for m in _SUPERSEDED_RE.finditer(note):
                tag = _version_tag(m.group("ver"), rr.names)
                ns = [int(x) for x in re.findall(r"\d+", m.group("ns"))]
                if tag is None or tag not in revs or any(x not in cmap for x in ns):
                    fold.errors.append(f"{cid}#{j}: lifecycle marker {m.group(0)!r} names "
                                       "no revision this claim spans")
                    continue
                fold.close(cmap[j], tag, c, m.group(0).rstrip("."), migration=False,
                           replaced_by=[cmap[x] for x in ns])
                fold.report["lifecycle_closures"] += 1
            for m in _ABSENT_RE.finditer(note):
                tag = _version_tag(m.group("ver"), rr.names)
                if tag is None or tag not in revs:
                    fold.errors.append(f"{cid}#{j}: lifecycle marker {m.group(0)!r} names "
                                       "no revision this claim spans")
                    continue
                fold.close(cmap[j], tag, c, m.group(0), migration=False)
                fold.report["lifecycle_closures"] += 1
        fold.maps[cid] = cmap

    # the folded claim
    first = olds[0]
    new = {"id": survivor_id, "predicate": predicate}
    quals = {k: v for k, v in (first.get("qualifiers") or {}).items()
             if k != "version" and not (isinstance(v, str) and v in rr.names | rr.expressions)}
    if quals:
        new["qualifiers"] = quals
    statuses = [str(r.get("status")) for r in fold.claim["revisions"]]
    new["status"] = ranged_mod.weakest_status(statuses) or first.get("status")
    asofs = [str(c["asof"]) for c in olds if c.get("asof")]
    if asofs:
        new["asof"] = max(asofs)
    if isinstance(first.get("reasoning"), str):
        new["reasoning"] = first["reasoning"]
    if any(c.get("sensitivity") == "private" for c in olds):
        new["sensitivity"] = "private"
    new["revisions"] = fold.claim["revisions"]
    new["value"] = fold.claim["value"]
    new["evidence"] = fold.claim["evidence"]
    if fold.claim["closures"]:
        new["closures"] = sorted(fold.claim["closures"],
                                 key=lambda cl: (cl["revision"], cl["element"]))
    plan["errors"].extend(fold.errors)

    # the byte invariant: verbatim keys identical across every remap; the oldest claim's
    # elements identical outright but for consumed note parts and moved locators
    for c in olds:
        cid = str(c.get("id"))
        for j, m_idx in fold.maps.get(cid, {}).items():
            old_el, new_el = c["value"][j], new["value"][m_idx]
            for k in verbatim:
                if _get(old_el, k) != _get(new_el, k):
                    plan["errors"].append(f"byte invariant: {cid}#{j} → #{m_idx} changes "
                                          f"verbatim key {k!r}")
            if c is first and _strip(_strip(old_el, {"note"}), locators) \
                    != _strip(_strip(new_el, {"note"}), locators):
                plan["errors"].append(f"byte invariant: {cid}#{j} → #{m_idx} changes the "
                                      "element")

    # lineage rows: every retired claim id, plus merge-survivor spellings
    file_rows, _ = load_lineage_rows(ledger_root)
    retired_files = sorted(k for k, v in file_rows.items() if v.get("to") == fact_id)
    for c in olds:
        cid = str(c.get("id"))
        last = span[cid][-1]
        expr = rr.expression_of.get(last)
        sole = expr is not None and [n for n, e in rr.expression_of.items() if e == expr] \
            == [last]
        proj = last if expr is None else (expr if sole else f"{expr}/{last}")
        plan["projections"][str((c.get("qualifiers") or {}).get("version", cid))] = proj
        if cid == survivor_id:
            continue
        row: dict = {"to": survivor_id, "reason": "ranged",
                     "elements": {str(k): v for k, v in sorted(fold.maps[cid].items())},
                     "projection": proj}
        q = (c.get("qualifiers") or {}).get("version")
        if isinstance(q, str):
            row["qualifier"] = q
        plan["rows"][cid] = row
        plan["retired"].append(cid)
        short_part = cid.split(":", 1)[1]
        for old_file in retired_files:
            key = f"{old_file}:{short_part}"
            if key not in claim_rows:
                plan["rows"][key] = row
    for key in plan["rows"]:
        if key in claim_rows:
            plan["errors"].append(f"lineage key {key!r} is already a row")

    # validate the folded claim against the v47.1 rules before any write
    new_fact = copy.deepcopy(fact)
    pos = min(i for i, c in enumerate(new_fact["claims"])
              if isinstance(c, dict) and c.get("predicate") == predicate)
    new_fact["claims"] = [c for c in new_fact["claims"]
                          if not (isinstance(c, dict) and c.get("predicate") == predicate)]
    new_fact["claims"].insert(pos, new)
    for msg in ranged_mod.check_claim(new, new_fact, rr):
        plan["errors"].append(f"folded claim: {msg}")

    # internal references naming a retired claim are rewritten in the same pass (§4.1)
    interps, _ = load_json_dir(ledger_root, "interpretations/*.json")
    retired = set(plan["retired"])
    plan["references_rewritten"] = []
    interp_writes: dict[str, str] = {}
    interp_originals: dict[str, str] = {}
    for ipath, o in sorted(interps.items()):
        if not isinstance(o, dict):
            continue
        changed_any = False
        based = o.get("based_on")
        if isinstance(based, list) and any(b in retired for b in based):
            o["based_on"] = [survivor_id if b in retired else b for b in based]
            changed_any = True
        ch = o.get("challenges")
        if isinstance(ch, dict) and ch.get("claim") in retired:
            plan["errors"].append(
                f"{ipath.name}: challenges {ch['claim']!r} — a correction on a folded claim "
                "is re-pinned as an ELEMENT pin (§7.3), which needs the disputed element: "
                "retarget it by hand (challenges.claim/element) before the fold")
        if changed_any:
            rel = str(ipath.relative_to(ledger_root))
            interp_originals[rel] = ipath.read_text(encoding="utf-8")
            interp_writes[rel] = _dump(o)
            plan["references_rewritten"].append(rel)

    plan["claim"] = new
    plan["report"] = {**fold.report, "elements": len(new["value"]),
                      "revisions": [r["revision"] for r in new["revisions"]],
                      "closures": len(new.get("closures") or [])}
    rel_fact = str(fact_path.relative_to(ledger_root))
    lineage_path = ledger_root / "facts" / "LINEAGE.json"
    raw = json.loads(lineage_path.read_text(encoding="utf-8")) if lineage_path.is_file() else {}
    raw.update({k: {rk: r[rk] for rk in _ROW_KEYS_ORDER if rk in r}
                for k, r in plan["rows"].items()})
    plan["_writes"] = {rel_fact: _dump(new_fact),
                       "facts/LINEAGE.json": json.dumps(raw, indent=1, ensure_ascii=False)
                       + "\n"}
    plan["_writes"].update(interp_writes)
    plan["_originals"] = {**interp_originals,
        rel_fact: fact_path.read_text(encoding="utf-8"),
        "facts/LINEAGE.json": (lineage_path.read_text(encoding="utf-8")
                               if lineage_path.is_file() else None),
    }
    return plan


def _get(el: object, k: str) -> object:
    return el.get(k) if isinstance(el, dict) else None


def apply_fold(ledger_root: Path, plan: dict, join=None, datasets=None) -> None:
    """Execute a refusal-free `plan_fold` behind the `ath ledger check` gate (see
    `merge.apply_merge`): any NEW check error rolls every write back."""
    apply_merge(ledger_root, plan, join, datasets, verb="migrate-ranged")
