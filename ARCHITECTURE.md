---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 9.0
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-04-20
changelog:
  - version: 9.0
    date: 2026-04-20
    summary: "content_type redefined as IANA MIME type. Schema library pivots from per-concept classification to per-MIME normalization guidelines; schemas self-declare applicable MIME types via their own frontmatter. Closed content-type enum removed — classification happens by forward reference to ordinary concept documents. Relations reduced to two flat frontmatter fields (part_of, same_as); Relation struct with per-entry type dropped along with sequel_to/reply_to/references/adaptation_of/supersedes/superseded_by/contradicts. ArtifactRef gains mimetype (required) and primary (optional boolean, one-per-source). New visibility field (visible/deranked/hidden) separates editorial curation from pipeline status. Body tags (Obsidian-style #tag markers) forward-declared as the mechanism for topical aboutness."
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

The Athenaeum is a knowledge normalization and synthesis pipeline. It captures content from arbitrary external sources, normalizes it into a uniform markdown representation, composes related records through merging, and synthesizes domain-specific reference works (compendiums) from the normalized material.

The system has two layers:

- **The corpus layer.** A flat collection of UUID-identified records, each producing exactly one markdown file. Records are either **sources** (captured from a single external origin) or **documents** (merged from other records). Records compose into a directed acyclic graph (DAG) through merging, where each level produces richer output than the level below.

- **The compendium layer.** Curated synthesis of selected records into domain-specific reference works — structured, editorial, and opinionated where the corpus is faithful and objective.

### 1.2 Design Principles

1. **Every record is independently valid.** Whether it's a single captured forum post or a merged multi-source artist profile, every record in the corpus is a complete, addressable, useful markdown document.

2. **Artifact immutability.** Captured artifacts (the raw external files — HTML, PDF, epub, etc.) never change. Normalization produces a new representation; it does not modify the original.

3. **Normalization integrity.** Normalization must never add information that doesn't already exist in the original artifact. Contextualization achieves a more accurate representation of the artifact's content — it may resolve ambiguity, fix formatting, and improve structure, but it must not fabricate or interpolate content. Sources are faithful to their origin. Documents are where the complete picture forms by combining multiple accurate sources.

4. **Compositional merges.** Records compose into richer records without consuming the originals. A song record merged with lyrics and audio metadata produces a new, richer document. The originals remain independently accessible.

5. **Metadata-driven organization.** Classification, grouping, and discovery are metadata operations, not filesystem operations. Moving a record from one category to another means updating a field, not relocating files or remapping IDs.

6. **Stable identity.** A record's UUID never changes regardless of how it's classified, merged, or reorganized. References to a record are permanent.

7. **LLM-native.** The pipeline leverages LLM capabilities for semantic tasks (contextualization, merge candidate discovery, assembly) while keeping mechanical tasks (capture, format conversion) deterministic and reproducible.

8. **Offline-first.** Only capture requires network access. Everything else operates on local data.

### 1.3 Terminology

| Term | Definition |
|------|-----------|
| **Record** | The universal unit. A UUID-identified markdown file. Either a source or a document. |
| **Source** | A record captured from a single external origin. Represents a faithful textual rendering of its artifact(s). |
| **Document** | A record created by merging other records, or authored directly as a concept. Represents a synthesized or conceptual entity. |
| **Artifact** | A raw external file (HTML, PDF, epub, image, audio, etc.) captured from an origin. Stored in `artifacts/{uuid}/`. Immutable. |
| **Asset** | A file used or produced during document normalization — derived from artifacts (frame grabs, transcriptions) or an artifact used directly. Stored in `assets/{uuid}/`. Document-only. |
| **UUID** | Universally unique identifier for a record (v4, RFC 9562). Stable and permanent. |
| **Constituent** | A record that is a direct child of a document record in the merge DAG. |
| **Merge** | The process of creating a document record from existing records about the same subject. |
| **Normalization** | Converting raw captured content into well-formed markdown with structured metadata. Must not add information not present in the original artifact. |
| **Compendium** | A curated synthesis of records into a domain-specific reference work. |
| **Content type** | The IANA MIME type of the record's primary artifact (sources) or `text/markdown` (documents). `unknown` is allowed as a sentinel. |
| **Concept document** | An ordinary document record that represents an abstract idea, category, person, or entity. Other records classify themselves by referencing concept documents via `part_of`. No special schema or flag — just a regular document used as a reference target. |
| **Schema** | A reference document under `schema/` giving normalization guidance for a MIME type or family of MIMEs. Schemas declare the MIME types they handle in their own frontmatter; they describe *how* to produce markdown from a given format, not *what* the record is about. |
| **Relation** | A forward reference in a record's frontmatter to another record. Only two kinds exist: `part_of` (instance-of or membership) and `same_as` (equivalence). |

---

## 2. Core Model

### 2.1 Records

A **record** is the universal unit of the Athenaeum. Every record:

- Has a universally unique identifier (UUID v4)
- Is a single markdown file `{uuid}.md` with YAML frontmatter and normalized content body
- Lives in either `sources/` or `documents/` depending on its type
- Is independently addressable and useful as a standalone document

The corpus is a flat collection of markdown files with supporting directories for artifacts, assets, and schemas:

```
corpus/
├── sources/
│   ├── 7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c.md
│   ├── 8b4e3c2d-5e6f-4a7b-9c0d-1e2f3a4b5c6d.md
│   └── ...
├── documents/
│   ├── 9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e.md
│   └── ...
├── artifacts/
│   ├── 7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c/
│   │   ├── thread.html
│   │   ├── img_001.jpg
│   │   └── img_002.jpg
│   └── ...
├── assets/
│   ├── 9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e/
│   │   ├── frame_001.jpg
│   │   └── transcript.vtt
│   └── ...
├── capture/
│   └── brake-caliper-rebuild.12345/
│       ├── thread.html
│       └── img_001.jpg
└── schema/
    ├── html_content.md
    ├── pdf_content.md
    ├── audio_content.md
    ├── video_content.md
    └── ...
```

**Directory purposes:**

- **`sources/`** — Source records (one markdown file per captured origin)
- **`documents/`** — Document records (merged documents + concept documents, same shape)
- **`artifacts/`** — Raw captured files organized by source UUID. Immutable originals. May be externalized to remote storage.
- **`assets/`** — Derived or referenced files for document records, organized by document UUID. May be externalized to remote storage.
- **`capture/`** — Staging area for in-progress captures. Descriptive folder names, no UUIDs. Failed captures remain here without consuming corpus resources.
- **`schema/`** — MIME-normalization schemas. Each file declares which MIME types it handles in its own frontmatter (`applies_to_mimetypes:`) and provides conversion / contextualization guidance for the pipeline.

No nesting beyond the top-level separation. Organization is expressed through metadata (tags, MIME type, `part_of` references, `same_as` equivalences) and through the merge DAG — not through directory hierarchy.

### 2.2 Sources

**Sources** are records captured from a single external origin — a forum thread, a YouTube video, a PDF document, a web article, a metadata page.

The source's `content_type` is the **IANA MIME type of its primary artifact**: `text/html`, `video/mp4`, `application/pdf`, `audio/mpeg`, and so on. The MIME drives normalization: a matching schema in the schema library (selected by MIME compatibility, not by filename) provides guidance on how to produce a faithful markdown rendition of content in that format. Sources do not carry semantic classifications like "forum post" or "bank statement" — those are expressed separately as `part_of` references to concept documents.

The source record's frontmatter references its artifact files via `artifacts://` URIs (see section 3.1.2) with SHA-256 hashes for integrity verification and `mimetype` per ref for accurate rendering. Exactly one artifact ref SHOULD be marked `primary: true` — it's the artifact the record's MIME-level `content_type` applies to and the default view in consumers. The artifacts themselves live in `artifacts/{uuid}/` and may be externalized to remote storage.

**A source is a faithful representation of its artifact.** Normalization may improve formatting, resolve ambiguity, and fix structural issues, but it must not add information that isn't present in the original artifact. The source record is an accurate markdown rendition of its artifact — nothing more. Any classification beyond "what format is this" is a deferrable enrichment done via forward references after first-pass normalization completes.

### 2.3 Documents

**Documents** are records that either (a) synthesize multiple related records about the same subject through a merge, or (b) represent a standalone concept (an abstract idea, a category, a person, a place, an entity) that other records forward-reference for classification purposes.

A document's `content_type` is almost always `text/markdown` — documents *are* markdown by construction. Their role in the corpus (merged synthesis vs. standalone concept) is a matter of how other records relate to them, not something the document itself declares. A "Song" concept document is ontologically identical to "Convergence (2019 album)" — both are documents with bodies describing their subject. The difference is emergent: hundreds of song-audio source records reference the Song concept document via `part_of`; relatively few records reference the specific album.

Merged documents list their **direct constituent UUIDs** in the `constituents` field. Only direct children — not the full flattened tree. To find all leaf sources, follow the chain through constituent records. Concept documents typically have no `constituents` (they aren't synthesized from other records; they're authored directly), or a short list of the key sources that informed the document's prose.

Documents may reference files via `asset_refs` — either derived files produced during normalization (stored in `assets/{uuid}/`) or artifacts from constituent source records used directly.

**Documents are where editorial work lives.** Unlike sources (which are faithful to a single artifact), documents may synthesize, reconcile disagreements, and draw cross-references. This is the appropriate place for the kind of editorial enrichment that would violate normalization integrity if applied to a source.

### 2.4 The Merge DAG

Records compose into a directed acyclic graph (DAG) through merging. Each merge creates a new document record whose `constituents` field lists its direct children.

```
[lyrics_rym_a1b2]     ──┐
                         ├──► [song_c3d4]  ──┐
[audio_yt_e5f6]        ──┘                   │
                                              ├──► [album_g7h8]  ──► [artist_k1l2]
[lyrics_rym_i9j0]     ──┐                   │
                         ├──► [song_m3n4]  ──┘
[metadata_ma_o5p6]    ──┘
```

**Properties:**

- **Acyclic.** A record cannot be a constituent of itself, directly or indirectly.
- **Direct children only.** Each document's `constituents` lists only its immediate children. The full tree is reconstructable by traversal.
- **Non-destructive.** Merging creates a new record; originals are unmodified and remain independently addressable.
- **Multi-parent.** A single record can be a constituent of multiple document records. An interview transcript might contribute to both an artist document and a documentary film document.

### 2.5 Normalization Context Flow

When a document record is created through merging, its normalization draws on all constituents to produce richer output than any constituent alone.

This context can also flow **downward** to improve the accuracy of source records. A song source from a lyrics website might have an incomplete translation. When that song is merged with an audio transcription source, the album document gains context from both. A subsequent **re-normalization** pass on the original lyrics source can use the audio transcription's context to complete the translation — this is valid because the information already exists in the artifact (the lyrics are there, just ambiguous), and the context helps achieve a more accurate representation.

Re-normalization is on-demand, not automatic. Processing order follows a reverse topological sort — leaves first, then their parent documents, then grandparents — so improvements at lower levels propagate upward through subsequent passes.

### 2.6 Every Record Is a Valid Document

There is no "incomplete" state in terms of document validity. A freshly captured source record that has been normalized is a complete, useful document. Merging makes it *richer*, but the unmerged version is not deficient.

This means:

- The corpus is always in a valid state
- Any record can be selected for compendium synthesis at any time
- Merging is an enrichment operation, not a completion requirement
- The system is useful from the first captured source onward

---

## 3. Record Format

### 3.1 Frontmatter Schema

All record metadata lives in YAML frontmatter of `{uuid}.md`. There are no separate configuration files — the markdown file is the single source of truth for both metadata and content.

The schema library (`schema/`) provides MIME-normalization guidance consumed by the conversion and contextualization pipeline. Schemas are reference material, not field-validation authorities; extended frontmatter fields are tolerated freely (see §3.1.8). Appendix A provides a reference snapshot of common MIME types encountered in practice with examples.

#### 3.1.1 Core Fields

Present on every record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uuid` | string | yes | UUIDv4 identifier. Immutable once assigned. |
| `title` | string | yes | Short descriptive label |
| `description` | string | yes | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `record_type` | enum | yes | `source` or `document` |
| `content_type` | string | yes | IANA MIME type of the record's primary artifact. For documents almost always `text/markdown`. `unknown` is permitted as a sentinel when the MIME cannot be determined. |
| `status` | enum | yes | Pipeline state: `stub` (captured, no body), `draft` (converted, body filled), `normalized` (LLM-refined, ready for use). |
| `visibility` | enum | no | Editorial curation layer, independent of `status`. One of `visible` (default when absent), `deranked` (appears in results at lower priority), `hidden` (excluded from default results, still accessible by direct UUID). |
| `tags` | string[] | no | Declarative topic tags for filtering and organization. See §3.2 for the relationship to body-embedded tag markers. |

`content_type` carries format semantics only — it says nothing about what the record is *about* or what it represents conceptually. Semantic classification (this video is a song; this PDF is a bank statement) is expressed through forward references to concept documents via `part_of`. See §3.5.

`visibility` lets a curator retire low-quality records from normal surfaces without deleting them. Use cases: low-content pages caught in a bulk scrape; superseded captures that remain valuable as historical versions; records flagged for further review. Default search and list queries show only `visible` records.

#### 3.1.2 Source-Specific Fields

Present only on source records (`record_type: source`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `origin_url` | string | conditional | URL of the original content. Required for web-sourced artifacts. |
| `origin_name` | string | yes | Human-readable origin identifier (e.g., "ExampleForum.com", "MusicDB.org") |
| `original_filename` | string | conditional | For non-web sources. Use when `origin_url` is absent. |
| `capture_date` | date | yes | When the artifact was acquired |
| `artifact_store` | string | no | Remote base URI for this record's artifacts. Absent = local only, not yet externalized. |
| `artifact_refs` | array | yes | References to artifact files with integrity hashes (see below) |
| `author` | string | no | Identifiable person who produced this content. Omit for anonymous content. |
| `date_published` | date | no | When the original content was published. Omit for undated content. |

**Artifact references** use the `artifacts://` URI scheme, where the path is relative to the record's artifact folder (`artifacts/{uuid}/`). Each reference carries its own MIME type and may be flagged as the primary artifact:

```yaml
artifact_store: "smb://nas/athenaeum/artifacts/7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c/"
artifact_refs:
  - ref: "artifacts://thread.html"
    sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    mimetype: "text/html"
    primary: true
  - ref: "artifacts://img_001.jpg"
    sha256: "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"
    mimetype: "image/jpeg"
```

**Per-ref fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ref` | string | yes | `artifacts://` URI relative to `artifacts/{uuid}/` |
| `sha256` | string | yes | SHA-256 integrity hash |
| `mimetype` | string | yes | IANA MIME type of this specific artifact file |
| `primary` | bool | no | Default `false`. Exactly one entry per source record SHOULD have `primary: true`. Drives default-artifact selection in consumers (e.g., the artifact rendered in the Original tab of a detail view). The record's top-level `content_type` matches the `mimetype` of this entry. |

**Resolution order:**

1. Check `artifacts/{uuid}/` in the local corpus
2. If not found locally and `artifact_store` is set, fetch from remote to `artifacts/{uuid}/`
3. Use local copy

The `artifact_store` field being absent signals the record's artifacts have not been externalized yet — they exist only in the local `artifacts/{uuid}/` directory. All records should eventually be externalized.

The SHA-256 hash enables integrity verification (confirming the artifact hasn't been corrupted or modified since capture) and deduplication (identifying identical artifacts captured from different origins).

#### 3.1.3 Document-Specific Fields

Present only on document records (`record_type: document`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `constituents` | string[] | yes | UUIDs of direct child records (not flattened — follow the chain for leaves) |
| `merge_rationale` | string | no | Why these records were merged together |
| `asset_store` | string | no | Remote base URI for this document's assets. Absent = local only, not yet externalized. |
| `asset_refs` | array | no | References to asset and artifact files (see below) |

Frontmatter stays manageable because `constituents` lists only direct children. An artist document with 10 albums lists 10 UUIDs. Each album lists its own songs. The full tree is reconstructable but never materialized in a single frontmatter block.

**Asset references** can reference two kinds of files:

1. **Derived assets** (`assets://`) — files produced during document normalization (frame grabs, transcription segments, derived diagrams). Stored in `assets/{uuid}/`.

2. **Source artifacts** (`artifacts://`) — artifacts from a constituent source record used directly in the document (e.g., a PDF rendered inline). These require a `source` field identifying which source record the artifact belongs to. No `sha256` needed — the hash lives on the source record.

```yaml
asset_store: "smb://nas/athenaeum/assets/9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e/"
asset_refs:
  - ref: "assets://frame_001.jpg"
    sha256: "abc123..."
  - ref: "assets://frame_002.jpg"
    sha256: "def456..."
  - ref: "artifacts://service-bulletin.pdf"
    source: "p6h7i8j9-k0l1-4m2n-3o4p-5q6r7s8t9u0v"
```

**Resolution:**

- `assets://filename` → check `assets/{uuid}/` locally → fetch from `asset_store` if set → use local copy
- `artifacts://filename` with `source` → resolves against the source record's artifact folder using the source record's resolution order

**Assets are document-only.** Sources reference only their raw artifacts. Derived files only exist at the document level. This keeps the source layer purely about faithful artifact representation.

#### 3.1.4 Quality Fields

Present on every record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `credibility_tier` | enum | yes | Trustworthiness of the content (see table below) |
| `normalization_confidence` | float | yes | `0.0`–`1.0`, quality of the conversion/normalization process itself |
| `normalization_model` | string | yes | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`) |
| `normalization_date` | date | yes | When normalization was last performed |

**Credibility tiers:**

| Tier | Description | Examples |
|------|-------------|----------|
| `authoritative` | Official or primary source | OEM service manual, published novel text, peer-reviewed paper |
| `expert` | Credentialed professional with demonstrated expertise | Professional mechanic writeup, published literary criticism |
| `community_validated` | Claim independently confirmed by multiple people | Forum fix confirmed by 5+ users, widely accepted fan analysis |
| `anecdotal` | Single person's unconfirmed experience | One forum post describing a symptom |
| `speculative` | Theory or hypothesis without evidence | Unsubstantiated claim or guess |

Credibility is about the trustworthiness of the content's claims. Normalization confidence is about how accurately the raw artifact was converted to markdown. A perfectly transcribed YouTube video might have high confidence but low credibility. A badly OCR'd service manual might have low confidence but authoritative credibility.

#### 3.1.5 Pipeline Fields

Present on source records; optional on document records.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conversion_method` | string | conditional | How the artifact was converted (source records) |
| `conversion_tool` | string | conditional | Tool/script version used for conversion |
| `conversion_date` | date | conditional | When conversion was performed |

These fields enable targeted bulk re-conversion when tools improve (e.g., "re-convert all records processed by `tesseract v4`").

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

**Severity:** `critical` (unusable without fix), `major` (significant loss but partially useful), `minor` (cosmetic or non-essential)

**Remediation:** `wayback_snapshot`, `alternate_source`, `original_author`, `re_capture`, `manual_reconstruction`, `none`

The `resolved` boolean tracks whether the issue has been addressed. Resolved issues remain in frontmatter as historical record.

#### 3.1.7 Relations

Forward references to other records. v9 collapses the previous tagged-array `relations` list into two flat frontmatter fields, both arrays of UUIDs:

```yaml
part_of:
  - "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"   # Album 3 (document)
  - "f7e8d9c0-b1a2-4c3d-9e4f-5a6b7c8d9e0f"   # Artist X discography (document)
same_as:
  - "e4d3c2b1-a098-4765-8fed-cba987654321"   # Reupload / duplicate capture
```

| Field | Type | Applies to | Meaning |
|-------|------|-----------|---------|
| `part_of` | UUID[] | all records | Instance-of / membership. The referencing record **is an instance of** (or a member of) the concept described by each target. Transitivity is computed by the server — wider memberships reachable through chains of `part_of` do not need to be restated. |
| `same_as` | UUID[] | all records | Equivalence. Each target represents the same underlying thing as this record (reuploads, duplicate captures, dedup candidates). Symmetric — stored one-way, walked both ways. |

**Rule: `part_of` is strictly ontological — "is an instance of the concept described by the target."** A song audio file is a song; it belongs as `part_of` a Song concept document. A Wikipedia page *about* songs is **not** a song — it's an article *describing* songs — and therefore does not have the Song concept in its `part_of` list. Articles and other reference material attach via other mechanisms: as `constituents` when their content was synthesized into a document's body, or as body-prose tags surfaced via backlinks.

| Relationship | Mechanism | Direction |
|---|---|---|
| Instance classification | `part_of` | Instance → Concept (outbound on the record that *is* the instance) |
| Body-material derivation / merge DAG | `constituents` (see §3.1.3) | Composed document → source material used |
| Identity equivalence | `same_as` | Symmetric (stored one-way, graph walked both ways) |
| Related reading / mentions / evidence | Body-prose tags (§3.2) surfaced as backlinks | Emerges from content |

**Source-to-source constraint.** `part_of` targets MUST be document records — a source is never ontologically an instance of another source. `same_as` is the only inter-source relation and is used for duplicates and reuploads. Body-prose cross-references (e.g. one AllData HTML artifact hyperlinking another) stay in content and are never lifted to `part_of`.

**Deferrability.** First-pass normalization produces only the body; relations are added later by human curation or LLM enrichment passes. A record with empty `part_of` and `same_as` is complete and valid — just not yet classified.

**Opportunistic compaction.** Redundant `part_of` entries that are derivable by transitivity from existing chains SHOULD be removed when the record is otherwise touched. Do not proactively rewrite unchanged records.

**Unresolved references.** v8's `unresolved: "string"` slot is dropped. Mentions of entities that don't yet have records live in body prose as tags (§3.2) — the server's tag index surfaces them for curator follow-up.

#### 3.1.8 Extended Fields

Records may carry additional frontmatter fields beyond those in §3.1.1–§3.1.7. These are not enumerated by a closed schema — v9 removes the per-concept required-field enforcement of v8. Any extended fields are informational or capture-pipeline-specific (e.g., `channel_name`, `duration_seconds`, `post_url`, `score`, `subreddit`, `username`, `publication`, `isbn`) and are tolerated but not required by the core loader.

The MIME-normalization schemas in `schema/` (see §3.3) may suggest extended fields that are useful to preserve for certain MIME families, but they do not mandate them. Extended fields are a convenience for preserving capture-time metadata, not a classification mechanism.

If a field is genuinely required for a kind of content, the strongest practice is to author a concept document that documents the expectations and reference it via `part_of` — making the requirement a human-readable convention rather than a parser constraint.

### 3.2 Body Format

The body of `{uuid}.md` below the frontmatter closing `---` is the normalized markdown content:

- For **source records**: the artifact's content converted to well-formed markdown — a faithful representation of the original, not an embellishment
- For **document records**: enriched content assembled from all constituents (for merged documents) or authored directly (for concept documents), structured for coherent reading — the appropriate place for cross-referencing, synthesis, and editorial structure

The body uses standard markdown with wiki-links for cross-record references (`[[target_uuid|Display Text]]`) and callout blocks for warnings and notes (`> [!note]`, `> [!warning]`).

**Body tags (forward-declared).** Records may embed `#tag` markers within body prose to indicate topical mentions at specific positions in the content — a news segment that mentions the Pontiac G8 at minute 12, a textbook chapter that references Newton's Third Law in its opening paragraph. Body-tag parsing and indexing are reserved for a future minor revision of this spec; their semantics and exact syntax are not yet finalized. When implemented, the server will build a tag-position index queryable for backlinks (records mentioning `#song` surface when viewing the Song concept document), and topical aboutness emerges from this index rather than being declared in frontmatter `part_of`.

**Editorial comment blocks (forward-declared).** Records may embed editorial annotations inline within body content to add curator context without altering the normalized rendering. Syntax and indexing also reserved for a future revision.

Until those mechanisms land, body prose is free-form markdown; only frontmatter fields are indexed and queryable.

### 3.3 Schema Library

The `schema/` directory contains **MIME-normalization schemas** — reference documents consumed by the normalization pipeline (humans authoring scripts, LLMs performing contextualization) that describe how to produce a markdown representation from artifact content of a given MIME type.

A schema is a markdown file whose frontmatter declares which MIME types it handles, and whose body gives guidance to normalizers. Each schema self-declares its applicable MIME types:

```yaml
---
schema_id: html_content
applies_to_mimetypes:
  - text/html
  - application/xhtml+xml
version: "1.0"
---

# HTML Content Normalization

Guidance on converting captured HTML artifacts into well-formed markdown...

## Stripping

- Remove navigation chrome, sidebars, ads, related-content widgets.
- Preserve the primary content area, headings, lists, tables, code blocks.

## Edge cases
...
```

**Organization.** Schema files live under `schema/` with arbitrary filenames chosen by the author — there is no enforced MIME-to-filename mapping. A schema can cover one MIME (`text/html`) or a family (`audio/mpeg`, `audio/x-m4b`, `audio/wav`). The pipeline selects a schema for a record by matching the record's `content_type` against available schemas' `applies_to_mimetypes`. When multiple schemas match, the most specific one wins (more specific MIME match, then most recent version).

**What schemas are not.** v9 schemas are not classification instruments. They do not enumerate the conceptual categories of records (that's expressed by concept documents and `part_of`), and they do not enforce required extended fields (see §3.1.8). They only describe *how to convert* a given input format into a faithful markdown rendition.

**Authoring workflow.** New MIMEs get schemas lazily. The first record with a novel MIME gets a best-effort normalization and the pipeline flags the gap; a schema is written when enough similar content arrives to justify the effort. An `unknown` or missing schema falls back to a generic best-effort normalizer.

**Migration note.** v8 maintained a closed enum of concept schemas (`schema/sources/forum_post.md`, `schema/documents/album.md`). These are not v9 schemas — they describe concepts, not MIME normalization. They migrate to ordinary concept documents in the corpus (under `documents/`) and are removed from `schema/` over time. Migration is out of scope for this spec.

### 3.4 Examples

#### Source Record

```yaml
---
uuid: "7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c"
title: "Brake Caliper Rebuild - Complete Guide"
description: "Forum thread with a step-by-step brake caliper rebuild procedure, including torque specs, seal kit part numbers, and before/after photos."
record_type: source
content_type: text/html
status: normalized
tags: ["brakes", "caliper-rebuild", "diy"]

origin_url: "https://www.example-autoforum.com/threads/brake-caliper-rebuild.12345/"
origin_name: "ExampleForum.com"
capture_date: 2026-02-16
artifact_refs:
  - ref: "artifacts://thread.html"
    sha256: "e3b0c44298fc1c149afbf4c8996fb924..."
    mimetype: "text/html"
    primary: true
  - ref: "artifacts://img_001.jpg"
    sha256: "a7ffc6f8bf1ed76651c14756a061d662..."
    mimetype: "image/jpeg"
  - ref: "artifacts://img_002.jpg"
    sha256: "9f86d081884c7d659a2feaa0c55ad015..."
    mimetype: "image/jpeg"
date_published: 2024-01-24

credibility_tier: community_validated
normalization_confidence: 0.95
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-16
conversion_method: "forum-scraper"
conversion_tool: "scrape_thread.py v0.6"
conversion_date: 2026-02-16

# capture-pipeline extended fields
username: "user_mike"
thread_url: "https://www.example-autoforum.com/threads/brake-caliper-rebuild.12345/"
reply_count: 13

issues:
  - type: missing_media
    severity: major
    description: "2 of 4 embedded images unavailable"
    remediation: wayback_snapshot
    resolved: false

part_of:
  - "c1d2e3f4-5678-4901-abcd-ef0123456789"   # Forum-post concept document
  - "f1e2d3c4-b5a6-4798-8000-123456789abc"   # Brake-system concept document
---

## Brake Caliper Rebuild Procedure

A complete guide to rebuilding front brake calipers, including
seal replacement, piston inspection, and bleeding procedure...
```

#### Document Record (merged)

```yaml
---
uuid: "9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e"
title: "Convergence"
description: "The Celestial Order's second studio album (2019), a progressive rock record blending jazz fusion elements with intricate polyrhythmic arrangements."
record_type: document
content_type: text/markdown
status: normalized
tags: ["the-celestial-order", "progressive-rock", "2019"]

constituents:
  - "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d"  # MusicDB album page (source)
  - "e1f2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b"  # Review aggregator page (source)
  - "i5j6k7l8-m9n0-4o1p-8q2r-3s4t5u6v7w8x"  # YouTube live performance (source)
  - "m9n0o1p2-q3r4-4s5t-8u6v-7w8x9y0z1a2b"  # song: Meridian (document)
  - "q3r4s5t6-u7v8-4w9x-8y0z-1a2b3c4d5e6f"  # song: Convergence (document)
  - "u7v8w9x0-y1z2-4a3b-8c4d-5e6f7a8b9c0d"  # song: Tidal Resonance (document)
merge_rationale: "All records related to The Celestial Order album Convergence"

asset_refs:
  - ref: "assets://frame_001.jpg"
    sha256: "d4735e3a265e16eee03f59718b9b5d03..."
  - ref: "artifacts://page.html"
    source: "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d"

credibility_tier: authoritative
normalization_confidence: 0.90
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-17

# capture-pipeline extended fields
artist_name: "The Celestial Order"
release_date: 2019
label: "Horizon Records"
track_count: 8
genre: ["progressive rock", "jazz fusion"]

part_of:
  - "b0b0b0b0-1111-4222-8333-444444444444"  # Album concept document
  - "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"  # The Celestial Order (artist document)
---

## Convergence (2019)

The Celestial Order's second album represents a bold evolution from their
debut, weaving jazz fusion elements into a progressive rock framework...
```

#### Concept Document

A concept document has the same shape as a merged document, but typically no `constituents` (it's authored directly rather than synthesized) and is the *target* of many `part_of` references from instance records. Nothing in its frontmatter marks it as "a concept" — its role emerges from the graph.

```yaml
---
uuid: "b0b0b0b0-1111-4222-8333-444444444444"
title: "Album"
description: "A musical release grouping a cohesive set of recorded tracks — studio album, EP, live album, or compilation. Used as a classification target for individual album records."
record_type: document
content_type: text/markdown
status: normalized
tags: ["concept", "music"]

credibility_tier: authoritative
normalization_confidence: 1.0
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-04-19

part_of:
  - "cccccccc-dddd-4eee-8fff-000000000000"  # Music (broader concept)
---

## Album

An **album** is a musical release grouping tracks into a cohesive work...
```

### 3.5 Classification via concept documents

Semantic classification in v9 is expressed by graph membership: records declare `part_of` references to **concept documents** — ordinary document records that describe a category, entity, or idea. Nothing in a concept document's frontmatter marks it as "a concept"; its role is emergent from how other records refer to it.

**Worked example: a single track**

Album-track structure with a new track record classified across multiple axes:

```yaml
# Track 2 source record
content_type: audio/mpeg
part_of:
  - <album-3-uuid>                  # This specific album
  - <artist-x-discography-uuid>     # Redundant if Album 3 is already part_of Discography — remove on next touch

# Album 3 document
record_type: document
content_type: text/markdown
part_of:
  - <artist-x-discography-uuid>
  - <album-concept-uuid>            # "Album" as a general concept

# Artist X discography document
record_type: document
content_type: text/markdown
part_of:
  - <all-songs-concept-uuid>
```

**Transitivity.** The server computes wider memberships by walking `part_of` chains. "Track 2 belongs to All Songs" doesn't need to be stated anywhere — it follows from the chain. Records should declare only the most specific memberships that are directly true; compaction on-touch removes entries made redundant by chain additions elsewhere.

**Dedup example** using `same_as`:

```yaml
# A YouTube video reupload
content_type: video/mp4
same_as:
  - <original-video-uuid>
  - <mirror-upload-uuid>
```

Both records remain fully valid representations. If one should take priority in default surfaces, use `visibility: deranked` or `visibility: hidden` on the less-preferred entries — separate from the structural `same_as` claim.

**What `part_of` is not.** `part_of` is strictly instance-of. A Wikipedia article *about* the Pontiac G8 is not a Pontiac G8 — it's an article. It does not belong as `part_of` the Pontiac-G8 concept document. Its relationship is better expressed:

- As a `constituent` of the Pontiac-G8 document, if its content was synthesized into that document's body, OR
- Via body-prose tags (forward-declared in §3.2), emerging as a backlink when viewing the Pontiac-G8 concept document

This rule is universal: `part_of` targets must pass the "is this record *an instance of* the target concept" test. If the relationship is "about" or "references" or "informs," it belongs elsewhere.

**Deferrability.** First-pass normalization of a source produces only the body — the record has `part_of: []`. Classification is added later by curators or LLM enrichment passes. Records can live indefinitely without explicit classification; the corpus degrades gracefully.

---

## 4. Pipeline

The path from raw content to normalized record is a pipeline of discrete steps: **capture**, **normalize**, optionally **merge**, and optionally **re-normalize**. Each step is independently re-runnable. A separate **build** step materializes the corpus for consumption.

### 4.1 Capture

Capture brings raw content into the corpus and assigns it identity. It has two steps: **staging** and **reconciliation**.

#### 4.1.1 Staging

**What:** Acquire raw content from an external source into the staging area.

**How:** Script-driven or manual — web scrapers, downloaders, API clients, manual file copy. Capture acquires **all associated content** from the source: the primary content (HTML page, PDF, etc.) plus any embedded or linked assets (images, supplementary files) that would otherwise be lost.

**Output:** Raw files in `capture/` in a temporary folder with a descriptive name (e.g., `capture/brake-caliper-rebuild.12345/`). No UUID assigned yet, MIME types not yet finalized. The naming convention is descriptive because identity doesn't exist yet.

Failed or abandoned captures remain in `capture/` without consuming any corpus resources — no UUID, no record, no artifact folder. The `capture/` directory is a transient workspace.

#### 4.1.2 Reconciliation

**What:** Assign identity to captured content, move artifacts into the corpus, and create a source record stub.

**How:** Reconciliation examines the captured content, assigns a UUIDv4, and records per-artifact MIME types. MIME detection is typically deterministic (file extension + magic-byte sniffing); only ambiguous cases warrant LLM assistance.

**Process:**

1. **Assign UUID.** Generate a UUIDv4 for this record.
2. **Detect MIME types.** For each captured file, determine its IANA MIME type (via extension + content sniffing). These populate `artifact_refs[].mimetype`.
3. **Pick the primary artifact.** Exactly one of the captured files is the record's primary content; its MIME becomes the record's top-level `content_type`. For a scraped web page with images, the HTML file is primary. For a downloaded PDF with cover thumbnails, the PDF. For a captured video with a description page, the video. Heuristics: prefer the artifact that carries the primary content of the origin, falling back to the first or largest file. Mark it `primary: true` in `artifact_refs`.
4. **Move artifacts.** Rename the temporary capture folder to the UUID and move it to `artifacts/{uuid}/`. The raw files are now in their permanent location.
5. **Compute hashes.** Calculate SHA-256 hashes for each artifact file.
6. **Create source stub.** Write `sources/{uuid}.md` with frontmatter populated:
   - `status: stub` (no body content yet)
   - `content_type` = the primary artifact's MIME
   - `artifact_refs` with `artifacts://` URIs, SHA-256 hashes, MIME types, and the `primary: true` flag on one entry
   - Core metadata: `origin_url`, `origin_name`, `capture_date`, etc.
   - `part_of` left empty — classification is deferred to a later pass

**Key principles:**

- Capture is the **only step requiring network access**. Everything downstream is offline.
- The UUID is only assigned when artifacts are successfully acquired and reconciled. Failed captures don't consume UUIDs.
- All associated content from the origin is captured — every file becomes a reference in `artifact_refs`.
- Reconciliation does not classify *what the record is about* — only *what format it is in*. Classification (via `part_of`) happens later as an enrichment pass.

Content to be captured may be tracked externally (a backlog, a spreadsheet, a task list). The corpus itself only contains records for content that has been captured and reconciled.

### 4.2 Normalize

Normalization transforms a stub record into a complete, useful markdown file. It has two sub-steps: **conversion** (deterministic) and **contextualization** (LLM-driven).

#### 4.2.1 Conversion

**What:** Deterministic conversion of artifact content into markdown.

**How:** MIME-driven conversion — no LLM involvement, deterministic and reproducible. Conversion reads the primary artifact file referenced by `artifact_refs` (resolving via the local `artifacts/{uuid}/` directory or fetching from `artifact_store`) and produces the markdown body of the record. The converter is selected by matching the record's `content_type` MIME against available schema guidance in `schema/` (§3.3).

**Output:** The body of `{uuid}.md` is filled with the artifact's content as well-formed markdown. `status` set to `draft`.

**MIME-family handling (representative):**

| MIME family | Conversion output |
|-------------|-------------------|
| `text/html`, `application/xhtml+xml` | Clean content; strip navigation, styling, chrome |
| `application/pdf` | Text and table extraction; per-page structure |
| `image/*` | `![alt text](artifacts://filename)` embed; descriptive alt from MIME-schema guidance |
| `audio/*` | Transcription (Whisper or similar) with timestamps |
| `video/*` | Transcription + frame descriptions per schema guidance |
| `application/epub+zip` | Parse chapter structure, extract text |
| `text/markdown`, `text/plain` | Passthrough (`conversion_method: passthrough`) |
| `unknown` or unmatched | Best-effort fallback; emit `draft` body with a placeholder and record the gap |

Trivial conversion is fine. A clean text file gets `conversion_method: "passthrough"` — the pipeline is uniform even when a step does minimal work.

**Conversion provenance.** The `conversion_method`, `conversion_tool`, and `conversion_date` fields enable targeted bulk re-conversion when tools improve (e.g., "re-convert all `application/pdf` records processed by `tesseract v4` with `tesseract v5`").

#### 4.2.2 Contextualization

**What:** LLM-driven refinement of record content.

**How:** An LLM agent loads the record and the MIME-normalization schema matching the record's `content_type`, then refines the content with semantic understanding. For document records (after merge), the agent loads all constituent records together for cross-record awareness.

**Operations:**

| Operation | Why LLM |
|-----------|---------|
| Convert remaining inline HTML to well-formed markdown | Requires semantic understanding of structure |
| Improve image alt text and classification | Requires content understanding |
| Normalize formatting across the record | Requires editorial judgment |
| Generate or refine `description` | Requires content understanding |
| Assess `credibility_tier` | Requires domain judgment |
| Surface quality issues | Requires quality judgment |
| Cross-reference related content (document records) | Requires cross-record semantic awareness |

**Normalization integrity (source records).** For source records, contextualization must produce a more accurate representation of the artifact — not a more complete one. The agent may:

- Fix structural issues (broken tables, malformed lists)
- Resolve encoding ambiguity (mojibake → correct characters, when determinable from context)
- Improve formatting fidelity (better markdown representation of the original structure)
- Add alt text to images based on visible content
- Surface issues where content is missing or degraded

The agent must **not**:

- Add factual claims not present in the artifact
- Fill in gaps with inferred information
- Embellish or editorialize the content
- Add context from external knowledge

**Document records are different.** When contextualizing a document record (after merge), the agent draws on all constituent records to produce enriched, composite content. Cross-referencing, synthesis, and editorial structure are appropriate here because the document's purpose is to form a complete picture from multiple accurate sources.

**Output:** Record with refined body and `status: normalized`.

### 4.3 Merge

**What:** Create a new document record from existing records that represent the same subject.

**Process:**

1. **Discover candidates.** LLM-assisted or manual. After normalizing a batch, a discovery pass identifies records about the same subject. "These three sources are all about the same album."

2. **Propose merge.** The proposal specifies which records to combine, what concept document(s) the result should `part_of`, and an optional merge rationale. The operator approves or rejects.

3. **Create document record.** A new UUID is assigned. The record is written to `documents/{uuid}.md`. The `constituents` field lists direct child UUIDs. `record_type` is `document`. `content_type` is `text/markdown`. `part_of` references any concept documents the merged result classifies under.

4. **Normalize the document.** The normalizer loads all constituent records and assembles enriched content drawing on all of them, producing the document's markdown body. Any derived files produced during normalization are stored in `assets/{uuid}/` and referenced via `asset_refs`. The document is richer than any individual constituent because it draws on all of them and is free to synthesize across sources.

**Merge is non-destructive.** Constituent records remain unchanged and independently addressable in `sources/` (or `documents/` for multi-level merges). The merge creates a new record on top of them. An incorrect merge is undone by deleting the document record — the constituents are unaffected.

**Multi-level merges** are natural: song documents (merged from lyrics + audio + metadata sources) become constituents of an album document, which becomes a constituent of an artist document. Each level adds context and produces progressively richer output.

### 4.4 Re-normalize

**What:** Flow normalization context from merges back to constituent records to improve their accuracy.

**When:**

- A constituent source has known issues (incomplete translation, ambiguous formatting) that parent records might help resolve
- A new merge provides context that wasn't available at original normalization time
- A model upgrade justifies re-processing with better tools

**How:** On-demand pass triggered by the operator or Curator agent. Processing order follows a **reverse topological sort** of the DAG — leaf sources first (using context from their parent documents to resolve ambiguity), then intermediate documents, then top-level documents. This ensures improvements at lower levels propagate upward when parent documents are subsequently re-normalized.

**Normalization integrity still applies.** Even during re-normalization with additional context, a source record must remain faithful to its artifact. Context from parent records can help resolve ambiguity (e.g., disambiguating a partial lyric translation), but must not introduce information that isn't in the original artifact.

**Re-normalization is optional.** Many records will never be re-normalized — the initial normalization is sufficient. The capability exists for cases where DAG context meaningfully improves accuracy.

### 4.5 Build

**What:** Materialize the corpus into a browsable or publishable form.

**How:** A build process reads the corpus and produces output suitable for consumption (static site, browsable vault, or other format).

**Processing order:** Reverse topological sort of the DAG:

1. For each source record, resolve `artifact_refs` to actual files (ensure artifacts are in `artifacts/{uuid}/`, fetching from `artifact_store` if needed)
2. For document records, resolve `asset_refs` similarly (ensure assets are in `assets/{uuid}/`, fetching from `asset_store` if needed)
3. Generate index and navigation structures appropriate to the output format

**URL-to-UUID resolution.** The build process can generate a lookup index mapping origin URLs to UUIDs, enabling consumers to find records by the URL they were captured from. Both the original origin URL and the record's UUID serve as stable entry points.

Build is an implementation detail — this spec defines what the corpus contains, not how it's published. The build system reads markdown files and metadata, and produces whatever output format is appropriate.

### 4.6 Phase Boundaries and Re-processing

Pipeline steps are independently re-runnable:

| Operation | Scope | Trigger |
|-----------|-------|---------|
| **Re-capture** | One record | Upstream content may have changed |
| **Re-convert** | Records by `conversion_tool` version | Conversion tools improved |
| **Re-contextualize** | Records by `normalization_model` | LLM models improved |
| **Re-merge** | One document record | Constituents have been updated |
| **Re-normalize (contextual)** | DAG subgraph | Merge context should flow to constituents |

Each operation can target specific records via metadata queries. The `conversion_tool`, `normalization_model`, and `normalization_date` fields enable precise targeting (e.g., "re-contextualize all records normalized before March 2026").

---

## 5. Pipeline Agents

### 5.1 Overview

The pipeline is operated by specialized agents — lightweight, single-purpose workers that each handle one item per invocation. Agents have focused responsibilities, process exactly one item, and report results to a coordinator. There is no inter-agent communication and no shared state beyond the corpus filesystem.

Agents consult MIME-normalization schemas in `schema/` that match the record's `content_type`, applying consistent normalization guidance for each MIME family.

### 5.2 Ingestor

Handles capture staging, reconciliation, and record stub creation for a single content item.

**Model class:** Haiku-tier (fast, cheap — no creative judgment needed)

**Scope:** One content item per invocation

**Responsibilities:**

1. Run the appropriate capture script to acquire artifacts into `capture/`
2. Reconcile: detect MIME types, pick the primary artifact, assign UUID, move artifacts to `artifacts/{uuid}/`
3. Compute SHA-256 hashes for each artifact file
4. Create `sources/{uuid}.md` with stub frontmatter including `content_type`, per-ref `mimetype`, and `primary: true` on one ref
5. Verify artifact integrity (file completeness, expected content present, hashes recorded)
6. Report results: success/failure, UUID assigned, artifact count, any warnings

The ingestor receives instructions about what to capture. It is a reliable executor, not a decision maker — it does not choose what to ingest or how to classify content.

### 5.3 Normalizer

Transforms record stubs into fully normalized records, handling both conversion and contextualization.

**Model class:** Sonnet-tier (creative judgment required for contextualization, issue surfacing, description generation)

**Scope:** One record per invocation. For document records, all constituent records are loaded for cross-record awareness.

**Responsibilities:**

1. **Conversion.** For source records with `status: stub`, resolve the primary artifact and run the MIME-matched converter to fill the markdown body. Set `status: draft`. This step shells out to deterministic tooling.
2. **Contextualization.** Refine content with LLM judgment, consulting the MIME-normalization schema that matches the record's `content_type`. For source records: achieve accurate representation without adding information. For document records: synthesize across constituents, produce derived assets in `assets/{uuid}/`. Surface issues. Generate or refine `description`. Assess `credibility_tier`. Set `status: normalized`.
3. **Self-verify.** Check for broken artifact references. Verify SHA-256 hashes if artifacts are locally available. Confirm `content_type` matches the `mimetype` of the primary artifact ref.

### 5.4 Merger

Creates document records from related source records.

**Model class:** Sonnet-tier (semantic judgment required for candidate discovery and assembly)

**Scope:** One merge operation per invocation

**Responsibilities:**

1. **Candidate discovery** (when prompted). Given a set of records, identify groups that represent the same subject. Present candidates to operator for approval.
2. **Create document record.** Assign UUID, write `documents/{uuid}.md`, populate frontmatter with `constituents`, `content_type: text/markdown`, and any applicable `part_of` references to concept documents.
3. **Assemble document content.** Load all constituent records and produce enriched markdown that draws on all of them. Produce any derived assets in `assets/{uuid}/`. Structure the body coherently; no schema-enforced layout in v9.

### 5.5 Curator

Autonomous orchestration skill that assesses corpus state, prioritizes work, and dispatches agents.

**Operating loop:**

1. **Assess.** Scan `sources/` and `documents/` for record statuses (`stub`, `draft`, `normalized`), unresolved issues, merge candidates, and re-normalization opportunities. Check `capture/` for completed captures awaiting reconciliation.
2. **Prioritize.** Apply decision framework: compendium blockers first, then high-priority new captures, then normalization of existing stubs, then merge candidates, then re-normalization.
3. **Propose.** Present the prioritized work plan to the operator for approval.
4. **Execute.** Spawn ingestor, normalizer, and merger agents, managing parallelism by launching multiple agents concurrently.
5. **Report.** Summarize results — records captured, normalized, merged, issues encountered.

### 5.6 Parallelism Model

- The **Curator** (or human operator) decides concurrency based on available resources and rate limits.
- Each agent processes one item. The Curator spawns N agents in parallel for N items.
- Agents do not communicate with each other. They read from and write to the corpus, and the Curator sequences work to avoid conflicts (e.g., not normalizing a document whose constituents are still being captured).
- Typical session: spawn 5 ingestors in parallel → wait for completion → spawn 5 normalizers for the new stubs → spawn merger for identified candidates.

### 5.7 Deterministic vs. LLM Boundary

| Operation | Type | Rationale |
|-----------|------|-----------|
| Capture (download, scrape) | Deterministic | Reproducible, scriptable, no judgment needed |
| Reconciliation (assign UUID, detect MIME, pick primary artifact) | Deterministic | File extension + magic-byte sniffing are mechanical; LLM only for genuinely ambiguous captures |
| Hash computation (SHA-256) | Deterministic | Mechanical integrity check |
| Conversion (HTML→MD, PDF→text, OCR, transcription) | Deterministic | Reproducible, tool-specific, no editorial judgment |
| Contextualization (refine, describe, assess, surface issues) | LLM | Requires semantic understanding and editorial judgment |
| Merge candidate discovery | LLM | Requires semantic matching across records |
| Document assembly (from constituents) | LLM | Requires editorial decisions about structure and emphasis |
| Re-normalization (context flow) | LLM | Requires contextual understanding from parent records |
| Build (export, index) | Deterministic | Mechanical, reproducible |

The boundary is clear: **if the operation could produce different valid outputs depending on judgment, it's LLM-driven. If the output is deterministic given the input, it's scripted.** This enables independent re-processing — you can re-convert with better tools without re-contextualizing, and vice versa.

---

## 6. Compendium Layer

### 6.1 What a Compendium Is

A **compendium** is a curated synthesis of records into a domain-specific reference work. Where records preserve and normalize source material faithfully, compendiums apply editorial judgment to produce coherent, structured knowledge.

A compendium is opinionated. It has a defined scope, a point of view, and a domain taxonomy. Multiple compendiums can draw from the same records and produce different works — an economics compendium and a socialism compendium might both use records from the same academic sources, selecting different subsets and synthesizing from different perspectives.

### 6.2 How Compendiums Use Records

Compendiums select records from the corpus and synthesize them into chapters organized by a domain taxonomy:

1. **Select records.** Using record descriptions, tags, MIME types, and `part_of` classifications, identify records relevant to the compendium's domain. Document records (merged or concept) are preferred because they're already enriched, but source records can also be selected directly.
2. **Organize by taxonomy.** Group selected records by the compendium's chapter structure. The taxonomy follows the domain's natural organization (by vehicle system for automotive, by character/faction/theme for fiction, by theory/era for economics).
3. **Synthesize chapters.** Distill grouped records into coherent prose, reconciling conflicts, identifying patterns, and citing record UUIDs.
4. **Build navigation.** Generate cross-references and supplementary sections (FAQ, glossary, quick reference).

### 6.3 Synthesis Principles

- **Cite records.** Every factual claim references the UUID(s) it derives from. The reader can always trace a claim back to a specific record.
- **Represent disagreement.** When records conflict, the compendium presents both positions with their respective credibility tiers rather than silently choosing one.
- **Aggregate patterns.** If 40 forum posts describe the same failure mode, the compendium captures the pattern (common mileage range, symptoms, root cause) rather than citing each post individually.
- **Respect credibility tiers.** Higher-tier records carry more weight. An `authoritative` document is not overruled by `anecdotal` reports unless the volume and consistency of community experience is overwhelming.
- **Respect issues.** Records with unresolved `critical` or `major` issues should be weighted accordingly and gaps noted.
- **Leverage relations.** `same_as` identifies duplicate captures (collapse to one for citation purposes). `part_of` reveals classification and enables grouping records by concept document during synthesis.

### 6.4 System Prompts

Each compendium has a **synthesis system prompt** — a document encoding domain-specific knowledge: scope boundaries, key relationships, document selection criteria, and synthesis guidelines.

System prompts are iterable. When synthesis produces gaps or errors, the system prompt is refined and synthesis is re-run: **synthesize → review → refine prompt → re-synthesize**.

### 6.5 Incremental Re-synthesis

Compendiums track which records were used to produce each chapter and the `normalization_date` of each record at the time of synthesis. When records are re-normalized or new records are added, only affected chapters need re-synthesis.

A record that has been re-normalized (new `normalization_date`) triggers re-synthesis only in chapters that cite it. This keeps re-synthesis proportional to actual content change, not to corpus-wide activity.

---

## Appendix A: MIME Reference

This appendix lists MIME types commonly encountered in practice, along with typical normalization notes and frequently-observed extended metadata fields. **It is not a closed enumeration.** Any IANA-registered MIME is valid as a `content_type` value. The schema library (`schema/`) is the authoritative source of normalization guidance for each MIME or MIME family; this appendix is an illustrative snapshot.

Extended fields shown below are **informational only** — they are capture-pipeline byproducts and v9 does not validate their presence. Their main role is preserving useful metadata that was trivially available at capture time (video duration, document page count, forum username).

### A.1 Source MIMEs

Sources typically have a non-markdown MIME reflecting their captured format. The record's body is the markdown rendition; the artifacts preserve the originals.

| MIME | Typical artifact | Notes |
|------|------------------|-------|
| `text/html`, `application/xhtml+xml` | Web pages, forum threads, articles, blog posts | Strip navigation, chrome, advertising. Preserve primary content, headings, tables, code blocks. The largest MIME by volume in most corpora. |
| `application/pdf` | Service manuals, academic papers, technical bulletins, datasheets, scans | Extract text and tables. OCR if the PDF is image-only. Preserve page boundaries via headings or horizontal rules when useful for citation. |
| `application/epub+zip` | Novels, non-fiction ebooks, collected works | Parse chapter structure; emit one heading per chapter. Preserve internal links where targets resolve within the ebook. |
| `text/markdown`, `text/plain` | Clean native markdown or text files | Passthrough with minimal cleanup. Set `conversion_method: "passthrough"`. |
| `video/mp4`, `video/webm`, `video/quicktime` | YouTube captures, tutorials, documentaries, films | Transcribe audio with timestamps. Describe frames per schema guidance. A primary artifact may have a companion HTML page capturing metadata — still marked non-primary. |
| `audio/mpeg`, `audio/x-m4a`, `audio/x-m4b`, `audio/wav`, `audio/ogg` | Podcast episodes, audiobook chapters, radio segments, songs | Transcribe with timestamps. Preserve speaker turn markers where determinable. |
| `image/jpeg`, `image/png`, `image/gif`, `image/webp` | Photos, diagrams, screenshots, scans | Emit as `![alt text](artifacts://filename)`; LLM-generated alt text based on visible content. Surface text content via OCR when appropriate. |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Word documents | Extract text preserving structure; handle tracked changes / comments conservatively. |
| `unknown` | Captures whose MIME cannot be determined or for which no schema exists | Best-effort fallback normalizer; record the gap in `issues[]`. |

**Typical extended fields for common captures** (informational, not required):

- **Forum threads (`text/html` from forum platforms):** `username`, `thread_url`, `reply_count`
- **Reddit threads (`text/html` from reddit.com):** `username`, `subreddit`, `post_url`, `score`, `comment_count`
- **Web articles (`text/html` from publisher sites):** `article_url`, `publication`, `author`
- **Video sources:** `duration_seconds`, `channel_name`, `platform`
- **Audio sources:** `duration_seconds`, `series_name`, `episode_number`
- **PDF sources:** `page_count`, `document_type` (e.g., `manual_section`, `bulletin`, `paper`, `datasheet`)
- **Ebooks:** `work_title`, `isbn`, `word_count`, `series_name`, `series_position`
- **Images:** `dimensions`, `subject`
- **Metadata pages from database sites:** `source_site` (MusicDB.org, IMDB, Wikipedia, etc.), `page_type` (band, album, artist, film, episode, etc.)
- **Screenplays:** `work_title`, `medium` (`film` / `television` / `stage`), `draft`
- **Product documentation:** `product_name`, `manufacturer`, `document_type` (`datasheet` / `catalog` / `guide` / `sds`), `part_numbers`

### A.2 Document MIMEs

Documents almost always have `content_type: text/markdown` — they are markdown by construction. The classification that used to be their "content type" in v8 (`album`, `novel`, `song`, `artist`, `tv_episode`, `technical_reference`, `research_work`) is expressed in v9 as `part_of` references to concept documents describing those categories.

Typical concept documents a corpus might author:

- **Music domain:** `Song`, `Album`, `Artist`, `Genre`, specific artist/band documents, specific album documents
- **Literature domain:** `Novel`, `Novella`, `Series`, `Author`, specific author/work documents
- **Broadcast domain:** `TV Episode`, `TV Series`, `Film`, `Podcast`
- **Technical domain:** `Technical Reference`, `Service Manual`, `System` (e.g., "Brake System"), specific product/model documents
- **Academic domain:** `Research Paper`, `Journal`, `Field` (e.g., "Condensed Matter Physics")

These concept documents are ordinary document records. Typical extended fields for each are a matter of curator convention and are preserved as informational metadata when present (e.g., `artist_name`, `release_date`, `label` on an album record; `work_title`, `author_name`, `year_published` on a novel record). The authoritative guide for any given concept is the prose in the concept document itself.

### A.3 When to author a concept document

A rule of thumb: if multiple records would otherwise sit orphaned and describable only by tags, and you find yourself wanting to query "all records that are X", then X likely deserves a concept document. Examples where a concept document pays off:

- Multiple sources about the same album → one Album-specific document as a shared classification target
- Many sources about products in a line → a product-line concept document
- Recurring abstract categories (Review, Analysis, Explainer) → category concept documents that cut across domains

Concept documents are cheap to create and cheap to retire (move or delete, update inbound `part_of` references). Do not over-plan. Start with the concepts that emerge naturally from the corpus's actual classification needs.
