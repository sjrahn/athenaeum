---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 13
status: current
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-07-12
---

# Athenaeum — Architecture Specification

## 1. Overview

### 1.1 What this is

The Athenaeum is a knowledge normalization and curation system. It captures artifacts from any source, normalizes each into a faithful, content-addressed record, interprets those records into an evidence-backed fact substrate, and compiles targeted compendiums on top — prose whose every assertion traces, at span level, back to captured bytes. The thesis: knowledge cited precisely enough that the expert agents drawing on it cannot hallucinate their grounding.

The system has three data layers and one driver:

- **The corpus layer is the foundation — the bytes.** A corpus is a content-addressed archive of captured artifacts, each identified by the blake3 hash of its bytes and represented by a faithful markdown record. Corpora are the unit of tenant isolation. The corpus contract is **`spec/corpus.md`** (ATH-CORPUS).

- **The ledger layer is the knowledge — the claims.** The ledger is the single fact substrate: **concepts** (materialized real-world things) and edges carrying typed claims in which every claim carries `corpus://`/`ref://` evidence, with an epistemic status ladder, plus the pre-assertion workspace (interpretations) beside them. Knowledge is authored once, here; privacy is derived sensitivity, not a partition. The ledger contract is **`spec/ledger.md`** (ATH-LEDGER).

- **The codex layer is the expertise — the compendiums.** A codex is a targeting of ledger facts that compiles to prose: a scope, an editorial voice, a generated Obsidian vault, and a published deliverable with every reference resolved. Codices own no knowledge and are cheap to mint. The codex contract is **`spec/codex.md`** (ATH-CODEX).

- **The orchestrator is the definition and the driver.** One repository — `athenaeum/athenaeum`, the eponymous repo of the system's org — holds the specifications, the shared tooling (the `athenaeum` distribution: the `ath` and `corpus` CLIs), the member manifest, and the resident principal-developer persona. Every other component is an independent member repo registered in the manifest.

### 1.2 Design principles

1. **Layered foundation.** The corpus depends on nothing; the ledger depends on the corpora; a codex depends on the ledger. Each layer knows nothing of the layers above it. References point downward only.
2. **Tenant isolation is a repo boundary where sharing lives.** Public and private corpora are separate repositories with mutually exclusive content — corpora are shareable artifacts, so their wall is physical. The ledger above them is deliberately **one repository** (the system's intermediate representation, never itself shared); privacy there is *derived sensitivity* on claims (`spec/ledger.md` §6.4), and becomes a hard boundary again exactly where content goes public: the codex build's leak check. No tooling, schema, or convention may blur tenants at the corpus layer or pass private-backed content through a public profile.
3. **Content addressing.** An artifact's identity is the blake3 hash of its bytes — permanent, and identical in every corpus that holds those bytes.
4. **Faithfulness below, interpretation above.** Corpus records are faithful renderings that add no information; interpretation lives in the ledger, where every interpretive move carries evidence and an epistemic status; editorial voice lives in the codices, where every sentence traces to a ledger fact.
5. **Evidence is the contract between the layers.** A ledger claim cites `corpus://` URIs — resolved by blake3 across the corpora, optionally span-precise (`?el=`, `?page=`, `?time_range=`, `?bbox=`) — or `ref://` citations into mirrored reference datasets, and the system's validation verifies those citations mechanically: anchors resolve, quotes match verbatim, re-normalized records and updated mirrors flag their citers. Traceability is not a style; it is a checked invariant.
6. **Members are config-driven.** The manifest (§2.3) and each codex's `codex.yaml` are the only places membership and joins are declared. Shared tooling never hardcodes a member path or id; a third party points the same tooling at their own org, corpora, and codices.
7. **Deterministic before LLM.** Every pipeline stage whose output is a function of its input is a script; every stage requiring judgment is an agent pass. The boundary is sharp so each stage's outputs are auditable and independently re-runnable.
8. **Durable vs regenerable, everywhere.** Tracked content is durable and reviewed (records, facts, schemas, specs); derived content (caches, resolved views, notes, build outputs) is regenerable and disposable. The same inversion appears at every layer.
9. **Offline-first.** Only capture requires network access. Everything else — normalization, authoring, validation, resolution — operates on local data.
10. **No transitionary states.** Every landed change leaves the system whole. Scaffolding deletes itself when it graduates; history files away under git tags, never in the working tree.

### 1.3 Terminology

| Term | Definition |
|---|---|
| **Orchestrator repo** | `athenaeum/athenaeum` — the system's definition (specs), tooling (`tools/`), member manifest (`athenaeum.yaml`), and driver persona. Its working tree is the workspace root; members are cloned beneath it at ignored paths. |
| **Member** | An independent git repository registered in the manifest: a corpus or a codex. Members live in the same forge org as the orchestrator repo. |
| **Manifest** | `athenaeum.yaml` at the orchestrator root — the single registry of members and the runtime join the tooling reads (§2.3). |
| **Corpus** | A content-addressed archive of artifacts with faithful markdown records; the unit of tenant isolation. Contract: `spec/corpus.md`. |
| **Ledger** | The single fact substrate: concepts + edges holding asserted claims with evidence, plus interpretations (the pre-assertion workspace). One repository interpreting every corpus; privacy is derived sensitivity, walled at the codex build. Contract: `spec/ledger.md`. |
| **Concept** | A materialized real-world thing in the ledger — typed, optionally schema-shaped; records are its evidence and artifact roster, never its identity (`spec/ledger.md` §4). |
| **Codex** | A targeting of ledger facts that compiles to prose: scope + voice + generated vault + published deliverable. Owns no knowledge. Contract: `spec/codex.md`. |
| **Artifact record** | One captured file's faithful markdown proxy in a corpus, named by the blake3 of its bytes. |
| **Fact / Claim / Evidence** | The ledger's knowledge atoms: a fact file (concept or edge) holds typed claims; each claim carries evidence entries whose `corpus://` / `ref://` URIs ground it in captured bytes or mirrored reference datasets. |
| **Reference dataset** | A locally-mirrored external database (Wikipedia, MusicBrainz, OpenStreetMap, …) citable as evidence by native id + snapshot version via `ref://` (`spec/ledger.md` §6.5). |
| **`corpus://` URI** | The evidence-citation primitive: `corpus://{hash}` with optional span parameters, resolved by blake3 across the registered corpora. Grammar: `spec/corpus.md` §6. |
| **`ledger://` URI** | The knowledge-reference primitive: `ledger://{id}` (or `…/{id}:{claim}`) referencing a fact, claim, or interpretation — external consumers read knowledge here, never from a codex's prose (`spec/ledger.md` §12). |
| **Normalizer** | The interpretive agent pass that takes a record from mechanical `draft` to faithful `normalized`. |
| **Orchestrator persona** | The system-resident principal-developer persona in the orchestrator repo, with cross-member scope — the system's one persona; member repos carry none. |

## 2. Topology

### 2.1 The org is the container

The system lives in one forge organization (the reference deployment: Forgejo at `code.example.org/athenaeum`). The org contains the orchestrator repo and every member repo as siblings. Org membership and repo visibility are the outermost access-control surface — which is what makes the repo boundary a real tenant boundary (§1.2 principle 2).

### 2.2 On-disk layout

The orchestrator repo's working tree is the workspace; members are cloned inside it at paths the repo ignores:

```
athenaeum/                        ← working tree of athenaeum/athenaeum
├── athenaeum.yaml                ← the member manifest (§2.3)
├── spec/                         ← this document + corpus.md + ledger.md + codex.md
├── tools/                        ← the `athenaeum` distribution (§6)
├── .claude/skills/orchestrator/  ← the driver persona + its institutional memory
├── corpora/                      ← members, UNTRACKED
│   ├── corpus/                   ←   public hub (bytes)
│   └── corpus-private/           ←   private hub (bytes)
├── ledger/                       ← member, UNTRACKED — the knowledge layer (one repo, spec/ledger.md §1.2)
└── codices/                      ← members, UNTRACKED
    └── codex-{name}/
```

Grouping directories (`corpora/`, `codices/`) mirror the manifest's structure and keep the orchestrator's tracked tree small and hot while member data stays heavy and cold. Nothing above requires this exact machine layout — the manifest is authoritative, and member `path:` overrides exist — but it is the reference shape and the path convention's default.

### 2.3 The manifest

`athenaeum.yaml` is the single registry of members and the join the tooling reads. Nothing else — no tool, schema, or doc — may hardcode a member's location.

```yaml
org: https://code.example.org/athenaeum   # remote base: {org}/{name}.git

corpora:
  {name}:
    description: …        # the member's role, one line
    visibility: …          # public | private — DEFAULT private (fail closed); the declared
                           # tenancy that drives derived sensitivity (spec/ledger.md §6.4)
    path: …                # optional — default corpora/{name}
    remote: …              # optional — default {org}/{name}.git
ledger:
  {name}:                  # exactly one (spec/ledger.md §1.2)
    description: …
    path: …                # optional — default {name}/ at the workspace root
    remote: …
codices:
  {name}:
    description: …
    path: …                # optional — default codices/{name}
    remote: …

references:                # reference datasets (spec/ledger.md §6.5) — mirrored databases, not git members
  {dataset}:
    description: …
    mirror: …              # the local mirror source (a ZIM file, a dump, an extract)
    snapshot: …            # the pinned snapshot version cited by evidence verification
```

Members are keyed by name; manifest order is presentation order. The manifest records **membership, not pins** — members are living repos, and the tooling synchronizes them (`ath sync`: clone missing, fetch and report the rest, fast-forward only on request). A deployment bootstraps by cloning the orchestrator repo and running `ath sync`.

### 2.4 Reference directions

```
ledger ──corpus://──▶ corpora          (downward: claim evidence, blake3-resolved, span-precise)
ledger ──ref://──▶ reference mirrors   (downward: linked external databases, snapshot-pinned)
codex ──scope──▶ ledger                (downward: targeting; notes derive from facts)
consumers ──ledger://──▶ ledger        (external knowledge reads: agents, deliverables)
corpus ──▶ (nothing)                   (the foundation references nothing above it)
orchestrator ──manifest──▶ members     (operational, not a data reference)
```

A corpus never references a ledger or codex; a ledger never references a codex; within the corpus layer, the public hub never references the private one. The ledger cites both corpora — privacy there is derived claim sensitivity, and it becomes a wall at the codex build's public-profile leak check, never before. Codices do not reference each other — they share the ledger instead (what dissolved the sibling-citation problem). Notes and other generated views are never citation targets. These directions are validated, not just conventional.

## 3. The corpus layer

At architecture altitude: a **corpus** is a content-addressed archive of artifacts, each carried by a faithful markdown record (`records/{ab}/{blake3}.md`, one-level sharding) whose body decomposes the artifact into addressable segments, and whose lifecycle is `stub → draft → normalized` — deterministic ingest and draft, then an LLM **faithful-form** pass driven through an external request/claim queue. Schemas (four namespaces: `mime`, `origin`, `atom`, `context`) drive capture, drafting, and faithful rendering per media type, per source, and per form. A record classifies its artifact mechanically only (`mime/*`, `origin/*`); what its content *means* is asserted in the ledger, never in the record — a record contains nothing unfalsifiable against its own bytes. Artifact bytes live in an untracked content-addressed store; records, schemas, and corpus-local extensions are tracked.

Everything in that paragraph — the record grammar, schema system, lifecycle, functional-URI grammar, derived views, queue contract — is specified normatively by **`spec/corpus.md`**. This document adds only the system-level constraints:

- **Two hubs, mutually exclusive content** (the reference deployment): `corpus` for world artifacts, `corpus-private` for personal artifacts. Which hub an artifact belongs to is decided by its subject's tenancy, before capture.
- **Corpus-local extension, universal core.** Format knowledge that is domain- or source-specific (a private drafter, a vendor schema) lives in the corpus that needs it, loaded through the tooling's corpus-local extension seams. The universal package carries no tenant- or vendor-specific knowledge.
- **A corpus carries no resident persona.** The orchestrator persona (§6.2) drives content work in every corpus through that corpus's own gates; host- and source-specific operational knowledge lives in the orchestrator repo's runbooks (`docs/`). How many personas a deployment stations is deployment policy, not architecture — the reference deployment runs exactly one.

## 4. The ledger layer

At architecture altitude: the **ledger** is the single fact substrate — one repository interpreting every registered corpus. There is deliberately no ledger-side tenant partition: the ledger is the system's intermediate representation, never itself published; privacy is **derived sensitivity** on claims (evidence resolving only in private corpora, or an asserted upward override) and becomes a wall at the codex build. A **fact** is a typed **concept** — a materialized real-world thing, for which records are evidence and artifact roster, never identity — or an **edge**, holding **claims**; every claim carries **evidence** (`corpus://` URIs resolved by blake3 across the corpora, span-precise where verified; `ref://` citations into mirrored reference datasets) and a position on the epistemic status ladder, promoted in place as evidence accrues. Beside the facts sits the **pre-assertion workspace** — interpretations: identity guesses, working assessments, corrections/tombstones, and ingestion needs. The boundary is physical: everything in `facts/` is asserted; consumers never filter speculation out of knowledge.

Knowledge is authored **once**, in the ledger — never re-authored per presentation. The ledger carries the coverage obligation for every corpus it interprets (every in-scope record represented — cited as evidence or rostered on a concept), which is how the system proves nothing captured goes unrepresented silently. Everything in this paragraph is specified normatively by **`spec/ledger.md`**, including the evidence-verification gate — anchors resolve, quotes match verbatim, snapshot binding flags rot — that makes the system's traceability a checked invariant.

Historical note: the fact model was born *inside* the first codices (under ATH-ARCH v12's agent-owned convention), generalized across all of them, and graduated into this layer once cross-codex identity made the fragmentation visible. The `same_as` cross-codex protocol, the `codex://` publication surface, and coverage-ceding machinery were all compensations for that fragmentation, and all dissolved with it.

## 5. The codex layer

A **codex is a targeting of facts that compiles to prose**: a scope over the ledger, an editorial voice, a generated Obsidian vault of notes (each note's frontmatter naming the exact ledger files it derives from), and a **build** that renders the deliverable — the reference deployment is Quartz — with every reference resolved: `corpus://` footnotes become citations, functional-URI embeds are rastered through the corpus resolver into real assets, wikilinks become site links, and each page exposes its provenance chain (prose → fact → claim → evidence → bytes).

Codices own no knowledge and are cheap to mint: a new compendium is a scope and a voice. Everything below the ledger is regenerable. Tenancy follows content into deliverables — **build profiles** ensure a publicly deployed site contains only what its audience may see (private-backed content excluded or stubbed; a leak check validates the built output). The codex contract — manifest, scope semantics, note provenance, build obligations, profiles — is **`spec/codex.md`**.

A codex may additionally *operate* — embed an agent that acts on the systems its domain describes (the reference case: a homelab codex inspecting live infrastructure). Its knowledge flows through the normal path (observations ingest into the corpus, facts land in the ledger); its operating agent is bounded by an explicit autonomy contract in the codex's operating guide — read-only by default, mutations enumerated and classed, everything else owner-gated.

## 6. Pipeline and agents

### 6.1 The deterministic / LLM boundary

| Operation | Type |
|---|---|
| Capture (fetch, hash, store), ingest, MIME detection | Deterministic |
| Draft (mechanical body extraction, overlay-declared emissions) | Deterministic |
| Normalize (faithful-form refinement: shaping, descriptions) | LLM agent pass |
| Functional-URI resolution, derived views | Deterministic |
| Ledger harvest (mechanical concept/claim minting from corpus facts, origin-keyed) | Deterministic |
| Ledger fact authoring and interpretation | LLM agent pass |
| Ledger validation (check, evidence verification, promote mechanics) | Deterministic |
| Codex scope materialization | Deterministic |
| Codex note synthesis (voice, templates) | LLM agent pass |
| Codex build (resolve, raster, link, leak check) | Deterministic |
| Member sync/status (`ath`) | Deterministic |

If the operation could produce different valid outputs depending on judgment, it is agent-driven; if the output is a function of the input, it is scripted. This enables independent re-processing at every stage.

### 6.2 Personas

- **The orchestrator persona** (orchestrator repo) — principal developer for the system and its one operating persona: specs, tooling, cross-member coherence, member health, and the content operating loop in every member (assess → prioritize → propose → execute → report; external captures, deletions, and normative spec changes are owner-gated). Boots from `.claude/skills/orchestrator/`; keeps logbook/state/gotchas as institutional memory. Member repos carry no personas.
- **The Normalizer** (corpus agent) — one record (or small batch) per invocation, draft → normalized, through the decompose/edit/compile substrate; never hand-edits record markdown; faithful-form work only — it asserts nothing about the world. Driven through the corpus's request/claim queue by an external loop session (`spec/corpus.md` §8.5) — the corpus tooling never invokes a normalizer itself; demand flows down from the ledger's citation discipline.
- **Ledger authors** — the interpretive passes that declare facts and interpretations from corpus evidence, under the ledger's SCHEMA/CLAUDE discipline; harvest, validation, and promotion mechanics are deterministic tooling. Materialization discipline binds them: concepts are real-world things — records are evidence, never subjects (`spec/ledger.md` §4).
- **Codex compilers** — the synthesis passes that render scoped facts into a codex's voice; scope materialization and the build are deterministic tooling.

Agent passes are one-item-scoped, report to their driver, and share no state beyond the repos themselves. Concurrency is the driver's decision.

## 7. Tooling

One distribution — **`athenaeum`** (Python, `tools/` in the orchestrator repo) — ships the system's CLIs:

- **`corpus`** — the corpus pipeline and query surface: capture / ingest / draft / normalize-queue verbs, resolve (functional URIs), lint, health, find, decompose/compile, store, gc. Auto-discovers its corpus root; accepts `--corpus-root`.
- **`ath`** — the orchestrator umbrella: `ath sync` / `ath status` against the manifest; `ath corpus …` delegation; `ath ledger …` (validation, evidence verification, harvest, promote, generators, worklist) and `ath codex …` (scope, build, leak check) — landing with the shared ledger/codex packages. Deliberately no bare `ledger` or `codex` commands.

Tooling agnosticism is normative: no member ids or paths in code; member-local extensions load through declared seams; a third party brings their own org, members, and agents to the same distribution.

Serving layers (read APIs, browsers, viewers) are deliberately unspecified: they are rebuildable consumers of the contracts above, produced when the system's form calls for them, never load-bearing.

## 8. Change management

- **The specs are law.** Code conforms to `spec/`; when code needs something a spec doesn't cover, the spec changes first — and a change to `spec/corpus.md`'s data contract additionally requires a migration story for every existing record.
- **History files away under tags** (`pre-reforge` marks the 2026-07 restructuring); the working tree carries only the system's current form.
- **Institutional memory is layered like the system**: the orchestrator persona's references for system-level memory and history; the system runbooks (`docs/`) for operational knowledge. Auto-memory is never the source of truth.

---

*Version 13 (2026-07) supersedes v12's two-layer draft: the orchestrator becomes a specified component (eponymous repo + manifest + `ath`); the fact model born inside the first codices graduates into its own layer — the single ledger (ATH-LEDGER), where concepts materialize real-world things and privacy is derived sensitivity — leaving codices as targeted compilations (ATH-CODEX); and the retired viewer/server stack is descoped from the architecture. The corpus contract moved to 2.0 (classification to the ledger) in the same revision.*

*Amended in place 2026-07-12: the Curator persona (public corpus) was absorbed into the orchestrator (2026-07-06) — one persona system-wide; its operational knowledge lives in the system runbooks (`docs/capture-operations.md`), its pre-reforge references at the corpus repo's `pre-reforge` tag.*
