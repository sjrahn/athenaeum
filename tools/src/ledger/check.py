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
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

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
    FULL_HASH_RE,
    HYPOTHESIS_STATUSES,
    INTERP_KEYS,
    INTERP_KINDS,
    NEED_ACTIONS,
    NEED_KEYS,
    PERIOD_RE,
    PROPOSES_EVIDENCE_KEYS,
    QUALIFIED_URI_RE,
    REF_URI_RE,
    ROSTER_KEYS,
    SLUG_RE,
    SOURCE_KEY_RE,
    SOURCE_REF_RE,
    SOURCES_ENTRY_KEYS,
    STANDING_STATUSES,
    STATE_RE,
    WIKILINK_RE,
    canonical_claim_state,
    is_edge,
    is_redirect,
    load_json_dir,
    load_lineage,
)
from ledger.schemas import load_schemas

if TYPE_CHECKING:
    from ath.manifest import Reference

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
    datasets: Mapping[str, Reference],
    *,
    no_corpus: bool = False,
) -> Report:
    rep = Report()
    facts, parse_errors = load_json_dir(ledger_root, "facts/*/*.json")
    interps, interp_parse_errors = load_json_dir(ledger_root, "interpretations/*.json")
    for e in parse_errors + interp_parse_errors:
        rep.errors.append(e)

    for stray in sorted(ledger_root.glob("facts/*.json")):
        if stray.name == "LINEAGE.json":  # the lineage map (§4.1) lives here by design
            continue
        rep.err(f"facts/{stray.name}", "fact files live under facts/{type}/, not facts/")

    schemas, schema_errors = load_schemas(ledger_root)
    rep.errors.extend(schema_errors)
    invs, inv_errors = invariants_mod.load_invariants(ledger_root)
    rep.errors.extend(inv_errors)

    # -------------------------------------------------- resolution availability
    resolve_live = not no_corpus and join.complete
    if no_corpus:
        rep.note("corpus join skipped (--no-corpus): resolution, binding-staleness, and "
                 "sensitivity checks not run")
    elif not join.complete:
        rep.warn("corpus join", f"registered corpora missing on disk "
                 f"({', '.join(join.missing)}) — resolution, binding-staleness, and "
                 "sensitivity checks NOT run; this check result certifies structure only")

    # ---------------------------------------------------------------- indexes
    ids: dict[str, Path] = {}
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
            # a legacy redirect-shape file (§4.1, is_redirect) is never live —
            # it errors below in the main fact-files pass and contributes
            # nothing to resolution; lineage (facts/LINEAGE.json) is the only
            # source of redirect chasing now
            if not is_redirect(o):
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

    # the lineage map (§4.1): id uniqueness runs across facts + interpretations
    # + the map's own KEYS, so a retired slug can never be re-minted by accident
    lineage, lineage_errors = load_lineage(ledger_root)
    rep.errors.extend(lineage_errors)
    for key, target in lineage.items():
        if key in ids:
            rep.err("facts/LINEAGE.json", f"lineage key {key!r} collides with a living id "
                                          f"(also {rel(ids[key])})")
        if target not in live_facts:
            if target in lineage:
                rep.err("facts/LINEAGE.json", f"lineage row {key!r} -> {target!r}: "
                                              f"{target!r} is itself a retired id — retarget "
                                              "to the final survivor (one-hop rule)")
            else:
                rep.err("facts/LINEAGE.json", f"lineage row {key!r} -> {target!r}: "
                                              f"{target!r} does not exist")

    def resolve_id(ref: str) -> str | None:
        """A fact reference through at most one lineage-map hop → live id, or None."""
        if ref in live_facts:
            return ref
        if ref in lineage:
            target = lineage[ref]
            return target if target in live_facts else None
        return None

    # needed inside the fact loop below (per-source resolution checks), so
    # computed ahead of the claims pass that used to compute it
    retired = views.retired_terms(ledger_root)
    used_sources: dict[Path, set[str]] = {}

    # *(17, §6.5/§13.1)* every registered mirror-artifact hash, hash -> the
    # (dataset, tag) that registered it — first registrant wins on a hash
    # collision across datasets (vanishingly unlikely; a blake3 collision or a
    # deliberately shared mirror). Built once, purely from the manifest (no
    # corpus join needed), and consulted below wherever claim evidence could
    # cite a mirror's bytes directly instead of through `ref://`.
    mirror_hash_owner: dict[str, tuple[str, str]] = {}
    for dname, dref in datasets.items():
        for tag, snap in (dref.snapshots or {}).items():
            mirror_hash_owner.setdefault(snap.artifact, (dname, tag))

    # ------------------------------------------------------------- fact files
    all_claims: list[tuple[Path, dict, dict]] = []
    for f, o in facts.items():
        where = rel(f)
        if is_redirect(o):
            rep.err(where, "carries the legacy redirect shape (merged_into) — fold into "
                           "facts/LINEAGE.json (§4.1)")
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

        # *(17, §6.5)* deliberately no mirror-hash-as-evidence warning here: a
        # roster entry citing a mirror artifact's corpus hash is not evidence
        # standing in for `ref://` content — it's the coverage-discharge
        # mechanism itself ("snapshot records roster on the dataset's own
        # concept ... never per entry"). Warning here would fight the spec's
        # own design.
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

        # the per-fact sources table: claim evidence cites a `source` key
        # (validated in the claims pass below) that resolves here to exactly
        # one record|ref target — resolution and binding staleness are
        # checked ONCE per source, not once per citing evidence entry
        sources = o.get("sources")
        if sources is not None and not isinstance(sources, dict):
            rep.err(where, "sources must be a mapping of source-key to {record|ref, "
                           "verified?}")
            sources = None
        if isinstance(sources, dict):
            targets_seen: dict[tuple[str, str], str] = {}
            for skey, sentry in sources.items():
                swhere = f"{where} :: sources.{skey}"
                if not isinstance(skey, str) or not SOURCE_KEY_RE.match(skey):
                    rep.err(where, f"source key {skey!r} is not local-slug shaped "
                                   "(^[a-z][a-z0-9-]{0,31}$)")
                if not isinstance(sentry, dict):
                    rep.err(swhere, "sources entry must be an object")
                    continue
                unknown = set(sentry) - SOURCES_ENTRY_KEYS
                if unknown:
                    rep.err(swhere, f"unknown sources-entry keys {sorted(unknown)}")
                has_record, has_ref = "record" in sentry, "ref" in sentry
                if has_record == has_ref:
                    rep.err(swhere, "a sources entry must carry exactly one of "
                                   "record|ref")
                    continue
                v = sentry.get("verified")
                if v is not None and not isinstance(v, dict):
                    rep.err(swhere, "verified must be an object")
                if has_record:
                    h = str(sentry["record"])
                    if not FULL_HASH_RE.match(h):
                        rep.err(swhere, f"record {h!r} is not a full 64-hex blake3 hash")
                    dup = targets_seen.get(("record", h))
                    if dup is not None:
                        rep.err(swhere, f"duplicate source for record {h[:12]}… (also "
                                       f"{dup!r}) — one sources entry per target")
                    else:
                        targets_seen[("record", h)] = skey
                    owner = mirror_hash_owner.get(h)
                    if owner is not None:
                        odset, otag = owner
                        rep.warn(swhere, f"record {h[:12]}… is the mirror artifact for "
                                        f"{odset!r}@{otag!r} — the mirror record exists "
                                        "for provenance and distribution; its content's "
                                        f"honest citation surface is ref://{odset}/{{id}}, "
                                        "not the corpus hash directly (§6.5, §13.1)")
                    if resolve_live and FULL_HASH_RE.match(h):
                        if not join.resolves(h):
                            rep.err(swhere, f"cites corpus://{h[:12]}… which resolves "
                                           "in no registered corpus")
                        elif isinstance(v, dict) and v.get("touch") and join.touch(h) \
                                and v["touch"] != join.touch(h):
                            rep.warn(swhere, f"corpus://{h[:12]}… touched since this "
                                            "source was verified — re-run `ath ledger "
                                            "verify`")
                else:
                    r = str(sentry["ref"])
                    rm = SOURCE_REF_RE.match(r)
                    if not rm:
                        rep.err(swhere, f"ref {r!r} is not a {{dataset}}/{{id}} citation")
                    elif rm.group(1) not in datasets:
                        rep.err(swhere, f"ref:// dataset {rm.group(1)!r} is not "
                                       "registered in the manifest's references:")
                    elif rm.group(2) is not None \
                            and rm.group(2) not in datasets[rm.group(1)].snapshots:
                        # *(17, §13.1)* the dataset is registered but the pinned
                        # tag is not one of its snapshots — a dangling pin. A pin
                        # into an unregistered dataset is caught by the branch
                        # above and never reaches here, so exactly one error.
                        rep.err(swhere, f"ref:// pin {rm.group(1)!r}@{rm.group(2)!r} is a "
                                       f"dangling pin: {rm.group(2)!r} is not a registered "
                                       f"snapshot tag on {rm.group(1)!r} (§13.1)")
                    dup = targets_seen.get(("ref", r))
                    if dup is not None:
                        rep.err(swhere, f"duplicate source for ref {r!r} (also {dup!r}) "
                                       "— one sources entry per target")
                    else:
                        targets_seen[("ref", r)] = skey

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
        # universal (§4.4): every {"entity": <id>} inside a claim value resolves —
        # the no-dangling rule extended to the roster shape structured-array
        # claims carry. Consumers' scope traversals follow these refs (§12), so
        # a dangle would silently truncate a compilation; it errors at its source.
        for eid in _iter_entity_refs(c.get("value")):
            if resolve_id(eid) is None:
                rep.err(where, f"dangling entity reference {eid!r} in claim value")
        # declared elements (§4.4): validate the objects inside a structured
        # array claim value against the field's element declarations — enum
        # `values` and typed `entity` `target`s; undeclared keys, missing keys,
        # and non-dict elements validate nothing (parse tolerantly).
        elements = fspec.get("elements")
        if isinstance(elements, dict) and isinstance(c.get("value"), list):
            for el in c["value"]:
                if not isinstance(el, dict):
                    continue
                for ekey, edecl in elements.items():
                    if not isinstance(edecl, dict) or ekey not in el:
                        continue
                    ev = el[ekey]
                    evalues = edecl.get("values")
                    if evalues is not None and str(ev) not in evalues:
                        rep.err(where, f"schema: {o.get('type')}.{pred} element {ekey!r} "
                                       f"value {ev!r} not among declared values {evalues}")
                    etarget = edecl.get("target")
                    if etarget is not None and isinstance(ev, str):
                        resolved = resolve_id(ev)
                        if resolved is not None:  # dangle owned by the universal rule
                            got = live_facts.get(resolved, {}).get("type")
                            admissible = (etarget if isinstance(etarget, list)
                                          else [etarget])
                            if got not in admissible:
                                rep.err(where, f"schema: {o.get('type')}.{pred} element "
                                               f"{ekey!r} {ev!r} is a {got!r}, declared "
                                               f"target {etarget!r}")

        fact_sources = o.get("sources") if isinstance(o.get("sources"), dict) else {}
        evs = c.get("evidence") or []
        if not evs:
            rep.err(where, "no evidence")
        hashes: set[str] = set()
        has_auth = False
        # *(1.8, §5.4)* the bar counts only verifiable-surface evidence: entries
        # citing a DEFERRED surface (a segments-surface record persisting no
        # segments yet — join.deferred_surface) are admissible but carry nothing
        # toward `confirmed`. `ref://` entries and environment-limited ops stay
        # countable — verifiable in principle. Offline (no live corpora) the
        # surface state is unknowable, so everything counts: fail open here,
        # because inventing bar failures a resolver never saw helps no one.
        countable_hashes: set[str] = set()
        auth_countable = False
        priv = c.get("sensitivity") == "private"
        for e in evs:
            if not isinstance(e, dict):
                rep.err(where, "evidence entries must be objects")
                continue
            unknown = set(e) - EVIDENCE_KEYS
            if "uri" in unknown:
                rep.err(where, "evidence entry carries the retired inline `uri` field "
                               "— migrate to the sources-table shape (source + "
                               "optional anchor)")
                unknown = unknown - {"uri"}
            if unknown:
                rep.err(where, f"unknown evidence keys {sorted(unknown)}")
            kind = e.get("kind")
            if kind not in EVIDENCE_KINDS:
                rep.err(where, f"evidence kind {kind!r} missing/invalid "
                               f"(authoritative|direct|incidental)")
            has_auth = has_auth or kind == "authoritative"
            entry_countable = True  # flipped only by a provably deferred surface
            anchor = e.get("anchor")
            if isinstance(anchor, str) and anchor.startswith("?"):
                rep.err(where, f"anchor {anchor!r} must not carry a leading '?'")
            skey = e.get("source")
            if not skey or not isinstance(skey, str):
                rep.err(where, "evidence entry has no source")
            elif skey not in fact_sources:
                rep.err(where, f"evidence.source {skey!r} does not resolve in this "
                               "fact's sources")
            else:
                used_sources.setdefault(f, set()).add(skey)
                # resolution and binding staleness already checked once, at
                # the sources-table pass above — here only the authentication
                # bar (distinct records) and per-claim privacy are derived
                entry = fact_sources[skey]
                if isinstance(entry, dict) and "record" in entry:
                    h = str(entry["record"])
                    if FULL_HASH_RE.match(h):
                        hashes.add(h)
                        if resolve_live and join.deferred_surface(h) is True:
                            entry_countable = False
                        else:
                            countable_hashes.add(h)
                        if resolve_live and join.resolves(h) and join.is_private(h):
                            priv = True
                elif isinstance(entry, dict) and "ref" in entry and anchor:
                    # §6.5 "Anchors are entry-level": a ref:// citation carries
                    # no span parameters — quotes verify against the adapter's
                    # rendered entry as a whole, so an `anchor` on evidence
                    # citing a ref source is a grammar error, not merely unchecked.
                    rep.err(where, f"evidence.source {skey!r} cites ref://"
                                   f"{entry['ref']} with anchor {anchor!r} — ref:// "
                                   "citations carry no span parameters (§6.5)")
            if entry_countable and kind == "authoritative":
                auth_countable = True
        if st == "confirmed" and evs \
                and not (auth_countable or len(countable_hashes) >= 2):
            if has_auth or len(hashes) >= 2:
                # the classic bar shape is met, but only by deferred surfaces —
                # name the actual defect so the fix (form, or demote) is legible
                rep.err(where, "fails the authentication bar for `confirmed`: its "
                               "bar-carrying evidence cites deferred surfaces — "
                               "records whose declared citation surface has no "
                               "persisted segments yet (§5.4, 1.8). Form the "
                               "records (the citations are standing demand) or "
                               "demote the claim")
            else:
                rep.err(where, "fails the authentication bar for `confirmed` (needs an "
                               "authoritative artifact or ≥2 independent records)")
        if priv:
            private_claims += 1
        c["_private"] = priv  # consumed by the file-level pass below, then dropped

    # sources entries no evidence references — a warning, never an error
    # (the table may legitimately hold a source ahead of the claim that uses it)
    for f, o in facts.items():
        if is_redirect(o):
            continue
        sources = o.get("sources")
        if not isinstance(sources, dict):
            continue
        used = used_sources.get(f, set())
        for skey in sources:
            if isinstance(skey, str) and skey not in used:
                rep.warn(rel(f), f"sources entry {skey!r} is not referenced by any "
                                 "evidence")

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
                elif rm.group(2) is not None \
                        and rm.group(2) not in datasets[rm.group(1)].snapshots:
                    rep.err(where, f"based_on ref:// pin {rm.group(1)!r}@{rm.group(2)!r} is "
                                   f"a dangling pin: {rm.group(2)!r} is not a registered "
                                   f"snapshot tag on {rm.group(1)!r} (§13.1)")
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
                pevs = proposes.get("evidence")
                if not pevs:
                    rep.warn(where, "proposes carries no evidence — promotion will need it")
                elif isinstance(pevs, list):
                    # proposes predates the fact it targets, so its evidence
                    # stays in the pre-reforge inline-`uri` shape (design
                    # corner: interpretations are unchanged) — `promote` hoists
                    # it into the target fact's sources table at landing time
                    for pe in pevs:
                        if not isinstance(pe, dict):
                            rep.err(where, "proposes evidence entries must be objects")
                            continue
                        pbad = set(pe) - PROPOSES_EVIDENCE_KEYS
                        if "source" in pbad or "anchor" in pbad:
                            rep.err(where, "proposes evidence carries a sources-table "
                                           "`source`/`anchor` key — proposes has no fact "
                                           "of its own to reference; keep the inline `uri` "
                                           "form until promotion")
                            pbad = pbad - {"source", "anchor"}
                        if pbad:
                            rep.err(where, f"proposes evidence unknown keys {sorted(pbad)}")
                        pkind = pe.get("kind")
                        if pkind not in EVIDENCE_KINDS:
                            rep.err(where, f"proposes evidence kind {pkind!r} "
                                           "missing/invalid (authoritative|direct|incidental)")
                        puri = str(pe.get("uri", ""))
                        pcm = CORPUS_URI_RE.match(puri)
                        prm = REF_URI_RE.match(puri)
                        if pcm:
                            if resolve_live and not join.resolves(pcm.group(1)):
                                rep.err(where, f"proposes evidence cites "
                                               f"corpus://{pcm.group(1)[:12]}… which "
                                               "resolves in no registered corpus")
                            owner = mirror_hash_owner.get(pcm.group(1))
                            if owner is not None:
                                odset, otag = owner
                                rep.warn(where, f"proposes evidence cites "
                                               f"corpus://{pcm.group(1)[:12]}…, the mirror "
                                               f"artifact for {odset!r}@{otag!r} — the "
                                               "mirror record's honest citation surface is "
                                               f"ref://{odset}/{{id}}, not the corpus hash "
                                               "directly (§6.5, §13.1)")
                        elif prm:
                            if "?" in prm.group(3):
                                # §6.5 "Anchors are entry-level": REF_URI_RE's id
                                # group is greedy (`(.+)$`), so a param'd uri
                                # still MATCHES — it doesn't fall through to the
                                # generic "not a citation" error below; the
                                # rejection has to be explicit here instead.
                                rep.err(where, f"proposes evidence ref:// uri "
                                               f"{puri!r} carries a span parameter — "
                                               "ref:// citations carry no anchors "
                                               "(§6.5)")
                            if prm.group(1) not in datasets:
                                rep.err(where, f"proposes evidence ref:// dataset "
                                               f"{prm.group(1)!r} is not registered")
                            elif prm.group(2) is not None \
                                    and prm.group(2) not in datasets[prm.group(1)].snapshots:
                                rep.err(where, f"proposes evidence ref:// pin "
                                               f"{prm.group(1)!r}@{prm.group(2)!r} is a "
                                               f"dangling pin: {prm.group(2)!r} is not a "
                                               f"registered snapshot tag on "
                                               f"{prm.group(1)!r} (§13.1)")
                        elif QUALIFIED_URI_RE.match(puri):
                            rep.err(where, f"proposes evidence uri {puri!r} uses the "
                                           "retired qualified form — cite bare "
                                           "corpus://{hash}")
                        else:
                            rep.err(where, f"proposes evidence uri {puri!r} is not a "
                                           "corpus:// or ref:// citation")
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
                        _, claim_fact, claim = claims_by_id[target]
                        claim_sources = claim_fact.get("sources") \
                            if isinstance(claim_fact.get("sources"), dict) else {}
                        current = canonical_claim_state(claim, claim_sources)
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
            if n.get("action") == "promote":
                m = CORPUS_URI_RE.match(str(n.get("record", "")))
                if not m or not m.group(2):
                    rep.err(where, "promote need requires a member corpus:// record "
                                   "(container hash + member address, e.g. "
                                   "corpus://<hash>?path=…)")
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


def _iter_strings(v: object):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _iter_strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _iter_strings(x)


def _iter_entity_refs(v: object):
    """Ids from every {"entity": <str>} object inside a claim value (§4.4).

    The roster shape (conv. 7): an act's or member's id rides an `entity` key.
    A non-string `entity` is ignored — parse tolerantly, validate nothing.
    """
    if isinstance(v, dict):
        e = v.get("entity")
        if isinstance(e, str):
            yield e
        for x in v.values():
            yield from _iter_entity_refs(x)
    elif isinstance(v, list):
        for x in v:
            yield from _iter_entity_refs(x)
