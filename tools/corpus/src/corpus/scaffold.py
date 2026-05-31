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
# Untracked corpus state — regenerable from records/ + schema/.
artifacts/
capture/
cache/
export/

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
│   │   └── <host>.yaml   # Per-host overlays as you add sources
│   └── composite/
│       └── {namespace}/  # THIS corpus's classification namespace(s)
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
