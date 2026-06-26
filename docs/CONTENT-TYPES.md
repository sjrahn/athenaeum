# Content Types

A *curatorial planning* enumeration of the content **sources** a corpus is expected to hold,
and how each maps onto the ATH-CORPUS v1.0 model. This file is planning scaffolding, not a
contract — the normative record format lives in [`spec-corpus.md`](../spec-corpus.md) and the
pipeline mechanics in [`impl-corpus.md`](../impl-corpus.md). It enumerates the source taxonomy
and points at the model rather than restating it.

> Earlier revisions of this file described a pre-v1.0 model — a per-document `Credibility`
> enum, a `Normalization Confidence` number, and a `/sources/` + `/manuscript/` +
> `relations.toml` ingestion workflow. That model, and the Rust stack that implemented it,
> was retired. None of it survives in v1.0; the sections below are the current mapping.

## Source taxonomy

A planning vocabulary for *what kinds of things* a corpus collects. In v1.0 these are **not**
schema fields — they inform capture planning, and become **classifications** (spec §4.4)
wherever a distinction is worth recording.

### Website
- News article
- Forum post / thread
- Opinion / editorial
- Blog post
- Reference article (Wikipedia / wiki)

### Print (physical / electronic)
- Fiction
- Non-fiction
- Textbook
- Reference manual
- Script / screenplay
- Research paper

### Audio-visual
- Video (e.g. YouTube)
- Podcast
- Television
- Feature film
- Documentary

## How a content type lands in the corpus (v1.0)

There is **no per-content-type metadata schema** and no "document kind" field. A content type
expresses itself through three orthogonal mechanisms:

1. **MIME type** (`mime` namespace, spec §7.1) — the artifact's media type (`text/html`,
   `application/pdf`, `application/epub+zip`, `video/mp4`, …) selects the drafter, the
   addressing scheme, and the canonicalization strategy. A "research paper" is just an
   `application/pdf` artifact; a "blog post" is `text/html`.
2. **Classifications** (spec §4.4; `composite` namespace §7.4) — stackable, schema-declared
   labels record *what kind of thing* an artifact is and any signal worth capturing (e.g. a
   codex-defined `peer-reviewed` / `preprint` credibility-**signal** classification, surfaced
   as a derived view). Classifications replace the old enum metadata fields entirely.
3. **Origin** (`origin` namespace, spec §7.2) — capture provenance: source URL(s), capture
   timestamp, per-host capture recipe. "Where it came from" lives here.

## The record (v1.0) — anatomy by reference

Each artifact has exactly one **record** (its markdown proxy). In brief — see
[`spec-corpus.md`](../spec-corpus.md) §4 for the authoritative shape:

- **Frontmatter** (§4.2, ≤9 fields) — `id` (blake3 of the artifact bytes), `title` +
  `description` (the keys are always present but empty until `status: normalized`), `status`
  (`stub`/`draft`/`normalized`), the optional `transport`/`canonical`/`perceptual` hashes,
  `touch` (per-pass provenance), `visibility`.
- **Body blocks** in three zones (§4.3): *metadata* (`artifact` — exactly one, MIME plus
  provenance-namespaced fields, with **no** generic `title`/`credibility`/`norm_conf`;
  `origin`; `classify`; `embed`), *content* (`section` / `segment` — the artifact decomposed
  into addressable segments, each one atom of text/image/audio/video plus an address, §1.3),
  and *annotations* (`context` — `concept` Wikipedia joins, `reference` citations, and
  surfaced issues, §4.3.3).

## Pipeline (v1.0) — by reference

`capture` → `ingest` (blake3 content-address + MIME detect → stub) → `draft` (the MIME schema
segments the content zone, emits embeds, sets `canonical`; mechanical classifications fill
`classify` blocks) → `normalize` (an LLM authors `title`/`description`, may re-segment, fills
interpretive classifications, surfaces issues). Records are stored content-addressed at
`records/{first-2-of-id}/{full-id}.md`; `corpus lint` checks shape. See spec §8 /
[`impl-corpus.md`](../impl-corpus.md) for the stage mechanics and the deterministic ↔ LLM
boundary.

Backlog growth, grooming, and prioritization are **curatorial** concerns owned by a codex's
expert agent (the layer above) — not corpus-pipeline stages. See
[`impl-codex.md`](../impl-codex.md).
