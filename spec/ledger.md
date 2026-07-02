---
spec_id: ATH-LEDGER
title: "Ledger Specification"
version: 1.0
status: current
license: "CC BY-SA 4.0"
date_created: 2026-07-02
date_modified: 2026-07-02
---

# Ledger Specification

## 1. Overview

### 1.1 What this is

The **ledger** is the Athenaeum system's knowledge layer (`spec/athenaeum.md`): the tenant-partitioned fact substrate between the corpora (faithful bytes, `spec/corpus.md`) and the codices (targeted prose compilations, `spec/codex.md`). It holds **facts** — typed claims in which **every claim carries evidence**: `corpus://` URIs into captured bytes, span-precise where verified — and **interpretations**, the pre-assertion workspace beside them.

The name is meant literally: a ledger is claims with evidence and an audit trail. Entries are *posted* (claims — asserted, each with computable trust) or held in *suspense* (interpretations — not yet assertable). The boundary between the two is physical (§1.3), which is what lets every consumer of the fact graph trust that everything in it is asserted knowledge.

### 1.2 The hubs

The ledger is partitioned by tenancy exactly as the corpus layer is — one hub per tenant boundary, each an independent repository:

```
corpus  ────interprets────▶  ledger            (public: self-contained)
corpus-private ─interprets─▶ ledger-private    (private: may extend public entities)
```

- **Placement rule:** a fact lives in the hub matching the **most private evidence it cites**. A claim citing any `corpus-private` record belongs in `ledger-private`, whatever else it cites.
- **The extends rule:** the same entity id in both hubs is **the same entity by definition** — the private hub's file extends the public identity with additional (private) claims. Validation confirms `type`/`name` agreement. A genuinely different private entity MUST NOT reuse a public id.
- **Direction:** the private hub sees the public hub (references its entity ids, cites the public corpus); the public hub is self-contained and never references anything private. The same asymmetry as the corpora.
- One knowledge substrate, many consumers: codices target the ledger; expert agents read it directly. Knowledge is authored once, here — never re-authored per presentation.

### 1.3 The assertion boundary

**Claims are asserted; interpretations are not.** The claim `status` ladder (§5.3) is a state machine over *asserted* knowledge — a claim is born at the lowest rung its evidence supports and is promoted **in place** as evidence accrues. Uncertainty about an asserted claim is ladder position, not a separate file.

An interpretation exists when the epistemic content **isn't claim-shaped** (§7): an identity guess resolving to a graph merge, a working assessment with no settled predicate, negative/corrective knowledge whose job is to tombstone errors, or an ingestion need. Interpretations sit physically beside the facts so that no consumer of `facts/` ever has to filter speculation out of knowledge.

### 1.4 Terminology

| Term | Definition |
|---|---|
| **Hub** | One ledger repository (`ledger`, `ledger-private`); the tenancy partition unit. |
| **Fact file** | JSON under `facts/{type}/{slug}.json` — an entity or an edge, holding claims. |
| **Redirect tombstone** | A fact file reduced to `{id, type, merged_into}` — the lineage a merged or renamed id leaves behind (§4.1). |
| **Claim** | One atomic, typed, **asserted** statement with evidence (§5). |
| **Evidence** | A `corpus://` citation grounding a claim, graded by `kind` (§6). |
| **Interpretation** | A structured **pre-assertion** item: hypothesis, assessment, correction, or need (§7). |
| **Authentication bar** | The evidence threshold for `confirmed` (§5.4). |
| **Harvest rule** | A deterministic derivation minting auto-provenance facts/claims from corpus record facts (§10). |
| **Invariant** | A declared constraint over the fact graph, validated deterministically (§11). |
| **`ledger://` URI** | The external reference form for ledger content: `ledger://{hub}/{id}` or `…/{id}:{claim}` (§12). |

## 2. The hub manifest — `ledger.yaml`

Each hub carries a `ledger.yaml` read by the tooling:

```yaml
name: ledger-private            # == the repo/directory name
description: >-
  …
corpus: corpus-private          # the corpus this hub interprets — cited bare: corpus://{hash}
extends: ledger                 # public hub this one may extend (private hubs only)
```

- `corpus` names a manifest-registered corpus (`spec/athenaeum.md` §2.3); its records are cited with **bare** URIs. Evidence into the *other* tenancy's corpus uses the **qualified** form `corpus://{corpus}/{hash}` and is legal only in the direction tenancy allows (private cites public; never the reverse). Evidence into any undeclared corpus is a validation error.
- `extends` (private hubs) names the public hub whose entity ids may be extended (§1.2).

## 3. Layout

```
ledger[-private]/
├── ledger.yaml
├── CLAUDE.md                  # the hub's operating guide
├── facts/
│   ├── SCHEMA.md              # the fact model + hub conventions
│   ├── VOCAB.md               # GENERATED — vocabulary registry (§8)
│   └── {type}/{slug}.json
├── interpretations/
│   ├── SCHEMA.md
│   └── {slug}.json
├── harvest/
│   └── {slug}.yaml            # mechanical claim-minting rules over the corpus (§10)
├── invariants/
│   └── {slug}.yaml            # declared constraints over the fact graph (§11)
├── open-questions.md          # work-list: generated block + curated items (§7.4)
├── coverage.md                # GENERATED corpus→ledger coverage ledger (§9)
└── docs/                      # process docs — never world knowledge
```

There is no `notes/` in a hub: prose lives in codices. World knowledge lives only in `facts/` + `interpretations/`; the boundary is strict.

## 4. Facts

### 4.1 Identity

Fact and interpretation ids are **readable slugs** (`[a-z0-9]+(-[a-z0-9]+)*`): human-meaningful, wikilink-friendly, stable. The id is the filename stem; a fact's `type` is its parent directory name; both equalities are validated. Ids MUST be unique across a hub's facts *and* interpretations together, and a private hub MUST NOT mint an id that collides with a public id unless it is extending that entity (§1.2).

**Ids carry lineage.** Once minted, an id never silently disappears — external consumers hold `ledger://` URIs (§12) the hub does not control. When entities merge (an identity hypothesis resolving, §7.1) or a slug is renamed, the losing file becomes a **redirect tombstone** — `{"id": "old-slug", "type": "…", "merged_into": "survivor-slug"}` and nothing else; its claims move to the survivor. References (wikilinks, claim `object`s, `ledger://`) resolve through redirects, **one hop only**: merging into an id that is itself a redirect retargets the older tombstone to the final survivor. Outright deletion is reserved for content that should never have existed.

### 4.2 Entity files — `facts/{type}/{slug}.json`

A durable noun and the claims intrinsic to it:

```jsonc
{
  "id": "lateral-raise",           // slug; == filename stem; wikilink target
  "type": "exercise",              // == directory name; types minted as evidence needs them
  "name": "Lateral raise",
  "aliases": ["side raise"],       // optional
  "meta": "…",                     // optional authoring commentary — never a claim, needs no evidence
  "claims": [ /* Claim objects, §5 */ ]
}
```

A bare `{id, type, name}` **stub is valid** — every fact file is independently valid; there is no "incomplete" state. A stub is a signal: it marks the capture frontier and surfaces in the generated work-list. Any entity referenced as a claim `object` or an interpretation's `about` MUST have at least a stub — no dangling references. (A private-hub extension of a public entity repeats only `{id, type, name}` + its private claims.)

### 4.3 Edge files — `facts/{edge-type}/{slug}.json`

A claim cluster not owned by a single entity — an event, an episode, a comparison, a dated series:

```jsonc
{
  "id": "…", "type": "…",
  "subject": "entity-id",          // the primary entity, for edge types that have one
  "participants": ["a", "b"],      // and/or the entities the edge spans
  "title": "…",
  "period": "2026-09",
  "meta": "…",
  "claims": [ /* Claim objects */ ]
}
```

A file is an edge when it carries `subject` and/or `participants`; otherwise it is an entity. Long time-series and episodic clusters belong in edges.

## 5. Claims

### 5.1 The Claim object

```jsonc
{
  "id": "lateral-raise:targets",   // "{file-id}:{short}" — unique within the hub
  "predicate": "targets",          // registered in VOCAB.md (§8)
  "value": "…",                    // literal (string/number/bool/array/object) — ATTRIBUTE claims
  "object": "lateral-deltoid",     // an entity id — RELATIONAL claims
  "qualifiers": { "attribution": "…" },
  "period": "2019/..",             // when the fact HOLDS (§5.2)
  "status": "provisional",         // the ladder (§5.3)
  "asof": "2026-06-22",            // when the fact was OBSERVED
  "reasoning": "…",                // the argument, for anything not stated verbatim by the source
  "evidence": [ /* Evidence objects, §6 — ≥1 unless the file is a pure stub */ ]
}
```

Field semantics:

- **`value` + `object` together is legitimate**: on a relational claim, `object` is the machine edge and `value` a human gloss. One claim's worth of content per claim — if a `value` hides several independently-checkable assertions of different confidence, split it.
- **Structured values over prose blobs**: list-shaped knowledge (form cues, ingredients, steps, spec tables) takes array/object values, one checkable element each.
- **`reasoning`** carries inference rationale — never smuggled into an evidence `note`.
- Wikilinks (`[[slug]]`) in string values are permitted and validated against fact ids (own hub, plus the extended public hub from a private hub).
- Never store a relation *and* its inverse; symmetric relations are stored once. Which side stores a directed relation is a hub convention, documented per type.
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

Every rung is an assertion. Pre-assertion content (a suspicion, a guess) is an interpretation, not a low-status claim (§1.3). A hub MAY retire statuses it has no use for (registered per §8); it MUST NOT mint new ones.

### 5.4 The authentication bar

A claim may be **`confirmed`** only when it has:

> at least one **authoritative** evidence artifact, **or** two or more **independent** records (different corpus hashes, different provenance) — and nothing else in the graph contradicting it.

Validation enforces the bar mechanically. Corroboration is multiple evidence entries on one claim; conflict is `conflicting` with all evidence kept; a graph contradiction is `disputed` plus the challenging `correction`.

## 6. Evidence

### 6.1 The Evidence object

```jsonc
{
  "uri": "corpus://826482aa…?time_range=00:54-00:58",  // the load-bearing field
  "quote": "…",                    // optional verbatim span from the resolved content
  "note": "…",                     // optional human hint about the ARTIFACT (what/why)
  "kind": "direct"                 // authoritative | direct | incidental
}
```

**`kind` grades the artifact so trust is computed, not vibed:**

- `authoritative` — an artifact whose *function* is to certify the datum (a manual for its product's specs, a monograph or government database for a drug's properties, an official statement for its own content). Authority is **scoped**.
- `direct` — a first-party statement in informal media.
- `incidental` — a passing mention or background detail; the weakest grade.

### 6.2 URI discipline

- `uri` MUST be a resolvable `corpus://` URI with the **full 64-hex** blake3. Span parameters (`?el=`, `?page=`, `?time_range=`, `?frame=`, `?page=N&bbox=`, `?path=`, `#anchor`) follow the corpus functional-URI grammar (`spec/corpus.md` §6).
- **Bare = the hub's own corpus** (`ledger.yaml` `corpus:`); **qualified** (`corpus://{corpus}/{hash}`) = the other tenancy's corpus, legal only private-citing-public (§2).
- **Anchor only as precisely as verified.** A record-level cite is always safe; a wrong anchor is bad provenance — worse than none. Segment addresses printed by the corpus tooling (`corpus body` / `corpus toc`) are ground truth; not every valid address materializes under `corpus resolve`, and that alone does not invalidate a citation.
- **Quotes are verbatim spans** of the resolved content at the cited anchor — they exist to be machine-checked (§13.2). Paraphrase belongs in `note` or `reasoning`, never in `quote`.

### 6.3 Source honesty

Only assert what a source shows. Model knowledge is a *lead* for searching or capturing, never evidence. When the needed source is a still-mechanical `draft` record, request normalization (`corpus enqueue`) rather than citing draft text — validation flags evidence whose record is not `normalized`. When the source isn't captured, that is a `capture` need (§7); when the real world could settle it directly, an `observe` need.

## 7. Interpretations

### 7.1 What they are

Structured, evidence-linked **pre-assertion** items, physically beside the facts. A claim that is merely uncertain still lives in `facts/` — that is what the ladder is for. An interpretation exists when the thing itself isn't claim-shaped:

- an **identity guess** — "these two mentions are the same thing"; resolves by a graph merge, not a status bump;
- a **working assessment** — a synthesis with no settled predicate shape (including coverage-gap assessments: "the corpus attests X only shallowly; here is what to capture");
- a **correction** — durable negative/corrective knowledge ("X is NOT attested"; "claim Y is wrong"), including challenges to existing claims; refuted hypotheses stay as **tombstones** so future harvesters don't re-infer them;
- a **need** — an ingestion/verification request, carried on whichever interpretation needs it. Citations found while reading content land here too (as of ATH-CORPUS 2.0 the corpus carries only mechanically-declared references): a source a record cites is a `capture`/`search` need — or, where the domain cares about the citation itself, an edge with span evidence.

### 7.2 The Interpretation object — `interpretations/{slug}.json`

```jsonc
{
  "id": "…",                       // slug; shares the hub id namespace (§4.1)
  "kind": "hypothesis",            // hypothesis | assessment | correction
  "about": ["entity-or-edge-id"],
  "statement": "…",
  "confidence": "likely",          // hypotheses only: speculative | plausible | likely
  "reasoning": "…",
  "based_on": ["corpus://…", "file-id:short"],   // empty = a hunch, not repo material
  "would_resolve": ["…"],
  "proposes": { /* a draft Claim object (§5.1), for claim-shaped hypotheses */ },
  "challenges": { "claim": "file-id:short", "state": "blake3:…" },  // corrections only: the claim under challenge, pinned as it stood (§7.3)
  "needs": [
    { "action": "capture", "why": "…" },                       // enqueue | search | capture | observe
    { "action": "enqueue", "record": "corpus://…", "why": "…" }
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

A `correction` challenging an existing claim names it in **`challenges`** — the typed edge for corrections, as `proposes` is for hypotheses — which pins the claim's content identity as it stood at filing (`state`: a canonical-JSON hash, stamped and checked by tooling); the challenged claim carries `status: disputed` until resolved, and validation cross-checks the pair. The pin is a guard, not decoration: a claim edited after the challenge flags its correction for **re-review** rather than letting the dispute silently apply to content it never examined — the same drift detection snapshot binding gives evidence (§13.2), extended to the claim the dispute is about.

### 7.4 Generated work-lists

`open-questions.md` carries a generated block over every `open`/`standing` interpretation and its `needs`, plus the stub-entity frontier; hand-curated items live outside the marked block. Edit the interpretation files, never the generated block. One interpretation per checkable statement.

## 8. Vocabulary

Every predicate, qualifier key, entity type, and edge type in use is registered in the hub's **`VOCAB.md`** — generated with counts and one-line definitions, never hand-maintained:

- Reuse before minting; a new term lands as a visible diff, never a silent addition.
- Vocabulary grows organically — minted when real evidence needs it, never pre-built. The one sanctioned pre-built form is a **declared import**: an adopted domain bundle's vocabulary (§10, the domain-package seam) enters `VOCAB.md` marked as imported — adoption is itself the evidence of need.
- **Retired vocabulary** stays listed with its reason; using a retired term is a validation error.
- Per-type conventions (e.g. an applicability discipline for vehicle-variant claims) live in the hub's `facts/SCHEMA.md` beside the vocabulary they govern.
- A private hub SHOULD reuse its public hub's vocabulary where meanings coincide; validation surfaces near-duplicate predicates across the pair.

## 9. Coverage

Each hub carries the **coverage obligation for its corpus**: every in-scope record of the corpus it interprets should be *represented* — cited as evidence by at least one fact or interpretation. `coverage.md` is the generated ledger (covered / backlog / out-of-scope with reasons). A represented-but-shallow topic becomes a coverage-gap assessment with `capture` needs — the ledger is *designed* to generate ingestion demand. Coverage is how the hub proves the compendium thesis over its corpus: nothing captured goes unrepresented silently.

(There is no ceding between hubs: each hub covers exactly its own corpus. Presentation scope is a codex concern, `spec/codex.md`.)

## 10. Harvest — mechanical claims

Interpretation is authored; membership and structure often need not be. A hub MAY declare **harvest rules** — `harvest/{slug}.yaml` — deterministic derivations that sweep the corpus the hub interprets and mint facts and claims mechanically. Harvest is the ledger-side successor of the corpus's 1.0 `classify_when` engine (ATH-CORPUS 2.0 §7.4): the corpus stopped asserting what its records mean; the same deterministic membership now mints knowledge in the layer that owns it.

```yaml
id: alldata-procedures
description: Every AllData procedure page is a claim on its vehicle-system entity.
match:                            # deterministic predicate over corpus record facts
  origin.id: {equals: alldata.com}
mint:                             # templated from the matched record's facts
  entity: { id: "…", type: "…", name: "…" }        # stub minted if absent
  claims:
    - { predicate: "…", value: "…", evidence_kind: direct }
```

Semantics:

- **Deterministic.** A harvest run is a pure function of the corpus's mechanical record facts — no LLM, no network, no clock. The **fact base** is exactly what the corpus drafter exposes: `mime`, `origin.uri`/`host`/`path`/`fragment`/`query.<k>`, `origin.id`, `media.<field>` — with the 1.0 `classify_when` operator grammar (`equals`/`in`/`glob`/`matches`/`exists`; `all_of`/`any_of`/`none_of`; exact-by-default, missing-fact-is-false) carried over unchanged. Body keywords are permanently excluded — the canonical false-positive source stays out of deterministic rules.
- **Auto provenance, asserted wins.** Harvested facts and claims carry `provenance: auto` and are stripped and regenerated on every run (rules or records changed → output converges); anything a human edits loses its `auto` mark and the harvester never touches it again. An auto claim never overwrites an asserted one.
- **Born low.** A harvested claim's evidence is the matched record (span-level where the rule can address it); its status is capped at `provisional` — confirmation is earned through the bar (§5.4), never minted.
- **Registered like everything else.** Harvested types and predicates appear in `VOCAB.md` (§8) with their counts; a new rule lands as a visible diff, and its first run *is* the review surface.

*(Non-normative — the domain-package seam.)* Harvest rules (§10), invariants (§11), types + predicates (§8), and per-type authoring conventions (`facts/SCHEMA.md`) are deliberately shaped as **one bundleable unit**: together they are a complete declarative domain model — a fiction package's character/scene types, no-overlap invariants, and narrative-position conventions; a methodology package's condition/parameter types and citation disciplines. A bundling/import mechanism is intentionally deferred until a second real domain demands it; when adopted, a package's vocabulary enters `VOCAB.md` as a **declared import**, never a silent mint — adoption is the evidence of need that the organic-growth rule (§8) requires.

## 11. Invariants

Declared constraints over the fact graph — the **coherence** half of ledger integrity (evidence verification, §13.2, is the **grounding** half). An invariant is data, not code: `invariants/{slug}.yaml`:

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
| `unique` | at most one matching claim per entity (optionally `per:` a qualifier key — e.g. one price per retailer) |
| `exclusive` | at most one of an enumerated predicate/value set holds per entity |
| `temporal-no-overlap` | the `period`s of matching claims on one entity do not overlap |
| `requires` | a matching claim implies another claim exists (predicate template) |
| `cardinality` | matching-claim count per entity within declared bounds |

Semantics:

- **Deterministic**, run by validation (§13.1); a violation names the exact claims.
- **Resolution is human, and binary**: either the invariant is wrong — amend it, and validation emits the **migration worklist** of claims and dependent notes to revisit — or a claim is wrong — challenge it with a `correction` (§7), sending it to `disputed`. An invariant is never silently bent.
- **Hub scope**: the public hub validates its own facts; a private hub validates the *merged view* of extended entities (its claims plus the public claims) against both hubs' invariants — cross-tenancy coherence is checked where visibility allows, privately, and never the reverse.
- **Grown organically**, like vocabulary: declare an invariant when a real inconsistency class appears, never ahead of one. A new invariant lands as a visible diff, and its first validation run *is* the audit.

## 12. Referencing the ledger

External consumers (codices, expert agents, deliverables) reference ledger content as:

```
ledger://{hub}/{id}              → a fact (entity or edge) or an interpretation
ledger://{hub}/{id}:{short}      → a specific claim
```

Facts, claims, and interpretations are citable; **generated views are not**. Within a hub (and from a private hub into its extended public hub), plain slugs suffice — wikilinks and `object` references resolve by id, following redirect tombstones (§4.1) so references survive merges and renames. A codex declares which hubs it targets (`spec/codex.md` §2) and inherits the tenancy rule: a public deliverable never references private-hub content, even by id.

## 13. Validation

### 13.1 The check contract

Validation is deterministic, hub-local plus read-only corpus access. It MUST verify at minimum:

**Structure** — JSON well-formedness; id == filename stem; type == directory; id uniqueness across facts + interpretations; claim-id format and uniqueness; entity/edge shape.

**Hub topology** — extends-rule conformance (id collisions with the public hub are extensions with matching `type`/`name`, or errors); no public-hub reference to anything private.

**Graph** — no dangling claim `object`s, `about`s, `based_on` claim ids, or wikilinks; no relation stored with its inverse; redirect tombstones (§4.1) satisfy references and resolve in one hop (the `merged_into` target exists and is not itself a redirect; a redirect carries no claims).

**Epistemics** — the authentication bar for every `confirmed` claim; `disputed` ⇄ standing `correction` pairing, with `challenges` pins current (a pinned claim edited since its challenge was filed flags the correction for re-review, §7.3); `reported` claims carrying `attribution`; retired vocabulary unused; `proposes` and `challenges` objects well-formed (against §5.1 and §7.3).

**Evidence** — URI grammar and hub discipline (§6.2); cited records exist; cited records are `normalized` (warn when a declared `enqueue` need covers the draft).

**Harvest** — harvested (`provenance: auto`) facts/claims converge with the current rules (stale output is an error the harvester fixes); no auto claim shadows an asserted one; harvested claims respect the `provisional` cap (§10).

**Invariants** — every declared invariant (§11) holds; violations name the claims; an amended invariant emits its migration worklist.

**Views** — `VOCAB.md`, `open-questions.md` generated blocks, and `coverage.md` regenerable and current. Validation SHOULD additionally expose the **disagreement view**: attributed (`reported`) claims diverging from `confirmed` claims on the same predicate — the enumerated gap between what voices assert and what evidence establishes, which downstream experts surface as "the community believes X; the evidence says Y."

### 13.2 Evidence verification (the anti-hallucination gate)

Beyond record existence, validation MUST — once per claim edit, and on demand — verify the evidence *content*:

1. **Anchor resolution**: every span parameter resolves against the cited record (the segment address exists; the page/region/time-range is within bounds).
2. **Quote verification**: every `quote` is found verbatim (modulo whitespace normalization) within the content the URI resolves to.
3. **Snapshot binding**: an evidence entry records the cited record's normalization state (its latest `touch` identity) at verification time, so a later re-normalization flags the evidence for re-verification instead of silently rotting.

A claim whose evidence fails verification is flagged at the severity of its status (`confirmed` failing = error; lower rungs = warning). This is the mechanical guarantee behind the system's thesis: a citation is not decoration — it is a checked invariant.

*(Implementation note, non-normative: the shared ledger package (`ath ledger …`) implements this contract, replacing the per-codex `check.py` copies that preceded the ledger layer. Beyond checking, it ships the revision-workflow generator — `ath ledger worklist`: fact → the notes deriving from it; record → the claims citing it; invariant → the claims violating it. Every edit to the durable layer deterministically yields the list of dependents to revisit; the worklist is the revision process, not a lint report.)*

---

## Appendix A: Worked example (non-normative)

A public-hub entity with an asserted claim, its private-hub extension, and a claim-shaped hypothesis with `proposes`:

```jsonc
// ledger/facts/vehicle/pontiac-g8.json  (public hub)
{
  "id": "pontiac-g8", "type": "vehicle", "name": "Pontiac G8",
  "claims": [{
    "id": "pontiac-g8:platform", "predicate": "platform", "object": "gm-zeta",
    "status": "confirmed", "asof": "2026-06-30",
    "evidence": [
      { "uri": "corpus://3a71…?el=42", "quote": "…built on GM's Zeta platform…", "kind": "authoritative" },
      { "uri": "corpus://9c02…?page=3", "kind": "direct" }
    ]
  }]
}
```

```jsonc
// ledger-private/facts/vehicle/pontiac-g8.json  (extends the public entity)
{
  "id": "pontiac-g8", "type": "vehicle", "name": "Pontiac G8",
  "claims": [{
    "id": "pontiac-g8:owned-by", "predicate": "owned_by", "object": "steven-rahn",
    "status": "confirmed", "asof": "2026-05-12",
    "evidence": [{ "uri": "corpus://55ab…?page=1", "quote": "…", "kind": "authoritative", "note": "bill of sale" }]
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
