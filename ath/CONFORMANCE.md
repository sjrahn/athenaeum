# Conformance — `ath` against `spec/athenaeum.md`

What the reference implementation does against each section of the specification. This file is implementation
traceability, not part of the specification: the spec governs; every *gap* is work owed. The implementation predates
the current specification in most sections; the implementation plan works from this table.

Gates: `cd ath && bun run check && bun run build`. A change that touches the contract's behaviour updates its row here
with the test that pins it.

| § | requirement | state |
|---|---|---|
| 4 | instances: standalone or one pinned, read-only base; tiers; repin | gap: the code models foundation/extension layers (`layer:`, `successor: true`, `layer init`); no pin verification, no repin |
| 5 | layout `corpus/{forms,shapes,records}` `graph/{kinds,properties,entities}` `stores/ policies/ rulings.jsonl`; records as `<id>.yaml`, one per ingested artifact; shards; names per vocabulary; file is the subject; host state under XDG holds no holdings | gap: the code writes `ontology/ corpus/ ledger/`, `.claims.jsonl`, `.owner.jsonl`, `lineage.jsonl`, `corpus/bytes/`, `.ath/` in the repository |
| 6 | lines for terms, entities and rulings only; identity; canonical key order; revisions computed, never stored | gap: the code writes records as lines and a stored `rev` |
| 7.1 | 8-hex ids, 16 on collision, base wins at repin | gap: full hashes everywhere |
| 7.2–7.8 | constituents, axes, unions, routes anywhere in an address, derived addresses | partly: routes only in bind and only leading; constituents are written as subjects at ingest (must not be) |
| 8 | a record is one YAML document written at ingest with its projection (`intrinsics`, `provenance`), then `shape`, `chrome`, `passes` (each naming what it covers in `over` and attests), then `readings` (by address, formless) or `scopes` (a tree that has adopted them, signed whole; a table is its rows); stages unread/read/transcribed/formed derived; rendered artifacts read, structured ones pass-through | gap: the code writes `.claims.jsonl` with three lines per scope (`in`, `manifests`, `reads_as`) |
| 9 | testimony as artifacts in the stores; links inside testimony bytes; receipt `{actor, artifact, instance, name, received, testimony: [{hash, name}]}`; testimony shapes; admission before placement; provenance projected onto the record, the chain derived | gap: ingest folds a sidecar into `captured_from` lines |
| 10.1–10.5 | sniffing (YAML by the receipt's name); intrinsics per format, a part's inline; constituents as assets or parts, incl. `data:` URIs and tracks; the rendered/structured classes; surface ops on structured formats only | gap: YAML, `data:` constituents, json/yaml/vcard/markdown ops; no class; html and pdf are treated as surfaces |
| 10.6 | hint ops `pdf.words@1`, `html.text@1`, `html.attr@1`, `audio.speech@1`: never bound, never stored; drawn text only; no op reads | gap: `pdf.words`/`html.text` bind as surfaces; `image.words@1` (tesseract) exists and must be removed |
| 10.7 | selector languages by family | gap: CSS only; rfc822 blocks are named by the op, not the vocabulary |
| 11 | corpus forms (structure only, format-agnostic) and shapes (family `matches`, `select`, `columns`, `spine`, `chrome`, `surface`, testimony fields); graph kinds and properties; nothing restates a format | gap: the code reads one undifferentiated term vocabulary with mime-root terms, `axes`/`tree`/`physical`, semantic forms, `concept`/`keys`/`cells`/`sentinel` and prose `lint` |
| 12 | derived table, holdings, relevance | gap |
| 13.1–13.3 | passes in `passes`; staging in host state; signing lays readings by address and a tree whole; a pass attests `readings` or `structure` | gap: staging under `.ath/` in the repository; `pass sign` overwrites the real file temporarily; one `complete` |
| 13.4 | the reading check against the hint, advisory only; the normaliser | partly: the comparison exists (`ath/test/lint.l7.test.ts`) but blocks; names to change |
| 13.5 | rulings `distrust · accept · seek · defer · decline` in `rulings.jsonl` | gap: only `inspected` in `.owner.jsonl` |
| 14 | entities (`is`), claims one line per pass, `ev` without standing, bindings `b3:`/`derived:`/`field:`/`intrinsics:`, cell anchors `&col=M`, derived standing and status, demand; no harvest | gap: concepts, `term`, `manifested_by`, harvest, `line:` bindings |
| 15 | markdown proxy, provenance view, graph projection under `ath:` | partly: proxy exists; N-Quads uses `corpus://`, `ledger://` |
| 16 | planes | conforms in substance (`ath/test/serve.test.ts`) |
| 17 | named checks: class, unit, tree, coverage (advisory via hints), citation; sorts; per form, testimony, file; vocabulary checks | gap: codes G1–G4, O-codes; no sort checks; coverage blocks on the surface |
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
