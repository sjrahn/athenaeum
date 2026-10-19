# Athenaeum

A knowledge normalization and curation system: capture artifacts from any
source, normalize each into a faithful, content-addressed record, and
interpret those records into an evidence-backed fact substrate. The thesis:
**knowledge cited precisely enough that the expert agents drawing on it
cannot hallucinate their grounding.**

This repository is the **distribution** — the system's definition (the
specification) and its shared tooling. It is deployment-agnostic and tracks
no instance state: the system instantiated — records, vocabularies, entities,
rulings and the declarations of its stores — is an **instance**, one private
repository the tooling discovers and operates in. An instance stands alone or
extends exactly one base; what is shared is separated from what is not by
extension, never within one instance.

## The shape of the system

| Part | Holds |
|---|---|
| **Corpus** | One record per artifact (BLAKE3 identity): the projection ingest writes — what the format defines and what the testimony says — and the readings and tree authors sign; forms and shapes, which say what is structure |
| **Graph** | Entities and their claims, each line evidenced by anchors into records and signed by a pass; kinds and properties, which say what is meant |
| **Custody** | The artifacts and testimony themselves — stores, observed trees, a host index — found by hash, every read verified |

The corpus never names the graph; the graph cites the corpus. Consumers read
entities from outside the system and own voice, never knowledge.

## The specification

[`spec/athenaeum.md`](spec/athenaeum.md) — one normative document: instances,
files, lines, artifacts and addresses, records, testimony, formats, the
vocabularies, passes and rulings, entities and claims, export, serving, checks,
custody and the tool. The spec is law: code conforms to it, and when code needs
something it doesn't cover, the spec changes first.

## The tooling

[`ath/`](ath/) is the tooling, a Bun/TypeScript workspace — the
specification's reference implementation (conformance and open gaps:
[`ath/CONFORMANCE.md`](ath/CONFORMANCE.md)): the `ath` CLI, the `athd` host
daemon, and the residence scanner. It ingests artifacts and testimony from
disk and never fetches them.

```bash
cd ath && bun install && bun run build      # dist/ath, dist/ath-scan
ath instance init <path>                    # a standalone instance; --extends <path> for an extension
```

The CLI finds the instance by walking up from the working directory for
`athenaeum.yaml` (`$ATHENAEUM_ROOT` overrides). See
[`ath/README.md`](ath/README.md) for the packages and the gates. The v52
Python tooling is on the `v52` tag.

[`ath/packages/scanner/`](ath/packages/scanner/) is the residence scanner — a
host-side manifest publisher that lets custody treat a large network share as
an observed tree without hashing it over the wire. Its manifest format is a
versioned contract
([`MANIFEST-SCHEMA.md`](ath/packages/scanner/MANIFEST-SCHEMA.md)).

[`testdata/`](testdata/) is the regression library: the regression ontology, a
manifest of the synthetic fixtures (a generated twin of every byte shape in the
owner's corpus) with their generators, and a seeder that builds a regression
instance pair with the tool itself.

## License

Code (`ath/`, `testdata/`) is [MIT](LICENSE); the
specification (`spec/`) is [CC BY-SA 4.0](LICENSE-CC).
