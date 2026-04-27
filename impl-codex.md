# Athenaeum — Codex Implementation Guide

**Status:** living document. Updates as implementation matures.

**Companion to:** [`spec-athenaeum.md`](spec-athenaeum.md), the authoritative data contract. This guide describes the *implementation* of the codex layer, plus the compendium build process that sits above it. Choices here may change as tooling evolves; the spec must not.

The corpus / artifact-layer counterpart is [`impl-corpus.md`](impl-corpus.md).

---

## 1. Scope

This guide covers the codex side: codex directory layout, slug-as-topic conventions, codex-record authoring workflow, runtime resolution of wikilinks across codices and corpora, codex regeneration mechanics, the compendium directory layout, and the compendium build process.

What lives in this guide vs in the spec:

- **Spec (authoritative).** What records carry, how layers reference each other, what the reference stability hierarchy is, what slug uniqueness scoping means. The data contract and the layering invariants.
- **This guide.** How a codex is laid out on disk, how the runtime mounts codices and corpora, how the build process resolves the layered references and produces compiled outputs.

If the two ever conflict, the spec wins; this guide gets corrected.

---

## 2. Codex directory layout

A codex is a named container holding authored codex records. The on-disk shape:

```
codex-{name}/
├── codex.yaml                 — codex-level metadata (optional)
└── documents/
    ├── {first-2-of-uuid}/     — sharded by first 2 hex chars of UUID
    │   └── {full-uuid}.md
    └── ...
```

**Sharding policy.** Codex records are sharded one level deep by the first two hex characters of the UUID, mirroring the corpus's artifact sharding. Same depth as artifact records and binary cache in the corpus. Flat layout is acceptable below ~1k records; sharded once a codex's record count crosses that threshold. The convention is identical to the corpus: full UUID kept in the filename so files are self-identifying when copied outside their shard.

**`codex.yaml`** is optional and may carry codex-level metadata such as:

```yaml
name: codex-personal
display_name: "Personal Codex"
description: "..."
tag_vocabulary_url: "..."     # optional pointer to a tag-conventions doc
```

The spec does not mandate any of these fields. Tooling should treat `codex.yaml` as best-effort hints — the codex name (the directory) is the authoritative identity.

**No top-level `binary/`, `schema/`, or `capture/` in a codex.** Those are corpus-side. A codex consumes artifacts from corpora it doesn't own.

---

## 3. Slug-as-topic conventions

Slugs in a codex are the codex's stable topic handles. Their job is to survive codex regeneration so that compendium references targeting them continue to resolve.

### 3.1 Choosing a slug

A slug is the document's topical name, not the document's title. Aim for:

- **Kebab-case, lowercase, ASCII-safe** — matches `[a-z0-9]+(-[a-z0-9]+)*` per spec §1.3.
- **Stable across regeneration** — picked from the topic, not the document's instance details. A document about a how-to guide for X gets the slug `how-to-x`, not `how-to-x-rev3-by-author-y`.
- **Codex-unique** — uniqueness is enforced at write time. Slug collisions within a codex are an authoring bug.

### 3.2 Renaming a slug

A slug rename breaks references that target it: in-codex wikilinks pointing at it, plus any compendium that cites `[[codex-name:old-slug]]`. A rename helper should:

1. Find every reference to the old slug within the codex.
2. Find every reference of the form `[[{this-codex-name}:old-slug]]` across loaded compendiums.
3. Rewrite all of them to the new slug.
4. Commit as a single change so the rename is atomic in version control.

### 3.3 Reserved slug-like patterns

A few patterns SHOULD be avoided to keep the resolution rules clean:

- A slug shaped like a UUID (`xxxxxxxx-xxxx-...`) — the resolver will treat it as a UUID match.
- A slug containing a colon (`:`) — the colon is the cross-codex/cross-corpus delimiter in compendium bodies.
- A slug that's purely numeric — ambiguous with `page=N`-style references.

---

## 4. Authoring workflows

### 4.1 Codex-side authoring

Authoring a codex record follows the spec's `Author` agent contract (§5.4). The implementation:

1. **Pick the codex.** The author works in exactly one codex per invocation.
2. **Pick a synthesis target.** A topic that benefits from authored prose — a how-to guide, a concept page, a synthesis across several artifacts. The trigger may come from the curator, from a tag cluster, from operator direction, or from a compendium gap.
3. **Pick a slug** (the codex topic). Stable, kebab-case, codex-unique.
4. **Compose the body.** Cite artifacts via `[[blake3]]` wikilinks (the most stable form). Embed artifact content via `![[blake3]]` where useful. Use functional URIs (`![[blake3://hash?params|alt text]]`) for derived views (PDF page extraction, video framegrab, image crop). Link to peer records within the same codex via `[[slug]]` (preferred) or `[[uuid]]`.
5. **Never write `[[codex-name:…]]`.** A codex is pure — its records only reference downward to artifacts and locally to peer records. Cross-codex citation is a compendium-record authoring job.
6. **Save** under `documents/{first-2-of-uuid}/{full-uuid}.md`. Frontmatter populated with UUID, slug (if used), title, description, tags, status. Codex-record frontmatter is deliberately thin (spec §3.1.3) — there is no codex-record-side credibility field. Compendiums weight a codex record's evidentiary artifacts by the credibility-signal classifications those artifacts carry.

### 4.2 Compendium authoring

A compendium body is the integration point — where multi-codex / multi-corpus synthesis happens. The compendium author:

1. **Identifies inputs.** Which codices, which codex topics, which artifacts. Often starts by selecting a small set of seed topics across one or more codices and following references outward.
2. **Drafts chapters.** Markdown prose with:
   - `[[blake3]]` for artifact citations (any loaded corpus).
   - `[[corpus-name:blake3]]` for provenance disambiguation when blake3 alone is ambiguous (rare but useful for cases where both a private and public corpus contain the same content and the compendium needs to be specific).
   - `[[codex-name:slug]]` for codex topic citations (preferred form for codex citations — survives regeneration).
   - `[[codex-name:uuid]]` only when there's no slug and no artifact equivalent. Discouraged because it orphans across regeneration.
   - `![[blake3://hash?params]]` for derived views.
3. **Applies the lowest-level-source preference.** When a compendium record is about a particular subject and an artifact directly says it, cite the artifact, not a codex topic that paraphrases it. When the compendium needs interpretation/synthesis that no single artifact provides, cite the codex topic that already did that synthesis. The hierarchy is: artifact > codex topic by slug > codex record by UUID (avoid).

---

## 5. Runtime resolution

Wikilink resolution is the runtime's job. The runtime mounts a set of codices and corpora and answers reference lookups.

### 5.1 Mounting

The runtime configuration declares which codices and corpora are accessible. Both can be local directories or remote URIs (server-mounted). The configuration is the join — codices and corpora don't declare runtime joins in their own data.

A typical configuration:

```yaml
corpora:
  - name: corpus-public
    path: /path/to/corpus-public
  - name: corpus-private
    path: /path/to/corpus-private
codices:
  - name: codex-personal
    path: /path/to/codex-personal
  - name: codex-shared
    path: /path/to/codex-shared
compendiums:
  - name: compendium-personal-vehicle
    path: /path/to/compendium-personal-vehicle
```

Multiple codices may coexist with no relationship to one another beyond what compendium references express.

### 5.2 Resolution rules

Per spec §3.6:

**In an artifact body** (read-only at this stage; the runtime is just rendering):
1. `[[blake3]]` → any artifact in any loaded corpus that has a matching blake3.
2. Anything else → unresolved.

**In a codex record's body:**
1. `[[blake3]]` → any artifact in any loaded corpus.
2. `[[slug]]` → a codex record in the same codex with that slug.
3. `[[uuid]]` → a codex record in the same codex with that UUID.
4. Anything else → unresolved.

**In a compendium record's body:**
1. `[[blake3]]` → any artifact in any loaded corpus (collision detection: if two loaded corpora have the same blake3, that's fine — it's by definition the same bytes).
2. `[[corpus-name:blake3]]` → that artifact in the named corpus, asserting provenance.
3. `[[codex-name:slug]]` → the codex topic in the named codex.
4. `[[codex-name:uuid]]` → the codex record instance in the named codex.
5. Anything else → unresolved.

### 5.3 Unresolved-link handling

When a reference cannot be resolved, the runtime should:

- In Obsidian-style raw browsing, fall back to the alt text or display text and surface the link as broken (Obsidian's standard treatment).
- In compiled outputs, log the unresolved reference and substitute a clearly-marked fallback ("[unresolved]" or similar). Don't silently drop the link.
- In tooling backlink panels, list unresolved references as authoring follow-ups.

### 5.4 Collision detection

Same blake3 in two corpora — fine, they are by definition the same bytes; the corpora may both have it. The reference resolves to either copy.

Same slug in two codices — fine, slugs are codex-scoped. A bare `[[slug]]` reference within a codex record resolves locally; a qualified `[[other-codex:slug]]` reference in a compendium record resolves to the named codex.

Same UUID in two codices — should not happen by design (UUIDv4 collision is astronomical). If it does, the runtime should warn and let the qualified form resolve unambiguously.

---

## 6. Codex regeneration

Regeneration is a contemplated future workflow: re-derive an entire codex from a corpus snapshot plus authoring prompts. Not part of v10's required behavior, but the design supports it via the slug-as-stable-topic principle.

### 6.1 What regeneration preserves

- **Slug → topic mapping.** Every slug present before regeneration maps to a topic in the regenerated codex. The slug is the contract; compendium references that target the slug continue to resolve.
- **Codex name.** The codex itself keeps its identity.

### 6.2 What regeneration may change

- **UUIDs.** Each regeneration mints fresh UUIDs. Compendium references that targeted UUIDs may orphan.
- **Body prose.** A new authoring pass produces new prose.
- **Wikilinks within the codex.** A regenerated codex record may reference different artifacts or different sibling slugs depending on what the synthesis prompts produce.

### 6.3 Migration / rebuild discipline

If a regeneration produces materially different output (slug renames, topic restructuring), it's not pure regeneration anymore — it's an edit. Treat it as such: surface diffs, propagate changes to compendiums that cite the codex, run rename helpers.

### 6.4 When regeneration makes sense

- A codex was built from an early corpus snapshot and has drifted from the current corpus state.
- An authoring prompt has been substantially improved.
- A new model is meaningfully better and the cost of re-running is justified.

A codex that is hand-authored record-by-record without a regeneration prompt is not regenerable — it's a hand-built artifact, like any other. Regeneration is opt-in and applies to codices whose authoring is procedural enough to support it.

---

## 7. Build process

The build process compiles outputs (mdbook, static site, browsable vault) for a particular target — typically a compendium plus its connected codices and corpora.

### 7.1 Inputs

- A target compendium (or a codex, if the goal is to publish a codex on its own).
- The runtime's mounted set of codices and corpora.
- Build configuration (output format, theme, etc.).

### 7.2 Resolution pass

1. Walk the target's body (and all body fragments: chapters, sub-pages).
2. Resolve every wikilink and embed per the rules in §5.
3. Resolve every functional URI: compute the transformation, write the derived artifact to the build's output directory, substitute the path.
4. Build navigation: tag indexes, slug routes, backlink panels (Obsidian-style).
5. Generate origin-URI redirects: for every artifact referenced by the target, expose all of its `uris[]` entries as redirect entries pointing at the artifact's compiled-output path.

### 7.3 Output formats

The spec doesn't dictate the format. Common choices:

- **mdbook** — book-shaped published output for compendium publishing.
- **Static site** — flexible HTML output, often the default for Obsidian Publish-style deployments.
- **Browseable Obsidian vault** — symlinks/copies into one Obsidian vault that mounts the target plus its dependencies for human browsing.
- **JSON API** — structured outputs consumable by tooling.

### 7.4 Ephemeral vs durable outputs

Functional URI results, derived images, transcoded media — all ephemeral. They live in the build output directory and are rebuildable from the underlying artifact. Cache them but don't treat them as records.

---

## 8. Open implementation questions

- **Codex sharding crossover.** Same as the corpus side: at what doc count do we move to two-level sharding? Likely a `codex.yaml` flag.
- **Cross-codex slug discovery.** When a compendium author wants to see what slugs are available in a codex they're loading, the runtime needs an index. Currently rebuildable on mount; persistent index is a perf optimization.
- **Conflicting slugs across codices in the same compendium build.** Two codices each define `brake-bleeding`. The compendium author cites both via qualified `[[codex-name:slug]]` form, so there's no ambiguity, but the build should warn when the same slug exists in multiple loaded codices for the author's awareness.
- **Compendium chapter granularity.** A compendium could be a single compendium record or many. Convention: split chapters into separate records when the chapter is large enough that scrolling through it gets in the way; otherwise keep the compendium as a small set of records. The build process flattens or paginates per the target output format.
- **Codex regeneration tooling.** When sjrahn wants to actually do a regeneration, the tooling will need: corpus-snapshot pinning, prompt versioning, slug-preservation enforcement, and a diff report. Out of scope for v10 implementation.
