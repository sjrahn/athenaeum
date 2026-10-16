# testdata/ — the regression library

One artifact per mime (`exemplars.yaml`, 22 mimes: pdf, html, rfc822, markdown, javascript, csv, tsv, json,
ndjson, vcard, p21, zip, epub, mbox, jpeg, png, gif, webp, svg, heic, mp4, m4a) for spec + tooling
regression testing against real byte shapes, plus the regression ontology those bytes classify
under. Most bytes come from a private source instance and are **placed by hand**; a few shapes
had no suitably-small real artifact and are generated instead (see "The synthetic tier").

Tracked here: this README, `exemplars.yaml` (the manifest — file, blake3, mime, root term, shape
and a neutral technical note, no personal content), `seed.ts` (the seeder), `ontology/` (the
regression ontology a foundation starts from), `passes/` (the TOOL03 pass lines and the generated twin's) and `synthetic/`.
**`regression/` and `instance/` are never tracked** — they hold private bytes and are gitignored
at the repo root (`/testdata/regression/`, `/testdata/instance/`).

### Placing the regression bytes

`testdata/regression/<file>` for every `source: regression` entry in `exemplars.yaml`, named as the
manifest names it; the blake3 pins the exact bytes. Sources: the source instance's
`corpus/artifacts/<ab>/<blake3>.*` (the manifest's blake3 names the file), its `corpus/export/`
folder (the XenForo thread, the Amazon order history, the Discord zip, the festival mailing), and the
public TOOL03 PDF (https://cdm.unfccc.int/methodologies/PAmethodologies/tools/am-tool-03-v3.pdf,
blake3 `404d090f…`, behind an interstitial — fetch it by hand). `ath/test/regression.test.ts`
self-skips per missing file and names it; `ATH_REGRESSION=<dir>` points it elsewhere.

### The synthetic tier

A few shapes (single-track audio/mp4, a message with a nested message and an attachment,
image/heic, gif, webp, svg, ndjson, a sign with printed text, the Amazon header over fabricated
rows) have no suitably-small real artifact to pull an exemplar from. For those,
`testdata/synthetic/` holds *generated* fixtures with no private content — `gen.py` produces the
audio (ffmpeg), the message (stdlib `email`) and the heic (`heif-enc`); the gif and webp are one
ImageMagick call each; the rest are hand-written — whose bytes are committed directly to this public
repo, manifest entries pointing at them with `source: synthetic`. The committed bytes, not a fresh
run of a generator, are what the manifest's blake3 pins: an encoder's output drifts across tool
versions even for identical input (see spec/CHANGELOG.md's v32 entry, born from exactly this
problem for real media), so pinning a freshly-generated hash would make the manifest
non-reproducible from one machine or ffmpeg/libheif version to the next.

### Generated twins (`synthetic/gen/`)

Where a regression artifact is private, a *twin* with the same shape and fictional content is generated and
committed beside it, and the script that generates it is kept under `synthetic/gen/`: the twin is what the
test suite always runs; the private bytes, when placed, run the same leg over the real thing. The first is
`gen/procedure.ts`, the twin of the TOOL03 PDF: one content model drives both the typst source
(`procedure.typ`, rendered to `procedure.pdf` with typst 0.15.1 and its bundled fonts; `set document(date:
none)` makes the render byte-identical across runs) and the pass lines (`passes/<blake3>.p1.jsonl`), whose
boxes are read back off the rendered PDF through `pdf.words@1`. Re-rendering is re-running the script; the
committed PDF is what the manifest pins, and a changed render is a new blake3, a new pass file and a new pin
in the test, on purpose.

### The regression ontology

`ontology/` is the ontology every test foundation copies in (`ath/test/layers.ts`): the TOOL03
terms, the XenForo and Amazon expression roots, and a root term per mime (spec/successor.md
Appendix D, D-roots). Edit it here; `ath ontology lint` over a fresh foundation is the gate.

## Seeding a scratch instance

```
bun testdata/seed.ts                              # regression/ + synthetic/ bytes
bun testdata/seed.ts --from /path/to/source/instance   # also pull missing bytes by blake3
```

Idempotent — an entry whose subject already exists in `instance/` is skipped, so re-running after
adding a manifest entry only seeds what's new. A container's members (zip, epub, mbox, a message's
attachments) become subjects of their own.

Sanity-check after seeding:

```
bun ath/src/main.ts --root testdata/instance lint --all
```
