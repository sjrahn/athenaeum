---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 8.0
status: draft
author: Steven Rahn
date_created: 2026-02-08
date_modified: 2026-03-18
changelog:
  - version: 8.0
    date: 2026-03-18
    summary: "Major rewrite: flat UUID-based record store with compositional merges (DAG). Sources (captured from origins) and documents (merged composites) as the two record types. All metadata in YAML frontmatter. Schema library for content type definitions. Normalization integrity principle. Eliminates corpus-per-repo structure, graduation, tombstones, ID remapping, routing claims, partition codes."
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

- **The compendium layer.** Curated synthesis of selected records into domain-specific reference works — structured, editorial, and opinionated where the record store is faithful and objective.

### 1.2 Design Principles

1. **Every record is independently valid.** Whether it's a single captured forum post or a merged multi-source artist profile, every record in the store is a complete, addressable, useful markdown document.

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
| **Source** | A record captured from a single external origin. Its content type is source-oriented. |
| **Document** | A record created by merging other records. Its content type is concept-oriented. |
| **Artifact** | A raw external file (HTML, PDF, epub, image, audio, etc.) captured from an origin. Stored externally, referenced by URI. Immutable. |
| **UUID** | Universally unique identifier for a record (v4, RFC 9562). Stable and permanent. |
| **Constituent** | A record that is a direct child of a document record in the merge DAG. |
| **Merge** | The process of creating a document record from existing records about the same subject. |
| **Normalization** | Converting raw captured content into well-formed markdown with structured metadata. Must not add information not present in the original artifact. |
| **Compendium** | A curated synthesis of records into a domain-specific reference work. |
| **Content type** | Classification of a record. Source types are origin-oriented; document types are concept-oriented. Defined in the schema library. |
| **Schema** | A content type definition specifying required fields, normalization guidance, and formatting standards. Lives in `schema/`. |

---

## 2. Core Model

### 2.1 Records

A **record** is the universal unit of the Athenaeum. Every record:

- Has a universally unique identifier (UUID v4)
- Is a single markdown file `{uuid}.md` with YAML frontmatter and normalized content body
- Lives in either `sources/` or `documents/` depending on its type
- Is independently addressable and useful as a standalone document

The store is a flat collection of markdown files with a schema library:

```
store/
├── sources/
│   ├── 7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c.md
│   ├── 8b4e3c2d-5e6f-4a7b-9c0d-1e2f3a4b5c6d.md
│   └── ...
├── documents/
│   ├── 9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e.md
│   └── ...
└── schema/
    ├── sources/
    │   ├── forum_post.md
    │   ├── video.md
    │   └── ...
    └── documents/
        ├── album.md
        ├── novel.md
        └── ...
```

No nesting beyond the top-level type separation. Organization is expressed through metadata (tags, content types, relations) and through the merge DAG — not through directory hierarchy.

### 2.2 Sources

**Sources** are records captured from a single external origin — a forum post, a YouTube video, a PDF document, a web article, a metadata page.

Source content types describe **what was captured and from where**: `forum_post`, `video`, `pdf_document`, `epub`, `web_article`, `metadata_page`, etc. The content type determines which schema governs the record — what extended fields are required, what normalization guidance applies, and how the body should be structured.

The source record's frontmatter references external artifact files (the raw HTML, PDF, epub, etc.) by URI with a SHA-256 hash for integrity verification. The artifacts themselves are not stored in the record store. The store contains only markdown.

**A source is a faithful representation of its artifact.** Normalization may improve formatting, resolve ambiguity, and fix structural issues, but it must not add information that isn't present in the original artifact. The source record is an accurate markdown rendition of its artifact — nothing more.

### 2.3 Documents

**Documents** are records created by merging other records that represent the same subject. They represent concepts rather than individual captured things — a novel (merged from epub + audiobook sources), an album (merged from song documents + metadata sources), an artist (merged from album documents + artist page sources).

Document content types describe **what the merged record represents**: `novel`, `song`, `album`, `artist`, `tv_episode`, etc. The content type determines the schema — what extended fields are required and how the body should structure the merged content.

The record's frontmatter lists its **direct constituent UUIDs** in the `constituents` field. Only direct children — not the full flattened tree. To find all leaf sources, follow the chain through constituent records.

**Documents are where the complete picture forms.** Unlike sources (which are faithful to a single artifact), documents draw on multiple sources to produce enriched, composite content. A document may synthesize, reconcile contradictions, and add cross-referencing between its constituents. This is the appropriate place for the kind of editorial enrichment that would violate normalization integrity if applied to a source.

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

- The store is always in a valid state
- Any record can be selected for compendium synthesis at any time
- Merging is an enrichment operation, not a completion requirement
- The system is useful from the first captured source onward

---

## 3. Record Format

### 3.1 Frontmatter Schema

All record metadata lives in YAML frontmatter of `{uuid}.md`. There are no separate configuration files — the markdown file is the single source of truth for both metadata and content.

Content-type-specific extended fields are defined in the schema library (`schema/`). The schema files are authoritative — they define required/optional fields, normalization guidance, and formatting standards for each content type. The appendix (section A) provides a reference snapshot of the initial content types with examples.

#### 3.1.1 Core Fields

Present on every record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uuid` | string | yes | UUIDv4 identifier. Immutable once assigned. |
| `title` | string | yes | Short descriptive label |
| `description` | string | yes | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `record_type` | enum | yes | `source` or `document` |
| `content_type` | string | yes | From the source or document type enum (see schema library and appendix A) |
| `status` | enum | yes | `stub` (captured, no body), `draft` (converted, body filled), `normalized` (LLM-refined, ready for use) |
| `tags` | string[] | no | Classification tags for filtering and organization |

#### 3.1.2 Source-Specific Fields

Present only on source records (`record_type: source`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `origin_url` | string | conditional | URL of the original content. Required for web-sourced artifacts. |
| `origin_name` | string | yes | Human-readable origin identifier (e.g., "G8Board.com", "Metal Archives") |
| `original_filename` | string | conditional | For non-web sources. Use when `origin_url` is absent. |
| `capture_date` | date | yes | When the artifact was acquired |
| `artifact_refs` | array | yes | References to external artifact files with integrity hashes (see below) |
| `author` | string | no | Identifiable person who produced this content. Omit for anonymous content. |
| `date_published` | date | no | When the original content was published. Omit for undated content. |

**Artifact references** include a URI and SHA-256 hash for each external artifact file:

```yaml
artifact_refs:
  - uri: "artifacts://g8board/290127/thread.html"
    sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  - uri: "artifacts://g8board/290127/img_001.jpg"
    sha256: "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"
```

The SHA-256 hash enables integrity verification (confirming the artifact hasn't been corrupted or modified since capture) and deduplication (identifying identical artifacts captured from different origins).

#### 3.1.3 Document-Specific Fields

Present only on document records (`record_type: document`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `constituents` | string[] | yes | UUIDs of direct child records (not flattened — follow the chain for leaves) |
| `merge_rationale` | string | no | Why these records were merged together |

Frontmatter stays manageable because `constituents` lists only direct children. An artist document with 10 albums lists 10 UUIDs. Each album lists its own songs. The full tree is reconstructable but never materialized in a single frontmatter block.

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
    description: "3 of 5 embedded images unavailable — showed timing chain alignment"
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

Optional array of explicit relationships to other records. These capture **intrinsic relationships** — objective facts evident in the content itself, not connections discovered during synthesis.

```yaml
relations:
  - type: "sequel_to"
    target: "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
  - type: "references"
    unresolved: "GM TSB #PI0597B"
```

**Relation types:**

| Type | Meaning | Example |
|------|---------|---------|
| `sequel_to` | Next in a sequence | Dune Messiah → Dune |
| `preceded_by` | Previous in a sequence | Dune → Dune Messiah |
| `reply_to` | Direct response | Forum reply → parent thread |
| `references` | Explicitly cites or links to | Forum post → TSB it mentions |
| `adaptation_of` | Creative adaptation | Screenplay → novel |
| `supersedes` | Replaces or updates | Revised TSB → original TSB |
| `superseded_by` | Has been replaced | Original TSB → revised TSB |
| `contradicts` | Explicitly disagrees with | Forum post refuting another |

Cross-record references use `target` (a UUID) when the referenced record exists in the store, or `unresolved` (a human-readable string) when it doesn't yet. Unresolved references can be resolved later as the store grows.

Discovered relationships — connections identified during synthesis rather than present in the content itself — belong in the compendium layer, not record frontmatter.

#### 3.1.8 Content-Type Extended Fields

Each content type defines additional fields specific to that type. These appear alongside core fields in the frontmatter. The authoritative definitions live in the schema library (`schema/sources/` and `schema/documents/`). Appendix A provides a reference snapshot with examples.

Content types are a closed enum — adding a new type requires creating a schema file. Types may gain subtypes as the library grows (e.g., `forum_post.xenforo`, `forum_post.vbulletin`) to provide more specific normalization guidance.

### 3.2 Body Format

The body of `{uuid}.md` below the frontmatter closing `---` is the normalized markdown content:

- For **source records**: the artifact's content converted to well-formed markdown — a faithful representation of the original, not an embellishment
- For **document records**: enriched content assembled from all constituents, structured for coherent reading — the appropriate place for cross-referencing, synthesis, and editorial structure

The body uses standard markdown with wiki-links for cross-record references (`[[target_uuid|Display Text]]`) and callout blocks for warnings and notes (`> [!note]`, `> [!warning]`).

### 3.3 Schema Library

The `schema/` directory contains the authoritative definitions for each content type. Each schema file is a markdown document with YAML frontmatter defining:

- **Extended fields**: required and optional fields specific to this content type
- **Normalization guidance**: what the normalizer should focus on, common pitfalls, quality expectations
- **Formatting standards**: how the body should be structured for this content type
- **Example**: a representative frontmatter block

Schema files are organized by record type:

- `schema/sources/` — source content type schemas (e.g., `forum_post.md`, `video.md`)
- `schema/documents/` — document content type schemas (e.g., `album.md`, `novel.md`)

The schema library is the extensibility mechanism. As the store grows, new content types are added by creating new schema files. Existing types may gain subtypes for more specific guidance (e.g., `forum_post.xenforo` for XenForo-specific parsing instructions).

### 3.4 Examples

#### Source Record

```yaml
---
uuid: "7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c"
title: "Rear Suspension Rebuild - The Easy Way"
description: "Forum thread documenting a complete rear subframe swap using a 2017 Caprice PPV dropout into a Pontiac G8 GT, including ABS sensor wiring and compatibility details."
record_type: source
content_type: forum_post
status: normalized
tags: ["suspension", "rear-subframe", "ppv-swap", "pontiac-g8"]

origin_url: "https://www.g8board.com/threads/rear-suspension-rebuild.290127/"
origin_name: "G8Board.com"
capture_date: 2026-02-16
artifact_refs:
  - uri: "artifacts://g8board/290127/thread.html"
    sha256: "e3b0c44298fc1c149afbf4c8996fb924..."
  - uri: "artifacts://g8board/290127/img_001.jpg"
    sha256: "a7ffc6f8bf1ed76651c14756a061d662..."
  - uri: "artifacts://g8board/290127/img_002.jpg"
    sha256: "9f86d081884c7d659a2feaa0c55ad015..."
date_published: 2024-01-24

credibility_tier: community_validated
normalization_confidence: 0.95
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-16
conversion_method: "g8board-scraper"
conversion_tool: "scrape_thread.py v0.6"
conversion_date: 2026-02-16

# extended: forum_post
username: "G8GTSteve"
thread_url: "https://www.g8board.com/threads/rear-suspension-rebuild.290127/"
reply_count: 13

issues:
  - type: missing_media
    severity: major
    description: "2 of 4 embedded images unavailable"
    remediation: wayback_snapshot
    resolved: false

relations:
  - type: references
    unresolved: "GM TSB #PI0597B"
---

## Rear Subframe Swap Procedure

The easiest upgrade path for the G8 rear suspension is a complete
subframe swap from a 2017 Caprice PPV...
```

#### Document Record

```yaml
---
uuid: "9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e"
title: "Obscura"
description: "Gorguts' third studio album (1998), a landmark of technical death metal known for its extreme dissonance and avant-garde composition."
record_type: document
content_type: album
status: normalized
tags: ["gorguts", "death-metal", "technical", "1998"]

constituents:
  - "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d"  # Metal Archives album page
  - "e1f2g3h4-i5j6-4k7l-8m9n-0o1p2q3r4s5t"  # RYM album page with reviews
  - "i5j6k7l8-m9n0-4o1p-8q2r-3s4t5u6v7w8x"  # YouTube live performance
  - "m9n0o1p2-q3r4-4s5t-8u6v-7w8x9y0z1a2b"  # song: Earthly Love
  - "q3r4s5t6-u7v8-4w9x-8y0z-1a2b3c4d5e6f"  # song: Obscura
  - "u7v8w9x0-y1z2-4a3b-8c4d-5e6f7a8b9c0d"  # song: Nostalgia
merge_rationale: "All records related to the Gorguts album Obscura"

credibility_tier: authoritative
normalization_confidence: 0.90
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-17

# extended: album
artist_name: "Gorguts"
release_date: 1998
label: "Olympic Recordings"
track_count: 8
genre: ["technical death metal", "avant-garde metal"]

relations:
  - type: preceded_by
    target: "y1z2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b"
---

## Obscura (1998)

Gorguts' third album represents a radical departure from their earlier
death metal style...
```

---

## 4. Pipeline

The path from raw content to normalized record is a pipeline of discrete steps: **capture**, **normalize**, optionally **merge**, and optionally **re-normalize**. Each step is independently re-runnable. A separate **build** step materializes the store for consumption.

### 4.1 Capture

**What:** Acquire raw content from an external source and create a source record stub in the store.

**How:** Script-driven or manual — web scrapers, downloaders, API clients, manual file copy. Capture acquires **all associated content** from the source: the primary content (HTML page, PDF, etc.) plus any embedded or linked assets (images, supplementary files) that would otherwise be lost.

**Output:**

1. Artifact files stored in the external artifact store (location and organization are implementation-specific)
2. A new source record `{uuid}.md` in `sources/` with frontmatter populated, SHA-256 hashes computed for each artifact, and `status: stub` (no body content)

**Key principles:**

- Capture is the **only step requiring network access**. Everything downstream is offline.
- Capture assigns identity (UUID) but makes no organizational decisions beyond content type and basic metadata.
- Failed captures do not leave records in the store. The UUID is only assigned when artifacts are successfully acquired.
- All associated content from the origin is captured — every file becomes a reference in `artifact_refs` with its SHA-256 hash.
- Capture metadata (timestamp, origin URL, scraper version) is recorded in frontmatter.

Content to be captured may be tracked externally (a backlog, a spreadsheet, a task list). The store itself only contains records for content that has been captured.

### 4.2 Normalize

Normalization transforms a stub record into a complete, useful markdown document. It has two sub-steps: **conversion** (deterministic) and **contextualization** (LLM-driven).

#### 4.2.1 Conversion

**What:** Deterministic conversion of artifact content into markdown.

**How:** Content-type-specific scripts — no LLM involvement, deterministic and reproducible. Conversion reads the external artifact(s) referenced by `artifact_refs` and produces the markdown body of the record.

**Output:** The body of `{uuid}.md` is filled with the artifact's content as well-formed markdown. `status` set to `draft`.

**Format-specific handling:**

| Artifact format | Conversion output |
|-----------------|-------------------|
| HTML page | Clean content; strip navigation, styling, chrome |
| Forum thread HTML | Parse post boundaries, usernames, dates |
| PDF | Text and table extraction |
| Image | `![alt text](artifact_ref)` embed |
| Audio / video | Transcription (Whisper, etc.) with timestamps |
| epub | Parse chapter structure, extract text |
| Clean markdown / text | Passthrough (`conversion_method: passthrough`) |

Trivial conversion is fine. A clean text file gets `conversion_method: "passthrough"` — the pipeline is uniform even when a step does minimal work.

**Conversion provenance.** The `conversion_method`, `conversion_tool`, and `conversion_date` fields enable targeted bulk re-conversion when tools improve (e.g., "re-convert all records processed by `tesseract v4` with `tesseract v5`").

#### 4.2.2 Contextualization

**What:** LLM-driven refinement of record content.

**How:** An LLM agent loads the record and its schema definition, then refines the content with semantic understanding. For document records (after merge), the agent loads all constituent records together for cross-record awareness.

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

1. **Discover candidates.** LLM-assisted or manual. After normalizing a batch, a discovery pass identifies records about the same subject. "These three sources are all about the same Gorguts album."

2. **Propose merge.** The proposal specifies which records to combine, what document content type the result should be, and an optional merge rationale. The operator approves or rejects.

3. **Create document record.** A new UUID is assigned. The record is written to `documents/{uuid}.md`. The `constituents` field lists direct child UUIDs. `record_type` is `document`. `content_type` is from the document type enum.

4. **Normalize the document.** The normalizer loads all constituent records and assembles enriched content drawing on all of them, producing the document's markdown body. The document is richer than any individual constituent because it draws on all of them and is free to synthesize across sources.

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

**What:** Materialize the store into a browsable or publishable form.

**How:** A build process reads the store and produces output suitable for consumption (static site, browsable vault, or other format).

**Processing order:** Reverse topological sort of the DAG:

1. For each source record, resolve `artifact_refs` to actual files (download or symlink from external storage)
2. For document records, make constituent records accessible (symlink or copy)
3. Generate index and navigation structures appropriate to the output format

**URL-to-UUID resolution.** The build process can generate a lookup index mapping origin URLs to UUIDs, enabling consumers to find records by the URL they were captured from. Both the original origin URL and the record's UUID serve as stable entry points.

Build is an implementation detail — this spec defines what the store contains, not how it's published. The build system reads markdown files and metadata, and produces whatever output format is appropriate.

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

The pipeline is operated by specialized agents — lightweight, single-purpose workers that each handle one item per invocation. Agents have focused responsibilities, process exactly one item, and report results to a coordinator. There is no inter-agent communication and no shared state beyond the store filesystem.

Agents reference schema files for the content types they're processing, ensuring normalization guidance and formatting standards are applied consistently.

### 5.2 Ingestor

Handles capture and record stub creation for a single content item.

**Model class:** Haiku-tier (fast, cheap — no creative judgment needed)

**Scope:** One content item per invocation

**Responsibilities:**

1. Run the appropriate capture script to acquire artifacts from the external source
2. Store artifacts in the external artifact store and compute SHA-256 hashes
3. Create `{uuid}.md` in `sources/` with stub frontmatter (including `artifact_refs` with hashes)
4. Verify artifact integrity (file completeness, expected content present, hashes recorded)
5. Report results: success/failure, UUID assigned, artifact count, any warnings

The ingestor receives instructions about what to capture. It is a reliable executor, not a decision maker — it does not choose what to ingest or how to classify content.

### 5.3 Normalizer

Transforms record stubs into fully normalized records, handling both conversion and contextualization.

**Model class:** Sonnet-tier (creative judgment required for contextualization, issue surfacing, description generation)

**Scope:** One record per invocation. For document records, all constituent records are loaded for cross-record awareness.

**Responsibilities:**

1. **Conversion.** For source records with `status: stub`, run the appropriate conversion script to fill the markdown body. Set `status: draft`. This step shells out to deterministic tooling.
2. **Contextualization.** Refine content with LLM judgment, following the content type's schema for normalization guidance. For source records: achieve accurate representation without adding information. For document records: synthesize across constituents. Surface issues. Generate or refine `description`. Assess `credibility_tier`. Set `status: normalized`.
3. **Self-verify.** Validate frontmatter against the content type schema. Check for broken artifact references. Verify SHA-256 hashes if artifacts are locally available.

### 5.4 Merger

Creates document records from related source records.

**Model class:** Sonnet-tier (semantic judgment required for candidate discovery and assembly)

**Scope:** One merge operation per invocation

**Responsibilities:**

1. **Candidate discovery** (when prompted). Given a set of records, identify groups that represent the same subject. Present candidates to operator for approval.
2. **Create document record.** Assign UUID, write `{uuid}.md` to `documents/`, populate frontmatter with `constituents`, `content_type`, and core fields.
3. **Assemble document content.** Load all constituent records and produce enriched markdown that draws on all of them. Structure the body according to the document content type's schema.

### 5.5 Curator

Autonomous orchestration skill that assesses store state, prioritizes work, and dispatches agents.

**Operating loop:**

1. **Assess.** Scan `sources/` and `documents/` for record statuses (`stub`, `draft`, `normalized`), unresolved issues, merge candidates, and re-normalization opportunities.
2. **Prioritize.** Apply decision framework: compendium blockers first, then high-priority new captures, then normalization of existing stubs, then merge candidates, then re-normalization.
3. **Propose.** Present the prioritized work plan to the operator for approval.
4. **Execute.** Spawn ingestor, normalizer, and merger agents, managing parallelism by launching multiple agents concurrently.
5. **Report.** Summarize results — records captured, normalized, merged, issues encountered.

### 5.6 Parallelism Model

- The **Curator** (or human operator) decides concurrency based on available resources and rate limits.
- Each agent processes one item. The Curator spawns N agents in parallel for N items.
- Agents do not communicate with each other. They read from and write to the store, and the Curator sequences work to avoid conflicts (e.g., not normalizing a document whose constituents are still being captured).
- Typical session: spawn 5 ingestors in parallel → wait for completion → spawn 5 normalizers for the new stubs → spawn merger for identified candidates.

### 5.7 Deterministic vs. LLM Boundary

| Operation | Type | Rationale |
|-----------|------|-----------|
| Capture (download, scrape) | Deterministic | Reproducible, scriptable, no judgment needed |
| Hash computation (SHA-256) | Deterministic | Mechanical integrity check |
| Conversion (HTML→MD, PDF→text, OCR, transcription) | Deterministic | Reproducible, tool-specific, no editorial judgment |
| Contextualization (refine, describe, assess, surface issues) | LLM | Requires semantic understanding and editorial judgment |
| Merge candidate discovery | LLM | Requires semantic matching across records |
| Document assembly (from constituents) | LLM | Requires editorial decisions about structure and emphasis |
| Re-normalization (context flow) | LLM | Requires contextual understanding from parent records |
| Build (export, index, symlink) | Deterministic | Mechanical, reproducible |

The boundary is clear: **if the operation could produce different valid outputs depending on judgment, it's LLM-driven. If the output is deterministic given the input, it's scripted.** This enables independent re-processing — you can re-convert with better tools without re-contextualizing, and vice versa.

---

## 6. Compendium Layer

### 6.1 What a Compendium Is

A **compendium** is a curated synthesis of records into a domain-specific reference work. Where records preserve and normalize source material faithfully, compendiums apply editorial judgment to produce coherent, structured knowledge.

A compendium is opinionated. It has a defined scope, a point of view, and a domain taxonomy. Multiple compendiums can draw from the same records and produce different works — an economics compendium and a socialism compendium might both use records from the same academic sources, selecting different subsets and synthesizing from different perspectives.

### 6.2 How Compendiums Use Records

Compendiums select records from the store and synthesize them into chapters organized by a domain taxonomy:

1. **Select records.** Using record descriptions, tags, and content types, identify records relevant to the compendium's domain. Document records (merges) are preferred because they're already enriched, but source records can also be selected directly.
2. **Organize by taxonomy.** Group selected records by the compendium's chapter structure. The taxonomy follows the domain's natural organization (by vehicle system for automotive, by character/faction/theme for fiction, by theory/era for economics).
3. **Synthesize chapters.** Distill grouped records into coherent prose, reconciling conflicts, identifying patterns, and citing record UUIDs.
4. **Build navigation.** Generate cross-references and supplementary sections (FAQ, glossary, quick reference).

### 6.3 Synthesis Principles

- **Cite records.** Every factual claim references the UUID(s) it derives from. The reader can always trace a claim back to a specific record.
- **Represent disagreement.** When records conflict, the compendium presents both positions with their respective credibility tiers rather than silently choosing one.
- **Aggregate patterns.** If 40 forum posts describe the same failure mode, the compendium captures the pattern (common mileage range, symptoms, root cause) rather than citing each post individually.
- **Respect credibility tiers.** Higher-tier records carry more weight. An `authoritative` document is not overruled by `anecdotal` reports unless the volume and consistency of community experience is overwhelming.
- **Respect issues.** Records with unresolved `critical` or `major` issues should be weighted accordingly and gaps noted.
- **Leverage relations.** Records that declare `contradicts`, `supersedes`, or `references` relationships provide direct synthesis signals.

### 6.4 System Prompts

Each compendium has a **synthesis system prompt** — a document encoding domain-specific knowledge: scope boundaries, key relationships, document selection criteria, and synthesis guidelines.

System prompts are iterable. When synthesis produces gaps or errors, the system prompt is refined and synthesis is re-run: **synthesize → review → refine prompt → re-synthesize**.

### 6.5 Incremental Re-synthesis

Compendiums track which records were used to produce each chapter and the `normalization_date` of each record at the time of synthesis. When records are re-normalized or new records are added, only affected chapters need re-synthesis.

A record that has been re-normalized (new `normalization_date`) triggers re-synthesis only in chapters that cite it. This keeps re-synthesis proportional to actual content change, not to store-wide activity.

---

## Appendix A: Content Type Reference

This appendix provides a reference snapshot of the initial content types. The schema files in `schema/` are authoritative — they define the full specification including normalization guidance and formatting standards. This appendix shows the extended fields and representative examples for each type.

Content types are a closed enum. Adding a new type requires creating a schema file. Types may gain subtypes over time (e.g., `forum_post.xenforo`) for more specific normalization guidance.

### A.1 Source Content Types

Source content types are **origin-oriented** — they describe what was captured and guide conversion.

---

#### `forum_post`

Threaded forum discussion from sites like G8Board, LS1Tech, or similar.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `username` | yes | string | Exact username of the poster |
| `thread_url` | yes | string | Direct link to the thread |
| `reply_count` | no | int | Number of replies — engagement signal |

```yaml
---
uuid: "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c"
title: "AFM Delete Guide with Dyno Results"
description: "Detailed walkthrough of AFM/DoD delete on an L76 6.0L, including before/after dyno numbers and part list."
record_type: source
content_type: forum_post
status: normalized
tags: ["afm-delete", "l76", "engine"]

origin_url: "https://www.g8board.com/threads/afm-delete-guide.56789/"
origin_name: "G8Board.com"
capture_date: 2026-03-01
artifact_refs:
  - uri: "artifacts://g8board/56789/thread.html"
    sha256: "e3b0c44298fc1c149afbf4c8996fb924..."
date_published: 2023-08-15

credibility_tier: community_validated
normalization_confidence: 0.92
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-01
conversion_method: "g8board-scraper"
conversion_tool: "scrape_thread.py v0.6"
conversion_date: 2026-03-01

username: "LS3SwapKing"
thread_url: "https://www.g8board.com/threads/afm-delete-guide.56789/"
reply_count: 47
---

## AFM Delete Procedure

The Active Fuel Management (AFM) system on the L76 can be fully deleted...
```

---

#### `reddit_post`

Reddit thread. Separated from `forum_post` because Reddit's voting system provides a distinct credibility signal.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `username` | yes | string | Reddit username |
| `subreddit` | yes | string | Subreddit without the `r/` prefix |
| `post_url` | yes | string | Permalink to the post |
| `score` | no | int | Net upvotes — engagement and credibility signal |
| `comment_count` | no | int | Number of comments |

```yaml
---
uuid: "r2d3e4f5-a6b7-4c8d-9e0f-1a2b3c4d5e6f"
title: "BSG S04E20 Daybreak Discussion Thread"
description: "Reddit discussion of the BSG series finale with 200+ comments analyzing the ending, character arcs, and thematic resolution."
record_type: source
content_type: reddit_post
status: normalized
tags: ["bsg", "series-finale", "discussion"]

origin_url: "https://www.reddit.com/r/BSG/comments/abc123/"
origin_name: "r/BSG"
capture_date: 2026-03-10
artifact_refs:
  - uri: "artifacts://reddit/bsg/abc123/thread.json"
    sha256: "9f86d081884c7d659a2feaa0c55ad015..."
date_published: 2024-06-15

credibility_tier: community_validated
normalization_confidence: 0.88
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-10
conversion_method: "reddit-api"
conversion_tool: "reddit_scraper.py v1.2"
conversion_date: 2026-03-10

username: "CylonHunter42"
subreddit: "BSG"
post_url: "https://www.reddit.com/r/BSG/comments/abc123/"
score: 342
comment_count: 218
---

## Series Finale Discussion

The finale's resolution divided the fanbase...
```

---

#### `web_article`

Article, blog post, or wiki page from the web.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `article_url` | yes | string | Link to the article |
| `publication` | no | string | Name of the outlet or site |

```yaml
---
uuid: "w3e4f5g6-h7i8-4j9k-0l1m-2n3o4p5q6r7s"
title: "Why Direct Injection Causes Carbon Buildup"
description: "Technical explainer on the mechanism by which direct injection engines accumulate carbon deposits on intake valves and available solutions."
record_type: source
content_type: web_article
status: normalized
tags: ["direct-injection", "carbon-buildup", "engine"]

origin_url: "https://www.engineeringexplained.com/carbon-buildup"
origin_name: "Engineering Explained"
capture_date: 2026-02-20
artifact_refs:
  - uri: "artifacts://engineering-explained/carbon-buildup/page.html"
    sha256: "a7ffc6f8bf1ed76651c14756a061d662..."
  - uri: "artifacts://engineering-explained/carbon-buildup/diagram_01.png"
    sha256: "d7a8fbb307d7809469ca9abcb0082e4f..."
date_published: 2023-11-03
author: "Jason Fenske"

credibility_tier: expert
normalization_confidence: 0.96
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-20
conversion_method: "web-scraper"
conversion_tool: "single_page.py v0.3"
conversion_date: 2026-02-20

article_url: "https://www.engineeringexplained.com/carbon-buildup"
publication: "Engineering Explained"
---

## The Direct Injection Carbon Problem

Direct injection engines spray fuel directly into the combustion chamber...
```

---

#### `video`

Video content — YouTube, instructional, documentary, etc.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `duration_seconds` | yes | int | Video length |
| `channel_name` | no | string | Channel or creator name |
| `platform` | no | string | Hosting platform (YouTube, Vimeo, etc.) |

```yaml
---
uuid: "v4f5g6h7-i8j9-4k0l-1m2n-3o4p5q6r7s8t"
title: "Engineering Explained — Carbon Buildup Explainer"
description: "Video explainer covering why direct injection engines accumulate carbon on intake valves, with visual demonstrations and solution comparison."
record_type: source
content_type: video
status: normalized
tags: ["direct-injection", "carbon-buildup", "video"]

origin_url: "https://youtube.com/watch?v=xyz123"
origin_name: "Engineering Explained"
capture_date: 2026-02-20
artifact_refs:
  - uri: "artifacts://youtube/xyz123/video.mp4"
    sha256: "b94d27b9934d3e08a52e52d7da7dabfa..."
  - uri: "artifacts://youtube/xyz123/thumbnail.jpg"
    sha256: "2cf24dba5fb0a30e26e83b2ac5b9e29e..."
date_published: 2023-10-15
author: "Jason Fenske"

credibility_tier: expert
normalization_confidence: 0.85
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-20
conversion_method: "whisper-transcription"
conversion_tool: "whisper-large-v3"
conversion_date: 2026-02-20

duration_seconds: 782
channel_name: "Engineering Explained"
platform: "YouTube"
---

## Transcript

[00:00] Hey guys, today we're talking about why direct injection
engines have a carbon buildup problem...
```

---

#### `audio`

Audio content — podcast episodes, audiobook chapters, radio segments.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `duration_seconds` | yes | int | Audio length |
| `series_name` | no | string | Name of the show or series |
| `episode_number` | no | int | Episode number |

```yaml
---
uuid: "a5g6h7i8-j9k0-4l1m-2n3o-4p5q6r7s8t9u"
title: "Ron D. Moore BSG Podcast — S01E01 33"
description: "Showrunner Ron D. Moore's audio commentary on the BSG premiere episode, covering production decisions, casting, and the 33-minute concept."
record_type: source
content_type: audio
status: normalized
tags: ["bsg", "podcast", "production", "ron-moore"]

origin_url: "https://example.com/rdm-podcast/s01e01.mp3"
origin_name: "Ron D. Moore BSG Podcast"
capture_date: 2026-03-05
artifact_refs:
  - uri: "artifacts://rdm-podcast/s01e01.mp3"
    sha256: "ef2d127de37b942baad06145e54b0c61..."
date_published: 2005-01-21
author: "Ronald D. Moore"

credibility_tier: authoritative
normalization_confidence: 0.82
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-05
conversion_method: "whisper-transcription"
conversion_tool: "whisper-large-v3"
conversion_date: 2026-03-05

duration_seconds: 2640
series_name: "Battlestar Galactica Podcast"
episode_number: 1
---

## Transcript

[00:00] Welcome to the Battlestar Galactica podcast. I'm Ron Moore...
```

---

#### `pdf_document`

PDF capture — service manuals, academic papers, technical bulletins, datasheets.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `page_count` | yes | int | Number of pages |
| `document_type` | no | string | `manual_section`, `bulletin`, `paper`, `datasheet`, `report` |

```yaml
---
uuid: "p6h7i8j9-k0l1-4m2n-3o4p-5q6r7s8t9u0v"
title: "GM TSB PI0597B — Steering Intermediate Shaft Clunk"
description: "General Motors technical service bulletin addressing a clunk noise from the steering intermediate shaft on 2008-2009 Pontiac G8 and related platforms."
record_type: source
content_type: pdf_document
status: normalized
tags: ["steering", "tsb", "intermediate-shaft", "pontiac-g8"]

origin_url: "https://gm.com/bulletins/PI0597B.pdf"
origin_name: "General Motors"
capture_date: 2026-02-10
artifact_refs:
  - uri: "artifacts://gm/bulletins/PI0597B.pdf"
    sha256: "c3ab8ff13720e8ad9047dd39466b3c89..."
date_published: 2009-03-15

credibility_tier: authoritative
normalization_confidence: 0.91
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-10
conversion_method: "pdf-extraction"
conversion_tool: "pdfplumber v0.10"
conversion_date: 2026-02-10

page_count: 3
document_type: "bulletin"
---

## PI0597B — Steering Column Intermediate Shaft

**Affected vehicles:** 2008-2009 Pontiac G8 (all trims)

**Condition:** A clunk or pop noise from the steering column area...
```

---

#### `epub`

Ebook capture — novels, non-fiction, collected works.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Canonical title of the work |
| `isbn` | no | string | ISBN if known |
| `word_count` | no | int | Total word count |
| `series_name` | no | string | Name of the series |
| `series_position` | no | int | Position in the series |

```yaml
---
uuid: "e7i8j9k0-l1m2-4n3o-4p5q-6r7s8t9u0v1w"
title: "Dune (epub)"
description: "Frank Herbert's 1965 science fiction novel about ecology, politics, and prescience on the desert planet Arrakis."
record_type: source
content_type: epub
status: normalized
tags: ["dune", "frank-herbert", "science-fiction"]

origin_name: "Digital library"
original_filename: "Frank_Herbert_Dune.epub"
capture_date: 2026-01-15
artifact_refs:
  - uri: "artifacts://books/frank-herbert/dune.epub"
    sha256: "6b86b273ff34fce19d6b804eff5a3f57..."
date_published: 1965-08-01
author: "Frank Herbert"

credibility_tier: authoritative
normalization_confidence: 0.98
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-01-20
conversion_method: "epub-parser"
conversion_tool: "ebooklib v0.18"
conversion_date: 2026-01-20

work_title: "Dune"
isbn: "978-0-441-17271-9"
word_count: 187000
series_name: "Dune Chronicles"
series_position: 1
---

## Book One: Dune

In the week before their departure for Arrakis...
```

---

#### `image`

Captured image — photo, diagram, screenshot, scan.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `dimensions` | no | string | Width x height in pixels (e.g., "1920x1080") |
| `subject` | no | string | What the image depicts |

```yaml
---
uuid: "i8j9k0l1-m2n3-4o4p-5q6r-7s8t9u0v1w2x"
title: "G8 Rear Subframe Dropout — Annotated"
description: "Annotated photograph of a Caprice PPV rear subframe dropout showing mounting points, bushing locations, and ABS sensor routing."
record_type: source
content_type: image
status: normalized
tags: ["suspension", "rear-subframe", "ppv", "photo"]

origin_name: "G8Board.com user upload"
capture_date: 2026-02-16
artifact_refs:
  - uri: "artifacts://g8board/290127/subframe_annotated.jpg"
    sha256: "d4735e3a265e16eee03f59718b9b5d03..."

credibility_tier: community_validated
normalization_confidence: 0.90
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-16
conversion_method: "image-embed"
conversion_tool: "passthrough"
conversion_date: 2026-02-16

dimensions: "2048x1536"
subject: "Caprice PPV rear subframe dropout, annotated mounting points"
---

![Annotated PPV rear subframe showing mounting points and ABS sensor routing](artifacts://g8board/290127/subframe_annotated.jpg)

Mounting points are circled in red. The ABS sensor wire routes along the
upper control arm bracket (yellow arrow).
```

---

#### `metadata_page`

Structured reference page from a database site — Metal Archives, RateYourMusic, IMDB, Wikipedia, Discogs.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `source_site` | yes | string | Which site (e.g., "Metal Archives", "RYM", "IMDB") |
| `page_type` | yes | string | What kind of page (e.g., "band", "album", "artist", "film", "episode") |

```yaml
---
uuid: "m9k0l1m2-n3o4-4p5q-6r7s-8t9u0v1w2x3y"
title: "Gorguts — Metal Archives Page"
description: "Metal Archives entry for Gorguts covering discography, lineup history, genre classification, and related artists."
record_type: source
content_type: metadata_page
status: normalized
tags: ["gorguts", "death-metal", "discography"]

origin_url: "https://www.metal-archives.com/bands/Gorguts/1124"
origin_name: "Metal Archives"
capture_date: 2026-03-10
artifact_refs:
  - uri: "artifacts://metal-archives/bands/gorguts/page.html"
    sha256: "4e07408562bedb8b60ce05c1decfe3ad..."
  - uri: "artifacts://metal-archives/bands/gorguts/logo.jpg"
    sha256: "4b227777d4dd1fc61c6f884f48641d02..."

credibility_tier: community_validated
normalization_confidence: 0.94
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-10
conversion_method: "web-scraper"
conversion_tool: "ma_scraper.py v1.0"
conversion_date: 2026-03-10

source_site: "Metal Archives"
page_type: "band"
---

## Gorguts

**Country of origin:** Canada
**Location:** Sherbrooke, Quebec
**Status:** Active
**Formed in:** 1989
**Genre:** Technical Death Metal, Avant-garde Metal

### Discography

| Year | Title | Type |
|------|-------|------|
| 1991 | Considered Dead | Full-length |
| 1993 | The Erosion of Sanity | Full-length |
| 1998 | Obscura | Full-length |
| 2001 | From Wisdom to Hate | Full-length |
| 2013 | Colored Sands | Full-length |
| 2016 | Pleiades' Dust | EP |
```

---

#### `screenplay`

Film, television, or stage script.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Title of the production |
| `medium` | yes | enum | `film`, `television`, `stage` |
| `draft` | no | string | Which draft, if known |

```yaml
---
uuid: "s0l1m2n3-o4p5-4q6r-7s8t-9u0v1w2x3y4z"
title: "Dune: Part One — Shooting Script"
description: "Denis Villeneuve and Jon Spaihts' shooting script for Dune: Part One (2021), covering the first half of Frank Herbert's novel."
record_type: source
content_type: screenplay
status: normalized
tags: ["dune", "villeneuve", "screenplay", "2021"]

origin_name: "Awards screener archive"
original_filename: "Dune_Part_One_Shooting_Script.pdf"
capture_date: 2026-02-01
artifact_refs:
  - uri: "artifacts://screenplays/dune-part-one/script.pdf"
    sha256: "ef797c8118f02dfb649607dd5d3f8c76..."
date_published: 2021-01-01
author: "Denis Villeneuve, Jon Spaihts"

credibility_tier: authoritative
normalization_confidence: 0.88
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-05
conversion_method: "pdf-extraction"
conversion_tool: "pdfplumber v0.10"
conversion_date: 2026-02-05

work_title: "Dune: Part One"
medium: "film"
draft: "shooting script"
---

## FADE IN:

EXT. CALADAN — CLIFFS — DAY

A black hawk lands on a rocky promontory...
```

---

#### `product_documentation`

Product datasheets, catalogs, user guides, safety data sheets.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `product_name` | yes | string | Name of the product |
| `manufacturer` | yes | string | Who makes it |
| `document_type` | no | enum | `datasheet`, `catalog`, `guide`, `sds` |
| `part_numbers` | no | string[] | Associated part numbers |

```yaml
---
uuid: "d1m2n3o4-p5q6-4r7s-8t9u-0v1w2x3y4z5a"
title: "Penrite HPR 5 — Product Data Sheet"
description: "Technical data sheet for Penrite HPR 5 5W-40 full synthetic engine oil including specifications, approvals, and application guide."
record_type: source
content_type: product_documentation
status: normalized
tags: ["penrite", "engine-oil", "5w-40", "datasheet"]

origin_url: "https://www.penriteoil.com.au/products/hpr-5"
origin_name: "Penrite"
capture_date: 2026-02-25
artifact_refs:
  - uri: "artifacts://penrite/hpr5/datasheet.pdf"
    sha256: "e7f6c011776e8db7cd330b54174fd76f..."

credibility_tier: authoritative
normalization_confidence: 0.93
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-25
conversion_method: "pdf-extraction"
conversion_tool: "pdfplumber v0.10"
conversion_date: 2026-02-25

product_name: "HPR 5 5W-40"
manufacturer: "Penrite"
document_type: "datasheet"
part_numbers: ["HPR05005", "HPR05020"]
---

## Penrite HPR 5 — 5W-40 Full Synthetic

**Description:** Premium full synthetic engine oil suitable for
high-performance naturally aspirated and turbocharged engines...
```

---

### A.2 Document Content Types

Document content types are **concept-oriented** — they describe what the merged record represents. Document records always have a `constituents` field listing their direct child UUIDs.

---

#### `novel`

A complete literary work — a novel, novella, or standalone non-fiction book.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Canonical title |
| `author_name` | yes | string | Primary author |
| `year_published` | no | int | Year of first publication |
| `series_name` | no | string | Series name if part of a series |
| `series_position` | no | int | Position in the series |

```yaml
---
uuid: "n2o3p4q5-r6s7-4t8u-9v0w-1x2y3z4a5b6c"
title: "Dune"
description: "Frank Herbert's 1965 science fiction novel — the definitive merged record combining the epub text, audiobook transcription, and critical edition annotations."
record_type: document
content_type: novel
status: normalized
tags: ["dune", "frank-herbert", "science-fiction", "1965"]

constituents:
  - "e7i8j9k0-l1m2-4n3o-4p5q-6r7s8t9u0v1w"  # epub capture
  - "a8b9c0d1-e2f3-4a4b-5c6d-7e8f9a0b1c2d"  # audiobook transcription
  - "f2g3h4i5-j6k7-4l8m-9n0o-1p2q3r4s5t6u"  # critical edition annotations
merge_rationale: "Combining all format representations and annotations of Dune into a definitive record"

credibility_tier: authoritative
normalization_confidence: 0.97
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-02-01

work_title: "Dune"
author_name: "Frank Herbert"
year_published: 1965
series_name: "Dune Chronicles"
series_position: 1

relations:
  - type: preceded_by
    target: "x5y6z7a8-b9c0-4d1e-2f3a-4b5c6d7e8f9a"
---

## Dune

*Dune* is a 1965 science fiction novel by Frank Herbert...
```

---

#### `song`

A musical composition — the concept, not any single source.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `song_title` | yes | string | Track title |
| `artist_name` | yes | string | Performing artist |
| `album_name` | no | string | Album it appears on |
| `track_number` | no | int | Position on the album |
| `duration_seconds` | no | int | Track length |

```yaml
---
uuid: "q3r4s5t6-u7v8-4w9x-8y0z-1a2b3c4d5e6f"
title: "Obscura (track)"
description: "Title track from Gorguts' 1998 album, featuring extreme dissonance and unconventional song structure. Lyrics, transcription, and metadata combined."
record_type: document
content_type: song
status: normalized
tags: ["gorguts", "obscura", "death-metal"]

constituents:
  - "x1y2z3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a"  # lyrics from darklyrics.com
  - "b5c6d7e8-f9a0-4b1c-2d3e-4f5a6b7c8d9e"  # audio transcription of live performance
  - "f9g0h1i2-j3k4-4l5m-6n7o-8p9q0r1s2t3u"  # RYM track page
merge_rationale: "All records for the track Obscura by Gorguts"

credibility_tier: authoritative
normalization_confidence: 0.85
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-15

song_title: "Obscura"
artist_name: "Gorguts"
album_name: "Obscura"
track_number: 2
duration_seconds: 234
---

## Obscura

**Track 2** on *Obscura* (1998). 3:54.

### Lyrics

Immersed in the obscure infinity...

### Musical Analysis

The track opens with a heavily dissonant chord voicing...
```

---

#### `album`

A musical release — studio album, EP, live album, compilation.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `artist_name` | yes | string | Performing artist |
| `release_date` | no | int | Year of release |
| `label` | no | string | Record label |
| `track_count` | no | int | Number of tracks |
| `genre` | no | string[] | Genre classifications |

Full example provided in section 3.4 (Document Record example).

---

#### `artist`

A musical artist or band — biography, discography, and associated material.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `artist_name` | yes | string | Artist or band name |
| `origin_country` | no | string | Country of origin |
| `years_active` | no | string | Active years (e.g., "1989–present") |
| `genre` | no | string[] | Primary genres |

```yaml
---
uuid: "k1l2m3n4-o5p6-4q7r-8s9t-0u1v2w3x4y5z"
title: "Gorguts"
description: "Canadian technical/avant-garde death metal band formed in 1989. Complete profile merging discography, lineup history, and critical reception from multiple sources."
record_type: document
content_type: artist
status: normalized
tags: ["gorguts", "death-metal", "technical", "canada"]

constituents:
  - "m9k0l1m2-n3o4-4p5q-6r7s-8t9u0v1w2x3y"  # Metal Archives band page
  - "o3p4q5r6-s7t8-4u9v-0w1x-2y3z4a5b6c7d"  # RYM artist page
  - "s7t8u9v0-w1x2-4y3z-4a5b-6c7d8e9f0a1b"  # Wikipedia article
  - "9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e"  # album: Obscura
  - "w1x2y3z4-a5b6-4c7d-8e9f-0a1b2c3d4e5f"  # album: Colored Sands
  - "a5b6c7d8-e9f0-4a1b-2c3d-4e5f6a7b8c9d"  # album: The Erosion of Sanity
merge_rationale: "Comprehensive Gorguts artist profile from all available sources and album documents"

credibility_tier: community_validated
normalization_confidence: 0.91
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-17

artist_name: "Gorguts"
origin_country: "Canada"
years_active: "1989–present"
genre: ["technical death metal", "avant-garde metal"]
---

## Gorguts

Gorguts is a Canadian technical death metal band formed in 1989
in Sherbrooke, Quebec by guitarist and vocalist Luc Lemay...

### Discography

#### Obscura (1998)

The album that redefined what death metal could be...
```

---

#### `tv_episode`

A television episode — combining transcript, summaries, discussion, and production material.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `series_name` | yes | string | Name of the TV series |
| `season` | yes | int | Season number |
| `episode` | yes | int | Episode number within the season |
| `episode_title` | yes | string | Episode title |
| `air_date` | no | date | Original air date |
| `director` | no | string | Director |
| `writer` | no | string | Writer(s) |

```yaml
---
uuid: "t5u6v7w8-x9y0-4z1a-2b3c-4d5e6f7a8b9c"
title: "BSG S01E01 — 33"
description: "Premiere episode of Battlestar Galactica. The fleet jumps every 33 minutes to evade Cylon pursuit. Comprehensive record combining transcript, Wikipedia summary, Reddit discussion, and showrunner commentary."
record_type: document
content_type: tv_episode
status: normalized
tags: ["bsg", "season-1", "premiere"]

constituents:
  - "x9y0z1a2-b3c4-4d5e-6f7a-8b9c0d1e2f3a"  # episode transcript
  - "b3c4d5e6-f7a8-4b9c-0d1e-2f3a4b5c6d7e"  # Wikipedia episode summary
  - "r2d3e4f5-a6b7-4c8d-9e0f-1a2b3c4d5e6f"  # Reddit discussion thread
  - "a5g6h7i8-j9k0-4l1m-2n3o-4p5q6r7s8t9u"  # Ron D. Moore podcast commentary
merge_rationale: "All available records for BSG S01E01"

credibility_tier: authoritative
normalization_confidence: 0.88
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-15

series_name: "Battlestar Galactica"
season: 1
episode: 1
episode_title: "33"
air_date: 2005-01-14
director: "Michael Rymer"
writer: "Ronald D. Moore"
---

## 33

The fleet has been on the run for five days, jumping every 33 minutes
to stay ahead of Cylon pursuit...

### Transcript Excerpts

**ADAMA:** It's been 237 jumps, and the Cylons keep finding us...

### Production Notes

Ron D. Moore explains in his podcast commentary that the 33-minute
concept emerged from wanting to show the crew under extreme fatigue...
```

---

#### `technical_reference`

Merged technical documentation — service manual sections, bulletins, and community knowledge combined into a comprehensive reference.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `subject` | yes | string | What this reference covers |
| `systems` | no | string[] | Technical systems involved |
| `applicable_models` | no | string[] | Models or products this applies to |

```yaml
---
uuid: "r6s7t8u9-v0w1-4x2y-3z4a-5b6c7d8e9f0a"
title: "G8/VE Rear Wheel Bearing Reference"
description: "Comprehensive rear wheel bearing reference for the Pontiac G8 / VE Commodore platform, combining OEM service manual procedures, TSB guidance, and community-validated techniques."
record_type: document
content_type: technical_reference
status: normalized
tags: ["wheel-bearing", "rear", "suspension", "pontiac-g8"]

constituents:
  - "7a3f2b1c-4d5e-4f6a-8b9c-0d1e2f3a4b5c"  # forum: rear suspension rebuild
  - "p6h7i8j9-k0l1-4m2n-3o4p-5q6r7s8t9u0v"  # GM TSB PI0597B
  - "v0w1x2y3-z4a5-4b6c-7d8e-9f0a1b2c3d4e"  # service manual section
  - "z4a5b6c7-d8e9-4f0a-1b2c-3d4e5f6a7b8c"  # forum: bearing failure symptoms
  - "d8e9f0g1-h2i3-4j4k-5l6m-7n8o9p0q1r2s"  # forum: PPV subframe swap
merge_rationale: "All records related to rear wheel bearings on the G8/VE platform"

credibility_tier: community_validated
normalization_confidence: 0.92
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-17

subject: "Rear wheel bearing diagnosis, replacement, and upgrade"
systems: ["suspension", "hub-assembly", "abs"]
applicable_models: ["2008-2009 Pontiac G8", "VE Commodore"]
---

## Rear Wheel Bearings — G8/VE Platform

### Failure Symptoms

The most common symptom is a humming or grinding noise from the rear
that increases with speed...

### OEM Procedure

The service manual specifies...

### Community-Validated Alternatives

The Caprice PPV subframe swap provides an alternative that replaces
the entire rear suspension assembly...
```

---

#### `research_work`

An academic work — paper plus supplementary data, errata, and related material.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Title of the work |
| `authors` | yes | string[] | Author list |
| `journal` | no | string | Publication venue |
| `year_published` | no | int | Year of publication |
| `doi` | no | string | DOI if available |
| `peer_reviewed` | no | bool | Whether the work is peer-reviewed |

```yaml
---
uuid: "w8x9y0z1-a2b3-4c4d-5e6f-7a8b9c0d1e2f"
title: "The Tendency of the Rate of Profit to Fall"
description: "Comprehensive merged record on Marx's law of the tendency of the rate of profit to fall, combining the original Capital Vol. III text with contemporary analysis and empirical studies."
record_type: document
content_type: research_work
status: normalized
tags: ["marxism", "economics", "profit-rate", "political-economy"]

constituents:
  - "a2b3c4d5-e6f7-4a8b-9c0d-1e2f3a4b5c6d"  # Capital Vol. III, Part III
  - "e6f7g8h9-i0j1-4k2l-3m4n-5o6p7q8r9s0t"  # Michael Roberts empirical study
  - "i0j1k2l3-m4n5-4o6p-7q8r-9s0t1u2v3w4x"  # Andrew Kliman response paper
merge_rationale: "Core text and major analytical responses on the tendency of the rate of profit to fall"

credibility_tier: authoritative
normalization_confidence: 0.90
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-10

work_title: "The Tendency of the Rate of Profit to Fall"
authors: ["Karl Marx"]
year_published: 1894
peer_reviewed: false
---

## The Law of the Tendency of the Rate of Profit to Fall

Marx presents the argument in Capital, Volume III, Part III...
```
