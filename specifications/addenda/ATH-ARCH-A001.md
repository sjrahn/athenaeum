---
addendum_id: ATH-ARCH-A001
parent_spec: ATH-ARCH
parent_version: 1.0
title: "Origin Identity Guidelines — The One-Voice Rule"
type: clarification
status: pending
author: Steven Rahn
date_created: 2026-02-09
sections_affected:
  - "3. Origin Repositories"
incorporation_target: ~
---

## Context

Section 3 (Origin Repositories) defines origins as "normalized repositories of source material organized by where the information came from, not what it's about" but does not provide explicit guidance on how to determine the boundary of an origin. In practice, this leads to ambiguous cases: should all GM documents go in one origin or be split by document type? Should similar forums be combined? The spec needs a clear, repeatable rule for scoping origins.

## Change

The following guidelines clarify how origin boundaries are determined. These do not change the architecture — they make explicit what is already implied by the "organized by where it came from" principle.

### The One-Voice Rule

An origin repository represents a single distinct voice — one entity that produces information. The question that determines an origin boundary is not "what kind of document is it" or "what platform does it live on" but **"who produced it."**

If you can point at a source and say "that came from the same entity expressing its own perspective," it belongs in the same origin. If two sources come from different entities — even if they're on the same platform, cover the same topic, or share the same format — they belong in separate origins.

### What "Voice" Means

A voice is an entity with a coherent perspective:

- A **company** — GM, Holden, Penrite Oils
- A **community** — one forum, one subreddit, one Discord server
- An **author** — Frank Herbert, Brian Herbert
- A **channel or show** — Engineering Explained, South Main Auto
- A **government body** — NHTSA, Australian ANCAP
- An **academic journal** — a single publication venue

A platform is never a voice. Reddit is not an origin — r/MechanicAdvice is. YouTube is not an origin — Engineering Explained is. "Car forums" is not an origin — g8board is.

### Consolidation by Entity, Not Document Type

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

### Why Not Consolidate Similar Voices?

Five car forums (g8board, ls1tech, performanceforums, pontiacg8forum, holdenforums) share a platform type, content structure, and ingestion method. It's tempting to merge them into one `car-forums` origin to reduce repo count. This is wrong for three reasons:

1. **Each community is a distinct voice.** g8board is G8-obsessed. ls1tech is LS-engine-first and happens to cover G8s. holdenforums brings the Australian VE platform perspective that American forums lack. These are genuinely different perspectives with different biases, different expertise concentrations, and different blind spots.

2. **Combining introduces the taxonomy problem we're avoiding.** The entire origin architecture is built on the principle that "where it came from" is an unchallengeable fact requiring no editorial judgment. If you combine forums, you're making an editorial decision about which communities are "similar enough" — and that decision may need to be undone later.

3. **The compendium is where commonality is extracted.** Five forums all discussing rear wheel bearings is not a reason to combine them. It's a reason for the compendium to pull from all five and synthesize their perspectives. That's the compendium's job, not the origin's.

4. **The friction of multiple repos is trivial.** Adding an origin as a submodule is one line in `.gitmodules`. Sparse checkout is handled by `setup.sh`. The real friction is untangling combined origins later when you need one voice in a compendium but not another.

### The Decision Test

When deciding whether something is one origin or multiple:

1. **Can you name the entity?** "GM", "g8board", "Frank Herbert", "r/MechanicAdvice" — if you can name it as a single entity with a coherent identity, it's one origin.

2. **Would you ever want one without the other in a compendium?** If ls1tech's LS engine content belongs in an engine-building compendium but g8board's doesn't, they must be separate origins. You can't partially submodule a repo.

3. **Is the split based on document type or entity?** If you're splitting because "service manuals are different from press releases," stop — that's a `source_type` distinction, not an origin distinction. If you're splitting because "GM and Holden are different manufacturers," proceed — those are different entities even though they shared a corporate parent.

### Updated Examples

| Voice (Entity) | Origin Repo | Contains |
|----------------|-------------|----------|
| General Motors | `gm` | Service manuals, TSBs, recalls, press releases, dealer bulletins, brochures |
| Holden | `holden` | Workshop manuals, Australian-market documentation, press releases |
| Penrite Oils | `penrite` | Product datasheets, application guides, safety data sheets |
| G8Board.com | `g8board` | All forum threads from this community |
| LS1Tech.com | `ls1tech` | All forum threads from this community |
| HoldenForums | `holdenforums` | All forum threads from this community |
| r/MechanicAdvice | `r-mechanicadvice` | All posts from this subreddit |
| r/PontiacG8 | `r-pontiacg8` | All posts from this subreddit |
| Frank Herbert | `frank-herbert` | Novels, short stories, essays, interviews |
| Engineering Explained | `engineering-explained` | All videos from this channel |
| South Main Auto | `south-main-auto` | All videos from this channel |
| NHTSA | `nhtsa` | Recall databases, safety ratings, investigation reports |

### Impact on `origin.toml`

The `source_id_prefix` is per-entity. A single 4-letter prefix covers everything from that voice:

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

### Impact on Manifest

One manifest per entity means one place to see total coverage:

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

[[sources]]
source_id = "GMOT.0101"
title = "TSB PI0832A — Transmission Shudder Under Light Throttle"
status = "pending"
priority = "high"
notes = "Referenced by 8 forum sources across g8board and ls1tech"
```

The `source_type` field in each normalized file's frontmatter distinguishes what kind of document it is (`service_manual`, `technical_bulletin`, `article`, `product_documentation`). The manifest and origin just track that it all comes from GM.
