---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 11
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-05-31
---

# Athenaeum — Architecture Specification

## 1. Overview

### 1.1 What This Is

The Athenaeum is a knowledge normalization and synthesis system. It captures content from external sources, normalizes each captured file into a uniform markdown representation, supports authoring codex records that synthesize knowledge across many captured artifacts, and compiles cross-cutting reference works (compendiums) that draw across multiple authored bodies of work.

The system has three layers, each with a distinct purpose:

- **The corpus is the foundation.** It is the truth, the baseline — a content-addressed archive of captured artifacts, faithful to what was captured. The corpus is the unit of tenant isolation; a "private" corpus and a "public" corpus are separate corpora, and their content should be mutually exclusive.

- **The codex is where knowledge is decomposed and organized.** It is where connections are built across the corpus, where the signals emerge that drive the next capture, and where authored interpretation lives.

- **The compendium is the funnel.** It takes the codex's knowledge graph and focuses it on a topic, producing a concise, targeted reference work richly built up from the corpus's foundation.

### 1.2 Design Principles

1. **Layered foundation.** The corpus is the foundation, fully independent of the layers above it. Codices depend on corpora; compendiums depend on codices and corpora. References point downward only — a layer's records know nothing about layers above them. Codex regeneration triggers compendium re-build (compendium references into a codex are tied to that codex's current instance), and that is the intended behavior.

2. **Every record is independently valid.** A single captured page and a fully synthesized monograph are both complete, addressable, useful markdown documents.

3. **Artifact immutability via content addressing.** Captured artifacts are identified by the blake3 hash of their binary content. The bytes never change; if they did, the hash would change and the record would be a different record. Re-encountering the same bytes records another capture against the existing record rather than creating a new one (the corpus tracks that provenance; see `spec-corpus.md`).

4. **Normalization integrity.** An artifact's body is a faithful normalized rendering of its original content. Normalization may produce a more accurate representation (resolve encoding ambiguity, fix format-conversion artifacts, surface OCR text from images) but it MUST NOT add information that didn't exist in the original. Editorial work happens in codex records and compendium records, not in artifacts.

5. **The normalized body as universal representation.** Every artifact record carries a text body: a normalized rendering of the original file appropriate to its content type. This body projects all modalities into a common representational space — text — enabling universal computation across the corpus. Search, similarity, clustering, and embeddings all operate on this body. The body is the durable, auditable, git-versioned input; everything derived from it is ephemeral cache, rebuildable when models improve or normalization is refined.

6. **Compositional structure lives in the body.** Codex records and compendium records express composition through their prose — wikilinks, embeds, and tags. The link graph itself is the hierarchy. Equivalence is computed from intrinsic properties.

7. **Metadata-driven organization.** Classification, grouping, and discovery are tag and link operations, not filesystem operations. Reorganizing the corpus means editing references, never moving or renaming files.

8. **Stable identity.** Every record carries an `id`: an artifact's id is its blake3 hash (immutable with the bytes); a codex record's id is a UUIDv7 minted when the record is authored; a compendium record's id is the author-chosen slug. References are permanent within a layer; codex regeneration mints fresh UUIDs and dependent compendiums must be re-built.

9. **LLM-informed.** The data contract is shaped by what the pipeline's LLM agents can produce reliably (faithful normalization, semantic classification, synthesis). The spec describes the data; pipeline mechanics — including which steps are LLM-driven and which are deterministic — live in `impl-corpus.md` and `impl-codex.md`.

10. **Offline-first.** Only capture requires network access. Everything else operates on local data — including normalization (when the local model is sufficient), record authoring, similarity, and compendium synthesis.

### 1.3 Terminology

| Term | Definition |
|------|-----------|
| **Record** | The universal unit. A markdown file with YAML frontmatter and a normalized or authored body. One of three kinds: an artifact record (in a corpus), a codex record (in a codex), or a compendium record (in a compendium). |
| **Corpus** | A content-addressed archive of artifacts. Identified by name. The unit of tenant isolation — a "private" corpus and a "public" corpus are separate corpora and never merged. Contains artifact records, the binary store, and any base/custom classification schemas the corpus uses. |
| **Codex** | A named container holding authored codex records. Lives outside any corpus. References artifacts (across any loaded corpus) and other records within the same codex; never references another codex. Multiple codices may coexist; the runtime determines which are loaded. |
| **Compendium** | A compiled reference work that integrates across codices and corpora. Composed of compendium records (author-named markdown chapters). The cross-cutting integration layer — when synthesis spans codices, that synthesis happens here. Cites artifacts and codex records via footnote URIs (`[^N]: corpus://hash`, `[^N]: codex://name/uuid`); embeds artifact-derived views via functional URIs (`![[corpus://hash?params]]`). |
| **Artifact Record** | A record representing a single captured file. Identified by the blake3 hash of its binary content (`{blake3}.md`). One record per file, one content type per record. The body is a normalized text rendering of the artifact. The actual binary file is stored in content-addressed storage indexed by the same hash. Artifact records are the ground truth of the corpus. |
| **Codex Record** | A record representing authored knowledge, identified by a UUIDv7 (`{uuid}.md`), living within a codex. The body is a markdown composition that wikilinks to peer codex records in the same codex, footnote-cites artifacts (resolved to APA at build), and embeds artifact content via functional URIs. Codex records are where editorial work lives. |
| **Compendium Record** | A markdown chapter that composes a compendium, identified by an author-chosen slug (also the filename stem, e.g., `01-introduction.md`) under the compendium's `records/` directory. Compendium records are the integration-layer units where multi-codex / multi-corpus synthesis is written. |
| **`id`** | The unified identifier field present on every record. Its shape differs per layer: blake3 hash (64-char hex) for artifacts, UUIDv7 for codex records, author-chosen slug for compendium records. The `id` is also the filename stem under the container's `records/` directory. |
| **Content-Addressed Naming** | Artifact records are named by the blake3 hash of their binary content. Byte-identical files produce the same hash and therefore the same record — structural deduplication is automatic. Codex and compendium records use UUIDv7 and author-chosen slug respectively. |
| **Blake3** | The 256-bit content hash that identifies an artifact record and its underlying binary. 64-character lowercase hex string. Functions as identity, filename stem, and content-addressed storage key. |
| **UUID** | Universally unique identifier for a codex record. UUIDv7 (RFC 9562) — time-ordered, monotonic-by-creation. Stable and permanent within a codex instance; codex regeneration mints fresh UUIDs and invalidates dependent compendiums (which must be rebuilt). Not used on artifact records or compendium records. |
| **Reference** | A wikilink, footnote citation, or embed in a record's body that points to another record. References live in the body, not in frontmatter, and are visible in Obsidian's graph and backlink views. References point downward only — see §1.2 principle 1 and §2.4. |
| **Wikilink** | `[[id\|display]]` — an intra-layer cross-reference. The id is local to the container (blake3 in artifact bodies, UUIDv7 in codex-record bodies, slug in compendium-record bodies). Wikilinks never cross containers. The display text is optional. |
| **Footnote Citation** | `text[^N]` with `[^N]: <bare-uri>` at the bottom of the record. The cross-layer downward-citation form. Footnote URIs are `corpus://{hash}` (artifact) or `codex://{name}/{uuid}` (codex record); the build/export step resolves them into APA-style citations. |
| **Embed** | `![[target]]` — inline content inclusion. In artifact bodies: raw `![[blake3]]` for intra-corpus cross-refs that mirror the original content's embeds. In codex- and compendium-record bodies: functional URI `![[corpus://hash?params]]` (or no params for the identity transform); always targets an artifact. Codex records are not embedded — they are wikilinked. |
| **Tag** | A flat, kebab-case classification label matching `[a-z0-9]+(-[a-z0-9]+)*`. Tags are codex-local — they live on codex records only. Artifact records classify through a corpus-layer derived view (see `spec-corpus.md`); compendium records organize by chapter structure. |
| **Capture** | An encounter event recorded against an artifact. Re-encountering identical bytes records another capture on the existing artifact (the corpus tracks the provenance; see `spec-corpus.md`); the bytes themselves never move and never produce a new record. |
| **Normalization** | Producing the artifact's text body — extraction (HTML→markdown, PDF→text), transcription (audio/video→text), description (image→text), or metadata summary (opaque binary). Faithful to the original. |
| **Functional URI** | A composable URI scheme used in codex and compendium bodies. `corpus://{hash}` references an artifact (whole, by anchor `#section`, or by transformation `?page=4&crop=…`); `codex://{name}/{uuid}` references a codex record from a compendium footnote. Resolved at compile/render time. |
| **Schema** | A corpus-layer reference document describing how to normalize or classify content. The corpus model organizes schemas into five namespaces (`mime` / `origin` / `atom` / `composite` / `context`), with MIME-base as the required floor, composite as the optional corpus-author-driven classification layer, and context for annotations; see `spec-corpus.md`. |

---

## 2. Core Model

### 2.1 Records and Containers

A **record** is the universal unit of the Athenaeum. Every record is a single markdown file with YAML frontmatter and a body. Records are one of three kinds, each living in its own container:

- **Artifact records** — one per captured file, named by the blake3 hash of the binary content. Artifact records live in **a corpus**.

- **Codex records** — authored compositions, named by UUIDv7. Codex records live in **a codex**.

- **Compendium records** — authored chapters of a compiled reference work, with author-chosen filenames. Compendium records live in **a compendium**.

The system has three layers of container:

| Container | Holds | Identifier | Reference direction |
|-----------|-------|-----------|--------------------|
| **Corpus** | Artifact records, the binary cache, schemas, capture staging. | Corpus name. | None outbound (corpora reference nothing). |
| **Codex** | Codex records authored by a particular author or team. | Codex name. | Downward: footnote citations to artifacts (`[^N]: corpus://{hash}`), functional-URI embeds of artifacts (`![[corpus://{hash}?params]]`), wikilinks to peer codex records in the same codex (`[[uuid]]`). |
| **Compendium** | Compendium records — authored chapters of a published reference work drawn from one or more codices and corpora. | Compendium name. | Downward: footnote citations to artifacts and codex records (`[^N]: corpus://{hash}`, `[^N]: codex://{name}/{uuid}`), functional-URI embeds of artifacts, wikilinks to peer compendium records in the same compendium (`[[slug]]`). |

All three layers use a `records/` directory for tracked markdown records. The corpus additionally maintains an `artifacts/` cache for raw binary content; the cache is **untracked** (regenerable from blake3 plus capture provenance).

**Corpus directory layout (high level):**

```
corpus-{name}/
├── records/      — Artifact Records (tracked markdown, content-addressed by blake3)
├── artifacts/    — raw binary cache (UNTRACKED, .gitignore'd)
├── capture/      — staging for in-progress captures
└── schema/       — corpus schemas (specified by spec-corpus.md)
```

**Codex directory layout (high level):**

```
codex-{name}/
├── codex.yaml    — codex-level metadata (optional; see §2.5)
└── records/      — Codex Records (tracked markdown, UUID-named)
```

**Compendium directory layout (high level):**

```
compendium-{name}/
└── records/      — Compendium Records (tracked markdown, author-chosen filenames)
```

Compendium-record filenames are an authoring choice (e.g., `01-introduction.md`, `02-history.md`) — chapter-style names rather than the content-addressed hashes of artifact records or the UUIDs of codex records. See §6.

**Directory purposes:**

- **`records/`** (all three layers) — Tracked markdown records. Layout under `records/` (sharding, etc.) is an implementation concern; the spec only requires that a record be locatable by its identity (blake3 for artifacts, UUID for codex records, file path for compendium records).
- **`artifacts/` / `capture/` / `schema/`** (corpus only) — the corpus's untracked binary cache (regenerable from blake3 + capture provenance), capture staging, and schemas. These corpus internals are specified by **`spec-corpus.md`** (§2.2).

There is no nesting beyond the top-level separation in any container. Organization is expressed through tags, wikilinks, embeds, and computed similarity — not through directory hierarchy. Concrete on-disk paths and sharding conventions live in the implementation guides (`impl-corpus.md` for corpus side, `impl-codex.md` for codex and compendium sides).

### 2.2 The Corpus Layer

The corpus layer — the artifact-record format, frontmatter, normalized body, classification, provenance, schemas, deduplication, and the `corpus://` functional-URI scheme — is specified by **`spec-corpus.md`** (ATH-CORPUS), the authoritative contract for everything inside a corpus. This document specifies the architecture and the layers above (codex, compendium); it does not restate the corpus contract.

At architecture altitude: a **corpus** is a content-addressed archive of **artifact records**, each identified by the blake3 hash of its captured bytes (the record's `id`, also the `{blake3}.md` filename stem) and carrying a normalized text body — a faithful rendering of the original file into markdown that projects every modality into a common representational space, enabling universal computation (search, similarity, embeddings) across the corpus. Byte-identical captures deduplicate to a single record. Artifacts are immutable (the bytes define the identity), reference nothing in the layers above them, and are the ground truth the whole system rests on. Codices and compendiums reference artifacts downward via footnote citations and functional-URI embeds (§3.6, §3.7), both using the `corpus://` scheme that `spec-corpus.md` defines.

### 2.3 Codex Records

A codex record is an authored markdown composition representing synthesized knowledge. **Codex records live in a codex**, never inside the corpus. A codex record is identified by a UUIDv7 (`{uuid}.md`) and contains:

- **Frontmatter:** `id`, `title`, `description`, `status`, and `tags`. Codex-record frontmatter is deliberately thin — structural relationships live in the body.

- **Body:** Authored markdown prose with wikilinks to peer codex records in the same codex (`[[uuid|display]]`), footnote citations of artifacts (`text[^N]` with `[^N]: corpus://{hash}` resolved to APA at build time), and functional-URI embeds of artifacts (`![[corpus://{hash}?params]]`). The body *is* the composition — it is the authoritative record of what knowledge the codex record synthesizes and what evidence it draws on.

A codex record's references go downward to artifacts (footnote citation, functional-URI embed) and locally to other records within the same codex (wikilink). A codex's records do not reference other codices (see §1.2 principle 1); cross-codex integration happens at the compendium layer (§6).

**Codex records are where editorial work lives.** Unlike artifact bodies (which faithfully mirror their original content), codex-record bodies are written by curators or synthesis agents. Codex records may add interpretation, analysis, and context that no single artifact contains; structure knowledge for a particular audience or purpose; reconcile disagreements across artifacts; and carry the editorial voice that artifacts intentionally lack.

### 2.4 The Layered Reference Graph

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

Each arrow is a footnote citation, functional-URI embed, or wikilink appearing in the body of the referencing record. The "Album" codex record wikilinks its track records (peers in the same codex); each track record footnote-cites the artifacts it draws on (in the corpus). Reading the body reveals the structure; no separate metadata block restates it.

Across the three layers:

- **Artifact records (corpus)** — bodies may wikilink other artifacts in the same corpus when the original content's hyperlinks/embeds resolve to captured targets. Artifacts never reference codices or compendiums.
- **Codex records (codex)** — bodies wikilink to peer codex records in the same codex (`[[uuid]]`), footnote-cite artifacts (`[^N]: corpus://{hash}`), and embed artifact-derived views via functional URIs (`![[corpus://{hash}?params]]`). **A codex record never references another codex's records.** When that integration is needed, lift it to a compendium.
- **Compendium records (compendium)** — bodies wikilink to peer compendium records (`[[slug]]`), footnote-cite artifacts and codex records (`[^N]: corpus://{hash}` or `[^N]: codex://{name}/{uuid}`), and embed artifact-derived views via functional URIs.

**Properties:**

- **Composition is implicit.** Following wikilinks reconstructs the structure. There is no canonical "tree" — a record may have many parents and many children.
- **Acyclic by convention within a layer.** Cycles are technically possible (a record linking to another that links back) but conventionally avoided in compositional structures. Cross-references between peer records at the same layer are fine and frequently desirable.
- **Non-destructive.** Authoring a parent record does not modify or consume its referenced children. References are pointers; targets remain independent.
- **Multi-parent.** A single record may be referenced by many records at higher layers. An interview-transcript artifact might be cited by an artist-profile codex record in one codex, a documentary-film codex record in another codex, and a compendium record that synthesizes both.
- **Strictly downward.** References don't cycle across layers; a layer's records know nothing about layers above them.

### 2.5 Codices

A **codex** is a named container holding authored codex records. Codices live outside the corpus, structurally independent of any specific corpus. The runtime configuration (which codices are loaded, which corpora are loaded) is the join — content addressing handles the rest.

**Codex contents:**

- **`records/`** — codex records (UUID-named).
- **`codex.yaml`** (optional) — codex-level metadata: display name, description, an optional default tag vocabulary or tag-conventions reference. The spec does not mandate any particular fields here; this is a place for codex-author convention.

**Codex naming.** A codex is identified by name. The runtime maintains a mapping from codex name to on-disk location (or remote URI). When a compendium-record footnote contains `codex://{name}/{uuid}`, the runtime looks up `{name}` against the loaded codices.

**Reference rules.** A codex record's body may:

- **Wikilink** peer codex records in the same codex: `[[uuid|display]]`.
- **Footnote-cite** artifacts: `text[^N]` with `[^N]: corpus://{hash}` (with optional `#anchor` or `?params`).
- **Embed** artifact-derived views via functional URI: `![[corpus://{hash}?params]]` (or bare `![[corpus://{hash}]]` for the identity transform).

See §3.6 for the full per-primitive resolution algorithm.

A codex record never references another codex's records. Cross-codex integration happens at the compendium layer (§6).

**Codex regeneration.** A codex may be authored by hand, by an LLM agent, or by a regeneration pass that re-derives the codex from a corpus snapshot plus authoring prompts. Regeneration mints fresh UUIDs and produces new prose; the codex's name (the directory) is preserved, but its records are otherwise replaced. **Codex regeneration invalidates dependent compendiums** — any compendium that cites this codex via `codex://{name}/{uuid}` must be re-built against the regenerated codex. This is by design: a regenerated codex is conceptually a new instance, and the compendiums that draw on it are re-derived. Tooling assists by surfacing dependent compendiums when a regeneration is requested.

**Multiple codices, no declared joins.** A user may have many codices (personal, professional, project-specific). Each codex is structurally independent. Two people independently maintaining codices that happen to satisfy the same compendium's references is a feature — content addressing makes the join just work at runtime.

### 2.6 Re-normalization

Normalization and re-normalization of artifact bodies — when and how an artifact is (re)rendered — are corpus-layer mechanics specified by **`spec-corpus.md`** (its `stub → draft → normalized` lifecycle and re-run model). Normalization integrity holds throughout (§1.2 principle 4): a re-normalized body stays faithful to the original bytes, and editorial enrichment that draws on outside context lives in codex records, never in artifacts. Codex and compendium records are re-authored, not re-normalized.

### 2.7 Every Record Is a Valid Markdown Document

There is no "incomplete" state in terms of record validity. A freshly captured artifact whose body has been normalized is a complete, useful markdown document. An authored codex record whose body cites a single artifact is a complete, useful markdown document. The corpus is always in a valid state; any record can be selected for compendium synthesis at any time. Authoring richer codex records on top of existing artifacts and other records is enrichment, not a completion requirement.

---

## 3. Record Format

### 3.1 Frontmatter Schema

All record metadata lives in YAML frontmatter at the top of each `.md` file. There are no separate configuration files — the markdown file is the single source of truth for both metadata and content.

Artifact frontmatter — and the schema library that drives it — is a corpus-layer concern specified by `spec-corpus.md` (§2.2, §3.3). The fields below are the cross-layer core plus the codex- and compendium-record specifics.

#### 3.1.1 Core Fields

Every record carries an `id`, a `description`, and a `status`. Codex and compendium records additionally carry a frontmatter `title`; codex records carry `tags`. **Artifact-record frontmatter is specified separately by `spec-corpus.md`** (§3.1.2) — in the corpus model an artifact's title, media type, and most metadata live in its body blocks, not frontmatter.

| Field | Type | Required | Applies to | Description |
|-------|------|----------|------------|-------------|
| `id` | string | yes | all | Record identifier and filename stem under the container's `records/` directory. **Artifact:** the blake3 hash of the binary content, 64-character lowercase hex. **Codex record:** UUIDv7 (RFC 9562, time-ordered, monotonic-by-creation). **Compendium record:** author-chosen slug matching `[a-z0-9]+(-[a-z0-9]+)*`. |
| `title` | string | yes (codex, compendium) | codex + compendium records | Short descriptive label. An artifact's title lives in its corpus body block, not frontmatter (see `spec-corpus.md`). |
| `description` | string | yes | all | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `status` | enum | yes | all | Lifecycle state: `stub` (captured, no body), `draft` (body filled), `normalized` (refined, ready for use). Codex and compendium records typically begin at `draft` since authoring fills the body directly. |
| `tags` | string[] | no | codex records only | Classification tags. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Declare what this codex record is about. Tags are codex-local — a codex MAY define a tag vocabulary in its `codex.yaml` or a conventions file for consistency. Frontmatter tags declare whole-record topical coverage; inline `%% #tag %%` annotations (§3.2.5) provide positional precision within the body. |

Artifact classification is a corpus-layer concern — derived from the artifact's body blocks, specified by `spec-corpus.md`, not declared in frontmatter here. Compendium-record organization is the author's chapter structure. (`visibility`, the editorial curation layer for retiring low-quality artifacts without deleting them, is an artifact frontmatter field in the corpus model — see `spec-corpus.md`.)

**Record type signaling.** A record's type is determined by independent signals that always agree: its **container** (a corpus's, codex's, or compendium's `records/`) and its **`id` shape** (64-character lowercase hex blake3 for artifacts, UUIDv7 for codex records, author-chosen slug for compendium records).

#### 3.1.2 Artifact Frontmatter

Artifact-record frontmatter is specified by **`spec-corpus.md`**, not here. In the corpus model it is bytes-identity only (`id`, `description`, `status`, byte-hash fields, the `touch[]` provenance chain, `visibility`); everything else an artifact carries — its media type, origins/URIs, capture timestamps, classifications, and schema-extracted fields — lives in the record's **body blocks**, not frontmatter, and is exposed through on-demand derived views. The codex and compendium layers never read artifact frontmatter directly; they reference artifacts through the `corpus://` scheme (§3.6, §3.7).

#### 3.1.3 Codex-Record-Specific Fields

Present only on codex records.

Codex-record frontmatter is deliberately thin. The complete set of frontmatter fields on a codex record is the core fields `id`, `title`, `description`, `status`, `tags` — and that is it. No `content_type` (codex records are markdown by construction), no `visibility`, no quality or pipeline metadata. Structural relationships are body references — wikilinks to peer codex records, footnote citations of artifacts, functional-URI embeds — and computed similarity (see §3.5). The body is the authoritative record of what knowledge the codex record synthesizes and what evidence it draws on.

Credibility, when relevant, is consulted by reading the credibility-signal classifications on the evidentiary artifacts the codex record cites — a corpus-layer derived view (see `spec-corpus.md`). The codex record itself carries no credibility field.

Compendium records carry the same minimal core fields as codex records (excluding `tags`); they organize by chapter structure rather than tag classification.

#### 3.1.4 Issues

Quality and completeness problems on artifacts (missing media, broken links, partial capture, content modified since publication, encoding corruption, format loss) are a corpus-layer concern — recorded as `context` blocks in the `issue` namespace and surfaced through the corpus's derived `issues` view, specified by **`spec-corpus.md`**. They are not record frontmatter in this spec.

#### 3.1.5 Extended Fields

Format-intrinsic and classification-derived fields (a web article's `byline` / `published_date`, an audio file's `artist` / `album`, a PDF's `page_count`) are a corpus-layer concern. In the corpus model they live in the artifact's body blocks and schema-declared namespaces and surface through derived views, specified by **`spec-corpus.md`** — not as record frontmatter here.

### 3.2 Body Format

The body of a record is the markdown content below the frontmatter closing `---`. **Artifact bodies** are a corpus-layer concern — their structure (the normalized rendering and the metadata / content / annotation block grammar) is specified by **`spec-corpus.md`**. This section covers **codex-record and compendium-record bodies**; compendium-record bodies follow the codex-record conventions with the added freedom of cross-codex / cross-corpus citation forms (see §6).

#### 3.2.1 Artifact Body Integrity

An artifact's body is a faithful normalized rendering of its original content — it adds no editorial content, interpretation, or connection that wasn't in the original (§1.2 principle 4). The block-structured body grammar and the normalization rules are specified by **`spec-corpus.md`**.

#### 3.2.2 Cross-Reference Resolution

Resolving an artifact's original hyperlinks and embedded resources to intra-corpus references (raw `[[blake3]]` wikilinks / `![[blake3]]` embeds) is a corpus-layer concern, specified by **`spec-corpus.md`**. Codex and compendium bodies do not use raw blake3 references; they reference artifacts via the `corpus://` scheme (§3.6, §3.7).

#### 3.2.3 What Embeds Mean

In codex- and compendium-record bodies, embeds are functional URIs targeting an artifact: `![[corpus://{hash}?params]]`. The `params` may transform the artifact (page extract, framegrab, crop); a bare `![[corpus://{hash}]]` is the identity transform. Codex records are not embedded — they are wikilinked or footnote-cited. (Within an artifact body, a raw `![[blake3]]` embed means something narrower — an intra-corpus mirror of the original content; that is a corpus-layer concern, see `spec-corpus.md`.)

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

Inline annotations are valid only in codex-record bodies. Artifact bodies remain faithful to the original content (§3.2.1); their classification is a corpus-layer derived view (see `spec-corpus.md`). Compendium-record bodies organize by chapter structure.

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

Compendium records organize by chapter structure and synthesis-system-prompt-driven taxonomy.

#### 3.5.2 The Codex Graph

The codex graph handles structural organization. A "Brake System Overview" codex record that links to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" records expresses compositional structure through its body. The link graph is the hierarchy.

A codex record that represents a concept (a category, a person, a place, a thing) is just a regular codex record with descriptive prose; other records reference it by wikilink. The role is emergent from the graph.

#### 3.5.3 Deduplication and Similarity

Deduplication and similarity over artifacts — exact (blake3), perceptual (per-format hashes), and semantic (embeddings of the normalized body) — are computed from intrinsic artifact properties and are a corpus-layer concern, specified by **`spec-corpus.md`**. The codex and compendium layers consume the results (e.g., finding related artifacts to cite) but do not define them.

### 3.6 Reference Resolution

Three reference primitives express the layered graph. Each has a single resolution rule.

**Wikilinks `[[id]]` — intra-layer only.**

- Artifact body: `[[blake3]]` → an artifact in the same corpus (intra-corpus; a corpus-layer concern, see `spec-corpus.md`). Same-bytes blake3 collision across loaded corpora is harmless — the bytes are by definition identical; either copy resolves correctly.
- Codex-record body: `[[uuid]]` → another codex record in the same codex (UUIDv7).
- Compendium-record body: `[[slug]]` → another compendium record in the same compendium.

Wikilinks never cross containers. A codex record never wikilinks an artifact, another codex's record, or a compendium record; a compendium record never wikilinks an artifact or a codex record.

**Footnote citations `text[^N]` with `[^N]: <uri>` — cross-layer downward citation.**

- Codex body → artifact: `[^N]: corpus://{hash}` (with optional `#anchor` or `?params`).
- Compendium body → artifact: `[^N]: corpus://{hash}` (or `corpus://{name}/{hash}` for provenance disambiguation).
- Compendium body → codex record: `[^N]: codex://{name}/{uuid}` (with optional `#anchor`).

The footnote body carries a bare URI; the build/export step resolves it into a proper APA-style citation, generating author / publication-date / title / source from the target's metadata — for an artifact, from its corpus body blocks and derived views (`spec-corpus.md`); for a codex record, from its frontmatter. The footnote label is author-chosen (numeric or short slug) and is preserved through resolution.

**Embeds `![[…]]` — cross-layer functional inclusion (or intra-corpus raw cross-ref).**

- Artifact body: `![[blake3]]` → intra-corpus raw embed (a corpus-layer concern, §3.2.2, `spec-corpus.md`). Mirrors the original content's embeds; no scheme prefix, no transformation.
- Codex- and compendium-record body: `![[corpus://{hash}?params]]` → functional URI embed of an artifact. A bare `![[corpus://{hash}]]` is the identity transform.

Codex records are never embedded — when one codex record needs to draw on another, wikilink it; when a compendium needs to integrate a codex record, footnote-cite it.

**Unresolved references.** A reference that cannot be resolved is surfaced as broken (Obsidian-style raw browsing) or flagged in compiled outputs with a clearly-marked fallback rather than silently dropped. Tooling backlink panels list unresolved references as authoring follow-ups.

**Cross-corpus same-bytes.** When multiple corpora are loaded, the same blake3 may appear in more than one. This is harmless — the bytes are identical, and a bare reference resolves to either copy. Compendium footnotes use the qualified `corpus://{name}/{hash}` form when provenance assertion matters.

### 3.7 Functional URI Scheme

Functional URIs are a codex- and compendium-record primitive. They appear in footnote citations (resolved to APA at build time) and in embeds (resolved to inline content). Two schemes:

- **`corpus://`** — references an artifact by content hash. Used in footnote citations and embeds. **Its grammar, transformation parameters (`page`, `crop`/`bbox`, `resize`, `framegrab`/`time_range`, `grayscale`, …), resolver contract, and caching are defined by `spec-corpus.md` (§6);** the upper layers use the scheme as-is.
- **`codex://`** — references a codex record by codex name and UUIDv7. Used only in compendium-record footnotes. Defined here, since codex records are this spec's concern.

**`corpus://` (summary).** Base form `corpus://{hash}` resolves to an artifact in any loaded corpus that has the hash; `corpus://{name}/{hash}` asserts which corpus (provenance, for when two loaded corpora share a hash); `corpus://{hash}#anchor` navigates to a named region; query parameters compose left-to-right into a derived view (e.g. `corpus://{hash}?page=4&crop=50,100,550,400`). The authoritative form and parameter set live in `spec-corpus.md` §6.

**`codex://` codex-record URIs.**

- **Base form:** `codex://{name}/{uuid}` — resolves to the codex record with the given UUIDv7 in the codex named `{name}`.
- **Fragment navigation:** `codex://{name}/{uuid}#anchor` — navigates to a named section of the codex record's body.
- **No transformation parameters.** Codex records are not embedded, cropped, or page-extracted; the URI exists for citation, not for derived views.

**Semantics.** Functional URIs are **deterministic** (the underlying artifact is immutable by content addressing; a codex record's UUID is stable within its codex instance), **cacheable** (the cache key is the full URI string), and **ephemeral** (they exist at compile/render time, not as stored records). In raw Obsidian browsing, an unresolved URI falls back to its alt text or footnote label. In compiled outputs (mdbook, static site), the build resolves every functional URI — computing artifact transformations for embeds, and generating APA-style citations from footnote URIs (drawing author / date / title from the target's metadata: an artifact's via its corpus body blocks and derived views, a codex record's via its frontmatter).

---

## 4. Pipeline

The path from raw content to a richly authored corpus has discrete steps; each is independently re-runnable.

- **Capture** brings content into the corpus. Identity is the hash of the bytes; failed captures consume no identity space. Capture is the only step requiring network access. Every captured file becomes its own artifact record; bundles of related files (a page plus its embedded images, a video plus its description page) become multiple artifact records, related through cross-references in their normalized bodies.

- **Normalize** transforms an artifact stub into a complete record — producing the faithful normalized body, applying classification, and resolving intra-corpus cross-references. The corpus-layer mechanics (the `stub → draft → normalized` lifecycle, the schema namespaces, and where classification and extracted fields live in the record) are specified by `spec-corpus.md`. Bodies are faithful — normalization may improve accuracy but never adds information not present in the original.

- **Author** creates or edits a codex record (in a codex) or a compendium record (in a compendium) that synthesizes knowledge across artifacts and other records. The author writes nothing outside the target container. Authoring is non-destructive: referenced artifacts and other records are unchanged and independently addressable.

- **Re-normalize** is on-demand re-running of normalization when context, schemas, or models improve, or when newly captured artifacts resolve previously unresolved cross-references. Integrity is preserved — the new body remains a faithful rendering of the original artifact.

- **Build** materialises one or more layers for viewing. Each layer is independently exportable:

  - **Corpus build** — a browsable artifact vault. Resolves intra-corpus wikilinks among artifacts; serves binaries via the corpus's `artifacts/` cache.
  - **Codex build** — a browsable knowledge work (mdbook, static site, vault). Resolves intra-codex wikilinks (codex-record↔codex-record) and downward references (footnote URIs to artifacts, functional-URI embeds). The codex's referenced corpora must be loaded.
  - **Compendium build** — the published reference work. Resolves all references across the integration set (intra-compendium wikilinks; footnote URIs to codex records and artifacts, resolved into APA-style citations; functional-URI embeds). The compendium's referenced codices and corpora must be loaded.

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

The pipeline is operated by specialized agents — lightweight, single-purpose workers that each handle one item per invocation. Agents have focused responsibilities, process exactly one item, and report results to a coordinator. There is no inter-agent communication and no shared state beyond the corpus filesystem.

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

Creates or edits codex records in a codex (or compendium records in a compendium).

**Model class:** Sonnet-tier (semantic judgment required for synthesis).

**Scope:** One record per invocation, in one container.

**Output contract:** When the author finishes successfully, a record exists in the target container with the layer-appropriate `id` (UUIDv7 in a codex; author-chosen slug in a compendium), title, description, status, and (codex only) tags. The body is authored markdown prose: footnote-cites artifacts (`[^N]: corpus://{hash}` resolved to APA at build); embeds artifact-derived views via functional URIs (`![[corpus://{hash}?params]]`); wikilinks peer records in the same container (`[[uuid]]` for codex, `[[slug]]` for compendium); applies tags in frontmatter (codex only). A compendium-record body may additionally footnote-cite codex records (`[^N]: codex://{name}/{uuid}`). Backlinks and related-record candidates within the container are surfaced for follow-up. The author writes nothing outside the target container.

### 5.5 Curator

Autonomous orchestration skill that assesses corpus state, prioritizes work, and dispatches agents. Also responsible for the schema-feedback loop (§3.3) — monitoring the codex layer for emerging patterns and proposing new custom classification schemas to the operator (the schema mechanics themselves are specified by `spec-corpus.md`).

**Operating loop:**

1. **Assess.** Scan loaded corpora's `records/` and any active codex's `records/` for record statuses (`stub`, `draft`, `normalized`), unresolved issues, unresolved cross-references, and authoring opportunities. Check the corpus's `capture/` for completed captures awaiting reconciliation. Watch the codex layer for tag clusters that might warrant a new custom classification schema in the corpus, and watch the corpus side for URI-domain frequency or repeated extended-field demand that suggests the same.
2. **Prioritize.** Apply decision framework: compendium blockers first, then high-priority new captures, then normalization of existing stubs, then re-resolution sweeps, then re-normalization driven by tool/model upgrades or by newly authored custom classification schemas.
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
| Codex- or compendium-record authoring | LLM | Requires synthesis, structure, and editorial decisions |
| Functional URI evaluation (page extract, framegrab, crop) | Deterministic | Reproducible transformations of immutable inputs |
| Build (export, index) | Deterministic | Mechanical, reproducible |

The boundary is clear: **if the operation could produce different valid outputs depending on judgment, it's LLM-driven. If the output is deterministic given the input, it's scripted.** This enables independent re-processing — re-convert with better tools without re-contextualizing, and vice versa.

---

## 6. Compendium Layer

### 6.1 What a Compendium Is

A **compendium** is the cross-cutting integration layer of the system — a compiled, published reference work compiled from one or more codices and one or more corpora.

Where corpora preserve captured content faithfully and codices author synthesis on top of corpora, compendiums sit above codices and corpora and apply a further editorial layer: scope, point of view, and a domain taxonomy. **A compendium is the only place where multi-codex / multi-corpus integration happens.** Codices do not reference each other (§2.5); when synthesis must span codices, that synthesis is a compendium.

A compendium is opinionated. Multiple compendiums can draw from the same codices and corpora and produce different works — a personal compendium and a general compendium on the same subject might draw on overlapping content, but the personal one pulls additionally from the user's private corpus while the general one stays public-only.

### 6.2 How Compendiums Use Records

Compendiums select codex records and artifacts from one or more codices and corpora and synthesize them into chapters organized by a domain taxonomy:

1. **Select inputs.** Using tags, codex-record titles, descriptions, and tier-3 body-embedding similarity, identify the codices, codex records, and artifacts relevant to the compendium's domain. Codex records are preferred when they exist (someone has already done the synthesis); raw artifacts are cited directly when the compendium needs primary-source precision.
2. **Organize by taxonomy.** Group selected inputs by the compendium's chapter structure.
3. **Synthesize chapters.** Distill grouped inputs into coherent prose, reconciling conflicts, identifying patterns, and citing the appropriate identifier per §6.3. Functional URIs may be used to cite specific pages, frames, or crops of artifacts.
4. **Build navigation.** Generate cross-references and supplementary sections (FAQ, glossary, quick reference).

**Compendium body references.** Inside a compendium body, three reference primitives apply:

- **Wikilinks** `[[slug]]` — intra-compendium peer-chapter references.
- **Footnote citations** `text[^N]` with the URI in the footnote body:
  - `[^N]: corpus://{hash}` (or `corpus://{name}/{hash}` for provenance disambiguation) — citing an artifact.
  - `[^N]: codex://{name}/{uuid}` — citing a codex record. Bound to the codex's current instance; codex regeneration mints fresh UUIDs and dependent compendiums must be re-built (§2.5).
- **Embeds** `![[corpus://{hash}?params]]` — functional URI for a derived view of artifact content. Codex records are not embedded; cite them via footnote.

**Anonymized examples.**
- A user's personal compendium for a specific subject draws from their *private* corpus (personal records, history) AND *public* corpora (manuals, advisories) for context. It cites codex records from the user's personal codex and artifacts from both corpora.
- A general compendium for the same subject category draws only from *public* corpora and from any general-purpose codex that synthesizes the public material. The personal corpus is not in scope.

### 6.3 Synthesis Principles

- **Cite the lowest source that suffices.** When an artifact directly says it, footnote-cite the artifact (`[^N]: corpus://{hash}`); when interpretation that no single artifact provides is needed, footnote-cite the codex record that already did that synthesis (`[^N]: codex://{name}/{uuid}`). Artifacts are stable across all regeneration; codex-record references are stable only as long as the cited codex isn't regenerated, in which case the compendium must be re-built (§2.5, §6.5).
- **Cite records.** Every factual claim references the identifier(s) it derives from. Use functional URI fragments and parameters (`corpus://{hash}#section`, `corpus://{hash}?page=4`) when citing specific pages, frames, or crops where precision matters.
- **Represent disagreement.** When sources conflict, the compendium presents both positions with whatever credibility-signal classifications they carry (a corpus-layer derived view; see `spec-corpus.md`). Where the corpus expresses no credibility signals, surface the disagreement neutrally and let the reader judge.
- **Aggregate patterns.** If many artifacts describe the same phenomenon, the compendium captures the pattern (common conditions, symptoms, root cause) rather than citing each artifact individually.
- **Weight by credibility signals.** Records carrying classifications the compendium treats as authoritative (e.g., `peer-reviewed`, `community-validated`) carry more weight in synthesis than records carrying classifications it treats as weaker (e.g., `preprint`, `anecdotal-claim`, `corporate-bias`). The specific weighting is a compendium-author choice — different compendiums on the same domain may weight the same signals differently. The synthesis system prompt (§6.4) is the natural place to encode the compendium's weighting policy.
- **Respect issues.** Records with unresolved `critical` or `major` issues should be weighted accordingly and gaps noted.
- **Leverage codex records and tags.** Codex records are the strongest input — a well-authored codex record already encodes synthesis a compendium chapter wants. Compendium chapters typically start by selecting a small set of seed records from one or more codices and following their references outward into the underlying corpora.
- **Leverage similarity.** Tier-3 body embeddings surface cross-modal connections (an audio transcript and an HTML article on the same topic) that tags alone may miss.

### 6.4 System Prompts

Each compendium has a **synthesis system prompt** — a document encoding domain-specific knowledge: scope boundaries, key relationships, codex/corpus selection criteria, and synthesis guidelines.

System prompts are iterable. When synthesis produces gaps or errors, the system prompt is refined and synthesis is re-run: **synthesize → review → refine prompt → re-synthesize**.

### 6.5 Incremental Re-synthesis

Compendiums track which inputs were used to produce each chapter — codex records by `codex://{name}/{uuid}`, artifacts by `corpus://{hash}`, with the relevant timestamps. When an artifact is re-normalized or a codex record is re-authored, only affected chapters need re-synthesis.

**Codex regeneration invalidates dependent compendiums.** A regenerated codex mints fresh UUIDs (§2.5); compendium footnote references of the form `codex://{name}/{uuid}` are tied to a specific codex instance, so once that codex is regenerated, every dependent compendium must be re-built against the new instance. Tooling SHOULD surface dependent compendiums when a codex regeneration is requested so the operator can plan the cascade.

A record updated in place (re-authored, re-normalized) triggers re-synthesis only in chapters that cite it. This keeps incremental re-synthesis proportional to actual content change. Codex regeneration, by contrast, is a wholesale event that re-runs every chapter that drew on the regenerated codex.

---

## Appendix A: When to Author a Codex Record

A rule of thumb: when multiple artifacts share strong classification overlap (the same custom classification schemas applied across them) and would benefit from synthesized prose, author a codex record. Examples where authored records pay off:

- Multiple artifacts about the same album → an album record in a music-focused codex that synthesizes across the metadata page, the audio, and reviews.
- Many artifacts about products in a line → a product-line record that summarizes shared attributes and links to per-product records in the same codex.
- Recurring abstract categories (Review, Analysis, Explainer) → category records within a codex that cut across the codex's domain via cross-record wikilinks.

Cross-codex synthesis is not a codex's job — when multiple codices need to come together, that's a compendium (§6).

Codex records are cheap to create and cheap to retire. Do not over-plan. Start with the syntheses that the corpus's actual usage makes valuable, and let the codex graph grow organically.
