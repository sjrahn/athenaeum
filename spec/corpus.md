---
spec_id: ATH-CORPUS
title: "Corpus Specification"
version: 3.8
status: current
license: "CC BY-SA 4.0"
date_created: 2026-05-24
date_modified: 2026-07-28
---

# Corpus Specification

A **corpus** is the foundation layer of the Athenaeum system: a content-addressed archive of captured artifacts, represented as markdown records. This document is its complete specification, in two parts. **Part I (§1–§11)** is the normative data contract — every record in every corpus conforms to it, and tooling across the system cites its section numbers. **Part II (§12)** is the implementation guide: non-normative notes on how the reference pipeline produces conforming records. Two appendices follow — the glossary (Appendix A) and a non-normative content-type taxonomy (Appendix B).

The corpus sits beneath the ledger layer, which interprets it through `corpus://` functional URIs — see [`athenaeum.md`](athenaeum.md) for the system architecture, [`ledger.md`](ledger.md) for the knowledge layer, and [`codex.md`](codex.md) for the codex contract.

**Version 2.0** removed the corpus's interpretive classification system — the `composite` umbrella, the classify block, section-scope composites, the `concept` context namespace, and the interpretive `reference` emission path — in favor of the ledger layer: a record describes its bytes, retrieval, and faithful form; what its content *means* is asserted one layer up, with evidence pointing back down. Removed sections are **tombstoned in place** (numbering preserved, successor named) rather than renumbered, so 1.0-era citations of this spec still land somewhere true.

**Version 2.1** — the **containment amendment** — decoupled records from standalone artifact files. Every transport is now self-contained (the `decomposable` disposition and the `artifact_kind` declaration retire): a raw archive drafts as an embed manifest, and any declared member may be **promoted** to a first-class record whose bytes remain inside the container, resolved by streaming (§2, §1.2, §8.1). No existing record changes shape (§12.17).

**Version 3.0** — the **derivation revision** — completes the movement 2.1 began: a record stores only what is **authored** (the normalize pass's faithful form) or **attested** (ingest-stamped byte-facts), and everything mechanical is **derived, addressable, and reproducible**. The `draft` stage retires: its fact-stamping becomes ingest **attestation**, its content extraction becomes resolver **derivation ops** (§6.2), and its body-writing becomes the normalize pass's job — mechanical (a *shaper*) where a declared form mapping makes the shape deterministic, interpretive where it does not. The stored table of contents retires with it: TOC grouping becomes a derived rendering over **structural segments** (byte-marks only, §4.3.2.3), and the freed **section block** becomes the surface of the new **form axis** (§4.4.1, §7.8) — record- and span-scope structural form, the fourth classification axis. Embeds close to *"this asset is part of this record's capture"* (§4.3.1.4); referenced-but-not-contained content materializes through lineage-chained resolution (§6.2), derived and never stored. Media containers are attested as track manifests (§1.2). Removed and reshaped sections are tombstoned in place exactly as 2.0 did; the 2.0 tombstones themselves are untouched — the form axis is *not* the classify block returning (§7.8).

**Version 3.1** — the **layers amendment** — retires the last stored lifecycle field: `status` leaves the frontmatter, and a record's state becomes **derived from what the record demonstrably carries** (§4.1) — every record is **attested** at birth (the artifact's *proxy*: complete and consumable through the derivation ops), a record is **formed** where a named form contract governs a stored rendering, and **authored** where the editorial vouch is written. `normalized` dissolves into *formed + authored*; `stub` dissolves into the plain record. Two ideas carry the amendment: **formless is the zeroth form** — the identity contract ("the faithful representation of these bytes is the bytes"), valid indefinitely, prescribing nothing, with deliberately no catch-all shape and no default — and **forms are a goal, not a rarity** (§7.8, amending 3.0's "rare by design"): the form namespace is the corpus's *rendering-contract library*, adopted lazily where benefit demands, so `origin` says where bytes came from, `mime` says what container they arrived in, and `form` says what markdown shape renders them faithfully. Citability re-keys accordingly — ledger verification checks evidence against **verifiable surfaces** (stored renderings, engine-pinned derived content, authored prose) rather than against a status flag (`ledger.md` §6.3, §13.2) — and the normalization queue becomes **standing demand**, never a backlog (§8.5). Migration: §12.19.

**Version 3.2** — the **derived-editorial amendment** — retires the stored interpretive editorial fields: a record's display `title` and `description` become **derived, never stored**, resolved from **role-marked schema fields** (`role: title` / `role: description` on `extended_fields` declarations, §4.2.3) by the precedence **artifact → origin → form** — each later layer overriding the earlier, latest block winning within a layer — so every record carries an honest mechanical title/description from birth, no LLM pass required, and the frontmatter pair survives only as an **optional deliberate override**, preferred absent (§4.2.1). The interpretive editorial prose relocates onto the **form section header** — the vouch's new home — and with it the **authored state dissolves into the form layer** (§4.1): a formless record derives exactly what its marked fields say; genuinely interpretive prose requires a form or belongs to the ledger (the 2.0 line about meaning, one layer up). §7.8's field rule softens accordingly: *mechanically derivable* becomes a preference, not a requirement — a non-derivable field is interpretive by design, disclosed by the touch chain. (*Terminology:* the **authored layer** as an ownership name — the half of the record the normalize pass writes, §4.4.7 — is unchanged; what retires is authored as a record **state** keyed on frontmatter fields.) Migration: §12.21.

**Version 3.3** — the **terminal-forms amendment** — makes §7.8's destiny split machine-readable: *formless-permanently* becomes a declarable judgment, no longer prose. Two **terminal contracts** join the form library (§7.8): **`form/passthrough`** — the identity contract named and assertable: the artifact is its own terminal rendering, better than any markdown shape on both fidelity and token economy, so the contract prescribes the **absence** of a stored rendering (content zone = structural byte-marks only; lint inverts — a stored rendering under a terminal contract is the violation) — and **`form/manifest`** — the container specialization: the members are the content, conformance binds the attested member embeds, and the editorial header vouches the container. A terminal contract is **not** the catch-all §7.8 forbids: it prescribes no shape — it records the earned judgment that no shape exists, exactly as a named form records the judgment that one does. Declaration rides the overlay grain (mime `form:` default, origin override — the `disposition:` pattern), with one derivation: a **`disposition: manifest` record with no rendering contract declared stands under `form/manifest`** — the disposition already IS the terminal judgment, and the amendment refuses to make owners state it twice; per-record assertion (§4.4.6) covers exceptions. Consequences: derived state gains a fourth reported value — **terminal** — beside formed / rendered / proxy (§4.1), so *proxy* narrows to mean genuinely unassessed-or-awaiting; a terminal record **never gates and never enters the queue by default** — the pass gate is trivially satisfied, an enqueued terminal record drains to a **no-op finalize** unless the request explicitly asks for re-evaluation, and the licensed residue that 3.3 named — the whole-record opener's editorial vouch and the per-asset descriptions — is retired outright in 3.5, so a terminal record has no describe-pass work at all (§8.5); and the ledger's evidence doctrine sharpens — a terminal record is a **complete source**, its derived surfaces permanent and full-strength, and the normalize-demand signal keys to formless-*for-now* alone (`ledger.md` §6.3, v1.3). Migration: §12.23.

**Version 3.4** — the **roster amendment** — separates a record's asset **index** from its asset **narration**, which the per-asset embed block had been carrying together. The N `<!--embed-->` blocks collapse into ONE `<!--members-->` block (§4.3.1.4) whose rows are a **closed four-key shape** — `address`, `media_type`, `transport`, `bytes` — and nothing else. The block becomes **wholly attested**: re-derived from the artifact on every attestation, never touched by a normalizer, so the roster is once again idempotently derivable from the bytes it claims to describe. Every descriptive per-member fact (pixel dimensions, verbatim `alt`, member filenames, an email member's `from`/`subject`/`date`, a vCard's display name) moves to the **`members` derivation** (§6.2), which is where a normalize pass now looks to see what an artifact carries. The admission rule is stated normatively so the next candidate field is decided rather than debated: a row field must answer a question asked **across records** without opening an artifact **and** be an identity-or-accounting fact rather than a reading of content — which is also why the roster stays *stored* (§12.15: the member index is one pass over `records/`, and deriving it instead would mean parsing every artifact on start). The per-asset `description:` field is retired outright: the old blocks are deleted, the members block replaces them, and prose stored in the retired field is **dropped** rather than migrated — an abolished field has no successor, and no obligation falls on a member as a result. Where a record narrates an asset it does so on the block that places it (§4.3.2.2) or on the member's own record once promoted (§8.1), as ordinary authoring in a layer re-attestation does not touch. Independently, **segment bodies stop carrying intra-corpus links entirely** (§4.3.2.2, §5.1): both the `corpus://` functional-URI and raw-blake3 wikilink/embed forms retire — specified, linted, rendered by nothing, used by no record — because cross-artifact connection is already expressed by the source's own URLs and reconciled at read time (§12.4.7), and nothing within one transport ever needed a link at all. A promoted record's origin lineage `uri:` is untouched: it is capture history, never a lookup route. Migration: §12.26.

**Version 3.5** — the **faithfulness amendment** — states the rule the previous four were converging on and applies it without exception: **a record asserts nothing about itself.** A record is the faithful representation of its bytes; where faithfulness cannot be achieved, the record says *where the bytes are* and stops. Summary is a query, and the query layer is the ledger (`ledger.md`). Six retirements follow from the one rule. **`description:` retires everywhere** — on segments, on sections, on frontmatter — and with it the interpretive rung of the derived-editorial ladder: the corpus may *report* a source's self-description (an HTML `meta`, a PDF `/Subject`, a producer sidecar — those are bytes) and may never *author* one (§4.2.3, §4.3.2.1, §4.3.2.2). **The universal section-header fields retire**: a section opener declares a form and binds its contract, nothing more, and every field a span carries is one that form declares (§4.3.2.1, §7.8) — there is no field every section has, because a universal field is a place where accretion happens. **`entry:` retires on content segments** — a fossil of the 1.0–2.x section, whose TOC line it labelled — and is renamed **`mark:`** on the structural segment, where it always meant something different and verifiable: the source's own mark text, verbatim (§4.3.2.3). **The annotations zone narrows to capture fidelity alone** (§4.3.3): the `reference` and `relation` namespaces retire, because an explicit link the source carries is *body content* reconciled at read time (§12.4.7) and an implicit or ambiguous reference is a ledger claim anchored at the span that makes it; and an `issue` becomes a typed code at an address, carrying no prose. **`canonical:` retires from the frontmatter** — disabled on the write path since 2026-06-28, never swept from the records that already carried it, and still without a shape for the HTML population. Against those retirements the amendment makes one **restoration**, and it is the point of the whole thing: a record may carry **more than one form section**, so content previously exiled to the annotations zone as "navigation, not content" comes home as a second span under the form that fits it. The whole-record section loses its privileges with its fields and its sibling prohibition; a span-scope section with a derived envelope is the ordinary shape (§4.3.2.1). A record holding several spans needs an order, and the amendment states it: **within a span the source's presented order, across spans significance order** — what the artifact is *for* first, the framing after — because document position is already carried exactly by the address, and a record that stated it twice would end up believing the weaker copy (§4.3.2.1). Which framing regions come home at all is the origin overlay's judgment, not a corpus-wide rule (§7.2). Migration: §12.27.

**Version 3.6** — the **addressing amendment** — makes an HTML address **total, structural, and permanent**. `el=<N>`, a 1-indexed counter over a *whitelist* of tags, becomes `el=<path>`, a dotted child-index path over **every** element in document order — `el=1.2.2.1.3` — so three properties hold that could not before. **The address space is total**: every element is nameable, and the `<li>` that was never citable and the `<div>`-soup artifact with *zero* addressable elements (§12.25's open question, filed rather than answered) both resolve. **It is permanent**: a whitelist is a versioned contract in disguise — adding `<dl>` on 2026-06-25 silently re-pointed `el=N` on 455 of the 458 artifacts containing one, invisibly, because a record does not record which whitelist produced its addresses — and the fix is not a better whitelist but the removal of the concept. The predicate splits in two: the **address space** (total, mechanical, never revised) and the drafter's **emit heuristic** (which elements get a segment — free to change forever, because it no longer decides what an address *means*). **And relation is legible from the address itself**: containment is a prefix test, ordering and siblinghood fall out, and a span that is a subtree *is* that subtree's own address — so an envelope can no longer over-claim content it does not hold, which retires a whole defect class rather than sweeping it. Ranges gain a sibling form `el=<parent>.[<a>-<b>]`; an authored claim on genuinely disjoint regions is an ordered **list** of addresses, which is what it always structurally was. *(A **migrated** interval is a different case and takes the tightest containing address instead — the retired flat form spanned everything between its bounds, so a list of the bounds would narrow it; §12.28.)* Two attested facts make drift loud instead of silent: the artifact block carries the pinned **parser identity** and the **element count**, so a resolver whose parse disagrees says so rather than resolving to the wrong element. Migration is mechanical and exactly verifiable — old index → new path is a pure function of an immutable artifact. *(Numbering is an identifier, not a schedule: 3.6 lands* before *3.5's record sweeps, because both touch every record and re-addressing first avoids a second pass over all of them.)* Migration: §12.28.

**Version 3.7** — the **derived-envelope amendment** — removes the last stored fact a record was keeping a second copy of: the **section's `address`**. A span's envelope was always *defined* as the min–max span of its children's addresses, and the conformance rule proved the redundancy by re-deriving the identical value and comparing it against the stored one — a fact written down and then checked against itself, which is the shape of every drift bug the previous amendments removed. It is now **derived, never stored** (§4.3.2.1): a section opener carries only the fields its form declares, and a form that declares none takes the bare opener that 3.5 already called complete. Two consequences fall out and both are simplifications. The **whole-record section ceases to be expressible** — it was spelled by the *absence* of `address`, and absence is no longer a signal — so every span's claim is exactly its children's envelope and cannot be anything else; the "claims the entire content zone" special case retires with the spelling, and with it the sibling prohibition's last remnant (§4.3.2.1). And the derived-editorial ladder loses the code path 3.5 had already retired in text: §4.2.3 stated that *a form contract marks nothing* and that *no section, at any scope, contributes to a record's display identity*, while the implementation still read a whole-record section's fields and three bundled form overlays still declared editorial marks — a divergence the stored envelope was quietly holding up. Both go. What remains of the section block is what 3.0 created it for: a span, a form id, and the contract's own declared fields. Migration: §12.29.

**Version 3.8** — the **placement amendment** — settles where a **member's** representation lives, and the answer is: on the member's own record, never on the record that contains it. A member is bytes with their own blake3, already rostered and already promotable (§4.3.1.4, §8.1); a containing record that transcribes one is authoring content about *someone else's* bytes, in a place where it can only ever be duplicated. The measurement is the argument: on the public hub 1,573 member transports appear in more than one record, 558 were transcribed in more than one record already, and 1,481 transcription passes had been spent producing renderings of bytes that had already been rendered. So **placement means promotion** (§8.1): a member positioned in a body must have a record of its own, and the containing record positions it with a new sixth segment kind — the **placement** (§4.3.2.4) — which carries an address and withholds every claim. What the member *is* stays where the bytes are. Three things follow. The parent's rendering of a member becomes a **violation**, not a style (§4.3.2.2), which is what makes the dedup sound: one leaf serves every parent, and *context is an input to the normalize pass, never to its output* — a member shared by 668 records has 668 contexts and one faithful rendering. The **import is derived** — the leaf is found by blake3 from the roster, so nothing is stored that could rot, exactly as §12.26 refuses a stored residence marker and 3.4 refused a stored body link. And a segment's `address` becomes **optional, with absence meaning the whole transport** (§4.3.2.2) — the record-side mirror of the bare `corpus://<id>` that has always named an artifact whole — which is what a promoted member's own rendering addresses, and which closes §12.25's open question by removing the fabricated value it was about rather than by inventing a better one. Demand splits to match the two failure modes: a placed member with no record is the **parent's** defect and lints there; a promoted member awaiting its pass carries **normalization pressure** on the leaf, N-fold in the number of parents placing it, joining the ledger's demand on one mechanism (§8.5). Migration: §12.30.

---

# Part I — The contract (normative)

## 1. Overview

### 1.1 What this is

A **corpus** is a content-addressed archive of captured artifacts, accessed through faithfully represented markdown proxies called **records**. Artifacts are deconstructed into addressable segments and rendered to text losslessly, or — where no lossless rendering exists — marked in place so the bytes themselves are one resolve away *(3.5: description as a third option is retired; §4.3.2.2)*. A record classifies its artifact **mechanically** — what the bytes are (media type) and where they came from (origin); what the content *means* is the ledger layer's concern ([`ledger.md`](ledger.md)), asserted there as claims whose evidence points back into the record.

A record is a single markdown file. The YAML frontmatter at its head carries a small bytes-identity header — what these bytes ARE (their hashes), the editorial summary, the provenance chain of processing passes. The **record body** below the frontmatter is organized into three **zones**: a **metadata zone** declaring what the artifact is, where it came from, and what members it carries; a **content zone** carrying the rendered content as sections and segments; and an **annotations zone** carrying observations about the record. Each zone holds a small set of HTML-comment block families; §4.3 specifies the grammar.

### 1.2 The transport model

Every captured file is a **transport** — a media-type-shaped container — that carries **content**.

- A transport's **intrinsic information** surfaces in the record's metadata zone — primarily in the artifact block for transport-intrinsic fields.
- A transport's **content** decomposes into a flat sequence of addressable segments in the record's content zone. Each segment carries one of four **content atoms** (text, image, audio, video) — or is a **structural segment**, a body-empty byte-mark carrying no atom (§4.3.2.3) — and an **address** indicating its location inside the transport.
- Every transport is **self-contained**: it produces a single record. When it contains a **nested transport**, it lifts that nested transport's intrinsic metadata into the outer record's artifact block and addresses its content per stream / per member, while an asset it merely references is rostered as a member row in the metadata zone. An ordinary single-content file (a plain HTML page, a PDF) simply has no nested transport to lift. A **raw archive** — a transport whose content is *other transports* — is attested as a **members roster**: every member becomes a content-addressed row (the member's `transport:` byte-hash + its member address) and the content zone stays empty (§12.4). *(2.1: the schema-declared disposition — `artifact_kind`, with its `decomposable` explode-at-ingest alternative — is removed; §7.1.)*
- A declared member is thereby **promotable**: because its member row records byte identity and address, it may later be minted as a first-class record of its own (**promotion**, §8.1) without its bytes ever leaving the container — a lookup of the promoted `id` streams them out through the container's address scheme (§2). Containment nests (a promoted member may itself be a container), and **residence is invisible**: the same bytes may live standalone, inside a container, or both, and no record changes when they move (§2).
- *(3.0)* **Container-vs-transport is a declared judgment, not a derivable fact.** The bytes cannot say which they are — a `.docx` is *provably* a zip, and reading it as one would be wrong. A mime schema therefore declares a **`disposition:`** (§7.1): **`manifest`** — the members ARE the content (archives, mailboxes, multi-entry text containers, media containers): the content zone holds only the container's own byte-marks, and every member is attested as a **manifest member**, promotable; or **`work`** — one transport whose content decomposes as units, and whose internal member files surface as **exposable members**: addressable and promotable, but *not* the content — a `.docx` is better read as one work; its pasted photo is an exposable member, its `word/document.xml` is not independently meaningful. The authoring criterion, normatively: **are the members independently meaningful transports?** An MKV audio track is — the transcript lives on it; OOXML internals are not. (EPUB's 2.x `self_contained` judgment — "an EPUB is one work, one record" — is this key's implicit ancestor, now explicit: `disposition: work`.) The mime schema declares the format's default; an origin overlay MAY override it for a producer whose use of the format deviates (§7.2). The disposition is always stamped and auditable, never sniffed per record. *(The 2.1 removal of `artifact_kind` stands — that key routed explode-at-ingest, which stays gone; `disposition:` declares attest/read shape, and nothing explodes.)*
- *(3.0)* **The member-vs-unit rule.** A **member** is a transport with its own MIME and standalone byte identity — attested as a row of the record's members block per the disposition, manifest or exposable, promotable either way. A **unit** is content *within* one transport — a message in a chat transcript, an entry in a log — reached by unit ops (`turn=`, §6.2) under a form mapping (§7.2), never rostered as a member. Unit-structured single transports are **not containers**: an NDJSON/JSONL stream, a location-history JSON, a health-export XML/CSV, a GPX track decompose as units of one work (`form/log` territory, §7.8), not as members.
- *(3.0)* A **multi-track media container** (MP4/ISOBMFF, Matroska, and kin) is a raw archive in the strict sense — a transport whose content is other transports — and is attested the same way: a **track manifest**. Each elementary stream becomes a content-addressed member row addressed `stream_id=<id>` (video stream, audio stream(s), text-based subtitle track(s)), and an attached picture is an ordinary member row; the artifact block carries the container facts (duration, per-stream codecs, dimensions). The content zone carries exactly one thing: the container's **chapter marks** as structural segments (§4.3.2.3) — chapters are byte-marks of the *container* (an MKV `Chapters` element, an MP4 chapter track; both encodings project to the same marks, the mime schema pinning which encoding wins), marking the shared timeline no single track owns. Tracks are **promotable on demand, never exploded**: a promoted track record's bytes materialize through the container (`stream_id=` transform — the `part=<N>` precedent), no bytes copied; extraction semantics are pinned by the mime schema (the mbox `msg=<N>` precedent) so member bytes are deterministic (§11 flags the demuxer-determinism engineering risk). The audio-track record owns the transcript (`?transcribe`, §6.2); the video-track record owns frame work (on-screen text as `text/ocr` is faithful; what a frame *shows* is not recorded at all — the frame marker stands for it, §4.3.2.2); a text-based subtitle track projects faithfully as (time_range, text) segments. Tracks inherit the container's chapter marks at **read time through lineage** (§6.2) — never copied, because the track's own bytes do not carry them (§4.3.2.3, the byte-mark rule). A **single-stream artifact** (a bare MP3, a JPEG) has no member transports to declare and stays a single `work`; a single-*track* media container nonetheless stays `disposition: manifest` — **default-member resolution** (§6.2) makes the bare op transparent (`?transcribe` on a single-audio MKV needs no `stream_id=`), so the disposition never flips per record. The same-video composition — tracks threaded over the shared timeline — is a read-time derived view joining on (lineage, time), exactly as a cross-platform conversation view joins on (ledger identity, time): same tuple, same composition layer, no media-specific logic stored anywhere.
- *(3.0)* The manifest family extends along two more axes, no new machinery. **Multi-entry text containers** are the mbox precedent generalized: a multi-card VCF is a manifest of `text/vcard` members at `card=<N>` (`BEGIN:VCARD`/`END:VCARD` delimiter-pinned extraction, so member bytes are deterministic and promotable — §12.11), an ICS calendar of `VEVENT` entries at `entry=<N>` likewise. **HEIF/HEIC** is the media container on the image axis: image items attested at `item=<id>`, and an Apple **Live Photo** is the container's *declared primary* still (the `pitm` primary-item box — a byte-fact) plus its paired video track, both reachable bare through default-member resolution (§6.2): `bbox=` acts on the declared-primary still, `time_range=` reaches the motion component. A **motion photo** (an MP4 appended inside a JPEG's bytes) is the nested-transport lift above — the inner video attests as an embedded transport of the JPEG work — not a new mechanism. Formats that arrive later slot into the same strategies: 7z/rar/dmg join the zip-manifest family, PST/OST and WARC join the mbox precedent, when a real capture wants them.

### 1.3 The atom / segment model

A record body's content zone is a sequence of **sections** (form spans, §4.3.2.1 — rare; present only where a form is declared) and **segments** (the read-order rendering). Each content segment carries:

- One **content atom**: `text`, `image`, `audio`, or `video`. Only `text` segments carry a segment body. Segments of the other three atoms are positioning markers — they declare where in the reading order a region of *this* transport appears, materialized on demand through the resolver — and their segment body is empty. *(3.8: an asset that is itself a transport, and so has a member row, is positioned by a **placement** instead — below.)*
- An **address** specifying the segment's location inside the transport, in a scheme determined by the media-type schema. Addresses compose, so that chains can form from transport to atom to region (a region within a frame within a video). *(3.8: **optional** — an absent address names the whole transport, §4.3.2.2.)*
- Exactly one **atomic classification**, declared on the opener line in the form `<!--segment <atom>/<id>-->` (or bare `<!--segment <atom>-->` for unclassified-but-typed segments). Text-atom overlays may declare lossless-shaping behavior — those overlays shape the segment body into a specific lossless form (a markdown table, a transcript, a chat message). When multiple representations apply to the same source region, each becomes its own segment.

*(3.0)* A fifth segment kind — the **structural segment**, `<!--segment structural-->` (§4.3.2.3) — carries no content atom and no body: it is a **byte-mark**, the faithful record that the source itself declares a structural boundary at an address (a heading, an outline entry, a chapter mark, a topic boundary), with a `level:` and an optional `mark:`. The table of contents is a **derived rendering** over these marks — arbitrary depth, zero nesting grammar — never a stored grouping. *(The 1.0–2.x stored TOC — sections as grouping blocks — retires; §4.3.2.1.)*

*(3.8)* A sixth — the **placement**, `<!--segment placement-->` (§4.3.2.4) — likewise carries no atom and no body: it records that a **member** (§4.3.1.4) sits at this position, and nothing else. What the member contains is its own record's to say, reached by the blake3 its roster row already carries; placing one is what obliges promoting it (§8.1). The two content-less kinds are symmetric — a mark points at a boundary the source declares, a placement at bytes the roster names — and both exist for what they withhold.

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

3. **Faithfulness.** A record body is a faithful, lossless rendering of the transport's content. Normalization may resolve ambiguity (encoding, broken layout, OCR for scans) but never adds information not present in the source. Descriptive content (a summary of what an image shows, a paraphrase of what was said) is lossy by definition and *(3.5)* has **no home in a record at all** — not the body, not a header field, not the annotations zone. Where a region has no lossless rendering the record marks its address and stops; summary is a query, answered one layer up by the ledger's claims over the record's verifiable surfaces (§4.3.2.2). Re-segmentation is structural, never editorial. *(3.0)* The same principle governs structure: a **structural segment exists only where the source carries the mark** (§4.3.2.3, the byte-mark rule). A grouping the bytes do not declare — a conversation's per-day break: whose midnight? — is a *read-time rendering* with explicit parameters, never a stored block.

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

An id need not resolve to a *standalone* file. When a captured container's record rosters a member as a content-addressed row (the member's `transport:` hash with a resolvable member address), that member's bytes are retrievable by their own blake3 **through the container**: the implementation streams them out via the container's address scheme, recursively when containers nest. How the route from a bare id to its container is found is implementation-defined, but it MUST be **derived** from the records' members-block rows — never stored on the promoted record (§12.9) — so bytes may move between standalone residence and containment, or be resolvable by several routes at once, without any record changing. Every route to an id yields identical bytes by construction; a resolver may take any.

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
| `context` | The umbrella for every **annotation** namespace — observations *about* a record. | Per-namespace overlays declared via the **context block** (`context/<namespace>/<id>`). *(3.5: one namespace — `issue`, capture-fidelity problems. `reference` and `relation` retired, §4.3.3.3/§4.3.3.5.)* |

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

*(3.1)* A record is born complete. Ingest (or promotion) attests the bytes' identity and facts, and from that moment the record is the artifact's **proxy**: bytes retrievable by id (§2); artifact block + **attested byte-facts** emitted — the mime schema's declared attestations (artifact fields; manifest members for archive/mail/media-container types; structural byte-marks; sidecar lift); first origin block populated from capture / containment context; fully *readable* — its mechanical body is a resolver derivation (§6.2), computed on demand, cacheable by a search index (§9), never persisted to the record. Everything beyond attestation is layered on when it earns its place, and every layer is **self-evident in the record's own bytes** — there is no stored lifecycle field summarizing them (*3.1: `status` is retired*; §12.19):

| Layer | Present when | Written by |
|---|---|---|
| **attested** | always — the universal baseline above | ingest / promote (§8.1); refreshed by re-attest (§8.3) |
| **formed** | a **form section** (§4.3.2.1) governs the record's stored content zone: the record carries a stored **rendering** of its content under a named rendering contract (§7.8) *(3.5: the section header carries only the fields its form declares — there are no editorial fields to author, §4.3.2.1)* | the normalize pass — a mechanical shaper where a declared mapping applies, an interpretive agent where not (§4.4.6) |
| **terminal** *(3.3)* | a **terminal contract** (`form/passthrough` / `form/manifest`, §7.8) governs the record — declared at overlay grain (mime/origin `form:`; or derived: `disposition: manifest` with no rendering contract declared) or asserted per record (§4.4.6) — and the record **deliberately stores no rendering**: the artifact (or its attested members) is the terminal representation. An optional whole-record opener may carry the editorial header (§4.2.3) with nothing beneath | the declaration (an overlay key — no record write); the opener, a deliberate describe pass |
| **authored** *(retired 3.2)* | — dissolved into the form layer: interpretive editorial prose rides the form section header (§4.2.3, §4.3.2.1); a formless record's title/description are derived from its role-marked attested and origin fields, and genuinely interpretive prose requires a form or belongs to the ledger. Segment/section descriptions and asserted annotations remain the normalize pass's licensed work (§1.5 principle 3, §4.4.7) — they just no longer constitute a record state | — |

Three consequences carry the model:

- **Formless is the zeroth form.** A record with no form section is not pending — it is the artifact's proxy under the **identity contract** (§7.8): the faithful representation of the bytes is the bytes, delivered through the derivation ops, prescribing nothing about what the artifact is. Most artifacts a corpus consumes as raw context — code, datasets, media, containers — live here permanently and correctly. A formless record is upgraded to a named form when one is identified or authored for it (§4.4.6), and only then. *(3.3)* The *permanently* half of that sentence is now declarable: a **terminal contract** (§7.8) marks it, reporting distinguishes **terminal** from **proxy**, and *proxy* thereby narrows to mean genuinely unassessed-or-awaiting — the population a rendering contract may still claim.
- **A stored rendering rides a named form.** Steady-state invariant: a record stores a content zone beyond its byte-marks only where a form contract governs it — under the identity contract, a "stored rendering" would merely restate bytes the resolver already derives. (Formless segments *within* a record that carries a form span are the mixed-artifact case and conform — §4.3.2.1. Renderings the 2.x→3.x migrations grandfathered without a form exit through their next pass — §12.19.)
- **There is no vouch** *(3.5, retiring 3.2's "the vouch rides the form" and with it 3.1's "the vouch is orthogonal")*. Every record derives its title/description from role-marked artifact and origin fields (§4.2.3) — mechanical, present from birth, no pass required — and where those resolve empty, **empty is the answer**. The interpretive editorial fields 3.2 placed on the form section header are retired: a record has no editorial opinion of itself to record, at any scope. Shaping is the whole of the pass, and what a record's content *means* is the ledger's to say (the 2.0 discipline, now without exception). What 2.x–3.0 called `normalized` — 3.1's *formed + authored* — is **formed** alone, and 3.5 empties the second half of that phrase of any residual meaning.

State is **reported, never stored**: health, the queue's pass gate (§8.5), and the ledger's verification (`ledger.md` §13.2) each derive the predicate they need from the record; the touch chain (§4.2.2) remains the provenance trail. *(3.0: the `draft` status retired — the §8.1 tombstone. 3.1: `stub` and `normalized` follow it; a record carrying a `status:` field reads tolerantly — the field is ignored on read and dropped on the record's next write; §12.19. 3.2: the `authored` predicate follows — and with it the stored editorial pair: frontmatter `title:`/`description:` read tolerantly as the override of §4.2.1 and are dropped by the migration sweep where not deliberately asserted; §12.21.)*

### 4.2 Frontmatter

The frontmatter (`---...---` at the top of the file) holds **only the bytes-identity header** — at most eight fields *(3.1: `status` retired, §4.1; 3.2: `title`/`description` become optional overrides of the derived editorial fields, §4.2.3, and are absent in the steady state)*. Everything else lives in body blocks (§4.3) or surfaces as derived views (§9).

#### 4.2.1 Core fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Primary identity — blake3 hash of the artifact's bytes, 64-char lowercase hex. Filename stem. Bare hex (no `<algo>:` prefix; algorithm is invariant). |
| `transport` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | Byte-level hash(es) of the file under additional algorithms beyond the primary blake3. The primary blake3 lives on `id` and is **not** duplicated here. Use `transport:` only for alternative algorithms. |
| `perceptual` | `<algo>:<hex>` \| list[`<algo>:<hex>`] | no | Record-scope perceptual fingerprint — present only for single-atom records (e.g. an image artifact carries a perceptual hash). Multi-atom records carry per-segment perceptual fingerprints in segment headers instead. |
| `touch` | string \| list[string] | yes (≥1) | Ordered list of touch identifiers, one per processing pass. Singular (bare string) when one entry; list when 2+. `touch[0]` is the original ingest. |
| `visibility` | enum | no | `visible` (default), `deranked`, `hidden`. Editorial curation, orthogonal to the derived content state (§4.1). |

*(3.5)* Three fields retire from this table. **`title` and `description`** — the optional overrides 3.2 left behind — are gone: an override is by definition the record asserting a display value of its own, which §4.2.3 no longer admits from any layer. The derived pair resolves from attested byte-facts or resolves empty, and empty is an honest answer. **`canonical`** is gone with the mechanism (§7.1): the strategy was disabled on the write path in 2026-06-28 after `blake3-canonical-pdf` was found to collapse unrelated scanned PDFs, no shape was ever settled for the HTML population that carried most of it, and nothing has read the field since. A record needing a content-identity beyond its bytes will re-earn the field with a strategy that works; until then storing a hash nothing computes and nothing reads is stale state that reads as live.

#### 4.2.2 Touch identifiers

A touch identifier is a short bare string distinguishing a processing pass. The sequence is `touch[]` — a bare string when the chain has one entry, a list otherwise; the chain records the record's **current-shape provenance** (which passes produced the shape it has now). It is not an immutable history: `re-stub` resets it (§8.4), so a re-stubbed record's chain reflects its post-reset lineage, not every pass it ever saw.

- **Pipeline tooling** uses a stable identifier of the form `<package>.<module>@<version>` (e.g. `corpus.ingest@0.2.0`, `corpus.shape.conversation@0.2.0` — a **shaper** pass names the form or strategy it shaped). The `<package>.<module>` identifies the code path; `<version>` is its installed version.
- **LLM models** use the canonical model identifier with any context modifier in brackets — e.g. `<model-id>[<modifier>]`.
- **Combined tooling + model** — a single pass that is both a deterministic re-assembly and the LLM pass it carries joins the two with `+`: `<package>.<module>@<version>+<model-id>`.

Consecutive identical passes coalesce rather than repeat: a second identical identifier becomes `<identifier>_2`, a third `<identifier>_3`, and so on; a different identifier resets the count. The counter reflects the current chain, so a `re-stub` (which collapses the chain, §8.4) resets it.

The latest touch's tooling version implicitly encodes the spec era under which the record's current shape was produced.

#### 4.2.3 Derived editorial fields *(3.2; the interpretive rung retired in 3.5)*

A record's display **title** and **description** are **derived, never stored** — a pure function of the record's own blocks and their schemas, computed at read time exactly like the classifications view (§9.1).

*(3.5)* They are also **never authored**. The two candidate layers are the two that carry someone else's words: the **artifact**, whose bytes may state a title or a self-description, and the **origin**, whose producer may have stamped one. The corpus reports those. It never composes its own — the interpretive candidate 3.2 placed on the form section header is retired with the field itself (§4.3.2.1), and so is the frontmatter override (§4.2.1). A record that resolves an empty title or an empty description is not defective and is not awaiting a pass: it means the source said nothing about itself under that role, which is a fact about the source. Where a display string genuinely needs authoring, it is authored **against the concept in the ledger**, which is the layer whose job is saying what things are.

**Role marks.** An `extended_fields` declaration in either of the two candidate namespaces may carry `role: title` or `role: description`, marking that field as an editorial candidate:

- a **mime** schema marks artifact-block byte-facts (§7.1) — a PDF's `/Info` title or `/Subject`, an HTML `<title>` or `meta[name=description]`, a bundle's embedded comment;
- an **origin** overlay marks origin-block fields (§7.2) — `ytdlp_title`, `ytdlp_description`.

A **form** contract marks nothing. Forms declare shape (§7.8), and a shape judgment is the corpus's own word about itself — precisely what this section no longer admits. This is the bright line: artifact and origin quote a source; form would editorialize.

**Editorial templates** *(3.3; narrowed to the origin layer in 3.5)*. An **origin overlay** may declare a top-level `editorial:` block naming a **mechanical composition** over more than one origin-block field (§7.2):

```yaml
editorial:
  title_template: "Mail window — {window_start} → {window_end}"
```

`{name}` placeholders substitute the origin block's own `extended_fields` values, read exactly as a role-marked field is (a list-valued field joins its non-empty items with `, `); static text passes through unchanged. Resolution is **all or nothing**: the template resolves only when **every** placeholder names a field holding a non-empty value — one unresolved placeholder falls the **entire** template through, never a partial composition. A template composes **attested producer facts into a display string**; it states nothing the origin block does not already carry, which is why it survives the 3.5 rule while an authored value does not. *(3.5: `description_template` retires unused — it was admitted in 3.3 as "a natural sibling, undeclared until a contract needs it" and no contract ever declared one. `<role>_template` for a retired role is not declarable.)*

A `title_template` (or any `<role>_template`) value may be an **ordered list** of templates in place of a single string: entries are tried in declaration order and the **first that fully resolves wins** — each entry individually all-or-nothing, per the rule just above — with a bare string standing as the one-element case of the same grammar. The cascade lets one producer overlay title several record shapes with disjoint field sets from a single declaration: each shape picks its own composition deterministically, by which entry's fields are actually present.

Templates resolve per origin block exactly as the overlay's role marks do (§7.2: latest qualified block wins; a bare block contributes nothing), so the origin layer's within-layer order is **template → role-marked fields** — e.g. a mail window bundle's overlay composing from the fields its producing verb stamped (§12.3.13). On a **subtype-qualified** origin block, `editorial` resolves by the same ladder as any other concern (§7.2): the subtype overlay's declaration is consulted first, the id overlay's as fallback. A `<role>_template` value may be an **ordered list** in place of a single string: entries are tried in declaration order and the **first that fully resolves wins** — each entry individually all-or-nothing — with a bare string standing as the one-element case. The cascade lets one producer overlay title several record shapes with disjoint field sets from a single declaration.

**Resolution.** Candidates resolve by layer precedence **artifact → origin** — the origin overriding the artifact, because a producer's stamp is the later and more specific statement about the same bytes. Within a layer, the **latest block wins** (origin blocks append in capture order, so a re-capture's fields supersede); within one block, the schema's declaration order decides, first non-empty winning. An empty or absent candidate falls through to the next, and an all-empty chain resolves to an honest empty value. *(3.5: the form layer and the frontmatter override are both gone from this ladder; with them goes the whole-record-section privilege — no section, at any scope, contributes to a record's display identity.)*

**Consequences.** Every record carries its display identity **from birth, deterministically, and permanently** — there is no pass that can improve it and none that can corrupt it. *(3.5)* Resolution is now wholly mechanical: no LLM pass has ever been required, and now none is *permitted*, so a record's title cannot drift from what its bytes and its producer say. A record deriving *empty* is a signal about its **schemas**, not its content — the mime or origin overlay wants a role mark on a field the block already carries — and health surfaces it as exactly that (§12.21). Where the derived pair is empty and the schemas have nothing to mark, the honest reading is that the source named itself nothing; a consumer needing a human label for that record wants the **ledger's** name for the concept it evidences, not a sentence the corpus invented. Consumers (the derived body, search indexing, export §10, the ledger's display of cited records) read the derived value, and there is no longer any stored pair for anything to read.

**Enumeration is by cohort, not by title** *(3.5)*. The pressure that kept an authored title alive was practical rather than principled: a table of records wants no empty cells. The answer is not to require every record to produce one string — which is what manufactures the mechanical/interpretive ambiguity this section exists to remove — but to **stop listing unlike records in one table**. A cohort is a population sharing a schema — one origin, one form, one mime — and **that schema's `extended_fields` declaration IS the column set**, in declaration order, every column mechanically derivable from the bytes by §7.2/§7.8. A statement cohort lists as `institution | account_ref | statement_date | coverage`; a bulletin cohort as `bulletin_no | bulletin_date | supersedes`. Those columns are strictly richer than the title string that used to flatten them, and unlike a title they sort, filter, and group.

Which layer supplies the columns is decided by **which layer holds mechanical facts for that population**, exactly as elsewhere the layers do not bleed: the **origin** for producer exports (whose sidecars stamp account, period, coverage), the **form** for shape-bearing cohorts, the **mime** for format facts. A cohort whose schemas declare nothing is not defective — a generic `form/document` population genuinely has no universal facts, and the honest listing for it is by origin instead.

Three columns are always available and never interpretive, and they are the whole of what a **heterogeneous** listing is owed: the record `id`, its origin `uri`, and its media type. Where a cross-cohort listing wants a human name, that name belongs to the **ledger** — a record's human handle is the name of the concept it evidences (`ledger.md` §4), authored once against the thing itself rather than once per record that mentions it. The corpus enumerates within a population; naming across populations is knowledge, and knowledge is one layer up.

### 4.3 The record body — seven block families, three zones

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

##### 4.3.1.4 The members block

At most one per record. A single header-only block whose payload is the **unabridged roster of this record's embedded assets** — one row per member. *(3.4: replaces the per-asset `<!--embed-->` block, §12.26.)* A member is a **closed primitive**: it declares an asset whose bytes are **part of this record's capture** — materializable from the record's own artifact (a nested transport, an archive member, an inline `data:` asset, a media track) or from its capture-time enrichment (`also_capture`). A record never rosters content that lives in *another* record's capture; content the record's bytes merely *reference* is reached at read time through the resolver — a lineage-chained reference (§6.2) or a URL-tier context edge (§4.3.3.3) — derived, never stored. The `transport:` hash names the bytes (the dedup key); the address says where the asset appears in this transport.

The block is **wholly attested** (§4.4.x layers): every row is re-derived from the artifact on every attestation, and nothing in it is a normalizer's to write. It is an **index**, not a description — its job is to answer *which record holds this blake3, at what address, of what type, how big* without opening a single artifact, because that question is asked across the whole corpus at once (the member index, §12.15) and must stay cheap at fleet scale.

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
| `media_type` | The member's full MIME type. *(3.4: moved from the retired per-asset block's opener line, since one block now carries mixed types.)* |
| `bytes` | The member's size in bytes, uncompressed. Present so size accounting over a corpus of containers costs one pass over records and no artifact reads. |

###### The admission rule

A field is admitted to the row only if it (a) answers a question asked **across records** without opening an artifact, and (b) is an **identity-or-accounting fact** rather than a reading of content. Both, not either.

Everything else about a member — pixel dimensions, verbatim `alt` text, a member filename, an email member's `from`/`subject`/`date`, a vCard's display name — is derived on demand by the `members` op (§9) and stored nowhere. This is not a size optimization; it is what keeps the roster mechanical. A block that carries readings of content invites authoring, and an authored roster is no longer idempotently derivable from the artifact it claims to describe.

Two consequences worth stating, because both are tempting:

- **Pixel dimensions fail (a)**, not (b) — the question they answer is about one image, and any real use of it needs the pixels anyway. They would earn a place if a gate were ever built to check a fractional region address against the asset's true extent rather than only against the region grammar (§6.2); until such a gate exists, they are derived.
- **An email member's `from`/`subject`/`date` pass (a) and fail (b)** — "find the message from X about Y" genuinely is a cross-record question, which is exactly why this one is tempting. It is a reading of content, it belongs to the `members` derivation, and admitting it is how the roster would begin accumulating again.

A member's **narration** has no home here — and *(3.5)* no home anywhere else either. 3.4 retired the per-asset `description:` and pointed narration at the block that places the asset; 3.5 retires it there too (§4.3.2.2). What a record can say about a member is its row (identity and accounting), its placing marker (where and what type), and any lossless extraction from it; anything beyond that is the member's own record once promoted (§8.1), or a ledger claim. §12.26, §12.27.

###### Deduplication

Members are deduplicated by `transport` — identical content collapses to one row regardless of how many positions reference it. The attesting pass walks the transport's assets in order, hashes each, and merges duplicates by appending positions to the existing row's `address` list.

###### Linking from segments

Segments link to members by **address membership**, not by an explicit reference field. A segment whose address appears (scalar or list-member) in a member's `address` is the place where that asset sits in the record's representation. Unplaced members — rows no segment points at — are tolerated as a record of available assets: the roster is unabridged by design, and declining to *place* a favicon is the pruning decision, never editing the roster.

*(3.8)* The segment that does the linking is a **placement** (§4.3.2.4), and it is the only kind admitted at a member's address. The correspondence is exact in both directions: **a placement's address MUST appear in some member's address** — a placement naming no member names nothing — and **no content-atom segment's address may appear in, or chain from, a member's address**, because a member's content is its own record's to render. The chained form is included deliberately: `el=<path>&bbox=<x,y,w,h>` is a crop of the member's *pixels*, so it is a rendering of the member's bytes wearing the container's address, and it re-homes onto the member's own record with the crop intact and the `el=` prefix gone. Placing is therefore also what obliges promotion (§8.1). *(Structural byte-marks are unaffected and may stand at any address, member or not: a mark is the source declaring a boundary, which is a fact about this transport regardless of what sits at the position.)*

Every image, audio, and video segment therefore addresses something the resolver materializes from **this record's own capture** without a roster row — which is the same carve-out this section always drew, now stated as the rule rather than the exception. Two cases qualify:

- **Artifact self-slices** *(unchanged from 2.x)* — a region of the record's own artifact: a `frame=`/`time=`/`time_range=` into a video, a `page=` render of a PDF, a `bbox=` into a single-image record.
- **Lineage-chained references** *(3.0)* — an asset the record's bytes declare but do not contain, whose bytes live in the record's own containment-lineage parent (§6.2): a conversation message's attachment (`turn=<N>&att=<M>`), a promoted member's sibling asset. The reference is faithful content (it is *in* the bytes); the resolution chain is derived at read time from the lineage origin block plus the record's own bytes — never stored — and cannot rot, because the parent is content-addressed. A reference whose target member is absent (a dead CDN link the export never localized, a takeout gap) is still a faithful marker; materialization fails loudly at resolve/health time, never papered over by a stale stored pointer.

A member row is needed only for assets that are neither self-slices nor lineage-resolvable — an inline image the capture inlined, a nested transport, a declared track. *(3.8: which is the same set that takes a placement rather than a marker, and the same set promotion reaches — one line, drawn once, read three ways.)*

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

(The structural mark is the platform's own topic boundary — a byte-mark; DiscordChatExporter (DCE) exports carry none and go flat. `participant:` indexes the section's authorship-ordered codebook. Turn 2 is an attachment-bearing reply: its `text/message` envelope segment is empty-bodied — the message has no text, and the envelope never rides the marker — and the `image` marker at the composed address carries no member row: the attachment is lineage-resolvable, §4.3.1.4/§6.2.)

###### Section header fields

| Field | Required? | Description |
|---|---|---|
| ~~`address`~~ | *(3.7: retired)* | The span's **envelope** — the min–max span of the child segment addresses (`pages=2-6`, `turn=1-74`, `el=` under the §6.1.1 path algebra). **Derived, never stored.** Below. |
| *(form fields)* | Per overlay | The **codebook and envelope fields the form overlay declares** (§7.8) — e.g. `form/conversation`'s `participants:` list, the authorship-ordered codebook that `participant:` segment indexes resolve against. Mechanically derivable from the span's own bytes (§7.8). |

***(3.7) The envelope is derived, never stored.*** A span **is** its children; its envelope is the min–max span of their addresses and could never have been anything else. The 3.0–3.6 grammar stored it and then had lint re-derive the identical value to check it — the one construction the previous four amendments each removed an instance of, here in its purest form. So the field goes, and the derivation is the definition: `section_address(children)` under the children's own discrete-index scheme, computed by every reader. Nothing is lost — a stored envelope could disagree with its children, and a derived one cannot.

Two things retire with the field rather than needing successors. The **whole-record section** was spelled by the *absence* of `address`; with the field gone there is no absence to read, so a section always claims exactly its children's extent and the "spans the entire content zone" case has no spelling and needs none — where one form governs everything, its one span's envelope simply covers everything. And a record's **display identity** stops having any section-shaped input at all, which is what §4.2.3 already said in 3.5 (*a form contract marks nothing*; *no section, at any scope, contributes*) and what the whole-record lookup was still quietly implementing.

*(A **temporal** section — `time_range=` — was never an envelope in this sense: it is a structurally bounded interval, not a min–max over children, and it is built directly. Such a section states its bounds as the form's own declared field, not as the retired universal one.)*

***(3.5) There are no universal section-header fields.*** `entry:`, `title:`, and `description:` are retired — and *(3.7)* `address` with them, so the count of universal fields is now zero. **Every field a section carries is one its form declares.** A form that declares nothing — `form/index` is the measuring case — takes a **bare opener**, and the bare opener is complete: `<!--section index-->` says *this span takes the index form and renders under its contract*, which is the entire job of the block. The retirement is structural, not stylistic. A field present on every section regardless of form is a field no contract owns and no check binds, so it is where accretion lands — first a TOC label, then a title, then a paragraph of interpretation — and each addition looked reasonable against the one before it. Removing the universal slot removes the landing site.

###### Rules

- **Positional span.** A section's closer is followed directly by its first child block; its span runs to the next section opener or the end of the content zone. Markdown prose between a section closer and the next opener is a parse error — sections have no body region.
- **Depth one, no overlap, one form per span.** Sections never nest and never overlap (positional by construction). Forms do not nest; a genuinely separable sub-document is a **promotion** candidate, not a nested form. *(3.5: the whole-record section's sibling prohibition is lifted. A record MAY carry any number of sections, each a span under its own form — an article followed by the index of sibling links the page also renders; a manual's procedure span followed by its parts table. The prohibition existed because the whole-record section held the record's editorial identity and two of them would have been two answers to one question; with those fields retired the section holds only a shape judgment, and a document that changes shape partway through is an ordinary document, not a contradiction.)* *(3.7: and the prohibition is now unstatable as well as lifted. It was keyed on a section with no `address`, and there is no longer such a thing — a span's extent is its children's, so two sections can only overlap if their children do, which the address grammar and `segment-address-duplicate` already decide. One rule, at the segment grain, instead of two at different grains.)*
- **Block order is significance order, not source order.** *(3.5, stated 2026-07-27 — multi-span records are what made the question askable.)* **Within** a span, blocks follow the source's presented order: that is what faithfully rendering a region means, and the ordered-axis forms bind it as a `monotonic` check (§7.8). **Across** spans the rule is different — the content zone opens with what the artifact is *for*, and the spans that merely frame it (a breadcrumb trail, a sibling-links rail, whatever navigation furniture the page wraps around its content) follow it. Nothing is lost by this, because block order was never where document position lived: position is carried exactly, mechanically, and at finer grain by the `address` (§6.1.1). A record that encoded it in both channels would be stating one fact twice, and the weaker copy is the one that eventually gets believed. For chrome the source's own order is not even well defined — a rail is routinely emitted nowhere near where it is displayed — so a rule that ranks spans by what the artifact is about is the only one that needs no per-host adjudication. **Nothing declares a span "chrome."** Whether a span is the content or the frame is a property of its role in *this* record, never of its form: `form/index` is the whole content of a category-selector page and the furniture on an article that happens to carry a link rail. Significance is expressed *by* position, so a `chrome:` field would be a second answer to a question order has already answered — and, being a field no contract owns, exactly the accretion site the retired universal headers were.
- **Formless is the zeroth form; a named form is earned.** *(3.1, amending 3.0's "rare by design.")* A section exists *only* where a named form is declared — and a record with no section is not deficient: its content stands under the **identity contract** (§4.1, §7.8), consumable through the derived body, prescribing nothing about what the artifact is. Artifacts with no faithful markdown shape — code, datasets, media, containers — stay formless permanently; that is their correct steady state, never a backlog. For artifacts a markdown shape genuinely fits, formless is instead a starting point: a named form is the goal, adopted lazily when identified or authored (§4.4.6, §7.8). Segments before the first section opener are **formless** content under mime + atoms alone — the mixed-artifact case: a statement PDF whose page 1 is a cover letter carries page 1's segments bare, then `<!--section statement address: pages=2-6-->` over the statement proper.
- **Coherence is lint-enforced.** A record carrying `<!--section <form-id>-->` MUST satisfy that form overlay's declared conformance checks (§7.8) — envelope fields present, codebook indexes in range, addresses parse in the span's scheme. There is no half-asserted form and no transitionary state: stamping the form and conforming the span land together.

*(The 2.0 note on section-scope composites is unchanged and remains at §4.4.3: a passage's meaning is still a ledger claim over the span. The form id on the opener is a structural-shape judgment, not a meaning — §7.8.)*

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
address: pages=2-6
account: '…7841'
period: 2026-03
-->

<!--segment text/ocr
address: page=2&bbox=0.06,0.12,0.88,0.30
-->

... transactions rendered per the statement form's contract ...
```

Page 1 stays formless — no contract has been identified for it and nothing yet demands one (§7.8: adoption is benefit-driven; formless is valid indefinitely); the statement's codebook/envelope fields (`account`, `period`) ride the section header, mechanically derivable from the span's own bytes; lint runs `form/statement`'s checks over pages 2–6 only. *(3.5: page 1's cover letter is not narrated — it is **transcribed**. The image marker says a page-1 raster exists; the co-addressed `text/ocr` segment carries what it says. The pre-3.5 shape wrote `description: Cover letter accompanying the March statement.` on the marker, which is the record telling the reader about content it declined to render — a paraphrase competing with the bytes it stands in front of. If the letter is worth mentioning it is worth transcribing; if it is not worth transcribing, the marker alone is the honest record and the bytes are one resolve away.)*

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
- **Body-empty marker** — every other segment, in two cases. (a) The three non-text atoms (`image`, `audio`, `video`) are positioning markers in document flow for a region of **the record's own transport** — a self-slice the resolver materializes from these bytes (a PDF page raster, a `bbox=` crop, a `frame=`/`time_range=` cut). *(3.8: an address that a **member** row carries is no longer this case — the member has its own byte identity and its own record, and it is positioned by a `placement` (§4.3.2.4). A content atom at a member address claims residue in bytes that are not the record's to claim.)* (b) A `text/<id>` overlay whose declaring schema sets `enables_lossless: false` marks a *typed but non-lossless* text region — e.g. a live, formula-driven table whose displayed values are a single-execution snapshot rather than faithful content. In both cases the segment body is empty **and stays empty**.

  *(3.5)* **A marker says where the bytes are; it never says what they contain.** What the region is, is answered by the opener — the atom and its overlay id (`image/chart`, `image/logo`, `text/data-table-dynamic`) — which is a typed, cross-record-queryable, mechanically-checkable answer, and by the address, which is where to go. A marker carrying prose would be the record substituting a paraphrase for a rendering it declined to perform. This obliges the atom namespace to keep its overlay ids **self-describing** (§7.3): an overlay too vague to answer "what is this region" is under-specified, and the fix is a better overlay, never a sentence on the segment. Where more than the type is genuinely knowable, it is knowable **losslessly** — as a co-addressed segment (below) or, if the asset deserves standing of its own, as a promotion (§8.1).

**A faithful rendering replaces the marker** *(3.5; corrected 2026-07-27)*. Where a region's content is rendered losslessly, that rendering is the region's representation and the positioning marker goes. Nothing is lost by dropping it: the member row addresses the bytes directly (§4.3.1.4), so the resolver reaches the pixels whether or not a marker sits in the reading order. What a marker adds beside a complete transcription is not a second representation but a **second, contradictory ruling** about one region — because the atom is precisely how a segment declares whether anything is left over (§7.3, `enables_lossless`), and a region cannot both have residue and not have it.

**If it cannot faithfully replace, it is not a faithful rendering** — and the marker standing alone is then a **finished** record, not a backlog. A photograph is never reduced to its words: its marker is permanent, the region is honestly represented by its bytes, and `corpus resolve` is how a reader reaches them. Where the whole artifact is that case, `form/passthrough` states it at record scope (§7.8). Better tooling may reduce such a region later; nothing is owed until it does.

Same-region stacking remains exactly what the identity rule permits — several representations at one address, distinguished by opener-id — but a marker beside a *complete* transcription of the same region is not an instance of it. The genuine instances extract **different** information: the text printed *in* a photograph is a `text/ocr` segment at the sub-region it occupies (`el=N&bbox=…`), which is a different address, while the photograph's own residue keeps the marker at `el=N`. A whole-frame `bbox=0,0,1,1` is not a sub-region — it is the same full-region transcription wearing a crop, and the same rule applies.

*(This paragraph previously read "a marker and a faithful extraction of the same region coexist, always." That was drafted the day after the ruling above and inverted it; the tooling was then reconciled to the draft rather than to the ruling. Both are corrected — §12.28's successor migration re-removes the markers that sweep restored.)*

###### The address field

| Field | Description |
|---|---|
| `address` | Address inside the transport, in the scheme defined by the media-type schema. Part of the segment's identity. Composable: addresses chain transforms (e.g. transport → frame → region) as the schema permits. *(3.8: **optional** — absence names the whole transport. Below.)* |

***(3.8) An absent `address` names the whole transport.*** A functional URI has always spelled *these bytes, whole* as the bare `corpus://<id>` with no query (§5.1, §6.1); an absent segment address is the record-side mirror of it, and means exactly the same thing. It is required for the ordinary case a promoted member creates: a record whose artifact **is** the addressed content — a promoted table image whose whole rendering is one `text/data-table`, a plain-text artifact rendered whole — where every axis the media-type schema declares is a way of naming a *part*, and naming the whole through one of them means fabricating a value (`bbox=0,0,1,1` — the same full-region rendering wearing a crop; a bare `el=1` on an artifact whose text lives in un-addressed layout elements). The fabricated value is not merely inelegant: it is a stored claim that a *region* was addressed, which lint then checks against a grammar that cannot see it is false. Absence is checkable, singular, and cannot drift. *(§12.25 named one instance of this — an invented `el=1` on an artifact with no addressable element — and 3.6 closed that instance by making the HTML address space total. The general case is the one here: content that genuinely is the whole artifact, where every part-naming axis is the wrong tool. §12.30.)*

Two rules bound it, so absence stays the whole-transport statement rather than becoming the lazy default:

- **A body-empty positioning marker may never be address-less.** A marker's whole content is *where* (§4.3.2.2); a marker positioning the record's own bytes within the record's own flow states nothing, and there is nothing for a reader to resolve that `corpus://<id>` did not already give them. This holds for the three non-text atoms, for the structural byte-mark (a boundary is a position by definition, §4.3.2.3), and for the placement (which names a member *by* its address, §4.3.2.4).
- **The identity rule is unchanged**, and it does the rest: identity is (`opener-id`, `address`), and an absent address is one value like any other — so a record carries at most one address-less segment per opener-id, and an address-less rendering coexists with `bbox=`-addressed extractions of parts of the same artifact exactly as two addressed segments would.

###### Optional header fields

| Field | Description |
|---|---|
| `perceptual` | An atom-canonical content fingerprint (§7.7) using the `<algo>:<hex>` prefix convention. |
| `speaker` | An integer diarization index identifying who is speaking in this `audio` segment. |

*(3.5)* **`description` and `entry` are both retired from the segment header.** `description` goes with the field everywhere (§4.2.3): a segment cannot narrate its own region. `entry` goes as a **fossil** — it labelled the line a segment contributed to the 1.0–2.x stored table of contents, and that job moved to the structural segment when the TOC became a derived rendering (§4.3.2.3, 3.0); what remained was an authored label with no consumer, sitting on content segments in numbers that dwarfed the byte-mark field it was supposed to be distinct from. Where such a label is genuinely the **source's own** heading or caption text, it was never an authored label at all and belongs on a structural segment as `mark:` — verifiable against the bytes, and picked up by the derived TOC for free. Where it is not in the source, it is the record naming its own structure, and it goes.

The atomic classification, if any, lives on the opener line as `<!--segment <atom>/<id>-->`. A segment carries exactly one atomic class id; when multiple representations apply to the same source region, each becomes its own segment with its own opener (and identity is the `(opener-id, address)` pair).

Segment-scope issues live as standalone issue context blocks in the annotations zone with an `address:` field pointing back to the segment — never inline on segment headers.

###### The four content atoms

- **`text`** — the atom whose segments carry segment bodies, with one exception. Plain prose by default; shaped by a `text/<overlay>` for structured lossless forms. A `text/<overlay>` declaring `enables_lossless: false` is a body-empty marker like the non-text atoms, its overlay id carrying the answer to what the region is.
- **`image`** — a static image at the addressed region. Body-empty positioning marker. Text printed within it extracts as co-addressed `text` segments.
- **`audio`** — an audio range. Body-empty positioning marker. Transcripts live as separate `text` segments at the same address.
- **`video`** — a video stream over the addressed time range. Body-empty positioning marker. Captions and scene transcripts live as separate `text` segments at the same address.

###### Faithfulness

The segment body MUST be a faithful, lossless rendering of the addressed content. Descriptive content — a summary of what an image shows, a paraphrase of what was said, a characterization of what a live or computed region contains — is **lossy** by definition, and *(3.5)* it now has **no home anywhere in a record**: not the body, not a header field, not the annotations zone. Re-segmentation is structural; content within remains faithful.

*(3.5)* **The rule and its consequence.** A record is the faithful representation of its bytes. Where a region cannot be faithfully represented, the record's honest statement is *the bytes are here, at this address, of this type* — a body-empty marker — and the reader resolves them (§6.2). Anything more is the corpus summarizing itself, and summary is exactly the failure mode this discipline exists to prevent: a paraphrase cannot be checked against the bytes the way a transcription can, it is written once and never re-verified, and it is indistinguishable in the record from content that *was* verified. The prior arrangement made this concrete — an image marker's `description` was authored prose sitting in the content zone, competing with the faithful segments beside it, cited by downstream consumers as though it were evidence.

Summary is a **query**, and the query layer is the ledger. Where a reader wants "what does this record contain," the answer is composed from ledger claims that cite the record's verifiable surfaces, each with span-precise evidence that can be re-checked against the bytes and revised when wrong (`ledger.md` §6.3). That is the same information the description was reaching for, held where it can be audited, attributed, and superseded — none of which a sentence in a record header can be.

###### Cross-references in segment bodies

Segment bodies carry **no intra-corpus links**. *(3.4)* A `corpus://` reference stored in a body is a violation: the resolution it names is derivable at read time from the record's own bytes plus its lineage, so storing it duplicates a derivation and can disagree with it. Nothing inside the same transport needs one either — an inline image is its own `image` segment, addressed on the artifact's own axis (§4.3.1.4).

Cross-artifact connection is expressed the way the captured bytes already express it: by the **source URL**, reconciled to intra-corpus references at read time during cross-reference resolution (§12.4.7), never by a stored corpus address.

Segment bodies may carry:

- **Plain markdown URLs** — the links the source itself carries, whether or not their targets are captured. Reconciliation is a derived view's job, not the body's.

*(3.0: the 2.x "Body-draft mode contract" paragraph is deleted with the stage; the stored content zone has exactly one author — the normalize pass — and its total-replacement discipline is stated at §4.4.7.)*

*(3.4: this retires the raw-blake3 wikilink/embed forms `[[<blake3>]]` / `![[<blake3>]]` and the functional-URI forms `[[corpus://…]]` / `![[corpus://…]]` from segment bodies. Both were specified, both were enforced by lint, neither was ever rendered by anything, and no record in either hub ever used them — §12.26. Unaffected: the origin block's lineage `uri: corpus://<container>?<address>` on a promoted record, which is capture **history** and is never consulted for byte lookup, §8.1/§12.15.)*

##### 4.3.2.3 The structural segment

```
<!--segment structural
address: <the MARK's position>
level: <int>
mark: <the mark's own text, verbatim>        # optional — omitted when the mark is unlabeled
-->
```

A **structural segment** is a body-empty mark recording that **the source itself declares a structural boundary** at an address: a heading (`el=<path>`, §6.1.1), an EPUB nav target (`spine=<N>`), a PDF outline entry (`page=<N>`), a media chapter (`time=<tc>`), a chat platform's topic boundary (`turn=<N>`). It carries no content atom, takes no atomic overlay, and never has a body; it contributes nothing to the faithful text rendering (and is excluded from `token_counts.body`, §9.6). Its identity is (`structural`, address), stacking beside content segments at the same address per the standard rule.

***(3.5)* `mark:` — the field's name matches its meaning.** It was `entry:` through 3.4, sharing a name with the content segment's authored leaf label (now retired, §4.3.2.2) while meaning something categorically different: not a label a pass chose, but **the source's own mark text, verbatim** — checkable against the bytes like every other attested fact. The shared name was itself the evidence that the two had been conflated, and the numbers showed which way the confusion ran: at the amendment, 61 structural marks carried the field against 12,936 content segments. Renaming it settles the byte-mark's identity: a value in `mark:` that is not in the source is a violation, not a judgment call.

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
mark: Opening
-->

<!--segment structural
address: time=00:12:31
level: 1
mark: The heist
-->
```

The chapters are the container's byte-marks on the shared timeline; the tracks (promotable, §8.1) inherit them at read time through lineage — a track record never copies marks its own bytes do not carry.

##### 4.3.2.4 The placement segment *(3.8)*

```
<!--segment placement
address: <where the member sits in this transport>
-->
```

A **placement** is a body-empty segment recording that a **member** (§4.3.1.4) sits at this position in the record's reading order. It is the sixth segment kind: no content atom, no atomic overlay, no body, no fields but the address. Its identity is (`placement`, address). It is the exact structural twin of the structural byte-mark (§4.3.2.3) — both carry a position and withhold every claim about content — and the two differ only in what the position is *of*: a mark points at a boundary the source declares, a placement at bytes the roster already names.

**What it withholds is why it exists.** The atom is precisely how a segment declares whether anything is left over (§7.3, `enables_lossless`): an `image` at an address claims *irreducible bytes here*, a lossless `text/<id>` claims *this is what they say*. For a member both claims are about bytes that have their own blake3, their own byte-facts, and — once positioned — their own record. A containing record making either claim is asserting something about content it does not own, in the one place where the assertion cannot be shared: the next record to contain the same member would have to make it again. A placement makes exactly one statement, and it is a statement about *this* record: **member X sits here**.

**The member is named by the address, and the rendering is imported.** A placement stores no reference to the member and no reference to its record. The address it carries appears in exactly one roster row (§4.3.1.4's dedup rule guarantees at most one), that row's `transport:` is the member's blake3, and the blake3 **is** the id of its record (§2) — so *placement → row → hash → leaf record* is a derivation over the record's own bytes, computed by every reader and stored nowhere. A stored `corpus://` pointer here would be the body-link grammar 3.4 retired (§4.3.2.2) and the residence marker §12.26 refuses, for the same reason both were refused: a derivable fact written down is a fact that can disagree with its derivation.

###### Placement means promotion

A member positioned by a placement **must** have a record (§8.1) — that is the rule the kind exists to make statable, and it runs in one direction only. Promotion is not automatic and an **unplaced** member never needs it: the roster is unabridged by design (§4.3.1.4), and a favicon, a spacer gif, or a container member nothing has yet looked at stays a row and nothing more. What forces a record is the act of *placing*, because placing is the record saying this asset is part of how it reads, and the only faithful representation of an asset is one made from the asset's own bytes.

The consequence worth stating plainly is the one that makes the arrangement pay: **one leaf serves every parent.** A member appearing in N records is rendered once. Which fixes the invariant that makes sharing sound — *context is an input to the normalize pass, never to its output.* A parent's context legitimately tells a pass what it is looking at (the lineage origin block supplies it, §8.1); the rendering the pass produces must be faithful to the member's bytes alone. A rendering that depended on which parent asked could not be shared, and the whole arrangement would be a duplication bug wearing a dedup's clothes.

###### A placement displaces the member's content, never the parent's structure

The parent keeps everything that is *about the parent's own bytes* — its headings, its byte-marks, its reading order, its form. What it stops carrying is the member's **content**. The two are easy to conflate when they name the same string, and the case that makes it concrete is common: a page declares `<h3>Refrigerant System Capacities</h3>` and then embeds a generated image of the table, with that same title drawn into the pixels. Both records record it, and neither is a duplicate of the other — the parent's byte-mark records *that the page declares a heading here*, checkable against the page's bytes; the member's caption records *that the table is titled this*, checkable against the image's. Two records, two facts, two sets of bytes that happen to share a string because the producer rendered one label twice. Deleting the parent's mark would leave the page's own declared structure unrecorded, which is what §4.3.2.3 exists to prevent — on such a page it is frequently the only TOC entry there is.

Which settles the converse too: **a member's own title is part of its rendering, not a byte-mark on it.** A byte-mark records structure the source *declares* — a heading element, a nav target, an outline entry, a chapter (§4.3.2.3) — and a title drawn in pixels is *rendered*, not declared; reading it as a heading is an interpretation of layout. It belongs inside the lossless rendering that already interprets that layout, which for a table is the `<caption>` its own grammar provides. A mark would also need a position to point at, and on a record whose rendering is the whole transport there is none to give it without inventing one (§4.3.2.2).

###### Scope: a transport within a transport, never a region of one

The rule reaches exactly the assets that have a roster row, and no others. A **region** of the record's own transport — a rastered PDF page, a `bbox=` crop of a single-image artifact, a video `frame=` — has no member row, no independent blake3, and no leaf to promote to; it stays a content-atom marker with its transcriptions beside it (§4.3.2.2), and nothing here touches it. The distinction is not a convention to remember: it is already exactly the line §4.3.1.4 draws for whether a row exists at all.

A region **of a member** is the case worth stating, because it looks like the exempt one and is not. `el=<path>&bbox=…` chains a crop onto a member's address, so what it renders is the member's pixels — the member's own record is where that rendering belongs, and the address it takes there is the crop alone (the fractions were always relative to the member's extent, so nothing is recomputed). A whole-frame crop (`bbox=0,0,1,1`) is not a region at all — §4.3.2.2 already says so — and takes the whole-transport address, which is to say none.

###### The two demands, at their two grains

A placed member in the wrong state is two different defects, and each lints where it can actually be fixed (§8.5):

- **Placed with no record** is the **parent's** defect — no leaf exists, so nothing else could carry the finding, and the check is cheap: the leaf's path is a pure function of the roster hash, so existence is a stat. It is an **error**: a record positioning bytes it has not promoted has named a rendering that cannot be reached.
- **Promoted but not yet rendered** is not a defect at all — it is **demand**, and it belongs to the leaf. A leaf placed in N parents carries N-fold **normalization pressure**, which is a second source on the same mechanism the ledger's citation discipline already drives (§8.5, `ledger.md` §6.3), so the queue can be ranked by how much of the corpus is waiting on one pass. Nothing gates on it; a leaf standing as its artifact's proxy is a complete record (§4.1).

###### Worked example — three table images in one HTML article

```
<!--members
- address: el=1.2.2.1.3.1.4.1.8.3
  media_type: image/png
  transport: blake3:cefda49d…
  bytes: 63420
- address: el=1.2.2.1.3.1.4.1.14.3
  media_type: image/png
  transport: blake3:010894ee…
  bytes: 51420
-->

<!--section document-->

<!--segment structural
address: el=1.2.2.1.1.1
level: 3
mark: Underhood Fuse Block
-->

<!--segment placement
address: el=1.2.2.1.3.1.4.1.8.3
-->

<!--segment placement
address: el=1.2.2.1.3.1.4.1.14.3
-->
```

and, on the record whose id is `cefda49d…`:

```
<!--artifact image/png-->

<!--origin
uri: corpus://<the article>?el=1.2.2.1.3.1.4.1.8.3
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

*(3.5: narrowed to one job.)* The annotations zone carries exactly one kind of observation: **where this record's representation of its bytes falls short.** One block family, the **context block**, and after 3.5 one namespace — `issue`. Context **never** contributes to the faithful content zone — it is a side-channel that accretes without disturbing the lossless body.

**Why the zone survives the faithfulness rule at all.** A record asserts nothing about itself (§4.3.2.2), and an issue is not an exception to that: it is a statement about the **capture**, not about the content — the same category as the `touch:` chain, an origin block's `source_transport`, or a declared chrome strip. When a marker says *the bytes are here, read them* and the reason is that we tried to render them and could not, that has to be recordable, or unachieved faithfulness becomes invisible. The issue is the **complement** of the body-empty marker: the marker offloads to the bytes, the issue records that the offload was forced. Without it a paywalled page and a fully-transcribed one are indistinguishable in the record, and there is no worklist.

**Context is scarce by design, and now scarce by construction.** Absent a real fidelity problem the annotations zone is **empty** — the normal state for the overwhelming majority of records. It is emphatically **not** a normalizer scratchpad: a normalizer MUST NOT emit commentary, summaries, running notes, or "what I did" prose as context, and *(3.5)* it can no longer do so by accident, because an issue carries **no prose field** (§4.3.3.2).

*(2.0)* The 1.0 interpretive `reference` path — normalizer-found citations in the content — moved to the ledger: a found citation is a `capture`/`search` need or, where the domain cares, a citation edge with span evidence (`ledger.md` §7). The 1.0 `concept` namespace was removed outright (§4.3.3.4). *(3.5: the `reference` and `relation` namespaces follow — §4.3.3.3, §4.3.3.5.)* Content-*meaning* observations of every kind are ledger material; the annotations zone records only what is faithfulness-scoped.

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

Per-id overlays (`context/issue/<id>`) extend with id-specific fields. The `severity`/`resolution` value sets are corpus-local (schema-declared); cross-corpus tooling should treat unknown values gracefully rather than assuming a fixed vocabulary. Issues come from three sources — the **deterministic pipeline** (mechanical detections at capture/ingest: bot blocks, corrupt encoding, missing inputs), the **normalizer** (faithfulness problems found while rendering), and **external** health-signal sweeps — each recorded in `detector` and, where engine-owned, `provenance: auto`.

***(3.5)* An issue is a typed code at an address, and carries no prose.** Its whole payload is `(<namespace>/<id>[/<subtype>], address, severity, resolution, detector)` plus whatever **structured** id-specific fields its overlay declares — a count, a URL, a signature. The `description` field is retired with the field everywhere else: a sentence explaining the problem is the record narrating itself, it cannot be checked against anything, and it is the exact seam through which summary re-enters a zone that already exists to be a side-channel. The type carries the meaning — `partial-content/paywall` at `el=12` needs no gloss — and this is the same obligation §4.3.2.2 puts on atom overlays: an issue id too vague to be self-explanatory is under-specified, and the fix is a **better id**, never a sentence. Where a fidelity problem genuinely warrants explanation at length, it is an interpretation in the ledger, which can cite the record and be revised.

**An issue is not a derivation.** A finding that a read-time pass could recompute from the record and its schemas — *this record's derived title is generic*, *this record carries no form* — is a **health signal** (§12.21), computed on demand, never persisted into records. Storing it makes the record assert a verdict about itself that goes stale the moment either side changes. The test: if a sweep over the corpus could produce the finding from what is already there, it belongs to health; if only the pass that had the artifact open could know it, it belongs here.

##### 4.3.3.3 The `reference` namespace *(removed in 3.5)*

*Retired.* A `reference` block recorded a **declared dependent link** — a product page's manual, a spec sheet — lifted from an origin overlay's `capture.references` declaration and pinned to the link's mention, carrying `attribution_text` (the link text) and `source_url` (the resolved href).

Both halves already had homes, and the block was the seam between them. **The link is content.** An anchor the source renders is part of the page: it belongs in the faithful body as an ordinary markdown URL, which §4.3.2.2 has always permitted ("the links the source itself carries, whether or not their targets are captured"), with `attribution_text` being nothing other than the link's own text. **The edge is a derivation.** Whether that URL names a captured record was already resolved at read time against the URI index (§12.4.7, §9.9) and was never stored. So the block held a copy of body content plus an anchor for a derivation that needs no anchor — and it made a *mechanical* emission out of the normalize pass, which is the wrong stage for something that reads only the artifact.

**The case the block was reaching for is real, and it is a ledger claim.** Where a source refers to something *without* a link — a video host naming a document by voice, ambiguously; a bulletin citing "the applicable service procedure" — there is no URL to render and nothing mechanical to resolve. Resolving that reference to the thing it means is an act of knowledge, and it belongs where knowledge is checkable: a typed claim on the ledger concept, its evidence anchored at the transcript span or the paragraph that makes the reference, reviewable and revisable like every other claim (`ledger.md` §6.3, §7). That is the relational web the ledger exists to be, and a corpus record was never the place to hold one end of it.

##### 4.3.3.4 The `concept` namespace *(removed in 2.0)*

*Retired.* The concept block was the ledger's shadow: a per-record entity annotation resolved against an external knowledge base (Wikipedia/Wikidata), built because no internal entity layer existed — its `concept:` id was "the join key by which records that invoke the same concept are related without either knowing about the other," which is precisely what a ledger **concept** is (`ledger.md` §4 — the namespace's very name graduated with it). The ledger replaces every part of it: record-scope *aboutness* is coverage and the artifact roster (`ledger.md` §9, §4.2); a span-scoped *mention* is claim evidence anchored by a functional URI; the external join key (`wikidata:Q…`) is a concept-level external-identity claim citing a mirrored reference dataset (`ledger.md` §6.5), made once, not stamped per record. The local-KB machinery (1.0 §12.12) retires with it.

##### 4.3.3.5 The `relation` namespace *(removed in 3.5)*

*Retired, and it is the retirement that motivated the amendment.* A `relation` block recorded a **source-declared cross-link** — a "related information" rail, sibling-page links — lifted per host from an origin overlay and stored as `target_text`/`target_url` at the rail's address.

The block existed because a host overlay had judged the rail "navigation, not content" and dropped it from the body, then judged it too valuable to lose and built a side-channel to keep it. Both judgments were right about the rail and wrong about the conclusion: **the rail is content of a different form.** It is an index — an entry set whose value is the entries and their targets, which is precisely `form/index` (§7.8) — sitting inside a document. Before 3.5 a record could hold only one form, so a page that was an article *and* an index had nowhere to put the second half; the annotations zone absorbed it, and 77,310 links across 4,995 public records ended up outside the faithful body while sitting plainly inside the artifact's bytes.

Lifting the whole-record section's sibling prohibition (§4.3.2.1) removes the reason. A trailing `<!--section index-->` over the rail's span renders those links as what they are: faithful body content, in the source's own order, with the source's own labels, addressed on the artifact's own axis, and citable. Nothing is lifted, nothing is stored twice, and the cross-record edge remains what it always was — a read-time resolution of the URL (§12.4.7), self-healing as targets are captured or removed. **Trailing** is the ordering rule, not a preference (§4.3.2.1): the rail is the page's frame, not its subject. And the rail is rarely the only such region — a page that carries one usually carries a breadcrumb too, and the two are one entry set under one shape, so they take **one** index span whose segments render each region at its own address, in source order within the span. The span's envelope is then the ordered address list its children derive (§6.1.1) — the honest form for a claim over disjoint regions, and the one that cannot overlap the content span beside it.

**The general rule this leaves behind.** When content is present in the bytes and worth keeping, the answer is never a side-channel: it is a **span under the form that fits it**. If no form fits, the content is formless segments, which is also fine (§7.8's zeroth form). A record needing a place to put content that is *not* content is a record that has mis-classified something.

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

Classifications attach at three structural scopes — record, section (span), and segment — plus the **member**, where the media-type axis attaches via each member row's `media_type`:

| Axis | Record | Section (span) | Segment | Member |
|---|---|---|---|---|
| media-type | ✓ (artifact MIME) | — | — | ✓ (per-member `media_type`) |
| origin | ✓ (origin block) | — | — | — |
| form | ✓ (a whole-record section) | ✓ (a span section) | — | — |
| atomic | — | — | ✓ (segment opener) | — |

#### 4.4.3 Section scope *(dissolved in 2.0)*

*Retired.* The 1.0 section-scope composite (a passage's identity — "this section is a recipe") and the further-deferred identity+role dual-composite citation model (borrowed material carrying both what it is and what it does in the host) are both expressed as **ledger claims over section spans**: span-precise evidence URIs make "what this passage is" and "what this passage does here" two claims about one anchor, with no record-side mechanism at all. Nothing remains at this layer.

*(3.0 note.)* What returns to section scope in 3.0 is the **form axis** (§4.4.1) — a structural-shape judgment, checkable against the bytes, binding a `form/` overlay on the section opener. What this tombstone retired — a passage's *meaning*, its identity and role as domain knowledge — stays retired: it remains a ledger claim over the span, and no form overlay may carry it (§7.8).

#### 4.4.4 Scope-driven fidelity *(removed in 2.0)*

*Retired with the composite namespace.* The three field groups (descriptive / structural / citation) organized composite extended fields by scope; composite fields are now claim values and qualifiers in the ledger. The citation field group's survivor was the mechanical reference block's ladder (§4.4.5), itself retired in 3.5 (§4.3.3.3).

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
| **attested** *(3.0)* | ingest-stamped byte-facts: artifact-block fields, manifest members, structural byte-marks whose address family the mime schema's `attest:` declares (§4.3.2.3), sidecar-lifted origin fields | re-attested (stripped + regenerated) by re-ingest / re-attest (§8.3) |
| **auto** | a context block with `provenance: auto` — a detector or overlay-declared emission (emitted at normalize — §4.3.3.3, §4.3.3.5) | stripped + regenerated from the current overlays by a re-run of the owning pass (re-normalize) |
| **asserted** | a context block with no `provenance` — human / normalizer (faithfulness issues) | never touched |

A **form section** is stamped by one of two paths, both recorded in the touch chain: **declared** — the record's origin overlay declares its form (§7.2), and the shaper stamps + conforms the span mechanically on the normalize pass (regenerated on re-shape); or **asserted** — an interpretive pass recognizes the shape on a record whose origin is generic, and the pass's model identifier is in the chain (§4.2.2). Recognition may come from any layer — a ledger scribe reading cross-corpus is exactly who will spot that some old PDF is really a transcript — but the record mutation always goes through the corpus normalize pass and its lint gate (a worklist entry, then a re-normalize dispatch); scribes author knowledge, normalizers author faithful form. A wrong assertion fails form-coherence lint immediately (§4.3.2.1); a wrong-but-lint-passing one is corrected by a later asserted pass, auditable in the chain.

*(2.0: the 1.0 ladder's classify-block rows — `classify_when` auto-membership and asserted composites — moved to the ledger; deterministic membership is now a harvest rule with the same auto/asserted discipline at the claim level, `ledger.md` §10.)*

#### 4.4.7 Re-run lifetime

Metadata-, content-, and annotations-zone material persists across re-runs **unless the pass that owns it is itself re-run**. 3.0 has exactly two owning passes:

- **Ingest / promote own the attested layer** — the artifact block's fields, manifest members, structural byte-marks, sidecar-lifted origin fields, origin stamping. A **re-attest** (§8.3) strips and regenerates them from the current schemas; it never touches the authored layer.
- **Normalize owns the authored layer** — the stored content zone (total replacement per pass: shaper or agent, same discipline the 2.x body-draft contract stated), the form span's declared fields, and asserted faithfulness issues. A re-normalize refreshes it; it never touches attested facts except to *read* them. *(3.5: descriptions and editorial header fields are retired, so the authored layer is now faithful renderings, form declarations, and typed fidelity issues — nothing interpretive.)*

`provenance: auto` context blocks belong to whichever pass's overlay declared them and regenerate with it; asserted context blocks are never auto-touched. The 2.x three-way dance — re-draft wiping normalize work, normalize partially surviving re-draft (§4.4.7/2.x) — dissolves with the stage: there is nothing between the attested facts and the authored form. To deliberately reset everything, `re-stub` (§8.4).

---

## 5. URIs and references

### 5.1 URI forms

Two URI forms appear within the corpus:

- **Plain URLs** — the source's own links, carried verbatim in segment bodies whether or not their targets are captured. Reconciliation to intra-corpus references is a derived view (§12.4.7), never a stored rewrite.
- **Functional URIs** — `corpus://<hash>[?<params>]` — composable references resolved to derived views (§6). They are the **read-time** address language: tooling, ledger evidence, and agent instructions name surfaces with them. *(3.4: they are never stored in a record's content zone, §4.3.2.2. The one place a `corpus://` string is persisted is a promoted record's origin lineage `uri:`, which is history, not a lookup route — §8.1, §12.15.)*

*(3.4: the raw-blake3 wikilink/embed forms `[[<blake3>|link text]]` / `![[<blake3>]]` are retired — specified, linted, rendered by nothing, and used by no record in either hub. §12.26.)*

### 5.2 Re-capture

If the same bytes are encountered again, the record's identity is unchanged. The capture URL may differ across encounters, so origin blocks are append-only: each re-encounter checks the canonicalized capture URL against existing origin blocks' `uri:` entries and either appends to an existing origin's `uri:` list (when the new URL aliases an existing origin via known shortlink/redirect rules) or emits a new origin block (when it's genuinely a separate source). A re-dropped local file (a uri-less origin) dedups by `filename` instead of a URL — the same bytes under the same name append no duplicate origin, while the same bytes under a *different* name record a distinct local source (its own origin).

If a URL re-fetched later yields different bytes, the new content produces a different hash and therefore a different record.

### 5.3 Referencing a region in another record

A functional URI addresses a **region** of a record — encode the address in its query string:

```
corpus://<hash>?<address-keys>
```

The form serves read-time reference — tooling, ledger evidence, agent instruction — and is never stored in a record's content zone *(3.4, §4.3.2.2)*. It carries the **address only**, so it resolves to the region (and the asset or derived view at it), not to one specific representation: where same-region stacking places several segments at one address (a segment's in-record identity is `(opener-id, address)`, §4.3.2.2), those representations are distinguished only within the record, not by a cross-record reference.

---

## 6. Functional URIs

### 6.1 Grammar

```
corpus://<hash>[?<params>]
```

- `<hash>` — blake3 hash of the source artifact, 64-char lowercase hex.
- `<params>` — `&`-separated key/value pairs and flag-style keys. Order is significant — parameters compose left-to-right, each operating on the previous step's output. A param **value** percent-encodes the query-reserved characters `%`/`&`/`#` as `%25`/`%26`/`%23`; the parser decodes, and canonicalization re-encodes. Values may therefore carry any character — archive member names are producer-controlled (`?path=…D%26D 5e….json` addresses a member literally named `…D&D 5e….json`). *(2.1: the encode contract existed from the start; the decode side is normative as of 2026-07-12.)*

Bare `corpus://<hash>` resolves to the source artifact's bytes. `corpus://<hash>?<params>` resolves to a derived view per §6.2.

#### 6.1.1 The `el=` path — the HTML address space *(3.6)*

`el=<path>` names an element in a markup artifact by its **child-index path**: dot-separated 1-based positions among element siblings, walked from the artifact's body. `el=1` is the body's first element child; `el=1.3.2` is that element's third element child's second. Text nodes, comments, and attributes are not counted — only elements.

**The space is total.** *Every* element is addressable. There is no predicate deciding which tags may be named, and this is the amendment's substance rather than a convenience: any such predicate is a **versioned contract that records do not record**. Adding one tag to a whitelist silently re-points every stored address that crosses an instance of it, with nothing in the record to say which version produced it and no gate able to detect the difference (§12.28 measures the one that already happened). A total space cannot be revised, so it cannot rot.

**What a drafter emits is a separate question.** Which elements get their own segment is an authoring heuristic owned by the drafter and the form contracts — it may change in any release, add or drop element kinds freely, and none of that changes what an existing address *means*. Splitting the two is what buys permanence: the space is mechanical and frozen; the taste is free.

**Relation is legible from the address.**

- **Containment** — `A` contains `B` iff `A` is a component-wise prefix of `B` (`el=1.3` contains `el=1.3.2`; it does not contain `el=1.30`). No artifact access.
- **Order and siblinghood** — component-wise **numeric** comparison, so `el=1.10` follows `el=1.9`. A lexical string sort is wrong here and is the obvious implementation trap.
- **A subtree is one address.** The container's own path names it and everything under it, exactly. An envelope therefore cannot over-claim content it does not hold — the failure mode a min–max integer range could not even express, let alone prevent.

**Ranges.** Three forms, in order of preference:

| form | meaning |
|---|---|
| `el=1.3` | the element **and its whole subtree** — the common case, and free |
| `el=1.3.[2-9]` | **sibling range**: children 2 through 9 of `el=1.3`, inclusive, and their subtrees |
| `[el=1.3.2, el=1.7, el=2.1]` | an ordered **list** — a region crossing subtree boundaries |

The sibling range is the only new syntax; brackets cannot collide with the path grammar, which is digits and dots. The list is the existing multi-region address form (§4.3.2.2) and needs nothing new. A span that crosses subtree boundaries **must** use the list: there is deliberately no way to write a flat "from here to there" that cuts across structure, because such a region is not one structural thing and the old `el=<N>-<M>` form's ability to say so was how over-claiming envelopes arose.

**Two attested facts keep drift loud.** The path is a function of the *parsed* tree, so the parse is part of the contract. The artifact block carries the **parser identity** the addresses were computed under and the total **element count** (§7.1). A resolver whose parse yields a different count knows immediately that it disagrees, and says so — instead of silently resolving a path to the wrong element, which is precisely the failure this amendment exists to end.

*(An optional record-level `address_prefix` — a declared common ancestor, shortening every address in a record — is deliberately **not** specified. Measurement found no heuristic-free definition that pays: the longest common prefix over all elements is empty on 399 of 400 sampled artifacts, and so is a single-child descent from body, because a body always carries stray siblings. The only workable definition is a per-host content selector, which trades address length for a config dependency on the exact axis this amendment is removing one from. It stays deferrable at no cost: absent means absolute, so the field can be added later without re-pointing a single existing address.)*

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
| `bbox=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Crop a relative region (image: floats in `[0.0, 1.0]`, origin top-left) or narrow a worksheet (spreadsheet: an A1 range, e.g. `bbox=B2:G30`). Polymorphic — see below. The 3rd and 4th values are a **width and a height, not a second corner**: `x+w` and `y+h` must each be ≤ 1. A stored region-op value that breaks this grammar is a lint ERROR (`address-region-invalid`) — the region grammar had been enforced only at render time, so an address nobody resolved could carry pixel values or corner coordinates and pass every gate (§12.24). |
| `crop=<x>,<y>,<w>,<h>` | image / spreadsheet | image / cell-range | Alias for `bbox` (inherits its polymorphism). |
| `mark=<x>,<y>,<w>,<h>[;…]` | image | image | Outline the region(s) on the **whole** image (does not crop) — the inspection dual of `crop`, showing where a region sits in context. Relative floats in `[0.0, 1.0]`; `;`-separated for multiple regions. |
| `cover=<x>,<y>,<w>,<h>[;…]` | image | image | Paint the region(s) **out**, filled with the background colour sampled from the ring just outside each box (never assumed white). The chrome remover, for captures that baked a viewer's own controls into the artifact: a crop only removes them when nothing real shares their x-range, which on a wide drawing the sheet's own labels usually do at another height. Does not crop — chain `crop=`/`bbox=` after it when a crop is also wanted. Lossy by nature (it deletes pixels), and disclosed by riding the address: the same surface resolves without the op to show what was removed. Same grammar as `mark=`. |
| `resize=<W>x<H>` | image | image | Resize to absolute pixel dimensions (forces both, may distort or enlarge). |
| `fit=<W>x<H>` \| `fit=<preset>` | image | image | Downscale to fit within a bounding box, aspect-preserving; reduce-only (never enlarges). A `<preset>` names an implementation-defined budget. |
| `rotate=<90\|180\|270>` | image | image | Rotate clockwise by a quarter turn (lossless; 90/270 swap width and height). |
| `auto_orient` | image | image | Apply the image's EXIF orientation tag so a sideways/flipped capture displays upright. No-op when absent. |
| `autocontrast` | image | image | Stretch the per-channel histogram to full range (legibility for faint scans). |
| `contrast=<factor>` | image | image | Scale contrast by a float factor (`1.0` unchanged). |
| `grayscale` | image | image | Convert to single-channel grayscale. |
| `dpi=<N>` | (render config) | (config) | Rasterization DPI for `page=<N>`. Position-independent. Default 200. |
| `body` *(3.0)* | any | markdown | The record's **derived body** — the faithful mechanical rendering the 2.x draft stage stored: DOM→markdown under the overlay's capture-time chrome config (HTML), spine text (EPUB), reply-text trim (eml), verbatim passthrough (JSON, plain text), page markers (PDF). A pure function of (artifact × schemas × op version); what `corpus body` prints for a stub. |
| `members` *(3.0; 3.4)* | any transport with embedded assets | json | Member enumeration over every address axis (`el`/`spine`/`path`/`msg`/`part`/`card`/`stream_id`/…) — the roster **with its full descriptors**, derived. Beyond the stored row's four keys (§4.3.1.4) it carries every mechanically-readable per-member fact: pixel dimensions, verbatim `alt`, member filename, an email member's `from`/`subject`/`date`, a vCard's display name. *(3.4: this op is where those descriptors live now that the stored roster is a four-key index. It is the surface a normalize pass consults to see what an artifact carries — never the block, which by design says less.)* |
| `transcribe` *(3.0)* | audio / audio stream | json/text | Speech-to-text over the addressed audio, with timestamps and speaker-turn indexes where determinable. **Version-labeled** (§6.4): the result carries engine + model version. |
| `turn=<N>` *(3.0)* | turn-structured record | json/text | The verbatim N-th unit of the record's declared unit array (1-indexed), located by the origin overlay's form mapping (§7.2) — for a chat transcript, the complete message object: reactions, edit history, attachment declarations, platform ids, one hop away from the envelope segments. |
| `turn=<N>&att=<M>` *(3.0)* | turn-structured record | bytes | The M-th attachment declared by unit N, materialized through **lineage-chained resolution** (below). |
| `cut=precise\|copy` *(3.0)* | (cut config) | (config) | Cut semantics for `time_range=` (the muxing contract): `precise` (default — frame-accurate, re-encodes) or `copy` (keyframe-snapped stream copy, disclosed). Position-independent, like `dpi=`. |
| `format=<token>` *(3.0)* | media / image | converted rendering | Output-format conversion, composing **after** selection and cutting (the muxing contract): `time_range=12:04-12:09&format=gif`. Changes encoding only, never the addressed content. |
| `scenes=<threshold>` *(3.1)* | video / stream | boundary proposals | Scene-cut boundary proposals over the video timeline — a text listing of cut timestamps at the stated detection threshold, engine-versioned (§6.4). Normalizer support for boundary work (`form/slide-deck`, §12.20): proposals to be verified by the pass, never marks. |

A parameter applied to an incompatible working type is a hard error.

A PDF `page=<N>` is a **page selector**, not an unconditional render: a per-page op after it (`render`, `text`, `words`, `probe`) reads the *selected page* directly, so `page=<N>&text` returns the page's embedded text layer rather than an OCR of its render. A terminal `page=<N>` (and any image op or `bbox=` after it) renders the page to an image, so an `address: page=<N>` image marker (§4.3.2.2) still resolves to the page bytes. The whole-document ops `probe` and `outline` operate on the PDF itself (no page selected). These introspection ops are how a normalizer determines a PDF's shape and extracts its content — the attestation itself is uniform (§11).

`fit=` presets are **implementation-defined**, not enumerated here: a preset (e.g. `llm`) bounds the result to a consumer's budget — typically a vision model's maximum input dimensions and pixel count — and those limits are model-dependent and drift over time, so freezing them into the spec would rot. The normative contract is only that `fit=` downscales aspect-preserving and never enlarges; the concrete bounds of any named preset live in the resolver implementation.

Parameter value grammar may be media-type-dependent; the resolver dispatches on the source artifact's type. In particular `bbox` is **polymorphic** — relative floats in `[0.0, 1.0]` when cropping a rendered image (an image artifact, or a `page=` render of a PDF), and a spreadsheet cell range (e.g. `bbox=B2:G30`) when narrowing a worksheet region — so the same token does not collide across media types. Pure **address selectors** that locate a region without transforming it — `sheet=<name>`, `el=<path>` (§6.1.1), and any others — are defined by each media-type schema (§4.3.2) and are not enumerated here; §6.2 lists only the parameters that produce a derived view.

**The muxing contract** *(3.0)*. Media cutting, muxing, and conversion are resolver ops with normatively pinned *behavior* and implementation-owned *mechanics* — the contract maps onto ffmpeg's primitives, and exactly as with `fit=` presets, the supported codec/format sets are implementation-defined so the spec doesn't rot; only the behavior below is normative.

- **Composition cut.** `time_range=<s>-<e>` on a media **container** materializes a cut of the *composition*: default-member resolution (below) applied **per kind** — the unique-or-declared-primary video member plus the unique-or-declared-primary audio member — muxed into the source's container family. A kind with **zero** members is omitted from the composition — absence is not ambiguity (a silent video cuts video-only; an audio-only container cuts audio-only). Ambiguity within a *present* kind (two audio tracks, no declared primary) → the bare op fails stating it, never guesses. Subtitle tracks never ride implicitly — opt-in by selection.
- **Stream selection composes.** `stream_id=<id>&time_range=<s>-<e>` cuts one stream; an explicit subset is a comma list — `stream_id=0,2&time_range=…` (the repeated-`-map` analogue) — cutting exactly the named members, muxed.
- **Multi-cut.** `time_range=a-b,c-d` — the address grammar's existing ordered-list-for-non-contiguous-spans convention (§12.11), now materialized: the cuts concatenate in listed order. Concatenation is safe by construction — every cut shares the source's codec parameters. This is the composition layer's supercut primitive: one URI names an ordered excerpt reel of one source.
- **Cut semantics, ffmpeg-honest.** The default is **precise** — frame-accurate, which re-encodes: evidence is the primary consumer, and a cited 5-second clip must contain *exactly* the cited span. `cut=copy` is the disclosed fast path — keyframe-snapped stream copy, whose bounds may widen to the previous keyframe; the URI says so, so nothing silently drifts.
- **Format conversion.** `format=<token>` converts the working result's encoding, composing after selection and cutting (`time_range=12:04-12:09&format=gif` on an MKV → cut, then convert). Rules: (a) conversion changes **only the encoding, never the addressed content**; (b) targets must be **atom-compatible** — video→`gif` is a video-to-animated-image rendering (audio dropped by the format's nature, not by editorial choice), audio→`wav`/`mp3` is fine, audio→`png` is a hard error; (c) the supported token set is implementation-defined per the resolver's engine (the `fit=` precedent) — the contract is behavioral; (d) `format=` names *explicitly* what existing ops already do implicitly — a terminal `frame=` renders to an image, a terminal `page=` rasterizes, transcription extracts audio to an intermediate wav — one parameterized surface for the same idea.
- **Canonical application order**, pinned so one URI is deterministic and composable: **select → cut → convert → size** (`stream_id=` → `time_range=` → `format=` → `fit=`). A downscaled gif snippet of one stream is a single composable URI.

Cuts, muxes, and conversions are **version-labeled ops** (§6.4): encoder output drifts across engine versions, so results are cache-keyed by engine version and pure per version. They are ephemeral derived renderings with exactly the standing of a `page=` raster — never new artifacts, never new records.

**Lineage-chained resolution** *(3.0)*. A promoted record's resolver MAY chain through the record's own containment-lineage origin block (`uri: corpus://<container>?…`, §8.1) to materialize content its bytes *declare* but do not *contain*: read the declared reference from the record's own artifact (message N's attachment path), then resolve it as a member of the blake3-pinned parent container. The chain is derived at read time from (lineage block × record bytes) — never stored on any block — so it cannot rot: the parent is content-addressed and immutable, and an absent member (a reference the export never localized) fails loudly at resolve and surfaces in health, exactly the failure mode a stored pointer would have papered over. This is the transcript analogue of an HTML page's captured assets, with the container playing the role of the capture's asset store; it is also how a promoted track record inherits its container's chapter marks (§1.2) — reading up the lineage rather than copying down. *(Note: lineage-chained resolution is a resolver read of corpus state, which resolve has always been — §6.3; the byte-lookup independence rule of §12.9 is untouched: lineage is consulted for declared-reference chasing, never for the record's own byte residence.)*

**Default-member resolution** *(3.0)*. When an op requires a member of a given kind and the container holds **exactly one** of that kind — or the container itself **declares a primary** (HEIF's `pitm` primary-item box: a byte-fact, attested) — the member selector may be omitted and the op routes through transparently: `bbox=` on a Live Photo acts on the declared-primary still; `time_range=` reaches its motion component; `?transcribe` on a single-audio-track MKV needs no `stream_id=`. Zero candidates, or more than one with no declared primary → the bare op **fails stating the ambiguity** — it never guesses. Two properties are pinned. First, it is **read-side sugar only**: attested member rows always carry their explicit `stream_id=`/`item=` addresses, and nothing stored depends on the sugar existing. Second, it is **citation-safe by content-addressing**: the artifact is immutable, so whether a bare anchor is unambiguous is a *permanent fact of the bytes* — a citation that resolved once resolves forever, never invalidated by later state. (This is also why a single-track media container keeps `disposition: manifest` rather than flipping per record — the bare op is already transparent; §1.2.)

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
  - `disposition:` — `manifest` | `work` (default `work`): the **container-vs-transport judgment** (§1.2), declared per format because it is not derivable from the bytes. `manifest` — the members ARE the content: every member attests as a manifest member (promotable), the content zone holds only container byte-marks. `work` — one transport whose content decomposes as units; internal member files the schema names attest as **exposable members** — addressable and promotable without being the content: a PDF's embedded files / portfolio members (the `attachment=<N>` axis, §12.11), OOXML embedded media and OLE objects. The authoring criterion is normative: *are the members independently meaningful transports?* An MKV audio track is (the transcript lives on it); `word/document.xml` is not. EPUB's 2.x `self_contained` wording is this key's ancestor (`disposition: work`). An origin overlay MAY override for a deviant producer (§7.2); the resolved disposition is always auditable from the record's attested shape, never sniffed per record. *(Distinct from the 2.1-removed `artifact_kind`, whose tombstone stands: nothing explodes at ingest under either value.)*
  - `attest:` — the **ingest attestations**: which byte-facts ingest stamps at ingest time. Artifact-block fields (a PDF's `/Info`, an EPUB's Dublin Core, an eml's headers); **manifest members** for `disposition: manifest` types (archive members at `path=`, mail messages at `msg=`, cards at `card=`, calendar entries at `entry=`, MIME parts at `part=`, media tracks at `stream_id=`, image items at `item=`); **exposable members** for `work` types that declare them; **structural byte-marks** (a media container's chapters); sidecar lift (§7.2). Attestations are deterministic byte-facts — the theme's "attested" half — and re-attest regenerates them (§8.3).
  - `derive:` — the **derivation ops** the type exposes (§6.2), with any per-type config (the 2.x `draft.manifest` config becomes the `members` op's config; a strategy-named general implementation may serve many schemas exactly as `zip-manifest` did).

  The concrete YAML key surgery (which 2.x keys alias, which hard-retire) is implementation-guide material (§12.4); a schema still declaring `mode`/`draft.*` is read tolerantly and ignored.
- *(2.1: `artifact_kind` removed.)* Every transport is self-contained (§1.2); a raw archive is attested as a members roster (§12.4) and its members are reachable by promotion (§8.1). A schema still declaring the field is ignored (tolerant parsing).
- `address_scheme` — the parameters the schema expects in segment `address:` values.
- `addressing` (optional) *(3.6)* — for a format whose address space is a **parsed tree**, the parse the addresses were computed under. `parser` names the pinned implementation (the HTML family: the stdlib-backed `html.parser` tree BeautifulSoup builds — error recovery and implied-tag insertion differ between parsers, so the choice is part of the contract, not an implementation detail). At attestation the resolved parser identity and the artifact's total **element count** are stamped onto the artifact block as attested facts. The count is the cheap self-check the old whitelist could not have: a consumer whose parse yields a different number knows its tree disagrees and reports that, rather than resolving `el=1.3.2` to whatever its own walk happens to reach (§6.1.1).
- `extended_fields` — fields the matching artifact block carries, each with type and optional `semantic_type` tag. *(3.2)* A declaration may carry `role: title` / `role: description`, marking the field as an editorial candidate for the record's derived title/description (§4.2.3) — the artifact layer's contribution, weakest in the precedence. The artifact block holds only facts about the **primary-artifact bytes** (e.g. ffprobe codec / dimensions / streams); source metadata from a capturer's enrichment sidecar does NOT live here — see `sidecar`. Vendor/domain identity (what a bundle *is*, beyond its bytes) does NOT live here either — that is knowledge, asserted in the ledger as roster entries and claims citing the record, minted mechanically by a harvest rule keyed on the kept-whole MIME (`ledger.md` §10).
- `sidecar` (optional) — for an artifact type a capturer enriches with a companion metadata sidecar (e.g. a yt-dlp `.info.json`), declares what is lifted and where. `source` names the sidecar (e.g. `ytdlp-info-json`); `ytdlp_keys` lists the info.json keys copied — each into the **origin block** as a flat `ytdlp_<key>` field (§7.2), the mapping the sidecar-lift attestation applies. The sidecar is companion metadata staged in `capture/<hash>.<suffix>`, consumed at ingest attestation (§8.1), then **deleted** — never persisted to `artifacts/` (only the artifact carries the `<hash>` name there). It is *non-primary-source* metadata, so nothing from it goes to the artifact block, the body, or the frontmatter `description`.
- `transport_algos` — additional byte-hash algorithms to compute beyond the primary blake3 `id`.
- `canonical_strategy` (optional) — procedure for computing the record's `canonical` hash. Names a canonicalization-algorithm id and the canonicalization steps performed before hashing. The canonicalization MAY be scoped to a **content region** — hashing only the article-content text and excluding per-page framing (title, breadcrumb, entry-specific headings) — so two records holding the same content reached by different URLs share a `canonical` and collapse to one record (the duplicate's URL folded into the original). The content-region selector is host-specific and supplied by the origin overlay (not this schema); when it matches nothing the canonicalization falls back to the whole document. *(3.0: whether the value computes at ingest attestation or as a derivation op is an open question — §12.18.)*
  - **Status — retired (3.5); previously disabled 2026-06-28.** The frontmatter `canonical:` field is removed (§4.2.1) and the strategy computes nothing. The 2026-06-28 disable stopped *persisting* the value after `blake3-canonical-pdf` was found to hash only per-page extracted text — so every text-empty (scanned) PDF canonicalized identically and unrelated scans were being silently merged, the duplicate's bytes discarded. What the disable did not do was **sweep**, and the spec then asserted as fact that "no record carries `canonical:`" while 7,210 records did, surviving every re-attestation because the strip touches the body and not the frontmatter. Two years of a field nothing writes, nothing reads, and no strategy serves is not a paused feature; it is stale state that reads as live, and the honest move is to remove it and let a working strategy re-earn the field. Re-introduction requires what was always missing: a canonicalization that distinguishes a scanned page from an empty one, and a settled shape for the **HTML** population that carried 7,132 of those values with no defined content region at all.
- `normalization.guidance` (optional) — prose guidance for the normalizer.
- `form:` *(3.3)* — `{id: passthrough}` (or another **terminal** contract id, §7.8): the format's terminal-contract default — the class judgment that these bytes are their own terminal rendering. Mime-level `form:` admits terminal contracts ONLY (a rendering contract is producer knowledge and rides the origin overlay's `form:`, §7.2, which also overrides this default either way). Redundant for `disposition: manifest` formats — the disposition already derives `form/manifest` (§7.8) — so the key's real population is passthrough defaults on `work`-disposition formats: stills, raw streams, code, datasets, binaries.

### 7.2 The origin namespace

An `origin` schema declares an overlay for one source of retrieval.

- `kind: interpretive` — origin overlays are always interpretive (the match cue may be mechanical, but body guidance is consumed by the LLM normalize pass).

An origin overlay's `normalization.guidance` is **body-shaping tactics** — how to render this source's content faithfully — and, with subtypes (`origin/<id>/<subtype>`), it is the home for **per-page-shape** guidance within a host (how a procedure page vs. an index page of the same site normalizes). *(2.0: this guidance role was previously split with composite overlays; the domain-semantic half of composite guidance moved to ledger per-type conventions, the body-shaping half lands here.)* *(3.0: the guidance narrows accordingly — origin-specific tactics and provenance notes only; the decomposition contract lives on the form overlay (§7.8), stated once for every origin that maps onto it.)*

*(3.5, stated 2026-07-27)* One judgment the origin overlay owns outright: **which of a page's index-like regions belong in the record at all.** The same shape carries opposite weight on different templates — a link list is the entire content of a category-selector page and disposable furniture on the same host's article page; a breadcrumb is the page's own statement of what it covers on one site and a decorative echo of the URL on another. No corpus-wide rule can decide that, because the markup is identical in both cases and only the publisher's own layout says which is which. So the overlay **names the regions its records render**, and a region it does not name is chrome the body omits — the judgment is stated once per host, in the open, and is revisable, rather than being re-derived per record by whoever normalizes it. This is the boundary the strip declarations draw at capture time (§12.3.13), one stage later and at content grain: the strip decides what is in the **bytes**, the guidance decides what is in the **body**. A named region that is genuinely the page's frame rather than its subject lands in a trailing span under §4.3.2.1's ordering rule.

*(3.3, first exercised)* A subtype's overlay MAY be a **file of its own** — `schema/origin/<id>/<subtype>.yaml` — carrying everything an id-level overlay carries: `extended_fields`, `editorial` templates (§4.2.3), strip declarations (§12.3.13), `normalization.guidance`, not merely subtype-scoped guidance prose. Block-side resolution is a **ladder, not a merge**: on a subtype-qualified opener, the subtype overlay is consulted first and the id overlay is the fallback — per concern, the first of the two that actually declares something wins (the walk §12.3.13 exercises, at the grain this grammar already owns). A producer-declared stamp may itself be subtype-qualified exactly as a bare id is stamped, above: a capture sidecar's `origin_schema:` field may read `<id>/<subtype>`, so the compound opener `<!--origin <id>/<subtype>-->` stamps directly, with no separate mechanism.
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

Two producer-export origins ride this uri-less, producer-declared path today. **`imessage-export`** binds a self-contained conversation HTML with attachments inlined. **`claude-code-session`** binds a captured Claude Code session — its `<id>.jsonl` transcript plus the sidecar tree of sub-agent transcripts, tool-result payloads, and workflow state — bundled into ONE deterministic zip by `corpus session capture` (§12.8) and carrying the session's identity as structured fields (`session_id`, `host`, `record_count`, …) rather than a synthetic URI. A session's record is a `zip-manifest` whose members are directly-addressed `path=<member>` rows (the transcript is a transport resolved verbatim, never transcribed), and successive captures of a growing session are distinct records reconciled by continuity-gated supersession (§12.8), not by a stable id.

The universal `origin` overlay declares the fields every origin block carries. `snapshot:` is always present; an origin carries **either** a retrieval `uri:` **or** local-file metadata:

- `uri` (optional) — string or list-of-strings; the URI(s) by which the origin was reached. Present for a *retrieval* origin (a web capture, a synthetic-scheme source like `imessage://`). **Omitted** for a dropped-in local file: the staging path the bytes sat at is unlinked at ingest, so a `file://` path would be a reference dead on arrival — there is nothing to re-fetch.
- `snapshot` — ISO-8601 timestamp of observation (when the corpus saw this origin).
- `filename` / `source_modified` (local-file origins) — the dropped file's basename and its mtime (ISO-8601, `semantic_type: timestamp`, so it aggregates into the `timeline` view). These carry the durable provenance a `file://` path could not. A local-file origin omits `uri:` and carries these instead; an origin with neither a `uri:` nor local-file metadata is malformed.

**Directory layout — namespaced by URI scheme family.** Origin overlays live under `schema/origin/<scheme-family>/<id>.yaml`, grouped by the URI scheme they are retrieved over so each family can carry its own match semantics. The `web` family (http/https) is keyed by host — `origin/web/<host>.yaml`, matched by `applies_to.host_pattern` — while `otherwise/` is the catch-all for un-namespaced schemes and other families (`urn/`, `file/`, `s3/`) get their own sub-namespace and match predicate as a corpus needs them. The universal `origin/origin.yaml` sits at the namespace root and layers into every overlay. The overlay **id is the bare `<id>`** (e.g. `youtube.com`) regardless of sub-namespace, so the `<!--origin youtube.com-->` opener and the `origin/youtube.com` classification are independent of where the file lives. `corpus init` seeds `origin/origin.yaml` + `origin/web/example.com.yaml`; the flat `origin/<id>.yaml` layout is still read for back-compat.

This bare-id doctrine is scoped to the **scheme-family** directories above — `web/`, `otherwise/`, and any future declared family — which are purely organizational: they group by retrieval scheme, never by producer hierarchy, so nesting a host file one level deeper changes nothing about its id. Any OTHER directory under `origin/` is instead a **producer id**, and the grammar is structural, not organizational: `schema/origin/google-takeout/gmail.yaml` is the subtype overlay `google-takeout/gmail` (id `google-takeout`, subtype `gmail`), never a bare `gmail` — the directory segment IS the id, exactly as `origin/<id>/<subtype>.yaml` names it above.

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
  - `assembly:` *(2.1)* — config for **pre-ingest bundle assembly** (`corpus assemble`, §12.3.11): repackaging a source's delivered part(s) into ONE indexed container bundle before ordinary ingest, for delivery formats that are transient (an expiring export job), access-hostile (a solid compressed stream), or envelope-less (a loose directory tree an export tool wrote straight to disk). Keys: `merge_parts` (union a multi-part delivery's member trees — the split is delivery, not structure), `conflict` (`error`: a same-path collision across parts with differing bytes aborts; identical bytes dedup), `additions` (an allowlist of declared NON-original files placed at the bundle root, outside the original tree — e.g. an out-of-band export report), `rewrites` (declarative `{from, to}` restructure rules; **empty is the norm** — the original internal structure is NEVER changed except by a rule asserted here), `excludes` (declared filesystem-cruft subtraction — fnmatch patterns; slash-less patterns claim the basename at any depth, slashed ones the full relpath; exclusions are reported, never silent), `level` (the bundle's compression level), `derive` (mechanical origin-field extraction patterns — filename-convention regexes, addition-content regexes, and `from_member_head` regexes over the leading bytes of glob-matched members of a directory source, greatest match winning across members — so every vendor-shaped fact lives in the overlay, none in the engine), `seed_fields` (which derived fields beyond `account`/`job`/`exported_at` ride into the sidecar), and `name_fields` (derived fields whose values join the bundle's filename and archive comment — the job identity where no job id exists). The assembled bundle is staged with a capture sidecar (`origin_schema:` + the derived/declared fields) and enters the pipeline through ordinary ingest; the consumed part archives are recorded as `source_parts` tombstones (filename + byte hash) on the origin block — a directory source, having no delivery envelope, leaves none (member byte-identity is carried per-member by the manifest's members block). Absent the section, `corpus assemble` refuses the overlay.
- `transcription:` — per-host audio transcription (read by the `transcribe` derivation op, §6.2). `enabled: false` skips transcription (an `info` issue, not a `warning`); `adapter` / `base_url` override the global `[corpus.transcription]` backend. Absent the section, the global config applies.
- `canonical:` — `content_selector` scoping the `canonical` hash to the article-content region (§7.1). *(3.5: retired with the field — see the §7.1 `canonical_strategy` status note. Declarations may remain in overlays as dormant configuration; nothing consumes them.)*
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

All three frontmatter hash fields (`transport`, `canonical`, `perceptual`) and the body-block hash fields (`<!--members--> transport`, `<!--segment--> perceptual`) use a uniform encoding:

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
- `extended_fields` — the section-header fields the form's spans carry: **codebook lists** (e.g. `participants:` — authorship-derived, first-appearance order, entry grammar `<display> <durable-id>` — the join surface a codebook-index envelope field resolves against, §7.3) and span envelope facts. *(3.5, restoring 3.1's MUST and closing 3.2's exception)* Every field MUST be **mechanically derivable from the span's own bytes**. 3.2 softened this to a preference so that the universal editorial header fields could be declared interpretive-by-design; with those fields retired (§4.3.2.1) the exception has no remaining instance, and the rule returns to what it was — a fact that could be recomputed but is instead hand-stated is in the wrong layer, and a fact that *cannot* be recomputed is not a property of the span. Conformance checks (`checks:`, below) therefore bind **every** declared field. *(3.5: a form declares no editorial role marks — §4.2.3. Since these are the only fields a section carries, a form that declares none takes a bare opener, which is complete.)*
- `decomposition` — the normal form, normatively: which segment kinds compose the span (the envelope atom overlays and their required header fields), the addressing axis (`turn=`, `time_range=`, `pages=` — the form is **modality-blind**: `form/conversation` covers a chat export at `turn=` and a recorded meeting at `time_range=` with the same envelope), attachment and event conventions.
- `checks` — the mechanical conformance obligations lint enforces on any span carrying this form (§4.3.2.1): required envelope fields, codebook indexes in range, address monotonicity, **co-addressed segment pairings** (a contract whose faithful rendering is two stacked segments — a figure and the relation it states, §4.3.2.2 — binds the pair, so a span carrying one without the other is a violation rather than a span that merely looks finished). *(The check grammar is tooling-defined pending the first three overlays — §12.18 open questions.)*
- `normalization.guidance` — prose tactics for the authoring pass, stated **once** for every origin that maps onto the form.
- ~~`editorial`~~ *(3.3; removed from the form namespace in 3.5)* — editorial templates survive only on the **origin** overlay (§4.2.3, §7.2), where they compose a producer's own stamped facts. A form template composed the corpus's shape judgment into a display string, which is the record speaking about itself by a mechanical route rather than an authored one; the route was never the objection.

**Terminal contracts** *(3.3)*. Two members of the form domain prescribe the **absence** of a stored rendering — they are the zeroth form's judgment made assertable, closing the gap between *formless-unassessed* and *formless-by-design*:

- **`form/passthrough`** — the identity contract, named. Adopting it asserts the earned judgment that **no markdown shape will ever render these bytes more faithfully or more token-efficiently than the bytes themselves**, delivered through the derivation ops (§6.2). Its conformance check is the inversion of every other form's: the content zone holds structural byte-marks only — a stored rendering under a terminal contract is the lint violation. Its population: media streams and stills, code drops, datasets, binaries — the raw-context artifacts §4.1 names.
- **`form/manifest`** — the container specialization. The **members are the content** (`disposition: manifest`, §1.2): conformance binds the attested rows of the members block (§4.3.1.4 — the roster IS the attestation, nothing re-stated), and the content zone holds container byte-marks only *(3.5: the editorial header that used to vouch the container is retired — what the bundle is, is the members roster plus the mime, and what a reader wants said about it is a ledger claim)*. One derivation keeps the judgment single: a `disposition: manifest` record with no rendering contract declared for it **stands under `form/manifest`** — the disposition already is the terminal judgment, and the contract refuses to make an owner state it twice. An overlay MAY still bind a rendering contract over a manifest-disposition record where one genuinely applies; the explicit declaration wins.

A terminal contract is **not** the catch-all this section forbids: the prohibition targets stamping a *shape* an artifact may not have, and a terminal contract prescribes no shape — it records that none exists, earned by the same identification discipline as any adoption (§4.4.6) and guarded the same way (terminal adoption to flatter a census is exactly the force-stamping §12.22 refuses). Declaration rides the overlay grain — a mime schema's `form:` default, an origin overlay's override, per-record assertion for exceptions — because formless-permanence is almost always a class fact, not a record fact.

**Governing-contract precedence** *(3.3; the guards measured against the real fleet at first implementation)*. A record's governing contract resolves: (1) the **origin overlay's `form:`** declaration (§7.2 — rendering or terminal); (2) the record's **own asserted whole-record section** (rendering or terminal) — a stamped per-record judgment outranks every class-grain default (the §12.20 promoted h264 slide-deck track is the measuring case: a raw-stream passthrough mime default must never condemn it); (3) the **mime schema's `form:`** terminal default (§7.1); (4) the **`disposition: manifest` derivation**. Two guards on (3)/(4), neither applying to (1)/(2): a class default never claims a record **already carrying a stored rendering** — grandfathered rendered content stays `rendered` until its pass exits it (§12.19), never retroactively condemned by a later class declaration — and the manifest derivation requires the manifest attestation to have actually emitted **member rows**: a promoted member stub whose format family is manifest-dispositioned carries no roster of its own and stays `proxy` (the promoted vcard cards are the measuring case — §12.23 holds them proxy until their rendering contract lands). Stamping is **optional**: a terminal record needs no section at all — the declaration alone governs. *(3.5: with the editorial header retired there is no longer any reason to write an empty-span whole-record opener; a bare terminal record is the complete shape.)* Downstream: a terminal record **never gates and never enters the queue by default** (§8.5), health reports it as **terminal** — not proxy — and the ledger treats it as a **complete source** whose derived surfaces are permanent, full-strength evidence (`ledger.md` §6.3).

**Forms are a goal, not a rarity** *(3.1, amending 3.0's "rare by design")*. For the right artifacts — those with a faithful markdown shape — a named form is where the record is headed: messaging exports render as `conversation`, statements and receipts as their contracts, and the document population (captured articles, manuals, papers) as a small set of **generic shapes**. Adoption is **lazy and benefit-driven** — §4.4.6's two stamping paths, pulled by demand through the queue (§8.5) — never forced by totality: nothing requires every record to carry a named form, which is precisely what keeps the library honest and small. The population splits cleanly: formless-permanently (no faithful markdown shape exists — the identity contract IS the rendering), formless-for-now (a shape fits but none is yet identified, authored, or worth the pass), and formed. *(3.3: the split is machine-readable — formless-permanently is a terminal declaration, reported as `terminal`, and `proxy` narrows to formless-for-now-or-unassessed.)*

**The minting test** *(3.1 restatement)*. A form is minted when all four hold: (1) it names a **shape, never a subject** (below); (2) its decomposition contract states what a faithful rendering IS, precisely enough that conformance is **mechanically checkable against the bytes** — every fact it declares recomputable from the span *(3.5: every fact, without exception — 3.2's carve-out for declared-interpretive fields retires with the fields it was written for)*; (3) a **population wants it** — the contract recurs across ≥2 origins, or a generic shape covers a modality-wide population; (4) a consumer **uses it** — a shaper, a composition view, a harvest rule, or the ledger's span-precise citation surface. One origin wanting a shape is origin-overlay guidance; a label that changes nothing about rendering or checking is not a form. *(3.0's second criterion — "changes the normal form vs. mime + atoms alone" — relaxes: a generic shape may render close to what mime + atoms already produce; what it adds is the contract itself — a named, checkable expectation a stored rendering can be verified against (§4.3.2.1 coherence; `ledger.md` §13.2), which an uncontracted rendering never has.)*

**Generic shapes, guarded** *(3.1)*. A small generic hierarchy — on the order of `document`, `article`, `procedure`, `transcript`, `data-table-set`, `slide-deck` — is expected to cover the corpus's entire rendered population in **fewer than ten shapes**; a proposed eleventh generic shape is a design smell to be argued for, not a routine mint. A generic shape is still a real contract (an honest `form/document` binds artifacts that genuinely render as documents); what it must never be is a default (the zeroth form, above).

**Forms name shapes, never subjects.** `conversation`, `statement`, `receipt` are shapes: a time-ordered participant-attributed message sequence; a period envelope with transaction line items; an itemized-commerce document. `product-manual` is **not** a form — a manual decomposes as a generic document (`form/document` at most, 3.1), and manual-*ness* is a ledger claim *(3.5: the reference block's `role:` field retired with the block, §4.3.3.3)*. `episode` vs `film` are legitimate — act structure with title/credit conventions vs scene-and-chapter continuity are decomposition contracts in the bytes — while *which show* an episode belongs to is the ledger rostering the record onto a concept, exactly as `form/receipt` never names the merchant (the origin block and the bytes do). This is the normative line that keeps §4.3.1.3/§7.4 honestly tombstoned: the classify block asserted meaning at record scope and is not returning; the form opener asserts shape at span scope, mechanically checkable, nothing more. *(3.1)* The guard binds hardest exactly where the library grows: a shape is generic or it is nothing — `form/procedure`, never `form/<site>-procedure`; the subject half of any proposed compound form belongs to the origin block (provenance) or the ledger (meaning). Shapes mint as their populations adopt and their consumers arrive — never before. *(The library's membership is not restated here: `form/<id>` overlay files are the registry, each carrying its own contract, its consumers, and the judgment that earned it. A roster in this section would be duplicate state, and it would rot.)*

**Stamping** is §4.4.6's two paths (declared via the origin overlay's `form:` key; asserted by an interpretive pass through the normalize gate). **Coherence** is §4.3.2.1's lint rule. **Downstream**, `form.*` joins the ledger harvest fact base (`ledger.md` §10) — deterministic rosters keyed on shape (`every form/receipt records onto the spending concept`) — and composition views consume *(form, envelope)* tuples with no platform knowledge: the cross-platform conversation thread joins spans on (ledger identity × timestamp); the same-video view joins tracks on (lineage × timeline); one composition layer, two join keys, zero stored view state.

---

## 8. Pipeline

### 8.1 Stages

| Stage | Mechanics | Touch identifier shape |
|---|---|---|
| `capture` | Bytes land in the corpus's staging area. | none |
| `ingest` | blake3 of bytes → `id`; `transport_algos` → `transport:`; MIME detect → artifact-block opener; **byte-fact attestation** per the mime schema's `attest:` and `disposition:` (§7.1) — artifact fields, the members block whether manifest or exposable (members / messages / cards / entries / parts / tracks / items), structural byte-marks, sidecar lift; emit the record (the artifact's proxy, §4.1) with first origin block from capture context; persist binary. | `<pkg>.ingest@<v>` |
| `promote` | Mint a record for a container member already in the corpus: locate via the members-block row, stream + blake3-verify → `id`; MIME detect; **attest** per the member's mime schema; emit a record whose first origin block records the containment lineage as history (`uri: corpus://<container-id>?<member-address>` + `filename`/`source_modified` where present). Bytes are NOT copied (§2). *(3.8: **required** for any member a record positions with a placement (§4.3.2.4) — placing is the act that obliges it; an unplaced member never needs it. The lineage origin is also what supplies the normalize pass its parent **context**, which is an input to the pass and never to its output.)* | `<pkg>.promote@<v>` |
| `draft` | *(retired in 3.0.)* The stage's three duties split: fact-stamping → ingest **attestation** (above); content extraction → resolver **derivation ops** (§6.2); body-writing → the normalize pass. A `status: draft` record reads tolerantly as a just-attested record (§12.18). | — |
| `normalize` | The **one authoring pass**: consumes the derivation ops and renders the record under its named form contract (§7.8) — executed by a mechanical **shaper** where the record's declared form mapping (§7.2) or manifest shape makes it deterministic, by an interpretive agent where judgment is required — with the span's declared form fields and typed faithfulness issues riding the same pass. *(3.5: the pass no longer authors editorial headers or descriptions; its whole output is faithful renderings, form declarations, and fidelity issues.)* | `<pkg>.shape.<id>@<v>` / `<model-id>` / combined (`+`) |

Idempotent re-capture is part of `ingest`. Concrete tooling is implementation-defined.

An origin overlay's `capture.references` (§7.2) drives one mechanical, deterministic action (§8.2): for rules marked `capture: true` (or `corpus capture --with-references`), the **capture** side fetches the page's declared dependent links at depth 1 as their own records after the primary ingest. *(3.5: its record-side half — emitting a `reference` context block per declared link — retires with the block (§4.3.3.3). The links themselves are already in the faithful body, and whether one names a captured record is a read-time resolution (§9.9, §12.4.7); nothing needed storing. `capture.relations` retires outright, having had only the emission half.)* The declaration is therefore now purely a **capture** instruction: which outbound links are part of this capture.

A corpus may also specialize the **shaping** of its own content with corpus-local shaper code — `<corpus_root>/shapers/*.py`, loaded mechanically before the normalize pass (the analogue of the corpus-local capturer in §7.2). Such a shaper claims a record by its origin or form id (§7.2) and builds the authored content zone in place of (or ahead of) the generic mapping-driven shaper and the interpretive agent; the package ships none and knows nothing of any specific format. Implementation-defined — see §12.4.3.

### 8.2 The deterministic / LLM boundary

| Operation | Type | Why |
|---|---|---|
| Hashing, MIME detection, schema lookup | deterministic | mechanical |
| Byte-fact attestation (artifact fields, manifest members, byte-marks, sidecar lift) | deterministic | mechanical |
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
| The artifact block's opener (the MIME) and the origin blocks with their `uri:` history. | The artifact block's attested fields, the members block, all sections/segments (authored and byte-mark alike), all context blocks. |
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

**The pass gate** *(3.1, succeeding the 3.0 `status: normalized` gate; re-keyed 3.2)*. **Done** means the pass left the record **formed where its overlays declare a form** (§7.2, §4.4.6 — form-coherence lint covers the conformance half) and linting clean. Both are derived from the record itself; `finalize` enforces them together. *(3.2: the 3.1 gate's authored half dissolves with the layer — a formed span's editorial fields ride its section header under its own contract, and a record staying formless owes no vouch: its derived title/description are already honest, §4.2.3.)* *(3.3: a record governed by a **terminal contract** satisfies the gate with no stored rendering — the contract prescribes exactly that — so a terminal record drains to an immediate no-op `finalize` unless the request explicitly asks for re-evaluation or a describe pass; an accidental enqueue self-heals.)* *(3.8: linting clean now also means every member the record **places** has been promoted (§4.3.2.4) — the pass discovers its placements while making them, so the obligation is discharged in the same pass that creates it, and a parent whose placed member has no record does not close.)*

***(3.8) Normalization pressure — the second demand source.*** A promoted member awaiting its own pass is **demand**, not backlog, exactly as the queue's founding rule says (§3.1 above): its parents want it rendered. The magnitude is mechanical and needs no field — a leaf placed in N records is wanted N times — so pressure is **derived** from the member index (§12.15) like every other cross-record fact, and the queue can be ranked by it: rendering one member that 668 records place is 668 records improved by one pass, which is a materially different proposition from rendering one that a single record places. This joins the ledger's demand (`ledger.md` §6.3 — the citation discipline enqueuing what it wants formed) as a second source on one mechanism; neither is a gate, and a leaf that no consumer ever asks about stays a complete record standing as its artifact's proxy (§4.1).

**Drivable by an external loop, in either of two modes.** The claim is atomic (concurrent loops never double-claim) and every verb is non-interactive with a meaningful exit code and machine-readable output, so an agent loop runs `drain` → normalize the emitted id in-session → `finalize` (or `release --failed`) each iteration. A **scheduled** loop (e.g. cron) drains until the queue reports empty, then waits for the next tick — simple, but the loop session itself does the polling, waking even when there is no work. A **standing** loop instead blocks on the `drain` long-poll, which waits in the tooling until a request is claimable and returns it the instant one appears — so the (costly) loop session is engaged only when there is genuinely work. Both drive the same atomic claim; the long-poll is an ergonomic over it, not a distinct contract, and the same loop body serves either. The normalizer reads the record's applicable overlays' `normalization.guidance` (mime §7.1, origin §7.2, form §7.8, atom §7.3); because form knowledge rides in overlays, one generic loop serves every source — and demand flows down from the ledger, whose citation discipline prefers formed surfaces and raises demand by enqueuing (`ledger.md` §6.3): the ledger contributes by enqueuing, never by supplying a normalizer. *(3.0; completed 3.3)* The loop session's first consult is the record's **governing contract**, and the pass branches four ways: (1) **terminal** (§7.8) — no-op `finalize`, unless the request explicitly asks for re-evaluation *(3.5: the describe pass is gone with descriptions; a terminal record has no residual authoring work at all)*; (2) **declared form, mapped** — the shaper writes the form mechanically and there is nothing left for an agent to add, so the pass is deterministic end to end *(3.5)*; (3) **declared-but-unmapped or asserted form** — the interpretive case, and on an already-formed record a *refinement*: improve the existing shaping, never regress it; (4) **no form, no terminal** — the **adoption sweep**: test the library's contracts against the record's own bytes and adopt by assertion where one genuinely fits (§4.4.6), under the §12.22 discipline — body evidence wins, substantive-content veto, and a record matching no contract exits the pass formless and reported, never force-stamped. `finalize`'s done-gate is the pass gate above, form-coherence (§4.3.2.1) included.

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

The members block and context blocks are NOT included. A record carrying an artifact block and one qualified origin block yields:

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

Returns structured records — each issue carries its id/subtype + universal fields + optional `address:` + any id-specific fields. *(3.5: `issue` is the only namespace, so this view and the context view now coincide.)*

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
- `full` — `blocks` plus an image-token estimate summed over an image artifact and the record's image members, each `≈ min(width·height, cap) / pixels-per-token` (`0` when dimensions are unavailable). *(3.4: the artifact's own dimensions are attested on its block; member dimensions come from the `members` derivation (§6.2), since the stored roster carries none — so this tier needs a resolvable artifact, and degrades to omitting the member contribution rather than failing. `full` is declared an estimate precisely so this degradation is in contract.)*

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

### 9.9 The `references` view *(3.5: re-based on the body)*

The outbound-link view. *(3.5)* Its input is no longer the retired `reference`/`relation` context namespaces (§4.3.3.3, §4.3.3.5) but the **faithful body itself**: every markdown URL a record's segments carry, which is where the source's own links now live in full. Each entry carries the link text, the URL, the address of the segment holding it, and the **derived** resolution (`resolved_uri`/`captured`, computed against the URI index at read time — §4.4.5, §12.4.7). The resolved edge is directional toward the linked record; the reverse ("records that link *this* one") is a corpus-wide read derivable from these edges but, like cross-record content addressing (§11), the corpus-wide index is not specified here. Computed on demand, never persisted.

The re-basing is a strict gain in coverage as well as in honesty: the context-block path saw only links an origin overlay had declared a lift for, while the body carries **every** link the source rendered.

---

## 10. Export

A record renders correctly only inside its corpus, because its addressed surfaces — the image a positioning segment marks, the crop a transcription cites — are **derivations** that need a resolver. **Export** produces a portable, self-contained rendering by materializing every addressed surface to a file alongside the exported record and emitting a local reference to it.

Surface materialization contract:

```
<!--segment image/figure address: <address>-->   →   ![<derived alt>](<local-file>)
```

*(3.4: the contract is stated over the record's own addressed surfaces, not over stored body links. It was previously written as a rewrite of `![[corpus://…]]` embed references in segment bodies — a construct §4.3.2.2 now forbids and no record ever carried. The export therefore reads placement from the content zone's addresses, which is where placement always actually lived; alt text comes from the `members` derivation (§6.2).)*

Export is idempotent and untracked. The output layout (filenames, directory structure) is implementation-defined.

---

## 11. Out of scope

Genuinely deferred items for this spec version:

- **Automatic PDF text / OCR extraction.** Every PDF presents **uniformly** — `/Info` fields attested, and a derived body (§6.2) of per-page body-empty `image` segments addressed `page=<N>` — regardless of born-digital or scanned. Deciding a page's shape, pulling its embedded text layer, transcribing a scan into `text/ocr` (with engine/confidence provenance — the corpus owns OCR provenance rather than laundering a pre-baked layer), and outline-driven structural marks are all **normalize-pass** work over the resolver's introspection ops (§6.2). What remains deferred is an *automatic* (non-agent) text-or-OCR pass.
- **Deterministic stream extraction** *(3.0)*. Track promotion from media containers (§1.2) requires member-byte determinism; the mbox precedent achieves it by pinning extraction semantics on the mime schema, and the same discipline is required here (elementary-stream sample data in decode order per the container's own tables; HEIF `item=` payloads likewise). Pinning a demuxer's output across tool versions is an open engineering item — content-addressing plus continuity-gated supersession (§12.8) is the net if a pinned extraction ever shifts bytes.
- **SQLite databases** *(3.0)*. An application's SQLite store (`chat.db`, `Photos.sqlite`, a browser's history db) is THE container of raw app data, and rows are deterministically addressable — a row/query axis would be well-defined under the disposition machinery above. Deferred **deliberately**, not overlooked: the corpus philosophy prefers **producer-declared exports** — the app's own export surface, with its declared semantics — over reverse-engineered application internals, and no real capture has yet wanted the database itself. When one does, `disposition: manifest` plus a pinned row-extraction scheme is the landing zone; until then this silence is a decision.
- **Cross-record content addressing** via `<!--members--> transport` — the shape leaves room for a corpus-wide `transport → (record_id, address)` index but the index itself is not specified. (Building it requires reconciling the `<algo>:<hex>` member-row `transport` encoding with the bare-hex record `id` — strip the prefix and confirm `algo == blake3` before matching.)
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

Inline media a transport merely *references* (images in an HTML page, etc.) are not separate records: ingest attests one members-block row per asset (deduped by `transport` byte-hash), and the body carries an `image`/`audio`/`video` positioning segment (§4.3.1.4) — never a stored intra-corpus link *(3.4: segment bodies carry none at all, §4.3.2.2)*. A raw archive is no exception (2.1): its roster IS its attestation, and a member becomes its own record only by deliberate promotion (§8.1). Hyperlinks to *other* resources are reconciled to intra-corpus references during cross-reference resolution (§12.4.7).

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
- **`canonical`** — *(3.5: retired, §4.2.1/§7.1.)* Nothing computes it and no record carries it, so `records.content_key()` returns `None` for every record and `find_content_duplicate` short-circuits unconditionally: the cross-URL content-dedup fold is inert by construction rather than by configuration.
- **`perceptual`** — atom fingerprints (image pHash, text simhash, …), **opt-in and schema-gated**, attested at ingest only when the fingerprint knob resolves on (§12.4.4); default off. Per-segment on multi-atom records, record-scope on single-atom ones (§7.7).

There is no frontmatter `hashes` field and no mandatory per-MIME perceptual hash. A MIME with no canonical strategy and no fingerprint knob is blake3-`id`-only, and that record is normal.

#### 12.3.4 The record at birth *(3.1; formerly "the stub record")*

Ingest emits the record — the artifact's proxy, complete at birth (§4.1). The frontmatter carries only the bytes-identity header — `id`, `transport:` (any `transport_algos`), `touch: [<pkg>.ingest@<v>]`; *(3.1)* no `status` field; *(3.2)* no editorial fields — the display title/description derive from the role-marked attested and sidecar-lifted fields the same ingest just stamped (§4.2.3), so the proxy is presentable the moment it exists. Everything else lands in body blocks:

- The **artifact block**, its body holding the format-intrinsic extended fields the mime schema declares, named bare (`title`/`author`/`page_count`, not `pdf_title`; §4.3.1.1). Sources: PDF info dict, EXIF, ID3, HTML `<meta>`, OPF Dublin Core, ffprobe streams.
- The mime schema's remaining **attestations** (§7.1): manifest/exposable members per the disposition, structural byte-marks, sidecar lift.
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

**Sidecar → origin block (ingest attestation), then deleted.** The `.info.json` is *non-primary-source* metadata, so the sidecar lift copies every declared key into the **origin block** as a flat `ytdlp_<key>` field (`ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts, …) via `records.merge_origin_fields` — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when returned) becomes a `ytdlp_comments` list field; `webpage_url`/`original_url` fold into the origin `uri:` aliases. The lifted key set is schema-declared — `sidecar.ytdlp_keys` on the video/audio mime schema (§7.1); the lift is mechanical, not hardcoded. One datum is *structural* rather than flat: **`chapters[]`** (the uploader's outline) is consumed into **structural segments** (producer-declared byte-marks, §4.3.2.3) — each chapter title a `mark:`, each bound a `time=` mark address. Chapters are consumed into marks, never copied to a `ytdlp_*` field; a mark's `mark:`/address is structure, not body content, so this respects the same primary-artifact boundary. Transcription moves off the pathway entirely: it is the `transcribe` derivation op (§6.2), consumed at normalize.

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

#### 12.3.10 Dependent capture (`capture.references`)

A page's most relevant outbound links are part of the capture itself — a product-detail page's manual or spec sheet far more than the other hundred links on the page. The per-host `capture.references` overlay section (§7.2) declares which links those are, and the tooling fetches them depth-1 as their own records. The home is one module, `corpus.references` — *declare, match* — with the *fetch* delegating to the existing capture/crawl machinery. Opt-in throughout: no rules → entirely inert. *(3.5: the **emit** third of that module retires with the reference block (§4.3.3.3). Declaration and matching stay — they are what decides **what to capture** — and the link itself needs no emission, since the faithful body already carries it. This is a strict narrowing: the section is now a capture instruction and nothing else.)*

- **The rules** (`references.parse_rules` → `ReferenceRule`): a list of `{match, role, capture, cross_host}`. A rule's `match` keys (`selector` CSS, `href_pattern`/`text_pattern` regex on the resolved href / anchor text, `rel` token) are ANDed; rules are ORed. `role` (corpus-local label — `manual`, `spec-sheet`) rides onto the emitted reference; `capture: true` opts the target into the depth-1 grab (default false = annotate only); `cross_host: allow` (the default — manuals are off-host) lets a match reach another host, `same` host-restricts it. Parse-tolerant: a non-mapping entry, a rule with no match key, or a bad `cross_host` is skipped, never fatal.
- **Matching** (`references.match` / `matches_for_record`): parse the DOM, scope candidate anchors by `selector` (else all `<a href>`), apply the AND filters, resolve relatives against the base URL, normalize, drop non-crawlable hrefs (`urls.is_crawlable_href` — the same filter `links`/`crawl` use), enforce `cross_host: same`, and dedupe by URL (DOM order, first rule wins for role/capture). `matches_for_record` applies the host's rules against the record's primary origin URI and excludes self-links. Shared by the overlay emission, `corpus links --references`, and the grab.
- ~~**Emission rides the attestation pass**~~ *(3.5: removed.)* `references.emit_overlay_references` and the `<!--context reference-->` block it wrote are retired (§4.3.3.3). Whether a declared link names a captured record remains a read-time derived edge — now resolved over the **body's** links rather than over stored blocks (§9.9, §12.4.7) — and it self-heals (`captured ⇄ pending`) under capture, removal, and supersession exactly as before. The retirement also dissolves the known gap the emission carried: it was HTML-only and record-scoped, writing no segment anchor because the declared link usually sat in un-segmented chrome. Under 3.5 that chrome is either rendered as content — in which case the link has a real segment address — or it is genuinely chrome and stripped, in which case there was never anything to anchor.
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

- **Dedup keys on member identity, never position.** "Already persisted" is decided per member by the un-stuffed member blake3 (§12.11 — the promotable identity, §8.1); ordinals scatter across exports and mean nothing. The exclusion set is **derived at run time, never stored**: the union of (i) a full streaming enumeration of each lineage record's artifact bytes where locally present, (ii) each lineage record's declared `msg=` member-row transports — the fallback when the bytes are remote or retired, warned, since a selectively-declared mailbox declares a subset — and (iii) every standalone `message/rfc822` record id in the corpus (a promoted or independently-ingested message is a persisted member wherever it now lives).
- **The lineage is transitive.** Each `--against` expands through the named record's own `window_against` origin field, so naming only the latest window reaches the whole chain back to its baseline snapshot. A deliberate re-baseline (a new full snapshot ingested whole) starts a fresh lineage.
- **Members copy raw.** A selected member is copied verbatim — separator line plus stuffed bytes — in source order, so the bundle is a valid mboxrd whose members carry byte-for-byte the identities the source held (§2). Within-source duplicate members (the same blake3 twice) fold to one copy, counted. An unreadable source aborts with no partial bundle (the §12.3.11 exception to parse-tolerance); an empty delta emits nothing and says so.
- **Provenance rides the sidecar** (`origin_schema:` + `origin_fields:`, §7.2, overlay id supplied by `--origin` exactly as `assemble` takes it, or auto-stamped from the `default_origin` binding when the flag is absent — below): the source export's identity (`source_export`, `source_modified`, `source_message_count` — the staged bundle keeps its own `filename`), the window bounds derived from the selected members' Date headers (`window_start` / `window_end`), the counts (`window_count`, `excluded_count`, `duplicate_count`), and **`window_against`** — the lineage record ids as **plain hashes, deliberately not `corpus://` refs**: they record what was subtracted at build time (process provenance), not a resolution route — no member resolves through the lineage — so a later-retired lineage record must not raise `dangling_origin_refs` (§12.8).
- **Full declaration is the window convention.** Post-ingest, `corpus reattest <id> --messages 1-<N>` declares every member — affordable precisely because the bundle is thin — so the manifest doubles as the window's **human delta index** (per-member date / from / subject) and as the **machine dedup-set** the next window subtracts without re-scanning artifact bytes: a fully-declared window's roster IS its member set.
- **Year-split for full snapshots (the re-baseline shape).** A full snapshot need not persist as one monolith: `corpus mbox-split <export>` partitions the canonicalized members by Date-header year into per-year mboxes — **closed years only** (strictly before the current year; a member with an unparseable Date is never falsely closed, it stays with the current residue) — and assembles them into ONE deterministic zip container staged for ordinary ingest: a `zip-manifest` record whose `<YYYY>.mbox` members are each **promotable** (§8.1) to a first-class mbox record whose bytes stay in the container. The current year's members emit as a residue mbox handed to the window flow, never to the container. The payoff compounds with the chrome strip: a closed year's stripped mbox is **byte-identical in every future full export**, so the next re-baseline's year members re-encounter (origin append, zero new mints — §12.3.5) and only the newly-closed year mints; a full snapshot's marginal cost converges to one year plus the hot end. The container sidecar carries the source export's identity + transport, the strip disclosure, the per-year member counts, and the excluded current-year/undated counts. Mail is the standard's first instance (§12.3.14): its years-through-2025 stratum is the grandfathered `eras` entry — closed at year grain, never re-cut — the forward grain from 2026 is month per the standard, and `mbox-window` remains the member-dedup mechanism the rolling current-period record rides.
- **Provider-metadata headers strip at capture — the mailbox chrome strip.** A provider that mutates per-message metadata *inside* the exported bytes (Gmail's `X-Gmail-Labels`: read state, categories, importance, user labels — measured as the COMPLETE churn set between two real exports: member identity modulo that one header was 99.1% stable, every residual an arrival or purge) makes member identity hostage to workflow state. The remedy is the HTML chrome-strip precedent (§12.3.6) on the mail axis: a **declared header list** is removed from every member's header zone (folded continuations included; body lines never touched) **before identity** — the stripped bytes are the stored bytes, blake3 over them the one identity, exactly as a chrome-stripped DOM is the stored page. Declarative list only, no eval hook — mail surgery must be reviewable. **The declaration is still schema config, never a verb — but the declaring grain is the origin overlay, not the mime schema.** Label chrome is producer knowledge, so `strip_headers` lives on the *producer's* overlay (§7.2) — e.g. `google-takeout/gmail` — exactly as a host's chrome-strip interactions live on `origin/web/<host>` overlays (§12.3.6); the packaged distribution ships no strip values on any grain. The `application/mbox` mime schema (§7.1) carries no `strip_headers` of its own — it supplies the **interaction point** only: it documents the strip hook, and it carries the one corpus-local **binding**, `default_origin: <overlay-id>` — "an unattributed mbox entering this corpus is presumed produced by this origin" — which is what keeps canonicalization unconditional at identity-mint time even when no sidecar stamps an origin. Resolution precedence, most-specific first, in the fingerprint-knob shape (§7.7): (1) the CLI `mbox-window --strip` override; (2) absent that, the **stamped** origin's `<id>[/<subtype>]` ladder (§4.3.1, §7.2) — ingest reads the sidecar's `origin_schema` before hashing; (3) absent a stamped origin, the `default_origin` binding's own ladder; (4) absent both, off. The **ladder** is the same grammar the opener already carries, not a novel notion: a stamped compound (`google-takeout/gmail`) is grammatically id + subtype, so the walk tries the subtype overlay first, then the id overlay — one segment shed at a time, as deeper nesting would demand — and the first of the two that DECLARES `strip_headers` is final: an explicit empty list is itself a declaration, meaning "no strip." The ladder never crosses producers: a stamped origin whose walk finds no declaration leaves the strip OFF outright — falling through to another producer's chrome list would be a category error, so the `default_origin` binding is consulted only when nothing is stamped at all. **Auto-stamp** closes the loop: `mbox-split` and `mbox-window`, run with no `--origin`, stamp their emitted sidecar's `origin_schema` from the `default_origin` binding (disclosed in their output) — attribution is config-automatic by the same principle as the strip. Ingest itself never invents origin attribution; the binding drives canonicalization alone, and attribution enters only via a sidecar. And **ingest applies the resolved strip automatically** when a standalone mbox stages, so the invariant can never depend on an operator remembering a pre-processing command. This is the one deliberate amendment to ingest's hash-what-staged contract: canonicalize-then-hash where declared, with the delivered bytes' blake3 preserved as `source_transport` on the origin block (`stripped_headers` + the member count beside it) so the pre-strip identity is disclosed, never silently lost. An already-canonical file (a window bundle emitted stripped; a re-drop of stripped bytes) passes through untouched. `corpus mbox-window` resolves the SAME config for its source, its emission, AND its lineage artifact enumeration — so a pre-strip (label-full) snapshot still serves as lineage across the strip boundary, its members hashed as-if-stripped at scan time. Two caveats: the declared-member fallback carries pre-strip hashes and cannot cross the boundary — lineage older than the strip needs its artifact bytes present (warned, never silent) — and the strip applies only where a mailbox enters standalone: members inside an ingested container must stay byte-identical to their container route (§2), so a mail export's mailbox is extracted and staged, never ingested-as-zip.

#### 12.3.14 Temporal stratification — the standard for re-delivered temporal exports *(3.3)*

A producer that re-delivers **temporal content** — mail, message-platform exports, photo libraries — generalizes past the mailbox precedent (§12.3.13) into a named standard: **temporal stratification**. The same forces that shaped the mailbox flow — recurring full-export waste, provider-metadata churn, and the closed-vs-live boundary — recur on every date-addressable stream, so the standard fixes the grain and the stratum shape once, leaving only the producer's canonicalization measurement and its export-to-period mapping as onboarding work. Mechanics:

- **The model.** Any re-delivered temporal stream stratifies into: **closed periods** at **month grain** — the standard, one order finer than the mailbox year-split (§12.3.13) — byte-stable after canonicalization and therefore re-encountered (origin append, zero new mints, §12.3.5) by every future export; ONE **rolling current-period record** per stream, re-established on every export — idempotent when nothing changed (the re-cut is byte-identical, so it re-encounters rather than re-mints), superseding its predecessor when the period grew (continuity-gated, §12.8; the prior cut retires only after the ledger's citations move — operator-gated, NEVER automatic deletion), a disclosed retire path when the period shrank (a mid-period purge, reported rather than silently absorbed); a standing, never-closing **undated bucket** for members carrying no parseable date; and OPTIONAL **year containers** assembled from twelve settled months at year close — the closed-years-container pattern (§12.3.13), recast one grain finer as an assembly over months rather than a partition over messages. Grain is independent of capture cadence: a bi-monthly export closes several months in one batch; nightly re-establishment of the rolling record costs nothing on a quiet day, since nothing changed to re-mint.
- **The declaration.** A `partition:` block on the producer's origin overlay, beside `strip_headers` (§12.3.13) — resolved by the same §7.2 id/subtype ladder and, for an unattributed export, the same `default_origin` binding: the corpus prescribes the stratification, the tooling only executes it.

  ```yaml
  partition:
    grain: month           # the standard closed-period grain
    eras:                  # optional: historical strata grandfather at their own grain
    - until: "2025"        #   e.g. mail: closed YEARS through 2025 (the live 21-record stratum)
      grain: year
    undated: standing      # the never-closing bucket (the default)
    assemble: year         # optional: year containers as month assemblies
  ```

  The `eras` schedule is what lets a future full-export re-baseline re-encounter history at the grain it already settled at: mail's years through 2025 re-encounter the existing records unchanged, while 2026 onward closes monthly — an existing stratum is never re-cut by default just because the standard's grain moved on.
- **File-grain sources split with `corpus period-split`** — the §12.3.13 split's sibling for a directory/zip of member FILES rather than mailbox messages (a photo library: originals + JSON sidecars; any per-file export tree). Each member's date resolves through a declared **date axis** — a paired sidecar's dotted path (e.g. a photo's PhotoInfo JSON `date`), with file mtime as the explicit fallback axis — and members bucket into ONE deterministic zip PER closed month: each month container is a record directly (file-grain months are records; mbox months are promotable members of one container, §12.3.13), plus the rolling current-month container and the standing undated bucket, sidecar-stamped exactly as the mbox flow's outputs are. Two honest divergences from the mbox flow: (1) a generic zip container carries no media-type-level `default_origin` binding to lean on — `application/zip` is universal, and presuming a producer from it would be dishonest — so the producer is named at the verb (`--origin`), and the partition schedule resolves through THAT ladder; (2) closed-month byte-stability additionally depends on the producer preserving both member bytes AND the dates the axis reads — exactly what the measurement gate below establishes before any declaration ships.
- **Late arrivals.** A member dated into an already-closed period, arriving in a later export, re-mints that period at next close — a narrow blast radius (one month, not one year), resolved by ordinary mechanical supersession on member identity (§12.11 — the promotable identity, §8.1): the same failure mode a year stratum already carries, just proportionally smaller.
- **Citation policy.** The ledger cites a promoted member or a closed period, never a rolling record's shifting identity by default; where a citation does land on a rolling record, it supersedes mechanically the same way any growing record does — member blake3 to member blake3, continuity-gated (`ath ledger supersede`, `ledger.md` §13.3).
- **The onboarding gate — no declaration without measurement.** A producer's `partition:` (and any canonicalization it pairs with) is earned exactly as the mailbox header strip was: a banked two-export diff over the same closed period (the Gmail 99.1%-stable measurement, §12.3.13), recorded in the overlay's comment block, is the prerequisite for declaring closed-period byte-stability at all. A producer whose serializer is NOT deterministic across export jobs onboards **member-dedup-only** — the window-reduction pattern (§12.3.13), with no closed-period claim — until, or unless, a later measurement earns the stronger guarantee.
- **JSON-family canonicalization — `strip_fields`.** The mail chrome strip's amendment generalizes past mbox headers to any JSON-family export: a producer overlay MAY declare `strip_fields`, a declarative list of dotted key paths (`[]` permitted for array traversal) removed **span-surgically** — the matched key-value span's bytes are deleted in place; the document is NEVER re-parsed, re-ordered, or re-serialized, so every byte the producer did not name stays exactly as delivered, precisely as the header strip leaves body lines untouched (§12.3.13). The same amendment applies verbatim: canonicalize-then-hash where declared, the delivered bytes' blake3 kept as `source_transport` (disclosed as `stripped_fields` + the field count), an already-canonical file passing through untouched, declarative list only — no eval hook, so field surgery stays as reviewable as header surgery. First consumers: the Discord and Meta onboardings.

### 12.4 Attest & derive (the draft stage's successor)

*(3.0)* The 2.x draft stage's per-format drafters split into **attestations** (ingest-time byte-facts) and **derivation ops** (resolver-side content extraction); the body each drafter wrote is now the `body` op's output, stored only when the normalize pass authors it. A classification is never a frontmatter array and carries no justification field — the `classifications` list is a derived view (§9.1) — and records carry no `tags` field.

#### 12.4.1 The per-format split

The per-format inventory, restated as the split (each 2.x drafter's mechanics carry over to whichever side of the split owns them):

| 2.x drafter | Disposition | 3.0 attestations (ingest) | 3.0 derivation ops (§6.2) |
|---|---|---|---|
| HTML | work | inline `data:`-asset members (hash, type, `el=` address) | `body` (DOM→markdown, overlay chrome config), `el=` |
| PDF | work | `/Info` fields; **exposable members** for embedded files / portfolio members (`attachment=<N>`) | `body` (page markers), `page=` + introspection ops, `attachment=` |
| EPUB | work | Dublin Core fields; image-member rows | `body` (spine text), `spine=`/`el=` |
| OOXML (docx/xlsx) | work | document facts; **exposable members** (embedded media, OLE objects) | `body` (document text / sheets), `sheet=`/`bbox=` |
| zip/tar (+ zip-shaped types) | manifest | member rows (`path=`), archive facts | `members`, `path=` |
| mbox | manifest | declared-message members (`msg=`, **selective declaration** — below; §12.11 pins the extraction) | `msg=` |
| multi-card VCF | manifest | card members (`card=<N>`, delimiter-pinned — the mbox precedent on the contact axis; each member `text/vcard`, promotable) | `members`, `card=` |
| ICS calendar | manifest | entry members (`entry=<N>`, `VEVENT`-delimited, promotable) | `members`, `entry=` |
| eml | work | header lift; part members (`part=`) | `body` (reply-text trim), `part=` |
| JSON | work | shape facts (`json_root`, `json_top_count`); `malformed-json` issue | `body` (verbatim passthrough), `turn=`/`att=` where a form mapping declares units |
| audio / video containers | manifest | container/stream facts; **track rows (`stream_id=`) + chapter marks** (§1.2) | `transcribe`, `time_range=`, `frame=`, `stream_id=` (default-member sugar, §6.2) |
| HEIF/HEIC | manifest | image-item members (`item=<id>`); the declared primary (`pitm`) attested | `item=`, image ops via default-member resolution |
| image (single-stream) | work | dimensions/EXIF; a motion photo's nested MP4 as an embedded transport (§1.2) | `bbox=` and the image toolkit |
| markdown / plain | work | — | `body` (passthrough) |
| unknown | work | best-effort facts only | — |

Formats that arrive later slot into existing strategies, not new machinery: 7z/rar/dmg join the zip-manifest strategy; PST/OST joins the mbox precedent; WARC likewise (§1.2).

**Mechanics that survive the split, restated on their owners** *(3.0 — the 2.x drafter prose retired; these behaviors, which 10,000+ records conform to, did not)*:

- **Selective mailbox declaration** (mbox attestation). A mailbox may hold 10⁵ messages, so message members are declared **selectively**: the ingest/re-attest surface accepts named 1-indexed ordinals (the 2.x `--messages 5,12,90-95` surface, re-homed — §12.18 open question 10), each recorded as a `message/rfc822` member row at `msg=<N>` (blake3 over the un-stuffed member bytes, plus the message's Date / From / Subject and byte length). Declaration is **cumulative and idempotent**: a re-declaration unions the newly-named ordinals with the already-declared set, an identical re-declaration folds, and a changed hash for a declared ordinal is a **hard error**. An undeclared run attests the mailbox summary only (message count, byte size, date span), no members.
- **The eml reply-text trim** (the `body` op for `message/rfc822`). The derived body is the **reply text only** — the `text/plain` part, else `text/html` reduced to text — with trailing quoted history trimmed from the first confidently-matched marker (an `On … wrote:` attribution directly above a `>`-quoted line, `-----Original Message-----`, an Outlook header block or underscore rule, or a `>`-run to EOF), keeping everything when no marker matches (**prefer false negatives**) and keeping signatures. Part member rows skip the text alternatives the body consumed.
- **HTML addressability** (the `el=` selector). *(3.6)* `el=<path>` names an element by its child-index path over **every** element in document order (§6.1.1) — there is no addressable-element predicate, because there is no longer a subset. What an address materializes is still determined by the element it names (§6.2). What shapers and the resolver share is now the path walk itself, which has no configuration to drift; which elements a drafter chooses to *emit a segment for* is a separate, freely-revisable heuristic that changes no address's meaning.
- **Manifest lint conventions.** An empty archive attests a blocking `partial-content` issue. `embed-unreferenced` is relaxed for `manifest`-disposition records (the members ARE the content) and for `message/rfc822` records (parts are message *members*, not body-flow assets — the normalizer links an inline image into the body where it belongs).

#### 12.4.2 One construction path (the constituent model)

`recordbuild.Build` remains the one construction path — `add_blocks` → `open_section`/`add_segment` (which enforce body⟺lossless per segment) — and `recordbuild.finish` emits + grammar-validates it. These are the same ops `compile` replays from a decomposed `manifest.corpus`, so attest / re-attest / decompose / compile / normalize all construct records identically: shapers and agent passes construct the authored layer through it, and a shaped record decomposes then recompiles byte-for-byte. This is the substrate the LLM normalizer works on: it edits the decomposed **constituent files** (per-segment body sidecars + the ops manifest) *(3.5: the description sidecars retire with the field)* and recompiles deterministically — never rewriting a monolithic markdown blob — which makes whole classes of structural corruption unrepresentable. (`begin_from_post` seeds the Build for re-attest; `begin` seeds it from a `meta.yaml` for compile.)

#### 12.4.3 Corpus-local shapers

A corpus can specialize the shaping of its *own* content without editing the package — **corpus-local shapers**, the successor of the 2.x corpus-local drafters (the iMessage sub-drafter foremost), same trust boundary, same registration pattern. `<corpus_root>/shapers/*.py` load via the same `local_code` loader (§12.3.1); a module claims records by origin or form id — a producer-declared `corpus-origin-schema` meta or a stamped origin-block id (§7.2) — and builds the authored content zone in place of (or ahead of) the generic mapping-driven shaper and the interpretive agent. A shaper constructs through `recordbuild` and reuses the public address/member helpers (`compute_embed_metadata`, `transforms.html.is_addressable`), so its addresses and member transports line up with the resolver by construction. The record envelope (title, origin fields) stays the generic path's; only the authored content zone is delegated. Format-specific shapers, atoms, and overlays for private content live in the owning corpus repo, never in the package.

#### 12.4.4 Perceptual fingerprinting (opt-in)

Fingerprints attest at ingest where the knob resolves on (§7.7). A segment gets a `perceptual:` only when `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override)` resolves on — precedence CLI (the ingest/re-attest `--fingerprint` / `--no-fingerprint` override) › origin overlay › mime-schema `fingerprint` knob › off (the default; §7.7). The resolved knob (`true` = the atom's default algorithm, an algorithm name, or a list) becomes concrete per-atom algorithms via `fingerprint.algos_for_atom(atom, knob)`, computed by `fingerprint.text_fingerprints` / `image_fingerprints` (a registry keyed by algorithm, mirroring `content_hash._STRATEGIES`). Algorithm selection is schema-only; the CLI flag is on/off.

#### 12.4.5 Deterministic auto-classification *(removed in 2.0)*

*Retired with the composite namespace (§7.4).* The `classify_when` engine, `corpus classify`, `corpus reclassify`, and lint's `classification-stale` all retire; deterministic membership is now a ledger **harvest rule** over the same fact base (`ledger.md` §10), evaluated ledger-side (`ath ledger harvest`) as a pure function of the corpus's mechanical record facts — so `draft` no longer carries any classification hook at all.

#### 12.4.6 Bulk re-attest (`corpus reattest`)

The attested layer is a deterministic function of (retained artifact + schemas + tooling), and `id = blake3(artifact)` is unchanged by re-derivation — so regenerating it is an in-place `.md` rewrite, and `git diff records/` surfaces exactly which records a schema / overlay / tooling change affected. **`corpus reattest`** `[target] [--mime/--host/--state] [--dry-run] [--fingerprint]` sweeps the attested layer (§8.3) across the corpus — an unchanged record re-derives byte-for-byte and is not rewritten (idempotent; `--dry-run` reports the set, writing nothing). *(3.1: the 3.0 `--status` selector re-keys to the derived-state predicates of §4.1 — e.g. formless-only; concrete flag names are tooling-time detail.)* Unlike the 2.x `corpus redraft` it succeeds, re-attest never touches the authored layer (§4.4.7), so it needs no authored-refusal guard; authored-layer sweeps are **re-normalize** dispatches through the queue (§8.5). The **`corpus draft` verb retires**. Distinct from `corpus compile`, which reassembles a record from a decomposed *manifest* (§12.4.2) rather than from the source *artifact* — different inputs, different jobs. (`records.dumps` serializes a record to canonical text without writing, so reattest can compare against disk.)

Pipeline-state provenance is the `touch[]` chain (§4.2.2): each pass appends a `<pkg>.<module>@<version>` (or `<model-id>`) identifier, so the latest touch's tooling version encodes the spec era of the record's current shape and re-run targeting reads it. There is no separate `conversion_method` / `conversion_tool` field.

#### 12.4.7 Cross-reference resolution

Cross-reference reconciliation is a **read-time derived view, never a stored rewrite** *(3.4)*. Segment bodies carry the source's own hyperlinks verbatim and nothing else (§4.3.2.2, §5.1); the mapping from those URLs to corpus ids is computed when asked and never written back. Given a record's stored body, the view scans its segment bodies for **hyperlinks** (`<a href>` → other resources) — *not* same-transport inline media, which is already a member row + segment (§12.4.1) — and for each:

1. Maps the URL → `id` by querying the corpus's URI index (`records.build_uri_index` — every record's origin `uri:` list keyed by identity, §12.3.9).
2. If matched, **reports** the pairing `(href, id)`. The body is not touched.
3. If unmatched, the URL stands as what it is: a reference to something outside the corpus, which the same view will pair automatically once that target is captured.

*(3.4: steps 1–3 previously **rewrote** the body in place, substituting a raw intra-corpus wikilink `[[<id>|original link text]]` — the form §5.1 now retires. Three reasons it had to go, beyond consistency. It is a **stored derivation**: the pairing is recomputable from the URI index at any moment, so writing it down creates a second copy that can disagree with the first — and does, the instant a target is re-captured or an origin gains a `uri:`. It **damaged faithfulness**: the body is a lossless rendering of the addressed content (§4.3.2.2), and a substituted wikilink is neither what the source said nor recoverable from it. And it **polluted the ledger's citable surface**, since verification reads segment bodies as verbatim quotable text — an anchor text severed from its href, or a bare hash, is not something a claim should be able to quote. No record in either hub ever carried the rewritten form, so nothing is migrated.)*

This is purely mechanical: the view reports links the original content contained and never invents one. Being a view rather than a sweep, it needs no re-run after a batch of captures — the next read simply pairs more of them.

**Reconciliation tooling.** The on-demand counterpart ships as `corpus links` (per-record) and `corpus crawl` (frontier BFS): both extract a record's `<a href>`, resolve relatives against its origin URI, normalize, and look each up in the URI index. A hit means the reference is already captured; a miss is the crawl frontier. `corpus links --show-captured` annotates which is which. Link extraction filters hrefs through `urls.is_crawlable_href`, which keeps client-side routing fragments (`#/route`, `#!/route` — on a hash-routed SPA the fragment *is* the resource identity) while dropping bare anchors (`#section`) and the `javascript:`/`mailto:`/`tel:` schemes.

### 12.5 Normalize

Normalization is the **one authoring pass** (§8.1): it renders a record under its named form contract, the span's editorial header fields riding with it (§4.2.3). It is executed by a **shaper** (deterministic tooling registered per form or manifest strategy — the successor of the 2.x draft strategies) wherever the record's declared form mapping makes the shape mechanical, and by an interpretive agent session (through the queue, §8.5) wherever judgment is required; most records are a composition — the shaper writes the form, the agent authors what only judgment can (the editorial header fields, descriptions, faithfulness issues). The agent works over the same derivation ops any reader uses (`corpus body`, the introspection ops, `transcribe`) — nothing it consumes is privileged or unreproducible.

#### 12.5.0 Shapers

A **shaper** is deterministic normalize tooling: it reads the origin overlay's `form:` mapping (§7.2) and the form overlay's decomposition contract (§7.8), consumes derivation ops, and emits the authored content zone through `recordbuild` (§12.4.2) — the form section with its codebook, envelope segments (`turn=` addresses, codebook indexes, timestamps in the form's convention), event segments, attachment markers, structural byte-marks. Its touch is `<pkg>.shape.<form-id>@<v>`; a combined pass appends `+<model-id>` when interpretive work rides the same pass. Shapers live in the package (generic, mapping-driven) or corpus-local under `shapers/` (§12.4.3). A shaper failure on a malformed unit is parse-tolerant per the standing principle — log, mark with an issue, continue.

#### 12.5.1 The interpretive pass

The normalizer authors the record's stored faithful form — faithful-form work only:

- Authors the stored content zone from the derived body and the introspection ops (where a shaper hasn't already written the form), improving formatting fidelity (broken tables, malformed lists) and resolving encoding ambiguity where determinable. *(3.1)* A stored rendering rides a named form (§4.1): the interpretive pass authors a content zone only under the record's declared form or one it asserts through §4.4.6's gate. *(3.5)* The pass authors **no prose about the record at any scope** — the derived title/description stand or stand empty (§4.2.3), and there is no scope-specific narration left to write. What remains is rendering, extraction, and disclosure.
- **Extracts losslessly wherever extraction is possible** — text printed inside an image as a co-addressed `text/ocr` segment, a rendered table as a `text/data-table`, speech as a transcript. *(3.5: this replaces the retired describe step, and it is the amendment's substantive demand on the pass. Where the old pass wrote a sentence about what an image showed, the new pass either transcribes what the image says or leaves the marker alone; the members block remains wholly attested and off-limits either way, §4.3.1.4.)*
- Places assets as **body-empty markers** at their addresses, typed by the most specific atom overlay that honestly fits (§7.3) — the overlay id is the only answer the record gives to "what is this region."
- Surfaces fidelity problems as `<!--context issue/<id>-->` blocks in the annotations zone — typed codes at addresses, no prose (§4.3.3.2).
- Declares the form span(s) and their contract-declared fields (§4.3.2.1); a record whose content changes shape partway carries more than one span.
- Re-segments where judged appropriate (structural only).

The pass MUST preserve faithfulness (§1.5 principle 3): no information that wasn't in the source. *(3.5)* And it may add no information *about* the source: descriptive content has no destination — not a body, not a header, not an annotation. If it cannot be rendered losslessly it is not recorded, and the marker plus the bytes are the honest answer.

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
    # ...the agent normalizes $id in-session: faithful rendering, lossless
    #    extraction, form spans, fidelity issues, re-segmentation; recompiles...
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

**Where each pattern lands.** A recurring *deterministic membership* pattern becomes a ledger **harvest rule** (`ledger.md` §10 — authored in the ledger, evaluated by `ath ledger harvest`). Recurring *body-shape* guidance becomes origin-overlay guidance (per host / subtype, §7.2) or an atom overlay (per form, §7.3). Recurring *link structure* the capture should FOLLOW becomes a `capture.references` declaration (§7.2); recurring link structure the record should RENDER is a form span over it (§4.3.2.1) — *(3.5: `capture.relations` retired with the relation block; there is no lift-to-annotation path left.)* Domain conventions for authoring claims land in the ledger's `facts/SCHEMA.md` or a concept schema (`ledger.md` §4.4), never in corpus schemas.

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
- **`corpus session <capture|list>`** bundles a Claude Code session — its `<id>.jsonl` transcript plus the `<id>/` sidecar tree (sub-agent transcripts, tool-result payloads, workflow state) — into ONE deterministic zip via the reusable writer core above (the first shipped consumer of the `pack` engine), then ingests it as a zip manifest so every member is a directly-addressed `path=<member>` row (the transcript is never transcribed). It binds the `claude-code-session` producer-export origin (§7.2, uri-less, keyed on a `session_id` field); `--from [user@]host` sources a session from another machine over ssh/rsync. Sessions are personal (a transcript embeds every tool result verbatim) — they belong in a private corpus.
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

**The member index (2.1).** The route from a bare blake3 to its container (§2) is a derived map — `member transport hash → (container id, member address)` — built by walking every record's members block *(3.4; §4.3.1.4)*, exactly as the URI index is built (§12.15 applies: rebuilt-on-start; persistence is a deferred perf optimization). Binary-store lookup falls back through it when no standalone file exists, recursing through nested containers, and the resolver cache absorbs hot paths — a member deep inside a solid compressed stream (a tgz) costs one streaming decompress on first touch and is cache-warm after. The promoted record's origin `uri:` (its containment lineage, §8.1) is **history, never consulted for byte lookup** — residence must stay free to change out from under it.

*(3.4)* This index is why the members block is **stored** rather than derived on the fly. Every row in it is mechanically recomputable from the artifact, so storing it looks redundant — but the index is built by one pass over `records/`, and rebuilding it from artifacts instead would mean opening and parsing **every** artifact on start, including multi-megabyte HTML and containers with tens of thousands of members. The roster is stored precisely so that the cross-record questions — *which record holds this hash, at what address, how big* — cost no artifact reads at all. That is also the whole justification for the row's four-key shape (§4.3.1.4): a field that does not serve a cross-record question is not paying for the space it occupies in a file the indexer reads end to end.

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
| element | `el=<path>` · `el=<parent>.[<a>-<b>]` · list | marked-up / HTML text *(3.6: a dotted child-index path over every element in document order, §6.1.1; output determined by the element — an `<img>` renders to an image, a `<video>`/`<audio>` or `<a href="data:…">` attachment carrier materializes to its raw bytes, a text element to its region)* |
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
| attachment | `attachment=<N>` | a `work` transport's exposable members (PDF embedded files / portfolio members; OOXML embedded objects — §7.1) |
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
- ~~**Segment-anchored mechanical references.**~~ *(Closed in 3.5 by removal: the reference block retires (§4.3.3.3), so there is no anchor to pin. The link's position is wherever the faithful body renders it, which is a real segment address by construction — the DOM→segment mapping the gap needed is the rendering itself.)*

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
7. ~~Whether `canonical_strategy` computes at ingest attestation or as a derivation op when re-enabled.~~ *(Moot in 3.5: the field is retired, §7.1. The question returns only with a strategy that works — and then it returns alongside the harder one it always deferred, which is what a content-canonical hash means for the HTML population.)*
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
2. ~~Whether health's derived-editorial coverage should distinguish *empty-because-unmarked* from *empty-because-bare*.~~ *(Superseded in 3.5, and the distinction turned out to be the wrong axis: the metric itself was measuring conformance to a universal display slot that no longer exists. It is replaced by **per-cohort column coverage** — §12.27.)*
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

### 12.24 The stored-address gate: region grammar enforced, and the sweep behind it (non-normative)

**The defect was a missing gate, not a missing rule.** The region grammar (§6.2: `x,y,WIDTH,HEIGHT` as fractions in `[0,1]`) had exactly one enforcement site — the render path, which validated correctly and raised a clear error. But nothing ever asked it about a *stored* address, so a segment could carry `bbox=0,0,2272,1920` (pixels) or `bbox=0.5,0.5,0.95,0.85` (corner coordinates) and pass `lint`, `health`, and `compile` while resolving to nothing at all. A lossless transcription's address is the only provenance it has (§4.3.2.2), so this was a citation pointing at no bytes, wearing a green light.

Two rules close it. **`address-region-invalid`** (ERROR, text-only, in the default gate) holds every stored region-op value in every address — sections, segments, embeds, body wikilinks — to the grammar the transform renders through, sharing one implementation so the two cannot drift. It declines to judge a non-numeric value, since `bbox=` is polymorphic and a spreadsheet's `A1:D20` is a different grammar under the same key. **`corpus lint --resolve`** (opt-in, reads artifact bytes) materializes every stored address and reports what fails — the only mechanical proof that an address means anything, and now the check the normalize pass's resolve-and-read-back rule is measured by. Building it required distinguishing *names nothing* from *names something with no bytes*: an `el=` naming a `<table>` or a span envelope (`el=1-8`) is a correct, complete citation with no file to render, so the render path raises a typed `NotMaterializable` and the gate counts those as declared coverage rather than defects. Without that distinction the pass reported 26 false positives in a 30-record sample.

**The sweep** (`migration/bbox-fraction-33.jsonl`, touch `corpus.migrate.bbox-fraction-33@0.1.0`): 1,823 bad addresses across 981 public records — 96% on one origin, propagated by copying a sibling's address rather than measuring one — plus 14 across 8 private records. Each address was classified against its parent surface's **real pixel dimensions**, never by pattern: 1,683 were the full element (`0,0,W,H` matching the measured size exactly) and became `0,0,1,1`; the rest divided into readings that the geometry *forced* (a size reading that overflows the frame leaves corners as the only valid one, and vice versa) and readings that stayed genuinely ambiguous. Each swept record was re-linted and **re-resolved** before its edit was kept, and rolled back otherwise; acceptance was "introduced no new finding", so an unrelated pre-existing defect could not hold a repair hostage.

**What the sweep refused to do is the substantive part.** 10 records were held rather than converted on a derivable-looking pattern, and the follow-up pass (`migration/bbox-held-33.jsonl`) settled every one of them by the only method that works — resolve the candidate crop and check it against the text the segment claims to have read. That pass corrected the holding rationale itself, which had over-generalized from a single proof: of the 7 records held on one origin, **5 were simply right under the corner reading** (crops matching their bodies verbatim), 1 needed the *size* reading (the corner reading stopped mid-content, dropping words the body carries), and only **1 address in the entire corpus** was genuinely mis-addressed — its transcription was read off the correct frame and the timestamp typed wrong, which the segment's own description proved by quoting the on-screen caption that appears 8 seconds earlier. The remaining 2 records were not defective at all: their embeds are valid inline **SVG**, and "cannot identify image file" was a missing rasterizer, not corrupt bytes — the dimension oracle was the SVG's own `viewBox`, which the stored boxes matched exactly. That misdiagnosis is why the render path now raises `NotMaterializable` for a valid vector image instead of an error.

**The generalizable finding is that the correct repair is per-record, and no wider unit.** The same origin used *both* readings across its records, and the two corpora disagreed about the same overflow shape: on the public hub the corner reading was proven by tiling and by crops matching bodies, while on the private statements it demonstrably **truncated** a transaction table mid-row and size-with-overshoot was right. Any blanket conversion — by origin, by shape, or by hub — would have silently destroyed content somewhere. Ground truth is bytes, per record.

A well-formed crop that names the wrong region is still beyond mechanical reach, which is why the authoring rule remains *resolve it and look at it*. The retimed record is the proof of that rule's value in both directions: an accurate description is what caught an address its own gate could never have flagged.

### 12.25 The index-span hole, and the fabricated addresses under it (non-normative)

**The `--resolve` gate had the same shape of hole it was built to close.** A span address has no single byte surface, so the materialization transforms short-circuited every range form to `NotMaterializable` *before looking at the numbers*. An out-of-range span therefore reported as declared coverage while the bare index beside it errored: `el=94-102` on a nine-element artifact read green, `el=145` on the same record read red. That hid 8 of the 17 out-of-range addresses in the corpus, and three whole records the single-index check never saw. Bounds are a property of the address, not of whether it happens to materialize, so they now live in one place (`functional_uri.parse_index_span`) that both axes call before either decides what kind of thing it is holding — the same consolidation the region grammar got, for the same reason. The count is taken lazily on the EPUB path: a span needs it, a single index reaches the identical check inside materialization, and one record there carries 22,293 addresses.

**What the closed hole exposed was not drift but fabrication.** 16 addresses across 6 records were invented. On these captures the source prose arrived as `<div>`+`<br>` soup carrying **zero addressable elements**, so interleaved prose segments had no anchor — and because `address:` is a required field, the normalize pass wrote plausible-looking numbers instead of reporting that it could not derive one. They survive no test: non-monotonic against true document order (`el=145` sits after `el=152`), matching neither the artifact's element list nor the cleaned body's nor any line numbering. This is a distinct failure from §12.24's drift, which at least copied a real address from a sibling; here there was no source to copy.

**The repair is the tightest true interval** (`migration/el-interval-33.jsonl`): prose lying between real elements K and K+1 takes `el=K-(K+1)`. A range has always been a document-order interval rather than a set — that is what makes the drafter's own `el=1-<max>` wrapper honest over unaddressable prose — so the form is a clarification, not a new one. Coarser than the content is an ordinary citation; false is not, and precision below the element remains the citing side's `quote:` (§4.3.3). Every one of the 16 was **proved by source position**: the segment's own verbatim prose located in the artifact bytes, required to fall between the two endpoints' offsets — 12 by a phrase unique in the whole artifact, 4 (one-word `Disclaimer` tails, 8 occurrences each) by *every* occurrence falling inside the interval, which holds the interval whichever one the segment renders. The verifier refused the repair three times before it passed, twice for real bugs in the proof and once for an acceptance rule that demanded uniqueness where universality was the stronger evidence.

**One record is held, and it is the tooling's own doing.** An artifact with zero addressable elements has no endpoint to write and cannot omit the field either — the segment grammar requires an address — so `draft/html.py` has always emitted a bare `el=1` fallback that is guaranteed not to resolve. The unresolvable address there is the *drafter's* output, faithfully preserved through normalize, and green under `lint`, `health`, and `compile` alike. The mechanical layer now at least declares it (`partial-content/unaddressable-content`, warning), but what addresses whole-document content when the axis has no members is an open question for the address grammar, not a record defect to sweep. Filed as such rather than given an invented answer — which is the whole lesson of the class.

*(3.6 answers it, and answers it by deletion: with the address space total, an artifact cannot have "no members" — `<div>` soup is addressable like anything else, and the held record's prose takes the path of the element that actually contains it. The `unaddressable-content` issue and the `el=1` fallback both retire with the predicate that produced them, §12.28.)*

### 12.26 The roster amendment: one attested index, and the narration moved out (non-normative)

**The conflation.** The per-asset `<!--embed-->` block was doing two unlike jobs under one grammar. On a container the roster **is** the content — `form/manifest` says so, and the private hub's 1,029 container records carry **77,502** of these blocks between them, one of them 22,293 in a single 4 MB record. On a prose artifact the same block was a per-asset descriptor, holding an authored `description` beside mechanical byte-facts, and duplicating a placement the content zone already stated. The two jobs pull opposite ways: a roster wants to be exhaustive, mechanical, and cheap to scan; a descriptor wants to be selective and authored. Nothing could satisfy both, and what actually happened is that the mechanical half quietly acquired an authored field.

**The trap that made this urgent rather than merely tidy.** Attested-layer strip-and-re-derive carried authored embed descriptions across the cycle by keying them on the member's `transport` hash. A member the normalizer had *pruned* is absent from that map, so re-attestation re-derived it from the artifact **bare** — and because re-attestation sweeps every record by default, the description was destroyed permanently and the pruned member came back anyway. The house pruning pattern was therefore unsafe in a way no gate could see. A wholly attested roster with no authored column removes the trap by construction: there is nothing to carry across, so nothing can be dropped in transit.

**The shape.** One block, rows of exactly `address`, `media_type`, `transport`, `bytes` (§4.3.1.4). The admission rule is written into the normative text on purpose — a field must answer a **cross-record** question without opening an artifact *and* be an identity-or-accounting fact, not a reading of content — because the failure mode here is accretion, one reasonable-looking field at a time, and a rule decides the next case where taste would relitigate it. `bytes` earns its place on both counts and is the one dropped field whose derivation is *not* uniformly cheap (a zip reads it from the central directory, but a tar needs a streaming pass and an inline `data:` image a base64 decode). Pixel dimensions fail the first test and are derived; an email member's `from`/`subject`/`date` pass the first and fail the second, which is exactly why they were the tempting case.

**Why the roster stays stored** even though every row is recomputable: the member index is built by one pass over `records/` (§12.15). Deriving it instead would mean opening and parsing *every* artifact on start — the 43 MB HTML pages, the 22,293-member bundle — to answer a question the records could have answered for free. Storing a four-key roster is what keeps `corpus://<member-hash>` resolution and `promote` cheap. It is also the reason the row is closed: the indexer reads these files end to end, so a field that serves no cross-record question is not free.

**Nothing migrates.** The per-asset blocks are deleted and the members block replaces them; the ~15,600 descriptions stored in the retired field go with them. There is no re-homing sweep, and no obligation falls on a member as a result — a member is not required to be placed in the body, or promoted, or described. Where a record wants to narrate an asset, that is ordinary authoring on the block that places it, done when a normalize pass has reason to; it is not a destination for text written against a withdrawn contract.

The alternative was considered and refused. A sweep moving each description onto the address-matching block reads as conservative and is not: it lifts prose written under a retired grammar into the authored layer, where it becomes indistinguishable from prose a pass actually wrote, and where re-attestation can no longer correct it. A description worth having is worth writing again.

**The migration is lazy, and it is re-attestation.** The reader accepts both forms; only the new one is written. Conversion is not a text transform — an HTML `el=` member never stored `bytes`, so the new row needs the artifact — which means conversion *is* an ordinary re-attestation, and no bespoke migration verb is required. Two properties keep it from converting records by accident. Serialization is **form-preserving**: a record read from legacy per-asset blocks is written back as legacy per-asset blocks, so touching a record for an unrelated reason never converts it. That obligation reaches the decompose→compile substrate as well, which is where it nearly failed: a working dir rebuilds the record from a manifest whose member row is deliberately closed to the retired fields, so the working dir must carry them as opaque data alongside it. Preserving what a record already stores is a different obligation from letting an author write it, and a substrate that conflates the two converts every record it touches. And conversion **reports what it drops** — re-attestation prints the count and addresses of the retired descriptions it is shedding, because a record silently losing fifty of them is the kind of change an operator should watch happen rather than discover afterward.

**The body-link retirement rides along.** Segment bodies stop carrying intra-corpus links (§4.3.2.2, §5.1). Both forms — `corpus://` functional URIs and raw-blake3 wikilinks — were specified, were enforced by lint rules, were rendered by nothing, and were used by **no record in either hub**: 0 occurrences of either, and 2 records containing a `[[` at all. Cross-artifact connection was always carried by the source's own URLs and reconciled at read time (§12.4.7); within one transport a link was never needed, because an inline image is its own positioning segment on the artifact's own axis. A stored corpus address duplicates a derivation and can disagree with it, which is reason enough on its own. Untouched, and worth stating because the strings look identical: a promoted record's origin lineage `uri: corpus://<container>?<address>`, present on 3,942 records, is capture **history** and is never consulted for byte lookup (§12.15).

### 12.27 The faithfulness amendment: what a record stopped saying, and what it got back (non-normative)

**One rule, arrived at from four directions.** 3.1 derived a record's state from what it carries. 3.2 derived its display identity from role-marked schema fields. 3.3 made *no faithful shape exists* an assertable judgment rather than a gap. 3.4 closed the members roster to identity-and-accounting facts under a written admission rule. Each removed a place where a record asserted something about itself, and each stopped one step short of the general case — 3.2 kept an interpretive rung and called the form section header "the vouch's new home"; 3.4 abolished per-asset descriptions and re-homed narration onto the placing segment. 3.5 states the rule the four were converging on and takes the last step: **a record asserts nothing about itself.** Where a region cannot be faithfully rendered, the record says *the bytes are here, at this address, of this type* and stops.

**What the corpus was actually holding.** Measured across both hubs at the amendment (7,417 public + 4,407 private records):

| | public | private |
|---|---|---|
| whole-record section `description:` (the vouch) | 6,793 | 451 |
| span-scope section `description:` | 0 | 20 |
| segment `description:` — 2,037 of 2,041 on `image` markers | 1,593 | 448 |
| → with **no** faithful sibling segment at the same address | 1,255 | 384 |
| `entry:` on content segments (the fossil) | 9,654 | 3,282 |
| `entry:` on structural segments (the byte-mark) | 61 | 0 |
| `relation` context blocks | **77,310** | 0 |
| `reference` context blocks | 48 | 0 |
| `issue/generic-title` (a detector's verdict, stored) | 5 | 2,648 |
| genuine capture-fidelity issues | 161 | 36 |
| records carrying `canonical:` | 7,153 | 57 |

**The descriptions were substituting for transcription work not done.** The sample that settled it is a specifications page whose entire capacity table is a single PNG: the marker's description read *"A rendered table titled 'Refrigerant System Capacities,' with an Application column and a two-column Metric/Imperial Specification…"* — a lossy paraphrase standing in front of a table, uncitable, unverifiable, and indistinguishable in the record from content that had been transcribed. Where they were *not* doing that they were restating the atom: 155 of them described logos, on segments already typed `image/logo`. The 1,639 with no faithful sibling are the honest cost, and they do not vanish silently — where the reason a region went unrendered is a fidelity problem, it becomes a typed `issue` at that address, which converts a paragraph of prose into a closable worklist item.

**Ledger exposure, measured before deciding.** Of 2,706 quote-bearing citations across the ledger, **9** anchor on text that exists only in a description; the rest quote segment bodies. The ledger's own scribe convention already read "transcription is evidence; description is not," so the layer that consumes corpus evidence had reached this conclusion first. The nine re-anchor or retire in the same change as the sweep, per the standing rule that `ath ledger verify` is green in the commit that moves evidence, never after it.

**`entry:` was a fossil, and the data says which kind.** It labelled the line a segment contributed to the 1.0–2.x stored table of contents; 3.0 moved that job to the structural segment and made the TOC a derived rendering, but the field stayed. By 3.5 it sat on 12,936 content segments against 61 structural marks — the field spec'd for *the source's own text* used 61 times, the vestige 200× more. A maintenance checklist shows both halves at once: four segments labelled `Inspect`, `Lubricate`, `Replace`, `Rotate`, every one of them verbatim in the artifact's bytes and therefore a byte-mark that was never an authored label at all — and beside them one labelled `Breadcrumb`, which appears nowhere in the source, because it is the record naming its own structure. The first four reclassify to structural segments carrying `mark:`, where they become checkable and populate the derived TOC for free; the fifth goes. Renaming the survivor settles the confusion the shared name created.

**The annotations zone was 99.75% not annotations.** 80,203 context blocks; **197** of them genuine capture-fidelity observations. The rest split two ways. `issue/generic-title` — 2,653 blocks — is a detector's verdict about a *derived* value, persisted into records where it goes stale the moment either side changes; it is a health query (§12.21) and computes on demand. And `relation` — 77,310 blocks across 4,995 records, **67% of the public hub** — was the alldata "Related Information" rail, lifted per the origin overlay's own instruction: *"Drop it from the body (navigation, not content), but do not lose it."*

**That last one is the amendment's point, and it inverts.** The rail is in the stored artifact bytes — the overlay deliberately exempts it from the chrome strip ("they carry the crawl graph") — and it is addressed. It is simply **absent from the faithful body**: of 77,310 lifted links, the target URL appears in a segment body 224 times, the link text 39 times, and the rail's address matches an existing segment 6 times. So this was never duplication. It was 77,310 pieces of source content exiled to a side-channel because a record could hold only one form, and a page that is an article *and* an index had nowhere to put the second half. Lifting the whole-record section's sibling prohibition removes the reason; a trailing `<!--section index-->` over the rail's span brings the links home as faithful content, in source order, with source labels, citable. The amendment's ledger of removals ends with a **restoration**, and it is the larger number.

**What derived identity looks like afterward.** Title survives everywhere it mattered: all 7,379 public records with a title today have an artifact- or origin-layer candidate (an HTML `<title>` is a byte-fact), and 3,762 of 4,369 private. The **607** private records that lose theirs expose a *schema* gap, not an editorial one — their mime or origin overlay wants a `role: title` mark on a field the block already carries — and that is a mechanical fix, not an authoring pass. Description is different by design: only 282 records derive one from bytes, so **7,226 records (61%) resolve empty**, and empty is the correct answer. It means the source said nothing about itself under that role.

**`canonical:` was stale state reading as live.** Disabled on the write path 2026-06-28 after `blake3-canonical-pdf` was found to collapse unrelated scanned PDFs — but never swept, and the spec then asserted "no record carries `canonical:`" while 7,210 did. They survive re-attestation because the attested-layer strip touches the body, not the frontmatter; a record re-attested during the 3.4 migration still carries its 2026-era hash. 20 values collide across 92 public records. The mechanism is nonetheless inert in practice, for a reason nobody wrote down: a new capture discards its canonical, so the *incoming* side's `content_key()` is `None` and the dedup fold short-circuits regardless of what is stored. That is exactly the kind of safety that evaporates the moment someone re-enables the write path assuming the corpus is clean.

**The sweep, and why it is one change and not six.** Roughly 9,300 description fields, 12,936 `entry:` fields, 77,358 `relation`/`reference` blocks, 2,653 stored detector verdicts, and 7,210 frontmatter hashes come out; 77,310 links go in; 10,659 whole-record sections take a derived envelope. They land together because they are one rule, and because the gates would otherwise contradict each other in the interval: `segment-description-required` currently **mandates** a description on every body-empty marker, so the rule does not dissolve, it **inverts** — every conformant marker in both hubs becomes non-conformant on the same commit the spec text changes. A spec that is law cannot spend a migration window disagreeing with every record it governs.

**The health metric it replaces, and why the old one was measuring the wrong thing.** 3.2 gave health a **derived-editorial coverage** tally — records deriving a non-empty title versus empty, the empty set standing as the role-marking worklist (§12.21) — and left open whether to split *empty-because-unmarked* from *empty-because-bare*. Both the metric and its open question assume every record owes one display string. Under §4.2.3's cohort enumeration it owes none, so the tally would park 607 private records on a worklist of things that are already correct — a signal that never goes green, which is the same failure this amendment removed from `issue/generic-title`. The replacement is **per-cohort column coverage**: for each origin, form, and mime population, what fraction of the fields that schema declares are actually populated across its records. That number is actionable in a way a title census never was, because a gap in it names a specific field on a specific overlay.

**And it immediately names the first real gap.** The private hub is already well served — `bank-statement` declares six columns, `tax-slip` five, `claude-code-session` eleven, and a statements table beats the title it replaces outright. The public hub is not: of its formed population, `form/bulletin` (1,060 records) declares five genuinely useful columns while `index`, `procedure`, `document`, and `article` — 5,732 records, 77% — declare none, and only two of 33 public origin overlays declare any fields at all. Two different causes, and only one is a defect. `document` and `article` declaring nothing is **correct** — a generic shape has no universal facts, and that population enumerates by origin. But the alldata `index`/`procedure` cohorts have structured facts sitting in plain sight, in the URL (`#/vehicle/46076/component/3894/itype/432` carries vehicle, component, and information type) and in the captured breadcrumb. Recovering them wants a capability the origin namespace does not have yet: a **URI-pattern derive** populating `extended_fields` from the origin URI, the same shape `capture.assembly`'s `derive` patterns already use against filename conventions (§12.3.11). That is the amendment's clearest follow-on work, and it is additive — no record changes, one overlay declaration per host.

Two properties make the sweep auditable rather than merely large. It is **subtractive** for everything except the index-section restoration, and subtraction of a field with no successor needs no re-homing decision per record — the 3.4 precedent holds: *an abolished field has no successor, and a description worth having is worth writing again*, this time as a transcription that can be checked. And the one **additive** half is mechanically derivable from the bytes it restores: the rail's links, labels, order, and addresses all come from the artifact, so the restored span is verifiable against the same artifact the record already attests, not authored from memory.

### 12.28 The addressing amendment: a whitelist is a versioned contract (non-normative)

**It already happened, and nothing noticed.** Commit `76deb2e`, 2026-06-25, added `<dl>` to the HTML addressable-tag whitelist — a one-line fix for a real gap. 458 public artifacts contain a `<dl>`; on **455 of them**, `el=N` names a different element before and after that commit. One record shifts 811 addresses. No gate could see it, because a record does not record which whitelist produced its addresses, and both readings are internally consistent.

The corpus appears to have escaped. Where segment bodies were distinctive enough to probe, addresses match the *current* whitelist — a later fleet re-attest re-derived them. That is timing, not design, and the near-miss has a sharper edge: **re-attest re-derives the attested layer and never the authored one**, so a normalizer-written `el=17` is regenerated by nothing. What saved those addresses is that most alldata authoring happened after June 25. The next whitelist change has no such coincidence waiting for it, and the whitelist had a standing queue of good reasons to change — `<li>` is unaddressable today, which means an index form's individual entries cannot be cited.

**So the fix is not a better whitelist.** Widening it is the same bet again at a later date; versioning it stores the problem in every record forever. What the predicate was actually doing was **two jobs at once** — deciding which elements may be *named*, and deciding which elements the drafter *emits a segment for* — and it was shared by the drafter and the resolver, which is exactly why a change in authoring taste silently re-pointed stored addresses. Separate them and the failure mode has nowhere to live: the address space becomes total and mechanical, and the emit heuristic becomes free.

**Why a path rather than a bigger flat counter.** Total addressing alone fixes permanence; it does not make an address say anything about structure. The path form does, and two of its consequences are worth more than its cost:

- Containment is a prefix test, so *"is this rail inside that span"* stops needing an artifact read. The alternative was a bespoke `subtree_extent` derivation — tooling built to recover information the address could simply carry.
- **An envelope can no longer over-claim.** A subtree *is* its own address. The min–max integer range could express a span wider than the content it held, and did: §12.24's drift, §12.25's 16 fabricated addresses, the 1,839 records whose over-wide content address straddles their related-information rail (§12.27). Those are one defect class with one root, and it is not a class the new form can represent.

**The measured cost, and where it bites.** Real paths on real artifacts: median 26–35 characters, 13–18 components; p90 39–51; max 61–63. Every alldata address shares the SPA shell prefix `1.2.2.1.2.2.1.3.`, and the longest addresses (50+ chars, 26 components) are the recursively-nested navigation `<ul>` — which is to say the worst addresses in the corpus would be the ones §12.27's restoration writes. A record-level `address_prefix` was measured as a mitigation and **declined**: no heuristic-free definition pays (longest-common-prefix over all elements is empty on 399 of 400 artifacts; so is a single-child descent from body — a body always carries stray script and mount siblings), and the only definition that works is a per-host content selector, which would reintroduce a config dependency on the very axis this amendment removes one from. It stays free to add later: absent means absolute.

**The migration is mechanical and exactly verifiable**, which is the reason to be willing to do it at this scale. Old index → new path is a pure function of an immutable artifact: walk the old filtered list and the new total tree over the same bytes, pair them positionally, rewrite. No judgment enters anywhere, every record's mapping is checkable on its own, and the rewrite proves itself by re-resolving each address to the same element the old one named. Scope: ~7,000 HTML records and **1,731 ledger anchors** — 63% of all anchored evidence in the ledger, and by far the largest re-anchoring the system has done.

Two retirements ride along, both by deletion rather than repair. The `partial-content/unaddressable-content` issue and the guaranteed-unresolvable `el=1` fallback that provoked it (§12.25) have no meaning once every element is addressable — the `<div>`-soup record's prose takes the path of the element that contains it, which is what it always should have been able to say. And `is_addressable`, shared by drafter and resolver since P2, ceases to exist as a shared predicate; what remains is a drafter-side emit heuristic under a name that admits it.

**What the apply taught, and what a mechanical migration cannot decide.** The rewrite ran clean on the sample and on the fleet dry-run, and then the gate — a whole-corpus `lint` diff, taken before and after — reported 2,148 new errors. The cause was not the walk but the reading of the retired range form. `el=<lo>-<hi>` was an **interval over the document**, first element through last and inclusive of what lay between; that is precisely why normalizers reached for it, since bare prose in a `<div>` had no element of its own and could only be fixed between two landmarks. Mapping such an address to the ordered LIST of its endpoints — "which is what it always structurally was" — is right about an *authored* cross-subtree claim and wrong about a migrated interval: the list names the two landmarks the prose is not in, silently narrows the claim, and collides with the point addresses those landmarks already carry. The correct replacement is **the tightest §6.1.1 address containing the interval**: the ancestor's subtree when one endpoint holds the other, when both land in one child, or when the interval covers every child; otherwise the sibling range over the endpoints' slots in their nearest common ancestor. Resolution parity is then exact in both directions — a legacy flat range and a 3.6 sibling range are both unmaterializable, so no address gains or loses a byte surface in the migration. That correction alone took the new errors from 2,148 to 31.

The residue is the interesting part, because it is **not** mechanical. A flat interval could claim a span wider than the content it held, and several such intervals on one record collapse onto the single container that actually holds them: `el=1-14` and `el=2-11` become the same address, which is the truth about them and a duplicate claim. §6.1.1 cannot represent the over-claim — that is the amendment's point — and it must not represent it silently either. So the engine carries a **neutrality gate**: every record is linted before and after its own rewrite, and any rule whose count rises holds the record, unmigrated. A held record keeps the legacy grammar in full (it is never stamped, so the resolver still reads its integers the old way, and the attest guard refuses to stamp it out from under them) and goes to a worklist for deliberate re-addressing. Twenty public records held — thirteen on aliasing intervals, four whose stored section envelope stops agreeing with the span of its own segments, two whose interval spans the path root's own children and therefore has no sibling-range spelling at all, and one on `form/schematic`'s asset-rendering XOR. Everything else migrated with the gate reporting *zero* new findings on either hub, which is the claim worth making: not that the migration was careful, but that it is measured.

**The two layers migrate in one order, and the manifest is what joins them.** Because a held record keeps legacy integers, its ledger anchors must keep legacy integers too — an anchor rewritten to a path against a record that still reads integers is the one way this migration can silently break a citation, and neither layer can detect it alone. So `corpus remap-el --apply` runs first and its run manifest becomes the **eligibility set** for `ath ledger remap-el`: only records the corpus remap actually rewrote may have their anchors rewritten. The stamp cannot serve as that signal, in either direction — after the corpus applies, "stamped" no longer distinguishes *migrated* from *was never in scope*.

**Sequencing.** This lands *before* §12.27's record sweeps. Both touch every record; re-addressing first means one pass rather than two, and spares the restoration from writing `el=` ranges that would immediately need remapping. Version numbers are identifiers, not a schedule.

### 12.29 The derived-envelope amendment: a fact checked against itself (non-normative)

**What made it visible.** The section `address` survived four amendments' worth of "stop storing what you can derive" because it did not *look* like an assertion — it looked like the span's definition. The tell was in the gate: `section-address-span` re-derived the envelope from the children and compared it to the stored one, which means the system already knew the derivation was authoritative and was spending a rule to check the copy. Every other instance of that shape had already been removed — `status` (3.1), the stored title/description (3.2), the per-member descriptive fields (3.4), the stored detector verdicts (3.5) — and each was found the same way, by noticing what a check was actually checking. sjrahn named this one on sight, twice, looking at records: *"why do we have address on the section block? this is just repeating what's on the segments? why?"*

**Measured before deciding.** Across both hubs at the amendment: **10,646** records carry a single section spelled whole-record (6,780 public + 3,866 private); **26** are multi-section; **5** are multi-section *and* carry a form declaring editorial marks. The last number is what settled the design — the population that could have been affected by re-keying the editorial ladder was five records, and re-reading §4.2.3 showed it should not be re-keyed at all but deleted.

**The divergence the field was holding up.** 3.5 wrote that *a form contract marks nothing* and that *no section, at any scope, contributes to a record's display identity*, and retired the frontmatter override in the same breath. The implementation did not follow: `_form_editorial_candidate` still read a whole-record section's fields, and three bundled form overlays — `form/statement`'s `editorial.title_template`, `form/conversation`'s and `form/contact-card`'s `role: title` — still declared marks the spec no longer admits. Nothing failed, because the *fields* those marks would have read were themselves retired in 3.5, so the rung resolved empty in practice and the divergence stayed invisible. Removing the stored envelope forced the question: the whole-record lookup had exactly one caller, and that caller was already spec-illegal. **Two records** across both hubs still carried a frontmatter override (one per hub); they retire with the rung.

**The migration.** Wholly subtractive and mechanical: strip `address:` from every section header. There is no re-homing decision, because the value is recomputed identically by every reader — the sweep's own proof is that the *derived* envelope before equals the derived envelope after, on every record, which holds by construction since the children do not move. The one thing to watch is not the records but the readers: any consumer that keyed on `address is None` to mean *whole-record* has to re-key or retire, and the honest replacement for "the record's own asserted form" is **the first form section in the content zone** — which under §4.3.2.1's significance order is the content span, what the artifact is *for*. `section-address-span` retires outright: with nothing stored there is nothing to disagree.

**Why this is the last one.** The section block now carries a form id and the fields that form declares, and nothing else. There is no universal slot left for a field to accrete into, which was the structural argument 3.5 made for removing the previous three. The count of universal section-header fields is zero, and zero is a number that cannot drift.

---

### 12.30 The placement amendment: a member's rendering, and the work already spent twice (non-normative)

**What made it visible.** sjrahn, reading a normalized AllData article that carried three PNG members — one positioned with a bare marker, two transcribed into `text/data-table` tables in the article's own body: *"this is suppose to be on their promoted records. the current representation as i see it should be illegal."* The article was not wrong under 3.7; it was doing exactly what §4.3.2.2 licensed. What the shape hid is that the two transcriptions are renderings of bytes with their own blake3, and the corpus had no way to say so.

**Measured before deciding.** Public hub: **14,300** member rows over **9,840** distinct transports, of which **9,109 are placed**; **1,573** transports appear in more than one record; **3,842** rows carry a parent-side rendering across **1,406** records; and — the number that decided it — **558** members were already transcribed in more than one record, **1,481** transcription passes spent producing renderings of bytes that had already been rendered. One PNG is placed by 668 records. Private hub: **77,502** rows, only **5,337** placed (the container manifests are overwhelmingly unplaced, which is the rule working: an unplaced member owes nothing), **2,089** parent-side renderings across **96** records. Promotion scope is therefore **9,109 + 5,337 = 14,446** distinct members — a large number of new records, and the cost sjrahn weighed and accepted: *"I am worried about the case of duplicating and splitting work done if an out of band promotion happens there is an ambiguity of where the body content for an image should be placed. we can instead just force it always to the leaf records."*

**Why a segment kind rather than a block or a link.** Three alternatives were considered and each fails on a rule the spec already holds. A **block** would put positioning in two places — the roster row already carries the address — and would sit in a zone with no reading order, which is the one thing a placement must have. A **stored `corpus://` link** is the body-link grammar 3.4 retired and the residence marker §12.26 refuses; it would also rot, since bytes may move between standalone and contained residence without any record changing (§2). Re-using the **`image` marker** and simply forbidding the transcription beside it fails hardest, because the marker is not neutral: the atom is precisely how a segment declares residue (§7.3), so a marker at a member address keeps asserting *irreducible bytes here* about bytes the record does not own. The kind is needed for what it withholds, and §4.3.2.3's byte-mark is the exact precedent — a fifth kind that carries a position and no content claim. This is the sixth.

**The address the leaf's rendering takes.** A promoted table image renders whole, and every axis its mime schema declares names a *part* — so the migration would have had to fabricate one (`bbox=0,0,1,1`, a full-region rendering wearing a crop). This is the general form of the defect §12.25 named on one instance of it: there, a `<div>`-soup HTML artifact with no addressable element got a `el=1` the normalize pass invented because `address:` was required, and 3.6 closed *that* instance by making the HTML address space total. The instance closed; the hole did not. Wherever the addressed content genuinely **is** the artifact, every part-naming axis is the wrong tool and a required field forces a fabrication. 3.8 removes the requirement rather than inventing a better value: an **absent** address names the whole transport, mirroring the bare `corpus://<id>` (§4.3.2.2). The two guard rules — a marker may never be address-less; identity is still (`opener-id`, `address`) — keep absence a statement rather than a default.

**The migration, and the order that matters.**

1. **Finish 3.4 first.** The roster amendment shipped a dual reader and lazy conversion, and eleven days later **3,550 of 3,561** public records and **1,029** private ones were still on the retired per-asset block — so the dual reader was not a transition, it was the steady state. Legacy rows carry no `bytes`, and 249 of them carry an atom-overlay id (`image/photo`, `image/figure`) where a MIME type belongs. `corpus reattest` converts, recomputes, and re-sniffs in one pass over the artifact; run it to completion and delete the dual reader. **A lazily-migrated grammar is a grammar with two spellings**, and the second one does not decay on its own.
2. **Promote every placed member**, which requires the containment layer to stream an `el=` member out of an HTML container — the one family it could not reach, and the family holding 9,109 of the 14,446.
3. **Move each parent-side rendering to its leaf**, at the whole-transport address — and the chained renderings with them. 2,065 public segments address a crop *of* a member (`el=<path>&…`), of which **1,829 are whole-frame** (`bbox=0,0,1,1`, `bbox=full`, and two long-form spellings of the same thing) and lose the crop entirely, ~236 are genuine sub-regions and keep it, and a residue of ~16 wears an unrecognized suffix (`region=banner`, `part=2`, `caption=after`) and needs eyes. That the dominant case is a fabricated whole-frame crop is the same finding twice: it is the invented address this amendment removes, sitting in the very population the amendment re-homes. Where two parents transcribed the same member differently, the collision is a **judgment**, not a merge: hold and report, never clobber. Where they agree, one survives and the other's work is what the amendment was measuring.
4. **Re-anchor the ledger in the same change.** 23 citations anchor on a member address; 17 are `el=` into an HTML parent and move to the leaf, 6 are `path=` into a container and are untouched (they resolve member bytes directly and never quoted a parent's rendering).

**One form check retires with the arrangement it policed.** `form/schematic` declared `embed_rendered`, binding each member in the span to exactly one of {a `text/data-table` transcription, an `image` marker} — an XOR that was right for as long as the parent was where a member's rendering lived. Under 3.8 it never is, so both of its branches are `member-rendered-on-parent` violations, and the residual question it was reaching for — *has this sheet been read yet* — is demand on the sheet's own record (§8.5), not a conformance failure of the page that embeds it. Retired rather than re-keyed: the amendment answers it structurally, which is strictly better than a per-form check answering it by declaration. Its two findings (`form-embed-not-rendered`, `form-marker-superseded`) go with it, and so do the four lint helpers that existed only to scope member ownership to a span.

**What this does not touch.** A region of the record's own transport — a rastered PDF page, a `bbox=` crop, a `frame=` still — has no member row and no leaf, and keeps its content-atom marker with its transcriptions beside it. sjrahn drew that line himself, correcting an overreach: *"your comment 'the parent needs no image segment ever' is only true for embedded images. for things like pdfs we take crops of rastered pages and stay within that record. this is only for things that are transports on their own within another transport."*

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
| **Members block** | `<!--members-->` — the record's unabridged roster of embedded assets, one row per member, closed to `address` / `media_type` / `transport` / `bytes`. Wholly attested; deduplicated by `transport:`. *(3.4: replaces the per-asset `<!--embed-->` block, whose descriptive fields moved to the `members` derivation and whose `description` moved to the block that places the asset — §4.3.1.4, §12.26.)* |
| **Section block** | `<!--section <form-id>-->` — a **form span**: a positional span of the content zone declaring a named structural form, carrying only the fields that form declares. Depth one, never overlapping; a record may carry several. *(3.0: the 1.0–2.x TOC-grouping role is retired — see Structural segment. 3.5: no universal header fields; the sibling prohibition on a whole-record span is lifted.)* |
| **Segment block** | `<!--segment <atom>-->` — the body's content atom: a lossless rendering of its addressed region, or a body-empty **marker** saying only where the bytes are and what type they are. *(3.5: a marker carries no narration.)* |
| **Structural segment** | `<!--segment structural-->` — a body-empty **byte-mark**: the source's own declared boundary (heading, outline entry, chapter, topic) at an address, with `level:` and optional `mark:`. The TOC is a derived rendering over these marks. |
| **Placement** | *(3.8)* `<!--segment placement-->` — a body-empty segment recording that a **member** sits at this position and nothing more. The member is named by the shared address, its record by the roster row's blake3 — derived, never stored. Placing a member obliges promoting it (§4.3.2.4, §8.1). |
| **Normalization pressure** | *(3.8)* Derived demand on a promoted member's record: the number of records placing it. A second source on the queue's one mechanism, beside the ledger's citation demand; ranks the queue, gates nothing (§8.5). |
| **Context block** | `<!--context issue/<id>[/<subtype>]-->` — an annotations-zone **capture-fidelity** observation, a typed code with no prose; record- or segment-scope (via `address:`). *(3.5: `issue` is the only namespace.)* |
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
| **Self-contained** | The universal container principle: every transport produces a single record (lifting nested-stream metadata when present). A raw archive is attested as a members-block roster of its contents. *(2.1: the former schema-declared `decomposable` disposition is removed.)* |
| **Container / member** | A container is an artifact whose content is other transports (an archive); a member is one such contained transport, rostered as a content-addressed row of the container record's members block (§4.3.1.4). |
| **Member / Unit** | A member is a transport with its own MIME and standalone byte identity (a manifest or exposable member row, promotable). A unit is content *within* one transport, reached by unit ops (`turn=`) under a form mapping — never a member. |
| **Promotion** | Minting a first-class record for a container member without copying its bytes: the promoted `id` is the member's blake3, resolved by streaming through the container (§2, §8.1). |
| **Disposition** | A mime schema's declared container-vs-transport judgment (§7.1, §1.2): `manifest` — the members ARE the content — or `work` — one transport whose internals surface as exposable members. Declared (origin-overridable), auditable, never sniffed per record. Distinct from the 2.1-removed `artifact_kind` (nothing explodes at ingest). |
| **Exposable member** | An internal member file of a `work`-disposition transport, rostered as addressable and promotable without being the content (a PDF's embedded file at `attachment=<N>`, a docx's pasted photo) — versus a **manifest member**, where the roster IS the content. |
| **Attestation** | Ingest-stamped byte-facts: artifact fields, the members block (manifest or exposable), structural byte-marks, sidecar lift. Deterministic; stripped + regenerated by re-attest. |
| **Derivation op** | A resolver operation deriving mechanical content from the artifact (`body`, `members`, `transcribe`, `turn=`) — on-demand, cacheable, pure or version-labeled (§6.4). |
| **Shaper** | Deterministic normalize tooling that authors a record's stored form from a declared form mapping — the mechanical half of the one authoring pass. |
| **Lineage-chained resolution** | Read-time materialization of content a record's bytes declare but do not contain, through the record's containment-lineage parent (§6.2). Derived, never stored. |
| **Default-member resolution** | Read-side sugar (§6.2): a bare op routes to a container's sole member of the required kind, or its declared primary (`pitm`); ambiguity fails loudly. Citation-safe by content-addressing; attested member rows keep explicit addresses. |
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
