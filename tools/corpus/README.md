# ath-corpus

Corpus tooling for [ATH-CORPUS v1.0](../../spec-corpus.md) — parse, lint, draft, resolve,
derive views, and orchestrate the capture → ingest → draft → normalize pipeline that produces
spec-conformant corpus records.

Provides:

- An importable Python library (`import corpus`).
- A CLI (`corpus <subcommand>`).
- Bundled **universal** schemas (`mime`, `origin/origin`, `atom/**`, `composite/issue/**`).

Each consuming corpus repo supplies only its **own** records and its **own**
`composite/<namespace>/` classification + issue schemas.

## Status

In active development. Phase 1 (core model + schema loader + derived views + lint + edit loop)
underway. See [the plan](../../../.claude/plans/what-i-d-like-to-crispy-turtle.md) and the
[athenaeum skill logbook](../../.claude/skills/athenaeum/references/logbook.md).

## Install

Three forms — pick one per your situation:

```toml
# Editable path (example-org monorepo-adjacent checkout, recommended for dev)
[project]
dependencies = ["ath-corpus"]
[tool.uv.sources]
ath-corpus = { path = "../athenaeum/tools/corpus", editable = true }

# Git subdirectory (CI / pinned to a revision)
[project]
dependencies = [
    "ath-corpus @ git+https://code.example.org/example-org/athenaeum.git@<rev>#subdirectory=tools/corpus",
]

# Built wheel (release; built via `uv build` and published to Forgejo's package registry)
[project]
dependencies = ["ath-corpus>=0.1"]
```

## Dev quickstart

```bash
cd tools/corpus
uv sync                                # install base + dev tools
uv run pytest                          # run the test suite
uv run corpus --help                   # CLI dispatcher

# Heavy backends are opt-in via extras:
uv sync --extra capture --extra media  # Playwright + yt-dlp
uv sync --extra office                 # openpyxl + xlrd + python-docx
uv sync --extra fingerprint            # imagehash + pyacoustid + simhash
uv sync --extra azure                  # azure-storage-blob + azure-identity
uv sync --extra s3                     # boto3
```

## Layout

```
tools/corpus/
├── pyproject.toml
├── README.md
├── src/corpus/
│   ├── ...                 # core library
│   ├── schemas_default/    # BUNDLED universal schemas (mime/origin/atom/composite/issue)
│   └── _cli/               # unified `corpus <subcommand>` dispatcher
└── tests/
```

## Conformance authority

[`spec-corpus.md`](../../spec-corpus.md) (ATH-CORPUS v1.0) is the contract. Where this
implementation needs something the spec doesn't cover, the spec gets updated first.

The reference port source is `LuklaCloud/Corpus` (the "CarbonAi" corpus). Where the reference
diverges from our spec — chiefly embed-zone placement, issue block shape, origin schema
layout — **our spec wins**.
