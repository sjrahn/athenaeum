---
spec_id: ATH-CODEX
title: "Codex Specification"
version: 1.0
status: current
license: "CC BY-SA 4.0"
date_created: 2026-07-02
date_modified: 2026-07-02
---

# Codex Specification

## 1. Overview

### 1.1 What this is

A **codex** is a domain-scoped knowledge repository in the Athenaeum system (`spec/athenaeum.md`). It interprets one or more corpora (`spec/corpus.md`) into a structured fact graph in which **every claim carries evidence** — `corpus://` URIs into captured bytes, span-precise where verified — and synthesizes regenerable prose views on top. The codex layer is where interpretation lives; the discipline of this specification is what keeps interpretation honest.

This document is normative for a codex's **knowledge representation**: the strata, the file shapes, the claim and evidence envelopes, the epistemic ladder, the interpretation lifecycle, the publication surface, and validation. It is deliberately silent on a codex's **domain**: what to represent, how to scope it, what vocabulary it needs, what its deliverables are — those are the codex's own (§1.3).

### 1.2 The strata

```
corpus             faithful bytes                                (not owned by the codex)
   ↓  interpret & declare
facts/             typed claims (JSON), every claim evidenced     the durable layer
   ↕  hypothesize / challenge / request
interpretations/   not-yet-facts (JSON): hypotheses,              the epistemic workspace
                   assessments, corrections, ingestion needs
   ↓  synthesize & author
notes/             prose (markdown), regenerated from facts       the disposable layer
```

The load-bearing inversion: **facts are durable; notes are regenerable.** A note is a *view* over the fact graph — delete it and regenerate it and nothing is lost, because every sentence traces to a fact and every fact traces to bytes. Never put a claim in a note that isn't backed by a fact; never put a fact in `facts/` without evidence.

**Claims are born interpretive.** Nearly every claim starts as one artifact's voice, once, in one context — accurate *to the artifact* is not accurate *to reality*. The claim `status` ladder (§5.3) records exactly how far each claim has climbed, and promotion happens **in place** as evidence accrues.

### 1.3 Fixed vs codex-owned

**Fixed by this spec:** the strata; the entity/edge/claim/evidence shapes (§4–§6); the epistemic ladder and authentication bar (§5.3–§5.4); the interpretation model and lifecycle (§7); note regenerability and provenance frontmatter (§8); the vocabulary registry mechanism (§9); the publication surface and cross-codex rules (§11); validation (§12).

**Codex-owned:** the domain and its scope rules (including what to cede to sibling codices); the entity/edge type inventory and predicate vocabulary (grown organically, registered per §9); graph shape conventions (a hub-subject codex stores relations radiating from its subject; a polycentric codex stores each relation once on the more specific/dependent side — either is valid, each codex declares its convention in its docs); qualifier conventions; coverage obligations (§10); curation policy; deliverables. Grow all of it organically — add types and predicates when real evidence needs them, never ahead of it.

### 1.4 Terminology

| Term | Definition |
|---|---|
| **Fact file** | A JSON file under `facts/{type}/{slug}.json` — an entity (durable noun) or an edge (claim cluster spanning entities), holding claims. |
| **Claim** | One atomic, typed assertion with evidence: the knowledge atom (§5). |
| **Evidence** | A `corpus://` citation grounding a claim, graded by `kind` (§6). |
| **Interpretation** | A structured not-yet-fact: hypothesis, assessment, correction, or need (§7). |
| **Note** | Regenerable markdown prose derived from facts (§8). |
| **Primary corpus** | The corpus a codex cites with bare URIs (§2, §6.2). |
| **Supporting corpus** | An additional corpus cited with qualified URIs, never the sole basis of a claim (§6.2). |
| **Authentication bar** | The evidence threshold a claim must clear to be `confirmed` (§5.4). |
| **Publication surface** | The set of identifiers a codex exposes for sibling citation via `codex://` (§11). |

## 2. The codex manifest — `codex.yaml`

Every codex carries a `codex.yaml` at its root. It is a **tooling contract, not a hint**: shared tooling and validation read it, and nothing may hardcode what it declares.

```yaml
name: codex-{name}              # == the repo/directory name
display_name: "…"
description: >-                 # the domain and its scope, briefly
  …

primary_corpus: {corpus-name}   # cited bare: corpus://{hash}
supporting_corpora: []          # optional; cited qualified: corpus://{corpus}/{hash}

id_scheme: readable-slug        # the id convention for facts/interpretations (§4.1)
strata: [corpus, facts, interpretations, notes]
```

Rules:

- `primary_corpus` is required and names a manifest-registered corpus (`spec/athenaeum.md` §2.3). `supporting_corpora` entries likewise.
- A codex MUST NOT read a corpus it does not declare. Evidence URIs into undeclared corpora are validation errors. Tenancy flows through this declaration: a person-agnostic codex does not declare the private hub, and validation holds it to that.
- `id_scheme: readable-slug` is the scheme this version specifies (§4.1). The field exists so the scheme is explicit, not assumed.
- Validation resolves corpus roots through the system manifest + this declaration. (Tooling that predates the shared codex package hardcodes relative roots; that is a known interim defect, not license.)

## 3. Layout

```
codex-{name}/
├── codex.yaml
├── CLAUDE.md                  # the codex's operating guide (domain, scope, conventions)
├── facts/
│   ├── SCHEMA.md              # the fact model + this codex's domain deltas
│   ├── VOCAB.md               # GENERATED — the vocabulary registry (§9)
│   └── {type}/{slug}.json     # entity and edge files
├── interpretations/
│   ├── SCHEMA.md
│   └── {slug}.json
├── notes/
│   └── {type}/{Name}.md       # GENERATED prose views
├── open-questions.md          # work-list: generated block + curated items (§7.4)
├── coverage.md                # GENERATED coverage ledger, when §10 is adopted
├── coverage-scope.json        # ceded records, when §10 is adopted
├── tools/                     # per-codex checks (thin; the shared engine is ath codex — §12)
└── docs/                      # process docs (runbooks, conventions) — never world knowledge
```

Everything under `notes/`, `VOCAB.md`, `coverage.md`, and generated blocks is derived — regenerate, don't hand-drift. World knowledge lives only in `facts/` + `interpretations/`; process knowledge lives in `docs/`; the boundary is strict.

## 4. Facts

### 4.1 Identity

Fact and interpretation ids are **readable slugs** (`[a-z0-9]+(-[a-z0-9]+)*`): human-meaningful, Obsidian-wikilink-friendly, and stable. The id is the filename stem; a fact's `type` is its parent directory name; both equalities are validation errors when broken. Ids MUST be unique across the codex's facts *and* interpretations together — they share the publication namespace (§11).

### 4.2 Entity files — `facts/{type}/{slug}.json`

A durable noun and the claims intrinsic to it:

```jsonc
{
  "id": "lateral-raise",           // slug; == filename stem; wikilink target
  "type": "exercise",              // == directory name; types are minted as evidence needs them
  "name": "Lateral raise",         // canonical display name
  "aliases": ["side raise"],       // optional
  "note": "notes/exercise/Lateral Raise.md",  // optional; ONLY a path to the generated note
  "meta": "…",                     // optional authoring commentary — never a claim, needs no evidence
  "claims": [ /* Claim objects, §5 */ ]
}
```

A bare `{id, type, name}` **stub is valid** — every fact file is independently valid, and there is no "incomplete" state. A stub is also a signal: an entity referenced but not yet fleshed out marks the capture frontier and surfaces in the generated work-list (§7.4). Any entity referenced as a claim `object` or in an interpretation's `about` MUST have at least a stub file — no dangling references.

### 4.3 Edge files — `facts/{edge-type}/{slug}.json`

A claim cluster not owned by a single entity — an event, an episode, a comparison, a dated series:

```jsonc
{
  "id": "…", "type": "…",
  "subject": "entity-id",          // the primary entity, for edge types that have one
  "participants": ["a", "b"],      // and/or the entities the edge spans
  "title": "…",
  "period": "2026-09",             // when it holds (§5.2 period grammar)
  "meta": "…",
  "claims": [ /* Claim objects */ ]
}
```

A file is an edge when it carries `subject` and/or `participants`; otherwise it is an entity. Long time-series and episodic clusters belong in edges, not piled onto an entity.

## 5. Claims

### 5.1 The Claim object

```jsonc
{
  "id": "lateral-raise:targets",   // "{file-id}:{short}" — unique within the codex
  "predicate": "targets",          // the attribute or relation (registered in VOCAB.md)
  "value": "…",                    // literal (string/number/bool/array/object) — ATTRIBUTE claims
  "object": "lateral-deltoid",     // an entity id — RELATIONAL claims
  "qualifiers": { "attribution": "…" },   // optional structured extras
  "period": "2019/..",             // when the fact HOLDS
  "status": "provisional",         // the epistemic ladder (§5.3)
  "asof": "2026-06-22",            // when the fact was OBSERVED
  "reasoning": "…",                // the argument, for anything not stated verbatim by the source
  "evidence": [ /* Evidence objects, §6 — ≥1 unless the file is a pure stub */ ]
}
```

Field semantics:

- **`value` + `object` together is legitimate**: on a relational claim, `object` is the machine edge and `value` a human gloss of the tie. Keep the gloss to one claim's worth of content; if a `value` hides several independently-checkable assertions of different confidence, split the claim.
- **Structured values over prose blobs.** List-shaped knowledge (form cues, ingredients, steps, spec tables) takes array/object values, one element per checkable item.
- **`reasoning`** carries inference rationale — never smuggled into an evidence `note` (which describes the artifact, not the argument).
- Wikilinks (`[[slug]]`) inside string values are permitted and validated against fact ids.
- Never store a relation *and* its inverse; symmetric relations are stored once. Which side stores a directed relation is the codex's declared graph convention (§1.3).
- **Attribute the voice.** Advice, technique, opinion, analysis are claims about what someone asserts: `status: reported`, the speaker in the `attribution` qualifier. Two voices stay two claims.

### 5.2 Time

- **`period`** — when the fact is/was true of the world: ISO date, month, or year; range `a/b`; open range `a/..`; `~` prefix for circa. A current fact has an open or absent period; a lapsed one, a closed period.
- **`asof`** — when the supporting observation was made (a record's origin `snapshot` date is the natural choice).
- Time never rides in ad-hoc qualifiers. Time-varying measurements (a price, a status) are datapoints: keep `asof`, put the distinguishing axis in a qualifier, and land long series in an edge.

### 5.3 The epistemic ladder — `status`

Epistemic only; time lives in `period`/`asof`. A claim moves up **in place**; it is never re-filed.

| Status | Meaning |
|---|---|
| `confirmed` | Authenticated per the bar (§5.4). |
| `provisional` | A single non-authoritative source states it directly and plainly. The default birth state; seek corroboration. |
| `inferred` | Deduced from evidence, not stated verbatim — the argument lives in `reasoning`. |
| `reported` | A person asserts it (advice, opinion, testimony); name the voice in `attribution`. |
| `disputed` | A standing, specific reason to doubt it — a `correction` interpretation cites it. Keep the evidence; resolve by corroboration. |
| `conflicting` | Independent sources disagree; keep all evidence, explain per evidence `note`. |

A codex MAY retire statuses it has no use for (registering the retirement per §9); it MUST NOT mint new ones.

### 5.4 The authentication bar

A claim may be **`confirmed`** only when it has:

> at least one **authoritative** evidence artifact, **or** two or more **independent** records (different corpus hashes, different provenance) — and nothing else in the graph contradicting it.

Validation enforces the bar mechanically: a `confirmed` claim that doesn't clear it is flagged for downgrade. Corroboration is simply multiple evidence entries on one claim; when sources conflict, keep both and set `conflicting`; when the graph contradicts an artifact-backed claim, set `disputed` and file the `correction` (§7).

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

- `authoritative` — an artifact whose *function* is to certify the datum (a manual for its product's specs, a monograph or government database entry for a drug's properties, an official statement for its own content). Authority is **scoped**: a manual is authoritative about its product, not the world.
- `direct` — a first-party statement in informal media (a practitioner demonstrating their own technique, a creator stating their own view).
- `incidental` — a passing mention or background detail; the weakest grade.

### 6.2 URI discipline

- `uri` MUST be a resolvable `corpus://` URI with the **full 64-hex** blake3. Span parameters (`?el=`, `?page=`, `?time_range=`, `?frame=`, `?page=N&bbox=`, `?path=`, `#anchor`) follow the corpus functional-URI grammar (`spec/corpus.md` §6).
- **Bare vs qualified:** evidence into the `primary_corpus` uses the bare form `corpus://{hash}`; evidence into a `supporting_corpora` member uses the qualified form `corpus://{corpus}/{hash}`. A bare URI in a codex therefore always means the primary corpus. URIs into undeclared corpora are errors (§2).
- **Supporting evidence never stands alone:** a claim MUST NOT rest solely on supporting-corpus evidence — the primary corpus is where the claim's domain lives; supporting corpora corroborate.
- **Anchor only as precisely as verified.** A record-level cite is always safe; a wrong anchor is bad provenance — worse than none. Segment addresses printed by the corpus tooling (`corpus body` / `corpus toc`) are the ground truth for `el=` / `time_range=` / `frame=`; not every valid address materializes under `corpus resolve`, and that alone does not invalidate a citation.
- **Quotes are verbatim spans** of the resolved content at the cited anchor — they exist to be machine-checked (§12.2). Paraphrase belongs in `note` or `reasoning`, never in `quote`.

### 6.3 Source honesty

Only assert what a source shows. Model knowledge (training data) is a *lead* for searching or capturing, never evidence. When the needed source is a still-mechanical `draft` record, request its normalization (`corpus enqueue`) rather than citing raw draft text — validation flags evidence whose record is not `normalized`. When the source isn't captured at all, that is a `capture` need on an interpretation (§7); when the real world could settle it directly, an `observe` need.

## 7. Interpretations

### 7.1 What they are

Structured, evidence-linked **not-yet-facts**, sitting *beside* the fact layer. A claim that is merely uncertain still lives in `facts/` — that is what the ladder is for. An interpretation exists when the thing itself isn't a typed claim:

- an **identity guess** — "these two mentions are the same thing" (an entity merge has no home on one claim);
- a **working assessment** — a synthesis no single artifact states (including coverage-gap assessments: "the corpus attests X only shallowly; here is what to capture");
- a **correction** — durable negative/corrective knowledge ("X is NOT attested"; "claim Y is wrong"), including challenges to existing facts;
- a **need** — an ingestion/verification request, carried on whichever interpretation needs it.

### 7.2 The Interpretation object — `interpretations/{slug}.json`

```jsonc
{
  "id": "…",                       // slug; shares the id namespace with facts (§4.1)
  "kind": "assessment",            // hypothesis | assessment | correction
  "about": ["entity-or-edge-id"],  // ids this bears on (must exist)
  "statement": "…",
  "confidence": "likely",          // hypotheses only: speculative | plausible | likely
  "reasoning": "…",
  "based_on": ["corpus://…", "file-id:short"],   // corpus URIs and/or claim ids; empty = a hunch, not repo material
  "would_resolve": ["…"],          // hypotheses: what observation settles it
  "needs": [
    { "action": "capture", "why": "…" },                       // enqueue | search | capture | observe
    { "action": "enqueue", "record": "corpus://…", "why": "…" }
  ],
  "status": "standing",            // §7.3
  "resolution": null,              // on promoted/refuted/retired: what happened, and the claim ids / evidence that settled it
  "asof": "2026-07-02"
}
```

### 7.3 Lifecycle

```
             ┌── promoted ──→ the content now lives as claim(s); resolution names them
hypothesis ──┤   (open)
             └── refuted  ──→ TOMBSTONE — kept so future harvesters don't re-infer it

assessment / correction:  standing ──→ retired (superseded / no longer relevant)
```

Promotion mechanics: when evidence lands, author the claim(s) in `facts/` at the highest status the bar allows, set `status: promoted` + `resolution`, keep the file. A `correction` challenging an existing claim names the claim id in `based_on`; the challenged claim carries `status: disputed` until resolved — validation cross-checks the pair.

### 7.4 Generated work-lists

`open-questions.md` carries a generated block over every `open`/`standing` interpretation and its `needs`, plus the stub-entity frontier; hand-curated items live outside the marked block. Edit the interpretation files, never the generated block. One interpretation per checkable statement — don't bundle guesses.

## 8. Notes

Notes are **generated prose views** over the fact graph — Obsidian-flavored markdown under `notes/{type}/{Name}.md`, wikilinking entities and footnoting `corpus://` sources. Frontmatter is the provenance contract:

```yaml
---
entity: lateral-raise            # the fact this note anchors (its `note` field points back)
generated_from:                  # the EXACT fact/interpretation files this note derives from
  - facts/exercise/lateral-raise.json
  - facts/anatomy/lateral-deltoid.json
updated: 2026-07-02
---
```

Rules: a note asserts nothing without a backing fact; interpretive content included from `interpretations/` is visibly marked as such; when facts change, regenerate the affected notes (`generated_from` is how staleness is detected — validation compares note age against its sources). Notes are never citation targets (§11).

## 9. Vocabulary

Every predicate, qualifier key, entity type, and edge type in use is registered in the codex's **`VOCAB.md`** — generated (with counts and one-line definitions) by validation tooling, never hand-maintained. The discipline:

- Reuse before minting; a new term lands as a visible diff to `VOCAB.md`, never a silent addition.
- Vocabulary grows organically — minted when real evidence needs it, never pre-built.
- **Retired vocabulary** stays listed with its retirement reason; using a retired term is a validation error. History is grown, not silently deleted.
- `same_as` is universal (§11.3); `description`/`summary` are honest homes for genuinely prose-shaped content, not escape hatches from atomic claims.

## 10. Coverage (optional module)

A codex MAY adopt a **coverage obligation**: a declared scope of corpus records that should each be *represented* — cited as evidence by at least one fact or interpretation. When adopted:

- `coverage.md` is the generated ledger: covered / backlog / ceded, per record.
- `coverage-scope.json` records **ceded** records (hash → sibling codex + why), keeping the ledger honest without authoring anything out-of-domain.
- A represented-but-shallow topic becomes a coverage-gap assessment with `capture` needs (§7.1) — the codex is *designed* to generate ingestion demand.

Coverage is how a codex proves the compendium thesis over its slice of the corpus: nothing captured goes unrepresented silently.

## 11. The publication surface and cross-codex references

### 11.1 What `codex://` addresses

```
codex://{codex-name}/{id}              → a fact (entity or edge) or an interpretation
codex://{codex-name}/{id}:{short}      → a specific claim
```

The **citable id space** of a codex is exactly its fact ids, claim ids, and interpretation ids — the durable strata. **Notes are not citable** (regenerable views may vanish at any regeneration). Ids are codex-unique across facts and interpretations (§4.1), so the form is unambiguous; resolution goes through the system manifest (`spec/athenaeum.md` §2.3).

### 11.2 The no-internals rule

A codex never reads or references another codex's files, layout, or notes. Sideways integration is *citation of published identifiers* — the same relationship a codex has to any external work. Validation resolves `codex://` references against the target codex's published id space and flags dangles (including after the target renames or retires an id — a rename is a breaking change to citers and should be treated like one).

### 11.3 Cross-codex identity — `same_as`

When two codices describe the same real-world thing, the entity on each side MAY carry a `same_as` claim whose `value` is the `codex://` URI of the counterpart (a same-codex relation targets a local slug in `object` instead). `same_as` is the seed of cross-codex identity; it asserts identity, not agreement — each codex's claims remain its own.

### 11.4 Tenancy

Sideways citation crosses tenant boundaries only in the safe direction: a codex reading the private hub may cite a public codex's ids; a person-agnostic codex citing into a personal codex would leak by reference and is a validation error unless the deployment explicitly allows it.

## 12. Validation

### 12.1 The check contract

Validation is deterministic and repo-local (plus read-only corpus access). It MUST verify at minimum:

**Structure** — JSON well-formedness; id == filename stem; type == directory; id uniqueness across facts + interpretations; claim-id format and uniqueness; entity/edge shape (edge ⇔ `subject`/`participants`).

**Graph** — no dangling claim `object`s, interpretation `about`s, `based_on` claim ids, or `[[wikilinks]]`; `note` fields point at existing note paths; no relation stored with its inverse.

**Epistemics** — the authentication bar for every `confirmed` claim; `disputed` claims paired with a standing `correction` and vice versa; `reported` claims carrying `attribution`; retired vocabulary unused.

**Evidence** — URI grammar (bare = primary, qualified = declared supporting corpus only); cited records exist in the corpus; cited records are `normalized` (warn when a declared `enqueue` need covers the draft); no claim resting solely on supporting-corpus evidence.

**Views** — `VOCAB.md`, `open-questions.md` generated blocks, and (when adopted) `coverage.md` are regenerable and current; note staleness vs `generated_from` sources.

**Publication** — outbound `codex://` references resolve against the target codex's published id space.

### 12.2 Evidence verification (the anti-hallucination gate)

Beyond record existence, validation MUST — once per claim edit, and on demand — verify the evidence *content*:

1. **Anchor resolution**: every span parameter resolves against the cited record (the segment address exists; the page/region/time-range is within bounds).
2. **Quote verification**: every `quote` is found verbatim (modulo whitespace normalization) within the content the URI resolves to.
3. **Snapshot binding**: an evidence entry records the cited record's normalization state (its latest `touch` identity) at verification time, so a later re-normalization of the record flags the evidence for re-verification instead of silently rotting.

A claim whose evidence fails verification is flagged at the severity of its status (`confirmed` failing = error; lower rungs = warning). This is the mechanical guarantee behind the system's thesis: a citation is not decoration — it is a checked invariant.

*(Implementation note, non-normative: §12.1 is implemented today by per-codex `tools/check.py`; §12.2 and manifest-driven corpus resolution land with the shared codex package (`ath codex check`), which replaces the per-codex copies. Until then, §12.2 verification is manual discipline at authoring time.)*

## 13. Operational codices

A codex whose domain is a live system MAY embed an **operating agent** that inspects and acts on that system. The knowledge layer is unchanged — observations land as facts with evidence (ingesting command output, configs, and diagnostics into the appropriate corpus and citing them), and the codex cites the corpus like any other.

The operating side is bounded by an explicit **autonomy contract** in the codex's `CLAUDE.md`: read-only inspection is the default; mutating actions are enumerated, classed (propose vs execute), and anything outside the enumeration requires the owner. An operational codex without a written autonomy contract is read-only by definition.

---

## Appendix A: Worked example (non-normative)

An entity, a claim with span-precise evidence, a challenging interpretation, and the note that renders them:

```jsonc
// facts/exercise/lateral-raise.json
{
  "id": "lateral-raise", "type": "exercise", "name": "Lateral raise",
  "claims": [{
    "id": "lateral-raise:targets",
    "predicate": "targets", "object": "lateral-deltoid",
    "value": "emphasizes the side delt over the front delt when the arm path stays in the scapular plane",
    "status": "provisional", "asof": "2026-06-22",
    "evidence": [{
      "uri": "corpus://826482aa…?time_range=00:54-00:58",
      "quote": "This is going to put a lot more emphasis on the side delt muscle.",
      "note": "form tutorial, creator demonstrating own technique",
      "kind": "direct"
    }]
  }]
}
```

```jsonc
// interpretations/fitness-anatomy-coverage-gap.json
{
  "id": "fitness-anatomy-coverage-gap", "kind": "assessment",
  "about": ["lateral-raise", "lateral-deltoid"],
  "statement": "The corpus attests exercise↔muscle links only via form tutorials; it holds no anatomical source.",
  "reasoning": "Every targets-claim in the fitness cluster is single-voice direct evidence.",
  "based_on": ["lateral-raise:targets"],
  "needs": [{ "action": "capture", "why": "an anatomy/exercise-science reference for the muscle groups the tutorials name" }],
  "status": "standing", "asof": "2026-07-02"
}
```

```markdown
<!-- notes/exercise/Lateral Raise.md -->
---
entity: lateral-raise
generated_from:
  - facts/exercise/lateral-raise.json
  - interpretations/fitness-anatomy-coverage-gap.json
updated: 2026-07-02
---
# Lateral raise
Targets the [[lateral-deltoid]][^1] …
> *Interpretive:* anatomical grounding is thin in the corpus — see the standing coverage-gap assessment.

[^1]: corpus://826482aa…?time_range=00:54-00:58
```
