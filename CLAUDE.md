# Athenaeum — orchestrator workspace

Knowledge system: **corpus** (faithful bytes) → **ledger** (evidence-backed claims) →
**codices** (compiled prose). This repo is the orchestrator: specs, tooling, manifest.
Members are independent git repos at ignored paths — `corpus/` and `ledger/` at the root,
`codices/codex-*` — registered in `athenaeum.yaml` (the only place locations live).

**The specs are law** (`spec/athenaeum.md` v14, `spec/corpus.md`, `spec/ledger.md`,
`spec/codex.md`). Code conforms to spec; when code needs something a spec doesn't cover,
the spec changes first. External captures, deletions, and normative spec changes are
owner-gated.

## Operating principles

- **Deferral**: records are usable from ingest; normalization runs only under demand
  (queue = demand, never backlog — corpus.md §8.5). Never propose pre-emptive forming
  sweeps or standing drain loops. The ledger cites deferred surfaces at reduced strength
  (ledger.md 1.8); citations are themselves the demand signal.
- **Tenancy is derived, per record**: origin overlays declare `tenancy: public|private`
  (fail closed private); the codex leak check is the publication wall (ledger.md §6.4).
  One corpus, one ledger — privacy is never a repo partition.
- **Thin operation**: no resident skill, no logbook. Memory = specs + tracker + git
  history + `docs/` runbooks.

## Gates (run before reporting any content/tooling change done)

    cd tools && uv run --no-sync python -m pytest -q     # NOT bare `uv run pytest`
    uv run --no-sync ruff check src tests
    uv run --no-sync ath ledger check && uv run --no-sync ath ledger verify
    corpus lint <id>                                     # per touched record

Install once: `cd tools && uv sync` (editable; `corpus`/`ath` land on PATH via the venv).
Known-red baseline: 3 `test_members_parity` failures (ticket #171) against the live corpus.

## Surfaces

- `ath` — status/sync, `ath issue` (tracker read + snapshot sync; writes go through `fj`),
  `ath ledger …` (check/verify/harvest/merge/…), `ath codex <name> …`.
- `corpus` — capture → ingest → (deferred) normalize; `inspect`/`diagnose`/`body`/`resolve`.
- Dispatchable workers in `.claude/agents/`: `normalizer` (form passes), `ledger-scribe`
  (interpretive authoring), `overlay-author` (new web hosts). They never run git; review
  and commit their work here.
- Backlog: the Forgejo tracker (`athenaeum/athenaeum`); offline snapshot `docs/tickets.md`
  (regenerate with `ath issue sync`).
