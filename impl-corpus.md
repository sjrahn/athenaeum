# Athenaeum — Corpus Implementation Guide

**Status:** living document. Updates as implementation matures.

**Companion to:** [`spec-corpus.md`](spec-corpus.md), the authoritative corpus-layer data contract — and [`spec-athenaeum.md`](spec-athenaeum.md) for how the corpus sits beneath the codex / compendium layers. This guide describes the *implementation* of the corpus / artifact-layer pipeline. The spec says what each artifact carries; this guide says how the pipeline produces it. Choices here may change as tooling evolves; the spec must not. This guide tracks the current `spec-corpus.md` (ATH-CORPUS v1.0) model.

The codex-layer counterpart is [`impl-codex.md`](impl-codex.md).

---

## 1. Scope

This guide covers the corpus side of the system: capture, reconciliation, normalization, custom-classification feedback, and re-normalization. It does **not** cover codex-record authoring, codex regeneration, compendium build, or any cross-corpus runtime resolution — those live in `impl-codex.md`.

What lives in this guide vs in the spec:

- **Spec (authoritative).** The data contract — every field, every hash declaration, every required behavior of records. Tooling consumers rely on these guarantees.
- **This guide.** How the pipeline produces those records: which scripts run in what order, where files land on disk, sharding conventions, MIME-detection strategy, fingerprint-opt-in resolution, in-memory vs on-disk record build.

If the two ever conflict, the spec wins; this guide gets corrected.

---

## 2. Capture pipeline

A capture takes a target (URL, filesystem path, manual upload) and produces an artifact record plus its binary in the content-addressed store. The pipeline is content-addressed end-to-end: identity is the hash of the bytes.

### 2.1 Fetch

The fetcher is responsible for retrieving the bytes. Depending on the target:

- **HTTP/HTTPS URL** — fetch with redirect-following enabled. The original requested URL and the final-after-redirect URL are both valid identifiers; both land on the record's first **origin block** (`uri:` list, §2.6).
- **Filesystem path** — copy from disk. The source path becomes a `file://` (or filesystem-path) `uri:` on the origin block.
- **Manual upload** — accept the bytes and any provided origin URI from the operator.

Inline media a transport *references* (images in an HTML page, etc.) are not separate records: the body drafter emits an **embed block** per asset (deduped by `transport` byte-hash) plus an `image`/`audio`/`video` positioning segment in the content zone (§3.1, spec §4.3.1.4) — never an intra-corpus wikilink (those are reserved for cross-*artifact* references, spec §4.3.2.2). A transport the schema declares `decomposable` (a raw archive) is the exception: the ingestor explodes it into one captured artifact per member. Hyperlinks to *other* resources are reconciled to intra-corpus references during cross-reference resolution (§3.2).

### 2.2 MIME detection

MIME detection selects the **mime schema** that drives the rest of the pipeline (container disposition, `transport_algos`, address scheme, drafter). Strategy:

1. **Magic-byte sniffing** — the primary path (`mime.detect`). Inspect the leading bytes; refine ambiguous container magic by form-type and extension (a RIFF prefix → webp/wav/avi by its offset-8 form-type; an ISOBMFF `.m4b` → `audio/mp4` not `video/mp4`). A `PK\x03\x04` zip is refined by its members (`_refine_zip`): universal formats (OOXML / EPUB / JAR) match fixed internal paths baked into the tooling; a corpus's *own* zip-shaped types (a diagnostics export, a backup bundle) match their schema-declared shape signatures (`applies_to.zip_members` / `zip_member_patterns`) when a `corpus_root` is in scope — so vendor/site-specific recognition lives in the overlay, not the package, and an unrecognized zip stays `application/zip`.
2. **Extension hint** — disambiguates where magic is generic, and names the type for extensionless or schema-id-from-filename cases.
3. **`unknown` sentinel** — when both fail. Record the gap; the artifact is still valid, it just won't get format-specific drafting.

The detected MIME becomes the **artifact block's opener argument** — `<!--artifact <mime-type>-->` — which is **authoritative**. There is no frontmatter `content_type` / `media_type` field (spec §4.3.1.1).

### 2.3 Hashing

Three hash families live at three different layers (spec §7.6 encoding; §2 / §4.2.1 fields):

- **blake3 of the bytes** — always, at ingest. This is the artifact's `id` (bare hex, no prefix) — the identity and filename stem.
- **`transport_algos`** — additional *byte-level* algorithms the mime schema declares (e.g. `sha256` for interoperability), computed at ingest into the `transport:` field as `<algo>:<hex>`. The primary blake3 is on `id` and is not duplicated here.
- **`canonical`** — a *content*-canonical hash set at **draft** time by the mime schema's `canonical_strategy` (`blake3-canonical-{pdf,html,image,epub}`), so two records holding the same content reached by different URLs can collapse (spec §7.1). Draft-time, not ingest-time.
- **`perceptual`** — atom fingerprints (image pHash, text simhash, …) are **opt-in and schema-gated**, computed at **draft** only when the `fingerprint` knob resolves on (§3.1); default off. Per-segment on multi-atom records, record-scope on single-atom ones (spec §7.7).

There is no frontmatter `hashes` field and no mandatory per-MIME perceptual hash. A MIME with no canonical strategy and no fingerprint knob is blake3-`id`-only, and that record is normal.

### 2.4 In-memory record build

Ingest emits the **stub record** (spec §4.1). The frontmatter carries only the bytes-identity header — `id` (blake3), `transport:` (any `transport_algos`), `status: stub`, `touch: [<pkg>.ingest@<v>]`, and the two editorial fields `title: ''` / `description: ''` (empty until the normalizer authors them, spec §4.2.1). Everything else lives in **body blocks**:

- The **artifact block** `<!--artifact <mime-type>-->` (§2.2), its body holding the format-intrinsic extended fields the mime schema declares, named **bare** (`title`/`author`/`page_count`, not `pdf_title`; spec §4.3.1.1 / principle 10). Sources: PDF info dict, EXIF, ID3, HTML `<meta>`, OPF Dublin Core, ffprobe streams.
- The first **origin block** from capture context — `uri:` + `snapshot:` (§2.6).

No `content_type`, no `hashes`, no `classifications`, no `tags`, no `uris`/`capture_dates` frontmatter — none of those exist in the v1.0 model. The content zone is empty; draft (§3) fills it. Classifications aren't stamped here either — `classify_when` membership is applied at **draft** (§3.1).

### 2.5 Dedup

Look up the artifact by `id` (blake3 hash) against the existing corpus:

- **Match.** The bytes are already in the corpus. Fold the new capture into the existing record's **origin blocks** (§2.6): append the inbound URL to a matching origin's `uri:` list when it aliases one (via known shortlink/redirect + `url_equivalent` rules), or emit a new origin block when it is a genuinely separate source. Do not create a new record.
- **No match.** This is a new artifact. Write the record under `records/` and the binary under the `artifacts/` cache (§2.7).

Dedup is the natural side effect of content addressing — bytes that match an existing hash hit the same record. Two pre-download stages catch a duplicate *before* the bytes are even fetched: the cheap string-identity `find_by_uri` short-circuit, and the redirect-aware short-link resolution (`corpus check`, §2.12).

### 2.6 Capture provenance

Capture provenance lives in **origin blocks** in the record body's metadata zone — not in frontmatter (spec §4.3.1.2). Each origin block carries:

- `uri:` — a string or list. One origin block per distinct *source*; its `uri:` list collects the spellings that resolve to it (request URL, final-after-redirect URL, shortlink, mirror, `file://` path), deduped by identity key (§2.11).
- `snapshot:` — the ISO-8601 timestamp the origin was observed.

Re-capture is append-only (spec §5.2): a re-encounter folds an aliasing URL into an existing origin's `uri:` list or adds a new origin block, per §2.5. The pipeline does **not** record per-event metadata (which URI was used at which moment, the redirect chain, the HTTP method); recovering a particular (uri, time) capture package is a job for an out-of-band capture log, not the record. A yt-dlp capture additionally lifts its `.info.json` into flat `ytdlp_<key>` fields on the origin block (§2.9).

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
├── schema/                             ← tracked: mime / origin / atom / composite / context
│   ├── mime/
│   ├── origin/                         ← web/<host>.yaml, otherwise/<id>.yaml
│   ├── atom/
│   ├── composite/                      ← <namespace>/<id>.yaml classifications
│   └── context/                        ← issue / reference / … annotation overlays
├── capture/                            ← UNTRACKED: in-progress staging
├── cache/                              ← UNTRACKED: resolver-output cache
└── .gitignore                          ← lists artifacts/, capture/, cache/
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

**Sidecar → origin block (draft time), then deleted.** The yt-dlp `.info.json` is *non-primary-source* metadata, so `draft/_sidecar.py` lifts every declared key into the **origin block** as a flat `ytdlp_<key>` field (`ytdlp_title`, `ytdlp_description`, `ytdlp_uploader`, engagement counts, …) via `records.merge_origin_fields` — never the artifact block, the body, or the frontmatter `description`. `comments[]` (when yt-dlp returns it) becomes a `ytdlp_comments` list field; `webpage_url`/`original_url` fold into the origin `uri:` aliases. The lifted key set is **schema-declared** — `sidecar.ytdlp_keys` on the video/audio mime schema (the drafter is mechanical, not hardcoded). One info.json datum is *structural* rather than flat: **`chapters[]`** (the uploader's outline). A video that ships chapter markers is sectioned by them — each chapter title becomes a section `entry` (the §4.3.2.2 TOC label) and the chapter bounds become the section time-ranges, in preference to the default speaker-run sectioning. Chapters are consumed into the section structure, never copied to a `ytdlp_*` origin field; a section's `entry`/address is metadata structure, **not** body content, so this respects the same primary-artifact boundary. The only body content a media drafter writes is the **transcript** (from the primary artifact's own audio). **Title** is normalizer-owned: the frontmatter `title` (like `description`) stays empty through draft; the normalizer authors it from the block-level candidates (the artifact block's **bare `title`** — the opener's MIME names the format, so the candidate isn't prefixed — or an origin `ytdlp_title`, whose `ytdlp_` prefix survives because the origin opener names the source record, not the tool). A media drafter's title routes to the origin's `ytdlp_title` (the A/V artifact block carries no `title`; ingest stamps none) — for display `records.title_for` reads the frontmatter `title`, falling back to the artifact `title` then `ytdlp_title`. After a successful draft, `_cli/draft._cleanup_enrichment` **deletes** the sidecar; enrichment is one-shot (re-capture to restore; the extracted fields already persist on the record).

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

### 2.12 Redirect-aware short-link dedup (`corpus check` + the capture second stage)

`urls.identity_key` canonicalizes a URL *string* but never touches the network, so an **opaque short link** (`https://vt.tiktok.com/XXXX/`) has a different identity key from the canonical it 301s to (`https://www.tiktok.com/@user/video/<id>`). The byte-level re-encounter on ingest eventually catches the duplicate, but only *after* the (expensive, esp. video) download. The redirect-resolution layer closes that gap by following the redirect chain to the final URL **without downloading the artifact**.

- **The primitive** is `redirects.resolve_final_url(url)` (pure stdlib `urllib`): a per-hop **HEAD** (falling back to a body-less GET on 405/501) follows `Location` headers up to `MAX_HOPS`, never reading a response body — so even when the final URL serves a multi-megabyte video the probe stays cheap. Redirect loops, hop-cap, non-web `Location`s, and any network/parse failure all return the input unchanged (parse-tolerant — a probe never *breaks* the caller, it only *improves* dedup when it succeeds). `redirects.is_probably_short_link(url)` is a conservative gate (known shortener hosts, `vt.`/`vm.` subdomains, or a single short opaque path segment) so a normal canonical URL never pays the network round-trip.
- **The recipe-aware wrapper** `recipes.resolve_identity_for_url(corpus_root, url)` returns `(final_url, identity_key)`: it follows redirects only when the URL looks like a short link, then computes the identity key from the **final** URL (so the destination host's `url_equivalent` strips the volatile query the canonical resolves with — e.g. TikTok's `?_r`/`?_t`). The key is taken from the final URL's host overlay, so a short link whose apex differs from its destination (`youtu.be` → `youtube.com`) picks up the destination's equivalence rules.
- **Capture short-circuit (second stage).** `capture_and_ingest` keeps the cheap string-identity `find_by_uri` first; on a miss, `_redirect_dedup` runs the redirect-aware resolution and re-checks (`find_by_uri(..., _prekeyed=True)`) — catching a fresh short link to an already-captured canonical **before** the download, and folding the short link into the matched record's origin URI list as an alias. `--force` skips both stages (it never even probes redirects), and the short-link heuristic keeps the probe off the hot path for normal URLs.
- **`corpus check <url>`** (`_cli/check.py`) is the **read-only** surface: same resolution (urlcanon + overlay recipe + redirect-follow), then `find_by_uri`, reporting the matching record hash + path or "not captured". It never captures / ingests / downloads / writes (the redirect follow is a body-less HEAD/GET). Script contract — exit `0` already captured, `1` not captured, `2` usage error, `3` resolution error; `--json` emits `{url, resolved_url, identity_key, redirected, captured, record, path}`; `--no-follow-redirects` does a string-identity-only check (offline / fast). This replaces the throwaway `curl -sIL <short> | grep /video/ | grep -rlF records/` curator workaround.

---

## 3. Normalization

Normalization brings an artifact from `status: stub` to `status: normalized`. The spec defines what the normalized record carries (§4 and §8 of the spec); this guide describes how the pipeline gets there. ("Normalization" here spans the deterministic **draft** pass and the LLM-guided **normalize** pass — §3.1 is draft, §3.4 is normalize.)

### 3.1 Conversion (deterministic)

Conversion produces the artifact's body as well-formed markdown. It is MIME-driven and shells out to deterministic tooling. Per-MIME mappings:

- **`text/html`, `application/xhtml+xml`** → the **mechanical** HTML drafter (`draft/html.py`): it removes only non-rendered infrastructure (scripts/styles/comments), assigns `el=N` addressing to every element of the raw artifact, emits dedup'd image embeds, and emits one cleaned-`<body>` text segment. It does **not** strip page chrome — a universal tool can't reliably tell chrome from content (e.g. ASP.NET WebForms wraps the whole page in one `<form>`), and a wrong guess drops content silently. Chrome removal (nav/ads/cookie notices) is therefore a **capture-time, per-host** decision: list the selectors to delete in the origin overlay's `capture.interactions[].remove` (§2.8). Structural recovery (headings/tables/lists/equations) is the normalizer's job.
- **`application/pdf`** → `draft/pdf.py` picks one of two shapes by **inspecting the bytes**. A **born-digital** PDF gets text extraction, one `text` segment per page (`page=<N>`), wrapped into `<!--section-->` blocks by the outline (`get_toc(max_depth=1)`, `pages=<start>-<end>`). A **scanned image-of-document** — detected when *every* page is dominated by a full-page raster (`_is_scanned_pdf`: ≥ `_SCANNED_COVERAGE` (0.9) of page area, measured by walking the content-stream CTM over image `Do` ops; vendor-agnostic — no `/Producer` sniffing) — is drafted **as if it had no text layer**: sectionless, one **body-empty `image` segment per page** (`page=<N>`). The page's own text layer is usually a machine-OCR layer baked in before capture (interpretation, not faithful source, often low quality), so it is deliberately suppressed; the normalizer re-reads each page region into `text/ocr` at `page=<N>&bbox=...` via the image-of-document playbook, so the corpus owns the OCR provenance (engine/confidence/region). A born-digital page with no extractable text (DRM'd, vector-only) still yields zero text segments and a normalizer `partial-content` issue. Page renders materialize on demand via the `page=<N>` functional URI (which is also why a `page=` image segment is a self-slice needing no embed — `lint._self_slice`).
- **`application/epub+zip`** → the EPUB drafter (`draft/epub.py` + the pure `corpus.epub` OPF reader). `self_contained` (one record per book, not decomposed — an EPUB is one work). Emits one bare `text` segment per spine (reading-order) content document, addressed `spine=<N>`, with a mechanically-cleaned structural-HTML body (same philosophy as the HTML drafter — non-rendered infrastructure stripped, structure kept), and **groups them into `<!--section-->` blocks by the book's navigation document** (EPUB 3 nav `<item properties="nav">` → EPUB 2 NCX `<navMap>`): top-level TOC entries become sections (`address: spines=<start>-<end>`, `entry:` = the part/chapter title), spine docs before the first TOC target become a synthetic `Front matter` section — the exact analogue of how the PDF drafter wraps pages by `get_toc(max_depth=1)` (`pages=`/`page=` ↔ `spines=`/`spine=`). A book with no usable nav/NCX drafts sectionless (flat top-level segments carrying their document title as `entry:`), like an outline-less PDF. Each `<img>` references a separately-stored zip member, so it becomes an **`<!--embed-->`** (addressed `spine=<N>&el=<K>`, `transport` = blake3 of the member bytes, deduped by hash across the book; the body keeps a src-stripped `<img data-el="K">` placeholder) — the HTML drafter's embed model, not the PDF's bare-image-segment model. That embed address **materializes** through `transforms/epub.py`: `spine=<N>` selects the OPF content document and binds a resolver over the book's zip image members, then `el=<K>` resolves the addressed `<img>` to its member bytes (decoded to a PIL image) — `corpus://<id>?spine=<N>&el=<K>` → the image. The body strips `<img src>` because it's redundant: the src lives on in the immutable artifact, and el-indexing is shared with the drafter (`corpus.epub.addressable_image_bytes`, same `_strip_non_addressable` + `_ADDRESSABLE_TAGS` axis), so a recorded address round-trips to byte-identical content (the resolved bytes' blake3 == the embed's recorded `transport`). Mirrors the HTML `el=` transform, but resolves a zip member relative to the spine document rather than an inline `data:` URI. Publication metadata (Dublin Core) lands as bare artifact fields — the opener's MIME names the format (`title`/`creator`/`language`/…; `title` is the title candidate; `spine_item_count`/`toc_entry_count` record the shape). Canonical: `blake3-canonical-epub` (concatenated spine text — packaging-invariant; images don't perturb it).
- **raw `application/zip`** → `decomposable` by default (the bundled `application/zip` schema): the ingestor explodes it into one captured artifact per member; the container produces no record. A corpus that wants a *particular* zip-shaped bundle kept WHOLE declares its own `self_contained` mime schema for it (recognized by shape via `applies_to.zip_member_patterns` — see MIME detection above) and points it at the **`zip-manifest`** drafter below.
- **`draft.strategy: zip-manifest`** → the general `self_contained`-zip drafter (`draft/zip_manifest.py`), selected by *strategy* not schema id (`corpus.draft.STRATEGY_REGISTRY`), so one drafter serves any number of bundle types (a diagnostics export, a config/log backup) that differ only by the schema's `draft.manifest` config. It records the archive as an **embed manifest**. The modeling point: a zip member is a *transport* (a file with its own bytes + MIME), NOT a content atom (a subsection of the artifact, like a PDF crop) — and an `<!--embed-->` is precisely "an embedded transport" (which is why it carries a `media_type`). So **every member becomes an embed** (`transport` = blake3 of the member bytes, `media_type` content-sniffed, addressed `path=<relpath>`, root-stripped per `manifest.root_strip`) that the normalizer describes — and the **content zone is empty**: a pure container has no content atoms of its own, and a member's bytes are verbatim + resolvable, so nothing is transcribed (the PDF/HTML/EPUB drafters materialize a body only because they *transform* their source — rasterize, OCR, clean markup; a zip member needs no such work). The folder hierarchy lives in the `path=` addresses (a tree is a derived rendering, not stored section/segment blocks). `media_type` is content-sniffed (`_is_text`: UTF-8, no NULs), not extension — so a `.cfg`/`.conf`/extensionless log is `text/plain`, not extension-misclassified `application/octet-stream`; a precise extension guess (`application/json`, `image/png`) is kept; an opaque binary is `application/octet-stream`. Bytes materialize through `transforms/zip.py`: `corpus://<id>?path=<relpath>` → the member bytes (`working_kind: zip` + the `path=`→`bytes` transform; `corpus.ziparchive.resolve_member` re-derives the wrapper root so a root-stripped address round-trips). The artifact block carries **generic zip facts only** — `member_count`, `uncompressed_bytes`, `compressed_bytes`, `compression` (the method set, e.g. `deflate`), `encrypted` (any member password-flagged), `comment` (the archive comment) — facts about the zip bytes, filled for every record (the "+zip inherently surfaces zip fields", done in the shared zip handler since only it can read them). When there's a single wrapper dir its name is a fallback `title` candidate. The drafter knows **nothing about any vendor**: recognizing a bundle as an Unraid diagnostics package and surfacing its identity (version, hostname, board, array health, the composed title) is **codex-layer domain knowledge**, carried by a classification overlay (`unraid/diagnostic-package`, a composite whose `classify_when: {mime: {equals: …}}` auto-applies on the kept-whole MIME at draft) and filled by the normalizer into the classify block — NOT by this drafter, and NOT on the artifact block. The MIME schema's job is purely mechanical: recognize the shape (`zip_member_patterns`), keep it whole (`artifact_kind: self_contained`), route to this strategy. An empty archive yields a blocking `partial-content` issue. Because such a record has no content-zone segments, the `embed-unreferenced` lint is relaxed for it (the embeds ARE the content, not flow-positioned assets). The clean split: the corpus layer is domain-agnostic (a kept-whole zip → an embed manifest + generic facts); the codex layer adds the domain identity via classification + normalization.
- **`audio/*`** → speech-to-text transcription. Reference: Whisper. Output includes timestamps. Speaker turn markers where determinable. `audio/mp4` covers `.m4a` / `.m4b` audiobooks (an `.m4b` magic-sniffs as `video/mp4` on its generic ISOBMFF brand; `mime.detect` refines it to `audio/mp4` by extension so it routes to transcription, not the video keyframe path — embedded chapter markers and cover-art `mjpeg` are not consumed in v1).
- **`video/*`** → audio transcription + per-keyframe descriptions when the schema asks for them.
- **`image/*`** → a single body-empty `image` segment addressed `bbox=0,0,1,1` (`draft/image.py`); the image is its own self-artifact (no embed — the bytes are the record's, materialized via the `bbox=` functional URI, spec §4.3.1.4). Any visual description is normalizer-written on the segment `description:`; an optional `perceptual:` when the fingerprint knob resolves on. No VLM/OCR in the deterministic drafter.
- **`text/markdown`, `text/plain`** → passthrough with minimal cleanup (one `text` segment, body = the source text).
- **`unknown`** → best-effort fallback; emit a `metadata` body summarizing what little can be determined.

**One construction path (the constituent model).** Every drafter builds the record's content zone through the **`recordbuild.Build` ops** — `add_blocks` → `open_section`/`add_segment` (which enforce body⟺lossless per segment) — and `recordbuild.finish` emits + grammar-validates it. These are the *same* ops `compile` replays from a decomposed `manifest.corpus`, so draft / redraft / decompose / compile / normalize all construct records identically and a drafted record decomposes then recompiles byte-for-byte. This is the substrate the LLM normalizer works on: it edits the decomposed **constituent files** (per-segment body / description sidecars + the ops manifest) and recompiles deterministically — never rewriting a monolithic markdown blob — which makes whole classes of structural corruption *unrepresentable*. (`begin_from_post` seeds the Build for the draft/redraft path; `begin` seeds it from a `meta.yaml` for compile.)

**Perceptual fingerprinting is opt-in (draft time).** A segment gets a `perceptual:` only when `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override)` resolves on — precedence CLI (`corpus draft --fingerprint` / `--no-fingerprint`) › composite classification › mime-schema `fingerprint` knob › **off** (the default; a record with no `perceptual:` is normal). The resolved knob (`True` = the atom's default algorithm, an algorithm name, or a list) becomes concrete per-atom algorithms via `fingerprint.algos_for_atom(atom, knob)`, computed by `fingerprint.text_fingerprints` / `image_fingerprints` (a registry keyed by algorithm, mirroring `content_hash._STRATEGIES`). Resolution at draft only sees the mime default, **mechanical** composites, and already-present classify blocks; an **interpretive** composite (e.g. `composite/document`, assigned by the not-yet-built normalizer) applies on a later `corpus redraft`. Algorithm selection is schema-only; the CLI flag is on/off.

**Bulk recompile (`corpus redraft`).** A drafted record is a deterministic function of (retained artifact + schemas + tooling), and `id = blake3(artifact)` is unchanged by re-derivation — so regenerating it is an **in-place `.md` rewrite**, and `git diff records/` surfaces exactly which records a schema / overlay / tooling change affected. `corpus redraft [target] [--mime/--host/--status] [--dry-run] [--fingerprint]` applies the per-record draft core (`_cli.draft.derive_record`) across the corpus via a **clean re-stub** — `restub.restub_post` with the touch chain collapsed to the original ingest entry (no re-stub touch) — so an *unchanged* record re-derives byte-for-byte and is not rewritten (**idempotent**; `--dry-run` reports the set, writing nothing). It refuses `normalized` records unless `--force`, since re-deriving discards normalization. This is **distinct from `corpus compile`**, which reassembles a record from a decomposed *manifest* (the normalization edit substrate) rather than from the source *artifact* — different inputs, different jobs. (`records.dumps` serializes a record to the canonical text without writing, so redraft can compare against disk.)

Pipeline-state provenance is the **`touch[]` chain** (spec §4.2.2): each pass appends a `<pkg>.<module>@<version>` (or `<model-id>`) identifier, so the latest touch's tooling version encodes the spec era of the record's current shape and re-run targeting reads it. There is no separate `conversion_method` / `conversion_tool` frontmatter.

**Deterministic auto-classification (`classify_when`).** A composite overlay that declares a `classify_when` predicate (spec §7.4) gets stamped onto every matching record **at draft time** as a `<!--classify <ns>/<id>-->` block with `provenance: auto`. The engine is `classify_rules.py`: `build_facts(corpus_root, post)` extracts the flat fact base (`mime`; `origin.host`/`path`/`fragment`/`query.<k>`/`id` — any-origin, list-valued via `urls.host_of` + `urlsplit`/`parse_qsl`; `media.<field>` by **inverting the `ytdlp_` prefix off the origin block's fields**, so the alias set tracks `draft/_sidecar.py::_YTDLP_KEYS` automatically — `tags` is inert until lifted); `evaluate(predicate, facts)` runs the `all_of`/`any_of`/`none_of` + `equals`/`in`/`glob`/`matches`/`exists` grammar (pure, total, **missing-fact-⇒-false** via empty-value-list semantics); `matching_classes` scans `schemas.iter_all_classifications` (namespace base **and** every subclass, deep-merged — the kind-agnostic walk the worked subclass examples need, since `interpretive_classifications_for` walks bases only). `apply_auto_classifications(corpus_root, post)` is the idempotent strip-all-`provenance:auto` + regen-from-rules fixpoint — auto blocks placed **before** any surviving non-auto block (draft-time precedes interpretive per §4.3.1.3), asserted blocks untouched. The hook is in `_cli.draft.derive_record` after `_apply_drafter_result` (origin `ytdlp_*` present) and before the status flip, so **both** `corpus draft` and `corpus redraft` (a stub routes through `derive_record`) self-heal auto blocks. It is the **mechanical, membership-at-draft** path — complementary to, and never merged with, `classify_match.candidates()` (the interpretive body-cue matcher the normalizer consumes). Pure opt-in: no `classify_when` anywhere ⇒ no behavior change.

**`corpus classify` / `corpus reclassify`.** Operate on **stored** records (not a re-stub), so they preserve the body and asserted blocks — re-evaluating only auto membership. `corpus classify <hash> [--dry-run] [--json]` does one record (prints the satisfying fact as the "why"); `corpus reclassify [target] [--mime/--host/--classification/--status] [--dry-run]` is the bulk re-propagation after authoring/editing an overlay (mirrors `redraft`'s iteration + filters + dry-run). Both are body-safe and so default to **all** statuses incl. `normalized` — unlike `redraft`, which refuses `normalized`. Lint's `classification-stale` (warning) flags any `provenance: auto` block whose overlay was deleted or no longer matches; the fix is `corpus reclassify`.

### 3.2 Cross-reference resolution (deterministic)

After the body exists, scan segment bodies for **hyperlinks** (`<a href>` → other resources) — *not* same-transport inline media, which is already an embed + segment (§3.1). For each hyperlink:

1. Map the URL → `id` by querying the corpus's URI index (`records.build_uri_index` — every record's origin `uri:` list keyed by identity, §2.11).
2. If matched, rewrite as a raw intra-corpus wikilink `[[<id>|original link text]]`. No URI scheme prefix — these are layer-local cross-*artifact* references (spec §4.3.2.2 / §5.1).
3. If unmatched, leave the plain markdown URL. The target is outside the corpus and may resolve on a later cross-reference re-resolution pass (§5.3) once it is captured.

This is purely mechanical. The normalizer does not invent links the original content didn't contain.

**Reconciliation tooling.** The on-demand counterpart to this resolution pass ships as `corpus links` (per-record) and `corpus crawl` (frontier BFS): both extract a record's `<a href>`, resolve relatives against its origin URI, normalize (`corpus.urls.normalize`), and look each up in `records.build_uri_index` — the map of every record's origin `uri:` list (including the dedup'd alias forms a page was reached by) to its id. A hit means the reference is already captured; a miss is the **crawl frontier** (what still needs capturing). `corpus links --show-captured` annotates which is which. Link extraction filters hrefs through `corpus.urls.is_crawlable_href`, which keeps **client-side routing fragments** (`#/route`, `#!/route`) — on a hash-routed SPA the fragment *is* the resource identity, so these are real outbound links, not in-page anchors — while dropping bare anchors (`#section`) and the `javascript:`/`mailto:`/`tel:` schemes. (Link-bearing navigation that a host renders as visual chrome — breadcrumbs, related-item rails — is therefore preserved at capture for crawl purposes via the origin overlay's `remove:` selectors, not stripped.)

### 3.3 Schema application

Draft applies schemas in the spec's declared order (§8.1):

1. **The mime schema** runs first — the sole body-drafter. It segments the content zone, emits embed blocks, fills the artifact block's bare extended fields, and (when it declares a `canonical_strategy`) sets `canonical`.
2. **Atom overlays** classify each segment on its opener (`<!--segment <atom>/<id>-->`); a `text/<id>` overlay with `enables_lossless: true` shapes a lossless body (table, transcript, OCR text).
3. **Mechanical composite classifications** run in declared order — each emits/fills its own `<!--classify <namespace>/<id>-->` block (metadata only; never the body). Membership is decided by the `classify_when` predicate where one is declared, and the block is stamped `provenance: auto` (§3.1).

A classification is **not** a frontmatter array and carries **no** justification field: the `classifications` list is a *derived view* computed by walking the metadata-zone blocks (spec §9.1 / principle 11). Records carry no `tags` field. Extended fields are **bare** — the block opener scopes them (spec §4.3.1.1 / §7.4).

### 3.4 Contextualization (LLM-driven)

The normalizer (LLM-guided) refines the record:

- Apply matching **interpretive** composite classifications — each as its own `<!--classify <namespace>/<id>-->` block (no `provenance`, so the auto engine never touches it), with the overlay's `normalization.guidance` consumed here. No frontmatter array, no justification field (membership IS the block; spec §9.1).
- Improve formatting fidelity (broken tables, malformed lists); resolve encoding ambiguity where determinable.
- Write asset descriptions on embeds and on self-slice / non-lossless segments via `description:` (lossy interpretation — never in a faithful segment body); fill embed `alt` only when the source provides it.
- Surface problems as **`<!--context issue/<id>-->`** blocks (missing media, broken links, partial content, encoding corruption, format loss) — the annotations zone, not a frontmatter array (§3.6).
- Author the frontmatter **`title`** and **`description`** (the two editorial fields, empty until now).
- Re-segment the content zone where judged appropriate (structural only), and set `status: normalized`.

Contextualization MUST preserve faithfulness — the body stays a lossless rendering of the original (spec principle 3). No information that wasn't in the source; descriptive content lives on `description:` / `alt`, not in a segment body.

### 3.5 Self-verification

Before declaring the record normalized, the normalizer confirms:

- The **artifact-block opener** MIME matches the actual MIME of the stored binary (there is no `content_type` field — the opener is authoritative, §2.2).
- The `id` (blake3 hash) matches the binary's hash.
- The on-disk record path matches the shard convention.
- `corpus lint` is clean at `normalized` severity (the executable encoding of the spec's required-field and grammar rules).

Failures here are bugs in the pipeline; they should fail loudly.

### 3.6 The context block (annotations zone)

The annotations zone is a single block family — **`context`** (spec §4.3.3) — drawing overlays from a reserved top-level `context/` umbrella, one namespace per kind of observation. The bundled namespaces are `issue` (problems, with the severity/resolution/detector shape), `reference` (cited sources, the §4.4.5 ladder), and `concept` (Wikipedia/Wikidata concepts, §4.3.3.4); a corpus may add its own. The block stores as `{namespace, id, subtype, fields}` — the same shape as a classify block — in `post.metadata["_contexts"]`; emitted `<!--context <ns>/<id>-->`. Context never feeds the canonical hash or the faithful body segment.

**Context is scarce by design (spec §4.3.3).** The mechanical namespaces (`issue`, and the deferred `aside`/`relation`) auto-populate only on real signal and only where schema-gated — `aside` exists *solely* where an overlay declares the extraction. The interpretive `reference` requires a referent in the content. The normalizer is contractually forbidden from using context as a scratchpad (commentary / summaries / running notes); absent real signal the annotations zone is empty. There is deliberately **no** bundled free-text `note` namespace — that would invite exactly that flooding.

- **Issue migration.** The bundled issue overlays moved `schemas_default/composite/issue/** → context/issue/**`; `schemas.load_context_schema(corpus_root, "<ns>/<id>")` layers `context/<ns>/<ns>.yaml` → `context/<ns>/<id>.yaml` (the generalized `load_issue_schema`, now a thin shim). `records.iter_issue_blocks` / `append_issue_block` are back-compat shims over `_contexts` filtered to `namespace == "issue"`, so the drafters/detectors, `health.unresolved_issues`, the §9.2 issues view, and lint's issue rules are unchanged. The reader is **parse-tolerant**: a legacy `<!--issue <id>-->` still loads (as the `issue` namespace) and upgrades to `<!--context issue/<id>-->` on the next write (`redraft` regenerates drafter issues for free).
- **Reference.** Normally normalizer-/human-asserted (it's the durable home for a cross-reference §3.2 couldn't resolve mechanically): a casual mention gets a `reference` context anchored by `address:` + a verbatim `quote:` and researched up `attribution_text → source_url → source_uri`. Lint `reference-unresolved` flags a `source_uri` that doesn't resolve to a captured record; `context-namespace-unknown` flags a block whose namespace has no `context/<ns>` overlay.
- **Concept.** A concept the body invokes, resolved against the **local Wikipedia KB** (an external authority, *not* a corpus record — the contrast with `reference`'s tier-3 `corpus://`). The block is lean — the identity ladder `label → url → concept` (`concept` = the `wikidata:Q…` / `enwiki:<Title>` / `local:<slug>` join key) plus the optional `address:`/`quote:` anchor (present = a span-level mention; absent = record-level aboutness). The human-facing **gloss is fetched live** from the KB at serialize time, never stored on the record. Projected by `derived_views.concepts` (§9.7) and `records.iter_concept_blocks`. Authored by `corpus concept link` (manual) today; an automatic content-scanning annotation pass is deferred.
- **Decompose/compile.** The manifest keeps the dedicated `issue <id> sev= res= detector=` line for the issue namespace and adds a generic `context <ns>/<id> k=v…` line for the others (`recordbuild.add_context`).

### 3.7 Normalizer-support commands

The LLM normalizer never reads `schema/*.yaml` directly (the reference contract forbids it). It works through read-only commands (`_cli/{diagnose,guidance,overlay,preview}.py`, surfacing the spec §9 derived views and the §6 resolver):

- **`corpus diagnose <hash> [--json]`** — the normalizer's first call: a one-page brief combining the derived views (classifications / issues / uris) with a quick-lint and the record's `<!--context-->` blocks.
- **`corpus guidance <hash>`** — the merged `normalization.guidance` from every applied mime / origin / composite overlay for the record.
- **`corpus overlay <namespace>/<id>`** — the field-spec table (types, `semantic_type`, required) for a candidate classification, so the normalizer fills a classify block without reading YAML.
- **`corpus preview <target> [--page N] [--mark x,y,w,h]… [--full] [-o out.png]`** — the cropping loop's *eyes*. Renders the artifact (an image, or a PDF page via `--page`) with each proposed bbox **outlined on the full image** (the `mark=` transform, §3.7.1) so a vision-model normalizer can see *where* a region sits in context, judge the fit, and adjust the coordinates before committing them as a segment `address`. Read-only — it never writes the record; the agent commits regions separately (`POST /records/{id}/regions`, or by editing the body). Fits the render to the `llm` budget by default (see below); prints the cache path, or copies to `-o`.

Membership it can assert manually via `corpus classify <hash> <namespace>/<id> --field k=v` (validated, no `provenance`, so the auto engine leaves it). These commands were brought to parity with the LuklaCloud corpus normalizer toolchain.

#### 3.7.1 The cropping agent's image toolkit — `mark`/`fit`/`rotate`/`auto_orient`/`autocontrast`, and `corpus preview`

This whole group was shaped by reviewing real normalizer runs on image-of-document records (scanned/photographed forms). The dominant friction those runs hit was **not** crop mechanics but `bbox=` **semantics**: agents read `bbox=x,y,w,h` as corner coordinates (`x1,y1,x2,y2`), so the "width/height" values were far corners, overflowed `x+w>1`, and the resolve failed — repeatedly, in one case never recovered (the agent abandoned `corpus resolve` for hand-rolled PIL on raw cache files). The cheapest fixes target that directly: the `crop=`/`bbox=` bounds error now names the format and the overflowing axis (`x+w=1.1>1 … bbox is x,y,WIDTH,HEIGHT, NOT corners`), `corpus resolve`/`corpus preview --help` print the full transform grammar (`_common.TRANSFORM_GRAMMAR`), and the previously-empty `mime/image/image.yaml` now carries `normalization.guidance` teaching the bbox convention, crop-first legibility, orientation, and the verify loop.

Two image transforms (`transforms/image.py`, spec §6.2) close the loop between an agent proposing a crop and seeing whether it's right:

- **`mark=x,y,w,h[;x,y,w,h…]`** (image → image) — draws the region(s) **onto the full image** rather than cropping to them. It's the inspection dual of `crop=`/`bbox=`: `crop` returns the region's pixels, `mark` returns the whole frame with the box outlined (a cycling high-visibility stroke, auto-labeled `1..N`, width ∝ image size). Composes after `page=`, so `corpus://<id>?page=4&mark=0.1,0.1,0.6,0.3` outlines a box on a rendered PDF page. This is the server-side, agent-facing parallel of the web cropper (`rw-cropper.ts`, which draws `<div>` overlays for a human curator) — an LLM can't run a browser, so it Reads a PNG with the box burned in.
- **`fit=<W>x<H>` | `fit=<preset>`** (image → image) — downscale to fit within a box, **aspect-preserving and reduce-only** (an image already within bounds passes through untouched). Distinct from `resize=WxH`, which forces exact dimensions (distorts, may enlarge). The **`llm` preset** bounds the image to a vision model's input budget so a resolve destined for model context isn't silently re-scaled (or rejected) downstream: long edge ≤ `LLM_MAX_EDGE` (1568px) **and** total pixels ≤ `LLM_MAX_PIXELS` (1,150,000), the smaller scale winning. These constants live in `transforms/image.py`, **not** the spec — spec §6.2 describes `fit=` generically and notes presets are implementation-defined, because model limits drift. PDF `dpi=` is the other half of the dial: rasterize at the DPI you want, then `fit=llm` caps the result regardless.

The split that keeps `fit` honest: the transforms stay **pure** (no implicit fitting), and only the agent-facing surface defaults the budget on. `corpus preview` fits to `llm` unless `--full` — because a preview *is* going into a model's context — while a raw `corpus resolve` / the API `resolve?uri=` apply `fit=` only when the URI says so (a codex embedding a crop in a human-facing deliverable wants native resolution). A typical loop iteration: `corpus preview <id> --page 4 --mark 0.1,0.1,0.6,0.3 -o /tmp/look.png`, Read it, adjust the numbers, repeat; once the box is right, write the segment at `page=4&bbox=0.1,0.1,0.6,0.3`.

Four more image transforms round out the toolkit, all `image → image`, all composable in the chain:

- **`rotate=90|180|270`** — clockwise quarter-turn (lossless transpose; 90/270 swap W/H), and **`auto_orient`** (flag) — applies the EXIF orientation tag (no-op when absent). Together they right a sideways/upside-down phone-photo or scan *before* the agent reads it; the run we reviewed had an agent hand-rotate in PIL and pick the wrong direction twice. `corpus preview --rotate`/`--auto-orient` expose them.
- **`autocontrast`** (flag, 1% cutoff) and **`contrast=<factor>`** — pull a faint scan toward readable (the run reached for `ImageEnhance` against raw cache files for exactly this). `corpus preview --autocontrast` exposes the flag.

A caveat the image guidance makes explicit: unlike a PDF (vector source, re-renderable at higher `dpi=`), an **image's resolution is fixed** — cropping can't add detail, so for fine print on a low-res capture the levers are crop-tight + `resize=` (enlarge — interpolated, not new detail) + `autocontrast`; there is no DPI escape hatch.

**`corpus preview --from-segments <id>`** is the verify half of the loop: instead of ad-hoc `--mark` coords it reads the record's *already-committed* bbox segment addresses (via `segments.iter_blocks`, grouped by `page=`) and draws them — so the normalizer can confirm each written address frames the span it meant. Neither reviewed run ever verified a committed bbox (there was no cheap way to); this is that way.

### 3.8 The normalization queue (request/claim mechanics)

`normalize` is the one stage the tooling does not run itself — it is interpretive, performed by an external **loop session** (e.g. a Claude Code `/loop`). The corpus provides only the request/claim contract (spec §8.5); it never spawns or names a normalizer. The verbs live in `_cli/{enqueue,drain,finalize,release,await,queue}.py` over the `corpus.queue` library.

**State layout (`corpus.queue`).** External, untracked, under `<root>/queue/` (gitignored alongside `artifacts/` `capture/` `cache/`), one marker per record:

- `<id>.req` — a pending request (`requested_at`, `requested_by`).
- `<id>.claim` — claimed/in-flight (`claimed_at`, `claimed_by`).
- `<id>.result` — the last terminal outcome (`completed` | `failed`, with `reason`).

A record's queue state is a pure function of which marker exists: `requested` / `claimed` / `idle`. The markers are JSON written atomically (temp sibling + `os.replace`). **The queue never touches `records/`** — every verb is read-only on the record (`finalize` reads it to lint; `await` reads `status` as a fallback).

**Atomic claim.** `drain` claims by `os.rename(<id>.req → <id>.claim)` — atomic on POSIX, so when two loop sessions race for the same request exactly one wins (the loser's `rename` raises and it moves to the next candidate). Requests are claimed FIFO by `requested_at`. An empty queue returns nothing on stdout and **exit 1** — the `/loop` stop signal. A stale `<id>.claim` (a dead session) is reclaimable once `claimed_at` is older than `--lease` (default 30 min); reclaim renames it back to `.req`. A duplicate pass from an over-eager reclaim is wasteful, not unsafe (re-normalization is idempotent), so reclaim is best-effort.

**The loop session** (the agent, not the tooling) drives it:

```bash
while id=$(corpus drain --by "$SESSION"); do
    corpus guidance "$id"     # the merged overlay normalization.guidance (§3.7)
    # ...the agent normalizes $id in-session: title, description, embed/segment
    #    descriptions, re-segmentation; sets status: normalized; recompiles...
    corpus finalize "$id" || corpus release "$id" --failed "<reason>"
done
```

That bare loop is the **scheduled** shape: a tick (cron) drains until dry, then the model sleeps until the next tick — so the *model* polls, waking on a clock even when the queue is empty. `drain --wait` moves the poll off the model: it long-polls the claim primitive **in the subprocess** (the free layer) and returns the instant a request is claimable, blocking instead of exiting 1 on an empty queue (until `--timeout`, if set; `--interval` sets the poll cadence, default 2 s). The wait holds no claim — `drain` claims atomically only at the moment it succeeds — so an interrupt mid-wait (exit 130) leaks nothing. A **standing** loop runs `corpus drain --wait` under a persistent runner that re-invokes per claim, so the (expensive) model is woken only when there is genuinely work, not on a clock. The contract is unchanged: `--wait` is an ergonomic over the same atomic claim; without it the scheduled loop above behaves exactly as before.

`finalize` is the **done gate**: it refuses (exit 1, claim left intact) unless the record is `status: normalized` *and* lints with no `error`-severity findings — so a dirty pass is never reported complete. A requester (a codex agent) does `corpus enqueue <id>` then `corpus await <id>`; `await` polls the external state and resolves by exit code (0 = completed / `normalized`; non-zero = failed or timeout), so it works for a **re-normalization** of an already-`normalized` record (status alone can't tell the new pass apart — the queue entry can). Because the per-domain knowledge rides in overlays (`corpus guidance`), one generic loop serves every codex; a codex contributes by authoring overlays and enqueuing, never by supplying a normalizer.

**Result lifecycle.** `.req` and `.claim` are transient — each transition is an atomic rename that consumes the prior marker — but `complete`/`fail` leave a `<id>.result` that nothing removes on its own, so settled outcomes accumulate (one small JSON per ever-normalized record). A `.result` is **coordination state for `await`, not history** (the record's `status`/`touch[]` is the durable trail); it must outlive the pass so a *decoupled* requester can await after the loop tick ends, which is exactly why results are **not** deleted on loop end (that would race the awaiter, dropping it to the `status` fallback that can't distinguish a re-normalization). They are instead GC'd by age: `corpus queue --prune [--older-than DAYS]` (default 7 d; `0` = now) removes settled results past the grace window and sweeps crash-orphaned `*.tmp.*` write scratch, never touching live `.req`/`.claim`. Run it periodically (a cron tick, or before/after a drain session); it is idempotent.

---

## 4. Composite classifications (the curator feedback loop)

Composite classification schemas are corpus-local and corpus-author-driven (the Curator agent's domain; spec §7.4). They emerge from observed patterns in how the corpus is used, not from upfront design — and the package ships none.

### 4.1 Pattern detection

The curator periodically scans for patterns that warrant a classification:

- **Origin / fact frequency.** Many records share an origin host or a deterministic fact (a `ytdlp_channel_id`, a URL shape) — a candidate for a `classify_when`-keyed class.
- **Recurring extended-field values.** Many records share a value in a schema-extracted field — a candidate sub-classification.
- **Codex-driven demand.** The codex / compendium layers (`impl-codex.md`) reach for metadata that isn't yet extracted.

### 4.2 Schema authoring

A composite overlay lives at `schema/composite/<namespace>/<id>.yaml` (the namespace universal at `<namespace>/<namespace>.yaml`) and declares (spec §7.4):

```yaml
kind: mechanical          # or interpretive
applies_at: [record]      # subset of [record, section]; default [record]
applies_to:
  content_types: [...]    # mechanical only
classify_when:            # optional deterministic membership predicate
  all_of:
    - media.channel_id: {equals: "UC-..."}
extended_fields:          # bare — the classify opener scopes them
  episode_date: {type: string, semantic_type: timestamp}
normalization:
  guidance: |             # interpretive payload (consumed at normalize)
    ...
```

`classify_when` (spec §7.4) is the deterministic-membership lever: when present, the drafter stamps the class on every matching record at draft with `provenance: auto`. It is orthogonal to `kind` — an `interpretive` overlay may carry a `classify_when`, so membership is decided at draft while its guidance is still applied at normalize.

### 4.3 Re-propagation

Authoring or editing an overlay does not touch existing records until a sweep re-evaluates membership:

- **`corpus reclassify [target] [--mime/--host/--classification/--status] [--dry-run]`** re-runs the `classify_when` engine over **stored** records (body-safe; preserves asserted blocks), converging every `provenance: auto` block to the current rules — default all statuses incl. `normalized` (§3.1).
- **`corpus redraft`** re-derives records from their retained artifacts when the change is to a mime schema, drafter, or fingerprint knob (refuses `normalized` unless `--force`).

Lint's `classification-stale` (warning) flags an `auto` block whose overlay was deleted or no longer matches; the fix is `corpus reclassify`. `git diff records/` is the review surface for any sweep.

### 4.4 Schema evolution

As patterns refine, overlays iterate — narrow a too-broad `classify_when`, augment weak `extended_fields`, split a class into subclasses. Each iteration is followed by a targeted `corpus reclassify` (or `redraft`) over the affected scope.

---

## 5. Re-runs and re-normalization

Every pipeline stage is independently and idempotently **re-runnable** (spec §8.3); a re-run appends a `touch[]` entry. Re-processing is how the corpus absorbs improvement: new schemas, a better extractor / transcriber, an upgraded normalization model, or newly-captured artifacts that resolve old cross-references.

### 5.1 The re-run verbs

- **Re-ingest** — re-encountered bytes matching an existing `id`; folds the capture into origin blocks (§2.5), never a new record.
- **`corpus redraft`** — re-derive a record from its **retained artifact** + current schemas / tooling (§3.1). `id = blake3(artifact)` is unchanged, so it is an in-place `.md` rewrite; **idempotent** (an unchanged record re-derives byte-for-byte and is not rewritten), `--dry-run` reports the set. Refuses `normalized` unless `--force`. Filters `--mime` / `--host` / `--status`.
- **`corpus reclassify`** — re-evaluate `classify_when` membership over stored records (§4.3); body-safe, all statuses.
- **Re-normalize** — re-run the interpretive (LLM) pass; refreshes interpretive classify and issue context blocks, may re-segment.
- **`corpus compile`** — reassemble a record from a decomposed **manifest** (the normalization edit substrate, §3.1) — a different input than `redraft`'s artifact.
- **`re-stub`** — the deliberate reset to `status: stub` (spec §8.4): discards everything schema-derived (body, classify / embed / context blocks, `canonical` / `perceptual`), keeps everything byte-tied (`id`, `transport`, origin `uri:` history, `visibility`) and collapses `touch[]`.

### 5.2 Scoping a sweep

The deterministic re-derivation makes scoping a `git diff records/` concern rather than a frontmatter-diff one: re-derive the affected set and the diff *is* the surgical, reviewable change surface — no field-level diff / merge logic. Scope by the most precise selector available — `--host` (a re-captured / re-overlaid origin), `--mime` (a drafter or mime-schema change), `--classification` (a reworked composite), `--status` (e.g. only `draft`).

### 5.3 Cross-reference re-resolution

A lightweight sweep re-runs only §3.2 against existing bodies — useful after a batch of captures that may resolve URLs left as plain markdown in older records. `corpus links` / `corpus crawl` surface what is now resolvable vs. still-frontier.

---

## 6. Open implementation questions

These are flagged for follow-up; not all are blockers.

- **Sharding crossover** (applies to both corpus and codex). When does single-level hex-prefix sharding stop being adequate? At what record count do we move to two-level (`a7/f3/...`)? Likely a tooling-driven flag declared in `corpus.toml` (corpus side) or `codex.yaml` (codex side), with tooling rebalancing on change. `impl-codex.md §8` defers to this entry as the canonical write-up.
- **Binary cache GC.** Is the binary cache append-only forever, or does it have a GC pass for orphaned binaries (records deleted, hash unreferenced)? Deferred until corpus deletion semantics are needed.
- **URI index persistence.** The URI → `id` lookup (`records.build_uri_index`) is **rebuilt-on-start** from the records — the settled default (an in-memory query engine, not a data store). A persistent side-file is a deferred perf optimization, not an open design question.
- **Schema validation.** Should schema files themselves be validated (a `classify_when` predicate's ops parseable, `extended_fields` well-formed, `semantic_type` within the closed seven, no reserved `provenance` declared as a field)? `corpus lint` validates *records*, not schemas; a `validate-schemas` command is still missing.
- **Multi-corpus capture.** When the same content needs to land in multiple corpora (e.g., something captured personally and also of public interest), does the capture flow handle that, or is it a copy step on top? Currently a copy step; a "capture into multiple corpora" mode is a possible future feature.

## 7. The read API (`corpus.api`)

`corpus.api` (behind the `[api]` optional extra → `fastapi`, `uvicorn[standard]`, `python-multipart`) is a thin **read** HTTP surface over this pipeline's library functions — it serializes what `records` / `derived_views` / `segments` / `schemas` / `resolver` / `store` already produce, adding **no** parsing/derivation/resolution logic. It is the server for the Angular Corpus Console (`web/`). FastAPI/uvicorn import only inside `corpus.api.app`/`__main__` (never the base library — gotcha #24/#70).

- **Multi-corpus routing** (`corpus.api.config`). The tooling is single-root per invocation; fronting several corpora from one server is an API concern. `corpus-api serve --corpus <id>=<path> …` (or env `ATH_API_CORPORA`, or cwd discovery) maps ids → roots; each root's own `corpus.toml` is still read via `config.load_config` for the store/transcription backends.
- **Serialization** (`corpus.api.serialize`, pure). Maps the unified `Post` blocks to the Console JSON: `transport` (the 1:1 artifact), `embeds[]` (`media_type`/`address`/`transport`/`fields`), `origins[]`, `classifyBlocks[]`, `artifactFields`, `content[]` (sections+segments from `segments.iter_blocks`), `annotations[]` (`derived_views.context`), `concepts[]` (`derived_views.concepts`, each entry **KB-enriched** with a live `summary`/`source` when a resolver is configured), `touch[]`, derived `classifications[]`, and `tokens` (`{body,blocks,full}` from `corpus.tokens`). Title via `records.title_for`; mime via `records.media_type_for`.
- **Token counts** (`corpus.tokens`, a derived view — spec §9, never persisted). Three **cumulative** tiers sizing a record as LLM context: `body` (content-zone text segments), `blocks` (the whole record markdown — `records.dumps(post)`), `full` (`blocks` + Σ image estimate over image embeds + an image artifact, ≈ `min(w·h, 1.15 MP)/750` per Anthropic). Text is counted with a local Claude-proxy tokenizer (`tiktoken` `o200k_base`); tiktoken is **lazy-imported** with a chars/4 heuristic fallback, so the base library + import guard (gotcha #24) never pull it in. Installed via the `tokens` extra (also folded into `[api]` so the served field is real, not heuristic). The index caches the three ints per record (`_ingest`, like `size`/`segment_count`) and exposes them as numeric **core fields** `core::tokens_{body,blocks,full}` (mirroring `core::size_mb`) — so they get `/fields` histogram stats and `cond=…~number~between~lo,hi` filtering for free; the workbench row carries `tokens_*` for the ledger. **Offline caveat:** `o200k_base` fetches its BPE vocab from the web on first use, then caches under `TIKTOKEN_CACHE_DIR` — warm the cache once (gotcha).
- **Concept KB** (`corpus.wiki` + `corpus.concepts`, behind the `wiki` extra → `libzim`). A read-only handle on a Kiwix Wikipedia **ZIM** (full-text `Searcher` + title `SuggestionSearcher`, article read, best-effort Wikidata-QID parse from the article HTML). `libzim` is **lazy-imported** so the base library + import guard never depend on it; the ZIM path resolves `--wiki-zim` / `ATH_WIKI_ZIM` / `[corpus.wiki].zim` (one ZIM fronts every corpus). `concepts.ConceptResolver` layers a corpus-local registry (`<root>/concepts/*.yaml`, `local:<slug>` custom concepts — the curatorial extension point) over the ZIM (local-first), unifying `search`/`get`. The chip gloss is fetched live and never written to a record (concept blocks stay lean). Without a ZIM the resolver degrades to local-only and the wiki endpoints return `503`.
- **Index** (`corpus.api.index`, per-corpus, in-memory, process-cached). Builds the facet tree (mime/origin-host/status/visibility/`composite:<ns>`/`concept`, count-desc — the server-side `cxBuildFacets`; the `concept` facet keys on the concept join id and labels by display name), the typed `extended_fields` registry (`extended_fields.<f>.type` → the Console vocabulary `string|number|uri|date|bool|list|hash`, with value collection — the server-side `cxOverlayValues`), and filter/sort/paginate. Origins are faceted by **host** (a superset that also keys the overlay lookup, since overlay ids are hosts), because `derived_classifications` only emits `origin/<id>` for overlay-matched origins.
- **Endpoints** (`/v1`): `corpora`; `{corpus}/records` (params `q,sort,offset,limit` + repeated `facet=<key>=<value>` / `field=<overlayKey>::<f>=<value>`); `{corpus}/facets`; `{corpus}/schema`; `{corpus}/records/{id}`; `{corpus}/records/{id}/graph` (read-only connection graph for the record workbench's *graph* mode — resolved origins/embeds/classification-peers/captured cross-refs + uncaptured outbound links extracted from the body via `corpus.graph`, dedup/capture-checked against a per-corpus URI index cached on `CorpusIndex`; the capture *action* routes to the deferred submit phase); `{corpus}/artifacts/{id}` (`store.ensure_local` → `FileResponse`, GET+HEAD, range-served); `{corpus}/resolve?uri=corpus://…` (`resolver.resolve` → `FileResponse`; the functional-URI value must be fully percent-encoded — gotcha #68); `health`. **Concept KB** (corpus-independent, registered before the `{corpus}` routes): `wiki/search?q=&limit=` and `wiki/article?id=` (`503` when no ZIM is configured). The workbench row also carries `transport_name` (`serialize.transport_name`, `<id[:12]>.<ext>`) for the ledger's untitled placeholder — the same value the detail's `transport.name` uses. **Write** routes: `POST records/{id}/regions` (the crop-editor save) is **implemented** — it loads the record, replaces its bbox-addressed content-zone segments with the posted set (`corpus.regions.save_regions`, via the `recordbuild` construction ops so the grammar is validated before any write, then an atomic `paths.atomic_write_text`), preserving the metadata zone + frontmatter title and appending a `corpus.regions@` touch; the API then rebuilds the per-corpus index (`get_index(fresh=True)`). `POST check`/`submit` remain stubbed `501` pending the submit/ingest phase.
