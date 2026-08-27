"""The domain layer — concept-anchored vocabulary and membership (`spec/
ledger.md` §15.4-§15.5): domain concepts, import closures, commitment, and
the deterministic `isa:` subsumption test over declared `extends:` chains.

A domain is a concept first — this module never mints identity of its own,
it only resolves the `ontology:` block a concept MAY carry, and the
`domain:` membership field any fact MAY carry. Everything here is pure
graph-walking over already-loaded dicts; the checks that *validate* the
shapes below (well-formedness, cycles, shadowing, self-anchoring) live in
`ledger.check`'s Ontology block (§13.1), which calls these functions rather
than re-deriving the walks.

Two independent resolution styles show up, deliberately:

- `commitment_for_fact`/`import_closure` take a `resolve_id` callable
  (`ledger.scope.make_resolver`'s closure — lineage *and* liveness) because
  they look a domain id up in `domains`, a dict keyed by LIVE concept ids
  (`load_domains`'s own input, `facts_by_id`, is the live snapshot) — a
  dangling or retired domain reference must not silently resolve to some
  unrelated live entry.
- The `domain:` fact axis (`domain_axis_values`/`resolve_domain_operand`)
  takes a raw lineage map, exactly as `demands.py`'s `id:` condition treats
  its operands (`_resolve_operand`) — a rule may legitimately name a domain
  by an id that has since been renamed, and the axis should still match by
  canonicalizing through the lineage table alone, without requiring the
  result to currently live (evaluation never raises, §13.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ath.manifest import Reference

# The `ontology:` block's own shape (§15.4) — checked by `ledger.check`'s
# Ontology block, which owns every well-formedness error message; these are
# just the vocab this module and check.py share.
ONTOLOGY_KEYS = {"commitment", "imports", "types"}
DOMAIN_TYPE_KEYS = {"extends", "description"}
COMMITMENTS = {"real", "conditional"}

__all__ = [
    "COMMITMENTS",
    "DOMAIN_TYPE_KEYS",
    "ONTOLOGY_KEYS",
    "all_domain_minted_types",
    "ambiguous_type_names",
    "commitment_for_fact",
    "domain_axis_values",
    "domain_spine_references",
    "domain_type_chain_errors",
    "domain_types",
    "effective_schema",
    "import_closure",
    "import_cycle_errors",
    "isa_matches",
    "load_domains",
    "resolve_domain_operand",
    "resolve_domain_ref",
    "type_chain",
]


# --------------------------------------------------------------- domain concepts


def load_domains(facts_by_id: dict[str, dict]) -> dict[str, dict]:
    """Every domain concept in *facts_by_id* → {id: its `ontology:` block}
    (§15.4). A fact carrying a non-dict `ontology` is skipped here — check's
    structural pass flags the shape error; this is the resolved-view seam
    every other module (and every other check clause) reads."""
    return {
        fid: fact["ontology"]
        for fid, fact in facts_by_id.items()
        if isinstance(fact, dict) and isinstance(fact.get("ontology"), dict)
    }


def import_closure(domain_id: str, domains: dict[str, dict], resolve_id) -> set[str]:
    """*domain_id* + its `imports`, transitive (§15.4) — a domain is a
    concept, so `imports` entries are lineage-resolved (and liveness-
    checked) exactly like any other fact reference. Cycle-safe: a domain
    already in the closure is never re-expanded — the cycle itself is
    check's `import_cycle_errors` to report, not this function's to raise."""
    root = resolve_id(domain_id) or domain_id
    closure: set[str] = set()
    stack = [root]
    while stack:
        did = stack.pop()
        if did in closure:
            continue
        closure.add(did)
        block = domains.get(did)
        if not isinstance(block, dict):
            continue
        for imp in block.get("imports") or []:
            if isinstance(imp, str):
                rid = resolve_id(imp) or imp
                if rid not in closure:
                    stack.append(rid)
    return closure


def commitment_for_fact(fact: dict, domains: dict[str, dict], resolve_id) -> str:
    """"conditional" iff *fact*'s resolved `domain:` names a domain concept
    whose `ontology:` block declares `commitment: "conditional"`; "real"
    otherwise — no `domain:`, a dangling one, or one naming a fact carrying
    no `ontology:` block at all (§15.4's commitment default; the dangling/
    non-domain case is check's own error to surface elsewhere)."""
    dom = fact.get("domain")
    if not isinstance(dom, str) or not dom:
        return "real"
    live = resolve_id(dom)
    block = domains.get(live) if live else None
    if not isinstance(block, dict):
        return "real"
    return "conditional" if block.get("commitment") == "conditional" else "real"


def domain_types(closure: set[str], domains: dict[str, dict]) -> dict[str, dict]:
    """type name → declaration, merged from every domain in *closure*'s own
    `ontology.types` (§15.4). A same-named collision across two domains in
    one closure is never reachable in a clean ledger — that's check's
    `ambiguous_type_names` to report; this just merges, deterministically by
    sorted closure order."""
    out: dict[str, dict] = {}
    for did in sorted(closure):
        block = domains.get(did)
        if not isinstance(block, dict):
            continue
        types = block.get("types")
        if isinstance(types, dict):
            for tname, tdecl in types.items():
                if isinstance(tname, str) and isinstance(tdecl, dict):
                    out[tname] = tdecl
    return out


def all_domain_minted_types(domains: dict[str, dict]) -> dict[str, list[str]]:
    """type name → sorted domain ids that mint it, across EVERY domain
    concept regardless of import relationships (§15.4's "a fact whose type
    is domain-minted MUST carry domain:" is a global property of the name,
    not one scoped to a particular closure — a fact naming no domain at all
    can never legitimately carry a domain-minted type)."""
    owners: dict[str, list[str]] = {}
    for did, block in domains.items():
        if not isinstance(block, dict):
            continue
        for tname in block.get("types") or {}:
            if isinstance(tname, str):
                owners.setdefault(tname, []).append(did)
    return {t: sorted(ds) for t, ds in owners.items()}


def ambiguous_type_names(closure: set[str], domains: dict[str, dict]) -> dict[str, list[str]]:
    """type name → the (≥2) domains in *closure* that each mint it — a
    validation error (§15.4: "a name resolving ambiguously across the
    closure ... is a validation error")."""
    owners: dict[str, list[str]] = {}
    for did in sorted(closure):
        block = domains.get(did)
        if not isinstance(block, dict):
            continue
        for tname in block.get("types") or {}:
            if isinstance(tname, str):
                owners.setdefault(tname, []).append(did)
    return {t: ds for t, ds in owners.items() if len(ds) > 1}


def import_cycle_errors(domains: dict[str, dict], resolve_id) -> list[str]:
    """Every domain's `imports` form a DAG (§15.4) — white/gray/black DFS
    cycle detection, lineage-resolved. One message per domain found sitting
    on a cycle (a genuine cycle touches every domain on it, so each is
    reported from its own entry point rather than only the first found)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(domains, WHITE)
    errors: list[str] = []

    def visit(did: str, path: list[str]) -> None:
        if color.get(did) == BLACK:
            return
        if color.get(did) == GRAY:
            errors.append(f"ontology: import cycle — {' -> '.join([*path, did])}")
            return
        color[did] = GRAY
        block = domains.get(did) or {}
        for imp in block.get("imports") or []:
            if isinstance(imp, str):
                rid = resolve_id(imp) or imp
                visit(rid, [*path, did])
        color[did] = BLACK

    for did in sorted(domains):
        if color[did] == WHITE:
            visit(did, [])
    return errors


# ------------------------------------------------------------ schema resolution


def effective_schema(
    fact: dict, schemas: dict[str, dict], domain_schemas: dict[str, dict[str, dict]],
) -> dict:
    """The schema governing *fact*'s type (§15.4): its domain's own type
    sense (`schemas/{domain}/{type}.yaml`) when the fact carries `domain:`
    and that domain declares one for this type; the shared-tier schema
    otherwise. A domain sense is a DISTINCT declared shape, never merged
    with (or falling back to) the shared-tier schema of the same name."""
    ftype = str(fact.get("type"))
    dom = fact.get("domain")
    if isinstance(dom, str) and dom:
        dsch = domain_schemas.get(dom, {}).get(ftype)
        if isinstance(dsch, dict):
            return dsch
    return schemas.get(ftype) or {}


# --------------------------------------------------------------- isa / extends


def type_chain(
    ftype: str, schemas: dict[str, dict], domain_type_decls: dict[str, dict] | None = None,
) -> list[str]:
    """The declared is-a chain starting at *ftype*, walking `extends:`
    upward (§15.3, the `isa:` closure of §15.5): *domain_type_decls* — a
    fact's own domain closure's minted types (§15.4), when relevant — are
    consulted for a name before falling back to the shared-tier *schemas*,
    so a domain sense composes through its own package first; chains
    compose across the two exactly as §15.3 describes. Stops at the first
    spine-form reference (colon-bearing — the chain terminates there), when
    a name carries no further `extends:` of its own (frontier — the same
    non-error reading `schemas.extends_chain_errors` gives it), or on a
    would-be cycle (a name already visited — the cycle is a validation
    error elsewhere, never re-detected here as a silent loop)."""
    domain_type_decls = domain_type_decls or {}
    chain = [ftype]
    seen = {ftype}
    current = ftype
    while True:
        decl = domain_type_decls.get(current)
        if not isinstance(decl, dict):
            decl = schemas.get(current)
        if not isinstance(decl, dict):
            break
        ext = decl.get("extends")
        if not (isinstance(ext, str) and ext.strip()):
            break
        if ":" in ext:
            chain.append(ext)
            break
        if ext in seen:
            break
        chain.append(ext)
        seen.add(ext)
        current = ext
    return chain


def domain_type_chain_errors(domains: dict[str, dict], schemas: dict[str, dict]) -> list[str]:
    """Domain-minted types' own `extends:` chains (§15.3 applied to the
    §15.4 minted-type grammar): acyclic, resolving within the minting
    domain's own `ontology.types`, the shared tier, or terminating at a
    spine reference. Mirrors `schemas.extends_chain_errors`'s reading
    exactly — a chain that simply runs out at a frontier type is not an
    error; only a genuine cycle, or a name resolving nowhere, is."""
    errors: list[str] = []
    for did, block in sorted(domains.items()):
        if not isinstance(block, dict):
            continue
        types = block.get("types")
        if not isinstance(types, dict):
            continue
        for tname, tdecl in sorted(types.items()):
            if not isinstance(tdecl, dict):
                continue
            ext = tdecl.get("extends")
            if not (isinstance(ext, str) and ext.strip()):
                continue
            chain = [tname]
            current = ext
            while True:
                if ":" in current:
                    break
                if current in chain:
                    errors.append(f"ontology types ({did}): {tname!r} extends chain is "
                                  f"cyclic — {' -> '.join([*chain, current])}")
                    break
                decl = types.get(current)
                if not isinstance(decl, dict):
                    decl = schemas.get(current)
                if decl is None:
                    if current not in schemas and current not in types:
                        errors.append(
                            f"ontology types ({did}): {tname!r} extends {current!r} names "
                            "neither a declared type nor a spine reference (no colon, §15.3)"
                        )
                    break
                chain.append(current)
                nxt = decl.get("extends") if isinstance(decl, dict) else None
                if not (isinstance(nxt, str) and nxt.strip()):
                    break
                current = nxt
    return errors


def domain_spine_references(domains: dict[str, dict]) -> set[str]:
    """Every spine-form `extends:` a domain's minted types declare (§15.3,
    §15.4) — the domain-block analogue of `schemas.spine_references`."""
    refs: set[str] = set()
    for block in domains.values():
        if not isinstance(block, dict):
            continue
        for tdecl in (block.get("types") or {}).values():
            if isinstance(tdecl, dict):
                ext = tdecl.get("extends")
                if isinstance(ext, str) and ":" in ext:
                    refs.add(ext)
    return refs


def _spine_canonical(
    ref: str, references: Sequence[Reference], corpora_roots: Sequence[Path],
) -> tuple[str, str] | None:
    """*ref*'s `(dataset, native_id)` identity when the registered spine
    resolves it, else None — every resolution failure (grammar, missing
    registration, absent mirror, unavailable adapter) collapses to "no
    unification" here; `isa_matches` already tried literal comparison first,
    and `check`'s own Ontology block is where an unresolvable spine
    reference is separately reported as an error or honest unverifiable."""
    from refdata.errors import RefdataError
    from refdata.spine import resolve_term

    try:
        term = resolve_term(ref, references, corpora_roots)
    except RefdataError:
        return None
    return (term.dataset, term.native_id)


def isa_matches(
    fact: dict,
    operand: str,
    *,
    schemas: dict[str, dict],
    domains: dict[str, dict] | None = None,
    resolve_id=None,
    references: Sequence[Reference] = (),
    corpora_roots: Sequence[Path] = (),
) -> bool:
    """§15.5's `isa:` operator: does *fact*'s type equal *operand*, or reach
    it through declared `extends:` chains — a deterministic graph walk over
    the shared-tier *schemas* plus, when *fact* carries `domain:`, its
    resolved domain's import-closure minted types? No reasoner, ever.

    *operand* names a shared-tier type or a spine class (label or native
    id). Comparison tries literal string equality against every element of
    the declared chain first; where that misses and *operand* is spine-form
    (colon-bearing), it unifies against each spine-form chain element via
    `refdata.spine.resolve_term` — so `isa: "cco:Material Artifact"` matches
    a chain declaring `cco:ont00000995` and vice versa wherever the mirrors
    are materialized (that pair is CCO v2.2's artifact root: label-form
    references use the release's actual `rdfs:label`, and there is no bare
    "Artifact" class in v2.2). Where they aren't, unification simply misses (nothing
    silently wrong: check's Ontology block separately reports an
    unresolvable spine reference)."""
    ftype = str(fact.get("type"))
    dtypes: dict[str, dict] = {}
    if domains and resolve_id is not None:
        dom = fact.get("domain")
        if isinstance(dom, str) and dom:
            live_dom = resolve_id(dom)
            if live_dom:
                closure = import_closure(live_dom, domains, resolve_id)
                dtypes = domain_types(closure, domains)
    chain = type_chain(ftype, schemas, dtypes)
    if operand in chain:
        return True
    if ":" not in operand:
        return False
    op_key = _spine_canonical(operand, references, corpora_roots)
    if op_key is None:
        return False
    for elem in chain:
        if ":" in elem and _spine_canonical(elem, references, corpora_roots) == op_key:
            return True
    return False


# ------------------------------------------------------------- the domain: axis


def resolve_domain_ref(ref: object, lineage: dict[str, str]) -> str:
    """One domain reference — a fact's own `domain:` value, or a `domain:`
    condition's `equals`/`in` operand — through at most one lineage hop
    (§4.1): the same non-liveness-checked canonicalization `id:` operands
    get (`demands._resolve_operand`), which the `domain:` axis (§15.5)
    mirrors exactly."""
    return lineage.get(str(ref), str(ref))


def domain_axis_values(fact: dict, lineage: dict[str, str] | None = None) -> list[str]:
    """The `domain:` fact axis's addressable value (§15.5) — 0- or 1-element,
    matching the `_field_values`/`_fact_values` shape every other axis
    already returns (missing-domain is simply an empty list — missing-is-
    false throughout the operator grammar)."""
    d = fact.get("domain")
    if not isinstance(d, str) or not d:
        return []
    return [resolve_domain_ref(d, lineage or {})]


def resolve_domain_operand(op: object, lineage: dict[str, str] | None = None) -> object:
    """An `equals`/`in` operand under the `domain:` axis, lineage-resolved
    exactly as an `id:` operand is (§14, §15.5); `glob`/`matches`/`exists`
    operands pass through unchanged — literal, exactly as `id:` treats
    them."""
    lineage = lineage or {}
    if isinstance(op, dict) and len(op) == 1:
        (k, arg), = op.items()
        if k == "equals":
            return {k: resolve_domain_ref(arg, lineage)}
        if k == "in" and isinstance(arg, list):
            return {k: [resolve_domain_ref(a, lineage) for a in arg]}
        return op
    if isinstance(op, dict):
        return op
    return resolve_domain_ref(op, lineage)  # bare scalar — implicit equals
