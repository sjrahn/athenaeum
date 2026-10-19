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
- `ath/` — the tooling (Bun/TypeScript workspace), the specification's
  reference implementation on the foundations of the `ita` CLI: `packages/`
  `contracts` (zod contracts) ← `kit` (dispatch, gates, envelope, locks,
  journal, host paths, canonical lines) ← `engine` (formats, addresses,
  records, vocabularies, passes, the graph) and `custody` (stores, the index,
  reconcile) ← `verbs` (§19.5) ← `cli`; `daemon` (`athd`, kit and contracts
  only, handed the registry); `scanner` (the residence scanner, spec §18.5,
  its manifest its own versioned contract: `packages/scanner/MANIFEST-SCHEMA.md`;
  `verbs` takes its per-file testimony from it).
  `test/workspace.lint.test.ts` pins the package graph. No network to
  acquire: bytes are ingested from disk; producers live outside.
- `testdata/` — the regression library: `ontology/` (the regression ontology a
  standalone instance starts from, in the vocabularies' own layout), `exemplars.yaml`
  (every artifact of the set: file, blake3, mime, the shape it classifies as) +
  `seed.ts` (the regression instance pair, built with the tool's own verbs, pinned by
  `ath/test/seed.test.ts`), `synthetic/` (committed fixtures, each export with its
  `<file>.testimony.yaml`, and their generators: a twin of every byte shape in the
  owner's corpus, inventoried in `synthetic/gen/COVERAGE.md`) and `passes/` (the
  generated forming pass of the asserted-tree PDF). No private byte is in the set.
  See `testdata/README.md`.

The v52 Python tooling (`tools/`) is retired on this branch; it lives on the
`v52` tag and keeps serving the current instance from a worktree of that tag.

## Gates (run before reporting any tooling change done)

    cd ath && bun run check      # tsc --noEmit, biome check, bun test
    cd ath && bun run build      # the compiled binary still loads pdfium

The suite runs over committed fixtures (`ath/test/fixtures/`, `testdata/synthetic/`); nothing self-skips. Run the
tests with `TMPDIR` on a filesystem with room (`/tmp` is a 16 GB tmpfs here). A change that touches the contract's behaviour also updates its
row in `ath/CONFORMANCE.md` with the test that pins it.
