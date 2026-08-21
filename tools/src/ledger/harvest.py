"""Harvest — mechanical concept/roster/claim minting (`spec/ledger.md` §10).

A harvest run is a pure function of the corpora's mechanical record facts:
strip every `provenance: auto` concept file, roster entry, and claim; sweep
the registered corpora; re-mint from the rules. Asserted content always
wins — a human edit removed the `auto` mark, and the harvester never touches
it again; auto roster/claims converge onto asserted concepts by id.

Fact base per record: `mime`, `origin.uri/host/path/fragment/query.<k>`,
`origin.id`, any stored origin-block field (`origin.<field>`); the
`classify_when` operator grammar carried over from ATH-CORPUS 1.0
(equals/in/glob/matches/exists; all_of/any_of/none_of; missing-fact-is-false).
Body content is permanently excluded.

Minted ids MUST be keyed by origin-native identity (the record-shadow
prohibition): templates interpolate origin facts — `{origin.path[2]}`,
`{origin.handle}` — slugified; a rule whose id template names no origin fact
is refused at load.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import yaml

from ledger.corpora import RegisteredCorpus
from ledger.model import ensure_source
from ledger.scope import op_matches

RULE_KEYS = {"id", "description", "match", "mint"}
MINT_KEYS = {"concept", "roster", "claims"}
CONCEPT_MINT_KEYS = {"id", "type", "name"}
_OPS = {"equals", "in", "glob", "matches", "exists"}
_GROUPS = {"all_of", "any_of", "none_of"}
_TEMPLATE_RE = re.compile(r"\{([a-z0-9_.]+)(?:\[(\d+)\])?(?:\|([a-z0-9_.]+))?\}")


class HarvestError(RuntimeError):
    pass


def load_rules(ledger_root: Path) -> list[dict]:
    rules = []
    base = ledger_root / "harvest"
    if not base.is_dir():
        return rules
    for f in sorted(base.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise HarvestError(f"{f.name}: top level must be a mapping")
        if data.get("id") != f.stem:
            raise HarvestError(f"{f.name}: id {data.get('id')!r} != filename stem")
        unknown = set(data) - RULE_KEYS
        if unknown:
            raise HarvestError(f"{f.name}: unknown keys {sorted(unknown)}")
        mint = data.get("mint") or {}
        if set(mint) - MINT_KEYS:
            raise HarvestError(f"{f.name}: unknown mint keys {sorted(set(mint) - MINT_KEYS)}")
        concept = mint.get("concept")
        if concept:
            if set(concept) - CONCEPT_MINT_KEYS:
                raise HarvestError(f"{f.name}: unknown concept keys")
            # the record-shadow prohibition: a minted id must be keyed by
            # origin-native identity, never record identity
            if not _TEMPLATE_RE.search(str(concept.get("id", ""))):
                raise HarvestError(
                    f"{f.name}: concept id {concept.get('id')!r} interpolates no origin "
                    "fact — hash-only rules may roster/claim but never mint (§10)"
                )
            for m in _TEMPLATE_RE.finditer(str(concept["id"])):
                for key in (m.group(1), m.group(3)):
                    if key is not None and not key.startswith("origin."):
                        raise HarvestError(
                            f"{f.name}: concept id may only be keyed by origin "
                            f"facts, got {{{key}}}"
                        )
        rules.append(data)
    return rules


# ------------------------------------------------------------------ fact base


def record_facts(post) -> dict[str, object]:
    """The mechanical fact base of one record (see module docstring)."""
    from corpus import records

    facts: dict[str, object] = {}
    mime = records.media_type_for(post)
    if mime:
        facts["mime"] = mime
    origin = next(records.iter_origin_blocks(post), None)
    if origin:
        # block shape: {id: <overlay id>, subtype: …, fields: {uri, snapshot, …}}
        if origin.get("id"):
            facts["origin.id"] = origin["id"]
        if origin.get("subtype"):
            facts["origin.subtype"] = origin["subtype"]
        for k, v in (origin.get("fields") or {}).items():
            if v is None:
                continue
            facts[f"origin.{k}"] = v
        uri = facts.get("origin.uri")
        if isinstance(uri, list):
            uri = uri[0] if uri else None
        if isinstance(uri, str) and uri:
            facts["origin.uri"] = uri
            parts = urlsplit(uri)
            facts["origin.host"] = parts.netloc.lower()
            # fragment routers (my.alldata.com/#/vehicle/…) put the path in the
            # fragment; expose the joined path so path[i] indexing sees it all
            frag = parts.fragment
            path = parts.path + ("/" + frag.lstrip("/") if frag else "")
            facts["origin.path"] = path
            if frag:
                facts["origin.fragment"] = frag
            for k, v in parse_qsl(parts.query, keep_blank_values=True):
                facts[f"origin.query.{k}"] = v
    return facts


def _fact_values(facts: dict, name: str) -> list[str]:
    v = facts.get(name)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def match(predicate: dict, facts: dict) -> bool:
    """The classify_when grammar: fact→{op: arg} tests joined by AND;
    all_of/any_of/none_of group sub-predicates; missing fact is false.

    Operator evaluation itself is `scope.op_matches` — the one §10
    implementation shared with scope evaluation and the demand engine
    (§10, "Beyond the finding cap") — with its ValueError (unknown operator,
    or a `matches` pattern `compile_matches` refuses) wrapped into this
    module's own `HarvestError` at this boundary."""
    for key, spec in (predicate or {}).items():
        if key in _GROUPS:
            subs = spec if isinstance(spec, list) else [spec]
            results = [match(s, facts) for s in subs]
            ok = {"all_of": all(results), "any_of": any(results),
                  "none_of": not any(results)}[key]
            if not ok:
                return False
            continue
        if not isinstance(spec, dict):
            spec = {"equals": spec}
        values = _fact_values(facts, key)
        for op, arg in spec.items():
            if op not in _OPS:
                raise HarvestError(f"unknown operator {op!r} on {key!r}")
            try:
                matched = op_matches(op, arg, values)
            except ValueError as e:
                raise HarvestError(f"{key!r}: {e}") from e
            if not matched:
                return False
    return True


# ------------------------------------------------------------------ templating


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def expand(template: str, facts: dict, *, slug: bool) -> str | None:
    """Interpolate `{fact}` / `{fact[i]}` / `{a|b}` (first non-empty wins).
    Returns None when any interpolation has no value (the rule skips)."""
    out: list[str] = []
    pos = 0
    for m in _TEMPLATE_RE.finditer(template):
        out.append(template[pos:m.start()])
        pos = m.end()
        value = None
        for name in (m.group(1), m.group(3)):
            if not name:
                continue
            values = _fact_values(facts, name)
            if name.endswith(".path") and m.group(2) is not None and values:
                segs = [s for s in values[0].split("/") if s]
                idx = int(m.group(2))
                value = segs[idx - 1] if 1 <= idx <= len(segs) else None
            elif values:
                value = values[0] if len(values) == 1 else None  # lists never key
            if value:
                break
        if not value:
            return None
        out.append(_slug(value) if slug else value)
    out.append(template[pos:])
    return "".join(out)


# ------------------------------------------------------------------ the run


@dataclass
class HarvestRun:
    minted: int = 0
    rostered: int = 0
    claimed: int = 0
    stripped_files: int = 0
    stripped_entries: int = 0
    matched_records: int = 0
    notes: list[str] = field(default_factory=list)


def run_harvest(ledger_root: Path, corpora: list[RegisteredCorpus]) -> HarvestRun:
    import json

    from corpus import records

    rules = load_rules(ledger_root)
    run = HarvestRun()

    # ---- strip: auto files die; auto roster entries/claims leave asserted files
    for f in sorted(ledger_root.glob("facts/*/*.json")):
        try:
            fact = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fact.get("provenance") == "auto":
            f.unlink()
            run.stripped_files += 1
            continue
        dirty = False
        roster = fact.get("artifacts")
        if isinstance(roster, list):
            kept = [e for e in roster
                    if not (isinstance(e, dict) and e.get("provenance") == "auto")]
            if len(kept) != len(roster):
                run.stripped_entries += len(roster) - len(kept)
                fact["artifacts"] = kept
                if not kept:
                    del fact["artifacts"]
                dirty = True
        claims = fact.get("claims")
        stripped_claims = False
        if isinstance(claims, list):
            kept = [c for c in claims
                    if not (isinstance(c, dict) and c.get("provenance") == "auto")]
            if len(kept) != len(claims):
                run.stripped_entries += len(claims) - len(kept)
                fact["claims"] = kept
                if not kept:
                    del fact["claims"]
                dirty = stripped_claims = True
        # an auto claim's evidence was the only thing keeping its sources-table
        # entry alive — prune what stripping just orphaned (re-minted below,
        # possibly under a fresh key: keys are local and meaningless, §amendment)
        if stripped_claims and isinstance(fact.get("sources"), dict):
            still_used = {
                e.get("source") for c in fact.get("claims") or [] if isinstance(c, dict)
                for e in c.get("evidence") or [] if isinstance(e, dict)
            }
            pruned = {k: v for k, v in fact["sources"].items() if k in still_used}
            if len(pruned) != len(fact["sources"]):
                if pruned:
                    fact["sources"] = pruned
                else:
                    del fact["sources"]
                dirty = True
        if dirty:
            f.write_text(json.dumps(fact, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")

    if not rules:
        run.notes.append("no harvest rules declared")
        return run

    # ---- sweep: deterministic order (corpus name, then record path)
    by_id: dict[str, Path] = {p.stem: p for p in ledger_root.glob("facts/*/*.json")}
    pending: dict[str, dict] = {}  # minted-this-run concepts, by id

    def load_target(cid: str) -> dict | None:
        if cid in pending:
            return pending[cid]
        if cid in changed_existing:
            return changed_existing[cid]
        p = by_id.get(cid)
        if p is None:
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def save_target(cid: str, fact: dict) -> None:
        if cid in pending:
            return  # written at the end
        p = by_id[cid]
        p.write_text(json.dumps(fact, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    changed_existing: dict[str, dict] = {}

    for corpus in sorted(corpora, key=lambda c: c.name):
        if not corpus.available:
            run.notes.append(f"{corpus.name}: not on disk — skipped")
            continue
        for path in records.iter_record_paths(corpus.root):
            try:
                post = records.load(path)
            except Exception:
                continue  # parse tolerantly
            facts = None
            for rule in rules:
                if facts is None:
                    facts = record_facts(post)
                if not match(rule.get("match") or {}, facts):
                    continue
                run.matched_records += 1
                mint = rule.get("mint") or {}
                spec = mint.get("concept")
                cid = None
                if spec:
                    cid = expand(str(spec["id"]), facts, slug=True)
                    if not cid:
                        continue  # identity fact missing → this record can't key
                    target = load_target(cid) if cid in by_id or cid in pending \
                        else None
                    if target is None and cid not in by_id:
                        name = expand(str(spec.get("name", cid)), facts, slug=False) or cid
                        target = {"id": cid, "type": str(spec["type"]), "name": name,
                                  "provenance": "auto"}
                        pending[cid] = target
                        run.minted += 1
                    elif target is None:
                        continue
                else:
                    continue  # roster/claim-only rules need a static target (future)
                hash_ = str(post.metadata.get("id", path.stem))
                uri = f"corpus://{hash_}"
                roster_specs = mint.get("roster") or []
                if roster_specs:
                    roster = target.setdefault("artifacts", [])
                    for rs in roster_specs:
                        entry = {"uri": uri, "role": str((rs or {}).get("role", "documents")),
                                 "provenance": "auto"}
                        if not any(x.get("uri") == uri and x.get("role") == entry["role"]
                                   for x in roster if isinstance(x, dict)):
                            roster.append(entry)
                            run.rostered += 1
                for cs in mint.get("claims") or []:
                    pred = str((cs or {}).get("predicate", "")).strip()
                    value = expand(str(cs.get("value", "")), facts, slug=False)
                    if not pred or value is None:
                        continue
                    claims = target.setdefault("claims", [])
                    existing = next(
                        (c for c in claims if isinstance(c, dict)
                         and c.get("predicate") == pred and c.get("value") == value), None)
                    if existing is not None:
                        # only mint/reuse a sources entry when it will actually
                        # be referenced — an asserted claim discards `ev`
                        # entirely, and must not leave an orphaned source behind
                        if existing.get("provenance") == "auto":
                            skey = ensure_source(target, record=hash_)
                            if not any(e.get("source") == skey
                                       for e in existing.get("evidence", [])):
                                existing["evidence"].append(
                                    {"source": skey,
                                     "kind": str(cs.get("evidence_kind", "direct"))})
                        continue  # asserted claim wins; auto converges as evidence
                    skey = ensure_source(target, record=hash_)
                    ev = {"source": skey, "kind": str(cs.get("evidence_kind", "direct"))}
                    short = _slug(pred)
                    if any(isinstance(c, dict) and c.get("id") == f"{cid}:{short}"
                           for c in claims):
                        short = f"{short}-{hash_[:8]}"
                    claims.append({
                        "id": f"{cid}:{short}", "predicate": pred, "value": value,
                        "status": "provisional", "provenance": "auto",
                        "evidence": [ev],
                    })
                    run.claimed += 1
                if cid in by_id:
                    changed_existing[cid] = target

    for cid, fact in changed_existing.items():
        save_target(cid, fact)
    for cid, fact in pending.items():
        p = ledger_root / "facts" / fact["type"] / f"{cid}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(fact, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    return run
