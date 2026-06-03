# Capture Fidelity Tiers

**Status:** implemented in `tools/corpus` (2026-06-03). The capture-field contract now
lives in `spec-corpus.md §7.2` (`capture.fidelity`) and `impl-corpus.md §3.1`; this doc is
retained as the design rationale + empirical measurements. See "Implementation status" at the end.
**Author:** Curator (corpus repo), 2026-06-03
**Owner implemented:** athenaeum tooling

## Why

Browser capture inlines a self-contained snapshot via SingleFile. On asset-heavy SPAs that
boilerplate dwarfs the content. Measured on **my.alldata.com** (2009 Pontiac G8 repair manual,
the first large recapture target): a typical page is **~11.4 MB, of which ~85% is the Angular app
shell** — web/icon fonts shipped in four redundant formats (eot+ttf+woff+woff2) plus icon-sprite /
illustration SVGs — re-inlined fresh into *every* page. The actual content (a maintenance table, a
few diagram figures) is a couple hundred KB. The seed (vehicle home, zero diagrams) carries the
*same* 4.8 MB of SVG + 4.8 MB of fonts as a content leaf, which proves it's shell, not content.

At ~7,000 pages that's **~77 GB of almost entirely redundant bytes**, and content-addressed dedup
does not help (each page's whole-file blake3 differs because the content differs, so the shared
boilerplate is stored once per page).

But the fix is not universal: some sites should be captured **as exactly as possible** (design,
art, layout-sensitive pages where presentation *is* the content); others we capture **only for the
information**. So fidelity belongs on the per-host overlay, not as a global flag.

## Measured reductions (real AllData pages, empirical)

The option spellings below were verified live against the vendored SingleFile bundle — all four
take effect.

| Tier | SingleFile options added over base | Seed | Content leaf | ≈ ×7k pages |
|---|---|---|---|---|
| **exact** (current behaviour) | — | 11.34 MB | 11.46 MB | ~77 GB |
| **balanced** | `removeAlternativeFonts`, `removeAlternativeImages`, `removeAlternativeMedias` | **2.67 MB** (−76%) | 2.79 MB | ~19 GB |
| **lean** | balanced + `removeUnusedStyles` | **1.04 MB** (−91%) | — | ~7 GB |

Per-asset breakdown (seed, exact → lean):
- **Fonts 4.79 MB → 0.93 MB** — `removeAlternativeFonts` drops eot (`vnd.ms-fontobject`, IE-only) +
  ttf where a woff/woff2 alternate exists. The remaining ~0.9 MB is woff icon fonts with no woff2
  alternate (the floor; only an icon-font *removal* would cut further, which loses glyphs).
- **Chrome SVG 4.81 MB → 0.01 MB** — `removeAlternativeImages` drops the app icon-sprite /
  illustration SVGs (they sit *outside* the content region).
- **CSS 1.70 MB → 0.43 MB** — `removeUnusedStyles` (lean only) prunes rules with no matching element.

**Content fidelity confirmed:** a content leaf re-captured `balanced`/`lean` **merged byte-identically**
with its `exact` capture on the content-scoped canonical; and a Diagrams page kept all 5 PNG figures
*inside* `ad-repair-dynamic-content`. None of these options touch the drafted record — the mechanical
drafter reads DOM text/tables, not fonts/CSS — so records are identical across tiers; only the
gitignored `artifacts/` shrink.

## Design

Add a `capture.fidelity` field (enum: `exact` | `balanced` | `lean`) resolvable per host, mapping to
a SingleFile-options preset merged over the base `SINGLEFILE_OPTIONS`.

```python
# capture/__init__.py, alongside SINGLEFILE_OPTIONS
FIDELITY_PRESETS = {
    "exact":    {},                                          # byte-faithful; presentation IS content
    "balanced": {"removeAlternativeFonts": True,             # −76%, no rendering risk
                 "removeAlternativeImages": True,
                 "removeAlternativeMedias": True},
    "lean":     {"removeAlternativeFonts": True,             # −91%, information-faithful
                 "removeAlternativeImages": True,
                 "removeAlternativeMedias": True,
                 "removeUnusedStyles": True},
}

# at snapshot time:
fidelity = recipe.get("fidelity") or global_default or "balanced"
opts = {**SINGLEFILE_OPTIONS, **FIDELITY_PRESETS[fidelity]}
# pass `opts` to singlefile.getPageData
```

**Default: `balanced`.** It is a strict improvement for virtually every site (−76%) with no
rendering-fidelity risk, so it's the right global default. `exact` and `lean` are opt-in per host.

**Resolution order:** CLI `--fidelity` › overlay `capture.fidelity` › global `origin/origin.yaml`
`capture.fidelity` › tooling default (`balanced`). Same precedence pattern as `transport`.

**Provenance:** stamp the resolved fidelity into the capture sidecar / record provenance so each
artifact records *how* it was captured (relevant when comparing or re-capturing later).

**Wiring checklist:**
- `capture/__init__.py` — `FIDELITY_PRESETS`, resolution + merge at the `getPageData` call site.
- `capture/recipes.py` — surface `fidelity` from the merged recipe (it already deep-merges
  `origin/origin.yaml` under per-host overlays, so the global default lands for free).
- `spec-corpus.md §7.2` — document `capture.fidelity` among the capture fields.
- `scaffold.py` — mention `fidelity` in the annotated `example.com.yaml` template.
- CLI — add `--fidelity {exact,balanced,lean}` override on `capture` / `crawl`.

## Validation gate (before AllData lean re-crawl) — PASSED 2026-06-03

PNG content diagrams were confirmed preserved under lean; the one untested case was **electrical SVG
wiring schematics** (the interactive Non-OE diagrams the overlay un-lazies via the
`img[temp-src]` → `src` eval): does `removeAlternativeImages` drop a content SVG inside
`ad-repair-dynamic-content`?

**Result: PASS.** A/B on a TSB leaf carrying 4.86 MB of real content SVG:

| | exact | lean |
|---|---|---|
| File size | 17.14 MB | **6.83 MB** |
| Content region | 5.78 MB | 5.78 MB — identical |
| Content `<img src=data:svg>` diagrams | 11 | 11 |
| Content SVG bytes | 4.86 MB | 4.86 MB |

All 11 schematic figures survived lean **byte-for-byte** and the content region is identical — the
entire 10.3 MB saving came from chrome *outside* the content region. `removeAlternativeImages` drops
only *alternate* representations; a single-source inlined `<img src="data:image/svg…">` has no
alternate, so it is untouchable. (This is why lean is **content-proportional**: a real-content-heavy
page lands at 6.8 MB, not ~1 MB.) `removeAlternativeImages` **stays** in the `balanced`/`lean`
presets — no tooling change. The fallback below was therefore not needed.

- ~~If a content SVG is dropped: remove `removeAlternativeImages` from the `balanced`/`lean` presets
  (fonts + CSS alone still 11.4 MB → ~5 MB).~~ Not needed — gate passed.

## Corpus-side follow-up (Curator, after this lands)

1. Set `capture.fidelity: lean` on `schema/origin/web/my.alldata.com.yaml`.
2. Wipe the paused fat crawl — records + artifacts + the `capture/crawl-*.json` sidecar (all ~1,200
   captured-so-far pages get redone lean). The re-crawl produces **all-new record ids** — `id` is
   `blake3(snapshot bytes)`, and the tier changes those bytes, so this is a fresh id set, not an
   in-place rewrite (see gotcha #50).
3. Restart the full-vehicle crawl fresh.

## Implementation status (landed 2026-06-03)

Implemented as specified, with `balanced` confirmed as the global default (sjrahn's call).

- **`capture/__init__.py`** — `FIDELITY_PRESETS` (`exact`/`balanced`/`lean`) + `DEFAULT_FIDELITY =
  "balanced"`; `_resolve_fidelity(cli, recipe)` (precedence: CLI `--fidelity` › overlay
  `capture.fidelity` › `origin/origin.yaml` › default; unknown spelling warns and falls through) and
  `_singlefile_options(fidelity)` merged over `SINGLEFILE_OPTIONS` at the `getPageData` call.
- **Provenance** — the resolved tier is stamped into a `<meta name="corpus-fidelity">` tag in the
  snapshot `<head>`, alongside `corpus-capture-url` / `corpus-fetched-at` (bytes-recoverable). It sits
  outside any content-scoped `canonical:` region, so it does not perturb content-dedup.
- **CLI** — `--fidelity {exact,balanced,lean}` on both `corpus capture` and `corpus crawl`
  (`CaptureOptions.fidelity`; crawl threads it through `_capture_one` for a whole-site re-crawl
  without editing the overlay).
- **Docs** — `spec-corpus.md §7.2`, `impl-corpus.md §3.1`, and the `scaffold.py` / `recipes.py`
  annotated `capture:` templates.
- **Tests** — option spellings verified present in the vendored `single-file.js`; unit tests cover
  resolution precedence, the per-tier merge, the provenance stamp, and a fake-page `_snapshot_html`
  integration test proving the resolved tier's preset actually reaches `getPageData`. Suite 287/3.

**Caveat carried into gotcha #50:** "records identical across tiers" holds for the drafted *body*
(the mechanical drafter reads DOM, not fonts/CSS) but **not** for record *identity* — `id =
blake3(artifact)`, and the tiers exist to change the artifact bytes, so the same URL at two tiers is
two distinct records (different id/filename/shard). The validation gate above **passed** (2026-06-03,
PASS table) — `removeAlternativeImages` does not touch single-source content SVGs, so lean is cleared
for the AllData re-crawl.
