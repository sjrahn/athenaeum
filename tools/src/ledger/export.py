"""`ath ledger export` — the one-way, deterministic RDF projection of the
fact graph (spec/ledger.md §15.7), plus the conformance gate (ISO/IEC
21838-1 Annex D.5.1).

**Serialization form (a documented choice — §15.7 leaves it open).** Every
claim exports through the explicit **`rdf:reifies` + triple-term** pattern
(`_:r rdf:reifies <<( s p o )>> ; …props`) — never the `{| … |}` annotation
sugar. One form handles all three assertion classes uniformly: an asserted
claim gets the naked triple `s p o .` *plus* the reifier block; a
described-never-asserted claim gets *only* the reifier block; a presence
claim — which has no triple at all — gets a reifier-shaped individual
carrying no `rdf:reifies` (nothing to reify). Picking one form throughout
means the assertion map (below) is a single branch (emit the naked triple,
or don't) rather than two parallel serializers.

**Target editions pinned.** This module implements the triple-term +
`rdf:reifies` non-assertion pattern of **RDF 1.2 Concepts and Abstract
Syntax** and the Turtle-family syntax of **RDF 1.2 Turtle** — both W3C
Recommendations on the RDF-star/RDF 1.2 track. It was authored offline
against that track's late-2025 Recommendation text and does not itself fetch
or verify a live W3C TR date; the coordinator should confirm the exact
Recommendation date against https://www.w3.org/TR/ at the next reasoner/
interop check and update this paragraph to cite it precisely.

**IRI scheme** (documented once, used everywhere below):

- A fact (concept or edge) — `ledger://{id}`.
- A claim — `ledger://{id}#{short}` — a **fragment**, because a claim's own
  `{file-id}:{short}` form (spec §5.1) uses `:` as its separator and a `:`
  cannot introduce an IRI authority the way `//` does; the fragment keeps
  the claim addressable off its fact's own IRI without colliding with the
  URI grammar.
- A shared-tier type — `ledger://type/{name}`; a domain-minted type sense —
  `ledger://type/{domain-id}/{name}` (§15.4's qualified form).
- A predicate — `ledger://predicate/{name}`.
- A spine term — its **native** IRI where the registered dataset's adapter
  namespace is known (`_SPINE_IRI_PREFIXES`, confirmed against
  `refdata/adapters/bfo_2020.py` and `cco_release.py`, which resolve real
  IRIs down to a bare native id and keep only that bare id — so the full IRI
  is reconstructed here from the adapter's known namespace, not read back
  out of the adapter). Where the namespace isn't known, or the reference
  simply doesn't resolve (§15.2's own honestly-unverifiable outcomes), the
  declared literal is still emitted — as `ledger://spine/{dataset}/{ident}`
  — and recorded in `ExportReport.unverified_spine_refs`: never silently
  dropped.
- Every tooling-internal predicate/class this module itself mints (claim
  status, asof, presence, the reproducibility stamp's own fields, …) lives
  under `ledger://meta/{name}` — a namespace disjoint from both the
  `ledger://predicate/…` vocabulary the ledger's own schemas populate and
  the `ledger://type/…` one, so a consumer can tell "the ledger's own
  domain vocabulary" from "this exporter's plumbing" on sight.

**The record<->bytes joint** (§15.7: "generic dependence … no intermediate
pattern-individuals the ledger cannot address") is realized as the
reifier's own PROV-O derivation edge (`prov:wasDerivedFrom`/
`wasQuotedFrom`, below) — a claim (an information content entity) generically
depending on the bytes that ground it is exactly what that edge already
states; no separate blank-node pattern is minted for it.

**Determinism.** No clock, no randomness, no dict-iteration-order leakage:
every statement is collected into a `set[tuple[str, str, str]]` and the
whole export is one global `sorted()` pass before rendering — a single flat
list of `s p o .` lines (no predicate-object-list grouping) trades Turtle
idiom for a trivially-auditable, trivially-deterministic serializer. Any
timestamp in the output is instance data (a claim's own `asof`), never
`date.today()`/`now()`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from ath._version import SPEC_VERSION
from ath.manifest import Instance, Reference
from ledger import ontology
from ledger import tenancy as tenancy_mod
from ledger.corpora import CorpusJoin
from ledger.invariants import load_invariants
from ledger.model import (
    CLAIM_ID_RE,
    CLAIM_STATUSES,
    CORPUS_URI_RE,
    PRESENCE_VALUES,
    derived_uri,
    is_redirect,
    load_json_dir,
    load_lineage_rows,
)
from ledger.schemas import load_schemas
from ledger.scope import make_resolver
from refdata import ADAPTERS, adapter_available, materialize, resolve_adapter_name
from refdata import spine as spine_mod

__all__ = [
    "ExportError",
    "ExportReport",
    "GateResult",
    "export_ledger",
    "gate_owner_export",
    "run_conformance_gate",
    "spine_payloads",
]


class ExportError(RuntimeError):
    """A malformed export request (an unrecognized `--plane`) — never raised
    for ordinary content problems, which degrade to a report note or an
    unverified/skipped entry instead (§15.7's own partial-projection idiom)."""


# --------------------------------------------------------------------- IRIs

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
PROV = "http://www.w3.org/ns/prov#"
SH = "http://www.w3.org/ns/shacl#"
IAO_IS_ABOUT = "http://purl.obolibrary.org/obo/IAO_0000136"
IAO_TERM_REPLACED_BY = "http://purl.obolibrary.org/obo/IAO_0100001"

_LEDGER_SCHEME = "ledger://"
_META_NS = "ledger://meta/"

# Confirmed against refdata/adapters/bfo_2020.py (`_local_id`: the IRI's
# final `/`-segment under `http://purl.obolibrary.org/obo/`) and
# cco_release.py (`_CCO_NS`) — both adapters keep only the bare native id,
# so the full IRI is reconstructed here from each adapter's own documented
# namespace rather than read back out of a stored full IRI.
_SPINE_IRI_PREFIXES = {
    "bfo-2020": "http://purl.obolibrary.org/obo/",
    "cco-release": "https://www.commoncoreontologies.org/",
}

_SLUGGY = "-_."


def _q(s: str) -> str:
    return quote(str(s), safe=_SLUGGY)


def _ref(iri: str) -> str:
    return f"<{iri}>"


def fact_iri(fact_id: str) -> str:
    return f"{_LEDGER_SCHEME}{_q(fact_id)}"


def claim_iri(claim_id: str) -> str:
    m = CLAIM_ID_RE.match(claim_id)
    if not m:
        # Malformed claim id — check.py's business to have already flagged;
        # still never silently dropped here.
        return f"{_LEDGER_SCHEME}{_q(claim_id)}"
    fid, short = m.group(1), m.group(2)
    return f"{fact_iri(fid)}#{_q(short)}"


def type_iri(name: str, domain: str | None = None) -> str:
    if domain:
        return f"{_LEDGER_SCHEME}type/{_q(domain)}/{_q(name)}"
    return f"{_LEDGER_SCHEME}type/{_q(name)}"


def predicate_iri(name: str) -> str:
    return f"{_LEDGER_SCHEME}predicate/{_q(name)}"


def meta(name: str) -> str:
    return f"{_META_NS}{name}"


# ------------------------------------------------------------- literals

_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}
_ESC_RE = re.compile("|".join(re.escape(c) for c in _ESCAPES))
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _esc(s: str) -> str:
    return _ESC_RE.sub(lambda m: _ESCAPES[m.group(0)], s)


def _lit_str(value: object) -> str:
    return f'"{_esc(str(value))}"'


def _lit_date_ish(value: str) -> str:
    """`asof`/`period` tokens: a full YYYY-MM-DD types as `xsd:date`; a
    partial one (year, year-month, a range, a `~circa` prefix) stays a plain
    string literal rather than mistyping a partial/compound token."""
    if _DATE_RE.match(value):
        return f'"{value}"^^{_ref(XSD + "date")}'
    return _lit_str(value)


def _value_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _lit_str(value)
    # Structured (list/dict) claim values have no atomic RDF literal shape;
    # a full mapping (per-element individuals) is future work (§15.7 is a
    # partial projection by design) — compact deterministic JSON keeps the
    # content visible and round-trip-parseable rather than dropping it.
    return _lit_str(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


# --------------------------------------------------------------- planes


def _grants_for_plane(instance: Instance, plane: str) -> frozenset[str] | None:
    """None means the owner plane (no filter). Fails loudly on a malformed
    plane spec — an unknown *audience* name is not an error (`grants_for`'s
    own contract: it grants exactly `{public}`), matching the read surface's
    forgiving-audience-name behavior (Part I §5.1)."""
    if plane == "owner":
        return None
    if plane == "public":
        return frozenset({"public"})
    if plane.startswith("audience:"):
        return instance.grants_for(plane[len("audience:"):])
    raise ExportError(
        f"unknown plane {plane!r} — want 'owner', 'public', or 'audience:{{name}}' (§15.7)"
    )


# ------------------------------------------------------------- reports


@dataclass(frozen=True)
class ExportReport:
    plane: str
    spec_version: int
    instance_commit: str  # "" -> rendered/printed as "absent"
    spine: tuple[spine_mod.SpineBinding, ...]
    unverified_spine_refs: tuple[str, ...] = ()
    unexpressed_invariants: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    triples: int = 0


@dataclass(frozen=True)
class GateResult:
    """The conformance gate's outcome (§15.7, ISO/IEC 21838-1 Annex D.5.1) —
    a small dataclass so `ath ledger check` can consume it later without
    depending on this module's CLI-facing plumbing."""

    status: str  # "passed" | "failed" | "unverifiable"
    detail: str


def _git_head(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


# ----------------------------------------------------------- spine IRIs


def _spine_prefix(dataset: str, references: Sequence[Reference],
                  corpora_roots: Sequence[Path]) -> str | None:
    ref = next((r for r in references if r.dataset == dataset), None)
    if ref is None:
        return None
    adapter_name = ref.adapter
    if not adapter_name:
        try:
            from refdata import resolve_adapter_name

            adapter_name = resolve_adapter_name(ref, corpora_roots)
        except Exception:
            return None
    return _SPINE_IRI_PREFIXES.get(adapter_name)


def _resolve_parent_iri(
    parent: str, references: Sequence[Reference], corpora_roots: Sequence[Path],
    unverified: list[str],
) -> str:
    """One `extends:` parent (§15.3) -> its IRI. A spine-form reference
    (bears a `:`) resolves through `refdata.spine`; a plain name is another
    declared type/predicate, projecting as its own bare `ledger://type|
    predicate/…` IRI — chain composition is left to the reasoner's
    transitive `rdfs:subClassOf`/`subPropertyOf` closure, never flattened
    here (each type/predicate emits only its own immediate parent edge)."""
    if ":" not in parent:
        return type_iri(parent)
    try:
        term = spine_mod.resolve_term(parent, references, corpora_roots)
    except Exception as e:
        unverified.append(f"{parent}: {e}")
        return f"{_LEDGER_SCHEME}spine/{_q(parent)}"
    prefix = _spine_prefix(term.dataset, references, corpora_roots)
    if prefix is None:
        unverified.append(
            f"{parent}: resolved to {term.dataset}:{term.native_id} but its adapter's "
            "native IRI namespace is not one this exporter knows"
        )
        return f"{_LEDGER_SCHEME}spine/{_q(term.dataset)}/{_q(term.native_id)}"
    return prefix + term.native_id


# --------------------------------------------------------------- writer


class _Writer:
    """Collects `(subject, predicate, object)` string triples — every field
    already fully rendered (an IRI wrapped in `<>`, a compact fixed token
    like `a`/`owl:Class`, or a literal) — and renders them as one globally
    sorted, deduplicated, flat Turtle statement list (module docstring:
    determinism over grouping idiom)."""

    def __init__(self) -> None:
        self._stmts: set[tuple[str, str, str]] = set()

    def add(self, s: str, p: str, o: str) -> None:
        self._stmts.add((s, p, o))

    def render(self, header: Sequence[str]) -> str:
        lines = list(header)
        lines.append(f"@prefix rdf: <{RDF}> .")
        lines.append(f"@prefix rdfs: <{RDFS}> .")
        lines.append(f"@prefix owl: <{OWL}> .")
        lines.append(f"@prefix xsd: <{XSD}> .")
        lines.append(f"@prefix prov: <{PROV}> .")
        lines.append(f"@prefix sh: <{SH}> .")
        lines.append("")
        for s, p, o in sorted(self._stmts):
            lines.append(f"{s} {p} {o} .")
        return "\n".join(lines) + "\n"

    @property
    def count(self) -> int:
        return len(self._stmts)


# ------------------------------------------------------------- assertion

_ASSERT_STATUSES = frozenset({"confirmed", "provisional", "inferred"})


def _claim_asserts(status: object, commitment: str) -> bool:
    """The §15.7 assertion map: confirmed/provisional/inferred assert
    (unless the owning fact's domain commitment is `conditional`, in which
    case NOTHING from it ever asserts, on any plane, whatever its status);
    reported/disputed/conflicting are always described-only."""
    if commitment == "conditional":
        return False
    return status in _ASSERT_STATUSES


def _emit_claim_common(
    w: _Writer, reifier: str, claim: dict, sources: dict,
) -> None:
    status = claim.get("status")
    if isinstance(status, str) and status in CLAIM_STATUSES:
        w.add(_ref(reifier), _ref(meta("status")), _lit_str(status))
    asof = claim.get("asof")
    if isinstance(asof, str):
        w.add(_ref(reifier), _ref(meta("asof")), _lit_date_ish(asof))
    period = claim.get("period")
    if isinstance(period, str):
        w.add(_ref(reifier), _ref(meta("period")), _lit_date_ish(period))
    reasoning = claim.get("reasoning")
    if isinstance(reasoning, str):
        w.add(_ref(reifier), _ref(meta("reasoning")), _lit_str(reasoning))
    qualifiers = claim.get("qualifiers")
    if isinstance(qualifiers, dict):
        for k in sorted(qualifiers):
            w.add(_ref(reifier), _ref(predicate_iri(f"qualifier-{k}")),
                  _value_literal(qualifiers[k]))
    for e in claim.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        uri = derived_uri(sources, e.get("source"), e.get("anchor"))
        if uri is None:
            continue
        pred = PROV + ("wasQuotedFrom" if e.get("quote") else "wasDerivedFrom")
        w.add(_ref(reifier), _ref(pred), _ref(uri))


def _emit_claim(
    w: _Writer, fact_id: str, claim: dict, sources: dict, commitment: str,
    resolve_id, notes: list[str],
) -> None:
    cid = claim.get("id")
    predicate = claim.get("predicate")
    if not isinstance(cid, str) or not isinstance(predicate, str):
        return
    subj = fact_iri(fact_id)
    reifier = claim_iri(cid)
    pred_iri = predicate_iri(predicate)

    presence = claim.get("presence")
    if presence in PRESENCE_VALUES:
        # §5.5/§15.7: no triple exists to reify — a reifier-shaped
        # individual carrying the presence marker, never a naked triple.
        w.add(_ref(reifier), "a", _ref(meta("PresenceClaim")))
        w.add(_ref(reifier), _ref(meta("aboutFact")), _ref(subj))
        w.add(_ref(reifier), _ref(meta("onPredicate")), _ref(pred_iri))
        w.add(_ref(reifier), _ref(meta("presence")), _lit_str(presence))
        _emit_claim_common(w, reifier, claim, sources)
        return

    obj_id = claim.get("object")
    value = claim.get("value")
    gloss = None
    if isinstance(obj_id, str):
        resolved = resolve_id(obj_id)
        if resolved is None:
            notes.append(f"{cid}: object {obj_id!r} does not resolve — claim skipped")
            return
        triple_obj = _ref(fact_iri(resolved))
        if value is not None:
            gloss = value
    elif value is not None:
        triple_obj = _value_literal(value)
    else:
        notes.append(f"{cid}: neither object nor value — claim skipped")
        return

    triple_term = f"<<( {_ref(subj)} {_ref(pred_iri)} {triple_obj} )>>"
    w.add(_ref(reifier), _ref(RDF + "reifies"), triple_term)
    if _claim_asserts(claim.get("status"), commitment):
        w.add(_ref(subj), _ref(pred_iri), triple_obj)
    if gloss is not None:
        w.add(_ref(reifier), _ref(meta("gloss")), _value_literal(gloss))
    _emit_claim_common(w, reifier, claim, sources)


# --------------------------------------------------------------- vocab


def _emit_schema_vocab(
    w: _Writer, schemas: Mapping[str, dict],
    references: Sequence[Reference], corpora_roots: Sequence[Path], unverified: list[str],
) -> None:
    """Type-level `extends:` only — declares every schema's class and its
    immediate parent edge, regardless of live usage (declared vocabulary is
    part of the ledger's shape whether or not a fact currently exercises
    it). Predicate declarations are `_emit_predicate_decl`'s job, scoped to
    predicates actually used on the emitted (visible) claim set."""
    for name, schema in sorted(schemas.items()):
        if not isinstance(schema, dict):
            continue
        cls = type_iri(name)
        w.add(_ref(cls), "a", "owl:Class")
        ext = schema.get("extends")
        if isinstance(ext, str) and ext.strip():
            parent = _resolve_parent_iri(ext, references, corpora_roots, unverified)
            w.add(_ref(cls), "rdfs:subClassOf", _ref(parent))


def _owning_domain(name: str, closure: set[str], domains: Mapping[str, dict]) -> str | None:
    """Which domain in *closure* mints *name* in its OWN `ontology.types` —
    as opposed to merely inheriting it through an import (§15.4: the class
    identity is qualified by the MINTING domain, not every domain whose
    closure happens to see it). `ledger.ontology.ambiguous_type_names` is
    check's own gate against two closure members minting the same name; a
    clean ledger never reaches more than one hit here."""
    for did in sorted(closure):
        block = domains.get(did)
        if isinstance(block, dict) and name in (block.get("types") or {}):
            return did
    return None


def _emit_domain_type_vocab(
    w: _Writer, domains: Mapping[str, dict], visible_domain_ids: set[str],
    schemas: Mapping[str, dict], resolve_id,
    references: Sequence[Reference], corpora_roots: Sequence[Path],
    unverified: list[str], notes: list[str],
) -> None:
    """Every domain-minted type visible on this plane (§15.4/§15.7): its
    qualified class, plus its immediate `extends:` parent edge — resolved
    through the MINTING domain's own import closure via `ledger.ontology`
    (`import_closure` + `domain_types` + `type_chain`), never re-derived
    here, so a type inherited through an import chains exactly as
    `ledger.check`'s own ontology gate already verified it does."""
    owners = ontology.all_domain_minted_types(dict(domains))
    for tname, owner_ids in sorted(owners.items()):
        visible = [d for d in owner_ids if d in visible_domain_ids]
        if not visible:
            continue
        if len(visible) > 1:
            notes.append(
                f"domain type {tname!r} minted by more than one visible domain "
                f"({', '.join(visible)}) — an ambiguity check should already flag this; "
                "the export skips its class edge rather than guessing one"
            )
            continue
        did = visible[0]
        cls = type_iri(tname, domain=did)
        w.add(_ref(cls), "a", "owl:Class")
        closure = ontology.import_closure(did, dict(domains), resolve_id)
        merged = ontology.domain_types(closure, dict(domains))
        chain = ontology.type_chain(tname, dict(schemas), domain_type_decls=merged)
        if len(chain) < 2:
            continue
        parent = chain[1]
        if ":" in parent:
            parent_iri = _resolve_parent_iri(parent, references, corpora_roots, unverified)
        else:
            parent_owner = _owning_domain(parent, closure, domains)
            parent_iri = (type_iri(parent, domain=parent_owner) if parent_owner
                         else type_iri(parent))
        w.add(_ref(cls), "rdfs:subClassOf", _ref(parent_iri))


def _emit_predicate_decl(
    w: _Writer, name: str, schemas: Mapping[str, dict],
    references: Sequence[Reference], corpora_roots: Sequence[Path], unverified: list[str],
) -> None:
    w.add(_ref(predicate_iri(name)), "a", "rdf:Property")
    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        fspec = (schema.get("fields") or {}).get(name)
        if not isinstance(fspec, dict):
            continue
        fext = fspec.get("extends")
        if isinstance(fext, str) and fext.strip():
            parent = _resolve_parent_iri(fext, references, corpora_roots, unverified)
            w.add(_ref(predicate_iri(name)), "rdfs:subPropertyOf", _ref(parent))
            return


# ---------------------------------------------------------------- SHACL


def _emit_invariant_shapes(w: _Writer, invariants: list[dict], unexpressed: list[str]) -> None:
    for inv in invariants:
        inv_id = inv.get("id")
        constraint = inv.get("constraint")
        applies = inv.get("applies_to") if isinstance(inv.get("applies_to"), dict) else {}
        ftype, pred = applies.get("type"), applies.get("predicate")
        if not (isinstance(inv_id, str) and isinstance(ftype, str) and isinstance(pred, str)
                and constraint in ("cardinality", "unique")):
            if isinstance(inv_id, str):
                unexpressed.append(
                    f"{inv_id} ({constraint}): SHACL cannot express this constraint kind "
                    "as a plain node shape (§15.7: partial projection, IR stays authoritative)"
                )
            continue
        shape = f"{_LEDGER_SCHEME}shape/{_q(inv_id)}"
        prop = f"_:shp-{_q(inv_id)}"
        w.add(_ref(shape), "a", "sh:NodeShape")
        w.add(_ref(shape), "sh:targetClass", _ref(type_iri(ftype)))
        w.add(_ref(shape), "sh:property", prop)
        w.add(prop, "sh:path", _ref(predicate_iri(pred)))
        if constraint == "unique":
            w.add(prop, "sh:maxCount", "1")
        else:
            mn, mx = inv.get("min"), inv.get("max")
            if isinstance(mn, int):
                w.add(prop, "sh:minCount", str(mn))
            if isinstance(mx, int):
                w.add(prop, "sh:maxCount", str(mx))


# --------------------------------------------------------------- lineage


def _emit_lineage(
    w: _Writer, lineage_rows: dict[str, dict], visible_survivor,
) -> None:
    for old_id, row in sorted(lineage_rows.items()):
        survivor = row.get("to")
        if not isinstance(survivor, str) or not visible_survivor(survivor):
            continue
        w.add(_ref(fact_iri(old_id)), "owl:deprecated", "true")
        w.add(_ref(fact_iri(old_id)), _ref(IAO_TERM_REPLACED_BY), _ref(fact_iri(survivor)))


# --------------------------------------------------------------- roster


def _roster_entry_visible(
    uri: str, join: CorpusJoin, datasets: Mapping[str, Reference],
    grants: frozenset[str], declared: frozenset[str] | None,
) -> bool:
    m = CORPUS_URI_RE.match(uri)
    if not m:
        return True  # unresolvable/malformed — check's dangle to flag, not this filter's
    try:
        return tenancy_mod.evidence_entry_visible(
            {"record": m.group(1)}, join, datasets, grants, declared=declared)
    except Exception:
        return False  # fail closed


# ---------------------------------------------------------------- main


def export_ledger(
    ledger_root: Path,
    join: CorpusJoin,
    datasets: Mapping[str, Reference],
    instance: Instance,
    *,
    plane: str = "owner",
    corpora_roots: Sequence[Path] = (),
) -> tuple[str, ExportReport]:
    """The full §15.7 projection: `ledger_root`'s live facts (never
    interpretations — those are never exported, §1.3/§15.7) -> deterministic
    Turtle-family text + an `ExportReport`. `plane` is `"owner"` (default,
    unfiltered), `"public"`, or `"audience:{name}"` — anything else is
    `ExportError`. Fails closed throughout: any visibility check this
    function cannot compute answers "not visible" (never "visible")."""
    grants = _grants_for_plane(instance, plane)
    declared = instance.declared_tiers if grants is not None else None
    references = list(datasets.values())
    corpora_roots = list(corpora_roots)

    raw_facts, _ = load_json_dir(ledger_root, "facts/*/*.json")
    live = {p: f for p, f in raw_facts.items() if not is_redirect(f)}
    facts_by_id: dict[str, dict] = {}
    for f in live.values():
        fid = f.get("id")
        if isinstance(fid, str):
            facts_by_id[fid] = f
    lineage_rows, _ = load_lineage_rows(ledger_root)
    lineage = {k: v["to"] for k, v in lineage_rows.items()}
    resolve_id = make_resolver(facts_by_id, lineage)
    schemas, _ = load_schemas(ledger_root)
    domains = ontology.load_domains(facts_by_id)
    invariants, _ = load_invariants(ledger_root)

    notes: list[str] = []
    unverified: list[str] = []

    def _visible_fact(fact: dict) -> bool:
        if grants is None:
            return True
        try:
            return tenancy_mod.fact_visible(fact, join, datasets, grants, declared=declared)
        except Exception:
            return False

    def _visible_claim(fact: dict, claim: dict) -> bool:
        if grants is None:
            return True
        sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        try:
            return tenancy_mod.claim_visible(claim, sources, join, datasets, grants,
                                             declared=declared)
        except Exception:
            return False

    def _visible_survivor(survivor_id: str) -> bool:
        if grants is None:
            return True
        fact = facts_by_id.get(survivor_id)
        return fact is not None and _visible_fact(fact)

    # §15.7: "the `ontology:` declarations of domain concepts not visible to
    # the grant set are never emitted".
    visible_domains = {
        did: block for did, block in domains.items()
        if _visible_survivor(did)
    }

    w = _Writer()
    used_predicates: set[str] = set()
    used_shared_types: set[str] = set()

    for fid in sorted(facts_by_id):
        fact = facts_by_id[fid]
        if not _visible_fact(fact):
            continue
        ftype = fact.get("type")
        if not isinstance(ftype, str):
            continue
        domain_id = fact.get("domain")
        # Structural (not plane-gated): a fact's own type-resolution scope
        # (§15.4's import closure) is a fact about the ledger's vocabulary,
        # independent of whether THIS plane also emits the domain's own
        # `ontology:` declarations below — `domains` here is deliberately
        # the full, unfiltered set, matching `commitment_for_fact`'s own
        # unfiltered read just below.
        resolved_domain = resolve_id(domain_id) if isinstance(domain_id, str) else None
        minting_domain = None
        if resolved_domain:
            closure = ontology.import_closure(resolved_domain, domains, resolve_id)
            if ftype in ontology.domain_types(closure, domains):
                minting_domain = _owning_domain(ftype, closure, domains)
        cls_iri = (type_iri(ftype, domain=minting_domain) if minting_domain
                  else type_iri(ftype))
        if minting_domain is None:
            used_shared_types.add(ftype)
        w.add(_ref(fact_iri(fid)), "a", _ref(cls_iri))

        try:
            commitment = ontology.commitment_for_fact(fact, domains, resolve_id)
        except Exception:
            commitment = "conditional"  # uncertain commitment never asserts (fail closed)

        sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        for claim in fact.get("claims") or []:
            if not isinstance(claim, dict) or not _visible_claim(fact, claim):
                continue
            predicate = claim.get("predicate")
            if isinstance(predicate, str):
                used_predicates.add(predicate)
            _emit_claim(w, fid, claim, sources, commitment, resolve_id, notes)

        for entry in fact.get("artifacts") or []:
            if not isinstance(entry, dict):
                continue
            uri = entry.get("uri")
            if not isinstance(uri, str):
                continue
            if grants is not None and not _roster_entry_visible(uri, join, datasets, grants,
                                                                 declared):
                continue
            w.add(_ref(uri), _ref(IAO_IS_ABOUT), _ref(fact_iri(fid)))

    for name in sorted(used_predicates):
        _emit_predicate_decl(w, name, schemas, references, corpora_roots, unverified)
    for name in sorted(used_shared_types):
        if name not in schemas:
            w.add(_ref(type_iri(name)), "a", "owl:Class")  # schemaless — frontier, still a class
    _emit_schema_vocab(w, schemas, references, corpora_roots, unverified)
    _emit_domain_type_vocab(w, domains, set(visible_domains), schemas, resolve_id,
                            references, corpora_roots, unverified, notes)

    _emit_lineage(w, lineage_rows, _visible_survivor)
    unexpressed: list[str] = []
    _emit_invariant_shapes(w, invariants, unexpressed)

    spec_version = SPEC_VERSION
    instance_commit = _git_head(instance.root) or ""
    bindings = spine_mod.spine_bindings(references)

    stamp_subject = _ref(f"{_LEDGER_SCHEME}export")
    w.add(stamp_subject, _ref(meta("specVersion")), str(spec_version))
    w.add(stamp_subject, _ref(meta("instanceCommit")), _lit_str(instance_commit or "absent"))
    w.add(stamp_subject, _ref(meta("plane")), _lit_str(plane))
    for b in bindings:
        binding_label = f"{b.dataset}@{b.tag}:{b.artifact}"
        w.add(stamp_subject, _ref(meta("spineBinding")), _lit_str(binding_label))

    header = [
        "# Athenaeum ledger export (spec/ledger.md §15.7) — one-way, deterministic, regenerable.",
        "# Serialization: RDF 1.2 triple-term + rdf:reifies (see module docstring for the "
        "pinned target editions).",
        f"# spec_version={spec_version} instance_commit={instance_commit or 'absent'} "
        f"plane={plane}",
    ]
    text = w.render(header)
    report = ExportReport(
        plane=plane,
        spec_version=spec_version,
        instance_commit=instance_commit,
        spine=tuple(bindings),
        unverified_spine_refs=tuple(unverified),
        unexpressed_invariants=tuple(unexpressed),
        notes=tuple(notes),
        triples=w.count,
    )
    return text, report


# --------------------------------------------------------- conformance gate

_REASONER_ENV = "ATHENAEUM_REASONER"
_DEFAULT_REASONER_TEMPLATE = "robot merge {inputs} reason --reasoner ELK -o {output}"


def run_conformance_gate(
    owner_export_text: str,
    *,
    work_dir: Path,
    spine_paths: Sequence[Path] = (),
    reasoner_cmd: str | None = None,
) -> GateResult:
    """ISO/IEC 21838-1 Annex D.5.1 (§15.7): demonstrate the owner-plane
    export, combined with the registered spine (its mirrors materialized —
    `spine_paths`, when the caller has extracted them), is consistent — via
    whatever standard OWL 2 reasoner the verifying environment provides.

    Seam: `reasoner_cmd` (or the `ATHENAEUM_REASONER` env var) names a
    command **template** with `{inputs}` (one `--input PATH` per export/
    spine file, already shell-quoted), `{output}`, and `{export}` (the
    export file alone) substitution points; absent either, this looks for
    `robot` (ROBOT's `merge`+`reason`) on PATH. Neither present -> **honestly
    unverifiable**, never a silent pass (§13.2's idiom, generalized). Runs
    only over already-produced export artifacts — never in an authoring
    path — and never raises: a reasoner that can't be invoked, times out, or
    errors is unverifiable/failed, never a traceback escaping to the CLI.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    export_path = work_dir / "export.ttl"
    export_path.write_text(owner_export_text, encoding="utf-8")
    output_path = work_dir / "reasoned.owl"

    template = reasoner_cmd or os.environ.get(_REASONER_ENV)
    if template is None:
        if shutil.which("robot") is None:
            return GateResult(
                "unverifiable",
                "no OWL 2 reasoner available: 'robot' is not on PATH and "
                f"{_REASONER_ENV} is unset — the export is otherwise complete; "
                "conformance is honestly unverifiable in this environment (§15.7)",
            )
        template = _DEFAULT_REASONER_TEMPLATE

    inputs = " ".join(
        f"--input {shlex.quote(str(p))}" for p in (export_path, *spine_paths)
    )
    try:
        cmd_str = template.format(
            inputs=inputs, output=shlex.quote(str(output_path)),
            export=shlex.quote(str(export_path)),
        )
        args = shlex.split(cmd_str)
    except (ValueError, KeyError, IndexError) as e:
        return GateResult("unverifiable", f"malformed reasoner command template: {e}")

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return GateResult("unverifiable", f"reasoner invocation failed: {e}")

    if proc.returncode == 0:
        return GateResult("passed", proc.stdout.strip() or "reasoner reported the export "
                          "consistent with the registered spine")
    detail = proc.stderr.strip() or proc.stdout.strip() or f"reasoner exited {proc.returncode}"
    return GateResult("failed", detail)


def spine_payloads(
    references: Sequence[Reference], corpora_roots: Sequence[Path], work_dir: Path,
) -> tuple[list[Path], list[str]]:
    """Every registered spine dataset's (§15.2) reasoner-consumable ontology
    payload, extracted into `work_dir/{dataset}/` — what §15.7's gate needs
    to check the export against the registered spine's own axioms, not the
    export in isolation. Each step degrades to a report NOTE rather than a
    crash or a silent gap: an adapter that can't be resolved, isn't
    available in this environment, exposes no `ontology_payload_paths` (a
    plain reference adapter, same non-error reading as `SpineIncapableAdapter`
    §15.2), an unmaterialized mirror, or a corrupt archive all leave that one
    dataset out and say so — the gate still runs, honestly narrower."""
    paths: list[Path] = []
    notes: list[str] = []
    for ref in references:
        if not ref.spine:
            continue
        try:
            adapter_name = resolve_adapter_name(ref, corpora_roots)
        except Exception as e:
            notes.append(f"spine {ref.dataset}: adapter unresolved ({e}) — gate runs "
                        "without it, honestly narrower")
            continue
        if not adapter_available(adapter_name):
            notes.append(
                f"spine {ref.dataset}: adapter {adapter_name!r} unavailable in this "
                "environment — gate runs without it, honestly narrower"
            )
            continue
        adapter = ADAPTERS[adapter_name]
        payload_fn = getattr(adapter, "ontology_payload_paths", None)
        if payload_fn is None:
            notes.append(
                f"spine {ref.dataset}: adapter {adapter_name!r} exposes no "
                "ontology_payload_paths — gate runs without it, honestly narrower"
            )
            continue
        mirror_path = materialize(ref, ref.latest, corpora_roots)
        if mirror_path is None:
            notes.append(f"spine {ref.dataset}: mirror not materialized — gate runs "
                        "without it, honestly narrower")
            continue
        try:
            extracted = payload_fn(mirror_path, work_dir / ref.dataset)
        except Exception as e:
            notes.append(f"spine {ref.dataset}: payload extraction failed ({e}) — gate "
                        "runs without it, honestly narrower")
            continue
        paths.extend(extracted)
    return paths, notes


def gate_owner_export(
    owner_export_text: str,
    references: Sequence[Reference],
    corpora_roots: Sequence[Path],
    *,
    work_dir: Path,
    reasoner_cmd: str | None = None,
) -> tuple[GateResult, list[str]]:
    """The full §15.7 gate flow in one call: extract every registered
    spine's reasoner payload (`spine_payloads`) and run
    `run_conformance_gate` against the owner-plane export combined with
    them. Whenever any registered spine dataset had to be skipped, the
    returned `GateResult.detail` is amended with an explicit coverage
    caveat up front — a "passed" from this function never reads as an
    unqualified claim broader than what was actually checked (the spec's
    own "combined with the registered spine" language, §15.7). Returns the
    skip notes too, for the caller to surface individually."""
    spine_paths, notes = spine_payloads(references, corpora_roots, work_dir / "spine")
    result = run_conformance_gate(owner_export_text, work_dir=work_dir,
                                  spine_paths=spine_paths, reasoner_cmd=reasoner_cmd)
    total_spine = sum(1 for r in references if r.spine)
    if total_spine and notes:
        coverage = "partially" if spine_paths else "not"
        caveat = f"[spine {coverage} included — {len(notes)} dataset note(s) below] "
        result = GateResult(status=result.status, detail=caveat + result.detail)
    return result, notes
