"""Ranged claims (spec/ledger.md v47.1, §4.2, §4.4, §5.6) — the roster's revision stratum.

A work's **revisions** are its distinct text states. Each is witnessed by rostered
records and ordered by `against`. The roster is the stratum a ranged claim scopes by:
evidence entry → `source` → record → that record's roster entry → its revision. This
module reads that stratum off one fact, deterministically and from the roster alone.
It never consults a claim (§5.6 Strata).

A roster entry names its revision by its `revision` tag. An entry that omits
`revision` but carries `expression` witnesses that expression's **sole** text state,
named by the expression slug (§4.2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import blake3

from ledger.model import CORPUS_URI_RE, canonical_claim_state, derived_uri

# A revision tag (§4.2): `2-1-2`, `d2026-10-27`, `c2026-06-21`, `t2026-10-28T15:20`,
# `t2026-10-28T15:20Z`, `t2026-10-28T15:20+01:00`. It is case-sensitive, because the
# stamp's `T`/`Z` are as printed. It never carries the §12 reference separators
# (`/`, `@`, `#`, `?`) or whitespace, so `@{expression}/{tag}` stays unambiguous.
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:+\-]*$")


@dataclass
class RosterRevisions:
    """One fact's revision stratum, read off its roster (§4.2)."""

    #: every revision name the roster witnesses (tags, plus sole-state expression slugs)
    names: set[str] = field(default_factory=set)
    #: the expression slugs the roster declares
    expressions: set[str] = field(default_factory=set)
    #: revision name → its expression (None on an unversioned work)
    expression_of: dict[str, str | None] = field(default_factory=dict)
    #: revision name → its predecessor's name, where the roster orders it
    against: dict[str, str] = field(default_factory=dict)
    #: full record hash → the revision name its entries witness (when they agree)
    record_revision: dict[str, str] = field(default_factory=dict)
    #: the §4.2 / §13.1 violations found while reading
    errors: list[str] = field(default_factory=list)

    def ancestors(self, name: str) -> list[str]:
        """*name*'s predecessors along the roster's `against` order, nearest first.
        This is cycle-safe: a cycle is reported by `read_roster` and simply stops
        the walk here."""
        out: list[str] = []
        seen = {name}
        cur = self.against.get(name)
        while cur is not None and cur not in seen:
            out.append(cur)
            seen.add(cur)
            cur = self.against.get(cur)
        return out

    def precedes(self, earlier: str, later: str) -> bool:
        """True iff *earlier* is an ancestor of *later* in the roster order."""
        return earlier in self.ancestors(later)


def _entry_revision(entry: dict) -> str | None:
    """The revision name a roster entry witnesses: its tag, or its expression's sole
    state, or None (the entry names neither)."""
    rev = entry.get("revision")
    if isinstance(rev, str) and rev:
        return rev
    expr = entry.get("expression")
    if isinstance(expr, str) and expr:
        return expr
    return None


def read_roster(fact: dict) -> RosterRevisions:
    """Read *fact*'s revision stratum and collect every v47.1 roster violation (§4.2):
    - tag grammar;
    - tags unique within the work and colliding with no expression slug;
    - within one expression, either every entry omits `revision` or every entry carries
      one;
    - a record's entries agree on `expression` and `revision`;
    - the entries witnessing a revision agree on its `against`;
    - `against` names another revision of this work, and the order is acyclic.
    """
    rr = RosterRevisions()
    entries = [e for e in (fact.get("artifacts") or []) if isinstance(e, dict)]
    tags: set[str] = set()
    per_expr_with: dict[str, int] = {}
    per_expr_without: dict[str, int] = {}
    per_record: dict[str, set[tuple[object, object]]] = {}
    against_seen: dict[str, set[str]] = {}

    for entry in entries:
        rev = entry.get("revision")
        expr = entry.get("expression")
        if isinstance(expr, str) and expr:
            rr.expressions.add(expr)
        if rev is not None:
            if not (isinstance(rev, str) and TAG_RE.match(rev)):
                rr.errors.append(
                    f"roster revision {rev!r} is not a tag — letters, digits, `.`, `:`, "
                    "`+`, `-`, starting with a letter or digit (§4.2)")
                continue
            tags.add(rev)
        if isinstance(expr, str) and expr:
            bucket = per_expr_with if rev is not None else per_expr_without
            bucket[expr] = bucket.get(expr, 0) + 1
        ag = entry.get("against")
        if ag is not None and not (isinstance(ag, str) and TAG_RE.match(ag)):
            rr.errors.append(f"roster against {ag!r} is not a revision name (§4.2)")
            continue
        name = _entry_revision(entry)
        if ag is not None and name is None:
            rr.errors.append(
                f"roster against {ag!r} on an entry naming no revision — `against` "
                "orders a revision, so the entry needs `revision` or `expression` (§4.2)")
        uri = entry.get("uri")
        m = CORPUS_URI_RE.match(str(uri or ""))
        if m:
            per_record.setdefault(m.group(1), set()).add(
                (expr if isinstance(expr, str) else None,
                 rev if isinstance(rev, str) else None))
        if name is None:
            continue
        rr.names.add(name)
        rr.expression_of.setdefault(name, expr if isinstance(expr, str) and expr else None)
        if isinstance(ag, str):
            against_seen.setdefault(name, set()).add(ag)

    for tag in sorted(tags & rr.expressions):
        rr.errors.append(
            f"roster revision tag {tag!r} collides with an expression slug of this work "
            "— tags are unique within the work and collide with none of its expression "
            "slugs (§4.2)")
    # one tag, one expression: the same tag under two expressions would be two revisions
    # sharing a name, which `@{tag}` and the `against` order cannot tell apart
    tag_exprs: dict[str, set[str | None]] = {}
    for entry in entries:
        rev = entry.get("revision")
        if isinstance(rev, str) and TAG_RE.match(rev):
            expr = entry.get("expression")
            tag_exprs.setdefault(rev, set()).add(expr if isinstance(expr, str) else None)
    for tag, exprs in sorted(tag_exprs.items()):
        if len(exprs) > 1:
            shown = sorted(str(e) for e in exprs)
            rr.errors.append(
                f"roster revision tag {tag!r} appears under expressions {shown} — a tag "
                "names one revision, unique within the work (§4.2)")
    for expr in sorted(set(per_expr_with) & set(per_expr_without)):
        rr.errors.append(
            f"roster expression {expr!r}: {per_expr_with[expr]} entr(y/ies) carry "
            f"`revision`, {per_expr_without[expr]} omit it — an omitted `revision` is the "
            "expression's SOLE text state, so within one expression every entry omits it "
            "or every entry carries it (§4.2)")
    for rec, pairs in sorted(per_record.items()):
        if len(pairs) > 1:
            shown = sorted((str(e), str(r)) for e, r in pairs)
            rr.errors.append(
                f"rostered corpus://{rec[:12]}… has entries disagreeing on (expression, "
                f"revision) {shown} — a record witnesses at most one revision of a work "
                "(§4.2)")
            continue
        (expr, rev), = pairs
        name = rev or expr
        if name is not None:
            rr.record_revision[rec] = name
    for name, ags in sorted(against_seen.items()):
        if len(ags) > 1:
            rr.errors.append(
                f"roster revision {name!r}: its entries disagree on `against` "
                f"{sorted(ags)} — entries witnessing one revision agree on it (§4.2)")
            continue
        (ag,) = ags
        if ag == name:
            rr.errors.append(f"roster revision {name!r} is `against` itself (§4.2)")
            continue
        if ag not in rr.names:
            rr.errors.append(
                f"roster revision {name!r} is `against` {ag!r}, which no roster entry of "
                "this work witnesses (§4.2)")
            continue
        rr.against[name] = ag
    for name in sorted(rr.against):
        seen = {name}
        cur = rr.against.get(name)
        while cur is not None:
            if cur == name:
                rr.errors.append(
                    f"roster `against` order is cyclic through revision {name!r} (§4.2)")
                break
            if cur in seen:
                break
            seen.add(cur)
            cur = rr.against.get(cur)
    return rr


# ------------------------------------------------------------------ ranged claims (§5.6)

#: a `revisions` entry's keys (§5.6 Reconciliation) — closed
REVISION_KEYS = {"revision", "mode", "source", "status", "against", "note"}
REVISION_MODES = {"transcribed", "diffed"}
#: a closure's keys (§5.6 Closures) — closed
CLOSURE_KEYS = {"element", "revision", "source", "anchor", "quote", "note", "replaced_by",
                "basis"}
CLOSURE_BASES = {"migration"}
#: a `corrections` entry's keys (§5.6 Corrections) — closed
CORRECTION_KEYS = {"element", "at", "key", "was", "note"}
#: the keys only a ranged claim carries (§5.1)
RANGED_CLAIM_KEYS = {"revisions", "closures", "corrections"}
#: the holding modes (§5.6 Holding)
ATTESTED, CARRIED, PENDING = "attested", "carried", "pending-closure"
#: weakest-first ranking of the ladder for the claim-level status (§5.3): the claim's
#: `status` equals the weakest of its revisions'
STATUS_RANK = {"disputed": 0, "conflicting": 1, "reported": 2, "inferred": 3,
               "provisional": 4, "confirmed": 5}


def is_folded(claim: dict) -> bool:
    """A claim under a `ranged` field is **folded** once it carries `revisions`;
    until then it is **unfolded**: frontier on the fold worklist, read whole (§5.6)."""
    return isinstance(claim, dict) and "revisions" in claim


def weakest_status(statuses: list[str]) -> str | None:
    ranked = [s for s in statuses if s in STATUS_RANK]
    return min(ranked, key=STATUS_RANK.__getitem__) if ranked else None


def _elements(claim: dict) -> int:
    """How many elements the claim has: its array's length, or 1 for a scalar value,
    whose one element is the value itself (§5.6 Holding)."""
    v = claim.get("value")
    return len(v) if isinstance(v, list) else 1


def _is_array(claim: dict) -> bool:
    return isinstance(claim.get("value"), list)


def _idx(obj: dict, claim: dict) -> int | None:
    """The element an evidence entry, closure or correction names: its `element` on an
    array claim, or 0 on a scalar claim (where it carries none). None means a malformed
    or out-of-range index, or a whole-value entry on an array claim."""
    el = obj.get("element")
    if not _is_array(claim):
        return 0 if el is None else None
    if isinstance(el, bool) or not isinstance(el, int):
        return None
    return el if 0 <= el < _elements(claim) else None


def source_revision(fact: dict, rr: RosterRevisions, skey: object) -> str | None:
    """The revision a sources key speaks for: key → record → roster entry → revision.
    It is derived and never written (§5.6). A `ref://` source, an unknown key or an
    unrostered record speaks for none."""
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    entry = sources.get(skey) if isinstance(skey, str) else None
    if not isinstance(entry, dict) or "record" not in entry:
        return None
    return rr.record_revision.get(str(entry["record"]))


@dataclass
class Holding:
    """A folded claim's holding table: revision → {element index → mode} (§5.6)."""

    #: the reconciled revisions, in table order
    order: list[str] = field(default_factory=list)
    #: revision → its `revisions` entry
    entries: dict[str, dict] = field(default_factory=dict)
    #: revision → {element → attested | carried | pending-closure}
    modes: dict[str, dict[int, str]] = field(default_factory=dict)
    #: revision → the element indices element-bound evidence attests there (whole-value
    #: entries attest every element of a scalar claim; on an array they count toward the
    #: bar but attest nothing, since the closure rule needs per-element attestation)
    attested: dict[str, set[int]] = field(default_factory=dict)
    #: revision → {element → [its closures there]}
    closures: dict[str, dict[int, list[dict]]] = field(default_factory=dict)

    def holds(self, rev: str, i: int) -> bool:
        return i in self.modes.get(rev, {})

    def chain(self, rev: str) -> list[str]:
        """*rev* and its reconciliation bases, along the table's `against`, nearest first."""
        out, seen, cur = [], set(), rev
        while cur is not None and cur in self.entries and cur not in seen:
            out.append(cur)
            seen.add(cur)
            ag = self.entries[cur].get("against")
            cur = ag if isinstance(ag, str) else None
        return out


def compute_holding(claim: dict, fact: dict, rr: RosterRevisions) -> Holding:
    """Evaluate §5.6 Holding over the claim's `revisions` table, in table order (an
    `against` names a revision listed earlier, so one pass suffices; an `against` that
    is not listed earlier contributes nothing — check reports it)."""
    h = Holding()
    n = _elements(claim)
    for ent in claim.get("revisions") or []:
        if not isinstance(ent, dict) or not isinstance(ent.get("revision"), str):
            continue
        rev = ent["revision"]
        if rev in h.entries:
            continue  # a duplicate row; check reports it
        h.order.append(rev)
        h.entries[rev] = ent
        h.attested[rev] = set()
        h.closures[rev] = {}
    for e in claim.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        rev = source_revision(fact, rr, e.get("source"))
        if rev not in h.attested:
            continue
        if not _is_array(claim):
            h.attested[rev].add(0)
            continue
        i = _idx(e, claim)
        if i is not None:
            h.attested[rev].add(i)
    for cl in claim.get("closures") or []:
        if not isinstance(cl, dict) or cl.get("revision") not in h.closures:
            continue
        i = _idx(cl, claim)
        if i is not None:
            h.closures[cl["revision"]].setdefault(i, []).append(cl)
    done: set[str] = set()
    for rev in h.order:
        ent = h.entries[rev]
        ag = ent.get("against")
        base = h.modes.get(ag, {}) if isinstance(ag, str) and ag in done else {}
        mode = ent.get("mode")
        modes: dict[int, str] = {}
        for i in range(n):
            closed = h.closures[rev].get(i, [])
            if i in h.attested[rev]:
                modes[i] = ATTESTED
            elif i in base and mode == "diffed" and not closed:
                modes[i] = CARRIED
            elif (i in base and mode == "transcribed" and closed
                  and all(c.get("basis") == "migration" for c in closed)):
                modes[i] = PENDING
        h.modes[rev] = modes
        done.add(rev)
    return h


# ------------------------------------------------------------------ projection selection


def parse_selection(sel: str) -> tuple[str, str | None]:
    """`x` or `x/y` (the part after `@`, §12) → (x, y)."""
    x, _, y = sel.partition("/")
    return x, (y or None)


def select_revision(sel: str, rr: RosterRevisions) -> tuple[str | None, str]:
    """Resolve an `@` selection to one revision of the work (§12 Projection): (revision,
    "") or (None, why unresolvable). On a work whose roster declares expressions, `x` is
    an expression and `x/y` names its revision `y`; a bare `x` is the expression's sole
    revision, or the terminal one in the roster's `against` order. On an unversioned
    work `x` is a tag."""
    x, y = parse_selection(sel)
    if not x:
        return None, f"empty selection @{sel!r}"
    if rr.expressions:
        if x not in rr.expressions:
            return None, f"@{sel}: {x!r} is no expression rostered on this work"
        revs = sorted(n for n, e in rr.expression_of.items() if e == x)
        if y is not None:
            if y not in revs:
                return None, f"@{sel}: {y!r} is no revision of expression {x!r}"
            return y, ""
        if len(revs) == 1:
            return revs[0], ""
        terminal = [r for r in revs if not any(rr.precedes(r, o) for o in revs if o != r)]
        if len(terminal) == 1 and all(rr.precedes(o, terminal[0])
                                      for o in revs if o != terminal[0]):
            return terminal[0], ""
        return None, (f"@{sel}: expression {x!r} has revisions {revs} that the roster's "
                      "`against` order does not chain to one terminal — ambiguous; pin "
                      f"the revision (@{x}/<tag>)")
    if y is not None:
        return None, f"@{sel}: an unversioned work is selected by tag alone (@<tag>)"
    if x not in rr.names:
        return None, f"@{sel}: {x!r} is no revision rostered on this work"
    return x, ""


@dataclass
class Projection:
    """A ranged claim read at one revision (§5.6, §12)."""

    claim_id: str
    revision: str
    status: object
    #: element index → (mode, element value, locators)
    elements: dict[int, tuple[str, object, dict]]
    evidence: list[dict]
    closures: list[dict]
    #: the revisions whose evidence and cites the projection carries (r plus every
    #: revision a holding element is carried through) — what its visibility reads
    through: list[str]


def project(claim: dict, fact: dict, rr: RosterRevisions, rev: str,
            holding: Holding | None = None) -> tuple[Projection | None, str]:
    """Project a folded claim at revision *rev* (§12): (projection, "") or (None, why)."""
    if not is_folded(claim):
        return None, f"{claim.get('id')}: unfolded — no projection (§5.6)"
    h = holding or compute_holding(claim, fact, rr)
    if rev not in h.entries:
        return None, (f"{claim.get('id')}: revision {rev!r} is not reconciled on this claim "
                      "— no defined element set (§5.6)")
    value = claim.get("value")
    through: list[str] = [rev]
    elements: dict[int, tuple[str, object, dict]] = {}
    for i, mode in sorted(h.modes[rev].items()):
        el = value[i] if isinstance(value, list) else value
        # the element's locators: its own revision's evidence, else the nearest along
        # the `against` chain (§6.1)
        locs: dict = {}
        for r in h.chain(rev):
            for e in claim.get("evidence") or []:
                if (isinstance(e, dict) and _idx(e, claim) == i
                        and source_revision(fact, rr, e.get("source")) == r
                        and isinstance(e.get("locators"), dict)):
                    locs = {**e["locators"], **locs}
            if locs:
                break
        # a carried (or pending-closure) element brings the revisions it is carried
        # through, back to the one that attests it
        if mode != ATTESTED:
            for r in h.chain(rev)[1:]:
                if r not in through:
                    through.append(r)
                if h.modes.get(r, {}).get(i) == ATTESTED:
                    break
        elements[i] = (mode, el, locs)
    evidence = [e for e in claim.get("evidence") or []
                if isinstance(e, dict) and source_revision(fact, rr, e.get("source")) == rev]
    closures = [c for c in claim.get("closures") or []
                if isinstance(c, dict) and c.get("revision") == rev]
    return Projection(str(claim.get("id")), rev, h.entries[rev].get("status"), elements,
                      evidence, closures, through), ""


def projection_cites(claim: dict, fact: dict, rr: RosterRevisions,
                     p: Projection) -> list[str]:
    """Every sources key a projection's visibility reads (§6.4): the evidence entries,
    closures and reconciliation cites of each revision in `p.through`."""
    keys: list[str] = []
    want = set(p.through)
    for e in claim.get("evidence") or []:
        if isinstance(e, dict) and source_revision(fact, rr, e.get("source")) in want:
            keys.append(e.get("source"))
    for c in claim.get("closures") or []:
        if isinstance(c, dict) and c.get("revision") in want:
            keys.append(c.get("source"))
    for r in claim.get("revisions") or []:
        if isinstance(r, dict) and r.get("revision") in want:
            keys.append(r.get("source"))
    return [k for k in keys if isinstance(k, str)]


# ------------------------------------------------------------------ check (§13.1)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_claim(claim: dict, fact: dict, rr: RosterRevisions) -> list[str]:
    """Every §13.1 Epistemics violation on one FOLDED ranged claim: the reconciliation
    table, evidence scoping, closures, completeness under `transcribed`, the claim-level
    status, `corrections`, and the qualifier ban. The per-(element, revision) bar is
    `bar_failures`, run by the caller (it reads the corpus join's surfaces)."""
    errs: list[str] = []
    n = _elements(claim)
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    table = claim.get("revisions")
    if not isinstance(table, list) or not table:
        return ["ranged claim `revisions` must be a non-empty list of reconciliations "
                "(§5.6)"]
    listed: list[str] = []
    for k, ent in enumerate(table):
        w = f"revisions[{k}]"
        if not isinstance(ent, dict):
            errs.append(f"{w} must be an object")
            continue
        bad = set(ent) - REVISION_KEYS
        if bad:
            errs.append(f"{w} unknown keys {sorted(bad)}")
        rev = ent.get("revision")
        if not isinstance(rev, str) or not rev:
            errs.append(f"{w} names no revision")
            continue
        if rev in listed:
            errs.append(f"{w} {rev!r} is reconciled twice — a revision appears at most once")
            continue
        if rev not in rr.names:
            errs.append(f"{w} {rev!r} is no revision rostered on this fact (§4.2)")
        mode = ent.get("mode")
        if mode not in REVISION_MODES:
            errs.append(f"{w} mode {mode!r} not in {sorted(REVISION_MODES)}")
        st = ent.get("status")
        if st not in STATUS_RANK:
            errs.append(f"{w} status {st!r} is not a ladder status (§5.3)")
        skey = ent.get("source")
        if not isinstance(skey, str) or skey not in sources:
            errs.append(f"{w} source {skey!r} does not resolve in this fact's sources")
        elif source_revision(fact, rr, skey) != rev:
            errs.append(f"{w} source {skey!r} does not witness {rev!r} — the "
                        "reconciliation cites the revision's own record (§5.6)")
        ag = ent.get("against")
        if ag is None:
            if mode == "diffed":
                errs.append(f"{w} {rev!r} is `diffed` with no `against` — a diff names "
                            "its base (§5.6)")
            prior = [r for r in listed if rr.precedes(r, rev)]
            if prior:
                errs.append(f"{w} {rev!r} omits `against`, but the roster orders it after "
                            f"{prior} which this claim already reconciles — `against` is "
                            "owed, or the earlier elements drop out unclosed (§5.6)")
        elif ag not in listed:
            errs.append(f"{w} {rev!r} is `against` {ag!r}, which is not listed earlier in "
                        "the table (§5.6)")
        elif rr.precedes(rev, ag):
            errs.append(f"{w} {rev!r} is `against` {ag!r}, which the roster orders AFTER "
                        "it (§5.6)")
        listed.append(rev)
    statuses = [e.get("status") for e in table if isinstance(e, dict)]
    weakest = weakest_status([s for s in statuses if isinstance(s, str)])
    if weakest is not None and claim.get("status") != weakest:
        errs.append(f"claim status {claim.get('status')!r} must equal its weakest "
                    f"revision's, {weakest!r} (§5.3)")
    # evidence on a ranged claim is scoped: a rostered record at a listed revision
    for k, e in enumerate(claim.get("evidence") or []):
        if not isinstance(e, dict):
            continue
        entry = sources.get(e.get("source")) if isinstance(e.get("source"), str) else None
        if isinstance(entry, dict) and "ref" in entry:
            errs.append(f"evidence[{k}] cites ref://{entry['ref']} — ref:// evidence is "
                        "not admissible on a ranged claim (§6.1)")
            continue
        rev = source_revision(fact, rr, e.get("source"))
        if isinstance(entry, dict) and "record" in entry and rev is None:
            errs.append(f"evidence[{k}] cites corpus://{str(entry['record'])[:12]}…, which "
                        "is rostered at no revision of this fact — evidence on a ranged "
                        "claim is never unscoped (§6.1)")
        elif rev is not None and rev not in listed:
            errs.append(f"evidence[{k}] speaks for revision {rev!r}, which the claim does "
                        "not reconcile (§6.1)")
        locs = e.get("locators")
        if locs is not None and not (isinstance(locs, dict) and all(
                isinstance(a, str) and isinstance(b, str) for a, b in locs.items())):
            errs.append(f"evidence[{k}] locators must map a key to its printed label "
                        "(§6.1)")
    h = compute_holding(claim, fact, rr)
    # closures (§5.6 Closures, Migration closures)
    for k, cl in enumerate(claim.get("closures") or []):
        w = f"closures[{k}]"
        if not isinstance(cl, dict):
            errs.append(f"{w} must be an object")
            continue
        bad = set(cl) - CLOSURE_KEYS
        if bad:
            errs.append(f"{w} unknown keys {sorted(bad)}")
        rev = cl.get("revision")
        if rev not in h.entries:
            errs.append(f"{w} names revision {rev!r}, which the claim does not reconcile")
            continue
        i = _idx(cl, claim)
        if i is None:
            errs.append(f"{w} element {cl.get('element')!r} is not an in-range index"
                        + ("" if _is_array(claim) else " (a scalar claim's closure "
                           "carries no element)"))
            continue
        basis = cl.get("basis")
        if basis is not None and basis not in CLOSURE_BASES:
            errs.append(f"{w} basis {basis!r} not in {sorted(CLOSURE_BASES)}")
        if basis == "migration" and h.entries[rev].get("mode") != "transcribed":
            errs.append(f"{w} is a migration closure on a {h.entries[rev].get('mode')!r} "
                        "revision — it stands only on `transcribed` (§5.6)")
        skey = cl.get("source")
        if not isinstance(skey, str) or skey not in sources:
            errs.append(f"{w} source {skey!r} does not resolve in this fact's sources")
        elif source_revision(fact, rr, skey) != rev:
            errs.append(f"{w} source {skey!r} does not witness {rev!r} — a closure cites "
                        "the closing revision's record (§5.6)")
        if not isinstance(cl.get("note"), str) or not cl.get("note"):
            errs.append(f"{w} carries no `note` saying what changed (§5.6)")
        ag = h.entries[rev].get("against")
        if not (isinstance(ag, str) and h.holds(ag, i)):
            errs.append(f"{w} closes element {i} at {rev!r}, but it does not hold at that "
                        "revision's `against` (§5.6)")
        if i in h.attested[rev]:
            errs.append(f"{w} closes element {i} at {rev!r}, where evidence attests it "
                        "(§5.6)")
        rb = cl.get("replaced_by")
        if rb is not None:
            if not (isinstance(rb, list) and all(
                    isinstance(x, int) and not isinstance(x, bool) for x in rb)):
                errs.append(f"{w} replaced_by must be a list of element indices")
            else:
                for x in rb:
                    if not 0 <= x < n:
                        errs.append(f"{w} replaced_by {x} is out of range")
                    elif not h.holds(rev, x):
                        errs.append(f"{w} replaced_by {x} does not hold at {rev!r} (§5.6)")
    # completeness under `transcribed` (§5.6): every element holding at `against` is
    # attested or closed at the revision (an inert migration closure counts)
    for rev in h.order:
        ent = h.entries[rev]
        ag = ent.get("against")
        if ent.get("mode") != "transcribed" or not isinstance(ag, str) or ag not in h.modes:
            continue
        missing = [i for i in sorted(h.modes[ag])
                   if i not in h.attested[rev] and not h.closures[rev].get(i)]
        if missing:
            shown = ", ".join(map(str, missing[:20])) + (" …" if len(missing) > 20 else "")
            errs.append(f"revision {rev!r} is `transcribed` (declared complete) but "
                        f"element(s) {shown} holding at {ag!r} are neither attested nor "
                        "closed there (§5.6 completeness)")
    # corrections (§5.6 Corrections)
    for k, co in enumerate(claim.get("corrections") or []):
        w = f"corrections[{k}]"
        if not isinstance(co, dict):
            errs.append(f"{w} must be an object")
            continue
        bad = set(co) - CORRECTION_KEYS
        if bad:
            errs.append(f"{w} unknown keys {sorted(bad)}")
        if _idx(co, claim) is None:
            errs.append(f"{w} element {co.get('element')!r} is not an in-range index")
        if not (isinstance(co.get("at"), str) and _DATE_RE.match(co["at"])):
            errs.append(f"{w} at {co.get('at')!r} is not a YYYY-MM-DD date")
        if not (isinstance(co.get("key"), str) and co["key"]):
            errs.append(f"{w} names no edited value `key`")
        if "was" not in co:
            errs.append(f"{w} records no prior value `was`")
    # the qualifier ban (§5.1): scope is derived, never written
    quals = claim.get("qualifiers") if isinstance(claim.get("qualifiers"), dict) else {}
    named = rr.names | rr.expressions
    for qk, qv in quals.items():
        if qk == "version" or (isinstance(qv, str) and qv in named):
            errs.append(f"ranged claim carries qualifier {qk}={qv!r} naming a version — "
                        "which text states an element is derived from its evidence, never "
                        "written (§5.1)")
    return errs


BarInfo = tuple[dict, bool, object, "tuple[str, str] | None"]


def bar_failures(claim: dict, fact: dict, rr: RosterRevisions,
                 infos: list[BarInfo]) -> dict[str, list[int]]:
    """§5.4 per (element, revision): for each `confirmed` revision, the elements holding
    there that fail the bar. *infos* is one (evidence entry, countable, kind, independent
    source id) per entry. An attested element counts its own entries from the revision
    plus the revision's whole-value entries. A carried or pending-closure element
    inherits its result from `against`."""
    h = compute_holding(claim, fact, rr)
    scoped = [(source_revision(fact, rr, e.get("source")), _idx(e, claim)
               if "element" in e else None, cnt, k, s) for e, cnt, k, s in infos]
    passed: dict[tuple[str, int], bool] = {}

    def clears(rev: str, i: int) -> bool:
        if (rev, i) in passed:
            return passed[(rev, i)]
        mode = h.modes.get(rev, {}).get(i)
        if mode == ATTESTED:
            mine = [(cnt, k, s) for r, el, cnt, k, s in scoped
                    if r == rev and (el is None or el == i)]
            ok = (any(cnt and k == "authoritative" for cnt, k, _s in mine)
                  or len({s for cnt, _k, s in mine if cnt and s is not None}) >= 2)
        elif mode in (CARRIED, PENDING):
            ag = h.entries[rev].get("against")
            ok = isinstance(ag, str) and clears(ag, i)
        else:
            ok = True
        passed[(rev, i)] = ok
        return ok

    out: dict[str, list[int]] = {}
    for rev in h.order:
        if h.entries[rev].get("status") != "confirmed":
            continue
        failing = [i for i in sorted(h.modes[rev]) if not clears(rev, i)]
        if failing:
            out[rev] = failing
    return out


def selection_well_formed(sel: object) -> bool:
    """`x` or `x/y`, each a tag or slug (§12 projection grammar)."""
    if not isinstance(sel, str):
        return False
    x, y = parse_selection(sel)
    return bool(TAG_RE.match(x)) and (y is None or bool(TAG_RE.match(y))) \
        and sel.count("/") <= 1


# ------------------------------------------------------------------ element pins (§7.3)


def canonical_element_state(claim: dict, fact: dict, element: int,
                            revisions: list[str] | None) -> str:
    """The v47.1 §7.3 element pin: blake3 over element N's value, the evidence entries
    bound to it, and its closures. Evidence is restricted to the revisions the pin was
    stamped over, when the claim is ranged. Evidence entries canonicalize to their
    derived citation, as `canonical_claim_state` does. A later revision's attestation
    therefore never flags the correction, while an edit to what it examined does."""
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    rr = read_roster(fact) if revisions is not None else None
    want = set(revisions or [])
    value = claim.get("value")
    ev = []
    for e in claim.get("evidence") or []:
        if not isinstance(e, dict) or e.get("element") != element:
            continue
        if rr is not None and source_revision(fact, rr, e.get("source")) not in want:
            continue
        e2 = {k: v for k, v in e.items() if k not in ("source", "anchor", "verified")}
        uri = derived_uri(sources, e.get("source"), e.get("anchor"))
        if uri is not None:
            e2["uri"] = uri
        ev.append(e2)
    closures = []
    for c in claim.get("closures") or []:
        if isinstance(c, dict) and c.get("element") == element:
            c2 = {k: v for k, v in c.items() if k not in ("source", "anchor")}
            uri = derived_uri(sources, c.get("source"), c.get("anchor"))
            if uri is not None:
                c2["uri"] = uri
            closures.append(c2)
    content = {
        "element": element,
        "value": value[element] if isinstance(value, list) and 0 <= element < len(value)
        else None,
        "evidence": ev, "closures": closures,
    }
    payload = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "blake3:" + blake3.blake3(payload.encode("utf-8")).hexdigest()


def challenge_state(challenges: dict, claim: dict, fact: dict) -> str:
    """The pin a `challenges` object carries: an element pin when it names `element`
    (§7.3, v47.1), else the whole-claim state."""
    el = challenges.get("element")
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    if isinstance(el, int) and not isinstance(el, bool):
        revs = challenges.get("revisions")
        return canonical_element_state(claim, fact, el,
                                       list(revs) if isinstance(revs, list) else None)
    return canonical_claim_state(claim, sources)


def stamp_revisions(claim: dict) -> list[str] | None:
    """The revision set an element pin is stamped over: the claim's reconciled
    revisions (a folded claim), else None (no ranging, all evidence bound to N)."""
    if not is_folded(claim):
        return None
    return [r["revision"] for r in claim.get("revisions") or []
            if isinstance(r, dict) and isinstance(r.get("revision"), str)]


# ------------------------------------------------------------------ references (§12, §4.1)

_REF_RE = re.compile(
    r"^(?:ledger://)?(?P<fact>[a-z0-9]+(?:--?[a-z0-9]+)*):(?P<short>[a-z0-9]+(?:--?[a-z0-9]+)*)"
    r"(?:@(?P<sel>[^#]+))?(?:#(?P<n>\d+))?$")


@dataclass
class Resolved:
    """A `ledger://` claim reference resolved (§12): where it landed, or why not."""

    ref: str
    claim_id: str | None = None
    #: the projection applied (the ref's own `@`, else a `ranged` row's), if any
    selection: str | None = None
    revision: str | None = None
    element: int | None = None
    projection: Projection | None = None
    #: the claim read whole (not ranged, or no `@` on a folded claim)
    whole: dict | None = None
    error: str = ""
    hops: list[str] = field(default_factory=list)


def resolve_reference(
    ref: str, facts_by_id: dict[str, dict], claim_rows: dict[str, dict],
    lineage: dict[str, str], ranged_field,
) -> Resolved:
    """Resolve a claim reference `ledger://{id}:{short}[@x[/y]][#N]` (§12) through the
    lineage map's one hop (§4.1). A `ranged` row lands on its ranged claim. It applies
    its `projection` when the reference carries no `@`, and remaps `#N` through its
    `elements` (absent means identity; an index the map does not carry is unresolvable).
    *ranged_field(fact, predicate)* says whether a claim sits under a ranged field.
    Selection on an unfolded claim is unresolvable. On a claim that is not ranged, `@`
    selects nothing and the claim reads whole."""
    out = Resolved(ref)
    m = _REF_RE.match(ref.strip())
    if not m:
        out.error = f"{ref!r} is not a claim reference ledger://{{id}}:{{short}}[@…][#N]"
        return out
    cid = f"{m.group('fact')}:{m.group('short')}"
    sel = m.group("sel")
    n = int(m.group("n")) if m.group("n") is not None else None
    row = claim_rows.get(cid)
    if row is not None:
        out.hops.append(f"{cid} → {row['to']} ({row['reason']})")
        if row["reason"] == "ranged":
            if sel is None and isinstance(row.get("projection"), str):
                sel = row["projection"]
            els = row.get("elements")
            if n is not None and isinstance(els, dict):
                if str(n) not in els:
                    out.error = (f"#{n} is not carried by the `ranged` row {cid!r}'s "
                                 "elements remap — unresolvable (§4.1)")
                    return out
                n = els[str(n)]
        cid = row["to"]
    else:
        fm = re.match(r"^([^:]+):(.+)$", cid)
        if fm and fm.group(1) in lineage:
            cid = f"{lineage[fm.group(1)]}:{fm.group(2)}"
            out.hops.append(f"{fm.group(1)} → {lineage[fm.group(1)]} (file row)")
    out.claim_id, out.selection, out.element = cid, sel, n
    fid = cid.split(":", 1)[0]
    fact = facts_by_id.get(fid)
    claim = next((c for c in (fact or {}).get("claims") or []
                  if isinstance(c, dict) and c.get("id") == cid), None)
    if claim is None:
        out.error = f"no living claim {cid!r}"
        return out
    is_ranged = ranged_field(fact, claim.get("predicate"))
    if sel is None or not is_ranged:
        out.whole = claim
        if is_ranged and is_folded(claim):
            # a folded claim read with no `@` is not one text's content (§12): report it
            # whole, flagged so a caller never mistakes it for a projection
            out.error = ("no `@` on a folded ranged claim — read through a projection, "
                         "never its raw value as one version's content (§12)")
        return out
    if not is_folded(claim):
        out.error = f"{cid!r} is unfolded — `@` on it is unresolvable (§5.6)"
        return out
    rr = read_roster(fact)
    rev, why = select_revision(sel, rr)
    if rev is None:
        out.error = why
        return out
    out.revision = rev
    p, why = project(claim, fact, rr, rev)
    if p is None:
        out.error = why
        return out
    out.projection = p
    if n is not None and n not in p.elements:
        out.error = (f"#{n} does not hold at {rev!r} — closed or not yet opened; "
                     "unresolvable (§12)")
    return out


def projection_table(claim_rows: dict[str, dict]) -> dict[str, dict[str, str]]:
    """{fact: {old qualifier: projection}} — the consumer's version-qualifier map, derived
    from the `ranged` rows' `qualifier` and `projection` (non-normative view)."""
    table, _conflicts = projection_table_checked(claim_rows)
    return table


def projection_table_checked(
    claim_rows: dict[str, dict],
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """`projection_table` and its conflicts. Where two predicates' rows disagree on one
    (fact, qualifier), as when one claim spans a patch the other was never reconciled
    at, the table keeps one deterministically (the most specific, then the lexically
    greatest) and names each disagreement. The conflict is the finding: a consumer pinning
    that projection meets the lagging predicate unreconciled until a scribe reconciles it
    there."""
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for key, row in sorted(claim_rows.items()):
        q, p = row.get("qualifier"), row.get("projection")
        if row.get("reason") == "ranged" and isinstance(q, str) and isinstance(p, str):
            fact = str(row["to"]).split(":", 1)[0]
            seen.setdefault((fact, q), {})[key] = p
    table: dict[str, dict[str, str]] = {}
    conflicts: list[str] = []
    for (fact, q), by_key in sorted(seen.items()):
        projs = sorted(set(by_key.values()))
        table.setdefault(fact, {})[q] = max(projs, key=lambda s: (s.count("/"), s))
        if len(projs) > 1:
            conflicts.append(f"{fact} {q!r}: " + ", ".join(
                f"{k} → @{p}" for k, p in sorted(by_key.items())))
    return table, conflicts


def load_reference_context(ledger_root):
    """(facts by id, claim-grain rows, file-grain lineage, ranged_field) for resolving
    references against a ledger tree."""
    from ledger import ontology
    from ledger.model import (
        is_redirect,
        load_claim_lineage_rows,
        load_json_dir,
        load_lineage,
    )
    from ledger.schemas import load_domain_schemas, load_schemas

    facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    by_id = {str(o.get("id")): o for o in facts.values()
             if isinstance(o, dict) and not is_redirect(o)}
    schemas, _ = load_schemas(ledger_root)
    domain_schemas, _ = load_domain_schemas(ledger_root)
    lineage, _ = load_lineage(ledger_root)

    def ranged_field(fact: dict, predicate: object) -> bool:
        fields = ontology.effective_schema(fact, schemas, domain_schemas).get("fields") or {}
        spec = fields.get(str(predicate))
        return isinstance(spec, dict) and spec.get("ranged") is True

    return by_id, load_claim_lineage_rows(ledger_root), lineage, ranged_field


def projection_json(r: Resolved) -> dict:
    """A resolved reference as the `ath ledger project --json` document."""
    doc: dict = {"ref": r.ref, "claim": r.claim_id, "hops": r.hops}
    if r.error:
        doc["error"] = r.error
    if r.projection is not None:
        p = r.projection
        els = p.elements if r.element is None else {
            k: v for k, v in p.elements.items() if k == r.element}
        doc.update({
            "selection": r.selection, "revision": p.revision, "status": p.status,
            "elements": [{"index": i, "mode": mode, "value": val,
                          **({"locators": locs} if locs else {})}
                         for i, (mode, val, locs) in sorted(els.items())],
            "evidence": p.evidence, "closures": p.closures, "through": p.through,
        })
    elif r.whole is not None:
        doc["whole"] = r.whole
    return doc


def revision_diff(claim: dict, fact: dict, rr: RosterRevisions, r1: str, r2: str) -> dict:
    """The derived view of what changed between two reconciled revisions of one ranged
    claim (§5.6 Derived views). Never authored knowledge. Returns `opened` (holding at
    *r2*, not *r1*), `closed` (holding at *r1*, not *r2*, with each closure's note and
    `replaced_by` where one closes it between them), `kept`, and `pending` (held at *r2*
    only as pending-closure)."""
    h = compute_holding(claim, fact, rr)
    for r in (r1, r2):
        if r not in h.entries:
            raise ValueError(f"{claim.get('id')}: revision {r!r} is not reconciled")
    a, b = h.modes[r1], h.modes[r2]
    closures = [c for c in claim.get("closures") or [] if isinstance(c, dict)]
    closed = []
    for i in sorted(set(a) - set(b)):
        why = [c for c in closures if c.get("element") == i]
        closed.append({"element": i, "closures": [
            {k: c[k] for k in ("revision", "note", "replaced_by", "basis") if k in c}
            for c in why]})
    return {"claim": claim.get("id"), "from": r1, "to": r2,
            "opened": sorted(set(b) - set(a)), "closed": closed,
            "kept": sorted(set(a) & set(b)),
            "pending": sorted(i for i, m in b.items() if m == PENDING)}
