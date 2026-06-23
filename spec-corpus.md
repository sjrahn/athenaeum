---
spec_id: ATH-CORPUS
title: "Corpus Specification"
version: 1.0
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-05-24
date_modified: 2026-06-05
---

# Corpus Specification

## 1. Overview

### 1.1 What this is

A **corpus** is a content-addressed archive of captured artifacts, accessed through faithfully represented markdown proxies called **records**. Artifacts are deconstructed into addressable segments and normalized to text, either losslessly or by description. Artifacts can stack classifications for the purposes of discoverability and improved normalization.

A record is a single markdown file. The YAML frontmatter at its head carries a small bytes-identity header — what these bytes ARE (their hashes), the editorial summary, the provenance chain of processing passes. The **record body** below the frontmatter is organized into three **zones**: a **metadata zone** declaring what the artifact is, where it came from, what classifications apply to it, and what assets it embeds; a **content zone** carrying the rendered content as sections and segments; and an **annotations zone** carrying observations about the record. Each zone holds a small set of HTML-comment block families; §4.3 specifies the grammar.

### 1.2 The transport model

Every captured file is a **transport** — a media-type-shaped container — that carries **content**.

- A transport's **intrinsic information** surfaces in the record's metadata zone — primarily in the artifact block for transport-intrinsic fields.
- A transport's **content** decomposes into a flat sequence of addressable segments in the record's content zone. Each segment carries one of four **content atoms** (text, image, audio, video) and an **address** indicating its location inside the transport.
- A transport's **container disposition** is declared by its media-type schema (`artifact_kind`, §7.1) and is **required** — there is no default. A **self-contained** transport produces a single record; when it contains a **nested transport**, it lifts that nested transport's intrinsic metadata into the outer record's artifact block (e.g. per-stream fields for a multi-stream media file) and addresses its content per stream / per member, while an asset it merely references is described as an embed in the metadata zone. An ordinary single-content file (a plain HTML page, a PDF) is `self_contained` — it simply has no nested transport to lift.
- A transport MAY instead be declared **decomposable** by its media-type schema (a raw archive), in which case the ingestor treats it as a folder of files: each member becomes its own captured artifact, and the container itself produces no record.

### 1.3 The atom / segment model

A record body's content zone is a sequence of **sections** and **segments** (the read-order rendering). Each segment carries:

- One **content atom**: `text`, `image`, `audio`, or `video`. Only `text` segments carry a segment body. Segments of the other three atoms are positioning markers — they declare where in the reading order an asset appears, and link to a matching embed (by address membership) for the asset's metadata and description. Their segment body is empty.
- An **address** specifying the segment's location inside the transport, in a scheme determined by the media-type schema. Addresses compose, so that chains can form from transport to atom to region (a region within a frame within a video).
- Exactly one **atomic classification**, declared on the opener line in the form `<!--segment <atom>/<id>-->` (or bare `<!--segment <atom>-->` for unclassified-but-typed segments). Text-atom overlays may declare lossless-shaping behavior — those overlays shape the segment body into a specific lossless form (a markdown table, a transcript, OCR text). When multiple representations apply to the same source region, each becomes its own segment.

Two segments may share an address as long as their opener-id differs — same-region stacking is how a record represents multiple valid lossless representations of one source region. Segments are addressable from outside the record via functional URIs that carry the segment's address in their query string (§5).

### 1.4 Lifecycle

```
captured bytes              (no identity yet — staging only)
       │
       │ ingest             deterministic: hashes, MIME detection, container disposition; stub record written
       ▼
   stub record              identity established; bytes persisted in the corpus's binary store
       │
       │ draft              deterministic: media-type schema runs, then mechanical classifications in declared order
       ▼
   draft record             faithful first-pass body, segment layout established, mechanical metadata-zone blocks emitted
       │
       │ normalize          LLM-guided: interpretive classifications run, description authored, body may be re-segmented
       ▼
 normalized record          ready for use
```

Once ingested, the artifact's bytes must remain retrievable by id. Where and how the implementation stores them is its concern; the contract is that a lookup by id produces the bytes. Re-running any stage is an expected refinement pattern, not a fallback; every stage from ingest onward appends a `touch[]` entry to the record's provenance chain (which `re-stub` may reset, §8.4).

### 1.5 Design principles

1. **Layered foundation.** The corpus is a foundation layer — the truth, the baseline. It depends on nothing; any system that builds atop it depends on the records it produces.

2. **Content addressing.** Every artifact's identity is the blake3 hash of its bytes. Bytes don't change; if they did, the hash would change and the record would be a different record.

3. **Faithfulness.** A record body is a faithful, lossless rendering of the transport's content. Normalization may resolve ambiguity (encoding, broken layout, OCR for scans) but never adds information not present in the source. Descriptive content (a summary of what an image shows, a paraphrase of what was said) is lossy by definition and lives on the matching embed's description field — or, when no embed exists, on the addressing segment's or section's `description:` — **not** in a segment body. Re-segmentation is structural, never editorial.

4. **The record body as universal representation.** Every artifact carries a markdown body composed of segments. This projects every modality — text, image, audio, video — into a common representational space. Search, similarity, and embeddings all operate on the body.

5. **Transports declare, content fills.** Format-specific machinery (address scheme, extraction strategy, body shape) lives on the media-type schema. Content-specific tactics live on classifications. The two layers don't bleed.

6. **Deterministic before LLM.** Media-type schemas and mechanical classifications are scripts; interpretive classifications are LLM-guidance. The boundary is sharp so each stage's outputs are auditable.

7. **On-demand derived views.** Cross-cutting aggregates and richer modal projections are computed by walking body blocks and semantic-tagged fields, or by resolving functional URIs — never persisted alongside the record.

8. **Stable identity, mutable metadata, faithful body.** A record's `id` is fixed at capture. Body blocks evolve as drafting and normalization improve; the body content remains faithful.

9. **Offline-first.** Only `capture` requires network access. Ingest, draft, normalize, and URI resolution all operate on local data.

10. **Frontmatter is bytes-identity only.** What the bytes ARE (their hashes), how visible they are to authoring tools, how to navigate the provenance chain, the editorial display title + summary the normalizer authors. Everything else — the title *candidates*, media-type, origins, classifications, issues, extended fields — lives in body blocks because everything else came from a schema decision, and schema decisions are auditable per-block. A field is named **bare** when its block opener already identifies its provenance: an artifact block names the format (its MIME), a classify block names the composite (`<namespace>/<id>`), so their fields are `title`/`author`/`isbn`, never `pdf_title`/`book_isbn`. A provenance prefix survives only where the opener does *not* carry it — an origin block's `ytdlp_title` (the opener names the source record, not the extraction tool), or a metadata sub-standard the format embeds (`exif_*`, `og_*`). (Prefixing every field was a holdover from when these all shared the frontmatter's flat namespace; once each rides its own self-identifying block, the prefix only echoes the block.)

11. **Classifications are derived, not declared.** A record's classifications list is computed by walking its metadata-zone blocks. The body IS the classification declaration. The same principle applies to issues (walks annotations-zone blocks) and to the aggregated URI, timeline, and identifier views (which walk semantic-tagged schema fields together with the universal origin `uri:`/`snapshot:` fields and, for identifiers, the record's own `id` — §9).

---

## 2. Identity

Every artifact is identified by the blake3 hash of its bytes — a 64-character lowercase hex string. This identifier is the record's `id` and the lookup key by which the corpus's binary store produces the bytes. The implementation owns where and how the bytes are stored; the contract is that an `id` resolves to its bytes.

The `id` field is bare hex with no algorithm prefix because the algorithm is invariant. All other hash fields in the spec use an `<algo>:<hex>` prefix encoding (§7.6) so that multiple hash families can coexist within one field.

---

## 3. Schema namespaces

A corpus's schemas are organized into five spec-reserved **namespaces**. Three are primitive **axes** — each bound to a single block-keyword role in the record body — and two are umbrellas: `composite` for classifications, `context` for annotations:

| Namespace | Role | What it declares |
|---|---|---|
| `mime` | Declares the **artifact block**. | Per-media-type fields, address scheme, body-draft behavior, container disposition. |
| `origin` | Declares the **origin block**. | Per-source-of-retrieval overlays: how to recognize an origin, what additional fields it contributes. |
| `atom` | Declares the **atomic classification** on a **segment block**. | Per-atom-and-subtype overlays: what kind of content a segment carries, and (for text-atom overlays) whether it licenses a shaped lossless body. |
| `composite` | The umbrella for every user-defined **classification** namespace. | Per-namespace classifications declared via the **classify block** (`composite/<namespace>/<id>`). |
| `context` | The umbrella for every **annotation** namespace — observations *about* a record. | Per-namespace overlays declared via the **context block** (`context/<namespace>/<id>`): `issue` (problems), `reference` (cited sources), … |

A record references a schema by the qualified id encoded on a block opener — for example, `<!--classify <namespace>/<id>-->`. The schema loader resolves the id by walking a chain of declarations from most-specific to least-specific:

1. The subtype-overlay declaration (`<namespace>/<id>/<subtype>`), if a subtype is present on the opener.
2. The id declaration (`<namespace>/<id>`).
3. The id's parent declaration, if the id is itself two-part within the namespace (applies in the `mime` and `atom` namespaces where ids decompose into axis + subtype, such as `mime/text/html` or `atom/text/data-table`).
4. The namespace's universal declaration.

Each layer's declared fields extend its parent's; conflicts resolve in favor of the most-specific declaration.

The on-disk organization of these schemas is implementation-discretionary; a reference layout appears in the implementation notes appendix.

---

## 4. Records

### 4.1 What a record is

A markdown file with YAML frontmatter. The frontmatter carries the bytes-identity header; the record body carries the schema-derived metadata blocks AND the segmented rendering of the transport's content AND any annotations.

A record is always at one of three statuses:

| Status | Meaning | Stage that produced it |
|---|---|---|
| `stub` | Identity established; bytes persisted in the corpus's binary store; artifact block emitted; first origin block populated from capture context; content zone empty. | ingest |
| `draft` | Media-type schema and any mechanical classifications applied; record body's content zone segmented per the media-type schema; mechanical classify and embed blocks emitted; drafter-detected issue context blocks emitted. | draft |
| `normalized` | Interpretive classifications applied; description authored; content zone re-segmented where the LLM judged appropriate; interpretive classify and issue context blocks surfaced. | normalize |

### 4.2 Frontmatter

The frontmatter (`---...---` at the top of the file) holds **only the bytes-identity header** plus the two editorial display fields — at most nine fields. Everything else lives in body blocks (§4.3) or surfaces as derived views (§9).

#### 4.2.1 Core fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Primary identity — blake3 hash of the artifact's bytes, 64-char lowercase hex. Filename stem. Bare hex (no `<algo>:` prefix; algorithm is invariant). |
| `title` | string | yes | Short display title. The key is always present; its value is empty (`''`) at stub/draft and authored at `normalized`. Like `description`, the deterministic pipeline never populates it — the normalizer chooses among the **block-level title candidates** (the artifact block's bare `title` field, or an origin block's `ytdlp_title`) or writes its own. |
| `description` | string | yes | 1–3 sentence summary. The key is always present; its value is empty (`''`) at stub/draft and authored at `normalized`. The primary mechanism for discovery. |
| `status` | enum | yes | `stub`, `draft`, or `normalized`. |
| `transport` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | Byte-level hash(es) of the file under additional algorithms beyond the primary blake3. The primary blake3 lives on `id` and is **not** duplicated here. Use `transport:` only for alternative algorithms. |
| `canonical` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | A canonicalized-content hash, set at draft time by the matching media-type schema's canonicalization strategy. Lets two records be compared for "same content?" even when ever-changing metadata (timestamps, producer strings) differs. Optional. |
| `perceptual` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | Record-scope perceptual fingerprint — present only for single-atom records (e.g. an image artifact carries a perceptual hash). Multi-atom records carry per-segment perceptual fingerprints in segment headers instead. |
| `touch` | string \| list[string] | yes (≥1) | Ordered list of touch identifiers, one per processing pass. Singular (bare string) when one entry; list when 2+. `touch[0]` is the original ingest. |
| `visibility` | enum | no | `visible` (default), `deranked`, `hidden`. Editorial curation, orthogonal to status. |

#### 4.2.2 Touch identifiers

A touch identifier is a short bare string distinguishing a processing pass. The sequence is `touch[]` — a bare string when the chain has one entry, a list otherwise; the chain records the record's **current-shape provenance** (which passes produced the shape it has now). It is not an immutable history: `re-stub` resets it (§8.4), so a re-stubbed record's chain reflects its post-reset lineage, not every pass it ever saw.

- **Pipeline tooling** uses a stable identifier of the form `<package>.<module>@<version>`, where `<module>` may be a dotted path (e.g. `draft.<mime-type-id>`, `classify.<namespace>-<id>`). The `<package>.<module>` identifies the code path; `<version>` is its installed version.
- **LLM models** use the canonical model identifier with any context modifier in brackets — e.g. `<model-id>[<modifier>]`.
- **Combined tooling + model** — a single pass that is both a deterministic re-assembly and the LLM pass it carries joins the two with `+`: `<package>.<module>@<version>+<model-id>`.

Consecutive identical passes coalesce rather than repeat: a second identical identifier becomes `<identifier>_2`, a third `<identifier>_3`, and so on; a different identifier resets the count. The counter reflects the current chain, so a `re-stub` (which collapses the chain, §8.4) resets it.

The latest touch's tooling version implicitly encodes the spec era under which the record's current shape was produced.

### 4.3 The record body — seven block families, three zones

The record body is the markdown content below the closing `---` of the frontmatter. It has three **zones** — metadata, content, annotations — each holding a fixed set of HTML-comment block families.

Every block has the same shape: an HTML comment whose opener line carries a keyword (and optional arg), the YAML payload on the lines that follow, and a closing `-->` alone on its line. HTML comments are syntactically distinct from markdown horizontal rules and from frontmatter delimiters, and every standards-compliant markdown renderer ignores them — so the record body renders cleanly.

```
─── metadata zone ────────────────────────
<!--artifact <mime-type>-->               # exactly 1
<!--origin [<id>[/<subtype>]]-->          # 1..N
<!--classify <namespace>/<id>-->          # 0..N
<!--embed <mime-type>-->                  # 0..N

─── content zone ─────────────────────────
<!--section [<namespace>/<id>]-->         # 0..N (each contains 0..N segments)
or
<!--segment <atom>-->                     # 0..N (sectionless top-level segments)

─── annotations zone ─────────────────────
<!--context <namespace>/<id>[/<subtype>]--># 0..N (record- or segment-scoped via address:)
```

Zone order is fixed. A block of a later zone appearing before a block of an earlier zone is a parse error. Within a zone, the relative order of different block *families* is not significant (only the order among classify blocks matters — §4.3.1.3); the diagram's family order is illustrative. **All metadata- and annotation-zone blocks are header-only**: their YAML payload is the entire block; there is no markdown content between blocks within those zones. **Only segment blocks carry inline content** — the segment body holds the actual text.

#### 4.3.1 The metadata zone

The metadata zone carries the artifact's identity, its origins, its applied classifications, and its embedded assets. Four block families.

##### 4.3.1.1 The artifact block

Exactly one per record. The opener-line argument is the canonical MIME type and is **authoritative** — there is no frontmatter `media_type` field. The block body holds the fields declared by the matching `mime` schema chain, named **bare** — the opener's MIME already identifies their provenance (§principle 10), so a PDF's title is `title`, not `pdf_title`. When the format exposes a title it rides as that bare `title` candidate; the normalizer picks among it and the origin block's `ytdlp_title` to author the frontmatter `title` (§4.2.1). (A field keeps a prefix only when it names a provenance the opener does *not* carry — a metadata sub-standard the format embeds, e.g. `exif_*` on an image, `og_*` on HTML.)

```
<!--artifact <mime-type>
<extended-field-1>: <value>
<extended-field-2>: <value>
-->
```

Contributes one entry — `mime/<mime-type>` — to the derived classifications view.

##### 4.3.1.2 The origin block

One or more per record. Each block describes one origin (one source of retrieval). The required body fields are `uri:` (string or list-of-strings — a canonical URL plus its shortlinks/redirects collapse to one block whose `uri:` is a list) and `snapshot:` (ISO-8601 timestamp of when this origin was observed). Multiple origin blocks describe genuinely separate sources. A capture with no retrieval URL (a local file) still records an origin, using a `file://` or filesystem-path `uri:`.

```
<!--origin <id>
uri: <https://example.com/...>
snapshot: <ISO-8601>
-->

<!--origin
uri:
- <https://example.com/...>
- <https://alias.example.org/...>
snapshot: <ISO-8601>
-->
```

The opener may be bare (`<!--origin-->`) or qualified (`<!--origin <id>-->` or `<!--origin <id>/<subtype>-->`):

- **Bare** — generic origin; no schema overlay. Contributes nothing to the classifications view.
- **Qualified** — matches an `origin/<id>` schema overlay. Contributes `origin/<id>[/<subtype>]` to the derived classifications.

The id is not necessarily a hostname; the host-pattern match (when one is declared on the schema overlay) is a **cue** the drafter uses to decide which origin schema applies. Origin overlays may also key on non-host cues — file-system paths, API endpoint fingerprints, manual hints — declared in the overlay's match predicate.

The origin block subsumes:

- The capture URI(s) — one block per origin, `uri:` as a list when the same origin is reached through redirects or shortlinks.
- The observation timestamp (`snapshot:`).
- The origin-identifying classification (qualified `<id>` opener).
- Any origin-specific extended fields the schema overlay declares.

##### 4.3.1.3 The classify block

Zero or more per record. Each block carries the fields a classification overlay declares.

```
<!--classify <namespace>/<id>
<extended-field-1>: <value>
<extended-field-2>: <value>
-->
```

The opener argument is the namespace-qualified classification id, optionally subclassed (`<namespace>/<id>/<subtype>`). Contributes one entry `<namespace>/<id>[/<subtype>]` to the derived classifications view.

One field name is **reserved**: `provenance`. `provenance: auto` marks a block stamped by the deterministic `classify_when` engine (§7.4) — the engine owns it, stripping and regenerating it on every re-draft / reclassify. Its absence (or `provenance: asserted`) marks a hand- or normalizer-asserted block, which the engine never touches (§4.4.6). No composite may declare `provenance` as an `extended_field`.

Block order within the metadata zone follows execution order: mechanical classify blocks first (in drafter-declared order, `provenance: auto` among them), then interpretive (in normalizer-discovered order). The parser preserves order; tools rely on it so that later passes can read earlier passes' fields.

##### 4.3.1.4 The embed block

Zero or more per record. Header-only blocks describing embedded assets (inline images, video streams, audio clips, nested transports). Carry the asset's identifying metadata; the record body refers to them by position (address-membership).

```
<!--embed <mime-type>
address: <address>                # scalar — single occurrence
transport: <algo>:<hex>
<width>: <px>
<height>: <px>
alt: <verbatim source alt text>
-->

<!--embed <mime-type>
address:                          # list — repeated bytes at multiple positions
- <address-1>
- <address-2>
transport: <algo>:<hex>
alt: <verbatim source alt text>
-->
```

The opener line carries the embed's full MIME type.

###### Required header fields

| Field | Description |
|---|---|
| `address` | Where the asset appears in the transport, in the scheme defined by the media-type schema. Polymorphic: a single string or a YAML list of strings. |
| `transport` | Content-identifying hash, `<algo>:<hex>`. The canonical id of the embed; the deduplication key. |

###### Optional header fields

Per the matching media-type schema. The asset's descriptors split into two distinct kinds:

- `alt` — verbatim source-side alternate text (the publisher's caption, the image's `alt` attribute, the audio track's title, etc.). Drafter-emitted at capture; **never replaced by the normalizer**. Omitted when the source has none. Provenance-bearing — may be missing, terse, or wrong, but reflects what the publisher wrote.
- `description` — normalizer-written description of the asset as a whole. Lossy by definition. Omitted when the asset is purely decorative.

Plus per-mime fields declared by the embed's media-type schema.

###### Embed description vs segment description

The embed's `description` covers the **whole asset**. A segment derived from that embed — addressing a sub-region, applying overlays — carries its own `description:` on the segment header describing the scope-specific interpretation. Same bytes, different scope, often a different narrative.

###### Deduplication

Embeds are deduplicated by `transport` — identical content collapses to one embed regardless of how many positions reference it. The drafter walks the transport's assets in order, hashes each, and merges duplicates by appending positions to the existing embed's `address` list.

###### Linking from segments

Segments link to embeds by **address membership**, not by an explicit reference field. A segment whose address appears (scalar or list-member) in an embed's `address` is described by that embed. Orphan embeds — embeds with no segment pointing at them — are tolerated as a record of available imagery; the normalizer may prune them.

Every image, audio, and video segment's address must appear in some embed's address — **except artifact-self-slices**. When a segment's address is a region of the record's *own* artifact that the resolver can materialize on demand (a `frame=`/`time=`/`time_range=` into a video, a `page=` render of a PDF, a `bbox=` into a single-image record), no embed is required: the bytes already live in the artifact and the functional URI (§6) produces the slice. An embed is needed only for assets the artifact does *not* itself contain — an inline image referenced by an HTML page, a nested transport, an externally-sourced clip. A self-slice carries any description on the addressing segment's (or section's) own `description:`, since there is no embed to host it.

#### 4.3.2 The content zone

The content zone carries the record body's rendered content — structural sections containing atomic segments. Two block families.

##### 4.3.2.1 The section block

A **section** is the universal grouping primitive — a chapter, a heading-delimited block, a sheet, a user turn, a speaker run. It is the table-of-contents unit. A section has its own opener that may carry a single composite classification — `<!--section <namespace>/<id>-->`, what kind of section this is (§4.4) — and a YAML header carrying an address and an optional `entry` (the TOC label). Sections contain segments; they have no body of their own.

```
<!--section [<namespace>/<id>]
address: <address>
entry: <TOC label>
-->

<!--segment <atom>
address: <address>
-->

<segment body>

<!--section
address: <next-address>
-->

...
```

A section's closer (`-->`) is followed **directly** by its first child segment opener — or, for an empty section (a TOC node with no content of its own), by the next section opener or the end of the body. Markdown prose between a section closer and the next opener is a parse error — sections have no body region.

A section's child segments arrange themselves along the media's natural axis:
- **Parallel** (temporal media) — segments within a section are simultaneous along time.
- **Sequential** (linear media) — segments within a section are stacked in reading order.

###### Section header fields

| Field | Required? | Description |
|---|---|---|
| `address` | Required | Address inside the transport in the scheme defined by the media-type schema. The section's identity. For a discrete-index scheme (`pages=`, `spines=`, `block=`, `sheet=`) it is the **envelope** — the min–max span of the section's child segment addresses — so the section never claims a range wider than the content it holds; a drafter derives it from the children rather than from a structural bound. Temporal sections (`time_range=`) are an exception: their bounds are structural intervals (chapters, speaker runs) that may legitimately differ from their checkpoints' content edges. |
| `entry` | Optional | The TOC label — written by the drafter when the source has a natural title; by the normalizer otherwise. |
| `description` | Optional | Scope-specific description of what this section IS — used when the section's address is a self-materializable asset (an artifact-self-slice with no embed, §4.3.1.4) and no child segment carries the description. Normalizer-written. |

The section's composite classification, if any, rides on the opener line as `<!--section <namespace>/<id>-->` — exactly as an atomic overlay rides a segment opener (§4.3.2.2) and a namespaced id rides a classify block (§4.3.1.3). A section carries at most one composite; the composite's extended fields sit flat in the section header. The overlay's declaring schema must permit section scope (its `applies_at` must include `section`, §7.4).

###### Section emission

A drafter emits sections when the source carries natural boundaries (outline entries, headings, sheets, user turns, speaker changes, etc.). When boundaries are absent, the drafter emits top-level segments instead — a **sectionless record**. The specific boundary policy and address shape per media type are declared on the media-type schema.

###### Nesting

Nesting depth is exactly one: sections contain segments; segments contain nothing; sections do not nest.

##### 4.3.2.2 The segment block

```
<!--segment <atom>[/<id>]
address: <address>                       # single string OR a YAML list of strings
<other-header-fields>: <values>
-->

<segment body>                            # text atom only
```

The atom (`text`, `image`, `audio`, or `video`) sits on the opener line itself, optionally qualified by an atomic-overlay id (e.g. `<!--segment text/data-table-->`). A segment is **logically contiguous content of one classification**. An interrupting element of a different classification forces a segment boundary.

A segment's identity is `(opener-id, address)` — the atomic class id on the opener plus the address. Two segments may share an address only when their opener-id differs. This permits **same-region stacking**: a single source region can carry multiple representations — a positioning marker for the asset, a structured transcription, a literal-text transcription — each as its own segment with the same address but a distinct opener-id. Multi-region segments use an ordered list of single-region addresses in reading order.

###### Body permission rule

A segment carries a segment body only when that body is a faithful, lossless rendering of the addressed content. This resolves to three cases:

- **Plain prose** — `<!--segment text-->` with the segment body as markdown text. Default for HTML prose, PDF page text, etc.
- **Shaped lossless transcription** — `<!--segment text/<id>-->` where the overlay's declaring schema licenses lossless shaping (`enables_lossless: true`, §4.4.1). The overlay shapes the segment body into the declared form (markdown table, transcript, OCR text, time-stamped captions, etc.). The address scheme may chain through transport→atom transforms to reach a region within a frame within a stream.
- **Body-empty marker** — every other segment, in two cases. (a) The three non-text atoms (`image`, `audio`, `video`) are positioning markers in document flow that link to a matching embed (by address membership) for the asset's metadata and description. (b) A `text/<id>` overlay whose declaring schema sets `enables_lossless: false` marks a *typed but non-lossless* text region — e.g. a live, formula-driven table whose displayed values are a single-execution snapshot rather than faithful content. In both cases the segment body is empty and what the region IS goes in the segment's `description:`.

###### Required header fields

| Field | Description |
|---|---|
| `address` | Address inside the transport, in the scheme defined by the media-type schema. The segment's identity. Composable: addresses chain transforms (e.g. transport → frame → region) as the schema permits. |

###### Optional header fields

| Field | Description |
|---|---|
| `description` | The segment's scope-specific description — what this segment IS at its address and under its overlay. Distinct from the matching embed's `description` (which describes the whole asset). Normalizer-written. |
| `perceptual` | An atom-canonical content fingerprint (§7.7) using the `<algo>:<hex>` prefix convention. |
| `entry` | A short identifying label — the TOC line. Sectionless records carry `entry:` on the top-level segment; in-section segments don't (the section is the TOC unit). |
| `speaker` | An integer diarization index identifying who is speaking in this `audio` segment. |

The atomic classification, if any, lives on the opener line as `<!--segment <atom>/<id>-->`. A segment carries exactly one atomic class id; when multiple representations apply to the same source region, each becomes its own segment with its own opener (and identity is the `(opener-id, address)` pair).

Segment-scope issues live as standalone issue context blocks in the annotations zone with an `address:` field pointing back to the segment — never inline on segment headers.

###### The four content atoms

- **`text`** — the atom whose segments carry segment bodies, with one exception. Plain prose by default; shaped by a `text/<overlay>` for structured lossless forms. A `text/<overlay>` declaring `enables_lossless: false` is a body-empty marker like the non-text atoms, with its meaning on the segment `description:` (see the body permission rule).
- **`image`** — a static image at the addressed region. Body-empty positioning marker; description on the matching embed at the same address — or, for an artifact-self-slice with no embed (§4.3.1.4), on this segment's own `description:`.
- **`audio`** — an audio range. Body-empty positioning marker; description on the matching embed (or, for a self-slice, on the segment's `description:`). Transcripts live as separate `text` segments at the same address.
- **`video`** — a video stream over the addressed time range. Body-empty positioning marker; description on the matching embed (or, for a self-slice, on the segment's `description:`). Captions and scene transcripts live as separate `text` segments at the same address.

###### Faithfulness

The segment body MUST be a faithful, lossless rendering of the addressed content. Descriptive content (a summary of what an image shows, a paraphrase of what was said, or what a live/computed region contains) is **lossy** by definition and belongs on the matching embed's `description` field — or, when no embed exists (an artifact-self-slice, §4.3.1.4, or a non-lossless `text/<id>` overlay), on the addressing segment's or section's own `description:` — NOT in a segment body. Re-segmentation is structural; content within remains faithful.

###### Cross-references in segment bodies

Functional URIs and wikilinks in segment bodies are for **cross-artifact references**. They are NOT used to embed inline images from within the same transport — inline images are their own `image` segments.

Segment bodies may carry:

- **Plain markdown URLs** — for external references whose targets aren't captured in the corpus.
- **Raw blake3 wikilinks/embeds** — `[[<blake3>|link text]]`, `![[<blake3>]]` — intra-corpus references whose targets are captured artifacts.
- **Functional URIs for cross-artifact derived views** — `[[corpus://<other-hash>?<params>|<caption>]]`, `![[corpus://<other-hash>?<params>|<alt-text>]]`.

###### Body-draft mode contract

The mime schema is the **only** body-drafter — it alone owns the content zone. A pass operating in body-draft mode **completely overwrites** any existing content zone in the record body. No dependency on prior content; no expectation that future content survives; same bytes always produce the same content zone (modulo extractor version). Body-drafting is total replacement. Mechanical classifications are metadata-only and never body-draft (§7.4).

#### 4.3.3 The annotations zone

The annotations zone carries observations *about* the record — problems with it, sources it cites, derived relations. One block family: the **context block**, drawing its overlays from the `context/` umbrella (§3), with one namespace per kind of observation (`issue`, `reference`, …). Context **never** contributes to the faithful content zone or the canonical content hash — it is a side-channel that accretes without disturbing the lossless body.

**Context is scarce by design.** A record carries a context block only when it records durable, high-value information the faithful body cannot — a detected problem (`issue`), a cited source resolved toward its record (`reference`), an overlay-declared chrome extraction (`aside`), a corpus-graph relation (`relation`). It is emphatically **not** a normalizer scratchpad: a normalizer MUST NOT emit commentary, summaries, running notes, or "what I did" prose as context. The **mechanical** namespaces (`issue`, `aside`, `relation`) auto-populate *only* on real signal and *only* where schema-gated — in particular an `aside` block exists **solely** where an origin or composite overlay declares the extraction, and there are none absent that declaration. **Interpretive** additions (`reference`) require a referent actually present in the content. Absent real signal the annotations zone is **empty** — the normal state for most records.

##### 4.3.3.1 The context block

Zero or more per record. Each is a typed observation, optionally pinned to a segment. The opener `<namespace>/<id>` matches the corresponding `context/<namespace>/<id>` overlay (mirroring how a classify block matches `composite/<namespace>/<id>`); an optional `<subtype>` extends it.

```
<!--context <namespace>/<id>
address: <segment-address>               # presence pins it to a segment; absence = record scope
quote: <verbatim span>                   # optional: the exact phrase within the segment
occurrence: <n>                          # optional: which match, when the quote repeats
provenance: auto                         # optional reserved field (see below)
<namespace-field>: <value>
-->
```

A context block with an `address:` field is **segment-scoped**; without it, **record-scoped**. The optional **`quote:`** (a verbatim span copied from the addressed segment's body) sharpens the anchor to the exact phrase; **`occurrence:`** disambiguates when that span repeats. Because the body is an immutable rendering of the immutable artifact, a verbatim `quote:` survives re-drafts where a character offset would not.

One field name is **reserved**: `provenance` (same semantics as on the classify block, §4.4.6). `provenance: auto` marks an engine-stamped block (a drafter detection, a derived-graph sweep) that is regenerated on re-run; its absence (or `provenance: asserted`) marks a human- or normalizer-asserted block that the engine never touches. No namespace may declare `provenance` as an overlay field.

Context blocks **do not** contribute to the derived classifications view (§9.1) — they surface in the derived `context` view, of which the `issues` view (§9.2) is the `issue`-namespace projection. Conceptually, a *classification* says what the content IS; a *context* records something observed about it.

##### 4.3.3.2 The `issue` namespace

An `issue` context block (`<!--context issue/<id>-->`) is a typed problem with the record or a segment. Its universal overlay (`context/issue/issue.yaml`) declares:

- `severity` — typically `blocking | warning | info` (the schema declares the closed set).
- `resolution` — typically `open | fixed | wontfix | superseded`.
- `detector` — touch identifier of the pass that emitted the issue.

Per-id overlays (`context/issue/<id>`) extend with id-specific fields. The `severity`/`resolution` value sets are corpus-local (schema-declared); cross-corpus tooling should treat unknown values gracefully rather than assuming a fixed vocabulary. Issues come from three sources — the **drafter** (deterministic detections: bot blocks, corrupt encoding, missing inputs), the **normalizer** (content-meaning problems), and **external** health-signal sweeps — each recorded in `detector` and, where engine-owned, `provenance: auto`.

##### 4.3.3.3 The `reference` namespace

A `reference` context block (`<!--context reference-->`) records a source the body cites — a book, an article, a bare external link — pinned to the mention via `address:` (+ `quote:`) and resolved up the **three-tier citation ladder** (§4.4.5): `attribution_text` (free text) → `source_url` (a resolvable URL) → `source_uri` (a functional `corpus://<id>` URI pointing at the separately-captured record). It is the addressable, segment-scoped realization of the citation model §4.4.3 deferred: a casual mention is captured first as free text and progressively researched toward a lossless intra-corpus link, without the host record ever changing shape.

##### 4.3.3.4 The `concept` namespace

A `concept` context block (`<!--context concept-->`) records a concept the body invokes — an entity, idea, work, or place — resolved against an **external local knowledge base** (Wikipedia/Wikidata), *not* a corpus record. This is the deliberate counterpart to `reference`'s tier-3 `source_uri`: a reference resolves toward a captured artifact (`corpus://<id>`), whereas a concept resolves toward an external authority the corpus does **not** capture (§11) — there is no value in re-capturing Wikipedia when it is run locally and read in place.

Like `reference`, it rides a lossy→lossless identity ladder: `label:` (free-text display name) → `url:` (the resolvable article URL) → `concept:` (the stable canonical id). The `concept:` id is the **join key** — `wikidata:Q<n>` (preferred, version-stable), `enwiki:<Article_Title>` (a local-dump article when no QID is resolved), or `local:<slug>` (a corpus-local custom concept) — by which records that invoke the same concept are related without either knowing about the other. As elsewhere, **scope** carries meaning: a block with `address:` (+ optional `quote:`) is a **mention** pinned to a span; an `address:`-less block records the record's **aboutness** as a whole. Concepts surface through the derived `concepts` view (§9.7).

### 4.4 Classifications: scope and fidelity

Classifications identify what a record (and its sections and segments) IS. The framework rests on two ideas: what *kind* of classification is being made (four axes) and what structural *scope* it applies at (three scopes — record, section, segment).

#### 4.4.1 The four classification axes

Every classification falls along one of four conceptual axes. Each axis has its own block, its own schema namespace, and its own scope rules.

| Axis | What it identifies | Block | Schema namespace |
|---|---|---|---|
| **media-type** | The format / container / transport of the bytes. | artifact block (exactly 1) | `mime` |
| **origin** | Where the bytes came from. | origin block (1..N) | `origin` |
| **atomic** | What kind of atomic content a segment carries. | segment-block opener | `atom` |
| **composite** | A named recurring pattern that combines axes. | classify block at record scope; section opener at section scope | `composite` |

**media-type** and **origin** are properties of the bytes — they live at record scope only. **atomic** and **composite** are interpretive judgments — they apply at the structural scope(s) where they're meaningful.

Atomic-axis schemas declare two extra keys beyond the universal classification fields:

- `applies_to.atom` — which atom this overlay attaches to (`text`, `image`, `audio`, or `video`). Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `enables_lossless` (boolean, default false) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's declaration describes what shape the body takes.

A segment carries **exactly one** atomic class id, on the opener line. When multiple representations apply to the same source region, each becomes its own segment.

#### 4.4.2 Three scopes

Classifications attach at three structural scopes — record, section, segment — plus the **embed**, where the media-type axis attaches via each embed's MIME:

| Axis | Record | Section | Segment | Embed |
|---|---|---|---|---|
| media-type | ✓ (artifact MIME, via artifact block) | — | — | ✓ (per-embed MIME on the opener line) |
| origin | ✓ (capture-time match, via origin block) | — | — | — |
| atomic | — | — | ✓ (on the segment opener) | — |
| composite | ✓ (via classify block) | ✓ (on the section opener) | — | — |

#### 4.4.3 Section scope: one composite (open item — citations)

A section carries **at most one** composite, on its opener — the section's identity (what this passage IS on its own terms).

A richer model has been considered for **citations**, where a borrowed section would carry both an *identity* composite (what the passage is) and a *role* composite (what it does in the host record), so a host can integrate quoted, embedded, or forwarded material without losing the material's own identity. That dual-composite form is **not yet reconciled** with the one-composite-on-the-opener grammar and is not specified here; treat section composites as single-identity for now. Citation lineage in the interim is carried by the citation field group (§4.4.4) and the three-tier ladder (§4.4.5) — whose segment-scoped realization now ships as the `reference` context block (§4.3.3.3). What remains deferred is only the section-scope identity+role dual composite.

#### 4.4.4 Scope-driven fidelity

A composite schema's extended fields decompose into three field groups by scope (§7.4):

- **Descriptive** — common across scopes the schema declares.
- **Structural** — record-scope only.
- **Citation** — section-scope only: the resolvable-source fields `attribution_text`, `source_url`, `source_uri` (the §4.4.5 ladder). The further fields `cited_by_reason`, `in_point`, `out_point` belong to the **deferred** dual-composite citation model (§4.4.3) and are not yet a usable contract.

#### 4.4.5 Three-tier lineage ladder

A cited source progresses from lossy toward lossless through the citation field group:

| Tier | Citation field | Meaning |
|---|---|---|
| **1** | `attribution_text` | Free-text. Ambiguous but captured. |
| **2** | `source_url` | Resolvable URL. |
| **3** | `source_uri` | Functional URI pointing to a separately-captured full record. |

Host records never change shape — enrichment happens at the linked target. This ladder is carried by the **`reference` context block** (§4.3.3.3), which pins the citation to the exact mention via `address:`/`quote:` and applies at any scope; the section-opener citation fields (below) are the section-scope special case.

#### 4.4.6 Mechanical vs interpretive kind

Each **composite** classification schema declares `kind: mechanical` or `kind: interpretive` (§7.4). (The other axes fix their kind: atom schemas declare `kind: atomic` (§7.3); origin overlays are always `kind: interpretive` (§7.2).)

| Kind | When it runs | What it does |
|---|---|---|
| **mechanical** | Draft time | Ships with an extraction script. |
| **interpretive** | Normalize time | LLM-guidance prose. |

Block ordering reflects execution order: mechanical first (drafter-declared order), then interpretive (normalizer-discovered order).

**Provenance ladder.** Orthogonal to `kind` (which says *where the payload runs*), a record-scope classification has one of three **provenances** (who put it there, and what re-running does to it):

| Provenance | How it appears | On re-draft / reclassify |
|---|---|---|
| **structural-derived** | `mime/*`, `origin/*` — walked from the artifact / origin blocks (§9.1), never a classify block | recomputed |
| **auto** | a classify block with `provenance: auto` — a `classify_when` match (§7.4) | stripped + regenerated from the current rules |
| **asserted** | a classify block with no `provenance` — human / normalizer | never touched |

`classify_when` thus **decouples where membership is decided from where the payload is consumed**: an `interpretive` composite can have its membership stamped `auto` at draft, while its `normalization.guidance` is still applied at normalize. A `provenance: auto` block whose overlay was deleted or no longer matches is *stale* — `corpus reclassify` re-converges it; lint warns (`classification-stale`).

#### 4.4.7 Re-run lifetime

Classify blocks persist across re-runs **unless their declaring schema is itself re-run**. A re-draft of the mime schema refreshes the artifact block and, for a body-draft mime schema, re-runs the body draft (re-segmenting the content zone and re-emitting embeds). A re-draft of a specific mechanical classification refreshes only that classify block. A re-normalize refreshes only the interpretive classify blocks (and may re-segment the content zone). To deliberately reset all accumulated metadata, use the `re-stub` operation (§8.4).

---

## 5. URIs and references

### 5.1 URI forms

Three URI forms appear within the corpus:

- **Plain URLs** — for unresolved external references in segment bodies whose targets aren't captured in the corpus.
- **Raw blake3 wikilinks/embeds** — `[[<blake3>|link text]]`, `![[<blake3>]]` — intra-corpus references whose targets are captured artifacts.
- **Functional URIs** — `corpus://<hash>[?<params>]` — composable references resolved to derived views (§6).

### 5.2 Re-capture

If the same bytes are encountered again, the record's identity is unchanged. The capture URL may differ across encounters, so origin blocks are append-only: each re-encounter checks the canonicalized capture URL against existing origin blocks' `uri:` entries and either appends to an existing origin's `uri:` list (when the new URL aliases an existing origin via known shortlink/redirect rules) or emits a new origin block (when it's genuinely a separate source).

If a URL re-fetched later yields different bytes, the new content produces a different hash and therefore a different record.

### 5.3 Referencing a region in another record

A functional URI addresses a **region** of a record — encode the address in its query string:

```
corpus://<hash>?<address-keys>
```

The same form serves both navigation (wikilink) and rendering (embed). It carries the **address only**, so it resolves to the region (and the asset or derived view at it), not to one specific representation: where same-region stacking places several segments at one address (a segment's in-record identity is `(opener-id, address)`, §4.3.2.2), those representations are distinguished only within the record, not by a cross-record reference.

---

## 6. Functional URIs

### 6.1 Grammar

```
corpus://<hash>[?<params>]
```

- `<hash>` — blake3 hash of the source artifact, 64-char lowercase hex.
- `<params>` — `&`-separated key/value pairs and flag-style keys. Order is significant — parameters compose left-to-right, each operating on the previous step's output.

Bare `corpus://<hash>` resolves to the source artifact's bytes. `corpus://<hash>?<params>` resolves to a derived view per §6.2.

### 6.2 Transformations

| Param | Input type | Output type | Description |
|---|---|---|---|
| `page=<N>` | PDF | image | Render page N (1-indexed) as an image. |
| `time_range=<s>-<e>` | video / audio | media slice | Extract a time range. |
| `stream_id=<id>` | multi-stream media | stream-isolated | Select a specific stream. |
| `bbox=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Crop a relative region (image: floats in `[0.0, 1.0]`, origin top-left) or narrow a worksheet (spreadsheet: an A1 range, e.g. `bbox=B2:G30`). Polymorphic — see below. |
| `crop=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Alias for `bbox` (inherits its polymorphism). |
| `resize=<W>x<H>` | image | image | Resize to absolute pixel dimensions. |
| `grayscale` | image | image | Convert to single-channel grayscale. |
| `dpi=<N>` | (render config) | (config) | Rasterization DPI for `page=<N>`. Position-independent. Default 200. |

A parameter applied to an incompatible working type is a hard error.

Parameter value grammar may be media-type-dependent; the resolver dispatches on the source artifact's type. In particular `bbox` is **polymorphic** — relative floats in `[0.0, 1.0]` when cropping a rendered image (an image artifact, or a `page=` render of a PDF), and a spreadsheet cell range (e.g. `bbox=B2:G30`) when narrowing a worksheet region — so the same token does not collide across media types. Pure **address selectors** that locate a region without transforming it — `sheet=<name>`, `el=<N>` (a 1-indexed index to *any* element in an HTML artifact; what it materializes is determined by the element, e.g. an `<img>`'s image bytes or a text element's region), and any others — are defined by each media-type schema (§4.3.2) and are not enumerated here; §6.2 lists only the parameters that produce a derived view.

### 6.3 The resolver

A corpus provides a **resolver** that materializes any functional URI to a deterministic, cacheable, ephemeral result. Given the same URI and the same source artifact, a resolver always returns the same result; the URI is the cache key.

The resolver's surface (CLI, library, HTTP service, etc.) is implementation-defined; the contract is that the URI scheme of §6.1 and the transformations of §6.2 are honored.

### 6.4 Caching

Resolver results may be cached. Cache lifetime, eviction policy, and storage location are all implementation-defined; the spec mandates only that the result is deterministic and reproducible from inputs.

---

## 7. Schema declarations

§3 introduced the five namespaces and the schema-loader resolution chain. This section specifies what the four schema-declaration namespaces (`mime`, `origin`, `atom`, `composite`) declare; the `context` umbrella's overlays are specified alongside the context block in §4.3.3.

### 7.1 The mime namespace

A `mime` schema declares everything the matching artifact block needs and everything the drafter needs to process the transport.

- `description` — prose definition.
- `applies_to.content_types` — list of canonical MIME types this schema covers.
- `applies_to.zip_members` / `applies_to.zip_member_patterns` (optional) — shape signature for a zip-shaped type whose telltale members sit under a *variable* wrapper directory (a diagnostics export, a backup bundle), so a fixed internal path can't recognize it. `zip_members` lists exact member paths (ANY present matches); `zip_member_patterns` lists member-path regexes (EACH must match some member). Evaluated by the shared MIME refiner against the corpus's schemas, so vendor/site-specific zip recognition lives in the overlay rather than the package. Universal zip formats (OOXML / EPUB / JAR) keep their fixed-path signatures in the tooling and need no declaration.
- `mode` — `extract-only` or `body-draft`.
- `working_kind` (optional) — the resolver's initial working-value kind for the functional-URI transform pipeline (`pdf`, `image`, `audio`, `video`, `html`, `epub`, `zip`, …); falls back to a built-in table for the bundled types when omitted.
- `draft` (optional) — drafting controls beyond `mode`. `draft.strategy` names a general, *type-agnostic* drafter registered by strategy name rather than schema id (e.g. `zip-manifest`), so one drafter serves many schemas whose representation differs only by config; the strategy's config rides alongside it (e.g. `draft.manifest`). Absent a strategy, the drafter is dispatched by schema id. This is the drafting analogue of the origin overlay's `capture` block — overlay-driven, but keyed by media type (the mime schema) rather than by host.
- `artifact_kind` (required) — `self_contained` (produces one record, lifting nested-stream metadata when present — the disposition for ordinary single-content files too) or `decomposable` (a raw archive that explodes into one record per member). No default.
- `address_scheme` — the parameters the schema expects in segment `address:` values.
- `extended_fields` — fields the matching artifact block carries, each with type and optional `semantic_type` tag. The artifact block holds only facts about the **primary-artifact bytes** (e.g. ffprobe codec / dimensions / streams); source metadata from a capturer's enrichment sidecar does NOT live here — see `sidecar`. Vendor/domain identity (what a bundle *is*, beyond its bytes) does NOT live here either — that is a classification overlay's concern, filled by the normalizer (e.g. an `unraid/diagnostic-package` composite over a kept-whole zip).
- `sidecar` (optional) — for an artifact type a capturer enriches with a companion metadata sidecar (e.g. a yt-dlp `.info.json`), declares what is lifted and where. `source` names the sidecar (e.g. `ytdlp-info-json`); `ytdlp_keys` lists the info.json keys copied — each into the **origin block** as a flat `ytdlp_<key>` field (§7.2), the mapping guidance the drafter applies. The sidecar is companion metadata staged in `capture/<hash>.<suffix>`, read at draft, then **deleted** — never persisted to `artifacts/` (only the artifact carries the `<hash>` name there). It is *non-primary-source* metadata, so nothing from it goes to the artifact block, the body, or the frontmatter `description`.
- `transport_algos` — additional byte-hash algorithms to compute beyond the primary blake3 `id`.
- `canonical_strategy` (optional) — procedure for computing the record's `canonical` hash. Names a canonicalization-algorithm id and the canonicalization steps the drafter performs before hashing. The canonicalization MAY be scoped to a **content region** — hashing only the article-content text and excluding per-page framing (title, breadcrumb, entry-specific headings) — so two records holding the same content reached by different URLs share a `canonical` and collapse to one record (the duplicate's URL folded into the original). The content-region selector is host-specific and supplied by the origin overlay (not this schema); when it matches nothing the canonicalization falls back to the whole document.
- `normalization.guidance` (optional) — prose guidance for the normalizer.

### 7.2 The origin namespace

An `origin` schema declares an overlay for one source of retrieval.

- `kind: interpretive` — origin overlays are always interpretive (the match cue may be mechanical, but body guidance is interpretive).
- `description` — prose framing of the publisher.
- `applies_to.host_pattern` (string, optional) or `applies_to.host_patterns` (list[string], optional) — host pattern(s) the drafter matches against origin URIs.
- `applies_to.include_subdomains` (bool, default false).
- `applies_to.cues` (optional) — non-host cues for the matcher.
- `normalization.guidance` (string) — markdown prose tactics.
- `extended_fields` (optional) — fields beyond the universal `uri:` / `snapshot:`. A capturer's enrichment sidecar populates these — e.g. a yt-dlp capture's `ytdlp_<key>` fields (title, description, uploader, engagement counts, `ytdlp_comments`), declared by the artifact's mime schema `sidecar` section (§7.1) and merged onto the origin block at draft.

The drafter iterates every origin block in the record. For each origin schema, if any origin block's `uri:` matches the schema's host pattern (or another declared cue), the drafter promotes that origin block's opener from bare `<!--origin-->` to `<!--origin <id>-->` and populates the schema's extended fields. The promoted opener contributes `origin/<id>[/<subtype>]` to the derived classifications view.

The universal `origin` overlay declares the two fields every origin block carries:

- `uri` — string or list-of-strings; the URI(s) by which the origin was reached (a `file://` or filesystem path for a local capture).
- `snapshot` — ISO-8601 timestamp of observation.

**Directory layout — namespaced by URI scheme family.** Origin overlays live under `schema/origin/<scheme-family>/<id>.yaml`, grouped by the URI scheme they are retrieved over so each family can carry its own match semantics. The `web` family (http/https) is keyed by host — `origin/web/<host>.yaml`, matched by `applies_to.host_pattern` — while `otherwise/` is the catch-all for un-namespaced schemes and other families (`urn/`, `file/`, `s3/`) get their own sub-namespace and match predicate as a corpus needs them. The universal `origin/origin.yaml` sits at the namespace root and layers into every overlay. The overlay **id is the bare `<id>`** (e.g. `youtube.com`) regardless of sub-namespace, so the `<!--origin youtube.com-->` opener and the `origin/youtube.com` classification are independent of where the file lives. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`; the flat `origin/<id>.yaml` layout is still read for back-compat.

**Operational overlay sections.** Capture and transcription are retrieval concerns of an origin, so their per-host configuration lives on the origin overlay — one host-keyed file describes both *what* a source is and *how* to capture and process it. These sections are corpus-local (the package ships none) and read mechanically by the tooling; declaring them is how the tooling stays generic with **no hardcoded host knowledge**:

- `capture:` — how to retrieve this origin (read at capture time).
  - `capturer` — the capturer name: `browser` (Playwright/HTML; the default), `video` (yt-dlp), or a corpus-local capturer. This is the **sole router** for video vs. browser — there is no built-in video-host list. (`corpus capture --video` / `--no-video` override it for a one-off URL.)
  - `transport` — `headless` | `headed` | `cdp` (browser capturer).
  - `fidelity` — `exact` | `balanced` | `lean` (browser capturer): the self-contained-snapshot completeness tier. `exact` is byte-faithful (presentation *is* content); `balanced` (the default) drops redundant font / image / media alternates inlined for self-containment; `lean` additionally prunes style rules with no matching element. The tiers affect only the snapshot **artifact** size — the drafted record is identical across tiers (the drafter reads DOM text/tables, not fonts/CSS) — so fidelity is purely a per-origin retention/faithfulness choice. The resolved tier is stamped into a `corpus-fidelity` snapshot meta tag for provenance. Precedence: `corpus capture --fidelity` › per-host `capture.fidelity` › `origin/origin.yaml` › tooling default (`balanced`).
  - `url_rewrite` — `[{pattern, replacement}]` regex rules applied to the navigation target before fetch; the original URL stays the recorded origin and the rewritten form becomes an alias.
  - `url_equivalent` — declares which URL spellings denote the **same resource**, so the corpus matches an inbound URL to a record (and keeps one origin URI per resource) even when the spelling differs — query noise (`?nested_view=1`, tracking params), a redundant `/page-1` ≡ the bare form, etc. **Identity-only**: it computes a URL's *identity key* and never changes which bytes are fetched (that is `url_rewrite` / `interactions`). Two URLs are equivalent iff their identity keys are equal. Declared as a list of `[{pattern, replacement}]` rules (same shape as `url_rewrite`), or a map `{query: keep|drop, rules: [...], on_rewritten: bool}`. The identity key = the conservative `normalize` (lowercase scheme+host, sort query, drop a plain anchor, …), then — for `query: drop` (default `keep`) — strip the whole query, then apply the regex `rules` in order, then a final delimiter tidy, then fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`); with `on_rewritten: true` the host's `url_rewrite` is applied first so identity is computed from the fetched form rather than the inbound one. The trailing-slash fold is part of the **identity** key only, never of `normalize` — `normalize`'s output is the URL a crawl re-fetches, where the slash can be significant, whereas a comparison key may fold it (so a naive first-page rule like `…/page-1 → \1` need not chase the recorded slashed origin). **Opt-in**: absent the section, identity is exactly `normalize` (string match), so the layer is inert for every host that does not declare it, and host-scoped so a blanket `query: drop` cannot wrongly fold a host where `?page=`/`?id=` matters. Applied at the **capture short-circuit** (re-capturing a known resource is skipped), **crawl frontier dedup** (an equivalent of a visited / captured URL is not re-enqueued), **pagination uri-recording** (an equivalent spelling of an already-recorded constituent page is not appended), and **resolve** of a raw URL to its record. Pairs with — and is independent of — `url_rewrite`.
  - `pagination` — reconcile a work a site splits across `?page=N` / `/page-N` URLs into **one** record (browser capturer only). `true` enables it with auto-detection; a map gives control: `content_selector` (the per-page content region — else a structural page-1-vs-page-2 diff finds it), `next` (`{rel: true}` follows `<link/a rel=next>`, the default; `selector` overrides with a CSS link), `max_pages` (safety cap, default 100), and `expect_count.selector` (an element whose text holds the site-advertised item count, for the completeness check). The capturer walks the pages, captures each via the staging-only path, merges their content regions into page 1's framework — **deduping by element id or a normalized-subtree hash** — and ingests the merged document. **INVARIANT: exactly one artifact and one record result; per-page captures are never content-addressed.** The clean seed is the recorded origin URI; every constituent page URL (bare site form *and* the pinned `url_rewrite` form) is folded in as an origin alias, and a `pagination: {pages, form, posts}` provenance field lands on the origin block (`posts` = the merged content-item count: id-bearing region children when present — forum/CMS posts carry stable ids — else all direct children, so framework nodes don't inflate it). When the merged item count falls short of the advertised count, or `max_pages` is hit, a `pagination-incomplete` `warning` issue is emitted (capture stage) rather than silently shipping a lossy record. Pairs naturally with `url_rewrite` to pin one render form across every page.
  - `ytdlp:` — a mapping merged straight into yt-dlp's options (full passthrough; e.g. `format`, `getcomments`, `impersonate`). Library-owned keys (output path, logger, the resolved cookie file) are forced after the merge and cannot be overridden.
  - `cookies_from_host` — `true` (default) pulls the capture URL's own-origin cookies from a running CDP browser session into yt-dlp; `false` disables; a list adds extra origin scopes. Lets a logged-in session unlock a host's full content.
  - `also_capture:` — `[{role, capturer, …}]` supporting captures run after the primary one; their bytes **enrich the primary record** (e.g. a comments page folded into the record's metadata) rather than forming separate records.
- `transcription:` — per-host audio transcription (read at draft time). `enabled: false` skips transcription (an `info` issue, not a `warning`); `adapter` / `base_url` override the global `[corpus.transcription]` backend. Absent the section, the global config applies.
- `canonical:` — `content_selector` scoping the `canonical` hash to the article-content region (§7.1).
- `metadata:` — reserved hook to remap/disable how a capturer's enrichment sidecar maps into the record (per host). The mapping itself is **host-agnostic and applied for every yt-dlp capture**, and is **schema-declared**, not hardcoded: the keys lifted from the `.info.json` come from the artifact mime schema's `sidecar.ytdlp_keys` (§7.1). Because the sidecar is *non-primary-source* metadata, every lifted key lands on the **origin block** as a flat `ytdlp_<key>` field (e.g. `ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts) — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when yt-dlp returns it) becomes a `ytdlp_comments` list field; `webpage_url` / `original_url` fold into the origin `uri:` aliases. The sidecar is **draft-time-only enrichment** — staged in `capture/`, consumed at draft, then deleted; it is one-shot (a re-draft after deletion does not re-apply it; the extracted fields already persist on the record). The only content the media drafters write to the body is the **transcript**, derived from the primary artifact's own audio.

### 7.3 The atom namespace

An `atom` schema declares an atomic-axis overlay that may attach to a segment.

- `kind: atomic`
- `description` — prose definition.
- `applies_to.atom` — `text`, `image`, `audio`, or `video`. Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `applies_to.cues` (optional) — heuristic patterns for the normalizer.
- `enables_lossless` (boolean, default `false`) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's other declarations describe what shape the body takes.
- `extended_fields` (optional) — id-specific fields. For lossless-enabling overlays these typically describe address-shape requirements.
- `normalization.guidance` (string) — markdown prose tactics.

A segment carries exactly one atomic class id, on the opener line.

### 7.4 The composite namespace

`composite` is the umbrella for **classification** namespaces — every user-defined namespace is a sub-namespace under `composite`, surfacing through the generic classify block at record scope, or a composite on the section opener at section scope. (Annotation overlays — `issue`, `reference`, … — live under the separate `context/` umbrella and surface through the context block, §3 / §4.3.3, not here.)

A classification schema (mechanical or interpretive) declares:

- `kind: mechanical` or `kind: interpretive`.
- `description` — prose definition.
- `applies_at` — list of scopes (subset of `[record, section]`). Default `[record]`.
- `applies_to.content_types` (mechanical only) — MIMEs the classification can apply to.
- `applies_to.cues` (optional) — heuristic patterns.
- `classify_when` (optional) — a **deterministic** membership predicate (below). When present, the drafter auto-assigns the class to every record it matches and stamps the classify block `provenance: auto` (§4.3.1.3). Orthogonal to `kind` — a `classify_when` may sit on an `interpretive` overlay (membership decided at draft; the `normalization.guidance` payload still consumed at normalize).
- `script` (mechanical only) — reference to the extraction script. A mechanical classification extracts metadata only — it emits/fills classify blocks and never drafts the record body (the mime schema is the sole body-drafter; §4.3.2.2).
- `normalization.guidance` (interpretive only) — class-specific tactics in prose.
- `extended_fields` — fields the matching classify block carries. Named **bare**, never prefixed with the composite id: the classify opener's `<namespace>/<id>` already scopes them (§principle 10), so a `composite/book` carries `title`/`author`/`isbn`, not `book_title`/`book_author`/`book_isbn`.
- `subclasses` (optional, interpretive) — finer-grained categories.

#### Deterministic membership — `classify_when`

When a record's membership in a class is decidable from **stable, deterministic facts**, the class declares a `classify_when` predicate and the drafter assigns it at draft time — so every record of a known kind reaches the normalizer with that class (and its `normalization.guidance`) already attached, rather than re-deriving membership each pass. It is **mechanical** (no LLM, no network, no clock) and **pure opt-in**: a corpus with no `classify_when` overlays behaves exactly as one without this feature.

`classify_when` is evaluated over a flat, normalized **fact base**:

| Fact | Source |
|---|---|
| `mime` | the artifact block's MIME |
| `origin.uri` / `origin.host` / `origin.path` / `origin.fragment` / `origin.query.<k>` | parts of an origin block's uri(s) — **any-origin** (matches if ≥1 origin uri satisfies) |
| `origin.id` | id of a matched origin overlay (§7.2) |
| `media.<field>` | normalized alias over the origin block's `ytdlp_<field>` fields (e.g. `media.channel_id`) — insulates rules from yt-dlp key drift |

Each leaf is `{<fact>: {<op>: <value>}}`, exact-by-default: `equals` (scalar equality), `in` (set membership), `glob` (shell-glob, for path/fragment/uri), `matches` (anchored regex — a documented sharp tool), `exists: <bool>`. Combinators `all_of` / `any_of` / `none_of` each take a list; a bare mapping of several `{fact: {op}}` at one level is `all_of` sugar. A **list-valued** fact (any-origin facts, `media.tags`) tests *any element* for `equals`/`in` and *non-empty* for `exists`.

Three guarantees bound false positives: (1) exact-match operators are the default; (2) **a missing fact is *false*** for every operator except `exists: false` — an HTML record has no `media.channel_id`, so a video rule can never fire on it (no null-matches-anything path exists); (3) the interpretive `applies_to.cues.body_contains` is **not** part of this fact base and MUST NOT be promoted to a deterministic trigger — body keywords are the canonical false-positive source and stay normalizer-only.

#### Scope-aware extended fields

A composite schema's `extended_fields` decompose into three field groups by scope:

- **Descriptive** — apply at every scope the schema declares in `applies_at`.
- **Structural** — apply at record scope only.
- **Citation** — apply at section scope only.

Group membership is declared per-field by adding `applies_at:` inside the field's mapping.

### 7.5 Semantic-type vocabulary

A closed list of seven types. Schemas tag extended-field declarations with one of these to opt the field into a derived view (§9) or document its meaning.

| Type | Aggregated into | Notes |
|---|---|---|
| `uri` | `uris` derived view | String. Deduplicated across all uri-tagged fields and origin-block `uri:` values. |
| `timestamp` | `timeline` derived view | ISO-8601 instant or interval. Aggregated with origin-block `snapshot:` values (§9.4). |
| `identifier` | `identifiers` derived view | Vendor-issued opaque ID. The view also includes the record's own `id` (§9.5). |
| `hash` | (no view) | Cryptographic hash. |
| `fingerprint` | (no view) | Non-cryptographic content fingerprint. The segment-header field is spelled `perceptual:` (§7.7), but the semantic-type tag spelling remains `fingerprint`. |
| `person` | (no view) | A single alias string identifying one person. |
| `geolocation` | (no view) | Location reference. |

The vocabulary is closed.

### 7.6 Hash encoding convention

All three frontmatter hash fields (`transport`, `canonical`, `perceptual`) and the body-block hash fields (`<!--embed--> transport`, `<!--segment--> perceptual`) use a uniform encoding:

- Value type: `str` or `list[str]`.
- Value format: `<algo>:<hex>` — algorithm identifier as colon-prefix, lowercase hex value following.
- Lists are one-liner-friendly: `transport: [<algo>:<hex>, <algo>:<hex>]`.
- Parsing: split on the first `:` to obtain `(algo, value)`.

The `id` field is the exception — always bare blake3 hex (algorithm is invariant).

### 7.7 Atom fingerprint strategies

Perceptual fingerprinting is **opt-in** and **schema-gated**. A segment carries a `perceptual:` only when a `fingerprint` knob resolves on for its record — fingerprints are a near-duplicate / similarity-search signal, not part of a faithful first-pass draft, so the default is **off** and a record with no `perceptual:` is normal. The knob is a top-level field on a **mime schema** (the per-file-type default) and may be overridden on a **composite classification** (for records of that class). Values: `false` / absent = off; `true` = on with each atom's *default* algorithm; an algorithm name or a list = on with those algorithms (a list yields a list-valued `perceptual:`). Resolution precedence, most-specific first: `corpus draft --fingerprint` / `--no-fingerprint` › composite classification (assigned classify block, then mechanical composites) › mime schema › off. Only what is knowable at draft is consulted; an **interpretive** composite (assigned by the normalizer post-draft) takes effect on a later recompile.

When fingerprinting is on, the algorithm for a segment is determined by its `atom:`, not by the source media-type. Each atom has a default algorithm; the knob may select an alternative where the atom supports more than one:

| Atom | Default algorithm | Algo prefix | Alternatives | Notes |
|---|---|---|---|---|
| `image` | perceptual hash (pHash, 64-bit) | `phash` | `dhash`, `ahash`, `whash` | Robust to re-encoding, mild crops, and small resamples. |
| `audio` | acoustic fingerprint (chromaprint) | `chromaprint` | — | Comparable across codec changes and bitrates. |
| `text` | simhash (64-bit) over normalized tokens | `simhash` | — | After Unicode normalization, lowercasing, and whitespace collapse. |

The `<algo>:<hex>` value records which algorithm produced it, so a record self-documents how it was fingerprinted.

---

## 8. Pipeline

### 8.1 Stages

| Stage | Mechanics | Touch identifier shape |
|---|---|---|
| `capture` | Bytes land in the corpus's staging area. | none |
| `ingest` | blake3 of bytes → `id`; additional algorithms per the mime schema's `transport_algos` → `transport:`; MIME detect → artifact-block opener; evaluate the mime schema's `artifact_kind`; emit stub with first origin block from capture context; persist binary in the corpus's binary store. | `<pkg>.ingest@<v>` |
| `draft` | Run the mime schema first (it segments the content zone, emits embed blocks, and — when it declares a `canonical_strategy` — sets `canonical`), then each mechanical classification in declared order (each emits/fills its classify block — metadata only); drafter-detected issue context blocks emitted. | `<pkg>.draft.<mime-type-id>@<v>`, then `<pkg>.classify.<namespace>-<id>@<v>` per mechanical classification |
| `normalize` | Interpretive classifications run via LLM; may fill classify-block fields, re-segment the content zone, surface issue context blocks; description authored. | `<model-id>` |

Idempotent re-capture is part of `ingest`. Concrete tooling is implementation-defined.

### 8.2 The deterministic / LLM boundary

| Operation | Type | Why |
|---|---|---|
| Hashing, MIME detection, mime schema lookup | deterministic | mechanical |
| Container disposition | deterministic | schema-declared |
| Mime schema's body draft, artifact-block field extraction, and `canonical` hashing | deterministic | scriptable |
| Mechanical classification field extraction | deterministic | scripted |
| Origin-host matching | deterministic | mechanical |
| Functional URI evaluation | deterministic | spec mandates |
| Description authoring | LLM | requires understanding |
| Body re-segmentation under interpretive guidance | LLM | requires judgment |
| Interpretive classification field filling | LLM | by definition |
| Issue surfacing | LLM (content) / drafter (mechanical) | depends on kind |

### 8.3 Re-runs

Every stage is independently re-runnable; re-runs are **scoped**.

- **Re-ingest** — re-encounters bytes that match an existing `id`. Appends a touch identifier; may append to origin blocks.
- **Re-draft (full)** — re-runs the mime schema followed by every mechanical classification.
- **Re-draft (scoped)** — re-runs only one schema. Refreshes ONLY the blocks/fields declared by that schema.
- **Re-normalize** — re-runs interpretive classifications.
- **Re-resolve** — bare resolver-cache regeneration.

Each re-run appends a new `touch[]` entry.

### 8.4 Re-stub

`re-stub` is a deliberate reset operation that returns a record to `status: stub`, ready for a fresh draft pass. Everything **derived from a schema decision** is discarded. Everything **tied to the bytes themselves** is preserved.

| What survives | What is reset |
|---|---|
| `id`, `transport` — byte-intrinsic. | `title` and `description` → empty; `canonical`, `perceptual` (record-scope). |
| The artifact block's opener (the MIME) and the origin blocks with their `uri:` history. | The artifact block's body fields, all classify blocks, all embed blocks, all sections/segments, all context blocks. |
| `visibility`. | `status` → `stub`; record body's content zone → empty. |
| `touch[]` collapses to its first entry (the original ingest touch) plus the re-stub touch. | |
| The persisted bytes. | |

Re-stub is invoked deliberately — never automatic. Its uses:

- Schema-shape design changes that make existing blocks invalid.
- Records whose accumulated normalize work was wrong.
- Migration from a deprecated schema generation.

Re-stub appends a `touch[]` entry of the form `<pkg>.re-stub@<v>`. It is also the natural translation point for migrating records from prior schema generations: a re-stub accepts older frontmatter on input and always writes v1.0-shaped stub on output, preserving byte-intrinsic state and discarding everything that depended on the prior schema shape.

### 8.5 The normalization queue

`normalize` (§8.1) is the one stage the corpus tooling does not itself run — it is interpretive, performed by an external **loop session** (a scheduled agent). The tooling provides only the **request/claim contract** that lets any actor ask for a (re-)normalization pass and await its result; it never invokes a normalizer.

**The queue never writes records.** Record `status`, `touch[]`, and body are authored solely by `ingest`, `draft`, and the normalizer (§8.1). Queue state is **external to the record** and untracked — regenerable orchestration, like `capture/` and `cache/` (§12.1). Queue operations are **read-only on records**: they may read a record (to gate on lint, or report a result) but never mutate it. One writer per concern — the normalizer owns `status`; the queue owns only its own entries.

**Requests are status-independent and repeatable.** A record may be enqueued at any status — `draft` for a first pass, or `normalized` for a *refinement* when a new overlay matches it or its guidance improves (re-normalize, §8.3). `normalized` is not terminal; each completed pass appends a `<model-id>` touch. Enqueue never inspects `status`.

A queue entry moves `idle → requested → claimed → idle`, recording the last pass's outcome:

| Verb | Effect | Writes record? |
|---|---|---|
| `enqueue <id>` | request a (re-)normalization pass; idempotent — a request arriving while one is pending joins it. | no |
| `drain` | atomically **claim** the next pending entry and emit its `id`; an empty queue is a non-error empty result — the loop's stop signal. Reclaims a claim whose lease has lapsed (a dead session). | no |
| `finalize <id>` | close the claimed pass **complete** — gated on the record being `status: normalized` and linting clean; refuses (non-zero) on a blocking finding, so a dirty pass is never reported done. | reads only |
| `release <id> [--failed]` | return a claim — bare re-queues it; `--failed` records a failed outcome. | no |
| `await <id>` | block until the requested pass reaches a terminal outcome; success/failure by exit status. | reads only |

**Done** means the normalizer set `status: normalized` *and* the record lints clean — `finalize` enforces both halves.

**Drivable by an external loop.** The claim is atomic (concurrent loops never double-claim) and every verb is non-interactive with a meaningful exit code and machine-readable output, so a scheduled agent loop runs `drain` → normalize the emitted id in-session → `finalize` (or `release --failed`) each iteration, ending when `drain` reports the queue empty. The normalizer reads the record's applicable overlays' `normalization.guidance` (§7.4); because domain knowledge rides in overlays, one generic loop serves every domain — a codex contributes by authoring overlays and enqueuing, not by supplying a normalizer.

---

## 9. Derived views

Cross-cutting aggregates over a record's frontmatter and body blocks, computed on demand. None are persisted.

### 9.1 The `classifications` view

Computed by walking the metadata zone:

```
classifications := []
on <!--artifact <mime-type>-->:
  classifications += ["mime/<mime-type>"]
on <!--origin <id>[/<subtype>]-->:
  if id present:
    classifications += ["origin/<id>[/<subtype>]"]
on <!--classify <namespace>/<id>[/<subtype>]-->:
  classifications += ["<namespace>/<id>[/<subtype>]"]
dedupe preserving body order
```

Embed blocks and context blocks are NOT included. Composites on **section** openers are also not included — they are section-scoped identity (read by walking the content zone, §4.3.2.1), not record-scope classifications. The walk does not distinguish provenance (§4.4.6): a `provenance: auto` classify block contributes its `<namespace>/<id>` entry exactly like an asserted one, so auto classes surface to `find --classification` and the normalizer for free.

A record carrying an artifact block, one qualified origin block, and one classify block yields:

```
[
  "mime/<mime-type>",
  "origin/<origin-id>",
  "<namespace>/<id>"
]
```

### 9.2 The `issues` view

The `issue`-namespace projection of the annotations zone (the full annotation set is the `context` view, §4.3.3):

```
issues := []
on <!--context issue/<id>[/<subtype>]-->:
  issues += { id: "<id>[/<subtype>]", severity, resolution, detector, address?, ...fields }
```

Returns structured records — each issue carries its id/subtype + universal fields + optional `address:` + any id-specific fields. Context blocks in other namespaces (`reference`, …) are not in this view.

### 9.3 The `uris` view

Aggregates:

- Every origin-block `uri:` value across all origin blocks (flatten lists).
- Every body-block extended field tagged `semantic_type: uri` declared by any matching schema.

Deduplicated with URL canonicalization.

### 9.4 The `timeline` view

Aggregates:

- Every origin-block `snapshot:` value.
- Every body-block extended field tagged `semantic_type: timestamp`.

Returns an ordered list of `(timestamp, source)` tuples sorted ascending, where `source` names the origin block or semantic-tagged field the timestamp came from.

### 9.5 The `identifiers` view

Aggregates every body-block field tagged `semantic_type: identifier`, plus the record's own `id`.

### 9.6 The `token_counts` view

Three **cumulative** estimates of a record's size as model context, for budgeting and discovery:

- `body` — tokens in the content zone's text-atom segment bodies only.
- `blocks` — tokens in the whole record markdown (frontmatter + every metadata/annotation block + the content zone). Always ≥ `body`.
- `full` — `blocks` plus an image-token estimate summed over image embed blocks and an image artifact, each `≈ min(width·height, cap) / pixels-per-token` from the declared dimensions (`0` when dimensions are absent).

The text tokenizer and the image constants are an implementation choice (impl-corpus.md), not part of the contract — what the spec fixes is the **shape**: three cumulative tiers, ordered `body ≤ blocks ≤ full`. Like every §9 view it is computed on demand and never persisted.

### 9.7 The `concepts` view

The `concept`-namespace projection of the context view (§4.3.3.4) — the dual of the `issues` view (§9.2). Each entry is a concept the record invokes, with its identity ladder (`label`, `url`, `concept`) and optional anchor (`address`, `quote`, `occurrence`); a segment-scoped entry is a *mention*, a record-scoped entry is *aboutness*. The `concept` id (`wikidata:Q…` / `enwiki:…` / `local:…`) is the join key by which independently-annotated records that invoke the same concept are related (§4.3.3.4). Like every §9 view it is computed on demand and never persisted.

### 9.8 How views are computed

A derived-view walker:

1. Loads the record's frontmatter and parses the body's three zones.
2. For each matched block, loads the corresponding schema chain.
3. Walks blocks, collecting values per view rules.
4. Deduplicates or sorts per view.
5. Returns the result.

Views are computed at query time.

---

## 10. Export

A record renders correctly only inside its corpus, because segment bodies embed derived views via functional URIs that need a resolver. **Export** produces a portable, self-contained rendering by materializing each functional-URI embed to a file alongside the exported record and rewriting the embed reference to point to the local file.

Embed rewrite contract:

```
![[corpus://<hash>?<params>|<alt-text>]]   →   ![<alt-text>](<local-file>)
```

Export is idempotent and untracked. The output layout (filenames, directory structure) is implementation-defined.

---

## 11. Out of scope

Genuinely deferred items for this spec version:

- **OCR for scanned PDFs** — the deterministic draft step records the scanned flag and an issue context block; OCR is future work.
- **Cross-record content addressing** via `<!--embed--> transport` — the shape leaves room for a corpus-wide `transport → (record_id, address)` index but the index itself is not specified. (Building it requires reconciling the `<algo>:<hex>` embed `transport` encoding with the bare-hex record `id` — strip the prefix and confirm `algo == blake3` before matching.)
- **Range-aware navigation** for content the resolver doesn't materialize.
- **`page=<N>-<M>` ranges** and other open transforms beyond §6.2.
- **Whole-corpus build tooling** — single-record export is in scope; bulk operations are not.
- **Export to non-markdown formats.**
- **Additional semantic types** beyond the closed seven.
- **Capturing the concept knowledge base.** Wikipedia/Wikidata is referenced by `concept` blocks (§4.3.3.4) as an external authority run locally; the corpus does not capture its articles as records, and the local KB (acquisition, search, read) is an implementation concern (impl-corpus.md), not a corpus-layer contract.

---

## 12. Implementation notes (non-normative)

This section catalogs conventional realizations of the spec contracts. None of it is mandated; an implementation is free to make different choices as long as it honors the contracts above.

### 12.1 On-disk layout

A typical filesystem-backed corpus is organized as:

```
corpus-<name>/
├── README.md                optional
├── records/                 tracked: record markdown files
├── artifacts/               UNTRACKED: raw binary cache
├── capture/                 UNTRACKED: in-progress capture staging
├── cache/                   UNTRACKED: resolver-output cache
├── queue/                   UNTRACKED: normalization request/claim state (§8.5)
└── schema/                  tracked: all schemas
    ├── mime/
    ├── origin/
    ├── atom/
    └── composite/
        ├── issue/
        └── <user-namespace>/
```

`records/` and `schema/` are tracked in version control. `artifacts/`, `capture/`, `cache/`, and `queue/` are regenerable and conventionally listed in `.gitignore`.

### 12.2 Sharding

For large filesystem-backed corpora, files under `records/`, `artifacts/`, and `cache/` are conventionally sharded by the first two hex characters of the leading hash:

```
records/<id[:2]>/<id>.md
artifacts/<id[:2]>/<id>.<ext>
cache/<urihash[:2]>/<urihash>.<ext>
```

This keeps any single directory under ~256 entries until the corpus reaches ~16k items per slot. Other sharding strategies (deeper trees, content-addressed object stores, etc.) work equally well.

### 12.3 Schema directory layout

The schema namespaces of §3 are conventionally laid out as:

```
schema/<namespace>/<namespace>.yaml              namespace universal
schema/<namespace>/<axis>/<axis>.yaml            axis common guidance (mime and atom namespaces)
schema/<namespace>/<axis>/<axis>_<id>.yaml       specific declaration
```

The **underscore-flattened** subtype convention (`text_html.yaml` inside `text/` rather than `html.yaml`) keeps filenames self-describing.

Inside `composite/`, namespaces with no axis decomposition use the simpler `schema/composite/<namespace>/<id>.yaml` form, with the namespace universal at `schema/composite/<namespace>/<namespace>.yaml`.

Inside `origin/`, overlays nest by **URI scheme family** (§7.2): `schema/origin/web/<host>.yaml` for http(s) sources (host-matched), `schema/origin/otherwise/<id>.yaml` as the catch-all, and other scheme families (`urn/`, `file/`, `s3/`) as a corpus needs them, with the namespace universal at `schema/origin/origin.yaml`. The overlay id is the bare `<id>` regardless of sub-namespace; the flat `schema/origin/<id>.yaml` form is read for back-compat.

### 12.4 Resolver surface

A common resolver surface is a CLI that writes the materialized result to disk and prints its absolute path:

```
$ resolve 'corpus://<hash>?<params>'
/abs/path/to/cache/<shard>/<urihash>.<ext>
```

Conventional flags: `--regenerate` to bypass cache, `--json` to print a sidecar with derivation metadata. Library and HTTP-service surfaces are equally valid.

### 12.5 Cache layout

A common resolver-cache layout mirrors the sharding convention:

```
cache/<urihash[:2]>/<urihash>.<ext>
```

where `urihash = hash(<canonical-uri>)`. Cache invalidation is by deletion; eviction policy is implementation-defined.

### 12.6 Export output layout

A common export layout writes one directory per exported record:

```
export/<record_id>/
├── <name>.md
├── <name>_001.<ext>
├── <name>_002.<ext>
└── ...
```

with embed-rewrite mapping each functional URI to a sequentially numbered local file.

### 12.7 Common address schemes (illustrative)

Media-type schemas declare their own address grammar (§4.3.2). Schemes that have proven useful in practice, as examples only:

| Axis | Example | Typical source |
|---|---|---|
| element | `el=<N>` / `el=<N>-<M>` | marked-up / HTML text (any element by 1-indexed position; output determined by the element) |
| page | `page=<N>` | paginated documents |
| block | `block=<N>` | block-structured documents without fixed pages |
| sheet | `sheet=<name>` (+ `bbox=<A1-range>`) | spreadsheets |
| time | `time=<tc>` / `time_range=<s>-<e>` | audio / video |
| frame | `frame=<tc>` | video stills |
| region | `bbox=<x>,<y>,<w>,<h>` | image crops (relative floats) |
| turn | `turn=<N>` | turn-structured transcripts / sessions |
| stream | `stream_id=<id>` | multi-stream media (composed onto another axis) |

Addresses compose with `&` (e.g. `page=<N>&bbox=<x>,<y>,<w>,<h>`); a single address or an ordered list (for non-contiguous spans, in reading order); query-reserved characters in a value are percent-encoded.

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **Corpus** | A content-addressed archive of captured artifacts. |
| **Record** | A markdown file with YAML frontmatter representing a single artifact. |
| **Artifact** | A captured file. Identified by the blake3 hash of its bytes. |
| **Transport** | The media-type-shaped container of a file. Also the name for the bytes-level hash field (`transport:`). |
| **Content** | What a transport carries. Decomposes into segments. |
| **Segment** | An addressable unit of content. Carries one atom, one address, and at most one atomic classification. |
| **Atom** | One of four content types: `text`, `image`, `audio`, `video`. |
| **Record body** | The markdown content below the frontmatter. Organized into three zones. |
| **Segment body** | The markdown prose inside a single `text`-atom segment block. |
| **Zone** | One of three partitions of the record body: metadata, content, annotations. |
| **Artifact block** | `<!--artifact <mime-type>-->` — exactly one per record. Opener arg is the authoritative media-type declaration. |
| **Origin block** | `<!--origin [<id>[/<subtype>]]-->` — one or more per record. Carries `uri:` and `snapshot:`. |
| **Classify block** | `<!--classify <namespace>/<id>[/<subtype>]-->` — zero or more per record. |
| **Embed block** | `<!--embed <mime-type>-->` — content-addressed asset metadata. Deduplicated by `transport:`. |
| **Section block** | `<!--section [<namespace>/<id>]-->` — structural grouping; the TOC unit. May carry one composite on the opener. Contains zero or more segments. |
| **Segment block** | `<!--segment <atom>-->` — the body's content atom. |
| **Context block** | `<!--context <namespace>/<id>[/<subtype>]-->` — an annotations-zone observation (namespaces: `issue`, `reference`, …); record- or segment-scope (via `address:`). |
| **Namespace** | One of `mime`, `origin`, `atom`, `composite`, `context`. Each is a schema axis or umbrella with its own block-keyword role. |
| **Mechanical classification** | `kind: mechanical` schema + associated script. Runs at draft time. |
| **Interpretive classification** | `kind: interpretive` schema with LLM-guidance prose. Runs at normalize time. |
| **`classify_when`** | A deterministic membership predicate on a composite schema (§7.4). When it matches a record's fact base, the drafter auto-assigns the class at draft time and stamps the classify block `provenance: auto`. Orthogonal to `kind`. |
| **Provenance** | On a classify or context block (§4.4.6): `provenance: auto` = engine-stamped (a `classify_when` match or a detector), stripped and regenerated on every re-draft / reclassify; absent or `asserted` = human/normalizer, never auto-touched. |
| **Self-contained / decomposable** | Container disposition declared by the mime schema (`artifact_kind`, required). `self_contained` produces one record (lifting nested-stream metadata when present; also the disposition for ordinary single-content files); `decomposable` explodes a raw archive into one record per member. |
| **Mode** | A mime schema's drafting behavior: `extract-only` or `body-draft`. Mechanical classifications are metadata-only and never body-draft. |
| **Capture, Ingest, Draft, Normalize** | Pipeline stages. |
| **Touch** | A single processing pass. Recorded in `touch[]`. |
| **Touch chain** | The ordered list `touch[0..N]`. Records current-shape provenance; reset by re-stub (§8.4). |
| **Re-stub** | A deliberate reset that discards body and accumulated metadata, leaving only byte-intrinsic state and the touch chain. See §8.4. |
| **Resolver** | The corpus-provided mechanism that materializes a functional URI to a deterministic result. |
| **Functional URI** | A `corpus://<hash>?<params>` URI naming a derived view. |
| **Derived view** | A computed aggregate over body blocks / semantic-tagged fields. |
| **Semantic type** | One of seven closed-vocabulary tags on schema-declared fields. |
| **Transport hash** | `transport:` — the bytes-level hash of the file. Encoded as `<algo>:<hex>`. |
| **Canonical hash** | `canonical:` — the canonicalized-content hash. |
| **Perceptual hash** | `perceptual:` — atom-canonical content fingerprint. |
