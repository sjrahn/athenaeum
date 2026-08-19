# Athenaeum — the distribution (spec + tooling)

This repository is the Athenaeum **distribution**: the specification and the
shared tooling, deployment-agnostic and publicly hostable (spec Part I §2.1).
It tracks **no instance state** — the system instantiated (corpus + ledger +
config) is the **instance**, one private repo the tooling discovers by walking
up from the working directory for `athenaeum.yaml` ($ATHENAEUM_ROOT
overrides). Work in this repo is spec and tooling development; content work
happens in an instance, under the instance's own `CLAUDE.md`.

**The specification is law** — one spec, four parts, one version:
`spec/athenaeum.md` (Part I, architecture), `spec/corpus.md` (Part II),
`spec/ledger.md` (Part III), `spec/custody.md` (Part IV). Amendment history:
`spec/CHANGELOG.md`; the spec text carries current law only. Code conforms to
spec; when code needs something the spec doesn't cover, the spec changes
first — and an amendment lands complete: text + enforcement/guidance sweep +
migration story, together (Part I §8). Normative spec changes are owner-gated.

## Layout

- `spec/` — the four parts + CHANGELOG.
- `tools/` — the `athenaeum` Python distribution: the `ath` and `corpus` CLIs
  (`uv tool install --editable tools/` puts them on PATH). Templates a new
  instance is scaffolded from (`ath init`) live at `tools/src/ath/templates/`
  — agent definitions included: edit them THERE; instances hold copies.
- `scanner/` — the residence scanner (Bun/TypeScript): host-side manifest
  publisher for attached locations (Part IV §5). Its manifest format is its
  own versioned contract (`scanner/MANIFEST-SCHEMA.md`).

## Gates (run before reporting any tooling change done)

    cd tools && uv run --no-sync python -m pytest -q     # NOT bare `uv run pytest`
    uv run --no-sync ruff check src tests

Live-instance tests (members-parity and kin) self-skip unless an instance is
reachable — point `ATHENAEUM_ROOT` at one to include them, and check the
instance's `corpus/runbooks/deployment.md` for known-red baselines before
treating a red gate as a regression. A change that touches ledger/corpus
behavior also owes the instance gates run against a real instance:

    uv run --no-sync ath ledger check --root $ATHENAEUM_ROOT
    uv run --no-sync ath ledger verify --root $ATHENAEUM_ROOT

## Backlog

`athenaeum/athenaeum` on the deployment forge carries spec + tooling tickets
(read via `ath issue --root <instance>` where the instance's tracker points
here, or the forge UI; writes via `fj`). Instance content tickets live on the
instance's own tracker — see its config.
