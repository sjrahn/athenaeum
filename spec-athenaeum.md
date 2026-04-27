---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 10.15
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-04-27
changelog:
  - version: 10.15
    date: 2026-04-27
    summary: >
      Refinement pass O. §4 (Pipeline) and §5 (Pipeline Agents) trimmed to
      data and output contracts; the procedural recipes (capture sub-steps,
      normalize sub-steps, build mechanics) move to `impl-corpus.md` and
      `impl-codex.md`. §4 collapses to a single per-step bullet list with
      the contract for each step; phase-boundaries table renumbered §4.6
      → §4.1 as the meta summary of independently re-runnable operations.
      §4.1 staging / reconciliation, §4.2.1 conversion sub-step, §4.2.2
      cross-reference-resolution sub-step, and §4.2.3 contextualization
      sub-step are gone from the spec body. §4.5 Build collapsed into the
      per-step bullet list; the per-layer build-target enumeration is
      preserved but the step-by-step "how" recipe is gone. §5 keeps each
      agent's model-class / scope / output contract; the procedural
      detail and the redundant pointer to §5.7 are stripped from §5.3
      Normalizer. §5.4 Author output contract updated to reference the
      v10.14 reference primitives (footnote citations, functional-URI
      embeds, intra-codex wikilinks). impl-corpus.md and impl-codex.md
      remain canonical for "how"; this commit confirms that.
  - version: 10.14
    date: 2026-04-27
    summary: >
      Refinement pass N. Reference syntax overhaul plus §3 frontmatter rework.
      Three reference primitives, each scoped to one job: wikilinks `[[id]]`
      are intra-layer only (artifact body → another artifact in the same corpus;
      codex body → another codex record in the same codex; compendium body →
      another compendium record in the same compendium); footnote citations
      `text[^N]` with `[^N]: corpus://hash` (or `codex://name/uuid`) at the
      bottom of the record are the cross-layer downward-citation form, with the
      bare URI in the footnote body resolved to APA-style at build/export;
      embeds `![[corpus://hash?params]]` are cross-layer functional URIs that
      always target an artifact (codex records are wikilinked, never embedded).
      Artifact-body embeds keep raw `![[blake3]]` for intra-corpus cross-refs.
      Functional URI scheme renamed `blake3://` → `corpus://` (generic,
      layer-named); a parallel `codex://name/uuid` URI is the codex-citation
      form for compendium footnotes. §3.1.1 Core Fields collapses `blake3` and
      `uuid` rows into a unified `id` field whose shape varies per layer
      (blake3 hash for artifacts, UUIDv7 for codex records, author-chosen
      slug for compendium records). `visibility` scoped to artifact records
      only. §3.1.2 drops `normalization_type`, `author`, and `date_published`
      (the latter two surface via classification schemas when relevant).
      §3.1.3 codex-record frontmatter restated as just `id`, `title`,
      `description`, `status`, `tags`. §3.1.4 (Quality Fields) and §3.1.5
      (Pipeline Fields) deleted entirely as pipeline-state metadata not data
      contract; absorbed into impl-corpus.md as tracking-metadata for re-run
      targeting. Prior §3.1.6 (Issues) and §3.1.7 (Extended Fields) renumber
      to §3.1.4 and §3.1.5. §3.2 reordered: §3.2.4 is now "Codex-Record
      Bodies" (the intro), §3.2.5 is "Inline Topic Annotations" (sub-aspect
      of codex bodies). §3.2.6 / §3.2.7 rewritten for footnote citations;
      codex-to-codex connections drop the embed bullet (codex records are
      wikilinked). §3.6 retitled "Reference Resolution" (covering all three
      primitives, not just wikilinks) and rewritten with one resolution rule
      per primitive. §3.7 renames the scheme `blake3://` → `corpus://` and
      adds `codex://name/uuid`. §3.4 examples reworked (`id:` field, UUIDv7
      example, footnote citations, `corpus://` URIs). §6.2 / §6.3 / §6.5
      compendium prose updated for footnote-citation form. §1.3 terminology
      revised: Wikilink, Embed, Reference, UUID, Functional URI entries
      reflect the new model; Footnote Citation entry added.
  - version: 10.13
    date: 2026-04-27
    summary: >
      Refinement pass M. §1 cleanup and layer-purpose framing. §1.1 drops the
      strict-downward diagram and the runtime-resolution paragraph (both pre-empted
      vocabulary the reader hadn't met yet) and leads with the three layers' purposes:
      the corpus is the foundation (truth, baseline); the codex is where knowledge is
      decomposed and organized (where connections are built and signals emerge for
      new captures); the compendium is the funnel that focuses the knowledge graph
      on a topic. §1.2 design principles renumbered and reordered: principle 1 is
      now "Layered foundation" (absorbing the prior principle 6 "Strictly downward
      references"); principles 2–8 follow the prior order with the strict-downward
      content folded into 1; principle 9 reframed from "LLM-native" to
      "LLM-informed" (the LLM mechanics live in the impl docs now, the spec is
      shaped by what LLM agents can produce reliably); principle 10 unchanged
      (offline-first). Stable-identity principle (now 8) updated to mention the
      unified `id` field foreshadowed in refinement N. Cross-references "principle
      6" → "principle 1" updated in §1.3 terminology and §2.3 codex records.
      Pure prose cleanup; no semantic changes.
  - version: 10.12
    date: 2026-04-26
    summary: >
      Refinement pass L. Migratory prose removed throughout the spec body and
      impl docs. The spec now describes the present-tense system; references
      to dropped concepts (constituents, part_of, is_a, same_as, merge DAG /
      ceremony / rationale, the v10 invariant framing, the prior
      slug-preserving regen approach) and meta-version phrasing ("in v10",
      "no longer", "the previous") are gone where they served no purpose for
      a fresh reader. Specifically: §1.2 principle 5 drops the "no stored
      constituents/part_of/is_a/same_as" tail; §2.2 re-capture paragraph
      reframes "no automatic mechanism in v10" as a present-tense out-of-band
      concern; §2.4 layered-graph intro drops the "no constituents list, no
      part_of field, no merge DAG metadata" tail; §2.4 strictly-downward
      bullet drops "the v10 invariant"; §3.1.1 record-type-signaling reframed
      from "no dedicated record_type field" to a positive three-signal list;
      §3.1.3 drops the "no constituents/part_of/same_as/is_a" sentence;
      §3.2.7 drops "no stored structural relations"; §3.3.2 composition drops
      "no separate tags field on artifacts"; §3.5 / §3.5.1 / §3.5.2 / §3.5.3
      reframed positively (Tags section opens with codex-record scope rather
      than absent-on-artifacts, codex-graph drops "not through frontmatter
      relations", dedup drops "not through stored relations"); §3.7
      functional-URI scheme reframed positively (codex / compendium primitive,
      no "not used in artifact bodies" defensive negative); §4.3 Author drops
      "no merge ceremony, no constituent list, no merge rationale field";
      §4.2.3 / §5.3 normalizer output contracts drop "Artifacts do not carry
      frontmatter tags" defensive notes. impl-codex.md §3 (Compendium
      directory layout) reframed positively; §4.1 Save step drops "no
      codex-record-side credibility field" framing in favour of stating the
      compendium-side weighting model directly; §5.2 drops "no codex-side
      variations"; §6.3 strips the "previous slug-preserving approach"
      commentary that explained the v10.7-series design choice — the spec
      describes what it is, not what it isn't anymore. Pure prose cleanup;
      no semantic changes.
  - version: 10.11
    date: 2026-04-26
    summary: >
      Refinement pass K. Closing structural cleanup. (1) §1.2 design principles
      renumbered to a clean 1–10 (the dropped principle 11 from refinement I
      already left a gap; the inserted principle 6 had been numbered 10; the
      remaining principles 6–9 had been numbered 6–9 out of order). (2) §4.5
      Build rewritten to enumerate the three layers (corpus / codex /
      compendium) as independent build targets — each layer is exportable for
      viewing on its own. Per-layer build descriptions added; the previous
      corpus-centric framing is gone. (3) Strictly-downward-references rule
      cross-referenced rather than restated: §1.1 layered-architecture prose
      tightened (drops the standalone "Codices reference downward only"
      assertion and the closing "References point downward only" sentence,
      replacing them with a pointer to §1.2 principle 6 and §2.4); §1.3
      terminology Reference entry shortened to a cross-reference; §2.3
      tightened to point at §1.2. (4) §3.3.4 MIME table replaced with a
      one-paragraph cross-reference to Appendix A.1 (which has the richer
      Notes-column version); the per-row table is no longer duplicated.
      (5) impl-corpus.md §6 sharding-crossover question reframed to apply to
      both corpus and codex sides, with `impl-codex.md §8` deferring to it
      as canonical. impl-codex.md §8 sharding entry rewritten as a
      cross-reference. No semantic changes; pure structural cleanup.
  - version: 10.10
    date: 2026-04-26
    summary: >
      Refinement pass J. Tags become a pure codex-record concept; artifact
      records and compendium records no longer carry frontmatter `tags`.
      Artifact classification is recorded entirely in the `classifications:[]`
      audit trail (every applied custom classification schema is logged with
      a justification, and the schema's contributed extended fields merge
      into top-level frontmatter). The schema-application *is* the artifact-
      side classification signal — there's no parallel tag list. Inline
      `%% #tag %%` annotations are restricted to codex-record bodies (§3.2.4
      rewritten); artifact bodies, which must remain faithful to original
      content, no longer permit them. §3.1.1 `tags` row scoped to "codex
      records only"; §3.5.1 rewritten for codex-only tags; §3.4 example
      artifact frontmatter has its `tags:` line removed. §3.3.2 schema YAML
      drops `classification.add_tags`; the `has_tags` match condition is
      renamed `has_classifications` (a schema gates on prior schema
      applications, not on artifact tags). §3.3.2 composition rule, audit
      trail prose, layered-matching prose, and examples all updated. §4.2.3
      and §5.3 normalizer output contracts no longer mention "the resulting
      tags" — artifacts emit extended fields and classification entries.
      Appendix A.2 examples have their `add_tags` blocks stripped (the
      schema name itself is the signal); `has_tags: [forum-thread]` in the
      community-validated / anecdotal-claim schemas becomes
      `has_classifications: [forum-thread]`. impl-corpus.md §3.3, §3.4,
      §4.1 (Tag clusters → Classification clusters), §4.2 schema-authoring
      YAML, §4.3, §5.2 all updated. Codex-side tag handling unchanged.
  - version: 10.9
    date: 2026-04-26
    summary: >
      Refinement pass I. Slugs dropped entirely. The "regen-safe codex
      citation" goal — that compendiums citing `[[codex-name:slug]]` could
      survive codex regeneration — is replaced with the simpler invariant:
      **codex regeneration invalidates dependent compendiums**, which must be
      re-built. This drops the entire slug mechanism and tightens the model.
      §3.6 retitled "Wikilink Resolution" and rewritten as the single canonical
      per-container resolution algorithm (artifact body → blake3 only; codex
      record → blake3 + uuid; compendium record → blake3 + corpus-name:blake3
      + codex-name:uuid). §3.6's prior slug-stability and slug-renaming prose
      removed. §1.2 design-principle 11 ("Reference stability hierarchy")
      dropped — without slugs it collapses into principle 10. §1.3 terminology
      removes Slug and Codex Topic entries; Wikilink and Compendium entries
      tightened to the new wikilink shapes. §2.3 / §2.5 / §3.1.1 / §3.1.3 /
      §3.2.4 / §3.2.5 / §3.4 example / §4.3 / §4.5 / §5.4 / §6.x scrubbed of
      `slug` field references and `[[codex-name:slug]]` wikilinks; codex
      citations now use `[[codex-name:uuid]]`. §3.2.4 inline-annotation syntax
      label corrected from `%% #slug %%` to `%% #tag %%`. §6.5 rewritten with
      explicit "codex regeneration invalidates dependent compendiums" rule.
      impl-codex.md §3 (Slug-as-topic conventions) deleted wholesale; §4.1
      and §4.2 scrubbed; §5.2 replaced with cross-reference to spec §3.6 plus
      implementation notes; §5.4 collision detection trimmed; §6 codex-
      regeneration rewritten with explicit compendium-cascade discipline;
      §8 open questions pruned of slug-related items. impl-codex.md sections
      renumbered: deleted slug §3 closes the gap, new compendium-layout
      section becomes §3, others (§4–§8) unchanged.
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

The system has three layers, each with a distinct purpose:

- **The corpus is the foundation.** It is the truth, the baseline — a content-addressed archive of captured artifacts, faithful to what was captured. The corpus is the unit of tenant isolation; a "private" corpus and a "public" corpus are separate corpora, and their content should be mutually exclusive.

- **The codex is where knowledge is decomposed and organized.** It is where connections are built across the corpus, where the signals emerge that drive the next capture, and where authored interpretation lives.

- **The compendium is the funnel.** It takes the codex's knowledge graph and focuses it on a topic, producing a concise, targeted reference work richly built up from the corpus's foundation.

### 1.2 Design Principles

1. **Layered foundation.** The corpus is the foundation, fully independent of the layers above it. Codices depend on corpora; compendiums depend on codices and corpora. References point downward only — a layer's records know nothing about layers above them. Codex regeneration triggers compendium re-build (compendium references into a codex are tied to that codex's current instance), and that is the intended behavior.

2. **Every record is independently valid.** A single captured page and a fully synthesized monograph are both complete, addressable, useful markdown documents.

3. **Artifact immutability via content addressing.** Captured artifacts are identified by the blake3 hash of their binary content. The bytes never change; if they did, the hash would change and the record would be a different record. Re-encountering the same bytes appends a new entry to the existing record's `capture_dates` rather than creating a new record.

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
| **Tag** | A flat, kebab-case classification label matching `[a-z0-9]+(-[a-z0-9]+)*`. Tags are codex-local — they live on codex records only. Artifact records classify via the `classifications:[]` audit trail; compendium records organize by chapter structure. |
| **Capture** | An encounter event recorded only by date. Re-encountering identical bytes appends a new entry to the artifact's `capture_dates`; the bytes themselves never move and never produce a new record. |
| **Normalization** | Producing the artifact's text body — extraction (HTML→markdown, PDF→text), transcription (audio/video→text), description (image→text), or metadata summary (opaque binary). Faithful to the original. |
| **Functional URI** | A composable URI scheme used in codex and compendium bodies. `corpus://{hash}` references an artifact (whole, by anchor `#section`, or by transformation `?page=4&crop=…`); `codex://{name}/{uuid}` references a codex record from a compendium footnote. Resolved at compile/render time. |
| **Schema** | A reference document describing how to normalize or classify content. Two kinds: **base schemas** (MIME-type-keyed, universal, foundational data contract) and **custom classification schemas** (corpus-local, optional, corpus-author-driven). |

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

Compendium-record filenames are an authoring choice (e.g., `01-introduction.md`, `02-history.md`) — chapter-style names rather than the content-addressed hashes of artifact records or the UUIDs of codex records. See §6.

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

**Re-capture of changed content.** If a captured URL is later re-fetched and returns different content, the new content produces a different hash and therefore a new artifact record. Both records list the URL in their `uris[]`, making them discoverable as captures of the same origin URL at different points in time. Cross-URI succession — recognising that the same content has moved to a new URL — is an out-of-band concern, not something the artifact record asserts.

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

The schema library (`schema/`) provides normalization and classification guidance (see §3.3); extended fields beyond the core schema are tolerated freely (see §3.1.5). Appendix A provides a concise per-MIME field reference.

#### 3.1.1 Core Fields

Present on every record (unless noted as record-type-specific).

| Field | Type | Required | Applies to | Description |
|-------|------|----------|------------|-------------|
| `id` | string | yes | all | Record identifier and filename stem under the container's `records/` directory. **Artifact:** the blake3 hash of the binary content, 64-character lowercase hex. **Codex record:** UUIDv7 (RFC 9562, time-ordered, monotonic-by-creation). **Compendium record:** author-chosen slug matching `[a-z0-9]+(-[a-z0-9]+)*`. |
| `title` | string | yes | all | Short descriptive label. |
| `description` | string | yes | all | 1–3 sentence description. Primary mechanism for discovery and relevance assessment. |
| `content_type` | string | yes (artifacts) | artifact records | IANA MIME type of the captured artifact (e.g., `text/html`, `application/pdf`, `image/jpeg`). `unknown` is permitted as a sentinel when the MIME cannot be determined. Codex records and compendium records are markdown by construction and do not carry `content_type`. |
| `status` | enum | yes | all | Pipeline state: `stub` (captured, no body), `draft` (converted, body filled), `normalized` (LLM-refined, ready for use). Codex records and compendium records typically begin at `draft` since authoring fills the body directly. |
| `visibility` | enum | no | artifact records only | Editorial curation layer for artifacts, independent of `status`. One of `visible` (default), `deranked` (appears in results at lower priority), `hidden` (excluded from default results, still accessible by direct identifier). Lets a curator retire low-quality artifacts (low-content pages caught in a bulk scrape, superseded captures, flagged-for-review) without deleting them. Codex and compendium records are deleted or rewritten rather than retired. |
| `tags` | string[] | no | codex records only | Classification tags. Kebab-case, lowercase, matching `[a-z0-9]+(-[a-z0-9]+)*`. Declare what this codex record is about. Tags are codex-local — a codex MAY define a tag vocabulary in its `codex.yaml` or a conventions file for consistency. Frontmatter tags declare whole-record topical coverage; inline `%% #tag %%` annotations (§3.2.5) provide positional precision within the body. |

Artifact classification is recorded in the `classifications:[]` audit trail (§3.1.2, §3.3.2); compendium-record organization is the author's chapter structure.

**Record type signaling.** A record's type is determined by three independent signals that always agree:

- **Container**: artifacts live in a corpus's `records/`, codex records in a codex's `records/`, compendium records in a compendium's `records/`.
- **`id` shape**: 64-character lowercase hex blake3 hash for artifacts, UUIDv7 for codex records, author-chosen slug for compendium records.
- **Required field presence**: `content_type` on artifacts; codex and compendium records have neither `content_type` nor visibility.

#### 3.1.2 Artifact-Specific Fields

Present only on artifact records.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uris` | string[] | yes (≥1) | All known URIs that resolve to this artifact's bytes. None canonical — request URLs, redirect targets, mirror URLs, DOIs, IPFS CIDs, `file://` paths are all equivalent labels. URIs may be added at any time (e.g., a DOI assigned later, a mirror discovered) and become valid retroactively for the artifact. |
| `capture_dates` | ISO-8601[] | yes (≥1) | Timestamps at which these bytes were encountered. Re-encountering identical bytes appends a new entry. |
| `hashes` | map | no | Per-artifact instances of the cryptographic and perceptual hashes the base schema (§3.3.1) declares for this MIME. blake3 is the artifact's `id`; other declared hashes (e.g., `chromaprint`, `phash`, `sha256`) live here. |
| `classifications` | object[] | no | Audit log of custom classification schemas applied to this artifact. Each entry is `{schema, justification}`; see §3.3.2. The schemas' contributed extended fields merge into top-level frontmatter (this array does not duplicate them). Absent when no custom classifications have been applied. |

Example artifact frontmatter fragment:

```yaml
id: "a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."
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
```

The same bytes encountered twice append a new entry to `capture_dates` — they never produce a second record. New URIs discovered for already-captured bytes are appended to `uris[]` whenever they're discovered, including long after the original capture.

Author identity, publication dates, and similar provenance attributes surface as extended fields contributed by base or custom classification schemas (e.g., a `web-article` schema contributes `byline` and `published_date`; an `epub` base schema contributes `epub_author` and `pub_date`). They are not core fields.

#### 3.1.3 Codex-Record-Specific Fields

Present only on codex records.

Codex-record frontmatter is deliberately thin. The complete set of frontmatter fields on a codex record is the core fields `id`, `title`, `description`, `status`, `tags` — and that is it. No `content_type` (codex records are markdown by construction), no `visibility`, no quality or pipeline metadata. Structural relationships are body references — wikilinks to peer codex records, footnote citations of artifacts, functional-URI embeds — and computed similarity (see §3.5). The body is the authoritative record of what knowledge the codex record synthesizes and what evidence it draws on.

Credibility, when relevant, is consulted by reading the credibility-signal classifications on the evidentiary artifacts the codex record cites (§3.3.2, Appendix A.2). The codex record itself carries no credibility field.

Compendium records carry the same minimal core fields as codex records (excluding `tags`); they organize by chapter structure rather than tag classification.

#### 3.1.4 Issues

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

#### 3.1.5 Extended Fields

Records may carry frontmatter fields beyond those in §3.1.1–§3.1.4. Extended fields come from two sources:

- **Base schema extraction.** Format-intrinsic fields read from the artifact's binary (file headers, embedded metadata). Examples: `page_title` and `meta_description` for HTML, `duration_seconds` and `bitrate_kbps` for audio, `width_px` and `height_px` for images, `page_count` for PDFs. The base schema for each MIME type defines which fields the normalizer extracts (see §3.3.1).

- **Custom classification schema extraction.** Domain-specific fields added when a custom classification schema (§3.3.2) matches the record. Examples: `artist`, `album`, `track_number` when an audio file's ID3 tags identify it as a musical recording; `service_section`, `vehicle_platform` when a PDF is recognized as a service manual page. Custom classification schemas are corpus-local and corpus-author-driven.

Extended fields are tolerated by the core loader but not required. A record carrying only the base-schema fields its MIME yields is fully valid — classification can be deferred to a later pass.

If a field is genuinely required for a kind of content the corpus cares about, the strongest practice is to author a custom classification schema that declares the requirement and applies to matching artifacts; the resulting `classifications:[]` entry is the discoverability signal.

### 3.2 Body Format

The body of a record is the markdown content below the frontmatter closing `---`. The rules differ sharply between artifact bodies and codex-record bodies. Compendium-record bodies follow the codex-record body conventions (with the added freedom of cross-codex / cross-corpus citation forms; see §6).

#### 3.2.1 Artifact Body Integrity

An artifact's body is a faithful normalized rendering of the original content. The normalizer MUST NOT add editorial content, interpretation, or connections that did not exist in the original. The body mirrors the original's structure: its headings, paragraphs, lists, links, and embedded media, translated into markdown.

#### 3.2.2 Cross-Reference Resolution

The original content's hyperlinks and embedded resources are resolved during normalization to **intra-corpus** wikilinks and embeds. The reference is layer-local — within the same corpus — so the raw form is used; no scheme prefix is needed:

- **Captured target exists in corpus:** Replace the URL with a raw blake3 wikilink or embed.
  - Hyperlinks become wikilinks: `[[{blake3}|original link text]]`
  - Embedded images become embeds: `![[{blake3}]]`
  - Embedded media become embeds with alt text: `![[{blake3}|description]]`

- **Captured target does not exist:** Leave as a standard markdown URL: `[link text](https://original-url.com)` or `![alt](https://original-url.com/image.jpg)`. The link is unresolved — it points outside the corpus. If the target is captured later, a re-normalization pass can resolve it.

Cross-reference resolution is the *only* way artifacts link to each other. No artifact body contains wikilinks or embeds that the normalizer invented — every link corresponds to a link or embed in the original content.

Wikilinks SHOULD use the full 64-character blake3 hash. Tooling MAY accept unambiguous hash prefixes for human-edited contexts, but generated artifact bodies use the full hash.

#### 3.2.3 What Embeds Mean

In an artifact body, `![[blake3]]` is an intra-corpus raw embed (§3.2.2): it mirrors a captured target's appearance in the original content. Obsidian renders the target artifact's normalized body inline at that position; for an image artifact, that means OCR text and visual description appear where the original image was.

In codex- and compendium-record bodies, embeds are functional URIs targeting an artifact: `![[corpus://{hash}?params]]`. The `params` may transform the artifact (page extract, framegrab, crop); a bare `![[corpus://{hash}]]` is the identity transform. Codex records are not embedded — they are wikilinked or footnote-cited.

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

Inline annotations are valid only in codex-record bodies. Artifact bodies remain faithful to the original content (§3.2.1); their classification lives in the `classifications:[]` audit trail (§3.1.2, §3.3.2). Compendium-record bodies organize by chapter structure.

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

Custom classification schemas are optional. A corpus author authors them to recognize content patterns and extract domain-specific extended fields beyond what the base schema gives. The spec defines the schema format and the composition rules; it does **not** dictate which schemas a particular corpus should have.

Custom classification schemas live in the corpus's `schema/classification/` directory. They are portable with the corpus but are not universal — different corpora carry different custom schemas reflecting their own concerns.

**Match conditions.** A schema's `match` block declares the conditions under which it applies. Any of these condition types may be combined; all listed conditions must be satisfied for the schema to match:

- **`content_type`** — exact MIME match or MIME-prefix match (e.g., `audio/*`).
- **`uri_pattern`** — a regex evaluated against any entry in the artifact's `uris[]`. A typical use is matching a domain (e.g., `^https?://[^/]*example\\.com/`).
- **`has_classifications`** — list of schema names the artifact must already carry in its `classifications:[]` audit trail (i.e., the listed schemas have already been applied).
- **`field_match`** — required values for already-extracted extended fields (e.g., `pdf_producer: "TexLive"`).

A match is a logical AND across the listed conditions. To express disjunction, author multiple schemas — they compose naturally (see below).

**Schema document format.**

```yaml
schema_type: classification
match:
  content_type: "audio/mpeg"
  has_classifications: []                       # optional
  uri_pattern: ""                               # optional
  field_match:                                  # optional
    # field_name: required_value

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

**Composition.** The normalizer applies the base schema first (format extraction, declared hashes, base-schema fields). It then evaluates all custom classification schemas in the corpus; every schema whose `match` is satisfied contributes its `extended_fields` to the artifact and adds an entry to the artifact's `classifications:[]` audit trail (with required justification). Multiple schemas may match — their fields merge (last-write-wins on collision). The schema's *application* — the entry in `classifications:[]` — is itself the artifact-side classification signal.

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

The array does **not** duplicate the schema's contributed fields — those live in the merged top-level frontmatter per the composition rule above. The array is purely the log of *which schemas applied and the reasoning for each*. Field provenance ("which schema contributed `thread_id`?") is reconstructed by walking the schemas referenced in `classifications:` against their declarations — the schema files are the source of truth for what each schema contributes.

**Layered matching.** Because a schema's match conditions can include `has_classifications`, a schema can layer on top of an earlier match. A general-platform schema might apply (recording itself in `classifications:[]`) and add a few generic fields; a more-specific schema gated on `has_classifications: [video-platform-x]` plus a `uri_pattern` can then add fields specific to a particular show or section of that platform. This is how a corpus grows from coarse to fine classification without duplicating match logic.

**Examples (illustrative — concrete schemas are corpus-author choices).**
- An artifact captured from a video-hosting platform: a domain-keyed schema (e.g., `video-platform-x`) records itself in `classifications:[]` and adds `upload_date`, `like_count`, `channel_name`, `view_count`.
- An artifact from a specific recurring show on that platform: a layered schema (`has_classifications: [video-platform-x]` + a channel-specific `uri_pattern`) adds `episode_date`, `hosts`, `guests`, `topics_discussed`.
- An artifact from a specific forum-platform signature: a `uri_pattern` schema (e.g., `forum-thread`) adds `thread_id`, `op_username`, `reply_count`.
- Audio with populated ID3 tags: as in the example above, the `musical-recording` schema applies and adds `artist`, `album`, `track_number`.

**Unclassified artifacts.** An artifact that matches no custom classification schema is fully valid — it carries its base-schema fields and an empty `classifications:[]` audit trail. Custom classification can be deferred to a later pass when more context is available.

**Schema vocabulary conventions.** Schema names (the filename stems under `schema/classification/`) are the corpus-side classification vocabulary. A corpus's conventions file (or `schema/README.md`) MAY document the available schemas with one-line descriptions. Unknown / freshly-authored schemas are always valid — they signal vocabulary growth.

#### 3.3.3 Custom classification as a living curatorial artifact

Custom classification schemas are not authored upfront; they emerge from how the corpus is used.

**The feedback loop.** Codex-record and compendium-record authoring reveals patterns. Authors keep reaching for the same metadata about the same kind of content; classification clusters form around recurring URI domains, MIME families, or extracted-field shapes; a domain dominates a slice of the corpus. The curator notices these patterns and authors a custom classification schema that captures them — declaring the fields the authors keep wanting and a schema name that identifies the pattern. A re-normalization sweep applies the new schema to every existing artifact whose match conditions are satisfied. Subsequent authoring is now richer because the metadata is already on the artifacts.

This loop is the corpus's classification layer growing in step with its actual usage. A corpus with no codex layer above it yet has only base schemas — and that's fine. A corpus whose codex layer is rich and active will grow a substantial custom classification library over time. The schemas, the artifacts, and the records co-evolve.

The pipeline mechanics of pattern detection, schema authoring, and re-normalization sweeps live in `impl-corpus.md`.

The Curator agent (§5.5) is responsible for monitoring the codex layer for pattern emergence and proposing new custom classification schemas to the operator.

#### 3.3.4 MIME Type Reference

The per-MIME normalization-method-and-extracted-fields reference is in **Appendix A.1**. It lists the canonical MIME, the normalization method, the typical base-schema extended fields, and notes per type. The set is illustrative, not closed — any IANA MIME type is valid as a `content_type` value.

A corpus authoring its own custom classification schemas adds further extended fields on top of the base-schema reference (see §3.3.2).

### 3.4 Examples

#### Artifact Record

```yaml
---
id: "a7f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."
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

The inline image is embedded via raw `![[blake3]]` — intra-corpus, mirroring the original post's image. The link to the bleeding thread is a raw blake3 wikilink to another artifact record in the same corpus. The parts-retailer link stays as a plain markdown URL because that page wasn't captured. No editorialization in the body — it faithfully mirrors the original forum post's structure and content.

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

The codex record uses footnote citations for downward artifact references (resolved to APA at build time), functional-URI embeds for inline artifact-derived views (page extracts, framegrabs), and intra-codex wikilinks (`[[uuid]]`) for peer codex records. The footnote bodies carry bare `corpus://` URIs that the build resolves into proper APA-style citations, drawing author / publication-date / title / source from the cited artifact's frontmatter.

### 3.5 Classification

Classification uses three mechanisms: tags (on codex records), the codex graph (wikilinks among codex records), and computed similarity (over normalized bodies and perceptual hashes).

#### 3.5.1 Tags

Tags are a codex-record primitive — they handle categorical classification on codex records exclusively. A codex record tagged `brake-caliper` and `vehicle-platform-x` is discoverable at the intersection. Tags are flat (no hierarchy), portable (no external dependencies), and codex-local — a tag means whatever the codex's conventions say it means. Tags appear in frontmatter (whole-record scope) and may also appear inline in the body (`%% #tag %%`, §3.2.5).

A codex MAY maintain a conventions file or use `codex.yaml` to list its tag vocabulary with one-line descriptions. This is guidance, not constraint — unknown tags are valid and signal vocabulary growth.

Artifact classification works differently: every applied custom classification schema is recorded in the artifact's `classifications:[]` audit trail with a justification, and the schema's contributed extended fields merge into top-level frontmatter (§3.3.2). The schema-application *is* the artifact's classification signal.

Compendium records organize by chapter structure and synthesis-system-prompt-driven taxonomy.

#### 3.5.2 The Codex Graph

The codex graph handles structural organization. A "Brake System Overview" codex record that links to "Caliper Rebuild," "Rotor Replacement," and "Brake Bleeding" records expresses compositional structure through its body. The link graph is the hierarchy.

A codex record that represents a concept (a category, a person, a place, a thing) is just a regular codex record with descriptive prose; other records reference it by wikilink. The role is emergent from the graph.

#### 3.5.3 Deduplication and Similarity

Deduplication and similarity are computed from intrinsic properties of artifacts:

**Tier 1: Blake3 (exact).** Same bytes → same hash → same record. Structural, automatic, zero-cost.

**Tier 2: Perceptual hashes (format-specific, cached).** Same perceptible content, different bytes. pHash/dHash for images, chromaprint for audio, simhash for text/HTML. Computed from the binary artifact. Cached for performance, rebuildable from inputs that are already stored.

**Tier 3: Body embeddings (cross-modal, cached).** The normalized body projects every modality into text. Embeddings of that text enable universal semantic similarity. An audio transcript and an HTML transcript of the same interview land near each other because their normalized text says the same things. Cached, rebuildable, model-upgradeable.

All three tiers produce queries, not stored edges. The spec defines the inputs (binary artifact + normalized body); tooling builds the indices.

### 3.6 Reference Resolution

Three reference primitives express the layered graph. Each has a single resolution rule.

**Wikilinks `[[id]]` — intra-layer only.**

- Artifact body: `[[blake3]]` → an artifact in the same corpus. Same-bytes blake3 collision across loaded corpora is harmless — the bytes are by definition identical; either copy resolves correctly.
- Codex-record body: `[[uuid]]` → another codex record in the same codex (UUIDv7).
- Compendium-record body: `[[slug]]` → another compendium record in the same compendium.

Wikilinks never cross containers. A codex record never wikilinks an artifact, another codex's record, or a compendium record; a compendium record never wikilinks an artifact or a codex record.

**Footnote citations `text[^N]` with `[^N]: <uri>` — cross-layer downward citation.**

- Codex body → artifact: `[^N]: corpus://{hash}` (with optional `#anchor` or `?params`).
- Compendium body → artifact: `[^N]: corpus://{hash}` (or `corpus://{name}/{hash}` for provenance disambiguation).
- Compendium body → codex record: `[^N]: codex://{name}/{uuid}` (with optional `#anchor`).

The footnote body carries a bare URI; the build/export step resolves it into a proper APA-style citation, generating author / publication-date / title / source from the target record's metadata. The footnote label is author-chosen (numeric or short slug) and is preserved through resolution.

**Embeds `![[…]]` — cross-layer functional inclusion (or intra-corpus raw cross-ref).**

- Artifact body: `![[blake3]]` → intra-corpus raw embed (§3.2.2). Mirrors the original content's embeds; no scheme prefix, no transformation.
- Codex- and compendium-record body: `![[corpus://{hash}?params]]` → functional URI embed of an artifact. A bare `![[corpus://{hash}]]` is the identity transform.

Codex records are never embedded — when one codex record needs to draw on another, wikilink it; when a compendium needs to integrate a codex record, footnote-cite it.

**Unresolved references.** A reference that cannot be resolved is surfaced as broken (Obsidian-style raw browsing) or flagged in compiled outputs with a clearly-marked fallback rather than silently dropped. Tooling backlink panels list unresolved references as authoring follow-ups.

**Cross-corpus same-bytes.** When multiple corpora are loaded, the same blake3 may appear in more than one. This is harmless — the bytes are identical, and a bare reference resolves to either copy. Compendium footnotes use the qualified `corpus://{name}/{hash}` form when provenance assertion matters.

### 3.7 Functional URI Scheme

Functional URIs are a codex- and compendium-record primitive. They appear in footnote citations (resolved to APA at build time) and in embeds (resolved to inline content). Two URI schemes:

- **`corpus://`** — references an artifact, by content hash. Used in footnote citations and embeds.
- **`codex://`** — references a codex record, by codex name and UUIDv7. Used only in compendium-record footnotes.

**`corpus://` artifact URIs.**

- **Base form:** `corpus://{hash}` — resolves to an artifact in any loaded corpus that has the hash.
- **Provenance form:** `corpus://{name}/{hash}` — asserts which corpus. Used in compendium contexts where two loaded corpora share a hash and the compendium needs to be specific.
- **Fragment navigation:** `corpus://{hash}#anchor` — navigates to a named section of the artifact's normalized body.
- **Transformation parameters:** appended as query parameters, composed left-to-right (each function operates on the output of the previous):

| Parameter | Applies to | Meaning |
|-----------|-----------|---------|
| `page={n}` | PDF | Extract page n (1-indexed). |
| `page={n}-{m}` | PDF | Extract page range. |
| `crop={x},{y},{w},{h}` | Image, PDF page | Crop to region (origin top-left, pixels or percentage). |
| `resize={w}x{h}` | Image | Resize to dimensions. |
| `framegrab={t}` | Video | Extract frame at timestamp (seconds or `m:ss`). |
| `range={t1}-{t2}` | Audio, Video | Extract time range. |
| `grayscale` | Image | Convert to grayscale. |

**Composition example:** `corpus://{hash}?page=4&crop=50,100,550,400` — extract page 4 from a PDF, then crop to the indicated region. The result is an image.

**`codex://` codex-record URIs.**

- **Base form:** `codex://{name}/{uuid}` — resolves to the codex record with the given UUIDv7 in the codex named `{name}`.
- **Fragment navigation:** `codex://{name}/{uuid}#anchor` — navigates to a named section of the codex record's body.
- **No transformation parameters.** Codex records are not embedded or cropped or page-extracted; the URI exists for citation, not for derived views.

**Semantics:**

- Functional URIs are **deterministic** — same inputs always produce the same output (the underlying artifact is immutable by content addressing; a codex record's UUID is stable within its codex instance).
- Results are **cacheable** — the cache key is the full URI string. Cache can be blown away and regenerated at any time.
- Results are **ephemeral** — they exist at compile/render time and are not stored as records.

**In Obsidian (raw browsing):** URIs that can't be resolved at browse time fall back to displaying the alt text or footnote label. Tooling or plugins can resolve them.

**In compiled outputs (mdbook, static site):** The build process resolves all functional URIs — computing artifact transformations for embeds, generating APA-style citations from footnote URIs.

The transformation parameter set is deliberately minimal. Future extensions should be added conservatively — each parameter must be deterministic over immutable inputs.

---

## 4. Pipeline

The path from raw content to a richly authored corpus has discrete steps; each is independently re-runnable.

- **Capture** brings content into the corpus. Identity is the hash of the bytes; failed captures consume no identity space. Capture is the only step requiring network access. Every captured file becomes its own artifact record; bundles of related files (a page plus its embedded images, a video plus its description page) become multiple artifact records, related through cross-references in their normalized bodies.

- **Normalize** transforms an artifact stub into a complete record: produces the body (extraction / transcription / description / metadata per the artifact's MIME, driven by the base schema), applies the matching base schema and any custom classification schemas, populates extended fields, records each schema application in `classifications:[]` with a required justification, resolves intra-corpus cross-references in the body to raw blake3 wikilinks and embeds, and refines the description. Bodies are faithful — normalization may improve accuracy but never adds information not present in the original.

- **Author** creates or edits a codex record (in a codex) or a compendium record (in a compendium) that synthesizes knowledge across artifacts and other records. The author writes nothing outside the target container. Authoring is non-destructive: referenced artifacts and other records are unchanged and independently addressable.

- **Re-normalize** is on-demand re-running of normalization when context, schemas, or models improve, or when newly captured artifacts resolve previously unresolved cross-references. Integrity is preserved — the new body remains a faithful rendering of the original artifact.

- **Build** materialises one or more layers for viewing. Each layer is independently exportable:

  - **Corpus build** — a browsable artifact vault. Resolves intra-corpus wikilinks among artifacts; serves binaries via the corpus's `artifacts/` cache.
  - **Codex build** — a browsable knowledge work (mdbook, static site, vault). Resolves intra-codex wikilinks (codex-record↔codex-record) and downward references (footnote URIs to artifacts, functional-URI embeds). The codex's referenced corpora must be loaded.
  - **Compendium build** — the published reference work. Resolves all references across the integration set (intra-compendium wikilinks; footnote URIs to codex records and artifacts, resolved into APA-style citations; functional-URI embeds). The compendium's referenced codices and corpora must be loaded.

  The build process can also generate a lookup index mapping any `uris[]` value to its artifact id, enabling consumers to find records by any URL known to resolve to them.

Procedural detail — fetch / hash / store ordering, MIME detection, conversion tooling, cross-reference-resolution mechanics, contextualization sub-steps, schema authoring, sharding, build mechanics, output formats — lives in `impl-corpus.md` and `impl-codex.md`.

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

**Output contract:** When the normalizer finishes successfully, the artifact record carries a faithful normalized markdown body, every base-schema-declared field that can be extracted, every field declared by any custom classification schema whose match conditions are satisfied, a `classifications:` array entry for every custom classification schema that was applied (each with a required `justification`), a refined `description`, and `status: normalized`. Any hyperlink or embed in the original content whose target exists in the corpus has been rewritten as a raw blake3 wikilink or embed (intra-corpus); targets that don't exist in the corpus remain as plain URLs. The normalizer never invents links the original content didn't contain.

Self-verification responsibilities: the artifact's `content_type` must match the MIME of the stored binary, and the `id` field must match the binary's blake3 hash.

### 5.4 Author

Creates or edits codex records in a codex (or compendium records in a compendium).

**Model class:** Sonnet-tier (semantic judgment required for synthesis).

**Scope:** One record per invocation, in one container.

**Output contract:** When the author finishes successfully, a record exists in the target container with the layer-appropriate `id` (UUIDv7 in a codex; author-chosen slug in a compendium), title, description, status, and (codex only) tags. The body is authored markdown prose: footnote-cites artifacts (`[^N]: corpus://{hash}` resolved to APA at build); embeds artifact-derived views via functional URIs (`![[corpus://{hash}?params]]`); wikilinks peer records in the same container (`[[uuid]]` for codex, `[[slug]]` for compendium); applies tags in frontmatter (codex only). A compendium-record body may additionally footnote-cite codex records (`[^N]: codex://{name}/{uuid}`). Backlinks and related-record candidates within the container are surfaced for follow-up. The author writes nothing outside the target container.

### 5.5 Curator

Autonomous orchestration skill that assesses corpus state, prioritizes work, and dispatches agents. Also responsible for the schema-feedback loop (§3.3.3) — monitoring the codex layer for emerging patterns and proposing new custom classification schemas to the operator.

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
- **Represent disagreement.** When sources conflict, the compendium presents both positions with whatever credibility-signal classifications they carry (see §3.3.2). Where the corpus expresses no credibility signals, surface the disagreement neutrally and let the reader judge.
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

## Appendix A: MIME Reference

This appendix is a concise overview of MIME types commonly encountered in practice. The authoritative source for normalization guidance per MIME is the base schema in `schema/base/`. Extended fields beyond `content_type` are extracted by base schemas (format-intrinsic) and custom classification schemas (corpus-local, optional, domain-specific).

Any IANA-registered MIME is valid as a `content_type` value. `unknown` is permitted as a sentinel.

### A.1 Common artifact MIMEs

| MIME | Method | Typical extended fields | Notes |
|------|--------|------------------------|-------|
| `text/html`, `application/xhtml+xml` | extraction | `page_title`, `meta_description`, `canonical_url`, `og_title`, `og_description`, `og_image`, `og_type`, `language` | Strip navigation, chrome, advertising. Preserve primary content, headings, tables, code blocks. The largest MIME by volume in most corpora. |
| `application/pdf` | extraction | `page_count`, `pdf_author`, `pdf_title`, `pdf_creation_date`, `pdf_producer`, `is_scanned` | Extract text and tables. OCR if scanned. Page boundaries surface as section anchors usable from functional URIs. |
| `application/epub+zip` | extraction | `work_title`, `epub_author`, `language`, `chapter_count`, `word_count` | Parse chapter structure; one heading per chapter. Internal links resolve via cross-reference resolution if other captures match. |
| `text/markdown`, `text/plain` | extraction (passthrough) | `word_count`, `language` | Minimal cleanup; the body is the file's contents. |
| `video/mp4`, `video/webm`, `video/mkv`, `video/quicktime` | transcription | `duration_seconds`, `width_px`, `height_px`, `frame_rate`, `video_codec`, `audio_codec` | Transcribe audio with timestamps. Frame descriptions per schema guidance. |
| `audio/mpeg`, `audio/flac`, `audio/wav`, `audio/ogg` | transcription | `duration_seconds`, `bitrate_kbps`, `sample_rate_hz`, `channels` | Transcribe with timestamps. Speaker turn markers where determinable. ID3-tagged audio that a corpus-local custom classification schema recognizes as musical recordings gains `artist`, `track_title`, `album`, `track_number`. |
| `image/jpeg`, `image/png`, `image/webp`, `image/gif` | description | `width_px`, `height_px`, `color_space`, `exif_date`, `exif_gps_lat`, `exif_gps_lon`, `exif_camera` | Visual description and OCR text in body. Embedded in artifact bodies via raw `![[blake3]]` (intra-corpus); embedded in codex- or compendium-record bodies via functional URI `![[corpus://hash?params]]`. |
| `message/rfc822` | extraction | `from`, `to`, `subject`, `message_date`, `in_reply_to` | Body is the message text; headers extracted to extended fields. Multipart bodies flatten to text/plain or text/html as primary. |
| `application/json` | extraction (passthrough) | `top_level_keys` | Prettify; preserve structure. |
| `unknown` | metadata | `byte_size`, `magic_bytes_summary` | Best-effort fallback. Record the gap in `issues[]`. |

### A.2 Classification examples

A corpus typically authors custom classification schemas to recognize content patterns it cares about. Each schema's *application* (its entry in `classifications:[]`) is itself the artifact-side classification signal. Examples of content-pattern schemas:

- **Forum threads** — text/html on a known forum domain → adds extended fields `username`, `thread_url`, `reply_count`.
- **Voting-community threads** — text/html on aggregator-style platforms → adds `community_slug`, `post_url`, `score`, `comment_count`.
- **Web articles** — text/html on publisher domains → adds `article_url`, `publication`, `byline`.
- **Service manuals** — application/pdf with publisher metadata matching a manual pattern → adds `service_section`, `vehicle_platform`, `manufacturer`.
- **Musical recordings** — audio/* with populated ID3 artist/album → adds `artist`, `track_title`, `album`, `track_number`.

Credibility signals are also custom classifications — each signal is its own narrow schema. There is no universal credibility scheme; corpora invent their own vocabulary as patterns emerge. Some illustrative examples:

```yaml
# schema/classification/peer-reviewed.yaml
schema_type: classification
match:
  content_type: "application/pdf"
  uri_pattern: "^https?://(www\\.sciencedirect|link\\.springer|onlinelibrary\\.wiley|nature)\\.com/"
```

```yaml
# schema/classification/preprint.yaml
schema_type: classification
match:
  content_type: "application/pdf"
  uri_pattern: "^https?://(arxiv\\.org|biorxiv\\.org|medrxiv\\.org)/"
```

```yaml
# schema/classification/corporate-bias.yaml
schema_type: classification
match:
  content_type: "*"
  # LLM judgment: matches when contextualization recognizes
  # promotional / corporate-PR framing in the content.
```

```yaml
# schema/classification/community-validated.yaml
schema_type: classification
match:
  has_classifications: [forum-thread]
  # LLM judgment: applies when thread shows clear consensus
  # across multiple independent users and no dissent.
```

```yaml
# schema/classification/anecdotal-claim.yaml
schema_type: classification
match:
  has_classifications: [forum-thread]
  # LLM judgment: applies when content is a single user's
  # unconfirmed experience report.
```

These schemas record themselves in the matched artifact's `classifications:[]` audit trail (with required justification, §3.3.2). They contribute no extended fields — the schema name itself is the signal that a compendium synthesis can weight.

Different corpora carry different credibility vocabularies. A research-paper corpus might define schemas like `retracted`, `predatory-journal`, `industry-funded`. A forum corpus might define `op-claim`, `consensus-supported`, `disputed`. A news corpus might define `wire-service`, `op-ed`, `sponsored-content`. The vocabulary evolves as the curator notices what kinds of credibility distinctions actually matter for the corpus's downstream synthesis use cases — the §3.3.3 schema-feedback loop applies to credibility signals like any other custom classification.

Custom classification schemas are corpus-local and optional. The same MIME can carry different custom classifications across corpora. Unclassified artifacts are fully valid — the base schema fields are sufficient on their own.

### A.3 When to author a codex record

A rule of thumb: when multiple artifacts share strong classification overlap (the same custom classification schemas applied across them) and would benefit from synthesized prose, author a codex record. Examples where authored records pay off:

- Multiple artifacts about the same album → an album record in a music-focused codex that synthesizes across the metadata page, the audio, and reviews.
- Many artifacts about products in a line → a product-line record that summarizes shared attributes and links to per-product records in the same codex.
- Recurring abstract categories (Review, Analysis, Explainer) → category records within a codex that cut across the codex's domain via cross-record wikilinks.

Cross-codex synthesis is not a codex's job — when multiple codices need to come together, that's a compendium (§6).

Codex records are cheap to create and cheap to retire. Do not over-plan. Start with the syntheses that the corpus's actual usage makes valuable, and let the codex graph grow organically.
