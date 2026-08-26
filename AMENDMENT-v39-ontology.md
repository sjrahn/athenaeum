# Amendment draft — v39: The spine, the anchored domains, and the projection

**Status: DRAFT for owner review — not yet law.** Folding this in is a normative
change (owner-gated, Part I §8): version 38 → 39, one bump across all four
parts, though only Part III and Part I carry text changes. This document is
fold-ready: §1–§2 are complete normative text (a new Part III §15 and §5.5),
§3 is the exact edit list for existing Part III sections (old → new), §4 the
Part I edits, §5 the Part II edits, §6 the CHANGELOG entry, §7 the migration
story with measured cost, §8 the enforcement/guidance sweep checklist — the
three things Part I §8 requires landing together.

**Basis.** The banked rulings of 2026-08-25 (BFO as TLO with the
conditional-ontology pattern; vendored BFO-2020 tables; CCO v2.2 as the
mid-level spine; OWL-reasoner conformance gate; all-in migration; no
cross-module merge, hub-and-spoke topology; novalue/somevalue adopted;
property-grade constraints; deletion-reason enum; coarse-selector/refinedBy
adoption) — grounded in the "Grounding the Ledger" report — plus the
**concept-anchored domain** ruling that followed the report's soundness
review: every domain ontology is anchored on a concept; the slug is the
namespace; no parallel module tree exists. One banked ruling is **superseded
by owner direction in this draft's revision**: the spine is no longer
*vendored by the distribution* — it is **instance-registered reference data**
(§15.2), captured and pinned like any reference dataset, updatable and even
forkable independently of any tooling release; the distribution ships only
the format adapters. The same ruling extends to the one other data-like
payload the tooling carried: the SingleFile capture-engine bundle leaves the
tooling tree and becomes an instance-registered **asset** (Part I §2.3
`assets:`, Part II §12.3.6 — §5 below), resolved by hash through custody and
stamped into capture provenance.

**Deliberately excluded from this amendment** (each its own follow-up, none
blocked by this one): the Part II semi-diplomatic terminology and the
per-segment transcription-mode sketch (corpus-side, still exploratory); the
OAIS declaratory items (Designated Community, Representation Information,
Succession Plan — a Part I/II writing exercise); the sweep-backed
negative-evidence citation grammar (stays the named Part III §6 extension
point — presence claims cite ordinary positive evidence until a real claim
demands the sweep grammar); nanopublication and Web Annotation renderings
(mechanical futures of the projection, never law); trusty-URI alignment
(ruled optional-at-most); ISO 21838-1 D.2(2b) defined-class declarations
(deferred to Part I §9 until a real type needs one).

**Naming decisions flagged for owner veto** (each used consistently below;
any veto is a find-and-replace before folding):

- **`extends:`** for the is-a chain key — not `anchors:`, which would collide
  with the evidence entry's `anchor` field. "Extension" is also ISO 21838-1's
  own word for the relation (Annex D: conformance through extension).
- **`ontology:`** for the block a concept carries; a concept carrying one is a
  **domain concept**; the fact-level membership field is **`domain:`**.
- **`presence: "none" | "some"`** for the novalue/somevalue claim shapes.
- **`isa:`** for the opt-in subsumption operator.
- **`requires_domain: true`** on a shared schema (distinct from the `domain:`
  key that names a domain-sense schema's owner).
- Lineage `reason` enum starts `merged | renamed` — grown by amendment
  (no `split` machinery exists yet; the organic rule applies).
- **`spine: true`** as the config marker admitting a reference dataset as an
  extension-chain root (Part I §2.3).
- **`assets:`** as the config section for instance-registered tool assets
  (the SingleFile bundle its first population), and **`snapshot_engine:`** as
  the capture-sidecar/origin field recording which build produced a snapshot.

---

## 1. Part III — new §15 (insert after §14, before Appendix A)

```markdown
## 15. Ontology — the spine and the anchored domains

### 15.1 The two tiers and the spine

The ledger's vocabulary (§8) carries an ontological backbone. Every concept
and edge type in use ultimately **extends** the **registered spine** — the
BFO-2020 top-level ontology and the Common Core Ontologies mid-level, held by
the instance as registered reference datasets (§15.2) — and vocabulary lives
in exactly two tiers:

- **The shared tier** — the instance-general vocabulary: every type,
  predicate, schema, and registered term as this specification already defines
  them. Storage is unchanged (`schemas/{type}.yaml`, `VOCAB.md`); the tier
  gains extension chains into the spine (§15.3).
- **Domains** — concept-anchored vocabulary: a concept MAY carry an
  **`ontology:` block**, making it a **domain concept** that scopes vocabulary
  and membership to itself (§15.4).

Principles, each load-bearing:

- **One substrate.** A domain is a concept. Domain identity is concept
  identity — the slug is the namespace, unique by construction (§4.1), carried
  by the lineage map through merges and renames, addressable by wikilink and
  `ledger://` like everything else. There is no module registry, no parallel
  ontology tree, and no new identity grammar anywhere in this section.
- **A domain is a real thing.** A domain concept is an ordinary concept first
  (§4): a narrative universe, a franchise, a show, a system — something
  materialized because it was recognized, carrying its own claims and roster.
  A concept minted solely to house vocabulary is the bucket §4.2 prohibits;
  discipline-level vocabulary ("fiction", "automotive") belongs to the shared
  tier, never to an invented topic concept.
- **Organic, with promotion.** Vocabulary mints where evidence needs it (§8):
  domain-specific terms mint in their domain; what recurs across domains
  promotes to the shared tier. A domain that outgrows its first anchor
  re-seats to a better concept mechanically (§15.4). Nothing is pre-built.
- **Conformance is ISO/IEC 21838-1 Annex D.** Unique extension chains (D.2)
  compose transitively through the spine (D.3) and are demonstrated by a
  standard reasoner over the export (D.5.1 — §15.7). The chain declarations
  are data; the lint is graph traversal; the reasoner runs at check time,
  never at runtime.

### 15.2 The registered spine

The spine is **instance data, not distribution code**. Each spine source —
BFO-2020 and the CCO release, per the adoption rulings — is a **reference
dataset** (§6.5): its release bytes are an ordinary mirror artifact in the
corpus (a terminal-contract record — capture provenance, content-addressed
integrity, custody routes, and gc protection with no new machinery),
registered in the instance config (Part I §2.3) with tag-keyed snapshots and a
declared `latest:`, and marked **`spine: true`** — the flag that admits it as
an extension-chain root. The distribution ships the **adapters** — the format
knowledge for reading a BFO-2020 table set or a CCO release tree — and
nothing else: which releases an instance trusts, at which bytes, is the
instance's own declared, pinned, visible-diff state, updated independently of
any tooling release.

- **Reference form.** Declarations reference spine terms as `{dataset}:{id}`
  — the registered dataset's name plus the term's native identity
  (`cco:ont00001017`) — or its **label** where the label is unique in the
  resolved release (`cco:Artifact`, `bfo:site`); tooling surfaces the
  resolved pair, and the derived form is an ordinary `ref://{dataset}/{id}`
  (§6.5). **A reference that does not resolve against the resolved release is
  a validation error** — never a warning: nothing human-checks an opaque IRI
  by eye, and a plausible fabricated reference is precisely the failure class
  this gate exists to stop. Where the mirror bytes are not locally
  materialized, resolution reports **honestly unverifiable**, never failure
  (the §6.5 idiom — CI holds the mirrors).
- **Always bare — one spine version per instance.** Extension chains resolve
  at each spine dataset's `latest` only; the per-citation `@{tag}` pin (§6.5)
  is deliberately not admitted in `extends:` — per-type pins would mix spine
  versions inside one ontology, which the conformance gate (§15.7) cannot
  make coherent. The instance-wide pin point is the registration itself: the
  tag names the release, the snapshot's artifact blake3 is the true pin.
- **Updating is a registration diff.** Register the new snapshot, bump
  `latest` — one visible config diff — and validation re-resolves every
  chain: a reference the new release no longer carries **errors** loudly; one
  resolving to a term the release marks deprecated **warns**; and the
  conformance gate (§15.7) re-runs against the new spine. A spine migration
  keeps both snapshots registered until its sweep completes.
- **Extend, never modify.** The spine's whole value is shared semantics —
  divergence belongs in the shared tier and the domains, as extensions. A
  deliberate fork remains possible and honest — it is a new registered
  snapshot whose mirror bytes and capture provenance say exactly what it is —
  but its cost (every interoperability dividend of a shared spine) is the
  forker's to carry, knowingly.

The distribution's templates carry the default registration shape (BFO-2020 +
CCO, per the rulings); capturing the release bytes is an ordinary owner-gated
capture, and registration follows it. An instance with no spine registered
has no ontology layer yet — every `extends:` is frontier and the gate has
nothing to run against; the layer activates by registration, exactly as the
reference-dataset layer did (v17).

### 15.3 Extension chains — `extends:`

Every concept and edge type in use owes a chain into the spine, declared in
its schema (§4.4) by the key **`extends:`** — exactly **one** parent:

- a spine **class**, for concept types (`extends: "cco:Organization"`);
- a spine **relation**, for edge types (relations, not categories, are what
  edges specialize);
- or **another declared type**, resolvable where the declaring type resolves
  (§15.4) — chains compose.

The chain is derived by following `extends:` upward. It MUST be acyclic and
MUST terminate in the spine; exactly one parent per type is D.2(2a)'s "unique
chain of is-a relations" as a lint rule. The D.2(2b) defined-class escape is
deliberately deferred (Part I §9) until a real type needs it.

A **missing** `extends:` on an in-use type is **frontier**, never an error —
surfaced on the work-list (§7.4) like every owed thing — and the v39 migration
seeds chains for every type in use at landing, so the frontier is only ever a
new mint awaiting its chain. A minimal schema (`type`, `description`,
`extends:`) is legal and imposes no field validation: the chain declaration is
earned structure's floor, not a gate on minting.

A predicate MAY declare `extends:` in its field declaration (§4.4), naming a
spine relation or property — optional; an unextended predicate projects as an
instance-local property (§15.7).

### 15.4 Domains — concept-anchored ontology

A concept MAY carry an **`ontology:` block**:

```jsonc
// facts/continuity/bsg-reimagined.json (excerpt)
{
  "id": "bsg-reimagined",
  "type": "continuity",            // resolves OUTSIDE this domain — see guards
  "name": "Battlestar Galactica (2003 continuity)",
  "ontology": {
    "commitment": "conditional",   // real (default) | conditional
    "imports": [],                 // other domain concepts; DAG, lineage-resolved
    "types": {
      "vessel": { "extends": "cco:Artifact", "description": "An in-universe craft." }
    }
  },
  "claims": [ /* ordinary claims about the property itself */ ]
}
```

- **Membership.** Any fact MAY carry a top-level **`domain:`** — a domain
  concept's id, resolved through the lineage map (§4.1) like every reference.
  Membership scopes vocabulary resolution and carries the domain's commitment.
- **Resolution is upward.** A member fact's types and predicates resolve in
  its domain's **import closure** (the domain, its imports, transitively) ∪
  the shared tier ∪ the spine — nothing else. A fact with no `domain:`
  resolves in the shared tier ∪ spine alone. Reuse-before-minting (§8) applies
  across the whole resolution set. A name resolving ambiguously across the
  closure (two imported domains minting the same type) is a validation error —
  loud, resolved by rename or import restructuring, never by precedence.
- **Domain-minted types.** Declared in `ontology.types`, same grammar as the
  shared tier (`extends:` chains into the closure, the shared tier, or the
  spine; missing chain = frontier). A fact whose type is domain-minted MUST
  carry `domain:` naming a domain whose closure declares it. The directory
  layout is unchanged — `facts/{type}/{slug}.json`, type = directory name —
  and two domains minting the same type name coexist: ids stay globally
  unique, the `domain:` field selects the sense, `VOCAB.md` renders the
  qualified form (`vessel @ bsg-reimagined`). A domain type's operational
  schema (fields, expectations), when earned, lives at
  **`schemas/{domain-id}/{type}.yaml`** — the §4.4 grammar plus a `domain:`
  key that MUST equal the parent directory name.
- **No shadowing.** A domain MUST NOT mint a type or predicate name that
  resolves in the shared tier — the shared term is the reuse target; a
  genuinely divergent sense takes a distinct name, or the divergence promotes.
  Cross-domain reuse of a name is fine (disjoint scopes).
- **The economy default.** Prefer a shared-tier generic type plus `domain:`
  membership; mint a domain type sense only when the kind is genuinely
  domain-specific. (The precedent is Wikidata's two-tier threshold: per-work
  variation stays qualified claims; a version earns its own item only on
  distinctive features.) A shared type whose instances are meaningless without
  domain context MAY declare **`requires_domain: true`** in its schema — a
  fact of that type without `domain:` is then a validation error.
- **Commitment.** `real` (default) or **`conditional`** — ISO/IEC 21838-2
  §4.9.3(b): the domain's members and minted vocabulary use the full machinery
  of the system with **no existence commitment**. The bracket is declared
  once, on the domain, wholesale; member facts never override it. It changes
  nothing inside the ledger — evidence discipline (§6) and the bar (§5.4)
  apply unchanged, because evidence always attested what artifacts state and
  depict, never that a claim's subject exists — and it binds at the edges:
  presentation renders conditional content as depiction, never as world-fact
  (§12), and the export never asserts it (§15.7). Claims from real facts to
  conditional facts (a portrayal, an appearance, a depiction) are ordinary
  out-of-universe claims about the fiction — always legitimate.
- **Guards**, each validated (§13.1):
  - a domain concept's own `type` — and its own `domain:`, if any — MUST
    resolve outside its own import closure (no self-anchoring);
  - `imports` name domain concepts only and form a DAG (no cycles),
    lineage-resolved;
  - `commitment` is one of `real | conditional`.
- **Re-seating.** Moving a domain to a better concept — the first work to the
  continuity that outgrew it — is a mechanical remap: the `ontology:` block
  moves, member `domain:` fields re-point, `schemas/{domain-id}/` renames, and
  the pass emits the migration worklist (§11's amended-invariant shape). Where
  the old domain concept itself merges or renames, the lineage map already
  carries every reference, `domain:` fields included. Domains are grown at the
  leaf and promoted when reality proves the recurrence — never designed
  upfront.

### 15.5 Condition-grammar growth

The shared operator grammar (§10) gains, everywhere it runs — harvest `match`,
invariant `applies_to`, demand and expectation `when`, scope seeds (§12.1):

- **The `domain:` fact axis** — operators over the fact's domain membership,
  `equals`/`in` operands lineage-resolved exactly as `id:` operands are (§14).
- **The `isa:` operator on `type:`** — matches when the fact's type equals the
  operand **or reaches it through `extends:` chains** (transitive closure over
  the declared DAG — deterministic, datalog-class, no reasoner). The operand
  names a shared-tier type or a spine class (label or opaque id). The existing
  operators are **unchanged**: `equals`/`in`/`glob`/`matches` stay literal —
  subsumption matching is opt-in by operator, never a silent redefinition of
  rules already deployed.

Scope evaluation (§12.1) gains the same two seed axes, plus a **commitment
parameter**: include or exclude conditional-domain facts (default include,
carried with their bracket visible).

### 15.6 Correspondence across domains

- **No cross-domain merge.** The lineage map's merge is **within-domain
  identity** — two mints that should have been one entity from the start.
  Across domains, and categorically across differing commitment,
  correspondence is **claims, never merges**: typed, evidence-bearing, graded,
  revisable. (The grounds are SKOS's own: merged resources are interchangeable
  in every statement, and separately-governed, separately-committed scopes are
  precisely where that must not happen. Merging a conditional concept into a
  real one is a category error outright.)
- **Hub-and-spoke.** When one thing has many domain-specific versions — a
  character across continuities — version concepts link **hub-ward** to one
  central concept, one claim per version, never pairwise (n links, not n²).
  The hub is minted at the second version, per the organic rule; the reading
  is the librarians' ladder — hub at work level, versions at expression level.
  Cross-spoke links exist only where a work itself asserts the connection (a
  crossover), as ordinary evidenced claims.
- **The version threshold.** A version earns its own concept only when it has
  distinctive features; mere per-work variation stays qualified claims on the
  one concept. The correspondence predicates (`version_of` and kin) are
  shared-tier vocabulary, minted organically when the first hub is.

### 15.7 The export projection

**`ath ledger export`** — a one-way, deterministic, regenerable projection of
the fact graph into RDF. The ledger's JSON is the source of truth — the
system's intermediate representation — and is **not constrained by the limits
of the projection**: IR-side verification (§13, §11, §14) is the authority;
the export carries what the target can express and no consumer round-trips it.
RDF is how the product speaks, never how the ledger thinks.

- **Plane-projected — the wall applies.** An export computes for a grant set
  (Part I §5.1): the **owner plane** (the default — local artifacts, the
  conformance gate) or, explicitly, the **public plane** or a declared
  audience plane. On any plane but the owner's, the §12 publication filter is
  pre-applied, fail closed: private-backed claims, the ids of fully-private
  fact files, evidence that resolves only privately, and the `ontology:`
  declarations of domain concepts not visible to the grant set are never
  emitted. An export handed beyond the owner is a publication; the plane — not
  the recipient's care — is the wall.
- **Target and shape.** The projection targets **RDF 1.2** — the triple-term +
  `rdf:reifies` "triple annotation" pattern, whose non-assertion semantics are
  normative in the target itself. Every claim exports as a **reifier**
  carrying its status, `asof`, `period`, qualifiers, and evidence (PROV-O
  derivation to the anchored `corpus://`/`ref://` URIs; quoted entries carry
  quotation-grade derivation). The tooling pins the dated editions of the
  target specifications it implements.
- **The assertion map** (normative). `confirmed`, `provisional`, and
  `inferred` claims **assert** their triple and annotate it; `reported`,
  `disputed`, and `conflicting` claims are **described, never asserted** —
  reifier and triple term only. The line is principled: the first three are
  the ledger asserting the world is so (however graded); the last three are
  assertions *about* assertions — a voice's testimony, a standing dispute,
  source disagreement. Presence claims (§5.5) have no triple and export as
  reifier-only descriptions carrying their presence marker.
  **Conditional-domain claims are never asserted on any plane**, whatever
  their status — the commitment bracket, expressed in the target's own
  non-assertion semantics. Interpretations are never exported at all.
- **Vocabulary mapping.** Concepts and edges export as OWL **individuals**,
  never classes. Types export as classes subclassed per their `extends:`
  chains into the registered spine. The record↔bytes joint is generic
  dependence (the spine's own relation — no intermediate pattern-individuals
  the ledger cannot address). The artifact roster projects as IAO aboutness
  (the record is about the concept; quoted evidence entries as mention-grade).
  The lineage map exports as the deprecation pattern — retired IRI kept,
  deprecated, equivalence to the survivor. Invariants export as SHACL shapes
  **where the target expresses them** — a partial projection for interchange;
  the IR engine remains the authority (open-world OWL cannot state them, and
  no reasoner is ever consulted about instance data at runtime).
- **The conformance gate** (ISO/IEC 21838-1 Annex D.5.1). Validation includes
  the gate: where the verifying environment provides a standard OWL 2
  reasoner, it MUST demonstrate that the owner-plane export combined with the
  registered spine (its mirrors materialized) is consistent, and the spine
  logically interpretable in it;
  where the environment cannot, the gate reports **honestly unverifiable**,
  never a silent pass (the §13.2 idiom — CI provides the reasoner). The gate
  runs over export artifacts at check time — never in any authoring or query
  path. The reasoner is implementation detail this specification never names.
- **Reproducibility.** Every export stamps the §12 tuple — specification
  version, instance commit, the spine snapshot bindings (resolved tag +
  mirror-artifact blake3, §6.5), plane — so a consumer pinning an export pins
  what produced it.

### 15.8 Worked sketch (non-normative)

The fiction pattern, end to end, in the instance's idiom. The continuity
concept anchors a conditional domain (its own type, `continuity`, resolves in
the shared tier — media vocabulary extending the spine). The character rides
the **shared** `character` type (economy default; the schema declares
`requires_domain: true`) with membership selecting the universe; only `vessel`
is domain-minted, because no shared kind fits. Evidence discipline is
unchanged throughout — the in-universe claim anchors a time-coded quote in a
real record, exactly like any claim:

```jsonc
// facts/character/william-adama.json
{
  "id": "william-adama", "type": "character", "domain": "bsg-reimagined",
  "name": "William Adama",
  "sources": { "s1": { "record": "<miniseries-pt1 blake3>" } },
  "claims": [{
    "id": "william-adama:commands", "predicate": "commands", "object": "galactica",
    "status": "provisional",
    "evidence": [{ "source": "s1", "anchor": "time_range=41:05-41:12",
                   "quote": "This is the Commander.", "kind": "direct" }]
  }]
}
```

`galactica` is a `vessel` fact carrying `domain: "bsg-reimagined"`. Edward
James Olmos is a real `person`; his `portrays → william-adama` claim is an
ordinary out-of-universe claim and exports asserted. Adama's `commands` claim
exports described-never-asserted (conditional domain), whatever its rung. A
second continuity arriving later mints its own membership and, at that moment,
the hub concept and its `version_of` spokes (§15.6) — and if the first
domain's anchor proves too narrow (a film that grew into a franchise), the
domain re-seats (§15.4) without an id changing anywhere.
```

## 2. Part III — new §5.5 (insert after §5.4)

```markdown
### 5.5 Presence claims

A claim MAY assert, in place of a value, the **shape of its predicate's
extension** on this fact:

```jsonc
{ "id": "elizabeth-i:child", "predicate": "child", "presence": "none",
  "status": "confirmed", "asof": "2026-08-25",
  "evidence": [ /* the sources attesting the absence */ ] }
```

- **`presence: "none"`** — the fact verifiably has no value under this
  predicate. Distinct from silence: absence of a claim means nothing (§4.4),
  while a presence claim is an evidence-bearing assertion of absence.
- **`presence: "some"`** — a value exists but its identity is unknown:
  known-existence, unidentified ("this person has a father; no source names
  him"). The claim that closes the existence question while the identity
  question stays open.
- **Shape.** A claim carries exactly one of `value`, `object`, or `presence`.
  `element` bindings do not apply to presence claims; a field's declared value
  kind (§4.4) does not bind them — there is no value to parse.
- **Otherwise ordinary.** The full ladder applies; the bar (§5.4) applies
  unchanged — for `none`, the evidence attests the absence itself (a source
  stating it, an authoritative record whose scope covers it; sweep-backed
  negative evidence remains the named extension point in §6). Invariants count
  presence claims as matching claims. A presence claim **satisfies demands**
  under its predicate (§14): a confirmed "verifiably none" settles an owed
  field the way a value does — `blocked` remains for demands no source can
  settle either way.
- **Never mechanical.** Harvest MUST NOT mint presence claims (§10): absence
  is never derivable from the harvest fact base.
- **Contradiction is the ordinary machinery.** A later value claim under a
  predicate carrying a standing `presence: "none"` is a graph contradiction —
  `conflicting`/`disputed` with a correction (§7.3), never a silent
  replacement.
```

## 3. Part III — edits to existing sections (exact old → new)

**E1 — §1.4 Terminology.** Add rows to the table:

```markdown
| **Domain concept** | A concept carrying an `ontology:` block — the anchor of a domain: concept-scoped vocabulary and membership, with declared commitment (§15.4). |
| **Domain (`domain:`)** | A fact's membership in a domain concept's scope — vocabulary resolution through the domain's import closure, commitment carried from the domain (§15.4). |
| **Shared tier** | The instance-general vocabulary — every type, predicate, and schema not scoped to a domain; extension chains tie it to the spine (§15.1, §15.3). |
| **Spine** | The ontology reference datasets the instance registers as its extension-chain roots — mirror bytes as corpus artifacts, `spine: true` in the config, tooling-shipped adapters; every extension chain terminates in it (§15.2). |
| **Extension chain (`extends:`)** | A type's declared single-parent is-a chain into the spine — ISO 21838-1 D.2 conformance as data (§15.3). |
| **Presence claim** | A claim asserting the shape of its predicate's extension — `presence: "none"` (verifiably no value) or `"some"` (value exists, identity unknown) — in place of a value (§5.5). |
```

**E2 — §1.4 Terminology, lineage row.** Replace:

> | **Lineage map** | `facts/LINEAGE.json` — the committed `{"old-id": "survivor-id"}` map every merged or renamed id retires into (§4.1); its keys stay occupied forever. |

with:

> | **Lineage map** | `facts/LINEAGE.json` — the committed map every merged or renamed id retires into: `"old-id"` → `{"to": "survivor-id", "reason": …}` (§4.1); its keys stay occupied forever. |

**E3 — §3 Layout.** Under `schemas/`, add one line after the `{type}.yaml` line:

```
│   ├── {domain-id}/{type}.yaml # domain type senses — per-domain operational schemas (§15.4)
```

**E4 — §4.1, the lineage-map sentence.** Replace:

> the losing id retires into the **lineage map** — `facts/LINEAGE.json`, a flat committed `{"old-id": "survivor-id"}` object —

with:

> the losing id retires into the **lineage map** — `facts/LINEAGE.json`, a flat committed object mapping `"old-id"` → `{"to": "survivor-id", "reason": "merged" | "renamed"}`; the `reason` vocabulary is closed, grown by amendment —

**E5 — §4.1, first bullet.** Replace:

> - **Retired slugs stay occupied.**

sentence's follow-on "chase a key to its survivor" language in the second
bullet:

> - **References resolve through the map, one hop only**: wikilinks, claim `object`s, `{"entity": …}` refs, and `ledger://` chase a key to its survivor.

with:

> - **References resolve through the map, one hop only**: wikilinks, claim `object`s, `{"entity": …}` refs, `domain:` memberships (§15.4), and `ledger://` chase a key to its row's `to`.

And append to the §4.1 closing line ("Outright deletion — id and lineage row
both — is reserved for content that should never have existed."):

> An outright deletion keeps no row and carries no reason field — the
> repository history is its record (the no-dead-lineage rule: reasons ride
> rows only where rows exist).

**E6 — §4.2 concept file.** In the jsonc example, after the `"sensitivity"`
line, add:

```jsonc
  "domain": "bsg-reimagined",      // optional — domain membership (§15.4)
```

And append one paragraph at the end of §4.2:

> **Domains.** A fact MAY carry **`domain:`** — membership in a domain
> concept's scope — and a concept MAY itself carry an **`ontology:`** block,
> anchoring a domain. Both are §15.4's; nothing about them changes what a
> concept *is* here: a domain concept is an ordinary concept first, and
> membership is a resolution scope, never a partition.

**E7 — §4.4 Schemas.** In the first example block (`type: song`), add after
the `description:` line:

```yaml
extends: "bfo:generically dependent continuant"  # the extension chain into the spine (§15.3)
```

And add to the semantics bullet list:

> - **Extension and membership.** `extends:` names the type's single parent —
>   a spine class (concept types), a spine relation (edge types), or another
>   declared type (§15.3); missing is frontier, unresolvable or cyclic is an
>   error. `requires_domain: true` marks a type whose facts MUST carry
>   `domain:` (§15.4). A field MAY carry `extends:` naming a spine relation
>   its predicate specializes (optional, §15.3) and MAY carry `invariants:` —
>   field-attached constraints (§11). Domain type senses live at
>   `schemas/{domain-id}/{type}.yaml`, the same grammar plus a `domain:` key
>   matching the parent directory (§15.4).

**E8 — §5.1 Claim object.** Add to the field-semantics bullets:

> - **Presence claims** (§5.5): a claim may carry `presence: "none" | "some"`
>   in place of `value`/`object` — exactly one of the three forms per claim.

**E9 — §8 Vocabulary.** Append two bullets:

> - **Two tiers** (§15.1): unscoped vocabulary is the shared tier;
>   domain-scoped vocabulary registers under its domain concept —
>   `VOCAB.md` gains per-domain sections and qualified display
>   (`vessel @ bsg-reimagined`). Reuse-before-minting applies across a fact's
>   whole resolution set (§15.4); a domain never shadows a shared name.
> - **Extension chains are owed** (§15.3): an in-use type without `extends:`
>   is work-list frontier — the one standing owed-ness of vocabulary itself.

**E10 — §10 Harvest.** In the fact-base/operator bullet, append:

> The grammar additionally carries the `domain:` fact axis and the opt-in
> `isa:` operator (§15.5); existing operators are unchanged.

In the mint semantics, append one bullet:

> - **Minting into domains.** `mint.concept` MAY carry `domain:` — a domain
>   concept the rule names statically; the minted type must resolve in that
>   domain's closure (§15.4). Harvest MUST NOT mint presence claims (§5.5).

**E11 — §11 Invariants.** Append one bullet:

> - **Field-attached sugar** (§4.4): a schema field MAY carry `invariants:` —
>   the same constraint kinds, `applies_to` implied by the declaring type and
>   field — absorbed as sugar over this section exactly as `expectations:` are
>   sugar over demands (§14). One engine, two homes; violations report
>   identically.

**E12 — §12 Consumption contract.** In the honesty bullet, replace:

> a `provisional` claim MUST NOT present like a `confirmed` one, and interpretive content (standing corrections, open questions) presents as interpretive.

with:

> a `provisional` claim MUST NOT present like a `confirmed` one, interpretive
> content (standing corrections, open questions) presents as interpretive, and
> conditional-domain content presents as depiction, never as world-fact
> (§15.4).

And append to the evidence-resolution bullet:

> When materializing a citation, the anchor's resolved scope is the quote's
> context payload — a consumer SHOULD load the coarse selection to
> contextualize the quoted span, rather than peeking arbitrarily around it.

**E13 — §12.1 Scope.** In **Seed**, after "the facts matched by a
deterministic predicate over fact fields and claim predicates/values", append:

> — including the `domain:` axis and the `isa:` operator (§15.5)

And append to the **Close** bullet:

> **Commitment** is a scope parameter: conditional-domain facts are included
> by default, carried with their bracket; a scope may exclude them (§15.5).

**E14 — §13.1 Validation.** In **Graph**, replace:

> the lineage map (§4.1) satisfies references and resolves in one hop (every value names a living fact, never another key; keys collide with no living id; no fact file carries a retired shape).

with:

> the lineage map (§4.1) satisfies references and resolves in one hop (every
> row's `to` names a living fact, never another key; every row's `reason` is
> from the closed vocabulary; keys collide with no living id; no fact file
> carries a retired shape).

In **Epistemics**, append:

> presence claims well-formed: exactly one of `value`/`object`/`presence` per
> claim, `presence` from `none | some`, no `element` bindings on presence
> claims (§5.5);

Add a new block after **Schemas**:

> **Ontology** — `ontology:` blocks well-formed (§15.4): `commitment` from
> `real | conditional`, `imports` resolve to domain concepts and form a DAG,
> minted types well-formed with no shared-tier shadowing; every `domain:`
> membership resolves (through the lineage map) to a domain concept; every
> fact's type and predicates resolve in its resolution set, unambiguously; a
> domain-minted type's facts carry `domain:`; `requires_domain` honored; a
> domain concept's own type and membership resolve outside its own closure;
> `extends:` chains (§15.3) acyclic and spine-terminated where declared,
> frontier where missing; spine references resolve through the registered
> spine datasets (label or native id — unresolvable is an error, a deprecated
> term warns, absent mirror bytes report honestly unverifiable, §15.2); the
> conformance gate (§15.7) runs where the environment provides a reasoner and
> reports honestly-unverifiable where it cannot.

**E15 — §13.2.** Append to item 2 (quote verification):

> A quote that fails against a **re-derived** surface (a normalization or
> derivation-op pass that shifted the text) is flagged for **re-anchoring by
> re-evaluation within its anchor's resolved scope** — the anchor is the
> repair scope; record-wide fuzzy matching is never the repair.

**E16 — §14 Demands.** In the conditions bullet, after the `edge:` selector
material, append one sentence:

> Conditions additionally carry the `domain:` fact axis and the `isa:`
> operator (§15.5).

## 4. Part I — edits

**P1 — §6.1 table.** Add row:

> | Ontology export + conformance gate (Part III §15.7) | Deterministic |

**P2 — §7 Tooling.** Append to the `ath` bullet's verb list: `ath ledger
export` (the plane-projected RDF projection, Part III §15.7). Append one
sentence to the section:

> The distribution ships **spine adapters** — the format knowledge for
> reading the registered ontology reference datasets (a BFO-2020 table set, a
> CCO release tree — Part III §15.2); the spine data itself is instance
> state, captured and registered like any reference dataset, never shipped
> with the tooling.

**P3 — §9 Out of scope.** Add to the list:

> ISO 21838-1 D.2(2b) defined-class declarations (every chain is single-parent
> until a real type needs the escape); domain-scoped vocabulary classes beyond
> types and predicates (roster roles, modalities, and value kinds stay
> shared-tier); export serializations beyond the RDF 1.2 projection
> (nanopublication and Web Annotation renderings are mechanical futures of the
> same projection, not law); ontology-block nesting beyond `imports`.

**P4 — §2.3 The instance config.** In the `references:` block grammar, add
beneath the `adapter:` line:

```yaml
    spine: true            # optional — admits this dataset as an extension-chain
                           #   root for the ledger's ontology layer (Part III §15.2)
```

And add a sibling top-level block after `references:`:

```yaml
assets:                    # instance-registered tool assets (Part II §12.3.6):
  {name}:                  #   engine payloads the tooling injects or executes,
    description: …         #   pinned exactly as reference snapshots are
    latest: {tag}          # declared, never inferred
    snapshots:
      {tag}:
        artifact: …        # blake3 of the registered build's bytes
```

With one registry sentence appended to the section's closing paragraph:

> An `assets:` entry registers a **tool asset** — a payload the tooling
> injects or executes (the web capturer's SingleFile bundle, Part II
> §12.3.6) whose exact bytes shape captured content and therefore belong to
> the instance, not the tooling: captured with provenance, pinned by artifact
> blake3, resolved through custody, updated by registration diff. Same
> snapshot grammar as `references:`, none of the citation semantics — asset
> content is never a `ref://` surface.

**P5 — the version note** (bottom of Part I). Replace the v38 paragraph with:

> *Version 39 (2026-08-25, owner ruling) lands the ontology layer (Part III
> §15): the registered BFO-2020 + CCO spine (instance-held reference
> datasets, tooling-shipped adapters), extension chains on the shared tier,
> concept-anchored domains (a domain is a concept; the slug is the
> namespace), the opt-in `isa` operator, presence claims (§5.5),
> field-attached invariants, lineage reasons, and the plane-projected RDF 1.2
> export with the D.5.1 conformance gate. Prior version notes: the
> changelog.*

**Frontmatter**: all four parts bump `version: 38` → `39`;
`date_modified: 2026-08-25` on Parts I and III.

## 5. Part II — edits

**C1 — §12.3.6 (web capture).** After the paragraph introducing the
self-contained SingleFile snapshot, add:

> **The snapshot engine is an instance asset, not tooling.** The injected
> SingleFile bundle is registered in the instance config (`assets:`, Part I
> §2.3): its bytes are an ordinary corpus artifact — captured from upstream
> with retrieval provenance, content-addressed, resolved through custody
> routes, and pinned against deletion by its registration exactly as a
> reference snapshot is — and the capturer resolves the registered `latest`
> tag to its artifact blake3 and materializes the bytes locally. The tooling
> ships the **harness** (browser driving, injection, the snapshot call) and
> the format knowledge to load a registered build (the upstream
> string-constant module form or a direct IIFE); which build runs, at which
> bytes, is the instance's declared, pinned, visible-diff state — updated by
> capturing the new upstream release and bumping `latest`, never by a tooling
> release. Each web capture records the resolved asset identity on its
> capture sidecar as **`snapshot_engine:`** (`singlefile@{tag}` plus the
> artifact hash), landing in origin provenance — the engine-pin discipline
> (§6.4) applied to capture itself. With no asset registered, or its bytes
> not materialized in the capturing environment, capture degrades to the
> rendered-DOM snapshot and **discloses it loudly** — degraded fidelity is
> never silent.

*(No other Part II text changes; the SingleFile banner, from-save capture,
and `html-stampfree@1` are untouched.)*

## 6. CHANGELOG entry (prepend under "The unified line")

```markdown
- **v39** (2026-08-25, owner ruling) — **The spine, the domains, and the
  projection.** The ledger grows its ontology layer (Part III §15), on the
  2026-08-25 rulings and the "Grounding the Ledger" research arc, with one
  structural inversion ruled after the report's soundness review: **a domain
  is a concept** — no module files, no parallel tree; the slug is the
  namespace, unique by construction, lineage-carried, wikilink- and
  `ledger://`-addressable like everything else. (1) **The registered spine**
  (§15.2): the spine is instance data, not distribution code — BFO-2020 and
  the CCO release register as reference datasets (§6.5: mirror bytes are
  corpus artifacts — provenance, content-addressed integrity, custody, gc
  protection for free), marked `spine: true` in the config; the distribution
  ships format **adapters** only. Updating is a registration diff — new
  snapshot, bump `latest`, every chain re-resolves (vanished term = error,
  deprecated term = warning) and the gate re-runs; chains are **always bare**
  (one spine version per instance — the gate needs one coherent ontology);
  fabricated references error against the resolved release, absent mirrors
  report honestly unverifiable. *(Supersedes the vendor-the-tables ruling:
  instance-held, tooling-read, updated independently of any tooling
  release.)* (2) **Extension chains** (§15.3): every in-use type owes a
  single-parent `extends:` chain terminating in the spine (ISO 21838-1
  D.2(2a) as a lint); missing = work-list frontier; the migration seeds every
  existing type. (3) **Anchored domains** (§15.4): a concept MAY carry an
  `ontology:` block — commitment (`real | conditional`, the BFO
  §4.9.3(b) bracket, declared once, wholesale), imports (DAG), minted type
  senses; facts join by `domain:`; resolution is upward through the import
  closure ∪ shared tier ∪ spine; no shadowing; economy default is
  shared-type + membership (the Wikidata two-tier threshold); domains
  re-seat mechanically when they outgrow their anchor. Guards: a domain
  concept is a real thing first (no bucket concepts), and its own type
  resolves outside its own closure. (4) **Correspondence** (§15.6): no
  cross-domain merge, ever (SKOS interchangeability; conditional↔real merge
  is a category error) — evidence-bearing claims instead, hub-and-spoke (n
  links, not n²), hub minted at the second version. (5) **The projection**
  (§15.7): `ath ledger export`, one-way RDF 1.2 (reifier "triple
  annotation"), **plane-projected with the §12 wall pre-applied fail closed**
  on every plane but the owner's; assertion map: confirmed/provisional/
  inferred assert, reported/disputed/conflicting described-never-asserted,
  conditional never asserted anywhere; concepts as individuals, chains as
  subclass axioms, lineage as deprecation, invariants as partial SHACL —
  the IR stays the authority; the D.5.1 reasoner gate joins validation
  (honestly-unverifiable without a reasoner; CI provides one). (6) **Presence
  claims** (§5.5): `presence: "none" | "some"` — evidence-bearing absence and
  known-unknown, satisfying demands, counted by invariants, never harvested.
  (7) **Grammar riders**: the opt-in `isa:` operator + `domain:` condition
  axis (existing operators unchanged — subsumption is never a silent
  redefinition); field-attached `invariants:` sugar (§11); lineage rows gain
  `reason` (`merged | renamed`, closed, grown by amendment; outright
  deletions stay rowless — reasons without corpses); §13.2 re-derived-surface
  quote repair is re-evaluation within the anchor scope. (8) **The capture
  engine follows the spine** (Part II §12.3.6, Part I §2.3): the SingleFile
  bundle leaves the tooling tree — an instance-registered **asset**
  (`assets:` config block, snapshot grammar shared with `references:`, no
  citation semantics), its bytes captured from upstream with provenance,
  pinned by artifact blake3, resolved through custody; each web capture
  stamps `snapshot_engine:` (`singlefile@{tag}` + hash) into its provenance;
  unregistered or unmaterialized degrades to the rendered-DOM snapshot,
  disclosed loudly. The tooling keeps the harness and retires the vendor
  directory with its manual refresh procedure — refreshing becomes an
  ordinary owner-gated capture plus a registration diff. Migration: capture +
  register the two spine mirrors (`spine: true`, pinned by artifact blake3)
  and the capture-engine asset; seed ~28 `extends:` chains (minimal schemas
  where none exist); rewrite LINEAGE.json rows to object form (23 rows,
  reason backfilled merged/renamed from history); **zero fact-file edits** —
  absent `domain:` is the shared tier, every existing fact conformant
  byte-identically.
```

## 7. Migration story (measured)

Ordered; step 1 is distribution-side, 2–6 instance-side, one instance commit
for 2–5 (no transitionary states):

1. **Tooling lands with the amendment**: the spine adapters (`bfo-2020`
   reading the terms + relations tables; `cco-release` reading the module
   tree, catalog, labels, and deprecations), check's Ontology block, presence
   shapes, `isa`/`domain:` operators, lineage object form, VOCAB per-domain
   generation, `ath ledger export` + the gate; the `athenaeum.yaml` template
   gains the default spine-registration and asset shapes. The capture
   loader's resolution order becomes: `CORPUS_SINGLEFILE_BUNDLE` env override
   (the dev escape hatch, kept) → the registered `assets.singlefile` (tag →
   blake3 → custody) → disclosed rendered-DOM degrade; the
   `tools/src/corpus/vendor/` directory and its README refresh procedure
   **delete** (no dead lineage — the procedure's replacement is capture +
   registration). Gates: `uv run --no-sync python -m pytest -q`, ruff, per
   CLAUDE.md.
2. **Register the spine** in the instance: capture/ingest
   `BFO-2020-master.zip` and `CommonCoreOntologies-v2.2.zip` (both already on
   hand in the distribution checkout's `research/` — an owner-gated capture
   with a github public-origin overlay, `tenancy: public`), then register
   both in `athenaeum.yaml` — `spine: true`, adapters named, tags (`bfo:
   2020-master`; `cco: v2.2`, date folder `2026-08-13`, BSD-3), `latest:`
   declared, each snapshot pinned by its mirror-artifact blake3. In the same
   sitting, **register the capture engine**: capture the upstream SingleFile
   bundle (`single-file-bundle.js` from the single-file-cli repo — clean
   retrieval provenance; alternatively ingest the build currently in use,
   with local-file provenance) and register it as `assets.singlefile` with
   its tag and artifact blake3. Three visible diffs: the records, the config,
   nothing else.
3. **Seed extension chains** — the all-in ruling: a minimal schema
   (`extends:` + description) for every in-use type lacking one; existing
   schemas gain the one key. Measured against the live instance: 28 type
   directories; anchor targets per the report's §6 worked table (person →
   object; place → site; organization → cco:Organization; event/conversation →
   process; show/episode/expression → generically-dependent-continuant
   chains; the automotive cluster → artifact chains; edge types →
   spine relations). ~28 small YAML diffs.
4. **Lineage rewrite**: `facts/LINEAGE.json` → object rows. 23 rows today;
   reason backfilled from repository history (the report audited 21 as
   merges; re-verify those and the 2 added since — any rename backfills
   `renamed`). One mechanical diff.
5. **Fact files: zero edits.** Absent `domain:` = shared tier; every existing
   fact is conformant byte-identically. No domain exists at landing — the
   first one arrives with the first fiction onboarding, organically.
6. **Run the instance gates**: `ath ledger check` / `verify` (expected clean
   after 3–4), then the first `ath ledger export` + conformance gate in CI —
   the first run is the review surface, per the house rule.

Measured cost: 3 captures (2 spine mirrors + 1 engine bundle) + 1 config
registration diff, ~28 schema seeds, 1 LINEAGE rewrite, 0 fact edits, one
tooling-tree deletion (`vendor/`), no consumer-visible URI changes.

## 8. Enforcement & guidance sweep (lands with the fold-in)

- `tools/`: check contract additions (E14), presence-claim shapes, operator
  grammar (`isa`, `domain:`), lineage object form, VOCAB generator
  (per-domain sections, qualified display, chain-frontier), worklist
  (chain-owed items), demand surface (presence satisfies), `export` command +
  planes + gate, spine adapters (`bfo-2020`, `cco-release`) with
  label/deprecation resolution; `corpus` capture loader (asset resolution
  order, `snapshot_engine:` stamping, loud degrade disclosure), `vendor/`
  directory deletion, scaffold/docs references to it swept.
- Templates (`tools/src/ath/templates/`): the `athenaeum.yaml` template gains
  the default spine-registration shape; ledger `CLAUDE.md` and
  `facts/SCHEMA.md` — domain discipline (real things only, no bucket
  concepts; economy default; no shadowing), presence idiom, `isa` opt-in
  note; agent briefs likewise.
- Read surface: OpenAPI additions for the new scope axes
  (`domain`/`isa`/commitment) — spec-version stamp moves with the bump.
- `testdata/`: exemplar domain concept + member fact + presence claim +
  export fixture in the regression library.
- Instance runbooks (instance-side, at migration): the seeding commit's
  narrative; CI gains the reasoner step.
- This draft file and `REVIEW.md` delete when the amendment lands (no
  transitionary states; history keeps them).
