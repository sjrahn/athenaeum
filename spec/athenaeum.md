---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 13
status: current
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-07-02
---

# Athenaeum — Architecture Specification

## 1. Overview

### 1.1 What this is

The Athenaeum is a knowledge normalization and curation system. It captures artifacts from any source, normalizes each into a faithful, content-addressed record, and builds domain expertises on top whose every assertion traces — at span level — back to captured bytes. The thesis: rich compendiums of information that cite their sources precisely enough that the expert agents drawing on them cannot hallucinate their grounding.

The system has two data layers and one driver:

- **The corpus layer is the foundation — the truth.** A corpus is a content-addressed archive of captured artifacts, each identified by the blake3 hash of its bytes and represented by a faithful markdown record. Corpora are the unit of tenant isolation. The corpus contract is **`spec/corpus.md`** (ATH-CORPUS).

- **The codex layer is the knowledge — the expertise.** A codex is a domain-scoped repository whose structured fact graph cites corpus artifacts as evidence, claim by claim, span by span. The codex contract is **`spec/codex.md`** (ATH-CODEX).

- **The orchestrator is the definition and the driver.** One repository — `athenaeum/athenaeum`, the eponymous repo of the system's org — holds the specifications, the shared tooling (the `athenaeum` distribution: the `ath` and `corpus` CLIs), the member manifest, and the resident principal-developer persona. Every other component is an independent member repo registered in the manifest.

### 1.2 Design principles

1. **Layered foundation.** The corpus depends on nothing; a codex depends on one or more corpora; the corpus knows nothing of any codex. References point downward only.
2. **Tenant isolation is a repo boundary.** Public and private corpora are separate repositories with mutually exclusive content. No tooling, schema, or convention may blur them; visibility and access control operate at the repository, which is why the boundary is one.
3. **Content addressing.** An artifact's identity is the blake3 hash of its bytes — permanent, and identical in every corpus that holds those bytes.
4. **Faithfulness below, interpretation above.** Corpus records are faithful renderings that add no information; all interpretation, synthesis, and editorial judgment lives in the codex layer, where every interpretive move carries evidence.
5. **Evidence is the contract between the layers.** A codex claim cites `corpus://` URIs — optionally span-precise (`?el=`, `?page=`, `?time_range=`, `?bbox=`) — and the system's validation verifies those citations mechanically. Traceability is not a style; it is checkable.
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
| **Codex** | A domain-scoped knowledge repository: structured facts with claim-level corpus evidence, interpretations, and regenerable notes. Contract: `spec/codex.md`. |
| **Artifact record** | One captured file's faithful markdown proxy in a corpus, named by the blake3 of its bytes. |
| **Fact / Claim / Evidence** | The codex layer's knowledge atoms: a fact file holds typed claims; each claim carries evidence entries whose `corpus://` URIs ground it in captured bytes. |
| **`corpus://` URI** | The downward-citation primitive: `corpus://{hash}` with optional span parameters, resolved against a loaded corpus. Grammar: `spec/corpus.md` §6. |
| **`codex://` URI** | The sibling-citation primitive: `codex://{codex}/{id}` referencing another codex's *published* identifier — never its internals (§4.3, `spec/codex.md` §11). |
| **Curator** | The corpus-resident operating persona (public hub): assess → prioritize → propose → execute → report, with capture and commits owner-gated. |
| **Normalizer** | The interpretive agent pass that takes a record from mechanical `draft` to faithful `normalized`. |
| **Orchestrator persona** | The system-resident principal-developer persona in the orchestrator repo, with cross-member scope. |

## 2. Topology

### 2.1 The org is the container

The system lives in one forge organization (the reference deployment: Forgejo at `code.example.org/athenaeum`). The org contains the orchestrator repo and every member repo as siblings. Org membership and repo visibility are the outermost access-control surface — which is what makes the repo boundary a real tenant boundary (§1.2 principle 2).

### 2.2 On-disk layout

The orchestrator repo's working tree is the workspace; members are cloned inside it at paths the repo ignores:

```
athenaeum/                        ← working tree of athenaeum/athenaeum
├── athenaeum.yaml                ← the member manifest (§2.3)
├── spec/                         ← this document + corpus.md + codex.md
├── tools/                        ← the `athenaeum` distribution (§6)
├── .claude/skills/orchestrator/  ← the driver persona + its institutional memory
├── corpora/                      ← members, UNTRACKED
│   ├── corpus/                   ←   public hub
│   └── corpus-private/           ←   private hub
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
    path: …                # optional — default corpora/{name}
    remote: …              # optional — default {org}/{name}.git
codices:
  {name}:
    description: …
    path: …                # optional — default codices/{name}
    remote: …
```

Members are keyed by name; manifest order is presentation order. The manifest records **membership, not pins** — members are living repos, and the tooling synchronizes them (`ath sync`: clone missing, fetch and report the rest, fast-forward only on request). A deployment bootstraps by cloning the orchestrator repo and running `ath sync`.

### 2.4 Reference directions

```
codex ──corpus://──▶ corpus          (downward: claim evidence, span-precise)
codex ──codex://───▶ sibling codex   (sideways: published ids only, §4.3)
corpus ──▶ (nothing)                 (the foundation references nothing above it)
orchestrator ──manifest──▶ members   (operational, not a data reference)
```

A corpus never references a codex. A codex never reaches into another codex's internals. Notes (regenerable views) are never citation targets. These directions are validated, not just conventional.

## 3. The corpus layer

At architecture altitude: a **corpus** is a content-addressed archive of artifacts, each carried by a faithful markdown record (`records/{ab}/{blake3}.md`, one-level sharding) whose body decomposes the artifact into addressable segments, and whose lifecycle is `stub → draft → normalized` — deterministic ingest and draft, interpretive normalize driven through an external request/claim queue. Schemas (five namespaces: `mime`, `origin`, `atom`, `composite`, `context`) drive normalization and classification per media type, per source, and per corpus. Artifact bytes live in an untracked content-addressed store; records, schemas, and corpus-local extensions are tracked.

Everything in that paragraph — the record grammar, schema system, lifecycle, functional-URI grammar, derived views, queue contract — is specified normatively by **`spec/corpus.md`**. This document adds only the system-level constraints:

- **Two hubs, mutually exclusive content** (the reference deployment): `corpus` for world artifacts, `corpus-private` for personal artifacts. Which hub an artifact belongs to is decided by its subject's tenancy, before capture.
- **Corpus-local extension, universal core.** Format knowledge that is domain- or source-specific (a private drafter, a vendor schema) lives in the corpus that needs it, loaded through the tooling's corpus-local extension seams. The universal package carries no tenant- or vendor-specific knowledge.
- **A corpus carries its own operating discipline.** The public hub embeds the Curator persona; the private hub deliberately carries none (its owner drives the CLI directly). This is per-corpus policy, not architecture.

## 4. The codex layer

### 4.1 What a codex is

A codex is a domain-scoped knowledge repository. Its structure is the **strata**:

```
corpus            faithful bytes                              (not owned by the codex)
   ↓  interpret & declare
facts/            typed claims, every claim evidenced          the durable layer
   ↕  hypothesize / challenge / request
interpretations/  not-yet-facts: hypotheses, assessments,      the epistemic workspace
                  corrections, ingestion needs
   ↓  synthesize & author
notes/            prose views, regenerated from facts          the disposable layer
```

The load-bearing inversion: **facts are durable, notes are regenerable.** Any note can be deleted and rebuilt losslessly because every sentence traces to a fact and every fact traces to bytes.

### 4.2 What is fixed and what is the codex's own

Version 12 of this specification left a codex's internal structure entirely agent-owned. Experience decided the question v12 left open: the facts model generalized across every codex built, and its value — machine-checkable provenance — depends on the structure being uniform. **The codex knowledge representation is now normative**, specified by `spec/codex.md`: the strata, the fact/claim/evidence shapes, the epistemic ladder and authentication bar, the interpretation lifecycle, validation.

What remains the codex's own: its **domain** and scope rules, its **vocabulary** (grown organically, registered in its `VOCAB.md`), its **curation policy** (what to represent, what to cede to siblings, coverage obligations), its **conventions** (hub-subject vs polycentric graphs, applicability disciplines), and its **deliverables**. A codex declares itself — name, corpora it reads, id scheme, strata — in `codex.yaml`, which the shared tooling reads (`spec/codex.md` §2).

### 4.3 Codex independence and sibling citation

Codices are independent repos with no declared joins beyond the manifest. Integration across domains happens by **citation of published identifiers**: `codex://{codex}/{id}`, where the citable id space is defined by `spec/codex.md` §11 (facts and interpretations are citable; notes are not). A codex never reads or references another codex's internals; when two codices describe the same real-world thing, the `same_as` predicate carries the cross-codex identity link.

Tenancy applies at this layer too: a person-agnostic codex reads only the public hub; a personal codex reads the private hub (and may read the public one). The corpora a codex reads are declared in its `codex.yaml`, and citations into undeclared corpora are validation errors.

### 4.4 Operational codices

Most codices only *know*. A codex may additionally *operate* — embed an agent that acts on the systems its domain describes (the reference case: a homelab codex that inspects and proposes changes to live infrastructure). An operational codex's knowledge layer follows `spec/codex.md` unchanged; its operating agent is bounded by an explicit, documented autonomy contract (read-only by default; propose; execute only what the contract enumerates). See `spec/codex.md` §13.

## 5. Pipeline and agents

### 5.1 The deterministic / LLM boundary

| Operation | Type |
|---|---|
| Capture (fetch, hash, store), ingest, MIME detection | Deterministic |
| Draft (mechanical body extraction) | Deterministic |
| Normalize (faithful interpretive refinement) | LLM agent pass |
| Classification: mechanical `classify_when` rules / interpretive fields | Deterministic / LLM respectively |
| Functional-URI resolution, derived views, builds | Deterministic |
| Codex fact authoring, interpretation, note synthesis | LLM agent pass |
| Codex validation (`check`, evidence verification) | Deterministic |
| Member sync/status (`ath`) | Deterministic |

If the operation could produce different valid outputs depending on judgment, it is agent-driven; if the output is a function of the input, it is scripted. This enables independent re-processing at every stage.

### 5.2 Personas

- **The orchestrator persona** (orchestrator repo) — principal developer for the system: specs, tooling, cross-member coherence, member health. Boots from `.claude/skills/orchestrator/`; keeps logbook/state/gotchas as institutional memory.
- **The Curator** (public corpus) — the corpus operating loop: assess → prioritize → propose → execute → report. External captures, deletions, and commits are owner-gated.
- **The Normalizer** (corpus agent) — one record (or small batch) per invocation, draft → normalized, through the decompose/edit/compile substrate; never hand-edits record markdown. Driven through the corpus's request/claim queue by an external loop session (`spec/corpus.md` §8.5) — the corpus tooling never invokes a normalizer itself.
- **Codex agents** — each codex's authoring discipline is carried by its own CLAUDE.md + SCHEMA docs; validation is `ath codex`-tooling plus per-codex checks.

Agent passes are one-item-scoped, report to their driver, and share no state beyond the repos themselves. Concurrency is the driver's decision.

## 6. Tooling

One distribution — **`athenaeum`** (Python, `tools/` in the orchestrator repo) — ships the system's CLIs:

- **`corpus`** — the corpus pipeline and query surface: capture / ingest / draft / normalize-queue verbs, resolve (functional URIs), lint, health, find, decompose/compile, store, gc. Auto-discovers its corpus root; accepts `--corpus-root`.
- **`ath`** — the orchestrator umbrella: `ath sync` / `ath status` against the manifest; `ath corpus …` delegation; `ath codex …` (the codex validation/build/runtime surface, landing with the shared codex package). Deliberately no bare `codex` command.

Tooling agnosticism is normative: no member ids or paths in code; corpus-local and codex-local extensions load through declared seams; a third party brings their own org, members, and agents to the same distribution.

Serving layers (read APIs, browsers, viewers) are deliberately unspecified: they are rebuildable consumers of the contracts above, produced when the system's form calls for them, never load-bearing.

## 7. Change management

- **The specs are law.** Code conforms to `spec/`; when code needs something a spec doesn't cover, the spec changes first — and a change to `spec/corpus.md`'s data contract additionally requires a migration story for every existing record.
- **History files away under tags** (`pre-reforge` marks the 2026-07 restructuring); the working tree carries only the system's current form.
- **Institutional memory is layered like the system**: the orchestrator persona's references for system-level memory; the Curator's references for corpus-level memory; codex docs for codex-level process. Auto-memory is never the source of truth.

---

*Version 13 (2026-07) supersedes v12's two-layer draft: the orchestrator becomes a specified component (eponymous repo + manifest + `ath`), the codex layer's knowledge representation graduates from agent-owned reference convention to the normative ATH-CODEX contract, and the retired viewer/server stack is descoped from the architecture. The corpus contract is unchanged.*
