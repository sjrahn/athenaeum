---
spec_id: ATH
title: "The Athenaeum Specification"
status: draft
license: "CC BY-SA 4.0"
---

# The Athenaeum Specification

The Athenaeum keeps bytes, says what they manifest, and asserts what they express — each as a line that names its subject, its author and the evidence it rests on. Three things are kept because nothing else can recover them: the bytes, the testimony of where and how they were found, and the owner's rulings. Everything else is derived from them or rediscovered over them. The facts so found are the product.

This document is normative. The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Examples are illustrative; where an example and the text disagree, the text governs.

## 1. Scope

1.1 This specification defines:

- what an **instance** stores: bytes, testimony, the owner's rulings, and the lines that describe, structure, read and cite the bytes;
- what the **tooling** derives from them, and the rules every stored and derived thing obeys;
- what the tooling knows about **formats**, and the primitives an **ontology** composes to say what the data means;
- how bytes are kept and found (**custody**), and the tool surface through which all of it is read and written.

1.2 A conforming tool implements every MUST of this document for the formats it registers (§10). A conforming instance holds only what this document allows to be stored.

1.3 The tooling acquires nothing. Bytes and testimony are acquired by producers outside the tooling and handed to it from disk; the tooling never fetches them. The only network traffic it may cause is a custody transport a deployment declares (§18.2), moving bytes the instance already holds.

## 2. Principles

1. **Three things are kept; everything else is recovered.** The bytes, the testimony (§9) and the owner's rulings (§13.5) are irreplaceable: each is a snapshot nothing else reproduces. Every other stored line is an op's output — deterministic, re-derivable, kept as a cache with a pin — or a judgment a pass wrote, checkable against the bytes and rediscoverable by another pass. The ontology is scaffolding of the second kind: two instances fed the same bytes may build different ontologies and should arrive, given time, at the same facts.
2. **The tooling knows formats, never conventions.** An op sniffs a mime, records the properties the format's own specification defines, addresses the bytes on the axes the format has, decodes a surface, and exposes the format's own nodes — an element, a MIME part, a JSON value, an archive entry, a `data:` URI. It never names a term and never decides what a node means: that a row is a header, that a `>` line is a quote, that a repeated line is a running header, that an element is a post. A scope below `whole` exists only where an ontology line or a pass puts it. A new kind of thing is an ontology edit; a new format is one op module.
3. **Everything is a claim line.** Properties, structure, readings, world facts, ontology terms, passes, testimony links and rulings are lines of one grammar: a subject, a predicate, a value, an authorship. One sort, one merge, one lineage.
4. **Ops author byte facts; passes author judgments.** Anything that can be wrong is written by a pass and verified by a second author. Anything an op writes has no status, because it carries no judgment.
5. **Addresses are intrinsic.** A scope is named by coordinates in the bytes — page and box, byte range, row and column, time, constituent path — never by a transform, a parser's tree or an identifier.
6. **The ontology is the recipe.** A scope manifests terms; what a term expects — fields, reading aspect, children, owed world facts, render form, the op that yields its surface — rides on the term. A pass pins the ontology it read against by hash; nobody chooses a recipe.
7. **Derived, never stored.** Class, status, demand, binding state, chrome, staleness, provenance, every non-intrinsic address and the export are computed from stored lines at read time (§12). A stored copy of a derivable thing is a defect.
8. **Nothing lossy enters the record.** A reading is a transcription checkable against the bytes — never a summary, a description, a paraphrase or a characterisation. Where a scope has no lossless transcription, the record marks its address and stops. What a scope shows, means or contains is a world claim in the ledger, cited to the scope. Where the bytes came from is testimony, an artifact of its own. The record contains nothing unfalsifiable against its own bytes.

## 3. Terms

| term | meaning |
|---|---|
| **instance** | one repository of trees, rulings and custody (§4): **standalone**, or an **extension** of a **base** instance it builds on |
| **artifact** | bytes, identified by their BLAKE3; the subject `corpus://<blake3>` |
| **container** | an artifact whose format holds whole files of its own |
| **constituent** | an artifact held whole inside a container; its own subject |
| **record** | an artifact's file: its properties and the judgments over its scopes (§8) |
| **properties** | what the format defines about an artifact's bytes, recorded by an op (§8.1) |
| **testimony** | an artifact a producer emitted about other artifacts — where, when, by what, why they were found (§9) |
| **receipt** | the testimony the tooling writes for every ingest (§9.3) |
| **origin term** | a term that admits a shape of testimony (§9.4) |
| **scope** | a region of an artifact named by an intrinsic address `at` |
| **term** | a subject of the ontology: a kind of thing, and what it expects |
| **manifests** | the relation of a scope to a term it is an instance of |
| **unit** | a scope whose term `reads` an aspect: the grain of a reading |
| **reading** | a transcription of a unit under one aspect, stored with its revision |
| **surface** | the text an op decodes at a scope; what a quote is checked against |
| **op** | a versioned, deterministic function of bytes, registered in the tooling by name `<name>@<version>` |
| **family** | the format an op parses (html, csv, pdf, rfc822, json, …); one parse per family per artifact |
| **pass** | one author and one verifier over one artifact or one concept file; the named graph of every judgment it signs |
| **authorship** | what a line carries to say who wrote it: `by` (an op, or `owner`) or `pass` |
| **concept** | a real-world thing with a slug, the subject of world claims |
| **claim** | a ledger line asserting a value of a predicate of a concept, carrying evidence |
| **evidence entry** | an anchor and quote into an artifact supporting a claim, bound by verify |
| **ruling** | the owner's final judgment on something the tooling derived: an accepted divergence or a disowned testimony (§13.5) |
| **plane** | a served view of the instance: public, audience, owner (§16) |
| **demand** | work the stored lines imply is owed, derived (§14.7) |

## 4. Instances and extension

### 4.1 Standalone and extending instances

4.1.1 An instance is one repository holding the trees of §5, its rulings and its custody declaration. It is either **standalone** — complete in itself: its own ontology (carrying the terms §11.9 names), corpus, ledger and custody — or an **extension**: it builds on exactly one existing instance, its **base**, sees everything the base holds, and adds to it. The base never sees its extensions. A base may itself be an extension; an extension then builds on everything its base builds on.

4.1.2 An instance's root holds `athenaeum.yaml`:

```yaml
name: household               # the instance's name
extends:                      # absent on a standalone instance
  path: ../reference          # where the base is checked out
  commit: 3f1c0e9a…           # the base commit this instance is built against
tier: private                 # who may read this instance: public, or a named tier
audiences:                    # named audiences and the tiers each is granted (§16)
  family: [private]
```

A cycle among bases, a base missing at its path, a base checkout not at the pinned commit, or an unparseable file is a configuration error.

4.1.3 **Visibility is per instance.** Every line an instance holds carries its tier; no line declares its own. An extension MUST NOT be `public` unless its base is: what it adds cites what the base holds.

### 4.2 What extending means for management

4.2.1 **The base is read-only.** Every write an extension makes lands in the extension. Nothing the extension does changes a file of its base, and the base's owner manages the base as a standalone owner would.

4.2.2 **The base is pinned.** An extension is built against one commit of its base and reads the base at that commit. Moving the pin is an owner-gated verb (`instance repin`, §19.4). After a repin everything that depends on the base is re-derived: the ontology pin (§11.8) changes wherever the base's terms changed, so the extension's passes over affected scopes become stale; bindings, status and lints are recomputed against the new base; an anchor into an artifact the base no longer holds is flagged. Nothing the base does reaches the extension before a repin.

4.2.3 **Resolution** is content-addressed: a hash or slug resolves in the extension first, then in its base, and so on down. The view of a subject is the line-set union of its files across the instances.

4.2.4 **The corpus is shared, never overwritten.** An extension MUST NOT write an artifact line at an identity (§6.3) its base holds with different content. Bytes the base already holds are the same subject: ingesting them in the extension writes their receipt and any testimony delivered with them in the extension, and nothing on the subject. A disagreement with a base line is demand on the base (§14.7).

4.2.5 **The ledger may be overridden.** An extension's ledger line wins over its base's at the same identity, within the extension's view only.

4.2.6 **The ontology is extended, never redefined.** An extension MAY add terms and add lines to the base's terms; it MUST NOT write at an identity the base's ontology holds. A term an extension mints is a proposal to the base, listed as demand on the base.

4.2.7 **Rulings belong to the instance that makes them.** An extension's owner MAY rule on a base artifact (an accepted divergence, a disowned testimony); the ruling lives in the extension's rulings file and holds in the extension's view only.

4.2.8 **Demand flows to the base and stops there.** What an extension cannot fix — a disagreement with a base line, a proposed term, a base reading it judges wrong — is listed as demand for the base's owner. The base acts on it, or does not, in its own history; the extension sees the outcome at its next repin.

4.2.9 **Reproducibility** names every instance in the chain: each one's commit and the ontology pin.

### 4.3 What extending means for the tooling

4.3.1 **One tool reads the whole chain.** It loads every instance from the extension down to the standalone one, at their pinned commits, and writes only the extension. It takes the extension's locks; a base is read without them.

4.3.2 **The combined ontology is the ontology.** Classification, derivation, lints and the pin (§11.8) run over the base's terms and the extension's together, as loaded.

4.3.3 **The tool must serve the whole chain.** It MUST register every op the combined ontology names (§11.6), and for every mime a properties op at least as new as any `properties` line anywhere in the chain. A tool that falls short refuses to load the extension (configuration error) and names what it lacks; it never writes `properties` older than a line already stored.

4.3.4 **Bytes resolve through every custody declaration in the chain.** A base artifact's bytes resolve through the extension's own custody first and then through its base's declaration, read-only. A copy the extension holds counts toward the extension's floors (§18.6.5).

## 5. Trees and files

5.1 An instance holds three trees and its private working state:

```
<instance>/
├── athenaeum.yaml
├── ontology/<term>.claims.jsonl        terms — what a kind of thing expects
├── corpus/<blake3>.claims.jsonl        artifacts — what the bytes are and manifest; testimony links
│          <blake3>.rulings.jsonl       the owner's rulings on that artifact
│          bytes/<b2>/<blake3>          the co-located store (§18)
│          lineage.jsonl                corrections, re-keys, supersessions
├── ledger/<slug>.claims.jsonl          concepts — what the world is, cited into the corpus
│          lineage.jsonl
├── strings/<b2>/<rev>                  reading bodies stored out of line
└── .ath/                               working state: staged passes, locks, caches, history — untracked
```

`<b2>` is the first two hex digits of the name it shards.

5.2 **One-way reference.** An artifact's file never names a concept, and never names its testimony or its containers: those are indexes (§12). The ledger cites `corpus://` freely. The ontology is read by both and names neither.

5.3 **One file, one writer.** Passes and ops write `.claims.jsonl`; the owner writes `.rulings.jsonl`. Ops write only `properties` and `testimony` lines, at ingest and in a properties sweep (§8.1).

5.4 Everything under `.ath/` is regenerable or transient; nothing normative depends on it, and it is never tracked.

## 6. The claim line

### 6.1 Shape

6.1.1 A line is one JSON object on one line. Artifact lines are keyed by `at` (an intrinsic address in the file's artifact, §7.3); ledger and ontology lines by `subject`. Every line carries a `predicate` and the predicate's fields. Every artifact, ruling and ledger line carries exactly one authorship; an ontology line carries none, since the ontology is authored by its instance's history.

6.1.2 A line is a triple with provenance — `(subject, predicate, object)` plus its authorship — and maps to one N-Quads statement in the graph of its authorship (§15.3).

```
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","predicate":"in","value":{"at":"whole","ord":11},"pass":"p1"}
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","predicate":"manifests","term":"heading","num":"5.","level":1,"pass":"p1"}
{"at":"page=3&bbox=0.1192,0.6933,0.4851,0.019","predicate":"reads_as","aspect":"text","rev":"b3:9f86d081884c7d65","body":"Baseline emissions","pass":"p1"}
{"subject":"heading","predicate":"reads","value":"text"}
{"subject":"tide-table-02","predicate":"version","value":"02.1","evidence":[{"anchor":"corpus://5e6e497d…?page=1&bbox=0.1429,0.6906,0.0901,0.0087&text","quote":"Version 02.1","kind":"authoritative","mode":"stated","reading":"b3:aae7b6bb9c216abb"}],"pass":"p1"}
```

### 6.2 Authorship

6.2.1 `by` names an op as `<name>@<version>`, a harvest as `harvest:<term>@<pin>` (§14.6), or `owner`. `pass` names a pass line in the same file by its id (§13.1).

6.2.2 A `pass` line is itself the authorship of the lines that name it and carries none of its own.

6.2.3 An artifact, ruling or ledger line with no authorship, with both, or with a `pass` that does not resolve in its file MUST be refused at write.

### 6.3 Identity

6.3.1 A line's identity is the key a second line collides on. A write at an existing identity with different content is a **correction** (§6.6); a write with the same content is a no-op.

| line | identity |
|---|---|
| `properties` | (at, predicate, by) — a newer op writes a second line that supersedes the first |
| `testimony` | (at, predicate, value) — one line per subject the testimony describes |
| `manifests` | (at, predicate, term) — several terms on one scope are several lines |
| `in` | (at, predicate) — one placement per scope |
| `reads_as` | (at, predicate, aspect) — one reading per scope and aspect; a re-read is a new revision at the same identity |
| `pass` · `complete` | (at, predicate, id) · (at, predicate, pass) |
| rulings | (at, predicate, rev) for `inspected`; (at, predicate) for `disowned` |
| a ledger claim | (subject, predicate, value or object, qualifiers) — evidence entries accrue on the one line |
| an ontology line | (subject, predicate) for a single-valued predicate; (subject, predicate, name) for a repeatable one, where the name is the value's `name`, `col`, `selector` or `term`, else the whole value |

6.3.2 Competing transcriptions of one scope under one aspect are not representable.

### 6.4 Files and canonical form

6.4.1 One line per claim. A file is sorted by identity key. Nothing depends on line order: reading order is `ord` (§8.1), never position. The union of an extension with its base and a merge are line-set unions.

6.4.2 The canonical serialisation of a line is compact JSON, LF-terminated, non-ASCII characters unescaped, with its keys in a fixed order: `at` or `subject` first, then `predicate`, then every other key in code-point order; every nested object's keys in code-point order; arrays in their stored order. Two lines are the same content when their canonical serialisations are equal. Every hash this document defines over JSON — a revision, the pin — is taken over this form.

6.4.3 The packed `value` is the unit of judgment: `in` packs its parent and `ord` because they are verified together.

### 6.5 Strings and revisions

6.5.1 A reading's `rev` is `b3:` followed by the first 16 hex digits of the BLAKE3 of its body: a string as UTF-8, an array as its canonical JSON (§6.4.2).

6.5.2 A body MAY be inline (`body`) or stored out of line under `strings/` by its `rev`. A body is retained while the instance references its `rev`; an extension's references never keep or remove a body in its base.

### 6.6 Corrections and lineage

6.6.1 A correction is a delete and an insert, never an edit in place. Every correction, re-key (§7.8) and supersession appends a row to the tree's `lineage.jsonl`: `{"from": <identity + content hash>, "to": <identity + content hash>, "by": <authorship>, "date": <ISO date>}`.

6.6.2 `properties` and `testimony` lines are never corrected: a newer attester supersedes a `properties` line with a second line (§8.1); a testimony cannot change, since its bytes cannot.

## 7. Artifacts and addresses

### 7.1 Artifact subjects

7.1.1 An artifact subject is `corpus://<blake3>`, the full 64-hex BLAKE3 of its bytes. Identity is the hash and nothing else: no URL, name, path or producer key takes part in it.

7.1.2 New bytes are a new subject. The same bytes met again are the same subject; the encounter adds testimony only (§9) and changes nothing on the subject.

### 7.2 Containers and constituents

7.2.1 A **container** is an artifact whose format holds whole files of its own: an archive entry, a package's documents, a message's parts, a mailbox's messages, the payload of a `data:` URI in markup. Which formats are containers, and how their constituents are named, is the format's definition (§10.3).

7.2.2 A container's `properties` carries its **constituents**: per constituent, its `path` in the format's own terms and its BLAKE3, plus the fields the format defines for it (a filename, a mediatype, a Message-ID). Every constituent is its own artifact subject. A constituent's file names no container.

7.2.3 Ingest makes subjects of a container's constituents, one level deep: a constituent's own constituents stay on its list until that constituent is itself ingested as a container.

7.2.4 Which containers hold an artifact is derived from the constituent lists (§12). Cite the constituent, which outlives the package.

### 7.3 The intrinsic address — `at`

7.3.1 `at` is the only address stored and the only address an anchor carries. Its axes are declared by the artifact's root term (§11.4). Every axis is a coordinate in the bytes as stored, with no transform.

| axis | formats | meaning |
|---|---|---|
| `whole` | every artifact | the artifact; where `properties`, `testimony`, `pass`, `complete` and the root `manifests` sit |
| `page=N` · `page=N&bbox=x,y,w,h` | pdf, page images | page N, 1-based; a box normalised 0–1 in the page frame, origin top-left |
| `bbox=x,y,w,h` | raster images | a box normalised 0–1 on the pixel grid |
| `bytes=a,b` | every text format: html, xhtml, markdown, plain text, rfc822, json, ndjson, yaml, vcard | the half-open byte range [a, b) of the file |
| `row=N` · `row=N&col=M` · `col=M` | csv, tsv | physical row N and column M, both 0-based |
| `t=a,b` | audio, video | seconds [a, b) in the stored stream |
| `path=p` | containers | the constituent at path p, equivalent to the constituent's own subject |

7.3.2 A **union address** `a;b;c` names one scope made of several regions — a container spanning pages is the union of one box per page. A union is the scope's own address, never a constituent's address borrowed.

7.3.3 A trailing **aspect** `&text`, `&cells` or `&tex` names the reading surface a quote is taken from.

### 7.4 Canonical form

7.4.1 Box coordinates carry at most 4 decimals. Containment of one box in another allows 0.002 slack per edge.

7.4.2 The regions of a union sort by page, then y, then x, then byte start; `path` sorts last. Every address is canonicalised before it is used as identity.

### 7.5 Routes through containers

7.5.1 An address that carries `path=p` routes: the container's constituent list names the constituent at p, and the rest of the address applies in that constituent. The route holds wherever `path` stands in the address. A path the list lacks is flagged.

7.5.2 An anchor through a route canonicalises, at bind time, to the constituent's own subject.

### 7.6 Derived addresses

7.6.1 Two further forms exist and neither is stored.

- **Positional**: the `ord` path from `whole` down the `in` chain, always available.
- **Designated**: the path of designators the bytes themselves print — `?sec=5&para=6`, `?eq=1`, `?post=4`, `?col=Currency`, `?ch=2&fig=1` — available where a term declares a designator field (§11.2).

7.6.2 The resolver maps either form to an `at` through `manifests`, `in` and `ord`. A later designator key narrows to the earlier key's scopes' descendants by `in`, and to what their boxes contain. A designator field whose pattern has a capture answers to the capture as well as the whole value: `num: "3."` under `^(\d+)\.$` answers `sec=3`.

### 7.7 Physical addressability

A page the document has, a row the parse holds and a cell within such a row are scopes an anchor may name even where nothing manifests there.

### 7.8 Re-capture and re-key

7.8.1 A re-capture is a new subject. A `supersedes` claim in the ledger relates the two (§14.2); an anchor carries across where the surface at the same intrinsic address still holds its quote, and is otherwise held (§14.4).

7.8.2 A structure correction that moves a scope re-keys the readings on it — same body, same `rev`, new identity, one lineage row. Anchors that still lie inside the new box do not move.

## 8. The artifact file

### 8.1 Predicates

| predicate | authorship | meaning |
|---|---|---|
| `properties` | op | what the bytes are, as the format defines: mime, size, encoding, page count, dimensions, duration, embedded metadata the format specifies, and a container's constituents. Nothing a producer asserts. A cache with a pin: `by` names the format's properties op and its version; a line written by an older version than the tool's is **stale** (§12) and a properties sweep writes a superseding line. |
| `testimony` | op | on a testimony artifact only (§9): the subject it describes, `corpus://<blake3>`. One line per subject. |
| `pass` | — | a pass: `{id, by, verify, ontology, date}`. The named graph every judgment in the file belongs to (§13.1). |
| `complete` | pass | the pass's attestation that structure over `at` is complete — every word of the surface lies in a scope or in derived chrome. It means complete, never correct. It lapses on any structure change inside its extent. Written only on an asserted tree (§11.4). |
| `manifests` | pass, or derived | the scope at `at` manifests `term`, with the fields the term declares. An undeclared field is refused at write. A stored line wins over a derived one at the same scope. |
| `in` | pass, or derived | placement: the parent's bare `at` and `ord`, reading order within it. Physical scopes (pages, columns) carry no `in`: containment there is geometric. The logical tree runs from `whole` down. Every non-physical scope MUST be reachable from `whole` by `in`. |
| `reads_as` | pass | a transcription of the scope under one aspect (`text` · `cells` · `tex`), with `body` and `rev`. Every aspect is lossless and checkable against the bytes (§13.4). Readings are annotations beside the bytes, never substitutes for them. |

### 8.2 Rules

8.2.1 **Unit rule.** A `reads_as` sits only at a scope that manifests a term, and its aspect MUST be one that term `reads`. Readings are never smaller than a unit; a unit may be a group (a table with its caption, an equation with its label).

8.2.2 **Faithful to the bytes.** A reading transcribes what is printed, typo included. A correction of the source is a ledger claim with `mode: inferred` or a `challenges`, never a silent fix.

8.2.3 **Designators are structure.** A leading "5.", a right-margin "Equation (1)", a "#4" on a post are fields on `manifests`, verbatim as printed; the body is the text without them. Deciding that "2." is a number and not a sentence is a judgment, written by the pass that reads the scope.

8.2.4 **Where the bytes give the structure, nothing is stored.** Under an ontology's `select`, `shape` and `spine` lines (§11.7), `manifests` and `in` derive from the parse. The file then holds its `properties` line alone; a pass writes a line below `whole` only to disagree with the derived structure or to add to it.

8.2.5 **Chrome is derived by a declared rule.** Running headers, page numbers, navigation: a `chrome` line names what makes a run chrome (§11.2). The tooling applies the rule and has none of its own. Chrome is listed in the export header and stored nowhere.

8.2.6 **A scope with no lossless transcription has no reading.** It is addressed, manifested and placed; its bytes resolve at its `at`; the record stops there. Anything said about what it shows, means or contains is a ledger claim anchored at that `at` with no quote and `mode: inferred`. Where such a scope carries transcribable content (glyphs in a raster, speech in a stream), a pass manifests the sub-scopes that carry it and reads those, under a lossless aspect.

8.2.7 **A weak engine is a reading's author, never a derivation.** A proposal op (OCR, layout analysis, transcription) may propose lines a pass accepts or corrects (§13.1); its output never enters a file under its own `by`, and a claim always binds to the accepted reading.

8.2.8 **A field the address determines is derived.** A field a term declares `derived` (a page's number) is never stored.

```
// a CSV export: the whole file, one line
{"at":"whole","predicate":"properties","value":{"mime":"text/csv","bytes":151157,"rows":275,"cols":29,"encoding":"utf-8"},"by":"csv.properties@1"}
// derived, not stored: whole manifests retailer-order-history (by matches); row=0 manifests header (by the term's shape);
// row=N manifests order-line (by its rows line), in whole, ord N; col=3 manifests currency-code …
```

## 9. Testimony

### 9.1 What testimony is

9.1.1 Where the bytes were found, when, by what and why is not a fact about the bytes and cannot be checked against them. It is **testimony**: a snapshot a producer made, irreplaceable because the moment is gone, and never part of the record.

9.1.2 Testimony is an **artifact**. What a producer emits about a capture — a capture sidecar, an export's own manifest, a statement of origin — is ingested verbatim. Its identity is its BLAKE3. Its file holds `properties` and one `testimony` line per subject it describes:

```
{"at":"whole","predicate":"properties","value":{"mime":"application/yaml","bytes":612,"encoding":"utf-8"},"by":"yaml.properties@1"}
{"at":"whole","predicate":"testimony","value":"corpus://1409369e…","by":"ath.ingest@1"}
```

9.1.3 A testimony cannot be edited, because its bytes cannot change. A mistaken testimony is answered by a later testimony and, where the owner judges it wrong, by a `disowned` ruling (§13.5).

9.1.4 Testimony is evidence, not knowledge. It holds no claim and has no status. A ledger claim about where or when something was found or published cites the testimony artifact by an ordinary anchor into its bytes, under its own surface; such an entry's kind is `direct`.

### 9.2 Delivery

9.2.1 Testimony arrives with the bytes it describes: beside them as `<file>.testimony.<ext>`, or named explicitly at ingest. A producer's file is stored as delivered: nothing is folded into another line, renamed or dropped.

9.2.2 A testimony describing a container describes the container only; its constituents inherit it by derivation (§9.6). A producer manifest describing several files testifies to each, one line per subject.

### 9.3 The receipt

9.3.1 Every ingest writes one testimony of the tooling's own, the **receipt**: a JSON object

```json
{"actor": "reader-a", "received": "2026-01-12T09:14:03Z", "name": "statement-03.pdf", "testimony": ["<blake3>", "…"]}
```

— who handed the bytes in, the instant, the name they arrived under, and the testimony delivered with them. The receipt covers the bytes and every testimony it lists. Testimony is not itself receipted, so every artifact has at least one testimony and the chain stops at one.

9.3.2 The receipt is the only testimony shape the tooling prescribes. Every standalone instance carries its term, `receipt`, refining `testimony`.

### 9.4 Origin terms

9.4.1 An instance says what testimony it accepts in its ontology. An **origin term** refines `testimony`. It `matches` a producer's shape over the testimony's mime (§11.5), and declares its facets as `select` and `field` lines:

- the **source** — where the bytes came from: a uri, a sender, an account;
- the **producer** — what found or made them: the machine, the tool and its version, the session;
- the **context** — why they were acquired;

with `required` on every field each testimony of that origin MUST carry. A new origin, or a new required field, is an ontology edit.

9.4.2 The tooling knows no origin. Which facets exist, what they are called and which are required is the instance's.

### 9.5 Admission

9.5.1 Ingest MUST refuse, before any byte is placed, a delivered testimony that classifies to no term refining `testimony`, or that lacks a field its origin term requires.

9.5.2 The same check runs over the corpus as a lint (§17), so an origin term that tightens lists the testimony it no longer admits. A testimony admitted once is never removed for failing a later check; it is listed.

### 9.6 Provenance

9.6.1 An artifact's **provenance** is derived (§12): the testimony whose `testimony` lines name it, together with the provenance of every container whose constituent list holds its BLAKE3, at that path, transitively.

9.6.2 Provenance is shown as a chain — receipt, the container's testimony, the path, the constituent — so a container's uri is never presented as a constituent's. Nothing is copied to a constituent: an artifact first met alone and later inside an export has both origins the moment the export is ingested.

9.6.3 A disowned testimony stays in provenance, marked, with the owner's reason; an evidence entry anchored into it is held (§14.4).

### 9.7 Retiring a copy

Once another route resolves the same bytes — a container's constituent, a location (§18) — a standalone copy of an artifact's bytes MAY be retired, the full BLAKE3 verified first. Its readings, claims and testimony stay, since identity is the hash. Testimony bytes are never retired. Bytes a container re-encoded are a different artifact; "the same image as" is a ledger claim.

### 9.8 Placement

A testimony is held in an instance like any artifact. It MAY sit in a more private instance than its subject — a document in a public base, a private extension's record of the machine that fetched it: an extension MAY hold testimony about its base's artifacts.

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

### 10.2 Properties

10.2.1 Every `properties` line carries `mime`, `bytes` (the size) and, for text, `encoding`. Each format adds what its specification defines:

| format | properties beyond mime, size, encoding |
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

10.2.3 A field a producer asserts — inserted into the bytes by a capturing tool under a name of its own — is not a property. It is text in the bytes, which an origin term or any term MAY select like any other text.

10.2.4 Each format's properties op is named `<format>.properties@<version>`. The tool registers one current version per mime; a `properties` line by an older version is stale (§12).

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
| `pdf.words@1` | pdf | `whole`, `page`, `page&bbox` | the words of the text layer inside the region, banded into lines on each glyph's baseline origin, in column-aware reading order; boxes rounded to 4 decimals |
| `eml.text@1` | rfc822 | `bytes` | the span transfer-decoded (7bit, 8bit, binary, quoted-printable, base64) and charset-decoded, CRLF folded to LF, trailing whitespace trimmed |
| `json.text@1 [lines]` | json, ndjson | `whole`, `bytes` | the scalar values inside the span in document order, strings unescaped, one per line; `lines` parses one document per line |
| `yaml.text@1` | yaml | `whole`, `bytes` | as `json.text@1`, over the YAML parse |
| `vcard.text@1` | vcard | `whole`, `bytes` | the content lines in the span unfolded (RFC 6350 §3.2), each value unescaped, a structured value's components joined by a space |
| `markdown.text@1` | markdown | `whole`, `bytes` | the blocks in the span with their block markers removed (`#` runs, `>`, a list bullet or number, fence lines); inline markup verbatim |

10.4.4 An HTML scope's span runs from its start tag's first byte to its end tag's last byte, half-open; an element whose end is implied is flagged. Offsets in the decoded text map to bytes by a prefix sum of the UTF-8 lengths of its code units.

10.4.5 A JSON or YAML value's span covers its source text, a string's quotes included. A vCard content line's span covers its folded physical lines. A markdown block's span covers its lines, its markers included.

10.4.6 An op's version identifies its behaviour. Any change to an op's output for any input is a new version.

### 10.5 Proposal ops

A **proposal op** — optical character recognition over a raster, layout analysis over a page, transcription of a stream — prints candidate lines a pass MAY stage, accept or correct (§13.1). Its output is never stored under its own `by` and never bound as a surface. `image.words@1` proposes one box per recognised line of a raster, in reading order, with its text; the term each box manifests is named by the pass that stages it (or given to the verb). The engine and its version ride in the pass's note.

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

10.6.4 A value filled from a source is its source text verbatim (`1772355428000`, `Sunday, March 1 at 8:57 AM`); interpreting it is a value op's work. Where the field declares a `pattern`, the first capture (else the whole match) is the value, and a source that does not match keeps its raw text.

## 11. The ontology

### 11.1 Terms as subjects

A term is a subject whose expectations are lines in `ontology/<term>.claims.jsonl`. One vocabulary serves the corpus (what a scope may manifest), testimony (what an origin admits), the ledger (what a concept may be and owes) and the export (how a term renders). Formats, kinds of documents, units, containers, data shapes, conversations, origins and concept types are all terms.

### 11.2 Term predicates

| predicate | value |
|---|---|
| `refines` | the single parent term |
| `definition` | one sentence: the contract for the word |
| `aligns` | an IRI of a class in a published vocabulary the RDF projection asserts the term under |
| `matches` | a classification condition (§11.5); repeatable, every line must hold |
| `axes` | the address axes of a root (§7.3) |
| `physical` | the axis whose scopes are physical (`page`) |
| `tree` | `asserted` (structure is judgment: `in` and `ord` are written by passes) or `derived` (structure comes from the parse under `select`, `shape`, `spine`) |
| `derivation` | the surface op, `<op>@<version>[ <argument>]` (§10.4) |
| `reads` | the aspect a scope of this term is read under: exactly one of `text`, `cells`, `tex`, `none` |
| `field` | a field on `manifests`: `{name, kind, required?, derived?, options?, where?, pattern?, address?}`; `kind` is one of `int`, `enum`, `datetime`, `string`, `col`, `designator`, `list`. A **designator** is a verbatim sub-reading with `where` (`leading`, `trailing`, or a descendant term), `pattern` and the derived-address key it feeds (`address`) |
| `expects` | child terms a scope of this term normally contains; satisfied by a scope manifesting the term or a refinement of it |
| `owes` | world predicates the concept a scope of this term manifests should carry |
| `functional` | world predicates that take one value per concept |
| `convention` | reading conventions inherited down the `in` chain, from a closed set the comparator applies (§13.4): `{"footnotes": "[^n]"}`, `{"hyphens": "rejoin"}`, `{"scripts": "flatten-outside-math"}`, `{"bullets": "drop"}` |
| `renders` | the markdown form of a scope: `{"md": "<template>"}` over `{body}`, a field's name, and `{level+1}` |
| `select` | `{selector, term, in?, field?, attr?, ord?, level?}` — derived structure (§11.7) |
| `shape` | `{col, term, scheme?, pattern?, required?}` maps a column to a term; `{header: <row>, term}` declares which row, if any, is the header and the term it manifests; `{rows: <term>}` names the term every other row manifests |
| `spine` | `{term}`: the order a container's package declares, each entry a route scope manifesting `term`, placed `in whole` |
| `sentinel` | values that derive to null in harvest ("Not Available") |
| `keys` | the key column of a key-value table |
| `cells` | names for cell positions of a row's `cells` reading |
| `chrome` | what is chrome: `{"selector": …}`, or `{"repeats": {"pages": <n>, "share": <fraction>}, "mask": "digits", "box": <decimals>, "roles": {"page-number": "<masked pattern>"}}` — a run is chrome when its masked text and its box at the declared precision recur on at least *n* pages and that share of them; role by pattern, else `running-header` or `running-footer` by position |
| `concept` | a harvest rule (§14.6) |
| `lint` | a declarative check over scopes of the term (§17.3) |

### 11.3 The effective rules of a scope

A scope's rules are the union of its terms' `refines` chains and its ancestors' conventions down the `in` chain. Where two terms declare the same expectation, the most specific wins. A term with no `renders` renders as its parent; an unknown term renders as `unit`.

### 11.4 Roots, classes and trees

11.4.1 An artifact's **mime root** is the most specific term whose `matches` names its mime and nothing else. Its **root** is the most specific term that matches it at all. Its effective chain is the root's `refines` chain followed by the mime root's. `axes`, `physical`, `tree` and `derivation` come from the first term along that chain that declares them.

11.4.2 Every root refines one of these classes:

- **document** — readings can total to a proxy: pdf, html, xhtml, markdown, rfc822, the documents of a package;
- **lossy** — readings can be drawn, never total: **image** (raster images) and **media** (audio, video);
- **data** — values given by the parse: csv, json, ndjson, yaml, vcard, and **container**;
- **testimony**, refining data — what a producer said about other artifacts (§9).

11.4.3 Class is a lookup on the chain. One stored `manifests` at `whole` overrides the derived root (a PDF of photographs manifests `scan-album`); where two roots match an artifact, the most specific `matches` decides and a stored override settles the rest. Constituents carry their own terms; nothing is classified twice.

### 11.5 Classification

11.5.1 A `matches` line is a set of conditions, every one of which must hold:

| condition | holds when |
|---|---|
| `mime` | the artifact's mime is the value; required on every `matches` |
| `first_row` | a tabular artifact's first physical row begins with the listed cells, whatever row the shape declares the header |
| `selector` | the selector, in the root family's language (§10.6), selects something |
| `magic` | the bytes begin with the value |
| `container` | some container holding the artifact has this root term |
| `constituent` | some path on the artifact's own constituent list matches the pattern |
| `path` | the artifact's own path in some container matches the pattern |

A pattern is a prefix, or a glob where `*` stands for any run of characters, anchored at the start.

11.5.2 A term's `matches` lines all hold, or the term does not match. Alternatives are sibling terms under a common parent.

11.5.3 An artifact held by several containers is probed against every (container, path) pair the constituent lists give; a `container` or `path` condition holds if any pair satisfies it.

11.5.4 Among the matching terms, the most specific wins: the most conditions held, then the longer `refines` chain, then the term name in code-point order.

### 11.6 Which op yields a surface

11.6.1 A scope's surface comes from the first `derivation` along its own terms' chains, else along the artifact's effective chain. A `timestamp` term that declares `html.attr@1 datetime` yields the attribute while its siblings yield `html.text@1`.

11.6.2 A term naming an op the tool has not registered, a value that does not parse, or an argument the op refuses is a configuration error wherever the artifact loads, and a blocking ontology lint. A root that declares no derivation has no surface; its scopes are bound only by readings.

### 11.7 Derived structure

11.7.1 Where the tree is derived, every `select`, `shape` and `spine` line along the effective chain mints scopes from the parse:

- a selected node becomes a scope at its span (or its route), manifesting `term`;
- its parent is the nearest enclosing scope of the term named by `in`, else `whole`;
- its `ord` is byte order among its siblings, unless `ord` names another order the format defines;
- a `field` is filled from `attr` (§10.6.4); a designator field from the text `where` names;
- `level` sets a heading's level.

11.7.2 A tabular tree: the declared header row manifests its `shape` term and is `in whole, ord 0`; every other row manifests the `rows` term, `in whole`, ordered by row number; each shaped column is a scope at `col=M` manifesting its term, with `name` from the header, and contains its cells. Without a `rows` line, rows are addressable (§7.7) and manifest nothing.

11.7.3 A container's tree: one route scope per constituent a `select` path pattern names, manifesting that line's `term`; or one per spine entry in spine order, manifesting the `spine` line's `term`; each `in whole`.

11.7.4 A derived reading lives in the scope table and binds as `derived:<op>@<version>[ <argument>]` (§14.4). It is never stored.

### 11.8 The pin

11.8.1 A pass pins the ontology it read against: `b3:` followed by the first 16 hex digits of the BLAKE3 of the ontology as loaded — the term files sorted by term name, each file's lines sorted by identity, each line in canonical form (§6.4.2). A harvest pin is the first 6 hex digits.

11.8.2 A term change makes every pass pinned at an older hash **stale** for the scopes that manifest the changed term or its refinements: derived, listed, re-run. Nobody edits a recipe.

### 11.9 What the tooling prescribes

The tooling relies on exactly these terms, which every standalone instance carries: `unit`, `document`, `lossy`, `image`, `media`, `data`, `container`, `testimony` and `receipt`. Every other term is the instance's.

## 12. Derived, never stored

The following are functions of stored lines and are computed at read time. Writing any of them to a file is a lint failure.

| | derived from |
|---|---|
| class, root term | `properties.mime` through `matches`; the `refines` chain; a stored override |
| `manifests` and `in` on a derived tree | the parse through `select`, `shape`, `spine`; a stored line at the same scope wins |
| chrome | the rules `chrome` lines declare |
| positional and designated addresses | `manifests` fields, `in`, `ord` |
| containers of an artifact | the constituent lists that hold its BLAKE3 |
| provenance | testimony naming the artifact, and its containers' provenance (§9.6) |
| testimony admitted | whether a testimony classifies to an origin term and carries its required fields |
| stale properties | a `properties` line by an older op version than the tool's for its mime |
| binding state | an evidence entry's reading reference against the current revisions and surfaces (§14.4) |
| status | bound entries, kinds, modes and standing challenges (§14.5) |
| demand | §14.7 |
| staleness of a pass | `pass.ontology` against the current pin, for the scopes a changed term reaches |
| complete extent, section closure, paragraph numbers | `in` and `ord` |
| the export, the remainder, the envelope | §15 |
| sensitivity | the tier of the instance a line lives in |

## 13. Passes and the owner

### 13.1 Passes

13.1.1 A pass is one author and one verifier over one artifact, one set of constituents of a container (its `with` names the container's pass), or one concept file. The author and the verifier MUST differ. A judgment exists only once both have signed; there is no draft state in the trees.

13.1.2 A pass line: `{"at": "whole", "predicate": "pass", "value": {"id", "by", "verify", "ontology", "date", "note"?, "with"?}}` in an artifact file; the same value with `subject` in a concept file. `ontology` is the pin (§11.8). An id is `p<n>`, the lowest number free after every signed and open pass on the subject.

13.1.3 A correction pass swaps roles, so no correction is self-verified. A pass MAY start from a proposal op's output (§10.5) and accept or correct it.

### 13.2 Staging and signing

13.2.1 An open pass stages its lines under `.ath/passes/<subject>/<id>.jsonl`, outside the trees. Nothing under `corpus/` or `ledger/` exists unsigned.

13.2.2 Signing lays the staged lines over the stored lines by identity (with `complete` where the author asks), in canonical order, and runs G1–G3, the per-file and the per-term lints over the result. Any blocking finding refuses the signature and leaves the staging untouched. A staged line at an existing identity with different content is a correction with a lineage row `by: pass:<id>`. Abandoning a pass discards its staging.

### 13.3 Complete

`complete` is written only on an asserted tree. Under it, every word of the surface must lie in a scope or in chrome, and G3 blocks (§17.1). On a derived tree, completeness is the export's remainder (§15.1).

### 13.4 L7 — the reading against the bytes

13.4.1 For every reading, the body is compared with the surface at its `at` after the scope's conventions and designators are applied — per aspect. Divergence is listed for a human; it is never resolved automatically. Where the root declares no derivation, every reading is listed for inspection.

13.4.2 **One normaliser** serves L7 and quote binding (§14.4): Unicode NFKC; typographic quotes and dashes folded to ASCII; no-break space to space; whitespace runs collapsed. A second, **squashed** comparison removes whitespace and hyphens. Punctuation is content: a dropped period diverges.

13.4.3 **text.** Designator fields are removed from the surface's head or tail; footnote marks and bullets are treated as the scope's conventions declare; the bodies are compared token by token (longest common subsequence), then squashed.

13.4.4 **cells.** Each cell of the reading must occur as a contiguous run in the row's column-aware words.

13.4.5 **tex.** Control words map to their symbols (`\sum` → ∑, `\times` → ×, the Greek alphabet), braces and script marks drop, a label the scope's designator names drops from the surface; the multisets of letters, digits and operators must agree. A cell written as TeX is compared the same way.

### 13.5 Rulings

13.5.1 A **ruling** is the owner's final judgment on something the tooling derived. Rulings are lines in `<blake3>.rulings.jsonl`, written `by: owner` with a `date`. A rulings file holds exactly two predicates:

| predicate | at | meaning |
|---|---|---|
| `inspected` | a scope | `{rev, diverges: "accepted", why}` — an accepted L7 divergence, bound to the reading's revision; a re-read lapses it, so L7 converges on re-run |
| `disowned` | `whole` of a testimony | `{why}` — the owner judges the testimony wrong; it stays in provenance, marked, and evidence anchored into it is held |

13.5.2 Revoking a ruling removes its line with a lineage row.

13.5.3 Acquiring bytes from outside, deleting, retiring a standalone copy, moving an artifact between an extension and its base, repinning a base and changing an ontology are owner-gated verbs of the tool (§19), not rulings.

13.5.4 Owner prose has no place in the instance: anything worth saying about an artifact or a concept is a claim with evidence.

## 14. The ledger

### 14.1 Concepts

14.1.1 A concept is a real-world thing with a slug, its file `ledger/<slug>.claims.jsonl`. Its lines: `term` (one per term it is), `manifested_by` (one per scope that manifests it, at any grain — a book, a chapter, a figure, a list item), `part_of`, and one line per claim. Artifacts are evidence for a concept, never its identity.

14.1.2 A concept file carries its ledger passes as `pass` lines with `subject`. An authored claim carries `pass`; a harvested claim carries `by: harvest:<term>@<pin>`.

### 14.2 Claims and edges

14.2.1 A claim is `{subject, predicate, value | object, qualifiers?, evidence, <authorship>}`. An **edge** is a claim whose `object` is a slug; `qualifiers.as` keeps the value the bytes printed.

14.2.2 Predicates with fixed meaning:

| predicate | meaning |
|---|---|
| `same_as` | two slugs are one concept; it merges the moment it derives `confirmed`, with one lineage row |
| `supersedes` | an artifact or concept replaces another; anchors carry across as §7.8 says |
| `challenges` | names a claim by identity key and content hash, with evidence against it |
| `presence` | `none`: the thing is not attested where it would be |
| `blocked` | names the demand a claim blocks and why; the only demand that is authored |

### 14.3 Evidence entries

14.3.1 A claim carries `evidence: []`. Each entry is authored once and bound by verify:

| field | meaning |
|---|---|
| `anchor` | `corpus://<blake3>?<at>[&<aspect>]` — tight: the smallest scope the quote lies in, one cell of a table, never a region; a route through a container canonicalises to the constituent |
| `quote` | verbatim from the reading or surface the binding names; an elided composite (`…`) or a typographic re-take is refused; `prefix` and `suffix` disambiguate a repeated string and extend a long one |
| `kind` | the source's grade: `authoritative`, `direct`, `incidental` |
| `mode` | how the entry supports the value: `stated`, `inferred`, `reported`; `reasoning` is required when it is not `stated` |
| `reading` | the binding, stamped by verify (§14.4) |

14.3.2 A `stated` entry supports a string value only where the value is within its quote after normalisation; otherwise the claim is `inferred` with `reasoning`.

### 14.4 Binding

14.4.1 `reading` is one of:

- `b3:<16 hex>` — a stored reading's revision;
- `derived:<op>@<version>[ <argument>]` — the surface op yields the quote's surface;
- `line:<predicate>[ <field>]` — a value read off a `manifests` or `properties` line at the anchor;
- `null` — held.

14.4.2 An entry is **bound** when its anchor resolves to a scope, its binding yields a surface there, and its quote (with prefix and suffix) is in that surface under the normaliser (§13.4.2), plain or squashed. It is **held** when its binding is `null`, when the revision it names no longer exists, or when it is anchored into a disowned testimony. It is **flagged** otherwise, with the reason.

14.4.3 Three links are checked separately: claim to reading (the quote is in the bound body), reading to bytes (L7), value to quote (the verifier's judgment).

### 14.5 Status, derived

| status | when |
|---|---|
| `confirmed` | a bound `authoritative` entry, or two bound `direct` entries from distinct artifacts, and no standing challenge |
| `provisional` · `inferred` · `reported` | the bar is not met; the mode of the best bound entry decides — `stated` gives `provisional` |
| `disputed` | a challenge stands |
| `conflicting` | a bound sibling claim disagrees on a predicate the concept's term declares `functional` |
| `unsupported` | no bound entry — a hypothesis is a claim in this state; a proposed concept is one whose lines are all here |
| `refuted` | unsupported with an upheld challenge; it stays, so harvest does not infer it again |

### 14.6 Harvest

14.6.1 A term's `concept` lines are its harvest rules: `{term, key?, claims, group?, slug?, case?, extract?}`. For every scope manifesting the term, harvest mints the concept keyed as declared and writes one claim per mapped predicate, with an entry anchored at the evidencing scope or cell and bound to its surface, `by: harvest:<term>@<pin>`. A repeat appearance is another entry on the one claim. Harvest never cites two sources in one entry. Change a term's map and the ledger follows.

14.6.2 A map names scopes by **term** (`author`), a field as `term.field` or `properties.field`, a field source of the scope's own node as `@<source>` (§10.6), an edge as `term → concept-term`, a cell by index, or `*` for every row. A selector is never a map value or key.

14.6.3 **Keys.** A concept line without `key` augments the concept the enclosing document manifests. With a key, harvest mints one concept per holder of the key under each scope of the owning term: every scope of the key's term, every row the `rows` term manifests for a column key, the owner scope itself for a field source or a `properties` key. A claim resolves within the holder, then within its parent — never in `whole`.

14.6.4 **Slugs.** `slug` is a template over `{term}`, `{key}` and `{1}` (the first group of `extract` applied to the key), default `{term}-{key}`; every non-alphanumeric run becomes `-`; lowercase unless `case: keep`.

14.6.5 **Edges.** When an edge's left side is a term whose scopes contain the target (`post → forum-post`), one edge per scope, cited by the target concept's key; a value edge is cited by the cell or text that names it.

14.6.6 **Key-value tables and text.** A reference that is one of the term's `keys` reads the row whose first cell is that key and yields its second cell (`-` and empty yield nothing); a name on the term's `cells` line reads that index of the first `cells` reading at or under the scope; a reference that matches the leading `Key` of a line in a text reading yields the rest of the line. Entries bind at the row (`&cells`) or the block (`&text`).

14.6.7 **Grade.** Harvest writes `authoritative` when the concept is `manifested_by` a scope of the cited artifact and the predicate is one the concept's term `owes`; otherwise `direct`. Sentinel values yield nothing.

### 14.7 Demand

Derived, never stored:

- a held entry enqueues a reading pass over its unit;
- an unmet `owes` is a search;
- an unsupported claim is an acquisition;
- a stale pass is a re-run;
- an unmet `expects` is a soft finding;
- an extension's minted term, or its disagreement with a base line, is demand on the base (§4.2.8).

An absence the bytes print ("–", a missing row) is demand, not a defect. Only `blocked` is authored.

## 15. Export

### 15.1 The markdown proxy

15.1.1 The proxy is an output, never a record and never a citation target. It walks the tree in `ord` and emits each scope through its term's `renders` rule, designators re-emitted from fields, every block prefixed by its `at`.

15.1.2 Its header names: the authority (the bytes); every pass and its ontology pin; the inspected divergences; the chrome; and the **remainder** — on an asserted tree, the words outside every scope and chrome; on a derived tree, the characters outside every unit and declared chrome, of the total.

15.1.3 It is lossless back to the bytes and never breaks on a new term.

### 15.2 Provenance view

An artifact's provenance chain (§9.6) is exported beside the proxy on the owner plane, never on the public plane unless its testimony lies in a public instance.

### 15.3 N-Quads

15.3.1 Every stored line maps to one N-Quads statement and back, byte-identical: the subject `corpus://<blake3>?<at>`, `ledger://<slug>` or `ontology://<term>`; the predicate `urn:athenaeum:ns:<predicate>`; the line's payload as a literal typed `urn:athenaeum:ns:json`; the graph its authorship — `pass://<subject>#<id>` for a pass, `op://<name>@<version>` for an op or a harvest, `owner://<subject>` for a ruling; an ontology line's graph is `ontology://<term>`.

15.3.2 A term's `aligns` IRIs are asserted as its classes in the projection.

## 16. Planes and publication

16.1 Serving an instance serves the instance and everything it builds on, filtered by plane. The **public plane** serves the `public` instances of the chain, and the claims whose derived status is `confirmed`. An **audience plane** serves those plus every instance whose tier the audience's grant names, under the same status filter unless the grant names another. The **owner plane** serves every instance of the chain, every status, the rulings, provenance, demand and every finding.

16.2 Read-only is normative. A consumer reads `ledger://`, materialises `corpus://` only for what the ledger asserts, never cites a generated view, and pins the reproducibility tuple — the commit of every instance in the chain and the ontology pin — when it freezes a build.

16.3 A server re-reads the instances per request and holds no state of its own.

## 17. Lints

### 17.1 Generic

A failing generic lint blocks the pass from signing.

| lint | checks |
|---|---|
| G1 unit | every `reads_as` sits at a scope with a `manifests` whose term reads that aspect |
| G2 tree | every `in` resolves to a scope; `ord` contiguous from 0 per parent; no cycle; every non-physical scope reachable from `whole` |
| G3 cover | on an asserted tree, the words outside every scope and chrome are listed; under `complete` they block |
| G4 cite | every anchor resolves; every quote is in its bound surface; a bound revision that no longer exists is flagged |

### 17.2 Per term and per file

| lint | checks |
|---|---|
| per term | `reads` satisfied; required fields present; designators match the surface under `where` and `pattern`; `expects` met (soft); `owes` met (demand); the term's `lint` lines; L7 per aspect; `matches` agrees with a stored root |
| per testimony | it classifies to a term refining `testimony`; it carries every field its origin term requires |
| per file | no undeclared field; no derivable value stored; no aspect outside `text`, `cells`, `tex`; one writer per file; sorted; pass references resolve; every pin known; `testimony` only on a testimony artifact, by an op, naming a subject in the chain; `properties` only by an op; no stale `properties` (soft) |

### 17.3 Term lints

A term's `lint` lines are declarative checks over its scopes, composed from:

- `{"every": "<field>", "names": "<term>"}` — every value of the field names a scope of the term by designated address (a table of contents row names a heading);
- `{"contains": "<term>", "at_least": <n>}` — every scope of the term contains at least *n* scopes of the term named;
- `{"field": "<field>", "agrees": "properties.<key>"}` — the field equals the property.

### 17.4 Ontology lints

`ontology lint` refuses: a `reads` value outside the four; a `derivation` that does not parse, names an unregistered op or carries an argument the op refuses; a selector the root family's language rejects; a `concept` map naming a selector; a `matches` without `mime`; a write at an ontology identity a base holds; a `refines` cycle.

## 18. Custody

Custody is where bytes live and how a BLAKE3 finds them. The trees are tracked text; custody is the byte plane beneath them, machine-specific and untracked. An artifact's identity is a tree fact; its residence is a custody fact, and the two never touch: the same bytes may live standalone, inside a container, on an attached share or in several places at once, and no line changes when they move.

### 18.1 The contract

1. **An id resolves to its bytes.** Given a BLAKE3, the instance produces the bytes through whichever route holds them. Every route yields identical bytes; a resolver may take any.
2. **Residence is derived, never stored.** No line says where bytes live. Every route is computed from declared locations, constituent lists or derived indexes.
3. **The index proposes, the hash disposes.** A derived residence map may route a read under its staleness pins, but every act that mints, copies or retires bytes — ingest, adoption, replication, retiring a copy — verifies the full BLAKE3 first. A wrong map can at worst misroute a read.
4. **Nothing normative depends on custody state.** Location indexes and caches are regenerable deployment state. A consumer missing a row recomputes it when the bytes are in hand, or reports it.

### 18.2 Routes

An id resolves through five classes of route, in this order; a declared cost (§18.3.4) reorders within a class, never across classes:

1. **the co-located store** — `corpus/bytes/<b2>/<blake3>` in the instance, then in each base (§4.3.4);
2. **other store locations** — content-addressed trees the tool writes, declared in the custody file;
3. **attached locations** — trees whose files stay in place, resolved through the location index (§18.4);
4. **the constituent route** — bytes streamed out of a container through its constituent list; a constituent may have no standalone copy at all;
5. **remote hydration** — a store location with a remote transport, pulled local on demand.

### 18.3 Locations

18.3.1 An instance's custody is declared in `custody.yaml` at its root, untracked:

```yaml
locations:
  - name: bulk
    kind: store                    # a content-addressed tree the tool writes
    path: /mnt/slow/bytes
    place:
      mimes: [application/x-openzim]
      origins: [map-extract]       # origin terms: bytes whose testimony classifies here land here
  - name: shares
    kind: attached                 # files stay in place
    path: /mnt/shares/media
    manifest: true                 # the host's residence scanner presents a manifest (§18.5)
    cost: 20
  - name: offsite
    kind: store
    remote: rclone:offsite-bytes   # a transport, not a layout
floors:
  document: 2                      # redundancy floors by root or origin term (§18.6.3)
```

18.3.2 **Store locations.** A store location is a `<b2>/<blake3>` tree at another root. Placement directs new bytes there: an `origins` claim (the origin term the delivered testimony classifies to) beats a `mimes` claim, which beats a location declared `default: true`, which beats the co-located store; within one kind of claim, declaration order breaks ties.

18.3.3 **Attached locations.** An attached location is a tree the tool reads and never rewrites: files keep their names and paths. Attesting it streams and hashes the tree — or reads its presented manifest — and writes the location index; from then on its files resolve by bare id. Ingesting an attached file in place (`ingest --in-place`) writes its subject without copying its bytes, the full BLAKE3 verified at ingest. An index row pins `size` and `mtime`; a mismatch makes the row stale, and the route reports the bytes unresolvable rather than serving bytes that may no longer match their id.

18.3.4 **Cost.** A location MAY declare `cost`, a non-negative integer, lower being nearer. Undeclared, cost follows the route order. When bytes must move, the resolver takes the cheapest residence whose pins verify, falling through on staleness.

### 18.4 The location index

The location index maps a BLAKE3 to `(location, relpath, size, mtime)` with the row's provenance — `computed` (the tool hashed the bytes) or `presented` (a host's claim, §18.5) — and, for a presented row, the manifest generation it came from, so re-attesting skips generations already read. It persists under `.ath/`, because rebuilding it needs the bytes; deleting it is always safe at the cost of one attest per location.

### 18.5 Presented manifests

18.5.1 An attached location on another host MAY present its own manifest, maintained on that host against its local filesystem by the residence scanner. The scanner's identity model — `(dev, ino) → (size, mtime) → BLAKE3` — is sound only where inodes are real, so it runs where the bytes are: an unchanged stat is never re-hashed, a rename is a new path on a known identity, hard links collapse to one hash, and an interrupted scan resumes per file.

18.5.2 The manifest is published at the location root by temp-then-rename at each generation, so a reader only ever sees a whole generation. Its format is the scanner's own versioned contract, outside this specification. A manifest carries the stat facts of each identity and an advisory mime claim sniffed once when the bytes were hashed; ingest's own sniffing (§10.1) is authoritative.

18.5.3 Presented rows serve resolution under the same pins as computed rows; every act that mints or copies verifies the full hash. A deployment MAY re-verify presented rows by an ordinary attest. Scrubbing for decay is the scanner's duty on its host.

### 18.6 Custody acts

18.6.1 **Locate** answers, for a bare hash, where those bytes reside — every store, the location index, constituent routes, remote objects — ordered by cost, and whether a subject exists. It works for a hash the instance has never ingested. A hash with several residences is the deduplication surface: listed, never deleted automatically.

18.6.2 **Move** relocates a standalone copy between store locations by copy, verify, then remove: the bytes are copied under a temporary name, the full hash verified, the copy renamed into place, and only then the source removed. A failed verify leaves the source untouched. Attached files never move; a constituent with no standalone copy has nothing to move.

18.6.3 **Adopt** copies an attached file into a store under move's contract and leaves the original in place; from then on the store copy is served. Removing the original is a separate act.

18.6.4 **Retire** removes a standalone copy once another route resolves the same bytes, the full hash verified through that route first (§9.7). Testimony bytes are never retired.

18.6.5 **Floors.** `floors` names, per root or origin term, how many distinct locations should hold a route to an artifact's bytes — a standalone copy in a store, a container residence, a remote object and an attached file each count once. Across an extension and its base the highest floor wins. Below-floor artifacts are a health finding; a removal that would break a floor names it. Nothing enforces a floor at write.

18.6.6 **Caches.** A cache sweep never removes the location index or any index whose rebuild needs bytes.

## 19. The tool

### 19.1 Profiles and tiers

19.1.1 Every verb has a tier: `read`, `write` or `admin`. A caller runs under one profile: `owner` (admin), `agent` (write) or `reader` (read). A caller at a terminal is `owner`; a caller under an agent or a script is `agent`. A profile may be narrowed by flag or environment, never widened. A verb above the caller's tier does not exist for it.

19.1.2 Every mutating verb needs an **actor**: `ATH_ACTOR`, or the login name at a terminal. Without one the verb is denied. The actor is recorded in the receipt, in staging and in the history.

### 19.2 Writes

19.2.1 Every write is atomic. Bytes are written under a temporary name, verified against their BLAKE3 and renamed into place; a line file is rewritten under a temporary name and renamed. A verb that is interrupted leaves the instance as it was, or with every write it completed whole. Delivered files are copied, or for a file on an attached location left in place (§18.3.3), and never removed by the tool.

19.2.2 Mutating verbs take named locks under `.ath/locks/`; a held lock is `busy`. Every mutating verb appends its actor, arguments and outcome to the history under `.ath/`.

### 19.3 Envelope and exit codes

19.3.1 With `--json`, every verb prints one envelope: `{ok, cmd, version, elapsed_ms, data | error}`. A verdict — lint findings, failed bindings — is an `ok` envelope with exit code 1, never an error.

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
| 78 | config: `athenaeum.yaml`, a base, the custody file or the ontology is broken, or the tool cannot serve the chain (§4.3.3) |

### 19.4 Verbs

| verb | tier | contract |
|---|---|---|
| `instance init [--extends <path>]` · `instance show` · `instance check` | write · read · read | init writes `athenaeum.yaml` and the empty trees — for a standalone instance with the terms §11.9 names, for an extension pinned to its base's current commit; show prints the instance and what it builds on; check verifies the chain, its pins and its configuration |
| `instance repin` | admin | moves the base pin to the base's current commit and reports what the move makes stale (§4.2.2) |
| `ingest <file…> [--testimony <file>…] [--in-place]` | write | sniffs, records `properties`, makes subjects of constituents one level deep, admits or refuses testimony before any byte is placed, writes the receipt; the same bytes again add testimony only |
| `properties sweep [--stale]` | write | writes superseding `properties` lines where the op version is older than the tool's |
| `resolve <anchor>` | read | the bytes, the surface or the reading at an address, through routes |
| `tree <subject>` | read | the scope table in `ord`; a designated or positional address to its intrinsic `at` |
| `provenance <subject>` | read | the provenance chain (§9.6) |
| `claims show` · `claims sort` | read · write | a subject's lines across the chain; rewrite a file in canonical order |
| `pass open` · `stage` · `sign` · `abandon` · `show` | write (show: read) | §13.1–§13.2 |
| `propose <op> <subject>` | read | a proposal op's candidate lines (§10.5) |
| `inspect show` · `accept` · `revoke` | read · admin · admin | L7 findings; write or remove an `inspected` ruling, confirmed at a terminal |
| `disown <testimony> --why <text>` · `disown revoke` | admin | write or remove a `disowned` ruling |
| `harvest <subject>` | write | mint and update harvested concepts and claims (§14.6) |
| `verify [<subject>…]` | read | bindings, status, demand, stale passes |
| `lint [<subject>…] [--all]` | read | §17 |
| `ontology list` · `show` · `rules` · `pin` · `lint` | read | the terms, a term's lines, a scope's effective rules, the pin, §17.4 |
| `export markdown <subject>` · `export nquads [<subject>]` | read | §15 |
| `serve` | read | the planes over HTTP (§16) |
| `location attest` · `locate` | write · read | §18.3.3, §18.6.1 |
| `location move` · `adopt` · `retire` | admin | §18.6.2–§18.6.4 |
| `log` · `whoami` | read | the history; the caller's profile, actor and instance root |
