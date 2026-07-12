---
spec_id: ATH-CORPUS
title: "Corpus Specification"
version: 2.1
status: current
license: "CC BY-SA 4.0"
date_created: 2026-05-24
date_modified: 2026-07-04
---

# Corpus Specification

A **corpus** is the foundation layer of the Athenaeum system: a content-addressed archive of captured artifacts, represented as markdown records. This document is its complete specification, in two parts. **Part I (§1–§11)** is the normative data contract — every record in every corpus conforms to it, and tooling across the system cites its section numbers. **Part II (§12)** is the implementation guide: non-normative notes on how the reference pipeline produces conforming records. Two appendices follow — the glossary (Appendix A) and a non-normative content-type taxonomy (Appendix B).

The corpus sits beneath the ledger layer, which interprets it through `corpus://` functional URIs — see [`athenaeum.md`](athenaeum.md) for the system architecture, [`ledger.md`](ledger.md) for the knowledge layer, and [`codex.md`](codex.md) for the codex contract.

**Version 2.0** removed the corpus's interpretive classification system — the `composite` umbrella, the classify block, section-scope composites, the `concept` context namespace, and the interpretive `reference` emission path — in favor of the ledger layer: a record describes its bytes, retrieval, and faithful form; what its content *means* is asserted one layer up, with evidence pointing back down. Removed sections are **tombstoned in place** (numbering preserved, successor named) rather than renumbered, so 1.0-era citations of this spec still land somewhere true.

**Version 2.1** — the **containment amendment** — decoupled records from standalone artifact files. Every transport is now self-contained (the `decomposable` disposition and the `artifact_kind` declaration retire): a raw archive drafts as an embed manifest, and any declared member may be **promoted** to a first-class record whose bytes remain inside the container, resolved by streaming (§2, §1.2, §8.1). No existing record changes shape (§12.17).

---

# Part I — The contract (normative)

## 1. Overview

### 1.1 What this is

A **corpus** is a content-addressed archive of captured artifacts, accessed through faithfully represented markdown proxies called **records**. Artifacts are deconstructed into addressable segments and normalized to text, either losslessly or by description. A record classifies its artifact **mechanically** — what the bytes are (media type) and where they came from (origin); what the content *means* is the ledger layer's concern ([`ledger.md`](ledger.md)), asserted there as claims whose evidence points back into the record.

A record is a single markdown file. The YAML frontmatter at its head carries a small bytes-identity header — what these bytes ARE (their hashes), the editorial summary, the provenance chain of processing passes. The **record body** below the frontmatter is organized into three **zones**: a **metadata zone** declaring what the artifact is, where it came from, and what assets it embeds; a **content zone** carrying the rendered content as sections and segments; and an **annotations zone** carrying observations about the record. Each zone holds a small set of HTML-comment block families; §4.3 specifies the grammar.

### 1.2 The transport model

Every captured file is a **transport** — a media-type-shaped container — that carries **content**.

- A transport's **intrinsic information** surfaces in the record's metadata zone — primarily in the artifact block for transport-intrinsic fields.
- A transport's **content** decomposes into a flat sequence of addressable segments in the record's content zone. Each segment carries one of four **content atoms** (text, image, audio, video) and an **address** indicating its location inside the transport.
- Every transport is **self-contained**: it produces a single record. When it contains a **nested transport**, it lifts that nested transport's intrinsic metadata into the outer record's artifact block (e.g. per-stream fields for a multi-stream media file) and addresses its content per stream / per member, while an asset it merely references is described as an embed in the metadata zone. An ordinary single-content file (a plain HTML page, a PDF) simply has no nested transport to lift. A **raw archive** — a transport whose content is *other transports* — drafts as an **embed manifest**: every member becomes a content-addressed embed (the member's `transport:` byte-hash + its member address) and the content zone stays empty (§12.4). *(2.1: the schema-declared disposition — `artifact_kind`, with its `decomposable` explode-at-ingest alternative — is removed; §7.1.)*
- A declared member is thereby **promotable**: because its embed records byte identity and address, it may later be minted as a first-class record of its own (**promotion**, §8.1) without its bytes ever leaving the container — a lookup of the promoted `id` streams them out through the container's address scheme (§2). Containment nests (a promoted member may itself be a container), and **residence is invisible**: the same bytes may live standalone, inside a container, or both, and no record changes when they move (§2).

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
       │ ingest             deterministic: hashes, MIME detection; stub record written
       ▼
   stub record              identity established; bytes persisted in the corpus's binary store
       │
       │ draft              deterministic: media-type schema runs; overlay-declared emissions follow
       ▼
   draft record             faithful first-pass body, segment layout established, mechanical metadata-zone blocks emitted
       │
       │ normalize          LLM-guided faithful-form pass: description authored, body re-segmented / shaped where judged
       ▼
 normalized record          faithful form finalized — ready to cite
```

Once ingested, the artifact's bytes must remain retrievable by id. Where and how the implementation stores them is its concern; the contract is that a lookup by id produces the bytes. **Promotion** (§8.1) is a second entry point to `stub`: it mints a record for a container member's bytes, which are already retrievable by id through the container (§2) and are not copied. Re-running any stage is an expected refinement pattern, not a fallback; every stage from ingest onward appends a `touch[]` entry to the record's provenance chain (which `re-stub` may reset, §8.4).

### 1.5 Design principles

1. **Layered foundation.** The corpus is a foundation layer — the truth, the baseline. It depends on nothing; any system that builds atop it depends on the records it produces.

2. **Content addressing.** Every artifact's identity is the blake3 hash of its bytes. Bytes don't change; if they did, the hash would change and the record would be a different record.

3. **Faithfulness.** A record body is a faithful, lossless rendering of the transport's content. Normalization may resolve ambiguity (encoding, broken layout, OCR for scans) but never adds information not present in the source. Descriptive content (a summary of what an image shows, a paraphrase of what was said) is lossy by definition and lives on the matching embed's description field — or, when no embed exists, on the addressing segment's or section's `description:` — **not** in a segment body. Re-segmentation is structural, never editorial.

4. **The record body as universal representation.** Every artifact carries a markdown body composed of segments. This projects every modality — text, image, audio, video — into a common representational space. Search, similarity, and embeddings all operate on the body.

5. **Transports declare, content fills.** Format-specific machinery (address scheme, extraction strategy, body shape) lives on the media-type schema. Content-shaping tactics live on origin overlays (per source) and atom overlays (per form). The layers don't bleed.

6. **Deterministic before LLM.** Capture, ingest, and draft are scripts; the normalize pass is LLM-guided **faithful-form** work whose every output is checkable against the bytes in the same file. Interpretation — what content means — is not a corpus stage at all: it happens in the ledger, with evidence citing back into the record.

7. **On-demand derived views.** Cross-cutting aggregates and richer modal projections are computed by walking body blocks and semantic-tagged fields, or by resolving functional URIs — never persisted alongside the record.

8. **Stable identity, mutable metadata, faithful body.** A record's `id` is fixed at capture. Body blocks evolve as drafting and normalization improve; the body content remains faithful.

9. **Offline-first.** Only `capture` requires network access. Ingest, draft, normalize, and URI resolution all operate on local data.

10. **Frontmatter is bytes-identity only.** What the bytes ARE (their hashes), how visible they are to authoring tools, how to navigate the provenance chain, the editorial display title + summary the normalizer authors. Everything else — the title *candidates*, media-type, origins, issues, extended fields — lives in body blocks because everything else came from a schema decision, and schema decisions are auditable per-block. A field is named **bare** when its block opener already identifies its provenance: an artifact block names the format (its MIME), a context block names its namespace (`<namespace>/<id>`), so their fields are `title`/`author`/`severity`, never `pdf_title`/`issue_severity`. A provenance prefix survives only where the opener does *not* carry it — an origin block's `ytdlp_title` (the opener names the source record, not the extraction tool), or a metadata sub-standard the format embeds (`exif_*`, `og_*`). (Prefixing every field was a holdover from when these all shared the frontmatter's flat namespace; once each rides its own self-identifying block, the prefix only echoes the block.)

11. **Classifications are derived, not declared.** A record's classifications list is computed by walking its metadata-zone blocks — the artifact block yields `mime/*`, qualified origin blocks yield `origin/*`. The body IS the classification declaration. The same principle applies to issues (walks annotations-zone blocks) and to the aggregated URI, timeline, and identifier views (which walk semantic-tagged schema fields together with the universal origin `uri:`/`snapshot:` fields and, for identifiers, the record's own `id` — §9).

---

## 2. Identity

Every artifact is identified by the blake3 hash of its bytes — a 64-character lowercase hex string. This identifier is the record's `id` and the lookup key by which the corpus's binary store produces the bytes. The implementation owns where and how the bytes are stored; the contract is that an `id` resolves to its bytes.

An id need not resolve to a *standalone* file. When a captured container's record declares a member as a content-addressed embed (the member's `transport:` hash with a resolvable member address), that member's bytes are retrievable by their own blake3 **through the container**: the implementation streams them out via the container's address scheme, recursively when containers nest. How the route from a bare id to its container is found is implementation-defined, but it MUST be **derived** from the records' embed declarations — never stored on the promoted record (§12.9) — so bytes may move between standalone residence and containment, or be resolvable by several routes at once, without any record changing. Every route to an id yields identical bytes by construction; a resolver may take any.

The `id` field is bare hex with no algorithm prefix because the algorithm is invariant. All other hash fields in the spec use an `<algo>:<hex>` prefix encoding (§7.6) so that multiple hash families can coexist within one field.

---

## 3. Schema namespaces

A corpus's schemas are organized into four spec-reserved **namespaces**. Three are primitive **axes** — each bound to a single block-keyword role in the record body — and one is an umbrella: `context` for annotations:

| Namespace | Role | What it declares |
|---|---|---|
| `mime` | Declares the **artifact block**. | Per-media-type fields, address scheme, body-draft behavior. |
| `origin` | Declares the **origin block**. | Per-source-of-retrieval overlays: how to recognize an origin, what additional fields it contributes, how to capture and draft it. |
| `atom` | Declares the **atomic classification** on a **segment block**. | Per-atom-and-subtype overlays: what *form* of content a segment carries, and (for text-atom overlays) whether it licenses a shaped lossless body. |
| `context` | The umbrella for every **annotation** namespace — observations *about* a record. | Per-namespace overlays declared via the **context block** (`context/<namespace>/<id>`): `issue` (problems), `reference` (declared dependent links), `relation` (declared cross-links), … |

*(2.0)* The 1.0 model had a fifth namespace — `composite`, the umbrella for user-defined classification namespaces asserted on records via classify blocks. It was removed: what content means is knowledge, and knowledge lives in the ledger, minted mechanically by harvest rules where membership is deterministic and authored as claims where it is not (`ledger.md` §8, §10). See the §7.4 tombstone for where each of its parts went.

A record references a schema by the qualified id encoded on a block opener — for example, `<!--context <namespace>/<id>-->`. The schema loader resolves the id by walking a chain of declarations from most-specific to least-specific:

1. The subtype-overlay declaration (`<namespace>/<id>/<subtype>`), if a subtype is present on the opener.
2. The id declaration (`<namespace>/<id>`).
3. The id's parent declaration, if the id is itself two-part within the namespace (applies in the `mime` and `atom` namespaces where ids decompose into axis + subtype, such as `mime/text/html` or `atom/text/data-table`).
4. The namespace's universal declaration.

Each layer's declared fields extend its parent's; conflicts resolve in favor of the most-specific declaration.

The on-disk organization of these schemas is implementation-discretionary; a reference layout appears in Part II (§12.2).

---

## 4. Records

### 4.1 What a record is

A markdown file with YAML frontmatter. The frontmatter carries the bytes-identity header; the record body carries the schema-derived metadata blocks AND the segmented rendering of the transport's content AND any annotations.

A record is always at one of three statuses:

| Status | Meaning | Stage that produced it |
|---|---|---|
| `stub` | Identity established; bytes retrievable by id (§2 — persisted to the binary store at ingest, or resident in a containing artifact for a promoted record); artifact block emitted; first origin block populated from capture / containment context; content zone empty. | ingest / promote |
| `draft` | Media-type schema applied; record body's content zone segmented per the media-type schema; embed blocks and overlay-declared context blocks (references, relations, drafter-detected issues) emitted. | draft |
| `normalized` | Faithful form finalized: description authored; content zone re-segmented and shaped where the LLM judged appropriate; faithfulness issues surfaced. | normalize |

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

- **Pipeline tooling** uses a stable identifier of the form `<package>.<module>@<version>`, where `<module>` may be a dotted path (e.g. `draft.<mime-type-id>`). The `<package>.<module>` identifies the code path; `<version>` is its installed version.
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
<!--embed <mime-type>-->                  # 0..N

─── content zone ─────────────────────────
<!--section-->                            # 0..N (each contains 0..N segments)
or
<!--segment <atom>-->                     # 0..N (sectionless top-level segments)

─── annotations zone ─────────────────────
<!--context <namespace>/<id>[/<subtype>]--># 0..N (record- or segment-scoped via address:)
```

Zone order is fixed. A block of a later zone appearing before a block of an earlier zone is a parse error. Within a zone, the relative order of different block *families* is not significant; the diagram's family order is illustrative. **All metadata- and annotation-zone blocks are header-only**: their YAML payload is the entire block; there is no markdown content between blocks within those zones. **Only segment blocks carry inline content** — the segment body holds the actual text.

#### 4.3.1 The metadata zone

The metadata zone carries the artifact's identity, its origins, and its embedded assets. Three block families.

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

One or more per record. Each block describes one origin (one source of retrieval). `snapshot:` (ISO-8601 timestamp of when this origin was observed) is always required. A *retrieval* origin also carries `uri:` (string or list-of-strings — a canonical URL plus its shortlinks/redirects collapse to one block whose `uri:` is a list). Multiple origin blocks describe genuinely separate sources. A capture with **no retrieval URL** (a dropped-in local file) records a uri-less origin: there is no retrievable source — the staging path is unlinked at ingest — so instead of a `file://` path that dies on arrival, the block carries the durable `filename` (basename) and `source_modified` (the file's mtime); see §7.2.

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

##### 4.3.1.3 The classify block *(removed in 2.0)*

*Retired.* The classify block asserted record-scope interpretive classification — the `composite` umbrella's surface. That assertion is knowledge, and it moved to the ledger: what a record documents is expressed as ledger concepts and claims — the record rostered as an artifact of the thing and cited as evidence (`ledger.md` §4) — minted mechanically by **harvest rules** where membership is deterministic (`ledger.md` §10) and authored where it is not. The corpus-side classifications view (§9.1) retains its structural-derived rows (`mime/*`, `origin/*`). The reserved `provenance` field survives on context blocks (§4.3.3.1) with the same semantics.

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

A **section** is the universal grouping primitive — a chapter, a heading-delimited block, a sheet, a user turn, a speaker run. It is the table-of-contents unit. A section has a bare opener and a YAML header carrying an address and an optional `entry` (the TOC label). Sections contain segments; they have no body of their own.

```
<!--section
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

*(2.0)* Section openers are bare. The 1.0 section-scope composite — what a passage IS on its own terms — is expressed, when a domain cares, as a ledger claim whose evidence anchors the section's span (`ledger.md` §6); the record itself makes no such assertion. See the §4.4.3 tombstone.

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
| `entry` | A short identifying label — the TOC line. MULTI-block sectionless records carry `entry:` on each top-level segment; in-section segments don't (the section is the TOC unit); and a record whose content zone is a single top-level block carries none — such a record is its own TOC line, already labelled by the frontmatter `title`. |
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

The mime schema is the **only** body-drafter — it alone owns the content zone. A pass operating in body-draft mode **completely overwrites** any existing content zone in the record body. No dependency on prior content; no expectation that future content survives; same bytes always produce the same content zone (modulo extractor version). Body-drafting is total replacement. Overlay-declared emissions (§7.2) are metadata/annotations-only and never body-draft.

#### 4.3.3 The annotations zone

The annotations zone carries observations *about* the record — problems with it, sources it cites, derived relations. One block family: the **context block**, drawing its overlays from the `context/` umbrella (§3), with one namespace per kind of observation (`issue`, `reference`, …). Context **never** contributes to the faithful content zone or the canonical content hash — it is a side-channel that accretes without disturbing the lossless body.

**Context is scarce by design.** A record carries a context block only when it records durable, high-value information the faithful body cannot — a detected problem (`issue`), a declared dependent link resolved toward capture (`reference`), an overlay-declared chrome extraction (`aside`), a source-declared cross-link (`relation`). It is emphatically **not** a normalizer scratchpad: a normalizer MUST NOT emit commentary, summaries, running notes, or "what I did" prose as context. The **mechanical** namespaces (`aside`, `reference`, `relation`) auto-populate *only* on real signal and *only* where overlay-gated — each exists **solely** where an origin overlay declares the extraction, and there are none absent that declaration; every block requires a referent actually present in the content (a declared link or structure in the page). `issue` is the one namespace with an asserted path: the normalizer surfaces **faithfulness** problems (garbled OCR, truncated content) beside the drafter's mechanical detections. Absent real signal the annotations zone is **empty** — the normal state for most records.

*(2.0)* The 1.0 interpretive `reference` path — normalizer-found citations in the content — moved to the ledger: a found citation is a `capture`/`search` need or, where the domain cares, a citation edge with span evidence (`ledger.md` §7). The 1.0 `concept` namespace was removed outright (§4.3.3.4). Content-*meaning* observations of every kind are ledger material; the annotations zone records only what is mechanical or faithfulness-scoped.

##### 4.3.3.1 The context block

Zero or more per record. Each is a typed observation, optionally pinned to a segment. The opener `<namespace>/<id>` matches the corresponding `context/<namespace>/<id>` overlay; an optional `<subtype>` extends it.

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

One field name is **reserved**: `provenance` (§4.4.6). `provenance: auto` marks an engine-stamped block (a drafter detection, an overlay-declared emission) that is stripped and regenerated on re-run; its absence (or `provenance: asserted`) marks a human- or normalizer-asserted block that the engine never touches. No namespace may declare `provenance` as an overlay field.

Context blocks **do not** contribute to the derived classifications view (§9.1) — they surface in the derived `context` view, of which the `issues` view (§9.2) is the `issue`-namespace projection. Conceptually, a *classification* says what the content IS; a *context* records something observed about it.

##### 4.3.3.2 The `issue` namespace

An `issue` context block (`<!--context issue/<id>-->`) is a typed problem with the record or a segment. Its universal overlay (`context/issue/issue.yaml`) declares:

- `severity` — typically `blocking | warning | info` (the schema declares the closed set).
- `resolution` — typically `open | fixed | wontfix | superseded`.
- `detector` — touch identifier of the pass that emitted the issue.

Per-id overlays (`context/issue/<id>`) extend with id-specific fields. The `severity`/`resolution` value sets are corpus-local (schema-declared); cross-corpus tooling should treat unknown values gracefully rather than assuming a fixed vocabulary. Issues come from three sources — the **drafter** (deterministic detections: bot blocks, corrupt encoding, missing inputs), the **normalizer** (content-meaning problems), and **external** health-signal sweeps — each recorded in `detector` and, where engine-owned, `provenance: auto`.

##### 4.3.3.3 The `reference` namespace

A `reference` context block (`<!--context reference-->`) records a **declared dependent link** — a product page's manual, a spec sheet — emitted at draft from an origin overlay's `capture.references` declaration (§7.2), carrying `provenance: auto` and a corpus-local **`role`** field (`manual`, `spec-sheet`, …; schema-declared closed set, treated gracefully when unknown). It is pinned to its link's mention via `address:`/`quote:` (the link text) and carries the **citation ladder** (§4.4.5) at tier 1–2: `attribution_text` (the link text) → `source_url` (the resolved href).

**The intra-corpus edge is derived, never stored.** Whether `source_url` is itself a captured record is a **read-time derived edge** — resolved against the URI index by `derived_views.references` (§9.9) / `corpus links --references`, never baked into the record — so `draft` stays a pure function of the artifact (it reads no corpus state) and the edge self-heals (`captured ⇄ pending`) as targets are captured, removed, or superseded. As an `auto` block it is regenerated on re-draft.

*(2.0)* The 1.0 interpretive emission path (normalizer-authored citations found in the body, including the stored tier-3 `source_uri`) moved to the ledger (§4.3.3 note). The reference block is now mechanical-only: capture plumbing, not citation knowledge.

##### 4.3.3.4 The `concept` namespace *(removed in 2.0)*

*Retired.* The concept block was the ledger's shadow: a per-record entity annotation resolved against an external knowledge base (Wikipedia/Wikidata), built because no internal entity layer existed — its `concept:` id was "the join key by which records that invoke the same concept are related without either knowing about the other," which is precisely what a ledger **concept** is (`ledger.md` §4 — the namespace's very name graduated with it). The ledger replaces every part of it: record-scope *aboutness* is coverage and the artifact roster (`ledger.md` §9, §4.2); a span-scoped *mention* is claim evidence anchored by a functional URI; the external join key (`wikidata:Q…`) is a concept-level external-identity claim citing a mirrored reference dataset (`ledger.md` §6.5), made once, not stamped per record. The local-KB machinery (1.0 §12.12) retires with it.

##### 4.3.3.5 The `relation` namespace

A `relation` context block (`<!--context relation[/<predicate>]-->`) records a **source-declared cross-link** from this record toward another resource — navigation structure actually present in the content (a "related information" rail, sibling-page links) — typically lifted from chrome the faithful body drops, making the annotations zone its proper side-channel home. Mechanical: the lift is declared per host on the origin overlay (`capture.relations`, §7.2) and emitted at draft with `provenance: auto`. The target is recorded as `target_text`/`target_url` — **URL-tier only**: at the corpus layer a record never links another record by id; the URL is the edge, resolved to a captured record at read time exactly as references are (§9.9). An optional `predicate` subtype names the relation kind per the corpus-local overlay.

*(Migration note, non-normative: relation blocks emitted by 1.0-era normalize passes are asserted-labeled; they relabel to `provenance: auto` as origin-declared lifting lands in the drafter.)*

### 4.4 Classifications: scope and fidelity

Classifications identify what a record (and its segments) IS — **structurally**: its format, its retrieval source, the form of its content. What a record's content *means* is not a classification at this layer; it is ledger knowledge (`ledger.md`). The framework rests on two ideas: what *kind* of classification is being made (three axes) and what structural *scope* it applies at.

#### 4.4.1 The three classification axes

Every classification falls along one of three conceptual axes. Each axis has its own block, its own schema namespace, and its own scope rules.

| Axis | What it identifies | Block | Schema namespace |
|---|---|---|---|
| **media-type** | The format / container / transport of the bytes. | artifact block (exactly 1) | `mime` |
| **origin** | Where the bytes came from. | origin block (1..N) | `origin` |
| **atomic** | What *form* of atomic content a segment carries. | segment-block opener | `atom` |

**media-type** and **origin** are properties of the bytes — they live at record scope only. **atomic** is a **structural-form** judgment — what shape of content a segment carries (a table, a transcript, a chat message, a screenshot), checkable against the bytes like everything else in the faithful zone; it applies at segment scope. *(2.0: the 1.0 model called the atomic axis "interpretive" and had a fourth axis — **composite**, domain meaning at record and section scope. Composite moved to the ledger; atomic was never meaning — see the constitution in §7.3.)*

Atomic-axis schemas declare two extra keys beyond the universal classification fields:

- `applies_to.atom` — which atom this overlay attaches to (`text`, `image`, `audio`, or `video`). Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `enables_lossless` (boolean, default false) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's declaration describes what shape the body takes.

A segment carries **exactly one** atomic class id, on the opener line. When multiple representations apply to the same source region, each becomes its own segment.

#### 4.4.2 Scopes

Classifications attach at two structural scopes — record and segment — plus the **embed**, where the media-type axis attaches via each embed's MIME:

| Axis | Record | Segment | Embed |
|---|---|---|---|
| media-type | ✓ (artifact MIME, via artifact block) | — | ✓ (per-embed MIME on the opener line) |
| origin | ✓ (capture-time match, via origin block) | — | — |
| atomic | — | ✓ (on the segment opener) | — |

Sections carry no classification in 2.0 (§4.4.3).

#### 4.4.3 Section scope *(dissolved in 2.0)*

*Retired.* The 1.0 section-scope composite (a passage's identity — "this section is a recipe") and the further-deferred identity+role dual-composite citation model (borrowed material carrying both what it is and what it does in the host) are both expressed as **ledger claims over section spans**: span-precise evidence URIs make "what this passage is" and "what this passage does here" two claims about one anchor, with no record-side mechanism at all. Nothing remains at this layer.

#### 4.4.4 Scope-driven fidelity *(removed in 2.0)*

*Retired with the composite namespace.* The three field groups (descriptive / structural / citation) organized composite extended fields by scope; composite fields are now claim values and qualifiers in the ledger. The citation field group's survivor is the mechanical reference block's ladder (§4.4.5).

#### 4.4.5 The citation ladder (mechanical)

A declared dependent link progresses from lossy toward lossless:

| Tier | Citation field | Meaning |
|---|---|---|
| **1** | `attribution_text` | Free-text (the link text). Ambiguous but captured. |
| **2** | `source_url` | Resolvable URL. |
| **3** | *(derived, never stored)* | The captured record the URL resolves to. |

The ladder is carried by the **`reference` context block** (§4.3.3.3), pinned to the exact mention via `address:`/`quote:`. Host records never change shape — enrichment happens at the linked target. Tier 3 is always a **read-time resolution** of `source_url` against the URI index (§9.9): `draft` reads no corpus state and stays a pure function of the artifact, and the edge self-heals (`captured ⇄ pending`) as targets are captured, removed, or superseded rather than leaving a stored pointer that dangles. *(2.0: the 1.0 asserted tier-3 `source_uri` — a hand-linked citation with no resolvable URL — moved to the ledger with the rest of citation knowledge.)*

#### 4.4.6 Provenance

A record's metadata and annotations have one of three **provenances** (who put a datum there, and what re-running does to it):

| Provenance | How it appears | On re-run |
|---|---|---|
| **structural-derived** | `mime/*`, `origin/*` — walked from the artifact / origin blocks (§9.1) | recomputed |
| **auto** | a context block with `provenance: auto` — a drafter detection or an overlay-declared emission (references §4.3.3.3, relations §4.3.3.5) | stripped + regenerated from the current overlays |
| **asserted** | a context block with no `provenance` — human / normalizer (faithfulness issues) | never touched |

*(2.0: the 1.0 ladder's classify-block rows — `classify_when` auto-membership and asserted composites — moved to the ledger; deterministic membership is now a harvest rule with the same auto/asserted discipline at the claim level, `ledger.md` §10.)*

#### 4.4.7 Re-run lifetime

Metadata- and annotations-zone blocks persist across re-runs **unless the pass that owns them is itself re-run**. A re-draft of the mime schema refreshes the artifact block and, for a body-draft mime schema, re-runs the body draft (re-segmenting the content zone, re-emitting embeds and overlay-declared `auto` context blocks). A re-normalize refreshes the faithful-form work (descriptions, segmentation, the editorial fields) and asserted faithfulness issues. To deliberately reset all accumulated metadata, use the `re-stub` operation (§8.4).

---

## 5. URIs and references

### 5.1 URI forms

Three URI forms appear within the corpus:

- **Plain URLs** — for unresolved external references in segment bodies whose targets aren't captured in the corpus.
- **Raw blake3 wikilinks/embeds** — `[[<blake3>|link text]]`, `![[<blake3>]]` — intra-corpus references whose targets are captured artifacts.
- **Functional URIs** — `corpus://<hash>[?<params>]` — composable references resolved to derived views (§6).

### 5.2 Re-capture

If the same bytes are encountered again, the record's identity is unchanged. The capture URL may differ across encounters, so origin blocks are append-only: each re-encounter checks the canonicalized capture URL against existing origin blocks' `uri:` entries and either appends to an existing origin's `uri:` list (when the new URL aliases an existing origin via known shortlink/redirect rules) or emits a new origin block (when it's genuinely a separate source). A re-dropped local file (a uri-less origin) dedups by `filename` instead of a URL — the same bytes under the same name append no duplicate origin, while the same bytes under a *different* name record a distinct local source (its own origin).

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
| `page=<N>` | PDF | image | Select page N (1-indexed). On its own it renders the page as an image; an image op or `bbox=` after it auto-renders first. |
| `page=<N>&render` | PDF page | image | Render the selected page as an image (the explicit form of a terminal `page=<N>`). |
| `page=<N>&text` | PDF page | text | The page's embedded text layer, verbatim — not an OCR of the raster; empty when the page carries no text layer. |
| `page=<N>&words` | PDF page | json | The page's text-layer words, each with a `bbox` (`[0.0, 1.0]` page fractions, origin top-left). |
| `page=<N>&probe` | PDF page | json | Per-page structural signals: dimensions, rotation, text/image-coverage stats, an invisible-text flag, and an advisory shape hint. |
| `probe` | PDF | json | Whole-document structural probe: per-page table, `/Info`, outline presence, and a shape summary. |
| `outline` | PDF | json | The PDF outline / TOC tree (nested `{title, page, children}`). |
| `time_range=<s>-<e>` | video / audio | media slice | Extract a time range. |
| `stream_id=<id>` | multi-stream media | stream-isolated | Select a specific stream. |
| `bbox=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Crop a relative region (image: floats in `[0.0, 1.0]`, origin top-left) or narrow a worksheet (spreadsheet: an A1 range, e.g. `bbox=B2:G30`). Polymorphic — see below. |
| `crop=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Alias for `bbox` (inherits its polymorphism). |
| `mark=<x>,<y>,<w>,<h>[;…]` | image | image | Outline the region(s) on the **whole** image (does not crop) — the inspection dual of `crop`, showing where a region sits in context. Relative floats in `[0.0, 1.0]`; `;`-separated for multiple regions. |
| `resize=<W>x<H>` | image | image | Resize to absolute pixel dimensions (forces both, may distort or enlarge). |
| `fit=<W>x<H>` \| `fit=<preset>` | image | image | Downscale to fit within a bounding box, aspect-preserving; reduce-only (never enlarges). A `<preset>` names an implementation-defined budget. |
| `rotate=<90\|180\|270>` | image | image | Rotate clockwise by a quarter turn (lossless; 90/270 swap width and height). |
| `auto_orient` | image | image | Apply the image's EXIF orientation tag so a sideways/flipped capture displays upright. No-op when absent. |
| `autocontrast` | image | image | Stretch the per-channel histogram to full range (legibility for faint scans). |
| `contrast=<factor>` | image | image | Scale contrast by a float factor (`1.0` unchanged). |
| `grayscale` | image | image | Convert to single-channel grayscale. |
| `dpi=<N>` | (render config) | (config) | Rasterization DPI for `page=<N>`. Position-independent. Default 200. |

A parameter applied to an incompatible working type is a hard error.

A PDF `page=<N>` is a **page selector**, not an unconditional render: a per-page op after it (`render`, `text`, `words`, `probe`) reads the *selected page* directly, so `page=<N>&text` returns the page's embedded text layer rather than an OCR of its render. A terminal `page=<N>` (and any image op or `bbox=` after it) renders the page to an image, so an `address: page=<N>` image marker (§4.3.2.2) still resolves to the page bytes. The whole-document ops `probe` and `outline` operate on the PDF itself (no page selected). These introspection ops are how a normalizer determines a PDF's shape and extracts its content — the drafter itself is uniform (§11).

`fit=` presets are **implementation-defined**, not enumerated here: a preset (e.g. `llm`) bounds the result to a consumer's budget — typically a vision model's maximum input dimensions and pixel count — and those limits are model-dependent and drift over time, so freezing them into the spec would rot. The normative contract is only that `fit=` downscales aspect-preserving and never enlarges; the concrete bounds of any named preset live in the resolver implementation.

Parameter value grammar may be media-type-dependent; the resolver dispatches on the source artifact's type. In particular `bbox` is **polymorphic** — relative floats in `[0.0, 1.0]` when cropping a rendered image (an image artifact, or a `page=` render of a PDF), and a spreadsheet cell range (e.g. `bbox=B2:G30`) when narrowing a worksheet region — so the same token does not collide across media types. Pure **address selectors** that locate a region without transforming it — `sheet=<name>`, `el=<N>` (a 1-indexed index to *any* addressable element in an HTML artifact — content blocks plus inline-media carriers `<img>`/`<video>`/`<audio>`/`<a href="data:…">`; what it materializes is determined by the element, e.g. an `<img>`'s rendered image, a `<video>`/attachment carrier's raw bytes, or a text element's region), and any others — are defined by each media-type schema (§4.3.2) and are not enumerated here; §6.2 lists only the parameters that produce a derived view.

### 6.3 The resolver

A corpus provides a **resolver** that materializes any functional URI to a deterministic, cacheable, ephemeral result. Given the same URI and the same source artifact, a resolver always returns the same result; the URI is the cache key.

The resolver's surface (CLI, library, HTTP service, etc.) is implementation-defined; the contract is that the URI scheme of §6.1 and the transformations of §6.2 are honored.

### 6.4 Caching

Resolver results may be cached. Cache lifetime, eviction policy, and storage location are all implementation-defined; the spec mandates only that the result is deterministic and reproducible from inputs.

---

## 7. Schema declarations

§3 introduced the four namespaces and the schema-loader resolution chain. This section specifies what the three schema-declaration namespaces (`mime`, `origin`, `atom`) declare; the `context` umbrella's overlays are specified alongside the context block in §4.3.3.

### 7.1 The mime namespace

A `mime` schema declares everything the matching artifact block needs and everything the drafter needs to process the transport.

- `description` — prose definition.
- `applies_to.content_types` — list of canonical MIME types this schema covers.
- `applies_to.zip_members` / `applies_to.zip_member_patterns` (optional) — shape signature for a zip-shaped type whose telltale members sit under a *variable* wrapper directory (a diagnostics export, a backup bundle), so a fixed internal path can't recognize it. `zip_members` lists exact member paths (ANY present matches); `zip_member_patterns` lists member-path regexes (EACH must match some member). Evaluated by the shared MIME refiner against the corpus's schemas, so vendor/site-specific zip recognition lives in the overlay rather than the package. Universal zip formats (OOXML / EPUB / JAR) keep their fixed-path signatures in the tooling and need no declaration.
- `mode` — `extract-only` or `body-draft`.
- `working_kind` (optional) — the resolver's initial working-value kind for the functional-URI transform pipeline (`pdf`, `image`, `audio`, `video`, `html`, `epub`, `zip`, …); falls back to a built-in table for the bundled types when omitted.
- `draft` (optional) — drafting controls beyond `mode`. `draft.strategy` names a general, *type-agnostic* drafter registered by strategy name rather than schema id (e.g. `zip-manifest`), so one drafter serves many schemas whose representation differs only by config; the strategy's config rides alongside it (e.g. `draft.manifest`). Absent a strategy, the drafter is dispatched by schema id. This is the drafting analogue of the origin overlay's `capture` block — overlay-driven, but keyed by media type (the mime schema) rather than by host.
- *(2.1: `artifact_kind` removed.)* Every transport is self-contained (§1.2); a raw archive drafts as an embed manifest (`draft.strategy: zip-manifest` or a sibling, §12.4) and its members are reachable by promotion (§8.1). A schema still declaring the field is ignored (tolerant parsing).
- `address_scheme` — the parameters the schema expects in segment `address:` values.
- `extended_fields` — fields the matching artifact block carries, each with type and optional `semantic_type` tag. The artifact block holds only facts about the **primary-artifact bytes** (e.g. ffprobe codec / dimensions / streams); source metadata from a capturer's enrichment sidecar does NOT live here — see `sidecar`. Vendor/domain identity (what a bundle *is*, beyond its bytes) does NOT live here either — that is knowledge, asserted in the ledger as roster entries and claims citing the record, minted mechanically by a harvest rule keyed on the kept-whole MIME (`ledger.md` §10).
- `sidecar` (optional) — for an artifact type a capturer enriches with a companion metadata sidecar (e.g. a yt-dlp `.info.json`), declares what is lifted and where. `source` names the sidecar (e.g. `ytdlp-info-json`); `ytdlp_keys` lists the info.json keys copied — each into the **origin block** as a flat `ytdlp_<key>` field (§7.2), the mapping guidance the drafter applies. The sidecar is companion metadata staged in `capture/<hash>.<suffix>`, read at draft, then **deleted** — never persisted to `artifacts/` (only the artifact carries the `<hash>` name there). It is *non-primary-source* metadata, so nothing from it goes to the artifact block, the body, or the frontmatter `description`.
- `transport_algos` — additional byte-hash algorithms to compute beyond the primary blake3 `id`.
- `canonical_strategy` (optional) — procedure for computing the record's `canonical` hash. Names a canonicalization-algorithm id and the canonicalization steps the drafter performs before hashing. The canonicalization MAY be scoped to a **content region** — hashing only the article-content text and excluding per-page framing (title, breadcrumb, entry-specific headings) — so two records holding the same content reached by different URLs share a `canonical` and collapse to one record (the duplicate's URL folded into the original). The content-region selector is host-specific and supplied by the origin overlay (not this schema); when it matches nothing the canonicalization falls back to the whole document.
  - **Status — currently disabled (2026-06-28).** The drafter still computes the value, but it is **not persisted**: no record carries `canonical:`, so the cross-URL content-dedup collapse described above is inert. Reason: `blake3-canonical-pdf` hashes only per-page extracted text, so every text-empty (scanned / image) PDF canonicalizes identically and unrelated scans were being silently merged into one record (the duplicate's bytes discarded). The mechanism is re-enabled — restore the persist in `_apply_drafter_result` — once the strategy distinguishes such artifacts (e.g. a byte / rendered-image hash) and `canonical:` earns its keep.
- `normalization.guidance` (optional) — prose guidance for the normalizer.

### 7.2 The origin namespace

An `origin` schema declares an overlay for one source of retrieval.

- `kind: interpretive` — origin overlays are always interpretive (the match cue may be mechanical, but body guidance is consumed by the LLM normalize pass).

An origin overlay's `normalization.guidance` is **body-shaping tactics** — how to render this source's content faithfully — and, with subtypes (`origin/<id>/<subtype>`), it is the home for **per-page-shape** guidance within a host (how a procedure page vs. an index page of the same site normalizes). *(2.0: this guidance role was previously split with composite overlays; the domain-semantic half of composite guidance moved to ledger per-type conventions, the body-shaping half lands here.)*
- `description` — prose framing of the publisher.
- `applies_to.host_pattern` (string, optional) or `applies_to.host_patterns` (list[string], optional) — host pattern(s) the drafter matches against origin URIs (the `web` family).
- `applies_to.include_subdomains` (bool, default false).
- `applies_to.scheme` (string, optional) or `applies_to.schemes` (list[string], optional) — URI scheme(s) the overlay matches, compared case-insensitively against an origin URI's scheme. This is how a **non-web scheme family** (e.g. `imessage:`, a future `urn:` / `s3:`) binds, since such URIs have no meaningful host. An overlay may declare host pattern(s), scheme(s), or both.
- `applies_to.cues` (optional) — non-host cues for the matcher.
- `normalization.guidance` (string) — markdown prose tactics.
- `extended_fields` (optional) — fields beyond the universal `uri:` / `snapshot:`. A capturer's enrichment sidecar populates these — e.g. a yt-dlp capture's `ytdlp_<key>` fields (title, description, uploader, engagement counts, `ytdlp_comments`), declared by the artifact's mime schema `sidecar` section (§7.1) and merged onto the origin block at draft.

The drafter iterates every origin block in the record. For each origin schema, if any origin block's `uri:` matches the schema's host pattern (or another declared cue), the drafter upgrades that origin block's opener from bare `<!--origin-->` to `<!--origin <id>-->` and populates the schema's extended fields. The qualified opener contributes `origin/<id>[/<subtype>]` to the derived classifications view. (*Promotion* is reserved for the container-member operation of §8.1.)

An overlay `id` may also be **producer-declared** rather than `uri:`-matched. A capturer/producer that knows what it ingested stamps the id directly — `<!--origin <id>-->` written with the overlay's extended fields — which is the only way a **uri-less** origin (a dropped-in local file, e.g. an `imessage-export`) binds an overlay, since there is no `uri:` to match. Two mechanisms, both yielding the same stamped block: (a) a **capture sidecar** at ingest carries `origin_schema:` (the overlay id) + `origin_fields:` (its extended fields), consumed by the ingestor; (b) the producer injects **`<meta name="corpus-origin-schema">`** + per-field `<meta name="corpus-origin-<field>">` tags into the captured artifact, which the (mechanical) drafter folds onto the origin block (a repeated field meta collects into a list). A stored `id` from any path is equivalent downstream: it contributes `origin/<id>[/<subtype>]` to the derived classifications view, its overlay's `normalization.guidance` surfaces for the normalizer, and it satisfies an `origin.id` predicate in a ledger harvest rule (`ledger.md` §10) — the producer-declared id is not re-derived from a `uri:`, so it works with none.

Two producer-export origins ride this uri-less, producer-declared path today. **`imessage-export`** binds a self-contained conversation HTML with attachments inlined. **`claude-code-session`** binds a captured Claude Code session — its `<id>.jsonl` transcript plus the sidecar tree of sub-agent transcripts, tool-result payloads, and workflow state — bundled into ONE deterministic zip by `corpus session capture` (§12.8) and carrying the session's identity as structured fields (`session_id`, `host`, `record_count`, …) rather than a synthetic URI. A session's record is a `zip-manifest` whose members are directly-addressed `path=<member>` embeds (the transcript is a transport resolved verbatim, never transcribed), and successive captures of a growing session are distinct records reconciled by continuity-gated supersession (§12.8), not by a stable id.

The universal `origin` overlay declares the fields every origin block carries. `snapshot:` is always present; an origin carries **either** a retrieval `uri:` **or** local-file metadata:

- `uri` (optional) — string or list-of-strings; the URI(s) by which the origin was reached. Present for a *retrieval* origin (a web capture, a synthetic-scheme source like `imessage://`). **Omitted** for a dropped-in local file: the staging path the bytes sat at is unlinked at ingest, so a `file://` path would be a reference dead on arrival — there is nothing to re-fetch.
- `snapshot` — ISO-8601 timestamp of observation (when the corpus saw this origin).
- `filename` / `source_modified` (local-file origins) — the dropped file's basename and its mtime (ISO-8601, `semantic_type: timestamp`, so it aggregates into the `timeline` view). These carry the durable provenance a `file://` path could not. A local-file origin omits `uri:` and carries these instead; an origin with neither a `uri:` nor local-file metadata is malformed.

**Directory layout — namespaced by URI scheme family.** Origin overlays live under `schema/origin/<scheme-family>/<id>.yaml`, grouped by the URI scheme they are retrieved over so each family can carry its own match semantics. The `web` family (http/https) is keyed by host — `origin/web/<host>.yaml`, matched by `applies_to.host_pattern` — while `otherwise/` is the catch-all for un-namespaced schemes and other families (`urn/`, `file/`, `s3/`) get their own sub-namespace and match predicate as a corpus needs them. The universal `origin/origin.yaml` sits at the namespace root and layers into every overlay. The overlay **id is the bare `<id>`** (e.g. `youtube.com`) regardless of sub-namespace, so the `<!--origin youtube.com-->` opener and the `origin/youtube.com` classification are independent of where the file lives. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`; the flat `origin/<id>.yaml` layout is still read for back-compat.

**Operational overlay sections.** Capture and transcription are retrieval concerns of an origin, so their per-host configuration lives on the origin overlay — one host-keyed file describes both *what* a source is and *how* to capture and process it. These sections are corpus-local (the package ships none) and read mechanically by the tooling; declaring them is how the tooling stays generic with **no hardcoded host knowledge**:

- `capture:` — how to retrieve this origin (read at capture time). One overlay serves **both** capture modes: a live URL fetch and a from-save replay of a manual SingleFile save (§12.3.12) resolve the same recipe and run the same `interactions`, so a host's chrome strip and media-surfacing steps are authored once for both.
  - `capturer` — the capturer name: `browser` (Playwright/HTML; the default), `video` (yt-dlp), or a corpus-local capturer. This is the **sole router** for video vs. browser — there is no built-in video-host list. (`corpus capture --video` / `--no-video` override it for a one-off URL.)
  - `transport` — `headless` | `headed` | `cdp` (browser capturer).
  - `fidelity` — `exact` | `balanced` | `lean` (browser capturer): the self-contained-snapshot completeness tier. `exact` is byte-faithful (presentation *is* content); `balanced` (the default) drops redundant font / image / media alternates inlined for self-containment; `lean` additionally prunes style rules with no matching element. The tiers affect only the snapshot **artifact** size — the drafted record is identical across tiers (the drafter reads DOM text/tables, not fonts/CSS) — so fidelity is purely a per-origin retention/faithfulness choice. The resolved tier is stamped into a `corpus-fidelity` snapshot meta tag for provenance. Precedence: `corpus capture --fidelity` › per-host `capture.fidelity` › `origin/origin.yaml` › tooling default (`balanced`).
  - `url_rewrite` — `[{pattern, replacement}]` regex rules applied to the navigation target before fetch; the original URL stays the recorded origin and the rewritten form becomes an alias.
  - `url_equivalent` — declares which URL spellings denote the **same resource**, so the corpus matches an inbound URL to a record (and keeps one origin URI per resource) even when the spelling differs — query noise (`?nested_view=1`, tracking params), a redundant `/page-1` ≡ the bare form, etc. **Identity-only**: it computes a URL's *identity key* and never changes which bytes are fetched (that is `url_rewrite` / `interactions`). Two URLs are equivalent iff their identity keys are equal. Declared as a list of `[{pattern, replacement}]` rules (same shape as `url_rewrite`), or a map `{query: keep|drop, rules: [...], on_rewritten: bool}`. The identity key = the conservative `normalize` (lowercase scheme+host, sort query, drop a plain anchor, …), then — for `query: drop` (default `keep`) — strip the whole query, then apply the regex `rules` in order, then a final delimiter tidy, then fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`); with `on_rewritten: true` the host's `url_rewrite` is applied first so identity is computed from the fetched form rather than the inbound one. The trailing-slash fold is part of the **identity** key only, never of `normalize` — `normalize`'s output is the URL a crawl re-fetches, where the slash can be significant, whereas a comparison key may fold it (so a naive first-page rule like `…/page-1 → \1` need not chase the recorded slashed origin). **Opt-in**: absent the section, identity is exactly `normalize` (string match), so the layer is inert for every host that does not declare it, and host-scoped so a blanket `query: drop` cannot wrongly fold a host where `?page=`/`?id=` matters. Applied at the **capture short-circuit** (re-capturing a known resource is skipped), **crawl frontier dedup** (an equivalent of a visited / captured URL is not re-enqueued), **pagination uri-recording** (an equivalent spelling of an already-recorded constituent page is not appended), and **resolve** of a raw URL to its record. Pairs with — and is independent of — `url_rewrite`.
  - `pagination` — reconcile a work a site splits across `?page=N` / `/page-N` URLs into **one** record (browser capturer only). `true` enables it with auto-detection; a map gives control: `content_selector` (the per-page content region — else a structural page-1-vs-page-2 diff finds it), `next` (`{rel: true}` follows `<link/a rel=next>`, the default; `selector` overrides with a CSS link), `max_pages` (safety cap, default 100), and `expect_count.selector` (an element whose text holds the site-advertised item count, for the completeness check). The capturer walks the pages, captures each via the staging-only path, merges their content regions into page 1's framework — **deduping by element id or a normalized-subtree hash** — and ingests the merged document. **INVARIANT: exactly one artifact and one record result; per-page captures are never content-addressed.** The clean seed is the recorded origin URI; every constituent page URL (bare site form *and* the pinned `url_rewrite` form) is folded in as an origin alias, and a `pagination: {pages, form, posts}` provenance field lands on the origin block (`posts` = the merged content-item count: id-bearing region children when present — forum/CMS posts carry stable ids — else all direct children, so framework nodes don't inflate it). When the merged item count falls short of the advertised count, or `max_pages` is hit, a `pagination-incomplete` `warning` issue is emitted (capture stage) rather than silently shipping a lossy record. Pairs naturally with `url_rewrite` to pin one render form across every page.
  - `ytdlp:` — a mapping merged straight into yt-dlp's options (full passthrough; e.g. `format`, `getcomments`, `impersonate`). Library-owned keys (output path, logger, the resolved cookie file) are forced after the merge and cannot be overridden.
  - `cookies_from_host` — `true` (default) pulls the capture URL's own-origin cookies from a running CDP browser session into yt-dlp; `false` disables; a list adds extra origin scopes. Lets a logged-in session unlock a host's full content.
  - `also_capture:` — `[{role, capturer, …}]` supporting captures run after the primary one; their bytes **enrich the primary record** (e.g. a comments page folded into the record's metadata) rather than forming separate records.
  - `references:` — `[{match, role, capture, cross_host}]` — declares which of a captured page's outbound links are **dependent reference material** (a PDP's product manual, a spec sheet). Each rule's `match` (`selector` / `href_pattern` / `text_pattern` / `rel`; present keys ANDed, rules ORed) selects `<a>` elements in the drafted DOM. **Emission is a draft-stage concern** (the anchor needs the segmented body): each distinct declared link (resolved + normalized, excluding the record's own origin URIs) emits one `reference` context block (§4.3.3.3) on the primary record, with `provenance: auto`, the rule's `role`, and tier 2 (`source_url`). The mechanical drafter writes **no** tier-3 `source_uri` and reads no corpus state: whether the target is itself a record is a read-time derived edge resolved from `source_url` (`derived_views.references` §9.9 / `corpus links --references`), so `draft` stays a pure function of the artifact and the edge tracks the corpus (`captured ⇄ pending`) instead of a stored pointer that rots under removal/supersession (§4.3.3.3). **Fetching** the target is a separate **capture-side** action: `capture: true` (or `corpus capture --with-references`) fetches it **once, at depth 1**, as its own record (content-hash deduped) right after the primary; `capture: false` (default) is surface-only and the deferred `corpus crawl --references` pass fetches pending targets on demand. `cross_host: allow` (the default for references — manuals are off-host) permits reaching declaration matches on other hosts, but **only** matches — never a general cross-host crawl. Distinct from `also_capture`, whose bytes **enrich the primary record** rather than forming separate, referenced records. Absent the section the feature is inert (no hardcoded link knowledge).
  - `relations:` — `[{match, predicate}]` — the sibling of `references:` for **source-declared cross-link structure** (a "related information" rail, sibling-page navigation): the same match grammar selects the links, and draft emits one `relation` context block per distinct target (§4.3.3.5) with `provenance: auto`, the rule's `predicate` as the block subtype, and `target_text`/`target_url`. Relations are edges, not fetch demands — there is no `capture:` key; a relation target enters the corpus only through the ordinary crawl/capture paths. Absent the section, inert.
  - `assembly:` *(2.1)* — config for **pre-ingest bundle assembly** (`corpus assemble`, §12.3.11): repackaging a source's delivered part(s) into ONE indexed container bundle before ordinary ingest, for delivery formats that are transient (an expiring export job), access-hostile (a solid compressed stream), or envelope-less (a loose directory tree an export tool wrote straight to disk). Keys: `merge_parts` (union a multi-part delivery's member trees — the split is delivery, not structure), `conflict` (`error`: a same-path collision across parts with differing bytes aborts; identical bytes dedup), `additions` (an allowlist of declared NON-original files placed at the bundle root, outside the original tree — e.g. an out-of-band export report), `rewrites` (declarative `{from, to}` restructure rules; **empty is the norm** — the original internal structure is NEVER changed except by a rule asserted here), `excludes` (declared filesystem-cruft subtraction — fnmatch patterns; slash-less patterns claim the basename at any depth, slashed ones the full relpath; exclusions are reported, never silent), `level` (the bundle's compression level), `derive` (mechanical origin-field extraction patterns — filename-convention regexes, addition-content regexes, and `from_member_head` regexes over the leading bytes of glob-matched members of a directory source, greatest match winning across members — so every vendor-shaped fact lives in the overlay, none in the engine), `seed_fields` (which derived fields beyond `account`/`job`/`exported_at` ride into the sidecar), and `name_fields` (derived fields whose values join the bundle's filename and archive comment — the job identity where no job id exists). The assembled bundle is staged with a capture sidecar (`origin_schema:` + the derived/declared fields) and enters the pipeline through ordinary ingest; the consumed part archives are recorded as `source_parts` tombstones (filename + byte hash) on the origin block — a directory source, having no delivery envelope, leaves none (member byte-identity is carried per-member by the manifest's embeds). Absent the section, `corpus assemble` refuses the overlay.
- `transcription:` — per-host audio transcription (read at draft time). `enabled: false` skips transcription (an `info` issue, not a `warning`); `adapter` / `base_url` override the global `[corpus.transcription]` backend. Absent the section, the global config applies.
- `canonical:` — `content_selector` scoping the `canonical` hash to the article-content region (§7.1). *(Currently inert — `canonical:` is not persisted; see the §7.1 `canonical_strategy` status note.)*
- `metadata:` — reserved hook to remap/disable how a capturer's enrichment sidecar maps into the record (per host). The mapping itself is **host-agnostic and applied for every yt-dlp capture**, and is **schema-declared**, not hardcoded: the keys lifted from the `.info.json` come from the artifact mime schema's `sidecar.ytdlp_keys` (§7.1). Because the sidecar is *non-primary-source* metadata, every lifted key lands on the **origin block** as a flat `ytdlp_<key>` field (e.g. `ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts) — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when yt-dlp returns it) becomes a `ytdlp_comments` list field; `webpage_url` / `original_url` fold into the origin `uri:` aliases. The sidecar is **draft-time-only enrichment** — staged in `capture/`, consumed at draft, then deleted; it is one-shot (a re-draft after deletion does not re-apply it; the extracted fields already persist on the record). The only content the media drafters write to the body is the **transcript**, derived from the primary artifact's own audio.

### 7.3 The atom namespace

An `atom` schema declares an atomic-axis overlay that may attach to a segment.

- `kind: atomic`
- `description` — prose definition.
- `applies_to.atom` — `text`, `image`, `audio`, or `video`. Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `applies_to.cues` (optional) — heuristic patterns for the normalizer.
- `enables_lossless` (boolean, default `false`) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's other declarations describe what shape the body takes.
- `extended_fields` (optional) — id-specific fields. For lossless-enabling overlays these typically describe address-shape requirements; for envelope-bearing forms (a chat message's `sender`/`timestamp`) they carry the segment's structural envelope, verbatim from the source.
- `normalization.guidance` (string) — markdown prose tactics for rendering the form faithfully.

A segment carries exactly one atomic class id, on the opener line.

**The atom constitution.** Atom overlays declare **form, never meaning**: the shape of a lossless body, the structural envelope of a segment, extraction tactics for a region's faithful rendering. "This text is a table," "this image is a screenshot," "this segment is one chat bubble with this sender and timestamp" are form statements, checkable against the bytes. A subtype whose payload is domain semantics — what the content is *about* — is wrong at this layer; that is a ledger claim over the segment's span (`ledger.md` §6).

### 7.4 The composite namespace *(removed in 2.0)*

*Retired with the classify block (§4.3.1.3).* The `composite` umbrella was the corpus's interpretive classification system — a pre-ledger claims system embedded in the archival layer. Where each part went:

| 1.0 mechanism | 2.0 successor |
|---|---|
| User-defined classification namespaces | Ledger **types and predicates**, under VOCAB discipline (`ledger.md` §8) |
| Asserted classify blocks (record scope) | **Claims** with record evidence (`ledger.md` §5–§6) |
| Section-scope composites | Claims with span evidence (§4.4.3) |
| `classify_when` deterministic membership | **Harvest rules** (`ledger.md` §10) — the same fact base and predicate grammar, evaluated ledger-side over corpus records |
| Mechanical extraction scripts | Harvest-rule `mint` templates over the same fact base |
| Domain-semantic `normalization.guidance` | Per-type authoring conventions (the ledger's `facts/SCHEMA.md` / concept schemas, `ledger.md` §8, §4.4) |
| Body-shaping guidance keyed by page type | The origin overlay (subtypes, §7.2) or an atom overlay (§7.3) |
| `extended_fields` | Claim values and qualifiers |

The fact base and predicate grammar that `classify_when` defined are now specified in the harvest-rule contract (`ledger.md` §10), unchanged in substance: draft-visible facts only (`mime`, `origin.*`, `media.*`), exact-by-default operators, missing-fact-is-false, and body keywords permanently excluded as the canonical false-positive source.

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

Perceptual fingerprinting is **opt-in** and **schema-gated**. A segment carries a `perceptual:` only when a `fingerprint` knob resolves on for its record — fingerprints are a near-duplicate / similarity-search signal, not part of a faithful first-pass draft, so the default is **off** and a record with no `perceptual:` is normal. The knob is a top-level field on a **mime schema** (the per-file-type default) and may be overridden on an **origin overlay** (for records from that source). Values: `false` / absent = off; `true` = on with each atom's *default* algorithm; an algorithm name or a list = on with those algorithms (a list yields a list-valued `perceptual:`). Resolution precedence, most-specific first: `corpus draft --fingerprint` / `--no-fingerprint` › origin overlay › mime schema › off.

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
| `ingest` | blake3 of bytes → `id`; additional algorithms per the mime schema's `transport_algos` → `transport:`; MIME detect → artifact-block opener; emit stub with first origin block from capture context; persist binary in the corpus's binary store. | `<pkg>.ingest@<v>` |
| `promote` | Mint a record for a container member already in the corpus: locate the member by its embed declaration (container id + member address, §2), stream the bytes and blake3-verify against the embed's recorded `transport:` hash → `id`; MIME detect → artifact-block opener; emit stub whose first origin block records the containment lineage **as history** — `uri: corpus://<container-id>?<member-address>`, plus the universal `filename` / `source_modified` from the member's archive metadata when present. The bytes are NOT copied; they remain resolvable through the container (§2). | `<pkg>.promote@<v>` |
| `draft` | Run the mime schema first (it segments the content zone, emits embed blocks, and — when it declares a `canonical_strategy` — sets `canonical`), then the origin overlay's declared emissions (`reference`/`relation` context blocks); drafter-detected issue context blocks emitted. | `<pkg>.draft.<mime-type-id>@<v>` |
| `normalize` | The faithful-form LLM pass: re-segments and shapes the content zone where judged appropriate, authors descriptions and the two editorial fields, surfaces faithfulness issues. | `<model-id>` |

Idempotent re-capture is part of `ingest`. Concrete tooling is implementation-defined.

An origin overlay's `capture.references` (§7.2) drives two mechanical, deterministic actions (§8.2): the **draft** stage emits `provenance: auto` `reference` context blocks for the page's declared dependent links (at tier 2 `source_url`; the intra-corpus edge is resolved at read time, never stored — §4.3.3.3), and the **capture** side, for rules marked `capture: true` (or `corpus capture --with-references`), fetches those targets at depth 1 as their own records after the primary ingest. `capture.relations` (§7.2) drives the same draft-stage emission for declared cross-link structure (`relation` blocks, §4.3.3.5), with no capture side.

A corpus may also specialize the **draft** of its own content with corpus-local drafter code — `<corpus_root>/drafters/*.py`, loaded mechanically before drafting (the draft-stage analogue of the corpus-local capturer in §7.2). Such a drafter claims a record by its origin id (a producer-declared or stamped overlay binding, §7.2) and builds the content zone in place of the generic body draft; the package ships none and knows nothing of any specific format. Implementation-defined — see §12.4.3.

### 8.2 The deterministic / LLM boundary

| Operation | Type | Why |
|---|---|---|
| Hashing, MIME detection, mime schema lookup | deterministic | mechanical |
| Member promotion (byte streaming, hash verify, stub mint) | deterministic | mechanical |
| Mime schema's body draft, artifact-block field extraction, and `canonical` hashing | deterministic | scriptable |
| Origin-host matching | deterministic | mechanical |
| Overlay-declared reference/relation emission (draft) / depth-1 dependent capture (capture) | deterministic | overlay-declared |
| Functional URI evaluation | deterministic | spec mandates |
| Description authoring | LLM | requires understanding |
| Body re-segmentation and shaping under overlay guidance | LLM | requires judgment |
| Issue surfacing | LLM (faithfulness) / drafter (mechanical) | depends on kind |

### 8.3 Re-runs

Every stage is independently re-runnable; re-runs are **scoped**.

- **Re-ingest** — re-encounters bytes that match an existing `id`. Appends a touch identifier; may append to origin blocks.
- **Re-draft (full)** — re-runs the mime schema and the overlay-declared emissions.
- **Re-draft (scoped)** — re-runs only one schema. Refreshes ONLY the blocks/fields declared by that schema.
- **Re-normalize** — re-runs the faithful-form pass.
- **Re-resolve** — bare resolver-cache regeneration.

Each re-run appends a new `touch[]` entry.

### 8.4 Re-stub

`re-stub` is a deliberate reset operation that returns a record to `status: stub`, ready for a fresh draft pass. Everything **derived from a schema decision** is discarded. Everything **tied to the bytes themselves** is preserved.

| What survives | What is reset |
|---|---|
| `id`, `transport` — byte-intrinsic. | `title` and `description` → empty; `canonical`, `perceptual` (record-scope). |
| The artifact block's opener (the MIME) and the origin blocks with their `uri:` history. | The artifact block's body fields, all embed blocks, all sections/segments, all context blocks. |
| `visibility`. | `status` → `stub`; record body's content zone → empty. |
| `touch[]` collapses to its first entry (the original ingest touch) plus the re-stub touch. | |
| The persisted bytes. | |

Re-stub is invoked deliberately — never automatic. Its uses:

- Schema-shape design changes that make existing blocks invalid.
- Records whose accumulated normalize work was wrong.
- Migration from a deprecated schema generation.

Re-stub appends a `touch[]` entry of the form `<pkg>.re-stub@<v>`. It is also the natural translation point for migrating records from prior schema generations: a re-stub accepts older frontmatter on input and always writes a current-spec-shaped stub on output, preserving byte-intrinsic state and discarding everything that depended on the prior schema shape.

### 8.5 The normalization queue

`normalize` (§8.1) is the one stage the corpus tooling does not itself run — it is interpretive, performed by an external **loop session** (a scheduled agent). The tooling provides only the **request/claim contract** that lets any actor ask for a (re-)normalization pass and await its result; it never invokes a normalizer.

**The queue never writes records.** Record `status`, `touch[]`, and body are authored solely by `ingest`, `draft`, and the normalizer (§8.1). Queue state is **external to the record** and untracked — regenerable orchestration, like `capture/` and `cache/` (§12.1). Queue operations are **read-only on records**: they may read a record (to gate on lint, or report a result) but never mutate it. One writer per concern — the normalizer owns `status`; the queue owns only its own entries.

**Requests are status-independent and repeatable.** A record may be enqueued at any status — `draft` for a first pass, or `normalized` for a *refinement* when a new overlay matches it or its guidance improves (re-normalize, §8.3). `normalized` is not terminal; each completed pass appends a `<model-id>` touch. Enqueue never inspects `status`.

A queue entry moves `idle → requested → claimed → idle`, recording the last pass's outcome:

| Verb | Effect | Writes record? |
|---|---|---|
| `enqueue <id>` | request a (re-)normalization pass; idempotent — a request arriving while one is pending joins it. | no |
| `drain` | atomically **claim** the next pending entry and emit its `id`; an empty queue is a non-error empty result — the loop's stop signal. A blocking variant long-polls for the next claim instead of reporting empty (the *standing* mode below). Reclaims a claim whose lease has lapsed (a dead session). | no |
| `finalize <id>` | close the claimed pass **complete** — gated on the record being `status: normalized` and linting clean; refuses (non-zero) on a blocking finding, so a dirty pass is never reported done. | reads only |
| `release <id> [--failed]` | return a claim — bare re-queues it; `--failed` records a failed outcome. | no |
| `await <id>` | block until the requested pass reaches a terminal outcome; success/failure by exit status. | reads only |

**Done** means the normalizer set `status: normalized` *and* the record lints clean — `finalize` enforces both halves.

**Drivable by an external loop, in either of two modes.** The claim is atomic (concurrent loops never double-claim) and every verb is non-interactive with a meaningful exit code and machine-readable output, so an agent loop runs `drain` → normalize the emitted id in-session → `finalize` (or `release --failed`) each iteration. A **scheduled** loop (e.g. cron) drains until the queue reports empty, then waits for the next tick — simple, but the loop session itself does the polling, waking even when there is no work. A **standing** loop instead blocks on the `drain` long-poll, which waits in the tooling until a request is claimable and returns it the instant one appears — so the (costly) loop session is engaged only when there is genuinely work. Both drive the same atomic claim; the long-poll is an ergonomic over it, not a distinct contract, and the same loop body serves either. The normalizer reads the record's applicable overlays' `normalization.guidance` (mime §7.1, origin §7.2, atom §7.3); because form knowledge rides in overlays, one generic loop serves every source — and demand flows down from the ledger, whose citation discipline requires `normalized` records (`ledger.md` §6.3): the ledger contributes by enqueuing, never by supplying a normalizer.

**Entry lifecycle and pruning.** A request and its claim are transient — each transition supersedes the prior state — but a settled pass records its **outcome** so a requester's `await` can resolve it, and so a *re-normalization* is distinguishable from an earlier pass (which `status` alone cannot tell apart, since a re-normalized record is still `normalized`). An outcome is **coordination state, not history**: the record's own `status` and `touch[]` are the durable trail. Because a requester may `await` after a loop iteration ends, an outcome is **never discarded at loop end** — that would race the awaiter, dropping it to the `status` fallback. Outcomes are instead garbage-collected by **age**: a settled outcome past a grace window (plus any orphaned scratch) is prunable, never a live request or claim — so the queue's footprint stays bounded without dropping an outcome a requester still needs. The grace window and the prune trigger are operational policy, not part of the contract.

---

## 9. Derived views

Cross-cutting aggregates over a record's frontmatter and body blocks, computed on demand. None are persisted.

### 9.1 The `classifications` view

Computed by walking the metadata zone — structural-derived only (§4.4.6):

```
classifications := []
on <!--artifact <mime-type>-->:
  classifications += ["mime/<mime-type>"]
on <!--origin <id>[/<subtype>]-->:
  if id present:
    classifications += ["origin/<id>[/<subtype>]"]
dedupe preserving body order
```

Embed blocks and context blocks are NOT included. A record carrying an artifact block and one qualified origin block yields:

```
[
  "mime/<mime-type>",
  "origin/<origin-id>"
]
```

*(2.0: the classify-block rows are gone with the composite namespace. "What does this record document" is a ledger query — the concepts rostering the record, the claims citing it (`ath ledger worklist`, `ledger.md` §13), and the coverage ledger (`ledger.md` §9).)*

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

The text tokenizer and the image constants are an implementation choice (§12.13), not part of the contract — what the spec fixes is the **shape**: three cumulative tiers, ordered `body ≤ blocks ≤ full`. Like every §9 view it is computed on demand and never persisted.

### 9.7 The `concepts` view *(removed in 2.0)*

*Retired with the `concept` namespace (§4.3.3.4).* "Which records invoke this thing" is a ledger query: the concept's artifact roster and its claims' evidence URIs point at the records, and coverage (`ledger.md` §9) is the record-first direction.

### 9.8 How views are computed

A derived-view walker:

1. Loads the record's frontmatter and parses the body's three zones.
2. For each matched block, loads the corresponding schema chain.
3. Walks blocks, collecting values per view rules.
4. Deduplicates or sorts per view.
5. Returns the result.

Views are computed at query time.

### 9.9 The `references` view

The `reference`-namespace projection of the context view (§4.3.3.3) — the sibling of the `issues` view (§9.2), and the pattern the `relation` namespace (§4.3.3.5) follows. Each entry carries the stored ladder (`attribution_text`, `source_url`), the anchor (`address`, `quote`, `occurrence`), `provenance`, `role`, and the **derived** tier-3 resolution (`resolved_uri`/`captured`, computed against the URI index at read time — §4.4.5). The resolved edge is directional toward the depended-on record; the reverse ("records that reference *this* one") is a corpus-wide read derivable from these edges but, like cross-record content addressing (§11), the corpus-wide index is not specified here. Computed on demand, never persisted.

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

- **Automatic PDF text / OCR extraction.** Every PDF drafts **uniformly** to per-page body-empty `image` segments addressed `page=<N>` — the image-of-document shape (§7.1), sectionless — regardless of whether it is born-digital or scanned. The drafter makes **no** born-digital-vs-scanned determination and extracts **no** text. Deciding a page's shape, pulling its embedded text layer, mapping text to regions, transcribing a scan into `text/ocr` segments (§4.3.2), and outline-driven sectioning are all **normalizer (agent) passes**, supported by the resolver's PDF introspection ops (`page=<N>&text`, `page=<N>&words`, `page=<N>&probe`, `probe`, `outline`; §6.2). What remains deferred is an *automatic* (non-agent) text-or-OCR pass.
- **Cross-record content addressing** via `<!--embed--> transport` — the shape leaves room for a corpus-wide `transport → (record_id, address)` index but the index itself is not specified. (Building it requires reconciling the `<algo>:<hex>` embed `transport` encoding with the bare-hex record `id` — strip the prefix and confirm `algo == blake3` before matching.)
- **Range-aware navigation** for content the resolver doesn't materialize.
- **`page=<N>-<M>` ranges** and other open transforms beyond §6.2.
- **Whole-corpus build tooling** — single-record export is in scope; bulk operations are not.
- **Export to non-markdown formats.**
- **Additional semantic types** beyond the closed seven.
- **Recursive dependent capture.** `capture.references` (§7.2) fetches declared references at **depth 1** only; following a grabbed reference's own references — and any general multi-hop crawl — remains `corpus crawl`'s job, not the capture-alongside path.

---

# Part II — Implementation guide (non-normative)

## 12. Implementation guide

This part describes how the reference pipeline — the `corpus` tooling shipped by the orchestrator repo — produces records that conform to Part I: which passes run in what order, where files land on disk, detection and dedup strategy, queue mechanics, and maintenance. Part I says what each record carries; this part says how the pipeline gets there. Nothing here is mandated: an implementation is free to make different choices as long as it honors the Part I contracts, and where the two disagree, Part I wins and this part gets corrected.

### 12.1 On-disk layout and sharding

A typical filesystem-backed corpus:

```
corpus-<name>/
├── README.md                optional
├── records/                 tracked: record markdown files
│   └── <id[:2]>/<id>.md
├── schema/                  tracked: mime / origin / atom / context
├── artifacts/               UNTRACKED: raw-bytes cache
│   └── <id[:2]>/<id>.<ext>
├── capture/                 UNTRACKED: in-progress capture staging
├── cache/                   UNTRACKED: resolver-output cache
│   └── <urihash[:2]>/<urihash>.<ext>
├── queue/                   UNTRACKED: normalization request/claim state (§8.5)
├── export/                  UNTRACKED: regenerable export bundles (§10)
└── .gitignore               lists the untracked directories
```

- **`records/` and `schema/` are tracked** in version control; the markdown records are the source of truth.
- **`artifacts/` is the binary cache and is never tracked** — a corpus's `.gitignore` lists it. The cache is regenerable from blake3 plus capture provenance: destroyable and rebuildable at any time. The contract is only "given a blake3, this corpus can produce the bytes" (§2); a local filesystem shard, an object store, an S3-compatible bucket, or a content-addressed store all satisfy it. Consumers should not hard-code the path scheme — they should ask the corpus how to locate `<blake3>`. A **promoted** record (§8.1) has no `artifacts/` entry at all: its bytes materialize through its container via the member index (§12.9), which is just another way of satisfying the same contract.
- **Sharding is one level deep, by the first two hex characters of the leading hash**, with the same depth for `records/`, `artifacts/`, and `cache/`. That gives 256 buckets: at ~10k records the average bucket holds ~40 entries; at 100k, ~400. Deeper trees are a layout choice, not a contract (§12.15). The full hash stays in the filename, so a copy outside its shard directory still names itself fully — useful for moves, backups, and ad-hoc inspection.
- **Capture staging** lives under `capture/`: failed or abandoned captures sit there without consuming corpus identity space, and ingest unlinks a staged capture on success.

### 12.2 Schema directory layout

The namespaces of §3 are conventionally laid out as:

```
schema/<namespace>/<namespace>.yaml              namespace universal
schema/<namespace>/<axis>/<axis>.yaml            axis common guidance (mime and atom)
schema/<namespace>/<axis>/<axis>_<id>.yaml       specific declaration
```

The **underscore-flattened** subtype convention (`text_html.yaml` inside `text/`, rather than `html.yaml`) keeps filenames self-describing.

Annotation overlays use the namespace pattern under `schema/context/` — `context/<ns>/<ns>.yaml` layering under `context/<ns>/<id>.yaml` (the bundled `issue` overlays live here).

Inside `origin/`, overlays nest by **URI scheme family** (§7.2): `schema/origin/web/<host>.yaml` for http(s) sources (host-matched), `schema/origin/otherwise/<id>.yaml` as the catch-all, and other families (`urn/`, `file/`, `s3/`) as a corpus needs them, with the namespace universal at `schema/origin/origin.yaml`. The overlay id is the bare `<id>` regardless of sub-namespace; the flat `schema/origin/<id>.yaml` form is still read for back-compat. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`.

### 12.3 Capture

A capture takes a target — URL, filesystem path, manual upload — and produces a record plus its binary in the content-addressed store. The pipeline is content-addressed end-to-end: identity is the hash of the bytes.

#### 12.3.1 Fetch and capturer routing

**Routing is overlay-driven — no hardcoded host knowledge.** The capturer is chosen by the origin overlay's `capture.capturer:` field (`browser` — Playwright/HTML, the default; `video` — yt-dlp; or a corpus-local capturer name); `corpus capture --video` / `--no-video` are one-off overrides. There is no built-in video-host list: a host that should go to yt-dlp declares `capturer: video` in its overlay, so an undeclared video URL captures as HTML unless `--video` is passed.

- **HTTP/HTTPS URL** — fetched with redirect-following enabled. The original requested URL and the final-after-redirect URL both land on the record's first origin block (`uri:` list).
- **Filesystem path** — copied from staging, which is unlinked at ingest; the origin block is uri-less and carries `filename` + `source_modified` instead (§7.2).
- **Manual upload** — the operator supplies the bytes and any origin URI.

Inline media a transport merely *references* (images in an HTML page, etc.) are not separate records: the body drafter emits an embed block per asset (deduped by `transport` byte-hash) plus an `image`/`audio`/`video` positioning segment in the content zone (§4.3.1.4) — never an intra-corpus wikilink (those are reserved for cross-*artifact* references, §4.3.2.2). A raw archive is no exception (2.1): it drafts as an embed manifest, and a member becomes its own record only by deliberate promotion (§8.1). Hyperlinks to *other* resources are reconciled to intra-corpus references during cross-reference resolution (§12.4.7).

**Corpus-local capturers.** A corpus can ship its own capturer code under `<corpus_root>/capturers/*.py`. `corpus.local_code.load_corpus_modules(corpus_root, subdir)` imports these by path (`importlib`, not `sys.path`, so distinct corpora cannot collide on a module name), registering each module in `sys.modules` before exec, idempotently per `(root, subdir)`, with per-file failures logged and skipped. Trust boundary: this executes Python from the corpus root — the corpus owner's own code, which is the point of the tier — but a serving layer never captures or drafts, so merely fronting a corpus never runs it.

#### 12.3.2 MIME detection

MIME detection selects the **mime schema** that drives the rest of the pipeline (`transport_algos`, address scheme, drafter):

1. **Magic-byte sniffing** — the primary path (`mime.detect`). Inspect the leading bytes; refine ambiguous container magic by form-type and extension (a RIFF prefix → webp/wav/avi by its offset-8 form-type; an ISOBMFF `.m4b` → `audio/mp4`, not `video/mp4`, so it routes to transcription rather than the video keyframe path). A `PK\x03\x04` zip is refined by its members (`_refine_zip`): universal formats (OOXML / EPUB / JAR) match fixed internal paths baked into the tooling, while a corpus's *own* zip-shaped types (a diagnostics export, a backup bundle) match their schema-declared shape signatures (`applies_to.zip_members` / `zip_member_patterns`, §7.1) when a `corpus_root` is in scope — vendor-specific recognition lives in the overlay, not the package, and an unrecognized zip stays `application/zip`. An mbox opens with a `From ` separator at offset 0. A single email message (`message/rfc822`, typically a promoted mbox `msg=<N>`) has no magic number, so it is recognized by **header shape** — a distinctively-email header prefix (`Return-Path:` / `Received:` / `X-GM-THRID` / …), or, after the extension hint, two consecutive header-shaped lines — with the mbox `From ` separator always winning first (an mbox opens with the separator, an eml never does).
2. **Extension hint** — disambiguates where magic is generic, and names the type for extensionless or schema-id-from-filename cases.
3. **`unknown` sentinel** — when both fail. Record the gap; the artifact is still valid, it just gets no format-specific drafting.

The detected MIME becomes the **artifact block's opener argument**, which is authoritative — there is no frontmatter media-type field (§4.3.1.1).

#### 12.3.3 Hashing

The hash families of §2 / §4.2.1 land at different stages (§7.6 encoding):

- **blake3 of the bytes** — always, at ingest. The artifact's `id` (bare hex): identity and filename stem.
- **`transport_algos`** — additional byte-level algorithms the mime schema declares (e.g. `sha256` for interoperability), computed at ingest into `transport:` as `<algo>:<hex>`. The primary blake3 is on `id` and is not duplicated here.
- **`canonical`** — a content-canonical hash computed at **draft** by the mime schema's `canonical_strategy` (`blake3-canonical-{pdf,html,image,epub}`). Currently computed but **not persisted** (see the §7.1 status note); without it `records.content_key()` returns `None` and `find_content_duplicate` short-circuits, so the cross-URL content-dedup fold is inert.
- **`perceptual`** — atom fingerprints (image pHash, text simhash, …), **opt-in and schema-gated**, computed at draft only when the fingerprint knob resolves on (§12.4.4); default off. Per-segment on multi-atom records, record-scope on single-atom ones (§7.7).

There is no frontmatter `hashes` field and no mandatory per-MIME perceptual hash. A MIME with no canonical strategy and no fingerprint knob is blake3-`id`-only, and that record is normal.

#### 12.3.4 The stub record

Ingest emits the stub record (§4.1). The frontmatter carries only the bytes-identity header — `id`, `transport:` (any `transport_algos`), `status: stub`, `touch: [<pkg>.ingest@<v>]`, and the two editorial fields `title: ''` / `description: ''`, empty until the normalizer authors them (§4.2.1). Everything else lands in body blocks:

- The **artifact block**, its body holding the format-intrinsic extended fields the mime schema declares, named bare (`title`/`author`/`page_count`, not `pdf_title`; §4.3.1.1). Sources: PDF info dict, EXIF, ID3, HTML `<meta>`, OPF Dublin Core, ffprobe streams.
- The first **origin block** from capture context — `uri:` + `snapshot:`, or the uri-less local-file form (§7.2). A **SingleFile save** is a third shape: a manual save carries a self-describing banner comment in its first bytes (`Page saved with SingleFile` + `url:` + `saved date:`), so a save dropped straight into `capture/` and ingested (no capture step) seeds a *retrieval* origin from the banner — `uri:` = the banner URL, `snapshot:` = the saved date parsed to ISO-8601 with its numeric offset **preserved** (not converted to UTC; the parenthesized zone name ignored) — instead of the uri-less local-file form. An explicit capture-sidecar `source_url` still wins; a banner-less or non-HTML file is unchanged. The banner is scanned only within a bounded head.

No `content_type`, `hashes`, `classifications`, `tags`, or `uris`/`capture_dates` frontmatter — none of those exist in this model. The content zone is empty; draft fills it.

#### 12.3.5 Dedup, re-capture, and capture provenance

Ingest looks the artifact up by `id` against the existing corpus:

- **Match** — the bytes are already in the corpus. Fold the new capture into the existing record's origin blocks: append the inbound URL to a matching origin's `uri:` list when it aliases one (via known shortlink/redirect + `url_equivalent` rules), or emit a new origin block when it is a genuinely separate source (§5.2). Never a new record.
- **No match** — a new artifact. Write the record under `records/` and the binary under `artifacts/`.

Dedup is the natural side effect of content addressing. Two pre-download stages catch a duplicate *before* the (expensive, especially video) fetch: the cheap string-identity `find_by_uri` short-circuit, and the redirect-aware short-link resolution (§12.3.9).

Capture provenance lives in **origin blocks** (§4.3.1.2), never frontmatter: one block per distinct source, its `uri:` list collecting the spellings that resolve to it (request URL, final-after-redirect URL, shortlink, mirror), deduped by identity key (§12.3.9), plus the `snapshot:` timestamp. The pipeline does **not** record per-event metadata (which URI was used at which moment, the redirect chain, the HTTP method); recovering a particular (uri, time) capture package is a job for an out-of-band capture log, not the record.

#### 12.3.6 Browser capture recipes (per-host interactions and fidelity)

A web capture renders the page in a headless browser, drives it to surface all displayable media, then writes a self-contained SingleFile snapshot (CSS/fonts/images inlined as `data:` URIs). What the browser does before the snapshot is an ordered list of **interactions**, declared in the matching origin overlay's `capture.interactions:` (§7.2); absent a recipe, a conservative default of `scroll: full` → `expand: all` → `scroll: full` runs. Each step is a single-key mapping; steps are best-effort (a bad selector never aborts a capture):

- `scroll: full` — scroll top-to-bottom, hydrating lazy-loaded / below-the-fold media.
- `expand: all` (or `details`) — open `<details>` and click `[aria-expanded="false"]` accordions/tabs.
- `click: {selector, repeat, delay_ms}` — advance carousels / load-more buttons.
- `wait: {ms}` or `wait: {selector, timeout_ms}` — settle async loads.
- `hover: {selector}` — trigger hover-reveal media.
- `remove: ['#header', 'footer', '.ad']` — delete matching elements from the live DOM before the snapshot. **This is where page chrome is removed.** The HTML drafter (§12.4.1) is deliberately mechanical and never guesses what is chrome, so stripping nav/header/footer/ads/cookie-notices is a per-host decision made here, where the site's real structure is known. Removing chrome at capture also keeps its images from being inlined and embedded. (Link-bearing navigation the crawl needs — breadcrumbs, related-item rails — is preserved by *not* listing it here.)
- `eval: "<javascript>"` — escape hatch for site-specific DOM surgery (fetch-and-inject an AJAX-on-click tab, promote a `data-*` high-res image URL into `src` so it gets inlined). An async-function string is awaited before the snapshot.

The snapshot's **fidelity** is a per-host tier (`capture.fidelity:` — `exact` | `balanced` | `lean`, default `balanced`; `FIDELITY_PRESETS` in `capture/__init__.py`). On asset-heavy SPAs the self-contained inlining (web/icon fonts in redundant formats, app icon-sprite SVGs) is re-inlined into every page, dwarfs the content, and defeats content-addressed dedup (each page's whole-file hash differs). `balanced` drops redundant font/image/media alternates (≈−76%, no rendering risk); `lean` also prunes unused CSS (≈−91%); `exact` keeps everything for presentation-critical sites. The tiers touch only the gitignored `artifacts/` — the mechanical drafter reads DOM text/tables, so the drafted record is byte-identical across tiers. The resolved tier is stamped into a `corpus-fidelity` meta tag; `corpus capture --fidelity` / `corpus crawl --fidelity` override per run.

Capture config (`capturer`, `transport`, `fidelity`, `interactions`, `viewport`) lives on the per-host origin overlay under its `capture:` section (§7.2); global defaults can sit on the universal `origin.yaml`. `scaffold.py`'s example overlay shows the full annotated shape.

#### 12.3.7 The video (yt-dlp) pathway

The **video capturer** drives yt-dlp. Its options are declared in `capture.ytdlp:` and merged straight into `YoutubeDL` (full passthrough — `format`, `getcomments`, `impersonate`, …); the library forces `outtmpl` / `logger` / the resolved cookie file after the merge so an overlay can't break output, logging, or auth. `capture.cookies_from_host` (default `true`) pulls the capture URL's own-origin cookies from a running CDP browser (`--remote-debugging-port=9222`) into yt-dlp, so a logged-in session unlocks a host's full content (e.g. the full format ladder rather than a degraded anonymous one). yt-dlp writes a `.info.json` enrichment sidecar (post metadata + comments); ingest renames it to `capture/<hash>.info.json` and leaves it in staging — it is draft-time-only enrichment, never persisted to `artifacts/`.

**Sidecar → origin block (draft time), then deleted.** The `.info.json` is *non-primary-source* metadata, so `draft/_sidecar.py` lifts every declared key into the **origin block** as a flat `ytdlp_<key>` field (`ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts, …) via `records.merge_origin_fields` — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when returned) becomes a `ytdlp_comments` list field; `webpage_url`/`original_url` fold into the origin `uri:` aliases. The lifted key set is schema-declared — `sidecar.ytdlp_keys` on the video/audio mime schema (§7.1); the drafter is mechanical, not hardcoded. One datum is *structural* rather than flat: **`chapters[]`** (the uploader's outline). A video that ships chapter markers is sectioned by them — each chapter title becomes a section `entry` and the chapter bounds become the section time-ranges, in preference to the default speaker-run sectioning. Chapters are consumed into section structure, never copied to a `ytdlp_*` field; a section's `entry`/address is metadata structure, not body content, so this respects the same primary-artifact boundary. The only body content a media drafter writes is the **transcript**, derived from the primary artifact's own audio.

**Title is normalizer-owned.** The frontmatter `title` (like `description`) stays empty through draft; the normalizer authors it from the block-level candidates — the artifact block's bare `title`, or an origin `ytdlp_title` (the `ytdlp_` prefix survives because the origin opener names the source record, not the tool; §4.2.1). A media drafter's title candidate routes to the origin's `ytdlp_title` (an A/V artifact block carries no `title`); for display, `records.title_for` reads the frontmatter `title`, falling back to the artifact `title`, then `ytdlp_title`. After a successful draft, `_cli/draft._cleanup_enrichment` deletes the sidecar; enrichment is one-shot (re-capture to restore — the extracted fields already persist on the record).

**Per-host transcription (draft time).** The audio/video drafters resolve the record's origin host and read the overlay's `transcription:` section (`draft/_hostcfg.py`): absent → the global `[corpus.transcription]` adapter; `enabled: false` → skip (an `info` issue, not a `warning`); `adapter`/`base_url` → a per-host backend that overrides the global even when the corpus default is `noop`.

#### 12.3.8 Pagination reconciliation

A paginated work — a thread / multi-page article / gallery a site splits across `?page=N` / `/page-N` URLs — is **one logical artifact**. The overlay's `capture.pagination` knob (§7.2; browser capturer only; `capture/pagination.py` + `_reconcile_pagination`) walks the pages and ingests a single merged record instead of capturing page 1 only or fragmenting the work into N content-addressed records. Both `corpus capture` and `corpus crawl` route through `capture_and_ingest`, so the branch lives there, after the dedup short-circuit:

1. **Walk + stage.** Each page is fetched through the staging-only `capture()` path (so its `url_rewrite` / `interactions` / chrome-strip / fidelity all apply per page), its HTML read into memory, and its staging file unlinked immediately — `_sanitize_filename` drops the query string, so `?page=N` pages would otherwise collide on one staging name, and per-page bytes must never be content-addressed. The next page is found by `<link/a rel=next>` (the `<link>` survives the chrome strip — it lives in `<head>`) or a `next.selector` override; the walk stops at no-next, a repeat URL, or `max_pages` (flagged).
2. **Merge.** Page 1 is the framework. The content region is the declared `content_selector`, else the host's `canonical.content_selector`, else a structural diff of page 1 vs page 2 (`detect_region`: descend while exactly one matched-identity child differs; the container whose children then diverge is the region). Each later page's content children are appended into page 1's region, **deduped by element id or a normalized-subtree hash** (so a repeated quoted-OP / threaded post isn't double-counted); a page adding zero new children stops the walk.
3. **Ingest once.** The merged HTML is written to one staging file and ingested — the sole content-addressed artifact + record. A single page (no next link) skips the round-trip and ingests the original snapshot bytes verbatim, so its id is byte-identical to a non-paginated capture (and no pagination provenance is attached).
4. **Provenance.** The clean seed is the recorded origin URI; every constituent page URL — both the bare site form (what a crawl discovers) and the pinned `url_rewrite` form — is folded in via `records.add_origin_uri_alias`, plus a `pagination: {pages, form, posts}` field via `records.merge_origin_fields` (`posts` is the id-aware item count — `_count_items` counts id-bearing region children when any are present, so framework `div`s inside the region don't inflate it; else all children). When the merged count falls short of an advertised `expect_count.selector` value, or `max_pages` was hit, a `pagination-incomplete` `warning` issue (capture-stage detector `corpus.capture`) is emitted rather than silently shipping a lossy record.

**Crawl interaction.** Recording every constituent URL as an alias makes the dedup short-circuit fire when a crawl later discovers `/page-N`, resolving to the merged record instead of re-capturing. `crawl._expand` additionally drops any link already in the expanding record's own origin URIs, keeping those pages out of the frontier (genuine content links — post permalinks, cross-thread — are kept).

#### 12.3.9 URL equivalence and redirect-aware short-link dedup

A record's origin URI list should hold **one URI per distinct resource**, and an inbound URL should match a record whenever it denotes the same resource, even when the spelling differs (query noise, `/page-1` ≡ bare). The per-host `capture.url_equivalent` overlay section (§7.2) declares this; the tooling reduces every URL to an **identity key** and compares keys instead of normalized strings.

- **The primitive** is `urls.identity_key(url, equivalent, *, url_rewrite)` (pure, stdlib-only). `urls.normalize_equivalence` coerces the overlay value to a canonical config; the key is `normalize` → (if `on_rewritten`) apply `url_rewrite` first → (if `query: drop`) strip the query → apply the `rules` in order (via the shared `urls.apply_rewrite_rules`) → tidy a dangling delimiter → fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`). With no config it returns exactly `normalize(url)`, so the layer is inert (opt-in) for any host that does not declare it. The trailing-slash fold is in `identity_key`, **not** `normalize`, on purpose: `normalize`'s output is the URL `crawl._expand` stores and re-fetches (a server may distinguish `/a/b` from `/a/b/`), so the fetched form keeps its slash while the comparison key folds it.
- **Identity ≠ fetch.** The identity key is a comparison key only. Crawl still stores the fetchable normalized URL in its frontier/visited; only the dedup *comparison* uses identity keys. Equivalence must never decide which bytes are fetched (that is `url_rewrite` / `interactions`).
- **The recipe-aware wrapper** `recipes.identity_key_for_url(corpus_root, url)` resolves the host's `capture` recipe once and passes its `url_equivalent` + `url_rewrite` to `identity_key`; single-URL sites (`records.find_by_uri`) call it directly, while bulk sites (`records.build_uri_index`, `crawl._expand`) memoize the recipe by host.
- **The four identity sites** all key by `identity_key`: `build_uri_index`/`find_by_uri` (capture short-circuit + raw-URL resolve), `crawl._expand` (frontier dedup, folding in the own-URI exclusion), `_reconcile_pagination` (within-walk seen-set + constituent-alias recording), and `records.add_origin_uri_alias(post, alias, *, corpus_root=)` — which, given `corpus_root`, skips an alias whose identity key matches an existing origin URI, keeping origin blocks minimal. Where a host declares the page-form equivalence, it supersedes pagination's bare+pinned dual-alias recording — a fragment-only pin (`#flat`) collapses to the bare form, while a genuinely path-changing `url_rewrite` still records both.

`identity_key` canonicalizes a URL *string* and never touches the network, so an **opaque short link** (`https://vt.tiktok.com/XXXX/`) keys differently from the canonical it 301s to. The redirect-resolution layer closes that gap by following the redirect chain to the final URL **without downloading the artifact**:

- **The primitive** is `redirects.resolve_final_url(url)` (pure stdlib): a per-hop HEAD (falling back to a body-less GET on 405/501) follows `Location` headers up to `MAX_HOPS`, never reading a response body — so even when the final URL serves a multi-megabyte video, the probe stays cheap. Redirect loops, hop-cap, non-web `Location`s, and any network/parse failure all return the input unchanged: a probe never breaks the caller, it only improves dedup when it succeeds. `redirects.is_probably_short_link(url)` is a conservative gate (known shortener hosts, `vt.`/`vm.` subdomains, or a single short opaque path segment) so a normal canonical URL never pays the network round-trip.
- **The recipe-aware wrapper** `recipes.resolve_identity_for_url(corpus_root, url)` returns `(final_url, identity_key)`: it follows redirects only when the URL looks like a short link, then computes the identity key from the **final** URL — so the destination host's `url_equivalent` strips the volatile query the canonical resolves with, and a short link whose apex differs from its destination (`youtu.be` → `youtube.com`) picks up the destination's equivalence rules.
- **Capture short-circuit (second stage).** `capture_and_ingest` keeps the cheap string-identity `find_by_uri` first; on a miss, `_redirect_dedup` runs the redirect-aware resolution and re-checks — catching a fresh short link to an already-captured canonical **before** the download, and folding the short link into the matched record's origin URI list as an alias. `--force` skips both stages, and the short-link heuristic keeps the probe off the hot path.
- **`corpus check <url>`** (`_cli/check.py`) is the read-only surface: the same resolution (canonicalize + overlay recipe + redirect-follow), then `find_by_uri`, reporting the matching record hash + path or "not captured". It never captures, ingests, downloads, or writes. Script contract: exit `0` already captured, `1` not captured, `2` usage error, `3` resolution error; `--json` emits `{url, resolved_url, identity_key, redirected, captured, record, path}`; `--no-follow-redirects` does a string-identity-only check (offline / fast).

#### 12.3.10 Dependent references (`capture.references`)

A page's most relevant outbound links are part of the capture itself — a product-detail page's manual or spec sheet far more than the other hundred links on the page. The per-host `capture.references` overlay section (§7.2) declares which links those are; the tooling emits a `reference` context block (§4.3.3.3) for each and, opt-in, fetches it depth-1 as its own record. The home is one module, `corpus.references` — *declare, match, emit* — with the *fetch* delegating to the existing capture/crawl machinery. Opt-in throughout: no rules → entirely inert.

- **The rules** (`references.parse_rules` → `ReferenceRule`): a list of `{match, role, capture, cross_host}`. A rule's `match` keys (`selector` CSS, `href_pattern`/`text_pattern` regex on the resolved href / anchor text, `rel` token) are ANDed; rules are ORed. `role` (corpus-local label — `manual`, `spec-sheet`) rides onto the emitted reference; `capture: true` opts the target into the depth-1 grab (default false = annotate only); `cross_host: allow` (the default — manuals are off-host) lets a match reach another host, `same` host-restricts it. Parse-tolerant: a non-mapping entry, a rule with no match key, or a bad `cross_host` is skipped, never fatal.
- **Matching** (`references.match` / `matches_for_record`): parse the DOM, scope candidate anchors by `selector` (else all `<a href>`), apply the AND filters, resolve relatives against the base URL, normalize, drop non-crawlable hrefs (`urls.is_crawlable_href` — the same filter `links`/`crawl` use), enforce `cross_host: same`, and dedupe by URL (DOM order, first rule wins for role/capture). `matches_for_record` applies the host's rules against the record's primary origin URI and excludes self-links. Shared by draft emission, `corpus links --references`, and the grab.
- **Emission is draft-stage** (`references.emit_overlay_references`, called from the draft core right after the per-host canonical content-scoping). Each match emits one `<!--context reference-->` with `provenance: auto`, the rule's `role`, tier-1 `attribution_text` (the link text), and tier-2 `source_url` (the resolved href). It stops at tier 2: the mechanical drafter writes **no** tier-3 `source_uri` and reads **no** corpus state, keeping `draft` a pure function of the artifact (§4.3.3.3). Whether `source_url` is itself a record is a read-time derived edge: `derived_views.references` (§9.9) resolves it against the URI index and surfaces `captured`/`resolved_uri`, so the edge self-heals (`captured ⇄ pending`) under capture/removal/supersession. Idempotent for free: `draft` runs only on a clean stub and `redraft` re-stubs first, so emission only ever appends. **Known gap:** emission is HTML-only and *record-scoped* in the current implementation — no segment anchor is written, because the declared link usually sits in un-segmented chrome and a brittle DOM→segment map would mis-pin it. §4.3.3.3 specifies a segment-pinned anchor (`address:`/`quote:`); closing this gap is an open item (§12.15).
- **The depth-1 grab** (`references.fetch_references`): `select_for_capture(matches, force=)` picks targets — `force=True` (`--with-references`) all, `force=False` (`--no-references`) none, `force=None` (default) the rules' own `capture: true`. Each selected, not-already-captured target is fetched once via `capture_and_ingest` — depth is fixed at 1 (a grabbed target is ingested as a stub, never expanded; multi-hop stays `crawl`'s job, §11). Best-effort: a per-target failure is recorded, not raised. Surfaces: `corpus capture --with-references` / `--no-references` (the inline grab after the primary ingest), `corpus crawl --references [seed]` (the deferred sweep; `--dry-run` lists pending targets).
- **Discovery + view.** `corpus links --references <record>` previews the declared subset, each line annotated `[role=…, captured|pending, auto?]`. The `references` derived view (§9.9) is the `reference`-namespace projection; the reverse edge (which records reference *this* one) is a corpus-wide read, not indexed (§9.9 / §11).

#### 12.3.11 Pre-ingest bundle assembly (`corpus assemble`, 2.1)

Some sources deliver an export as one or more **transient part archives** — an expiring download job, a solid compressed stream with no member index (a tgz) — where the delivered envelope is worthless to preserve and hostile to containment resolution; others deliver **no envelope at all** — an export tool (DiscordChatExporter) that writes a loose directory tree straight to disk. `corpus assemble --origin <overlay-id> <part…> [--add <file>]…` repackages such a delivery (a part is a tar/tgz/zip archive or a directory tree) into ONE indexed bundle **before** ordinary ingest, driven entirely by the overlay's `capture.assembly` config (§7.2): union the parts' member trees (`merge_parts`, `conflict: error` on divergent same-path bytes), drop declared-cruft members (`excludes` — reported, never silent), place declared `additions` at the bundle root (the original tree is never touched; any restructure exists only as an asserted `rewrites` rule), derive origin fields mechanically (`derive` patterns over the source filename convention, addition contents, and directory-member head bytes; CLI flags override), and write the bundle plus its capture sidecar (`origin_schema:` + fields, §12.3) into `capture/` staging. A directory source's member relpaths come verbatim from its tree root and member mtimes from disk; having no envelope it leaves no `source_parts` tombstone — its assertion of byte identity is the per-member blake3 the manifest records. The engine is two layers: a **reusable deterministic bundle writer** (sorted members, verbatim paths, source mtimes, per-member zstd with `stored` for already-compressed types, archive comment stamped with the job identity, streaming, atomic; same inputs → same bytes) — shared with the planned `pack` verb (§12.8), which feeds it existing corpus artifacts instead of extracted part members — and the overlay-driven assemble frontend. The consumed parts are recorded as `source_parts` tombstones (`<filename> blake3:<hash>`) on the bundle's origin block, and are retired via `rm` only after the bundle's members verify container-resolvable. Assembly is the one deliberate exception to parse-tolerance: an unreadable source member aborts with no partial bundle — a bundle is complete or absent. Member byte-identity is untouched by re-packaging (§2), so records promoted from a part archive survive an assemble→retire cycle with zero edits — residence just moves.

#### 12.3.12 From-save capture (manual SingleFile saves)

A manual SingleFile save — a page a human saved from their own browser session — is often the *only* faithful record obtainable: content behind a login the tooling can't replay, a page since changed or removed, a session-specific view. **From-save capture** makes such a save a first-class capture: `corpus capture <path>` (the argument resolves to an existing local file rather than a URL) replays the saved DOM through the same browser pipeline live capture uses, so the host overlay's `capture.interactions` (§12.3.6) apply identically to both. The save is not merely ingested — it is re-rendered so the per-host chrome strip and media surfacing run against it.

- **Provenance is the banner.** The save's SingleFile banner (§12.3.4) supplies the origin URL (used to look up the host recipe) and the saved date. Absent a banner, a `<file>.capture.yaml` sidecar's `source_url` / `fetched_at` is the fallback; with neither, from-save refuses with a clear error — it cannot record a capture whose source URL is unknown.
- **The save is the honest state — nothing is fetched live.** The file loads via `file://` in a headless browser with CSP bypassed (a save may carry a CSP `<meta>`) and **every http/https request aborted**. A SingleFile save has already inlined every asset as a `data:` URI, so the saved bytes are self-contained; the abort guarantees a dead-script DOM can never reach the network to backfill what the human's save did not capture. The overlay's `capture.interactions` still run (`DEFAULT_STEPS` when the recipe declares none) and remain best-effort — a click / lazy-load step that depended on live scripts degrades to a no-op, while `remove` / `expand` / `eval` DOM surgery applies as in live capture.
- **The snapshot is stamped to the saved date.** The re-snapshot injects the same `corpus-*` metas live capture does, but with `corpus-capture-url` = the banner URL and `corpus-fetched-at` = the saved date, and ingest seeds the record's first origin with `snapshot:` = the saved date — the fetch happened when the human saved the page, not when it was re-snapshotted. Fidelity, viewport, and interactions resolve from the overlay exactly as for live capture.
- **The source is retained.** From-save never unlinks the source file — a manual save can be irreplaceable — consuming only the re-snapshot staging file at ingest. The already-captured short-circuit (§12.3.5) and `--force` behave as for a URL capture, keyed on the resolved banner URL.

### 12.4 Draft

Draft brings a stub to `status: draft`, applying schemas in the §8.1 order: the mime schema first — the sole body-drafter, segmenting the content zone, emitting embeds, filling the artifact block's bare fields — with atom overlays riding segment openers, then the origin overlay's declared emissions (`reference`/`relation` context blocks, `provenance: auto`). A classification is never a frontmatter array and carries no justification field — the `classifications` list is a derived view (§9.1) — and records carry no `tags` field.

#### 12.4.1 Per-format drafters

Conversion produces the artifact's body as well-formed markdown. It is MIME-driven and shells out to deterministic tooling:

- **`text/html`, `application/xhtml+xml`** → the mechanical HTML drafter (`draft/html.py`). It removes only non-rendered infrastructure (scripts/styles/comments), assigns `el=N` addressing to every content element of the raw artifact (the shared `transforms.html.is_addressable` predicate — content-bearing blocks and inline-media carriers, not layout-only `div`/`span` wrappers), emits dedup'd embeds, and emits one cleaned-`<body>` text segment. The `el=N` axis is the structural `_ADDRESSABLE_TAGS` set (content blocks + `<img>`) plus inline-media carriers: `<video>`/`<audio>` (materialized from their inline `<source data:…>`) and `<a href="data:…">` attachments (vCards, files). Every carrier becomes a dedup'd embed (`transport` = blake3 of the decoded bytes; `media_type` from the data URI; an attachment keeps its recovered `filename`, an image its `width`/`height`/`alt`), and the carrier's base64 `data:` payload is stripped from the body — the carrier survives as a body-empty `el=N` positioning marker (critical: a single inline video can be hundreds of MB). A bare `<a>`/`<source>` is not addressable — only a `data:`-bearing one — so per-message deep links never consume an index. The carrier→bytes round-trip lives on the resolver side (`transforms/html.py`); drafter and resolver import the same predicate + helpers, so they name the same elements `el=N` by construction (asserted in `test_drafters.py`). The drafter does **not** strip page chrome — a universal tool can't reliably tell chrome from content, and a wrong guess drops content silently; chrome removal is a capture-time, per-host decision (§12.3.6). Structural recovery (headings/tables/lists/equations) is the normalizer's job.
- **`application/pdf`** → `draft/pdf.py` is uniform and mechanical: every PDF drafts to the same shape — one body-empty `image` segment per page addressed `page=<N>`, sectionless — plus the `/Info` fields on the artifact block (`page_count`, `title`, `author`, `producer`, `creation_date`, `modification_date`). The drafter makes no born-digital-vs-scanned determination and extracts no text; the page raster is the faithful transport unit (§11). Everything an agent needs to determine a page's shape and recover its content is exposed at normalize time through the resolver's introspection ops (§6.2): `page=<N>&text`, `page=<N>&words`, `page=<N>&probe` / `probe`, and `outline`. The normalizer uses these to pull born-digital text into prose segments, OCR a scan into `text/ocr` at `page=<N>&bbox=…` (so the corpus owns OCR provenance — engine/confidence/region — rather than laundering a pre-baked machine-OCR layer), and wrap pages into sections from the outline (`pages=<start>-<end>`). Resolver mechanics: `page=<N>` yields an intermediate `pdfpage` selector so a sub-op reads the page directly rather than OCR'ing a render; a terminal `pdfpage` — or an image op / `bbox=` after it — auto-renders to image, so a `page=` image segment stays a self-slice needing no embed (`lint._self_slice`). `words`/`probe`/`outline` cache as `json`. Canonical: `blake3-canonical-pdf` (per-page extracted text; persist currently disabled — §7.1 note).
- **`application/epub+zip`** → the EPUB drafter (`draft/epub.py` + the pure `corpus.epub` OPF reader). `self_contained` — an EPUB is one work, one record. Emits one bare `text` segment per spine (reading-order) content document, addressed `spine=<N>`, with a mechanically-cleaned structural-HTML body (same philosophy as the HTML drafter), and groups them into sections by the book's navigation document (EPUB 3 nav → EPUB 2 NCX): top-level TOC entries become sections (`address: spines=<start>-<end>`, `entry:` = the part/chapter title), spine docs before the first TOC target become a synthetic `Front matter` section — the exact analogue of the PDF outline wrap (`pages=`/`page=` ↔ `spines=`/`spine=`). A book with no usable nav drafts sectionless, like an outline-less PDF. Each `<img>` references a separately-stored zip member, so it becomes an **embed** (addressed `spine=<N>&el=<K>`, `transport` = blake3 of the member bytes, deduped across the book; the body keeps a src-stripped `<img data-el="K">` placeholder) — the HTML drafter's embed model, not the PDF's bare-image-segment model. That address materializes through `transforms/epub.py`: `spine=<N>` selects the OPF content document and binds a resolver over the book's zip image members, then `el=<K>` resolves the addressed `<img>` to its member bytes — so a recorded address round-trips to byte-identical content (the resolved bytes' blake3 == the embed's recorded `transport`; el-indexing is shared with the drafter via `corpus.epub.addressable_image_bytes`). Publication metadata (Dublin Core) lands as bare artifact fields (`title`/`creator`/`language`/…; `spine_item_count`/`toc_entry_count` record the shape). Canonical: `blake3-canonical-epub` (concatenated spine text — packaging-invariant).
- **Raw `application/zip`** (and the tar family — `.tar`, `.tgz`) → drafted by the `zip-manifest` strategy (a tar sibling shares the strategy's representation; a tgz is a solid gzip stream, so member access is a streaming decompress — the resolver cache absorbs it, §12.9): every member an embed, content zone empty, members promotable on demand (§8.1). A corpus that wants a *particular* archive-shaped bundle recognized as its own type still declares its own mime schema for it (recognized by shape via `applies_to.zip_member_patterns`, §12.3.2) and points it at the same strategy. *(2.1: raw zips no longer explode at ingest — `_ingest_decomposable` retires; a member record now exists only where someone deliberately promoted it.)*
- **`draft.strategy: zip-manifest`** → the general `self_contained`-zip drafter (`draft/zip_manifest.py`), selected by *strategy* rather than schema id (`corpus.draft.STRATEGY_REGISTRY`), so one drafter serves any number of bundle types that differ only by the schema's `draft.manifest` config. It records the archive as an **embed manifest**. The modeling point: a zip member is a *transport* (a file with its own bytes + MIME), not a content atom — and an embed is precisely "an embedded transport". So every member becomes an embed (`transport` = blake3 of the member bytes, `media_type` content-sniffed, addressed `path=<relpath>`, root-stripped per `manifest.root_strip`) that the normalizer describes — and the content zone is **empty**: a pure container has no content atoms of its own, and a member's bytes are verbatim + resolvable, so nothing is transcribed. The folder hierarchy lives in the `path=` addresses (a tree is a derived rendering, not stored blocks). `media_type` is content-sniffed (`_is_text`: UTF-8, no NULs), not extension-guessed, so a `.cfg`/extensionless log is `text/plain`; a precise extension guess (`application/json`, `image/png`) is kept; an opaque binary is `application/octet-stream`. Bytes materialize through `transforms/zip.py`: `corpus://<id>?path=<relpath>` → the member bytes. The artifact block carries generic zip facts only — `member_count`, `uncompressed_bytes`, `compressed_bytes`, `compression`, `encrypted`, `comment`; a single wrapper dir's name is a fallback `title` candidate. The drafter knows nothing about any vendor: recognizing a bundle as, say, an Unraid diagnostics package and surfacing its identity is ledger knowledge — a harvest rule keyed on the kept-whole MIME rosters the record onto its concept mechanically (`ledger.md` §10) — not this drafter's concern, and not the artifact block's. An empty archive yields a blocking `partial-content` issue; because such a record has no content-zone segments, the `embed-unreferenced` lint is relaxed for it (the embeds ARE the content).
- **`draft.strategy: mbox-manifest`** → the **selective** mailbox drafter (`draft/mbox_manifest.py`). Unlike the archive manifests it does NOT declare every member — a mailbox may hold 10^5 messages — so `corpus draft <mbox-id> --messages 5,12,90-95` declares only the named 1-indexed messages, each recorded as a `message/rfc822` embed addressed `msg=<N>` (blake3 over the un-stuffed member bytes, plus the message's Date / From / Subject and byte length). It is cumulative and idempotent: re-running unions the newly-named ordinals with the already-declared set (an identical re-declaration folds; a changed hash for a declared ordinal is a hard error), and a plain `corpus draft <mbox-id>` records the mailbox summary only (message count, byte size, date span) with no embeds. Extraction is pinned (§12.11): a separator is any line beginning with `From ` (mboxrd), un-stuffing drops one leading `>` from a `^>+From ` line, and line terminators are preserved — so member bytes are deterministic. A declared message is promotable (§8.1); its bytes stream out of the mailbox via `transforms/mbox.py` (`corpus://<mbox-id>?msg=<N>`, streaming to the ordinal and stopping at the next separator, never loading the mailbox whole), and a promoted message is `message/rfc822`, drafted by `draft/eml.py` (next).
- **`application/json`** (`draft/jsonfile.py`) → the verbatim-**passthrough** drafter. JSON is a carrier syntax, so the faithful representation of a JSON artifact is its own text: the drafter decodes the bytes (UTF-8 per the JSON spec, BOM tolerated) and emits ONE `text/code` segment (`language: json`) spanning every line, addressed `line=1-<N>` — no element explosion, no reshaping, no key extraction. Two cheap shape facts land on the artifact block (`json_root`, `json_top_count`); parsing is validation only — a malformed document still drafts (parse tolerantly) with a `malformed-json` warning issue. What a given JSON *means* is the origin overlay's normalization guidance plus ledger knowledge, never this drafter's — the normalizer's licence is annotation (frontmatter `title`/`description`, optional contiguous line-addressed sub-segmentation), never transformation of the passthrough body.
- **`message/rfc822`** (`draft/eml.py`) → a promoted (or standalone-ingested) email message. The mechanical drafter (1) lifts the headers onto the **artifact block**, RFC2047-decoded and single-line — `subject` (also the `title` candidate), `from`, `to`, `cc`, `bcc`, `date`, `message_id`, `in_reply_to`, `references` (a list in file order), `thread_id` (Gmail `X-GM-THRID`) — so thread reconstruction is a frontmatter query (`references` / `in_reply_to` ↔ `message_id` joins, grouped by `thread_id`); (2) renders the body as the **reply text only** — the `text/plain` part, else `text/html` reduced to text, with trailing **quoted history** trimmed from the first confidently-matched marker (an `On … wrote:` attribution directly above a `>`-quoted line, `-----Original Message-----`, an Outlook header block or underscore rule, or a `>`-run to EOF), keeping everything when no marker matches (prefer false negatives) and keeping signatures; and (3) records **every non-body MIME part** — attachments, inline images, nested messages — as a `part=<N>` embed (`transport` = blake3 over the **CTE-decoded** payload, plus `filename` / `disposition` / `content_id`), skipping the text alternatives the body consumed. A declared part is promotable (§8.1) — a contract-PDF attachment becomes a first-class `application/pdf` record whose bytes never leave the message, materialized via `transforms/message.py` (`corpus://<eml-id>?part=<N>`). Because the parts are message *members* (not body-flow assets a mechanical pass can position), `embed-unreferenced` is relaxed for a `message/rfc822` record — the normalizer links an inline image into the body where it belongs.
- **`audio/*`** → speech-to-text transcription (reference: Whisper), with timestamps and speaker turn markers where determinable. `audio/mp4` covers `.m4a`/`.m4b` audiobooks (an `.m4b` magic-sniffs as `video/mp4` on its generic ISOBMFF brand; `mime.detect` refines it by extension so it routes to transcription — embedded chapter markers and cover-art `mjpeg` are not consumed in v1).
- **`video/*`** → audio transcription + per-keyframe descriptions when the schema asks for them.
- **`image/*`** → a single body-empty `image` segment addressed `bbox=0,0,1,1` (`draft/image.py`); the image is its own self-artifact — no embed; the bytes are the record's, materialized via the `bbox=` functional URI (§4.3.1.4). Any visual description is normalizer-written on the segment `description:`; an optional `perceptual:` when the fingerprint knob resolves on. No VLM/OCR in the deterministic drafter.
- **`text/markdown`, `text/plain`** → passthrough with minimal cleanup (one `text` segment, body = the source text).
- **`unknown`** → best-effort fallback; emit a metadata-only body summarizing what little can be determined.

#### 12.4.2 One construction path (the constituent model)

Every drafter builds the record's content zone through the **`recordbuild.Build` ops** — `add_blocks` → `open_section`/`add_segment` (which enforce body⟺lossless per segment) — and `recordbuild.finish` emits + grammar-validates it. These are the same ops `compile` replays from a decomposed `manifest.corpus`, so draft / redraft / decompose / compile / normalize all construct records identically, and a drafted record decomposes then recompiles byte-for-byte. This is the substrate the LLM normalizer works on: it edits the decomposed **constituent files** (per-segment body / description sidecars + the ops manifest) and recompiles deterministically — never rewriting a monolithic markdown blob — which makes whole classes of structural corruption unrepresentable. (`begin_from_post` seeds the Build for draft/redraft; `begin` seeds it from a `meta.yaml` for compile.)

#### 12.4.3 Corpus-local drafters

A corpus can specialize the draft of its *own* content without editing the package — the draft-stage analogue of the corpus-local capturer (§12.3.1). `_cli/draft.derive_record` loads `<corpus_root>/drafters/*.py` (via the same `local_code` loader and trust boundary) before any dispatch. The first hook is HTML: a module calls `@draft.html.register_html_subdrafter("<origin-id>")`, and the mechanical HTML drafter hands the whole content zone to it when the record's origin matches — a producer-declared `corpus-origin-schema` meta or a stamped origin-block id (§7.2) — instead of leaving the single wrapping `el=1-N` segment for the normalizer. The sub-drafter returns the same `(blocks, embeds, issues)` trio the generic path produces and reuses the public `compute_embed_metadata` + `transforms.html.is_addressable`, so its `el=N` addresses and embed transports line up with the resolver by construction. The record envelope (title, origin fields, canonical) stays the generic path's; only the content zone is delegated. Format-specific drafters, atoms, and overlays for private content live in the owning corpus repo, never in the package.

#### 12.4.4 Perceptual fingerprinting (opt-in)

A segment gets a `perceptual:` only when `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override)` resolves on — precedence CLI (`corpus draft --fingerprint` / `--no-fingerprint`) › origin overlay › mime-schema `fingerprint` knob › off (the default; §7.7). The resolved knob (`true` = the atom's default algorithm, an algorithm name, or a list) becomes concrete per-atom algorithms via `fingerprint.algos_for_atom(atom, knob)`, computed by `fingerprint.text_fingerprints` / `image_fingerprints` (a registry keyed by algorithm, mirroring `content_hash._STRATEGIES`). Algorithm selection is schema-only; the CLI flag is on/off.

#### 12.4.5 Deterministic auto-classification *(removed in 2.0)*

*Retired with the composite namespace (§7.4).* The `classify_when` engine, `corpus classify`, `corpus reclassify`, and lint's `classification-stale` all retire; deterministic membership is now a ledger **harvest rule** over the same fact base (`ledger.md` §10), evaluated ledger-side (`ath ledger harvest`) as a pure function of the corpus's mechanical record facts — so `draft` no longer carries any classification hook at all.

#### 12.4.6 Bulk recompile (`corpus redraft`)

A drafted record is a deterministic function of (retained artifact + schemas + tooling), and `id = blake3(artifact)` is unchanged by re-derivation — so regenerating it is an in-place `.md` rewrite, and `git diff records/` surfaces exactly which records a schema / overlay / tooling change affected. `corpus redraft [target] [--mime/--host/--status] [--dry-run] [--fingerprint]` applies the per-record draft core across the corpus via a clean re-stub (`restub.restub_post` with the touch chain collapsed to the original ingest entry, no re-stub touch) — so an unchanged record re-derives byte-for-byte and is not rewritten (idempotent; `--dry-run` reports the set, writing nothing). It refuses `normalized` records unless `--force`, since re-deriving discards normalization. Distinct from `corpus compile`, which reassembles a record from a decomposed *manifest* (§12.4.2) rather than from the source *artifact* — different inputs, different jobs. (`records.dumps` serializes a record to canonical text without writing, so redraft can compare against disk.)

Pipeline-state provenance is the `touch[]` chain (§4.2.2): each pass appends a `<pkg>.<module>@<version>` (or `<model-id>`) identifier, so the latest touch's tooling version encodes the spec era of the record's current shape and re-run targeting reads it. There is no separate `conversion_method` / `conversion_tool` field.

#### 12.4.7 Cross-reference resolution

After the body exists, scan segment bodies for **hyperlinks** (`<a href>` → other resources) — *not* same-transport inline media, which is already an embed + segment (§12.4.1). For each hyperlink:

1. Map the URL → `id` by querying the corpus's URI index (`records.build_uri_index` — every record's origin `uri:` list keyed by identity, §12.3.9).
2. If matched, rewrite as a raw intra-corpus wikilink `[[<id>|original link text]]` — no URI scheme prefix; these are layer-local cross-artifact references (§4.3.2.2 / §5.1).
3. If unmatched, leave the plain markdown URL. The target is outside the corpus and may resolve on a later re-resolution pass once it is captured.

This is purely mechanical: the pipeline does not invent links the original content didn't contain. A lightweight sweep re-runs just this pass against existing bodies — useful after a batch of captures resolves URLs left as plain markdown in older records.

**Reconciliation tooling.** The on-demand counterpart ships as `corpus links` (per-record) and `corpus crawl` (frontier BFS): both extract a record's `<a href>`, resolve relatives against its origin URI, normalize, and look each up in the URI index. A hit means the reference is already captured; a miss is the crawl frontier. `corpus links --show-captured` annotates which is which. Link extraction filters hrefs through `urls.is_crawlable_href`, which keeps client-side routing fragments (`#/route`, `#!/route` — on a hash-routed SPA the fragment *is* the resource identity) while dropping bare anchors (`#section`) and the `javascript:`/`mailto:`/`tel:` schemes.

### 12.5 Normalize

Normalization brings a record from `draft` to `normalized` (§8.1). It is interpretive — performed by an external agent session driven through the queue (§8.5, §12.5.6), never by the tooling itself.

#### 12.5.1 The interpretive pass

The normalizer refines the record — faithful-form work only:

- Improves formatting fidelity (broken tables, malformed lists); resolves encoding ambiguity where determinable.
- Writes asset descriptions on embeds and on self-slice / non-lossless segments via `description:` (lossy interpretation — never in a faithful segment body); fills embed `alt` only when the source provides it.
- Surfaces problems as `<!--context issue/<id>-->` blocks in the annotations zone.
- Authors the frontmatter `title` and `description` (the two editorial fields, empty until now).
- Re-segments the content zone where judged appropriate (structural only), and sets `status: normalized`.

The pass MUST preserve faithfulness (§1.5 principle 3): no information that wasn't in the source; descriptive content lives on `description:` / `alt`, never in a segment body.

#### 12.5.2 Self-verification

Before declaring the record normalized, the normalizer confirms:

- The artifact-block opener MIME matches the actual MIME of the stored binary (the opener is authoritative, §12.3.2).
- The `id` (blake3) matches the binary's hash.
- The on-disk record path matches the shard convention.
- `corpus lint` is clean at `normalized` severity — lint is the executable encoding of the spec's required-field and grammar rules.

Failures here are pipeline bugs; they should fail loudly.

#### 12.5.3 Annotations in practice

A context block stores as `{namespace, id, subtype, fields}` in `post.metadata["_contexts"]`. The bundled namespaces are `issue` and `reference` (§4.3.3); a corpus may add its own under `schema/context/<ns>/` (`relation` overlays are corpus-local, per §4.3.3.5). Context is scarce by design (§4.3.3), and there is deliberately no bundled free-text `note` namespace — that would invite scratchpad flooding. The `aside` namespace named in §4.3.3 has no bundled overlay yet; it is deferred.

- **Issue loading and parse tolerance.** `schemas.load_context_schema(corpus_root, "<ns>/<id>")` layers `context/<ns>/<ns>.yaml` → `context/<ns>/<id>.yaml`. `records.iter_issue_blocks` / `append_issue_block` are shims over `_contexts` filtered to the `issue` namespace, so drafters/detectors, `health.unresolved_issues`, the §9.2 view, and lint's issue rules share one path. The reader is parse-tolerant: a legacy `<!--issue <id>-->` still loads (as the `issue` namespace) and upgrades to `<!--context issue/<id>-->` on the next write.
- **Reference lint.** `context-namespace-unknown` flags a block whose namespace has no `context/<ns>` overlay. *(The 1.0 `reference-unresolved` lint retired with the stored tier-3 `source_uri`, §4.4.5.)*
- **Decompose/compile conventions.** The manifest keeps a dedicated `issue <id> sev= res= detector=` line for the issue namespace and a generic `context <ns>/<id> k=v…` line for the others (`recordbuild.add_context`). Two conventions keep the working dir hand-editable: `status` is authored only on the manifest `record … status=` line (not duplicated in `meta.yaml`, where an edit would be a silent no-op), and `meta.yaml` renders a multi-line string as a YAML block literal (`|`) so a multi-line `description` never reads as a truncated stump. An address list in the manifest is bracketed and `|`-separated (`[a|b|…]`), not comma-separated — a single address (e.g. `bbox=x,y,w,h`) already contains commas.

#### 12.5.4 Normalizer-support commands

The LLM normalizer never reads `schema/*.yaml` directly; it works through read-only commands (`_cli/{diagnose,guidance,overlay,preview}.py`, surfacing the §9 derived views and the §6 resolver):

- **`corpus diagnose <hash> [--json]`** — the first call: a one-page brief combining the derived views (classifications / issues / uris) with a quick-lint and the record's context blocks.
- **`corpus guidance <hash>`** — the merged `normalization.guidance` from every applied mime / origin / atom overlay for the record.
- **`corpus overlay <namespace>/<id>`** — the field-spec table (types, `semantic_type`, required) for a mime or atom overlay, so the normalizer works without reading YAML. Given a bare host instead, it falls back to the origin overlay and prints its host match, declared operational sections, and `normalization.guidance`.
- **`corpus lint <target> [--json]`** — the conformance gate; `--json` emits a single JSON array of findings (each = the `Finding` fields + `record_id`), across all records when `<target>` is omitted.
- **`corpus preview <target> [--page N] [--mark x,y,w,h]… [--full] [-o out.png]`** — the cropping loop's *eyes* (§12.5.5). Renders the artifact (an image, or a PDF page via `--page`) with each proposed bbox outlined on the full image so a vision-model normalizer can see where a region sits, judge the fit, and adjust before committing. Read-only — it never writes the record; the agent commits regions separately by editing the record body. Fits the render to the `llm` budget by default; prints the cache path, or copies to `-o`.

#### 12.5.5 The image toolkit

This group was shaped by reviewing real normalizer runs on image-of-document records (scanned/photographed forms), whose dominant friction was `bbox=` **semantics**: agents read `bbox=x,y,w,h` as corner coordinates, overflowed `x+w>1`, and the resolve failed. The fixes target that directly: the `crop=`/`bbox=` bounds error names the format and the overflowing axis (`… bbox is x,y,WIDTH,HEIGHT, NOT corners`), `corpus resolve`/`corpus preview --help` print the full transform grammar (`_common.TRANSFORM_GRAMMAR`), and `mime/image/image.yaml` carries `normalization.guidance` teaching the bbox convention, crop-first legibility, orientation, and the verify loop.

- **`mark=x,y,w,h[;…]`** (image → image, §6.2) — draws the region(s) onto the full image rather than cropping to them: the inspection dual of `crop=`/`bbox=` (a cycling high-visibility stroke, auto-labeled `1..N`, width ∝ image size). Composes after `page=`, so `corpus://<id>?page=4&mark=0.1,0.1,0.6,0.3` outlines a box on a rendered PDF page — how an agent that can't run a browser sees a proposed crop, as a PNG with the box burned in.
- **`fit=<W>x<H>` | `fit=<preset>`** — downscale to fit, aspect-preserving and reduce-only; distinct from `resize=` (forces exact dimensions, may distort or enlarge). The **`llm` preset** bounds the image to a vision model's input budget: long edge ≤ `LLM_MAX_EDGE` (1568 px) and total pixels ≤ `LLM_MAX_PIXELS` (1,150,000), the smaller scale winning. These constants live in `transforms/image.py`, not Part I — §6.2 keeps presets implementation-defined because model limits drift. PDF `dpi=` is the other half of the dial: rasterize at the DPI you want, then `fit=llm` caps the result.
- **`rotate=90|180|270`** and **`auto_orient`** — right a sideways/upside-down phone photo or scan before the agent reads it; `corpus preview --rotate`/`--auto-orient` expose them.
- **`autocontrast`** (1% cutoff) and **`contrast=<factor>`** — pull a faint scan toward readable; `corpus preview --autocontrast` exposes the flag.

The split that keeps `fit` honest: the transforms stay pure (no implicit fitting), and only the agent-facing surface defaults the budget on — `corpus preview` fits to `llm` unless `--full` (a preview *is* going into model context), while a raw `corpus resolve` applies `fit=` only when the URI says so (a codex embedding a crop in a human-facing deliverable wants native resolution). A typical loop iteration: `corpus preview <id> --page 4 --mark 0.1,0.1,0.6,0.3 -o /tmp/look.png`, read it, adjust, repeat; once right, write the segment at `page=4&bbox=0.1,0.1,0.6,0.3`. **`corpus preview --from-segments <id>`** is the verify half: it reads the record's already-committed bbox segment addresses (grouped by `page=`) and draws them, so the normalizer can confirm each written address frames the span it meant.

One caveat the image guidance makes explicit: unlike a PDF (vector source, re-renderable at higher `dpi=`), an image's resolution is fixed — cropping can't add detail, so for fine print on a low-res capture the levers are crop-tight + `resize=` (interpolated enlargement, not new detail) + `autocontrast`; there is no DPI escape hatch.

#### 12.5.6 Queue mechanics

The queue contract is §8.5; the verbs live in `_cli/{enqueue,drain,finalize,release,await,queue}.py` over the `corpus.queue` library.

**State layout.** External, untracked, under `<root>/queue/` (gitignored alongside `artifacts/`, `capture/`, `cache/`), one marker per record: `<id>.req` (pending request: `requested_at`, `requested_by`), `<id>.claim` (in-flight: `claimed_at`, `claimed_by`), `<id>.result` (last terminal outcome: `completed` | `failed`, with `reason`). A record's queue state is a pure function of which marker exists; markers are JSON written atomically (temp sibling + `os.replace`). The queue never touches `records/` — every verb is read-only on the record (`finalize` reads it to lint; `await` reads `status` as a fallback).

**Atomic claim.** `drain` claims by `os.rename(<id>.req → <id>.claim)` — atomic on POSIX, so when two loop sessions race, exactly one wins (the loser's rename raises and it moves to the next candidate). Requests are claimed FIFO by `requested_at`. An empty queue returns nothing on stdout and exit 1 — the loop's stop signal (per §8.5 this is a non-error empty result; the exit code exists only to break the loop). A stale `.claim` (a dead session) is reclaimable once `claimed_at` is older than `--lease` (default 30 min); reclaim renames it back to `.req`. A duplicate pass from an over-eager reclaim is wasteful, not unsafe (re-normalization is idempotent), so reclaim is best-effort.

**The loop session** (the agent, not the tooling) drives it:

```bash
while id=$(corpus drain --by "$SESSION"); do
    corpus guidance "$id"     # merged overlay normalization.guidance (§12.5.4)
    # ...the agent normalizes $id in-session: title, description, embed/segment
    #    descriptions, re-segmentation; sets status: normalized; recompiles...
    corpus finalize "$id" || corpus release "$id" --failed "<reason>"
done
```

That bare loop is the **scheduled** shape: a tick (cron) drains until dry, then the model sleeps until the next tick — the model polls, waking on a clock even when the queue is empty. `drain --wait` moves the poll off the model: it long-polls the claim primitive in the subprocess and returns the instant a request is claimable, blocking instead of exiting on an empty queue (until `--timeout`, if set; `--interval` sets the poll cadence, default 2 s). The wait holds no claim — `drain` claims atomically only at the moment it succeeds — so an interrupt mid-wait leaks nothing. A **standing** loop runs `corpus drain --wait` under a persistent runner that re-invokes per claim, so the (expensive) model wakes only when there is genuinely work. The contract is unchanged: `--wait` is an ergonomic over the same atomic claim.

**The done gate.** `finalize` refuses (exit 1, claim left intact) unless the record is `status: normalized` *and* lints with no error-severity findings — a dirty pass is never reported complete. A requester (a codex agent) does `corpus enqueue <id>` then `corpus await <id>`; `await` polls the external state and resolves by exit code, so it works for a re-normalization of an already-`normalized` record (status alone can't tell the new pass apart — the queue entry can). Because per-domain knowledge rides in overlays (`corpus guidance`), one generic loop serves every codex; a codex contributes by authoring overlays and enqueuing, never by supplying a normalizer.

**Result lifecycle.** `.req` and `.claim` are transient — each transition is an atomic rename that consumes the prior marker — but a settled pass leaves a `<id>.result` that nothing removes on its own (§8.5: an outcome must outlive the pass so a decoupled requester can await after the loop tick ends). Results are GC'd by age: `corpus queue --prune [--older-than DAYS]` (default 7 d; `0` = now) removes settled results past the grace window and sweeps crash-orphaned `*.tmp.*` scratch, never touching live `.req`/`.claim`. Run it periodically; it is idempotent.

**Operator runbook.** The operating modes and result lifecycle are surfaced via `corpus workflow normalize-loop` — guidance for *running* the tooling, distinct from `corpus guidance <id>` (per-record). Runbooks are markdown shipped in the package (`corpus/workflows/`, loaded via `importlib.resources`); `corpus workflow` lists them, shows a runbook, or narrows to a section. The queue verbs' `--help` cross-reference it. Keeping the runbook in the package means the operating modes are maintained once, in the tooling, not duplicated per corpus.

### 12.6 The curator feedback loop *(reshaped in 2.0)*

The 1.0 loop authored composite overlays from observed patterns. The loop survives; its outputs relocate:

**Pattern detection.** The curator periodically scans for patterns worth encoding: origin / fact frequency (many records share a host or a deterministic fact — a `ytdlp_channel_id`, a URL shape); recurring body shapes within a host; demand flowing down from above (the ledger's needs and coverage gaps, `ledger.md` §7/§9).

**Where each pattern lands.** A recurring *deterministic membership* pattern becomes a ledger **harvest rule** (`ledger.md` §10 — authored in the ledger, evaluated by `ath ledger harvest`). Recurring *body-shape* guidance becomes origin-overlay guidance (per host / subtype, §7.2) or an atom overlay (per form, §7.3). Recurring *link structure* becomes a `capture.references` / `capture.relations` declaration (§7.2). Domain conventions for authoring claims land in the ledger's `facts/SCHEMA.md` or a concept schema (`ledger.md` §4.4), never in corpus schemas.

**Re-propagation.** Corpus-side overlay changes re-propagate with `corpus redraft` (scoped by `--host`/`--mime`; `git diff records/` is the review surface). Ledger-side rule changes re-propagate with `ath ledger harvest` — records are untouched.

### 12.7 Re-run verbs

Every stage is independently re-runnable (§8.3); each re-run appends a `touch[]` entry. Re-processing is how the corpus absorbs improvement: new schemas, a better extractor / transcriber, an upgraded normalization model, or newly-captured artifacts that resolve old cross-references. The CLI mapping:

- **Re-ingest** — automatic on re-encountered bytes matching an existing `id`; folds the capture into origin blocks (§12.3.5), never a new record.
- **`corpus redraft`** — re-derive from the retained artifact + current schemas/tooling (§12.4.6).
- **Re-normalize** — enqueue the record again (§12.5.6); refreshes the faithful-form work and faithfulness issues, may re-segment.
- **`corpus compile`** — reassemble a record from a decomposed manifest (§12.4.2) — a different input than `redraft`'s artifact.
- **`re-stub`** — the deliberate reset to `status: stub` (§8.4).

**Scoping a sweep.** Deterministic re-derivation makes scoping a `git diff records/` concern rather than a field-level-diff one: re-derive the affected set and the diff *is* the surgical, reviewable change surface. Scope by the most precise selector available — `--host` (a re-captured / re-overlaid origin), `--mime` (a drafter or mime-schema change), `--classification` (a `mime/*` / `origin/*` class), `--status` (e.g. only `draft`).

### 12.8 Maintenance: GC and record removal

Two distinct risk classes, kept as separate verbs (`corpus.maintenance`): a routine, age-gated sweep of regenerable data (`gc`) and a deliberate, ref-checked removal of a tracked record (`rm` / `forget-origin`). Nothing here is normative — Part I is silent on removal; this is CLI hygiene over the storage layout (§12.1).

- **`corpus gc`** prunes, by file mtime, four regenerable categories — never a tracked record, a live queue entry, or an artifact that still has a record: **`cache`** (resolver output; re-warms on the next resolve), **`staging`** (leftover `capture/` debris — sidecars, crawl coordination files, abandoned partials), **`orphans`** (artifacts with no owning record — ingest is the only writer of `artifacts/`, so an orphan is exactly an artifact file whose record is gone: the debris of a `--force` re-capture, a re-stub, or a hand-`rm`), and **`export`** (regenerable bundles). Previews by default (counts + bytes per category); `--yes` deletes. `--older-than DAYS` sets the grace window (default 7; `0` prunes everything now) — generous beyond the brief window in ingest between writing an artifact and its record, so the orphan sweep never races a fresh capture. `--include` restricts the set; `--json` emits the structured result. Idempotent, empty-shard-tidying, safe on a cron tick.
- **`corpus rm <id>`** removes a record across its layers — the `.md`, the content-addressed artifact, and now-empty shard dirs — with three guards. *Dry-run by default*: without `--yes`/`--force` it prints the plan (paths, sizes, inbound referrers) and deletes nothing. *Ref-checked*: `inbound_references` scans every record's `reference` blocks (§4.3.3.3) for one citing the target — a `source_url` that resolves to it — and refuses a cited record (exit 1) unless `--force`, naming the would-be-dangling referrers. (Ledger evidence citing the record is the other inbound-reference class; checking it is a ledger-side concern — `ath ledger worklist` names the citing claims.) *Reproducibility-warned*: the artifact is gitignored, so dropping it is undoable only by re-capture — `rm` says so, and `--keep-artifact` drops the `.md` while retaining the bytes. It deliberately does not touch the resolver cache (cache is keyed by functional-URI hash, so there is no clean per-record slice); `gc` reclaims orphaned cache by age. A fourth guard lands with containment (2.1): removing a **container** whose members have promoted records strands those records' bytes — `rm` names the promoted members and refuses without `--force`; even when forced, the failure mode is loud (health reports the ids unresolvable, §12.17).
- **`corpus forget-origin <id> <uri>`** handles the many-to-one provenance case: identical bytes accrue multiple origin aliases (§5.2); when one alias is wrong, this drops it without removing the record. Matched by identity key (§12.3.9), so a query-noise spelling still matches. Refuses when it is the record's only origin (that is an `rm`) and is a no-op when the uri isn't among the origins. An origin block whose every uri was forgotten is dropped; the edit appends a `corpus.forget-origin@` touch. It edits the tracked `.md` (git-recoverable), so it acts by default with `--dry-run` to preview — the asymmetry with `rm`'s dry-run default is deliberate (a tracked-text edit vs. irreproducible byte loss).
- **`corpus pack`** *(planned, 2.1)* — the inverse of promotion: consolidate standalone artifacts into a container (the container captured, ingested, and manifest-drafted; the members' blake3s unchanged), then prune the now-redundant standalone files once each member verifies as container-resolvable. No record changes — residence is invisible (§2). Until it lands, a standalone artifact whose blake3 is *also* container-resolvable is simply a redundant copy, not an orphan.
- **`corpus session <capture|list>`** bundles a Claude Code session — its `<id>.jsonl` transcript plus the `<id>/` sidecar tree (sub-agent transcripts, tool-result payloads, workflow state) — into ONE deterministic zip via the reusable writer core above (the first shipped consumer of the `pack` engine), then ingests and `zip-manifest`-drafts it so every member is a directly-addressed `path=<member>` embed (the transcript is never transcribed). It binds the `claude-code-session` producer-export origin (§7.2, uri-less, keyed on a `session_id` field); `--from [user@]host` sources a session from another machine over ssh/rsync. Sessions are personal (a transcript embeds every tool result verbatim) — they belong in a private corpus.
- **`corpus continuity <A> <B>`** proves whether record `A`'s addressable content is preserved in `B`: per `path=<member>` it is byte-identical, *contained* (A is a prefix B extends — the append-only case), *diverged*, or *absent*, and `contains_a` is true iff every unit is preserved. This is the supersession safety check — the *same* test answers "may B replace A?" (keep the more complete version: a re-captured session that grew supersedes its predecessor, while a compacted one must not clobber the fuller copy) and "may a citation of A be rewritten to B?" (`ath ledger supersede`, `ledger.md` §13.3). No synthetic stable id is minted: identity stays the blake3, and continuity carries citations forward only where the content survived.
- **`corpus capture --force --replace`** is a supersession ergonomic over `rm`: `--replace` (requires `--force`) snapshots the records holding the URL before the capture and, if the new bytes produced a different record id, retires the prior record(s) for that URL, reclaiming the old artifact bytes. When the bytes are identical, the capture folds into the existing record and nothing is retired.

### 12.9 Resolver surface and cache

A common resolver surface is a CLI that writes the materialized result to disk and prints its absolute path:

```
$ resolve 'corpus://<hash>?<params>'
/abs/path/to/cache/<shard>/<urihash>.<ext>
```

Conventional flags: `--regenerate` to bypass cache, `--json` to print a sidecar with derivation metadata. Library and HTTP-service surfaces are equally valid (§6.3).

The cache layout mirrors the sharding convention — `cache/<urihash[:2]>/<urihash>.<ext>`, where `urihash = hash(<canonical-uri>)`, with a `<name>.json` sidecar for JSON-valued ops so extensions can't collide. Cache invalidation is by deletion; eviction policy is implementation-defined (§6.4).

**The member index (2.1).** The route from a bare blake3 to its container (§2) is a derived map — `member transport hash → (container id, member address)` — built by walking every record's embed blocks, exactly as the URI index is built (§12.15 applies: rebuilt-on-start; persistence is a deferred perf optimization). Binary-store lookup falls back through it when no standalone file exists, recursing through nested containers, and the resolver cache absorbs hot paths — a member deep inside a solid compressed stream (a tgz) costs one streaming decompress on first touch and is cache-warm after. The promoted record's origin `uri:` (its containment lineage, §8.1) is **history, never consulted for byte lookup** — residence must stay free to change out from under it.

### 12.10 Export output layout

A common export layout writes one directory per exported record:

```
export/<record_id>/
├── <name>.md
├── <name>_001.<ext>
├── <name>_002.<ext>
└── ...
```

with the §10 embed-rewrite mapping each functional URI to a sequentially numbered local file.

### 12.11 Common address schemes (illustrative)

Media-type schemas declare their own address grammar (§4.3.2). Schemes that have proven useful in practice, as examples only:

| Axis | Example | Typical source |
|---|---|---|
| element | `el=<N>` / `el=<N>-<M>` | marked-up / HTML text (any element by 1-indexed position; output determined by the element — an `<img>` renders to an image, a `<video>`/`<audio>` or `<a href="data:…">` attachment carrier materializes to its raw bytes, a text element to its region) |
| page | `page=<N>` | paginated documents |
| block | `block=<N>` | block-structured documents without fixed pages |
| sheet | `sheet=<name>` (+ `bbox=<A1-range>`) | spreadsheets |
| time | `time=<tc>` / `time_range=<s>-<e>` | audio / video |
| frame | `frame=<tc>` | video stills |
| region | `bbox=<x>,<y>,<w>,<h>` | image crops (relative floats) |
| turn | `turn=<N>` | turn-structured transcripts / sessions |
| stream | `stream_id=<id>` | multi-stream media (composed onto another axis) |
| path | `path=<relpath>` | archive members (kept-whole archives: zip, tar/tgz) |
| message | `msg=<N>` | mailbox archives (mbox; 1-indexed). Extraction semantics — the `From ` delimiter convention and `>From ` un-stuffing variant — are pinned by the mime schema, so member bytes are deterministic and promotable (§8.1) |
| part | `part=<N>` | MIME message parts (email; 1-indexed addressable parts — every leaf part plus every nested `message/rfc822` as a whole, in depth-first pre-order — as CTE-decoded payload bytes; promotable per §8.1) |

Addresses compose with `&` (e.g. `page=<N>&bbox=<x>,<y>,<w>,<h>`); a single address or an ordered list (for non-contiguous spans, in reading order); query-reserved characters in a value are percent-encoded.

### 12.12 The concept knowledge base *(removed in 2.0)*

*Retired with the `concept` namespace (§4.3.3.4).* The local Wikipedia/Wikidata KB (Kiwix ZIM via `libzim`), `concepts.ConceptResolver`, the corpus-local `concepts/*.yaml` registry, and `corpus concept link` all retire from the corpus contract. External-authority identity is a ledger concern: a concept claims its `wikidata:Q…` id once, citing a mirrored reference dataset — where the local-mirror idea itself returns, as the `ref://` resolver (`ledger.md` §6.5).

### 12.13 Token counting

The `token_counts` view (§9.6) is computed with: text counted by a local BPE tokenizer approximating the target model's (an `o200k`-class vocabulary), lazy-imported behind an optional extra with a chars/4 heuristic fallback so the base library carries no tokenizer dependency; and an image-token estimate of `≈ min(width·height, 1,150,000 px) / 750` per image, from declared dimensions (`0` when absent). The tokenizer fetches its vocabulary on first use and caches it — warm the cache once for offline operation. Like every §9 view, the counts are never persisted to records; a search index may cache them per record (alongside size and segment count) for filtering and statistics.

### 12.14 Serving a corpus

No server is part of the corpus contract — a corpus is a directory of records, schemas, and caches, fully usable offline through the library and CLI (§1.5 principle 9). A serving layer may front one or more corpora — records, derived views (§9), artifact bytes, resolver output (§6) — over HTTP for browsing or search. It should remain a thin read surface that serializes what the library already produces, adding no parsing, derivation, or resolution logic of its own, and it never drafts, normalizes, or executes corpus-local code. Multi-corpus routing (mapping public ids to corpus roots) is a serving-layer concern; the tooling itself is single-root per invocation. One sharp edge: a functional-URI value passed through a URL query string must be fully percent-encoded.

### 12.15 Open implementation questions

Flagged for follow-up; not all are blockers.

- **Sharding crossover** (applies to both corpus and codex layers). When does single-level hex-prefix sharding stop being adequate — at what record count do we move to two-level (`a7/f3/…`)? Likely a tooling-driven flag declared in `corpus.toml` (corpus side) or `codex.yaml` (codex side), with tooling rebalancing on change; the codex layer defers to this entry (see `codex.md`).
- **URI index persistence.** The URI → `id` lookup (`records.build_uri_index`) is rebuilt-on-start from the records — the settled default (an in-memory query engine, not a data store). A persistent side-file is a deferred perf optimization, not an open design question.
- **Schema validation.** `corpus lint` validates *records*, not schemas; a `validate-schemas` command (`extended_fields` well-formed, `semantic_type` within the closed seven, no reserved `provenance` declared as a field, `capture.*` sections parseable) is still missing.
- **Multi-corpus capture.** When the same content needs to land in multiple corpora, capture is currently a copy step on top; a "capture into multiple corpora" mode is a possible future feature.
- **Segment-anchored mechanical references.** Overlay-declared reference emission is record-scoped today (§12.3.10), while §4.3.3.3 specifies a segment-pinned anchor (`address:`/`quote:`); closing the gap needs a reliable DOM→segment mapping.

### 12.16 The 2.0 migration (non-normative)

The migration story for the 1.0 → 2.0 contract change, recorded here because 10,000+ records conform to 1.0. Field inventory at the time of the change (public + private corpora): ~10,200 classify blocks, of which ~10,100 were `provenance: auto` (regenerable derivations); ~93 asserted classify blocks; ~146 interpretive `reference` blocks; ~77,000 `relation` blocks (mechanical in nature, asserted-labeled); zero `concept` blocks; zero `aside` blocks.

1. **Tooling alignment first.** The corpus tooling sheds the classify subsystem (the classify-block grammar, `classify_when` engine, `corpus classify`/`reclassify`, composite schema loading, the classifications view's composite rows, `classification-stale` lint, the concept resolver + `corpus concept`) before any record sweep, so lint and health define 2.0 conformance.
2. **Strip the derived.** All `provenance: auto` classify blocks are stripped in one sweep — they are derivations, re-mintable as ledger harvest output; nothing is lost.
3. **Harvest the asserted.** Asserted classify blocks and interpretive reference blocks carry real interpretation: they convert to ledger concepts/claims (the record rostered and cited as evidence) and capture needs respectively, as part of the ledger migration. Until the ledger exists, the extraction inventory is the migration's staging artifact.
4. **Schemas retire into rules and shapes.** Composite schema YAMLs leave `schema/` and become source material for harvest rules (`classify_when` → `match`, extraction scripts → `mint`), concept schemas and ledger `SCHEMA.md` conventions (domain shapes and guidance, `ledger.md` §4.4/§8), and origin-overlay guidance (body-shaping parts — notably the per-page-type guidance of large mechanical families).
5. **Relations relabel on re-draft.** 1.0-era relation blocks relabel to `provenance: auto` as origin-declared lifting (`capture.relations`) lands in the drafter; until then they are grandfathered as-is (§4.3.3.5 migration note).

### 12.17 The 2.1 containment amendment (non-normative)

Migration story: **zero existing records change shape.** Records never carried `artifact_kind` (it was schema-side); the only bundled `decomposable` schema (raw `application/zip`) flips to the `zip-manifest` strategy and `_ingest_decomposable` retires. Records minted by past decomposable ingests are ordinary standalone records and stay exactly as they are — promotion is additive, a second residence for bytes, not a new record shape. Schemas still declaring `artifact_kind` are ignored (tolerant parsing) and swept at leisure.

Tooling alignment order, mirroring §12.16's tooling-first discipline:

1. **The member index + store fallback** land in the resolver/store layer (§12.9), so a bare blake3 resolves through containment before anything mints records that depend on it.
2. **`health` redefines "missing"** as *unresolvable by any route* — standalone or containment (`missing_artifacts` consults the member index). Deep byte-verification of container members (streaming re-hash against embed `transport:` hashes) is an explicit verb, not a default check.
3. **`corpus promote`** mints member records (§8.1), verifying streamed bytes against the embed's recorded hash before writing the stub.
4. **The zip default flips** (raw archives stop exploding; tar/tgz gains a manifest drafter + `path=` transform).
5. **`corpus pack`** (consolidation, §12.8) follows when a corpus wants it — e.g. folding thousands of sibling standalone files into a handful of taxonomy archives with no record edits.

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
| **Embed block** | `<!--embed <mime-type>-->` — content-addressed asset metadata. Deduplicated by `transport:`. |
| **Section block** | `<!--section-->` — structural grouping; the TOC unit. Contains zero or more segments. |
| **Segment block** | `<!--segment <atom>-->` — the body's content atom. |
| **Context block** | `<!--context <namespace>/<id>[/<subtype>]-->` — an annotations-zone observation (namespaces: `issue`, `reference`, `relation`, …); record- or segment-scope (via `address:`). |
| **Namespace** | One of `mime`, `origin`, `atom`, `context`. Each is a schema axis or umbrella with its own block-keyword role. |
| **Provenance** | On a context block (§4.4.6): `provenance: auto` = engine-stamped (a detector or overlay-declared emission), stripped and regenerated on re-run; absent or `asserted` = human/normalizer, never auto-touched. |
| **Self-contained** | The universal container disposition: every transport produces a single record (lifting nested-stream metadata when present). A raw archive drafts as an embed manifest of its members. *(2.1: the former schema-declared `decomposable` disposition is removed.)* |
| **Container / member** | A container is an artifact whose content is other transports (an archive); a member is one such contained transport, declared as a content-addressed embed on the container's record. |
| **Promotion** | Minting a first-class record for a container member without copying its bytes: the promoted `id` is the member's blake3, resolved by streaming through the container (§2, §8.1). |
| **Mode** | A mime schema's drafting behavior: `extract-only` or `body-draft`. |
| **Capture, Ingest, Draft, Normalize** | Pipeline stages. |
| **Touch** | A single processing pass. Recorded in `touch[]`. |
| **Touch chain** | The ordered list `touch[0..N]`. Records current-shape provenance; reset by re-stub (§8.4). |
| **Re-stub** | A deliberate reset that discards body and accumulated metadata, leaving only byte-intrinsic state and the touch chain. See §8.4. |
| **Resolver** | The corpus-provided mechanism that materializes a functional URI to a deterministic result. |
| **Functional URI** | A `corpus://<hash>?<params>` URI naming a derived view. |
| **Derived view** | A computed aggregate over body blocks / semantic-tagged fields. |
| **Semantic type** | One of seven closed-vocabulary tags on schema-declared fields. |
| **Transport hash** | `transport:` — the bytes-level hash of the file. Encoded as `<algo>:<hex>`. |
| **Canonical hash** | `canonical:` — the canonicalized-content hash. *(Currently not persisted — disabled 2026-06-28, see §7.1.)* |
| **Perceptual hash** | `perceptual:` — atom-canonical content fingerprint. |

---

## Appendix B: Content types (non-normative)

A curatorial vocabulary for the content **sources** a corpus is expected to hold, and how each maps onto the model. These are planning terms, not schema fields: they inform capture planning, and become ledger types (`ledger.md` §8) wherever a distinction is worth recording.

### B.1 Source taxonomy

| Family | Kinds |
|---|---|
| **Website** | news article · forum post / thread · opinion / editorial · blog post · reference article (Wikipedia / wiki) |
| **Print** (physical / electronic) | fiction · non-fiction · textbook · reference manual · script / screenplay · research paper |
| **Audio-visual** | video (e.g. YouTube) · podcast · television · feature film · documentary |

### B.2 How a content type lands in the corpus

There is **no per-content-type metadata schema** and no "document kind" field. A content type expresses itself through three orthogonal mechanisms:

1. **MIME type** (`mime` namespace, §7.1) — the artifact's media type (`text/html`, `application/pdf`, `application/epub+zip`, `video/mp4`, …) selects the drafter, the addressing scheme, and the canonicalization strategy. A "research paper" is just an `application/pdf` artifact; a "blog post" is `text/html`.
2. **Ledger assertion** (`ledger.md`) — *what kind of thing* an artifact documents, and any domain signal worth recording (e.g. a `peer-reviewed` / `preprint` credibility signal), is asserted as typed claims whose evidence cites the record — minted mechanically by harvest rules where membership is deterministic (`ledger.md` §10). This replaces per-document enum metadata fields entirely. *(1.0 expressed this as corpus-side composite classifications.)*
3. **Origin** (`origin` namespace, §7.2) — capture provenance: source URL(s), capture timestamp, per-host capture recipe. "Where it came from" lives here.

Backlog growth, grooming, and prioritization of what to capture are **curatorial** concerns owned by the layers above the corpus — the ledger's needs and coverage gaps generate ingestion demand (`ledger.md` §7, §9) — not corpus-pipeline stages.
