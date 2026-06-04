# URL Equivalence — overlay-declared identity rules

**Status:** IMPLEMENTED (2026-06-04). Authored corpus-side, validated by the g8board pagination work;
built on the athenaeum tooling side. The knob, identity-key algorithm, and four application sites are
**spec-corpus §7.2** (`url_equivalent` capture field) + **impl-corpus §2.11** (URL equivalence — identity
keys). The g8board overlay adoption + live re-capture (the worked case below) stay the curator's
corpus-side follow-up.

## Why

A record's `origin.uri` list should hold **one URI per distinct resource**, and an inbound URL should
match a record whenever it denotes the same resource — *even when the spelling differs*. Today identity
is (post-`url_rewrite`) string equality, so trivially-equivalent spellings fragment:

- **Query noise.** `…/threads/slug.287089/page-2` ≡ `…/page-2?nested_view=1` ≡ `…/page-2?utm_source=x`.
  The g8board pager historically emitted `?nested_view=1` links; a logged-in/threaded session adds
  view/affiliate params. Each variant became a separate alias (or a miss).
- **First-page spelling.** `…/threads/slug.287089/` ≡ `…/threads/slug.287089/page-1` (page-1
  server-redirects to bare). A capture seeded at the bare URL records the bare form; an inbound
  `/page-1` then **misses the record** though it's the same page.

`url_rewrite` can paper over some of this, but it's the wrong tool: it transforms **what gets fetched**,
not **what counts as the same resource**, and using it for identity both changes the fetch and litters
the origin list with the rewritten variants. We want a separate, declarative **equivalence** layer.

## The feature: `capture.url_equivalent`

A per-host overlay list of normalization rules, **same pattern→replacement shape as `url_rewrite`**, but
applied to compute a URL's **identity key** — never to change the fetched URL. Two URLs are equivalent
iff their identity keys are equal.

```yaml
capture:
  url_equivalent:
    # first page == bare thread URL. A NAIVE rule is enough: the identity layer folds the
    # sub-path trailing slash (`…/slug.id/` ≡ `…/slug.id`), so this and the bare slashed origin
    # `…/slug.id/` converge on one key — the rule need not chase the slash. (See the resolved
    # trailing-slash note below; the `…/slug.id/page-1/` form is absorbed by the `/?` too.)
    - pattern: '/page-1/?$'
      replacement: ''
    # view / affiliate / tracking params don't change identity (strip them)
    - pattern: '[?&](nested_view|affiliate-data|utm_[^=&]*)=[^&]*'
      replacement: ''
```

A small **query shorthand** covers the common "no query param is significant for this host" case
(g8board is exactly this) without enumerating each:

```yaml
capture:
  url_equivalent:
    query: drop                 # strip ALL query params for identity
    rules: [ … ]                # optional, applied after `query`
    # default `query: keep`; ?page=, ?id=, search queries stay significant unless a rule says otherwise
```

### Canonicalization algorithm
To get a URL's identity key: apply built-in normalizations (lowercase scheme+host, drop a fragment,
sort surviving query params), then — for `query: drop` — strip the whole query, then apply each
`url_equivalent` rule in order (`re.sub(pattern, replacement, url)`), then a final tidy (collapse a
dangling `?`/`&`), then **fold a sub-path trailing slash** (`…/a/b/` ≡ `…/a/b`). Compare keys for
equality. **`url_rewrite` is independent** — it still rewrites the *fetch* URL; identity is computed from
the *original* inbound URL via `url_equivalent` (or, with `on_rewritten: true`, from the post-rewrite
URL — opt-in, default the original).

> **✓ Trailing-slash finding — RESOLVED (athenaeum, 2026-06-04).** The curator caught it live: `normalize`
> **preserves** a sub-path trailing slash (`…/slug.id/` does NOT reduce to `…/slug.id`), and the recorded
> origin is the slashed form, so a naive `…/page-1 → \1` rule produced the slash-less key and **missed the
> real origin** (record `a72470d6`). **Decision: the fold lives in the identity-key step, not in
> `normalize`.** `normalize`'s output is the URL a crawl **re-fetches** (`crawl._expand` stores
> `normalize(link)` as the fetch target), and a server may distinguish `/a/b` from `/a/b/`, so the fetched
> form must keep its slash. But an identity *comparison* key is free to fold it — so `urls.identity_key`
> now folds a sub-path trailing slash as its final step (`_fold_trailing_slash`). Consequences: a **naive
> `\1` rule just works**; `bare ≡ bare/ ≡ /page-1` converge for any host that declares `url_equivalent`;
> the curator's explicit `\1/` overlay rule is unaffected (it folds to the same key). The fold applies
> only inside the opt-in identity layer (a host without `url_equivalent` keeps trailing slashes
> significant, matching the fetch form). The earlier "drop a trailing `/`" claim about `normalize` was
> inaccurate and stays removed.

## Where it applies (all the identity sites, not just capture)
1. **Capture short-circuit** — `corpus capture <url>` already-captured check: canonicalize `<url>`,
   compare against stored origins' keys.
2. **Pagination uri-recording** — as a merge marches `rel=next`, a page URL whose key equals an
   already-recorded origin URI is **not appended** (the user's ask: "they wouldn't need to be added to
   the uris list if it already matched as equivalent"). Distinct pages (page-2, page-3) keep distinct
   keys and are still recorded once each; their param/first-page variants collapse.
3. **Crawl frontier dedup** — don't enqueue a URL whose key matches a visited/captured resource.
4. **`resolve`** — a `corpus://` or raw URL resolves to the record whose origin key matches.

## Recording
Store the **first-encountered** spelling as the canonical origin URI (e.g. the bare seed). Equivalent
spellings are *not* added. Optionally keep a single `canonical:` form per the rules; do **not** expand
the alias list with every variant — the point is a minimal origin block.

## Defaults / safety
- **Opt-in.** No `url_equivalent` ⇒ today's behavior (string identity). Default `query: keep`.
- Rules are host-scoped (the overlay), so a blanket `query: drop` can't wrongly fold a host where
  `?page=`/`?id=` matters.
- Equivalence is **identity-only**: it must never influence which bytes are fetched or how a page renders
  (that's `url_rewrite`/`interactions`). Keeping the two layers separate avoids the "rewrite for matching
  also changed the capture" trap that motivated this doc.

## g8board adoption (the worked case)
g8board's view mode is now a logged-in-account setting (LINEAR), so the overlay carries **no**
`url_rewrite` and captures clean bare `/page-N` URIs. With `url_equivalent` it additionally gains:
`/page-1 ≡ bare` and `query: drop` (nested_view/affiliate-data/etc. are all noise). Then an inbound
`…/page-1?nested_view=1` matches the record with **no** extra alias stored. Test fixtures: thread
`somebody-help-low-voltage-now-key-stuck.286547` (3 pages, record `a72470d6`) and
`g8-gt-diy-camshaft-swap.287089` (34 pages, record `49d4caee`) — assert their origin lists stay
bare-only and that `/page-1`, `/page-1?nested_view=1`, `/page-2?nested_view=1` all match.

## Open questions (resolved at implementation, 2026-06-04)
1. **`query: drop` vs per-rule** — **RESOLVED: shipped both.** The `query: keep|drop` shorthand (default
   `keep`) handles the common "no query param is significant" case; the regex `rules` give precision.
   `normalize_equivalence` accepts the bare-list (rules-only) form and the `{query, rules, on_rewritten}`
   map form.
2. **Should `url_rewrite` outputs feed `url_equivalent`?** — **RESOLVED: shipped the opt-in hook.** Default
   is identity from the original inbound URL; `on_rewritten: true` computes the identity key from the
   `url_rewrite` output instead. No host needs it today (g8board dropped `url_rewrite`), but the knob is
   live (`urls.identity_key(..., url_rewrite=)`).
3. **Param *value* significance** — **DEFERRED (YAGNI).** No host yet needs a param whose name matters but
   only for some values; revisit if one appears. A `rules` regex can already match specific `name=value`
   forms if needed.
4. **Interaction with content-scoped `canonical.content_selector`** — composes unchanged. URL-equivalence
   is pre-fetch (cheap, by spelling — the identity key); content-canonical is post-fetch (by bytes — the
   draft-time content-dedup). URL-equiv collapses spelling variants first; content-canonical still merges
   genuinely-distinct URLs that render the same body (the alldata DTC case).
