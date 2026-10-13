# {name} — an Athenaeum layer

This repository is one **layer** of an Athenaeum: three trees of sorted JSONL claim files —
`ontology/` (what a kind of thing expects), `corpus/` (artifact subjects by blake3: what the
bytes are and manifest) and `ledger/` (concept subjects by slug: what the world is, cited into
the corpus). A **foundation** is public by construction; an **extension** names the foundation
it extends in `athenaeum.yaml` and never writes it. The contract is `spec/successor.md` in the
Athenaeum distribution; `ath` on PATH finds this layer by walking up for `athenaeum.yaml`
(`$ATHENAEUM_ROOT` overrides).

**Five rules** (spec §1): everything is a claim line · ops author byte-facts, passes author
judgments · addresses are intrinsic · the ontology is the recipe · derived, never stored. And
the sixth: nothing lossy enters the corpus — a reading is a transcription checkable against the
bytes; what a scope shows or means is a ledger claim.

## Working in this layer

- `ath ingest <file>…` makes an artifact subject from bytes on disk (no network: producers hand
  bytes in). A container's members become subjects of their own.
- A judgment is written by a **pass**: `ath pass open <blake3> --by <author> --verify <verifier>`,
  `ath claims append <blake3> --pass pN --from lines.jsonl`, then `ath pass sign <blake3> pN`
  (the lints gate it). Nothing under `corpus/` exists unsigned.
- `ath tree`, `ath resolve`, `ath inspect` (L7: readings against the bytes), `ath harvest`
  (concept lines → ledger), `ath verify` (bindings, derived status, demand), `ath export`,
  `ath serve`. `ath help <group>` lists each.
- The owner's acts live in `<blake3>.owner.jsonl` and are written only by `ath inspect accept`
  at a terminal. External captures, deletions and normative changes stay owner-gated.

## Gates (run before reporting any content change done)

    ath lint --all && ath verify --all

Dispatchable workers in `.claude/agents/`: `pass-author` (structure and readings on one
artifact, as a pass) and `ledger-pass` (world claims cited into the corpus, as a pass). They
never run git; review and commit their work here.
