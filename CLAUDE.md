# Athenaeum — the distribution (spec + tooling)

This repository is the Athenaeum **distribution**: the specification and the
shared tooling, deployment-agnostic and publicly hostable.
It tracks **no instance state** — the system instantiated (corpus + ledger +
config) is the **instance**, one private repo the tooling discovers by walking
up from the working directory for `athenaeum.yaml` ($ATHENAEUM_ROOT
overrides). Work in this repo is spec and tooling development; content work
happens in an instance, under the instance's own `CLAUDE.md`.

**The specification is law** — one document, `spec/athenaeum.md` (a draft on this
branch; `main` and the `v52` tag carry the frozen v52 parts). It is purely
normative: present-tense rules of the system, no history, no migration prose, no
test names. Code conforms to spec; when code needs something the spec doesn't
cover, the spec changes first. Normative spec changes are owner-gated.
`ath/CONFORMANCE.md` maps each spec section to the tests that pin it and the
gaps still owed.

## Layout

- `spec/athenaeum.md` — the specification.
- `ath/` — the `ath` CLI (Bun/TypeScript): the specification's reference
  implementation, on the model of the `ita` CLI (contracts + kit + engine +
  commands). No network: bytes are ingested from disk; producers live outside.
  Templates a new layer is scaffolded from (`ath layer init`) live at
  `ath/templates/` — agent briefs included: edit them THERE; layers hold copies.
- `scanner/` — the residence scanner (Bun/TypeScript): host-side manifest
  publisher for attached locations (spec §18.5). Its manifest format is its
  own versioned contract (`scanner/MANIFEST-SCHEMA.md`).
- `testdata/` — the regression library: `ontology/` (the regression ontology a
  foundation starts from, a root term per mime), `exemplars.yaml` (one artifact
  per mime: file, blake3, mime, root) + `seed.ts` (a gitignored scratch layer),
  `synthetic/` (committed fixtures and their generators: a twin of every byte
  shape in the owner's corpus, inventoried in `synthetic/gen/COVERAGE.md`) and
  `passes/` (the generated pass of the asserted-tree PDF). No private byte is in
  the set. See `testdata/README.md`.

The v52 Python tooling (`tools/`) is retired on this branch; it lives on the
`v52` tag and keeps serving the current instance from a worktree of that tag.

## Gates (run before reporting any tooling change done)

    cd ath && bun run check      # tsc --noEmit, biome check, bun test
    cd ath && bun run build      # the compiled binary still loads pdfium

The regression suite (`ath/test/regression.test.ts`) runs entirely over the
committed synthetic fixtures; nothing self-skips. Run the tests with `TMPDIR`
on a filesystem with room (`/tmp` is a 16 GB tmpfs here). A change that touches the contract's behaviour also updates its
row in `ath/CONFORMANCE.md` with the test that pins it.
