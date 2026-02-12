---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 2.0
status: draft
author: Steven Rahn
date_created: 2026-02-08
date_modified: 2026-02-12
addenda_incorporated:
  - ATH-ARCH-A001
  - ATH-ARCH-A002
changelog:
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

The architecture intentionally avoids complexity where simplicity suffices. There is no vector database, no knowledge graph, no multi-agent orchestration, and no domain router. These are not rejected — they are deferred until a concrete need for them is demonstrated. The system is designed so that any of these can be added later without rearchitecting what exists.

---

## 2. Architecture Overview

Athenaeum is organized into three conceptual layers. Raw sources enter the **Corpus** layer, where they are ingested, extracted, and normalized into markdown with rich summaries. Each corpus carries tiered summaries in its `{corpus_id}.toml` that enable **corpus discovery** via progressive disclosure — compendiums can efficiently discover which corpora are relevant to their domain by fetching these summaries from the Forgejo API without cloning every corpus. The **Compendium** layer declares corpus dependencies, uses an LLM to select relevant documents based on summaries, and synthesizes the selected material into domain-specific reference works guided by a compendium-specific system prompt.

**Terminology:** *Corpus* (plural: *corpora*) means "a body of collected texts" — this is where raw source material lives. *Compendium* means "a comprehensive collection of concise information" — this is where synthesized reference works live. *Manuscript* refers to the pre-rendered markdown that gets compiled into the published compendium.

### 2.1 Corpus Layer

A corpus is a self-contained collection of normalized material from a single source of information — one voice. It represents everything captured from that source, processed through a three-phase pipeline — ingestion, extraction, and normalization — into markdown files with structured frontmatter. Each file carries a summary that captures what the document contains and why it's useful.

A corpus can have multiple **origins** — distinct raw content sources that feed into it. A forum corpus has one origin (the forum itself). A manufacturer corpus might have several: a PDF archive of service manuals, a web database of technical bulletins, and a press release feed. Each origin has its own ingestion method and reingest configuration, declared in the corpus's registration file.

Key properties:

- **One voice, one corpus.** A forum is a corpus. An author is a corpus. A YouTube channel is a corpus. A manufacturer's entire catalog of publications is a corpus. The organizing principle is *who produced the information*, not what it's about.
- **Multiple origins, one corpus.** A single entity may publish through multiple channels and formats. These are different origins within the same corpus — the corpus groups them by voice, and each origin's ingestion pipeline handles format differences.
- **No editorial filtering.** A corpus contains everything from its source, summarized but unfiltered. Topical selection happens downstream at the compendium layer.
- **Summary-driven discovery.** Every normalized file carries a summary that enables downstream selection without reading the full content. An LLM reading the summary can determine whether the document is relevant to a given domain.

The range of corpora is deliberately broad: `g8board` (an automotive forum), `frank-herbert` (an author's collected works), `gm` (a manufacturer's manuals, bulletins, and press releases), `engineering-explained` (a YouTube channel's transcripts), `marxists-org` (a text archive). Each is independent and self-contained.

### 2.2 Corpus Discovery

Corpus discovery is API-driven — each corpus's `{corpus_id}.toml` carries tiered summaries that describe the corpus, and these are fetched on demand from the Forgejo API without cloning any repos. There is no separate registry repository; the corpora describe themselves.

Each corpus carries three summary tiers in its `{corpus_id}.toml`:

1. **Tier 1** — a single sentence. Enough to include or exclude at a glance.
2. **Tier 2** — a concise paragraph. Enough to confirm relevance and understand scope.
3. **Tier 3** — a comprehensive description. Full detail on what the corpus contains, its document count, and its coverage.

At compendium setup time, tooling lists all repos in the Corpus organization via the Forgejo API, fetches each `{corpus_id}.toml`, and extracts the summary tiers. An LLM reads tier 1 summaries for all corpora to identify candidates, reads tier 2 for confirmation, and consults tier 3 only when needed. This avoids the cost of cloning and scanning corpora that turn out to be irrelevant. See section 4 for the discovery format and progressive disclosure process.

### 2.3 Compendium Layer

A compendium defines a knowledge domain and synthesizes a structured reference work from corpus material. It does not store source content — it declares which corpora it draws from, selects relevant documents using an LLM that reads document summaries, and synthesizes a coherent, browsable reference from the selected material.

Key properties:

- **Domain declaration.** A compendium defines its scope by listing corpus dependencies and providing a synthesis system prompt that encodes domain knowledge.
- **Shared corpora, different selections.** Multiple compendiums can draw from the same corpus. An `economics` compendium and a `socialism` compendium might both depend on `marxists-org`, with their respective system prompts guiding the LLM to select different documents.
- **System prompt as domain bootstrap.** The compendium's system prompt provides the LLM with domain-specific context: key relationships, disambiguation guidance, scope boundaries. This is iterable — when synthesis produces gaps or errors, the system prompt is refined.
- **Synthesis output.** Selected documents are synthesized into manuscripts — structured, cross-referenced markdown that gets compiled into a browsable, textbook-like reference.

For example, a `dune` compendium declares dependencies on `frank-herbert`, `brian-herbert`, `denis-villeneuve`, and `scifi-channel-dune`. Its system prompt defines the Dune franchise scope and key relationships. During synthesis, the LLM reads document summaries from each corpus — Frank Herbert's *Dune* and *Dune Messiah* are selected because their summaries clearly relate to the Dune universe, while *Man of Two Worlds* (a comedy collaboration) and *The Dragon in the Sea* (a submarine thriller) are skipped. From `denis-villeneuve`, the Dune screenplays are selected while *Blade Runner 2049* and *Arrival* are not. The LLM's semantic understanding, guided by the system prompt, makes these selections — no tag matching required.

See section 5 for the detailed compendium structure and synthesis process.

### 2.4 Data Flow

The full pipeline from source to published reference:

```
  Raw Source (PDF, forum thread, transcript, ...)
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 1: Ingestion                         │
  │  acquire raw content                        │  script-driven or manual
  │  → ingested/{document_id}/                  │
  │    {document_id}_XXX.{ext}                  │
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 2: Extraction                        │
  │  programmatic transform                     │  deterministic, no LLM
  │  → ingested/{document_id}/                  │
  │    {document_id}_XXX.extract.md (sidecars)  │
  │  → assets/{document_id}/                    │
  └─────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  Phase 3: Normalization                     │
  │  LLM-driven interpretation                  │  summaries, credibility,
  │  → documents/{document_id}.md               │  relations, frontmatter
  └─────────────────────────────────────────────┘
       │
       │  normalized markdown with summary
       ▼
  ┌─────────────────────────────────────────────┐
  │  Corpus Discovery                           │
  │  {corpus_id}.toml summaries                 │  ◄── fetched via Forgejo API
  │  from each corpus repo                      │
  └─────────────────────────────────────────────┘
       │
       │  progressive disclosure: tier1 → tier2 → tier3
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

Concretely: Frank Herbert's *Dune* enters the `frank-herbert` corpus as a raw epub file (ingestion). Extraction produces a markdown sidecar with chapter text and metadata alongside the raw file. The normalization agent then interprets the sidecar into the final normalized markdown with a summary describing it as a science fiction novel about ecology, politics, and prescience on the desert planet Arrakis. The `frank-herbert.toml` captures the corpus scope across its tiered summaries. When the `dune` compendium is set up, tier 1 summaries fetched from all corpora immediately identify `frank-herbert` as relevant. At synthesis time, the LLM reads individual document summaries within the cloned corpus and — guided by the compendium's system prompt — selects *Dune* and *Dune Messiah* while skipping *Man of Two Worlds*. The same `frank-herbert` corpus could simultaneously feed a hypothetical `sci-fi-comedy` compendium whose system prompt would guide selection of *Man of Two Worlds* instead.

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

**Before (incorrect — split by document type):**
```
corpus/gm-service-manuals/
corpus/gm-bulletins/
corpus/gm-press-releases/
```

**After (correct — one entity, one corpus):**
```
corpus/gm/
```

Within the `gm` corpus, individual documents use `content_type` to distinguish `service_manual` from `technical_bulletin` from `product_documentation` from `article`. Credibility tiers handle trust differences between a factory service manual (`authoritative`) and a marketing brochure (`expert` or lower). The corpus only answers: **who said this.**

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

#### Updated Examples

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

Each corpus repo contains a registration file (`{corpus_id}.toml`) that declares metadata about the corpus and its origins. The filename matches the `corpus_id` by convention, enabling discovery tooling to cache all registration files in a flat directory without name collisions:

```toml
# g8board.toml
corpus_id = "g8board"
corpus_name = "G8Board.com"
corpus_prefix = "G8BD"

# tiered summaries for corpus discovery (see section 4)
summary_tier1 = "G8Board.com automotive forum — Pontiac G8 community"

summary_tier2 = """
Forum threads from G8Board.com, the primary English-language \
community for the 2008-2009 Pontiac G8. Covers diagnostics, \
repairs, modifications, and ownership experiences for the G8 GT \
(L76 6.0L V8), G8 GXP (LS3 6.2L V8), and base V6 models."""

summary_tier3 = """
Comprehensive archive of G8Board.com forum threads normalized from \
HTML captures. The G8 is a rebadged Holden VE Commodore built in \
Elizabeth, South Australia.

Coverage includes: suspension and wheel bearing issues, engine and \
transmission diagnostics, AFM/DoD cylinder deactivation problems, \
brake upgrades, exhaust and intake modifications, electrical \
troubleshooting, and general ownership experiences.

High-value threads include community-validated diagnostic \
walkthroughs, long-running troubleshooting threads with multiple \
confirming reports, and DIY guides with detailed procedures.

~2,400 normalized documents. Community-validated and anecdotal \
credibility tiers."""

[[origins]]
origin_id = "forum"
origin_type = "forum"
origin_url = "https://www.g8board.com"
ingestion_method = "web_scraper"
active = true

[origins.reingest]
default_volatility = "unlikely"       # most old threads are stable
active_threshold_days = 7             # check 'active' documents weekly
periodic_threshold_days = 90          # check 'periodic' documents quarterly
unlikely_threshold_days = 365         # check 'unlikely' documents annually
# 'static' documents are never re-checked
```

For a multi-document-type entity (see section 3.1), multiple origins within the corpus handle the different ingestion paths:

```toml
# gm.toml
corpus_id = "gm"
corpus_name = "General Motors"
corpus_prefix = "GMOT"

summary_tier1 = "General Motors official documentation — service manuals, TSBs, recalls"

summary_tier2 = """
Official publications from General Motors covering service manuals, \
technical service bulletins, recall notices, dealer bulletins, press \
releases, and brochures. Primarily North American market vehicles."""

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
```

Each `[[origins]]` entry represents a distinct raw content source within the corpus. A single-origin corpus (like g8board) has one `[[origins]]` entry. A multi-origin corpus (like GM) has one entry per ingestion path. The `origin_type`, `origin_url`, `ingestion_method`, and `active` fields live at the origin level because they describe the raw content source, not the corpus as a whole.

Each origin's `[origins.reingest]` section defines the default volatility for documents from that origin and the thresholds for re-ingestion priority. Individual documents can override `default_volatility` via the `volatility` field in their frontmatter. The ingestion scanner compares each document's `ingestion_date_last` against the appropriate threshold to generate a re-ingestion priority queue. If a document spans multiple origins, set `volatility` explicitly in the document frontmatter.

The `corpus_prefix` ensures globally unique document IDs across all corpora. Prefixes are 4 uppercase letters (allowing for 456,976 unique corpus prefixes). Every normalized file in this repo will have a document ID like `G8BD.0001`, `G8BD.0042`, etc. The numeric portion is zero-padded to 4 digits, supporting up to 9,999 documents per corpus. When a compendium cites `G8BD.0042`, it unambiguously resolves to a specific file in a specific corpus repo.

#### 3.2.1 Corpus Repository Layout

Each corpus repo has a clean top-level structure:

```
Corpus/g8board/
├── g8board.toml                        # corpus registration + origin configs
├── backlog.toml                        # non-captured document tracking
├── documents/                          # one markdown file per captured document
│   ├── G8BD.0001.md
│   ├── G8BD.0002.md
│   └── G8BD.0042.md
├── assets/                             # embedded content referenced by document files
│   ├── G8BD.0001/
│   │   ├── bearing-removal.jpg
│   │   └── torque-sequence.png
│   └── G8BD.0042/
│       └── hub-assembly-diagram.png
└── ingested/                           # raw files + extraction sidecars, per document
    ├── G8BD.0001/
    │   ├── G8BD.0001_001.html
    │   └── G8BD.0001_001.extract.md
    └── G8BD.0042/
        ├── G8BD.0042_001.html
        ├── G8BD.0042_001.extract.md
        ├── G8BD.0042_002.html          # e.g., wayback capture
        └── G8BD.0042_002.extract.md
```

**Directory purposes:**

- **`documents/`** — One markdown file per document. Files only exist here when there is actual normalized content. No stubs, no placeholders.
- **`assets/`** — Images, diagrams, and other embedded content referenced by document files. Organized as one subdirectory per document ID (only present when that document has assets). Assets are produced during extraction — the normalization agent references existing assets via the `assets` array in the extraction sidecar.
- **`ingested/`** — Raw files and extraction sidecars, organized as one subdirectory per document ID. Raw files use standardized names (`{document_id}_XXX.{ext}` — three-digit sequence, original extension preserved). Each raw file is paired with an extraction sidecar (`{document_id}_XXX.extract.md`) that contains the programmatically extracted content as markdown with YAML frontmatter.

**The many-to-one rule:** A single document can have multiple raw files in `ingested/{document_id}/` — the same content in different formats, multiple captures from different dates, or complementary representations (a transcript plus screenshots). Each raw file has its own extraction sidecar. Regardless of how many ingested files exist for a document, normalization always produces exactly **one markdown file** in `documents/` per document ID.

#### 3.2.2 Document Backlog

Captured documents are self-describing — they exist as files in `documents/` with complete frontmatter. The `backlog.toml` file tracks documents that are *not yet captured*: known to exist, but pending ingestion, explicitly deferred, or currently unavailable.

```toml
# backlog.toml — tracks known documents not yet captured

[[documents]]
document_id = "G8BD.0200"
title = "Complete AFM delete guide with dyno results"
status = "pending"
priority = "high"
discovered_url = "https://www.g8board.com/forum/thread-56789"
discovered_date = "2026-02-08"

[[documents]]
document_id = "G8BD.0201"
title = "Headlight condensation fix - bake and reseal"
status = "pending"
priority = "medium"
discovered_url = "https://www.g8board.com/forum/thread-56800"
discovered_date = "2026-02-08"
notes = "Includes detailed photos of the baking process"

[[documents]]
document_id = "G8BD.0202"
title = "G8 production numbers by color and trim"
status = "deferred"
notes = "Interesting but not relevant to any current compendium"
```

For an author corpus, the backlog tracks works not yet acquired:

```toml
# backlog.toml for frank-herbert

[[documents]]
document_id = "FHBT.0003"
title = "Children of Dune"
status = "pending"
priority = "high"
notes = "Need to acquire epub"

[[documents]]
document_id = "FHBT.0011"
title = "The White Plague"
status = "deferred"
notes = "Out of print, difficult to acquire"

[[documents]]
document_id = "FHBT.0012"
title = "Man of Two Worlds"
status = "unavailable"
notes = "Co-authored with Bill Ransom, no digital edition found"
```

The `content_type` field in each document file's frontmatter distinguishes what kind of content it is (`service_manual`, `technical_bulletin`, `article`, `product_documentation`). The backlog and corpus just track that it all comes from the same entity.

**Status values** (backlog only — captured documents exist as files, not backlog entries):

| Status | Meaning |
|--------|---------|
| `pending` | Known to exist and belongs in this corpus. Queued for future ingestion |
| `deferred` | Known to exist, explicitly deprioritized. Won't be ingested soon but tracked for completeness |
| `unavailable` | Known to exist but currently impossible to acquire (dead link, out of print, behind paywall) |

**Priority values** (only applicable to `pending` documents):

| Priority | Meaning |
|----------|---------|
| `critical` | Blocking a compendium — needed for synthesis now |
| `high` | Actively wanted for a current compendium |
| `medium` | Would improve coverage but not urgent |
| `low` | Known to exist, no current compendium needs it |

**Backlog-specific optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `discovered_url` | string | Where this document was found (for web-based origins) |
| `discovered_date` | date | When this document was discovered |
| `notes` | string | Freeform notes about this document or why it's in a particular status |

**Document IDs are reserved at discovery time.** When you identify a thread, article, or work that belongs in this corpus, it gets a backlog entry and a document ID immediately — even before ingestion. This means the ID is stable and can be referenced in `relations` by other documents before the content is captured. Gaps in numbering (from documents that remain `pending` indefinitely) are expected and harmless.

**The backlog is not for cross-corpus references.** If a g8board post mentions a GM TSB, that reference is recorded as an `unresolved` relation in the document's frontmatter — not as a backlog entry in g8board. The TSB belongs in the `gm` corpus and would be registered there.

**Build-time validation:**

- Every file in `documents/` must have valid frontmatter
- Every document_id in `backlog.toml` must NOT have a file in `documents/`
- No overlapping IDs between `documents/` and `backlog.toml`

**Ingestion backlog reporting:**

```
Ingestion Backlog:
  Corpus/frank-herbert:     6 captured, 8 pending (2 high, 3 medium, 3 low), 2 deferred, 1 unavailable
  Corpus/g8board:          42 captured, 156 pending (12 critical, 45 high, 99 medium), 3 deferred
  Corpus/gm:               75 captured, 120 pending (20 high, 60 medium, 40 low), 5 deferred
```

### 3.3 Normalized Document Format

Every normalized document file is a single markdown file with structured YAML frontmatter. The frontmatter follows a rigid schema: a set of universal fields present on every document, plus extended fields determined by the `content_type`. This consistency enables tooling to validate, query, and compare documents across any corpus.

#### 3.3.1 Universal Required Fields

Every document file must include all of these fields, no exceptions:

| Field | Type | Description |
|-------|------|-------------|
| `document_id` | string | `XXXX.####` globally unique identifier (4-letter corpus prefix + 4-digit number) |
| `title` | string | Short descriptive label for the document file (not necessarily the work's canonical title) |
| `summary` | string | One-to-three sentence description of what this document contains and why it's useful. Generated during normalization. Enables synthesis-time relevance assessment without reading the full content |
| `content_type` | enum | Declares which extended schema applies. See section 3.3.3 for valid types |
| `credibility_tier` | enum | `authoritative`, `expert`, `community_validated`, `anecdotal`, `speculative`. See section 3.4 |
| `ingestion_date_first` | date | When this document was originally captured |
| `ingestion_date_last` | date | When we last checked/re-ingested from the upstream source (same as `ingestion_date_first` on initial capture) |
| `content_changed_last` | date | When the upstream content last actually differed from what we had. Used by the ingestion layer to assess source stability |
| `normalization_confidence` | float | `0.0`–`1.0`, quality of the conversion process. See section 3.4.1 |
| `normalization_model` | string | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`) |
| `normalization_date` | date | When normalization was last performed. **This is the field the compendium layer compares against to determine if re-synthesis is needed** — it captures both content changes and re-normalization with improved models |

#### 3.3.2 Universal Optional Fields

These fields are present on most documents but legitimately absent on some:

| Field | Type | When absent |
|-------|------|-------------|
| `author` | string | The name of the identifiable person who produced this content. Reserved for real, identifiable people — anonymous forum posts and Reddit posts use the `username` extended field instead (a plain string handle, not tracked or disambiguated). Anonymous or unsigned government documents omit this field entirely. If a forum poster is later identified as a real person, the `author` field can be added alongside the `username` field |
| `date_published` | date | Undated historical texts, some web content |
| `origin_url` | string | Physical books, offline documents |
| `volatility` | enum | `static`, `unlikely`, `periodic`, `active`. Omit to inherit the default from the document's origin in `{corpus_id}.toml`. Only set per-document as an override when a document's volatility differs from the origin norm (e.g., an unusually active thread on a mostly-dormant forum). If a document spans multiple origins, set explicitly |
| `relations` | array | Omit if no explicit references to other documents. See section 3.6 |
| `issues` | array | Omit if no known quality or completeness problems. See section 3.5 |

#### 3.3.3 Extended Schemas by `content_type`

The `content_type` field determines which additional fields are required or available. This is a closed enum — adding a new type requires defining its extended schema.

##### `forum_post`

Covers: g8board, ls1tech, performanceforums, and similar threaded discussion sites.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `username` | yes | string | Exact username of the poster on the forum (plain string, not a registry term) |
| `thread_url` | yes | string | Direct link to the thread |
| `reply_count` | no | int | Number of replies — engagement signal |
| `is_solution` | no | bool | Whether this was marked or widely accepted as the answer |

##### `reddit_post`

Covers: Reddit posts and threads. Separated from `forum_post` because Reddit's voting system provides a distinct credibility signal.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `username` | yes | string | Exact Reddit username of the poster (plain string, not a registry term) |
| `subreddit` | yes | string | Which subreddit, without the r/ prefix |
| `post_url` | yes | string | Permalink to the post |
| `score` | no | int | Net upvotes — engagement and credibility signal |
| `comment_count` | no | int | Number of comments |
| `post_type` | no | enum | `discussion`, `question`, `guide`, `review` |

##### `book`

Covers: complete published works — novels, non-fiction books, collected works. **A single document is always the entire book.** In `ingested/` the book may be split across many files (chapter PDFs, an epub, a complete PDF), but normalization always produces one markdown file per work.

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
| `superseded_by` | no | string | Bulletin number if this has been replaced |

##### `video`

Covers: YouTube videos, instructional content, any video-first source. Each video is one document file containing the transcript and, where relevant, descriptions of visual content.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `duration_seconds` | yes | int | Video length |
| `has_visual_content` | yes | bool | Whether visual elements are meaningful to the content (a hands-on repair demo vs. a talking head) |
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

#### 3.3.4 Complete Example

A forum post document with all applicable fields:

```yaml
---
document_id: "G8BD.0042"
title: "DIY rear wheel bearing replacement with diagnosis walkthrough"
summary: "Detailed step-by-step guide for diagnosing and replacing rear wheel bearings on the Pontiac G8, including jacking points, torque specs, and tool list. Author reports failure at 82k miles with symptoms of humming at highway speeds progressing to grinding."
content_type: "forum_post"
credibility_tier: "community_validated"
ingestion_date_first: "2026-01-20"
ingestion_date_last: "2026-06-15"
content_changed_last: "2026-01-20"
normalization_confidence: 0.92
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: "2026-01-20"

# universal optional (author omitted — anonymous forum poster, see username below)
date_published: "2019-03-15"
origin_url: "https://www.g8board.com/forum/thread-12345"
volatility: "unlikely"
relations:
  - type: "references"
    document_id: "G8BD.0038"
  - type: "references"
    unresolved: "GM TSB #PI0597B"
issues:
  - type: "missing_media"
    severity: "major"
    description: "2 of 4 embedded images unavailable — showed bearing removal tool setup and torque sequence"
    remediation: "wayback_snapshot"
    resolved: true

# extended: forum_post
username: "TorqueDave"
thread_url: "https://www.g8board.com/forum/thread-12345"
reply_count: 47
is_solution: true
---

[normalized markdown content]
```

### 3.4 Credibility Tiers

Each document is rated for trustworthiness:

| Tier | Description | Examples |
|------|-------------|----------|
| `authoritative` | Official or primary source documentation | OEM service manual, published TSB, peer-reviewed research, original text of a novel |
| `expert` | Credentialed professional with demonstrated expertise | Professional mechanic writeup, licensed practitioner guide, scholarly analysis |
| `community_validated` | Claim independently confirmed by multiple people | Forum fix confirmed by 5+ unrelated users |
| `anecdotal` | Single person's experience, unconfirmed | One forum post describing a symptom |
| `speculative` | Theory or hypothesis without supporting evidence | "I think it might be the alternator" |

For fiction origins, `authoritative` means the primary text itself. `expert` would be published literary criticism. `community_validated` might be widely-accepted fan analysis. The tiers adapt naturally to any domain.

#### 3.4.1 Normalization Confidence

The `normalization_confidence` field (`0.0`–`1.0`) rates the quality of the conversion process itself — how accurately the raw source was captured and converted to markdown. This is distinct from credibility (trustworthiness of claims) and distinct from the summary (what it's about).

A perfectly transcribed YouTube video might have high normalization confidence but low credibility tier. A badly OCR'd service manual might have low normalization confidence but authoritative credibility.

### 3.5 Document Issues

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

#### 3.5.1 Issue Types

| Type | Description |
|------|-------------|
| `missing_media` | Images, videos, or embedded content no longer available at the original location |
| `broken_links` | Referenced URLs within the document content are dead |
| `partial_content` | Content was truncated, paywalled, or incompletely captured |
| `content_modified` | Content has been edited since original publication — original version may differ from current |
| `encoding_corruption` | Garbled text, mojibake, or mangled characters |
| `format_loss` | Tables, diagrams, code blocks, or formatting that didn't survive conversion |

#### 3.5.2 Severity Levels

| Severity | Meaning |
|----------|---------|
| `critical` | Document is essentially unusable without remediation — key content is missing or corrupted |
| `major` | Significant information loss but document is still partially useful |
| `minor` | Cosmetic or non-essential content affected |

#### 3.5.3 Remediation Actions

| Remediation | Description |
|-------------|-------------|
| `wayback_snapshot` | Retrieve an archived version from the Wayback Machine |
| `alternate_source` | Same content may be available from a different origin |
| `original_author` | Could contact the original author for missing material |
| `re_ingest` | Re-capture from origin may resolve (e.g., temporary outage, encoding fix) |
| `manual_reconstruction` | Requires human effort to reconstruct from context |
| `none` | No remediation needed or possible |

The `resolved` boolean tracks whether the issue has been addressed. The typical workflow: normalization flags dead images → issue is logged with `remediation: "wayback_snapshot"` → Wayback snapshot is retrieved and added to `ingested/{document_id}/` → document is re-normalized from improved raw material → issue is marked `resolved: true`. The issue remains in frontmatter as a historical record.

For the `content_modified` type, the remediation may involve pulling both the current version and a Wayback snapshot as separate raw files. A forum post edited to add "UPDATE: don't do this, it caused X" is more valuable with both versions visible — the normalization can reconcile them or note the differences.

Build-time scanning can surface unresolved issues as a prioritized remediation queue:

```
Unresolved Issues for Corpus/g8board:
  critical: 2 documents (both remediable via wayback_snapshot)
  major: 8 documents (5 missing_media, 3 partial_content)
  minor: 15 documents
```

### 3.6 Document Relations

Normalized documents can declare explicit relationships to other documents. These capture **intrinsic relationships** — objective facts about the document that are evident at normalization time. A forum post linked to another thread. A novel is the sequel to another novel. A revised TSB supersedes an earlier one. These are unchallengeable observations captured when the material is being read.

```yaml
relations:
  - type: "sequel_to"
    document_id: "FHBT.0001"            # Dune Messiah is a sequel to Dune
  - type: "reply_to"
    document_id: "G8BD.0038"            # this forum post replies to that thread
  - type: "adaptation_of"
    document_id: "FHBT.0001"            # Villeneuve screenplay adapts the novel
  - type: "supersedes"
    document_id: "GTSB.0004"            # revised TSB replaces an earlier one
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
| `contradicts` | Explicitly disagrees with | One forum post refuting another |

**Cross-corpus references** are particularly valuable. A g8board post may reference a GM TSB that lives in a different corpus repo. At normalization time, the referenced document's ID may not be known yet. The `unresolved` field captures the reference in human-readable form. As the corpus ecosystem grows, a periodic reconciliation pass can attempt to resolve these against all known document IDs.

**Discovered relationships** — connections identified during synthesis rather than present in the document itself ("this post describes the same failure mode as that manual section") — belong in the compendium layer, not document frontmatter. Document relations are strictly what the document itself declares or implies.

#### 3.6.1 Corpus Discovery via Relations

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

### 3.7 Exotic Origin Types

The corpus-as-repo pattern supports any content type. The only requirement is a pipeline that can ingest, extract, and normalize the content into markdown with frontmatter. The extraction phase (see section 3.8) handles format-specific programmatic transformation; the normalization phase handles LLM-driven interpretation.

**YouTube channels:** Ingestion downloads the video/audio. Extraction runs a transcription tool (e.g., Whisper) and captures frame data, producing a markdown sidecar with timestamped transcript segments and visual content metadata. The normalization agent then interprets the sidecar into final markdown with summary, credibility assessment, and structured frontmatter. Each video is one document file.

```yaml
---
document_id: "ENEX.0017"
title: "Engineering Explained — Why Direct Injection Causes Carbon Buildup"
summary: "Technical explainer covering the mechanism by which direct injection engines accumulate carbon deposits on intake valves, why port injection doesn't have this problem, and what solutions exist including walnut blasting and dual injection systems."
content_type: "video"
credibility_tier: "expert"
ingestion_date_first: "2026-02-01"
ingestion_date_last: "2026-02-01"
content_changed_last: "2026-02-01"
normalization_confidence: 0.85
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: "2026-02-01"

# universal optional
author: "Engineering Explained"
date_published: "2021-06-14"
origin_url: "https://youtube.com/watch?v=..."
volatility: "static"

# extended: video
duration_seconds: 847
has_visual_content: true
---

[transcript with timestamps and descriptive notes for visual content]
```

**Authors (fiction):** Extraction handles format conversion (epub parsing, OCR for scanned editions). Each work is normalized into one or more document files — a short story as one file, a novel potentially split into chapters. The primary text is `authoritative` credibility. Introductions, afterwords, and interviews are tagged separately.

**Podcasts:** Similar to YouTube — extraction runs the transcription tool, normalization interprets the result. One episode per document file.

**Government / institutional sources:** Extraction handles PDF text extraction, OCR, and table recognition. The normalization agent interprets the extracted content into markdown. Each publication is one document file.

### 3.8 Normalization Pipeline

The path from raw source to normalized markdown is a three-phase pipeline. Formalizing these phases makes the pipeline reproducible, auditable, and independently improvable — you can re-normalize from improved models without re-extracting, and you can re-extract with better tools without re-downloading.

#### 3.8.1 Phase 1: Ingestion

**What:** Acquire raw content from external sources.

**How:** Script-driven or manual — web scrapers, downloaders, API clients, manual file copy.

**Output:** Raw files in `ingested/{document_id}/` with standardized names: `{document_id}_XXX.{ext}` (three-digit sequence number, original extension preserved). Multiple files per document are common (e.g., an HTML capture plus a Wayback snapshot).

Ingestion is already defined by the corpus repository structure (section 3.2.1) and the backlog tracking system (section 3.2.2). This phase simply acquires content; it performs no transformation.

#### 3.8.2 Phase 2: Extraction

**What:** Programmatic transformation of raw files into clean, structured extraction sidecars.

**How:** Content-type-specific scripts — no LLM involvement, deterministic processing only.

**Output:** One extraction sidecar per raw file (`{document_id}_XXX.extract.md`) alongside the raw file in `ingested/{document_id}/`, plus assets saved to `assets/{document_id}/`.

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
document_id: "G8BD.0042"
sequence: 1
origin: "forum"
original_url: "https://www.g8board.com/forum/thread-12345"
original_filename: "thread.html"
capture_date: "2026-01-15"
content_type_hint: "forum_post"
extraction_method: "g8board-scraper"
extraction_tool: "athenaeum-extract v0.3"
extraction_date: "2026-01-20"
assets:
  - filename: "bearing-removal.jpg"
    context: "Shows bearing removal tool setup"
  - filename: "torque-sequence.png"
    context: "Torque sequence diagram for hub assembly"
---

[extracted clean text content]
```

The sidecar frontmatter follows these conventions:

- **`document_id`** and **`sequence`** — identify which document and which raw file this sidecar corresponds to.
- **`origin`** — which origin within the corpus this raw file came from (matches an `origin_id` in `{corpus_id}.toml`).
- **`original_url`** and **`original_filename`** — provenance of the raw file before standardized naming.
- **`capture_date`** — when the raw file was acquired.
- **`content_type_hint`** — a hint, not authoritative — the normalization agent makes the final `content_type` determination.
- **`extraction_method`**, **`extraction_tool`**, **`extraction_date`** — extraction provenance, enabling targeted bulk re-extraction when tools improve.
- **`assets`** — filenames and context strings for extracted images/diagrams saved to `assets/{document_id}/`.
- **No rigid schema per content type** — the body contains extracted text structured as the extractor sees fit. Follows the spec's philosophy of leaning on LLM understanding rather than rigid schemas.

**Asset extraction.** Images, diagrams, and other embedded content are extracted during this phase and saved to `assets/{document_id}/`. The `assets` array in the sidecar frontmatter provides filenames and context strings that the normalization agent uses to produce correct relative paths and alt text in the final markdown document.

#### 3.8.3 Phase 3: Normalization

**What:** LLM-driven interpretation of extracted content into final normalized markdown with full frontmatter.

**How:** A normalization agent consuming the extraction sidecars, guided by the frontmatter schema and corpus context.

**Output:** `documents/{document_id}.md` with complete YAML frontmatter (all universal required fields, applicable optional and extended fields) and structured markdown content.

**The normalization agent receives:**

1. Extraction sidecars for the document (one or more `.extract.md` files from `ingested/{document_id}/`)
2. `{corpus_id}.toml` context (corpus metadata, origin configs, credibility defaults)
3. The frontmatter schema (universal required fields, optional fields, extended fields for the relevant content type)
4. Content-type-specific guidance (how to structure forum threads vs. book chapters vs. video transcripts)

**The normalization agent is responsible for:**

| Operation | Why normalization |
|-----------|-------------------|
| Generate `summary` | Requires content understanding |
| Assess `credibility_tier` | Requires domain judgment |
| Identify `relations` | Requires cross-document awareness |
| Flag `issues` | Requires quality judgment |
| Determine `is_solution` for forum posts | Requires thread context understanding |
| Structure the markdown body | Requires editorial decisions about presentation |
| Populate all frontmatter fields | Requires interpretation of extraction metadata |

The spec defines what the normalization agent receives and produces without prescribing implementation form. The normalization system prompt could live in the corpus repo (for corpus-specific customization) or be standardized tooling (for consistency across corpora).

#### 3.8.4 Phase Boundaries and Re-processing

The three phases are designed to be independently re-runnable:

- **Re-ingestion** (Phase 1 only): Re-acquire from the upstream source when content may have changed. Does not trigger re-extraction or re-normalization unless the ingested content actually differs.
- **Re-extraction** (Phase 2 only): Re-create sidecars from existing ingested files when extraction tools improve (e.g., "find all documents extracted with tesseract v4 and re-extract with v5"). The `extraction_method` and `extraction_tool` sidecar fields enable targeted bulk re-extraction.
- **Re-normalization** (Phase 3 only): Re-normalize from existing extraction sidecars when LLM models improve. This is the most common re-processing scenario and the cheapest — no re-downloading, no re-extracting.

Extraction sidecars are persisted alongside raw files in `ingested/` to enable this independence. Extraction is often the expensive step (OCR, Whisper transcription), and the resulting sidecars are small compared to raw files. Compendiums only clone `documents/`, `assets/`, and `{corpus_id}.toml` — the `ingested/` directory (raw files and sidecars) is never needed downstream.

---

## 4. Corpus Discovery

### 4.1 Overview

Corpus discovery enables compendiums to identify which corpora are relevant to their domain without cloning and scanning every corpus repository. Each corpus's `{corpus_id}.toml` carries tiered summaries that describe the corpus (see section 3.2 for format). At compendium setup time, these summaries are fetched via the Forgejo API — no separate registry repository is needed.

This design follows the spec's principle of avoiding unnecessary infrastructure. The corpora describe themselves; discovery is a computed view over the Corpus organization, not a maintained artifact.

### 4.2 Summary Tier Format

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

### 4.3 API-Driven Discovery Process

Discovery tooling fetches summaries from the Forgejo API without cloning any repos:

1. **Enumerate corpora.** `GET /api/v1/orgs/corpus/repos` — list all repositories in the Corpus organization. Each repo is one corpus.

2. **Fetch corpus metadata.** For each repo, `GET /api/v1/repos/corpus/{name}/contents/{name}.toml` — fetch the file contents via API. These requests are parallelized.

3. **Parse and extract.** Parse each `{corpus_id}.toml` and extract `corpus_id`, `summary_tier1`, `summary_tier2`, `summary_tier3`.

This produces a complete discovery index from live data in seconds, even for hundreds of corpora. The index can be cached locally and refreshed on demand.

### 4.4 Progressive Disclosure Process

The tiered summary structure enables efficient corpus selection at compendium setup time:

1. **Tier 1 scan.** Read the `summary_tier1` for every corpus. At one sentence each, all corpora fit in a single LLM context window. Immediately identify obvious candidates and obvious exclusions. For a Dune compendium: `frank-herbert`, `brian-herbert`, `denis-villeneuve`, `scifi-channel-dune` are obvious candidates. `g8board`, `gm`, `penrite` are obvious exclusions.

2. **Tier 2 confirmation.** For each candidate, read `summary_tier2` to confirm relevance and understand scope. This catches false positives (a corpus whose name suggests relevance but whose content doesn't match) and surfaces additional context about what each corpus actually contains.

3. **Tier 3 deep dive.** Consult `summary_tier3` only when needed — when scope boundaries are unclear or when understanding the full contents matters for the compendium's design. This is optional for most corpora.

4. **Declare dependencies.** Register the selected corpora in `compendium.toml`.

5. **Document-level selection.** After resolving (cloning) declared corpora, read individual document file summaries within each corpus to select which documents feed into synthesis. The compendium's synthesis system prompt guides the LLM's selection decisions at this level.

This process is typically performed once during compendium setup and revisited when new corpora are added to the organization.

### 4.5 Summary Maintenance

Because summaries live in `{corpus_id}.toml` — the same file that defines everything else about the corpus — maintenance is straightforward:

- **New corpus.** When a new corpus repository is created, its `{corpus_id}.toml` includes tiered summaries from the start. No separate registry entry to create.
- **Summary updates.** When a corpus grows significantly (new documents added, coverage expanded), update the summary tiers in `{corpus_id}.toml`. This is a single-file commit in the corpus repo.
- **No sync burden.** There is no separate registry to keep in sync with corpus repos. The summaries are always authoritative because they live at the source.

---

## 5. Compendium Synthesis

### 5.1 Repository Structure

Each compendium repository has this structure:

```
Compendium/{domain}/
├── .gitignore                     # ignores corpora/ (resolved at build time)
├── corpora/                       # resolved corpus repos (gitignored, like node_modules)
│   ├── g8board/                   → resolved (sparse: documents/ + assets/ + g8board.toml)
│   ├── gm/                        → resolved (sparse: documents/ + assets/ + gm.toml)
│   └── ls1tech/                   → resolved (sparse: documents/ + assets/ + ls1tech.toml)
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

### 5.2 Dependency Resolution

Compendium repos only need the `documents/` directory, `assets/` directory, and `{corpus_id}.toml` from each corpus — never the `ingested/` directory (which contains raw files and extraction sidecars used only for re-normalization within the corpus repo). Each corpus dependency is declared in `compendium.toml` with a pinned commit hash and the sparse paths to check out:

```toml
[[compendium.corpora]]
name = "g8board"
repo = "corpus/g8board"
commit = "a1b2c3d"
sparse = ["documents/", "assets/", "g8board.toml"]
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
# clone_corpus "g8board" "Corpus/g8board" "a1b2c3d" "documents/" "assets/" "g8board.toml"
```

This script is run once after cloning the compendium repo, before synthesis, and by the CI workflow on every build. Because `corpora/` is gitignored, the compendium repo itself stays clean — only the manuscript, configuration, and tooling are versioned.

### 5.3 The Synthesis Process

Synthesis transforms source material from multiple corpora into a coherent, structured compendium. This is the core intellectual work of the system.

The process for each compendium:

1. **Resolve corpora.** Run `resolve.sh` to clone/update all declared corpus dependencies at their pinned commits.
2. **Select documents.** Read the `summary` field of each document file across all resolved corpora. Using the compendium's synthesis system prompt as context, the LLM selects documents relevant to the domain. Documents are prioritized by credibility tier and relevance to the compendium's scope.
3. **Organize by taxonomy.** Group selected documents by the compendium's chapter structure.
4. **Synthesize chapters.** Distill the grouped documents into coherent prose, reconciling conflicts, identifying patterns, and citing document IDs.
5. **Build navigation.** Generate/update `SUMMARY.md`, cross-references, and supplementary sections (FAQ, glossary, quick reference).
6. **Build output.** Run mdBook to compile the manuscript into the published static site.

### 5.4 Compendium Configuration

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
sparse = ["documents/", "assets/", "frank-herbert.toml"]

[[compendium.corpora]]
name = "brian-herbert"
repo = "corpus/brian-herbert"
commit = "a1b2c3d"
sparse = ["documents/", "assets/", "brian-herbert.toml"]

[[compendium.corpora]]
name = "denis-villeneuve"
repo = "corpus/denis-villeneuve"
commit = "c3d4e5f"
sparse = ["documents/", "assets/", "denis-villeneuve.toml"]

[[compendium.corpora]]
name = "scifi-channel-dune"
repo = "corpus/scifi-channel-dune"
commit = "f7e8d9c"
sparse = ["documents/", "assets/", "scifi-channel-dune.toml"]
include_all = true          # every document in this corpus is relevant — skip summary assessment
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
documents whose summaries indicate Dune-related content. Frank Herbert's
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

The `include_all = true` flag is an efficiency optimization for corpora where every document is known to be in scope (e.g., `scifi-channel-dune` is entirely Dune content). It skips the summary assessment step for that corpus.

### 5.5 Synthesis Principles

- **Cite documents.** Every factual claim in the compendium references the document ID(s) it derives from. The reader (human or agent) can always trace a claim back to a specific file in a specific corpus.
- **Represent disagreement.** When the service manual says one thing and 30 forum posts say another, the compendium captures both positions with their respective credibility tiers.
- **Aggregate patterns.** If 40 forum posts describe the same failure mode, the compendium entry reflects the pattern (common mileage range, symptoms, root cause) rather than citing each post individually.
- **Respect credibility tiers.** Higher-tier documents carry more weight in synthesis. An `authoritative` document is not overruled by `anecdotal` reports unless the volume and consistency of community experience is overwhelming.
- **Structure for navigation.** Chapters follow the domain's natural taxonomy. Each chapter is self-contained but cross-references related chapters.
- **Leverage document relations.** When documents declare explicit relationships (`contradicts`, `supersedes`, `references`), the synthesis step should incorporate these signals. A document that `contradicts` another is a flag for the compendium to present both positions. A TSB that `supersedes` an earlier one means the earlier guidance may be outdated.
- **Respect document issues.** Documents with unresolved `critical` or `major` issues should be weighted accordingly. A document flagged with `missing_media` of `major` severity may be missing key visual information. The compendium can still use it but should note the gap rather than treating the document as complete.

### 5.6 Versioning

Git provides version control at both layers:

- **Corpus repos** track when documents were added or corrected. The full history of normalization is preserved.
- **Compendium repos** track when synthesis was performed, what changed, and which corpus versions were used. Because `compendium.toml` pins each corpus to a specific commit, compendium builds are reproducible.

---

## 6. Compendium Format

### 6.1 mdBook

The compendium is built as an **mdBook** — a static documentation site generated from structured markdown files. mdBook was selected because:

- Source files are plain markdown in git (the single source of truth)
- Generates clean, navigable HTML with built-in full-text search
- Table of contents generated from `SUMMARY.md`
- Cross-references between chapters via standard markdown links
- Supports embedded images for diagrams, photos, and visual references
- Generates `searchindex.json` for programmatic full-text search
- Lightweight, fast, and self-hostable
- Rust-based toolchain

### 6.2 Textbook Structure

Each compendium follows a consistent structural pattern:

| Section | Purpose |
|---------|---------|
| **Introduction** | Domain overview, scope, how to use this compendium |
| **Quick Reference** | High-frequency lookups — specs, part numbers, key facts |
| **Chapters** | The body of knowledge, organized by domain taxonomy |
| **FAQ** | Common questions that don't fit neatly into a single chapter |
| **Glossary** | Domain-specific terminology definitions |
| **References** | Master registry of all corpora and documents with credibility tiers |

### 6.3 Navigation Aids

The `SUMMARY.md` file serves as both the mdBook table of contents and the agent's navigation map. It provides hierarchical structure down to the section level.

mdBook also generates a `searchindex.json` file at build time that provides full-text search across all pages. This serves as the compendium's index — mapping keywords, part numbers, symptoms, and any other terms to the sections where they appear. See section 10.2 for how the agent leverages this.

### 6.4 Compendium Page Frontmatter

mdBook supports YAML frontmatter on pages — it ignores it during rendering, which makes it ideal for metadata that tooling and agents can read without polluting the HTML output. Every compendium chapter page carries synthesis provenance and per-document traceability:

```yaml
---
chapter_id: "suspension.wheel-bearings.rear"
title: "Rear Wheel Bearings"
synthesis_model: "claude-opus-4-5-20250630"
synthesis_date: "2026-02-08"
last_reviewed: "2026-02-08"
documents:
  - document_id: "G8BD.0042"
    synthesized_at: "2026-01-20"
    credibility_tier: "community_validated"
  - document_id: "G8BD.0118"
    synthesized_at: "2026-01-15"
    credibility_tier: "community_validated"
  - document_id: "G8BD.0203"
    synthesized_at: "2026-02-01"
    credibility_tier: "anecdotal"
  - document_id: "GMSM.0034"
    synthesized_at: "2026-02-01"
    credibility_tier: "authoritative"
  - document_id: "GTSB.0012"
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

#### 6.4.1 Incremental Synthesis

The per-document `synthesized_at` field enables precise incremental re-synthesis. When a corpus's pinned commit is bumped in `compendium.toml`, the staleness check is mechanical:

```
For each chapter in manuscript/:
  For each document in chapter.documents:
    Fetch the document file from corpora/
    If document.normalization_date > chapter_document.synthesized_at:
      Flag this chapter for re-synthesis
```

A commit bump that touches 200 files (because `ingestion_date_last` was updated on a routine check) but only has real normalization changes in 3 of them results in exactly the chapters referencing those 3 documents being flagged. Everything else is untouched. This keeps re-synthesis proportional to actual change, not to ingestion activity.

The same check catches re-normalization events: if a document is re-normalized with a better model (content unchanged, but `normalization_date` and `normalization_model` updated), the compendium correctly flags that chapter for re-synthesis from the improved material.

**Build-time validation:** The `documents` list enables a CI check that verifies every cited document ID actually resolves to a real file in the resolved corpora. This catches broken references when documents are reorganized or when a pinned commit is bumped and document IDs have changed.

**Model audit trail:** Between the `normalization_model` on document files and `synthesis_model` on compendium pages, the full model provenance chain is captured. If a model is found to produce problematic output, you can query across both layers to identify every artifact it touched and prioritize re-processing.

---

## 7. Hosting & Distribution

### 7.1 Architecture

The compendium sites are hosted on an external Caddy server (`ref.example.org`) that is independent of the home infrastructure. This provides:

> **Domain naming:** `ref.example.org` hosts published compendiums — the synthesized reference works that agents and humans browse. `corpus.example.org` is reserved for a future corpus explorer that will provide browsable access to the corpus repositories and their source material.

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

### 7.2 Access Control

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

### 7.3 Caddy Server Configuration

The Caddy instance is an external VPS that currently serves as a reverse proxy. Each compendium is deployed as a subdirectory under `/srv/ref/`.

```
/srv/ref/
├── commodore-ve/        # mdBook build output
├── dune/                # mdBook build output
├── economics/           # mdBook build output
└── ...
```

---

## 8. CI/CD Pipeline

### 8.1 Build & Deploy Flow

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

### 8.2 Deployment Mechanism

The Caddy server accepts deployments via one of:

- **SSH/SCP push:** The Forgejo Actions runner pushes build artifacts directly to `/srv/ref/{domain}/` on the Caddy VPS via SSH with a deploy key.
- **Webhook receiver:** A small receiver script on the Caddy box accepts a tarball via HTTP POST with a shared secret, unpacks it to the target directory.

### 8.3 Workflow Template

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

The `resolve.sh` script (see section 5.2) clones each declared corpus at its pinned commit with sparse checkout, pulling only `documents/`, `assets/`, and `{corpus_id}.toml`. This keeps CI fast even as corpus repos grow large with ingested source material.

### 8.4 Corpus Update Propagation

When new documents are added to a corpus repo, the compendiums that reference it don't automatically rebuild. This is intentional — synthesis is a curated process. The workflow is:

1. New documents are committed to the corpus repo (e.g., `Corpus/g8board`)
2. The compendium maintainer bumps the pinned commit hash in `compendium.toml` when ready to incorporate new material
3. New synthesis is performed incorporating the new documents
4. Push triggers the build and deploy pipeline

For corpora with high ingestion velocity, this can be automated with a scheduled workflow that bumps pinned commits periodically.

---

## 9. Agent Layer

### 9.1 Design

Each domain has a **single bespoke agent** — a dedicated AI assistant that is an expert in that domain and nothing else. There is no multi-agent orchestration, no router, and no shared context between domains. When you need automotive expertise, you invoke the automotive agent. When you need Dune lore, you invoke the Dune agent.

This simplicity is deliberate:

- The user always knows which expert they need
- Each agent's system prompt is fully tailored to its domain
- No prompt budget is wasted on routing logic or domain detection
- Each agent can have domain-specific personality, terminology, and reasoning patterns

### 9.2 Agent Configuration

Each agent is configured as a **skill** (for Claude Code / claude.ai) or equivalent construct for other platforms. The agent's configuration includes:

- **System prompt:** Domain-specific persona, expertise description, reasoning instructions, and the compendium's `SUMMARY.md` content as its navigation map.
- **Compendium URL:** The base URL for fetching compendium pages and the search index (e.g., `https://ref.example.org/commodore-ve/`).
- **Access credentials:** The agent's basic auth credentials for the compendium site.
- **Domain taxonomy:** Key concepts, terminology, and the structure of the domain to guide query decomposition.

### 9.3 Agent Behavior Model

When the agent receives a question, it follows this process:

1. **Understand the query.** Parse the question to identify which systems, symptoms, concepts, or topics are involved.
2. **Navigate the compendium.** Using the `SUMMARY.md` table of contents (already in context), identify which chapter(s) and section(s) are relevant. If the query doesn't map cleanly to the TOC structure, query the `searchindex.json` for relevant terms to discover applicable sections.
3. **Fetch relevant sections.** Retrieve the specific markdown pages from the compendium site via HTTP GET. Only fetch what's needed — not the entire compendium.
4. **Synthesize a response.** Answer the question based on the retrieved compendium content, citing specific documents where the compendium provides them.
5. **Flag coverage gaps.** If the compendium doesn't cover the topic well, tell the user explicitly rather than speculating.

### 9.4 Example: Automotive Agent

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
   reports [G8BD.0015, G8BD.0042, ...], typically appearing between
   60-90k miles). The second most likely cause is the steering
   intermediate shaft — a known weakness that GM issued TSB
   #PI0597B for [GTSB.0023]..."
```

### 9.5 Example: Fiction Agent

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
   both masculine and feminine ancestral memories [FHBT.0001, ch.1].
   Jessica's decision to bear a son one generation early meant Paul
   was uncontrolled by the Sisterhood's plans [FHBT.0001, ch.3]...
   
   The Villeneuve adaptation emphasizes this tension visually in
   the Reverend Mother's testing scene [DVNV.0001, act 1], though it
   compresses the political context that Herbert developed across
   several chapters..."
```

---

## 10. Retrieval Strategy

### 10.1 Primary Method — TOC-Based Navigation

The agent's primary retrieval mechanism is structural navigation using the compendium's table of contents. The `SUMMARY.md` is loaded into the agent's context as part of its system prompt. This gives the agent a complete map of what knowledge exists and where it lives.

This is analogous to how a knowledgeable human uses a reference book: they already know the structure, they go to the right chapter, and they read the relevant section. The agent does the same via HTTP fetches of specific pages.

**Advantages:**

- No embedding infrastructure required
- No vector database to maintain
- Retrieval is deterministic and explainable ("I looked in chapter 4.1")
- Works with the same artifact the human browses
- Updates are instant — new content appears as soon as it's deployed

### 10.2 Search Index Lookup

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

### 10.3 Fallback — Vector Search (Deferred)

Semantic vector search is **not implemented initially** but the architecture accommodates it if needed. The trigger for adding it would be repeated instances where the agent cannot find relevant content through TOC navigation or the search index because the user's query language doesn't match any terminology present in the compendium.

If implemented, it would be a lightweight vector store (e.g., Qdrant in Docker) with embeddings over the compendium's markdown chunks, used only when TOC/search index navigation fails to identify relevant sections.

### 10.4 Forgejo API as Alternative Access Path

The Forgejo REST API provides raw file access to the compendium markdown:

```
GET /api/v1/repos/Compendium/{domain}/raw/manuscript/{path}
Authorization: token {read-only-token}
```

This serves as an alternative access path — useful for agents running in environments where fetching rendered HTML is less convenient than raw markdown (e.g., Claude Code sessions where markdown is the native format). Both access methods (hosted site and API) serve the same content from the same source of truth.

---

## 11. Scaling & Reuse

### 11.1 Adding a New Corpus

1. Create a new repository under the Corpus organization
2. Add `{corpus_id}.toml` with corpus metadata, origin configs, and reingest configuration
3. Add `backlog.toml` and populate with known pending documents
4. Create the `documents/`, `assets/`, and `ingested/` directories
5. Build or configure the ingestion pipeline appropriate to the content type
6. Build or configure the extraction pipeline — content-type-specific scripts that produce extraction sidecars (see section 3.8.2). For simple text content, a passthrough extractor is sufficient
7. Begin processing source material through the three-phase pipeline: ingest → extract → normalize (see section 3.8)
8. The corpus is now discoverable — its `{corpus_id}.toml` tiered summaries are available via the Forgejo API for any compendium to find (see section 4)

### 11.2 Adding a New Compendium

1. Create a new repository under the Compendium organization
2. Discover relevant corpora via API-driven progressive disclosure (see section 4.4)
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

### 11.3 Stacking Compendiums

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

### 11.4 Domain Taxonomy Design

Each domain needs its own taxonomy — the organizational structure that chapters follow. This should be designed before significant content is ingested, though it will evolve. Guidelines:

- Follow the natural structure of the domain (for a vehicle: by system; for health: by body system; for fiction: by world element — characters, factions, locations, technology, themes, adaptations)
- Prefer 2-3 levels of hierarchy maximum
- Each leaf section should be self-contained enough to be useful when fetched in isolation
- Cross-reference liberally between related sections

### 11.5 Standardized Frontmatter Schema

The complete document frontmatter schema is defined in section 3.3. In summary:

**Universal required** (every document):
`document_id`, `title`, `summary`, `content_type`, `credibility_tier`, `ingestion_date_first`, `ingestion_date_last`, `content_changed_last`, `normalization_confidence`, `normalization_model`, `normalization_date`

**Universal optional** (present when applicable):
`author`, `date_published`, `origin_url`, `volatility`, `relations`, `issues`

**Extended schemas** are determined by `content_type` (closed enum):

| Content Type | Required Extended Fields | Optional Extended Fields |
|-------------|-------------------------|--------------------------|
| `forum_post` | `username`, `thread_url` | `reply_count`, `is_solution` |
| `reddit_post` | `username`, `subreddit`, `post_url` | `score`, `comment_count`, `post_type` |
| `book` | `work_title` | `isbn`, `word_count`, `series_name`, `series_position` |
| `service_manual` | `manual_title`, `section_reference`, `model_years` | `vehicle_system` |
| `technical_bulletin` | `bulletin_number`, `affected_models`, `affected_years` | `superseded_by` |
| `video` | `duration_seconds`, `has_visual_content` | `channel_name` |
| `podcast` | `duration_seconds` | `episode_number`, `series_name` |
| `research_paper` | `journal`, `peer_reviewed` | `doi` |
| `article` | `article_url` | `publication` |
| `screenplay` | `work_title`, `medium` | `draft` |
| `product_documentation` | `product_name`, `manufacturer` | `document_type`, `part_numbers` |

**Compendium page frontmatter** (section 6.4):
`chapter_id`, `title`, `synthesis_model`, `synthesis_date`, `last_reviewed`, `documents[]` (with `document_id`, `synthesized_at`, `credibility_tier` per document)

---

## 12. Infrastructure Summary

### 12.1 Component Map

```
┌──────────────────────────────────────────────────────────────┐
│                    Forgejo (Tailnet)                           │
│                                                                │
│  Corpus Organization               Compendium Organization     │
│  ├── g8board/                      ├── commodore-ve/           │
│  │   ├── g8board.toml              │   ├── corpora/ (resolved) │
│  │   ├── backlog.toml              │   ├── manuscript/         │
│  │   ├── documents/                │   ├── compendium.toml     │
│  │   ├── assets/                   │   └── book.toml           │
│  │   └── ingested/                 ├── dune/                   │
│  ├── frank-herbert/                ├── economics/              │
│  └── ...                           └── ...                     │
│                                                                │
│  example-org Organization (System Infrastructure)                │
│  └── athenaeum/                    # spec, tooling             │
│                                                                │
│  Forgejo Actions Runner                                        │
│  └── on push: resolve corpora → mdbook build → deploy          │
└───────────────────────┬────────────────────────────────────────┘
                        │ rsync / scp / webhook
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                  Caddy VPS (External)                          │
│                                                                │
│  ref.example.org                                               │
│  ├── basicauth (steven, agent)                                 │
│  ├── /srv/ref/commodore-ve/    ← mdBook HTML output         │
│  ├── /srv/ref/dune/            ← mdBook HTML output         │
│  ├── /srv/ref/economics/       ← mdBook HTML output         │
│  └── ...                                                       │
└───────────────────────┬────────────────────────────────────────┘
                        │ HTTPS (basic auth)
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                       Consumers                                │
│                                                                │
│  Steven (browser)                                              │
│  └── Browses any compendium like a textbook                    │
│                                                                │
│  Domain Agent (Claude skill / Claude Code)                     │
│  ├── SUMMARY.md in system prompt context                       │
│  ├── searchindex.json for full-text keyword lookup             │
│  ├── Fetches specific pages via HTTP on demand                 │
│  └── Responds with source-grounded answers                     │
└──────────────────────────────────────────────────────────────┘
```

### 12.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Source of truth | Forgejo (git) | Version control, API access, Actions CI |
| Source organization | Forgejo org (Corpus) | One repo per corpus, with origins declared in `{corpus_id}.toml` |
| Corpus discovery | Forgejo API + `{corpus_id}.toml` | Tiered summaries fetched on demand, no separate registry repo |
| Compendium format | Markdown + mdBook | Human-readable source, clean output, built-in search |
| Source linkage | Declared dependencies in `compendium.toml` | Pin corpora to commits, resolve at build time with sparse checkout |
| Hosting | Caddy on external VPS | Simple, reliable, automatic HTTPS, basic auth |
| CI/CD | Forgejo Actions | Integrated with repos, self-hosted runner |
| Agent platform | Claude (skill / Code) | Primary AI interface, flexible access patterns |
| Retrieval | TOC navigation + searchindex.json + HTTP fetch | No additional infrastructure, deterministic, explainable |

### 12.3 What Is Intentionally Not Included

| Component | Status | Trigger to Add |
|-----------|--------|----------------|
| Vector database | Deferred | Agent repeatedly fails to find content via TOC/search index |
| Knowledge graph | Deferred | Multi-hop relationship queries become common |
| Domain router | Not planned | Only needed if agents are invoked implicitly |
| Cross-domain linking | Not planned | Domains are intentionally isolated |
| Real-time ingestion | Not planned | Compendium is a curated reference, not a live feed |
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

When the agent encounters a question it cannot answer well (coverage gap), this could be captured as a signal to prioritize source collection in that area. The agent logs topics where it had to flag thin coverage, and those become ingestion priorities for the relevant origins.

### B.4 Multi-Format Export

The same compendium markdown could be exported to additional formats: PDF for offline reading, EPUB for e-readers, or structured JSON for programmatic access. These are build-step additions that don't affect the source material.

### B.5 Corpus Ingestion Automation

As corpus pipelines mature, ingestion can be increasingly automated. A forum scraper that runs on a schedule, a YouTube channel monitor that transcribes new uploads, or an RSS-triggered pipeline for new publications. The normalized output always flows into the same corpus repo structure regardless of how it was triggered.
