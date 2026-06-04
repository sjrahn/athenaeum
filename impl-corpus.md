# Athenaeum — Corpus Implementation Guide

**Status:** living document. Updates as implementation matures.

**Companion to:** [`spec-corpus.md`](spec-corpus.md), the authoritative corpus-layer data contract — and [`spec-athenaeum.md`](spec-athenaeum.md) for how the corpus sits beneath the codex / compendium layers. This guide describes the *implementation* of the corpus / artifact-layer pipeline. The spec says what each artifact carries; this guide says how the pipeline produces it. Choices here may change as tooling evolves; the spec must not. (Note: this guide is still v10.15-shaped and predates `spec-corpus.md`'s model; a rewrite to the current corpus model is pending.)

The codex-layer counterpart is [`impl-codex.md`](impl-codex.md).

---

## 1. Scope

This guide covers the corpus side of the system: capture, reconciliation, normalization, custom-classification feedback, and re-normalization. It does **not** cover codex-record authoring, codex regeneration, compendium build, or any cross-corpus runtime resolution — those live in `impl-codex.md`.

What lives in this guide vs in the spec:

- **Spec (authoritative).** The data contract — every field, every hash declaration, every required behavior of records. Tooling consumers rely on these guarantees.
- **This guide.** How the pipeline produces those records: which scripts run in what order, where files land on disk, sharding conventions, MIME-detection strategy, perceptual-hash family selection, in-memory vs on-disk record build.

If the two ever conflict, the spec wins; this guide gets corrected.

---

## 2. Capture pipeline

A capture takes a target (URL, filesystem path, manual upload) and produces an artifact record plus its binary in the content-addressed store. The pipeline is content-addressed end-to-end: identity is the hash of the bytes.

### 2.1 Fetch

The fetcher is responsible for retrieving the bytes. Depending on the target:

- **HTTP/HTTPS URL** — fetch with redirect-following enabled. Capture the final URL after redirect chain; both the original requested URL and the final URL are valid identifiers and both are recorded.
- **Filesystem path** — copy from disk. The source path becomes a `file://` URI on the artifact record.
- **Manual upload** — accept the bytes and any provided origin URI from the operator.

Embedded resources (images in HTML, attachments in email, etc.) are captured **as their own separate artifacts**. A captured page yields one artifact for the page and one artifact per embedded resource. Cross-references between them are resolved during normalization (§3.2).

### 2.2 MIME detection

MIME detection runs **before** hashing because perceptual-hash family selection depends on MIME (see §2.3). Strategy:

1. **Extension hint** — fast path. If the source has a recognizable extension and the magic bytes are consistent with it, accept and proceed.
2. **Magic-byte sniffing** — fallback. Use a library like `infer` (Rust) or `mime-type` to inspect the first kilobyte.
3. **`unknown` sentinel** — when both fail. Record the gap; the artifact is still valid, it just won't get format-specific normalization or perceptual hashing.

The `content_type` field on the artifact record is set from this step.

### 2.3 Hashing

Hashes are computed per the artifact's MIME's base schema (§3.3.1 of the spec). At minimum:

- **blake3** — always. This is the artifact's `id`.
- **Format-specific perceptual hashes** as the base schema declares. Examples (illustrative; the canonical list lives in the schema files):
  - `image/*` → `phash` and/or `dhash`
  - `audio/*` → `chromaprint`
  - `video/*` → `phash` of keyframes and/or `chromaprint` of audio track
  - `text/html`, `text/markdown`, `text/plain` → `simhash`
- **Auxiliary hashes** the schema lists (commonly `sha256` for interoperability; rarely `md5`).

If a base schema is missing or incomplete for a MIME, fall back to blake3-only. The artifact is still valid; future schema updates can backfill the missing hashes via re-normalization.

### 2.4 In-memory record build

Build the artifact record's frontmatter in memory:

- `id` — the blake3 hash from §2.3 (the artifact's identity and filename stem).
- `content_type` — from §2.2.
- Capture provenance — see §2.6.
- `hashes` — populate per the base schema's declarations (other declared hashes; blake3 is the `id`).
- Base-schema extended fields — extract format-intrinsic metadata (file headers, embedded metadata: ID3 tags, EXIF, PDF info dict, HTML `<meta>` etc.).
- Custom classification schema fields — see §4.
- `status: stub` initially; flips to `draft` or `normalized` as later stages run.

The body starts empty and is filled by normalization (§3).

### 2.5 Dedup

Look up the artifact by `id` (blake3 hash) against the existing corpus:

- **Match.** The bytes are already in the corpus. Append capture provenance to the existing record (a new entry in `capture_dates[]`, and any new URI added to `uris[]`). Do not create a new record.
- **No match.** This is a new artifact. Write the record under `records/` and the binary under the `artifacts/` cache (§2.7).

Dedup is the natural side effect of content addressing — bytes that match an existing hash hit the same record, no special "is this a duplicate?" check is needed.

### 2.6 Capture provenance

Append per-capture provenance to the artifact record:

- Append the encounter timestamp to `capture_dates[]`.
- Add any new URI(s) (request URL, final-after-redirect URL, asset CDN URL, mirror URL, DOI, `file://` path) to `uris[]`. URIs are deduplicated as a set; order doesn't matter.

That's it. The artifact record carries `uris[]` (every URI known to resolve to its bytes, none canonical) and `capture_dates[]` (every timestamp the bytes were encountered). The pipeline does **not** record per-event metadata (which URI was actually used at which moment, what `method` was used, what redirect chain occurred). If recovering a particular (uri, date) capture package becomes important later, that's a job for an out-of-band capture log, not for the artifact record.

### 2.7 Storage layout

When reconciliation completes, the artifact record (tracked markdown) lives under `records/`, and the raw bytes (untracked cache) live under `artifacts/`. The implementation chooses sharding to keep individual filesystem directories tractable.

**Convention.**

```
corpus-{name}/
├── records/                            ← tracked markdown (Artifact Records)
│   └── {first-2-of-blake3}/
│       └── {full-blake3}.md
├── artifacts/                          ← UNTRACKED raw-bytes cache
│   └── {first-2-of-blake3}/
│       └── {full-blake3}.{ext}
├── schema/
│   ├── base/
│   └── classification/
├── capture/
└── .gitignore                          ← lists `artifacts/`
```

- **`records/` is tracked.** Markdown artifact records are the source of truth and live in version control.
- **`artifacts/` is the binary cache and is NOT tracked.** A corpus's `.gitignore` MUST list `artifacts/`. The cache is regenerable from blake3 plus capture provenance — destroyable and rebuildable at any time. The data contract is just "given a blake3, this corpus can produce the bytes"; the contract says nothing about *how*. Concrete implementations may put the cache on local FS, an object store, an S3-compatible bucket, a content-addressed CAS, or any combination. The local-FS shard shown above is the conventional starting point.
- **Sharding depth: one level, by the first 2 hex characters of the blake3 hash.** Both `records/` and `artifacts/` (when on local FS) use the **same shard depth.** That gives 256 buckets at one level. At ~10k records the average bucket holds ~40 — well under any filesystem's pain threshold. At 100k it's ~400. Deeper sharding can be added later if buckets get crowded; it's a layout choice, not a contract.
- **Full hash kept in filename.** A copy of `a7f3b2c1...md` outside its shard directory still names itself fully — useful for moves, backups, ad-hoc inspection.
- **Same shard depth for `records/` and `artifacts/`.** Symmetric is simpler when both are on local FS.
- **Capture staging** lives at `corpus-{name}/capture/` for in-progress captures; failed or abandoned captures sit there without consuming corpus identity space.

The spec is explicit that `records/` is tracked markdown and `artifacts/` is an untracked cache; everything else (path scheme inside `records/`, where `artifacts/` actually lives) is implementation-discretion. Consumers should not hard-code the path scheme — they should ask the corpus how to locate `{blake3}`.

### 2.8 Browser capture interactions (per-host recipes)

A web capture renders the page in a headless browser, drives it to surface all displayable media, then writes a self-contained SingleFile snapshot (CSS/fonts/images inlined as `data:` URIs). What the browser does before the snapshot is an ordered list of **interactions**, declared in the matching origin overlay's `capture.interactions:` (absent a recipe, a conservative default of `scroll: full` → `expand: all` → `scroll: full` runs). Each step is a single-key mapping; steps are best-effort (a bad selector never aborts a capture):

- `scroll: full` — scroll top-to-bottom, hydrating lazy-loaded / below-the-fold media.
- `expand: all` (or `details`) — open `<details>` and click `[aria-expanded="false"]` accordions/tabs.
- `click: {selector, repeat, delay_ms}` — advance carousels / load-more buttons.
- `wait: {ms}` or `wait: {selector, timeout_ms}` — settle async loads.
- `hover: {selector}` — trigger hover-reveal media.
- **`remove: ['#header', 'footer', '.ad']`** — delete matching elements from the live DOM before the snapshot. This is **where page chrome is removed.** The HTML drafter (§3.1) is deliberately mechanical and never guesses what is chrome, so stripping nav/header/footer/ads/cookie-notices is a per-host decision made here, where the site's real structure is known. Removing chrome at capture also keeps its images from being inlined and embedded.
- `eval: "<javascript>"` — escape hatch for site-specific DOM surgery (e.g. fetch-and-inject an AJAX-on-click tab, or promote a `data-*` high-res image URL into `src` so it gets inlined). An async-function string is awaited before the snapshot.

The snapshot's **fidelity** is a per-host tier (`capture.fidelity:` — `exact` | `balanced` | `lean`, default `balanced`; `FIDELITY_PRESETS` in `capture/__init__.py`). On asset-heavy SPAs the self-contained inlining (web/icon fonts in redundant formats, app icon-sprite SVGs) is re-inlined into every page and dwarfs the content, and content-addressed dedup can't share it (each page's whole-file hash differs). `balanced` drops redundant font/image/media alternates (≈−76%, no rendering risk); `lean` also prunes unused CSS (≈−91%); `exact` keeps everything for presentation-critical sites. The tiers touch only the gitignored `artifacts/` — the mechanical drafter reads DOM text/tables, so the drafted record is **byte-identical across tiers**. The resolved tier is stamped into a `corpus-fidelity` meta tag; `corpus capture --fidelity` / `corpus crawl --fidelity` override per run.

Capture config (`capturer`, `transport`, `fidelity`, `interactions`, `viewport`) lives on a per-host origin overlay (`schema/origin/web/<host>.yaml` — origin overlays are namespaced by URI scheme family, http(s) under `web/`) under a `capture:` section; global defaults can sit on the universal `origin.yaml`. See `scaffold.py`'s example overlay for the full annotated shape.

### 2.9 Capture routing & the video (yt-dlp) pathway

**Routing is overlay-driven — no hardcoded host knowledge.** The capturer is chosen by the origin overlay's `capture.capturer:` field (`browser` | `video` | a corpus-local name), defaulting to `browser`; `corpus capture --video` / `--no-video` are one-off overrides. There is **no** built-in video-host list — a host that should go to yt-dlp declares `capturer: video` in its overlay (so an un-declared video URL captures as HTML, or you pass `--video`).

The **video capturer** drives yt-dlp. Its options are declared in `capture.ytdlp:` and merged straight into `YoutubeDL` (full passthrough — e.g. `format`, `getcomments`, `impersonate`); the library forces `outtmpl` / `logger` / the resolved cookie file so an overlay can't break output, logging, or auth. `capture.cookies_from_host` (default `true`) pulls the capture URL's own-origin cookies from a running CDP browser (`--remote-debugging-port=9222`) into yt-dlp, so a logged-in session unlocks a host's full content (e.g. TikTok serves its full format ladder rather than the degraded anonymous one). yt-dlp writes a `.info.json` enrichment sidecar (post metadata + comments); **ingest renames it to `capture/<hash>.info.json` and leaves it in staging** — it is draft-time-only enrichment, never persisted to `artifacts/` (only the artifact carries the `<hash>` name there).

**Sidecar → origin block (draft time), then deleted.** The yt-dlp `.info.json` is *non-primary-source* metadata, so `draft/_sidecar.py` lifts every declared key into the **origin block** as a flat `ytdlp_<key>` field (`ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts, …) via `records.merge_origin_fields` — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when yt-dlp returns it) becomes a `ytdlp_comments` list field; `webpage_url`/`original_url` fold into the origin `uri:` aliases. The lifted key set is **schema-declared** — `sidecar.ytdlp_keys` on the video/audio mime schema (the drafter is mechanical, not hardcoded). One info.json datum is *structural* rather than flat: **`chapters[]`** (the uploader's outline). A video that ships chapter markers is sectioned by them — each chapter title becomes a section `entry` (the §4.3.2.2 TOC label) and the chapter bounds become the section time-ranges, in preference to the default speaker-run sectioning. Chapters are consumed into the section structure, never copied to a `ytdlp_*` origin field; a section's `entry`/address is metadata structure, **not** body content, so this respects the same primary-artifact boundary. The only body content a media drafter writes is the **transcript** (from the primary artifact's own audio). **Title** is normalizer-owned: the frontmatter `title` (like `description`) stays empty through draft; the normalizer authors it from the **namespaced** block-level candidates (a format-scoped artifact `*_title` — `html_title`/`pdf_title`/`docx_title`/`workbook_title` — or an origin `ytdlp_title`). The artifact block carries **no generic `title`** (ingest stamps none; a media drafter's title routes to the origin's `ytdlp_title`) — for display `records.title_for` reads the frontmatter `title`, falling back to the first artifact `*_title` then `ytdlp_title`. After a successful draft, `_cli/draft._cleanup_enrichment` **deletes** the sidecar; enrichment is one-shot (re-capture to restore; the extracted fields already persist on the record).

**Per-host transcription (draft time).** The audio/video drafters resolve the record's origin host and read the overlay's `transcription:` section (`draft/_hostcfg.py`): absent → the global `[corpus.transcription]` adapter; `enabled: false` → skip (an `info` issue, not a `warning`); `adapter`/`base_url` → a per-host backend that overrides the global even when the corpus default is `noop`.

### 2.10 Pagination reconciliation (capture time)

A paginated work — a thread / multi-page article / gallery a site splits across `?page=N` / `/page-N` URLs — is **one logical artifact**. The overlay's `capture.pagination` knob (browser capturer only; `capture/pagination.py` + `_reconcile_pagination` in `capture/__init__.py`) walks the pages and ingests a single merged record instead of capturing page 1 only or fragmenting the work into N content-addressed records.

Because both `corpus capture` and `corpus crawl` route through `capture_and_ingest`, the branch lives there: after the dedup short-circuit, if the resolved recipe declares `pagination` (and the capturer is `browser`), `_reconcile_pagination` runs. The flow:

1. **Walk + stage.** Each page is fetched through the **staging-only `capture()`** path (so its `url_rewrite` / `interactions` / `remove:` chrome-strip / fidelity all apply per page), its HTML **read into memory, and its staging file unlinked immediately** — `_sanitize_filename` drops the query string, so `?page=N` pages would otherwise collide on one staging name, and per-page bytes must never be content-addressed. The next page is found by `<link/a rel=next>` (the `<link>` survives the chrome strip — it lives in `<head>`) or a `next.selector` override; the walk stops at no-next, a repeat URL, or `max_pages` (flagged).
2. **Merge.** Page 1 is the framework. The content region is the declared `content_selector`, else the host's `canonical.content_selector`, else a **structural diff** of page 1 vs page 2 (`detect_region`: descend while exactly one matched-identity child differs; the container whose children then diverge is the region). Each later page's content children are appended into page 1's region, **deduped by element id or a normalized-subtree hash** (so a repeated quoted-OP / threaded post isn't double-counted); a page adding zero new children stops the walk.
3. **Ingest once.** The merged HTML is written to one staging file and ingested — the sole content-addressed artifact + record. A **single page** (no next link) skips the BeautifulSoup round-trip and ingests the original snapshot bytes verbatim, so its id is byte-identical to a non-paginated capture (and no pagination provenance is attached).
4. **Provenance.** The clean seed is the recorded origin URI; every constituent page URL — both the **bare site form** (what a crawl discovers) and the **pinned `url_rewrite` form** — is folded in via `records.add_origin_uri_alias`, and a `pagination: {pages, form, posts}` field via `records.merge_origin_fields` (`posts` is the **id-aware** item count — `_count_items` counts id-bearing region children when any are present, so framework `div`s riding inside the content region don't inflate it; else all children). When the merged item count falls short of an advertised `expect_count.selector` value, or `max_pages` was hit, a `pagination-incomplete` `warning` issue (capture-stage detector `corpus.capture`) is emitted rather than silently shipping a lossy record.

**Crawl interaction.** Recording every constituent URL as an alias makes the `capture_and_ingest` dedup short-circuit fire when a crawl later discovers `/page-N` — so it resolves to the merged record instead of re-capturing. `crawl._expand` additionally drops any link already in the expanding record's own origin URIs, keeping those pages out of the frontier (genuine content links — post permalinks, cross-thread — are kept). The corpus-local pin overlay + live re-capture for a specific host is the curator's follow-up.

### 2.11 URL equivalence (identity keys)

A record's origin URI list should hold **one URI per distinct resource**, and an inbound URL should match a record whenever it denotes the same resource — even when the spelling differs (query noise, `/page-1` ≡ bare). The per-host `capture.url_equivalent` overlay section (spec §7.2) declares this; the tooling reduces every URL to an **identity key** and compares keys instead of normalized strings.

- **The primitive** is `urls.identity_key(url, equivalent, *, url_rewrite)` (pure, stdlib-only). `urls.normalize_equivalence` coerces the overlay value (a `[{pattern, replacement}]` list or a `{query, rules, on_rewritten}` map) to a canonical config; the key is `normalize` → (if `on_rewritten`) apply `url_rewrite` first → (if `query: drop`) strip the query → apply the `rules` in order (via the shared `urls.apply_rewrite_rules`, which capture's `_apply_url_rewrite` also delegates to) → tidy a dangling delimiter → fold a sub-path trailing slash (`…/a/b/` ≡ `…/a/b`, via `_fold_trailing_slash`). **With no config it returns exactly `normalize(url)`**, so the layer is inert (opt-in) for any host that does not declare it. The trailing-slash fold is in `identity_key`, **not** `normalize`, on purpose: `normalize`'s output is the URL `crawl._expand` stores and re-fetches (a server may distinguish `/a/b` from `/a/b/`), so the fetched form keeps its slash while the comparison key folds it — a naive first-page rule (`…/page-1 → \1`) then converges with the recorded slashed origin (`…/slug.id/`) for free.
- **Identity ≠ fetch.** The identity key is a comparison key only. Crawl still stores the **fetchable** `normalize`d URL in its frontier/visited (those strings are fed back to `capture`); only the dedup *comparison* uses identity keys. Equivalence must never decide which bytes are fetched (that is `url_rewrite` / `interactions`).
- **The recipe-aware wrapper** `recipes.identity_key_for_url(corpus_root, url)` resolves the host's `capture` recipe once and passes its `url_equivalent` + `url_rewrite` to `identity_key`; the single-URL sites (`records.find_by_uri`) call it, while the bulk sites (`records.build_uri_index`, `crawl._expand`) memoize the recipe **by host** to avoid re-resolving the overlay per URI. `records.py` reaches `recipes` via a **call-time** `from .capture import recipes` to dodge the `records ↔ capture.__init__` import cycle.
- **The four identity sites** all key by `identity_key`: `build_uri_index`/`find_by_uri` (capture short-circuit + raw-URL `resolve`), `crawl._expand` (frontier dedup — also folds in the own-URI exclusion), `_reconcile_pagination` (the within-walk seen-set + the constituent-alias recording), and `records.add_origin_uri_alias(post, alias, *, corpus_root=)` — which, given `corpus_root`, skips an alias whose identity key matches an existing origin URI (keeping the origin block minimal; `corpus_root=None` preserves the exact-string back-compat). Where a host declares the page-form equivalence this **supersedes** the pagination bare+pinned dual-alias recording — a fragment-only pin (`#flat`) collapses to the bare form, while a genuinely path-changing `url_rewrite` still records both.

---

## 3. Normalization

Normalization brings an artifact from `status: stub` to `status: normalized`. The spec defines what the normalized record carries (§5.3 of the spec); this guide describes how the pipeline gets there.

### 3.1 Conversion (deterministic)

Conversion produces the artifact's body as well-formed markdown. It is MIME-driven and shells out to deterministic tooling. Per-MIME mappings:

- **`text/html`, `application/xhtml+xml`** → the **mechanical** HTML drafter (`draft/html.py`): it removes only non-rendered infrastructure (scripts/styles/comments), assigns `el=N` addressing to every element of the raw artifact, emits dedup'd image embeds, and emits one cleaned-`<body>` text segment. It does **not** strip page chrome — a universal tool can't reliably tell chrome from content (e.g. ASP.NET WebForms wraps the whole page in one `<form>`), and a wrong guess drops content silently. Chrome removal (nav/ads/cookie notices) is therefore a **capture-time, per-host** decision: list the selectors to delete in the origin overlay's `capture.interactions[].remove` (§2.8). Structural recovery (headings/tables/lists/equations) is the normalizer's job.
- **`application/pdf`** → text + table extraction. OCR via `tesseract` if the PDF is image-only. Page boundaries surface as headings or anchor markers usable from functional URIs.
- **`application/epub+zip`** → the EPUB drafter (`draft/epub.py` + the pure `corpus.epub` OPF reader). `self_contained` (one record per book, not decomposed — an EPUB is one work). Emits one bare `text` segment per spine (reading-order) content document, addressed `spine=<N>`, with a mechanically-cleaned structural-HTML body (same philosophy as the HTML drafter — non-rendered infrastructure stripped, structure kept), and **groups them into `<!--section-->` blocks by the book's navigation document** (EPUB 3 nav `<item properties="nav">` → EPUB 2 NCX `<navMap>`): top-level TOC entries become sections (`address: spines=<start>-<end>`, `entry:` = the part/chapter title), spine docs before the first TOC target become a synthetic `Front matter` section — the exact analogue of how the PDF drafter wraps pages by `get_toc(max_depth=1)` (`pages=`/`page=` ↔ `spines=`/`spine=`). A book with no usable nav/NCX drafts sectionless (flat top-level segments carrying their document title as `entry:`), like an outline-less PDF. Each `<img>` references a separately-stored zip member, so it becomes an **`<!--embed-->`** (addressed `spine=<N>&el=<K>`, `transport` = blake3 of the member bytes, deduped by hash across the book; the body keeps a src-stripped `<img data-el="K">` placeholder) — the HTML drafter's embed model, not the PDF's bare-image-segment model. That embed address **materializes** through `transforms/epub.py`: `spine=<N>` selects the OPF content document and binds a resolver over the book's zip image members, then `el=<K>` resolves the addressed `<img>` to its member bytes (decoded to a PIL image) — `corpus://<id>?spine=<N>&el=<K>` → the image. The body strips `<img src>` because it's redundant: the src lives on in the immutable artifact, and el-indexing is shared with the drafter (`corpus.epub.addressable_image_bytes`, same `_strip_non_addressable` + `_ADDRESSABLE_TAGS` axis), so a recorded address round-trips to byte-identical content (the resolved bytes' blake3 == the embed's recorded `transport`). Mirrors the HTML `el=` transform, but resolves a zip member relative to the spine document rather than an inline `data:` URI. Publication metadata (Dublin Core) lands as namespaced `epub_*` artifact fields (`epub_title` is the title candidate; `spine_item_count`/`toc_entry_count` record the shape). Canonical: `blake3-canonical-epub` (concatenated spine text — packaging-invariant; images don't perturb it).
- **`audio/*`** → speech-to-text transcription. Reference: Whisper. Output includes timestamps. Speaker turn markers where determinable. `audio/mp4` covers `.m4a` / `.m4b` audiobooks (an `.m4b` magic-sniffs as `video/mp4` on its generic ISOBMFF brand; `mime.detect` refines it to `audio/mp4` by extension so it routes to transcription, not the video keyframe path — embedded chapter markers and cover-art `mjpeg` are not consumed in v1).
- **`video/*`** → audio transcription + per-keyframe descriptions when the schema asks for them.
- **`image/*`** → visual description from a VLM + OCR text via `tesseract` if applicable.
- **`text/markdown`, `text/plain`** → passthrough with minimal cleanup. `conversion_method: passthrough`.
- **`unknown`** → best-effort fallback; emit a `metadata` body summarizing what little can be determined.

**One construction path (the constituent model).** Every drafter builds the record's content zone through the **`recordbuild.Build` ops** — `add_blocks` → `open_section`/`add_segment` (which enforce body⟺lossless per segment) — and `recordbuild.finish` emits + grammar-validates it. These are the *same* ops `compile` replays from a decomposed `manifest.corpus`, so draft / redraft / decompose / compile / normalize all construct records identically and a drafted record decomposes then recompiles byte-for-byte. This is the substrate the LLM normalizer works on: it edits the decomposed **constituent files** (per-segment body / description sidecars + the ops manifest) and recompiles deterministically — never rewriting a monolithic markdown blob — which makes whole classes of structural corruption *unrepresentable*. (`begin_from_post` seeds the Build for the draft/redraft path; `begin` seeds it from a `meta.yaml` for compile.)

**Perceptual fingerprinting is opt-in (draft time).** A segment gets a `perceptual:` only when `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override)` resolves on — precedence CLI (`corpus draft --fingerprint` / `--no-fingerprint`) › composite classification › mime-schema `fingerprint` knob › **off** (the default; a record with no `perceptual:` is normal). The resolved knob (`True` = the atom's default algorithm, an algorithm name, or a list) becomes concrete per-atom algorithms via `fingerprint.algos_for_atom(atom, knob)`, computed by `fingerprint.text_fingerprints` / `image_fingerprints` (a registry keyed by algorithm, mirroring `content_hash._STRATEGIES`). Resolution at draft only sees the mime default, **mechanical** composites, and already-present classify blocks; an **interpretive** composite (e.g. `composite/document`, assigned by the not-yet-built normalizer) applies on a later `corpus redraft`. Algorithm selection is schema-only; the CLI flag is on/off.

**Bulk recompile (`corpus redraft`).** A drafted record is a deterministic function of (retained artifact + schemas + tooling), and `id = blake3(artifact)` is unchanged by re-derivation — so regenerating it is an **in-place `.md` rewrite**, and `git diff records/` surfaces exactly which records a schema / overlay / tooling change affected. `corpus redraft [target] [--mime/--host/--status] [--dry-run] [--fingerprint]` applies the per-record draft core (`_cli.draft.derive_record`) across the corpus via a **clean re-stub** — `restub.restub_post` with the touch chain collapsed to the original ingest entry (no re-stub touch) — so an *unchanged* record re-derives byte-for-byte and is not rewritten (**idempotent**; `--dry-run` reports the set, writing nothing). It refuses `normalized` records unless `--force`, since re-deriving discards normalization. This is **distinct from `corpus compile`**, which reassembles a record from a decomposed *manifest* (the normalization edit substrate) rather than from the source *artifact* — different inputs, different jobs. (`records.dumps` serializes a record to the canonical text without writing, so redraft can compare against disk.)

Conversion writes pipeline-state metadata (`conversion_method`, `conversion_tool`, `conversion_date`) into a tracking sidecar or a frontmatter section the implementation reserves for re-run targeting. These fields are an implementation concern, not a record-contract requirement.

### 3.2 Cross-reference resolution (deterministic)

After the body exists, scan it for hyperlinks and embedded-resource references. For each:

1. Map the URL → blake3 by querying the corpus's URI index (any artifact whose `uris[]` contains this URL).
2. If matched, rewrite as a raw intra-corpus wikilink (`[[blake3|original link text]]`) or embed (`![[blake3]]`). No URI scheme prefix — these are layer-local references.
3. If unmatched, leave as a standard markdown URL or image embed. The link points outside the corpus and may be resolved by a future re-normalization pass when the target is captured.

This is purely mechanical. The normalizer does not invent links the original content didn't contain.

**Reconciliation tooling.** The on-demand counterpart to this resolution pass ships as `corpus links` (per-record) and `corpus crawl` (frontier BFS): both extract a record's `<a href>`, resolve relatives against its origin URI, normalize (`corpus.urls.normalize`), and look each up in `records.build_uri_index` — the map of every record's origin `uri:` list (including the dedup'd alias forms a page was reached by) to its id. A hit means the reference is already captured; a miss is the **crawl frontier** (what still needs capturing). `corpus links --show-captured` annotates which is which. Link extraction filters hrefs through `corpus.urls.is_crawlable_href`, which keeps **client-side routing fragments** (`#/route`, `#!/route`) — on a hash-routed SPA the fragment *is* the resource identity, so these are real outbound links, not in-page anchors — while dropping bare anchors (`#section`) and the `javascript:`/`mailto:`/`tel:` schemes. (Link-bearing navigation that a host renders as visual chrome — breadcrumbs, related-item rails — is therefore preserved at capture for crawl purposes via the origin overlay's `remove:` selectors, not stripped.)

### 3.3 Schema application

For every artifact, apply the base schema first (extracts format-intrinsic fields, sets normalization guidance). Then walk the corpus's custom classification schemas, evaluating each one's match condition against the artifact:

- `content_type` match — exact MIME or prefix.
- `uri` regex / domain match — does any URI in `uris[]` match?
- Prior-classification match — does the artifact already carry a `classifications:[]` entry the schema requires (the `has_classifications` condition)?
- Extended-field-value match — does the artifact have a field with a particular value?

Schemas that match contribute their declared extended fields and append an entry to the artifact's `classifications:[]` audit trail (with required justification). Multiple schemas may match; their fields merge with last-write-wins on collision. Custom classification schemas do **not** write to a frontmatter `tags` field — artifacts don't carry one (spec §3.5.1).

### 3.4 Contextualization (LLM-driven)

Refine the body and frontmatter:

- Apply matching custom classification schemas, recording each application in the artifact's `classifications:` array as `{schema, justification}`. The schema's contributed extended fields merge into top-level frontmatter per §3.3.2 composition rules. Justification is required for every application — mechanical for deterministic matches, substantive prose for LLM judgments.
- Improve formatting fidelity (broken tables, malformed lists).
- Resolve encoding ambiguity where determinable from context.
- Add or improve image alt text from visible content.
- Surface issues to `issues[]` (missing media, broken links, partial content, encoding corruption, format loss).
- Generate or refine `description`.
- Set `status: normalized`.

For artifact records, contextualization MUST preserve normalization integrity — the body remains a faithful rendering of the original content. No information that wasn't in the original.

### 3.5 Self-verification

Before declaring the record normalized, the normalizer confirms:

- The `content_type` matches the actual MIME of the stored binary.
- The `id` field (blake3 hash) matches the binary's hash.
- The on-disk record path matches the shard convention.

Failures here are bugs in the pipeline; they should fail loudly.

---

## 4. Custom-classification feedback loop

Custom classification schemas (§3.3.2 + §3.3.3 of the spec) are corpus-local and corpus-author-driven. They emerge from observed patterns in how the corpus is used, not from upfront design. The spec articulates the loop conceptually (and assigns it to the Curator agent); this section describes the operational implementation.

### 4.1 Pattern detection

The curator (human or agent) periodically scans the corpus for patterns that suggest a custom classification schema should exist:

- **Classification clusters.** A set of artifacts share an existing classification (the same schema applied to all of them) and would benefit from richer extended fields layered on top, gated via `has_classifications`.
- **URI-domain frequency.** Many artifacts have one of their `uris[]` matching a common domain, suggesting a platform-specific schema (custom field set for that platform).
- **Recurring extended-field values.** Many artifacts have the same value in a schema-extracted field, suggesting a sub-classification.
- **Codex-driven demand.** The codex/compendium layers (`impl-codex.md`) reveal patterns when authoring keeps reaching for the same kind of metadata that isn't currently extracted.

### 4.2 Schema authoring

When a pattern is worth formalizing, the curator drafts a custom classification schema:

```yaml
schema_type: classification
match:
  content_type: "..."
  uri_pattern: "..."                  # optional
  has_classifications: ["..."]        # optional
  field_match:                        # optional
    field_name: value
extended_fields:
  ...
```

The schema is committed to the corpus's `schema/classification/` directory.

### 4.3 Re-normalization sweep

To apply the new schema retroactively, the curator triggers a re-normalization sweep over the artifacts the schema's match condition matches. Re-normalization:

- Re-runs schema application (§3.3) against affected artifacts.
- Appends an entry to each affected artifact's `classifications:[]` array (with justification) and adds the schema's declared extended fields, without disturbing other frontmatter.
- Does **not** rewrite the body unless the body's content depends on schema-extracted fields (rare).

Sweep scoping options:

- By `uri` pattern — fastest, when the schema's match is URI-based.
- By `content_type` — useful when the schema applies to a whole MIME family.
- By prior classification — when the schema layers on top of an earlier classification (`has_classifications` match).

### 4.4 Schema evolution

As patterns refine, schemas iterate. A schema that initially matched too broadly can be narrowed; one that extracted weak fields can be augmented. Each iteration triggers another targeted re-normalization sweep on affected artifacts.

---

## 5. Re-normalization mechanics

Re-normalization is the general capability to re-process existing artifacts when something has improved: new schemas (§4), upgraded normalization model, better OCR/transcription tools, or newly captured artifacts that resolve previously unresolved cross-references.

### 5.1 When to re-normalize

- A new custom classification schema lands and its match condition selects existing artifacts.
- A base schema is improved (new extended-field declarations, better normalization guidance).
- A normalization model is upgraded.
- A conversion tool is upgraded (better extractor, better OCR, better transcription).
- An artifact has known issues that re-processing might resolve.
- Newly captured artifacts may resolve previously unresolved cross-references in older artifacts' bodies.

### 5.2 Scoping a sweep

The curator scopes the sweep using the most-precise selector possible:

- By conversion-tooling generation (the implementation's pipeline-state tracking), when re-running improved conversion.
- By normalization-model generation, when re-running improved contextualization.
- By `uri` pattern, when applying a URI-targeted custom classification schema.
- By prior classification (the artifact already carries a particular classification), when applying a layered schema.
- By `content_type`, when applying a MIME-keyed change.

### 5.3 Partial re-application

Re-normalization should disturb only the fields that need updating. The implementation should:

- Diff the current frontmatter against the would-be new frontmatter.
- Apply only the differences.
- Avoid churn on fields the change doesn't affect (descriptions hand-edited by curators, manually adjusted classification justifications, etc.).

This keeps re-normalization sweeps surgical and reviewable in git diffs.

### 5.4 Cross-reference re-resolution

A lightweight sweep that re-runs only §3.2 (cross-reference resolution) against artifact bodies. Useful when many new artifacts have been captured that may resolve URLs left as plain markdown in older bodies. Doesn't touch any other field.

---

## 6. Open implementation questions

These are flagged for follow-up; not all are blockers.

- **Sharding crossover** (applies to both corpus and codex). When does single-level hex-prefix sharding stop being adequate? At what record count do we move to two-level (`a7/f3/...`)? Likely a tooling-driven flag declared in `corpus.toml` (corpus side) or `codex.yaml` (codex side), with tooling rebalancing on change. `impl-codex.md §8` defers to this entry as the canonical write-up.
- **Binary cache GC.** Is the binary cache append-only forever, or does it have a GC pass for orphaned binaries (records deleted, hash unreferenced)? Deferred until corpus deletion semantics are needed.
- **URI index storage.** The URI → blake3 lookup needs an index. Build it on server start (rebuild from records) or maintain a side-file (`corpus/index/uri.db`)? Currently rebuilt-on-start; persistent index is a perf optimization for later.
- **Schema validation.** Should schema files themselves be validated (their match conditions parseable, their declared fields well-formed)? A `validate-schemas` tooling command would be useful.
- **Multi-corpus capture.** When the same content needs to land in multiple corpora (e.g., something captured personally and also of public interest), does the capture flow handle that, or is it a copy step on top? Currently a copy step; a "capture into multiple corpora" mode is a possible future feature.
