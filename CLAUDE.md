# Athenaeum — orchestrator workspace

Knowledge system: **corpus** (faithful bytes) → **ledger** (evidence-backed claims).
Together they are the system's **end product**, consumed from outside — compilations,
expert agents — under the consumption contract (spec Part III §12); the system holds no
registry of consumers. This repo is the orchestrator: **the specification and the shared
tooling, nothing else** — it is deployment-agnostic and publicly hostable. Everything
instance-specific is deployment state: the member manifest (`athenaeum.yaml`, untracked —
`athenaeum.yaml.example` is the template) and the member repos cloned at ignored paths
(`corpus/`, `ledger/` at the root).

**The specification is law** — one spec, three parts, one version:
`spec/athenaeum.md` (Part I, architecture), `spec/corpus.md` (Part II), `spec/ledger.md`
(Part III). Code conforms to spec; when code needs something the spec doesn't cover, the
spec changes first. External captures, deletions, and normative spec changes are
owner-gated.

**Boot order for a working session**: this file, then the deployment's own notes —
`corpus/runbooks/deployment.md` (members, backlog location, known-red baselines) and the
runbooks beside it. Operational knowledge lives with the members (corpus `runbooks/`,
ledger `docs/`), never in this repo.

## Operating principles

- **Deferral**: records are usable from ingest; normalization runs only under demand
  (queue = demand, never backlog — corpus.md §8.5). Never propose pre-emptive forming
  sweeps or standing drain loops. The ledger cites deferred surfaces at reduced strength
  (ledger.md 1.8); citations are themselves the demand signal.
- **Tenancy is derived, per record**: origin overlays declare `tenancy: public|private`
  (fail closed private); publication filters on derived sensitivity, fail closed — the
  consumption contract is the wall (ledger.md §6.4, §12). One corpus, one ledger —
  privacy is never a repo partition.
- **Thin operation**: no resident skill, no logbook. Memory = the spec + tracker + git
  history + member runbooks.

## Gates (run before reporting any content/tooling change done)

    cd tools && uv run --no-sync python -m pytest -q     # NOT bare `uv run pytest`
    uv run --no-sync ruff check src tests
    uv run --no-sync ath ledger check && uv run --no-sync ath ledger verify
    corpus lint <id>                                     # per touched record

Install once: `cd tools && uv sync` (editable; `corpus`/`ath` land on PATH via the venv).
Known-red baselines are deployment state — check `corpus/runbooks/deployment.md` before
treating a red gate as a regression.

## Surfaces

- `ath` — status/sync, `ath issue` (tracker read + snapshot sync; writes go through the
  forge's own CLI), `ath ledger …` (check/verify/harvest/merge/…).
- `corpus` — capture → ingest → (deferred) normalize; `inspect`/`diagnose`/`body`/`resolve`.
- Dispatchable workers in `.claude/agents/`: `normalizer` (form passes), `ledger-scribe`
  (interpretive authoring), `overlay-author` (new web hosts). They never run git; review
  and commit their work here.
- Backlog: the tracker registered in the manifest (`tracker:`); its committed snapshot
  lives where `tracker.snapshot` points (regenerate with `ath issue sync`).
