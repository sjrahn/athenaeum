<!--
Successor contract, draft 2 — UNRATIFIED. v52 (spec/athenaeum.md, corpus.md, ledger.md, custody.md) stays the law
until this draft is ratified as one amendment (Part I §8). Source: the design project "Athenaeum successor model
design", page "Successor Spec" (2026-10-12), converted to markdown on 2026-10-13 without change to its text; draft 2
(2026-10-17) is the owner's revision after the instance's migration census (§0).
Review: spec/successor-review.md. Reference implementation: ath/ (the sprint/refactor branch); its rulings on what
the draft leaves open are Appendix D, which grows with the implementation and is folded into the text at ratification.
-->

*ATH · successor · draft 2 · 2026-10-17 · supersedes v52 on ratification*

# Athenaeum Specification — the contract

The Athenaeum captures bytes, describes what they manifest, and asserts what they express — each as a line that names its subject, its author and the evidence it rests on. Nothing stored is a function of anything else stored. The bytes remain the authority. Three things are kept because nothing else can recover them — the bytes, the testimony of where and how they were found, and the owner's acts; everything else is derived from them or rediscovered over them, and the facts so found are the product.

## 0. Status and precedence

- v52 is frozen and stays the law for the current tooling. This draft is written in Sol §7's order — contract first, grammar inside it — and is ratified as one amendment, never incrementally.
- **Part IV (custody)** is carried, read in this draft's vocabulary: identity is the BLAKE3 of the bytes; bytes reside across declared locations and resolve by content address. Its *members-block* is a container's `attests` roster (§5.1), and a promoted record's origin lineage is derived containment (§8). One rule is added: a standalone copy of an artifact's bytes may be retired once another route — a container's member, a location — resolves the same bytes, the full BLAKE3 verified first (Part IV principle 3). Testimony is never retired (§6a).
- Part I's principles survive where they are not contradicted here: deterministic before LLM, durable vs regenerable, offline-first, no transitionary states, the specification is law. Where this draft and Part I disagree, this draft wins.
- Regression set: the artifacts of Appendix B, every one generated and committed. A rule that cannot be shown on one of them is not in the contract.
- **Draft 2** (2026-10-17) adds rules 1 and 2 (§1): what is irreplaceable, and formats, not conventions. Provenance leaves the record: `captured_from` retires and a producer's testimony becomes an artifact of its own, linked by `testifies` (§6a); a member inherits its containers' testimony by derivation. `attests` stays, as a cache with a pin. Selectors are read in the root family's language, a header row and chrome are declared, never assumed (§7.2). The rulings this moves are marked in Appendix D as drafted ahead of the implementation.

## 1. The system in eight rules

1. **Three things are kept; everything else is recovered.** The bytes, the testimony of where and how they were found (§6a), and the owner's acts are irreplaceable: each is a snapshot nothing else reproduces. Every other stored line is an op's output — deterministic, re-derivable, kept as a cache with a pin — or a judgment a pass wrote, checkable against the bytes and rediscoverable by another pass. The ontology is scaffolding of the second kind: two instances fed the same bytes may build different ontologies, and should arrive, given time, at the same facts. The facts are the product.
2. **The tooling knows formats, never conventions.** An op sniffs a mime, attests what the format's own specification defines, addresses the bytes on the axes the format has, decodes a surface, and exposes the format's own nodes — an element, a MIME part, a JSON value, a zip entry, a `data:` URI. It never names a term and never decides what a node means: that a row is a header, that a `>` line is a quote, that a repeated line is a running header, that an element is a post. A scope below `whole` exists only where an ontology line (`select`, `shape`, `spine`, `chrome`) or a pass puts it. Meaning is the ontology's and the record's; a new kind of thing is an ontology edit, a new format is one op module.
3. **Everything is a claim line.** Artifact facts, structure, readings, world facts, ontology terms, passes and owner acts are all lines of one grammar: a subject, a predicate, a value, an attestation. One sort, one merge, one lineage.
4. **Ops author byte-facts; passes author judgments.** Anything that can be wrong is written by a pass and verified by a second one. Anything an op writes has no status because it has no judgment in it.
5. **Addresses are intrinsic.** A scope is named by coordinates in the bytes — page and box, byte range, row and column, time — never by a transform, a parser's tree or an id.
6. **The ontology is the recipe.** A scope *manifests* terms; what a term expects — fields, reading aspect, children, owed world facts, render form — rides on the term. A pass pins the ontology it read against by hash; nobody chooses a recipe.
7. **Derived, never stored.** Class, status, demand, held/flagged, chrome, staleness, provenance through containers, every non-intrinsic address and the export are computed from stored lines at read time. A stored copy of a derivable thing is a defect.
8. **Nothing lossy enters the corpus.** A reading is a transcription checkable against the bytes — never a summary, a description, a paraphrase or a characterisation. Where a scope has no lossless transcription, the record marks its address and stops. What a scope shows, means or contains is a *world claim*: it lives in the ledger, cited to the scope, graded like any other claim. The record contains nothing unfalsifiable against its own bytes — which is why where the bytes came from is not in it: that is a producer's testimony, an artifact of its own (§6a).

> v52 → the record was a markdown proxy carrying promises (forms, atoms, segments, touch chains, status); the ledger was JSON objects with an authored status ladder. Both become lines; the proxy becomes an export (§11).

## 2. Layers — foundation and extension

An instance is a **chain of layers**, the bottom public. A private instance is an *extension* of a public *foundation*, never a peer. A foundation may itself extend another.

- `athenaeum.yaml` names the foundation, pinned by commit or manifest. The foundation is read-only from above.
- **Resolution** is content-addressed and unscoped: a hash or slug resolves in the extension first, then down the chain. The view of a subject is the *line-set union* of its files across layers.
- **Tenancy is layer.** Everything in the foundation is public by construction; everything in an extension carries that extension's tier. Origin `tenancy:` declarations, the union rule and the visibility floor are gone.
- **Shadowing: refuse in the corpus, override in the ledger.** An extension may not write at a foundation artifact's existing identity (§4.2) — disagreement with a foundation reading is demand upward. In the ledger the extension's line wins in the union.
- **Schema and ontology are foundation-owned.** An extension adds terms and fields; it never redefines a foundation term. A local mint is a proposal, nagged upward.
- **Publication is the foundation.** `ath serve` on an extension serves the union on the owner plane and the foundation on the public plane (§12).

> v52 → one private repository, tenancy derived per origin, sensitivity computed upward. Replaced by layering (direction §1–2). The 400 floor records in the owner's instance are the placement worklist.

## 3. Three trees, one grammar

```
<layer>/
├── ontology/<term>.claims.jsonl        terms — what a kind of thing expects
├── corpus/<blake3>.claims.jsonl        artifact subjects — what the bytes are and manifest (testimony too)
│          <blake3>.owner.jsonl         the owner's acts on that artifact (inspected)
│          lineage.jsonl                 moves, re-keys, supersessions
└── ledger/<slug>.claims.jsonl          concept subjects — what the world is, cited into the corpus
```

- **One-way reference.** An artifact file never names a concept. The ledger cites `corpus://` freely; the ontology is read by both and names neither. "World claims citing a scope" is an index, never a stored line in the corpus.
- **One file, two writers, never.** Passes write `.claims.jsonl`; the owner writes `.owner.jsonl`; ops append to `.claims.jsonl` only, and only `attests` and `testifies`, at ingest or an attests sweep.
- **The subject never names its testimony.** A testimony's file names the artifact it describes (`testifies`); which testimony describes an artifact is an index, as citations are.
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
{"subject":"hl-02","predicate":"version","value":"02.1","evidence":[{"anchor":"corpus://5e6e497d…?page=1&bbox=0.1429,0.6906,0.0901,0.0087&text","quote":"Version 02.1","kind":"authoritative","mode":"stated","reading":"b3:aae7b6bb9c216abb"}],"pass":"p1"}
```

### 4.2 Identity

Identity is the key a second line collides on. A write at an existing identity is a *correction*: delete + insert with a lineage row, never an edit in place.

| | |
|---|---|
| `attests` | (at, predicate, by) — a newer attester writes a second line that `supersedes` the first; never an edit |
| `testifies` | (at, predicate, value) — one line per subject the testimony describes; never corrected, since the testimony's bytes cannot change |
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

An artifact subject is `corpus://<blake3>`. A new hash is a new subject; the same hash met again is the same subject, and the encounter adds testimony only (§6a). A **container**'s `attests` carries its member roster: per member, its `path` in the format's own terms (a zip entry, a MIME part path, an mbox ordinal, the byte span of a `data:` URI) and its blake3. Every member is its own subject, and its file names no container: which containers hold it is derived from the rosters (§8). Cite the member, which outlives the package; the container route canonicalises to it.

### 5.2 The intrinsic address — `at`

The only address stored and the only address an anchor carries. Its axes are declared by the artifact's mime-root term (§7.3); every axis is a coordinate in the bytes, in the stored frame, with no transform.

| | |
|---|---|
| `whole` | the artifact; the subject of attests, testifies, pass, walked and the root manifests |
| `page=N · page=N&bbox=x,y,w,h` | pdf, images of pages; box normalised 0–1 in the page frame |
| `bbox=x,y,w,h` | raster images, on the pixel grid |
| `bytes=a,b` | every text format — html, xhtml, markdown, plain text, rfc822, json, ndjson, yaml, vcard: a byte range into the file (Q1 confirmed; `el=` retired) |
| `row=N · row=N&col=M` | csv, tsv, tabular data |
| `t=a,b` | audio, video — seconds in the stored stream |
| `path=…` | a container member, equivalent to the member's own subject; the route may stand anywhere in an address and the rest applies in the member |
| `a;b;c` | a **union address** — one box per page for a container that spans pages; a container's `at` is the union of its members' boxes, never a member's address borrowed |
| `…&text · &cells · &tex` | a trailing aspect names the reading surface a quote is taken from |

### 5.3 Derived addresses

Two further forms exist and neither is stored. **Positional** — the `ord` path (§5 ¶3), always available. **Designated** — the path of designators the bytes themselves print (`?sec=5&para=6`, `?eq=1`, `?post=4`, `?col=Currency`, `?ch=2&fig=1`), available where a term declares a designator field (§7.4). The resolver maps either to an `at` through `manifests`, `in` and `ord`. A world claim written against "paragraph 7 of the procedure" binds, through the resolver, to an intrinsic anchor — which is why designators are structure, not prose.

### 5.4 Re-capture and retarget

A re-capture is a new subject. `supersedes` on the new subject carries anchors across where the derivation at the same intrinsic address still holds the quote; otherwise the citing entry is *held* (§9.3). A structure correction that moves a scope re-keys the readings on it — same body, same `rev`, new identity, one lineage row — and anchors that still lie inside the new box do not move.

> v52 → el=, turn=, block=, region=, transforms in the URI (Part II §6.2), the segment address field. All retired; a v52 turn= is the positional `ord` of a conversation's message scopes.

## 6. The artifact file — seven predicates

| predicate | by | meaning |
|---|---|---|
| `attests` | op | what the bytes are: mime, size, page count, dimensions, encoding, embedded metadata, the member roster of a container — every field one the format defines, nothing a producer asserts. A cache with a pin: `by` names the attester and its version; a line older than the engine's attester for the mime is *stale* (§8) and a sweep writes the superseding line. Never edited. |
| `testifies` | op | on a **testimony artifact** only (§6a): the subject it describes, `corpus://<blake3>`. One line per subject. The subject's own file never names its testimony. |
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
- **Where the bytes give the structure, nothing is stored.** CSV rows, HTML elements under a term's `select`, EPUB spines: `manifests` and `in` derive from the parse, the file stores three lines at `whole`, and a pass writes a line below `whole` only to disagree or to add (a paragraph that is also a `biography`).
- **Chrome is derived, by a declared rule.** Running headers, page numbers, navigation: a `chrome` line names what makes a run chrome — a selector, or repetition (the same masked text and box on at least the declared number and share of pages). The tooling applies the rule and has none of its own. Chrome is listed in the export header and stored nowhere.
- **A scope with no lossless transcription has no reading.** It is addressed, manifested and placed; the bytes are resolved at its `at`; the record stops there. Anything said about what it shows, means or contains is a ledger claim anchored at that `at` with no quote, `mode: inferred`, graded as such. Where such a scope does carry transcribable content (glyphs in a raster, speech in a stream), a pass manifests the sub-scopes that carry it and reads those, under a lossless aspect, checkable against a derivation.
- **A weak engine is a reading's author, never a derivation.** A transcript claim always binds to a reading (Q3 answered).

```
// a CSV: the whole file, three lines
{"at":"whole","predicate":"attests","value":{"mime":"text/csv","bytes":151157,"rows":275,"cols":29,"encoding":"utf-8"},"by":"csv.attest@1"}
{"at":"whole","predicate":"pass","value":{"id":"p1","by":"claude-opus-4-8","verify":"claude-sonnet-5_3","ontology":"b3:b215417f49218591","date":"2026-10-12"}}
{"at":"whole","predicate":"walked","pass":"p1"}
// derived, not stored: whole manifests amazon-order-history (by matches); row=0 manifests header (by the term's shape line); row=N manifests record, in whole ord N; col=3 manifests currency-code …
```

> v52 → the record body (metadata / content / annotations zones; section, segment, structural and placement blocks; atoms; forms; the sweep namespace; faithfulness issues). The whole of Part II §4 is replaced by this table. structure (claim-model rev 2) → manifests + in.

## 6a. Testimony

Where the bytes were found, when, by what and why is not a fact about the bytes and cannot be checked against them. It is **testimony**: a snapshot a producer made, irreplaceable because the moment is gone (rule 1), and never part of the record (rule 8).

- **Testimony is an artifact.** What a producer emits about a capture — a capture sidecar, a serialised v52 origin block, an export's own manifest — is ingested **verbatim** as an artifact of its own: its identity is its BLAKE3, its file holds `attests` and one `testifies` line per subject it describes. It cannot be edited, because its bytes cannot change; a mistaken testimony is answered by a later one and an owner act, never corrected in place.
- **The receipt.** Every ingest writes one testimony of the instance's own — the actor who handed the bytes in, the instant, the name they arrived under, the testimony delivered with them — so every artifact has at least one. A receipt covers the bytes *and* every testimony delivered with them; testimony, the receipt included, is not itself receipted, so the regress stops at one. The receipt's shape is the one testimony shape the tooling prescribes; the foundation carries its term (`receipt`).
- **Origin terms.** An instance says what testimony it accepts in its ontology. An origin term `matches` a producer's shape over the testimony's mime and declares its facets as `select` and `field` lines — the **source** (where the bytes came from: a uri, a sender, an account), the **producer** (what found or made them: the machine, the tool and its version, the session), the **context** (why) — with `required` on what every testimony of that origin must carry. A new origin, or a new required field, is an ontology edit.
- **Enforcement.** Ingest refuses, before a byte is placed, testimony that classifies to no origin term or lacks a field its term requires; the same check runs over the corpus as a lint, so an origin term that tightens lists the testimony it no longer admits. The tooling knows no origin.
- **More testimony, never churn.** The same bytes met again — the same PDF on a second site, a photo first sent on its own and later inside an export — are the same subject; the encounter adds a testimony and touches nothing else. A subject's record never changes because its provenance grew.
- **Inheritance is derived.** A member's provenance is its own testimony together with the provenance of every container whose roster lists it, transitively, and is shown as that chain: the export's uri is the export's, never the photo's. Nothing is copied to the member (§8).
- **Retiring a copy loses nothing.** Once a container resolves the same bytes, a standalone copy may be retired (§0, Part IV); its readings, claims and testimony stay, since identity is the hash. Bytes a container re-encoded are a different subject; "the same image as" is a ledger claim.
- **Testimony is evidence, not knowledge.** It is never graded and holds no claim. A ledger claim about where or when something was published cites the testimony artifact by an ordinary anchor into its bytes, under the testimony's own derivation.
- **Placement.** A testimony is placed in a layer like any artifact and may sit in a more private one than its subject — a public PDF, a private record of the machine that fetched it.

```
// testimony: the producer's sidecar, ingested verbatim — its own subject, two lines
{"at":"whole","predicate":"attests","value":{"mime":"application/yaml","bytes":612,"encoding":"utf-8"},"by":"yaml.attest@1"}
{"at":"whole","predicate":"testifies","value":"corpus://1409369e…","by":"ath.ingest@2"}
// derived, not stored: whole manifests web-capture (an origin term, by matches); its source.uri, producer.tool and context fields
// are read from the bytes by the term's select lines; the subject's provenance lists it beside its receipt
```

> v52 → the origin block on the record (`origin_schema`, origin fields, capture context), origin overlays under schema/origin/, `consumer_ingest` origin lists; draft 1's `captured_from` line. The block becomes a testimony artifact, the overlay an origin term, the lane's allowlist the set of origin terms an extension declares.

## 7. The ontology — terms as subjects

A term is a subject whose expectations are lines in `ontology/<term>.claims.jsonl`. One vocabulary serves the corpus (what a scope may manifest), the ledger (what a concept may be and owes) and the export (how a term renders). Mime roots, document kinds, units, containers, data shapes, web shapes and concept types are all terms; "class" and "type" from direction §3 are terms on the root.

### 7.1 The effective rules of a scope

**Union over its terms' `refines` chains ∪ its ancestors' `convention`s down the `in` chain.** That is the recipe: computed, never chosen. A `biography` with no render rule renders as its `paragraph`; an unknown term renders as `unit`. The most specific term wins where two declare the same expectation.

### 7.2 Term predicates

| | |
|---|---|
| `refines · definition · aligns` | single parent; one-sentence definition (the contract for the word); optional alignment to a spine class (BFO/CCO, DoCO, FaBiO…) for the RDF projection |
| `matches` | classification: mime, plus a header fingerprint, a selector (in the root family's selector language, as `select`), a magic, a path on the artifact's own roster or its own path in a container. The most specific matching term is what `whole` manifests by derivation; a stored `manifests` at `whole` overrides it. Testimony classifies the same way, to an origin term (§6a) |
| `axes · physical · tree · derivation` | mime-root declarations: the intrinsic address axes; which scope is physical (page); whether the tree is *asserted* (pdf: `in`/`ord` are judgments) or *derived* (csv, html, epub: from the parse); the op that yields the quote surface, `<op>@<v>[ <arg>]` (`pdf.words@1`, `html.text@1`, `csv.parse@1 tab`) — the ontology names the op; an op exists only in the engine's registry |
| `reads` | the aspect a scope of this term is read under: text · cells · tex · none. Every aspect is a lossless transcription; there is no descriptive aspect and an extension may not declare one. Resolved along `refines` |
| `field` | a declared field on `manifests`: name, kind (int · enum · datetime · string · col · designator), required. A **designator** field is a verbatim sub-reading with `where`, `pattern` and the derived `address` key it feeds |
| `expects` | child terms a scope of this term normally contains; each missing one is a soft lint, never an error |
| `owes` | world predicates the concept manifested by a scope of this term should have. Unmet is *demand* (§9.5), derived |
| `convention · renders` | reading conventions inherited down the tree (sub/superscripts flattened outside math; footnote marks as `[^n]`; hyphens rejoined); the markdown form per term, fallback along `refines`. A consumer may ignore `renders` entirely |
| `select · shape · spine` | derived structure, the only way a scope below `whole` exists without a pass. `select` maps a selector → term (+ `in`, field source) in the **selector language of the root's family**: CSS for html and xhtml; a JSON pointer pattern for json, ndjson and yaml (`/messages/*`, `*` any key or index; a field's source is a relative pointer); a property name for vcard (`FN`, `EMAIL`; a field's source a parameter); a block kind for markdown (`heading`, `paragraph`, `list-item`, `code`, `table`, `quote`); a line pattern for a decoded text body (`^>` a quote, `^-- $` to the end a signature) over the format's own nodes (a MIME part, the header block). `shape` maps a column → term (+ scheme, pattern, required) and declares which row, if any, is the header — never assumed. `spine` maps a package's order → `in whole, ord` |
| `sentinel · keys · chrome` | values that derive to null ("Not Available"); the key column of a key-value table; what is chrome — selectors whose text is chrome, or a repetition rule (masked text and box recurring on at least *n* pages and a share of them), the tooling applying the rule and having none of its own |
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

Every mime has a root term that refines one of three: **document** (readings can total to a proxy: pdf, html, xhtml, markdown, rfc822, epub members), **image**/**media** — lossy (readings can be drawn, never total: raster images, audio, video), **data** (intrinsically addressable, values given by the parse: csv, json, ndjson, yaml, vcard, archives and other containers). Class is a lookup on the chain, overridable by one stored `manifests` at `whole` (a PDF of photographs manifests `scan-album`). Containers are data; members carry their own terms; nothing is classified twice. A container is any format that holds whole files of its own: an archive, a package, a message's parts, markup's `data:` URIs — every one, wherever it sits; which element carries a `data:` URI is not the format's concern.

### 7.4 The pin

`pass.ontology` is the BLAKE3 of the ontology layer as loaded (sorted term files). A term change makes every pass pinned at the old hash *stale* for the scopes that manifest it or its refinements — derived, listed, re-run; nobody edits a recipe. Extensions add term files and lines; a line at a foundation term's existing identity is refused.

> v52 → mime/, origin/, atom/, form/, context/ schema namespaces; ledger schemas/{type}.yaml and value kinds; the ontology layer §15 with BFO/CCO spine. The spine survives as aligns targets; forms retire into terms; the recipe parameter of the first draft's pass retires into the hash pin.

## 8. Derived, never stored

The following are functions of stored lines and are computed at read time. Writing any of them to a file is a lint failure.

| | |
|---|---|
| `class, root term` | from attests.mime through matches; from the refines chain |
| `manifests, in — where the tree is derived` | from the parse through select / shape / spine; a stored line at the same scope wins |
| `chrome` | the rules `chrome` lines declare: selectors, repetition over pages |
| `provenance` | an artifact's testimony (`testifies` lines naming it) ∪ the provenance of every container whose roster lists it, transitively, as a chain (§6a) |
| `containers of X` | the rosters that list X's BLAKE3 — what Part IV's member index serves |
| `stale attests` | an `attests` line whose attester is older than the engine's for its mime; a sweep supersedes it |
| `testimony admitted` | whether a testimony classifies to an origin term and carries its required fields, against the current ontology |
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
| `reading` | the binding, stamped by verify: a reading `rev`, or `derived:<op>@<v>[ <arg>]` where the parse is the quote surface, or null — *held*. A claim about where or when the bytes were found cites the testimony artifact like any other bytes |

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
{"subject":"parameter-q-l-k-y","predicate":"term","value":"parameter"}
{"subject":"parameter-q-l-k-y","predicate":"manifested_by","value":"corpus://5e6e497d…?page=4&bbox=0.1506,0.4571,0.4382,0.0162"}
{"subject":"parameter-q-l-k-y","predicate":"symbol","value":"Q_{L,k,y}","evidence":[{"anchor":"corpus://5e6e497d…?page=4&bbox=0.1506,0.4571,0.4382,0.0162&cells","quote":"$Q_{L,k,y}$","kind":"authoritative","mode":"stated","reading":"b3:efd915f530aa4d6b"}],"by":"harvest:methodological-tool@a835a5"}
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
| `per term` | reads satisfied · required fields present (on testimony, those its origin term requires) · designators match the derivation under where/pattern · expects met (soft) · owes met (demand) · the term's own lint lines · L7 per aspect · matches agrees with the stored root |
| `per file` | no undeclared field · no derivable value stored · `testifies` only on a testimony, by an op, naming a subject in the chain · an attests field the format defines, nothing a producer asserts · no reads_as under an aspect outside text · cells · tex · one writer per file · sorted · pass refs resolve · ontology hash known |

## Appendix A. Retired from v52

The markdown record and its zones · form / atom / section / segment / placement grammar · the five schema namespaces · touch[] and record status · sweep / coverage · el= / turn= / block= / region= and URI transforms · the classify, reference, concept and relation annotation namespaces · re-stub and the "no formless zone" gate · triage as a form proposer (it survives as a term proposer) · derived views (classifications, issues, uris, timeline…) · the interpretations tree and the physical assertion boundary · the authored status ladder, promote, confidence · verified.touch, the ops map, the sources table, citation_surface: segments · origin tenancy, the visibility floor, the union rule · the origin block, origin overlays and the consumer-ingest origin list (now testimony artifacts and origin terms, §6a) · draft 1's `captured_from` · the whole-record stamp · the structure predicate and the recipe parameter of the first successor drafts.

## Appendix B. Regression set

| predicate | by | meaning |
|---|---|---|
| `pdf · 5e6e497d…` | asserted tree | A generated calculation procedure in the shape of a methodological tool (`testdata/synthetic/gen/procedure.ts`, typst), 8 pages, 2,671 words. 436 pass lines generated from the content model and read back off the render · 131 readings all L7-ok (4 tex) · 0 words outside scope or chrome under `walked` · 18 concepts / 65 claims / 73 entries, 56 confirmed. Exercises: page-spanning containers at union addresses, 2-D math, chrome by repetition, designators at three levels, the TOC, harvest from definitions and key-value parameter tables; the bytes are committed and the leg always runs. |
| `html · 430c0b0f…` | derived tree | The generated twin of the XenForo thread (`gen/thread.ts`): ten posts in XenForo's markup under a v52 banner, 27 KB. 76 scopes by select · 17 concepts / 70 claims / 85 entries, 58 confirmed · two quotes linking their posts · remainder 22 of 6,376 characters. Runs always. |
| `html · 2af1ebd5…` | derived tree | The generated twin of an iMessage conversation page (`gen/conversation-page.ts`): 40 message blocks in imessage-exporter's layout, provenance from a `.capture.yaml` sidecar. 168 scopes by select under `imessage-conversation` · remainder 340 of 5,099 characters. Runs always. |
| `html · 7d848c4f…` | derived tree | The generated twin of a service-manual page capture (`gen/manual-page.ts`): topics as definition lists, notices, numbered steps, specification tables, inlined figures, framework chrome. 75 scopes by select under `service-manual-page` · remainder 0. Runs always. |
| `zip · e82abeed… · 2997cc12… · a55a755c…` | containers | The generated twins of a Messenger, an Instagram and a Threads month slice (`gen/bundles.ts`): inbox threads as `message_1.json` beside their media, activity indexes. 28 · 27 · 23 members; each bundle classifies by its layout and each thread by its name (D-roster). Run always. |
| `zip · fb67bd41… · 7c75a49d… · 23725953… · 2940d770…` | containers | The generated twins of a Google Chat month (`messages.json` + `group_info.json`), an iMessage week (conversation pages), a mail export month (`<id>.eml` + `<id>.metadata.json`) and a photo-library month (HEIC/JPG/MOV originals with sidecar JSON). 5 · 4 · 12 · 13 members; sidecar provenance on every bundle. Run always. |
| `zip · e635ad72… · a9fe6816… · bc55b3a4… · 755432d1… · e0fb7ff7… · 7fafd3bd…` | containers | The generated twins of a retailer data delivery, a ride-hailing export, a health export, a host diagnostics report, a note-vault subtree and a vendor download tree (`gen/bundles2.ts`). 6 · 6 · 6 · 19 · 10 · 9 members; each told by its layout, members by mime (rar, 7z, exe, DXF, raw TIFF enter the sniffer). Run always. |
| `zip · 81f4436b… · f993a31d… · 08ac924b… · 1d7dc1e9… · da7b858a… · 96d4f9ff…` | containers | The generated twins of an agent session (zstd members), a statement year (twelve typst PDFs), a camera card dump, a Takeout slice, a Drive folder (a plain zip: no layout to be told by) and a harvested profile year (told apart from a month slice by a deeper prefix, so it refines it). 5 · 12 · 9 · 10 · 4 · 6 members. Run always. |
| loose media and documents (28 files) | a | `gen/media.ts`: a QuickTime and a 3GPP clip, raw H.264, HEVC and AV1 streams, Opus, AAC and MPEG audio, a TIFF, an AVIF, an icon, an animated GIF; `gen/documents.ts`: a statement, a tax slip, a policy schedule, a banking letter, a chart print-out, a design export (typst), a Word document, an owner statement, a contact card, an SMS backup, a Timeline export, a stylesheet, TypeScript and Python sources, a calendar, a GPX track. Each classifies to its root and lints; the documents fold a sidecar. Run always. |
| `html · 95460875… · d97e60d3… · 9515b279… · 7684234e…` | derived trees | The generated twins of the generic web captures (`gen/pages.ts`): a news article, a product page (schema.org microdata), an order page, a property listing, each under a banner with navigation and footer chrome. 21 · 18 · 15 · 22 scopes under `article-page`, `product-page`, `order-page`, `listing-page`. Run always. |
| odd formats (4 files) | a | `gen/odds.ts`: a ZIM header, an OSM PBF header blob, a FreeCAD document (a zip told by its parts), a gzip. Signature stubs by design. Run always. |
| `rfc822 · 2c694381…` | derived tree | The generated twin of the festival mailing (`gen/mailing.ts`): multipart/mixed over multipart/alternative, a quoted-printable body with six paragraphs and a signature, an HTML alternative, an OOXML workbook, a JPEG and a PDF as members. 1 concept / 4 claims. Runs always. |
| `epub · a04764fb…` | container | The generated twin of the novel (`gen/novel.ts`): calibre's layout, Dublin Core with an ISBN, 52 members, 25 spine items, a chapter of 606 paragraphs and 6 quotes. 1 concept / 5 claims. Runs always. |
| `mbox · 7ccea795…` | container | The generated twin of the mailbox slice (`gen/chat-archive.ts`): mboxrd, 358 messages as xml + html alternatives, two text/plain bodies with stuffed `From ` lines. Runs always. |
| `zip · 43ccf072…` | container | The generated twin of the chat export (`gen/chat-export.ts`): 9 members, the JSON and the SVG under zstd (method 93), seven PNGs stored. Runs always. |
| one exemplar per mime | roots | `testdata/exemplars.yaml`: 86 generated entries over 33 mimes, a twin of every byte shape in the owner's corpus (`testdata/synthetic/gen/COVERAGE.md` is the inventory); each ingests, classifies to its root and lints clean. No private byte is in the set. |

## Appendix C. Open before ratification

- **O10** — assessments: a `note` predicate with no evidence on the owner plane only, or prose stays out of knowledge.
- **O11** — `mode` per entry: the best bound entry decides the rung (proposed); confirm.
- **L7 for tex** — the multiset comparator is specified, not built; Equation (1) is accepted by hand today.
- **Two root classes at once** (a scanned regulation): resolved by the most specific `matches` and one stored override; needs an exemplar.
- **Term governance** — who reviews a proposed term into a foundation. Not a spec question; must exist before the first extension ships one.
- **Testimony withdrawn** (§6a) — a testimony cannot be edited; whether a mistaken one is answered only by a later testimony and an owner act, or an owner act may also hide it from provenance, is open.
- **The receipt's form** — draft 2 makes it a testimony artifact the tooling writes; a line in a layer log is the alternative. Either way it is the one shape the tooling prescribes.
- **Testimony as evidence** — which `kind` a ledger entry anchored into a testimony carries (the producer's own word about a fetch is `direct` for the fetch, `incidental` for what the page said).
- **Testimony placement** — whether an extension's testimony about a foundation artifact is allowed by default (draft 2: yes; the subject is unchanged).
- **Migration** — measured by the instance's census (2026-10-16): 31,587 records (11,451 formed), 3,828 facts, 12,492 claims, 31,901 evidence entries, 335 floor records. Identity carries over (record id = BLAKE3, re-minted identically), so the migration rebuilds from bytes and re-binds quotes; nothing rendered is converted. Each v52 origin block becomes a testimony artifact, serialised verbatim, and each origin overlay an origin term; authored statuses become checks; records become exports; the floor records are placed in a layer. Owner rulings (2026-10-16): the converter rewrites v52 table quotes (`a | b`, raw CSV fragments) to the surface's tab form, and the normaliser stays strict; v52 OCR and transcript readings on lossy scopes seed a staged, unsigned pass by an import actor, binding only once a second pass verifies and signs (§10.1). Blocked until their rulings land in code: 6,929 JSON-anchored entries (D-json), 14,964 embedded members (D-embeds), 709 vCard and 82 markdown entries.

Borrowed vocabulary, by design: Web Annotation (anchor + quote with prefix/suffix) · PROV (pass, by, verify, lineage) · nanopublications (claim + provenance as named graphs) · Akoma Ntoso (designated addressing) · Datomic (fact log + transaction entity = line + pass). What no precedent combines — intrinsic addresses, structure as verified judgment, readings as revisions bound per evidence entry, status and demand derived, the ontology as the recipe, one-way layering — is the system.

## Appendix D. Reference-implementation rulings

The draft leaves gaps that code cannot leave open. Each ruling below is what the reference implementation (`ath/`) does, where the review (`spec/successor-review.md`) raised it, and the test that pins it. A ruling is a proposal until ratification; the owner may overturn any of them, and the test then changes with the text. The last column names the test file that pins it (several where several do); a ruling marked untested or not yet run is in force in the code but not yet guarded. A ruling marked **drafted (draft 2)** is the contract the code must meet and does not yet; its last column says what the code does today and which test will change.

| id | question | ruling | pinned by |
|---|---|---|---|
| D-F1 | Who attests a ledger line? (§4.1 names `by` for ops and `pass` for a pass line "in the same file"; §10.1 defines passes over artifacts only.) | A ledger pass is a line `{"subject": <slug>, "predicate": "pass", "value": {id, by, verify, ontology, date}}` in the concept file. Authored claims carry `pass`; harvests carry `by: harvest:<term>@<pin>`. A ledger line with neither, or with a `pass` that does not resolve in its file, is refused at write. | `ath/test/lint.test.ts` |
| D-F2 | Pages carry no `in`, yet cover labels and the TOC hang off a page and the export emits them. | Pages stay physical. `cover-page` and `table-of-contents` refine `unit`, carry `in whole, ord N`, and own the scopes on their page. G2 requires every non-page scope to be reachable from `whole` by `in`. | ath/test/lint.test.ts (G2 reachability); ath/test/corpus.pass.test.ts (cover-page in whole) |
| D-F3 | The binding grammar (§9.2) is `rev | derived:<op>@<v> | null`; the data binds attributes and op-line values. | `reading` is one of `b3:<16 hex>`, `derived:<op>@<v>[ <arg>]` (the argument names an attribute or path), `line:<predicate>[ <field>]` (a value read off an op line: `manifests`, `attests`), or `null` (held). G4 checks the quote against the surface each form names. The same `<op>@<v>[ <arg>]` is what a term's `derivation` line carries (D-derivation). Draft 2: `line:captured_from` retires with the line; a claim about provenance cites the testimony artifact under its derivation. | ath/test/ledger.test.ts (line:manifests; line:captured_from until draft 2 lands); ath/test/corpus.container.test.ts (the route); the refusal of a malformed binding is a zod refinement in ath/src/engine/model/evidence.ts, untested |
| D-F4 | `walked` on a derived tree is vacuous when chrome is the complement of the selection. | `walked` is written only where the root term's `tree` is `asserted`. On a derived tree the export header carries `remainder <chars outside units and declared chrome> / <text chars>`, and G3 checks against declared `chrome` selectors only. | ath/test/lint.test.ts (walked on a derived tree); ath/test/export.test.ts (the remainder in the header) |
| D-F5 | The ontology pin recipe is unstated and the regression pins do not reproduce. | Pin = BLAKE3 over the ontology layer serialised as: term files sorted by term name, lines sorted by identity key, each line compact JSON with non-ASCII unescaped, LF-terminated; written `b3:` + first 16 hex. The harvest pin is the first 6 hex. Every pin in the regression set is rewritten under this recipe. | ath/test/ontology.test.ts (pin determinism, per-term pins); ath/test/corpus.pass.test.ts (staleness) |
| D-F6 | Source grade differs across the set (PDF/CSV `authoritative`, HTML `direct`) and decides public visibility. | Harvest writes `authoritative` when the concept is `manifested_by` a scope of the cited artifact and the predicate is one its term `owes`; otherwise `direct`. An authored entry keeps what its pass wrote. | `ath/test/ledger.test.ts` |
| D-F7 | Harvest anchors at the whole post and elides quotes. | A selector a `concept` map names must also be a `select` line (ontology lint). A field-derived value binds `line:manifests <field>` at the scope's bare `at`. A quote never carries `…`; a long value is quoted by `quote` plus `suffix`. | ath/test/ontology.test.ts (selectors in maps refused); ath/test/ledger.test.ts (line:manifests for fields); the `…` refusal is a zod refinement in ath/src/engine/model/evidence.ts, untested |
| D-F8 | Design-page ids (`scope:`) leak into evidence entries. | `scope` is an undeclared field; the per-file lint refuses it; regression input strips it. | `ath/test/lint.test.ts` |
| D-D1 | A `reads_as` with `aspect: none`. | Refused. A term's `reads: none` is the whole statement; no line sits on the scope. | `ath/test/model.line.test.ts` |
| D-D2 | `page=N` lines store `number: N`. | A field may be declared `derived: true` on its term; a derived field is never stored and the per-file lint reads the declaration. `page.number` is declared derived. | ath/test/lint.test.ts; ath/test/ontology.test.ts |
| D-D3 | A concept manifested by several scopes. | `manifested_by` is repeatable, one line per manifesting scope; evidence accrues on the one claim it supports. | observed on the regression HTML (member-davisb1983, five manifested_by lines); not yet asserted |
| D-D4 | A `stated` entry whose value is not its quote (`Example Forum` from `Slip/berth \| Example Forum`). | `html.title@1` stays an op; the claim is `mode: inferred` with `reasoning`. G4 refuses `stated` where the value is not a substring of the quote after normalisation. | ath/test/lint.test.ts (G4: a stated value outside its quote) |
| D-D5 | No lineage in the regenerated set. | Every identity whose content changes gets a lineage row, `by: regenerate@<version>`. | `ath/test/corpus.pass.test.ts` |
| D-D6 | "Data has no readings" versus `record reads cells`. | Read as "no *stored* readings". A derived reading lives in the scope table and binds as `derived:<op>@<v>`. | `text only` |
| D-rev | The revision recipe. | `rev` = `b3:` + first 16 hex of BLAKE3 over the body: a string as UTF-8, an array as compact JSON (`JSON.stringify`, non-ASCII unescaped). Verified against the 131 readings of the generated procedure. | ath/test/corpus.pass.test.ts (stamped; a wrong rev refused); ath/test/regression.test.ts (the calculation procedure: 436 lines append, every rev recomputed) |
| D-staging | §10.1 says there is no draft state; a pass needs somewhere to accumulate lines before both have signed. | Pass lines stage in `<layer>/.ath/passes/<blake3>/<id>.jsonl`, outside the trees, until `pass sign` merges them. Nothing under `corpus/` exists unsigned. | `ath/test/corpus.pass.test.ts` |
| D-bbox | Box precision and containment. | Canonical boxes carry at most 4 decimals; `pdf.words@1` rounds to 4; containment uses ±0.002 slack per edge. | ath/test/model.address.test.ts; ath/test/ops.pdf.test.ts |
| D-csv | Row and column numbering. | `row=N` is the physical row, 0-based; `col` is 0-based. Draft 2: which row is the header is declared by `shape` (`{header: 0}`, or none), never assumed; the header row sits `in whole, ord 0`, every other row in order; `?col=<name>` resolves through the declared header; a BOM is recorded in `attests` and stripped from the surface; sentinels derive to null only in harvest, never in the surface. | **drafted (draft 2), not implemented** for the declared header; the code takes row 0 as the header when the root `expects` header (`ath/test/ops.test.ts`; `ath/test/corpus.derive.test.ts`) |
| D-html | The `html.text@1` surface and the byte map. | Drop `head`, `script`, `style`, `template`, `noscript`, `svg`; block elements and `<br>` end a line; `td`/`th` separate by tab; whitespace runs collapse to one space; lines trimmed; blank runs collapsed. A scope's span is its start tag's first byte to its end tag's last byte, half-open; an implied end is flagged. The byte map is a prefix sum of UTF-8 lengths per UTF-16 code unit of the decoded file. | ath/test/ops.test.ts (byte map, spans); ath/test/regression.test.ts (the forum thread: 31 bodies byte-exact against the generator's model) |
| D-chrome | Chrome by repetition on an asserted tree. | Draft 2: the rule is the ontology's. `chrome` on `document` declares `{repeats: {pages: 3, share: 0.4, box: 3}, mask: "digits"}`; the tooling masks, rounds and counts as declared and has no default. Roles (`page-number` for a masked `# of #`, `running-header`/`running-footer` by position) are `chrome` values too. Chrome words are excluded from G3. | **drafted (draft 2), not implemented**; the code applies max(3, 0.4·pages) itself (`ath/src/engine/ops/pdf/words.ts` detectChrome; `ath/test/ops.pdf.test.ts`) |
| D-L7 | One normaliser; the `tex` comparator. | G4 and L7 share one normaliser: NFKC, quote and dash folding, NBSP → space, whitespace collapse, then a second pass with whitespace and hyphens removed. Text compares by token LCS; cells per cell as a contiguous run in the row's column-aware words; tex by the multiset of letters, digits and operators after TeX layout is stripped and `\sum \times \rho` map to their symbols. Divergence is listed; an `inspected` line by rev accepts it. | `ath/test/lint.l7.test.ts` |
| D-status | Derived status. | `confirmed` ⇔ a bound `authoritative` entry, or two bound `direct` entries from distinct artifacts, and no standing challenge; `disputed` ⇔ a challenge stands; `conflicting` ⇔ a bound sibling disagrees on a predicate the term declares `functional`; else the mode of the best bound entry; else `unsupported`; `refuted` ⇔ unsupported with an upheld challenge. | `ath/test/ledger.test.ts` |
| D-ocr | Rule 8 on a raster. | A raster root declares no `derivation`. `image.words@1` (tesseract word boxes) is a proposal op: a pass accepts its boxes into `manifests` + `reads_as` or does not. L7 lists every image reading for inspection. The engine version rides in the pass note. | `ath/test/ops.image.test.ts` |
| D-union | Union address order. | Members of `a;b;c` sort by page, then y, then x; the resolver canonicalises before identity. | `ath/test/model.address.test.ts` |
| D-select | Selector engine. | CSS selectors are evaluated by `css-select` over the parse5 tree; the ontology may use any selector it supports. Owner-confirmable. | ath/test/ops.test.ts; ath/test/corpus.derive.test.ts |
| D-pdf | PDF engine. | `pdf.words@1` is pdfium (the same engine as v52's pypdfium2) through `@embedpdf/pdfium`; `pdftotext -bbox-layout` may run as a cross-check op and is never bound to. Owner-confirmable. | `ath/test/ops.pdf.test.ts` |
| D-spike-pdfium | Can pdfium run inside a compiled `ath` binary? | Yes. `@embedpdf/pdfium` 2.15.1 initialises from `pdfium.wasm` embedded with `with { type: "file" }`; `FPDFText_*` char boxes agree with pypdfium2's on the fixture PDFs; the compiled binary runs from any directory. No fallback needed. | `ath/test/ops.pdf.test.ts` |
| D-spike-parse5 | Do parse5 source offsets survive the htmlparser2 tree adapter, and map to bytes? | Yes. `sourceCodeLocation` is present on adapter nodes; a prefix-sum table of UTF-8 lengths per UTF-16 code unit maps start/end offsets to byte ranges exactly, astral characters included; `css-select` runs over the same tree. | `ath/test/ops.test.ts` |
| D-F7b | Which names may a `concept` map use? (The regression ontology named CSS selectors in maps.) | A concept map names scopes by **term**: `author`; a field as `term.field` (`post.position`) or `predicate.field` for an op line (`attests.mime`; draft 2: provenance is read off a testimony, never an op line on the subject); an attribute of the scope's own element as `@attr` (`@data-site`); an edge as `term → concept-term`; a cell by index for definition lists; `*` for every row. A selector is never a map value or a key; the ontology lint refuses one. The regression ontology gains `member-title`, `author-link` and `quote` terms with `select` lines, and `select` lines may name an `attr` that fills a `field`. | `ath/test/ontology.test.ts` |
| D-concept-key | A `concept` line without a `key`. | Allowed: the concept is the one the enclosing document manifests (`metadata`, `revision-history` augment the document's own concept). | ath/test/ontology.test.ts (the regression ontology lints clean with keyless concepts) |
| D-D7 | The regression ontology's `text` term declared `reads` as a sentence. | A `reads` value is exactly one of `text`, `cells`, `tex`, `none`; the lint refuses prose. The data is corrected to `text`. | `ath/test/ontology.test.ts` |
| D-identity-ontology | What does an ontology line collide on? | A single-valued predicate collides on `(subject, predicate)`; a repeatable one (`field`, `select`, `shape`, `convention`, `concept`, `lint`, `matches`) on `(subject, predicate, name)` where the name is the value's `name`, `col`, `selector` or `term`, else the whole value. An extension writing a foundation term's existing identity is refused. | ath/test/model.line.test.ts; ath/test/ontology.test.ts |
| D-ingest-op | What op attests at ingest, and what writes provenance? | Draft 2: ingest writes, per artifact, `attests` (`by` the mime's attester and version), the receipt (§6a) and, for every testimony delivered with the bytes, that testimony as an artifact with a `testifies` line naming the subject, `by: ath.ingest@2`. The tooling reads no provenance out of the bytes: a v52 capture banner's `corpus-capture-*` meta tags are the bytes' own text, which an origin term may select like any other. The same bytes again add testimony only and leave `attests` alone; the same testimony again is a no-op. | **drafted (draft 2), not implemented**; the code writes `captured_from` from sidecar, flags and banner (`ath/test/corpus.ingest.test.ts`) |
| D-shadow-same | An extension ingests bytes its foundation already holds. | Same identity, same content is a no-op and writes nothing in the extension; different content is refused. Draft 2: the encounter still writes its receipt and any testimony delivered with it in the extension, and nothing on the subject. | `ath/test/corpus.ingest.test.ts` |
| D-col | A column of a table as a scope. | `col=M` is an address axis of tabular roots beside `row=N[&col=M]`: a column scope (the shape's term, `name` from the header) contains its cells. Columns carry no `in` (an axis, like a page) and are not G2 findings. | ath/test/model.address.test.ts; ath/test/corpus.derive.test.ts |
| D-csv (amended) | Ord on a tabular tree. | `row=0` (the header) is `in whole, ord 0`; `row=N` is `in whole, ord N`. | `ath/test/corpus.derive.test.ts` |
| D-mime-root | An expression root (`amazon-order-history`, `xenforo-thread`) is not on the mime root's chain. | The artifact's effective chain is the expression root's refines chain followed by the mime root's (`csv`, `html`, `pdf`: the most specific term whose `matches` is the mime alone). Axes, tree, derivation and physical come from whichever declares them first; a scope's own terms name a derivation before the root chain does (D-derivation). | `ath/test/corpus.derive.test.ts` |
| D-key-holders | How many concepts does a `concept` line mint? | One per holder of its key under each scope of the owning term: every scope of the key's term (`post.id` → every post), every record row for a column key (`Order ID`), the owner scope itself for `@attr` and op-line keys. Claims resolve within the holder, then within its parent (a member's `member-title` is the post's child, not the author-link's). | `ath/test/ledger.test.ts` |
| D-edge-cite | What evidence does an edge to another concept carry? | When the edge's left side is a term whose scopes are containers (`post → forum-post`), one edge per scope, cited by the target concept's key (`line:manifests id`); a value edge (`Website → marketplace`) is cited by the cell or text that names it. `qualifiers.as` keeps the value the bytes printed. | `ath/test/ledger.test.ts` |
| D-slug | How a harvested concept is named. | `slug` on the concept line is a template over `{term}`, `{key}` and `{1}` (the first group of `extract` applied to the key), default `{term}-{key}`; non-alphanumerics become `-`; lowercase unless `case: keep` (ASINs). | `ath/test/ledger.test.ts` |
| D-designator-where | Where a designator's text comes from on a derived tree. | `where` may name a descendant term (`post.position` from the `post-number` scope); the pattern runs over that scope's text. | `ath/test/corpus.derive.test.ts` |
| D-expects | What satisfies `expects`. | A scope manifesting the expected term or any term that refines it. The page expectation moves from `document` to `pdf`. | `ath/test/lint.test.ts` |
| D-pass-line | A `pass` line carries no attestation of its own. | It is the attestation; the per-file lint exempts it. | `ath/test/lint.test.ts` |
| D-sign | What `pass sign` lints, and against what. | The stored lines with the pass's staged lines laid over by identity (plus `walked` when asked), in canonical order; G1–G3, per-file and per-term lints; any blocking finding refuses the signature and leaves the staging untouched. A staged line at an existing identity with different content is a correction with a lineage row `by: pass:<id>`. | `ath/test/corpus.pass.test.ts` |
| D-G3-severity | When does an uncovered word block? | On an asserted tree G3 lists the words outside every scope and chrome; it blocks only under `walked` (the pass claims completeness). A `walked` on a derived tree is itself a finding (D-F4). | `ath/test/corpus.pass.test.ts` |
| D-L7-text | What the text comparator absorbs. | Designator fields stripped from the derivation's head or tail; footnote marks `[^n]` removed from the reading and the superscript digit unglued from its word in the derivation; bullets dropped; then a token comparison, then the squashed comparison. Punctuation is content: a dropped period diverges. | `ath/test/lint.l7.test.ts` |
| D-L7-tex | The tex comparator. | Control words map to their symbols (`\sum` → ∑, `\times` → ×, `\rho` → ρ), braces and script marks drop, the `Equation (n)` label drops from the derivation; the multisets of letters, digits and operators must agree; the map covers the Greek alphabet. The four equations of the generated procedure pass. | `ath/test/lint.l7.test.ts` |
| D-inspect | The owner's acceptance. | `inspect accept` is admin-tier (typed confirmation at a terminal, never under `--json`), writes `{at, inspected, {rev, diverges: accepted, why}, by: owner, date}` to `<blake3>.owner.jsonl`, and binds to the reading revision: a re-read lapses it. `inspect revoke` removes it with a lineage row. | `ath/test/corpus.pass.test.ts` |
| D-pass-id | Pass ids. | `p<n>`, the lowest free number after every signed and open pass on the artifact; the author and verifier must differ. | `ath/test/corpus.pass.test.ts` |
| D-ocr (applied) | The raster exemplar. | `lossy` and `image` enter the ontology (`image` reads none, axes `bbox`, tree asserted, no derivation); `jpeg`/`png` match their mimes. `ath image words` runs tesseract (`--psm 6 tsv`) and prints proposal lines — one `label` scope per OCR line, placed in whole in reading order, with a text reading — that a pass stages like any other lines. L7 lists each as `no-derivation`. The synthetic sign (`testdata/synthetic/sign.jpg`) is the exemplar. | `ath/test/ops.image.test.ts` |
| D-container-route | A claim cited through a container. | `corpus://<zip>?path=<p>[;<at>]` canonicalises at bind time to the member subject the roster names at that path, with the remaining address applied there; a path the roster lacks is flagged. Draft 2: the route is found wherever it stands in the address (`bytes=…;path=…` canonicalises with `path` last and still routes), in `resolve`, `tree` and `inspect` as in bind. `zip` and `container` enter the ontology (`container` refines `data`, axes `path`, tree derived from the roster). | `ath/test/corpus.container.test.ts`; the anywhere-in-the-address route **drafted (draft 2), not implemented** |
| D-zip-reader | How zip members are read. | A reader of the engine's own over the central directory (store, deflate, zstd — what Discord's exporter writes); zip64 is refused loudly. No library pins the op. | ath/test/ops.test.ts (deflate); the zstd archive: ath/test/regression.test.ts (the chat export) |
| D-physical-addressable | Which addresses exist without a line. | A row the parse holds (tabular) and a page the document has (PDF) are scopes an anchor may name even when nothing manifests there; a cell within such a row likewise. | `ath/test/corpus.container.test.ts` |
| D-rfc822 | A message's axis and derivation (§5.2 puts rfc822 on `bytes=`). | A parser of the engine's own (RFC 5322/2045) gives every part a raw span in the file; `eml.text@1` is the span transfer-decoded (7bit · 8bit · binary · quoted-printable · base64) and charset-decoded, CRLF folded to LF, trailing whitespace trimmed. `attests` carries the identifying headers (`message_id`, `subject`, `from`, `to`, `cc`, `date`, `date_iso`; a raw header line is read as UTF-8 when it is valid UTF-8 (RFC 6532), latin1 otherwise, then RFC 2047 words decode), the part table with spans, and the roster. A leaf that is not a text/plain body — the HTML alternative, an attachment, a nested message — is a member of its own routed `path=<part path>` (`1.2`, `3`); the filename rides on the roster row and is what the member is sniffed by. | `ath/test/ops.mail.test.ts`; `ath/test/regression.test.ts` (rfc822 leg) |
| D-rfc822-parts | Units inside a body whose bytes are encoded. | Draft 2: `eml.text@1` exposes the format's nodes — the header block and every part with its raw span — and the ontology names them: `select` on `rfc822` maps `header` → `message-header`, `part[type=text/plain]` → `message-body` (fields `part`, `encoding`, `charset`), and inside a decoded body line patterns map blocks: `^$`-delimited runs → `paragraph`, every line `^>` → `quote`, from `^-- $` to the end → `signature`. Blocks derive only under a line-local encoding (quoted-printable and the identities); a base64 body is one scope. A block equal to the whole body is the body. Finer units a pass asserts are raw spans too. | **drafted (draft 2), not implemented** for the ontology naming; the code mints these terms itself (`ath/src/engine/ops/mail/text.ts`; `ath/test/ops.mail.test.ts`) |
| D-mbox | Members of a mailbox. | `From ` at the file start or after a blank line delimits (mboxrd); a member's bytes are un-stuffed (one `>` off every `^>+From ` line) and hashed so; the route is `path=<1-based ordinal>`; the roster row carries the Message-ID. A member is sniffed as a message by its header lines, before the HTML check, since a message may mention `<html` in its first kilobyte. | `ath/test/ops.mail.test.ts`; `ath/test/regression.test.ts` (mbox leg) |
| D-epub | The package and its chapters (Appendix B's mock, made real). | `attests` carries the OPF's Dublin Core (`title`, `creator`, `language`, `identifier`, `isbn`, `date`, `publisher`), the `opf` path and the `spine` as member paths in reading order; the derived tree is one `spine-item` route scope per spine item, in whole, ord by the spine. A chapter is a member classified by its package: a `matches` line may name `container: <root term>` (a fourth probe beside mime, header, selector), so `epub-chapter` refines `html` and selects headings, paragraphs and quotes under `html.text@1`. The publication harvests from the attestation (`attests.<field>` → `line:attests <field>`). XML is read with htmlparser2 in xmlMode, never as HTML. | `ath/test/ops.epub.test.ts`; `ath/test/regression.test.ts` (epub leg) |
| D-sniff | What names a mime. | Magic first: a zip is an epub only by its OCF `mimetype` member and OOXML by its parts (`xl/`, `word/`, `ppt/`), never by extension; ISOBMFF by `ftyp` brand (heic/avif/M4A/qt/3gp, else mp4); a message by its header lines; mbox by `From ` + a header line; vCard, iCalendar, STEP (`ISO-10303-21;`) by their first line; JSON by parsing (one object, or one per line); then the extension (md, tsv, js, …); then text vs binary. Every mime an exemplar carries has a root term; `application/octet-stream` manifests nothing. | `ath/test/ops.test.ts` (sniff); `ath/test/regression.test.ts` (one exemplar per mime) |
| D-members-depth | How deep members mint. | A container's members become subjects; a member's own members do not (a message's HTML alternative inside a mailbox, a zip in a zip stay on their member's roster) until the member is ingested on its own. Recorded, not ruled. | `ath/test/regression.test.ts` (mbox leg: the alternatives are on the rosters, not subjects) |
| D-roots | Mime roots with no tree yet. | `markdown`, `plain-text`, `javascript`, `json`, `ndjson`, `vcard`, `step`, `xml`, `xlsx`, `docx`, `media` (`mp4`, `quicktime`, `m4a`), `heic`, `gif`, `webp`, `svg` enter the regression ontology as roots so every exemplar classifies and lints (draft 2: `json`, `ndjson`, `vcard` and `markdown` leave this list as D-json, D-vcard and D-markdown land); none declares a derivation (markdown blocks, JSON paths, vCard properties and media spans are later rulings); each lands as one op module plus one `derivation` line (D-derivation). The second sweep (2026-10-16) adds `tiff`, `raw-image` (ARW), `dng`, `avif`, `calendar`, `dxf`, `threegpp`, and under a `binary` unit `octet-stream`, `rar`, `seven-zip`, `executable`, `elf`, `gzip`; the sniffer learns the TIFF, RAR, 7z, MZ and ELF magics and the DXF header. The third sweep adds `opus`, `ogg`, `mpeg-audio`, `aac`, `h264`, `hevc`, `av1`, `icon`, `css`, `typescript`, `python`, `fcstd`; the sniffer learns Ogg (Opus by its head), ID3 and MPEG audio frames, ADTS, IVF, Annex B elementary streams (H.264 by NAL type 1–23, HEVC by a VPS/SPS/PPS/SEI header with its temporal id), the ICO header ahead of the Annex B check, and a FreeCAD document by its zip parts; the fourth adds `zim`, `osm-pbf` and the four page roots (`article-page`, `product-page`, `order-page`, `listing-page`) with their units (`comment`, `price`, `sku`, `review`, `order-fact`, `order-line`, `tracking-event`, `listing-fact`), and the ZIM and OSM PBF signatures. `tsv` refines `csv` and parses with the tab; `csv` itself expects header, record and column. | `ath/test/regression.test.ts` (one exemplar per mime) |
| D-sidecar | How a producer hands provenance to ingest (the capture split: ita acquires, the layer ingests). | Draft 2: the producer's file — `<file>.capture.yaml` beside the bytes, or `--testimony <file>` — is a testimony artifact, ingested verbatim; nothing is folded, renamed or dropped, so a producer's shape may change as long as an origin term admits it. Ingest refuses, before a byte is placed, a testimony that classifies to no origin term or lacks a required field (§6a). The bytes and the testimony are copied, never unlinked. Identity is the BLAKE3 of the bytes and nothing else; a URI lookup is a derived index over the testimony's selected `source.uri` and aliases, exact strings. | **drafted (draft 2), not implemented**; the code folds the sidecar into `captured_from` and drops keys it does not know, `origin_schema` among them (`ath/test/corpus.ingest.test.ts`) |
| D-captures | The same bytes ingested from two places (an attachment also saved on its own; a member two containers share). | Draft 2: dissolved. A second encounter adds a testimony (or, for a member, nothing: the new container's roster is the encounter); provenance through containers is derived (D-provenance). Nothing on the subject changes, so there is no identity to collide on. | **drafted (draft 2), not implemented**; the code appends a `captured_from` line keyed on `container#path`, uri or origin, and a second uri-less capture with different fields is refused (`ath/test/corpus.ingest.test.ts`) |
| D-roster | How a bundle and its members are told apart from any other zip and JSON. | `matches` gains two probes: `member` holds when some path on the artifact's own roster starts with the value (`*x`: ends with x) — a bundle is told by its layout (`your_facebook_activity/`, `Groups/`, `*.metadata.json`); `path` holds against the artifact's own path inside its container — a member is told by its name (`*/message_1.json`). Either value is a prefix, or a glob where `*` stands for any run of characters (`*.metadata.json`, `*-diagnostics-*` + `/smart/`). A container is classified with its roster when a member asks for its root. Draft 2: a member held by several containers (the same GIF at five spans, a photo inside two exports) is probed against every (container, path) pair the rosters give; a `container`/`path` condition holds if any pair satisfies it, and the most specific term wins as for any `matches`. The roster probe needs a mime beside it, as every `matches` does; several `matches` lines on one term still conjoin, so alternatives are sibling terms under a common parent (`messenger-conversation`, `instagram-conversation`, `threads-conversation` under `meta-conversation`). | `ath/test/regression.test.ts` (export bundles) |
| D-attr-pattern | A selected attribute carries the value in another form than the key it must match (`#post-42` against `post.id` = `post-42`). | A field filled from an attribute passes through the pattern the term declares for that field, when it declares one: the first capture (else the whole match) is the value, an attribute that does not match keeps its raw value. A concept map then reaches it as `term.field → concept` and the edge resolves by key. Harvest asks a concept's parent scope for a reference its own scope lacks (a sibling carries it), but never `whole`: a term found anywhere in the artifact is not this concept's evidence. | `ath/test/regression.test.ts` (the forum thread: `quote-source.target`, `quotes`) |
| D-twin | The regression set must not depend on private bytes. | Every regression artifact is a generated **twin** of a shape in the owner's corpus, with fictional content, committed under `testdata/synthetic/` with the script that generates it under `testdata/synthetic/gen/`; no value in a generator is copied from a real file (`gen/README.md`). The committed bytes pin the blake3; a re-render is a new artifact. The private bytes and their legs are gone from the set (2026-10-16); every shape they carried has a twin (`gen/plain.ts`, `thread.ts`, `mailing.ts`, `novel.ts`, `chat-archive.ts`, `chat-export.ts`, `procedure.ts`); what a twin exposed is recorded here: XenForo carries a quote's source on the attribution link inside the blockquote, never on the blockquote; the regression ontology now selects `blockquote.bbCodeBlock--quote` as the quote and its `a.bbCodeBlock-sourceJump` as a `quote-source` whose `target` is the link's `data-content-selector`, and `quotes` is harvested (D-attr-pattern). The asserted-tree PDF (`procedure.pdf`, the only PDF the suite needs) comes with its pass file, generated from the same content model by locating every block's words in the rendered pages (the running header and footer, chrome by repetition, are excluded from the search). `pdf.words@1` bands lines on the glyph's baseline origin (`FPDFText_GetCharOrigin`), not the box bottom: under a font with tight glyph boxes a descender opened a new band mid-line; the word set is unchanged. Two render templates the twin's export exposed are corrected in the regression ontology: `equation` renders `\\tag*{{label}}` (the inner braces are the placeholder), and `heading` renders `{level+1} …`, where a scope with no `level` (a selected title) is level 0. | `ath/test/regression.test.ts` (the calculation procedure); `ath/test/export.test.ts` |
| D-designated | `sec=5&para=6`: what the second key narrows to; what a captured designator answers to. | A later key narrows to the earlier key's scopes' tree descendants and whatever their boxes contain (a one-line heading contains nothing geometrically; its paragraphs are placed in it). A designator field whose declared pattern has a capture answers to the capture as well as the whole value: `label: Equation (2)` under `^Equation \((\d+)\)$` answers `eq=2`; `num: "3."` answers `sec=3`. | `ath/test/regression.test.ts` (the calculation procedure: `sec=3&para=8`, `sec=5.2&eq=2`, `sec=6.2&table=3`) |
| D-harvest-keys | How a concept map reads a key-value table, a named cell and a `Key: value` text block. | A reference that is one of the term's `keys` reads the row at or under the scope whose first cell is that key and yields its second cell (`-` and empty yield nothing); a reference that is a name on the term's `cells` line reads that index of the first cells reading at or under the scope; a reference that matches the leading `Key` of a line in a text reading yields the rest of the line. Entries bind at the row (`&cells`) or the block (`&text`) by the reading's rev. `*` stays a later ruling. A cell written as TeX (`$\Delta T_{i,y}$`) is compared by L7 through the same symbol map as a tex reading; the map covers the Greek alphabet. | `ath/test/regression.test.ts` (the calculation procedure: 12 parameters by symbol, 5 monitored parameters by `Data / parameter:`, the tool's metadata) |
| D-derivation | Who chooses the op that yields a scope's surface, and where an op exists. | **The ontology names the op; the registry is the only place an op exists; nothing is chosen by code.** A term's `derivation` line is `<op>@<v>[ <arg>]` — D-F3's `derived:` binding form without the prefix, one grammar for what a term names and what verify stamps; prose belongs on `definition`. A scope resolves under the first `derivation` along its own terms' refines chains, else along the root chain (D-mime-root order): a `timestamp` under `html.attr@1 datetime` yields the attribute while its siblings yield `html.text@1`, with no code touched. The arg rides to the op: `html.attr@1 <name>` names the attribute, `csv.parse@1 tab` the delimiter (`tsv` is that one line). A derived reading's `rev` is `derived:` + the line's value, never a constant in code. The engine registers ops by name (`csv.parse@1`, `eml.text@1`, `html.attr@1`, `html.text@1`, `html.title@1`, `pdf.words@1`); the bytes are parsed once per family (`html`, `csv`, `pdf`, `mail`) under the op the mime root names, and the family's form is what the classification probes read. A term naming an op the engine lacks, a value that does not parse, or an arg the op refuses (each op says what it takes: `csv.parse@1` a delimiter, `html.attr@1` a name, the rest none) is `O10-derivation` in `ontology lint` and CONFIG (78) wherever the artifact loads; `lint --all` records it as one blocking `T-derivation` on the subject and goes on; a binding naming an unknown op or arg is flagged, not fatal. Without resident bytes there is no surface (NOT_FOUND), as for the bytes themselves. `xhtml` (`application/xhtml+xml`) refines `html` as its own root, since `matches` lines conjoin. A root that declares no derivation has no surface, quietly (D-roots). `whole` on markup resolves to the document text under `html.text@1`; the title is reached by name (`html.title@1`). Attesters stay keyed by mime (byte facts at ingest, before classification) and sniffing stays code (D-sniff); the ontology takes over at the mime. `monetary-amount` and `datetime` declare no derivation until a value op is written. The unit of extension is one op module with its tests; everything above it is an ontology edit. Draft 2: families gain `json`, `vcard`, `markdown` and `yaml` (D-json, D-vcard, D-markdown), each op also carrying its family's selector language (D-select-family). | `ath/test/corpus.derivation.test.ts`; `ath/test/corpus.derive.test.ts` (the timestamp); `ath/test/regression.test.ts` (the forum thread: 31 bodies, 21 under `html.text@1`, 10 under `html.attr@1 datetime`) |
| D-planes | What each plane serves (spec §12, applied). | `public`: the foundation layers and claims whose derived status is `confirmed`; `audience:<name>`: the foundation plus every extension whose `tier` the audience's grant (`audiences:` in athenaeum.yaml) names, same status filter; `owner`: the whole chain, every status, the owner files, demand and findings. The server re-reads the layer per request and holds no state. | `ath/test/serve.test.ts` |
| D-testimony | What testimony is and what the tooling prescribes of it (§6a). | A testimony is an artifact ingested verbatim; its file holds `attests` and one `testifies` line per subject (`corpus://<blake3>`), `by: ath.ingest@2`; nothing else about it is the tooling's. It is admitted only if it classifies to an origin term and carries that term's required fields — at ingest (refused before a byte is placed) and as a lint over the corpus. An origin term is an ordinary term over the testimony's mime (yaml, json) whose `select` lines read its facets (source, producer, context). | **drafted (draft 2), not implemented** |
| D-receipt | What the instance testifies of its own. | Every ingest writes a receipt: a JSON testimony `{actor, received, name, testimony: [<blake3>…]}` — who handed the bytes in, the instant, the name they arrived under, the testimony delivered with them — classified by the foundation term `receipt`. Every artifact therefore has at least one testimony. The receipt is the provenance of the testimony it lists, and no testimony is itself receipted. | **drafted (draft 2), not implemented** |
| D-provenance | A member's provenance, and an artifact's containers. | Derived at read time: an artifact's provenance is the testimony whose `testifies` names it ∪, for every container whose roster lists its BLAKE3, that container's provenance at that path, transitively, shown as a chain (receipt → export testimony → `path` → member). The rosters are the containment index Part IV's member route reads. Nothing is copied to a member. | **drafted (draft 2), not implemented** |
| D-attests-pin | How `attests` stays current. | `attests.by` is the mime's attester and its version (`html.attest@2`); the engine's registry names the current one per mime. A line with an older attester is *stale* (derived, listed by `lint`); `ath reattest --stale` writes superseding lines and nothing else. An attests field is one the format defines; a field a producer asserts is refused. | **drafted (draft 2), not implemented** |
| D-select-family | What a `select` selector is. | It is read in the selector language of the family the root's derivation names: CSS (html, xhtml), a JSON pointer pattern with `*` (json, ndjson, yaml), a property name (vcard), a block kind (markdown), a line pattern over a decoded body (rfc822). A family's op supplies its matcher and the check `ontology lint` runs on each selector (`O11-selector`). `matches.selector` dispatches the same way, so a standalone export classifies by shape (`/participants` and `/messages/*/sender_name` tell a Meta conversation), not only by a bundle path (D-roster). A field's source (`attr`) is read in the same family: an HTML attribute, a relative JSON pointer, a vCard parameter; `@attr` in a `concept` map likewise. Every selected scope is a `bytes=` span. | **drafted (draft 2), not implemented** |
| D-embeds | `data:` URIs in markup (v52 `el=` members; 47% of the instance's records). | An html or xhtml artifact is a container of every `data:` URI in its bytes, wherever it sits (an attribute, a `srcset` candidate, CSS `url()`); `data:,` and an empty payload are skipped. The payload, base64- or percent-decoded, is the member; its roster `path` is the URI's byte span, `<a>-<b>`; the mediatype gives the name it is sniffed by. The same payload at five places is one subject on five roster rows. A v52 `el=N` maps to its span once, in the converter. | **drafted (draft 2), not implemented** |
| D-json | JSON, NDJSON and YAML. | A span-keeping parser of the engine's own gives every value its byte span; `json.text@1` is the scalar leaves inside a span in document order, strings unescaped, one per line; `json.text@1 lines` parses NDJSON/JSONL as an array of documents; `yaml.text@1` serves YAML the same way over its own parse. Selectors are pointer patterns (D-select-family); a field filled from a scalar carries its source text verbatim (`1772355428000`), parsing it being a value op's work. A conversation is a term whose `select` mints one `message` per array element, in byte order; a v52 `turn=` maps to that `ord` in the converter, which knows v52's numbering (a Meta export is newest first). | **drafted (draft 2), not implemented** |
| D-vcard | vCard 3.0 and 4.0. | `vcard.props@1` unfolds content lines (RFC 6350 §3.2); a property's span covers its folded physical lines; its surface is the unfolded, unescaped value, structured components joined by a space. Selectors: `card` (one `BEGIN…END`) or a property name; a field's source is a parameter (`TYPE`). | **drafted (draft 2), not implemented** |
| D-markdown | CommonMark blocks. | `md.blocks@1` scans CommonMark blocks — ATX and setext headings, fenced and indented code, lists and their items, block quotes, GFM tables, thematic breaks, paragraphs, YAML front matter — with byte spans; a block's surface is its source with its block markers stripped (`#`, `>`, the bullet or number, the fence lines) and inline markup verbatim. Selectors are block kinds; a heading's `level` is its depth. | **drafted (draft 2), not implemented** |
