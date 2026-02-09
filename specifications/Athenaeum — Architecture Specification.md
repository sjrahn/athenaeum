---
spec_id: ATH-ARCH
title: "Athenaeum — Architecture Specification"
version: 1.0
status: final
author: Steven Rahn
date_created: 2026-02-08
date_modified: 2026-02-09
changelog:
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

The system is organized into two Forgejo organizations that serve fundamentally different purposes.

**Terminology:** *Corpus* (plural: *corpora*) means "a body of collected texts" — this is where raw source material lives. *Compendium* means "a comprehensive collection of concise information" — this is where synthesized reference works live. *Manuscript* refers to the pre-rendered markdown that gets compiled into the published compendium.

### 2.1 Corpus Organization

The **Corpus** organization contains origin repositories — one per source of information. Each origin is a self-contained collection of normalized material from a single provenance.

```
Corpus (Forgejo Organization)
│
├── Automotive
│   ├── g8board/                  # forum posts from g8board.com
│   ├── ls1tech/                  # forum posts from ls1tech.com
│   ├── gm-service-manuals/       # official GM service manual sections
│   ├── gm-tsbs/                  # GM technical service bulletins
│   └── penrite-oils/             # product documentation
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
│   ├── gm-service-manuals/        → resolved (sparse: normalized/ + assets/ + origin.toml)
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

### 3.1 Source Registration

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

The `[reingest]` section defines the default volatility for sources in this origin and the thresholds for re-ingestion priority. Individual sources can override `default_volatility` via the `volatility` field in their frontmatter. The ingestion scanner compares each source's `ingestion_date_last` against the appropriate threshold to generate a re-ingestion priority queue.

The `source_id_prefix` ensures globally unique source IDs across all origins. Prefixes are 4 uppercase letters (allowing for 456,976 unique origin prefixes). Every normalized file in this repo will have a source ID like `G8BD.0001`, `G8BD.0042`, etc. The numeric portion is zero-padded to 4 digits, supporting up to 9,999 sources per origin. When a compendium cites `G8BD.0042`, it unambiguously resolves to a specific file in a specific origin repo.

#### 3.1.1 Origin Repository Layout

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

#### 3.1.2 Source Manifest

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

**The manifest is not for cross-origin references.** If a g8board post mentions a GM TSB, that reference is recorded as an `unresolved` relation in the source's frontmatter — not as a manifest entry in g8board. The TSB belongs in the `gm-tsbs` origin and would be registered there when that origin is created.

**Build-time validation:**

- Every `captured` entry in manifest must have a corresponding file in `normalized/`
- Every file in `normalized/` must have a `captured` entry in manifest
- No `pending`, `deferred`, or `unavailable` source should have a file in `normalized/`

**Ingestion backlog reporting:**

```
Ingestion Backlog:
  Corpus/frank-herbert:     6 captured, 8 pending (2 high, 3 medium, 3 low), 2 deferred, 1 unavailable
  Corpus/g8board:          42 captured, 156 pending (12 critical, 45 high, 99 medium), 3 deferred
  Corpus/gm-service-manuals: 15 captured, 60 pending (20 high, 40 medium)
```

### 3.2 Normalized Source Format

Every normalized source file is a single markdown document with structured YAML frontmatter. The frontmatter follows a rigid schema: a set of universal fields present on every source, plus extended fields determined by the `source_type`. This consistency enables tooling to validate, query, and compare sources across any origin.

#### 3.2.1 Universal Required Fields

Every source file must include all of these fields, no exceptions:

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | string | `XXXX.####` globally unique identifier (4-letter origin prefix + 4-digit number) |
| `title` | string | Short descriptive label for the source file (not necessarily the work's canonical title) |
| `summary` | string | One-to-three sentence description of what this source contains and why it's useful. Generated during normalization. Enables synthesis-time relevance assessment without reading the full content |
| `source_type` | enum | Declares which extended schema applies. See section 3.2.4 for valid types |
| `credibility_tier` | enum | `authoritative`, `expert`, `community_validated`, `anecdotal`, `speculative`. See section 3.3 |
| `tags` | string[] | Objective content descriptors for filtering and scoping. See section 3.2.2 |
| `raw_sources` | string[] | Filenames in `ingested/{source_id}/` this was normalized from. Preserves traceability to original artifacts |
| `ingestion_date_first` | date | When this source was originally captured |
| `ingestion_date_last` | date | When we last checked/re-ingested from the upstream source (same as `ingestion_date_first` on initial capture) |
| `content_changed_last` | date | When the upstream content last actually differed from what we had. Used by the ingestion layer to assess source stability |
| `normalization_confidence` | float | `0.0`–`1.0`, quality of the conversion process. See section 3.3.1 |
| `normalization_model` | string | Model or tool that performed normalization (e.g., `claude-sonnet-4-5-20250514`, `whisper-large-v3`) |
| `normalization_date` | date | When normalization was last performed. **This is the field the compendium layer compares against to determine if re-synthesis is needed** — it captures both content changes and re-normalization with improved models |

#### 3.2.2 Tags

Tags are objective descriptors of what the source discusses — not where it should be used. Good tags describe the content's topics, subjects, entities, and concepts. The same source can be relevant to multiple compendiums through different tag intersections.

Tags are the primary mechanism by which `compendium.toml` filters sources for inclusion. They should be:

- **Objective** — describe what's in the content, not editorial judgments
- **Granular** — prefer specific terms (`wheel-bearing`, `l76`, `afm-delete`) over vague ones (`car-parts`)
- **Consistent** — use the same tag across origins for the same concept (don't mix `wheel-bearing` and `hub-bearing` for the same component)

#### 3.2.3 Universal Optional Fields

These fields are present on most sources but legitimately absent on some:

| Field | Type | When absent |
|-------|------|-------------|
| `author` | string | Anonymous forum posts, unsigned government documents |
| `date_published` | date | Undated historical texts, some web content |
| `origin_url` | string | Physical books, offline documents |
| `volatility` | enum | `static`, `unlikely`, `periodic`, `active`. Omit to inherit the default from `origin.toml`. Only set per-source as an override when a source's volatility differs from the origin norm (e.g., an unusually active thread on a mostly-dormant forum) |
| `relations` | array | Omit if no explicit references to other sources. See section 3.5 |
| `issues` | array | Omit if no known quality or completeness problems. See section 3.4 |

#### 3.2.4 Extended Schemas by `source_type`

The `source_type` field determines which additional fields are required or available. This is a closed enum — adding a new type requires defining its extended schema.

##### `forum_post`

Covers: g8board, ls1tech, performanceforums, and similar threaded discussion sites.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `thread_url` | yes | string | Direct link to the thread |
| `reply_count` | no | int | Number of replies — engagement signal |
| `is_solution` | no | bool | Whether this was marked or widely accepted as the answer |

##### `reddit_post`

Covers: Reddit posts and threads. Separated from `forum_post` because Reddit's voting system provides a distinct credibility signal.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
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

#### 3.2.5 Complete Example

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

# universal optional
author: "username"
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
thread_url: "https://www.g8board.com/forum/thread-12345"
reply_count: 47
is_solution: true
---

[normalized markdown content]
```

### 3.3 Credibility Tiers

Each source is rated for trustworthiness:

| Tier | Description | Examples |
|------|-------------|----------|
| `authoritative` | Official or primary source documentation | OEM service manual, published TSB, peer-reviewed research, original text of a novel |
| `expert` | Credentialed professional with demonstrated expertise | Professional mechanic writeup, licensed practitioner guide, scholarly analysis |
| `community_validated` | Claim independently confirmed by multiple people | Forum fix confirmed by 5+ unrelated users |
| `anecdotal` | Single person's experience, unconfirmed | One forum post describing a symptom |
| `speculative` | Theory or hypothesis without supporting evidence | "I think it might be the alternator" |

For fiction origins, `authoritative` means the primary text itself. `expert` would be published literary criticism. `community_validated` might be widely-accepted fan analysis. The tiers adapt naturally to any domain.

#### 3.3.1 Normalization Confidence

The `normalization_confidence` field (`0.0`–`1.0`) rates the quality of the conversion process itself — how accurately the raw source was captured and converted to markdown. This is distinct from credibility (trustworthiness of claims) and distinct from tags (what it's about).

A perfectly transcribed YouTube video might have high normalization confidence but low credibility tier. A badly OCR'd service manual might have low normalization confidence but authoritative credibility.

### 3.4 Source Issues

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

#### 3.4.1 Issue Types

| Type | Description |
|------|-------------|
| `missing_media` | Images, videos, or embedded content no longer available at the original source |
| `broken_links` | Referenced URLs within the source content are dead |
| `partial_content` | Source was truncated, paywalled, or incompletely captured |
| `content_modified` | Source has been edited since original publication — original version may differ from current |
| `encoding_corruption` | Garbled text, mojibake, or mangled characters |
| `format_loss` | Tables, diagrams, code blocks, or formatting that didn't survive conversion |

#### 3.4.2 Severity Levels

| Severity | Meaning |
|----------|---------|
| `critical` | Source is essentially unusable without remediation — key content is missing or corrupted |
| `major` | Significant information loss but source is still partially useful |
| `minor` | Cosmetic or non-essential content affected |

#### 3.4.3 Remediation Actions

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

### 3.5 Source Relations

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

#### 3.5.1 Origin Discovery via Relations

Source relations serve as a **dependency discovery mechanism** for compendiums. When building a compendium, a build-time analysis can scan all `relations` across filtered sources, collect every `source_id` prefix that points to an origin not currently declared as a dependency, and surface it as a recommendation:

```
Origin Dependency Analysis for Compendium/commodore-ve:
  Currently declared: G8BD (g8board), GMSM (gm-service-manuals)

  Referenced but not included:
    LSTK (ls1tech)         — 15 sources reference this origin
    GTSB (gm-tsbs)         — 12 sources reference this origin
    PFRM (performanceforums) — 4 sources reference this origin

  Unresolved references:
    "GM TSB #PI0597B"      — referenced by 8 sources
    "Holden WSM Section 4" — referenced by 3 sources
```

This turns the relation graph into an organic growth signal — the sources themselves tell you which origins you should be pulling in. The more references to a missing origin, the stronger the signal that including it would improve synthesis quality.

### 3.6 Exotic Origin Types

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

## 5. Compendium Format

### 5.1 mdBook

The compendium is built as an **mdBook** — a static documentation site generated from structured markdown files. mdBook was selected because:

- Source files are plain markdown in git (the single source of truth)
- Generates clean, navigable HTML with built-in full-text search
- Table of contents generated from `SUMMARY.md`
- Cross-references between chapters via standard markdown links
- Supports embedded images for diagrams, photos, and visual references
- Generates `searchindex.json` for programmatic full-text search
- Lightweight, fast, and self-hostable
- Rust-based toolchain

### 5.2 Textbook Structure

Each compendium follows a consistent structural pattern:

| Section | Purpose |
|---------|---------|
| **Introduction** | Domain overview, scope, how to use this compendium |
| **Quick Reference** | High-frequency lookups — specs, part numbers, key facts |
| **Chapters** | The body of knowledge, organized by domain taxonomy |
| **FAQ** | Common questions that don't fit neatly into a single chapter |
| **Glossary** | Domain-specific terminology definitions |
| **Sources** | Master registry of all origins and sources with credibility tiers |

### 5.3 Navigation Aids

The `SUMMARY.md` file serves as both the mdBook table of contents and the agent's navigation map. It provides hierarchical structure down to the section level.

mdBook also generates a `searchindex.json` file at build time that provides full-text search across all pages. This serves as the compendium's index — mapping keywords, part numbers, symptoms, and any other terms to the sections where they appear. See section 9.2 for how the agent leverages this.

### 5.4 Compendium Page Frontmatter

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

#### 5.4.1 Incremental Synthesis

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

## 6. Hosting & Distribution

### 6.1 Architecture

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

### 6.2 Access Control

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

### 6.3 Caddy Server Configuration

The Caddy instance is an external VPS that currently serves as a reverse proxy. Each compendium is deployed as a subdirectory under `/srv/ref/`.

```
/srv/ref/
├── commodore-ve/        # mdBook build output
├── dune/                # mdBook build output
├── economics/           # mdBook build output
└── ...
```

---

## 7. CI/CD Pipeline

### 7.1 Build & Deploy Flow

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

### 7.2 Deployment Mechanism

The Caddy server accepts deployments via one of:

- **SSH/SCP push:** The Forgejo Actions runner pushes build artifacts directly to `/srv/ref/{domain}/` on the Caddy VPS via SSH with a deploy key.
- **Webhook receiver:** A small receiver script on the Caddy box accepts a tarball via HTTP POST with a shared secret, unpacks it to the target directory.

### 7.3 Workflow Template

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

### 7.4 Origin Update Propagation

When new sources are added to an origin repo, the compendiums that reference it don't automatically rebuild. This is intentional — synthesis is a curated process. The workflow is:

1. New sources are committed to the origin repo (e.g., `Corpus/g8board`)
2. The compendium maintainer bumps the pinned commit hash in `compendium.toml` when ready to incorporate new material
3. New synthesis is performed incorporating the new sources
4. Push triggers the build and deploy pipeline

For origins with high ingestion velocity, this can be automated with a scheduled workflow that bumps pinned commits periodically.

---

## 8. Agent Layer

### 8.1 Design

Each domain has a **single bespoke agent** — a dedicated AI assistant that is an expert in that domain and nothing else. There is no multi-agent orchestration, no router, and no shared context between domains. When you need automotive expertise, you invoke the automotive agent. When you need Dune lore, you invoke the Dune agent.

This simplicity is deliberate:

- The user always knows which expert they need
- Each agent's system prompt is fully tailored to its domain
- No prompt budget is wasted on routing logic or domain detection
- Each agent can have domain-specific personality, terminology, and reasoning patterns

### 8.2 Agent Configuration

Each agent is configured as a **skill** (for Claude Code / claude.ai) or equivalent construct for other platforms. The agent's configuration includes:

- **System prompt:** Domain-specific persona, expertise description, reasoning instructions, and the compendium's `SUMMARY.md` content as its navigation map.
- **Compendium URL:** The base URL for fetching compendium pages and the search index (e.g., `https://ref.example.org/commodore-ve/`).
- **Access credentials:** The agent's basic auth credentials for the compendium site.
- **Domain taxonomy:** Key concepts, terminology, and the structure of the domain to guide query decomposition.

### 8.3 Agent Behavior Model

When the agent receives a question, it follows this process:

1. **Understand the query.** Parse the question to identify which systems, symptoms, concepts, or topics are involved.
2. **Navigate the compendium.** Using the `SUMMARY.md` table of contents (already in context), identify which chapter(s) and section(s) are relevant. If the query doesn't map cleanly to the TOC structure, query the `searchindex.json` for relevant terms to discover applicable sections.
3. **Fetch relevant sections.** Retrieve the specific markdown pages from the compendium site via HTTP GET. Only fetch what's needed — not the entire compendium.
4. **Synthesize a response.** Answer the question based on the retrieved compendium content, citing specific sources where the compendium provides them.
5. **Flag coverage gaps.** If the compendium doesn't cover the topic well, tell the user explicitly rather than speculating.

### 8.4 Example: Automotive Agent

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

### 8.5 Example: Fiction Agent

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

## 9. Retrieval Strategy

### 9.1 Primary Method — TOC-Based Navigation

The agent's primary retrieval mechanism is structural navigation using the compendium's table of contents. The `SUMMARY.md` is loaded into the agent's context as part of its system prompt. This gives the agent a complete map of what knowledge exists and where it lives.

This is analogous to how a knowledgeable human uses a reference book: they already know the structure, they go to the right chapter, and they read the relevant section. The agent does the same via HTTP fetches of specific pages.

**Advantages:**

- No embedding infrastructure required
- No vector database to maintain
- Retrieval is deterministic and explainable ("I looked in chapter 4.1")
- Works with the same artifact the human browses
- Updates are instant — new content appears as soon as it's deployed

### 9.2 Search Index Lookup

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

### 9.3 Fallback — Vector Search (Deferred)

Semantic vector search is **not implemented initially** but the architecture accommodates it if needed. The trigger for adding it would be repeated instances where the agent cannot find relevant content through TOC navigation or the search index because the user's query language doesn't match any terminology present in the compendium.

If implemented, it would be a lightweight vector store (e.g., Qdrant in Docker) with embeddings over the compendium's markdown chunks, used only when TOC/search index navigation fails to identify relevant sections.

### 9.4 Forgejo API as Alternative Access Path

The Forgejo REST API provides raw file access to the compendium markdown:

```
GET /api/v1/repos/Compendium/{domain}/raw/manuscript/{path}
Authorization: token {read-only-token}
```

This serves as an alternative access path — useful for agents running in environments where fetching rendered HTML is less convenient than raw markdown (e.g., Claude Code sessions where markdown is the native format). Both access methods (hosted site and API) serve the same content from the same source of truth.

---

## 10. Scaling & Reuse

### 10.1 Adding a New Origin

1. Create a new repository under the Corpus organization
2. Add `origin.toml` with the registration metadata, source ID prefix, and reingest configuration
3. Add `manifest.toml` and populate it with known sources (both `captured` and `pending`)
4. Create the `normalized/`, `assets/`, and `ingested/` directories
5. Build or configure the ingestion pipeline appropriate to the source type
6. Begin normalizing source material with rich frontmatter tags
7. The origin is now available for any compendium to declare as a dependency

### 10.2 Adding a New Compendium

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

### 10.3 Stacking Compendiums

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

### 10.4 Domain Taxonomy Design

Each domain needs its own taxonomy — the organizational structure that chapters follow. This should be designed before significant content is ingested, though it will evolve. Guidelines:

- Follow the natural structure of the domain (for a vehicle: by system; for health: by body system; for fiction: by world element — characters, factions, locations, technology, themes, adaptations)
- Prefer 2-3 levels of hierarchy maximum
- Each leaf section should be self-contained enough to be useful when fetched in isolation
- Cross-reference liberally between related sections

### 10.5 Standardized Frontmatter Schema

The complete source frontmatter schema is defined in section 3.2. In summary:

**Universal required** (every source):
`source_id`, `title`, `summary`, `source_type`, `credibility_tier`, `tags`, `raw_sources`, `ingestion_date_first`, `ingestion_date_last`, `content_changed_last`, `normalization_confidence`, `normalization_model`, `normalization_date`

**Universal optional** (present when applicable):
`author`, `date_published`, `origin_url`, `volatility`, `relations`, `issues`

**Extended schemas** are determined by `source_type` (closed enum):

| Source Type | Required Extended Fields | Optional Extended Fields |
|-------------|-------------------------|--------------------------|
| `forum_post` | `thread_url` | `reply_count`, `is_solution` |
| `reddit_post` | `subreddit`, `post_url` | `score`, `comment_count`, `post_type` |
| `book` | `work_title` | `isbn`, `word_count`, `series_name`, `series_position` |
| `service_manual` | `manual_title`, `section_reference`, `model_years` | `vehicle_system` |
| `technical_bulletin` | `bulletin_number`, `affected_models`, `affected_years` | `superseded_by` |
| `video` | `duration_seconds`, `has_visual_content` | `channel_name` |
| `podcast` | `duration_seconds` | `episode_number`, `series_name` |
| `research_paper` | `journal`, `peer_reviewed` | `doi` |
| `article` | `article_url` | `publication` |
| `screenplay` | `work_title`, `medium` | `draft` |
| `product_documentation` | `product_name`, `manufacturer` | `document_type`, `part_numbers` |

**Compendium page frontmatter** (section 5.4):
`chapter_id`, `title`, `synthesis_model`, `synthesis_date`, `last_reviewed`, `sources[]` (with `source_id`, `synthesized_at`, `credibility_tier` per source)

---

## 11. Infrastructure Summary

### 11.1 Component Map

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

### 11.2 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Source of truth | Forgejo (git) | Version control, API access, Actions CI |
| Source organization | Forgejo org (Corpus) | One repo per origin, rich frontmatter tags |
| Compendium format | Markdown + mdBook | Human-readable source, clean output, built-in search |
| Source linkage | Declared dependencies in `compendium.toml` | Pin origins to commits, resolve at build time with sparse checkout |
| Hosting | Caddy on external VPS | Simple, reliable, automatic HTTPS, basic auth |
| CI/CD | Forgejo Actions | Integrated with repos, self-hosted runner |
| Agent platform | Claude (skill / Code) | Primary AI interface, flexible access patterns |
| Retrieval | TOC navigation + searchindex.json + HTTP fetch | No additional infrastructure, deterministic, explainable |

### 11.3 What Is Intentionally Not Included

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
Corpora: g8board, ls1tech, gm-service-manuals, gm-tsbs, penrite-oils
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
