---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 10.3
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-04-26
changelog:
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

The Athenaeum is a knowledge normalization and synthesis system. It captures content from external sources, normalizes each captured file into a uniform markdown representation, and supports authoring documents that synthesize knowledge across many captured files.

The system has two sharply separated layers within the corpus:

- **The artifact layer.** Content-addressed records, one per captured file, named by the blake3 hash of the file's binary content. Each artifact's body is a faithful normalized rendering of the original content. Cross-references in the original (hyperlinks, embedded images) are resolved to blake3 wikilinks and embeds where the targets exist in the corpus. The artifact layer is the ground truth — it preserves what was captured, exactly as it was.

- **The document layer.** Authored markdown compositions, named by UUID. Document bodies have full editorial freedom: they reference artifacts as evidence, embed artifact content inline, and connect to other documents through wikilinks and tags. Documents are where synthesized, opinionated, contextualized knowledge lives.

Above the corpus sits the **compendium layer** — curated reference works synthesized from selected records, organized by a domain taxonomy and shaped by an editorial point of view.

### 1.2 Design Principles

1. **Every record is independently valid.** A single captured page and a fully synthesized monograph are both complete, addressable, useful markdown documents.

2. **Artifact immutability via content addressing.** Captured artifacts are identified by the blake3 hash of their binary content. The bytes never change; if they did, the hash would change and the record would be a different record. Re-encountering the same bytes appends a new entry to the existing record's `capture_dates` rather than creating a new record.

3. **Normalization integrity.** An artifact's body is a faithful normalized rendering of its original content. Normalization may produce a more accurate representation (resolve encoding ambiguity, fix format-conversion artifacts, surface OCR text from images) but it MUST NOT add information that didn't exist in the original. Editorial work happens in documents, not in artifacts.

4. **The normalized body as universal representation.** Every artifact record carries a text body: a normalized rendering of the original file appropriate to its content type. This body projects all modalities into a common representational space — text — enabling universal computation across the corpus. Search, similarity, clustering, and embeddings all operate on this body. The body is the durable, auditable, git-versioned input; everything derived from it is ephemeral cache, rebuildable when models improve or normalization is refined.

5. **Compositional structure lives in the body.** Documents express composition through their prose: wikilinks, embeds, and tags. There is no stored frontmatter "constituents," "part_of," "is_a," or "same_as." The link graph itself is the hierarchy. Equivalence is computed from intrinsic properties, not asserted.

6. **Metadata-driven organization.** Classification, grouping, and discovery are tag and link operations, not filesystem operations. Reorganizing the corpus means editing references, never moving or renaming files.

7. **Stable identity.** An artifact's blake3 hash never changes (the bytes are immutable). A document's UUID never changes. References are permanent.

8. **LLM-native.** The pipeline leverages LLM capabilities for semantic tasks (normalization, cross-reference resolution, document authoring) while keeping mechanical tasks (capture, hashing, format conversion, functional URI evaluation) deterministic and reproducible.

9. **Offline-first.** Only capture requires network access. Everything else operates on local data — including normalization (when the local model is sufficient), document authoring, similarity, and compendium synthesis.

### 1.3 Terminology

| Term | Definition |
|------|-----------|
| **Record** | The universal unit. A markdown file with YAML frontmatter and a normalized or authored body. Either an artifact or a document. |
| **Artifact Record** | A record representing a single captured file, named by the blake3 hash of its binary content (`{blake3-hash}.md`). One record per file, one content type per record. The body is a normalized text rendering of the artifact. The actual binary file is stored in content-addressed storage indexed by the same hash. Artifact records are the ground truth of the corpus. |
| **Document Record** | A record representing authored knowledge, named by a UUID (`{uuid}.md`). The body is a markdown composition that references artifacts (as evidence) and other documents (as cross-references). Documents are where editorial work lives. |
| **Content-Addressed Naming** | Artifact records are named by the blake3 hash of their binary content. Byte-identical files produce the same hash and therefore the same record — structural deduplication is automatic. Document records continue to use UUID-based naming. |
| **Blake3** | The 256-bit content hash that identifies an artifact record and its underlying binary. 64-character lowercase hex string. Functions as identity, filename stem, and content-addressed storage key. |
| **UUID** | Universally unique identifier for a document record (v4, RFC 9562). Stable and permanent. Not used on artifact records. |
| **Reference** | A wikilink or embed in a record's body that points to another record by blake3 hash (artifacts) or UUID/slug (documents). References are the primary mechanism for expressing relationships between records. They live in the body, not in frontmatter, and are visible in Obsidian's graph and backlink views. |
| **Wikilink** | `[[target\|display]]` — a clickable cross-reference. Targets are blake3 hashes (for artifacts) or document UUIDs/slugs. The display text is optional; without it the target identifier is shown. |
| **Embed** | `![[target]]` — inline content inclusion. Renders the target's normalized body at that position. For images, this surfaces the text description; in compiled outputs the actual binary can be substituted. |
| **Tag** | A flat, kebab-case classification label matching `[a-z0-9]+(-[a-z0-9]+)*`. Tags are corpus-local — they require no external concept document to function. |
| **Slug** | An optional, corpus-unique, human-readable identifier for a record (`[a-z0-9]+(-[a-z0-9]+)*`). Enables readable wikilinks: `[[brake-bleeding\|Brake Bleeding Procedure]]` instead of `[[a1b2c3d4-…\|Brake Bleeding Procedure]]`. |
| **Capture** | An encounter event recorded only by date. Re-encountering identical bytes appends a new entry to the artifact's `capture_dates`; the bytes themselves never move and never produce a new record. |
| **Normalization** | Producing the artifact's text body — extraction (HTML→markdown, PDF→text), transcription (audio/video→text), description (image→text), or metadata summary (opaque binary). Faithful to the original; no editorialization beyond inline topic annotations. |
| **Functional URI** | A composable URI scheme (`blake3://{hash}?page=4&crop=…`) used in document bodies to reference deterministic transformations of artifact content. Document-layer only. Resolved at compile/render time. |
| **Schema** | A reference document describing how to normalize or classify content. Two kinds: **base schemas** (MIME-type-keyed, universal, foundational data contract) and **custom classification schemas** (corpus-local, optional, corpus-author-driven). |
| **Compendium** | A curated synthesis of records into a domain-specific reference work. |

---

## 2. Core Model

### 2.1 Records

A **record** is the universal unit of the Athenaeum. Every record is a single markdown file with YAML frontmatter and a body. Records are one of two kinds:

- **Artifact records** (`record_type: artifact`) — one per captured file, named by the blake3 hash of the binary content. The body is a normalized text rendering of the original content.

- **Document records** (`record_type: document`) — authored compositions, named by UUID v4. The body is markdown prose with wikilinks and embeds referencing other records.

A corpus contains the following top-level directories:

```
corpus/
├── artifacts/   — artifact records (content-addressed by blake3)
├── documents/   — document records (UUID-named)
├── binary/      — content-addressed binary store, keyed by blake3
├── capture/     — staging area for in-progress captures
└── schema/      — base and custom classification schemas (see §3.3)
```

**Directory purposes:**

- **`artifacts/`** — Artifact records, content-addressed by the blake3 hash of the underlying binary. Concrete on-disk layout (e.g., sharding) is an implementation concern; the only invariant is that an artifact record is locatable by its blake3 hash.
- **`documents/`** — Document records, identified by UUID.
- **`binary/`** — Content-addressed binary store. Each captured file is locatable by its blake3 hash; concrete layout is an implementation concern.
- **`capture/`** — Staging area for in-progress captures. No identity assigned yet. Failed captures remain here without consuming corpus resources.
- **`schema/`** — Schemas governing normalization and classification (see §3.3).

There is no nesting beyond the top-level separation. Organization is expressed through tags, wikilinks, embeds, and computed similarity — not through directory hierarchy. Concrete on-disk paths and sharding conventions live in the implementation guide (`impl-corpus.md`).

### 2.2 Artifacts

An artifact record represents a single captured file. It is named by the blake3 hash of the file's binary content (`{blake3-hash}.md`) and contains:

- **Frontmatter:** `content_type` (MIME type), `uris[]` (all known URIs that resolve to this artifact, none canonical), `capture_dates[]` (timestamps these bytes were encountered), schema-extracted extended fields, and standard metadata fields.

- **Body:** A normalized markdown rendering of the artifact, faithful to the original content's structure and meaning. For HTML: stripped-and-cleaned markdown preserving document structure. For audio: a transcript. For images: OCR text and/or visual description. For PDFs: extracted text with structural markup. Cross-references in the original content (hyperlinks, embedded images) are resolved to blake3 wikilinks and embeds where the targets exist in the corpus, preserving the original content's link structure. See §3.2 for body format rules.

- **Binary storage:** The actual file is stored in the content-addressed binary store under `binary/`, retrievable by the same blake3 hash.

**Content-addressed deduplication.** If the same file is encountered again, the hash matches an existing record. No new record is created — the existing record gains a new `capture_dates` entry, and any URI not already in `uris[]` is appended. Git sees a metadata-only diff.

**Re-capture of changed content.** If a previously captured URL returns different content, the new content produces a different hash and therefore a new artifact record. Both records will list the URL in their `uris[]`, making them discoverable as captures of the same origin URL at different points in time. Cross-URI succession (the same content at a new URL) has no automatic mechanism in v10.

**Record type.** Artifact records use `record_type: artifact`.

### 2.3 Documents

A document record is an authored markdown composition representing synthesized knowledge. It is named by a UUID (`{uuid}.md`) and contains:

- **Frontmatter:** `uuid`, `title`, `tags` (classification), and minimal metadata. Document frontmatter is deliberately thin — structural relationships live in the body.

- **Body:** Authored markdown prose with wikilinks to other documents, wikilinks and embeds referencing artifacts (by blake3 hash), and optionally functional URIs for computed transformations of artifact content. The body *is* the composition — it is the authoritative record of what knowledge the document synthesizes and what evidence it draws on.

Documents connect to other documents through wikilinks and tags. Documents reference artifacts through wikilinks (for citation/evidence) and embeds (for inline content inclusion). The reference direction is always document → artifact for evidence, and document ↔ document for knowledge structure.

**Documents are where editorial work lives.** Unlike artifact bodies (which faithfully mirror their original content), document bodies are written by curators or synthesis agents. Documents may add interpretation, analysis, and context that no single artifact contains; structure knowledge for a particular audience or purpose; reconcile disagreements across artifacts; and carry the editorial voice that artifacts intentionally lack.

**Record type.** Document records use `record_type: document`.

### 2.4 The Document Graph

Composition is expressed through references in document bodies — there is no stored "constituents" list, no `part_of` field, no merge DAG metadata. The link graph itself is the hierarchy.

```
[[artifact a7f3…]]   ──┐
                       ├──►  [[doc song-meridian]]   ──┐
[[artifact e5f6…]]   ──┘                               │
                                                       ├──►  [[doc album-convergence]]  ──►  [[doc artist-celestial]]
[[artifact i9j0…]]   ──┐                               │
                       ├──►  [[doc song-tidal]]      ──┘
[[artifact o5p6…]]   ──┘
```

Each arrow is a wikilink or embed appearing in the body of the referencing record. The "Album: Convergence" document mentions and links to its track documents and the artist; each track document mentions and links to the artifacts it synthesizes from. Reading the body reveals the structure; no separate metadata block restates it.

**Properties:**

- **Composition is implicit.** Following wikilinks reconstructs the structure. There is no canonical "tree" — documents may have many parents and many children.
- **Acyclic by convention.** Cycles are technically possible (a document linking to a document that links back) but conventionally avoided in compositional structures. Cross-references between peer documents (sibling links) are fine and frequently desirable.
- **Non-destructive.** Authoring a parent document does not modify or consume its referenced children. The references are pointers; the targets remain independent.
- **Multi-parent.** A single artifact or document may be referenced by many documents. An interview transcript artifact might be cited by both an artist-profile document and a documentary-film document.
- **Reference direction.** Documents reference artifacts (citation/evidence). Documents reference other documents (knowledge structure, prerequisites, see-also). Artifacts reference other artifacts only when the original content's cross-references resolve to captured targets (see §3.2). Artifacts never reference documents — artifact bodies are faithful to original content, which had no knowledge of corpus documents.

### 2.5 Re-normalization Context Flow

Normalization is on-demand, not a one-time event. A given artifact may be re-normalized when:

- New artifacts are captured whose presence resolves previously unresolved cross-references (turning external URLs into blake3 wikilinks).
- The normalization model is upgraded.
- Schema guidance for the artifact's MIME type is improved.
- A bulk re-normalization sweep is triggered by tooling improvements.

Re-normalization MUST preserve normalization integrity — the new body remains faithful to the original artifact's content. It may produce a more accurate representation, but it MUST NOT introduce information not present in the original. Editorial enrichment that draws on context outside the artifact belongs in document bodies, not in artifact bodies.

Document bodies are re-authored, not re-normalized. They are edited by humans or synthesis agents like any other authored markdown.

### 2.6 Every Record Is a Valid Document

There is no "incomplete" state in terms of record validity. A freshly captured artifact whose body has been normalized is a complete, useful markdown document. An authored document whose body cites a single artifact is a complete, useful markdown document. The corpus is always in a valid state; any record can be selected for compendium synthesis at any time. Authoring richer documents on top of existing artifacts and documents is enrichment, not a completion requirement.

---

## 3. Record Format

### 3.1 Frontmatter Schema

All record metadata lives in YAML frontmatter at the top of each `.md` file. There are no separate configuration files — the markdown file is the single source of truth for both metadata and content.

The schema library (`schema/`) provides normalization and classification guidance (see §3.3); extended fields beyond the core schema are tolerated freely (see §3.1.7). Appendix A provides a concise per-MIME field reference.

#### 3.1.1 Core Fields

Present on every record (unless noted as record-type-specific).

| Field | Type | Required | Applies to | Description |
|-------|------|----------|------------|-------------|
| `record_type` | enum | yes | both | One of `artifact` or `document`. |
| `blake3` | string | yes (artifacts) | artifact records | The blake3 hash of the artifact's binary content. 64-character lowercase hex string. Serves as the record's identity, filename stem, and content-addressed storage key. |
| `uuid` | UUID | yes (documents) | document records | Standard v4 UUID. Not used on artifact records — artifact identity is the blake3 hash. |
| `slug` | string | no | both (typically documents) | Optional corpus-unique, human-readable identifier. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Used for readable wikilinks. Uniqueness enforced corpus-wide; slug changes require updating all references. |
| `title` | string | yes | both | Short descriptive label. |
| `description` | string | yes | both | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `content_type` | string | yes (artifacts) | artifact records | IANA MIME type of the captured artifact (e.g., `text/html`, `application/pdf`, `image/jpeg`). `unknown` is permitted as a sentinel when the MIME cannot be determined. Document records do not carry `content_type` — they are markdown by construction. |
| `status` | enum | yes | both | Pipeline state: `stub` (captured, no body), `draft` (converted, body filled), `normalized` (LLM-refined, ready for use). Document records typically begin at `draft` since authoring fills the body directly. |
| `visibility` | enum | no | both | Editorial curation layer, independent of `status`. One of `visible` (default when absent), `deranked` (appears in results at lower priority), `hidden` (excluded from default results, still accessible by direct identifier). |
| `tags` | string[] | no | both | Classification tags. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Declare what this record is about or what category it belongs to. Tags are corpus-local — they require no external concept document to function. A corpus MAY define a tag vocabulary in its conventions file for consistency. |

On artifact records, `tags` classify what the captured content is about. They are populated by the normalizer during contextualization and may be refined by curation passes. Frontmatter tags declare whole-record topical coverage; inline comment tags (`%% #tag %%`) provide positional precision (see §3.2).

On document records, `tags` classify what the authored knowledge covers. They are set by the document's author (human or agent).

`visibility` lets a curator retire low-quality records from normal surfaces without deleting them. Use cases: low-content pages caught in a bulk scrape; superseded captures that remain valuable as historical versions; records flagged for further review. Default search and list queries show only `visible` records.

#### 3.1.2 Artifact-Specific Fields

Present only on artifact records (`record_type: artifact`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uris` | string[] | yes (≥1) | All known URIs that resolve to this artifact's bytes. None canonical — request URLs, redirect targets, mirror URLs, DOIs, IPFS CIDs, `file://` paths are all equivalent labels. URIs may be added at any time (e.g., a DOI assigned later, a mirror discovered) and become valid retroactively for the artifact. |
| `capture_dates` | ISO-8601[] | yes (≥1) | Timestamps at which these bytes were encountered. Re-encountering identical bytes appends a new entry. |
| `hashes` | map | no | Per-artifact instances of the cryptographic and perceptual hashes the base schema (§3.3.1) declares for this MIME. blake3 is at the top level (it is the identity); other declared hashes (e.g., `chromaprint`, `phash`, `sha256`) live here. |
| `normalization_type` | enum | no | How the body was derived: `extraction` (HTML→markdown, PDF→text), `transcription` (audio/video→text), `description` (image→text), `metadata` (opaque binary→summary). |
| `author` | string | no | Identifiable person who produced this content. Omit for anonymous content. |
| `date_published` | date | no | When the original content was published. Omit for undated content. |

Example artifact frontmatter fragment:

```yaml
blake3: "a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."
record_type: artifact
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

#### 3.1.3 Document-Specific Fields

Present only on document records (`record_type: document`).

Document frontmatter is deliberately thin. Beyond the core fields (`uuid`, `title`, `description`, `record_type`, `status`, optional `slug`, `visibility`, `tags`) and the common quality and pipeline fields below, documents carry no structural metadata. A document's references to artifacts and other documents are visible in its body as wikilinks and embeds; the body is the authoritative record of what knowledge the document synthesizes and what evidence it draws on.

There is no `constituents` list, no `part_of`, no `same_as`, no `is_a`. All structural relationships are body references or computed similarity (see §3.5).

#### 3.1.4 Quality Fields

Present on every record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `credibility_tier` | enum | yes | Trustworthiness of the content (see table below). |
| `normalization_confidence` | float | yes (artifacts) | `0.0`–`1.0`, quality of the normalization process for this artifact. |
| `normalization_model` | string | no | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`). |
| `normalization_date` | date | no | When normalization was last performed. |

**Credibility tiers:**

| Tier | Description | Examples |
|------|-------------|----------|
| `authoritative` | Official or primary source | OEM service manual, published novel text, peer-reviewed paper |
| `expert` | Credentialed professional with demonstrated expertise | Professional mechanic writeup, published literary criticism |
| `community_validated` | Claim independently confirmed by multiple people | Forum fix confirmed by 5+ users, widely accepted fan analysis |
| `anecdotal` | Single person's unconfirmed experience | One forum post describing a symptom |
| `speculative` | Theory or hypothesis without evidence | Unsubstantiated claim or guess |

Credibility describes the trustworthiness of the content's claims. Normalization confidence describes how accurately the raw artifact was rendered into markdown. A perfectly transcribed video might have high confidence but low credibility. A badly OCR'd service manual might have low confidence but authoritative credibility.

#### 3.1.5 Pipeline Fields

Present on artifact records; optional on document records.

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

The body of a record is the markdown content below the frontmatter closing `---`. The rules differ sharply between artifact bodies and document bodies.

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

When an artifact body contains `![[blake3-hash]]`, Obsidian renders the target artifact's body inline. For an image artifact, this means the image's normalized text (OCR, visual description) appears at the position where the original image was. For a linked document artifact, Obsidian renders the target's full body. In compiled outputs (mdbook, static site), the tooling can substitute the actual binary (render the real image, embed the real video).

The same syntax in document bodies has the same meaning, plus access to functional URIs (§3.7) for computed transformations.

#### 3.2.4 Inline Topic Annotations

Artifact bodies may contain topic annotations in Obsidian-style comment blocks. These are the *only* permitted editorialization in an artifact body — they are metadata annotations classifying what the surrounding content discusses, not additions to the content.

**Syntax:** `%% #slug %%` or `%% #slug-1 #slug-2 %%`

**Scoping rules:**

1. **Frontmatter `tags`** — whole-record scope. Every line is implicitly within these topics.
2. **Annotation on a heading** — section scope. Applies until the next heading of equal or higher level.
3. **Annotation on a line** — passage scope. Applies to that specific line only.

Scopes are additive. Annotate at topical transition points, not on every line.

Document bodies may use the same annotation syntax for the same purpose.

#### 3.2.5 Document Bodies

Document bodies are authored compositions with full editorial freedom. Unlike artifact bodies (which faithfully mirror original content), document bodies are written by curators or synthesis agents. They may:

- Add interpretation, analysis, and context that no single artifact contains.
- Structure knowledge for a particular audience or purpose.
- Reference artifacts as evidence using wikilinks: `[[{blake3-hash}|display text]]`
- Embed artifact content inline: `![[{blake3-hash}]]`
- Use functional URIs for computed transformations: `![[blake3://{hash}?params|alt text]]`
- Link to other documents: `[[{uuid}|display text]]` or `[[slug|display text]]`
- Use tags for topical classification (in frontmatter and optionally inline).

#### 3.2.6 Referencing Artifacts from Documents

Documents reference artifacts in two ways:

- **Wikilinks** (`[[{blake3-hash}|text]]`) — citation-style references. "See the original forum post for details." The reader can click through to the full artifact.

- **Embeds** (`![[{blake3-hash}]]`) — inline content inclusion. The artifact's normalized body renders at that position. For images, this surfaces the text description; in compiled outputs, the actual image can be substituted.

Both create backlinks visible in Obsidian's graph view, making it discoverable which documents draw on which artifacts.

#### 3.2.7 Connecting Documents to Documents

Documents connect to each other through standard Obsidian primitives:

- **Wikilinks** — cross-references between documents. "See also the [[brake-system-overview|Brake System Overview]]."
- **Tags** — shared classification. Documents tagged `#brake-caliper` are discoverable together.
- **Embeds** — inline inclusion of one document's body in another.

There are no stored structural relations (`is_a`, `part_of`). Compositional structure is expressed through the document graph itself: a "Brake System Overview" document that wikilinks to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" documents *is* the compositional structure. The links in the body are the hierarchy.

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

**The feedback loop.** Document authoring (codices, compendiums) reveals patterns. Authors keep reaching for the same metadata about the same kind of content; tag clusters form around recurring topics; a domain dominates a slice of the corpus. The curator notices these patterns and authors a custom classification schema that captures them — declaring the fields the authors keep wanting and the tag that names the pattern. A re-normalization sweep applies the new schema to every existing artifact whose match conditions are satisfied. Subsequent document authoring is now richer because the metadata is already on the artifacts.

This loop is the corpus's classification layer growing in step with its actual usage. A corpus with no document layer yet has only base schemas — and that's fine. A corpus whose document layer is rich and active will grow a substantial custom classification library over time. The schemas, the artifacts, and the documents co-evolve.

The pipeline mechanics of pattern detection, schema authoring, and re-normalization sweeps live in `impl-corpus.md`.

The Curator agent (§5.5) is responsible for monitoring the document layer for pattern emergence and proposing new custom classification schemas to the operator.

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
record_type: artifact
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
tags: [brake-caliper, caliper-rebuild]
credibility_tier: community_validated
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

#### Document Record

```yaml
---
uuid: "a1b2c3d4-e5f6-7a8b-9c0d-e1f2a3b4c5d6"
slug: "brake-caliper-rebuild"
title: "Brake Caliper Rebuild"
description: "Authored guide to rebuilding the front calipers on a sliding-caliper braking system, drawing on the service manual, a community forum thread, and a video walkthrough."
record_type: document
status: draft
visibility: visible
tags: [brake-caliper, caliper-rebuild]
credibility_tier: expert
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

The document uses both plain blake3 wikilinks (for direct artifact references) and functional URIs (for computed transformations like page extraction and framegrabs). Links to other documents use slugs for readability.

### 3.5 Classification

Classification in v10 uses tags, the document graph, and computed similarity — no stored structural relations.

#### 3.5.1 Tags

Tags handle categorical classification. An artifact tagged `brake-caliper` is findable by topic. A document tagged `brake-caliper` and `g8-gt` is discoverable at the intersection. Tags are flat (no hierarchy), portable (no external dependencies), and corpus-local (a tag means whatever the corpus's conventions say it means).

A corpus MAY maintain a conventions file (`schema/tags.md` or similar) listing its tag vocabulary with one-line descriptions. This is guidance, not constraint — unknown tags are valid and signal vocabulary growth.

#### 3.5.2 The Document Graph

The document graph handles structural organization. A "Brake System Overview" document that links to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" documents expresses compositional structure through its body, not through frontmatter relations. The link graph is the hierarchy.

A document representing a concept (a category, a person, a place, a thing) is just a document with descriptive prose. Other documents reference it by wikilink. There is no special "concept document" status — the role is emergent from the graph.

#### 3.5.3 Deduplication and Similarity

Deduplication and similarity are handled entirely through intrinsic properties of artifacts, not through stored relations:

**Tier 1: Blake3 (exact).** Same bytes → same hash → same record. Structural, automatic, zero-cost.

**Tier 2: Perceptual hashes (format-specific, cached).** Same perceptible content, different bytes. pHash/dHash for images, chromaprint for audio, simhash for text/HTML. Computed from the binary artifact. Cached for performance, rebuildable from inputs that are already stored.

**Tier 3: Body embeddings (cross-modal, cached).** The normalized body projects every modality into text. Embeddings of that text enable universal semantic similarity. An audio transcript and an HTML transcript of the same interview land near each other because their normalized text says the same things. Cached, rebuildable, model-upgradeable.

All three tiers produce queries, not stored edges. The spec defines the inputs (binary artifact + normalized body); tooling builds the indices.

### 3.6 Slugs

Slugs provide human-readable addressability for records. Documents need slugs so other documents can wikilink to them by readable name rather than UUID. Artifact records rarely need slugs but can have them for significant, frequently-referenced captures.

A slug is corpus-unique. Slug changes require updating all wikilinks that reference the old slug; tooling SHOULD provide a rename helper that walks the corpus and rewrites references in a single pass.

A wikilink resolves in this order:

1. Exact match against `blake3` (artifact record).
2. Exact match against `uuid` (document record).
3. Exact match against `slug` (any record).
4. Otherwise, an unresolved link — surfaced in tooling as a backlink candidate.

### 3.7 Functional URI Scheme

Documents may reference computed transformations of artifacts using functional URIs. These are only valid in document bodies — artifact bodies use plain blake3 wikilinks and embeds only.

**Base syntax:** `blake3://{hash}` — resolves to the artifact's binary content.

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

**Composition example:** `blake3://{hash}?page=4&crop=50,100,550,400` — extract page 4 from a PDF, then crop to the caliper diagram region. The result is an image.

**Semantics:**

- Functional URIs are **deterministic** — same inputs always produce the same output (the underlying artifact is immutable by content addressing).
- Results are **cacheable** — the cache key is the full URI string. Cache can be blown away and regenerated at any time.
- Results are **ephemeral** — they are not stored as records. They exist at compile/render time.
- Functional URIs are **document-layer only** — artifact bodies never contain them.

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
- An artifact record exists for that blake3 hash. If a record for the hash already existed (the bytes had been captured before), reconciliation appended capture provenance to it rather than creating a duplicate. If no record existed, a new one was created with `record_type: artifact`, `blake3`, `content_type` (the MIME determined for the binary), capture provenance, and `status: stub` (body empty pending normalization).
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

**How:** The normalizer loads the record, the matching base schema, and any custom classification schemas whose match conditions apply. It refines the body, fills extended fields, assesses `credibility_tier`, generates or refines `description`, and surfaces issues. For artifact records the body MUST remain a faithful normalized rendering — contextualization may improve accuracy but MUST NOT add information.

**Schema composition.** Base schema fields are extracted first. Matching custom classification schemas add their tags and extended fields, merging into the record (last-write-wins on field collisions). Multiple custom schemas may match.

**Output:** Record with refined body, extended fields populated, and `status: normalized`.

### 4.3 Author

**What:** Create or edit a document record that synthesizes knowledge across one or more artifacts and other documents.

**Outputs of an authoring pass:** A document record with `record_type: document`, a UUID, optional slug, title, description, tags, quality fields, and a body composed of authored markdown prose. The body cites artifacts via wikilinks (`[[blake3|text]]`), embeds artifact content where it pays off (`![[blake3]]`), uses functional URIs for computed transformations (`![[blake3://hash?params]]`), links to peer documents (`[[uuid-or-slug|text]]`), and applies tags in frontmatter.

There is no merge ceremony, no constituent list, no merge rationale field. The body *is* the synthesis; the references in the body are the structural relationships.

**Authoring is non-destructive.** Referenced artifacts and other documents are unchanged and independently addressable. Removing a reference from a document body simply removes that reference — no cascade, no mutation of the target.

**Documents may be authored in layers.** A specific subject's how-to document may be referenced by a higher-level service-overview document, which is in turn referenced by a system-overview document. Each level adds context. The link graph is the hierarchy.

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

1. Resolve all wikilinks and embeds (artifact↔artifact, document↔artifact, document↔document) to whatever the target format expects (file paths, anchored URLs, inlined content).
2. Resolve all functional URIs in document bodies — compute transformations, write derived artifacts to the build's output directory, substitute paths.
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
| **Re-author a document** | One document | Knowledge updated; new artifacts available |
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

**Output contract:** When the normalizer finishes successfully, the artifact record carries a faithful normalized markdown body, every base-schema-declared field that can be extracted, every field declared by any custom classification schema whose match conditions are satisfied, the resulting tags, a `normalization_type` reflecting how the body was derived, an assessed `credibility_tier`, a refined `description`, and `status: normalized`. Any hyperlink or embed in the original content whose target exists in the corpus has been rewritten as a blake3 wikilink or embed; targets that don't exist in the corpus remain as plain URLs. The normalizer never invents links the original content didn't contain.

Self-verification responsibilities: the artifact's `content_type` must match the MIME of the stored binary, and the `blake3` field must match the binary's hash.

The split between deterministic (conversion, cross-reference resolution, schema-driven extraction) and LLM-driven (contextual refinement, description, credibility judgment) is described in §5.7. Procedural detail lives in `impl-corpus.md`.

### 5.4 Author

Creates or edits document records that synthesize knowledge across artifacts and other documents.

**Model class:** Sonnet-tier (semantic judgment required for synthesis).

**Scope:** One document per invocation.

**Output contract:** When the author finishes successfully, a document record exists with `record_type: document`, a UUID, optional slug, title, description, tags, quality fields, and a body composed of authored markdown prose. The body cites artifacts via wikilinks, embeds artifact content where useful, may use functional URIs for computed transformations, and links to peer documents. Backlinks and related-document candidates are surfaced for follow-up.

### 5.5 Curator

Autonomous orchestration skill that assesses corpus state, prioritizes work, and dispatches agents. Also responsible for the schema-feedback loop (§3.3.3) — monitoring the document layer for emerging patterns and proposing new custom classification schemas to the operator.

**Operating loop:**

1. **Assess.** Scan `artifacts/` and `documents/` for record statuses (`stub`, `draft`, `normalized`), unresolved issues, unresolved cross-references, and authoring opportunities. Check `capture/` for completed captures awaiting reconciliation. Watch the document layer for recurring patterns (tag clusters, URI-domain frequency, repeated extended-field demand) that might warrant a new custom classification schema.
2. **Prioritize.** Apply decision framework: compendium blockers first, then high-priority new captures, then normalization of existing stubs, then re-resolution sweeps, then re-normalization driven by tool/model upgrades or by newly authored custom classification schemas.
3. **Propose.** Present the prioritized work plan to the operator for approval. Surface schema-authoring proposals when patterns warrant them.
4. **Execute.** Spawn capturer, normalizer, and author agents, managing parallelism by launching multiple agents concurrently.
5. **Report.** Summarize results — records captured, normalized, authored, issues encountered, schemas proposed.

### 5.6 Parallelism Model

- The **Curator** (or human operator) decides concurrency based on available resources and rate limits.
- Each agent processes one item. The Curator spawns N agents in parallel for N items.
- Agents do not communicate with each other. They read from and write to the corpus, and the Curator sequences work to avoid conflicts (e.g., not authoring a document whose evidentiary artifacts are still being captured).
- Typical session: spawn 5 capturers in parallel → wait for completion → spawn 5 normalizers for the new stubs → spawn an author for any documents the new artifacts unblock.

### 5.7 Deterministic vs. LLM Boundary

| Operation | Type | Rationale |
|-----------|------|-----------|
| Capture (fetch, hash, store) | Deterministic | Reproducible, scriptable, no judgment needed |
| Reconciliation (dedup check, MIME detection) | Deterministic | Hash comparison + extension/magic-byte sniffing are mechanical |
| Hash computation (blake3, sha256, md5) | Deterministic | Mechanical integrity check |
| Conversion (HTML→MD, PDF→text, OCR, transcription) | Deterministic | Reproducible, tool-specific, no editorial judgment |
| Cross-reference resolution | Deterministic | Mechanical URL→blake3 lookup against the corpus index |
| Contextualization (refine, describe, assess, surface issues) | LLM | Requires semantic understanding and editorial judgment |
| Custom classification schema match | Deterministic (when conditions are mechanical) / LLM (when conditions require interpretation) | Depends on the schema's match condition |
| Document authoring | LLM | Requires synthesis, structure, and editorial decisions |
| Functional URI evaluation (page extract, framegrab, crop) | Deterministic | Reproducible transformations of immutable inputs |
| Build (export, index) | Deterministic | Mechanical, reproducible |

The boundary is clear: **if the operation could produce different valid outputs depending on judgment, it's LLM-driven. If the output is deterministic given the input, it's scripted.** This enables independent re-processing — re-convert with better tools without re-contextualizing, and vice versa.

---

## 6. Compendium Layer

### 6.1 What a Compendium Is

A **compendium** is a curated synthesis of records into a domain-specific reference work. Where the corpus preserves and normalizes captured content faithfully and authors documents that synthesize across captures, compendiums apply a further editorial layer: scope, point of view, and a domain taxonomy.

A compendium is opinionated. Multiple compendiums can draw from the same records and produce different works — an economics compendium and a socialism compendium might both draw on the same academic artifacts, selecting different subsets and synthesizing from different perspectives.

### 6.2 How Compendiums Use Records

Compendiums select records from the corpus and synthesize them into chapters organized by a domain taxonomy:

1. **Select records.** Using descriptions, tags, and tier-3 body-embedding similarity, identify records relevant to the compendium's domain. Document records are preferred because they're already authored synthesis, but artifact records can be cited directly when their content is the primary source.
2. **Organize by taxonomy.** Group selected records by the compendium's chapter structure. The taxonomy follows the domain's natural organization (by vehicle system for automotive, by character/faction/theme for fiction, by theory/era for economics).
3. **Synthesize chapters.** Distill grouped records into coherent prose, reconciling conflicts, identifying patterns, and citing record identifiers (blake3 for artifacts, UUID/slug for documents). Functional URIs may be used to cite specific pages, frames, or crops.
4. **Build navigation.** Generate cross-references and supplementary sections (FAQ, glossary, quick reference).

### 6.3 Synthesis Principles

- **Cite records.** Every factual claim references the identifier(s) it derives from — blake3 for artifacts, UUID or slug for documents. Functional URIs cite specific pages, frames, or crops where precision matters.
- **Represent disagreement.** When records conflict, the compendium presents both positions with their respective credibility tiers rather than silently choosing one.
- **Aggregate patterns.** If 40 forum-thread artifacts describe the same failure mode, the compendium captures the pattern (common mileage range, symptoms, root cause) rather than citing each artifact individually.
- **Respect credibility tiers.** Higher-tier records carry more weight. An `authoritative` document is not overruled by `anecdotal` reports unless the volume and consistency of community experience is overwhelming.
- **Respect issues.** Records with unresolved `critical` or `major` issues should be weighted accordingly and gaps noted.
- **Leverage tags and the document graph.** Tags surface candidate records by topic. The document graph (existing authored documents and their wikilinks) is the strongest input — a well-authored document already encodes the synthesis a chapter needs. Compendium chapters often start by selecting a small set of seed documents and following their references outward.
- **Leverage similarity.** Tier-3 body embeddings surface cross-modal connections (an audio transcript and an HTML article on the same topic) that tags alone may miss.

### 6.4 System Prompts

Each compendium has a **synthesis system prompt** — a document encoding domain-specific knowledge: scope boundaries, key relationships, document selection criteria, and synthesis guidelines.

System prompts are iterable. When synthesis produces gaps or errors, the system prompt is refined and synthesis is re-run: **synthesize → review → refine prompt → re-synthesize**.

### 6.5 Incremental Re-synthesis

Compendiums track which records were used to produce each chapter and the `normalization_date` (for artifacts) or last-edit date (for documents) of each at the time of synthesis. When records are re-normalized, re-authored, or new records are added, only affected chapters need re-synthesis.

A record that has been updated triggers re-synthesis only in chapters that cite it. This keeps re-synthesis proportional to actual content change, not to corpus-wide activity.

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
| `image/jpeg`, `image/png`, `image/webp`, `image/gif` | description | `width_px`, `height_px`, `color_space`, `exif_date`, `exif_gps_lat`, `exif_gps_lon`, `exif_camera` | Visual description and OCR text in body. Embedded in artifact bodies via `![[blake3]]`; embedded in document bodies via plain embed or functional URI. |
| `message/rfc822` | extraction | `from`, `to`, `subject`, `message_date`, `in_reply_to` | Body is the message text; headers extracted to extended fields. Multipart bodies flatten to text/plain or text/html as primary. |
| `application/json` | extraction (passthrough) | `top_level_keys` | Prettify; preserve structure. |
| `unknown` | metadata | `byte_size`, `magic_bytes_summary` | Best-effort fallback. Record the gap in `issues[]`. |

### A.2 Classification examples

A corpus typically authors custom classification schemas to recognize content patterns it cares about. Examples:

- **Forum threads** — text/html on a known forum domain → `add_tags: [forum-thread]`, extended fields `username`, `thread_url`, `reply_count`.
- **Voting-community threads** — text/html on aggregator-style platforms → `community_slug`, `post_url`, `score`, `comment_count`.
- **Web articles** — text/html on publisher domains → `article_url`, `publication`, `byline`.
- **Service manuals** — application/pdf with publisher metadata matching a manual pattern → `service_section`, `vehicle_platform`, `manufacturer`.
- **Musical recordings** — audio/* with populated ID3 artist/album → `artist`, `track_title`, `album`, `track_number`.

Custom classification schemas are corpus-local and optional. The same MIME can carry different custom classifications across corpora. Unclassified artifacts are fully valid — the base schema fields are sufficient on their own.

### A.3 When to author a document on top

A rule of thumb: when multiple artifacts share strong tag overlap and would benefit from synthesized prose, author a document. Examples where authored documents pay off:

- Multiple artifacts about the same album → an album document that synthesizes across the metadata page, the audio, and reviews.
- Many artifacts about products in a line → a product-line document that summarizes shared attributes and links to per-product documents.
- Recurring abstract categories (Review, Analysis, Explainer) → category documents that cut across domains via cross-document wikilinks.

Documents are cheap to create and cheap to retire. Do not over-plan. Start with the syntheses that the corpus's actual usage makes valuable, and let the document graph grow organically.
