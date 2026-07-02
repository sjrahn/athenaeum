---
spec_id: ATH-CODEX
title: "Codex Specification"
version: 1.0
status: current
license: "CC BY-SA 4.0"
date_created: 2026-07-02
date_modified: 2026-07-02
---

# Codex Specification

## 1. Overview

### 1.1 What this is

A **codex** is a targeting of facts that compiles to prose. It selects a scope from the ledger hubs (`spec/ledger.md`), synthesizes that knowledge into an editorial voice, and produces a deliverable — an Obsidian vault of generated notes, rendered as a published site with every reference resolved and every media citation rastered.

A codex owns **no knowledge**. Facts, claims, evidence, and interpretations live in the ledger, authored once; a codex is a *view with a voice*. This is what makes codices cheap: a new compendium for a new audience or purpose is a scope declaration and an editorial stance, never re-authored knowledge. Many codices over the same ledger — different audiences, different depths, different languages even — is the expected case.

### 1.2 The compilation chain

```
ledger hubs        facts + interpretations              (authored knowledge — not owned here)
    ↓  target      the codex's scope selects its slice
codex notes/       generated Obsidian prose             (regenerable, provenance-tracked)
    ↓  build       resolve · raster · link
deliverable        published site (reference: Quartz)   (fully resolved, tenancy-safe)
```

Everything below the ledger is **regenerable**. Delete a note — or the whole vault — and rebuild it losslessly: every sentence traces to a fact, every fact traces to bytes.

### 1.3 Fixed vs codex-owned

**Fixed by this spec:** the codex manifest (§2); scope semantics (§3); note provenance and the no-unbacked-prose rule (§4); the build's resolution obligations (§5); tenancy profiles (§6); validation (§7).

**Codex-owned:** the domain and audience; the editorial voice and note templates; vault organization; site theme and deployment; publication cadence. Taste is the codex's entire job.

## 2. The codex manifest — `codex.yaml`

```yaml
name: codex-{name}
display_name: "…"
description: >-
  …

ledgers:                        # the hubs this codex targets, in precedence order
  - ledger
  - ledger-private              # targeting a private hub makes the codex private-citing

scope:                          # what slice of the ledger this codex compiles (§3)
  types: [vehicle, component, system, part, issue, campaign]
  roots: [pontiac-g8]           # subgraph roots; traversal per §3
  tags: []                      # optional additional selectors

profiles:                       # build profiles (§6); "private" is implicit and unrestricted
  public:
    redact: exclude             # exclude | stub — how private-evidence content renders
```

- `ledgers` names manifest-registered hubs (`spec/athenaeum.md` §2.3). A codex targeting any private hub is a **private-citing codex** and inherits the tenancy obligations of §6.
- The manifest is a tooling contract: scope selection, note generation, build, and validation all read it. Nothing may hardcode hub paths.

## 3. Scope — targeting the ledger

A codex's scope is the set of ledger facts it compiles, computed from selectors:

- **`types`** — include every fact of the listed types.
- **`roots`** — include the listed entities and their subgraph: claims' `object` targets, edge `subject`/`participants`, transitively, within the type filter.
- **`tags`** — reserved for ledger-side topical tagging (optional selector; a codex needing finer selection than types + roots SHOULD propose ledger tags rather than maintaining hand lists).
- Selectors are **additive**; the computed scope is materialized by tooling (deterministic) and is the exact input set for note generation. An explicit `exclude:` list exists for editorial carve-outs and is visible in the manifest — silent omission is not a mechanism.

Interpretations riding on in-scope facts (their `about` intersects the scope) are part of the scope: a codex renders the epistemic state honestly, including standing corrections and open questions, marked as interpretive (§4).

## 4. Notes — the generated vault

Notes are Obsidian-flavored markdown under `notes/`, generated from the scoped facts by the codex's templates and voice. Frontmatter is the provenance contract:

```yaml
---
entity: pontiac-g8               # the fact this note anchors
generated_from:                  # the EXACT ledger files this note derives from
  - ledger/facts/vehicle/pontiac-g8.json
  - ledger-private/facts/vehicle/pontiac-g8.json
  - ledger/interpretations/base-v6-transmission-is-5l40e.json
updated: 2026-07-02
---
```

Rules:

- **No unbacked prose.** A note asserts nothing without a backing claim in `generated_from`. Editorial connective tissue (transitions, emphasis, ordering) is voice; new assertions are not.
- **Claims render with their epistemic state.** A `provisional` claim does not read like a `confirmed` one; interpretive content (from interpretations) is visibly marked as such. The ladder survives into prose — that is the honesty the ledger bought.
- **Citations carry through**: every rendered assertion footnotes the `corpus://` evidence of its backing claim(s). Wikilinks target peer notes in the same vault.
- **Regenerate, don't hand-drift.** `generated_from` is how staleness is detected; validation compares note age against its ledger sources.

## 5. The build

The build compiles the vault into the deliverable. The reference deployment is **Quartz** (an Obsidian-vault static-site renderer); the obligations below are renderer-independent:

1. **Resolve every `corpus://` footnote** into a human citation (title / source / date drawn from the record's metadata), linking the evidence anchor where the profile permits.
2. **Raster every functional-URI embed**: `![[corpus://{hash}?page=4&bbox=…]]`, `?frame=`, `?time_range=` — materialized through the corpus resolver into static assets in the site (the resolver and its cache already produce exactly these derivations; the build copies them in and rewrites the reference).
3. **Resolve wikilinks** natively (vault-internal links become site links; Quartz handles this).
4. **Surface provenance**: each note's rendered page exposes its `generated_from` chain — the reader can walk prose → fact → claim → evidence → bytes.
5. **Fail loudly on unresolvables.** A citation that no longer resolves fails the build (or renders an explicit broken-reference marker in dev builds); silent drops are forbidden.

The build is deterministic (`spec/athenaeum.md` §6.1): same vault + same ledger + same corpus state = same site.

## 6. Profiles and tenancy

The tenancy rule follows content into deliverables: **a published site may only contain what its audience may see.**

- The implicit **private profile** (the owner's own vault/site) renders everything the codex targets.
- A **public profile** of a private-citing codex MUST NOT leak private content — not evidence bytes, not quotes, not fact values, not ids. Per `codex.yaml`, private-backed content is either **excluded** (notes or note sections derived from private-hub facts are omitted) or **stubbed** (the assertion renders with a "private evidence" marker and no content). Rastered assets from the private corpus never enter a public build.
- Validation includes a **leak check** on public-profile output: no private-hub ids, no `corpus-private` URIs, no private-corpus assets in the built site.

A codex targeting only the public ledger has no restrictions; its public and private profiles coincide.

## 7. Validation

Deterministic, per-codex:

- Manifest sanity: declared ledgers exist; scope selectors resolve; excludes are visible.
- Scope integrity: every note's `generated_from` files are in the computed scope and exist; no note without a backing entity; staleness (note older than any source).
- Prose honesty: every note section maps to backing claims (tooling-assisted; the no-unbacked-prose rule is ultimately editorial discipline plus spot-verification).
- Build: all references resolve; rastered assets present; the public-profile leak check (§6).

*(Implementation note, non-normative: codex tooling ships with the shared ledger package as `ath codex …` — scope materialization, note scaffolding, build, leak check.)*

---

## Appendix A: What a codex is not (non-normative)

- Not a knowledge store — knowledge lives in the ledger; a codex with hand-authored facts in its notes is a defect.
- Not a mirror — a codex that renders *every* scoped fact with no editorial selection or voice is just a ledger report; the value of the layer is curation for an audience.
- Not an integration API — other systems wanting the knowledge read the ledger (`ledger://`, the ledger package), not a codex's prose.
