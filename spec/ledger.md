---
spec_id: ATH
part: III
title: "Athenaeum Specification — Part III: The Ledger"
version: 30
status: current
license: "CC BY-SA 4.0"
date_created: 2026-07-02
date_modified: 2026-08-21
---

# Athenaeum Specification — Part III: The Ledger

## 1. Overview

### 1.1 What this is

The **ledger** is the Athenaeum system's knowledge layer ([Part I](athenaeum.md)): the single fact substrate atop the corpus (faithful bytes, [Part II](corpus.md)) — with it, it forms the system's **end product**, consumed from outside by compilations and expert agents under the consumption contract (§12). It holds **concepts** — materialized real-world things (§4) carrying typed claims in which **every claim carries evidence**: `corpus://` URIs into captured bytes (span-precise where verified) and `ref://` URIs into mirrored reference datasets (§6.5) — and **interpretations**, the pre-assertion workspace beside them.

The name is meant literally: a ledger is claims with evidence and an audit trail. Entries are *posted* (claims — asserted, each with computable trust) or held in *suspense* (interpretations — not yet assertable). The boundary between the two is physical (§1.3), which is what lets every consumer of the fact graph trust that everything in it is asserted knowledge.

Amendment history lives in [`CHANGELOG.md`](CHANGELOG.md); the closed ATH-LEDGER line (1.0–1.9) is indexed there too. This text carries current law only.

### 1.2 One ledger

The ledger is not shared — it is the system's intermediate representation, read only by its owner's tooling and by consumers under §12 — so it is **one directory of the instance repository** (`ledger/`, beside `corpus/` — Part I §2.2), interpreting the instance's one corpus. Nowhere in the system is privacy a partition — not a repo, not a directory.

```
corpus ──interprets──▶  ledger  ──consumed──▶  compilations, agents  (publication is theirs, gated by §12)
```

- **Sensitivity is derived, not partitioned.** A claim citing private evidence is **private-backed** (§6.4). One thing is one file, whatever mix of sensitivities its claims carry.
- **The wall moves to publication.** Privacy is enforced where it is load-bearing: the consumption contract (§12) obliges any consumer publishing beyond the owner to filter on derived sensitivity, fail closed. Nothing inside the ledger needs a wall — everything inside it is the owner's.
- One knowledge substrate, many consumers: compilations target the ledger; expert agents read it directly. Knowledge is authored once, here — never re-authored per presentation.

### 1.3 The assertion boundary

**Claims are asserted; interpretations are not.** The claim `status` ladder (§5.3) is a state machine over *asserted* knowledge — a claim is born at the lowest rung its evidence supports and is promoted **in place** as evidence accrues. Uncertainty about an asserted claim is ladder position, not a separate file.

An interpretation exists when the epistemic content **isn't claim-shaped** (§7): an identity guess resolving to a graph merge, a working assessment with no settled predicate, negative/corrective knowledge whose job is to tombstone errors, or an ingestion need. Interpretations sit physically beside the facts so that no consumer of `facts/` ever has to filter speculation out of knowledge.

### 1.4 Terminology

| Term | Definition |
|---|---|
| **Concept** | A materialized real-world thing — the durable noun of the knowledge layer; records are its evidence and artifacts, never its identity (§4). |
| **Fact file** | JSON under `facts/{type}/{slug}.json` — a concept or an edge, holding claims. |
| **Concept schema** | A declared, validating shape for a concept type — `schemas/{type}.yaml` (§4.4). |
| **Artifact roster** | A concept's typed `corpus://` links: the records that are artifacts *of* the thing (§4.2). |
| **Lineage map** | `facts/LINEAGE.json` — the committed `{"old-id": "survivor-id"}` map every merged or renamed id retires into (§4.1); its keys stay occupied forever. |
| **Claim** | One atomic, typed, **asserted** statement with evidence (§5). |
| **Evidence** | A `corpus://` or `ref://` citation grounding a claim, graded by `kind` (§6). |
| **Reference dataset** | A locally-mirrored external database (Wikipedia, MusicBrainz, …), citable as evidence by native id via `ref://` — resolved at its `latest` snapshot tag, or pinned `@{tag}`; each snapshot's mirror is a corpus artifact (§6.5). |
| **Sensitivity** | The derived visibility of evidence, claims, and files — computed per grant set from record tenancy, never partitioned (§6.4). |
| **Interpretation** | A structured **pre-assertion** item: hypothesis, assessment, correction, or need (§7). |
| **Authentication bar** | The evidence threshold for `confirmed` (§5.4). |
| **Harvest rule** | A deterministic derivation minting auto-provenance concepts, roster entries, and claims from corpus record facts, keyed by origin-native identity (§10). |
| **Invariant** | A declared constraint over the fact graph, validated deterministically (§11). |
| **`ledger://` URI** | The external reference form for ledger content: `ledger://{id}` or `…/{id}:{claim}` (§12). |

## 2. The corpus join

Evidence cites records **bare** — `corpus://{hash}` — and resolves by blake3 in the instance's corpus (§6.2): a hash either resolves or it doesn't. There is no per-corpus URI form and no ledger-side registry of what it interprets: the instance's layout (Part I §2.2) is the join — the ledger at `ledger/` interprets the corpus at `corpus/`, and the evidence's sensitivity is a **derived property** of the resolved record (§6.4), never URI syntax.

*(The pre-v26 `ledger.yaml` — a ledger-side list of registered corpora — is retired with the multi-corpus topology; the instance config (`athenaeum.yaml`, Part I §2.3) carries what remains: the tenancy floor and the reference-dataset registry.)*

## 3. Layout

```
ledger/
├── CLAUDE.md                  # the ledger's operating guide
├── facts/
│   ├── SCHEMA.md              # the fact model + authoring conventions
│   ├── VOCAB.md               # GENERATED — vocabulary registry (§8)
│   └── {type}/{slug}.json
├── schemas/
│   ├── {type}.yaml            # concept schemas — declared, validating type shapes (§4.4)
│   └── values/
│       └── {kind}.yaml        # value kinds — declared typed-value shapes (§4.5)
├── interpretations/
│   ├── SCHEMA.md
│   └── {slug}.json
├── harvest/
│   └── {slug}.yaml            # mechanical minting rules over the corpus (§10)
├── invariants/
│   └── {slug}.yaml            # declared constraints over the fact graph (§11)
├── demands/
│   └── {slug}.yaml            # completeness rules — what asserted content owes (§14)
├── open-questions.md          # work-list: generated block + curated items (§7.4)
├── coverage.md                # GENERATED corpus→ledger coverage ledger (§9)
└── docs/                      # process docs — never world knowledge
```

There is no `notes/` in the ledger: prose lives with consumers (§12). World knowledge lives only in `facts/` + `interpretations/`; the boundary is strict.

## 4. Facts

Fact files are **concepts** — durable real-world nouns (§4.2) — and **edges**, claim clusters spanning them (§4.3). Entry into the knowledge layer is **materialization**: a fact file exists because a real thing was recognized — a song, a vehicle, a procedure — never because a record arrived. **Records are evidence, never subjects.** No fact file may exist to describe, mirror, or shadow a corpus record, and no id may derive from record identity (§4.1): the corpus asserts nothing about the world; the ledger stores nothing about bytes. Where many records attest the same thing they converge on **one** concept — as evidence on its claims and entries on its artifact roster — deduplication by construction.

### 4.1 Identity

Fact and interpretation ids are **readable slugs** (`[a-z0-9]+(--?[a-z0-9]+)*`): human-meaningful, wikilink-friendly, stable. A double hyphen conventionally separates the two sides of a pair edge id (`steven-rahn--greg-rahn`). The id is the filename stem; a fact's `type` is its parent directory name; both equalities are validated. Ids MUST be unique across the ledger's facts *and* interpretations together.

**Identity is real-world identity.** A concept id names the thing, not any record of it. When identity is established mechanically it comes from **origin-native keys** — a source's own stable identifiers exposed in origin facts (§10) — so re-captures and mirrors of the same thing converge on the same concept rather than minting shadows.

**Ids carry lineage.** Once minted, an id never silently **changes meaning** — external consumers hold `ledger://` URIs (§12) the ledger does not control, and frozen corpus bytes name ids in prose forever. When concepts merge (an identity hypothesis resolving, §7.1) or a slug is renamed, the losing id retires into the **lineage map** — `facts/LINEAGE.json`, a flat committed `{"old-id": "survivor-id"}` object — and the losing **file is deleted**: its claims move to the survivor, the type directories list only living concepts, and the merge's full story (date, moved claims, the diff itself) lives in the repository history. The map's semantics:

- **Retired slugs stay occupied.** Id uniqueness (§13.1) runs across facts, interpretations, *and the lineage map's keys* — a retired id can never be re-minted by accident, so an old reference can dangle loudly but never resolve silently to a different thing. Deliberate resurrection requires removing the row, a visible diff.
- **References resolve through the map, one hop only**: wikilinks, claim `object`s, `{"entity": …}` refs, and `ledger://` chase a key to its survivor. Merging into an id that is itself a key **retargets the older row** to the final survivor, so chains never form.
- **Claim ids carry lineage through the file id.** A claim's id is `{file-id}:{short}` (§5.1); when claims move to a merge's survivor each is **re-keyed to the survivor's prefix with its `short` preserved** — an external `ledger://{id}:{short}` then resolves through the map unchanged: the row maps the id half, the preserved short maps the rest. A short colliding with an existing claim on the survivor is **renamed**, and the merge emits a **migration worklist** naming every renamed claim and its dependents (the §11 amended-invariant shape) — a rename is loud, never silent. Outside merge-collision, tooling MUST NOT rewrite a short; internal references that name claims by id (`challenges`, `based_on`) are rewritten in the same pass that re-keys them, and a correction's `challenges` pin is re-stamped when the only delta is the re-key itself (§7.3 — the content the dispute examined is unchanged).

Outright deletion — id and lineage row both — is reserved for content that should never have existed.

### 4.2 Concept files — `facts/{type}/{slug}.json`

A materialized real-world thing and the claims intrinsic to it:

```jsonc
{
  "id": "gorguts",                 // slug; == filename stem; wikilink target
  "type": "artist",                // == directory name; schema-typed where one is declared (§4.4)
  "name": "Gorguts",
  "aliases": [],                   // optional
  "meta": "…",                     // optional authoring commentary — never a claim, needs no evidence
  "sensitivity": "private",        // optional asserted override, upward only (§6.4)
  "period": "2026-07-08/2026-07-09",  // optional — the fact's own timebox (§5.2); mirrors an evidenced claim
  "artifacts": [                   // the roster — records that are artifacts OF this thing (optional)
    { "uri": "corpus://826482aa…", "role": "documents", "note": "Metal Archives band page" },
    { "uri": "corpus://3fc0d1b2…", "role": "interview" }
  ],
  "claims": [ /* Claim objects, §5 */ ]
}
```

**The artifact roster** is the concept→record arrow that replaced corpus-side record classification: the corpus never declares "this record is an instance of class X"; the concept declares "these records are artifacts of me" — many records, one node, nothing dangling. A `role` is registered vocabulary (§8) naming a real relationship to the thing (`documents`, `performance-of`, `tablature-of`, `interview`); a role that cannot be phrased *of/about the concept* is a bucket, not a relationship, and does not belong. Roster entries carry harvest (`auto`) or asserted provenance under the §10 semantics; rostered URIs must resolve (§13).

**The timebox.** A concept MAY carry a top-level `period` — the fact's own timebox (§5.2): the calendar span of a bounded occurrence, the duration of an episode. It is a structural *summary* — what the schema's `period` expectation (§4.4), temporal invariants (§11), and timeline tooling read cheaply — while the *evidence* for that span rides a normal claim (for an `event`, the `occurs` claim). The two are bound by convention: the top-level value **mirrors** the evidenced timebox claim's `period`, so the summary never states a span the graph cannot back. Edges carry `period` the same way (§4.3); it stays optional on both, and its format is the §5.2 grammar.

A bare `{id, type, name}` **stub is valid** — every fact file is independently valid; there is no "incomplete" state. A stub is a signal: it marks the capture frontier and surfaces in the generated work-list. Any concept referenced as a claim `object` or an interpretation's `about` MUST have at least a stub — no dangling references.

### 4.3 Edge files — `facts/{edge-type}/{slug}.json`

A claim cluster not owned by a single concept — an event, an episode, a comparison, a dated series:

```jsonc
{
  "id": "…", "type": "…",
  "subject": "concept-id",         // the primary concept, for edge types that have one
  "participants": ["a", "b"],      // and/or the concepts the edge spans
  "title": "…",
  "period": "2026-09",
  "meta": "…",
  "claims": [ /* Claim objects */ ]
}
```

A file is an edge when it carries `subject` and/or `participants`; otherwise it is a concept. Long time-series and episodic clusters belong in edges.

### 4.4 Schemas — `schemas/{type}.yaml`

A schema is the declared shape of a fact type — a concept type or an edge type:

```yaml
type: song
description: A recorded or performed musical work.
fields:                          # the type's registered predicates
  appears_on: { target: album, expected: true }  # relational + owed: frontier when missing
  composed_by: { target: artist }  # relational — the claim object must be an `artist`
  length: {}                     # attribute — value shape per SCHEMA.md conventions
  released: { value: instant }   # typed attribute — value validated under a declared kind (§4.5)
roster_roles: [tablature-of, performance-of, interview]
```

An edge type's schema may additionally declare its span, and a field may carry an enumerated value vocabulary — the pattern that keeps a tie's *kind* as data instead of a predicate taxonomy:

```yaml
type: relationship
description: A person↔person tie. The tie's kind is data, never new schema fields.
participants: [person, person]   # positional — participant i must resolve to type i
fields:
  kind:
    values: [friend, sibling, father-of, care-provider-of]  # enumerated value vocabulary
    target: person
    participant: true            # the object, when present, must be a participant
  interaction: {}
```

A field whose value is a **structured array** — a roster of objects, one checkable element each (§5.1) — may declare **`elements:`**, a mapping of element-key to a declaration reusing the per-field grammar above (`values` for an enumerated vocabulary, `target` for a typed fact reference, `value` for a declared kind — §4.5). It validates the objects *inside* the array the way `values`/`target` validate a scalar field:

```yaml
type: event
fields:
  attendance:                      # a structured array — one person per element
    elements:
      entity: { target: person }             # each element's `entity` is a person
      role:   { values: [worked, attended, performed] }
  lineup:
    elements:
      entity: { target: organization }        # each element's `entity` is an act (an org)
```

Undeclared element keys are admissible — they register nothing and validate nothing, exactly as unmarked fields do; an element carrying `{"handle": …}` or `{"name": …}` in place of `entity` is fine.

**Entity references resolve — always.** Independent of any `elements` declaration, every `{"entity": <id>}` object inside a claim value MUST resolve to an existing fact (through the lineage map, §4.1): the no-dangling-references rule (§4.2) extended to the roster shape structured-array claims carry (§5.1). Consumers' scope traversals follow these references (§12), so a dangling one would silently truncate a compilation — validation makes it an error at its source.

Any type's schema may declare **expectations** — conditional owed-ness, the declared half of gap-finding (§7.4):

```yaml
# on schemas/person.yaml — owed only for facts the `when` selects:
expectations:
  - id: close-family-coordinates   # optional stable name — required only to BLOCK its demands (§14)
    description: close family of steven-rahn — identity coordinates are chase-worthy
    when: { relationship: { kind: [sibling, father-of, mother-of], with: steven-rahn } }
    expect: [date_of_birth, phone, email]
# on schemas/employment.yaml — no `when`: owed on every fact of the type:
expectations:
  - description: every employment episode is timeboxed
    expect: [period]             # the reserved name `period` is the fact's own timebox
```

Semantics:

- **Validating, never generative.** A schema is data the checker reads (like invariants, §11), not code that produces anything. Only mis-shape is an error: a relational field whose object resolves outside its declared `target` (one type, or a list of admissible types — `{ target: [system, component] }` — for relations the graph legitimately makes to several), a field value outside its declared `values`, a typed field's value failing to parse under its declared kind (`value:` naming a §4.5 kind — an undeclared kind is itself an error), a declared **element** value outside its `values` or an element `entity` resolving outside its `target` type(s), an object on a `participant: true` field that is not one of the edge's participants, an edge whose participants diverge from the declared `participants` (count or positional type), an unregistered roster role.
- **Stubs stay valid.** A fact missing an owed field is *frontier*, not failure — `expected: true` marks a field owed unconditionally; an `expectations` entry marks its `expect` fields owed on the facts its `when` selects (no `when` — every fact of the type). An entry MAY declare **`id:`** — a stable slug in the demand-rule namespace (unique across `demands/` rules and all named expectations, §13.1): the name its demands are blocked under (§14). Unnamed entries evaluate identically; their positional display ids (`expectation:{type}[{i}]`) are display-only — reordering a schema's list renumbers them, so nothing durable may reference one. Either way conformance gaps sharpen the generated work-list (§7.4); they never invalidate a file. The `when` selector names an edge type: a fact is selected when it participates in an edge of that type — restricted, when given, to edges whose `kind` claim takes one of the listed `kind:` values and whose participants include `with:` (a fact is never selected by a `with:` naming itself). Unmarked fields are *admissible, not owed*: they register vocabulary and validate targets, and their absence means nothing (most organizations manufacture nothing). A type with no schema is equally legal: schemas are earned structure, not a gate.
- **Timeboxed fields.** A field may declare `timeboxed: true` — e.g. `residence: { target: place, timeboxed: true }` — meaning every claim under that predicate owes a `period`: an attested residence or employment episode without a timespan is half a fact, and `asof` alone records observation, never duration. Like owed fields, a missing timebox is *frontier* (a labeled chase on the work-list, §7.4), never an error — the gap says "find the start/end", which is exactly how new evidence that widens a period announces where it belongs.
- **Grown organically or imported** — declared when a real shape recurs, or adopted wholesale in a domain package (§10); either way a schema lands as a visible diff and its vocabulary registers (§8).

### 4.5 Value kinds — `schemas/values/{kind}.yaml`

A **value kind** is a declared typed-value shape: what a field's claim `value` must parse as when the field references it (`{ value: money }`, §4.4). Kinds are the ledger's answer to typed quantities — money that sums, instants that order, coordinates that are coordinates — **without a global type ontology**: a kind is **instance-declared data**, like schemas and invariants, composed from a small **closed primitive-constraint vocabulary** the distribution's checker interprets. The closed part sits where it is mechanical (parsing a decimal, recognizing an ISO-4217 code), never where it is ontological; kinds themselves grow organically per instance and register in `VOCAB.md` (§8) like every other vocabulary.

```yaml
kind: money
description: An amount of a currency.
shape:
  amount:   { constraint: decimal }        # a decimal string — never a JSON float
  currency: { constraint: iso-4217 }
required: [amount, currency]
```

```yaml
kind: body-weight                          # instance-minted — organic, like any vocabulary
description: A measured body weight.
shape:
  amount: { constraint: decimal }
  unit:   { constraint: enum, values: [kg, lb] }
required: [amount, unit]
```

- **The primitive-constraint vocabulary is closed** — grown by amendment, like the corpus's semantic types, never minted per instance: `string`, `number`, `integer`, `boolean`, `decimal` (a decimal string, preserving precision JSON numbers cannot), `enum` (+ `values:`), `pattern` (+ `pattern:`), `range` (+ `min:`/`max:`, on numbers), `iso-instant`, `iso-date`, `iana-zone`, `iso-4217`, `latitude`, `longitude`. This is the `period`-grammar class of closedness — mechanical world-structure the validator must be code for — not the predicate class.
- **A typed claim value is the kind's object shape** (or, on a structured array, one object per element): `required` fields present, every present field parsing under its constraint, undeclared fields inadmissible. Mis-shape is a §13.1 error, exactly as a `values` violation is; a **missing** typed field stays frontier under the ordinary owed-ness rules (§4.4, §14). The human gloss, where wanted, rides `qualifiers` — never mixed into the typed object.
- **No conversion, no operations.** Values are stored as attested; unit vocabularies are plain `enum` constraints the instance owns. Deterministic conversion or arithmetic, where ever wanted, is consumer- or tooling-side work over the validated shapes — never silent mutation of asserted values. A `coordinate` kind buys a validated shape; nearness and containment stay unspecified (Part I §9).
- **Kinds register and retire like vocabulary** (§8): reuse before minting, visible diffs, retired kinds error in use. A kind's shape change is contract change — validation emits the migration worklist of nonconforming claims (the §11 amended-invariant shape), and so does first declaring `value:` on a field with existing prose claims: typing an existing field is deliberate and measured, never a silent break.
- **Shipped kinds are imports, never law.** The distribution carries common kind declarations (`money`, `quantity`, `instant`, `duration`, `coordinate`) as templates an instance **adopts** — the declared-import seam (§10): adoption is a visible diff and is itself the evidence of need. Nothing forces an instance to hold a kind it doesn't use; nothing stops it refining its own.
- **Kinds are data, not code.** The checker interprets declarations; it never loads instance code. An algorithmic-validity seam (check digits and the like) is designed but deferred until a declared kind needs one (Part I §9).

## 5. Claims

### 5.1 The Claim object

```jsonc
{
  "id": "lateral-raise:targets",   // "{file-id}:{short}" — unique within the ledger
  "predicate": "targets",          // registered in VOCAB.md (§8)
  "value": "…",                    // literal (string/number/bool/array/object) — ATTRIBUTE claims
  "object": "lateral-deltoid",     // a concept id — RELATIONAL claims
  "qualifiers": { "attribution": "…" },
  "period": "2019/..",             // when the fact HOLDS (§5.2)
  "status": "provisional",         // the ladder (§5.3)
  "asof": "2026-06-22",            // when the fact was OBSERVED
  "reasoning": "…",                // the argument, for anything not stated verbatim by the source
  "evidence": [ /* evidence entries anchoring this fact's sources, §6 — ≥1 unless the file is a pure stub */ ]
}
```

Field semantics:

- **`value` + `object` together is legitimate**: on a relational claim, `object` is the machine edge and `value` a human gloss. One claim's worth of content per claim — if a `value` hides several independently-checkable assertions of different confidence, split it.
- **Structured values over prose blobs**: list-shaped knowledge (form cues, ingredients, steps, spec tables) takes array/object values, one checkable element each. Evidence binds to a single element via `element` where a source attests part of the array (§6.1) — the array stays one claim precisely because partial backing is expressible.
- **Typed values parse.** Under a field declaring `value:` (§4.4), the claim's `value` is the referenced kind's object shape (§4.5) — or, on a structured array, one such object per declared element. The gloss rides `qualifiers`, never the typed object.
- **`reasoning`** carries inference rationale — never smuggled into an evidence `note`.
- Wikilinks (`[[slug]]`) in string values are permitted and validated against fact ids.
- Never store a relation *and* its inverse; symmetric relations are stored once. Which side stores a directed relation is a ledger convention, documented per type (`facts/SCHEMA.md`).
- **Attribute the voice.** Advice, technique, opinion, analysis are claims about what someone asserts: `status: reported`, the speaker in `attribution`. Two voices stay two claims.

### 5.2 Time

- **`period`** — when the fact is/was true of the world: ISO date, month, or year; range `a/b`; open range `a/..`; `~` prefix for circa.
- **`asof`** — when the supporting observation was made (a record's origin `snapshot` date is the natural choice).
- Time never rides in ad-hoc qualifiers. Time-varying measurements are datapoints: keep `asof`, put the axis in a qualifier, land long series in an edge.

### 5.3 The epistemic ladder — `status`

The state machine over asserted claims. Epistemic only — time lives in `period`/`asof`. A claim moves up **in place**; it is never re-filed.

| Status | Meaning |
|---|---|
| `confirmed` | Authenticated per the bar (§5.4). |
| `provisional` | A single non-authoritative source states it directly and plainly. The default birth state; seek corroboration. |
| `inferred` | Deduced from evidence, not stated verbatim — the argument lives in `reasoning`. |
| `reported` | A person asserts it (advice, opinion, testimony); name the voice in `attribution`. |
| `disputed` | A standing, specific reason to doubt it — a `correction` interpretation cites it (§7). Keep the evidence. |
| `conflicting` | Independent sources disagree; keep all evidence, explain per evidence `note`. |

Every rung is an assertion. Pre-assertion content (a suspicion, a guess) is an interpretation, not a low-status claim (§1.3). A ledger MAY retire statuses it has no use for (registered per §8); it MUST NOT mint new ones.

### 5.4 The authentication bar

A claim may be **`confirmed`** only when it has:

> at least one **authoritative** evidence artifact, **or** two or more **independent** sources — records of different provenance (different corpus hashes) and/or `ref://` citations, one reference dataset counting **once** however many of its entries are cited — and nothing else in the graph contradicting it.

The bar counts only evidence resolving on **verifiable surfaces**. An evidence entry citing a **deferred surface** — a record whose mime declares `citation_surface: segments` (corpus §7.1) and which persists no segments yet — is admissible on every lower rung but contributes nothing toward `confirmed`: not as the authoritative artifact, not toward record independence. (Environment gaps are different: evidence whose derivation op the verifying environment merely cannot run is verifiable *in principle* and still counts — deferral is a property of the surface, never of the machine.) When the record's declared surface lands, the same evidence starts counting; that promotion path is what deferral buys.

**Array-valued claims clear the bar per element.** Where a claim's `value` is an array, each element must individually meet the bar, counting the claim's whole-value evidence (entries with no `element`) plus the entries bound to that element (`element`, §6.1) — the authoritative artifact or the two independent sources may differ from element to element. A claim whose elements all clear confirms; one uncorroborated element holds the whole claim below `confirmed`, and validation names it. This is the same bar applied at the value's real grain — it neither weakens the whole-claim reading (a claim with no element-bound evidence is checked exactly as a scalar) nor licenses splitting arrays to dodge it.

Validation enforces the bar mechanically. Corroboration is multiple evidence entries on one claim; conflict is `conflicting` with all evidence kept; a graph contradiction is `disputed` plus the challenging `correction`.

## 6. Evidence

### 6.1 Sources and evidence entries

Citations are two-level: a fact-level **`sources` table** names each cited artifact once, and per-claim **evidence entries** anchor spans of it. One backing record cited by five claims is one sources entry and five span-precise entries — the artifact's hash and its verification binding (§13.2) live at the altitude they are true at: per *(fact, source)*, never per entry.

```jsonc
// fact-level, sibling of "claims":
"sources": {
  "s1": { "record": "826482aa…<full 64-hex blake3>",           // a corpus record,
          "verified": { "touch": "…", "at": "2026-07-11" } },   //   stamped by verify (§13.2)
  "s2": { "ref": "musicbrainz/artist/{mbid}" }                  // or a reference-dataset entry (§6.5)
},

// each claim evidence entry:
{
  "source": "s1",                       // the load-bearing field — a key in this fact's sources
  "anchor": "time_range=00:54-00:58",   // optional span parameters, no leading `?`; omitted = record-level cite
  "quote": "…",                         // optional verbatim span from the resolved content
  "note": "…",                          // optional human hint about the ARTIFACT (what/why)
  "kind": "direct",                     // authoritative | direct | incidental
  "element": 2                          // optional: binds this entry to value[2] of an array-valued claim
}
```

- **Source keys** match `^[a-z][a-z0-9-]{0,31}$`, are local to their fact, and carry no meaning — renames are free (challenge pins canonicalize on the derived citation, §7.3).
- A sources entry carries exactly one of **`record`** (a full 64-hex blake3) or **`ref`** (`{dataset}/{id}`, §6.5). Two entries in one fact naming the same target is a validation error — the table exists so each artifact appears once. Every entry must be referenced by at least one evidence entry (unreferenced = warning); every `evidence.source` must resolve in its own fact's table (unresolved = error).
- The **derived citation** is `corpus://{record}` — plus, when an `anchor` is present, `?` and the anchor verbatim (or the anchor alone when it begins with `#`, the fragment form) — or `ref://{ref}`. All §6.2 discipline applies to the derived form.
- **`element`** — a 0-based integer index into the claim's array `value`, binding the entry to that one element where the source attests part of the array. Only legal on a claim whose `value` is an array, and only in range — anything else is a check error (§13.1). One element per entry: a quote backing several elements becomes several entries, each quoting what backs its element. Omitted = the entry supports the whole value (every element). The binding feeds the §5.4 per-element bar and reads as documentation everywhere else; §13.2 verification of the entry is unchanged.
- Rosters (`artifacts[].uri`) and interpretation `based_on` lists (§7.2) are references, not evidence: they keep the direct URI form. A draft claim inside `proposes` likewise cites inline (`uri:`) — it has no fact table to reference; `ledger promote` materializes its citations into the target fact's sources table.

**`kind` grades the artifact so trust is computed, not vibed:**

- `authoritative` — an artifact whose *function* is to certify the datum (a manual for its product's specs, a monograph or government database for a drug's properties, an official statement for its own content). Authority is **scoped**.
- `direct` — a first-party statement in informal media.
- `incidental` — a passing mention or background detail; the weakest grade.

### 6.2 Citation discipline

- The derived citation MUST resolve: **`corpus://{hash}`** with the full 64-hex blake3 — anchor span parameters (`el=`, `page=`, `time_range=`, `frame=`, `page=N&bbox=`, `path=`, or a `#fragment`) per the corpus functional-URI grammar (`spec/corpus.md` §6) — or **`ref://{dataset}/{id}`** into a registered reference dataset (§6.5). (Rosters and `based_on` references, which carry direct URIs, obey the same grammar.)
- **Resolution is content-addressed, never scoped.** A hash resolves by blake3 in the corpus — it resolves or it doesn't; there is no scoping syntax. The resolved record's tenancy (and hence the evidence's sensitivity, §6.4) is a derived property, not URI syntax. A hash that does not resolve is a validation error.
- **Anchor only as precisely as verified.** A record-level cite is always safe; a wrong anchor is bad provenance — worse than none. Segment addresses printed by the corpus tooling (`corpus body` / `corpus toc`) are ground truth. Every anchor is expected to resolve mechanically — against the record's stored rendering or through a derivation op (`spec/corpus.md` §6.2) — and §13.2 verifies it there; an anchor that cannot be mechanically resolved is a citation defect, not a tolerated form. (An anchor whose surface has no text projection — an image region, an untranscribed span — still resolves and bounds-checks; it simply carries no `quote`.)
- **Quotes are verbatim spans** of the resolved content at the cited anchor — they exist to be machine-checked (§13.2). Paraphrase belongs in `note` or `reasoning`, never in `quote`.

### 6.3 Source honesty

Only assert what a source shows. Model knowledge is a *lead* for searching or capturing, never evidence.

Citability keys to **verifiable surfaces**, never to record state: the record's **faithful rendering** — segment bodies under their form (form-span renderings) and a derivation op's mechanical output (engine-pinned, `spec/corpus.md` §6.4) — and **attested byte-facts** (artifact-block fields, the members roster, structural byte-marks, corpus §4.4.6) all verify (§13.2); citing into a formless record's derived body is legitimate evidence, machine-checked like any other, with the op version pinned on the binding (§13.2).

*(Residue clause, corpus CHANGELOG 3.5)* A record ingested before the corpus's faithfulness sweep may still carry retired descriptive fields — section-header/segment descriptions, section entries, the frontmatter `title`/`description` override; verification reads them **tolerantly** where they exist (an existing anchor into one still resolves) but they are never a surface **new** evidence may cite — a fresh claim cites the faithful rendering or the byte-facts, never a field the corpus grammar no longer writes.

One distinction, keyed per-mime: a record whose mime declares `citation_surface: segments` (corpus §7.1 — formats whose raw/derived whole-record text is presentation soup, e.g. captured HTML DOMs) is a **deferred surface until persisted segments exist**. Claim evidence against it is admissible — cite freely; the citation is itself the normalize demand (§13.2.4) — but it is excluded from the §5.4 bar, and its quotes are held unmatched until the formed surface lands: record-wide matching against presentation soup is never attempted, because a match there would be structurally misleading rather than merely weak. What the record already attests mechanically — byte-facts, origin fields, derivation-op output — remains a verifiable surface and verifies now. Interpretations reference deferred surfaces exactly as freely (§13.2) — that is how a discovery read from a raw capture surfaces before it can be asserted.

**Evidence strength never keys to form state**: status assignment (§8) weighs source authority and independence — a claim meeting the confirmed bar on formless-record evidence is confirmed, and a record governed by a **terminal contract** (corpus §7.8) is a complete source whose derived surfaces are permanent, including a manifest record's attested member roster (first-class direct evidence for containment and existence facts).

Prefer the **formed** surface where one exists or is declared: span-precise anchors (`turn=`) bind tighter and survive tooling upgrades better than derived-body offsets — so when citing more than incidentally into a formless record whose artifact has a natural markdown shape, **raise demand** with `corpus enqueue` (the queue is standing demand, `spec/corpus.md` §8.5); the ledger contributes by enqueuing, never by authoring records. The demand signal keys to formless-**for-now** alone: enqueuing a terminal record raises nothing — no better surface is coming — and where a needed surface is a container *member*, the demand is a **`promote`** need (`corpus promote 'corpus://<container-id>?<member-address>'`; then form the promoted record) — never "normalize the container." Promoted members land **bodiless** until formed. When the source isn't captured, that is a `capture` need (§7); when the real world could settle it directly, an `observe` need.

### 6.4 Sensitivity — derived, not declared

Tenancy at the knowledge layer is computed, not partitioned (§1.2):

- **The tier set is instance-declared.** Tenancy names form an open set in the value-kinds mold (§4.5) — the mechanics here, the set the instance's. Two tiers are **reserved** with fixed semantics: **`public`** — the publishable tier, the one the §12 wall keys on — and **`private`** — the floor, the owner's alone, never grantable. The instance MAY declare further tiers (`family`, `accountant`, …) in its config (`spec/athenaeum.md` §2.3): slugs, colliding with no reserved name. An instance declaring nothing has exactly the `public | private` binary — every pre-tier instance is already conformant, byte-identically.
- **Record tenancy is a derived set, never stored.** A record's tenancy is the **union** of the tiers its origins declare (origin overlays MAY declare `tenancy: {tier}` from the declared set — deployment metadata the ledger reads schema-first; the corpus itself never consumes it), plus every tier inherited through an origin's `corpus://` lineage (a promoted member takes its container's tenancy, chased transitively). A record whose origins declare nothing falls closed to the **instance's declared `visibility:` floor** (a declared tier; default `private` — fail closed; `spec/athenaeum.md` §2.3). Union generalizes any-public-wins: bytes demonstrably public are public evidence even if also captured privately — an additional capture only ever *widens* a record's disclosure, never narrows it.
- **Visibility is grant intersection.** A reader holds a **grant set** of tiers; a record is **visible** to grant set G iff its tier set intersects G. The public reading is G = {`public`}; every declared audience (`spec/athenaeum.md` §2.3) holds its granted tiers plus `public`, implicitly, and never `private`; the owner reads everything. **Evidence sensitivity is this lookup**: a cited hash is visible to G iff its holding record is; otherwise it is private to that reading (fail closed). `ref://` evidence derives the same way: its visibility is the tenancy of the resolved snapshot's mirror-artifact record (§6.5) — public for a public-origin mirror (a Wikipedia ZIM), fail closed for one declaring nothing (a licensed export).
- **A claim is visible to G** iff *every* evidence entry it carries is visible to G and it asserts no `sensitivity: private` (the owner-only restriction). **Private-backed** means *not visible to {`public`}* — the term every publication sentence in this specification keys on, unchanged. The assertion stays binary and **upward only** — derived privacy is a floor no assertion lowers, and per-claim narrowing to a specific tier is deliberately not grammar (a claim's audience comes from its evidence; `sensitivity: private` withdraws it to the owner entirely). (A claim can be private on public evidence — a claim about your home citing a public map; the reverse cannot exist.)
- **A fact file is visible to G** iff any claim or roster entry it carries is visible to G and the file asserts no `sensitivity: private`. A file visible to no grant set but the owner's is **private** — existence itself can be the leak, per reading.
- Sensitivity gates **nothing inside the ledger** — everything here is the owner's. It is the claim metadata the consumption contract's publication filter keys on (§12): computed at its source, enforced at the boundary — and with tiers, enforced per audience the same way (Part I §5.1).

### 6.5 Reference datasets — `ref://`

Some sources are linked, not captured **per entry**. The corpus captures the world's *ephemera* — pages rot, so bytes are frozen under faithfulness obligations. Reference datasets mirror the world's *databases* — Wikipedia, MusicBrainz, OpenStreetMap: versioned, bulk-distributed, queried in place from a local mirror. The mirror bytes themselves **are corpus artifacts**: each registered snapshot's mirror (a ZIM file, a dump) is an ordinary **terminal-contract record** (corpus §7.8 — the artifact is its own terminal representation), which buys capture provenance, content-addressed integrity, store-backend distribution, and gc protection with no new machinery. What stays deliberately un-corpus-like is the **entry grain**: no per-entry records, no blake3 per article, no faithfulness pass over database rows — `ref://` is the sole citation surface for a mirror's *content*.

- **Citation form: `ref://{dataset}/{id}`** — the dataset's **native identity** (a page slug, an MBID, an OSM element id), never a URL — resolved at the dataset's **`latest`** snapshot tag; **`ref://{dataset}@{tag}/{id}`** pins a registered snapshot permanently. Datasets are registered in the instance config (`spec/athenaeum.md` §2.3): a format **adapter** — declared there, or derived schema-first from the mirror-artifact record's mime overlay `ref_adapter` (`spec/corpus.md` §7.1; an explicit declaration wins — the bootstrap and override path) — an explicit **`latest:`** tag (declared, never inferred), and a **`snapshots:`** map of tag → mirror-artifact blake3. A `ref://` into an unregistered dataset — or a pin naming an unregistered tag — is a validation error.
- **Bare tracks; pinned freezes.** A bare citation asserts corroboration by the dataset *as maintained*: verification resolves it through `latest` and stamps the resolved tag **and** artifact hash on the sources entry (§13.2), so bumping `latest` flags every bare citer for re-verification — each quote either still matches (re-stamp) or the entry changed (re-anchor, or pin the old tag deliberately). A pinned citation asserts the dataset's state *at that snapshot* — drift-free by construction; it pairs naturally with the claim's `asof` for point-in-time content. **Authoring convention: default to bare.** Pin only for genuinely point-in-time assertions or where a moved `latest` no longer carries the quote — a pin exempts evidence from drift detection, and that exemption must be deliberate, never a habit.
- **Resolution is downward.** The resolver maps `(dataset, tag)` → the snapshot's mirror-artifact blake3 → bytes through the corpus's custody routes (Part IV) — an attached location or store location over the mirrors directory serves the file in place; an adapter needing a sidecar index (an OSM extract's) keeps it as cache-mold derived state under the corpus's `cache/refidx/`, keyed by mirror blake3, gc-exempt by name (Part IV §6.4) — and the dataset's adapter renders the entry (an article's text, a release's fields) for quote verification (§13.2). Content resolution requires the mirror bytes locally materialized; where they are absent — or the dataset's adapter is unavailable in the verifying environment — content verification reports **unverifiable**, never failure, while grammar, registration, and snapshot-binding checks stay mechanical everywhere. Claim evidence citing a mirror's corpus hash *directly* draws a warning: the record exists for provenance and distribution; its content's honest citation surface is `ref://` (§13.1).
- **Graded like any evidence.** `kind` applies unchanged: a MusicBrainz release entry is `authoritative` for its own tracklist; a Wikipedia passage is typically `direct` or `incidental`. For the authentication bar, one dataset is **one independent source** however many of its entries a claim cites (§5.4). Sensitivity derives from the resolved snapshot record's tenancy like all evidence (§6.4).
- **Never swept.** Harvest (§10) runs over corpus record facts only — mirror *content* is never harvested, and enrichment from a dataset is authored ledger work citing `ref://`, demand-pulled like everything else. Coverage (§9) discharges at the mirror grain: snapshot records roster on the dataset's own concept (role `snapshot-of` or similar), never per entry.
- **External identity lands here.** A concept's ids in the world's databases (a Wikidata QID, an MBID) are ordinary claims citing the dataset itself — `predicate: musicbrainz-id`, evidence `ref://musicbrainz/artist/{mbid}` — made once on the concept, never stamped per record.
- **Anchors are entry-level.** A `ref://` citation carries no span parameters — quotes verify against the adapter's rendered entry as a whole. Per-dataset anchor grammar is out of scope (Part I §9) until real citations demand it.

## 7. Interpretations

### 7.1 What they are

Structured, evidence-linked **pre-assertion** items, physically beside the facts. A claim that is merely uncertain still lives in `facts/` — that is what the ladder is for. An interpretation exists when the thing itself isn't claim-shaped:

- an **identity guess** — "these two mentions are the same thing"; resolves by a graph merge, not a status bump;
- a **working assessment** — a synthesis with no settled predicate shape (including coverage-gap assessments: "the corpus attests X only shallowly; here is what to capture");
- a **correction** — durable negative/corrective knowledge ("X is NOT attested"; "claim Y is wrong"), including challenges to existing claims; refuted hypotheses stay as **tombstones** so future harvesters don't re-infer them;
- a **need** — an ingestion/verification request, carried on whichever interpretation needs it. Citations found while reading content land here too (the corpus carries only mechanically-declared references): a source a record cites is a `capture`/`search` need — or, where the domain cares about the citation itself, an edge with span evidence.

### 7.2 The Interpretation object — `interpretations/{slug}.json`

```jsonc
{
  "id": "…",                       // slug; shares the ledger id namespace (§4.1)
  "kind": "hypothesis",            // hypothesis | assessment | correction
  "about": ["concept-or-edge-id"],
  "statement": "…",
  "confidence": "likely",          // hypotheses only: speculative | plausible | likely
  "reasoning": "…",
  "based_on": ["corpus://…", "file-id:short"],   // empty = a hunch, not repo material
  "would_resolve": ["…"],
  "proposes": { /* a draft Claim object (§5.1), for claim-shaped hypotheses */ },
  "challenges": { "claim": "file-id:short", "state": "blake3:…" },  // corrections only: the claim under challenge, pinned as it stood (§7.3)
  "needs": [
    { "action": "capture", "why": "…" },                       // enqueue | search | capture | observe | promote
    { "action": "enqueue", "record": "corpus://…", "why": "…" },
    { "action": "promote", "record": "corpus://…?path=…", "why": "…" },
    { "action": "search", "demand": "hat-colour", "why": "…" } // a blocked demand names its rule (§14)
  ],
  "status": "open",                // §7.3
  "resolution": null,
  "asof": "2026-07-02"
}
```

**`proposes`** is the typed edge between the two state machines: a claim-shaped hypothesis carries its draft claim, so promotion is mechanical — tooling moves the proposed claim into the target fact file at the highest status the bar allows, stamps `resolution` with the claim id, and sets `status: promoted` (`ledger promote <id>`).

### 7.3 Lifecycle

```
             ┌── promoted ──→ the content now lives as claim(s); resolution names them
hypothesis ──┤   (open)
             └── refuted  ──→ TOMBSTONE — kept so future harvesters don't re-infer it

assessment / correction:  standing ──→ retired (superseded / no longer relevant)
```

A `correction` challenging an existing claim names it in **`challenges`** — the typed edge for corrections, as `proposes` is for hypotheses — which pins the claim's content identity as it stood at filing (`state`: a blake3 hash of the claim object's canonical JSON — keys sorted, minimal separators — **excluding `status`**, since the dispute mechanism moves it, and with **each evidence entry canonicalized to its derived citation** (§6.1) so the pin is invariant under source-key renames; verification bindings live on the sources table (§13.2), outside the claim object, so they never enter the hash; stamped and checked by tooling); the challenged claim carries `status: disputed` until resolved, and validation cross-checks the pair. The pin is a guard, not decoration: a claim edited after the challenge flags its correction for **re-review** rather than letting the dispute silently apply to content it never examined — the same drift detection snapshot binding gives evidence (§13.2), extended to the claim the dispute is about.

### 7.4 Generated work-lists

`open-questions.md` carries a generated block over every `open`/`standing` interpretation and its `needs`, plus the stub-concept and completeness frontier — owed fields, unmet expectations, missing timeboxes, and open/blocked demands, all fed by the one demand engine (§4.2, §4.4, §14); hand-curated items live outside the marked block. Edit the interpretation files, never the generated block. One interpretation per checkable statement.

## 8. Vocabulary

Every predicate, qualifier key, concept type, edge type, roster role, value kind (§4.5), and demand rule (§14) in use is registered in the ledger's **`VOCAB.md`** — generated with counts and one-line definitions, never hand-maintained:

- Reuse before minting; a new term lands as a visible diff, never a silent addition.
- Vocabulary grows organically — minted when real evidence needs it, never pre-built. The one sanctioned pre-built form is a **declared import**: an adopted domain bundle's vocabulary (§10, the domain-package seam) enters `VOCAB.md` marked as imported — adoption is itself the evidence of need.
- **Retired vocabulary** stays listed with its reason; using a retired term is a validation error.
- Per-type conventions (e.g. an applicability discipline for vehicle-variant claims) live in `facts/SCHEMA.md` beside the vocabulary they govern; shapes that harden graduate into schemas (§4.4).

## 9. Coverage

The ledger carries the **coverage obligation for the corpus**: every in-scope record should be *represented* — cited as evidence by at least one fact or interpretation, or rostered by a concept (§4.2). `coverage.md` is the generated ledger (covered / backlog / out-of-scope with reasons). A represented-but-shallow topic becomes a coverage-gap assessment with `capture` needs — the ledger is *designed* to generate ingestion demand. Coverage is how the ledger proves the compendium thesis over the corpus: nothing captured goes unrepresented silently.

(Presentation scope is a consumer concern, outside the system (§12). Coverage is not gated by sensitivity — private records are covered, privately.)

## 10. Harvest — mechanical claims

Interpretation is authored; membership and structure often need not be. The ledger MAY declare **harvest rules** — `harvest/{slug}.yaml` — deterministic derivations that sweep the corpus and mint concepts, roster entries, and claims mechanically. Harvest is the ledger-side successor of the corpus's retired `classify_when` engine: the corpus asserts nothing about what its records mean; the same deterministic membership mints knowledge in the layer that owns it.

```yaml
id: metal-archives-bands
description: Materialize a band concept from every Metal Archives band page.
match:                            # deterministic predicate over corpus record facts
  origin.host: {equals: www.metal-archives.com}
  origin.path: {glob: "/bands/*/*"}
mint:                             # templated from the matched record's facts
  concept: { id: "band-{origin.path[2]}", type: band, name: "{origin.path[1]}" }
  roster:  [ { role: documents } ]                 # the matched record, rostered on the concept
  claims:
    - { predicate: "…", value: "…", evidence_kind: direct }
```

Semantics:

- **Deterministic.** A harvest run is a pure function of the corpus's mechanical record facts — no LLM, no network, no clock. The **fact base** is exactly what the corpus pipeline exposes mechanically: `mime`, `origin.uri`/`host`/`path`/`fragment`/`query.<k>`, `origin.id`, any stored origin-block field (`origin.<field>` — producer-declared provenance is mechanical by definition), **`form.id` (the record's section-opener form ids) and `form.<field>` (a whole-record form section's mechanical header fields — codebooks and span envelope facts, mechanical by construction, corpus §7.8)**, `media.<field>` — with the operator grammar (`equals`/`in`/`glob`/`matches`/`exists`; `all_of`/`any_of`/`none_of`; exact-by-default, missing-fact-is-false). Body content — including titles and keywords — is permanently excluded: the canonical false-positive source stays out of deterministic rules.
- **Keyed by the world, never the record.** A minted concept id MUST derive from **origin-native identity** — the source's own stable key exposed in origin facts (a site's entity id in the path, a catalog number in a query param) — never from record identity. A rule that can only key by hash cannot mint concepts (the record-shadow prohibition, §4); it can still roster records onto, and mint claims against, concepts that exist. This is what makes harvest converge: re-captures and mirrors of the same thing match the same key and accumulate as roster entries and evidence on **one** concept.
- **Auto provenance, asserted wins.** Harvested concepts, roster entries, and claims carry `provenance: auto` and are stripped and regenerated on every run (rules or records changed → output converges); anything a human edits loses its `auto` mark and the harvester never touches it again. An auto claim never overwrites an asserted one.
- **Born low.** A harvested claim's evidence is the matched record (span-level where the rule can address it); its status is capped at `provisional` — confirmation is earned through the bar (§5.4), never minted.
- **Registered like everything else.** Harvested types, predicates, and roster roles appear in `VOCAB.md` (§8) with their counts; a new rule lands as a visible diff, and its first run *is* the review surface.

*(Non-normative — the domain-package seam.)* Concept schemas (§4.4), harvest rules (§10), invariants (§11), types + predicates (§8), and per-type authoring conventions (`facts/SCHEMA.md`) are deliberately shaped as **one bundleable unit**: together they are a complete declarative domain model — a music package's song/album/artist schemas and roster roles; a fiction package's character/scene schemas, no-overlap invariants, and narrative-position conventions; a methodology package's condition/parameter types and citation disciplines. A bundling/import mechanism is intentionally deferred until a second real domain demands it; when adopted, a package's vocabulary enters `VOCAB.md` as a **declared import**, never a silent mint — adoption is the evidence of need that the organic-growth rule (§8) requires.

## 11. Invariants

Declared constraints over the fact graph — the **coherence** third of ledger integrity (evidence verification, §13.2, is the **grounding** third; demands, §14, the **completeness** third). An invariant is data, not code: `invariants/{slug}.yaml`:

```yaml
id: residence-no-overlap
description: A person has at most one primary residence at a time.
applies_to: { type: person, predicate: residence }
constraint: temporal-no-overlap
severity: error                  # error | warning
```

Built-in constraint kinds:

| Kind | Holds when |
|---|---|
| `unique` | at most one matching claim per fact file (optionally `per:` a qualifier key — e.g. one price per retailer) |
| `exclusive` | at most one of an enumerated predicate/value set holds per fact file |
| `temporal-no-overlap` | the `period`s of matching claims on one fact file do not overlap |
| `requires` | a matching claim implies another claim exists (predicate template) |
| `cardinality` | matching-claim count per fact file within declared bounds |

Semantics:

- **Deterministic**, run by validation (§13.1); a violation names the exact claims.
- **Resolution is human, and binary**: either the invariant is wrong — amend it, and validation emits the **migration worklist** of claims and dependent notes to revisit — or a claim is wrong — challenge it with a `correction` (§7), sending it to `disputed`. An invariant is never silently bent.
- **Grown organically**, like vocabulary: declare an invariant when a real inconsistency class appears, never ahead of one. A new invariant lands as a visible diff, and its first validation run *is* the audit.

## 12. The consumption contract

The corpus + ledger join is the system's **end product** (Part I §5): an interpreted archive whose every claim is evidence-backed, graded, and sensitivity-derived. Consumers — compilations (the codex estate), expert agents, deliverable pipelines — sit outside the system and read the product under this contract.

Ledger content is referenced as:

```
ledger://{id}                    → a fact (concept or edge) or an interpretation
ledger://{id}:{short}            → a specific claim
```

- **Read knowledge here; never re-author it.** Facts, claims, and interpretations are citable; **generated views are not** — and no consumer's derived prose is a citation target for anything. A consumer that hand-authors facts into its own output has left the contract: knowledge lives in the ledger, authored once. Within the ledger, plain slugs suffice — wikilinks and `object` references resolve by id, following the lineage map (§4.1) so references survive merges and renames.
- **Render the epistemic state honestly.** A consumer surfacing claims carries their ladder position with them — a `provisional` claim MUST NOT present like a `confirmed` one, and interpretive content (standing corrections, open questions) presents as interpretive. The ladder survives into presentation; that is the honesty the ledger bought.
- **Publication filters on sensitivity, fail closed.** What a published deliverable may *contain* is governed by derived sensitivity (§6.4) — a filter over content, never a URI form. A consumer publishing beyond the owner MUST NOT emit private-backed claim content, the ids of fully-private fact files, or evidence bytes and derived assets that resolve only privately; private-backed content is excluded or explicitly stubbed, never leaked. This is the system's publication wall. A publishing consumer SHOULD read exclusively through the read surface's **public plane** (Part I §5.1) — the wall pre-applied in system code, so the obligation is discharged by construction; a consumer with raw instance access bears the obligation unchanged. *(Non-normative: the codex kit's public-profile leak check remains a consumer-side reference for raw-access consumers.)*
- **Pin the tuple when freezing.** A consumer freezing a deliverable SHOULD record its reproducibility tuple — the instance commit, the touch identity of every record cited or resolved (§13.2), and every `ref://` citation's stamped snapshot binding — tag + mirror-artifact blake3 (§6.5, §13.2) — so ledger or corpus movement beneath a frozen build is a *detected transition* (`ath ledger worklist` names the dependents), never silent rot discovered by readers.
- **Evidence resolution materializes; it never originates.** A consumer's own `corpus://`/`ref://` reads happen only to render citations the ledger already asserts (footnotes, embeds, rasters) — never as a second, independent evidence path.

### 12.1 Scope selection and traversal

Compilations are compiled from **scoped** facts; the scope's semantics are specified once, here, and exposed as one library call and as the read surface's query parameters — never re-implemented per consumer. A **scope evaluation** is deterministic: seed, traverse, close.

- **Seed** — the starting set: explicit fact ids; every fact of a type; or the facts matched by a deterministic predicate over fact fields and claim predicates/values, in the operator grammar the ledger already speaks (§10: `equals` / `in` / `glob` / `matches` / `exists`; `all_of` / `any_of` / `none_of`; exact-by-default, missing-is-false).
- **Traverse** — which reference kinds to follow, to what depth: relational claim `object`s, `{"entity": …}` references inside claim values, wikilinks in string values, roster `uri`s, and edge participation (an edge joins the scope when a participant is in it, and its participants are then reachable). Every hop resolves through the lineage map (§4.1) before it counts — a scope never sees a retired id.
- **Close** — the evaluation is a visited-set closure: cycle-safe, order-deterministic (ids sorted at each frontier), reproducible for a given instance commit. **Evidence chasing** is a scope parameter, not a traversal kind: `none` (facts only), `references` (evidence entries carried as URIs), or `resolved` (each citation materialized through the corpus resolver or `ref://` adapter — read-time resolution under the contract above, never an evidence path).

Sensitivity is orthogonal: a scope evaluation computes membership; what a consumer may *emit* from it stays governed by the publication filter — on the public plane and every audience plane alike, the projection for the reader's grant set (§6.4) applies after scoping, fail closed.

## 13. Validation

### 13.1 The check contract

Validation is deterministic, ledger-local plus read-only corpus access. It MUST verify at minimum:

**Structure** — JSON well-formedness; id == filename stem; type == directory; id uniqueness across facts + interpretations; claim-id format and uniqueness; concept/edge shape.

**Sensitivity** — derived sensitivity (§6.4) computes for every claim (all evidence resolves against the corpus or registered datasets, so every visibility determination is total); asserted `sensitivity` overrides are upward only. The tenancy declarations hold: declared tier names are slugs colliding with no reserved name, and audience names are slugs colliding with no plane name (`public`, `private`, `owner` are never audience names — Part I §5.1); every origin-overlay `tenancy:`, the `visibility:` floor, and every audience grant names a **declared** tier — an unknown name is an error, and the record it would have widened stays at the floor until fixed (fail closed); no audience is granted `private`.

**Graph** — no dangling claim `object`s, `about`s, `based_on` claim ids, wikilinks, or `{"entity": <id>}` references inside claim values (§4.4); no relation stored with its inverse; the lineage map (§4.1) satisfies references and resolves in one hop (every value names a living fact, never another key; keys collide with no living id; no fact file carries a retired shape).

**Epistemics** — the authentication bar for every `confirmed` claim, counting only verifiable-surface evidence (§5.4) — per element for array-valued claims, naming each element that fails; `element` bindings well-formed: integer, in range, on an array `value` only; `disputed` ⇄ standing `correction` pairing, with `challenges` pins current (a pinned claim edited since its challenge was filed flags the correction for re-review, §7.3); `reported` claims carrying `attribution`; retired vocabulary unused; `proposes` and `challenges` objects well-formed (against §5.1 and §7.3).

**Evidence** — URI grammar and resolution discipline (§6.2); cited and rostered records exist (bare-hash resolution in the corpus); `ref://` citations name registered datasets — and, when pinned, registered snapshot tags: a pin whose tag is no longer registered is an error, a dangling pin — (§6.5); claim evidence citing a corpus hash registered as a mirror artifact warns — the content's citation surface is `ref://` (§6.5); every citation resolves to a **verifiable surface** and passes §13.2.

**Harvest** — harvested (`provenance: auto`) concepts, roster entries, and claims converge with the current rules (stale output is an error the harvester fixes); no minted id derives from record identity (§10); no auto claim shadows an asserted one; harvested claims respect the `provisional` cap (§10).

**Schemas** — declared schemas (§4.4) hold: relational fields target the declared type(s); field values stay within declared `values`; declared **element** values stay within their `values` and element `entity`s resolve within their `target` type(s); `participant: true` objects name a participant; edge participants match the declared `participants`; roster roles are registered; conformance gaps — owed fields, unmet expectations, and missing timeboxes alike — land on the work-list as frontier, never as stub errors.

**Value kinds** — kind declarations (§4.5) are well-formed: every `constraint:` names a primitive the distribution knows, `required` names declared shape fields, no `value:` references an undeclared or retired kind. Typed claim values parse under their kind's declared shape, each present field checked by its constraint; a field newly typed over nonconforming existing claims, or a kind whose shape changed under standing claims, emits the migration worklist. A **missing** typed field is frontier, never an error.

**Demands** — demand rules (§14) are well-formed: the `when` condition parses under the operator grammar — `id:` `equals`/`in` operands resolve through the lineage map, `related:` names a known `via` kind, carries `edge:` only under `via: edge`, its `where` parses, and no `related:` nests inside a `where` — every owed `field` is declarable vocabulary, a `needs` entry's `demand:` names a declared rule or a named expectation id (§4.4) — never a positional display id — and the demand-rule namespace is collision-free (rule ids and expectation `id:`s unique together). Demand evaluation itself emits **no errors and no warnings** — open and blocked demands are frontier, reported on the work-list only. Filing is never denied.

**Invariants** — every declared invariant (§11) holds; violations name the claims; an amended invariant emits its migration worklist.

**Views** — `VOCAB.md`, `open-questions.md` generated blocks, and `coverage.md` regenerable and current. Validation SHOULD additionally expose the **disagreement view**: attributed (`reported`) claims diverging from `confirmed` claims on the same predicate — the enumerated gap between what voices assert and what evidence establishes, which downstream experts surface as "the community believes X; the evidence says Y."

### 13.2 Evidence verification (the anti-hallucination gate)

Beyond record existence, validation MUST — once per claim edit, and on demand — verify the evidence *content*:

1. **Anchor resolution**: every span parameter resolves against the cited record (the segment address exists; the page/region/time-range is within bounds).
2. **Quote verification**: every `quote` is found verbatim (modulo whitespace and presentational-markup normalization — inline markers such as `<u>…</u>` vanish before matching, so a quote cites the *rendered* text and never truncates around markup) within the content the URI resolves to. The citable content is the record's **faithful rendering** — segment bodies under their form (form-span renderings) and the derivation ops' mechanical output — plus attested byte-facts (artifact-block fields, the members roster, structural byte-marks; §6.3). *(Residue clause)* A record ingested before the corpus's faithfulness sweep may still carry retired descriptive fields; verification reads them **tolerantly** where present — an existing anchor into one still resolves and its quote still checks — but a fresh claim's evidence may never cite one: new evidence cites the faithful rendering or the byte-facts, never a field the corpus grammar no longer writes.
3. **Snapshot binding**: verification records the cited record's content state (its latest `touch` identity) — for `ref://` evidence, the **resolved snapshot's tag and its mirror-artifact blake3** (§6.5): a bare citation resolves through `latest` and is flagged for re-verification when the resolved tag or its artifact hash moves (the hash is the true pin — the config is mutable, the hash is not; a re-pointed tag flags exactly as a moved `latest` does); a pinned citation is drift-free by construction, its residual failure modes being mirror absence (honestly unverifiable) and tag deregistration (a §13.1 error) — on the fact's **sources entry**: one binding per *(fact, source)*, shared by every evidence entry anchored to it, so a later authoring pass or mirror update flags the evidence for re-verification instead of silently rotting. Re-stamping is touch-keyed: an unchanged touch never rewrites the binding. For evidence whose anchored content resolves through a **derivation op** rather than the stored record body, the binding additionally pins the op's version label (`spec/corpus.md` §6.4): the touch chain does not move when resolver tooling upgrades, so the op pin is what flags a derived surface's drift — exactly as the touch flags a re-authored one. The binding's `verified` object carries an **`ops` map** — `"ops": {"<axis-param>": "<engine-pin>"}`, e.g. `{"prop": "vcard-prop@1", "path": "archive-path@1"}` — one entry per derivation-op axis any of that source's evidence resolves through, valued with the engine pin current at stamp time (read from the resolver's own registry introspection, never hand-written). Anchors resolvable from the record's stored body pin nothing — the touch already covers them; only derived-surface resolution pins. At verification, a source whose evidence resolves through an op whose current engine differs from the pinned one is flagged for re-verification (warning), and re-stamping is pin-keyed exactly as it is touch-keyed: an unchanged pin never rewrites the binding. Correspondingly, verification MUST resolve a derived-surface anchor **through the corpus resolver** (the derivation ops themselves — ledger depends on corpus, so this is a library call, never a re-implementation) and check the quote against the derived output; the honestly-unverifiable class narrows to anchors whose op the verifying environment genuinely cannot run (artifact bytes absent, an optional extra not installed), which stay honestly unverifiable, never errors.

Verifying against derived surfaces makes member anchors first-class: a `?path=` member's bytes derive mechanically through their container, so anchors and quotes into members verify like any other surface — no honest citation form remains unverifiable by construction.

4. **Deferred-surface classification**: before any quote matching, the cited record's mime is checked against its declared **citation surface** (corpus §7.1). Evidence citing a `segments`-surface record with **no persisted segments** is classified **`deferred`** — neither failed nor warned: its quotes are held unmatched (record-wide matching against such a surface — a raw HTML DOM's nav chrome, script payloads, inlined framing — produces matches that are structurally misleading rather than merely weak), it stamps no binding, and it is excluded from the §5.4 bar. What such a record already attests mechanically still verifies now: a quote found on an attested byte-fact surface, or an anchor resolving through a derivation op, verifies exactly as on any record — verification checks what is checkable and defers the rest (a quote that *fails* against a mechanically derived surface is still a failure; deferral is never a shield for a wrong quote). Verification **aggregates deferred citations per record** — claim evidence and interpretation references alike — and reports the aggregate as standing normalize demand: the citation is the pressure signal (cite-then-pressure). `raw`-surface records (the default) are unaffected: their record-wide fallback stays legitimate per §6.3. When a deferred record's declared surface lands (its touch moves), the held quotes verify on the next pass — deferral resolves by forming, never by re-authoring evidence.

A claim whose evidence fails verification is flagged at the severity of its status (`confirmed` failing = error; lower rungs = warning). This is the mechanical guarantee behind the system's thesis: a citation is not decoration — it is a checked invariant.

*(Implementation note, non-normative: the shared ledger package (`ath ledger …`) implements this contract. Beyond checking, it ships the revision-workflow generator — `ath ledger worklist`: record → the claims and rosters citing it; fact → its dependents (claims, edges, wikilinks, interpretations); invariant → the claims violating it. Every edit to the durable layer deterministically yields the list of dependents to revisit; the worklist is the revision process, not a lint report. Consumers track their own derived prose's dependence on facts on their side of the boundary — §12's tuple pin is what makes that mechanical.)*

### 13.3 Supersession — following a re-captured record

A corpus record's identity is the blake3 of its bytes (`spec/corpus.md` §2), so a source re-captured with more content lands as a **new** record — a Claude Code session that grew by a few turns (`corpus session capture`, `spec/corpus.md` §12.8) is the motivating case. Citations must follow the content without a human re-checking each one, and without a synthetic stable id papering over the change. **`ath ledger supersede <old> <new>`** does this, gated by **content continuity** (`corpus continuity`, `spec/corpus.md` §12.8): for every ledger citation of `<old>` — fact `sources` entries (judged per referencing evidence entry, anchor by anchor) and roster `artifacts[].uri`s — it re-points the citation to `<new>` (anchors verbatim) **only** where the addressed content is preserved in `<new>` (byte-identical, or contained as a prefix the new capture extends). When every entry riding a sources key is preserved, the key's `record` is rewritten in place; when only some are, the entry **splits** — preserved evidence entries move to a fresh sources key for `<new>`, diverged ones stay behind on `<old>` (the same-target uniqueness rule is satisfied: old and new are distinct records). A citation whose content **diverged** (a compacted or rewritten source) is left untouched and reported for re-anchoring — no quote is silently moved onto content it was never checked against, so no separate "dirty" flag is required: a genuine break stays visibly on the old id, which `check` (§13.1, dangling citation) and `verify` (§13.2, broken anchor/quote) already surface. `--retire` then reclaims the old record's bytes (`corpus rm`), refused while any diverged citation still references it. This is the corpus-citation analogue of the concept-level lineage row (§4.1): lineage followed forward, one content-address to the next, only where the evidence still holds. *(Since the v26 merge, the citation re-point and the record retire land in one commit — the atomicity the two-repo topology could not give it.)*

---

## 14. Demands — the completeness rule layer

Ledger integrity's third third (§11): **grounding** is verified (§13.2), **coherence** is declared (§11), and **completeness** is declared here — rules stating what asserted content *owes*. A demand rule is **data, not code**, evaluated deterministically; the schema declares, the tooling evaluates, the authoring pass judges and satisfies. One rule set, two read modes: **batch** — the §7.4 work-list frontier — and **interactive** — the authoring-time demand surface, the scribe's autocomplete: assert, ask what the assertion now owes, chase.

Schema `expectations:` (§4.4) are the type-local form of the same layer, absorbed unchanged as sugar over the general grammar; cross-type rules land beside the invariants they mirror: `demands/{slug}.yaml`:

```yaml
id: hat-colour
description: An asserted hat owes its colour, from the closed vocabulary.
when:                              # condition over the fact and its one-hop neighborhood —
                                   #   the §10 operator grammar
  claim: { predicate: wearing, value: { in: [hat, cap, beanie] } }
owes:
  - field: hat_colour              # answer shape rides from the field's own declaration
```

- **Conditions are fact-first**: the fact's `id` (the §10 operator grammar over the living id; `equals`/`in` operands resolve through the lineage map (§4.1) so a rule survives merges and renames, while `glob`/`matches` match living ids as written), its `type`, its claims (predicate + value/object match), its roster, and its edge participation (`edge: { {edge-type}: {kind?, with?, target_type?} }` — the §4.4 `when` selector, generalized), composed with `all_of`/`any_of`/`none_of`. Identity exclusion is the idiom for perspective: a rule that owes something of *whoever hosts the appointment* excludes the graph's visiting subject with `none_of: [{id: {equals: …}}]` — data, visible in the rule, honest about whom it exempts.
- **Cross-fact conditions are one hop.** A condition MAY reach a fact's immediate neighbors: `related: { via: {kind}, edge?: …, where?: {condition}, exists?: true|false }`. `via` names a fact-reaching §12.1 traversal kind — `object` | `entity` | `wikilink` | `edge` (with `edge:` carrying the §4.4 selector to narrow which edges count; `roster` is deliberately not among them — roster rows target corpus records, never facts (§4.2), so a roster `via` could never hold and is malformed, not vacuous) — and the neighbor set is that hop, lineage-resolved, exactly as a scope evaluation would take it. `where` is this same condition grammar evaluated against each neighbor, **except `related:` itself — one hop is deliberate**; multi-hop reach is scope's business (§12.1), never a rule condition's. `exists: true` (the default) holds iff some neighbor matches `where` (or any neighbor exists, when `where` is omitted); `exists: false` holds iff none does. Missing-is-false throughout: a fact with no neighbors along `via` fails `exists: true` and passes `exists: false`. Deeper reach — conditions over a closure, aggregate counts — remains the named extension point, landing as amendment to this section, never a redesign: the rule-engine trajectory is intentional, and growth is grammar, not invention.
- **What a demand carries.** The owed field — and, riding along from that field's own declaration (§4.4, §4.5), its answer shape: a value kind, a closed `values:` vocabulary, or a relational `target` type. The demand surface returns demands **with their shapes attached**, so an authoring pass fills a constrained slot rather than free text. (Value-level completeness needs no rule at all: a `money` kind's `required` fields make the currency demand structural — rules cover the conditional cases.)
- **Filing is never denied.** A fact with unmet demands is a legitimate, visible state — the interpretations precedent applied to completeness. A demand is **open** (owed, unmet — frontier, never a validation error), **satisfied** (the demanded claim exists, having cleared the ordinary evidence discipline — demands direct attention and never lower the bar), or **blocked**.
- **Blocked is productive.** A demand unsatisfiable with current sources is declared so — an interpretation whose `needs` entry names the demand (`demand: {rule-id}` beside `action`/`why`, §7.2; the id is a declared `demands/` rule or a **named** expectation (`id:`, §4.4) — a positional `expectation:{type}[{i}]` display id is never a blocking target, and validation says so pointing at the one-line fix) — and that declaration *is* ingestion pressure: "no source attests the birth year" files the `capture`/`search` need naming what to chase. Demand-pull pointed at acquisition: the system asks the world for better sources, and an unsatisfiable demand is a good outcome, not a failure. Blocked state is **derived, never stored**: a demand is blocked while an open interpretation names it; capture lands, the ordinary worklist flags the interpretation, satisfaction re-derives.
- **Anti-churn is mechanical.** Open demands are frontier — `check` output is untouched. The surface returns them grouped per fact, deduplicated per rule firing, blocked state visible. A blocked demand leaves the hot set and does not re-fire while its interpretation stands; it resurfaces when the world changes — new evidence on the fact, or the rule amended (which, like an amended invariant, emits its migration worklist).
- **Honest retraction is the hallucination mitigation.** An authoring pass that cannot ground an answer declares the blocker instead of fabricating one; the constrained answer shape and the ordinary §13.2 gate do the rest. The system *wants* the feelers out — demands exist to provoke them; blocked is how an honest feeler retracts.
- **Grown organically**, like invariants: declare a demand rule when a real completeness class appears; a new rule lands as a visible diff, and its first evaluation is the review surface. Rules and their vocabulary register (§8).

The surfaces: **`ath ledger demands <fact-id>`** (and evaluation against a draft fact file, for mid-authoring use), the read surface's owner-plane demand endpoint, and the §7.4 work-list — all the same deterministic evaluation.

## Appendix A: Worked example (non-normative)

One concept carrying a public claim and a private-backed claim (one file — sensitivity is derived, §6.4), an artifact roster, and a claim-shaped hypothesis with `proposes`:

```jsonc
// ledger/facts/vehicle/pontiac-g8.json
{
  "id": "pontiac-g8", "type": "vehicle", "name": "Pontiac G8",
  "artifacts": [
    { "uri": "corpus://3a71…", "role": "documents", "note": "service manual" }   // rosters keep direct URIs (§6.1)
  ],
  "sources": {
    "s1": { "record": "3a71…<64hex>", "verified": { "touch": "corpus.compile@0.1.0+claude-sonnet-5", "at": "2026-07-11" } },
    "s2": { "record": "9c02…<64hex>" },
    "s3": { "record": "55ab…<64hex>" }
  },
  "claims": [{
    "id": "pontiac-g8:platform", "predicate": "platform", "object": "gm-zeta",
    "status": "confirmed", "asof": "2026-06-30",
    "evidence": [
      { "source": "s1", "anchor": "el=42", "quote": "…built on GM's Zeta platform…", "kind": "authoritative" },
      { "source": "s2", "anchor": "page=3", "kind": "direct" }
    ]
  },
  {
    // 55ab…'s record derives private tenancy → this claim is private-backed (§6.4);
    // public-facing consumers exclude it under the consumption contract (§12)
    "id": "pontiac-g8:owned-by", "predicate": "owned_by", "object": "steven-rahn",
    "status": "confirmed", "asof": "2026-05-12",
    "evidence": [{ "source": "s3", "anchor": "page=1", "quote": "…", "kind": "authoritative", "note": "bill of sale" }]
  }]
}
```

```jsonc
// ledger/interpretations/base-v6-transmission-is-5l40e.json
{
  "id": "base-v6-transmission-is-5l40e", "kind": "hypothesis",
  "about": ["pontiac-g8"], "confidence": "likely",
  "statement": "The base V6's automatic is the 5L40-E.",
  "based_on": ["corpus://71fe…?el=18"],
  "proposes": {
    "id": "pontiac-g8:base-v6-transmission", "predicate": "transmission",
    "object": "5l40e", "qualifiers": { "applies_to": "base-v6" },
    "evidence": [{ "uri": "corpus://71fe…?el=18", "kind": "incidental" }]
  },
  "would_resolve": ["a service-manual spec table naming the V6 transmission"],
  "status": "open", "asof": "2026-07-02"
}
```
