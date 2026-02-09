---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 2.0
status: draft
author: Steven Rahn
date_created: 2026-02-08
date_modified: 2026-02-09
addenda_incorporated:
  - ATH-ARCH-A001
  - ATH-ARCH-A002
changelog:
  - version: 2.0
    date: 2026-02-09
    summary: "Incorporate ATH-ARCH-A001 (origin identity guidelines), ATH-ARCH-A002 (term registry)"
  - version: 1.0
    date: 2026-02-08
    summary: "Initial specification"
---

## 1. Overview

**Athenaeum** is a personal knowledge infrastructure for building domain-specific AI agents backed by comprehensive, source-grounded reference material. The system separates the concerns of **source collection** and **knowledge synthesis** into distinct layers, enabling source material to be reused across multiple domains without duplication.

Each domain of interest (automotive repair, political theory, a fiction universe) is treated as an independent **compendium** that pulls from one or more **corpora** — normalized repositories of source material organized by where the information came from, not what it's about. Compendiums synthesize their corpora into authoritative **manuscripts** that are compiled into browsable, textbook-like references serving both human readers and bespoke AI agents.

Athenaeum is designed around four core principles:

- **Origin objectivity.** Sources are organized by where they came from — a forum, an author, a manual, a YouTube channel. This is an unchallengeable fact that requires no editorial judgment. Topical categorization happens downstream via tags.
- **Domain isolation.** Each compendium is fully independent — its own repository, its own synthesized reference, its own agent. There is no shared knowledge graph or cross-domain routing. When you need an expert, you call on them explicitly.
- **Human-first accessibility.** Every compendium is browsable and readable by a human, structured like a textbook with a table of contents, search, glossary, and source citations. The agent accesses the same artifact a human would.
- **Source provenance.** Every claim in the compendium traces back to its original source material. The agent can tell you not just "this is the answer" but "this answer is supported by the service manual, corroborated by 12 forum reports, and contradicted by one outlier."

### 1.1 Design Philosophy

The architecture intentionally avoids complexity where simplicity suffices. There is no vector database, no knowledge graph, no multi-agent orchestration, and no domain router. These are not rejected — they are deferred until a concrete need for them is demonstrated. The system is designed so that any of these can be added later without rearchitecting what exists.

---

## 2. Two-Layer Architecture

The system is organized into two Forgejo organizations that serve fundamentally different purposes, plus a Term Registry that provides system-wide controlled vocabulary (see section 5). The registry lives in the `example-org` Forgejo organization as foundational infrastructure — not a third content organization, but the controlled vocabulary that both content organizations depend on.

**Terminology:** *Corpus* (plural: *corpora*) means "a body of collected texts" — this is where raw source material lives. *Compendium* means "a comprehensive collection of concise information" — this is where synthesized reference works live. *Manuscript* refers to the pre-rendered markdown that gets compiled into the published compendium.

### 2.1 Corpus Organization

The **Corpus** organization contains origin repositories — one per source of information. Each origin is a self-contained collection of normalized material from a single provenance.

```
Corpus (Forgejo Organization)
│
├── Automotive
│   ├── g8board/                  # forum — G8Board.com community
│   ├── ls1tech/                  # forum — LS1Tech.com community
│   ├── gm/                      # General Motors — manuals, TSBs, bulletins, press releases
│   ├── holden/                   # Holden — workshop manuals, AU-market documentation
│   └── penrite/                  # Penrite Oils — datasheets, application guides
│
├── Academic / Reference
│   ├── jstor-economics/          # journal articles from JSTOR
│   ├── pubmed/                   # medical research papers
│   ├── marxists-org/             # texts from marxists.org
│   └── wikipedia-economics/      # relevant Wikipedia articles
│
├── Fiction / Creative
│   ├── frank-herbert/            # all works by Frank Herbert
│   ├── brian-herbert/            # all works by Brian Herbert
│   ├── denis-villeneuve/         # screenplays, production material
│   └── scifi-channel-dune/       # miniseries episodes
│
├── Media
│   ├── engineering-explained/    # YouTube channel transcripts
│   ├── south-main-auto/         # YouTube channel transcripts
│   └── huberman-lab/            # podcast transcripts
│
└── ...
```

**Key properties of origin repos:**

- **One origin, one repo.** A forum is a repo. An author is a repo. A YouTube channel is a repo. A government agency's publications are a repo.
- **No editorial judgment.** The origin repo contains everything captured from that source, normalized and tagged. There is no filtering by topic — that happens at the compendium layer.
- **Self-contained normalization.** Each origin repo has its own ingestion and normalization pipeline appropriate to its source type (web scraper for forums, PDF extractor for manuals, transcription pipeline for video/audio).
- **Rich frontmatter tags.** Every normalized file is tagged with descriptive metadata that enables downstream compendiums to filter for relevant content. The tags are objective descriptors of what the source discusses, not judgments about which compendium it belongs to.

### 2.2 Compendium Organization

The **Compendium** organization contains compendium repositories — one per domain. Each compendium declares its origin dependencies in `compendium.toml` and resolves them at build/synthesis time, pulling the required content into a local `corpora/` directory. This is analogous to how `package.json` declares dependencies and `node_modules` is populated by `npm install`.

```
Compendium (Forgejo Organization)
├── commodore-ve/                 # Pontiac G8 / Holden Commodore VE platform
├── economics/                    # broad economics compendium
├── socialism/                    # focused socialism compendium
├── dune/                         # Dune universe compendium
├── human-health/                 # fitness, nutrition, medical reference
└── ...
```

Each compendium repository has this structure:

```
Compendium/{domain}/
├── .gitignore                     # ignores corpora/ (resolved at build time)
├── corpora/                       # resolved origin repos (gitignored, like node_modules)
│   ├── g8board/                   → resolved (sparse: normalized/ + assets/ + origin.toml)
│   ├── gm/                        → resolved (sparse: normalized/ + assets/ + origin.toml)
│   └── ls1tech/                   → resolved (sparse: normalized/ + assets/ + origin.toml)
├── manuscript/                    # pre-rendered compendium content (mdBook source)
│   ├── SUMMARY.md                 # mdBook table of contents
│   ├── introduction.md
│   ├── quick-reference.md
│   ├── faq.md
│   ├── glossary.md
│   ├── sources.md                 # master source registry
│   └── {chapter-slug}/            # chapters organized by domain taxonomy
│       ├── {section}.md
│       └── ...
├── compendium.toml                # compendium configuration (dependencies, tag filters, etc.)
├── book.toml                      # mdBook configuration (src = "manuscript")
├── resolve.sh                     # clones/updates corpora from declared dependencies
└── README.md
```

#### 2.2.1 Dependency Resolution

Compendium repos only need the `normalized/` directory, `assets/` directory, and `origin.toml` from each origin — never the `ingested/` directory, which can be massive (PDFs, epubs, HTML dumps, video files). Each origin dependency is declared in `compendium.toml` with a pinned commit hash and the sparse paths to check out:

```toml
[[compendium.corpora]]
name = "g8board"
repo = "Corpus/g8board"
commit = "a1b2c3d"
require_any = ["g8", "ve", "suspension"]
sparse = ["normalized/", "assets/", "origin.toml"]
```

The `corpora/` directory is gitignored — it is populated on demand by a `resolve.sh` script that clones each declared origin at its pinned commit with sparse checkout:

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
# clone_corpus "g8board" "Corpus/g8board" "a1b2c3d" "normalized/" "assets/" "origin.toml"
```

This script is run once after cloning the compendium repo, before synthesis, and by the CI workflow on every build. Because `corpora/` is gitignored, the compendium repo itself stays clean — only the manuscript, configuration, and tooling are versioned.

### 2.3 How They Connect

Origins flow into compendiums via declared dependencies. Multiple compendiums can reference the same origin. The compendium layer uses frontmatter tags to filter which sources are relevant to its scope.

```
Corpus/frank-herbert/
  ├── dune.md                    tags: [dune, arrakis, spice, sci-fi]
  ├── dune-messiah.md            tags: [dune, arrakis, prescience, sci-fi]
  ├── man-of-two-worlds.md       tags: [comedy, sci-fi, collaboration]
  └── the-dragon-in-the-sea.md   tags: [submarine, psychology, sci-fi]

Corpus/denis-villeneuve/
  ├── dune-2021-screenplay.md    tags: [dune, arrakis, screenplay, adaptation]
  ├── dune-part-two-screenplay.md tags: [dune, screenplay, adaptation]
  ├── blade-runner-2049.md       tags: [blade-runner, screenplay, sci-fi]
  └── arrival-screenplay.md      tags: [linguistics, sci-fi, screenplay]

Compendium/dune/
  corpora:
    - frank-herbert/       → filter: tags contain "dune"
    - brian-herbert/        → filter: tags contain "dune"
    - denis-villeneuve/     → filter: tags contain "dune"
    - scifi-channel-dune/   → filter: all (entire origin is Dune-specific)
  
  Result: dune.md, dune-messiah.md, dune-2021-screenplay.md,
          dune-part-two-screenplay.md, and everything from scifi-channel-dune.
          NOT man-of-two-worlds.md, NOT blade-runner-2049.md.
```

---

## 3. Origin Repositories

### 3.1 Origin Identity

An origin repository represents a single distinct voice — one entity that produces information. The question that determines an origin boundary is not "what kind of document is it" or "what platform does it live on" but **"who produced it."**

If you can point at a source and say "that came from the same entity expressing its own perspective," it belongs in the same origin. If two sources come from different entities — even if they're on the same platform, cover the same topic, or share the same format — they belong in separate origins.

#### What "Voice" Means

A voice is an entity with a coherent perspective:

- A **company** — GM, Holden, Penrite Oils
- A **community** — one forum, one subreddit, one Discord server
- An **author** — Frank Herbert, Brian Herbert
- A **channel or show** — Engineering Explained, South Main Auto
- A **government body** — NHTSA, Australian ANCAP
- An **academic journal** — a single publication venue

A platform is never a voice. Reddit is not an origin — r/MechanicAdvice is. YouTube is not an origin — Engineering Explained is. "Car forums" is not an origin — g8board is.

#### Consolidation by Entity, Not Document Type

All material produced by a single entity belongs in one origin, regardless of document type or format. General Motors publishes service manuals, technical service bulletins, recall notices, press releases, dealer bulletins, and marketing brochures. These are all one voice: GM.

**Before (incorrect — split by document type):**
```
corpus/gm-service-manuals/
corpus/gm-bulletins/
corpus/gm-press-releases/
```

**After (correct — one entity, one origin):**
```
corpus/gm/
```

Within the `gm` origin, individual sources use `source_type` to distinguish `service_manual` from `technical_bulletin` from `product_documentation` from `article`. Tags handle topical filtering. Credibility tiers handle trust differences between a factory service manual (`authoritative`) and a marketing brochure (`expert` or lower). The origin only answers: **who said this.**

#### Why Not Consolidate Similar Voices?

Five car forums (g8board, ls1tech, performanceforums, pontiacg8forum, holdenforums) share a platform type, content structure, and ingestion method. It's tempting to merge them into one `car-forums` origin to reduce repo count. This is wrong for four reasons:

1. **Each community is a distinct voice.** g8board is G8-obsessed. ls1tech is LS-engine-first and happens to cover G8s. holdenforums brings the Australian VE platform perspective that American forums lack. These are genuinely different perspectives with different biases, different expertise concentrations, and different blind spots.

2. **Combining introduces the taxonomy problem we're avoiding.** The entire origin architecture is built on the principle that "where it came from" is an unchallengeable fact requiring no editorial judgment. If you combine forums, you're making an editorial decision about which communities are "similar enough" — and that decision may need to be undone later.

3. **The compendium is where commonality is extracted.** Five forums all discussing rear wheel bearings is not a reason to combine them. It's a reason for the compendium to pull from all five and synthesize their perspectives. That's the compendium's job, not the origin's.

4. **The friction of multiple repos is trivial.** Adding an origin as a dependency is one line in `compendium.toml`. Sparse checkout is handled by `resolve.sh`. The real friction is untangling combined origins later when you need one voice in a compendium but not another.

#### The Decision Test

When deciding whether something is one origin or multiple:

1. **Can you name the entity?** "GM", "g8board", "Frank Herbert", "r/MechanicAdvice" — if you can name it as a single entity with a coherent identity, it's one origin.

2. **Would you ever want one without the other in a compendium?** If ls1tech's LS engine content belongs in an engine-building compendium but g8board's doesn't, they must be separate origins. You can't partially include a repo.

3. **Is the split based on document type or entity?** If you're splitting because "service manuals are different from press releases," stop — that's a `source_type` distinction, not an origin distinction. If you're splitting because "GM and Holden are different manufacturers," proceed — those are different entities even though they shared a corporate parent.

#### Updated Examples

| Voice (Entity) | Origin Repo | Contains |
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

### 3.2 Source Registration

Each origin repo contains a registration file that declares metadata about the origin itself:

```toml
# origin.toml
origin_id = "g8board"
origin_name = "G8Board.com"
origin_type = "forum"
origin_url = "https://www.g8board.com"
description = "Community forum for Pontiac G8 owners and enthusiasts"
source_id_prefix = "G8BD"            # 4-letter prefix for all source IDs from this origin
ingestion_method = "web_scraper"
active = true                        # whether new content is still being captured

[reingest]
default_volatility = "unlikely"       # most old threads are stable
active_threshold_days = 7             # check 'active' sources weekly
periodic_threshold_days = 90          # check 'periodic' sources quarterly
unlikely_threshold_days = 365         # check 'unlikely' sources annually
# 'static' sources are never re-checked
```

For a multi-document-type entity (see section 3.1), the registration reflects that a single voice may have multiple ingestion paths:

```toml
# origin.toml for gm
origin_id = "gm"
origin_name = "General Motors"
origin_type = "manufacturer"
origin_url = "https://www.gm.com"
description = "Official documentation, bulletins, and publications from General Motors"
source_id_prefix = "GMOT"
ingestion_method = "mixed"
active = true

[reingest]
default_volatility = "static"
unlikely_threshold_days = 365
```

The `ingestion_method = "mixed"` reflects that a single entity origin may have multiple ingestion paths (PDF extraction for manuals, web scraping for press releases, API access for recall databases). The origin groups them by voice; the pipeline handles format differences internally.

The `[reingest]` section defines the default volatility for sources in this origin and the thresholds for re-ingestion priority. Individual sources can override `default_volatility` via the `volatility` field in their frontmatter. The ingestion scanner compares each source's `ingestion_date_last` against the appropriate threshold to generate a re-ingestion priority queue.

The `source_id_prefix` ensures globally unique source IDs across all origins. Prefixes are 4 uppercase letters (allowing for 456,976 unique origin prefixes). Every normalized file in this repo will have a source ID like `G8BD.0001`, `G8BD.0042`, etc. The numeric portion is zero-padded to 4 digits, supporting up to 9,999 sources per origin. When a compendium cites `G8BD.0042`, it unambiguously resolves to a specific file in a specific origin repo.

#### 3.2.1 Origin Repository Layout

Each origin repo has a clean top-level structure:

```
Corpus/g8board/
├── origin.toml                         # origin registration and reingest config
├── manifest.toml                       # registry of all known sources (captured or not)
├── normalized/                         # one markdown file per captured source
│   ├── G8BD.0001.md
│   ├── G8BD.0002.md
│   └── G8BD.0042.md
├── assets/                             # embedded content referenced by normalized files
│   ├── G8BD.0001/
│   │   ├── bearing-removal.jpg
│   │   └── torque-sequence.png
│   └── G8BD.0042/
│       └── hub-assembly-diagram.png
└── ingested/                           # original captured artifacts, organized by source ID
    ├── G8BD.0001/
    │   └── thread.html                 # original filenames preserved
    ├── G8BD.0002/
    │   └── thread.html
    └── G8BD.0042/
        ├── thread.html                 # initial capture
        └── thread_wayback_20190315.html  # remediation capture
```

**Directory purposes:**

- **`normalized/`** — One markdown file per source. Files only exist here when there is actual normalized content. No stubs, no placeholders.
- **`assets/`** — Images, diagrams, and other embedded content referenced by normalized files. Organized as one subdirectory per source ID (only present when that source has assets). Normalized markdown references assets via relative paths: `![diagram](../assets/G8BD.0042/hub-assembly-diagram.png)`.
- **`ingested/`** — Original captured artifacts in their native format. Organized as one subdirectory per source ID, preserving original filenames. Multiple files per source are common (e.g., initial capture plus Wayback snapshot for remediation).

**The many-to-one rule:** A single source can have multiple files in `ingested/{source_id}/` — the same content in different formats, multiple captures from different dates, or complementary representations (a transcript plus screenshots). Regardless of how many ingested files exist for a source, normalization always produces exactly **one markdown file** in `normalized/` per source ID. The `raw_sources` field in the frontmatter lists the filenames from `ingested/{source_id}/` that the normalization was produced from.

#### 3.2.2 Source Manifest

Each origin repo contains a `manifest.toml` that serves as a registry of every source known to belong to this origin — whether captured or not. This is the origin's complete inventory: what we have, what we know about, and what we're planning to acquire.

```toml
# manifest.toml

[[sources]]
source_id = "G8BD.0042"
title = "Rear wheel bearing failure at 80k miles"
status = "captured"

[[sources]]
source_id = "G8BD.0200"
title = "Complete AFM delete guide with dyno results"
status = "pending"
priority = "high"
discovered_url = "https://www.g8board.com/forum/thread-56789"
discovered_date = "2026-02-08"

[[sources]]
source_id = "G8BD.0201"
title = "Headlight condensation fix - bake and reseal"
status = "pending"
priority = "medium"
discovered_url = "https://www.g8board.com/forum/thread-56800"
discovered_date = "2026-02-08"
notes = "Includes detailed photos of the baking process"

[[sources]]
source_id = "G8BD.0202"
title = "G8 production numbers by color and trim"
status = "deferred"
notes = "Interesting but not relevant to any current compendium"
```

For an author origin, the manifest doubles as a bibliography:

```toml
# manifest.toml for frank-herbert

[[sources]]
source_id = "FHBT.0001"
title = "Dune"
status = "captured"

[[sources]]
source_id = "FHBT.0002"
title = "Dune Messiah"
status = "captured"

[[sources]]
source_id = "FHBT.0003"
title = "Children of Dune"
status = "pending"
priority = "high"
notes = "Need to acquire epub"

[[sources]]
source_id = "FHBT.0011"
title = "The White Plague"
status = "deferred"
notes = "Out of print, difficult to source"

[[sources]]
source_id = "FHBT.0012"
title = "Man of Two Worlds"
status = "unavailable"
notes = "Co-authored with Bill Ransom, no digital edition found"
```

For a multi-document-type entity (see section 3.1), one manifest covers all document types from that voice:

```toml
# manifest.toml for gm — partial example

[[sources]]
source_id = "GMOT.0001"
title = "2008 Pontiac G8 Factory Service Manual — Engine Mechanical"
status = "captured"

[[sources]]
source_id = "GMOT.0042"
title = "TSB PI0597B — Rear Wheel Bearing Premature Failure"
status = "captured"

[[sources]]
source_id = "GMOT.0100"
title = "2008 Pontiac G8 Press Release — Launch Announcement"
status = "pending"
priority = "low"
discovered_url = "https://media.gm.com/archive/2008/pontiac-g8"
discovered_date = "2026-02-09"
```

The `source_type` field in each normalized file's frontmatter distinguishes what kind of document it is (`service_manual`, `technical_bulletin`, `article`, `product_documentation`). The manifest and origin just track that it all comes from GM.

**Status values:**

| Status | Meaning |
|--------|---------|
| `captured` | Ingested, normalized, and present in `normalized/`. The source is fully in the system |
| `pending` | Known to exist and belongs in this origin. Queued for future ingestion |
| `deferred` | Known to exist, explicitly deprioritized. Won't be ingested soon but tracked for completeness |
| `unavailable` | Known to exist but currently impossible to acquire (dead link, out of print, behind paywall) |

**Priority values** (only applicable to `pending` sources):

| Priority | Meaning |
|----------|---------|
| `critical` | Blocking a compendium — needed for synthesis now |
| `high` | Actively wanted for a current compendium |
| `medium` | Would improve coverage but not urgent |
| `low` | Known to exist, no current compendium needs it |

**Manifest-specific optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `discovered_url` | string | Where this source was found (for web-based origins) |
| `discovered_date` | date | When this source was discovered |
| `notes` | string | Freeform notes about this source or why it's in a particular status |

**Source IDs are reserved at discovery time.** When you identify a thread, article, or work that belongs in this origin, it gets a manifest entry and a source ID immediately — even before ingestion. This means the ID is stable and can be referenced in `relations` by other sources before the content is captured. Gaps in numbering (from sources that remain `pending` indefinitely) are expected and harmless.

**The manifest is not for cross-origin references.** If a g8board post mentions a GM TSB, that reference is recorded as an `unresolved` relation in the source's frontmatter — not as a manifest entry in g8board. The TSB belongs in the `gm` origin and would be registered there.

**Build-time validation:**

- Every `captured` entry in manifest must have a corresponding file in `normalized/`
- Every file in `normalized/` must have a `captured` entry in manifest
- No `pending`, `deferred`, or `unavailable` source should have a file in `normalized/`

**Ingestion backlog reporting:**

```
Ingestion Backlog:
  Corpus/frank-herbert:     6 captured, 8 pending (2 high, 3 medium, 3 low), 2 deferred, 1 unavailable
  Corpus/g8board:          42 captured, 156 pending (12 critical, 45 high, 99 medium), 3 deferred
  Corpus/gm:               75 captured, 120 pending (20 high, 60 medium, 40 low), 5 deferred
```

### 3.3 Normalized Source Format

Every normalized source file is a single markdown document with structured YAML frontmatter. The frontmatter follows a rigid schema: a set of universal fields present on every source, plus extended fields determined by the `source_type`. This consistency enables tooling to validate, query, and compare sources across any origin.

#### 3.3.1 Universal Required Fields

Every source file must include all of these fields, no exceptions:

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | string | `XXXX.####` globally unique identifier (4-letter origin prefix + 4-digit number) |
| `title` | string | Short descriptive label for the source file (not necessarily the work's canonical title) |
| `summary` | string | One-to-three sentence description of what this source contains and why it's useful. Generated during normalization. Enables synthesis-time relevance assessment without reading the full content |
| `source_type` | enum | Declares which extended schema applies. See section 3.3.4 for valid types |
| `credibility_tier` | enum | `authoritative`, `expert`, `community_validated`, `anecdotal`, `speculative`. See section 3.4 |
| `tags` | string[] | Objective content descriptors for filtering and scoping. See section 3.3.2 |
| `raw_sources` | string[] | Filenames in `ingested/{source_id}/` this was normalized from. Preserves traceability to original artifacts |
| `ingestion_date_first` | date | When this source was originally captured |
| `ingestion_date_last` | date | When we last checked/re-ingested from the upstream source (same as `ingestion_date_first` on initial capture) |
| `content_changed_last` | date | When the upstream content last actually differed from what we had. Used by the ingestion layer to assess source stability |
| `normalization_confidence` | float | `0.0`–`1.0`, quality of the conversion process. See section 3.4.1 |
| `normalization_model` | string | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`, `whisper-large-v3`) |
| `normalization_date` | date | When normalization was last performed. **This is the field the compendium layer compares against to determine if re-synthesis is needed** — it captures both content changes and re-normalization with improved models |

#### 3.3.2 Tags

Tags are objective descriptors of what the source discusses — not where it should be used. Good tags describe the content's topics, subjects, entities, and concepts. The same source can be relevant to multiple compendiums through different tag intersections.

Tags are the primary mechanism by which `compendium.toml` filters sources for inclusion. They should be:

- **Objective** — describe what's in the content, not editorial judgments
- **Granular** — prefer specific terms (`wheel-bearing`, `l76`, `afm-delete`) over vague ones (`car-parts`)
- **Consistent** — use the same tag across origins for the same concept (don't mix `wheel-bearing` and `hub-bearing` for the same component). The Term Registry (section 5) is the enforcement mechanism for tag consistency — every tag used in frontmatter must be a registered term

#### 3.3.3 Universal Optional Fields

These fields are present on most sources but legitimately absent on some:

| Field | Type | When absent |
|-------|------|-------------|
| `author` | string | Uses canonical term tags from the Term Registry (section 5). Reserved for identifiable people — anonymous forum posts and Reddit posts use the `username` extended field instead. Anonymous or unsigned government documents omit this field entirely |
| `date_published` | date | Undated historical texts, some web content |
| `origin_url` | string | Physical books, offline documents |
| `volatility` | enum | `static`, `unlikely`, `periodic`, `active`. Omit to inherit the default from `origin.toml`. Only set per-source as an override when a source's volatility differs from the origin norm (e.g., an unusually active thread on a mostly-dormant forum) |
| `relations` | array | Omit if no explicit references to other sources. See section 3.6 |
| `issues` | array | Omit if no known quality or completeness problems. See section 3.5 |

#### 3.3.4 Extended Schemas by `source_type`

The `source_type` field determines which additional fields are required or available. This is a closed enum — adding a new type requires defining its extended schema.

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

Covers: complete published works — novels, non-fiction books, collected works. **A single source is always the entire book.** In `ingested/` the book may be split across many files (chapter PDFs, an epub, a complete PDF), but normalization always produces one markdown file per work.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `work_title` | yes | string | Canonical title of the work (e.g., "Dune") |
| `isbn` | no | string | ISBN if known |
| `word_count` | no | int | Total word count of the complete work |
| `series_name` | no | string | Name of the series (e.g., "Dune Chronicles") |
| `series_position` | no | int | Position in the series (e.g., 1) |

##### `service_manual`

Covers: OEM service manuals, workshop manuals. Each section of the manual is a separate source — the manual as a whole is too large for a single file and sections are independently useful.

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

Covers: YouTube videos, instructional content, any video-first source. Each video is one source file containing the transcript and, where relevant, descriptions of visual content.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `duration_seconds` | yes | int | Video length |
| `has_visual_content` | yes | bool | Whether visual elements are meaningful to the content (a hands-on repair demo vs. a talking head) |
| `channel_name` | no | string | Channel or creator name, if not obvious from the origin |

##### `podcast`

Covers: Audio-first content — podcast episodes, radio segments, audiobook supplements. Each episode is one source file.

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

#### 3.3.5 Complete Example

A forum post with all applicable fields:

```yaml
---
source_id: "G8BD.0042"
title: "DIY rear wheel bearing replacement with diagnosis walkthrough"
summary: "Detailed step-by-step guide for diagnosing and replacing rear wheel bearings on the Pontiac G8, including jacking points, torque specs, and tool list. Author reports failure at 82k miles with symptoms of humming at highway speeds progressing to grinding."
source_type: "forum_post"
credibility_tier: "community_validated"
tags: ["suspension", "wheel-bearing", "rear", "diagnosis", "replacement", "g8", "ve"]
raw_sources: ["thread.html", "thread_wayback_20190315.html"]
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
    source_id: "G8BD.0038"
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

Each source is rated for trustworthiness:

| Tier | Description | Examples |
|------|-------------|----------|
| `authoritative` | Official or primary source documentation | OEM service manual, published TSB, peer-reviewed research, original text of a novel |
| `expert` | Credentialed professional with demonstrated expertise | Professional mechanic writeup, licensed practitioner guide, scholarly analysis |
| `community_validated` | Claim independently confirmed by multiple people | Forum fix confirmed by 5+ unrelated users |
| `anecdotal` | Single person's experience, unconfirmed | One forum post describing a symptom |
| `speculative` | Theory or hypothesis without supporting evidence | "I think it might be the alternator" |

For fiction origins, `authoritative` means the primary text itself. `expert` would be published literary criticism. `community_validated` might be widely-accepted fan analysis. The tiers adapt naturally to any domain.

#### 3.4.1 Normalization Confidence

The `normalization_confidence` field (`0.0`–`1.0`) rates the quality of the conversion process itself — how accurately the raw source was captured and converted to markdown. This is distinct from credibility (trustworthiness of claims) and distinct from tags (what it's about).

A perfectly transcribed YouTube video might have high normalization confidence but low credibility tier. A badly OCR'd service manual might have low normalization confidence but authoritative credibility.

### 3.5 Source Issues

Normalized sources can declare known quality or completeness problems via the `issues` array. This is distinct from `normalization_confidence` — confidence rates how well the conversion went for what we had, while issues flag what we're missing or what has degraded.

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
| `missing_media` | Images, videos, or embedded content no longer available at the original source |
| `broken_links` | Referenced URLs within the source content are dead |
| `partial_content` | Source was truncated, paywalled, or incompletely captured |
| `content_modified` | Source has been edited since original publication — original version may differ from current |
| `encoding_corruption` | Garbled text, mojibake, or mangled characters |
| `format_loss` | Tables, diagrams, code blocks, or formatting that didn't survive conversion |

#### 3.5.2 Severity Levels

| Severity | Meaning |
|----------|---------|
| `critical` | Source is essentially unusable without remediation — key content is missing or corrupted |
| `major` | Significant information loss but source is still partially useful |
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

The `resolved` boolean tracks whether the issue has been addressed. The typical workflow: normalization flags dead images → issue is logged with `remediation: "wayback_snapshot"` → Wayback snapshot is retrieved and added to `ingested/{source_id}/` → source is re-normalized from improved raw material → issue is marked `resolved: true`. The issue remains in frontmatter as a historical record.

For the `content_modified` type, the remediation may involve pulling both the current version and a Wayback snapshot as separate raw files. A forum post edited to add "UPDATE: don't do this, it caused X" is more valuable with both versions visible — the normalization can reconcile them or note the differences.

Build-time scanning can surface unresolved issues as a prioritized remediation queue:

```
Unresolved Issues for Corpus/g8board:
  critical: 2 sources (both remediable via wayback_snapshot)
  major: 8 sources (5 missing_media, 3 partial_content)
  minor: 15 sources
```

### 3.6 Source Relations

Normalized sources can declare explicit relationships to other sources. These capture **intrinsic relationships** — objective facts about the source that are evident at normalization time. A forum post linked to another thread. A novel is the sequel to another novel. A revised TSB supersedes an earlier one. These are unchallengeable observations captured when the material is being read.

```yaml
relations:
  - type: "sequel_to"
    source_id: "FHBT.0001"            # Dune Messiah is a sequel to Dune
  - type: "reply_to"
    source_id: "G8BD.0038"            # this forum post replies to that thread
  - type: "adaptation_of"
    source_id: "FHBT.0001"            # Villeneuve screenplay adapts the novel
  - type: "supersedes"
    source_id: "GTSB.0004"            # revised TSB replaces an earlier one
  - type: "references"
    unresolved: "GM TSB #PI0597B"      # cross-origin reference not yet resolved
```

**Relation types:**

| Type | Meaning | Example |
|------|---------|---------|
| `sequel_to` | Next in a sequence | Dune Messiah → Dune |
| `preceded_by` | Previous in a sequence | Dune → Dune Messiah |
| `reply_to` | Direct response to another source | Forum reply → parent thread |
| `references` | Explicitly cites or links to | Forum post → TSB it mentions |
| `adaptation_of` | Creative adaptation of source material | Screenplay → novel |
| `supersedes` | Replaces or updates | Revised TSB → original TSB |
| `contradicts` | Explicitly disagrees with | One forum post refuting another |

**Cross-origin references** are particularly valuable. A g8board post may reference a GM TSB that lives in a different origin repo. At normalization time, the referenced source's ID may not be known yet. The `unresolved` field captures the reference in human-readable form. As the origin ecosystem grows, a periodic reconciliation pass can attempt to resolve these against all known source IDs.

**Discovered relationships** — connections identified during synthesis rather than present in the source itself ("this post describes the same failure mode as that manual section") — belong in the compendium layer, not source frontmatter. Source relations are strictly what the source itself declares or implies.

#### 3.6.1 Origin Discovery via Relations

Source relations serve as a **dependency discovery mechanism** for compendiums. When building a compendium, a build-time analysis can scan all `relations` across filtered sources, collect every `source_id` prefix that points to an origin not currently declared as a dependency, and surface it as a recommendation:

```
Origin Dependency Analysis for Compendium/commodore-ve:
  Currently declared: G8BD (g8board), GMOT (gm)

  Referenced but not included:
    LSTK (ls1tech)         — 15 sources reference this origin
    HLDN (holden)          — 3 sources reference this origin
    PFRM (performanceforums) — 4 sources reference this origin

  Unresolved references:
    "GM TSB #PI0597B"      — referenced by 8 sources
    "Holden WSM Section 4" — referenced by 3 sources
```

This turns the relation graph into an organic growth signal — the sources themselves tell you which origins you should be pulling in. The more references to a missing origin, the stronger the signal that including it would improve synthesis quality.

### 3.7 Exotic Origin Types

The origin-as-repo pattern supports any source type. The only requirement is an ingestion pipeline that produces normalized markdown with frontmatter.

**YouTube channels:** A transcription pipeline (e.g., Whisper) processes each video into a markdown file. For visual content, descriptive frames or AI-generated visual descriptions can supplement the transcript. Each video is one source file.

```yaml
---
source_id: "ENEX.0017"
title: "Engineering Explained — Why Direct Injection Causes Carbon Buildup"
summary: "Technical explainer covering the mechanism by which direct injection engines accumulate carbon deposits on intake valves, why port injection doesn't have this problem, and what solutions exist including walnut blasting and dual injection systems."
source_type: "video"
credibility_tier: "expert"
tags: ["engine", "direct-injection", "carbon-buildup", "intake-valves", "fuel-system"]
raw_sources: ["transcript.json", "frames.zip"]
ingestion_date_first: "2026-02-01"
ingestion_date_last: "2026-02-01"
content_changed_last: "2026-02-01"
normalization_confidence: 0.85
normalization_model: "whisper-large-v3"
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

**Authors (fiction):** Each work is normalized into one or more source files — a short story as one file, a novel potentially split into chapters. The primary text is `authoritative` credibility. Introductions, afterwords, and interviews are tagged separately.

**Podcasts:** Similar to YouTube — transcription pipeline, one episode per source file, tagged by topics discussed.

**Government / institutional sources:** PDFs, reports, and policy documents normalized via PDF extraction. Each document is one source file.

---

## 4. Compendium Synthesis

### 4.1 The Synthesis Process

Synthesis transforms tagged source material from multiple origins into a coherent, structured compendium. This is the core intellectual work of the system.

The process for each compendium:

1. **Resolve corpora.** Run `resolve.sh` to clone/update all declared origin dependencies at their pinned commits.
2. **Filter by tags.** Scan all source files across all corpora. Select those whose tags match the compendium's scope criteria (defined in `compendium.toml`).
3. **Assess summaries.** Read the `summary` field of each filtered source to understand its scope and relevance without loading full content. Prioritize sources by credibility tier and relevance to the chapter being synthesized.
4. **Organize by taxonomy.** Group filtered sources by the compendium's chapter structure.
4. **Synthesize chapters.** Distill the grouped sources into coherent prose, reconciling conflicts, identifying patterns, and citing source IDs.
5. **Build navigation.** Generate/update `SUMMARY.md`, cross-references, and supplementary sections (FAQ, glossary, quick reference).
6. **Build output.** Run mdBook to compile the manuscript into the published static site.

### 4.2 Corpus Configuration

Each compendium repo contains a `compendium.toml` that defines its scope:

```toml
[compendium]
name = "Dune Universe Compendium"
description = "Comprehensive reference for the Dune universe across all media"

# Default tag filters — sources must match at least one to be included
[[compendium.filters]]
require_any = ["dune", "arrakis", "bene-gesserit", "fremen", "spice-melange"]

# Per-origin declarations with pinned commits and optional filter overrides
[[compendium.corpora]]
name = "scifi-channel-dune"
repo = "corpus/scifi-channel-dune"
commit = "f7e8d9c"
sparse = ["normalized/", "assets/", "origin.toml"]
include_all = true          # every source in this origin is relevant

[[compendium.corpora]]
name = "frank-herbert"
repo = "corpus/frank-herbert"
commit = "b2c3d4e"
sparse = ["normalized/", "assets/", "origin.toml"]
require_any = ["dune"]      # only Dune-related works from this author

[[compendium.corpora]]
name = "denis-villeneuve"
repo = "corpus/denis-villeneuve"
commit = "c3d4e5f"
sparse = ["normalized/", "assets/", "origin.toml"]
require_any = ["dune"]      # only Dune-related screenplays
```

Because `author` is a canonical term tag (see section 5.7), compendium configuration can also filter by author directly using `match_author`:

```toml
[[compendium.corpora]]
name = "nyt"
repo = "corpus/nyt"
commit = "d4e5f6a"
sparse = ["normalized/", "assets/", "origin.toml"]
match_author = "ryan-grimm"          # only his articles from the NYT

[[compendium.corpora]]
name = "the-intercept"
repo = "corpus/the-intercept"
commit = "e5f6a7b"
sparse = ["normalized/", "assets/", "origin.toml"]
match_author = "ryan-grimm"          # only his articles from The Intercept
```

Tag-based filters and author-based filters can be combined. A source matches if it satisfies either condition:

```toml
[[compendium.corpora]]
name = "nyt"
repo = "corpus/nyt"
commit = "d4e5f6a"
sparse = ["normalized/", "assets/", "origin.toml"]
require_any = ["economics", "federal-reserve"]
match_author = "ryan-grimm"
# Source matches if it satisfies EITHER condition
```

### 4.3 Synthesis Principles

- **Cite sources.** Every factual claim in the compendium references the source ID(s) it derives from. The reader (human or agent) can always trace a claim back to a specific file in a specific origin.
- **Represent disagreement.** When the service manual says one thing and 30 forum posts say another, the compendium captures both positions with their respective credibility tiers.
- **Aggregate patterns.** If 40 forum posts describe the same failure mode, the compendium entry reflects the pattern (common mileage range, symptoms, root cause) rather than citing each post individually.
- **Respect credibility tiers.** Higher-tier sources carry more weight in synthesis. An `authoritative` source is not overruled by `anecdotal` reports unless the volume and consistency of community experience is overwhelming.
- **Structure for navigation.** Chapters follow the domain's natural taxonomy. Each chapter is self-contained but cross-references related chapters.
- **Leverage source relations.** When sources declare explicit relationships (`contradicts`, `supersedes`, `references`), the synthesis step should incorporate these signals. A source that `contradicts` another is a flag for the compendium to present both positions. A TSB that `supersedes` an earlier one means the earlier guidance may be outdated.
- **Respect source issues.** Sources with unresolved `critical` or `major` issues should be weighted accordingly. A source flagged with `missing_media` of `major` severity may be missing key visual information. The compendium can still use it but should note the gap rather than treating the source as complete.

### 4.4 Versioning

Git provides version control at both layers:

- **Origin repos** track when sources were added or corrected. The full history of normalization is preserved.
- **Compendium repos** track when synthesis was performed, what changed, and which origin versions were used. Because `compendium.toml` pins each origin to a specific commit, compendium builds are reproducible.

---

## 5. Term Registry

### 5.1 Overview

The Term Registry is a system-wide controlled vocabulary that provides canonical identification for all named entities and descriptors across Athenaeum. It ensures that when two sources reference the same person, organization, vehicle, component, or concept, they use the same term — even if those sources were normalized months apart by different models from different origins.

Without a registry, identification degrades into freeform text matching: `"Ryan Grimm"`, `"ryan-grimm"`, `"R. Grimm"`, and `"grimm-ryan"` all refer to the same person but are invisible to any automated system. The registry solves this by establishing canonical terms with rich metadata, supporting disambiguation of concepts that share surface forms, and enforcing that all frontmatter always uses the correct canonical term.

Every tag used in the system — from specific entities like `l76-engine` to descriptors like `diagnosis` — is a registered term. Terms describe sources. Terms also describe other terms. The registry is a single flat namespace with no imposed hierarchy.

The registry sits alongside the Corpus and Compendium organizations as a foundational Athenaeum component. Every origin's normalization process reads from it and proposes additions to it.

### 5.2 Disambiguation Philosophy

The term registry defines precise coordinates in concept space, not opinions. A term's job is to refer to exactly one thing unambiguously. When a natural-language word or phrase refers to genuinely different things depending on context, it cannot be a term on its own — it requires disambiguation.

This is not about controversy. It's about precision. `palestine` is not a valid term because it is ambiguous — it refers to different geopolitical realities depending on the era and context. `palestine-pre1948` and `palestine-current` are valid terms because each refers to exactly one thing. Both can have "Palestine" as a colloquial name because that *is* what people call them. The canonical term is the precise coordinate. The names are how humans refer to it.

The same principle applies everywhere:

- `mercury` is ambiguous (planet, element, Roman god, car brand). `mercury-planet`, `mercury-element`, `mercury-roman-deity`, `mercury-automobile` are precise.
- `dod` is ambiguous (Displacement on Demand, Department of Defense). `afm-dod` and `dod-department-of-defense` are precise.
- `jaguar` is ambiguous (animal, car brand). `jaguar-animal` and `jaguar-automobile` are precise.

Not every term needs disambiguation. `ryan-grimm` is unambiguous — there is one person being referred to. `l76-engine` is unambiguous — there is one engine. Disambiguation is only required when a surface form genuinely maps to multiple distinct concepts.

The iterative nature of the registry means disambiguation improves over time. A term that seemed unambiguous may later be discovered to refer to two things, at which point it gets split and reconciled. The registry is a living document that gets more precise with use.

### 5.3 Core Principle

**The frontmatter is the source of truth. The registry is the authority. They must always agree.**

There is no alias resolution, no runtime translation, no indirection layer. Every tag in every source file's frontmatter is the current canonical form as defined by the registry. If a tag is found to be incorrect — because two entities were confused, or because a tag was superseded by a better canonical form — the affected frontmatter is rewritten. The old form ceases to exist in the system.

### 5.4 Term Structure

Each term in the registry has:

#### Canonical Tag

The single authoritative identifier used in all frontmatter. Follows the same format as regular tags — lowercase, hyphenated, concise:

- `ryan-grimm`
- `general-motors`
- `pontiac-g8`
- `l76-engine`
- `rear-wheel-bearing`

#### Term Type

There is no type enum. Instead, each term is described by **descriptor tags** — the same tags used to describe source content. A term's "type" emerges from its tags rather than being assigned from a closed taxonomy:

- `ryan-grimm` is tagged `person`, `journalist`, `political-reporter`
- `general-motors` is tagged `organization`, `manufacturer`, `automotive`
- `l76-engine` is tagged `component`, `engine`, `v8`, `gen-iv`
- `dune-novel` is tagged `work`, `novel`, `science-fiction`
- `pontiac-g8` is tagged `vehicle`, `sedan`, `rear-wheel-drive`

This avoids the taxonomy problem that a closed enum creates — where you'd inevitably encounter something that doesn't fit neatly into `person` vs. `organization` vs. `concept` and end up debating categories instead of describing things.

Descriptor tags that describe terms (like `person`, `organization`, `vehicle`, `component`) are themselves registered terms in the same registry. Terms describe terms. The system is self-referential and flat.

#### Names

The colloquial representations of the term — how humans refer to it in natural language. A term can have multiple names because the same concept is often referred to differently in different contexts:

```toml
# l76-engine.toml

canonical = "l76-engine"
names = ["L76", "L76 6.0L V8", "6.0 V8", "L76 engine"]
tags = ["component", "engine", "v8", "gen-iv", "gm"]
description = "GM Gen IV 6.0L V8 with Active Fuel Management (AFM/DoD), used in 2008-2009 Pontiac G8 GT and various GM trucks. Shares architecture with LS2 but adds cylinder deactivation."
```

The `names` field serves the normalization pipeline — when Pass 1 produces a raw tag or encounters a reference in source text, the resolution step checks which terms have matching entries in their `names` array, then uses source context to determine which specific term is intended.

Multiple terms sharing a name is expected and is the core mechanism for disambiguation:

```toml
# palestine-current.toml

canonical = "palestine-current"
names = ["Palestine", "State of Palestine", "Occupied Palestinian Territories", "OPT"]
tags = ["location", "state", "middle-east"]
description = "The occupied territories comprising the Gaza Strip and the West Bank, including East Jerusalem. Recognized as a state by the UN General Assembly in 2012."

[[relations]]
type = "contains"
target = "gaza-strip"

[[relations]]
type = "contains"
target = "west-bank"
```

```toml
# palestine-pre1948.toml

canonical = "palestine-pre1948"
names = ["Palestine", "Mandatory Palestine", "British Palestine"]
tags = ["location", "historical-territory", "middle-east"]
description = "The geographic region of Palestine as defined by pre-1948 borders, encompassing the territory of the British Mandate for Palestine (1920-1948)."
```

Both terms have "Palestine" as a name. When a source refers to "Palestine," the resolution step examines the source context to determine which term applies. An article about Ottoman-era agriculture resolves to `palestine-pre1948`. A report on current humanitarian conditions resolves to `palestine-current`. The source context drives the resolution, not an editorial default.

#### Description

A precise, objective explanation of what the term refers to. The description serves two purposes:

1. **Normalization guidance** — gives the model enough context to correctly match source content to the right term and to improve normalization quality during the enrichment pass
2. **Human disambiguation** — lets a reviewer quickly understand what a term means when resolving conflicts or reviewing proposals

Descriptions should be factual and specific enough that two reasonable people would agree on whether a given reference matches the term.

When terms share similar surface forms, the description carries the disambiguation:

```toml
# mercury-planet.toml

canonical = "mercury-planet"
names = ["Mercury"]
tags = ["location", "planet", "solar-system"]
description = "The smallest planet in the Solar System and closest to the Sun, with an orbital period of approximately 88 Earth days."
```

```toml
# mercury-element.toml

canonical = "mercury-element"
names = ["Mercury", "quicksilver", "Hg"]
tags = ["element", "chemical", "metal"]
description = "Chemical element with atomic number 80, a heavy silvery liquid metal at room temperature. Symbol Hg from Latin hydrargyrum."
```

#### Entity Relations

Entities can declare relationships to other entities. These are distinct from source relations — they describe how entities relate to each other in the real world:

| Relation | Description | Example |
|----------|-------------|---------|
| `writes_for` | Person publishes through this outlet | `ryan-grimm` → `the-intercept` |
| `manufactures` | Organization produces this product | `general-motors` → `pontiac-g8` |
| `subsidiary_of` | Organization owned by another | `holden` → `general-motors` |
| `component_of` | Part belongs to a system or vehicle | `l76-engine` → `pontiac-g8` |
| `variant_of` | One entity is a variant of another | `holden-ve-commodore` → `pontiac-g8` |
| `sequel_to` | Creative work follows another | `dune-messiah-novel` → `dune-novel` |
| `adaptation_of` | One work adapts another | `dune-2021-film` → `dune-novel` |
| `member_of` | Person belongs to organization | `frank-herbert` → `sfwa` |

These relations are informational — they help agents and synthesis understand context. They are not used for filtering or scoping.

### 5.5 Registry Format

The registry lives in its own repository as a flat collection of TOML files — one file per term. Every registered term, whether it represents a specific entity like `ryan-grimm` or a descriptor like `person`, gets its own file:

```
example-org/term-registry/
├── registry.toml                    # registry metadata and configuration
├── tags/
│   ├── afm-dod.toml
│   ├── article.toml                 # descriptor
│   ├── automotive.toml              # descriptor
│   ├── brian-herbert.toml
│   ├── component.toml               # descriptor
│   ├── descriptor.toml              # descriptor
│   ├── detroit.toml
│   ├── diagnosis.toml               # descriptor
│   ├── diy.toml                     # descriptor
│   ├── dune-novel.toml
│   ├── engine.toml                  # descriptor
│   ├── frank-herbert.toml
│   ├── g8board.toml
│   ├── general-motors.toml
│   ├── holden.toml
│   ├── holden-ve-commodore.toml
│   ├── how-to.toml                  # descriptor
│   ├── journalist.toml              # descriptor
│   ├── l76-engine.toml
│   ├── ls1tech.toml
│   ├── ls2-engine.toml
│   ├── manufacturer.toml            # descriptor
│   ├── novel.toml                   # descriptor
│   ├── organization.toml            # descriptor
│   ├── penrite.toml
│   ├── person.toml                  # descriptor
│   ├── pontiac-g8.toml
│   ├── r-mechanicadvice.toml
│   ├── rear-wheel-bearing.toml
│   ├── ryan-grimm.toml
│   ├── t56-transmission.toml
│   ├── troubleshooting.toml         # descriptor
│   ├── vehicle.toml                 # descriptor
│   └── work.toml                    # descriptor
└── proposals/
    └── pending/
        └── 2026-02-09_G8BD.0200.toml
```

There is no organizational hierarchy in the directory structure. No `persons/` or `components/` subdirectories. The terms themselves carry that information — `ryan-grimm.toml` is tagged `person`, `journalist`. The filesystem is flat; the taxonomy lives in the term metadata.

#### Term File Format

Every registered term — entity or descriptor — uses the same file format:

```toml
# ryan-grimm.toml

canonical = "ryan-grimm"
names = ["Ryan Grimm", "Ryan Grim"]
tags = ["person", "journalist", "political-reporter"]
description = "Investigative journalist, formerly at The Intercept and HuffPost. Covers political power structures and progressive politics."

[[relations]]
type = "writes_for"
target = "the-intercept"
```

```toml
# general-motors.toml

canonical = "general-motors"
names = ["General Motors", "GM"]
tags = ["organization", "manufacturer", "automotive"]
description = "American multinational automotive manufacturer. Parent company of Chevrolet, Pontiac (discontinued), GMC, Buick, and Cadillac."

[[relations]]
type = "manufactures"
target = "pontiac-g8"

[[relations]]
type = "subsidiary_of"
target = "holden"
note = "Holden was a GM subsidiary until 2020"
```

```toml
# l76-engine.toml

canonical = "l76-engine"
names = ["L76", "L76 6.0L V8", "6.0 V8", "L76 engine"]
tags = ["component", "engine", "v8", "gen-iv", "gm"]
description = "GM Gen IV 6.0L V8 with Active Fuel Management (AFM/DoD), used in 2008-2009 Pontiac G8 GT and various GM trucks. Shares architecture with LS2 but adds cylinder deactivation."

[[relations]]
type = "component_of"
target = "pontiac-g8"

[[relations]]
type = "variant_of"
target = "ls2-engine"
```

Descriptor tags have simpler entries but the same format:

```toml
# person.toml

canonical = "person"
names = ["person"]
tags = []
description = "A specific individual human being."
```

```toml
# journalist.toml

canonical = "journalist"
names = ["journalist"]
tags = ["person"]
description = "A person who investigates, writes, and reports news or information for publication."
```

```toml
# diagnosis.toml

canonical = "diagnosis"
names = ["diagnosis", "diagnostic"]
tags = ["descriptor"]
description = "Content focused on identifying the cause of a problem or fault."
```

Note that descriptor terms can themselves have tags. `journalist` is tagged `person` because every journalist is a person — this captures the relationship without imposing a rigid hierarchy. A normalization model or query tool can traverse these relationships to understand that filtering for `person` should include terms tagged `journalist`.

### 5.6 Two-Pass Normalization Pipeline

The term registry integrates into normalization through a two-pass process. The first pass is isolated — the model works with only the raw source material. The second pass is enriched — the model has registry context and can improve its output.

#### Pass 1: Isolated Normalization

The model normalizes the source with no registry context. It produces:

- The normalized markdown content
- Frontmatter with all required fields
- A set of **raw tags** based purely on what it observes in the source material

These raw tags are the model's best-effort identification of entities and descriptors from the source alone. They may be ambiguous (`dod` could mean Active Fuel Management's Displacement on Demand or the Department of Defense), inconsistent with existing conventions (`6.0-v8` when the registry uses `l76-engine`), or novel (an entity the registry has never seen).

The raw tags are not written to the final frontmatter. They are an intermediate output.

#### Tag Resolution

Each raw tag from Pass 1 is compared against the registry:

1. **Exact match** — the raw tag matches a canonical tag in the registry. Use the canonical tag.

2. **Semantic match** — the raw tag doesn't match exactly but clearly refers to a registered entity (e.g., raw tag `6.0-v8-afm` clearly maps to registered entity `l76-engine`). The resolution process identifies the correct canonical tag. High-confidence matches can be automated; lower-confidence matches are flagged for human review.

3. **Ambiguous match** — the raw tag could refer to multiple registered entities (e.g., `dod` could map to both `afm-dod` and `dod-department-of-defense`). Flagged for human review with the source context to determine which entity is intended.

4. **No match** — the raw tag doesn't correspond to any registered term. Two possibilities:
   - It's a **new entity** that should be registered → goes to the proposal queue
   - It's a **new descriptor** that should be registered → goes to the proposal queue (descriptors are terms too)

After resolution, the frontmatter is populated with correct canonical entity tags plus any descriptor tags.

#### Pass 2: Enriched Normalization

With tags now resolved, the model re-normalizes with the registry metadata for each matched entity as additional context. The model now knows:

- `l76-engine` is a "GM Gen IV 6.0L V8 with AFM/DoD"
- `pontiac-g8` is a specific vehicle platform
- `afm-dod` is the "Active Fuel Management / Displacement on Demand" cylinder deactivation system

This richer understanding improves:

- **Summary quality** — the model can write more precise, technically accurate summaries
- **Tag completeness** — the model may identify additional relevant entities now that it understands the domain context (e.g., recognizing that a discussion about "cylinder deactivation problems" should also be tagged with `afm-dod`)
- **Normalization quality** — the model can better structure the content, resolve ambiguous references in the source text, and produce a more useful normalized document

#### Term Proposals

Any raw tag from Pass 1 that didn't resolve to a registry entry is emitted as a proposal — whether it appears to represent a specific entity or a descriptor:

```toml
# proposals/pending/2026-02-09_G8BD.0200.toml

[[proposals]]
proposed_by = "G8BD.0200"
proposed_tag = "4l60e-transmission"
proposed_tags = ["component", "transmission", "gm"]
proposed_names = ["4L60E", "4L60E transmission"]
context = "GM 4-speed automatic transmission discussed in rebuild procedure"
confidence = 0.95

[[proposals]]
proposed_by = "G8BD.0200"
proposed_tag = "tremec-t56"
proposed_tags = ["component", "transmission", "manual-transmission"]
proposed_names = ["T56", "Tremec T56", "T56 6-speed"]
context = "Tremec 6-speed manual transmission option in the Pontiac G8 GXP, discussed in context of swap into GT models"
confidence = 0.95
```

Proposals are reviewed by a human. Approved proposals become term files in the registry. Rejected proposals are discarded.

#### Pipeline Summary

```
Raw Source
    ↓
Pass 1: Isolated normalization (no registry context)
    → normalized content + raw tags
    ↓
Tag Resolution: Match raw tags against registry
    → canonical terms (matched)
    → proposals (unresolved → registration queue)
    → ambiguous (flagged for human review)
    ↓
Pass 2: Enriched normalization (with registry metadata)
    → improved content, summary, and tags
    ↓
Final normalized source file (written to normalized/)
```

### 5.7 Author Field vs. Username Field

The `author` field in source frontmatter is reserved for real, identifiable people. It uses canonical term tags:

```yaml
# Correct — identifiable person, registered term
author: "ryan-grimm"

# For multiple authors
authors: ["frank-herbert", "brian-herbert"]
```

For sources where the author is an anonymous or pseudonymous handle (forum posts, Reddit posts, etc.), the `author`/`authors` field is omitted entirely. Instead, the relevant extended schema provides a **`username`** field that stores the exact username of the poster as a plain string:

```yaml
# forum_post extended fields
username: "TorqueDave"
thread_url: "https://www.g8board.com/forum/thread-12345"
```

```yaml
# reddit_post extended fields
username: "LS_Swapper_9000"
subreddit: "r-pontiacg8"
post_url: "https://reddit.com/r/PontiacG8/comments/abc123"
```

The `username` field:
- Stores the exact handle as it appears on the platform
- Is a plain string, not a term registry reference
- Is not disambiguated, reconciled, or tracked as an entity
- Exists purely for provenance — "who posted this on the platform"

This avoids the rabbit hole of trying to track and disambiguate pseudonymous internet users across platforms. If a forum poster is later identified as a real person (e.g., a known mechanic or engineer who posts under their real name), the `author` field can be added with their registered term and the `username` field retained for platform provenance.

### 5.8 Reconciliation

Reconciliation is the process of correcting frontmatter when the registry changes. It is not optional and is not deferred. When the registry changes, affected frontmatter is rewritten immediately. Old forms cease to exist.

#### Merge (Two Tags → One)

When two canonical tags are determined to represent the same entity:

1. **Decide canonical form.** Choose the more descriptive or established tag.
2. **Remove the retired entry** from the registry entirely. It does not become an alias. It is gone.
3. **Rewrite all frontmatter.** Automated pass scans every origin for the retired tag in any frontmatter field (`tags`, `author`/`authors`, or any extended field) and replaces it with the surviving canonical tag.
4. **Commit changes.** Each affected origin gets a reconciliation commit.

The retired tag ceases to exist anywhere in the system. Future normalization will not produce it because:
- Pass 1 may still produce the old surface form as a raw tag
- But tag resolution will semantically match it to the surviving canonical form, informed by the richer metadata now present on that entity
- If the old form keeps appearing from Pass 1 and failing resolution, that's a signal the registry description should be improved to enable more reliable matching

#### Split (One Tag → Two)

When a single term is found to represent two different concepts:

1. **Create two distinct entries.** E.g., `mercury-planet` and `mercury-element`.
2. **Remove the ambiguous entry** from the registry.
3. **Classify affected sources.** Determine which concept each source actually references. This requires human review — the automated system flags the sources, a human assigns them.
4. **Rewrite all frontmatter.** Replace the old term with the correct disambiguated term in each affected source file.

Split reconciliation is more invasive than merge reconciliation and always requires human judgment.

#### Rename (Tag → Better Tag)

When a canonical tag should be renamed for clarity:

1. **Update the registry entry** with the new canonical tag.
2. **Rewrite all frontmatter** containing the old tag.
3. The old form ceases to exist.

#### Build-Time Validation

Every build should verify consistency:

- Every tag in source frontmatter has a corresponding `.toml` file in the term registry
- No frontmatter contains a tag that was retired through merge, split, or rename
- Every `author`/`authors` field value is a registered term tagged `person` (forum/reddit posts use `username` instead, which is not validated against the registry)
- Every tag referenced in a term file's `tags` array has its own term file in the registry
- Every `relations` target references a term that exists in the registry

### 5.9 Unified Term Namespace

All terms — whether they represent specific entities like `ryan-grimm` or descriptors like `diagnosis` — live in the same flat registry and follow the same format. There is no formal distinction between "entity terms" and "descriptor terms" at the system level. Every term is just a term.

In practice, terms naturally fall along a spectrum:

**Specific entities** have rich descriptions, relations to other terms, and tend to be unique proper nouns:
- `ryan-grimm` — a specific person with a career history, publications, and affiliations
- `l76-engine` — a specific component with technical specifications and vehicle applications
- `pontiac-g8` — a specific vehicle with model years, platforms, and manufacturer relations

**Descriptors** have simpler entries and describe qualities, activities, or categories:
- `diagnosis` — content focused on identifying problems
- `how-to` — step-by-step procedural content
- `person` — the concept of being a human individual

**Meta-descriptors** are descriptors that primarily exist to describe other terms:
- `person`, `organization`, `vehicle`, `component` — these describe what kind of entity a term represents
- `descriptor` — terms that describe content qualities rather than specific entities

This spectrum is not enforced by the system. It emerges naturally from how terms are used. The registry treats them all identically.

### 5.10 Reconciliation Reporting

A periodic reconciliation scan validates consistency across the system:

```
Term Registry Reconciliation Report:

  Retired terms found in frontmatter (reconciliation failures):
    "displacement-on-demand" found in G8BD.0150, G8BD.0203
    Action: automated rewrite required — this term no longer exists, use "afm-dod"

  Potential duplicates (similar terms, not yet investigated):
    ls2-engine / ls2 — both tagged [component, engine], both in automotive origins
    Action: human review to determine if these are the same term

  Ambiguous surface forms from recent normalization:
    "dod" produced by G8BD.0200 (resolved → afm-dod)
    "dod" produced by USGV.0015 (resolved → dod-department-of-defense)
    Status: correctly disambiguated

  Unresolved proposals: 12
    3 high-confidence (>0.9) — likely auto-approvable
    6 medium-confidence (0.7-0.9) — need review
    3 low-confidence (<0.7) — may be false identification

  Unregistered tags (in frontmatter, no matching file in registry): 4
    "mystery-component" — used in G8BD.0150
    Action: create term file or correct to existing term
```

### 5.11 Registry Scope and Growth

The registry starts small and grows organically through normalization:

1. **Bootstrap from existing origins.** Normalize existing sources, let Pass 1 produce raw tags, resolve and register them.
2. **Grow with each normalization.** New sources produce proposals for entities the registry hasn't seen.
3. **Cross-origin signal.** When the same entity appears across multiple origins, that reinforces confidence in the registration. An entity referenced by 5 origins is well-established.
4. **Compendium-driven demand.** Building a new compendium may reveal entities that need registration to enable proper filtering.

The registry doesn't need to be complete before normalization begins. Pass 1 operates without registry context. Tag resolution handles what the registry knows, and proposals capture what it doesn't. The system is functional from day one and improves as the registry grows.

### 5.12 Infrastructure Placement

The term registry is system-wide infrastructure, consumed by both the Corpus and Compendium layers but owned by neither. It lives in the `example-org` Forgejo organization alongside other Athenaeum system infrastructure:

```
example-org/athenaeum/                # spec, tooling, reconciliation scripts
example-org/term-registry/            # controlled vocabulary
corpus/gm/                          # origin repos
corpus/g8board/
compendium/commodore-ve/            # compendium repos
compendium/dune/
```

The `example-org` org contains the things that make Athenaeum work — system-level infrastructure, specifications, and tooling. The `corpus` and `compendium` orgs contain the things Athenaeum operates on. The term registry is plumbing, not content.

The registry is accessed by normalization tooling via Forgejo API or by cloning the repo. It does not need to be submoduled into every origin — the normalization pipeline reads it as an external dependency.

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
| **Sources** | Master registry of all origins and sources with credibility tiers |

### 6.3 Navigation Aids

The `SUMMARY.md` file serves as both the mdBook table of contents and the agent's navigation map. It provides hierarchical structure down to the section level.

mdBook also generates a `searchindex.json` file at build time that provides full-text search across all pages. This serves as the compendium's index — mapping keywords, part numbers, symptoms, and any other terms to the sections where they appear. See section 10.2 for how the agent leverages this.

### 6.4 Compendium Page Frontmatter

mdBook supports YAML frontmatter on pages — it ignores it during rendering, which makes it ideal for metadata that tooling and agents can read without polluting the HTML output. Every compendium chapter page carries synthesis provenance and per-source traceability:

```yaml
---
chapter_id: "suspension.wheel-bearings.rear"
title: "Rear Wheel Bearings"
synthesis_model: "claude-opus-4-5-20250630"
synthesis_date: "2026-02-08"
last_reviewed: "2026-02-08"
sources:
  - source_id: "G8BD.0042"
    synthesized_at: "2026-01-20"
    credibility_tier: "community_validated"
  - source_id: "G8BD.0118"
    synthesized_at: "2026-01-15"
    credibility_tier: "community_validated"
  - source_id: "G8BD.0203"
    synthesized_at: "2026-02-01"
    credibility_tier: "anecdotal"
  - source_id: "GMSM.0034"
    synthesized_at: "2026-02-01"
    credibility_tier: "authoritative"
  - source_id: "GTSB.0012"
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
| `last_reviewed` | When the chapter was last reviewed for accuracy against current sources |
| `sources` | Per-source traceability with the `normalization_date` at time of synthesis and the source's credibility tier |
| `sources[].synthesized_at` | The source's `normalization_date` at the time this chapter was synthesized. **This is the key field for incremental synthesis** |
| `sources[].credibility_tier` | Copied from the source at synthesis time — enables credibility assessment without fetching back into the origin |

Aggregate fields like `source_count`, `origin_count`, and `credibility_summary` are derivable from the `sources` list and do not need to be stored separately.

#### 6.4.1 Incremental Synthesis

The per-source `synthesized_at` field enables precise incremental re-synthesis. When an origin's pinned commit is bumped in `compendium.toml`, the staleness check is mechanical:

```
For each chapter in manuscript/:
  For each source in chapter.sources:
    Fetch the source file from corpora/
    If source.normalization_date > chapter_source.synthesized_at:
      Flag this chapter for re-synthesis
```

A commit bump that touches 200 files (because `ingestion_date_last` was updated on a routine check) but only has real normalization changes in 3 of them results in exactly the chapters referencing those 3 sources being flagged. Everything else is untouched. This keeps re-synthesis proportional to actual change, not to ingestion activity.

The same check catches re-normalization events: if a source is re-normalized with a better model (content unchanged, but `normalization_date` and `normalization_model` updated), the compendium correctly flags that chapter for re-synthesis from the improved source material.

**Build-time validation:** The `sources` list enables a CI check that verifies every cited source ID actually resolves to a real file in the resolved corpora. This catches broken references when sources are reorganized or when a pinned commit is bumped and source IDs have changed.

**Model audit trail:** Between the `normalization_model` on source files and `synthesis_model` on compendium pages, the full model provenance chain is captured. If a model is found to produce problematic output, you can query across both layers to identify every artifact it touched and prioritize re-processing.

---

## 7. Hosting & Distribution

### 7.1 Architecture

The compendium sites are hosted on an external Caddy server (`ref.example.org`) that is independent of the home infrastructure. This provides:

> **Domain naming:** `ref.example.org` hosts published compendiums — the synthesized reference works that agents and humans browse. `corpus.example.org` is reserved for a future corpus explorer that will provide browsable access to the origin repositories and their source material.

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
        run: bash resolve.sh          # clones origins at pinned commits with sparse checkout
      - name: Install mdBook
        run: |
          # install or use cached mdBook binary
      - name: Build
        run: mdbook build
      - name: Deploy
        run: |
          rsync -avz --delete book/ deploy@caddy-vps:/srv/ref/${GITHUB_REPOSITORY##*/}/
```

The `resolve.sh` script (see section 2.2.1) clones each declared origin at its pinned commit with sparse checkout, pulling only `normalized/`, `assets/`, and `origin.toml`. This keeps CI fast even as origin repos grow large with ingested source material.

### 8.4 Origin Update Propagation

When new sources are added to an origin repo, the compendiums that reference it don't automatically rebuild. This is intentional — synthesis is a curated process. The workflow is:

1. New sources are committed to the origin repo (e.g., `Corpus/g8board`)
2. The compendium maintainer bumps the pinned commit hash in `compendium.toml` when ready to incorporate new material
3. New synthesis is performed incorporating the new sources
4. Push triggers the build and deploy pipeline

For origins with high ingestion velocity, this can be automated with a scheduled workflow that bumps pinned commits periodically.

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
4. **Synthesize a response.** Answer the question based on the retrieved compendium content, citing specific sources where the compendium provides them.
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

### 11.1 Adding a New Origin

1. Create a new repository under the Corpus organization
2. Add `origin.toml` with the registration metadata, source ID prefix, and reingest configuration
3. Add `manifest.toml` and populate it with known sources (both `captured` and `pending`)
4. Create the `normalized/`, `assets/`, and `ingested/` directories
5. Build or configure the ingestion pipeline appropriate to the source type
6. Begin normalizing source material with rich frontmatter tags
7. The origin is now available for any compendium to declare as a dependency

### 11.2 Adding a New Compendium

1. Create a new repository under the Compendium organization
2. Declare origin dependencies in `compendium.toml` with pinned commits and tag filters
3. Create `resolve.sh` to clone corpora at pinned commits with sparse checkout (copy from template)
4. Add `corpora/` to `.gitignore`
5. Define the domain taxonomy — the chapter structure
6. Establish the standard manuscript directory structure
6. Begin the synthesis process from filtered sources
7. Add the Forgejo Actions deploy workflow (copy from template)
8. Create the agent skill with domain-specific system prompt and SUMMARY.md
9. Add deploy target to the Caddy configuration

### 11.3 Stacking Compendiums

The architecture supports compendiums of varying scope that share source material:

```
Compendium/economics/           (broad)
  corpora: marxists-org, jstor-economics, wikipedia-economics, ...
  filters: require_any = ["economics", "economic-theory", "markets", ...]

Compendium/socialism/           (focused)
  corpora: marxists-org, jstor-economics, ...
  filters: require_any = ["socialism", "marxism", "class-theory", ...]

Compendium/politics/            (broad, different lens)
  corpora: marxists-org, jstor-economics, wikipedia-politics, ...
  filters: require_any = ["political-theory", "governance", "socialism", "capitalism", ...]
```

All three compendiums reference `marxists-org` as an origin. The economics compendium pulls sources tagged with broad economic concepts. The socialism compendium pulls a narrower subset. The politics compendium pulls an overlapping but distinct set. **One source file, one location in git, zero duplication, multiple compendiums synthesizing from different perspectives.**

The same pattern applies to fiction. A "Golden Age Sci-Fi" compendium and a "Dune" compendium both declare `frank-herbert` as a dependency, but filter for different tags.

### 11.4 Domain Taxonomy Design

Each domain needs its own taxonomy — the organizational structure that chapters follow. This should be designed before significant content is ingested, though it will evolve. Guidelines:

- Follow the natural structure of the domain (for a vehicle: by system; for health: by body system; for fiction: by world element — characters, factions, locations, technology, themes, adaptations)
- Prefer 2-3 levels of hierarchy maximum
- Each leaf section should be self-contained enough to be useful when fetched in isolation
- Cross-reference liberally between related sections

### 11.5 Standardized Frontmatter Schema

The complete source frontmatter schema is defined in section 3.3. In summary:

**Universal required** (every source):
`source_id`, `title`, `summary`, `source_type`, `credibility_tier`, `tags`, `raw_sources`, `ingestion_date_first`, `ingestion_date_last`, `content_changed_last`, `normalization_confidence`, `normalization_model`, `normalization_date`

**Universal optional** (present when applicable):
`author`, `date_published`, `origin_url`, `volatility`, `relations`, `issues`

**Extended schemas** are determined by `source_type` (closed enum):

| Source Type | Required Extended Fields | Optional Extended Fields |
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
`chapter_id`, `title`, `synthesis_model`, `synthesis_date`, `last_reviewed`, `sources[]` (with `source_id`, `synthesized_at`, `credibility_tier` per source)

---

## 12. Infrastructure Summary

### 12.1 Component Map

```
┌──────────────────────────────────────────────────────────────┐
│                    Forgejo (Tailnet)                           │
│                                                                │
│  Corpus Organization               Compendium Organization     │
│  ├── g8board/                      ├── commodore-ve/           │
│  │   ├── origin.toml               │   ├── corpora/ (resolved) │
│  │   ├── manifest.toml             │   ├── manuscript/         │
│  │   ├── normalized/               │   ├── compendium.toml     │
│  │   ├── assets/                   │   └── book.toml           │
│  │   └── ingested/                 ├── dune/                   │
│  ├── frank-herbert/                ├── economics/              │
│  └── ...                           └── ...                     │
│                                                                │
│  example-org Organization (System Infrastructure)                │
│  └── term-registry/               # controlled vocabulary     │
│      ├── registry.toml             # registry metadata         │
│      ├── tags/                     # one .toml file per term   │
│      └── proposals/pending/        # unreviewed term proposals │
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
| Source organization | Forgejo org (Corpus) | One repo per origin, rich frontmatter tags |
| Compendium format | Markdown + mdBook | Human-readable source, clean output, built-in search |
| Source linkage | Declared dependencies in `compendium.toml` | Pin origins to commits, resolve at build time with sparse checkout |
| Term Registry | Flat TOML files in git | Controlled vocabulary for tags and entities |
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

## Appendix A: Example Corpus Configurations

### A.1 Commodore VE (Automotive)

```
Corpora: g8board, ls1tech, gm, holden, penrite
Taxonomy: by vehicle system (engine, drivetrain, suspension, electrical, ...)
Agent persona: Expert mechanic familiar with the VE/WM platform
```

### A.2 Dune Universe (Fiction)

```
Corpora: frank-herbert, brian-herbert, denis-villeneuve, scifi-channel-dune
Taxonomy: by world element (characters, factions, locations, technology, themes, adaptations)
Agent persona: Dune scholar with access to all canonical and adaptation material
```

### A.3 Economics (Academic)

```
Corpora: marxists-org, jstor-economics, wikipedia-economics, ...
Taxonomy: by school of thought and topic area
Agent persona: Economics professor with breadth across schools of thought
```

### A.4 Socialism (Focused Academic)

```
Corpora: marxists-org, jstor-economics (subset), ...
Filters: require_any = ["socialism", "marxism", "class-theory", ...]
Taxonomy: by theoretical framework and historical application
Agent persona: Political theory specialist focused on socialist thought
```

---

## Appendix B: Future Considerations

### B.1 Public Compendia

Some domains may be worth sharing publicly. A car compendium for a specific platform would be genuinely valuable to other owners. The per-compendium auth gateway (Phase 2) would allow individual compendiums to be toggled public while others remain private.

### B.2 Collaborative Contribution

If a compendium is made public, contributions become possible via pull requests — either to origin repos (new sources) or to compendium repos (synthesis improvements). The Forgejo PR workflow supports this naturally.

### B.3 Agent Self-Improvement Feedback Loop

When the agent encounters a question it cannot answer well (coverage gap), this could be captured as a signal to prioritize source collection in that area. The agent logs topics where it had to flag thin coverage, and those become ingestion priorities for the relevant origins.

### B.4 Multi-Format Export

The same compendium markdown could be exported to additional formats: PDF for offline reading, EPUB for e-readers, or structured JSON for programmatic access. These are build-step additions that don't affect the source material.

### B.5 Origin Ingestion Automation

As origin pipelines mature, ingestion can be increasingly automated. A forum scraper that runs on a schedule, a YouTube channel monitor that transcribes new uploads, or an RSS-triggered pipeline for new publications. The normalized output always flows into the same origin repo structure regardless of how it was triggered.
