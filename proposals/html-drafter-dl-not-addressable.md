# Proposal: the HTML drafter's `<dl>` is not addressable

**Status:** **implemented.** `dl` added to `_ADDRESSABLE_TAGS` in `draft/html.py` + `transforms/html.py` (lockstep), with a round-trip regression test in `tests/test_drafters.py`. No normative spec change — the fix brings the impl *closer* to the spec's stated `el=N` ("any element") semantics. The §5 addressing-index-stability caveat applies: HTML records that contain a `<dl>` need a re-draft to pick up the new numbering.
**Scope:** `corpus/draft/html.py`, `corpus/transforms/html.py`, `tests/test_drafters.py`. One tuple, mirrored in two files, plus a test.
**Author:** HTML-drafter follow-up.
**Naming note:** the repo's existing proposal lives at `docs/PROPOSAL-dependent-references.md`. This file follows the path that was requested (`proposals/…`); relocate to `docs/PROPOSAL-html-drafter-dl-not-addressable.md` if convention alignment is preferred.

---

## 1. The gap

The mechanical HTML drafter assigns an `el=N` address to a curated set of structural /
content-bearing tags and **only** that set:

```python
# corpus/draft/html.py:137
_ADDRESSABLE_TAGS = (
    "section", "article", "p", "ul", "ol", "table",
    "pre", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
)
```

`<dl>` — the definition list — is absent. Its block-level list siblings `<ul>` and `<ol>`
are both present. The set is mirrored verbatim in the resolver
(`corpus/transforms/html.py:30`) and the two are asserted to stay in lockstep
(`tests/test_drafters.py:292`), so the omission is symmetric: the drafter never tags a
`<dl>`, and the resolver could never resolve an `el=N` to one.

This is an **oversight, not a design choice.** The curation exists to drop *layout-only
wrappers* — the comment at `draft/html.py:132` is explicit: "`div`, `span` are NOT
addressable — they're chrome the drafter unwraps anyway." A `<dl>` is the opposite of
chrome: it is semantic content, the exact peer of `<ul>`/`<ol>`. The drafter already
treats it as content elsewhere — `draft/html.py:122` keeps `id` globally *specifically*
so that "cross-reference anchors target ids on headings **and definition-list items**"
don't dangle. So the code simultaneously (a) preserves `<dl>` content and its anchor ids,
and (b) refuses to give the `<dl>` block an address. Those two positions are inconsistent.

## 2. What happens today

A `<dl>` is **not removed** — the drafter strips only non-rendered infrastructure
(scripts/styles/comments), never content — so its text survives into the cleaned `<body>`.
Nothing is lost. But because it carries no `data-el="N"` annotation:

- **It is not an individually addressable segment.** A `concept`/`reference` annotation,
  a citation, or any functional URI (`corpus://<id>?el=N`) cannot point *at* the
  definition list. Glossaries, term/definition blocks, FAQ markup, and the `<dl>`-based
  metadata key/value blocks many CMSes emit are unreachable by address.
- **Its content is absorbed into a neighbor's range.** Segment boundaries are the
  `data-el` positions (`enumerate(work.find_all(_ADDRESSABLE_TAGS), start=1)`,
  `draft/html.py:393`). A `<dl>` sitting between two addressable elements is not a
  boundary, so when the wrapper `el=1-<max>` segment is later split, the `<dl>`'s text
  gets attributed to whichever addressable sibling swallows it — a quiet provenance smear.
- **The resolver agrees it doesn't exist.** `soup.find_all(_ADDRESSABLE_TAGS)`
  (`transforms/html.py:90`) skips it, so even a hand-written `el=N` aimed at a `<dl>` can
  never materialize.

Contrast `<ul>`/`<ol>`: each is one addressable block (one `el=N` for the whole list, not
per-`<li>`), a clean citation target, and a hard segment boundary. `<dl>` should behave
identically.

## 3. Why this matters / why now

The spec is *more* permissive than the implementation here. `el=<N>` is defined as "a
1-indexed index to **any** element in an HTML artifact … output determined by the element"
(`spec-corpus.md:627`, restated `spec-corpus.md:1115`), and `impl-corpus.md:197` describes
the drafter as assigning "`el=N` addressing to **every element** of the raw artifact." The
real `_ADDRESSABLE_TAGS` is a deliberate narrowing of "every element" down to "every
*content* element" — sound in intent, but `<dl>` was dropped on the wrong side of that
line. Closing the gap moves the impl *toward* the spec, not away from it.

"Why now" is the addressing-stability argument (§5): the cost of adding `dl` is paid by
re-numbering, and that cost only grows as hand-pinned `el=N` annotations accumulate.
Today, with concept/reference annotation freshly landed and few (if any) `el=N` addresses
authored against live HTML records, the blast radius is at its minimum.

## 4. The decision: `<dl>` is addressable, `<dt>`/`<dd>` are not

Follow the list precedent exactly:

- **`<dl>` joins `_ADDRESSABLE_TAGS`** — one `el=N` for the whole definition list, the peer
  of `<ul>`/`<ol>`.
- **`<dt>`/`<dd>` stay out** — they are the peers of `<li>`, which is itself not addressed.
  The list is the addressable unit; its items are interior structure the normalizer renders
  to markdown.

This is the consistent, minimal choice. The alternative (addressing `<dt>`/`<dd>`
individually) would break parity with `<ul>`/`<ol>`/`<li>`, multiply the index inflation in
§5, and buy nothing the whole-`<dl>` address plus preserved item `id`s don't already give.

## 5. The one real cost: `el=N` index stability

`el=N` is a **position**, not a stable identity:
`enumerate(find_all(_ADDRESSABLE_TAGS), start=1)`. Adding `dl` to the set means any
document containing a `<dl>` gets `+1` to the index of *every addressable element after it*.

- **Internally consistent on re-draft.** Embeds, segment addresses, and the cleaned body
  are all regenerated in the same pass, so a freshly drafted record is self-consistent —
  the renumbering never desyncs a record from itself.
- **The exposure is hand-authored cross-references.** A `concept`/`reference` block whose
  `address: el=N` was pinned against the *old* numbering, on a record that contains a
  `<dl>` before the cited element, will silently point one element early after a re-draft.
  This is the same fragility `el=N` already carries for any content edit upstream of an
  annotation — adding `dl` just triggers it once, deterministically.

Mitigation: do it before such addresses proliferate (§3), and treat it as a one-time
re-draft of HTML records. An optional belt-and-suspenders step — grep existing
`address: el=` annotations on HTML records and re-verify them post-change — is cheap at the
current corpus size and worth a line in the migration note. No artifact bytes change; only
derived proxies do.

## 6. The fix

1. `corpus/draft/html.py:137` — add `"dl"` to `_ADDRESSABLE_TAGS`, in the prose-block group
   beside `ul`/`ol`. Update the enumerating comment (`draft/html.py:128–131`) to name it.
2. `corpus/transforms/html.py:30` — mirror the addition (lockstep, asserted at
   `test_drafters.py:292` — the test passes only if both move together).
3. `tests/test_drafters.py` — extend the drafter fixture / addressing test so a document
   containing a `<dl><dt>…</dt><dd>…</dd></dl>` yields one `el=N` for the `<dl>` and the
   resolver round-trips `corpus://<id>?el=N` back to that block.

No spec edit required. Optionally tighten `impl-corpus.md:197`'s "every element" wording to
"every content element (`_ADDRESSABLE_TAGS`)" so the doc stops overstating the axis — but
that is editorial and independent of this fix.

## 7. Open questions

- **Audit the rest of the axis while we're here?** `<dl>` is the clear miss, but the same
  "content peer of an included tag, currently excluded" test could be run against
  `<details>`/`<summary>` (collapsible content), `<aside>` (often content, sometimes
  chrome), and `<dialog>`. Recommendation: ship `<dl>` alone (unambiguous), and only widen
  if a real corpus surfaces a second miss — each addition pays the §5 renumbering cost.
- **Migration scope.** Is a full re-draft of HTML records acceptable now, or should the
  change ride along with the next normalize-loop pass that re-drafts them anyway? The
  latter folds the cost into work already happening.
- **Should `el=N` ever become stable (id-based) instead of positional?** Out of scope here,
  but this proposal is a small data point for that larger question — positional addressing
  makes *any* axis change a renumbering event.
