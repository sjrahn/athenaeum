# Review: the successor contract (draft 1) against v52, the tooling and its own regression set

- **Date:** 2026-10-13. **Reviewer:** Claude Fable 5.1. **Scope:** `Successor Spec.dc.html` (draft 1, 2026-10-12) and `TOOL03 Manifest.dc.html` with the three regression artifacts under `tool03/conclusion/` (PDF `404d090f…`, CSV `1409369e…`, HTML `dd0a7844…`), read against `spec/*.md` v52, `tools/src`, `exemplars/`, `SOL-REVIEW.md`, `SUCCESSOR-DIRECTION.md`, `CLAIM-MODEL-REVIEW.md`, `TOOL03-REVIEW.md`.
- **Method:** read the spec text; ran the draft's own generic lints (G1 unit, G2 tree, undeclared fields, derivable-stored) against the PDF claims file; recomputed five reading revisions with BLAKE3; walked the HTML manifest's 82 evidence entries for anchor tightness, kind and quote fidelity; grepped the tooling for the ops and the axis the draft names. The CSV and PDF manifest JSONs are cut at 256 KB by the design API, so their `concepts` sections were read from the ledger files directly, not from the manifest.
- **Verdict:** the direction is right and the grammar held on three real artifacts. It is not ratifiable as draft 1: three contract gaps the data exposes (ledger attestation, the ord walk, the binding grammar), one guarantee that is vacuous on derived trees (`walked`), a regression set that fails four of its own lints, no lossy or real-container exemplar, and a migration story the draft's own §0 and Part I §8 require but Appendix C defers.

## 1. What holds

- **One grammar, mechanically checkable.** The PDF file is 413 lines over seven predicates (150 `manifests`, 137 `in`, 122 `reads_as`, 1 each of `attests`, `captured_from`, `pass`, `walked`). G1 and G2 run clean: every reading sits at a scope whose term `reads` that aspect; every `in` resolves; `ord` is contiguous from 0 under every parent; no field is undeclared; no term is outside the ontology. v52's forms never had a check of this kind (Sol §4).
- **Revisions are content addresses.** Five bodies recomputed with BLAKE3 (strings, arrays as compact JSON, TeX) match their `rev` exactly. "Readings as revisions" is demonstrated, not asserted.
- **Derived trees are the passthrough Sol asked for.** CSV and HTML store four lines each at `whole`; 306 and 42 scopes derive from `matches`, `shape` and `select`. The v52 `citation_surface: segments` deferral (ledger §5.4, §6.3) and the "no formless zone" gate have nothing left to defer.
- **Faithful to the bytes, correction in the ledger.** The source typo `FCi.j.y` survives in the reading and the export (`$FC_{i.j.y}$`); the owner's accept of Equation (1) is one line in a second file with a reason. Both are the TOOL03-REVIEW rulings carried through.
- **Union addresses work.** Five page-spanning containers carry `page=5&bbox=…;page=6&bbox=…`; `fc-i-j-y` is `manifested_by` two scopes. `in` is a bare `at` throughout.
- **Derived status does what it says.** The HTML harvest cites itself `direct` and every one of 77 claims derives `provisional`; the PDF cites itself `authoritative` and derives `confirmed`. The mechanism is honest. What it exposes is F6.
- **Sol's six asks are all answered:** bounded faithfulness (rule 6 + L7), marker coexistence (several `manifests` at one `at`, readings per aspect), form obligations (term `field`/`reads`/`expects`/`owes`), passthrough as a strategy (derived trees), default-read disclosure (export header: authority, pass, inspected, chrome, remainder), address/reading separation (`at` vs `rev`). Layering, derived status, no stamp, the ontology as recipe and rule 6 go beyond Sol; they are owner direction and the draft is internally consistent about them.

## 2. Contract findings, ranked

### F1 — Ledger attestation is unspecified, and the data shows it.

§4.1: every line carries "exactly one attestation: `by` (an op, versioned) or `pass` (a reference to a pass line in the same file)." §10.1: a pass is "one author and one verifier over one artifact." Neither covers a ledger line. In the data: every authored claim on `cdm-tool-03` is `by: "claude-opus-4-8"` (a model, unversioned, no verifier); harvests are `by: harvest:<term>@<hash>`; no ledger file has a `pass` line. §4.1's own example shows a ledger line with `"pass":"p1"` that cannot resolve. The TOOL03-REVIEW §6.5 said the asymmetry was "moot once passes are lines"; the data never made the move.

**Rule needed:** a ledger pass is a line (`subject: <slug>, predicate: pass`) with author, verifier, ontology hash and date, in the concept file; authored claims carry `pass`, harvests carry `by: harvest:<term>@<ontology-hash>` as an op. Then rule 2 ("anything that can be wrong is written by a pass and verified") holds in the ledger too.

### F2 — The ord walk cannot reach the cover.

§6: "Physical scopes (pages) carry no `in`"; "the logical tree runs from `whole` through headings and containers"; §11: the export "walks the tree in `ord`". In the file, 10 page scopes have no `in` and **7 scopes have a page as parent** (the five cover labels, the emblem, the TOC). They are unreachable from `whole`, yet the export emits them first. Text and implementation disagree.

**Rule needed:** either pages carry `in whole, ord N` (then they are logical and §6's sentence goes), or `cover-page`/`table-of-contents` are containers that carry `in whole` and the labels hang off them. The second keeps pages physical and is one line per such page.

### F3 — The binding grammar is narrower than what the files bind to.

§9.2: `reading` is a rev, `derived:<op>@<v>`, or null. In the HTML ledger: `derived:captured_from` (no version; `captured_from` is a line, not an op), `derived:html.attr@1 datetime` (an argument), `derived:html.title@1`. G4 ("every quote is in its bound surface") needs the surface defined: `data-site=g8board.com` is not in `html.text@1`.

**Rule needed:** `derived:<op>@<v>[ <arg>]` with the argument naming the attribute or path; and a value read off an `attests`/`captured_from` line is cited by that line (`reading: line:captured_from`), not by a pseudo-derivation.

### F4 — `walked` is vacuous on a derived tree.

The `html` term's convention says chrome is "every text run outside the selected terms". Under that definition G3 ("every word lies in a scope or in derived chrome") cannot fail, so `walked` attests nothing. The manifest's own counts are 7,174 text characters and 3,848 inside units, with demand 0; the manifest does not say what `textChars` already excludes (a 689 KB XenForo page carries far more text than that), so the ratio is indicative, not measured. PDF chrome is a falsifiable derivation (same text and box on ≥3 pages); HTML chrome is the complement of the selection. This is the hidden partiality Sol §5 warned about, re-entering through the ontology.

**Rule needed:** on a derived tree, chrome is declared (`chrome` selectors, which `xenforo-thread` already has) and the residual is the remainder; `walked` carries the residual ratio or does not exist for derived trees.

### F5 — The staleness mechanism does not fire on its own regression set.

§9.4: harvest is `by: harvest:<term>@<ontology-hash>`; §7.4/§8: a pass pinned at a hash other than the current one is stale, listed, re-run. The CSV harvest is `@f834e9`, the HTML harvest `@b21541`, the pass pin on both artifacts `b3:b215417f…`. Either ~2,087 CSV claims are stale and the manifest should list them (it reports demand 0), or `f834e9` is the hash of something else the spec does not name. Say which; this is the one place the derived-staleness rule could have been shown working.

### F6 — Source grade is inconsistent across the set, and the public plane makes it matter.

The PDF and the CSV cite themselves `authoritative`; the HTML thread cites itself `direct`. §12 serves only `confirmed` on the public plane, so the entire forum harvest is invisible publicly while the order history is not. The draft defines `kind` as "source grade" and nothing more.

**Rule needed:** when a record is the `manifested_by` of the concept, its harvest entries are `authoritative` for the term's `owes`; `direct` is for a record that reports the thing without being it.

### F7 — The harvest writes loose anchors and elided quotes.

HTML ledger, 82 entries: 38 anchor at the whole 28 KB post. Thirty of those (`thread → post`, `position`, quoting `#1`) do so because no finer scope exists: the designator is a field on the post's `manifests` line, and the spec does not say where a field-derived quote anchors. The other eight (`title`, `user_id`) have finer selectors (`.userTitle`, `a.username[data-user-id]`), but those live in the `concept` map, not in `select` lines, so no scope is derived for them and harvest falls back to the parent. Separately, 8 quotes end in `…`, which §9.2 refuses ("typographic re-takes and elided composites", Q4). Two rules for harvest: a selector a `concept` map names must also be a `select` line (or the map may only name terms); a long value is quoted by prefix/suffix, never by ellipsis.

### F8 — Page ids leak into evidence entries.

Every entry carries `scope: "t1r8"`, `"title"`, `"d1b"`: the design page's internal ids. Undeclared field; §4.3 retires ids. Strip at regeneration.

## 3. The regression set against its own lints

- **D1** The emblem carries `reads_as aspect: none`. Fails the per-file lint ("no `reads_as` under an aspect outside text · cells · tex") and the §6.5 ruling (the `none` lives on the term's `reads`, nothing on the scope). Appendix B counts 121 readings; the file has 122.
- **D2** Every `page=N` line stores `number: N`, a function of the address. §8: a stored derivable is a lint failure.
- **D3** `member-davisb1983` has three `manifested_by` lines and four author scopes in evidence.
- **D4** `g8board-com name`: value `Pontiac G8 Forum`, quote `Idle/stall | Pontiac G8 Forum`, `mode: stated`. Either `inferred` or a title derivation that splits.
- **D5** No `lineage.jsonl` in `tool03/conclusion/`; the only one is the first draft's, with the retired `structure` predicate.
- **D6** Wording. Direction §3 and Appendix B say "data has no readings", yet the ontology declares `record reads cells` and every CSV row carries a derived reading bound as `derived:csv.parse@1`. Not a contradiction in practice (the reading is the parse), but the contract should say "no *stored* readings" or the set's own phrasing will be cited against it.

None changes the grammar. All of them should be gone before the set is called a regression set, and the set should be produced by tooling from the bytes, not by a model pass inside a design page.

## 4. Against the current state

- **What the draft retires, in size.** Part II §4 (lines 148–892 of `spec/corpus.md`), the five schema namespaces (14 form YAMLs among them), ledger §5 (status ladder), §7 (interpretations), §6.4 (tenancy), §13.2 (`verified.touch`), Part I §2.1 (two repositories). In tooling: the resolver (2,028 lines), lint (3,469), verify (1,117) and most of 85 K lines across `corpus/` and `ledger/`, with 227 test files. Appendix A names the right things; nothing is missing from the list.
- **The draft's ops are named, not built.** `pdf.words@1`, `html.text@1`, `csv.parse@1`, `image.words@1`, `money.parse@1` appear nowhere in `tools/src` under those names (two mentions in a mime YAML and `check.py`). v52 has derivation-op pins (§7.9, v43) and the exemplars reproduce 67/67 PDF anchors from today's words op, so PDF words and HTML text have equivalents to rename. What is genuinely absent, per `exemplars/README.md` finding 4 and confirmed in the resolver: the `bytes=` axis, words-in-box, image OCR, `jsonpath`. The three regression files were hand-produced; nothing today can regenerate or lint them.
- **By its own §0 it cannot ratify yet.** Part I §8: an amendment lands text, enforcement sweep and migration story together. Appendix C defers migration cost. The ratification unit should be: contract + a reference implementation that regenerates the three artifacts from bytes and runs §13 on them + the measured cost on ath-steven (authored statuses → checks, 17,949 + 13,210 records → exports, 400 floor records placed).
- **The regression set is private.** `exemplars/`, the direction doc and the PDF exemplar sit in `.git/info/exclude`; the Amazon CSV carries the owner's addresses and payment instruments. A public spec cannot cite them. TOOL03 and the g8board thread are public; the CSV needs a synthetic twin or a public dataset of the same shape.
- **No lossy exemplar, no real container.** The set is document / data / document. The instance holds 9,238 JPEG, 318 MP4, 908 ZIP with 2,632 anchors. Sol §7 step 2 named the photo with OCR and the speech-bearing video; rule 6 and the "sub-scopes that carry transcribable content" clause are untested on pixels or audio, and the EPUB is a mock with placeholder hashes. Blocking for ratification.
- **Exemplar debt the draft inherits.** `exemplars/README.md` findings 1–4 (verify green where the resolver is red; `el=` forked three times; orientation in four conventions; missing ops) are the measured reasons for the draft. They are cited nowhere in it. Appendix B should point at them.

## 5. Before ratification, in order

1. F1 (ledger attestation), F2 (pages and the walk), F3 (binding grammar): contract text.
2. F4 (`walked` on derived trees), F6 (source grade of a manifestation's own harvest): contract text.
3. Fix D1–D5, F5, F7, F8 and regenerate the three files with tooling that runs §13.
4. One lossy exemplar (JPEG with printed text) and one real container (a ZIP from the instance, members as subjects).
5. The migration measurement Appendix C owes.
6. A public regression set.

O10, O11 and the `tex` comparator can stay open through ratification; term governance cannot wait past the first extension.
