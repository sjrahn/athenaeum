# Perceptual Fingerprinting → Schema-Driven Opt-In

**Status:** implemented in `tools/corpus` (2026-06-03), and extended in review. The
record-contract is in `spec-corpus.md §7.7`; draft-time mechanics in `impl-corpus.md §3.1`.
This doc is retained as the design rationale. See "Implementation status" at the end.
**Author:** Curator (corpus repo), 2026-06-03
**Owner implemented:** athenaeum tooling

## Why

Perceptual fingerprints (text simhash, image pHash, audio chromaprint) are a **near-duplicate /
similarity-search** concern — a codex-layer or maintenance-tool signal, not part of a faithful
first-pass draft. Today every text drafter computes a simhash **unconditionally** and writes it to
each segment's `perceptual:` header.

**Desired behaviour:** perceptual hashing is **not computed by default**, and the choice is a
**schema-layer knob**, not one global flag:

- each **mime schema** sets the per-file-type **default** (the general case for that file type);
- a **composite classification** may **override** it for records of that class.

> Example (the motivating case): `application/pdf` defaults the fingerprint **off**; the
> `composite/document` classification turns it **on** — so a PDF classified as a document gets a
> fingerprint, a bare PDF does not.

All the existing plumbing **stays** (the `corpus.fingerprint` package, the segment/record
`perceptual:` field + parse/emit, the lint rules); only the **automatic computation** becomes
opt-in, gated by the resolved schema knob.

## Current behaviour (what to gate)

Text fingerprint computed inside each drafter, passed straight to `Segment(perceptual=…)`:

- `draft/html.py:329` — `perceptual=text_fp.fingerprint_text(cleaned_html)`  ← the one hitting AllData
- `draft/xls.py:134`, `draft/xlsx.py:194`, `draft/docx.py:175` and `:185`

via `corpus.fingerprint.text.fingerprint_text()`. (`fingerprint/{image,audio}.py` exist but aren't
wired into any drafter yet.) The drafter is invoked from `_cli/draft.py:79-85`, which already loads
the mime schema (`mt_schema`).

## Design — the `fingerprint` knob

**Field:** `fingerprint: <bool>` (whether to compute the perceptual hash; the computed value still
lands in the existing `perceptual:` field). Absent ⇒ **off**.

**Declared on:**
- **mime schema** (`schemas_default/mime/<…>.yaml`; corpus-local `schema/mime/` overrides) — the
  per-file-type default. Unset = off, so "not computed by default" holds with **zero** schema edits;
  a type that wants it on by default sets `fingerprint: true`.
- **composite classification schema** (`schema/composite/<ns>[/<sub>].yaml`) — an optional override
  for records carrying that classification.

**Resolution — most-specific wins — at the point of computation:**

```
  CLI  --fingerprint / --no-fingerprint        (explicit; unset = schema-resolved)
   ›  composite classification `fingerprint`    (most-specific: assigned classify-block › subclass › namespace)
   ›  mime schema `fingerprint`
   ›  false
```

A helper — e.g. `schemas.resolve_fingerprint(corpus_root, media_type, post, cli_override) -> bool` —
implements this using `load_mime_schema`, the record's `iter_classify_blocks`, and
`mechanical_classifications_for(media_type)`.

### Lifecycle / timing (important)

The fingerprint is computed at **draft**. So resolution at draft sees only the classifications
**knowable then**: the mime default, **mechanical** composites
(`mechanical_classifications_for` — deterministic from the MIME), and any `<!--classify-->` blocks
already on the record. **Interpretive** composites — including today's `composite/document`
(`kind: interpretive`, `applies_to.content_types: []`, assigned by the not-yet-built normalizer) —
are added **after** draft, so their override takes effect on a subsequent **re-fingerprint**
(`re-stub` → `draft`, or a future normalize/fingerprint pass) once the classify block is present.
This is the normal interpretive-layer caveat: mechanical knobs apply on the first draft; interpretive
ones apply once the record is classified. State it plainly so "the document overlay turns it on" is
understood to fire post-classification, not at the initial stub→draft.

## Implementation checklist

- **Drafter interface** (`draft/__init__.py` docstring §Interface): add `fingerprint: bool = False`
  to the documented kwargs; every registered drafter accepts it (pdf/image/video/audio ignore it).
- **Text drafters** (html, xls, xlsx, docx): `perceptual = text_fp.fingerprint_text(body) if fingerprint else None`.
- **Draft dispatch** (`_cli/draft.py:run()`): `fingerprint = schemas.resolve_fingerprint(corpus_root, media_type, post, args.fingerprint)`; pass `fingerprint=` into the `drafter(...)` call. Add a tri-state `--fingerprint` / `--no-fingerprint` in `configure()` (default unset → schema-resolved).
- **Resolver** `schemas.resolve_fingerprint(...)` per the precedence above.
- **Mime schemas**: no edits required for "off by default" (absent = off). Optionally set `fingerprint: true` on any type that should default on (none today).
- **Keep (do not remove):** `corpus/fingerprint/`; `Segment.perceptual` emit (`segments.py:82,96-97,432-460`); the `recordbuild.py` seg DSL `perceptual=` key; lint `_PERCEPTUAL_RE` (`lint.py:77`) + `_rule_perceptual_format` (`:174`) + `_rule_segment_perceptual_format` (`:377`).

## Validation

- Draft a PDF/HTML with no `fingerprint` anywhere → no `perceptual:` on segments; lint clean.
- A mime schema (or an applicable mechanical composite, or a pre-assigned classify block) with
  `fingerprint: true` → segments carry `perceptual: simhash:<hex>`; lint clean.
- `--no-fingerprint` forces off even when a schema enables; `--fingerprint` forces on.
- A record with an interpretive `composite/document` classify block + `composite/document`
  `fingerprint: true` → re-draft produces the fingerprint (timing case).
- Pre-existing records carrying `perceptual:` still parse + lint (plumbing intact).

## Corpus-side follow-up (Curator)

- Leave mime defaults off (absent) — perceptual isn't used yet, so the AllData lean re-crawl drafts
  carry no `perceptual:` by default. The current 50 sample drafts re-draft clean.
- If/when document-class fingerprinting is wanted: set `fingerprint: true` on the corpus's
  `schema/composite/document/document.yaml` (fires post-classification, per the lifecycle note).

## Implementation status (landed 2026-06-03)

Implemented as proposed (default off, schema-gated, `schemas.resolve_fingerprint` precedence
CLI › composite › mime › False, lint untouched, plumbing kept), and **extended** in review across
a four-commit arc:

- **The knob selects the algorithm, not just on/off.** `fingerprint:` accepts `false`/`true`/an
  algorithm name/a list (a list → a list-valued `perceptual:`). A `fingerprint/__init__.py` registry
  (`DEFAULT_ALGO_BY_ATOM`, `algos_for_atom`, `text_fingerprints`/`image_fingerprints`) mirrors
  `content_hash._STRATEGIES`. The drafter resolves per-atom algorithms from the knob.
- **Image fingerprinting is wired** (the proposal noted it was unwired): the image drafter now emits
  `perceptual:` on its image atom, with `phash`/`dhash`/`ahash`/`whash` selectable via the knob.
- **One construction path.** Drafters were unified onto the `recordbuild.Build` ops (the
  decompose/compile constituent model) instead of `segments.emit`, so draft/redraft/decompose/compile/
  normalize all construct records identically (the normalization substrate; impl-corpus §3.1).
- **Deterministic bulk recompile** restores the CarbonAI `assemble --force/--dry-run` capability:
  `corpus redraft [--mime/--host/--status] [--dry-run]` re-derives records from their retained
  artifacts, idempotently (unchanged → byte-identical → no write), so `git diff records/` surfaces
  exactly what a knob flip affects. Distinct from `corpus compile` (manifest reassembly).

**The CLI is on/off only** (`corpus draft --fingerprint` / `--no-fingerprint`; algorithm selection is
schema-only). **Lifecycle caveat confirmed and stated**: at draft only the mime default, mechanical
composites, and already-present classify blocks resolve — the interpretive `composite/document`
override fires on a later `corpus redraft` once the normalizer assigns its classify block (the
normalizer is not built yet). Records/specs: `spec-corpus.md §7.7`, `impl-corpus.md §3.1`. Suite
305/3; the corpus-side follow-up above is the Curator's.
