<!--
Successor contract, draft 1 — UNRATIFIED. v52 (spec/athenaeum.md, corpus.md, ledger.md, custody.md) stays the law
until this draft is ratified as one amendment (Part I §8). Source: the design project "Athenaeum successor model
design", page "Successor Spec" (2026-10-12), converted to markdown on 2026-10-13 without change to its text.
Review: spec/successor-review.md. Reference implementation: ath/ (the sprint/refactor branch); its rulings on what
the draft leaves open are Appendix D, which grows with the implementation and is folded into the text at ratification.
-->

*ATH · successor · draft 1 · 2026-10-12 · supersedes v52 on ratification*

# Athenaeum Specification — the contract

The Athenaeum captures bytes, describes what they manifest, and asserts what they express — each as a line that names its subject, its author and the evidence it rests on. Nothing stored is a function of anything else stored. The bytes remain the authority.

## 0. Status and precedence

- v52 is frozen and stays the law for the current tooling. This draft is written in Sol §7's order — contract first, grammar inside it — and is ratified as one amendment, never incrementally.
- **Part IV (custody)** is carried unchanged: identity is the BLAKE3 of the bytes; bytes reside across declared locations and resolve by content address. Nothing below touches it.
- Part I's principles survive where they are not contradicted here: deterministic before LLM, durable vs regenerable, offline-first, no transitionary states, the specification is law. Where this draft and Part I disagree, this draft wins.
- Regression set: the three artifacts of Appendix B and the exemplars (`exemplars/`). A rule that cannot be shown on one of them is not in the contract.

## 1. The system in five rules

1. **Everything is a claim line.** Artifact facts, structure, readings, world facts, ontology terms, passes and owner acts are all lines of one grammar: a subject, a predicate, a value, an attestation. One sort, one merge, one lineage.
2. **Ops author byte-facts; passes author judgments.** Anything that can be wrong is written by a pass and verified by a second one. Anything an op writes has no status because it has no judgment in it.
3. **Addresses are intrinsic.** A scope is named by coordinates in the bytes — page and box, byte range, row and column, time — never by a transform, a parser's tree or an id.
4. **The ontology is the recipe.** A scope *manifests* terms; what a term expects — fields, reading aspect, children, owed world facts, render form — rides on the term. A pass pins the ontology it read against by hash; nobody chooses a recipe.
5. **Derived, never stored.** Class, status, demand, held/flagged, chrome, staleness, every non-intrinsic address and the export are computed from stored lines at read time. A stored copy of a derivable thing is a defect.
6. **Nothing lossy enters the corpus.** A reading is a transcription checkable against the bytes — never a summary, a description, a paraphrase or a characterisation. Where a scope has no lossless transcription, the record marks its address and stops. What a scope shows, means or contains is a *world claim*: it lives in the ledger, cited to the scope, graded like any other claim. The record contains nothing unfalsifiable against its own bytes.

> v52 → the record was a markdown proxy carrying promises (forms, atoms, segments, touch chains, status); the ledger was JSON objects with an authored status ladder. Both become lines; the proxy becomes an export (§11).

## 2. Layers — foundation and extension

An instance is a **chain of layers**, the bottom public. A private instance is an *extension* of a public *foundation*, never a peer. A foundation may itself extend another.

- `athenaeum.yaml` names the foundation, pinned by commit or manifest. The foundation is read-only from above.
- **Resolution** is content-addressed and unscoped: a hash or slug resolves in the extension first, then down the chain. The view of a subject is the *line-set union* of its files across layers.
- **Tenancy is layer.** Everything in the foundation is public by construction; everything in an extension carries that extension's tier. Origin `tenancy:` declarations, the union rule and the visibility floor are gone.
- **Shadowing: refuse in the corpus, override in the ledger.** An extension may not write at a foundation artifact's existing identity (§4.2) — disagreement with a foundation reading is demand upward. In the ledger the extension's line wins in the union.
- **Schema and ontology are foundation-owned.** An extension adds terms and fields; it never redefines a foundation term. A local mint is a proposal, nagged upward.
- **Publication is the foundation.** `ath serve` on an extension serves the union on the owner plane and the foundation on the public plane (§12).

> v52 → one private repository, tenancy derived per origin, sensitivity computed upward. Replaced by layering (direction §1–2). The 400 floor records in ath-steven are the placement worklist.

## 3. Three trees, one grammar

```
<layer>/
├── ontology/<term>.claims.jsonl        terms — what a kind of thing expects
├── corpus/<blake3>.claims.jsonl        artifact subjects — what the bytes are and manifest
│          <blake3>.owner.jsonl         the owner's acts on that artifact (inspected)
│          lineage.jsonl                 moves, re-keys, supersessions
└── ledger/<slug>.claims.jsonl          concept subjects — what the world is, cited into the corpus
```

- **One-way reference.** An artifact file never names a concept. The ledger cites `corpus://` freely; the ontology is read by both and names neither. "World claims citing a scope" is an index, never a stored line in the corpus.
- **One file, two writers, never.** Passes write `.claims.jsonl`; the owner writes `.owner.jsonl`; ops append to both only through `attests`/`captured_from` at ingest.
- **Strings** are content-addressed: a reading's `rev` is the BLAKE3 of its body (arrays as JSON). Bodies may be inline or in a string store; retention is "referenced from any layer"; a foundation never compacts on its own authority.

> v52 → corpus/records/{ab}/{blake3}.md + schema/{mime,origin,atom,form,context}; ledger/facts/{type}/{slug}.json + interpretations/ + schemas/. Five schema namespaces collapse into the ontology (§7).

## 4. The claim line

### 4.1 Shape

A line is a JSON object. Artifact lines are keyed by `at` (an address in the file's artifact); ledger and ontology lines by `subject`. Every line carries a `predicate`, the predicate's fields, and exactly one attestation: `by` (an op, versioned) or `pass` (a reference to a pass line in the same file). The grammar is a triple with provenance — `(subject, predicate, object) + attestation` — and a one-line round-trip to N-Quads is the format's conformance test.

```
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","predicate":"in","value":{"at":"whole","ord":11},"pass":"p1"}
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","predicate":"manifests","term":"heading","num":"5.","level":1,"pass":"p1"}
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","predicate":"reads_as","aspect":"text","rev":"b3:9f86…","body":"Baseline emissions","pass":"p1"}
{"subject":"heading","predicate":"reads","value":"text"}
{"subject":"cdm-tool-03","predicate":"version","value":"03.0","evidence":[{"anchor":"corpus://404d090f…?page=1&bbox=…&text","quote":"Version 03.0","kind":"authoritative","mode":"stated","reading":"b3:2c1e…"}],"pass":"p1"}
```

### 4.2 Identity

Identity is the key a second line collides on. A write at an existing identity is a *correction*: delete + insert with a lineage row, never an edit in place.

| | |
|---|---|
| `attests · captured_from` | (at, predicate, by) — a newer op writes a second line that `supersedes` the first; never an edit |
| `manifests` | (at, manifests, term) — several terms on one scope are several lines |
| `in` | (at, in) — one placement per scope |
| `reads_as` | (at, reads_as, aspect) — one reading per scope and aspect; a re-read is a new revision at the same identity. Competing transcriptions are deliberately not representable. |
| `pass · walked · inspected` | (at, predicate, id \| pass \| rev) |
| `ledger claim` | (subject, predicate, value \| object, qualifiers) — evidence entries accrue on the one line |
| `ontology` | (subject, predicate, value) — repeatable predicates (field, select, shape, convention, concept) key on the value's name |

### 4.3 Files

- One line per claim; the file is sorted by key; a layer union and a merge are line-set unions. Nothing in the file depends on line order — reading order is `ord`, never position.
- **Passes are lines** (§10.1). A claim's `pass` is a two-character reference; author, verifier, date and ontology hash live once.
- The packed `value` is the unit of judgment — `in` packs its parent and `ord` because they are verified together.

> v52 → touch[] identifiers, status on records, the Claim object with ids. Retired: a claim has no id; it is addressed by its identity key and pinned by content hash where a challenge needs it.

## 5. Subjects and addresses

### 5.1 Artifact subjects

An artifact subject is `corpus://<blake3>`. A new hash is a new subject. A **container**'s `attests` carries its member roster; every member is its own subject whose `captured_from` names the container and path. Cite the member, which outlives the package; the container route canonicalises to it.

### 5.2 The intrinsic address — `at`

The only address stored and the only address an anchor carries. Its axes are declared by the artifact's mime-root term (§7.3); every axis is a coordinate in the bytes, in the stored frame, with no transform.

| | |
|---|---|
| `whole` | the artifact; the subject of attests, captured_from, pass, walked and the root manifests |
| `page=N · page=N&bbox=x,y,w,h` | pdf, images of pages; box normalised 0–1 in the page frame |
| `bbox=x,y,w,h` | raster images, on the pixel grid |
| `bytes=a,b` | html, xhtml, markdown, plain text, rfc822 — a byte range into the captured file (Q1 confirmed; `el=` retired) |
| `row=N · row=N&col=M` | csv, tsv, tabular data |
| `t=a,b` | audio, video — seconds in the stored stream |
| `path=…` | a container member, equivalent to the member's own subject |
| `a;b;c` | a **union address** — one box per page for a container that spans pages; a container's `at` is the union of its members' boxes, never a member's address borrowed |
| `…&text · &cells · &tex` | a trailing aspect names the reading surface a quote is taken from |

### 5.3 Derived addresses

Two further forms exist and neither is stored. **Positional** — the `ord` path (§5 ¶3), always available. **Designated** — the path of designators the bytes themselves print (`?sec=5&para=6`, `?eq=1`, `?post=4`, `?col=Currency`, `?ch=2&fig=1`), available where a term declares a designator field (§7.4). The resolver maps either to an `at` through `manifests`, `in` and `ord`. A world claim written against "paragraph 7 of TOOL03" binds, through the resolver, to an intrinsic anchor — which is why designators are structure, not prose.

### 5.4 Re-capture and retarget

A re-capture is a new subject. `supersedes` on the new subject carries anchors across where the derivation at the same intrinsic address still holds the quote; otherwise the citing entry is *held* (§9.3). A structure correction that moves a scope re-keys the readings on it — same body, same `rev`, new identity, one lineage row — and anchors that still lie inside the new box do not move.

> v52 → el=, turn=, block=, region=, transforms in the URI (Part II §6.2), the segment address field. All retired; turn= survives only as a designator alias a term resolves.

## 6. The artifact file — seven predicates

| predicate | by | meaning |
|---|---|---|
| `attests` | op | what the bytes are: mime, size, page count, dimensions, encoding, embedded metadata, the member roster of a container. Immutable; a better ingest writes a superseding line. |
| `captured_from` | op | origin, uri, via (capture · upload · export), snapshot time, or container + path for a member. Repeatable: one line per capture of the same bytes. |
| `pass` | pass | id, by, verify, ontology (hash), date, note. The named graph every judgment in the file belongs to. |
| `walked` | pass | the pass's attestation that structure over `at` is complete — every word lies in a scope or in derived chrome. Lapses on any structure change inside its extent. Means complete, never correct. |
| `manifests` | pass | the scope at `at` manifests `term`, with the fields the term declares (`num`, `level`, `layout`, `version`…). An undeclared field is refused at write. A stored line wins over a derived one at the same scope. |
| `in` | pass | placement: the parent's bare `at` and `ord`, reading order within it. Physical scopes (pages) carry no `in`: containment there is geometric. The logical tree runs from `whole` through headings and containers. |
| `reads_as` | pass | a transcription of the scope under one `aspect` (text · cells · tex), `body` and `rev`. Every aspect is lossless and checkable against the bytes (L7). Readings are annotations beside the bytes, never substitutes for them. |

### 6.1 Rules

- **Unit rule.** A `reads_as` sits only at a scope that manifests a term, and the aspect must be one that term `reads`. Readings are never smaller than a unit; a unit may be a group (table + caption, equation + label, biography + portrait).
- **Faithful to the bytes.** A reading transcribes what is printed, typo included (`FCi.j.y`, not `FC_{i,j,y}`). A correction of the source is a ledger claim with `mode: inferred` or a `challenges`, never a silent fix.
- **Designators are structure.** A leading "5.", a right-margin "Equation (1)", a "#4" on a post are fields on `manifests`, verbatim as printed; the body is the text without them. Deciding that "2." is a number and not a sentence is a judgment, so it is written by the pass, not stripped at export.
- **Demand → structure over the closure, text over the unit.** A demanded quote triggers structure for the enclosing section and its ancestry (so paths resolve) and a reading of the demanded unit only. No token budget is needed.
- **Where the bytes give the structure, nothing is stored.** CSV rows, HTML elements under a term's `select`, EPUB spines: `manifests` and `in` derive from the parse, the file stores four lines at `whole`, and a pass writes a line below `whole` only to disagree or to add (a paragraph that is also a `biography`).
- **Chrome is derived.** Running headers, page numbers, navigation: the property that makes a run chrome (same text and box on ≥3 pages; outside every selected term) is a derivation. It is listed in the export header and stored nowhere.
- **A scope with no lossless transcription has no reading.** It is addressed, manifested and placed; the bytes are resolved at its `at`; the record stops there. Anything said about what it shows, means or contains is a ledger claim anchored at that `at` with no quote, `mode: inferred`, graded as such. Where such a scope does carry transcribable content (glyphs in a raster, speech in a stream), a pass manifests the sub-scopes that carry it and reads those, under a lossless aspect, checkable against a derivation.
- **A weak engine is a reading's author, never a derivation.** A transcript claim always binds to a reading (Q3 answered).

```
// a CSV: the whole file, four lines
{"at":"whole","predicate":"attests","value":{"mime":"text/csv","bytes":151157,"rows":275,"header_row":0,"cols":29,"encoding":"utf-8"},"by":"corpus.ingest@0.1.0"}
{"at":"whole","predicate":"captured_from","value":{"origin":"amazon.ca","via":"upload","received":"2026-10-12","note":"Request My Data export"},"by":"capture@1"}
{"at":"whole","predicate":"pass","value":{"id":"p1","by":"claude-opus-4-8","verify":"claude-sonnet-5_3","ontology":"b3:b215417f49218591","date":"2026-10-12"}}
{"at":"whole","predicate":"walked","pass":"p1"}
// derived, not stored: whole manifests amazon-order-history (by matches); row=N manifests record, in whole ord N; col=3 manifests currency-code …
```

> v52 → the record body (metadata / content / annotations zones; section, segment, structural and placement blocks; atoms; forms; the sweep namespace; faithfulness issues). The whole of Part II §4 is replaced by this table. structure (claim-model rev 2) → manifests + in.

## 7. The ontology — terms as subjects

A term is a subject whose expectations are lines in `ontology/<term>.claims.jsonl`. One vocabulary serves the corpus (what a scope may manifest), the ledger (what a concept may be and owes) and the export (how a term renders). Mime roots, document kinds, units, containers, data shapes, web shapes and concept types are all terms; "class" and "type" from direction §3 are terms on the root.

### 7.1 The effective rules of a scope

**Union over its terms' `refines` chains ∪ its ancestors' `convention`s down the `in` chain.** That is the recipe: computed, never chosen. A `biography` with no render rule renders as its `paragraph`; an unknown term renders as `unit`. The most specific term wins where two declare the same expectation.

### 7.2 Term predicates

| | |
|---|---|
| `refines · definition · aligns` | single parent; one-sentence definition (the contract for the word); optional alignment to a spine class (BFO/CCO, DoCO, FaBiO…) for the RDF projection |
| `matches` | classification: mime, plus a header fingerprint, a selector, a magic. The most specific matching term is what `whole` manifests by derivation; a stored `manifests` at `whole` overrides it |
| `axes · physical · tree · derivation` | mime-root declarations: the intrinsic address axes; which scope is physical (page); whether the tree is *asserted* (pdf: `in`/`ord` are judgments) or *derived* (csv, html, epub: from the parse); the op that yields the quote surface (`pdf.words@1`, `html.text@1`, `csv.parse@1`) |
| `reads` | the aspect a scope of this term is read under: text · cells · tex · none. Every aspect is a lossless transcription; there is no descriptive aspect and an extension may not declare one. Resolved along `refines` |
| `field` | a declared field on `manifests`: name, kind (int · enum · datetime · string · col · designator), required. A **designator** field is a verbatim sub-reading with `where`, `pattern` and the derived `address` key it feeds |
| `expects` | child terms a scope of this term normally contains; each missing one is a soft lint, never an error |
| `owes` | world predicates the concept manifested by a scope of this term should have. Unmet is *demand* (§9.5), derived |
| `convention · renders` | reading conventions inherited down the tree (sub/superscripts flattened outside math; footnote marks as `[^n]`; hyphens rejoined); the markdown form per term, fallback along `refines`. A consumer may ignore `renders` entirely |
| `select · shape · spine` | derived structure for markup, tabular and container roots: a CSS selector → term (+ `in`, field source); a column → term (+ scheme, pattern, required); a package's order → `in whole, ord` |
| `sentinel · keys · chrome` | values that derive to null ("Not Available"); the key column of a key-value table; selectors whose text is chrome |
| `concept` | the harvest rule: scopes of this term manifest a concept of `term`, keyed by a field or cell, with a map from owed predicates to the scopes or cells that evidence them (§9.4) |
| `lint` | a term-specific check in prose the tooling implements by name ("every TOC row names a heading"; "declared epub:type agrees with the derived term") |

```
{"subject":"pdf","predicate":"refines","value":"document"}
{"subject":"pdf","predicate":"matches","value":{"mime":"application/pdf"}}
{"subject":"pdf","predicate":"axes","value":["page","bbox"]}
{"subject":"pdf","predicate":"tree","value":"asserted — in and ord are judgments"}
{"subject":"pdf","predicate":"derivation","value":"pdf.words@1"}
{"subject":"heading","predicate":"refines","value":"unit"}
{"subject":"heading","predicate":"reads","value":"text"}
{"subject":"heading","predicate":"field","value":{"name":"num","kind":"designator","where":"leading","pattern":"^\\d+(\\.\\d+)*\\.$","address":"sec"}}
{"subject":"heading","predicate":"renders","value":{"md":"#{level+1} {num} {body}"}}
{"subject":"methodological-tool","predicate":"refines","value":"regulation"}
{"subject":"methodological-tool","predicate":"expects","value":["cover-page","table-of-contents","heading","equation","parameter-table","revision-history"]}
{"subject":"methodological-tool","predicate":"owes","value":["version","title","issued_by","entered_into_force","keywords","decision_class","calculates","supersedes"]}
{"subject":"xenforo-thread","predicate":"matches","value":{"mime":"text/html","selector":"html#XF[data-template=\"thread_view\"]"}}
{"subject":"xenforo-thread","predicate":"select","value":{"selector":"article.message--post","term":"post","ord":"document order"}}
{"subject":"amazon-order-history","predicate":"shape","value":{"col":"ASIN","term":"product-identifier","scheme":"asin"}}
{"subject":"parameter-table","predicate":"concept","value":{"term":"monitored-parameter","key":"Data / parameter:","claims":{"symbol":"Data / parameter:","unit":"Data unit:","description":"Description:"}}}
```

### 7.3 Mime roots and class

Every mime has a root term that refines one of three: **document** (readings can total to a proxy: pdf, html, xhtml, markdown, rfc822, epub members), **image**/**media** — lossy (readings can be drawn, never total: raster images, audio, video), **data** (intrinsically addressable, values given by the parse: csv, json, vcard, archives and other containers). Class is a lookup on the chain, overridable by one stored `manifests` at `whole` (a PDF of photographs manifests `scan-album`). Containers are data; members carry their own terms; nothing is classified twice.

### 7.4 The pin

`pass.ontology` is the BLAKE3 of the ontology layer as loaded (sorted term files). A term change makes every pass pinned at the old hash *stale* for the scopes that manifest it or its refinements — derived, listed, re-run; nobody edits a recipe. Extensions add term files and lines; a line at a foundation term's existing identity is refused.

> v52 → mime/, origin/, atom/, form/, context/ schema namespaces; ledger schemas/{type}.yaml and value kinds; the ontology layer §15 with BFO/CCO spine. The spine survives as aligns targets; forms retire into terms; the recipe parameter of the first TOOL03 pass retires into the hash pin.

## 8. Derived, never stored

The following are functions of stored lines and are computed at read time. Writing any of them to a file is a lint failure.

| | |
|---|---|
| `class, root term` | from attests.mime through matches; from the refines chain |
| `manifests, in — where the tree is derived` | from the parse through select / shape / spine; a stored line at the same scope wins |
| `chrome` | repeated runs; text outside selected terms; declared chrome selectors |
| `positional and designated addresses` | from manifests fields, in, ord |
| `binding state: bound · held · flagged` | from an evidence entry's reading reference against current revisions |
| `status` | from bound entries, kinds, modes and standing challenges (§9.3) |
| `demand` | held entries, unmet owes, unsupported claims, unmet expects, stale passes |
| `staleness` | pass.ontology ≠ current, for the scopes a changed term reaches |
| `walked extent, section closure, ¶n` | from in and ord |
| `the export, the remainder, the envelope` | §11 |
| `sensitivity` | the layer a line lives in |

## 9. The ledger — concept subjects

### 9.1 Concepts

A concept is a real-world thing with a slug. Its file is lines: `term` (one line per term it is), `manifested_by` (the scope that is its manifestation, at any grain — a book, a chapter, a figure, a list item that is "Option A"), `part_of`, and one line per claim. Records are evidence and roster, never identity. Edges are claims whose value is an `object` slug with `qualifiers`.

### 9.2 Evidence entries

A claim carries `evidence: []`. Each entry is authored once and bound by verify:

| | |
|---|---|
| `anchor` | `corpus://<blake3>?<at>[&aspect]` — tight: the smallest scope the quote lies in, one cell of a table, never a region |
| `quote` | verbatim from the reading or derivation named; typographic re-takes and elided composites are refused (Q4 confirmed) — optional `prefix`/`suffix` disambiguate a repeated string |
| `kind` | source grade: authoritative · direct · incidental |
| `mode` | how the entry supports the value: stated · inferred · reported (+ `reasoning` when not stated) |
| `reading` | the binding, stamped by verify: a reading `rev`, or `derived:<op>@<v>` where the parse is the quote surface, or null — *held* |

Three links are checked separately: claim → reading (the quote is in the bound body), reading → bytes (L7, §10.3), value ← quote (the reviewer's judgment). `ref://` citations into mirrored reference datasets are entries of the same shape with the mirror's snapshot as the binding.

### 9.3 Status, derived

| | |
|---|---|
| `confirmed` | the bar is met on bound entries (one authoritative, or independent direct entries) and no challenge stands |
| `provisional · inferred · reported` | bar not met; the mode of the best bound entry |
| `disputed · conflicting` | a `challenges` stands · a bound sibling disagrees on a functional predicate |
| `unsupported` | no bound entry — a hypothesis is a claim in this state; a proposed subject is one whose lines are all here |
| `refuted` | unsupported with an upheld challenge; stays as a tombstone so harvest does not re-infer it |

There is no `promote`, no `confidence`, no interpretations tree. `same_as` merges the moment it derives confirmed, with one lineage row. `challenges` names a claim by identity key and content hash. "X is not attested" is `presence: none`.

### 9.4 Harvest

A term's `concept` lines are the harvest rules. For each scope manifesting the term, harvest mints the concept keyed as declared, writes one claim per mapped predicate with an entry anchored at the evidencing cell or scope, bound to the derivation where the parse is the surface, `by: harvest:<term>@<ontology-hash>`. Repeat appearances are additional entries on the one claim. Harvest caps at what a single record can support — by construction, since it never cites two sources. Change the key map in the term file and the ledger follows.

### 9.5 Demand

Derived, never stored: a held entry enqueues a reading pass over its unit; an unmet `owes` is a search; an unsupported claim is a capture; a stale pass is a re-run; an unmet `expects` is a soft lint. Only `blocked` is authored — a claim naming the demand it blocks and why. An absence the bytes print ("–", a missing row) is demand, not a defect.

```
{"subject":"pe-fc-j-y","predicate":"term","value":"parameter"}
{"subject":"pe-fc-j-y","predicate":"manifested_by","value":"corpus://404d090f…?page=3&bbox=0.1853,0.8509,0.718,0.0293"}
{"subject":"pe-fc-j-y","predicate":"symbol","value":"PE_{FC,j,y}","evidence":[{"anchor":"corpus://404d090f…?page=3&bbox=0.1853,0.8509,0.718,0.0293&text","quote":"$PE_{FC,j,y}$","kind":"authoritative","mode":"stated","reading":"b3:da29f220436826be"}],"by":"harvest:definition@b21541"}
{"subject":"amazon-ca","predicate":"name","value":"Amazon.ca","evidence":[{"anchor":"corpus://1409369e…?row=1&col=28","quote":"Amazon.ca","kind":"authoritative","mode":"stated","reading":"derived:csv.parse@1"},{"anchor":"corpus://1409369e…?row=2&col=28","quote":"Amazon.ca","kind":"authoritative","mode":"stated","reading":"derived:csv.parse@1"}],"by":"harvest:amazon-order-history@b21541"}
// derived: status confirmed · confirmed
```

> v52 → facts/ vs interpretations/ (the physical assertion boundary), the authored six-rung ladder, promote, the per-(fact, source) verified.touch and ops map, the sources table, citation_surface: segments. All replaced by per-entry binding and derivation. The coverage obligation (every record represented) becomes: every artifact's root scope is manifested_by something or its class is lossy with no demand.

## 10. Passes, inspection, the owner

### 10.1 Passes

A pass is one author and one verifier over one artifact (or one member set, with `with` naming the container's pass). A claim exists only once both have signed; there is no draft state. A correction pass swaps roles so no correction is self-verified. A pass may start from a layout engine's proposal run as an op (`docling.layout@2` beside `pdf.words@1`) and accept or correct against it; the tool's labels never enter the file under an op's `by`.

### 10.2 No stamp

There is no substitution grain. An artifact, however completely walked and read, is a set of annotations; the bytes remain the authority for delivery, export and serving, and verification needs them regardless. What survives of the stamp is the **inspection surface**: bytes ‖ derivation ‖ reading per unit, lints pre-run, on the owner plane.

### 10.3 L7 — the reading against the bytes

For every reading, compare the body to the derivation at its `at` after the scope's conventions and designator strip — **per aspect**: sequence diff for `text`; per cell for `cells`; identifier/operator multiset after stripping layout for `tex`. Where the root term declares no derivation for the aspect, every reading is listed for inspection. Divergence is listed for a human; it is never auto-resolved.

### 10.4 The owner file

The owner's acts are lines in `<blake3>.owner.jsonl` — a second writer, a second file. `inspected` records an accepted divergence by reading revision with a reason, so L7 converges on re-run; it lapses with the revision. External captures, deletions and normative changes stay owner-gated; everything else is a pass.

```
{"at":"page=3&bbox=0.1853,0.7778,0.7174,0.0356","predicate":"inspected","value":{"rev":"b3:0c41…","diverges":"accepted","why":"2-D math; derivation is baseline-ordered, reading is TeX"},"by":"owner","date":"2026-10-12"}
```

> v52 → sweep/coverage, the Normalizer's self-verification, the normalization queue as the one demand channel (demand is now derived and the queue consumes it), the stamp of direction §4 (parked: a tree hash of the lines is a blob hash; if it returns it pins the file's blob and lives in the owner file).

## 11. Export — a derivation

The markdown proxy is an output, not a record. It walks the tree in `ord`, emits each scope through its term's `renders` rule (designators re-emitted from fields), carries every block's `at`, and names in its header the authority (*the bytes*), the pass and ontology hash, the inspected divergences, the chrome and the remainder — every word that lies in no scope. It is lossless back to the bytes, never a citation target, and never breaks on a new term. The RDF projection is the same walk over N-Quads.

## 12. Planes and publication

- The **public plane** serves the foundation. An **audience plane** serves the foundation plus the extension layers its grant names. The **owner plane** serves the whole chain, the owner files and every lint.
- Each plane also filters by **derived status** at a rung the consumption contract names (public: confirmed; audiences as declared; owner: everything). Pre-assertion content is a status filter, not a directory.
- Read-only is normative. Consumers read `ledger://`, materialise `corpus://` only for what the ledger already asserts, never cite a generated view, and pin the reproducibility tuple (layer commits, ontology hash) when freezing a build.

## 13. Lints

Four generic, the rest generated per term. A failing generic lint blocks the pass from signing; term lints are listed on the inspection surface.

| | |
|---|---|
| `G1 unit` | every reads_as sits at a scope with a manifests whose term reads that aspect |
| `G2 tree` | every in resolves to a scope; ord contiguous from 0 per parent; no cycle |
| `G3 cover` | under a walked extent, every word of the derivation lies in a scope or in derived chrome |
| `G4 cite` | every anchor resolves; every quote is in its bound surface; a bound revision that no longer exists is flagged |
| `per term` | reads satisfied · required fields present · designators match the derivation under where/pattern · expects met (soft) · owes met (demand) · the term's own lint lines · L7 per aspect · matches agrees with the stored root |
| `per file` | no undeclared field · no derivable value stored · no reads_as under an aspect outside text · cells · tex · one writer per file · sorted · pass refs resolve · ontology hash known |

## Appendix A. Retired from v52

The markdown record and its zones · form / atom / section / segment / placement grammar · the five schema namespaces · touch[] and record status · sweep / coverage · el= / turn= / block= / region= and URI transforms · the classify, reference, concept and relation annotation namespaces · re-stub and the "no formless zone" gate · triage as a form proposer (it survives as a term proposer) · derived views (classifications, issues, uris, timeline…) · the interpretations tree and the physical assertion boundary · the authored status ladder, promote, confidence · verified.touch, the ops map, the sources table, citation_surface: segments · origin tenancy, the visibility floor, the union rule · the whole-record stamp · the structure predicate and the recipe parameter of the first successor drafts.

## Appendix B. Regression set

| predicate | by | meaning |
|---|---|---|
| `pdf · 404d090f…` | asserted tree | CDM TOOL03 v03.0, 10 pages. 147 scopes · 150 manifests · 137 in · 121 reads_as · 1 pass · 11 concepts / 75 claims / 13 owed. Exercises: page-spanning containers, 2-D math, a source typo, chrome, designators, the TOC lint, harvest from parameter tables. manifest |
| `csv · 1409369e…` | derived tree | Amazon order history, 275 × 29. 4 stored lines · 306 derived manifests · 426 concepts / 2,087 claims / 62 owed. Exercises: matches by header fingerprint, shape, sentinels, a declared-field derivation (money.parse), harvest keyed across rows. |
| `html · dd0a7844…` | derived tree | XenForo thread, 10 posts, 689 KB. 4 stored lines · 42 derived scopes by select · 16 concepts / 77 claims. Exercises: bytes= as the axis, select, declared chrome, a captured snapshot time, designators from attribution. |
| `epub (mock)` | container | members as subjects, spine → in/ord, epub:type → terms, harvest from the OPF. Review §8 — §8.3's `description` reading is withdrawn under rule 6. |
| `exemplars/` | reading model | the two-column PDF (ord), the mp3 (re-key without anchor moves), the structured-text conversation (data has no readings). |

## Appendix C. Open before ratification

- **O10** — assessments: a `note` predicate with no evidence on the owner plane only, or prose stays out of knowledge.
- **O11** — `mode` per entry: the best bound entry decides the rung (proposed); confirm.
- **L7 for tex** — the multiset comparator is specified, not built; Equation (1) is accepted by hand today.
- **Two root classes at once** (a scanned regulation): resolved by the most specific `matches` and one stored override; needs an exemplar.
- **Term governance** — who reviews a proposed term into a foundation. Not a spec question; must exist before the first extension ships one.
- **Migration** — ath-steven's authored statuses become checks; records become exports; the 400 floor records are placed in a layer. The measured cost is owed with the amendment.

Borrowed vocabulary, by design: Web Annotation (anchor + quote with prefix/suffix) · PROV (pass, by, verify, lineage) · nanopublications (claim + provenance as named graphs) · Akoma Ntoso (designated addressing) · Datomic (fact log + transaction entity = line + pass). What no precedent combines — intrinsic addresses, structure as verified judgment, readings as revisions bound per evidence entry, status and demand derived, the ontology as the recipe, one-way layering — is the system.

## Appendix D. Reference-implementation rulings

The draft leaves gaps that code cannot leave open. Each ruling below is what the reference implementation (`ath/`) does, where the review (`spec/successor-review.md`) raised it, and the test that pins it. A ruling is a proposal until ratification; the owner may overturn any of them, and the test then changes with the text. Tests are named by the file that will hold them; a ruling without a green test is not yet in force.

| id | question | ruling | pinned by |
|---|---|---|---|
| D-F1 | Who attests a ledger line? (§4.1 names `by` for ops and `pass` for a pass line "in the same file"; §10.1 defines passes over artifacts only.) | A ledger pass is a line `{"subject": <slug>, "predicate": "pass", "value": {id, by, verify, ontology, date}}` in the concept file. Authored claims carry `pass`; harvests carry `by: harvest:<term>@<pin>`. A ledger line with neither, or with a `pass` that does not resolve in its file, is refused at write. | `ath/test/lint.file.test.ts` |
| D-F2 | Pages carry no `in`, yet cover labels and the TOC hang off a page and the export emits them. | Pages stay physical. `cover-page` and `table-of-contents` refine `unit`, carry `in whole, ord N`, and own the scopes on their page. G2 requires every non-page scope to be reachable from `whole` by `in`. | `ath/test/lint.generic.test.ts` |
| D-F3 | The binding grammar (§9.2) is `rev | derived:<op>@<v> | null`; the data binds attributes and `captured_from` values. | `reading` is one of `b3:<16 hex>`, `derived:<op>@<v>[ <arg>]` (the argument names an attribute or path), `line:<predicate>[ <field>]` (a value read off an op line), or `null` (held). G4 checks the quote against the surface each form names. | `ath/test/model.evidence.test.ts` |
| D-F4 | `walked` on a derived tree is vacuous when chrome is the complement of the selection. | `walked` is written only where the root term's `tree` is `asserted`. On a derived tree the export header carries `remainder <chars outside units and declared chrome> / <text chars>`, and G3 checks against declared `chrome` selectors only. | `ath/test/corpus.tree.test.ts` |
| D-F5 | The ontology pin recipe is unstated and the regression pins do not reproduce. | Pin = BLAKE3 over the ontology layer serialised as: term files sorted by term name, lines sorted by identity key, each line compact JSON with non-ASCII unescaped, LF-terminated; written `b3:` + first 16 hex. The harvest pin is the first 6 hex. Every pin in the regression set is rewritten under this recipe. | `ath/test/ontology.hash.test.ts` |
| D-F6 | Source grade differs across the set (PDF/CSV `authoritative`, HTML `direct`) and decides public visibility. | Harvest writes `authoritative` when the concept is `manifested_by` a scope of the cited artifact and the predicate is one its term `owes`; otherwise `direct`. An authored entry keeps what its pass wrote. | `ath/test/ledger.harvest.test.ts` |
| D-F7 | Harvest anchors at the whole post and elides quotes. | A selector a `concept` map names must also be a `select` line (ontology lint). A field-derived value binds `line:manifests <field>` at the scope's bare `at`. A quote never carries `…`; a long value is quoted by `quote` plus `suffix`. | `ath/test/ledger.harvest.test.ts`, `ath/test/verify.quote.test.ts` |
| D-F8 | Design-page ids (`scope:`) leak into evidence entries. | `scope` is an undeclared field; the per-file lint refuses it; regression input strips it. | `ath/test/lint.file.test.ts` |
| D-D1 | A `reads_as` with `aspect: none`. | Refused. A term's `reads: none` is the whole statement; no line sits on the scope. | `ath/test/lint.file.test.ts` |
| D-D2 | `page=N` lines store `number: N`. | A field may be declared `derived: true` on its term; a derived field is never stored and the per-file lint reads the declaration. `page.number` is declared derived. | `ath/test/lint.file.test.ts` |
| D-D3 | A concept manifested by several scopes. | `manifested_by` is repeatable, one line per manifesting scope; evidence accrues on the one claim it supports. | `ath/test/ledger.file.test.ts` |
| D-D4 | A `stated` entry whose value is not its quote (`Pontiac G8 Forum` from `Idle/stall \| Pontiac G8 Forum`). | `html.title@1` stays an op; the claim is `mode: inferred` with `reasoning`. G4 refuses `stated` where the value is not a substring of the quote after normalisation. | `ath/test/verify.quote.test.ts` |
| D-D5 | No lineage in the regenerated set. | Every identity whose content changes gets a lineage row, `by: regenerate@<version>`. | `ath/test/corpus.file.test.ts` |
| D-D6 | "Data has no readings" versus `record reads cells`. | Read as "no *stored* readings". A derived reading lives in the scope table and binds as `derived:<op>@<v>`. | text only |
| D-rev | The revision recipe. | `rev` = `b3:` + first 16 hex of BLAKE3 over the body: a string as UTF-8, an array as compact JSON (`JSON.stringify`, non-ASCII unescaped). Verified against all 121 regression readings. | `ath/test/corpus.readings.test.ts` |
| D-staging | §10.1 says there is no draft state; a pass needs somewhere to accumulate lines before both have signed. | Pass lines stage in `<layer>/.ath/passes/<blake3>/<id>.jsonl`, outside the trees, until `pass sign` merges them. Nothing under `corpus/` exists unsigned. | `ath/test/corpus.pass.test.ts` |
| D-bbox | Box precision and containment. | Canonical boxes carry at most 4 decimals; `pdf.words@1` rounds to 4; containment uses ±0.002 slack per edge. | `ath/test/model.address.test.ts` |
| D-csv | Row and column numbering. | `row=0` is the header; `row=N` is the physical logical row and sits `in whole, ord N−1`; `col` is 0-based; `?col=<name>` resolves through the header; a BOM is recorded in `attests` and stripped from the surface; sentinels derive to null only in harvest, never in the surface. | `ath/test/ops.csv.test.ts` |
| D-html | The `html.text@1` surface and the byte map. | Drop `head`, `script`, `style`, `template`, `noscript`, `svg`; block elements and `<br>` end a line; `td`/`th` separate by tab; whitespace runs collapse to one space; lines trimmed; blank runs collapsed. A scope's span is its start tag's first byte to its end tag's last byte, half-open; an implied end is flagged. The byte map is a prefix sum of UTF-8 lengths per UTF-16 code unit of the decoded file. | `ath/test/ops.html.test.ts` |
| D-chrome | Chrome by repetition on an asserted tree. | A line is chrome when its digit-masked text and its box rounded to 3 decimals recur on at least max(3, 0.4·pages) pages; role `page-number` when the masked text matches `# of #`; otherwise `running-header`/`running-footer` by position. Chrome words are excluded from G3. The thresholds are a `convention` line on `document`. | `ath/test/corpus.chrome.test.ts` |
| D-L7 | One normaliser; the `tex` comparator. | G4 and L7 share one normaliser: NFKC, quote and dash folding, NBSP → space, whitespace collapse, then a second pass with whitespace and hyphens removed. Text compares by token LCS; cells per cell as a contiguous run in the row's column-aware words; tex by the multiset of letters, digits and operators after TeX layout is stripped and `\sum \times \rho` map to their symbols. Divergence is listed; an `inspected` line by rev accepts it. | `ath/test/lint.l7.test.ts` |
| D-status | Derived status. | `confirmed` ⇔ a bound `authoritative` entry, or two bound `direct` entries from distinct artifacts, and no standing challenge; `disputed` ⇔ a challenge stands; `conflicting` ⇔ a bound sibling disagrees on a predicate the term declares `functional`; else the mode of the best bound entry; else `unsupported`; `refuted` ⇔ unsupported with an upheld challenge. | `ath/test/ledger.status.test.ts` |
| D-ocr | Rule 6 on a raster. | A raster root declares no `derivation`. `image.words@1` (tesseract word boxes) is a proposal op: a pass accepts its boxes into `manifests` + `reads_as` or does not. L7 lists every image reading for inspection. The engine version rides in the pass note. | `ath/test/ops.image.test.ts` |
| D-union | Union address order. | Members of `a;b;c` sort by page, then y, then x; the resolver canonicalises before identity. | `ath/test/model.address.test.ts` |
| D-select | Selector engine. | CSS selectors are evaluated by `css-select` over the parse5 tree; the ontology may use any selector it supports. Owner-confirmable. | `ath/test/ops.html.test.ts` |
| D-pdf | PDF engine. | `pdf.words@1` is pdfium (the same engine as v52's pypdfium2) through `@embedpdf/pdfium`; `pdftotext -bbox-layout` may run as a cross-check op and is never bound to. Owner-confirmable. | `ath/test/ops.pdf.test.ts` |
| D-spike-pdfium | Can pdfium run inside a compiled `ath` binary? | Yes. `@embedpdf/pdfium` 2.15.1 initialises from `pdfium.wasm` embedded with `with { type: "file" }`; `FPDFText_*` char boxes agree with pypdfium2's on the fixture PDFs; the compiled binary runs from any directory. No fallback needed. | `ath/test/ops.pdf.test.ts` (M3) |
| D-spike-parse5 | Do parse5 source offsets survive the htmlparser2 tree adapter, and map to bytes? | Yes. `sourceCodeLocation` is present on adapter nodes; a prefix-sum table of UTF-8 lengths per UTF-16 code unit maps start/end offsets to byte ranges exactly, astral characters included; `css-select` runs over the same tree. | `ath/test/ops.html.test.ts` (M2) |
| D-F7b | Which names may a `concept` map use? (The regression ontology named CSS selectors in maps.) | A concept map names scopes by **term**: `author`; a field as `term.field` (`post.position`) or `predicate.field` for an op line (`captured_from.uri`); an attribute of the scope's own element as `@attr` (`@data-site`); an edge as `term → concept-term`; a cell by index for definition lists; `*` for every row. A selector is never a map value or a key; the ontology lint refuses one. The regression ontology gains `member-title`, `author-link` and `quote` terms with `select` lines, and `select` lines may name an `attr` that fills a `field`. | `ath/test/ontology.test.ts` |
| D-concept-key | A `concept` line without a `key`. | Allowed: the concept is the one the enclosing document manifests (`metadata`, `revision-history` augment the document's own concept). | `ath/test/ontology.test.ts` |
| D-D7 | The regression ontology's `text` term declared `reads` as a sentence. | A `reads` value is exactly one of `text`, `cells`, `tex`, `none`; the lint refuses prose. The data is corrected to `text`. | `ath/test/ontology.test.ts` |
| D-identity-ontology | What does an ontology line collide on? | A single-valued predicate collides on `(subject, predicate)`; a repeatable one (`field`, `select`, `shape`, `convention`, `concept`, `lint`, `matches`) on `(subject, predicate, name)` where the name is the value's `name`, `col`, `selector` or `term`, else the whole value. An extension writing a foundation term's existing identity is refused. | `ath/test/model.line.test.ts`, `ath/test/ontology.test.ts` |
| D-ingest-op | What op attests at ingest, and what writes `captured_from`? | Both lines are `by: ath.ingest@1`. Provenance comes from a sidecar JSON, flags, or the bytes themselves (a v52 capture banner's `corpus-capture-*` meta tags), merged in that order. A second ingest of the same bytes with the same provenance is a no-op; with different provenance it is refused (an op line is never corrected; a superseding line is a later ruling). | `ath/test/corpus.ingest.test.ts` |
| D-shadow-same | An extension ingests bytes its foundation already holds. | Same identity, same content is a no-op and writes nothing in the extension; different content is refused. | `ath/test/corpus.ingest.test.ts` |
| D-col | A column of a table as a scope. | `col=M` is an address axis of tabular roots beside `row=N[&col=M]`: a column scope (the shape's term, `name` from the header) contains its cells. Columns carry no `in` (an axis, like a page) and are not G2 findings. | `ath/test/model.address.test.ts`, `ath/test/corpus.derive.test.ts` |
| D-csv (amended) | Ord on a tabular tree. | `row=0` (the header) is `in whole, ord 0`; `row=N` is `in whole, ord N`. | `ath/test/corpus.derive.test.ts` |
| D-mime-root | An expression root (`amazon-order-history`, `xenforo-thread`) is not on the mime root's chain. | The artifact's effective chain is the expression root's refines chain followed by the mime root's (`csv`, `html`, `pdf`: the most specific term whose `matches` is the mime alone). Axes, tree, derivation and physical come from whichever declares them first. | `ath/test/corpus.derive.test.ts` |
| D-key-holders | How many concepts does a `concept` line mint? | One per holder of its key under each scope of the owning term: every scope of the key's term (`post.id` → every post), every record row for a column key (`Order ID`), the owner scope itself for `@attr` and op-line keys. Claims resolve within the holder, then within its parent (a member's `member-title` is the post's child, not the author-link's). | `ath/test/ledger.test.ts` |
| D-edge-cite | What evidence does an edge to another concept carry? | When the edge's left side is a term whose scopes are containers (`post → forum-post`), one edge per scope, cited by the target concept's key (`line:manifests id`); a value edge (`Website → marketplace`) is cited by the cell or text that names it. `qualifiers.as` keeps the value the bytes printed. | `ath/test/ledger.test.ts` |
| D-slug | How a harvested concept is named. | `slug` on the concept line is a template over `{term}`, `{key}` and `{1}` (the first group of `extract` applied to the key), default `{term}-{key}`; non-alphanumerics become `-`; lowercase unless `case: keep` (ASINs). | `ath/test/ledger.test.ts` |
| D-designator-where | Where a designator's text comes from on a derived tree. | `where` may name a descendant term (`post.position` from the `post-number` scope); the pattern runs over that scope's text. | `ath/test/corpus.derive.test.ts` |
| D-expects | What satisfies `expects`. | A scope manifesting the expected term or any term that refines it. The page expectation moves from `document` to `pdf`. | `ath/test/lint.test.ts` |
| D-pass-line | A `pass` line carries no attestation of its own. | It is the attestation; the per-file lint exempts it. | `ath/test/lint.test.ts` |
| D-sign | What `pass sign` lints, and against what. | The stored lines with the pass's staged lines laid over by identity (plus `walked` when asked), in canonical order; G1–G3, per-file and per-term lints; any blocking finding refuses the signature and leaves the staging untouched. A staged line at an existing identity with different content is a correction with a lineage row `by: pass:<id>`. | `ath/test/corpus.pass.test.ts` |
| D-G3-severity | When does an uncovered word block? | On an asserted tree G3 lists the words outside every scope and chrome; it blocks only under `walked` (the pass claims completeness). A `walked` on a derived tree is itself a finding (D-F4). | `ath/test/corpus.pass.test.ts` |
| D-L7-text | What the text comparator absorbs. | Designator fields stripped from the derivation's head or tail; footnote marks `[^n]` removed from the reading and the superscript digit unglued from its word in the derivation; bullets dropped; then a token comparison, then the squashed comparison. Punctuation is content: a dropped period diverges. | `ath/test/lint.l7.test.ts` |
| D-L7-tex | The tex comparator. | Control words map to their symbols (`\sum` → ∑, `\times` → ×, `\rho` → ρ), braces and script marks drop, the `Equation (n)` label drops from the derivation; the multisets of letters, digits and operators must agree. Equation (1) of TOOL03 passes. | `ath/test/lint.l7.test.ts` |
| D-inspect | The owner's acceptance. | `inspect accept` is admin-tier (typed confirmation at a terminal, never under `--json`), writes `{at, inspected, {rev, diverges: accepted, why}, by: owner, date}` to `<blake3>.owner.jsonl`, and binds to the reading revision: a re-read lapses it. `inspect revoke` removes it with a lineage row. | `ath/test/corpus.pass.test.ts` |
| D-pass-id | Pass ids. | `p<n>`, the lowest free number after every signed and open pass on the artifact; the author and verifier must differ. | `ath/test/corpus.pass.test.ts` |
| D-ocr (applied) | The raster exemplar. | `lossy` and `image` enter the ontology (`image` reads none, axes `bbox`, tree asserted, no derivation); `jpeg`/`png` match their mimes. `ath image words` runs tesseract (`--psm 6 tsv`) and prints proposal lines — one `label` scope per OCR line, placed in whole in reading order, with a text reading — that a pass stages like any other lines. L7 lists each as `no-derivation`. The synthetic sign (`testdata/synthetic/sign.jpg`) is the exemplar. | `ath/test/ops.image.test.ts` |
| D-container-route | A claim cited through a container. | `corpus://<zip>?path=<p>[;<at>]` canonicalises at bind time to the member subject the roster names at that path, with the remaining address applied there; a path the roster lacks is flagged. `zip` and `container` enter the ontology (`container` refines `data`, axes `path`, tree derived from the roster). | `ath/test/corpus.container.test.ts` |
| D-zip-reader | How zip members are read. | A reader of the engine's own over the central directory (store, deflate, zstd — what Discord's exporter writes); zip64 is refused loudly. No library pins the op. | `ath/test/regression.test.ts` |
| D-physical-addressable | Which addresses exist without a line. | A row the parse holds (tabular) and a page the document has (PDF) are scopes an anchor may name even when nothing manifests there; a cell within such a row likewise. | `ath/test/corpus.container.test.ts` |
| D-planes | What each plane serves (spec §12, applied). | `public`: the foundation layers and claims whose derived status is `confirmed`; `audience:<name>`: the foundation plus every extension whose `tier` the audience's grant (`audiences:` in athenaeum.yaml) names, same status filter; `owner`: the whole chain, every status, the owner files, demand and findings. The server re-reads the layer per request and holds no state. | `ath/test/serve.test.ts` |
