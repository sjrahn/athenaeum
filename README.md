# Athenaeum

A knowledge normalization and curation system: capture any artifact, normalize it into a faithful content-addressed record, and build domain expertises on top that cite their sources at span level — compendiums of information that trace back to source and feed expert agents without hallucination.

This repo — **`athenaeum/athenaeum`** — is the system's definition and driver:

- **`spec/`** — the specifications (system architecture, the corpus contract, the ledger contract, the codex contract).
- **`athenaeum.yaml`** — the member manifest: the single registry of the system's corpora, ledger, codices, and reference-dataset mirrors.
- **`tools/`** — the `athenaeum` distribution, shipping two CLIs: `ath` (the orchestrator umbrella — member sync/status against the manifest, corpus delegation) and `corpus` (the corpus pipeline: capture → ingest → draft → normalize, the functional `corpus://` URI resolver, schemas, lint, health).
- **`.claude/skills/orchestrator/`** — the resident principal-developer persona and its institutional memory.

Bootstrap on a fresh machine:

```bash
git clone https://code.example.org/athenaeum/athenaeum.git && cd athenaeum
uv tool install --editable "tools[capture,media,fingerprint]" --with cryptography
ath sync    # clones every member from athenaeum.yaml
```

The member repos live in the same Forgejo org and are cloned beneath this tree (gitignored):

| Member | Layer | Content |
|---|---|---|
| `corpus` | corpus (public hub) | world artifacts — web, PDF, video, reference databases |
| `corpus-private` | corpus (private hub) | personal artifacts — messages, documents, records |
| `ledger` | ledger | the fact substrate — concepts and claims citing the corpora as evidence |
| `codex-*` | codex | targeted compilations of ledger facts into prose deliverables |

The three data layers: a **corpus** is a content-addressed archive of immutable artifacts with faithful markdown proxies (the bytes); the **ledger** is the single fact substrate — concepts carrying evidence-backed claims, privacy as derived sensitivity (the knowledge); a **codex** is a targeting of ledger facts that compiles to prose (the expertise). Tenant isolation is a repo boundary where sharing lives — public and private corpora never mix, and the codex build's leak check walls what publishes.

`REFORGE.md`, while present, tracks the 2026-07 restructuring that gave the system this shape.
