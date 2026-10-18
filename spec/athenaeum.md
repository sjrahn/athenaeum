---
spec_id: ATH
title: "The Athenaeum Specification"
status: draft
license: "CC BY-SA 4.0"
---

# The Athenaeum Specification

The Athenaeum keeps artifacts, says what they are, and asserts what they show about the world — each assertion a line that names its subject, its author and the evidence it rests on. Three things are kept because nothing else can recover them: the artifacts, the testimony of where and how they were found, and the owner's rulings. Everything else is derived from them or rediscovered over them. The entities and claims so found are the product.

This document is normative. The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Examples are illustrative; where an example and the text disagree, the text governs.

## 1. Scope

1.1 This specification defines:

- what an **instance** holds: artifacts, testimony, rulings, a vocabulary, and the judgments that describe, structure, read and cite artifacts and the entities they evidence;
- what the **tooling** derives from them, and the rules every stored and derived thing obeys;
- what the tooling knows about **formats**, and the primitives a vocabulary composes to say what data is;
- how artifacts are kept and found (**custody**), and the tool through which all of it is read and written.

1.2 A conforming tool implements every MUST of this document for the formats it registers (§10). A conforming instance holds only what this document allows to be stored.

1.3 The tooling acquires nothing. Artifacts and testimony are acquired by producers outside the tooling and handed to it from disk; the tooling never fetches them. The only network traffic it causes is custody's: reaching the stores an instance declares (§18.2), to keep and resolve what it already holds.

## 2. Principles

1. **Three things are kept; everything else is recovered.** The artifacts, the testimony (§9) and the owner's rulings (§13.5) are irreplaceable: each is a snapshot nothing else reproduces. Every other stored line is a judgment an author wrote and a verifier signed, checkable against the artifacts and rediscoverable by another author, or a cache of an op's output kept beside such judgments. The vocabulary is scaffolding of the same kind: two instances fed the same artifacts may build different vocabularies and should arrive, given time, at the same entities and claims.
2. **The tooling knows formats, never conventions.** An op sniffs a mime, records what the format's own specification defines, addresses the bytes on the axes the format has, decodes a surface, and exposes the format's own nodes — an element, a MIME part, a JSON value, an archive entry, a `data:` URI. It never names a term and never decides what a node is: that a row is a header, that a `>` line is a quote, that a repeated line is a running header, that an element is a post. A scope below `whole` exists only where the vocabulary or an author puts it. A new kind of thing is a vocabulary edit; a new format is one op module.
3. **Authors judge; the tooling assists.** Every structure, reading and claim that can be wrong is written by an author and verified by a second. The tooling addresses, decodes, selects, checks and reports; it never writes a claim of its own.
4. **Nothing is written until something is said.** Ingesting an artifact places it and its testimony in custody and writes nothing to the repository. An artifact's record comes into being with the first judgment about it; an entity's file with the first claim.
5. **Addresses are intrinsic.** A scope is named by coordinates in the bytes — page and box, byte range, row and column, time, constituent path — never by a transform, a parser's tree or an identifier.
6. **The vocabulary is the recipe.** A scope manifests forms; what a form expects — fields, reading aspect, children, render form, the op that yields its surface — rides on the form. What an entity owes rides on its kind. An author pins the vocabulary it read against by hash; nobody chooses a recipe.
7. **Derived, never stored.** Class, status, demand, binding state, chrome, staleness, provenance, holdings, every non-intrinsic address and the export are computed at read time (§12). A stored copy of a derivable thing is a defect.
8. **Nothing lossy enters a record.** A reading is a transcription checkable against the bytes — never a summary, a description, a paraphrase or a characterisation. Where a scope has no lossless transcription, the record marks its address and stops. What a scope shows about the world is a claim about an entity, cited to the scope. Where an artifact came from is testimony, never a line of its record. A record contains nothing unfalsifiable against its own bytes.

## 3. Terms

| term | meaning |
|---|---|
| **instance** | one repository with its vocabulary, records, entities, store and policy declarations and rulings (§4): **standalone**, or an **extension** of a **base** it builds on |
| **artifact** | bytes, identified by their BLAKE3; the subject `ath://<id>` (§7.1) |
| **id** | an artifact's short identifier: the first 8 hex digits of its BLAKE3, 16 where 8 collide (§7.1) |
| **container** | an artifact whose format holds whole files of its own |
| **constituent** | an artifact held whole inside a container; its own subject |
| **testimony** | an artifact a producer emitted about other artifacts — where, when, by what, why they were found (§9) |
| **receipt** | the testimony the tooling writes for every ingest (§9.3) |
| **record** | the file of judgments about one artifact, written once something is said about it (§8) |
| **intrinsics** | the line of a record that holds what the artifact's format defines about its bytes (§8.1) |
| **scope** | a region of an artifact named by an intrinsic address `at` |
| **term** | an entry of the vocabulary: a **form**, a **kind** or a **property** (§11) |
| **form** | what a scope is: a photograph, a receipt, a heading, a table, a page capture |
| **kind** | what an entity is: a transaction, a residence, a person, a vessel |
| **property** | what can be said of an entity: a total, an address, a vessel's name |
| **manifests** | the relation of a scope to a form it is |
| **unit** | a scope whose form `reads` an aspect: the grain of a reading |
| **reading** | an author's transcription of a unit under one aspect, stored with its revision |
| **surface** | the text an op decodes at a scope; what a quote is checked against |
| **entity** | a particular thing in the world, of one or more kinds, the subject of claims (§14) |
| **name** | the identifier of a term or an entity; one name space for both (§5.3) |
| **claim** | a line asserting the value of a property of an entity, carrying evidence |
| **evidence** | an anchor and a quote into an artifact supporting a claim, bound by verify |
| **op** | a versioned, deterministic function of bytes, registered in the tooling as `<name>@<version>` |
| **family** | the format an op parses (html, csv, pdf, rfc822, json, …); one parse per family per artifact |
| **pass** | one author and one verifier over one artifact or one entity: the graph every judgment they sign belongs to |
| **authorship** | what a line carries to say who wrote it: `by` (an op, or `owner`) or `pass` |
| **ruling** | the owner's steering: what the instance should distrust, accept, seek, defer or decline; never evidence (§13.5) |
| **store** | a place custody keeps artifacts and testimony: **managed** or **observed** (§18.2) |
| **policy** | an instance's rule for how many copies of which artifacts sit on which stores (§18.6) |
| **plane** | a served view of an instance: public, audience, owner (§16) |
| **demand** | work the stored lines and rulings imply is owed, derived (§14.6) |

## 4. Instances

4.1 An instance is one repository. It is standalone, or it extends exactly one other instance, its **base**. An extension reads everything its base holds as its own and writes only to itself; a base never reads its extensions. A base may itself extend another.

4.2 An instance's root holds `athenaeum.yaml`:

```yaml
id: 0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70   # a UUID, the instance's identity on every host
name: household
tier: private                              # public, or a named tier
extends:                                   # absent on a standalone instance
  path: ../reference
  commit: 5f2a9c1e7d3b40a86e1f2c9b7d4a3e5f60812c7d
shard: { records: 2, entities: 2 }         # §5.2
audiences:                                 # §16
  family: [private]
```

A cycle among bases, a base missing at its path or not at its pinned commit, or an unparseable file is a configuration error.

4.3 An extension reads its base at the pinned commit and at no other. Moving the pin (`instance repin`, §19.5) recomputes everything derived from the base: the vocabulary pin, and with it the staleness of the extension's passes; bindings, status and checks; ids (§7.1.3); anchors into artifacts the base no longer holds, which are flagged.

4.4 A subject resolves in the extension first, then in its base, and so on down; the view of a subject is the line-set union of its files. Within that union:

- a record line is never overridden: an extension MUST NOT write at an identity (§6.3) its base holds with different content; artifacts the base holds are the same subjects, and ingesting them again in the extension adds a receipt and testimony there and nothing else;
- an extension's entity line wins over its base's at the same identity;
- an extension adds terms and lines to the vocabulary, and MUST NOT write at an identity the base's vocabulary holds;
- a disagreement with a base line, and a term the extension mints, are demand on the base (§14.6).

4.5 Every line an instance holds carries the instance's `tier`; no line declares its own. An instance MUST NOT be `public` unless its base is.

## 5. Files

5.1 An instance's repository holds tracked content and nothing else:

```
<instance>/
├── athenaeum.yaml
├── terms/<name>.jsonl                 the vocabulary (§11)
├── records/<shard>/<id>.jsonl         judgments about artifacts (§8)
├── entities/<shard>/<name>.jsonl      entities and their claims (§14)
├── stores/<name>.yaml                 §18.2
├── policies/<name>.yaml               §18.6
└── rulings.jsonl                      §13.5
```

5.2 **Shards.** A record's `<shard>` is the first *n* hex digits of its artifact's id; an entity's is the first *n* characters of its name. `athenaeum.yaml` declares *n* per directory; absent, both take 2. Terms are never sharded. Changing a width is `instance reshard` (§19.5), which moves files and changes no line.

5.3 **Names.** Terms and entities are named by a **name**: lowercase letters, digits and hyphens, starting with a letter or digit, never consisting of hex digits alone. Terms and entities share one name space: no name names both. Every subject is therefore `ath://<id>` or `ath://<name>`, and resolves to exactly one file.

5.4 **The file is the subject.** A line in `terms/<name>.jsonl` or `entities/<shard>/<name>.jsonl` is about that name, and a line in `records/<shard>/<id>.jsonl` is about that artifact; no line repeats its subject.

5.5 **One-way reference.** A record never names an entity, a testimony or a container: those relations are derived (§12). Entities cite records freely. Terms are read by both and name neither.

5.6 **Host state.** What belongs to one machine lives outside every repository, under the XDG base directories:

| path | holds |
|---|---|
| `$XDG_DATA_HOME/athenaeum/` | the host's local store: `artifacts/` and `testimony/` (§18.2.3) |
| `$XDG_STATE_HOME/athenaeum/index.sqlite` | the custody index (§18.4) |
| `$XDG_STATE_HOME/athenaeum/instances/<id>/` | an instance's holdings, staged passes, locks and history, by the instance's `id` |
| `$XDG_CONFIG_HOME/athenaeum/access.yaml` | how this host reaches each store |

5.7 **Holdings.** An instance's holdings — every artifact and testimony it has ingested — are listed in its host state, updated at every ingest. The receipts in the stores are the authority: holdings are rebuilt from the receipts that name the instance (§9.3) when they are lost, and only then are the stores consulted for them.

## 6. Lines

### 6.1 Shape

6.1.1 A line is one JSON object on one line. Its keys:

| key | holds |
|---|---|
| `at` | in a record: the intrinsic address of the scope the line is about (§7.3) |
| `pred` | the predicate |
| `val` | the value |
| `by` · `pass` | the authorship |

Predicates add their own keys (`form`, `aspect`, `body`, `rev`, `ev`, …). A ruling carries an `id` (§13.5).

6.1.2 Every record, entity and ruling line carries exactly one authorship; a term line carries none, since the vocabulary is authored by its instance's history.

6.1.3 A line is a triple with provenance — the file's subject (and `at`), `pred`, `val` — plus its authorship, and maps to one N-Quads statement (§15.3).

```
// records/9f/9f2c1a3b.jsonl
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","pred":"in","val":{"at":"whole","ord":11},"pass":"p1"}
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","pred":"manifests","form":"heading","num":"5.","level":1,"pass":"p1"}
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","pred":"reads_as","aspect":"text","body":"Baseline emissions","rev":"b3:9f86d081884c7d65","pass":"p1"}
// terms/heading.jsonl
{"pred":"reads","val":"text"}
// entities/ti/tide-table-02.jsonl
{"pred":"version","val":"02.1","ev":[{"anchor":"ath://5e6e497d?page=1&bbox=0.1429,0.6906,0.0901,0.0087&text","quote":"Version 02.1","grade":"authoritative","mode":"stated","reading":"b3:aae7b6bb9c216abb"}],"pass":"p1"}
```

### 6.2 Authorship

6.2.1 `by` names an op as `<name>@<version>`, or `owner`. `pass` names a pass line in the same file by its id (§13.1).

6.2.2 A `pass` line is itself the authorship of the lines that name it and carries none of its own.

6.2.3 A record, entity or ruling line with no authorship, with both, or with a `pass` that does not resolve in its file MUST be refused at write.

### 6.3 Identity

6.3.1 A line's identity is the key a second line collides on. A write at an existing identity with different content replaces the line; a write with the same content is a no-op.

| line | identity |
|---|---|
| `intrinsics` | (at, pred, by) — a newer op writes a second line that supersedes the first |
| `manifests` | (at, pred, form) — several forms on one scope are several lines |
| `in` | (at, pred) — one placement per scope |
| `reads_as` | (at, pred, aspect) — one reading per scope and aspect; a re-read is a new revision at the same identity |
| `pass` · `complete` | (at, pred, id) · (at, pred, pass) |
| a claim | (pred, val, qual) — evidence accrues on the one line |
| `is` | (pred, val) |
| a ruling | (id) |
| a term line | (pred) for a single-valued predicate; (pred, name) for a repeatable one, where the name is the value's `name`, `col`, `selector` or `form`, else the whole value |

6.3.2 Competing transcriptions of one scope under one aspect are not representable.

6.3.3 The repository's history is the record of every replacement; no line records one.

### 6.4 Files and canonical form

6.4.1 One line per assertion. A file is sorted by identity. Nothing depends on line order: reading order is `ord` (§8.1), never position. The union of an extension with its base, and a merge, are line-set unions.

6.4.2 The canonical serialisation of a line is compact JSON, LF-terminated, non-ASCII characters unescaped, with its keys in a fixed order: `id` or `at` first, then `pred`, then every other key in code-point order, then the authorship (`by` or `pass`) last; every nested object's keys in code-point order; arrays in their stored order. Two lines are the same content when their canonical serialisations are equal. Every hash this document defines over JSON — a revision, the pin — is taken over this form.

6.4.3 The packed `val` is the unit of judgment: `in` packs its parent and `ord` because they are verified together.

### 6.5 Revisions

A reading's body is always on its line. Its `rev` is `b3:` followed by the first 16 hex digits of the BLAKE3 of its body: a string as UTF-8, an array as its canonical JSON (§6.4.2).

## 7. Artifacts and addresses

### 7.1 Artifacts and their ids

7.1.1 An artifact's identity is the BLAKE3 of its bytes and nothing else: no URL, name, path or producer key takes part in it. New bytes are a new artifact. The same bytes met again are the same artifact; the encounter adds testimony (§9) and nothing else.

7.1.2 Within an instance an artifact is written by its **id**: the first 8 hex digits of its BLAKE3. Its subject is `ath://<id>`; its record, when it has one, is `records/<shard>/<id>.jsonl`. Testimony and the format's constituent lists carry full hashes; everything tracked in the repository carries ids.

7.1.3 Where two artifacts the instance holds share their first 8 digits, the one received first (by its receipt, §9.3; a constituent by its container's) keeps the 8-digit id and every later one is written with 16. An extension defers to its base: if a repin brings a base artifact onto an 8-digit id the extension already uses for another artifact, the repin rewrites the extension's lines to give its own artifact 16 digits. Should 16 digits collide, the full hash is the id.

7.1.4 A reference that names an id resolves to exactly one artifact or is flagged.

### 7.2 Containers and constituents

7.2.1 A **container** is an artifact whose format holds whole files of its own: an archive entry, a package's documents, a message's parts, a mailbox's messages, the payload of a `data:` URI in markup. Which formats are containers, and how their constituents are named, is the format's definition (§10.3).

7.2.2 A container's constituents — per constituent, its `path` in the format's own terms, its BLAKE3, and the fields the format defines for it (a filename, a mediatype, a Message-ID) — are a fact of the container's bytes. Every constituent is its own artifact, addressable and resolvable from the moment its container is ingested, and the instance holds it because it holds its container.

7.2.3 Which containers hold an artifact is derived from their constituents (§12). Cite the constituent, which outlives the package.

### 7.3 The intrinsic address — `at`

7.3.1 `at` is the only address stored and the only address an anchor carries. Its axes are declared by the artifact's root form (§11.4). Every axis is a coordinate in the bytes as stored, with no transform.

| axis | formats | meaning |
|---|---|---|
| `whole` | every artifact | the artifact; where `intrinsics`, `pass`, `complete` and the root `manifests` sit |
| `page=N` · `page=N&bbox=x,y,w,h` | pdf | page N, 1-based; a box normalised 0–1 in the page frame, origin top-left |
| `bbox=x,y,w,h` | raster images | a box normalised 0–1 on the pixel grid |
| `bytes=a,b` | every text format: html, xhtml, markdown, plain text, rfc822, json, ndjson, yaml, vcard | the half-open byte range [a, b) of the file |
| `row=N` · `row=N&col=M` · `col=M` | csv, tsv | physical row N and column M, both 0-based |
| `t=a,b` | audio, video | seconds [a, b) in the stored stream |
| `path=p` | containers | the constituent at path p, equivalent to the constituent's own subject |

7.3.2 A **union address** `a;b;c` names one scope made of several regions — a table spanning pages is the union of one box per page. A union is the scope's own address, never a constituent's address borrowed.

7.3.3 A trailing **aspect** `&text`, `&cells` or `&tex` names the reading a quote is taken from.

### 7.4 Canonical form

7.4.1 Box coordinates carry at most 4 decimals. Containment of one box in another allows 0.002 slack per edge.

7.4.2 The regions of a union sort by page, then y, then x, then byte start; `path` sorts last. Every address is canonicalised before it is used as identity.

### 7.5 Routes through containers

7.5.1 An address that carries `path=p` routes: the container's constituents name the constituent at p, and the rest of the address applies in that constituent. The route holds wherever `path` stands in the address. A path the container lacks is flagged.

7.5.2 An anchor through a route canonicalises, at bind time, to the constituent's own id.

### 7.6 Derived addresses

7.6.1 Two further forms exist and neither is stored.

- **Positional**: the `ord` path from `whole` down the `in` chain, always available.
- **Designated**: the path of designators the bytes themselves print — `?sec=5&para=6`, `?eq=1`, `?post=4`, `?col=Currency`, `?ch=2&fig=1` — available where a form declares a designator field (§11.2).

7.6.2 The resolver maps either form to an `at` through `manifests`, `in` and `ord`. A later designator key narrows to the earlier key's scopes' descendants by `in`, and to what their boxes contain. A designator field whose pattern has a capture answers to the capture as well as the whole value: `num: "3."` under `^(\d+)\.$` answers `sec=3`.

### 7.7 Physical addressability

A page the document has, a row the parse holds and a cell within such a row are scopes an anchor may name even where nothing manifests there.

### 7.8 Re-capture and moved scopes

7.8.1 A re-capture is a new artifact. A `supersedes` claim relates the two (§14.2); an anchor carries across where the surface at the same intrinsic address still holds its quote, and is otherwise held (§14.4).

7.8.2 A structure correction that moves a scope moves the readings on it — same body, same `rev`, new address. An anchor still inside the new region does not move; an anchor left outside is flagged, and verify finds the reading by its `rev` at its new address and reports the anchor to move.

## 8. Records

### 8.1 Predicates

8.1.1 A record holds judgments about one artifact, and the cache of its intrinsics. It is written with the first judgment about the artifact; an artifact nobody has said anything about has no record, and its format, structure and provenance are derived on demand.

| predicate | authorship | meaning |
|---|---|---|
| `intrinsics` | op | what the artifact's format defines about its bytes: mime, size, encoding, page count, dimensions, duration, the metadata the format specifies, and a container's constituents. Nothing a producer asserts. Written when the record is, as a cache: `by` names the format op and its version; a line by an older version than the tool's is **stale** (§12) and a format sweep writes a superseding line. |
| `pass` | — | a pass: `{id, by, verify, vocab, date}`. The graph every judgment in the file belongs to (§13.1). |
| `complete` | pass | the pass's attestation that structure over `at` is complete — every word of the surface lies in a scope or in chrome. It means complete, never correct. It lapses on any structure change inside its extent. Written only on an asserted tree (§11.4). |
| `manifests` | pass, or derived | the scope at `at` is the `form` named, with the fields the form declares. Only a form may be manifested. An undeclared field is refused at write. A stored line wins over a derived one at the same scope. |
| `in` | pass, or derived | placement: the parent's bare `at` and `ord`, reading order within it. Physical scopes (pages, columns) carry no `in`: containment there is geometric. The logical tree runs from `whole` down. Every non-physical scope MUST be reachable from `whole` by `in`. |
| `reads_as` | pass | an author's transcription of the scope under one aspect (`text` · `cells` · `tex`), with `body` and `rev`. Every aspect is lossless and checked against the bytes where the bytes give a surface (§13.4). Readings are annotations beside the bytes, never substitutes for them. |

### 8.2 Rules

8.2.1 **Unit rule.** A `reads_as` sits only at a scope that manifests a form, and its aspect MUST be one that form `reads`. Readings are never smaller than a unit; a unit may be a group (a table with its caption, an equation with its label).

8.2.2 **Faithful to the bytes.** A reading transcribes what is printed, typo included. A correction of the source is a claim with `mode: inferred` or a `challenges`, never a silent fix.

8.2.3 **Designators are structure.** A leading "5.", a right-margin "Equation (1)", a "#4" on a post are fields on `manifests`, verbatim as printed; the body is the text without them. Deciding that "2." is a number and not a sentence is a judgment, written by the pass that reads the scope.

8.2.4 **Where the bytes give the structure, nothing is stored.** Under a form's `select`, `shape` and `spine` lines (§11.7), `manifests` and `in` derive from the parse; a pass writes a line below `whole` only to disagree with the derived structure or to add to it.

8.2.5 **Chrome is derived by a declared rule.** Running headers, page numbers, navigation: a form's `chrome` line names what makes a run chrome (§11.2). The tooling applies the rule and has none of its own. Chrome is listed in the export header and stored nowhere.

8.2.6 **A scope with no lossless transcription has no reading.** It is addressed, manifested and placed; its bytes resolve at its `at`; the record stops there. Anything said about what it shows is a claim anchored at that `at` with no quote and `mode: inferred`. Where such a scope carries transcribable content — print in a photograph, speech in a recording — a pass manifests the sub-scopes that carry it and reads those.

8.2.7 **Reading an image is reading.** An author looks at the pixels of a scope and transcribes what is printed there, under aspect `text`, exactly as it reads any other scope. No op transcribes an image. A PDF's text layer is a surface only where the PDF draws its text (§10.4.4).

8.2.8 **A field the address determines is derived.** A field a form declares `derived` (a page's number) is never stored.

```
// records/a4/a48bf844.jsonl — the photograph of a receipt on a table, read by p1
{"at":"whole","pred":"intrinsics","val":{"bytes":2310455,"height":3024,"mime":"image/jpeg","width":4032},"by":"jpeg.intrinsics@1"}
{"at":"whole","pred":"pass","val":{"by":"reader-a","date":"2026-01-12","id":"p1","verify":"reader-b","vocab":"b3:5c1e0a9d77f3b210"}}
{"at":"whole","pred":"manifests","form":"photograph","pass":"p1"}
{"at":"bbox=0.31,0.12,0.38,0.71","pred":"in","val":{"at":"whole","ord":0},"pass":"p1"}
{"at":"bbox=0.31,0.12,0.38,0.71","pred":"manifests","form":"receipt","pass":"p1"}
{"at":"bbox=0.36,0.69,0.27,0.03","pred":"in","val":{"at":"bbox=0.31,0.12,0.38,0.71","ord":4},"pass":"p1"}
{"at":"bbox=0.36,0.69,0.27,0.03","pred":"manifests","form":"total-line","pass":"p1"}
{"at":"bbox=0.36,0.69,0.27,0.03","pred":"reads_as","aspect":"text","body":"TOTAL 42.10","rev":"b3:0de3a1c94b7e5f21","pass":"p1"}
```

## 9. Testimony

### 9.1 What testimony is

9.1.1 Where an artifact was found, when, by what and why is not a fact of its bytes and cannot be checked against them. It is **testimony**: a snapshot a producer made, irreplaceable because the moment is gone, and never a line of a record.

9.1.2 Testimony is itself an artifact — a capture sidecar, an export's own manifest, the tooling's receipt — kept verbatim. Its identity is its BLAKE3. It is held in custody beside the artifacts, in each store's `testimony/` tree, under the same policies (§18.6), and never in the repository.

9.1.3 **Testimony carries its own links.** A testimony names, in its own bytes and by full hash, the artifacts it is about; nothing else records the link. A receipt names its artifact and the testimony delivered with it (§9.3). A producer's testimony that names no hash is linked by the receipt that delivered it.

9.1.4 A testimony cannot be edited, because its bytes cannot change. A mistaken testimony is answered by a later one and, where the owner will not rely on it, by a `distrust` ruling (§13.5).

9.1.5 Testimony is evidence, not knowledge. It holds no claim and has no status. A claim about where or when something was found or published cites the testimony by an ordinary anchor into its bytes; such evidence is graded `direct`.

### 9.2 Delivery

9.2.1 Testimony arrives with the artifact it describes: beside it as `<file>.testimony.<ext>`, or named explicitly at ingest. It is kept exactly as delivered.

9.2.2 A testimony describing a container describes the container only; its constituents inherit it by derivation (§9.6).

### 9.3 The receipt

9.3.1 Every ingest writes one testimony of the tooling's own, the **receipt**:

```json
{"actor":"reader-a","artifact":"9f2c1a3b…","instance":"0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70","name":"statement-03.pdf","received":"2026-01-12T09:14:03Z","testimony":["41aa07d2…"]}
```

— the instance it was ingested into, who handed the artifact in, the instant, the name it arrived under, the artifact's full hash, and the full hash of every testimony delivered with it. Testimony is not itself receipted: the receipt covers it, so every artifact has at least one testimony and the chain stops at one.

9.3.2 The receipt is the only testimony shape the tooling prescribes. Every standalone instance carries its form, `receipt`, refining `testimony`.

9.3.3 The receipts naming an instance are the authority for what it holds (§5.7).

### 9.4 Origin forms

9.4.1 An instance says what testimony it accepts in its vocabulary. An **origin form** refines `testimony`. It `matches` a producer's shape over the testimony's mime (§11.5), and declares its facets as `select` and `field` lines:

- the **source** — where the artifact came from: a uri, a sender, an account;
- the **producer** — what found or made it: the machine, the tool and its version, the session;
- the **context** — why it was acquired;

with `required` on every field each testimony of that origin MUST carry. A new origin, or a new required field, is a vocabulary edit.

9.4.2 The tooling knows no origin. Which facets exist, what they are called and which are required is the instance's.

### 9.5 Admission

9.5.1 Ingest MUST refuse, before anything is placed in a store, a delivered testimony that manifests no form refining `testimony`, or that lacks a field its origin form requires.

9.5.2 The same check runs over the holdings (§17), so an origin form that tightens lists the testimony it no longer admits. A testimony admitted once is never removed for failing a later check; it is listed.

### 9.6 Provenance

9.6.1 An artifact's **provenance** is derived (§12): every testimony that names it, together with the provenance of every container that holds it, at that path, transitively.

9.6.2 Provenance is shown as a chain — the receipt, the container's testimony, the path, the constituent — so a container's uri is never presented as a constituent's. Nothing is copied to a constituent: an artifact first met alone and later inside an export has both origins the moment the export is ingested.

9.6.3 A distrusted testimony stays in provenance, marked; evidence anchored into it is held (§14.4).

### 9.7 Removing a copy

A copy of an artifact MAY be removed from a store once the artifact's policies hold without it, counting every route — a container that holds it is a copy of it (§18.6.3). Its records, claims and testimony stay, since identity is the hash. A container that re-encoded an artifact holds a different artifact; "the same image as" is a claim.

### 9.8 Placement

A testimony belongs to the instance its receipt names. An extension MAY hold testimony about its base's artifacts; it MAY be more private than its subject — a document in a public base, a private extension's record of the machine that fetched it.

## 10. Formats

Everything in this section is knowledge of a format's own specification. None of it says what the data means.

### 10.1 Sniffing

10.1.1 Ingest names an artifact's mime from its bytes. A format with a signature is named by its signature, never by a file extension:

- leading magic bytes (PDF, PNG, JPEG, GIF, TIFF, WebP, ZIP, RAR, 7z, gzip, PE, ELF, Ogg, the ICO header, MPEG audio frames and ID3, ADTS, IVF, Annex B elementary streams, ZIM, OSM PBF, …);
- a ZIP is told apart by its entries: EPUB by its `mimetype` entry, OOXML by its parts (`word/`, `xl/`, `ppt/`), an application package by its declared parts;
- ISO base media files by the `ftyp` brand (HEIC, AVIF, M4A, QuickTime, 3GPP, else MP4);
- a message by its header lines; a mailbox by a `From ` line followed by a header line;
- vCard, iCalendar and STEP by their first line;
- JSON by parsing — one value, or one value per line (NDJSON).

10.1.2 Where no signature decides, the extension MAY name a text format (markdown, YAML, TSV, source code). What nothing names is `application/octet-stream`.

10.1.3 A constituent is sniffed by its bytes and, where the container gives one, by the name the container gives it.

### 10.2 Intrinsics

10.2.1 Every `intrinsics` line carries `mime`, `bytes` (the size) and, for text, `encoding`. Each format adds what its specification defines:

| format | beyond mime, size, encoding |
|---|---|
| pdf | page count; page sizes; the document information dictionary |
| raster images | width and height in pixels; the format's embedded metadata (EXIF, XMP, ICC) as recorded |
| audio, video | duration; tracks with their codec, and for video the frame size and rate |
| csv, tsv | rows, columns, the delimiter, whether a byte-order mark is present |
| html, xhtml | the declared encoding; `<title>`; the standard `<meta>` names the format defines (`generator`, `description`, `author`) |
| rfc822 | `message_id`, `subject`, `from`, `to`, `cc`, `date` and `date_iso`; the part table, each part with its mime, transfer encoding, charset, filename, disposition and raw byte span; the constituents |
| mbox | the message count; the constituents |
| zip | the constituents |
| epub | the package's Dublin Core (`title`, `creator`, `language`, `identifier`, `isbn`, `date`, `publisher`); the package document's path; the spine as constituent paths in reading order; the constituents |

10.2.2 A header field is read as UTF-8 where it is valid UTF-8, else as ISO-8859-1, and then its encoded words decode (RFC 2047, RFC 6532).

10.2.3 A field a producer asserts — inserted into the bytes by a capturing tool under a name of its own — is not part of the format. It is text in the bytes, which an origin form or any form MAY select like any other text.

10.2.4 Each format's intrinsics op is named `<format>.intrinsics@<version>`. The tool registers one current version per mime; a `intrinsics` line by an older version is stale (§12).

### 10.3 Constituents

| container | a constituent is | its `path` |
|---|---|---|
| zip | every file entry (stored, deflate, zstd); a ZIP64 archive is refused | the entry name |
| epub | every file entry of its ZIP | the entry name |
| rfc822 | every leaf part whose content is not `text/plain`, and every nested message, decoded from its transfer encoding | the MIME part path (`1.2`, `3`) |
| mbox | every message, un-stuffed (one `>` removed from every `^>+From ` line) | the 1-based ordinal |
| html, xhtml | the payload of every `data:` URI in the bytes, wherever it stands — an attribute, a `srcset` candidate, a CSS `url()` — base64- or percent-decoded; an empty payload is skipped | the URI's byte span, `<a>-<b>` |

10.3.1 The same bytes at several paths are one constituent subject listed several times.

10.3.2 A container format with no registered reader is an artifact with no constituents.

### 10.4 Surface ops

10.4.1 A **surface op** decodes the text at a scope: given the bytes, one region of an address and an optional argument, it yields a string or nothing. A union address yields the regions' surfaces joined by a newline. Each op says which arguments it takes and refuses every other.

10.4.2 The bytes are parsed once per family per artifact, and the classification probes (§11.5) read that parse.

10.4.3 The registered surface ops:

| op | family | regions served | surface |
|---|---|---|---|
| `html.text@1` | html, xhtml | `whole`, `bytes` | the text of the elements in the span: `head`, `script`, `style`, `template`, `noscript` and `svg` dropped; block elements and `<br>` end a line; table cells separated by a tab; whitespace runs collapsed to one space; lines trimmed; blank lines collapsed |
| `html.attr@1 <name>` | html, xhtml | `whole`, `bytes` | the named attribute of the root element at the span |
| `html.title@1` | html, xhtml | `whole` | the document's `<title>` |
| `csv.parse@1 [<delimiter>]` | csv | `row`, `row&col` | a cell's value; a row's cells joined by a tab; RFC 4180 quoting; a byte-order mark stripped; the argument names the delimiter (`tab`, `;`, `|`), default comma |
| `pdf.words@1` | pdf | `whole`, `page`, `page&bbox` | the words the PDF draws inside the region (§10.4.4), banded into lines on each glyph's baseline origin, in column-aware reading order; boxes rounded to 4 decimals |
| `eml.text@1` | rfc822 | `bytes` | the span transfer-decoded (7bit, 8bit, binary, quoted-printable, base64) and charset-decoded, CRLF folded to LF, trailing whitespace trimmed |
| `json.text@1 [lines]` | json, ndjson | `whole`, `bytes` | the scalar values inside the span in document order, strings unescaped, one per line; `lines` parses one document per line |
| `yaml.text@1` | yaml | `whole`, `bytes` | as `json.text@1`, over the YAML parse |
| `vcard.text@1` | vcard | `whole`, `bytes` | the content lines in the span unfolded (RFC 6350 §3.2), each value unescaped, a structured value's components joined by a space |
| `markdown.text@1` | markdown | `whole`, `bytes` | the blocks in the span with their block markers removed (`#` runs, `>`, a list bullet or number, fence lines); inline markup verbatim |

10.4.4 **Born-digital text only.** `pdf.words@1` reads text the PDF draws. A glyph drawn invisible — text render mode 3, the mode an OCR layer laid under a page image uses — contributes nothing to the surface. A page whose only text is invisible is a raster page: it has no surface, and an author reads it as an image (§8.2.7) or it is not read.

10.4.5 An HTML scope's span runs from its start tag's first byte to its end tag's last byte, half-open; an element whose end is implied is flagged. Offsets in the decoded text map to bytes by a prefix sum of the UTF-8 lengths of its code units.

10.4.6 A JSON or YAML value's span covers its source text, a string's quotes included. A vCard content line's span covers its folded physical lines. A markdown block's span covers its lines, its markers included.

10.4.7 An op's version identifies its behaviour. Any change to an op's output for any input is a new version.

### 10.5 The proposal op

10.5.1 One medium cannot be read directly by an author: speech. For it alone the tooling has a **proposal op**, `audio.speech@1`, a speech recogniser run on the host — a local binary or a service bound to the host — over an audio or video artifact. It prints candidate scopes `t=a,b` with the text it heard. An author MAY stage them in a pass, correct them and sign; the engine and its model ride in the pass's note.

10.5.2 The proposal op's output is never a surface and never stored under its own `by`. What a pass signs are readings; claims bind to the readings. A reading of speech has no surface to be checked against, so the reading check lists it for inspection (§13.4).

10.5.3 No other proposal op exists. In particular no op transcribes an image or proposes the layout of a page.

### 10.6 Selector languages

10.6.1 A `select` line's selector, and a `matches` line's `selector`, are read in the language of the family the artifact's root derivation names:

| family | selector | a field's source (`attr`) |
|---|---|---|
| html, xhtml | a CSS selector | an attribute name |
| json, ndjson, yaml | a JSON pointer (RFC 6901) in which `*` stands for any key or index (`/messages/*`) | a pointer relative to the selected value (`sender_name`) |
| vcard | `card` (one `BEGIN`…`END`), or a content-line name (`FN`, `EMAIL`) | a parameter name (`TYPE`) |
| markdown | a block kind: `heading`, `paragraph`, `list`, `list-item`, `code`, `table`, `quote`, `break`, `front-matter` | — (a heading's `level` is its depth) |
| rfc822 | `header` (the header block); `part[type=<mime>]` (a part by its type); inside a decoded `text/plain` part, a line rule: `{"lines": "<regex>"}` (a run of lines each matching), `{"from": "<regex>"}` (from a matching line to the part's end), `{"blank": true}` (runs delimited by blank lines) | — |
| containers | a path pattern over the constituent list (`*` any run of characters) | — |

10.6.2 A line rule applies only where the part's transfer encoding is line-local (7bit, 8bit, binary, quoted-printable); a base64 part is one scope.

10.6.3 Every scope a selector mints is a `bytes=` span in a text format, or a `path=` route in a container.

10.6.4 A value filled from a source is its source text verbatim (`1772355428000`, `Sunday, March 1 at 8:57 AM`); interpreting it is an author's work. Where the field declares a `pattern`, the first capture (else the whole match) is the value, and a source that does not match keeps its raw text.


## 11. The vocabulary

### 11.1 Three sorts of term

11.1.1 The vocabulary is the instance's terms, one file each under `terms/`. A term is of exactly one sort, fixed by the root its `refines` chain reaches:

| sort | root | what it names | used by |
|---|---|---|---|
| **form** | `form` | what a scope of an artifact is: photograph, receipt, heading, table, page capture, testimony | `manifests` on records |
| **kind** | `kind` | what an entity is: transaction, residence, person, vessel | `is` on entities |
| **property** | `property` | what can be said of an entity: total, address, vessel name | the `pred` of a claim |

11.1.2 A scope manifests only forms; an entity is only of kinds; a claim's predicate is only a property. A receipt is a form — what a region of a photograph shows; the purchase it records is an entity of kind `transaction`, and the receipt is evidence for the transaction's claims.

### 11.2 Term predicates

11.2.1 Every term MAY carry `refines` (its single parent), `definition` (one sentence: the contract for the word) and `aligns` (the IRI of a class or property in a published vocabulary the graph projection asserts it under).

11.2.2 A **form** carries:

| predicate | value |
|---|---|
| `matches` | a classification condition (§11.5); repeatable, every line must hold |
| `axes` | the address axes of a root form (§7.3) |
| `physical` | the axis whose scopes are physical (`page`) |
| `tree` | `asserted` (structure is judgment: `in` and `ord` are written by passes) or `derived` (structure comes from the parse under `select`, `shape`, `spine`) |
| `derivation` | the surface op, `<op>@<version>[ <argument>]` (§10.4) |
| `reads` | the aspect a scope of this form is read under: exactly one of `text`, `cells`, `tex`, `none` |
| `field` | a field on `manifests`: `{name, type, required?, derived?, options?, where?, pattern?, address?}`; `type` is one of `int`, `enum`, `datetime`, `string`, `col`, `designator`, `list`. A **designator** is a verbatim sub-reading with `where` (`leading`, `trailing`, or a descendant form), `pattern` and the derived-address key it feeds (`address`) |
| `expects` | child forms a scope of this form normally contains; satisfied by a scope manifesting the form or a refinement of it |
| `evidences` | the kinds an entity this form records is usually of (`receipt` → `transaction`); it steers authors and mints nothing |
| `convention` | reading conventions inherited down the `in` chain, from a closed set the reading check applies (§13.4): `{"footnotes": "[^n]"}`, `{"hyphens": "rejoin"}`, `{"scripts": "flatten-outside-math"}`, `{"bullets": "drop"}` |
| `renders` | the markdown form of a scope: `{"md": "<template>"}` over `{body}`, a field's name, and `{level+1}` |
| `select` | `{selector, form, in?, field?, attr?, ord?, level?}` — derived structure (§11.7) |
| `shape` | `{col, form, pattern?, required?}` maps a column to a form; `{header: <row>, form}` declares which row, if any, is the header and the form it manifests; `{rows: <form>}` names the form every other row manifests |
| `spine` | `{form}`: the order a container's package declares, each entry a route scope manifesting `form`, placed `in whole` |
| `chrome` | what is chrome: `{"selector": …}`, or `{"repeats": {"pages": <n>, "share": <fraction>}, "mask": "digits", "box": <decimals>, "roles": {"page-number": "<masked pattern>"}}` — a run is chrome when its masked text and its box at the declared precision recur on at least *n* pages and that share of them; role by pattern, else `running-header` or `running-footer` by position |
| `check` | a declarative check over scopes of the form (§17.3) |

11.2.3 A **kind** carries `owes`: the properties an entity of this kind should have. An unmet `owes` is demand (§14.6).

11.2.4 A **property** carries `range` — the type of its values (`string`, `int`, `decimal`, `amount`, `date`, `datetime`, `uri`, `bool`), or a kind, when its value is another entity — and MAY carry `functional`: an entity has at most one value of it.

```
// terms/receipt.jsonl                                  // terms/transaction.jsonl
{"pred":"refines","val":"document"}                     {"pred":"refines","val":"kind"}
{"pred":"definition","val":"a printed record of a sale"} {"pred":"owes","val":["total","date","merchant"]}
{"pred":"expects","val":["line-item","total-line"]}
{"pred":"evidences","val":["transaction"]}              // terms/merchant.jsonl
                                                        {"pred":"refines","val":"property"}
// terms/total.jsonl                                    {"pred":"range","val":"organization"}
{"pred":"refines","val":"property"}                     {"pred":"functional","val":true}
{"pred":"range","val":"amount"}
{"pred":"functional","val":true}
```

A form and a property may not share a name (§5.3): the scope that shows a total manifests the form `total-line`, and the transaction's `total` is the property.

### 11.3 The effective rules of a scope

A scope's rules are the union of its forms' `refines` chains and its ancestors' conventions down the `in` chain. Where two forms declare the same expectation, the most specific wins. A form with no `renders` renders as its parent; an unknown form renders as `unit`.

### 11.4 Roots, classes and trees

11.4.1 An artifact's **mime root** is the most specific form whose `matches` names its mime and nothing else. Its **root** is the most specific form that matches it at all. Its effective chain is the root's `refines` chain followed by the mime root's. `axes`, `physical`, `tree` and `derivation` come from the first form along that chain that declares them.

11.4.2 Every root form refines one of these classes:

- **document** — readings can total to a proxy: pdf, html, xhtml, markdown, rfc822, the documents of a package;
- **lossy** — readings can be drawn, never total: **image** (raster images) and **media** (audio, video);
- **data** — values given by the parse: csv, json, ndjson, yaml, vcard, and **container**;
- **testimony**, refining data — what a producer said about other artifacts (§9).

11.4.3 Class is a lookup on the chain. One stored `manifests` at `whole` overrides the derived root (a PDF of photographs manifests `scan-album`); where two roots match an artifact, the most specific `matches` decides and a stored override settles the rest. Constituents carry their own forms; nothing is classified twice.

### 11.5 Classification

11.5.1 A `matches` line is a set of conditions, every one of which must hold:

| condition | holds when |
|---|---|
| `mime` | the artifact's mime is the value; required on every `matches` |
| `first_row` | a tabular artifact's first physical row begins with the listed cells, whatever row the shape declares the header |
| `selector` | the selector, in the root family's language (§10.6), selects something |
| `magic` | the bytes begin with the value |
| `container` | some container holding the artifact has this root form |
| `constituent` | some path among the artifact's own constituents matches the pattern |
| `path` | the artifact's own path in some container matches the pattern |

A pattern is a prefix, or a glob where `*` stands for any run of characters, anchored at the start.

11.5.2 A form's `matches` lines all hold, or the form does not match. Alternatives are sibling forms under a common parent.

11.5.3 An artifact held by several containers is probed against every (container, path) pair; a `container` or `path` condition holds if any pair satisfies it.

11.5.4 Among the matching forms, the most specific wins: the most conditions held, then the longer `refines` chain, then the name in code-point order.

### 11.6 Which op yields a surface

11.6.1 A scope's surface comes from the first `derivation` along its own forms' chains, else along the artifact's effective chain. A `timestamp` form that declares `html.attr@1 datetime` yields the attribute while its siblings yield `html.text@1`.

11.6.2 A form naming an op the tool has not registered, a value that does not parse, or an argument the op refuses is a configuration error wherever the artifact loads, and a blocking vocabulary check. A root that declares no derivation has no surface; its scopes are bound only by readings.

### 11.7 Derived structure

11.7.1 Where the tree is derived, every `select`, `shape` and `spine` line along the effective chain mints scopes from the parse:

- a selected node becomes a scope at its span (or its route), manifesting `form`;
- its parent is the nearest enclosing scope of the form named by `in`, else `whole`;
- its `ord` is byte order among its siblings, unless `ord` names another order the format defines;
- a `field` is filled from `attr` (§10.6.4); a designator field from the text `where` names;
- `level` sets a heading's level.

11.7.2 A tabular tree: the declared header row manifests its `shape` form and is `in whole, ord 0`; every other row manifests the `rows` form, `in whole`, ordered by row number; each shaped column is a scope at `col=M` manifesting its form, with `name` from the header, and contains its cells. Without a `rows` line, rows are addressable (§7.7) and manifest nothing.

11.7.3 A container's tree: one route scope per constituent a `select` path pattern names, manifesting that line's `form`; or one per spine entry in spine order, manifesting the `spine` line's `form`; each `in whole`.

11.7.4 Derived structure and its surfaces are computed, never stored, and bind as `derived:<op>@<version>[ <argument>]` (§14.4).

### 11.8 The pin

11.8.1 A pass pins the vocabulary it read against (`vocab`): `b3:` followed by the first 16 hex digits of the BLAKE3 of the vocabulary as loaded, an extension's terms together with its base's — the term files in name order, each preceded by its name and its lines sorted by identity, each line in canonical form (§6.4.2).

11.8.2 A change to a term makes every pass pinned at an older hash **stale** for the scopes and entities it reaches: derived, listed, re-run. Nobody edits a recipe.

### 11.9 What the tooling prescribes

The tooling relies on exactly these terms, which every standalone instance carries: the roots `form`, `kind` and `property`; the forms `unit`, `document`, `lossy`, `image`, `media`, `data`, `container`, `testimony` and `receipt`. Every other term is the instance's.

## 12. Derived, never stored

The following are computed at read time. Writing any of them to a file is a check failure.

| | derived from |
|---|---|
| an unwritten record | the artifact's bytes, its intrinsics op and the vocabulary |
| class, root form | the mime through `matches`; the `refines` chain; a stored override |
| `manifests` and `in` on a derived tree | the parse through `select`, `shape`, `spine`; a stored line at the same scope wins |
| chrome | the rules `chrome` lines declare |
| positional and designated addresses | `manifests` fields, `in`, `ord` |
| containers of an artifact | the constituents of the containers the instance holds |
| holdings | the receipts naming the instance (§5.7) |
| provenance | the testimony naming an artifact, and its containers' provenance (§9.6) |
| testimony admitted | whether a testimony's root is an origin form and it carries the fields that form requires |
| stale intrinsics | a `intrinsics` line by an older op version than the tool's for its mime |
| binding state | an evidence entry's binding against the current readings and surfaces (§14.4) |
| status | bound evidence, grades, modes and standing challenges (§14.5) |
| demand | §14.6 |
| staleness of a pass | `pass.vocab` against the current pin, for what a changed term reaches |
| residence | the host index (§18.4) |
| relevance | the `seek` rulings an artifact, scope or entity meets (§13.5) |
| complete extent, section closure, paragraph numbers | `in` and `ord` |
| the export, the remainder, the envelope | §15 |
| sensitivity | the tier of the instance a line lives in |

## 13. Passes and rulings

### 13.1 Passes

13.1.1 A pass is one author and one verifier over one artifact, one set of constituents of a container (its `with` names the container's pass), or one entity. The author and the verifier MUST differ. A judgment exists only once both have signed; nothing unsigned is in the repository.

13.1.2 A pass line: `{"at":"whole","pred":"pass","val":{"id","by","verify","vocab","date","note"?,"with"?}}` in a record; the same without `at` in an entity's file. `vocab` is the pin (§11.8). An id is `p<n>`, the lowest number free after every signed and open pass on the subject.

13.1.3 A correction pass swaps roles, so no correction is self-verified. A pass over speech MAY start from the proposal op's output (§10.5).

### 13.2 Staging and signing

13.2.1 An open pass stages its lines in its instance's host state (§5.6), outside the repository.

13.2.2 Signing lays the staged lines over the stored lines by identity (with `complete` where the author asks), in canonical order, and runs the record checks, the per-file checks and the per-form checks over the result (§17). Any blocking finding refuses the signature and leaves the staging untouched. A staged line at an existing identity with different content replaces the stored line (§6.3). A record that does not yet exist is created, with its `intrinsics` line, by the first signature over its artifact. Abandoning a pass discards its staging.

### 13.3 Complete

`complete` is written only on an asserted tree. Under it, every word of the surface must lie in a scope or in chrome, and the coverage check blocks (§17.1). On a derived tree, completeness is the export's remainder (§15.1).

### 13.4 The reading check

13.4.1 For every reading the bytes give a surface for, the **reading check** compares the reading's body with the surface at its `at`, after the scope's conventions and designators are applied, per aspect. Divergence is listed for a person; it is never resolved automatically. A reading with no surface to compare — of an image, of speech — is listed for inspection; its verifier is its check.

13.4.2 **One normaliser** serves the reading check and binding (§14.4): Unicode NFKC; typographic quotes and dashes folded to ASCII; no-break space to space; whitespace runs collapsed. A second, **squashed** comparison removes whitespace and hyphens. Punctuation is content: a dropped period diverges.

13.4.3 **text.** Designator fields are removed from the surface's head or tail; footnote marks and bullets are treated as the scope's conventions declare; the bodies are compared token by token (longest common subsequence), then squashed.

13.4.4 **cells.** Each cell of the reading must occur as a contiguous run in the row's column-aware words.

13.4.5 **tex.** Control words map to their symbols (`\sum` → ∑, `\times` → ×, the Greek alphabet), braces and script marks drop, a label the scope's designator names drops from the surface; the multisets of letters, digits and operators must agree. A cell written as TeX is compared the same way.

### 13.5 Rulings

13.5.1 A **ruling** is how the owner steers an instance. It never asserts, supports or refutes a claim, is never evidence, and is never served outside the owner plane or projected into the graph (§15.3). It changes only what the instance relies on and what it works on next.

13.5.2 Rulings are the lines of `rulings.jsonl`, each with its own `id`, written `by: owner` with a `date`:

```
{"id":"r7","pred":"seek","val":{"owes":["service_history"],"select":{"kind":"vehicle"},"why":"…"},"date":"2026-01-20","by":"owner"}
```

| ruling | on | effect |
|---|---|---|
| `distrust` | a testimony (`ath://<id>`); an op's output at a scope (`ath://<id>?<at>` with the op); a pass (`ath://<id>#<pass-id>`) | everything bound through it is held, and becomes demand to re-derive, re-read or re-acquire; a distrusted testimony stays in provenance, marked. It says *do not rely on this*, never *this is false* |
| `accept` | a finding: a reading-check divergence (a scope and the reading's `rev`) or a check finding | the finding is listed as known and no longer recurs; a re-read lapses an accepted divergence |
| `seek` | a selection (forms, kinds, origins, an entity), optionally the owed properties or readings wanted | creates demand for what it names, and makes it **relevant**: every artifact, scope and entity that meets it — at ingest, at signing — is reported as meeting it |
| `defer` | a demand item or a selection of them | orders the work after everything not deferred |
| `decline` | a demand item or a selection of them | removes it from demand: what is declined is not pursued |

13.5.3 `why` is the owner's note to themself. It is shown to the owner alone and is never evidence, never exported and never served on any other plane.

13.5.4 A ruling lives in the instance that makes it. An extension holds its base's `distrust` and `accept` rulings too — they correct what both rely on — but not its base's `seek`, `defer` and `decline`, which steer only the base's work. An extension's owner MAY rule on its base's artifacts, passes and testimony. Revoking a ruling removes its line.

13.5.5 Acquiring artifacts from outside, deleting, removing a copy from a store, moving an artifact between an extension and its base, repinning a base and changing the vocabulary are owner-gated verbs of the tool (§19), not rulings.

## 14. Entities and claims

### 14.1 Entities

14.1.1 An **entity** is a particular thing in the world — a purchase, a house, a person, a boat — named by a name (§5.3), its file `entities/<shard>/<name>.jsonl`. It is of one or more kinds (`is`), and carries one line per claim. Artifacts are evidence for an entity, never its identity.

14.1.2 An entity's file holds its passes as `pass` lines and every claim carries `pass`: every line in it was authored and verified.

```
// entities/tx/txn-corner-shop-48213.jsonl
{"pred":"pass","val":{"by":"reader-a","date":"2026-01-12","id":"p1","verify":"reader-b","vocab":"b3:5c1e0a9d77f3b210"}}
{"pred":"is","val":"transaction","pass":"p1"}
{"pred":"total","val":"42.10","ev":[{"anchor":"ath://a48bf844?bbox=0.36,0.69,0.27,0.03&text","grade":"authoritative","mode":"stated","quote":"42.10","reading":"b3:0de3a1c94b7e5f21"}],"pass":"p1"}
{"pred":"merchant","val":"ath://corner-shop","ev":[{"anchor":"ath://a48bf844?bbox=0.34,0.13,0.31,0.04&text","grade":"authoritative","mode":"stated","quote":"CORNER SHOP","reading":"b3:7a19c4e0d2b65f83"}],"qual":{"as":"CORNER SHOP"},"pass":"p1"}
```

14.1.3 Splitting an entity, merging two or renaming one is a verb (`entity split|merge|rename`, §19.5) that rewrites every reference in the instance at once. An extension cannot rename its base's entities; on a repin it is told of the base's.

### 14.2 Claims

14.2.1 A claim is `{pred, val, qual?, ev, pass}`: `pred` is a property (§11.2.4); `val` is a value of the property's range, or `ath://<name>` of an entity of the kind its range names; `qual.as` keeps the value as the bytes printed it.

14.2.2 Predicates with fixed meaning:

| predicate | meaning |
|---|---|
| `is` | the entity is of this kind |
| `same_as` | two entities are one; they merge the moment it derives `confirmed` |
| `supersedes` | an artifact or entity replaces another; anchors carry across as §7.8 says |
| `challenges` | names a claim by its identity and content hash, with evidence against it |
| `presence` | `none`: the thing is not attested where it would be |

### 14.3 Evidence

14.3.1 A claim carries `ev: []`. Each entry is authored once and bound by verify:

| key | meaning |
|---|---|
| `anchor` | `ath://<id>?<at>[&<aspect>]` — tight: the smallest scope the quote lies in, one cell of a table, never a region; a route through a container canonicalises to the constituent |
| `quote` | verbatim from the reading or surface the binding names; an elided composite (`…`) or a typographic re-take is refused; `prefix` and `suffix` disambiguate a repeated string and extend a long one |
| `grade` | the source's standing: `authoritative`, `direct`, `incidental` |
| `mode` | how the entry supports the value: `stated`, `inferred`, `reported`; `reason` is required when it is not `stated` |
| `reading` | the binding, stamped by verify (§14.4) |

14.3.2 A `stated` entry supports a string value only where the value is within its quote after normalisation; otherwise the claim is `inferred` with a `reason`.

### 14.4 Binding

14.4.1 `reading` is one of:

- `b3:<16 hex>` — a stored reading's revision;
- `derived:<op>@<version>[ <argument>]` — the surface op yields the quote's surface;
- `line:<pred>[ <field>]` — a value read off a `manifests` or `intrinsics` line at the anchor;
- `null` — held.

14.4.2 An entry is **bound** when its anchor resolves to a scope, its binding yields a surface there, and its quote (with prefix and suffix) is in that surface under the normaliser (§13.4.2), plain or squashed. It is **held** when its binding is `null`, when the revision it names no longer exists, or when it relies on a distrusted testimony, op output or pass (§13.5). It is **flagged** otherwise, with the reason.

14.4.3 Three links are checked separately: claim to reading (the quote is in the bound body), reading to bytes (the reading check), value to quote (the verifier's judgment).

### 14.5 Status, derived

| status | when |
|---|---|
| `confirmed` | a bound `authoritative` entry, or two bound `direct` entries from distinct artifacts, and no standing challenge |
| `provisional` · `inferred` · `reported` | the bar is not met; the mode of the best bound entry decides — `stated` gives `provisional` |
| `disputed` | a challenge stands |
| `conflicting` | a bound sibling claim disagrees on a `functional` property |
| `unsupported` | no bound entry — a hypothesis is a claim in this state |
| `refuted` | unsupported with an upheld challenge; it stays, so it is not proposed again |

### 14.6 Demand

Derived, never stored:

- a held entry is a reading owed over its unit;
- an unmet `owes` of an entity's kind is a search;
- an unsupported claim is an acquisition;
- a stale pass is a re-run;
- an unmet `expects` is a soft finding;
- a `seek` ruling demands what it names;
- an extension's minted term, or its disagreement with a base line, is demand on the base (§4.4).

The owner orders demand with `defer` and removes it with `decline` (§13.5); nothing else about demand is written. An absence the bytes print ("–", a missing row) is demand, not a defect.

## 15. Export

### 15.1 The markdown proxy

15.1.1 The proxy is an output, never a record and never a citation target. It walks the tree in `ord` and emits each scope through its form's `renders` rule, designators re-emitted from fields, every block prefixed by its `at`.

15.1.2 Its header names: the authority (the bytes); every pass and its vocabulary pin; the accepted divergences; the chrome; and the **remainder** — on an asserted tree, the words outside every scope and chrome; on a derived tree, the characters outside every unit and declared chrome, of the total.

15.1.3 It is lossless back to the bytes and never breaks on a new term.

### 15.2 Provenance

An artifact's provenance chain (§9.6) is exported beside the proxy on the owner plane, and on another plane only where its testimony belongs to an instance that plane serves.

### 15.3 The graph

15.3.1 Every term, record and entity line maps to one N-Quads statement and back, byte-identical; rulings are never projected. Subjects are `ath://<id>?<at>`, `ath://<id>` and `ath://<name>`; the vocabulary of the projection sits under the same scheme without an authority: the predicate `ath:p/<pred>`, the line's payload a literal typed `ath:json`, and the graph its authorship — `ath://<subject>#<pass-id>` for a pass, `ath:by/<op>` for an op, `ath:terms` for a term's lines.

15.3.2 A term's `aligns` IRIs are asserted as its class or property in the projection; `is` projects as `rdf:type`.

## 16. Planes and publication

16.1 Serving an instance serves it and everything it builds on, filtered by plane. The **public plane** serves the `public` instances of the chain and the claims whose derived status is `confirmed`. An **audience plane** serves those plus every instance whose tier the audience's grant names, under the same status filter unless the grant names another. The **owner plane** serves every instance of the chain, every status, the rulings, provenance, demand and every finding.

16.2 Read-only is normative. A consumer reads entities, materialises artifacts only for what the entities' claims cite, never cites a generated view, and pins the reproducibility tuple — the commit of every instance in the chain and the vocabulary pin — when it freezes a build.

16.3 A server re-reads the instances per request and holds no state of its own.

## 17. Checks

### 17.1 Record checks

A failing record check blocks a pass from signing.

| check | holds when |
|---|---|
| **unit** | every `reads_as` sits at a scope with a `manifests` whose form reads that aspect |
| **tree** | every `in` resolves to a scope; `ord` is contiguous from 0 per parent; there is no cycle; every non-physical scope is reachable from `whole` |
| **coverage** | on an asserted tree, the words outside every scope and chrome are listed; under `complete` they block |
| **citation** | every anchor resolves; every quote is in its bound surface; a bound revision that no longer exists is flagged |

### 17.2 Vocabulary use, forms, testimony and files

| check | holds when |
|---|---|
| **sorts** | `manifests` names a form; `is` names a kind; a claim's `pred` is a property, and its `val` fits the property's range |
| **per form** | `reads` is satisfied; required fields are present; designators match the surface under `where` and `pattern`; `expects` is met (soft); the form's `check` lines hold; the reading check per aspect; `matches` agrees with a stored root |
| **per testimony** | its root is a form refining `testimony`; it carries every field its origin form requires |
| **per file** | no undeclared field; no derivable value stored; no aspect outside `text`, `cells`, `tex`; sorted; pass references resolve; every pin known; `intrinsics` only by an op; no stale `intrinsics` (soft); every id and name resolves to one subject |

### 17.3 Form checks

A form's `check` lines are declarative checks over its scopes, composed from:

- `{"every": "<field>", "names": "<form>"}` — every value of the field names a scope of the form by designated address (a table of contents row names a heading);
- `{"contains": "<form>", "at_least": <n>}` — every scope of the form contains at least *n* scopes of the form named;
- `{"field": "<field>", "agrees": "intrinsics.<key>"}` — the field equals the intrinsic value.

### 17.4 Vocabulary checks

The vocabulary check refuses: a term whose `refines` chain reaches no root, or more than one; a predicate the term's sort does not carry; a `reads` value outside the four; a `derivation` that does not parse, names an unregistered op or carries an argument the op refuses; a selector the root family's language rejects; a `matches` without `mime`; an `owes` naming no property; a `range` naming neither a type nor a kind; a name shared by a term and an entity; a write at an identity a base's vocabulary holds; a `refines` cycle.

## 18. Custody

Custody keeps artifacts and testimony and finds them by BLAKE3. The repository names artifacts by id and never says where they reside; residence is the business of stores, an index and the policies an instance declares.

### 18.1 Guarantees

1. **A hash resolves or fails.** Given a BLAKE3, custody produces the artifact through whichever route holds it, or reports that none does. No caller names a store.
2. **Every read is verified.** The BLAKE3 is computed over the bytes as they stream; a mismatch fails that route and the next is tried. No driver is trusted.
3. **Residence is derived.** No line in the repository records where an artifact resides. The index is a belief about the stores, refreshed by inventory, transfer and verification.
4. **Automation only adds.** Custody copies and verifies on its own. It removes a copy only from a store declared evictable, and only after verifying, at that moment, that the artifact's policies hold without it (§18.6.3). Every other removal is an owner-gated verb.

### 18.2 Stores

18.2.1 A **store** holds artifacts and testimony. Each is declared in the instance as `stores/<name>.yaml`:

```yaml
id: 6b1f0c52-5d0e-4a8e-9c1e-2f0d6f9b2a71
driver: rclone
role: managed
tags: [ssd, online, country:ca, city:winnipeg]
encryption: client             # none | client | driver
capacity: 4TB                  # only where the driver cannot report it
evict: { above: 90% }          # only on a store that may shed copies (§18.6.3)
```

| field | meaning |
|---|---|
| `id` | a UUID, the store's identity on every host; written into the store itself, so a store is recognised wherever it is mounted |
| `driver` | how the store is reached (§18.3) |
| `role` | `managed` — content-addressed trees only custody writes, `artifacts/` and `testimony/`, laid out as its driver chooses; or `observed` — a tree that keeps its own names and paths, which custody reads and never writes |
| `tags` | free strings, meaningful only to policies; a `key:value` tag lets a policy count distinct values of `key` |
| `encryption` | `none`; `client` — custody encrypts before the driver sees the artifact; `driver` — the driver's own encryption |
| `capacity` | the size custody plans against when the driver cannot report one |
| `evict` | the fill level above which the store sheds copies its policies no longer need |
| `links` | on an observed tree: the link methods ingest may use to place an artifact in a managed store on the same filesystem, tried in order — `reflink`, `hardlink` (§18.5.3) |

18.2.2 How a host reaches a store is not the instance's: `$XDG_CONFIG_HOME/athenaeum/access.yaml` maps each store id to the driver's configuration on that host — a path, an rclone remote, a reference to credentials. Credentials never enter a repository.

18.2.3 Every host has a **local store**: a managed store at `$XDG_DATA_HOME/athenaeum/`, tagged `local` and declared evictable. Ingest writes new artifacts and their testimony there first.

18.2.4 An observed tree, like the local store, holds artifacts without persisting them: a file in it may be edited, moved or deleted by anyone. A policy counts no copy in an observed tree.

### 18.3 Drivers

18.3.1 A driver offers: `capabilities`; `inventory(since)` — the artifacts or files present, with sizes, from a given generation; `has(blake3)`; `get(blake3 | path) → stream`; `put(blake3, stream)`; `remove(blake3)`; `stat()` — used and free space where it can tell. A managed store's driver puts under a temporary name and renames once the hash is verified.

18.3.2 The registered drivers are `local` (a directory on this host) and `rclone` (any backend rclone reaches: object stores, SMB shares, Proton Drive, SFTP and the rest). A further driver is one module implementing the same operations.

### 18.4 The index

18.4.1 Each host keeps one index, at `$XDG_STATE_HOME/athenaeum/index.sqlite`, shared by every instance on the host. Per store and BLAKE3 it records the state — `claimed` (an inventory says so), `verified` (custody hashed it, with the instant) or `missing` (looked for and absent) — with the size and the inventory generation. For an observed tree it records each path with its size and mtime, and any link to a managed copy.

18.4.2 The index persists, because rebuilding it needs every store's inventory and, for verification, the artifacts themselves. Deleting it is always safe; custody re-inventories.

### 18.5 Observed trees and the scanner

18.5.1 An observed tree is inventoried by the **scanner**, run on the host where the tree's filesystem is local, so that hashing runs at disk speed and only the manifest crosses the network. Its identity model — `(dev, ino) → (size, mtime) → BLAKE3` — re-hashes nothing whose stat is unchanged; a rename is a new path on a known identity; hard links collapse to one hash; an interrupted scan resumes per file. The manifest is published by temp-then-rename at each generation, so a reader sees only whole generations. Its format is the scanner's own versioned contract.

18.5.2 For every file the scanner records what was observed — host, path, size, mtime, birth time, generation. That record is testimony the scanner prepares in advance; it enters the instance only when the file is ingested.

18.5.3 Ingesting a file from an observed tree writes its receipt and keeps the scanner's record as a testimony of it, and places the artifact in a managed store: by the first of the tree's `links` methods the filesystem supports, else by copy. A **reflink** is an independent copy-on-write clone. A **hardlink** shares the observed file's inode, so an edit made in place to the observed file changes the managed copy; verification then finds it corrupt and reconcile restores it from another copy. A linked copy shares physical storage with its source and is counted as one copy.

18.5.4 Custody reports, per observed tree: artifacts also held by a managed store (with how each is linked) — candidates for clean-up outside the instance; held artifacts held only there — at risk; files the instance does not hold — candidates for ingest.

### 18.6 Policies

18.6.1 A **policy** says how an instance keeps a selection of its holdings. Each is a file `policies/<name>.yaml`:

```yaml
select: { origin: agent-session }
require:
  - copies: 2
    where: { not: [local] }
    distinct: city
  - copies: 1
    where: { all: [ssd] }
confine: { all: ["country:ca"] }
verify: 90d
```

18.6.2 **Selection** matches labels the instance computes for each artifact and testimony it holds: its root form and that form's `refines` chain (`form`), the origin forms of its provenance (`origin`), the kinds of the entities that cite it (`kind`), its class, the instance's tier (`tier`), its mime and its size; `testimony: true` selects testimony. Every policy whose selection matches applies; an extension's policies apply together with its base's.

18.6.3 **Requirements.** A requirement holds when at least `copies` copies sit on stores whose tags satisfy `where` (`all`, `any`, `not`), spread across that many distinct values of the `distinct` key. A copy counts once per physical copy — routes through containers count (a constituent is held wherever its container is), linked copies sharing storage count once, observed trees and missing copies never count. `confine` restricts every copy to stores whose tags satisfy it; a copy outside is a finding and reconcile never places one there. `verify` is how recent a verification a copy needs to count; an older one is a finding and is re-verified.

18.6.4 Every instance carries the **default policy**: every artifact and testimony it holds has at least one copy on a managed store not tagged `local`. One held only in the local store or an observed tree is **unpersisted**.

### 18.7 Reconcile

18.7.1 **Status** lists every finding — unpersisted, below a requirement, outside a confinement, verification overdue, a store over capacity. **Plan** lists the actions that would resolve them. **Reconcile** performs them: it copies from the cheapest verified route to stores chosen by requirement, confinement, free space and declared cost; it re-verifies what is overdue; and it evicts from an evictable store above its fill level only copies whose policies hold without it, verified at that moment. Reconcile is idempotent and resumable: an interrupted run leaves every completed transfer in place and none half-written.

18.7.2 A store that is unavailable — a removable disk unplugged, a remote unreachable — is skipped and reconciled when it next answers.

### 18.8 Resolution

18.8.1 Resolving a BLAKE3 tries the routes the index knows, cheapest first: the local store, other managed stores by declared cost, observed trees, the constituent route — the container resolved, then the constituent extracted — and the stores of every base the instance builds on. The first route whose bytes verify wins; if none does, resolution fails.

18.8.2 Resolution reports how it succeeded: the route taken, nested through containers, and every other residence the index knows, with its state and the age of its verification:

```
b3:9f2c…  ← path=IMG_0042.HEIC in b3:41aa… (zip)
            ← store nas-media [hdd, city:winnipeg]  verified 3d
   also: offsite [object, city:toronto] verified 41d · local evicted
```

18.8.3 An artifact resolved from a store other than the local one MAY be kept in the local store as a cache copy.

### 18.9 The custody daemon

Each host MAY run one custody daemon, `athd`, serving every instance on the host. It runs reconcile on a schedule and on events — an ingest, a store becoming available, a change in an observed tree — keeps a resumable transfer queue with bandwidth limits and back-off, and is the single writer of the host index while it runs. Everything it does is a custody verb any caller can run by hand (§19.5); without it, those verbs take the index lock themselves.


## 19. The tool

### 19.1 Profiles and tiers

19.1.1 Every verb has a tier: `read`, `write` or `admin`. A caller runs under one profile: `owner` (admin), `agent` (write) or `reader` (read). A caller at a terminal is `owner`; a caller under an agent or a script is `agent`. A profile may be narrowed by flag or environment, never widened. A verb above the caller's tier does not exist for it.

19.1.2 Every mutating verb needs an **actor**: `ATH_ACTOR`, or the login name at a terminal. Without one the verb is denied. The actor is recorded in the receipt, in staging and in the history.

### 19.2 Loading an instance

19.2.1 The tool loads an instance with every base it builds on, at their pinned commits, and writes only the instance it was pointed at, under that instance's locks.

19.2.2 It MUST register every op the loaded vocabulary names (§11.6) and, for every mime, an intrinsics op at least as new as any `intrinsics` line in the chain. A tool that falls short refuses to load (configuration error) and names what it lacks; it never writes a `intrinsics` line older than one already stored.

### 19.3 Writes

19.3.1 Every write is atomic. An artifact or a testimony is written under a temporary name, verified against its BLAKE3 and renamed into place; a line file is rewritten under a temporary name and renamed. A verb that is interrupted leaves the instance as it was, or with every write it completed whole. A delivered file is placed in the local store by copy, or from an observed tree by link (§18.5.3); the tool never removes it from where it was delivered.

19.3.2 Mutating verbs take named locks in the instance's host state (§5.6); a held lock is `busy`. Every mutating verb appends its actor, arguments and outcome to the instance's history there.

### 19.4 Envelope and exit codes

19.4.1 With `--json`, every verb prints one envelope: `{ok, cmd, version, elapsed_ms, data | error}`. A verdict — check findings, failed bindings — is an `ok` envelope with exit code 1, never an error.

| code | meaning |
|---|---|
| 0 | ok |
| 1 | a verdict: the verb ran and its answer is no |
| 64 | usage |
| 66 | not found: a subject, file or instance that does not exist |
| 70 | internal: an unexpected failure |
| 71 | external: a tool outside the tooling failed |
| 73 | conflict: a write the contract refuses — identity, shadowing, an undeclared field, an unadmitted testimony |
| 75 | busy: a lock is held |
| 77 | denied: the caller's profile or actor may not run this |
| 78 | config: `athenaeum.yaml`, a base, a store or policy declaration, the host's access file or the vocabulary is broken, or the tool cannot serve the chain (§19.2.2) |

### 19.5 Verbs

| verb | tier | contract |
|---|---|---|
| `instance init [--extends <path>]` · `instance show` · `instance check` | write · read · read | init writes `athenaeum.yaml` and the empty directories — for a standalone instance with the terms §11.9 names, for an extension pinned to its base's current commit; show prints the instance and what it builds on; check verifies the chain, its pins and its configuration |
| `instance repin` | admin | moves the base pin to the base's current commit, rewrites ids that now collide (§7.1.3), and reports what the move makes stale (§4.3) |
| `instance reshard` | admin | moves files to the shard widths `athenaeum.yaml` declares (§5.2); no line changes |
| `ingest <file…> [--testimony <file>…]` | write | sniffs; admits or refuses delivered testimony before anything is placed; places the artifact and its testimony in the local store; writes the receipt; updates the holdings. Writes nothing to the repository |
| `holdings` · `holdings rebuild` | read · write | what the instance holds; rebuild the holdings from the receipts in the stores (§5.7) |
| `intrinsics sweep [--stale]` | write | writes superseding `intrinsics` lines where the op version is older than the tool's |
| `resolve <anchor> [--trace]` | read | the artifact, the surface or the reading at an address; `--trace` reports the route (§18.8.2) |
| `tree <subject>` | read | the scope table in `ord`, derived or stored; a designated or positional address to its intrinsic `at` |
| `provenance <subject>` | read | the provenance chain (§9.6) |
| `show <subject>` · `sort <subject>` | read · write | a subject's lines across the chain; rewrite a file in canonical order |
| `pass open` · `stage` · `sign` · `abandon` · `show` | write (show: read) | §13.1–§13.2 |
| `propose audio.speech@1 <subject>` | read | the proposal op's candidate scopes (§10.5) |
| `readings <subject>` | read | the reading check's findings for an artifact (§13.4) |
| `rule distrust\|accept\|seek\|defer\|decline <target> [--why <text>]` · `rule revoke <id>` · `rulings` | admin · admin · read | write or remove a ruling, confirmed at a terminal; list the rulings and what each currently affects |
| `relevant [<subject>]` | read | the `seek` rulings an artifact, scope or entity meets |
| `entity split` · `merge` · `rename` | write | §14.1.3 |
| `verify [<subject>…]` | read | bindings, status, demand, stale passes |
| `check [<subject>…] [--all]` | read | §17 |
| `vocab list` · `show` · `rules` · `pin` · `check` | read | the terms, a term's lines, a scope's effective rules, the pin, §17.4 |
| `export markdown <subject>` · `export graph [<subject>]` | read | §15 |
| `serve` | read | the planes over HTTP (§16) |
| `store add <name>` · `store list` | write · read | declare a store and write its id into it; the stores and their state |
| `custody inventory [<store>]` · `custody verify [<store>]` | write | refresh the index from inventories or scanner manifests; re-hash copies |
| `custody status` · `custody plan` | read | findings; the actions that would resolve them (§18.7) |
| `custody reconcile` | write | perform the plan: copy, verify, evict (§18.7) |
| `custody where <blake3>` · `custody report <store>` | read | every known residence of a hash, whether or not the instance holds it; an observed tree's report (§18.5.4) |
| `custody remove <blake3> --from <store>` | admin | remove one copy, refused unless the policies hold without it, verified at that moment (§9.7) |
| `log` · `whoami` | read | the history; the caller's profile, actor and instance root |
