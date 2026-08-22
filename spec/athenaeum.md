---
spec_id: ATH
part: I
title: "Athenaeum Specification — Part I: Architecture"
version: 33
status: current
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-08-21
---

# Athenaeum Specification — Part I: Architecture

**The Athenaeum specification is one document in four parts, under one version.** This part is the architecture; [Part II](corpus.md) is the corpus contract; [Part III](ledger.md) is the ledger contract; [Part IV](custody.md) is the custody contract — artifact byte residence and resolution. A normative change to any part bumps the shared version (§8). Amendment history lives in [`CHANGELOG.md`](CHANGELOG.md) and in git history under tags — the spec text carries current law only.

## 1. Overview

### 1.1 What this is

The Athenaeum is a knowledge normalization and curation system. It captures artifacts from any source, normalizes each into a faithful, content-addressed record, and interprets those records into an evidence-backed fact substrate. The thesis: knowledge cited precisely enough that the expert agents drawing on it cannot hallucinate their grounding.

The system's **end product** is the interpreted archive — the corpus + ledger join: every claim evidence-backed at span level, graded on an honest epistemic ladder, its sensitivity derived; every captured record represented. What sits above that product — compendium sites, expert agents, deliverables of any shape — consumes it from outside the system (§5). The system has two data layers, one custody plane, and one external driver:

- **The corpus layer is the foundation — the bytes.** The corpus is a content-addressed archive of captured artifacts, each identified by the blake3 hash of its bytes and represented by a faithful markdown record. Tenancy is a **derived, per-record property** — origin-overlay `tenancy:` declarations over the instance's tier set, fail closed to the private floor — never a directory or repo boundary (§1.2 principle 2). The corpus contract is **Part II** (`spec/corpus.md`).

- **The ledger layer is the knowledge — the claims.** The ledger is the single fact substrate: **concepts** (materialized real-world things) and edges carrying typed claims in which every claim carries `corpus://`/`ref://` evidence, with an epistemic status ladder, plus the pre-assertion workspace (interpretations) beside them. Knowledge is authored once, here; privacy is derived sensitivity, not a partition. The ledger contract is **Part III** (`spec/ledger.md`).

- **The custody plane is where the bytes live.** Records and facts are tracked text; artifact bytes are untracked and reside across declared **locations** — the co-located store, bulk store roots, operator-managed attached trees, remote stores — with resolution by content address across all of them. The custody contract is **Part IV** (`spec/custody.md`).

- **The tooling is the definition and the driver — and it lives outside the instance.** One repository — the **distribution** (`athenaeum/athenaeum`) — holds the specification and the shared tooling (the `athenaeum` Python distribution: the `ath` and `corpus` CLIs; the residence scanner). It is deployment-agnostic and publicly hostable: it tracks no instance state and points at an instance to do work inside it (§2). Everything the deployment owns lives in the **instance** — one private repository holding the corpus, the ledger, and the instance config.

Ownership stays disjoint by layer — the boundary each part's contract enforces — and the product boundary bounds the system itself:

| Layer | Owns | Never owns |
|---|---|---|
| Corpus | Artifact identity, byte provenance, faithful structure, addressable renderings, faithfulness annotations | World-level meaning or claims |
| Ledger | Concepts, edges, claims, interpretations, evidence bindings, derived sensitivity | Artifact renderings or publication prose |
| Custody | Byte residence, location routes, replication, residence indexes | Record content or identity semantics |
| Distribution | Specification, shared tooling, agent templates | Instance content |
| *Consumers (external, §5)* | *Presentation: scope, voice, rendering, deployment* | *Facts, claims, or any independent knowledge* |

### 1.2 Design principles

1. **Layered foundation.** The corpus depends on nothing; the ledger depends on the corpus. Consumers sit above the product boundary and depend on both. Each layer knows nothing of what is above it. References point downward only.
2. **Tenancy is declared knowledge, walled at publication.** The instance is one private repository, and a record's tenancy is *derived*: origin overlays declare `tenancy:` — a tier from the instance's declared set, `public | private` reserved, further tiers instance-owned (Part III §6.4) — at the source grain, decided once per origin, never once per capture; promoted members inherit through their container lineage, and a record whose origins declare nothing falls closed to the floor (Part III §6.4). Sensitivity computes upward from there (claims are visible where all their evidence is), and privacy becomes a hard boundary exactly where content leaves the owner: the consumption contract obliges any consumer publishing beyond the owner to filter on derived sensitivity for the reader's grant set, fail closed (Part III §12). No tooling, schema, or convention may lower a record's derived tenancy or pass content past the wall its grants stop at.
3. **Content addressing.** An artifact's identity is the blake3 hash of its bytes — permanent, and independent of where the bytes reside (Part IV).
4. **Faithfulness below, interpretation above.** Corpus records are faithful renderings that add no information; interpretation lives in the ledger, where every interpretive move carries evidence and an epistemic status. Editorial voice lives with consumers, beyond the product boundary — and every published sentence owes a traceable reference into the ledger (Part III §12).
5. **Evidence is the contract between the layers.** A ledger claim cites `corpus://` URIs — resolved by blake3, optionally span-precise (`?el=`, `?page=`, `?time_range=`, `?bbox=`) — or `ref://` citations into mirrored reference datasets, and the system's validation verifies those citations mechanically: anchors resolve, quotes match verbatim, re-normalized records and updated mirrors flag their citers. Traceability is not a style; it is a checked invariant.
6. **The instance is config-driven; the tooling is instance-agnostic.** The instance config (§2.3) is the only place instance identity is declared. Shared tooling never hardcodes an instance path or id; a third party points the same distribution at their own instance.
7. **Deterministic before LLM.** Every pipeline stage whose output is a function of its input is a script; every stage requiring judgment is an agent pass. The boundary is sharp so each stage's outputs are auditable and independently re-runnable.
8. **Durable vs regenerable, everywhere.** Tracked content is durable and reviewed (records, facts, schemas, specs, the instance config); derived content (caches, resolved views, residence indexes, build outputs) is regenerable and disposable. The same inversion appears at every layer.
9. **Offline-first.** Only capture requires network access. Everything else — normalization, authoring, validation, resolution — operates on local data.
10. **No transitionary states.** Every landed change leaves the system whole. Scaffolding deletes itself when it graduates; history files away under tags and the changelog, never in the working tree.

### 1.3 Terminology

| Term | Definition |
|---|---|
| **Distribution** | `athenaeum/athenaeum` — the system's definition (the specification) and tooling (`tools/`, `scanner/`), deployment-agnostic and publicly hostable. Cloned or installed anywhere; it holds no instance state. |
| **Instance** | One private git repository holding the system instantiated: the corpus (`corpus/`), the ledger (`ledger/`), and the instance config (`athenaeum.yaml`, tracked). The working directory the tooling discovers and operates in (§2.2). |
| **Instance config** | `athenaeum.yaml` at the instance root — tracked instance state: the tenancy floor, the tier and audience declarations, the tracker, the reference-dataset registry (§2.3). |
| **Corpus** | The content-addressed archive of artifacts with faithful markdown records, at `corpus/` in the instance; record tenancy is derived from origin declarations (§1.2). Contract: Part II. |
| **Ledger** | The single fact substrate: concepts + edges holding asserted claims with evidence, plus interpretations (the pre-assertion workspace), at `ledger/` in the instance. Privacy is derived sensitivity, walled at publication (Part III §12). Contract: Part III. |
| **Concept** | A materialized real-world thing in the ledger — typed, optionally schema-shaped; records are its evidence and artifact roster, never its identity (Part III §4). |
| **Product** | The corpus + ledger join, read through the system's contracts: the interpreted archive consumers build on (§5). |
| **Consumer** | Anything outside the system reading the product — a compilation (the codex estate), an expert agent, a deliverable pipeline. Consumers own presentation, never knowledge, and are bound by the consumption contract (Part III §12). |
| **Artifact record** | One captured file's faithful markdown proxy in the corpus, named by the blake3 of its bytes. |
| **Fact / Claim / Evidence** | The ledger's knowledge atoms: a fact file (concept or edge) holds typed claims; each claim carries evidence entries whose `corpus://` / `ref://` URIs ground it in captured bytes or mirrored reference datasets. |
| **Reference dataset** | A locally-mirrored external database (Wikipedia, MusicBrainz, OpenStreetMap, …) citable as evidence by native id via `ref://` — resolved at the dataset's `latest` snapshot tag, or pinned `@{tag}`; each registered snapshot's mirror is a corpus artifact, a terminal-contract record addressed by blake3 (Part III §6.5). Registered in the instance config (§2.3). |
| **Location** | A declared residence for artifact bytes — a content-addressed store root or an operator-managed attached tree, local or remote (Part IV). |
| **`corpus://` URI** | The evidence-citation primitive: `corpus://{hash}` with optional span parameters, resolved by blake3 in the corpus. Grammar: Part II §6. |
| **`ledger://` URI** | The knowledge-reference primitive: `ledger://{id}` (or `…/{id}:{claim}`) referencing a fact, claim, or interpretation — consumers read knowledge here, never from any rendered prose (Part III §12). |
| **Normalizer** | The interpretive half of the corpus's one authoring pass: renders a record under its form contract where no mechanical shaper can — shaping only: faithful renderings, structural marks, and typed fidelity issues (Part II §8.1, §4.1). |
| **Resident persona** | The system-resident principal-developer persona, stationed in the instance, with whole-system scope — the system's one persona. |
| **Form** | A named, mechanically checkable rendering contract binding a record span — what a faithful markdown shape looks like for a decomposable population (Part II §7.8). |
| **Owner** | The human authority for system direction. External captures, deletions, and normative spec changes are owner-gated — the resident persona proposes, the owner decides. |

## 2. Topology

### 2.1 Two repositories

The system is two git repositories with disjoint ownership:

- **The distribution** (`athenaeum/athenaeum`) — specification + tooling, publicly hostable. It tracks no instance state: no config, no runbooks, no backlog snapshots. Anyone can consume it; the reference deployment installs its CLIs once (`uv tool install --editable tools/`) and never works "inside" it except to develop the tooling itself.
- **The instance** — the deployment's own private repository: `corpus/` + `ledger/` + `athenaeum.yaml`, one history. Repo visibility on the deployment's forge is the outermost access-control surface; everything inside is the owner's. A deployment's forge org, member roster, and hosting are its own business — nothing in the distribution names them.

The corpus and the ledger are directories of one repository, not repositories of their own. The layer boundary they used to enforce by repo membership is enforced where it always actually lived: in each part's contract (what each layer may own — §1.1), in the tooling's write discipline, and in validation. One repository buys what two could not: atomic cross-layer commits (a supersession that re-points ledger citations and retires corpus bytes is one diff), one history for what happened and why, and no synchronization machinery between the layers.

### 2.2 On-disk layout and discovery

```
<instance>/                       ← the instance repo — the working directory
├── athenaeum.yaml                ← the instance config (§2.3), TRACKED
├── CLAUDE.md                     ← the resident persona's boot brief (thin: pointers + gates)
├── corpus/                       ← the corpus layer (Part II §12.1: records/, schema/,
│                                    runbooks/, untracked artifacts/ cache/ capture/ queue/)
└── ledger/                       ← the ledger layer (Part III §3: facts/, interpretations/,
                                     schemas/, harvest/, invariants/, docs/)
```

**Discovery is upward.** The tooling locates the instance by walking up from the current directory to the nearest `athenaeum.yaml` (the `ATHENAEUM_ROOT` environment variable or a `--root` flag overrides). The corpus tooling independently discovers its corpus root the same way (Part II §12.1); `corpus/corpus.toml` — untracked, machine-specific — carries the machine's custody declarations (Part IV). Nothing requires the instance to live at any particular path, and the distribution's own checkout location is irrelevant to operation.

**Scaffolding.** `ath init` creates a new instance: the config from its template, the corpus and ledger skeletons, the persona boot brief, and the agent definitions (`.claude/agents/`) from templates shipped with the distribution — so a fresh instance is self-contained for working sessions from its first commit.

Operational knowledge lives in the instance, beside what it operates: the corpus's `runbooks/`, the ledger's `docs/`. The distribution carries none of it.

### 2.3 The instance config — `athenaeum.yaml`

`athenaeum.yaml` at the instance root is **tracked** instance state — the durable declarations the tooling reads. It registers no members (the layers are fixed directories) and no consumers (§5).

```yaml
name: …                    # optional display name for the instance

visibility: private        # the tenancy floor: the tier records fall to when their origins
                           # declare no `tenancy:` (Part III §6.4). Default private.

tenancy:                   # optional — the instance-declared disclosure set (Part III §6.4);
  tiers: [family, accountant]   # named tiers beside the reserved `public` and `private`.
  audiences:               # named grant sets the read surface serves (§5.1): audience →
    family: [family]       #   tiers granted. `public` is implicit in every audience;
    finances: [accountant] #   `private` is the owner's alone, never grantable.
                           # Absent block: the public|private binary — pre-tier behavior.

tracker:                   # the issue tracker — the system's backlog
  repo: {owner}/{name}     # the forge repo carrying instance issues
  host: https://…          # the forge instance (API host derives from it)
  snapshot: corpus/runbooks/tickets.md   # where `ath issue sync` writes the committed
                           # offline read (relative to the instance root)

references:                # reference datasets (Part III §6.5) — mirrored databases;
  {dataset}:               #   a snapshot's mirror bytes are a corpus ARTIFACT, never a loose file
    description: …
    adapter: …             # optional — the format adapter resolving native ids (zim,
                           #   osm-pbf, …); when omitted, derived from the mirror record's
                           #   mime overlay `ref_adapter` (Part II §7.1); explicit wins
    latest: …              # the default snapshot tag — names a key below, declared, never inferred
    snapshots:
      {tag}:
        artifact: …        # blake3 of the mirror's bytes — the pin verification stamps
```

The registry earns tracking: a snapshot registration (tag → mirror blake3) is a durable fact about the system — it now lands as a visible diff with history, like every other durable declaration (§1.2 principle 8). Machine-specific custody (where mirror bytes physically reside) stays out of the config — that is `corpus.toml`'s job (Part IV).

A deployment bootstraps by installing the distribution's CLIs, running `ath init` (or cloning an existing instance), and working inside the instance.

### 2.4 Reference directions

```
ledger ──corpus://──▶ corpus           (downward: claim evidence, blake3-resolved, span-precise)
ledger ──ref://──▶ reference mirrors   (downward: registered datasets; a mirror resolves through
                                        the corpus store by snapshot-artifact blake3)
corpus ──▶ custody (Part IV)           (downward: id → bytes, wherever they reside)
consumers ──ledger://──▶ ledger        (the product's knowledge-read surface — Part III §12)
consumers ──corpus://──▶ corpus        (read-time resolution only: materializing citations the
                                        ledger already asserts — never independent evidence)
corpus ──▶ (nothing above it)          (the foundation references nothing above it)
tooling ──config──▶ instance           (operational, not a data reference)
```

The corpus never references the ledger; nothing in the system references a consumer. The ledger cites the corpus freely — privacy is derived claim sensitivity computed from record tenancy (Part III §6.4), and it becomes a wall at publication under the consumption contract, never before. A consumer's own `corpus://`/`ref://` reads happen only when materializing what the ledger already asserted into presentable form — never a second, independent evidence path. Generated views — the ledger's and any consumer's alike — are never citation targets. These directions are validated, not just conventional. The read surface (§5.1) changes none of them: it transports the same consumer reads over HTTP — the public and audience planes with the grant-set projection pre-applied, the owner plane for the owner's own frontends.

## 3. The corpus layer

At architecture altitude: the **corpus** is a content-addressed archive of artifacts, each carried by a faithful markdown record (`records/{ab}/{blake3}.md`, one-level sharding) whose body decomposes the artifact into addressable segments, and whose state is **derived, never stored** (Part II §4.1) — deterministic ingest and attestation, then an LLM **faithful-form** pass driven through an external request/claim queue. Schemas (five namespaces: `mime`, `origin`, `atom`, `form`, `context`) drive capture, attestation, and faithful rendering per media type, per source, and per form. A record classifies its artifact mechanically only (`mime/*`, `origin/*`); what its content *means* is asserted in the ledger, never in the record — a record contains nothing unfalsifiable against its own bytes. Artifact bytes live in the custody plane (Part IV); records, schemas, and corpus-local extensions are tracked.

Everything in that paragraph — the record grammar, schema system, lifecycle, functional-URI grammar, derived views, queue contract — is specified normatively by **Part II** (`spec/corpus.md`). This part adds only the system-level constraints:

- **One corpus, tenancy per origin.** All captured artifacts land in the one corpus, and a record's tenancy derives from its origins — each origin overlay declares `tenancy:` once, at the source grain, a tier from the instance's declared set (a web host's overlay declares public; an export producer's declares private; a shared album's might declare `family`), members inherit through container lineage, and silence falls closed to the instance's `visibility:` floor (Part III §6.4). The tenancy question is answered when a source is onboarded, never per capture. A second corpus is deliberately unsupported: the plural machinery the pre-v26 topology carried served no deployment, and structure is grown when a real need arrives, never ahead of one (Part III §8's organic-growth rule, applied to the architecture itself).
- **Corpus-local extension, universal core.** Format knowledge that is domain- or source-specific (a private shaper, a vendor schema) lives in the corpus tree, loaded through the tooling's corpus-local extension seam (Part II §12.4.3). The distribution carries no tenant- or vendor-specific knowledge.
- **The corpus carries no resident persona of its own.** The instance's one persona (§6.2) drives content work through the corpus's own gates; host- and source-specific operational knowledge lives in `corpus/runbooks/`.

## 4. The ledger layer

At architecture altitude: the **ledger** is the single fact substrate interpreting the corpus. There is deliberately no ledger-side tenant partition: the ledger is the system's intermediate representation, never itself published; privacy is **derived sensitivity** on claims (evidence whose records derive private tenancy, or an asserted upward override — Part III §6.4) and becomes a wall at publication (Part III §12). A **fact** is a typed **concept** — a materialized real-world thing, for which records are evidence and artifact roster, never identity — or an **edge**, holding **claims**; every claim carries **evidence** (`corpus://` URIs resolved by blake3, span-precise where verified; `ref://` citations into mirrored reference datasets) and a position on the epistemic status ladder, promoted in place as evidence accrues. Beside the facts sits the **pre-assertion workspace** — interpretations: identity guesses, working assessments, corrections/tombstones, and ingestion needs. The boundary is physical: everything in `facts/` is asserted; consumers never filter speculation out of knowledge.

Knowledge is authored **once**, in the ledger — never re-authored per presentation. The ledger carries the coverage obligation for the corpus (every in-scope record represented — cited as evidence or rostered on a concept), which is how the system proves nothing captured goes unrepresented silently. Everything in this paragraph is specified normatively by **Part III** (`spec/ledger.md`), including the evidence-verification gate — anchors resolve, quotes match verbatim, snapshot binding flags rot — that makes the system's traceability a checked invariant.

## 5. The product boundary

The system ends at its product: the corpus + ledger join, read through the contracts above. It is a **generalized substrate** — nothing in it is shaped for any particular audience, domain, or deliverable — and it is **well-defined**: every claim evidence-backed and mechanically verified, every status honest, every record's tenancy and every claim's sensitivity derived and readable, coverage proven. That definition is what makes the product consumable without coordination: a consumer needs the contracts, not a relationship with the system's internals.

**Consumers sit outside.** Compendium compilations (the codex estate — domain-specific sites compiled from scoped facts), expert agents reading facts directly, deliverable pipelines of any shape: none is part of the instance, and this specification does not govern their internals. What binds them is the **consumption contract** (Part III §12): read knowledge via `ledger://` — never re-author it, never cite generated views; filter publication on derived sensitivity, fail closed; pin the reproducibility tuple when freezing a build. The obligation rides the product, whatever tool renders it.

*(Non-normative.)* The reference consumer is the **codex kit** — the compilation tooling and its contract (ATH-CODEX), maintained with the codex estate outside this system. The kit consumes the system through its public contracts and the `athenaeum` distribution as a library — the same read surfaces any third-party consumer gets.

### 5.1 The read surface

The distribution ships the product's one network doorway: **`ath serve`** — a **read-only HTTP surface** over an instance, serving the corpus + ledger join through the same contracts library consumers get. It is the same read surface over a different transport — the same URIs, semantics, and filters — never a second authority and never an independent evidence path. What is normative is the **contract, not the framework**: the resource model, the scope-selection grammar (Part III §12.1), the plane semantics below, and the versioned OpenAPI document the tooling emits — stamped with the specification version, so a breaking surface change is by definition a normative amendment. The web framework underneath is implementation detail this specification never names.

- **The planes are the grant sets.** The **public plane** — the default — serves the **public projection**: every response filtered on derived sensitivity (Part III §6.4), fail closed, computed in-system. Private-backed claim content, the ids of fully-private fact files, and evidence that resolves only privately are never emitted. A publishing consumer that reads only the public plane discharges the consumption contract's publication filter **by construction** (Part III §12): the wall enforced once, in governed and validated code, instead of once per consumer. An **audience plane** — one per audience the instance declares (§2.3), each gated by its own per-deployment token — serves the same projection computed for that audience's grant set: its granted tiers plus `public`, never `private` (Part III §6.4) — the accountant's bundle, the family view, scoped disclosure as a projection, not a copy. The **owner plane** — enabled only explicitly, gated by its own token — serves the full instance, for the owner's own trusted frontends and authoring harnesses. Interpretations — pre-assertion content — are served on the owner plane **only**; no audience, however wide its grants, reads the pre-assertion workspace. Tokens are deployment state, never tracked config: the instance declares the audiences and their grants; the operator mints and hands out the tokens.
- **Read-only is normative.** No mutating verb exists on any plane. Writes remain the authoring machinery's — agent passes, the capture queue, the `ath ledger` verbs — each behind its own gates. The surface is a doorway into the product, never a path around the system.
- **The trust boundary is the port — stated honestly.** The wall binds consumers whose *only* access is the surface; filesystem access to the instance bypasses it entirely. The surface moves the publication wall from consumer code into system code; it does not protect against local access. The operational boundary is: who can reach the instance root vs. who can reach the port.
- **Deployment posture is the operator's.** The surface binds localhost by default. TLS, reverse proxies, internet exposure, and rate limiting are deployment decisions, deliberately outside this specification — it governs what the surface says, never where the operator points it.

## 6. Pipeline and agents

### 6.1 The deterministic / LLM boundary

| Operation | Type |
|---|---|
| Capture (fetch, hash, store), ingest, MIME detection | Deterministic |
| Attest / derive (byte-fact attestation at ingest; mechanical derivation ops resolved on demand) | Deterministic |
| Custody operations (location attest, move, adopt, replicate — Part IV) | Deterministic |
| Normalize (faithful-form refinement: shaping) | LLM agent pass |
| Functional-URI resolution, derived views | Deterministic |
| Ledger harvest (mechanical concept/claim minting from corpus facts, origin-keyed) | Deterministic |
| Ledger fact authoring and interpretation | LLM agent pass |
| Ledger validation (check, evidence verification, promote mechanics) | Deterministic |
| Demand evaluation (Part III §14) and scope evaluation (Part III §12.1) | Deterministic |
| The read surface (`ath serve`, §5.1) | Deterministic |
| Instance status (`ath`) | Deterministic |

If the operation could produce different valid outputs depending on judgment, it is agent-driven; if the output is a function of the input, it is scripted. This enables independent re-processing at every stage.

### 6.2 Personas

- **The resident persona** (stationed in the instance) — principal developer for the system and its one operating persona: cross-layer coherence, instance health, and the content operating loop in every layer (assess → prioritize → propose → execute → report; external captures, deletions, and normative spec changes are owner-gated). Boots **thin**: the instance `CLAUDE.md` (pointers, gates, the deferral principle — deliberately no resident skill or institutional-memory tree; the specification, the tracker, and git history are the system's memory). Deployment specifics (backlog location, known-red baselines) ride the instance's own runbooks. Spec and tooling development happens against the distribution's checkout, under its own brief.
- **The Normalizer** (corpus agent) — one record (or small batch) per invocation, attested → formed (or terminal), through the decompose/edit/compile substrate — state reported, never stored (Part II §4.1); never hand-edits record markdown; faithful-form work only — it asserts nothing about the world. Driven through the corpus's request/claim queue by an external loop session (Part II §8.5) — the corpus tooling never invokes a normalizer itself; demand flows down from the ledger's citation discipline.
- **Ledger authors** — the interpretive passes that declare facts and interpretations from corpus evidence, under the ledger's SCHEMA/CLAUDE discipline; harvest, validation, and promotion mechanics are deterministic tooling. Materialization discipline binds them: concepts are real-world things — records are evidence, never subjects (Part III §4).

Agent passes are one-item-scoped, report to their driver, and share no state beyond the instance itself. Concurrency is the driver's decision. What agents a consumer runs on the product's far side is the consumer's business.

## 7. Tooling

One distribution — **`athenaeum`** (Python, `tools/` in the distribution repo) — ships the system's CLIs:

- **`corpus`** — the corpus pipeline and query surface: capture / ingest / attest / normalize-queue verbs, resolve (functional URIs), lint, health, find, decompose/compile, and the custody verbs (Part IV: location, locate, gc).
- **`ath`** — the instance umbrella: `ath init` (scaffold an instance), `ath status` (instance state), `ath issue` (tracker read + snapshot; writes go through the forge's own CLI), `ath ledger …` (validation, evidence verification, harvest, promote, generators, worklist, demands), `ath serve` (the read surface, §5.1), `ath ref …` (the reference-dataset resolver), `ath corpus …` delegation. Deliberately no bare `ledger` command.

Tooling agnosticism is normative: no instance ids or paths in code; instance-local extensions load through declared seams; a third party brings their own instance and agents to the same distribution. Consumers use the distribution **as a library** — the resolver, the ledger read surface, the instance join — through the same public contracts.

The **residence scanner** (`scanner/` in the distribution repo) is the one non-Python tool: a host-side manifest publisher for attached locations on remote machines (Part IV). Its manifest format is its own versioned cross-language contract, deliberately outside this spec.

**Presentation layers** (browsers, viewers, compilations) are deliberately unspecified: rebuildable consumers of the contracts above, produced when the system's form calls for them, never load-bearing. The **read surface** (§5.1) is not one of them — it is product, not presentation: the specified doorway those consumers read through.

## 8. Change management

- **The specification is law.** Code conforms to `spec/`; when code needs something the specification doesn't cover, the spec changes first — and a change to Part II's data contract additionally requires a migration story for every existing record.
- **One version, four parts.** A normative change to any part bumps the shared version and records itself in [`CHANGELOG.md`](CHANGELOG.md). The closed pre-unification lines (ATH-ARCH, ATH-CORPUS, ATH-LEDGER, ATH-CODEX) are citable as history; new law cites the unified version.
- **Amendments land complete.** An amendment is the normative text, the sweep of every enforcement and guidance site that teaches the retired rule (lint rules, overlay `checks:` and prose, mime-schema guidance, agent briefs — the changelog alone enforces nothing), and the migration story with its measured cost, in the same change (the 3.12 freeze discipline, generalized).
- **History files away** — under git tags, in the changelog, never in the working tree or the spec text. The spec carries only the system's current form; a rule's origin story is one `git log` away.
- **Institutional memory is the system itself**: the specification for law, the tracker for the backlog and its rulings, git history for what happened and why, the instance runbooks for operational knowledge. There is deliberately no persona-resident memory tree — a logbook beside the system drifts from it. Auto-memory is never the source of truth.

## 9. Out of scope

Deliberately outside this specification's authority — named so a session doesn't invent law for these by analogy to what *is* specified: OCR generation policy (including automatic PDF OCR selection) and PDF page-range syntax (`page=N-M`); SQLite row/query addressing; a portable corpus-wide member-hash query API; general single-record, whole-corpus, or non-markdown export; semantic types beyond the closed corpus vocabulary (Part II §7.5); dependent capture beyond depth one; a second corpus per instance; per-dataset `ref://` anchor grammar (a `ref://` citation is entry-level — Part III §6.5); cross-instance federation and any resolver spanning instances; full-text search on the read surface (`/facts` selection is deterministic matching, never search); write verbs on the read surface; per-consumer or per-request grants (disclosure is granted per declared **audience** — §2.3, §5.1 — never negotiated at the door); instance-shipped value-kind validator code (kinds are data, Part III §4.5; an algorithmic-validity seam is designed but deferred until a declared kind needs one); SVG rasterization; and everything on the consumer side of the product boundary (§5) — compilation, presentation, rendering, deployment. An unsupported surface fails explicitly or stays inert — never inferred from a supported operation that merely looks similar.

---

*Version 33 (2026-08-22, owner ruling) generalizes the v32 route rules to the full breadth of the payload-identity principle they rest on (Part II §6.2): **route unification** holds for every member axis — a promoted member leaf (`stream_id=`, `msg=`, `part=`, `path=`, `card=`, `entry=`, `item=`) resolves through its container, one route, one cache entry, base form disclosed — and **member re-chaining** holds for every member axis, so a further transform after any member address re-enters the working-kind table (`?msg=N&part=M` reaches an attachment through the mbox). No new doctrine, no migration: member-leaf ids already conformed. Prior version notes: the changelog.*
