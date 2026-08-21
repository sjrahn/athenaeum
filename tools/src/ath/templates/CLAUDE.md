# {name} — Athenaeum instance

Knowledge system: **corpus** (faithful bytes, `corpus/`) → **ledger**
(evidence-backed claims, `ledger/`). Together they are the system's **end
product**, consumed from outside under the consumption contract
(spec/ledger.md §12). This repository is the **instance** — the system
instantiated (spec Part I §2). The specification and shared tooling live in
the Athenaeum distribution; `ath` and `corpus` on PATH point here by walking
up for `athenaeum.yaml`.

**The specification is law** — one spec, four parts, one version, in the
distribution's `spec/`: `athenaeum.md` (I, architecture), `corpus.md` (II),
`ledger.md` (III), `custody.md` (IV). Code conforms to spec; when code needs
something the spec doesn't cover, the spec changes first. External captures,
deletions, and normative spec changes are owner-gated.

**Boot order for a working session**: this file, then this instance's own
notes — `corpus/runbooks/deployment.md` (backlog location, known-red
baselines, machine specifics) and the runbooks beside it. Ledger process docs
live in `ledger/docs/`.

## Operating principles

- **Deferral**: records are usable from ingest; normalization runs only under
  demand (queue = demand, never backlog — corpus.md §8.5). Never propose
  pre-emptive forming sweeps or standing drain loops. The ledger cites
  deferred surfaces at reduced strength (ledger.md §6.3); citations are
  themselves the demand signal.
- **Tenancy is derived, per record**: origin overlays declare `tenancy: {tier}`
  — a tier from this instance's declared set (`public`/`private` reserved,
  plus whatever `tenancy.tiers` in `athenaeum.yaml` adds), fail closed to the
  `visibility:` floor (itself `public`, `private`, or a declared tier);
  publication filters on derived sensitivity per audience grant, fail closed —
  the consumption contract is the wall (ledger.md §6.4, §12).
- **Thin operation**: no resident skill, no logbook. Memory = the spec +
  tracker + git history + the runbooks here.

## Gates (run before reporting any content change done)

    ath ledger check && ath ledger verify
    corpus lint <id>                        # per touched record

Known-red baselines are deployment state — check
`corpus/runbooks/deployment.md` before treating a red gate as a regression.

## Surfaces

- `ath` — status, `ath issue` (tracker read + snapshot sync; writes go through
  the forge's own CLI), `ath ledger …` (check/verify/harvest/merge/…),
  `ath ref …` (reference datasets).
- `corpus` — capture → ingest → (deferred) normalize;
  `inspect`/`diagnose`/`body`/`resolve`/`locate`.
- Dispatchable workers in `.claude/agents/`: `normalizer` (form passes),
  `ledger-scribe` (interpretive authoring), `overlay-author` (new web hosts).
  They never run git; review and commit their work here.
- Backlog: the tracker registered in `athenaeum.yaml` (`tracker:`); its
  committed snapshot lives where `tracker.snapshot` points (regenerate with
  `ath issue sync`).
