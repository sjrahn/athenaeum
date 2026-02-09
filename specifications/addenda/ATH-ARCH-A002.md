---
addendum_id: ATH-ARCH-A002
parent_spec: ATH-ARCH
parent_version: 1.0
title: "Term Registry — System-Wide Controlled Vocabulary"
type: addition
status: incorporated
author: Steven Rahn
date_created: 2026-02-09
sections_affected:
  - "2. Two-Layer Architecture"
  - "3. Origin Repositories"
  - "4. Compendium Synthesis"
  - "11. Infrastructure Summary"
incorporation_target: 2.0
---

## Context

The architecture spec defines tags as a tagging mechanism for source metadata (§3) and uses them for compendium filtering (§4), but does not specify how tags are managed, disambiguated, or kept consistent across origins. As the system scales across multiple origins and compendiums, freeform tags will diverge — the same entity will be tagged differently in different origins, ambiguous surface forms will produce incorrect matches, and there will be no authority for what a tag means.

The system needs a controlled vocabulary that sits alongside the Corpus and Compendium layers as foundational infrastructure.

## Change

Add the **Term Registry** as a new system-wide component. The registry is a flat collection of TOML files — one per term — living in its own repository (`example-org/term-registry/`). It provides canonical identification for all named entities and descriptors used across Athenaeum.

### Overview

The Term Registry is a system-wide controlled vocabulary that provides canonical identification for all named entities and descriptors across Athenaeum. It ensures that when two sources reference the same person, organization, vehicle, component, or concept, they use the same term — even if those sources were normalized months apart by different models from different origins.

Without a registry, identification degrades into freeform text matching: `"Ryan Grimm"`, `"ryan-grimm"`, `"R. Grimm"`, and `"grimm-ryan"` all refer to the same person but are invisible to any automated system. The registry solves this by establishing canonical terms with rich metadata, supporting disambiguation of concepts that share surface forms, and enforcing that all frontmatter always uses the correct canonical term.

Every tag used in the system — from specific entities like `l76-engine` to descriptors like `diagnosis` — is a registered term. Terms describe sources. Terms also describe other terms. The registry is a single flat namespace with no imposed hierarchy.

The registry sits alongside the Corpus and Compendium organizations as a foundational Athenaeum component. Every origin's normalization process reads from it and proposes additions to it.

### Disambiguation Philosophy

The term registry defines precise coordinates in concept space, not opinions. A term's job is to refer to exactly one thing unambiguously. When a natural-language word or phrase refers to genuinely different things depending on context, it cannot be a term on its own — it requires disambiguation.

This is not about controversy. It's about precision. `palestine` is not a valid term because it is ambiguous — it refers to different geopolitical realities depending on the era and context. `palestine-pre1948` and `palestine-current` are valid terms because each refers to exactly one thing. Both can have "Palestine" as a colloquial name because that *is* what people call them. The canonical term is the precise coordinate. The names are how humans refer to it.

The same principle applies everywhere:

- `mercury` is ambiguous (planet, element, Roman god, car brand). `mercury-planet`, `mercury-element`, `mercury-roman-deity`, `mercury-automobile` are precise.
- `dod` is ambiguous (Displacement on Demand, Department of Defense). `afm-dod` and `dod-department-of-defense` are precise.
- `jaguar` is ambiguous (animal, car brand). `jaguar-animal` and `jaguar-automobile` are precise.

Not every term needs disambiguation. `ryan-grimm` is unambiguous — there is one person being referred to. `l76-engine` is unambiguous — there is one engine. Disambiguation is only required when a surface form genuinely maps to multiple distinct concepts.

The iterative nature of the registry means disambiguation improves over time. A term that seemed unambiguous may later be discovered to refer to two things, at which point it gets split and reconciled. The registry is a living document that gets more precise with use.

### Core Principle

**The frontmatter is the source of truth. The registry is the authority. They must always agree.**

There is no alias resolution, no runtime translation, no indirection layer. Every tag in every source file's frontmatter is the current canonical form as defined by the registry. If a tag is found to be incorrect — because two entities were confused, or because a tag was superseded by a better canonical form — the affected frontmatter is rewritten. The old form ceases to exist in the system.

### Term Structure

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

### Registry Format

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

### Two-Pass Normalization Pipeline

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

#### Author Field vs. Username Field

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

### Reconciliation

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

### Unified Term Namespace

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

### Impact on Source Frontmatter Extended Schemas

The following `source_type` extended schemas should include a `username` field:

| source_type | Field | Required | Description |
|-------------|-------|----------|-------------|
| `forum_post` | `username` | required | Exact username of the poster on the forum |
| `reddit_post` | `username` | required | Exact Reddit username of the poster |

This replaces any use of the `author` field for these source types. The `author` field remains available as a universal optional field but should only be populated when the poster is a known, identifiable person with a registered term.

### Impact on `compendium.toml`

The filtering system operates on canonical tags. Because `author` is now an entity tag, compendium configuration can filter by author directly:

```toml
[[compendium.corpora]]
name = "ryan-grimm"
include_all = true                   # his personal output, include everything

[[compendium.corpora]]
name = "nyt"
match_author = "ryan-grimm"          # only his articles from the NYT

[[compendium.corpora]]
name = "the-intercept"
match_author = "ryan-grimm"          # only his articles from The Intercept

[[compendium.corpora]]
name = "r-politics"
require_any_tags = ["ryan-grimm"]    # reddit posts discussing or referencing him
```

Tag-based filters and author-based filters can be combined:

```toml
[[compendium.corpora]]
name = "nyt"
require_any_tags = ["economics", "federal-reserve"]
match_author = "ryan-grimm"
# Source matches if it satisfies EITHER condition
```

### Reconciliation Reporting

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
    Status: correctly disambiguated ✓

  Unresolved proposals: 12
    3 high-confidence (>0.9) — likely auto-approvable
    6 medium-confidence (0.7-0.9) — need review
    3 low-confidence (<0.7) — may be false identification

  Unregistered tags (in frontmatter, no matching file in registry): 4
    "mystery-component" — used in G8BD.0150
    Action: create term file or correct to existing term
```

### Registry Scope and Growth

The registry starts small and grows organically through normalization:

1. **Bootstrap from existing origins.** Normalize existing sources, let Pass 1 produce raw tags, resolve and register them.
2. **Grow with each normalization.** New sources produce proposals for entities the registry hasn't seen.
3. **Cross-origin signal.** When the same entity appears across multiple origins, that reinforces confidence in the registration. An entity referenced by 5 origins is well-established.
4. **Compendium-driven demand.** Building a new compendium may reveal entities that need registration to enable proper filtering.

The registry doesn't need to be complete before normalization begins. Pass 1 operates without registry context. Tag resolution handles what the registry knows, and proposals capture what it doesn't. The system is functional from day one and improves as the registry grows.

### Infrastructure Placement

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
