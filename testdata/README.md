# testdata/ — exemplar test instance

A scratch Athenaeum instance seeded with one real artifact per interesting
mime/shape (multi-track media, mbox, zip envelopes, PDF, HTML, images,
vCard, JSON — see `exemplars.yaml` for the full list and per-shape notes),
pulled from a private source instance, for spec + tooling regression
testing against real byte shapes instead of synthetic fixtures.

Tracked here: this README, `exemplars.yaml` (the manifest — blake3 + mime +
shape + a neutral technical note, no personal content), and `seed.py` (the
seeder). **`instance/` is never tracked** — it holds real (if mostly tiny)
private artifact bytes and is gitignored at the repo root
(`/testdata/instance/`).

## Reseeding

```
ath init testdata/instance --name athenaeum-testdata   # once, if instance/ is missing
uv run --no-sync python testdata/seed.py --from /path/to/source/instance
# or: ATHENAEUM_ROOT=/path/to/source/instance uv run --no-sync python testdata/seed.py
```

Idempotent — an entry whose record already exists in `instance/` is skipped,
so re-running after adding a manifest entry only seeds what's new. Most
entries copy artifact bytes straight in and `corpus ingest` them; a few small
images exist in the source corpus only as promoted HTML-embed members with
no standalone bytes of their own (see `exemplars.yaml`'s header comment) —
for those, `seed.py` ingests the named container instead and runs `corpus
promote` inside `instance/` to re-mint the same content-addressed leaf.

Sanity-check after seeding:

```
uv run --no-sync corpus health --corpus-root testdata/instance/corpus --summary
```
