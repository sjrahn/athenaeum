# testdata/ — exemplar test instance

A scratch Athenaeum instance seeded with one artifact per interesting
mime/shape (multi-track media, mbox, zip envelopes, PDF, HTML, images,
vCard, JSON, single-track audio, message/rfc822 — see `exemplars.yaml` for
the full list and per-shape notes) for spec + tooling regression testing
against real byte shapes. Most come from a private source instance; a few
shapes have no real-artifact counterpart small enough to check in and are
generated instead (see "The synthetic tier" below).

Tracked here: this README, `exemplars.yaml` (the manifest — blake3 + mime +
shape + a neutral technical note, no personal content), `seed.ts` (the
seeder), and `synthetic/` (see below). **`instance/` is never tracked** — it
holds real (if mostly tiny) private artifact bytes and is gitignored at the
repo root (`/testdata/instance/`).

### The synthetic tier

A few shapes (single-track audio/mp4, message/rfc822 with attachments,
image/heic) had no suitably-small real artifact in the source instance to
pull an exemplar from. For those, `testdata/synthetic/` holds *generated*
fixtures with no private content — `gen.py` produces them (ffmpeg for the
audio, hand-assembled stdlib `email` bytes for the message, `heif-enc` for
the still image) — whose bytes are committed directly to this public repo,
manifest entries pointing at them with `source: synthetic` and a `file:`
path. The committed bytes, not a fresh run of `gen.py`, are what the
manifest's blake3 pins: an encoder's output drifts across tool versions even
for identical input (see spec/CHANGELOG.md's v32 entry, born from exactly
this problem for real media), so pinning a freshly-generated hash would make
the manifest non-reproducible from one machine or ffmpeg/libheif version to
the next. `gen.py` exists to regenerate or extend the set later, documenting
provenance (which encoder, which invocation) — it is not run as part of
`seed.ts`.

`synthetic-image.heic` is generated and committed but has **no manifest
entry**: `corpus ingest` currently has no mime schema/drafter for
image/heic (spec/corpus.md specs it as its own manifest shape —
`item=<id>` image items — not yet implemented; see `exemplars.yaml`'s
comment on the shape). The bytes are ready for whenever that lands.

### The v39 ontology exemplars

This library is otherwise strictly mime-record-shaped — `exemplars.yaml` has
no ledger-fact axis at all. The v39 ontology layer (spec/ledger.md §15)
needs one anyway, so `seed.ts`'s `seed_v39_ontology_exemplars` seeds it
straight into `instance/ledger/` after the manifest pass: a domain concept
(`facts/continuity/bsg-reimagined.json` — an `ontology:` block minting one
domain type, `commitment: "conditional"`), a domain-minted member fact
(`facts/vessel/galactica.json`) carrying both an ordinary claim and a
presence claim (§5.5), and the one evidence record they cite, hand-authored
directly as a corpus record (a fixed, patterned id — `"39" * 32` — never a
real blake3, mirroring the ledger test suite's own `H1`/`H2`/… fixtures).
Entirely synthetic — a fictional TV franchise — so it needs no `--from`
source and commits no real bytes; only the seeding code lives here,
tracked, same as every other exemplar. It rehearses `check`/`verify`/
`regen`/`export --gate` over itself as its own regression check, and writes
the export projection to `instance/ledger/.cache/v39-export-sample.ttl` —
gitignored with the rest of `instance/`, a write-side probe rather than a
tracked fixture.

## Reseeding

```
ath init testdata/instance --name athenaeum-testdata   # once, if instance/ is missing
bun testdata/seed.ts --from /path/to/source/instance
# or: ATHENAEUM_ROOT=/path/to/source/instance bun testdata/seed.ts
```

Idempotent — an entry whose record already exists in `instance/` is skipped,
so re-running after adding a manifest entry only seeds what's new. Most
entries copy artifact bytes straight in and `corpus ingest` them; a few small
images exist in the source corpus only as promoted HTML-embed members with
no standalone bytes of their own (see `exemplars.yaml`'s header comment) —
for those, `seed.ts` ingests the named container instead and runs `corpus
promote` inside `instance/` to re-mint the same content-addressed leaf.

Sanity-check after seeding:

```
bun ath/src/main.ts --root testdata/instance lint --all
```

### The successor regression set (`ath/`)

`testdata/ontology/` (tracked) is the regression ontology the successor tooling loads into a
foundation; `testdata/synthetic/amazon-twin.csv` (tracked) is a fabricated twin of the Amazon
order-history export with the same 29-column header, so the tabular tests run without private
bytes. `testdata/regression/` (gitignored) holds the real regression bytes
(`spec/successor.md` Appendix B): place `g8board-idle-stall-292301.html` and
`amazon-order-history.csv` from the source instance's `corpus/export/`, and the public
`am-tool-03-v3.pdf` (https://cdm.unfccc.int/methodologies/PAmethodologies/tools/am-tool-03-v3.pdf,
blake3 `404d090f…`). `ath/test/regression.test.ts` self-skips per missing file;
`ATH_REGRESSION=<dir>` points it elsewhere.
