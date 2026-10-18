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
2. **The tooling knows formats, never conventions.** An op sniffs a mime, records what the format's own specification defines, addresses the bytes on the axes the format has, decodes the surface of structured data, offers hints over rendered content, and exposes the format's own nodes — an element, a MIME part, a JSON value, an archive entry, a `data:` URI. It never names a term and never decides what a node is: that a row is a header, that a `>` line is a quote, that a repeated line is a running header, that an element is a post. A scope below `whole` exists only where the vocabulary or an author puts it. What a renderer draws — a page, a web page, a picture, a sound — is content only once an author has read it (§8.3). A new kind of thing is a vocabulary edit; a new format is one op module.
3. **Authors judge; the tooling assists.** Every structure, reading and claim that can be wrong is written by an author and verified by a second. The tooling addresses, decodes, selects, checks and reports; it never writes a claim of its own.
4. **Nothing is written until something is said.** Ingesting an artifact places it and its testimony in custody and writes nothing to the repository. An artifact's record comes into being with the first judgment about it; an entity's file with the first claim.
5. **Addresses are intrinsic.** A scope is named by coordinates in the bytes — page and box, byte range, row and column, time, constituent path — never by a transform, a parser's tree or an identifier.
6. **The vocabulary is the recipe.** Forms are structure, shapes converge artifact families onto them, and kinds are meaning. What a form expects — fields, reading aspect, children, render form — rides on the form; where a family's forms lie rides on its shape. What an entity owes rides on its kind. An author pins the vocabulary it read against by hash; nobody chooses a recipe.
7. **Derived, never stored.** Class, status, demand, binding state, chrome, staleness, provenance, holdings, every non-intrinsic address and the export are computed at read time (§12). A stored copy of a derivable thing is a defect.
8. **Nothing lossy enters a record.** A reading is a transcription of what the artifact shows, answerable to its rendering — never a summary, a description, a paraphrase or a characterisation. Where a scope has no lossless transcription, the record marks its address and stops. What a scope shows about the world is a claim about an entity, cited to the scope. Where an artifact came from is testimony, never a line of its record. A record contains nothing a reader cannot check against the artifact itself.

## 3. Terms

| term | meaning |
|---|---|
| **instance** | one repository — its corpus, its graph, its store and policy declarations and its rulings (§4): **standalone**, or an **extension** of a **base** it builds on |
| **corpus** | an instance's forms, shapes and records: how its artifacts are organised and what they say |
| **graph** | an instance's kinds, properties and entities: what its artifacts show about the world |
| **artifact** | bytes, identified by their BLAKE3; the subject `ath://<id>` (§7.1) |
| **id** | an artifact's short identifier: the first 8 hex digits of its BLAKE3, 16 where 8 collide (§7.1) |
| **container** | an artifact whose format holds whole files of its own |
| **constituent** | an artifact held whole inside a container; its own subject |
| **testimony** | an artifact a producer emitted about other artifacts — where, when, by what, why they were found (§9) |
| **receipt** | the testimony the tooling writes for every ingest (§9.3) |
| **record** | the document of judgments about one artifact, written once something is said about it: its readings and, once formed, its tree (§8) |
| **intrinsics** | the key of a record that holds what the artifact's format defines about its bytes (§8.1) |
| **scope** | a region of an artifact named by an intrinsic address `at` |
| **term** | an entry of a vocabulary: a **form** or a **shape** (the corpus's), a **kind** or a **property** (the graph's) (§11) |
| **form** | a structural unit — a page, a heading, a paragraph, a table, a row, a line, a message; never what content means (§11.1.2) |
| **shape** | the shape one family of artifacts shares, and where its forms lie (§11.1.3) |
| **kind** | what an entity is: a transaction, a residence, a person, a vessel |
| **property** | what can be said of an entity: a total, an address, a vessel's name |
| **rendered** · **structured** | the two classes of format: one whose content is what a renderer shows and an author reads; one whose bytes are the content, parsed exactly (§10.4) |
| **tree** | a formed record's scopes, nested in reading order (§8.4) |
| **stage** | how far a record has come: unread, read, transcribed, formed (§8.5) |
| **unit** | a scope whose form `reads` an aspect: the grain of a reading |
| **reading** | an author's transcription of what a region of a rendered artifact shows, under one aspect, at its address (§8.3) |
| **surface** | the text the parse of a structured artifact gives at a scope; what a quote into it is checked against (§10.5) |
| **hint** | an op's guess at what a region of a rendered artifact shows, offered to a reader and relied on by nothing (§10.6) |
| **entity** | a particular thing in the world, of one or more kinds, the subject of claims (§14) |
| **name** | the identifier of a term or an entity (§5.3) |
| **claim** | a line asserting the value of a property of an entity, carrying evidence |
| **evidence** | an anchor and a quote into an artifact supporting a claim, bound by verify; its standing is derived (§14.4.4) |
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

- a record is never overridden: an extension's record of an artifact its base has a record of adds readings at addresses the base's lacks, and a tree only where the base's has none, and MUST NOT write at an address or key its base holds with different content; artifacts the base holds are the same subjects, and ingesting them again in the extension adds a receipt and testimony there and nothing else;
- an extension's entity line wins over its base's at the same identity;
- an extension adds terms and lines to the vocabulary, and MUST NOT write at an identity the base's vocabulary holds;
- a disagreement with a base line, and a term the extension mints, are demand on the base (§14.6).

4.5 Every line an instance holds carries the instance's `tier`; no line declares its own. An instance MUST NOT be `public` unless its base is.

## 5. Files

5.1 An instance's repository holds tracked content and nothing else:

```
<instance>/
├── athenaeum.yaml
├── corpus/
│   ├── forms/<name>.jsonl             structural units (§11)
│   ├── shapes/<name>.jsonl            artifact families and where their forms lie (§11)
│   └── records/<shard>/<id>.yaml      judgments about artifacts (§8)
├── graph/
│   ├── kinds/<name>.jsonl             what an entity is (§11)
│   ├── properties/<name>.jsonl        what can be said of one (§11)
│   └── entities/<shard>/<name>.jsonl  entities and their claims (§14)
├── stores/<name>.yaml                 §18.2
├── policies/<name>.yaml               §18.6
└── rulings.jsonl                      §13.5
```

5.2 **Shards.** A record's `<shard>` is the first *n* hex digits of its artifact's id; an entity's is the first *n* characters of its name. `athenaeum.yaml` declares *n* per directory; absent, both take 2. Forms, shapes, kinds and properties are never sharded. Changing a width is `instance reshard` (§19.5), which moves files and changes no line.

5.3 **Names.** A term or an entity is named by a **name**: lowercase letters, digits and hyphens, starting with a letter or digit, never consisting of hex digits alone. A name is unique within its directory. Entities and kinds — the things a consumer asks the graph about — share one name space and are the subjects `ath://<name>`; artifacts are `ath://<id>`. Forms, shapes and properties are named within their own vocabularies and referred to by bare name (`"form":"heading"`, `"pred":"total"`); the graph projection gives them IRIs of their own (§15.3).

5.4 **The file is the subject.** A line in a term's or an entity's file is about that name, and a record is about its artifact; nothing repeats its subject.

5.5 **One-way reference.** The graph cites the corpus; the corpus never names the graph. A record never names an entity, a testimony or a container: those relations are derived (§12). A form or a shape never names a kind or a property.

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

6.1.1 A term, an entity and a ruling are files of lines, one JSON object per line; a record is one document (§8). A line carries `pred` and `val`; a ruling also carries an `id` (§13.5); a claim adds `qual` and `ev` (§14).

6.1.2 Every entity and ruling line carries exactly one authorship — `by` or `pass`; a term line carries none, since the vocabulary is authored by its instance's history. In a record, every reading, scope, chrome rule and stored shape carries `pass` (§8).

6.1.3 A line is one statement with one provenance, and maps to N-Quads statements (§15.3).

```
// corpus/forms/heading.jsonl
{"pred":"reads","val":"text"}
// graph/entities/ti/tide-table-02.jsonl
{"pred":"version","val":"02.1","ev":[{"anchor":"ath://5e6e497d?page=1&bbox=0.1429,0.6906,0.0901,0.0087&text","mode":"stated","quote":"Version 02.1","reading":"b3:aae7b6bb9c216abb"}],"pass":"p1"}
```

### 6.2 Authorship

6.2.1 `by` names an op as `<name>@<version>`, or `owner`. `pass` names a pass by its id: a pass line in the same entity file, or an entry of the record's `passes` (§13.1).

6.2.2 A pass is itself the authorship of what names it and carries none of its own.

6.2.3 An entity or ruling line, or an entry of a record, with no authorship, with both, or with a `pass` that does not resolve in its file MUST be refused at write.

### 6.3 Identity

6.3.1 A line's identity is the key a second line collides on. A write at an existing identity with different content replaces the line; a write with the same content is a no-op.

| line | identity |
|---|---|
| a claim | (pred, val, qual) — evidence accrues on the one line |
| `is` | (pred, val) |
| `pass` in an entity file | (pred, id) |
| a ruling | (id) |
| a term line | (pred) for a single-valued predicate; (pred, name) for a repeatable one, where the name is the value's `name`, `col`, `selector` or `form`, else the whole value |

A record's identities are its addresses and ids (§8.6).

6.3.2 The repository's history is the record of every replacement; no line records one.

### 6.4 Files and canonical form

6.4.1 One line per claim or term statement. A file is sorted by identity; nothing depends on line order. The union of an extension with its base, and a merge, are line-set unions.

6.4.2 The canonical serialisation of a line is compact JSON, LF-terminated, non-ASCII characters unescaped, with its keys in a fixed order: `id`; then `pred`; then every other key in code-point order; then `ev`; then the authorship (`by` or `pass`) last. Nested objects' keys are in code-point order; arrays keep their stored order. Two lines are the same content when their canonical serialisations are equal. Every hash this document defines over JSON — a revision of `cells`, a pin — is taken over this form.

### 6.5 Revisions

A reading's **revision** is `b3:` followed by the first 16 hex digits of the BLAKE3 of its body under one aspect — a string as UTF-8, `cells` as its canonical JSON. It is computed, never stored; evidence that binds a reading names it (§14.4), so a re-read that changes the body is seen.

## 7. Artifacts and addresses

### 7.1 Artifacts and their ids

7.1.1 An artifact's identity is the BLAKE3 of its bytes and nothing else: no URL, name, path or producer key takes part in it. New bytes are a new artifact. The same bytes met again are the same artifact; the encounter adds testimony (§9) and nothing else.

7.1.2 Within an instance an artifact is written by its **id**: the first 8 hex digits of its BLAKE3. Its subject is `ath://<id>`; its record, when it has one, is `corpus/records/<shard>/<id>.yaml`. Testimony and the format's constituent lists carry full hashes; everything tracked in the repository carries ids.

7.1.3 Where two artifacts the instance holds share their first 8 digits, the one received first (by its receipt, §9.3; a constituent by its container's) keeps the 8-digit id and every later one is written with 16. An extension defers to its base: if a repin brings a base artifact onto an 8-digit id the extension already uses for another artifact, the repin rewrites the extension's lines to give its own artifact 16 digits. Should 16 digits collide, the full hash is the id.

7.1.4 A reference that names an id resolves to exactly one artifact or is flagged.

### 7.2 Containers and constituents

7.2.1 A **container** is an artifact whose format holds whole files of its own: an archive entry, a package's documents, a message's parts, a mailbox's messages, the payload of a `data:` URI in markup. Which formats are containers, and how their constituents are named, is the format's definition (§10.3).

7.2.2 A container's constituents — per constituent, its `path` in the format's own terms, its BLAKE3, and the fields the format defines for it (a filename, a mediatype, a Message-ID) — are a fact of the container's bytes. Every constituent is its own artifact, addressable and resolvable from the moment its container is ingested, and the instance holds it because it holds its container.

7.2.3 Which containers hold an artifact is derived from their constituents (§12). Cite the constituent, which outlives the package.

### 7.3 The intrinsic address — `at`

7.3.1 `at` is the only address stored and the only address an anchor carries. Its axes are the artifact's format's (§10.4.3). Every axis is a coordinate in the bytes as stored, with no transform.

| axis | formats | meaning |
|---|---|---|
| `whole` | every artifact | the artifact: where the record's whole-level keys apply (§8.2), and the root of its tree |
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

- **Positional**: the path of positions from the root of the tree down to the scope, available once the record is formed.
- **Designated**: the path of designators the bytes themselves print — `?sec=5&para=6`, `?eq=1`, `?post=4`, `?col=Currency`, `?ch=2&fig=1` — available where a form declares a designator field (§11.2).

7.6.2 The resolver maps either to an `at` through the tree: scopes' forms, fields and positions. A later designator key narrows to the earlier key's scopes' descendants, and to what their boxes contain. A designator field whose pattern has a capture answers to the capture as well as the whole value: `num: "3."` under `^(\d+)\.$` answers `sec=3`.

### 7.7 Physical addressability

A page the document has, a row the parse holds and a cell within such a row are regions an anchor may name even where no reading or scope is at them.

### 7.8 Re-capture and moved scopes

7.8.1 A re-capture is a new artifact. A `supersedes` claim relates the two (§14.2); an anchor carries across where the body at the same intrinsic address still holds its quote, and is otherwise held (§14.4).

7.8.2 A reading is at its address and nowhere else. A structure correction touches no reading: a re-formed scope sits at a different address and reads the reading there. A reading at a wrong address is retired and written again at the right one; an anchor into the retired reading is held until verify finds the same revision at the new address and reports the anchor to move.

## 8. Records

### 8.1 What a record is

8.1.1 A record is the document of judgments about one artifact, and the cache of its intrinsics: `corpus/records/<shard>/<id>.yaml`. It is written with the first judgment about the artifact; an artifact nobody has said anything about has no record, and its intrinsics, structure and provenance are derived on demand.

8.1.2 What a record holds depends on the class of the artifact's format (§10.4):

- for a **rendered** artifact — a page, a web page, a picture, a recording — the content is what the rendering shows, and no parse gives it. The record holds **readings**, an author's transcriptions of regions of the rendering at intrinsic addresses, and, once the artifact is formed, a **tree** of scopes over those regions;
- for a **structured** artifact — a sheet, a JSON document, a vCard, a message, an archive — the parse is the reading and the shape is the structure (§11.7). The record holds at most the intrinsics cache and a stored choice of shape; a reading or a scope on a structured artifact is a check failure (§17.1).

8.1.3 **Readings and structure are separate.** A reading is identified by its address and never moves; a scope of the tree sits at a reading's address and reads it. Forming, re-forming or correcting the tree touches no reading, so evidence bound to a reading survives every change of structure.

### 8.2 The document

8.2.1 A record is one document with these keys, in this order:

| key | holds |
|---|---|
| `intrinsics` | what the artifact's format defines about its bytes: mime, size, encoding, page count, dimensions, duration, the metadata the format specifies, and a container's constituents (§10.2). Nothing a producer asserts. A cache: `op` names the intrinsics op and its version; a value by an older version than the tool's is **stale** (§12) and an intrinsics sweep rewrites it |
| `shape` | a stored choice of the artifact's shape, overriding the one `matches` derives (§11.4.3): `{name, pass}` |
| `chrome` | rules a pass declares for what is chrome in this artifact, each in the grammar of a shape's `chrome` line (§11.2.3) with its `pass`; applied together with the shape's (§8.4.6) |
| `passes` | the passes over the artifact, by id: `{by, verify, vocab, date, note?, with?}` (§13.1) |
| `complete` | the attestations of completeness, each the id of the pass that made it: `readings`, `structure` (§8.5) |
| `readings` | the readings, by address (§8.3) |
| `scopes` | the tree (§8.4) |

8.2.2 **Encoding.** A record is YAML, written only by the tool, in one style: the keys above in that order; a scope's keys as `form`, `at`, its fields in code-point order, `pass`, `scopes`; a reading's keys as its aspects in code-point order, then `pass`; a multi-line body as a literal block scalar; every scalar YAML would read as anything but a string, quoted. On load every field takes the type its form declares and every body is a string, or a list of lists of strings under `cells`; a document that does not parse, or a key the record's grammar lacks, is refused. Two records are the same content when their documents are equal.

### 8.3 Readings

8.3.1 A reading is an author's transcription of what the rendering shows in one region, under one **aspect**: `text` (print and speech), `cells` (a grid: a list of rows, each a list of cell strings), `tex` (mathematics). `readings` maps an intrinsic address to `{text?, cells?, tex?, pass}`: one entry per address, one body per aspect, signed by one pass. A re-read replaces the entry.

8.3.2 **Readings are formless and flat.** A reading has no form, no field, no parent and no order; its region may overlap another's (a paragraph and one line within it). What a region *is* belongs to the tree (§8.4). A reading is citable the moment it is signed, by its address and its revision (§6.5).

8.3.3 **Readings are written on demand.** A reader transcribes the region a claim needs and no more, and the record is created by the first. Nothing requires an artifact be read further than anyone has needed; a receipt photograph that was read for its total is a complete piece of work.

8.3.4 **Faithful to the rendering.** A reading transcribes what the rendering shows — the page as drawn, the web page as a browser lays it out, the pixels, the speech — typo included, and with everything printed in the region: a leading "5.", a bullet, a footnote mark. The bytes are consulted only through the rendering and the hints the tooling offers (§10.6); a reading is never a copy of a hint. A correction of the source is a claim with `mode: inferred` or a `challenges`, never a silent fix.

8.3.5 **Nothing lossy.** A reading is never a summary, a description, a paraphrase or a characterisation. A region with no lossless transcription — a photograph of a harbour — has no reading; anything said about what it shows is a claim anchored at its address with no quote and `mode: inferred`. Where such a region carries print or speech, the reader reads the sub-regions that carry it.

8.3.6 **Reading an image is reading.** An author looks at the pixels of a region and transcribes what is printed there, exactly as it reads any other region. No op transcribes an image. A PDF page is read as its rendering; the words the format draws are a hint to the reader (§10.6.3), and a page whose only text is a hidden layer under an image is read like any other.

### 8.4 The tree

8.4.1 A formed record holds one tree. `scopes` lists the top-level scopes in reading order; each scope is `{form, at, <fields>, pass, scopes?}`. A scope's parent is the scope whose `scopes` lists it, and its order is its position there; nothing references a parent, and the root — `whole` — is not a scope.

| key | holds |
|---|---|
| `form` | the form the scope is (§11.2.2), or a list where it is several; only forms appear here |
| `at` | its intrinsic address — a union where the scope spans regions (§7.3.2) |
| fields | the fields its forms declare, verbatim; an undeclared field is refused at write |
| `pass` | the pass that signed it |
| `scopes` | its children, in reading order |

8.4.2 **Physical regions are addresses, never scopes.** A page, a column, a row of a sheet is an axis of `at`; the tree holds logical scopes only. A cover page is a `cover-page` at `page=1` with its labels beneath it; the page itself is nowhere in the tree.

8.4.3 **A scope reads at its address.** A scope whose form `reads` an aspect has, at its own `at`, a reading under that aspect, which is its text; a scope whose form reads `none` has no reading of its own, and its text is its descendants' in order. A reading **lies in** a scope when its address is the scope's or is within the scope's `at` (§7.4); containment is by the scope's own address, never an ancestor's.

8.4.4 **Designators are structure.** A leading "5.", a right-margin "Equation (1)", a "#4" on a post are fields the forming pass fills verbatim as printed. A designator its form places `leading` or `trailing` is part of the reading and is removed from its head or tail wherever the scope is rendered or compared; one placed in the `margin` or in a descendant form lies outside the reading's body. Deciding that "2." is a number and not a sentence is a judgment, written by the pass that forms the scope.

8.4.5 **A field the address determines is derived.** A field a form declares `derived` (a page's number) is never stored.

8.4.6 **Chrome is derived by a declared rule.** Running headers, page numbers, navigation: the shape's `chrome` lines and the record's `chrome` key name what makes a run chrome (§11.2.3). The tooling applies the rules and has none of its own. Chrome is never a scope and never read; it is listed in the export header and stored nowhere.

8.4.7 **A tree is signed whole.** A forming pass stages for as long as it takes and signs once, over the whole artifact: its signature writes any reading the tree still needs and attests `complete.structure` (§8.5). A partly formed artifact is a staged pass, never a record. Re-forming replaces the tree whole, under a new pass.

### 8.5 Stages

8.5.1 A record's **stage** is derived from what it holds and attests, and is never stored:

| stage | the record holds | citable | what it gives beyond the bytes |
|---|---|---|---|
| **unread** | nothing: no record | nothing. A rendered artifact has no text until someone reads it | — |
| **read** | readings at some addresses | every read region, by address and revision | what was looked at is transcribed once and pinned |
| **transcribed** | readings that cover the artifact; `complete.readings` | every region of the artifact | the whole of what the rendering shows, in one place: search, a transcript in address order, "is this mentioned anywhere" |
| **formed** | the tree; `complete.structure` | all of that, and every scope by its designated and positional address | fields, conventions, chrome and the remainder, section closure, the markdown proxy, the per-form checks |

8.5.2 **Readings are complete** when the pass attests it. Where the format gives a hint (§10.6), the words of the hint outside every reading and chrome are listed as an advisory; where it gives none, the attestation stands alone, and the verifier is its check. The attestation lapses when a reading is retired.

8.5.3 **Structure is complete** when every reading lies in a scope, every scope that reads has its reading, and the pass attests it; the hint's words outside every scope and chrome are listed as an advisory. Formed implies transcribed. The attestation lapses on any change to the tree.

8.5.4 Until a record is formed, nothing about its artifact is addressed by a form: designated and positional addresses, fields, conventions and the per-form checks exist only in the tree. A read or transcribed record is cited at intrinsic addresses alone.

8.5.5 A structured artifact is at no stage: its parse is its reading and its shape its structure, from the moment it is ingested.

### 8.6 Identity

A reading's identity is its address; a scope's is its address, which is unique across the tree; a `chrome` rule's is its value; a pass's is its id. A write at an existing identity with different content replaces the entry; a write with the same content is a no-op; the repository's history is the record of every replacement.

```yaml
# corpus/records/c1/c1d0e9f2.yaml — a photograph of a sign, read in full: transcribed, not formed
intrinsics: {op: jpeg.intrinsics@1, mime: image/jpeg, bytes: 47268, width: 900, height: 420}
passes:
  p1: {by: reader-a, verify: reader-b, vocab: b3:5c1e0a9d77f3b210, date: 2026-01-12}
complete: {readings: p1}
readings:
  bbox=0.0667,0.1786,0.6022,0.1548:
    text: RETURNS ONLY
    pass: p1
  bbox=0.0667,0.4643,0.4556,0.1024:
    text: Bay 12 - Depot 7
    pass: p1
  bbox=0.0667,0.6976,0.6467,0.1071:
    text: No parking 7am to 6pm
    pass: p1
# that this is a loading-bay sign, and that bay 12 belongs to depot 7, are claims of entities (§14), cited here
```

```yaml
# corpus/records/9f/9f2c1a3b.yaml — a formed excerpt: the heading reads the reading at its own address
readings:
  page=3&bbox=0.1192,0.6933,0.4851,0.019:
    text: 5. Baseline emissions
    pass: p1
  page=3&bbox=0.1192,0.6102,0.7612,0.071:
    text: |-
      Baseline emissions are the emissions that would occur in the absence of the
      project activity, estimated for each lamp type k in year y as
    pass: p1
  page=4&bbox=0.2842,0.3844,0.572,0.0293:
    tex: Q_{L,k,y} = \sum_{i} N_{i,k} \cdot P_{i,k} \cdot O_{y}
    pass: p1
scopes:
  - form: heading
    at: page=3&bbox=0.1192,0.6933,0.4851,0.019
    level: 1
    num: "5."
    pass: p2
    scopes:
      - form: paragraph
        at: page=3&bbox=0.1192,0.6102,0.7612,0.071
        pass: p2
      - form: equation
        at: page=4&bbox=0.2842,0.3844,0.572,0.0293
        label: Equation (1)
        pass: p2
```

```yaml
# corpus/records/7a/7a3e0c11.yaml — a structured artifact: a sheet whose shape a pass chose; nothing is read
intrinsics: {op: csv.intrinsics@1, mime: text/csv, bytes: 412, encoding: utf-8, rows: 13, columns: 3, delimiter: ",", bom: false}
shape: {name: headed-sheet, pass: p1}
passes:
  p1: {by: reader-a, verify: reader-b, vocab: b3:5c1e0a9d77f3b210, date: 2026-01-12}
```

## 9. Testimony

### 9.1 What testimony is

9.1.1 Where an artifact was found, when, by what and why is not a fact of its bytes and cannot be checked against them. It is **testimony**: a snapshot a producer made, irreplaceable because the moment is gone, and never a line of a record.

9.1.2 Testimony is itself an artifact — a capture sidecar, an export's own manifest, the tooling's receipt — kept verbatim. Its identity is its BLAKE3. It is held in custody beside the artifacts, in each store's `testimony/` tree, under the same policies (§18.6), and never in the repository.

9.1.3 **Testimony carries its own links.** A testimony names, in its own bytes and by full hash, the artifacts it is about; nothing else records the link. A receipt names its artifact and the testimony delivered with it (§9.3). A producer's testimony that names no hash is linked by the receipt that delivered it.

9.1.4 A testimony cannot be edited, because its bytes cannot change. A mistaken testimony is answered by a later one and, where the owner will not rely on it, by a `distrust` ruling (§13.5).

9.1.5 Testimony is evidence, not knowledge. It holds no claim and has no status. A claim about where or when something was found or published cites the testimony by an ordinary anchor into its bytes; its standing, like any evidence's, is derived (§14.4.4).

### 9.2 Delivery

9.2.1 Testimony arrives with the artifact it describes: beside it as `<file>.testimony.<ext>`, or named explicitly at ingest. It is kept exactly as delivered.

9.2.2 A testimony describing a container describes the container only; its constituents inherit it by derivation (§9.6).

### 9.3 The receipt

9.3.1 Every ingest writes one testimony of the tooling's own, the **receipt**:

```json
{"actor":"reader-a","artifact":"9f2c1a3b…","instance":"0f4c2a8e-7b1d-4e5a-9c3f-6d2e8b1a4c70","name":"statement-03.pdf","received":"2026-01-12T09:14:03Z","testimony":[{"hash":"41aa07d2…","name":"statement-03.pdf.testimony.yaml"}]}
```

— the instance it was ingested into, who handed the artifact in, the instant, the name it arrived under, the artifact's full hash, and the full hash and delivered name of every testimony delivered with it. Testimony is not itself receipted: the receipt covers it, so every artifact has at least one testimony and the chain stops at one.

9.3.2 The receipt is the only testimony the tooling prescribes, and it knows the receipt's shape itself; no vocabulary declares it.

9.3.3 The receipts naming an instance are the authority for what it holds (§5.7).

### 9.4 Testimony shapes

9.4.1 An instance says what testimony it accepts in its corpus. A **testimony shape** (`testimony: true`, §11.2.3) recognises one producer's testimony by `matches` and declares, as `field` lines each read `from` a place in its structure, what that testimony carries — typically where the artifact came from (a uri, a sender, an account), what found or made it (a machine, a tool and its version, a session) and why it was acquired — with `required` on every field each testimony of that producer MUST carry. A new producer, or a new required field, is an edit to the corpus.

9.4.2 The tooling knows no producer. Which fields exist, what they are called and which are required is the instance's. Who the producer is and what its acquisitions were are the graph's: claims of entities, evidenced by the testimony.

### 9.5 Admission

9.5.1 Ingest MUST refuse, before anything is placed in a store, a delivered testimony that matches no testimony shape, or that lacks a field its shape requires.

9.5.2 The same check runs over the holdings (§17), so a testimony shape that tightens lists the testimony it no longer admits. A testimony admitted once is never removed for failing a later check; it is listed.

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

10.1.2 Where no signature decides, the extension of the name the artifact arrived under (its receipt's `name`, §9.3) MAY name a text format (markdown, YAML, TSV, source code). What nothing names is `application/octet-stream`.

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

10.2.3 A field a producer asserts — inserted into the bytes by a capturing tool under a name of its own — is not part of the format. It is text in the bytes, which a shape MAY select like any other.

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

### 10.4 Two classes of format

10.4.1 Every format the tooling registers is of one class:

- **structured** — the bytes are the content. The parse is exact, so the tooling decodes a **surface** at any address (§10.5) and a shape derives structure from the parse (§11.7). Nothing is read; a claim binds to the surface;
- **rendered** — the bytes are instructions to a renderer, and the content is what the rendering shows: the page as drawn, the web page as laid out, the pixels, the sound. No parse gives it. The tooling offers **hints** (§10.6) and an author reads (§8.3); a claim binds to a reading.

10.4.2 The class is the format's, and a constituent has its own: a message is structured, and its HTML part is a rendered constituent with a record of its own. Nothing is classified twice.

10.4.3 **What each format gives.** The tooling knows, for every format it registers, its class, the axes of its addresses (§7.3), which of them are physical, its surface or hint op, and whether it is a container. No vocabulary restates any of it.

| format | class | axes | physical | op | container |
|---|---|---|---|---|---|
| pdf | rendered | `page`, `page&bbox` | `page` | hint `pdf.words@1` | — |
| html, xhtml | rendered | `bytes` | — | hint `html.text@1` | its `data:` URIs |
| raster images | rendered | `bbox` | — | none | — |
| audio, video | rendered | `t` | — | hint `audio.speech@1` | — |
| csv, tsv | structured | `row`, `row&col`, `col` | `col` | `csv.parse@1` (`tab` for tsv) | — |
| json, ndjson | structured | `bytes` | — | `json.text@1` (`lines` for ndjson) | — |
| yaml | structured | `bytes` | — | `yaml.text@1` | — |
| vcard | structured | `bytes` | — | `vcard.text@1` | — |
| markdown, plain text | structured | `bytes` | — | `markdown.text@1` · the text itself | — |
| rfc822 | structured | `bytes` | — | `eml.text@1` | its parts |
| mbox | structured | `path` | — | — | its messages |
| zip, epub | structured | `path` | — | — | its entries |

10.4.4 A format the tooling sniffs but registers no row for is held, resolvable and addressable at `whole` only.

### 10.5 Surface ops

10.5.1 A **surface op** decodes the text at a scope of a structured artifact: given the bytes, one region of an address and an optional argument, it yields a string or nothing. A union address yields the regions' surfaces joined by a newline. Each op says which arguments it takes and refuses every other.

10.5.2 The bytes are parsed once per family per artifact, and the classification probes (§11.5) read that parse.

10.5.3 The registered surface ops:

| op | family | regions served | surface |
|---|---|---|---|
| `csv.parse@1 [<delimiter>]` | csv | `row`, `row&col` | a cell's value; a row's cells joined by a tab; RFC 4180 quoting; a byte-order mark stripped; the argument names the delimiter (`tab`, `;`, `\|`), default comma |
| `eml.text@1` | rfc822 | `bytes` | the span transfer-decoded (7bit, 8bit, binary, quoted-printable, base64) and charset-decoded, CRLF folded to LF, trailing whitespace trimmed |
| `json.text@1 [lines]` | json, ndjson | `whole`, `bytes` | the scalar values inside the span in document order, strings unescaped, one per line; `lines` parses one document per line |
| `yaml.text@1` | yaml | `whole`, `bytes` | as `json.text@1`, over the YAML parse |
| `vcard.text@1` | vcard | `whole`, `bytes` | the content lines in the span unfolded (RFC 6350 §3.2), each value unescaped, a structured value's components joined by a space |
| `markdown.text@1` | markdown | `whole`, `bytes` | the blocks in the span with their block markers removed (`#` runs, `>`, a list bullet or number, fence lines); inline markup verbatim |

10.5.4 A JSON or YAML value's span covers its source text, a string's quotes included. A vCard content line's span covers its folded physical lines. A markdown block's span covers its lines, its markers included.

10.5.5 An op's version identifies its behaviour. Any change to an op's output for any input is a new version.

### 10.6 Hints

10.6.1 A **hint op** guesses at what a rendered artifact shows at an address. A hint is never a surface: nothing binds to it, nothing stores it, and no check relies on it. It serves a reader in three ways: as proposed text the reader may stage, correct and sign (`propose`, §19.5); as the advisory the reading check lists where a signed reading differs from it (§13.4); and as the advisory that lists what a completeness attestation may have missed (§8.5). A shape's `select` over a rendered artifact proposes a tree the same way (§11.7.5).

10.6.2 The registered hint ops:

| op | family | regions | hint |
|---|---|---|---|
| `pdf.words@1` | pdf | `whole`, `page`, `page&bbox` | the words the PDF draws inside the region (§10.6.3), banded into lines on each glyph's baseline origin, in column-aware reading order; boxes rounded to 4 decimals |
| `html.text@1` | html, xhtml | `whole`, `bytes` | the text of the elements in the span: `head`, `script`, `style`, `template`, `noscript` and `svg` dropped; block elements and `<br>` end a line; table cells separated by a tab; whitespace runs collapsed to one space; lines trimmed; blank lines collapsed |
| `html.attr@1 <name>` | html, xhtml | `whole`, `bytes` | the named attribute of the root element at the span |
| `audio.speech@1` | audio, video | `whole`, `t` | candidate regions `t=a,b` with the speech a recogniser run on the host — a local binary or a service bound to the host — heard in each; the engine and its model ride in the note of the pass that signs |

10.6.3 **Drawn text only.** `pdf.words@1` reports text the PDF draws. A glyph drawn invisible — text render mode 3, the mode an OCR layer laid under a page image uses — contributes nothing. A page whose only text is invisible has no hint; it is read as a page.

10.6.4 An HTML span runs from an element's start tag's first byte to its end tag's last byte, half-open; an element whose end is implied is flagged. Offsets in the hint text map to bytes by a prefix sum of the UTF-8 lengths of its code units.

10.6.5 **No op reads.** No op transcribes an image, proposes the layout of a page, or writes a reading. What a pass signs are readings; a hint that was not corrected is still the pass's reading, and the pass answers for it.

### 10.7 Selector languages

10.7.1 A shape's `select` and `matches` selectors, and a `chrome` selector, are read in the language of the artifact's format:

| family | selector | a field's source (`attr`) |
|---|---|---|
| html, xhtml | a CSS selector | an attribute name |
| json, ndjson, yaml | a JSON pointer (RFC 6901) in which `*` stands for any key or index (`/messages/*`) | a pointer relative to the selected value (`sender_name`) |
| vcard | `card` (one `BEGIN`…`END`), or a content-line name (`FN`, `EMAIL`) | a parameter name (`TYPE`) |
| markdown | a block kind: `heading`, `paragraph`, `list`, `list-item`, `code`, `table`, `quote`, `break`, `front-matter` | — (a heading's `level` is its depth) |
| rfc822 | `header` (the header block); `part[type=<mime>]` (a part by its type); inside a decoded `text/plain` part, a line rule: `{"lines": "<regex>"}` (a run of lines each matching), `{"from": "<regex>"}` (from a matching line to the part's end), `{"blank": true}` (runs delimited by blank lines) | — |
| containers | a path pattern over the constituent list (`*` any run of characters) | — |

10.7.2 A line rule applies only where the part's transfer encoding is line-local (7bit, 8bit, binary, quoted-printable); a base64 part is one scope.

10.7.3 Every scope a selector names is a `bytes=` span in a text format, or a `path=` route in a container.

10.7.4 A value filled from a source is its source text verbatim (`1772355428000`, `Sunday, March 1 at 8:57 AM`); interpreting it is an author's work. Where the field declares a `pattern`, the first capture (else the whole match) is the value, and a source that does not match keeps its raw text.

## 11. The vocabularies

### 11.1 Forms, shapes, kinds and properties

11.1.1 An instance has two vocabularies — the corpus's and the graph's — and the directory a term's file sits in fixes what it is:

| | directory | names | used by |
|---|---|---|---|
| **forms** | `corpus/forms/` | structural units: page, heading, paragraph, table, row, line, block, message, field, value, cover-page, table-of-contents | `form` on the scopes of a record's tree, and nothing else |
| **shapes** | `corpus/shapes/` | the shapes of artifact families — one site's pages, one tool's exports, one producer's testimony — and how each converges onto forms | the classification of artifacts, and the derivation or proposal of their structure |
| **kinds** | `graph/kinds/` | what an entity is: transaction, residence, person, vessel | `is` on entities |
| **properties** | `graph/properties/` | what can be said of an entity: total, address, vessel name | the `pred` of a claim |

11.1.2 **Forms are structure, never meaning.** A form names how bytes are organised and never what content is, is for or is about: not a receipt, a regulation, a price, an author or a listing. A form is the same unit whatever format it appears in: a `message` in a chat export, in a mailbox and in a web page is one form. A photograph with a printed slip in it has a `block` and its `line`s; that the slip is a receipt, and that one line prints the purchase's total, are claims of an entity of kind `transaction`, cited to those scopes.

11.1.3 **Shapes converge families onto forms.** A shape recognises one family of artifacts by `matches` and says where the forms lie in its bytes. Many shapes converge on the same forms: a Messenger export, an Instagram export and an iMessage page are three shapes, each yielding `message`, `field` and `body`. A shape's name identifies its family; its lines say only where structure lies.

11.1.4 The corpus never names the graph; the graph cites the corpus. Forms and shapes never appear in the graph, and kinds and properties never appear in a record.

### 11.2 Term predicates

11.2.1 Every term MAY carry `refines` (its single parent, within its own vocabulary), `definition` (one sentence: the contract for the word) and `aligns` (the IRI of a class or property in a published vocabulary the graph projection asserts it under).

11.2.2 A **form** carries:

| predicate | value |
|---|---|
| `reads` | the aspect a scope of this form is read under: exactly one of `text`, `cells`, `tex`, `none` |
| `field` | a field a scope of this form carries: `{name, type, required?, derived?, options?, where?, pattern?, address?}`; `type` is one of `int`, `enum`, `datetime`, `string`, `col`, `designator`, `list`. A **designator** is a verbatim sub-reading with `where` (`leading`, `trailing`, `margin`, or a descendant form; §8.4.4), `pattern` and the derived-address key it feeds (`address`) |
| `expects` | child forms a scope of this form normally contains; satisfied by a scope of the form or a refinement of it |
| `convention` | reading conventions inherited down the tree, from a closed set the reading check applies (§13.4): `{"footnotes": "[^n]"}`, `{"hyphens": "rejoin"}`, `{"scripts": "flatten-outside-math"}`, `{"bullets": "drop"}` |
| `renders` | the markdown form of a scope: `{"md": "<template>"}` over the reading, a field's name, and `{level+1}` |
| `check` | a declarative check over scopes of the form (§17.3) |

11.2.3 A **shape** carries:

| predicate | value |
|---|---|
| `matches` | a classification condition (§11.5); repeatable, every line must hold |
| `select` | `{selector, form, in?, field?, attr?, ord?, level?}` — a node the selector names is a scope of `form`: derived on a structured artifact, proposed on a rendered one (§11.7) |
| `columns` | `{col, form, pattern?, required?}` maps a column to a form; `{header: <row>, form}` declares which row, if any, is the header and its form; `{rows: <form>}` names the form of every other row |
| `spine` | `{form}`: the order a package declares, each entry a top-level route scope of `form` |
| `chrome` | what is chrome: `{"selector": …}`, or `{"repeats": {"pages": <n>, "share": <fraction>}, "mask": "digits", "box": <decimals>, "roles": {"page-number": "<masked pattern>"}}` — a run is chrome when its masked text and its box at the declared precision recur on at least *n* pages and that share of them; role by pattern, else `running-header` or `running-footer` by position |
| `surface` | `{form, op}`: scopes of `form` in this family read their surface from `op`, `<op>@<version>[ <argument>]`, not the format's own; structured artifacts only (§11.6) |
| `testimony` | `true`: the shape is a producer's testimony (§9.4) |
| `field` | on a testimony shape: `{name, type, required?, from}` — a value the testimony carries, read `from` a place in its structure (a pointer, a column) |

11.2.4 A **kind** carries `owes`: the properties an entity of this kind should have. An unmet `owes` is demand (§14.6).

11.2.5 A **property** carries `range` — the type of its values (`string`, `int`, `decimal`, `amount`, `date`, `datetime`, `uri`, `bool`), a kind, when its value is another entity, or `artifact`, when its value is an artifact — and MAY carry `functional` (an entity has at most one value of it) and `authority` (§14.4.4).

```
// corpus/forms/line.jsonl                        // corpus/shapes/messenger-thread.jsonl
{"pred":"definition","val":"one line of print"}   {"pred":"matches","val":{"mime":"application/json","selector":"/participants"}}
{"pred":"reads","val":"text"}                     {"pred":"select","val":{"form":"message","selector":"/messages/*"}}
                                                  {"pred":"select","val":{"form":"field","in":"message","selector":"/messages/*/sender_name"}}
// graph/kinds/transaction.jsonl                  {"pred":"select","val":{"form":"body","in":"message","selector":"/messages/*/content"}}
{"pred":"owes","val":["total","date","merchant"]}
                                                  // graph/properties/total.jsonl
                                                  {"pred":"range","val":"amount"}
                                                  {"pred":"functional","val":true}
```

### 11.3 The effective rules of a scope

A scope's rules are the union of its forms' `refines` chains and its ancestors' conventions down the tree, under the artifact's shape and that shape's `refines` chain. Where two terms declare the same expectation, the most specific wins. A form with no `renders` renders as its parent; a scope whose forms declare none renders its reading.

### 11.4 Shapes of artifacts

11.4.1 Formats are the tooling's (§10.4.3); neither a form nor a shape restates one. An artifact's **shape** is the most specific shape that matches it (§11.5). An artifact no shape matches has none; it is held, addressable and resolvable, its structure is whatever passes assert, and it is listed as unshaped.

11.4.2 Structure is **derived** on a structured artifact, whose shape mints it from the parse (§11.7), and **asserted** on a rendered one, whose forming pass writes it (§8.4). A shape that matches a rendered artifact proposes and derives nothing; a pass never writes structure on a structured artifact — a disagreement with its shape is an edit to the shape.

11.4.3 A stored `shape` in the record (§8.2) overrides the derived one; where two shapes match an artifact, the most specific `matches` decides and a stored choice settles the rest. Constituents have their own shapes; nothing is classified twice.

### 11.5 Classification

11.5.1 A `matches` line is a set of conditions, every one of which must hold:

| condition | holds when |
|---|---|
| `mime` | the artifact's mime is the value; required on every `matches` |
| `first_row` | a tabular artifact's first physical row begins with the listed cells, whatever row the shape declares the header |
| `selector` | the selector, in the format's language (§10.7), selects something |
| `magic` | the bytes begin with the value |
| `container` | some container holding the artifact has this shape |
| `constituent` | some path among the artifact's own constituents matches the pattern |
| `path` | the artifact's own path in some container matches the pattern |

A pattern is a prefix, or a glob where `*` stands for any run of characters, anchored at the start.

11.5.2 A shape's `matches` lines all hold, or the shape does not match. Alternatives are sibling shapes under a common parent.

11.5.3 An artifact held by several containers is probed against every (container, path) pair; a `container` or `path` condition holds if any pair satisfies it.

11.5.4 Among the matching shapes, the most specific wins: the most conditions held, then the longer `refines` chain, then the name in code-point order.

### 11.6 Which op yields a surface

11.6.1 On a structured artifact a scope's surface comes from the first `surface` line for one of its forms along the shape's chain, else the format's own surface op (§10.4.3). A markdown shape that declares `{form: "front-matter", op: "yaml.text@1"}` makes its front matter yield the YAML values while every other scope yields `markdown.text@1`.

11.6.2 A shape naming an op the tool has not registered, a value that does not parse, or an argument the op refuses is a configuration error wherever the artifact loads, and a blocking vocabulary check. A rendered artifact gives no surface: its scopes are bound only by readings, and a `surface` line that reaches one is a vocabulary check failure.

### 11.7 Derived structure

11.7.1 On a structured artifact, every `select`, `columns` and `spine` line along its shape chain mints scopes from the parse:

- a selected node becomes a scope at its span (or its route), of `form`;
- its parent is the nearest enclosing scope of the form named by `in`, else it is a top-level scope;
- its position is byte order among its siblings, unless `ord` names another order the format defines;
- a `field` is filled from `attr` (§10.7.4); a designator field from the text `where` names;
- `level` sets a heading's level.

11.7.2 A tabular artifact: the declared header row is of its `columns` form and the first top-level scope; every other row is of the `rows` form, a top-level scope ordered by row number; each mapped column is a scope at `col=M` of its form, with `name` from the header, and contains its cells. Without a `rows` line, rows are addressable (§7.7) and of no form.

11.7.3 A container: one route scope per constituent a `select` path pattern names, of that line's `form`; or one per spine entry in spine order, of the `spine` line's `form`; each a top-level scope.

11.7.4 Derived structure and its surfaces are computed, never stored, and bind as `derived:<op>@<version>[ <argument>]` (§14.4).

11.7.5 **Proposals.** On a rendered artifact the same lines are hints: `propose` (§19.5) prints the tree they would mint, each scope with the hint text at its address, and a forming pass MAY stage it, correct it and sign. Nothing proposed is derived, stored or cited unsigned.

### 11.8 The pin

11.8.1 A pass pins the vocabulary it read against (`vocab`): a pass over a record pins the corpus's forms and shapes, a pass over an entity the graph's kinds and properties. A pin is `b3:` followed by the first 16 hex digits of the BLAKE3 of that vocabulary as loaded, an extension's terms together with its base's — the term files in name order, each preceded by its name and its lines sorted by identity, each line in canonical form (§6.4.2).

11.8.2 A change to a form or a shape makes every record pass pinned at an older hash **stale** for the scopes it reaches; a change to a kind or a property, every entity pass for the entities it reaches: derived, listed, re-run. Nobody edits a recipe.

### 11.9 What the tooling prescribes

The tooling prescribes no form and no shape. It relies on one property, `source`, with range `artifact` and `authority: true` (§14.4.4), which every standalone instance carries. Every other term is the instance's.

## 12. Derived, never stored

The following are computed at read time. Writing any of them to a file is a check failure.

| | derived from |
|---|---|
| a record's stage | the keys it holds and the completeness it attests (§8.5) |
| an artifact's shape | `matches` over the artifact; the `refines` chain; a stored choice |
| a structured artifact's structure | the parse through its shape's `select`, `columns`, `spine` |
| what is chrome | the rules the shape and the record declare |
| a proposal | hints over a rendered artifact (§10.6, §11.7.5) |
| positional and designated addresses | the tree: scopes' forms, fields and positions |
| containers of an artifact | the constituents of the containers the instance holds |
| holdings | the receipts naming the instance (§5.7) |
| provenance | the testimony naming an artifact, and its containers' provenance (§9.6) |
| testimony admitted | whether a testimony matches a testimony shape and carries the fields it requires |
| stale intrinsics | an `intrinsics` value by an older op version than the tool's for its mime |
| a reading's revision | the BLAKE3 of its body (§6.5) |
| binding state | an evidence entry's binding against the current readings and surfaces (§14.4) |
| standing of evidence | authority claims (§14.4.4) |
| status | bound evidence, its standing, modes and standing challenges (§14.5) |
| demand | §14.6 |
| staleness of a pass | `pass.vocab` against the current pin, for what a changed term reaches |
| residence | the host index (§18.4) |
| relevance | the `seek` rulings an artifact, scope or entity meets (§13.5) |
| section closure, paragraph numbers, the extent of an attestation | the tree |
| the export, the remainder, the envelope | §15 |
| sensitivity | the tier of the instance a line lives in |

## 13. Passes and rulings

### 13.1 Passes

13.1.1 A pass is one author and one verifier over one artifact, one set of constituents of a container (its `with` names the container's pass), or one entity. The author and the verifier MUST differ. A judgment exists only once both have signed; nothing unsigned is in the repository.

13.1.2 In a record a pass is an entry of `passes`: `<id>: {by, verify, vocab, date, note?, with?}`; in an entity's file it is a line `{"pred":"pass","val":{"id","by","verify","vocab","date","note"?}}`. `vocab` is the pin (§11.8). An id is `p<n>`, the lowest number free after every signed and open pass on the subject.

13.1.3 A correction pass swaps roles, so no correction is self-verified. A pass over a rendered artifact MAY start from a hint (§10.6) and from the tree its shape proposes (§11.7.5); what it signs is its own.

### 13.2 Staging and signing

13.2.1 An open pass stages in its instance's host state (§5.6), outside the repository: readings, a tree, chrome rules, a shape, an attestation; claims for an entity.

13.2.2 Signing lays the staged readings over the stored ones by address, puts a staged tree in place of the stored tree whole, adds the attestations the author makes, and runs the record checks, the per-file checks and the per-form checks over the result (§17). Any blocking finding refuses the signature and leaves the staging untouched. A record that does not yet exist is created, with its intrinsics, by the first signature over its artifact. Abandoning a pass discards its staging.

### 13.3 Complete

13.3.1 `complete.readings` is the pass's attestation that the readings cover the artifact: every region of the rendering that carries transcribable content has a reading. `complete.structure` is its attestation that the tree covers the readings: every reading lies in a scope and every scope that reads has its reading. The second is checked and blocks (§17.1); the first can only be attested, and where a hint exists the hint's words outside every reading and chrome are listed beside it.

13.3.2 Either means complete, never correct. `complete.readings` lapses when a reading is retired; `complete.structure` on any change to the tree. A formed record is a complete one: a tree is never signed without `complete.structure`.

13.3.3 A structured artifact attests nothing: its coverage is the export's remainder (§15.1).

### 13.4 The reading check

13.4.1 The rendering is the authority for a reading, and no op sees it: a reading is checked by its verifier. Where the format gives a hint (§10.6), the **reading check** compares the reading's body with the hint at its address, after the scope's conventions and designators are applied, per aspect, and lists the divergence as an advisory for the verifier. It never blocks and is never resolved automatically; an `accept` ruling marks a divergence known (§13.5). A reading with no hint — of an image — is listed for inspection.

13.4.2 **One normaliser** serves the reading check and binding (§14.4): Unicode NFKC; typographic quotes and dashes folded to ASCII; no-break space to space; whitespace runs collapsed. A second, **squashed** comparison removes whitespace and hyphens. Punctuation is content: a dropped period diverges.

13.4.3 **text.** Designator fields placed `leading` or `trailing` are removed from both bodies' head or tail; footnote marks and bullets are treated as the scope's conventions declare; the bodies are compared token by token (longest common subsequence), then squashed.

13.4.4 **cells.** Each cell of a row must occur as a contiguous run in the hint's column-aware words for that row.

13.4.5 **tex.** Control words map to their symbols (`\sum` → ∑, `\times` → ×, the Greek alphabet), braces and script marks drop, a label the scope's designator names drops from the hint; the multisets of letters, digits and operators must agree. A cell written as TeX is compared the same way.

### 13.5 Rulings

13.5.1 A **ruling** is how the owner steers an instance. It never asserts, supports or refutes a claim, is never evidence, and is never served outside the owner plane or projected into the graph (§15.3). It changes only what the instance relies on and what it works on next.

13.5.2 Rulings are the lines of `rulings.jsonl`, each with its own `id`, written `by: owner` with a `date`:

```
{"id":"r7","pred":"seek","val":{"owes":["service_history"],"select":{"kind":"vehicle"},"why":"…"},"date":"2026-01-20","by":"owner"}
```

| ruling | on | effect |
|---|---|---|
| `distrust` | a testimony (`ath://<id>`); an op's output at a scope (`ath://<id>?<at>` with the op); a pass (`ath://<id>#<pass-id>`) | everything bound through it is held, and becomes demand to re-derive, re-read or re-acquire; a distrusted testimony stays in provenance, marked. It says *do not rely on this*, never *this is false* |
| `accept` | a finding: a reading-check divergence (a scope and the reading's revision) or a check finding | the finding is listed as known and no longer recurs; a re-read lapses an accepted divergence |
| `seek` | a selection (forms, kinds, origins, an entity), optionally the owed properties or readings wanted | creates demand for what it names, and makes it **relevant**: every artifact, scope and entity that meets it — at ingest, at signing — is reported as meeting it |
| `defer` | a demand item or a selection of them | orders the work after everything not deferred |
| `decline` | a demand item or a selection of them | removes it from demand: what is declined is not pursued |

13.5.3 `why` is the owner's note to themself. It is shown to the owner alone and is never evidence, never exported and never served on any other plane.

13.5.4 A ruling lives in the instance that makes it. An extension holds its base's `distrust` and `accept` rulings too — they correct what both rely on — but not its base's `seek`, `defer` and `decline`, which steer only the base's work. An extension's owner MAY rule on its base's artifacts, passes and testimony. Revoking a ruling removes its line.

13.5.5 Acquiring artifacts from outside, deleting, removing a copy from a store, moving an artifact between an extension and its base, repinning a base and changing the vocabulary are owner-gated verbs of the tool (§19), not rulings.

## 14. Entities and claims

### 14.1 Entities

14.1.1 An **entity** is a particular thing in the world — a purchase, a house, a person, a boat — named by a name (§5.3), its file `graph/entities/<shard>/<name>.jsonl`. It is of one or more kinds (`is`), and carries one line per claim. Artifacts are evidence for an entity, never its identity.

14.1.2 An entity's file holds its passes as `pass` lines and every claim carries `pass`: every line in it was authored and verified.

```
// graph/entities/tx/txn-corner-shop-48213.jsonl
{"pred":"pass","val":{"by":"reader-a","date":"2026-01-12","id":"p1","verify":"reader-b","vocab":"b3:5c1e0a9d77f3b210"}}
{"pred":"is","val":"transaction","pass":"p1"}
{"pred":"total","val":"42.10","ev":[{"anchor":"ath://a48bf844?bbox=0.36,0.69,0.27,0.03&text","mode":"stated","quote":"42.10","reading":"b3:0de3a1c94b7e5f21"}],"pass":"p1"}
{"pred":"merchant","val":"ath://corner-shop","ev":[{"anchor":"ath://a48bf844?bbox=0.34,0.13,0.31,0.04&text","mode":"stated","quote":"CORNER SHOP","reading":"b3:7a19c4e0d2b65f83"}],"qual":{"as":"CORNER SHOP"},"pass":"p1"}
```

14.1.3 Splitting an entity, merging two or renaming one is a verb (`entity split|merge|rename`, §19.5) that rewrites every reference in the instance at once. An extension cannot rename its base's entities; on a repin it is told of the base's.

### 14.2 Claims

14.2.1 A claim is `{pred, val, qual?, ev, pass}`: `pred` is a property (§11.2.5); `val` is a value of the property's range, or `ath://<name>` of an entity of the kind its range names; `qual.as` keeps the value as the bytes printed it.

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
| `quote` | verbatim from the reading (a rendered artifact) or the surface (a structured one) the binding names; an elided composite (`…`) or a typographic re-take is refused; `prefix` and `suffix` disambiguate a repeated string and extend a long one |
| `mode` | how the entry supports the value: `stated`, `inferred`, `reported`; `reason` is required when it is not `stated` |
| `reading` | the binding, stamped by verify (§14.4) |

14.3.2 An entry says nothing about the standing of its source; standing is derived (§14.4.4).

14.3.3 A `stated` entry supports a string value only where the value is within its quote after normalisation; otherwise the claim is `inferred` with a `reason`.

### 14.4 Binding and standing

14.4.1 `reading` is one of:

- `b3:<16 hex>` — a reading's revision (§6.5): the reading at the anchor's scope and aspect, as it was when bound;
- `derived:<op>@<version>[ <argument>]` — on a structured artifact, the surface op yields the quote's surface;
- `field:<name>` — a field of the scope at the anchor, or `intrinsics:<key>` a value of the artifact's intrinsics;
- `null` — held.

14.4.2 An entry is **bound** when its anchor resolves to a scope, its binding yields a body there, and its quote (with prefix and suffix) is in that body under the normaliser (§13.4.2), plain or squashed. It is **held** when its binding is `null`, when the reading's revision is no longer the one it names, or when it relies on a distrusted testimony, op output or pass (§13.5). It is **flagged** otherwise, with the reason.

14.4.3 Three links are checked separately: claim to reading (the quote is in the bound body), reading to rendering (the verifier, with the reading check's advisories), value to quote (the verifier's judgment).

14.4.4 **Standing is derived, never written.** A property the graph declares `authority: true` — with range `artifact` — names an artifact as an authoritative source for the entity that carries it (`hl-02` `source` `ath://5e6e497d`). A bound entry anchored in artifact A and supporting a claim of entity X is **authoritative** while X carries a `confirmed` authority claim naming A; otherwise it is **independent**. An authority claim's own status is computed without the authority it would confer: A cannot vouch for itself.

### 14.5 Status, derived

| status | when |
|---|---|
| `confirmed` | a bound authoritative entry, or bound entries from two distinct artifacts, and no standing challenge |
| `provisional` · `inferred` · `reported` | the bar is not met; the mode of the best bound entry decides — `stated` gives `provisional` |
| `disputed` | a challenge stands |
| `conflicting` | a bound sibling claim disagrees on a `functional` property |
| `unsupported` | no bound entry — a hypothesis is a claim in this state |
| `refuted` | unsupported with an upheld challenge; it stays, so it is not proposed again |

### 14.6 Demand

Derived, never stored:

- a held entry is a reading owed over its region;
- an unmet `owes` of an entity's kind is a search;
- an unsupported claim is an acquisition;
- a stale pass is a re-run;
- an unmet `expects` is a soft finding;
- a `seek` ruling demands what it names;
- an extension's minted term, or its disagreement with a base line, is demand on the base (§4.4).

The owner orders demand with `defer` and removes it with `decline` (§13.5); nothing else about demand is written. An absence the bytes print ("–", a missing row) is demand, not a defect.

## 15. Export

### 15.1 The markdown proxy

15.1.1 The proxy is an output, never a record and never a citation target. It walks the tree in order and emits each scope through its form's `renders` rule over its reading, designators re-emitted from fields, every block prefixed by its `at`. A record that is not formed exports its readings in address order, each prefixed by its `at`, under no form.

15.1.2 Its header names: the authority (the bytes); every pass and its vocabulary pin; the accepted divergences; the chrome; and the **remainder** — for a rendered artifact, the readings outside every scope and, where a hint exists, the hint's words outside every scope and chrome; for a structured one, the characters outside every unit and declared chrome, of the total.

15.1.3 It is lossless back to the bytes and never breaks on a new term.

### 15.2 Provenance

An artifact's provenance chain (§9.6) is exported beside the proxy on the owner plane, and on another plane only where its testimony belongs to an instance that plane serves.

### 15.3 The graph

15.3.1 Every term and entity line, and every reading and scope of a record, maps to N-Quads statements — a scope to one per form, field and position, a reading to one per aspect — and back, byte-identical; rulings are never projected. Artifacts and their scopes are `ath://<id>` and `ath://<id>?<at>`; entities and kinds are `ath://<name>`; forms are `ath:form/<name>`, shapes `ath:shape/<name>` and properties `ath:p/<name>`. The line's own predicate is `ath:p/<pred>` for a claim and `ath:pred/<pred>` otherwise, its payload a literal typed `ath:json`, and its graph its authorship — `ath://<subject>#<pass-id>` for a pass, `ath:by/<op>` for an op, `ath:vocab` for a term's lines.

15.3.2 A term's `aligns` IRIs are asserted as its class or property in the projection; `is` projects as `rdf:type`.

## 16. Planes and publication

16.1 Serving an instance serves it and everything it builds on, filtered by plane. The **public plane** serves the `public` instances of the chain and the claims whose derived status is `confirmed`. An **audience plane** serves those plus every instance whose tier the audience's grant names, under the same status filter unless the grant names another. The **owner plane** serves every instance of the chain, every status, the rulings, provenance, demand and every finding.

16.2 Read-only is normative. A consumer reads entities, materialises artifacts only for what the entities' claims cite, never cites a generated view, and pins the reproducibility tuple — the commit of every instance in the chain and the vocabulary pin — when it freezes a build.

16.3 A server re-reads the instances per request and holds no state of its own.

## 17. Checks

### 17.1 Record checks

A failing record check blocks a pass from signing; an advisory is listed and never blocks.

| check | holds when |
|---|---|
| **class** | a structured artifact's record holds no reading and no scope |
| **unit** | every scope whose form reads an aspect has a reading under that aspect at its own `at`; every reading's body is under `text`, `cells` or `tex` |
| **tree** | every `at` in the tree is an address the format has, and no two scopes share one; every form named is a form |
| **coverage** | under `complete.structure`, every reading lies in a scope (§8.4.3); advisory: the hint's words outside every reading, or every scope, and chrome |
| **citation** | every anchor resolves; every quote is in its bound body or surface; a bound revision that no longer exists is flagged |

### 17.2 Vocabulary use, forms, testimony and files

| check | holds when |
|---|---|
| **sorts** | a scope's `form` names forms; a stored `shape` names a shape; `is` names a kind; a claim's `pred` is a property, and its `val` fits the property's range |
| **standing** | no evidence entry carries a standing; an authority claim names an artifact the instance holds |
| **per form** | `reads` is satisfied; required fields are present; designators are found where `where` and `pattern` say, in the reading or beside it; `expects` is met (soft); the form's `check` lines hold; the reading check per aspect (advisory); a stored `shape` is one that matches |
| **per testimony** | it matches a testimony shape; it carries every field the shape requires |
| **per file** | no undeclared field; no derivable value stored; no stored revision; keys in the record's order, lines sorted; pass references resolve; every pin known; `intrinsics` only by an op; no stale `intrinsics` (soft); every id and name resolves to one subject |

### 17.3 Form checks

A form's `check` lines are declarative checks over its scopes, composed from:

- `{"every": "<field>", "names": "<form>"}` — every value of the field names a scope of the form by designated address (a table of contents row names a heading);
- `{"contains": "<form>", "at_least": <n>}` — every scope of the form contains at least *n* scopes of the form named;
- `{"field": "<field>", "agrees": "intrinsics.<key>"}` — the field equals the intrinsic value.

### 17.4 Vocabulary checks

The vocabulary check refuses: a term that refines a term of another vocabulary; a predicate its vocabulary does not carry; a form that names a format, a shape or a family; a `reads` value outside the four; a `where` outside `leading`, `trailing`, `margin` and the forms; a `surface` op that does not parse, is unregistered, carries an argument the op refuses or reaches a rendered format; a selector the format's language rejects; a `matches` without `mime`; an `owes` naming no property; a `range` naming neither a type, `artifact` nor a kind; a name shared by an entity and a kind; a write at an identity a base's vocabulary holds; a `refines` cycle.

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

18.6.2 **Selection** matches labels the instance computes for each artifact and testimony it holds: its shape and that shape's `refines` chain (`shape`), the testimony shapes of its provenance (`origin`), the kinds of the entities that cite it (`kind`), the instance's tier (`tier`), its mime and its size; `testimony: true` selects testimony. Every policy whose selection matches applies; an extension's policies apply together with its base's.

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

19.2.2 It MUST register every op the loaded vocabulary names (§11.6) and, for every mime, an intrinsics op at least as new as any `intrinsics` value in the chain. A tool that falls short refuses to load (configuration error) and names what it lacks; it never writes an `intrinsics` value older than one already stored.

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
| `intrinsics sweep [--stale]` | write | rewrites `intrinsics` where its op version is older than the tool's |
| `resolve <anchor> [--trace]` | read | the artifact, the surface or the reading at an address; `--trace` reports the route (§18.8.2) |
| `tree <subject>` | read | the tree, derived or stored; a designated or positional address to its intrinsic `at` |
| `record <subject>` | read | the record's stage, its passes and attestations, and what the next stage needs (§8.5) |
| `provenance <subject>` | read | the provenance chain (§9.6) |
| `show <subject>` · `sort <subject>` | read · write | a subject's lines or document across the chain; rewrite a file in canonical order or style |
| `pass open` · `stage` · `sign` · `abandon` · `show` | write (show: read) | §13.1–§13.2 |
| `propose <subject> [<at>]` | read | the hints at an address: the text a hint op guesses, and the tree the artifact's shape would mint (§10.6, §11.7.5) |
| `readings <subject>` | read | the reading check's advisories for an artifact (§13.4) |
| `rule distrust\|accept\|seek\|defer\|decline <target> [--why <text>]` · `rule revoke <id>` · `rulings` | admin · admin · read | write or remove a ruling, confirmed at a terminal; list the rulings and what each currently affects |
| `relevant [<subject>]` | read | the `seek` rulings an artifact, scope or entity meets |
| `entity split` · `merge` · `rename` | write | §14.1.3 |
| `verify [<subject>…]` | read | bindings, status, demand, stale passes |
| `check [<subject>…] [--all]` | read | §17 |
| `vocab list` · `show` · `rules` · `pin` · `check` | read | the forms, shapes, kinds and properties; a term's lines; a scope's effective rules; the two pins; §17.4 |
| `export markdown <subject>` · `export graph [<subject>]` | read | §15 |
| `serve` | read | the planes over HTTP (§16) |
| `store add <name>` · `store list` | write · read | declare a store and write its id into it; the stores and their state |
| `custody inventory [<store>]` · `custody verify [<store>]` | write | refresh the index from inventories or scanner manifests; re-hash copies |
| `custody status` · `custody plan` | read | findings; the actions that would resolve them (§18.7) |
| `custody reconcile` | write | perform the plan: copy, verify, evict (§18.7) |
| `custody where <blake3>` · `custody report <store>` | read | every known residence of a hash, whether or not the instance holds it; an observed tree's report (§18.5.4) |
| `custody remove <blake3> --from <store>` | admin | remove one copy, refused unless the policies hold without it, verified at that moment (§9.7) |
| `log` · `whoami` | read | the history; the caller's profile, actor and instance root |
