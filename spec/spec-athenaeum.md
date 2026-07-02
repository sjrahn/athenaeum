---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 12
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-06-22
---

# Athenaeum — Architecture Specification

## 1. Overview

### 1.1 What This Is

The Athenaeum is a knowledge normalization and curation system. It captures content from external sources, normalizes each captured file into a uniform markdown representation, and supports **expert agents** that draw on the corpus to curate a domain of knowledge and produce their own deliverables.

The system has two layers:

- **The corpus is the foundation.** It is the truth, the baseline — a content-addressed archive of captured artifacts, faithful to what was captured. The corpus is the unit of tenant isolation; a "private" corpus and a "public" corpus are separate corpora, and their content should be mutually exclusive. The corpus and the tooling around it are the shared, reusable substrate this specification governs.

- **The codex is the expert above it.** A codex is a domain-scoped knowledge repository that **embeds an expert agent** — the agent pulls from the corpus to curate its domain and maintains the codex's own structure and deliverables. There is no single catch-all knowledge graph and no mandated downstream export format: many codices may coexist, each autonomous, each owning how it organizes its knowledge and what it produces. The only thing the architecture fixes is the **contract by which a codex consumes the corpus** (the `corpus://` functional-URI scheme, the read API, and derived views); everything internal to a codex — its record format, its synthesis structure, the shape of its deliverables — is the codex's own concern and may or may not be generalized across codices later.

This split is deliberate: the corpus layer is the **shared tooling** (a third party can point it at their own corpora), and the codex layer is **agent territory** (a third party brings their own expert agents). The architecture is agnostic to both the corpus topology and the agent topology.

### 1.2 Design Principles

1. **Layered foundation.** The corpus is the foundation, fully independent of the codices above it. A codex depends on one or more corpora; the corpus knows nothing about any codex. References point downward only — from a codex into a corpus, never the reverse. How a codex internally versions or rebuilds itself is the codex's own concern; the corpus is unaffected.

2. **Every record is independently valid.** A single captured page and a fully synthesized monograph are both complete, addressable, useful markdown documents.

3. **Artifact immutability via content addressing.** Captured artifacts are identified by the blake3 hash of their binary content. The bytes never change; if they did, the hash would change and the record would be a different record. Re-encountering the same bytes records another capture against the existing record rather than creating a new one (the corpus tracks that provenance; see `spec-corpus.md`).

4. **Normalization integrity.** An artifact's body is a faithful normalized rendering of its original content. Normalization may produce a more accurate representation (resolve encoding ambiguity, fix format-conversion artifacts, surface OCR text from images) but it MUST NOT add information that didn't exist in the original. Editorial work happens in a codex, not in artifacts.

5. **The normalized body as universal representation.** Every artifact record carries a text body: a normalized rendering of the original file appropriate to its content type. This body projects all modalities into a common representational space — text — enabling universal computation across the corpus. Search, similarity, clustering, and embeddings all operate on this body. The body is the durable, auditable, git-versioned input; everything derived from it is ephemeral cache, rebuildable when models improve or normalization is refined.

6. **Compositional structure lives in the body.** Within a codex, composition is expressed through prose — wikilinks, embeds, and tags — rather than through external metadata. The link graph itself is the hierarchy. Equivalence is computed from intrinsic properties. (The specific structure a codex uses internally is agent-owned; see §2.3.)

7. **Metadata-driven organization.** Classification, grouping, and discovery are tag and link operations, not filesystem operations. Reorganizing the corpus means editing references, never moving or renaming files.

8. **Stable identity.** Every artifact record carries an `id` that is its blake3 hash — immutable with the bytes, permanent, and the same in every corpus that holds those bytes. This is the identity the corpus↔codex contract rests on. How a codex identifies its own internal records (e.g. UUIDv7 minted at authoring time) is an agent-owned convention; see §2.3 and `impl-codex.md`.

9. **LLM-informed.** The data contract is shaped by what the pipeline's LLM agents can produce reliably (faithful normalization, semantic classification, synthesis). The spec describes the data; pipeline mechanics — including which steps are LLM-driven and which are deterministic — live in `impl-corpus.md` and `impl-codex.md`.

10. **Offline-first.** Only capture requires network access. Everything else operates on local data — including normalization (when the local model is sufficient), record authoring, similarity, and codex synthesis.

### 1.3 Terminology

| Term | Definition |
|------|-----------|
| **Record** | The universal unit. A markdown file with YAML frontmatter and a normalized or authored body. The architecture fixes one kind directly — the **artifact record** (in a corpus). A codex's internal records are an agent-owned form (see Codex Record). |
| **Corpus** | A content-addressed archive of artifacts. Identified by name. The unit of tenant isolation — a "private" corpus and a "public" corpus are separate corpora and never merged. Contains artifact records, the binary store, and any base/custom classification schemas the corpus uses. The shared, reusable layer of the system. |
| **Codex** | A named, domain-scoped knowledge repository that embeds an **expert agent**. Lives outside any corpus, in its own repo. Pulls from the corpus (across any loaded corpus) to curate its domain and produces its own deliverables; references the corpus downward only, never another codex. Its internal structure and deliverables are the codex's own concern. Multiple codices may coexist; the runtime determines which are loaded. |
| **Expert Agent** | The autonomous curator embedded in a codex. Reads the corpus through the shared contract (`corpus://`, the read API, derived views), decides how to organize its domain knowledge, and produces the codex's deliverables. The architecture does not constrain the agent's internal method — it is the codex author's to design, and may or may not be generalized across codices. |
| **Artifact Record** | A record representing a single captured file. Identified by the blake3 hash of its binary content (`{blake3}.md`). One record per file, one content type per record. The body is a normalized text rendering of the artifact. The actual binary file is stored in content-addressed storage indexed by the same hash. Artifact records are the ground truth of the corpus. |
| **Codex Record** | A unit of authored knowledge inside a codex. The reference convention (`impl-codex.md`) identifies it by a UUIDv7 (`{uuid}.md`) with a body that wikilinks peer records, footnote-cites artifacts (resolved to APA at build), and embeds artifact-derived views. This internal form is **agent-owned convention**, not fixed by the architecture — a codex may structure its knowledge differently. |
| **`id`** | The identifier field on every record. For an artifact it is the blake3 hash (64-char hex) — the architecture-fixed identity, the same in every corpus that holds the bytes. A codex's internal records carry their own ids by convention (e.g. UUIDv7). The `id` is the filename stem under the container's `records/` directory. |
| **Content-Addressed Naming** | Artifact records are named by the blake3 hash of their binary content. Byte-identical files produce the same hash and therefore the same record — structural deduplication is automatic. A codex's internal records use whatever naming its convention defines (the reference convention uses UUIDv7). |
| **Blake3** | The 256-bit content hash that identifies an artifact record and its underlying binary. 64-character lowercase hex string. Functions as identity, filename stem, and content-addressed storage key. |
| **UUID** | UUIDv7 (RFC 9562) — time-ordered, monotonic-by-creation — the identifier the reference codex convention mints for an internal codex record. Stable within a codex instance; regeneration mints fresh UUIDs. Not used on artifact records (which are blake3-addressed). |
| **Reference** | A wikilink, footnote citation, or embed in a record's body that points to another record. References live in the body, not in frontmatter, and are visible in Obsidian's graph and backlink views. A codex's references point downward only, into the corpus — see §1.2 principle 1 and §2.4. |
| **Wikilink** | `[[id\|display]]` — an intra-container cross-reference. The id is local to the container (blake3 in artifact bodies; the codex's own ids in codex-record bodies). Wikilinks never cross containers. The display text is optional. |
| **Footnote Citation** | `text[^N]` with `[^N]: <bare-uri>` at the bottom of a codex record — the downward-citation form into the corpus: `[^N]: corpus://{hash}`. A codex build resolves these into APA-style citations. |
| **Embed** | `![[target]]` — inline content inclusion. In artifact bodies: raw `![[blake3]]` for intra-corpus cross-refs that mirror the original content's embeds. In codex-record bodies: functional URI `![[corpus://hash?params]]` (or no params for the identity transform); always targets an artifact. |
| **Tag** | A flat, kebab-case classification label matching `[a-z0-9]+(-[a-z0-9]+)*`. In the reference codex convention, tags are codex-local labels on codex records. Artifact records classify through a corpus-layer derived view instead (see `spec-corpus.md`). |
| **Capture** | An encounter event recorded against an artifact. Re-encountering identical bytes records another capture on the existing artifact (the corpus tracks the provenance; see `spec-corpus.md`); the bytes themselves never move and never produce a new record. |
| **Normalization** | Producing the artifact's text body — extraction (HTML→markdown, PDF→text), transcription (audio/video→text), description (image→text), or metadata summary (opaque binary). Faithful to the original. |
| **Functional URI** | The composable `corpus://` scheme a codex uses to reference the corpus. `corpus://{hash}` references an artifact (whole, by anchor `#section`, or by transformation `?page=4&crop=…`). It is the heart of the corpus↔codex contract; its grammar and parameters are defined by `spec-corpus.md` §6. Resolved at compile/render time. |
| **Schema** | A corpus-layer reference document describing how to normalize or classify content. The corpus model organizes schemas into five namespaces (`mime` / `origin` / `atom` / `composite` / `context`), with MIME-base as the required floor, composite as the optional corpus-author-driven classification layer, and context for annotations; see `spec-corpus.md`. |

---

## 2. Core Model

### 2.1 Records and Containers

A **record** is the universal unit of the Athenaeum. Every record is a single markdown file with YAML frontmatter and a body. The architecture fixes one record kind directly, and a codex defines its own:

- **Artifact records** — one per captured file, named by the blake3 hash of the binary content. Artifact records live in **a corpus** and are fully specified by `spec-corpus.md`.

- **Codex records** — the units of authored knowledge inside **a codex**. Their form is agent-owned convention (the reference convention names them by UUIDv7); see §2.3.

The system has two layers of container:

| Container | Holds | Identifier | Reference direction |
|-----------|-------|-----------|--------------------|
| **Corpus** | Artifact records, the binary cache, schemas, capture staging. | Corpus name. | None outbound (corpora reference nothing). |
| **Codex** | The authored knowledge of a domain, curated by its embedded expert agent, plus the agent's deliverables. | Codex name. | Downward into the corpus only: footnote citations to artifacts (`[^N]: corpus://{hash}`), functional-URI embeds of artifacts (`![[corpus://{hash}?params]]`), and intra-codex references the codex defines for itself (e.g. `[[uuid]]` peer wikilinks). Never references another codex. |

Both layers use a `records/` directory for tracked markdown records. The corpus additionally maintains an `artifacts/` cache for raw binary content; the cache is **untracked** (regenerable from blake3 plus capture provenance).

**Corpus directory layout (high level):**

```
corpus-{name}/
├── records/      — Artifact Records (tracked markdown, content-addressed by blake3)
├── artifacts/    — raw binary cache (UNTRACKED, .gitignore'd)
├── capture/      — staging for in-progress captures
└── schema/       — corpus schemas (specified by spec-corpus.md)
```

**Codex directory layout (reference convention; agent-owned):**

```
codex-{name}/
├── codex.yaml    — codex-level metadata (optional; see §2.5)
└── records/      — Codex Records (tracked markdown, UUID-named by convention)
```

A codex's internal layout is the codex's own concern. The shape above is the reference convention documented in `impl-codex.md`; a codex may organize itself and lay out its deliverables differently. The architecture only requires that, however a codex is built, it references the corpus through the shared contract (§2.3).

**Directory purposes:**

- **`records/`** (both layers) — Tracked markdown records. Layout under `records/` (sharding, etc.) is an implementation concern; the architecture only fixes that an *artifact* record is locatable by its blake3 identity. A codex locates its own records however its convention defines.
- **`artifacts/` / `capture/` / `schema/`** (corpus only) — the corpus's untracked binary cache (regenerable from blake3 + capture provenance), capture staging, and schemas. These corpus internals are specified by **`spec-corpus.md`** (§2.2).

There is no nesting beyond the top-level separation in the corpus. Within a corpus, organization is expressed through references and computed similarity — not directory hierarchy. Concrete on-disk paths and sharding live in the implementation guides (`impl-corpus.md` for the corpus, `impl-codex.md` for the codex/agent side).

### 2.2 The Corpus Layer

The corpus layer — the artifact-record format, frontmatter, normalized body, classification, provenance, schemas, deduplication, and the `corpus://` functional-URI scheme — is specified by **`spec-corpus.md`** (ATH-CORPUS), the authoritative contract for everything inside a corpus. This document specifies the architecture and the codex layer above the corpus; it does not restate the corpus contract.

At architecture altitude: a **corpus** is a content-addressed archive of **artifact records**, each identified by the blake3 hash of its captured bytes (the record's `id`, also the `{blake3}.md` filename stem) and carrying a normalized text body — a faithful rendering of the original file into markdown that projects every modality into a common representational space, enabling universal computation (search, similarity, embeddings) across the corpus. Byte-identical captures deduplicate to a single record. Artifacts are immutable (the bytes define the identity), reference nothing in the codices above them, and are the ground truth the whole system rests on. A codex references artifacts downward via footnote citations and functional-URI embeds (§3.6, §3.7), using the `corpus://` scheme that `spec-corpus.md` defines.

### 2.3 The Codex Layer

A **codex** is a domain-scoped knowledge repository that embeds an **expert agent**. It lives outside the corpus, in its own repo, and exists to curate a domain: the agent pulls from the corpus, organizes what it finds, and produces the codex's deliverables — a browsable knowledge base, a tuned reference document, an index, an answering service, whatever the domain calls for.

**The shared contract is corpus consumption.** The one thing the architecture fixes about a codex is *how it reaches into the corpus*:

- **Footnote citations** of artifacts — `text[^N]` with `[^N]: corpus://{hash}` (optionally `#anchor` or `?params`), resolved to APA-style citations at build time.
- **Functional-URI embeds** of artifact-derived views — `![[corpus://{hash}?params]]` (or bare for the identity transform).
- References point **downward only**, into the corpus. A codex never references another codex (§1.2 principle 1, §2.5).

The `corpus://` scheme, the read API, and the corpus's derived views are the complete surface a codex consumes; they are defined by `spec-corpus.md` and exposed by the shared tooling. A third party builds a codex against this surface alone.

**Everything internal to a codex is agent-owned.** How the agent represents its curated knowledge — record format, identifiers, link/tag structure, the form of its deliverables — is the codex author's design, not fixed by this specification. The **reference convention** (documented in `impl-codex.md`) models a codex as a set of *codex records*: authored markdown compositions, each identified by a UUIDv7, with thin frontmatter (`id`, `title`, `description`, `status`, `tags`) and a body that wikilinks peer records, footnote-cites artifacts, and embeds artifact-derived views. That convention is one good way to build a codex; whether it generalizes across all codices is deliberately left open.

**A codex is where editorial work lives.** Unlike artifact bodies (which faithfully mirror their original content), a codex's authored content is written by its expert agent (or a human curator): it adds interpretation, analysis, and context no single artifact contains; structures knowledge for a particular audience or purpose; reconciles disagreements across artifacts; and carries the editorial voice that artifacts intentionally lack.

### 2.4 The Reference Graph

Composition is expressed through references in record bodies. The link graph itself is the hierarchy.

References point downward only. Within a single codex:

```
artifact a7f3…   ──┐
                   ├──►  song-meridian   ──┐
artifact e5f6…   ──┘                       │
                                           ├──►  album-convergence
artifact i9j0…   ──┐                       │
                   ├──►  song-tidal      ──┘
artifact o5p6…   ──┘
```

Each arrow is a footnote citation, functional-URI embed, or intra-codex wikilink appearing in the body of the referencing record. The "Album" codex record wikilinks its track records (peers in the same codex); each track record footnote-cites the artifacts it draws on (in the corpus). Reading the body reveals the structure; no separate metadata block restates it. (The intra-codex links shown here are the reference convention's; a codex may structure its own graph differently — §2.3.)

Across the two layers:

- **Artifact records (corpus)** — bodies may wikilink other artifacts in the same corpus when the original content's hyperlinks/embeds resolve to captured targets. Artifacts never reference a codex.
- **Codex records (codex)** — bodies footnote-cite artifacts (`[^N]: corpus://{hash}`) and embed artifact-derived views via functional URIs (`![[corpus://{hash}?params]]`), reaching downward into the corpus, and reference peer records within the same codex however the codex's convention defines (the reference convention uses `[[uuid]]` wikilinks). **A codex never references another codex.** When integration across domains is needed, that is itself a codex's deliverable, built like any other (§2.5).

**Properties:**

- **Composition is implicit.** Following references reconstructs the structure. There is no canonical "tree" — a record may have many parents and many children.
- **Acyclic by convention within a codex.** Cycles are technically possible but conventionally avoided in compositional structures. Cross-references between peer records in the same codex are fine and frequently desirable.
- **Non-destructive.** Authoring a record does not modify or consume the artifacts (or peer records) it references. References are pointers; targets remain independent.
- **Multi-consumer.** A single artifact may be cited by many codices. An interview-transcript artifact might be cited by an artist-profile codex in one repo and a documentary-film codex in another — neither codex knows about the other; the shared artifact is the only thing they have in common.
- **Strictly downward.** References don't cycle across layers; the corpus knows nothing about the codices that cite it.

### 2.5 Codices Are Independent

A codex lives outside the corpus, structurally independent of any specific corpus and of every other codex. The runtime configuration — which codices are loaded, which corpora are loaded — is the join; content addressing handles the rest.

**Codex contents (reference convention).**

- **`records/`** — the codex's authored records (UUID-named by convention).
- **`codex.yaml`** (optional) — codex-level metadata: display name, description, an optional tag vocabulary or conventions reference. The architecture mandates no fields here; this is a place for codex-author convention. A codex whose deliverable is not a record set may not have a `records/` directory at all.

A codex's body references reach downward into the corpus (footnote citations and functional-URI embeds, §2.3) and across its own internal records however its convention defines (§3.6 gives the per-primitive resolution rules for the reference convention).

**Codex naming.** A codex is identified by name. The runtime maintains a mapping from codex name to on-disk location (or remote URI), so a `codex://{name}/…` reference — used when one codex's deliverable cites another codex's output — can be resolved against the loaded codices. How a codex addresses its own internal records is its convention (§2.3).

**Autonomy.** A codex owns its structure, its build process, and its deliverables. It may be authored by hand, driven by its embedded expert agent, or regenerated by a pass that re-derives it from a corpus snapshot plus authoring prompts. Regeneration is a wholesale event — the codex's name is preserved but its internal records are replaced (the reference convention mints fresh UUIDs). Because nothing in the architecture *above* a codex depends on a codex's internal ids, the blast radius of a regeneration is the codex's own concern; any other codex that cites it decides for itself how to track that dependency.

**Many codices, no declared joins.** A user — or an organization, or the wider world — may have many codices: personal, professional, project-specific, one per domain expert. Each is structurally independent. Two people independently maintaining codices over the same corpus is the expected case, not a conflict: the shared corpus is the only thing they have in common, and that is enough. There is no single catch-all knowledge graph — knowledge lives, broken out by domain, in the codices that curate it.

### 2.6 Re-normalization

Normalization and re-normalization of artifact bodies — when and how an artifact is (re)rendered — are corpus-layer mechanics specified by **`spec-corpus.md`** (its `stub → draft → normalized` lifecycle and re-run model). Normalization integrity holds throughout (§1.2 principle 4): a re-normalized body stays faithful to the original bytes, and editorial enrichment that draws on outside context lives in a codex, never in artifacts. A codex's authored content is re-authored, not re-normalized.

### 2.7 Every Record Is a Valid Markdown Document

There is no "incomplete" state in terms of record validity. A freshly captured artifact whose body has been normalized is a complete, useful markdown document. An authored codex record whose body cites a single artifact is a complete, useful markdown document. The corpus is always in a valid state; any artifact can be drawn on by a codex at any time. Authoring richer codex content on top of existing artifacts is enrichment, not a completion requirement.

---

## 3. Record Format

### 3.1 Frontmatter Schema

All record metadata lives in YAML frontmatter at the top of each `.md` file. There are no separate configuration files — the markdown file is the single source of truth for both metadata and content.

Artifact frontmatter — and the schema library that drives it — is a corpus-layer concern specified by `spec-corpus.md` (§2.2, §3.3). The fields below are the cross-layer core plus the codex-record specifics (reference convention).

#### 3.1.1 Core Fields

Every record carries an `id`, a `description`, and a `status`. **Artifact-record frontmatter is specified by `spec-corpus.md`** (§3.1.2) — in the corpus model an artifact's title, media type, and most metadata live in its body blocks, not frontmatter. A codex record additionally carries a `title` and (by the reference convention) `tags`; the exact codex-record frontmatter is agent-owned convention (§3.1.3).

| Field | Type | Required | Applies to | Description |
|-------|------|----------|------------|-------------|
| `id` | string | yes | all | Record identifier and filename stem under the container's `records/` directory. **Artifact:** the blake3 hash of the binary content, 64-character lowercase hex (architecture-fixed). **Codex record (reference convention):** UUIDv7 (RFC 9562, time-ordered, monotonic-by-creation). |
| `title` | string | yes (codex record) | codex records | Short descriptive label. An artifact's title lives in its corpus body block, not frontmatter (see `spec-corpus.md`). |
| `description` | string | yes | all | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `status` | enum | yes | all | Lifecycle state: `stub` (captured, no body), `draft` (body filled), `normalized` (refined, ready for use). Codex records typically begin at `draft` since authoring fills the body directly. |
| `tags` | string[] | no | codex records (reference convention) | Classification tags. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Declare what this codex record is about. Tags are codex-local — a codex MAY define a tag vocabulary in its `codex.yaml` or a conventions file for consistency. Frontmatter tags declare whole-record topical coverage; inline `%% #tag %%` annotations (§3.2.5) provide positional precision within the body. |

Artifact classification is a corpus-layer concern — derived from the artifact's body blocks, specified by `spec-corpus.md`, not declared in frontmatter here. (`visibility`, the editorial curation layer for retiring low-quality artifacts without deleting them, is an artifact frontmatter field in the corpus model — see `spec-corpus.md`.)

**Record type signaling.** An artifact record is unmistakable: its **container** (a corpus's `records/`) and its **`id` shape** (64-character lowercase hex blake3) always agree. A codex's records are signalled by the codex's own convention (the reference convention uses UUIDv7 ids in the codex's `records/`).

#### 3.1.2 Artifact Frontmatter

Artifact-record frontmatter is specified by **`spec-corpus.md`**, not here. In the corpus model it is bytes-identity only (`id`, `description`, `status`, byte-hash fields, the `touch[]` provenance chain, `visibility`); everything else an artifact carries — its media type, origins/URIs, capture timestamps, classifications, and schema-extracted fields — lives in the record's **body blocks**, not frontmatter, and is exposed through on-demand derived views. A codex never reads artifact frontmatter directly; it references artifacts through the `corpus://` scheme (§3.6, §3.7).

#### 3.1.3 Codex-Record Fields (Reference Convention)

Present on codex records under the reference convention; a codex that structures its knowledge differently defines its own (§2.3).

Codex-record frontmatter is deliberately thin. The reference convention's complete set is the core fields `id`, `title`, `description`, `status`, `tags` — and that is it. No `content_type` (codex records are markdown by construction), no `visibility`, no quality or pipeline metadata. Structural relationships are body references — intra-codex wikilinks, footnote citations of artifacts, functional-URI embeds — and computed similarity (see §3.5). The body is the authoritative record of what knowledge the codex record synthesizes and what evidence it draws on.

Credibility, when relevant, is consulted by reading the credibility-signal classifications on the evidentiary artifacts the codex record cites — a corpus-layer derived view (see `spec-corpus.md`). The codex record itself carries no credibility field.

#### 3.1.4 Issues

Quality and completeness problems on artifacts (missing media, broken links, partial capture, content modified since publication, encoding corruption, format loss) are a corpus-layer concern — recorded as `context` blocks in the `issue` namespace and surfaced through the corpus's derived `issues` view, specified by **`spec-corpus.md`**. They are not record frontmatter in this spec.

#### 3.1.5 Extended Fields

Format-intrinsic and classification-derived fields (a web article's `byline` / `published_date`, an audio file's `artist` / `album`, a PDF's `page_count`) are a corpus-layer concern. In the corpus model they live in the artifact's body blocks and schema-declared namespaces and surface through derived views, specified by **`spec-corpus.md`** — not as record frontmatter here.

### 3.2 Body Format

The body of a record is the markdown content below the frontmatter closing `---`. **Artifact bodies** are a corpus-layer concern — their structure (the normalized rendering and the metadata / content / annotation block grammar) is specified by **`spec-corpus.md`**. This section covers **codex-record bodies** as the reference convention for a codex's authored content (§2.3); a codex may author its content differently.

#### 3.2.1 Artifact Body Integrity

An artifact's body is a faithful normalized rendering of its original content — it adds no editorial content, interpretation, or connection that wasn't in the original (§1.2 principle 4). The block-structured body grammar and the normalization rules are specified by **`spec-corpus.md`**.

#### 3.2.2 Cross-Reference Resolution

Resolving an artifact's original hyperlinks and embedded resources to intra-corpus references (raw `[[blake3]]` wikilinks / `![[blake3]]` embeds) is a corpus-layer concern, specified by **`spec-corpus.md`**. A codex's bodies do not use raw blake3 references; they reference artifacts via the `corpus://` scheme (§3.6, §3.7).

#### 3.2.3 What Embeds Mean

In codex-record bodies, embeds are functional URIs targeting an artifact: `![[corpus://{hash}?params]]`. The `params` may transform the artifact (page extract, framegrab, crop); a bare `![[corpus://{hash}]]` is the identity transform. Codex records are not embedded — they are wikilinked or footnote-cited. (Within an artifact body, a raw `![[blake3]]` embed means something narrower — an intra-corpus mirror of the original content; that is a corpus-layer concern, see `spec-corpus.md`.)

In compiled outputs (mdbook, static site), the tooling substitutes the actual binary (renders the image, embeds the audio) once the URI is resolved.

#### 3.2.4 Codex-Record Bodies

Codex-record bodies are authored compositions with full editorial freedom. They are written by curators or synthesis agents. They may:

- Add interpretation, analysis, and context that no single artifact contains.
- Structure knowledge for a particular audience or purpose.
- Cite artifacts via footnote: `text[^N]` with `[^N]: corpus://{hash}` (with optional `#anchor` or `?page=4`) at the bottom of the record. Footnote URIs resolve to APA-style citations at build/export time.
- Embed artifact content via functional URI: `![[corpus://{hash}]]` or `![[corpus://{hash}?params|alt text]]`.
- Wikilink to peer codex records in the same codex: `[[uuid|display text]]`.
- Use tags for topical classification (frontmatter, or inline `%% #tag %%` per §3.2.5).

#### 3.2.5 Inline Topic Annotations

Codex-record bodies may contain topic annotations in Obsidian-style comment blocks. These supplement the record's frontmatter `tags` field with positional precision — useful when a codex record covers multiple sub-topics and the author wants a section or passage tagged distinctly.

**Syntax:** `%% #tag %%` or `%% #tag-1 #tag-2 %%`

**Scoping rules:**

1. **Frontmatter `tags`** — whole-record scope. Every line is implicitly within these topics.
2. **Annotation on a heading** — section scope. Applies until the next heading of equal or higher level.
3. **Annotation on a line** — passage scope. Applies to that specific line only.

Scopes are additive. Annotate at topical transition points, not on every line.

Inline annotations are valid only in codex-record bodies. Artifact bodies remain faithful to the original content (§3.2.1); their classification is a corpus-layer derived view (see `spec-corpus.md`).

#### 3.2.6 Referencing Artifacts from Codex Records

Codex records reference artifacts in two ways:

- **Footnote citations** (`text[^N]` with `[^N]: corpus://{hash}` at the bottom of the record). Citation-style references resolved to APA at build/export time. May target sections (`corpus://{hash}#anchor`) or page extracts (`corpus://{hash}?page=4`).
- **Functional-URI embeds** (`![[corpus://{hash}]]` or `![[corpus://{hash}?params]]`). Inline content inclusion. The `params` transform (page extract, framegrab, crop) where useful; a bare `![[corpus://{hash}]]` is the identity transform (whole artifact).

Both produce backlinks visible in Obsidian's graph view, making it discoverable which codex records draw on which artifacts.

#### 3.2.7 Connecting Codex Records to Codex Records

Codex records connect to each other through:

- **Wikilinks** — `[[uuid|display text]]`. Cross-references between codex records in the same codex (e.g., `[[0193fb3c-7a8b-7c9d-…|Brake System Overview]]`).
- **Tags** — shared classification. Codex records tagged `#brake-caliper` are discoverable together.

Codex records are not embedded — when one codex record needs to draw on another, wikilink to it. Compositional structure is expressed through the codex graph itself: a "Brake System Overview" codex record that wikilinks to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" records *is* the compositional structure. The links in the body are the hierarchy.

### 3.3 Schema Library

Schemas — how an artifact's media type drives normalization, what fields are extracted, and how classification works — are a corpus-layer concern, specified by **`spec-corpus.md`**. The corpus model organizes them into five namespaces (`mime` / `origin` / `atom` / `composite` / `context`): MIME-base classification is the required data-contract floor, custom (composite) classification is the optional corpus-author-driven layer on top, and `context` carries annotations (issues, references).

Custom classification is a *living curatorial artifact*: patterns that emerge while authoring codex records — a recurring source type, a credibility signal worth capturing — become new corpus classification schemas, applied retroactively by re-normalization so that subsequent authoring is richer. That feedback loop, where the codex layer surfaces signals that drive corpus classification, is the Curator's job (§5.5); the schema mechanics live in `spec-corpus.md`.

### 3.4 Examples

For an **artifact-record** example — frontmatter, body blocks, and classifications — see `spec-corpus.md`. The example below is a **codex record**.

#### Codex Record

```yaml
---
id: "0193fb3c-7a8b-7c9d-9e0f-1a2b3c4d5e6f"
title: "Brake Caliper Rebuild"
description: "Authored guide to rebuilding the front calipers on a sliding-caliper braking system, drawing on the service manual, a community forum thread, and a video walkthrough."
status: draft
tags: [brake-caliper, caliper-rebuild]
---

## Overview

The front brake calipers in a typical single-piston sliding design
are straightforward to rebuild, but the piston bore must be inspected
carefully.

![[corpus://a7f3b2c1?page=4&crop=50,100,550,400|Caliper exploded diagram from service manual]]

## Inspection

Remove the caliper mounting bolts using the appropriate socket size.
See the service-manual procedure[^1] for torque specs.

Inspect the piston bore for scoring:

![[corpus://c9d0e1f2?framegrab=1:23|Bore scoring example from video walkthrough]]

If scoring is visible as in the image above, the caliper must be
replaced — the bore cannot be honed back to spec on this design. See
the forum-thread discussion[^2] for additional commentary.

## Related

- [[0193fb3c-7a8b-7c9d-9e0f-1a2b3c4d5e70|Brake Bleeding Procedure]] — must bench-bleed before reassembly
- [[0193fb3c-7a8b-7c9d-9e0f-1a2b3c4d5e71|Rotor Replacement]] — often done at the same time
- [[0193fb3c-7a8b-7c9d-9e0f-1a2b3c4d5e72|Brake System Overview]] — parent record

[^1]: corpus://b8c9d0e1d4e5f6a7b8c9d0e1f2a3b4c5...
[^2]: corpus://d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5...
```

The codex record uses footnote citations for downward artifact references (resolved to APA at build time), functional-URI embeds for inline artifact-derived views (page extracts, framegrabs), and intra-codex wikilinks (`[[uuid]]`) for peer codex records. The footnote bodies carry bare `corpus://` URIs that the build resolves into proper APA-style citations, drawing author / publication-date / title / source from the cited artifact's metadata (its corpus body blocks and derived views; see `spec-corpus.md`).

### 3.5 Classification

Classification uses three mechanisms: tags (on codex records), the codex graph (wikilinks among codex records), and computed similarity (a corpus-layer capability over normalized bodies and perceptual hashes; see `spec-corpus.md`).

#### 3.5.1 Tags

Tags are a codex-record primitive — they handle categorical classification on codex records exclusively. A codex record tagged `brake-caliper` and `vehicle-platform-x` is discoverable at the intersection. Tags are flat (no hierarchy), portable (no external dependencies), and codex-local — a tag means whatever the codex's conventions say it means. Tags appear in frontmatter (whole-record scope) and may also appear inline in the body (`%% #tag %%`, §3.2.5).

A codex MAY maintain a conventions file or use `codex.yaml` to list its tag vocabulary with one-line descriptions. This is guidance, not constraint — unknown tags are valid and signal vocabulary growth.

Artifact classification works differently: it is a corpus-layer concern, derived from the artifact's body blocks rather than declared in frontmatter (see `spec-corpus.md`). Each applied classification carries a justification; the schema-application *is* the artifact's classification signal.

#### 3.5.2 The Codex Graph

The codex graph handles structural organization. A "Brake System Overview" codex record that links to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" records expresses compositional structure through its body. The link graph is the hierarchy.

A codex record that represents a concept (a category, a person, a place, a thing) is just a regular codex record with descriptive prose; other records reference it by wikilink. The role is emergent from the graph.

#### 3.5.3 Deduplication and Similarity

Deduplication and similarity over artifacts — exact (blake3), perceptual (per-format hashes), and semantic (embeddings of the normalized body) — are computed from intrinsic artifact properties and are a corpus-layer concern, specified by **`spec-corpus.md`**. A codex consumes the results (e.g., finding related artifacts to cite) but does not define them.

### 3.6 Reference Resolution

The reference primitives express the graph. Each has a single resolution rule.

**Wikilinks `[[id]]` — intra-container only.**

- Artifact body: `[[blake3]]` → an artifact in the same corpus (intra-corpus; a corpus-layer concern, see `spec-corpus.md`). Same-bytes blake3 collision across loaded corpora is harmless — the bytes are by definition identical; either copy resolves correctly.
- Codex-record body (reference convention): `[[uuid]]` → another record in the same codex.

Wikilinks never cross containers. A codex record never wikilinks an artifact or another codex's record.

**Footnote citations `text[^N]` with `[^N]: <uri>` — downward citation into the corpus.**

- Codex body → artifact: `[^N]: corpus://{hash}` (with optional `#anchor` or `?params`), or `corpus://{name}/{hash}` for provenance disambiguation when two loaded corpora share a hash.

The footnote body carries a bare URI; the codex build resolves it into a proper APA-style citation, generating author / publication-date / title / source from the artifact's metadata (its corpus body blocks and derived views, `spec-corpus.md`). The footnote label is author-chosen (numeric or short slug) and is preserved through resolution. (When one codex's deliverable cites another codex's output, it uses the `codex://{name}/{id}` form — a cross-codex citation resolved against the loaded codices; see §3.7.)

**Embeds `![[…]]` — functional inclusion (or intra-corpus raw cross-ref).**

- Artifact body: `![[blake3]]` → intra-corpus raw embed (a corpus-layer concern, §3.2.2, `spec-corpus.md`). Mirrors the original content's embeds; no scheme prefix, no transformation.
- Codex-record body: `![[corpus://{hash}?params]]` → functional URI embed of an artifact. A bare `![[corpus://{hash}]]` is the identity transform.

Codex records are never embedded — when one codex record needs to draw on another, wikilink it.

**Unresolved references.** A reference that cannot be resolved is surfaced as broken (Obsidian-style raw browsing) or flagged in compiled outputs with a clearly-marked fallback rather than silently dropped. Tooling backlink panels list unresolved references as authoring follow-ups.

**Cross-corpus same-bytes.** When multiple corpora are loaded, the same blake3 may appear in more than one. This is harmless — the bytes are identical, and a bare reference resolves to either copy. A codex uses the qualified `corpus://{name}/{hash}` form when provenance assertion matters.

### 3.7 Functional URI Scheme

Functional URIs are the corpus-consumption primitive a codex uses. They appear in footnote citations (resolved to APA at build time) and in embeds (resolved to inline content). Two schemes:

- **`corpus://`** — references an artifact by content hash. Used in footnote citations and embeds. This is the heart of the corpus↔codex contract. **Its grammar, transformation parameters (`page`, `crop`/`bbox`, `resize`, `framegrab`/`time_range`, `grayscale`, …), resolver contract, and caching are defined by `spec-corpus.md` (§6);** a codex uses the scheme as-is.
- **`codex://`** — references a codex's *output* by codex name and record id. The cross-codex citation form: when one codex's deliverable cites another codex's output, it uses `codex://{name}/{id}`, resolved against the loaded codices. A codex never reaches *into* another codex's internals — it cites a published output, the way it would cite any external work.

**`corpus://` (summary).** Base form `corpus://{hash}` resolves to an artifact in any loaded corpus that has the hash; `corpus://{name}/{hash}` asserts which corpus (provenance, for when two loaded corpora share a hash); `corpus://{hash}#anchor` navigates to a named region; query parameters compose left-to-right into a derived view (e.g. `corpus://{hash}?page=4&crop=50,100,550,400`). The authoritative form and parameter set live in `spec-corpus.md` §6.

**`codex://` (summary).** Base form `codex://{name}/{id}` resolves to the named output of the codex named `{name}` (the reference convention's record id is a UUIDv7); `codex://{name}/{id}#anchor` navigates to a named section. No transformation parameters — a codex output is cited, not transformed into a derived view. The id shape and what a codex exposes for citation are the cited codex's own convention.

**Semantics.** Functional URIs are **deterministic** (the underlying artifact is immutable by content addressing; a codex output's id is stable within that codex's instance), **cacheable** (the cache key is the full URI string), and **ephemeral** (they exist at compile/render time, not as stored records). In raw Obsidian browsing, an unresolved URI falls back to its alt text or footnote label. In compiled outputs (mdbook, static site), the build resolves every functional URI — computing artifact transformations for embeds, and generating APA-style citations from footnote URIs (drawing author / date / title from the target's metadata: an artifact's via its corpus body blocks and derived views).

---

## 4. Pipeline

The path from raw content to a richly authored corpus has discrete steps; each is independently re-runnable.

- **Capture** brings content into the corpus. Identity is the hash of the bytes; failed captures consume no identity space. Capture is the only step requiring network access. Every captured file becomes its own artifact record; bundles of related files (a page plus its embedded images, a video plus its description page) become multiple artifact records, related through cross-references in their normalized bodies.

- **Normalize** transforms an artifact stub into a complete record — producing the faithful normalized body, applying classification, and resolving intra-corpus cross-references. The corpus-layer mechanics (the `stub → draft → normalized` lifecycle, the schema namespaces, and where classification and extracted fields live in the record) are specified by `spec-corpus.md`. Bodies are faithful — normalization may improve accuracy but never adds information not present in the original.

- **Author** creates or edits a codex's authored content (in the reference convention, a codex record) that synthesizes knowledge across artifacts and the codex's own peer records. The author writes nothing outside the target codex. Authoring is non-destructive: referenced artifacts and peer records are unchanged and independently addressable.

- **Re-normalize** is on-demand re-running of normalization when context, schemas, or models improve, or when newly captured artifacts resolve previously unresolved cross-references. Integrity is preserved — the new body remains a faithful rendering of the original artifact.

- **Build** materialises a layer for viewing or publication. Each is independently exportable:

  - **Corpus build** — a browsable artifact vault. Resolves intra-corpus wikilinks among artifacts; serves binaries via the corpus's `artifacts/` cache.
  - **Codex build** — the codex's own deliverable, produced by its expert agent: a browsable knowledge work (mdbook, static site, vault), a tuned portable reference document, an index, or whatever the domain calls for. It resolves the codex's intra-container references and its downward references into the corpus (footnote URIs to artifacts, resolved into APA-style citations; functional-URI embeds). The codex's referenced corpora must be loaded. The build process and output format are the codex's own concern; the reference convention is documented in `impl-codex.md`.

  The build process can also generate a lookup index mapping any known URI to its artifact id, enabling consumers to find records by any URL known to resolve to them.

Procedural detail — fetch / hash / store ordering, MIME detection, conversion tooling, cross-reference-resolution mechanics, contextualization sub-steps, schema authoring, sharding, build mechanics, output formats — lives in `impl-corpus.md` and `impl-codex.md`. The corpus-layer data contract (record format, schemas, lifecycle) is specified by `spec-corpus.md`.

### 4.1 Phase Boundaries and Re-processing

Pipeline steps are independently re-runnable:

| Operation | Scope | Trigger |
|-----------|-------|---------|
| **Re-capture** | One artifact (new bytes → new record) | Upstream content has changed |
| **Re-convert** | Artifacts of a given MIME or extraction-tool generation | Conversion tools improved |
| **Re-resolve cross-references** | Any artifact body | New artifacts captured |
| **Re-contextualize** | Artifacts processed by older models | LLM models improved |
| **Re-author a codex record** | One codex record | Knowledge updated; new artifacts available |
| **Rebuild similarity caches** | Tier 2/3 indices | Model upgrades; index drift |

Each operation can target specific records via metadata queries. The implementation tracks pipeline-state metadata (conversion tooling version, normalization model identifier, etc.) outside the spec-defined record contract; see `impl-corpus.md`.

---

## 5. Pipeline Agents

### 5.1 Overview

The pipeline is operated by specialized agents — lightweight, single-purpose workers that each handle one item per invocation. The **Capturer** and **Normalizer** are corpus-layer agents (shared tooling, described here as the reference pipeline). The **Author** and **Curator** describe how a codex's embedded expert agent does its work and how that work is orchestrated — the reference convention; a codex may operate differently. Agents have focused responsibilities, process exactly one item, and report results to a coordinator. There is no inter-agent communication and no shared state beyond the corpus filesystem.

Agents consult the corpus's schemas (specified by `spec-corpus.md`) to apply consistent normalization and classification per content type.

### 5.2 Capturer

Brings a single content item into the corpus.

**Model class:** Haiku-tier (fast, cheap — no creative judgment needed).

**Scope:** One content item per invocation.

**Output contract:** When the capturer finishes successfully, the artifact record for the captured bytes exists (newly created or augmented with this capture's provenance), and the binary lives in the content-addressed store keyed by its blake3 hash. The artifact's MIME has been determined, and every hash declared by its schema has been computed and recorded. The capturer reports whether the record is new or existing, plus any warnings.

The capturer is a reliable executor, not a decision maker — it does not choose what to capture or how to classify content. The procedural details (fetch tooling, MIME-detect ordering, in-memory vs on-disk staging) live in `impl-corpus.md`.

### 5.3 Normalizer

Brings an artifact stub to `status: normalized`.

**Model class:** Sonnet-tier (creative judgment required for contextualization, issue surfacing, description generation).

**Scope:** One artifact per invocation.

**Output contract:** When the normalizer finishes successfully, the artifact record carries a faithful normalized body, its classifications and extracted fields, a refined `description`, and `status: normalized`; any hyperlink or embed in the original content whose target exists in the corpus has been rewritten as an intra-corpus reference (targets not in the corpus remain plain URLs), and the normalizer never invents links the original didn't contain. Exactly where classifications and extracted fields live in the record, and the block grammar of the body, are the corpus normalization contract — specified by `spec-corpus.md`.

Self-verification responsibilities: the artifact's declared media type must match the MIME of the stored binary, and the `id` field must match the binary's blake3 hash.

### 5.4 Author

Creates or edits a codex's authored content (in the reference convention, a codex record). This is the codex's embedded expert agent doing synthesis; the contract below describes the reference convention.

**Model class:** Sonnet-tier (semantic judgment required for synthesis).

**Scope:** One record per invocation, in one codex.

**Output contract:** When the author finishes successfully, a record exists in the target codex with the convention's `id` (UUIDv7), title, description, status, and tags. The body is authored markdown prose: it footnote-cites artifacts (`[^N]: corpus://{hash}` resolved to APA at build), embeds artifact-derived views via functional URIs (`![[corpus://{hash}?params]]`), wikilinks peer records in the same codex (`[[uuid]]`), and applies tags in frontmatter. Backlinks and related-record candidates within the codex are surfaced for follow-up. The author writes nothing outside the target codex, and never into another codex.

### 5.5 Curator

Autonomous orchestration skill that assesses corpus state, prioritizes work, and dispatches agents. Also responsible for the schema-feedback loop (§3.3) — monitoring the codex layer for emerging patterns and proposing new custom classification schemas to the operator (the schema mechanics themselves are specified by `spec-corpus.md`).

**Operating loop:**

1. **Assess.** Scan loaded corpora's `records/` and any active codex's `records/` for record statuses (`stub`, `draft`, `normalized`), unresolved issues, unresolved cross-references, and authoring opportunities. Check the corpus's `capture/` for completed captures awaiting reconciliation. Watch the codex layer for tag clusters that might warrant a new custom classification schema in the corpus, and watch the corpus side for URI-domain frequency or repeated extended-field demand that suggests the same.
2. **Prioritize.** Apply decision framework: high-priority new captures first, then normalization of existing stubs, then re-resolution sweeps, then re-normalization driven by tool/model upgrades or by newly authored custom classification schemas, then codex authoring that the new artifacts unblock.
3. **Propose.** Present the prioritized work plan to the operator for approval. Surface schema-authoring proposals when patterns warrant them.
4. **Execute.** Spawn capturer, normalizer, and author agents, managing parallelism by launching multiple agents concurrently.
5. **Report.** Summarize results — records captured, normalized, authored, issues encountered, schemas proposed.

### 5.6 Parallelism Model

- The **Curator** (or human operator) decides concurrency based on available resources and rate limits.
- Each agent processes one item. The Curator spawns N agents in parallel for N items.
- Agents do not communicate with each other. They read from and write to the corpus, and the Curator sequences work to avoid conflicts (e.g., not authoring a codex record whose evidentiary artifacts are still being captured).
- Typical session: spawn 5 capturers in parallel → wait for completion → spawn 5 normalizers for the new stubs → spawn an author for any codex records the new artifacts unblock.

### 5.7 Deterministic vs. LLM Boundary

| Operation | Type | Rationale |
|-----------|------|-----------|
| Capture (fetch, hash, store) | Deterministic | Reproducible, scriptable, no judgment needed |
| Reconciliation (dedup check, MIME detection) | Deterministic | Hash comparison + extension/magic-byte sniffing are mechanical |
| Hash computation (blake3, sha256, md5) | Deterministic | Mechanical integrity check |
| Conversion (HTML→MD, PDF→text, OCR, transcription) | Deterministic | Reproducible, tool-specific, no editorial judgment |
| Cross-reference resolution | Deterministic | Mechanical URL→blake3 lookup against the corpus index |
| Contextualization (refine, describe, surface issues) | LLM | Requires semantic understanding and editorial judgment |
| Custom classification schema match | Deterministic (when conditions are mechanical) / LLM (when conditions require interpretation) | Depends on the schema's match condition |
| Codex authoring (expert-agent synthesis) | LLM | Requires synthesis, structure, and editorial decisions |
| Functional URI evaluation (page extract, framegrab, crop) | Deterministic | Reproducible transformations of immutable inputs |
| Build (export, index) | Deterministic | Mechanical, reproducible |

The boundary is clear: **if the operation could produce different valid outputs depending on judgment, it's LLM-driven. If the output is deterministic given the input, it's scripted.** This enables independent re-processing — re-convert with better tools without re-contextualizing, and vice versa.

---

## 6. Deliverables and Cross-Codex Integration

Earlier revisions of this architecture defined a third layer — the *compendium* — a compiled reference work that integrated across multiple codices and corpora. That is no longer a separate layer. A codex owns its own deliverables, and "a tuned, integrated, published reference work" is simply **one kind of deliverable a codex can produce**. The architecture does not fix its format; the reference convention's approach to building such a deliverable lives in `impl-codex.md`.

**Cross-codex integration still happens — it is just not privileged into its own layer.** When a deliverable must draw across domains, that integration is itself a codex: it consumes the corpus through the shared contract (§2.3), and where it leans on another codex's already-synthesized output, it cites that output by `codex://{name}/{id}` (§3.7), the way it would cite any external reference. No codex reaches into another codex's internals; each is autonomous (§2.5). Different integrating codices over the same corpora and outputs may take different scopes and points of view — a personal one drawing additionally on a private corpus, a general one staying public-only — and that divergence is expected.

**Synthesis is agent practice, not architecture.** The principles a good integrating agent follows — cite the lowest source that suffices, cite records, represent disagreement, aggregate patterns, weight by the credibility-signal classifications the corpus carries (a corpus-layer derived view; see `spec-corpus.md`), respect unresolved `critical`/`major` issues, lean on already-synthesized codex outputs as the strongest input, and use tier-3 similarity to surface cross-modal connections — are guidance for a codex's expert agent, recorded in `impl-codex.md`, not contract fixed here.

---

## Appendix A: When to Author a Codex Record (Reference Convention)

Guidance for the reference codex convention — not architecture. A rule of thumb: when multiple artifacts share strong classification overlap (the same custom classification schemas applied across them) and would benefit from synthesized prose, author a codex record. Examples where authored records pay off:

- Multiple artifacts about the same album → an album record in a music-focused codex that synthesizes across the metadata page, the audio, and reviews.
- Many artifacts about products in a line → a product-line record that summarizes shared attributes and links to per-product records in the same codex.
- Recurring abstract categories (Review, Analysis, Explainer) → category records within a codex that cut across the codex's domain via cross-record wikilinks.

A codex never reaches into another codex; when a deliverable must span domains, that integration is itself a codex (§6).

Codex records are cheap to create and cheap to retire. Do not over-plan. Start with the syntheses that the corpus's actual usage makes valuable, and let the codex graph grow organically. The fuller authoring playbook lives in `impl-codex.md`.
