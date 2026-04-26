# Athenaeum Architecture — v10 Change Guide

**Purpose:** Handoff to an agent tasked with updating `ARCHITECTURE.md` from v9 to v10. Describes every change, the rationale, affected sections, and concrete specification. Apply changes in order — later changes depend on earlier ones.

**Context:** v10 is a fundamental rethinking of the record model, the relationship system, and the boundary between captured content and authored knowledge. The major themes are:

1. **Artifact records replace source records.** Content-addressed by blake3 hash, one file per artifact, self-contained and portable. The artifact layer is a faithful markdown mirror of original content with cross-references resolved to blake3 wikilinks and embeds.

2. **Relations are eliminated in favor of Obsidian primitives.** `is_a`, `part_of`, `same_as`, and `constituents` are all dropped. Linking is handled by wikilinks and embeds at both layers. Tags handle classification. Similarity is computed from intrinsic properties, never stored.

3. **Two sharply separated layers.** The artifact layer faithfully represents source content with no editorialization in the body. The document layer is authored knowledge that references artifacts through functional URIs and connects to other documents through wikilinks and tags.

4. **The normalized body as universal representation.** Every artifact's text body projects its content into a common representational space, enabling computed similarity across modalities without stored relations.

5. **Per-artifact schemas.** MIME-type base schemas drive normalization and extended field extraction. Corpus-local classification schemas add domain-specific metadata. All classification is localized to the corpus.

---

## Change 0: Replace source records with content-addressed artifact records

### Rationale

v9's source record bundles multiple captured files into a single record with an `artifacts[]` array. This creates ambiguous identity (one `content_type` for a bundle of mixed media), imprecise normalization (which artifact is "primary"?), no structural dedup (the same image in fifty pages is stored fifty times), and opaque cross-references.

Content-addressed artifact records solve all four. Each captured file becomes its own record, named by its blake3 hash. One record, one file, one content type, one normalization path.

### Affected sections

This is a foundational change touching most of the spec. See the section summary at the end of this document for the full list.

### Specification

**§1.3 Terminology — replace Source Record, add Artifact Record:**

> **Artifact Record** — A record representing a single captured file, named by the blake3 hash of its binary content (`{blake3-hash}.md`). One record per file, one content type per record. The body is a normalized text rendering of the artifact. The actual binary file is stored in content-addressed storage indexed by the same hash. Artifact records are the ground truth of the corpus.
>
> **Content-Addressed Naming** — Artifact records are named by the blake3 hash of their binary content. Byte-identical files produce the same hash and therefore the same record — structural deduplication is automatic. Document records continue to use UUID-based naming.

**§2.2 Sources → §2.2 Artifacts — rewrite:**

> ### 2.2 Artifacts
>
> An artifact record represents a single captured file. It is named by the blake3 hash of the file's binary content (`{blake3-hash}.md`) and contains:
>
> - **Frontmatter:** `content_type` (MIME type), `origin_uri` (where obtained), `captures[]` (timestamped capture events), schema-extracted extended fields, and standard metadata fields.
>
> - **Body:** A normalized markdown rendering of the artifact, faithful to the original content's structure and meaning. For HTML: stripped-and-cleaned markdown preserving document structure. For audio: a transcript. For images: OCR text and/or visual description. For PDFs: extracted text with structural markup. Cross-references in the original content (hyperlinks, embedded images) are resolved to blake3 wikilinks and embeds where the targets exist in the corpus, preserving the original content's link structure. See §3.2 for body format rules.
>
> - **Binary storage:** The actual file is stored in a content-addressed store, retrievable by the same blake3 hash.
>
> **Content-addressed deduplication.** If the same file is encountered again, the hash matches an existing record. No new record is created — the existing record gains a new `captures[]` entry. Git sees a metadata-only diff.
>
> **Re-capture of changed content.** If a previously captured URL returns different content, the new content produces a different hash and a new artifact record. Both share the same `origin_uri`, making them discoverable as captures of the same origin at different points in time.
>
> **Record type.** Artifact records use `record_type: artifact`.

**§3.1.1 Core Fields — restructure for artifact records:**

Remove the `artifacts[]` array entirely. Remove `uuid` from artifact records (blake3 is the identity). Add:

| Field | Type | Required | Applies to | Description |
|-------|------|----------|------------|-------------|
| `blake3` | string | yes (artifacts) | artifact records | The blake3 hash of the artifact's binary content. 64-character lowercase hex string. Serves as the record's identity, filename stem, and content-addressed storage key. |
| `origin_uri` | string or string[] | yes (artifacts) | artifact records | The URI(s) where this file was obtained. Multiple URIs indicate the same file found at different locations. |
| `captures` | object[] | yes (artifacts) | artifact records | Timestamped capture events: `{date: ISO-8601, method: string, origin_uri: string}`. Accumulates entries when the same bytes are re-encountered. |
| `hashes` | map | no | artifact records | Auxiliary cryptographic hashes for interoperability (e.g., `md5`, `sha256`). Not used for identity or similarity. |
| `normalization_type` | string | no | artifact records | How the body was derived: `extraction` (HTML→markdown, PDF→text), `transcription` (audio/video→text), `description` (image→text), `metadata` (opaque binary→summary). |
| `uuid` | UUID | yes (documents) | document records | Standard v4 UUID. Not used on artifact records. |

Update `record_type` enum: `artifact` or `document` (replaces v9's `source`/`document`).

**§4.1 Capture — rewrite for content-addressed pipeline:**

> 1. **Fetch.** Retrieve the target and all embedded resources.
> 2. **Hash.** Compute blake3 of each file's binary content.
> 3. **Dedup check.** If `{hash}.md` exists with same `origin_uri`: append capture entry. If exists with different `origin_uri`: add origin_uri, append capture. If does not exist: create new record.
> 4. **Store binary.** Place file in content-addressed store at `{hash}.{ext}`. Idempotent.

**Example artifact record:**

```yaml
---
blake3: "a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."
title: "Caliper Rebuild Thread - G8Forum"
record_type: artifact
content_type: text/html
origin_uri: "https://g8forum.com/threads/caliper-rebuild.4521/"
captures:
  - date: 2026-03-15T14:22:00Z
    method: scrape
    origin_uri: "https://g8forum.com/threads/caliper-rebuild.4521/"
status: normalized
tags: [brake-caliper, caliper-rebuild]
credibility_tier: community
normalization_confidence: 0.92
normalization_type: extraction

# Schema-extracted extended fields (from text/html base schema)
page_title: "Caliper Rebuild Thread"
meta_description: "Discussion of front caliper rebuild on 2009 Pontiac G8 GT"
---

## Caliper Rebuild Thread

**Original post by GTO_Dave, 2024-08-12:**

Had to rebuild the front calipers on my '09 G8 GT at 180k km.
Here's what the bore looked like after pulling the piston:

![[b8c9d0e1f2a3b4c5...]]

Scoring was bad enough that I decided to replace rather than hone.
Ordered a remanufactured unit from [RockAuto](https://rockauto.com/caliper-xyz).

If you're seeing similar wear, check out the
[[c9d0e1f2a3b4c5d6...|brake bleeding procedure thread]]
before reassembling — I made the mistake of not bench-bleeding first.
```

Note: the inline image is embedded via `![[blake3-hash]]` — this embeds the image artifact's normalized text body (a visual description). The link to the bleeding thread is a wikilink to another artifact record. The RockAuto link stays as a plain URL because that page wasn't captured. No editorialization in the body — it faithfully mirrors the original forum post's structure and content.

---

## Change 1: Eliminate stored relations entirely

### Rationale

v9 used `part_of` and `same_as` as stored frontmatter relations. The v10 design conversations explored splitting `part_of` into `is_a` and `part_of`, then restricting them by layer, then recognizing that each one was either redundant with something computable or an assertion that could go stale:

- **`same_as`** was a manually maintained equivalence assertion. Replaced by three tiers of computed similarity: blake3 (exact bytes), perceptual hashes (format-specific), and body embeddings (cross-modal). No stored edge needed.

- **`is_a`** on artifacts was either redundant with `content_type` (format identity) or an interpretive classification that belongs to the corpus's schema system, not to the artifact's frontmatter. On documents, it was coupling the document to a specific concept hierarchy.

- **`part_of`** was compositional containment. In the new model, documents express composition through body prose — wikilinks and embeds referencing artifacts and other documents. The body *is* the composition; a frontmatter pointer adds nothing.

- **`constituents`** was a list of source records used during synthesis. In the new model, a document's references to artifacts are visible in its body as wikilinks and embeds. The body is the authoritative record of what the document draws on.

All structural relationships are now expressed through Obsidian primitives (wikilinks, embeds, tags) or computed from intrinsic properties. No stored relations exist. Nothing can go stale because nothing is a manually maintained assertion about a relationship between two records.

### Affected sections

- §1.3 Terminology — remove Relation definition
- §3.1.7 Relations — **delete entire section**
- §3.1.3 Document-Specific Fields — remove `constituents`
- §3.5 Classification — **major rewrite** (see Change 4)
- §3.5.1 Entity vs set — **delete**
- §3.5.2 Worked examples — **rewrite**
- §3.5.3 Deduplication — **rewrite** (see Change 2)
- All examples — remove relation fields from frontmatter

### Specification

**§3.1.7 — Delete entirely.** No relation fields exist. All inter-record references are wikilinks and embeds in body prose, or tags in frontmatter.

**§3.1.3 Document-Specific Fields — remove `constituents`.** A document's references to its source artifacts are its wikilinks and embeds. The body is the authoritative record.

**§1.3 Terminology — remove the Relation row.** Replace with:

> **Reference** — A wikilink or embed in a record's body that points to another record by blake3 hash (for artifacts) or UUID (for documents). References are the primary mechanism for expressing relationships between records. They live in the body, not in frontmatter, and are visible in Obsidian's graph and backlink views.

---

## Change 2: Define the three-tier computed similarity model

### Rationale

With all stored relations eliminated, similarity and deduplication must be computable from intrinsic artifact properties. The architecture provides three tiers, each operating on inputs already present in the record.

### Affected sections

- §3.5.3 Deduplication → rewrite as "Deduplication and Similarity"
- §1.2 Core Principles — add the normalized body principle

### Specification

**§1.2 Core Principles — add:**

> **The normalized body as universal representation.** Every artifact record carries a text body: a normalized rendering of the original file appropriate to its content type. This body projects all modalities into a common representational space — text — enabling universal computation across the corpus. Search, similarity, clustering, and embeddings all operate on this body. The body is the durable, auditable, git-versioned input; everything derived from it is ephemeral cache, rebuildable when models improve or normalization is refined.

**§3.5.3 — Rewrite as "Deduplication and Similarity":**

> Deduplication and similarity are handled entirely through intrinsic properties of artifacts, not through stored relations:
>
> **Tier 1: Blake3 (exact).** Same bytes → same hash → same record. Structural, automatic, zero-cost.
>
> **Tier 2: Perceptual hashes (format-specific, cached).** Same perceptible content, different bytes. pHash/dHash for images, chromaprint for audio, simhash for text/HTML. Computed from the binary artifact. Cached for performance, rebuildable from inputs that are already stored.
>
> **Tier 3: Body embeddings (cross-modal, cached).** The normalized body projects every modality into text. Embeddings of that text enable universal semantic similarity. An audio transcript and an HTML transcript of the same interview land near each other because their normalized text says the same things. Cached, rebuildable, model-upgradeable.
>
> All three tiers produce queries, not stored edges. The spec defines the inputs (binary artifact + normalized body); tooling builds the indices.

---

## Change 3: Define artifact-layer linking and embedding

### Rationale

Artifacts are not isolated files — they form a graph through standard markdown primitives that mirrors the original content's cross-references. When a forum post links to another thread and both were captured, the normalizer resolves the URL to a blake3 wikilink. When a page has an inline image that was captured, the normalizer embeds the image artifact's record. This makes the artifact layer a navigable knowledge base before any documents exist.

### Affected sections

- §3.2 Body Format — major expansion
- §4.2 Normalize — add cross-reference resolution
- §5.3 Normalizer — add reference resolution responsibility

### Specification

**§3.2 Body Format — add artifact linking rules:**

> #### Artifact Body Integrity
>
> An artifact's body is a faithful normalized rendering of the original content. The normalizer MUST NOT add editorial content, interpretation, or connections that did not exist in the original. The body mirrors the original's structure: its headings, paragraphs, lists, links, and embedded media, translated into markdown.
>
> #### Cross-Reference Resolution
>
> The original content's hyperlinks and embedded resources are resolved during normalization:
>
> - **Captured target exists in corpus:** Replace the URL with a blake3 wikilink or embed.
>   - Hyperlinks become wikilinks: `[[{blake3-hash}|original link text]]`
>   - Embedded images become embeds: `![[{blake3-hash}]]`
>   - Embedded media become embeds with alt text: `![[{blake3-hash}|description]]`
>
> - **Captured target does not exist:** Leave as a standard markdown URL: `[link text](https://original-url.com)` or `![alt](https://original-url.com/image.jpg)`. The link is unresolved — it points outside the corpus. If the target is captured later, a re-normalization pass can resolve it.
>
> Cross-reference resolution is the *only* way artifacts link to each other. No artifact body contains wikilinks or embeds that the normalizer invented — every link corresponds to a link or embed in the original content.
>
> #### What Embeds Mean
>
> When an artifact body contains `![[blake3-hash]]`, Obsidian renders the target artifact's body inline. For an image artifact, this means the image's normalized text (OCR, visual description) appears at the position where the original image was. For a linked document artifact, Obsidian renders the target's full body. In compiled outputs (mdbook, static site), the tooling can substitute the actual binary (render the real image, embed the real video).
>
> #### Inline Topic Annotations
>
> Artifact bodies may contain topic annotations in Obsidian-style comment blocks. These are the *only* permitted editorialization in an artifact body — they are metadata annotations classifying what the surrounding content discusses, not additions to the content.
>
> Syntax: `%% #slug %%` or `%% #slug-1 #slug-2 %%`
>
> Scoping rules:
> 1. **Frontmatter `tags`** — whole-record scope. Every line is implicitly within these topics.
> 2. **Annotation on a heading** — section scope. Applies until the next heading of equal or higher level.
> 3. **Annotation on a line** — passage scope. Applies to that specific line only.
>
> Scopes are additive. Annotate at topical transition points, not on every line.

**§4.2 Normalize — add cross-reference resolution step:**

> **Cross-reference resolution.** After producing the normalized body, the normalizer checks all hyperlinks and embedded resource references against the corpus's blake3 index. Targets that match a captured artifact are rewritten as blake3 wikilinks or embeds. Targets with no match remain as standard markdown URLs.

**§5.3 Normalizer — add responsibility:**

> **Cross-reference resolution.** For each hyperlink and embedded resource in the original content, check whether the target was captured (by URL → blake3 lookup). If captured, replace with a blake3 wikilink or embed. If not, leave as a standard URL. This is a mechanical resolution, not an editorial judgment — the normalizer does not add links that didn't exist in the original content.

---

## Change 4: Define the document layer

### Rationale

v9 underspecifies what documents actually are. In the new model, the artifact layer is the ground truth and the document layer is the knowledge layer — authored compositions that reference artifacts and connect to other documents. The document layer needs a clear specification: what a document body looks like, how it references artifacts, how documents connect to each other, and how functional URIs enable computed transformations.

### Affected sections

- §2.3 Documents — major rewrite
- §3.2 Body Format — add document body rules (complements artifact rules from Change 3)
- New §3.7 (or similar) — Functional URI Scheme
- §6 Compendiums — update for new document model

### Specification

**§2.3 Documents — rewrite:**

> ### 2.3 Documents
>
> A document record is an authored markdown composition representing synthesized knowledge. It is named by a UUID (`{uuid}.md`) and contains:
>
> - **Frontmatter:** `uuid`, `title`, `tags` (classification), and minimal metadata. Document frontmatter is deliberately thin — structural relationships live in the body.
>
> - **Body:** Authored markdown prose with wikilinks to other documents, wikilinks and embeds referencing artifacts (by blake3 hash), and optionally functional URIs for computed transformations of artifact content. The body *is* the composition — it is the authoritative record of what knowledge the document synthesizes and what evidence it draws on.
>
> Documents connect to other documents through wikilinks and tags. Documents reference artifacts through wikilinks (for citation/evidence) and embeds (for inline content inclusion). The reference direction is always document → artifact for evidence, and document ↔ document for knowledge structure.
>
> **Record type.** Document records use `record_type: document`.

**Document body rules (§3.2 addition):**

> #### Document Bodies
>
> Document bodies are authored compositions with full editorial freedom. Unlike artifact bodies (which faithfully mirror original content), document bodies are written by curators, synthesis agents, or merger processes. They may:
>
> - Add interpretation, analysis, and context that no single artifact contains.
> - Structure knowledge for a particular audience or purpose.
> - Reference artifacts as evidence using wikilinks: `[[{blake3-hash}|display text]]`
> - Embed artifact content inline: `![[{blake3-hash}]]`
> - Use functional URIs for computed transformations: `![[blake3://{hash}?params|alt text]]`
> - Link to other documents: `[[{uuid}|display text]]` or `[[slug|display text]]`
> - Use tags for topical classification (in frontmatter and optionally inline).
>
> #### Referencing Artifacts from Documents
>
> Documents reference artifacts in two ways:
>
> - **Wikilinks** (`[[{blake3-hash}|text]]`) — citation-style references. "See the original forum post for details." The reader can click through to the full artifact.
>
> - **Embeds** (`![[{blake3-hash}]]`) — inline content inclusion. The artifact's normalized body renders at that position. For images, this surfaces the text description; in compiled outputs, the actual image can be substituted.
>
> Both create backlinks visible in Obsidian's graph view, making it discoverable which documents draw on which artifacts.
>
> #### Connecting Documents to Documents
>
> Documents connect to each other through standard Obsidian primitives:
>
> - **Wikilinks** — cross-references between documents. "See also the [[brake-system-overview|Brake System Overview]]."
> - **Tags** — shared classification. Documents tagged `#brake-caliper` are discoverable together.
> - **Embeds** — inline inclusion of one document's body in another.
>
> There are no stored structural relations (`is_a`, `part_of`). Compositional structure is expressed through the document graph itself: a "Brake System Overview" document that wikilinks to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" documents *is* the compositional structure. The links in the body are the hierarchy.

**Document frontmatter example:**

```yaml
---
uuid: "a1b2c3d4-e5f6-7a8b-9c0d-e1f2a3b4c5d6"
title: "Brake Caliper Rebuild — Pontiac G8 GT"
record_type: document
tags: [brake-caliper, caliper-rebuild, g8-gt, zeta-platform]
status: draft
---
```

**Document body example:**

```markdown
## Overview

The front brake calipers on the Zeta platform are a single-piston
sliding design. Rebuild is straightforward but the piston bore must
be inspected carefully.

![[blake3://a7f3b2c1?page=4&crop=50,100,550,400|Caliper exploded diagram from service manual]]

## Inspection

Remove the caliper mounting bolts using a 14mm socket. See
[[b8c9d0e1...|AllData procedure]] for torque specs.

Inspect the piston bore for scoring:

![[blake3://c9d0e1f2?framegrab=1:23|Bore scoring example from video walkthrough]]

If scoring is visible as in the image above, the caliper must be
replaced. The bore cannot be honed to spec on these units — see
[[d0e1f2a3...|GTO_Dave's rebuild thread]] for discussion.

## Related

- [[brake-bleeding|Brake Bleeding Procedure]] — must bench-bleed before reassembly
- [[rotor-replacement|Rotor Replacement]] — often done at the same time
- [[brake-system-overview|Brake System Overview]] — parent document
```

Note: the document uses both plain blake3 wikilinks (for direct artifact references) and functional URIs (for computed transformations like page extraction and framegrabs). Links to other documents use slugs for readability.

---

## Change 5: Define the functional URI scheme

### Rationale

Documents need to reference specific derived views of artifacts — a single page from a PDF, a frame from a video, a cropped region of an image. These derived views should not be stored as separate artifacts because they are deterministic transformations of immutable inputs. They are computed at "compile" time (when rendering the document for a specific output format) and cached for performance.

### Affected sections

- New §3.7 — Functional URI Scheme
- §6 Compendiums — update compilation model

### Specification

**New §3.7 — Functional URI Scheme:**

> ### 3.7 Functional URI Scheme
>
> Documents may reference computed transformations of artifacts using functional URIs. These are only valid in document bodies — artifact bodies use plain blake3 wikilinks and embeds only.
>
> **Base syntax:** `blake3://{hash}` — resolves to the artifact's binary content.
>
> **Fragment navigation:** `blake3://{hash}#anchor` — navigates to a named section of the artifact's normalized body.
>
> **Transformation parameters:** appended as query parameters, composed left-to-right (each function operates on the output of the previous):
>
> | Parameter | Applies to | Meaning |
> |-----------|-----------|---------|
> | `page={n}` | PDF | Extract page n (1-indexed). |
> | `page={n}-{m}` | PDF | Extract page range. |
> | `crop={x},{y},{w},{h}` | Image, PDF page | Crop to region (origin top-left, pixels or percentage). |
> | `resize={w}x{h}` | Image | Resize to dimensions. |
> | `framegrab={t}` | Video | Extract frame at timestamp (seconds or `m:ss`). |
> | `range={t1}-{t2}` | Audio, Video | Extract time range. |
> | `grayscale` | Image | Convert to grayscale. |
>
> **Composition example:** `blake3://{hash}?page=4&crop=50,100,550,400` — extract page 4 from a PDF, then crop to the caliper diagram region. The result is an image.
>
> **Semantics:**
>
> - Functional URIs are **deterministic** — same inputs always produce the same output (the underlying artifact is immutable by content addressing).
> - Results are **cacheable** — the cache key is the full URI string. Cache can be blown away and regenerated at any time.
> - Results are **ephemeral** — they are not stored as records. They exist at compile/render time.
> - Functional URIs are **document-layer only** — artifact bodies never contain them.
>
> **In Obsidian (raw browsing):** Functional URIs that can't be resolved at browse time fall back to displaying the alt text. Tooling or plugins can resolve them.
>
> **In compiled outputs (mdbook, static site):** The build process resolves all functional URIs, computes transformations, and substitutes results (rendered images, extracted audio clips, etc.).

---

## Change 6: Restructure tags as the universal classification mechanism

### Rationale

With `is_a` and `part_of` eliminated, tags are the only classification mechanism. They need to be well-specified but remain simple and portable. Tags are corpus-local — they don't reference external concept documents. A corpus can define a tag vocabulary in a conventions file, but tags work even without one.

### Affected sections

- §3.1.1 Core Fields — update `tags` description
- §3.5 Classification — major rewrite
- §3.5.1 Entity vs set — **delete**

### Specification

**§3.1.1 Core Fields — update `tags`:**

> | `tags` | string[] | no | both | Classification tags. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Declare what this record is about or what category it belongs to. Tags are corpus-local — they require no external concept document to function. A corpus MAY define a tag vocabulary in its conventions file for consistency. |
>
> On artifact records, `tags` classify what the captured content is about. They are populated by the normalizer during contextualization and may be refined by curation passes. Frontmatter tags declare whole-record topical coverage; inline comment tags (`%% #tag %%`) provide positional precision.
>
> On document records, `tags` classify what the authored knowledge covers. They are set by the document's author (human or agent).

**§3.5 Classification — rewrite:**

> ### 3.5 Classification
>
> Classification in v10 uses tags and the document graph — no stored structural relations.
>
> **Tags** handle categorical classification. An artifact tagged `brake-caliper` is findable by topic. A document tagged `brake-caliper` and `g8-gt` is discoverable at the intersection. Tags are flat (no hierarchy), portable (no external dependencies), and corpus-local (a tag means whatever the corpus's conventions say it means).
>
> **The document graph** handles structural organization. A "Brake System Overview" document that links to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" documents expresses compositional structure through its body, not through frontmatter relations. The link graph is the hierarchy.
>
> **Computed similarity** handles deduplication and discovery. Perceptual hashes and body embeddings surface related content without stored edges.
>
> **Tag vocabulary conventions.** A corpus MAY maintain a conventions file listing its tag vocabulary with descriptions. This is guidance for normalizers and curators, not a schema constraint. Unknown tags are valid — they signal vocabulary growth. High-frequency unknown tags are candidates for vocabulary formalization.

**§3.5.1 — Delete.** Entity/set distinction is eliminated entirely.

---

## Change 7: Define the slug mechanism

### Rationale

Slugs provide human-readable addressability for records. Documents need slugs so other documents can wikilink to them by readable name rather than UUID. Artifact records rarely need slugs but can have them for significant, frequently-referenced captures.

### Affected sections

- §3.1.1 Core Fields — add `slug`
- §1.3 Terminology — add Slug

### Specification

**§1.3 Terminology:**

> **Slug** — An optional, corpus-unique, human-readable identifier for a record (`[a-z0-9]+(-[a-z0-9]+)*`). Enables readable wikilinks: `[[brake-bleeding|Brake Bleeding Procedure]]` instead of `[[a1b2c3d4-...|Brake Bleeding Procedure]]`.

**§3.1.1 Core Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | string | no | Corpus-unique human-readable identifier. Kebab-case, lowercase. Used for readable wikilinks. Primarily on document records. Uniqueness enforced corpus-wide; slug changes require updating all references. |

---

## Change 8: Define the two-layer schema system

### Rationale

With one artifact per record, each record has exactly one `content_type`, enabling schemas to define precisely what metadata the normalizer extracts. The schema system has two layers:

- **Base schemas** by MIME type: format-intrinsic extended fields and normalization guidance.
- **Corpus-local classification schemas**: domain-specific metadata extraction rules and additional tags, defined by the corpus rather than globally.

This keeps artifacts portable (base schemas are universal) while enabling domain specialization (classification schemas are corpus-local).

### Affected sections

- §3.3 Schema Library — major restructuring
- §3.1.4 Extended Fields — update
- §4.2 Normalize — update
- §5.3 Normalizer — update

### Specification

**§3.3 Schema Library — restructure:**

> ### 3.3 Schema Library
>
> #### 3.3.1 Base Schemas (MIME type)
>
> Base schemas are keyed by `content_type`. They define:
>
> - **Normalization method:** `extraction`, `transcription`, `description`, or `metadata`.
> - **Normalization guidance:** prose instructions for the normalizer.
> - **Extended fields:** structured metadata mechanically extractable from any file of this type. These are format-intrinsic — they come from file headers and embedded metadata.
>
> Base schemas are universal. They apply to any corpus using this MIME type. They travel with the Athenaeum toolkit, not with individual corpora.
>
> **Schema document format:**
>
> ```yaml
> schema_type: base
> content_type: "audio/mpeg"
>
> normalization:
>   method: "transcription"
>   guidance: |
>     Extract audio metadata from file headers. Read ID3v2 tags
>     when present, falling back to ID3v1.
>
> extended_fields:
>   duration_seconds:
>     type: number
>     required: true
>     source: file_metadata
>     description: "Total duration in seconds."
>   bitrate_kbps:
>     type: number
>     required: false
>     source: file_metadata
>     description: "Encoding bitrate in kbps."
>   sample_rate_hz:
>     type: number
>     required: false
>     source: file_metadata
>     description: "Sample rate in Hz."
>   channels:
>     type: number
>     required: false
>     source: file_metadata
>     description: "Audio channels (1=mono, 2=stereo)."
> ```
>
> #### 3.3.2 Corpus-Local Classification Schemas
>
> A corpus MAY define classification schemas that add domain-specific metadata extraction. These are keyed by a match condition (typically tag-based or content_type + heuristic) and define additional extended fields and tags.
>
> Classification schemas live in the corpus's schema directory, not in the global toolkit. They are portable with the corpus but not universal.
>
> ```yaml
> schema_type: classification
> match:
>   content_type: "audio/mpeg"
>   condition: "ID3 artist and album tags are populated"
>
> classification:
>   add_tags: [musical-recording]
>
> extended_fields:
>   artist:
>     type: string
>     source: id3_tag
>     description: "Performing artist from ID3 metadata."
>   track_title:
>     type: string
>     source: id3_tag
>     description: "Track title from ID3 metadata."
>   album:
>     type: string
>     source: id3_tag
>     description: "Album name from ID3 metadata."
>   track_number:
>     type: number
>     source: id3_tag
>     description: "Track position on album."
> ```
>
> **Composition.** The normalizer applies the base schema first (format extraction), then checks classification schemas for matching conditions. Matching classification schemas add their tags and extended fields to the record. Multiple classification schemas may match — their fields merge (last-write-wins on collision).
>
> **Unclassified artifacts.** An artifact that matches no classification schema is fully valid — it has its base schema fields and whatever tags the normalizer assigned. Classification can be deferred to a later pass when more context is available (e.g., after related artifacts are captured or documents are written that provide context).

**§3.3.3 MIME Type Reference — per-type sections:**

Include base field tables for at minimum:

- `text/html` — page_title, meta_description, canonical_url, og_title, og_description, og_image, og_type, language
- `text/markdown` — word_count
- `audio/mpeg`, `audio/flac`, `audio/wav`, `audio/ogg` — duration_seconds, bitrate_kbps, sample_rate_hz, channels
- `image/jpeg`, `image/png`, `image/webp`, `image/gif` — width_px, height_px, color_space, exif_date, exif_gps_lat, exif_gps_lon, exif_camera
- `video/mp4`, `video/webm`, `video/mkv` — duration_seconds, width_px, height_px, frame_rate, video_codec, audio_codec
- `application/pdf` — page_count, pdf_author, pdf_title, pdf_creation_date, pdf_producer, is_scanned

---

## Change 9: Update the changelog and version

### Specification

Increment to v10.0:

```yaml
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
```

---

## Summary of section-level changes

| Section | Action |
|---------|--------|
| Frontmatter: version, changelog | Update (Change 9) |
| §1.2 Core Principles | Add normalized body principle (Change 2) |
| §1.3 Terminology | Replace Source Record → Artifact Record, add Content-Addressed Naming, replace Relation → Reference, add Slug (Changes 0, 1, 7) |
| §2.2 Sources → Artifacts | **Rewrite entirely** (Change 0) |
| §2.3 Documents | **Major rewrite** for new document model (Change 4) |
| §2.4 The Merge DAG | **Rewrite** — constituents removed; document composition is expressed through body references (Change 1) |
| §2.6 Self-Sufficiency | Update for artifact terminology (Change 0) |
| §3.1 Record Format | Rewrite: blake3 naming for artifacts, UUID for documents (Change 0) |
| §3.1.1 Core Fields | Add `blake3`, `origin_uri`, `captures`, `hashes`, `normalization_type`, `slug`; remove `artifacts[]`; update `uuid` (documents only); update `record_type` enum; update `tags` (Changes 0, 6, 7) |
| §3.1.2 Source-Specific → Artifact-Specific Fields | Rewrite (Change 0) |
| §3.1.3 Document-Specific Fields | Remove `constituents` (Change 1) |
| §3.1.4 Extended Fields | Update to reference schema-defined fields (Change 8) |
| §3.1.7 Relations | **Delete entirely** (Change 1) |
| §3.2 Body Format | **Major expansion**: artifact body integrity, cross-reference resolution, inline topic annotations, document body rules, embed semantics (Changes 3, 4) |
| §3.3 Schema Library | **Major restructure**: base schemas + corpus-local classification schemas, per-MIME-type reference (Change 8) |
| §3.4 Examples | Rewrite all examples (Changes 0, 1, 4) |
| §3.5 Classification | **Major rewrite**: tags + document graph + computed similarity (Change 6) |
| §3.5.1 Entity vs set | **Delete entirely** (Change 6) |
| §3.5.3 Deduplication | Rewrite as "Deduplication and Similarity" (Change 2) |
| New §3.7 | Functional URI Scheme (Change 5) |
| §4.1 Capture | Rewrite for content-addressed pipeline (Change 0) |
| §4.2 Normalize | Update: single-artifact normalization, cross-reference resolution, schema composition (Changes 0, 3, 8) |
| §5.1 Capturer | Update for content-addressed pipeline (Change 0) |
| §5.3 Normalizer | Update: reference resolution, schema application (Changes 3, 8) |
| §6 Compendiums | Update for document model, functional URIs, compilation (Changes 4, 5) |
| Global | Replace `source` → `artifact` throughout (Change 0) |

---

## Design decisions — quick reference

| Question | Decision | Rationale |
|----------|----------|-----------|
| Why blake3? | Fast (designed for large files), 256-bit (collision-proof at any practical corpus size), wide tooling support. | Performance matters for hashing video files and large PDFs. |
| Do artifact records have UUIDs? | No. Blake3 hash is the identity. Documents keep UUID. | One identity system per record type. The hash *is* the identity. |
| Do artifacts link to each other? | Yes — through wikilinks and embeds that mirror the original content's cross-references. | A forum post with an inline image and a link to another thread should preserve that structure. |
| Can artifacts link to documents? | No. Artifact bodies faithfully represent original content. The original content didn't reference corpus documents. | Artifacts have no knowledge of documents. Reference direction is document → artifact only. |
| Is editorialization allowed in artifact bodies? | Only inline topic annotations (`%% #tag %%`). All other content faithfully mirrors the original. | Annotations are metadata, not content. They classify without altering the representation. |
| Why no `is_a`? | Either redundant with `content_type`/schema classification, or coupling the artifact to a specific concept hierarchy that hurts portability. | Classification is the corpus's job, not the artifact's. |
| Why no `part_of`? | Compositional structure is expressed in document bodies through wikilinks. The body *is* the composition. | A frontmatter pointer adds nothing that the body doesn't already express. |
| Why no `same_as`? | A manually maintained assertion that can go stale. Replaced by computed similarity: blake3 (exact), perceptual hashes (format-specific), body embeddings (cross-modal). | Nothing should be a stored assertion about a relationship that's computable from intrinsic properties. |
| Why no `constituents`? | A document's references to artifacts are visible in its wikilinks and embeds. The body is the authoritative record. | Duplicating the reference list in frontmatter creates a maintenance burden with no benefit. |
| Where do embeddings live? | They don't — they're cached. The normalized body is the durable input. | The spec defines the representation; tooling builds the indices. |
| Are functional URIs valid in artifact bodies? | No. Artifact bodies use plain blake3 wikilinks and embeds only. Functional URIs are document-layer only. | Artifact bodies are faithful representations, not editorial compositions. |
| How does a document express "this track belongs to this album"? | The album document wikilinks to the track document. The link in the body *is* the structural relationship. | No stored `part_of` needed — the document graph is the hierarchy. |
| Can an artifact be unclassified? | Yes. An artifact with base schema fields and no classification tags is fully valid. Classification can happen later. | Capture shouldn't block on classification. Defer complexity. |
| Are tags hierarchical? | No. Tags are flat. Hierarchy is expressed through the document graph. | Flat tags are portable. Hierarchical tags couple the corpus to a taxonomy. |
| What happens to the concept documents from v9? | They become regular documents. Documents that describe a concept (e.g., "Song", "Brake Caliper") are just documents with descriptive prose. Other documents link to them. No special status. | Concept documents were never structurally special — their role was emergent. Now it's just part of the document graph. |
| Are schemas portable? | Base schemas (MIME type) are universal. Classification schemas are corpus-local. | Artifacts are portable; domain knowledge is corpus-specific. |

---

## Deferred Considerations

### Temporal succession

Multiple captures of the same `origin_uri` with different content provide temporal ordering by capture date. Cross-URI succession (new URL for an updated version) has no automatic mechanism. A convention could emerge (tags like `supersedes:{blake3-hash}` or a document that lists versions), but is not specified in v10.

### Concept document retirement / redirection

Concept documents in v10 are just documents. If one is deprecated, the author updates it with a note and a wikilink to the replacement. No redirect mechanism is needed because there are no stored frontmatter references to redirect — only body wikilinks in other documents, which can be updated via find-and-replace.

### Schema library ↔ origin-nature overlap

In v9, origin-nature concept documents carried normalization guidance. In v10, this guidance lives in corpus-local classification schemas. The two mechanisms are now cleanly separated: base schemas say "how to process this format," classification schemas say "what domain-specific metadata to extract when we recognize this kind of content."

### Similarity infrastructure

Perceptual hash caching, embedding indices, similarity thresholds, and discovery workflows are tooling concerns. The spec provides the inputs (binary artifacts + normalized bodies); tooling builds the indices. Threshold guidance could live in corpus conventions files.

### Functional URI extension

The v10 URI parameter set is deliberately minimal. Future extensions could add: text extraction (`?extract=section-3`), format conversion (`?format=png`), annotation overlay (`?annotate=circle,50,50,20`), or composition (`?composite={other-hash}`). These should be added conservatively — each parameter must be deterministic over immutable inputs.