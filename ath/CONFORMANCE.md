# Conformance — `ath` against `spec/athenaeum.md`

What the reference implementation does against each section of the specification. This file is implementation
traceability, not part of the specification: the spec governs; every *gap* is work owed. The implementation predates
the current specification in most sections; the implementation plan works from this table.

Gates: `cd ath && bun run check && bun run build`. A change that touches the contract's behaviour updates its row here
with the test that pins it.

| § | requirement | state |
|---|---|---|
| 4 | instances: standalone or one pinned, read-only base; tiers; repin | gap: the code models foundation/extension layers (`layer:`, `successor: true`, `layer init`); no pin verification, no repin |
| 5 | layout `terms/ records/ entities/ stores/ policies/ rulings.jsonl`; shards; one name space; file is the subject; host state under XDG; holdings | gap: the code writes `ontology/ corpus/ ledger/`, `.claims.jsonl`, `.owner.jsonl`, `lineage.jsonl`, `corpus/bytes/`, `.ath/` in the repository |
| 6 | one scope line per scope (`at`, `form`, `in`, `ord`, fields, `text`/`cells`/`tex`, `pass`); whole lines with `pred`; revisions computed, never stored; canonical key order | gap: the code writes three lines per scope (`in`, `manifests`, `reads_as`) with `subject · predicate · value` and a stored `rev` |
| 7.1 | 8-hex ids, 16 on collision, base wins at repin | gap: full hashes everywhere |
| 7.2–7.8 | constituents, axes, unions, routes anywhere in an address, derived addresses | partly: routes only in bind and only leading; constituents are written as subjects at ingest (must not be) |
| 8 | records exist only once something is said; `intrinsics` cached with its op version; `complete`; a stored `shape` at `whole` | gap |
| 9 | testimony as artifacts in the stores; links inside testimony bytes; receipt `{actor, artifact, instance, name, received, testimony}`; origin forms; admission before placement; derived provenance | gap: ingest folds a sidecar into `captured_from` lines |
| 10.1–10.4 | sniffing (YAML by extension); intrinsics per format; constituents incl. `data:` URIs; surface ops; `pdf.words@1` ignores invisible text | gap: YAML, `data:` constituents, json/yaml/vcard/markdown ops, invisible-text rule; html reads producer meta tags |
| 10.5 | the one proposal op, `audio.speech@1` | gap: `image.words@1` (tesseract) exists and must be removed |
| 10.6 | selector languages by family | gap: CSS only; rfc822 blocks are named by the op, not the vocabulary |
| 11 | corpus forms (structure only, format-agnostic) and shapes (family `matches`, `select`, `columns`, `spine`, `chrome`, `surface`, testimony fields); graph kinds and properties; nothing restates a format | gap: the code reads one undifferentiated term vocabulary with mime-root terms, `axes`/`tree`/`physical`, semantic forms, `concept`/`keys`/`cells`/`sentinel` and prose `lint` |
| 12 | derived table, holdings, relevance | gap |
| 13.1–13.3 | passes, staging in host state, signing creates the record | gap: staging under `.ath/` in the repository; `pass sign` overwrites the real file temporarily |
| 13.4 | the reading check (was L7) | conforms in substance (`ath/test/lint.l7.test.ts`); names to change |
| 13.5 | rulings `distrust · accept · seek · defer · decline` in `rulings.jsonl` | gap: only `inspected` in `.owner.jsonl` |
| 14 | entities (`is`), claims on properties, `ev` with `grade`, binding, status, demand; no harvest | gap: concepts, `term`, `manifested_by`, harvest |
| 15 | markdown proxy, provenance view, graph projection under `ath:` | partly: proxy exists; N-Quads uses `corpus://`, `ledger://` |
| 16 | planes | conforms in substance (`ath/test/serve.test.ts`) |
| 17 | named checks: unit, tree, coverage, citation; sorts; per form, testimony, file; vocabulary checks | gap: codes G1–G4, O-codes; no sort checks |
| 18 | custody: stores, drivers (local, rclone), index, scanner testimony, links, policies, reconcile, resolution with trace, `athd` | gap: not implemented; the scanner exists (`scanner/`) |
| 19.1 | profiles, tiers, actor | conforms (`ath/test/kit.dispatch.test.ts`) |
| 19.2 | loading a chain; op and intrinsics coverage | gap |
| 19.3 | atomic writes, locks and history in host state | gap: no temp-then-rename for artifacts; locks and history in `.ath/` |
| 19.4 | envelope, exit codes | conforms (`ath/test/kit.dispatch.test.ts`) |
| 19.5 | verbs | gap: most verbs renamed or new |

## Regression set

The regression set is `testdata/`: every artifact a generated twin with fictional content, its generator under
`testdata/synthetic/gen/`, no value copied from a real file; `testdata/exemplars.yaml` lists one artifact per mime and
`ath/test/regression.test.ts` runs every leg over the committed artifacts. `bun testdata/mock.ts` writes an instance
pair in the specification's layout from the same fixtures (gitignored output), the shape the implementation must
produce.
