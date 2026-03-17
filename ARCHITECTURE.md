---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 7.1
status: draft
author: Steven Rahn
date_created: 2026-02-08
date_modified: 2026-03-17
addenda_incorporated:
  - ATH-ARCH-A001
  - ATH-ARCH-A002
changelog:
  - version: 7.1
    date: 2026-03-17
    summary: "Extracted ~600 lines of worked examples from §2–§14 into new §15 Working Examples, replaced inline with schema skeletons and forward references for improved readability"
  - version: 7.0
    date: 2026-03-17
    summary: "Major version: broadened corpus organizing principle from voice-only to classification chain (source corpora organized by voice, entity corpora organized by subject), explicit artifact immutability (captured artifacts are immutable throughout the classification chain), chain graduation (documents migrate from broad to specific corpora: triage → domain → entity, multi-hop with tombstone trail), partition-level graduation, reframed franchise corpora as entity corpus exemplars (§3.1.2), music domain running example alongside BSG, compendium role clarified (cross-entity synthesis + curated perspective), 'Origin objectivity' principle → 'Progressive classification'"
  - version: 6.0
    date: 2026-03-17
    summary: "Major version: subdivision→partition (sub_code→partition_code, sub_id→partition_id), doc_id→document_id (doc_seq→document_seq), source→record (src_id→record_id, src_seq→record_seq), sources/→material/, formal §1.2 Terminology (structural units, corpus organization, identifier components, pipeline terms), single/multi-origin corpus distinction (homogeneous vs heterogeneous multi-origin), derived artifacts formalized (flat derived/ dir, [[derived]] in document_id.toml, multi-record provenance), mdbook→Obsidian Vault + Quartz (assembled docs co-located in material/, gitignored content/ export, Obsidian-native agent navigation, Quartz replaces mdbook for static site generation)"
  - version: 5.0
    date: 2026-03-16
    summary: "Major version: broadened voice definition to include franchises (collaborative media with shared editorial identity), triage corpus for default intake with content-type partitions, routing registry ([[routing]] claims in corpus TOML for URL/channel/domain matching during reconciliation), graduation (cross-corpus document migration with tombstones and lineage tracking), cross-corpus references ([[cross_references]] in corpus TOML for discovery and soft routing), derived artifacts (pipeline-produced files like frame grabs/transcriptions/OCR in derived/ directory, namespaced by parent record_id, not assigned record_ids, regenerated during re-conversion)"
  - version: 4.0
    date: 2026-03-14
    summary: "Major version: three-phase pipeline (acquisition/normalization/assembly replaces four-phase), 'extraction sidecar' → 'source file' (definitive markdown representation), manuscript stubs eliminated (documents created only during Assembly), formal ID component terminology (corpus_id/sub_code/sub_id/doc_seq/doc_id/src_seq/src_id), corpus_prefix→corpus_id (4-letter code IS the corpus_id), document_id→doc_id and source_id→src_id field renames, new Conversion+Contextualization normalization steps, new Assembly phase with Obsidian+mdbook dual-format output (tags/aliases/callouts/wiki-links), source-level issue surfacing during contextualization, assets stored in sources/ with symlinks in manuscript/, new Assembler agent (§12.4), conversion_method/tool/date replace extraction_* fields"
  - version: 3.0
    date: 2026-02-16
    summary: "Major version: mandatory subdivisions (XXXX.TT.NNNNNNN ID format), directory overhaul (documents/→manuscript/, ingested/→sources/, assets inside manuscript/<slug>/assets/<doc_id>/), split ingestion into acquisition (.download/ staging) + reconciliation (ID assignment, stub creation), corpus as browsable mdbook reference (book.toml, frontmatter-strip, corpus.example.org), backlog rewrite ([[entries]] without pre-assigned IDs), document status field (pending_normalization|normalized), new §4 Corpus Format, new §12 Pipeline Agent Architecture (ingestor agent, normalizer agent, Curator skill), renumber all sections"
  - version: 2.0
    date: 2026-02-12
    summary: "Reorder §3 (pipeline before document format), simplify document frontmatter (summary→description, per-source fields moved to sidecar, add sources array), upgrade sidecar format (content_type_hint→content_type, add volatility/ingestion dates/author/date_published, move extended schemas to sidecar)"
  - version: 2.0
    date: 2026-02-12
    summary: "Restructure corpus/origin terminology (corpus = entity repo, origin = raw content source within corpus), replace manifest.toml with backlog.toml + document frontmatter, replace extracted/ directory with per-file extraction sidecars in ingested/, update registration TOML schema with per-origin configs"
  - version: 2.0
    date: 2026-02-12
    summary: "Rename origin.toml → {origin_id}.toml, 'source' → 'document' for normalized units, source_type → content_type, normalized/ → documents/, sources.md → references.md"
  - version: 2.0
    date: 2026-02-09
    summary: "Incorporate ATH-ARCH-A001 (origin identity guidelines), ATH-ARCH-A002 (term registry)"
  - version: 1.0
    date: 2026-02-08
    summary: "Initial specification"
---

## 1. Overview

**Athenaeum** is a personal knowledge infrastructure for building domain-specific AI agents backed by comprehensive, source-grounded reference material. The system separates the concerns of **source collection** and **knowledge synthesis** into distinct layers, enabling source material to be reused across multiple domains without duplication.

Each domain of interest (automotive repair, political theory, a fiction universe) is treated as an independent **compendium** that pulls from one or more **corpora** — normalized repositories of source material. Corpora come in two patterns: **source corpora** organize material by who produced it (a forum, an author, a manufacturer), while **entity corpora** organize material by what the subject is (a band, a franchise, a knowledge domain). Each corpus can have multiple **origins** — distinct raw content sources like a YouTube channel, a blog, or a PDF archive — that feed into its normalized collection. Documents migrate between corpora via **graduation**, moving from broad organizational homes toward increasingly specific ones as the corpus ecosystem matures. Compendiums synthesize their corpora into authoritative reference works published as Quartz sites and Obsidian vaults, serving both human readers and bespoke AI agents.

Athenaeum is designed around four core principles:

- **Progressive classification.** Content starts in the most unambiguous organizational home available — typically a source corpus organized by who produced it, or a triage corpus for unsorted content. Over time, documents graduate toward more specific homes: domain corpora, then entity corpora that coalesce material from many sources around a single subject. The goal is the most specific meaningful container, reached through iterative refinement rather than upfront taxonomy.
- **Domain isolation.** Each compendium is fully independent — its own repository, its own synthesized reference, its own agent. There is no shared knowledge graph or cross-domain routing. When you need an expert, you call on them explicitly.
- **Human-first accessibility.** Every compendium is browsable and readable by a human, structured like a textbook with a table of contents, search, glossary, and source citations. The agent accesses the same artifact a human would.
- **Source provenance.** Every claim in the compendium traces back to its original source material. The agent can tell you not just "this is the answer" but "this answer is supported by the service manual, corroborated by 12 forum reports, and contradicted by one outlier."

### 1.1 Design Philosophy

The architecture intentionally avoids complexity where simplicity suffices. There is no vector database, no knowledge graph, and no domain router. Pipeline orchestration uses a lightweight agent pattern (section 12) — single-purpose workers coordinated by a skill, not a general-purpose multi-agent framework. These are not rejected — they are deferred until a concrete need for them is demonstrated. The system is designed so that any of these can be added later without rearchitecting what exists.

### 1.2 Terminology

#### Structural Units

- **Corpus** (plural: *corpora*) — A self-contained repository of normalized material organized around a single meaningful unit — either a voice (source corpus) or a subject (entity corpus). Where raw source material lives.
- **Compendium** — A domain-specific synthesized reference work. Where curated knowledge lives.
- **Document** — The lowest quantification of a discrete 'thing' where another document would duplicate the majority of its content. A novel is one document; a book series is multiple documents.
- **Artifact** — The original file in its captured format (HTML, PNG, PDF, etc.). Artifacts are immutable — captured once and never modified. If the original is markdown, it is renamed to `.txt` so `.md` is reserved for records.
- **Record** — The markdown representation of an artifact: the file `{record_id}.md` in `material/`. Every artifact has a corresponding record, no exceptions. Contains YAML frontmatter with metadata and a body with the artifact's content as markdown.
- **Derived artifact** — A file produced by the pipeline from one or more captured artifacts (frame grabs, transcriptions, OCR output). Stored in a flat `derived/` directory within the document folder — no record namespacing, since derivations can span multiple records. Declared as `[[derived]]` entries in `{document_id}.toml` with provenance (`records` array). Not assigned record_ids. Reproducible — deleted and regenerated during re-conversion.

#### Corpus Organization

- **Source corpus** — A corpus organized by who produced the material (voice). The natural starting point for captured content — "who produced it" is an unchallengeable fact requiring no editorial judgment. Examples: g8board, frank-herbert, metal-archives, engineering-explained.
- **Entity corpus** — A corpus organized by what the subject is — a band, a franchise, a knowledge domain. Inherently multi-origin: documents accumulate records from multiple source corpora via graduation. Entity corpora represent the mature state where material is coalesced around a tangible, real-world subject. Examples: a music corpus (partitioned by bands), a BSG corpus (partitioned by episodes/characters/lore).
- **Classification chain** — The specificity spectrum from broad to specific that documents traverse via graduation: triage → domain corpus → entity corpus. Not all documents reach entity-level specificity, and that's fine — content is useful at any level.
- **Origin** — A distinct raw content source within a corpus (e.g., a YouTube channel, a blog, a PDF archive). A corpus with one `[[origins]]` entry is *single-origin*; with multiple entries, *multi-origin*. Source corpora tend toward single-origin. Entity corpora are inherently multi-origin — that is their defining characteristic.
- **Voice** — Editorial coherence, not single authorship. The organizing principle for source corpora. A TV franchise has dozens of contributors but speaks with one voice.
- **Partition** — An organizational category within a corpus. Partitions drive directory structure, navigation, and document ID assignment. Every corpus defines at least one.
- **Triage** — A default intake corpus for content without a dedicated home — the starting point of the classification chain. Content graduates out as dedicated corpora are created (section 3.1.1).
- **Routing** — URL/channel/domain claims declared in corpus TOML, checked during reconciliation to direct content to the right corpus (section 3.2.3).
- **Cross-reference** — Declared connections between corpora for discovery and soft routing (section 3.2.4).

#### Identifier Components

| Component | Example | Field Name |
|-----------|---------|------------|
| `corpus_id` | `ADG8` | 4-letter globally unique corpus identifier |
| `partition_code` | `RR` | 2-char uppercase alphanumeric partition code |
| `partition_id` | `ADG8.RR` | Corpus ID + partition code (derived, not stored) |
| `document_seq` | `0000001` | 7-digit zero-padded sequence within partition |
| `document_id` | `ADG8.RR.0000001` | Full document identifier (`corpus_id.partition_code.document_seq`) |
| `record_seq` | `001` | 3-digit zero-padded record sequence within document |
| `record_id` | `ADG8.RR.0000001_001` | Full record identifier (`document_id_record_seq`) |

#### Pipeline Terms

- **Capture** — Acquire raw content to `.capture/` staging (the only online step).
- **Reconciliation** — Assign identity, move to `material/`, create record stubs.
- **Conversion** — Deterministic per-artifact transform filling record bodies.
- **Contextualization** — LLM-driven cross-record refinement and issue surfacing.
- **Assembly** — Compile records into an assembled document in `material/`.
- **Export** — Build the gitignored `content/` directory for Quartz / vault distribution.
- **Graduation** — Cross-corpus document migration along the classification chain, with tombstones and lineage tracking. Documents graduate from broad to specific organizational homes.

---

## 2. Architecture Overview

Athenaeum is organized into three conceptual layers. Raw sources enter the **Corpus** layer, where they are acquired, normalized, and assembled into markdown documents with rich metadata and linking. Each corpus carries tiered summaries in its `{corpus_id}.toml` that enable **corpus discovery** via progressive disclosure — compendiums can efficiently discover which corpora are relevant to their domain by fetching these summaries from the Forgejo API without cloning every corpus. The **Compendium** layer declares corpus dependencies, uses an LLM to select relevant documents based on descriptions, and synthesizes the selected material into domain-specific reference works guided by a compendium-specific system prompt.

**Terminology:** See section 1.2 for formal definitions. In brief: *Corpus* is where raw source material lives. *Compendium* is where synthesized reference works live. *Record* is the markdown representation of an artifact (`{record_id}.md` in `material/`). *Partition* is an organizational category within a corpus — partitions drive directory structure, Quartz navigation, and document ID assignment.

A *document* is the lowest quantification of a discrete 'thing' where another document would duplicate the majority of its content. An individual novel is one document even if it has multiple editions or translations — those are records within the document. A book series is not one document; each novel stands on its own. There is room for discretion, but the test is: would a second document mostly repeat the first?

An *artifact* is the original file in its captured format — HTML, PNG, PDF, etc. Artifacts are immutable — captured once and never modified. When documents graduate between corpora, artifacts transfer intact; only IDs are remapped. If the original is already markdown, it is renamed to `.txt` during reconciliation so that `.md` is always reserved for the record. A *record* is the markdown representation of an artifact: the file `{record_id}.md` in `material/`. Every artifact has a corresponding record, no exceptions. The record has YAML frontmatter with metadata and a body containing the artifact's content interpreted as well-formed markdown.

A *derived artifact* is a file produced by the pipeline from one or more captured artifacts — frame grabs extracted from video, transcriptions generated from audio, OCR output from scanned images. Derived artifacts are stored in a flat `derived/` directory within the document folder — no record namespacing, since derivations can span multiple records. Declared as `[[derived]]` entries in `{document_id}.toml`. Not assigned their own `record_id`s. Derived artifacts are reproducible — deleted and regenerated during re-conversion.

**ID anatomy.** The full identifier `ADG8.RR.0000001_001` decomposes into these components:

| Component | Example | Definition |
|-----------|---------|------------|
| `corpus_id` | `ADG8` | 4-letter globally unique corpus identifier |
| `partition_code` | `RR` | 2-char uppercase alphanumeric partition code |
| `partition_id` | `ADG8.RR` | Corpus ID + partition code (derived, not stored) |
| `document_seq` | `0000001` | 7-digit zero-padded sequence within partition |
| `document_id` | `ADG8.RR.0000001` | Full document identifier |
| `record_seq` | `001` | 3-digit zero-padded record sequence within document |
| `record_id` | `ADG8.RR.0000001_001` | Full record identifier |

### 2.1 Corpus Layer

A corpus is a self-contained collection of normalized material organized around a single meaningful unit. **Source corpora** organize by voice — who produced the information (a forum, an author, a manufacturer). **Entity corpora** organize by subject — what the material is about (a band, a franchise, a knowledge domain). Both patterns produce the same output: markdown documents with structured frontmatter, processed through a three-phase pipeline — acquisition, normalization, and assembly. Each document carries a description that captures what it contains and why it's useful. Every corpus publishes as a browsable Quartz site and Obsidian vault (see section 4), organized by mandatory partitions that categorize documents within the corpus.

A corpus can have multiple **origins** — distinct raw content sources that feed into it. A forum corpus has one origin (the forum itself). A manufacturer corpus might have several: a PDF archive of service manuals, a web database of technical bulletins, and a press release feed. Entity corpora are inherently multi-origin — a music corpus might draw from Metal Archives, RateYourMusic, YouTube, Wikipedia, and Bandcamp, all contributing different perspectives on the same subjects. Each origin has its own ingestion method and reingest configuration, declared in the corpus's registration file.

Documents move along a **classification chain** — from broad organizational homes (triage) through domain corpora (music, television) to entity corpora (Gorguts, BSG) — via graduation. Not all documents reach entity-level specificity, and content is useful at every level. The goal is the most specific meaningful container, reached through iterative refinement.

Key properties:

- **One container, one corpus.** Source corpora are bounded by voice: a forum, an author, a manufacturer, a franchise. Entity corpora are bounded by subject: a band and its discography, a franchise and its episodes, a knowledge domain and its constituent topics. The principle is that each corpus represents one meaningful organizational unit. Content that hasn't been assigned to a dedicated corpus enters a triage corpus for later graduation (see section 3.1.1).
- **Multiple origins, one corpus.** A single entity may publish through multiple channels and formats. These are different origins within the same corpus. For source corpora, the corpus groups them by voice. For entity corpora, the corpus groups them by subject — gathering material from many producers about the same thing.
- **No editorial filtering.** A corpus contains everything from its source, summarized but unfiltered. Topical selection happens downstream at the compendium layer.
- **Summary-driven discovery.** Every assembled document carries a description that enables downstream selection without reading the full content. An LLM reading the description can determine whether the document is relevant to a given domain.

The range of corpora is deliberately broad. Source corpora: `g8board` (an automotive forum), `frank-herbert` (an author's collected works), `gm` (a manufacturer's manuals, bulletins, and press releases), `engineering-explained` (a YouTube channel's transcripts), `marxists-org` (a text archive). Entity corpora: `music` (bands, albums, and songs from many sources), `bsg` (a franchise's episodes, scripts, and lore from many origins). Each is independent and self-contained.

### 2.2 Corpus Discovery

Corpus discovery is API-driven — each corpus's `{corpus_id}.toml` carries tiered summaries that describe the corpus, and these are fetched on demand from the Forgejo API without cloning any repos. There is no separate registry repository; the corpora describe themselves.

Each corpus carries three summary tiers in its `{corpus_id}.toml`:

1. **Tier 1** — a single sentence. Enough to include or exclude at a glance.
2. **Tier 2** — a concise paragraph. Enough to confirm relevance and understand scope.
3. **Tier 3** — a comprehensive description. Full detail on what the corpus contains, its document count, and its coverage.

At compendium setup time, tooling lists all repos in the Corpus organization via the Forgejo API, fetches each `{corpus_id}.toml`, and extracts the summary tiers. An LLM reads tier 1 summaries for all corpora to identify candidates, reads tier 2 for confirmation, and consults tier 3 only when needed. This avoids the cost of cloning and scanning corpora that turn out to be irrelevant. See section 5 for the discovery format and progressive disclosure process.

### 2.3 Compendium Layer

A compendium defines a knowledge domain and synthesizes a structured reference work from corpus material. It does not store source content — it declares which corpora it draws from, selects relevant documents using an LLM that reads document descriptions, and synthesizes a coherent, browsable reference from the selected material.

Key properties:

- **Domain declaration.** A compendium defines its scope by listing corpus dependencies and providing a synthesis system prompt that encodes domain knowledge.
- **Shared corpora, different selections.** Multiple compendiums can draw from the same corpus. An `economics` compendium and a `socialism` compendium might both depend on `marxists-org`, with their respective system prompts guiding the LLM to select different documents.
- **System prompt as domain bootstrap.** The compendium's system prompt provides the LLM with domain-specific context: key relationships, disambiguation guidance, scope boundaries. This is iterable — when synthesis produces gaps or errors, the system prompt is refined.
- **Synthesis output.** Selected documents are synthesized into manuscripts — structured, cross-referenced markdown that gets compiled into a browsable, textbook-like reference.

**Relationship to entity corpora.** Entity corpora coalesce raw material around a subject; compendiums synthesize that material into authoritative reference works. These are complementary, not redundant. A music entity corpus with comprehensive Gorguts documents (gathered from Metal Archives, RateYourMusic, YouTube, and Wikipedia) gives a "Death Metal" compendium far richer input than five separate source corpora would. Compendiums serve two purposes that entity corpora do not:

- **Cross-entity synthesis.** A compendium draws from multiple corpora or partitions — comparing, contrasting, and connecting material across subjects. A "Death Metal" compendium synthesizes across Gorguts, Morbid Angel, Immolation, and dozens of other entities.
- **Curated perspective.** A compendium adds editorial voice, narrative structure, and analytical depth. The corpus gathers and assembles; the compendium interprets and teaches.

For example, a `dune` compendium declares dependencies on `frank-herbert`, `brian-herbert`, `denis-villeneuve`, and `scifi-channel-dune`. Its system prompt defines the Dune franchise scope and key relationships. During synthesis, the LLM reads document descriptions from each corpus — Frank Herbert's *Dune* and *Dune Messiah* are selected because their descriptions clearly relate to the Dune universe, while *Man of Two Worlds* (a comedy collaboration) and *The Dragon in the Sea* (a submarine thriller) are skipped. From `denis-villeneuve`, the Dune screenplays are selected while *Blade Runner 2049* and *Arrival* are not. The LLM's semantic understanding, guided by the system prompt, makes these selections — no tag matching required.

See section 6 for the detailed compendium structure and synthesis process.

### 2.4 Data Flow

The full pipeline from source to published reference:

```
  Raw Content (PDF, forum thread, transcript, ...)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 1: Acquisition                       │
  │  Capture: acquire to staging                │  script-driven or manual
  │  → .capture/<descriptive-name>/              │  (gitignored, only online step)
  │                                             │
  │  Reconciliation: assign identity            │  partition detection,
  │  → material/<slug>/<document_id>/                 │  ID assignment,
  │    {record_id}.{ext} (artifacts)               │  record stub creation
  │    {record_id}.md    (record stubs)            │
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 2: Normalization                     │
  │  Conversion: deterministic transform        │  per-artifact, isolated
  │  → fills record bodies                 │  status: stub → draft
  │                                             │
  │  Contextualization: LLM refinement          │  cross-record, issues
  │  → refines records                     │  status: draft → normalized
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 3: Assembly                          │
  │  compile records into document              │  descriptions, credibility,
  │  → material/<slug>/<document_id>/           │  relations,
  │    {document_id}.md                         │  Obsidian-native format
  └─────────────────────────────────────────────┘
       │
       │  assembled document with description
       ├──────────────────────────────────────────┐
       ▼                                          ▼
  ┌──────────────────────────┐  ┌──────────────────────────────┐
  │  Export + Corpus Site    │  │  Corpus Discovery            │
  │  export to content/      │  │  {corpus_id}.toml summaries  │
  │  Quartz build            │  │  fetched via Forgejo API     │
  │  → corpus.example.org/     │  └──────────────────────────────┘
  └──────────────────────────┘       │
                                     │  progressive disclosure
                                     ▼
  ┌─────────────────────────────────────────────┐
  │  Compendium: Synthesis                      │
  │  system prompt + summaries                  │
  │  → select → synthesize →                    │
  │  compile                                    │
  └─────────────────────────────────────────────┘
       │
       ▼
  Published Reference (Quartz site + Obsidian vault + AI agent context)
```

See section 15.1 for a concrete walkthrough tracing a document from capture through compendium selection.

---

## 3. Corpus Repositories

### 3.1 Corpus Identity

A corpus repository represents a single meaningful organizational unit. For **source corpora**, that unit is a voice — one entity that produces information. For **entity corpora**, that unit is a subject — one real-world thing that information is about. The question that determines a corpus boundary is **"what is the most specific meaningful container for this material?"**

Source corpora are the natural starting point. "Who produced it" is an unchallengeable fact requiring no editorial judgment — if you can point at a source and say "that came from the same entity expressing its own perspective," it belongs in the same source corpus. Entity corpora are the aspirational destination. As material accumulates around a subject from many sources, it graduates into an entity corpus where documents coalesce around tangible things — a band, an album, a franchise, a vehicle platform.

#### Source Corpora: Organized by Voice

A voice is an entity with a coherent editorial identity:

- A **company** — GM, Holden, Penrite Oils
- A **community** — one forum, one subreddit, one Discord server
- An **author** — Frank Herbert, Brian Herbert
- A **channel or show** — Engineering Explained, South Main Auto
- A **government body** — NHTSA, Australian ANCAP
- An **academic journal** — a single publication venue

Voice means editorial coherence, not single authorship. A TV franchise has dozens of writers, directors, and producers, but the show itself has a unified editorial identity that transcends any individual contributor. The test is whether the body of work speaks with one voice — not whether one person created it.

A platform is never a voice. Reddit is not a corpus — r/MechanicAdvice is. YouTube is not a corpus — Engineering Explained is. "Car forums" is not a corpus — g8board is.

#### Entity Corpora: Organized by Subject

An entity corpus organizes material around a real-world subject rather than a single producer. The subject is a tangible thing that exists independently and can have artifacts attached to it from many sources:

- A **knowledge domain** — music, automotive diagnostics, speculative fiction
- A **franchise** — Battlestar Galactica, the Dune film series
- A **specific entity** — Gorguts (the band), the Pontiac G8 (a vehicle platform)

Entity corpora are inherently multi-origin. A music corpus draws from Metal Archives, RateYourMusic, YouTube, Wikipedia, Bandcamp, and more — each contributing different perspectives on the same subjects. Documents within an entity corpus represent tangible things: a band, an album, a song, an episode. Partitions reflect the subject's natural structure (bands within music, episodes within a franchise), not content format.

Entity corpora are populated through **graduation** from source corpora and triage. Metal Archives scrapes about Gorguts start in the `metal-archives` source corpus. When a music entity corpus exists, those documents graduate into it, joining RateYourMusic data, YouTube live recordings, and Wikipedia articles — all coalesced into comprehensive documents about the same subjects.

Not all subjects warrant an entity corpus. Accumulation must justify the organizational overhead. A few scattered references to a band don't merit their own entity partition — but when material from five sources all describes the same discography, the entity corpus pattern produces dramatically richer documents than keeping them siloed in separate source corpora.

#### Consolidation Principles

**Within source corpora: consolidate by voice, not document type.** All material produced by a single entity belongs in one source corpus, regardless of document type or format. General Motors publishes service manuals, technical service bulletins, recall notices, press releases, dealer bulletins, and marketing brochures. These are all one voice: GM.

```
corpus/general-motors/
```

Within the `general-motors` corpus, individual documents use `content_type` to distinguish `service_manual` from `technical_bulletin` from `product_documentation` from `article`. Credibility tiers handle trust differences between a factory service manual (`authoritative`) and a marketing brochure (`expert` or lower). The source corpus only answers: **who said this.**

**Within entity corpora: consolidate by subject, across voices.** An entity corpus intentionally gathers material from many producers about the same subject. A music entity corpus combines Metal Archives band pages, RateYourMusic reviews, YouTube live recordings, and Wikipedia articles — all contributing different records to the same document about a band or album. The entity corpus answers: **what is this about, and what do we know about it from all available sources?**

These are complementary operations. Consolidating similar *voices* into a catch-all (five car forums → one "car-forums" corpus) is still wrong — they are distinct voices with different biases. Consolidating diverse *sources* around a single *subject* (five sources about Gorguts → one entity corpus or partition) is the whole point of entity corpora.

#### Why Not Consolidate Similar Voices?

Five car forums (g8board, ls1tech, performanceforums, pontiacg8forum, holdenforums) share a platform type, content structure, and ingestion method. It's tempting to merge them into one `car-forums` corpus to reduce repo count. This is wrong for four reasons:

1. **Each community is a distinct voice.** g8board is G8-obsessed. ls1tech is LS-engine-first and happens to cover G8s. holdenforums brings the Australian VE platform perspective that American forums lack. These are genuinely different perspectives with different biases, different expertise concentrations, and different blind spots.

2. **Combining introduces the taxonomy problem we're avoiding.** For source corpora, "where it came from" is an unchallengeable fact requiring no editorial judgment. If you combine forums, you're making an editorial decision about which communities are "similar enough" — and that decision may need to be undone later.

3. **The compendium and entity corpora are where commonality is extracted.** Five forums all discussing rear wheel bearings is not a reason to combine them at the source level. It's a reason for an entity corpus or compendium to pull from all five and synthesize their perspectives.

4. **The friction of multiple repos is trivial.** Adding a corpus as a dependency is one line in `compendium.toml`. Sparse checkout is handled by `resolve.sh`. The real friction is untangling combined corpora later when you need one voice in a compendium but not another.

**Note:** This reasoning applies to consolidating similar *voices* into a single source corpus. Entity corpora are a different operation — they intentionally gather diverse sources around a single *subject*. Don't confuse "five forums merged into one" (wrong) with "five sources about the same band coalesced into one entity partition" (correct).

#### The Decision Test

When deciding whether something is one corpus or multiple:

**For source corpora (voice-based):**

1. **Can you name the producer?** "GM", "g8board", "Frank Herbert", "r/MechanicAdvice" — if you can name a single entity with a coherent editorial identity, it's one source corpus.

2. **Would you ever want one without the other in a compendium?** If ls1tech's LS engine content belongs in an engine-building compendium but g8board's doesn't, they must be separate corpora. You can't partially include a repo.

3. **Is the split based on document type or entity?** If you're splitting because "service manuals are different from press releases," stop — that's a `content_type` distinction, not a corpus distinction. If you're splitting because "GM and Holden are different manufacturers," proceed — those are different entities even though they shared a corporate parent.

**For entity corpora (subject-based):**

4. **Has a subject accumulated enough mass across sources?** If five different source corpora each have documents about Gorguts, those documents are more valuable coalesced into a single entity corpus (or partition within a music corpus) than scattered across five repos.

5. **Can you name the real-world thing?** "Gorguts", "the Pontiac G8", "Battlestar Galactica" — if you can point at a tangible subject that exists independently and has artifacts from multiple sources, it's a candidate for an entity corpus or entity partition.

6. **Can it be further subdivided?** A band exists on its own but can also be divided into albums and songs, each with their own artifacts. If the subject has natural subdivisions that map to partitions and documents, the entity corpus pattern is a good fit.

#### Examples

**Source corpora** (organized by voice):

| Voice | Corpus Repo | Contains |
|-------|-------------|----------|
| General Motors | `gm` | Service manuals, TSBs, recalls, press releases, dealer bulletins, brochures |
| G8Board.com | `g8board` | All forum threads from this community |
| Frank Herbert | `frank-herbert` | Novels, short stories, essays, interviews |
| Metal Archives | `metal-archives` | All band/album/review pages from the site |

**Entity corpora** (organized by subject):

| Subject | Corpus Repo | Contains | Origins |
|---------|-------------|----------|---------|
| Music | `music` | Band pages, albums, songs, reviews, live recordings | Metal Archives, RYM, YouTube, Bandcamp, Wikipedia |
| Battlestar Galactica | `bsg` | Episodes, characters, lore, production docs | Episode files, Wikipedia, IMDB, Reddit, scripts |

See section 15.6 for the complete examples tables.

Entity corpora start broad (a music corpus partitioned by bands) and may eventually spawn more specific entity corpora (a Gorguts corpus) as material accumulates. Documents graduate upward through the classification chain — see section 3.3.5.

#### Single-Origin and Multi-Origin Corpora

Corpora fall into two broad patterns based on how many `[[origins]]` entries they declare. This is not a TOML field — it is determined by the number of origins in the registration file.

**Single-origin corpora** have one `[[origins]]` entry. Most source corpora are single-origin: `g8board` (one forum), `frank-herbert` (one author's collected works), `engineering-explained` (one YouTube channel), `nytimes` (one publication), `arxiv` (one preprint archive). The ingestion pipeline is uniform because all content comes from one source type.

**Multi-origin corpora** have multiple `[[origins]]` entries. These subdivide further:

- **Homogeneous multi-origin** — origins differ in ingestion method but produce similar content types. Example: `gm` has a PDF archive origin and a web database origin, but both produce technical documentation. The origins exist because the content lives in different places, not because the content is fundamentally different.
- **Heterogeneous multi-origin** — origins produce fundamentally different content types that are combined into multi-origin documents. Example: `bsg` (Battlestar Galactica) draws from episode files, Wikipedia, IMDB, Reddit, and production scripts — each origin contributes a different perspective on the same document (see section 3.1.2).

Source corpora tend toward single-origin. Entity corpora are inherently multi-origin — that is their defining characteristic. Multi-origin is the natural end state for any corpus that accumulates material from diverse sources about the same subjects. A music entity corpus might start with two origins (Metal Archives and Wikipedia) and grow to six as YouTube, Bandcamp, RateYourMusic, and Discogs are added.

#### 3.1.1 Triage Corpus

A **triage corpus** is the default intake destination for content that doesn't yet have a dedicated corpus — the starting point of the classification chain. Instead of creating a new corpus for every piece of content encountered — which creates decision paralysis at capture time — undecided content enters triage and is graduated to dedicated corpora as they are created.

The triage corpus eliminates a common friction point: encountering interesting content and stalling on "which corpus does this belong in?" The answer is always "triage, for now." The content is captured, normalized, and available — the organizational decision is deferred, not lost.

**Key properties:**

- **Content-type partitions.** Unlike dedicated corpora where partitions reflect the entity's or subject's structure, triage partitions reflect content format: `WB` (web), `DC` (documents/PDFs), `MD` (media — video/audio), `RF` (reference — databases, datasets), `NT` (notes — manual captures, observations). These are deliberately broad — they exist to provide minimal organization, not editorial judgment.
- **Not universal intake.** When a dedicated corpus exists and its routing claims match the content (see section 3.2.3), content goes directly to that corpus. Triage is for content that has no home yet, not a funnel for all content.
- **Graduation is the expected outcome.** Content accumulates in triage until a dedicated corpus is created, at which point matching content graduates out (see section 3.3.5). Graduation can be multi-hop: a BSG episode page might graduate from triage to a television domain corpus, then later to a dedicated BSG entity corpus. A healthy triage corpus trends toward empty as the corpus ecosystem matures.
- **TOML flag.** The corpus TOML includes `triage = true` to identify it as a triage corpus:

```toml
# TRGE.toml
corpus_id = "TRGE"
corpus_name = "Triage"
document_id_format = "TRGE.TT.NNNNNNN"
triage = true
summary_tier1 = "Unsorted content awaiting graduation to dedicated corpora"
# ... summary_tier2, summary_tier3

[[partition]]
code = "WB"
slug = "web"
name = "Web Captures"
description = "HTML pages, blog posts, articles, forum threads"
# ... additional format-based partitions (DC, MD, RF, NT)
```

See section 15.2 for the complete triage registration file.

#### 3.1.2 Franchise and Entity Corpus Patterns

A **franchise corpus** is the exemplar of the entity corpus pattern — a heterogeneous multi-origin corpus representing collaborative media with a shared editorial identity. Franchise corpora (television series, film franchises, video game series) were the first corpora to demonstrate subject-centric organization: the franchise itself is the organizing unit, not any individual writer, director, or contributor. The same pattern applies to all entity corpora: a music corpus organized by bands, an automotive corpus organized by vehicle platforms.

Entity corpora are distinguished by two properties that don't arise in single-origin source corpora:

1. **Heterogeneous origins.** A TV franchise corpus draws from episode files, Wikipedia episode guides, IMDB data, Reddit discussion, production scripts, and cast interviews. Each origin has its own ingestion method and format. This is a more extreme version of the multi-origin pattern — a manufacturer corpus might have two or three origin types, but a franchise corpus may have six or more.

2. **Multi-origin documents.** A single document (e.g., one episode) may have records from multiple origins: the episode transcript, the Wikipedia summary, the IMDB page, a Reddit discussion thread, and the shooting script. The document config (`{document_id}.toml`) is the anchor — the first record creates the document, and subsequent records from other origins are added as new artifacts within the same document. Each record's `origin` field tracks provenance. Reconciliation matches incoming content to existing documents by title, URL pattern, or operator direction.

**Partitions reflect structure, not format.** A TV franchise corpus uses partitions like `EP` (episodes), `CH` (characters/cast), `WD` (world-building/lore), `PR` (production), `AN` (analysis/reviews) — categories that reflect the franchise's structure, not the content format.

See section 15.6 for complete record breakdowns showing how BSG episodes and music entity documents combine artifacts from multiple origins, including assembly paths and graduation patterns.

### 3.2 Corpus Registration

Each corpus repo contains a registration file (`{corpus_id}.toml`) that declares metadata about the corpus, its origins, and its partitions. The filename uses the `corpus_id` (the 4-letter code), enabling discovery tooling to cache all registration files in a flat directory without name collisions. Optional fields include `triage` (boolean, marks the corpus as a triage intake — see section 3.1.1), `[[routing]]` entries (content claims for reconciliation routing — see section 3.2.3), and `[[cross_references]]` entries (declared connections to other corpora — see section 3.2.4):

```toml
# {corpus_id}.toml — registration file schema
corpus_id = "XXXX"                    # 4-letter globally unique identifier
corpus_name = "Human-Readable Name"
document_id_format = "XXXX.TT.NNNNNNN"
# triage = true                       # optional — marks as triage corpus

summary_tier1 = "One sentence"        # corpus discovery (section 5)
summary_tier2 = "One paragraph"
summary_tier3 = "Full description"

# optional: [[routing]], [[cross_references]] — see sections 3.2.3, 3.2.4

[[origins]]
origin_id = "source-name"
origin_type = "forum|pdf_archive|web_database|media_archive|web_reference"
origin_url = "https://..."            # optional
ingestion_method = "web_scraper|pdf_extractor|media_extractor"
active = true                         # is this origin still producing new content?

[origins.reingest]
default_volatility = "static|unlikely|periodic|active"
active_threshold_days = 7
periodic_threshold_days = 90
unlikely_threshold_days = 365

[[partition]]
code = "TT"                           # 2-char uppercase alphanumeric
slug = "human-readable-slug"          # drives directory structure
name = "Display Name"
description = "What this partition contains"
```

See section 15.2 for complete registration files demonstrating single-origin (G8BD), multi-origin (GMOT), entity/franchise (BSGF), and triage (TRGE) patterns.

Each `[[origins]]` entry represents a distinct raw content source within the corpus. A single-origin corpus (like g8board) has one `[[origins]]` entry. A multi-origin corpus (like GM) has one entry per ingestion path. The `origin_type`, `origin_url`, `ingestion_method`, and `active` fields live at the origin level because they describe the raw content source, not the corpus as a whole.

Each origin's `[origins.reingest]` section defines the default volatility for documents from that origin and the thresholds for re-ingestion priority. Individual records can override `default_volatility` via the `volatility` field in their record frontmatter. The ingestion scanner compares each record's `ingestion_date_last` against the appropriate threshold to generate a re-ingestion priority queue. If a document spans multiple origins, each record carries its own volatility from its respective origin.

The `corpus_id` ensures globally unique document IDs across all corpora. IDs are 4 uppercase letters (allowing for 456,976 unique corpus IDs). The full `document_id` format is `XXXX.TT.NNNNNNN` — a 4-letter `corpus_id`, a 2-character uppercase alphanumeric `partition_code`, and a 7-digit zero-padded `document_seq`. For example, `G8BD.TA.0000001` identifies the first document in the Technical Articles partition of the G8BD corpus. When a compendium cites `G8BD.SB.0000003`, it unambiguously resolves to a specific file in a specific corpus repo and partition.

#### Partitions

**Partitions are mandatory.** Every corpus defines at least one `[[partition]]` entry in its `{corpus_id}.toml`. This means the `document_id` format is always `XXXX.TT.NNNNNNN` — there is no short form without a `partition_code`.

Partitions drive three things: directory structure (files are organized under partition slug directories in `material/`), Quartz navigation (each partition becomes a section in the corpus site), and ID assignment (the 2-character `partition_code` is embedded in every `document_id`).

The partition structure varies by corpus type:

- **Forum corpus** (g8board): partitions map to forum sections — Technical Articles, V8 Engine, Suspension & Brakes, etc.
- **Author corpus** (frank-herbert): partitions map to work types — `NV` (novels), `SS` (short stories), `ES` (essays), `IN` (interviews).
- **Manufacturer corpus** (gm): partitions map to document types — `SM` (service manuals), `TB` (technical bulletins), `PR` (press releases).
- **YouTube channel** (engineering-explained): could use a single partition `VD` (videos) or subdivide by topic area.

Even a corpus with only one logical category still defines a partition — the format is universal.

#### 3.2.3 Routing Registry

Corpora can declare **routing claims** — patterns that identify content belonging to this corpus. During reconciliation (section 3.3.1.2), the ingestor checks all routing claims before assigning content to the local corpus. If another corpus claims the content, reconciliation rejects it locally and redirects the operator (or ingestor agent) to the target corpus.

Routing claims are declared as `[[routing]]` entries in `{corpus_id}.toml`:

```toml
# Routing claims in G8BD.toml
[[routing]]
type = "url_pattern"
claim = "https://www.g8board.com/*"

[[routing]]
type = "domain"
claim = "g8board.com"
```

**Claim types:**

| Type | Format | Example |
|------|--------|---------|
| `url_pattern` | Glob pattern matching URLs | `https://www.g8board.com/*` |
| `youtube_channel` | YouTube channel ID | `UCsVxgGlSsNBjReaEj-sjSQ` |
| `domain` | Domain name (matches all URLs on that domain) | `battlestarwiki.org` |

**Resolution rules:**

- **Discoverable via API.** Routing claims are fetched alongside corpus metadata during discovery (section 5.3), using the same Forgejo API mechanism. Reconciliation tooling builds a routing table from all corpus TOMLs.
- **Specificity wins.** When multiple corpora claim overlapping patterns, the more specific claim wins. A `url_pattern` of `https://www.reddit.com/r/BSG/*` is more specific than a `domain` of `reddit.com`. A longer glob prefix beats a shorter one.
- **Match → redirect.** If incoming content matches a routing claim from a different corpus, reconciliation rejects the content locally and reports which corpus claims it. The content should be captured into the claiming corpus instead.
- **No match → proceed locally.** If no routing claims match, reconciliation proceeds normally in the current corpus.
- **Triage special case.** Routing claims prevent content from accumulating in triage (section 3.1.1) when a dedicated corpus already claims it. The triage ingestor checks routing before ingesting — if a claim matches, the content is redirected rather than triaged.

Routing claims are informational declarations, not enforcement mechanisms. They rely on reconciliation tooling (or the ingestor agent) checking claims before ingesting. The system degrades gracefully if claims are not checked — content ends up in the wrong corpus and can be graduated later (section 3.3.5).

#### 3.2.4 Cross-Corpus References

Corpora can declare **cross-references** to other corpora — informational connections that serve two purposes: compendium discovery and soft routing for LLM ingestors.

```toml
# Cross-references in BSGF.toml
[[cross_references]]
corpus_id = "SCFI"
relationship = "related"
description = "Sci Fi Channel — network that aired BSG, shared production context"

[[cross_references]]
corpus_id = "RDMO"
relationship = "commentary"
description = "Ron D. Moore's podcast commentary on BSG episodes"
```

**Relationship types:**

| Type | Meaning | Example |
|------|---------|---------|
| `franchise` | Part of the same franchise ecosystem | BSG → Caprica (prequel series) |
| `source_author` | Author whose work this corpus derives from | Dune Films → Frank Herbert |
| `adaptation` | Adaptation of another corpus's content | Film corpus → novel corpus |
| `commentary` | Commentary or analysis of this corpus | Podcast → TV series |
| `related` | General topical or contextual relationship | BSG → Sci Fi Channel |

**Properties:**

- **Informational, not structural.** Cross-references create no hard dependencies. A cross-reference can point to a corpus that doesn't yet exist — it's a declaration of intent or relationship, not a build-time requirement.
- **Discovery signal.** When a compendium selects a corpus, its cross-references surface additional corpus candidates. The `dune` compendium selects `frank-herbert` and discovers via cross-reference that `dune-films` and `brian-herbert` are related (section 6.2).
- **Soft routing.** An LLM ingestor reading cross-references can make better decisions about where content belongs. If the BSG corpus cross-references a Ron D. Moore podcast corpus, the ingestor encountering Moore's BSG commentary can infer it likely belongs in the podcast corpus, not the BSG corpus.

#### 3.2.1 Corpus Repository Layout

Each corpus repo has a clean top-level structure:

```
Corpus/{corpus_id}/
├── {corpus_id}.toml              # registration
├── backlog.toml                  # non-captured entry tracking
├── quartz.config.ts              # Quartz configuration
├── content/                      # GITIGNORED — build artifact
├── material/                     # all corpus material
│   └── {slug}/
│       └── {document_id}/
│           ├── {document_id}.md          # assembled document
│           ├── {document_id}.toml        # document config
│           ├── {record_id}.{ext}         # artifact
│           ├── {record_id}.md            # record
│           └── derived/                  # pipeline-produced files
└── .capture/                     # gitignored staging
```

See section 15.3 for a fully populated directory tree with concrete file examples.

**Key distinctions by filename pattern:**
- `{document_id}.md` (e.g., `G8BD.SB.0000001.md`) — assembled document (no underscore)
- `{document_id}_{record_seq}.md` (e.g., `G8BD.SB.0000001_001.md`) — record (has underscore + seq)
- `{document_id}_{record_seq}.{ext}` — artifact (non-.md extension)
- `{document_id}.toml` — document config

**Directory purposes:**

- **`material/`** — All corpus material: artifacts, records, derived files, assembled documents, and document configs. Organized by partition slug and then by `document_id`. Each document has its own directory containing everything related to it. Assembled documents are co-located with their records — the assembled `{document_id}.md` lives alongside the `{record_id}.md` records and `{record_id}.{ext}` artifacts it was built from.
- **`material/<slug>/<document_id>/derived/`** — Pipeline-produced files (frame grabs, transcriptions, OCR output). Flat directory — no record namespacing since derivations can span multiple records. Declared as `[[derived]]` entries in `{document_id}.toml` with provenance (`records` array). Named descriptively (e.g., `frame_0001.jpg`, `transcript.vtt`). Deleted and regenerated during re-conversion.
- **`material/<slug>/<document_id>/{document_id}.toml`** — Document configuration. Contains the working `title`, optional per-phase `[prompts]` for pipeline agents, optional `original_document_id` (graduation lineage), and `[[derived]]` entries declaring derived artifacts. Created during reconciliation; prompts added as needed by the operator or Curator. Example:

```toml
# G8BD.SB.0000002.toml
title = "Brake Upgrade Guide"

[[derived]]
file = "frame_0001.jpg"
type = "frame_grab"
records = ["G8BD.SB.0000002_001"]

[[derived]]
file = "transcript.vtt"
type = "transcription"
records = ["G8BD.SB.0000002_001", "G8BD.SB.0000002_002"]
```
- **`content/`** — **Gitignored** build artifact for Quartz site generation and vault distribution. Populated by the export step (section 3.3.3.1): assembled documents copied to `content/<slug>/`, non-text artifacts and derived files copied to `content/assets/`, index pages generated. Not committed to git.
- **`quartz.config.ts`** — Quartz configuration for the corpus site. See section 4.
- **`.capture/`** — Gitignored staging area for captured content that has not yet been reconciled into the corpus. Capture scripts write artifacts here; reconciliation moves them into `material/` with a proper `document_id`. Failed captures remain here without consuming IDs.

**The many-to-one rule:** A single document can have multiple artifacts in `material/<slug>/<document_id>/` — the same content in different formats, multiple captures from different dates, or complementary representations (a transcript plus screenshots). Each artifact has its own record. Regardless of how many records exist for a document, assembly always produces exactly **one assembled document** (`{document_id}.md`) per `document_id`.

#### 3.2.2 Document Backlog

Captured documents are self-describing — they exist as assembled documents in `material/` with complete frontmatter. The `backlog.toml` file tracks entries that are *not yet captured*: known to exist, but pending ingestion, explicitly deferred, or currently unavailable.

**Backlog entries do not have document IDs.** IDs are assigned only at reconciliation (see section 3.3.1.2), not at discovery time. This is a deliberate design choice — it means failed captures don't consume IDs, the backlog doesn't need to know about partition codes, and there are never phantom IDs referenced by no file.

```toml
[[entries]]
title = "Description of known content"
url = "https://..."                    # optional
section = "partition-slug"
status = "pending|deferred|unavailable"
priority = "high|medium|low"           # optional
notes = "Additional context"           # optional
```

See section 15.4 for complete backlog examples.

The `content_type` field on each record distinguishes what kind of content it is (`service_manual`, `technical_bulletin`, `article`, `product_documentation`). The backlog and corpus just track that it all comes from the same entity.

**Primary fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Human-readable title of the entry |
| `url` | string | no | Where this content can be acquired (for web-based origins) |
| `section` | string | no | Partition slug this entry belongs to (may be `"unknown"` if not yet categorized) |
| `priority` | enum | no | `critical`, `high`, `medium`, `low` — only applicable to `pending` entries |
| `status` | enum | yes | `pending`, `ingested`, `deferred`, `unavailable` |
| `notes` | string | no | Freeform notes about this entry or why it's in a particular status |

**Status values:**

| Status | Meaning |
|--------|---------|
| `pending` | Known to exist and belongs in this corpus. Queued for future acquisition |
| `ingested` | Successfully acquired and reconciled into the corpus. Entry remains for tracking provenance |
| `deferred` | Known to exist, explicitly deprioritized. Won't be ingested soon but tracked for completeness |
| `unavailable` | Known to exist but currently impossible to acquire (dead link, out of print, behind paywall) |

**Priority values** (only applicable to `pending` entries):

| Priority | Meaning |
|----------|---------|
| `critical` | Blocking a compendium — needed for synthesis now |
| `high` | Actively wanted for a current compendium |
| `medium` | Would improve coverage but not urgent |
| `low` | Known to exist, no current compendium needs it |

**Within-corpus references to backlog items.** Because backlog entries have no document IDs, other documents in the corpus cannot reference them by ID. If a normalized document references content that is still in the backlog, the reference is recorded as an `unresolved` relation in the document's frontmatter — the same mechanism used for cross-corpus references. Once the backlog entry is acquired and reconciled, the `unresolved` reference can be resolved to the assigned document ID.

**The backlog is not for cross-corpus references.** If a g8board post mentions a GM TSB, that reference is recorded as an `unresolved` relation in the document's frontmatter — not as a backlog entry in g8board. The TSB belongs in the `gm` corpus and would be registered there.

**Build-time validation:**

- Every assembled document (`{document_id}.md`) must have valid, complete frontmatter (if an assembled document exists, it is Assembly-complete — no stubs or placeholders)
- Every record in `material/<slug>/<document_id>/` must have a `status` field
- No assembled document without all corresponding records at `status: normalized`
- Backlog entries with `status: ingested` should have a corresponding directory in `material/`

**Ingestion backlog reporting:** The ingestion scanner generates reports from backlog data, showing pending items by priority (see section 15.4).

### 3.3 Corpus Pipeline

The path from raw content to assembled document is a three-phase pipeline: **acquisition**, **normalization**, and **assembly**. Each phase has defined steps, and formalizing them makes the pipeline reproducible, auditable, and independently improvable — you can re-assemble from improved models without re-normalizing, you can re-convert with better tools without re-downloading, and failed acquisitions never consume document IDs.

**Capture is the only step that requires access to the originating location.** Everything that follows — reconciliation, conversion, contextualization, and assembly — is fully isolated and offline-first. If additional information is needed about a source, it should be captured as its own artifact and added to the document rather than fetched on demand during later phases.

#### 3.3.1 Phase 1: Acquisition

Acquisition brings raw content into the corpus and assigns it identity. It has two steps: capture (get the content) and reconciliation (place it in the corpus structure).

##### 3.3.1.1 Capture

**What:** Acquire raw content from external sources into a staging area.

**How:** Script-driven or manual — web scrapers, downloaders, API clients, manual file copy. Capture acquires **all associated content** from the origin — the primary content (HTML page, PDF, etc.) plus any embedded or linked assets (images, supplementary PDFs, data files) that would otherwise be lost. Capture has no knowledge of corpus structure and does not presuppose where content should go within the corpus — that is reconciliation's job.

**Output:** Raw files in `.capture/<descriptive-name>/` — a gitignored staging area with no document IDs assigned. The naming convention is descriptive (e.g., `.capture/afm-delete-guide.56789/thread.html`) because IDs don't exist yet. A typical capture for a web page includes the page HTML plus all embedded images.

Capture simply acquires content; it performs no transformation and assigns no identity. Failed captures (network errors, paywalled content, corrupt downloads) remain in `.capture/` as orphans without consuming any corpus resources. The `.capture/` directory is gitignored — it is a transient workspace, not part of the versioned corpus.

An artifact may optionally have a capture metadata file alongside it containing details that aren't embedded in the artifact itself — capture timestamp, origination URL, authentication context, or scraper version. The format of capture metadata is corpus-specific (JSON, YAML, etc.) and is consumed during reconciliation.

##### 3.3.1.2 Reconciliation

**What:** Move captured content from staging into the corpus, assigning identity and creating record stubs.

**How:** Reconciliation tooling (or the ingestor agent — see section 12) determines where content belongs in the corpus structure and assigns identity. This is a hybrid process — mechanical script when all information is available, LLM-assisted when fields need to be inferred. If required frontmatter fields cannot be populated from the artifact, capture metadata, or LLM inference, the item stays in `.capture/` and the operator is prompted.

**Routing check.** Before assigning identity, reconciliation checks the content against routing claims from all corpus `{corpus_id}.toml` files (see section 3.2.3). If a routing claim from another corpus matches the content (by URL pattern, YouTube channel, or domain), reconciliation rejects the content locally and reports the redirect target. If no claims match, reconciliation proceeds normally. The LLM ingestor also reads cross-references (section 3.2.4) from the current corpus as a soft routing signal — if the content seems to belong to a cross-referenced corpus, it flags this for operator review rather than hard-rejecting.

**Operations.** Reconciliation performs one of three operations depending on whether the content is new or updates existing material:

- **Document addition.** New content that doesn't belong to an existing document. Detect the appropriate partition (from backlog `section` field, content analysis, or user input), assign the next sequential `document_id` within that partition, create the source directory in `material/<slug>/<document_id>/`, move and rename artifacts, and create record stubs.
- **Record addition.** New content that belongs to an existing document — a different edition, a supplementary file, or a newly available format. Assign the next `record_seq` within the existing document, move artifacts, and create record stubs.
- **Record update.** Replacement for an existing record — a newer capture of the same content. Replace the artifact, update the record stub's `capture_date` and `ingestion_date_last`, and reset `status` to `stub` if re-conversion is needed.

**Artifact handling.** Every captured file becomes its own artifact with a unique record_id — the primary content (HTML, PDF, etc.) and any associated files (images, supplementary documents) are each reconciled as separate artifacts within the same document. Raw files are moved from `.capture/` to `material/<slug>/<document_id>/` with standardized names (`{record_id}.{ext}` — e.g., `ADG8.RR.0000001_001.html`, `ADG8.RR.0000001_002.jpg`). If the artifact is already markdown, it is renamed to `{record_id}.txt` so that `.md` is always reserved for the record.

**Record stubs.** For each artifact, reconciliation creates a record `{record_id}.md` in the same directory — a markdown file with YAML frontmatter and no body content, with `status: stub`. The frontmatter contains all fields that can be populated from the artifact and capture metadata: `document_id`, `sequence`, `content_type`, `origin`, `source_url`, `original_filename`, `capture_date`, and any per-record metadata available.

**No document stubs.** Assembled document files are created only during Assembly (section 3.3.3). Reconciliation does not create stubs or placeholders. The work queue for downstream phases is tracked by record `status` fields in `material/`, not by assembled document existence.

**Document config.** For document additions, reconciliation creates `{document_id}.toml` in the document directory with the working `title` — derived from the backlog entry, the original content's title, or LLM inference. This is the authoritative document title until assembly may refine it.

**Backlog update.** If the reconciled content corresponds to a backlog entry, mark it as `ingested`.

**Output:** Artifacts, record stubs, and document config in `material/<slug>/<document_id>/`, ready for normalization.

#### 3.3.2 Phase 2: Normalization

Normalization transforms record stubs into complete records — filling in the markdown body and refining it across records. It has two steps: conversion (deterministic, per-artifact) and contextualization (LLM-driven, cross-record).

##### 3.3.2.1 Conversion

**What:** Deterministic conversion of each artifact's content into a markdown representation.

**How:** Content-type-specific scripts — no LLM involvement, deterministic processing only. Conversion operates on each artifact in complete isolation from other records in the same document.

**Output:** The body of the existing record stub (`{record_id}.md`) is filled with the artifact's content interpreted as markdown, and `status` is set to `draft`.

**Key principle:** Conversion captures *what's there* without editorial judgment. No summaries, no credibility assessment, no relevance decisions. It strips away format-specific noise (HTML chrome, PDF layout artifacts, ad content) and produces the artifact's content as well-formed markdown. The conversion should be unabridged — all content from the source, nothing omitted.

Format-specific handling:

| Artifact format | Conversion output |
|----------------|-------------------|
| HTML page | Clean content preserving inline HTML tags; strip navigation, styling, framework chrome |
| Data table image | OCR → markdown table |
| Regular image | `![alt text](record_id.ext)` embed |
| PDF | Text and table extraction |
| Audio / video | Transcription (Whisper, etc.) with timestamps |
| epub | Parse chapter structure, extract text |
| Forum thread HTML | Parse post boundaries, usernames, dates |
| Clean markdown | Passthrough (`conversion_method: passthrough`) |

**Trivial conversion is fine.** A clean text file gets `conversion_method: "passthrough"` — the pipeline is uniform even when a step does minimal work.

**Non-text artifacts.** Images, diagrams, and other embedded content from the origin are captured alongside the primary content and reconciled as their own artifacts with unique record_ids (section 3.3.1). Their records contain an image embed (`![alt](record_id.ext)`). During export (section 3.3.3.1), non-text artifacts are copied to `content/assets/` for Quartz rendering.

**Derived files.** Conversion may produce derived files from captured artifacts — frame grabs extracted from video, transcriptions generated from audio, OCR output from scanned images. Derived files are stored in a flat `derived/` directory within the document folder (e.g., `material/<slug>/<document_id>/derived/frame_0001.jpg`). No record_id namespacing — derivations can span multiple records. Each derivation is declared as a `[[derived]]` entry in `{document_id}.toml` with the records it was derived from. Derived files are not assigned `record_id`s — they are named descriptively (`frame_0001.jpg`, `transcript.vtt`, `page_003.txt`). Re-conversion deletes the entire `derived/` directory and regenerates its contents. The `[[derived]]` declarations in TOML are also regenerated. The record body references derived files relative to the document directory (e.g., `![frame](derived/frame_0001.jpg)`).

**Conversion provenance.** The record frontmatter records `conversion_method`, `conversion_tool`, and `conversion_date` — enabling targeted bulk re-conversion when tools improve (e.g., "find all records converted with tesseract v4 and re-convert with v5").

**Per-document instructions.** If `{document_id}.toml` contains a `prompts.conversion` section, it is provided to the conversion process as additional instructions — e.g., guidance on handling unusual page structure, gallery chrome, or format-specific quirks.

##### 3.3.2.2 Contextualization

**What:** LLM-driven cross-record refinement within a single document.

**How:** An agent loads all records for a document together and refines them with awareness of each other. Artifacts should only need to be read if the record's markdown body is insufficient.

**Operations:**

| Operation | Why contextualization |
|-----------|----------------------|
| Convert remaining HTML to better-formed markdown | Requires semantic understanding of content structure |
| Resolve internal links (image references to other artifacts in the same document) | Requires cross-record awareness |
| Improve image alt text and classification | Requires content understanding |
| Normalize formatting across records | Requires editorial judgment about consistency |
| Cross-reference related content within the document | Requires semantic understanding |
| **Surface issues** | Requires quality judgment — see below |

**Issue surfacing.** Contextualization is the first point where quality and completeness problems are identified. The agent adds an `issues` array to the record frontmatter for any problems found — dead link placeholders, data corruption in artifacts, missing or degraded content, encoding problems. Issues use the same structure as document-level issues (see section 3.6): `type`, `severity`, `description`, `remediation`.

**Per-document instructions.** If `{document_id}.toml` contains a `prompts.contextualization` section, it is provided to the contextualization agent as additional instructions — e.g., guidance on cross-referencing specific posts, resolving contradictions between records, or handling content that requires domain-specific interpretation.

**Output:** Records with refined bodies and `status: normalized`. Artifacts are not modified.

##### 3.3.2.3 Record File Format

Each record is a markdown file with YAML frontmatter containing record metadata, paired with the artifact's content interpreted as markdown in the body. See section 15.5 for a complete record frontmatter example.

The record frontmatter follows these conventions:

- **`document_id`** and **`sequence`** — identify which document and which record within that document this file corresponds to.
- **`status`** — pipeline progress. One of: `stub` (reconciliation complete, no body content), `draft` (conversion complete, body filled), `normalized` (contextualization complete, ready for assembly).
- **`content_type`** — authoritative content type. The conversion script knows what it's processing — this is a definitive classification, not a hint. Closed enum (see section 3.3.2.4 for valid types and their extended fields).
- **`origin`** — which origin within the corpus this artifact came from (matches an `origin_id` in `{corpus_id}.toml`).
- **`source_url`** and **`original_filename`** — provenance of the artifact before standardized naming.
- **`capture_date`** — when the artifact was originally acquired.
- **`body_format`** — the format of the content in the record body. One of: `html` (inline HTML preserved in markdown), `markdown` (pure markdown), `text` (plain text).
- **`ingestion_date_last`** — when we last checked/re-ingested from the upstream source. Same as `capture_date` on initial capture. Used by the ingestion scanner to prioritize re-ingestion.
- **`content_changed_last`** — when the upstream content last actually differed from what we had. Used to assess source stability.
- **`author`** — the identifiable person who produced this content. Omit for anonymous content (anonymous forum posts use the `username` extended field instead).
- **`date_published`** — when the original content was published. Omit for undated content.
- **`volatility`** — override for the origin's `default_volatility`. Only set when this record's volatility differs from the origin norm. One of: `static`, `unlikely`, `periodic`, `active`.
- **`conversion_method`**, **`conversion_tool`**, **`conversion_date`** — conversion provenance, enabling targeted bulk re-conversion when tools improve.
- **`issues`** — quality or completeness problems surfaced during contextualization. Uses the same structure as document-level issues (section 3.6).

Extended fields are content-type-specific and follow the record's `content_type`. These are programmatically determinable fields that the conversion script populates based on what it's processing. See section 3.3.2.4 for the extended fields defined for each content type.

##### 3.3.2.4 Extended Record Fields by `content_type`

The `content_type` field determines which additional fields the conversion script populates on the record. This is a closed enum — adding a new type requires defining its extended fields.

##### `forum_post`

Covers: g8board, ls1tech, performanceforums, and similar threaded discussion sites.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `username` | yes | string | Exact username of the poster on the forum (plain string, not a registry term) |
| `thread_url` | yes | string | Direct link to the thread |
| `reply_count` | no | int | Number of replies — engagement signal |

##### `reddit_post`

Covers: Reddit posts and threads. Separated from `forum_post` because Reddit's voting system provides a distinct credibility signal.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `username` | yes | string | Exact Reddit username of the poster (plain string, not a registry term) |
| `subreddit` | yes | string | Which subreddit, without the r/ prefix |
| `post_url` | yes | string | Permalink to the post |
| `score` | no | int | Net upvotes — engagement and credibility signal |
| `comment_count` | no | int | Number of comments |

##### `book`

Covers: complete published works — novels, non-fiction books, collected works. **A single document is always the entire book.** In `material/` the book may be split across many records (chapter PDFs, an epub, a complete PDF), but assembly always produces one document per work.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Canonical title of the work (e.g., "Dune") |
| `isbn` | no | string | ISBN if known |
| `word_count` | no | int | Total word count of the complete work |
| `series_name` | no | string | Name of the series (e.g., "Dune Chronicles") |
| `series_position` | no | int | Position in the series (e.g., 1) |

##### `service_manual`

Covers: OEM service manuals, workshop manuals. Each section of the manual is a separate document — the manual as a whole is too large for a single file and sections are independently useful.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `manual_title` | yes | string | Which manual this section comes from |
| `section_reference` | yes | string | The manual's own section numbering |
| `model_years` | yes | string[] | Which model years this applies to |
| `vehicle_system` | no | string | Engine, suspension, electrical, etc. |

##### `technical_bulletin`

Covers: TSBs, recall notices, errata, and similar official corrections or advisories.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `bulletin_number` | yes | string | Official identifier (e.g., PI0597B) |
| `affected_models` | yes | string[] | Which models are covered |
| `affected_years` | yes | string[] | Which years are covered |

##### `video`

Covers: YouTube videos, instructional content, any video-first content. Each video is one document containing the transcript and, where relevant, descriptions of visual content.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `duration_seconds` | yes | int | Video length |
| `channel_name` | no | string | Channel or creator name, if not obvious from the origin |

##### `podcast`

Covers: Audio-first content — podcast episodes, radio segments, audiobook supplements. Each episode is one document file.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `duration_seconds` | yes | int | Episode length |
| `episode_number` | no | int | Episode number in the series |
| `series_name` | no | string | Name of the show or series |

##### `research_paper`

Covers: Academic publications — journal articles, conference papers, preprints.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `journal` | yes | string | Publication venue |
| `peer_reviewed` | yes | bool | Whether the paper is peer-reviewed |
| `doi` | no | string | DOI if available |

##### `article`

Covers: News articles, blog posts, Wikipedia articles, and other web-published written content.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `article_url` | yes | string | Link to the article |
| `publication` | no | string | Name of the outlet or site |

##### `screenplay`

Covers: Film, television, and stage scripts.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Title of the production |
| `medium` | yes | enum | `film`, `television`, `stage` |
| `draft` | no | string | Which draft, if known |

##### `product_documentation`

Covers: Product datasheets, catalogs, user guides, safety data sheets, and manufacturer documentation.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `product_name` | yes | string | Name of the product |
| `manufacturer` | yes | string | Who makes it |
| `document_type` | no | enum | `datasheet`, `catalog`, `guide`, `sds` |
| `part_numbers` | no | string[] | Associated part numbers |

#### 3.3.3 Phase 3: Assembly

**What:** Compile all normalized records for a document into a single, well-formatted document markdown file.

**How:** An assembly agent (see section 12.4) reads `{document_id}.toml` for the working title and any `prompts.assembly` instructions, then reads all records for a document, structures their content into a coherent document, and generates LLM-dependent frontmatter. The title from the TOML is used as input — the assembler may refine it based on content understanding.

**Precondition:** Assembly only operates on documents where **every** record has `status: normalized`. If any record is still `stub` or `draft`, the document is not ready for assembly.

**Output:** `material/<slug>/<document_id>/{document_id}.md` — the assembled document is co-located with its records and artifacts. Created during this phase, not stubbed by any earlier phase. If the document already exists (re-assembly), it is replaced.

**The assembly agent is responsible for:**

| Operation | Why assembly |
|-----------|-------------|
| Generate `description` | Requires content understanding across all records |
| Assess `credibility_tier` | Requires domain judgment |
| Identify `relations` | Requires cross-document awareness |
| Aggregate `issues` | Collects record-level issues into document-level summary |
| Structure the markdown body | Requires editorial decisions about presentation and ordering |
| Populate the `records` array | Requires mapping records to the document they produce |

**Obsidian-native output.** Assembled documents use Obsidian-compatible formatting:

- **Wiki-links** for cross-document references: `[[ADG8.LO.0000003|Component Locations]]`
- **Callout blocks** for warnings and notes: `> [!note]`, `> [!warning]`
- **Tags and aliases** in frontmatter for Obsidian navigation
- **Relative image paths** to co-located files: `![alt]({record_id}.{ext})` for captured artifacts, `![alt](derived/{filename})` for derived files

The spec defines what the assembly agent receives and produces without prescribing implementation form. The assembly agent definition lives in the corpus repo's `.claude/agents/` directory (see section 12.4), enabling corpus-specific customization while following a standardized pattern.

##### 3.3.3.1 Export

**What:** Build the gitignored `content/` directory from assembled documents for Quartz site generation and vault distribution.

**How:** An export step scans `material/` for assembled `{document_id}.md` files (identifiable by the `XXXX.TT.NNNNNNN.md` naming pattern — no underscore suffix), copies them to `content/<slug>/`, copies referenced non-text artifacts and derived files to `content/assets/`, generates partition index pages, and rewrites image paths from relative co-located references to the `content/` structure.

**Output:** A complete `content/` directory ready for Quartz build or vault distribution. This directory is gitignored — it is a build artifact, not committed content.

**Operations:**

- **Copy assembled documents** from `material/<slug>/<document_id>/{document_id}.md` to `content/<slug>/{document_id}.md`
- **Copy non-text artifacts and derived files** to `content/assets/`
- **Rewrite image paths** from relative (`{record_id}.{ext}`, `derived/{filename}`) to `content/` structure (`assets/{filename}`)
- **Generate index pages** — corpus overview (`content/index.md`) and partition overviews (`content/<slug>/index.md`)

#### 3.3.4 Phase Boundaries and Re-processing

The five pipeline steps are designed to be independently re-runnable:

- **Re-capture** (Acquisition only): Re-acquire from the upstream source when content may have changed. Content lands in `.capture/` as fresh staging. Does not trigger downstream steps unless the acquired content actually differs.
- **Re-reconciliation** (Acquisition only): Rarely needed — typically only when a document needs to be reassigned to a different partition.
- **Re-conversion** (Normalization only): Re-convert from existing artifacts when conversion tools improve (e.g., "find all records converted with tesseract v4 and re-convert with v5"). The `conversion_method` and `conversion_tool` record fields enable targeted bulk re-conversion. Re-conversion deletes `derived/` for affected documents and regenerates derived files.
- **Re-contextualization** (Normalization only): Re-run LLM refinement on existing records when models improve. Requires records to be at least `draft` status.
- **Re-assembly** (Assembly only): Re-assemble from existing normalized records when assembly logic or models improve. This is the cheapest re-processing scenario — no re-downloading, no re-converting.

Records are persisted alongside artifacts in `material/` to enable this independence. Conversion is often the expensive step (OCR, Whisper transcription), and the resulting records are small compared to raw artifacts. Compendiums clone `material/` and `{corpus_id}.toml` (sparse checkout) — assembled `{document_id}.md` files are identifiable by the naming pattern (no underscore suffix). The `.capture/` staging area is never needed downstream.

#### 3.3.5 Graduation and the Classification Chain

**Graduation** is the process of moving documents from one corpus to another along the **classification chain** — the specificity spectrum from broad to specific organizational homes. Documents start in the most unambiguous container available (a source corpus or triage) and graduate toward increasingly specific homes as the corpus ecosystem matures.

The classification chain typically runs: **triage → source corpus → domain corpus → entity corpus**. Not every document traverses the full chain — many remain in source corpora indefinitely, and that's fine. The chain describes the *direction* of organizational refinement, not a mandatory path.

**Artifact immutability.** Throughout the classification chain, captured artifacts (the original HTML, PDF, video, etc.) are immutable — they are never modified, only relocated. Records (markdown representations) may be re-contextualized in the new corpus's context (optional `--reset-status`), but the underlying artifact content is fixed. IDs are remapped to the target corpus's namespace, but the material itself transfers intact.

**When to graduate:**

- **Dedicated corpus created.** The most common trigger: a new corpus is created for a voice or subject that was previously triaged. All triage content matching that voice or subject graduates out.
- **Classification refinement.** A subject has accumulated enough documents across sources to justify a more specific organizational home — either a dedicated partition in a domain corpus, or its own entity corpus. An episode of Battlestar Galactica might graduate from triage to a television corpus, then later to a dedicated BSG entity corpus.
- **Domain accumulation.** Content in triage has accumulated enough mass around a single voice or subject to justify a dedicated corpus.
- **Wrong corpus.** Content was captured into the wrong corpus — the operator recognizes it belongs elsewhere.

**Process:**

1. **Copy records and derived files.** The document's entire source directory (`material/<slug>/<document_id>/`) including artifacts, records, document config, and `derived/` subdirectories is copied to the target corpus.
2. **Remap IDs.** The `document_id` and all `record_id`s are remapped to the target corpus's namespace — new `corpus_id`, new `partition_code` (determined by target partition), new `document_seq` (next available in target). Record frontmatter is updated to reflect the new IDs.
3. **Preserve status by default.** Graduated documents retain their pipeline status (`stub`, `draft`, `normalized`). The operator can request a status reset with `--reset-status` to force re-normalization in the target corpus context — useful when the target corpus has different contextualization guidance.
4. **Record lineage.** The target document's `{document_id}.toml` includes `original_document_id` — the document's ID in the source corpus. This preserves provenance: you can always trace a graduated document back to where it came from.
5. **Leave tombstone.** The source corpus's assembled document is replaced with a tombstone — a minimal document that records where the content went. If the document hadn't been assembled yet, the tombstone is created at this point.

**Tombstone format:** The tombstone includes the original `document_id`, `title`, `status: graduated`, `graduated_to`, `graduated_corpus`, and `graduation_date`. The body contains a redirect notice with a link to the new location. See section 15.5 for the complete format.

Tombstones are rendered as redirect notices in the corpus site — a reader browsing the triage corpus sees that the content has moved and where to find it.

**Batch graduation.** Graduation supports batch operations:

- **By routing match.** Graduate all triage documents whose URLs match a newly created corpus's routing claims.
- **By subject/topic.** Graduate all triage documents identified as belonging to a specific voice or subject (operator-selected or LLM-assisted).
- **By operator selection.** Manual selection of specific documents for graduation.
- **By partition.** Graduate an entire partition to its own corpus when it has accumulated enough mass. For example, the Gorguts partition within a music entity corpus could graduate to its own `gorguts` corpus when the discography and associated material justify standalone organization.

**Chain graduation.** A document may graduate multiple times through the classification chain. Each hop creates a new tombstone in the source corpus and records lineage in the target. The full chain is reconstructable by following tombstones forward from the original corpus. Example:

1. BSG episode Wikipedia page captured → `TRGE.WB.0000042` (triage)
2. Television corpus created → graduates to `TVSH.EP.0000015` (tombstone left in triage)
3. BSG entity corpus created → graduates to `BSGF.EP.0000001` (tombstone left in television)

Each hop's `original_document_id` tracks the immediate predecessor, not the ultimate origin.

**Lineage in target `{document_id}.toml`:** The target document's TOML includes `original_document_id` tracking the immediate predecessor. See section 15.5 for the complete lineage format.

### 3.4 Document Format

Every assembled document is a single markdown file with structured YAML frontmatter. The frontmatter carries document identity, a description for discovery, quality metadata, and a lightweight `records` array linking to the records that were used to produce it. Per-record metadata — content type, author, dates, and content-type-specific fields — lives on the records (section 3.3.2.3), not the document. Documents are created during Assembly (section 3.3.3) and only exist as assembled documents in `material/` when complete.

#### 3.4.1 Required Fields

Every document file must include all of these fields, no exceptions:

| Field | Type | Description |
|-------|------|-------------|
| `document_id` | string | `XXXX.TT.NNNNNNN` globally unique identifier (`corpus_id` + `partition_code` + `document_seq`) |
| `title` | string | Short descriptive label for the document (not necessarily the work's canonical title) |
| `description` | string | One-to-three sentence description of what this document contains and why it's useful. Generated during assembly. Enables synthesis-time relevance assessment without reading the full content |
| `credibility_tier` | enum | `authoritative`, `expert`, `community_validated`, `anecdotal`, `speculative`. See section 3.5 |
| `normalization_confidence` | float | `0.0`–`1.0`, quality of the conversion and assembly process. See section 3.5.1 |
| `normalization_model` | string | Model or tool that performed assembly (e.g., `claude-sonnet-4-5-20250514`) |
| `normalization_date` | date | When assembly was last performed. **This is the field the compendium layer compares against to determine if re-synthesis is needed** — it captures both content changes and re-assembly with improved models |
| `records` | array | One entry per record used to produce this document. See section 3.4.3 |

#### 3.4.2 Optional Fields

These fields are present on some documents but legitimately absent on most:

| Field | Type | When absent |
|-------|------|-------------|
| `tags` | string[] | No Obsidian navigation tags applicable |
| `aliases` | string[] | No alternative titles for Obsidian wiki-link resolution |
| `relations` | array | No explicit references to other documents. See section 3.7 |
| `issues` | array | No known quality or completeness problems. See section 3.6 |
| `status` | enum | Only present on tombstones: `graduated`. Absent on normal documents (document existence = complete) |
| `graduated_to` | string | Target `document_id` after graduation. Only present when `status: graduated` |
| `graduated_corpus` | string | Target `corpus_id` after graduation. Only present when `status: graduated` |
| `graduation_date` | date | When the document was graduated. Only present when `status: graduated` |

#### 3.4.3 Records Array

Each entry in the `records` array links to one record used to produce this document. The record (in `material/<slug>/<document_id>/`) holds the full per-record metadata — content type, author, dates, and content-type-specific fields. The document frontmatter carries only a reference and a human-readable identifier.

| Field | Type | Description |
|-------|------|-------------|
| `record_id` | string | Identifies the artifact and its record: `{document_id}_{record_seq}` (e.g., `G8BD.SB.0000001_001`) |
| `source_url` | string | URL of the original content. Use `original_filename` instead for offline sources |
| `original_filename` | string | Filename of the original content. Use when `source_url` is absent |

#### 3.4.4 Complete Example

See section 15.5 for a complete assembled document with all applicable fields, including relations, issues, and body content.

### 3.5 Credibility Tiers

Each document is rated for trustworthiness:

| Tier | Description | Examples |
|------|-------------|----------|
| `authoritative` | Official or primary source documentation | OEM service manual, published TSB, peer-reviewed research, original text of a novel |
| `expert` | Credentialed professional with demonstrated expertise | Professional mechanic writeup, licensed practitioner guide, scholarly analysis |
| `community_validated` | Claim independently confirmed by multiple people | Forum fix confirmed by 5+ unrelated users |
| `anecdotal` | Single person's experience, unconfirmed | One forum post describing a symptom |
| `speculative` | Theory or hypothesis without supporting evidence | "I think it might be the alternator" |

For fiction origins, `authoritative` means the primary text itself. `expert` would be published literary criticism. `community_validated` might be widely-accepted fan analysis. The tiers adapt naturally to any domain.

#### 3.5.1 Normalization Confidence

The `normalization_confidence` field (`0.0`–`1.0`) rates the quality of the conversion process itself — how accurately the raw source was captured and converted to markdown. This is distinct from credibility (trustworthiness of claims) and distinct from the description (what it's about).

A perfectly transcribed YouTube video might have high normalization confidence but low credibility tier. A badly OCR'd service manual might have low normalization confidence but authoritative credibility.

### 3.6 Document Issues

Normalized documents can declare known quality or completeness problems via the `issues` array. This is distinct from `normalization_confidence` — confidence rates how well the conversion went for what we had, while issues flag what we're missing or what has degraded.

The `issues` field is universal optional. Its absence means "no known issues." Each issue includes `type`, `severity`, `description`, `remediation`, and `resolved` fields. See sections 3.6.1-3.6.3 for valid values and section 15.5 for a complete example.

#### 3.6.1 Issue Types

| Type | Description |
|------|-------------|
| `missing_media` | Images, videos, or embedded content no longer available at the original location |
| `broken_links` | Referenced URLs within the document content are dead |
| `partial_content` | Content was truncated, paywalled, or incompletely captured |
| `content_modified` | Content has been edited since original publication — original version may differ from current |
| `encoding_corruption` | Garbled text, mojibake, or mangled characters |
| `format_loss` | Tables, diagrams, code blocks, or formatting that didn't survive conversion |

#### 3.6.2 Severity Levels

| Severity | Meaning |
|----------|---------|
| `critical` | Document is essentially unusable without remediation — key content is missing or corrupted |
| `major` | Significant information loss but document is still partially useful |
| `minor` | Cosmetic or non-essential content affected |

#### 3.6.3 Remediation Actions

| Remediation | Description |
|-------------|-------------|
| `wayback_snapshot` | Retrieve an archived version from the Wayback Machine |
| `alternate_source` | Same content may be available from a different origin |
| `original_author` | Could contact the original author for missing material |
| `re_ingest` | Re-capture from origin may resolve (e.g., temporary outage, encoding fix) |
| `manual_reconstruction` | Requires human effort to reconstruct from context |
| `none` | No remediation needed or possible |

The `resolved` boolean tracks whether the issue has been addressed. The typical workflow: normalization flags dead images → issue is logged with `remediation: "wayback_snapshot"` → Wayback snapshot is retrieved and added to `material/<slug>/<document_id>/` → document is re-assembled from improved raw material → issue is marked `resolved: true`. The issue remains in frontmatter as a historical record.

For the `content_modified` type, the remediation may involve pulling both the current version and a Wayback snapshot as separate raw files. A forum post edited to add "UPDATE: don't do this, it caused X" is more valuable with both versions visible — the normalization can reconcile them or note the differences.

Build-time scanning can surface unresolved issues as a prioritized remediation queue (see section 15.5 for example output).

### 3.7 Document Relations

Normalized documents can declare explicit relationships to other documents. These capture **intrinsic relationships** — objective facts about the document that are evident at normalization time. A forum post linked to another thread. A novel is the sequel to another novel. A revised TSB supersedes an earlier one. These are unchallengeable observations captured when the material is being read.

```yaml
relations:
  - type: "sequel_to"
    document_id: "FHBT.NV.0000001"      # Dune Messiah is a sequel to Dune
  - type: "reply_to"
    document_id: "G8BD.SB.0000001"      # this forum post replies to that thread
  - type: "adaptation_of"
    document_id: "FHBT.NV.0000001"      # Villeneuve screenplay adapts the novel
  - type: "supersedes"
    document_id: "GMOT.TB.0000004"      # revised TSB replaces an earlier one
  - type: "references"
    unresolved: "GM TSB #PI0597B"      # cross-corpus reference not yet resolved
```

**Relation types:**

| Type | Meaning | Example |
|------|---------|---------|
| `sequel_to` | Next in a sequence | Dune Messiah → Dune |
| `preceded_by` | Previous in a sequence | Dune → Dune Messiah |
| `reply_to` | Direct response to another document | Forum reply → parent thread |
| `references` | Explicitly cites or links to | Forum post → TSB it mentions |
| `adaptation_of` | Creative adaptation of original material | Screenplay → novel |
| `supersedes` | Replaces or updates | Revised TSB → original TSB |
| `superseded_by` | Has been replaced by | Original TSB → revised TSB |
| `contradicts` | Explicitly disagrees with | One forum post refuting another |

**Cross-corpus references** are particularly valuable. A g8board post may reference a GM TSB that lives in a different corpus repo. At normalization time, the referenced document's ID may not be known yet. The `unresolved` field captures the reference in human-readable form. As the corpus ecosystem grows, a periodic reconciliation pass can attempt to resolve these against all known document IDs.

**Discovered relationships** — connections identified during synthesis rather than present in the document itself ("this post describes the same failure mode as that manual section") — belong in the compendium layer, not document frontmatter. Document relations are strictly what the document itself declares or implies.

#### 3.7.1 Corpus Discovery via Relations

Document relations serve as a **dependency discovery mechanism** for compendiums. When building a compendium, a build-time analysis can scan all `relations` across filtered documents, collect every `document_id` prefix that points to a corpus not currently declared as a dependency, and surface it as a recommendation:

```
Corpus Dependency Analysis for Compendium/commodore-ve:
  Currently declared: G8BD (g8board), GMOT (gm)

  Referenced but not included:
    LSTK (ls1tech)         — 15 documents reference this corpus
    HLDN (holden)          — 3 documents reference this corpus
    PFRM (performanceforums) — 4 documents reference this corpus

  Unresolved references:
    "GM TSB #PI0597B"      — referenced by 8 documents
    "Holden WSM Section 4" — referenced by 3 documents
```

This turns the relation graph into an organic growth signal — the documents themselves tell you which corpora you should be pulling in. The more references to a missing corpus, the stronger the signal that including it would improve synthesis quality.

### 3.8 Exotic Origin Types

The corpus-as-repo pattern supports any content type. The only requirement is a pipeline that can acquire, normalize, and assemble the content into markdown with frontmatter. The conversion step (see section 3.3.2.1) handles format-specific programmatic transformation; contextualization handles LLM-driven refinement; assembly compiles records into the final document.

**YouTube channels:** Capture downloads the video/audio. Conversion runs a transcription tool (e.g., Whisper) and captures frame data, producing a record with timestamped transcript segments and visual content metadata. Contextualization refines the transcript and surfaces any issues. Assembly then compiles the record into the final document with description, credibility assessment, and structured frontmatter. Each video is one document.

```yaml
---
document_id: "ENEX.VD.0000017"
title: "Engineering Explained — Why Direct Injection Causes Carbon Buildup"
description: "Technical explainer covering the mechanism by which direct injection engines accumulate carbon deposits on intake valves, why port injection doesn't have this problem, and what solutions exist including walnut blasting and dual injection systems."
credibility_tier: "expert"
normalization_confidence: 0.85
normalization_model: "claude-sonnet-4-5-20250929"
normalization_date: "2026-02-01"

records:
  - record_id: "ENEX.VD.0000017_001"
    source_url: "https://youtube.com/watch?v=..."
---

[transcript with timestamps and descriptive notes for visual content]
```

**Authors (fiction):** Conversion handles format transformation (epub parsing, OCR for scanned editions). Each work is normalized into one or more document files — a short story as one file, a novel potentially split into chapters. The primary text is `authoritative` credibility. Introductions, afterwords, and interviews are tagged separately.

**Podcasts:** Similar to YouTube — conversion runs the transcription tool, contextualization refines the result. One episode per document file.

**Government / institutional sources:** Conversion handles PDF text extraction, OCR, and table recognition. Contextualization and assembly interpret the content into the final document. Each publication is one document file.

**TV franchises:** A franchise corpus (section 3.1.2) draws from multiple heterogeneous origins per episode. Each episode is one document with records from different origins — the episode transcript (from audio extraction), Wikipedia episode summary, IMDB page, Reddit discussion, and production script. Conversion handles each origin type differently (Whisper for audio, web scraping for Wikipedia/IMDB/Reddit, PDF extraction for scripts). Contextualization cross-references the records, resolving contradictions and enriching details. Assembly compiles all records into a comprehensive episode document. Derived files (frame grabs, transcription VTTs) are stored in `derived/` and copied to `content/assets/` during export.

---

## 4. Corpus Format

### 4.1 Overview

Corpora are not just data stores — they are browsable references. Each corpus publishes as a Quartz static site and can be opened as an Obsidian vault. Every assembled document is readable in a web browser or Obsidian. This serves three purposes: human review of assembled documents without opening raw files, a navigable corpus overview organized by partition, and a shareable reference that can be hosted independently of the compendium layer.

### 4.2 Quartz Configuration

Each corpus repository contains a `quartz.config.ts` at its root that configures the Quartz static site generator. Quartz builds from the gitignored `content/` directory (populated by export — see section 3.3.3.1) and produces a static site with navigation, search, and graph view.

Key properties:

- **Content source** — `content/` directory (gitignored, populated by export step)
- **Frontmatter handling** — Quartz natively uses YAML frontmatter for page metadata, tags, and title — no stripping needed
- **Build output** — `public/` directory (gitignored), deployed to Caddy server
- **Search** — Quartz generates a client-side search index covering all pages
- **Graph view** — wiki-links between documents produce an interactive relationship graph

### 4.3 Content Organization

Partitions become directories in the corpus site. The export step generates `content/<slug>/index.md` overview pages for each partition and a `content/index.md` corpus overview. Quartz auto-generates folder navigation from the directory structure — no manual table of contents is needed.

Documents in `content/` use the format `{document_id}.md` for consistent naming. Quartz renders partition directories as navigable sections with the partition overview as the landing page.

### 4.4 Hosting

Corpus sites are hosted at `corpus.example.org/{corpus_id}/`:

```
https://corpus.example.org/g8board/          → G8Board corpus site
https://corpus.example.org/frank-herbert/    → Frank Herbert corpus site
https://corpus.example.org/gm/              → General Motors corpus site
```

CI/CD for corpus sites follows the same pattern as compendium deployment (see section 9): push to main triggers export + Quartz build, and the output is deployed to the Caddy server. The corpus CI workflow is simpler than the compendium workflow because there are no corpus dependencies to resolve.

### 4.5 Obsidian Vault Usage

The `material/` directory (or the exported `content/` directory) can be opened directly as an Obsidian vault for local browsing. This provides:

- **Graph view** — wiki-links between assembled documents create a visual relationship map
- **Full-text search** — Obsidian's search across all assembled documents
- **Tag navigation** — frontmatter tags enable tag-based browsing
- **Backlinks** — automatic backlink discovery between documents

### 4.6 Relationship to Compendium

A corpus site and a compendium site serve different purposes from the same underlying technology:

| Aspect | Corpus Site | Compendium Site |
|--------|-------------|-----------------|
| **Content** | All assembled documents, unfiltered | Synthesized, curated domain reference |
| **Organization** | By partition (voice-based or subject-based) | By domain taxonomy (what it's about) |
| **Authorship** | Normalization agent (faithful to source) | Synthesis agent (editorial judgment) |
| **Audience** | Corpus maintainer, QA review | End users, domain agents |
| **Scope** | Single voice or subject | Multiple corpora, cross-entity synthesis |

The corpus site is a raw reference — every document in the corpus is visible and browsable. The compendium is a synthesized view — it selects, filters, and reorganizes content from multiple corpora into a coherent domain reference. A developer reviewing normalization quality browses the corpus site. A user or agent seeking domain knowledge browses the compendium.

---

## 5. Corpus Discovery

### 5.1 Overview

Corpus discovery enables compendiums to identify which corpora are relevant to their domain without cloning and scanning every corpus repository. Each corpus's `{corpus_id}.toml` carries tiered summaries that describe the corpus (see section 3.2 for format). At compendium setup time, these summaries are fetched via the Forgejo API — no separate registry repository is needed.

This design follows the spec's principle of avoiding unnecessary infrastructure. The corpora describe themselves; discovery is a computed view over the Corpus organization, not a maintained artifact.

### 5.2 Summary Tier Format

Each `{corpus_id}.toml` includes three summary tiers alongside the corpus's registration metadata. Each tier is a string field in `{corpus_id}.toml`. Tier 1 is a single sentence for quick include/exclude. Tier 2 is a concise paragraph confirming relevance. Tier 3 is comprehensive — full scope, document count, coverage areas. See section 15.7 for a complete example.

The tiers are designed for progressive disclosure:

- **`summary_tier1`** — A single sentence. Enough to include or exclude at a glance.
- **`summary_tier2`** — A concise paragraph. Enough to confirm relevance and understand scope.
- **`summary_tier3`** — A comprehensive description. Full detail on what the corpus contains, its document count, and its coverage.

### 5.3 API-Driven Discovery Process

Discovery tooling fetches summaries from the Forgejo API without cloning any repos:

1. **Enumerate corpora.** `GET /api/v1/orgs/corpus/repos` — list all repositories in the Corpus organization. Each repo is one corpus.

2. **Fetch corpus metadata.** For each repo, `GET /api/v1/repos/corpus/{name}/contents/{name}.toml` — fetch the file contents via API. These requests are parallelized.

3. **Parse and extract.** Parse each `{corpus_id}.toml` and extract `corpus_id`, `summary_tier1`, `summary_tier2`, `summary_tier3`.

4. **Build routing table.** Extract `[[routing]]` entries from all corpus TOMLs and compile into a unified routing table. This table is used during reconciliation (section 3.3.1.2) to check content claims before ingesting.

This produces a complete discovery index and routing table from live data in seconds, even for hundreds of corpora. The index can be cached locally and refreshed on demand.

### 5.4 Progressive Disclosure Process

The tiered summary structure enables efficient corpus selection at compendium setup time:

1. **Tier 1 scan.** Read the `summary_tier1` for every corpus. At one sentence each, all corpora fit in a single LLM context window. Immediately identify obvious candidates and obvious exclusions. For a Dune compendium: `frank-herbert`, `brian-herbert`, `denis-villeneuve`, `scifi-channel-dune` are obvious candidates. `g8board`, `gm`, `penrite` are obvious exclusions.

2. **Tier 2 confirmation.** For each candidate, read `summary_tier2` to confirm relevance and understand scope. This catches false positives (a corpus whose name suggests relevance but whose content doesn't match) and surfaces additional context about what each corpus actually contains.

3. **Tier 3 deep dive.** Consult `summary_tier3` only when needed — when scope boundaries are unclear or when understanding the full contents matters for the compendium's design. This is optional for most corpora.

4. **Declare dependencies.** Register the selected corpora in `compendium.toml`.

5. **Document-level selection.** After resolving (cloning) declared corpora, read individual document file descriptions within each corpus to select which documents feed into synthesis. The compendium's synthesis system prompt guides the LLM's selection decisions at this level.

This process is typically performed once during compendium setup and revisited when new corpora are added to the organization.

### 5.5 Summary Maintenance

Because summaries live in `{corpus_id}.toml` — the same file that defines everything else about the corpus — maintenance is straightforward:

- **New corpus.** When a new corpus repository is created, its `{corpus_id}.toml` includes tiered summaries from the start. No separate registry entry to create.
- **Summary updates.** When a corpus grows significantly (new documents added, coverage expanded), update the summary tiers in `{corpus_id}.toml`. This is a single-file commit in the corpus repo.
- **No sync burden.** There is no separate registry to keep in sync with corpus repos. The summaries are always authoritative because they live at the source.
- **Routing claims immediately discoverable.** When a new corpus adds `[[routing]]` entries to its TOML, those claims are immediately available to any reconciliation tooling that refreshes the routing table via the API. No separate registration step is needed.

---

## 6. Compendium Synthesis

### 6.1 Repository Structure

Each compendium repository has this structure:

```
Compendium/{domain}/
├── .gitignore                     # ignores corpora/ (resolved at build time)
├── corpora/                       # resolved corpus repos (gitignored, like node_modules)
│   ├── g8board/                   → resolved (sparse: material/ + g8board.toml)
│   ├── gm/                        → resolved (sparse: material/ + gm.toml)
│   └── ls1tech/                   → resolved (sparse: material/ + ls1tech.toml)
├── content/                       # compendium content (committed — authors write directly)
│   ├── introduction.md
│   ├── quick-reference.md
│   ├── faq.md
│   ├── glossary.md
│   ├── references.md              # master document registry
│   └── {chapter-slug}/            # chapters organized by domain taxonomy
│       ├── {section}.md
│       └── ...
├── compendium.toml                # compendium configuration (dependencies, system prompt, etc.)
├── quartz.config.ts               # Quartz configuration
├── resolve.sh                     # clones/updates corpora from declared dependencies
└── README.md
```

### 6.2 Dependency Resolution

Compendium repos need the `material/` directory and `{corpus_id}.toml` from each corpus. Assembled `{document_id}.md` files within `material/` are identifiable by naming pattern (no underscore suffix). Cross-references declared in selected corpora's `{corpus_id}.toml` (section 3.2.4) surface additional corpus candidates — when resolving dependencies, tooling can check cross-references and recommend corpora not yet declared. Each corpus dependency is declared in `compendium.toml` with a pinned commit hash and the sparse paths to check out:

```toml
[[compendium.corpora]]
name = "g8board"
repo = "corpus/g8board"
commit = "a1b2c3d"
sparse = ["material/", "g8board.toml"]
```

The `corpora/` directory is gitignored — it is populated on demand by a `resolve.sh` script that iterates over corpus dependencies, performs a sparse checkout of `material/` and `{corpus_id}.toml` at the pinned commit, and places the result under `corpora/{corpus_id}/`. See section 15.8 for the complete script.

This script is run once after cloning the compendium repo, before synthesis, and by the CI workflow on every build. Because `corpora/` is gitignored, the compendium repo itself stays clean — only the manuscript, configuration, and tooling are versioned.

### 6.3 The Synthesis Process

Synthesis transforms source material from multiple corpora into a coherent, structured compendium. This is the core intellectual work of the system.

The process for each compendium:

1. **Resolve corpora.** Run `resolve.sh` to clone/update all declared corpus dependencies at their pinned commits.
2. **Select documents.** Read the `description` field of each document file across all resolved corpora. Using the compendium's synthesis system prompt as context, the LLM selects documents relevant to the domain. Documents are prioritized by credibility tier and relevance to the compendium's scope.
3. **Organize by taxonomy.** Group selected documents by the compendium's chapter structure.
4. **Synthesize chapters.** Distill the grouped documents into coherent prose, reconciling conflicts, identifying patterns, and citing document IDs.
5. **Build navigation.** Generate cross-references and supplementary sections (FAQ, glossary, quick reference).
6. **Build output.** Run Quartz to compile the `content/` directory into the published static site.

### 6.4 Compendium Configuration

Each compendium repo contains a `compendium.toml` that declares its corpus dependencies and a synthesis system prompt that encodes domain-specific knowledge:

```toml
[compendium]
name = "Dune Universe Compendium"
description = "Comprehensive reference for the Dune universe across all media"
system_prompt_file = "synthesis-prompt.md"

[[compendium.corpora]]
name = "frank-herbert"
repo = "corpus/frank-herbert"
commit = "b2c3d4e"
sparse = ["material/", "frank-herbert.toml"]

[[compendium.corpora]]
name = "brian-herbert"
repo = "corpus/brian-herbert"
commit = "a1b2c3d"
sparse = ["material/", "brian-herbert.toml"]

[[compendium.corpora]]
name = "denis-villeneuve"
repo = "corpus/denis-villeneuve"
commit = "c3d4e5f"
sparse = ["material/", "denis-villeneuve.toml"]

[[compendium.corpora]]
name = "scifi-channel-dune"
repo = "corpus/scifi-channel-dune"
commit = "f7e8d9c"
sparse = ["material/", "scifi-channel-dune.toml"]
include_all = true          # every document in this corpus is relevant — skip description assessment
```

The `system_prompt_file` points to a markdown file in the compendium repo that provides the LLM with domain context during synthesis. The system prompt defines domain scope, document selection criteria, key relationships, and synthesis guidelines. See section 15.8 for a complete example.

This system prompt is iterable. When synthesis produces gaps (e.g., it conflates two characters, or misses a key relationship), the system prompt is refined and synthesis is re-run. The feedback loop is: synthesize → review → refine prompt → re-synthesize.

The `include_all = true` flag is an efficiency optimization for corpora where every document is known to be in scope (e.g., `scifi-channel-dune` is entirely Dune content). It skips the description assessment step for that corpus.

### 6.5 Synthesis Principles

- **Cite documents.** Every factual claim in the compendium references the document ID(s) it derives from. The reader (human or agent) can always trace a claim back to a specific file in a specific corpus.
- **Represent disagreement.** When the service manual says one thing and 30 forum posts say another, the compendium captures both positions with their respective credibility tiers.
- **Aggregate patterns.** If 40 forum posts describe the same failure mode, the compendium entry reflects the pattern (common mileage range, symptoms, root cause) rather than citing each post individually.
- **Respect credibility tiers.** Higher-tier documents carry more weight in synthesis. An `authoritative` document is not overruled by `anecdotal` reports unless the volume and consistency of community experience is overwhelming.
- **Structure for navigation.** Chapters follow the domain's natural taxonomy. Each chapter is self-contained but cross-references related chapters.
- **Leverage document relations.** When documents declare explicit relationships (`contradicts`, `supersedes`, `references`), the synthesis step should incorporate these signals. A document that `contradicts` another is a flag for the compendium to present both positions. A TSB that `supersedes` an earlier one means the earlier guidance may be outdated.
- **Respect document issues.** Documents with unresolved `critical` or `major` issues should be weighted accordingly. A document flagged with `missing_media` of `major` severity may be missing key visual information. The compendium can still use it but should note the gap rather than treating the document as complete.

### 6.6 Versioning

Git provides version control at both layers:

- **Corpus repos** track when documents were added or corrected. The full history of normalization is preserved.
- **Compendium repos** track when synthesis was performed, what changed, and which corpus versions were used. Because `compendium.toml` pins each corpus to a specific commit, compendium builds are reproducible.

---

## 7. Compendium Format

### 7.1 Quartz

The compendium is built as a **Quartz** site — a static site generator designed for Obsidian-style markdown with wiki-links, tags, and graph view. Quartz was selected because:

- Content is plain markdown in git (the single source of truth)
- Generates clean, navigable HTML with built-in full-text search
- Auto-generated folder navigation from directory structure
- Wiki-links produce an interactive graph view of relationships
- Frontmatter is natively used for page metadata (no stripping needed)
- Supports embedded images for diagrams, photos, and visual references
- Generates a client-side search index for programmatic full-text search
- Node.js-based, fast builds

### 7.2 Textbook Structure

Each compendium follows a consistent structural pattern:

| Section | Purpose |
|---------|---------|
| **Introduction** | Domain overview, scope, how to use this compendium |
| **Quick Reference** | High-frequency lookups — specs, part numbers, key facts |
| **Chapters** | The body of knowledge, organized by domain taxonomy |
| **FAQ** | Common questions that don't fit neatly into a single chapter |
| **Glossary** | Domain-specific terminology definitions |
| **References** | Master registry of all corpora and documents with credibility tiers |

### 7.3 Navigation Aids

Quartz auto-generates folder navigation from the `content/` directory structure and renders wiki-links into an interactive graph view. The search index provides full-text search across all pages — mapping keywords, part numbers, symptoms, and any other terms to the sections where they appear. See section 11.2 for how the agent leverages this.

### 7.4 Compendium Page Frontmatter

Quartz natively uses YAML frontmatter on pages for metadata, tags, and titles — no stripping needed. Every compendium chapter page carries synthesis provenance and per-document traceability:

```yaml
---
chapter_id: "suspension.wheel-bearings.rear"
title: "Rear Wheel Bearings"
synthesis_model: "claude-opus-4-5-20250630"
synthesis_date: "2026-02-08"
last_reviewed: "2026-02-08"
documents:
  - document_id: "G8BD.SB.0000001"
    synthesized_at: "2026-02-16"
    credibility_tier: "community_validated"
  - document_id: "G8BD.SB.0000002"
    synthesized_at: "2026-02-16"
    credibility_tier: "community_validated"
  - document_id: "G8BD.SB.0000003"
    synthesized_at: "2026-02-16"
    credibility_tier: "anecdotal"
  - document_id: "GMOT.SM.0000034"
    synthesized_at: "2026-02-01"
    credibility_tier: "authoritative"
  - document_id: "GMOT.TB.0000012"
    synthesized_at: "2026-02-08"
    credibility_tier: "authoritative"
---
```

Each field serves a specific purpose:

| Field | Purpose |
|-------|---------|
| `chapter_id` | Hierarchical identifier for cross-referencing and programmatic lookup |
| `synthesis_model` | Which AI model synthesized this chapter. Enables bulk re-synthesis when better models become available |
| `synthesis_date` | When the synthesis was last performed |
| `last_reviewed` | When the chapter was last reviewed for accuracy against current documents |
| `documents` | Per-document traceability with the `normalization_date` at time of synthesis and the document's credibility tier |
| `documents[].synthesized_at` | The document's `normalization_date` at the time this chapter was synthesized. **This is the key field for incremental synthesis** |
| `documents[].credibility_tier` | Copied from the document at synthesis time — enables credibility assessment without fetching back into the corpus |

Aggregate fields like `document_count`, `origin_count`, and `credibility_summary` are derivable from the `documents` list and do not need to be stored separately.

#### 7.4.1 Incremental Synthesis

The per-document `synthesized_at` field enables precise incremental re-synthesis. When a corpus's pinned commit is bumped in `compendium.toml`, the staleness check is mechanical:

```
For each chapter in content/:
  For each document in chapter.documents:
    Fetch the document file from corpora/
    If document.normalization_date > chapter_document.synthesized_at:
      Flag this chapter for re-synthesis
```

A commit bump that touches 200 files (because record `ingestion_date_last` fields were updated on a routine check) but only has real normalization changes in 3 of them results in exactly the chapters referencing those 3 documents being flagged. Everything else is untouched. This keeps re-synthesis proportional to actual change, not to ingestion activity.

The same check catches re-normalization events: if a document is re-normalized with a better model (content unchanged, but `normalization_date` and `normalization_model` updated), the compendium correctly flags that chapter for re-synthesis from the improved material.

**Build-time validation:** The `documents` list enables a CI check that verifies every cited document ID actually resolves to a real file in the resolved corpora. This catches broken references when documents are reorganized or when a pinned commit is bumped and document IDs have changed.

**Model audit trail:** Between the `normalization_model` on document files and `synthesis_model` on compendium pages, the full model provenance chain is captured. If a model is found to produce problematic output, you can query across both layers to identify every artifact it touched and prioritize re-processing.

---

## 8. Hosting & Distribution

### 8.1 Architecture

The compendium sites are hosted on an external Caddy server (`ref.example.org`) that is independent of the home infrastructure. This provides:

> **Domain naming:** `ref.example.org` hosts published compendiums — the synthesized reference works that agents and humans browse. `corpus.example.org` hosts corpus sites — browsable Quartz sites built from the assembled documents in each corpus (see section 4).

- High availability regardless of home lab state
- Accessibility from any device (phone, laptop, Claude Code session)
- A single stable endpoint for all corpora
- Decoupled content updates — the compendium improves without touching the agent

URL structure maps directly to the Compendium organization:

```
https://ref.example.org/commodore-ve/     → Commodore VE compendium
https://ref.example.org/dune/             → Dune universe compendium
https://ref.example.org/economics/        → Economics compendium
https://ref.example.org/{domain}/         → Any future domain
```

### 8.2 Access Control

**Phase 1 (current):** HTTP Basic Authentication across the entire `ref.example.org` site via Caddy's `basicauth` directive. Separate credentials for personal browsing and agent access.

```
ref.example.org {
    basicauth {
        steven <hashed-password>
        agent  <hashed-password>
    }
    root * /srv/ref
    file_server
}
```

**Phase 2 (future):** Per-compendium access control with a lightweight auth gateway. This would enable:

- Public/private toggle per compendium (some domains could be shared openly)
- Per-user compendium permissions
- A dashboard showing which compendia the authenticated user can access
- Separate agent tokens scoped to specific corpora

### 8.3 Caddy Server Configuration

The Caddy instance is an external VPS that currently serves as a reverse proxy. Each compendium is deployed as a subdirectory under `/srv/ref/`.

```
/srv/ref/
├── commodore-ve/        # Quartz build output
├── dune/                # Quartz build output
├── economics/           # Quartz build output
└── ...
```

---

## 9. CI/CD Pipeline

### 9.1 Build & Deploy Flow

Each compendium repository contains a Forgejo Actions workflow that automates the build-and-deploy cycle:

```
Developer pushes to main branch (or bumps a pinned commit in compendium.toml)
        ↓
Forgejo Actions workflow triggers
        ↓
resolve.sh clones/updates corpora at pinned commits
        ↓
Quartz builds the content/ directory
        ↓
Build artifacts (public/ directory) are deployed to Caddy server
        ↓
Live at ref.example.org/{domain}/ within seconds
```

### 9.2 Deployment Mechanism

The Caddy server accepts deployments via one of:

- **SSH/SCP push:** The Forgejo Actions runner pushes build artifacts directly to `/srv/ref/{domain}/` on the Caddy VPS via SSH with a deploy key.
- **Webhook receiver:** A small receiver script on the Caddy box accepts a tarball via HTTP POST with a shared secret, unpacks it to the target directory.

### 9.3 Workflow Templates

**Compendium workflow:** Triggered on push to main when `content/`, `quartz.config.ts`, or `compendium.toml` change. Steps: shallow clone, resolve corpus dependencies via `resolve.sh` (see section 6.2), build Quartz from `content/`, deploy `public/` to hosting via rsync.

**Corpus workflow:** Triggered on push to main when `material/` or `quartz.config.ts` change. Steps: export assembled documents to `content/` via `export.sh`, build Quartz, deploy `public/` to hosting. Simpler than the compendium workflow because there are no corpus dependencies to resolve.

See section 15.9 for complete workflow templates.

### 9.5 Corpus Update Propagation

When new documents are added to a corpus repo, the compendiums that reference it don't automatically rebuild. This is intentional — synthesis is a curated process. The workflow is:

1. New documents are committed to the corpus repo (e.g., `Corpus/g8board`)
2. The compendium maintainer bumps the pinned commit hash in `compendium.toml` when ready to incorporate new material
3. New synthesis is performed incorporating the new documents
4. Push triggers the build and deploy pipeline

For corpora with high ingestion velocity, this can be automated with a scheduled workflow that bumps pinned commits periodically.

---

## 10. Domain Agent Layer

### 10.1 Design

Each domain has a **single bespoke agent** — a dedicated AI assistant that is an expert in that domain and nothing else. There is no domain router and no shared context between domains. When you need automotive expertise, you invoke the automotive agent. When you need Dune lore, you invoke the Dune agent. (Pipeline agents — the ingestor, normalizer, assembler, and Curator described in section 12 — are internal corpus maintenance tools, not domain-facing agents.)

This simplicity is deliberate:

- The user always knows which expert they need
- Each agent's system prompt is fully tailored to its domain
- No prompt budget is wasted on routing logic or domain detection
- Each agent can have domain-specific personality, terminology, and reasoning patterns

### 10.2 Agent Configuration

Each agent is configured as a **skill** (for Claude Code / claude.ai) or equivalent construct for other platforms. The agent's configuration includes:

- **System prompt:** Domain-specific persona, expertise description, reasoning instructions, and domain taxonomy.
- **Compendium URL:** The base URL for fetching compendium pages and the search index (e.g., `https://ref.example.org/commodore-ve/`).
- **Access credentials:** The agent's basic auth credentials for the compendium site.
- **Domain taxonomy:** Key concepts, terminology, and the structure of the domain to guide query decomposition.

### 10.3 Agent Behavior Model

When the agent receives a question, it follows this process:

1. **Understand the query.** Parse the question to identify which systems, symptoms, concepts, or topics are involved.
2. **Navigate the compendium.** Using the domain taxonomy and document frontmatter, identify which chapter(s) and section(s) are relevant. If the query doesn't map cleanly to the structure, use Quartz search for relevant terms to discover applicable sections.
3. **Fetch relevant sections.** Retrieve the specific markdown pages from the compendium site via HTTP GET. Only fetch what's needed — not the entire compendium.
4. **Synthesize a response.** Answer the question based on the retrieved compendium content, citing specific documents where the compendium provides them.
5. **Flag coverage gaps.** If the compendium doesn't cover the topic well, tell the user explicitly rather than speculating.

### 10.4 Example Agent Interactions

The agent selects documents by searching descriptions and tags, retrieves relevant sections, and synthesizes an answer citing specific sources. See section 15.10 for example dialogues demonstrating automotive and fiction domain agents.

---

## 11. Retrieval Strategy

### 11.1 Primary Method — Obsidian-Native Navigation

The agent's primary retrieval mechanism is structural navigation using the compendium's domain taxonomy, document descriptions, tags, and Quartz search index. The domain taxonomy and key terms are loaded into the agent's context as part of its system prompt. Wiki-link graph connections between documents surface related content.

This is analogous to how a knowledgeable human uses a reference book: they already know the structure, they go to the right chapter, and they read the relevant section. The agent does the same via HTTP fetches of specific pages.

**Advantages:**

- No embedding infrastructure required
- No vector database to maintain
- Retrieval is deterministic and explainable ("I looked in chapter 4.1")
- Works with the same artifact the human browses
- Updates are instant — new content appears as soon as it's deployed

### 11.2 Search Index Lookup

Quartz generates a search index at build time as part of its static output. This is the same index that powers the browser-side search UI — a full-text tokenized index of every page in the compendium. The agent can fetch and query this index directly via HTTP, bypassing the browser UI entirely.

For example, querying the Commodore VE compendium's search index for "bearing" returns 30 ranked results with chapter paths and content snippets:

```
Suspension » Wheel Bearings » Wheel Bearings
  "The G8 uses two completely different wheel bearing designs front
   and rear..."

Drivetrain » Driveshaft » Center Support Bearing
  "The center support bearing (also called the carrier bearing or
   driveshaft support bearing) sits at the junction of..."

Common Issues & Known Weaknesses » Front Wheel Bearings
  "Both front bearings typically fail within the 60,000 to 90,000
   mile window..."
```

This is superior to a hand-curated index because:

- It's **full-text** — every word in the compendium is searchable, not just manually tagged keywords
- It **ranks results** by relevance
- It provides **content snippets** that help the agent evaluate relevance before fetching the full page
- It's **automatically regenerated** on every build with zero manual maintenance
- It handles fuzzy queries (user describes symptoms in unexpected language) better than structural navigation alone

**Usage pattern:** The agent fetches the Quartz search index once per session, queries it locally for relevant terms, then uses the results to identify which pages to fetch in full. For very large compendia where the search index itself is too large to hold in context, a lightweight wrapper endpoint could accept a query and return just the top N results with paths and snippets.

The search index and structural navigation complement each other: the taxonomy is best for "I know which system this is about," while the search index is best for "I have a symptom or keyword and need to find where it's discussed."

### 11.3 Fallback — Vector Search (Deferred)

Semantic vector search is **not implemented initially** but the architecture accommodates it if needed. The trigger for adding it would be repeated instances where the agent cannot find relevant content through structural navigation or the search index because the user's query language doesn't match any terminology present in the compendium.

If implemented, it would be a lightweight vector store (e.g., Qdrant in Docker) with embeddings over the compendium's markdown chunks, used only when TOC/search index navigation fails to identify relevant sections.

### 11.4 Forgejo API as Alternative Access Path

The Forgejo REST API provides raw file access to the corpus and compendium markdown:

```
GET /api/v1/repos/Corpus/{name}/raw/material/{slug}/{document_id}/{document_id}.md
GET /api/v1/repos/Compendium/{domain}/raw/content/{path}
Authorization: token {read-only-token}
```

This serves as an alternative access path — useful for agents running in environments where fetching rendered HTML is less convenient than raw markdown (e.g., Claude Code sessions where markdown is the native format). Both access methods (hosted site and API) serve the same content from the same source of truth.

---

## 12. Pipeline Agent Architecture

### 12.1 Overview

The corpus pipeline (section 3.3) is operated by specialized agents — lightweight, single-purpose AI workers that each handle one item per invocation. This section formalizes the agent pattern that has emerged from the alldata-g8 corpus implementation.

The pattern is intentionally minimal: each agent has a focused responsibility, processes exactly one item, and reports results to a coordinator. There is no inter-agent communication, no shared state beyond the filesystem, and no orchestration framework. Parallelism is managed at the coordinator level (the Curator skill or a human operator), not within the agents themselves.

This is distinct from the domain agent layer (section 10), which provides end-user knowledge retrieval. Pipeline agents are internal tools for building and maintaining corpora.

### 12.2 Ingestor Agent

The ingestor agent handles capture, reconciliation, and integrity verification for a single content item.

**Characteristics:**

- **Model class:** haiku (fast, cheap — no creative judgment needed)
- **Scope:** One item per invocation
- **Location:** `.claude/agents/ingestor.md` in the corpus repo
- **Tools:** Read, Bash, Glob, Grep (read-only except for Bash to run scripts)

**Responsibilities:**

1. **Capture.** Run the appropriate scraper or downloader to acquire raw content into `.capture/`.
2. **Routing check.** Before assigning identity, check incoming content against the routing table (section 3.2.3). If another corpus claims the content, reject it locally and report the redirect target to the coordinator. Read cross-references (section 3.2.4) for soft routing signals — flag content that may belong to a cross-referenced corpus for operator review.
3. **Reconciliation.** Auto-detect the partition from backlog metadata or content analysis, assign the next sequential `document_id`, create the document directory in `material/<slug>/<document_id>/`, move artifacts there, create record stubs (`status: stub`), and create `{document_id}.toml` with the working title.
4. **Integrity verification.** Verify file creation, check content completeness (page counts, post counts, post number gaps), validate record frontmatter, and detect deduplication issues.
5. **Structured reporting.** Report results back to the coordinator with success/failure status, assigned `document_id`, file counts, routing redirects, and any integrity warnings.

The ingestor agent does not make decisions about what to ingest or which partition to target — it receives these instructions from the coordinator. It is a reliable executor, not a decision maker.

### 12.3 Normalizer Agent

The normalizer agent transforms record stubs into fully normalized records, handling both conversion and contextualization.

**Characteristics:**

- **Model class:** sonnet (creative judgment required for contextualization, issue surfacing)
- **Scope:** One document per invocation (all records for that document)
- **Location:** `.claude/agents/normalizer.md` in the corpus repo
- **Tools:** Read, Write, Edit, Bash, Glob, Grep

**Responsibilities:**

1. **Conversion.** For each record with `status: stub`, run the appropriate conversion script or tool to fill the record body. Set `status: draft`. This step shells out to deterministic tooling.
2. **Contextualization.** Load all records for the document together. Refine content across records — resolve internal links, improve alt text, convert HTML to better markdown, normalize formatting. Surface issues in record frontmatter. Set `status: normalized`.
3. **Self-verify.** Validate record frontmatter against the schema, check for broken asset references.

The normalizer agent receives corpus context (`{corpus_id}.toml`, the record schema, content-type-specific conversion guidance) and reads `{document_id}.toml` for any per-document `prompts.conversion` or `prompts.contextualization` instructions. Its system prompt is corpus-specific, living in the corpus repo alongside the agent definition.

### 12.4 Assembler Agent

The assembler agent compiles normalized records into a fully spec-compliant assembled document.

**Characteristics:**

- **Model class:** sonnet (editorial judgment required for descriptions, credibility assessment, document structure)
- **Scope:** One document per invocation
- **Location:** `.claude/agents/assembler.md` in the corpus repo
- **Tools:** Read, Write, Edit, Bash, Glob, Grep

**Responsibilities:**

1. **Read document config and records.** Read `{document_id}.toml` for the working title and any `prompts.assembly` instructions. Load all records from `material/<slug>/<document_id>/` with `status: normalized`.
2. **Generate document frontmatter.** Produce the `description`, `credibility_tier`, `relations`, `issues`, `tags`, and `aliases` fields that require content understanding and domain judgment.
3. **Assemble the document.** Compile record content into a single well-structured markdown document with Obsidian formatting (wiki-links, callouts). Write to `material/<slug>/<document_id>/{document_id}.md`.
4. **Self-verify.** Validate the output against the document frontmatter schema, check that the `records` array matches the records on disk.

### 12.5 The Curator

The Curator is an autonomous corpus management skill that orchestrates pipeline operations. Unlike the ingestor, normalizer, and assembler agents (which are single-purpose workers), the Curator operates at a higher level — assessing corpus state, prioritizing work, and dispatching agents.

**Characteristics:**

- **Type:** Claude Code skill (`.claude/skills/`)
- **Operating loop:** Assess → Prioritize → Propose → Execute → Report
- **Dispatches:** Ingestor, normalizer, and assembler agents via the Task tool, parallelizing multiple invocations

**Operating loop:**

1. **Assess.** Read `backlog.toml`, scan `material/` for record status (`stub`, `draft`, `normalized`), check for assembled documents needing re-assembly, review corpus health metrics. For triage corpora: identify documents eligible for graduation by checking routing claims from other corpora and flagging content clusters that suggest a dedicated corpus should be created.
2. **Prioritize.** Apply a decision framework: critical compendium blockers first, then high-priority backlog items, then graduation of triage content to dedicated corpora, then normalization of existing stubs, then assembly of normalized documents, then low-priority discovery.
3. **Propose.** Present the prioritized work plan to the human operator for approval.
4. **Execute.** Spawn ingestor agents (for capture + reconciliation), normalizer agents (for conversion + contextualization), and assembler agents (for document assembly), managing parallelism by launching multiple agents concurrently. For triage corpora, execute batch graduation operations when dedicated corpora are ready to receive content (section 3.3.5). When spawning normalizer and assembler agents, the Curator reads each document's `{document_id}.toml` and includes the relevant `[prompts]` section in the agent's task description.
5. **Report.** Summarize results — documents ingested, records normalized, documents assembled, issues encountered, updated corpus health metrics.

**Reference files.** The Curator's skill definition references corpus-specific configuration: the `{corpus_id}.toml` schema, the pipeline workflow, the frontmatter schema, and a self-improvement playbook that captures lessons learned from previous runs. These reference files live in the corpus repo and evolve with the corpus.

### 12.6 Parallelism Model

Parallelism is managed at the coordinator level, not within agents:

- The **Curator** (or a human operator) decides how many agents to run concurrently based on available resources and rate limits.
- Each **ingestor agent** processes one item. The coordinator spawns N ingestor agents in parallel for N items.
- Each **normalizer agent** processes one document (all its records). The coordinator spawns N normalizer agents in parallel for N documents.
- Each **assembler agent** processes one document. The coordinator spawns N assembler agents in parallel for N documents.
- Agents do not communicate with each other. They read from and write to the filesystem, and the coordinator sequences work to avoid conflicts (e.g., not normalizing a document that is still being ingested, not assembling a document that is still being normalized).

This model avoids the complexity of inter-agent coordination while still enabling high throughput. A typical Curator session might spawn 5 ingestor agents in parallel, wait for completion, spawn 5 normalizer agents for the newly reconciled documents, then spawn 5 assembler agents for the newly normalized documents.

### 12.7 Generality

The pipeline agent pattern is not specific to alldata-g8 or any particular content type. It applies to any corpus:

- The **ingestor agent** is parameterized by the capture script and reconciliation logic, which are corpus-specific.
- The **normalizer agent** is parameterized by the corpus's conversion tools and contextualization guidance, which vary by corpus.
- The **assembler agent** is parameterized by the corpus's document schema and assembly guidance.
- The **Curator** is parameterized by the corpus's backlog format, partition structure, and priority framework.

Each corpus repo contains its own agent definitions (`.claude/agents/`) and Curator skill (`.claude/skills/`), configured for that corpus's specific needs. The pattern is the same; the configuration differs.

---

## 13. Scaling & Reuse

### 13.1 Adding a New Corpus

1. Create a new repository under the Corpus organization
2. Add `{corpus_id}.toml` with corpus metadata, origin configs, `[[partition]]` entries, and reingest configuration
3. Define `[[routing]]` claims for content that belongs in this corpus (URL patterns, YouTube channels, domains — see section 3.2.3)
4. Add `[[cross_references]]` to declare relationships with other corpora (see section 3.2.4)
5. Add `backlog.toml` and populate with known pending entries
6. Create the `material/` directory with per-partition slug directories
7. Add `quartz.config.ts` for Quartz site configuration (see section 4.2)
8. Add `.capture/` and `content/` to `.gitignore`
10. Build or configure the acquisition pipeline appropriate to the content type
10. Build or configure the conversion pipeline — content-type-specific scripts that convert artifacts to record markdown (see section 3.3.2.1). For simple text content, a passthrough converter is sufficient
12. Create agent definitions in `.claude/agents/` (ingestor, normalizer, and assembler — see section 12) parameterized for this corpus
13. Optionally create a Curator skill in `.claude/skills/` for autonomous corpus management
14. Begin processing source material through the three-phase pipeline: acquire → normalize → assemble (see section 3.3)
15. Graduate any triage content that matches the new corpus's routing claims (see section 3.3.5)
16. The corpus is discoverable — its `{corpus_id}.toml` tiered summaries and routing claims are available via the Forgejo API for any compendium to find (see section 5)

### 13.2 Adding a New Compendium

1. Create a new repository under the Compendium organization
2. Discover relevant corpora via API-driven progressive disclosure (see section 5.4)
3. Declare corpus dependencies in `compendium.toml` with pinned commits
4. Write the synthesis system prompt with domain knowledge, scope boundaries, and key relationships
5. Create `resolve.sh` to clone corpora at pinned commits with sparse checkout (copy from template)
6. Add `corpora/` to `.gitignore`
7. Define the domain taxonomy — the chapter structure
8. Establish the standard `content/` directory structure
9. Begin the synthesis process
10. Add the Forgejo Actions deploy workflow (copy from template)
11. Create the agent skill with domain-specific system prompt and domain taxonomy
12. Add deploy target to the Caddy configuration

### 13.3 Stacking Compendiums

The architecture supports compendiums of varying scope that share source material:

```
Compendium/economics/           (broad)
  corpora: marxists-org, jstor-economics, wikipedia-economics, ...
  system prompt: broad economic theory, markets, policy

Compendium/socialism/           (focused)
  corpora: marxists-org, jstor-economics, ...
  system prompt: socialist theory, class analysis, historical application

Compendium/politics/            (broad, different lens)
  corpora: marxists-org, jstor-economics, wikipedia-politics, ...
  system prompt: political theory, governance, ideological frameworks
```

All three compendiums reference `marxists-org` as a corpus. Each compendium's system prompt guides the LLM to select different documents — the economics compendium selects documents on broad economic concepts, the socialism compendium selects a narrower subset focused on socialist theory, and the politics compendium selects an overlapping but distinct set. **One document file, one location in git, zero duplication, multiple compendiums synthesizing from different perspectives.**

The same pattern applies to fiction. A "Golden Age Sci-Fi" compendium and a "Dune" compendium both declare `frank-herbert` as a dependency, with their respective system prompts selecting different works.

### 13.4 Domain Taxonomy Design

Each domain needs its own taxonomy — the organizational structure that chapters follow. This should be designed before significant content is ingested, though it will evolve. Guidelines:

- Follow the natural structure of the domain (for a vehicle: by system; for health: by body system; for fiction: by world element — characters, factions, locations, technology, themes, adaptations)
- Prefer 2-3 levels of hierarchy maximum
- Each leaf section should be self-contained enough to be useful when fetched in isolation
- Cross-reference liberally between related sections

### 13.5 Standardized Frontmatter Schema

The complete document frontmatter schema is defined in section 3.4. In summary:

**Universal required** (every document):
`document_id`, `title`, `description`, `credibility_tier`, `normalization_confidence`, `normalization_model`, `normalization_date`, `records[]`

**Universal optional** (present when applicable):
`tags`, `aliases`, `relations`, `issues`, `status` (tombstone only: `graduated`), `graduated_to`, `graduated_corpus`, `graduation_date`

**Records entry:** `record_id`, `source_url` or `original_filename`

**Record fields** (section 3.3.2.3): core fields (`document_id`, `sequence`, `status`, `content_type`, `origin`, `source_url`, `original_filename`, `capture_date`, `body_format`, `ingestion_date_last`, `content_changed_last`, `author`, `date_published`, `volatility`, `conversion_method`, `conversion_tool`, `conversion_date`, `issues`) plus extended schemas by `content_type`:

| Content Type | Required Extended Fields | Optional Extended Fields |
|-------------|-------------------------|--------------------------|
| `forum_post` | `username`, `thread_url` | `reply_count` |
| `reddit_post` | `username`, `subreddit`, `post_url` | `score`, `comment_count` |
| `book` | `work_title` | `isbn`, `word_count`, `series_name`, `series_position` |
| `service_manual` | `manual_title`, `section_reference`, `model_years` | `vehicle_system` |
| `technical_bulletin` | `bulletin_number`, `affected_models`, `affected_years` | |
| `video` | `duration_seconds` | `channel_name` |
| `podcast` | `duration_seconds` | `episode_number`, `series_name` |
| `research_paper` | `journal`, `peer_reviewed` | `doi` |
| `article` | `article_url` | `publication` |
| `screenplay` | `work_title`, `medium` | `draft` |
| `product_documentation` | `product_name`, `manufacturer` | `document_type`, `part_numbers` |

**Document config** (`{document_id}.toml` in `material/<slug>/<document_id>/`):
`title` (required), `original_document_id` (optional, graduation lineage), `[prompts]` (optional: `conversion`, `contextualization`, `assembly`), `[[derived]]` (optional: `file`, `type`, `records[]`)

**Corpus registration** (`{corpus_id}.toml`):
`corpus_id`, `corpus_name`, `document_id_format`, `triage` (optional boolean), `summary_tier1`/`tier2`/`tier3`, `[[origins]]`, `[[partition]]`, `[[routing]]` (optional: `type`, `claim`), `[[cross_references]]` (optional: `corpus_id`, `relationship`, `description`)

**Derived files:** `material/<slug>/<document_id>/derived/` — flat directory, no record_id namespacing (derivations can span multiple records). Declared as `[[derived]]` entries in `{document_id}.toml` with `file` (filename), `type` (e.g., `frame_grab`, `transcription`), and `records[]` (provenance). Not assigned record_ids, regenerated during re-conversion

**Compendium page frontmatter** (section 7.4):
`chapter_id`, `title`, `synthesis_model`, `synthesis_date`, `last_reviewed`, `documents[]` (with `document_id`, `synthesized_at`, `credibility_tier` per document)

---

## 14. Infrastructure Summary

### 14.1 Component Map

```
┌──────────────────────────────────────────────────────────────┐
│                    Forgejo (Tailnet)                           │
│                                                                │
│  Corpus Organization               Compendium Organization     │
│  ├── g8board/                      ├── commodore-ve/           │
│  │   ├── g8board.toml              │   ├── corpora/ (resolved) │
│  │   ├── backlog.toml              │   ├── content/            │
│  │   ├── quartz.config.ts          │   ├── compendium.toml     │
│  │   ├── material/                 │   └── quartz.config.ts    │
│  │   ├── content/ (gitignored)     ├── dune/                   │
│  │   ├── .capture/ (gitignored)    ├── economics/              │
│  │   └── .claude/agents/           └── ...                     │
│  ├── frank-herbert/                                            │
│  └── ...                                                       │
│                                                                │
│  example-org Organization (System Infrastructure)                │
│  └── athenaeum/                    # spec, tooling             │
│                                                                │
│  Forgejo Actions Runner                                        │
│  ├── corpus: on push → export + Quartz build → deploy          │
│  └── compendium: on push → resolve → Quartz build → deploy    │
└───────────────────────┬────────────────────────────────────────┘
                        │ rsync / scp / webhook
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                  Caddy VPS (External)                          │
│                                                                │
│  ref.example.org (compendiums)                                 │
│  ├── basicauth (steven, agent)                                 │
│  ├── /srv/ref/commodore-ve/    ← compendium Quartz output   │
│  ├── /srv/ref/dune/            ← compendium Quartz output   │
│  └── ...                                                       │
│                                                                │
│  corpus.example.org (corpus sites)                             │
│  ├── basicauth (steven, agent)                                 │
│  ├── /srv/corpus/g8board/      ← corpus Quartz output       │
│  ├── /srv/corpus/frank-herbert/← corpus Quartz output       │
│  └── ...                                                       │
└───────────────────────┬────────────────────────────────────────┘
                        │ HTTPS (basic auth)
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                       Consumers                                │
│                                                                │
│  Steven (browser)                                              │
│  ├── Browses compendiums for domain knowledge                  │
│  └── Browses corpus sites for normalization review             │
│                                                                │
│  Domain Agent (Claude skill / Claude Code)                     │
│  ├── Domain taxonomy in system prompt context                  │
│  ├── Quartz search index for full-text keyword lookup          │
│  ├── Fetches specific pages via HTTP on demand                 │
│  └── Responds with source-grounded answers                     │
│                                                                │
│  Pipeline Agents (.claude/agents/)                             │
│  ├── Ingestor: acquire + reconcile + verify (haiku)            │
│  ├── Normalizer: record stubs → normalized records (sonnet)    │
│  ├── Assembler: normalized records → document (sonnet)         │
│  └── Curator: autonomous corpus management (.claude/skills/)   │
└──────────────────────────────────────────────────────────────┘
```

### 14.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Source of truth | Forgejo (git) | Version control, API access, Actions CI |
| Source organization | Forgejo org (Corpus) | One repo per corpus, with origins and partitions declared in `{corpus_id}.toml` |
| Corpus discovery | Forgejo API + `{corpus_id}.toml` | Tiered summaries fetched on demand, no separate registry repo |
| Content routing | `[[routing]]` in `{corpus_id}.toml` | URL/channel/domain claims checked during reconciliation, discoverable via same Forgejo API |
| Corpus format | Markdown + Quartz | Browsable corpus sites at `corpus.example.org`, Obsidian-native formatting |
| Compendium format | Markdown + Quartz | Human-readable source, clean output, built-in search, graph view |
| Source linkage | Declared dependencies in `compendium.toml` | Pin corpora to commits, resolve at build time with sparse checkout |
| Hosting | Caddy on external VPS | Simple, reliable, automatic HTTPS, basic auth |
| CI/CD | Forgejo Actions | Integrated with repos, self-hosted runner (corpus + compendium workflows) |
| Domain agents | Claude (skill / Code) | Primary AI interface for end-user knowledge retrieval |
| Pipeline agents | Claude Code agents (`.claude/agents/`) | Ingestor (haiku), normalizer (sonnet), assembler (sonnet), Curator (skill) for corpus maintenance |
| Retrieval | Quartz search + document frontmatter + HTTP fetch | No additional infrastructure, deterministic, explainable |

### 14.3 What Is Intentionally Not Included

| Component | Status | Trigger to Add |
|-----------|--------|----------------|
| Vector database | Deferred | Agent repeatedly fails to find content via structural navigation/search index |
| Knowledge graph | Deferred | Multi-hop relationship queries become common |
| Domain router | Not planned | Only needed if agents are invoked implicitly |
| Cross-domain linking | Not planned | Domains are intentionally isolated. Cross-corpus references (section 3.2.4) exist at the corpus layer for discovery and routing, but compendium domains remain independent |
| General-purpose orchestration framework | Not planned | Pipeline agents use lightweight coordination via Curator skill (section 12), not a framework |
| Per-compendium auth gateway | Deferred | Needed when sharing specific compendiums with others |

---

## 15. Working Examples

This section collects complete worked examples referenced throughout the specification. The technical definitions, schema tables, and design rationale live in their respective sections; these examples contextualize them with realistic data.

### 15.1 End-to-End Walkthrough

This walkthrough traces a single document from capture through compendium selection, demonstrating the full pipeline defined in sections 3.3 and 6.

Concretely: Frank Herbert's *Dune* enters the `FHBT` corpus as a raw epub file downloaded to `.capture/` (capture). Reconciliation detects it belongs in the `novels` partition, assigns it `FHBT.NV.0000001`, moves the epub to `material/novels/FHBT.NV.0000001/`, and creates a record stub `FHBT.NV.0000001_001.md`. During reconciliation, routing claims from all corpus `{corpus_id}.toml` files are checked — if a dedicated corpus claims this content, reconciliation redirects it there instead of ingesting locally (see section 3.2.3). Conversion parses the epub into markdown chapters in the record body. Contextualization refines formatting and surfaces any issues (missing chapters, encoding problems). The assembly agent then compiles the normalized record into a document at `material/novels/FHBT.NV.0000001/FHBT.NV.0000001.md` with a description characterizing it as a science fiction novel about ecology, politics, and prescience on the desert planet Arrakis. The `FHBT.toml` captures the corpus scope across its tiered summaries. When the `dune` compendium is set up, tier 1 summaries fetched from all corpora immediately identify `FHBT` as relevant. At synthesis time, the LLM reads individual document descriptions within the cloned corpus and — guided by the compendium's system prompt — selects *Dune* and *Dune Messiah* while skipping *Man of Two Worlds*. The same `FHBT` corpus could simultaneously feed a hypothetical `sci-fi-comedy` compendium whose system prompt would guide selection of *Man of Two Worlds* instead.

### 15.2 Corpus Registration Files

These complete registration files demonstrate the schema defined in section 3.2.

#### Single-Origin Source Corpus (G8BD.toml)

```toml
# G8BD.toml
corpus_id = "G8BD"
corpus_name = "G8Board.com"
document_id_format = "G8BD.TT.NNNNNNN"

# tiered summaries for corpus discovery (see section 5)
summary_tier1 = "Pontiac G8 forum threads covering DIY repairs, modifications, diagnostics, and common problems"

summary_tier2 = """
Community forum posts from G8Board.com covering maintenance, repair, \
and modification of 2008-2009 Pontiac G8 vehicles (GT, GXP, base V6). \
Organized across 8 taxonomy partitions: Technical Articles & DIY, \
V8 Engine, Suspension & Brakes, Drivetrain, Exhaust, G8 GT Talk, \
Stereo & Electronics, and Intake & Fuel. Document IDs use \
G8BD.TT.NNNNNNN format."""

summary_tier3 = """
Normalized forum threads from G8Board.com (document IDs use \
G8BD.TT.NNNNNNN format, e.g. G8BD.TA.0000001), the primary \
community forum for Pontiac G8 owners and enthusiasts. Organized \
across 8 partitions covering: engine topics (L76 6.0L, LS3 6.2L, \
AFM/DoD delete, camshaft swap DIY, oil consumption), drivetrain \
(transmission fluid, torque converter, driveshaft, differential \
mount bushings), suspension/brakes (wheel bearings, sway bar \
upgrades, brake upgrade part numbers), exhaust (factory exhaust \
system construction and modification), intake/fuel (hose clamp \
maintenance, air intake mods), stereo/electronics (LED swaps, \
lighting), general GT discussion (common problems, ownership \
guides), and technical articles (DIY guides). Sources preserve \
original posts and replies with credibility ratings. High-value \
content includes photo-documented procedures, GM part numbers, and \
community-validated troubleshooting from experienced G8 owners."""

[[origins]]
origin_id = "forum"
origin_name = "G8Board.com Forum"
origin_type = "forum"
origin_url = "https://www.g8board.com"
description = "Community forum for Pontiac G8 owners and enthusiasts"
ingestion_method = "web_scraper"
active = true

[origins.reingest]
default_volatility = "unlikely"       # most old threads are stable
active_threshold_days = 7             # check 'active' documents weekly
periodic_threshold_days = 90          # check 'periodic' documents quarterly
unlikely_threshold_days = 365         # check 'unlikely' documents annually
# 'static' documents are never re-checked

[[partition]]
code = "TA"
slug = "technical-articles-diy"
name = "Technical Articles & DIY"
description = "Community-written repair guides, installation how-tos, and diagnostic procedures"

[[partition]]
code = "V8"
slug = "v8-engine-tech-l76-ls3"
name = "V8 Engine"
description = "LS3/L76/LY7 engine topics: camshaft, lifters, oil, AFM/DoD, cooling"

[[partition]]
code = "SB"
slug = "suspension-brakes"
name = "Suspension & Brakes"
description = "Wheel bearings, sway bars, brake swaps, CTS-V/Brembo upgrades"

[[partition]]
code = "DT"
slug = "drivetrain-tech"
name = "Drivetrain"
description = "Transmission, torque converter, driveshaft, differential, manual swap"

[[partition]]
code = "EX"
slug = "exhaust-tech"
name = "Exhaust"
description = "Exhaust system modifications, catalytic converters, headers, mufflers"

[[partition]]
code = "GT"
slug = "g8-gt-talk-v8"
name = "G8 GT Talk"
description = "General V8 model discussion, common problems, ownership guides"

[[partition]]
code = "SE"
slug = "stereo-electronics"
name = "Stereo & Electronics"
description = "Audio, lighting, wiring, LED swaps, Bluetooth, radio programming"

[[partition]]
code = "IF"
slug = "intake-fuel-tech"
name = "Intake & Fuel"
description = "Intake manifold, fuel system, hose clamps, air intake modifications"
```

#### Multi-Origin Source Corpus (GMOT.toml)

```toml
# GMOT.toml
corpus_id = "GMOT"
corpus_name = "General Motors"
document_id_format = "GMOT.TT.NNNNNNN"

summary_tier1 = "General Motors official documentation — service manuals, TSBs, recalls"

summary_tier2 = """
Official publications from General Motors covering service manuals, \
technical service bulletins, recall notices, dealer bulletins, press \
releases, and brochures. Primarily North American market vehicles. \
Organized by document type partitions."""

summary_tier3 = """
General Motors official documentation normalized from PDFs, web \
captures, and database exports. Includes service manuals (Helm and \
ACDelco TDS), technical service bulletins (TSBs/PIs), NHTSA recall \
documentation cross-referenced to GM campaign numbers, dealer \
bulletins, press releases, and marketing brochures.

Coverage spans multiple GM brands and platforms with emphasis on \
vehicles sharing platforms with Holden (Zeta, Sigma). ~75 normalized \
documents. Authoritative credibility tier."""

[[origins]]
origin_id = "service-manuals"
origin_type = "pdf_archive"
ingestion_method = "pdf_extractor"
active = false

[origins.reingest]
default_volatility = "static"
unlikely_threshold_days = 365

[[origins]]
origin_id = "bulletins"
origin_type = "web_database"
origin_url = "https://www.gm.com/bulletins"
ingestion_method = "web_scraper"
active = true

[origins.reingest]
default_volatility = "periodic"
periodic_threshold_days = 90

[[partition]]
code = "SM"
slug = "service-manuals"
name = "Service Manuals"
description = "OEM factory service manual sections"

[[partition]]
code = "TB"
slug = "technical-bulletins"
name = "Technical Bulletins"
description = "TSBs, PIs, and recall notices"

[[partition]]
code = "PR"
slug = "press-releases"
name = "Press Releases"
description = "Official press releases and marketing documentation"
```

#### Entity/Franchise Corpus (BSGF.toml)

```toml
# BSGF.toml
corpus_id = "BSGF"
corpus_name = "Battlestar Galactica"
document_id_format = "BSGF.TT.NNNNNNN"

summary_tier1 = "Battlestar Galactica reimagined series (2003-2009) — episodes, production, analysis"

summary_tier2 = """
Comprehensive corpus for the reimagined Battlestar Galactica franchise \
(2003-2009), including the miniseries, 4 seasons (76 episodes), Razor, \
The Plan, and Caprica. Multi-origin: episode transcripts, Wikipedia \
episode guides, IMDB data, Reddit discussion, and production scripts."""

summary_tier3 = """
Reimagined Battlestar Galactica franchise corpus covering the 2003 \
miniseries, seasons 1-4 (76 episodes), TV movies (Razor, The Plan), \
and the prequel series Caprica. Origins include episode transcripts \
(audio extraction + Whisper), Wikipedia episode summaries, IMDB \
episode/cast pages, r/BSG discussion threads, and production scripts \
where available. Episodes are multi-origin documents combining all \
records for each episode. ~120 documents across episodes, characters, \
world-building, production, and analysis partitions."""

[[routing]]
type = "url_pattern"
claim = "https://en.wikipedia.org/wiki/Battlestar_Galactica*"

[[routing]]
type = "url_pattern"
claim = "https://www.reddit.com/r/BSG/*"

[[routing]]
type = "domain"
claim = "battlestarwiki.org"

[[cross_references]]
corpus_id = "SCFI"
relationship = "related"
description = "Sci Fi Channel — network that aired BSG, shared production context"

[[origins]]
origin_id = "episodes"
origin_name = "Episode Files"
origin_type = "media_archive"
ingestion_method = "media_extractor"
active = false

[origins.reingest]
default_volatility = "static"

[[origins]]
origin_id = "wikipedia"
origin_name = "Wikipedia Episode Guides"
origin_type = "web_reference"
origin_url = "https://en.wikipedia.org/wiki/Battlestar_Galactica_(TV_series)"
ingestion_method = "web_scraper"
active = true

[origins.reingest]
default_volatility = "periodic"
periodic_threshold_days = 180

[[origins]]
origin_id = "imdb"
origin_name = "IMDB"
origin_type = "web_database"
origin_url = "https://www.imdb.com/title/tt0407362/"
ingestion_method = "web_scraper"
active = true

[origins.reingest]
default_volatility = "unlikely"
unlikely_threshold_days = 365

[[origins]]
origin_id = "reddit"
origin_name = "r/BSG"
origin_type = "forum"
origin_url = "https://www.reddit.com/r/BSG/"
ingestion_method = "reddit_scraper"
active = true

[origins.reingest]
default_volatility = "unlikely"
unlikely_threshold_days = 365

[[origins]]
origin_id = "scripts"
origin_name = "Production Scripts"
origin_type = "pdf_archive"
ingestion_method = "pdf_extractor"
active = false

[origins.reingest]
default_volatility = "static"

[[partition]]
code = "EP"
slug = "episodes"
name = "Episodes"
description = "Episode documents — transcript, summary, cast, discussion, and script records per episode"

[[partition]]
code = "CH"
slug = "characters"
name = "Characters & Cast"
description = "Character profiles, cast information, character arcs"

[[partition]]
code = "WD"
slug = "world-building"
name = "World-Building"
description = "Lore, technology, locations, factions, mythology"

[[partition]]
code = "PR"
slug = "production"
name = "Production"
description = "Behind-the-scenes, showrunner interviews, production decisions"

[[partition]]
code = "AN"
slug = "analysis"
name = "Analysis"
description = "Reviews, critical analysis, thematic essays"
```

#### Triage Corpus (TRGE.toml)

```toml
# TRGE.toml
corpus_id = "TRGE"
corpus_name = "Triage"
document_id_format = "TRGE.TT.NNNNNNN"
triage = true

summary_tier1 = "Unsorted content awaiting graduation to dedicated corpora"

summary_tier2 = """
Default intake corpus for content that does not yet have a dedicated \
corpus. Organized by content format (web, documents, media, reference, \
notes) rather than by voice or subject. Content graduates to dedicated \
corpora as they are created."""

summary_tier3 = """
Triage corpus for content captured before a dedicated corpus exists. \
The starting point of the classification chain. Partitions are \
format-based: WB (web captures), DC (documents and PDFs), MD (media \
— video and audio), RF (reference databases and datasets), NT (manual \
notes and observations). Content graduates to dedicated corpora via \
the graduation process (section 3.3.5) as the corpus ecosystem grows \
— first to source or domain corpora, then potentially to entity \
corpora as subjects accumulate mass."""

[[partition]]
code = "WB"
slug = "web"
name = "Web Captures"
description = "HTML pages, blog posts, articles, forum threads"

[[partition]]
code = "DC"
slug = "documents"
name = "Documents"
description = "PDFs, office documents, ebooks"

[[partition]]
code = "MD"
slug = "media"
name = "Media"
description = "Video and audio files, transcripts"

[[partition]]
code = "RF"
slug = "reference"
name = "Reference"
description = "Databases, datasets, structured data"

[[partition]]
code = "NT"
slug = "notes"
name = "Notes"
description = "Manual captures, observations, annotations"
```

### 15.3 Directory Structure

Complete annotated directory tree for a corpus repository (section 3.2.1).

```
Corpus/G8BD/
├── G8BD.toml                           # registration + origin/partition configs
├── backlog.toml                        # non-captured entry tracking
├── quartz.config.ts                    # Quartz configuration
├── content/                            # GITIGNORED — build artifact for Quartz / vault
│   ├── index.md                        # generated corpus overview
│   ├── suspension-brakes/
│   │   ├── index.md                    # generated partition overview
│   │   ├── G8BD.SB.0000001.md          # copied from material/
│   │   └── G8BD.SB.0000002.md
│   └── assets/                         # copied non-text artifacts + derived files
│       ├── G8BD.SB.0000002_002.jpg
│       ├── frame_0001.jpg
│       └── transcript.vtt
├── material/                           # artifacts, records, derived, assembled docs, config
│   ├── suspension-brakes/
│   │   ├── G8BD.SB.0000001/
│   │   │   ├── G8BD.SB.0000001.md          # assembled document (canonical)
│   │   │   ├── G8BD.SB.0000001_001.html    # artifact
│   │   │   └── G8BD.SB.0000001_001.md      # record
│   │   └── G8BD.SB.0000002/
│   │       ├── G8BD.SB.0000002.md          # assembled document (canonical)
│   │       ├── G8BD.SB.0000002.toml        # document config (includes [[derived]])
│   │       ├── G8BD.SB.0000002_001.html    # artifact (page)
│   │       ├── G8BD.SB.0000002_001.md      # record
│   │       ├── G8BD.SB.0000002_002.jpg     # artifact (image)
│   │       ├── G8BD.SB.0000002_002.md      # record
│   │       └── derived/                    # flat — no record_id namespacing
│   │           ├── frame_0001.jpg
│   │           ├── frame_0042.jpg
│   │           └── transcript.vtt
│   └── technical-articles-diy/
│       └── G8BD.TA.0000001/
│           ├── G8BD.TA.0000001.md          # assembled document
│           ├── G8BD.TA.0000001_001.html
│           └── G8BD.TA.0000001_001.md      # record
└── .capture/
    └── example-thread.12345/
        ├── thread.html                 # artifact
        └── metadata.json              # optional capture metadata
```

### 15.4 Backlog Configuration

Complete backlog examples demonstrating the format defined in section 3.2.2.

**G8Board backlog:**

```toml
# backlog.toml — tracks known content not yet captured

[[entries]]
title = "Complete AFM delete guide with dyno results"
url = "https://www.g8board.com/threads/afm-delete-guide.56789/"
section = "v8-engine-tech-l76-ls3"
status = "pending"
priority = "high"

[[entries]]
title = "Headlight condensation fix - bake and reseal"
url = "https://www.g8board.com/threads/headlight-condensation.56800/"
section = "technical-articles-diy"
status = "pending"
priority = "medium"
notes = "Includes detailed photos of the baking process"

[[entries]]
title = "G8 production numbers by color and trim"
url = "https://www.g8board.com/threads/production-numbers.56900/"
section = "g8-gt-talk-v8"
status = "deferred"
notes = "Interesting but not relevant to any current compendium"
```

**Frank Herbert backlog:**

```toml
# backlog.toml for frank-herbert

[[entries]]
title = "Children of Dune"
section = "novels"
status = "pending"
priority = "high"
notes = "Need to acquire epub"

[[entries]]
title = "The White Plague"
section = "novels"
status = "deferred"
notes = "Out of print, difficult to acquire"

[[entries]]
title = "Man of Two Worlds"
section = "novels"
status = "unavailable"
notes = "Co-authored with Bill Ransom, no digital edition found"
```

**Backlog reporting output:**

```
Ingestion Backlog:
  Corpus/frank-herbert:     6 captured, 8 pending (2 high, 3 medium, 3 low), 2 deferred, 1 unavailable
  Corpus/g8board:          42 captured, 156 pending (12 critical, 45 high, 99 medium), 3 deferred
  Corpus/gm:               75 captured, 120 pending (20 high, 60 medium, 40 low), 5 deferred
```

### 15.5 Record and Document Formats

Complete frontmatter examples for the formats defined in sections 3.3.2.3 and 3.4.

#### Record Frontmatter

```yaml
---
document_id: "G8BD.SB.0000001"
sequence: 1
status: "normalized"
content_type: "forum_post"
origin: "forum"
source_url: "https://www.g8board.com/threads/rear-suspension-rebuild-the-easy-way.290127/"
original_filename: "G8BD.SB.0000001_001.html"
capture_date: "2026-02-16"
body_format: "html"
ingestion_date_last: "2026-02-16"
content_changed_last: "2026-02-16"
date_published: "2024-01-24T00:46:23-05:00"
volatility: "unlikely"
conversion_method: "g8board-scraper"
conversion_tool: "scrape_thread.py v0.6"
conversion_date: "2026-02-16"

# extended: forum_post
thread_url: "https://www.g8board.com/threads/rear-suspension-rebuild-the-easy-way.290127/"
reply_count: 13
---

[artifact content interpreted as markdown]
```

#### Assembled Document

A forum post document with all applicable fields:

```yaml
---
document_id: "G8BD.SB.0000001"
title: "Rear Suspension Rebuild - The Easy Way"
description: "Complete rear subframe swap using a 2017 Caprice PPV dropout into a high-mileage G8 GT, providing aluminum knuckles and control arms, lower ball joint in knuckle, 18mm rear sway bar, and stiffer cradle bushings. Includes ABS sensor wiring procedure and compatibility information for 2011-2017 PPV models."
credibility_tier: "community_validated"
normalization_confidence: 0.95
normalization_model: "claude-sonnet-4-5-20250929"
normalization_date: "2026-02-16"
tags: ["suspension", "rear-subframe", "ppv-swap"]
aliases: ["PPV Rear Subframe Swap"]

relations:
  - type: "references"
    unresolved: "GM TSB #PI0597B"
issues:
  - type: "missing_media"
    severity: "major"
    description: "2 of 4 embedded images unavailable — showed bearing removal tool setup and torque sequence"
    remediation: "wayback_snapshot"
    resolved: true

records:
  - record_id: "G8BD.SB.0000001_001"
    source_url: "https://www.g8board.com/threads/rear-suspension-rebuild-the-easy-way.290127/"
---

> [!note] PPV Compatibility
> This procedure applies to 2011-2017 Caprice PPV dropouts. Earlier PPV years use different knuckle geometry.

## Rear Subframe Swap Procedure

The easiest upgrade path for the G8 rear suspension is a complete subframe swap from a 2017 Caprice PPV...

See also: [[G8BD.SB.0000038|Rear Wheel Bearing Replacement]]
```

#### Tombstone Document

```yaml
---
document_id: "TRGE.WB.0000042"
title: "BSG S01E01 — 33 (Wikipedia)"
status: "graduated"
graduated_to: "BSGF.EP.0000001"
graduated_corpus: "BSGF"
graduation_date: "2026-03-15"
---

This document has been graduated to [BSGF.EP.0000001](https://corpus.example.org/bsg/episodes/BSGF.EP.0000001.html) in the Battlestar Galactica corpus.
```

#### Graduation Lineage

```toml
# BSGF.EP.0000001.toml
title = "33 (Season 1, Episode 1)"
original_document_id = "TVSH.EP.0000015"

[prompts]
# ...
```

#### Document Issues

```yaml
issues:
  - type: "missing_media"
    severity: "major"
    description: "3 of 5 embedded images unavailable — showed timing chain alignment marks"
    remediation: "wayback_snapshot"
    resolved: false
  - type: "encoding_corruption"
    severity: "minor"
    description: "Two characters in torque spec table rendered as mojibake"
    remediation: "re_ingest"
    resolved: true
```

**Issues reporting output:**

```
Unresolved Issues for Corpus/g8board:
  critical: 2 documents (both remediable via wayback_snapshot)
  major: 8 documents (5 missing_media, 3 partial_content)
  minor: 15 documents
```

### 15.6 Multi-Origin Documents

Record breakdowns showing how multi-origin documents combine artifacts from different sources (section 3.1.2).

#### BSG Episode

A Battlestar Galactica episode document combining records from five origins:

| Record | Origin | Content |
|--------|--------|---------|
| `BSGF.EP.0000001_001` | `episodes` | Episode transcript |
| `BSGF.EP.0000001_002` | `wikipedia` | Wikipedia episode summary |
| `BSGF.EP.0000001_003` | `imdb` | IMDB episode page (cast, ratings, trivia) |
| `BSGF.EP.0000001_004` | `reddit` | r/BSG episode discussion thread |
| `BSGF.EP.0000001_005` | `scripts` | Shooting script PDF |

Assembly compiles these five records into a single episode document at `material/episodes/BSGF.EP.0000001/BSGF.EP.0000001.md`, drawing on all perspectives to produce a comprehensive episode reference.

#### Music Entity Corpus

A music entity corpus with a Gorguts partition:

| Record | Origin | Content |
|--------|--------|---------|
| `MUSC.GG.0000001_001` | `metal-archives` | Metal Archives band page |
| `MUSC.GG.0000001_002` | `wikipedia` | Wikipedia artist article |
| `MUSC.GG.0000001_003` | `rate-your-music` | RYM artist page and discography |

| Record | Origin | Content |
|--------|--------|---------|
| `MUSC.GG.0000002_001` | `metal-archives` | Metal Archives album page for *Obscura* |
| `MUSC.GG.0000002_002` | `rate-your-music` | RYM album page with reviews |
| `MUSC.GG.0000002_003` | `youtube` | Live performance of tracks from the album |

The band document (`MUSC.GG.0000001`) and each album document (`MUSC.GG.0000002`, etc.) each coalesce records from multiple origins. The partition groups all Gorguts material together. If Gorguts accumulates enough mass, the entire `GG` partition could graduate to its own `GRGT` corpus.

#### Source and Entity Corpora Reference

**Source corpora** (organized by voice):

| Voice | Corpus Repo | Contains |
|-------|-------------|----------|
| General Motors | `gm` | Service manuals, TSBs, recalls, press releases, dealer bulletins, brochures |
| Holden | `holden` | Workshop manuals, Australian-market documentation, press releases |
| Penrite Oils | `penrite` | Product datasheets, application guides, safety data sheets |
| G8Board.com | `g8board` | All forum threads from this community |
| LS1Tech.com | `ls1tech` | All forum threads from this community |
| Frank Herbert | `frank-herbert` | Novels, short stories, essays, interviews |
| Engineering Explained | `engineering-explained` | All videos from this channel |
| South Main Auto | `south-main-auto` | All videos from this channel |
| NHTSA | `nhtsa` | Recall databases, safety ratings, investigation reports |
| Metal Archives | `metal-archives` | All band/album/review pages from the site |
| RateYourMusic | `rate-your-music` | All artist/album/review data from the site |
| Triage (catch-all) | `triage` | Unsorted content awaiting graduation to dedicated corpora |

**Entity corpora** (organized by subject):

| Subject | Corpus Repo | Contains | Origins |
|---------|-------------|----------|---------|
| Music | `music` | Band pages, albums, songs, reviews, live recordings | Metal Archives, RYM, YouTube, Bandcamp, Wikipedia |
| Battlestar Galactica | `bsg` | Episodes, characters, lore, production docs | Episode files, Wikipedia, IMDB, Reddit, scripts |
| Dune Films | `dune-films` | Screenplays, behind-the-scenes, interviews | Production archives, press, interviews |
| Gorguts (graduated from music) | `gorguts` | Everything about the band and discography | Same origins, Gorguts-specific |

Entity corpora start broad (a music corpus partitioned by bands) and may eventually spawn more specific entity corpora (a Gorguts corpus) as material accumulates. Documents graduate upward through the classification chain — see section 3.3.5.

### 15.7 Corpus Discovery

Complete summary tier examples for the format defined in section 5.

```toml
# frank-herbert.toml (summary fields — other fields omitted for clarity)

summary_tier1 = "Complete works of science fiction author Frank Herbert"

summary_tier2 = """
All published works by Frank Herbert (1920-1986), primarily the six \
Dune novels (1965-1985) plus standalone novels, short fiction, and \
collaborations. Themes: ecology, prescience, politics, religion, \
human consciousness."""

summary_tier3 = """
Frank Herbert's complete published bibliography normalized from \
printed and digital editions.

Dune series: Dune (1965), Dune Messiah (1969), Children of Dune \
(1976), God Emperor of Dune (1981), Heretics of Dune (1984), \
Chapterhouse: Dune (1985).

Standalone novels: The Dragon in the Sea (1956), The Green Brain \
(1966), The Santaroga Barrier (1968), Whipping Star (1970), The \
Dosadi Experiment (1977), others.

Collaborations with Bill Ransom: The Jesus Incident (1979), The \
Lazarus Effect (1983), The Ascension Factor (1988).

~45 normalized documents."""
```

### 15.8 Compendium Configuration

Scripts and configuration examples for section 6.

#### Dependency Resolution Script

```bash
#!/bin/bash
# resolve.sh — resolve corpus dependencies declared in compendium.toml

FORGEJO_URL="${FORGEJO_URL:-https://forgejo.example.com}"

# Parse compendium.toml for corpus declarations (simplified — real implementation
# would use a TOML parser or a dedicated build tool)
# For each declared corpus: clone at pinned commit with sparse checkout

clone_corpus() {
    local name="$1" repo="$2" commit="$3"
    shift 3
    local sparse_paths=("$@")

    local target="corpora/$name"

    if [ -d "$target" ]; then
        echo "Updating $name to $commit"
        cd "$target"
        git fetch origin
        git checkout "$commit"
        cd - > /dev/null
    else
        echo "Cloning $name at $commit"
        git clone --no-checkout "$FORGEJO_URL/$repo.git" "$target"
        cd "$target"
        git sparse-checkout init
        git sparse-checkout set "${sparse_paths[@]}"
        git checkout "$commit"
        cd - > /dev/null
    fi
}

# Example invocations (generated from compendium.toml):
# clone_corpus "g8board" "Corpus/g8board" "a1b2c3d" "material/" "g8board.toml"
```

#### Synthesis System Prompt

```markdown
# Dune Universe Compendium — Synthesis Prompt

You are synthesizing a comprehensive reference for the Dune franchise.

## Scope

The Dune franchise encompasses:
- Frank Herbert's six original novels (1965-1985)
- Brian Herbert and Kevin J. Anderson's continuation novels and prequels
- David Lynch's Dune (1984 film)
- Sci Fi Channel miniseries: Frank Herbert's Dune (2000), Children of Dune (2003)
- Denis Villeneuve's films: Dune: Part One (2021), Dune: Part Two (2024)
- The Dune: Awakening video game

## Document Selection

From multi-work corpora (frank-herbert, denis-villeneuve), select only
documents whose descriptions indicate Dune-related content. Frank Herbert's
non-Dune novels (The Dragon in the Sea, Whipping Star, etc.) and
Villeneuve's non-Dune films (Blade Runner 2049, Arrival) are out of scope.

## Key Relationships

- Paul Atreides is the son of Duke Leto Atreides and Lady Jessica
- The Bene Gesserit breeding program aimed to produce the Kwisatz Haderach
- Arrakis is the sole source of the spice melange
- The Fremen are the native population of Arrakis
...
```

### 15.9 CI/CD Workflows

Workflow templates for section 9.

#### Compendium Deployment

```yaml
# .forgejo/workflows/deploy.yml
name: Build and Deploy Compendium
on:
  push:
    branches: [main]
    paths:
      - 'content/**'
      - 'quartz.config.ts'
      - 'compendium.toml'

jobs:
  deploy:
    runs-on: [self-hosted]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1              # shallow clone — no full history needed
      - name: Resolve corpora
        run: bash resolve.sh          # clones corpora at pinned commits with sparse checkout
      - name: Build
        run: npx quartz build
      - name: Deploy
        run: |
          rsync -avz --delete public/ deploy@caddy-vps:/srv/ref/${GITHUB_REPOSITORY##*/}/
```

#### Corpus Site Deployment

```yaml
# .forgejo/workflows/deploy-corpus.yml
name: Build and Deploy Corpus Site
on:
  push:
    branches: [main]
    paths:
      - 'material/**'
      - 'quartz.config.ts'

jobs:
  deploy:
    runs-on: [self-hosted]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - name: Export
        run: bash export.sh           # builds content/ from material/
      - name: Build
        run: npx quartz build
      - name: Deploy
        run: |
          rsync -avz --delete public/ deploy@caddy-vps:/srv/corpus/${GITHUB_REPOSITORY##*/}/
```

### 15.10 Agent Behavior

Example agent interactions for sections 10-11.

#### Automotive Domain Agent

```
User: "My car is making a clunking sound when I turn at low speed,
       especially in parking lots."

Agent thinking:
  - Symptoms: clunk, low speed, turning
  - Taxonomy → Suspension → CV joints, wheel bearings, sway bar links
  - Also: Steering → intermediate shaft, rack mounts

Agent fetches:
  - /commodore-ve/suspension/sway-bar-links.html
  - /commodore-ve/suspension/wheel-bearings.html
  - /commodore-ve/steering/intermediate-shaft.html

Agent response:
  "The most common cause of a low-speed clunk during turns on the
   VE platform is worn sway bar end links (confirmed by 23 forum
   reports [G8BD.SB.0000001, G8BD.SB.0000002, ...], typically appearing between
   60-90k miles). The second most likely cause is the steering
   intermediate shaft — a known weakness that GM issued TSB
   #PI0597B for [GMOT.TB.0000023]..."
```

#### Fiction Domain Agent

```
User: "How does the Bene Gesserit breeding program connect to
       Paul's prescience?"

Agent thinking:
  - Topics: Bene Gesserit, breeding program, Kwisatz Haderach,
    prescience, Paul Atreides
  - Taxonomy → Factions → Bene Gesserit → Breeding Program
  - Also: Characters → Paul Atreides → Abilities

Agent fetches:
  - /dune/factions/bene-gesserit/breeding-program.html
  - /dune/characters/paul-atreides/prescience.html

Agent response:
  "The breeding program was a multi-generational effort to produce
   the Kwisatz Haderach — a male Bene Gesserit who could access
   both masculine and feminine ancestral memories [FHBT.NV.0000001, ch.1].
   Jessica's decision to bear a son one generation early meant Paul
   was uncontrolled by the Sisterhood's plans [FHBT.NV.0000001, ch.3]...

   The Villeneuve adaptation emphasizes this tension visually in
   the Reverend Mother's testing scene [DVNV.FL.0000001, act 1], though it
   compresses the political context that Herbert developed across
   several chapters..."
```

---

## Appendix A: Example Compendium Configurations

### A.1 Commodore VE (Automotive)

```
Corpora: g8board, ls1tech, gm, holden, penrite
Taxonomy: by vehicle system (engine, drivetrain, suspension, electrical, ...)
Agent persona: Expert mechanic familiar with the VE/WM platform
System prompt: Platform equivalencies (G8 = VE Commodore), engine options
  (L76, LS3, LY7), common failure modes, TSB cross-references
```

### A.2 Dune Universe (Fiction)

```
Corpora: frank-herbert, brian-herbert, denis-villeneuve, scifi-channel-dune
Taxonomy: by world element (characters, factions, locations, technology, themes, adaptations)
Agent persona: Dune scholar with access to all canonical and adaptation material
System prompt: Franchise scope (novels, films, TV, games), key character
  relationships, document selection guidance for multi-work corpora
```

**Alternative: franchise corpus.** The Dune film adaptations could alternatively be organized as a franchise corpus `dune-films` (section 3.1.2) combining Denis Villeneuve's films, the David Lynch film, and the Sci Fi Channel miniseries — all sharing a single editorial identity as "Dune screen adaptations." This would use multi-origin documents (screenplay + behind-the-scenes + interviews per production) and cross-reference the author corpora. The choice between per-director corpora and a franchise corpus depends on whether the compendium needs to distinguish directorial voices or treat all screen adaptations as one body of work.

### A.3 Economics (Academic)

```
Corpora: marxists-org, jstor-economics, wikipedia-economics, ...
Taxonomy: by school of thought and topic area
Agent persona: Economics professor with breadth across schools of thought
System prompt: Schools of thought boundaries, key theorists, document selection
  guidance for broad economic content
```

### A.4 Socialism (Focused Academic)

```
Corpora: marxists-org, jstor-economics, ...
Taxonomy: by theoretical framework and historical application
Agent persona: Political theory specialist focused on socialist thought
System prompt: Scope limited to socialist theory and its applications,
  document selection from shared corpora focuses on class analysis, labor
  theory, historical socialist movements
```

---

## Appendix B: Future Considerations

### B.1 Public Compendia

Some domains may be worth sharing publicly. A car compendium for a specific platform would be genuinely valuable to other owners. The per-compendium auth gateway (Phase 2) would allow individual compendiums to be toggled public while others remain private.

### B.2 Collaborative Contribution

If a compendium is made public, contributions become possible via pull requests — either to corpus repos (new documents) or to compendium repos (synthesis improvements). The Forgejo PR workflow supports this naturally.

### B.3 Agent Self-Improvement Feedback Loop

**Partially realized in v3.0.** The Curator skill (section 12.5) implements an assess → prioritize → propose → execute → report loop with a self-improvement playbook. Coverage gap signals from domain agents can feed into the Curator's prioritization framework. The remaining future work is formalizing the feedback path from domain agents to the Curator.

### B.4 Multi-Format Export

The same compendium markdown could be exported to additional formats: PDF for offline reading, EPUB for e-readers, or structured JSON for programmatic access. These are build-step additions that don't affect the source material.

### B.5 Corpus Ingestion Automation

**Realized in v3.0.** The pipeline agent architecture (section 12) formalizes corpus ingestion automation. The Curator skill autonomously assesses, prioritizes, and dispatches ingestor, normalizer, and assembler agents. Remaining future work: scheduled triggers (cron-based scraper runs, RSS monitors) and fully unattended operation without human approval of the Curator's proposals.

### B.6 Automated Graduation Triggers

Graduation (section 3.3.5) is currently operator-initiated. Future work could automate graduation triggers: when a new corpus is created with routing claims, automatically scan triage for matching content and propose batch graduation. Additionally, content clustering in triage could proactively suggest when a dedicated corpus should be created.

### B.7 Routing Conflict Dashboard

As the number of corpora grows, routing claim conflicts (overlapping patterns, ambiguous matches) will need visibility. A dashboard that visualizes all routing claims, highlights overlaps, and tests URLs against the routing table would aid corpus ecosystem management.
