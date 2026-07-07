"""The validation core — `spec/ledger.md` §13.1, deterministic and read-only.

Structure, graph, epistemics, evidence discipline, derived sensitivity,
schema conformance, invariants, and generated-view currency. Evidence
*content* verification (§13.2 — anchors, quotes, snapshot binding) is a
separate, heavier pass layered on top of this one.

Severity discipline: an `error` is a broken contract (rc 1); a `warning` is
work the ledger tracks but tolerates; a `note` is information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ledger import invariants as invariants_mod
from ledger import views
from ledger.corpora import CorpusJoin
from ledger.model import (
    ASOF_RE,
    CHALLENGE_KEYS,
    CLAIM_ID_RE,
    CLAIM_KEYS,
    CLAIM_STATUSES,
    CONCEPT_KEYS,
    CONFIDENCES,
    CORPUS_URI_RE,
    EDGE_KEYS,
    EVIDENCE_KEYS,
    EVIDENCE_KINDS,
    HYPOTHESIS_STATUSES,
    INTERP_KEYS,
    INTERP_KINDS,
    NEED_ACTIONS,
    NEED_KEYS,
    PERIOD_RE,
    QUALIFIED_URI_RE,
    REDIRECT_KEYS,
    REF_URI_RE,
    ROSTER_KEYS,
    SLUG_RE,
    STANDING_STATUSES,
    STATE_RE,
    WIKILINK_RE,
    canonical_claim_state,
    is_edge,
    is_redirect,
    load_json_dir,
)
from ledger.schemas import load_schemas

_RETIRED_QUALIFIERS_HINT = "time lives in `period`/`asof`, never ad-hoc qualifiers"


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_check(
    ledger_root: Path,
    join: CorpusJoin,
    datasets: set[str],
    *,
    no_corpus: bool = False,
) -> Report:
    rep = Report()
    facts, parse_errors = load_json_dir(ledger_root, "facts/*/*.json")
    interps, interp_parse_errors = load_json_dir(ledger_root, "interpretations/*.json")
    for e in parse_errors + interp_parse_errors:
        rep.errors.append(e)

    for stray in sorted(ledger_root.glob("facts/*.json")):
        rep.err(f"facts/{stray.name}", "fact files live under facts/{type}/, not facts/")

    schemas, schema_errors = load_schemas(ledger_root)
    rep.errors.extend(schema_errors)
    invs, inv_errors = invariants_mod.load_invariants(ledger_root)
    rep.errors.extend(inv_errors)

    # -------------------------------------------------- resolution availability
    resolve_live = not no_corpus and join.complete
    if no_corpus:
        rep.note("corpus join skipped (--no-corpus): resolution, status, and sensitivity "
                 "checks not run")
    elif not join.complete:
        rep.warn("corpus join", f"registered corpora missing on disk "
                 f"({', '.join(join.missing)}) — resolution, status, and sensitivity "
                 "checks NOT run; this check result certifies structure only")

    # ---------------------------------------------------------------- indexes
    ids: dict[str, Path] = {}
    redirects: dict[str, str] = {}
    live_facts: dict[str, dict] = {}
    fact_paths: dict[str, Path] = {}
    claims_by_id: dict[str, tuple[Path, dict, dict]] = {}

    def rel(p: Path) -> str:
        return str(p.relative_to(ledger_root))

    for f, o in facts.items():
        fid = o.get("id")
        stem = f.stem
        if fid != stem:
            rep.err(rel(f), f"id {fid!r} != filename stem {stem!r}")
        if not isinstance(fid, str) or not SLUG_RE.match(fid or ""):
            rep.err(rel(f), f"id {fid!r} is not a readable slug")
        dirname = f.parent.name
        if o.get("type") != dirname:
            rep.err(rel(f), f"type {o.get('type')!r} != directory {dirname!r}")
        if isinstance(fid, str):
            if fid in ids:
                rep.err(rel(f), f"duplicate id {fid!r} (also {rel(ids[fid])})")
            ids[fid] = f
            fact_paths[fid] = f
            if is_redirect(o):
                redirects[fid] = str(o.get("merged_into"))
            else:
                live_facts[fid] = o

    for f, o in interps.items():
        iid = o.get("id")
        if iid != f.stem:
            rep.err(rel(f), f"id {iid!r} != filename stem {f.stem!r}")
        if not isinstance(iid, str) or not SLUG_RE.match(iid or ""):
            rep.err(rel(f), f"id {iid!r} is not a readable slug")
        if isinstance(iid, str):
            if iid in ids:
                rep.err(rel(f), f"duplicate id {iid!r} (also {rel(ids[iid])}) — facts and "
                                "interpretations share one namespace")
            ids[iid] = f

    def resolve_id(ref: str) -> str | None:
        """A fact reference through at most one redirect hop → live id, or None."""
        if ref in live_facts:
            return ref
        if ref in redirects:
            target = redirects[ref]
            return target if target in live_facts else None
        return None

    # ------------------------------------------------------------- fact files
    all_claims: list[tuple[Path, dict, dict]] = []
    for f, o in facts.items():
        where = rel(f)
        if is_redirect(o):
            extra = set(o) - REDIRECT_KEYS
            if extra:
                rep.err(where, f"a redirect tombstone carries only id/type/merged_into "
                               f"(found {sorted(extra)})")
            target = str(o.get("merged_into"))
            if target not in live_facts:
                if target in redirects:
                    rep.err(where, f"merged_into {target!r} is itself a redirect — retarget "
                                   "to the final survivor (one-hop rule)")
                else:
                    rep.err(where, f"merged_into {target!r} does not exist")
            continue

        edge = is_edge(o)
        allowed = EDGE_KEYS if edge else CONCEPT_KEYS
        unknown = set(o) - allowed
        if unknown:
            kind = "edge" if edge else "concept"
            rep.err(where, f"unknown {kind} keys {sorted(unknown)}")
        if not edge and not o.get("name"):
            rep.err(where, "concept has no name (the minimum stub is id/type/name)")
        aliases = o.get("aliases")
        if aliases is not None and not (
            isinstance(aliases, list) and all(isinstance(a, str) for a in aliases)
        ):
            rep.err(where, "aliases must be a list of strings")
        if o.get("sensitivity") is not None and o.get("sensitivity") != "private":
            rep.err(where, "asserted sensitivity must be 'private' — the override is "
                           "upward only (derived privacy is the floor)")
        if o.get("provenance") not in (None, "auto"):
            rep.err(where, f"file provenance must be 'auto' when present "
                           f"(got {o.get('provenance')!r})")
        # the fact's own timebox (§4.2/§4.3) — concept or edge — same grammar as
        # a claim period; mirrors an evidenced timebox claim by convention
        if "period" in o and not PERIOD_RE.match(str(o["period"])):
            rep.warn(where, f"odd period format {o['period']!r}")
        if edge:
            subj = o.get("subject")
            if subj is not None and resolve_id(str(subj)) is None:
                rep.err(where, f"dangling subject {subj!r}")
            for p in o.get("participants") or []:
                if resolve_id(str(p)) is None:
                    rep.err(where, f"dangling participant {p!r}")
            declared_parts = (schemas.get(str(o.get("type"))) or {}).get("participants")
            if declared_parts:
                parts = [str(p) for p in o.get("participants") or []]
                if len(parts) != len(declared_parts):
                    rep.err(where, f"schema: {o.get('type')} declares participants "
                                   f"{declared_parts}, found {len(parts)}")
                else:
                    for i, (pid, want) in enumerate(zip(parts, declared_parts,
                                                        strict=True)):
                        resolved = resolve_id(pid)
                        got = live_facts.get(resolved or "", {}).get("type")
                        # dangling participants already errored above
                        if got is not None and got != want:
                            rep.err(where, f"schema: participants[{i}] {pid!r} is a "
                                           f"{got!r}, declared {want!r}")

        for entry in o.get("artifacts") or []:
            if not isinstance(entry, dict):
                rep.err(where, "roster entries must be objects")
                continue
            unknown = set(entry) - ROSTER_KEYS
            if unknown:
                rep.err(where, f"roster entry unknown keys {sorted(unknown)}")
            role = entry.get("role")
            if not role or not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", str(role)):
                rep.err(where, f"roster role {role!r} missing or not slug-shaped")
            if entry.get("provenance") not in (None, "auto"):
                rep.err(where, f"roster provenance must be 'auto' when present "
                               f"(got {entry.get('provenance')!r})")
            uri = str(entry.get("uri", ""))
            m = CORPUS_URI_RE.match(uri)
            if not m:
                if QUALIFIED_URI_RE.match(uri):
                    rep.err(where, f"roster uri {uri!r} uses the retired qualified form — "
                                   "cite bare corpus://{hash} (resolution is content-"
                                   "addressed, never scoped)")
                else:
                    rep.err(where, f"roster uri {uri!r} is not a corpus:// full-hash URI")
            elif resolve_live and not join.resolves(m.group(1)):
                rep.err(where, f"rostered corpus://{m.group(1)[:12]}… resolves in no "
                               "registered corpus")
            schema = schemas.get(str(o.get("type")))
            declared_roles = (schema or {}).get("roster_roles")
            if role and declared_roles and str(role) not in declared_roles:
                rep.err(where, f"roster role {role!r} not among the {o.get('type')!r} "
                               f"schema's roster_roles {declared_roles}")

        for c in o.get("claims") or []:
            if not isinstance(c, dict):
                rep.err(where, "claims must be objects")
                continue
            all_claims.append((f, o, c))
            cid = c.get("id")
            if isinstance(cid, str):
                if cid in claims_by_id:
                    rep.err(where, f"duplicate claim id {cid!r} "
                                   f"(also {rel(claims_by_id[cid][0])})")
                claims_by_id[cid] = (f, o, c)

    # ------------------------------------------------------------------ claims
    retired = views.retired_terms(ledger_root)
    need_hashes = _declared_need_hashes(interps)
    private_claims = 0
    private_files = 0

    for f, o, c in all_claims:
        cid = str(c.get("id", "?"))
        where = f"{rel(f)} :: {cid}"
        m = CLAIM_ID_RE.match(cid)
        if not m or m.group(1) != o.get("id"):
            rep.err(where, f"claim id must be '{o.get('id')}:{{short}}'")
        unknown = set(c) - CLAIM_KEYS
        if unknown:
            rep.err(where, f"unknown claim keys {sorted(unknown)}")
        pred = c.get("predicate")
        if not pred:
            rep.err(where, "missing predicate")
        elif str(pred) in retired:
            rep.err(where, f"retired vocabulary {pred!r} (see facts/VOCAB.md Retired)")
        st = c.get("status")
        if st not in CLAIM_STATUSES:
            rep.err(where, f"bad status {st!r} (allowed: {sorted(CLAIM_STATUSES)})")
        quals = c.get("qualifiers") or {}
        if not isinstance(quals, dict):
            rep.err(where, "qualifiers must be a mapping")
            quals = {}
        for qk in quals:
            if str(qk) in retired:
                rep.err(where, f"retired vocabulary qualifier {qk!r}")
            if str(qk) in ("when", "dates", "year", "period", "status"):
                rep.err(where, f"qualifier {qk!r} — {_RETIRED_QUALIFIERS_HINT}")
        if st == "reported" and not quals.get("attribution"):
            rep.err(where, "reported claims must name the voice in qualifiers.attribution")
        if c.get("provenance") not in (None, "auto"):
            rep.err(where, f"claim provenance must be 'auto' when present "
                           f"(got {c.get('provenance')!r})")
        if c.get("provenance") == "auto" and st not in (None, "provisional"):
            rep.err(where, f"harvested (auto) claims are capped at provisional (got {st!r})")
        if c.get("sensitivity") is not None and c.get("sensitivity") != "private":
            rep.err(where, "asserted claim sensitivity must be 'private' (upward only)")
        if "period" in c and not PERIOD_RE.match(str(c["period"])):
            rep.warn(where, f"odd period format {c['period']!r}")
        if "asof" in c and not ASOF_RE.match(str(c["asof"])):
            rep.warn(where, f"odd asof format {c['asof']!r}")
        if "asof" not in c and "period" not in c:
            rep.warn(where, "no asof or period (when was this observed/true?)")

        fspec = ((schemas.get(str(o.get("type"))) or {}).get("fields") or {}).get(str(pred))
        if not isinstance(fspec, dict):
            fspec = {}
        values = fspec.get("values")
        if values is not None and c.get("value") is not None \
                and str(c.get("value")) not in values:
            rep.err(where, f"schema: {o.get('type')}.{pred} value {c.get('value')!r} "
                           f"not among declared values {values}")
        obj = c.get("object")
        if fspec.get("participant") and obj is not None:
            parts = [str(p) for p in o.get("participants") or []]
            if str(obj) not in parts:
                rep.err(where, f"schema: {o.get('type')}.{pred} object must be one of "
                               f"the edge's participants {parts} (got {obj!r})")
        if obj is not None:
            target = resolve_id(str(obj))
            if target is None:
                rep.err(where, f"dangling object {obj!r}")
            else:
                want = fspec.get("target")
                got = live_facts.get(target, {}).get("type")
                admissible = want if isinstance(want, list) else [want] if want else []
                if admissible and got not in admissible:
                    rep.err(where, f"schema: {o.get('type')}.{pred} targets {want!r}, "
                                   f"object {obj!r} is a {got!r}")
        for s in _iter_strings(c.get("value")):
            for link in WIKILINK_RE.findall(s):
                if resolve_id(link) is None:
                    rep.err(where, f"wikilink [[{link}]] doesn't match a fact id")

        evs = c.get("evidence") or []
        if not evs:
            rep.err(where, "no evidence")
        hashes: set[str] = set()
        has_auth = False
        priv = c.get("sensitivity") == "private"
        for e in evs:
            if not isinstance(e, dict):
                rep.err(where, "evidence entries must be objects")
                continue
            unknown = set(e) - EVIDENCE_KEYS
            if unknown:
                rep.err(where, f"unknown evidence keys {sorted(unknown)}")
            kind = e.get("kind")
            if kind not in EVIDENCE_KINDS:
                rep.err(where, f"evidence kind {kind!r} missing/invalid "
                               f"(authoritative|direct|incidental)")
            has_auth = has_auth or kind == "authoritative"
            uri = str(e.get("uri", ""))
            cm = CORPUS_URI_RE.match(uri)
            rm = REF_URI_RE.match(uri)
            if cm:
                h = cm.group(1)
                hashes.add(h)
                if resolve_live:
                    if not join.resolves(h):
                        rep.err(where, f"cites corpus://{h[:12]}… which resolves in no "
                                       "registered corpus")
                    else:
                        if join.is_private(h):
                            priv = True
                        status = join.status(h)
                        if status != "normalized":
                            if h in need_hashes:
                                rep.warn(where, f"cites corpus://{h[:12]}… still "
                                                f"status={status} (a declared enqueue need "
                                                "covers it)")
                            else:
                                rep.err(where, f"cites corpus://{h[:12]}… still "
                                               f"status={status} — request normalization "
                                               "(corpus enqueue) and declare the need")
                        # snapshot binding (§13.2): a stamped verification whose
                        # record has since been re-normalized flags for re-verify
                        v = e.get("verified")
                        if isinstance(v, dict) and v.get("touch") and \
                                join.touch(h) and v["touch"] != join.touch(h):
                            rep.warn(where, f"corpus://{h[:12]}… re-normalized since this "
                                            "evidence was verified — re-run "
                                            "`ath ledger verify`")
            elif rm:
                if rm.group(1) not in datasets:
                    rep.err(where, f"ref:// dataset {rm.group(1)!r} is not registered in "
                                   "the manifest's references:")
            elif QUALIFIED_URI_RE.match(uri):
                rep.err(where, f"evidence uri {uri!r} uses the retired qualified form — "
                               "cite bare corpus://{hash}")
            else:
                rep.err(where, f"evidence uri {uri!r} is not a corpus:// or ref:// citation")
        if st == "confirmed" and evs and not (has_auth or len(hashes) >= 2):
            rep.err(where, "fails the authentication bar for `confirmed` (needs an "
                           "authoritative artifact or ≥2 independent records)")
        if priv:
            private_claims += 1
        c["_private"] = priv  # consumed by the file-level pass below, then dropped

    # file-level derived sensitivity (§6.4)
    if resolve_live:
        for _f, o in facts.items():
            if is_redirect(o):
                continue
            carried = []
            for c in o.get("claims") or []:
                if isinstance(c, dict):
                    carried.append(bool(c.pop("_private", False)))
            for entry in o.get("artifacts") or []:
                if isinstance(entry, dict):
                    m = CORPUS_URI_RE.match(str(entry.get("uri", "")))
                    carried.append(bool(m and join.is_private(m.group(1))))
            if o.get("sensitivity") == "private" or (carried and all(carried)):
                private_files += 1
        rep.counts["private_claims"] = private_claims
        rep.counts["private_files"] = private_files
        rep.note(f"sensitivity: {private_claims} private-backed claims, "
                 f"{private_files} private fact files (derived, §6.4)")
    else:
        for _, _o, c in all_claims:
            c.pop("_private", None)

    # --------------------------------------------------------- interpretations
    standing_challenges: dict[str, str] = {}  # claim id -> interp id
    for f, o in interps.items():
        where = rel(f)
        unknown = set(o) - INTERP_KEYS
        if unknown:
            rep.err(where, f"unknown keys {sorted(unknown)}")
        kind, st = o.get("kind"), o.get("status")
        if kind not in INTERP_KINDS:
            rep.err(where, f"bad kind {kind!r}")
        if kind == "hypothesis":
            if st not in HYPOTHESIS_STATUSES:
                rep.err(where, f"hypothesis status must be {sorted(HYPOTHESIS_STATUSES)}, "
                               f"got {st!r}")
            if o.get("confidence") not in CONFIDENCES:
                rep.err(where, f"hypothesis needs confidence {sorted(CONFIDENCES)}")
        elif kind in INTERP_KINDS:
            if st not in STANDING_STATUSES:
                rep.err(where, f"{kind} status must be {sorted(STANDING_STATUSES)}, "
                               f"got {st!r}")
            if o.get("confidence") is not None:
                rep.warn(where, "confidence is a hypothesis field")
        if st in ("promoted", "refuted") and not o.get("resolution"):
            rep.err(where, f"status {st} requires a resolution")
        if not o.get("statement"):
            rep.err(where, "missing statement")
        if not o.get("reasoning"):
            rep.warn(where, "no reasoning")
        if "asof" in o and not ASOF_RE.match(str(o["asof"])):
            rep.warn(where, f"odd asof format {o['asof']!r}")

        based = o.get("based_on") or []
        if not based:
            rep.err(where, "empty based_on — an interpretation must be evidence-linked "
                           "(a bare hunch is not repo material)")
        for b in based:
            b = str(b)
            cm = CORPUS_URI_RE.match(b)
            if cm:
                if resolve_live and not join.resolves(cm.group(1)):
                    rep.err(where, f"based_on corpus://{cm.group(1)[:12]}… resolves in no "
                                   "registered corpus")
                continue
            rm = REF_URI_RE.match(b)
            if rm:
                if rm.group(1) not in datasets:
                    rep.err(where, f"based_on ref:// dataset {rm.group(1)!r} unregistered")
                continue
            if QUALIFIED_URI_RE.match(b):
                rep.err(where, f"based_on {b!r} uses the retired qualified corpus form")
                continue
            if b not in claims_by_id:
                rep.err(where, f"based_on entry {b!r} is neither a citation nor a known "
                               "claim id")
        for a in o.get("about") or []:
            if resolve_id(str(a)) is None:
                rep.err(where, f"about entry {a!r} is not a known fact id")

        proposes = o.get("proposes")
        if proposes is not None:
            if kind != "hypothesis":
                rep.err(where, "proposes belongs on hypotheses")
            if not isinstance(proposes, dict):
                rep.err(where, "proposes must be a draft Claim object")
            else:
                pid = str(proposes.get("id", ""))
                pm = CLAIM_ID_RE.match(pid)
                if not pm:
                    rep.err(where, f"proposes.id {pid!r} must be '{{fact-id}}:{{short}}'")
                elif resolve_id(pm.group(1)) is None:
                    rep.err(where, f"proposes targets unknown fact {pm.group(1)!r}")
                if not proposes.get("predicate"):
                    rep.err(where, "proposes has no predicate")
                if not proposes.get("evidence"):
                    rep.warn(where, "proposes carries no evidence — promotion will need it")
                bad = set(proposes) - (CLAIM_KEYS - {"status"})
                if bad:
                    rep.err(where, f"proposes unknown keys {sorted(bad)} (status is "
                                   "assigned at promotion)")

        challenges = o.get("challenges")
        if challenges is not None:
            if kind != "correction":
                rep.err(where, "challenges belongs on corrections")
            if not isinstance(challenges, dict) or set(challenges) - CHALLENGE_KEYS:
                rep.err(where, "challenges must be {claim, state}")
            else:
                target = str(challenges.get("claim", ""))
                if target not in claims_by_id:
                    rep.err(where, f"challenges unknown claim {target!r}")
                else:
                    if st == "standing":
                        standing_challenges[target] = str(o.get("id"))
                    state = challenges.get("state")
                    if not state:
                        rep.warn(where, "challenge pin unstamped — set state to the "
                                        "canonical claim state (blake3 of the claim minus "
                                        "status)")
                    elif not STATE_RE.match(str(state)):
                        rep.err(where, f"challenge state {state!r} is not blake3:<64hex>")
                    else:
                        _, _, claim = claims_by_id[target]
                        current = canonical_claim_state(claim)
                        if current != state:
                            rep.warn(where, f"claim {target!r} edited since this challenge "
                                            "was filed — correction needs re-review "
                                            "(re-stamp after review)")

        for n in o.get("needs") or []:
            if not isinstance(n, dict):
                rep.err(where, "needs entries must be objects")
                continue
            unknown = set(n) - NEED_KEYS
            if unknown:
                rep.err(where, f"unknown need keys {sorted(unknown)}")
            if n.get("action") not in NEED_ACTIONS:
                rep.err(where, f"bad need action {n.get('action')!r}")
            if n.get("action") == "enqueue" and not CORPUS_URI_RE.match(str(n.get("record", ""))):
                rep.err(where, "enqueue need requires a bare corpus:// record")
            if not n.get("why"):
                rep.err(where, "need requires a why")

    # disputed ⇄ standing correction pairing
    for f, _o, c in all_claims:
        if c.get("status") == "disputed":
            cid = str(c.get("id"))
            if cid not in standing_challenges:
                rep.err(f"{rel(f)} :: {cid}", "disputed claim has no standing correction "
                                              "challenging it")
    for target, iid in standing_challenges.items():
        _, _, claim = claims_by_id[target]
        if claim.get("status") not in ("disputed", "conflicting"):
            rep.err(f"interpretations/{iid}.json",
                    f"standing challenge against {target!r} whose status is "
                    f"{claim.get('status')!r} — the challenged claim carries disputed")

    # ---------------------------------------------------------------- invariants
    for sev, msg in invariants_mod.evaluate(invs, facts):
        (rep.errors if sev == "error" else rep.warnings).append(msg)

    # the disagreement view (§13.1 Views): what voices assert vs what the
    # evidence establishes, enumerated — never an error, always surfaced
    for _f, o in facts.items():
        by_pred: dict[object, list[dict]] = {}
        for c in o.get("claims") or []:
            if isinstance(c, dict):
                by_pred.setdefault(c.get("predicate"), []).append(c)
        for pred, cs in by_pred.items():
            confirmed = [c for c in cs if c.get("status") == "confirmed"]
            for r in (c for c in cs if c.get("status") == "reported"):
                for k in confirmed:
                    if (r.get("value"), r.get("object")) != (k.get("value"), k.get("object")):
                        voice = (r.get("qualifiers") or {}).get("attribution", "?")
                        rep.note(f"disagreement: {o.get('id')}.{pred} — {voice} asserts "
                                 f"{r.get('id')}; the evidence says {k.get('id')}")

    # --------------------------------------------------------------------- views
    vocab_path = ledger_root / views.VOCAB_PATH
    if not vocab_path.is_file():
        rep.warn(views.VOCAB_PATH, "missing — run `ath ledger regen`")
    elif views.fresh_vocab(ledger_root, facts) != vocab_path.read_text(encoding="utf-8"):
        rep.warn(views.VOCAB_PATH, "stale — run `ath ledger regen`")
    openq_path = ledger_root / views.OPENQ_PATH
    if not openq_path.is_file():
        rep.warn(views.OPENQ_PATH, "missing — run `ath ledger regen`")
    else:
        fresh = views.fresh_openq(ledger_root, facts, interps, schemas)
        if fresh is None:
            rep.warn(views.OPENQ_PATH, "generated-block markers missing "
                                       f"({views.OPENQ_MARKS[0]} … {views.OPENQ_MARKS[1]})")
        elif fresh != openq_path.read_text(encoding="utf-8"):
            rep.warn(views.OPENQ_PATH, "stale — run `ath ledger regen`")

    rep.counts["facts"] = len(facts)
    rep.counts["interpretations"] = len(interps)
    rep.counts["claims"] = len(all_claims)
    return rep


def _declared_need_hashes(interps: dict[Path, dict]) -> set[str]:
    """Hashes named by enqueue needs — drafts these cover warn instead of erroring."""
    out: set[str] = set()
    for o in interps.values():
        for n in o.get("needs") or []:
            if isinstance(n, dict):
                m = CORPUS_URI_RE.match(str(n.get("record", "")))
                if m:
                    out.add(m.group(1))
    return out


def _iter_strings(v: object):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _iter_strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _iter_strings(x)
