---
spec_id: ATH-CORPUS
title: "Corpus Specification"
version: 3.2
status: current
license: "CC BY-SA 4.0"
date_created: 2026-05-24
date_modified: 2026-07-21
---

# Corpus Specification

A **corpus** is the foundation layer of the Athenaeum system: a content-addressed archive of captured artifacts, represented as markdown records. This document is its complete specification, in two parts. **Part I (§1–§11)** is the normative data contract — every record in every corpus conforms to it, and tooling across the system cites its section numbers. **Part II (§12)** is the implementation guide: non-normative notes on how the reference pipeline produces conforming records. Two appendices follow — the glossary (Appendix A) and a non-normative content-type taxonomy (Appendix B).

The corpus sits beneath the ledger layer, which interprets it through `corpus://` functional URIs — see [`athenaeum.md`](athenaeum.md) for the system architecture, [`ledger.md`](ledger.md) for the knowledge layer, and [`codex.md`](codex.md) for the codex contract.

**Version 2.0** removed the corpus's interpretive classification system — the `composite` umbrella, the classify block, section-scope composites, the `concept` context namespace, and the interpretive `reference` emission path — in favor of the ledger layer: a record describes its bytes, retrieval, and faithful form; what its content *means* is asserted one layer up, with evidence pointing back down. Removed sections are **tombstoned in place** (numbering preserved, successor named) rather than renumbered, so 1.0-era citations of this spec still land somewhere true.

**Version 2.1** — the **containment amendment** — decoupled records from standalone artifact files. Every transport is now self-contained (the `decomposable` disposition and the `artifact_kind` declaration retire): a raw archive drafts as an embed manifest, and any declared member may be **promoted** to a first-class record whose bytes remain inside the container, resolved by streaming (§2, §1.2, §8.1). No existing record changes shape (§12.17).

**Version 3.0** — the **derivation revision** — completes the movement 2.1 began: a record stores only what is **authored** (the normalize pass's faithful form) or **attested** (ingest-stamped byte-facts), and everything mechanical is **derived, addressable, and reproducible**. The `draft` stage retires: its fact-stamping becomes ingest **attestation**, its content extraction becomes resolver **derivation ops** (§6.2), and its body-writing becomes the normalize pass's job — mechanical (a *shaper*) where a declared form mapping makes the shape deterministic, interpretive where it does not. The stored table of contents retires with it: TOC grouping becomes a derived rendering over **structural segments** (byte-marks only, §4.3.2.3), and the freed **section block** becomes the surface of the new **form axis** (§4.4.1, §7.8) — record- and span-scope structural form, the fourth classification axis. Embeds close to *"this asset is part of this record's capture"* (§4.3.1.4); referenced-but-not-contained content materializes through lineage-chained resolution (§6.2), derived and never stored. Media containers are attested as track manifests (§1.2). Removed and reshaped sections are tombstoned in place exactly as 2.0 did; the 2.0 tombstones themselves are untouched — the form axis is *not* the classify block returning (§7.8).

**Version 3.1** — the **layers amendment** — retires the last stored lifecycle field: `status` leaves the frontmatter, and a record's state becomes **derived from what the record demonstrably carries** (§4.1) — every record is **attested** at birth (the artifact's *proxy*: complete and consumable through the derivation ops), a record is **formed** where a named form contract governs a stored rendering, and **authored** where the editorial vouch is written. `normalized` dissolves into *formed + authored*; `stub` dissolves into the plain record. Two ideas carry the amendment: **formless is the zeroth form** — the identity contract ("the faithful representation of these bytes is the bytes"), valid indefinitely, prescribing nothing, with deliberately no catch-all shape and no default — and **forms are a goal, not a rarity** (§7.8, amending 3.0's "rare by design"): the form namespace is the corpus's *rendering-contract library*, adopted lazily where benefit demands, so `origin` says where bytes came from, `mime` says what container they arrived in, and `form` says what markdown shape renders them faithfully. Citability re-keys accordingly — ledger verification checks evidence against **verifiable surfaces** (stored renderings, engine-pinned derived content, authored prose) rather than against a status flag (`ledger.md` §6.3, §13.2) — and the normalization queue becomes **standing demand**, never a backlog (§8.5). Migration: §12.19.

**Version 3.2** — the **derived-editorial amendment** — retires the stored interpretive editorial fields: a record's display `title` and `description` become **derived, never stored**, resolved from **role-marked schema fields** (`role: title` / `role: description` on `extended_fields` declarations, §4.2.3) by the precedence **artifact → origin → form** — each later layer overriding the earlier, latest block winning within a layer — so every record carries an honest mechanical title/description from birth, no LLM pass required, and the frontmatter pair survives only as an **optional deliberate override**, preferred absent (§4.2.1). The interpretive editorial prose relocates onto the **form section header** — the vouch's new home — and with it the **authored state dissolves into the form layer** (§4.1): a formless record derives exactly what its marked fields say; genuinely interpretive prose requires a form or belongs to the ledger (the 2.0 line about meaning, one layer up). §7.8's field rule softens accordingly: *mechanically derivable* becomes a preference, not a requirement — a non-derivable field is interpretive by design, disclosed by the touch chain. (*Terminology:* the **authored layer** as an ownership name — the half of the record the normalize pass writes, §4.4.7 — is unchanged; what retires is authored as a record **state** keyed on frontmatter fields.) Migration: §12.21.

**Version 3.3** — the **terminal-forms amendment** — makes §7.8's destiny split machine-readable: *formless-permanently* becomes a declarable judgment, no longer prose. Two **terminal contracts** join the form library (§7.8): **`form/passthrough`** — the identity contract named and assertable: the artifact is its own terminal rendering, better than any markdown shape on both fidelity and token economy, so the contract prescribes the **absence** of a stored rendering (content zone = structural byte-marks only; lint inverts — a stored rendering under a terminal contract is the violation) — and **`form/manifest`** — the container specialization: the members are the content, conformance binds the attested member embeds, and the editorial header vouches the container. A terminal contract is **not** the catch-all §7.8 forbids: it prescribes no shape — it records the earned judgment that no shape exists, exactly as a named form records the judgment that one does. Declaration rides the overlay grain (mime `form:` default, origin override — the `disposition:` pattern), with one derivation: a **`disposition: manifest` record with no rendering contract declared stands under `form/manifest`** — the disposition already IS the terminal judgment, and the amendment refuses to make owners state it twice; per-record assertion (§4.4.6) covers exceptions. Consequences: derived state gains a fourth reported value — **terminal** — beside formed / rendered / proxy (§4.1), so *proxy* narrows to mean genuinely unassessed-or-awaiting; a terminal record **never gates and never enters the queue by default** — the pass gate is trivially satisfied, an enqueued terminal record drains to a **no-op finalize** unless the request explicitly asks for re-evaluation, and the licensed residue (the optional whole-record opener carrying the editorial vouch, embed/segment descriptions) remains deliberate describe-pass work, never demand (§8.5); and the ledger's evidence doctrine sharpens — a terminal record is a **complete source**, its derived surfaces permanent and full-strength, and the normalize-demand signal keys to formless-*for-now* alone (`ledger.md` §6.3, v1.3). Migration: §12.23.

---

# Part I — The contract (normative)

## 1. Overview

### 1.1 What this is

A **corpus** is a content-addressed archive of captured artifacts, accessed through faithfully represented markdown proxies called **records**. Artifacts are deconstructed into addressable segments and normalized to text, either losslessly or by description. A record classifies its artifact **mechanically** — what the bytes are (media type) and where they came from (origin); what the content *means* is the ledger layer's concern ([`ledger.md`](ledger.md)), asserted there as claims whose evidence points back into the record.

A record is a single markdown file. The YAML frontmatter at its head carries a small bytes-identity header — what these bytes ARE (their hashes), the editorial summary, the provenance chain of processing passes. The **record body** below the frontmatter is organized into three **zones**: a **metadata zone** declaring what the artifact is, where it came from, and what assets it embeds; a **content zone** carrying the rendered content as sections and segments; and an **annotations zone** carrying observations about the record. Each zone holds a small set of HTML-comment block families; §4.3 specifies the grammar.

### 1.2 The transport model

Every captured file is a **transport** — a media-type-shaped container — that carries **content**.

- A transport's **intrinsic information** surfaces in the record's metadata zone — primarily in the artifact block for transport-intrinsic fields.
- A transport's **content** decomposes into a flat sequence of addressable segments in the record's content zone. Each segment carries one of four **content atoms** (text, image, audio, video) — or is a **structural segment**, a body-empty byte-mark carrying no atom (§4.3.2.3) — and an **address** indicating its location inside the transport.
- Every transport is **self-contained**: it produces a single record. When it contains a **nested transport**, it lifts that nested transport's intrinsic metadata into the outer record's artifact block and addresses its content per stream / per member, while an asset it merely references is described as an embed in the metadata zone. An ordinary single-content file (a plain HTML page, a PDF) simply has no nested transport to lift. A **raw archive** — a transport whose content is *other transports* — is attested as an **embed manifest**: every member becomes a content-addressed embed (the member's `transport:` byte-hash + its member address) and the content zone stays empty (§12.4). *(2.1: the schema-declared disposition — `artifact_kind`, with its `decomposable` explode-at-ingest alternative — is removed; §7.1.)*
- A declared member is thereby **promotable**: because its embed records byte identity and address, it may later be minted as a first-class record of its own (**promotion**, §8.1) without its bytes ever leaving the container — a lookup of the promoted `id` streams them out through the container's address scheme (§2). Containment nests (a promoted member may itself be a container), and **residence is invisible**: the same bytes may live standalone, inside a container, or both, and no record changes when they move (§2).
- *(3.0)* **Container-vs-transport is a declared judgment, not a derivable fact.** The bytes cannot say which they are — a `.docx` is *provably* a zip, and reading it as one would be wrong. A mime schema therefore declares a **`disposition:`** (§7.1): **`manifest`** — the members ARE the content (archives, mailboxes, multi-entry text containers, media containers): the content zone holds only the container's own byte-marks, and every member is attested as a **manifest embed**, promotable; or **`work`** — one transport whose content decomposes as units, and whose internal member files surface as **exposable embeds**: addressable and promotable, but *not* the content — a `.docx` is better read as one work; its pasted photo is an exposable embed, its `word/document.xml` is not independently meaningful. The authoring criterion, normatively: **are the members independently meaningful transports?** An MKV audio track is — the transcript lives on it; OOXML internals are not. (EPUB's 2.x `self_contained` judgment — "an EPUB is one work, one record" — is this key's implicit ancestor, now explicit: `disposition: work`.) The mime schema declares the format's default; an origin overlay MAY override it for a producer whose use of the format deviates (§7.2). The disposition is always stamped and auditable, never sniffed per record. *(The 2.1 removal of `artifact_kind` stands — that key routed explode-at-ingest, which stays gone; `disposition:` declares attest/read shape, and nothing explodes.)*
- *(3.0)* **The member-vs-unit rule.** A **member** is a transport with its own MIME and standalone byte identity — attested as a manifest embed or exposable embed per the disposition, promotable either way. A **unit** is content *within* one transport — a message in a chat transcript, an entry in a log — reached by unit ops (`turn=`, §6.2) under a form mapping (§7.2), never declared as an embed. Unit-structured single transports are **not containers**: an NDJSON/JSONL stream, a location-history JSON, a health-export XML/CSV, a GPX track decompose as units of one work (`form/log` territory, §7.8), not as members.
- *(3.0)* A **multi-track media container** (MP4/ISOBMFF, Matroska, and kin) is a raw archive in the strict sense — a transport whose content is other transports — and is attested the same way: a **track manifest**. Each elementary stream becomes a content-addressed embed addressed `stream_id=<id>` (video stream, audio stream(s), text-based subtitle track(s)), and an attached picture is an ordinary embed; the artifact block carries the container facts (duration, per-stream codecs, dimensions). The content zone carries exactly one thing: the container's **chapter marks** as structural segments (§4.3.2.3) — chapters are byte-marks of the *container* (an MKV `Chapters` element, an MP4 chapter track; both encodings project to the same marks, the mime schema pinning which encoding wins), marking the shared timeline no single track owns. Tracks are **promotable on demand, never exploded**: a promoted track record's bytes materialize through the container (`stream_id=` transform — the `part=<N>` precedent), no bytes copied; extraction semantics are pinned by the mime schema (the mbox `msg=<N>` precedent) so member bytes are deterministic (§11 flags the demuxer-determinism engineering risk). The audio-track record owns the transcript (`?transcribe`, §6.2); the video-track record owns frame work (on-screen text as `text/ocr` is faithful; what-a-frame-*shows* stays `description:`); a text-based subtitle track projects faithfully as (time_range, text) segments. Tracks inherit the container's chapter marks at **read time through lineage** (§6.2) — never copied, because the track's own bytes do not carry them (§4.3.2.3, the byte-mark rule). A **single-stream artifact** (a bare MP3, a JPEG) has no member transports to declare and stays a single `work`; a single-*track* media container nonetheless stays `disposition: manifest` — **default-member resolution** (§6.2) makes the bare op transparent (`?transcribe` on a single-audio MKV needs no `stream_id=`), so the disposition never flips per record. The same-video composition — tracks threaded over the shared timeline — is a read-time derived view joining on (lineage, time), exactly as a cross-platform conversation view joins on (ledger identity, time): same tuple, same composition layer, no media-specific logic stored anywhere.
- *(3.0)* The manifest family extends along two more axes, no new machinery. **Multi-entry text containers** are the mbox precedent generalized: a multi-card VCF is a manifest of `text/vcard` members at `card=<N>` (`BEGIN:VCARD`/`END:VCARD` delimiter-pinned extraction, so member bytes are deterministic and promotable — §12.11), an ICS calendar of `VEVENT` entries at `entry=<N>` likewise. **HEIF/HEIC** is the media container on the image axis: image items attested at `item=<id>`, and an Apple **Live Photo** is the container's *declared primary* still (the `pitm` primary-item box — a byte-fact) plus its paired video track, both reachable bare through default-member resolution (§6.2): `bbox=` acts on the declared-primary still, `time_range=` reaches the motion component. A **motion photo** (an MP4 appended inside a JPEG's bytes) is the nested-transport lift above — the inner video attests as an embedded transport of the JPEG work — not a new mechanism. Formats that arrive later slot into the same strategies: 7z/rar/dmg join the zip-manifest family, PST/OST and WARC join the mbox precedent, when a real capture wants them.

### 1.3 The atom / segment model

A record body's content zone is a sequence of **sections** (form spans, §4.3.2.1 — rare; present only where a form is declared) and **segments** (the read-order rendering). Each content segment carries:

- One **content atom**: `text`, `image`, `audio`, or `video`. Only `text` segments carry a segment body. Segments of the other three atoms are positioning markers — they declare where in the reading order an asset appears, and link to a matching embed (by address membership, §4.3.1.4) or materialize through the resolver — and their segment body is empty.
- An **address** specifying the segment's location inside the transport, in a scheme determined by the media-type schema. Addresses compose, so that chains can form from transport to atom to region (a region within a frame within a video).
- Exactly one **atomic classification**, declared on the opener line in the form `<!--segment <atom>/<id>-->` (or bare `<!--segment <atom>-->` for unclassified-but-typed segments). Text-atom overlays may declare lossless-shaping behavior — those overlays shape the segment body into a specific lossless form (a markdown table, a transcript, a chat message). When multiple representations apply to the same source region, each becomes its own segment.

*(3.0)* A fifth segment kind — the **structural segment**, `<!--segment structural-->` (§4.3.2.3) — carries no content atom and no body: it is a **byte-mark**, the faithful record that the source itself declares a structural boundary at an address (a heading, an outline entry, a chapter mark, a topic boundary), with a `level:` and an optional `entry:`. The table of contents is a **derived rendering** over these marks — arbitrary depth, zero nesting grammar — never a stored grouping. *(The 1.0–2.x stored TOC — sections as grouping blocks — retires; §4.3.2.1.)*

Two segments may share an address as long as their opener-id differs — same-region stacking is how a record represents multiple valid lossless representations of one source region (a structural mark stacks with the content segment at its address the same way). Segments are addressable from outside the record via functional URIs that carry the segment's address in their query string (§5).

### 1.4 Lifecycle

```
captured bytes              (no identity yet — staging only)
       │
       │ ingest             deterministic: hashes, MIME detection, byte-fact ATTESTATION
       ▼                    (artifact fields, manifest embeds, structural byte-marks, sidecar lift)
    record                  the artifact's PROXY — identity + attested facts; bytes persisted;
       │                    complete and consumable at birth: formless, the zeroth form (§7.8),
       │                    readable through the resolver's derivation ops (§6.2)
       │ normalize          the ONE authoring pass, demand-driven (§8.5): renders the record
       ▼                    under a NAMED form contract — a mechanical shaper where a declared
     formed                 mapping makes the shape deterministic, an interpretive agent where
    record                  not — the form span's header carrying the interpretive editorial
                            fields where the pass authors them (§4.2.3).
                            The preferred citation surface (ledger.md §6.3)
```

Once ingested, the artifact's bytes must remain retrievable by id. Where and how the implementation stores them is its concern; the contract is that a lookup by id produces the bytes. **Promotion** (§8.1) is a second entry point: it mints a record for a container member's bytes, which are already retrievable by id through the container (§2) and are not copied. Re-running any stage is an expected refinement pattern, not a fallback; every stage from ingest onward appends a `touch[]` entry to the record's provenance chain (which `re-stub` may reset, §8.4).

*(3.0: the `draft` stage and status retire — tombstoned at §8.1. Its three duties split cleanly: fact-stamping → ingest **attestation**; content extraction → resolver **derivation ops** (§6.2), computed on demand and cached, so a just-ingested record is fully readable without storing a mechanical body; body-writing → the normalize pass. What 2.x called "the drafted body" was always a pure derivation of (artifact × schemas × tooling) — 3.0 stops storing it and derives it instead, which is the same move 2.1 made for archive members and the tree view.)*

*(3.1: the `stub`/`normalized` statuses retire with the `status` field itself — §4.1. Nothing is pending by default: a record with no stored rendering and no vouch is not an unfinished stub but the artifact's proxy, complete at birth. The lower box of the diagram is where a record goes when a rendering contract or a consumer's demand takes it there — not where every record is headed.)*

*(3.2: the lower box reads `formed`, no longer `formed + authored` — the authored state dissolves into the form layer (§4.1). The proxy's display title/description are already derived from role-marked attested fields (§4.2.3), so the upper box is not just consumable but presentable, with no authoring pass ever required for it.)*

### 1.5 Design principles

1. **Layered foundation.** The corpus is a foundation layer — the truth, the baseline. It depends on nothing; any system that builds atop it depends on the records it produces.

2. **Content addressing.** Every artifact's identity is the blake3 hash of its bytes. Bytes don't change; if they did, the hash would change and the record would be a different record.

3. **Faithfulness.** A record body is a faithful, lossless rendering of the transport's content. Normalization may resolve ambiguity (encoding, broken layout, OCR for scans) but never adds information not present in the source. Descriptive content (a summary of what an image shows, a paraphrase of what was said) is lossy by definition and lives on the matching embed's description field — or, when no embed exists, on the addressing segment's or section's `description:` — **not** in a segment body. Re-segmentation is structural, never editorial. *(3.0)* The same principle governs structure: a **structural segment exists only where the source carries the mark** (§4.3.2.3, the byte-mark rule). A grouping the bytes do not declare — a conversation's per-day break: whose midnight? — is a *read-time rendering* with explicit parameters, never a stored block.

4. **The record body as universal representation.** Every artifact carries a markdown body composed of segments. This projects every modality — text, image, audio, video — into a common representational space. Search, similarity, and embeddings all operate on the body.

5. **Transports declare, content fills.** Format-specific machinery (address scheme, attestation set, derivation ops) lives on the media-type schema. Content-shaping tactics live on origin overlays (per source), **form overlays (per record-scope shape, §7.8)**, and atom overlays (per segment-scope form). The layers don't bleed: an origin overlay that specifies segment decomposition is a category error — it names *where bytes came from* and maps the producer's format onto a form; the form overlay owns the normal form.

6. **Deterministic before LLM.** Capture and ingest are scripts; every mechanical extraction is a **resolver derivation op** — a pure (or version-labeled, §6.4) function of the artifact; and the normalize pass is authored by a mechanical **shaper** wherever a declared form mapping makes the shape deterministic, by an LLM only where judgment is genuinely required. The boundary survives as *who executes*, recorded pass-by-pass in the touch chain (§4.2.2) — not as a lifecycle stage. Interpretation — what content means — is not a corpus stage at all: it happens in the ledger, with evidence citing back into the record.

7. **On-demand derived views.** Cross-cutting aggregates and richer modal projections are computed by walking body blocks and semantic-tagged fields, or by resolving functional URIs — never persisted alongside the record.

8. **Stable identity, mutable metadata, faithful body.** A record's `id` is fixed at capture. Body blocks evolve as attestation and normalization improve; the body content remains faithful.

9. **Offline-first.** Only `capture` requires network access. Ingest, normalize, and URI resolution — including every derivation op — all operate on local data.

10. **Frontmatter is bytes-identity only.** What the bytes ARE (their hashes), how visible they are to authoring tools, how to navigate the provenance chain. Everything else — the title candidates, media-type, origins, issues, extended fields — lives in body blocks because everything else came from a schema decision, and schema decisions are auditable per-block. *(3.2)* The display title/description follow the same rule: they are **derived** from role-marked block fields (§4.2.3) — the frontmatter pair survives only as a deliberate override, preferred absent (§4.2.1). A field is named **bare** when its block opener already identifies its provenance: an artifact block names the format (its MIME), a context block names its namespace (`<namespace>/<id>`), so their fields are `title`/`author`/`severity`, never `pdf_title`/`issue_severity`. A provenance prefix survives only where the opener does *not* carry it — an origin block's `ytdlp_title` (the opener names the source record, not the extraction tool), or a metadata sub-standard the format embeds (`exif_*`, `og_*`). (Prefixing every field was a holdover from when these all shared the frontmatter's flat namespace; once each rides its own self-identifying block, the prefix only echoes the block.)

11. **Classifications are derived, not declared.** A record's classifications list is computed by walking its body — the artifact block yields `mime/*`, qualified origin blocks yield `origin/*`, **qualified section openers yield `form/*`**. The body IS the classification declaration. The same principle applies to issues and to the aggregated URI, timeline, and identifier views (§9).

---

## 2. Identity

Every artifact is identified by the blake3 hash of its bytes — a 64-character lowercase hex string. This identifier is the record's `id` and the lookup key by which the corpus's binary store produces the bytes. The implementation owns where and how the bytes are stored; the contract is that an `id` resolves to its bytes.

An id need not resolve to a *standalone* file. When a captured container's record declares a member as a content-addressed embed (the member's `transport:` hash with a resolvable member address), that member's bytes are retrievable by their own blake3 **through the container**: the implementation streams them out via the container's address scheme, recursively when containers nest. How the route from a bare id to its container is found is implementation-defined, but it MUST be **derived** from the records' embed declarations — never stored on the promoted record (§12.9) — so bytes may move between standalone residence and containment, or be resolvable by several routes at once, without any record changing. Every route to an id yields identical bytes by construction; a resolver may take any.

The `id` field is bare hex with no algorithm prefix because the algorithm is invariant. All other hash fields in the spec use an `<algo>:<hex>` prefix encoding (§7.6) so that multiple hash families can coexist within one field.

---

## 3. Schema namespaces

A corpus's schemas are organized into five spec-reserved **namespaces**. Four are primitive **axes** — each bound to a single block-keyword role in the record body — and one is an umbrella: `context` for annotations:

| Namespace | Role | What it declares |
|---|---|---|
| `mime` | Declares the **artifact block**. | Per-media-type fields, address scheme, ingest attestations, derivation ops. |
| `origin` | Declares the **origin block**. | Per-source-of-retrieval overlays: how to recognize an origin, what additional fields it contributes, how to capture it, **which form its records carry and how the producer's format maps onto it**. |
| `form` *(3.0)* | Declares the **form id on a section-block opener**. | Per-record-scope-shape overlays: the normal form a span of content decomposes into — envelope contract, codebook fields, conformance checks (§7.8). |
| `atom` | Declares the **atomic classification** on a **segment block**. | Per-atom-and-subtype overlays: what *form* of content a segment carries, and (for text-atom overlays) whether it licenses a shaped lossless body. |
| `context` | The umbrella for every **annotation** namespace — observations *about* a record. | Per-namespace overlays declared via the **context block** (`context/<namespace>/<id>`): `issue` (problems), `reference` (declared dependent links), `relation` (declared cross-links), … |

*(2.0)* The 1.0 model had a `composite` umbrella, asserted on records via classify blocks. It was removed and **stays removed**: what content means is knowledge, and knowledge lives in the ledger (§7.4). The 3.0 `form` namespace is not its return — it declares structural *shape*, checkable against the bytes, never subject or meaning (§7.8).

A record references a schema by the qualified id encoded on a block opener — for example, `<!--context <namespace>/<id>-->`. The schema loader resolves the id by walking a chain of declarations from most-specific to least-specific:

1. The subtype-overlay declaration (`<namespace>/<id>/<subtype>`), if a subtype is present on the opener.
2. The id declaration (`<namespace>/<id>`).
3. The id's parent declaration, if the id is itself two-part within the namespace (applies in the `mime` and `atom` namespaces where ids decompose into axis + subtype, such as `mime/text/html` or `atom/text/data-table`).
4. The namespace's universal declaration.

Each layer's declared fields extend its parent's; conflicts resolve in favor of the most-specific declaration.

The on-disk organization of these schemas is implementation-discretionary; a reference layout appears in Part II (§12.2).

---

## 4. Records

### 4.1 What a record is

A markdown file with YAML frontmatter. The frontmatter carries the bytes-identity header; the record body carries the schema-derived metadata blocks AND the segmented rendering of the transport's content AND any annotations.

*(3.1)* A record is born complete. Ingest (or promotion) attests the bytes' identity and facts, and from that moment the record is the artifact's **proxy**: bytes retrievable by id (§2); artifact block + **attested byte-facts** emitted — the mime schema's declared attestations (artifact fields; manifest embeds for archive/mail/media-container types; structural byte-marks; sidecar lift); first origin block populated from capture / containment context; fully *readable* — its mechanical body is a resolver derivation (§6.2), computed on demand, cacheable by a search index (§9), never persisted to the record. Everything beyond attestation is layered on when it earns its place, and every layer is **self-evident in the record's own bytes** — there is no stored lifecycle field summarizing them (*3.1: `status` is retired*; §12.19):

| Layer | Present when | Written by |
|---|---|---|
| **attested** | always — the universal baseline above | ingest / promote (§8.1); refreshed by re-attest (§8.3) |
| **formed** | a **form section** (§4.3.2.1) governs the record's stored content zone: the record carries a stored **rendering** of its content under a named rendering contract (§7.8) — the section header carrying the interpretive editorial fields (the vouch's home, §4.2.3) where the pass authors them | the normalize pass — a mechanical shaper where a declared mapping applies, an interpretive agent where not (§4.4.6) |
| **terminal** *(3.3)* | a **terminal contract** (`form/passthrough` / `form/manifest`, §7.8) governs the record — declared at overlay grain (mime/origin `form:`; or derived: `disposition: manifest` with no rendering contract declared) or asserted per record (§4.4.6) — and the record **deliberately stores no rendering**: the artifact (or its attested members) is the terminal representation. An optional whole-record opener may carry the editorial header (§4.2.3) with nothing beneath | the declaration (an overlay key — no record write); the opener, a deliberate describe pass |
| **authored** *(retired 3.2)* | — dissolved into the form layer: interpretive editorial prose rides the form section header (§4.2.3, §4.3.2.1); a formless record's title/description are derived from its role-marked attested and origin fields, and genuinely interpretive prose requires a form or belongs to the ledger. Embed/segment descriptions and asserted annotations remain the normalize pass's licensed work (§1.5 principle 3, §4.4.7) — they just no longer constitute a record state | — |

Three consequences carry the model:

- **Formless is the zeroth form.** A record with no form section is not pending — it is the artifact's proxy under the **identity contract** (§7.8): the faithful representation of the bytes is the bytes, delivered through the derivation ops, prescribing nothing about what the artifact is. Most artifacts a corpus consumes as raw context — code, datasets, media, containers — live here permanently and correctly. A formless record is upgraded to a named form when one is identified or authored for it (§4.4.6), and only then. *(3.3)* The *permanently* half of that sentence is now declarable: a **terminal contract** (§7.8) marks it, reporting distinguishes **terminal** from **proxy**, and *proxy* thereby narrows to mean genuinely unassessed-or-awaiting — the population a rendering contract may still claim.
- **A stored rendering rides a named form.** Steady-state invariant: a record stores a content zone beyond its byte-marks only where a form contract governs it — under the identity contract, a "stored rendering" would merely restate bytes the resolver already derives. (Formless segments *within* a record that carries a form span are the mixed-artifact case and conform — §4.3.2.1. Renderings the 2.x→3.x migrations grandfathered without a form exit through their next pass — §12.19.)
- **The vouch rides the form** *(3.2, succeeding 3.1's "the vouch is orthogonal")*. Every record derives an honest title/description from its role-marked fields (§4.2.3) — mechanical, present from birth, no pass required. Where those derived values are not enough, the interpretive editorial fields land on the **form section header**: shaping and vouching are one movement through the same pass, and a record that has earned no form has, by the same token, earned no interpretive prose — what its content *means* is the ledger's to say (the 2.0 discipline). What 2.x–3.0 called `normalized` — 3.1's *formed + authored* — dissolves into **formed** alone.

State is **reported, never stored**: health, the queue's pass gate (§8.5), and the ledger's verification (`ledger.md` §13.2) each derive the predicate they need from the record; the touch chain (§4.2.2) remains the provenance trail. *(3.0: the `draft` status retired — the §8.1 tombstone. 3.1: `stub` and `normalized` follow it; a record carrying a `status:` field reads tolerantly — the field is ignored on read and dropped on the record's next write; §12.19. 3.2: the `authored` predicate follows — and with it the stored editorial pair: frontmatter `title:`/`description:` read tolerantly as the override of §4.2.1 and are dropped by the migration sweep where not deliberately asserted; §12.21.)*

### 4.2 Frontmatter

The frontmatter (`---...---` at the top of the file) holds **only the bytes-identity header** — at most eight fields *(3.1: `status` retired, §4.1; 3.2: `title`/`description` become optional overrides of the derived editorial fields, §4.2.3, and are absent in the steady state)*. Everything else lives in body blocks (§4.3) or surfaces as derived views (§9).

#### 4.2.1 Core fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Primary identity — blake3 hash of the artifact's bytes, 64-char lowercase hex. Filename stem. Bare hex (no `<algo>:` prefix; algorithm is invariant). |
| `title` | string | no *(3.2)* | **Optional final override** of the derived title (§4.2.3). Absent in the steady state — the derived value should suffice, and needing the override is a signal a schema wants a role mark or the record wants a form. When present it is a deliberate editorial assertion, strongest in the precedence, disclosed like any authored content by the touch chain. An override that merely restates the derived value is noise, not an assertion. *(Pre-3.2 records carried this as a required always-present key — the vouch's old home; the migration relocates or drops those values, §12.21.)* |
| `description` | string | no *(3.2)* | Optional final override of the derived description (§4.2.3). Same contract as `title` above. |
| `transport` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | Byte-level hash(es) of the file under additional algorithms beyond the primary blake3. The primary blake3 lives on `id` and is **not** duplicated here. Use `transport:` only for alternative algorithms. |
| `canonical` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | A canonicalized-content hash per the mime schema's `canonical_strategy`. Lets two records be compared for "same content?" even when ever-changing metadata (timestamps, producer strings) differs. *(3.0: computed at ingest attestation or as a derivation op when re-enabled — open question §12.18; the 2.x persist-disabled status note of §7.1 carries over.)* |
| `perceptual` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | Record-scope perceptual fingerprint — present only for single-atom records (e.g. an image artifact carries a perceptual hash). Multi-atom records carry per-segment perceptual fingerprints in segment headers instead. |
| `touch` | string \| list[string] | yes (≥1) | Ordered list of touch identifiers, one per processing pass. Singular (bare string) when one entry; list when 2+. `touch[0]` is the original ingest. |
| `visibility` | enum | no | `visible` (default), `deranked`, `hidden`. Editorial curation, orthogonal to the derived content state (§4.1). |

#### 4.2.2 Touch identifiers

A touch identifier is a short bare string distinguishing a processing pass. The sequence is `touch[]` — a bare string when the chain has one entry, a list otherwise; the chain records the record's **current-shape provenance** (which passes produced the shape it has now). It is not an immutable history: `re-stub` resets it (§8.4), so a re-stubbed record's chain reflects its post-reset lineage, not every pass it ever saw.

- **Pipeline tooling** uses a stable identifier of the form `<package>.<module>@<version>` (e.g. `corpus.ingest@0.2.0`, `corpus.shape.conversation@0.2.0` — a **shaper** pass names the form or strategy it shaped). The `<package>.<module>` identifies the code path; `<version>` is its installed version.
- **LLM models** use the canonical model identifier with any context modifier in brackets — e.g. `<model-id>[<modifier>]`.
- **Combined tooling + model** — a single pass that is both a deterministic re-assembly and the LLM pass it carries joins the two with `+`: `<package>.<module>@<version>+<model-id>`.

Consecutive identical passes coalesce rather than repeat: a second identical identifier becomes `<identifier>_2`, a third `<identifier>_3`, and so on; a different identifier resets the count. The counter reflects the current chain, so a `re-stub` (which collapses the chain, §8.4) resets it.

The latest touch's tooling version implicitly encodes the spec era under which the record's current shape was produced.

#### 4.2.3 Derived editorial fields *(3.2)*

A record's display **title** and **description** are **derived, never stored** — a pure function of the record's own blocks and their schemas, computed at read time exactly like the classifications view (§9.1).

**Role marks.** An `extended_fields` declaration in any of the three block-declaring namespaces may carry `role: title` or `role: description`, marking that field as an editorial candidate:

- a **mime** schema marks artifact-block byte-facts (§7.1) — a PDF's `/Info` title, a bundle's embedded comment;
- an **origin** overlay marks origin-block fields (§7.2) — `ytdlp_title`, `ytdlp_description`;
- a **form** contract's section-header fields are the **interpretive** candidates: the universal header fields `title:`/`description:` (§4.3.2.1) are implicitly role-marked on every form, and a contract may mark others explicitly.

**Editorial templates** *(3.3; extended to origin overlays in the same arc)*. A form contract — and, on the same grammar, an **origin overlay** (§7.2) — may additionally declare a top-level `editorial:` block naming a **mechanical composition** over more than one field (§7.8):

```yaml
editorial:
  title_template: "Statement — {account} — {period}"
```

`{name}` placeholders substitute the whole-record form section's own `extended_fields` values, read exactly as a role-marked field is (§7.8's `extended_fields` — a list-valued field joins its non-empty items with `, `); static text passes through unchanged. Resolution is **all or nothing**: the template resolves only when **every** placeholder names a field holding a non-empty value on the record's own section — one unresolved placeholder falls the **entire** template through, never a partial composition. (`description_template` is a natural sibling on the same block, undeclared until a contract needs it.)

A `title_template` (or any `<role>_template`) value may be an **ordered list** of templates in place of a single string: entries are tried in declaration order and the **first that fully resolves wins** — each entry individually all-or-nothing, per the rule just above — with a bare string standing as the one-element case of the same grammar. The cascade lets one producer overlay title several record shapes with disjoint field sets from a single declaration: each shape picks its own composition deterministically, by which entry's fields are actually present.

On an **origin overlay** the placeholders read the origin **block's** fields instead, resolving per block exactly as the overlay's role marks do (§7.2: latest qualified block wins; a bare block contributes nothing). The origin layer carries no implicit authored value, so its within-layer order is just **template → role-marked fields** — e.g. a mail window bundle's overlay composing `"Mail window — {window_start} → {window_end}"` from the fields its producing verb stamped (§12.3.13).

Within the form layer, three candidate kinds resolve in a fixed order, each checked only when the one before is empty: the section header's own **implicit** `title:`/`description:` (the interpretive vouch — an authored value always wins where present) → the contract's declared **template**, above (a mechanical composition, reached only absent an authored value) → the contract's explicitly **role-marked** `extended_fields` (a single verbatim field, checked last of the three). This ordering is internal to the form layer alone — the cross-layer precedence below (artifact → origin → form) is unchanged.

**Resolution.** Candidates resolve by layer precedence **artifact → origin → form** — each later layer overrides the earlier, the form's word strongest — with the frontmatter override (§4.2.1), when present, strongest of all. Within a layer, the **latest block wins** (origin blocks append in capture order, so a re-capture's fields supersede); within one block, the schema's declaration order decides, first non-empty winning. An empty or absent candidate falls through to the next; only a **whole-record** form section (no `address`, §4.3.2.1) contributes at record scope — a span-scope section's editorial fields describe its span, never the record.

**Consequences.** Every record carries an honest display identity **from birth, deterministically** — attested and sidecar-lifted fields resolve with no LLM pass, ever; the interpretive value arrives only when a form does, through the one authoring pass, disclosed by its touch. A record that derives *empty* values is not defective — it is a signal, surfaced by health (§12.21), that its schemas want role marks or the artifact wants a form. Consumers (the derived body, search indexing, export §10, the ledger's display of cited records) read the derived value; nothing reads the stored pair except as the override.

### 4.3 The record body — seven block families, three zones

The record body is the markdown content below the closing `---` of the frontmatter. It has three **zones** — metadata, content, annotations — each holding a fixed set of HTML-comment block families.

Every block has the same shape: an HTML comment whose opener line carries a keyword (and optional arg), the YAML payload on the lines that follow, and a closing `-->` alone on its line. HTML comments are syntactically distinct from markdown horizontal rules and from frontmatter delimiters, and every standards-compliant markdown renderer ignores them — so the record body renders cleanly.

```
─── metadata zone ────────────────────────
<!--artifact <mime-type>-->               # exactly 1
<!--origin [<id>[/<subtype>]]-->          # 1..N
<!--embed <mime-type>-->                  # 0..N

─── content zone ─────────────────────────
<!--section <form-id>-->                  # 0..N form spans (depth one; never overlap)
   containing <!--segment ...--> blocks
<!--segment <atom>[/<id>]-->              # content segments (top-level = formless)
<!--segment structural-->                 # byte-mark TOC entries (top-level or in-span)

─── annotations zone ─────────────────────
<!--context <namespace>/<id>[/<subtype>]--># 0..N (record- or segment-scoped via address:)
```

Zone order is fixed. A block of a later zone appearing before a block of an earlier zone is a parse error. Within a zone, the relative order of different block *families* is not significant; the diagram's family order is illustrative. **All metadata- and annotation-zone blocks are header-only**: their YAML payload is the entire block; there is no markdown content between blocks within those zones. **Only text-atom segment blocks carry inline content** — the segment body holds the actual text. *(3.0: the section opener is **qualified** — it carries a form id, §4.3.2.1; a bare 2.x TOC section no longer exists in the grammar and reads tolerantly per §12.18.)*

#### 4.3.1 The metadata zone

The metadata zone carries the artifact's identity, its origins, and its embedded assets. Three block families.

##### 4.3.1.1 The artifact block

Exactly one per record. The opener-line argument is the canonical MIME type and is **authoritative** — there is no frontmatter `media_type` field. The block body holds the fields declared by the matching `mime` schema chain, named **bare** — the opener's MIME already identifies their provenance (§principle 10), so a PDF's title is `title`, not `pdf_title`. When the format exposes a title it rides as that bare `title` candidate; the normalizer picks among it and the origin block's `ytdlp_title` to author the frontmatter `title` (§4.2.1). (A field keeps a prefix only when it names a provenance the opener does *not* carry — a metadata sub-standard the format embeds, e.g. `exif_*` on an image, `og_*` on HTML.)

```
<!--artifact <mime-type>
<extended-field-1>: <value>
<extended-field-2>: <value>
-->
```

Contributes one entry — `mime/<mime-type>` — to the derived classifications view.

##### 4.3.1.2 The origin block

One or more per record. Each block describes one origin (one source of retrieval). `snapshot:` (ISO-8601 timestamp of when this origin was observed) is always required. A *retrieval* origin also carries `uri:` (string or list-of-strings — a canonical URL plus its shortlinks/redirects collapse to one block whose `uri:` is a list). Multiple origin blocks describe genuinely separate sources. A capture with **no retrieval URL** (a dropped-in local file) records a uri-less origin: there is no retrievable source — the staging path is unlinked at ingest — so instead of a `file://` path that dies on arrival, the block carries the durable `filename` (basename) and `source_modified` (the file's mtime); see §7.2.

```
<!--origin <id>
uri: <https://example.com/...>
snapshot: <ISO-8601>
-->

<!--origin
uri:
- <https://example.com/...>
- <https://alias.example.org/...>
snapshot: <ISO-8601>
-->
```

The opener may be bare (`<!--origin-->`) or qualified (`<!--origin <id>-->` or `<!--origin <id>/<subtype>-->`):

- **Bare** — generic origin; no schema overlay. Contributes nothing to the classifications view.
- **Qualified** — matches an `origin/<id>` schema overlay. Contributes `origin/<id>[/<subtype>]` to the derived classifications.

The id is not necessarily a hostname; the host-pattern match (when one is declared on the schema overlay) is a **cue** the pipeline uses to decide which origin schema applies. Origin overlays may also key on non-host cues — file-system paths, API endpoint fingerprints, manual hints — declared in the overlay's match predicate.

The origin block subsumes:

- The capture URI(s) — one block per origin, `uri:` as a list when the same origin is reached through redirects or shortlinks.
- The observation timestamp (`snapshot:`).
- The origin-identifying classification (qualified `<id>` opener).
- Any origin-specific extended fields the schema overlay declares.

##### 4.3.1.3 The classify block *(removed in 2.0)*

*Retired.* The classify block asserted record-scope interpretive classification — the `composite` umbrella's surface. That assertion is knowledge, and it moved to the ledger: what a record documents is expressed as ledger concepts and claims — the record rostered as an artifact of the thing and cited as evidence (`ledger.md` §4) — minted mechanically by **harvest rules** where membership is deterministic (`ledger.md` §10) and authored where it is not. The corpus-side classifications view (§9.1) retains its structural-derived rows (`mime/*`, `origin/*`). The reserved `provenance` field survives on context blocks (§4.3.3.1) with the same semantics.

##### 4.3.1.4 The embed block

Zero or more per record. Header-only blocks describing **embedded assets**. *(3.0)* The embed is a **closed primitive**: it declares an asset whose bytes are **part of this record's capture** — materializable from the record's own artifact (a nested transport, an archive member, an inline `data:` asset, a media track) or from its capture-time enrichment (`also_capture`). A record never embeds content that lives in *another* record's capture; content the record's bytes merely *reference* is reached at read time through the resolver — a lineage-chained reference (§6.2) or a URL-tier context edge (§4.3.3.3) — derived, never stored. The `transport:` hash names the bytes (the dedup key); the address says where the asset appears in this transport.

```
<!--embed <mime-type>
address: <address>                # scalar — single occurrence
transport: <algo>:<hex>
<width>: <px>
<height>: <px>
alt: <verbatim source alt text>
-->

<!--embed <mime-type>
address:                          # list — repeated bytes at multiple positions
- <address-1>
- <address-2>
transport: <algo>:<hex>
alt: <verbatim source alt text>
-->
```

The opener line carries the embed's full MIME type.

###### Required header fields

| Field | Description |
|---|---|
| `address` | Where the asset appears in the transport, in the scheme defined by the media-type schema. Polymorphic: a single string or a YAML list of strings. |
| `transport` | Content-identifying hash, `<algo>:<hex>`. The canonical id of the embed; the deduplication key. |

###### Optional header fields

Per the matching media-type schema. The asset's descriptors split into two distinct kinds:

- `alt` — verbatim source-side alternate text (the publisher's caption, the image's `alt` attribute, the audio track's title, etc.). Mechanically emitted at capture/ingest; **never replaced by the normalizer**. Omitted when the source has none. Provenance-bearing — may be missing, terse, or wrong, but reflects what the publisher wrote.
- `description` — normalizer-written description of the asset as a whole. Lossy by definition. Omitted when the asset is purely decorative.

Plus per-mime fields declared by the embed's media-type schema.

###### Embed description vs segment description

The embed's `description` covers the **whole asset**. A segment derived from that embed — addressing a sub-region, applying overlays — carries its own `description:` on the segment header describing the scope-specific interpretation. Same bytes, different scope, often a different narrative.

###### Deduplication

Embeds are deduplicated by `transport` — identical content collapses to one embed regardless of how many positions reference it. The attesting pass walks the transport's assets in order, hashes each, and merges duplicates by appending positions to the existing embed's `address` list.

###### Linking from segments

Segments link to embeds by **address membership**, not by an explicit reference field. A segment whose address appears (scalar or list-member) in an embed's `address` is described by that embed. Orphan embeds — embeds with no segment pointing at them — are tolerated as a record of available assets; the normalizer may prune them.

Every image, audio, and video segment's address must appear in some embed's address — **except resolver-materializable addresses**. When the resolver can materialize the segment's address on demand, no embed is required — the functional URI (§6) produces the bytes, and any description rides the addressing segment's (or section's) own `description:`. Two cases qualify:

- **Artifact self-slices** *(unchanged from 2.x)* — a region of the record's own artifact: a `frame=`/`time=`/`time_range=` into a video, a `page=` render of a PDF, a `bbox=` into a single-image record.
- **Lineage-chained references** *(3.0)* — an asset the record's bytes declare but do not contain, whose bytes live in the record's own containment-lineage parent (§6.2): a conversation message's attachment (`turn=<N>&att=<M>`), a promoted member's sibling asset. The reference is faithful content (it is *in* the bytes); the resolution chain is derived at read time from the lineage origin block plus the record's own bytes — never stored — and cannot rot, because the parent is content-addressed. A reference whose target member is absent (a dead CDN link the export never localized, a takeout gap) is still a faithful marker; materialization fails loudly at resolve/health time, never papered over by a stale stored pointer.

An embed is needed only for assets that are neither self-slices nor lineage-resolvable — an inline image the capture inlined, a nested transport, a declared track.

#### 4.3.2 The content zone

The content zone carries the record body's rendered content — segments (content-atom and structural), optionally spanned by form sections. Two block families.

##### 4.3.2.1 The section block — the form span

*(3.0)* The section's 1.0–2.x role — the universal TOC grouping unit — is **retired in place**; its successor is the structural segment (§4.3.2.3), and the table of contents is a derived rendering. What remains is the primitive the grammar always had — a positional span over the content zone, with a YAML header — now carrying the one thing that genuinely needs a span with fields: the record's **form** (§4.4.1, §7.8).

A **section** declares that a span of the content zone has a named structural form. The opener is **qualified** — it carries the form id, exactly as a segment opener carries its atom id:

```
<!--section conversation
participants:
- Andy Sun <andy@example.net>
- Steven Rahn <steven@example.org>
-->

<!--segment structural
address: turn=1
level: 1
-->

<!--segment text/message
address: turn=1
participant: 0
timestamp: '2014-03-04T00:09:34Z'
-->

Yo

<!--segment text/message
address: turn=2
participant: 1
timestamp: '2014-03-04T00:11:02Z'
reply_to: turn=1
-->

<!--segment image
address: turn=2&att=1
-->
```

(The structural mark is the platform's own topic boundary — a byte-mark; DiscordChatExporter (DCE) exports carry none and go flat. `participant:` indexes the section's authorship-ordered codebook. Turn 2 is an attachment-bearing reply: its `text/message` envelope segment is empty-bodied — the message has no text, and the envelope never rides the marker — and the `image` marker at the composed address carries no embed: the attachment is lineage-resolvable, §4.3.1.4/§6.2.)

###### Section header fields

| Field | Required? | Description |
|---|---|---|
| `address` | Span-scope only | The span's **envelope** — the min–max span of the child segment addresses (`pages=2-6`, `turn=1-74`) — derived from the children, never wider than the content held. **Omitted on a whole-record form section** (one section spanning the entire content zone — the record-scope form); required when the form governs part of the record. |
| `entry` | Optional | A short label for the span. |
| `title` | Optional *(3.2)* | The span's interpretive display title — implicitly role-marked (`role: title`, §4.2.3) on every form. On a **whole-record** form section this is where the record's authored title lives (the vouch's home); on a span-scope section it titles the span alone. Normalizer-written, disclosed by the pass's touch. |
| `description` | Optional | Scope-specific description of what this span IS. Normalizer-written. *(3.2: implicitly role-marked — `role: description` — with the same whole-record/span-scope split as `title` above.)* |
| *(form fields)* | Per overlay | The **codebook and envelope fields the form overlay declares** (§7.8) — e.g. `form/conversation`'s `participants:` list, the authorship-ordered codebook that `participant:` segment indexes resolve against. Mechanically derivable from the span's own bytes wherever possible (§7.8's preference); a declared-interpretive field is disclosed by the touch chain. |

###### Rules

- **Positional span.** A section's closer is followed directly by its first child block; its span runs to the next section opener or the end of the content zone. Markdown prose between a section closer and the next opener is a parse error — sections have no body region.
- **Depth one, no overlap, one form per span.** Sections never nest and never overlap (positional by construction). A whole-record section (no `address`) admits no sibling sections. Forms do not nest; a genuinely separable sub-document is a **promotion** candidate, not a nested form.
- **Formless is the zeroth form; a named form is earned.** *(3.1, amending 3.0's "rare by design.")* A section exists *only* where a named form is declared — and a record with no section is not deficient: its content stands under the **identity contract** (§4.1, §7.8), consumable through the derived body, prescribing nothing about what the artifact is. Artifacts with no faithful markdown shape — code, datasets, media, containers — stay formless permanently; that is their correct steady state, never a backlog. For artifacts a markdown shape genuinely fits, formless is instead a starting point: a named form is the goal, adopted lazily when identified or authored (§4.4.6, §7.8). Segments before the first section opener are **formless** content under mime + atoms alone — the mixed-artifact case: a statement PDF whose page 1 is a cover letter carries page 1's segments bare, then `<!--section statement address: pages=2-6-->` over the statement proper.
- **Coherence is lint-enforced.** A record carrying `<!--section <form-id>-->` MUST satisfy that form overlay's declared conformance checks (§7.8) — envelope fields present, codebook indexes in range, addresses parse in the span's scheme. There is no half-asserted form and no transitionary state: stamping the form and conforming the span land together.

*(The 2.0 note on section-scope composites is unchanged and remains at §4.4.3: a passage's meaning is still a ledger claim over the span. The form id on the opener is a structural-shape judgment, not a meaning — §7.8.)*

###### Worked example — the mixed statement PDF

```
<!--segment image
address: page=1
description: Cover letter accompanying the March statement.
-->

<!--section statement
address: pages=2-6
account: '…7841'
period: 2026-03
-->

<!--segment text/ocr
address: page=2&bbox=0.06,0.12,0.88,0.30
-->

... transactions rendered per the statement form's contract ...
```

Page 1 stays formless — no contract has been identified for it and nothing yet demands one (§7.8: adoption is benefit-driven; formless is valid indefinitely); the statement's codebook/envelope fields (`account`, `period`) ride the section header, mechanically derivable from the span's own bytes; lint runs `form/statement`'s checks over pages 2–6 only.

##### 4.3.2.2 The segment block

```
<!--segment <atom>[/<id>]
address: <address>                       # single string OR a YAML list of strings
<other-header-fields>: <values>
-->

<segment body>                            # text atom only
```

The atom (`text`, `image`, `audio`, or `video`) sits on the opener line itself, optionally qualified by an atomic-overlay id (e.g. `<!--segment text/data-table-->`) — or the opener names the fifth, non-atom kind: `<!--segment structural-->` (§4.3.2.3). A content segment is **logically contiguous content of one classification**; an interrupting element of a different classification forces a segment boundary.

A segment's identity is `(opener-id, address)` — the atomic class id on the opener plus the address. Two segments may share an address only when their opener-id differs. This permits **same-region stacking**: a single source region can carry multiple representations — a positioning marker for the asset, a structured transcription, a literal-text transcription — each as its own segment with the same address but a distinct opener-id. Multi-region segments use an ordered list of single-region addresses in reading order.

###### Body permission rule

A segment carries a segment body only when that body is a faithful, lossless rendering of the addressed content. This resolves to three cases:

- **Plain prose** — `<!--segment text-->` with the segment body as markdown text. Default for HTML prose, PDF page text, etc.
- **Shaped lossless transcription** — `<!--segment text/<id>-->` where the overlay's declaring schema licenses lossless shaping (`enables_lossless: true`, §4.4.1). The overlay shapes the segment body into the declared form (markdown table, transcript, OCR text, time-stamped captions, etc.). The address scheme may chain through transport→atom transforms to reach a region within a frame within a stream.
- **Body-empty marker** — every other segment, in two cases. (a) The three non-text atoms (`image`, `audio`, `video`) are positioning markers in document flow that link to a matching embed (by address membership) for the asset's metadata and description. (b) A `text/<id>` overlay whose declaring schema sets `enables_lossless: false` marks a *typed but non-lossless* text region — e.g. a live, formula-driven table whose displayed values are a single-execution snapshot rather than faithful content. In both cases the segment body is empty and what the region IS goes in the segment's `description:`.

###### Required header fields

| Field | Description |
|---|---|
| `address` | Address inside the transport, in the scheme defined by the media-type schema. The segment's identity. Composable: addresses chain transforms (e.g. transport → frame → region) as the schema permits. |

###### Optional header fields

| Field | Description |
|---|---|
| `description` | The segment's scope-specific description — what this segment IS at its address and under its overlay. Distinct from the matching embed's `description` (which describes the whole asset). Normalizer-written. |
| `perceptual` | An atom-canonical content fingerprint (§7.7) using the `<algo>:<hex>` prefix convention. |
| `entry` | A short identifying label — an **authored leaf label** (normalizer-written) for a content block among siblings: a top-level block in a MULTI-block record, or a child block within a form section's span *(nesting admitted 2026-07-17 — previously top-level only; a generic form span wraps an already-labeled multi-block rendering whole, and the label's meaning never depended on being top-level: the form-adopt-32 migration measured 3,779 records whose authored labels a top-level-only rule would have forced to drop, §12.22)*. Distinct from the structural segment's `entry:`, which is the *source's own* mark text (byte-mark, §4.3.2.3). A record whose content zone is a single top-level block carries none. |
| `speaker` | An integer diarization index identifying who is speaking in this `audio` segment. |

The atomic classification, if any, lives on the opener line as `<!--segment <atom>/<id>-->`. A segment carries exactly one atomic class id; when multiple representations apply to the same source region, each becomes its own segment with its own opener (and identity is the `(opener-id, address)` pair).

Segment-scope issues live as standalone issue context blocks in the annotations zone with an `address:` field pointing back to the segment — never inline on segment headers.

###### The four content atoms

- **`text`** — the atom whose segments carry segment bodies, with one exception. Plain prose by default; shaped by a `text/<overlay>` for structured lossless forms. A `text/<overlay>` declaring `enables_lossless: false` is a body-empty marker like the non-text atoms, with its meaning on the segment `description:` (see the body permission rule).
- **`image`** — a static image at the addressed region. Body-empty positioning marker; description on the matching embed at the same address — or, for an artifact-self-slice with no embed (§4.3.1.4), on this segment's own `description:`.
- **`audio`** — an audio range. Body-empty positioning marker; description on the matching embed (or, for a self-slice, on the segment's `description:`). Transcripts live as separate `text` segments at the same address.
- **`video`** — a video stream over the addressed time range. Body-empty positioning marker; description on the matching embed (or, for a self-slice, on the segment's `description:`). Captions and scene transcripts live as separate `text` segments at the same address.

###### Faithfulness

The segment body MUST be a faithful, lossless rendering of the addressed content. Descriptive content (a summary of what an image shows, a paraphrase of what was said, or what a live/computed region contains) is **lossy** by definition and belongs on the matching embed's `description` field — or, when no embed exists (an artifact-self-slice, §4.3.1.4, or a non-lossless `text/<id>` overlay), on the addressing segment's or section's own `description:` — NOT in a segment body. Re-segmentation is structural; content within remains faithful.

###### Cross-references in segment bodies

Functional URIs and wikilinks in segment bodies are for **cross-artifact references**. They are NOT used to embed inline images from within the same transport — inline images are their own `image` segments.

Segment bodies may carry:

- **Plain markdown URLs** — for external references whose targets aren't captured in the corpus.
- **Raw blake3 wikilinks/embeds** — `[[<blake3>|link text]]`, `![[<blake3>]]` — intra-corpus references whose targets are captured artifacts.
- **Functional URIs for cross-artifact derived views** — `[[corpus://<other-hash>?<params>|<caption>]]`, `![[corpus://<other-hash>?<params>|<alt-text>]]`.

*(3.0: the 2.x "Body-draft mode contract" paragraph is deleted with the stage; the stored content zone has exactly one author — the normalize pass — and its total-replacement discipline is stated at §4.4.7.)*

##### 4.3.2.3 The structural segment

```
<!--segment structural
address: <the MARK's position>
level: <int>
entry: <the mark's own text, verbatim>       # optional — omitted when the mark is unlabeled
-->
```

A **structural segment** is a body-empty mark recording that **the source itself declares a structural boundary** at an address: a heading (`el=<N>`), an EPUB nav target (`spine=<N>`), a PDF outline entry (`page=<N>`), a media chapter (`time=<tc>`), a chat platform's topic boundary (`turn=<N>`). It carries no content atom, takes no atomic overlay, and never has a body; it contributes nothing to the faithful text rendering (and is excluded from `token_counts.body`, §9.6). Its identity is (`structural`, address), stacking beside content segments at the same address per the standard rule.

###### The byte-mark rule

A structural segment exists **only where the source bytes carry the mark** — or where the capture's producer-declared enrichment carries it (a yt-dlp sidecar's `chapters[]` is the uploader's own declaration, lifted mechanically at ingest; §12.3.7). A pass never invents one. Groupings a reader may want but the bytes do not declare — a conversation's per-day break (whose midnight? which participant's timezone?), a "front matter vs body" split with no nav entry — are **read-time renderings** with explicit parameters (`corpus toc --tz <zone>`, defaulting to UTC and saying so), computed from the envelope timestamps and addresses the segments already carry, never stored. *(This is §1.5 principle 3 applied to structure. It also retires, retroactively, every synthetic section the 2.x pipeline stored — the iMessage per-day sections foremost; §12.18.)*

###### Level and scope

- `level:` is the mark's own hierarchy where the source states one (`h1`–`h6`; outline depth; nav nesting), else `1`. Levels are the *whole* nesting grammar — there is no block nesting.
- A mark's **scope is derived**: it runs from its address to the next structural segment of the same or shallower level, or to the end of the enclosing form section (or content zone). Content before the first mark is preamble. The TOC tree — arbitrary depth — is a derived rendering over the flat mark sequence, exactly as an archive's directory tree is a derived rendering over `path=` addresses (§12.4): *a tree is a derived rendering, not stored blocks*, now applied to the table of contents itself.
- The mark's own `address` is a **position**, not an envelope — the 2.x envelope-derivation rule **narrows** to the form-span `address` (§4.3.2.1), where it survives; a consumer that needs a mark's span derives it from scope. *(The 2.x temporal exception — structural-interval bounds for `time_range=` sections — is deliberately dropped: chapter and speaker-run boundaries are byte-marks or read-time renderings now, and a temporal form span takes the derived envelope like any other.)*

###### Emission

Byte-marks are mechanical facts, so structural segments are **attested at ingest** where the mime schema declares them (a media container's chapters, §1.2) and otherwise written by the normalize pass's shaper from the same derivation ops any consumer can run (a PDF's `outline`, an EPUB's nav, an HTML page's headings, a transcript's declared topic ids). Either way the mark is checkable against the bytes — the same auditability as every attested fact. **Ownership is deterministic from the schema**: a structural segment is attested — and stripped + regenerated by re-attest — **iff its address family is declared in the mime schema's `attest:`** (§7.1); every other mark belongs to the authored layer and refreshes with re-normalize (§4.4.7). No per-segment provenance field is needed: schema plus touch chain recover the owner.

###### Worked example — a media container with chapters

```
<!--artifact video/x-matroska
duration: '01:42:07'
streams: [h264 1920x1080, aac 5.1 eng, subrip eng]
-->

<!--embed video/h264
address: stream_id=0
transport: blake3:…
-->

<!--embed audio/aac
address: stream_id=1
transport: blake3:…
-->

<!--embed text/x-subrip
address: stream_id=2
transport: blake3:…
-->

<!--segment structural
address: time=00:00:00
level: 1
entry: Opening
-->

<!--segment structural
address: time=00:12:31
level: 1
entry: The heist
-->
```

The chapters are the container's byte-marks on the shared timeline; the tracks (promotable, §8.1) inherit them at read time through lineage — a track record never copies marks its own bytes do not carry.

#### 4.3.3 The annotations zone

The annotations zone carries observations *about* the record — problems with it, sources it cites, derived relations. One block family: the **context block**, drawing its overlays from the `context/` umbrella (§3), with one namespace per kind of observation (`issue`, `reference`, …). Context **never** contributes to the faithful content zone or the canonical content hash — it is a side-channel that accretes without disturbing the lossless body.

**Context is scarce by design.** A record carries a context block only when it records durable, high-value information the faithful body cannot — a detected problem (`issue`), a declared dependent link resolved toward capture (`reference`), an overlay-declared chrome extraction (`aside`), a source-declared cross-link (`relation`). It is emphatically **not** a normalizer scratchpad: a normalizer MUST NOT emit commentary, summaries, running notes, or "what I did" prose as context. The **mechanical** namespaces (`aside`, `reference`, `relation`) auto-populate *only* on real signal and *only* where overlay-gated — each exists **solely** where an origin overlay declares the extraction, and there are none absent that declaration; every block requires a referent actually present in the content (a declared link or structure in the page). `issue` is the one namespace with an asserted path: the normalizer surfaces **faithfulness** problems (garbled OCR, truncated content) beside the pipeline's mechanical detections. Absent real signal the annotations zone is **empty** — the normal state for most records.

*(2.0)* The 1.0 interpretive `reference` path — normalizer-found citations in the content — moved to the ledger: a found citation is a `capture`/`search` need or, where the domain cares, a citation edge with span evidence (`ledger.md` §7). The 1.0 `concept` namespace was removed outright (§4.3.3.4). Content-*meaning* observations of every kind are ledger material; the annotations zone records only what is mechanical or faithfulness-scoped.

##### 4.3.3.1 The context block

Zero or more per record. Each is a typed observation, optionally pinned to a segment. The opener `<namespace>/<id>` matches the corresponding `context/<namespace>/<id>` overlay; an optional `<subtype>` extends it.

```
<!--context <namespace>/<id>
address: <segment-address>               # presence pins it to a segment; absence = record scope
quote: <verbatim span>                   # optional: the exact phrase within the segment
occurrence: <n>                          # optional: which match, when the quote repeats
provenance: auto                         # optional reserved field (see below)
<namespace-field>: <value>
-->
```

A context block with an `address:` field is **segment-scoped**; without it, **record-scoped**. The optional **`quote:`** (a verbatim span copied from the addressed segment's body) sharpens the anchor to the exact phrase; **`occurrence:`** disambiguates when that span repeats. Because the body is a faithful rendering of the immutable artifact, a verbatim `quote:` survives re-runs where a character offset would not.

One field name is **reserved**: `provenance` (§4.4.6). `provenance: auto` marks an engine-stamped block (a detector or overlay-declared emission) that is stripped and regenerated on re-run; its absence (or `provenance: asserted`) marks a human- or normalizer-asserted block that the engine never touches. No namespace may declare `provenance` as an overlay field.

Context blocks **do not** contribute to the derived classifications view (§9.1) — they surface in the derived `context` view, of which the `issues` view (§9.2) is the `issue`-namespace projection. Conceptually, a *classification* says what the content IS; a *context* records something observed about it.

##### 4.3.3.2 The `issue` namespace

An `issue` context block (`<!--context issue/<id>-->`) is a typed problem with the record or a segment. Its universal overlay (`context/issue/issue.yaml`) declares:

- `severity` — typically `blocking | warning | info` (the schema declares the closed set).
- `resolution` — typically `open | fixed | wontfix | superseded`.
- `detector` — touch identifier of the pass that emitted the issue.

Per-id overlays (`context/issue/<id>`) extend with id-specific fields. The `severity`/`resolution` value sets are corpus-local (schema-declared); cross-corpus tooling should treat unknown values gracefully rather than assuming a fixed vocabulary. Issues come from three sources — the **deterministic pipeline** (mechanical detections at capture/ingest: bot blocks, corrupt encoding, missing inputs), the **normalizer** (content-meaning problems), and **external** health-signal sweeps — each recorded in `detector` and, where engine-owned, `provenance: auto`.

##### 4.3.3.3 The `reference` namespace

A `reference` context block (`<!--context reference-->`) records a **declared dependent link** — a product page's manual, a spec sheet — emitted mechanically from an origin overlay's `capture.references` declaration (§7.2) by the **normalize pass** — the anchor needs the authored body (§8.1) — carrying `provenance: auto` and a corpus-local **`role`** field (`manual`, `spec-sheet`, …; schema-declared closed set, treated gracefully when unknown). It is pinned to its link's mention via `address:`/`quote:` (the link text) and carries the **citation ladder** (§4.4.5) at tier 1–2: `attribution_text` (the link text) → `source_url` (the resolved href).

**The intra-corpus edge is derived, never stored.** Whether `source_url` is itself a captured record is a **read-time derived edge** — resolved against the URI index by `derived_views.references` (§9.9) / `corpus links --references`, never baked into the record — so the emission stays a pure function of the artifact (it reads no corpus state) and the edge self-heals (`captured ⇄ pending`) as targets are captured, removed, or superseded. As an `auto` block it is regenerated on re-normalize (§8.3), with the pass that owns it (§4.4.6).

*(2.0)* The 1.0 interpretive emission path (normalizer-authored citations found in the body, including the stored tier-3 `source_uri`) moved to the ledger (§4.3.3 note). The reference block is now mechanical-only: capture plumbing, not citation knowledge.

##### 4.3.3.4 The `concept` namespace *(removed in 2.0)*

*Retired.* The concept block was the ledger's shadow: a per-record entity annotation resolved against an external knowledge base (Wikipedia/Wikidata), built because no internal entity layer existed — its `concept:` id was "the join key by which records that invoke the same concept are related without either knowing about the other," which is precisely what a ledger **concept** is (`ledger.md` §4 — the namespace's very name graduated with it). The ledger replaces every part of it: record-scope *aboutness* is coverage and the artifact roster (`ledger.md` §9, §4.2); a span-scoped *mention* is claim evidence anchored by a functional URI; the external join key (`wikidata:Q…`) is a concept-level external-identity claim citing a mirrored reference dataset (`ledger.md` §6.5), made once, not stamped per record. The local-KB machinery (1.0 §12.12) retires with it.

##### 4.3.3.5 The `relation` namespace

A `relation` context block (`<!--context relation[/<predicate>]-->`) records a **source-declared cross-link** from this record toward another resource — navigation structure actually present in the content (a "related information" rail, sibling-page links) — typically lifted from chrome the faithful body drops, making the annotations zone its proper side-channel home. Mechanical: the lift is declared per host on the origin overlay (`capture.relations`, §7.2) and emitted by the normalize pass, exactly as references are (§4.3.3.3), with `provenance: auto`. The target is recorded as `target_text`/`target_url` — **URL-tier only**: at the corpus layer a record never links another record by id; the URL is the edge, resolved to a captured record at read time exactly as references are (§9.9). An optional `predicate` subtype names the relation kind per the corpus-local overlay.

*(Migration note, non-normative: relation blocks emitted by 1.0-era normalize passes are asserted-labeled; they relabel to `provenance: auto` as origin-declared lifting lands in the mechanical pipeline.)*

### 4.4 Classifications: scope and fidelity

Classifications identify what a record (and its segments) IS — **structurally**: its format, its retrieval source, the form of its content. What a record's content *means* is not a classification at this layer; it is ledger knowledge (`ledger.md`). The framework rests on two ideas: what *kind* of classification is being made (four axes) and what structural *scope* it applies at.

#### 4.4.1 The classification axes

Every classification falls along one of four conceptual axes. Each axis has its own block surface, its own schema namespace, and its own scope rules.

| Axis | What it identifies | Block surface | Schema namespace |
|---|---|---|---|
| **media-type** | The format / container / transport of the bytes. | artifact block (exactly 1) | `mime` |
| **origin** | Where the bytes came from. | origin block (1..N) | `origin` |
| **form** *(3.0)* | What structural shape a span of content decomposes into. | **section-block opener** (0..N spans) | `form` |
| **atomic** | What *form* of atomic content a segment carries. | segment-block opener | `atom` |

**media-type** and **origin** are properties of the bytes — record scope only. **atomic** is a structural-form judgment at segment scope. **form** *(3.0)* is the same structural-form judgment one level up — what shape a *span* of content decomposes into (a conversation, a statement, a receipt) — checkable against the bytes like everything else in the faithful zone, applying at section scope (a whole-record section being the record-scope case). The ladder is uniform: record blocks bind mime/origin; section openers bind form; segment openers bind atom.

The form axis is **not** the 1.0 composite returning (§4.3.1.3, §7.4 — both tombstones intact): composite asserted *meaning* (what content is about — a subject, a domain judgment), which lives in the ledger as claims; form names a *shape* — a decomposition contract with mechanical facts — and can no more assert meaning than a `text/data-table` opener can (§7.8 states the discipline normatively).

Atomic-axis schemas declare two extra keys beyond the universal classification fields:

- `applies_to.atom` — which atom this overlay attaches to (`text`, `image`, `audio`, or `video`). Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `enables_lossless` (boolean, default false) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's declaration describes what shape the body takes.

A segment carries **exactly one** atomic class id, on the opener line. When multiple representations apply to the same source region, each becomes its own segment.

#### 4.4.2 Scopes

Classifications attach at three structural scopes — record, section (span), and segment — plus the **embed**, where the media-type axis attaches via each embed's MIME:

| Axis | Record | Section (span) | Segment | Embed |
|---|---|---|---|---|
| media-type | ✓ (artifact MIME) | — | — | ✓ (per-embed MIME) |
| origin | ✓ (origin block) | — | — | — |
| form | ✓ (a whole-record section) | ✓ (a span section) | — | — |
| atomic | — | — | ✓ (segment opener) | — |

#### 4.4.3 Section scope *(dissolved in 2.0)*

*Retired.* The 1.0 section-scope composite (a passage's identity — "this section is a recipe") and the further-deferred identity+role dual-composite citation model (borrowed material carrying both what it is and what it does in the host) are both expressed as **ledger claims over section spans**: span-precise evidence URIs make "what this passage is" and "what this passage does here" two claims about one anchor, with no record-side mechanism at all. Nothing remains at this layer.

*(3.0 note.)* What returns to section scope in 3.0 is the **form axis** (§4.4.1) — a structural-shape judgment, checkable against the bytes, binding a `form/` overlay on the section opener. What this tombstone retired — a passage's *meaning*, its identity and role as domain knowledge — stays retired: it remains a ledger claim over the span, and no form overlay may carry it (§7.8).

#### 4.4.4 Scope-driven fidelity *(removed in 2.0)*

*Retired with the composite namespace.* The three field groups (descriptive / structural / citation) organized composite extended fields by scope; composite fields are now claim values and qualifiers in the ledger. The citation field group's survivor is the mechanical reference block's ladder (§4.4.5).

#### 4.4.5 The citation ladder (mechanical)

A declared dependent link progresses from lossy toward lossless:

| Tier | Citation field | Meaning |
|---|---|---|
| **1** | `attribution_text` | Free-text (the link text). Ambiguous but captured. |
| **2** | `source_url` | Resolvable URL. |
| **3** | *(derived, never stored)* | The captured record the URL resolves to. |

The ladder is carried by the **`reference` context block** (§4.3.3.3), pinned to the exact mention via `address:`/`quote:`. Host records never change shape — enrichment happens at the linked target. Tier 3 is always a **read-time resolution** of `source_url` against the URI index (§9.9): the emitting pass reads no corpus state and stays a pure function of the artifact, and the edge self-heals (`captured ⇄ pending`) as targets are captured, removed, or superseded rather than leaving a stored pointer that dangles. *(2.0: the 1.0 asserted tier-3 `source_uri` — a hand-linked citation with no resolvable URL — moved to the ledger with the rest of citation knowledge.)*

#### 4.4.6 Provenance

A record's metadata and annotations have one of four **provenances** (who put a datum there, and what re-running does to it):

| Provenance | How it appears | On re-run |
|---|---|---|
| **structural-derived** | `mime/*`, `origin/*`, `form/*` — walked from the artifact / origin blocks and section openers (§9.1) | recomputed |
| **attested** *(3.0)* | ingest-stamped byte-facts: artifact-block fields, manifest embeds, structural byte-marks whose address family the mime schema's `attest:` declares (§4.3.2.3), sidecar-lifted origin fields | re-attested (stripped + regenerated) by re-ingest / re-attest (§8.3) |
| **auto** | a context block with `provenance: auto` — a detector or overlay-declared emission (emitted at normalize — §4.3.3.3, §4.3.3.5) | stripped + regenerated from the current overlays by a re-run of the owning pass (re-normalize) |
| **asserted** | a context block with no `provenance` — human / normalizer (faithfulness issues) | never touched |

A **form section** is stamped by one of two paths, both recorded in the touch chain: **declared** — the record's origin overlay declares its form (§7.2), and the shaper stamps + conforms the span mechanically on the normalize pass (regenerated on re-shape); or **asserted** — an interpretive pass recognizes the shape on a record whose origin is generic, and the pass's model identifier is in the chain (§4.2.2). Recognition may come from any layer — a ledger scribe reading cross-corpus is exactly who will spot that some old PDF is really a transcript — but the record mutation always goes through the corpus normalize pass and its lint gate (a worklist entry, then a re-normalize dispatch); scribes author knowledge, normalizers author faithful form. A wrong assertion fails form-coherence lint immediately (§4.3.2.1); a wrong-but-lint-passing one is corrected by a later asserted pass, auditable in the chain.

*(2.0: the 1.0 ladder's classify-block rows — `classify_when` auto-membership and asserted composites — moved to the ledger; deterministic membership is now a harvest rule with the same auto/asserted discipline at the claim level, `ledger.md` §10.)*

#### 4.4.7 Re-run lifetime

Metadata-, content-, and annotations-zone material persists across re-runs **unless the pass that owns it is itself re-run**. 3.0 has exactly two owning passes:

- **Ingest / promote own the attested layer** — the artifact block's fields, manifest embeds, structural byte-marks, sidecar-lifted origin fields, origin stamping. A **re-attest** (§8.3) strips and regenerates them from the current schemas; it never touches the authored layer.
- **Normalize owns the authored layer** — the stored content zone (total replacement per pass: shaper or agent, same discipline the 2.x body-draft contract stated), embed/segment `description:`s, the form span's editorial header fields (§4.2.3), asserted faithfulness issues. A re-normalize refreshes it; it never touches attested facts except to *read* them.

`provenance: auto` context blocks belong to whichever pass's overlay declared them and regenerate with it; asserted context blocks are never auto-touched. The 2.x three-way dance — re-draft wiping normalize work, normalize partially surviving re-draft (§4.4.7/2.x) — dissolves with the stage: there is nothing between the attested facts and the authored form. To deliberately reset everything, `re-stub` (§8.4).

---

## 5. URIs and references

### 5.1 URI forms

Three URI forms appear within the corpus:

- **Plain URLs** — for unresolved external references in segment bodies whose targets aren't captured in the corpus.
- **Raw blake3 wikilinks/embeds** — `[[<blake3>|link text]]`, `![[<blake3>]]` — intra-corpus references whose targets are captured artifacts.
- **Functional URIs** — `corpus://<hash>[?<params>]` — composable references resolved to derived views (§6).

### 5.2 Re-capture

If the same bytes are encountered again, the record's identity is unchanged. The capture URL may differ across encounters, so origin blocks are append-only: each re-encounter checks the canonicalized capture URL against existing origin blocks' `uri:` entries and either appends to an existing origin's `uri:` list (when the new URL aliases an existing origin via known shortlink/redirect rules) or emits a new origin block (when it's genuinely a separate source). A re-dropped local file (a uri-less origin) dedups by `filename` instead of a URL — the same bytes under the same name append no duplicate origin, while the same bytes under a *different* name record a distinct local source (its own origin).

If a URL re-fetched later yields different bytes, the new content produces a different hash and therefore a different record.

### 5.3 Referencing a region in another record

A functional URI addresses a **region** of a record — encode the address in its query string:

```
corpus://<hash>?<address-keys>
```

The same form serves both navigation (wikilink) and rendering (embed). It carries the **address only**, so it resolves to the region (and the asset or derived view at it), not to one specific representation: where same-region stacking places several segments at one address (a segment's in-record identity is `(opener-id, address)`, §4.3.2.2), those representations are distinguished only within the record, not by a cross-record reference.

---

## 6. Functional URIs

### 6.1 Grammar

```
corpus://<hash>[?<params>]
```

- `<hash>` — blake3 hash of the source artifact, 64-char lowercase hex.
- `<params>` — `&`-separated key/value pairs and flag-style keys. Order is significant — parameters compose left-to-right, each operating on the previous step's output. A param **value** percent-encodes the query-reserved characters `%`/`&`/`#` as `%25`/`%26`/`%23`; the parser decodes, and canonicalization re-encodes. Values may therefore carry any character — archive member names are producer-controlled (`?path=…D%26D 5e….json` addresses a member literally named `…D&D 5e….json`). *(2.1: the encode contract existed from the start; the decode side is normative as of 2026-07-12.)*

Bare `corpus://<hash>` resolves to the source artifact's bytes. `corpus://<hash>?<params>` resolves to a derived view per §6.2.

### 6.2 Transformations

*(3.0.)* The transformation table is also the home of the **derivation ops** — the mechanical extractions the 2.x drafters performed, now exposed as resolver operations: on-demand, cacheable, reproducible, consumed by the normalize pass and by any reader (a stub is fully readable through them). The 2.x rows stand unchanged (`time_range=` amended); 3.0 adds `body`, `members`, `transcribe`, the unit ops (`turn=`, `turn=&att=`), and the muxing-contract params (`cut=`, `format=`).

| Param | Input type | Output type | Description |
|---|---|---|---|
| `page=<N>` | PDF | image | Select page N (1-indexed). On its own it renders the page as an image; an image op or `bbox=` after it auto-renders first. |
| `page=<N>&render` | PDF page | image | Render the selected page as an image (the explicit form of a terminal `page=<N>`). |
| `page=<N>&text` | PDF page | text | The page's embedded text layer, verbatim — not an OCR of the raster; empty when the page carries no text layer. |
| `page=<N>&words` | PDF page | json | The page's text-layer words, each with a `bbox` (`[0.0, 1.0]` page fractions, origin top-left). |
| `page=<N>&probe` | PDF page | json | Per-page structural signals: dimensions, rotation, text/image-coverage stats, an invisible-text flag, and an advisory shape hint. |
| `probe` | PDF | json | Whole-document structural probe: per-page table, `/Info`, outline presence, and a shape summary. |
| `outline` | PDF | json | The PDF outline / TOC tree (nested `{title, page, children}`). |
| `time_range=<s>-<e>[,<s>-<e>…]` | media container / stream | media slice | *(amended, 3.0)* A cut of the **composition** (on a container: the default member of each kind, muxed — the muxing contract, below) or of one stream (after `stream_id=`). A comma-delimited ordered list concatenates cuts in listed order. |
| `stream_id=<id>` | multi-stream media | stream-isolated | Select a specific stream. |
| `bbox=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Crop a relative region (image: floats in `[0.0, 1.0]`, origin top-left) or narrow a worksheet (spreadsheet: an A1 range, e.g. `bbox=B2:G30`). Polymorphic — see below. |
| `crop=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Alias for `bbox` (inherits its polymorphism). |
| `mark=<x>,<y>,<w>,<h>[;…]` | image | image | Outline the region(s) on the **whole** image (does not crop) — the inspection dual of `crop`, showing where a region sits in context. Relative floats in `[0.0, 1.0]`; `;`-separated for multiple regions. |
| `resize=<W>x<H>` | image | image | Resize to absolute pixel dimensions (forces both, may distort or enlarge). |
| `fit=<W>x<H>` \| `fit=<preset>` | image | image | Downscale to fit within a bounding box, aspect-preserving; reduce-only (never enlarges). A `<preset>` names an implementation-defined budget. |
| `rotate=<90\|180\|270>` | image | image | Rotate clockwise by a quarter turn (lossless; 90/270 swap width and height). |
| `auto_orient` | image | image | Apply the image's EXIF orientation tag so a sideways/flipped capture displays upright. No-op when absent. |
| `autocontrast` | image | image | Stretch the per-channel histogram to full range (legibility for faint scans). |
| `contrast=<factor>` | image | image | Scale contrast by a float factor (`1.0` unchanged). |
| `grayscale` | image | image | Convert to single-channel grayscale. |
| `dpi=<N>` | (render config) | (config) | Rasterization DPI for `page=<N>`. Position-independent. Default 200. |
| `body` *(3.0)* | any | markdown | The record's **derived body** — the faithful mechanical rendering the 2.x draft stage stored: DOM→markdown under the overlay's capture-time chrome config (HTML), spine text (EPUB), reply-text trim (eml), verbatim passthrough (JSON, plain text), page markers (PDF). A pure function of (artifact × schemas × op version); what `corpus body` prints for a stub. |
| `members` *(3.0)* | container | json | Member enumeration (path/msg/part/stream axes with per-member hash, size, sniffed type) — the manifest, derived. |
| `transcribe` *(3.0)* | audio / audio stream | json/text | Speech-to-text over the addressed audio, with timestamps and speaker-turn indexes where determinable. **Version-labeled** (§6.4): the result carries engine + model version. |
| `turn=<N>` *(3.0)* | turn-structured record | json/text | The verbatim N-th unit of the record's declared unit array (1-indexed), located by the origin overlay's form mapping (§7.2) — for a chat transcript, the complete message object: reactions, edit history, attachment declarations, platform ids, one hop away from the envelope segments. |
| `turn=<N>&att=<M>` *(3.0)* | turn-structured record | bytes | The M-th attachment declared by unit N, materialized through **lineage-chained resolution** (below). |
| `cut=precise\|copy` *(3.0)* | (cut config) | (config) | Cut semantics for `time_range=` (the muxing contract): `precise` (default — frame-accurate, re-encodes) or `copy` (keyframe-snapped stream copy, disclosed). Position-independent, like `dpi=`. |
| `format=<token>` *(3.0)* | media / image | converted rendering | Output-format conversion, composing **after** selection and cutting (the muxing contract): `time_range=12:04-12:09&format=gif`. Changes encoding only, never the addressed content. |
| `scenes=<threshold>` *(3.1)* | video / stream | boundary proposals | Scene-cut boundary proposals over the video timeline — a text listing of cut timestamps at the stated detection threshold, engine-versioned (§6.4). Normalizer support for boundary work (`form/slide-deck`, §12.20): proposals to be verified by the pass, never marks. |

A parameter applied to an incompatible working type is a hard error.

A PDF `page=<N>` is a **page selector**, not an unconditional render: a per-page op after it (`render`, `text`, `words`, `probe`) reads the *selected page* directly, so `page=<N>&text` returns the page's embedded text layer rather than an OCR of its render. A terminal `page=<N>` (and any image op or `bbox=` after it) renders the page to an image, so an `address: page=<N>` image marker (§4.3.2.2) still resolves to the page bytes. The whole-document ops `probe` and `outline` operate on the PDF itself (no page selected). These introspection ops are how a normalizer determines a PDF's shape and extracts its content — the attestation itself is uniform (§11).

`fit=` presets are **implementation-defined**, not enumerated here: a preset (e.g. `llm`) bounds the result to a consumer's budget — typically a vision model's maximum input dimensions and pixel count — and those limits are model-dependent and drift over time, so freezing them into the spec would rot. The normative contract is only that `fit=` downscales aspect-preserving and never enlarges; the concrete bounds of any named preset live in the resolver implementation.

Parameter value grammar may be media-type-dependent; the resolver dispatches on the source artifact's type. In particular `bbox` is **polymorphic** — relative floats in `[0.0, 1.0]` when cropping a rendered image (an image artifact, or a `page=` render of a PDF), and a spreadsheet cell range (e.g. `bbox=B2:G30`) when narrowing a worksheet region — so the same token does not collide across media types. Pure **address selectors** that locate a region without transforming it — `sheet=<name>`, `el=<N>` (a 1-indexed index to *any* addressable element in an HTML artifact — content blocks plus inline-media carriers `<img>`/`<video>`/`<audio>`/`<a href="data:…">`; what it materializes is determined by the element, e.g. an `<img>`'s rendered image, a `<video>`/attachment carrier's raw bytes, or a text element's region), and any others — are defined by each media-type schema (§4.3.2) and are not enumerated here; §6.2 lists only the parameters that produce a derived view.

**The muxing contract** *(3.0)*. Media cutting, muxing, and conversion are resolver ops with normatively pinned *behavior* and implementation-owned *mechanics* — the contract maps onto ffmpeg's primitives, and exactly as with `fit=` presets, the supported codec/format sets are implementation-defined so the spec doesn't rot; only the behavior below is normative.

- **Composition cut.** `time_range=<s>-<e>` on a media **container** materializes a cut of the *composition*: default-member resolution (below) applied **per kind** — the unique-or-declared-primary video member plus the unique-or-declared-primary audio member — muxed into the source's container family. A kind with **zero** members is omitted from the composition — absence is not ambiguity (a silent video cuts video-only; an audio-only container cuts audio-only). Ambiguity within a *present* kind (two audio tracks, no declared primary) → the bare op fails stating it, never guesses. Subtitle tracks never ride implicitly — opt-in by selection.
- **Stream selection composes.** `stream_id=<id>&time_range=<s>-<e>` cuts one stream; an explicit subset is a comma list — `stream_id=0,2&time_range=…` (the repeated-`-map` analogue) — cutting exactly the named members, muxed.
- **Multi-cut.** `time_range=a-b,c-d` — the address grammar's existing ordered-list-for-non-contiguous-spans convention (§12.11), now materialized: the cuts concatenate in listed order. Concatenation is safe by construction — every cut shares the source's codec parameters. This is the composition layer's supercut primitive: one URI names an ordered excerpt reel of one source.
- **Cut semantics, ffmpeg-honest.** The default is **precise** — frame-accurate, which re-encodes: evidence is the primary consumer, and a cited 5-second clip must contain *exactly* the cited span. `cut=copy` is the disclosed fast path — keyframe-snapped stream copy, whose bounds may widen to the previous keyframe; the URI says so, so nothing silently drifts.
- **Format conversion.** `format=<token>` converts the working result's encoding, composing after selection and cutting (`time_range=12:04-12:09&format=gif` on an MKV → cut, then convert). Rules: (a) conversion changes **only the encoding, never the addressed content**; (b) targets must be **atom-compatible** — video→`gif` is a video-to-animated-image rendering (audio dropped by the format's nature, not by editorial choice), audio→`wav`/`mp3` is fine, audio→`png` is a hard error; (c) the supported token set is implementation-defined per the resolver's engine (the `fit=` precedent) — the contract is behavioral; (d) `format=` names *explicitly* what existing ops already do implicitly — a terminal `frame=` renders to an image, a terminal `page=` rasterizes, transcription extracts audio to an intermediate wav — one parameterized surface for the same idea.
- **Canonical application order**, pinned so one URI is deterministic and composable: **select → cut → convert → size** (`stream_id=` → `time_range=` → `format=` → `fit=`). A downscaled gif snippet of one stream is a single composable URI.

Cuts, muxes, and conversions are **version-labeled ops** (§6.4): encoder output drifts across engine versions, so results are cache-keyed by engine version and pure per version. They are ephemeral derived renderings with exactly the standing of a `page=` raster — never new artifacts, never new records.

**Lineage-chained resolution** *(3.0)*. A promoted record's resolver MAY chain through the record's own containment-lineage origin block (`uri: corpus://<container>?…`, §8.1) to materialize content its bytes *declare* but do not *contain*: read the declared reference from the record's own artifact (message N's attachment path), then resolve it as a member of the blake3-pinned parent container. The chain is derived at read time from (lineage block × record bytes) — never stored on any block — so it cannot rot: the parent is content-addressed and immutable, and an absent member (a reference the export never localized) fails loudly at resolve and surfaces in health, exactly the failure mode a stored pointer would have papered over. This is the transcript analogue of an HTML page's captured assets, with the container playing the role of the capture's asset store; it is also how a promoted track record inherits its container's chapter marks (§1.2) — reading up the lineage rather than copying down. *(Note: lineage-chained resolution is a resolver read of corpus state, which resolve has always been — §6.3; the byte-lookup independence rule of §12.9 is untouched: lineage is consulted for declared-reference chasing, never for the record's own byte residence.)*

**Default-member resolution** *(3.0)*. When an op requires a member of a given kind and the container holds **exactly one** of that kind — or the container itself **declares a primary** (HEIF's `pitm` primary-item box: a byte-fact, attested) — the member selector may be omitted and the op routes through transparently: `bbox=` on a Live Photo acts on the declared-primary still; `time_range=` reaches its motion component; `?transcribe` on a single-audio-track MKV needs no `stream_id=`. Zero candidates, or more than one with no declared primary → the bare op **fails stating the ambiguity** — it never guesses. Two properties are pinned. First, it is **read-side sugar only**: attested embeds always carry their explicit `stream_id=`/`item=` addresses, and nothing stored depends on the sugar existing. Second, it is **citation-safe by content-addressing**: the artifact is immutable, so whether a bare anchor is unambiguous is a *permanent fact of the bytes* — a citation that resolved once resolves forever, never invalidated by later state. (This is also why a single-track media container keeps `disposition: manifest` rather than flipping per record — the bare op is already transparent; §1.2.)

**Member re-chaining.** A member materialized through `path=` (§12.11 — a kept-whole archive: zip, tar/tgz) is not necessarily a terminal opaque byte-string: once extracted, the resolver re-detects the member's own mime from its bytes and filename and, when a further transform follows in the chain, re-enters the working-kind table (§7.1) for that mime — a PDF member takes `page=`/`text` exactly as a top-level PDF record would, a CSV member takes `row=`/`col=` (§12.11), and so on for every mime a `working_kind:` schema declares. A **terminal** `path=` (no further transform follows) never promotes to a full working-kind object merely to re-derive one — that would risk a silent, unrequested re-encode of a member no op asked to transform (an image member forced through a decode/encode round-trip, say); it decodes only an already-textual member (JSON, plain text) to its text, so a citation prints cleanly rather than as an opaque cache path. A member whose mime supports neither — no declared working kind, not textual — stays the raw `bytes` this axis serves by default, byte-identical to the address alone.

### 6.3 The resolver

A corpus provides a **resolver** that materializes any functional URI to a deterministic, cacheable, ephemeral result. *(3.0)* Ops fall into two determinism classes:

- **Pure ops** — a pure function of (URI × artifact × op version): same inputs, same bytes, always. All address selectors and the mechanical derivations (`body`, `members`, `text`, renders).
- **Version-labeled ops** — ops whose engine output may drift across engine versions (`transcribe`; OCR performed through the toolkit; the muxing contract's cuts, muxes, and `format=` conversions — encoder output is engine-versioned, §6.2): the result carries its engine + version, and the cache key includes them. Determinism holds *per version*. All remain ephemeral derived renderings — a precise cut has the same standing as a `page=` raster, never a new artifact.

The resolver's surface (CLI, library, HTTP service, etc.) is implementation-defined; the contract is that the URI scheme of §6.1 and the transformations of §6.2 are honored.

### 6.4 Caching

Resolver results may be cached. Cache lifetime, eviction policy, and storage location are all implementation-defined; the spec mandates only that the result is deterministic and reproducible from inputs — for a version-labeled op (§6.3), the cache key includes the engine + version.

**Pinning by authorship.** Until a pass consumes it, a version-labeled result is cache-transient — it may be regenerated under a newer engine, and nothing *in the record* depends on which (*3.1:* a ledger citation of a derived surface pins the op version on its own binding — `ledger.md` §13.2 — so drift there flags loudly without the corpus storing anything). The moment a normalize pass **consumes** such a result into the stored body, the output is pinned *in the record*, with engine/version provenance on the pass (touch chain) and on the segments where the form carries it (`text/ocr`'s engine/confidence fields — the §11 OCR-provenance philosophy, extended to transcripts): the corpus owns the derivation's provenance rather than laundering a pre-baked layer. A later pass re-derives only deliberately, disclosed by a new touch. This is what makes the retirement of the draft stage *reproducible*: a future normalize pass re-resolves the same surfaces — or knowingly upgrades them — without a stored intermediate rotting in between.

---

## 7. Schema declarations

§3 introduced the five namespaces and the schema-loader resolution chain. This section specifies what the four schema-declaration namespaces (`mime`, `origin`, `form`, `atom`) declare; the `context` umbrella's overlays are specified alongside the context block in §4.3.3.

### 7.1 The mime namespace

A `mime` schema declares everything the matching artifact block needs and everything ingest attestation and the resolver need to process the transport.

- `description` — prose definition.
- `applies_to.content_types` — list of canonical MIME types this schema covers.
- `applies_to.zip_members` / `applies_to.zip_member_patterns` (optional) — shape signature for a zip-shaped type whose telltale members sit under a *variable* wrapper directory (a diagnostics export, a backup bundle), so a fixed internal path can't recognize it. `zip_members` lists exact member paths (ANY present matches); `zip_member_patterns` lists member-path regexes (EACH must match some member). Evaluated by the shared MIME refiner against the corpus's schemas, so vendor/site-specific zip recognition lives in the overlay rather than the package. Universal zip formats (OOXML / EPUB / JAR) keep their fixed-path signatures in the tooling and need no declaration.
- `working_kind` (optional) — the resolver's initial working-value kind for the functional-URI transform pipeline (`pdf`, `image`, `audio`, `video`, `html`, `epub`, `zip`, …); falls back to a built-in table for the bundled types when omitted.
- `citation_surface` (optional) *(3.3)* — the format's honest **citation-surface class**, consumed by the ledger's evidence verification (`ledger.md` §6.3, §13.2) and printed by `corpus inspect`: `raw` (the default — the record's derived body is faithful line-of-sight content, so record-wide verbatim quote matching is honest even on a formless record: JSON, plain text, CSV) | `segments` (the raw/derived whole-record text is presentation soup — nav chrome, script payloads, inlined framing — so quote matching against it is *misleading rather than merely weak*; the record is citable only once persisted segments exist, and the honest demand against a segment-less record is `enqueue`, §8.5). Built-in default: the HTML family is `segments`; every other bundled type is `raw`. The class governs *citability*, never readability — any actor may read any record; a scribe reading a formless `raw`-surface record may cite it, and one reading a formless `segments`-surface record surfaces findings as interpretations plus an enqueue (with a form hint, §8.5), never as claim evidence.
- *(3.0)* `mode` and `draft.*` **retire** — there is no draft stage to configure. In their place a mime schema declares three things:
  - `disposition:` — `manifest` | `work` (default `work`): the **container-vs-transport judgment** (§1.2), declared per format because it is not derivable from the bytes. `manifest` — the members ARE the content: every member attests as a manifest embed (promotable), the content zone holds only container byte-marks. `work` — one transport whose content decomposes as units; internal member files the schema names attest as **exposable embeds** — addressable and promotable without being the content: a PDF's embedded files / portfolio members (the `attachment=<N>` axis, §12.11), OOXML embedded media and OLE objects. The authoring criterion is normative: *are the members independently meaningful transports?* An MKV audio track is (the transcript lives on it); `word/document.xml` is not. EPUB's 2.x `self_contained` wording is this key's ancestor (`disposition: work`). An origin overlay MAY override for a deviant producer (§7.2); the resolved disposition is always auditable from the record's attested shape, never sniffed per record. *(Distinct from the 2.1-removed `artifact_kind`, whose tombstone stands: nothing explodes at ingest under either value.)*
  - `attest:` — the **ingest attestations**: which byte-facts ingest stamps at ingest time. Artifact-block fields (a PDF's `/Info`, an EPUB's Dublin Core, an eml's headers); **manifest embeds** for `disposition: manifest` types (archive members at `path=`, mail messages at `msg=`, cards at `card=`, calendar entries at `entry=`, MIME parts at `part=`, media tracks at `stream_id=`, image items at `item=`); **exposable embeds** for `work` types that declare them; **structural byte-marks** (a media container's chapters); sidecar lift (§7.2). Attestations are deterministic byte-facts — the theme's "attested" half — and re-attest regenerates them (§8.3).
  - `derive:` — the **derivation ops** the type exposes (§6.2), with any per-type config (the 2.x `draft.manifest` config becomes the `members` op's config; a strategy-named general implementation may serve many schemas exactly as `zip-manifest` did).

  The concrete YAML key surgery (which 2.x keys alias, which hard-retire) is implementation-guide material (§12.4); a schema still declaring `mode`/`draft.*` is read tolerantly and ignored.
- *(2.1: `artifact_kind` removed.)* Every transport is self-contained (§1.2); a raw archive is attested as an embed manifest (§12.4) and its members are reachable by promotion (§8.1). A schema still declaring the field is ignored (tolerant parsing).
- `address_scheme` — the parameters the schema expects in segment `address:` values.
- `extended_fields` — fields the matching artifact block carries, each with type and optional `semantic_type` tag. *(3.2)* A declaration may carry `role: title` / `role: description`, marking the field as an editorial candidate for the record's derived title/description (§4.2.3) — the artifact layer's contribution, weakest in the precedence. The artifact block holds only facts about the **primary-artifact bytes** (e.g. ffprobe codec / dimensions / streams); source metadata from a capturer's enrichment sidecar does NOT live here — see `sidecar`. Vendor/domain identity (what a bundle *is*, beyond its bytes) does NOT live here either — that is knowledge, asserted in the ledger as roster entries and claims citing the record, minted mechanically by a harvest rule keyed on the kept-whole MIME (`ledger.md` §10).
- `sidecar` (optional) — for an artifact type a capturer enriches with a companion metadata sidecar (e.g. a yt-dlp `.info.json`), declares what is lifted and where. `source` names the sidecar (e.g. `ytdlp-info-json`); `ytdlp_keys` lists the info.json keys copied — each into the **origin block** as a flat `ytdlp_<key>` field (§7.2), the mapping the sidecar-lift attestation applies. The sidecar is companion metadata staged in `capture/<hash>.<suffix>`, consumed at ingest attestation (§8.1), then **deleted** — never persisted to `artifacts/` (only the artifact carries the `<hash>` name there). It is *non-primary-source* metadata, so nothing from it goes to the artifact block, the body, or the frontmatter `description`.
- `transport_algos` — additional byte-hash algorithms to compute beyond the primary blake3 `id`.
- `canonical_strategy` (optional) — procedure for computing the record's `canonical` hash. Names a canonicalization-algorithm id and the canonicalization steps performed before hashing. The canonicalization MAY be scoped to a **content region** — hashing only the article-content text and excluding per-page framing (title, breadcrumb, entry-specific headings) — so two records holding the same content reached by different URLs share a `canonical` and collapse to one record (the duplicate's URL folded into the original). The content-region selector is host-specific and supplied by the origin overlay (not this schema); when it matches nothing the canonicalization falls back to the whole document. *(3.0: whether the value computes at ingest attestation or as a derivation op is an open question — §12.18.)*
  - **Status — currently disabled (2026-06-28).** The pipeline still computes the value, but it is **not persisted**: no record carries `canonical:`, so the cross-URL content-dedup collapse described above is inert. Reason: `blake3-canonical-pdf` hashes only per-page extracted text, so every text-empty (scanned / image) PDF canonicalizes identically and unrelated scans were being silently merged into one record (the duplicate's bytes discarded). The mechanism is re-enabled once the strategy distinguishes such artifacts (e.g. a byte / rendered-image hash) and `canonical:` earns its keep.
- `normalization.guidance` (optional) — prose guidance for the normalizer.
- `form:` *(3.3)* — `{id: passthrough}` (or another **terminal** contract id, §7.8): the format's terminal-contract default — the class judgment that these bytes are their own terminal rendering. Mime-level `form:` admits terminal contracts ONLY (a rendering contract is producer knowledge and rides the origin overlay's `form:`, §7.2, which also overrides this default either way). Redundant for `disposition: manifest` formats — the disposition already derives `form/manifest` (§7.8) — so the key's real population is passthrough defaults on `work`-disposition formats: stills, raw streams, code, datasets, binaries.

### 7.2 The origin namespace

An `origin` schema declares an overlay for one source of retrieval.

- `kind: interpretive` — origin overlays are always interpretive (the match cue may be mechanical, but body guidance is consumed by the LLM normalize pass).

An origin overlay's `normalization.guidance` is **body-shaping tactics** — how to render this source's content faithfully — and, with subtypes (`origin/<id>/<subtype>`), it is the home for **per-page-shape** guidance within a host (how a procedure page vs. an index page of the same site normalizes). *(2.0: this guidance role was previously split with composite overlays; the domain-semantic half of composite guidance moved to ledger per-type conventions, the body-shaping half lands here.)* *(3.0: the guidance narrows accordingly — origin-specific tactics and provenance notes only; the decomposition contract lives on the form overlay (§7.8), stated once for every origin that maps onto it.)*
- `description` — prose framing of the publisher.
- `applies_to.host_pattern` (string, optional) or `applies_to.host_patterns` (list[string], optional) — host pattern(s) the pipeline matches against origin URIs (the `web` family).
- `applies_to.include_subdomains` (bool, default false).
- `applies_to.scheme` (string, optional) or `applies_to.schemes` (list[string], optional) — URI scheme(s) the overlay matches, compared case-insensitively against an origin URI's scheme. This is how a **non-web scheme family** (e.g. `imessage:`, a future `urn:` / `s3:`) binds, since such URIs have no meaningful host. An overlay may declare host pattern(s), scheme(s), or both.
- `applies_to.cues` (optional) — non-host cues for the matcher.
- `normalization.guidance` (string) — markdown prose tactics.
- `extended_fields` (optional) — fields beyond the universal `uri:` / `snapshot:`. A capturer's enrichment sidecar populates these — e.g. a yt-dlp capture's `ytdlp_<key>` fields (title, description, uploader, engagement counts, `ytdlp_comments`), declared by the artifact's mime schema `sidecar` section (§7.1) and merged onto the origin block at ingest (sidecar lift, §8.1). *(3.2)* A declaration may carry `role: title` / `role: description`, marking the field as an editorial candidate for the record's derived title/description (§4.2.3) — `ytdlp_title` role-marked `title` is the canonical case: every video record derives an honest display title from its sidecar lift, no pass required.

*(3.0)* An origin overlay MAY override its records' **disposition**:

- `disposition:` — `manifest` | `work`, overriding the mime schema's format default (§7.1) for this producer's records — an export tool that abuses an archive format as a single-work wrapper, or a format whose members are, for this producer, genuinely independent transports. Stamped and auditable like every overlay decision; never sniffed per record.

*(3.0)* An origin overlay MAY declare its records' **form**:

- `form:` — `{id: <form-id>, mapping: {…}}`. The `id` names the `form/` overlay every record of this origin carries (the **declared** stamping path, §4.4.6). The `mapping` names where the form's units live in *this producer's* format — for a chat transcript: the messages array path, and the per-message paths for author identity, display name, timestamp (+ its parse convention), text, reply reference, attachment declarations. The mapping is consumed mechanically — by the shaper that stamps and conforms the span at normalize, and by the resolver's `turn=` unit op (§6.2) — so a new platform is one origin overlay with a mapping, zero code. An overlay MAY declare `form:` with an `id` and **no** `mapping` when the shape is named but no mechanical shaper can drive it — adoption then rides the interpretive pass (§4.4.6). Absent the key entirely, records of this origin stand under the zeroth form (§4.1, §7.8) unless a form is asserted (§4.4.6).

- *(3.2 additive, 2026-07-16; match target narrowed 2026-07-17)* **Route-keyed declaration.** For a **multi-shape origin** — one host serving several shapes (a repair-data site whose routes carry procedures, bulletins, plates, and indexes) — `form:` MAY instead be a **list of match rules**, each `{match: <regex>, id: <form-id>, mapping: {…}?}`. `match` is tested unanchored against the qualified origin block's **primary `uri:` value only** — the first entry, the capture's identity URI. Dedup-folded alias URIs are alternate names and are deliberately NOT matched: aliases are not gate-grade route evidence — a hash-routed SPA that collapses a category route onto a single result pollutes aliases in *both* directions (non-bulletin sub-articles carrying genuine bulletin-route aliases, and vice versa), as the form-adopt-32 execution measured on real records (§12.22). Rules are tried in declaration order and the **first matching rule** is the record's declaration, exactly as if its `id`/`mapping` had been declared unconditionally; a rule without `match` matches everything (a terminal fallback, where the overlay wants one); a record matching no rule stands under the zeroth form, exactly as if the key were absent. Declaration order is the overlay author's precedence statement. The authoring discipline is conservative by design: a declared form is a **gate** (§8.5 — the pass cannot close until the declared form is stamped), so an overlay declares only routes whose shape is *certain*; an ambiguous route stays undeclared and its records adopt by assertion (§4.4.6).

The ingest pipeline iterates every origin block in the record. For each origin schema, if any origin block's `uri:` matches the schema's host pattern (or another declared cue), it upgrades that origin block's opener from bare `<!--origin-->` to `<!--origin <id>-->` and populates the schema's extended fields. The qualified opener contributes `origin/<id>[/<subtype>]` to the derived classifications view. (*Promotion* is reserved for the container-member operation of §8.1.)

An overlay `id` may also be **producer-declared** rather than `uri:`-matched. A capturer/producer that knows what it ingested stamps the id directly — `<!--origin <id>-->` written with the overlay's extended fields — which is the only way a **uri-less** origin (a dropped-in local file, e.g. an `imessage-export`) binds an overlay, since there is no `uri:` to match. Two mechanisms, both yielding the same stamped block: (a) a **capture sidecar** at ingest carries `origin_schema:` (the overlay id) + `origin_fields:` (its extended fields), consumed by the ingestor; (b) the producer injects **`<meta name="corpus-origin-schema">`** + per-field `<meta name="corpus-origin-<field>">` tags into the captured artifact, which ingest folds onto the origin block mechanically (a repeated field meta collects into a list). A stored `id` from any path is equivalent downstream: it contributes `origin/<id>[/<subtype>]` to the derived classifications view, its overlay's `normalization.guidance` surfaces for the normalizer, and it satisfies an `origin.id` predicate in a ledger harvest rule (`ledger.md` §10) — the producer-declared id is not re-derived from a `uri:`, so it works with none.

Two producer-export origins ride this uri-less, producer-declared path today. **`imessage-export`** binds a self-contained conversation HTML with attachments inlined. **`claude-code-session`** binds a captured Claude Code session — its `<id>.jsonl` transcript plus the sidecar tree of sub-agent transcripts, tool-result payloads, and workflow state — bundled into ONE deterministic zip by `corpus session capture` (§12.8) and carrying the session's identity as structured fields (`session_id`, `host`, `record_count`, …) rather than a synthetic URI. A session's record is a `zip-manifest` whose members are directly-addressed `path=<member>` embeds (the transcript is a transport resolved verbatim, never transcribed), and successive captures of a growing session are distinct records reconciled by continuity-gated supersession (§12.8), not by a stable id.

The universal `origin` overlay declares the fields every origin block carries. `snapshot:` is always present; an origin carries **either** a retrieval `uri:` **or** local-file metadata:

- `uri` (optional) — string or list-of-strings; the URI(s) by which the origin was reached. Present for a *retrieval* origin (a web capture, a synthetic-scheme source like `imessage://`). **Omitted** for a dropped-in local file: the staging path the bytes sat at is unlinked at ingest, so a `file://` path would be a reference dead on arrival — there is nothing to re-fetch.
- `snapshot` — ISO-8601 timestamp of observation (when the corpus saw this origin).
- `filename` / `source_modified` (local-file origins) — the dropped file's basename and its mtime (ISO-8601, `semantic_type: timestamp`, so it aggregates into the `timeline` view). These carry the durable provenance a `file://` path could not. A local-file origin omits `uri:` and carries these instead; an origin with neither a `uri:` nor local-file metadata is malformed.

**Directory layout — namespaced by URI scheme family.** Origin overlays live under `schema/origin/<scheme-family>/<id>.yaml`, grouped by the URI scheme they are retrieved over so each family can carry its own match semantics. The `web` family (http/https) is keyed by host — `origin/web/<host>.yaml`, matched by `applies_to.host_pattern` — while `otherwise/` is the catch-all for un-namespaced schemes and other families (`urn/`, `file/`, `s3/`) get their own sub-namespace and match predicate as a corpus needs them. The universal `origin/origin.yaml` sits at the namespace root and layers into every overlay. The overlay **id is the bare `<id>`** (e.g. `youtube.com`) regardless of sub-namespace, so the `<!--origin youtube.com-->` opener and the `origin/youtube.com` classification are independent of where the file lives. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`; the flat `origin/<id>.yaml` layout is still read for back-compat.

**Operational overlay sections.** Capture and transcription are retrieval concerns of an origin, so their per-host configuration lives on the origin overlay — one host-keyed file describes both *what* a source is and *how* to capture and process it. These sections are corpus-local (the package ships none) and read mechanically by the tooling; declaring them is how the tooling stays generic with **no hardcoded host knowledge**:

- `capture:` — how to retrieve this origin (read at capture time). One overlay serves **both** capture modes: a live URL fetch and a from-save replay of a manual SingleFile save (§12.3.12) resolve the same recipe and run the same `interactions`, so a host's chrome strip and media-surfacing steps are authored once for both.
  - `capturer` — the capturer name: `browser` (Playwright/HTML; the default), `video` (yt-dlp), or a corpus-local capturer. This is the **sole router** for video vs. browser — there is no built-in video-host list. (`corpus capture --video` / `--no-video` override it for a one-off URL.)
  - `transport` — `headless` | `headed` | `cdp` (browser capturer).
  - `fidelity` — `exact` | `balanced` | `lean` (browser capturer): the self-contained-snapshot completeness tier. `exact` is byte-faithful (presentation *is* content); `balanced` (the default) drops redundant font / image / media alternates inlined for self-containment; `lean` additionally prunes style rules with no matching element. The tiers affect only the snapshot **artifact** size — the record and its derived body are identical across tiers (the body derivation reads DOM text/tables, not fonts/CSS) — so fidelity is purely a per-origin retention/faithfulness choice. The resolved tier is stamped into a `corpus-fidelity` snapshot meta tag for provenance. Precedence: `corpus capture --fidelity` › per-host `capture.fidelity` › `origin/origin.yaml` › tooling default (`balanced`).
  - `url_rewrite` — `[{pattern, replacement}]` regex rules applied to the navigation target before fetch; the original URL stays the recorded origin and the rewritten form becomes an alias.
  - `url_equivalent` — declares which URL spellings denote the **same resource**, so the corpus matches an inbound URL to a record (and keeps one origin URI per resource) even when the spelling differs — query noise (`?nested_view=1`, tracking params), a redundant `/page-1` ≡ the bare form, etc. **Identity-only**: it computes a URL's *identity key* and never changes which bytes are fetched (that is `url_rewrite` / `interactions`). Two URLs are equivalent iff their identity keys are equal. Declared as a list of `[{pattern, replacement}]` rules (same shape as `url_rewrite`), or a map `{query: keep|drop, rules: [...], on_rewritten: bool}`. The identity key = the conservative `normalize` (lowercase scheme+host, sort query, drop a plain anchor, …), then — for `query: drop` (default `keep`) — strip the whole query, then apply the regex `rules` in order, then a final delimiter tidy, then fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`); with `on_rewritten: true` the host's `url_rewrite` is applied first so identity is computed from the fetched form rather than the inbound one. The trailing-slash fold is part of the **identity** key only, never of `normalize` — `normalize`'s output is the URL a crawl re-fetches, where the slash can be significant, whereas a comparison key may fold it (so a naive first-page rule like `…/page-1 → \1` need not chase the recorded slashed origin). **Opt-in**: absent the section, identity is exactly `normalize` (string match), so the layer is inert for every host that does not declare it, and host-scoped so a blanket `query: drop` cannot wrongly fold a host where `?page=`/`?id=` matters. Applied at the **capture short-circuit** (re-capturing a known resource is skipped), **crawl frontier dedup** (an equivalent of a visited / captured URL is not re-enqueued), **pagination uri-recording** (an equivalent spelling of an already-recorded constituent page is not appended), and **resolve** of a raw URL to its record. Pairs with — and is independent of — `url_rewrite`.
  - `pagination` — reconcile a work a site splits across `?page=N` / `/page-N` URLs into **one** record (browser capturer only). `true` enables it with auto-detection; a map gives control: `content_selector` (the per-page content region — else a structural page-1-vs-page-2 diff finds it), `next` (`{rel: true}` follows `<link/a rel=next>`, the default; `selector` overrides with a CSS link), `max_pages` (safety cap, default 100), and `expect_count.selector` (an element whose text holds the site-advertised item count, for the completeness check). The capturer walks the pages, captures each via the staging-only path, merges their content regions into page 1's framework — **deduping by element id or a normalized-subtree hash** — and ingests the merged document. **INVARIANT: exactly one artifact and one record result; per-page captures are never content-addressed.** The clean seed is the recorded origin URI; every constituent page URL (bare site form *and* the pinned `url_rewrite` form) is folded in as an origin alias, and a `pagination: {pages, form, posts}` provenance field lands on the origin block (`posts` = the merged content-item count: id-bearing region children when present — forum/CMS posts carry stable ids — else all direct children, so framework nodes don't inflate it). When the merged item count falls short of the advertised count, or `max_pages` is hit, a `pagination-incomplete` `warning` issue is emitted (capture stage) rather than silently shipping a lossy record. Pairs naturally with `url_rewrite` to pin one render form across every page.
  - `ytdlp:` — a mapping merged straight into yt-dlp's options (full passthrough; e.g. `format`, `getcomments`, `impersonate`). Library-owned keys (output path, logger, the resolved cookie file) are forced after the merge and cannot be overridden.
  - `cookies_from_host` — `true` (default) pulls the capture URL's own-origin cookies from a running CDP browser session into yt-dlp; `false` disables; a list adds extra origin scopes. Lets a logged-in session unlock a host's full content.
  - `also_capture:` — `[{role, capturer, …}]` supporting captures run after the primary one; their bytes **enrich the primary record** (e.g. a comments page folded into the record's metadata) rather than forming separate records.
  - `references:` — `[{match, role, capture, cross_host}]` — declares which of a captured page's outbound links are **dependent reference material** (a PDP's product manual, a spec sheet). Each rule's `match` (`selector` / `href_pattern` / `text_pattern` / `rel`; present keys ANDed, rules ORed) selects `<a>` elements in the captured page's DOM. **Emission is mechanical and rides the normalize pass** — the anchor needs the authored body (§8.1; record-scoped emission today — §12.15) — regenerating on re-normalize (§4.4.6): each distinct declared link (resolved + normalized, excluding the record's own origin URIs) emits one `reference` context block (§4.3.3.3) on the primary record, with `provenance: auto`, the rule's `role`, and tier 2 (`source_url`). The mechanical emission writes **no** tier-3 `source_uri` and reads no corpus state: whether the target is itself a record is a read-time derived edge resolved from `source_url` (`derived_views.references` §9.9 / `corpus links --references`), so the emission stays a pure function of the artifact and the edge tracks the corpus (`captured ⇄ pending`) instead of a stored pointer that rots under removal/supersession (§4.3.3.3). **Fetching** the target is a separate **capture-side** action: `capture: true` (or `corpus capture --with-references`) fetches it **once, at depth 1**, as its own record (content-hash deduped) right after the primary; `capture: false` (default) is surface-only and the deferred `corpus crawl --references` pass fetches pending targets on demand. `cross_host: allow` (the default for references — manuals are off-host) permits reaching declaration matches on other hosts, but **only** matches — never a general cross-host crawl. Distinct from `also_capture`, whose bytes **enrich the primary record** rather than forming separate, referenced records. Absent the section the feature is inert (no hardcoded link knowledge).
  - `relations:` — `[{match, predicate}]` — the sibling of `references:` for **source-declared cross-link structure** (a "related information" rail, sibling-page navigation): the same match grammar selects the links, and the same mechanical emission writes one `relation` context block per distinct target (§4.3.3.5) with `provenance: auto`, the rule's `predicate` as the block subtype, and `target_text`/`target_url`. Relations are edges, not fetch demands — there is no `capture:` key; a relation target enters the corpus only through the ordinary crawl/capture paths. Absent the section, inert.
  - `assembly:` *(2.1)* — config for **pre-ingest bundle assembly** (`corpus assemble`, §12.3.11): repackaging a source's delivered part(s) into ONE indexed container bundle before ordinary ingest, for delivery formats that are transient (an expiring export job), access-hostile (a solid compressed stream), or envelope-less (a loose directory tree an export tool wrote straight to disk). Keys: `merge_parts` (union a multi-part delivery's member trees — the split is delivery, not structure), `conflict` (`error`: a same-path collision across parts with differing bytes aborts; identical bytes dedup), `additions` (an allowlist of declared NON-original files placed at the bundle root, outside the original tree — e.g. an out-of-band export report), `rewrites` (declarative `{from, to}` restructure rules; **empty is the norm** — the original internal structure is NEVER changed except by a rule asserted here), `excludes` (declared filesystem-cruft subtraction — fnmatch patterns; slash-less patterns claim the basename at any depth, slashed ones the full relpath; exclusions are reported, never silent), `level` (the bundle's compression level), `derive` (mechanical origin-field extraction patterns — filename-convention regexes, addition-content regexes, and `from_member_head` regexes over the leading bytes of glob-matched members of a directory source, greatest match winning across members — so every vendor-shaped fact lives in the overlay, none in the engine), `seed_fields` (which derived fields beyond `account`/`job`/`exported_at` ride into the sidecar), and `name_fields` (derived fields whose values join the bundle's filename and archive comment — the job identity where no job id exists). The assembled bundle is staged with a capture sidecar (`origin_schema:` + the derived/declared fields) and enters the pipeline through ordinary ingest; the consumed part archives are recorded as `source_parts` tombstones (filename + byte hash) on the origin block — a directory source, having no delivery envelope, leaves none (member byte-identity is carried per-member by the manifest's embeds). Absent the section, `corpus assemble` refuses the overlay.
- `transcription:` — per-host audio transcription (read by the `transcribe` derivation op, §6.2). `enabled: false` skips transcription (an `info` issue, not a `warning`); `adapter` / `base_url` override the global `[corpus.transcription]` backend. Absent the section, the global config applies.
- `canonical:` — `content_selector` scoping the `canonical` hash to the article-content region (§7.1). *(Currently inert — `canonical:` is not persisted; see the §7.1 `canonical_strategy` status note.)*
- `metadata:` — reserved hook to remap/disable how a capturer's enrichment sidecar maps into the record (per host). The mapping itself is **host-agnostic and applied for every yt-dlp capture**, and is **schema-declared**, not hardcoded: the keys lifted from the `.info.json` come from the artifact mime schema's `sidecar.ytdlp_keys` (§7.1). Because the sidecar is *non-primary-source* metadata, every lifted key lands on the **origin block** as a flat `ytdlp_<key>` field (e.g. `ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts) — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when yt-dlp returns it) becomes a `ytdlp_comments` list field; `webpage_url` / `original_url` fold into the origin `uri:` aliases. The sidecar is **ingest-time-only enrichment** (sidecar lift, §8.1) — staged in `capture/`, consumed at ingest attestation, then deleted; it is one-shot (a re-attest after deletion does not re-apply it; the lifted fields already persist on the record). Nothing mechanical writes body content: the **transcript** is the `transcribe` derivation op's output (§6.2), consumed at normalize.

### 7.3 The atom namespace

An `atom` schema declares an atomic-axis overlay that may attach to a segment.

- `kind: atomic`
- `description` — prose definition.
- `applies_to.atom` — `text`, `image`, `audio`, or `video`. Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `applies_to.cues` (optional) — heuristic patterns for the normalizer.
- `enables_lossless` (boolean, default `false`) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's other declarations describe what shape the body takes.
- `extended_fields` (optional) — id-specific fields. For lossless-enabling overlays these typically describe address-shape requirements; for envelope-bearing forms (a chat message's `sender`/`timestamp`) they carry the segment's structural envelope, verbatim from the source.
- `normalization.guidance` (string) — markdown prose tactics for rendering the form faithfully.

*(3.0)* An envelope-bearing atom overlay's extended field may be declared as a **codebook index**: an integer field whose value indexes a list field on the *enclosing form section's* header (e.g. `text/message`'s `participant:` indexing `form/conversation`'s `participants:` codebook — first-appearance authorship order, entry grammar `<display> <durable-id>`). The index resolves through the record alone — segment → section header → entry — so a consumer needs no platform knowledge; lint's form-coherence checks (§4.3.2.1) verify indexes are in range. A codebook index and a verbatim envelope string (`sender:`) are both licensed forms of the same envelope — the overlay says which its records carry (repeating a verbatim identity string across a 70,000-message span is what the codebook exists to avoid).

A segment carries exactly one atomic class id, on the opener line. The structural segment is not an atom and takes no atom overlay (§4.3.2.3).

**The atom constitution.** Atom overlays declare **form, never meaning**: the shape of a lossless body, the structural envelope of a segment, extraction tactics for a region's faithful rendering. "This text is a table," "this image is a screenshot," "this segment is one chat bubble with this sender and timestamp" are form statements, checkable against the bytes. A subtype whose payload is domain semantics — what the content is *about* — is wrong at this layer; that is a ledger claim over the segment's span (`ledger.md` §6).

### 7.4 The composite namespace *(removed in 2.0)*

*Retired with the classify block (§4.3.1.3).* The `composite` umbrella was the corpus's interpretive classification system — a pre-ledger claims system embedded in the archival layer. Where each part went:

| 1.0 mechanism | 2.0 successor |
|---|---|
| User-defined classification namespaces | Ledger **types and predicates**, under VOCAB discipline (`ledger.md` §8) |
| Asserted classify blocks (record scope) | **Claims** with record evidence (`ledger.md` §5–§6) |
| Section-scope composites | Claims with span evidence (§4.4.3) |
| `classify_when` deterministic membership | **Harvest rules** (`ledger.md` §10) — the same fact base and predicate grammar, evaluated ledger-side over corpus records |
| Mechanical extraction scripts | Harvest-rule `mint` templates over the same fact base |
| Domain-semantic `normalization.guidance` | Per-type authoring conventions (the ledger's `facts/SCHEMA.md` / concept schemas, `ledger.md` §8, §4.4) |
| Body-shaping guidance keyed by page type | The origin overlay (subtypes, §7.2) or an atom overlay (§7.3) |
| `extended_fields` | Claim values and qualifiers |

The fact base and predicate grammar that `classify_when` defined are now specified in the harvest-rule contract (`ledger.md` §10), unchanged in substance: draft-visible facts only (`mime`, `origin.*`, `media.*`) *(3.0: the fact base has since grown `form.*` — `ledger.md` §10 — and "draft-visible" reads "attested-or-derived, never authored prose"; 3.1 keeps that reading under the derived-state lifecycle, §4.1)*, exact-by-default operators, missing-fact-is-false, and body keywords permanently excluded as the canonical false-positive source.

### 7.5 Semantic-type vocabulary

A closed list of seven types. Schemas tag extended-field declarations with one of these to opt the field into a derived view (§9) or document its meaning.

| Type | Aggregated into | Notes |
|---|---|---|
| `uri` | `uris` derived view | String. Deduplicated across all uri-tagged fields and origin-block `uri:` values. |
| `timestamp` | `timeline` derived view | ISO-8601 instant or interval. Aggregated with origin-block `snapshot:` values (§9.4). |
| `identifier` | `identifiers` derived view | Vendor-issued opaque ID. The view also includes the record's own `id` (§9.5). |
| `hash` | (no view) | Cryptographic hash. |
| `fingerprint` | (no view) | Non-cryptographic content fingerprint. The segment-header field is spelled `perceptual:` (§7.7), but the semantic-type tag spelling remains `fingerprint`. |
| `person` | (no view) | A single alias string identifying one person. |
| `geolocation` | (no view) | Location reference. |

The vocabulary is closed.

### 7.6 Hash encoding convention

All three frontmatter hash fields (`transport`, `canonical`, `perceptual`) and the body-block hash fields (`<!--embed--> transport`, `<!--segment--> perceptual`) use a uniform encoding:

- Value type: `str` or `list[str]`.
- Value format: `<algo>:<hex>` — algorithm identifier as colon-prefix, lowercase hex value following.
- Lists are one-liner-friendly: `transport: [<algo>:<hex>, <algo>:<hex>]`.
- Parsing: split on the first `:` to obtain `(algo, value)`.

The `id` field is the exception — always bare blake3 hex (algorithm is invariant).

### 7.7 Atom fingerprint strategies

Perceptual fingerprinting is **opt-in** and **schema-gated**. A segment carries a `perceptual:` only when a `fingerprint` knob resolves on for its record — fingerprints are a near-duplicate / similarity-search signal, not a mandatory attestation, so the default is **off** and a record with no `perceptual:` is normal. The knob is a top-level field on a **mime schema** (the per-file-type default) and may be overridden on an **origin overlay** (for records from that source). Values: `false` / absent = off; `true` = on with each atom's *default* algorithm; an algorithm name or a list = on with those algorithms (a list yields a list-valued `perceptual:`). Resolution precedence, most-specific first: the ingest/re-attest CLI `--fingerprint` / `--no-fingerprint` override › origin overlay › mime schema › off. *(3.0: fingerprints attest at ingest where the knob resolves on; §12.4.)*

When fingerprinting is on, the algorithm for a segment is determined by its `atom:`, not by the source media-type. Each atom has a default algorithm; the knob may select an alternative where the atom supports more than one:

| Atom | Default algorithm | Algo prefix | Alternatives | Notes |
|---|---|---|---|---|
| `image` | perceptual hash (pHash, 64-bit) | `phash` | `dhash`, `ahash`, `whash` | Robust to re-encoding, mild crops, and small resamples. |
| `audio` | acoustic fingerprint (chromaprint) | `chromaprint` | — | Comparable across codec changes and bitrates. |
| `text` | simhash (64-bit) over normalized tokens | `simhash` | — | After Unicode normalization, lowercasing, and whitespace collapse. |

The `<algo>:<hex>` value records which algorithm produced it, so a record self-documents how it was fingerprinted.

### 7.8 The form namespace *(3.0; recontracted 3.1)*

A `form` schema declares one **rendering contract**: an expectation for how a set of bytes is faithfully represented in a markdown shape. It binds on a section-block opener (§4.3.2.1) exactly as an atom overlay binds on a segment opener. *(3.1)* The namespace is the corpus's **shape-contract library**, the third leg of a deliberate separation of concerns: **origin** says where the bytes came from, **mime** says what container they arrived in, **form** says what markdown shape renders them faithfully. The layers never bleed (§1.5 principle 5): an origin overlay binds a form and maps the producer's format onto it (§7.2); the form overlay owns the shape.

**The zeroth form** *(3.1)*. `formless` is a member of the form domain, not a gap in it — the library's **identity contract**: the faithful representation of the bytes is the bytes, delivered through the derivation ops (§6.2), its verification the attestation already in hand. It prescribes nothing about what the artifact is, which is exactly the record layer's discipline — and it is why there is deliberately **no catch-all shape and no default form**: stamping a generic shape on an artifact merely so it "has a form" asserts a shape its bytes may not have (much of what a corpus consumes — code, datasets, binaries, containers — is nowhere near document form). A named form is a **prescription, and it is earned**: by *identification* (an existing contract fits the artifact) or by *authorship* (a new contract is written for it); until then the record stands formless, consumable, and honest (§4.1).

- `kind: form`
- `description` — prose definition of the shape.
- `extended_fields` — the section-header fields the form's spans carry: **codebook lists** (e.g. `participants:` — authorship-derived, first-appearance order, entry grammar `<display> <durable-id>` — the join surface a codebook-index envelope field resolves against, §7.3) and span envelope facts. *(3.2, softening 3.1's MUST)* Every field SHOULD be mechanically derivable from the span's own bytes — derivability is the strong preference, and a fact that could be recomputed but is instead hand-stated is in the wrong layer — but it is no longer a requirement: a field may be **interpretive by design**, authored at the pass and disclosed by the touch chain, with the universal editorial header fields (`title:`/`description:`, §4.3.2.1, §4.2.3) the canonical case. Conformance checks (`checks:`, below) bind only the derivable fields; a declaration may carry `role: title` / `role: description` (§4.2.3).
- `decomposition` — the normal form, normatively: which segment kinds compose the span (the envelope atom overlays and their required header fields), the addressing axis (`turn=`, `time_range=`, `pages=` — the form is **modality-blind**: `form/conversation` covers a chat export at `turn=` and a recorded meeting at `time_range=` with the same envelope), attachment and event conventions.
- `checks` — the mechanical conformance obligations lint enforces on any span carrying this form (§4.3.2.1): required envelope fields, codebook indexes in range, address monotonicity. *(The check grammar is tooling-defined pending the first three overlays — §12.18 open questions.)*
- `normalization.guidance` — prose tactics for the authoring pass, stated **once** for every origin that maps onto the form.
- `editorial` (optional) *(3.3)* — a top-level block naming **mechanical composition templates** for the derived title/description (§4.2.3): `title_template`, a string — or an ordered list of strings, the §4.2.3 cascade — whose `{name}` placeholders reference this form's own `extended_fields` (`description_template` is a natural sibling, undeclared until a contract needs it — the grammar admits it without a further amendment). Distinct from an `extended_fields` `role:` mark, above — a mark names one field verbatim; a template composes several into one string, e.g. `form/statement`'s `"Statement — {account} — {period}"` (neither `account` nor `period` alone identifies one statement among an account's many others).

**Terminal contracts** *(3.3)*. Two members of the form domain prescribe the **absence** of a stored rendering — they are the zeroth form's judgment made assertable, closing the gap between *formless-unassessed* and *formless-by-design*:

- **`form/passthrough`** — the identity contract, named. Adopting it asserts the earned judgment that **no markdown shape will ever render these bytes more faithfully or more token-efficiently than the bytes themselves**, delivered through the derivation ops (§6.2). Its conformance check is the inversion of every other form's: the content zone holds structural byte-marks only — a stored rendering under a terminal contract is the lint violation. Its population: media streams and stills, code drops, datasets, binaries — the raw-context artifacts §4.1 names.
- **`form/manifest`** — the container specialization. The **members are the content** (`disposition: manifest`, §1.2): conformance binds the attested member embeds (the roster IS the attestation — nothing re-stated), the content zone holds container byte-marks only, and the editorial header vouches the *container* (what this bundle is, what its members span). One derivation keeps the judgment single: a `disposition: manifest` record with no rendering contract declared for it **stands under `form/manifest`** — the disposition already is the terminal judgment, and the contract refuses to make an owner state it twice. An overlay MAY still bind a rendering contract over a manifest-disposition record where one genuinely applies; the explicit declaration wins.

A terminal contract is **not** the catch-all this section forbids: the prohibition targets stamping a *shape* an artifact may not have, and a terminal contract prescribes no shape — it records that none exists, earned by the same identification discipline as any adoption (§4.4.6) and guarded the same way (terminal adoption to flatter a census is exactly the force-stamping §12.22 refuses). Declaration rides the overlay grain — a mime schema's `form:` default, an origin overlay's override, per-record assertion for exceptions — because formless-permanence is almost always a class fact, not a record fact.

**Governing-contract precedence** *(3.3; the guards measured against the real fleet at first implementation)*. A record's governing contract resolves: (1) the **origin overlay's `form:`** declaration (§7.2 — rendering or terminal); (2) the record's **own asserted whole-record section** (rendering or terminal) — a stamped per-record judgment outranks every class-grain default (the §12.20 promoted h264 slide-deck track is the measuring case: a raw-stream passthrough mime default must never condemn it); (3) the **mime schema's `form:`** terminal default (§7.1); (4) the **`disposition: manifest` derivation**. Two guards on (3)/(4), neither applying to (1)/(2): a class default never claims a record **already carrying a stored rendering** — grandfathered rendered content stays `rendered` until its pass exits it (§12.19), never retroactively condemned by a later class declaration — and the manifest derivation requires the manifest attestation to have actually emitted **member embeds**: a promoted member stub whose format family is manifest-dispositioned carries no roster of its own and stays `proxy` (the promoted vcard cards are the measuring case — §12.23 holds them proxy until their rendering contract lands). Stamping is **optional and editorial**: a terminal record needs no section at all (the declaration alone governs); a whole-record opener with an empty span is written only where the editorial header (§4.2.3) has something deliberate to say. Downstream: a terminal record **never gates and never enters the queue by default** (§8.5), health reports it as **terminal** — not proxy — and the ledger treats it as a **complete source** whose derived surfaces are permanent, full-strength evidence (`ledger.md` §6.3).

**Forms are a goal, not a rarity** *(3.1, amending 3.0's "rare by design")*. For the right artifacts — those with a faithful markdown shape — a named form is where the record is headed: messaging exports render as `conversation`, statements and receipts as their contracts, and the document population (captured articles, manuals, papers) as a small set of **generic shapes**. Adoption is **lazy and benefit-driven** — §4.4.6's two stamping paths, pulled by demand through the queue (§8.5) — never forced by totality: nothing requires every record to carry a named form, which is precisely what keeps the library honest and small. The population splits cleanly: formless-permanently (no faithful markdown shape exists — the identity contract IS the rendering), formless-for-now (a shape fits but none is yet identified, authored, or worth the pass), and formed. *(3.3: the split is machine-readable — formless-permanently is a terminal declaration, reported as `terminal`, and `proxy` narrows to formless-for-now-or-unassessed.)*

**The minting test** *(3.1 restatement)*. A form is minted when all four hold: (1) it names a **shape, never a subject** (below); (2) its decomposition contract states what a faithful rendering IS, precisely enough that conformance is **mechanically checkable against the bytes** — every fact it declares recomputable from the span *(3.2: every fact save the declared-interpretive fields — the editorial header fields and any field a contract explicitly declares interpretive — which stand outside the checks by design)*; (3) a **population wants it** — the contract recurs across ≥2 origins, or a generic shape covers a modality-wide population; (4) a consumer **uses it** — a shaper, a composition view, a harvest rule, or the ledger's span-precise citation surface. One origin wanting a shape is origin-overlay guidance; a label that changes nothing about rendering or checking is not a form. *(3.0's second criterion — "changes the normal form vs. mime + atoms alone" — relaxes: a generic shape may render close to what mime + atoms already produce; what it adds is the contract itself — a named, checkable expectation a stored rendering can be verified against (§4.3.2.1 coherence; `ledger.md` §13.2), which an uncontracted rendering never has.)*

**Generic shapes, guarded** *(3.1)*. A small generic hierarchy — on the order of `document`, `article`, `procedure`, `transcript`, `data-table-set`, `slide-deck` — is expected to cover the corpus's entire rendered population in **fewer than ten shapes**; a proposed eleventh generic shape is a design smell to be argued for, not a routine mint. A generic shape is still a real contract (an honest `form/document` binds artifacts that genuinely render as documents); what it must never be is a default (the zeroth form, above).

**Forms name shapes, never subjects.** `conversation`, `statement`, `receipt` are shapes: a time-ordered participant-attributed message sequence; a period envelope with transaction line items; an itemized-commerce document. `product-manual` is **not** a form — a manual decomposes as a generic document (`form/document` at most, 3.1), and manual-*ness* is a role (`reference` block `role:`) or a ledger claim. `episode` vs `film` are legitimate — act structure with title/credit conventions vs scene-and-chapter continuity are decomposition contracts in the bytes — while *which show* an episode belongs to is the ledger rostering the record onto a concept, exactly as `form/receipt` never names the merchant (the origin block and the bytes do). This is the normative line that keeps §4.3.1.3/§7.4 honestly tombstoned: the classify block asserted meaning at record scope and is not returning; the form opener asserts shape at span scope, mechanically checkable, nothing more. *(3.1)* The guard binds hardest exactly where the library grows: a shape is generic or it is nothing — `form/procedure`, never `form/<site>-procedure`; the subject half of any proposed compound form belongs to the origin block (provenance) or the ledger (meaning). Forms minted at 3.0: `conversation`, `statement`, `receipt` (each recurring across origins in the operating corpora). Minted at 3.1 (2026-07-16, the media-ops increment §12.20): `transcript` and `slide-deck` — the first generics to arrive by the lazy discipline, minted with their consumers (the promoted audio- and video-track records of presentation video, §1.2). The remaining generic shapes mint as their populations adopt and their consumers arrive — never before.

**Stamping** is §4.4.6's two paths (declared via the origin overlay's `form:` key; asserted by an interpretive pass through the normalize gate). **Coherence** is §4.3.2.1's lint rule. **Downstream**, `form.*` joins the ledger harvest fact base (`ledger.md` §10) — deterministic rosters keyed on shape (`every form/receipt records onto the spending concept`) — and composition views consume *(form, envelope)* tuples with no platform knowledge: the cross-platform conversation thread joins spans on (ledger identity × timestamp); the same-video view joins tracks on (lineage × timeline); one composition layer, two join keys, zero stored view state.

---

## 8. Pipeline

### 8.1 Stages

| Stage | Mechanics | Touch identifier shape |
|---|---|---|
| `capture` | Bytes land in the corpus's staging area. | none |
| `ingest` | blake3 of bytes → `id`; `transport_algos` → `transport:`; MIME detect → artifact-block opener; **byte-fact attestation** per the mime schema's `attest:` and `disposition:` (§7.1) — artifact fields, manifest/exposable embeds (members / messages / cards / entries / parts / tracks / items), structural byte-marks, sidecar lift; emit the record (the artifact's proxy, §4.1) with first origin block from capture context; persist binary. | `<pkg>.ingest@<v>` |
| `promote` | Mint a record for a container member already in the corpus: locate by embed declaration, stream + blake3-verify → `id`; MIME detect; **attest** per the member's mime schema; emit a record whose first origin block records the containment lineage as history (`uri: corpus://<container-id>?<member-address>` + `filename`/`source_modified` where present). Bytes are NOT copied (§2). | `<pkg>.promote@<v>` |
| `draft` | *(retired in 3.0.)* The stage's three duties split: fact-stamping → ingest **attestation** (above); content extraction → resolver **derivation ops** (§6.2); body-writing → the normalize pass. A `status: draft` record reads tolerantly as a just-attested record (§12.18). | — |
| `normalize` | The **one authoring pass**: consumes the derivation ops and renders the record under its named form contract (§7.8) — executed by a mechanical **shaper** where the record's declared form mapping (§7.2) or manifest shape makes it deterministic, by an interpretive agent where judgment is required — the form span's editorial header fields (§4.2.3), embed/segment descriptions, and faithfulness issues riding the same pass. | `<pkg>.shape.<id>@<v>` / `<model-id>` / combined (`+`) |

Idempotent re-capture is part of `ingest`. Concrete tooling is implementation-defined.

An origin overlay's `capture.references` (§7.2) drives two mechanical, deterministic actions (§8.2): the record-side **emission** of `provenance: auto` `reference` context blocks for the page's declared dependent links (at tier 2 `source_url`; the intra-corpus edge is resolved at read time, never stored — §4.3.3.3) — which rides the **normalize pass**: the anchor needs the authored body, and a record-scoped emission (today's only form, §12.15) rides the same pass, regenerating on re-normalize (§4.4.6) — and the **capture** side, for rules marked `capture: true` (or `corpus capture --with-references`), fetches those targets at depth 1 as their own records after the primary ingest. `capture.relations` (§7.2) drives the same emission for declared cross-link structure (`relation` blocks, §4.3.3.5), with no capture side.

A corpus may also specialize the **shaping** of its own content with corpus-local shaper code — `<corpus_root>/shapers/*.py`, loaded mechanically before the normalize pass (the analogue of the corpus-local capturer in §7.2). Such a shaper claims a record by its origin or form id (§7.2) and builds the authored content zone in place of (or ahead of) the generic mapping-driven shaper and the interpretive agent; the package ships none and knows nothing of any specific format. Implementation-defined — see §12.4.3.

### 8.2 The deterministic / LLM boundary

| Operation | Type | Why |
|---|---|---|
| Hashing, MIME detection, schema lookup | deterministic | mechanical |
| Byte-fact attestation (artifact fields, manifest embeds, byte-marks, sidecar lift) | deterministic | mechanical |
| Member promotion (byte streaming, hash verify, record mint) | deterministic | mechanical |
| Derivation ops (`body`, `members`, text layers, renders, unit ops) | deterministic | pure functions (§6.3) |
| Transcription / OCR ops | deterministic **per engine version** | version-labeled; pinned by authorship (§6.4) |
| Origin-host matching; overlay-declared reference/relation emission | deterministic | overlay-declared |
| Form-mapped shaping (a conversation's envelopes from a declared mapping) | deterministic | a shaper — scripts, not judgment |
| Derived editorial fields (role-marked precedence resolution, §4.2.3) | deterministic | a pure function of stored blocks + schemas |
| Description authoring | LLM | requires understanding |
| Interpretive shaping and form assertion | LLM | requires judgment |
| Issue surfacing | LLM (faithfulness) / detector (mechanical) | depends on kind |

### 8.3 Re-runs

Every stage is independently re-runnable; re-runs are **scoped**.

- **Re-ingest** — re-encounters bytes matching an existing `id`. Appends a touch; may append origin blocks.
- **Re-attest** — re-runs the attestation layer (new mime schema, richer attestations): strips + regenerates attested facts (§4.4.6), never the authored layer. *(Succeeds 2.x re-draft-full/scoped.)*
- **Re-normalize** — re-runs the authoring pass (shaper or agent); total replacement of the authored layer.
- **Re-resolve** — bare resolver-cache regeneration (`--regenerate`), including deliberate version upgrades of version-labeled ops.

Each re-run appends a `touch[]` entry.

### 8.4 Re-stub

`re-stub` is a deliberate reset operation that returns a record to its attested baseline (§4.1), ready for fresh attestation — the verb keeps its historical name. Everything **derived from a schema decision** is discarded. Everything **tied to the bytes themselves** is preserved.

| What survives | What is reset |
|---|---|
| `id`, `transport` — byte-intrinsic. | `title` and `description` → empty; `canonical`, `perceptual` (record-scope). |
| The artifact block's opener (the MIME) and the origin blocks with their `uri:` history. | The artifact block's attested fields, all embed blocks, all sections/segments (authored and byte-mark alike), all context blocks. |
| `visibility`. | Record body's content zone → empty. |
| `touch[]` collapses to its first entry (the original ingest touch) plus the re-stub touch. | |
| The persisted bytes. | |

Re-stub is invoked deliberately — never automatic. Its uses:

- Schema-shape design changes that make existing blocks invalid.
- Records whose accumulated normalize work was wrong.
- Migration from a deprecated schema generation.

Re-stub appends a `touch[]` entry of the form `<pkg>.re-stub@<v>`. It remains the migration translation point: it accepts older frontmatter on input — including any legacy `status:` field — and always writes a current-spec-shaped record on output, preserving byte-intrinsic state and discarding everything that depended on the prior schema shape.

### 8.5 The normalization queue

`normalize` (§8.1) is the one stage the corpus tooling does not itself initiate — it is driven by an external **loop session** (a scheduled agent), which runs the mechanical shaper where the record's form mapping licenses one and works interpretively where not (§12.5). The tooling provides only the **request/claim contract** that lets any actor ask for a (re-)normalization pass and await its result; it never invokes a normalizer.

*(3.1)* The queue is **standing demand, never a backlog**. An entry exists because some consumer wants a pass — the ledger citing into a record, a codex compiling one, an overlay newly declaring a form, guidance improving — and the queue's size measures outstanding *demand*, not outstanding *work owed*. A formless record no consumer has asked about is complete, not pending (§4.1); it enters the queue when a reason does.

**The queue never writes records.** A record's `touch[]` and body are authored solely by `ingest` and the normalize pass (§8.1). Queue state is **external to the record** and untracked — regenerable orchestration, like `capture/` and `cache/` (§12.1). Queue operations are **read-only on records**: they may read a record (to gate on lint, or report a result) but never mutate it. One writer per concern — the normalizer owns the record; the queue owns only its own entries.

**Requests are state-independent and repeatable.** A record may be enqueued in any state — a formless proxy for a first pass, or a formed record for a *refinement* when a new overlay matches it or its guidance improves (re-normalize, §8.3). No state is terminal to the *queue*; each completed pass appends a touch. Enqueue never inspects the record. *(3.3: a **terminal-contract** record (§7.8) may likewise be enqueued — a deliberate describe pass, or an explicit re-evaluation — but it is never enqueued by default and its default pass is a no-op: see the pass gate below.)*

A queue entry moves `idle → requested → claimed → idle`, recording the last pass's outcome:

| Verb | Effect | Writes record? |
|---|---|---|
| `enqueue <id> [--hint "<text>"]` | request a (re-)normalization pass; idempotent — a request arriving while one is pending joins it. *(3.3)* `--hint` stores free-text requester context on the request, surfaced to the drain side (listing, claim, guidance) — the **proposes/disposes seam**: a reader of a formless record may propose what it looks like ("form/conversation candidate: messages[] with sender/timestamp") without authoring anything; the normalizer disposes against the bytes. A joining request's hint appends, never overwrites. | no |
| `drain` | atomically **claim** the next pending entry and emit its `id`; an empty queue is a non-error empty result — the loop's stop signal. A blocking variant long-polls for the next claim instead of reporting empty (the *standing* mode below). Reclaims a claim whose lease has lapsed (a dead session). | no |
| `finalize <id>` | close the claimed pass **complete** — gated on the **pass gate** (below); refuses (non-zero) on a blocking finding, so a dirty pass is never reported done. | reads only |
| `release <id> [--failed]` | return a claim — bare re-queues it; `--failed` records a failed outcome. | no |
| `await <id>` | block until the requested pass reaches a terminal outcome; success/failure by exit status. | reads only |

**The pass gate** *(3.1, succeeding the 3.0 `status: normalized` gate; re-keyed 3.2)*. **Done** means the pass left the record **formed where its overlays declare a form** (§7.2, §4.4.6 — form-coherence lint covers the conformance half) and linting clean. Both are derived from the record itself; `finalize` enforces them together. *(3.2: the 3.1 gate's authored half dissolves with the layer — a formed span's editorial fields ride its section header under its own contract, and a record staying formless owes no vouch: its derived title/description are already honest, §4.2.3.)* *(3.3: a record governed by a **terminal contract** satisfies the gate with no stored rendering — the contract prescribes exactly that — so a terminal record drains to an immediate no-op `finalize` unless the request explicitly asks for re-evaluation or a describe pass; an accidental enqueue self-heals.)*

**Drivable by an external loop, in either of two modes.** The claim is atomic (concurrent loops never double-claim) and every verb is non-interactive with a meaningful exit code and machine-readable output, so an agent loop runs `drain` → normalize the emitted id in-session → `finalize` (or `release --failed`) each iteration. A **scheduled** loop (e.g. cron) drains until the queue reports empty, then waits for the next tick — simple, but the loop session itself does the polling, waking even when there is no work. A **standing** loop instead blocks on the `drain` long-poll, which waits in the tooling until a request is claimable and returns it the instant one appears — so the (costly) loop session is engaged only when there is genuinely work. Both drive the same atomic claim; the long-poll is an ergonomic over it, not a distinct contract, and the same loop body serves either. The normalizer reads the record's applicable overlays' `normalization.guidance` (mime §7.1, origin §7.2, form §7.8, atom §7.3); because form knowledge rides in overlays, one generic loop serves every source — and demand flows down from the ledger, whose citation discipline prefers formed surfaces and raises demand by enqueuing (`ledger.md` §6.3): the ledger contributes by enqueuing, never by supplying a normalizer. *(3.0; completed 3.3)* The loop session's first consult is the record's **governing contract**, and the pass branches four ways: (1) **terminal** (§7.8) — no-op `finalize`, unless the request explicitly asks for re-evaluation or a describe pass (the opener's editorial header, embed/segment descriptions — the licensed residue); (2) **declared form, mapped** — the shaper writes the form mechanically and the agent's remaining work is the span's editorial header fields and descriptions (§4.2.3); (3) **declared-but-unmapped or asserted form** — the interpretive case, and on an already-formed record a *refinement*: improve the existing shaping, never regress it; (4) **no form, no terminal** — the **adoption sweep**: test the library's contracts against the record's own bytes and adopt by assertion where one genuinely fits (§4.4.6), under the §12.22 discipline — body evidence wins, substantive-content veto, and a record matching no contract exits the pass formless and reported, never force-stamped. `finalize`'s done-gate is the pass gate above, form-coherence (§4.3.2.1) included.

**Entry lifecycle and pruning.** A request and its claim are transient — each transition supersedes the prior state — but a settled pass records its **outcome** so a requester's `await` can resolve it, and so a *re-normalization* is distinguishable from an earlier pass (which the record alone cannot tell apart — only its touch chain grows). An outcome is **coordination state, not history**: the record's own `touch[]` is the durable trail. Because a requester may `await` after a loop iteration ends, an outcome is **never discarded at loop end** — that would race the awaiter, dropping it to the record-state fallback. Outcomes are instead garbage-collected by **age**: a settled outcome past a grace window (plus any orphaned scratch) is prunable, never a live request or claim — so the queue's footprint stays bounded without dropping an outcome a requester still needs. The grace window and the prune trigger are operational policy, not part of the contract.

---

## 9. Derived views

Cross-cutting aggregates over a record's frontmatter and body blocks, computed on demand. None are persisted.

### 9.1 The `classifications` view

Computed by walking the body — structural-derived only (§4.4.6):

```
classifications := []
on <!--artifact <mime-type>-->:
  classifications += ["mime/<mime-type>"]
on <!--origin <id>[/<subtype>]-->:
  if id present:
    classifications += ["origin/<id>[/<subtype>]"]
on <!--section <form-id>-->:
  classifications += ["form/<form-id>"]
dedupe preserving body order
```

Embed blocks and context blocks are NOT included. A record carrying an artifact block and one qualified origin block yields:

```
[
  "mime/<mime-type>",
  "origin/<origin-id>"
]
```

*(2.0: the classify-block rows are gone with the composite namespace. "What does this record document" is a ledger query — the concepts rostering the record, the claims citing it (`ath ledger worklist`, `ledger.md` §13), and the coverage ledger (`ledger.md` §9).)*

### 9.2 The `issues` view

The `issue`-namespace projection of the annotations zone (the full annotation set is the `context` view, §4.3.3):

```
issues := []
on <!--context issue/<id>[/<subtype>]-->:
  issues += { id: "<id>[/<subtype>]", severity, resolution, detector, address?, ...fields }
```

Returns structured records — each issue carries its id/subtype + universal fields + optional `address:` + any id-specific fields. Context blocks in other namespaces (`reference`, …) are not in this view.

### 9.3 The `uris` view

Aggregates:

- Every origin-block `uri:` value across all origin blocks (flatten lists).
- Every body-block extended field tagged `semantic_type: uri` declared by any matching schema.

Deduplicated with URL canonicalization.

### 9.4 The `timeline` view

Aggregates:

- Every origin-block `snapshot:` value.
- Every body-block extended field tagged `semantic_type: timestamp`.

Returns an ordered list of `(timestamp, source)` tuples sorted ascending, where `source` names the origin block or semantic-tagged field the timestamp came from.

### 9.5 The `identifiers` view

Aggregates every body-block field tagged `semantic_type: identifier`, plus the record's own `id`.

### 9.6 The `token_counts` view

Three **cumulative** estimates of a record's size as model context, for budgeting and discovery:

- `body` — tokens in the content zone's text-atom segment bodies only.
- `blocks` — tokens in the whole record markdown (frontmatter + every metadata/annotation block + the content zone). Always ≥ `body`.
- `full` — `blocks` plus an image-token estimate summed over image embed blocks and an image artifact, each `≈ min(width·height, cap) / pixels-per-token` from the declared dimensions (`0` when dimensions are absent).

The text tokenizer and the image constants are an implementation choice (§12.13), not part of the contract — what the spec fixes is the **shape**: three cumulative tiers, ordered `body ≤ blocks ≤ full`. Structural segments carry no body and count toward `blocks` only, never `body`. Like every §9 view it is computed on demand and never persisted.

### 9.7 The `concepts` view *(removed in 2.0)*

*Retired with the `concept` namespace (§4.3.3.4).* "Which records invoke this thing" is a ledger query: the concept's artifact roster and its claims' evidence URIs point at the records, and coverage (`ledger.md` §9) is the record-first direction.

### 9.8 How views are computed

A derived-view walker:

1. Loads the record's frontmatter and parses the body's three zones.
2. For each matched block, loads the corresponding schema chain.
3. Walks blocks, collecting values per view rules.
4. Deduplicates or sorts per view.
5. Returns the result.

Views are computed at query time.

### 9.9 The `references` view

The `reference`-namespace projection of the context view (§4.3.3.3) — the sibling of the `issues` view (§9.2), and the pattern the `relation` namespace (§4.3.3.5) follows. Each entry carries the stored ladder (`attribution_text`, `source_url`), the anchor (`address`, `quote`, `occurrence`), `provenance`, `role`, and the **derived** tier-3 resolution (`resolved_uri`/`captured`, computed against the URI index at read time — §4.4.5). The resolved edge is directional toward the depended-on record; the reverse ("records that reference *this* one") is a corpus-wide read derivable from these edges but, like cross-record content addressing (§11), the corpus-wide index is not specified here. Computed on demand, never persisted.

---

## 10. Export

A record renders correctly only inside its corpus, because segment bodies embed derived views via functional URIs that need a resolver. **Export** produces a portable, self-contained rendering by materializing each functional-URI embed to a file alongside the exported record and rewriting the embed reference to point to the local file.

Embed rewrite contract:

```
![[corpus://<hash>?<params>|<alt-text>]]   →   ![<alt-text>](<local-file>)
```

Export is idempotent and untracked. The output layout (filenames, directory structure) is implementation-defined.

---

## 11. Out of scope

Genuinely deferred items for this spec version:

- **Automatic PDF text / OCR extraction.** Every PDF presents **uniformly** — `/Info` fields attested, and a derived body (§6.2) of per-page body-empty `image` segments addressed `page=<N>` — regardless of born-digital or scanned. Deciding a page's shape, pulling its embedded text layer, transcribing a scan into `text/ocr` (with engine/confidence provenance — the corpus owns OCR provenance rather than laundering a pre-baked layer), and outline-driven structural marks are all **normalize-pass** work over the resolver's introspection ops (§6.2). What remains deferred is an *automatic* (non-agent) text-or-OCR pass.
- **Deterministic stream extraction** *(3.0)*. Track promotion from media containers (§1.2) requires member-byte determinism; the mbox precedent achieves it by pinning extraction semantics on the mime schema, and the same discipline is required here (elementary-stream sample data in decode order per the container's own tables; HEIF `item=` payloads likewise). Pinning a demuxer's output across tool versions is an open engineering item — content-addressing plus continuity-gated supersession (§12.8) is the net if a pinned extraction ever shifts bytes.
- **SQLite databases** *(3.0)*. An application's SQLite store (`chat.db`, `Photos.sqlite`, a browser's history db) is THE container of raw app data, and rows are deterministically addressable — a row/query axis would be well-defined under the disposition machinery above. Deferred **deliberately**, not overlooked: the corpus philosophy prefers **producer-declared exports** — the app's own export surface, with its declared semantics — over reverse-engineered application internals, and no real capture has yet wanted the database itself. When one does, `disposition: manifest` plus a pinned row-extraction scheme is the landing zone; until then this silence is a decision.
- **Cross-record content addressing** via `<!--embed--> transport` — the shape leaves room for a corpus-wide `transport → (record_id, address)` index but the index itself is not specified. (Building it requires reconciling the `<algo>:<hex>` embed `transport` encoding with the bare-hex record `id` — strip the prefix and confirm `algo == blake3` before matching.)
- **Range-aware navigation** for content the resolver doesn't materialize.
- **`page=<N>-<M>` ranges** and other open transforms beyond §6.2.
- **Whole-corpus build tooling** — single-record export is in scope; bulk operations are not.
- **Export to non-markdown formats.**
- **Additional semantic types** beyond the closed seven.
- **Recursive dependent capture.** `capture.references` (§7.2) fetches declared references at **depth 1** only; following a grabbed reference's own references — and any general multi-hop crawl — remains `corpus crawl`'s job, not the capture-alongside path.

---

# Part II — Implementation guide (non-normative)

## 12. Implementation guide

This part describes how the reference pipeline — the `corpus` tooling shipped by the orchestrator repo — produces records that conform to Part I: which passes run in what order, where files land on disk, detection and dedup strategy, queue mechanics, and maintenance. Part I says what each record carries; this part says how the pipeline gets there. Nothing here is mandated: an implementation is free to make different choices as long as it honors the Part I contracts, and where the two disagree, Part I wins and this part gets corrected.

### 12.1 On-disk layout and sharding

A typical filesystem-backed corpus:

```
corpus-<name>/
├── README.md                optional
├── records/                 tracked: record markdown files
│   └── <id[:2]>/<id>.md
├── schema/                  tracked: mime / origin / atom / context
├── artifacts/               UNTRACKED: raw-bytes cache
│   └── <id[:2]>/<id>.<ext>
├── capture/                 UNTRACKED: in-progress capture staging
├── cache/                   UNTRACKED: resolver-output cache
│   └── <urihash[:2]>/<urihash>.<ext>
├── queue/                   UNTRACKED: normalization request/claim state (§8.5)
├── export/                  UNTRACKED: regenerable export bundles (§10)
└── .gitignore               lists the untracked directories
```

- **`records/` and `schema/` are tracked** in version control; the markdown records are the source of truth.
- **`artifacts/` is the binary cache and is never tracked** — a corpus's `.gitignore` lists it. The cache is regenerable from blake3 plus capture provenance: destroyable and rebuildable at any time. The contract is only "given a blake3, this corpus can produce the bytes" (§2); a local filesystem shard, an object store, an S3-compatible bucket, or a content-addressed store all satisfy it. Consumers should not hard-code the path scheme — they should ask the corpus how to locate `<blake3>`. A **promoted** record (§8.1) has no `artifacts/` entry at all: its bytes materialize through its container via the member index (§12.9), which is just another way of satisfying the same contract.
- **Sharding is one level deep, by the first two hex characters of the leading hash**, with the same depth for `records/`, `artifacts/`, and `cache/`. That gives 256 buckets: at ~10k records the average bucket holds ~40 entries; at 100k, ~400. Deeper trees are a layout choice, not a contract (§12.15). The full hash stays in the filename, so a copy outside its shard directory still names itself fully — useful for moves, backups, and ad-hoc inspection.
- **Capture staging** lives under `capture/`: failed or abandoned captures sit there without consuming corpus identity space, and ingest unlinks a staged capture on success.

### 12.2 Schema directory layout

The namespaces of §3 are conventionally laid out as:

```
schema/<namespace>/<namespace>.yaml              namespace universal
schema/<namespace>/<axis>/<axis>.yaml            axis common guidance (mime and atom)
schema/<namespace>/<axis>/<axis>_<id>.yaml       specific declaration
```

The **underscore-flattened** subtype convention (`text_html.yaml` inside `text/`, rather than `html.yaml`) keeps filenames self-describing.

Annotation overlays use the namespace pattern under `schema/context/` — `context/<ns>/<ns>.yaml` layering under `context/<ns>/<id>.yaml` (the bundled `issue` overlays live here).

Inside `origin/`, overlays nest by **URI scheme family** (§7.2): `schema/origin/web/<host>.yaml` for http(s) sources (host-matched), `schema/origin/otherwise/<id>.yaml` as the catch-all, and other families (`urn/`, `file/`, `s3/`) as a corpus needs them, with the namespace universal at `schema/origin/origin.yaml`. The overlay id is the bare `<id>` regardless of sub-namespace; the flat `schema/origin/<id>.yaml` form is still read for back-compat. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`.

### 12.3 Capture

A capture takes a target — URL, filesystem path, manual upload — and produces a record plus its binary in the content-addressed store. The pipeline is content-addressed end-to-end: identity is the hash of the bytes.

#### 12.3.1 Fetch and capturer routing

**Routing is overlay-driven — no hardcoded host knowledge.** The capturer is chosen by the origin overlay's `capture.capturer:` field (`browser` — Playwright/HTML, the default; `video` — yt-dlp; or a corpus-local capturer name); `corpus capture --video` / `--no-video` are one-off overrides. There is no built-in video-host list: a host that should go to yt-dlp declares `capturer: video` in its overlay, so an undeclared video URL captures as HTML unless `--video` is passed.

- **HTTP/HTTPS URL** — fetched with redirect-following enabled. The original requested URL and the final-after-redirect URL both land on the record's first origin block (`uri:` list).
- **Filesystem path** — copied from staging, which is unlinked at ingest; the origin block is uri-less and carries `filename` + `source_modified` instead (§7.2).
- **Manual upload** — the operator supplies the bytes and any origin URI.

Inline media a transport merely *references* (images in an HTML page, etc.) are not separate records: ingest attests an embed block per asset (deduped by `transport` byte-hash), and the body carries an `image`/`audio`/`video` positioning segment (§4.3.1.4) — never an intra-corpus wikilink (those are reserved for cross-*artifact* references, §4.3.2.2). A raw archive is no exception (2.1): it is attested as an embed manifest, and a member becomes its own record only by deliberate promotion (§8.1). Hyperlinks to *other* resources are reconciled to intra-corpus references during cross-reference resolution (§12.4.7).

**Corpus-local capturers.** A corpus can ship its own capturer code under `<corpus_root>/capturers/*.py`. `corpus.local_code.load_corpus_modules(corpus_root, subdir)` imports these by path (`importlib`, not `sys.path`, so distinct corpora cannot collide on a module name), registering each module in `sys.modules` before exec, idempotently per `(root, subdir)`, with per-file failures logged and skipped. Trust boundary: this executes Python from the corpus root — the corpus owner's own code, which is the point of the tier — but a serving layer never captures, attests, or shapes, so merely fronting a corpus never runs it.

#### 12.3.2 MIME detection

MIME detection selects the **mime schema** that drives the rest of the pipeline (`transport_algos`, address scheme, attestations, derivation ops):

1. **Magic-byte sniffing** — the primary path (`mime.detect`). Inspect the leading bytes; refine ambiguous container magic by form-type and extension (a RIFF prefix → webp/wav/avi by its offset-8 form-type; an ISOBMFF `.m4b` → `audio/mp4`, not `video/mp4`, so it routes to transcription rather than the video keyframe path). A `PK\x03\x04` zip is refined by its members (`_refine_zip`): universal formats (OOXML / EPUB / JAR) match fixed internal paths baked into the tooling, while a corpus's *own* zip-shaped types (a diagnostics export, a backup bundle) match their schema-declared shape signatures (`applies_to.zip_members` / `zip_member_patterns`, §7.1) when a `corpus_root` is in scope — vendor-specific recognition lives in the overlay, not the package, and an unrecognized zip stays `application/zip`. An mbox opens with a `From ` separator at offset 0. A single email message (`message/rfc822`, typically a promoted mbox `msg=<N>`) has no magic number, so it is recognized by **header shape** — a distinctively-email header prefix (`Return-Path:` / `Received:` / `X-GM-THRID` / …), or, after the extension hint, two consecutive header-shaped lines — with the mbox `From ` separator always winning first (an mbox opens with the separator, an eml never does).
2. **Extension hint** — disambiguates where magic is generic, and names the type for extensionless or schema-id-from-filename cases.
3. **`unknown` sentinel** — when both fail. Record the gap; the artifact is still valid, it just gets no format-specific attestation or derivation.

The detected MIME becomes the **artifact block's opener argument**, which is authoritative — there is no frontmatter media-type field (§4.3.1.1).

#### 12.3.3 Hashing

The hash families of §2 / §4.2.1 land at different stages (§7.6 encoding):

- **blake3 of the bytes** — always, at ingest. The artifact's `id` (bare hex): identity and filename stem.
- **`transport_algos`** — additional byte-level algorithms the mime schema declares (e.g. `sha256` for interoperability), computed at ingest into `transport:` as `<algo>:<hex>`. The primary blake3 is on `id` and is not duplicated here.
- **`canonical`** — a content-canonical hash computed by the mime schema's `canonical_strategy` (`blake3-canonical-{pdf,html,image,epub}`; at ingest attestation or as a derivation op — §12.18 open question). Currently computed but **not persisted** (see the §7.1 status note); without it `records.content_key()` returns `None` and `find_content_duplicate` short-circuits, so the cross-URL content-dedup fold is inert.
- **`perceptual`** — atom fingerprints (image pHash, text simhash, …), **opt-in and schema-gated**, attested at ingest only when the fingerprint knob resolves on (§12.4.4); default off. Per-segment on multi-atom records, record-scope on single-atom ones (§7.7).

There is no frontmatter `hashes` field and no mandatory per-MIME perceptual hash. A MIME with no canonical strategy and no fingerprint knob is blake3-`id`-only, and that record is normal.

#### 12.3.4 The record at birth *(3.1; formerly "the stub record")*

Ingest emits the record — the artifact's proxy, complete at birth (§4.1). The frontmatter carries only the bytes-identity header — `id`, `transport:` (any `transport_algos`), `touch: [<pkg>.ingest@<v>]`; *(3.1)* no `status` field; *(3.2)* no editorial fields — the display title/description derive from the role-marked attested and sidecar-lifted fields the same ingest just stamped (§4.2.3), so the proxy is presentable the moment it exists. Everything else lands in body blocks:

- The **artifact block**, its body holding the format-intrinsic extended fields the mime schema declares, named bare (`title`/`author`/`page_count`, not `pdf_title`; §4.3.1.1). Sources: PDF info dict, EXIF, ID3, HTML `<meta>`, OPF Dublin Core, ffprobe streams.
- The mime schema's remaining **attestations** (§7.1): manifest/exposable embeds per the disposition, structural byte-marks, sidecar lift.
- The first **origin block** from capture context — `uri:` + `snapshot:`, or the uri-less local-file form (§7.2). A **SingleFile save** is a third shape: a manual save carries a self-describing banner comment in its first bytes (`Page saved with SingleFile` + `url:` + `saved date:`), so a save dropped straight into `capture/` and ingested (no capture step) seeds a *retrieval* origin from the banner — `uri:` = the banner URL, `snapshot:` = the saved date parsed to ISO-8601 with its numeric offset **preserved** (not converted to UTC; the parenthesized zone name ignored) — instead of the uri-less local-file form. An explicit capture-sidecar `source_url` still wins; a banner-less or non-HTML file is unchanged. The banner is scanned only within a bounded head.

No `content_type`, `hashes`, `classifications`, `tags`, or `uris`/`capture_dates` frontmatter — none of those exist in this model. The content zone holds attested byte-marks only (§4.3.2.3); the stored body is the normalize pass's (§12.5), and the derived body is readable immediately (`corpus body`, §6.2).

#### 12.3.5 Dedup, re-capture, and capture provenance

Ingest looks the artifact up by `id` against the existing corpus:

- **Match** — the bytes are already in the corpus. Fold the new capture into the existing record's origin blocks: append the inbound URL to a matching origin's `uri:` list when it aliases one (via known shortlink/redirect + `url_equivalent` rules), or emit a new origin block when it is a genuinely separate source (§5.2). Never a new record.
- **No match** — a new artifact. Write the record under `records/` and the binary under `artifacts/`.

Dedup is the natural side effect of content addressing. Two pre-download stages catch a duplicate *before* the (expensive, especially video) fetch: the cheap string-identity `find_by_uri` short-circuit, and the redirect-aware short-link resolution (§12.3.9).

Capture provenance lives in **origin blocks** (§4.3.1.2), never frontmatter: one block per distinct source, its `uri:` list collecting the spellings that resolve to it (request URL, final-after-redirect URL, shortlink, mirror), deduped by identity key (§12.3.9), plus the `snapshot:` timestamp. The pipeline does **not** record per-event metadata (which URI was used at which moment, the redirect chain, the HTTP method); recovering a particular (uri, time) capture package is a job for an out-of-band capture log, not the record.

#### 12.3.6 Browser capture recipes (per-host interactions and fidelity)

A web capture renders the page in a headless browser, drives it to surface all displayable media, then writes a self-contained SingleFile snapshot (CSS/fonts/images inlined as `data:` URIs). What the browser does before the snapshot is an ordered list of **interactions**, declared in the matching origin overlay's `capture.interactions:` (§7.2); absent a recipe, a conservative default of `scroll: full` → `expand: all` → `scroll: full` runs. Each step is a single-key mapping; steps are best-effort (a bad selector never aborts a capture):

- `scroll: full` — scroll top-to-bottom, hydrating lazy-loaded / below-the-fold media.
- `expand: all` (or `details`) — open `<details>` and click `[aria-expanded="false"]` accordions/tabs.
- `click: {selector, repeat, delay_ms}` — advance carousels / load-more buttons.
- `wait: {ms}` or `wait: {selector, timeout_ms}` — settle async loads.
- `hover: {selector}` — trigger hover-reveal media.
- `remove: ['#header', 'footer', '.ad']` — delete matching elements from the live DOM before the snapshot. **This is where page chrome is removed.** The HTML `body` derivation (§12.4.1) is deliberately mechanical and never guesses what is chrome, so stripping nav/header/footer/ads/cookie-notices is a per-host decision made here, where the site's real structure is known. Removing chrome at capture also keeps its images from being inlined and embedded. (Link-bearing navigation the crawl needs — breadcrumbs, related-item rails — is preserved by *not* listing it here.)
- `eval: "<javascript>"` — escape hatch for site-specific DOM surgery (fetch-and-inject an AJAX-on-click tab, promote a `data-*` high-res image URL into `src` so it gets inlined). An async-function string is awaited before the snapshot.

The snapshot's **fidelity** is a per-host tier (`capture.fidelity:` — `exact` | `balanced` | `lean`, default `balanced`; `FIDELITY_PRESETS` in `capture/__init__.py`). On asset-heavy SPAs the self-contained inlining (web/icon fonts in redundant formats, app icon-sprite SVGs) is re-inlined into every page, dwarfs the content, and defeats content-addressed dedup (each page's whole-file hash differs). `balanced` drops redundant font/image/media alternates (≈−76%, no rendering risk); `lean` also prunes unused CSS (≈−91%); `exact` keeps everything for presentation-critical sites. The tiers touch only the gitignored `artifacts/` — the mechanical body derivation reads DOM text/tables, so the record and its derived body are identical across tiers. The resolved tier is stamped into a `corpus-fidelity` meta tag; `corpus capture --fidelity` / `corpus crawl --fidelity` override per run.

Capture config (`capturer`, `transport`, `fidelity`, `interactions`, `viewport`) lives on the per-host origin overlay under its `capture:` section (§7.2); global defaults can sit on the universal `origin.yaml`. `scaffold.py`'s example overlay shows the full annotated shape.

#### 12.3.7 The video (yt-dlp) pathway

The **video capturer** drives yt-dlp. Its options are declared in `capture.ytdlp:` and merged straight into `YoutubeDL` (full passthrough — `format`, `getcomments`, `impersonate`, …); the library forces `outtmpl` / `logger` / the resolved cookie file after the merge so an overlay can't break output, logging, or auth. `capture.cookies_from_host` (default `true`) pulls the capture URL's own-origin cookies from a running CDP browser (`--remote-debugging-port=9222`) into yt-dlp, so a logged-in session unlocks a host's full content (e.g. the full format ladder rather than a degraded anonymous one). yt-dlp writes a `.info.json` enrichment sidecar (post metadata + comments); ingest renames it to `capture/<hash>.info.json` — it is ingest-time-only enrichment (the sidecar-lift attestation, §7.1), never persisted to `artifacts/`.

**Sidecar → origin block (ingest attestation), then deleted.** The `.info.json` is *non-primary-source* metadata, so the sidecar lift copies every declared key into the **origin block** as a flat `ytdlp_<key>` field (`ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts, …) via `records.merge_origin_fields` — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when returned) becomes a `ytdlp_comments` list field; `webpage_url`/`original_url` fold into the origin `uri:` aliases. The lifted key set is schema-declared — `sidecar.ytdlp_keys` on the video/audio mime schema (§7.1); the lift is mechanical, not hardcoded. One datum is *structural* rather than flat: **`chapters[]`** (the uploader's outline) is consumed into **structural segments** (producer-declared byte-marks, §4.3.2.3) — each chapter title an `entry:`, each bound a `time=` mark address. Chapters are consumed into marks, never copied to a `ytdlp_*` field; a mark's `entry`/address is structure, not body content, so this respects the same primary-artifact boundary. Transcription moves off the pathway entirely: it is the `transcribe` derivation op (§6.2), consumed at normalize.

**Title is normalizer-owned.** The frontmatter `title` (like `description`) stays empty through ingest; the normalizer authors it from the block-level candidates — the artifact block's bare `title`, or an origin `ytdlp_title` (the `ytdlp_` prefix survives because the origin opener names the source record, not the tool; §4.2.1). A media capture's title candidate routes to the origin's `ytdlp_title` (an A/V artifact block carries no `title`); for display, `records.title_for` reads the frontmatter `title`, falling back to the artifact `title`, then `ytdlp_title`. After a successful lift, ingest deletes the sidecar; enrichment is one-shot (re-capture to restore — the lifted fields already persist on the record).

**Per-host transcription (the `transcribe` op).** The op resolves the record's origin host and reads the overlay's `transcription:` section (§7.2): absent → the global `[corpus.transcription]` adapter; `enabled: false` → skip (an `info` issue, not a `warning`); `adapter`/`base_url` → a per-host backend that overrides the global even when the corpus default is `noop`.

#### 12.3.8 Pagination reconciliation

A paginated work — a thread / multi-page article / gallery a site splits across `?page=N` / `/page-N` URLs — is **one logical artifact**. The overlay's `capture.pagination` knob (§7.2; browser capturer only; `capture/pagination.py` + `_reconcile_pagination`) walks the pages and ingests a single merged record instead of capturing page 1 only or fragmenting the work into N content-addressed records. Both `corpus capture` and `corpus crawl` route through `capture_and_ingest`, so the branch lives there, after the dedup short-circuit:

1. **Walk + stage.** Each page is fetched through the staging-only `capture()` path (so its `url_rewrite` / `interactions` / chrome-strip / fidelity all apply per page), its HTML read into memory, and its staging file unlinked immediately — `_sanitize_filename` drops the query string, so `?page=N` pages would otherwise collide on one staging name, and per-page bytes must never be content-addressed. The next page is found by `<link/a rel=next>` (the `<link>` survives the chrome strip — it lives in `<head>`) or a `next.selector` override; the walk stops at no-next, a repeat URL, or `max_pages` (flagged).
2. **Merge.** Page 1 is the framework. The content region is the declared `content_selector`, else the host's `canonical.content_selector`, else a structural diff of page 1 vs page 2 (`detect_region`: descend while exactly one matched-identity child differs; the container whose children then diverge is the region). Each later page's content children are appended into page 1's region, **deduped by element id or a normalized-subtree hash** (so a repeated quoted-OP / threaded post isn't double-counted); a page adding zero new children stops the walk.
3. **Ingest once.** The merged HTML is written to one staging file and ingested — the sole content-addressed artifact + record. A single page (no next link) skips the round-trip and ingests the original snapshot bytes verbatim, so its id is byte-identical to a non-paginated capture (and no pagination provenance is attached).
4. **Provenance.** The clean seed is the recorded origin URI; every constituent page URL — both the bare site form (what a crawl discovers) and the pinned `url_rewrite` form — is folded in via `records.add_origin_uri_alias`, plus a `pagination: {pages, form, posts}` field via `records.merge_origin_fields` (`posts` is the id-aware item count — `_count_items` counts id-bearing region children when any are present, so framework `div`s inside the region don't inflate it; else all children). When the merged count falls short of an advertised `expect_count.selector` value, or `max_pages` was hit, a `pagination-incomplete` `warning` issue (capture-stage detector `corpus.capture`) is emitted rather than silently shipping a lossy record.

**Crawl interaction.** Recording every constituent URL as an alias makes the dedup short-circuit fire when a crawl later discovers `/page-N`, resolving to the merged record instead of re-capturing. `crawl._expand` additionally drops any link already in the expanding record's own origin URIs, keeping those pages out of the frontier (genuine content links — post permalinks, cross-thread — are kept).

#### 12.3.9 URL equivalence and redirect-aware short-link dedup

A record's origin URI list should hold **one URI per distinct resource**, and an inbound URL should match a record whenever it denotes the same resource, even when the spelling differs (query noise, `/page-1` ≡ bare). The per-host `capture.url_equivalent` overlay section (§7.2) declares this; the tooling reduces every URL to an **identity key** and compares keys instead of normalized strings.

- **The primitive** is `urls.identity_key(url, equivalent, *, url_rewrite)` (pure, stdlib-only). `urls.normalize_equivalence` coerces the overlay value to a canonical config; the key is `normalize` → (if `on_rewritten`) apply `url_rewrite` first → (if `query: drop`) strip the query → apply the `rules` in order (via the shared `urls.apply_rewrite_rules`) → tidy a dangling delimiter → fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`). With no config it returns exactly `normalize(url)`, so the layer is inert (opt-in) for any host that does not declare it. The trailing-slash fold is in `identity_key`, **not** `normalize`, on purpose: `normalize`'s output is the URL `crawl._expand` stores and re-fetches (a server may distinguish `/a/b` from `/a/b/`), so the fetched form keeps its slash while the comparison key folds it.
- **Identity ≠ fetch.** The identity key is a comparison key only. Crawl still stores the fetchable normalized URL in its frontier/visited; only the dedup *comparison* uses identity keys. Equivalence must never decide which bytes are fetched (that is `url_rewrite` / `interactions`).
- **The recipe-aware wrapper** `recipes.identity_key_for_url(corpus_root, url)` resolves the host's `capture` recipe once and passes its `url_equivalent` + `url_rewrite` to `identity_key`; single-URL sites (`records.find_by_uri`) call it directly, while bulk sites (`records.build_uri_index`, `crawl._expand`) memoize the recipe by host.
- **The four identity sites** all key by `identity_key`: `build_uri_index`/`find_by_uri` (capture short-circuit + raw-URL resolve), `crawl._expand` (frontier dedup, folding in the own-URI exclusion), `_reconcile_pagination` (within-walk seen-set + constituent-alias recording), and `records.add_origin_uri_alias(post, alias, *, corpus_root=)` — which, given `corpus_root`, skips an alias whose identity key matches an existing origin URI, keeping origin blocks minimal. Where a host declares the page-form equivalence, it supersedes pagination's bare+pinned dual-alias recording — a fragment-only pin (`#flat`) collapses to the bare form, while a genuinely path-changing `url_rewrite` still records both.

`identity_key` canonicalizes a URL *string* and never touches the network, so an **opaque short link** (`https://vt.tiktok.com/XXXX/`) keys differently from the canonical it 301s to. The redirect-resolution layer closes that gap by following the redirect chain to the final URL **without downloading the artifact**:

- **The primitive** is `redirects.resolve_final_url(url)` (pure stdlib): a per-hop HEAD (falling back to a body-less GET on 405/501) follows `Location` headers up to `MAX_HOPS`, never reading a response body — so even when the final URL serves a multi-megabyte video, the probe stays cheap. Redirect loops, hop-cap, non-web `Location`s, and any network/parse failure all return the input unchanged: a probe never breaks the caller, it only improves dedup when it succeeds. `redirects.is_probably_short_link(url)` is a conservative gate (known shortener hosts, `vt.`/`vm.` subdomains, or a single short opaque path segment) so a normal canonical URL never pays the network round-trip.
- **The recipe-aware wrapper** `recipes.resolve_identity_for_url(corpus_root, url)` returns `(final_url, identity_key)`: it follows redirects only when the URL looks like a short link, then computes the identity key from the **final** URL — so the destination host's `url_equivalent` strips the volatile query the canonical resolves with, and a short link whose apex differs from its destination (`youtu.be` → `youtube.com`) picks up the destination's equivalence rules.
- **Capture short-circuit (second stage).** `capture_and_ingest` keeps the cheap string-identity `find_by_uri` first; on a miss, `_redirect_dedup` runs the redirect-aware resolution and re-checks — catching a fresh short link to an already-captured canonical **before** the download, and folding the short link into the matched record's origin URI list as an alias. `--force` skips both stages, and the short-link heuristic keeps the probe off the hot path.
- **`corpus check <url>`** (`_cli/check.py`) is the read-only surface: the same resolution (canonicalize + overlay recipe + redirect-follow), then `find_by_uri`, reporting the matching record hash + path or "not captured". It never captures, ingests, downloads, or writes. Script contract: exit `0` already captured, `1` not captured, `2` usage error, `3` resolution error; `--json` emits `{url, resolved_url, identity_key, redirected, captured, record, path}`; `--no-follow-redirects` does a string-identity-only check (offline / fast).

#### 12.3.10 Dependent references (`capture.references`)

A page's most relevant outbound links are part of the capture itself — a product-detail page's manual or spec sheet far more than the other hundred links on the page. The per-host `capture.references` overlay section (§7.2) declares which links those are; the tooling emits a `reference` context block (§4.3.3.3) for each and, opt-in, fetches it depth-1 as its own record. The home is one module, `corpus.references` — *declare, match, emit* — with the *fetch* delegating to the existing capture/crawl machinery. Opt-in throughout: no rules → entirely inert.

- **The rules** (`references.parse_rules` → `ReferenceRule`): a list of `{match, role, capture, cross_host}`. A rule's `match` keys (`selector` CSS, `href_pattern`/`text_pattern` regex on the resolved href / anchor text, `rel` token) are ANDed; rules are ORed. `role` (corpus-local label — `manual`, `spec-sheet`) rides onto the emitted reference; `capture: true` opts the target into the depth-1 grab (default false = annotate only); `cross_host: allow` (the default — manuals are off-host) lets a match reach another host, `same` host-restricts it. Parse-tolerant: a non-mapping entry, a rule with no match key, or a bad `cross_host` is skipped, never fatal.
- **Matching** (`references.match` / `matches_for_record`): parse the DOM, scope candidate anchors by `selector` (else all `<a href>`), apply the AND filters, resolve relatives against the base URL, normalize, drop non-crawlable hrefs (`urls.is_crawlable_href` — the same filter `links`/`crawl` use), enforce `cross_host: same`, and dedupe by URL (DOM order, first rule wins for role/capture). `matches_for_record` applies the host's rules against the record's primary origin URI and excludes self-links. Shared by the overlay emission, `corpus links --references`, and the grab.
- **Emission rides the attestation pass** (`references.emit_overlay_references`; §8.1 — record-scoped, so it attests at ingest). Each match emits one `<!--context reference-->` with `provenance: auto`, the rule's `role`, tier-1 `attribution_text` (the link text), and tier-2 `source_url` (the resolved href). It stops at tier 2: the mechanical emission writes **no** tier-3 `source_uri` and reads **no** corpus state, keeping it a pure function of the artifact (§4.3.3.3). Whether `source_url` is itself a record is a read-time derived edge: `derived_views.references` (§9.9) resolves it against the URI index and surfaces `captured`/`resolved_uri`, so the edge self-heals (`captured ⇄ pending`) under capture/removal/supersession. Idempotent for free: `auto` blocks are stripped + regenerated by re-attest (§4.4.6), so emission never duplicates. **Known gap:** emission is HTML-only and *record-scoped* in the current implementation — no segment anchor is written, because the declared link usually sits in un-segmented chrome and a brittle DOM→segment map would mis-pin it. §4.3.3.3 specifies a segment-pinned anchor (`address:`/`quote:`); closing this gap is an open item (§12.15).
- **The depth-1 grab** (`references.fetch_references`): `select_for_capture(matches, force=)` picks targets — `force=True` (`--with-references`) all, `force=False` (`--no-references`) none, `force=None` (default) the rules' own `capture: true`. Each selected, not-already-captured target is fetched once via `capture_and_ingest` — depth is fixed at 1 (a grabbed target is ingested as its own record, never expanded; multi-hop stays `crawl`'s job, §11). Best-effort: a per-target failure is recorded, not raised. Surfaces: `corpus capture --with-references` / `--no-references` (the inline grab after the primary ingest), `corpus crawl --references [seed]` (the deferred sweep; `--dry-run` lists pending targets).
- **Discovery + view.** `corpus links --references <record>` previews the declared subset, each line annotated `[role=…, captured|pending, auto?]`. The `references` derived view (§9.9) is the `reference`-namespace projection; the reverse edge (which records reference *this* one) is a corpus-wide read, not indexed (§9.9 / §11).

#### 12.3.11 Pre-ingest bundle assembly (`corpus assemble`, 2.1)

Some sources deliver an export as one or more **transient part archives** — an expiring download job, a solid compressed stream with no member index (a tgz) — where the delivered envelope is worthless to preserve and hostile to containment resolution; others deliver **no envelope at all** — an export tool (DiscordChatExporter) that writes a loose directory tree straight to disk. `corpus assemble --origin <overlay-id> <part…> [--add <file>]…` repackages such a delivery (a part is a tar/tgz/zip archive or a directory tree) into ONE indexed bundle **before** ordinary ingest, driven entirely by the overlay's `capture.assembly` config (§7.2): union the parts' member trees (`merge_parts`, `conflict: error` on divergent same-path bytes), drop declared-cruft members (`excludes` — reported, never silent), place declared `additions` at the bundle root (the original tree is never touched; any restructure exists only as an asserted `rewrites` rule), derive origin fields mechanically (`derive` patterns over the source filename convention, addition contents, and directory-member head bytes; CLI flags override), and write the bundle plus its capture sidecar (`origin_schema:` + fields, §12.3) into `capture/` staging. A directory source's member relpaths come verbatim from its tree root and member mtimes from disk; having no envelope it leaves no `source_parts` tombstone — its assertion of byte identity is the per-member blake3 the manifest records. The engine is two layers: a **reusable deterministic bundle writer** (sorted members, verbatim paths, source mtimes, per-member zstd with `stored` for already-compressed types, archive comment stamped with the job identity, streaming, atomic; same inputs → same bytes) — shared with the planned `pack` verb (§12.8), which feeds it existing corpus artifacts instead of extracted part members — and the overlay-driven assemble frontend. The consumed parts are recorded as `source_parts` tombstones (`<filename> blake3:<hash>`) on the bundle's origin block, and are retired via `rm` only after the bundle's members verify container-resolvable. Assembly is the one deliberate exception to parse-tolerance: an unreadable source member aborts with no partial bundle — a bundle is complete or absent. Member byte-identity is untouched by re-packaging (§2), so records promoted from a part archive survive an assemble→retire cycle with zero edits — residence just moves.

#### 12.3.12 From-save capture (manual SingleFile saves)

A manual SingleFile save — a page a human saved from their own browser session — is often the *only* faithful record obtainable: content behind a login the tooling can't replay, a page since changed or removed, a session-specific view. **From-save capture** makes such a save a first-class capture: `corpus capture <path>` (the argument resolves to an existing local file rather than a URL) replays the saved DOM through the same browser pipeline live capture uses, so the host overlay's `capture.interactions` (§12.3.6) apply identically to both. The save is not merely ingested — it is re-rendered so the per-host chrome strip and media surfacing run against it.

- **Provenance is the banner.** The save's SingleFile banner (§12.3.4) supplies the origin URL (used to look up the host recipe) and the saved date. Absent a banner, a `<file>.capture.yaml` sidecar's `source_url` / `fetched_at` is the fallback; with neither, from-save refuses with a clear error — it cannot record a capture whose source URL is unknown.
- **The save is the honest state — nothing is fetched live.** The file loads via `file://` in a headless browser with CSP bypassed (a save may carry a CSP `<meta>`) and **every http/https request aborted**. A SingleFile save has already inlined every asset as a `data:` URI, so the saved bytes are self-contained; the abort guarantees a dead-script DOM can never reach the network to backfill what the human's save did not capture. The overlay's `capture.interactions` still run (`DEFAULT_STEPS` when the recipe declares none) and remain best-effort — a click / lazy-load step that depended on live scripts degrades to a no-op, while `remove` / `expand` / `eval` DOM surgery applies as in live capture.
- **The snapshot is stamped to the saved date.** The re-snapshot injects the same `corpus-*` metas live capture does, but with `corpus-capture-url` = the banner URL and `corpus-fetched-at` = the saved date, and ingest seeds the record's first origin with `snapshot:` = the saved date — the fetch happened when the human saved the page, not when it was re-snapshotted. Fidelity, viewport, and interactions resolve from the overlay exactly as for live capture.
- **The source is retained.** From-save never unlinks the source file — a manual save can be irreplaceable — consuming only the re-snapshot staging file at ingest. The already-captured short-circuit (§12.3.5) and `--force` behave as for a URL capture, keyed on the resolved banner URL.

#### 12.3.13 Mailbox window reduction (`corpus mbox-window`) *(3.3)*

A provider that exports **the whole mailbox every time** (Google Takeout's All-Mail mbox) makes each successive snapshot near-total re-delivery of bytes the corpus already holds; persisting every snapshot re-persists gigabytes for kilobytes of news. **Window reduction** is the pre-ingest answer, the mailbox sibling of §12.3.11: `corpus mbox-window <source.mbox> --against <record>…` streams the transient full export and writes into `capture/` staging a **window bundle** — a valid mboxrd holding ONLY the members not already persisted in the named lineage — plus its capture sidecar; the full export is then discarded, never ingested (its identity survives on the bundle's origin fields, tombstone-style, the `source_parts` idea on the mailbox axis). Mechanics:

- **Dedup keys on member identity, never position.** "Already persisted" is decided per member by the un-stuffed member blake3 (§12.11 — the promotable identity, §8.1); ordinals scatter across exports and mean nothing. The exclusion set is **derived at run time, never stored**: the union of (i) a full streaming enumeration of each lineage record's artifact bytes where locally present, (ii) each lineage record's declared `msg=` embed transports — the fallback when the bytes are remote or retired, warned, since a selectively-declared mailbox declares a subset — and (iii) every standalone `message/rfc822` record id in the corpus (a promoted or independently-ingested message is a persisted member wherever it now lives).
- **The lineage is transitive.** Each `--against` expands through the named record's own `window_against` origin field, so naming only the latest window reaches the whole chain back to its baseline snapshot. A deliberate re-baseline (a new full snapshot ingested whole) starts a fresh lineage.
- **Members copy raw.** A selected member is copied verbatim — separator line plus stuffed bytes — in source order, so the bundle is a valid mboxrd whose members carry byte-for-byte the identities the source held (§2). Within-source duplicate members (the same blake3 twice) fold to one copy, counted. An unreadable source aborts with no partial bundle (the §12.3.11 exception to parse-tolerance); an empty delta emits nothing and says so.
- **Provenance rides the sidecar** (`origin_schema:` + `origin_fields:`, §7.2, overlay id supplied by `--origin` exactly as `assemble` takes it, or auto-stamped from the `default_origin` binding when the flag is absent — below): the source export's identity (`source_export`, `source_modified`, `source_message_count` — the staged bundle keeps its own `filename`), the window bounds derived from the selected members' Date headers (`window_start` / `window_end`), the counts (`window_count`, `excluded_count`, `duplicate_count`), and **`window_against`** — the lineage record ids as **plain hashes, deliberately not `corpus://` refs**: they record what was subtracted at build time (process provenance), not a resolution route — no member resolves through the lineage — so a later-retired lineage record must not raise `dangling_origin_refs` (§12.8).
- **Full declaration is the window convention.** Post-ingest, `corpus reattest <id> --messages 1-<N>` declares every member — affordable precisely because the bundle is thin — so the manifest doubles as the window's **human delta index** (per-member date / from / subject) and as the **machine dedup-set** the next window subtracts without re-scanning artifact bytes: a fully-declared window's embed set IS its member set.
- **Year-split for full snapshots (the re-baseline shape).** A full snapshot need not persist as one monolith: `corpus mbox-split <export>` partitions the canonicalized members by Date-header year into per-year mboxes — **closed years only** (strictly before the current year; a member with an unparseable Date is never falsely closed, it stays with the current residue) — and assembles them into ONE deterministic zip container staged for ordinary ingest: a `zip-manifest` record whose `<YYYY>.mbox` members are each **promotable** (§8.1) to a first-class mbox record whose bytes stay in the container. The current year's members emit as a residue mbox handed to the window flow, never to the container. The payoff compounds with the chrome strip: a closed year's stripped mbox is **byte-identical in every future full export**, so the next re-baseline's year members re-encounter (origin append, zero new mints — §12.3.5) and only the newly-closed year mints; a full snapshot's marginal cost converges to one year plus the hot end. The container sidecar carries the source export's identity + transport, the strip disclosure, the per-year member counts, and the excluded current-year/undated counts.
- **Provider-metadata headers strip at capture — the mailbox chrome strip.** A provider that mutates per-message metadata *inside* the exported bytes (Gmail's `X-Gmail-Labels`: read state, categories, importance, user labels — measured as the COMPLETE churn set between two real exports: member identity modulo that one header was 99.1% stable, every residual an arrival or purge) makes member identity hostage to workflow state. The remedy is the HTML chrome-strip precedent (§12.3.6) on the mail axis: a **declared header list** is removed from every member's header zone (folded continuations included; body lines never touched) **before identity** — the stripped bytes are the stored bytes, blake3 over them the one identity, exactly as a chrome-stripped DOM is the stored page. Declarative list only, no eval hook — mail surgery must be reviewable. **The declaration is still schema config, never a verb — but the declaring grain is the origin overlay, not the mime schema.** Label chrome is producer knowledge, so `strip_headers` lives on the *producer's* overlay (§7.2) — e.g. `google-takeout/gmail` — exactly as a host's chrome-strip interactions live on `origin/web/<host>` overlays (§12.3.6); the packaged distribution ships no strip values on any grain. The `application/mbox` mime schema (§7.1) carries no `strip_headers` of its own — it supplies the **interaction point** only: it documents the strip hook, and it carries the one corpus-local **binding**, `default_origin: <overlay-id>` — "an unattributed mbox entering this corpus is presumed produced by this origin" — which is what keeps canonicalization unconditional at identity-mint time even when no sidecar stamps an origin. Resolution precedence, most-specific first, in the fingerprint-knob shape (§7.7): (1) the CLI `mbox-window --strip` override; (2) absent that, the **stamped** origin's namespace walk — ingest reads the sidecar's `origin_schema` (§7.2) before hashing; (3) absent a stamped origin, the `default_origin` binding's namespace walk; (4) absent both, off. The **namespace walk** tries the overlay id itself, then each id-prefix ancestor (`a/b/c` → `a/b` → `a`); the first overlay that DECLARES `strip_headers` is final — an explicit empty list is itself a declaration, meaning "no strip." The walk never crosses namespaces: a stamped origin whose walk finds no declaration leaves the strip OFF outright — falling through to another producer's chrome list would be a category error, so the `default_origin` binding is consulted only when nothing is stamped at all. **Auto-stamp** closes the loop: `mbox-split` and `mbox-window`, run with no `--origin`, stamp their emitted sidecar's `origin_schema` from the `default_origin` binding (disclosed in their output) — attribution is config-automatic by the same principle as the strip. Ingest itself never invents origin attribution; the binding drives canonicalization alone, and attribution enters only via a sidecar. And **ingest applies the resolved strip automatically** when a standalone mbox stages, so the invariant can never depend on an operator remembering a pre-processing command. This is the one deliberate amendment to ingest's hash-what-staged contract: canonicalize-then-hash where declared, with the delivered bytes' blake3 preserved as `source_transport` on the origin block (`stripped_headers` + the member count beside it) so the pre-strip identity is disclosed, never silently lost. An already-canonical file (a window bundle emitted stripped; a re-drop of stripped bytes) passes through untouched. `corpus mbox-window` resolves the SAME config for its source, its emission, AND its lineage artifact enumeration — so a pre-strip (label-full) snapshot still serves as lineage across the strip boundary, its members hashed as-if-stripped at scan time. Two caveats: the declared-embed fallback carries pre-strip hashes and cannot cross the boundary — lineage older than the strip needs its artifact bytes present (warned, never silent) — and the strip applies only where a mailbox enters standalone: members inside an ingested container must stay byte-identical to their container route (§2), so a mail export's mailbox is extracted and staged, never ingested-as-zip.

### 12.4 Attest & derive (the draft stage's successor)

*(3.0)* The 2.x draft stage's per-format drafters split into **attestations** (ingest-time byte-facts) and **derivation ops** (resolver-side content extraction); the body each drafter wrote is now the `body` op's output, stored only when the normalize pass authors it. A classification is never a frontmatter array and carries no justification field — the `classifications` list is a derived view (§9.1) — and records carry no `tags` field.

#### 12.4.1 The per-format split

The per-format inventory, restated as the split (each 2.x drafter's mechanics carry over to whichever side of the split owns them):

| 2.x drafter | Disposition | 3.0 attestations (ingest) | 3.0 derivation ops (§6.2) |
|---|---|---|---|
| HTML | work | inline `data:`-asset embeds (hash, type, `el=` address) | `body` (DOM→markdown, overlay chrome config), `el=` |
| PDF | work | `/Info` fields; **exposable embeds** for embedded files / portfolio members (`attachment=<N>`) | `body` (page markers), `page=` + introspection ops, `attachment=` |
| EPUB | work | Dublin Core fields; image-member embeds | `body` (spine text), `spine=`/`el=` |
| OOXML (docx/xlsx) | work | document facts; **exposable embeds** (embedded media, OLE objects) | `body` (document text / sheets), `sheet=`/`bbox=` |
| zip/tar (+ zip-shaped types) | manifest | member embeds (`path=`), archive facts | `members`, `path=` |
| mbox | manifest | declared-message embeds (`msg=`, **selective declaration** — below; §12.11 pins the extraction) | `msg=` |
| multi-card VCF | manifest | card embeds (`card=<N>`, delimiter-pinned — the mbox precedent on the contact axis; each member `text/vcard`, promotable) | `members`, `card=` |
| ICS calendar | manifest | entry embeds (`entry=<N>`, `VEVENT`-delimited, promotable) | `members`, `entry=` |
| eml | work | header lift; part embeds (`part=`) | `body` (reply-text trim), `part=` |
| JSON | work | shape facts (`json_root`, `json_top_count`); `malformed-json` issue | `body` (verbatim passthrough), `turn=`/`att=` where a form mapping declares units |
| audio / video containers | manifest | container/stream facts; **track embeds (`stream_id=`) + chapter marks** (§1.2) | `transcribe`, `time_range=`, `frame=`, `stream_id=` (default-member sugar, §6.2) |
| HEIF/HEIC | manifest | image-item embeds (`item=<id>`); the declared primary (`pitm`) attested | `item=`, image ops via default-member resolution |
| image (single-stream) | work | dimensions/EXIF; a motion photo's nested MP4 as an embedded transport (§1.2) | `bbox=` and the image toolkit |
| markdown / plain | work | — | `body` (passthrough) |
| unknown | work | best-effort facts only | — |

Formats that arrive later slot into existing strategies, not new machinery: 7z/rar/dmg join the zip-manifest strategy; PST/OST joins the mbox precedent; WARC likewise (§1.2).

**Mechanics that survive the split, restated on their owners** *(3.0 — the 2.x drafter prose retired; these behaviors, which 10,000+ records conform to, did not)*:

- **Selective mailbox declaration** (mbox attestation). A mailbox may hold 10⁵ messages, so message embeds are declared **selectively**: the ingest/re-attest surface accepts named 1-indexed ordinals (the 2.x `--messages 5,12,90-95` surface, re-homed — §12.18 open question 10), each recorded as a `message/rfc822` embed at `msg=<N>` (blake3 over the un-stuffed member bytes, plus the message's Date / From / Subject and byte length). Declaration is **cumulative and idempotent**: a re-declaration unions the newly-named ordinals with the already-declared set, an identical re-declaration folds, and a changed hash for a declared ordinal is a **hard error**. An undeclared run attests the mailbox summary only (message count, byte size, date span), no embeds.
- **The eml reply-text trim** (the `body` op for `message/rfc822`). The derived body is the **reply text only** — the `text/plain` part, else `text/html` reduced to text — with trailing quoted history trimmed from the first confidently-matched marker (an `On … wrote:` attribution directly above a `>`-quoted line, `-----Original Message-----`, an Outlook header block or underscore rule, or a `>`-run to EOF), keeping everything when no marker matches (**prefer false negatives**) and keeping signatures. Part embeds skip the text alternatives the body consumed.
- **HTML addressability** (the `el=` selector). `el=<N>` indexes the page's addressable elements, 1-indexed — content blocks plus the inline-media carriers (`<img>`, `<video>`, `<audio>`, `<a href="data:…">`) — and what an address materializes is determined by the element (§6.2). The addressable-element definition is op-owned, unchanged from 2.x; shapers and the resolver share one implementation (§12.4.3).
- **Manifest lint conventions.** An empty archive attests a blocking `partial-content` issue. `embed-unreferenced` is relaxed for `manifest`-disposition records (the embeds ARE the content) and for `message/rfc822` records (parts are message *members*, not body-flow assets — the normalizer links an inline image into the body where it belongs).

#### 12.4.2 One construction path (the constituent model)

`recordbuild.Build` remains the one construction path — `add_blocks` → `open_section`/`add_segment` (which enforce body⟺lossless per segment) — and `recordbuild.finish` emits + grammar-validates it. These are the same ops `compile` replays from a decomposed `manifest.corpus`, so attest / re-attest / decompose / compile / normalize all construct records identically: shapers and agent passes construct the authored layer through it, and a shaped record decomposes then recompiles byte-for-byte. This is the substrate the LLM normalizer works on: it edits the decomposed **constituent files** (per-segment body / description sidecars + the ops manifest) and recompiles deterministically — never rewriting a monolithic markdown blob — which makes whole classes of structural corruption unrepresentable. (`begin_from_post` seeds the Build for re-attest; `begin` seeds it from a `meta.yaml` for compile.)

#### 12.4.3 Corpus-local shapers

A corpus can specialize the shaping of its *own* content without editing the package — **corpus-local shapers**, the successor of the 2.x corpus-local drafters (the iMessage sub-drafter foremost), same trust boundary, same registration pattern. `<corpus_root>/shapers/*.py` load via the same `local_code` loader (§12.3.1); a module claims records by origin or form id — a producer-declared `corpus-origin-schema` meta or a stamped origin-block id (§7.2) — and builds the authored content zone in place of (or ahead of) the generic mapping-driven shaper and the interpretive agent. A shaper constructs through `recordbuild` and reuses the public address/embed helpers (`compute_embed_metadata`, `transforms.html.is_addressable`), so its addresses and embed transports line up with the resolver by construction. The record envelope (title, origin fields) stays the generic path's; only the authored content zone is delegated. Format-specific shapers, atoms, and overlays for private content live in the owning corpus repo, never in the package.

#### 12.4.4 Perceptual fingerprinting (opt-in)

Fingerprints attest at ingest where the knob resolves on (§7.7). A segment gets a `perceptual:` only when `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override)` resolves on — precedence CLI (the ingest/re-attest `--fingerprint` / `--no-fingerprint` override) › origin overlay › mime-schema `fingerprint` knob › off (the default; §7.7). The resolved knob (`true` = the atom's default algorithm, an algorithm name, or a list) becomes concrete per-atom algorithms via `fingerprint.algos_for_atom(atom, knob)`, computed by `fingerprint.text_fingerprints` / `image_fingerprints` (a registry keyed by algorithm, mirroring `content_hash._STRATEGIES`). Algorithm selection is schema-only; the CLI flag is on/off.

#### 12.4.5 Deterministic auto-classification *(removed in 2.0)*

*Retired with the composite namespace (§7.4).* The `classify_when` engine, `corpus classify`, `corpus reclassify`, and lint's `classification-stale` all retire; deterministic membership is now a ledger **harvest rule** over the same fact base (`ledger.md` §10), evaluated ledger-side (`ath ledger harvest`) as a pure function of the corpus's mechanical record facts — so `draft` no longer carries any classification hook at all.

#### 12.4.6 Bulk re-attest (`corpus reattest`)

The attested layer is a deterministic function of (retained artifact + schemas + tooling), and `id = blake3(artifact)` is unchanged by re-derivation — so regenerating it is an in-place `.md` rewrite, and `git diff records/` surfaces exactly which records a schema / overlay / tooling change affected. **`corpus reattest`** `[target] [--mime/--host/--state] [--dry-run] [--fingerprint]` sweeps the attested layer (§8.3) across the corpus — an unchanged record re-derives byte-for-byte and is not rewritten (idempotent; `--dry-run` reports the set, writing nothing). *(3.1: the 3.0 `--status` selector re-keys to the derived-state predicates of §4.1 — e.g. formless-only; concrete flag names are tooling-time detail.)* Unlike the 2.x `corpus redraft` it succeeds, re-attest never touches the authored layer (§4.4.7), so it needs no authored-refusal guard; authored-layer sweeps are **re-normalize** dispatches through the queue (§8.5). The **`corpus draft` verb retires**. Distinct from `corpus compile`, which reassembles a record from a decomposed *manifest* (§12.4.2) rather than from the source *artifact* — different inputs, different jobs. (`records.dumps` serializes a record to canonical text without writing, so reattest can compare against disk.)

Pipeline-state provenance is the `touch[]` chain (§4.2.2): each pass appends a `<pkg>.<module>@<version>` (or `<model-id>`) identifier, so the latest touch's tooling version encodes the spec era of the record's current shape and re-run targeting reads it. There is no separate `conversion_method` / `conversion_tool` field.

#### 12.4.7 Cross-reference resolution

Cross-reference reconciliation is a read-time/sweep concern. Once a stored body exists (normalize, §12.5), scan segment bodies for **hyperlinks** (`<a href>` → other resources) — *not* same-transport inline media, which is already an embed + segment (§12.4.1). For each hyperlink:

1. Map the URL → `id` by querying the corpus's URI index (`records.build_uri_index` — every record's origin `uri:` list keyed by identity, §12.3.9).
2. If matched, rewrite as a raw intra-corpus wikilink `[[<id>|original link text]]` — no URI scheme prefix; these are layer-local cross-artifact references (§4.3.2.2 / §5.1).
3. If unmatched, leave the plain markdown URL. The target is outside the corpus and may resolve on a later re-resolution pass once it is captured.

This is purely mechanical: the pipeline does not invent links the original content didn't contain. A lightweight sweep re-runs just this pass against existing bodies — useful after a batch of captures resolves URLs left as plain markdown in older records.

**Reconciliation tooling.** The on-demand counterpart ships as `corpus links` (per-record) and `corpus crawl` (frontier BFS): both extract a record's `<a href>`, resolve relatives against its origin URI, normalize, and look each up in the URI index. A hit means the reference is already captured; a miss is the crawl frontier. `corpus links --show-captured` annotates which is which. Link extraction filters hrefs through `urls.is_crawlable_href`, which keeps client-side routing fragments (`#/route`, `#!/route` — on a hash-routed SPA the fragment *is* the resource identity) while dropping bare anchors (`#section`) and the `javascript:`/`mailto:`/`tel:` schemes.

### 12.5 Normalize

Normalization is the **one authoring pass** (§8.1): it renders a record under its named form contract, the span's editorial header fields riding with it (§4.2.3). It is executed by a **shaper** (deterministic tooling registered per form or manifest strategy — the successor of the 2.x draft strategies) wherever the record's declared form mapping makes the shape mechanical, and by an interpretive agent session (through the queue, §8.5) wherever judgment is required; most records are a composition — the shaper writes the form, the agent authors what only judgment can (the editorial header fields, descriptions, faithfulness issues). The agent works over the same derivation ops any reader uses (`corpus body`, the introspection ops, `transcribe`) — nothing it consumes is privileged or unreproducible.

#### 12.5.0 Shapers

A **shaper** is deterministic normalize tooling: it reads the origin overlay's `form:` mapping (§7.2) and the form overlay's decomposition contract (§7.8), consumes derivation ops, and emits the authored content zone through `recordbuild` (§12.4.2) — the form section with its codebook, envelope segments (`turn=` addresses, codebook indexes, timestamps in the form's convention), event segments, attachment markers, structural byte-marks. Its touch is `<pkg>.shape.<form-id>@<v>`; a combined pass appends `+<model-id>` when the agent's editorial work rides the same pass. Shapers live in the package (generic, mapping-driven) or corpus-local under `shapers/` (§12.4.3). A shaper failure on a malformed unit is parse-tolerant per the standing principle — log, mark with an issue, continue.

#### 12.5.1 The interpretive pass

The normalizer authors the record's stored faithful form — faithful-form work only:

- Authors the stored content zone from the derived body and the introspection ops (where a shaper hasn't already written the form), improving formatting fidelity (broken tables, malformed lists) and resolving encoding ambiguity where determinable. *(3.1)* A stored rendering rides a named form (§4.1): the interpretive pass authors a content zone only under the record's declared form or one it asserts through §4.4.6's gate. *(3.2)* On a record staying formless the pass authors no record-scope editorial prose — the derived title/description already stand (§4.2.3); its remaining licensed work is the scope-specific kind below.
- Writes asset descriptions on embeds and on self-slice / non-lossless segments via `description:` (lossy interpretation — never in a faithful segment body); fills embed `alt` only when the source provides it.
- Surfaces problems as `<!--context issue/<id>-->` blocks in the annotations zone.
- Authors the form span's editorial header fields — `title:`/`description:` on the section opener (§4.2.3, the vouch's home) — where the derived candidates beneath don't already say it.
- Re-segments where judged appropriate (structural only).

The pass MUST preserve faithfulness (§1.5 principle 3): no information that wasn't in the source; descriptive content lives on `description:` / `alt`, never in a segment body.

#### 12.5.2 Self-verification

Before finalizing the pass, the normalizer confirms:

- The artifact-block opener MIME matches the actual MIME of the stored binary (the opener is authoritative, §12.3.2).
- The `id` (blake3) matches the binary's hash.
- The on-disk record path matches the shard convention.
- `corpus lint` is clean at the pass gate's severity (§8.5) — lint is the executable encoding of the spec's required-field and grammar rules.

Failures here are pipeline bugs; they should fail loudly.

#### 12.5.3 Annotations in practice

A context block stores as `{namespace, id, subtype, fields}` in `post.metadata["_contexts"]`. The bundled namespaces are `issue` and `reference` (§4.3.3); a corpus may add its own under `schema/context/<ns>/` (`relation` overlays are corpus-local, per §4.3.3.5). Context is scarce by design (§4.3.3), and there is deliberately no bundled free-text `note` namespace — that would invite scratchpad flooding. The `aside` namespace named in §4.3.3 has no bundled overlay yet; it is deferred.

- **Issue loading and parse tolerance.** `schemas.load_context_schema(corpus_root, "<ns>/<id>")` layers `context/<ns>/<ns>.yaml` → `context/<ns>/<id>.yaml`. `records.iter_issue_blocks` / `append_issue_block` are shims over `_contexts` filtered to the `issue` namespace, so pipeline detectors, `health.unresolved_issues`, the §9.2 view, and lint's issue rules share one path. The reader is parse-tolerant: a legacy `<!--issue <id>-->` still loads (as the `issue` namespace) and upgrades to `<!--context issue/<id>-->` on the next write.
- **Reference lint.** `context-namespace-unknown` flags a block whose namespace has no `context/<ns>` overlay. *(The 1.0 `reference-unresolved` lint retired with the stored tier-3 `source_uri`, §4.4.5.)*
- **Decompose/compile conventions.** The manifest keeps a dedicated `issue <id> sev= res= detector=` line for the issue namespace and a generic `context <ns>/<id> k=v…` line for the others (`recordbuild.add_context`). Two conventions keep the working dir hand-editable: record-level manifest facts are authored only on the manifest `record …` line (not duplicated in `meta.yaml`, where an edit would be a silent no-op) — *(3.1: the line's `status=` key retires with the field; until the tooling sweep it round-trips inertly)* — and `meta.yaml` renders a multi-line string as a YAML block literal (`|`) so a multi-line `description` never reads as a truncated stump. An address list in the manifest is bracketed and `|`-separated (`[a|b|…]`), not comma-separated — a single address (e.g. `bbox=x,y,w,h`) already contains commas.

#### 12.5.4 Normalizer-support commands

The LLM normalizer never reads `schema/*.yaml` directly; it works through read-only commands (`_cli/{diagnose,guidance,overlay,preview}.py`, surfacing the §9 derived views and the §6 resolver):

- **`corpus diagnose <hash> [--json]`** — the first call: a one-page brief combining the derived views (classifications / issues / uris) with a quick-lint and the record's context blocks.
- **`corpus guidance <hash>`** — the merged `normalization.guidance` from every applied mime / origin / form / atom overlay for the record.
- **`corpus overlay <namespace>/<id>`** — the field-spec table (types, `semantic_type`, required) for a mime, form, or atom overlay, so the normalizer works without reading YAML. Given a bare host instead, it falls back to the origin overlay and prints its host match, declared operational sections, and `normalization.guidance`.
- **`corpus lint <target> [--json]`** — the conformance gate; `--json` emits a single JSON array of findings (each = the `Finding` fields + `record_id`), across all records when `<target>` is omitted.
- **`corpus preview <target> [--page N] [--mark x,y,w,h]… [--full] [-o out.png]`** — the cropping loop's *eyes* (§12.5.5). Renders the artifact (an image, or a PDF page via `--page`) with each proposed bbox outlined on the full image so a vision-model normalizer can see where a region sits, judge the fit, and adjust before committing. Read-only — it never writes the record; the agent commits regions separately by editing the record body. Fits the render to the `llm` budget by default; prints the cache path, or copies to `-o`.

#### 12.5.5 The image toolkit

This group was shaped by reviewing real normalizer runs on image-of-document records (scanned/photographed forms), whose dominant friction was `bbox=` **semantics**: agents read `bbox=x,y,w,h` as corner coordinates, overflowed `x+w>1`, and the resolve failed. The fixes target that directly: the `crop=`/`bbox=` bounds error names the format and the overflowing axis (`… bbox is x,y,WIDTH,HEIGHT, NOT corners`), `corpus resolve`/`corpus preview --help` print the full transform grammar (`_common.TRANSFORM_GRAMMAR`), and `mime/image/image.yaml` carries `normalization.guidance` teaching the bbox convention, crop-first legibility, orientation, and the verify loop.

- **`mark=x,y,w,h[;…]`** (image → image, §6.2) — draws the region(s) onto the full image rather than cropping to them: the inspection dual of `crop=`/`bbox=` (a cycling high-visibility stroke, auto-labeled `1..N`, width ∝ image size). Composes after `page=`, so `corpus://<id>?page=4&mark=0.1,0.1,0.6,0.3` outlines a box on a rendered PDF page — how an agent that can't run a browser sees a proposed crop, as a PNG with the box burned in.
- **`fit=<W>x<H>` | `fit=<preset>`** — downscale to fit, aspect-preserving and reduce-only; distinct from `resize=` (forces exact dimensions, may distort or enlarge). The **`llm` preset** bounds the image to a vision model's input budget: long edge ≤ `LLM_MAX_EDGE` (1568 px) and total pixels ≤ `LLM_MAX_PIXELS` (1,150,000), the smaller scale winning. These constants live in `transforms/image.py`, not Part I — §6.2 keeps presets implementation-defined because model limits drift. PDF `dpi=` is the other half of the dial: rasterize at the DPI you want, then `fit=llm` caps the result.
- **`rotate=90|180|270`** and **`auto_orient`** — right a sideways/upside-down phone photo or scan before the agent reads it; `corpus preview --rotate`/`--auto-orient` expose them.
- **`autocontrast`** (1% cutoff) and **`contrast=<factor>`** — pull a faint scan toward readable; `corpus preview --autocontrast` exposes the flag.

The split that keeps `fit` honest: the transforms stay pure (no implicit fitting), and only the agent-facing surface defaults the budget on — `corpus preview` fits to `llm` unless `--full` (a preview *is* going into model context), while a raw `corpus resolve` applies `fit=` only when the URI says so (a codex embedding a crop in a human-facing deliverable wants native resolution). A typical loop iteration: `corpus preview <id> --page 4 --mark 0.1,0.1,0.6,0.3 -o /tmp/look.png`, read it, adjust, repeat; once right, write the segment at `page=4&bbox=0.1,0.1,0.6,0.3`. **`corpus preview --from-segments <id>`** is the verify half: it reads the record's already-committed bbox segment addresses (grouped by `page=`) and draws them, so the normalizer can confirm each written address frames the span it meant.

One caveat the image guidance makes explicit: unlike a PDF (vector source, re-renderable at higher `dpi=`), an image's resolution is fixed — cropping can't add detail, so for fine print on a low-res capture the levers are crop-tight + `resize=` (interpolated enlargement, not new detail) + `autocontrast`; there is no DPI escape hatch.

#### 12.5.6 Queue mechanics

The queue contract is §8.5; the verbs live in `_cli/{enqueue,drain,finalize,release,await,queue}.py` over the `corpus.queue` library.

**State layout.** External, untracked, under `<root>/queue/` (gitignored alongside `artifacts/`, `capture/`, `cache/`), one marker per record: `<id>.req` (pending request: `requested_at`, `requested_by`), `<id>.claim` (in-flight: `claimed_at`, `claimed_by`), `<id>.result` (last terminal outcome: `completed` | `failed`, with `reason`). A record's queue state is a pure function of which marker exists; markers are JSON written atomically (temp sibling + `os.replace`). The queue never touches `records/` — every verb is read-only on the record (`finalize` reads it to gate; `await` reads the record's derived state as a fallback).

**Atomic claim.** `drain` claims by `os.rename(<id>.req → <id>.claim)` — atomic on POSIX, so when two loop sessions race, exactly one wins (the loser's rename raises and it moves to the next candidate). Requests are claimed FIFO by `requested_at`. An empty queue returns nothing on stdout and exit 1 — the loop's stop signal (per §8.5 this is a non-error empty result; the exit code exists only to break the loop). A stale `.claim` (a dead session) is reclaimable once `claimed_at` is older than `--lease` (default 30 min); reclaim renames it back to `.req`. A duplicate pass from an over-eager reclaim is wasteful, not unsafe (re-normalization is idempotent), so reclaim is best-effort.

**The loop session** (the agent, not the tooling) drives it:

```bash
while id=$(corpus drain --by "$SESSION"); do
    corpus guidance "$id"     # merged overlay normalization.guidance (§12.5.4)
    # ...the agent normalizes $id in-session: title, description, embed/segment
    #    descriptions, re-segmentation; recompiles...
    corpus finalize "$id" || corpus release "$id" --failed "<reason>"
done
```

That bare loop is the **scheduled** shape: a tick (cron) drains until dry, then the model sleeps until the next tick — the model polls, waking on a clock even when the queue is empty. `drain --wait` moves the poll off the model: it long-polls the claim primitive in the subprocess and returns the instant a request is claimable, blocking instead of exiting on an empty queue (until `--timeout`, if set; `--interval` sets the poll cadence, default 2 s). The wait holds no claim — `drain` claims atomically only at the moment it succeeds — so an interrupt mid-wait leaks nothing. A **standing** loop runs `corpus drain --wait` under a persistent runner that re-invokes per claim, so the (expensive) model wakes only when there is genuinely work. The contract is unchanged: `--wait` is an ergonomic over the same atomic claim.

**The done gate.** `finalize` refuses (exit 1, claim left intact) unless the pass gate holds (§8.5: formed-where-declared + lint clean, both derived from the record; *3.2: the authored half retired with the layer*) — a dirty pass is never reported complete. A requester (a codex agent) does `corpus enqueue <id>` then `corpus await <id>`; `await` polls the external state and resolves by exit code, so it works for a re-normalization of an already-passed record (the record alone can't tell the new pass apart — the queue entry can). Because per-domain knowledge rides in overlays (`corpus guidance`), one generic loop serves every codex; a codex contributes by authoring overlays and enqueuing, never by supplying a normalizer.

**Result lifecycle.** `.req` and `.claim` are transient — each transition is an atomic rename that consumes the prior marker — but a settled pass leaves a `<id>.result` that nothing removes on its own (§8.5: an outcome must outlive the pass so a decoupled requester can await after the loop tick ends). Results are GC'd by age: `corpus queue --prune [--older-than DAYS]` (default 7 d; `0` = now) removes settled results past the grace window and sweeps crash-orphaned `*.tmp.*` scratch, never touching live `.req`/`.claim`. Run it periodically; it is idempotent.

**Operator runbook.** The operating modes and result lifecycle are surfaced via `corpus workflow normalize-loop` — guidance for *running* the tooling, distinct from `corpus guidance <id>` (per-record). Runbooks are markdown shipped in the package (`corpus/workflows/`, loaded via `importlib.resources`); `corpus workflow` lists them, shows a runbook, or narrows to a section. The queue verbs' `--help` cross-reference it. Keeping the runbook in the package means the operating modes are maintained once, in the tooling, not duplicated per corpus.

### 12.6 The curator feedback loop *(reshaped in 2.0)*

The 1.0 loop authored composite overlays from observed patterns. The loop survives; its outputs relocate:

**Pattern detection.** The curator periodically scans for patterns worth encoding: origin / fact frequency (many records share a host or a deterministic fact — a `ytdlp_channel_id`, a URL shape); recurring body shapes within a host; demand flowing down from above (the ledger's needs and coverage gaps, `ledger.md` §7/§9).

**Where each pattern lands.** A recurring *deterministic membership* pattern becomes a ledger **harvest rule** (`ledger.md` §10 — authored in the ledger, evaluated by `ath ledger harvest`). Recurring *body-shape* guidance becomes origin-overlay guidance (per host / subtype, §7.2) or an atom overlay (per form, §7.3). Recurring *link structure* becomes a `capture.references` / `capture.relations` declaration (§7.2). Domain conventions for authoring claims land in the ledger's `facts/SCHEMA.md` or a concept schema (`ledger.md` §4.4), never in corpus schemas.

**Re-propagation.** Corpus-side overlay changes re-propagate with `corpus reattest` (attested layer, scoped by `--host`/`--mime`; `git diff records/` is the review surface) and re-normalize sweeps (authored layer, §8.5). Ledger-side rule changes re-propagate with `ath ledger harvest` — records are untouched.

### 12.7 Re-run verbs

Every stage is independently re-runnable (§8.3); each re-run appends a `touch[]` entry. Re-processing is how the corpus absorbs improvement: new schemas, a better extractor / transcriber, an upgraded normalization model, or newly-captured artifacts that resolve old cross-references. The CLI mapping:

- **Re-ingest** — automatic on re-encountered bytes matching an existing `id`; folds the capture into origin blocks (§12.3.5), never a new record.
- **`corpus reattest`** — re-run the attestation layer from the retained artifact + current schemas/tooling (§12.4.6, §8.3).
- **Re-normalize** — enqueue the record again (§12.5.6); refreshes the authored layer (shaper or agent) and faithfulness issues, may re-segment.
- **`corpus compile`** — reassemble a record from a decomposed manifest (§12.4.2) — a different input than `reattest`'s artifact.
- **`re-stub`** — the deliberate reset to the attested baseline (§8.4).

**Scoping a sweep.** Deterministic re-derivation makes scoping a `git diff records/` concern rather than a field-level-diff one: re-derive the affected set and the diff *is* the surgical, reviewable change surface. Scope by the most precise selector available — `--host` (a re-captured / re-overlaid origin), `--mime` (an attestation or mime-schema change), `--classification` (a `mime/*` / `origin/*` / `form/*` class), or a derived-state selector (§4.1 — e.g. formless-only).

### 12.8 Maintenance: GC and record removal

Two distinct risk classes, kept as separate verbs (`corpus.maintenance`): a routine, age-gated sweep of regenerable data (`gc`) and a deliberate, ref-checked removal of a tracked record (`rm` / `forget-origin`). Nothing here is normative — Part I is silent on removal; this is CLI hygiene over the storage layout (§12.1).

- **`corpus gc`** prunes, by file mtime, four regenerable categories — never a tracked record, a live queue entry, or an artifact that still has a record: **`cache`** (resolver output; re-warms on the next resolve), **`staging`** (leftover `capture/` debris — sidecars, crawl coordination files, abandoned partials), **`orphans`** (artifacts with no owning record — ingest is the only writer of `artifacts/`, so an orphan is exactly an artifact file whose record is gone: the debris of a `--force` re-capture, a re-stub, or a hand-`rm`), and **`export`** (regenerable bundles). Previews by default (counts + bytes per category); `--yes` deletes. `--older-than DAYS` sets the grace window (default 7; `0` prunes everything now) — generous beyond the brief window in ingest between writing an artifact and its record, so the orphan sweep never races a fresh capture. `--include` restricts the set; `--json` emits the structured result. Idempotent, empty-shard-tidying, safe on a cron tick.
- **`corpus rm <id>`** removes a record across its layers — the `.md`, the content-addressed artifact, and now-empty shard dirs — with three guards. *Dry-run by default*: without `--yes`/`--force` it prints the plan (paths, sizes, inbound referrers) and deletes nothing. *Ref-checked*: `inbound_references` scans every record's `reference` blocks (§4.3.3.3) for one citing the target — a `source_url` that resolves to it — and refuses a cited record (exit 1) unless `--force`, naming the would-be-dangling referrers. (Ledger evidence citing the record is the other inbound-reference class; checking it is a ledger-side concern — `ath ledger worklist` names the citing claims.) *Reproducibility-warned*: the artifact is gitignored, so dropping it is undoable only by re-capture — `rm` says so, and `--keep-artifact` drops the `.md` while retaining the bytes. It deliberately does not touch the resolver cache (cache is keyed by functional-URI hash, so there is no clean per-record slice); `gc` reclaims orphaned cache by age. A fourth guard lands with containment (2.1): removing a **container** whose members have promoted records strands those records' bytes — `rm` names the promoted members and refuses without `--force`; even when forced, the failure mode is loud (health reports the ids unresolvable, §12.17).
- **`corpus health`'s `dangling_origin_refs` signal** *(3.3)* complements `rm`'s fourth guard above: even where removal itself was never blocked (or happened before this signal existed), a downstream record's own origin block may still name a container that no longer exists — a container a rebundle superseded (§5.2) but whose citing record's origin lineage was never re-pointed. Because origin blocks are append-only history (§5.2), only the record's LATEST block decides whether its live lineage is intact: a dead `corpus://<hash>` there is a `warning` — that citation is genuinely broken, with no route to the bytes through it. A dead hash surviving only in an earlier, superseded block is `info` — honest history of a container that has since been retired, harmless to the record's current lineage. Resolution is same-corpus only (`records/<shard>/<hash>.md` under the record's own root) — the signal never reaches across the tenant boundary. The repair is mechanical, not a hand-edit: `corpus promote` of the same member address under the live container (identity verified first via `corpus resolve`, blake3 against the record's own id) folds a fresh origin block recording the live lineage onto the existing record — the §8.1 fold path, zero mints — leaving the retired block in place as history.
- **`corpus forget-origin <id> <uri>`** handles the many-to-one provenance case: identical bytes accrue multiple origin aliases (§5.2); when one alias is wrong, this drops it without removing the record. Matched by identity key (§12.3.9), so a query-noise spelling still matches. Refuses when it is the record's only origin (that is an `rm`) and is a no-op when the uri isn't among the origins. An origin block whose every uri was forgotten is dropped; the edit appends a `corpus.forget-origin@` touch. It edits the tracked `.md` (git-recoverable), so it acts by default with `--dry-run` to preview — the asymmetry with `rm`'s dry-run default is deliberate (a tracked-text edit vs. irreproducible byte loss).
- **`corpus pack`** *(planned, 2.1)* — the inverse of promotion: consolidate standalone artifacts into a container (the container captured, ingested, and manifest-attested; the members' blake3s unchanged), then prune the now-redundant standalone files once each member verifies as container-resolvable. No record changes — residence is invisible (§2). Until it lands, a standalone artifact whose blake3 is *also* container-resolvable is simply a redundant copy, not an orphan.
- **`corpus session <capture|list>`** bundles a Claude Code session — its `<id>.jsonl` transcript plus the `<id>/` sidecar tree (sub-agent transcripts, tool-result payloads, workflow state) — into ONE deterministic zip via the reusable writer core above (the first shipped consumer of the `pack` engine), then ingests it as a zip manifest so every member is a directly-addressed `path=<member>` embed (the transcript is never transcribed). It binds the `claude-code-session` producer-export origin (§7.2, uri-less, keyed on a `session_id` field); `--from [user@]host` sources a session from another machine over ssh/rsync. Sessions are personal (a transcript embeds every tool result verbatim) — they belong in a private corpus.
- **`corpus continuity <A> <B>`** proves whether record `A`'s addressable content is preserved in `B`: per `path=<member>` it is byte-identical, *contained* (A is a prefix B extends — the append-only case), *diverged*, or *absent*, and `contains_a` is true iff every unit is preserved. This is the supersession safety check — the *same* test answers "may B replace A?" (keep the more complete version: a re-captured session that grew supersedes its predecessor, while a compacted one must not clobber the fuller copy) and "may a citation of A be rewritten to B?" (`ath ledger supersede`, `ledger.md` §13.3). No synthetic stable id is minted: identity stays the blake3, and continuity carries citations forward only where the content survived.
- **`corpus capture --force --replace`** is a supersession ergonomic over `rm`: `--replace` (requires `--force`) snapshots the records holding the URL before the capture and, if the new bytes produced a different record id, retires the prior record(s) for that URL, reclaiming the old artifact bytes. When the bytes are identical, the capture folds into the existing record and nothing is retired.

### 12.9 Resolver surface and cache

A common resolver surface is a CLI that writes the materialized result to disk and prints its absolute path:

```
$ resolve 'corpus://<hash>?<params>'
/abs/path/to/cache/<shard>/<urihash>.<ext>
```

Conventional flags: `--regenerate` to bypass cache, `--json` to print a sidecar with derivation metadata. Library and HTTP-service surfaces are equally valid (§6.3).

The cache layout mirrors the sharding convention — `cache/<urihash[:2]>/<urihash>.<ext>`, where `urihash = hash(<canonical-uri>)`, with a `<name>.json` sidecar for JSON-valued ops so extensions can't collide. Cache invalidation is by deletion; eviction policy is implementation-defined (§6.4).

**The member index (2.1).** The route from a bare blake3 to its container (§2) is a derived map — `member transport hash → (container id, member address)` — built by walking every record's embed blocks, exactly as the URI index is built (§12.15 applies: rebuilt-on-start; persistence is a deferred perf optimization). Binary-store lookup falls back through it when no standalone file exists, recursing through nested containers, and the resolver cache absorbs hot paths — a member deep inside a solid compressed stream (a tgz) costs one streaming decompress on first touch and is cache-warm after. The promoted record's origin `uri:` (its containment lineage, §8.1) is **history, never consulted for byte lookup** — residence must stay free to change out from under it.

### 12.10 Export output layout

A common export layout writes one directory per exported record:

```
export/<record_id>/
├── <name>.md
├── <name>_001.<ext>
├── <name>_002.<ext>
└── ...
```

with the §10 embed-rewrite mapping each functional URI to a sequentially numbered local file.

### 12.11 Common address schemes (illustrative)

Media-type schemas declare their own address grammar (§4.3.2). Schemes that have proven useful in practice, as examples only:

| Axis | Example | Typical source |
|---|---|---|
| element | `el=<N>` / `el=<N>-<M>` | marked-up / HTML text (any element by 1-indexed position; output determined by the element — an `<img>` renders to an image, a `<video>`/`<audio>` or `<a href="data:…">` attachment carrier materializes to its raw bytes, a text element to its region) |
| page | `page=<N>` | paginated documents |
| block | `block=<N>` | block-structured documents without fixed pages |
| sheet | `sheet=<name>` (+ `bbox=<A1-range>`) | spreadsheets |
| row | `row=<N>` (+ `col=<name-or-index>`) | delimiter-separated text tables (CSV/TSV; 1-indexed over data rows, header excluded; RFC 4180-aware raw-row extraction with the dialect pinned by the mime schema, so row bytes are deterministic; `col=` narrows to one field by header name or 1-indexed position, output `text`; engine-pinned — `csv-row-col@1` — like any derivation op, §6.4) |
| time | `time=<tc>` / `time_range=<s>-<e>[,…]` | audio / video (a comma-delimited ordered list of ranges materializes as concatenated cuts in listed order — the muxing contract, §6.2; on a container the cut is of the composition via per-kind default members) |
| frame | `frame=<tc>` | video stills |
| region | `bbox=<x>,<y>,<w>,<h>` | image crops (relative floats) |
| turn | `turn=<N>` | turn-structured transcripts / sessions (1-indexed unit in the record's declared unit array, located by the origin overlay's form mapping — §7.2; `turn=<N>&att=<M>` addresses unit N's M-th declared attachment, materialized by lineage-chained resolution, §6.2) |
| stream | `stream_id=<id>` | multi-stream media (a media container's track members — extraction semantics pinned by the mime schema so member bytes are deterministic and promotable, §8.1/§11; also composes onto another axis as before; bare ops route via default-member resolution, §6.2) |
| card | `card=<N>` | multi-card vCard files (1-indexed; `BEGIN:VCARD`/`END:VCARD` delimiter-pinned extraction, so member bytes are deterministic and promotable — the mbox precedent) |
| property | `prop=<N>` | a vCard's own properties (1-indexed over the card's property list, output `text`; decoded — QUOTED-PRINTABLE hex-escape + RFC 6350 §3.4 backslash-unescape — mirroring the `contact-card` form's `prop=N` segment addressing exactly, §7.8, so a citation's `?prop=N` anchor resolves to the same datum the formed record renders; a binary-encoded property — PHOTO/LOGO/SOUND/KEY, `ENCODING=B`/`BASE64` — has no decoded text, same as the segment's header-only rendering) |
| entry | `entry=<N>` | calendar files (ICS; 1-indexed `VEVENT`-delimited entries, promotable likewise) |
| item | `item=<id>` | HEIF/HEIC image items (container-declared item ids; the `pitm` primary is the default-member target, §6.2) |
| attachment | `attachment=<N>` | a `work` transport's exposable embedded files (PDF embedded files / portfolio members; OOXML embedded objects — §7.1) |
| path | `path=<relpath>` | archive members (kept-whole archives: zip, tar/tgz) |
| message | `msg=<N>` | mailbox archives (mbox; 1-indexed). Extraction semantics — the `From ` delimiter convention and `>From ` un-stuffing variant — are pinned by the mime schema, so member bytes are deterministic and promotable (§8.1) |
| part | `part=<N>` | MIME message parts (email; 1-indexed addressable parts — every leaf part plus every nested `message/rfc822` as a whole, in depth-first pre-order — as CTE-decoded payload bytes; promotable per §8.1) |

Addresses compose with `&` (e.g. `page=<N>&bbox=<x>,<y>,<w>,<h>`); a single address or an ordered list (for non-contiguous spans, in reading order); query-reserved characters in a value are percent-encoded.

### 12.12 The concept knowledge base *(removed in 2.0)*

*Retired with the `concept` namespace (§4.3.3.4).* The local Wikipedia/Wikidata KB (Kiwix ZIM via `libzim`), `concepts.ConceptResolver`, the corpus-local `concepts/*.yaml` registry, and `corpus concept link` all retire from the corpus contract. External-authority identity is a ledger concern: a concept claims its `wikidata:Q…` id once, citing a mirrored reference dataset — where the local-mirror idea itself returns, as the `ref://` resolver (`ledger.md` §6.5).

### 12.13 Token counting

The `token_counts` view (§9.6) is computed with: text counted by a local BPE tokenizer approximating the target model's (an `o200k`-class vocabulary), lazy-imported behind an optional extra with a chars/4 heuristic fallback so the base library carries no tokenizer dependency; and an image-token estimate of `≈ min(width·height, 1,150,000 px) / 750` per image, from declared dimensions (`0` when absent). The tokenizer fetches its vocabulary on first use and caches it — warm the cache once for offline operation. Like every §9 view, the counts are never persisted to records; a search index may cache them per record (alongside size and segment count) for filtering and statistics.

### 12.14 Serving a corpus

No server is part of the corpus contract — a corpus is a directory of records, schemas, and caches, fully usable offline through the library and CLI (§1.5 principle 9). A serving layer may front one or more corpora — records, derived views (§9), artifact bytes, resolver output (§6) — over HTTP for browsing or search. It should remain a thin read surface that serializes what the library already produces, adding no parsing, derivation, or resolution logic of its own, and it never attests, normalizes, or executes corpus-local code. Multi-corpus routing (mapping public ids to corpus roots) is a serving-layer concern; the tooling itself is single-root per invocation. One sharp edge: a functional-URI value passed through a URL query string must be fully percent-encoded.

### 12.15 Open implementation questions

Flagged for follow-up; not all are blockers.

- **Sharding crossover** (applies to both corpus and codex layers). When does single-level hex-prefix sharding stop being adequate — at what record count do we move to two-level (`a7/f3/…`)? Likely a tooling-driven flag declared in `corpus.toml` (corpus side) or `codex.yaml` (codex side), with tooling rebalancing on change; the codex layer defers to this entry (see `codex.md`).
- **URI index persistence.** The URI → `id` lookup (`records.build_uri_index`) is rebuilt-on-start from the records — the settled default (an in-memory query engine, not a data store). A persistent side-file is a deferred perf optimization, not an open design question.
- **Schema validation.** `corpus lint` validates *records*, not schemas; a `validate-schemas` command (`extended_fields` well-formed, `semantic_type` within the closed seven, no reserved `provenance` declared as a field, `capture.*` sections parseable) is still missing.
- **Multi-corpus capture.** When the same content needs to land in multiple corpora, capture is currently a copy step on top; a "capture into multiple corpora" mode is a possible future feature.
- **Segment-anchored mechanical references.** Overlay-declared reference emission is record-scoped today (§12.3.10), while §4.3.3.3 specifies a segment-pinned anchor (`address:`/`quote:`); closing the gap needs a reliable DOM→segment mapping.

### 12.16 The 2.0 migration (non-normative)

The migration story for the 1.0 → 2.0 contract change, recorded here because 10,000+ records conform to 1.0. Field inventory at the time of the change (public + private corpora): ~10,200 classify blocks, of which ~10,100 were `provenance: auto` (regenerable derivations); ~93 asserted classify blocks; ~146 interpretive `reference` blocks; ~77,000 `relation` blocks (mechanical in nature, asserted-labeled); zero `concept` blocks; zero `aside` blocks.

1. **Tooling alignment first.** The corpus tooling sheds the classify subsystem (the classify-block grammar, `classify_when` engine, `corpus classify`/`reclassify`, composite schema loading, the classifications view's composite rows, `classification-stale` lint, the concept resolver + `corpus concept`) before any record sweep, so lint and health define 2.0 conformance.
2. **Strip the derived.** All `provenance: auto` classify blocks are stripped in one sweep — they are derivations, re-mintable as ledger harvest output; nothing is lost.
3. **Harvest the asserted.** Asserted classify blocks and interpretive reference blocks carry real interpretation: they convert to ledger concepts/claims (the record rostered and cited as evidence) and capture needs respectively, as part of the ledger migration. Until the ledger exists, the extraction inventory is the migration's staging artifact.
4. **Schemas retire into rules and shapes.** Composite schema YAMLs leave `schema/` and become source material for harvest rules (`classify_when` → `match`, extraction scripts → `mint`), concept schemas and ledger `SCHEMA.md` conventions (domain shapes and guidance, `ledger.md` §4.4/§8), and origin-overlay guidance (body-shaping parts — notably the per-page-type guidance of large mechanical families).
5. **Relations relabel on re-draft.** 1.0-era relation blocks relabel to `provenance: auto` as origin-declared lifting (`capture.relations`) lands in the drafter; until then they are grandfathered as-is (§4.3.3.5 migration note).

### 12.17 The 2.1 containment amendment (non-normative)

Migration story: **zero existing records change shape.** Records never carried `artifact_kind` (it was schema-side); the only bundled `decomposable` schema (raw `application/zip`) flips to the `zip-manifest` strategy and `_ingest_decomposable` retires. Records minted by past decomposable ingests are ordinary standalone records and stay exactly as they are — promotion is additive, a second residence for bytes, not a new record shape. Schemas still declaring `artifact_kind` are ignored (tolerant parsing) and swept at leisure.

Tooling alignment order, mirroring §12.16's tooling-first discipline:

1. **The member index + store fallback** land in the resolver/store layer (§12.9), so a bare blake3 resolves through containment before anything mints records that depend on it.
2. **`health` redefines "missing"** as *unresolvable by any route* — standalone or containment (`missing_artifacts` consults the member index). Deep byte-verification of container members (streaming re-hash against embed `transport:` hashes) is an explicit verb, not a default check.
3. **`corpus promote`** mints member records (§8.1), verifying streamed bytes against the embed's recorded hash before writing the record.
4. **The zip default flips** (raw archives stop exploding; tar/tgz gains a manifest drafter + `path=` transform).
5. **`corpus pack`** (consolidation, §12.8) follows when a corpus wants it — e.g. folding thousands of sibling standalone files into a handful of taxonomy archives with no record edits.

### 12.18 The 3.0 revision migration (non-normative)

The migration story for the 2.x → 3.0 contract change. Inventory at drafting time (2026-07-13): **11,005 records** (3,629 private + 7,376 public); ~5,820 records carry ~19,350 section blocks; the private corpus is ~85% conversation-shaped (2,961 iMessage + 66 Discord + 59 Google Chat records), plus 54 bank statements, 44 receipts, 153 emails, containers and media; the public corpus is 7,213 HTML documents (2,360 of them ALLDATA procedure pages), 102 videos, 61 PDFs. **Zero ledger citations exist into the 125 Discord/Google Chat conversation records (verified 2026-07-13)**; ledger citations elsewhere are protected by the touch-keyed snapshot binding (below).

Order of operations, tooling-first per the §12.16 discipline:

1. **Tooling alignment.** The parser/emitter learns qualified section openers, the `structural` segment kind, and the two-status lifecycle (a 2.x `status: draft` parses tolerantly as stub-era input); the drafters split into attestations + derivation ops (§12.4); shapers land (`corpus.shape` registry; the iMessage sub-drafter re-registers as a shaper); `corpus draft` retires, `corpus reattest` arrives; lint gains form-coherence and byte-mark rules and drops draft-status rules; `health` and the member index are untouched (§12.9). Lint + health then *define* 3.0 conformance before any record sweep.
2. **The grammar sweep** (mechanical, per-record, lint-gated). Every stored TOC section converts or drops by the byte-mark rule: a section whose boundary is a byte-mark (EPUB nav → `spine=` marks; PDF outline wraps → `page=` marks; a media chapter; a Google Chat topic) becomes a structural segment (level from the source's own hierarchy else 1, `entry`/address preserved as the mark position); a **synthetic** section drops entirely — foremost the iMessage per-day sections (owner's decision, 2026-07-13: *"Absolutely remove that. It shouldn't have been there to begin with"*) — per-day grouping becomes the `corpus toc --tz` read-time rendering.
3. **The status sweep.** `status: draft` → `stub`. A 2.x-era mechanical body found on such a record is a **grandfathered materialized derivation**: tolerated by lint, superseded by the record's next pass (a re-normalize authors the stored form; a re-attest may strip it). Whether to strip these bodies eagerly (pure 3.0: re-derive on demand) or lazily (pragmatic: 2,961 conversations stay readable in-file through the transition) is an open question below; the lazy path is recommended and leaves no permanent transitionary state — every record exits it through its next pass.
4. **Form adoption sweeps.**
   - The **125 Discord/Google Chat conversations** re-shape mechanically (`corpus.shape.conversation`): form section + authorship-ordered codebook, one `text/message` per message at `turn=<N>` (codebook `participant:` indexes; timestamps in the source-stated zone — Google Chat locale strings normalize to UTC, DCE offsets kept verbatim, zone-less sources stay zone-less; `reply_to:` where the platform reference resolves in-record), `text/metadata` for DCE event messages, attachment markers at `turn=<N>&att=<M>` (no embeds — lineage-resolvable), Google Chat `topic_id` structural marks. Authored titles/descriptions are preserved verbatim; zero ledger citations exist into these records, so nothing re-anchors.
   - The **iMessage fleet** (2,961): day sections drop (step 2); the envelope form already conforms (`text/message` with verbatim `sender:` — licensed alongside the codebook form, §7.3); each record gains its `<!--section conversation-->` (with the codebook derived from the distinct senders) on its next pass through normalize — the sweep enqueues them; no re-transcription of anything.
   - **Statements (54) and receipts (44)** adopt `form/statement` / `form/receipt` as those overlays are authored — the origins already exist; the overlays inherit their shape guidance.
   - **102 public videos** re-attest as track manifests on demand (tracks promotable thereafter); no eager sweep — residence and shape change nothing about their bytes.
   - The **iCloud contacts export** re-attests under the new disposition: the ~150-card `text/vcard` artifact — currently one record segmented `el=<N>` — becomes a `card=` **manifest** with delimiter-pinned card embeds, each promotable to its own `text/vcard` record. The consumer is already waiting: the pending cross-platform identity-linking ledger pass ("identity-v2") wants to cite *individual cards*, not offsets into a 150-card blob.
   - The **Facebook / Instagram / Threads export containers** (already ingested) need **zero new machinery**: their conversation JSONs surface as promotable members shaped by `form/conversation` (per-producer `form:` mappings on their origin overlays, §7.2), and their media trees are lineage-resolvable at `turn=<N>&att=<M>` — the Discord pattern verbatim. The work is authoring mappings, not building anything.
5. **Gates.** Every sweep lands lint-clean + health-clean with the tooling suite green. For any sweep touching a **ledger-cited** record: the ledger's snapshot binding is touch-keyed (`ledger.md` §13.2) — a re-shaped record's new touch flags exactly the evidence entries needing re-verification; `ath ledger verify` names them; re-anchor (line/turn addresses move; quotes are verbatim spans and mostly survive) and `--stamp` re-bind. No citation silently rots: a broken anchor is a loud verify failure until re-anchored.

**Open questions** (flagged, not resolved here):

1. The form overlay `checks:` grammar — settle with the first three overlays (`conversation`, `statement`, `receipt`), not in the abstract.
2. The concrete mime-schema key surgery (`mode`/`draft.*` → `attest:`/`derive:` naming, aliasing, tolerance window) — tooling-time detail.
3. Eager vs lazy stripping of grandfathered 2.x mechanical bodies on stubs (step 3; lazy recommended).
4. Demuxer determinism for `stream_id=` member bytes (§11) — pin against container sample tables, and decide the reference implementation. *(Resolved — §12.20.)*
5. Sidecar-declared chapters vs the byte-mark rule: 3.0 admits producer-declared enrichment as a mark source (§4.3.2.3, §12.3.7) — confirm this extension is wanted, or restrict marks to container bytes only. *(Resolved — §12.20: confirmed as a mark source; new captures embed chapters in-band.)*
6. Text-based subtitle tracks project faithfully; bitmap subtitle tracks (PGS) have no lossless text projection — they stay embeds until an OCR-provenance projection is specified.
7. Whether `canonical_strategy` (persist currently disabled, §7.1) computes at ingest attestation or as a derivation op when re-enabled.
8. The derived-body op's cache/indexing contract for very large records (a 72k-message conversation's `body` on demand) — likely just §12.9's cache doing its job, but measure.
9. The exposable-embed attest sets per `work`-disposition format — which PDF/OOXML internals attest (embedded files yes; every OLE sub-object?), and at what depth — settle per mime schema with the first real captures that carry them.
10. The re-homed CLI surfaces for the retired `draft` verb's options — the `--fingerprint`/`--no-fingerprint` override (§12.4.4) and the mbox selective `--messages` declaration (§12.4.1) — are currently named only as "the ingest/re-attest surface", a placeholder; settle the concrete verbs and flags at tooling time.

### 12.19 The 3.1 layers migration (non-normative)

The migration story for the 3.0 → 3.1 contract change. Inventory at drafting time (2026-07-16): **11,058 records** (7,376 public + 3,682 private), every one at `status: stub` or `status: normalized` (the §12.18 sweeps are complete). Of these: **7,751 `normalized`** records carry stored renderings, of which only **139** carry form sections (the §12.18 step-4 conversions — conversations, statements/receipts, vcards) — the rest, dominated by the ~6,800-record public document population, are stored renderings under no named contract; **3,307 `stub`** records include the **3,278 grandfathered materialized derivations** of §12.18 step 3; **4,651 queue requests** are pending (3,194 private — the iMessage fleet + statements/receipts — and 1,457 public). Ledger snapshot bindings exist on cited records throughout, all touch-keyed (`ledger.md` §13.2).

Order of operations, tooling-first per the §12.16 discipline:

1. **Tooling alignment.** The parser accepts and ignores a frontmatter `status:` field (read-tolerant); the emitter never writes one — any record's next write drops it. The derived-state predicates of §4.1 (*formed*: a form section governs the stored content zone; *authored*: the two editorial fields non-empty) land in the records library as the one shared implementation. Lint re-keys every status-conditioned rule to the predicates (form-coherence is already predicate-shaped); the queue's `finalize` re-keys to the pass gate (§8.5); `health` retires its status tallies **and the remaining draft-era surfaces** (pre-existing debt rides along — e.g. the `corpus redraft --status` remnant) in favor of layer-presence reporting (attested / formed / authored / grandfathered counts, standing demand); sweep selectors (`--status`) re-key to derived-state flags. The suite green on all of this *defines* 3.1 conformance before any record sweep.
2. **The status-removal sweep** (the third status sweep; mechanical, per-record). Strip the `status:` line from every record's frontmatter — a frontmatter-only edit, zero body bytes change — with a `corpus.migrate.<sweep-name>@<v>` touch appended per record and a per-tenant migration manifest committed alongside, exactly as the §12.18 sweeps did.
3. **Ledger re-verify.** The sweep's touch flags **every cited record's** snapshot binding — the touch-keyed loud-flag discipline working as designed, not rot. Because the sweep changed no body bytes, anchors and quotes are untouched: `ath ledger verify` re-checks and `--stamp` re-binds mechanically in one pass. The ledger's own gate re-keys in the same step (`ledger.md` §13.1's evidence check and §6.3's discipline move from status to verifiable surfaces; §13.2 gains the derivation-op version pin).
4. **Form-library growth** (lazy — no eager sweep). The generic shape contracts (§7.8: `document`, `article`, `procedure`, …) are authored as their consumers arrive; the rendered-but-formless population adopts at its next pass through normalize. One measured shortcut is available per contract: where an existing stored rendering **already conforms** to a newly minted generic contract, a mechanical adopt sweep may stamp + conform in bulk — measured against the real bodies first, never assumed (the §12.18 lesson: a fixture proves the code, only the fleet proves the contract). The step-3 grandfathered bodies keep their §12.18 exit: adopt a form at the record's next pass, or remain convenience-only, unverifiable, and strippable.
5. **Gates.** Suite green; both corpora lint- and health-clean; `ath ledger check` + `verify` clean. Every sweep lands as one reviewable commit per tenant (`git diff records/` is the change surface).

**Open questions** (flagged, not resolved here):

1. Concrete CLI names for the derived-state selectors and health's layer-presence report — tooling time.
2. The derivation-op version pin's binding format on ledger sources entries (`ledger.md` §13.2) — settle with the first derived-surface citation, not in the abstract. *(Resolved — ledger 1.5, 2026-07-20: the sources `verified.ops` map, engine pins keyed by axis param, stamped from resolver registry introspection; verification resolves derived-surface anchors through the resolver itself.)*
3. Whether the queue's public backlog (1,457 pending requests predating the standing-demand reframe) still represents real demand — re-derive it from actual consumers (ledger worklists, codex scopes) rather than carrying it forward on faith.

### 12.20 The media-ops increment (non-normative)

§1.2's track-manifest model has been **normative since 3.0** — a multi-track media container is a raw archive; its elementary streams are content-addressed embeds at `stream_id=`, promotable on demand; the audio-track record owns the transcript, the video-track record owns frame work. This section is that model's deferred **implementation order** (the "media-ops increment" parked at §12.18 tooling time), triggered by its first consumer: the slide-deck + transcript treatment of presentation video (2026-07-16). Inventory at drafting: **103 video records** (102 public, 1 private), all attested as single works — none yet carries a track manifest; the resolver ignores `stream_id=` and implements none of the muxing ops.

1. **The determinism contract first** *(resolves §12.18 OQ4)*. A stream embed's `transport:` is the blake3 of the member's extracted bytes, so extraction is pinned before any manifest is attested. The rule is two-layer, pinned per codec on the mime schema:
   - **Identity bytes are byte-work, never engine output**: the codec configuration record followed by the sample payloads in decode order, each read verbatim from the container's own tables (ISOBMFF sample tables; Matroska block reads). Where the codec has a conventional self-framing elementary form, the pinned form is that convention (H.264/H.265 → Annex-B: parameter sets from the config record + start-code-framed NAL units — a syntactic reframing defined by the codec spec, not an encode; AAC → ADTS). Where none exists (Opus), the pinned form is a corpus-defined framing: the config record + length-prefixed packet payloads in decode order. No encoder and no muxer ever sits in the identity path — determinism by construction, the mbox `msg=` discipline at media scale.
   - **Playable renderings** (a file a player accepts) are `format=` conversions — engine-versioned (§6.4), cache-keyed, ephemeral. ffmpeg is the engine here, and only here.
   - The suite carries a double-run byte-identity test per pinned codec (plus a cross-version canary); continuity-gated supersession (§11, §12.8) remains the net if a pinned extraction is ever found to shift.
2. **Track-manifest attestation.** The media-container mime schemas gain their `attest:` manifest-embed declaration: one embed per elementary stream at `stream_id=<id>`, transport per the contract above; `disposition: manifest` throughout (§1.2 — default-member resolution keeps bare ops transparent on single-track containers). Chapter marks land as structural segments: container chapter atoms are byte-marks proper; producer-declared chapters from the capture sidecar are **admitted as a mark source** *(resolves §12.18 OQ5 — they are the source's own declared boundaries)*, and video captures embed chapters in-band going forward (`--embed-chapters`) so new artifacts carry them as byte-facts. `corpus reattest` upgrades an existing video record **additively** — the fleet adopts lazily, no sweep.
3. **Promotion through the stream.** `corpus promote corpus://<container>?stream_id=<n>` mints the track record: id = the pinned extraction's blake3, bytes resolving through the container by lineage (§2, §8.1 — no copy), origin = containment lineage. The resolver implements `stream_id=` isolation in this increment; `cut=` and `format=` (the muxing contract's ops, §6.2) ride with it.
4. **The two form mints** (§7.8 registry; contracts ship in the package, §12.2). `form/transcript` — speech as time-anchored, speaker-attributed verbatim text; the `speakers:` diarization codebook; the engine transcript (`?transcribe`) verified and corrected by the pass. Its boundary against `form/conversation` is exchange structure: conversation names a multi-party exchange, transcript names speech-over-time. `form/slide-deck` — an ordered sequence of visually-composed slides: one `image` marker per slide at `time_range=` (stills derive at `frame=`, no embed) with verbatim on-screen text as sibling `text/ocr`. A native-deck axis (a pptx export's member addressing) joins the contract's checks with its first native consumer.
5. **Boundary support.** Slide boundaries are mechanically **proposed** (a pinned scene-cut derivation op, engine-versioned like `transcribe`) and interpretively **verified** at the form pass against rendered stills (`frame=`, `corpus preview`). Chapters are marks or sections, never slides — a 10-chapter deck may hold 60 slides.
6. **The pilot, then the fleet.** The private presentation video (`fb4e0b72…`, captured 2026-07-16) runs end-to-end: reattest → track manifest; promote both streams; the audio track forms as `transcript` (a single-speaker degenerate codebook), the video track as `slide-deck`; both vouched; the container stays a pure manifest — its `body-empty` lint warning dissolves with its embeds, exactly as a zip's would. The 102 public videos adopt on demand at their next reattest. The film/tele residency arc (proposals) inherits all of this unchanged: a 20 GB mkv on a share serves its transcript, a clip, a frame through the cache while the artifact never localizes.
7. **Gates.** Suite green (including the determinism tests); pilot container + both track records lint-clean; health clean in both corpora; any ledger-cited video record's reattest rides §12.19.3's touch-keyed re-verify discipline.

**Open questions** (flagged, not resolved here):

1. The scene-cut op's pinned parameterization (engine, threshold, minimum interval) — settle on the pilot's real deck, not in the abstract. *(Resolved by the pilot, 2026-07-16: `scenes=0.3` recovered 33 of 36 slides with zero over-segmentation — a good default, and the miss pattern (a same-background title-card transition; two unexplained misses in a content-heavy stretch) is not threshold-fixable, which confirms the contract's proposed-then-verified split is load-bearing: no threshold substitutes for the eyeball pass.)*
2. Whether film-scale track records want residency claims ahead of the storage-network arc — parked with that proposal.
3. Bitmap subtitle tracks remain §12.18 OQ6: no lossless text projection; they stay embeds until an OCR-provenance projection is specified.

### 12.21 The 3.2 derived-editorial migration (non-normative)

The migration story for the 3.1 → 3.2 contract change. Inventory at drafting (2026-07-16): **11,061 records** (7,376 public + 3,685 private), of which **7,756 are authored** in the 3.1 sense (6,814 public + 942 private — stored frontmatter title/description) and only **141 are formed** (all private; `formed_unauthored: 0` in both tenants, so every formed record's vouch has a section header to land on). The dominant population is **formless-authored — ~7,615 records**, overwhelmingly public web captures whose stored titles were copied from `<title>` / `ytdlp_title` at authoring time.

Order of operations, tooling-first per the §12.16 discipline:

1. **Tooling alignment.** The schema loader parses `role:` on `extended_fields` declarations (mime §7.1, origin §7.2, form §7.8; unknown roles read tolerantly). The **derived-editorial resolution** (§4.2.3: precedence, latest-block-wins, whole-record-section scoping, empty-falls-through) lands in the records library as the one shared implementation — consumed by the derived body, search indexing, export, and health. The emitter writes frontmatter `title:`/`description:` **only when an override value is present** — never the empty-string placeholders; the parser reads a stored pair tolerantly as the override. Lint gains one rule: an override **equal to the record's derived value** is a `warning` (noise, not an assertion). The queue's `finalize` re-keys to the 3.2 pass gate (§8.5); health retires the `authored` tally in favor of **derived-editorial coverage** (records deriving non-empty vs. empty title — the empty set is the role-marking worklist); sweep selectors keyed on the authored predicate re-key or retire.
2. **Role-marking the schemas.** The candidates that exist today get their marks: `ytdlp_title` / `ytdlp_description` on the yt-dlp-lifted origin overlays (both tenants' `youtube.com` + the mime sidecar declaration they ride); artifact-block title-bearing fields in the package mime schemas (PDF `/Info` title, EPUB Dublin Core, eml `subject`, HTML `<title>` where attested); the universal section-header `title:`/`description:` need no per-form declaration (implicit, §4.3.2.1). This step is where the sweep's divergence report (step 3) feeds back: an overlay whose records lose a good stored title wants a mark or a form.
3. **The editorial-relocation sweep** (mechanical, per-record, one commit per tenant with a migration manifest, per the §12.18/§12.19 pattern). For every record with a stored pair: a **formed** record's values relocate onto its whole-record form section header (`title:`/`description:`, §4.3.2.1) — where a value merely equals a derived candidate beneath, it drops instead of relocating; a **formless** record's values **drop**. Where the dropped value equals a marked candidate, nothing is lost; where it diverges, the loss is **accepted by design** (sjrahn, 2026-07-16: *"I think we can accept the loss. It will be obvious then which overlays or forms we need to update to surface these"*) — the sweep emits a per-tenant **divergence report** (record id, dropped value, best derived candidate) as the migration's real deliverable, and the override mechanism is deliberately NOT used to grandfather divergent values: an override is a standing editorial assertion, never a migration artifact. Touch: `corpus.migrate.<sweep-name>@<v>` per record.
4. **Ledger re-verify.** The sweep's touch flags every cited record's snapshot binding (the §12.19.3 loud-flag discipline). Relocations change section-header YAML only — segment bodies, addresses, and quotes are untouched — so `ath ledger verify` re-checks and `--stamp` re-binds mechanically. The ledger's own wording re-keys in the same step: `ledger.md`'s "authored prose" verifiable surface (its §6.3/§13.1, the 1.1 amendment) narrows to **prose the record body carries under an authoring touch** — form-span renderings, editorial header fields, descriptions — no longer the frontmatter vouch.
5. **Gates.** Suite green; both corpora lint- and health-clean; `ath ledger check` + `verify` clean; `git diff records/` the review surface per tenant.

**Executed 2026-07-16** (same date as drafting). Two findings reshaped the run. (1) Step 2 surfaced that §7.2's **origin-block host qualification had never been implemented** — every URL-retrieved record fleet-wide carried a bare `<!--origin-->` opener, invisibly papered over by a hardcoded `ytdlp_title` display fallback — so an unplanned **origin-qualify sweep** landed between steps 2 and 3 (qualification wired into the shared attest seam for ingest + re-attest; 7,336 public + 1 private openers stamped, 27 overlays, most-specific-host-wins). (2) The step-3 equality split **inverted the drafting expectation**: divergence dominated — public 14,099 divergence rows against only 88 equal-drops, **96% of it one origin (`my.alldata.com`)**, whose ~6,500 authored procedure descriptions had *no derived candidate at all* and whose stored titles were cleaner than the branded html `<title>`; private landed 2,743×2 placeholder drops, 807/808 divergent drops, **134×2 relocations** (every whole-record form section took its vouch cleanly; zero header-occupied), and exactly one equal-drop. The divergence manifests (`migration/editorial-sweep-32-divergence.jsonl`, per tenant) are the standing role-mark/form worklist — alldata first, by an order of magnitude. Step 4 re-verified mechanically: 1,175 verified / 0 errors, 725 bindings re-stamped, no quote anywhere had cited the dropped prose. Post-migration coverage: public titled 7,338 / untitled 38; private titled 3,543 / untitled 142. One lint rule was fixed mid-sweep (`section-description-redundant` now exempts the whole-record section — the vouch's home is not a span synopsis).

**Open questions** (flagged, not resolved here):

1. Within-layer tie-breaking is **latest-block-wins** by decision (sjrahn, 2026-07-16: *"Let's go with latest block wins. May have to revisit"*) — revisit when multi-origin records with competing marked titles arrive in numbers (the re-capture case is the intended winner; the multi-source aggregation case is the one that might not be).
2. Whether health's derived-editorial coverage should distinguish *empty-because-unmarked* (schema wants a role mark) from *empty-because-bare* (the artifact genuinely carries no title-shaped fact) — settle when the coverage report exists.
3. Whether the lint `warning` on a derived-equal override should escalate to auto-drop on the record's next write (the `status:` precedent) — decide after the fleet shows how overrides actually get used.

---

### 12.22 The form-library growth arc: five generic contracts and the first multi-shape origin (non-normative)

The §12.19 step-4 lazy path executing at scale, driven by the §12.21 divergence worklist (96% of it one origin, `my.alldata.com`, 7,046 records; the owner's design calls are quoted in the orchestrator logbook, 2026-07-16).

**The five contracts.** `form/article` (prose-led reading matter), `form/document` (page-like renderings whose payload is figures/tables/plates — the extraction-preserving contract: §1.5's stored-rendering invariant would otherwise exit the fleet's vision-authored `text/ocr`/`text/data-table` siblings at their next pass), `form/procedure` (stepped work instructions, including diagnostic charts), `form/bulletin` (numbered, dated, tracked advisories; envelope `bulletin_no` + optional `bulletin_date`/`supersedes`/`campaign_id` — the harvest surface), `form/index` (entries-are-the-content listings, link-list or tabular). `data-table-set` is deliberately NOT minted (owner: *"we do want to keep the forms grounded in real representative things"*; §7.8's own line — a label that changes nothing about rendering or checking is not a form): table-payload pages are documents. The library lands at ten shapes, §7.8's guard edge.

**Population priors** (census 2026-07-16, route × body over 7,046 records; every bare-route itype identified; fleet-validated same date): procedures ~1,600 · documents ~1,400 · bulletins ~1,219 `/tsbs/<numeric-id>` leaves (the 189 bare `/tsbs/` listing routes are index tables) · articles ~450 · indexes ~2,450. The 559-record alldata stub tranche (501 of them `/tsbs/` leaves — the held EB drafts) carries raw mechanical bodies and normalizes INTO its forms through the queue; the sweep never wraps a raw body. The census disproved route-determines-shape three ways: leaf-route link-shells exist (an itype-21 `/nonstandard/` route rendering a "Related Links" list); strict link-purity under-counts indexes because kept breadcrumbs fail it; and the bulletin-adjacent bare routes (itypes 100/103/104/105/108/109/110/432/156) resolve to either an index list or FULL bulletin content depending on how many results the site's own filter matched — the classifier below is framing-tolerant and body-decided on purpose. Fleet validation also corrected three family priors (91 and 384 are reference/data tables → `document`, not procedure; 389 identification sheets → `document`, not article) and surfaced two conforming bulletin variants the contract admits: the regulator-format recall envelope (no issuer bulletin number — the campaign id is the tracked identifier) and the one-line supersession stub (envelope-only body; the contract carries `superseded_by` for it).

**The declared/swept split.** Route-keyed declarations (§7.2) cover only the shape-certain routes: `/tsbs/<numeric-id>` → `bulletin`; component landings (`/filter/`), itype-list routes, the vehicle root, and the selector itypes → `index`; the parts-and-labor itype → `document`. Everything else adopts by the sweep on body evidence — a wrong declaration is a standing gate failure, not a one-time miss.

**The sweep (`form-adopt-32`)**, mechanical under §12.19 step 4's measured-shortcut license ("measured against the real bodies first, never assumed"):

1. **Classify** — route prior (itype → family) + body-shape evidence (entry dominance → index; ordered-step spine → procedure; described-embed/table payload → document; prose-led → article), with a substantive-content veto both ways. Route/body disagreement resolves to the **body**; an unclassifiable record stays formless in the report, never force-stamped.
2. **Adopt** — wrap the content zone in the whole-record form section. The existing normalized body IS the conformed rendering: it was authored under the origin overlay's per-type tactics, which the contracts codify. A record the §12.19 manifest censused as `stub` (a grandfathered raw mechanical body) is NEVER wrapped — it classifies into the plan as queue work and normalizes into its form; the status manifest, not touch-signature heuristics, is the discriminator (touch signatures vary across normalize eras).
3. **Splice** — the §12.21 divergence manifest is the input: each record's dropped `title`/`description` lands on its new section header **verbatim** (the values were authored against exactly these bytes — this is the §12.21 relocation completed, not re-authoring, and the override mechanism stays unused). Records without a manifest row get header values only where a contract defines a mechanical composition (the index census line), else the header waits for the queue.
4. **Derive the bulletin envelope** — `bulletin_no` (+ date/supersedes/campaign id) extracted from the body's own printed identity lines; extraction rates measured fleet-wide before the run settle the fields' required-ness.
5. **Verify + manifest** — per-record checks (body bytes beneath the section opener byte-identical; spliced values == manifest values), `migration/form-adopt-32.jsonl`, whole-corpus lint finding-key set-diffs, and a **dry-run first**: the full proposed-adoption report is the owner's review surface before any record mutates.
6. **Ledger re-verify** — the sweep touch flags every cited binding (the §12.19.3 loud-flag discipline); quotes live in segment bodies the sweep never touches; `verify --stamp` re-binds.
7. **Declarations land WITH the sweep**, never before — a declaration without its stamped fleet opens thousands of standing gate failures (§8.5).

**Execution findings (2026-07-17)** — three gaps the sweep's own gates surfaced before any commit, all settled by drafting iteration: (a) §7.2's route-match target narrowed to the primary URI (see OQ3 below, resolved); (b) §4.3.2.2's `entry:` label admitted inside form sections — 3,779 of the 6,482 wrappable records (58%) carry authored leaf labels on content segments, which the top-level-only rule would have forced the wrap to drop (a genuine information loss: ~80% of sampled labels are real sub-block headings, DTC codes, and statuses, not duplicates), contradicting both the mechanical-path decision and §12.18's own don't-destroy-authored-labels precedent (the matching lint rule, `segment-entry-in-section`, retired with it); (c) the five generic contracts dropped their `monotonic` address check — the post-wrap lint gate measured 634 records (10%) whose faithfully-authored bodies present content out of `el=` order, because a generic span renders the SOURCE's presented order and `el=` is an extraction index, not a reading order (the ordered-axis forms — conversation, transcript, statement, receipt, slide-deck — keep theirs).

**Open questions**: (1) whether `form/index`'s `entry_count` earns its keep once census-composed descriptions exist; (2) the article/document boundary on mixed pages — adjudicated against real bodies, the classifier erring to `document` (the superset discipline); (3) *(resolved at execution, 2026-07-17)* alias-URI records whose aliases route to different shapes (the crawl-dedup fold): the execution's step-0 measurement found 24 wrapped records whose genuine `/tsbs/<numeric-id>` ALIAS would have mis-gated a non-bulletin body (repair-tip sub-articles the SPA also serves through a bulletin route), and 389 more through selector-route aliases — settled by narrowing §7.2's match target to the primary URI only (aliases are not gate-grade evidence); (4) the §12.21 divergence remainder outside alldata (the overlay-less export containers) — a separate, smaller arc.

### 12.23 The 3.3 terminal-forms migration (non-normative)

The migration story for the 3.2 → 3.3 contract change — deliberately the cheapest in the spec's history, because the amendment's central mechanism is **derivation, not stamping**: no record's bytes change.

Inventory at drafting (2026-07-17, private hub): 3,945 records — 141 formed, 3,457 rendered (grandfathered stored bodies, §12.19), 347 proxy. Of the proxy population, **~290 are containers** (199 iMessage per-conversation bundles, 42 osxphotos exports, 36 Discord channel exports, the takeout-family singletons) — all `disposition: manifest`, all therefore standing under `form/manifest` **the moment tooling implements the derivation**, zero declarations written. The remainder splits into: media/stream singletons wanting explicit `form: {id: passthrough}` mime defaults (`image/jpeg`, `image/png`, `audio/opus`, raw `video/h264`); records a rendering contract fits and will claim (tax slips, unrendered statements, promoted vcard cards — these stay `proxy`, correctly, until their forms land); and a small no-origin tail to be assessed.

Steps: (1) tooling — the fourth derived-state value (`terminal`), the disposition-derived `form/manifest` rule, the terminal pass-gate/no-op-drain semantics, the inverted lint check (stored rendering under a terminal contract), health's four-way split; (2) the passthrough mime-default declarations (a handful of schema keys, no record writes); (3) nothing else — openers are describe-pass work adopted on editorial demand, never swept. The 2,961-record iMessage queue mass is untouched: `form/conversation` is a rendering contract and gates normally. Verification: health's `proxy` count drops to the genuinely-awaiting population and the queue's standing demand becomes an honest signal; `ledger.md` v1.3 keys the enqueue signal to formless-for-now alone.

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **Corpus** | A content-addressed archive of captured artifacts. |
| **Record** | A markdown file with YAML frontmatter representing a single artifact. |
| **Artifact** | A captured file. Identified by the blake3 hash of its bytes. |
| **Transport** | The media-type-shaped container of a file. Also the name for the bytes-level hash field (`transport:`). |
| **Content** | What a transport carries. Decomposes into segments. |
| **Segment** | An addressable unit of content. Carries one atom, one address, and at most one atomic classification. |
| **Atom** | One of four **content** types: `text`, `image`, `audio`, `video`. A structural segment carries none — it is a mark, not content. |
| **Record body** | The markdown content below the frontmatter. Organized into three zones. |
| **Segment body** | The markdown prose inside a single `text`-atom segment block. |
| **Zone** | One of three partitions of the record body: metadata, content, annotations. |
| **Artifact block** | `<!--artifact <mime-type>-->` — exactly one per record. Opener arg is the authoritative media-type declaration. |
| **Origin block** | `<!--origin [<id>[/<subtype>]]-->` — one or more per record. Carries `uri:` and `snapshot:`. |
| **Embed block** | `<!--embed <mime-type>-->` — content-addressed asset metadata. Deduplicated by `transport:`. |
| **Section block** | `<!--section <form-id>-->` — a **form span**: a positional span of the content zone carrying a named structural form and its codebook fields. Depth one, never overlapping. *(3.0: the 1.0–2.x TOC-grouping role is retired — see Structural segment.)* |
| **Segment block** | `<!--segment <atom>-->` — the body's content atom. |
| **Structural segment** | `<!--segment structural-->` — a body-empty **byte-mark**: the source's own declared boundary (heading, outline entry, chapter, topic) at an address, with `level:` and optional `entry:`. The TOC is a derived rendering over these marks. |
| **Context block** | `<!--context <namespace>/<id>[/<subtype>]-->` — an annotations-zone observation (namespaces: `issue`, `reference`, `relation`, …); record- or segment-scope (via `address:`). |
| **Namespace** | One of `mime`, `origin`, `form`, `atom`, `context`. Each is a schema axis or umbrella with its own block-keyword role. |
| **Form** | The fourth classification axis (3.0): a **rendering contract** — an expectation for how a set of bytes is faithfully represented in a markdown shape (`conversation`, `statement`, `receipt`). Declared by a `form/` overlay; bound on a section opener; names shapes, never subjects; a goal for the right artifacts, never a default (3.1, §7.8). |
| **Formless (the zeroth form)** | The identity contract (3.1): the faithful representation of the bytes is the bytes, delivered through derivation ops. Valid indefinitely; prescribes nothing about what the artifact is. |
| **Proxy** | A record's universal role from birth (3.1, §4.1): the attested, consumable stand-in for its artifact — complete without any stored rendering or vouch. |
| **Formed** | Derived state predicate (3.1): a form section governs the record's stored content zone — a stored rendering under a named contract. *(3.2: the section header also carries the interpretive editorial fields where authored — the vouch's home.)* |
| **Authored / Vouch** | *(retired 3.2)* The 3.1 predicate — frontmatter title/description non-empty — dissolved into the form layer: interpretive editorial fields ride the form section header (§4.3.2.1), and record-level title/description are **derived** from role-marked fields (§4.2.3). "The authored layer" survives as an ownership name (what the normalize pass writes, §4.4.7). |
| **Derived editorial fields** | *(3.2)* A record's display title/description, computed — never stored — from role-marked fields by precedence **artifact → origin → form** (frontmatter override strongest, latest block wins within a layer; §4.2.3). |
| **Role-marked field** | *(3.2)* An `extended_fields` declaration carrying `role: title` or `role: description` — an editorial candidate for the derived title/description (§4.2.3). Declared on mime schemas, origin overlays, and form contracts; the section header's `title:`/`description:` are implicitly marked. |
| **Codebook** | A list field on a form section's header that envelope segment fields index into (e.g. `participants:` ↔ `participant: 2`) — derivable from the span's own bytes, entry grammar `<display> <durable-id>`. |
| **Provenance** | On a context block (§4.4.6): `provenance: auto` = engine-stamped (a detector or overlay-declared emission), stripped and regenerated on re-run; absent or `asserted` = human/normalizer, never auto-touched. |
| **Self-contained** | The universal container principle: every transport produces a single record (lifting nested-stream metadata when present). A raw archive is attested as an embed manifest of its members. *(2.1: the former schema-declared `decomposable` disposition is removed.)* |
| **Container / member** | A container is an artifact whose content is other transports (an archive); a member is one such contained transport, declared as a content-addressed embed on the container's record. |
| **Member / Unit** | A member is a transport with its own MIME and standalone byte identity (a manifest or exposable embed, promotable). A unit is content *within* one transport, reached by unit ops (`turn=`) under a form mapping — never an embed. |
| **Promotion** | Minting a first-class record for a container member without copying its bytes: the promoted `id` is the member's blake3, resolved by streaming through the container (§2, §8.1). |
| **Disposition** | A mime schema's declared container-vs-transport judgment (§7.1, §1.2): `manifest` — the members ARE the content — or `work` — one transport whose internals surface as exposable embeds. Declared (origin-overridable), auditable, never sniffed per record. Distinct from the 2.1-removed `artifact_kind` (nothing explodes at ingest). |
| **Exposable embed** | An internal member file of a `work`-disposition transport, attested as addressable and promotable without being the content (a PDF's embedded file at `attachment=<N>`, a docx's pasted photo) — versus a **manifest embed**, whose members ARE the content. |
| **Attestation** | Ingest-stamped byte-facts: artifact fields, manifest/exposable embeds, structural byte-marks, sidecar lift. Deterministic; stripped + regenerated by re-attest. |
| **Derivation op** | A resolver operation deriving mechanical content from the artifact (`body`, `members`, `transcribe`, `turn=`) — on-demand, cacheable, pure or version-labeled (§6.4). |
| **Shaper** | Deterministic normalize tooling that authors a record's stored form from a declared form mapping — the mechanical half of the one authoring pass. |
| **Lineage-chained resolution** | Read-time materialization of content a record's bytes declare but do not contain, through the record's containment-lineage parent (§6.2). Derived, never stored. |
| **Default-member resolution** | Read-side sugar (§6.2): a bare op routes to a container's sole member of the required kind, or its declared primary (`pitm`); ambiguity fails loudly. Citation-safe by content-addressing; attested embeds keep explicit addresses. |
| **Member re-chaining** | §6.2: a `path=`-extracted member re-detects its own mime and, when a further transform follows, re-enters the working-kind table for it (a PDF member takes `page=`/`text`); a terminal `path=` never promotes to a full working-kind object (no silent re-encode) — it only decodes an already-textual member (JSON/text) to text; an unrecognized member stays raw `bytes`. |
| **Muxing contract** | §6.2's normative behavior for media cuts and conversions: composition cuts via per-kind default members (subtitles opt-in), composable stream selection (`stream_id=0,2`), ordered multi-cuts (`time_range=a-b,c-d` → concatenation), precise-by-default cut semantics (`cut=copy` the disclosed keyframe-snapped path), `format=` conversion (encoding only, atom-compatible, implementation-defined token set), pinned order select→cut→convert→size. Behavior normative, mechanics resolver-owned (maps onto ffmpeg primitives — the `fit=` precedent); results are version-labeled ephemeral renderings, never new artifacts. |
| **Capture, Ingest, Normalize** | Pipeline stages. *(3.0: draft retired — its duties split into ingest attestation, derivation ops, and the normalize pass.)* |
| **Stub** | *(retired 3.1)* The 2.x–3.0 name for a just-attested record — now simply the record at its attested baseline, the artifact's proxy (§4.1). Survives in the `re-stub` verb name. |
| **Normalized** | *(retired 3.1)* The 2.x–3.0 citable status — dissolved into *formed + authored* (§4.1), then into *formed* alone when 3.2 retired the authored predicate; citability re-keys to verifiable surfaces (`ledger.md` §13.2). |
| **Touch** | A single processing pass. Recorded in `touch[]`. |
| **Touch chain** | The ordered list `touch[0..N]`. Records current-shape provenance; reset by re-stub (§8.4). |
| **Re-stub** | A deliberate reset that discards body and accumulated metadata, leaving only byte-intrinsic state and the touch chain. See §8.4. |
| **Resolver** | The corpus-provided mechanism that materializes a functional URI to a deterministic result. |
| **Functional URI** | A `corpus://<hash>?<params>` URI naming a derived view. |
| **Derived view** | A computed aggregate over body blocks / semantic-tagged fields. |
| **Semantic type** | One of seven closed-vocabulary tags on schema-declared fields. |
| **Transport hash** | `transport:` — the bytes-level hash of the file. Encoded as `<algo>:<hex>`. |
| **Canonical hash** | `canonical:` — the canonicalized-content hash. *(Currently not persisted — disabled 2026-06-28, see §7.1.)* |
| **Perceptual hash** | `perceptual:` — atom-canonical content fingerprint. |

---

## Appendix B: Content types (non-normative)

A curatorial vocabulary for the content **sources** a corpus is expected to hold, and how each maps onto the model. These are planning terms, not schema fields: they inform capture planning, and become ledger types (`ledger.md` §8) wherever a distinction is worth recording.

### B.1 Source taxonomy

| Family | Kinds |
|---|---|
| **Website** | news article · forum post / thread · opinion / editorial · blog post · reference article (Wikipedia / wiki) |
| **Print** (physical / electronic) | fiction · non-fiction · textbook · reference manual · script / screenplay · research paper |
| **Audio-visual** | video (e.g. YouTube) · podcast · television · feature film · documentary |

### B.2 How a content type lands in the corpus

There is **no per-content-type metadata schema** and no "document kind" field. A content type expresses itself through four orthogonal mechanisms:

1. **MIME type** (`mime` namespace, §7.1) — the artifact's media type (`text/html`, `application/pdf`, `application/epub+zip`, `video/mp4`, …) selects the attestations, the derivation ops, the addressing scheme, and the canonicalization strategy. A "research paper" is just an `application/pdf` artifact; a "blog post" is `text/html`.
2. **Form** (`form` namespace, §7.8; 3.0) — where a rendering contract fits the content (a conversation, a statement, a document), a form span declares it — shape only, never subject; formless (the zeroth form) where none does or none is yet adopted (3.1).
3. **Ledger assertion** (`ledger.md`) — *what kind of thing* an artifact documents, and any domain signal worth recording (e.g. a `peer-reviewed` / `preprint` credibility signal), is asserted as typed claims whose evidence cites the record — minted mechanically by harvest rules where membership is deterministic (`ledger.md` §10). This replaces per-document enum metadata fields entirely. *(1.0 expressed this as corpus-side composite classifications.)*
4. **Origin** (`origin` namespace, §7.2) — capture provenance: source URL(s), capture timestamp, per-host capture recipe. "Where it came from" lives here.

Backlog growth, grooming, and prioritization of what to capture are **curatorial** concerns owned by the layers above the corpus — the ledger's needs and coverage gaps generate ingestion demand (`ledger.md` §7, §9) — not corpus-pipeline stages.
