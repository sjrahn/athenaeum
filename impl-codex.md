# Athenaeum — Codex Implementation Guide

**Status:** living document. Updates as implementation matures.

**Companion to:** [`spec-athenaeum.md`](spec-athenaeum.md), the authoritative data contract. This guide describes the *implementation* of the codex layer, plus the compendium build process that sits above it. Choices here may change as tooling evolves; the spec must not.

The corpus / artifact-layer counterpart is [`impl-corpus.md`](impl-corpus.md).

---

## 1. Scope

This guide covers the codex side: codex directory layout, codex-record authoring workflow, runtime resolution of wikilinks across codices and corpora, codex regeneration mechanics, the compendium directory layout, and the compendium build process.

What lives in this guide vs in the spec:

- **Spec (authoritative).** What records carry and how layers reference each other. The data contract and the layering invariants.
- **This guide.** How a codex is laid out on disk, how the runtime mounts codices and corpora, how the build process resolves the layered references and produces compiled outputs.

If the two ever conflict, the spec wins; this guide gets corrected.

---

## 2. Codex directory layout

A codex is a named container holding authored codex records. The on-disk shape:

```
codex-{name}/
├── codex.yaml                 — codex-level metadata (optional)
└── records/
    ├── {first-2-of-id}/       — sharded by first 2 hex chars of the UUIDv7 id
    │   └── {full-uuidv7}.md
    └── ...
```

**Sharding policy.** Codex records are sharded one level deep by the first two hex characters of the UUIDv7 id, mirroring the corpus's artifact sharding. Same depth as artifact records and the binary cache in the corpus. Flat layout is acceptable below ~1k records; sharded once a codex's record count crosses that threshold. The convention is identical to the corpus: full UUIDv7 kept in the filename so files are self-identifying when copied outside their shard. UUIDv7 ids are time-ordered, so shard distribution remains roughly uniform as the codex grows.

**`codex.yaml`** is optional and may carry codex-level metadata such as:

```yaml
name: codex-personal
display_name: "Personal Codex"
description: "..."
tag_vocabulary_url: "..."     # optional pointer to a tag-conventions doc
```

The spec does not mandate any of these fields. Tooling should treat `codex.yaml` as best-effort hints — the codex name (the directory) is the authoritative identity.

**No top-level `artifacts/`, `schema/`, or `capture/` in a codex.** Those are corpus-side. A codex consumes artifacts from corpora it doesn't own.

---

## 3. Compendium directory layout

A compendium is a named container holding compendium records — author-named markdown chapters that integrate across one or more codices and corpora. The on-disk shape:

```
compendium-{name}/
├── compendium.yaml            — compendium-level metadata (optional)
└── records/
    ├── 01-introduction.md     — author-chosen filenames (chapter style)
    ├── 02-history.md
    ├── 03-overview.md
    └── ...
```

**Naming.** Compendium-record filenames are an authoring choice — pick a chapter-style name (`overview.md`, `01-introduction.md`). Numeric prefixes are conventional for ordering but not required; the build process (§7) determines the navigation order from frontmatter or directory listing per the target output format.

**No sharding.** Compendiums are typically small enough (single-digit to low-hundreds of chapters) that sharding adds complexity without payoff. Flat `records/` is the convention.

**No top-level `artifacts/`, `schema/`, or `capture/` in a compendium.** Those are corpus-side. A compendium consumes artifacts from corpora and codex records from codices.

**`compendium.yaml`** is optional and parallels `codex.yaml`: display name, description, references to the codices/corpora the compendium expects to be loaded against, and any synthesis-system-prompt pointer (spec §6.4). Tooling treats it as best-effort hints; the compendium name (the directory) is the authoritative identity.

---

## 4. Authoring workflows

### 4.1 Codex-side authoring

Authoring a codex record follows the spec's `Author` agent contract (§5.4). The implementation:

1. **Pick the codex.** The author works in exactly one codex per invocation.
2. **Pick a synthesis target.** A topic that benefits from authored prose — a how-to guide, a concept page, a synthesis across several artifacts. The trigger may come from the curator, from a tag cluster, from operator direction, or from a compendium gap.
3. **Mint a UUIDv7.** The codex record's `id` is a freshly minted UUIDv7. Time-ordered ids let tooling list a codex's records in creation order without reading the body.
4. **Compose the body.** Footnote-cite artifacts (`text[^N]` with `[^N]: corpus://{hash}`, optionally `corpus://{hash}#anchor` or `corpus://{hash}?page=4`). Embed artifact content via functional URI (`![[corpus://{hash}?params|alt text]]`) for derived views (PDF page extraction, video framegrab, image crop). Wikilink peer codex records via `[[uuid]]`.
5. **Never write `codex://...`.** A codex is pure — its records only reference downward to artifacts and locally to peer records (see spec §1.2). Cross-codex citation is a compendium-record authoring job.
6. **Save** under `records/{first-2-of-id}/{full-uuidv7}.md`. Frontmatter is just `id`, `title`, `description`, `status`, `tags`. Codex-record frontmatter is deliberately thin (spec §3.1.3); credibility weighting happens at the compendium layer by reading the credibility-signal classifications on the evidentiary artifacts a codex record cites.

### 4.2 Compendium authoring

A compendium body is the integration point — where multi-codex / multi-corpus synthesis happens. The compendium author:

1. **Identifies inputs.** Which codices, which codex records, which artifacts. Often starts by selecting a small set of seed records across one or more codices and following references outward.
2. **Picks a slug.** The compendium record's `id` is an author-chosen slug (also the filename stem; e.g., `01-introduction`, `inspection-procedure`).
3. **Drafts chapters.** Markdown prose with:
   - **Footnote citations** for downward references: `text[^N]` with `[^N]: corpus://{hash}` (artifact; provenance form `corpus://{name}/{hash}` when needed) or `[^N]: codex://{name}/{uuid}` (codex record).
   - **Functional URI embeds** for inline artifact-derived views: `![[corpus://{hash}?params]]`.
   - **Wikilinks** for intra-compendium peer-chapter references: `[[slug]]`.
4. **Applies the lowest-source preference.** When a compendium record is about a particular subject and an artifact directly says it, cite the artifact (`corpus://...`), not a codex record that paraphrases it. When the compendium needs interpretation/synthesis that no single artifact provides, cite the codex record that already did that synthesis (`codex://...`). Codex-record citations are bound to the cited codex's current instance — codex regeneration mints fresh UUIDs and dependent compendiums must be re-built (spec §2.5, §6.5).

---

## 5. Runtime resolution

Reference resolution is the runtime's job. The runtime mounts a set of codices, corpora, and compendiums and answers reference lookups for wikilinks, footnote URIs, and embed URIs.

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

The per-primitive resolution algorithm is canonical in spec §3.6; the runtime applies it as written. Implementation notes:

- **Lookup performance.** Wikilinks are intra-layer: a codex's UUIDv7 → record-path map and a corpus's blake3 → record-path map are both built at mount time (§5.1) and queried in constant time. A compendium's slug → record-path map is similar. Footnote URIs (`corpus://{hash}`, `codex://{name}/{uuid}`) parse to (corpus-name?, hash) or (codex-name, uuid) tuples and resolve against the same maps.
- **Cross-corpus blake3 identity.** When multiple corpora are loaded, a bare `corpus://{hash}` URI may match more than one loaded corpus. Because content addressing means the bytes are by definition identical, the runtime resolves to either copy. Compendium URIs use the qualified `corpus://{name}/{hash}` form when provenance disambiguation matters.
- **Display text and APA resolution.** Wikilink `|display-text` portions are preserved through resolution and used at render time. Footnote URIs resolve at build/export time into APA-style citation text drawn from the target record's frontmatter (artifact: `byline`, `published_date`, `title`, primary URI from `uris[]`; codex record: `title`, `description`, codex name).

### 5.3 Unresolved-reference handling

When a reference cannot be resolved, the runtime should:

- In Obsidian-style raw browsing, fall back to the display text or footnote-body URI and surface the reference as broken (Obsidian's standard treatment).
- In compiled outputs, log the unresolved reference and substitute a clearly-marked fallback ("[unresolved]" or similar). Don't silently drop it.
- In tooling backlink panels, list unresolved references as authoring follow-ups.

### 5.4 Collision detection

Same blake3 in two corpora — fine, they are by definition the same bytes; the corpora may both have it. The reference resolves to either copy.

Same UUIDv7 in two codices — astronomically unlikely. If it does occur, the runtime should warn and let the qualified `codex://{name}/{uuid}` URI resolve unambiguously.

---

## 6. Codex regeneration

Regeneration is a contemplated future workflow: re-derive an entire codex from a corpus snapshot plus authoring prompts. Not part of v10's required behavior, but the design supports it.

### 6.1 What regeneration preserves

- **Codex name.** The codex itself keeps its identity (the directory).
- **Tag vocabulary.** The codex's `codex.yaml` and any tag-conventions reference survive regeneration unchanged unless the operator explicitly amends them.

### 6.2 What regeneration replaces

- **UUIDs.** Each regeneration mints fresh UUIDs. The set of records is replaced wholesale.
- **Body prose.** A new authoring pass produces new prose.
- **Wikilinks within the codex.** A regenerated codex record may reference different artifacts or different sibling records depending on what the synthesis prompts produce.

### 6.3 Compendium cascade

A regenerated codex is a new instance: its UUIDs are fresh, so any compendium citing `codex://{this-codex}/{uuid}` becomes invalidated and must be re-built against the regenerated codex. Tooling SHOULD:

1. Identify dependent compendiums before triggering regeneration (by walking each loaded compendium's footnote URIs for `codex://{this-codex}/...` matches).
2. Surface the cascade to the operator for confirmation.
3. After codex regeneration completes, re-run compendium synthesis for each dependent compendium against the new codex.

### 6.4 When regeneration makes sense

- A codex was built from an early corpus snapshot and has drifted from the current corpus state.
- An authoring prompt has been substantially improved.
- A new model is meaningfully better and the cost of re-running is justified.

A codex that is hand-authored record-by-record without a regeneration prompt is not regenerable — it's a hand-built collection, like any other. Regeneration is opt-in and applies to codices whose authoring is procedural enough to support it.

---

## 7. Build process

The build process compiles outputs (mdbook, static site, browsable vault) for a particular target — typically a compendium plus its connected codices and corpora.

### 7.1 Inputs

- A target compendium (or a codex, if the goal is to publish a codex on its own).
- The runtime's mounted set of codices and corpora.
- Build configuration (output format, theme, etc.).

### 7.2 Resolution pass

1. Walk the target's body (and all body fragments: chapters, sub-pages).
2. Resolve every wikilink (intra-layer) per the rules in §5.
3. Resolve every footnote URI: parse `corpus://{hash}` or `codex://{name}/{uuid}`, look up the target record, generate APA-style citation text from the target's frontmatter, substitute into the footnote body.
4. Resolve every embed URI: compute the functional transformation (page extract, framegrab, crop), write the derived artifact to the build's output directory, substitute the path.
5. Build navigation: tag indexes (codex), chapter ordering (compendium), navigation menus, backlink panels.
6. Generate origin-URI redirects: for every artifact referenced by the target, expose all of its `uris[]` entries as redirect entries pointing at the artifact's compiled-output path.

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

- **Sharding crossover** (consolidated). At what record count does single-level hex-prefix sharding stop being adequate, and how do tooling rebalance moves work? Same question on both the corpus and codex sides; the canonical write-up is `impl-corpus.md §6`. Codex-side specifics: the threshold likely lands at a `codex.yaml` flag rather than `corpus.toml`.
- **Compendium chapter granularity.** A compendium could be a single compendium record or many. Convention: split chapters into separate records when the chapter is large enough that scrolling through it gets in the way; otherwise keep the compendium as a small set of records. The build process flattens or paginates per the target output format.
- **Codex regeneration tooling.** When sjrahn wants to actually do a regeneration, the tooling will need: corpus-snapshot pinning, prompt versioning, dependent-compendium cascade detection (§6.3), and a diff report. Out of scope for v10 implementation.
