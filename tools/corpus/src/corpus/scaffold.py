"""Scaffolding — `corpus init` materializes the minimal corpus seam.

Per the plan: a new corpus repo contains only `records/` + `schema/composite/<ns>/`
(plus the untracked `artifacts/` `capture/` `cache/` `export/`). Universal mime /
origin / atom / composite/issue schemas come from the package's bundled defaults.

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

_README_TEMPLATE = """\
# {name}

A corpus repository — content-addressed records under `records/`, classification
schemas under `schema/composite/<namespace>/`. Universal `mime` / `origin` /
`atom` / `composite/issue` schemas resolve from the [`ath-corpus`][] package's
bundled defaults.

[`ath-corpus`]: ../athenaeum/tools/corpus

## Layout

```
{name}/
├── records/              # TRACKED — record markdown files (sharded by id[:2])
├── schema/
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

    # Composite namespace stub — required so find_corpus_root sees schema/ as
    # populated and the loader has at least one corpus-supplied overlay.
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
