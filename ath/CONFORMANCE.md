# Conformance — `ath` against `spec/athenaeum.md`

What the reference implementation does against each section of the specification, and which tests pin it. This file is
implementation traceability, not part of the specification: the spec governs; a row marked *gap* is work owed.

Gates: `cd ath && bun run check && bun run build`. A change that touches the contract's behaviour updates its row here
with the test that pins it.

| § | requirement | tests | state |
|---|---|---|---|
| 4 | instances: standalone or extending one base; pinned, read-only base; the tool serves the chain | `ath/test/corpus.ingest.test.ts`, `ath/test/serve.test.ts` | gap: the code models foundation/extension *layers* (`layer:` key, foundation public, `layer init`); needs `extends: {path, commit}`, per-instance `tier`, `instance init/show/check/repin`, pin verification, tool-coverage check (§19.2.2), custody through the base (§18.2) |
| 5 | trees and files, one writer | — | conforms (no dedicated test) |
| 6.2 | authorship | `ath/test/lint.test.ts` | conforms |
| 6.3 | identity | `ath/test/model.line.test.ts`, `ath/test/ontology.test.ts` | gap: `properties`/`testimony` identities replace `attests`/`captured_from`; owner `disowned` |
| 6.5 | revisions | `ath/test/corpus.pass.test.ts`, `ath/test/regression.test.ts` | conforms |
| 6.6 | corrections and lineage | `ath/test/corpus.pass.test.ts` | conforms |
| 7.2 | constituents one level deep | `ath/test/regression.test.ts` | gap: the list is `constituents`, not `members`; a constituent's file names no container |
| 7.3–7.4 | axes, union order, box precision | `ath/test/corpus.derive.test.ts`, `ath/test/model.address.test.ts`, `ath/test/ops.pdf.test.ts`, `ath/test/ops.test.ts` | gap: `bytes=` for json/ndjson/yaml/vcard |
| 7.5 | routes through containers | `ath/test/corpus.container.test.ts` | gap: a `path` anywhere in the address; routes in resolve/tree/inspect |
| 7.6 | derived addresses | `ath/test/regression.test.ts` | conforms |
| 7.7 | physical addressability | `ath/test/corpus.container.test.ts` | conforms |
| 8.1 | the artifact file's predicates | — | gap: `properties` (op-named, pinned, swept), `testimony`, `complete` |
| 8.2 | rules | `ath/test/lint.test.ts`, `ath/test/model.line.test.ts`, `ath/test/ontology.test.ts` | conforms |
| 9 | testimony, receipt, origin terms, admission, provenance, retiring copies | `ath/test/corpus.ingest.test.ts` | gap: not implemented; ingest folds a sidecar into `captured_from` |
| 10.1 | sniffing | `ath/test/ops.test.ts`, `ath/test/regression.test.ts` | gap: YAML by extension |
| 10.2 | properties per format | `ath/test/ops.epub.test.ts`, `ath/test/ops.mail.test.ts`, `ath/test/regression.test.ts` | gap: html reads producer meta tags (§10.2.3); per-format `*.properties@N` ops |
| 10.3 | constituents per container | `ath/test/ops.mail.test.ts`, `ath/test/ops.test.ts`, `ath/test/regression.test.ts` | gap: html/xhtml `data:` constituents |
| 10.4 | surface ops | `ath/test/corpus.derivation.test.ts`, `ath/test/corpus.derive.test.ts`, `ath/test/ops.pdf.test.ts`, `ath/test/ops.test.ts`, `ath/test/regression.test.ts` | gap: json, yaml, vcard, markdown ops |
| 10.5 | proposal ops | `ath/test/ops.image.test.ts` | gap: the verb is `propose <op>` |
| 10.6 | selector languages | `ath/test/corpus.derive.test.ts`, `ath/test/ops.mail.test.ts`, `ath/test/ops.test.ts`, `ath/test/regression.test.ts` | gap: selectors by family; rfc822 blocks named by the ontology, not the op |
| 11.2 | term predicates | `ath/test/corpus.derive.test.ts`, `ath/test/lint.test.ts` | gap: `shape` declares the header; `chrome` repetition rule declared; `convention` closed set; declarative `lint` |
| 11.4 | roots, classes | `ath/test/corpus.derive.test.ts`, `ath/test/regression.test.ts` | gap: `testimony` class; foundation terms §11.9 |
| 11.5 | classification | `ath/test/ops.epub.test.ts`, `ath/test/regression.test.ts` | gap: probe `constituent` (was `member`); several containers; `selector` by family |
| 11.6 | derivation lookup | `ath/test/corpus.derivation.test.ts`, `ath/test/corpus.derive.test.ts`, `ath/test/regression.test.ts` | conforms |
| 11.7 | derived structure | `ath/test/corpus.derive.test.ts`, `ath/test/model.address.test.ts` | gap: declared header row; container select by path pattern |
| 11.8 | the pin | `ath/test/corpus.pass.test.ts`, `ath/test/ontology.test.ts` | conforms |
| 13.1–13.2 | passes, staging, signing | `ath/test/corpus.pass.test.ts` | gap: `complete` replaces `walked` |
| 13.3 | complete | `ath/test/corpus.pass.test.ts`, `ath/test/export.test.ts`, `ath/test/lint.test.ts` | gap: rename |
| 13.4 | L7 | `ath/test/lint.l7.test.ts` | conforms |
| 13.5 | rulings (`<blake3>.rulings.jsonl`) | `ath/test/corpus.pass.test.ts` | gap: `disowned`; the file is `.rulings.jsonl` (code writes `.owner.jsonl`) |
| 14.1–14.3 | concepts, claims, evidence | `ath/test/ledger.test.ts`, `ath/test/lint.test.ts`, `ath/test/ontology.test.ts` | conforms |
| 14.4 | binding | `ath/test/corpus.container.test.ts`, `ath/test/ledger.test.ts` | gap: `line:captured_from` goes; disowned testimony holds |
| 14.5 | status | `ath/test/ledger.test.ts` | conforms |
| 14.6 | harvest | `ath/test/ledger.test.ts`, `ath/test/ontology.test.ts`, `ath/test/regression.test.ts` | gap: `@<source>` by family (HTML-only today) |
| 15 | export | — | gap: provenance view (§15.2) |
| 16 | planes | `ath/test/serve.test.ts` | conforms |
| 17 | lints | `ath/test/corpus.pass.test.ts`, `ath/test/lint.test.ts` | gap: per-testimony lint; stale properties; term lints §17.3 |
| 18 | custody | — | gap: only the co-located store exists; locations, the index, presented manifests and custody acts are not implemented |
| 19.1 | profiles, tiers, actor | — | conforms (ath/test/kit.dispatch.test.ts) |
| 19.2 | loading an instance with its bases; op and properties coverage | — | gap: no coverage check |
| 19.3 | atomic writes, locks, history | — | gap: line files and bytes are not written by temp-then-rename |
| 19.4 | envelope, exit codes | — | conforms (ath/test/kit.dispatch.test.ts) |
| 19.5 | verbs | — | gap: `provenance`, `disown`, `propose`, `properties sweep`, `location …` |

## Regression set

The regression set is `testdata/`: every artifact a generated twin with fictional content, its generator under
`testdata/synthetic/gen/`, no value copied from a real file; `testdata/exemplars.yaml` lists one artifact per mime with
its root term, and `ath/test/regression.test.ts` runs every leg over the committed bytes. A rule that cannot be shown
on one of them is not conformed to.

## Earlier ruling identifiers

Comments in `ath/src` and `ath/test` cite rulings by identifier (`D-…`). Each now lives at the section below.

| id | § |
|---|---|
| D-shadow-same | 4 |
| D-planes | 4 |
| D-F1 | 6.2 |
| D-pass-line | 6.2 |
| D-identity-ontology | 6.3 |
| D-rev | 6.5 |
| D-D5 | 6.6 |
| D-members-depth | 7.2 |
| D-union | 7.3–7.4 |
| D-bbox | 7.3–7.4 |
| D-col | 7.3–7.4 |
| D-csv | 7.3–7.4 |
| D-container-route | 7.5 |
| D-designated | 7.6 |
| D-physical-addressable | 7.7 |
| D-attests-pin | 8.1 |
| D-D1 | 8.2 |
| D-D2 | 8.2 |
| D-D6 | 8.2 |
| D-D7 | 8.2 |
| D-testimony | 9 |
| D-receipt | 9 |
| D-provenance | 9 |
| D-sidecar | 9 |
| D-captures | 9 |
| D-ingest-op | 9 |
| D-sniff | 10.1 |
| D-rfc822 | 10.2 |
| D-epub | 10.2 |
| D-zip-reader | 10.3 |
| D-mbox | 10.3 |
| D-rfc822 | 10.3 |
| D-embeds | 10.3 |
| D-html | 10.4 |
| D-pdf | 10.4 |
| D-derivation | 10.4 |
| D-json | 10.4 |
| D-vcard | 10.4 |
| D-markdown | 10.4 |
| D-spike-pdfium | 10.4 |
| D-spike-parse5 | 10.4 |
| D-ocr | 10.5 |
| D-ocr (applied) | 10.5 |
| D-select | 10.6 |
| D-select-family | 10.6 |
| D-rfc822-parts | 10.6 |
| D-attr-pattern | 10.6 |
| D-expects | 11.2 |
| D-designator-where | 11.2 |
| D-mime-root | 11.4 |
| D-roots | 11.4 |
| D-roster | 11.5 |
| D-epub | 11.5 |
| D-derivation | 11.6 |
| D-csv (amended) | 11.7 |
| D-col | 11.7 |
| D-F5 | 11.8 |
| D-staging | 13.1–13.2 |
| D-sign | 13.1–13.2 |
| D-pass-id | 13.1–13.2 |
| D-F4 | 13.3 |
| D-G3-severity | 13.3 |
| D-L7 | 13.4 |
| D-L7-text | 13.4 |
| D-L7-tex | 13.4 |
| D-inspect | 13.5 |
| D-D3 | 14.1–14.3 |
| D-D4 | 14.1–14.3 |
| D-F7 | 14.1–14.3 |
| D-F8 | 14.1–14.3 |
| D-F3 | 14.4 |
| D-status | 14.5 |
| D-F6 | 14.6 |
| D-F7b | 14.6 |
| D-concept-key | 14.6 |
| D-key-holders | 14.6 |
| D-edge-cite | 14.6 |
| D-slug | 14.6 |
| D-harvest-keys | 14.6 |
| D-attr-pattern | 14.6 |
| D-planes | 16 |
| D-F8 | 17 |
| D-G3-severity | 17 |
| D-F2 | 8.1 |
| D-chrome | 11.2 |
| D-twin | Regression set |
