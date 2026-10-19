# Conformance — `ath` against `spec/athenaeum.md`

What the reference implementation does against each section of the specification. This file is implementation
traceability, not part of the specification: the spec governs; every *gap* is work owed. The implementation is being
built section by section against this table.

Gates: `cd ath && bun run check && bun run build`. `test/workspace.lint.test.ts` pins the package graph. A change that touches the contract's behaviour updates its row here
with the test that pins it.

| § | requirement | state |
|---|---|---|
| 4 | instances: standalone or one pinned, read-only base; no tiers, privacy by extension; repin; an extension's record of a base's artifact holds only its own receipts and origins | gap: the code models foundation/extension layers (`layer:`, `successor: true`, `layer init`); no pin verification, no repin |
| 5 | layout `corpus/{forms,shapes,records}` `graph/{kinds,properties,entities}` `stores/ policies/ rulings.jsonl`; records as `<id>.yaml`, one per ingested artifact; shards; names per vocabulary; file is the subject; host state under XDG holds no holdings | gap: the code writes `ontology/ corpus/ ledger/`, `.claims.jsonl`, `.owner.jsonl`, `lineage.jsonl`, `corpus/bytes/`, `.ath/` in the repository |
| 6 | lines for terms, entities and rulings only; a `pass` line is the one line without authorship; identity; canonical key order; a record stores no revision | partly: the canonical line (§6.4.2) and term identity (§6.3.1) — `test/canonical.test.ts`; entity and ruling identity owed |
| 7.1 | the full hash is the identity, the file name and every stored reference; a prefix only at the terminal | gap: prefixes at the terminal |
| 7.2–7.8 | constituents, axes, unions, routes anywhere in an address, canonical form (numbers, axis order, union order, path escaping), derived addresses | partly: parse, canonical form, order and containment — `test/address.test.ts`; refused regions against intrinsics, resolution and derived addresses owed |
| 8 | a record is one YAML document at `<blake3>.yaml` written at ingest with its projection (`intrinsics`, `receipts`, `origins`), then `shape`, `chrome`, `passes` (each naming what it covers in `over` by kind — addresses, `tree`, `shape`, `chrome` — and attests; ids monotonic, never dropped), then `readings` (by address, formless) or `scopes` (a tree that has adopted them, signed whole; a table is its rows); stages unread/read/transcribed/formed derived; rendered artifacts read, structured ones pass-through | partly: the document's grammar and its one style, load and write byte for byte — `test/canonical.test.ts` over `test/fixtures/records/`; passes, stages and the tree owed |
| 9 | testimony as artifacts in the stores, `subject` dropped from `origins`; the testimony contract (subject, producer, source) is all ingest asks; links inside testimony bytes; receipt `{actor, artifact, instance, name, received, testimony: [{hash, name}]}`; admission before placement, a `subject` that is not the delivered artifact refused; receipts and origins projected onto the record verbatim, the chain derived | gap: ingest folds a sidecar into `captured_from` lines |
| 10.1–10.5 | sniffing (YAML by the receipt's name); intrinsics per format, a part's inline; constituents as assets or parts, incl. `data:` URIs and tracks; the rendered/structured classes (epub, rfc822 rendered; selectors on them propose); surface ops on structured formats only | gap: YAML, `data:` constituents, json/yaml/vcard/markdown ops; no class; html and pdf are treated as surfaces |
| 10.6 | hint ops `pdf.words@1`, `html.text@1`, `html.attr@1`, `audio.speech@1`: never bound, never stored; drawn text only; no op reads | gap: `pdf.words`/`html.text` bind as surfaces; `image.words@1` (tesseract) exists and must be removed |
| 10.7 | selector languages by family | gap: CSS only; rfc822 blocks are named by the op, not the vocabulary |
| 11 | corpus forms (structure only, format-agnostic; `convention` from four) and shapes (family `matches` incl. `origin`, `select`, `columns` (columns are addresses), `spine`, `chrome`, `surface`); graph kinds and properties; nothing restates a format | partly: the four vocabularies, term identity and the pin (§11.8) — `test/canonical.test.ts`; loading, classification and derived structure owed |
| 12 | derived table, holdings, relevance | gap |
| 13.1–13.3 | passes in `passes`, ids never reused; staging in host state; signing lays readings by address and a tree whole; a pass attests `readings` or `structure`, neither implying the other; a partial pass on a formed record mints and retires nothing | gap: staging under `.ath/` in the repository; `pass sign` overwrites the real file temporarily; one `complete` |
| 13.4 | the reading check against the hint, advisory only; the normaliser | partly: the comparisons (`test/pass.compare.test.ts`), not yet wired to readings; names to change |
| 13.5 | rulings `distrust · accept · seek · defer · decline` in `rulings.jsonl` | gap: only `inspected` in `.owner.jsonl` |
| 14 | entities (`is`), claims one line per pass, `ev` without standing, `binding` `b3:`/`derived:`/`field:`/`intrinsics:` written by the entry's pass, a re-bind a later pass's own line, `observed` binding, cell anchors `&col=M`, grounded standing, ordered status with `manifests` sources, demand incl. re-bind and merge owed; no harvest | gap: concepts, `term`, `manifested_by`, harvest, `line:` bindings |
| 15 | markdown proxy, provenance view, graph projection under `ath:` | gap |
| 16 | serving an instance and its chain whole, no planes | gap |
| 17 | named checks: class, unit, tree, coverage (advisory via hints), citation; sorts; per form, testimony, file; vocabulary checks incl. unknown `convention` | gap: codes G1–G4, O-codes; no sort checks; coverage blocks on the surface |
| 18 | custody: stores, drivers (local, rclone), index, scanner testimony, links (hardlink provisional), policies incl. confinement at the local store, reconcile evicting from the local store only, resolution with trace, `athd` | gap: the scanner exists (`packages/scanner/`) |
| 19.1 | profiles, tiers, actor | conforms (`test/kit.dispatch.test.ts`, `test/kit.identity.test.ts`) |
| 19.2 | loading a chain; op and intrinsics coverage | gap |
| 19.3 | atomic writes, a journal for multi-file verbs, locks and history in host state | partly: temp-then-rename with fsync, the journal and its recovery before any mutating verb, locks and history under `$XDG_STATE_HOME/athenaeum/instances/<id>/` — `test/kit.journal.test.ts`, `test/kit.dispatch.test.ts`; artifact writes verified against their hash owed |
| 19.4 | envelope, exit codes, the socket's statuses | partly: envelope and codes — `test/kit.dispatch.test.ts`; the socket's statuses owed |
| 19.5 | verbs | gap: most verbs renamed or new |

## Regression set

The regression set is `testdata/`: every artifact a generated twin with fictional content, its generator under
`testdata/synthetic/gen/`, no value copied from a real file; `testdata/exemplars.yaml` lists one artifact per mime and
`ath/test/regression.test.ts` runs every leg over the committed artifacts. `bun testdata/mock.ts` writes an instance
pair in the specification's layout from the same fixtures (gitignored output), the shape the implementation must
produce.
