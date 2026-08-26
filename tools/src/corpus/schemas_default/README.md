# Packaged schema defaults

Per spec Part II §3/§7. This is the **packaged** half of the schema tree — the
format-universal contracts every instance gets for free. An instance's own
`schema/` dir layers on top (`tools/src/corpus/schemas.py` is the resolver; read
its module docstring for the exact merge rules). Nothing here is instance-specific:
no publisher tactics, no per-corpus classification, no origin overlays.

## Layout

```
schemas_default/
├── mime/      media-type schemas   — <!--artifact <mime-type>--> (format-universal)
├── atom/      atomic-overlay schemas — segment-scope content classification
├── form/      structural-shape contracts — bound on a section opener
└── context/   annotation-zone overlays — the <!--context ...--> block
```

`origin/` and `composite/` are spec-reserved namespaces (§3) that are deliberately
**not** packaged here: `origin/` is per-corpus publisher knowledge (see below);
`composite/` was the pre-ledger classification umbrella, retired in ATH-CORPUS 2.0
(§7.4) — what content *means* is a ledger claim now, not a record assertion — and
stays reserved-but-empty so the 1.0 layout is never repurposed.

## `mime/` — 37 schemas

`mime/<axis>/<axis>.yaml` (axis-common, e.g. `mime/image/image.yaml`) and
`mime/<axis>/<axis>_<subtype>.yaml` (specific, e.g. `mime/image/image_png.yaml`),
layered under the universal `mime/mime.yaml`. A schema's identity is its
`applies_to.content_types` list (the IANA MIME strings it claims), not a declared
id field — `schemas.py` derives the schema id (`image/image_png`) from the path.
Declares `mode`/`disposition`, `artifact_kind`, `address_scheme`, `extended_fields`,
and `normalization.guidance` for the deterministic drafter and the normalizer.

## `atom/` — 25 schemas

`atom/<atom>/<atom>.yaml` (common) + `atom/<atom>/<atom>_<id>.yaml` (specific),
for the four content atoms (`text`, `image`, `audio`, `video`). Each file declares
its id explicitly as `class_id` (e.g. `class_id: text/data-table`) — that's the
form guidance names it by (`` `text/data-table` ``). Only `text/*` overlays may
declare `enables_lossless: true`; the others are descriptive only.

## `form/` — 14 contracts

Flat `form/<id>.yaml`, id declared as `form_id`, with an optional universal
`form/form.yaml` layering underneath (none currently ships). These files ARE the
registry — the spec deliberately carries no separate roster (§7.8) — so `corpus
schemas`'s listing of this directory is the only membership list (`corpus
overlay` resolves *origin* overlays only, not forms). A form names a *shape*
(`document`, `article`, `conversation`, `receipt`, …),
never a subject; `terminal: true` marks a contract that prescribes the *absence*
of a stored rendering (`manifest`, `passthrough`) rather than a shape.

## `context/` — 24 overlays, 3 namespaces (`issue`, `reference`, `sweep`)

`context/<namespace>/<namespace>.yaml` (the namespace's universal — the ONLY file
for a single-id namespace like `sweep`) plus `context/<namespace>/<id>.yaml` (and
nested `<id>/<subtype>.yaml`) for the rest. No file declares an explicit id key;
`schemas.py`'s `class_id` convention is namespace-relative and path-derived
(`context/issue/partial-content/paywall.yaml` → `issue/partial-content/paywall`).
`issue/` backs the `<!--issue-->` annotation; `reference` and `sweep` are the other
two `<!--context <namespace>[/<id>]-->` namespaces currently declared.

## Packaged vs. instance — the resolution walk

Every reader in `schemas.py` composes two sources per file: **corpus-local first,
packaged second** (`_sources`), with **whole-file wins** at each layer rung (a
corpus-local override replaces its packaged counterpart entirely, so a corpus can
also *delete* a packaged field by restating the file without it) and **deep-merge
across rungs** (universal → axis/atom-common → subtype/id, most-specific wins).
An instance's `schema/` dir mirrors this same four-namespace-plus-origin layout;
nothing about the packaged tree's shape changes when an instance adds to it.

## Origin overlays — why they live outside this package

`origin/<scheme>/<id>.yaml` (host-pattern-matched web overlays under `web/`, other
discovery mechanisms under `otherwise/` or a producer's own namespace) declares
**publisher** tactics: cookie banners, footer templates, CMS quirks, per-source
normalization guidance. That knowledge is a property of *this corpus's* sources,
not of the format — so it is never packaged, and `corpus init` seeds only the
universal `origin/origin.yaml` plus one example. Add a host overlay when a
publisher's quirks are **repeatedly** tripping the normalizer across multiple
records of that source — never preemptively, before anything has been drafted
from it.

## Keeping guidance honest

`corpus schema-lint` validates this tree's own prose against itself: every
backticked field/overlay reference in a `description` or `normalization.guidance`
must resolve against the tree's *actual* declared vocabulary (derived at run time,
never a hardcoded list). Run it after any schema edit — a renamed field or a
retired overlay it still names is exactly the kind of defect no record-level check
can see.
