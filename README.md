# Athenaeum

A knowledge normalization and curation system: capture any artifact, normalize it into a faithful content-addressed record, and build domain expertises on top that cite their sources at span level — compendiums of information that trace back to source and feed expert agents without hallucination.

This repo — **`athenaeum/athenaeum`** — is the system's definition and driver:

- **`spec/`** — the specifications (system architecture, the corpus contract, the codex contract).
- **`tools/corpus/`** — `ath-corpus`, the corpus library and `corpus` CLI: capture → ingest → draft → normalize pipeline, functional `corpus://` URI resolver, schema system, lint, health.
- **`.claude/skills/orchestrator/`** — the resident principal-developer persona and its institutional memory.

The member repos live in the same Forgejo org and are cloned beneath this tree (gitignored):

| Member | Layer | Content |
|---|---|---|
| `corpus` | corpus (public hub) | world artifacts — web, PDF, video, reference databases |
| `corpus-private` | corpus (private hub) | personal artifacts — messages, documents, records |
| `codex-*` | codex | domain fact graphs citing the corpora as evidence |

The two layers: a **corpus** is a content-addressed archive of immutable artifacts with faithful markdown proxies (the truth layer); a **codex** is a domain repo whose facts carry claim-level evidence chains into the corpora (the knowledge layer). Tenant isolation is a repo boundary — public and private corpora never mix.

`REFORGE.md`, while present, tracks the 2026-07 restructuring that gave the system this shape.
