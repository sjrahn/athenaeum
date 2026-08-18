---
spec_id: ATH
part: I
title: "Athenaeum Specification — Part I: Architecture"
version: 25
status: current
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-08-17
---

# Athenaeum Specification — Part I: Architecture

**The Athenaeum specification is one document in three parts, under one version.** This part is the architecture; [Part II](corpus.md) is the corpus contract; [Part III](ledger.md) is the ledger contract. A normative change to any part bumps the shared version (§8). *(v15: the pre-unification spec lines — ATH-ARCH ≤14, ATH-CORPUS ≤3.14, ATH-LEDGER ≤1.9 — are closed; their numbers remain citable as history, and each part's changelog records its own line's closure.)*

## 1. Overview

### 1.1 What this is

The Athenaeum is a knowledge normalization and curation system. It captures artifacts from any source, normalizes each into a faithful, content-addressed record, and interprets those records into an evidence-backed fact substrate. The thesis: knowledge cited precisely enough that the expert agents drawing on it cannot hallucinate their grounding.

The system's **end product** is the interpreted archive — the corpus + ledger join: every claim evidence-backed at span level, graded on an honest epistemic ladder, its sensitivity derived; every captured record represented. What sits above that product — compendium sites, expert agents, deliverables of any shape — consumes it from outside the system (§5). The system has two data layers and one driver:

- **The corpus layer is the foundation — the bytes.** A corpus is a content-addressed archive of captured artifacts, each identified by the blake3 hash of its bytes and represented by a faithful markdown record. Tenancy is a **derived, per-record property** — origin-overlay `tenancy:` declarations, fail closed private — never a repo boundary (§1.2 principle 2). The corpus contract is **Part II** (`spec/corpus.md`).

- **The ledger layer is the knowledge — the claims.** The ledger is the single fact substrate: **concepts** (materialized real-world things) and edges carrying typed claims in which every claim carries `corpus://`/`ref://` evidence, with an epistemic status ladder, plus the pre-assertion workspace (interpretations) beside them. Knowledge is authored once, here; privacy is derived sensitivity, not a partition. The ledger contract is **Part III** (`spec/ledger.md`).

- **The orchestrator is the definition and the driver.** One repository — `athenaeum/athenaeum`, the eponymous repo of the system's org — holds the specification, the shared tooling (the `athenaeum` distribution: the `ath` and `corpus` CLIs), and the resident persona's generic brief. *(v16)* It is a **pure tooling-and-specification host** — deployment-agnostic, publicly hostable: the member manifest and every other piece of deployment state live with the deployment (§2.2), never tracked here. Every other component is an independent member repo registered in the manifest.

Ownership stays disjoint by layer — the boundary each part's contract enforces — and the product boundary bounds the system itself:

| Layer | Owns | Never owns |
|---|---|---|
| Corpus | Artifact identity, byte provenance, faithful structure, addressable renderings, faithfulness annotations | World-level meaning or claims |
| Ledger | Concepts, edges, claims, interpretations, evidence bindings, derived sensitivity | Artifact renderings or publication prose |
| Orchestrator | Specification, shared tooling, manifest, runbooks, agent definitions, cross-member operations | Member content |
| *Consumers (external, §5)* | *Presentation: scope, voice, rendering, deployment* | *Facts, claims, or any independent knowledge* |

### 1.2 Design principles

1. **Layered foundation.** The corpus depends on nothing; the ledger depends on the corpora. Consumers sit above the product boundary and depend on both. Each layer knows nothing of what is above it. References point downward only.
2. **Tenancy is declared knowledge, walled at publication.** The corpus is **one repository** (private, like every member), and a record's tenancy is *derived*: origin overlays declare `tenancy: public | private` at the source grain — decided once per origin, never once per capture — promoted members inherit through their container lineage, and a record whose origins declare nothing falls closed to private (Part III §6.4). Sensitivity computes upward from there (claims are private-backed by their evidence), and privacy becomes a hard boundary exactly where content goes public: the consumption contract obliges any consumer publishing beyond the owner to filter on derived sensitivity, fail closed (Part III §12). No tooling, schema, or convention may lower a record's derived tenancy or pass private-backed content to a public surface. *(v13's physical wall — separate public/private corpus repos — defended repo-grain sharing that publication never used; the publication filter was always the load-bearing wall, and remains it.)*
3. **Content addressing.** An artifact's identity is the blake3 hash of its bytes — permanent, and identical in every corpus that holds those bytes.
4. **Faithfulness below, interpretation above.** Corpus records are faithful renderings that add no information; interpretation lives in the ledger, where every interpretive move carries evidence and an epistemic status. Editorial voice lives with consumers, beyond the product boundary — and every published sentence owes a traceable reference into the ledger (Part III §12).
5. **Evidence is the contract between the layers.** A ledger claim cites `corpus://` URIs — resolved by blake3 across the corpora, optionally span-precise (`?el=`, `?page=`, `?time_range=`, `?bbox=`) — or `ref://` citations into mirrored reference datasets, and the system's validation verifies those citations mechanically: anchors resolve, quotes match verbatim, re-normalized records and updated mirrors flag their citers. Traceability is not a style; it is a checked invariant.
6. **Members are config-driven.** The manifest (§2.3) is the only place membership and member locations are declared. Shared tooling never hardcodes a member path or id; a third party points the same tooling at their own org and corpora.
7. **Deterministic before LLM.** Every pipeline stage whose output is a function of its input is a script; every stage requiring judgment is an agent pass. The boundary is sharp so each stage's outputs are auditable and independently re-runnable.
8. **Durable vs regenerable, everywhere.** Tracked content is durable and reviewed (records, facts, schemas, specs); derived content (caches, resolved views, build outputs) is regenerable and disposable. The same inversion appears at every layer.
9. **Offline-first.** Only capture requires network access. Everything else — normalization, authoring, validation, resolution — operates on local data.
10. **No transitionary states.** Every landed change leaves the system whole. Scaffolding deletes itself when it graduates; history files away under git tags, never in the working tree.

### 1.3 Terminology

| Term | Definition |
|---|---|
| **Orchestrator repo** | `athenaeum/athenaeum` — the system's definition (the specification) and tooling (`tools/`), deployment-agnostic and publicly hostable (v16). Its working tree is the workspace root; the manifest and the members live there untracked. |
| **Member** | An independent git repository registered in the manifest: a corpus or the ledger. Members live in the same forge org as the orchestrator repo. |
| **Manifest** | `athenaeum.yaml` at the workspace root — the single registry of members and the runtime join the tooling reads (§2.3). Deployment state: the orchestrator repo ignores it and ships `athenaeum.yaml.example` as the template. |
| **Corpus** | A content-addressed archive of artifacts with faithful markdown records; record tenancy is derived from origin declarations, never repo placement (§1.2). Contract: Part II. |
| **Ledger** | The single fact substrate: concepts + edges holding asserted claims with evidence, plus interpretations (the pre-assertion workspace). One repository interpreting every corpus; privacy is derived sensitivity, walled at publication (Part III §12). Contract: Part III. |
| **Concept** | A materialized real-world thing in the ledger — typed, optionally schema-shaped; records are its evidence and artifact roster, never its identity (Part III §4). |
| **Product** | The corpus + ledger join, read through the system's contracts: the interpreted archive consumers build on (§5). |
| **Consumer** | Anything outside the system reading the product — a compilation (the codex estate), an expert agent, a deliverable pipeline. Consumers own presentation, never knowledge, and are bound by the consumption contract (Part III §12). |
| **Artifact record** | One captured file's faithful markdown proxy in a corpus, named by the blake3 of its bytes. |
| **Fact / Claim / Evidence** | The ledger's knowledge atoms: a fact file (concept or edge) holds typed claims; each claim carries evidence entries whose `corpus://` / `ref://` URIs ground it in captured bytes or mirrored reference datasets. |
| **Reference dataset** | A locally-mirrored external database (Wikipedia, MusicBrainz, OpenStreetMap, …) citable as evidence by native id via `ref://` — resolved at the dataset's `latest` snapshot tag, or pinned `@{tag}`; each registered snapshot's mirror is a corpus artifact, a terminal-contract record addressed by blake3 (Part III §6.5). |
| **`corpus://` URI** | The evidence-citation primitive: `corpus://{hash}` with optional span parameters, resolved by blake3 across the registered corpora. Grammar: Part II §6. |
| **`ledger://` URI** | The knowledge-reference primitive: `ledger://{id}` (or `…/{id}:{claim}`) referencing a fact, claim, or interpretation — consumers read knowledge here, never from any rendered prose (Part III §12). |
| **Normalizer** | The interpretive half of the corpus's one authoring pass: renders a record under its form contract where no mechanical shaper can — shaping only: faithful renderings, structural marks, and typed fidelity issues; there is no editorial vouch to author (Part II §8.1, §4.1). |
| **Orchestrator persona** | The system-resident principal-developer persona in the orchestrator repo, with cross-member scope — the system's one persona; member repos carry none. |
| **Deployment** | One orchestrator repository, its manifest, one or more corpora, and exactly one ledger — the system, instantiated. What consumes it is not part of it. |
| **Interpretation** | A structured hypothesis, assessment, or correction living in the ledger's pre-assertion workspace — outside the claim boundary until promoted (Part III §1.3). |
| **Form** | A named, mechanically checkable rendering contract binding a record span — what a faithful markdown shape looks like for a decomposable population (Part II §7.8). |
| **Owner** | The human authority for system direction. External captures, deletions, and normative spec changes are owner-gated — the orchestrator persona proposes, the owner decides. |

## 2. Topology

### 2.1 The org is the container

The system lives in one forge organization (the reference deployment: Forgejo on a private host — the org URL is deployment state, declared only in the manifest). The org contains the orchestrator repo and every member repo as siblings. Org membership and repo visibility are the outermost access-control surface — which is what makes the repo boundary a real tenant boundary (§1.2 principle 2). A member's `remote:` override may name a different organization than the deployment's default — the tenant boundary still holds as long as that organization enforces equivalent repo-visibility controls.

### 2.2 On-disk layout

The orchestrator repo's working tree is the workspace; everything deployment-specific lives inside it at paths the repo ignores:

```
athenaeum/                        ← working tree of athenaeum/athenaeum
├── athenaeum.yaml                ← the member manifest (§2.3), UNTRACKED — deployment state
├── athenaeum.yaml.example        ← the manifest template the repo ships
├── spec/                         ← the specification: this part + corpus.md + ledger.md
├── tools/                        ← the `athenaeum` distribution (§6)
├── corpus/                       ← member, UNTRACKED — the corpus (bytes; one repo, tenancy per record)
└── ledger/                       ← member, UNTRACKED — the knowledge layer (one repo, Part III §1.2)
```

The two singleton layers sit at the root. *(v16)* The orchestrator repo tracks **no deployment state** — not the manifest, not runbooks, not backlog snapshots: it is a tooling-and-specification host any deployment (and the public) can consume. Operational runbooks live with the members they operate (the corpus's `runbooks/`, the ledger's `docs/`), where the deployment's privacy posture already governs them. Nothing above requires this exact machine layout — the manifest is authoritative, and member `path:` overrides exist — but it is the reference shape. Consumers live entirely outside the workspace (§5); the system holds no registry of them.

### 2.3 The manifest

`athenaeum.yaml` is the single registry of members and the join the tooling reads. Nothing else — no tool, schema, or doc — may hardcode a member's location. *(v16)* The manifest is **deployment state**: it lives at the workspace root, untracked by the orchestrator repo (which ships `athenaeum.yaml.example` as the template) — a deployment's org URL, member roster, and tracker are its own business, never published with the tooling.

```yaml
org: https://forge.example.com/athenaeum          # remote base: {org}/{name}.git

corpora:
  {name}:
    description: …        # the member's role, one line
    visibility: …          # public | private — DEFAULT private (fail closed). The FLOOR for
                           # records whose origins declare no `tenancy:` (Part III §6.4);
                           # per-record tenancy is derived from origin overlays, not from here
    path: …                # optional — default corpora/{name}; the reference deployment's
                           # single corpus overrides to `corpus` at the workspace root
    remote: …              # optional — default {org}/{name}.git
ledger:
  {name}:                  # exactly one (Part III §1.2)
    description: …
    path: …                # optional — default {name}/ at the workspace root
    remote: …

references:                # reference datasets (Part III §6.5) — mirrored databases, not git members;
  {dataset}:               #   a snapshot's mirror bytes are a corpus ARTIFACT, never a loose file (v17)
    description: …
    adapter: …             # optional since v21 — the format adapter resolving native ids
                           #   (zim, osm-pbf, …); when omitted, derived from the mirror
                           #   record's mime overlay `ref_adapter` (Part II §7.1); an
                           #   explicit declaration wins (bootstrap and override path)
    latest: …              # the default snapshot tag — names a key below, declared, never inferred
    snapshots:
      {tag}:
        artifact: …          # blake3 of the mirror's bytes — the pin verification stamps
        path: …              # DEPRECATED (v21; was the v18 interim) — read-in-place override,
                             #   superseded by attached locations (Part II §12.1.1): register
                             #   the mirrors directory as a location and the artifact hash
                             #   resolves there with no bytes moved. Read tolerantly until
                             #   every registered snapshot store-resolves, then removed
```

Members are keyed by name; manifest order is presentation order. The manifest records **membership, not pins** — members are living repos, and the tooling synchronizes them (`ath sync`: clone missing, fetch and report the rest, fast-forward only on request). A deployment bootstraps by cloning the orchestrator repo, writing its manifest from the example, and running `ath sync`.

The tracker's `snapshot` (the committed offline read of the backlog) is deployment state too: by default it lands beside the manifest, untracked; a deployment SHOULD point it into a member repo (the reference deployment: `corpus/runbooks/tickets.md`) so the backlog's movement stays in git history.

### 2.4 Reference directions

```
ledger ──corpus://──▶ corpus           (downward: claim evidence, blake3-resolved, span-precise)
ledger ──ref://──▶ reference mirrors   (downward: registered datasets; a mirror resolves through
                                        the corpus store by snapshot-artifact blake3 — v17)
consumers ──ledger://──▶ ledger        (the product's knowledge-read surface — Part III §12)
consumers ──corpus://──▶ corpus        (read-time resolution only: materializing citations the
                                        ledger already asserts — never independent evidence)
corpus ──▶ (nothing)                   (the foundation references nothing above it)
orchestrator ──manifest──▶ members     (operational, not a data reference)
```

A corpus never references the ledger; nothing in the system references a consumer. The ledger cites the corpus freely — privacy is derived claim sensitivity computed from record tenancy (Part III §6.4), and it becomes a wall at publication under the consumption contract, never before. A consumer's own `corpus://`/`ref://` reads happen only when materializing what the ledger already asserted into presentable form — never a second, independent evidence path. Generated views — the ledger's and any consumer's alike — are never citation targets. These directions are validated, not just conventional.

## 3. The corpus layer

At architecture altitude: a **corpus** is a content-addressed archive of artifacts, each carried by a faithful markdown record (`records/{ab}/{blake3}.md`, one-level sharding) whose body decomposes the artifact into addressable segments, and whose state is **derived, never stored** (Part II §4.1: attested at birth, **formed** where a form contract governs a stored rendering, **terminal** where the artifact is its own terminal representation) — deterministic ingest and attestation, then an LLM **faithful-form** pass driven through an external request/claim queue. Schemas (five namespaces: `mime`, `origin`, `atom`, `form`, `context`) drive capture, attestation, and faithful rendering per media type, per source, and per form. A record classifies its artifact mechanically only (`mime/*`, `origin/*`); what its content *means* is asserted in the ledger, never in the record — a record contains nothing unfalsifiable against its own bytes. Artifact bytes live in an untracked content-addressed store; records, schemas, and corpus-local extensions are tracked.

Everything in that paragraph — the record grammar, schema system, lifecycle, functional-URI grammar, derived views, queue contract — is specified normatively by **Part II** (`spec/corpus.md`). This part adds only the system-level constraints:

- **One corpus, tenancy per origin** (the reference deployment): all captured artifacts land in the single `corpus` member, and a record's tenancy derives from its origins — each origin overlay declares `tenancy: public | private` once, at the source grain (a web host's overlay declares public; an export producer's declares private), members inherit through container lineage, and silence falls closed to private (Part III §6.4). The tenancy question is answered when a source is onboarded, never per capture. *(v13's two mutually-exclusive hubs merged 2026-08-14 under a sensitivity-invariance gate: every cited record's derived sensitivity verified byte-identical across the consolidation.)*
- **Corpus-local extension, universal core.** Format knowledge that is domain- or source-specific (a private drafter, a vendor schema) lives in the corpus that needs it, loaded through the tooling's corpus-local extension seams. The universal package carries no tenant- or vendor-specific knowledge.
- **A corpus carries no resident persona.** The orchestrator persona (§6.2) drives content work in every corpus through that corpus's own gates; host- and source-specific operational knowledge lives in the member repos' runbooks (the corpus's `runbooks/`; the ledger's `docs/` — v16). How many personas a deployment stations is deployment policy, not architecture — the reference deployment runs exactly one.

## 4. The ledger layer

At architecture altitude: the **ledger** is the single fact substrate — one repository interpreting every registered corpus. There is deliberately no ledger-side tenant partition: the ledger is the system's intermediate representation, never itself published; privacy is **derived sensitivity** on claims (evidence whose records derive private tenancy, or an asserted upward override — Part III §6.4) and becomes a wall at publication (Part III §12). A **fact** is a typed **concept** — a materialized real-world thing, for which records are evidence and artifact roster, never identity — or an **edge**, holding **claims**; every claim carries **evidence** (`corpus://` URIs resolved by blake3 across the corpora, span-precise where verified; `ref://` citations into mirrored reference datasets) and a position on the epistemic status ladder, promoted in place as evidence accrues. Beside the facts sits the **pre-assertion workspace** — interpretations: identity guesses, working assessments, corrections/tombstones, and ingestion needs. The boundary is physical: everything in `facts/` is asserted; consumers never filter speculation out of knowledge.

Knowledge is authored **once**, in the ledger — never re-authored per presentation. The ledger carries the coverage obligation for every corpus it interprets (every in-scope record represented — cited as evidence or rostered on a concept), which is how the system proves nothing captured goes unrepresented silently. Everything in this paragraph is specified normatively by **Part III** (`spec/ledger.md`), including the evidence-verification gate — anchors resolve, quotes match verbatim, snapshot binding flags rot — that makes the system's traceability a checked invariant.

Historical note: the fact model was born *inside* the first codices (under ATH-ARCH v12's agent-owned convention), generalized across all of them, and graduated into this layer once cross-codex identity made the fragmentation visible. The `same_as` cross-codex protocol, the `codex://` publication surface, and coverage-ceding machinery were all compensations for that fragmentation, and all dissolved with it.

## 5. The product boundary

The system ends at its product: the corpus + ledger join, read through the contracts above. It is a **generalized substrate** — nothing in it is shaped for any particular audience, domain, or deliverable — and it is **well-defined**: every claim evidence-backed and mechanically verified, every status honest, every record's tenancy and every claim's sensitivity derived and readable, coverage proven per corpus. That definition is what makes the product consumable without coordination: a consumer needs the contracts, not a relationship with the system's internals.

**Consumers sit outside.** Compendium compilations (the codex estate — domain-specific sites compiled from scoped facts), expert agents reading facts directly, deliverable pipelines of any shape: none is a member, none appears in the manifest, and this specification does not govern their internals. What binds them is the **consumption contract** (Part III §12): read knowledge via `ledger://` — never re-author it, never cite generated views; filter publication on derived sensitivity, fail closed; pin the reproducibility tuple when freezing a build. The obligation rides the product, whatever tool renders it.

*(Non-normative.)* The reference consumer is the **codex kit** — the compilation tooling and its contract (ATH-CODEX), maintained with the codex estate outside this system. Through v14 codices were a member layer of this specification; v15 moved them out: the system had become a generalized corpus+ledger substrate with a well-defined product, and domain-specific compilations belong on the consuming side of that boundary. The kit consumes the system through its public contracts and the `athenaeum` distribution as a library — the same read surfaces any third-party consumer gets.

## 6. Pipeline and agents

### 6.1 The deterministic / LLM boundary

| Operation | Type |
|---|---|
| Capture (fetch, hash, store), ingest, MIME detection | Deterministic |
| Attest / derive (byte-fact attestation at ingest; mechanical derivation ops resolved on demand) | Deterministic |
| Normalize (faithful-form refinement: shaping) | LLM agent pass |
| Functional-URI resolution, derived views | Deterministic |
| Ledger harvest (mechanical concept/claim minting from corpus facts, origin-keyed) | Deterministic |
| Ledger fact authoring and interpretation | LLM agent pass |
| Ledger validation (check, evidence verification, promote mechanics) | Deterministic |
| Member sync/status (`ath`) | Deterministic |

If the operation could produce different valid outputs depending on judgment, it is agent-driven; if the output is a function of the input, it is scripted. This enables independent re-processing at every stage.

### 6.2 Personas

- **The orchestrator persona** (orchestrator repo) — principal developer for the system and its one operating persona: specs, tooling, cross-member coherence, member health, and the content operating loop in every member (assess → prioritize → propose → execute → report; external captures, deletions, and normative spec changes are owner-gated). *(v14)* Boots **thin**: the root `CLAUDE.md` (pointers, gates, the deferral principle — deliberately no resident skill or institutional-memory tree; the specification, the tracker, and git history are the system's memory). *(v16)* The brief is **generic** — deployment specifics (member roster, backlog location, known-red baselines) ride the deployment's own state: the untracked manifest and the member runbooks. Member repos carry no personas.
- **The Normalizer** (corpus agent) — one record (or small batch) per invocation, attested → formed (or terminal), through the decompose/edit/compile substrate — state reported, never stored (Part II §4.1); never hand-edits record markdown; faithful-form work only — it asserts nothing about the world. Driven through the corpus's request/claim queue by an external loop session (Part II §8.5) — the corpus tooling never invokes a normalizer itself; demand flows down from the ledger's citation discipline.
- **Ledger authors** — the interpretive passes that declare facts and interpretations from corpus evidence, under the ledger's SCHEMA/CLAUDE discipline; harvest, validation, and promotion mechanics are deterministic tooling. Materialization discipline binds them: concepts are real-world things — records are evidence, never subjects (Part III §4).

Agent passes are one-item-scoped, report to their driver, and share no state beyond the repos themselves. Concurrency is the driver's decision. What agents a consumer runs on the product's far side is the consumer's business.

## 7. Tooling

One distribution — **`athenaeum`** (Python, `tools/` in the orchestrator repo) — ships the system's CLIs:

- **`corpus`** — the corpus pipeline and query surface: capture / ingest / attest / normalize-queue verbs, resolve (functional URIs), lint, health, find, decompose/compile, store, gc. Auto-discovers its corpus root; accepts `--corpus-root`.
- **`ath`** — the orchestrator umbrella: `ath sync` / `ath status` against the manifest; `ath issue` (tracker read + snapshot); `ath corpus …` delegation; `ath ledger …` (validation, evidence verification, harvest, promote, generators, worklist) — landing with the shared ledger package. Deliberately no bare `ledger` command. *(v15: the codex verbs left with the codex kit — the distribution carries no consumer tooling.)*

Tooling agnosticism is normative: no member ids or paths in code; member-local extensions load through declared seams; a third party brings their own org, members, and agents to the same distribution. Consumers use the distribution **as a library** — the resolver, the ledger read surface, the manifest join — through the same public contracts.

Serving layers (read APIs, browsers, viewers) are deliberately unspecified: they are rebuildable consumers of the contracts above, produced when the system's form calls for them, never load-bearing.

## 8. Change management

- **The specification is law.** Code conforms to `spec/`; when code needs something the specification doesn't cover, the spec changes first — and a change to Part II's data contract additionally requires a migration story for every existing record.
- **One version, three parts.** A normative change to any part bumps the shared version and records itself in that part's changelog. The closed pre-unification lines (ATH-ARCH, ATH-CORPUS, ATH-LEDGER, ATH-CODEX) are citable as history; new law cites the unified version.
- **History files away under tags** (`pre-reforge` marks the 2026-07 restructuring); the working tree carries only the system's current form.
- **Institutional memory is the system itself** *(v14)*: the specification for law, the tracker for the backlog and its rulings, git history for what happened and why, the member runbooks (the corpus's `runbooks/`, the ledger's `docs/` — v16) for operational knowledge. There is deliberately no persona-resident memory tree — a logbook beside the system drifts from it. Auto-memory is never the source of truth.

## 9. Out of scope

Deliberately outside this specification's authority — named so a session doesn't invent law for these by analogy to what *is* specified: OCR generation policy (including automatic PDF OCR selection) and PDF page-range syntax (`page=N-M`); SQLite row/query addressing; a portable corpus-wide member-hash query API; general single-record, whole-corpus, or non-markdown export; semantic types beyond the closed corpus vocabulary (Part II §7.5); dependent capture beyond depth one; a network serving protocol; multi-corpus capture in one invocation; per-dataset `ref://` anchor grammar (a `ref://` citation is entry-level — Part III §6.5; the mirror layer itself is specified there as of v17); a standalone external `ledger://` network resolver; SVG rasterization; and everything on the consumer side of the product boundary (§5) — compilation, presentation, rendering, deployment. An unsupported surface fails explicitly or stays inert — never inferred from a supported operation that merely looks similar.

---

*Version 21 (2026-08-17, owner ruling) is the custody amendment, landing the store mechanics v18 waited on. Part II generalizes artifact custody to declared **locations** — content-addressed store roots the corpus writes (local or remote; rclone as the generic remote transport) and **attached** operator-managed trees whose files stay in place, unrenamed, id-addressable through a derived location index once an attest pass has hashed them (Part II §12.1.1, §12.9.2 — the containment model generalized). For this manifest: `references:` entries MAY omit `adapter:` where the mirror record's mime overlay declares `ref_adapter` (Part II §7.1; an explicit declaration wins), and the v18 snapshot `path:` override is **deprecated** — an attached location over the mirrors directory supersedes it with no bytes moved; the key is read tolerantly until every registered snapshot resolves through the store, then removed. Part II also sketches overlay-declared redundancy floors (`replicas:`, max across mime/origin layers) and exempts the persistent derived indexes from gc's cache sweep by name.*

*Version 19 (2026-08-16) is a Part III amendment (owner ruling): element-level evidence binding for array-valued claims — an evidence entry MAY bind to one element of an array `value`, and the authentication bar evaluates such claims per element (Part III §5.4, §6.1). Nothing in this part changes.*

*Version 18 (2026-08-16) adds the interim mirror-materialization override (owner ruling): a manifest snapshot entry MAY carry `path:` — a deployment-local file the resolver reads in place, tried before the corpus store. Identity and verification are unchanged (the `artifact` blake3 remains the pin); the key exists so mirrors are usable while store custody mechanics for tens-of-GB artifacts are worked out, and store resolution supersedes it when they land (Part III §6.5).*

*Version 17 (2026-08-15) activates the reference-dataset layer (owner ruling). The manifest's `references:` entries become multi-snapshot — a tag-keyed `snapshots:` map with a declared `latest:` default and a format `adapter:` — and each snapshot's mirror bytes are a **corpus artifact**: a terminal-contract record addressed by blake3, distributed and integrity-checked through the corpus store rather than living as a loose file. The citation grammar gains the optional pin `ref://{dataset}@{tag}/{id}`; Part III specifies the bare-tracks/pinned-freezes semantics, tenancy-derived `ref://` sensitivity, the one-dataset-one-independent-source bar rule, and the mirror-grain coverage discharge (§6.4, §5.4, §6.5, §13). §9's descope narrows from the mirror layer wholesale to per-dataset anchor grammar. No existing citations move — nothing cited `ref://` before this version.*

*Version 16 (2026-08-14) makes the orchestrator repo **deployment-agnostic** — a pure tooling-and-specification host, fit for public hosting. Deployment state leaves the tracked tree: the member manifest becomes an untracked workspace-root file (the repo ships `athenaeum.yaml.example`), the operational runbooks move to the member repos they operate (the corpus's `runbooks/`, the ledger's `docs/`), the tracker snapshot follows the manifest's `tracker.snapshot` into a member repo, and the persona brief (`CLAUDE.md`) is generic — instance specifics live in the deployment's own runbooks. No data contract changes.*

*Version 15 (2026-08-14) unifies the specification and draws the product boundary. The three specs become **one specification in three parts** under one version — corpus and ledger no longer version independently (their lines close at 3.14 and 1.9). **Codices leave the system**: through v14 they were a member layer (ATH-CODEX); the corpus+ledger substrate having generalized into a well-defined product, domain-specific compilations now consume it from outside — the codex kit and its contract move to the codex estate, the manifest and tooling drop the layer, and the publication wall is restated as the consumption contract's obligation (Part III §12), where it always did its load-bearing work.*

*Version 14 (2026-08-14) consolidates the corpus layer to **one repository**: tenant isolation moves from the v13 repo boundary to derived per-record tenancy (origin-overlay `tenancy:` declarations, fail closed private — Part III §6.4 v1.9), with the publication-side leak check unchanged as the wall. The merge landed behind a sensitivity-invariance gate (per-claim derived sensitivity byte-identical before and after), with both hubs' git histories preserved in the merged repo. The same revision adopts the **deferral principle** operationally: records are usable from ingest, and normalization is pulled by citation demand (ATH-LEDGER 1.8's deferred surfaces), never pushed as backlog.*

*Version 13 (2026-07) supersedes v12's two-layer draft: the orchestrator becomes a specified component (eponymous repo + manifest + `ath`); the fact model born inside the first codices graduates into its own layer — the single ledger (ATH-LEDGER), where concepts materialize real-world things and privacy is derived sensitivity — leaving codices as targeted compilations (ATH-CODEX); and the retired viewer/server stack is descoped from the architecture. The corpus contract moved to 2.0 (classification to the ledger) in the same revision.*

*Amended in place 2026-07-12: the Curator persona (public corpus) was absorbed into the orchestrator (2026-07-06) — one persona system-wide; its operational knowledge lives in the capture-operations runbook (since v16: the corpus repo's `runbooks/capture-operations.md`), its pre-reforge references at the corpus repo's `pre-reforge` tag.*
