"""Scaffolding — `corpus init` materializes the minimal corpus seam.

A new corpus repo contains `records/` + `schema/origin/origin.yaml` +
`schema/composite/<ns>/` (plus the untracked `artifacts/` `capture/` `cache/`
`export/`). Universal `mime` and `atom` schemas come from the package's bundled
defaults; `origin` and `composite` are **per-corpus concerns** (sources of
retrieval and classification axes are corpus-specific decisions) so the scaffold
seeds the universal origin overlay locally.

This module exports:
- `scaffold(target, *, namespace, force=False)` — create the tree.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_GITIGNORE = """\
# Untracked corpus state — regenerable from records/ + schema/. Root-anchored
# (leading /) so the `capture/` staging dir is ignored without also ignoring any
# same-named tracked dir nested elsewhere under schema/.
/artifacts/
/capture/
/cache/
/export/

# Editor / OS scratch
.DS_Store
*.swp
"""

_UNIVERSAL_ORIGIN_YAML = """\
# Universal origin-block fields — applied to every <!--origin--> block, regardless of
# whether the opener names a specific origin schema. Bare `<!--origin-->` uses just
# these fields; qualified forms (`<!--origin <id>-->`) layer additional fields from
# per-id yamls in this directory (`schema/origin/<id>.yaml`).
#
# Origin is a per-corpus concern (sources of retrieval are corpus-specific), so this
# file is corpus-local — the `ath-corpus` package does NOT bundle a universal origin.
# Extend or constrain as your corpus requires.
#
# See spec-corpus.md §7.2.

description: |
  Universal fields every origin block carries.

extended_fields:
  uri:
    type: string_or_list
    required: true
    semantic_type: uri
    description: |
      One or more URIs from which the artifact's bytes are retrievable for this
      origin. String when there's one URI; YAML list when canonical + shortlinks +
      post-redirect final URLs collapse to a single logical origin. Aggregated into
      the `uris` derived view (§9.3).
  snapshot:
    type: string
    required: true
    semantic_type: timestamp
    description: |
      ISO-8601 timestamp of when this origin was observed. For an origin block
      emitted at ingest, this is the capture timestamp; for re-captures, the most
      recent observation. Aggregated into the `timeline` derived view (§9.4).
"""

_README_TEMPLATE = """\
# {name}

A corpus repository — content-addressed records under `records/`, origin overlays
under `schema/origin/`, classification schemas under `schema/composite/<namespace>/`.
Universal `mime` / `atom` / `composite/issue` schemas resolve from the
[`ath-corpus`][] package's bundled defaults; `origin` and `composite` are
per-corpus concerns so they live here.

[`ath-corpus`]: ../athenaeum/tools/corpus

## Layout

```
{name}/
├── records/              # TRACKED — record markdown files (sharded by id[:2])
├── schema/
│   ├── origin/
│   │   ├── origin.yaml   # Universal origin fields (uri/snapshot) — corpus owns this
│   │   └── <host>.yaml   # Per-host overlays: origin fields + optional `capture:` config
│   └── composite/
│       └── {namespace}/  # THIS corpus's classification namespace(s)
├── capturers/            # TRACKED — optional corpus-local capturer code (example.py)
├── artifacts/            # UNTRACKED — binary store
├── capture/              # UNTRACKED — capture staging
├── cache/                # UNTRACKED — resolver output cache
└── export/               # UNTRACKED — portable export bundles
```

## Common commands

```bash
corpus find             # list records
corpus show <hash>      # record summary
corpus lint <hash>      # conformance check
corpus diagnose <hash>  # snapshot + classification candidates
```

See `ath-corpus`'s README for the full surface.
"""

_EXAMPLE_ORIGIN_OVERLAY_YAML = """\
# Example per-host origin overlay. Copy to schema/origin/<host>.yaml, uncomment, and
# edit. Matched against an origin's host (apex<->www aware); corpus-local first. One
# host-keyed file carries BOTH the origin-block field overlays (extended_fields, for
# record validation) AND, optionally, a `capture:` section (read only at capture time)
# describing how to fetch this source.
#
# applies_to:
#   host_pattern: example.com        # or host_patterns: [a, b]; "*" = catch-all
#   include_subdomains: true
#
# # Origin-block extended fields beyond the universal uri:/snapshot:, if this source
# # needs any. Validated on every <!--origin--> block for matching records.
# extended_fields: {}
#
# # Capture-time behavior — surface ALL displayable media (lazy-load, carousels, tabs,
# # accordions) before the self-contained snapshot. Absent, the browser capturer's
# # built-in defaults apply (headless + scroll/expand). Global defaults can go on the
# # universal origin.yaml `capture:`; per-host `capture:` here overrides.
# capture:
#   capturer: browser                # packaged (browser | video) or a corpus-local name
#   transport: headless              # headless | headed | cdp  (headed/cdp need a display
#                                    # or a running Chrome -- see `corpus capture --transport`)
#   interactions:
#     - scroll: full                   # hydrate lazy-loaded / below-the-fold media
#     - click: {selector: "button[aria-label='Next']", repeat: 12, delay_ms: 500}
#     - expand: all                    # open <details> + aria-expanded accordions/tabs
#     # `eval` is the escape hatch for site-specific JS. Two common high-fidelity uses:
#     #  (a) fetch+inject an AJAX-on-click tab/panel (same-origin fetch -> innerHTML).
#     #  (b) promote a click-to-zoom HIGH-RES image into `src` so it gets inlined+embedded
#     #      -- for data-* zoom URLs SingleFile doesn't inline (WooCommerce
#     #      data-large_image, magic/cloud-zoom data-zoom-image, etc.). A plain higher-res
#     #      `srcset` is already embedded automatically by the drafter; this is only for
#     #      the data-* case.
#     - eval: |
#         document.querySelectorAll('img[data-large_image], img[data-zoom-image]')
#           .forEach((i) => i.setAttribute('src',
#             i.getAttribute('data-large_image') || i.getAttribute('data-zoom-image')));
#   viewport: 1280x900
"""

_EXAMPLE_CAPTURER_PY = '''\
"""Corpus-local capturer template (CODE replacement tier).

Drop a single-file module in this directory and decorate a function with
`@register("<name>")`; a capture recipe's `capturer: <name>` then routes matching
origins to it. The `ath-corpus` package imports this directory ONLY when a recipe
names a capturer it doesn't ship -- and it imports (executes) your code, so treat
this as your corpus's own trusted code.

Uncomment to use.
"""

# from corpus.capture import CaptureResult, register
#
#
# @register("example")
# def capture_example(url, *, corpus_root, capture_dir, opts, recipe):
#     """Retrieve `url` however you like, write the bytes under `capture_dir`, and
#     return a CaptureResult pointing at the file. Raise
#     `corpus.capture.CaptureError` on failure. `recipe` is the matched recipe dict."""
#     out = capture_dir / "example.bin"
#     out.write_bytes(b"...")  # your custom retrieval here
#     return CaptureResult(capture_path=out, used_video=False, issues=[])
'''


def scaffold(target: Path, *, namespace: str, force: bool = False) -> Path:
    """Create the minimal corpus seam at `target`.

    Writes:
      - records/ (empty)
      - schema/composite/<namespace>/<namespace>.yaml (stub interpretive overlay)
      - .gitignore (untracked dirs)
      - README.md (overview)

    Does NOT write universal mime/origin/atom/composite-issue schemas — those resolve
    from the package via the schema-fallback loader. Does NOT create the untracked
    artifacts/capture/cache/export dirs (they materialize when first used).

    `namespace` is the corpus's primary composite namespace id (e.g. `document`,
    `recipe`). At least one composite namespace is required because the
    `schema/composite/` dir is the per-corpus seam.

    Returns the resolved target path. Raises FileExistsError if records/ or
    schema/ already exists and force=False.
    """
    target = Path(target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    records_dir = target / "records"
    schema_dir = target / "schema"
    if not force:
        if records_dir.exists() and any(records_dir.iterdir()):
            raise FileExistsError(f"{records_dir} is not empty (pass force=True to override)")
        if schema_dir.exists() and any(schema_dir.iterdir()):
            raise FileExistsError(f"{schema_dir} is not empty (pass force=True to override)")

    records_dir.mkdir(exist_ok=True)
    schema_dir.mkdir(exist_ok=True)

    # Universal origin overlay — corpus-supplied, not packaged. Every corpus
    # carries the baseline uri/snapshot field declarations; corpora may extend
    # them or add per-host overlays alongside.
    origin_dir = schema_dir / "origin"
    origin_dir.mkdir(parents=True, exist_ok=True)
    origin_yaml = origin_dir / "origin.yaml"
    if not origin_yaml.exists() or force:
        origin_yaml.write_text(_UNIVERSAL_ORIGIN_YAML, encoding="utf-8")

    # Composite namespace stub — at least one per-corpus axis (this is the
    # primary per-corpus reuse seam).
    ns_dir = schema_dir / "composite" / namespace
    ns_dir.mkdir(parents=True, exist_ok=True)
    ns_yaml = ns_dir / f"{namespace}.yaml"
    if not ns_yaml.exists() or force:
        ns_yaml.write_text(
            yaml.safe_dump(
                {
                    "kind": "interpretive",
                    "description": (
                        f"{namespace} — stub composite namespace. Author cues, "
                        f"extended_fields, and (optionally) subclasses under this dir."
                    ),
                    "applies_at": ["record"],
                    "applies_to": {
                        "cues": {"body_contains": []},
                        "content_types": [],
                    },
                    "extended_fields": {},
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

    # Pluggable-capture seam (both tracked, both optional): per-origin capture config
    # lives under a `capture:` section on a per-host origin overlay (schema/origin/
    # <host>.yaml), and corpus-local capturer code under capturers/. Seeded with
    # commented examples that are inert until edited.
    example_overlay = origin_dir / "example.com.yaml"
    if not example_overlay.exists() or force:
        example_overlay.write_text(_EXAMPLE_ORIGIN_OVERLAY_YAML, encoding="utf-8")

    capturers_dir = target / "capturers"
    capturers_dir.mkdir(parents=True, exist_ok=True)
    example_capturer = capturers_dir / "example.py"
    if not example_capturer.exists() or force:
        example_capturer.write_text(_EXAMPLE_CAPTURER_PY, encoding="utf-8")

    gi = target / ".gitignore"
    if not gi.exists() or force:
        gi.write_text(_GITIGNORE, encoding="utf-8")

    readme = target / "README.md"
    if not readme.exists() or force:
        readme.write_text(
            _README_TEMPLATE.format(name=target.name, namespace=namespace),
            encoding="utf-8",
        )

    return target
