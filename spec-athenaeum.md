---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 10.8
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-04-26
changelog:
  - version: 10.8
    date: 2026-04-26
    summary: >
      Refinement pass H. Storage layout made parallel across the three layers,
      with one shared name for tracked markdown (`records/`) and a clear
      tracked-vs-untracked split. Corpus directories renamed: the previous
      `artifacts/` (markdown records) becomes `records/` (tracked); the previous
      `binary/` (raw bytes) becomes `artifacts/` (untracked cache, listed in
      .gitignore, regenerable from blake3 plus capture provenance — implementation
      may store the bytes anywhere as long as a blake3 lookup produces them).
      Codex `documents/` becomes `records/`. Compendium directory layout spec'd
      for the first time: `compendium-{name}/records/` holds Compendium Records
      with author-chosen filenames (e.g., `01-introduction.md`); no sharding,
      no UUIDs. §2.1 layout diagrams rewritten for all three layers; §2.1
      directory-purpose prose rewritten with explicit tracked/untracked
      annotations; §2.2 binary-storage paragraph updated to point at the
      `artifacts/` cache. impl-corpus.md §2.7 rewritten with `.gitignore`
      callout and explicit "implementation may store the bytes anywhere"
      language. impl-codex.md §2 retitled and rewritten; new §2A defines the
      compendium directory layout. Pure layout rename — the data contract
      (records locatable by identity) is unchanged.
  - version: 10.7
    date: 2026-04-26
    summary: >
      Refinement pass G. Layer-record naming made parallel across the three
      layers. "Documents" (in codices) renamed to "Codex Records"; new term
      "Compendium Records" coined for the author-named markdown chapters that
      compose a compendium. Terminology table (§1.3) updated: Document Record
      entry renamed Codex Record, new Compendium Record entry added, supporting
      definitions (Record, Corpus, Codex, Compendium, Content-Addressed Naming,
      UUID, Reference, Wikilink, Tag) updated to match. §2.1 now describes
      three record kinds (artifact / codex record / compendium record) instead
      of two; §2.3 retitled "Codex Records"; §2.7 retitled "Every Record Is a
      Valid Markdown Document"; §3.1.3 retitled "Codex-Record-Specific Fields";
      §3.2.5 / §3.2.6 / §3.2.7 retitled with "Codex Record(s)" in place of
      "Document(s)"; §3.5.2 retitled "The Codex Graph"; §A.3 retitled "When to
      author a codex record." §3.4 example heading "Document Record" → "Codex
      Record." Agent contracts in §4.3 / §5.4 frame the Author as writing codex
      or compendium records. impl-corpus.md scope wording updated; impl-codex.md
      scope, §2 directory layout prose, §4.1 / §4.2 authoring steps, §5.2
      resolution rules, §5.4 collision rules, §6 regen prose, §8 open question
      all shifted from "document" to "codex record" / "compendium record"
      where the layer concept is meant. Pure rename — no semantic changes; the
      three-layer design is unchanged.
  - version: 10.6
    date: 2026-04-26
    summary: >
      Refinement pass F. Two cleanups. (1) `record_type` field removed entirely.
      The field was redundant: container, filename pattern (64-char blake3 hex vs.
      UUID v4), and required field presence (`blake3` vs. `uuid`) all
      independently signal record type. §3.1.1 Core Fields row dropped, prose
      mentions in §2.1 / §2.2 / §2.3 / §3.1.2 / §3.1.3 / §3.4 examples /
      §4.1.2 / §4.3 / §5.4 scrubbed. New one-liner in §3.1.1 explicitly
      documents the three signals that determine record type. impl-corpus.md
      §2.4 in-memory build bullet removed. (2) Functional URI scheme (§3.7)
      simplified to single-form: `blake3://hash?params` regardless of
      container. The previously-allowed `corpus-name:blake3://hash`
      compendium-only form removed — it duplicated provenance assertion that
      already lives on the wikilink-citation form `[[corpus-name:blake3]]`.
      Functional URIs are about content transformation; provenance is a
      citation concern, handled separately.
  - version: 10.5
    date: 2026-04-26
    summary: >
      Refinement pass E. Credibility removed from §3.1.4 core Quality Fields
      entirely (artifacts and documents both); the closed 5-tier enum dropped.
      Credibility is now expressed as multiple small custom classification
      schemas — `peer-reviewed`, `preprint`, `corporate-bias`, `community-validated`,
      `anecdotal-claim` shown as Appendix A.2 examples, but corpora invent their
      own vocabularies. New top-level `classifications:` array on artifact
      records provides a per-application audit trail: each entry is
      `{schema, justification}`, with universal required justification across
      all applied classifications (mechanical for deterministic matches,
      substantive prose for LLM judgments). Schema-declared fields and tags
      continue to merge into top-level frontmatter per the v10.3 composition
      rule; the array does not duplicate values. §6.3 compendium synthesis
      principles reworked to weight by whatever credibility-signal classifications
      the corpus carries rather than a fixed enum. Documents lose
      `credibility_tier` outright with no replacement — codices and compendiums
      consult artifact-level credibility signals when weighting matters.
      Normalizer language (§4.2.3, §5.3, §5.7) and impl docs updated to drop
      "assess credibility_tier" from the contextualization step (subsumed by
      "apply matching custom classification schemas").
  - version: 10.4
    date: 2026-04-26
    summary: >
      Refinement pass D. Three-layer hierarchy made explicit: corpus (artifacts) →
      codex (authored documents) → compendium (cross-cutting integration). Documents
      leave the corpus and live in named codices. Codices are pure: a codex body
      references downward only — to artifacts in any loaded corpus and to other
      documents within the same codex — and never to other codices. Cross-codex
      and cross-corpus integration happens at the compendium layer, where the
      qualified wikilink syntaxes `[[codex-name:slug]]` and `[[corpus-name:blake3]]`
      are valid. Reference stability hierarchy codified: prefer artifact (always
      stable) > codex topic by slug (survives codex regeneration) > UUID (instance-
      bound, may orphan). Codex regeneration framed as a contemplated workflow that
      motivates slug-as-stable-topic. Slug uniqueness is now codex-scoped for
      documents and corpus-scoped for artifacts. New §2.5 Codices, §2.4 reframed as
      "The Layered Reference Graph," §3.6 wikilink resolution rules per container,
      §6 compendium expanded with cross-codex/cross-corpus mechanics and
      regeneration safety, §4.3/§5.4 author writes-to-codex framing. Companion
      `impl-codex.md` created.
  - version: 10.3
    date: 2026-04-26
    summary: >
      Refinement pass C. Classification reframed as a clear hierarchy: MIME-based
      base schemas are foundational and required (the data-contract floor every
      conforming corpus carries), and custom classification schemas are an optional
      corpus-author-driven layer on top. §3.3.2 renamed "Custom Classification
      Schemas"; match conditions spelled out concretely (`content_type`,
      `uri_pattern`, `has_tags`, `field_match`). New §3.3.3 articulates the
      schema-feedback loop — custom classification schemas emerge from observed
      patterns in document authoring, get authored by the curator, and apply
      retroactively via re-normalization. Curator (§5.5) gains explicit
      schema-monitoring responsibility. Examples in §3.3 anonymized.
  - version: 10.2
    date: 2026-04-26
    summary: >
      Refinement pass B. Artifact record stripped to bare-fact provenance:
      `origin_uri` + structured `captures[]` (with date/method/origin_uri sub-objects)
      replaced by two flat arrays — `uris: string[]` (cumulative, none canonical;
      append-friendly so DOIs/mirrors added later become valid retroactively for all
      captures) and `capture_dates: ISO-8601[]` (encounter timestamps). No per-event
      `method` or URI association; recovery of a specific (uri, date) capture package
      is not the artifact record's job. v9-leftover `original_filename` and singular
      `capture_date` dropped (local-file captures use `file://` URIs in `uris[]`).
  - version: 10.1
    date: 2026-04-26
    summary: >
      Refinement pass A. Spec de-prescribed: §4 (Pipeline) and §5 (Agents) trimmed
      from process recipes to data-shape contracts; concrete sharding and on-disk
      paths moved to the new companion implementation guides `impl-corpus.md` and
      `impl-codex.md`. Base schemas (§3.3.1) gain explicit `hashes:` declarations —
      which cryptographic and perceptual hashes ship with each MIME's artifacts is
      now part of the data contract, not implementation detail. ARCHITECTURE.md
      renamed to spec-athenaeum.md to clarify its role as the spec, distinct from
      the impl docs. Examples in §3.4 anonymized — no real-world brand, forum,
      vehicle, or platform names.
  - version: 10.0
    date: 2026-04-24
    summary: >
      Fundamental architecture revision. Source records replaced by content-addressed
      artifact records — each captured file is its own record named by blake3 hash.
      One artifact per record, one content_type, one normalization path. Byte-identical
      dedup is structural. Artifact bodies faithfully mirror original content with
      cross-references resolved to blake3 wikilinks and embeds where targets exist
      in the corpus. All stored relations eliminated (is_a, part_of, same_as,
      constituents) — replaced by Obsidian primitives (wikilinks, embeds, tags) and
      computed similarity (blake3 exact, perceptual hashes, body embeddings). Two
      sharply separated layers: artifact layer (faithful representation, no
      editorialization) and document layer (authored knowledge, editorial freedom,
      functional URIs for computed transformations). Normalized body established as
      universal cross-modal representation enabling computed similarity without stored
      edges. Schema library restructured: universal MIME-type base schemas plus
      corpus-local classification schemas. Tags as sole classification mechanism —
      flat, portable, corpus-local. Functional URI scheme for deterministic
      transformations of artifact content at document compile time. Entity/set concept
      distinction eliminated. Slug mechanism for human-readable addressability.
  - version: 9.0
    date: 2026-04-20
    summary: "content_type redefined as IANA MIME type. Schema library pivots from per-concept classification to per-MIME normalization guidelines; schemas self-declare applicable MIME types via their own frontmatter. Closed content-type enum removed — classification happens by forward reference to ordinary concept documents, with an informal distinction between set documents (valid part_of targets) and entity documents (linked via body prose). Relations reduced to two flat frontmatter fields (part_of, same_as); Relation struct with per-entry type dropped along with sequel_to/reply_to/references/adaptation_of/supersedes/superseded_by/contradicts. ArtifactRef gains mimetype (required) and primary (optional boolean, one-per-source). New visibility field (visible/deranked/hidden) separates editorial curation from pipeline status. Body tags (Obsidian-style #tag markers) forward-declared as the mechanism for topical aboutness. Contextualization specifies progressive disclosure of ancestor concept documents: eagerly loaded descriptions, lazy-fetched bodies via tool calls, to scale to deep part_of chains."
  - version: 8.0
    date: 2026-03-18
    summary: "Major rewrite: flat UUID-based corpus with compositional merges (DAG). Sources (captured from origins) and documents (merged composites) as the two record types. All metadata in YAML frontmatter. Schema library for content type definitions. Normalization integrity principle. Concrete capture staging and artifact/asset storage. Eliminates corpus-per-repo structure, graduation, tombstones, ID remapping, routing claims, partition codes."
  - version: "1.0–7.1"
    date: "2026-02-08 – 2026-03-17"
    summary: "Initial spec through corpus-per-repo architecture with structural IDs, partitions, graduation chains, and multi-repo management. Superseded by v8.0."
---

# Athenaeum — Architecture Specification

## 1. Overview

### 1.1 What This Is

The Athenaeum is a knowledge normalization and synthesis system. It captures content from external sources, normalizes each captured file into a uniform markdown representation, supports authoring codex records that synthesize knowledge across many captured artifacts, and compiles cross-cutting reference works (compendiums) that draw across multiple authored bodies of work.

The system is structured as **three layers, with strictly downward references**:

```
   compendium  (cross-codex + cross-corpus integration; published reference work)
        ↓                  ↓
     codex  ────────►  codex  ────────►  codex
        ↓                  ↓                  ↓
                 corpus  ────────►  corpus
```

- **The corpus (artifact layer).** A content-addressed archive of captured artifacts. Each artifact is one record, named by the blake3 hash of its binary content, with a body that's a faithful normalized rendering of the original. Cross-references inside an artifact's body (hyperlinks, embedded images) are resolved to blake3 wikilinks and embeds when the targets exist in the corpus. The corpus is the ground truth — it preserves what was captured, exactly as it was. **A corpus is the unit of tenant isolation**: a "private" corpus and a "public" corpus are separate corpora, and their content should be mutually exclusive.

- **The codex layer.** Authored markdown compositions, named by UUID, organized into named **codices**. A codex's records reference artifacts (citation, embed, functional URI) and other records within the same codex (cross-link, embed). **Codices reference downward only**: a codex's body never references another codex. A codex is the home of a particular author's or team's interpretation of one or more corpora.

- **The compendium layer.** Compiled, published reference works that integrate across codices and corpora. A compendium is composed of compendium records — author-named markdown chapters drawing on codices and corpora. A compendium has a defined scope, a point of view, and a domain taxonomy. **Compendiums are the integration layer** — when knowledge spans multiple codices or multiple corpora, the synthesis happens here, not at the codex level.

References point downward only. Codices and corpora do not declare runtime joins; **content addressing handles the join at runtime** — a `[[blake3]]` reference resolves into any corpus the runtime has loaded that contains the hash, and a `[[codex-name:slug]]` reference (only valid in a compendium) resolves into any codex the runtime has loaded.

### 1.2 Design Principles

1. **Every record is independently valid.** A single captured page and a fully synthesized monograph are both complete, addressable, useful markdown documents.

2. **Artifact immutability via content addressing.** Captured artifacts are identified by the blake3 hash of their binary content. The bytes never change; if they did, the hash would change and the record would be a different record. Re-encountering the same bytes appends a new entry to the existing record's `capture_dates` rather than creating a new record.

3. **Normalization integrity.** An artifact's body is a faithful normalized rendering of its original content. Normalization may produce a more accurate representation (resolve encoding ambiguity, fix format-conversion artifacts, surface OCR text from images) but it MUST NOT add information that didn't exist in the original. Editorial work happens in codex records and compendium records, not in artifacts.

4. **The normalized body as universal representation.** Every artifact record carries a text body: a normalized rendering of the original file appropriate to its content type. This body projects all modalities into a common representational space — text — enabling universal computation across the corpus. Search, similarity, clustering, and embeddings all operate on this body. The body is the durable, auditable, git-versioned input; everything derived from it is ephemeral cache, rebuildable when models improve or normalization is refined.

5. **Compositional structure lives in the body.** Codex records and compendium records express composition through their prose: wikilinks, embeds, and tags. There is no stored frontmatter "constituents," "part_of," "is_a," or "same_as." The link graph itself is the hierarchy. Equivalence is computed from intrinsic properties, not asserted.

10. **Strictly downward references.** A corpus's artifacts never reference upward (codices or compendiums don't exist from an artifact's perspective). A codex's records reference local-codex records and any artifacts the runtime can resolve, but never another codex's records. Compendiums reference codices and corpora — they're the integration layer. This keeps each layer self-contained and the system regeneration-safe.

11. **Reference stability hierarchy.** When citing content, prefer the lowest level that suffices: artifact (`[[blake3]]`) is always stable; a codex topic by slug (`[[slug]]` locally or `[[codex-name:slug]]` from a compendium) survives codex regeneration; a UUID is bound to a specific authored doc instance and may orphan across regeneration. The spec calls this out so authoring tools and curators know which form is canonical.

6. **Metadata-driven organization.** Classification, grouping, and discovery are tag and link operations, not filesystem operations. Reorganizing the corpus means editing references, never moving or renaming files.

7. **Stable identity.** An artifact's blake3 hash never changes (the bytes are immutable). A codex record's UUID never changes. References are permanent.

8. **LLM-native.** The pipeline leverages LLM capabilities for semantic tasks (normalization, cross-reference resolution, codex- and compendium-record authoring) while keeping mechanical tasks (capture, hashing, format conversion, functional URI evaluation) deterministic and reproducible.

9. **Offline-first.** Only capture requires network access. Everything else operates on local data — including normalization (when the local model is sufficient), record authoring, similarity, and compendium synthesis.

### 1.3 Terminology

| Term | Definition |
|------|-----------|
| **Record** | The universal unit. A markdown file with YAML frontmatter and a normalized or authored body. One of three kinds: an artifact record (in a corpus), a codex record (in a codex), or a compendium record (in a compendium). |
| **Corpus** | A content-addressed archive of artifacts. Identified by name. The unit of tenant isolation — a "private" corpus and a "public" corpus are separate corpora and never merged. Contains artifact records, the binary store, and any base/custom classification schemas the corpus uses. |
| **Codex** | A named container holding authored codex records. Lives outside any corpus. References artifacts (across any loaded corpus) and other records within the same codex; never references another codex. Multiple codices may coexist; the runtime determines which are loaded. |
| **Compendium** | A compiled reference work that integrates across codices and corpora. Composed of compendium records (author-named markdown chapters). The cross-cutting integration layer — when synthesis spans codices, that synthesis happens here. References codices (`[[codex-name:slug]]`), artifacts (`[[blake3]]`), and may use functional URIs for derived views of artifact content. |
| **Artifact Record** | A record representing a single captured file, named by the blake3 hash of its binary content (`{blake3-hash}.md`). One record per file, one content type per record. The body is a normalized text rendering of the artifact. The actual binary file is stored in content-addressed storage indexed by the same hash. Artifact records are the ground truth of the corpus. |
| **Codex Record** | A record representing authored knowledge, named by a UUID (`{uuid}.md`), living within a codex. The body is a markdown composition that references artifacts (as evidence) and other codex records in the same codex (as cross-references). Codex records are where editorial work lives. |
| **Compendium Record** | A markdown chapter that composes a compendium, with an author-chosen filename (e.g., `01-introduction.md`, `02-history.md`) under the compendium's `records/` directory. Compendium records are the integration-layer units where multi-codex / multi-corpus synthesis is written. |
| **Codex Topic** | A slug within a codex naming a stable synthesis target. The slug is the topic's identity for cross-codex citation (from a compendium) and survives codex regeneration that preserves topic naming. |
| **Content-Addressed Naming** | Artifact records are named by the blake3 hash of their binary content. Byte-identical files produce the same hash and therefore the same record — structural deduplication is automatic. Codex records use UUID-based naming; compendium records use author-chosen filenames. |
| **Blake3** | The 256-bit content hash that identifies an artifact record and its underlying binary. 64-character lowercase hex string. Functions as identity, filename stem, and content-addressed storage key. |
| **UUID** | Universally unique identifier for a codex record (v4, RFC 9562). Stable and permanent. Not used on artifact records or compendium records. |
| **Reference** | A wikilink or embed in a record's body that points to another record. References live in the body, not in frontmatter, and are visible in Obsidian's graph and backlink views. References point downward only — codex records reference artifacts; compendium records reference codices and artifacts; artifacts never reference upward. |
| **Wikilink** | `[[target\|display]]` — a clickable cross-reference. Bare targets are blake3 hashes (artifacts in any loaded corpus) or, in a codex, the codex's own record UUIDs/slugs. Qualified targets `codex-name:slug` and `corpus-name:blake3` are valid only in compendium-record bodies. The display text is optional. |
| **Embed** | `![[target]]` — inline content inclusion. Renders the target's normalized body at that position. For images, this surfaces the text description; in compiled outputs the actual binary can be substituted. |
| **Tag** | A flat, kebab-case classification label matching `[a-z0-9]+(-[a-z0-9]+)*`. Tags are corpus-local on artifacts and codex-local on codex records — no external concept document required. |
| **Slug** | An optional, container-unique, human-readable identifier (`[a-z0-9]+(-[a-z0-9]+)*`). For codex records, the slug is unique within its codex and serves as the codex topic. For artifacts, slugs are rare; when present, they are unique within the corpus. Enables readable wikilinks. |
| **Capture** | An encounter event recorded only by date. Re-encountering identical bytes appends a new entry to the artifact's `capture_dates`; the bytes themselves never move and never produce a new record. |
| **Normalization** | Producing the artifact's text body — extraction (HTML→markdown, PDF→text), transcription (audio/video→text), description (image→text), or metadata summary (opaque binary). Faithful to the original; no editorialization beyond inline topic annotations. |
| **Functional URI** | A composable URI scheme (`blake3://{hash}?page=4&crop=…`) used in codex and compendium bodies to reference deterministic transformations of artifact content. Never used in artifact bodies. Resolved at compile/render time. |
| **Schema** | A reference document describing how to normalize or classify content. Two kinds: **base schemas** (MIME-type-keyed, universal, foundational data contract) and **custom classification schemas** (corpus-local, optional, corpus-author-driven). |

---

## 2. Core Model

### 2.1 Records and Containers

A **record** is the universal unit of the Athenaeum. Every record is a single markdown file with YAML frontmatter and a body. Records are one of three kinds, each living in its own container:

- **Artifact records** — one per captured file, named by the blake3 hash of the binary content. Artifact records live in **a corpus**.

- **Codex records** — authored compositions, named by UUID v4. Codex records live in **a codex** — never inside the corpus.

- **Compendium records** — authored chapters of a compiled reference work, with author-chosen filenames. Compendium records live in **a compendium**.

The system has three layers of container:

| Container | Holds | Identifier | Reference direction |
|-----------|-------|-----------|--------------------|
| **Corpus** | Artifact records, the binary cache, schemas, capture staging. | Corpus name. | None outbound (corpora reference nothing). |
| **Codex** | Codex records authored by a particular author or team. | Codex name. | Downward: artifacts (any loaded corpus) and other records in the same codex. |
| **Compendium** | Compendium records — authored chapters of a published reference work drawn from one or more codices and corpora. | Compendium name. | Downward: codices (`[[codex-name:slug]]`), artifacts (`[[blake3]]`). |

All three layers use a `records/` directory for tracked markdown records. The corpus additionally maintains an `artifacts/` cache for raw binary content; the cache is **untracked** (regenerable from blake3 plus capture provenance).

**Corpus directory layout (high level):**

```
corpus-{name}/
├── records/      — Artifact Records (tracked markdown, content-addressed by blake3)
├── artifacts/    — raw binary cache (UNTRACKED, .gitignore'd)
├── capture/      — staging for in-progress captures
└── schema/       — base + custom classification schemas (see §3.3)
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

Compendium-record filenames are an authoring choice (e.g., `01-introduction.md`, `02-history.md`); compendium records do not carry the content-addressing or UUID naming used by the layers below them. See §6.

**Directory purposes:**

- **`records/`** (all three layers) — Tracked markdown records. Layout under `records/` (sharding, etc.) is an implementation concern; the spec only requires that a record be locatable by its identity (blake3 for artifacts, UUID for codex records, file path for compendium records).
- **`artifacts/`** (corpus only) — Raw binary cache. **Untracked**, listed in `.gitignore`. Implementations choose where the bytes actually live (local FS shard, object store, S3-compatible bucket, …); the data contract is just "given a blake3, the implementation can produce the bytes." The cache is regenerable from blake3 plus capture provenance and is not the source of truth.
- **`capture/`** (corpus only) — Staging area for in-progress captures. No identity assigned yet. Failed captures remain here without consuming corpus resources.
- **`schema/`** (corpus only) — Schemas governing normalization and custom classification (see §3.3).

There is no nesting beyond the top-level separation in any container. Organization is expressed through tags, wikilinks, embeds, and computed similarity — not through directory hierarchy. Concrete on-disk paths and sharding conventions live in the implementation guides (`impl-corpus.md` for corpus side, `impl-codex.md` for codex and compendium sides).

### 2.2 Artifacts

An artifact record represents a single captured file. It is named by the blake3 hash of the file's binary content (`{blake3-hash}.md`) and contains:

- **Frontmatter:** `content_type` (MIME type), `uris[]` (all known URIs that resolve to this artifact, none canonical), `capture_dates[]` (timestamps these bytes were encountered), schema-extracted extended fields, and standard metadata fields.

- **Body:** A normalized markdown rendering of the artifact, faithful to the original content's structure and meaning. For HTML: stripped-and-cleaned markdown preserving document structure. For audio: a transcript. For images: OCR text and/or visual description. For PDFs: extracted text with structural markup. Cross-references in the original content (hyperlinks, embedded images) are resolved to blake3 wikilinks and embeds where the targets exist in the corpus, preserving the original content's link structure. See §3.2 for body format rules.

- **Binary storage:** The actual file is stored in the corpus's `artifacts/` binary cache, retrievable by the same blake3 hash. The cache is untracked and regenerable; implementations may store the bytes wherever serves them best as long as a blake3 lookup produces them.

**Content-addressed deduplication.** If the same file is encountered again, the hash matches an existing record. No new record is created — the existing record gains a new `capture_dates` entry, and any URI not already in `uris[]` is appended. Git sees a metadata-only diff.

**Re-capture of changed content.** If a previously captured URL returns different content, the new content produces a different hash and therefore a new artifact record. Both records will list the URL in their `uris[]`, making them discoverable as captures of the same origin URL at different points in time. Cross-URI succession (the same content at a new URL) has no automatic mechanism in v10.

### 2.3 Codex Records

A codex record is an authored markdown composition representing synthesized knowledge. **Codex records live in a codex**, never inside the corpus. A codex record is named by a UUID (`{uuid}.md`) and contains:

- **Frontmatter:** `uuid`, `title`, optional `slug` (the codex topic), `tags` (classification), and minimal metadata. Codex-record frontmatter is deliberately thin — structural relationships live in the body.

- **Body:** Authored markdown prose with wikilinks to other records within the same codex, wikilinks and embeds referencing artifacts (by blake3 hash, resolved against any loaded corpus), and optionally functional URIs for computed transformations of artifact content. The body *is* the composition — it is the authoritative record of what knowledge the codex record synthesizes and what evidence it draws on.

A codex record's references point downward: to artifacts (citation, embed, functional URI) and to other records within the same codex (cross-link, embed). **A codex's records do not reference other codices** — that integration happens at the compendium layer (§6).

**Codex records are where editorial work lives.** Unlike artifact bodies (which faithfully mirror their original content), codex-record bodies are written by curators or synthesis agents. Codex records may add interpretation, analysis, and context that no single artifact contains; structure knowledge for a particular audience or purpose; reconcile disagreements across artifacts; and carry the editorial voice that artifacts intentionally lack.

### 2.4 The Layered Reference Graph

Composition is expressed through references in record bodies — there is no stored "constituents" list, no `part_of` field, no merge DAG metadata. The link graph itself is the hierarchy.

References point downward only. Within a single codex:

```
[[artifact a7f3…]]   ──┐
                       ├──►  [[doc song-meridian]]   ──┐
[[artifact e5f6…]]   ──┘                               │
                                                       ├──►  [[doc album-convergence]]
[[artifact i9j0…]]   ──┐                               │
                       ├──►  [[doc song-tidal]]      ──┘
[[artifact o5p6…]]   ──┘
```

Each arrow is a wikilink or embed appearing in the body of the referencing record. The "Album" codex record mentions its track records (in the same codex), and each track record mentions the artifacts it draws on (in the corpus). Reading the body reveals the structure; no separate metadata block restates it.

Across the three layers:

- **Artifact records (corpus)** — bodies may reference other artifacts in the same corpus, but only when the original content's hyperlinks/embeds resolve to captured targets. Artifacts never reference codices or compendiums; artifact bodies are faithful to original content, which has no knowledge of the codex/compendium layer.
- **Codex records (codex)** — bodies reference artifacts (any loaded corpus) and other records within the same codex. **A codex record never references another codex's records.** When that integration is needed, lift it to a compendium.
- **Compendium records (compendium)** — bodies reference codices (`[[codex-name:slug]]` or `[[codex-name:uuid]]`), artifacts (`[[blake3]]`, optionally qualified `[[corpus-name:blake3]]`), and may use functional URIs for derived views.

**Properties:**

- **Composition is implicit.** Following wikilinks reconstructs the structure. There is no canonical "tree" — a record may have many parents and many children.
- **Acyclic by convention within a layer.** Cycles are technically possible (a record linking to another that links back) but conventionally avoided in compositional structures. Cross-references between peer records at the same layer are fine and frequently desirable.
- **Non-destructive.** Authoring a parent record does not modify or consume its referenced children. References are pointers; targets remain independent.
- **Multi-parent.** A single record may be referenced by many records at higher layers. An interview-transcript artifact might be cited by an artist-profile codex record in one codex, a documentary-film codex record in another codex, and a compendium record that synthesizes both.
- **Strictly downward.** This is the v10 invariant. References don't cycle across layers; a layer's records know nothing about layers above them.

### 2.5 Codices

A **codex** is a named container holding authored codex records. Codices live outside the corpus, structurally independent of any specific corpus. The runtime configuration (which codices are loaded, which corpora are loaded) is the join — content addressing handles the rest.

**Codex contents:**

- **`records/`** — codex records (UUID-named, with optional codex-unique slugs).
- **`codex.yaml`** (optional) — codex-level metadata: display name, description, an optional default tag vocabulary or tag-conventions reference. The spec does not mandate any particular fields here; this is a place for codex-author convention.

**Codex naming.** A codex is identified by name. The runtime maintains a mapping from codex name to on-disk location (or remote URI). When a compendium-record body wikilinks `[[codex-name:slug]]`, the runtime looks up `codex-name` against the loaded codices.

**Codex topics (slugs as stable handles).** A codex record's slug is unique within its codex and serves as the **codex topic** — the stable identifier external references can point to. Topics survive codex regeneration (see below); UUIDs do not.

**Reference rules.** A codex record's body may wikilink:

- `[[blake3]]` → any artifact in any loaded corpus.
- `[[uuid]]` → another codex record in the same codex (rarely the most stable choice).
- `[[slug]]` → another codex record in the same codex by topic slug (preferred for stability).

A codex record's body may **not** wikilink `[[codex-name:…]]` or `[[other-corpus-name:blake3]]`. Cross-codex / cross-corpus references happen at the compendium layer (§6).

**Codex regeneration.** A codex may be authored by hand, by an LLM agent, or by a regeneration pass that re-derives the codex from a corpus snapshot plus authoring prompts. Regeneration is a contemplated future workflow — not part of v10's required behavior — but the design supports it. What MUST stay stable across regeneration: the slug→topic mapping (so external references survive). What MAY change: UUIDs, body prose, exact wikilinks within a record. Cross-codex references in compendiums that target a codex by slug stay valid; references that targeted a record by UUID may orphan.

**Multiple codices, no declared joins.** A user may have many codices (personal, professional, project-specific). Each codex is structurally independent. Two people independently maintaining codices that happen to satisfy the same compendium's references is a feature — content addressing makes the join just work at runtime.

### 2.6 Re-normalization Context Flow

Normalization is on-demand, not a one-time event. A given artifact may be re-normalized when:

- New artifacts are captured whose presence resolves previously unresolved cross-references (turning external URLs into blake3 wikilinks).
- The normalization model is upgraded.
- Schema guidance for the artifact's MIME type is improved.
- A bulk re-normalization sweep is triggered by tooling improvements.

Re-normalization MUST preserve normalization integrity — the new body remains faithful to the original artifact's content. It may produce a more accurate representation, but it MUST NOT introduce information not present in the original. Editorial enrichment that draws on context outside the artifact belongs in codex-record bodies, not in artifact bodies.

Codex records are re-authored, not re-normalized. They are edited by humans or synthesis agents like any other authored markdown.

### 2.7 Every Record Is a Valid Markdown Document

There is no "incomplete" state in terms of record validity. A freshly captured artifact whose body has been normalized is a complete, useful markdown document. An authored codex record whose body cites a single artifact is a complete, useful markdown document. The corpus is always in a valid state; any record can be selected for compendium synthesis at any time. Authoring richer codex records on top of existing artifacts and other records is enrichment, not a completion requirement.

---

## 3. Record Format

### 3.1 Frontmatter Schema

All record metadata lives in YAML frontmatter at the top of each `.md` file. There are no separate configuration files — the markdown file is the single source of truth for both metadata and content.

The schema library (`schema/`) provides normalization and classification guidance (see §3.3); extended fields beyond the core schema are tolerated freely (see §3.1.7). Appendix A provides a concise per-MIME field reference.

#### 3.1.1 Core Fields

Present on every record (unless noted as record-type-specific).

| Field | Type | Required | Applies to | Description |
|-------|------|----------|------------|-------------|
| `blake3` | string | yes (artifacts) | artifact records | The blake3 hash of the artifact's binary content. 64-character lowercase hex string. Serves as the record's identity, filename stem, and content-addressed storage key. |
| `uuid` | UUID | yes (codex records) | codex records | Standard v4 UUID. Not used on artifact records — artifact identity is the blake3 hash. Not used on compendium records — their identity is the author-chosen filename. |
| `slug` | string | no | both (typically codex records) | Optional corpus-unique, human-readable identifier. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Used for readable wikilinks. Uniqueness enforced corpus-wide; slug changes require updating all references. |
| `title` | string | yes | all | Short descriptive label. |
| `description` | string | yes | all | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `content_type` | string | yes (artifacts) | artifact records | IANA MIME type of the captured artifact (e.g., `text/html`, `application/pdf`, `image/jpeg`). `unknown` is permitted as a sentinel when the MIME cannot be determined. Codex records and compendium records do not carry `content_type` — they are markdown by construction. |
| `status` | enum | yes | all | Pipeline state: `stub` (captured, no body), `draft` (converted, body filled), `normalized` (LLM-refined, ready for use). Codex records and compendium records typically begin at `draft` since authoring fills the body directly. |
| `visibility` | enum | no | all | Editorial curation layer, independent of `status`. One of `visible` (default when absent), `deranked` (appears in results at lower priority), `hidden` (excluded from default results, still accessible by direct identifier). |
| `tags` | string[] | no | all | Classification tags. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Declare what this record is about or what category it belongs to. Tags are corpus-local — they require no external concept document to function. A corpus MAY define a tag vocabulary in its conventions file for consistency. |

On artifact records, `tags` classify what the captured content is about. They are populated by the normalizer during contextualization and may be refined by curation passes. Frontmatter tags declare whole-record topical coverage; inline comment tags (`%% #tag %%`) provide positional precision (see §3.2).

On codex records, `tags` classify what the authored knowledge covers. They are set by the record's author (human or agent).

`visibility` lets a curator retire low-quality records from normal surfaces without deleting them. Use cases: low-content pages caught in a bulk scrape; superseded captures that remain valuable as historical versions; records flagged for further review. Default search and list queries show only `visible` records.

**Record type signaling.** Whether a record is an artifact, a codex record, or a compendium record is signaled by independent signals, with no dedicated `record_type` field. By the **container**: artifacts in a corpus's `records/` directory, codex records in a codex's `records/` directory, compendium records in a compendium's `records/` directory. By the **filename**: 64-character lowercase hex blake3 hash for artifacts, UUID v4 for codex records, author-chosen names (e.g., `01-introduction.md`) for compendium records. By **required field presence**: `blake3` on artifacts, `uuid` on codex records, neither on compendium records (their identity is the file path). The three signals are independently sufficient and never disagree.

#### 3.1.2 Artifact-Specific Fields

Present only on artifact records.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uris` | string[] | yes (≥1) | All known URIs that resolve to this artifact's bytes. None canonical — request URLs, redirect targets, mirror URLs, DOIs, IPFS CIDs, `file://` paths are all equivalent labels. URIs may be added at any time (e.g., a DOI assigned later, a mirror discovered) and become valid retroactively for the artifact. |
| `capture_dates` | ISO-8601[] | yes (≥1) | Timestamps at which these bytes were encountered. Re-encountering identical bytes appends a new entry. |
| `hashes` | map | no | Per-artifact instances of the cryptographic and perceptual hashes the base schema (§3.3.1) declares for this MIME. blake3 is at the top level (it is the identity); other declared hashes (e.g., `chromaprint`, `phash`, `sha256`) live here. |
| `classifications` | object[] | no | Audit log of custom classification schemas applied to this artifact. Each entry is `{schema, justification}`; see §3.3.2. The schemas' contributed fields and tags merge into top-level frontmatter (this array does not duplicate them). Absent when no custom classifications have been applied. |
| `normalization_type` | enum | no | How the body was derived: `extraction` (HTML→markdown, PDF→text), `transcription` (audio/video→text), `description` (image→text), `metadata` (opaque binary→summary). |
| `author` | string | no | Identifiable person who produced this content. Omit for anonymous content. |
| `date_published` | date | no | When the original content was published. Omit for undated content. |

Example artifact frontmatter fragment:

```yaml
blake3: "a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."
content_type: text/html
uris:
  - "https://forum.example.com/threads/caliper-rebuild.4521/"
  - "https://forum.example.com/threads/caliper-rebuild-2024/"   # redirect target
  - "doi:10.5555/forum.thread.4521"                              # added retroactively
capture_dates:
  - 2026-03-15T14:22:00Z
  - 2026-04-02T09:11:00Z
hashes:
  simhash: "f7e8d9c0b1a24c3d"
  sha256: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
normalization_type: extraction
```

The same bytes encountered twice append a new entry to `capture_dates` — they never produce a second record. New URIs discovered for already-captured bytes are appended to `uris[]` whenever they're discovered, including long after the original capture.

#### 3.1.3 Codex-Record-Specific Fields

Present only on codex records.

Codex-record frontmatter is deliberately thin. Beyond the core fields (`uuid`, `title`, `description`, `status`, optional `slug`, `visibility`, `tags`) and the common quality and pipeline fields below, codex records carry no structural metadata. A codex record's references to artifacts and other records are visible in its body as wikilinks and embeds; the body is the authoritative record of what knowledge the record synthesizes and what evidence it draws on.

There is no `constituents` list, no `part_of`, no `same_as`, no `is_a`. All structural relationships are body references or computed similarity (see §3.5).

#### 3.1.4 Quality Fields

Present on every record. These describe the normalizer's *self-assessment of how it did its job* — they are not content-trust judgments. Credibility, when expressed, is a custom classification — each credibility signal is its own schema. See §3.3.2 and Appendix A.2.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `normalization_confidence` | float | yes (artifacts) | `0.0`–`1.0`, quality of the normalization process for this artifact. |
| `normalization_model` | string | no | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`). |
| `normalization_date` | date | no | When normalization was last performed. |

#### 3.1.5 Pipeline Fields

Present on artifact records; optional on codex records.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conversion_method` | string | conditional | How the artifact body was produced (e.g., `html-extraction`, `pdf-text`, `whisper-transcription`, `passthrough`). |
| `conversion_tool` | string | conditional | Tool/script version used for conversion. |
| `conversion_date` | date | conditional | When conversion was performed. |

These fields enable targeted bulk re-conversion when tools improve (e.g., "re-convert all artifacts processed by `tesseract v4`").

#### 3.1.6 Issues

Optional array of known quality or completeness problems. Absence means "no known issues."

```yaml
issues:
  - type: "missing_media"
    severity: "major"
    description: "3 of 5 embedded images unavailable — showed step-by-step assembly procedure"
    remediation: "wayback_snapshot"
    resolved: false
```

**Issue types:**

| Type | Description |
|------|-------------|
| `missing_media` | Images, videos, or embedded content unavailable |
| `broken_links` | Referenced URLs are dead |
| `partial_content` | Content was truncated, paywalled, or incompletely captured |
| `content_modified` | Content edited since original publication |
| `encoding_corruption` | Garbled text, mojibake, mangled characters |
| `format_loss` | Tables, diagrams, or formatting didn't survive conversion |

**Severity:** `critical` (unusable without fix), `major` (significant loss but partially useful), `minor` (cosmetic or non-essential).

**Remediation:** `wayback_snapshot`, `alternate_source`, `original_author`, `re_capture`, `manual_reconstruction`, `none`.

The `resolved` boolean tracks whether the issue has been addressed. Resolved issues remain in frontmatter as historical record.

#### 3.1.7 Extended Fields

Records may carry frontmatter fields beyond those in §3.1.1–§3.1.6. Extended fields come from two sources:

- **Base schema extraction.** Format-intrinsic fields read from the artifact's binary (file headers, embedded metadata). Examples: `page_title` and `meta_description` for HTML, `duration_seconds` and `bitrate_kbps` for audio, `width_px` and `height_px` for images, `page_count` for PDFs. The base schema for each MIME type defines which fields the normalizer extracts (see §3.3.1).

- **Custom classification schema extraction.** Domain-specific fields added when a custom classification schema (§3.3.2) matches the record. Examples: `artist`, `album`, `track_number` when an audio file's ID3 tags identify it as a musical recording; `service_section`, `vehicle_platform` when a PDF is recognized as a service manual page. Custom classification schemas are corpus-local and corpus-author-driven.

Extended fields are tolerated by the core loader but not required. A record carrying only the base-schema fields its MIME yields is fully valid — classification can be deferred to a later pass.

If a field is genuinely required for a kind of content the corpus cares about, the strongest practice is to author a custom classification schema declaring the requirement and a tag the normalizer applies when the schema matches.

### 3.2 Body Format

The body of a record is the markdown content below the frontmatter closing `---`. The rules differ sharply between artifact bodies and codex-record bodies. Compendium-record bodies follow the codex-record body conventions (with the added freedom of cross-codex / cross-corpus citation forms; see §6).

#### 3.2.1 Artifact Body Integrity

An artifact's body is a faithful normalized rendering of the original content. The normalizer MUST NOT add editorial content, interpretation, or connections that did not exist in the original. The body mirrors the original's structure: its headings, paragraphs, lists, links, and embedded media, translated into markdown.

The one permitted addition is inline topic annotations (§3.2.4) — these are metadata, not content.

#### 3.2.2 Cross-Reference Resolution

The original content's hyperlinks and embedded resources are resolved during normalization:

- **Captured target exists in corpus:** Replace the URL with a blake3 wikilink or embed.
  - Hyperlinks become wikilinks: `[[{blake3-hash}|original link text]]`
  - Embedded images become embeds: `![[{blake3-hash}]]`
  - Embedded media become embeds with alt text: `![[{blake3-hash}|description]]`

- **Captured target does not exist:** Leave as a standard markdown URL: `[link text](https://original-url.com)` or `![alt](https://original-url.com/image.jpg)`. The link is unresolved — it points outside the corpus. If the target is captured later, a re-normalization pass can resolve it.

Cross-reference resolution is the *only* way artifacts link to each other. No artifact body contains wikilinks or embeds that the normalizer invented — every link corresponds to a link or embed in the original content.

Wikilinks SHOULD use the full 64-character blake3 hash. Tooling MAY accept unambiguous hash prefixes for human-edited contexts, but generated artifact bodies use the full hash.

#### 3.2.3 What Embeds Mean

When an artifact body contains `![[blake3-hash]]`, Obsidian renders the target artifact's body inline. For an image artifact, this means the image's normalized text (OCR, visual description) appears at the position where the original image was. For a linked text artifact, Obsidian renders the target's full body. In compiled outputs (mdbook, static site), the tooling can substitute the actual binary (render the real image, embed the real video).

The same syntax in codex-record and compendium-record bodies has the same meaning, plus access to functional URIs (§3.7) for computed transformations.

#### 3.2.4 Inline Topic Annotations

Artifact bodies may contain topic annotations in Obsidian-style comment blocks. These are the *only* permitted editorialization in an artifact body — they are metadata annotations classifying what the surrounding content discusses, not additions to the content.

**Syntax:** `%% #slug %%` or `%% #slug-1 #slug-2 %%`

**Scoping rules:**

1. **Frontmatter `tags`** — whole-record scope. Every line is implicitly within these topics.
2. **Annotation on a heading** — section scope. Applies until the next heading of equal or higher level.
3. **Annotation on a line** — passage scope. Applies to that specific line only.

Scopes are additive. Annotate at topical transition points, not on every line.

Codex-record bodies may use the same annotation syntax for the same purpose.

#### 3.2.5 Codex-Record Bodies

Codex-record bodies are authored compositions with full editorial freedom. Unlike artifact bodies (which faithfully mirror original content), codex-record bodies are written by curators or synthesis agents. They may:

- Add interpretation, analysis, and context that no single artifact contains.
- Structure knowledge for a particular audience or purpose.
- Reference artifacts as evidence using wikilinks: `[[{blake3-hash}|display text]]`
- Embed artifact content inline: `![[{blake3-hash}]]`
- Use functional URIs for computed transformations: `![[blake3://{hash}?params|alt text]]`
- Link to other codex records: `[[{uuid}|display text]]` or `[[slug|display text]]`
- Use tags for topical classification (in frontmatter and optionally inline).

#### 3.2.6 Referencing Artifacts from Codex Records

Codex records reference artifacts in two ways:

- **Wikilinks** (`[[{blake3-hash}|text]]`) — citation-style references. "See the original forum post for details." The reader can click through to the full artifact.

- **Embeds** (`![[{blake3-hash}]]`) — inline content inclusion. The artifact's normalized body renders at that position. For images, this surfaces the text description; in compiled outputs, the actual image can be substituted.

Both create backlinks visible in Obsidian's graph view, making it discoverable which codex records draw on which artifacts.

#### 3.2.7 Connecting Codex Records to Codex Records

Codex records connect to each other through standard Obsidian primitives:

- **Wikilinks** — cross-references between codex records. "See also the [[brake-system-overview|Brake System Overview]]."
- **Tags** — shared classification. Codex records tagged `#brake-caliper` are discoverable together.
- **Embeds** — inline inclusion of one codex record's body in another.

There are no stored structural relations (`is_a`, `part_of`). Compositional structure is expressed through the codex graph itself: a "Brake System Overview" codex record that wikilinks to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" records *is* the compositional structure. The links in the body are the hierarchy.

### 3.3 Schema Library

Classification has a clear hierarchy:

1. **MIME-based classification (base schemas) is the foundational and required step.** Every artifact gets a base schema applied, driven by its `content_type`. The base schema dictates the normalization method, declares the hashes that ship with the artifact, and lists the extended fields the normalizer extracts. This is the data-contract floor. Tooling consuming the corpus can rely on every base-schema-declared field and hash being present absolutely.

2. **Custom classification is an optional layer on top.** A corpus author MAY define custom classification schemas to recognize content patterns and extract domain-specific fields and tags. The spec describes the *mechanism* (match conditions, field/tag declarations, schema composition rules); it does **not** prescribe what schemas a particular corpus should have or how the corpus's authors should choose to maintain them. Custom classification is a curatorial artifact — it lives entirely with the corpus.

The two kinds of schemas live under `schema/base/` and `schema/classification/` respectively (concrete layout in `impl-corpus.md`).

#### 3.3.1 Base Schemas (MIME type)

Base schemas are keyed by `content_type`. **They are part of the data contract** — every conforming corpus carries the fields and hashes its base schemas declare for the MIMEs it contains. Tooling consuming the corpus relies on these guarantees absolutely.

A base schema defines:

- **Normalization method:** `extraction`, `transcription`, `description`, or `metadata`.
- **Normalization guidance:** prose instructions for the normalizer.
- **Hashes:** the cryptographic and perceptual hashes that ship with every artifact of this MIME. `blake3` is always present (it is the artifact's identity). Format-specific perceptual hashes (e.g., `chromaprint` for audio, `phash` for images) are declared here. Any auxiliary hashes (e.g., `sha256`, `md5`) the schema chooses to publish are also declared here. The per-artifact instances of these hashes live in the artifact record's `hashes` field (§3.1.2).
- **Extended fields:** structured metadata mechanically extractable from any file of this type. These are format-intrinsic — they come from file headers and embedded metadata.

Base schemas are universal. They apply to any corpus using this MIME type. They travel with the Athenaeum toolkit, not with individual corpora.

**Schema document format:**

```yaml
schema_type: base
content_type: "audio/mpeg"

normalization:
  method: "transcription"
  guidance: |
    Extract audio metadata from file headers. Read ID3v2 tags
    when present, falling back to ID3v1.

hashes:
  - blake3         # required for every artifact (its identity)
  - chromaprint    # perceptual hash for audio
  - sha256         # auxiliary, for interoperability with external systems

extended_fields:
  duration_seconds:
    type: number
    required: true
    source: file_metadata
    description: "Total duration in seconds."
  bitrate_kbps:
    type: number
    required: false
    source: file_metadata
    description: "Encoding bitrate in kbps."
  sample_rate_hz:
    type: number
    required: false
    source: file_metadata
    description: "Sample rate in Hz."
  channels:
    type: number
    required: false
    source: file_metadata
    description: "Audio channels (1=mono, 2=stereo)."
```

The procedural side — how a normalizer detects MIME, in what order it computes these hashes, where the resulting binary lands on disk — is an implementation concern (see `impl-corpus.md`). What the spec mandates is that each artifact of this MIME ends up carrying every declared hash and every required field.

#### 3.3.2 Custom Classification Schemas

Custom classification schemas are optional. A corpus author authors them to recognize content patterns and extract domain-specific fields and tags beyond what the base schema gives. The spec defines the schema format and the composition rules; it does **not** dictate which schemas a particular corpus should have.

Custom classification schemas live in the corpus's `schema/classification/` directory. They are portable with the corpus but are not universal — different corpora carry different custom schemas reflecting their own concerns.

**Match conditions.** A schema's `match` block declares the conditions under which it applies. Any of these condition types may be combined; all listed conditions must be satisfied for the schema to match:

- **`content_type`** — exact MIME match or MIME-prefix match (e.g., `audio/*`).
- **`uri_pattern`** — a regex evaluated against any entry in the artifact's `uris[]`. A typical use is matching a domain (e.g., `^https?://[^/]*example\\.com/`).
- **`has_tags`** — list of tags the artifact must already carry (after base-schema or earlier-classification application).
- **`field_match`** — required values for already-extracted extended fields (e.g., `pdf_producer: "TexLive"`).

A match is a logical AND across the listed conditions. To express disjunction, author multiple schemas — they compose naturally (see below).

**Schema document format.**

```yaml
schema_type: classification
match:
  content_type: "audio/mpeg"
  has_tags: []                                  # optional
  uri_pattern: ""                               # optional
  field_match:                                  # optional
    # field_name: required_value

classification:
  add_tags: [musical-recording]

extended_fields:
  artist:
    type: string
    source: id3_tag
    description: "Performing artist from ID3 metadata."
  track_title:
    type: string
    source: id3_tag
    description: "Track title from ID3 metadata."
  album:
    type: string
    source: id3_tag
    description: "Album name from ID3 metadata."
  track_number:
    type: number
    source: id3_tag
    description: "Track position on album."
```

**Composition.** The normalizer applies the base schema first (format extraction, declared hashes, base-schema fields). It then evaluates all custom classification schemas in the corpus; every schema whose `match` is satisfied contributes its `classification.add_tags` and `extended_fields` to the artifact. Multiple schemas may match — their fields merge (last-write-wins on collision; tag lists are unioned).

**Audit trail (`classifications` array).** Every applied custom classification schema is also recorded on the artifact in a top-level `classifications:` array (§3.1.2). Each entry has only two fields:

```yaml
classifications:
  - schema: forum-thread
    justification: "URL matched forum.example.com domain pattern"
  - schema: community-validated
    justification: "Repair confirmed across 5+ replies with photos; OP follow-up reports successful resolution; no dissenting comments"
```

- **`schema`** — the schema's name (filename stem under `schema/classification/`).
- **`justification`** — required prose explaining *why* this schema was applied. For deterministic matches the justification is mechanical ("matched id3v2 TPE1 + TALB populated", "URL matched forum.example.com domain pattern"). For LLM-judgment matches the justification is substantive prose summarising the evidence ("thread shows consensus across 5+ users on the symptoms and the remedy").

The contract is uniform: every applied schema produces a `classifications` entry, every entry carries a justification. The shape is the same regardless of how mechanical or judgmental the match was. Re-runs, schema iteration, and curator review all read the same audit trail.

The array does **not** duplicate the schema's contributed fields or tags — those live in the merged top-level frontmatter per the composition rule above. The array is purely the log of *which schemas applied and the reasoning for each*. Field provenance ("which schema contributed `thread_id`?") is reconstructed by walking the schemas referenced in `classifications:` against their declarations — the schema files are the source of truth for what each schema contributes.

**Layered matching.** Because a schema's match conditions can include `has_tags`, a schema can layer on top of an earlier match. A general-platform schema might add a tag (e.g., `video-platform-x`) and a few generic fields; a more-specific schema gated on `has_tags: [video-platform-x]` plus a `uri_pattern` can then add fields specific to a particular show or section of that platform. This is how a corpus grows from coarse to fine classification without duplicating match logic.

**Examples (illustrative — concrete schemas are corpus-author choices).**
- An artifact captured from a video-hosting platform: a domain-keyed schema adds `upload_date`, `like_count`, `channel_name`, `view_count`.
- An artifact from a specific recurring show on that platform: a layered schema (`has_tags: [hosted-video]` + a channel-specific `uri_pattern`) adds `episode_date`, `hosts`, `guests`, `topics_discussed`.
- An artifact from a specific forum-platform signature: a `uri_pattern` schema adds `thread_id`, `op_username`, `reply_count`.
- Audio with populated ID3 tags: as in the example above, adds `artist`, `album`, `track_number` and the `musical-recording` tag.

**Unclassified artifacts.** An artifact that matches no custom classification schema is fully valid — it carries its base-schema fields and whatever tags the normalizer or operator assigned. Custom classification can be deferred to a later pass when more context is available.

**Tag vocabulary conventions.** A corpus MAY maintain a conventions file listing its tag vocabulary with one-line descriptions. This is guidance for normalizers and curators, not a schema constraint. Unknown tags are valid — they signal vocabulary growth. High-frequency unknown tags are candidates for formalization, often via a new custom classification schema.

#### 3.3.3 Custom classification as a living curatorial artifact

Custom classification schemas are not authored upfront; they emerge from how the corpus is used.

**The feedback loop.** Codex-record and compendium-record authoring reveals patterns. Authors keep reaching for the same metadata about the same kind of content; tag clusters form around recurring topics; a domain dominates a slice of the corpus. The curator notices these patterns and authors a custom classification schema that captures them — declaring the fields the authors keep wanting and the tag that names the pattern. A re-normalization sweep applies the new schema to every existing artifact whose match conditions are satisfied. Subsequent authoring is now richer because the metadata is already on the artifacts.

This loop is the corpus's classification layer growing in step with its actual usage. A corpus with no codex layer above it yet has only base schemas — and that's fine. A corpus whose codex layer is rich and active will grow a substantial custom classification library over time. The schemas, the artifacts, and the records co-evolve.

The pipeline mechanics of pattern detection, schema authoring, and re-normalization sweeps live in `impl-corpus.md`.

The Curator agent (§5.5) is responsible for monitoring the codex layer for pattern emergence and proposing new custom classification schemas to the operator.

#### 3.3.4 MIME Type Reference

A concise per-type reference for the most commonly captured MIME types. Each row lists the canonical MIME, the normalization method, and the extended fields the base schema typically extracts. This is illustrative, not closed — any IANA MIME type is valid.

| MIME | Method | Typical extended fields |
|------|--------|------------------------|
| `text/html`, `application/xhtml+xml` | extraction | `page_title`, `meta_description`, `canonical_url`, `og_title`, `og_description`, `og_image`, `og_type`, `language` |
| `text/markdown` | extraction (passthrough) | `word_count` |
| `text/plain` | extraction (passthrough) | `word_count`, `language` |
| `application/pdf` | extraction | `page_count`, `pdf_author`, `pdf_title`, `pdf_creation_date`, `pdf_producer`, `is_scanned` |
| `application/epub+zip` | extraction | `work_title`, `epub_author`, `language`, `chapter_count`, `word_count` |
| `audio/mpeg`, `audio/flac`, `audio/wav`, `audio/ogg` | transcription | `duration_seconds`, `bitrate_kbps`, `sample_rate_hz`, `channels` |
| `video/mp4`, `video/webm`, `video/mkv`, `video/quicktime` | transcription | `duration_seconds`, `width_px`, `height_px`, `frame_rate`, `video_codec`, `audio_codec` |
| `image/jpeg`, `image/png`, `image/webp`, `image/gif` | description | `width_px`, `height_px`, `color_space`, `exif_date`, `exif_gps_lat`, `exif_gps_lon`, `exif_camera` |
| `message/rfc822` (email) | extraction | `from`, `to`, `subject`, `message_date`, `in_reply_to` |
| `application/json` | extraction (passthrough) | `top_level_keys` (when reasonable) |
| `unknown` or unmatched | metadata | `byte_size`, `magic_bytes_summary` |

A corpus authoring its own custom classification schemas adds further extended fields on top of these (see §3.3.2).

### 3.4 Examples

#### Artifact Record

```yaml
---
blake3: "a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."
title: "Caliper Rebuild Thread"
description: "Enthusiast-forum thread documenting a front caliper rebuild on a sedan, with photos of bore wear and discussion of remanufactured units."
content_type: text/html
uris:
  - "https://forum.example.com/threads/caliper-rebuild.4521/"
capture_dates:
  - 2026-03-15T14:22:00Z
hashes:
  simhash: "f7e8d9c0b1a24c3d"
  sha256: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
status: normalized
visibility: visible
tags: [brake-caliper, caliper-rebuild, forum-thread, community-validated]
normalization_confidence: 0.92
normalization_type: extraction
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-15
conversion_method: "html-extraction"
conversion_tool: "scrape_thread.py v0.6"
conversion_date: 2026-03-15

# Schema-extracted extended fields (from text/html base schema)
page_title: "Caliper Rebuild Thread"
meta_description: "Discussion of front caliper rebuild"
language: "en"

# Custom classification audit trail
classifications:
  - schema: forum-thread
    justification: "URL matched forum.example.com domain pattern"
  - schema: community-validated
    justification: "Repair confirmed across 5+ replies with photos; OP follow-up reports successful resolution; no dissenting comments"
---

## Caliper Rebuild Thread

**Original post by user_alpha, 2024-08-12:**

Had to rebuild the front calipers on my sedan at 180k km.
Here's what the bore looked like after pulling the piston:

![[b8c9d0e1f2a3b4c5...]]

Scoring was bad enough that I decided to replace rather than hone.
Ordered a remanufactured unit from [a parts retailer](https://parts.example.com/caliper-xyz).

If you're seeing similar wear, check out the
[[c9d0e1f2a3b4c5d6...|brake bleeding procedure thread]]
before reassembling — I made the mistake of not bench-bleeding first.
```

The inline image is embedded via `![[blake3-hash]]` — this embeds the image artifact's normalized text body (a visual description). The link to the bleeding thread is a wikilink to another artifact record. The parts-retailer link stays as a plain markdown URL because that page wasn't captured. No editorialization in the body — it faithfully mirrors the original forum post's structure and content.

#### Codex Record

```yaml
---
uuid: "a1b2c3d4-e5f6-7a8b-9c0d-e1f2a3b4c5d6"
slug: "brake-caliper-rebuild"
title: "Brake Caliper Rebuild"
description: "Authored guide to rebuilding the front calipers on a sliding-caliper braking system, drawing on the service manual, a community forum thread, and a video walkthrough."
status: draft
visibility: visible
tags: [brake-caliper, caliper-rebuild]
---

## Overview

The front brake calipers in a typical single-piston sliding design
are straightforward to rebuild, but the piston bore must be inspected
carefully.

![[blake3://a7f3b2c1?page=4&crop=50,100,550,400|Caliper exploded diagram from service manual]]

## Inspection

Remove the caliper mounting bolts using the appropriate socket size.
See [[b8c9d0e1...|service-manual procedure]] for torque specs.

Inspect the piston bore for scoring:

![[blake3://c9d0e1f2?framegrab=1:23|Bore scoring example from video walkthrough]]

If scoring is visible as in the image above, the caliper must be
replaced — the bore cannot be honed back to spec on this design. See
[[d0e1f2a3...|forum-thread discussion]] for additional commentary.

## Related

- [[brake-bleeding|Brake Bleeding Procedure]] — must bench-bleed before reassembly
- [[rotor-replacement|Rotor Replacement]] — often done at the same time
- [[brake-system-overview|Brake System Overview]] — parent document
```

The codex record uses both plain blake3 wikilinks (for direct artifact references) and functional URIs (for computed transformations like page extraction and framegrabs). Links to other codex records use slugs for readability.

### 3.5 Classification

Classification in v10 uses tags, the codex graph, and computed similarity — no stored structural relations.

#### 3.5.1 Tags

Tags handle categorical classification. An artifact tagged `brake-caliper` is findable by topic. A codex record tagged `brake-caliper` and `vehicle-platform-x` is discoverable at the intersection. Tags are flat (no hierarchy), portable (no external dependencies), and container-local on the side they live in (a tag means whatever the corpus's or codex's conventions say it means).

A corpus MAY maintain a conventions file (`schema/tags.md` or similar) listing its tag vocabulary with one-line descriptions. This is guidance, not constraint — unknown tags are valid and signal vocabulary growth.

#### 3.5.2 The Codex Graph

The codex graph handles structural organization. A "Brake System Overview" codex record that links to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" records expresses compositional structure through its body, not through frontmatter relations. The link graph is the hierarchy.

A codex record representing a concept (a category, a person, a place, a thing) is just a record with descriptive prose. Other records reference it by wikilink. There is no special "concept record" status — the role is emergent from the graph.

#### 3.5.3 Deduplication and Similarity

Deduplication and similarity are handled entirely through intrinsic properties of artifacts, not through stored relations:

**Tier 1: Blake3 (exact).** Same bytes → same hash → same record. Structural, automatic, zero-cost.

**Tier 2: Perceptual hashes (format-specific, cached).** Same perceptible content, different bytes. pHash/dHash for images, chromaprint for audio, simhash for text/HTML. Computed from the binary artifact. Cached for performance, rebuildable from inputs that are already stored.

**Tier 3: Body embeddings (cross-modal, cached).** The normalized body projects every modality into text. Embeddings of that text enable universal semantic similarity. An audio transcript and an HTML transcript of the same interview land near each other because their normalized text says the same things. Cached, rebuildable, model-upgradeable.

All three tiers produce queries, not stored edges. The spec defines the inputs (binary artifact + normalized body); tooling builds the indices.

### 3.6 Slugs

Slugs provide human-readable addressability for records.

**Documents (in codices)** routinely have slugs. The slug is **the codex topic** — the stable handle external references can point at. Slug uniqueness is **codex-scoped**: two codices may each define a `brake-bleeding` slug for their own purposes, with no collision.

**Artifact records (in corpora)** rarely have slugs but may carry one for a significant, frequently-referenced capture. Artifact slug uniqueness is **corpus-scoped**.

**Slug stability across regeneration.** When a codex is regenerated (re-derived from a corpus snapshot plus authoring prompts), slugs are the contract — they MUST be preserved. UUIDs are not preserved. This is why cross-codex references from compendiums (§6) prefer `[[codex-name:slug]]` over `[[codex-name:uuid]]`.

**Slug renaming.** Renaming a slug breaks references that target it. Tooling SHOULD provide a rename helper that walks the affected codex and any compendiums that reference it, rewriting references in a single pass.

**Wikilink resolution order** depends on the body's container:

In an artifact body:
1. Exact match against `blake3` (any artifact in any loaded corpus).
2. Otherwise, an unresolved link — surfaced as a backlink candidate.

In a codex's document body:
1. Exact match against `blake3` (any artifact in any loaded corpus).
2. Exact match against `slug` within the local codex.
3. Exact match against `uuid` within the local codex.
4. Otherwise, unresolved.

In a compendium body:
1. Bare `[[blake3]]` — any artifact in any loaded corpus.
2. Qualified `[[corpus-name:blake3]]` — that artifact in the named corpus (used when blake3 alone needs provenance disambiguation).
3. Qualified `[[codex-name:slug]]` — the codex topic in the named codex.
4. Qualified `[[codex-name:uuid]]` — a specific doc instance in the named codex (discouraged; orphans across regeneration).
5. Otherwise, unresolved.

### 3.7 Functional URI Scheme

Codex records and compendium records may reference computed transformations of artifacts using functional URIs. **Functional URIs are not used in artifact bodies** — artifact bodies use plain blake3 wikilinks and embeds only.

**Base syntax:** `blake3://{hash}` — resolves to the artifact's binary content. The functional URI scheme carries no corpus prefix; provenance assertion (when a compendium needs to be specific about which corpus it drew from) lives on the wikilink citation form `[[corpus-name:blake3]]` (§3.6, §6.2), separately from any embed or derived view.

**Fragment navigation:** `blake3://{hash}#anchor` — navigates to a named section of the artifact's normalized body.

**Transformation parameters:** appended as query parameters, composed left-to-right (each function operates on the output of the previous):

| Parameter | Applies to | Meaning |
|-----------|-----------|---------|
| `page={n}` | PDF | Extract page n (1-indexed). |
| `page={n}-{m}` | PDF | Extract page range. |
| `crop={x},{y},{w},{h}` | Image, PDF page | Crop to region (origin top-left, pixels or percentage). |
| `resize={w}x{h}` | Image | Resize to dimensions. |
| `framegrab={t}` | Video | Extract frame at timestamp (seconds or `m:ss`). |
| `range={t1}-{t2}` | Audio, Video | Extract time range. |
| `grayscale` | Image | Convert to grayscale. |

**Composition example:** `blake3://{hash}?page=4&crop=50,100,550,400` — extract page 4 from a PDF, then crop to the indicated region. The result is an image.

**Semantics:**

- Functional URIs are **deterministic** — same inputs always produce the same output (the underlying artifact is immutable by content addressing).
- Results are **cacheable** — the cache key is the full URI string. Cache can be blown away and regenerated at any time.
- Results are **ephemeral** — they are not stored as records. They exist at compile/render time.
- Functional URIs are **codex / compendium-only** — artifact bodies never contain them.

**In Obsidian (raw browsing):** Functional URIs that can't be resolved at browse time fall back to displaying the alt text. Tooling or plugins can resolve them.

**In compiled outputs (mdbook, static site):** The build process resolves all functional URIs, computes transformations, and substitutes results (rendered images, extracted audio clips, etc.).

The v10 parameter set is deliberately minimal. Future extensions should be added conservatively — each parameter must be deterministic over immutable inputs.

---

## 4. Pipeline

The path from raw content to a richly authored corpus is a pipeline of discrete steps: **capture**, **normalize**, optionally **author**, and optionally **re-normalize**. Each step is independently re-runnable. A separate **build** step materializes the corpus for consumption.

### 4.1 Capture

Capture brings raw content into the corpus. The flow is content-addressed end-to-end: identity is the hash of the bytes, not an assigned UUID.

#### 4.1.1 Staging (optional)

Captures may pass through `capture/` as a transient workspace for in-progress acquisition (multi-step downloads, multi-file scrapes, manual organization). Failed or abandoned captures remain here without consuming corpus resources.

#### 4.1.2 Reconciliation

When reconciliation completes for a captured file:

- The file's binary content is locatable in the content-addressed binary store under its blake3 hash.
- An artifact record exists for that blake3 hash. If a record for the hash already existed (the bytes had been captured before), reconciliation appended capture provenance to it rather than creating a duplicate. If no record existed, a new one was created with `blake3`, `content_type` (the MIME determined for the binary), capture provenance, and `status: stub` (body empty pending normalization).
- The artifact record carries every hash declared by its base schema (§3.3.1) — at minimum `blake3`, plus any format-specific perceptual hashes and auxiliary hashes the schema lists.
- Reconciliation has not classified *what the record is about* — only *what format it is in*. Classification (tags, custom classification schemas) happens during normalization or in later passes.

The procedural detail — order of fetch / MIME-detect / hash / store, transient staging, in-memory record build — is implementation-specific (see `impl-corpus.md`).

**Key principles:**

- Capture is the **only step requiring network access**. Everything downstream is offline.
- Identity is the hash. Failed captures consume no identity space.
- Every captured file becomes its own artifact record. Bundles of related files (a page plus its embedded images, a video plus its description page) become multiple artifact records, related through cross-references in their normalized bodies.

### 4.2 Normalize

Normalization transforms an artifact stub into a complete, useful markdown record. It has three sub-steps: **conversion** (deterministic), **cross-reference resolution** (deterministic), and **contextualization** (LLM-driven).

#### 4.2.1 Conversion

**What:** Deterministic conversion of artifact bytes into a markdown body.

**How:** MIME-driven, schema-guided. The base schema for the artifact's `content_type` selects the conversion path: extraction (HTML→markdown, PDF→text), transcription (audio/video→text), description (image→text via VLM), or metadata summary (opaque binaries).

**Output:** The artifact record's body is filled with the artifact's content as well-formed markdown. `status` set to `draft`. `normalization_type` set to the method used.

#### 4.2.2 Cross-reference resolution

After producing the normalized body, the normalizer checks all hyperlinks and embedded resource references against the corpus's blake3 index. Targets that match a captured artifact are rewritten as blake3 wikilinks or embeds. Targets with no match remain as standard markdown URLs. This is a mechanical resolution, not an editorial judgment — the normalizer does not add links that didn't exist in the original content.

Re-normalization passes can re-run cross-reference resolution as new artifacts are captured, turning previously unresolved URLs into wikilinks and embeds without altering anything else in the body.

#### 4.2.3 Contextualization

**What:** LLM-driven refinement of the body, informed by base schema guidance, custom classification schema matches, and any tag vocabulary conventions the corpus declares.

**How:** The normalizer loads the record, the matching base schema, and any custom classification schemas whose match conditions apply. It refines the body, fills extended fields, applies matching custom classification schemas (recording each application in the artifact's `classifications:` array as `{schema, justification}`), generates or refines `description`, and surfaces issues. For artifact records the body MUST remain a faithful normalized rendering — contextualization may improve accuracy but MUST NOT add information.

**Schema composition.** Base schema fields are extracted first. Matching custom classification schemas add their tags and extended fields, merging into the record (last-write-wins on field collisions). Multiple custom schemas may match.

**Output:** Record with refined body, extended fields populated, and `status: normalized`.

### 4.3 Author

**What:** Create or edit a codex record (in a codex) or a compendium record (in a compendium) that synthesizes knowledge across one or more artifacts and other records.

**Outputs of an authoring pass (codex side):** A codex record with a UUID, optional slug (the codex topic), title, description, tags, quality fields, and a body composed of authored markdown prose. The body cites artifacts via wikilinks (`[[blake3|text]]`), embeds artifact content where it pays off (`![[blake3]]`), uses functional URIs for computed transformations (`![[blake3://hash?params|alt text]]`), links to peer records in the same codex (`[[slug|text]]` or `[[uuid|text]]`), and applies tags in frontmatter.

A codex record's body never contains `[[codex-name:…]]` — codices stay pure (§2.5). Cross-codex citation belongs in compendium-record bodies (§6).

There is no merge ceremony, no constituent list, no merge rationale field. The body *is* the synthesis; the references in the body are the structural relationships.

**Authoring is non-destructive.** Referenced artifacts and other records are unchanged and independently addressable. Removing a reference from a codex-record body simply removes that reference — no cascade, no mutation of the target.

**Codex records may be authored in layers within a codex.** A specific subject's how-to record may be referenced by a higher-level overview record, which is in turn referenced by a top-level entry record. Each level adds context. The link graph (within the codex) is the hierarchy.

### 4.4 Re-normalize

**What:** Re-run normalization on existing artifact records, taking advantage of newly available context (newly captured artifacts that resolve previously unresolved cross-references), tooling improvements (better extraction, better OCR, better transcription), or model upgrades.

**When:**

- A previously unresolved cross-reference now has a captured target.
- A schema (base or classification) has been improved.
- The normalization model has been upgraded.
- An artifact has known issues that re-processing might resolve.

**How:** On-demand, triggered by the operator or Curator. Re-normalization MAY rewrite the body but MUST preserve normalization integrity — the new body remains a faithful rendering of the original artifact. Cross-reference resolution is re-run automatically.

**Re-normalization is optional.** Many artifacts will never be re-normalized — the initial normalization is sufficient. The capability exists for cases where new context or improved tooling meaningfully improves accuracy.

### 4.5 Build

**What:** Materialize the corpus into a browsable or publishable form.

**How:** A build process reads the corpus and produces output suitable for consumption (static site, browsable vault, mdbook, or other format).

**Steps:**

1. Resolve all wikilinks and embeds (artifact↔artifact, codex-record↔artifact, codex-record↔codex-record, compendium-record↔codex-record, compendium-record↔artifact) to whatever the target format expects (file paths, anchored URLs, inlined content).
2. Resolve all functional URIs in codex- and compendium-record bodies — compute transformations, write derived artifacts to the build's output directory, substitute paths.
3. Generate index and navigation structures appropriate to the output format (tag indexes, slug routes, backlink panels).

**Origin-URL routing.** The build process can generate a lookup index mapping any `uris[]` value to its artifact blake3 hash, enabling consumers to find records by any of the URLs known to resolve to them.

Build is an implementation detail — this spec defines what the corpus contains, not how it's published.

### 4.6 Phase Boundaries and Re-processing

Pipeline steps are independently re-runnable:

| Operation | Scope | Trigger |
|-----------|-------|---------|
| **Re-capture** | One artifact (new bytes → new record) | Upstream content has changed |
| **Re-convert** | Artifacts by `conversion_tool` version | Conversion tools improved |
| **Re-resolve cross-references** | Any artifact body | New artifacts captured |
| **Re-contextualize** | Records by `normalization_model` | LLM models improved |
| **Re-author a codex record** | One codex record | Knowledge updated; new artifacts available |
| **Rebuild similarity caches** | Tier 2/3 indices | Model upgrades; index drift |

Each operation can target specific records via metadata queries. The `conversion_tool`, `normalization_model`, and `normalization_date` fields enable precise targeting.

---

## 5. Pipeline Agents

### 5.1 Overview

The pipeline is operated by specialized agents — lightweight, single-purpose workers that each handle one item per invocation. Agents have focused responsibilities, process exactly one item, and report results to a coordinator. There is no inter-agent communication and no shared state beyond the corpus filesystem.

Agents consult base schemas and any custom classification schemas under `schema/` to apply consistent normalization and classification per content type.

### 5.2 Capturer

Brings a single content item into the corpus.

**Model class:** Haiku-tier (fast, cheap — no creative judgment needed).

**Scope:** One content item per invocation.

**Output contract:** When the capturer finishes successfully, the artifact record for the captured bytes exists (newly created or augmented with this capture's provenance), and the binary lives in the content-addressed store keyed by its blake3 hash. The artifact's MIME has been determined, and every hash declared by its base schema has been computed and recorded. The capturer reports whether the record is new or existing, plus any warnings.

The capturer is a reliable executor, not a decision maker — it does not choose what to capture or how to classify content. The procedural details (fetch tooling, MIME-detect ordering, in-memory vs on-disk staging) live in `impl-corpus.md`.

### 5.3 Normalizer

Brings an artifact stub to `status: normalized`.

**Model class:** Sonnet-tier (creative judgment required for contextualization, issue surfacing, description generation).

**Scope:** One artifact per invocation.

**Output contract:** When the normalizer finishes successfully, the artifact record carries a faithful normalized markdown body, every base-schema-declared field that can be extracted, every field declared by any custom classification schema whose match conditions are satisfied, the resulting tags, a `normalization_type` reflecting how the body was derived, a `classifications:` array entry for every custom classification schema that was applied (each with a required `justification`), a refined `description`, and `status: normalized`. Any hyperlink or embed in the original content whose target exists in the corpus has been rewritten as a blake3 wikilink or embed; targets that don't exist in the corpus remain as plain URLs. The normalizer never invents links the original content didn't contain.

Self-verification responsibilities: the artifact's `content_type` must match the MIME of the stored binary, and the `blake3` field must match the binary's hash.

The split between deterministic (conversion, cross-reference resolution, schema-driven extraction) and LLM-driven (contextual refinement, description, classification-schema match where the conditions require interpretation) is described in §5.7. Procedural detail lives in `impl-corpus.md`.

### 5.4 Author

Creates or edits codex records in a codex (or compendium records in a compendium).

**Model class:** Sonnet-tier (semantic judgment required for synthesis).

**Scope:** One record per invocation, in one container.

**Output contract:** When the author finishes successfully, a codex record exists in the target codex with a UUID, optional slug (the codex topic), title, description, tags, quality fields, and a body composed of authored markdown prose. The body cites artifacts via wikilinks, embeds artifact content where useful, may use functional URIs for computed transformations of artifact content, and links to peer records in the same codex. Backlinks and related-record candidates within the codex are surfaced for follow-up. When the author writes a codex record, it writes nothing outside the target codex; cross-codex synthesis is a compendium-record authoring job (§6), not a codex-record authoring job.

### 5.5 Curator

Autonomous orchestration skill that assesses corpus state, prioritizes work, and dispatches agents. Also responsible for the schema-feedback loop (§3.3.3) — monitoring the codex layer for emerging patterns and proposing new custom classification schemas to the operator.

**Operating loop:**

1. **Assess.** Scan loaded corpora's `records/` and any active codex's `records/` for record statuses (`stub`, `draft`, `normalized`), unresolved issues, unresolved cross-references, and authoring opportunities. Check the corpus's `capture/` for completed captures awaiting reconciliation. Watch the codex layer for recurring patterns (tag clusters, URI-domain frequency, repeated extended-field demand) that might warrant a new custom classification schema in the corpus.
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

Compendiums select records and codex topics from one or more codices and corpora and synthesize them into chapters organized by a domain taxonomy:

1. **Select inputs.** Using tags, codex-topic slugs, descriptions, and tier-3 body-embedding similarity, identify the codices, codex topics, and artifacts relevant to the compendium's domain. Codex topics are preferred when they exist (someone has already done the synthesis); raw artifacts are cited directly when the compendium needs primary-source precision.
2. **Organize by taxonomy.** Group selected inputs by the compendium's chapter structure.
3. **Synthesize chapters.** Distill grouped inputs into coherent prose, reconciling conflicts, identifying patterns, and citing identifiers per the reference stability hierarchy (§6.3). Functional URIs may be used to cite specific pages, frames, or crops of artifacts.
4. **Build navigation.** Generate cross-references and supplementary sections (FAQ, glossary, quick reference).

**Compendium body references.** Inside a compendium body, wikilinks may use:

- `[[blake3]]` or `![[blake3]]` — any artifact in any loaded corpus.
- `[[corpus-name:blake3]]` — disambiguation form when the artifact's provenance matters.
- `[[codex-name:slug]]` — a codex topic (preferred form for codex citations).
- `[[codex-name:uuid]]` — a specific authored codex record instance (discouraged; orphans across codex regeneration).
- `![[blake3://hash?params]]` — functional URI for a derived view of artifact content.

**Anonymized examples.**
- A user's personal compendium for a specific subject draws from their *private* corpus (personal records, history) AND *public* corpora (manuals, advisories) for context. It cites codex topics from the user's personal codex and artifacts from both corpora.
- A general compendium for the same subject category draws only from *public* corpora and from any general-purpose codex that synthesizes the public material. The personal corpus is not in scope.

### 6.3 Synthesis Principles

- **Reference stability hierarchy.** Prefer the lowest level of reference that suffices: artifact (`[[blake3]]`) is always stable across regeneration; a codex topic by slug (`[[codex-name:slug]]`) is stable across codex regeneration that preserves topic naming; a codex doc UUID is bound to a specific instance and may orphan. Compendiums that cite slugs survive their codices being rebuilt; compendiums that cite UUIDs are tied to a specific codex instance.
- **Cite records.** Every factual claim references the identifier(s) it derives from. Use functional URIs when citing specific pages, frames, or crops where precision matters.
- **Represent disagreement.** When sources conflict, the compendium presents both positions with whatever credibility-signal classifications they carry (see §3.3.2). Where the corpus expresses no credibility signals, surface the disagreement neutrally and let the reader judge.
- **Aggregate patterns.** If many artifacts describe the same phenomenon, the compendium captures the pattern (common conditions, symptoms, root cause) rather than citing each artifact individually.
- **Weight by credibility signals.** Records carrying classifications the compendium treats as authoritative (e.g., `peer-reviewed`, `community-validated`) carry more weight in synthesis than records carrying classifications it treats as weaker (e.g., `preprint`, `anecdotal-claim`, `corporate-bias`). The specific weighting is a compendium-author choice — different compendiums on the same domain may weight the same signals differently. The synthesis system prompt (§6.4) is the natural place to encode the compendium's weighting policy.
- **Respect issues.** Records with unresolved `critical` or `major` issues should be weighted accordingly and gaps noted.
- **Leverage codex topics and tags.** Codex topics are the strongest input — a well-authored codex doc already encodes synthesis a compendium chapter wants. Compendium chapters typically start by selecting a small set of seed topics from one or more codices and following their references outward into the underlying corpora.
- **Leverage similarity.** Tier-3 body embeddings surface cross-modal connections (an audio transcript and an HTML article on the same topic) that tags alone may miss.

### 6.4 System Prompts

Each compendium has a **synthesis system prompt** — a document encoding domain-specific knowledge: scope boundaries, key relationships, codex/corpus selection criteria, and synthesis guidelines.

System prompts are iterable. When synthesis produces gaps or errors, the system prompt is refined and synthesis is re-run: **synthesize → review → refine prompt → re-synthesize**.

### 6.5 Incremental Re-synthesis

Compendiums track which inputs were used to produce each chapter — codex topics by slug, artifacts by blake3, with the relevant timestamps. When an artifact is re-normalized, a codex doc is re-authored, or a codex is regenerated, only affected chapters need re-synthesis.

**Codex regeneration is regen-safe for compendiums that cite slugs.** A regenerated codex preserves its topic slugs (§2.5); compendium references that targeted those slugs continue to resolve. Compendium references that targeted codex UUIDs may orphan and require manual repair — which is why slug citations are the canonical form.

A record or topic that has been updated triggers re-synthesis only in chapters that cite it. This keeps re-synthesis proportional to actual content change.

---

## Appendix A: MIME Reference

This appendix is a concise overview of MIME types commonly encountered in practice. The authoritative source for normalization guidance per MIME is the base schema in `schema/base/`. Extended fields beyond `content_type` are extracted by base schemas (format-intrinsic) and custom classification schemas (corpus-local, optional, domain-specific).

Any IANA-registered MIME is valid as a `content_type` value. `unknown` is permitted as a sentinel.

### A.1 Common artifact MIMEs

| MIME | Method | Typical extended fields | Notes |
|------|--------|------------------------|-------|
| `text/html`, `application/xhtml+xml` | extraction | `page_title`, `meta_description`, `canonical_url`, `og_title`, `og_description`, `og_image`, `og_type`, `language` | Strip navigation, chrome, advertising. Preserve primary content, headings, tables, code blocks. The largest MIME by volume in most corpora. |
| `application/pdf` | extraction | `page_count`, `pdf_author`, `pdf_title`, `pdf_creation_date`, `pdf_producer`, `is_scanned` | Extract text and tables. OCR if scanned. Page boundaries surface as section anchors usable from functional URIs. |
| `application/epub+zip` | extraction | `work_title`, `epub_author`, `language`, `chapter_count`, `word_count` | Parse chapter structure; one heading per chapter. Internal links resolve via cross-reference resolution if other captures match. |
| `text/markdown`, `text/plain` | extraction (passthrough) | `word_count`, `language` | Minimal cleanup. `conversion_method: "passthrough"`. |
| `video/mp4`, `video/webm`, `video/mkv`, `video/quicktime` | transcription | `duration_seconds`, `width_px`, `height_px`, `frame_rate`, `video_codec`, `audio_codec` | Transcribe audio with timestamps. Frame descriptions per schema guidance. |
| `audio/mpeg`, `audio/flac`, `audio/wav`, `audio/ogg` | transcription | `duration_seconds`, `bitrate_kbps`, `sample_rate_hz`, `channels` | Transcribe with timestamps. Speaker turn markers where determinable. ID3-tagged audio that a corpus-local custom classification schema recognizes as musical recordings gains `artist`, `track_title`, `album`, `track_number`. |
| `image/jpeg`, `image/png`, `image/webp`, `image/gif` | description | `width_px`, `height_px`, `color_space`, `exif_date`, `exif_gps_lat`, `exif_gps_lon`, `exif_camera` | Visual description and OCR text in body. Embedded in artifact bodies via `![[blake3]]`; embedded in codex- or compendium-record bodies via plain embed or functional URI. |
| `message/rfc822` | extraction | `from`, `to`, `subject`, `message_date`, `in_reply_to` | Body is the message text; headers extracted to extended fields. Multipart bodies flatten to text/plain or text/html as primary. |
| `application/json` | extraction (passthrough) | `top_level_keys` | Prettify; preserve structure. |
| `unknown` | metadata | `byte_size`, `magic_bytes_summary` | Best-effort fallback. Record the gap in `issues[]`. |

### A.2 Classification examples

A corpus typically authors custom classification schemas to recognize content patterns it cares about. Examples of content-pattern schemas:

- **Forum threads** — text/html on a known forum domain → `add_tags: [forum-thread]`, extended fields `username`, `thread_url`, `reply_count`.
- **Voting-community threads** — text/html on aggregator-style platforms → `community_slug`, `post_url`, `score`, `comment_count`.
- **Web articles** — text/html on publisher domains → `article_url`, `publication`, `byline`.
- **Service manuals** — application/pdf with publisher metadata matching a manual pattern → `service_section`, `vehicle_platform`, `manufacturer`.
- **Musical recordings** — audio/* with populated ID3 artist/album → `artist`, `track_title`, `album`, `track_number`.

Credibility signals are also custom classifications — each signal is its own narrow schema. There is no universal credibility scheme; corpora invent their own vocabulary as patterns emerge. Some illustrative examples:

```yaml
# schema/classification/peer-reviewed.yaml
schema_type: classification
match:
  content_type: "application/pdf"
  uri_pattern: "^https?://(www\\.sciencedirect|link\\.springer|onlinelibrary\\.wiley|nature)\\.com/"
classification:
  add_tags: [peer-reviewed]
```

```yaml
# schema/classification/preprint.yaml
schema_type: classification
match:
  content_type: "application/pdf"
  uri_pattern: "^https?://(arxiv\\.org|biorxiv\\.org|medrxiv\\.org)/"
classification:
  add_tags: [preprint]
```

```yaml
# schema/classification/corporate-bias.yaml
schema_type: classification
match:
  content_type: "*"
  # LLM judgment: matches when contextualization recognizes
  # promotional / corporate-PR framing in the content.
classification:
  add_tags: [corporate-bias]
```

```yaml
# schema/classification/community-validated.yaml
schema_type: classification
match:
  has_tags: [forum-thread]
  # LLM judgment: applies when thread shows clear consensus
  # across multiple independent users and no dissent.
classification:
  add_tags: [community-validated]
```

```yaml
# schema/classification/anecdotal-claim.yaml
schema_type: classification
match:
  has_tags: [forum-thread]
  # LLM judgment: applies when content is a single user's
  # unconfirmed experience report.
classification:
  add_tags: [anecdotal-claim]
```

Different corpora carry different credibility vocabularies. A research-paper corpus might add `retracted`, `predatory-journal`, `industry-funded`. A forum corpus might add `op-claim`, `consensus-supported`, `disputed`. A news corpus might add `wire-service`, `op-ed`, `sponsored-content`. The vocabulary evolves as the curator notices what kinds of credibility distinctions actually matter for the corpus's downstream synthesis use cases — the §3.3.3 schema-feedback loop applies to credibility signals like any other custom classification.

Custom classification schemas are corpus-local and optional. The same MIME can carry different custom classifications across corpora. Unclassified artifacts are fully valid — the base schema fields are sufficient on their own.

### A.3 When to author a codex record

A rule of thumb: when multiple artifacts share strong tag overlap and would benefit from synthesized prose, author a codex record. Examples where authored records pay off:

- Multiple artifacts about the same album → an album record in a music-focused codex that synthesizes across the metadata page, the audio, and reviews.
- Many artifacts about products in a line → a product-line record that summarizes shared attributes and links to per-product records in the same codex.
- Recurring abstract categories (Review, Analysis, Explainer) → category records within a codex that cut across the codex's domain via cross-record wikilinks.

Cross-codex synthesis is not a codex's job — when multiple codices need to come together, that's a compendium (§6).

Codex records (and their codex topics) are cheap to create and cheap to retire. Do not over-plan. Start with the syntheses that the corpus's actual usage makes valuable, and let the codex graph grow organically.
