# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Starting a session

**Invoke `/orchestrator` before doing anything else.** It boots the system's principal-developer persona, loads state / logbook / gotchas from `.claude/skills/orchestrator/`, and runs a member sweep so you pick up exactly where the last session left off. The skill files are the source of truth for system state and history — don't rely on auto-memory.

While `REFORGE.md` exists at the root, it is the active restructuring plan — read it second.

## What this repo is

**`athenaeum/athenaeum`** — the orchestrator repo of the Athenaeum system: the system's definition (specs), its shared tooling (the corpus library/CLI, the `ath` umbrella, and the ledger + codex packages as they land), and its driver (the orchestrator persona). Every other part of the system is an independent member repo in the same Forgejo org (`code.example.org/athenaeum`), cloned beneath this working tree at gitignored paths.

```
athenaeum/                    ← this repo's working tree (the workspace root)
├── CLAUDE.md                 ← you are here
├── REFORGE.md                ← active restructuring plan (self-deletes when it graduates)
├── athenaeum.yaml            ← the member manifest — the registry `ath` reads
├── spec/                     ← the specs: athenaeum.md (ATH-ARCH) · corpus.md (ATH-CORPUS) · ledger.md (ATH-LEDGER) · codex.md (ATH-CODEX)
├── tools/                    ← the `athenaeum` distribution: `ath` + `corpus` CLIs (Python 3.12, uv)
├── .claude/skills/orchestrator/  ← the persona + state/logbook/gotchas
├── corpora/                  ← UNTRACKED member clones — the two tenant-isolated hubs
│   ├── corpus/               ←   public/world captures (has the /curator skill)
│   └── corpus-private/       ←   personal captures (no persona by design)
├── ledger/                   ← UNTRACKED member clone — the knowledge layer (one repo)
└── codices/                  ← UNTRACKED member clones — targeted compilations
    ├── codex-general/  codex-pontiac-g8/  codex-steven/   (migrating into the ledger, reforge 5c)
    └── codex-homelab/                                      (pre-pattern; migration pending)
```

## The system in one paragraph

The **corpus** layer is the foundation: content-addressed archives of captured artifacts (blake3 identity, faithful normalized markdown records, `stub → draft → normalized` lifecycle), specified by the corpus spec in `spec/`. Two hubs enforce tenant isolation as a *repo boundary*: public and private content never mix. The **ledger** layer is the knowledge: one repo of concepts — materialized real-world things — carrying typed claims in which every claim cites evidence downward (`corpus://` URIs resolved by blake3 across the corpora, span-precise; `ref://` into mirrored reference datasets), with privacy as *derived sensitivity*, never a partition. The **codex** layer is the expertise: targetings of ledger facts that compile to prose deliverables, where the public-profile leak check is the tenancy wall. The **orchestrator** (this repo) defines the contracts, ships the tooling, and drives the whole.

## Common commands

```bash
# Both CLIs come from ONE uv TOOL install of tools/ (editable; gotcha #1). Reinstall after moving it:
uv tool install --reinstall --editable "tools[capture,media,fingerprint]" --with cryptography

# The ath umbrella — system verbs against athenaeum.yaml (run anywhere under this tree):
ath status                          # orchestrator repo + every member: branch, dirty, ahead/behind
ath sync                            # clone missing members; fetch + report the rest (--pull to ff)
ath corpus <cmd>                    # delegation shim — identical to `corpus <cmd>`

# The corpus CLI:
corpus --help                       # works anywhere; auto-discovers the corpus root by cwd
corpus health --summary             # run from corpora/corpus or corpora/corpus-private
corpus lint <hash-prefix>

# Tooling test suite + lint (from tools/; gotcha #2 for the pytest invocation):
cd tools && uv sync --extra capture --extra media --extra office --extra fingerprint --extra tokens
uv run --no-sync python -m pytest -q      # expect all green
uv run --no-sync ruff check src tests     # expect clean

# Codex validation (from any codex under codices/):
python3 tools/check.py                     # exits 0; corpus joins hardcoded ../../corpora/* until the codex package lands
```

## Key principles

- **The specs are law.** Code conforms to `spec/`; when code needs something a spec doesn't cover, update the spec first. Corpus data-contract changes additionally require a migration story — 10,000+ records conform to it.
- **Tenant isolation is a repo boundary.** Nothing may blur `corpus` and `corpus-private`.
- **Members are config-driven.** No member path may be hardcoded in shared tooling (`--corpus-root`, the manifest, `codex.yaml`).
- **Deterministic before LLM.** Capture/ingest/draft are mechanical; normalize and codex authoring are interpretive agent passes. Keep the boundary sharp.
- **Parse tolerantly.** Log and skip unparseable records rather than failing a whole corpus.
- **Member repos commit through their own disciplines** — corpus content work boots `/curator` in `corpora/corpus`; codices are freely iterable until the shared codex package fixes their contract.
