# athenaeum

The Athenaeum system's shared tooling distribution — one Python package
shipping three libraries and two CLIs:

| Package | Surface | Contract |
|---|---|---|
| `corpus` | `corpus <subcommand>` — parse, lint, resolve, derive views, shape, and orchestrate the capture → ingest → (demand-driven) normalize pipeline | [ATH Part II](../spec/corpus.md) |
| `ath` | `ath <verb>` — instance verbs against the instance config (`init`, `status`, `issue`, `corpus`, `ledger`, `ref`) | [ATH Part I](../spec/athenaeum.md) |
| `ledger` | `ath ledger check\|verify\|harvest\|promote\|stamp\|worklist\|scope\|regen` — the knowledge layer's deterministic surface | [ATH Part III](../spec/ledger.md) |

Also bundled: the **universal** corpus schemas (`mime`, `origin`, `atom/**`,
`context/issue/**`). Each instance supplies only its own records and its
own corpus-local schema extensions; the ledger carries no tooling of its own.

Consumers of the system's product use this distribution **as a library**
(ATH Part I §5): the codex kit — `~/workspaces/codices/tools`, with its own
`codex` CLI and the ATH-CODEX contract — is the reference consumer. The
distribution itself carries no consumer tooling (v15).

## Install

Both CLIs come from ONE uv tool install of this directory (editable, so a
`src/` edit is live in the installed CLIs without reinstalling):

```bash
uv tool install --reinstall --editable "tools[capture,media,fingerprint]" --with cryptography
```

Consuming repos never vendor or path-depend on this package — the CLIs
auto-discover the corpus root / instance config by cwd ($ATHENAEUM_ROOT overrides).

The editable install makes `src/` edits live, but NOT dependency changes: when an
extra gains a package (v41 added `pillow-heif` to `media` — without it a HEIC
member cannot be decoded and `reattest` skips the record), every deployment
re-runs the `uv tool install --reinstall …` line above to pick it up.

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
├── pyproject.toml          # one distribution: packages src/{corpus,ath,ledger,refdata}
├── README.md
├── src/
│   ├── corpus/             # the corpus library + `corpus` CLI (+ schemas_default/)
│   ├── ath/                # the umbrella CLI: instance config, init/status, delegation shims
│   └── ledger/             # model, check, verify, harvest, promote, views, coverage
└── tests/
```

## Conformance authority

The specification in [`../spec/`](../spec/) — one document, four parts, one
version — is the contract. Where this implementation needs something the spec
doesn't cover, the spec gets updated first (the repo root `CLAUDE.md` states
the same law).
