# Pagination → Capture-Time Reconciliation (`pagination: true`)

**Status:** **IMPLEMENTED** in athenaeum `tools/corpus` (2026-06-03) — `capture.pagination` knob
(`capture/pagination.py` + `_reconcile_pagination`), spec'd in `spec-corpus.md §7.2` and
`impl-corpus.md §2.10`. This build ships: structural content-region auto-detect + declared
`content_selector`; `rel=next` + `next.selector` enumeration (**`next.url_pattern` deferred**);
the id/subtree-dedup merge; bare+pinned origin aliases + `pagination:` provenance; the
`pagination-incomplete` completeness detector; and crawl frontier exclusion via origin-alias match.
The **corpus-side follow-up** (the g8board overlay's flat-pin `url_rewrite` + `pagination` block and
the live re-capture) remains the curator's, below.
**Author:** Curator (corpus repo), 2026-06-03.
**Spec home:** `spec-corpus.md §7.2` (capture overlay) + `impl-corpus.md §2.10` (capture).

## Why

A paginated thread / article / gallery is **one logical artifact**, but the site splits it across
`?page=N` URLs. Capturing only page 1 silently loses the rest; capturing each page as its own record
fragments one work into N content-addressed records. We want: **walk the pages, merge them, and store
ONE content-addressed artifact** — the complete work as a single record — driven by a single overlay
knob, generically, for most sites.

This was prototyped against a live XenForo thread (see **Test case**). Two naive approaches both
**silently dropped posts** — a per-host fetch+inject `eval` got 46/54, and merging an inconsistent page
set got 51/54. The approach below got **54/54, lossless**. The lesson is baked into the design: *page
form must be consistent, and completeness must be checked.*

## The pipeline already stages to `capture/`

`capture()` (`capture/__init__.py:327`) writes a page's stripped SingleFile bytes to
`corpus_root/capture/<base>.html` and **does not ingest**. `ingest` then content-addresses those bytes
into `artifacts/<ab>/<blake3>` and writes the record. `capture_and_ingest()` (`:344`) chains them.

**Reconciliation slots cleanly between those two steps:** capture each page to `capture/` (existing
behavior, per page), **merge the staged page DOMs into one HTML**, then ingest *the merged file* as the
single artifact. The per-page staged files remain ephemeral in `capture/` (gitignored).

> **INVARIANT — only the merged artifact is ingested.** Per-page captures MUST use the staging-only
> `capture()` path, never `capture_and_ingest()`. No per-page bytes are ever content-addressed into
> `artifacts/`, and no per-page record is ever written — pages exist only as transient `capture/`
> staging files, which are deleted after the merge. Exactly one artifact (the merged document) and one
> record result from a paginated capture. (The corpus-side proof used `corpus capture` per page as a
> stand-in and wrongly persisted N page records into `artifacts/`; that is the anti-pattern this rule
> forbids.)

## Overlay surface

`pagination` under `capture:`, either the bare-bool minimal form or a map for config:

```yaml
capture:
  pagination: true            # minimal: enable, auto-detect everything
# — or —
capture:
  pagination:
    content_selector: '.js-replyNewMessageContainer'   # the per-page content region (else auto-detect)
    next:
      rel: true                # default: follow <a|link rel="next">
      # selector: 'a.pageNav-jump--next'               # override: CSS selector for the next-page link
      # url_pattern: '{thread}/page-{n}?nested_view=0' # override: construct page URLs directly
    max_pages: 100             # safety cap (log, don't silently truncate, if hit)
    expect_count:              # optional completeness oracle (see below)
      selector: '.pairs--rows dd'   # element whose text holds the reply/item count
```

Unset / `false` ⇒ today's single-page behavior (zero change for every other host).

## Reconciliation flow

1. **Pin a consistent page form (CRITICAL).** Run the seed URL through the existing `url_rewrite`
   (`capture:` overlay). This is where a site with multiple render modes is forced into ONE — see the
   test case, where the same thread renders *nested* (2 pages) at the bare URL but *flat* (3 pages) at
   `?nested_view=0`, and mixing them loses posts. **Apply `url_rewrite` to every page URL**, not just
   the seed, so the pin holds across the walk (a site's own `rel=next` href may drop the pinning query).

2. **Capture page 1** through the normal path (interactions → `remove:` chrome/ads → fidelity) into
   `capture/` staging. The strip runs **per page** so each page is clean before merge.

3. **Enumerate & capture the rest.** Default: follow `link[rel=next]` / `a[rel=next]` from each captured
   page (emitted by XenForo, WordPress, Discourse, vBulletin, most CMSs). Overrides: a `next.selector`
   or a `next.url_pattern`. Capture each next page (stripped) to `capture/`. **Stop** on: no next link /
   pattern miss / a page contributing zero new content-region children / `max_pages`.

4. **Merge.** Page 1 is the **common framework**. For each subsequent staged page, take its
   `content_selector` region and **append that region's child nodes, in order, into page 1's region**,
   **deduping by element id** (and by a normalized-subtree hash for nodes lacking ids — pages can repeat
   a post, e.g. quoted-OP or threaded context). Promote lazy `img[data-src] → src` on appended nodes so
   the capture's `<img>` pre-fetch inlines them.
   - **Content-region detection.** If `content_selector` is declared, use it (robust — recommended).
     Else **auto-detect**: walk page 1 vs page 2 in lockstep; the matched-identity element
     (tag+id+class path) whose descendants differ and which holds the most text is the content region.
     Auto-detect is the zero-config default; the declared selector is the escape hatch.

5. **Ingest the merged document** → `blake3` → `artifacts/<hash>` → one record (stub). The HTML drafter
   then sees one long thread and drafts normally.

6. **Provenance / identity.** Recorded origin URI = the **clean public** seed URL (drop the view-pin
   query — same pattern as the alldata vehicle→article alias and reddit old.reddit alias). Record the
   constituent page URLs (incl. the `?nested_view=0` / `page-N` forms) as origin aliases, plus a small
   `pagination:` provenance block: `{ pages: N, form: '<pinned url_rewrite>', posts: M }`. Note: the
   merged artifact's hash changes when the thread grows (a new reply ⇒ new bytes ⇒ new record); that is
   correct content-addressing for a mutable source — capture again to re-snapshot.

## Completeness check (don't repeat the silent-loss bug)

If `expect_count` is given (or a site emits a machine-readable count — XenForo's "N replies"), compare
merged item count against it and **emit a capture-stage detector** (warn) on mismatch. Reconciliation
that yields fewer items than the source advertises is the exact failure both prototypes hit; surface it
rather than shipping a lossy record. If `max_pages` is hit, log how many pages were dropped.

> **COUNT SEMANTICS — found during the g8board corpus-side validation; (a) now RESOLVED in the tooling.**
> Three denominators didn't line up: the page advertises **"53 replies"**, the lossless merge holds
> **54 posts** (replies + OP), and the merge logged **"56 items"** (54 post articles + 2 non-post
> framework `div`s that ride in the `content_selector` region). **(a) Done:** `merge_pages` now counts
> **id-bearing** region children (`_count_items` — forum/CMS posts carry stable ids; framework nodes
> don't), falling back to all children only when none have ids. So `posts` is now an honest item count
> (54, not 56) — both the `pagination:` provenance and the completeness check use it. **(b) Residual
> (by design):** the detector compares with strict `<` (`merged < advertised`), which already tolerates
> the **+1-for-OP** off-by-one without false-firing (54 ≥ 53 passes; a ≥2-post loss fires). The only
> remaining nuance is that a loss of *exactly one* post right at the reply-count boundary can slip
> through — acceptable, since the merge is independently lossless by unique-id count. `expect_count` is
> therefore now **safe to enable** per host (point `selector` at the "N replies" element); the g8board
> overlay can turn it on. Athenaeum landed (a) + a regression test in the same arc as this doc.

## Interaction with `corpus crawl`

A crawl that owns a paginated host must **not** also enqueue the `/page-N` URLs as separate seeds — page
1's reconciled capture already absorbs them. Either exclude `rel=next`/`page-N` targets from the frontier
when the host overlay has `pagination`, or recognize them as constituents of an already-captured record.
(Otherwise every thread yields 1 merged record + N redundant single-page records.)

## Test case — g8board.com (XenForo "california" theme)

**Live URL:** `https://www.g8board.com/threads/somebody-help-low-voltage-now-key-stuck.286547/`
A real 2-page-or-3-page thread (see the quirk below). Public; captured via the headed Chrome on :9222.
The corpus already ships a `schema/origin/web/g8board.com.yaml` overlay (lean + ad/chrome strip — the
Primis video-ad widget inlines as a **140 MB** data: URI otherwise; stripped → 5.6 MB). For this test it
additionally needs the **flat-view pin** + `pagination`:

```yaml
capture:
  fidelity: lean
  url_rewrite:                      # pin FLAT view so all pages share one structure
    - pattern: '(/threads/[^?#]*?)(?:/page-(\d+))?/?(?:\?.*)?$'
      replacement: '\1/page-\2?nested_view=0'   # (implementation: ensure page-1 form + nested_view=0)
  pagination:
    content_selector: '.js-replyNewMessageContainer'
    next: { rel: true }            # XenForo emits <link rel="next">; url_pattern '{thread}/page-{n}?nested_view=0' also works
    expect_count: { selector: '.block-outer .pairs dd, [data-xf-init] .count' }  # "53 replies" → 53 (+OP)
  interactions:
    - { scroll: full }
    - { wait: { ms: 1200 } }
    - remove: [ 'iframe', '[id*="primis"]', '[class*="primis"]', 'div[id^="google_ads"]',
                '[data-google-query-id]', 'ins.adsbygoogle', '.adContainer', '[id*="google-one-tap"]',
                '#header-banner', '#cali-header', 'header.p-header', '.p-nav', '.p-footer',
                '.message-signature' ]
    - { wait: { ms: 400 } }
```

**The quirk this test exists to exercise** (the user has seen it across this site):
- The **bare URL and `/page-1`** render **nested/threaded** — `article.js-post.nested-level-root`,
  38 post nodes, paginates to **2 pages**. Nested view is also slightly **lossy** here (38 ≠ a clean 40).
- **`/page-N` and `?nested_view=0`** render **flat/linear** — `article.message`, paginates to **3 pages**.
- Posts carry stable ids `id="js-post-<NNNN>"`; the content container is `.js-replyNewMessageContainer`.

**Expected result (flat pin, measured 2026-06-03):**

| page (flat, `?nested_view=0`) | posts |
|---|---|
| 1 | 20 |
| 2 | 20 |
| 3 | 14 |
| **merged, deduped** | **54** = 53 replies + OP, **no overlap, no loss** |

Merged artifact ≈ **6.27 MB**. (Counts are time-sensitive — the thread is live; assert against the
page's own "N replies" header at capture time, not the literal 54.)

**Regression assertions for the implementation:**
- Flat-pinned reconciliation ⇒ merged post count **==** header reply-count + 1 (54 today). **Lossless.**
- WITHOUT the flat pin (mixing nested page-1 with flat 2/3) ⇒ 51 → the completeness detector MUST fire.
- A per-page fetch+inject without dedup/consistency ⇒ 46 → likewise must fire.
- A single-page thread ⇒ no-op (one page captured, no merge, byte-identical to today).

Regenerate fixtures by capturing the flat page URLs with the g8board overlay (the proof's per-page
captures were deleted — only the merged artifact should ever persist, per the INVARIANT above):
`…/286547/page-1?nested_view=0`, `…/page-2`, `…/page-3`. The 2026-06-03 proof produced a merged
artifact of ~6.27 MB (blake3 `c7be01b4287484eb63e33b881d2604641ed9888cdd4ed00ea895a1988370a94b`) —
illustrative only, since the live thread (and thus the bytes) drift; assert on the **post count vs the
header reply-count**, not on a fixed hash.

## Implementation pointers (tools/corpus)

- **Hook point:** between `capture()` (`capture/__init__.py:327`, stages to `capture/`) and `ingest`.
  A `capture_and_reconcile()` sibling to `capture_and_ingest()` (`:344`), or a branch inside it when the
  resolved recipe has `pagination`.
- **Reuse:** `url_rewrite` application (already in the capture recipe path); `fidelity` resolution
  (`FIDELITY_PRESETS` `:122`, `_resolve_fidelity`); the interactions/`remove:` snapshot path
  (`_snapshot_html`); the `<img>` pre-fetch inliner; `content_selector` resolution mirrors
  `recipes.canonical_content_selector_for_url` (used by `draft`); `rel=next` extraction can reuse
  `crawl._extract_links`’s BeautifulSoup pass (`crawl.py:303`).
- **Merge:** BeautifulSoup parse of each staged page; `select_one(content_selector)`; append children
  with id/subtree dedup; serialize; hand the merged bytes to `ingest`.
- **Detector:** add a `pagination-incomplete` capture-stage detector (sibling to the existing
  `inline-image-failure`) for the completeness mismatch.

## Open questions for athenaeum

1. **Auto-detect vs declared content region** — ship declared-`content_selector`-only first, add
   structural auto-detect (diff page 1 vs page 2) as a follow-up? The declared path is proven; auto is
   the harder, more generic half.
2. **Merged-record identity & `pagination:` provenance block** — exact shape; how aliases for the
   constituent page URLs are recorded (origin `uri:` list vs a dedicated block).
3. **Crawl integration** — frontier exclusion of `rel=next`/`page-N` when the host overlay paginates
   (above), so threads don't double-capture.
4. **`expect_count` ergonomics** — per-host selector vs a small library of known patterns
   (XenForo/Discourse/WordPress) so most hosts need only `pagination: true`.
5. **Stop condition for `url_pattern` mode** — no `rel=next` to signal the end; use
   "page contributed zero new content-region children" + `max_pages`.

## Corpus-side follow-up (Curator)

- Once `pagination` lands: finalize `schema/origin/web/g8board.com.yaml` with the flat-pin `url_rewrite`
  + `pagination` block above, re-capture the thread as one merged record, and re-point crawl to treat
  `/page-N` as constituents. Until then, g8board threads capture page-1-only (the overlay's strip/lean
  already works; pagination is the missing piece).
