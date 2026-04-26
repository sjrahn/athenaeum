# Athenaeum — Corpus Implementation Guide

**Status:** living document. Updates as implementation matures.

**Companion to:** [`spec-athenaeum.md`](spec-athenaeum.md), which is the authoritative data contract. This guide describes the *implementation* of the corpus / artifact-layer pipeline. The spec says what each artifact carries; this guide says how the pipeline produces it. Choices here may change as tooling evolves; the spec must not.

The codex / document-layer counterpart is [`impl-codex.md`](impl-codex.md).

---

## 1. Scope

This guide covers the corpus side of the system: capture, reconciliation, normalization, custom-classification feedback, and re-normalization. It does **not** cover document authoring, codex regeneration, compendium build, or any cross-corpus runtime resolution — those live in `impl-codex.md`.

What lives in this guide vs in the spec:

- **Spec (authoritative).** The data contract — every field, every hash declaration, every required behavior of records. Tooling consumers rely on these guarantees.
- **This guide.** How the pipeline produces those records: which scripts run in what order, where files land on disk, sharding conventions, MIME-detection strategy, perceptual-hash family selection, in-memory vs on-disk record build.

If the two ever conflict, the spec wins; this guide gets corrected.

---

## 2. Capture pipeline

A capture takes a target (URL, filesystem path, manual upload) and produces an artifact record plus its binary in the content-addressed store. The pipeline is content-addressed end-to-end: identity is the hash of the bytes.

### 2.1 Fetch

The fetcher is responsible for retrieving the bytes. Depending on the target:

- **HTTP/HTTPS URL** — fetch with redirect-following enabled. Capture the final URL after redirect chain; both the original requested URL and the final URL are valid identifiers and both are recorded.
- **Filesystem path** — copy from disk. The source path becomes a `file://` URI on the artifact record.
- **Manual upload** — accept the bytes and any provided origin URI from the operator.

Embedded resources (images in HTML, attachments in email, etc.) are captured **as their own separate artifacts**. A captured page yields one artifact for the page and one artifact per embedded resource. Cross-references between them are resolved during normalization (§3.2).

### 2.2 MIME detection

MIME detection runs **before** hashing because perceptual-hash family selection depends on MIME (see §2.3). Strategy:

1. **Extension hint** — fast path. If the source has a recognizable extension and the magic bytes are consistent with it, accept and proceed.
2. **Magic-byte sniffing** — fallback. Use a library like `infer` (Rust) or `mime-type` to inspect the first kilobyte.
3. **`unknown` sentinel** — when both fail. Record the gap; the artifact is still valid, it just won't get format-specific normalization or perceptual hashing.

The `content_type` field on the artifact record is set from this step.

### 2.3 Hashing

Hashes are computed per the artifact's MIME's base schema (§3.3.1 of the spec). At minimum:

- **`blake3`** — always. This is the artifact's identity.
- **Format-specific perceptual hashes** as the base schema declares. Examples (illustrative; the canonical list lives in the schema files):
  - `image/*` → `phash` and/or `dhash`
  - `audio/*` → `chromaprint`
  - `video/*` → `phash` of keyframes and/or `chromaprint` of audio track
  - `text/html`, `text/markdown`, `text/plain` → `simhash`
- **Auxiliary hashes** the schema lists (commonly `sha256` for interoperability; rarely `md5`).

If a base schema is missing or incomplete for a MIME, fall back to blake3-only. The artifact is still valid; future schema updates can backfill the missing hashes via re-normalization.

### 2.4 In-memory record build

Build the artifact record's frontmatter in memory:

- `blake3` — from §2.3.
- `record_type: artifact`.
- `content_type` — from §2.2.
- Capture provenance — see §2.6.
- `hashes` — populate per the base schema's declarations.
- Base-schema extended fields — extract format-intrinsic metadata (file headers, embedded metadata: ID3 tags, EXIF, PDF info dict, HTML `<meta>` etc.).
- Custom classification schema fields — see §4.
- `status: stub` initially; flips to `draft` or `normalized` as later stages run.

The body starts empty and is filled by normalization (§5).

### 2.5 Dedup

Look up the artifact by `blake3` against the existing corpus:

- **Match.** The bytes are already in the corpus. Append capture provenance to the existing record (a new entry in `capture_dates[]`, and any new URI added to `uris[]`). Do not create a new record.
- **No match.** This is a new artifact. Write the record to its on-disk path (§2.7) and the binary to the binary cache (§2.7).

Dedup is the natural side effect of content addressing — bytes that match an existing hash hit the same record, no special "is this a duplicate?" check is needed.

### 2.6 Capture provenance

Append per-capture provenance to the artifact record:

- Append the encounter timestamp to `capture_dates[]`.
- Add any new URI(s) (request URL, final-after-redirect URL, asset CDN URL, mirror URL, DOI, `file://` path) to `uris[]`. URIs are deduplicated as a set; order doesn't matter.

That's it. The artifact record carries `uris[]` (every URI known to resolve to its bytes, none canonical) and `capture_dates[]` (every timestamp the bytes were encountered). The pipeline does **not** record per-event metadata (which URI was actually used at which moment, what `method` was used, what redirect chain occurred). If recovering a particular (uri, date) capture package becomes important later, that's a job for an out-of-band capture log, not for the artifact record.

### 2.7 Storage layout

When reconciliation completes, the artifact's record and binary live on disk. The implementation chooses sharding to keep individual filesystem directories tractable.

**Convention.**

```
corpus/{name}/
├── artifacts/
│   └── {first-2-of-blake3}/
│       └── {full-blake3}.md
├── binary/
│   └── {first-2-of-blake3}/
│       └── {full-blake3}.{ext}
├── schema/
│   ├── base/
│   └── classification/
└── capture/
```

- **Sharding depth: one level, by the first 2 hex characters of the blake3 hash.** Both `artifacts/` and `binary/` use the **same shard depth.** That gives 256 buckets at one level. At ~10k artifacts the average bucket holds ~40 records — well under any filesystem's pain threshold. At 100k it's ~400. Deeper sharding can be added later if buckets get crowded; it's a layout choice, not a contract.
- **Full hash kept in filename.** A copy of `a7f3b2c1...md` outside its shard directory still names itself fully — useful for moves, backups, ad-hoc inspection.
- **Same shard depth for binary and artifacts.** Symmetric is simpler. Per-MIME asymmetry (e.g., deeper sharding for binary because cached derivations might inflate file count) is unnecessary at current and projected scale.
- **Capture staging** lives at `corpus/{name}/capture/` for in-progress captures; failed or abandoned captures sit there without consuming corpus identity space.

The spec does not name these paths; it just requires that an artifact record be locatable from its blake3 hash, and the binary likewise. Future implementations may shard differently; consumers should not hard-code the path scheme — they should ask the corpus how to locate `{blake3}`.

---

## 3. Normalization

Normalization brings an artifact from `status: stub` to `status: normalized`. The spec defines what the normalized record carries (§5.3 of the spec); this guide describes how the pipeline gets there.

### 3.1 Conversion (deterministic)

Conversion produces the artifact's body as well-formed markdown. It is MIME-driven and shells out to deterministic tooling. Per-MIME mappings:

- **`text/html`, `application/xhtml+xml`** → an HTML→markdown extractor that strips chrome, navigation, ads, scripts, and preserves headings, paragraphs, lists, tables, code blocks. Reference implementations: readability + html2md, or a server-rendered DOM extraction pipeline.
- **`application/pdf`** → text + table extraction. OCR via `tesseract` if the PDF is image-only. Page boundaries surface as headings or anchor markers usable from functional URIs.
- **`audio/*`** → speech-to-text transcription. Reference: Whisper. Output includes timestamps. Speaker turn markers where determinable.
- **`video/*`** → audio transcription + per-keyframe descriptions when the schema asks for them.
- **`image/*`** → visual description from a VLM + OCR text via `tesseract` if applicable.
- **`text/markdown`, `text/plain`** → passthrough with minimal cleanup. `conversion_method: passthrough`.
- **`unknown`** → best-effort fallback; emit a `metadata` body summarizing what little can be determined.

Conversion writes provenance to `conversion_method`, `conversion_tool`, `conversion_date` for targeted bulk re-conversion later.

### 3.2 Cross-reference resolution (deterministic)

After the body exists, scan it for hyperlinks and embedded-resource references. For each:

1. Map the URL → blake3 by querying the corpus's URI index (any artifact whose `uris[]` contains this URL).
2. If matched, rewrite as a wikilink (`[[blake3|original link text]]`) or embed (`![[blake3]]`).
3. If unmatched, leave as a standard markdown URL or image embed. The link points outside the corpus and may be resolved by a future re-normalization pass when the target is captured.

This is purely mechanical. The normalizer does not invent links the original content didn't contain.

### 3.3 Schema application

For every artifact, apply the base schema first (extracts format-intrinsic fields, sets normalization guidance). Then walk the corpus's custom classification schemas, evaluating each one's match condition against the artifact:

- `content_type` match — exact MIME or prefix.
- `uri` regex / domain match — does any URI in `uris[]` match?
- Prior-tag match — does the artifact already have a tag the schema requires?
- Extended-field-value match — does the artifact have a field with a particular value?

Schemas that match contribute their declared tags and extended fields. Multiple schemas may match; their outputs merge with last-write-wins on collision.

### 3.4 Contextualization (LLM-driven)

Refine the body and frontmatter:

- Improve formatting fidelity (broken tables, malformed lists).
- Resolve encoding ambiguity where determinable from context.
- Add or improve image alt text from visible content.
- Surface issues to `issues[]` (missing media, broken links, partial content, encoding corruption, format loss).
- Generate or refine `description`.
- Assess `credibility_tier`.
- Set `status: normalized`.

For artifact records, contextualization MUST preserve normalization integrity — the body remains a faithful rendering of the original content. No information that wasn't in the original.

### 3.5 Self-verification

Before declaring the record normalized, the normalizer confirms:

- The `content_type` matches the actual MIME of the stored binary.
- The `blake3` field matches the binary's hash.
- The on-disk record path matches the shard convention.

Failures here are bugs in the pipeline; they should fail loudly.

---

## 4. Custom-classification feedback loop

Custom classification schemas (§3.3.2 of the spec) are corpus-local and corpus-author-driven. They emerge from observed patterns in how the corpus is used, not from upfront design. Refinement C (planned) will articulate this loop in the spec; this section describes the operational implementation.

### 4.1 Pattern detection

The curator (human or agent) periodically scans the corpus for patterns that suggest a classification schema should exist:

- **Tag clusters.** A set of artifacts share a tag and would benefit from richer extended fields than the base schema gives.
- **URI-domain frequency.** Many artifacts have one of their `uris[]` matching a common domain, suggesting a platform-specific schema (custom field set for that platform).
- **Recurring extended-field values.** Many artifacts have the same value in a schema-extracted field, suggesting a sub-classification.
- **Codex-driven demand.** The codex/compendium layers (`impl-codex.md`) reveal patterns when authoring keeps reaching for the same kind of metadata that isn't currently extracted.

### 4.2 Schema authoring

When a pattern is worth formalizing, the curator drafts a classification schema:

```yaml
schema_type: classification
match:
  content_type: "..."
  uri_pattern: "..."           # optional
  has_tags: ["..."]            # optional
  field_match:                 # optional
    field_name: value
classification:
  add_tags: [...]
extended_fields:
  ...
```

The schema is committed to the corpus's `schema/classification/` directory.

### 4.3 Re-normalization sweep

To apply the new schema retroactively, the curator triggers a re-normalization sweep over the artifacts the schema's match condition matches. Re-normalization:

- Re-runs schema application (§3.3) against affected artifacts.
- Adds the schema's tags and extended fields without disturbing other frontmatter.
- Does **not** rewrite the body unless the body's content depends on schema-extracted fields (rare).

Sweep scoping options:

- By `uri` pattern — fastest, when the schema's match is URI-based.
- By `content_type` — useful when the schema applies to a whole MIME family.
- By prior tag — when the schema layers on top of an earlier classification.

### 4.4 Schema evolution

As patterns refine, schemas iterate. A schema that initially matched too broadly can be narrowed; one that extracted weak fields can be augmented. Each iteration triggers another targeted re-normalization sweep on affected artifacts.

---

## 5. Re-normalization mechanics

Re-normalization is the general capability to re-process existing artifacts when something has improved: new schemas (§4), upgraded normalization model, better OCR/transcription tools, or newly captured artifacts that resolve previously unresolved cross-references.

### 5.1 When to re-normalize

- A new classification schema lands and its match condition selects existing artifacts.
- A base schema is improved (new extended-field declarations, better normalization guidance).
- A normalization model is upgraded.
- A conversion tool is upgraded (better extractor, better OCR, better transcription).
- An artifact has known issues that re-processing might resolve.
- Newly captured artifacts may resolve previously unresolved cross-references in older artifacts' bodies.

### 5.2 Scoping a sweep

The curator scopes the sweep using the most-precise selector possible:

- By `conversion_tool` version, when re-running improved conversion.
- By `normalization_model`, when re-running improved contextualization.
- By `uri` pattern, when applying a URI-targeted classification schema.
- By tag, when applying a tag-keyed classification schema.
- By `content_type`, when applying a MIME-keyed change.

### 5.3 Partial re-application

Re-normalization should disturb only the fields that need updating. The implementation should:

- Diff the current frontmatter against the would-be new frontmatter.
- Apply only the differences.
- Avoid churn on fields the change doesn't affect (descriptions hand-edited by curators, manually adjusted credibility tiers, etc.).

This keeps re-normalization sweeps surgical and reviewable in git diffs.

### 5.4 Cross-reference re-resolution

A lightweight sweep that re-runs only §3.2 (cross-reference resolution) against artifact bodies. Useful when many new artifacts have been captured that may resolve URLs left as plain markdown in older bodies. Doesn't touch any other field.

---

## 6. Open implementation questions

These are flagged for follow-up; not all are blockers.

- **Sharding crossover.** When does single-level sharding stop being adequate? At what corpus size do we move to two-level (`a7/f3/...`)? Likely a tooling-driven flag — `corpus.toml` could declare the shard depth and tooling could rebalance on change.
- **Binary cache GC.** Is the binary cache append-only forever, or does it have a GC pass for orphaned binaries (records deleted, hash unreferenced)? Deferred until corpus deletion semantics are needed.
- **URI index storage.** The URI → blake3 lookup needs an index. Build it on server start (rebuild from records) or maintain a side-file (`corpus/index/uri.db`)? Currently rebuilt-on-start; persistent index is a perf optimization for later.
- **Schema validation.** Should schema files themselves be validated (their match conditions parseable, their declared fields well-formed)? A `validate-schemas` tooling command would be useful.
- **Multi-corpus capture.** When the same content needs to land in multiple corpora (e.g., something captured personally and also of public interest), does the capture flow handle that, or is it a copy step on top? Currently a copy step; a "capture into multiple corpora" mode is a possible future feature.
