# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Starting a session on this repo

If you are Claude Code and this is the start of a session working on Athenaeum, **invoke `/athenaeum` before doing anything else.** That skill boots the project's principal-developer persona, loads the project state / logbook / gotchas from `.claude/skills/athenaeum/`, and runs a short git-status check so you pick up exactly where the last session left off. The skill files are the source of truth for project state and history — don't rely on auto-memory for that.

## Repository layout

```
athenaeum/
├── spec-athenaeum.md        # Canonical specification (v10) — data contract for records, frontmatter, body, schema library
├── impl-corpus.md           # Implementation guide for the corpus / artifact-layer pipeline
├── impl-codex.md            # Implementation guide for the codex / document-layer pipeline
├── docs/
│   ├── CONTENT-TYPES.md     # Content type enumeration and metadata attributes
│   ├── NEW-CORPUS.md        # Corpus planning notes
│   ├── APPLE-CLIENT-PLAN.md # Phased plan for the multiplatform Apple client
│   └── APPLE-UX-NOTES.md    # Apple-client UX notes
├── Cargo.toml               # Workspace root
├── crates/
│   ├── ath-core/            # Domain models, corpus loading, SQLite db, filtering, DAG, parsing, API types
│   ├── ath-gui/             # egui viewer (native + WASM), thin HTTP client
│   └── ath-server/          # axum HTTP server, in-memory SQLite, query endpoints
└── .claude/skills/athenaeum/ # Skill state, logbook, gotchas
```

## Common commands

```bash
# Run the server (loads corpora into SQLite, serves API on :8080)
cargo run -p ath-server

# Run the desktop viewer (connects to server)
cargo run -p ath-gui

# Override server URL
ATHENAEUM_SERVER=http://localhost:8080 cargo run -p ath-gui

# Check all crates compile
cargo check

# Check WASM target compiles
cargo check --target wasm32-unknown-unknown -p ath-gui

# Build WASM (requires trunk)
cd crates/ath-gui && trunk build
```

## Notable GUI libraries

- **egui_taffy 0.12** — CSS flexbox layout engine. Used for submit panel two-column layout. Avoid wrapping individual widgets in `.ui()`/`.ui_infinite()` — use only for structural flex containers. See gotchas #11.
- **egui_commonmark 0.23** — Markdown renderer for record body content.
- **catppuccin theme** — Inlined in `crates/ath-gui/src/theme.rs` (catppuccin-egui crate doesn't support egui 0.34 yet). Switchable from status bar.
- **Fira Code** — Embedded font (`crates/ath-gui/fonts/FiraCode-Regular.ttf`). Default font, switchable from status bar. Font size adjustable 8–24pt. See `crates/ath-gui/src/fonts.rs`.
- **egui_extras** — Image loaders (`install_image_loaders()` required at startup). JPEG requires explicit `image` crate feature.

## Key design principles

- **`spec-athenaeum.md` is the spec.** Code must conform to it. When code needs something the spec doesn't cover, update the spec first. Pipeline mechanics (capture, sharding, MIME-detect ordering, etc.) live in `impl-corpus.md` and `impl-codex.md`, not in the spec.
- **Two corpora, always separate.** `../corpus-private` and `../corpus-public` are hardcoded in ath-server. They are distinct collections with a corpus switcher, never merged.
- **Client-server architecture.** Both desktop and web targets are HTTP clients. The GUI never reads the filesystem directly.
- **SQLite is in-memory.** Rebuilt from corpus files on every server start. It's a query engine, not a data store.
- **Parse tolerantly.** Log and skip unparseable records rather than failing the whole corpus.
- **Source and document records are conceptually different.** They have distinct frontmatter fields, distinct detail views, and distinct filter sets.
