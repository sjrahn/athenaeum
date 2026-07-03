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

A **codex** is a targeting of facts that compiles to prose. It selects a scope from the ledger (`spec/ledger.md`), synthesizes that knowledge into an editorial voice, and produces a deliverable — an Obsidian vault of generated notes, rendered as a published site with every reference resolved and every media citation rastered.

A codex owns **no knowledge**. Facts, claims, evidence, and interpretations live in the ledger, authored once; a codex is a *view with a voice*. This is what makes codices cheap: a new compendium for a new audience or purpose is a scope declaration and an editorial stance, never re-authored knowledge. Many codices over the same ledger — different audiences, different depths, different languages even — is the expected case.

### 1.2 The compilation chain

```
the ledger         facts + interpretations              (authored knowledge — not owned here)
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

scope:                          # what slice of the ledger this codex compiles (§3)
  types: [vehicle, component, system, part, issue, campaign]
  roots: [pontiac-g8]           # subgraph roots; traversal per §3
  tags: []                      # optional additional selectors

profiles:                       # build profiles (§6); "private" is implicit and unrestricted
  public:
    redact: exclude             # exclude | stub — how private-backed content renders
```

- Every codex targets **the ledger** (the manifest-registered knowledge layer, `spec/athenaeum.md` §2.3). Whether a codex's scope contains private-backed content is a property of the scoped claims' derived sensitivity (`spec/ledger.md` §6.4), not a manifest declaration — §6's obligations attach by content.
- The manifest is a tooling contract: scope selection, note generation, build, and validation all read it. Nothing may hardcode member paths.

## 3. Scope — targeting the ledger

A codex's scope is the set of ledger facts it compiles, computed from selectors:

- **`types`** — include every fact of the listed types.
- **`roots`** — include the listed concepts and their subgraph: claims' `object` targets, edge `subject`/`participants`, transitively, within the type filter.
- **`tags`** — reserved for ledger-side topical tagging (optional selector; a codex needing finer selection than types + roots SHOULD propose ledger tags rather than maintaining hand lists).
- Selectors are **additive**; the computed scope is materialized by tooling (deterministic) and is the exact input set for note generation. An explicit `exclude:` list exists for editorial carve-outs and is visible in the manifest — silent omission is not a mechanism.

Interpretations riding on in-scope facts (their `about` intersects the scope) are part of the scope: a codex renders the epistemic state honestly, including standing corrections and open questions, marked as interpretive (§4).

## 4. Notes — the generated vault

Notes are Obsidian-flavored markdown under `notes/`, generated from the scoped facts by the codex's templates and voice. Frontmatter is the provenance contract:

```yaml
---
concept: pontiac-g8              # the fact this note anchors
generated_from:                  # the EXACT ledger files this note derives from
  - ledger/facts/vehicle/pontiac-g8.json
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
6. **Emit the build certificate.** Every build freezes its reproducibility tuple: the codex commit (the vault as compiled), the ledger commit, the touch identity of every corpus record cited or rastered, the mirror snapshot version of every reference dataset cited (`spec/ledger.md` §6.5), the tooling version, and the profile. Certificates are **write-only evidence, never working state**: rebuilding from the same tuple MUST reproduce the site — that equality is the audit — and ledger or corpus movement since the last certificate is a *detected transition*, surfaced as the regeneration worklist (`ath ledger worklist`), never discovered by readers.

The build is deterministic (`spec/athenaeum.md` §6.1): same tuple = same site — the certificate is that guarantee made citable. (Note *generation* above the build is interpretive and not byte-reproducible; the certificate pins the vault commit precisely so the deterministic half is auditable and the interpretive half gets an honest staleness signal.)

## 6. Profiles and tenancy

The tenancy rule follows content into deliverables: **a published site may only contain what its audience may see.** Privacy is a *derived property of claims* (`spec/ledger.md` §6.4 — evidence resolving only in private corpora, or an asserted upward override); the codex layer is where that metadata becomes a wall.

- The implicit **private profile** (the owner's own vault/site) renders everything the codex targets.
- A **public profile** MUST NOT leak private-backed content — not evidence bytes, not quotes, not fact values, not ids. Per `codex.yaml`, private-backed content is either **excluded** (notes or note sections derived from private-backed claims are omitted; a fully-private fact file is omitted entirely, id included) or **stubbed** (the assertion renders with a "private evidence" marker and no content). Rastered assets from a private corpus never enter a public build.
- Validation includes a **leak check** on public-profile output: no private-backed claim content, no ids of fully-private fact files, no URIs or assets resolving only in a private corpus. This check is the tenancy boundary of the knowledge layer — the ledger itself is one repository and carries no wall (`spec/ledger.md` §1.2).

A codex whose scope contains no private-backed claims has no restrictions; its public and private profiles coincide.

**Tenancy is the mandatory profile axis, not the only one.** A profile may gate visibility on any attribute derivable from claim metadata — the general mechanism is a filter over the scoped claims and their evidence. The exemplar: a fiction codex over a novel corpus gates on **narrative position** — a fact's introduction point is its earliest evidence anchor, so a "reader at chapter N" profile renders only knowledge the story has revealed by that point, and the companion wiki unfolds with the reader without a separate spoiler mechanism. Audience tiers and progress gates are the same filter wearing different predicates.

## 7. Validation

Deterministic, per-codex:

- Manifest sanity: scope selectors resolve; excludes are visible.
- Scope integrity: every note's `generated_from` files are in the computed scope and exist; no note without a backing fact; staleness (note older than any source).
- Prose honesty: every note section maps to backing claims (tooling-assisted; the no-unbacked-prose rule is ultimately editorial discipline plus spot-verification).
- Build: all references resolve; rastered assets present; the public-profile leak check (§6); the last certificate re-derives (§5), with ledger or corpus movement since it reported as the rebuild worklist.

*(Implementation note, non-normative: codex tooling ships with the shared ledger package as `ath codex …` — scope materialization, note scaffolding, build, leak check.)*

---

## Appendix A: What a codex is not (non-normative)

- Not a knowledge store — knowledge lives in the ledger; a codex with hand-authored facts in its notes is a defect.
- Not a mirror — a codex that renders *every* scoped fact with no editorial selection or voice is just a ledger report; the value of the layer is curation for an audience.
- Not an integration API — other systems wanting the knowledge read the ledger (`ledger://`, the ledger package), not a codex's prose.
