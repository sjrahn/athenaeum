---
spec_id: ATH
part: II
title: "Athenaeum Specification — Part II: The Corpus"
version: 38
status: current
license: "CC BY-SA 4.0"
date_created: 2026-02-08
date_modified: 2026-08-21
---

# Athenaeum Specification — Part II: The Corpus

Amendment history — including the closed ATH-CORPUS line (2.0–3.14) and the numbered migration narratives this document once carried — lives in [`CHANGELOG.md`](CHANGELOG.md) and in git history. This text carries current law only. The record grammar below is the declared final shape (the 3.12 freeze): amendments are exceptional rather than iterative, and one lands only as a complete change — the normative text, the sweep of every enforcement and guidance site, and the fleet migration story, together (Part I §8).

# The contract (normative)

## 1. Overview

### 1.1 What this is

A **corpus** is a content-addressed archive of captured artifacts, accessed through faithfully represented markdown proxies called **records**. Artifacts are deconstructed into addressable segments and rendered to text losslessly, or — where no lossless rendering exists — marked in place so the bytes themselves are one resolve away (§4.3.2.2). A record classifies its artifact **mechanically** — what the bytes are (media type) and where they came from (origin); what the content *means* is the ledger layer's concern ([`ledger.md`](ledger.md)), asserted there as claims whose evidence points back into the record.

A record is a single markdown file. The YAML frontmatter at its head carries a small bytes-identity header — what these bytes ARE (the blake3 identity, plus any stored byte-stable hashes — §2's residency rule) and the provenance chain of processing passes. The **record body** below the frontmatter is organized into three **zones**: a **metadata zone** declaring what the artifact is, where it came from, and what members it carries; a **content zone** carrying the rendered content as sections and segments; and an **annotations zone** carrying observations about the record. Each zone holds a small set of HTML-comment block families; §4.3 specifies the grammar.

### 1.2 The transport model

Every captured file is a **transport** — a media-type-shaped container — that carries **content**.

- A transport's **intrinsic information** surfaces in the record's metadata zone — primarily in the artifact block for transport-intrinsic fields.
- A transport's **content** decomposes into a flat sequence of addressable segments in the record's content zone. Each segment carries one of four **content atoms** (text, image, audio, video) — or is a **structural segment**, a body-carrying byte-mark with no atom (§4.3.2.3), or a **placement** (§4.3.2.4) — and an **address** indicating its location inside the transport.
- Every transport is **self-contained**: it produces a single record. When it contains a **nested transport**, it lifts that nested transport's intrinsic metadata into the outer record's artifact block and addresses its content per stream / per member, while an asset it merely references is rostered as a member row in the metadata zone. An ordinary single-content file (a plain HTML page, a PDF) simply has no nested transport to lift. A **raw archive** — a transport whose content is *other transports* — is attested as a **members roster**: every member becomes a content-addressed row (the member's `transport:` byte-hash + its member address) and the content zone stays empty (§12.4).
- A declared member is thereby **promotable**: because its member row records byte identity and address, it may later be minted as a first-class record of its own (**promotion**, §8.1) without its bytes ever leaving the container — a lookup of the promoted `id` streams them out through the container's address scheme (§2). Containment nests (a promoted member may itself be a container), and **residence is invisible**: the same bytes may live standalone, inside a container, or both, and no record changes when they move (§2, Part IV).
- **Container-vs-transport is a declared judgment, not a derivable fact.** The bytes cannot say which they are — a `.docx` is *provably* a zip, and reading it as one would be wrong. A mime schema therefore declares a **`disposition:`** (§7.1): **`manifest`** — the members ARE the content (archives, mailboxes, multi-entry text containers, media containers): the content zone holds only the container's own byte-marks, and every member is attested as a **manifest member**, promotable; or **`work`** — one transport whose content decomposes as units, and whose internal member files surface as **exposable members**: addressable and promotable, but *not* the content — a `.docx` is better read as one work; its pasted photo is an exposable member, its `word/document.xml` is not independently meaningful. The authoring criterion, normatively: **are the members independently meaningful transports?** An MKV audio track is — the transcript lives on it; OOXML internals are not. The mime schema declares the format's default; an origin overlay MAY override it for a producer whose use of the format deviates (§7.2). The disposition is always stamped and auditable, never sniffed per record. Nothing explodes at ingest under either value.
- **The member-vs-unit rule.** A **member** is a transport with its own MIME and standalone byte identity — attested as a row of the record's members block per the disposition, manifest or exposable, promotable either way. A **unit** is content *within* one transport — a message in a chat transcript, an entry in a log — reached by unit ops (`turn=`, §6.2) under a form mapping (§7.2), never rostered as a member. Unit-structured single transports are **not containers**: an NDJSON/JSONL stream, a location-history JSON, a health-export XML/CSV, a GPX track decompose as units of one work (`form/log` territory, §7.8), not as members.
- A **multi-track media container** (MP4/ISOBMFF, Matroska, and kin) is a raw archive in the strict sense — a transport whose content is other transports — and is attested the same way: a **track manifest**. Each elementary stream becomes a content-addressed member row addressed `stream_id=<id>` (video stream, audio stream(s), text-based subtitle track(s)), and an attached picture is an ordinary member row; the member's *bytes* are **the raw elementary stream** — the codec payload in decode order, exactly as the container's own sample tables lay it out (§2, the payload-identity principle): extraction is a pure function of the container bytes, computed by the corpus's own engine-free table reader, so the member id is stable across every tool version **by construction** — no muxer, no framing, no engine in the identity path. `corpus://<leaf> ≡ corpus://<container>?stream_id=<n>` is an identity equation, verifiable by re-derivation (§2); a raw payload is deliberately not a playable file (parameter sets and timing live in the container's tables — §2), and every playable rendering is a derived, version-labeled surface (the muxing contract, §6.2); the artifact block carries the container facts (duration, per-stream codecs, dimensions). The content zone carries exactly one thing: the container's **chapter marks** as structural segments (§4.3.2.3) — chapters are byte-marks of the *container* (an MKV `Chapters` element, an MP4 chapter track; both encodings project to the same marks, the mime schema pinning which encoding wins), marking the shared timeline no single track owns. Tracks are **promotable on demand, never exploded**: a promoted track record's bytes materialize through the container (`stream_id=` transform), no bytes copied; extraction semantics are the payload rule itself (the mbox `msg=<N>` precedent, now with nothing to pin — a table-driven concatenation has no producer to attest). The audio-track record owns the transcript (`?transcribe`, §6.2); the video-track record owns frame work (on-screen text as `text/ocr` is faithful — sweepable to exhaustion per band, §4.3.3.6; what a frame *shows* is not recorded at all — the frame marker stands for it, §4.3.2.2); a text-based subtitle track projects faithfully as (time_range, text) segments. Tracks inherit the container's chapter marks at **read time through lineage** (§6.2) — never copied, because the track's own bytes do not carry them (§4.3.2.3, the byte-mark rule). A **single-stream artifact** (a bare MP3, a JPEG) has no member transports to declare and stays a single `work`; a single-*track* media container is an **ordinary one-row manifest** *(v32 — payload identity dissolved both of the old objections: the roster row names the payload, not the container, so no second identity for identical content is minted, and the track's own work has lived on its leaf since the container/leaf split)* — its one track promotable on demand like any member, with `corpus://<leaf> ≡ corpus://<container>?stream_id=0` making the container and its stream interchangeable names for one content, which is what a wrapper being packaging *means*. **The container-vs-leaf judgment is made from containment lineage, never from a roster-row count**: what separates a leaf from a container is the positive fact promotion writes and attestation never does — an origin `uri:` of `corpus://<container>?stream_id=<n>`. A standalone single-track capture, having no such lineage, keeps whatever its mime declares. **Default-member resolution** (§6.2) makes the bare op transparent either way (`?transcribe` on a single-audio MKV needs no `stream_id=`) — transparency is a property of *addressing*, not a reason to call a leaf a manifest. The general rule holds regardless of medium: a **pure envelope** — a transport with no content of its own (zip, tar, gzip, a single-track media container chief among them) — decomposes to nothing once it holds exactly one member; that member is promoted and the envelope is treated as packaging. *(v32)* For a **compressed** single-member envelope whose payload is standalone-parseable (a gzip'd text file, a one-file zip), packaging-not-identity applies at **ingest**: the record minted is the *payload's* — id = the unwrapped bytes' blake3 — with the envelope's transport hash attested in `hash:` as delivery provenance (the §12.3.13 "bytes deliberately not retained" precedent) and the payload stored as the artifact. The same content delivered bare or wrapped thus mints the same record — the wrapper never forks identity. **"Single-member" is a physical fact of the archive's entry list, never of an exposable roster**: an overlay's judgment about which entries a members block exposes is revisable presentation, and identity may not hang on revisable state — an archive physically holding a second file (a metadata sidecar an overlay hides) is not an envelope-of-one and does not collapse; a schema wishing to declare such a sidecar *discardable packaging* (the §12.3.13 mold — hash attested, bytes not retained) is a named extension point, a deliberate declaration this rule does not infer. Likewise a zip carrying its own declared content in the archive comment (a role-marked `comment`) is content-bearing and never collapses. A single-track *media* container is the one envelope whose wrapper IS retained (its tables carry the timing and parameters its payload deliberately lacks — §2), so it lands as the one-row manifest above rather than collapsing; either way no identity keys on wrapper bytes. A **content-bearing** container — HTML, `message/rfc822`, a media container carrying its own chapter marks — never reduces to its member regardless of count: member count says nothing about whether a container is reducible, only a declared mime-schema property does. The same-video composition — tracks threaded over the shared timeline — is a read-time derived view joining on (lineage, time), exactly as a cross-platform conversation view joins on (ledger identity, time): same tuple, same composition layer, no media-specific logic stored anywhere.
- The manifest family extends along two more axes, no new machinery. **Multi-entry text containers** are the mbox precedent generalized: a multi-card VCF is a manifest of `text/vcard` members at `card=<N>` (`BEGIN:VCARD`/`END:VCARD` delimiter-pinned extraction, so member bytes are deterministic and promotable — §12.11), an ICS calendar of `VEVENT` entries at `entry=<N>` likewise. **HEIF/HEIC** is the media container on the image axis: image items attested at `item=<id>`, and an Apple **Live Photo** is the container's *declared primary* still (the `pitm` primary-item box — a byte-fact) plus its paired video track, both reachable bare through default-member resolution (§6.2): `bbox=` acts on the declared-primary still, `time_range=` reaches the motion component. A **motion photo** (an MP4 appended inside a JPEG's bytes) is the nested-transport lift above — the inner video attests as an embedded transport of the JPEG work — not a new mechanism. Formats that arrive later slot into the same strategies: 7z/rar/dmg join the zip-manifest family, PST/OST and WARC join the mbox precedent, when a real capture wants them.

### 1.3 The atom / segment model

A record body's content zone is a sequence of **sections** (form spans, §4.3.2.1 — present only where a form is declared) and **segments** (the read-order rendering). Each content segment carries:

- One **content atom**: `text`, `image`, `audio`, or `video`. Only `text` segments carry a segment body. Segments of the other three atoms are positioning markers — they declare where in the reading order a region of *this* transport appears, materialized on demand through the resolver — and their segment body is empty. (An asset that is itself a transport, and so has a member row, is positioned by a **placement** instead — below.)
- An **address** specifying the segment's location inside the transport, in a scheme determined by the media-type schema. Addresses compose, so that chains can form from transport to atom to region (a region within a frame within a video). **Optional** — an absent address names the whole transport (§4.3.2.2).
- Exactly one **atomic classification**, declared on the opener line in the form `<!--segment <atom>/<id>-->` (or bare `<!--segment <atom>-->` for unclassified-but-typed segments). Text-atom overlays may declare lossless-shaping behavior — those overlays shape the segment body into a specific lossless form (a markdown table, a transcript, a chat message). When multiple representations apply to the same source region, each becomes its own segment.

A fifth segment kind — the **structural segment**, `<!--segment structural-->` (§4.3.2.3) — carries no content atom: it is a **byte-mark**, the faithful record that the source itself declares a structural boundary at an address (a heading, an outline entry, a chapter mark, a topic boundary), with a `level:` and the mark's own text in its **body**, rendered faithfully like any other content; an empty body is an unlabeled boundary. The table of contents is a **derived rendering** over these marks — arbitrary depth, zero nesting grammar — never a stored grouping.

A sixth — the **placement**, `<!--segment placement-->` (§4.3.2.4) — likewise carries no atom and no body: it records that a **member** (§4.3.1.4) sits at this position, and nothing else. What the member contains is its own record's to say, reached by the blake3 its roster row already carries; placing one is what obliges promoting it (§8.1). The two content-less kinds are symmetric — a mark points at a boundary the source declares, a placement at bytes the roster names — and both exist for what they withhold.

Two segments may share an address as long as their opener-id differs — same-region stacking is how a record represents multiple valid lossless representations of one source region (a structural mark stacks with the content segment at its address the same way). Segments are addressable from outside the record via functional URIs that carry the segment's address in their query string (§5).

### 1.4 Lifecycle

```
captured bytes              (no identity yet — staging only)
       │
       │ ingest             deterministic: hashes, MIME detection, byte-fact ATTESTATION
       ▼                    (artifact fields, manifest members, structural byte-marks, sidecar lift)
    record                  the artifact's PROXY — identity + attested facts; bytes persisted;
       │                    complete and consumable at birth: formless, the zeroth form (§7.8),
       │                    readable through the resolver's derivation ops (§6.2)
       │ normalize          the ONE authoring pass, demand-driven (§8.5): renders the record
       ▼                    under a NAMED form contract — a mechanical shaper where a declared
     formed                 mapping makes the shape deterministic, an interpretive agent where
    record                  not — the form span's header carrying the fields its form declares.
                            The preferred citation surface (ledger.md §6.3)
```

Once ingested, the artifact's bytes must remain retrievable by id. Where and how they are stored is the custody plane's concern (Part IV); the contract is that a lookup by id produces the bytes. **Promotion** (§8.1) is a second entry point: it mints a record for a container member's bytes, which are already retrievable by id through the container (§2) and are not copied. Re-running any stage is an expected refinement pattern, not a fallback; every stage from ingest onward appends a `touch[]` entry to the record's provenance chain (which `re-stub` may reset, §8.4).

There is no stored lifecycle field and nothing is pending by default: a record with no stored rendering is not an unfinished stub but the artifact's proxy, complete at birth. The lower box of the diagram is where a record goes when a rendering contract or a consumer's demand takes it there — not where every record is headed (§4.1).

### 1.5 Design principles

1. **Layered foundation.** The corpus is a foundation layer — the truth, the baseline. It depends on nothing; any system that builds atop it depends on the records it produces.

2. **Content addressing.** Every artifact's identity is the blake3 hash of its bytes. Bytes don't change; if they did, the hash would change and the record would be a different record.

3. **Faithfulness.** A record body is a faithful, lossless rendering of the transport's content. Normalization may resolve ambiguity (encoding, broken layout, OCR for scans) but never adds information not present in the source. Descriptive content (a summary of what an image shows, a paraphrase of what was said) is lossy by definition and has **no home in a record at all** — not the body, not a header field, not the annotations zone. Where a region has no lossless rendering the record marks its address and stops; summary is a query, answered one layer up by the ledger's claims over the record's verifiable surfaces (§4.3.2.2). Re-segmentation is structural, never editorial. The same principle governs structure: a **structural segment exists only where the source carries the mark** (§4.3.2.3, the byte-mark rule). A grouping the bytes do not declare — a conversation's per-day break: whose midnight? — is a *read-time rendering* with explicit parameters, never a stored block.

4. **The record body as universal representation.** Every artifact carries a markdown body composed of segments. This projects every modality — text, image, audio, video — into a common representational space. Search, similarity, and embeddings all operate on the body.

5. **Transports declare, content fills.** Format-specific machinery (address scheme, attestation set, derivation ops) lives on the media-type schema. Content-shaping tactics live on origin overlays (per source), **form overlays (per record-scope shape, §7.8)**, and atom overlays (per segment-scope form). The layers don't bleed: an origin overlay that specifies segment decomposition is a category error — it names *where bytes came from* and maps the producer's format onto a form; the form overlay owns the normal form.

6. **Deterministic before LLM.** Capture and ingest are scripts; every mechanical extraction is a **resolver derivation op** — a pure (or version-labeled, §6.4) function of the artifact; and the normalize pass is authored by a mechanical **shaper** wherever a declared form mapping makes the shape deterministic, by an LLM only where judgment is genuinely required. The boundary survives as *who executes*, recorded pass-by-pass in the touch chain (§4.2.2) — not as a lifecycle stage. Interpretation — what content means — is not a corpus stage at all: it happens in the ledger, with evidence citing back into the record.

7. **On-demand derived views.** Cross-cutting aggregates and richer modal projections are computed by walking body blocks and semantic-tagged fields, or by resolving functional URIs — never persisted alongside the record.

8. **Stable identity, mutable metadata, faithful body.** A record's `id` is fixed at capture. Body blocks evolve as attestation and normalization improve; the body content remains faithful.

9. **Offline-first.** Only `capture` requires network access. Ingest, normalize, and URI resolution — including every derivation op — all operate on local data.

10. **Frontmatter is bytes-identity only.** What the bytes ARE (their hashes), how visible they are to authoring tools, how to navigate the provenance chain. Everything else — the title candidates, media-type, origins, issues, extended fields — lives in body blocks because everything else came from a schema decision, and schema decisions are auditable per-block. The display title/description follow the same rule: they are **derived** from role-marked block fields (§4.2.3), never stored. A field is named **bare** when its block opener already identifies its provenance: an artifact block names the format (its MIME), a context block names its namespace (`<namespace>/<id>`), so their fields are `title`/`author`/`severity`, never `pdf_title`/`issue_severity`. A provenance prefix survives only where the opener does *not* carry it — an origin block's `ytdlp_title` (the opener names the source record, not the extraction tool), or a metadata sub-standard the format embeds (`exif_*`, `og_*`).

11. **Classifications are derived, not declared.** A record's classifications list is computed by walking its body — the artifact block yields `mime/*`, qualified origin blocks yield `origin/*`, **qualified section openers yield `form/*`**. The body IS the classification declaration. The same principle applies to issues and to the aggregated URI, timeline, and identifier views (§9).

---

## 2. Identity

Every artifact is identified by the blake3 hash of its bytes — a 64-character lowercase hex string. This identifier is the record's `id` and the lookup key by which the corpus's custody plane produces the bytes (Part IV). The custody plane owns where and how the bytes are stored; the contract is that an `id` resolves to its bytes.

An id need not resolve to a *standalone* file. When a captured container's record rosters a member as a content-addressed row (the member's `transport:` hash with a resolvable member address), that member's bytes are retrievable by their own blake3 **through the container**: the implementation streams them out via the container's address scheme, recursively when containers nest. How the route from a bare id to its container is found is implementation-defined, but it MUST be **derived** from the records' members-block rows — never stored on the promoted record (§12.9) — so bytes may move between standalone residence and containment, or be resolvable by several routes at once, without any record changing. Every route to an id yields identical bytes by construction; a resolver may take any. The full route inventory — store locations, attached trees, presented manifests, remote hydration — is Part IV.

**The payload-identity principle** *(v32)*. A member's identity bytes are the **fully-unwrapped payload** — the content as the container stores it, with every wrapper removed: for a media track, the raw elementary stream in decode order, exactly the sample bytes the container's own tables lay out; for a compressed envelope's member, the decompressed bytes. Wrappers — a mux envelope, a compression layer — are **residence forms**, never identity. The asymmetry that forces this is not stylistic: *unwrapping* is a pure function of the container bytes (a table-driven sample concatenation, a fully-specified inflate — computable by an engine-free reader, identical under every tool version by construction), while *wrapping* is engine work whose output shifts across tool versions even under pinned invocations — measured live, `-bitexact` included. An identity that keys on wrapped bytes therefore strands its own records when the wrapping tool moves; an identity that keys on the payload cannot drift, because there is no engine anywhere in its derivation.

Two consequences are load-bearing. First, the **identity equation**: `corpus://<member-id>` and `corpus://<container>?<member-address>` name the same bytes *provably* — `blake3(payload(container, address)) == member-id` is checkable by re-derivation, so the paragraph above's "every route yields identical bytes by construction" is not a design intention but a verifiable invariant, and a promoted member record needs no standalone bytes at all. Second, a raw payload is deliberately **not a playable or standalone-parseable file** — a video payload's parameter sets and every track's timing live in the container's tables — and does not need to be: resolution routes through the container (§6.2), and every playable or framed rendering is a **derived surface** (the muxing contract) with the standing of a `page=` raster, version-labeled and cache-resident, where engine drift is harmless precisely because no identity hangs on it.

The `id` field is bare hex with no algorithm prefix because the algorithm is invariant. All other hash fields in the spec use an `<algo>:<hex>` prefix encoding (§7.6) so that multiple hash families can coexist within one field.

**Hash residency.** Every stored auxiliary hash lives in one frontmatter field — `hash:` (§4.2.1) — and its **tag** carries its class (§7.6, §7.9): a bare algorithm id (`sha256:`, `md5:`) is a **byte-stable** value, a `<procedure>@<version>` tag (`eml-stripped@2.1:`) is a **procedure-versioned** one. What may enter the field, and when, splits by that class — the question is never "could we recompute this?" but "could recomputing it ever produce a different value?":

- A **byte-stable** hash — a pure function of the exact bytes under a fixed public algorithm (`sha256`, `md5`, a blake3 prefix rung) — can never drift, so the record is its natural durable home: written once, true forever, churn-free after the write. Storing them is not merely permitted but *smart* — the record is git-tracked and travels with every clone, so a stored byte-stable hash survives store migrations, remote-store outages, and index loss, and is the recovery clue for a record whose bytes are lost. Its tag is the algorithm, which is also its verification affordance: anyone holding candidate bytes can check them against it. Write points are bounded to keep churn at zero in the steady state: **at ingest** (bytes and record both in hand — the free moment) per the declared recipes (§7.9), or later by a **deliberate flush** (§12.9.1) — never as a side effect of any other pass.
- A **procedure-versioned** hash — one whose value depends on an evolvable procedure, not the bytes alone: a canonicalized identity (the stamp-strip can be refined), a perceptual fingerprint (implementations vary) — is **index-first** (§12.9.1). An **identity-class** value (§7.9's comparison axis) MAY be flushed into `hash:`, always under its `<procedure>@<version>` tag: the tag deliberately names the procedure and NOT the digest algorithm inside it (§7.9), and a tagged value never lies — it states exactly which procedure produced it — so a recipe revision makes stored values *visibly superseded* (lint-flaggable, deliberately re-flushable) rather than silently wrong. A **similarity-class** value (a fingerprint) is never flushed at all — records store identities, and equality on a similarity value claims nothing (§7.9). Neither is ever written automatically, at ingest or anywhere else.
- The **derived hash index** (§12.9.1) is the query layer over both classes and the sole automatic destination for procedure-versioned values. It is deployment state: regenerable, never authoritative — nothing normative may depend on it existing, and a consumer missing a row recomputes it *when the bytes are in hand* or reports it unindexed, never fails.

Unchanged by this rule, because they attest what no recompute could produce: the **members roster's `transport` rows** (the §2 resolution route, stored for §12.9's one-pass economics) and any hash of **bytes the corpus deliberately does not retain** (a canonicalized mailbox's pre-strip `source_transport`, §12.3.13).

---

## 3. Schema namespaces

A corpus's schemas are organized into five spec-reserved **namespaces**. Four are primitive **axes** — each bound to a single block-keyword role in the record body — and one is an umbrella: `context` for annotations:

| Namespace | Role | What it declares |
|---|---|---|
| `mime` | Declares the **artifact block**. | Per-media-type fields, address scheme, ingest attestations, derivation ops. |
| `origin` | Declares the **origin block**. | Per-source-of-retrieval overlays: how to recognize an origin, what additional fields it contributes, how to capture it, **which form its records carry and how the producer's format maps onto it**. |
| `form` | Declares the **form id on a section-block opener**. | Per-record-scope-shape overlays: the normal form a span of content decomposes into — envelope contract, codebook fields, conformance checks (§7.8). |
| `atom` | Declares the **atomic classification** on a **segment block**. | Per-atom-and-subtype overlays: what *form* of content a segment carries, and (for text-atom overlays) whether it licenses a shaped lossless body. |
| `context` | The umbrella for every **annotation** namespace — observations *about* a record. | Per-namespace overlays declared via the **context block** (`context/<namespace>/<id>`). Two namespaces: `issue`, capture-fidelity problems, and `sweep`, extraction-exhaustion declarations (§4.3.3). |

The retired `composite` umbrella — record-scope interpretive classification — **stays retired**: what content means is knowledge, and knowledge lives in the ledger (§7.4). The `form` namespace is not its return — it declares structural *shape*, checkable against the bytes, never subject or meaning (§7.8).

A record references a schema by the qualified id encoded on a block opener — for example, `<!--context <namespace>/<id>-->`. The schema loader resolves the id by walking a chain of declarations from most-specific to least-specific:

1. The subtype-overlay declaration (`<namespace>/<id>/<subtype>`), if a subtype is present on the opener.
2. The id declaration (`<namespace>/<id>`).
3. The id's parent declaration, if the id is itself two-part within the namespace (applies in the `mime` and `atom` namespaces where ids decompose into axis + subtype, such as `mime/text/html` or `atom/text/data-table`).
4. The namespace's universal declaration.

Each layer's declared fields extend its parent's; conflicts resolve in favor of the most-specific declaration.

The on-disk organization of these schemas is implementation-discretionary; a reference layout appears in the implementation guide (§12.2).

---
## 4. Records

### 4.1 What a record is

A markdown file with YAML frontmatter. The frontmatter carries the bytes-identity header; the record body carries the schema-derived metadata blocks AND the segmented rendering of the transport's content AND any annotations.

A record is **born complete**. Ingest (or promotion) attests the bytes' identity and facts, and from that moment the record is the artifact's **proxy**: bytes retrievable by id (§2); artifact block + **attested byte-facts** emitted — the mime schema's declared attestations (artifact fields; manifest members for archive/mail/media-container types; structural byte-marks; sidecar lift); first origin block populated from capture / containment context; fully *readable* — its mechanical body is a resolver derivation (§6.2), computed on demand, cacheable by a search index (§9), never persisted to the record. Everything beyond attestation is layered on when it earns its place, and every layer is **self-evident in the record's own bytes** — there is no stored lifecycle field summarizing them:

| Layer | Present when | Written by |
|---|---|---|
| **attested** | always — the universal baseline above | ingest / promote (§8.1); refreshed by re-attest (§8.3) |
| **formed** | a **form section** (§4.3.2.1) governs the record's stored content zone: the record carries a stored **rendering** of its content under a named rendering contract (§7.8) | the normalize pass — a mechanical shaper where a declared mapping applies, an interpretive agent where not (§4.4.6) |
| **terminal** | a **terminal contract** (`form/passthrough` / `form/manifest`, §7.8) governs the record — declared at overlay grain (mime/origin `form:`; or derived: `disposition: manifest` with no rendering contract declared) or asserted per record (§4.4.6) — and the record **deliberately stores no rendering**: the artifact (or its attested members) is the terminal representation | the declaration (an overlay key — no record write) |

Three consequences carry the model:

- **Formless is the zeroth form.** A record with no form section is not pending — it is the artifact's proxy under the **identity contract** (§7.8): the faithful representation of the bytes is the bytes, delivered through the derivation ops, prescribing nothing about what the artifact is. Most artifacts a corpus consumes as raw context — code, datasets, media, containers — live here permanently and correctly. A formless record is upgraded to a named form when one is identified or authored for it (§4.4.6), and only then. The *permanently* half is declarable: a **terminal contract** (§7.8) marks it, reporting distinguishes **terminal** from **proxy**, and *proxy* thereby narrows to mean genuinely unassessed-or-awaiting — the population a rendering contract may still claim.
- **A stored rendering rides a named form.** Steady-state invariant: a record stores a content zone beyond its byte-marks only where a form contract governs it — under the identity contract, a "stored rendering" would merely restate bytes the resolver already derives. (Formless segments *within* a record that carries a form span are the mixed-artifact case and conform — §4.3.2.1. Renderings older migrations grandfathered without a form — the `rendered` state — exit through their next pass, never retroactively condemned.)
- **There is no vouch.** Every record derives its title/description from role-marked artifact and origin fields (§4.2.3) — mechanical, present from birth, no pass required — and where those resolve empty, **empty is the answer**. A record has no editorial opinion of itself to record, at any scope. Shaping is the whole of the normalize pass, and what a record's content *means* is the ledger's to say.

State is **reported, never stored**: health, the queue's pass gate (§8.5), and the ledger's verification (`ledger.md` §13.2) each derive the predicate they need from the record; the touch chain (§4.2.2) remains the provenance trail. A record still carrying a legacy `status:` field reads tolerantly — the field is ignored on read and dropped on the record's next write.

### 4.2 Frontmatter

The frontmatter (`---...---` at the top of the file) holds **only the bytes-identity header** — four fields. Everything else lives in body blocks (§4.3) or surfaces as derived views (§9).

#### 4.2.1 Core fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Primary identity — blake3 hash of the artifact's bytes, 64-char lowercase hex. Filename stem. Bare hex (no `<algo>:` prefix; algorithm is invariant). |
| `hash` | `<tag>:<hex>` \| list[`<tag>:<hex>`] | no | Auxiliary identity hashes beyond the primary blake3 (which lives on `id` and is **not** duplicated here). The tag classifies each value (§2, §7.6): a bare **algorithm id** (`sha256`, `md5`, `blake3-64k`) is a byte-stable, byte-verifiable digest — written at ingest per the declared `residency: record` recipes (§7.9) or added by deliberate flush; a **`<procedure>@<version>`** tag (`html-stampfree@1`, `eml-stripped@2.1`) is a procedure-versioned canonicalized identity — flush-only, never automatic, equality meaning "same content under that procedure at that version." Similarity-class values (§7.9) are never admissible. (A legacy `transport:` field reads tolerantly as `hash:` until swept.) |
| `touch` | string \| list[string] | yes (≥1) | Ordered list of touch identifiers, one per processing pass. Singular (bare string) when one entry; list when 2+. `touch[0]` is the original ingest. |
| `visibility` | enum | no | `visible` (default), `deranked`, `hidden`. Editorial curation, orthogonal to the derived content state (§4.1). |

Retired frontmatter, read tolerantly where a legacy record still carries it, never written: `status` (§4.1), `title`/`description` (an override is the record asserting a display value of its own, which §4.2.3 does not admit from any layer), `canonical` (the one content-canonical strategy collapsed unrelated scanned PDFs and was disabled; canonicalized identity re-earned residency as tagged `hash:` values under §7.9's conditions — the field itself stays retired), `perceptual` (fingerprints are similarity-class and live in the derived hash index only, §7.7/§7.9), `transport` (renamed `hash:` — the record's actual transport identity always was `id`; this field only ever held auxiliary digests).

#### 4.2.2 Touch identifiers

A touch identifier is a short bare string distinguishing a processing pass. The sequence is `touch[]` — a bare string when the chain has one entry, a list otherwise; the chain records the record's **current-shape provenance** (which passes produced the shape it has now). It is not an immutable history: `re-stub` resets it (§8.4), so a re-stubbed record's chain reflects its post-reset lineage, not every pass it ever saw.

- **Pipeline tooling** uses a stable identifier of the form `<package>.<module>@<version>` (e.g. `corpus.ingest@0.2.0`, `corpus.shape.conversation@0.2.0` — a **shaper** pass names the form or strategy it shaped). The `<package>.<module>` identifies the code path; `<version>` is its installed version.
- **LLM models** use the canonical model identifier with any context modifier in brackets — e.g. `<model-id>[<modifier>]`.
- **Combined tooling + model** — a single pass that is both a deterministic re-assembly and the LLM pass it carries joins the two with `+`: `<package>.<module>@<version>+<model-id>`.

Consecutive identical passes coalesce rather than repeat: a second identical identifier becomes `<identifier>_2`, a third `<identifier>_3`, and so on; a different identifier resets the count. The counter reflects the current chain, so a `re-stub` (which collapses the chain, §8.4) resets it.

The latest touch's tooling version implicitly encodes the spec era under which the record's current shape was produced.

#### 4.2.3 Derived editorial fields

A record's display **title** and **description** are **derived, never stored** — a pure function of the record's own blocks and their schemas, computed at read time exactly like the classifications view (§9.1).

They are also **never authored**. The two candidate layers are the two that carry someone else's words: the **artifact**, whose bytes may state a title or a self-description, and the **origin**, whose producer may have stamped one. The corpus reports those. It never composes its own. A record that resolves an empty title or an empty description is not defective and is not awaiting a pass: it means the source said nothing about itself under that role, which is a fact about the source. Where a display string genuinely needs authoring, it is authored **against the concept in the ledger**, which is the layer whose job is saying what things are.

**Role marks.** An `extended_fields` declaration in either of the two candidate namespaces may carry `role: title` or `role: description`, marking that field as an editorial candidate:

- a **mime** schema marks artifact-block byte-facts (§7.1) — a PDF's `/Info` title or `/Subject`, an HTML `<title>` or `meta[name=description]`, a bundle's embedded comment;
- an **origin** overlay marks origin-block fields (§7.2) — `ytdlp_title`, `ytdlp_description`.

A **form** contract marks nothing. Forms declare shape (§7.8), and a shape judgment is the corpus's own word about itself — precisely what this section does not admit. This is the bright line: artifact and origin quote a source; form would editorialize.

**Editorial templates.** An **origin overlay** may declare a top-level `editorial:` block naming a **mechanical composition** over more than one origin-block field (§7.2):

```yaml
editorial:
  title_template: "Mail window — {window_start} → {window_end}"
```

`{name}` placeholders substitute the origin block's own `extended_fields` values, read exactly as a role-marked field is (a list-valued field joins its non-empty items with `, `); static text passes through unchanged. Resolution is **all or nothing**: the template resolves only when **every** placeholder names a field holding a non-empty value — one unresolved placeholder falls the **entire** template through, never a partial composition. A template composes **attested producer facts into a display string**; it states nothing the origin block does not already carry, which is why it is admissible while an authored value is not. Only roles that exist are templatable — there is no `description_template`, the role having no template consumer.

A `title_template` (or any `<role>_template`) value may be an **ordered list** of templates in place of a single string: entries are tried in declaration order and the **first that fully resolves wins** — each entry individually all-or-nothing, per the rule just above — with a bare string standing as the one-element case of the same grammar. The cascade lets one producer overlay title several record shapes with disjoint field sets from a single declaration: each shape picks its own composition deterministically, by which entry's fields are actually present.

Templates resolve per origin block exactly as the overlay's role marks do (§7.2: latest qualified block wins; a bare block contributes nothing), so the origin layer's within-layer order is **template → role-marked fields**. On a **subtype-qualified** origin block, `editorial` resolves by the same ladder as any other concern (§7.2): the subtype overlay's declaration is consulted first, the id overlay's as fallback.

**Resolution.** Candidates resolve by layer precedence **artifact → origin** — the origin overriding the artifact, because a producer's stamp is the later and more specific statement about the same bytes. Within a layer, the **latest block wins** (origin blocks append in capture order, so a re-capture's fields supersede); within one block, the schema's declaration order decides, first non-empty winning. An empty or absent candidate falls through to the next, and an all-empty chain resolves to an honest empty value. No section, at any scope, contributes to a record's display identity.

**Consequences.** Every record carries its display identity **from birth, deterministically, and permanently** — there is no pass that can improve it and none that can corrupt it. Resolution is wholly mechanical: no LLM pass is required or *permitted*, so a record's title cannot drift from what its bytes and its producer say. A record deriving *empty* is a signal about its **schemas**, not its content — the mime or origin overlay wants a role mark on a field the block already carries — and health surfaces it as exactly that. Where the derived pair is empty and the schemas have nothing to mark, the honest reading is that the source named itself nothing; a consumer needing a human label for that record wants the **ledger's** name for the concept it evidences, not a sentence the corpus invented. Consumers (the derived body, search indexing, export §10, the ledger's display of cited records) read the derived value, and there is no stored pair for anything to read.

**Enumeration is by cohort, not by title.** The pressure that kept an authored title alive was practical rather than principled: a table of records wants no empty cells. The answer is not to require every record to produce one string — which is what manufactures the mechanical/interpretive ambiguity this section exists to remove — but to **stop listing unlike records in one table**. A cohort is a population sharing a schema — one origin, one form, one mime — and **that schema's `extended_fields` declaration IS the column set**, in declaration order, every column mechanically derivable from the bytes by §7.2/§7.8. A statement cohort lists as `institution | account_ref | statement_date | coverage`; a tax-slip cohort as `slip_type | tax_year | issuer | slip_status | as_of`. Those columns are strictly richer than the title string that used to flatten them, and unlike a title they sort, filter, and group. An `extended_fields` declaration earns its place by being **derivable from** the bytes and **absent from** the rendering — a producer's sidecar fact, a URI-pattern derive, a computed envelope. A field that merely re-states a line the body already carries adds a column and a divergence at once.

Which layer supplies the columns is decided by **which layer holds mechanical facts for that population**, exactly as elsewhere the layers do not bleed: the **origin** for producer exports (whose sidecars stamp account, period, coverage), the **form** for shape-bearing cohorts, the **mime** for format facts. A cohort whose schemas declare nothing is not defective — a generic `form/document` population genuinely has no universal facts, and the honest listing for it is by origin instead.

Three columns are always available and never interpretive, and they are the whole of what a **heterogeneous** listing is owed: the record `id`, its origin `uri`, and its media type. Where a cross-cohort listing wants a human name, that name belongs to the **ledger** — a record's human handle is the name of the concept it evidences (`ledger.md` §4), authored once against the thing itself rather than once per record that mentions it. The corpus enumerates within a population; naming across populations is knowledge, and knowledge is one layer up.

### 4.3 The record body — six block families, three zones

The record body is the markdown content below the closing `---` of the frontmatter. It has three **zones** — metadata, content, annotations — each holding a fixed set of HTML-comment block families.

Every block has the same shape: an HTML comment whose opener line carries a keyword (and optional arg), the YAML payload on the lines that follow, and a closing `-->` alone on its line. HTML comments are syntactically distinct from markdown horizontal rules and from frontmatter delimiters, and every standards-compliant markdown renderer ignores them — so the record body renders cleanly.

```
─── metadata zone ────────────────────────
<!--artifact <mime-type>-->               # exactly 1
<!--origin [<id>[/<subtype>]]-->          # 1..N
<!--members-->                            # 0..1

─── content zone ─────────────────────────
<!--section <form-id>-->                  # 0..N form spans (depth one; never overlap)
   containing <!--segment ...--> blocks
<!--segment <atom>[/<id>]-->              # content segments (top-level = formless)
<!--segment structural-->                 # byte-mark TOC entries (top-level or in-span)
<!--segment placement-->                  # member positioned at this address (§4.3.2.4)

─── annotations zone ─────────────────────
<!--context <namespace>/<id>[/<subtype>]--># 0..N (record- or segment-scoped via address:)
```

Zone order is fixed. A block of a later zone appearing before a block of an earlier zone is a parse error. Within a zone, the relative order of different block *families* is not significant; the diagram's family order is illustrative. **All metadata- and annotation-zone blocks are header-only**: their YAML payload is the entire block; there is no markdown content between blocks within those zones. **Only text-atom segment blocks and structural segments carry inline content** — the segment body holds the actual text. The section opener is **qualified** — it carries a form id (§4.3.2.1); a bare TOC-grouping section does not exist in the grammar and reads tolerantly on legacy records.

#### 4.3.1 The metadata zone

The metadata zone carries the artifact's identity, its origins, and its embedded assets. Three block families.

##### 4.3.1.1 The artifact block

Exactly one per record. The opener-line argument is the canonical MIME type and is **authoritative** — there is no frontmatter `media_type` field. The block body holds the fields declared by the matching `mime` schema chain, named **bare** — the opener's MIME already identifies their provenance (§1.5 principle 10), so a PDF's title is `title`, not `pdf_title`. When the format exposes a title it rides as that bare `title` candidate — a role-marked candidate in §4.2.3's derived ladder alongside the origin block's `ytdlp_title`; nothing authors a stored title. (A field keeps a prefix only when it names a provenance the opener does *not* carry — a metadata sub-standard the format embeds, e.g. `exif_*` on an image, `og_*` on HTML.)

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

##### 4.3.1.3 The classify block *(retired)*

The classify block asserted record-scope interpretive classification. That assertion is knowledge, and it lives in the ledger: what a record documents is expressed as ledger concepts and claims — the record rostered as an artifact of the thing and cited as evidence (`ledger.md` §4) — minted mechanically by **harvest rules** where membership is deterministic (`ledger.md` §10) and authored where it is not. The corpus-side classifications view (§9.1) retains its structural-derived rows (`mime/*`, `origin/*`, `form/*`). The reserved `provenance` field survives on context blocks (§4.3.3.1) with the same semantics.

##### 4.3.1.4 The members block

At most one per record. A single header-only block whose payload is the **unabridged roster of this record's embedded assets** — one row per member. A member is a **closed primitive**: it declares an asset whose bytes are **part of this record's capture** — materializable from the record's own artifact (a nested transport, an archive member, an inline `data:` asset, a media track) or from its capture-time enrichment (`also_capture`). A record never rosters content that lives in *another* record's capture; content the record's bytes merely *reference* is reached at read time through the resolver — a lineage-chained reference (§6.2) or a read-time link resolution (§9.9) — derived, never stored. The `transport:` hash names the bytes (the dedup key); the address says where the asset appears in this transport.

The block is **wholly attested** (§4.4.6): every row is re-derived from the artifact on every attestation, and nothing in it is a normalizer's to write. It is an **index**, not a description — its job is to answer *which record holds this blake3, at what address, of what type, how big* without opening a single artifact, because that question is asked across the whole corpus at once (the member index, §12.9) and must stay cheap at fleet scale.

```
<!--members
- address: <address>              # scalar — single occurrence
  media_type: <mime-type>
  transport: <algo>:<hex>
  bytes: <n>
- address:                        # list — repeated bytes at multiple positions
  - <address-1>
  - <address-2>
  media_type: <mime-type>
  transport: <algo>:<hex>
  bytes: <n>
-->
```

###### Row fields

The row is a **closed shape** — exactly these four keys, and an unrecognized key is a validation error. A closed shape needs a closed check, or the block silently re-accumulates the descriptive payload this grammar exists to keep out of it.

| Field | Description |
|---|---|
| `address` | Where the asset appears in the transport, in the scheme defined by the media-type schema. Polymorphic: a single string or a YAML list of strings. |
| `transport` | Content-identifying hash, `<algo>:<hex>`. The canonical id of the member; the deduplication key. |
| `media_type` | The member's full MIME type. |
| `bytes` | The member's size in bytes, uncompressed. Present so size accounting over a corpus of containers costs one pass over records and no artifact reads. |

###### The admission rule

A field is admitted to the row only if it (a) answers a question asked **across records** without opening an artifact, and (b) is an **identity-or-accounting fact** rather than a reading of content. Both, not either.

Everything else about a member — pixel dimensions, verbatim `alt` text, a member filename, an email member's `from`/`subject`/`date`, a vCard's display name — is derived on demand by the `members` op (§6.2) and stored nowhere. This is not a size optimization; it is what keeps the roster mechanical. A block that carries readings of content invites authoring, and an authored roster is no longer idempotently derivable from the artifact it claims to describe.

Two consequences worth stating, because both are tempting:

- **Pixel dimensions fail (a)**, not (b) — the question they answer is about one image, and any real use of it needs the pixels anyway. They would earn a place if a gate were ever built to check a fractional region address against the asset's true extent rather than only against the region grammar (§6.2); until such a gate exists, they are derived.
- **An email member's `from`/`subject`/`date` pass (a) and fail (b)** — "find the message from X about Y" genuinely is a cross-record question, which is exactly why this one is tempting. It is a reading of content, it belongs to the `members` derivation, and admitting it is how the roster would begin accumulating again.

A member's **narration** has no home here — and no home anywhere else either. What a record can say about a member is its row (identity and accounting), its placing marker (where and what type), and any lossless extraction from it; anything beyond that is the member's own record once promoted (§8.1), or a ledger claim.

###### Deduplication

Members are deduplicated by `transport` — identical content collapses to one row regardless of how many positions reference it. The attesting pass walks the transport's assets in order, hashes each, and merges duplicates by appending positions to the existing row's `address` list.

###### Linking from segments

Segments link to members by **address membership**, not by an explicit reference field. A segment whose address appears (scalar or list-member) in a member's `address` is the place where that asset sits in the record's representation. Unplaced members — rows no segment points at — are tolerated as a record of available assets: the roster is unabridged by design, and declining to *place* a favicon is the pruning decision, never editing the roster.

The segment that does the linking is a **placement** (§4.3.2.4), and it is the only kind admitted at a member's address. The correspondence is exact in both directions: **a placement's address MUST appear in some member's address** — a placement naming no member names nothing — and **no content-atom segment's address may appear in, or chain from, a member's address**, because a member's content is its own record's to render. The chained form is included deliberately: `el=<N>&bbox=<x,y,w,h>` is a crop of the member's *pixels*, so it is a rendering of the member's bytes wearing the container's address, and it re-homes onto the member's own record with the crop intact and the `el=` prefix gone. Placing is therefore also what obliges promotion (§8.1). *(A **placement** may chain from a member's address, and only a placement may: that is the deconstructed import, and it names a region the member's own record has already declared rather than one the parent measured — §4.3.2.4. The prohibition here is on **content**, which is why the two forms do not collide: a chained placement still says only* member X sits here, *at finer grain.)* *(Structural byte-marks are unaffected and may stand at any address, member or not: a mark is the source declaring a boundary, which is a fact about this transport regardless of what sits at the position.)*

Every image, audio, and video segment therefore addresses something the resolver materializes from **this record's own capture** without a roster row. Two cases qualify:

- **Artifact self-slices** — a region of the record's own artifact: a `frame=`/`time=`/`time_range=` into a video, a `page=` render of a PDF, a `bbox=` into a single-image record.
- **Lineage-chained references** — an asset the record's bytes declare but do not contain, whose bytes live in the record's own containment-lineage parent (§6.2): a conversation message's attachment (`turn=<N>&att=<M>`), a promoted member's sibling asset. The reference is faithful content (it is *in* the bytes); the resolution chain is derived at read time from the lineage origin block plus the record's own bytes — never stored — and cannot rot, because the parent is content-addressed. A reference whose target member is absent (a dead CDN link the export never localized, a takeout gap) is still a faithful marker; materialization fails loudly at resolve/health time, never papered over by a stale stored pointer.

A member row is needed only for assets that are neither self-slices nor lineage-resolvable — an inline image the capture inlined, a nested transport, a declared track. (Which is the same set that takes a placement rather than a marker, and the same set promotion reaches — one line, drawn once, read three ways.)
#### 4.3.2 The content zone

The content zone carries the record body's rendered content — segments (content-atom and structural), optionally spanned by form sections. Two block families.

##### 4.3.2.1 The section block — the form span

A **section** declares that a span of the content zone has a named structural form. It is a positional span with a YAML header, carrying the one thing that genuinely needs a span with fields: the record's **form** (§4.4.1, §7.8). The opener is **qualified** — it carries the form id, exactly as a segment opener carries its atom id:

```
<!--section conversation
participants:
- Alex Doe <alex@example.org>
- Robin Roe <robin@example.net>
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

(The structural mark is the platform's own topic boundary — a byte-mark; exports that carry none go flat. `participant:` indexes the section's authorship-ordered codebook. Turn 2 is an attachment-bearing reply: its `text/message` envelope segment is empty-bodied — the message has no text, and the envelope never rides the marker — and the `image` marker at the composed address carries no member row: the attachment is lineage-resolvable, §4.3.1.4/§6.2.)

###### Section header fields

**There are no universal section-header fields.** Every field a section carries is one its form declares (§7.8) — codebook lists (e.g. `form/conversation`'s `participants:`, the authorship-ordered codebook that `participant:` segment indexes resolve against) and span envelope facts, each mechanically derivable from the span's own bytes. A form that declares nothing takes a **bare opener**, and the bare opener is complete: `<!--section index-->` says *this span takes the index form and renders under its contract*, which is the entire job of the block. The rule is structural, not stylistic: a field present on every section regardless of form is a field no contract owns and no check binds, so it is where accretion lands — removing the universal slot removes the landing site.

**The envelope is derived, never stored.** A span **is** its children; its envelope is the min–max span of the child segment addresses (`pages=2-6`, `turn=1-74`; for `el=` the **tightest single containing address** under §6.1.1 — a contiguous sibling run's range, else the lowest common container element's own ordinal, derived under the attested parse), computed by every reader as `section_address(children)` under the children's own discrete-index scheme. A stored envelope could disagree with its children, and a derived one cannot. Two things follow: a section always claims the tightest address its children's extent admits — where one form governs everything, its one span's envelope simply covers everything, and there is no separate "whole-record section" spelling — and a record's display identity has no section-shaped input at all (§4.2.3). *(A **temporal** section — `time_range=` — is a structurally bounded interval, not a min–max over children: it states its bounds as the form's own declared field.)*

###### Rules

- **Positional span.** A section's closer is followed directly by its first child block; its span runs to the next section opener or the end of the content zone. Markdown prose between a section closer and the next opener is a parse error — sections have no body region.
- **Depth one, no overlap, one form per span.** Sections never nest and never overlap (positional by construction). Forms do not nest; a genuinely separable sub-document is a **promotion** candidate, not a nested form. A record MAY carry any number of sections, each a span under its own form — an article followed by the index of sibling links the page also renders; a manual's procedure span followed by its parts table. A section holds only a shape judgment, and a document that changes shape partway through is an ordinary document, not a contradiction. Two sections can only overlap if their children do, which the address grammar and `segment-address-duplicate` already decide — one rule, at the segment grain.
- **Block order is significance order, not source order.** **Within** a span, blocks follow the source's presented order: that is what faithfully rendering a region means, and the ordered-axis forms bind it as a `monotonic` check (§7.8). **Across** spans the rule is different — the content zone opens with what the artifact is *for*, and the spans that merely frame it (a breadcrumb trail, a sibling-links rail, whatever navigation furniture the page wraps around its content) follow it. Nothing is lost by this, because block order was never where document position lived: position is carried exactly, mechanically, and at finer grain by the `address` (§6.1.1). A record that encoded it in both channels would be stating one fact twice, and the weaker copy is the one that eventually gets believed. For chrome the source's own order is not even well defined — a rail is routinely emitted nowhere near where it is displayed — so a rule that ranks spans by what the artifact is about is the only one that needs no per-host adjudication. **Nothing declares a span "chrome."** Whether a span is the content or the frame is a property of its role in *this* record, never of its form: `form/index` is the whole content of a category-selector page, and `form/nav` — the shape a framing rail or breadcrumb takes — is itself the whole content of a wayfinding hub and the trailing furniture on an article that happens to carry a link rail. Even the form minted *for* the framing population names a shape, not a role; position still says which it is here. Significance is expressed *by* position, so a `chrome:` field would be a second answer to a question order has already answered — and, being a field no contract owns, exactly the accretion site the retired universal headers were.
- **Formless is the zeroth form; a named form is earned.** A section exists *only* where a named form is declared — and a record with no section is not deficient: its content stands under the **identity contract** (§4.1, §7.8), consumable through the derived body, prescribing nothing about what the artifact is. Artifacts with no faithful markdown shape — code, datasets, media, containers — stay formless permanently; that is their correct steady state, never a backlog. For artifacts a markdown shape genuinely fits, formless is instead a starting point: a named form is the goal, adopted lazily when identified or authored (§4.4.6, §7.8). Segments before the first section opener are **formless** content under mime + atoms alone — the mixed-artifact case: a statement PDF whose page 1 is a cover letter carries page 1's segments bare, then `<!--section statement-->` over the statement proper.
- **Coherence is lint-enforced.** A record carrying `<!--section <form-id>-->` MUST satisfy that form overlay's declared conformance checks (§7.8) — envelope fields present, codebook indexes in range, addresses parse in the span's scheme. There is no half-asserted form and no transitionary state: stamping the form and conforming the span land together.

(A passage's *meaning* remains a ledger claim over the span — §4.4.3. The form id on the opener is a structural-shape judgment, not a meaning — §7.8.)

###### Worked example — the mixed statement PDF

```
<!--segment image
address: page=1
-->

<!--segment text/ocr
address: page=1
-->

Dear Mr Rahn — enclosed please find your statement for the period …

<!--section statement
account: '…7841'
period: 2026-03
-->

<!--segment text/ocr
address: page=2&bbox=0.06,0.12,0.88,0.30
-->

... transactions rendered per the statement form's contract ...
```

Page 1 stays formless — no contract has been identified for it and nothing yet demands one (§7.8: adoption is benefit-driven; formless is valid indefinitely); the statement's codebook/envelope fields (`account`, `period`) ride the section header, mechanically derivable from the span's own bytes; lint runs `form/statement`'s checks over pages 2–6 only. Page 1's cover letter is not narrated — it is **transcribed**. The image marker says a page-1 raster exists; the co-addressed `text/ocr` segment carries what it says. If the letter is worth mentioning it is worth transcribing; if it is not worth transcribing, the marker alone is the honest record and the bytes are one resolve away.

##### 4.3.2.2 The segment block

```
<!--segment <atom>[/<id>]
address: <address>                       # single string OR a YAML list of strings
<other-header-fields>: <values>
-->

<segment body>                            # text atom only
```

The atom (`text`, `image`, `audio`, or `video`) sits on the opener line itself, optionally qualified by an atomic-overlay id (e.g. `<!--segment text/data-table-->`) — or the opener names a non-atom kind: `<!--segment structural-->` (§4.3.2.3) or `<!--segment placement-->` (§4.3.2.4). A content segment is **logically contiguous content of one classification**; an interrupting element of a different classification forces a segment boundary.

A segment's identity is `(opener-id, address)` — the atomic class id on the opener plus the address. Two segments may share an address only when their opener-id differs. This permits **same-region stacking**: a single source region can carry multiple representations — a positioning marker for the asset, a structured transcription, a literal-text transcription — each as its own segment with the same address but a distinct opener-id. Multi-region segments use an ordered list of single-region addresses in reading order.

###### Body permission rule

A segment carries a segment body only when that body is a faithful, lossless rendering of the addressed content. This resolves to three cases:

- **Plain prose** — `<!--segment text-->` with the segment body as markdown text. Default for HTML prose, PDF page text, etc.
- **Shaped lossless transcription** — `<!--segment text/<id>-->` where the overlay's declaring schema licenses lossless shaping (`enables_lossless: true`, §4.4.1). The overlay shapes the segment body into the declared form (markdown table, transcript, OCR text, time-stamped captions, etc.). The address scheme may chain through transport→atom transforms to reach a region within a frame within a stream.
- **Body-empty marker** — every other segment, in two cases. (a) The three non-text atoms (`image`, `audio`, `video`) are positioning markers in document flow for a region of **the record's own transport** — a self-slice the resolver materializes from these bytes (a PDF page raster, a `bbox=` crop, a `frame=`/`time_range=` cut). (An address that a **member** row carries is not this case — the member has its own byte identity and its own record, and it is positioned by a `placement` (§4.3.2.4). A content atom at a member address claims residue in bytes that are not the record's to claim.) (b) A `text/<id>` overlay whose declaring schema sets `enables_lossless: false` marks a *typed but non-lossless* text region — e.g. a live, formula-driven table whose displayed values are a single-execution snapshot rather than faithful content. In both cases the segment body is empty **and stays empty**.

  **A marker says where the bytes are; it never says what they contain.** What the region is, is answered by the opener — the atom and its overlay id (`image/chart`, `image/logo`, `text/data-table-dynamic`) — which is a typed, cross-record-queryable, mechanically-checkable answer, and by the address, which is where to go. A marker carrying prose would be the record substituting a paraphrase for a rendering it declined to perform. This obliges the atom namespace to keep its overlay ids **self-describing** (§7.3): an overlay too vague to answer "what is this region" is under-specified, and the fix is a better overlay, never a sentence on the segment. Where more than the type is genuinely knowable, it is knowable **losslessly** — as a co-addressed segment (below) or, if the asset deserves standing of its own, as a promotion (§8.1).

**A faithful rendering replaces the marker.** Where a region's content is rendered losslessly, that rendering is the region's representation and the positioning marker goes. Nothing is lost by dropping it: the member row addresses the bytes directly (§4.3.1.4), so the resolver reaches the pixels whether or not a marker sits in the reading order. What a marker adds beside a complete transcription is not a second representation but a **second, contradictory ruling** about one region — because the atom is precisely how a segment declares whether anything is left over (§7.3, `enables_lossless`), and a region cannot both have residue and not have it.

**If it cannot faithfully replace, it is not a faithful rendering** — and the marker standing alone is then a **finished** record, not a backlog. A photograph is never reduced to its words: its marker is permanent, the region is honestly represented by its bytes, and `corpus resolve` is how a reader reaches them. Where the whole artifact is that case, `form/passthrough` states it at record scope (§7.8). Better tooling may reduce such a region later; nothing is owed until it does.

Same-region stacking remains exactly what the identity rule permits — several representations at one address, distinguished by opener-id — but a marker beside a *complete* transcription of the same region is not an instance of it. The genuine instances extract **different** information: the text printed *in* a photograph is a `text/ocr` segment at the sub-region it occupies (`el=N&bbox=…`), which is a different address, while the photograph's own residue keeps the marker at `el=N`. A whole-frame `bbox=0,0,1,1` is not a sub-region — it is the same full-region transcription wearing a crop, and the same rule applies.

Whether such extraction is **exhaustive or incidental** is not readable from the segments alone — three `text/ocr` segments say where somebody looked, never that nobody needs to look further. A pass that has processed an entire band declares it with a **sweep** (§4.3.3.6); absent one, extraction is sparse by default and the bytes remain the band's representation.

###### The address field

| Field | Description |
|---|---|
| `address` | Address inside the transport, in the scheme defined by the media-type schema. Part of the segment's identity. Composable: addresses chain transforms (e.g. transport → frame → region) as the schema permits. **Optional** — absence names the whole transport. Below. |

**An absent `address` names the whole transport.** A functional URI has always spelled *these bytes, whole* as the bare `corpus://<id>` with no query (§5.1, §6.1); an absent segment address is the record-side mirror of it, and means exactly the same thing. It is required for the ordinary case a promoted member creates: a record whose artifact **is** the addressed content — a promoted table image whose whole rendering is one `text/data-table`, a plain-text artifact rendered whole — where every axis the media-type schema declares is a way of naming a *part*, and naming the whole through one of them means fabricating a value (`bbox=0,0,1,1` — the same full-region rendering wearing a crop). The fabricated value is not merely inelegant: it is a stored claim that a *region* was addressed, which lint then checks against a grammar that cannot see it is false. Absence is checkable, singular, and cannot drift.

Two rules bound it, so absence stays the whole-transport statement rather than becoming the lazy default:

- **A body-empty positioning marker may never be address-less.** A marker's whole content is *where*; a marker positioning the record's own bytes within the record's own flow states nothing, and there is nothing for a reader to resolve that `corpus://<id>` did not already give them. This holds for the three non-text atoms, for the structural byte-mark (a boundary is a position by definition, §4.3.2.3), and for the placement (which names a member *by* its address, §4.3.2.4).
- **The identity rule is unchanged**, and it does the rest: identity is (`opener-id`, `address`), and an absent address is one value like any other — so a record carries at most one address-less segment per opener-id, and an address-less rendering coexists with `bbox=`-addressed extractions of parts of the same artifact exactly as two addressed segments would.

**Admissibility belongs to the media type, and the media type declares it.** Absence names the whole transport — but whether a transport *has* a whole to name is a property of the medium, not a choice available to the record. A still image is one contained presentation: it is consumed at once, and every axis its schema declares (`bbox=`) names a part, so the whole is nameable only by absence. A **sequence** is not. A PDF is pages, a video is time, an mbox is messages, and one address-less rendering over any of them asserts a reading of the whole while naming no element of it — the reader is given a body and no route back into the artifact. The distinction is not derivable from the bytes at check time and must not be guessed, so the mime schema states it (§7.1, `whole_address`) and lint enforces it:

- **`admissible`** — a single contained presentation. An address-less rendering is the conforming form. *(`image/png`, `image/jpeg`, `application/x-troff-man`, plain text.)*
- **`forbidden`** — an inherent sequence, **or** an address space already total. Both make absence wrong, for opposite reasons: a sequence has no whole to name, and a total space (HTML, §6.1.1) has an honest address for every region including the outermost, so absence is unnecessary rather than untrue. *(`application/pdf` — `page=`; `application/mbox` — `msg=`; `video/*` — `time_range=`; `text/html` — `el=`.)* A one-page PDF is **not** an exception: `page=1` is a true statement about a real unit, so nothing is fabricated by requiring it.
- **`single_unit_only`** — a medium that *may* be a sequence, where only the bytes decide. Absence is admissible **iff** the attested count named by `whole_address_count` equals 1. *(`image/gif`, `image/webp`, `image/avif`, `image/heif` — `frame_count`; a HEIF may carry an image sequence, which is why the still formats and the motion formats cannot be split by MIME family.)*

**The frame axis is the sequence's road to conformance.** The animation-capable image schemas declare `frame=` (§7.1 `address_scheme`; §6.2 for the grammar): a rendering of one frame addresses `frame=<N>`, and a rendering that holds across the whole sequence — a burned-in caption the animation never changes — addresses the **inclusive span** `frame=<A>-<B>`, which is an *assertion*, checkable frame by frame, never an omission and never a single frame dressed as the truth about all of them. The two shapes are content judgments, not grammar: a changing screen flattened into one text is exactly what the whole-address gate exists to catch, and it decomposes into single-frame segments; an invariant caption is *most truly* rendered over its full span. `frame=` chains frame-then-region (`frame=3&bbox=…` — a region *of* frame 3; the reverse order is a lint error), and its stored values are gated by `address-frame-invalid` against the same attested `frame_count` the whole-address rule compares — compare, never decode, both rules alike.

**The gate compares an attested count; it never decodes.** The count is stamped at ingest attestation (§8.3) alongside the sequence counts the bearing types already carry — `page_count`, `message_count`, `member_count`, `card_count` — so `whole_address_count` names an existing convention rather than inventing one. A gate that had to open and decode the artifact would report red when a decoder was absent rather than when a record was wrong, which is not a validity check but a report on the checking host.

**An unstamped artifact of a `single_unit_only` type is unresolved, not admitted.** Absence on a record whose `whole_address_count` field is missing is an **error**, not a pass — the check has no fact to compare, and defaulting to admissible would silently grandfather exactly the population the value exists to catch. Re-attest supplies the count (§8.3).

###### Optional header fields

| Field | Description |
|---|---|
| `speaker` | An integer diarization index identifying who is speaking in this `audio` segment. |

Retired header fields, read tolerantly on legacy records, never written: `perceptual` (fingerprints live in the derived hash index, §7.7/§7.9), `description` (a segment cannot narrate its own region, §4.2.3), `entry` (a source's own heading or caption text belongs on a structural segment's body — verifiable against the bytes, picked up by the derived TOC; a label not in the source is the record naming its own structure, and it goes).

The atomic classification, if any, lives on the opener line as `<!--segment <atom>/<id>-->`. A segment carries exactly one atomic class id; when multiple representations apply to the same source region, each becomes its own segment (and identity is the `(opener-id, address)` pair).

Segment-scope issues live as standalone issue context blocks in the annotations zone with an `address:` field pointing back to the segment — never inline on segment headers.

###### The four content atoms

- **`text`** — the atom whose segments carry segment bodies, with one exception. Plain prose by default; shaped by a `text/<overlay>` for structured lossless forms. A `text/<overlay>` declaring `enables_lossless: false` is a body-empty marker like the non-text atoms, its overlay id carrying the answer to what the region is.
- **`image`** — a static image at the addressed region. Body-empty positioning marker. Text printed within it extracts as co-addressed `text` segments.
- **`audio`** — an audio range. Body-empty positioning marker. Transcripts live as separate `text` segments at the same address.
- **`video`** — a video stream over the addressed time range. Body-empty positioning marker. Captions and scene transcripts live as separate `text` segments at the same address.

###### Faithfulness

The segment body MUST be a faithful, lossless rendering of the addressed content. Descriptive content — a summary of what an image shows, a paraphrase of what was said, a characterization of what a live or computed region contains — is **lossy** by definition and has **no home anywhere in a record**: not the body, not a header field, not the annotations zone. Re-segmentation is structural; content within remains faithful.

**The rule and its consequence.** A record is the faithful representation of its bytes. Where a region cannot be faithfully represented, the record's honest statement is *the bytes are here, at this address, of this type* — a body-empty marker — and the reader resolves them (§6.2). Anything more is the corpus summarizing itself, and summary is exactly the failure mode this discipline exists to prevent: a paraphrase cannot be checked against the bytes the way a transcription can, it is written once and never re-verified, and it is indistinguishable in the record from content that *was* verified.

Summary is a **query**, and the query layer is the ledger. Where a reader wants "what does this record contain," the answer is composed from ledger claims that cite the record's verifiable surfaces, each with span-precise evidence that can be re-checked against the bytes and revised when wrong (`ledger.md` §6.3). That is the same information a description would reach for, held where it can be audited, attributed, and superseded — none of which a sentence in a record header can be.

###### Cross-references in segment bodies

Segment bodies carry **no intra-corpus links**. A `corpus://` reference stored in a body is a violation: the resolution it names is derivable at read time from the record's own bytes plus its lineage, so storing it duplicates a derivation and can disagree with it. Nothing inside the same transport needs one either — an inline image is its own `image` segment, addressed on the artifact's own axis (§4.3.1.4).

Cross-artifact connection is expressed the way the captured bytes already express it: by the **source URL**, reconciled to intra-corpus references at read time during cross-reference resolution (§12.4.7), never by a stored corpus address.

Segment bodies may carry:

- **Plain markdown URLs** — the links the source itself carries, whether or not their targets are captured. Reconciliation is a derived view's job, not the body's.

(The stored content zone has exactly one author — the normalize pass — and its total-replacement discipline is stated at §4.4.7. The raw-blake3 and functional-URI wikilink/embed forms are retired from segment bodies; the one place a `corpus://` string is persisted is a promoted record's origin lineage `uri:`, which is capture history, never a lookup route — §8.1, §12.9.)

##### 4.3.2.3 The structural segment

```
<!--segment structural
address: <the MARK's position>
level: <int>
-->

<the mark's own text, verbatim — as markdown>     # empty when the mark is unlabeled
```

A **structural segment** records that **the source itself declares a structural boundary** at an address: a heading (`el=<N>`, §6.1.1), an EPUB nav target (`spine=<N>`), a PDF outline entry (`page=<N>`), a media chapter (`time=<tc>`), a chat platform's topic boundary (`turn=<N>`). It carries no content atom and takes no atomic overlay. Its identity is (`structural`, address), stacking beside content segments at the same address per the standard rule.

**The mark's text lives in the BODY.** A mark is markup, and a header scalar is a string: a source heading routinely carries links, emphasis, and line breaks, and a scalar flattens all of it at authoring time, silently. Worse, text held outside any body displaces what is beside it — every position computed over a span's rendering comes out short by the mark's length. So a structural segment's body is its mark, rendered faithfully like any other content — links kept (§4.3.2.2), verbatim otherwise. An **empty body is an unlabeled boundary** (an `<hr>`, an untitled chapter). The mark contributes to the faithful text rendering and counts toward `token_counts.body` (§9.6), because it is text the record renders.

**The verbatim obligation is mechanically checkable**: the body's **plain-text projection** must equal the addressed element's own text. A body whose text is not the source's is a violation, not a judgment call.

###### The byte-mark rule

A structural segment exists **only where the source bytes carry the mark** — or where the capture's producer-declared enrichment carries it (a yt-dlp sidecar's `chapters[]` is the uploader's own declaration, lifted mechanically at ingest; §12.3.7). A pass never invents one. Groupings a reader may want but the bytes do not declare — a conversation's per-day break (whose midnight? which participant's timezone?), a "front matter vs body" split with no nav entry — are **read-time renderings** with explicit parameters (`corpus toc --tz <zone>`, defaulting to UTC and saying so), computed from the envelope timestamps and addresses the segments already carry, never stored. (This is §1.5 principle 3 applied to structure.)

###### Level and scope

- `level:` is the mark's own hierarchy where the source states one (`h1`–`h6`; outline depth; nav nesting), else `1`. Levels are the *whole* nesting grammar — there is no block nesting.
- A mark's **scope is derived**: it runs from its address to the next structural segment of the same or shallower level, or to the end of the enclosing form section (or content zone). Content before the first mark is preamble. The TOC tree — arbitrary depth — is a derived rendering over the flat mark sequence, exactly as an archive's directory tree is a derived rendering over `path=` addresses: *a tree is a derived rendering, not stored blocks*, applied to the table of contents itself.
- The mark's own `address` is a **position**, not an envelope; a consumer that needs a mark's span derives it from scope.

###### Emission

Byte-marks are mechanical facts, so structural segments are **attested at ingest** where the mime schema declares them (a media container's chapters, §1.2) and otherwise written by the normalize pass's shaper from the same derivation ops any consumer can run (a PDF's `outline`, an EPUB's nav, an HTML page's headings, a transcript's declared topic ids). Either way the mark is checkable against the bytes — the same auditability as every attested fact. **Ownership is deterministic from the schema**: a structural segment is attested — and stripped + regenerated by re-attest — **iff its address family is declared in the mime schema's `attest:`** (§7.1); every other mark belongs to the authored layer and refreshes with re-normalize (§4.4.7). No per-segment provenance field is needed: schema plus touch chain recover the owner.

###### Worked example — a media container with chapters

```
<!--artifact video/x-matroska
duration: '01:42:07'
streams: [h264 1920x1080, aac 5.1 eng, subrip eng]
-->

<!--members
- address: stream_id=0
  media_type: video/h264
  transport: blake3:…
  bytes: 4200000000
- address: stream_id=1
  media_type: audio/aac
  transport: blake3:…
  bytes: 293000000
- address: stream_id=2
  media_type: text/x-subrip
  transport: blake3:…
  bytes: 41000
-->

<!--segment structural
address: time=00:00:00
level: 1
-->

Opening

<!--segment structural
address: time=00:12:31
level: 1
-->

The heist
```

The chapters are the container's byte-marks on the shared timeline; the tracks (promotable, §8.1) inherit them at read time through lineage — a track record never copies marks its own bytes do not carry.

##### 4.3.2.4 The placement segment

```
<!--segment placement
address: <where the member sits in this transport>
-->
```

A **placement** is a body-empty segment recording that a **member** (§4.3.1.4) sits at this position in the record's reading order. It is the sixth segment kind: no content atom, no atomic overlay, no body, no fields but the address. Its identity is (`placement`, address). It is the exact structural twin of the structural byte-mark (§4.3.2.3) — both carry a position and withhold every claim about content — and the two differ only in what the position is *of*: a mark points at a boundary the source declares, a placement at bytes the roster already names.

**What it withholds is why it exists.** The atom is precisely how a segment declares whether anything is left over (§7.3, `enables_lossless`): an `image` at an address claims *irreducible bytes here*, a lossless `text/<id>` claims *this is what they say*. For a member both claims are about bytes that have their own blake3, their own byte-facts, and — once positioned — their own record. A containing record making either claim is asserting something about content it does not own, in the one place where the assertion cannot be shared: the next record to contain the same member would have to make it again. A placement makes exactly one statement, and it is a statement about *this* record: **member X sits here**.

**The member is named by the address, and the rendering is imported.** A placement stores no reference to the member and no reference to its record. The address it carries appears in exactly one roster row (§4.3.1.4's dedup rule guarantees at most one), that row's `transport:` is the member's blake3, and the blake3 **is** the id of its record (§2) — so *placement → row → hash → leaf record* is a derivation over the record's own bytes, computed by every reader and stored nowhere. A stored `corpus://` pointer here would be the retired body-link grammar, refused for the same reason: a derivable fact written down is a fact that can disagree with its derivation.

###### Import is member-gated, and whole unless it is exhaustive

A record imports another record's rendering **iff** that record is a **member** of this one, positioned by a placement. There is no general cross-record import and there is deliberately no syntax for one: the corpus links *downward to bytes* (§5.1), never sideways to another record's authoring, and a record able to pull arbitrary content from another record would carry material it neither owns nor can check against anything. The member relation is the entire permission, and it is already exactly the relation the roster attests.

Within that permission there are two forms, and the default is the coarse one.

- **Whole import** — a placement carrying the member's address **bare**. The leaf's rendering is imported entire, in the leaf's own order. This is the ordinary form and it asks nothing of the leaf but existence.
- **Deconstructed import** — a placement whose address **chains** the member's address with a suffix (`el=<N>&<suffix>`). It imports only those leaf segments whose own address *is* that suffix, so a parent can position a member's parts individually rather than as one block.

***The grain of the deconstruction is the address, not the segment.*** A leaf may carry several segments at one address — identity is (`opener-id`, `address`), so a `text` and a `text/data-table` describing the same region are distinct segments legitimately sharing one (§4.3.2.2) — and a placement naming that address imports **all** of them, in the leaf's order. This is a deliberate coarsening: a placement carries an address and no opener, and giving it one would make the parent name *which representation* of a region it wanted, which is a judgment about the member's content and therefore the leaf's to make. Until a real case needs that granularity, one address is one placeable unit — which also keeps *exhaustive* countable against something the leaf already partitions itself by.

The deconstructed form is admitted under two constraints. Both are checks against the leaf, not conventions to remember:

**Match.** Every chained suffix MUST equal, character for character, an address the leaf carries on one of its own segments. A parent may name a region the member has **already declared**; it may never invent one. This keeps the parent out of the business of measuring someone else's pixels — the crop is the leaf's claim, made once, in the one place it is checkable against the bytes it crops.

**Exhaustive.** If a member is placed deconstructed, **every distinct segment address on its leaf MUST be placed**. A member is placed whole or placed in full, never in part; the two forms may not be mixed for one member. Partial placement would let a parent quietly drop a region — a silent and entirely plausible omission — and would let *some of the member* and *the member* look alike in the record while differing in what they show.

Together the constraints make drift **mechanical rather than silent**. If the leaf re-crops, gains a region, or loses one, the parent's chained addresses stop matching the leaf's and lint says so at the next gate. The alternative — a parent restating geometry it measured for itself — resolves to *something* forever, and a region that has quietly moved while still resolving is precisely the failure the match constraint exists to prevent.

Promotion is unaffected, because it binds at the **member's** grain: N deconstructed placements name one member, one roster row, one blake3, one leaf. **No crop is ever promoted** — a crop has no independent bytes and no blake3 of its own, which is the same line §4.3.1.4 draws for whether a roster row exists at all.

Ordering needs no new rule. A placement's position in the content zone is the *parent's* reading order, which has always been the parent's own claim: an ordered-axis form keeps its `monotonic` address check and a generic form does not have one, because `el=` is an extraction index rather than a reading order (§7.8). Deconstructed placements inherit that unchanged. So a parent whose source packed two subjects into one two-up print figure may read them in the order its subject demands — the exhaustiveness constraint is what makes the freedom safe, since nothing can be hidden by reordering that could not equally be hidden by omission, and omission is what is forbidden.

###### Placement means promotion

A member positioned by a placement **must** have a record (§8.1) — that is the rule the kind exists to make statable, and it runs in one direction only. Promotion is not automatic and an **unplaced** member never needs it: the roster is unabridged by design (§4.3.1.4), and a favicon, a spacer gif, or a container member nothing has yet looked at stays a row and nothing more. What forces a record is the act of *placing*, because placing is the record saying this asset is part of how it reads, and the only faithful representation of an asset is one made from the asset's own bytes.

The consequence worth stating plainly is the one that makes the arrangement pay: **one leaf serves every parent.** A member appearing in N records is rendered once. Which fixes the invariant that makes sharing sound — *context is an input to the normalize pass, never to its output.* A parent's context legitimately tells a pass what it is looking at (the lineage origin block supplies it, §8.1); the rendering the pass produces must be faithful to the member's bytes alone. A rendering that depended on which parent asked could not be shared, and the whole arrangement would be a duplication bug wearing a dedup's clothes.

###### A placement displaces the member's content, never the parent's structure

The parent keeps everything that is *about the parent's own bytes* — its headings, its byte-marks, its reading order, its form. What it stops carrying is the member's **content**. The two are easy to conflate when they name the same string, and the case that makes it concrete is common: a page declares `<h3>Refrigerant System Capacities</h3>` and then embeds a generated image of the table, with that same title drawn into the pixels. Both records record it, and neither is a duplicate of the other — the parent's byte-mark records *that the page declares a heading here*, checkable against the page's bytes; the member's caption records *that the table is titled this*, checkable against the image's. Two records, two facts, two sets of bytes that happen to share a string because the producer rendered one label twice. Deleting the parent's mark would leave the page's own declared structure unrecorded, which is what §4.3.2.3 exists to prevent — on such a page it is frequently the only TOC entry there is.

Which settles the converse too: **a member's own title is part of its rendering, not a byte-mark on it.** A byte-mark records structure the source *declares* — a heading element, a nav target, an outline entry, a chapter (§4.3.2.3) — and a title drawn in pixels is *rendered*, not declared; reading it as a heading is an interpretation of layout. It belongs inside the lossless rendering that already interprets that layout, which for a table is the `<caption>` its own grammar provides. A mark would also need a position to point at, and on a record whose rendering is the whole transport there is none to give it without inventing one (§4.3.2.2).

###### Scope: a transport within a transport, never a region of one

The rule reaches exactly the assets that have a roster row, and no others. A **region** of the record's own transport — a rastered PDF page, a `bbox=` crop of a single-image artifact, a video `frame=` — has no member row, no independent blake3, and no leaf to promote to; it stays a content-atom marker with its transcriptions beside it (§4.3.2.2), and nothing here touches it. The distinction is not a convention to remember: it is already exactly the line §4.3.1.4 draws for whether a row exists at all.

A region **of a member** is the case worth stating, because it looks like the exempt one and is not. `el=<N>&bbox=…` chains a crop onto a member's address, so what it renders is the member's pixels — the member's own record is where that rendering belongs, and the address it takes there is the crop alone (the fractions were always relative to the member's extent, so nothing is recomputed). A whole-frame crop (`bbox=0,0,1,1`) is not a region at all — §4.3.2.2 already says so — and takes the whole-transport address, which is to say none.

###### The two demands, at their two grains

A placed member in the wrong state is two different defects, and each lints where it can actually be fixed (§8.5):

- **Placed with no record** is the **parent's** defect — no leaf exists, so nothing else could carry the finding, and the check is cheap: the leaf's path is a pure function of the roster hash, so existence is a stat. It is an **error**: a record positioning bytes it has not promoted has named a rendering that cannot be reached.
- **Promoted but not yet rendered** is not a defect at all — it is **demand**, and it belongs to the leaf. A leaf placed in N parents carries N-fold **normalization pressure**, which is a second source on the same mechanism the ledger's citation discipline already drives (§8.5, `ledger.md` §6.3), so the queue can be ranked by how much of the corpus is waiting on one pass. Nothing gates on it; a leaf standing as its artifact's proxy is a complete record (§4.1).

###### Worked example — table images in one HTML article

```
<!--members
- address: el=87
  media_type: image/png
  transport: blake3:cefda49d…
  bytes: 63420
- address: el=93
  media_type: image/png
  transport: blake3:010894ee…
  bytes: 51420
-->

<!--section document-->

<!--segment structural
address: el=71
level: 3
-->

Underhood Fuse Block

<!--segment placement
address: el=87
-->

<!--segment placement
address: el=93
-->
```

and, on the record whose id is `cefda49d…`:

```
<!--artifact image/png-->

<!--origin
uri: corpus://<the article>?el=87
snapshot: …
-->

<!--segment text/data-table
-->

**Fuse Block - Underhood, Device Usage**

| No. | Device | Rating | Description |
|---|---|---|---|
…
```

The article says where the two tables sit; each table says what it contains, once, at the whole-transport address (no `bbox=0,0,1,1` — the rendering is of the whole artifact, §4.3.2.2), and a third article embedding the same PNG reaches the same rendering by placing the same hash.

#### 4.3.3 The annotations zone

The annotations zone carries observations about **this record's representation of its bytes** — never about the bytes' meaning. One block family, the **context block**, and two namespaces: **`issue`** (§4.3.3.2) — where the representation falls short — and **`sweep`** (§4.3.3.6) — where a sparse extraction class has been carried to exhaustion. Context **never** contributes to the faithful content zone — it is a side-channel that accretes without disturbing the lossless body.

**Why the zone survives the faithfulness rule at all.** A record asserts nothing about itself (§4.3.2.2), and an issue is not an exception to that: it is a statement about the **capture**, not about the content — the same category as the `touch:` chain, an origin block's `source_transport`, or a declared chrome strip. When a marker says *the bytes are here, read them* and the reason is that we tried to render them and could not, that has to be recordable, or unachieved faithfulness becomes invisible. The issue is the **complement** of the body-empty marker: the marker offloads to the bytes, the issue records that the offload was forced. Without it a paywalled page and a fully-transcribed one are indistinguishable in the record, and there is no worklist. The **sweep** is the same statement's positive twin: that a pass extracted *everything* of one class a band holds is likewise a fact about the capture that only the pass which had the whole band open could know — without it, three on-screen-text segments left by an exhaustive sweep and three left by incidental gleaning are indistinguishable, and exhaustiveness is unrecordable (§4.3.3.6).

**Context is scarce by design, and scarce by construction.** Absent a real fidelity problem or an earned exhaustion judgment the annotations zone is **empty** — the normal state for the overwhelming majority of records. It is emphatically **not** a normalizer scratchpad: a normalizer MUST NOT emit commentary, summaries, running notes, or "what I did" prose as context, and it cannot do so by accident, because no context namespace carries a prose field (§4.3.3.2, §4.3.3.6).

Content-*meaning* observations of every kind are ledger material; the annotations zone records only what is faithfulness-scoped. (The retired `reference`, `relation`, and `concept` namespaces — §4.3.3.3–§4.3.3.5 — each moved to the layer that owned their content.)

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

Per-id overlays (`context/issue/<id>`) extend with id-specific fields. The `severity`/`resolution` value sets are corpus-local (schema-declared); external tooling should treat unknown values gracefully rather than assuming a fixed vocabulary. Issues come from three sources — the **deterministic pipeline** (mechanical detections at capture/ingest: bot blocks, corrupt encoding, missing inputs), the **normalizer** (faithfulness problems found while rendering), and **external** health-signal sweeps — each recorded in `detector` and, where engine-owned, `provenance: auto`.

**An issue is a typed code at an address, and carries no prose.** Its whole payload is `(<namespace>/<id>[/<subtype>], address, severity, resolution, detector)` plus whatever **structured** id-specific fields its overlay declares — a count, a URL, a signature. A sentence explaining the problem is the record narrating itself, it cannot be checked against anything, and it is the exact seam through which summary re-enters a zone that exists to be a side-channel. The type carries the meaning — `partial-content/paywall` at `el=12` needs no gloss — and this is the same obligation §4.3.2.2 puts on atom overlays: an issue id too vague to be self-explanatory is under-specified, and the fix is a **better id**, never a sentence. Where a fidelity problem genuinely warrants explanation at length, it is an interpretation in the ledger, which can cite the record and be revised.

**An issue is not a derivation.** A finding that a read-time pass could recompute from the record and its schemas — *this record's derived title is generic*, *this record carries no form* — is a **health signal**, computed on demand, never persisted into records. Storing it makes the record assert a verdict about itself that goes stale the moment either side changes. The test: if a sweep over the corpus could produce the finding from what is already there, it belongs to health; if only the pass that had the artifact open could know it, it belongs here.

##### 4.3.3.3 The `reference` namespace *(retired)*

A `reference` block recorded a declared dependent link (a product page's manual) lifted from an origin overlay's `capture.references` declaration. Both halves had homes: **the link is content** — an anchor the source renders belongs in the faithful body as an ordinary markdown URL, its `attribution_text` being nothing other than the link's own text — and **the edge is a derivation** — whether that URL names a captured record is resolved at read time against the URI index (§12.4.7, §9.9) and never stored. The case the block was reaching for — a source referring to something *without* a link (a video naming a document by voice) — is an act of knowledge: a typed claim on the ledger concept, its evidence anchored at the span that makes the reference (`ledger.md` §6.3, §7). `capture.references` survives as a pure capture instruction (§7.2).

##### 4.3.3.4 The `concept` namespace *(retired)*

The concept block was the ledger's shadow: a per-record entity annotation resolved against an external knowledge base, built before an internal entity layer existed. The ledger replaces every part of it: record-scope *aboutness* is coverage and the artifact roster (`ledger.md` §9, §4.2); a span-scoped *mention* is claim evidence anchored by a functional URI; the external join key (`wikidata:Q…`) is a concept-level external-identity claim citing a mirrored reference dataset (`ledger.md` §6.5), made once, not stamped per record.

##### 4.3.3.5 The `relation` namespace *(retired)*

A `relation` block recorded a source-declared cross-link (a "related information" rail) as a side-channel, because the rail had been judged navigation and dropped from the body — then judged too valuable to lose. Both judgments were right about the rail and wrong about the conclusion: **the rail is content of a different form** — a navigational link set, `form/nav` (§7.8) — rendered as a trailing form span: faithful body content, in the source's own order, with the source's own labels, addressed on the artifact's own axis, and citable. The cross-record edge remains what it always was — a read-time resolution of the URL (§12.4.7), self-healing as targets are captured or removed. (`form/nav` and `form/index` are distinct shapes: an index's entries ARE the content; a nav span's entries point at content from beside it.)

**The general rule this leaves behind.** When content is present in the bytes and worth keeping, the answer is never a side-channel: it is a **span under the form that fits it**. If no form fits, the content is formless segments, which is also fine (§7.8's zeroth form). A record needing a place to put content that is *not* content is a record that has mis-classified something.

##### 4.3.3.6 The `sweep` namespace

A `sweep` context block (`<!--context sweep/extraction-->`) declares that one **extraction class** has been carried to **exhaustion** over a band of the record's address space: every region within the band that holds content of the declared class is represented by a stored segment of that class. Its universal overlay (`context/sweep/sweep.yaml` — the namespace-universal path, as `context/issue/issue.yaml`) declares:

- `kind` — the segment opener-id the sweep vouches for (`text/ocr`, `text/transcript`, `structural`). MUST resolve against a declared overlay (or name the structural kind).
- `detector` — touch identifier of the pass that swept the band (as `issue`'s).

The universal context fields carry the rest: `address:` names the band in the record's own address scheme (§6.1.1) — absent, the sweep covers the whole transport — and `provenance` follows §4.3.3.1 (`auto` for a deterministic full-band engine's emission, stripped and regenerated on re-run; asserted for an interpretive pass's judgment). Like the issue, a sweep is a **typed declaration with no prose field**.

The semantics:

- **A sweep widens what absence means, never what presence means.** Stored segments are honest with or without one (§4.3.2.2); what a sweep adds is the negative: inside the band, a region with **no** segment of the swept kind is a region that **holds no such content** — silence becomes a statement. Outside every sweep band the standing default holds: extraction of any class is **sparse**, stored segments are honest annotations of where somebody looked, and the bytes remain the band's representation — a reader owes an unswept band a real read (playback, contact sheets, the resolver) before concluding anything from what is *not* segmented there.
- **Fail-closed, earned.** No declaration is ever implied: a record with no sweep blocks is sparse everywhere, which is exactly today's honest reading of every existing record. Only a pass that actually processed the **entire band** may write one — a sweep is a claim about work done, checkable against nothing but the pass that did it, which is why it carries `detector` and rides the touch chain like every other layer.
- **A sweep never asserts rendering.** It does not flip its band to "faithfully rendered": body-empty markers inside a swept band keep their §4.3.2.2 meaning (the bytes are the region's representation), and a formed span needs no sweep — a rendering contract's conformance already binds its span whole (§4.3.2.1). Sweeps exist for precisely the population rendering contracts don't cover: sparse extraction over formless and terminal records — a media stream's on-screen text, a scan's OCR'd regions, a container's structural marks.
- **An empty sweep is meaningful.** A band holding zero segments of the swept kind is a valid, valuable declaration — *no on-screen text appears in this range* — and exactly the statement no sparse record can make.
- **Coherence is lint-enforced.** `kind` MUST resolve; `address` MUST parse in the record's scheme; two sweeps of the same `kind` MUST NOT overlap (a widened re-sweep replaces the band, never stacks on it).

Sweeps surface through the derived `context` view (§9.2's sibling projection), and health's per-record completeness summary derives from them — spans under rendering contracts, swept bands per class, and the passthrough remainder — reported, never stored (§4.1). Downstream, a swept band is what makes **absence citable**: a ledger claim that something does *not* appear in a band is groundable only where the band was swept for it; the citation grammar for that negative evidence is a named extension point in Part III's evidence contract (`ledger.md` §6), landing there when a real claim demands it, never here.

### 4.4 Classifications: scope and fidelity

Classifications identify what a record (and its segments) IS — **structurally**: its format, its retrieval source, the form of its content. What a record's content *means* is not a classification at this layer; it is ledger knowledge (`ledger.md`). The framework rests on two ideas: what *kind* of classification is being made (four axes) and what structural *scope* it applies at.

#### 4.4.1 The classification axes

Every classification falls along one of four conceptual axes. Each axis has its own block surface, its own schema namespace, and its own scope rules.

| Axis | What it identifies | Block surface | Schema namespace |
|---|---|---|---|
| **media-type** | The format / container / transport of the bytes. | artifact block (exactly 1) | `mime` |
| **origin** | Where the bytes came from. | origin block (1..N) | `origin` |
| **form** | What structural shape a span of content decomposes into. | **section-block opener** (0..N spans) | `form` |
| **atomic** | What *form* of atomic content a segment carries. | segment-block opener | `atom` |

**media-type** and **origin** are properties of the bytes — record scope only. **atomic** is a structural-form judgment at segment scope. **form** is the same structural-form judgment one level up — what shape a *span* of content decomposes into (a conversation, a statement, a receipt) — checkable against the bytes like everything else in the faithful zone, applying at section scope (a single form span whose envelope covers the whole content zone being the record-scope case; §4.3.2.1). The ladder is uniform: record blocks bind mime/origin; section openers bind form; segment openers bind atom.

The form axis is **not** the retired composite returning (§4.3.1.3, §7.4 — both tombstones intact): composite asserted *meaning* (what content is about — a subject, a domain judgment), which lives in the ledger as claims; form names a *shape* — a decomposition contract with mechanical facts — and can no more assert meaning than a `text/data-table` opener can (§7.8 states the discipline normatively).

Atomic-axis schemas declare two extra keys beyond the universal classification fields:

- `applies_to.atom` — which atom this overlay attaches to (`text`, `image`, `audio`, or `video`). Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `enables_lossless` (boolean, default false) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's declaration describes what shape the body takes.

A segment carries **exactly one** atomic class id, on the opener line. When multiple representations apply to the same source region, each becomes its own segment.

#### 4.4.2 Scopes

Classifications attach at three structural scopes — record, section (span), and segment — plus the **member**, where the media-type axis attaches via each member row's `media_type`:

| Axis | Record | Section (span) | Segment | Member |
|---|---|---|---|---|
| media-type | ✓ (artifact MIME) | — | — | ✓ (per-member `media_type`) |
| origin | ✓ (origin block) | — | — | — |
| form | ✓ (a single span whose envelope covers the whole content zone) | ✓ (a span section) | — | — |
| atomic | — | — | ✓ (segment opener) | — |

#### 4.4.3 Section scope *(dissolved)*

The section-scope composite (a passage's identity — "this section is a recipe") and the identity+role dual-composite citation model are both expressed as **ledger claims over section spans**: span-precise evidence URIs make "what this passage is" and "what this passage does here" two claims about one anchor, with no record-side mechanism at all. What lives at section scope now is the **form axis** (§4.4.1) — a structural-shape judgment, checkable against the bytes, binding a `form/` overlay on the section opener. A passage's *meaning* stays retired at this layer: it remains a ledger claim over the span, and no form overlay may carry it (§7.8).

#### 4.4.4 Scope-driven fidelity *(retired with the composite namespace)*

The three field groups (descriptive / structural / citation) organized composite extended fields by scope; composite fields are now claim values and qualifiers in the ledger.

#### 4.4.5 The citation ladder *(retired with the reference block — §4.3.3.3; a link's position is wherever the faithful body renders it)*

#### 4.4.6 Provenance

A record's metadata and annotations have one of four **provenances** (who put a datum there, and what re-running does to it):

| Provenance | How it appears | On re-run |
|---|---|---|
| **structural-derived** | `mime/*`, `origin/*`, `form/*` — walked from the artifact / origin blocks and section openers (§9.1) | recomputed |
| **attested** | ingest-stamped byte-facts: artifact-block fields, manifest members, structural byte-marks whose address family the mime schema's `attest:` declares (§4.3.2.3), sidecar-lifted origin fields | re-attested (stripped + regenerated) by re-ingest / re-attest (§8.3) |
| **auto** | a context block with `provenance: auto` — a detector or overlay-declared emission | stripped + regenerated from the current overlays by a re-run of the owning pass (re-normalize) |
| **asserted** | a context block with no `provenance` — human / normalizer (faithfulness issues) | never touched |

A **form section** is stamped by one of two paths, both recorded in the touch chain: **declared** — the record's origin overlay declares its form (§7.2), and the shaper stamps + conforms the span mechanically on the normalize pass (regenerated on re-shape); or **asserted** — an interpretive pass recognizes the shape on a record whose origin is generic, and the pass's model identifier is in the chain (§4.2.2). Recognition may come from any layer — a ledger scribe reading across the corpus is exactly who will spot that some old PDF is really a transcript — but the record mutation always goes through the corpus normalize pass and its lint gate (a worklist entry, then a re-normalize dispatch); scribes author knowledge, normalizers author faithful form. A wrong assertion fails form-coherence lint immediately (§4.3.2.1); a wrong-but-lint-passing one is corrected by a later asserted pass, auditable in the chain.

#### 4.4.7 Re-run lifetime

Metadata-, content-, and annotations-zone material persists across re-runs **unless the pass that owns it is itself re-run**. There are exactly two owning passes:

- **Ingest / promote own the attested layer** — the artifact block's fields, manifest members, structural byte-marks, sidecar-lifted origin fields, origin stamping. A **re-attest** (§8.3) strips and regenerates them from the current schemas; it never touches the authored layer.
- **Normalize owns the authored layer** — the stored content zone (total replacement per pass: shaper or agent, same discipline), the form span's declared fields, and asserted faithfulness issues. A re-normalize refreshes it; it never touches attested facts except to *read* them. The authored layer is faithful renderings, form declarations, and typed fidelity issues — nothing interpretive.

`provenance: auto` context blocks belong to whichever pass's overlay declared them and regenerate with it; asserted context blocks are never auto-touched. There is nothing between the attested facts and the authored form. To deliberately reset everything, `re-stub` (§8.4).

---
## 5. URIs and references

### 5.1 URI forms

Two URI forms appear within the corpus:

- **Plain URLs** — the source's own links, carried verbatim in segment bodies whether or not their targets are captured. Reconciliation to intra-corpus references is a derived view (§12.4.7), never a stored rewrite.
- **Functional URIs** — `corpus://<hash>[?<params>]` — composable references resolved to derived views (§6). They are the **read-time** address language: tooling, ledger evidence, and agent instructions name surfaces with them. They are never stored in a record's content zone (§4.3.2.2); the one place a `corpus://` string is persisted is a promoted record's origin lineage `uri:`, which is history, not a lookup route (§8.1, §12.9).

### 5.2 Re-capture

If the same bytes are encountered again, the record's identity is unchanged. The capture URL may differ across encounters, so origin blocks are append-only: each re-encounter checks the canonicalized capture URL against existing origin blocks' `uri:` entries and either appends to an existing origin's `uri:` list (when the new URL aliases an existing origin via known shortlink/redirect rules) or emits a new origin block (when it's genuinely a separate source). A re-dropped local file (a uri-less origin) dedups by `filename` instead of a URL — the same bytes under the same name append no duplicate origin, while the same bytes under a *different* name record a distinct local source (its own origin).

If a URL re-fetched later yields different bytes, the new content produces a different hash and therefore a different record.

### 5.3 Referencing a region in another record

A functional URI addresses a **region** of a record — encode the address in its query string:

```
corpus://<hash>?<address-keys>
```

The form serves read-time reference — tooling, ledger evidence, agent instruction — and is never stored in a record's content zone (§4.3.2.2). It carries the **address only**, so it resolves to the region (and the asset or derived view at it), not to one specific representation: where same-region stacking places several segments at one address (a segment's in-record identity is `(opener-id, address)`, §4.3.2.2), those representations are distinguished only within the record, not by a cross-record reference.

---

## 6. Functional URIs

### 6.1 Grammar

```
corpus://<hash>[?<params>]
```

- `<hash>` — blake3 hash of the source artifact, 64-char lowercase hex.
- `<params>` — `&`-separated key/value pairs and flag-style keys. Order is significant — parameters compose left-to-right, each operating on the previous step's output. A param **value** percent-encodes the query-reserved characters `%`/`&`/`#` as `%25`/`%26`/`%23`; the parser decodes, and canonicalization re-encodes. Values may therefore carry any character — archive member names are producer-controlled (`?path=…D%26D 5e….json` addresses a member literally named `…D&D 5e….json`).

Bare `corpus://<hash>` resolves to the source artifact's bytes — with one declared exception *(v35, owner ruling)*: a **markup artifact** (the `el=` family, §6.1.1) delivers its **annotated view** by default, and `corpus://<hash>?raw` yields the stored bytes exactly. The identity invariant is untouched — the store holds the original bytes, attestation hashes them, and for markup the checkable equation keys on the `raw` route (`blake3(corpus://<hash>?raw) == <hash>`); for every other type the bare route is the raw route. `corpus://<hash>?<params>` resolves to a derived view per §6.2.

#### 6.1.1 The `el=` ordinal — the HTML address space

`el=<N>` names an element in a markup artifact by its **document-order ordinal** *(v35)*: the 1-based position of the element in a depth-first pre-order walk of the artifact's body. `el=1` is the body's first element child; its descendants take the ordinals immediately after it, before its next sibling. Text nodes, comments, and attributes are not counted — only elements. Two properties fall out of pre-order for free: numeric order **is** document order, and a subtree occupies a **contiguous ordinal interval**.

**The space is total.** *Every* element is addressable. There is no predicate deciding which tags may be named, and this is substance rather than convenience: any such predicate is a **versioned contract that records do not record** — adding one tag to a whitelist silently re-points every stored address that crosses an instance of it, with nothing in the record to say which version produced it and no gate able to detect the difference. A total space cannot be revised, so it cannot rot.

**What a drafter emits is a separate question.** Which elements get their own segment is an authoring heuristic owned by the drafter and the form contracts — it may change in any release, add or drop element kinds freely, and none of that changes what an existing address *means*. Splitting the two is what buys permanence: the space is mechanical and frozen; the taste is free.

**Relation is legible from the tree, not the address** *(the v35 trade, owner-ruled)*.

- **Order** — plain numeric comparison, which is document order by construction. No sort trap.
- **Containment and siblinghood** — properties of the parsed tree: `A` contains `B` iff `B`'s ordinal falls inside `A`'s subtree interval, and two ordinals are siblings iff their elements share a parent. Neither is decidable from the two numbers alone. This is the deliberate trade against the dotted child-index path this space replaces (history, CHANGELOG v35): the path bought address-local containment at the price of addresses no human could read, compare, or cite (`el=1.2.2.1.3.1.4.1.8.3`), and measurement across the live consumers showed the algebra always ran beside a parse anyway — span checks, envelope derivation, lint, and verify all walk the artifact, and the attested parser identity (below) guarantees every walker sees the same tree. What had to survive the trade, and does, is totality.
- **A subtree is one address.** The container's own ordinal names it and everything under it, exactly.

**Ranges.** Three forms:

| form | meaning |
|---|---|
| `el=7` | the element **and its whole subtree** — the common case, and free |
| `el=[12-19]` | **sibling range**: the elements at ordinals 12 and 19 — which MUST be siblings — and every element sibling between them, subtrees included |
| `[el=7, el=42]` | an ordered **list** — disjoint landmarks (§4.3.2.2) |

**The sibling constraint is normative, not advisory** *(owner ruling)*: a range whose endpoints do not share a parent element is an invalid address — refused at resolution and a lint **error** (`address-el-range-invalid`) on a stored value, checked against the attested parse exactly as a point ordinal is bounds-checked. The syntax could carry a flat "from here to there" that cuts across structure; the grammar deliberately refuses to let it mean anything, because such an interval is not one structural thing — endpoints at different depths name a region no element of the artifact declares, and a flat document-interval range is how over-claiming envelopes arise. The bracketless `el=<a>-<b>` spelling remains the retired flat form and is rejected with its own message.

**Address up, never across** *(owner ruling)*. When a region spans more than a clean sibling run, the address is the **lowest common container element** — one ordinal, one subtree — never a longer bridge. The mechanical envelope derivation (§4.3.2) applies this in order: claims contained in another claim drop; one survivor is the envelope; survivors forming a contiguous sibling run collapse to the range; anything wider takes the common container's own ordinal. The ordered list remains an authorable address form for genuinely disjoint landmarks, but the derivation never emits it. This is the same honesty rule as prose with no element of its own (below): one segment at the container beats a claim that stitches together structure the artifact does not declare.

**The space names elements, so text in no element has no tight address.** Making every element addressable does not make every *region* addressable. Prose emitted as bare text nodes between `<br>`s in a flat `<div>` belongs to no element but its container, and the container is routinely the page's whole content. This is not a gap to be closed by a fourth range form: a character-offset address would name a region that is not a structural thing and would re-point on any reparse, losing the permanence a total space buys. **The honest response is at the record layer, not the address layer**: where several segments' prose shares one container and none has an element of its own, they are one region of the artifact and belong in **one segment** addressed at that container (§4.3.2.1 — a span that is a subtree *is* that subtree's own address). What is lost is the prose's internal ordering against the pictures interleaved with it; what is gained is that the record stops claiming a picture's address for a paragraph.

**Ordinals are counted by machines, never by eyes — so the machine count is what readers get** *(owner ruling)*. The **annotated view** — the artifact with every element's ordinal stamped on its own start tag as a `data-el="<N>"` attribute — is the **default delivery** of a markup artifact: bare `corpus://<hash>` resolves to it, because nearly every reader of delivered HTML is there to cite it, and an address authored any other way — counted by hand, inferred from position — is a guess, the failure class the attested parse checks exist to catch. The stamping **fully maintains faithfulness by construction**: it is a span-surgical splice into the original bytes (the header-strip / `strip_fields` discipline — each element's start tag gains the one attribute; no re-parse, no re-serialization, no byte the source carried moved or altered), a pure derivable function of the raw bytes, provable by re-derivation. `?raw` (§6.2) yields the stored bytes exactly — the route the identity equation keys on for markup, and rarely needed otherwise.

**Two attested facts keep drift loud.** The ordinal is a function of the *parsed* tree, so the parse is part of the contract. The artifact block carries the **parser identity** the addresses were computed under and the total **element count** (§7.1 `addressing`). A resolver whose parse yields a different count knows immediately that it disagrees, and says so — instead of silently resolving an ordinal to the wrong element.

**Three grammar generations, dispatched by the record, never the value** *(v35)*. The spelling `el=5` has meant three things across this space's history — a filtered-whitelist index, a single-component child path, and today's ordinal — so the **record** picks the grammar: an `addressing` stamp carrying `scheme: ordinal` (§7.1) marks this space; a stamp without the key is the frozen dotted-path era; an unstamped record is the frozen whitelist era. Both frozen grammars remain resolvable read-only, exactly as stored, and both are scheduled out by the v35 remap (CHANGELOG). Sniffing the value is forbidden — it resolves silently to the wrong element, the exact failure the stamp exists to end.

### 6.2 Transformations

The transformation table is also the home of the **derivation ops** — mechanical extractions exposed as resolver operations: on-demand, cacheable, reproducible, consumed by the normalize pass and by any reader (a just-attested record is fully readable through them).

| Param | Input type | Output type | Description |
|---|---|---|---|
| `page=<N>` | PDF | image | Select page N (1-indexed). On its own it renders the page as an image; an image op or `bbox=` after it auto-renders first. |
| `page=<N>&render` | PDF page | image | Render the selected page as an image (the explicit form of a terminal `page=<N>`). |
| `page=<N>&text` | PDF page | text | The page's embedded text layer, verbatim — not an OCR of the raster; empty when the page carries no text layer. |
| `page=<N>&words` | PDF page | json | The page's text-layer words, each with a `bbox` (`[0.0, 1.0]` page fractions, origin top-left). |
| `page=<N>&probe` | PDF page | json | Per-page structural signals: dimensions, rotation, text/image-coverage stats, an invisible-text flag, and an advisory shape hint. |
| `probe` | PDF | json | Whole-document structural probe: per-page table, `/Info`, outline presence, and a shape summary. |
| `outline` | PDF | json | The PDF outline / TOC tree (nested `{title, page, children}`). |
| `time_range=<s>-<e>[,<s>-<e>…]` | media container / stream | media slice | A cut of the **composition** (on a container: the default member of each kind, muxed — the muxing contract, below) or of one stream (after `stream_id=`). A comma-delimited ordered list concatenates cuts in listed order. |
| `stream_id=<id>` | multi-stream media | stream-isolated | Select a specific stream. **Terminal**, it materializes the member's identity bytes — the raw payload (§2), byte-identical to resolving the promoted leaf's bare id. With further ops it selects the stream for the derived-rendering chain (cuts, `format=`, `transcribe`), which runs against the derived playable surface. |
| `frame=<N>` \| `frame=<A>-<B>` | animated image / video | image / — | **Polymorphic** (see below). On an **animated image** (GIF, animated WebP/AVIF): a **1-based ordinal** selecting one frame of the sequence, bounds-checked against the attested `frame_count`; leads its chain, so `frame=3&bbox=…` names a region *of frame 3*. The inclusive span form `frame=<A>-<B>` is a **stored-address assertion** (§4.3.2.2 — a rendering that holds across every frame in the span); it names no single byte surface and does not materialize. On a **video**: a timecode (seconds or `HH:MM:SS`) rendering the frame at that timestamp to an image. A stored image-side value that breaks the ordinal grammar, exceeds the attested count, or trails a region param is a lint ERROR (`address-frame-invalid`). |
| `bbox=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Crop a relative region (image: floats in `[0.0, 1.0]`, origin top-left) or narrow a worksheet (spreadsheet: an A1 range, e.g. `bbox=B2:G30`). Polymorphic — see below. The 3rd and 4th values are a **width and a height, not a second corner**: `x+w` and `y+h` must each be ≤ 1. A stored region-op value that breaks this grammar is a lint ERROR (`address-region-invalid`). |
| `crop=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Alias for `bbox` (inherits its polymorphism). |
| `mark=<x>,<y>,<w>,<h>[;…]` | image | image | Outline the region(s) on the **whole** image (does not crop) — the inspection dual of `crop`, showing where a region sits in context. Relative floats in `[0.0, 1.0]`; `;`-separated for multiple regions. |
| `cover=<x>,<y>,<w>,<h>[;…]` | image | image | Paint the region(s) **out**, filled with the background colour sampled from the ring just outside each box (never assumed white). The chrome remover, for captures that baked a viewer's own controls into the artifact. Does not crop — chain `crop=`/`bbox=` after it when a crop is also wanted. Lossy by nature (it deletes pixels), and disclosed by riding the address: the same surface resolves without the op to show what was removed. Same grammar as `mark=`. |
| `resize=<W>x<H>` | image | image | Resize to absolute pixel dimensions (forces both, may distort or enlarge). |
| `fit=<W>x<H>` \| `fit=<preset>` | image | image | Downscale to fit within a bounding box, aspect-preserving; reduce-only (never enlarges). A `<preset>` names an implementation-defined budget. |
| `rotate=<90\|180\|270>` | image | image | Rotate clockwise by a quarter turn (lossless; 90/270 swap width and height). |
| `auto_orient` | image | image | Apply the image's EXIF orientation tag so a sideways/flipped capture displays upright. No-op when absent. |
| `autocontrast` | image | image | Stretch the per-channel histogram to full range (legibility for faint scans). |
| `contrast=<factor>` | image | image | Scale contrast by a float factor (`1.0` unchanged). |
| `grayscale` | image | image | Convert to single-channel grayscale. |
| `dpi=<N>` | (render config) | (config) | Rasterization DPI for `page=<N>`. Position-independent. Default 200. |
| `body` | any | markdown | The record's **derived body** — the faithful mechanical rendering: DOM→markdown under the overlay's capture-time chrome config (HTML), spine text (EPUB), reply-text trim (eml), verbatim passthrough (JSON, plain text), page markers (PDF). A pure function of (artifact × schemas × op version); what `corpus body` prints for a formless record. |
| `members` | any transport with embedded assets | json | Member enumeration over every address axis (`el`/`spine`/`path`/`msg`/`part`/`card`/`stream_id`/…) — the roster **with its full descriptors**, derived. Beyond the stored row's four keys (§4.3.1.4) it carries every mechanically-readable per-member fact: pixel dimensions, verbatim `alt`, member filename, an email member's `from`/`subject`/`date`, a vCard's display name. The surface a normalize pass consults to see what an artifact carries — never the block, which by design says less. |
| `annotated` | HTML | html | *(v35)* The **annotated view** — the artifact's original bytes with every element's document-order ordinal (§6.1.1) spliced into its own start tag as a `data-el="<N>"` attribute, span-surgically (no re-parse, no re-serialization; every source byte kept in order). The authoring surface, and the **default delivery**: bare `corpus://<hash>` on a markup artifact resolves here, so a reader cannot cite by guesswork — the correct coordinates are forced into view. Computed under the record's attested parse, version-labeled (§6.4), cache-only, provable by re-derivation. **Terminal only**, like `raw` — a delivery view, not a working step: ops run against the raw parse, never against stamped bytes. The explicit spelling exists for disclosure and symmetry; it and the bare route are one resolution, one cache entry. |
| `raw` | any | bytes | *(v35)* The stored artifact bytes, exactly — for a markup artifact, the escape from the annotated default (rarely needed: byte-level verification, re-export, external diffing); for every other type the bare route already is this. `blake3(?raw) == <hash>` is the identity equation's markup spelling. Terminal only — it composes with nothing. |
| `transcribe` | audio / audio stream | json/text | Speech-to-text over the addressed audio, with timestamps and speaker-turn indexes where determinable. **Version-labeled** (§6.4): the result carries engine + model version. |
| `scene` | promoted media stream leaf | json | The leaf's **cut list** under its stamped `cutting:` strategy (§7.1): the resolved strategy, every span with its `time_range=` address and length, and the degeneracy signals (`no-boundaries`, `over-segmented`). The introspection surface an authoring pass reads before deciding anything — `probe`'s role for a PDF page, on a timeline. Runs the **stamped** strategy, never a fresh resolution, so this op can never be the route by which a record is silently re-cut; an unstamped leaf answers `unresolved` rather than failing, because that is a legitimate state (§7.1). |
| `turn=<N>` | turn-structured record | json/text | The verbatim N-th unit of the record's declared unit array (1-indexed), located by the origin overlay's form mapping (§7.2) — for a chat transcript, the complete message object: reactions, edit history, attachment declarations, platform ids, one hop away from the envelope segments. |
| `turn=<N>&att=<M>` | turn-structured record | bytes | The M-th attachment declared by unit N, materialized through **lineage-chained resolution** (below). |
| `cut=precise\|copy` | (cut config) | (config) | Cut semantics for `time_range=` (the muxing contract): `precise` (default — frame-accurate, re-encodes) or `copy` (keyframe-snapped stream copy, disclosed). Position-independent, like `dpi=`. |
| `format=<token>` | media / image | converted rendering | Output-format conversion, composing **after** selection and cutting (the muxing contract): `time_range=12:04-12:09&format=gif`. Changes encoding only, never the addressed content. |
| `scenes=<threshold>` | video / stream | boundary proposals | Scene-cut boundary proposals over the video timeline — a text listing of cut timestamps at the stated detection threshold, engine-versioned (§6.4). Normalizer support for boundary work: proposals to be verified by the pass, never marks. |

A parameter applied to an incompatible working type is a hard error.

A PDF `page=<N>` is a **page selector**, not an unconditional render: a per-page op after it (`render`, `text`, `words`, `probe`) reads the *selected page* directly, so `page=<N>&text` returns the page's embedded text layer rather than an OCR of its render. A terminal `page=<N>` (and any image op or `bbox=` after it) renders the page to an image, so an `address: page=<N>` image marker (§4.3.2.2) still resolves to the page bytes. The whole-document ops `probe` and `outline` operate on the PDF itself (no page selected). These introspection ops are how a normalizer determines a PDF's shape and extracts its content — the attestation itself is uniform (§11).

`fit=` presets are **implementation-defined**, not enumerated here: a preset (e.g. `llm`) bounds the result to a consumer's budget — typically a vision model's maximum input dimensions and pixel count — and those limits are model-dependent and drift over time, so freezing them into the spec would rot. The normative contract is only that `fit=` downscales aspect-preserving and never enlarges; the concrete bounds of any named preset live in the resolver implementation.

Parameter value grammar may be media-type-dependent; the resolver dispatches on the source artifact's type. In particular `bbox` is **polymorphic** — relative floats in `[0.0, 1.0]` when cropping a rendered image (an image artifact, or a `page=` render of a PDF), and a spreadsheet cell range (e.g. `bbox=B2:G30`) when narrowing a worksheet region — so the same token does not collide across media types. `frame=` is polymorphic the same way: a **1-based ordinal** (or inclusive ordinal span) on an animated image, whose frames are a sequence with no timebase a reader can trust (GIF delays are per-frame and advisory), and a **timecode** on a video, whose timeline is the medium's own axis — the physics of each medium picks its reading, and the token does not collide. Pure **address selectors** that locate a region without transforming it — `sheet=<name>`, `el=<N>` (§6.1.1), and any others — are defined by each media-type schema (§4.3.2) and are not enumerated here; §6.2 lists only the parameters that produce a derived view.

**The muxing contract.** Media cutting, muxing, and conversion are resolver ops with normatively pinned *behavior* and implementation-owned *mechanics* — the contract maps onto ffmpeg's primitives, and exactly as with `fit=` presets, the supported codec/format sets are implementation-defined so the spec doesn't rot; only the behavior below is normative.

- **Composition cut.** `time_range=<s>-<e>` on a media **container** materializes a cut of the *composition*: default-member resolution (below) applied **per kind** — the unique-or-declared-primary video member plus the unique-or-declared-primary audio member — muxed into the source's container family. A kind with **zero** members is omitted from the composition — absence is not ambiguity (a silent video cuts video-only; an audio-only container cuts audio-only). Ambiguity within a *present* kind (two audio tracks, no declared primary) → the bare op fails stating it, never guesses. Subtitle tracks never ride implicitly — opt-in by selection.
- **Stream selection composes.** `stream_id=<id>&time_range=<s>-<e>` cuts one stream; an explicit subset is a comma list — `stream_id=0,2&time_range=…` — cutting exactly the named members, muxed.
- **Multi-cut.** `time_range=a-b,c-d` — the address grammar's ordered-list-for-non-contiguous-spans convention (§12.11), materialized: the cuts concatenate in listed order. Concatenation is safe by construction — every cut shares the source's codec parameters. This is the composition layer's supercut primitive: one URI names an ordered excerpt reel of one source.
- **Cut semantics, ffmpeg-honest.** The default is **precise** — frame-accurate, which re-encodes: evidence is the primary consumer, and a cited 5-second clip must contain *exactly* the cited span. `cut=copy` is the disclosed fast path — keyframe-snapped stream copy, whose bounds may widen to the previous keyframe; the URI says so, so nothing silently drifts.
- **Format conversion.** `format=<token>` converts the working result's encoding, composing after selection and cutting (`time_range=12:04-12:09&format=gif` on an MKV → cut, then convert). Rules: (a) conversion changes **only the encoding, never the addressed content**; (b) targets must be **atom-compatible** — video→`gif` is a video-to-animated-image rendering (audio dropped by the format's nature, not by editorial choice), audio→`wav`/`mp3` is fine, audio→`png` is a hard error; (c) the supported token set is implementation-defined per the resolver's engine (the `fit=` precedent) — the contract is behavioral; (d) `format=` names *explicitly* what existing ops already do implicitly — a terminal `frame=` renders to an image, a terminal `page=` rasterizes, transcription extracts audio to an intermediate wav — one parameterized surface for the same idea.
- **Canonical application order**, pinned so one URI is deterministic and composable: **select → cut → convert → size** (`stream_id=` → `time_range=` → `format=` → `fit=`). A downscaled gif snippet of one stream is a single composable URI.

Cuts, muxes, and conversions are **version-labeled ops** (§6.4): encoder output drifts across engine versions, so results are cache-keyed by engine version and pure per version. They are ephemeral derived renderings with exactly the standing of a `page=` raster — never new artifacts, never new records.

**Lineage-chained resolution.** A promoted record's resolver MAY chain through the record's own containment-lineage origin block (`uri: corpus://<container>?…`, §8.1) to materialize content its bytes *declare* but do not *contain*: read the declared reference from the record's own artifact (message N's attachment path), then resolve it as a member of the blake3-pinned parent container. The chain is derived at read time from (lineage block × record bytes) — never stored on any block — so it cannot rot: the parent is content-addressed and immutable, and an absent member (a reference the export never localized) fails loudly at resolve and surfaces in health, exactly the failure mode a stored pointer would have papered over. This is the transcript analogue of an HTML page's captured assets, with the container playing the role of the capture's asset store; it is also how a promoted track record inherits its container's chapter marks (§1.2) — reading up the lineage rather than copying down. (Lineage-chained resolution is a resolver read of corpus state, which resolve has always been — §6.3; the byte-lookup independence rule of §12.9 is untouched: lineage is consulted for declared-reference chasing, never for the record's own byte residence.)

**Route unification** *(v32; generalized to every member axis, v33)*. A promoted member leaf's identity bytes are the container-resident payload (§1.2, §2) — the identity equation `corpus://<leaf> ≡ corpus://<container>?<axis>=<n>` names one content two ways — so every op on the leaf resolves **through its container**: `corpus://<leaf>?<ops>` and `corpus://<container>?<axis>=<n>&<ops>` are **the same resolution** — one route, one derivation, one cache entry. The rule keys on the positive fact promotion writes and attestation never does (§1.2): a containment-lineage origin whose `uri:` is a member address of a blake3-pinned parent — and it holds for every member axis alike (`stream_id=`, `msg=`, `part=`, `path=`, `card=`, `entry=`, `item=`), because the payload-identity principle it rests on (§2) never was media law. For a media-stream leaf this is where the timeline lives: `frame=`, `time=`, `time_range=`, `scenes=`, and `transcribe` read the container's tables through the route and run against the derived playable surface, in the same timeline the container reports; a mail-message leaf's `part=` reads the container-resident message bytes the same way. Nothing about *addresses* changes — a leaf's axes are its own content's axes either way. A resolver SHOULD **disclose the base form** when resolving any promoted member leaf (print `≡ corpus://<container>?<axis>=<n>` alongside the result), so the equivalence is visible rather than merely true.

**Default-member resolution.** When an op requires a member of a given kind and the container holds **exactly one** of that kind — or the container itself **declares a primary** (HEIF's `pitm` primary-item box: a byte-fact, attested) — the member selector may be omitted and the op routes through transparently: `bbox=` on a Live Photo acts on the declared-primary still; `time_range=` reaches its motion component; `?transcribe` on a single-audio-track MKV needs no `stream_id=`. Zero candidates, or more than one with no declared primary → the bare op **fails stating the ambiguity** — it never guesses. Two properties are pinned. First, it is **read-side sugar only**: attested member rows always carry their explicit `stream_id=`/`item=` addresses, and nothing stored depends on the sugar existing. Second, it is **citation-safe by content-addressing**: the artifact is immutable, so whether a bare anchor is unambiguous is a *permanent fact of the bytes* — a citation that resolved once resolves forever, never invalidated by later state.

**Member re-chaining** *(generalized to every member axis, v33)*. A member materialized through **any member axis** (§12.11 — `path=` for a kept-whole archive, `msg=` for a mailbox, `part=` for a MIME message, `card=`/`entry=`/`item=` alike) is not necessarily a terminal opaque byte-string: once extracted, the resolver re-detects the member's own mime from its bytes and declared name and, when a further transform follows in the chain, re-enters the working-kind table (§7.1) for that mime — a PDF member takes `page=`/`text` exactly as a top-level PDF record would, a CSV member takes `row=`/`col=` (§12.11), a mailbox's message takes `part=` (`?msg=23&part=3` reaches an attachment through the mbox — the composition the mbox precedent always implied), and so on for every mime a `working_kind:` schema declares. A **terminal** member address (no further transform follows) never promotes to a full working-kind object merely to re-derive one — that would risk a silent, unrequested re-encode of a member no op asked to transform; it decodes only an already-textual member (JSON, plain text) to its text, so a citation prints cleanly rather than as an opaque cache path. A member whose mime supports neither — no declared working kind, not textual — stays the raw `bytes` a member axis serves by default, byte-identical to the address alone.

### 6.3 The resolver

A corpus provides a **resolver** that materializes any functional URI to a deterministic, cacheable, ephemeral result. Ops fall into two determinism classes:

- **Pure ops** — a pure function of (URI × artifact × op version): same inputs, same bytes, always. All address selectors and the mechanical derivations (`body`, `members`, `text`, renders).
- **Version-labeled ops** — ops whose engine output may drift across engine versions (`transcribe`; OCR performed through the toolkit; the muxing contract's cuts, muxes, and `format=` conversions — encoder output is engine-versioned, §6.2): the result carries its engine + version, and the cache key includes them. Determinism holds *per version*. All remain ephemeral derived renderings — a precise cut has the same standing as a `page=` raster, never a new artifact.

The resolver's surface (CLI, library, HTTP service, etc.) is implementation-defined; the contract is that the URI scheme of §6.1 and the transformations of §6.2 are honored.

### 6.4 Caching

Resolver results may be cached. Cache lifetime, eviction policy, and storage location are all implementation-defined; the spec mandates only that the result is deterministic and reproducible from inputs — for a version-labeled op (§6.3), the cache key includes the engine + version.

**Pinning by authorship.** Until a pass consumes it, a version-labeled result is cache-transient — it may be regenerated under a newer engine, and nothing *in the record* depends on which (a ledger citation of a derived surface pins the op version on its own binding — `ledger.md` §13.2 — so drift there flags loudly without the corpus storing anything). The moment a normalize pass **consumes** such a result into the stored body, the output is pinned *in the record*, with engine/version provenance on the pass (touch chain) and on the segments where the form carries it (`text/ocr`'s engine/confidence fields — the OCR-provenance philosophy, extended to transcripts): the corpus owns the derivation's provenance rather than laundering a pre-baked layer. A later pass re-derives only deliberately, disclosed by a new touch. This is what makes the absence of a stored mechanical body *reproducible*: a future normalize pass re-resolves the same surfaces — or knowingly upgrades them — without a stored intermediate rotting in between.

---

## 7. Schema declarations

§3 introduced the five namespaces and the schema-loader resolution chain. This section specifies what the four schema-declaration namespaces (`mime`, `origin`, `form`, `atom`) declare; the `context` umbrella's overlays are specified alongside the context block in §4.3.3.

### 7.1 The mime namespace

A `mime` schema declares everything the matching artifact block needs and everything ingest attestation and the resolver need to process the transport.

- `description` — prose definition.
- `applies_to.content_types` — list of canonical MIME types this schema covers.
- `applies_to.zip_members` / `applies_to.zip_member_patterns` (optional) — shape signature for a zip-shaped type whose telltale members sit under a *variable* wrapper directory (a diagnostics export, a backup bundle), so a fixed internal path can't recognize it. `zip_members` lists exact member paths (ANY present matches); `zip_member_patterns` lists member-path regexes (EACH must match some member). Evaluated by the shared MIME refiner against the corpus's schemas, so vendor/site-specific zip recognition lives in the overlay rather than the package. Universal zip formats (OOXML / EPUB / JAR) keep their fixed-path signatures in the tooling and need no declaration.
- `working_kind` (optional) — the resolver's initial working-value kind for the functional-URI transform pipeline (`pdf`, `image`, `audio`, `video`, `html`, `epub`, `zip`, …); falls back to a built-in table for the bundled types when omitted.
- `citation_surface` (optional) — the format's honest **citation-surface class**, consumed by the ledger's evidence verification (`ledger.md` §6.3, §13.2) and printed by `corpus inspect`: `raw` (the default — the record's derived body is faithful line-of-sight content, so record-wide verbatim quote matching is honest even on a formless record: JSON, plain text, CSV) | `segments` (the raw/derived whole-record text is presentation soup — nav chrome, script payloads, inlined framing — so quote matching against it is *misleading rather than merely weak*; until persisted segments exist the record is a **deferred surface**: claim evidence citing it is admissible but held unmatched and excluded from the ledger's confirmed bar, and the citation itself aggregates as normalize demand — cite-then-pressure, `ledger.md` §13.2.4; what the record attests mechanically — byte-facts, derivation-op output — verifies now). Built-in default: the HTML family is `segments`; every other bundled type is `raw`. The class governs *citation strength*, never readability — any actor may read and cite any record; the class decides only what the evidence can carry before the declared surface lands.
- `disposition:` — `manifest` | `work` (default `work`): the **container-vs-transport judgment** (§1.2), declared per format because it is not derivable from the bytes. `manifest` — the members ARE the content: every member attests as a manifest member (promotable), the content zone holds only container byte-marks. `work` — one transport whose content decomposes as units; internal member files the schema names attest as **exposable members** — addressable and promotable without being the content: a PDF's embedded files / portfolio members (the `attachment=<N>` axis, §12.11), OOXML embedded media and OLE objects. The authoring criterion is normative: *are the members independently meaningful transports?* An origin overlay MAY override for a deviant producer (§7.2); the resolved disposition is always auditable from the record's attested shape, never sniffed per record.
- `attest:` — the **ingest attestations**: which byte-facts ingest stamps at ingest time. Artifact-block fields (a PDF's `/Info`, an EPUB's Dublin Core, an eml's headers); **manifest members** for `disposition: manifest` types (archive members at `path=`, mail messages at `msg=`, cards at `card=`, calendar entries at `entry=`, MIME parts at `part=`, media tracks at `stream_id=`, image items at `item=`); **exposable members** for `work` types that declare them; **structural byte-marks** (a media container's chapters); sidecar lift (§7.2). Attestations are deterministic byte-facts; re-attest regenerates them (§8.3).
- `derive:` — the **derivation ops** the type exposes (§6.2), with any per-type config (a strategy-named general implementation may serve many schemas, as `zip-manifest` does).
- `address_scheme` — the parameters the schema expects in segment `address:` values.
- `whole_address` (optional) — whether a segment of this media type may omit its `address` to name the whole transport (§4.3.2.2). `admissible` — a single contained presentation, absence is the conforming form for a whole rendering. `forbidden` — an inherent sequence (no whole to name), or a total address space (the whole already has an honest address). `single_unit_only` — absence is admissible **iff** the artifact-block field named by `whole_address_count` equals 1. Default when the key is absent: `admissible` for a `disposition: work` type whose `address_scheme` declares only part-naming axes, `forbidden` for a `disposition: manifest` type — but the default is a reading aid, not a licence to leave it undeclared on a type whose bytes can go either way.
- `whole_address_count` (optional) — **required** when `whole_address: single_unit_only`: the artifact-block field carrying the count of the medium's sequence unit (`frame_count` for the animation-capable image formats). It names an attested fact, never a derivation — the gate is a comparison, so a type that cannot stamp its count at ingest cannot use `single_unit_only`.
- `cut_strategy` (optional) — for a format whose address space is a **timeline**, the default procedure that decides where its segment boundaries fall. Names a versioned strategy and its parameters: `{id: scene-threshold@0.1.0, threshold: 0.3}` — composing with the `scenes=<threshold>` derivation op (§6.2): the declared parameter is what the op is run at. The bundled strategies are `scene-threshold@` (a detector's dissimilarity measure crosses a bound — the default for a camera or screen recording), `keyframe@` (cut at container keyframes: free, since the demuxer already knows them, and honest where the encoder's own decisions track content), and `fixed-interval@` (every N seconds — the fallback that must exist, because a static screen recording yields no scene cuts at all and a scrolling one yields hundreds, and both mean *this strategy did not fit*). Parameters are a free-form map rather than a fixed `threshold:` key precisely so the concept does not harden around one detector. An **origin overlay MAY override** it (§7.2), which is the point: sensitivity is a property of what kind of thing was recorded, not of the codec. *(Distinct from `address_scheme`, which says a timeline is addressable at all; this says where one is cut.)*
- `framing` — *(retired, v32)* the stamp that admitted a muxing engine into the identity path, attesting muxer, version, flags, and a sample count onto a promoted leaf's artifact block. The payload-identity principle (§2) removed the engine from the identity path entirely — a leaf's bytes are a table-driven sample concatenation with no producer to attest — so the stamp's subject no longer exists. A leaf's artifact block MAY attest `samples:` directly (the engine-free count from the corpus's own table reader), which remains the like-with-like self-check `cutting:` and stored markers compare against. A `framing:` stamp surviving on a pre-v32 leaf is honest history of the bytes it described, not a defect; it retires with the leaf's migration. The general doctrine the stamp articulated stands, and the other stamps rest on it: `touch:` is provenance history — the transforms a record has been through — while a stamp is an **attested fact about the bytes as they now stand**, carrying its own disagreement check.

- `cutting` — **the stamp, not a schema key.** The mime schema declares the *default* (`cut_strategy`); the resolved strategy, its parameters, and its result are attested onto the **artifact block** of the stream leaf, exactly as `addressing:` stamps parser and element count (§6.1.1):

  ```
  <!--artifact video/mp4
  cutting:
    id: scene-threshold@0.1.0
    threshold: 0.3
    cuts: 33
    duration: 616.53
  -->
  ```

  The stamp carries the declaration's own keys **unrenamed**, plus the result (`cuts`, `duration`). A schema declaring `cut_strategy: {id: …, threshold: …}` stamps `cutting: {id: …, threshold: …, cuts: N, …}` — so stamping is a merge, never a translation, and there is no key-mapping step in which a parameter can be silently dropped.

  `cuts` counts the resulting **spans** — the addressable things — not the detector's boundary points: N boundaries inside a timeline yield N+1 spans. The span count is the right thing to attest for the same reason `addressing:` attests an **element** count rather than a parse depth: it is one per stored address, so a consumer comparing it against the record's own markers is comparing like with like. It also means an empty count is never legitimate — a timeline with no detected boundary is one span, not zero — which is what lets a zero read as malformed rather than as "found nothing".

  Three rules govern it, and each answers a way the key could otherwise rot.

  **Resolution happens once, at promotion, and the result is stored.** A stream leaf is reached by containment, so its own origin is `corpus://<container>?stream_id=<N>` — capture lineage, which §12.9 is explicit is *never* a lookup route. The strategy therefore cannot be resolved by a reader walking to the container's overlay. `promote` already holds both records (it is reading the container to stream the member's bytes), so it resolves *mime default ← container's origin overlay* there and writes the answer down. The leaf is thereafter **self-describing**: no walk, no dependency on a second record, and the resolution is auditable from the record itself. What is written down is a **resolution**, which is not recomputable from the leaf's own bytes at all — not a stored derivable fact.

  **Re-attestation compares before it writes.** Re-attesting a promoted member streams from its container, so it *can* re-resolve the strategy — and must not do so silently. An unchanged **cut count** refreshes the stamp and moves nothing. A **changed** count means the strategy that produced this record's authored segments is not the strategy that would produce them now: the record is **held**, with both cut lists reported, and re-segmentation becomes a deliberate authoring act. Without this rule an overlay edit becomes a silent fleet re-addressing that moves every `time_range=` out from under whatever cites it — the key causing the drift it exists to detect.

  **An unstamped leaf is unresolved, not defaulted.** A stream promoted before its strategy existed carries no `cutting:`, and that is a record awaiting a stamp, not a defective one and not one to be re-cut on sight — the same rule §4.3.2.2 sets for a missing `whole_address_count`. An absent attested fact means the check has nothing to compare, so it reports rather than assuming.

- `addressing` (optional) — for a format whose address space is a **parsed tree**, the parse the addresses were computed under. `parser` names the pinned implementation (the HTML family: the stdlib-backed `html.parser` tree BeautifulSoup builds — error recovery and implied-tag insertion differ between parsers, so the choice is part of the contract, not an implementation detail). `scheme` names the address grammar the stored values are written under (*v35*): `ordinal` is the current space (§6.1.1); absence of the key on a stamped record is the frozen dotted-path era, resolvable read-only but never written anew. At attestation the resolved parser identity and the artifact's total **element count** are stamped onto the artifact block as attested facts. The count is the cheap self-check: a consumer whose parse yields a different number knows its tree disagrees and reports that, rather than resolving `el=42` to whatever its own walk happens to reach (§6.1.1).
- `extended_fields` — fields the matching artifact block carries, each with type and optional `semantic_type` tag. A declaration may carry `role: title` / `role: description`, marking the field as an editorial candidate for the record's derived title/description (§4.2.3) — the artifact layer's contribution, weakest in the precedence. The artifact block holds only facts about the **primary-artifact bytes** (e.g. ffprobe codec / dimensions / streams); source metadata from a capturer's enrichment sidecar does NOT live here — see `sidecar`. Vendor/domain identity (what a bundle *is*, beyond its bytes) does NOT live here either — that is knowledge, asserted in the ledger as roster entries and claims citing the record, minted mechanically by a harvest rule keyed on the kept-whole MIME (`ledger.md` §10).
- `sidecar` (optional) — for an artifact type a capturer enriches with a companion metadata sidecar (e.g. a yt-dlp `.info.json`), declares what is lifted and where. `source` names the sidecar (e.g. `ytdlp-info-json`); `ytdlp_keys` lists the info.json keys copied — each into the **origin block** as a flat `ytdlp_<key>` field (§7.2), the mapping the sidecar-lift attestation applies. The sidecar is companion metadata staged in `capture/<hash>.<suffix>`, consumed at ingest attestation (§8.1), then **deleted** — never persisted to `artifacts/` (only the artifact carries the `<hash>` name there). It is *non-primary-source* metadata, so nothing from it goes to the artifact block, the body, or the frontmatter.
- `derived_hashes` — list of **recipe ids** (§7.9) this format adds to the corpus-wide default set (§7.9's layer model: default ∪ mime ∪ origin overlay, additive union — a declaration adds, never suppresses). Destination follows each recipe's residency class (§2, §7.9): a byte-stable recipe with `residency: record` lands in the frontmatter `hash:` **and** the index; every other recipe lands in the index only. (A schema still declaring the legacy `transport_algos` reads as `derived_hashes` with each bare algorithm name as a `residency: record` byte-stable recipe.)
- `ref_adapter` (optional) — names the **reference-dataset format adapter** (`ledger.md` §6.5) that serves entries out of artifacts of this format (`zim`, `osm-pbf`). Schema-first deployment metadata in the tenancy mold (`ledger.md` §6.4): the corpus itself never consumes it — the reference-dataset resolver reads it to derive a registered dataset's adapter from its mirror record's mime, so registration can omit `adapter:` (`athenaeum.md` §2.3; an explicit declaration still wins — the bootstrap and override path).
- `replicas` (optional) — the format's **redundancy floor**: the minimum number of distinct locations (Part IV §6.3) that must hold any artifact of this format. An origin overlay MAY declare the same key for a source whose bytes are irreplaceable regardless of format (a producer export that can never be re-pulled); the resolved floor is the **max** across layers — a declaration strengthens custody, never weakens it. Consumed by health's under-replication signal and `corpus replicate` (Part IV); the corpus itself enforces nothing at write time, and an undeclared floor is 1 (the bytes exist somewhere — §2's baseline contract).
- `fingerprint` (optional) — the perceptual-fingerprint knob (§7.7).
- `normalization.guidance` (optional) — prose guidance for the normalizer.
- `form:` — `{id: passthrough}` (or another **terminal** contract id, §7.8): the format's terminal-contract default — the class judgment that these bytes are their own terminal rendering. Mime-level `form:` admits terminal contracts ONLY (a rendering contract is producer knowledge and rides the origin overlay's `form:`, §7.2, which also overrides this default either way). Redundant for `disposition: manifest` formats — the disposition already derives `form/manifest` (§7.8) — so the key's real population is passthrough defaults on `work`-disposition formats: stills, raw streams, code, datasets, binaries.

Retired mime-schema keys, read tolerantly and ignored: `mode`/`draft.*` (the draft stage), `artifact_kind` (nothing explodes at ingest), `canonical_strategy` (content-canonical identity stays retired: it requires judgment about what the content region *is*, and the one attempt collapsed unrelated scanned PDFs; the shipped tier is the deliberately narrower **capture-invariant** identity — `html-stampfree@1`, §7.9 — which canonicalizes only corpus-injected bytes and is structurally incapable of conflating distinct source documents. A future content-canonical, if it clears that bar, enters as a versioned §7.9 recipe; this key stays retired either way).
### 7.2 The origin namespace

An `origin` schema declares an overlay for one source of retrieval.

- `kind: interpretive` — origin overlays are always interpretive (the match cue may be mechanical, but body guidance is consumed by the LLM normalize pass).

An origin overlay's `normalization.guidance` is **body-shaping tactics** — how to render this source's content faithfully — and, with subtypes (`origin/<id>/<subtype>`), it is the home for **per-page-shape** guidance within a host (how a procedure page vs. an index page of the same site normalizes). The guidance is origin-specific tactics and provenance notes only; the decomposition contract lives on the form overlay (§7.8), stated once for every origin that maps onto it.

One judgment the origin overlay owns outright: **which of a page's index-like regions belong in the record at all.** The same shape carries opposite weight on different templates — a link list is the entire content of a category-selector page and disposable furniture on the same host's article page; a breadcrumb is the page's own statement of what it covers on one site and a decorative echo of the URL on another. No corpus-wide rule can decide that, because the markup is identical in both cases and only the publisher's own layout says which is which. So the overlay **names the regions its records render** (the `regions:` declaration, below), and a region it does not name is chrome the body omits — the judgment is stated once per host, in the open, and is revisable, rather than being re-derived per record by whoever normalizes it. This is the boundary the strip declarations draw at capture time (§12.3.13), one stage later and at content grain: the strip decides what is in the **bytes**, the guidance decides what is in the **body**. A named region that is genuinely the page's frame rather than its subject lands in a trailing span under §4.3.2.1's ordering rule.

A subtype's overlay MAY be a **file of its own** — `schema/origin/<id>/<subtype>.yaml` — carrying everything an id-level overlay carries: `extended_fields`, `editorial` templates (§4.2.3), strip declarations (§12.3.13), `normalization.guidance`, not merely subtype-scoped guidance prose. Block-side resolution is a **ladder, not a merge**: on a subtype-qualified opener, the subtype overlay is consulted first and the id overlay is the fallback — per concern, the first of the two that actually declares something wins. A producer-declared stamp may itself be subtype-qualified: a capture sidecar's `origin_schema:` field may read `<id>/<subtype>`, so the compound opener `<!--origin <id>/<subtype>-->` stamps directly, with no separate mechanism.

- `description` — prose framing of the publisher.
- `applies_to.host_pattern` (string, optional) or `applies_to.host_patterns` (list[string], optional) — host pattern(s) the pipeline matches against origin URIs (the `web` family).
- `applies_to.include_subdomains` (bool, default false).
- `applies_to.scheme` (string, optional) or `applies_to.schemes` (list[string], optional) — URI scheme(s) the overlay matches, compared case-insensitively against an origin URI's scheme. This is how a **non-web scheme family** (e.g. `imessage:`, a future `urn:` / `s3:`) binds, since such URIs have no meaningful host. An overlay may declare host pattern(s), scheme(s), or both.
- `applies_to.cues` (optional) — non-host cues for the matcher.
- `tenancy` (optional) — a tier from the instance's declared set (`public | private` reserved; further tiers instance-declared, `athenaeum.md` §2.3): the source-grain tenancy declaration the ledger's sensitivity derivation reads (`ledger.md` §6.4). Deployment metadata the corpus itself never consumes; silence falls closed to the instance's `visibility:` floor.
- `normalization.guidance` (string) — markdown prose tactics.
- `extended_fields` (optional) — fields beyond the universal `uri:` / `snapshot:`. A capturer's enrichment sidecar populates these — e.g. a yt-dlp capture's `ytdlp_<key>` fields (title, description, uploader, engagement counts, `ytdlp_comments`), declared by the artifact's mime schema `sidecar` section (§7.1) and merged onto the origin block at ingest (sidecar lift, §8.1). A declaration may carry `role: title` / `role: description`, marking the field as an editorial candidate for the record's derived title/description (§4.2.3) — `ytdlp_title` role-marked `title` is the canonical case: every video record derives an honest display title from its sidecar lift, no pass required.
- `derived_hashes` (optional) — recipe ids (§7.9) this producer's records add to the effective set, the third layer of the additive union (default ∪ mime ∪ origin; §7.9). Producer knowledge on the producer's grain: a host- or export-specific canonicalization (`eml-stripped@2.1`-shaped) rides here exactly as strip declarations do (§12.3.13), never on the mime schema.
- `replicas` (optional) — a redundancy floor for this producer's records (§7.1, Part IV §6.3).

An origin overlay MAY override its records' **disposition**:

- `disposition:` — `manifest` | `work`, overriding the mime schema's format default (§7.1) for this producer's records — an export tool that abuses an archive format as a single-work wrapper, or a format whose members are, for this producer, genuinely independent transports. Stamped and auditable like every overlay decision; never sniffed per record.

An origin overlay MAY declare its records' **form**:

- `form:` — `{id: <form-id>, mapping: {…}}`. The `id` names the `form/` overlay every record of this origin carries (the **declared** stamping path, §4.4.6). The `mapping` names where the form's units live in *this producer's* format — for a chat transcript: the messages array path, and the per-message paths for author identity, display name, timestamp (+ its parse convention), text, reply reference, attachment declarations. The mapping is consumed mechanically — by the shaper that stamps and conforms the span at normalize, and by the resolver's `turn=` unit op (§6.2) — so a new platform is one origin overlay with a mapping, zero code. An overlay MAY declare `form:` with an `id` and **no** `mapping` when the shape is named but no mechanical shaper can drive it — adoption then rides the interpretive pass (§4.4.6). Absent the key entirely, records of this origin stand under the zeroth form (§4.1, §7.8) unless a form is asserted (§4.4.6).

- **Route-keyed declaration.** For a **multi-shape origin** — one host serving several shapes (a repair-data site whose routes carry procedures, bulletins, plates, and indexes) — `form:` MAY instead be a **list of match rules**, each `{match: <regex>, id: <form-id>, mapping: {…}?}`. `match` is tested unanchored against the qualified origin block's **primary `uri:` value only** — the first entry, the capture's identity URI. Dedup-folded alias URIs are alternate names and are deliberately NOT matched: aliases are not gate-grade route evidence — a hash-routed SPA that collapses a category route onto a single result pollutes aliases in *both* directions. Rules are tried in declaration order and the **first matching rule** is the record's declaration, exactly as if its `id`/`mapping` had been declared unconditionally; a rule without `match` matches everything (a terminal fallback, where the overlay wants one); a record matching no rule stands under the zeroth form, exactly as if the key were absent. Declaration order is the overlay author's precedence statement. The authoring discipline is conservative by design: a declared form is a **gate** (§8.5 — the pass cannot close until the declared form is stamped), so an overlay declares only routes whose shape is *certain*; an ambiguous route stays undeclared and its records adopt by assertion (§4.4.6).

An origin overlay MAY declare its pages' **regions** — the machine-readable form of the judgment above:

- `regions:` — `[{role, selector, renders, lifts_to?}]`, in declaration order.
  - `role` (string) — the author's name for the region (`breadcrumb`, `vehicle`, `related-information`, `article`). Free-form and host-scoped: it labels a decision, and no corpus-wide vocabulary could, since the same markup means opposite things on different publishers.
  - `selector` (string) — a CSS selector locating the region in the captured artifact.
  - `renders` — `subject` | `framing` | `never`. **`subject`** is what the page is *for* and renders in the record's main span; **`framing`** is the page's own statement about its subject (a breadcrumb, a related-information rail) and renders in a trailing span — `form/nav`, the navigational link set (§7.8) — which is exactly §4.3.2.1's cross-span significance order made mechanical; **`never`** is chrome the body omits. Declaration order is the order framing regions take in that trailing span.
  - `lifts_to` (string, optional) — an `extended_fields` key. The region's text populates that field on the origin block at ingest rather than (or as well as) entering the body. This is for a region that is the same on every page of a host — a vehicle header naming one vehicle across thousands of records is a fact about the *origin*, and storing it per-record would be storing one value ten thousand times.

Naming the regions is what lets the framing restoration be **mechanical rather than interpretive**: without a declaration each record's normalizer re-decides, per record, which of a page's index-like regions belong to it, and re-deciding a host-wide judgment ten thousand times is how it comes out ten thousand slightly different ways. The declaration states it once, in the open, revisable, and gate-checkable. A region the overlay does not name at all is omitted — silence is not `subject`.

**Regions nest, and the innermost declaration governs.** A byte of the artifact belongs to **exactly one** region: the declared region with the smallest span containing it. Everything else follows from that one sentence — a `framing` or `never` region inside a `subject` envelope is framing or never *for its own bytes*, and a `subject` envelope inside another contributes its content once, not twice. The rule is not a refinement, it is what makes the declaration mean anything at all: modern application markup is a tree of custom elements, so a page's outermost content element contains its breadcrumb, its vehicle header **and** its cross-link rail; reading that element as `subject` claims all three as the page's subject while the overlay's own next three rows say they are not. Two consequences:

- **Containment is a property of the artifact, not of the declaration order.** The same two selectors may nest on one template and sit side by side on another, so a reader resolves containment **per record** against the bytes. Declaration order remains the order framing regions take in the trailing span — never an implied nesting.
- **An overlapping-but-not-containing pair is an error, not a tie to break.** Two declared regions whose spans interleave describe a markup shape no DOM produces, so the declaration is wrong; report it rather than picking a winner. Silence is not `subject`, and a coin toss is not a judgment.

An origin overlay MAY declare **exemplars** — handcrafted records of this same origin that show a shape rather than describing it:

- `exemplars:` — `[{record, content, shows, address?}]`.
  - `record` (blake3) — a record of **this same origin**. Cross-origin exemplars are forbidden, and not merely by convention: shape judgments are origin-specific (a repair site's print residue is nothing like an mbox's).
  - `content` (`blake3:<hex>`) — the hash of the exemplar's **content zone** at the moment it was blessed. Not the record file: a `touch` entry appends on every pass, so a file hash would break on changes that teach nothing. The content zone is precisely what an exemplar teaches, so it is precisely what the pin should cover — it moves when, and only when, the lesson does.
  - `shows` (string) — what this example demonstrates, in a line or two. The hint is what makes a list of ids usable; without it an exemplar is a reading assignment with no question attached.
  - `address` (optional) — the span the exemplar demonstrates, when it is one part of a larger record rather than the whole of it.

**Why examples at all, beside guidance that already states the rules.** Prose under-determines shape. A rule can say *a table's title is its `<caption>`* and leave a dozen renderings conformant; an example settles which one this host uses, and settles it in the grammar the worker will actually write. The failure mode it replaces is worse than vagueness: a pass with no blessed example takes its shape from whatever record it happens to open — during any lazy migration, a record in the **retired** grammar.

The pin is what separates this from that failure. An exemplar whose content zone no longer hashes to its declared `content` is **stale**, and a stale exemplar is worse than none: it teaches with full authority a shape the corpus has moved off. So it is an ERROR, and clearing it is a deliberate act — re-read the record, confirm it still shows what the `shows` line claims, re-pin. The same argument as §4.3.2.4's match constraint: a reference that resolves to *something* forever is the dangerous kind.

Exemplars are **additive to guidance, never a replacement for it**. An example shows a shape; it cannot state a prohibition, because absence is not visible in a sample. *Never invent a region* is not demonstrable — no example exhibits the thing it forbids — so the rules stay in `normalization.guidance` and the examples show what conformance looks like. A tooling surface that delivers one without the other has delivered half the contract.

The ingest pipeline iterates every origin block in the record. For each origin schema, if any origin block's `uri:` matches the schema's host pattern (or another declared cue), it upgrades that origin block's opener from bare `<!--origin-->` to `<!--origin <id>-->` and populates the schema's extended fields. The qualified opener contributes `origin/<id>[/<subtype>]` to the derived classifications view. (*Promotion* is reserved for the container-member operation of §8.1.)

An overlay `id` may also be **producer-declared** rather than `uri:`-matched. A capturer/producer that knows what it ingested stamps the id directly — `<!--origin <id>-->` written with the overlay's extended fields — which is the only way a **uri-less** origin (a dropped-in local file, e.g. an `imessage-export`) binds an overlay, since there is no `uri:` to match. Two mechanisms, both yielding the same stamped block: (a) a **capture sidecar** at ingest carries `origin_schema:` (the overlay id) + `origin_fields:` (its extended fields), consumed by the ingestor; (b) the producer injects **`<meta name="corpus-origin-schema">`** + per-field `<meta name="corpus-origin-<field>">` tags into the captured artifact, which ingest folds onto the origin block mechanically (a repeated field meta collects into a list). A stored `id` from any path is equivalent downstream: it contributes `origin/<id>[/<subtype>]` to the derived classifications view, its overlay's `normalization.guidance` surfaces for the normalizer, and it satisfies an `origin.id` predicate in a ledger harvest rule (`ledger.md` §10) — the producer-declared id is not re-derived from a `uri:`, so it works with none.

Two producer-export origins ride this uri-less, producer-declared path today. **`imessage-export`** binds a self-contained conversation HTML with attachments inlined. **`claude-code-session`** binds a captured Claude Code session — its `<id>.jsonl` transcript plus the sidecar tree of sub-agent transcripts, tool-result payloads, and workflow state — bundled into ONE deterministic zip by `corpus session capture` (§12.8) and carrying the session's identity as structured fields (`session_id`, `host`, `record_count`, …) rather than a synthetic URI. A session's record is a `zip-manifest` whose members are directly-addressed `path=<member>` rows (the transcript is a transport resolved verbatim, never transcribed), and successive captures of a growing session are distinct records reconciled by continuity-gated supersession (§12.8), not by a stable id.

The universal `origin` overlay declares the fields every origin block carries. `snapshot:` is always present; an origin carries **either** a retrieval `uri:` **or** local-file metadata:

- `uri` (optional) — string or list-of-strings; the URI(s) by which the origin was reached. Present for a *retrieval* origin (a web capture, a synthetic-scheme source like `imessage://`). **Omitted** for a dropped-in local file: the staging path the bytes sat at is unlinked at ingest, so a `file://` path would be a reference dead on arrival — there is nothing to re-fetch.
- `snapshot` — ISO-8601 timestamp of observation (when the corpus saw this origin).
- `filename` / `source_modified` (local-file origins) — the dropped file's basename and its mtime (ISO-8601, `semantic_type: timestamp`, so it aggregates into the `timeline` view). These carry the durable provenance a `file://` path could not. A local-file origin omits `uri:` and carries these instead; an origin with neither a `uri:` nor local-file metadata is malformed.

**Directory layout — namespaced by URI scheme family.** Origin overlays live under `schema/origin/<scheme-family>/<id>.yaml`, grouped by the URI scheme they are retrieved over so each family can carry its own match semantics. The `web` family (http/https) is keyed by host — `origin/web/<host>.yaml`, matched by `applies_to.host_pattern` — while `otherwise/` is the catch-all for un-namespaced schemes and other families (`urn/`, `file/`, `s3/`) get their own sub-namespace and match predicate as a corpus needs them. The universal `origin/origin.yaml` sits at the namespace root and layers into every overlay. The overlay **id is the bare `<id>`** (e.g. `youtube.com`) regardless of sub-namespace, so the `<!--origin youtube.com-->` opener and the `origin/youtube.com` classification are independent of where the file lives. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`; the flat `origin/<id>.yaml` layout is still read for back-compat.

This bare-id doctrine is scoped to the **scheme-family** directories above — `web/`, `otherwise/`, and any future declared family — which are purely organizational: they group by retrieval scheme, never by producer hierarchy, so nesting a host file one level deeper changes nothing about its id. Any OTHER directory under `origin/` is instead a **producer id**, and the grammar is structural, not organizational: `schema/origin/google-takeout/gmail.yaml` is the subtype overlay `google-takeout/gmail` (id `google-takeout`, subtype `gmail`), never a bare `gmail` — the directory segment IS the id, exactly as `origin/<id>/<subtype>.yaml` names it above.

**Operational overlay sections.** Capture and transcription are retrieval concerns of an origin, so their per-host configuration lives on the origin overlay — one host-keyed file describes both *what* a source is and *how* to capture and process it. These sections are corpus-local (the package ships none) and read mechanically by the tooling; declaring them is how the tooling stays generic with **no hardcoded host knowledge**:

- `capture:` — how to retrieve this origin (read at capture time). One overlay serves **both** capture modes: a live URL fetch and a from-save replay of a manual SingleFile save (§12.3.12) resolve the same recipe and run the same `interactions`, so a host's chrome strip and media-surfacing steps are authored once for both.
  - `capturer` — the capturer name: `browser` (Playwright/HTML; the default) or `video` (yt-dlp). This is the **sole router** for video vs. browser — there is no built-in video-host list. (`corpus capture --video` / `--no-video` override it for a one-off URL.)
  - `transport` — `headless` | `headed` | `cdp` (browser capturer).
  - `fidelity` — `exact` | `balanced` | `lean` (browser capturer): the self-contained-snapshot completeness tier. `exact` is byte-faithful (presentation *is* content); `balanced` (the default) drops redundant font / image / media alternates inlined for self-containment; `lean` additionally prunes style rules with no matching element. The tiers affect only the snapshot **artifact** size — the record and its derived body are identical across tiers (the body derivation reads DOM text/tables, not fonts/CSS) — so fidelity is purely a per-origin retention/faithfulness choice. The resolved tier is stamped into a `corpus-fidelity` snapshot meta tag for provenance. Precedence: `corpus capture --fidelity` › per-host `capture.fidelity` › `origin/origin.yaml` › tooling default (`balanced`).
  - `url_rewrite` — `[{pattern, replacement}]` regex rules applied to the navigation target before fetch; the original URL stays the recorded origin and the rewritten form becomes an alias.
  - `url_equivalent` — declares which URL spellings denote the **same resource**, so the corpus matches an inbound URL to a record (and keeps one origin URI per resource) even when the spelling differs — query noise (`?nested_view=1`, tracking params), a redundant `/page-1` ≡ the bare form, etc. **Identity-only**: it computes a URL's *identity key* and never changes which bytes are fetched (that is `url_rewrite` / `interactions`). Two URLs are equivalent iff their identity keys are equal. Declared as a list of `[{pattern, replacement}]` rules (same shape as `url_rewrite`), or a map `{query: keep|drop, rules: [...], on_rewritten: bool}`. The identity key = the conservative `normalize` (lowercase scheme+host, sort query, drop a plain anchor, …), then — for `query: drop` (default `keep`) — strip the whole query, then apply the regex `rules` in order, then a final delimiter tidy, then fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`); with `on_rewritten: true` the host's `url_rewrite` is applied first so identity is computed from the fetched form rather than the inbound one. The trailing-slash fold is part of the **identity** key only, never of `normalize` — `normalize`'s output is the URL a crawl re-fetches, where the slash can be significant, whereas a comparison key may fold it. **Opt-in**: absent the section, identity is exactly `normalize` (string match), so the layer is inert for every host that does not declare it, and host-scoped so a blanket `query: drop` cannot wrongly fold a host where `?page=`/`?id=` matters. Applied at the **capture short-circuit** (re-capturing a known resource is skipped), **crawl frontier dedup** (an equivalent of a visited / captured URL is not re-enqueued), **pagination uri-recording** (an equivalent spelling of an already-recorded constituent page is not appended), and **resolve** of a raw URL to its record. Pairs with — and is independent of — `url_rewrite`.
  - `pagination` — reconcile a work a site splits across `?page=N` / `/page-N` URLs into **one** record (browser capturer only). `true` enables it with auto-detection; a map gives control: `content_selector` (the per-page content region — else a structural page-1-vs-page-2 diff finds it), `next` (`{rel: true}` follows `<link/a rel=next>`, the default; `selector` overrides with a CSS link), `max_pages` (safety cap, default 100), and `expect_count.selector` (an element whose text holds the site-advertised item count, for the completeness check). The capturer walks the pages, captures each via the staging-only path, merges their content regions into page 1's framework — **deduping by element id or a normalized-subtree hash** — and ingests the merged document. **INVARIANT: exactly one artifact and one record result; per-page captures are never content-addressed.** The clean seed is the recorded origin URI; every constituent page URL (bare site form *and* the pinned `url_rewrite` form) is folded in as an origin alias, and a `pagination: {pages, form, posts}` provenance field lands on the origin block (`posts` = the merged content-item count: id-bearing region children when present — forum/CMS posts carry stable ids — else all direct children, so framework nodes don't inflate it). When the merged item count falls short of the advertised count, or `max_pages` is hit, a `pagination-incomplete` `warning` issue is emitted (capture stage) rather than silently shipping a lossy record. Pairs naturally with `url_rewrite` to pin one render form across every page.
  - `ytdlp:` — a mapping merged straight into yt-dlp's options (full passthrough; e.g. `format`, `getcomments`, `impersonate`). Library-owned keys (output path, logger, the resolved cookie file) are forced after the merge and cannot be overridden.
  - `cookies_from_host` — `true` (default) pulls the capture URL's own-origin cookies from a running CDP browser session into yt-dlp; `false` disables; a list adds extra origin scopes. Lets a logged-in session unlock a host's full content.
  - `also_capture:` — `[{role, capturer, …}]` supporting captures run after the primary one; their bytes **enrich the primary record** (e.g. a comments page folded into the record's metadata) rather than forming separate records.
  - `references:` — `[{match, role, capture, cross_host}]` — declares which of a captured page's outbound links are **dependent reference material** (a PDP's product manual, a spec sheet). Each rule's `match` (`selector` / `href_pattern` / `text_pattern` / `rel`; present keys ANDed, rules ORed) selects `<a>` elements in the captured page's DOM. The declaration is purely a **capture instruction** (§8.1) — which outbound links are part of this capture; it writes nothing onto the record. **Fetching** a declared target is the action: `capture: true` (or `corpus capture --with-references`) fetches it **once, at depth 1**, as its own ordinary record (content-hash deduped) right after the primary; `capture: false` (default) is surface-only and the deferred `corpus crawl --references` pass fetches pending targets on demand; `corpus links --references` reports declared targets and their captured/pending state at read time. `cross_host: allow` (the default for references — manuals are off-host) permits reaching declaration matches on other hosts, but **only** matches — never a general cross-host crawl. Distinct from `also_capture`, whose bytes **enrich the primary record** rather than forming separate, referenced records. Absent the section the feature is inert (no hardcoded link knowledge).
  - `assembly:` — config for **pre-ingest bundle assembly** (`corpus assemble`, §12.3.11): repackaging a source's delivered part(s) into ONE indexed container bundle before ordinary ingest, for delivery formats that are transient (an expiring export job), access-hostile (a solid compressed stream), or envelope-less (a loose directory tree an export tool wrote straight to disk). Keys: `merge_parts` (union a multi-part delivery's member trees — the split is delivery, not structure), `conflict` (`error`: a same-path collision across parts with differing bytes aborts; identical bytes dedup), `additions` (an allowlist of declared NON-original files placed at the bundle root, outside the original tree — e.g. an out-of-band export report), `rewrites` (declarative `{from, to}` restructure rules; **empty is the norm** — the original internal structure is NEVER changed except by a rule asserted here), `excludes` (declared filesystem-cruft subtraction — fnmatch patterns; slash-less patterns claim the basename at any depth, slashed ones the full relpath; exclusions are reported, never silent), `level` (the bundle's compression level), `derive` (mechanical origin-field extraction patterns — filename-convention regexes, addition-content regexes, and `from_member_head` regexes over the leading bytes of glob-matched members of a directory source, greatest match winning across members — so every vendor-shaped fact lives in the overlay, none in the engine), `seed_fields` (which derived fields beyond `account`/`job`/`exported_at` ride into the sidecar), and `name_fields` (derived fields whose values join the bundle's filename and archive comment — the job identity where no job id exists). The assembled bundle is staged with a capture sidecar (`origin_schema:` + the derived/declared fields) and enters the pipeline through ordinary ingest; the consumed part archives are recorded as `source_parts` tombstones (filename + byte hash) on the origin block — a directory source, having no delivery envelope, leaves none (member byte-identity is carried per-member by the manifest's members block). Absent the section, `corpus assemble` refuses the overlay.
- `transcription:` — per-host audio transcription (read by the `transcribe` derivation op, §6.2). `enabled: false` skips transcription (an `info` issue, not a `warning`); `adapter` / `base_url` override the global `[corpus.transcription]` backend. Absent the section, the global config applies.
- `metadata:` — reserved hook to remap/disable how a capturer's enrichment sidecar maps into the record (per host). The mapping itself is **host-agnostic and applied for every yt-dlp capture**, and is **schema-declared**, not hardcoded: the keys lifted from the `.info.json` come from the artifact mime schema's `sidecar.ytdlp_keys` (§7.1). Because the sidecar is *non-primary-source* metadata, every lifted key lands on the **origin block** as a flat `ytdlp_<key>` field — never the artifact block, the body, or the frontmatter. `comments[]` (when yt-dlp returns it) becomes a `ytdlp_comments` list field; `webpage_url` / `original_url` fold into the origin `uri:` aliases. The sidecar is **ingest-time-only enrichment** (sidecar lift, §8.1) — staged in `capture/`, consumed at ingest attestation, then deleted; it is one-shot (a re-attest after deletion does not re-apply it; the lifted fields already persist on the record). Nothing mechanical writes body content: the **transcript** is the `transcribe` derivation op's output (§6.2), consumed at normalize.
- `strip_headers` / `strip_fields` / `partition:` — producer canonicalization and temporal stratification (§12.3.13, §12.3.14).

### 7.3 The atom namespace

An `atom` schema declares an atomic-axis overlay that may attach to a segment.

- `kind: atomic`
- `description` — prose definition.
- `applies_to.atom` — `text`, `image`, `audio`, or `video`. Must match the id's axis segment (e.g. `text` in `atom/text/data-table`).
- `applies_to.cues` (optional) — heuristic patterns for the normalizer.
- `enables_lossless` (boolean, default `false`) — when `true`, this overlay licenses a shaped lossless body in the text-atom segment that carries it. Only valid on `applies_to.atom: text` overlays. The overlay's other declarations describe what shape the body takes.
- `extended_fields` (optional) — id-specific fields. For lossless-enabling overlays these typically describe address-shape requirements; for envelope-bearing forms (a chat message's `sender`/`timestamp`) they carry the segment's structural envelope, verbatim from the source.
- `normalization.guidance` (string) — markdown prose tactics for rendering the form faithfully.

An envelope-bearing atom overlay's extended field may be declared as a **codebook index**: an integer field whose value indexes a list field on the *enclosing form section's* header (e.g. `text/message`'s `participant:` indexing `form/conversation`'s `participants:` codebook — first-appearance authorship order, entry grammar `<display> <durable-id>`). The index resolves through the record alone — segment → section header → entry — so a consumer needs no platform knowledge; lint's form-coherence checks (§4.3.2.1) verify indexes are in range. A codebook index and a verbatim envelope string (`sender:`) are both licensed forms of the same envelope — the overlay says which its records carry (repeating a verbatim identity string across a 70,000-message span is what the codebook exists to avoid).

A segment carries exactly one atomic class id, on the opener line. The structural segment is not an atom and takes no atom overlay (§4.3.2.3).

**The atom constitution.** Atom overlays declare **form, never meaning**: the shape of a lossless body, the structural envelope of a segment, extraction tactics for a region's faithful rendering. "This text is a table," "this image is a screenshot," "this segment is one chat bubble with this sender and timestamp" are form statements, checkable against the bytes. A subtype whose payload is domain semantics — what the content is *about* — is wrong at this layer; that is a ledger claim over the segment's span (`ledger.md` §6).

### 7.4 The composite namespace *(retired)*

The `composite` umbrella was the corpus's interpretive classification system — a pre-ledger claims system embedded in the archival layer. Where each part went:

| Retired mechanism | Successor |
|---|---|
| User-defined classification namespaces | Ledger **types and predicates**, under VOCAB discipline (`ledger.md` §8) |
| Asserted classify blocks (record scope) | **Claims** with record evidence (`ledger.md` §5–§6) |
| Section-scope composites | Claims with span evidence (§4.4.3) |
| `classify_when` deterministic membership | **Harvest rules** (`ledger.md` §10) — the same fact base and predicate grammar, evaluated ledger-side over corpus records |
| Mechanical extraction scripts | Harvest-rule `mint` templates over the same fact base |
| Domain-semantic `normalization.guidance` | Per-type authoring conventions (the ledger's `facts/SCHEMA.md` / concept schemas, `ledger.md` §8, §4.4) |
| Body-shaping guidance keyed by page type | The origin overlay (subtypes, §7.2) or an atom overlay (§7.3) |
| `extended_fields` | Claim values and qualifiers |

The fact base and predicate grammar that `classify_when` defined are specified in the harvest-rule contract (`ledger.md` §10), unchanged in substance: attested-or-derived facts only (`mime`, `origin.*`, `form.*`, `media.*` — never authored prose), exact-by-default operators, missing-fact-is-false, and body keywords permanently excluded as the canonical false-positive source.

### 7.5 Semantic-type vocabulary

A closed list of seven types. Schemas tag extended-field declarations with one of these to opt the field into a derived view (§9) or document its meaning.

| Type | Aggregated into | Notes |
|---|---|---|
| `uri` | `uris` derived view | String. Deduplicated across all uri-tagged fields and origin-block `uri:` values. |
| `timestamp` | `timeline` derived view | ISO-8601 instant or interval. Aggregated with origin-block `snapshot:` values (§9.4). |
| `identifier` | `identifiers` derived view | Vendor-issued opaque ID. The view also includes the record's own `id` (§9.5). |
| `hash` | (no view) | Cryptographic hash. |
| `fingerprint` | (no view) | Non-cryptographic content fingerprint. The semantic-type tag spelling is `fingerprint` (§7.7). |
| `person` | (no view) | A single alias string identifying one person. |
| `geolocation` | (no view) | Location reference. |

The vocabulary is closed.

### 7.6 Hash encoding convention

Every hash value outside the `id` field — the frontmatter `hash:` field, the members-block `transport` rows, origin-block hash fields (`source_transport`, §12.3.13), and derived-hash-index rows (§12.9.1) — uses a uniform encoding:

- Value type: `str` or `list[str]`.
- Value format: `<tag>:<hex>` — tag as colon-prefix, lowercase hex value following.
- A multi-valued `hash:` renders as a block-style list — one `- <tag>:<hex>` row per value — the same shape every other frontmatter list (`touch:`) uses; a single value stays a bare scalar.
- Parsing: split on the first `:` to obtain `(tag, value)`.
- The tag grammar carries the §2 classification. A **bare algorithm id** (`sha256`, `md5`, `blake3-64k`) tags a byte-stable value — the algorithm is the whole identity, and holding candidate bytes lets anyone verify against it. A **`<procedure>@<version>`** tag (`html-stampfree@1`, `eml-stripped@2.1` — the `@` versioning the touch-identifier grammar already uses, §4.2.2) tags a procedure-versioned value. The procedure tag deliberately names the canonicalization and NOT the digest algorithm inside it (§7.9): the algorithm is an implementation detail pinned by the recipe's versioned definition, and surfacing it would invite a byte-verification that cannot succeed against a canonicalized value. The version is part of the tag, compared exactly; the same first-`:` split applies.

The `id` field is the exception — always bare blake3 hex (algorithm is invariant).

### 7.7 Atom fingerprint strategies

Perceptual fingerprinting is **opt-in** and **schema-gated**. Fingerprints are a near-duplicate / similarity-search signal, not a mandatory attestation, so the default is **off** and an unfingerprinted record is normal. The knob is a top-level `fingerprint` field on a **mime schema** (the per-file-type default) and may be overridden on an **origin overlay** (for records from that source). Values: `false` / absent = off; `true` = on with each atom's *default* algorithm; an algorithm name or a list = on with those algorithms. Resolution precedence, most-specific first: the ingest/re-attest CLI `--fingerprint` / `--no-fingerprint` override › origin overlay › mime schema › off. Fingerprint algorithms are the **similarity family** of derived-hash recipes (§7.9): procedure-versioned on the residency axis (implementations and parameters vary), **similarity** on the comparison axis — their values are distance-queryable points, not identities, so equality on them claims nothing. Where the knob resolves on, they land in the **derived hash index** keyed by record and segment address (§12.9.1) — and they stay there: a similarity value has no record flush target *by rule* — the `hash:` field admits identity-class values only (§4.2.1, §7.9), and a fingerprint is not one.

When fingerprinting is on, the algorithm for a segment is determined by its `atom:`, not by the source media-type. Each atom has a default algorithm; the knob may select an alternative where the atom supports more than one:

| Atom | Default algorithm | Algo prefix | Alternatives | Notes |
|---|---|---|---|---|
| `image` | perceptual hash (pHash, 64-bit) | `phash` | `dhash`, `ahash`, `whash` | Robust to re-encoding, mild crops, and small resamples. |
| `audio` | acoustic fingerprint (chromaprint) | `chromaprint` | — | Comparable across codec changes and bitrates. |
| `text` | simhash (64-bit) over normalized tokens | `simhash` | — | After Unicode normalization, lowercasing, and whitespace collapse. |

The `<algo>:<hex>` value records which algorithm produced it, so an index row self-documents how its record was fingerprinted.

### 7.8 The form namespace

A `form` schema declares one **rendering contract**: an expectation for how a set of bytes is faithfully represented in a markdown shape. It binds on a section-block opener (§4.3.2.1) exactly as an atom overlay binds on a segment opener. The namespace is the corpus's **shape-contract library**, the third leg of a deliberate separation of concerns: **origin** says where the bytes came from, **mime** says what container they arrived in, **form** says what markdown shape renders them faithfully. The layers never bleed (§1.5 principle 5): an origin overlay binds a form and maps the producer's format onto it (§7.2); the form overlay owns the shape.

**The zeroth form.** `formless` is a member of the form domain, not a gap in it — the library's **identity contract**: the faithful representation of the bytes is the bytes, delivered through the derivation ops (§6.2), its verification the attestation already in hand. It prescribes nothing about what the artifact is, which is exactly the record layer's discipline — and it is why there is deliberately **no catch-all shape and no default form**: stamping a generic shape on an artifact merely so it "has a form" asserts a shape its bytes may not have (much of what a corpus consumes — code, datasets, binaries, containers — is nowhere near document form). A named form is a **prescription, and it is earned**: by *identification* (an existing contract fits the artifact) or by *authorship* (a new contract is written for it); until then the record stands formless, consumable, and honest (§4.1).

- `kind: form`
- `description` — prose definition of the shape.
- `extended_fields` — the section-header fields the form's spans carry: **codebook lists** (e.g. `participants:` — authorship-derived, first-appearance order, entry grammar `<display> <durable-id>` — the join surface a codebook-index envelope field resolves against, §7.3) and span envelope facts. Every field MUST be **mechanically derivable from the span's own bytes** — a fact that could be recomputed but is instead hand-stated is in the wrong layer, and a fact that *cannot* be recomputed is not a property of the span. Conformance checks (`checks:`, below) therefore bind **every** declared field. A form declares no editorial role marks (§4.2.3). Since these are the only fields a section carries, a form that declares none takes a bare opener, which is complete. **Codebook positions are durable.** A codebook entry's position is a join key the ledger's claims bind to (a claim that identifies *who* `participants: 2` is cites the span — its evidence lives or dies with that index), so a corrective re-pass obeys the lineage discipline at record scale (`ledger.md` §4.1): a **split** — one entry that conflated two identities (a diarizer merging two speakers) — appends new entries and re-points only the affected segments' indexes, while the conflated entry **stays in place, occupied and never reused**, so unaffected indexes never shift; entries are never deleted, reordered, or renumbered. Where the source itself supplies durable ids, a correction is ordinary fidelity repair against the bytes. Either way the surgery is a body edit like any other — the ledger's drift machinery re-verifies citing claims (`ledger.md` §13.2) — but a pass that re-points indexes MUST emit the migration worklist naming the citing claims it knows to be affected, loudly, rather than leaving them for the next verification sweep to trip over.
- `decomposition` — the normal form, normatively: which segment kinds compose the span (the envelope atom overlays and their required header fields), the addressing axis (`turn=`, `time_range=`, `pages=` — the form is **modality-blind**: `form/conversation` covers a chat export at `turn=` and a recorded meeting at `time_range=` with the same envelope), attachment and event conventions.
- `checks` — the mechanical conformance obligations lint enforces on any span carrying this form (§4.3.2.1): required envelope fields, codebook indexes in range, address monotonicity, **co-addressed segment pairings** (a contract whose faithful rendering is two stacked segments — a figure and the relation it states, §4.3.2.2 — binds the pair, so a span carrying one without the other is a violation rather than a span that merely looks finished). *(The check grammar is the overlay `checks:` block — `envelope_required` / `codebook` / `address_axes` / `monotonic` — as implemented by all current overlays.)*
- `normalization.guidance` — prose tactics for the authoring pass, stated **once** for every origin that maps onto the form.

(Editorial templates survive only on the **origin** overlay (§4.2.3, §7.2), where they compose a producer's own stamped facts. A form template would compose the corpus's shape judgment into a display string — the record speaking about itself by a mechanical route rather than an authored one; the route was never the objection.)

**Terminal contracts.** Two members of the form domain prescribe the **absence** of a stored rendering — they are the zeroth form's judgment made assertable, closing the gap between *formless-unassessed* and *formless-by-design*:

- **`form/passthrough`** — the identity contract, named. Adopting it asserts the earned judgment that **no markdown shape will ever render these bytes more faithfully or more token-efficiently than the bytes themselves**, delivered through the derivation ops (§6.2). Its conformance check is the inversion of every other form's: the content zone holds structural byte-marks only — a stored rendering under a terminal contract is the lint violation. Its population: media streams and stills, code drops, datasets, binaries — the raw-context artifacts §4.1 names.
- **`form/manifest`** — the container specialization. The **members are the content** (`disposition: manifest`, §1.2): conformance binds the attested rows of the members block (§4.3.1.4 — the roster IS the attestation, nothing re-stated), and the content zone holds container byte-marks only. One derivation keeps the judgment single: a `disposition: manifest` record with no rendering contract declared for it **stands under `form/manifest`** — the disposition already is the terminal judgment, and the contract refuses to make an owner state it twice. An overlay MAY still bind a rendering contract over a manifest-disposition record where one genuinely applies; the explicit declaration wins.

A terminal contract is **not** the catch-all this section forbids: the prohibition targets stamping a *shape* an artifact may not have, and a terminal contract prescribes no shape — it records that none exists, earned by the same identification discipline as any adoption (§4.4.6) and guarded the same way (terminal adoption to flatter a census is exactly the force-stamping the adoption discipline refuses). Declaration rides the overlay grain — a mime schema's `form:` default, an origin overlay's override, per-record assertion for exceptions — because formless-permanence is almost always a class fact, not a record fact.

**Governing-contract precedence.** A record's governing contract resolves: (1) the **origin overlay's `form:`** declaration (§7.2 — rendering or terminal); (2) the record's **own asserted form span(s)** (rendering or terminal) — a stamped per-record judgment outranks every class-grain default; (3) the **mime schema's `form:`** terminal default (§7.1); (4) the **`disposition: manifest` derivation**. Two guards on (3)/(4), neither applying to (1)/(2): a class default never claims a record **already carrying a stored rendering** — grandfathered rendered content stays `rendered` (a stored rendering under no named form contract, tolerated pending its next pass) until its pass exits it, never retroactively condemned by a later class declaration — and the manifest derivation requires the manifest attestation to have actually emitted **member rows**: a promoted member stub whose format family is manifest-dispositioned carries no roster of its own and stays `proxy`. Stamping is **optional**: a terminal record needs no section at all — the declaration alone governs; a bare terminal record is the complete shape. Downstream: a terminal record **never gates and never enters the queue by default** (§8.5), health reports it as **terminal** — not proxy — and the ledger treats it as a **complete source** whose derived surfaces are permanent, full-strength evidence (`ledger.md` §6.3).

**Forms are a goal, not a rarity.** For the right artifacts — those with a faithful markdown shape — a named form is where the record is headed: messaging exports render as `conversation`, statements and receipts as their contracts, and the document population (captured articles, manuals, papers) as a small set of **generic shapes**. Adoption is **lazy and benefit-driven** — §4.4.6's two stamping paths, pulled by demand through the queue (§8.5) — never forced by totality: nothing requires every record to carry a named form, which is precisely what keeps the library honest and small. The population splits cleanly: formless-permanently (no faithful markdown shape exists — the identity contract IS the rendering; machine-readable as a terminal declaration, reported `terminal`), formless-for-now (a shape fits but none is yet identified, authored, or worth the pass — reported `proxy`), and formed.

**The minting test.** A form is minted when all four hold: (1) it names a **shape, never a subject** (below); (2) its decomposition contract states what a faithful rendering IS, precisely enough that conformance is **mechanically checkable against the bytes** — every fact it declares recomputable from the span; (3) a **population wants it** — the contract recurs across ≥2 origins, or a generic shape covers a modality-wide population; (4) a consumer **uses it** — a shaper, a composition view, a harvest rule, or the ledger's span-precise citation surface. One origin wanting a shape is origin-overlay guidance; a label that changes nothing about rendering or checking is not a form. **The test is standing, not a gate passed once**: a minted form that stops satisfying it **retires**, and the four criteria are the same four read in the present tense. A form is cheap to mint and expensive to keep — every one is a page of prose the authoring pass must read, a set of fields lint must bind, and a shape a normalizer will fit records to — so a contract whose consumer never arrived, or whose population turned out to be one host, is not harmless furniture. It is guidance competing with the guidance that works. Retirement re-forms its records onto the generic shape that already covered them (§4.4.6) and leaves the retired overlay's genuinely host-specific knowledge on the **origin** overlay, where a single-host judgment belonged from the start (§7.2). (A generic shape may render close to what mime + atoms already produce; what it adds is the contract itself — a named, checkable expectation a stored rendering can be verified against, which an uncontracted rendering never has.)

**Generic shapes, guarded.** A small generic hierarchy — on the order of `document`, `article`, `procedure`, `transcript`, `data-table-set`, `slide-deck` — is expected to cover the corpus's entire rendered population in **fewer than ten shapes**; a proposed eleventh generic shape is a design smell to be argued for, not a routine mint. A generic shape is still a real contract (an honest `form/document` binds artifacts that genuinely render as documents); what it must never be is a default (the zeroth form, above).

**Forms name shapes, never subjects.** `conversation`, `statement`, `receipt` are shapes: a time-ordered participant-attributed message sequence; a period envelope with transaction line items; an itemized-commerce document. `product-manual` is **not** a form — a manual decomposes as a generic document (`form/document` at most), and manual-*ness* is a ledger claim. `episode` vs `film` are legitimate — act structure with title/credit conventions vs scene-and-chapter continuity are decomposition contracts in the bytes — while *which show* an episode belongs to is the ledger rostering the record onto a concept, exactly as `form/receipt` never names the merchant (the origin block and the bytes do). This is the normative line that keeps §4.3.1.3/§7.4 honestly tombstoned: the classify block asserted meaning at record scope and is not returning; the form opener asserts shape at span scope, mechanically checkable, nothing more. The guard binds hardest exactly where the library grows: a shape is generic or it is nothing — `form/procedure`, never `form/<site>-procedure`; the subject half of any proposed compound form belongs to the origin block (provenance) or the ledger (meaning). Shapes mint as their populations adopt and their consumers arrive — never before. *(The library's membership is not restated here: `form/<id>` overlay files are the registry, each carrying its own contract, its consumers, and the judgment that earned it. A roster in this section would be duplicate state, and it would rot.)*

**Stamping** is §4.4.6's two paths (declared via the origin overlay's `form:` key; asserted by an interpretive pass through the normalize gate). **Coherence** is §4.3.2.1's lint rule. **Downstream**, `form.*` joins the ledger harvest fact base (`ledger.md` §10) — deterministic rosters keyed on shape (`every form/receipt records onto the spending concept`) — and composition views consume *(form, envelope)* tuples with no platform knowledge: the cross-platform conversation thread joins spans on (ledger identity × timestamp); the same-video view joins tracks on (lineage × timeline); one composition layer, two join keys, zero stored view state.

### 7.9 Derived-hash recipes

A **recipe** is a named procedure — an algorithm plus an optional canonicalization — computed over an artifact's bytes, encoded `<algo>:<hex>` (§7.6). The effective set for an artifact resolves from **three additive layers**, most general first, as a union — a layer adds recipes and never suppresses another's:

1. the **default set** — corpus-wide, applied with no declaration: `sha256` and `md5` (`residency: record` — sha256 the interop standard; md5 for store-side verification against object-store metadata, S3 single-part ETags / Azure `Content-MD5` / GCS `md5Hash`, an integrity audit with zero egress) plus `blake3-prefix-ladder` (index-only — the grown-export screen joins on producer filenames, which no mime grain predicts);
2. the **mime schema**'s `derived_hashes:` (§7.1) — format knowledge: `text/html` adds `html-stampfree@1`, the capture-invariant identity that only means something where capture stamps exist;
3. the matched **origin overlay**'s `derived_hashes:` (§7.2) — producer knowledge: a host- or export-specific canonicalization (`eml-stripped@2.1`-shaped) rides the overlay exactly as strip declarations do (§12.3.13).

Ingest computes the resolved union while the staged bytes are in hand (§8.1); an existing fleet backfills through the index (§12.9.1).

A recipe is characterized on two orthogonal axes, both properties of the procedure and never per-corpus choices. The **comparison axis** says what a consumer may do with the value: an **identity** recipe (every cryptographic hash, canonicalized or not) mints an equivalence — equality means the (canonical) bytes are the same, so the value is joinable, dedup-grade, proof-grade up to the hash. A **similarity** recipe (the perceptual family, §7.7 — pHash, simhash, chromaprint) mints a point in a metric space: comparison is a distance computation and equality is meaningless as a claim — chromaprint fingerprints of the same recording are matched by alignment scoring, almost never byte-equal. A similarity value is therefore **never flushable to `hash:`** — that field's contract is "equality means same content" (§4.2.1), and a similarity value there would invite exactly the join it cannot support. The **residency axis** is §2's two classes, each with its own tag grammar (§7.6):

- **Byte-stable** — a fixed public algorithm over the exact bytes; the value can never change. Its tag is the bare algorithm id (`sha256`, `md5`, `blake3-64k`) — the algorithm *is* the full identity, and the tag doubles as the verification affordance. MAY declare `residency: record`: ingest then writes it to the frontmatter `hash:` alongside the index row; without the marker it is index-resident and record-flushable (§12.9.1). Declaring `residency: record` on a procedure-versioned recipe is a schema error.
- **Procedure-versioned** — the value depends on an evolvable canonicalization or implementation. Its tag is **`<procedure>@<version>`** — the procedure named after the media family it canonicalizes (`html-stampfree`, `eml-stripped`), versioned with the `@` the touch-identifier grammar already uses (§4.2.2), and deliberately **omitting the digest algorithm**: the algorithm is pinned inside the recipe's versioned definition, and changing it is just one more thing that bumps the version. Always **index-first**; reaches a record's `hash:` only by deliberate flush, always under its full tag. Revising a recipe's procedure REQUIRES a version bump; a revision never rewrites stored values — rows and flushed entries of the old version stand as what they are, the old procedure's output — and lint may flag them for a deliberate re-flush, never silently.

The registry ships four recipes; each names its class, its layer, and its guarantee:

| Recipe id | Class | Computes | Guarantee / purpose |
|---|---|---|---|
| `sha256` | byte-stable, `residency: record` (default set) | sha256 over the artifact bytes, unmodified. | Interoperability with external checksum ecosystems — producer-published digests, replacement-copy matching for lost bytes. |
| `md5` | byte-stable, `residency: record` (default set) | md5 over the artifact bytes, unmodified. | **Store-side verification without egress**: object stores serve an md5 in listing metadata (S3 single-part ETags, Azure `Content-MD5`, GCS `md5Hash`), so a remote store audits against record frontmatter with no byte pulls. Not a cryptographic guarantee — the tag is honest about being md5 — an integrity check, with sha256 beside it for strength. |
| `html-stampfree@1` | procedure-versioned (declared by the `text/html` mime schema) | A digest (blake3, pinned by this version's definition) after neutralizing **corpus-injected capture stamps**: the `corpus-*` meta tags browser capture writes (§12.3.6) and the SingleFile banner comment (§12.3.4). Bytes the pipeline did not inject are never touched. | **Capture-invariant identity** — two captures of byte-identical delivered content hash equal even though their stored blake3 ids differ by the stamps. Because the canonicalization is scoped to the corpus's own injections, it is *structurally incapable* of conflating distinct source documents. This is the identity the same-document health signals join on (§12.9.1). Versioned because the stamp inventory can grow with the pipeline. |
| `blake3-prefix-ladder` | byte-stable, index-only (default set) | blake3 of the artifact's first 4 KiB, 64 KiB, and 1 MiB — three rows/values, each tagged with its rung (`blake3-4k`, `blake3-64k`, `blake3-1m`). | **Grown-export screening** — a producer re-emitting an append-only export (an iMessage conversation one message longer) yields a longer file whose ladder matches the shorter file's at every rung the shorter file reaches. Prefix candidacy is thereby decidable index-only; a streaming byte-compare of the shorter file's length confirms only the survivors. A screen, not a proof: matching rungs admit a candidate, never conclude a prefix. Byte-stable (a rung length is a parameter, not a procedure), so flushing it to `hash:` is legal — the default keeps three niche values out of every record. |

The registry recipes are identity-class. The **similarity family** — the §7.7 fingerprint algorithms — are recipes of the same machinery (procedure-versioned, index-resident, version-tagged rows) whose comparison axis bars them from records entirely; §7.7's knob is their opt-in surface.

**Two tiers of canonicalized identity, kept deliberately apart.** Capture-invariant identity (above) answers "is this the same *delivered document* across captures?" — mechanical, canonicalization scoped to self-injected bytes, safe by construction. **Content-canonical** identity ("is this the same *content* across URLs/renderings?") remains retired (§7.1): it requires judgment about what the content region *is*, and the one attempt collapsed unrelated documents. If a content-canonical strategy ever clears that bar it enters as a new procedure-versioned recipe here — index-first and version-tagged like every other, so a failure is a config deletion and visibly-superseded values, not a fleet sweep.

---
## 8. Pipeline

### 8.1 Stages

| Stage | Mechanics | Touch identifier shape |
|---|---|---|
| `capture` | Bytes land in the corpus's staging area. | none |
| `ingest` | blake3 of bytes → `id`; `derived_hashes` recipes → `hash:` (`residency: record` byte-stable) + the hash index (§7.9, §12.9.1); MIME detect → artifact-block opener; **byte-fact attestation** per the mime schema's `attest:` and `disposition:` (§7.1) — artifact fields, the members block whether manifest or exposable (members / messages / cards / entries / parts / tracks / items), structural byte-marks, sidecar lift; emit the record (the artifact's proxy, §4.1) with first origin block from capture context; persist binary. | `<pkg>.ingest@<v>` |
| `promote` | Mint a record for a container member already in the corpus: locate via the members-block row, stream + blake3-verify → `id`; MIME detect; **attest** per the member's mime schema; emit a record whose first origin block records the containment lineage as history (`uri: corpus://<container-id>?<member-address>` + `filename`/`source_modified` where present). Bytes are NOT copied (§2). **Required** for any member a record positions with a placement (§4.3.2.4) — placing is the act that obliges it; an unplaced member never needs it. The lineage origin is also what supplies the normalize pass its parent **context**, which is an input to the pass and never to its output. | `<pkg>.promote@<v>` |
| `normalize` | The **one authoring pass**: consumes the derivation ops and renders the record under its named form contract (§7.8) — executed by a mechanical **shaper** where the record's declared form mapping (§7.2) or manifest shape makes it deterministic, by an interpretive agent where judgment is required — with the span's declared form fields and typed faithfulness issues riding the same pass. The pass's whole output is faithful renderings, form declarations, and fidelity issues. | `<pkg>.shape.<id>@<v>` / `<model-id>` / combined (`+`) |

(The 2.x `draft` stage is retired: fact-stamping became ingest **attestation**; content extraction became resolver **derivation ops** (§6.2), computed on demand and cached; body-writing became the normalize pass. A legacy `status: draft` record reads tolerantly as a just-attested record.)

Idempotent re-capture is part of `ingest`. Concrete tooling is implementation-defined.

An origin overlay's `capture.references` (§7.2) drives one mechanical, deterministic action (§8.2): for rules marked `capture: true` (or `corpus capture --with-references`), the **capture** side fetches the page's declared dependent links at depth 1 as their own records after the primary ingest. The declaration is purely a **capture** instruction: which outbound links are part of this capture. The links themselves are already in the faithful body, and whether one names a captured record is a read-time resolution (§9.9, §12.4.7); nothing is stored.

A corpus may also specialize the **shaping** of its own content with corpus-local shaper code — `<corpus_root>/shapers/*.py`, loaded mechanically before the normalize pass. Such a shaper claims a record by its origin or form id (§7.2) and builds the authored content zone in place of (or ahead of) the generic mapping-driven shaper and the interpretive agent; the package ships none and knows nothing of any specific format. Implementation-defined — see §12.4.3.

### 8.2 The deterministic / LLM boundary

| Operation | Type | Why |
|---|---|---|
| Hashing, MIME detection, schema lookup | deterministic | mechanical |
| Byte-fact attestation (artifact fields, manifest members, byte-marks, sidecar lift) | deterministic | mechanical |
| Member promotion (byte streaming, hash verify, record mint) | deterministic | mechanical |
| Derivation ops (`body`, `members`, text layers, renders, unit ops) | deterministic | pure functions (§6.3) |
| Transcription / OCR ops | deterministic **per engine version** | version-labeled; pinned by authorship (§6.4) |
| Origin-host matching (overlay resolution) | deterministic | overlay-declared |
| Form-mapped shaping (a conversation's envelopes from a declared mapping) | deterministic | a shaper — scripts, not judgment |
| Derived editorial fields (role-marked precedence resolution, §4.2.3) | deterministic | a pure function of stored blocks + schemas |
| Interpretive shaping and form assertion | LLM | requires judgment |
| Issue surfacing | LLM (faithfulness) / detector (mechanical) | depends on kind |

### 8.3 Re-runs

Every stage is independently re-runnable; re-runs are **scoped**.

- **Re-ingest** — re-encounters bytes matching an existing `id`. Appends a touch; may append origin blocks.
- **Re-attest** — re-runs the attestation layer (new mime schema, richer attestations): strips + regenerates attested facts (§4.4.6), never the authored layer.
- **Re-normalize** — re-runs the authoring pass (shaper or agent); total replacement of the authored layer.
- **Re-resolve** — bare resolver-cache regeneration (`--regenerate`), including deliberate version upgrades of version-labeled ops.

Each re-run appends a `touch[]` entry.

### 8.4 Re-stub

`re-stub` is a deliberate reset operation that returns a record to its attested baseline (§4.1), ready for fresh attestation — the verb keeps its historical name. Everything **derived from a schema decision** is discarded. Everything **tied to the bytes themselves** is preserved.

| What survives | What is reset |
|---|---|
| `id`, `hash` — byte-intrinsic. | The artifact block's attested fields, the members block, all sections/segments (authored and byte-mark alike), all context blocks. |
| The artifact block's opener (the MIME) and the origin blocks with their `uri:` history. | Record body's content zone → empty. |
| `visibility`. | |
| `touch[]` collapses to its first entry (the original ingest touch) plus the re-stub touch. | |
| The persisted bytes. | |

Re-stub is invoked deliberately — never automatic. Its uses:

- Schema-shape design changes that make existing blocks invalid.
- Records whose accumulated normalize work was wrong.
- Migration from a deprecated schema generation.

Re-stub appends a `touch[]` entry of the form `<pkg>.re-stub@<v>`. It remains the migration translation point: it accepts older frontmatter on input — including any legacy `status:` field — and always writes a current-spec-shaped record on output, preserving byte-intrinsic state and discarding everything that depended on the prior schema shape.

### 8.5 The normalization queue

`normalize` (§8.1) is the one stage the corpus tooling does not itself initiate — it is driven by an external **loop session** (a scheduled agent), which runs the mechanical shaper where the record's form mapping licenses one and works interpretively where not (§12.5). The tooling provides only the **request/claim contract** that lets any actor ask for a (re-)normalization pass and await its result; it never invokes a normalizer.

The queue is **standing demand, never a backlog**. An entry exists because some consumer wants a pass — the ledger citing into a record, an external consumer's build wanting a formed surface, an overlay newly declaring a form, guidance improving — and the queue's size measures outstanding *demand*, not outstanding *work owed*. A formless record no consumer has asked about is complete, not pending (§4.1); it enters the queue when a reason does. **The deferral principle is deployment law, not aspiration: normalization runs only under demand.** There is no standing drain program and no pre-emptive forming sweep; every ingested record is usable from birth (readable via its derived surfaces, citable at the strength its surface class carries — `ledger.md` §6.3), a drain session runs when demand exists and stops when the queue is dry, and `normalization_pressure` (below / the health report) is a *ranking input* for that demand, never a work list.

**The queue never writes records.** A record's `touch[]` and body are authored solely by `ingest` and the normalize pass (§8.1). Queue state is **external to the record** and untracked — regenerable orchestration, like `capture/` and `cache/` (§12.1). Queue operations are **read-only on records**: they may read a record (to gate on lint, or report a result) but never mutate it. One writer per concern — the normalizer owns the record; the queue owns only its own entries.

**Requests are state-independent and repeatable.** A record may be enqueued in any state — a formless proxy for a first pass, or a formed record for a *refinement* when a new overlay matches it or its guidance improves (re-normalize, §8.3). No state is terminal to the *queue*; each completed pass appends a touch. Enqueue never inspects the record. (A **terminal-contract** record (§7.8) may likewise be enqueued — an explicit re-evaluation of the terminal judgment — but it is never enqueued by default and its default pass is a no-op: see the pass gate below.)

A queue entry moves `idle → requested → claimed → idle`, recording the last pass's outcome:

| Verb | Effect | Writes record? |
|---|---|---|
| `enqueue <id> [--hint "<text>"]` | request a (re-)normalization pass; idempotent — a request arriving while one is pending joins it. `--hint` stores free-text requester context on the request, surfaced to the drain side (listing, claim, guidance) — the **proposes/disposes seam**: a reader of a formless record may propose what it looks like ("form/conversation candidate: messages[] with sender/timestamp") without authoring anything; the normalizer disposes against the bytes. A joining request's hint appends, never overwrites. | no |
| `drain` | atomically **claim** the next pending entry and emit its `id`; an empty queue is a non-error empty result — the loop's stop signal. A blocking variant long-polls for the next claim instead of reporting empty (the *standing* mode below). Reclaims a claim whose lease has lapsed (a dead session). | no |
| `finalize <id>` | close the claimed pass **complete** — gated on the **pass gate** (below); refuses (non-zero) on a blocking finding, so a dirty pass is never reported done. | reads only |
| `release <id> [--failed]` | return a claim — bare re-queues it; `--failed` records a failed outcome. | no |
| `await <id>` | block until the requested pass reaches a terminal outcome; success/failure by exit status. | reads only |

**The pass gate.** **Done** means the pass left the record **formed where its overlays declare a form** (§7.2, §4.4.6 — form-coherence lint covers the conformance half) and linting clean. Both are derived from the record itself; `finalize` enforces them together. A record governed by a **terminal contract** satisfies the gate with no stored rendering — the contract prescribes exactly that — so a terminal record drains to an immediate no-op `finalize` unless the request explicitly asks for re-evaluation; an accidental enqueue self-heals. Linting clean also means every member the record **places** has been promoted (§4.3.2.4) — the pass discovers its placements while making them, so the obligation is discharged in the same pass that creates it, and a parent whose placed member has no record does not close.

**Normalization pressure — the second demand source.** A promoted member awaiting its own pass is **demand**, not backlog: its parents want it rendered. The magnitude is mechanical and needs no field — a leaf placed in N records is wanted N times — so pressure is **derived** from the member index (§12.9) like every other cross-record fact, and the queue can be ranked by it: rendering one member that 668 records place is 668 records improved by one pass. This joins the ledger's demand (`ledger.md` §6.3 — the citation discipline enqueuing what it wants formed) as a second source on one mechanism; neither is a gate, and a leaf that no consumer ever asks about stays a complete record standing as its artifact's proxy (§4.1).

**Drivable by an external loop, in either of two modes.** The claim is atomic (concurrent loops never double-claim) and every verb is non-interactive with a meaningful exit code and machine-readable output, so an agent loop runs `drain` → normalize the emitted id in-session → `finalize` (or `release --failed`) each iteration. A **scheduled** loop (e.g. cron) drains until the queue reports empty, then waits for the next tick — simple, but the loop session itself does the polling, waking even when there is no work. A **standing** loop instead blocks on the `drain` long-poll, which waits in the tooling until a request is claimable and returns it the instant one appears — so the (costly) loop session is engaged only when there is genuinely work. Both drive the same atomic claim; the long-poll is an ergonomic over it, not a distinct contract, and the same loop body serves either. The normalizer reads the record's applicable overlays' `normalization.guidance` (mime §7.1, origin §7.2, form §7.8, atom §7.3); because form knowledge rides in overlays, one generic loop serves every source — and demand flows down from the ledger, whose citation discipline prefers formed surfaces and raises demand by enqueuing (`ledger.md` §6.3): the ledger contributes by enqueuing, never by supplying a normalizer. The loop session's first consult is the record's **governing contract**, and the pass branches four ways: (1) **terminal** (§7.8) — no-op `finalize`, unless the request explicitly asks for re-evaluation; (2) **declared form, mapped** — the shaper writes the form mechanically and there is nothing left for an agent to add, so the pass is deterministic end to end; (3) **declared-but-unmapped or asserted form** — the interpretive case, and on an already-formed record a *refinement*: improve the existing shaping, never regress it; (4) **no form, no terminal** — the **adoption sweep**: test the library's contracts against the record's own bytes and adopt by assertion where one genuinely fits (§4.4.6) — body evidence wins, substantive-content veto, and a record matching no contract exits the pass formless and reported, never force-stamped. `finalize`'s done-gate is the pass gate above, form-coherence (§4.3.2.1) included.

**Entry lifecycle and pruning.** A request and its claim are transient — each transition supersedes the prior state — but a settled pass records its **outcome** so a requester's `await` can resolve it, and so a *re-normalization* is distinguishable from an earlier pass (which the record alone cannot tell apart — only its touch chain grows). An outcome is **coordination state, not history**: the record's own `touch[]` is the durable trail. Because a requester may `await` after a loop iteration ends, an outcome is **never discarded at loop end** — that would race the awaiter. Outcomes are instead garbage-collected by **age**: a settled outcome past a grace window (plus any orphaned scratch) is prunable, never a live request or claim — so the queue's footprint stays bounded without dropping an outcome a requester still needs. The grace window and the prune trigger are operational policy, not part of the contract.

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

The members block and context blocks are NOT included. A record carrying an artifact block and one qualified origin block yields:

```
[
  "mime/<mime-type>",
  "origin/<origin-id>"
]
```

("What does this record document" is a ledger query — the concepts rostering the record, the claims citing it (`ath ledger worklist`, `ledger.md` §13), and the coverage ledger (`ledger.md` §9).)

### 9.2 The `issues` view

The `issue`-namespace projection of the annotations zone (the full annotation set is the `context` view, §4.3.3):

```
issues := []
on <!--context issue/<id>[/<subtype>]-->:
  issues += { id: "<id>[/<subtype>]", severity, resolution, detector, address?, ...fields }
```

Returns structured records — each issue carries its id/subtype + universal fields + optional `address:` + any id-specific fields. (The `sweep` namespace (§4.3.3.6) projects the same way in the full `context` view: id, `kind`, `detector`, optional `address:`.)

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

- `body` — tokens in the content zone's text-atom segment bodies and structural-mark bodies.
- `blocks` — tokens in the whole record markdown (frontmatter + every metadata/annotation block + the content zone). Always ≥ `body`.
- `full` — `blocks` plus an image-token estimate summed over an image artifact and the record's image members, each `≈ min(width·height, cap) / pixels-per-token` (`0` when dimensions are unavailable). The artifact's own dimensions are attested on its block; member dimensions come from the `members` derivation (§6.2), since the stored roster carries none — so this tier needs a resolvable artifact, and degrades to omitting the member contribution rather than failing. `full` is declared an estimate precisely so this degradation is in contract.

The text tokenizer and the image constants are an implementation choice (§12.13), not part of the contract — what the spec fixes is the **shape**: three cumulative tiers, ordered `body ≤ blocks ≤ full`. Like every §9 view it is computed on demand and never persisted.

### 9.7 The `concepts` view *(retired)*

"Which records invoke this thing" is a ledger query: the concept's artifact roster and its claims' evidence URIs point at the records, and coverage (`ledger.md` §9) is the record-first direction.

### 9.8 How views are computed

A derived-view walker:

1. Loads the record's frontmatter and parses the body's three zones.
2. For each matched block, loads the corresponding schema chain.
3. Walks blocks, collecting values per view rules.
4. Deduplicates or sorts per view.
5. Returns the result.

Views are computed at query time.

### 9.9 The `references` view

The outbound-link view. Its input is the **faithful body itself**: every markdown URL a record's segments carry, which is where the source's own links live in full. Each entry carries the link text, the URL, the address of the segment holding it, and the **derived** resolution (`resolved_uri`/`captured`, computed against the URI index at read time — §12.4.7). The resolved edge is directional toward the linked record; the reverse ("records that link *this* one") is a corpus-wide read derivable from these edges but, like cross-record content addressing (§11), the corpus-wide index is not specified here. Computed on demand, never persisted.

---

## 10. Export

A record renders correctly only inside its corpus, because its addressed surfaces — the image a positioning segment marks, the crop a transcription cites — are **derivations** that need a resolver. **Export** produces a portable, self-contained rendering by materializing every addressed surface to a file alongside the exported record and emitting a local reference to it.

Surface materialization contract:

```
<!--segment image/figure address: <address>-->   →   ![<derived alt>](<local-file>)
```

The contract is stated over the record's own addressed surfaces, not over stored body links: export reads placement from the content zone's addresses, which is where placement lives; alt text comes from the `members` derivation (§6.2).

Export is idempotent and untracked. The output layout (filenames, directory structure) is implementation-defined.

---

## 11. Out of scope

Genuinely deferred items for this spec version:

- **Automatic PDF text / OCR extraction.** Every PDF presents **uniformly** — `/Info` fields attested, and a derived body (§6.2) of per-page body-empty `image` segments addressed `page=<N>` — regardless of born-digital or scanned. Deciding a page's shape, pulling its embedded text layer, transcribing a scan into `text/ocr` (with engine/confidence provenance — the corpus owns OCR provenance rather than laundering a pre-baked layer), and outline-driven structural marks are all **normalize-pass** work over the resolver's introspection ops (§6.2). What remains deferred is an *automatic* (non-agent) text-or-OCR pass.
- **Matroska/EBML table reading.** Member-byte determinism for track promotion is no longer a discipline but a construction (§2, v32): payload extraction is the corpus's own engine-free sample-table reader, so there is no invocation to pin, no producer to attest, and no canary to watch — the pinned-muxer regime (`-bitexact` + `framing:` stamp) is retired, having been measured insufficient (cross-version drift stranded live records; the v32 changelog carries the arc). What remains genuinely deferred is the reader's **container coverage**: it parses ISOBMFF; Matroska/EBML sample tables are unimplemented, so MKV/WebM tracks stay unpromotable until that lands — a coverage gap, not a determinism gap.
- **SQLite databases.** An application's SQLite store (`chat.db`, `Photos.sqlite`, a browser's history db) is THE container of raw app data, and rows are deterministically addressable — a row/query axis would be well-defined under the disposition machinery above. Deferred **deliberately**, not overlooked: the corpus philosophy prefers **producer-declared exports** — the app's own export surface, with its declared semantics — over reverse-engineered application internals, and no real capture has yet wanted the database itself. When one does, `disposition: manifest` plus a pinned row-extraction scheme is the landing zone; until then this silence is a decision.
- **Cross-record content addressing** via `<!--members--> transport` — the shape leaves room for a corpus-wide `transport → (record_id, address)` index but the index itself is not specified. (Building it requires reconciling the `<algo>:<hex>` member-row `transport` encoding with the bare-hex record `id` — strip the prefix and confirm `algo == blake3` before matching.)
- **Range-aware navigation** for content the resolver doesn't materialize.
- **`page=<N>-<M>` ranges** and other open transforms beyond §6.2.
- **Whole-corpus build tooling** — single-record export is in scope; bulk operations are not.
- **Export to non-markdown formats.**
- **Additional semantic types** beyond the closed seven.
- **Recursive dependent capture.** `capture.references` (§7.2) fetches declared references at **depth 1** only; following a grabbed reference's own references — and any general multi-hop crawl — remains `corpus crawl`'s job, not the capture-alongside path.

---

# Implementation guide (non-normative)

## 12. Implementation guide
### 12.1 On-disk layout and sharding

The corpus layer of the instance (Part I §2.2):

```
corpus/
├── README.md                optional
├── records/                 tracked: record markdown files
│   └── <id[:2]>/<id>.md
├── schema/                  tracked: mime / origin / form / atom / context
├── runbooks/                tracked: operational knowledge (deployment notes, capture ops)
├── artifacts/               UNTRACKED: the co-located byte store (Part IV)
│   └── <id[:2]>/<id>.<ext>
├── capture/                 UNTRACKED: in-progress capture staging
├── cache/                   UNTRACKED: resolver-output cache
│   ├── <urihash[:2]>/<urihash>.<ext>
│   ├── hashes.db            derived hash index (§12.9.1)
│   ├── locations.db         attached-location index (Part IV §4)
│   └── refidx/              ref-dataset sidecar indexes, by mirror blake3 (ledger.md §6.5)
├── queue/                   UNTRACKED: normalization request/claim state (§8.5)
├── export/                  UNTRACKED: regenerable export bundles (§10)
├── corpus.toml              UNTRACKED: machine-specific config (locations — Part IV §3;
│                            transcription backend)
└── .gitignore               lists the untracked entries
```

- **`records/`, `schema/`, and `runbooks/` are tracked** in version control (the instance repo); the markdown records are the source of truth.
- **`artifacts/` is the co-located byte store and is never tracked.** The contract is only "given a blake3, this corpus can produce the bytes" (§2); the co-located tree is the default **location** among the routes Part IV declares — bulk store roots, attached trees, remote stores. Consumers should not hard-code the path scheme — they ask the corpus to locate `<blake3>`. A **promoted** record (§8.1) has no `artifacts/` entry at all: its bytes materialize through its container via the member index (§12.9).
- **Sharding is one level deep, by the first two hex characters of the leading hash**, with the same depth for `records/`, `artifacts/`, and `cache/`. That gives 256 buckets: at ~10k records the average bucket holds ~40 entries; at 100k, ~400. Deeper trees are a layout choice, not a contract (§12.15). The full hash stays in the filename, so a copy outside its shard directory still names itself fully — useful for moves, backups, and ad-hoc inspection.
- **Capture staging** lives under `capture/`: failed or abandoned captures sit there without consuming corpus identity space, and ingest unlinks a staged capture on success.

#### 12.1.1 Artifact locations

**Moved to Part IV** ([`custody.md`](custody.md) §3–§6): location declaration (`corpus.toml`), store and attached kinds, ingest placement claims, move/adopt semantics, presented manifests and the residence scanner, route preference, redundancy floors, and the residency query (`corpus locate`). This stub keeps the section number so existing citations resolve.

### 12.2 Schema directory layout

The namespaces of §3 are conventionally laid out as:

```
schema/<namespace>/<namespace>.yaml              namespace universal
schema/<namespace>/<axis>/<axis>.yaml            axis common guidance (mime and atom)
schema/<namespace>/<axis>/<axis>_<id>.yaml       specific declaration
```

The **underscore-flattened** subtype convention (`text_html.yaml` inside `text/`, rather than `html.yaml`) keeps filenames self-describing.

Annotation overlays use the namespace pattern under `schema/context/` — `context/<ns>/<ns>.yaml` layering under `context/<ns>/<id>.yaml` (the bundled `issue` overlays live here).

Inside `origin/`, overlays nest by **URI scheme family** (§7.2): `schema/origin/web/<host>.yaml` for http(s) sources (host-matched), `schema/origin/otherwise/<id>.yaml` as the catch-all, and other families (`urn/`, `file/`, `s3/`) as a corpus needs them, with the namespace universal at `schema/origin/origin.yaml`. The overlay id is the bare `<id>` regardless of sub-namespace, the flat `schema/origin/<id>.yaml` form still read for back-compat; a non-family directory is a producer id (`google-takeout/gmail.yaml` = subtype overlay `google-takeout/gmail`, §7.2). `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`.

### 12.3 Capture

A capture takes a target — URL, filesystem path, manual upload — and produces a record plus its binary in the content-addressed store. The pipeline is content-addressed end-to-end: identity is the hash of the bytes.

#### 12.3.1 Fetch and capturer routing

**Routing is overlay-driven — no hardcoded host knowledge.** The capturer is chosen by the origin overlay's `capture.capturer:` field (`browser` — Playwright/HTML, the default; `video` — yt-dlp); `corpus capture --video` / `--no-video` are one-off overrides. There is no built-in video-host list: a host that should go to yt-dlp declares `capturer: video` in its overlay, so an undeclared video URL captures as HTML unless `--video` is passed.

- **HTTP/HTTPS URL** — fetched with redirect-following enabled. The original requested URL and the final-after-redirect URL both land on the record's first origin block (`uri:` list).
- **Filesystem path** — copied from staging, which is unlinked at ingest; the origin block is uri-less and carries `filename` + `source_modified` instead (§7.2).
- **Manual upload** — the operator supplies the bytes and any origin URI.

Inline media a transport merely *references* (images in an HTML page, etc.) are not separate records: ingest attests one members-block row per asset (deduped by `transport` byte-hash), and the body carries a placement or positioning segment (§4.3.1.4) — never a stored intra-corpus link. A raw archive is no exception: its roster IS its attestation, and a member becomes its own record only by deliberate promotion (§8.1). Hyperlinks to *other* resources are reconciled to intra-corpus references during cross-reference resolution (§12.4.7).

#### 12.3.2 MIME detection

MIME detection selects the **mime schema** that drives the rest of the pipeline (`derived_hashes`, address scheme, attestations, derivation ops):

1. **Magic-byte sniffing** — the primary path (`mime.detect`). Inspect the leading bytes; refine ambiguous container magic by form-type and extension (a RIFF prefix → webp/wav/avi by its offset-8 form-type; an ISOBMFF `.m4b` → `audio/mp4`, not `video/mp4`, so it routes to transcription rather than the video keyframe path). A `PK\x03\x04` zip is refined by its members (`_refine_zip`): universal formats (OOXML / EPUB / JAR) match fixed internal paths baked into the tooling, while a corpus's *own* zip-shaped types (a diagnostics export, a backup bundle) match their schema-declared shape signatures (`applies_to.zip_members` / `zip_member_patterns`, §7.1) when a `corpus_root` is in scope — vendor-specific recognition lives in the overlay, not the package, and an unrecognized zip stays `application/zip`. An mbox opens with a `From ` separator at offset 0. A single email message (`message/rfc822`, typically a promoted mbox `msg=<N>`) has no magic number, so it is recognized by **header shape** — a distinctively-email header prefix (`Return-Path:` / `Received:` / `X-GM-THRID` / …), or, after the extension hint, two consecutive header-shaped lines — with the mbox `From ` separator always winning first (an mbox opens with the separator, an eml never does).
2. **Extension hint** — disambiguates where magic is generic, and names the type for extensionless or schema-id-from-filename cases.
3. **`unknown` sentinel** — when both fail. Record the gap; the artifact is still valid, it just gets no format-specific attestation or derivation.

The detected MIME becomes the **artifact block's opener argument**, which is authoritative — there is no frontmatter media-type field (§4.3.1.1).

#### 12.3.3 Hashing

The hash families of §2 land at different destinations by residency class (§2, §7.6 encoding):

- **blake3 of the bytes** — always, at ingest. The artifact's `id` (bare hex): identity and filename stem.
- **Byte-stable recipes** (§7.9) — computed at ingest from the resolved union (default set ∪ mime ∪ origin overlay): `residency: record` recipes (the default set's `sha256` + `md5`) land in frontmatter `hash:` *and* the index; the rest (the default set's `blake3-prefix-ladder` grown-export screen) land in the index, record-flushable on demand (§12.9.1).
- **Procedure-versioned recipes** — `html-stampfree@1` capture-invariant identity: index-first, reaching frontmatter `hash:` only by deliberate flush under its full `<procedure>@<version>` tag (§4.2.1, §12.9.1).
- **Fingerprints** — atom fingerprints (image pHash, text simhash, …), **opt-in and schema-gated** (§7.7); default off. Procedure-versioned **similarity-class** (§7.9), index-resident: keyed by segment address on multi-atom records, record-scope on single-atom ones; never record-flushed — a similarity value is not an identity.

There is no mandatory per-MIME recipe or fingerprint. A MIME with no `derived_hashes` declaration and no fingerprint knob is blake3-`id`-only — no `hash:` field at all — and that record, and its empty index slice, is normal.

#### 12.3.4 The record at birth

Ingest emits the record — the artifact's proxy, complete at birth (§4.1). The frontmatter carries only the bytes-identity header — `id`, `hash:` (the declared `residency: record` byte-stable recipes, §7.9), `touch: [<pkg>.ingest@<v>]`. Everything else lands in body blocks:

- The **artifact block**, its body holding the format-intrinsic extended fields the mime schema declares, named bare (`title`/`author`/`page_count`, not `pdf_title`; §4.3.1.1). Sources: PDF info dict, EXIF, ID3, HTML `<meta>`, OPF Dublin Core, ffprobe streams.
- The mime schema's remaining **attestations** (§7.1): manifest/exposable members per the disposition, structural byte-marks, sidecar lift.
- The first **origin block** from capture context — `uri:` + `snapshot:`, or the uri-less local-file form (§7.2). A **SingleFile save** is a third shape: a manual save carries a self-describing banner comment in its first bytes (`Page saved with SingleFile` + `url:` + `saved date:`), so a save dropped straight into `capture/` and ingested (no capture step) seeds a *retrieval* origin from the banner — `uri:` = the banner URL, `snapshot:` = the saved date parsed to ISO-8601 with its numeric offset **preserved** (not converted to UTC; the parenthesized zone name ignored) — instead of the uri-less local-file form. An explicit capture-sidecar `source_url` still wins; a banner-less or non-HTML file is unchanged. The banner is scanned only within a bounded head.

No `content_type`, `hashes`, `classifications`, `tags`, or `uris`/`capture_dates` frontmatter — none of those exist in this model. The content zone holds attested byte-marks only (§4.3.2.3); the stored body is the normalize pass's (§12.5), and the derived body is readable immediately (`corpus body`, §6.2).

#### 12.3.5 Dedup, re-capture, and capture provenance

Ingest looks the artifact up by `id` against the existing corpus:

- **Match** — the bytes are already in the corpus. Fold the new capture into the existing record's origin blocks: append the inbound URL to a matching origin's `uri:` list when it aliases one (via known shortlink/redirect + `url_equivalent` rules), or emit a new origin block when it is a genuinely separate source (§5.2). Never a new record.
- **No match** — a new artifact. Write the record under `records/` and the binary to the claimed location (Part IV §3.1; the co-located tree by default).

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

**Sidecar → origin block (ingest attestation), then deleted.** The `.info.json` is *non-primary-source* metadata, so the sidecar lift copies every declared key into the **origin block** as a flat `ytdlp_<key>` field (`ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts, …) via `records.merge_origin_fields` — never the artifact block, the body, or the frontmatter. `comments[]` (when returned) becomes a `ytdlp_comments` list field; `webpage_url`/`original_url` fold into the origin `uri:` aliases. The lifted key set is schema-declared — `sidecar.ytdlp_keys` on the video/audio mime schema (§7.1); the lift is mechanical, not hardcoded. One datum is *structural* rather than flat: **`chapters[]`** (the uploader's outline) is consumed into **structural segments** (producer-declared byte-marks, §4.3.2.3) — each chapter title the segment's **body**, each bound a `time=` mark address. Chapters are consumed into marks, never copied to a `ytdlp_*` field; a chapter mark is the producer's own declared boundary rather than a reading of the primary artifact, so this respects the same primary-artifact boundary. Transcription is off the pathway entirely: it is the `transcribe` derivation op (§6.2), consumed at normalize.

**Title is derived, never authored** (§4.2.3). The display title resolves mechanically from the block-level role-marked candidates — the artifact block's bare `title`, or an origin `ytdlp_title` (the `ytdlp_` prefix survives because the origin opener names the source record, not the tool; §4.2.1) — no authoring pass, normalizer or otherwise, is involved. A media capture's title candidate routes to the origin's `ytdlp_title` (an A/V artifact block carries no `title`). After a successful lift, ingest deletes the sidecar; enrichment is one-shot (re-capture to restore — the lifted fields already persist on the record).

**Per-host transcription (the `transcribe` op).** The op resolves the record's origin host and reads the overlay's `transcription:` section (§7.2): absent → the global `[corpus.transcription]` adapter; `enabled: false` → skip (an `info` issue, not a `warning`); `adapter`/`base_url` → a per-host backend that overrides the global even when the corpus default is `noop`.

#### 12.3.8 Pagination reconciliation

A paginated work — a thread / multi-page article / gallery a site splits across `?page=N` / `/page-N` URLs — is **one logical artifact**. The overlay's `capture.pagination` knob (§7.2; browser capturer only; `capture/pagination.py` + `_reconcile_pagination`) walks the pages and ingests a single merged record instead of capturing page 1 only or fragmenting the work into N content-addressed records. Both `corpus capture` and `corpus crawl` route through `capture_and_ingest`, so the branch lives there, after the dedup short-circuit:

1. **Walk + stage.** Each page is fetched through the staging-only `capture()` path (so its `url_rewrite` / `interactions` / chrome-strip / fidelity all apply per page), its HTML read into memory, and its staging file unlinked immediately — `_sanitize_filename` drops the query string, so `?page=N` pages would otherwise collide on one staging name, and per-page bytes must never be content-addressed. The next page is found by `<link/a rel=next>` (the `<link>` survives the chrome strip — it lives in `<head>`) or a `next.selector` override; the walk stops at no-next, a repeat URL, or `max_pages` (flagged).
2. **Merge.** Page 1 is the framework. The content region is the declared `content_selector`, else a structural diff of page 1 vs page 2 (`detect_region`: descend while exactly one matched-identity child differs; the container whose children then diverge is the region). Each later page's content children are appended into page 1's region, **deduped by element id or a normalized-subtree hash** (so a repeated quoted-OP / threaded post isn't double-counted); a page adding zero new children stops the walk.
3. **Ingest once.** The merged HTML is written to one staging file and ingested — the sole content-addressed artifact + record. A single page (no next link) skips the round-trip and ingests the original snapshot bytes verbatim, so its id is byte-identical to a non-paginated capture (and no pagination provenance is attached).
4. **Provenance.** The clean seed is the recorded origin URI; every constituent page URL — both the bare site form (what a crawl discovers) and the pinned `url_rewrite` form — is folded in via `records.add_origin_uri_alias`, plus a `pagination: {pages, form, posts}` field via `records.merge_origin_fields` (`posts` is the id-aware item count — `_count_items` counts id-bearing region children when any are present, so framework `div`s inside the region don't inflate it; else all children). When the merged count falls short of an advertised `expect_count.selector` value, or `max_pages` was hit, a `pagination-incomplete` `warning` issue (capture-stage detector `corpus.capture`) is emitted rather than silently shipping a lossy record.

**Crawl interaction.** Recording every constituent URL as an alias makes the dedup short-circuit fire when a crawl later discovers `/page-N`, resolving to the merged record instead of re-capturing. `crawl._expand` additionally drops any link already in the expanding record's own origin URIs, keeping those pages out of the frontier (genuine content links — post permalinks, cross-thread — are kept).

#### 12.3.9 URL equivalence and redirect-aware short-link dedup

A record's origin URI list should hold **one URI per distinct resource**, and an inbound URL should match a record whenever it denotes the same resource, even when the spelling differs (query noise, `/page-1` ≡ bare). The per-host `capture.url_equivalent` overlay section (§7.2) declares this; the tooling reduces every URL to an **identity key** and compares keys instead of normalized strings.

- **The primitive** is `urls.identity_key(url, equivalent, *, url_rewrite)` (pure, stdlib-only). `urls.normalize_equivalence` coerces the overlay value to a canonical config; the key is `normalize` → (if `on_rewritten`) apply `url_rewrite` first → (if `query: drop`) strip the query → apply the `rules` in order (via the shared `urls.apply_rewrite_rules`) → tidy a dangling delimiter → fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`). With no config it returns exactly `normalize(url)`, so the layer is inert (opt-in) for any host that does not declare it. The trailing-slash fold is in `identity_key`, **not** `normalize`, on purpose: `normalize`'s output is the URL `crawl._expand` stores and re-fetches (a server may distinguish `/a/b` from `/a/b/`), so the fetched form keeps its slash while the comparison key folds it.
- **Identity ≠ fetch.** The identity key is a comparison key only. Crawl still stores the fetchable normalized URL in its frontier/visited; only the dedup *comparison* uses identity keys. Equivalence must never decide which bytes are fetched (that is `url_rewrite` / `interactions`).
- **The recipe-aware wrapper** `recipes.identity_key_for_url(corpus_root, url)` resolves the host's `capture` recipe once and passes its `url_equivalent` + `url_rewrite` to `identity_key`; single-URL sites (`records.find_by_uri`) call it directly, while bulk sites (`records.build_uri_index`, `crawl._expand`) memoize the recipe by host.
- **The four identity sites** all key by `identity_key`: `build_uri_index`/`find_by_uri` (capture short-circuit + raw-URL resolve), `crawl._expand` (frontier dedup, folding in the own-URI exclusion), `_reconcile_pagination` (within-walk seen-set + constituent-alias recording), and `records.add_origin_uri_alias(post, alias, *, corpus_root=)` — which, given `corpus_root`, skips an alias whose identity key matches an existing origin URI, keeping origin blocks minimal.

`identity_key` canonicalizes a URL *string* and never touches the network, so an **opaque short link** (`https://vt.tiktok.com/XXXX/`) keys differently from the canonical it 301s to. The redirect-resolution layer closes that gap by following the redirect chain to the final URL **without downloading the artifact**:

- **The primitive** is `redirects.resolve_final_url(url)` (pure stdlib): a per-hop HEAD (falling back to a body-less GET on 405/501) follows `Location` headers up to `MAX_HOPS`, never reading a response body. Redirect loops, hop-cap, non-web `Location`s, and any network/parse failure all return the input unchanged: a probe never breaks the caller, it only improves dedup when it succeeds. `redirects.is_probably_short_link(url)` is a conservative gate (known shortener hosts, `vt.`/`vm.` subdomains, or a single short opaque path segment) so a normal canonical URL never pays the network round-trip.
- **The recipe-aware wrapper** `recipes.resolve_identity_for_url(corpus_root, url)` returns `(final_url, identity_key)`: it follows redirects only when the URL looks like a short link, then computes the identity key from the **final** URL — so the destination host's `url_equivalent` strips the volatile query the canonical resolves with, and a short link whose apex differs from its destination (`youtu.be` → `youtube.com`) picks up the destination's equivalence rules.
- **Capture short-circuit (second stage).** `capture_and_ingest` keeps the cheap string-identity `find_by_uri` first; on a miss, `_redirect_dedup` runs the redirect-aware resolution and re-checks — catching a fresh short link to an already-captured canonical **before** the download, and folding the short link into the matched record's origin URI list as an alias. `--force` skips both stages, and the short-link heuristic keeps the probe off the hot path.
- **`corpus check <url>`** (`_cli/check.py`) is the read-only surface: the same resolution (canonicalize + overlay recipe + redirect-follow), then `find_by_uri`, reporting the matching record hash + path or "not captured". It never captures, ingests, downloads, or writes. Script contract: exit `0` already captured, `1` not captured, `2` usage error, `3` resolution error; `--json` emits `{url, resolved_url, identity_key, redirected, captured, record, path}`; `--no-follow-redirects` does a string-identity-only check (offline / fast).

#### 12.3.10 Dependent capture (`capture.references`)

A page's most relevant outbound links are part of the capture itself — a product-detail page's manual or spec sheet far more than the other hundred links on the page. The per-host `capture.references` overlay section (§7.2) declares which links those are, and the tooling fetches them depth-1 as their own records. The home is one module, `corpus.references` — *declare, match* — with the *fetch* delegating to the existing capture/crawl machinery. Opt-in throughout: no rules → entirely inert.

- **The rules** (`references.parse_rules` → `ReferenceRule`): a list of `{match, role, capture, cross_host}`. A rule's `match` keys (`selector` CSS, `href_pattern`/`text_pattern` regex on the resolved href / anchor text, `rel` token) are ANDed; rules are ORed. `role` (corpus-local label — `manual`, `spec-sheet`) labels the declared target; `capture: true` opts the target into the depth-1 grab (default false = surface-only); `cross_host: allow` (the default — manuals are off-host) lets a match reach another host, `same` host-restricts it. Parse-tolerant: a non-mapping entry, a rule with no match key, or a bad `cross_host` is skipped, never fatal.
- **Matching** (`references.match` / `matches_for_record`): parse the DOM, scope candidate anchors by `selector` (else all `<a href>`), apply the AND filters, resolve relatives against the base URL, normalize, drop non-crawlable hrefs (`urls.is_crawlable_href` — the same filter `links`/`crawl` use), enforce `cross_host: same`, and dedupe by URL (DOM order, first rule wins for role/capture). `matches_for_record` applies the host's rules against the record's primary origin URI and excludes self-links. Shared by `corpus links --references` and the grab.
- **The depth-1 grab** (`references.fetch_references`): `select_for_capture(matches, force=)` picks targets — `force=True` (`--with-references`) all, `force=False` (`--no-references`) none, `force=None` (default) the rules' own `capture: true`. Each selected, not-already-captured target is fetched once via `capture_and_ingest` — depth is fixed at 1 (a grabbed target is ingested as its own record, never expanded; multi-hop stays `crawl`'s job, §11). Best-effort: a per-target failure is recorded, not raised. Surfaces: `corpus capture --with-references` / `--no-references` (the inline grab after the primary ingest), `corpus crawl --references [seed]` (the deferred sweep; `--dry-run` lists pending targets).
- **Discovery + view.** `corpus links --references <record>` previews the declared subset, each line annotated `[role=…, captured|pending]`. Whether a declared link names a captured record is a read-time derived edge over the body's links (§9.9, §12.4.7), self-healing (`captured ⇄ pending`) under capture, removal, and supersession.

#### 12.3.11 Pre-ingest bundle assembly (`corpus assemble`)

Some sources deliver an export as one or more **transient part archives** — an expiring download job, a solid compressed stream with no member index (a tgz) — where the delivered envelope is worthless to preserve and hostile to containment resolution; others deliver **no envelope at all** — an export tool that writes a loose directory tree straight to disk. `corpus assemble --origin <overlay-id> <part…> [--add <file>]…` repackages such a delivery (a part is a tar/tgz/zip archive or a directory tree) into ONE indexed bundle **before** ordinary ingest, driven entirely by the overlay's `capture.assembly` config (§7.2): union the parts' member trees (`merge_parts`, `conflict: error` on divergent same-path bytes), drop declared-cruft members (`excludes` — reported, never silent), place declared `additions` at the bundle root (the original tree is never touched; any restructure exists only as an asserted `rewrites` rule), derive origin fields mechanically (`derive` patterns over the source filename convention, addition contents, and directory-member head bytes; CLI flags override), and write the bundle plus its capture sidecar (`origin_schema:` + fields, §12.3) into `capture/` staging. A directory source's member relpaths come verbatim from its tree root and member mtimes from disk; having no envelope it leaves no `source_parts` tombstone — its assertion of byte identity is the per-member blake3 the manifest records. The engine is two layers: a **reusable deterministic bundle writer** (sorted members, verbatim paths, source mtimes, per-member zstd with `stored` for already-compressed types, archive comment stamped with the job identity, streaming, atomic; same inputs → same bytes) — shared with `corpus session capture` and the planned `pack` verb (§12.8) — and the overlay-driven assemble frontend. The consumed parts are recorded as `source_parts` tombstones (`<filename> blake3:<hash>`) on the bundle's origin block, and are retired via `rm` only after the bundle's members verify container-resolvable. Assembly is the one deliberate exception to parse-tolerance: an unreadable source member aborts with no partial bundle — a bundle is complete or absent. Member byte-identity is untouched by re-packaging (§2), so records promoted from a part archive survive an assemble→retire cycle with zero edits — residence just moves.

#### 12.3.12 From-save capture (manual SingleFile saves)

A manual SingleFile save — a page a human saved from their own browser session — is often the *only* faithful record obtainable: content behind a login the tooling can't replay, a page since changed or removed, a session-specific view. **From-save capture** makes such a save a first-class capture: `corpus capture <path>` (the argument resolves to an existing local file rather than a URL) replays the saved DOM through the same browser pipeline live capture uses, so the host overlay's `capture.interactions` (§12.3.6) apply identically to both. The save is not merely ingested — it is re-rendered so the per-host chrome strip and media surfacing run against it.

- **Provenance is the banner.** The save's SingleFile banner (§12.3.4) supplies the origin URL (used to look up the host recipe) and the saved date. Absent a banner, a `<file>.capture.yaml` sidecar's `source_url` / `fetched_at` is the fallback; with neither, from-save refuses with a clear error — it cannot record a capture whose source URL is unknown.
- **The save is the honest state — nothing is fetched live.** The file loads via `file://` in a headless browser with CSP bypassed (a save may carry a CSP `<meta>`) and **every http/https request aborted**. A SingleFile save has already inlined every asset as a `data:` URI, so the saved bytes are self-contained; the abort guarantees a dead-script DOM can never reach the network to backfill what the human's save did not capture. The overlay's `capture.interactions` still run (`DEFAULT_STEPS` when the recipe declares none) and remain best-effort — a click / lazy-load step that depended on live scripts degrades to a no-op, while `remove` / `expand` / `eval` DOM surgery applies as in live capture.
- **The snapshot is stamped to the saved date.** The re-snapshot injects the same `corpus-*` metas live capture does, but with `corpus-capture-url` = the banner URL and `corpus-fetched-at` = the saved date, and ingest seeds the record's first origin with `snapshot:` = the saved date — the fetch happened when the human saved the page, not when it was re-snapshotted. Fidelity, viewport, and interactions resolve from the overlay exactly as for live capture.
- **The source is retained.** From-save never unlinks the source file — a manual save can be irreplaceable — consuming only the re-snapshot staging file at ingest. The already-captured short-circuit (§12.3.5) and `--force` behave as for a URL capture, keyed on the resolved banner URL.

#### 12.3.13 Mailbox window reduction (`corpus mbox-window`)

A provider that exports **the whole mailbox every time** (Google Takeout's All-Mail mbox) makes each successive snapshot near-total re-delivery of bytes the corpus already holds; persisting every snapshot re-persists gigabytes for kilobytes of news. **Window reduction** is the pre-ingest answer, the mailbox sibling of §12.3.11: `corpus mbox-window <source.mbox> --against <record>…` streams the transient full export and writes into `capture/` staging a **window bundle** — a valid mboxrd holding ONLY the members not already persisted in the named lineage — plus its capture sidecar; the full export is then discarded, never ingested (its identity survives on the bundle's origin fields, tombstone-style). Mechanics:

- **Dedup keys on member identity, never position.** "Already persisted" is decided per member by the un-stuffed member blake3 (§12.11 — the promotable identity, §8.1); ordinals scatter across exports and mean nothing. The exclusion set is **derived at run time, never stored**: the union of (i) a full streaming enumeration of each lineage record's artifact bytes where locally present, (ii) each lineage record's declared `msg=` member-row transports — the fallback when the bytes are remote or retired, warned, since a selectively-declared mailbox declares a subset — and (iii) every standalone `message/rfc822` record id in the corpus (a promoted or independently-ingested message is a persisted member wherever it now lives).
- **The lineage is transitive.** Each `--against` expands through the named record's own `window_against` origin field, so naming only the latest window reaches the whole chain back to its baseline snapshot. A deliberate re-baseline (a new full snapshot ingested whole) starts a fresh lineage.
- **Members copy raw.** A selected member is copied verbatim — separator line plus stuffed bytes — in source order, so the bundle is a valid mboxrd whose members carry byte-for-byte the identities the source held (§2). Within-source duplicate members (the same blake3 twice) fold to one copy, counted. An unreadable source aborts with no partial bundle (the §12.3.11 exception to parse-tolerance); an empty delta emits nothing and says so.
- **Provenance rides the sidecar** (`origin_schema:` + `origin_fields:`, §7.2, overlay id supplied by `--origin` exactly as `assemble` takes it, or auto-stamped from the `default_origin` binding when the flag is absent — below): the source export's identity (`source_export`, `source_modified`, `source_message_count`), the window bounds derived from the selected members' Date headers (`window_start` / `window_end`), the counts (`window_count`, `excluded_count`, `duplicate_count`), and **`window_against`** — the lineage record ids as **plain hashes, deliberately not `corpus://` refs**: they record what was subtracted at build time (process provenance), not a resolution route — no member resolves through the lineage — so a later-retired lineage record must not raise `dangling_origin_refs` (§12.8).
- **Full declaration is the window convention.** Post-ingest, `corpus reattest <id> --messages 1-<N>` declares every member — affordable precisely because the bundle is thin — so the manifest doubles as the window's **human delta index** (per-member date / from / subject) and as the **machine dedup-set** the next window subtracts without re-scanning artifact bytes: a fully-declared window's roster IS its member set.
- **Year-split for full snapshots (the re-baseline shape).** A full snapshot need not persist as one monolith: `corpus mbox-split <export>` partitions the canonicalized members by Date-header year (the UTC boundary rule, §12.3.14) into per-year mboxes — **closed years only** (strictly before the current year; a member with an unparseable Date is never falsely closed, it stays with the current residue) — and assembles them into ONE deterministic zip container staged for ordinary ingest: a `zip-manifest` record whose `<YYYY>.mbox` members are each **promotable** (§8.1) to a first-class mbox record whose bytes stay in the container. The current year's members emit as a residue mbox handed to the window flow, never to the container. The payoff compounds with the chrome strip: a closed year's stripped mbox is **byte-identical in every future full export**, so the next re-baseline's year members re-encounter (origin append, zero new mints — §12.3.5) and only the newly-closed year mints; a full snapshot's marginal cost converges to one year plus the hot end. The container sidecar carries the source export's identity + transport, the strip disclosure, the per-year member counts, and the excluded current-year/undated counts. Mail's years-through-2025 stratum is the grandfathered `eras` entry (§12.3.14) — closed at year grain, never re-cut; the forward grain from 2026 is month per the standard, and `mbox-window` remains the member-dedup mechanism the rolling current-period record rides.
- **Provider-metadata headers strip at capture — the mailbox chrome strip.** A provider that mutates per-message metadata *inside* the exported bytes (Gmail's `X-Gmail-Labels`: read state, categories, importance, user labels — measured as the COMPLETE churn set between two real exports: member identity modulo that one header was 99.1% stable, every residual an arrival or purge) makes member identity hostage to workflow state. The remedy is the HTML chrome-strip precedent (§12.3.6) on the mail axis: a **declared header list** is removed from every member's header zone (folded continuations included; body lines never touched) **before identity** — the stripped bytes are the stored bytes, blake3 over them the one identity, exactly as a chrome-stripped DOM is the stored page. Declarative list only, no eval hook — mail surgery must be reviewable. **The declaration is schema config, never a verb — and the declaring grain is the origin overlay, not the mime schema.** Label chrome is producer knowledge, so `strip_headers` lives on the *producer's* overlay (§7.2) — e.g. `google-takeout/gmail` — exactly as a host's chrome-strip interactions live on `origin/web/<host>` overlays (§12.3.6); the packaged distribution ships no strip values on any grain. The `application/mbox` mime schema (§7.1) carries no `strip_headers` of its own — it supplies the **interaction point** only: it documents the strip hook, and it carries the one corpus-local **binding**, `default_origin: <overlay-id>` — "an unattributed mbox entering this corpus is presumed produced by this origin" — which is what keeps canonicalization unconditional at identity-mint time even when no sidecar stamps an origin. Resolution precedence, most-specific first, in the fingerprint-knob shape (§7.7): (1) the CLI `mbox-window --strip` override; (2) absent that, the **stamped** origin's `<id>[/<subtype>]` ladder (§4.3.1, §7.2) — ingest reads the sidecar's `origin_schema` before hashing; (3) absent a stamped origin, the `default_origin` binding's own ladder; (4) absent both, off. The **ladder** is the same grammar the opener already carries: a stamped compound (`google-takeout/gmail`) is grammatically id + subtype, so the walk tries the subtype overlay first, then the id overlay — one segment shed at a time — and the first of the two that DECLARES `strip_headers` is final: an explicit empty list is itself a declaration, meaning "no strip." The ladder never crosses producers: a stamped origin whose walk finds no declaration leaves the strip OFF outright — falling through to another producer's chrome list would be a category error, so the `default_origin` binding is consulted only when nothing is stamped at all. **Auto-stamp** closes the loop: `mbox-split` and `mbox-window`, run with no `--origin`, stamp their emitted sidecar's `origin_schema` from the `default_origin` binding (disclosed in their output) — attribution is config-automatic by the same principle as the strip. Ingest itself never invents origin attribution; the binding drives canonicalization alone, and attribution enters only via a sidecar. And **ingest applies the resolved strip automatically** when a standalone mbox stages, so the invariant can never depend on an operator remembering a pre-processing command. This is the one deliberate amendment to ingest's hash-what-staged contract: canonicalize-then-hash where declared, with the delivered bytes' blake3 preserved as `source_transport` on the origin block (`stripped_headers` + the member count beside it) so the pre-strip identity is disclosed, never silently lost. An already-canonical file (a window bundle emitted stripped; a re-drop of stripped bytes) passes through untouched. `corpus mbox-window` resolves the SAME config for its source, its emission, AND its lineage artifact enumeration — so a pre-strip (label-full) snapshot still serves as lineage across the strip boundary, its members hashed as-if-stripped at scan time. Two caveats: the declared-member fallback carries pre-strip hashes and cannot cross the boundary — lineage older than the strip needs its artifact bytes present (warned, never silent) — and the strip applies only where a mailbox enters standalone: members inside an ingested container must stay byte-identical to their container route (§2), so a mail export's mailbox is extracted and staged, never ingested-as-zip.

- **Producer member exclusion — `exclude_members`** *(v37, owner ruling)*. A producer overlay MAY declare a member-exclusion predicate list beside `strip_headers`: each entry names a header and the values that exclude a member (`google-takeout/gmail`: `header: X-Gmail-Labels`, `contains: [Spam, Trash]`). Declarative list only, no eval hook — exclusion surgery must be as reviewable as header surgery. This is a **policy filter, not canonicalization**: the owner rules the content itself out of scope, and excluded members enter no bucket, no container, no record — captured nowhere, by design. The motivating measurement: Gmail auto-purges Spam/Trash after 30 days, so those members make CLOSED periods unstable by mere passage of time (a settled 2024 stratum dropped members between two real exports purely by purge) — excluding them is what makes the producer's closed-period byte-stability claim honest under `measured` onboarding (§12.3.14). Mechanics: the predicate resolves through the same §7.2 id/subtype ladder (and `default_origin` binding) as `strip_headers`; it reads the header **before** the strip removes it (same pass, read-then-strip); `mbox-split`, `mbox-window`, and the export-diff measurement all apply the same resolved exclusion, so strata, rolling window, and measurement agree. Disclosure: per-bucket excluded counts on the emitted sidecar origin fields plus the run total — the omission is always visible, never inferred.

#### 12.3.14 Temporal stratification — the standard for re-delivered temporal exports

A producer that re-delivers **temporal content** — mail, message-platform exports, photo libraries — generalizes past the mailbox precedent (§12.3.13) into a named standard: **temporal stratification**. The same forces that shaped the mailbox flow — recurring full-export waste, provider-metadata churn, and the closed-vs-live boundary — recur on every date-addressable stream, so the standard fixes the grain and the stratum shape once, leaving only the producer's canonicalization measurement and its export-to-period mapping as onboarding work. Mechanics:

- **The model.** Any re-delivered temporal stream stratifies into: **closed periods** at **month grain** — the standard, one order finer than the mailbox year-split (§12.3.13) — byte-stable after canonicalization and therefore re-encountered (origin append, zero new mints, §12.3.5) by every future export; ONE **rolling current-period record** per stream, re-established on every export — idempotent when nothing changed (the re-cut is byte-identical, so it re-encounters rather than re-mints), superseding its predecessor when the period grew (continuity-gated, §12.8; the prior cut retires only after the ledger's citations move — operator-gated, NEVER automatic deletion), a disclosed retire path when the period shrank (a mid-period purge, reported rather than silently absorbed); a standing, never-closing **undated bucket** for members carrying no parseable date; and OPTIONAL **year containers** assembled from twelve settled months at year close — the closed-years-container pattern (§12.3.13), recast one grain finer as an assembly over months rather than a partition over messages. Grain is independent of capture cadence: a bi-monthly export closes several months in one batch; nightly re-establishment of the rolling record costs nothing on a quiet day, since nothing changed to re-mint.
- **The boundary** *(v34, owner ruling)*. Period boundaries are **UTC calendar boundaries**, uniform across every producer and every grain — there is deliberately no per-source timezone knob, because a boundary that moves per source silently duplicates or drops boundary-straddling members between strata that should agree. A date-axis value carrying an offset (an RFC 5322 `Date:` header, an offset-bearing ISO timestamp) **converts to UTC before bucketing**; a **naive** value (no offset anywhere in the bytes — an EXIF-style local time) buckets **at face value**, because inventing an offset would fabricate a fact the bytes do not carry — which of the two a producer's axis yields is a property the onboarding measurement records with the rest. A third value class exists *(v38, owner ruling)*: **rendered-local** — a producer that stores UTC internally but renders every timestamp into the exporting machine's local zone at export time, with no offset in the output and no per-message zone anywhere (imessage-exporter: chat.db is Apple-epoch UTC, the renderer converts through the machine zone). Such a producer's overlay MUST declare **`render_timezone:`** (an IANA zone name, never a fixed offset — within one export the offset varies under DST, so conversion runs through tz-database rules), **banked with the measurement that proved it** (rendered strings reconciled against a known-UTC reference from the same export), and rendered values convert through the declared zone — DST-aware — to UTC before bucketing. The zone is an **export-run property, not a machine constant** (a machine with automatic timezone that exports while traveling renders in that location's zone): each export is verified against a known-UTC reference where one exists, and an export measured to a different zone converts through *its* measured zone — declared at the split for that export and disclosed on its emitted sidecars — rather than the overlay's standing value. This declares a measured fact about the render, never invents an offset, and the boundary stays UTC for every producer: the v34 prohibition was on per-source *boundaries*, and it stands. A rendered-local axis with no declaration buckets nothing — the members land undated rather than silently mis-filed at face value. Close-out follows from membership, not from a clock: a period **closes at the first export taken after its UTC end** — an hour after or a week after changes nothing, since membership keys on each member's own date and only content dated within the period ever lands in its container.
- **The declaration.** A `partition:` block on the producer's origin overlay, beside `strip_headers` (§12.3.13) — resolved by the same §7.2 id/subtype ladder and, for an unattributed export, the same `default_origin` binding: the corpus prescribes the stratification, the tooling only executes it.

  ```yaml
  partition:
    grain: month           # the standard closed-period grain
    onboarding: measured   # or settled-first-cut (v36, owner-ruled — the gate bullet below)
    eras:                  # optional: historical strata grandfather at their own grain
    - until: "2025"        #   e.g. mail: closed YEARS through 2025
      grain: year
    undated: standing      # the never-closing bucket (the default)
    assemble: year         # optional: year containers as month assemblies
  ```

  The `eras` schedule is what lets a future full-export re-baseline re-encounter history at the grain it already settled at: an existing stratum is never re-cut by default just because the standard's grain moved on.
- **File-grain sources split with `corpus period-split`** — the §12.3.13 split's sibling for a directory/zip of member FILES rather than mailbox messages (a photo library: originals + JSON sidecars; any per-file export tree). Each member's date resolves through a declared **date axis** — a paired sidecar's dotted path (e.g. a photo's PhotoInfo JSON `date`), with file mtime as the explicit fallback axis; a sidecar date value may be an ISO string **or an epoch-seconds integer** *(v36)*, which is UTC by definition and satisfies the §12.3.14 boundary rule trivially. The member↔sidecar **pairing convention is producer-declared** *(v36)*, resolved through the same `--origin` ladder as the partition schedule (osxphotos: sidecar `<member>.json` beside `<member>`; proton-mail-export: `<stem>.metadata.json` beside `<stem>.eml`); an export-level metadata file that pairs with no member (a `labels.json`) is **not a member** — it is excluded from bucketing and disclosed in the split's sidecar counts, never allowed to bucket as an undated primary. Members bucket into ONE deterministic zip PER closed month: each month container is a record directly (file-grain months are records; mbox months are promotable members of one container, §12.3.13), plus the rolling current-month container and the standing undated bucket, sidecar-stamped exactly as the mbox flow's outputs are. Two honest divergences from the mbox flow: (1) a generic zip container carries no media-type-level `default_origin` binding to lean on — `application/zip` is universal, and presuming a producer from it would be dishonest — so the producer is named at the verb (`--origin`), and the partition schedule resolves through THAT ladder; (2) closed-month byte-stability additionally depends on the producer preserving both member bytes AND the dates the axis reads — exactly what the `measured` onboarding mode establishes before a byte-stability-claiming declaration ships (the `settled-first-cut` mode sidesteps the dependency entirely by never re-cutting — the gate bullet below).
- **Producer-specific member-grain splitting is instance-owned** *(v38, owner ruling)*. The distribution ships the two generic split flows — `mbox-split` (mailbox members) and `period-split` (file-grain trees) — and prescribes the **stratum shape** they emit; it does not ship a splitter per producer format. A producer whose export demands member-grain surgery inside a bespoke format (a chat exporter's per-conversation HTML, message divs as members) is split **instance-side** — the corpus-local code tier (§12.4.3's trust boundary), composed from the distribution's shared primitives (the date-axis resolution incl. `render_timezone`, the UTC bucketing helper, sidecar stamping, the overlay ladder) — emitting the same stratum shape into the same declared `partition:` schedule. What the spec owns is the contract of the OUTPUT (deterministic per-period containers, disclosure, dedup on the producer's member identity key, the onboarding mode); how a bespoke format's members are carved is the instance's choice about its own artifacts, deliberately not system default.
- **Late arrivals.** A member dated into an already-closed period, arriving in a later export, re-mints that period at next close — a narrow blast radius (one month, not one year), resolved by ordinary mechanical supersession on member identity (§12.11 — the promotable identity, §8.1).
- **Citation policy.** The ledger cites a promoted member or a closed period, never a rolling record's shifting identity by default; where a citation does land on a rolling record, it supersedes mechanically the same way any growing record does — member blake3 to member blake3, continuity-gated (`ath ledger supersede`, `ledger.md` §13.3).
- **The onboarding gate — no declaration without measurement, or an owner ruling in its place** *(v36)*. Two onboarding modes, declared as `partition.onboarding:`:
  - **`measured`** (the default): a producer's `partition:` (and any canonicalization it pairs with) is earned exactly as the mailbox header strip was — a banked two-export diff over the same closed period, recorded in the overlay's comment block, is the prerequisite for declaring closed-period byte-stability at all.
  - **`settled-first-cut`** *(v36, owner-ruled per producer)*: closed periods are cut **once, from the first export that covers them, and never re-cut or reconciled** — no byte-stability claim is made, so no measurement is owed; what is banked in the overlay's comment block, where the measurement numbers would go, is the **ruling** (owner, date, rationale). The mode's discipline is operational and stated: settled strata are never re-ingested; each future export contributes only its newly-closed period(s) and the rolling residue, and whatever a re-export would have said differently about an already-settled period is deliberately out of scope — even a member's later deletion at the provider reconciles nothing. This is the honest mode for a producer whose history is append-only in practice and whose re-export fidelity is unmeasured or unwanted; it claims less than `measured` (first-cut authority rather than reproducibility), never more.

  A producer whose serializer is NOT deterministic across export jobs, and that has no such ruling, onboards **member-dedup-only** — the window-reduction pattern (§12.3.13), with no closed-period claim — until, or unless, a later measurement or ruling earns a mode.
- **JSON-family canonicalization — `strip_fields`.** The mail chrome strip generalizes past mbox headers to any JSON-family export: a producer overlay MAY declare `strip_fields`, a declarative list of dotted key paths (`[]` permitted for array traversal) removed **span-surgically** — the matched key-value span's bytes are deleted in place; the document is NEVER re-parsed, re-ordered, or re-serialized, so every byte the producer did not name stays exactly as delivered, precisely as the header strip leaves body lines untouched (§12.3.13). The same amendment applies verbatim: canonicalize-then-hash where declared, the delivered bytes' blake3 kept as `source_transport` (disclosed as `stripped_fields` + the field count), an already-canonical file passing through untouched, declarative list only — no eval hook, so field surgery stays as reviewable as header surgery.

### 12.4 Attest & derive

The per-format machinery splits into **attestations** (ingest-time byte-facts) and **derivation ops** (resolver-side content extraction); the mechanical body is the `body` op's output, stored only when the normalize pass authors it. A classification is never a frontmatter array and carries no justification field — the `classifications` list is a derived view (§9.1) — and records carry no `tags` field.

#### 12.4.1 The per-format split

The per-format inventory:

| Format | Disposition | Attestations (ingest) | Derivation ops (§6.2) |
|---|---|---|---|
| HTML | work | inline `data:`-asset members (hash, type, `el=` address) | `body` (DOM→markdown, overlay chrome config), `el=` |
| PDF | work | `/Info` fields; **exposable members** for embedded files / portfolio members (`attachment=<N>`) | `body` (page markers), `page=` + introspection ops, `attachment=` |
| EPUB | work | Dublin Core fields; image-member rows | `body` (spine text), `spine=`/`el=` |
| OOXML (docx/xlsx) | work | document facts; **exposable members** (embedded media, OLE objects) | `body` (document text / sheets), `sheet=`/`bbox=` |
| zip/tar (+ zip-shaped types) | manifest | member rows (`path=`), archive facts | `members`, `path=` |
| mbox | manifest | declared-message members (`msg=`, **selective declaration** — below; §12.11 pins the extraction) | `msg=` |
| multi-card VCF | manifest | card members (`card=<N>`, delimiter-pinned; each member `text/vcard`, promotable) | `members`, `card=` |
| ICS calendar | manifest | entry members (`entry=<N>`, `VEVENT`-delimited, promotable) | `members`, `entry=` |
| eml | work | header lift; part members (`part=`) | `body` (reply-text trim), `part=` |
| JSON | work | shape facts (`json_root`, `json_top_count`); `malformed-json` issue | `body` (verbatim passthrough), `turn=`/`att=` where a form mapping declares units |
| audio / video containers | manifest | container/stream facts; **track rows (`stream_id=`) + chapter marks** (§1.2) | `transcribe`, `time_range=`, `frame=`, `stream_id=` (default-member sugar, §6.2) |
| HEIF/HEIC | manifest | image-item members (`item=<id>`); the declared primary (`pitm`) attested | `item=`, image ops via default-member resolution |
| image (single-stream) | work | dimensions/EXIF; a motion photo's nested MP4 as an embedded transport (§1.2) | `bbox=` and the image toolkit |
| markdown / plain | work | — | `body` (passthrough) |
| unknown | work | best-effort facts only | — |

Formats that arrive later slot into existing strategies, not new machinery: 7z/rar/dmg join the zip-manifest strategy; PST/OST joins the mbox precedent; WARC likewise (§1.2).

**Format-specific mechanics, on their owners:**

- **Selective mailbox declaration** (mbox attestation). A mailbox may hold 10⁵ messages, so message members are declared **selectively**: the ingest/re-attest surface accepts named 1-indexed ordinals (`--messages 5,12,90-95`), each recorded as a `message/rfc822` member row at `msg=<N>` (blake3 over the un-stuffed member bytes, plus the message's Date / From / Subject and byte length). Declaration is **cumulative and idempotent**: a re-declaration unions the newly-named ordinals with the already-declared set, an identical re-declaration folds, and a changed hash for a declared ordinal is a **hard error**. An undeclared run attests the mailbox summary only (message count, byte size, date span), no members.
- **The eml reply-text trim** (the `body` op for `message/rfc822`). The derived body is the **reply text only** — the `text/plain` part, else `text/html` reduced to text — with trailing quoted history trimmed from the first confidently-matched marker (an `On … wrote:` attribution directly above a `>`-quoted line, `-----Original Message-----`, an Outlook header block or underscore rule, or a `>`-run to EOF), keeping everything when no marker matches (**prefer false negatives**) and keeping signatures. Part member rows skip the text alternatives the body consumed.
- **HTML addressability** (the `el=` selector). `el=<N>` names an element by its document-order ordinal over **every** element (§6.1.1) — there is no addressable-element predicate. What an address materializes is determined by the element it names (§6.2). What shapers and the resolver share is the ordinal walk itself, which has no configuration to drift; which elements a drafter chooses to *emit a segment for* is a separate, freely-revisable heuristic that changes no address's meaning.
- **Manifest lint conventions.** An empty archive attests a blocking `partial-content` issue. `embed-unreferenced` is relaxed for `manifest`-disposition records (the members ARE the content) and for `message/rfc822` records (parts are message *members*, not body-flow assets — the normalizer links an inline image into the body where it belongs).

#### 12.4.2 One construction path (the constituent model)

`recordbuild.Build` remains the one construction path — `add_blocks` → `open_section`/`add_segment` (which enforce body⟺lossless per segment) — and `recordbuild.finish` emits + grammar-validates it. These are the same ops `compile` replays from a decomposed `manifest.corpus`, so attest / re-attest / decompose / compile / normalize all construct records identically: shapers and agent passes construct the authored layer through it, and a shaped record decomposes then recompiles byte-for-byte. This is the substrate the LLM normalizer works on: it edits the decomposed **constituent files** (per-segment body sidecars + the ops manifest) and recompiles deterministically — never rewriting a monolithic markdown blob — which makes whole classes of structural corruption unrepresentable. (`begin_from_post` seeds the Build for re-attest; `begin` seeds it from a `meta.yaml` for compile.)

#### 12.4.3 Corpus-local shapers

A corpus can specialize the shaping of its *own* content without editing the package — **corpus-local shapers**, the system's one corpus-local code tier. `<corpus_root>/shapers/*.py` load via the `local_code` loader — each file imported by path (`importlib`, not `sys.path`), registered in `sys.modules` before exec, idempotently per `(root, subdir)`, per-file failures logged and skipped. Trust boundary: this executes Python from the corpus root — the corpus owner's own code, which is the point of the tier — but a serving layer never attests, normalizes, or shapes, so merely fronting a corpus never runs it. A module claims records by origin or form id — a producer-declared `corpus-origin-schema` meta or a stamped origin-block id (§7.2) — and builds the authored content zone in place of (or ahead of) the generic mapping-driven shaper and the interpretive agent. A shaper constructs through `recordbuild` and reuses the public address/member helpers (`compute_embed_metadata`, `transforms.html.is_addressable`), so its addresses and member transports line up with the resolver by construction. The record envelope (origin fields) stays the generic path's; only the authored content zone is delegated. Format-specific shapers, atoms, and overlays for private content live in the corpus tree, never in the package.

#### 12.4.4 Perceptual fingerprinting (opt-in)

Fingerprints attest at ingest where the knob resolves on (§7.7). A segment gets a fingerprint row only when `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override)` resolves on — precedence CLI (the ingest/re-attest `--fingerprint` / `--no-fingerprint` override) › origin overlay › mime-schema `fingerprint` knob › off (the default; §7.7). The resolved knob (`true` = the atom's default algorithm, an algorithm name, or a list) becomes concrete per-atom algorithms via `fingerprint.algos_for_atom(atom, knob)`, computed by `fingerprint.text_fingerprints` / `image_fingerprints` (a registry keyed by algorithm). Algorithm selection is schema-only; the CLI flag is on/off. Values land in the derived hash index (§12.9.1), never on records.

#### 12.4.5 Deterministic auto-classification *(retired with the composite namespace — §7.4)*

The `classify_when` engine, `corpus classify`, `corpus reclassify`, and lint's `classification-stale` are gone; deterministic membership is a ledger **harvest rule** over the same fact base (`ledger.md` §10), evaluated ledger-side (`ath ledger harvest`) as a pure function of the corpus's mechanical record facts.

#### 12.4.6 Bulk re-attest (`corpus reattest`)

The attested layer is a deterministic function of (retained artifact + schemas + tooling), and `id = blake3(artifact)` is unchanged by re-derivation — so regenerating it is an in-place `.md` rewrite, and `git diff` over the records surfaces exactly which records a schema / overlay / tooling change affected. **`corpus reattest`** `[target] [--mime/--host/--state] [--dry-run] [--fingerprint]` sweeps the attested layer (§8.3) across the corpus — an unchanged record re-derives byte-for-byte and is not rewritten (idempotent; `--dry-run` reports the set, writing nothing). Re-attest never touches the authored layer (§4.4.7); authored-layer sweeps are **re-normalize** dispatches through the queue (§8.5). Distinct from `corpus compile`, which reassembles a record from a decomposed *manifest* (§12.4.2) rather than from the source *artifact* — different inputs, different jobs. (`records.dumps` serializes a record to canonical text without writing, so reattest can compare against disk.)

Pipeline-state provenance is the `touch[]` chain (§4.2.2): each pass appends a `<pkg>.<module>@<version>` (or `<model-id>`) identifier, so the latest touch's tooling version encodes the spec era of the record's current shape and re-run targeting reads it. There is no separate `conversion_method` / `conversion_tool` field.

#### 12.4.7 Cross-reference resolution

Cross-reference reconciliation is a **read-time derived view, never a stored rewrite**. Segment bodies carry the source's own hyperlinks verbatim and nothing else (§4.3.2.2, §5.1); the mapping from those URLs to corpus ids is computed when asked and never written back. Given a record's stored body, the view scans its segment bodies for **hyperlinks** (`<a href>` → other resources) — *not* same-transport inline media, which is already a member row + segment (§12.4.1) — and for each:

1. Maps the URL → `id` by querying the corpus's URI index (`records.build_uri_index` — every record's origin `uri:` list keyed by identity, §12.3.9).
2. If matched, **reports** the pairing `(href, id)`. The body is not touched.
3. If unmatched, the URL stands as what it is: a reference to something outside the corpus, which the same view will pair automatically once that target is captured.

This is purely mechanical: the view reports links the original content contained and never invents one. Being a view rather than a sweep, it needs no re-run after a batch of captures — the next read simply pairs more of them. (A stored rewrite would be a second copy of a recomputable pairing that can disagree with the first, would damage the lossless body, and would pollute the ledger's citable surface.)

**Reconciliation tooling.** The on-demand counterpart ships as `corpus links` (per-record) and `corpus crawl` (frontier BFS): both extract a record's `<a href>`, resolve relatives against its origin URI, normalize, and look each up in the URI index. A hit means the reference is already captured; a miss is the crawl frontier. `corpus links --show-captured` annotates which is which. Link extraction filters hrefs through `urls.is_crawlable_href`, which keeps client-side routing fragments (`#/route`, `#!/route` — on a hash-routed SPA the fragment *is* the resource identity) while dropping bare anchors (`#section`) and the `javascript:`/`mailto:`/`tel:` schemes.
### 12.5 Normalize

Normalization is the **one authoring pass** (§8.1): it renders a record under its named form contract. It is executed by a **shaper** (deterministic tooling registered per form or manifest strategy) wherever the record's declared form mapping makes the shape mechanical, and by an interpretive agent session (through the queue, §8.5) wherever judgment is required. The agent works over the same derivation ops any reader uses (`corpus body`, the introspection ops, `transcribe`) — nothing it consumes is privileged or unreproducible.

#### 12.5.0 Shapers

A **shaper** is deterministic normalize tooling: it reads the origin overlay's `form:` mapping (§7.2) and the form overlay's decomposition contract (§7.8), consumes derivation ops, and emits the authored content zone through `recordbuild` (§12.4.2) — the form section with its codebook, envelope segments (`turn=` addresses, codebook indexes, timestamps in the form's convention), event segments, attachment markers, structural byte-marks. Its touch is `<pkg>.shape.<form-id>@<v>`; a combined pass appends `+<model-id>` when interpretive work rides the same pass. Shapers live in the package (generic, mapping-driven) or corpus-local under `shapers/` (§12.4.3). A shaper failure on a malformed unit is parse-tolerant per the standing principle — log, mark with an issue, continue.

#### 12.5.1 The interpretive pass

The normalizer authors the record's stored faithful form — faithful-form work only:

- Authors the stored content zone from the derived body and the introspection ops (where a shaper hasn't already written the form), improving formatting fidelity (broken tables, malformed lists) and resolving encoding ambiguity where determinable. A stored rendering rides a named form (§4.1): the interpretive pass authors a content zone only under the record's declared form or one it asserts through §4.4.6's gate. The pass authors **no prose about the record at any scope** — the derived title/description stand or stand empty (§4.2.3). What remains is rendering, extraction, and disclosure.
- **Extracts losslessly wherever extraction is possible** — text printed inside an image as a co-addressed `text/ocr` segment, a rendered table as a `text/data-table`, speech as a transcript. Where the pass cannot render losslessly it leaves the marker alone; the members block remains wholly attested and off-limits either way (§4.3.1.4).
- Places assets as **body-empty markers** at their addresses, typed by the most specific atom overlay that honestly fits (§7.3) — the overlay id is the only answer the record gives to "what is this region."
- Surfaces fidelity problems as `<!--context issue/<id>-->` blocks in the annotations zone — typed codes at addresses, no prose (§4.3.3.2).
- Declares the form span(s) and their contract-declared fields (§4.3.2.1); a record whose content changes shape partway carries more than one span.
- Re-segments where judged appropriate (structural only).

The pass MUST preserve faithfulness (§1.5 principle 3): no information that wasn't in the source. And it may add no information *about* the source: descriptive content has no destination — not a body, not a header, not an annotation. If it cannot be rendered losslessly it is not recorded, and the marker plus the bytes are the honest answer.

#### 12.5.2 Self-verification

Before finalizing the pass, the normalizer confirms:

- The artifact-block opener MIME matches the actual MIME of the stored binary (the opener is authoritative, §12.3.2).
- The `id` (blake3) matches the binary's hash.
- The on-disk record path matches the shard convention.
- `corpus lint` is clean at the pass gate's severity (§8.5) — lint is the executable encoding of the spec's required-field and grammar rules.

Failures here are pipeline bugs; they should fail loudly.

#### 12.5.3 Annotations in practice

A context block stores as `{namespace, id, subtype, fields}` in `post.metadata["_contexts"]`. The bundled namespace is `issue` (§4.3.3); a corpus may add its own under `schema/context/<ns>/`. Context is scarce by design (§4.3.3), and there is deliberately no bundled free-text `note` namespace — that would invite scratchpad flooding.

- **Issue loading and parse tolerance.** `schemas.load_context_schema(corpus_root, "<ns>/<id>")` layers `context/<ns>/<ns>.yaml` → `context/<ns>/<id>.yaml`. `records.iter_issue_blocks` / `append_issue_block` are shims over `_contexts` filtered to the `issue` namespace, so pipeline detectors, `health.unresolved_issues`, the §9.2 view, and lint's issue rules share one path. The reader is parse-tolerant: a legacy `<!--issue <id>-->` still loads (as the `issue` namespace) and upgrades to `<!--context issue/<id>-->` on the next write.
- **Reference lint.** `context-namespace-unknown` flags a block whose namespace has no `context/<ns>` overlay.
- **Decompose/compile conventions.** The manifest keeps a dedicated `issue <id> sev= res= detector=` line for the issue namespace and a generic `context <ns>/<id> k=v…` line for the others (`recordbuild.add_context`). Two conventions keep the working dir hand-editable: record-level manifest facts are authored only on the manifest `record …` line (not duplicated in `meta.yaml`, where an edit would be a silent no-op), and `meta.yaml` renders a multi-line string as a YAML block literal (`|`) so a multi-line value never reads as a truncated stump. An address list in the manifest is bracketed and `|`-separated (`[a|b|…]`), not comma-separated — a single address (e.g. `bbox=x,y,w,h`) already contains commas.

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
- **`fit=<W>x<H>` | `fit=<preset>`** — downscale to fit, aspect-preserving and reduce-only; distinct from `resize=` (forces exact dimensions, may distort or enlarge). The **`llm` preset** bounds the image to a vision model's input budget: long edge ≤ `LLM_MAX_EDGE` (1568 px) and total pixels ≤ `LLM_MAX_PIXELS` (1,150,000), the smaller scale winning. These constants live in `transforms/image.py`, not the contract — §6.2 keeps presets implementation-defined because model limits drift. PDF `dpi=` is the other half of the dial: rasterize at the DPI you want, then `fit=llm` caps the result.
- **`rotate=90|180|270`** and **`auto_orient`** — right a sideways/upside-down phone photo or scan before the agent reads it; `corpus preview --rotate`/`--auto-orient` expose them.
- **`autocontrast`** (1% cutoff) and **`contrast=<factor>`** — pull a faint scan toward readable; `corpus preview --autocontrast` exposes the flag.

The split that keeps `fit` honest: the transforms stay pure (no implicit fitting), and only the agent-facing surface defaults the budget on — `corpus preview` fits to `llm` unless `--full` (a preview *is* going into model context), while a raw `corpus resolve` applies `fit=` only when the URI says so (a consumer embedding a crop in a human-facing deliverable wants native resolution). A typical loop iteration: `corpus preview <id> --page 4 --mark 0.1,0.1,0.6,0.3 -o /tmp/look.png`, read it, adjust, repeat; once right, write the segment at `page=4&bbox=0.1,0.1,0.6,0.3`. **`corpus preview --from-segments <id>`** is the verify half: it reads the record's already-committed bbox segment addresses (grouped by `page=`) and draws them, so the normalizer can confirm each written address frames the span it meant.

One caveat the image guidance makes explicit: unlike a PDF (vector source, re-renderable at higher `dpi=`), an image's resolution is fixed — cropping can't add detail, so for fine print on a low-res capture the levers are crop-tight + `resize=` (interpolated enlargement, not new detail) + `autocontrast`; there is no DPI escape hatch.

#### 12.5.6 Queue mechanics

The queue contract is §8.5; the verbs live in `_cli/{enqueue,drain,finalize,release,await,queue}.py` over the `corpus.queue` library.

**State layout.** External, untracked, under `<root>/queue/` (gitignored alongside `artifacts/`, `capture/`, `cache/`), one marker per record: `<id>.req` (pending request: `requested_at`, `requested_by`), `<id>.claim` (in-flight: `claimed_at`, `claimed_by`), `<id>.result` (last terminal outcome: `completed` | `failed`, with `reason`). A record's queue state is a pure function of which marker exists; markers are JSON written atomically (temp sibling + `os.replace`). The queue never touches `records/` — every verb is read-only on the record (`finalize` reads it to gate; `await` reads the record's derived state as a fallback).

**Atomic claim.** `drain` claims by `os.rename(<id>.req → <id>.claim)` — atomic on POSIX, so when two loop sessions race, exactly one wins (the loser's rename raises and it moves to the next candidate). Requests are claimed FIFO by `requested_at`. An empty queue returns nothing on stdout and exit 1 — the loop's stop signal (per §8.5 this is a non-error empty result; the exit code exists only to break the loop). A stale `.claim` (a dead session) is reclaimable once `claimed_at` is older than `--lease` (default 30 min); reclaim renames it back to `.req`. A duplicate pass from an over-eager reclaim is wasteful, not unsafe (re-normalization is idempotent), so reclaim is best-effort.

**The loop session** (the agent, not the tooling) drives it:

```bash
while id=$(corpus drain --by "$SESSION"); do
    corpus guidance "$id"     # merged overlay normalization.guidance (§12.5.4)
    # ...the agent normalizes $id in-session: faithful rendering, lossless
    #    extraction, form spans, fidelity issues, re-segmentation; recompiles...
    corpus finalize "$id" || corpus release "$id" --failed "<reason>"
done
```

That bare loop is the **scheduled** shape: a tick (cron) drains until dry, then the model sleeps until the next tick — the model polls, waking on a clock even when the queue is empty. `drain --wait` moves the poll off the model: it long-polls the claim primitive in the subprocess and returns the instant a request is claimable, blocking instead of exiting on an empty queue (until `--timeout`, if set; `--interval` sets the poll cadence, default 2 s). The wait holds no claim — `drain` claims atomically only at the moment it succeeds — so an interrupt mid-wait leaks nothing. A **standing** loop runs `corpus drain --wait` under a persistent runner that re-invokes per claim, so the (expensive) model wakes only when there is genuinely work. The contract is unchanged: `--wait` is an ergonomic over the same atomic claim.

**The done gate.** `finalize` refuses (exit 1, claim left intact) unless the pass gate holds (§8.5: formed-where-declared + lint clean, both derived from the record) — a dirty pass is never reported complete. A requester (an external consumer's build agent) does `corpus enqueue <id>` then `corpus await <id>`; `await` polls the external state and resolves by exit code, so it works for a re-normalization of an already-passed record (the record alone can't tell the new pass apart — the queue entry can). Because per-domain knowledge rides in overlays (`corpus guidance`), one generic loop serves every requester; a requester contributes by authoring overlays and enqueuing, never by supplying a normalizer.

**Result lifecycle.** `.req` and `.claim` are transient — each transition is an atomic rename that consumes the prior marker — but a settled pass leaves a `<id>.result` that nothing removes on its own (§8.5: an outcome must outlive the pass so a decoupled requester can await after the loop tick ends). Results are GC'd by age: `corpus queue --prune [--older-than DAYS]` (default 7 d; `0` = now) removes settled results past the grace window and sweeps crash-orphaned `*.tmp.*` scratch, never touching live `.req`/`.claim`. Run it periodically; it is idempotent.

**Operator runbook.** The operating modes and result lifecycle are surfaced via `corpus workflow normalize-loop` — guidance for *running* the tooling, distinct from `corpus guidance <id>` (per-record). Runbooks are markdown shipped in the package (`corpus/workflows/`, loaded via `importlib.resources`); `corpus workflow` lists them, shows a runbook, or narrows to a section. The queue verbs' `--help` cross-reference it. Keeping the runbook in the package means the operating modes are maintained once, in the tooling, not duplicated per corpus.

### 12.6 The curator feedback loop

Pattern detection and where each pattern lands:

**Pattern detection.** Periodic scans for patterns worth encoding: origin / fact frequency (many records share a host or a deterministic fact — a `ytdlp_channel_id`, a URL shape); recurring body shapes within a host; demand flowing down from above (the ledger's needs and coverage gaps, `ledger.md` §7/§9).

**Where each pattern lands.** A recurring *deterministic membership* pattern becomes a ledger **harvest rule** (`ledger.md` §10 — authored in the ledger, evaluated by `ath ledger harvest`). Recurring *body-shape* guidance becomes origin-overlay guidance (per host / subtype, §7.2) or an atom overlay (per form, §7.3). Recurring *link structure* the capture should FOLLOW becomes a `capture.references` declaration (§7.2); recurring link structure the record should RENDER is a form span over it (§4.3.2.1). Domain conventions for authoring claims land in the ledger's `facts/SCHEMA.md` or a concept schema (`ledger.md` §4.4), never in corpus schemas.

**Re-propagation.** Corpus-side overlay changes re-propagate with `corpus reattest` (attested layer, scoped by `--host`/`--mime`; the records diff is the review surface) and re-normalize sweeps (authored layer, §8.5). Ledger-side rule changes re-propagate with `ath ledger harvest` — records are untouched.

### 12.7 Re-run verbs

Every stage is independently re-runnable (§8.3); each re-run appends a `touch[]` entry. Re-processing is how the corpus absorbs improvement: new schemas, a better extractor / transcriber, an upgraded normalization model, or newly-captured artifacts that resolve old cross-references. The CLI mapping:

- **Re-ingest** — automatic on re-encountered bytes matching an existing `id`; folds the capture into origin blocks (§12.3.5), never a new record.
- **`corpus reattest`** — re-run the attestation layer from the retained artifact + current schemas/tooling (§12.4.6, §8.3).
- **Re-normalize** — enqueue the record again (§12.5.6); refreshes the authored layer (shaper or agent) and faithfulness issues, may re-segment.
- **`corpus compile`** — reassemble a record from a decomposed manifest (§12.4.2) — a different input than `reattest`'s artifact.
- **`re-stub`** — the deliberate reset to the attested baseline (§8.4).

**Scoping a sweep.** Deterministic re-derivation makes scoping a records-diff concern rather than a field-level-diff one: re-derive the affected set and the diff *is* the surgical, reviewable change surface. Scope by the most precise selector available — `--host` (a re-captured / re-overlaid origin), `--mime` (an attestation or mime-schema change), `--classification` (a `mime/*` / `origin/*` / `form/*` class), or a derived-state selector (§4.1 — e.g. formless-only).

### 12.8 Maintenance: GC and record removal

Two distinct risk classes, kept as separate verbs (`corpus.maintenance`): a routine, age-gated sweep of regenerable data (`gc`) and a deliberate, ref-checked removal of a tracked record (`rm` / `forget-origin`). Nothing here is normative — the contract is silent on removal; this is CLI hygiene over the storage layout (§12.1).

- **`corpus gc`** prunes, by file mtime, four regenerable categories — never a tracked record, a live queue entry, or an artifact that still has a record: **`cache`** (resolver output; re-warms on the next resolve), **`staging`** (leftover `capture/` debris — sidecars, crawl coordination files, abandoned partials), **`orphans`** (artifacts with no owning record — ingest is the only writer of `artifacts/`, so an orphan is exactly an artifact file whose record is gone: the debris of a `--force` re-capture, a re-stub, or a hand-`rm`), and **`export`** (regenerable bundles). Previews by default (counts + bytes per category); `--yes` deletes. `--older-than DAYS` sets the grace window (default 7; `0` prunes everything now) — generous beyond the brief window in ingest between writing an artifact and its record, so the orphan sweep never races a fresh capture. `--include` restricts the set; `--json` emits the structured result. Idempotent, empty-shard-tidying, safe on a cron tick. The cache sweep **excludes by name** the persistent derived indexes and reference-dataset sidecar indexes — `hashes.db` (§12.9.1), `locations.db` (Part IV §4), `refidx/` (`ledger.md` §6.5) — regenerable in principle but hours-expensive in practice, the opposite economics of the resolver-output cache the sweep exists to prune (Part IV §6.4). Their reclamation is a deliberate deletion, never an age sweep.
- **`corpus rm <id>`** removes a record across its layers — the `.md`, the content-addressed artifact, and now-empty shard dirs — with guards. *Dry-run by default*: without `--yes`/`--force` it prints the plan (paths, sizes, inbound referrers) and deletes nothing. *Ref-checked*: ledger evidence citing the record is the inbound-reference class that matters; checking it is a ledger-side concern — `ath ledger worklist` names the citing claims. *Reproducibility-warned*: the artifact is untracked, so dropping it is undoable only by re-capture — `rm` says so, and `--keep-artifact` drops the `.md` while retaining the bytes. *Floor-checked*: `rm` names any redundancy floor a removal would break (Part IV §6.3). It deliberately does not touch the resolver cache (cache is keyed by functional-URI hash, so there is no clean per-record slice); `gc` reclaims orphaned cache by age. A **containment guard**: removing a container whose members have promoted records strands those records' bytes — `rm` names the promoted members and refuses without `--force`; even when forced, the failure mode is loud (health reports the ids unresolvable). The guard's *resolution* is `corpus retire`, below.
- **Container retirement — extend or die** *(v37, owner ruling)*. Retiring a container that has promoted member records resolves every member in exactly one of two ways, decided by bytes, in one sweep (`corpus retire <container>`): **extend** — some live container carries the byte-identical member (verified blake3 against the member's own id), so the member re-points to it via the §8.1 origin fold (the `dangling_origin_refs` repair above) and survives with a live route, its retired route left in an earlier origin block as history; or **die** — no live container carries the bytes, and the member record is removed WITH the container, in the same sweep. There is deliberately no third state: a member record kept alive on provenance alone — a transferred-origin husk, an acknowledged tombstone, any route to bytes that no longer exist — is prohibited. Dead lineage serves no reader, and it accumulates: every dangling reference is a fixation point for a later pass to misread or confabulate against, so what does not exist any more is removed cleanly rather than memorialized. The sweep is **manifest-first**: the dry-run names every extension (member → live container) and every removal, and discloses the ledger impact — each citing claim of every to-die record — before anything is touched; the operator then either repoints citations first (`ath ledger supersede`, operator-confirmed where continuity diverges) or removes and lets `ath ledger verify` fail loudly after. Both are honest; a silent husk is not.
- **`corpus health`'s `dangling_origin_refs` signal** complements the containment guard: a downstream record's own origin block may name a container that no longer exists — a container a rebundle superseded (§5.2) but whose citing record's origin lineage was never re-pointed. Because origin blocks are append-only history (§5.2), only the record's LATEST block decides whether its live lineage is intact: a dead `corpus://<hash>` there is a `warning` — that citation is genuinely broken, with no route to the bytes through it. A dead hash surviving only in an earlier, superseded block is `info` — honest history of a container that has since been retired, harmless to the record's current lineage. The repair is mechanical, not a hand-edit: `corpus promote` of the same member address under the live container (identity verified first via `corpus resolve`, blake3 against the record's own id) folds a fresh origin block recording the live lineage onto the existing record — the §8.1 fold path, zero mints — leaving the retired block in place as history.
- **`corpus forget-origin <id> <uri>`** handles the many-to-one provenance case: identical bytes accrue multiple origin aliases (§5.2); when one alias is wrong, this drops it without removing the record. Matched by identity key (§12.3.9), so a query-noise spelling still matches. Refuses when it is the record's only origin (that is an `rm`) and is a no-op when the uri isn't among the origins. An origin block whose every uri was forgotten is dropped; the edit appends a `corpus.forget-origin@` touch. It edits the tracked `.md` (git-recoverable), so it acts by default with `--dry-run` to preview — the asymmetry with `rm`'s dry-run default is deliberate (a tracked-text edit vs. irreproducible byte loss).
- **`corpus pack`** *(planned)* — the inverse of promotion: consolidate standalone artifacts into a container (the container captured, ingested, and manifest-attested; the members' blake3s unchanged), then prune the now-redundant standalone files once each member verifies as container-resolvable. No record changes — residence is invisible (§2). Until it lands, a standalone artifact whose blake3 is *also* container-resolvable is simply a redundant copy, not an orphan.
- **`corpus session <capture|list>`** bundles a Claude Code session — its `<id>.jsonl` transcript plus the `<id>/` sidecar tree (sub-agent transcripts, tool-result payloads, workflow state) — into ONE deterministic zip via the reusable writer core (§12.3.11), then ingests it as a zip manifest so every member is a directly-addressed `path=<member>` row (the transcript is never transcribed). It binds the `claude-code-session` producer-export origin (§7.2, uri-less, keyed on a `session_id` field); `--from [user@]host` sources a session from another machine over ssh/rsync. Sessions are personal (a transcript embeds every tool result verbatim) — their records derive private tenancy.
- **`corpus continuity <A> <B>`** proves whether record `A`'s addressable content is preserved in `B`: per `path=<member>` it is byte-identical, *contained* (A is a prefix B extends — the append-only case), *diverged*, or *absent*, and `contains_a` is true iff every unit is preserved. This is the supersession safety check — the *same* test answers "may B replace A?" (keep the more complete version: a re-captured session that grew supersedes its predecessor, while a compacted one must not clobber the fuller copy) and "may a citation of A be rewritten to B?" (`ath ledger supersede`, `ledger.md` §13.3). No synthetic stable id is minted: identity stays the blake3, and continuity carries citations forward only where the content survived.

  **A media pair is compared by SAMPLE SEQUENCE, not by bytes.** Under payload identity (§2, v32) a re-derivation of the same track is id-stable by construction, so within the v32 regime this comparison rarely arises; where it earns its keep is **across framings** — a pre-v32 leaf (muxed single-track bytes) against its payload successor, or any pair whose wrappers differ. There, whole-artifact identity would report *diverged* for a supersession that is in fact exact — and a gate that is always red gets ignored. What survives a reframe is the **sequence of sample sizes in decode order**: re-enveloping (or un-enveloping) moves every sample's file offset and changes no sample's size, while a re-encode, a dropped or reordered sample, or a differently-framed payload all break it. The sequence is read by the corpus's own engine-free sample-table reader — the same reader that now *produces* payload bytes, reading here from each side's own tables — with the four verdicts keeping their meanings, *contained* naming a sequence B extends. This is the v32 migration's own exactness proof: old muxed leaf → new payload leaf verifies as byte-different, sample-identical. **Which tracks pair is decided by containment lineage, never by position**: where B's origin names `corpus://<A>?stream_id=<n>`, B's single track is compared against A's track `n`, because a leaf's own track 0 may be its container's track 1 and pairing by index would silently compare the wrong two. Absent lineage, tracks pair by index and a count mismatch is reported rather than reconciled.
- **`corpus capture --force --replace`** is a supersession ergonomic over `rm`: `--replace` (requires `--force`) snapshots the records holding the URL before the capture and, if the new bytes produced a different record id, retires the prior record(s) for that URL, reclaiming the old artifact bytes. When the bytes are identical, the capture folds into the existing record and nothing is retired.

### 12.9 Resolver surface and cache

A common resolver surface is a CLI that writes the materialized result to disk and prints its absolute path:

```
$ resolve 'corpus://<hash>?<params>'
/abs/path/to/cache/<shard>/<urihash>.<ext>
```

Conventional flags: `--regenerate` to bypass cache, `--json` to print a sidecar with derivation metadata. Library and HTTP-service surfaces are equally valid (§6.3).

The cache layout mirrors the sharding convention — `cache/<urihash[:2]>/<urihash>.<ext>`, where `urihash = hash(<canonical-uri>)`, with a `<name>.json` sidecar for JSON-valued ops so extensions can't collide. Cache invalidation is by deletion; eviction policy is implementation-defined (§6.4).

**The member index.** The route from a bare blake3 to its container (§2) is a derived map — `member transport hash → (container id, member address)` — built by walking every record's members block, exactly as the URI index is built (§12.15 applies: rebuilt-on-start; persistence is a deferred perf optimization). Byte lookup falls back through it when no standalone file exists (Part IV §2's resolution order), recursing through nested containers, and the resolver cache absorbs hot paths — a member deep inside a solid compressed stream (a tgz) costs one streaming decompress on first touch, a media track one table-driven payload stream (§2), and both are cache-warm after. The promoted record's origin `uri:` (its containment lineage, §8.1) is **history, never consulted for byte lookup** — residence must stay free to change out from under it.

This index is why the members block is **stored** rather than derived on the fly. Every row in it is mechanically recomputable from the artifact, so storing it looks redundant — but the index is built by one pass over `records/`, and rebuilding it from artifacts instead would mean opening and parsing **every** artifact on start, including multi-megabyte HTML and containers with tens of thousands of members. The roster is stored precisely so that the cross-record questions — *which record holds this hash, at what address, how big* — cost no artifact reads at all. That is also the whole justification for the row's four-key shape (§4.3.1.4): a field that does not serve a cross-record question is not paying for the space it occupies in a file the indexer reads end to end.

#### 12.9.1 The derived hash index

The query layer over every recipe value (§2, §7.9) — record-resident and index-only alike; this section is the reference shape. The index is **deployment state in the resolver-cache mold** — untracked, never authoritative — and its natural storage is a database, not markdown: the reference implementation is a single SQLite file, `cache/hashes.db`, though any store honoring the row shape conforms.

- **Row shape**: `(record_id, recipe, algo, value, param)` — `param` distinguishes multi-value recipes (the prefix ladder's rung length; a fingerprint's segment address) and is empty otherwise. `<algo>:<hex>` reassembles per §7.6, version tag included for procedure-versioned rows.
- **Hash while the bytes are in hand.** Every write point is a moment the bytes are already local and streaming: ingest computes the declared recipes on the staged file (§8.1); `corpus reattest` refreshes rows as it streams; the **backfill pass** (`corpus hash-index backfill`) walks records whose rows are missing, resolving bytes locally or through containment (§12.9). Against a **remote store** (Part IV), nothing pulls bytes *solely* to hash: backfill takes an explicit `--hydrate` to authorize remote reads, reports what it skipped otherwise, and any pass that hydrates bytes for its own reasons opportunistically fills the record's missing rows while they're local. The steady state is an index that fills as a side effect of work the corpus was doing anyway.
- **Record sync.** Record-resident values (the `hash:` field, ingest-written and flushed alike) are mirrored into the index whenever a record is written or (re)scanned — the index is a superset view, so a consumer queries one surface. A wiped index rebuilds its record-resident rows from `records/` alone (one cheap pass, no bytes); only never-flushed index-only rows need bytes to recompute — which is the flush calculus below.
- **The flush** (`corpus hash flush <ids|--all> [--recipes …]`) is the **one deliberate write** of index-only values into a record's `hash:` field, each under its class tag (§7.6) — identity-class values only; similarity values never flush (§7.9). Never automatic — no pass flushes as a side effect — so record churn is always an operator's explicit choice. Its economics: flushed values survive index loss *in git, with the record*, and are the insurance to buy **before** evicting local bytes to a remote store or wiping `cache/`.
- **Rebuild** = the record-sync pass plus backfill for whatever was never flushed. Deleting the file is always safe in the sense that nothing normative depends on it (§2) — what it costs is recomputing unflushed rows when their bytes are next in hand. Resolution of bytes (§2) explicitly never routes through this index — that is the members roster's job, and residence-freedom depends on it staying there.
- **Consumers**: the same-document health signals — the duplicate-capture join on `html-stampfree@1` and the grown-export screen on the prefix ladder — both index-joined, zero artifact reads in the steady state. External checksum verification (`sha256` interop) and any future similarity search (§7.7 fingerprints) read the same rows.
- **Not a general side-store.** The index holds recipe-value rows only. The URI index and member index remain rebuilt-on-start from records (§12.15); a value derivable from *records* stays derivable, and this index exists precisely for values whose recomputation needs *bytes* — the distinction keeps "what must a fresh clone recompute" a one-line answer: nothing tracked, everything under `cache/`.

#### 12.9.2 The location index

**Moved to Part IV** ([`custody.md`](custody.md) §4): the attached-location route's derived map, its persistence rationale, staleness pins, and row provenance. This stub keeps the section number so existing citations resolve.

### 12.10 Export output layout

A common export layout writes one directory per exported record:

```
export/<record_id>/
├── <name>.md
├── <name>_001.<ext>
├── <name>_002.<ext>
└── ...
```

with the §10 surface-materialization contract mapping each record's addressed surface to a sequentially numbered local file.

### 12.11 Common address schemes (illustrative)

Media-type schemas declare their own address grammar (§4.3.2). Schemes that have proven useful in practice, as examples only:

| Axis | Example | Typical source |
|---|---|---|
| element | `el=<N>` · `el=[<a>-<b>]` (sibling range) · list | marked-up / HTML text (a 1-based document-order ordinal over every element, §6.1.1; output determined by the element — an `<img>` renders to an image, a `<video>`/`<audio>` or `<a href="data:…">` attachment carrier materializes to its raw bytes, a text element to its region) |
| page | `page=<N>` | paginated documents |
| block | `block=<N>` | block-structured documents without fixed pages |
| sheet | `sheet=<name>` (+ `bbox=<A1-range>`) | spreadsheets |
| row | `row=<N>` (+ `col=<name-or-index>`) | delimiter-separated text tables (CSV/TSV; 1-indexed over data rows, header excluded; RFC 4180-aware raw-row extraction with the dialect pinned by the mime schema, so row bytes are deterministic; `col=` narrows to one field by header name or 1-indexed position, output `text`; engine-pinned — `csv-row-col@1` — like any derivation op, §6.4) |
| time | `time=<tc>` / `time_range=<s>-<e>[,…]` | audio / video (a comma-delimited ordered list of ranges materializes as concatenated cuts in listed order — the muxing contract, §6.2; on a container the cut is of the composition via per-kind default members) |
| frame | `frame=<tc>` | video stills |
| region | `bbox=<x>,<y>,<w>,<h>` | image crops (relative floats) |
| turn | `turn=<N>` | turn-structured transcripts / sessions (1-indexed unit in the record's declared unit array, located by the origin overlay's form mapping — §7.2; `turn=<N>&att=<M>` addresses unit N's M-th declared attachment, materialized by lineage-chained resolution, §6.2) |
| stream | `stream_id=<id>` | multi-stream media (a media container's track members — extraction semantics pinned by the mime schema so member bytes are deterministic and promotable, §8.1/§11; also composes onto another axis; bare ops route via default-member resolution, §6.2) |
| card | `card=<N>` | multi-card vCard files (1-indexed; `BEGIN:VCARD`/`END:VCARD` delimiter-pinned extraction, so member bytes are deterministic and promotable — the mbox precedent) |
| property | `prop=<N>` | a vCard's own properties (1-indexed over the card's property list, output `text`; decoded — QUOTED-PRINTABLE hex-escape + RFC 6350 §3.4 backslash-unescape — mirroring the `contact-card` form's `prop=N` segment addressing exactly, §7.8, so a citation's `?prop=N` anchor resolves to the same datum the formed record renders; a binary-encoded property — PHOTO/LOGO/SOUND/KEY, `ENCODING=B`/`BASE64` — has no decoded text, same as the segment's header-only rendering) |
| entry | `entry=<N>` | calendar files (ICS; 1-indexed `VEVENT`-delimited entries, promotable likewise) |
| item | `item=<id>` | HEIF/HEIC image items (container-declared item ids; the `pitm` primary is the default-member target, §6.2) |
| attachment | `attachment=<N>` | a `work` transport's exposable members (PDF embedded files / portfolio members; OOXML embedded objects — §7.1) |
| path | `path=<relpath>` | archive members (kept-whole archives: zip, tar/tgz) |
| message | `msg=<N>` | mailbox archives (mbox; 1-indexed). Extraction semantics — the `From ` delimiter convention and `>From ` un-stuffing variant — are pinned by the mime schema, so member bytes are deterministic and promotable (§8.1) |
| part | `part=<N>` | MIME message parts (email; 1-indexed addressable parts — every leaf part plus every nested `message/rfc822` as a whole, in depth-first pre-order — as CTE-decoded payload bytes; promotable per §8.1) |

Addresses compose with `&` (e.g. `page=<N>&bbox=<x>,<y>,<w>,<h>`); a single address or an ordered list (for non-contiguous spans, in reading order); query-reserved characters in a value are percent-encoded.

### 12.12 The concept knowledge base *(retired)*

Retired with the `concept` namespace (§4.3.3.4). External-authority identity is a ledger concern: a concept claims its `wikidata:Q…` id once, citing a mirrored reference dataset — where the local-mirror idea itself returns, as the `ref://` resolver (`ledger.md` §6.5).

### 12.13 Token counting

The `token_counts` view (§9.6) is computed with: text counted by a local BPE tokenizer approximating the target model's (an `o200k`-class vocabulary), lazy-imported behind an optional extra with a chars/4 heuristic fallback so the base library carries no tokenizer dependency; and an image-token estimate of `≈ min(width·height, 1,150,000 px) / 750` per image, from declared dimensions (`0` when absent). The tokenizer fetches its vocabulary on first use and caches it — warm the cache once for offline operation. Like every §9 view, the counts are never persisted to records; a search index may cache them per record (alongside size and segment count) for filtering and statistics.

### 12.14 Serving a corpus

No server is part of the corpus contract — a corpus is a directory of records, schemas, and caches, fully usable offline through the library and CLI (§1.5 principle 9). A serving layer may front the corpus — records, derived views (§9), artifact bytes, resolver output (§6) — over HTTP for browsing or search. It should remain a thin read surface that serializes what the library already produces, adding no parsing, derivation, or resolution logic of its own, and it never attests, normalizes, or executes corpus-local code. One sharp edge: a functional-URI value passed through a URL query string must be fully percent-encoded.

### 12.15 Open implementation questions

Flagged for follow-up; not all are blockers.

- **Sharding crossover.** When does single-level hex-prefix sharding stop being adequate — at what record count do we move to two-level (`a7/f3/…`)? Likely a tooling-driven flag declared in `corpus.toml`, with tooling rebalancing on change.
- **URI index persistence.** The URI → `id` lookup (`records.build_uri_index`) is rebuilt-on-start from the records — the settled default (an in-memory query engine, not a data store). A persistent side-file is a deferred perf optimization, not an open design question. (The hash index (§12.9.1) establishes the pattern such a side-file would follow — untracked, regenerable, never authoritative — but records-derived indexes stay rebuilt-on-start until measurement says otherwise.)
- **Schema validation.** `corpus lint` validates *records*, not schemas; a `validate-schemas` command (`extended_fields` well-formed, `semantic_type` within the closed seven, no reserved `provenance` declared as a field, `capture.*` sections parseable) is still missing.

### 12.16–12.37 Migration history *(filed away)*

The numbered migration narratives — one entry per amendment or implementation increment through the closed ATH-CORPUS line — are **history, not law**: they live in git (the deleted `spec/corpus-history.md`, recoverable at its deletion commit; the `pre-reforge` tag for older material), indexed by [`CHANGELOG.md`](CHANGELOG.md). A cross-reference of the form `history §12.x` resolves there.

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **Corpus** | A content-addressed archive of captured artifacts. |
| **Record** | A markdown file with YAML frontmatter representing a single artifact. |
| **Artifact** | A captured file. Identified by the blake3 hash of its bytes. |
| **Transport** | The media-type-shaped container of a file. Also the name for the members-block row's bytes-level hash field (`transport:`) and the origin-block `source_transport`. |
| **Content** | What a transport carries. Decomposes into segments. |
| **Segment** | An addressable unit of content. Carries an address (optional — absence names the whole transport, §4.3.2.2) and at most one atomic classification; the structural and placement kinds carry no atom at all. |
| **Atom** | One of four **content** types: `text`, `image`, `audio`, `video`. A structural segment carries none — it is a mark, not content. |
| **Record body** | The markdown content below the frontmatter. Organized into three zones. |
| **Segment body** | The markdown prose inside a single `text`-atom segment block (or a structural mark's text). |
| **Zone** | One of three partitions of the record body: metadata, content, annotations. |
| **Artifact block** | `<!--artifact <mime-type>-->` — exactly one per record. Opener arg is the authoritative media-type declaration. |
| **Origin block** | `<!--origin [<id>[/<subtype>]]-->` — one or more per record. Carries `uri:` and `snapshot:`. |
| **Members block** | `<!--members-->` — the record's unabridged roster of embedded assets, one row per member, closed to `address` / `media_type` / `transport` / `bytes`. Wholly attested; deduplicated by `transport:`. |
| **Section block** | `<!--section <form-id>-->` — a **form span**: a positional span of the content zone declaring a named structural form, carrying only the fields that form declares. Depth one, never overlapping; a record may carry several. |
| **Derived envelope** | A form section's envelope — the min–max span of its children's addresses — computed, never stored (§4.3.2.1). Where one form governs everything, a single span's derived envelope simply covers the whole content zone. |
| **Segment block** | `<!--segment <atom>-->` — the body's content atom: a lossless rendering of its addressed region, or a body-empty **marker** saying only where the bytes are and what type they are. A marker carries no narration. |
| **Structural segment** | `<!--segment structural-->` — a **byte-mark**: the source's own declared boundary (heading, outline entry, chapter, topic) at an address, with `level:` and the mark's own text in its **body**. An empty body is an unlabeled boundary. The TOC is a derived rendering over these marks. |
| **Placement** | `<!--segment placement-->` — a body-empty segment recording that a **member** sits at this position and nothing more. The member is named by the shared address, its record by the roster row's blake3 — derived, never stored. Placing a member obliges promoting it (§4.3.2.4, §8.1). |
| **Normalization pressure** | Derived demand on a promoted member's record: the number of records placing it. A second source on the queue's one mechanism, beside the ledger's citation demand; ranks the queue, gates nothing (§8.5). |
| **Context block** | `<!--context issue/<id>[/<subtype>]-->` — an annotations-zone **capture-fidelity** observation, a typed code with no prose; record- or segment-scope (via `address:`). `issue` is the only namespace. |
| **Namespace** | One of `mime`, `origin`, `form`, `atom`, `context`. Each is a schema axis or umbrella with its own block-keyword role. |
| **Form** | The fourth classification axis: a **rendering contract** — an expectation for how a set of bytes is faithfully represented in a markdown shape (`conversation`, `statement`, `receipt`). Declared by a `form/` overlay; bound on a section opener; names shapes, never subjects; a goal for the right artifacts, never a default (§7.8). |
| **Formless (the zeroth form)** | The identity contract: the faithful representation of the bytes is the bytes, delivered through derivation ops. Valid indefinitely; prescribes nothing about what the artifact is. |
| **Proxy** | A record's universal role from birth (§4.1): the attested, consumable stand-in for its artifact — complete without any stored rendering. |
| **Terminal contract** | A member of the form domain prescribing the **absence** of a stored rendering — `form/passthrough` (the identity contract, named) or `form/manifest` (the members are the content). Governs a record exactly as a rendering contract does; a terminal record never gates by default and is reported `terminal`, not `proxy` (§7.8). |
| **`rendered`** | The grandfathered state: a record carrying a stored rendering under no named form contract, tolerated pending its next pass through normalize — never a steady-state target, and never retroactively condemned by a later class-grain form declaration (§7.8's governing-contract precedence guard). |
| **Formed** | Derived state predicate: a form section governs the record's stored content zone — a stored rendering under a named contract (§4.1). |
| **Derived editorial fields** | A record's display title/description, computed — never stored — from role-marked fields by precedence **artifact → origin** (latest block wins within a layer; an all-empty chain resolves to an honest empty value; §4.2.3). |
| **Role-marked field** | An `extended_fields` declaration carrying `role: title` or `role: description` — an editorial candidate for the derived title/description (§4.2.3). Declared only on mime schemas and origin overlays; a form contract marks no editorial role. |
| **Codebook** | A list field on a form section's header that envelope segment fields index into (e.g. `participants:` ↔ `participant: 2`) — derivable from the span's own bytes, entry grammar `<display> <durable-id>`. |
| **Provenance** | On a context block (§4.4.6): `provenance: auto` = engine-stamped (a detector or overlay-declared emission), stripped and regenerated on re-run; absent or `asserted` = human/normalizer, never auto-touched. |
| **Self-contained** | The universal container principle: every transport produces a single record (lifting nested-stream metadata when present). A raw archive is attested as a members-block roster of its contents. |
| **Container / member** | A container is an artifact whose content is other transports (an archive); a member is one such contained transport, rostered as a content-addressed row of the container record's members block (§4.3.1.4). |
| **Member / Unit** | A member is a transport with its own MIME and standalone byte identity (a manifest or exposable member row, promotable). A unit is content *within* one transport, reached by unit ops (`turn=`) under a form mapping — never a member. |
| **Promotion** | Minting a first-class record for a container member without copying its bytes: the promoted `id` is the member's blake3, resolved by streaming through the container (§2, §8.1). |
| **Disposition** | A mime schema's declared container-vs-transport judgment (§7.1, §1.2): `manifest` — the members ARE the content — or `work` — one transport whose internals surface as exposable members. Declared (origin-overridable), auditable, never sniffed per record. |
| **Exposable member** | An internal member file of a `work`-disposition transport, rostered as addressable and promotable without being the content (a PDF's embedded file at `attachment=<N>`, a docx's pasted photo) — versus a **manifest member**, where the roster IS the content. |
| **Attestation** | Ingest-stamped byte-facts: artifact fields, the members block (manifest or exposable), structural byte-marks, sidecar lift. Deterministic; stripped + regenerated by re-attest. |
| **Derivation op** | A resolver operation deriving mechanical content from the artifact (`body`, `members`, `transcribe`, `turn=`) — on-demand, cacheable, pure or version-labeled (§6.4). |
| **Shaper** | Deterministic normalize tooling that authors a record's stored form from a declared form mapping — the mechanical half of the one authoring pass. |
| **Lineage-chained resolution** | Read-time materialization of content a record's bytes declare but do not contain, through the record's containment-lineage parent (§6.2). Derived, never stored. |
| **Default-member resolution** | Read-side sugar (§6.2): a bare op routes to a container's sole member of the required kind, or its declared primary (`pitm`); ambiguity fails loudly. Citation-safe by content-addressing; attested member rows keep explicit addresses. |
| **Member re-chaining** | §6.2: a `path=`-extracted member re-detects its own mime and, when a further transform follows, re-enters the working-kind table for it (a PDF member takes `page=`/`text`); a terminal `path=` never promotes to a full working-kind object (no silent re-encode) — it only decodes an already-textual member (JSON/text) to text; an unrecognized member stays raw `bytes`. |
| **Muxing contract** | §6.2's normative behavior for media cuts and conversions: composition cuts via per-kind default members (subtitles opt-in), composable stream selection (`stream_id=0,2`), ordered multi-cuts (`time_range=a-b,c-d` → concatenation), precise-by-default cut semantics (`cut=copy` the disclosed keyframe-snapped path), `format=` conversion (encoding only, atom-compatible, implementation-defined token set), pinned order select→cut→convert→size. Behavior normative, mechanics resolver-owned; results are version-labeled ephemeral renderings, never new artifacts. |
| **Capture, Ingest, Normalize** | Pipeline stages (§8.1). |
| **Stub** | *(historical)* The former name for a just-attested record — now simply the record at its attested baseline, the artifact's proxy (§4.1). Survives in the `re-stub` verb name. |
| **Touch** | A single processing pass. Recorded in `touch[]`. |
| **Touch chain** | The ordered list `touch[0..N]`. Records current-shape provenance; reset by re-stub (§8.4). |
| **Re-stub** | A deliberate reset that discards body and accumulated metadata, leaving only byte-intrinsic state and the touch chain. See §8.4. |
| **Resolver** | The corpus-provided mechanism that materializes a functional URI to a deterministic result. |
| **Functional URI** | A `corpus://<hash>?<params>` URI naming a derived view. |
| **Derived view** | A computed aggregate over body blocks / semantic-tagged fields. |
| **Semantic type** | One of seven closed-vocabulary tags on schema-declared fields. |
| **Whole-address admissibility** | A mime schema's `whole_address` declaration (§7.1) — `admissible`, `forbidden`, or `single_unit_only` — stating whether an address-less segment (naming the whole transport) is legal for the medium. |
| **Cut strategy** | A mime schema's declared `cut_strategy` default (origin-overridable) for deriving a time-addressed stream's segment boundaries. The promoted leaf carries a **`cutting:`** stamp naming the versioned strategy, its parameters, and the resulting cut count — the self-check a disagreeing consumer compares against rather than re-deriving (§7.1). |
| **`framing:` stamp** | *(retired, v32)* The attestation that admitted a muxing engine into the identity path. Payload identity (§2) removed the engine, and with it the stamp's subject; surviving stamps on pre-v32 leaves are honest history (§7.1). |
| **Payload identity** | The v32 identity principle (§2): a member's identity bytes are the fully-unwrapped payload (raw elementary stream, decompressed content); wrappers are residence forms. Makes `corpus://<leaf> ≡ corpus://<container>?<address>` a verifiable identity equation and keeps every engine out of the identity path. |
| **Transport hash** | The bytes-level hash of a file or member. Encoded as `<algo>:<hex>`; carried by members-block `transport` rows. |
| **Hash field** | `hash:` — frontmatter home for auxiliary identity hashes. Tag classifies each value (§7.6): bare algorithm id = byte-stable digest; `<procedure>@<version>` = canonicalized identity, flush-only. |
| **Canonical hash** | A procedure-versioned canonicalized identity, `<procedure>@<version>:<hex>`, resident in the derived hash index and flushable into `hash:` (§4.2.1, §7.9). Content-canonical remains barred. |
| **Perceptual hash** | An atom-canonical content fingerprint — procedure-versioned, similarity-class, resident in the derived hash index only (§7.7, §7.9). |

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

1. **MIME type** (`mime` namespace, §7.1) — the artifact's media type (`text/html`, `application/pdf`, `application/epub+zip`, `video/mp4`, …) selects the attestations, the derivation ops, the addressing scheme, and the hash recipes. A "research paper" is just an `application/pdf` artifact; a "blog post" is `text/html`.
2. **Form** (`form` namespace, §7.8) — where a rendering contract fits the content (a conversation, a statement, a document), a form span declares it — shape only, never subject; formless (the zeroth form) where none does or none is yet adopted.
3. **Ledger assertion** (`ledger.md`) — *what kind of thing* an artifact documents, and any domain signal worth recording (e.g. a `peer-reviewed` / `preprint` credibility signal), is asserted as typed claims whose evidence cites the record — minted mechanically by harvest rules where membership is deterministic (`ledger.md` §10). This replaces per-document enum metadata fields entirely.
4. **Origin** (`origin` namespace, §7.2) — capture provenance: source URL(s), capture timestamp, per-host capture recipe. "Where it came from" lives here.

Backlog growth, grooming, and prioritization of what to capture are **curatorial** concerns owned by the layers above the corpus — the ledger's needs and coverage gaps generate ingestion demand (`ledger.md` §7, §9) — not corpus-pipeline stages.
