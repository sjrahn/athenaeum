---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 3.0
status: draft
author: Steven Rahn
date_created: 2026-02-08
date_modified: 2026-02-16
addenda_incorporated:
  - ATH-ARCH-A001
  - ATH-ARCH-A002
changelog:
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

Each domain of interest (automotive repair, political theory, a fiction universe) is treated as an independent **compendium** that pulls from one or more **corpora** — normalized repositories of source material organized by where the information came from, not what it's about. Each corpus can have multiple **origins** — distinct raw content sources like a YouTube channel, a blog, or a PDF archive — that feed into its normalized collection. Compendiums synthesize their corpora into authoritative **manuscripts** that are compiled into browsable, textbook-like references serving both human readers and bespoke AI agents.

Athenaeum is designed around four core principles:

- **Origin objectivity.** Sources are organized by where they came from — a forum, an author, a manual, a YouTube channel. This is an unchallengeable fact that requires no editorial judgment. Topical categorization happens downstream at the compendium layer.
- **Domain isolation.** Each compendium is fully independent — its own repository, its own synthesized reference, its own agent. There is no shared knowledge graph or cross-domain routing. When you need an expert, you call on them explicitly.
- **Human-first accessibility.** Every compendium is browsable and readable by a human, structured like a textbook with a table of contents, search, glossary, and source citations. The agent accesses the same artifact a human would.
- **Source provenance.** Every claim in the compendium traces back to its original source material. The agent can tell you not just "this is the answer" but "this answer is supported by the service manual, corroborated by 12 forum reports, and contradicted by one outlier."

### 1.1 Design Philosophy

The architecture intentionally avoids complexity where simplicity suffices. There is no vector database, no knowledge graph, and no domain router. Pipeline orchestration uses a lightweight agent pattern (section 12) — single-purpose workers coordinated by a skill, not a general-purpose multi-agent framework. These are not rejected — they are deferred until a concrete need for them is demonstrated. The system is designed so that any of these can be added later without rearchitecting what exists.

---

## 2. Architecture Overview

Athenaeum is organized into three conceptual layers. Raw sources enter the **Corpus** layer, where they are ingested, extracted, and normalized into markdown with rich descriptions. Each corpus carries tiered summaries in its `{corpus_id}.toml` that enable **corpus discovery** via progressive disclosure — compendiums can efficiently discover which corpora are relevant to their domain by fetching these summaries from the Forgejo API without cloning every corpus. The **Compendium** layer declares corpus dependencies, uses an LLM to select relevant documents based on descriptions, and synthesizes the selected material into domain-specific reference works guided by a compendium-specific system prompt.

**Terminology:** *Corpus* (plural: *corpora*) means "a body of collected texts" — this is where raw source material lives. *Compendium* means "a comprehensive collection of concise information" — this is where synthesized reference works live. *Manuscript* has a dual meaning depending on context: at the corpus level, it means "normalized documents structured for mdbook rendering" (the `manuscript/` directory in a corpus repo); at the compendium level, it means "synthesized reference content" (the `manuscript/` directory in a compendium repo). Both are mdbook source directories, but their content has different provenance. *Subdivision* refers to an organizational category within a corpus — subdivisions drive directory structure, mdbook chapters, and document ID assignment.

### 2.1 Corpus Layer

A corpus is a self-contained collection of normalized material from a single source of information — one voice. It represents everything captured from that source, processed through a four-phase pipeline — acquisition, reconciliation, extraction, and normalization — into markdown files with structured frontmatter. Each file carries a description that captures what the document contains and why it's useful. Every corpus builds as a browsable mdbook reference (see section 4), organized by mandatory subdivisions that categorize documents within the corpus.

A corpus can have multiple **origins** — distinct raw content sources that feed into it. A forum corpus has one origin (the forum itself). A manufacturer corpus might have several: a PDF archive of service manuals, a web database of technical bulletins, and a press release feed. Each origin has its own ingestion method and reingest configuration, declared in the corpus's registration file.

Key properties:

- **One voice, one corpus.** A forum is a corpus. An author is a corpus. A YouTube channel is a corpus. A manufacturer's entire catalog of publications is a corpus. The organizing principle is *who produced the information*, not what it's about.
- **Multiple origins, one corpus.** A single entity may publish through multiple channels and formats. These are different origins within the same corpus — the corpus groups them by voice, and each origin's ingestion pipeline handles format differences.
- **No editorial filtering.** A corpus contains everything from its source, summarized but unfiltered. Topical selection happens downstream at the compendium layer.
- **Summary-driven discovery.** Every normalized file carries a description that enables downstream selection without reading the full content. An LLM reading the description can determine whether the document is relevant to a given domain.

The range of corpora is deliberately broad: `g8board` (an automotive forum), `frank-herbert` (an author's collected works), `gm` (a manufacturer's manuals, bulletins, and press releases), `engineering-explained` (a YouTube channel's transcripts), `marxists-org` (a text archive). Each is independent and self-contained.

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

For example, a `dune` compendium declares dependencies on `frank-herbert`, `brian-herbert`, `denis-villeneuve`, and `scifi-channel-dune`. Its system prompt defines the Dune franchise scope and key relationships. During synthesis, the LLM reads document descriptions from each corpus — Frank Herbert's *Dune* and *Dune Messiah* are selected because their descriptions clearly relate to the Dune universe, while *Man of Two Worlds* (a comedy collaboration) and *The Dragon in the Sea* (a submarine thriller) are skipped. From `denis-villeneuve`, the Dune screenplays are selected while *Blade Runner 2049* and *Arrival* are not. The LLM's semantic understanding, guided by the system prompt, makes these selections — no tag matching required.

See section 6 for the detailed compendium structure and synthesis process.

### 2.4 Data Flow

The full pipeline from source to published reference:

```
  Raw Source (PDF, forum thread, transcript, ...)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 1a: Acquisition                      │
  │  acquire raw content to staging             │  script-driven or manual
  │  → .download/<descriptive-name>/            │  (gitignored)
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 1b: Reconciliation                   │
  │  assign identity, move to corpus            │  subdivision detection,
  │  → sources/<slug>/{document_id}/            │  ID assignment,
  │  → manuscript/<slug>/{document_id}.md       │  stub creation
  │    (status: pending_normalization)           │
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 2: Extraction                        │
  │  programmatic transform                     │  deterministic, no LLM
  │  → sources/<slug>/{document_id}/            │
  │    {document_id}_XXX.extract.md (sidecars)  │
  │  → manuscript/<slug>/assets/{document_id}/  │
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 3: Normalization                     │
  │  LLM-driven interpretation                  │  descriptions, credibility,
  │  → manuscript/<slug>/{document_id}.md       │  relations, frontmatter
  │    (status: normalized)                      │
  └─────────────────────────────────────────────┘
       │
       │  normalized markdown with description
       ├──────────────────────────────────────────┐
       ▼                                          ▼
  ┌──────────────────────────┐  ┌──────────────────────────────┐
  │  Corpus Book             │  │  Corpus Discovery            │
  │  mdbook build from       │  │  {corpus_id}.toml summaries  │
  │  manuscript/             │  │  fetched via Forgejo API     │
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
  Published Reference (browsable textbook + AI agent context)
```

Concretely: Frank Herbert's *Dune* enters the `frank-herbert` corpus as a raw epub file downloaded to `.download/` (acquisition). Reconciliation detects it belongs in the `novels` subdivision, assigns it `FHBT.NV.0000001`, moves the epub to `sources/novels/FHBT.NV.0000001/`, and creates a stub in `manuscript/novels/FHBT.NV.0000001.md`. Extraction produces a markdown sidecar with chapter text and metadata alongside the raw file. The normalization agent then interprets the sidecar into the final normalized markdown with a description describing it as a science fiction novel about ecology, politics, and prescience on the desert planet Arrakis, replacing the stub and setting `status: normalized`. The `frank-herbert.toml` captures the corpus scope across its tiered summaries. When the `dune` compendium is set up, tier 1 summaries fetched from all corpora immediately identify `frank-herbert` as relevant. At synthesis time, the LLM reads individual document descriptions within the cloned corpus and — guided by the compendium's system prompt — selects *Dune* and *Dune Messiah* while skipping *Man of Two Worlds*. The same `frank-herbert` corpus could simultaneously feed a hypothetical `sci-fi-comedy` compendium whose system prompt would guide selection of *Man of Two Worlds* instead.

---

## 3. Corpus Repositories

### 3.1 Corpus Identity

A corpus repository represents a single distinct voice — one entity that produces information. The question that determines a corpus boundary is not "what kind of document is it" or "what platform does it live on" but **"who produced it."**

If you can point at a source and say "that came from the same entity expressing its own perspective," it belongs in the same corpus. If two sources come from different entities — even if they're on the same platform, cover the same topic, or share the same format — they belong in separate corpora.

#### What "Voice" Means

A voice is an entity with a coherent perspective:

- A **company** — GM, Holden, Penrite Oils
- A **community** — one forum, one subreddit, one Discord server
- An **author** — Frank Herbert, Brian Herbert
- A **channel or show** — Engineering Explained, South Main Auto
- A **government body** — NHTSA, Australian ANCAP
- An **academic journal** — a single publication venue

A platform is never a voice. Reddit is not a corpus — r/MechanicAdvice is. YouTube is not a corpus — Engineering Explained is. "Car forums" is not a corpus — g8board is.

#### Consolidation by Entity, Not Document Type

All material produced by a single entity belongs in one corpus, regardless of document type or format. General Motors publishes service manuals, technical service bulletins, recall notices, press releases, dealer bulletins, and marketing brochures. These are all one voice: GM.

```
corpus/general-motors/
```

Within the `general-motors` corpus, individual documents use `content_type` to distinguish `service_manual` from `technical_bulletin` from `product_documentation` from `article`. Credibility tiers handle trust differences between a factory service manual (`authoritative`) and a marketing brochure (`expert` or lower). The corpus only answers: **who said this.**

#### Why Not Consolidate Similar Voices?

Five car forums (g8board, ls1tech, performanceforums, pontiacg8forum, holdenforums) share a platform type, content structure, and ingestion method. It's tempting to merge them into one `car-forums` corpus to reduce repo count. This is wrong for four reasons:

1. **Each community is a distinct voice.** g8board is G8-obsessed. ls1tech is LS-engine-first and happens to cover G8s. holdenforums brings the Australian VE platform perspective that American forums lack. These are genuinely different perspectives with different biases, different expertise concentrations, and different blind spots.

2. **Combining introduces the taxonomy problem we're avoiding.** The entire corpus architecture is built on the principle that "where it came from" is an unchallengeable fact requiring no editorial judgment. If you combine forums, you're making an editorial decision about which communities are "similar enough" — and that decision may need to be undone later.

3. **The compendium is where commonality is extracted.** Five forums all discussing rear wheel bearings is not a reason to combine them. It's a reason for the compendium to pull from all five and synthesize their perspectives. That's the compendium's job, not the corpus's.

4. **The friction of multiple repos is trivial.** Adding a corpus as a dependency is one line in `compendium.toml`. Sparse checkout is handled by `resolve.sh`. The real friction is untangling combined corpora later when you need one voice in a compendium but not another.

#### The Decision Test

When deciding whether something is one corpus or multiple:

1. **Can you name the entity?** "GM", "g8board", "Frank Herbert", "r/MechanicAdvice" — if you can name it as a single entity with a coherent identity, it's one corpus.

2. **Would you ever want one without the other in a compendium?** If ls1tech's LS engine content belongs in an engine-building compendium but g8board's doesn't, they must be separate corpora. You can't partially include a repo.

3. **Is the split based on document type or entity?** If you're splitting because "service manuals are different from press releases," stop — that's a `content_type` distinction, not a corpus distinction. If you're splitting because "GM and Holden are different manufacturers," proceed — those are different entities even though they shared a corporate parent.

#### Examples

| Voice (Entity) | Corpus Repo | Contains |
|----------------|-------------|----------|
| General Motors | `gm` | Service manuals, TSBs, recalls, press releases, dealer bulletins, brochures |
| Holden | `holden` | Workshop manuals, Australian-market documentation, press releases |
| Penrite Oils | `penrite` | Product datasheets, application guides, safety data sheets |
| G8Board.com | `g8board` | All forum threads from this community |
| LS1Tech.com | `ls1tech` | All forum threads from this community |
| Frank Herbert | `frank-herbert` | Novels, short stories, essays, interviews |
| Engineering Explained | `engineering-explained` | All videos from this channel |
| South Main Auto | `south-main-auto` | All videos from this channel |
| NHTSA | `nhtsa` | Recall databases, safety ratings, investigation reports |

### 3.2 Corpus Registration

Each corpus repo contains a registration file (`{corpus_id}.toml`) that declares metadata about the corpus, its origins, and its subdivisions. The filename matches the `corpus_id` by convention, enabling discovery tooling to cache all registration files in a flat directory without name collisions:

```toml
# g8board.toml
corpus_id = "g8board"
corpus_name = "G8Board.com"
corpus_prefix = "G8BD"
document_id_format = "G8BD.TT.NNNNNNN"

# tiered summaries for corpus discovery (see section 5)
summary_tier1 = "Pontiac G8 forum threads covering DIY repairs, modifications, diagnostics, and common problems"

summary_tier2 = """
Community forum posts from G8Board.com covering maintenance, repair, \
and modification of 2008-2009 Pontiac G8 vehicles (GT, GXP, base V6). \
Organized across 8 taxonomy subdivisions: Technical Articles & DIY, \
V8 Engine, Suspension & Brakes, Drivetrain, Exhaust, G8 GT Talk, \
Stereo & Electronics, and Intake & Fuel. Document IDs use \
G8BD.TT.NNNNNNN format."""

summary_tier3 = """
Normalized forum threads from G8Board.com (document IDs use \
G8BD.TT.NNNNNNN format, e.g. G8BD.TA.0000001), the primary \
community forum for Pontiac G8 owners and enthusiasts. Organized \
across 8 subdivisions covering: engine topics (L76 6.0L, LS3 6.2L, \
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

[[subdivision]]
code = "TA"
slug = "technical-articles-diy"
name = "Technical Articles & DIY"
description = "Community-written repair guides, installation how-tos, and diagnostic procedures"

[[subdivision]]
code = "V8"
slug = "v8-engine-tech-l76-ls3"
name = "V8 Engine"
description = "LS3/L76/LY7 engine topics: camshaft, lifters, oil, AFM/DoD, cooling"

[[subdivision]]
code = "SB"
slug = "suspension-brakes"
name = "Suspension & Brakes"
description = "Wheel bearings, sway bars, brake swaps, CTS-V/Brembo upgrades"

[[subdivision]]
code = "DT"
slug = "drivetrain-tech"
name = "Drivetrain"
description = "Transmission, torque converter, driveshaft, differential, manual swap"

[[subdivision]]
code = "EX"
slug = "exhaust-tech"
name = "Exhaust"
description = "Exhaust system modifications, catalytic converters, headers, mufflers"

[[subdivision]]
code = "GT"
slug = "g8-gt-talk-v8"
name = "G8 GT Talk"
description = "General V8 model discussion, common problems, ownership guides"

[[subdivision]]
code = "SE"
slug = "stereo-electronics"
name = "Stereo & Electronics"
description = "Audio, lighting, wiring, LED swaps, Bluetooth, radio programming"

[[subdivision]]
code = "IF"
slug = "intake-fuel-tech"
name = "Intake & Fuel"
description = "Intake manifold, fuel system, hose clamps, air intake modifications"
```

For a multi-document-type entity (see section 3.1), multiple origins and subdivisions within the corpus handle the different ingestion paths and organizational categories:

```toml
# gm.toml
corpus_id = "gm"
corpus_name = "General Motors"
corpus_prefix = "GMOT"
document_id_format = "GMOT.TT.NNNNNNN"

summary_tier1 = "General Motors official documentation — service manuals, TSBs, recalls"

summary_tier2 = """
Official publications from General Motors covering service manuals, \
technical service bulletins, recall notices, dealer bulletins, press \
releases, and brochures. Primarily North American market vehicles. \
Organized by document type subdivisions."""

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

[[subdivision]]
code = "SM"
slug = "service-manuals"
name = "Service Manuals"
description = "OEM factory service manual sections"

[[subdivision]]
code = "TB"
slug = "technical-bulletins"
name = "Technical Bulletins"
description = "TSBs, PIs, and recall notices"

[[subdivision]]
code = "PR"
slug = "press-releases"
name = "Press Releases"
description = "Official press releases and marketing documentation"
```

Each `[[origins]]` entry represents a distinct raw content source within the corpus. A single-origin corpus (like g8board) has one `[[origins]]` entry. A multi-origin corpus (like GM) has one entry per ingestion path. The `origin_type`, `origin_url`, `ingestion_method`, and `active` fields live at the origin level because they describe the raw content source, not the corpus as a whole.

Each origin's `[origins.reingest]` section defines the default volatility for documents from that origin and the thresholds for re-ingestion priority. Individual source files can override `default_volatility` via the `volatility` field in their extraction sidecar. The ingestion scanner compares each sidecar's `ingestion_date_last` against the appropriate threshold to generate a re-ingestion priority queue. If a document spans multiple origins, each sidecar carries its own volatility from its respective origin.

The `corpus_prefix` ensures globally unique document IDs across all corpora. Prefixes are 4 uppercase letters (allowing for 456,976 unique corpus prefixes). The full document ID format is `XXXX.TT.NNNNNNN` — a 4-letter corpus prefix, a 2-character uppercase alphanumeric subdivision code, and a 7-digit zero-padded sequence number. For example, `G8BD.TA.0000001` identifies the first document in the Technical Articles subdivision of the g8board corpus. When a compendium cites `G8BD.SB.0000003`, it unambiguously resolves to a specific file in a specific corpus repo and subdivision.

#### Subdivisions

**Subdivisions are mandatory.** Every corpus defines at least one `[[subdivision]]` entry in its `{corpus_id}.toml`. This means the document ID format is always `XXXX.TT.NNNNNNN` — there is no short form without a subdivision code.

Subdivisions drive three things: directory structure (files are organized under subdivision slug directories in both `manuscript/` and `sources/`), mdbook chapter organization (each subdivision becomes a top-level chapter in the corpus book), and ID assignment (the 2-character code is embedded in every document ID).

The subdivision structure varies by corpus type:

- **Forum corpus** (g8board): subdivisions map to forum sections — Technical Articles, V8 Engine, Suspension & Brakes, etc.
- **Author corpus** (frank-herbert): subdivisions map to work types — `NV` (novels), `SS` (short stories), `ES` (essays), `IN` (interviews).
- **Manufacturer corpus** (gm): subdivisions map to document types — `SM` (service manuals), `TB` (technical bulletins), `PR` (press releases).
- **YouTube channel** (engineering-explained): could use a single subdivision `VD` (videos) or subdivide by topic area.

Even a corpus with only one logical category still defines a subdivision — the format is universal.

#### 3.2.1 Corpus Repository Layout

Each corpus repo has a clean top-level structure:

```
Corpus/g8board/
├── g8board.toml                        # corpus registration + origin/subdivision configs
├── backlog.toml                        # non-captured entry tracking
├── book.toml                           # mdbook config (src = "manuscript")
├── manuscript/                         # normalized documents, organized by subdivision
│   ├── SUMMARY.md                      # mdbook table of contents
│   ├── README.md                       # corpus-level overview page
│   ├── suspension-brakes/              # subdivision slug directory
│   │   ├── README.md                   # subdivision overview
│   │   ├── G8BD.SB.0000001.md
│   │   ├── G8BD.SB.0000002.md
│   │   └── assets/                     # embedded content for this subdivision
│   │       └── G8BD.SB.0000002/
│   │           ├── bearing-removal.jpg
│   │           └── torque-sequence.png
│   └── technical-articles-diy/
│       ├── README.md
│       ├── G8BD.TA.0000001.md
│       └── G8BD.TA.0000002.md
├── sources/                            # raw files + extraction sidecars, by subdivision
│   ├── suspension-brakes/
│   │   ├── G8BD.SB.0000001/
│   │   │   ├── G8BD.SB.0000001_001.html
│   │   │   └── G8BD.SB.0000001_001.extract.md
│   │   └── G8BD.SB.0000002/
│   │       ├── G8BD.SB.0000002_001.html
│   │       └── G8BD.SB.0000002_001.extract.md
│   └── technical-articles-diy/
│       └── G8BD.TA.0000001/
│           ├── G8BD.TA.0000001_001.html
│           └── G8BD.TA.0000001_001.extract.md
└── .download/                          # staging area for acquired content (gitignored)
    └── example-thread.12345/
        └── thread.html
```

**Directory purposes:**

- **`manuscript/`** — Normalized documents structured for mdbook rendering. Organized by subdivision slug directories, each containing one markdown file per normalized document plus a `README.md` that serves as the subdivision's chapter overview. The corpus builds as a browsable mdbook reference (see section 4). Documents with `status: pending_normalization` exist here as stubs — minimal files created at reconciliation that serve as the work queue for the normalizer agent.
- **`manuscript/<slug>/assets/<doc_id>/`** — Images, diagrams, and other embedded content referenced by document files. Nested inside the manuscript tree so that mdbook resolves relative paths cleanly (documents reference assets via `./assets/<doc_id>/filename`). Assets are produced during extraction — the normalization agent references existing assets via the `assets` array in the extraction sidecar.
- **`sources/`** — Raw files and extraction sidecars, organized by subdivision slug and then by document ID. Raw files use standardized names (`{document_id}_XXX.{ext}` — three-digit sequence, original extension preserved). Each raw file is paired with an extraction sidecar (`{document_id}_XXX.extract.md`) that contains the programmatically extracted content as markdown with YAML frontmatter.
- **`.download/`** — Gitignored staging area for acquired content that has not yet been reconciled into the corpus. Acquisition scripts write raw content here; reconciliation moves it into `sources/` with a proper document ID. Failed acquisitions remain here without consuming IDs.
- **`book.toml`** — mdbook configuration for the corpus book (`src = "manuscript"`). See section 4.
- **`SUMMARY.md`** — mdbook table of contents. Subdivisions become top-level chapters, with individual documents listed as sub-entries.
- **Per-subdivision `README.md`** — Overview page for each subdivision chapter, describing the subdivision's scope.

**The many-to-one rule:** A single document can have multiple raw files in `sources/<slug>/{document_id}/` — the same content in different formats, multiple captures from different dates, or complementary representations (a transcript plus screenshots). Each raw file has its own extraction sidecar. Regardless of how many source files exist for a document, normalization always produces exactly **one markdown file** in `manuscript/<slug>/` per document ID.

#### 3.2.2 Document Backlog

Captured documents are self-describing — they exist as files in `manuscript/` with complete frontmatter. The `backlog.toml` file tracks entries that are *not yet captured*: known to exist, but pending ingestion, explicitly deferred, or currently unavailable.

**Backlog entries do not have document IDs.** IDs are assigned only at reconciliation (see section 3.3.2), not at discovery time. This is a deliberate design choice — it means failed acquisitions don't consume IDs, the backlog doesn't need to know about subdivision codes, and there are never phantom IDs referenced by no file.

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

For an author corpus, the backlog tracks works not yet acquired:

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

The `content_type` field on each extraction sidecar distinguishes what kind of content it is (`service_manual`, `technical_bulletin`, `article`, `product_documentation`). The backlog and corpus just track that it all comes from the same entity.

**Primary fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Human-readable title of the entry |
| `url` | string | no | Where this content can be acquired (for web-based origins) |
| `section` | string | no | Subdivision slug this entry belongs to (may be `"unknown"` if not yet categorized) |
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

- Every file in `manuscript/<slug>/` must have valid frontmatter with a `status` field
- Backlog entries with `status: ingested` should have a corresponding file in `manuscript/`
- No document file should exist without a corresponding directory in `sources/`

**Ingestion backlog reporting:**

```
Ingestion Backlog:
  Corpus/frank-herbert:     6 captured, 8 pending (2 high, 3 medium, 3 low), 2 deferred, 1 unavailable
  Corpus/g8board:          42 captured, 156 pending (12 critical, 45 high, 99 medium), 3 deferred
  Corpus/gm:               75 captured, 120 pending (20 high, 60 medium, 40 low), 5 deferred
```

### 3.3 Normalization Pipeline

The path from raw source to normalized markdown is a four-phase pipeline. Formalizing these phases makes the pipeline reproducible, auditable, and independently improvable — you can re-normalize from improved models without re-extracting, you can re-extract with better tools without re-downloading, and failed acquisitions never consume document IDs.

#### 3.3.1 Phase 1a: Acquisition

**What:** Acquire raw content from external sources into a staging area.

**How:** Script-driven or manual — web scrapers, downloaders, API clients, manual file copy.

**Output:** Raw files in `.download/<descriptive-name>/` — a gitignored staging area with no document IDs assigned. The naming convention is descriptive (e.g., `.download/afm-delete-guide.56789/thread.html`) because IDs don't exist yet.

Acquisition simply captures content; it performs no transformation and assigns no identity. Failed acquisitions (network errors, paywalled content, corrupt downloads) remain in `.download/` as orphans without consuming any corpus resources. The `.download/` directory is gitignored — it is a transient workspace, not part of the versioned corpus.

#### 3.3.2 Phase 1b: Reconciliation

**What:** Move acquired content from staging into the corpus, assigning identity.

**How:** Reconciliation tooling (or the ingestor agent — see section 12) auto-detects the appropriate subdivision from the content or backlog metadata, assigns the next available document ID within that subdivision, creates the source directory, and generates a document stub.

**Operations:**

1. **Subdivision detection.** Determine which subdivision the content belongs to — from backlog `section` field, from content analysis, or from explicit user input.
2. **ID assignment.** Assign the next sequential `XXXX.TT.NNNNNNN` ID within the detected subdivision.
3. **Source creation.** Move raw files from `.download/` to `sources/<slug>/{document_id}/` with standardized names (`{document_id}_XXX.{ext}`).
4. **Extraction.** Run the appropriate extraction script to produce sidecars alongside the raw files.
5. **Stub creation.** Create a document stub in `manuscript/<slug>/{document_id}.md` with `status: pending_normalization` — a minimal file containing frontmatter skeleton with the assigned ID, title, and status. This stub serves as the work queue entry for the normalizer agent.
6. **Backlog update.** Mark the corresponding backlog entry as `ingested` if one exists.

**Output:** A reconciled document with files in `sources/<slug>/{document_id}/` (raw files + extraction sidecars) and a stub in `manuscript/<slug>/{document_id}.md`. The sidecar's `document_id` field is populated during reconciliation — it was absent during acquisition.

**The stub pattern.** Reconciliation creates document stubs with `status: pending_normalization` in `manuscript/`. This replaces the v2.0 invariant of "no stubs, no placeholders" — stubs now serve as the explicit work queue for normalizer agents. A stub contains enough frontmatter for the document to appear in `SUMMARY.md` and be tracked, but its content is minimal until normalization completes and sets `status: normalized`.

#### 3.3.3 Phase 2: Extraction

**What:** Programmatic transformation of raw files into clean, structured extraction sidecars.

**How:** Content-type-specific scripts — no LLM involvement, deterministic processing only. Extraction is typically run as part of reconciliation (section 3.3.2) but can be re-run independently.

**Output:** One extraction sidecar per raw file (`{document_id}_XXX.extract.md`) alongside the raw file in `sources/<slug>/{document_id}/`, plus assets saved to `manuscript/<slug>/assets/{document_id}/`.

**Key principle:** Extraction captures *what's there* without editorial judgment. No summaries, no credibility assessment, no relevance decisions. It strips away format-specific noise (HTML chrome, PDF layout artifacts, ad content) and produces structured text that the normalization agent can interpret.

Operations that belong in extraction:

| Operation | Why extraction |
|-----------|---------------|
| Strip HTML chrome/ads | Rule-based, programmatic |
| OCR a scanned PDF | Tool-driven, no semantic judgment |
| Transcribe audio (Whisper) | Tool-driven, no semantic judgment |
| Extract text from epub | Programmatic |
| Parse forum thread structure (post boundaries, usernames, dates) | Pattern-based |
| Pull images from HTML/PDF | Programmatic |
| PDF table recognition | Tool-driven (even if ML-assisted internally) |

**Trivial extraction is fine.** A clean text file gets `extraction_method: "passthrough"` — the pipeline is uniform even when a phase does minimal work.

**Extraction sidecar format.** Each sidecar is a markdown file with YAML frontmatter containing extraction metadata, paired with the extracted clean content as the body:

```yaml
---
document_id: "G8BD.SB.0000001"
sequence: 1
content_type: "forum_post"
origin: "forum"
original_url: "https://www.g8board.com/threads/rear-suspension-rebuild-the-easy-way.290127/"
original_filename: "G8BD.SB.0000001_001.html"
capture_date: "2026-02-16"
ingestion_date_last: "2026-02-16"
content_changed_last: "2026-02-16"
date_published: "2024-01-24T00:46:23-05:00"
volatility: "unlikely"
extraction_method: "g8board-scraper"
extraction_tool: "scrape_thread.py v0.6"
extraction_date: "2026-02-16"
assets:
  - filename: "bearing-removal.jpg"
    context: "Shows bearing removal tool setup"
  - filename: "torque-sequence.png"
    context: "Torque sequence diagram for hub assembly"

# extended: forum_post
thread_url: "https://www.g8board.com/threads/rear-suspension-rebuild-the-easy-way.290127/"
reply_count: 13
---

[extracted clean text content]
```

The sidecar frontmatter follows these conventions:

- **`document_id`** and **`sequence`** — identify which document and which raw file this sidecar corresponds to.
- **`content_type`** — authoritative content type. The extraction script knows what it's processing — this is a definitive classification, not a hint. Closed enum (see section 3.3.3.1 for valid types and their extended fields).
- **`origin`** — which origin within the corpus this raw file came from (matches an `origin_id` in `{corpus_id}.toml`).
- **`original_url`** and **`original_filename`** — provenance of the raw file before standardized naming.
- **`capture_date`** — when the raw file was originally acquired.
- **`ingestion_date_last`** — when we last checked/re-ingested from the upstream source. Same as `capture_date` on initial capture. Used by the ingestion scanner to prioritize re-ingestion.
- **`content_changed_last`** — when the upstream content last actually differed from what we had. Used to assess source stability.
- **`author`** — the identifiable person who produced this content. Omit for anonymous content (anonymous forum posts use the `username` extended field instead).
- **`date_published`** — when the original content was published. Omit for undated content.
- **`volatility`** — override for the origin's `default_volatility`. Only set when this source's volatility differs from the origin norm. One of: `static`, `unlikely`, `periodic`, `active`.
- **`extraction_method`**, **`extraction_tool`**, **`extraction_date`** — extraction provenance, enabling targeted bulk re-extraction when tools improve.
- **`assets`** — filenames and context strings for extracted images/diagrams saved to `manuscript/<slug>/assets/{document_id}/`.

Extended fields are content-type-specific and follow the sidecar's `content_type`. These are programmatically determinable fields that the extraction script populates based on what it's processing. See section 3.3.3.1 for the extended fields defined for each content type.

**Asset extraction.** Images, diagrams, and other embedded content are extracted during this phase and saved to `manuscript/<slug>/assets/{document_id}/`. The `assets` array in the sidecar frontmatter provides filenames and context strings that the normalization agent uses to produce correct relative paths (`./assets/<doc_id>/filename`) and alt text in the final markdown document. Assets live inside the manuscript tree so that mdbook resolves relative paths without path rewriting.

##### 3.3.3.1 Extended Sidecar Fields by `content_type`

The `content_type` field determines which additional fields the extraction script populates on the sidecar. This is a closed enum — adding a new type requires defining its extended fields.

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

Covers: complete published works — novels, non-fiction books, collected works. **A single document is always the entire book.** In `sources/` the book may be split across many files (chapter PDFs, an epub, a complete PDF), but normalization always produces one markdown file per work.

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

Covers: YouTube videos, instructional content, any video-first source. Each video is one document file containing the transcript and, where relevant, descriptions of visual content.

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

#### 3.3.4 Phase 3: Normalization

**What:** LLM-driven interpretation of extracted content into final normalized markdown with full frontmatter.

**How:** A normalization agent (see section 12.3) consuming the extraction sidecars, guided by the frontmatter schema and corpus context. Normalization replaces the stub created at reconciliation with the full document content and sets `status: normalized`.

**Output:** `manuscript/<slug>/{document_id}.md` with complete YAML frontmatter (required fields, applicable optional fields, and the `sources` array linking to extraction sidecars) and structured markdown content.

**The normalization agent receives:**

1. Extraction sidecars for the document (one or more `.extract.md` files from `sources/<slug>/{document_id}/`)
2. `{corpus_id}.toml` context (corpus metadata, origin configs, credibility defaults)
3. The frontmatter schema (required fields, optional fields, and the sources array linking to extraction sidecars)
4. Content-type-specific guidance (how to structure forum threads vs. book chapters vs. video transcripts)

**The normalization agent is responsible for:**

| Operation | Why normalization |
|-----------|-------------------|
| Generate `description` | Requires content understanding |
| Assess `credibility_tier` | Requires domain judgment |
| Identify `relations` | Requires cross-document awareness |
| Flag `issues` | Requires quality judgment |
| Structure the markdown body | Requires editorial decisions about presentation |
| Populate the `sources` array | Requires mapping sidecars to the document they produced |
| Set `status: normalized` | Signals that the stub has been replaced with full content |

The spec defines what the normalization agent receives and produces without prescribing implementation form. The normalization agent definition lives in the corpus repo's `.claude/agents/` directory (see section 12.3), enabling corpus-specific customization while following a standardized pattern.

#### 3.3.5 Phase Boundaries and Re-processing

The four phases are designed to be independently re-runnable:

- **Re-acquisition** (Phase 1a only): Re-acquire from the upstream source when content may have changed. Content lands in `.download/` as fresh staging. Does not trigger re-reconciliation, re-extraction, or re-normalization unless the acquired content actually differs.
- **Re-reconciliation** (Phase 1b only): Rarely needed — typically only when a document needs to be reassigned to a different subdivision.
- **Re-extraction** (Phase 2 only): Re-create sidecars from existing source files when extraction tools improve (e.g., "find all documents extracted with tesseract v4 and re-extract with v5"). The `extraction_method` and `extraction_tool` sidecar fields enable targeted bulk re-extraction.
- **Re-normalization** (Phase 3 only): Re-normalize from existing extraction sidecars when LLM models improve. This is the most common re-processing scenario and the cheapest — no re-downloading, no re-extracting.

Extraction sidecars are persisted alongside raw files in `sources/` to enable this independence. Extraction is often the expensive step (OCR, Whisper transcription), and the resulting sidecars are small compared to raw files. Compendiums only clone `manuscript/` and `{corpus_id}.toml` — the `sources/` directory (raw files and sidecars) and `.download/` staging area are never needed downstream.

### 3.4 Normalized Document Format

Every normalized document file is a single markdown file with structured YAML frontmatter. The frontmatter carries document identity, a description for discovery, quality metadata, and a lightweight `sources` array linking to the extraction sidecars that were used to produce it. Per-source metadata — content type, author, dates, and content-type-specific fields — lives on the extraction sidecars (section 3.3.3), not the document.

#### 3.4.1 Required Fields

Every document file must include all of these fields, no exceptions:

| Field | Type | Description |
|-------|------|-------------|
| `document_id` | string | `XXXX.TT.NNNNNNN` globally unique identifier (4-letter corpus prefix + 2-char subdivision code + 7-digit number) |
| `title` | string | Short descriptive label for the document file (not necessarily the work's canonical title) |
| `description` | string | One-to-three sentence description of what this document contains and why it's useful. Generated during normalization. Enables synthesis-time relevance assessment without reading the full content |
| `credibility_tier` | enum | `authoritative`, `expert`, `community_validated`, `anecdotal`, `speculative`. See section 3.5 |
| `normalization_confidence` | float | `0.0`–`1.0`, quality of the conversion process. See section 3.5.1 |
| `normalization_model` | string | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`) |
| `normalization_date` | date | When normalization was last performed. **This is the field the compendium layer compares against to determine if re-synthesis is needed** — it captures both content changes and re-normalization with improved models |
| `status` | enum | `pending_normalization` or `normalized`. Documents start as stubs (`pending_normalization`) created at reconciliation and transition to `normalized` when the normalizer agent completes processing |
| `sources` | array | One entry per raw file used to produce this document. See section 3.4.3 |

#### 3.4.2 Optional Fields

These fields are present on some documents but legitimately absent on most:

| Field | Type | When absent |
|-------|------|-------------|
| `relations` | array | No explicit references to other documents. See section 3.7 |
| `issues` | array | No known quality or completeness problems. See section 3.6 |

#### 3.4.3 Sources Array

Each entry in the `sources` array links to one extraction sidecar used to produce this document. The sidecar (in `sources/<slug>/{document_id}/`) holds the full per-source metadata — content type, author, dates, and content-type-specific fields. The document frontmatter carries only a reference and a human-readable identifier.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | string | Identifies the raw file and its sidecar: `{document_id}_XXX` (e.g., `G8BD.SB.0000001_001`) |
| `origin_url` | string | URL of the original content. Use `original_filename` instead for offline sources |
| `original_filename` | string | Filename of the original content. Use when `origin_url` is absent |

#### 3.4.4 Complete Example

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
status: "normalized"

relations:
  - type: "references"
    unresolved: "GM TSB #PI0597B"
issues:
  - type: "missing_media"
    severity: "major"
    description: "2 of 4 embedded images unavailable — showed bearing removal tool setup and torque sequence"
    remediation: "wayback_snapshot"
    resolved: true

sources:
  - source_id: "G8BD.SB.0000001_001"
    origin_url: "https://www.g8board.com/threads/rear-suspension-rebuild-the-easy-way.290127/"
---

[normalized markdown content]
```

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

The `issues` field is universal optional. Its absence means "no known issues."

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

The `resolved` boolean tracks whether the issue has been addressed. The typical workflow: normalization flags dead images → issue is logged with `remediation: "wayback_snapshot"` → Wayback snapshot is retrieved and added to `sources/<slug>/{document_id}/` → document is re-normalized from improved raw material → issue is marked `resolved: true`. The issue remains in frontmatter as a historical record.

For the `content_modified` type, the remediation may involve pulling both the current version and a Wayback snapshot as separate raw files. A forum post edited to add "UPDATE: don't do this, it caused X" is more valuable with both versions visible — the normalization can reconcile them or note the differences.

Build-time scanning can surface unresolved issues as a prioritized remediation queue:

```
Unresolved Issues for Corpus/g8board:
  critical: 2 documents (both remediable via wayback_snapshot)
  major: 8 documents (5 missing_media, 3 partial_content)
  minor: 15 documents
```

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

The corpus-as-repo pattern supports any content type. The only requirement is a pipeline that can ingest, extract, and normalize the content into markdown with frontmatter. The extraction phase (see section 3.3) handles format-specific programmatic transformation; the normalization phase handles LLM-driven interpretation.

**YouTube channels:** Ingestion downloads the video/audio. Extraction runs a transcription tool (e.g., Whisper) and captures frame data, producing a markdown sidecar with timestamped transcript segments and visual content metadata. The normalization agent then interprets the sidecar into final markdown with description, credibility assessment, and structured frontmatter. Each video is one document file.

```yaml
---
document_id: "ENEX.VD.0000017"
title: "Engineering Explained — Why Direct Injection Causes Carbon Buildup"
description: "Technical explainer covering the mechanism by which direct injection engines accumulate carbon deposits on intake valves, why port injection doesn't have this problem, and what solutions exist including walnut blasting and dual injection systems."
credibility_tier: "expert"
normalization_confidence: 0.85
normalization_model: "claude-sonnet-4-5-20250929"
normalization_date: "2026-02-01"
status: "normalized"

sources:
  - source_id: "ENEX.VD.0000017_001"
    origin_url: "https://youtube.com/watch?v=..."
---

[transcript with timestamps and descriptive notes for visual content]
```

**Authors (fiction):** Extraction handles format conversion (epub parsing, OCR for scanned editions). Each work is normalized into one or more document files — a short story as one file, a novel potentially split into chapters. The primary text is `authoritative` credibility. Introductions, afterwords, and interviews are tagged separately.

**Podcasts:** Similar to YouTube — extraction runs the transcription tool, normalization interprets the result. One episode per document file.

**Government / institutional sources:** Extraction handles PDF text extraction, OCR, and table recognition. The normalization agent interprets the extracted content into markdown. Each publication is one document file.

---

## 4. Corpus Format

### 4.1 Overview

Corpora are not just data stores — they are browsable mdbook references. Each corpus builds as a self-contained static site where every normalized document is readable in a web browser. This serves three purposes: human review of normalized documents without opening raw files, a navigable corpus overview organized by subdivision, and a shareable reference that can be hosted independently of the compendium layer.

The term "corpus manuscript" refers to the normalized documents structured for mdbook rendering — the `manuscript/` directory is the mdbook source. This is distinct from "compendium manuscript," which refers to the synthesized reference content in a compendium's `manuscript/` directory. Both use mdbook as the rendering engine, but their content has fundamentally different provenance: corpus manuscripts are normalized source material, compendium manuscripts are LLM-synthesized domain knowledge.

### 4.2 book.toml

Each corpus repository contains a `book.toml` at its root:

```toml
[book]
title = "G8Board.com Corpus"
authors = ["Steven Rahn"]
language = "en"
src = "manuscript"

[build]
build-dir = ".build"

[preprocessor.frontmatter-strip]

[output.html]
default-theme = "navy"

[output.html.fold]
enable = true
level = 0
```

Key configuration:

- **`src = "manuscript"`** — points mdbook at the `manuscript/` directory as its source.
- **`[preprocessor.frontmatter-strip]`** — uses the `mdbook-frontmatter` crate (third-party preprocessor) to strip YAML frontmatter from rendered HTML output. This is essential because every document file carries YAML frontmatter for machine-readable metadata, but this metadata should not appear in the rendered book. The preprocessor removes everything between `---` delimiters before rendering.
- **`build-dir = ".build"`** — keeps build output separate from the source tree (gitignored).
- **`[output.html.fold]`** — collapses chapter entries by default for cleaner navigation in corpora with many documents.

### 4.3 Chapter Organization

Subdivisions become top-level chapters in the corpus book. The `SUMMARY.md` file defines the mdbook table of contents:

```markdown
# Summary

[G8Board.com Corpus](./README.md)

---

- [Drivetrain](./drivetrain-tech/README.md)
    - [G8BD.DT.0000001 - Trans mount bolt sizes](./drivetrain-tech/G8BD.DT.0000001.md)
    - [G8BD.DT.0000002 - Diff compatibility list](./drivetrain-tech/G8BD.DT.0000002.md)
- [Suspension & Brakes](./suspension-brakes/README.md)
    - [G8BD.SB.0000001 - Rear Suspension Rebuild](./suspension-brakes/G8BD.SB.0000001.md)
    - [G8BD.SB.0000002 - Brake upgrade P/Ns](./suspension-brakes/G8BD.SB.0000002.md)
- [Technical Articles & DIY](./technical-articles-diy/README.md)
    - [G8BD.TA.0000001 - Backup sensor info](./technical-articles-diy/G8BD.TA.0000001.md)
    ...
```

Each subdivision directory contains a `README.md` that serves as the chapter landing page, describing the subdivision's scope and listing its contents. Document entries in `SUMMARY.md` use the format `[{document_id} - {title}]({path})` for consistent navigation.

The `SUMMARY.md` is maintained as documents are added — reconciliation (section 3.3.2) adds new document entries, and the normalizer updates the title if it changes during normalization.

### 4.4 Hosting

Corpus books are hosted at `corpus.example.org/{corpus_id}/`:

```
https://corpus.example.org/g8board/          → G8Board corpus book
https://corpus.example.org/frank-herbert/    → Frank Herbert corpus book
https://corpus.example.org/gm/              → General Motors corpus book
```

CI/CD for corpus books follows the same pattern as compendium deployment (see section 9): push to main triggers an mdbook build, and the output is deployed to the Caddy server. The corpus CI workflow is simpler than the compendium workflow because there are no corpus dependencies to resolve — the `manuscript/` directory is the complete source.

### 4.5 Relationship to Compendium

A corpus book and a compendium book serve different purposes from the same underlying technology:

| Aspect | Corpus Book | Compendium Book |
|--------|-------------|-----------------|
| **Content** | All normalized documents, unfiltered | Synthesized, curated domain reference |
| **Organization** | By subdivision (where it came from) | By domain taxonomy (what it's about) |
| **Authorship** | Normalization agent (faithful to source) | Synthesis agent (editorial judgment) |
| **Audience** | Corpus maintainer, QA review | End users, domain agents |
| **Scope** | Single voice | Multiple corpora, multiple voices |

The corpus book is a raw reference — every document in the corpus is visible and browsable. The compendium is a synthesized view — it selects, filters, and reorganizes content from multiple corpora into a coherent domain reference. A developer reviewing normalization quality browses the corpus book. A user or agent seeking domain knowledge browses the compendium.

---

## 5. Corpus Discovery

### 5.1 Overview

Corpus discovery enables compendiums to identify which corpora are relevant to their domain without cloning and scanning every corpus repository. Each corpus's `{corpus_id}.toml` carries tiered summaries that describe the corpus (see section 3.2 for format). At compendium setup time, these summaries are fetched via the Forgejo API — no separate registry repository is needed.

This design follows the spec's principle of avoiding unnecessary infrastructure. The corpora describe themselves; discovery is a computed view over the Corpus organization, not a maintained artifact.

### 5.2 Summary Tier Format

Each `{corpus_id}.toml` includes three summary tiers alongside the corpus's registration metadata:

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

The tiers are designed for progressive disclosure:

- **`summary_tier1`** — A single sentence. Enough to include or exclude at a glance.
- **`summary_tier2`** — A concise paragraph. Enough to confirm relevance and understand scope.
- **`summary_tier3`** — A comprehensive description. Full detail on what the corpus contains, its document count, and its coverage.

### 5.3 API-Driven Discovery Process

Discovery tooling fetches summaries from the Forgejo API without cloning any repos:

1. **Enumerate corpora.** `GET /api/v1/orgs/corpus/repos` — list all repositories in the Corpus organization. Each repo is one corpus.

2. **Fetch corpus metadata.** For each repo, `GET /api/v1/repos/corpus/{name}/contents/{name}.toml` — fetch the file contents via API. These requests are parallelized.

3. **Parse and extract.** Parse each `{corpus_id}.toml` and extract `corpus_id`, `summary_tier1`, `summary_tier2`, `summary_tier3`.

This produces a complete discovery index from live data in seconds, even for hundreds of corpora. The index can be cached locally and refreshed on demand.

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

---

## 6. Compendium Synthesis

### 6.1 Repository Structure

Each compendium repository has this structure:

```
Compendium/{domain}/
├── .gitignore                     # ignores corpora/ (resolved at build time)
├── corpora/                       # resolved corpus repos (gitignored, like node_modules)
│   ├── g8board/                   → resolved (sparse: manuscript/ + g8board.toml)
│   ├── gm/                        → resolved (sparse: manuscript/ + gm.toml)
│   └── ls1tech/                   → resolved (sparse: manuscript/ + ls1tech.toml)
├── manuscript/                    # pre-rendered compendium content (mdBook source)
│   ├── SUMMARY.md                 # mdBook table of contents
│   ├── introduction.md
│   ├── quick-reference.md
│   ├── faq.md
│   ├── glossary.md
│   ├── references.md              # master document registry
│   └── {chapter-slug}/            # chapters organized by domain taxonomy
│       ├── {section}.md
│       └── ...
├── compendium.toml                # compendium configuration (dependencies, system prompt, etc.)
├── book.toml                      # mdBook configuration (src = "manuscript")
├── resolve.sh                     # clones/updates corpora from declared dependencies
└── README.md
```

### 6.2 Dependency Resolution

Compendium repos only need the `manuscript/` directory and `{corpus_id}.toml` from each corpus — never the `sources/` directory (which contains raw files and extraction sidecars used only for re-normalization within the corpus repo). Assets are included because they live inside `manuscript/`. Each corpus dependency is declared in `compendium.toml` with a pinned commit hash and the sparse paths to check out:

```toml
[[compendium.corpora]]
name = "g8board"
repo = "corpus/g8board"
commit = "a1b2c3d"
sparse = ["manuscript/", "g8board.toml"]
```

The `corpora/` directory is gitignored — it is populated on demand by a `resolve.sh` script that clones each declared corpus at its pinned commit with sparse checkout:

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
# clone_corpus "g8board" "Corpus/g8board" "a1b2c3d" "manuscript/" "g8board.toml"
```

This script is run once after cloning the compendium repo, before synthesis, and by the CI workflow on every build. Because `corpora/` is gitignored, the compendium repo itself stays clean — only the manuscript, configuration, and tooling are versioned.

### 6.3 The Synthesis Process

Synthesis transforms source material from multiple corpora into a coherent, structured compendium. This is the core intellectual work of the system.

The process for each compendium:

1. **Resolve corpora.** Run `resolve.sh` to clone/update all declared corpus dependencies at their pinned commits.
2. **Select documents.** Read the `description` field of each document file across all resolved corpora. Using the compendium's synthesis system prompt as context, the LLM selects documents relevant to the domain. Documents are prioritized by credibility tier and relevance to the compendium's scope.
3. **Organize by taxonomy.** Group selected documents by the compendium's chapter structure.
4. **Synthesize chapters.** Distill the grouped documents into coherent prose, reconciling conflicts, identifying patterns, and citing document IDs.
5. **Build navigation.** Generate/update `SUMMARY.md`, cross-references, and supplementary sections (FAQ, glossary, quick reference).
6. **Build output.** Run mdBook to compile the manuscript into the published static site.

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
sparse = ["manuscript/", "frank-herbert.toml"]

[[compendium.corpora]]
name = "brian-herbert"
repo = "corpus/brian-herbert"
commit = "a1b2c3d"
sparse = ["manuscript/", "brian-herbert.toml"]

[[compendium.corpora]]
name = "denis-villeneuve"
repo = "corpus/denis-villeneuve"
commit = "c3d4e5f"
sparse = ["manuscript/", "denis-villeneuve.toml"]

[[compendium.corpora]]
name = "scifi-channel-dune"
repo = "corpus/scifi-channel-dune"
commit = "f7e8d9c"
sparse = ["manuscript/", "scifi-channel-dune.toml"]
include_all = true          # every document in this corpus is relevant — skip description assessment
```

The `system_prompt_file` points to a markdown file in the compendium repo that provides the LLM with domain context during synthesis. This is where relationships, disambiguation guidance, and scope boundaries live:

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

### 7.1 mdBook

The compendium is built as an **mdBook** — a static documentation site generated from structured markdown files. mdBook was selected because:

- Source files are plain markdown in git (the single source of truth)
- Generates clean, navigable HTML with built-in full-text search
- Table of contents generated from `SUMMARY.md`
- Cross-references between chapters via standard markdown links
- Supports embedded images for diagrams, photos, and visual references
- Generates `searchindex.json` for programmatic full-text search
- Lightweight, fast, and self-hostable
- Rust-based toolchain

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

The `SUMMARY.md` file serves as both the mdBook table of contents and the agent's navigation map. It provides hierarchical structure down to the section level.

mdBook also generates a `searchindex.json` file at build time that provides full-text search across all pages. This serves as the compendium's index — mapping keywords, part numbers, symptoms, and any other terms to the sections where they appear. See section 11.2 for how the agent leverages this.

### 7.4 Compendium Page Frontmatter

mdBook supports YAML frontmatter on pages — it ignores it during rendering, which makes it ideal for metadata that tooling and agents can read without polluting the HTML output. Every compendium chapter page carries synthesis provenance and per-document traceability:

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
For each chapter in manuscript/:
  For each document in chapter.documents:
    Fetch the document file from corpora/
    If document.normalization_date > chapter_document.synthesized_at:
      Flag this chapter for re-synthesis
```

A commit bump that touches 200 files (because sidecar `ingestion_date_last` fields were updated on a routine check) but only has real normalization changes in 3 of them results in exactly the chapters referencing those 3 documents being flagged. Everything else is untouched. This keeps re-synthesis proportional to actual change, not to ingestion activity.

The same check catches re-normalization events: if a document is re-normalized with a better model (content unchanged, but `normalization_date` and `normalization_model` updated), the compendium correctly flags that chapter for re-synthesis from the improved material.

**Build-time validation:** The `documents` list enables a CI check that verifies every cited document ID actually resolves to a real file in the resolved corpora. This catches broken references when documents are reorganized or when a pinned commit is bumped and document IDs have changed.

**Model audit trail:** Between the `normalization_model` on document files and `synthesis_model` on compendium pages, the full model provenance chain is captured. If a model is found to produce problematic output, you can query across both layers to identify every artifact it touched and prioritize re-processing.

---

## 8. Hosting & Distribution

### 8.1 Architecture

The compendium sites are hosted on an external Caddy server (`ref.example.org`) that is independent of the home infrastructure. This provides:

> **Domain naming:** `ref.example.org` hosts published compendiums — the synthesized reference works that agents and humans browse. `corpus.example.org` hosts corpus books — browsable mdbook references built from the normalized documents in each corpus (see section 4).

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
├── commodore-ve/        # mdBook build output
├── dune/                # mdBook build output
├── economics/           # mdBook build output
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
mdBook builds the manuscript/ directory
        ↓
Build artifacts (book/ directory) are deployed to Caddy server
        ↓
Live at ref.example.org/{domain}/ within seconds
```

### 9.2 Deployment Mechanism

The Caddy server accepts deployments via one of:

- **SSH/SCP push:** The Forgejo Actions runner pushes build artifacts directly to `/srv/ref/{domain}/` on the Caddy VPS via SSH with a deploy key.
- **Webhook receiver:** A small receiver script on the Caddy box accepts a tarball via HTTP POST with a shared secret, unpacks it to the target directory.

### 9.3 Workflow Template

A standardized workflow file that works for any compendium repository:

```yaml
# .forgejo/workflows/deploy.yml
name: Build and Deploy Compendium
on:
  push:
    branches: [main]
    paths:
      - 'manuscript/**'
      - 'book.toml'
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
      - name: Install mdBook
        run: |
          # install or use cached mdBook binary
      - name: Build
        run: mdbook build
      - name: Deploy
        run: |
          rsync -avz --delete book/ deploy@caddy-vps:/srv/ref/${GITHUB_REPOSITORY##*/}/
```

The `resolve.sh` script (see section 6.2) clones each declared corpus at its pinned commit with sparse checkout, pulling only `manuscript/` and `{corpus_id}.toml`. This keeps CI fast even as corpus repos grow large with source material.

### 9.4 Corpus Book Deployment

Corpus repositories have their own CI/CD workflow that builds the corpus book and deploys it to `corpus.example.org`. This workflow is simpler than the compendium workflow because there are no dependencies to resolve:

```yaml
# .forgejo/workflows/deploy-corpus.yml
name: Build and Deploy Corpus Book
on:
  push:
    branches: [main]
    paths:
      - 'manuscript/**'
      - 'book.toml'

jobs:
  deploy:
    runs-on: [self-hosted]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - name: Build
        run: mdbook build
      - name: Deploy
        run: |
          rsync -avz --delete .build/ deploy@caddy-vps:/srv/corpus/${GITHUB_REPOSITORY##*/}/
```

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

Each domain has a **single bespoke agent** — a dedicated AI assistant that is an expert in that domain and nothing else. There is no domain router and no shared context between domains. When you need automotive expertise, you invoke the automotive agent. When you need Dune lore, you invoke the Dune agent. (Pipeline agents — the ingestor, normalizer, and Curator described in section 12 — are internal corpus maintenance tools, not domain-facing agents.)

This simplicity is deliberate:

- The user always knows which expert they need
- Each agent's system prompt is fully tailored to its domain
- No prompt budget is wasted on routing logic or domain detection
- Each agent can have domain-specific personality, terminology, and reasoning patterns

### 10.2 Agent Configuration

Each agent is configured as a **skill** (for Claude Code / claude.ai) or equivalent construct for other platforms. The agent's configuration includes:

- **System prompt:** Domain-specific persona, expertise description, reasoning instructions, and the compendium's `SUMMARY.md` content as its navigation map.
- **Compendium URL:** The base URL for fetching compendium pages and the search index (e.g., `https://ref.example.org/commodore-ve/`).
- **Access credentials:** The agent's basic auth credentials for the compendium site.
- **Domain taxonomy:** Key concepts, terminology, and the structure of the domain to guide query decomposition.

### 10.3 Agent Behavior Model

When the agent receives a question, it follows this process:

1. **Understand the query.** Parse the question to identify which systems, symptoms, concepts, or topics are involved.
2. **Navigate the compendium.** Using the `SUMMARY.md` table of contents (already in context), identify which chapter(s) and section(s) are relevant. If the query doesn't map cleanly to the TOC structure, query the `searchindex.json` for relevant terms to discover applicable sections.
3. **Fetch relevant sections.** Retrieve the specific markdown pages from the compendium site via HTTP GET. Only fetch what's needed — not the entire compendium.
4. **Synthesize a response.** Answer the question based on the retrieved compendium content, citing specific documents where the compendium provides them.
5. **Flag coverage gaps.** If the compendium doesn't cover the topic well, tell the user explicitly rather than speculating.

### 10.4 Example: Automotive Agent

```
User: "My car is making a clunking sound when I turn at low speed,
       especially in parking lots."

Agent thinking:
  - Symptoms: clunk, low speed, turning
  - SUMMARY.md → Suspension → CV joints, wheel bearings, sway bar links
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

### 10.5 Example: Fiction Agent

```
User: "How does the Bene Gesserit breeding program connect to
       Paul's prescience?"

Agent thinking:
  - Topics: Bene Gesserit, breeding program, Kwisatz Haderach,
    prescience, Paul Atreides
  - SUMMARY.md → Factions → Bene Gesserit → Breeding Program
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

## 11. Retrieval Strategy

### 11.1 Primary Method — TOC-Based Navigation

The agent's primary retrieval mechanism is structural navigation using the compendium's table of contents. The `SUMMARY.md` is loaded into the agent's context as part of its system prompt. This gives the agent a complete map of what knowledge exists and where it lives.

This is analogous to how a knowledgeable human uses a reference book: they already know the structure, they go to the right chapter, and they read the relevant section. The agent does the same via HTTP fetches of specific pages.

**Advantages:**

- No embedding infrastructure required
- No vector database to maintain
- Retrieval is deterministic and explainable ("I looked in chapter 4.1")
- Works with the same artifact the human browses
- Updates are instant — new content appears as soon as it's deployed

### 11.2 Search Index Lookup

mdBook generates a `searchindex.json` file at build time as part of its static output. This is the same index that powers the browser-side search UI — a full-text tokenized index of every page in the compendium. The agent can fetch and query this index directly via HTTP, bypassing the browser UI entirely.

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

**Usage pattern:** The agent fetches `ref.example.org/{domain}/searchindex.json` once per session, queries it locally for relevant terms, then uses the results to identify which pages to fetch in full. For very large compendia where the search index itself is too large to hold in context, a lightweight wrapper endpoint could accept a query and return just the top N results with paths and snippets.

The search index and SUMMARY.md navigation complement each other: the TOC is best for "I know which system this is about," while the search index is best for "I have a symptom or keyword and need to find where it's discussed."

### 11.3 Fallback — Vector Search (Deferred)

Semantic vector search is **not implemented initially** but the architecture accommodates it if needed. The trigger for adding it would be repeated instances where the agent cannot find relevant content through TOC navigation or the search index because the user's query language doesn't match any terminology present in the compendium.

If implemented, it would be a lightweight vector store (e.g., Qdrant in Docker) with embeddings over the compendium's markdown chunks, used only when TOC/search index navigation fails to identify relevant sections.

### 11.4 Forgejo API as Alternative Access Path

The Forgejo REST API provides raw file access to the compendium markdown:

```
GET /api/v1/repos/Compendium/{domain}/raw/manuscript/{path}
Authorization: token {read-only-token}
```

This serves as an alternative access path — useful for agents running in environments where fetching rendered HTML is less convenient than raw markdown (e.g., Claude Code sessions where markdown is the native format). Both access methods (hosted site and API) serve the same content from the same source of truth.

---

## 12. Pipeline Agent Architecture

### 12.1 Overview

The corpus normalization pipeline (section 3.3) is operated by specialized agents — lightweight, single-purpose AI workers that each handle one item per invocation. This section formalizes the agent pattern that has emerged from the g8board corpus implementation.

The pattern is intentionally minimal: each agent has a focused responsibility, processes exactly one item, and reports results to a coordinator. There is no inter-agent communication, no shared state beyond the filesystem, and no orchestration framework. Parallelism is managed at the coordinator level (the Curator skill or a human operator), not within the agents themselves.

This is distinct from the domain agent layer (section 10), which provides end-user knowledge retrieval. Pipeline agents are internal tools for building and maintaining corpora.

### 12.2 Ingestor Agent

The ingestor agent handles acquisition, reconciliation, and integrity verification for a single content item.

**Characteristics:**

- **Model class:** haiku (fast, cheap — no creative judgment needed)
- **Scope:** One item per invocation
- **Location:** `.claude/agents/ingestor.md` in the corpus repo
- **Tools:** Read, Bash, Glob, Grep (read-only except for Bash to run scripts)

**Responsibilities:**

1. **Acquisition.** Run the appropriate scraper or downloader to capture raw content into `.download/`.
2. **Reconciliation.** Auto-detect the subdivision from backlog metadata or content analysis, assign the next sequential document ID, move files to `sources/<slug>/{document_id}/`, run extraction to produce sidecars, create the document stub in `manuscript/<slug>/`.
3. **Integrity verification.** Verify file creation, check content completeness (page counts, post counts, post number gaps), validate sidecar frontmatter, and detect deduplication issues.
4. **Structured reporting.** Report results back to the coordinator with success/failure status, assigned document ID, file counts, and any integrity warnings.

The ingestor agent does not make decisions about what to ingest or which subdivision to target — it receives these instructions from the coordinator. It is a reliable executor, not a decision maker.

### 12.3 Normalizer Agent

The normalizer agent transforms extraction sidecars into fully spec-compliant corpus documents.

**Characteristics:**

- **Model class:** sonnet (creative judgment required for descriptions, credibility assessment, issue identification)
- **Scope:** One document per invocation
- **Location:** `.claude/agents/normalizer.md` in the corpus repo
- **Tools:** Read, Write, Edit, Bash, Glob, Grep

**Responsibilities:**

1. **Read sidecars.** Load all extraction sidecars from `sources/<slug>/{document_id}/` to understand the raw content.
2. **Generate LLM-dependent frontmatter.** Produce the `description`, `credibility_tier`, `relations`, and `issues` fields that require content understanding and domain judgment.
3. **Assemble the document.** Combine the generated frontmatter with the extracted content body into the final normalized markdown, replacing the stub created at reconciliation.
4. **Set status.** Update `status` from `pending_normalization` to `normalized`.
5. **Self-verify.** Validate the output against the frontmatter schema, check for broken asset references, and verify the `sources` array matches the sidecars on disk.

The normalizer agent receives corpus context (`{corpus_id}.toml`, the frontmatter schema, content-type-specific guidance) and produces a single output file. Its system prompt is corpus-specific, living in the corpus repo alongside the agent definition.

### 12.4 The Curator

The Curator is an autonomous corpus management skill that orchestrates pipeline operations. Unlike the ingestor and normalizer agents (which are single-purpose workers), the Curator operates at a higher level — assessing corpus state, prioritizing work, and dispatching agents.

**Characteristics:**

- **Type:** Claude Code skill (`.claude/skills/`)
- **Operating loop:** Assess → Prioritize → Propose → Execute → Report
- **Dispatches:** Ingestor and normalizer agents via the Task tool, parallelizing multiple invocations

**Operating loop:**

1. **Assess.** Read `backlog.toml`, scan `manuscript/` for stubs (`status: pending_normalization`), check `sources/` for integrity, review corpus health metrics.
2. **Prioritize.** Apply a decision framework: critical compendium blockers first, then high-priority backlog items, then normalization of existing stubs, then low-priority discovery.
3. **Propose.** Present the prioritized work plan to the human operator for approval.
4. **Execute.** Spawn ingestor agents (for acquisition + reconciliation) and normalizer agents (for pending stubs), managing parallelism by launching multiple agents concurrently.
5. **Report.** Summarize results — documents ingested, documents normalized, issues encountered, updated corpus health metrics.

**Reference files.** The Curator's skill definition references corpus-specific configuration: the `{corpus_id}.toml` schema, the pipeline workflow, the frontmatter schema, and a self-improvement playbook that captures lessons learned from previous runs. These reference files live in the corpus repo and evolve with the corpus.

### 12.5 Parallelism Model

Parallelism is managed at the coordinator level, not within agents:

- The **Curator** (or a human operator) decides how many agents to run concurrently based on available resources and rate limits.
- Each **ingestor agent** processes one item. The coordinator spawns N ingestor agents in parallel for N items.
- Each **normalizer agent** processes one document. The coordinator spawns N normalizer agents in parallel for N documents.
- Agents do not communicate with each other. They read from and write to the filesystem, and the coordinator sequences work to avoid conflicts (e.g., not normalizing a document that is still being ingested).

This model avoids the complexity of inter-agent coordination while still enabling high throughput. A typical Curator session might spawn 5 ingestor agents in parallel, wait for completion, then spawn 5 normalizer agents for the newly reconciled documents.

### 12.6 Generality

The pipeline agent pattern is not specific to g8board or forum content. It applies to any corpus:

- The **ingestor agent** is parameterized by the acquisition script and reconciliation logic, which are corpus-specific.
- The **normalizer agent** is parameterized by the corpus's frontmatter schema and content-type guidance, which vary by corpus.
- The **Curator** is parameterized by the corpus's backlog format, subdivision structure, and priority framework.

Each corpus repo contains its own agent definitions (`.claude/agents/`) and Curator skill (`.claude/skills/`), configured for that corpus's specific needs. The pattern is the same; the configuration differs.

---

## 13. Scaling & Reuse

### 13.1 Adding a New Corpus

1. Create a new repository under the Corpus organization
2. Add `{corpus_id}.toml` with corpus metadata, origin configs, `[[subdivision]]` entries, and reingest configuration
3. Add `backlog.toml` and populate with known pending entries
4. Create the `manuscript/` directory with `SUMMARY.md`, `README.md`, and per-subdivision slug directories (each with its own `README.md`)
5. Create the `sources/` directory with matching subdivision slug directories
6. Add `book.toml` with `src = "manuscript"` and `[preprocessor.frontmatter-strip]` (see section 4.2)
7. Add `.download/` to `.gitignore`
8. Build or configure the acquisition pipeline appropriate to the content type
9. Build or configure the extraction pipeline — content-type-specific scripts that produce extraction sidecars (see section 3.3.3). For simple text content, a passthrough extractor is sufficient
10. Create agent definitions in `.claude/agents/` (ingestor and normalizer — see section 12) parameterized for this corpus
11. Optionally create a Curator skill in `.claude/skills/` for autonomous corpus management
12. Begin processing source material through the four-phase pipeline: acquire → reconcile → extract → normalize (see section 3.3)
13. The corpus is discoverable — its `{corpus_id}.toml` tiered summaries are available via the Forgejo API for any compendium to find (see section 5)

### 13.2 Adding a New Compendium

1. Create a new repository under the Compendium organization
2. Discover relevant corpora via API-driven progressive disclosure (see section 5.4)
3. Declare corpus dependencies in `compendium.toml` with pinned commits
4. Write the synthesis system prompt with domain knowledge, scope boundaries, and key relationships
5. Create `resolve.sh` to clone corpora at pinned commits with sparse checkout (copy from template)
6. Add `corpora/` to `.gitignore`
7. Define the domain taxonomy — the chapter structure
8. Establish the standard manuscript directory structure
9. Begin the synthesis process
10. Add the Forgejo Actions deploy workflow (copy from template)
11. Create the agent skill with domain-specific system prompt and SUMMARY.md
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
`document_id`, `title`, `description`, `credibility_tier`, `normalization_confidence`, `normalization_model`, `normalization_date`, `status`, `sources[]`

**Universal optional** (present when applicable):
`relations`, `issues`

**Sources entry:** `source_id`, `origin_url` or `original_filename`

**Sidecar fields** (section 3.3.3): core fields (`document_id`, `sequence`, `content_type`, `origin`, `original_url`, `original_filename`, `capture_date`, `ingestion_date_last`, `content_changed_last`, `author`, `date_published`, `volatility`, `extraction_method`, `extraction_tool`, `extraction_date`, `assets`) plus extended schemas by `content_type`:

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
│  │   ├── backlog.toml              │   ├── manuscript/         │
│  │   ├── book.toml                 │   ├── compendium.toml     │
│  │   ├── manuscript/               │   └── book.toml           │
│  │   ├── sources/                  ├── dune/                   │
│  │   ├── .download/ (gitignored)   ├── economics/              │
│  │   └── .claude/agents/           └── ...                     │
│  ├── frank-herbert/                                            │
│  └── ...                                                       │
│                                                                │
│  example-org Organization (System Infrastructure)                │
│  └── athenaeum/                    # spec, tooling             │
│                                                                │
│  Forgejo Actions Runner                                        │
│  ├── corpus: on push → mdbook build → deploy to corpus.rahn   │
│  └── compendium: on push → resolve → mdbook build → deploy    │
└───────────────────────┬────────────────────────────────────────┘
                        │ rsync / scp / webhook
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                  Caddy VPS (External)                          │
│                                                                │
│  ref.example.org (compendiums)                                 │
│  ├── basicauth (steven, agent)                                 │
│  ├── /srv/ref/commodore-ve/    ← compendium mdBook output   │
│  ├── /srv/ref/dune/            ← compendium mdBook output   │
│  └── ...                                                       │
│                                                                │
│  corpus.example.org (corpus books)                             │
│  ├── basicauth (steven, agent)                                 │
│  ├── /srv/corpus/g8board/      ← corpus mdBook output       │
│  ├── /srv/corpus/frank-herbert/← corpus mdBook output       │
│  └── ...                                                       │
└───────────────────────┬────────────────────────────────────────┘
                        │ HTTPS (basic auth)
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                       Consumers                                │
│                                                                │
│  Steven (browser)                                              │
│  ├── Browses compendiums for domain knowledge                  │
│  └── Browses corpus books for normalization review             │
│                                                                │
│  Domain Agent (Claude skill / Claude Code)                     │
│  ├── SUMMARY.md in system prompt context                       │
│  ├── searchindex.json for full-text keyword lookup             │
│  ├── Fetches specific pages via HTTP on demand                 │
│  └── Responds with source-grounded answers                     │
│                                                                │
│  Pipeline Agents (.claude/agents/)                             │
│  ├── Ingestor: acquire + reconcile + verify (haiku)            │
│  ├── Normalizer: sidecars → normalized doc (sonnet)            │
│  └── Curator: autonomous corpus management (.claude/skills/)   │
└──────────────────────────────────────────────────────────────┘
```

### 14.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Source of truth | Forgejo (git) | Version control, API access, Actions CI |
| Source organization | Forgejo org (Corpus) | One repo per corpus, with origins and subdivisions declared in `{corpus_id}.toml` |
| Corpus discovery | Forgejo API + `{corpus_id}.toml` | Tiered summaries fetched on demand, no separate registry repo |
| Corpus format | Markdown + mdBook | Browsable corpus books at `corpus.example.org`, frontmatter stripped via `mdbook-frontmatter` |
| Compendium format | Markdown + mdBook | Human-readable source, clean output, built-in search |
| Source linkage | Declared dependencies in `compendium.toml` | Pin corpora to commits, resolve at build time with sparse checkout |
| Hosting | Caddy on external VPS | Simple, reliable, automatic HTTPS, basic auth |
| CI/CD | Forgejo Actions | Integrated with repos, self-hosted runner (corpus + compendium workflows) |
| Domain agents | Claude (skill / Code) | Primary AI interface for end-user knowledge retrieval |
| Pipeline agents | Claude Code agents (`.claude/agents/`) | Ingestor (haiku), normalizer (sonnet), Curator (skill) for corpus maintenance |
| Retrieval | TOC navigation + searchindex.json + HTTP fetch | No additional infrastructure, deterministic, explainable |

### 14.3 What Is Intentionally Not Included

| Component | Status | Trigger to Add |
|-----------|--------|----------------|
| Vector database | Deferred | Agent repeatedly fails to find content via TOC/search index |
| Knowledge graph | Deferred | Multi-hop relationship queries become common |
| Domain router | Not planned | Only needed if agents are invoked implicitly |
| Cross-domain linking | Not planned | Domains are intentionally isolated |
| General-purpose orchestration framework | Not planned | Pipeline agents use lightweight coordination via Curator skill (section 12), not a framework |
| Per-compendium auth gateway | Deferred | Needed when sharing specific compendiums with others |

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

**Partially realized in v3.0.** The Curator skill (section 12.4) implements an assess → prioritize → propose → execute → report loop with a self-improvement playbook. Coverage gap signals from domain agents can feed into the Curator's prioritization framework. The remaining future work is formalizing the feedback path from domain agents to the Curator.

### B.4 Multi-Format Export

The same compendium markdown could be exported to additional formats: PDF for offline reading, EPUB for e-readers, or structured JSON for programmatic access. These are build-step additions that don't affect the source material.

### B.5 Corpus Ingestion Automation

**Realized in v3.0.** The pipeline agent architecture (section 12) formalizes corpus ingestion automation. The Curator skill autonomously assesses, prioritizes, and dispatches ingestor and normalizer agents. Remaining future work: scheduled triggers (cron-based scraper runs, RSS monitors) and fully unattended operation without human approval of the Curator's proposals.
