# athenaeum

The Athenaeum system's shared tooling distribution — one Python package
shipping four libraries and two CLIs:

| Package | Surface | Contract |
|---|---|---|
| `corpus` | `corpus <subcommand>` — parse, lint, resolve, derive views, shape, and orchestrate the capture → ingest → (demand-driven) normalize pipeline | [ATH-CORPUS](../spec/corpus.md) |
| `ath` | `ath <verb>` — system verbs against the member manifest (`status`, `sync`, `corpus`, `ledger`, `codex`) | [ATH-ARCH](../spec/athenaeum.md) |
| `ledger` | `ath ledger check\|verify\|harvest\|promote\|stamp\|worklist\|regen` — the knowledge layer's deterministic surface | [ATH-LEDGER](../spec/ledger.md) |
| `codex` | `ath codex <name> scope\|notes\|build\|check` — targeting, vault generation, the certified build with the public-profile leak check | [ATH-CODEX](../spec/codex.md) |

Also bundled: the **universal** corpus schemas (`mime`, `origin`, `atom/**`,
`context/issue/**`). Each corpus repo supplies only its own records and its
own corpus-local schema extensions; the ledger and codices carry no tooling
of their own.

## Install

Both CLIs come from ONE uv tool install of this directory (editable, so a
`src/` edit is live in the installed CLIs without reinstalling):

```bash
uv tool install --reinstall --editable "tools[capture,media,fingerprint]" --with cryptography
```

Consuming repos never vendor or path-depend on this package — the CLIs
auto-discover the corpus root / member manifest by cwd.

## Dev quickstart

```bash
cd tools
uv sync --extra capture --extra media --extra office --extra fingerprint --extra tokens
uv run --no-sync python -m pytest -q      # the suite — expect all green (gotcha #2: not `uv run pytest`)
uv run --no-sync ruff check src tests     # expect clean

# Heavy backends are opt-in via extras:
#   capture (Playwright)  media (yt-dlp)  office (openpyxl/xlrd/python-docx)
#   fingerprint (imagehash/pyacoustid/simhash)  tokens  azure  s3
```

## Layout

```
tools/
├── pyproject.toml          # one distribution: packages src/{corpus,ath,ledger,codex}
├── README.md
├── src/
│   ├── corpus/             # ATH-CORPUS library + `corpus` CLI (+ schemas_default/)
│   ├── ath/                # the umbrella CLI: manifest, status/sync, delegation shims
│   ├── ledger/             # model, check, verify, harvest, promote, views, coverage
│   └── codex/              # manifest, scope, notes, build (raster + leak check + certificate)
└── tests/
```

## Conformance authority

The specs in [`../spec/`](../spec/) are the contract. Where this
implementation needs something a spec doesn't cover, the spec gets updated
first (the workspace root `CLAUDE.md` states the same law).
