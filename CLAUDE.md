# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Starting a session on this repo

If you are Claude Code and this is the start of a session working on Athenaeum, **invoke `/athenaeum` before doing anything else.** That skill boots the project's principal-developer persona, loads the project state / logbook / gotchas from `.claude/skills/athenaeum/`, and runs a short git-status check so you pick up exactly where the last session left off. The skill files are the source of truth for project state and history — don't rely on auto-memory for that.

## Repository layout

```
athenaeum/
├── spec-athenaeum.md        # Architecture spec (v11) — three layers, codex + compendium contracts; corpus layer defers to spec-corpus.md
├── spec-corpus.md           # Corpus spec (ATH-CORPUS v1.0) — artifact record format, body blocks, schemas, functional URIs
├── impl-corpus.md           # Implementation guide for the corpus / artifact-layer pipeline
├── impl-codex.md            # Implementation guide for the codex layer + compendium build
├── docs/
│   ├── CONTENT-TYPES.md     # Content type enumeration and metadata attributes
│   ├── NEW-CORPUS.md        # Corpus planning notes
│   ├── APPLE-CLIENT-PLAN.md # Phased plan for the multiplatform Apple client
│   └── APPLE-UX-NOTES.md    # Apple-client UX notes
├── web/                     # Corpus Console — Angular v22 SPA (the CURRENT viewer). Standalone
│   │                        #   components on @angular/cdk + @angular/aria; signals + httpResource;
│   │                        #   design tokens in src/styles/tokens.css. Responsive (760px breakpoint).
│   └── src/app/{core,shell,browser,viewer,chips}/
├── tools/corpus/            # Python corpus tooling (ath-corpus) — the data layer + the new API
│   └── src/corpus/api/      # FastAPI read API behind the `[api]` extra (corpus.api) — the CURRENT server
├── Cargo.toml               # Workspace root (RETIRED — see below)
├── crates/                  # RETIRED Rust stack (egui/axum). Superseded by web/ + corpus.api; slated
│   ├── ath-core/            #   for deletion once parity is confirmed. Don't extend; pre-v1.0 model.
│   ├── ath-gui/             #   (old egui viewer)
│   └── ath-server/          #   (old axum server — source/document/credibility/norm_conf model)
└── .claude/skills/athenaeum/ # Skill state, logbook, gotchas
```

**The viewer/server stack is now `web/` (Angular) + `tools/corpus`'s `corpus.api` (FastAPI over the corpus library).** The Rust `crates/` are retired — they serve the old corpus model (source/document kind, credibility, norm_conf) the v1.0 corpus layer dropped. Don't build on them.

## Common commands

```bash
# Run the API (FastAPI over the corpus library) — serves /v1 on :8099.
# Map corpus ids to roots (one server can front several corpora). Needs the [api] extra.
cd tools/corpus && uv run --extra api corpus-api serve \
  --corpus corpus=../../corpus --corpus corpus-test=../../corpus-test \
  --host 0.0.0.0 --port 8099

# Run the Angular viewer (dev server). The API base auto-follows window.location.hostname:8099.
# Node >= 22.22.3 required for Angular v22 (a local Node 24 lives at ~/.local/opt/node — see gotchas).
cd web && PATH=$HOME/.local/opt/node/bin:$PATH npx ng serve --host 0.0.0.0 --port 4200 --allowed-hosts true

# Build / lint the web app
cd web && PATH=$HOME/.local/opt/node/bin:$PATH npx ng build   # (ng lint)

# Corpus CLI (unchanged) + the API's base-install guard (gotcha #24 — must stay green)
cd tools/corpus && uv run python -c "import corpus.draft"
```

## Notable web/app stack (the Corpus Console)

- **Angular v22** — standalone components, signals, **`httpResource`** for reactive fetch, `ChangeDetectionStrategy.OnPush`, native control flow (`@if`/`@for`/`@switch`). Follow the official `angular-developer` skill (`npx skills add https://github.com/angular/skills`).
- **`@angular/cdk` + `@angular/aria`** — component base (no Bootstrap/Material/Tailwind). `cdk/layout` BreakpointObserver drives the 760px mobile breakpoint (`core/viewport.ts`). The `@angular/aria` *headless directive* adoption (menu/listbox/tabs) is a deferred a11y pass — current components carry hand-rolled ARIA semantics.
- **Design tokens** — `web/src/styles/tokens.css`, ported verbatim from the Claude Design system (JetBrains Mono + IBM Plex Sans; warm-paper light / ink dark; square corners; hairlines; no shadows except true floats; no animation). The single source of visual truth — don't restyle.
- **Real artifact rendering** — PDFs via the API's `resolve?page=N` rasterization (no pdf.js), native `<video>`/`<audio>` (range-streamed), `<img>`, sandboxed `<iframe>` for HTML snapshots, fetched text for md/json/eml.

## Key design principles

- **The specs are `spec-athenaeum.md` (architecture + codex/compendium contracts) and `spec-corpus.md` (the corpus layer).** Code must conform to them. When code needs something a spec doesn't cover, update the spec first. Pipeline mechanics (capture, sharding, MIME-detect ordering, etc.) live in `impl-corpus.md` and `impl-codex.md`, not in the specs.
- **Corpora are separate, switchable.** The API maps corpus *ids → roots* (`corpus.api.config`); a server can front several (e.g. `../corpus` prod + `../corpus-test`). The web app's corpus tabs + endpoint switcher key off `GET /v1/corpora`. Legacy `../corpus-public`/`../corpus-private` are pre-v1.0 schema and not served.
- **The API wraps the library — no reimplementation.** `corpus.api` serializes what `records`/`derived_views`/`schemas`/`resolver`/`store` already produce. It builds a small per-corpus in-memory index for facets/filter (rebuilt on load), not a separate data store.
- **The frontend talks only to the API.** The Angular app never reads the filesystem; artifact bytes come from `GET /v1/{corpus}/artifacts/{id}` and functional URIs from `GET /v1/{corpus}/resolve?uri=…` (fully percent-encode the `uri` value — gotcha).
- **Parse tolerantly.** Log and skip unparseable records rather than failing the whole corpus.
- **The corpus layer is flat artifact↔record (v1.0).** No source/document kind, no credibility, no norm_conf, no standalone tags — those were the old (retired) Rust model. Records are artifacts + their markdown proxy; embeds are embedded transports (directly addressed) vs derived self-slices (materialized on demand).
