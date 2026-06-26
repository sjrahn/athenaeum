# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Starting a session on this repo

If you are Claude Code and this is the start of a session working on Athenaeum, **invoke `/athenaeum` before doing anything else.** That skill boots the project's principal-developer persona, loads the project state / logbook / gotchas from `.claude/skills/athenaeum/`, and runs a short git-status check so you pick up exactly where the last session left off. The skill files are the source of truth for project state and history — don't rely on auto-memory for that.

## Repository layout

```
shared/                      # THIS repo — shared tooling for the Athenaeum system (athenaeum Forgejo org)
├── spec-athenaeum.md        # Architecture spec (v12) — TWO layers: corpus (foundation) + codex (a domain
│                            #   repo that embeds an expert agent). Defines the corpus↔codex contract;
│                            #   the corpus layer defers to spec-corpus.md.
├── spec-corpus.md           # Corpus spec (ATH-CORPUS v1.0) — artifact record format, body blocks, schemas, functional URIs
├── impl-corpus.md           # Implementation guide for the corpus / artifact-layer pipeline
├── impl-codex.md            # Reference convention (NON-NORMATIVE) for the codex/expert-agent layer + its deliverables
├── docs/
│   ├── CONTENT-TYPES.md     # Source taxonomy + how content types map onto the v1.0 model
│   └── NEW-CORPUS.md        # Corpus planning notes
├── web/                     # Corpus Console — Angular v22 SPA (the CURRENT viewer). Standalone
│   │                        #   components on @angular/cdk + @angular/aria; signals + httpResource;
│   │                        #   design tokens in src/styles/tokens.css. Responsive (760px breakpoint).
│   └── src/app/{core,shell,browser,viewer,chips,workbench}/
├── tools/corpus/            # Python corpus tooling (ath-corpus) — the data layer + the API
│   └── src/corpus/api/      # FastAPI read API behind the `[api]` extra (corpus.api) — the CURRENT server
├── clients/apple/           # Multiplatform Apple client (Swift). NOTE: predates the web+API stack and
│                            #   targets the now-deleted Rust server (:8080) — orphaned, needs rework.
└── .claude/skills/athenaeum/ # Skill state, logbook, gotchas
```

**The system has two layers; this repo is the shared, reusable tooling for the *corpus* layer.**

- **Corpus** — the content-addressed artifact archive (spec-corpus.md). The shared tooling owns it end to end: the `corpus` library, the `corpus.api` server, and the `web/` viewer. The actual corpora are sibling repos under the `athenaeum` org: **`corpus`** (all public captures) and **`corpus-private`** (personal documents).
- **Codices** — the layer above: domain-scoped knowledge repos, each embedding an **expert agent** that pulls from the corpus to curate its domain and produce its own deliverables. Each codex is its own repo, autonomous, agent-owned; the shared tooling is **agnostic** to it. `impl-codex.md` documents one reference convention, not a mandate.

**The Rust `crates/` stack (ath-core/ath-gui/ath-server) has been deleted** — it served the pre-v1.0 corpus model (source/document kind, credibility, norm_conf) and was superseded by `web/` + `corpus.api`. The Swift Apple client under `clients/apple/` still targets that old server and is orphaned until reworked.

## Common commands

```bash
# Run the API (FastAPI over the corpus library) — serves /v1 on :8099.
# Map corpus ids to roots (one server can front several corpora). Needs the [api] extra.
# Add `--extra wiki --wiki-zim <path-to-wikipedia.zim>` to power the concept KB (/v1/wiki/*,
# live concept glosses); without it concepts still show label/link and the wiki endpoints 503.
cd tools/corpus && uv run --extra api --extra wiki corpus-api serve \
  --corpus corpus=../../corpus --corpus corpus-private=../../corpus-private \
  --wiki-zim /path/to/wikipedia_en_all.zim \
  --host 0.0.0.0 --port 8099
# (corpus ids → roots are arbitrary; --corpus corpus-test=../../corpus-test adds a dev fixture.
#  The tooling fixes no ids: --corpus id=path / ATH_API_CORPORA / cwd discovery all work.)

# Run the Angular viewer (dev server). API base defaults to window.location.hostname:8099, overridable
# via an index.html <meta name="ath-api-base"> tag, a window.ATH_API_BASE global, or the in-app endpoint switcher.
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

- **The specs are `spec-athenaeum.md` (architecture — two layers: corpus + codex/expert-agent; the corpus↔codex contract) and `spec-corpus.md` (the corpus layer).** Code must conform to them. When code needs something a spec doesn't cover, update the spec first. Pipeline mechanics (capture, sharding, MIME-detect ordering, etc.) live in `impl-corpus.md`; the non-normative codex/agent reference convention lives in `impl-codex.md`.
- **Agnostic to corpus and agent topology.** The shared tooling fixes no corpus ids and no codex/agent structure. A third party points it at their own corpora (`--corpus id=path` / `ATH_API_CORPORA` / cwd discovery) and brings their own expert agents (codices). Don't hardcode corpus ids or assume a particular codex shape — the codex layer is external, agent-owned.
- **Corpora are separate, switchable.** The API maps corpus *ids → roots* (`corpus.api.config`); a server can front several. The real corpora are **`corpus`** (all public captures) + **`corpus-private`** (personal); `corpus-test` is a small dev fixture. The web app's corpus tabs + endpoint switcher key off `GET /v1/corpora`.
- **The API wraps the library — no reimplementation.** `corpus.api` serializes what `records`/`derived_views`/`schemas`/`resolver`/`store` already produce. It builds a small per-corpus in-memory index for facets/filter (rebuilt on load), not a separate data store.
- **The frontend talks only to the API.** The Angular app never reads the filesystem; artifact bytes come from `GET /v1/{corpus}/artifacts/{id}` and functional URIs from `GET /v1/{corpus}/resolve?uri=…` (fully percent-encode the `uri` value — gotcha).
- **Parse tolerantly.** Log and skip unparseable records rather than failing the whole corpus.
- **The corpus layer is flat artifact↔record (v1.0).** No source/document kind, no credibility, no norm_conf, no standalone tags — those were the old (retired) Rust model. Records are artifacts + their markdown proxy; embeds are embedded transports (directly addressed) vs derived self-slices (materialized on demand).
- **Concepts link artifacts to Wikipedia, not to each other directly.** A `concept` context block (spec §4.3.3.4) annotates a mention (`address:`+`quote:`) or aboutness (no address) with a `wikidata:Q…`/`enwiki:…`/`local:…` join key. Records invoking the same concept relate *without either knowing about the other*. Wikipedia is an **external local KB** (Kiwix ZIM via `corpus.wiki`), never captured as records; glosses are fetched live, never stored. Authored manually via `corpus concept link` (the auto-annotation pass + corpus-wide concept graph are deferred).
