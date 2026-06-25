# Proposal: overlay-declared dependent references ("capture alongside")

**Status:** **accepted (decision 4.1) and applied to `spec-corpus.md`.** Implementation pending (see §9 sequencing). This doc is retained as the design rationale.
**Applied to:** `spec-corpus.md` §4.3.3 (intro), §4.3.3.3 (`reference` dual-source), §7.2 (`capture.references`), §8.1–8.2 (capture-stage note + boundary row), §9.9 (`references` view), §11 (depth-1 boundary).
**Author:** normalize-loop workstream.
**Motivating corpus:** the retail PDPs being added to `../corpus/` (e.g. `canadiantire.ca` — see its origin overlay).

---

## 1. Motivation

A product-detail page (PDP) links to a small number of artifacts that are *part of the
thing being captured* far more than the rest of the page's links are: the product manual,
the spec sheet, the install guide. Those targets are usually hosted off-site (a
manufacturer or CDN host), they rarely change, and they are exactly the documents a reader
of the PDP record will want next.

Today the only way to get them into the corpus is to **crawl later** — a same-domain BFS
(`corpus crawl`) that doesn't even reach an off-host manual, run out of band, that has to
*rediscover* which of a page's hundred links mattered. That is backwards: the page itself,
at capture time, knows which links matter — the overlay author can name them precisely
(`#nl-product-details a[href$=".pdf"]`). We want to **declare** those links as *dependent
reference material* once, per host, and have them treated as part of the original capture:
recorded on the PDP record as references, and — opt-in — fetched alongside it as their own
records.

This is not "crawl everything one hop out." It is "the overlay names the few links that are
reference material, and the tooling honors that declaration."

---

## 2. What already exists (build on these seams, don't bolt on)

This feature is ~80% wiring of mechanisms the spec and tooling already have:

| Need | Existing mechanism |
|---|---|
| Per-host "which links matter" declaration | **Origin overlay `capture:` section** (§7.2) — already declares `interactions`, `canonical.content_selector`, `also_capture`, etc. New sibling key. |
| Overlay *declares* an extraction → it materializes | **`aside` precedent** (§4.3.3): "an `aside` block exists **solely** where an origin or composite overlay declares the extraction." Same shape. |
| A record points at a separately-captured artifact | **`reference` context block** (§4.3.3.3) + **three-tier ladder** (§4.4.5): `attribution_text` → `source_url` → `source_uri: corpus://<id>`. Directional; host record never changes shape. |
| Engine-stamped, regenerated-on-rerun annotations | **`provenance: auto`** on the context block (§4.3.3.1) — already how the drafter stamps `issue`/`aside`. |
| Extract a page's outbound links, normalize, drop already-captured | **`corpus links`** — "what does this page link to that we haven't captured yet." |
| Fetch + ingest a discovered URL with robots/politeness | **`corpus crawl`** — BFS frontier, robotparser, resumable; calls `corpus.capture`. |
| Supporting capture folded into the primary record | **`capture.also_capture`** (§7.2) — *distinct* from this proposal (see §4.4). |

The genuinely new parts are: (a) one overlay section, (b) a mechanical emission path for the
`reference` namespace, (c) a depth-1, declaration-bounded capture mode, (d) a derived view.

---

## 3. Design overview

Four parts, each landing on an existing seam.

### 3.1 Declaration — `capture.references` on the origin overlay

A new optional list under the overlay's `capture:` section (corpus-local data, authored per
host → the package ships none, no host knowledge is hardcoded — same contract as every other
operational overlay section):

```yaml
capture:
  references:
    - match:                                  # all listed keys AND; multiple rules OR
        selector: '#nl-product-details a[href$=".pdf"]'   # CSS, resolved against the captured DOM
        href_pattern: '\.pdf($|\?)'           # optional regex on the resolved href
        text_pattern: '(?i)manual|guide'      # optional regex on the link text
        rel: 'nofollow'                        # optional <a rel> token match
      role: manual                             # corpus-local label → the reference block's role field
      capture: true                            # true: grab depth-1 as its own record; false (default): surface only
      cross_host: allow                        # references default to allow (manuals are off-host); 'same' restricts
```

- **`match`** — at least one key required; keys present are ANDed; rules are ORed. Matching
  runs against the *kept* DOM (after `interactions`/`eval`), so the overlay author scopes it
  the same way they scope `canonical.content_selector`.
- **`role`** — a corpus-local, schema-declared label (`manual`, `spec-sheet`, …), carried
  onto each emitted reference block. Like `issue.severity`, the value set is corpus-local;
  cross-corpus tooling treats unknown values gracefully.
- **`capture`** — `false` (default) = surface-only (emit the reference block, don't fetch).
  `true` = auto-grab (see §3.3). **Opt-in by design** — silently fetching external bytes on
  every capture is a footgun (size, ToS, manual→firmware→… chains).
- **`cross_host`** — references default to `allow` (the whole point is reaching an off-host
  manual), but *only* to declaration matches — this is never a general cross-domain crawl.

### 3.2 Surfacing — emit a `reference` block per match (the safe default)

At capture/draft, each matched `<a>` (resolved + normalized via `corpus.urls.normalize`,
deduped, dropping links already present as some record's origin URI) yields **one `reference`
context block on the primary record**:

```
<!--context reference
address: <segment-address of the link's segment>
quote: <verbatim link text>
provenance: auto                 # overlay-declared, mechanical — regenerated on re-draft
role: manual                     # from the rule
attribution_text: <link text>    # tier 1
source_url: <resolved href>      # tier 2 — present immediately
source_uri: corpus://<id>        # tier 3 — filled once the target is captured (now if capture:true, later otherwise)
-->
```

This rides the **existing** three-tier ladder unchanged. A surface-only reference sits at
tier 2 (`source_url`) until something captures the target and resolves it to tier 3 — which
can be the auto-grab below, a later `corpus crawl --references` pass, or a normalizer.

### 3.3 Auto-grab — depth-1, declaration-bounded (opt-in)

When a rule sets `capture: true`, after the primary capture+ingest the capturer fetches each
matched href **once**, ingests it as **its own record** (content-hash dedup — re-capturing an
unchanged PDP never refetches the manual), and back-fills the primary's reference block to
tier 3. This reuses `crawl`'s fetch path, robots, and politeness — it is `crawl` with the
frontier filtered to declaration matches and **depth fixed at 1**. Off-host is allowed (per
`cross_host`), but only to matches. No recursion: a grabbed manual does **not** get its own
references followed in this pass (depth >1 remains `corpus crawl`'s job — §11).

A CLI override toggles it for a one-off run: `corpus capture --with-references` /
`--no-references`. Absent any `capture.references` section the whole feature is inert.

### 3.4 Persistence & query — directional ladder + a derived view

The `reference` block is the persisted edge (PDP → manual), directional, on the host record,
resolved up the ladder. The **reverse** edge ("which PDPs reference this manual") is a
*derived* read, not stored — consistent with how the corpus derives back-references and with
the concept-join philosophy of "relate without either knowing about the other." A new
`references` derived view (§9, below) projects the namespace the way `concepts`/`issues` do.

---

## 4. The one real decision

Overlay-declared dependent links are **mechanical** (a selector fires) and **overlay-declared**
— but they want the **`reference` ladder** (which §4.3.3 currently frames as *interpretive*,
normalizer-authored). Two ways to reconcile:

### 4.1 Recommended — reuse `reference`, add a mechanical emission path

Make `reference` a **dual-source** namespace (mechanical *and* interpretive), exactly as
`issue` already is (drafter-deterministic *and* normalizer-content-meaning, §4.3.3.2):

- **interpretive** — the normalizer authors a citation it found in the content (today's use).
- **mechanical** — the drafter/capturer emits an overlay-declared dependent reference with
  `provenance: auto` (new; this proposal).

Both ride the same ladder and surface in the same view, distinguished by `provenance`
(auto vs asserted) and `role`. Note the existing §4.3.3 gate — "interpretive additions
(`reference`) require a referent actually present in the content" — is *already satisfied*:
the `<a href>` is literally in the page. The change is only that the emission can be
mechanical, not solely normalizer-driven, mirroring `classify_when`'s decoupling of *where
membership is decided* from *where the payload is consumed* (§4.4.6).

**Why this over a new namespace:** the semantic *is* a reference (a source the body points
at); the ladder is identical; a consumer asking "what does this record reference" gets human
citations and declared dependencies uniformly; and it avoids namespace proliferation.

### 4.2 Alternative — a distinct `dependency` namespace

Introduce a new mechanical context namespace (`dependency` / `attachment` / `asset`) that
rides the same ladder but leaves `reference` purely interpretive. Cleaner conceptual split
between "a source the author cited" and "material the page ships as a download," at the cost
of a second namespace and a second view (or a merged view). **Runner-up.** Recommend 4.1
unless you want the citation/download distinction to be a first-class namespace boundary
rather than a `role` field.

---

## 5. Proposed normative changes (wording for review)

Concrete edits, smallest surface that lands 4.1. Wording is drafted to drop in.

### 5.1 §3 — namespace table (`context` row)

No structural change. The row's open list already reads "`issue` (problems), `reference`
(cited sources), …"; leave it — `reference` already appears.

### 5.2 §4.3.3 — annotations-zone intro (the mechanical/interpretive split)

Current text names `issue, aside, relation` as mechanical and `reference` as interpretive.
Replace the two relevant sentences with (additions **bold**):

> The **mechanical** namespaces (`issue`, `aside`, `relation`) auto-populate *only* on real
> signal and *only* where schema-gated — in particular an `aside` block exists **solely**
> where an origin or composite overlay declares the extraction, and there are none absent
> that declaration. The **`reference`** namespace is **dual-source**: an *interpretive*
> citation the normalizer finds in the content, **or** a *mechanical*, **overlay-declared**
> dependent reference emitted at capture (`provenance: auto`, §4.3.3.3 / §7.2) — both require
> a referent actually present in the content (a citation, or a declared link in the page).
> Absent real signal the annotations zone is **empty** — the normal state for most records.

### 5.3 §4.3.3.3 — the `reference` namespace

Append a paragraph after the existing one:

> **Two emission paths.** A `reference` block is either *interpretive* — authored by the
> normalizer from a citation present in the body — or *mechanical* — emitted at capture from
> an origin overlay's `capture.references` declaration (§7.2), carrying `provenance: auto`
> and a corpus-local **`role`** field (`manual`, `spec-sheet`, …; schema-declared closed set,
> treated gracefully when unknown). A mechanical reference is pinned to its link's segment via
> `address:`/`quote:` (the link text) and starts at tier 2 (`source_url` = the resolved href);
> it advances to tier 3 (`source_uri: corpus://<id>`) when the target is captured — immediately
> when the overlay rule sets `capture: true`, or later by a `corpus crawl --references` pass or
> the normalizer. As an `auto` block it is regenerated on re-draft; an asserted (normalizer or
> human) reference at the same anchor is never overwritten.

### 5.4 §7.2 — origin namespace, operational overlay sections

Add a bullet under "Operational overlay sections", after `also_capture`:

> - `references:` — `[{match, role, capture, cross_host}]` — declares which of a captured
>   page's outbound links are **dependent reference material** (a PDP's product manual, a
>   spec sheet). Read after capture. Each rule's `match` (`selector` / `href_pattern` /
>   `text_pattern` / `rel`; present keys ANDed, rules ORed) selects `<a>` elements in the
>   kept DOM; each distinct, not-already-captured target (resolved + normalized) emits one
>   `reference` context block (§4.3.3.3) on the primary record, with `provenance: auto` and
>   the rule's `role`. `capture: true` additionally fetches the target **once, at depth 1**,
>   as its own record (content-hash deduped) and resolves the reference to tier 3; `capture:
>   false` (default) is surface-only. `cross_host: allow` (the default for references — manuals
>   are off-host) permits reaching declaration matches on other hosts, but **only** matches —
>   never a general cross-host crawl. Distinct from `also_capture`, whose bytes **enrich the
>   primary record** rather than forming separate, referenced records. Absent the section the
>   feature is inert (no hardcoded link knowledge).

### 5.5 §8.1 / §8.2 — pipeline

Note in the capture/draft stage description that the capture stage may (a) emit `provenance:
auto` `reference` blocks from `capture.references`, and (b) when a rule sets `capture: true`,
trigger bounded depth-1 dependent captures after the primary ingest. These are mechanical
(deterministic side of the §8.2 boundary), not normalize-stage work.

### 5.6 §9 — new `references` derived view (`§9.9`)

> ### 9.9 The `references` view
>
> The `reference`-namespace projection of the context view (§4.3.3.3) — the sibling of the
> `issues` (§9.2) and `concepts` (§9.7) views. Each entry carries the ladder
> (`attribution_text`, `source_url`, `source_uri`), the anchor (`address`, `quote`,
> `occurrence`), `provenance`, and `role`. The resolved `source_uri` is the directional edge
> to the cited/depended-on record; the reverse ("records that reference *this* one") is a
> corpus-wide read derivable from these edges but, like cross-record content addressing
> (§11), the corpus-wide index is not specified here. Computed on demand, never persisted.

### 5.7 §11 — out of scope (boundary clarification)

Add:

> - **Recursive dependent capture.** `capture.references` (§7.2) fetches declared references
>   at **depth 1** only; following a grabbed reference's own references — and any general
>   multi-hop crawl — remains `corpus crawl`'s job, not the capture-alongside path.

---

## 6. Tooling surface (non-normative — `impl-corpus.md`)

- `corpus capture` — reads `capture.references`; emits reference blocks; `--with-references` /
  `--no-references` override the per-rule `capture:` for a one-off; depth-1; off-host allowed
  to matches; `--dry-run` shows what would be grabbed.
- `corpus links` — gains a typed `--references` projection: the declared subset (with `role`),
  not all `<a href>`. The shared extractor `crawl` and the auto-grab both call.
- `corpus crawl --references <seed>` — resolves *pending* (tier-2) references corpus-wide or
  for a seed: fetch the declared, not-yet-captured targets and resolve them to tier 3. This is
  the "crawl later" path, now declaration-bounded instead of same-domain BFS.
- A derived `references` view in `corpus.derived_views` + the API/web surface, mirroring
  `concepts`.

## 7. Guardrails (restated)

- Auto-grab is **opt-in** (per-rule `capture: true` or `--with-references`); default
  surface-only.
- **Depth 1**, no recursion in the capture-alongside path.
- Content-hash dedup (free — store is content-addressed): re-capturing an unchanged PDP never
  refetches the manual.
- Reuse `crawl`'s robots/politeness/resumability.
- Cross-host only to declaration matches.
- Inert absent the overlay section.

## 8. Open questions

1. **Decision 4.1 vs 4.2** — reuse `reference` (recommended) or a new `dependency` namespace?
2. **`role` value set** — leave fully corpus-local (like `issue.severity`), or seed a tiny
   suggested vocabulary in `corpus init`'s example overlay?
3. **Where the reference anchor points when the link isn't in a drafted text segment** — most
   PDP "Manuals" links are in a button/region the drafter may not segment verbatim. Fallback:
   record-scoped reference (no `address:`) with `role` + `source_url`, or synthesize an anchor
   from the kept-DOM position. (Leaning record-scoped fallback.)
4. **Auto-grab timing** — inline in the capture stage (one `corpus capture` does it all) vs a
   separate explicit `corpus crawl --references` step the loop schedules. (Leaning: surface
   inline always; grab inline only under `capture:true`/`--with-references`, else defer to the
   crawl step — keeps a plain capture cheap and side-effect-light.)

## 9. Sequencing

1. Land the spec changes (§5) — settle decision 4.1/4.2 first.
2. Overlay section + surface-only path (emit reference blocks; `corpus links --references`).
   No fetching — lowest risk, immediately useful to the normalizer.
3. `references` derived view + API/web surface.
4. Auto-grab (`capture:true` / `--with-references`) and `corpus crawl --references`, reusing
   crawl's fetch path.
