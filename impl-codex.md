# Athenaeum — Codex Implementation Guide

**Status:** living document, **non-normative**. Updates as implementation matures.

**Companion to:** [`spec-athenaeum.md`](spec-athenaeum.md), the authoritative architecture. The spec fixes exactly one thing about the codex layer — **the contract by which a codex consumes the corpus** (the `corpus://` functional-URI scheme, the read API, and derived views; spec §2.3). Everything in *this* guide is the **reference convention**: one good way to build a codex and its deliverables. A codex embeds an expert agent that owns its own structure, so it may follow this convention, extend it, or replace it — whether any of it generalizes across all codices is deliberately left open. The corpus layer the codex consumes is specified by [`spec-corpus.md`](spec-corpus.md); the corpus/artifact-layer implementation counterpart is [`impl-corpus.md`](impl-corpus.md).

If this guide ever conflicts with the spec's corpus-consumption contract, the spec wins and this guide gets corrected. On everything *internal* to a codex, this guide is advisory.

---

## 1. Scope

This guide covers the codex side: how a codex is laid out on disk, how its expert agent curates knowledge from the corpus, how the runtime resolves references, how a codex regenerates, and how it builds its deliverables — including an *integrated reference work* (the role earlier revisions called a "compendium").

What is fixed vs what is convention:

- **Fixed by the spec.** How a codex reaches into the corpus: downward-only footnote citations and functional-URI embeds over `corpus://` (spec §2.3, §3.6, §3.7). A codex never references another codex's internals; cross-codex use is citation of a *published output* (`codex://{name}/{id}`).
- **Convention (this guide).** The codex's internal record format, on-disk layout, authoring workflow, the shape of its deliverables, and the build process. Agent-owned; change freely.

---

## 2. Codex directory layout (reference convention)

A codex is a domain-scoped knowledge repository that embeds an expert agent. In the reference convention its on-disk shape is:

```
codex-{name}/
├── codex.yaml                 — codex-level metadata (optional)
└── records/
    ├── {first-2-of-id}/       — sharded by first 2 hex chars of the UUIDv7 id
    │   └── {full-uuidv7}.md
    └── ...
```

**Sharding policy.** Codex records are sharded one level deep by the first two hex characters of the UUIDv7 id, mirroring the corpus's artifact sharding. Flat layout is acceptable below ~1k records; sharded once a codex's record count crosses that threshold. The full UUIDv7 is kept in the filename so files are self-identifying when copied outside their shard. UUIDv7 ids are time-ordered, so shard distribution remains roughly uniform as the codex grows.

**`codex.yaml`** is optional and may carry codex-level metadata such as:

```yaml
name: codex-personal
display_name: "Personal Codex"
description: "..."
tag_vocabulary_url: "..."     # optional pointer to a tag-conventions doc
```

None of these fields are mandated. Tooling should treat `codex.yaml` as best-effort hints — the codex name (the directory) is the authoritative identity.

**No top-level `artifacts/`, `schema/`, or `capture/` in a codex.** Those are corpus-side. A codex consumes artifacts from corpora it doesn't own, through the `corpus://` contract.

A codex whose deliverable is *not* a record set — a single tuned document, an index, an answering service — may lay itself out entirely differently. This layout is the convention for a record-structured codex, not a requirement.

---

## 3. Authoring workflows (reference convention)

Authoring a codex record follows the spec's `Author` agent contract (§5.4) — the codex's embedded expert agent doing synthesis. The implementation:

1. **Pick the codex.** The author works in exactly one codex per invocation.
2. **Pick a synthesis target.** A topic that benefits from authored prose — a how-to guide, a concept page, a synthesis across several artifacts. The trigger may come from the curator, a tag cluster, operator direction, or a gap in a deliverable.
3. **Mint a UUIDv7.** The codex record's `id` is a freshly minted UUIDv7. Time-ordered ids let tooling list a codex's records in creation order without reading the body.
4. **Compose the body.** Footnote-cite artifacts (`text[^N]` with `[^N]: corpus://{hash}`, optionally `corpus://{hash}#anchor` or `corpus://{hash}?page=4`). Embed artifact content via functional URI (`![[corpus://{hash}?params|alt text]]`) for derived views (PDF page extraction, video framegrab, image crop). Wikilink peer codex records via `[[uuid]]`.
5. **Reference downward, not sideways.** A codex record references downward to artifacts and locally to peer records in the same codex (spec §2.4). It does not reach into another codex. When a *deliverable* needs another codex's already-synthesized output, it cites that output by `codex://{name}/{id}` — a citation of a published result (§4), not something woven into internal records.
6. **Save** under `records/{first-2-of-id}/{full-uuidv7}.md`. Frontmatter is just `id`, `title`, `description`, `status`, `tags` (spec §3.1.3). Credibility weighting is consulted by reading the credibility-signal classifications on the evidentiary artifacts a record cites (a corpus-layer derived view).

---

## 4. Integrated reference deliverables (the "compendium" pattern)

Earlier revisions of the architecture made the integrated reference work — a published, opinionated reference compiled across codices and corpora — its own layer (the *compendium*). It is no longer a separate layer; it is **one kind of deliverable a codex can produce**, documented here as a candidate pattern. An *integrating codex* is simply a codex whose domain is "a coherent reference work over these sources."

### 4.1 Layout

An integrated-reference deliverable is a set of author-named chapters:

```
codex-{name}/                  — or a dedicated build-output directory
└── chapters/   (or records/)
    ├── 01-introduction.md     — author-chosen filenames (chapter style)
    ├── 02-history.md
    └── ...
```

**Naming.** Chapter filenames are an authoring choice — pick a chapter-style name (`overview.md`, `01-introduction.md`). Numeric prefixes are conventional for ordering but not required; the build process (§7) determines navigation order from frontmatter or directory listing per the target output format. Chapter sets are typically small enough that no sharding is needed; flat is the convention.

### 4.2 Authoring an integrated reference

1. **Identify inputs.** Which corpora, which artifacts, and which other codices' published outputs. Often starts by selecting a small set of seed records and following references outward.
2. **Pick a chapter name.** The chapter's `id` is an author-chosen slug (also the filename stem; e.g., `01-introduction`, `inspection-procedure`).
3. **Draft chapters.** Markdown prose with:
   - **Footnote citations** for downward references: `text[^N]` with `[^N]: corpus://{hash}` (artifact; provenance form `corpus://{name}/{hash}` when needed) or `[^N]: codex://{name}/{id}` (another codex's published output).
   - **Functional-URI embeds** for inline artifact-derived views: `![[corpus://{hash}?params]]`.
   - **Wikilinks** for intra-deliverable peer-chapter references: `[[slug]]`.
4. **Apply the lowest-source preference.** When an artifact directly says it, cite the artifact (`corpus://...`), not a codex output that paraphrases it. When you need synthesis another codex already did, cite that codex's output (`codex://...`). Cross-codex citations are bound to the cited codex's current instance — if it regenerates, the citing deliverable re-resolves and rebuilds (§6).

### 4.3 Synthesis practice

The guidance earlier revisions called "synthesis principles" is **agent practice** for an integrating codex, not contract:

- **Cite the lowest source that suffices** — artifact over codex-output paraphrase.
- **Represent disagreement** — present conflicting positions with whatever credibility-signal classifications the corpus carries (a corpus-layer derived view; see `spec-corpus.md`).
- **Aggregate patterns** — capture the shared phenomenon rather than citing each artifact individually.
- **Weight by credibility signals** — records carrying classifications the codex treats as authoritative (`peer-reviewed`, `community-validated`) outweigh weaker ones (`preprint`, `anecdotal-claim`). The weighting is the codex author's policy.
- **Respect issues** — records with unresolved `critical`/`major` issues are weighted down and gaps noted.
- **Lean on already-synthesized codex outputs** and **tier-3 similarity** to surface cross-modal connections tags alone miss.

A **synthesis system prompt** — encoding scope boundaries, key relationships, source-selection criteria, and the weighting policy — is the natural home for a codex's editorial voice, iterated **synthesize → review → refine prompt → re-synthesize**.

---

## 5. Runtime resolution

Reference resolution is the runtime's job. The runtime mounts a set of codices and corpora and answers reference lookups for wikilinks, footnote URIs, and embed URIs.

### 5.1 Mounting

The runtime configuration declares which codices and corpora are accessible. Both can be local directories or remote URIs (server-mounted). The configuration is the join — codices and corpora don't declare runtime joins in their own data.

A typical configuration:

```yaml
corpora:
  - name: corpus              # all public captures
    path: /path/to/corpus
  - name: corpus-private      # personal documents
    path: /path/to/corpus-private
codices:
  - name: codex-personal
    path: /path/to/codex-personal
  - name: codex-shared
    path: /path/to/codex-shared
```

Multiple codices coexist with no relationship to one another beyond what cross-codex output citations express.

### 5.2 Resolution rules

The per-primitive resolution algorithm is canonical in spec §3.6; the runtime applies it as written. Implementation notes:

- **Lookup performance.** Wikilinks are intra-container: a codex's UUIDv7 → record-path map and a corpus's blake3 → record-path map are both built at mount time (§5.1) and queried in constant time. Footnote URIs (`corpus://{hash}`, `codex://{name}/{id}`) parse to (corpus-name?, hash) or (codex-name, id) tuples and resolve against the same maps.
- **Cross-corpus blake3 identity.** When multiple corpora are loaded, a bare `corpus://{hash}` URI may match more than one. Because content addressing means the bytes are by definition identical, the runtime resolves to either copy. URIs use the qualified `corpus://{name}/{hash}` form when provenance disambiguation matters.
- **Display text and APA resolution.** Wikilink `|display-text` portions are preserved through resolution and used at render time. Footnote URIs resolve at build/export time into APA-style citation text drawn from the target's metadata (artifact: `byline`, `published_date`, `title`, primary URI from `uris[]`; codex output: `title`, `description`, codex name).

### 5.3 Unresolved-reference handling

When a reference cannot be resolved, the runtime should:

- In Obsidian-style raw browsing, fall back to the display text or footnote-body URI and surface the reference as broken.
- In compiled outputs, log the unresolved reference and substitute a clearly-marked fallback ("[unresolved]" or similar). Don't silently drop it.
- In tooling backlink panels, list unresolved references as authoring follow-ups.

### 5.4 Collision detection

Same blake3 in two corpora — fine, they are by definition the same bytes; the reference resolves to either copy. Same UUIDv7 in two codices — astronomically unlikely; if it occurs, the runtime should warn and let the qualified `codex://{name}/{id}` form resolve unambiguously.

---

## 6. Codex regeneration

Regeneration is a contemplated workflow: re-derive an entire codex from a corpus snapshot plus authoring prompts. The design supports it; it is opt-in.

### 6.1 What regeneration preserves

- **Codex name.** The codex keeps its identity (the directory).
- **Tag vocabulary.** The codex's `codex.yaml` and any tag-conventions reference survive unchanged unless the operator explicitly amends them.

### 6.2 What regeneration replaces

- **Internal ids.** Each regeneration mints fresh UUIDs. The set of records is replaced wholesale.
- **Body prose.** A new authoring pass produces new prose.
- **Intra-codex references.** A regenerated record may reference different artifacts or different sibling records depending on what the synthesis prompts produce.

### 6.3 Downstream cascade

A regenerated codex is a new instance: its ids are fresh, so any *other* deliverable or codex that cites `codex://{this-codex}/{id}` is invalidated and must re-resolve against the regenerated codex. Because nothing in the architecture above a codex depends on a codex's internal ids (spec §2.5), this cascade is bounded to the explicit citers. Tooling SHOULD:

1. Identify dependents before triggering regeneration (by walking each loaded codex's footnote URIs for `codex://{this-codex}/...` matches).
2. Surface the cascade to the operator for confirmation.
3. After regeneration completes, re-run the dependent builds against the new instance.

### 6.4 When regeneration makes sense

- A codex was built from an early corpus snapshot and has drifted from the current corpus state.
- An authoring prompt has been substantially improved.
- A new model is meaningfully better and the cost of re-running is justified.

A codex hand-authored record-by-record without a regeneration prompt is not regenerable — it's a hand-built collection. Regeneration applies to codices whose authoring is procedural enough to support it.

---

## 7. Build process

The build process compiles a codex's **deliverable** for a target — a browsable knowledge vault, a published integrated reference (§4), an index, a JSON API.

### 7.1 Inputs

- The target codex (and, for an integrating codex, the other codices whose outputs it cites).
- The runtime's mounted set of codices and corpora.
- Build configuration (output format, theme, etc.).

### 7.2 Resolution pass

1. Walk the target's body (and all body fragments: chapters, sub-pages).
2. Resolve every wikilink (intra-container) per the rules in §5.
3. Resolve every footnote URI: parse `corpus://{hash}` or `codex://{name}/{id}`, look up the target, generate APA-style citation text from its metadata, substitute into the footnote body.
4. Resolve every embed URI: compute the functional transformation (page extract, framegrab, crop), write the derived artifact to the build's output directory, substitute the path.
5. Build navigation: tag indexes, chapter ordering, navigation menus, backlink panels.
6. Generate origin-URI redirects: for every artifact referenced by the target, expose all of its `uris[]` entries as redirect entries pointing at the artifact's compiled-output path.

### 7.3 Output formats

The format is the codex's choice. Common ones:

- **mdbook** — book-shaped published output, natural for an integrated reference.
- **Static site** — flexible HTML, often the default for Obsidian Publish-style deployments.
- **Browseable Obsidian vault** — symlinks/copies into one vault that mounts the target plus its dependencies for human browsing.
- **JSON API** — structured outputs consumable by tooling.

### 7.4 Ephemeral vs durable outputs

Functional-URI results, derived images, transcoded media — all ephemeral. They live in the build output directory and are rebuildable from the underlying artifact. Cache them but don't treat them as records.

---

## 8. Open implementation questions

- **Sharding crossover** (consolidated). At what record count does single-level hex-prefix sharding stop being adequate, and how do tooling rebalance moves work? Same question on both the corpus and codex sides; the canonical write-up is `impl-corpus.md §6`. Codex-side specifics: the threshold likely lands at a `codex.yaml` flag.
- **Deliverable granularity.** An integrated reference could be a single chapter or many. Convention: split chapters into separate files when a chapter gets large enough that scrolling through it gets in the way; otherwise keep the deliverable as a small set. The build process flattens or paginates per the target output format.
- **Codex regeneration tooling.** When sjrahn wants to actually do a regeneration, the tooling will need: corpus-snapshot pinning, prompt versioning, dependent-citer cascade detection (§6.3), and a diff report.
- **Generalizing the codex form.** Whether the record-structured reference convention here becomes the shared shape for all codices, or each expert agent keeps its own internal model, is the open question the two-layer architecture deliberately leaves to experience.
