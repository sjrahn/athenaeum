---
spec_id: ATH-LEDGER
title: "Ledger Specification"
version: 1.6
status: current
license: "CC BY-SA 4.0"
date_created: 2026-07-02
date_modified: 2026-08-07
---

# Ledger Specification

## 1. Overview

### 1.1 What this is

The **ledger** is the Athenaeum system's knowledge layer (`spec/athenaeum.md`): the single fact substrate between the corpora (faithful bytes, `spec/corpus.md`) and the codices (targeted prose compilations, `spec/codex.md`). It holds **concepts** — materialized real-world things (§4) carrying typed claims in which **every claim carries evidence**: `corpus://` URIs into captured bytes (span-precise where verified) and `ref://` URIs into mirrored reference datasets (§6.5) — and **interpretations**, the pre-assertion workspace beside them.

The name is meant literally: a ledger is claims with evidence and an audit trail. Entries are *posted* (claims — asserted, each with computable trust) or held in *suspense* (interpretations — not yet assertable). The boundary between the two is physical (§1.3), which is what lets every consumer of the fact graph trust that everything in it is asserted knowledge.

**Version 1.1** tracks the corpus layers amendment (`spec/corpus.md` 3.1): the corpus `status` field is retired, so citability re-keys from record status to **verifiable surfaces** — a stored rendering under a named form contract, mechanically derived content (engine-pinned), or authored prose (§6.3, §13.1) — and the snapshot binding gains a derivation-op version pin for derived-surface evidence (§13.2). The demand discipline is unchanged in spirit: the ledger raises corpus work by enqueuing, never by authoring records.

**Version 1.2** tracks the corpus derived-editorial amendment (`spec/corpus.md` 3.2): the corpus's authored state dissolves into its form layer, and a record's frontmatter title/description become derived display values (an optional override at most — corpus §4.2.3), so the **"authored prose" verifiable surface narrows to prose the record BODY carries under an authoring touch** — form-span renderings, section-header editorial fields, embed/segment descriptions — never the frontmatter pair (§6.3). Existing evidence is unaffected: quotes anchor into body content, which is exactly the surface that remains.

**Version 1.3** tracks the corpus terminal-forms amendment (`spec/corpus.md` 3.3): a record governed by a **terminal contract** (`form/passthrough` / `form/manifest`) is a **complete source** — its derived surfaces are its permanent citation surface, and evidence resolved against them is **full-strength for status assignment**: the confirmed bar keys to source authority and independence alone, never to form state (§6.3, §8). The normalize-demand signal narrows accordingly: *raise demand when leaning on a formless record* now means formless-**for-now** — a record a rendering contract fits — and enqueuing a terminal record raises nothing, because there is no better surface coming. A manifest record's attested member roster is first-class evidence for containment and existence facts (graded like any direct surface, not incidental).

**Version 1.4** tracks the corpus citation-surface amendment (`spec/corpus.md` §7.1): a mime schema may declare its **citation surface** — `segments` (the record's raw/derived whole-record text is presentation soup; honest citation requires persisted segments) or `raw` (the derived body is faithful; record-wide verbatim quotes are honest — the default). For **claim evidence**, citing a `segments`-surface record that carries no persisted segments is now a verification **error** at any status — the record-wide quote fallback is structurally misleading against such surfaces; the honest move is `enqueue`, then cite (§6.3, §13.2). **Interpretations are exempt**: the pre-assertion workspace exists precisely to hold discoveries the evidence bar cannot yet carry — an interpretation may reference such a record freely, and validation only *warns* when it does so without a matching `enqueue`/`promote` need, so the discovery surfaces AND the normalize demand rides along.

**Version 1.5** settles the derivation-op version pin's binding format — the 1.1 open item (`spec/corpus.md` §12.19 OQ2), demanded by the first derived-surface citations. The sources-entry `verified` binding gains an **`ops` map** (§13.2): engine pins keyed by axis param, recorded at stamp time for every derivation-op-resolved anchor the source's evidence uses; a pin mismatch at verification flags the evidence for re-verification exactly as a touch mismatch does. With it, verification MUST resolve derived-surface anchors through the corpus resolver rather than declaring them unverifiable — the (1.1) "member anchors are first-class" promise, now implemented; the honestly-unverifiable residue narrows to ops the verifying environment genuinely cannot run.

**Version 1.6** reconciles the citable-surface contract against `spec/corpus.md` 3.4–3.12 (§6.3, §13.2) — six amendments this tracking note had never closed (folds #70). The 3.5 faithfulness amendment retired every surface Version 1.2 had named as citable authored prose: section-header/segment descriptions, section entries, and the frontmatter title/description override. Citable surfaces are now the record's **faithful rendering** (segment bodies under their form) and **attested byte-facts** (artifact-block fields, the members roster, structural byte-marks) — nothing else; the per-mime `citation_surface` rule (1.4, above) remains this contract's own mechanism for records whose derived body isn't a citable surface at all. A record swept before the 3.5 faithfulness amendment (corpus §12.27) may still carry a retired descriptive field; verification reads it **tolerantly** where it exists, but it is never a surface new evidence may cite. No implementation change: `ledger/verify.py`'s tolerant read already matches this contract — this version brings the text to what the code does.

### 1.2 One ledger

The corpus layer is tenant-partitioned as a hard repo boundary because corpora are shareable artifacts. The ledger is not shared — it is the system's intermediate representation, consumed only by its owner's tooling and codices — so it is **one repository**, interpreting every corpus it declares (§2):

```
corpus ─────────┐
                ├──interprets──▶  ledger  ──compiles──▶  codices  (the publication surface)
corpus-private ─┘
```

- **Sensitivity is derived, not partitioned.** A claim citing private evidence is **private-backed** (§6.4) — the placement rule of the two-hub design ("a fact lives with its most private evidence") survives as computed metadata instead of repo placement. One thing is one file, whatever mix of sensitivities its claims carry.
- **The wall moves to publication.** Privacy is enforced where it is load-bearing: codex profiles filter on sensitivity, and the public-profile leak check is the hard boundary (`spec/codex.md` §6). Nothing inside the ledger needs a wall — everything inside it is the owner's.
- One knowledge substrate, many consumers: codices target the ledger; expert agents read it directly. Knowledge is authored once, here — never re-authored per presentation.

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
| **Redirect tombstone** | A fact file reduced to `{id, type, merged_into}` — the lineage a merged or renamed id leaves behind (§4.1). |
| **Claim** | One atomic, typed, **asserted** statement with evidence (§5). |
| **Evidence** | A `corpus://` or `ref://` citation grounding a claim, graded by `kind` (§6). |
| **Reference dataset** | A locally-mirrored external database (Wikipedia, MusicBrainz, …), citable as evidence by native id via `ref://` (§6.5). |
| **Sensitivity** | The derived privacy of evidence, claims, and files — computed from where evidence resolves, never partitioned (§6.4). |
| **Interpretation** | A structured **pre-assertion** item: hypothesis, assessment, correction, or need (§7). |
| **Authentication bar** | The evidence threshold for `confirmed` (§5.4). |
| **Harvest rule** | A deterministic derivation minting auto-provenance concepts, roster entries, and claims from corpus record facts, keyed by origin-native identity (§10). |
| **Invariant** | A declared constraint over the fact graph, validated deterministically (§11). |
| **`ledger://` URI** | The external reference form for ledger content: `ledger://{id}` or `…/{id}:{claim}` (§12). |

## 2. The ledger manifest — `ledger.yaml`

The ledger carries a `ledger.yaml` read by the tooling:

```yaml
name: ledger                    # == the repo/directory name
description: >-
  …
corpora: [corpus, corpus-private]   # the corpora this ledger interprets and covers (§9)
```

- `corpora` names manifest-registered corpora (`spec/athenaeum.md` §2.3). Evidence cites records **bare** — `corpus://{hash}` — and resolves by blake3 across the registered corpora (§6.2): a hash either resolves or it doesn't. Which corpus holds the bytes — and hence the evidence's sensitivity — is a **derived property** (§6.4), never URI syntax.
- There is exactly **one ledger per deployment** (§1.2); the manifest registers it like any member.

## 3. Layout

```
ledger/
├── ledger.yaml
├── CLAUDE.md                  # the ledger's operating guide
├── facts/
│   ├── SCHEMA.md              # the fact model + authoring conventions
│   ├── VOCAB.md               # GENERATED — vocabulary registry (§8)
│   └── {type}/{slug}.json
├── schemas/
│   └── {type}.yaml            # concept schemas — declared, validating type shapes (§4.4)
├── interpretations/
│   ├── SCHEMA.md
│   └── {slug}.json
├── harvest/
│   └── {slug}.yaml            # mechanical minting rules over the corpora (§10)
├── invariants/
│   └── {slug}.yaml            # declared constraints over the fact graph (§11)
├── open-questions.md          # work-list: generated block + curated items (§7.4)
├── coverage.md                # GENERATED corpus→ledger coverage ledger, per corpus (§9)
└── docs/                      # process docs — never world knowledge
```

There is no `notes/` in the ledger: prose lives in codices. World knowledge lives only in `facts/` + `interpretations/`; the boundary is strict.

## 4. Facts

Fact files are **concepts** — durable real-world nouns (§4.2) — and **edges**, claim clusters spanning them (§4.3). Entry into the knowledge layer is **materialization**: a fact file exists because a real thing was recognized — a song, a vehicle, a procedure — never because a record arrived. **Records are evidence, never subjects.** No fact file may exist to describe, mirror, or shadow a corpus record, and no id may derive from record identity (§4.1): the corpus asserts nothing about the world; the ledger stores nothing about bytes. Where many records attest the same thing they converge on **one** concept — as evidence on its claims and entries on its artifact roster — deduplication by construction: record-level classification (the 1.0 corpus's classify block) duplicated and diverged precisely because it had no join point.

### 4.1 Identity

Fact and interpretation ids are **readable slugs** (`[a-z0-9]+(--?[a-z0-9]+)*`): human-meaningful, wikilink-friendly, stable. A double hyphen conventionally separates the two sides of a pair edge id (`steven-rahn--greg-rahn`). The id is the filename stem; a fact's `type` is its parent directory name; both equalities are validated. Ids MUST be unique across the ledger's facts *and* interpretations together.

**Identity is real-world identity.** A concept id names the thing, not any record of it. When identity is established mechanically it comes from **origin-native keys** — a source's own stable identifiers exposed in origin facts (§10) — so re-captures and mirrors of the same thing converge on the same concept rather than minting shadows.

**Ids carry lineage.** Once minted, an id never silently disappears — external consumers hold `ledger://` URIs (§12) the ledger does not control. When concepts merge (an identity hypothesis resolving, §7.1) or a slug is renamed, the losing file becomes a **redirect tombstone** — `{"id": "old-slug", "type": "…", "merged_into": "survivor-slug"}` and nothing else; its claims move to the survivor. References (wikilinks, claim `object`s, `ledger://`) resolve through redirects, **one hop only**: merging into an id that is itself a redirect retargets the older tombstone to the final survivor. Outright deletion is reserved for content that should never have existed.

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

**The artifact roster** is the concept→record arrow that replaced 1.0 record classification (ATH-CORPUS 2.0): the corpus stopped declaring "this record is an instance of class X"; the concept now declares "these records are artifacts of me" — many records, one node, nothing dangling. A `role` is registered vocabulary (§8) naming a real relationship to the thing (`documents`, `performance-of`, `tablature-of`, `interview`); a role that cannot be phrased *of/about the concept* is a bucket, not a relationship, and does not belong. Roster entries carry harvest (`auto`) or asserted provenance under the §10 semantics; rostered URIs must resolve (§13).

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

A schema is the declared shape of a fact type — a concept type or an edge type — the 1.0 composite schemas reborn at the layer that owns meaning (ATH-CORPUS 2.0):

```yaml
type: song
description: A recorded or performed musical work.
fields:                          # the type's registered predicates
  appears_on: { target: album, expected: true }  # relational + owed: frontier when missing
  composed_by: { target: artist }  # relational — the claim object must be an `artist`
  length: {}                     # attribute — value shape per SCHEMA.md conventions
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

A field whose value is a **structured array** — a roster of objects, one checkable element each (§5.1) — may declare **`elements:`**, a mapping of element-key to a declaration reusing the per-field grammar above (`values` for an enumerated vocabulary, `target` for a typed fact reference). It validates the objects *inside* the array the way `values`/`target` validate a scalar field:

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

**Entity references resolve — always.** Independent of any `elements` declaration, every `{"entity": <id>}` object inside a claim value MUST resolve to an existing fact (through redirect tombstones, §4.1): the no-dangling-references rule (§4.2) extended to the roster shape structured-array claims carry (§5.1). Codex scope traversal follows these references (`spec/codex.md`), so a dangling one would silently truncate a compilation — validation makes it an error at its source.

Any type's schema may declare **expectations** — conditional owed-ness, the declared half of gap-finding (§7.4):

```yaml
# on schemas/person.yaml — owed only for facts the `when` selects:
expectations:
  - description: close family of steven-rahn — identity coordinates are chase-worthy
    when: { relationship: { kind: [sibling, father-of, mother-of], with: steven-rahn } }
    expect: [date_of_birth, phone, email]
# on schemas/employment.yaml — no `when`: owed on every fact of the type:
expectations:
  - description: every employment episode is timeboxed
    expect: [period]             # the reserved name `period` is the fact's own timebox
```

Semantics:

- **Validating, never generative.** A schema is data the checker reads (like invariants, §11), not code that produces anything. Only mis-shape is an error: a relational field whose object resolves outside its declared `target` (one type, or a list of admissible types — `{ target: [system, component] }` — for relations the graph legitimately makes to several), a field value outside its declared `values`, a declared **element** value outside its `values` or an element `entity` resolving outside its `target` type(s), an object on a `participant: true` field that is not one of the edge's participants, an edge whose participants diverge from the declared `participants` (count or positional type), an unregistered roster role.
- **Stubs stay valid.** A fact missing an owed field is *frontier*, not failure — `expected: true` marks a field owed unconditionally; an `expectations` entry marks its `expect` fields owed on the facts its `when` selects (no `when` — every fact of the type). Either way conformance gaps sharpen the generated work-list (§7.4); they never invalidate a file. The `when` selector names an edge type: a fact is selected when it participates in an edge of that type — restricted, when given, to edges whose `kind` claim takes one of the listed `kind:` values and whose participants include `with:` (a fact is never selected by a `with:` naming itself). Unmarked fields are *admissible, not owed*: they register vocabulary and validate targets, and their absence means nothing (most organizations manufacture nothing). A type with no schema is equally legal: schemas are earned structure, not a gate.
- **Timeboxed fields.** A field may declare `timeboxed: true` — e.g. `residence: { target: place, timeboxed: true }` — meaning every claim under that predicate owes a `period`: an attested residence or employment episode without a timespan is half a fact, and `asof` alone records observation, never duration. Like owed fields, a missing timebox is *frontier* (a labeled chase on the work-list, §7.4), never an error — the gap says "find the start/end", which is exactly how new evidence that widens a period announces where it belongs.
- **Grown organically or imported** — declared when a real shape recurs, or adopted wholesale in a domain package (§10); either way a schema lands as a visible diff and its vocabulary registers (§8).

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
- **Structured values over prose blobs**: list-shaped knowledge (form cues, ingredients, steps, spec tables) takes array/object values, one checkable element each.
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

> at least one **authoritative** evidence artifact, **or** two or more **independent** records (different corpus hashes, different provenance) — and nothing else in the graph contradicting it.

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
  "kind": "direct"                      // authoritative | direct | incidental
}
```

- **Source keys** match `^[a-z][a-z0-9-]{0,31}$`, are local to their fact, and carry no meaning — renames are free (challenge pins canonicalize on the derived citation, §7.3).
- A sources entry carries exactly one of **`record`** (a full 64-hex blake3) or **`ref`** (`{dataset}/{id}`, §6.5). Two entries in one fact naming the same target is a validation error — the table exists so each artifact appears once. Every entry must be referenced by at least one evidence entry (unreferenced = warning); every `evidence.source` must resolve in its own fact's table (unresolved = error).
- The **derived citation** is `corpus://{record}` — plus, when an `anchor` is present, `?` and the anchor verbatim (or the anchor alone when it begins with `#`, the fragment form) — or `ref://{ref}`. All §6.2 discipline applies to the derived form.
- Rosters (`artifacts[].uri`) and interpretation `based_on` lists (§7.2) are references, not evidence: they keep the direct URI form. A draft claim inside `proposes` likewise cites inline (`uri:`) — it has no fact table to reference; `ledger promote` materializes its citations into the target fact's sources table.

**`kind` grades the artifact so trust is computed, not vibed:**

- `authoritative` — an artifact whose *function* is to certify the datum (a manual for its product's specs, a monograph or government database for a drug's properties, an official statement for its own content). Authority is **scoped**.
- `direct` — a first-party statement in informal media.
- `incidental` — a passing mention or background detail; the weakest grade.

### 6.2 Citation discipline

- The derived citation MUST resolve: **`corpus://{hash}`** with the full 64-hex blake3 — anchor span parameters (`el=`, `page=`, `time_range=`, `frame=`, `page=N&bbox=`, `path=`, or a `#fragment`) per the corpus functional-URI grammar (`spec/corpus.md` §6) — or **`ref://{dataset}/{id}`** into a registered reference dataset (§6.5). (Rosters and `based_on` references, which carry direct URIs, obey the same grammar.)
- **Resolution is content-addressed, never scoped.** A hash resolves by blake3 across every corpus in `ledger.yaml` `corpora:` — some corpus satisfies it or none does; there is no per-corpus URI form. Which corpus holds the bytes (and hence the evidence's sensitivity, §6.4) is a derived property, not URI syntax. A hash resolving in no registered corpus is a validation error.
- **Anchor only as precisely as verified.** A record-level cite is always safe; a wrong anchor is bad provenance — worse than none. Segment addresses printed by the corpus tooling (`corpus body` / `corpus toc`) are ground truth. *(1.1)* Every anchor is expected to resolve mechanically — against the record's stored rendering or through a derivation op (`spec/corpus.md` §6.2) — and §13.2 verifies it there; an anchor that cannot be mechanically resolved is a citation defect, not a tolerated form. (An anchor whose surface has no text projection — an image region, an untranscribed span — still resolves and bounds-checks; it simply carries no `quote`.)
- **Quotes are verbatim spans** of the resolved content at the cited anchor — they exist to be machine-checked (§13.2). Paraphrase belongs in `note` or `reasoning`, never in `quote`.

### 6.3 Source honesty

Only assert what a source shows. Model knowledge is a *lead* for searching or capturing, never evidence. *(1.1; the surface set reconciled against corpus 3.12 — folds #70)* Citability keys to **verifiable surfaces**, never to record state: the record's **faithful rendering** — segment bodies under their form (form-span renderings) and a derivation op's mechanical output (engine-pinned, `spec/corpus.md` §6.4) — and **attested byte-facts** (artifact-block fields, the members roster, structural byte-marks, corpus §4.4.6) all verify (§13.2); citing into a formless record's derived body is legitimate evidence, machine-checked like any other, with the op version pinned on the binding (§13.2). The per-mime `citation_surface` rule below (§1.4) is this section's own mechanism for a record whose derived body is not, itself, a citable surface. *(Residue clause, corpus §12.27)* A record ingested before the corpus's 3.5 faithfulness sweep may still carry retired descriptive fields — section-header/segment descriptions, section entries, the frontmatter `title`/`description` override; verification reads them **tolerantly** where they exist (an existing anchor into one still resolves) but they are never a surface **new** evidence may cite — a fresh claim cites the faithful rendering or the byte-facts, never a field the corpus grammar no longer writes. *(1.4)* One carve-out, keyed per-mime: a record whose mime declares `citation_surface: segments` (corpus §7.1 — formats whose raw/derived whole-record text is presentation soup, e.g. captured HTML DOMs) has **no citable surface until persisted segments exist** — claim evidence against such a record is a verification error, never a fallback match; raise `enqueue` demand and cite after the pass. Interpretations remain free to reference it (§13.2) — that is how a discovery read from a raw capture surfaces before it can be asserted. *(1.3)* **Evidence strength never keys to form state**: status assignment (§8) weighs source authority and independence — a claim meeting the confirmed bar on formless-record evidence is confirmed, and a record governed by a **terminal contract** (corpus §7.8) is a complete source whose derived surfaces are permanent, including a manifest record's attested member roster (first-class direct evidence for containment and existence facts). Prefer the **formed** surface where one exists or is declared: span-precise anchors (`turn=`) bind tighter and survive tooling upgrades better than derived-body offsets — so when citing more than incidentally into a formless record whose artifact has a natural markdown shape, **raise demand** with `corpus enqueue` (the queue is standing demand, `spec/corpus.md` §8.5); the ledger contributes by enqueuing, never by authoring records. *(1.3)* The demand signal keys to formless-**for-now** alone: enqueuing a terminal record raises nothing — no better surface is coming — and where a needed surface is a container *member*, the demand is a **`promote`** need (`corpus promote 'corpus://<container-id>?<member-address>'`; then form the promoted record) — never "normalize the container." Promoted members land **bodiless** until formed. When the source isn't captured, that is a `capture` need (§7); when the real world could settle it directly, an `observe` need.

### 6.4 Sensitivity — derived, not declared

Tenancy at the knowledge layer is computed, not partitioned (§1.2):

- **Evidence sensitivity is a lookup.** A cited hash is **private** iff it resolves *only* in private corpora — a corpus is private iff its manifest registration declares it (`visibility:`, default private — fail closed; `spec/athenaeum.md` §2.3). Bytes present in a public corpus are public evidence even if also captured privately. `ref://` evidence is public.
- **A claim is private-backed** iff any of its evidence is private, or it asserts `sensitivity: private`. The override is **upward only** — derived privacy is a floor no assertion lowers. (A claim can be private on public evidence — a claim about your home citing a public map; the reverse cannot exist.)
- **A fact file is private** iff every claim and roster entry it carries is private-backed, or it asserts `sensitivity: private` — existence itself can be the leak.
- Sensitivity gates **nothing inside the ledger** — everything here is the owner's. It is the claim metadata codex profiles filter on and the public-profile leak check enforces (`spec/codex.md` §6): the mandatory profile axis, computed at its source.

### 6.5 Reference datasets — `ref://`

Some sources are linked, not captured. The corpus captures the world's *ephemera* — pages rot, so bytes are frozen under faithfulness obligations. Reference datasets mirror the world's *databases* — Wikipedia, MusicBrainz, OpenStreetMap: versioned, bulk-distributed, queried in place from a local mirror.

- **Citation form: `ref://{dataset}/{id}`** — the dataset's **native identity** (a page slug, an MBID, an OSM element id), never a URL. Datasets are registered in the system manifest (`spec/athenaeum.md` §2.3) with mirror source and snapshot version; a `ref://` into an unregistered dataset is a validation error.
- **Not corpus records.** No blake3, no capture, no record lifecycle, no faithfulness pass. Reproducibility pins on the **mirror snapshot version** (a ZIM date, a dump serial) — recorded at verification exactly as corpus evidence records touch identity (§13.2), and frozen into build certificates (`spec/codex.md` §5).
- **Graded like any evidence.** `kind` applies unchanged: a MusicBrainz release entry is `authoritative` for its own tracklist; a Wikipedia passage is typically `direct` or `incidental`.
- **External identity lands here.** A concept's ids in the world's databases (a Wikidata QID, an MBID) are ordinary claims citing the dataset itself — `predicate: musicbrainz-id`, evidence `ref://musicbrainz/artist/{mbid}` — made once on the concept, never stamped per record (the 1.0 corpus `concept` block's join key, at its correct altitude).
- *(Deferred tooling: the local-mirror resolver is post-reforge. Until it lands, validation checks `ref://` grammar and dataset registration; content verification (§13.2) reports `unverifiable` rather than failing.)*

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
    { "action": "promote", "record": "corpus://…?path=…", "why": "…" }
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

`open-questions.md` carries a generated block over every `open`/`standing` interpretation and its `needs`, plus the stub-concept and schema-conformance frontier — owed fields, unmet expectations, and missing timeboxes (§4.2, §4.4); hand-curated items live outside the marked block. Edit the interpretation files, never the generated block. One interpretation per checkable statement.

## 8. Vocabulary

Every predicate, qualifier key, concept type, edge type, and roster role in use is registered in the ledger's **`VOCAB.md`** — generated with counts and one-line definitions, never hand-maintained:

- Reuse before minting; a new term lands as a visible diff, never a silent addition.
- Vocabulary grows organically — minted when real evidence needs it, never pre-built. The one sanctioned pre-built form is a **declared import**: an adopted domain bundle's vocabulary (§10, the domain-package seam) enters `VOCAB.md` marked as imported — adoption is itself the evidence of need.
- **Retired vocabulary** stays listed with its reason; using a retired term is a validation error.
- Per-type conventions (e.g. an applicability discipline for vehicle-variant claims) live in `facts/SCHEMA.md` beside the vocabulary they govern; shapes that harden graduate into schemas (§4.4).

## 9. Coverage

The ledger carries the **coverage obligation for every corpus it interprets** (`ledger.yaml` `corpora:`): every in-scope record should be *represented* — cited as evidence by at least one fact or interpretation, or rostered by a concept (§4.2). `coverage.md` is the generated ledger, tracked per corpus (covered / backlog / out-of-scope with reasons). A represented-but-shallow topic becomes a coverage-gap assessment with `capture` needs — the ledger is *designed* to generate ingestion demand. Coverage is how the ledger proves the compendium thesis over its corpora: nothing captured goes unrepresented silently.

(Presentation scope is a codex concern, `spec/codex.md`. Coverage is not gated by sensitivity — private records are covered, privately.)

## 10. Harvest — mechanical claims

Interpretation is authored; membership and structure often need not be. The ledger MAY declare **harvest rules** — `harvest/{slug}.yaml` — deterministic derivations that sweep the registered corpora and mint concepts, roster entries, and claims mechanically. Harvest is the ledger-side successor of the corpus's 1.0 `classify_when` engine (ATH-CORPUS 2.0 §7.4): the corpus stopped asserting what its records mean; the same deterministic membership now mints knowledge in the layer that owns it.

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

- **Deterministic.** A harvest run is a pure function of the corpora's mechanical record facts — no LLM, no network, no clock. The **fact base** is exactly what the corpus pipeline exposes mechanically: `mime`, `origin.uri`/`host`/`path`/`fragment`/`query.<k>`, `origin.id`, any stored origin-block field (`origin.<field>` — producer-declared provenance is mechanical by definition), **`form.id` (the record's section-opener form ids) and `form.<field>` (a whole-record form section's mechanical header fields — codebooks and span envelope facts, mechanical by construction, §ATH-CORPUS 7.8)**, `media.<field>` — with the 1.0 `classify_when` operator grammar (`equals`/`in`/`glob`/`matches`/`exists`; `all_of`/`any_of`/`none_of`; exact-by-default, missing-fact-is-false) carried over unchanged. Body content — including titles and keywords — is permanently excluded: the canonical false-positive source stays out of deterministic rules.
- **Keyed by the world, never the record.** A minted concept id MUST derive from **origin-native identity** — the source's own stable key exposed in origin facts (a site's entity id in the path, a catalog number in a query param) — never from record identity. A rule that can only key by hash cannot mint concepts (the record-shadow prohibition, §4); it can still roster records onto, and mint claims against, concepts that exist. This is what makes harvest converge: re-captures and mirrors of the same thing match the same key and accumulate as roster entries and evidence on **one** concept.
- **Auto provenance, asserted wins.** Harvested concepts, roster entries, and claims carry `provenance: auto` and are stripped and regenerated on every run (rules or records changed → output converges); anything a human edits loses its `auto` mark and the harvester never touches it again. An auto claim never overwrites an asserted one.
- **Born low.** A harvested claim's evidence is the matched record (span-level where the rule can address it); its status is capped at `provisional` — confirmation is earned through the bar (§5.4), never minted.
- **Registered like everything else.** Harvested types, predicates, and roster roles appear in `VOCAB.md` (§8) with their counts; a new rule lands as a visible diff, and its first run *is* the review surface.

*(Non-normative — the domain-package seam.)* Concept schemas (§4.4), harvest rules (§10), invariants (§11), types + predicates (§8), and per-type authoring conventions (`facts/SCHEMA.md`) are deliberately shaped as **one bundleable unit**: together they are a complete declarative domain model — a music package's song/album/artist schemas and roster roles; a fiction package's character/scene schemas, no-overlap invariants, and narrative-position conventions; a methodology package's condition/parameter types and citation disciplines. A bundling/import mechanism is intentionally deferred until a second real domain demands it; when adopted, a package's vocabulary enters `VOCAB.md` as a **declared import**, never a silent mint — adoption is the evidence of need that the organic-growth rule (§8) requires.

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
| `unique` | at most one matching claim per fact file (optionally `per:` a qualifier key — e.g. one price per retailer) |
| `exclusive` | at most one of an enumerated predicate/value set holds per fact file |
| `temporal-no-overlap` | the `period`s of matching claims on one fact file do not overlap |
| `requires` | a matching claim implies another claim exists (predicate template) |
| `cardinality` | matching-claim count per fact file within declared bounds |

Semantics:

- **Deterministic**, run by validation (§13.1); a violation names the exact claims.
- **Resolution is human, and binary**: either the invariant is wrong — amend it, and validation emits the **migration worklist** of claims and dependent notes to revisit — or a claim is wrong — challenge it with a `correction` (§7), sending it to `disputed`. An invariant is never silently bent.
- **Grown organically**, like vocabulary: declare an invariant when a real inconsistency class appears, never ahead of one. A new invariant lands as a visible diff, and its first validation run *is* the audit.

## 12. Referencing the ledger

External consumers (codices, expert agents, deliverables) reference ledger content as:

```
ledger://{id}                    → a fact (concept or edge) or an interpretation
ledger://{id}:{short}            → a specific claim
```

Facts, claims, and interpretations are citable; **generated views are not**. Within the ledger, plain slugs suffice — wikilinks and `object` references resolve by id, following redirect tombstones (§4.1) so references survive merges and renames. What a published deliverable may *contain* is governed by sensitivity (§6.4) and the codex profile's leak check (`spec/codex.md` §6) — a filter over content, never a URI form.

## 13. Validation

### 13.1 The check contract

Validation is deterministic, ledger-local plus read-only corpus access. It MUST verify at minimum:

**Structure** — JSON well-formedness; id == filename stem; type == directory; id uniqueness across facts + interpretations; claim-id format and uniqueness; concept/edge shape.

**Sensitivity** — derived sensitivity (§6.4) computes for every claim (all evidence resolves against registered corpora or datasets, so the private/public determination is total); asserted `sensitivity` overrides are upward only.

**Graph** — no dangling claim `object`s, `about`s, `based_on` claim ids, wikilinks, or `{"entity": <id>}` references inside claim values (§4.4); no relation stored with its inverse; redirect tombstones (§4.1) satisfy references and resolve in one hop (the `merged_into` target exists and is not itself a redirect; a redirect carries no claims).

**Epistemics** — the authentication bar for every `confirmed` claim; `disputed` ⇄ standing `correction` pairing, with `challenges` pins current (a pinned claim edited since its challenge was filed flags the correction for re-review, §7.3); `reported` claims carrying `attribution`; retired vocabulary unused; `proposes` and `challenges` objects well-formed (against §5.1 and §7.3).

**Evidence** — URI grammar and resolution discipline (§6.2); cited and rostered records exist (bare-hash resolution across the registered corpora); `ref://` citations name registered datasets (§6.5); *(1.1)* every citation resolves to a **verifiable surface** and passes §13.2 — the 1.0 cited-records-are-`normalized` check retires with the corpus `status` field (`spec/corpus.md` §4.1).

**Harvest** — harvested (`provenance: auto`) concepts, roster entries, and claims converge with the current rules (stale output is an error the harvester fixes); no minted id derives from record identity (§10); no auto claim shadows an asserted one; harvested claims respect the `provisional` cap (§10).

**Schemas** — declared schemas (§4.4) hold: relational fields target the declared type(s); field values stay within declared `values`; declared **element** values stay within their `values` and element `entity`s resolve within their `target` type(s); `participant: true` objects name a participant; edge participants match the declared `participants`; roster roles are registered; conformance gaps — owed fields, unmet expectations, and missing timeboxes alike — land on the work-list as frontier, never as stub errors.

**Invariants** — every declared invariant (§11) holds; violations name the claims; an amended invariant emits its migration worklist.

**Views** — `VOCAB.md`, `open-questions.md` generated blocks, and `coverage.md` regenerable and current. Validation SHOULD additionally expose the **disagreement view**: attributed (`reported`) claims diverging from `confirmed` claims on the same predicate — the enumerated gap between what voices assert and what evidence establishes, which downstream experts surface as "the community believes X; the evidence says Y."

### 13.2 Evidence verification (the anti-hallucination gate)

Beyond record existence, validation MUST — once per claim edit, and on demand — verify the evidence *content*:

1. **Anchor resolution**: every span parameter resolves against the cited record (the segment address exists; the page/region/time-range is within bounds).
2. **Quote verification**: every `quote` is found verbatim (modulo whitespace and presentational-markup normalization — inline markers such as `<u>…</u>` vanish before matching, so a quote cites the *rendered* text and never truncates around markup) within the content the URI resolves to. The citable content is the record's **faithful rendering** — segment bodies under their form (form-span renderings) and the derivation ops' mechanical output — plus attested byte-facts (artifact-block fields, the members roster, structural byte-marks; §6.3). *(Residue clause, corpus §12.27)* A record ingested before the 3.5 faithfulness sweep may still carry retired descriptive fields (embed/segment descriptions, section entries, the frontmatter title/description override); verification reads them **tolerantly** where present — an existing anchor into one still resolves and its quote still checks — but a fresh claim's evidence may never cite one: new evidence cites the faithful rendering or the byte-facts, never a field the corpus grammar no longer writes.
3. **Snapshot binding**: verification records the cited record's content state (its latest `touch` identity) — for `ref://` evidence, the dataset's mirror snapshot version (§6.5) — on the fact's **sources entry**: one binding per *(fact, source)*, shared by every evidence entry anchored to it, so a later authoring pass or mirror update flags the evidence for re-verification instead of silently rotting. Re-stamping is touch-keyed: an unchanged touch never rewrites the binding. *(1.1)* For evidence whose anchored content resolves through a **derivation op** rather than the stored record body, the binding additionally pins the op's version label (`spec/corpus.md` §6.4): the touch chain does not move when resolver tooling upgrades, so the op pin is what flags a derived surface's drift — exactly as the touch flags a re-authored one. *(1.5 — the format, settled:)* the binding's `verified` object carries an **`ops` map** — `"ops": {"<axis-param>": "<engine-pin>"}`, e.g. `{"prop": "vcard-prop@1", "path": "archive-path@1"}` — one entry per derivation-op axis any of that source's evidence resolves through, valued with the engine pin current at stamp time (read from the resolver's own registry introspection, never hand-written). Anchors resolvable from the record's stored body pin nothing — the touch already covers them; only derived-surface resolution pins. At verification, a source whose evidence resolves through an op whose current engine differs from the pinned one is flagged for re-verification (warning), and re-stamping is pin-keyed exactly as it is touch-keyed: an unchanged pin never rewrites the binding. *(1.5)* Correspondingly, verification MUST resolve a derived-surface anchor **through the corpus resolver** (the derivation ops themselves — ledger depends on corpus, so this is a library call, never a re-implementation) and check the quote against the derived output; the former "anchor the record markdown cannot resolve — unverifiable" class narrows to anchors whose op the verifying environment genuinely cannot run (artifact bytes absent, an optional extra not installed), which stay honestly unverifiable, never errors.

*(1.1)* Verifying against derived surfaces makes member anchors first-class: a `?path=` member's bytes derive mechanically through their container, so anchors and quotes into members verify like any other surface — no honest citation form remains unverifiable by construction.

4. **Citation-surface gate** *(1.4)*: before any quote matching, the cited record's mime is checked against its declared **citation surface** (corpus §7.1). A `segments`-surface record with **no persisted segments** fails claim evidence outright — an **error regardless of claim status**, reported with the `enqueue` demand — because record-wide matching against such a surface (a raw HTML DOM's nav chrome, script payloads, inlined framing) produces matches that are structurally misleading rather than merely weak. `raw`-surface records (the default) are unaffected: their record-wide fallback stays legitimate per §6.3. **Interpretation references are exempt** from the error — the pre-assertion workspace holds what cannot yet be verified — but an interpretation referencing a segment-less `segments`-surface record without a matching `enqueue`/`promote` need draws a **warning**: type the demand beside the discovery.

A claim whose evidence fails verification is flagged at the severity of its status (`confirmed` failing = error; lower rungs = warning). This is the mechanical guarantee behind the system's thesis: a citation is not decoration — it is a checked invariant.

*(Implementation note, non-normative: the shared ledger package (`ath ledger …`) implements this contract, replacing the per-codex `check.py` copies that preceded the ledger layer. Beyond checking, it ships the revision-workflow generator — `ath ledger worklist`: fact → the notes deriving from it; record → the claims citing it; invariant → the claims violating it. Every edit to the durable layer deterministically yields the list of dependents to revisit; the worklist is the revision process, not a lint report.)*

### 13.3 Supersession — following a re-captured record

A corpus record's identity is the blake3 of its bytes (`spec/corpus.md` §2), so a source re-captured with more content lands as a **new** record — a Claude Code session that grew by a few turns (`corpus session capture`, `spec/corpus.md` §12.8) is the motivating case. Citations must follow the content without a human re-checking each one, and without a synthetic stable id papering over the change. **`ath ledger supersede <old> <new>`** does this, gated by **content continuity** (`corpus continuity`, `spec/corpus.md` §12.8): for every ledger citation of `<old>` — fact `sources` entries (judged per referencing evidence entry, anchor by anchor) and roster `artifacts[].uri`s — it re-points the citation to `<new>` (anchors verbatim) **only** where the addressed content is preserved in `<new>` (byte-identical, or contained as a prefix the new capture extends). When every entry riding a sources key is preserved, the key's `record` is rewritten in place; when only some are, the entry **splits** — preserved evidence entries move to a fresh sources key for `<new>`, diverged ones stay behind on `<old>` (the same-target uniqueness rule is satisfied: old and new are distinct records). A citation whose content **diverged** (a compacted or rewritten source) is left untouched and reported for re-anchoring — no quote is silently moved onto content it was never checked against, so no separate "dirty" flag is required: a genuine break stays visibly on the old id, which `check` (§13.1, dangling citation) and `verify` (§13.2, broken anchor/quote) already surface. `--retire` then reclaims the old record's bytes (`corpus rm`), refused while any diverged citation still references it. This is the corpus-citation analogue of the concept-level `merged_into` redirect (§4.1): lineage followed forward, one content-address to the next, only where the evidence still holds.

---

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
    // 55ab… resolves only in corpus-private → this claim is private-backed (§6.4);
    // public codex profiles filter it, and the leak check enforces that (spec/codex.md §6)
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
