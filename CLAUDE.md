# Athenaeum — the distribution (spec + tooling)

This repository is the Athenaeum **distribution**: the specification and the
shared tooling, deployment-agnostic and publicly hostable (spec Part I §2.1).
It tracks **no instance state** — the system instantiated (corpus + ledger +
config) is the **instance**, one private repo the tooling discovers by walking
up from the working directory for `athenaeum.yaml` ($ATHENAEUM_ROOT
overrides). Work in this repo is spec and tooling development; content work
happens in an instance, under the instance's own `CLAUDE.md`.

**The specification is law** — one spec, four parts, one version (frozen at v52 on
`main`; `spec/successor.md` is the unratified successor draft that `ath/` implements):
`spec/athenaeum.md` (Part I, architecture), `spec/corpus.md` (Part II),
`spec/ledger.md` (Part III), `spec/custody.md` (Part IV). Amendment history:
`spec/CHANGELOG.md`; the spec text carries current law only. Code conforms to
spec; when code needs something the spec doesn't cover, the spec changes
first — and an amendment lands complete: text + enforcement/guidance sweep +
migration story, together (Part I §8). Normative spec changes are owner-gated.

## Layout

- `spec/` — the four frozen v52 parts + CHANGELOG, and `spec/successor.md`, the
  unratified successor contract with Appendix D (the rulings `ath/` makes where
  the draft is silent, each pinned by a test).
- `ath/` — the `ath` CLI (Bun/TypeScript): the successor contract's reference
  implementation, on the model of the `ita` CLI (contracts + kit + engine +
  commands). No network: bytes are ingested from disk; producers live outside.
  Templates a new layer is scaffolded from (`ath layer init`) live at
  `ath/templates/` — agent briefs included: edit them THERE; layers hold copies.
- `scanner/` — the residence scanner (Bun/TypeScript): host-side manifest
  publisher for attached locations (Part IV §5). Its manifest format is its
  own versioned contract (`scanner/MANIFEST-SCHEMA.md`).
- `testdata/` — the regression library: `ontology/` (the regression ontology a
  foundation starts from), `exemplars.yaml` + `seed.ts` (a gitignored scratch
  layer), `synthetic/` (committed fixtures), `passes/` (the TOOL03 pass lines),
  and `regression/` (gitignored: the private regression bytes, placed by hand).
  See `testdata/README.md`.

The v52 Python tooling (`tools/`) is retired on this branch; it lives on the
`v52` tag and keeps serving the current instance from a worktree of that tag.

## Gates (run before reporting any tooling change done)

    cd ath && bun run check      # tsc --noEmit, biome check, bun test
    cd ath && bun run build      # the compiled binary still loads pdfium

The regression suite (`ath/test/regression.test.ts`) self-skips per missing
file under `testdata/regression/`; place the bytes to include it. A change
that touches the contract's behaviour also owes a row in `spec/successor.md`
Appendix D with the test that pins it.
