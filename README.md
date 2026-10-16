# Athenaeum

A knowledge normalization and curation system: capture artifacts from any
source, normalize each into a faithful, content-addressed record, and
interpret those records into an evidence-backed fact substrate. The thesis:
**knowledge cited precisely enough that the expert agents drawing on it
cannot hallucinate their grounding.**

This repository is the **distribution** — the system's definition (the
specification) and its shared tooling. It is deployment-agnostic and tracks
no instance state: the system instantiated (corpus + ledger + config) is an
**instance**, one private repository the tooling discovers and operates in.
The same distribution points at any instance; a third party runs their own.

## The shape of the system

Two data layers, one custody plane, sharp ownership boundaries:

| Layer | Owns |
|---|---|
| **Corpus** | Content-addressed artifacts (blake3 identity) with faithful markdown records — structure and renderings, never meaning |
| **Ledger** | The fact substrate: concepts and edges carrying typed claims, every claim bound to span-level `corpus://` / `ref://` evidence on an honest epistemic ladder |
| **Custody** | Where artifact bytes reside — stores, attached trees, remote locations — resolved by content address |

Interpretation never leaks downward, presentation never leaks in: consumers
(sites, expert agents, deliverables) read the corpus + ledger join from
outside the system and own voice, never knowledge.

## The specification

**One document in four parts, under one version** — the spec is law: code
conforms to spec, and when code needs something the spec doesn't cover, the
spec changes first.

- [Part I — Architecture](spec/athenaeum.md): topology, layering, tenancy, the consumption contract
- [Part II — Corpus](spec/corpus.md): records, addressing, atoms, forms, the normalize pass
- [Part III — Ledger](spec/ledger.md): concepts, claims, evidence, epistemic status, derived sensitivity
- [Part IV — Custody](spec/custody.md): byte residence and resolution

Amendment history: [`spec/CHANGELOG.md`](spec/CHANGELOG.md). The spec text
carries current law only.

## The tooling

[`ath/`](ath/) is the `ath` CLI (Bun/TypeScript) — the successor contract's
reference implementation: a layer of sorted JSONL claim files (`ontology/`,
`corpus/`, `ledger/`), bytes ingested from disk (never fetched), derivation
ops as the quote surface (`pdf.words@1`, `html.text@1`, `csv.parse@1`),
passes that stage and sign judgments, lints, L7, verify, harvest, the
markdown and N-Quads exports, and the read surface by plane:

```bash
cd ath && bun install && bun run build      # dist/ath
ath layer init <path>                       # a foundation; --extends <path> for an extension
```

The CLI discovers the enclosing layer by walking up from the working
directory for `athenaeum.yaml` (`$ATHENAEUM_ROOT` overrides). See
[`ath/README.md`](ath/README.md) for the package layout and the gates. The
v52 Python tooling is on the `v52` tag.

[`scanner/`](scanner/) is the residence scanner (Bun/TypeScript) — a
host-side manifest publisher that lets a corpus treat a large network share
as a self-describing content-addressed residence without hashing it over
the wire. Its manifest format is a versioned contract
([`scanner/MANIFEST-SCHEMA.md`](scanner/MANIFEST-SCHEMA.md)).

[`testdata/`](testdata/) is the regression library: the regression ontology,
a tracked manifest and seeder for a gitignored scratch layer, and the synthetic
fixtures (a generated twin of every byte shape in the owner's corpus) with their generators.

## License

Code (`ath/`, `scanner/`, `testdata/`) is [MIT](LICENSE); the
specification (`spec/`) is [CC BY-SA 4.0](LICENSE-CC).
