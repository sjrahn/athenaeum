---
spec_id: ATH-SYSTEM
title: "Athenaeum System Specification"
version: "1.0-draft"
status: draft
license: "CC BY-SA 4.0"
date_created: 2026-07-26
date_modified: 2026-07-26
---

# Athenaeum System Specification

## 1. Conformance

### 1.1 Normative language

The terms **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**,
**SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** are normative.

A conforming Athenaeum deployment MUST satisfy this document as one system contract. A
component that implements only one layer MUST satisfy every requirement assigned to that layer
and MUST preserve the reference directions and tenancy boundaries defined here.

A registered ledger or codex checkout lacking `ledger.yaml` or `codex.yaml` is
synchronization-only: it participates in `ath status` and `ath sync`, is not operational, and
MUST fail layer commands as a setup error. A registered corpus is operational when it satisfies
section 4.1; `corpus.toml` remains optional.

While this document has `status: draft`, ATH-ARCH 13, ATH-CORPUS 3.4, ATH-LEDGER 1.5, and
ATH-CODEX 1.0 remain authoritative when they conflict with this draft. Adoption MUST identify
the specifications and versions this document supersedes; after adoption, this document governs
such conflicts.

### 1.2 Scope

This specification defines:

- the system topology and member manifest;
- corpus artifact identity, records, schemas, capture, attestation, normalization, resolution,
  storage, and validation;
- ledger facts, claims, evidence, interpretations, sensitivity, derivations, and validation;
- codex targeting, generated notes, profiles, builds, certificates, and validation;
- the shared tooling, agent roles, operational gates, and trust boundaries.

### 1.3 System purpose

Athenaeum MUST:

1. capture artifacts and assign identity from their bytes;
2. represent each artifact with a faithful, addressable corpus record;
3. materialize evidence-backed knowledge in one ledger;
4. select ledger knowledge into audience-specific codices;
5. preserve a trace from codex output to ledger claim to evidence, ending at artifact bytes for
   corpus evidence or registered native identity and snapshot metadata for reference evidence;
6. enforce corpus tenancy at repository boundaries and publication tenancy at codex builds;
7. execute deterministic operations mechanically and judgment-bearing operations through
   disclosed authoring passes.

### 1.4 Core terms

| Term | Definition |
|---|---|
| **Deployment** | One orchestrator repository, one manifest, one or more corpora, exactly one ledger, and zero or more codices. |
| **Orchestrator repository** | The repository containing this specification, shared tooling, the member manifest, system runbooks, and agent definitions. |
| **Orchestrator persona** | The principal-developer role that operates the system across repositories. |
| **Member** | A corpus, the ledger, or a codex registered in the system manifest and stored as an independent repository. |
| **Corpus** | A tenant-isolated, content-addressed archive of artifacts and faithful records. |
| **Artifact** | Immutable bytes identified by their BLAKE3 digest. |
| **Record** | The markdown proxy for one artifact. |
| **Ledger** | The single repository of asserted facts and pre-assertion interpretations. |
| **Fact** | A materialized concept or edge. Concepts and edges MAY carry claims; only concepts MAY carry artifact roster entries. |
| **Claim** | One atomic asserted statement with evidence and epistemic status. |
| **Interpretation** | A structured hypothesis, assessment, or correction outside the assertion boundary. |
| **Codex** | A targeting of ledger knowledge for an audience; scope, profile filtering, and build are deterministic, while optional synthesis and voice MAY be authored. |
| **Form** | A named, mechanically checkable rendering contract over a record or record span. |
| **Functional URI** | A `corpus://` address that resolves artifact bytes or a derived surface. |
| **Reference dataset** | A registered external evidence namespace cited by native identity; shared tooling validates its namespace but does not resolve mirror content. |
| **Owner** | The human authority for system direction and actions reserved by section 7.5. |

## 2. Architecture

### 2.1 Layers

The system has three data layers and one driver:

| Layer | Owns | MUST NOT own |
|---|---|---|
| Corpus | Artifact identity, byte provenance, faithful structure, addressable renderings, faithfulness annotations | World-level meaning or claims |
| Ledger | Concepts, edges, claims, interpretations, evidence bindings, derived sensitivity | Artifact renderings or publication prose |
| Codex | Scope, profiles, generated notes, renderer-ready output, build receipts | Facts, claims, or independent knowledge |
| Orchestrator | Specifications, shared tooling, manifest, runbooks, agent definitions, cross-member operations | Member content |

### 2.2 Reference directions

Permitted references are:

```text
ledger    --corpus://--> corpora
ledger    --ref://-----> registered reference namespaces
codex     --scope------> ledger
codex     --copied corpus://--> corpora
codex     --copied ref://-----> registered reference namespaces
consumer  --ledger://---------> ledger
orchestrator --manifest-> members
```

The following are REQUIRED:

- A corpus MUST NOT reference the ledger or a codex.
- A public corpus MUST NOT reference any private corpus.
- The ledger MUST NOT reference a codex.
- A codex MUST NOT reference another codex.
- Generated views and generated notes MUST NOT be evidence targets.
- Shared knowledge between codices MUST pass through the ledger.
- A promoted record MUST persist at least one `corpus://` origin URI naming its containment
  lineage. Promotion MUST deduplicate exact URIs and preserve every distinct valid route. These
  URIs are provenance and MUST NOT be used as the record's residence index.

### 2.3 Tenancy

A corpus repository is the unit of tenant isolation.

- Public and private artifacts MUST reside in separate corpus repositories.
- Tenant assignment MUST occur before capture or ingest.
- World artifacts MUST reside in a public corpus.
- Personal records, account exports, sessions, private communications, and private tool output
  MUST reside in a private corpus.
- Corpus tooling MUST operate against one corpus root per invocation.
- Evidence, sensitivity, verification, coverage, and codex operations MUST join exactly the
  corpora declared by the ledger. `ath ledger check --no-corpus` is the limited structural-check
  exception.
- The ledger MUST remain one repository and MUST derive sensitivity from evidence.
- A non-private codex build MUST fail closed for an incomplete corpus join or a well-formed
  unresolved corpus hash. Malformed ledger entries require the separate ledger-validation gate.

### 2.4 Deterministic and authored operations

| Operation | Execution class |
|---|---|
| Capture, canonicalization, hashing, MIME detection, ingest, and attestation | Deterministic |
| Functional-URI resolution and derived views | Deterministic, version-pinned where engine-sensitive |
| Form shaping under a complete mechanical mapping | Deterministic |
| Form assertion, faithful transcription, descriptions, and editorial values | Authored pass |
| Ledger harvest, promotion, checks, verification, regeneration, and supersession | Deterministic |
| Ledger fact and interpretation authoring | Authored pass |
| Codex scope, default notes, profile filtering, build, and leak check | Deterministic |
| Member discovery, status, fetch, clone, and fast-forward synchronization | Deterministic |

Authored work MUST remain attributable in durable repository history. Agent normalization MUST
also identify its model in corpus touch provenance. A deterministic operation MUST NOT be
delegated to an LLM when the same result can be computed mechanically.

### 2.5 Durable and generated state

| Component | Durable authoritative state | Durable generated state | Ephemeral operational state |
|---|---|---|---|
| Orchestrator | Specs, tools, manifest, runbooks, agent definitions, orchestrator state/logbook/gotchas/proposals | None | Environments and caches |
| Corpus | Records, schemas, local extension code, configuration | None | Capture staging, resolver cache, queue, exports |
| Corpus storage | Artifact bytes and resolvable contained members | None | Local hydration copies where a remote or container remains authoritative |
| Ledger | `ledger.yaml`, facts, interpretations, schemas, harvest rules, invariants, schema authoring guides, and curated work-list content | Vocabulary, generated work-list blocks, and coverage views | None |
| Codex | Manifest | Generated tracked notes and certificates | Build content tree and renderer output |

Artifact bytes are durable data even when they are not tracked by Git. A deployment
MUST retain or recover every artifact required by a live record.

## 3. Deployment and Manifest

### 3.1 Orchestrator repository

The orchestrator repository MUST contain these tracked paths:

```text
athenaeum/
|-- athenaeum.yaml
|-- spec/
|-- tools/
|-- docs/
|-- .claude/agents/
`-- .claude/skills/orchestrator/
```

Default untracked member checkout paths are:

```text
athenaeum/
|-- corpora/                 # member repositories, ignored by the orchestrator repo
|-- {ledger-name}/           # ledger member repository, ignored by the orchestrator repo
`-- codices/                 # member repositories, ignored by the orchestrator repo
```

Member paths are defaults only. Shared tooling MUST resolve paths from the manifest and MUST NOT
hardcode member names or deployment-specific locations.

### 3.2 System manifest

The system manifest MUST be `athenaeum.yaml` at the orchestrator root and MUST use this shape:

```yaml
org: https://forge.example/example-org

corpora:
  corpus-name:
    description: "..."
    visibility: public
    path: corpora/corpus-name
    remote: https://forge.example/example-org/corpus-name.git

ledger:
  ledger-name:
    description: "..."
    path: ledger-name
    remote: https://forge.example/example-org/ledger-name.git

codices:
  codex-name:
    description: "..."
    path: codices/codex-name
    remote: https://forge.example/example-org/codex-name.git

references:
  dataset-name:
    description: "..."
    mirror: /absolute/path/to/mirror
    snapshot: "snapshot-id"
```

Manifest rules:

- `org` MUST be a repository base URL.
- Member keys are member names.
- Manifest order is presentation order.
- Corpus visibility is `public` or `private` and defaults to `private`.
- A deployment MUST register exactly one ledger.
- Default corpus paths are `corpora/{name}`.
- The default ledger path is `{name}` at the workspace root.
- Default codex paths are `codices/{name}`.
- Default remotes are `{org}/{name}.git`.
- `path` and `remote` override their defaults.
- Reference datasets are not Git members.
- A reference registration MUST provide a mirror path and snapshot identifier.
- Member entries MUST NOT pin commits.

These are deployment constraints beyond the shared loader's full enforcement. The loader checks
layer mappings, rejects more than one ledger, validates corpus visibility, and requires either a
remote or an `org` from which to derive one. It does not validate `org` as a URL, accepts zero
ledgers, and accepts empty reference mirror or snapshot values. Ledger commands reject a
zero-ledger deployment.

The reference topology places the orchestrator and member repositories in one designated forge
organization. Repository visibility is the outer access-control boundary. A remote override MAY
name another organization and MUST provide equivalent tenancy controls.

### 3.3 Discovery

- System, ledger, and codex verbs MUST locate the orchestrator root by walking upward for
  `athenaeum.yaml` unless an explicit root is supplied. `ath corpus` delegates without manifest
  discovery.
- Corpus commands operating on an existing corpus MUST locate its root by walking upward for both
  `records/` and `schema/` unless `--corpus-root` is supplied. `corpus init` creates a root and is
  exempt.
- Ledger and codex commands MUST resolve the ledger and codex through the manifest.

### 3.4 Member synchronization

`ath sync` MUST:

- clone a missing member from its resolved remote;
- fetch an existing member;
- report tracking state;
- modify an existing branch only when `--pull` is supplied;
- permit only fast-forward pulls;
- fail on clone, fetch, or pull errors.

`ath status` MUST report the orchestrator and every member, including branch, dirty state, and
ahead/behind state. Missing repositories MUST make status fail. Dirty repositories alone MUST
not make status fail.

### 3.5 Runtime

The reference tooling MUST be one Python distribution named `athenaeum`, requiring Python 3.14
or later, and MUST provide exactly these top-level executables:

```text
ath
corpus
```

Ledger and codex commands MUST be subcommands of `ath`. A deployment MUST NOT require separate
`ledger` or `codex` executables.

## 4. Corpus Contract

### 4.1 Corpus root

A filesystem corpus MUST contain `records/` and `schema/`. It MAY contain the remaining paths:

```text
corpus-root/
|-- records/                   # tracked record markdown
|   `-- <id[:2]>/<id>.md
|-- schema/                    # tracked corpus-local schemas
|-- artifacts/                 # untracked artifact residence or hydration cache
|   `-- <id[:2]>/<id>.<ext>
|-- capture/                   # untracked staging
|-- cache/                     # untracked resolver output
|-- queue/                     # untracked normalize coordination
|-- export/                    # untracked portable renderings
|-- corpus.toml                # optional corpus configuration
|-- capturers/                 # optional trusted local extensions
|-- drafters/                  # optional trusted derivation extensions
`-- shapers/                   # optional trusted local form shapers
```

`records/` and `schema/` are durable corpus state. `capture/`, `cache/`, `queue/`, and
`export/` are reclaimable operational state. Artifact bytes MUST remain available through the
configured store or a valid containment route.

### 4.2 Artifact identity

- An artifact id MUST be the BLAKE3 digest of the artifact bytes.
- The encoded id MUST be exactly 64 lowercase hexadecimal characters.
- A record filename stem MUST equal its artifact id.
- A lookup by id MUST yield bytes whose BLAKE3 digest equals the id.
- Different bytes MUST receive different ids.
- Re-encountering identical bytes MUST reuse the existing record.
- Alternative byte hashes MUST use `<algorithm>:<lowercase-hex>`.
- The primary BLAKE3 MUST NOT be duplicated in `transport`.

### 4.3 Residence and containment

Physical artifact-store location MUST be invisible to the record. Containment routes remain
derivable from stored member rows.

- Bytes MAY reside as a standalone object, within a container, or through multiple routes.
- A standalone residence MAY be local or remotely hydrated.
- A promoted member MAY have no standalone artifact file.
- Contained residence MUST be derived from member rows in container records.
- Every valid route to an id MUST yield identical bytes.
- A promoted record's lineage origin MUST NOT be the authoritative residence route.
- Containment resolution MUST detect cycles.
- Materialized members MAY be cached by content identity.

### 4.4 Transport, members, and units

Every artifact is one transport. A MIME schema MAY declare a disposition and defaults to `work`:

| Disposition | Contract |
|---|---|
| `work` | The transport is one work. Independently meaningful internal transports may be exposed as members but are not the work's primary content structure. |
| `manifest` | The members are the content. The record stores the roster required by the MIME attestation contract; that roster MAY be selective and cumulative when the MIME contract permits it. No authored member listing is stored. |

An origin overlay MAY override the MIME disposition.

A member is an independently meaningful transport with its own MIME, byte identity, address,
and byte count. A unit is content inside one transport and is addressed by a unit operation such
as `turn=`. Units MUST NOT be stored as member rows merely because they are addressable.

### 4.5 Record frontmatter

A record MUST begin with YAML frontmatter and MAY contain only these keys:

| Field | Type | Required | Contract |
|---|---|---:|---|
| `id` | string | yes | Artifact BLAKE3; equals filename stem. |
| `title` | string | no | Deliberate final override of the derived title. |
| `description` | string | no | Deliberate final override of the derived description. |
| `transport` | string or list | no | Additional byte hashes. |
| `canonical` | string or list | no | Canonical-content hashes under declared strategies. |
| `perceptual` | string or list | no | Record-level fingerprints for single-atom records. |
| `touch` | string or list | yes | Non-empty ordered current-shape provenance. |
| `visibility` | enum | no | `visible`, `deranked`, or `hidden`; default `visible`. |

An override equal to the otherwise derived editorial value is invalid redundant state.

Touch identifiers MUST use one of:

```text
corpus.<module>@<version>[_N]
<tool>@<version>[_N]
<model-id>[<modifier>][_N]
corpus.<module>@<version>+<model-id>[<modifier>][_N]
```

Consecutive equal identifiers MUST coalesce with `_2`, `_3`, and subsequent counters. The touch
chain records current-shape provenance and MAY be reset by `re-stub`.

### 4.6 Record body

The record body MUST contain three zones in this order:

```text
metadata
content
annotations
```

Allowed block families and cardinalities are:

```text
<!--artifact <mime-type>-->                  exactly 1
<!--origin [<id>[/<subtype>]]-->             1 or more
<!--members-->                               0 or 1
<!--embed <mime-type>-->                     0 or more; alternate to members

<!--section <form-id>-->                     0 or more
<!--segment <atom>[/<id>]-->                 0 or more
<!--segment structural-->                    0 or more

<!--context <namespace>[/<id>[/<subtype>]]--> 0 or more
```

`embed` and `members` MUST NOT coexist in one record.

Each block MUST be an HTML comment with an opener line, zero or more YAML payload lines, and `-->`
on a line by itself. Metadata, annotation, and section blocks MUST contain no prose body. Only
permitted text segments may contain markdown body content.

A later-zone block preceding an earlier-zone block is invalid.

### 4.7 Artifact block

The artifact block MUST use:

```markdown
<!--artifact <canonical-mime-type>
<schema-declared-fields>
-->
```

The opener MIME type is authoritative. Artifact fields MUST describe the primary artifact bytes
and MUST use the names declared by the matching MIME schema. The block contributes
`mime/<mime-type>` to the classifications view.

### 4.8 Origin blocks

Every origin block MUST carry `snapshot` as an ISO-8601 timestamp.

A retrieval origin MUST carry `uri`:

```markdown
<!--origin <id>[/<subtype>]
uri: https://example.test/resource
snapshot: 2026-07-26T00:00:00Z
-->
```

`uri` MAY be a list when several URLs identify the same retrieval origin.

A local-file origin normally omits `uri` and carries:

```markdown
<!--origin <id>[/<subtype>]
filename: artifact.pdf
source_modified: 2026-07-25T12:00:00Z
snapshot: 2026-07-26T00:00:00Z
-->
```

Rules:

- An origin is source-bearing when it has a non-empty `uri`, `filename`, or `source_modified`.
  Tooling permits local metadata beside a URI.
- A bare origin has no overlay and contributes no origin classification.
- A qualified origin contributes `origin/<id>[/<subtype>]`; an unresolved overlay is skipped
  rather than rejected.
- Distinct sources MUST use distinct origin blocks.
- Alias URLs for one source MUST share one block.
- Re-encounters MUST append or fold origin provenance without replacing prior origins.
- Producer-declared origins MAY be qualified through capture sidecars or embedded origin tags.

### 4.9 Members block

The members block carries the complete roster required by the applicable attestation strategy:

```markdown
<!--members
- address: path=manual.pdf
  media_type: application/pdf
  transport: blake3:<64-lowercase-hex>
  bytes: 123456
- address:
  - el=4
  - el=9
  media_type: image/png
  transport: blake3:<64-lowercase-hex>
  bytes: 2048
-->
```

Each row MUST contain exactly:

| Field | Contract |
|---|---|
| `address` | One address or an ordered non-empty list of occurrence addresses. |
| `media_type` | Full MIME type of the member. |
| `transport` | Content-identifying `<algorithm>:<hex>` hash. |
| `bytes` | Uncompressed non-negative byte count. |

Unknown or missing row keys are invalid.

The shared parser rejects unknown row keys but accepts an absent or unvalidated `bytes` value,
and `append_member` does not coalesce duplicate transports. Such rows do not satisfy this data
contract even when they pass ordinary lint.

Manifest strategies are normally unabridged. A MIME-specific contract MAY permit selective
cumulative declaration. `application/mbox` declares only requested 1-indexed `msg=` members, and
an undeclared run may carry no member rows.

Members MUST be deduplicated by `transport`; repeated occurrences MUST accumulate addresses in
source order. The roster is wholly attested. A normalizer MUST NOT alter roster membership,
addresses, MIME types, transport hashes, or byte counts.

Filenames, dimensions, verbatim alternative text, mail headers, display names, and other
mechanically readable member facts belong to the `members` derivation. Authored descriptions and
narration do not. A record narrates a placed asset through its section or segment description or
through the promoted member's own record.

A segment links a member by address membership. Unplaced members are valid. Image, audio, and
video segments MUST match a member address unless the address is an artifact self-slice or a
lineage-resolvable reference.

#### 4.9.1 Alternate roster form

Readers MUST also accept the per-asset roster form:

```markdown
<!--embed <media-type>
address: <address-or-list>
transport: blake3:<64-lowercase-hex>
<legacy-descriptive-fields>: <values>
-->
```

A record using per-asset blocks MUST NOT also contain a `members` block. Ordinary serialization
MUST preserve the record's existing roster form. New records and new attestations MUST emit only
the `members` form. Re-attestation MUST convert per-asset blocks into a members roster by reading
the artifact, computing `bytes`, deduplicating by transport, and dropping fields outside the
four-key members-row contract. Conversion MUST report the number of retired descriptions being
dropped and identify affected addresses; bulk output MAY bound the address sample. Writers MUST
NOT emit new per-asset blocks.

`decompose`/`compile` is a rebuilding path rather than ordinary serialization. Compile emits a
members roster, converts an alternate roster, and drops its extra fields without the
re-attestation conversion report.

### 4.10 Sections and forms

A section declares one form over a positional content span:

```markdown
<!--section <form-id>
address: <form-defined-envelope>
entry: <optional-label>
title: <optional-title>
description: <optional-description>
<form-fields>: <values>
-->
```

- A whole-record section MUST omit `address` and MUST have no sibling sections.
- A span section MUST carry the exact envelope defined by its form's address axis. The applicable
  schema MUST define address ordering and envelope construction.
- Sections MUST be depth one, non-overlapping, and non-nesting.
- A section span runs to the next section or the end of the content zone.
- Prose between a section header and its first segment is invalid.
- Segments outside a section stand under the formless identity contract.
- A form assertion and form conformance MUST land in the same write.
- Whole-record `title` and `description` are record editorial candidates.
- Span-scoped editorial values apply only to that span.

### 4.11 Content segments

A content segment MUST use:

```markdown
<!--segment <atom>[/<overlay-id>]
address: <address-or-list>
description: <optional-description>
perceptual: <optional-algorithm:hex>
entry: <optional-label>
speaker: <optional-integer>
<overlay-fields>: <values>
-->

<optional-text-body>
```

The content atoms are exactly `text`, `image`, `audio`, and `video`.

- Segment identity is `(opener-id, address)`.
- Equal addresses MAY stack only when opener ids differ.
- An address list represents non-contiguous regions in reading order.
- `entry` is an optional authored leaf label. Lint warns when a multi-block content zone is only
  partially labeled.
- Segment-scoped issues MUST be separate context blocks.

Body rules:

| Segment | Body contract |
|---|---|
| Bare `text` | MAY contain faithful markdown prose. |
| `text/<id>` with `enables_lossless: true` | MAY contain the overlay-defined lossless shape. |
| `text/<id>` with `enables_lossless: false` | MUST be body-empty and SHOULD carry a description. |
| `image`, `audio`, `video` | MUST be body-empty and MAY carry a description. |

Segment bodies MUST be faithful renderings of addressed content. Summaries, paraphrases, visual
readings, and other lossy descriptions MUST NOT appear in segment bodies. Segment bodies MUST
NOT contain `corpus://` links or raw corpus hash links. Source-authored ordinary URLs MAY remain
verbatim.

### 4.12 Structural segments

A structural segment MUST use:

```markdown
<!--segment structural
address: <source-mark-position>
level: <positive-integer>
entry: <optional-source-label>
-->
```

- It MUST be body-empty.
- It MUST NOT take an atom overlay.
- It MUST correspond to a boundary declared by artifact bytes or producer enrichment.
- An authored pass MUST NOT invent a structural segment.
- `level` MUST preserve source hierarchy or be `1` when no hierarchy is declared.
- Its scope extends to the next mark of equal or shallower level or to the enclosing span end.
- Tables of contents MUST be derived from the flat mark sequence and MUST NOT be stored as block
  nesting.

Structural segments declared by MIME attestation belong to the attested layer. Structural marks
persisted from one-shot producer enrichment belong to the capture-origin layer and MUST survive
re-attestation when their sidecar is unavailable. Structural segments written by normalize
belong to the normalize-owned layer.

### 4.13 Context blocks

A context block MUST use:

```markdown
<!--context <namespace>[/<id>[/<subtype>]]
address: <optional-segment-address>
quote: <optional-verbatim-span>
occurrence: <optional-positive-integer>
<namespace-fields>: <values>
-->
```

Without `address`, context is record-scoped. With `address`, it is segment-scoped. `quote` and a
positive `occurrence` carry asserted anchor semantics. Lint checks only string shape for
`address` and `quote`; verbatim occurrence is an authoring responsibility.

`provenance` is reserved. Mechanically regenerated context MUST include `provenance: auto`;
asserted context MUST omit `provenance`.

Context MUST be limited to durable mechanical or faithfulness observations. It MUST NOT contain
normalizer scratch notes, world-level interpretation, or general summaries.

Current namespaces are:

| Namespace | Contract |
|---|---|
| `issue` | A typed record or segment faithfulness problem. |
| `reference` | An overlay-declared dependent source link. |
| `relation` | A corpus-local source cross-link namespace. |

Issue vocabulary is schema-defined and MUST be parsed tolerantly across corpora. Reference blocks
are mechanically emitted only when an origin overlay declares extraction and the referent exists
in the record. Their target remains a URL; captured-record resolution is derived at read time.
Shared tooling does not emit relation blocks.

### 4.14 Derived editorial values

Record title and description MUST be derived at read time. Candidate precedence is:

```text
artifact -> origin -> whole-record form -> frontmatter override
```

Later layers override earlier layers. Within one layer, later blocks override earlier blocks.
Within one block, declaration order selects the first non-empty role-marked field.

MIME, origin, and form fields MAY declare `role: title` or `role: description`.

Forms and origin overlays MAY declare all-or-nothing templates:

```yaml
editorial:
  title_template:
  - "Statement - {account} - {period}"
  - "Statement - {period}"
```

Every placeholder MUST resolve for a template to apply. Ordered template lists use the first
fully resolving template. List-valued substitutions join non-empty values with `, `.

Within the form layer, candidate order is:

```text
explicit section value -> template -> role-marked form field
```

Only a whole-record section contributes form candidates at record scope. An empty derived title
or description is valid.

### 4.15 Derived record state

State MUST be computed and MUST NOT be stored.

| State | Predicate |
|---|---|
| `terminal` | A terminal form governs the record and no content-atom rendering is stored. |
| `formed` | A named form section governs a stored rendering. |
| `rendered` | A content-atom rendering exists without a governing form. |
| `proxy` | No terminal form and no stored content-atom rendering. |

Structural marks alone do not constitute a rendering. A proxy is complete and readable through
artifact bytes and derivation operations.

### 4.16 Schema namespaces

Reserved schema namespaces are:

| Namespace | Block | Responsibility |
|---|---|---|
| `mime` | artifact | MIME recognition, disposition, attestations, address axes, derivations, citation surface |
| `origin` | origin | source recognition, capture, producer fields, form declaration, operational overlays |
| `form` | section | rendering contracts and conformance checks |
| `atom` | segment | segment shape and lossless-body permission |
| `context` | context | annotations and issue vocabularies |

Schema lookup MUST walk most-specific to least-specific:

```text
subtype -> id -> axis/common -> namespace universal
```

The effective schema MUST merge from least-specific to most-specific so that specific mappings
override general mappings. Lists replace rather than concatenate. At each rung, a corpus-local
file shadows the packaged file as a whole.

Origin subtype resolution is concern-specific. Editorial, disposition, fingerprint, strip, and
partition resolution use subtype-first fallback. Form selection, semantic-field views, and
guidance resolve the id-level origin overlay only.

The closed semantic-type vocabulary is:

```text
uri
timestamp
identifier
hash
fingerprint
person
geolocation
```

Corpus-local schema code and Python extensions are trusted deployment code. Loading failures
MUST be reported and skipped during tolerant reads. A serving process MUST NOT execute capture
or shaping extensions merely by serving records.

Corpus configuration MUST be loaded from built-in defaults, then `[corpus]` in
`<corpus-root>/corpus.toml`, then environment overrides. Invalid backend or adapter names MUST
fail. The supported configuration shape is:

```toml
[corpus.store]
backend = "local"            # local | azure | s3
account = "..."              # azure
container = "..."            # azure
bucket = "..."               # s3
region = "..."               # s3
prefix = "..."               # azure or s3

[corpus.transcription]
adapter = "noop"             # noop | http-whisper
base_url = "..."

[corpus.capture]
default_transport = "headless" # headless | headed | cdp
```

Supported environment overrides are `CORPUS_STORE`, `CORPUS_AZURE_ACCOUNT`,
`CORPUS_AZURE_CONTAINER`, `CORPUS_AZURE_PREFIX`, `CORPUS_S3_BUCKET`, `CORPUS_S3_REGION`,
`CORPUS_S3_PREFIX`, `CORPUS_TRANSCRIBE`, `WHISPER_BASE_URL`, and
`CORPUS_CAPTURE_TRANSPORT`. `WHISPER_BASE_URL` fills an absent file value and MUST NOT replace a
configured `base_url`.

### 4.17 MIME schemas

A MIME schema MAY declare:

- canonical MIME applicability and container signatures;
- `working_kind`;
- `citation_surface: raw | segments`;
- `disposition: work | manifest`;
- `attest` declarations;
- `derive` operations;
- `address_scheme`;
- `extended_fields` and editorial roles;
- sidecar lift;
- alternative transport hashes;
- canonical and perceptual fingerprint policies;
- normalization guidance;
- a terminal form default.

`raw` is the default citation surface. When no valid schema value is declared, the HTML family
defaults to `segments`; an explicit `raw` or `segments` declaration overrides that fallback. A
MIME-level form declaration MUST name a terminal form.

MIME schema declarations use these value contracts:

- `applies_to.content_types` is a list of canonical MIME strings.
- `applies_to.zip_members` is an any-match list of exact member paths.
- `applies_to.zip_member_patterns` is an all-match list of regular expressions.
- `working_kind` is the initial resolver working type.
- `citation_surface` is `raw` or `segments`.
- `disposition` is `work` or `manifest` and defaults to `work`.
- `derive` is an interpreted strategy mapping. `attest` is declarative metadata.
- `address_scheme` declares permitted segment-address axes.
- `extended_fields` is a field mapping; each field MAY declare type, semantic type, editorial
  role, requirement, and closed values.
- `transport_algos` is a list of additional byte-hash algorithm names.
- `normalization.guidance` is normalizer-facing markdown.
- `form.id` names a terminal form only.

Readers MUST accept `mode` and `draft.*` declarations through the schema compatibility aliases.
New schemas SHOULD emit `disposition`, `attest`, and `derive`. A MIME schema MAY declare
`csv_dialect` for row/column resolution and a corpus-local `default_origin` binding for
unattributed producer-shaped imports.

An atom schema MUST declare `kind: atomic` and `applies_to.atom`. It MAY declare cues, extended
fields, and normalization guidance. `enables_lossless` defaults to false; only a text-atom
overlay may set it to true and license a shaped faithful segment body.

### 4.18 Origin overlays

An origin overlay MAY declare:

- host or scheme matching;
- capture transport, fidelity, interactions, URL rewriting, and URL equivalence;
- pagination and dependent capture;
- yt-dlp options and cookie scope;
- additional origin fields and editorial roles;
- disposition overrides;
- an unconditional or route-keyed form declaration;
- a form mapping consumed by shapers and unit resolvers;
- reference extraction;
- transcription configuration;
- assembly, pre-hash stripping, and temporal partition behavior;
- normalization guidance.

For route matching, an origin block's primary URI is its scalar `uri` or the first item in its
`uri` list. Route-keyed forms MUST be ordered first-match rules evaluated against the primary URI
of the qualified origin block being resolved. A block without a URI does not match a route rule.
A rule without `match` is a fallback.

Subtype precedence applies only to the concern resolvers identified in section 4.16.

An unconditional origin form uses:

```yaml
form:
  id: conversation
  mapping: {}
```

A route-keyed declaration uses:

```yaml
form:
  - match: "/procedure/"
    id: procedure
    mapping: {}
  - id: document
```

`applies_to.host_pattern` or `host_patterns` matches web hosts.
`applies_to.scheme` or `schemes` matches URI schemes case-insensitively.
`applies_to.include_subdomains` defaults to false.

Capture configuration uses:

```yaml
capture:
  capturer: browser
  transport: headless
  fidelity: balanced
  interactions: []
  url_rewrite: []
  url_equivalent: {}
  pagination: false
  ytdlp: {}
  cookies_from_host: true
  viewport: 1280x720
  user_agent: "..."
  references: []
```

`capturer` names `browser`, `video`, or a registered corpus-local capturer. Browser transport is
`headless`, `headed`, or `cdp`. Fidelity is `exact`, `balanced`, or `lean`. URL rewrite rules are
ordered `{pattern,replacement}` mappings. URL equivalence MAY declare `query: keep|drop`, ordered
rules, and `on_rewritten`. Pagination MAY be `true` or a mapping containing
`content_selector`, `next`, `max_pages`, and `expect_count.selector`.

Producer-level `strip_headers`, `strip_fields`, and `partition` declarations live at
origin-overlay scope. Lookup walks the stamped producer subtype/id ancestry; an explicit empty
strip list disables that strip. When no producer is stamped, a corpus-local MIME `default_origin`
binding MAY select the producer declaration. A stamped producer's silence is final and MUST NOT
fall through to `default_origin`.

### 4.19 Forms

A form schema declares a structural rendering contract and MAY declare section fields,
decomposition, address axes, checks, guidance, and editorial templates. Form ids MUST be
discovered from `form/*.yaml`; this specification does not duplicate that registry.

Deterministic shaper code is registered separately by form or origin id. A form schema declares
the decomposition contract consumed by a shaper; it does not contain or register the shaper
implementation.

Formless is the zeroth form and MUST remain valid; there is no catch-all rendering form. A
terminal contract is identified by `terminal: true`. `passthrough` and `manifest` are packaged
terminal contracts, but terminality MUST be resolved from the schema marker rather than
hardcoded ids.

- `passthrough` declares that artifact bytes are the terminal representation.
- `manifest` declares that the attested member roster is the terminal representation.
- A terminal record MUST NOT store content-atom renderings.
- Structural marks and an empty whole-record form header are permitted.

Governing form precedence is:

```text
origin declaration -> asserted whole-record section -> MIME terminal default -> manifest derivation
```

MIME and manifest class defaults MUST yield to an existing stored rendering. Manifest derivation
applies only when the effective disposition is `manifest` and an attested member roster exists.
Explicit origin declarations and asserted whole-record sections are not subject to those guards.

### 4.20 Capture

Capture produces staged bytes and provenance. It MUST NOT mint corpus identity before the final
artifact bytes are established.

- Capturer routing MUST be origin-overlay-driven.
- The default browser capturer MAY be overridden by CLI or overlay.
- Browser interactions MUST run in declaration order.
- Supported interaction classes MAY include scroll, expand, click, hover, wait, remove, and
  explicit evaluation.
- Interaction failures MAY be non-fatal but MUST NOT be represented as successful content
  completeness checks.
- Browser capture MUST produce a self-contained snapshot.
- Capture fidelity is `exact`, `balanced`, or `lean` and MUST be recorded in the snapshot.
- `url_rewrite` changes the fetched target while preserving the inbound URL as provenance.
- `url_equivalent` changes resource comparison only and MUST NOT change fetched bytes.
- Pagination capture MUST produce one merged artifact and MUST NOT ingest intermediate pages.
- Incomplete pagination MUST emit a warning issue.
- Dependent capture MUST stop at depth one.
- From-save capture MUST NOT fetch network content.
- External durable capture MUST be owner-authorized.

### 4.21 Pre-identity transforms and assembly

An origin MAY declare deterministic transforms applied before artifact identity, including mail
header stripping and span-surgical JSON field stripping.

- The stored artifact id MUST hash the transformed bytes.
- When transformation changes delivered bytes, the origin block for that delivery MUST retain
  `source_transport: blake3:<64-lowercase-hex>`. As origin history, this field MUST survive
  `re-stub`.
- JSON stripping MUST preserve all unaffected byte spans and MUST NOT reserialize the document.
- A pre-identity transform MUST be a declarative producer-origin overlay setting. Its
  configuration is version-controlled with the overlay and its execution version is disclosed
  through tooling provenance; no separate overlay `version` field is defined.

`corpus assemble` MAY convert multipart deliveries or directory exports into one deterministic
bundle before ingest. Assembly MUST abort on unreadable input or unresolved member conflicts.
The bundle writer MUST order members deterministically and preserve declared member bytes and
timestamps.

### 4.22 Temporal partitioning

A producer partition declaration MAY split temporal exports when repeat-export stability has
been measured.

- A schedule supports `grain: month | year`, optional grain-specific `eras`, and
  `undated: standing | rolling`.
- A declared schedule defaults `undated` to `standing`; mailbox splitting without a schedule
  uses year grain with rolling undated members.
- Each run emits closed periods and one current-period residue.
- Standing undated members use a separate bucket; rolling undated members join the residue.
- Closed periods MUST be byte-stable and re-encounterable.
- Growth MUST produce a continuity-gated successor.
- Closed periods MAY be assembled into larger containers.
- Partition grain and capture cadence are independent.

### 4.23 Ingest and attestation

Ingest MUST:

1. read capture context and producer declarations;
2. apply declared pre-identity transforms;
3. compute BLAKE3 identity and configured transport hashes;
4. detect and refine MIME;
5. persist or establish a valid residence for the bytes;
6. create or locate the record;
7. attest artifact fields, members, declared byte-marks, and available sidecar enrichment;
8. add origin provenance;
9. append the ingest touch;
10. remove successful staging inputs.

Re-encountering identical bytes MUST fold provenance into the existing record. Different bytes
MUST produce a different record.

Attestation MUST be deterministic. Re-attestation MUST replace artifact fields, the ordinary
member roster, and each MIME-declared structural mark whose source remains regenerable while
preserving normalize-owned content. One-shot capture enrichment already persisted on an origin
block or as structural marks MUST remain when its consumed sidecar is unavailable.
Re-attestation MUST merge newly available marks idempotently rather than duplicate them.

A MIME schema MAY declare a selective manifest. A selective manifest roster is complete only for
the declared subset. Re-attestation MUST preserve previously declared members, add newly declared
members idempotently, and MUST NOT infer that undeclared members are absent from the artifact.

### 4.24 Promotion

Promotion MUST:

1. accept a member functional URI;
2. locate the member through the container's attested roster;
3. materialize member bytes;
4. verify the bytes against the member row's declared transport hash and compute their BLAKE3;
5. mint or re-encounter the member record under the computed BLAKE3 id;
6. detect its MIME and mint a proxy with an empty artifact payload; independent attestation
   occurs on a later `corpus reattest` pass;
7. record the container functional URI as containment lineage;
8. leave member bytes in place while containment remains a valid residence.

### 4.25 Normalize

Normalize is the sole authoring pass over a record.

It MAY:

- execute a deterministic form shaper;
- assert a form when the bytes satisfy it;
- write a faithful stored rendering;
- write whole-record or span editorial values;
- write section and segment descriptions;
- write asserted faithfulness issues;
- write non-MIME structural marks that are mechanically recoverable from the source.

It MUST NOT:

- add information absent from the artifact or declared capture enrichment;
- alter roster semantics; deterministic `compile` MAY perform only the representation conversion
  required by section 4.9.1;
- put lossy prose in a segment body;
- invent structural marks or addresses;
- store intra-corpus links in segment bodies;
- regress an existing faithful rendering;
- assert world-level facts.

Every address written by normalize MUST be derived from the artifact, resolved, and inspected
before the pass is finalized. This is an authoring responsibility: `finalize` runs ordinary lint
only, while `corpus lint --resolve` separately checks section, segment, and member addresses but
not context anchors.

### 4.26 Rerun ownership

| Operation | Owned effect |
|---|---|
| Re-ingest | Fold provenance for identical bytes. |
| Re-attest | Replace the attested layer only. |
| Re-normalize | Replace normalize-owned rendering and prose. |
| Re-resolve | Regenerate ephemeral resolver output. |
| Re-stub | Return the record to a pre-attestation proxy baseline and reset current-shape provenance. |

`re-stub` MUST preserve id, transport hashes, MIME, origin history, visibility, artifact
residence, and the original ingest provenance. It MUST remove editorial overrides, canonical
and perceptual values, schema-derived artifact payloads, members, sections, segments, context,
and post-ingest current-shape touches before re-attesting.

### 4.27 Normalize queue

Queue state is per corpus, external to records, and transitions:

```text
idle -> requested -> claimed -> idle
```

An idle entry MAY retain the last completed or failed outcome for an awaiter; that outcome is not
a fourth live state.

`enqueue` idempotently creates or joins a pending request. A joining hint appends while the
request remains requested; a request arriving after claim is reported as in flight and does not
alter the claimed payload. `drain` atomically claims the oldest eligible request. `drain --wait`
long-polls until a claim is available or its timeout expires. `finalize` completes a claimed pass
only after its form and ordinary-lint gate succeeds. Bare `release` requeues a claim;
`release --failed` records a failed result. `await` polls for a result and, when none exists,
falls back to form-state evaluation without rerunning lint.

The pass gate requires zero lint errors, any declared form to be present and coherent, and any
terminal form to carry no rendering. Editorial values are optional; no separate editorial-vouch
field is part of the record contract.

The reference queue storage uses `.req`, `.claim`, and `.result` files, atomic same-directory
renames, a 1,800-second lease, and seven-day result retention. The values and filenames are
operational defaults, not conformance requirements. `corpus queue --prune` removes aged outcomes
and orphaned temporary files but never live requests or claims. Queue state is coordination, not
durable history.

### 4.28 Functional URI grammar

The corpus URI grammar is:

```text
corpus://<64-lowercase-blake3>[?<param>[&<param>...]][#<fragment>]
```

A parameter is `key=value` or a flag key. Order is significant and operations compose from left
to right. Values MUST percent-encode `%`, `&`, and `#` as `%25`, `%26`, and `%23`.

A bare URI resolves artifact bytes. A parameterized URI resolves an addressed or derived
surface. A fragment is a preserved body-anchor name and is not a transform operation.
Canonicalization MUST lowercase the hash, preserve parameter order, decode then re-encode value
escapes, and preserve the fragment. Incompatible operation sequences MUST fail.

### 4.29 Functional URI operations

Functional URI operations include:

| Family | Operations |
|---|---|
| Record | `body`, `members` |
| PDF | `page=N`, `render`, `text`, `words`, `probe`, `outline`; `dpi=N` render configuration |
| Image | `format=png`, `bbox=`, `crop=`, `mark=`, `cover=`, `resize=`, `fit=`, `rotate=`, `auto_orient`, `autocontrast`, `contrast=`, `grayscale` |
| Media | `frame=`, `stream_id=`, `time_range=`, `cut=`, `format=`, `transcribe`, `scenes=` |
| Units | `turn=N`, `turn=N&att=M` |
| Additional operations | Registered handlers reachable from the active working-kind pipeline. |

A resolver MUST NOT advertise a selector as supported unless its active working-kind pipeline
has a registered handler. An `address_scheme` declaration alone does not guarantee
materialization. The shared resolver additionally provides HTML `selector=` and media
`extract_audio` operations.

Operation requirements:

- `body` returns the mechanical faithful body derivation.
- `members` returns each stored roster row augmented with mechanically readable descriptors.
- `page=N` is 1-indexed and renders when terminal or followed by an image operation.
- `page=N&text` returns embedded text and MUST NOT perform OCR.
- Image `bbox=x,y,w,h` and `crop=x,y,w,h` use top-left relative fractions.
- `x+w` and `y+h` MUST each be at most `1`.
- Spreadsheet `bbox` MAY use an A1 range.
- `mark` outlines without cropping.
- `cover` removes pixels and remains disclosed in the URI.
- `fit` preserves aspect ratio and MUST NOT enlarge.
- `resize` MAY distort and enlarge.
- `time_range` accepts one range or an ordered comma-separated range list.
- `cut=precise` is frame-accurate and may re-encode.
- `cut=copy` is keyframe-snapped and may widen bounds.
- On image values, `format=` accepts only `png`.
- Media `format=` accepts registered targets. GIF drops audio and audio-only targets drop video.
  A media-format result is terminal and accepts no following operation.
- `turn=N&att=M` resolves through containment lineage.
- `path=` re-sniffs a member before any following operation.
- A terminal textual `path=` returns text; a non-text member returns bytes.
- For media muxing, omitted `stream_id` selects the sole stream of each present audio/video kind
  and fails when a present kind is ambiguous. No declared-primary fallback is implemented.
- Ambiguity MUST fail.

Bare resolver configuration parameters such as `dpi`, `cut`, or `time` without a consuming
operation return the source artifact unchanged.

### 4.30 Resolver and cache

An uncached pure resolver operation is deterministic over canonical URI, artifact bytes, schemas,
and operation version. Engine-sensitive operations are deterministic per their effective engine
version.

Resolver output is ephemeral and MUST NOT become a corpus record solely because it was rendered.
Cache identity uses the canonical functional URI, the transcription adapter for `transcribe`, and
ffmpeg identity for `time_range`, `format`, and `scenes`. `frame` and `extract_audio` are not
engine-version-keyed. Schema and configuration revisions are not independently keyed, so an
existing cache entry may survive such changes. Cache output MAY be deleted and regenerated.

When a normalize pass consumes engine-sensitive output, the pass and affected segment fields
MUST retain sufficient engine/model provenance to identify the consumed result.

### 4.31 Derived views

The corpus MUST compute views on demand and MUST NOT persist them in records.

| View | Result |
|---|---|
| `classifications` | `mime/*`, qualified `origin/*`, and asserted `form/*` in record order. |
| `context` | Structured context blocks. |
| `issues` | Issue projection of context. |
| `uris` | Origin URIs and `semantic_type: uri` fields, deduplicated by canonical URL identity while preserving the first spelling. |
| `timeline` | Origin snapshots and timestamp fields sorted ascending. |
| `identifiers` | Record id and identifier fields. |
| `token_counts` | Cumulative `body`, `blocks`, and `full` estimates. |
| `references` | Stored URL-tier references plus current captured-target resolution. |

TOC trees, archive trees, member indexes, URL reconciliation, and reverse-reference reports are
also derived and MUST NOT be stored as record content.

### 4.32 Export comparison

`corpus export-diff` MUST compare two producer exports without ingesting either. It reports
member identity, additions, removals, and candidate provider-field churn. It MAY classify a
source as suitable for full-strata partitioning, member-dedup-only processing, or clean direct
capture. It MUST NOT alter corpus state.

### 4.33 Artifact stores

The reference store interface MUST provide:

- canonical local path resolution;
- local and remote existence checks;
- lazy hydration;
- persistence;
- local and remote inventories.

Supported backends are local filesystem, Azure Blob Storage, and S3-compatible object storage.
The default is local-only. Cloud backends MUST use provider credential chains and MUST NOT
require credentials in corpus records or manifests.

Corpus configuration precedence is:

```text
built-in defaults -> corpus.toml -> environment overrides
```

### 4.34 Removal and garbage collection

`corpus gc` MUST preview by default and MAY age-prune resolver cache, staging debris, exports, and
artifact files with no owning record. `corpus rm` MUST also preview by default. It checks corpus
reference blocks and whether removing a container would strand promoted member records. It warns
before deleting gitignored artifact bytes; it does not query the ledger or prove re-capture
availability.

Ledger-aware retirement MUST use `ath ledger supersede <old> <new> --retire` after continuity and
citation checks. `corpus forget-origin` removes one alias and MUST refuse the record's sole origin.

### 4.35 Corpus validation

The record contract covers:

- frontmatter shape, id, hash encodings, touch grammar, and visibility;
- zone order and block syntax;
- artifact and origin cardinalities;
- members closed-row shape, hashes, types, addresses, and byte counts;
- section depth, envelopes, and form coherence;
- segment atom, body-permission, address, identity, and member linkage;
- structural mark fields;
- context namespace and anchor grammar;
- terminal-form absence of renderings;
- forbidden intra-corpus body links;
- malformed HTML residue and markdown fences;
- form-specific checks and codebook indexes;
- region grammar and bounds;
- load failures.

`corpus lint` applies parser checks and registered validation rules to a load-bearing subset of
that contract. It does not enforce every item above; notably, it does not fully check closed
frontmatter keys, filename/id equality, origin overlay resolution, member `bytes` or transport
deduplication, audio/video member linkage, or context quote occurrence. It MUST return nonzero for
reported errors and MAY return zero with warnings.

`corpus lint --resolve` MUST additionally resolve every distinct stored address, report ordinary
resolution failures and zero-byte outputs, and accept a valid text region that has no separate
byte materialization. It cannot establish that a well-formed address points at the intended
semantic region; author inspection remains required.

`corpus health` MUST report record-state counts, titles, MIME distribution, unshaped records,
issues, records lacking both standalone bytes and a declared containment route, validity
violations, and dangling origin lineage. It does not materialize declared containment routes.
Its process exit status is informational; callers MUST inspect the report.

## 5. Ledger Contract

### 5.1 Ledger root

Exactly one ledger exists per deployment. `ath ledger` requires a registered ledger root
containing `ledger.yaml`. The deployed ledger uses:

```text
ledger/
|-- ledger.yaml
|-- facts/
|   |-- SCHEMA.md
|   |-- VOCAB.md
|   `-- <type>/<id>.json
|-- schemas/<type>.yaml
|-- interpretations/
|   |-- SCHEMA.md
|   `-- <id>.json
|-- harvest/<id>.yaml
|-- invariants/<id>.yaml
|-- open-questions.md
`-- coverage.md
```

World knowledge MUST exist only in facts and interpretations. The ledger MUST NOT contain a
publication vault or independent prose knowledge base.

Shared validation does not require every listed path. Missing `facts/VOCAB.md` and
`open-questions.md` produce warnings.

### 5.2 Ledger manifest

`ledger.yaml` uses:

```yaml
name: ledger-name
description: "..."
corpora: [corpus-name, corpus-private-name]
```

`corpora` MUST be a non-empty list and every listed corpus MUST be registered in the system
manifest. `name` and `description` are optional and are not validated against the member
registration. Evidence resolution and coverage apply only to listed corpora.

### 5.3 Identity

Fact and interpretation ids MUST match:

```text
[a-z0-9]+(--?[a-z0-9]+)*
```

They share one global namespace. The filename stem MUST equal `id`. A fact's parent directory
MUST equal `type`.

An id MUST identify a real-world thing, event, relationship, or bounded edge. It MUST NOT derive
from a corpus record id. Mechanically established ids MUST derive from source-native stable
identity. `--` MAY separate pair-edge participants.

### 5.4 Concepts, edges, and redirects

A concept MAY contain:

```json
{
  "id": "concept-id",
  "type": "type",
  "name": "Display Name",
  "aliases": [],
  "meta": "author commentary",
  "sensitivity": "private",
  "period": "2026-07",
  "provenance": "auto",
  "artifacts": [],
  "sources": {},
  "claims": []
}
```

An object is an edge when it contains `subject` or `participants`; an edge MAY carry `title` in
place of `name`. Authors SHOULD provide a non-empty subject or participant list.

Concept keys are closed to `id`, `type`, `name`, `aliases`, `meta`, `sensitivity`, `period`,
`provenance`, `artifacts`, `sources`, and `claims`; a concept requires a non-empty `name`. Edge
keys are closed to `id`, `type`, `subject`, `participants`, `title`, `period`, `meta`,
`sensitivity`, `provenance`, `sources`, and `claims`.

A redirect MUST contain exactly:

```json
{"id": "old-id", "type": "type", "merged_into": "new-id"}
```

- A concept is a materialized real-world noun.
- A corpus record is evidence or an artifact of a concept and MUST NOT be the concept itself.
- A bare `{id,type,name}` concept is valid.
- A redirect target MUST exist and MUST NOT be a redirect.
- Redirects resolve one hop.
- Shared tooling validates redirect tombstones but does not perform fact merges, renames, or
  deletions.
- `meta` is author commentary and MUST NOT be treated as a claim or publication assertion.
- `sensitivity`, when asserted, MUST equal `private`.
- `provenance`, when present, MUST equal `auto`.

### 5.5 Artifact roster

Concept artifacts use:

```json
{
  "uri": "corpus://<hash>",
  "role": "documents",
  "note": "optional artifact note",
  "provenance": "auto"
}
```

- A roster entry accepts only `uri`, `role`, `note`, and `provenance`.
- `uri` MUST be a full-hash `corpus://` URI and resolve when a corpus join is available.
- `role` MUST be slug-shaped. A schema `roster_roles` declaration restricts allowed roles.
- `provenance`, when present, MUST equal `auto`.
- Roster entries contribute to sensitivity.
- Vocabulary currency is warning-only; retired roster roles are not rejected.

### 5.6 Fact schemas

A fact schema MAY declare:

```yaml
type: <type>
description: "..."
participants: [<type>, ...]
roster_roles: [<role>, ...]
fields:
  <predicate>:
    description: "..."
    target: <type> | [<type>, ...]
    values: [<value>, ...]
    expected: true
    participant: true
    timeboxed: true
    elements:
      <key>:
        description: "..."
        target: <type> | [<type>, ...]
        values: [<value>, ...]
expectations:
  - description: "..."
    when:
      <edge-type>:
        kind: [<value>, ...]
        with: <fact-id>
    expect: [<predicate>, period]
```

- Schema filename stem MUST equal `type`.
- A fact type MAY omit a schema.
- Relational objects MUST resolve to allowed target types.
- Declared value enums MUST hold.
- Structured `{"entity": "id"}` values MUST resolve whether or not a schema declares them.
- `participant: true` restricts objects to edge participants.
- Edge participants MUST satisfy declared count and positional types.
- Declared element constraints apply only to declared element keys.
- `expected`, `expectations`, and `timeboxed` produce frontier work, not invalid facts.

`fields` MUST be a mapping. A field declaration MAY be null or a mapping; `target` is a string or
list of strings, `values` is a list of strings, and `expected`, `participant`, and `timeboxed`
are booleans. `elements` maps keys to declarations with optional string-or-string-list `target`
and string-list `values`. An expectation requires a non-empty string list in `expect`; `when`,
when present, is one edge-type mapping with optional string-list `kind` and string `with`.

### 5.7 Claims

A claim MUST use this closed shape:

```json
{
  "id": "fact-id:short-id",
  "predicate": "predicate",
  "value": "value",
  "object": "other-fact-id",
  "qualifiers": {},
  "period": "2026-07",
  "status": "provisional",
  "asof": "2026-07-26",
  "reasoning": "...",
  "sensitivity": "private",
  "provenance": "auto",
  "evidence": [{"source": "s1", "kind": "direct"}]
}
```

- Claim ids MUST be globally unique and begin with their owning fact id plus `:`.
- The checker requires a non-empty predicate, an allowed status, and non-empty evidence.
- Claim atomicity is an authoring property and is not mechanically checked.
- A claim SHOULD have `value`, `object`, or both.
- A claim MUST have one or more evidence entries.
- Relational claims SHOULD use `object`.
- Authors SHOULD store a relation in one direction and SHOULD extend an existing claim with
  corroboration rather than create a semantic duplicate. The checker does not infer inverses or
  semantic duplicates.
- `reasoning` contains inference rationale and MUST NOT replace evidence.
- When present, `provenance` MUST equal `auto`; an auto claim MUST be provisional and is subject
  to removal and regeneration by harvest.

### 5.8 Time

`period` states when a claim held. `asof` states when evidence was observed.

The period grammar is:

```text
<date>   ::= YYYY | YYYY-MM | YYYY-MM-DD
<dated>  ::= <date> [THH:MM]
<period> ::= [~] <dated> | [~] <dated> "/" (".." | [~] <dated>)
```

`asof` accepts `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` only. Odd `period` and `asof` formats are
warnings.

Validation rejects qualifier keys `when`, `dates`, `year`, `period`, and `status`. It does not
detect other temporal qualifier names, enforce top-level period mirroring, or determine whether a
series should be represented as datapoints or edges.

### 5.9 Epistemic status

Allowed claim statuses are:

| Status | Authoring meaning |
|---|---|
| `confirmed` | Satisfies the authentication bar. |
| `provisional` | One non-authoritative source states the claim directly. |
| `inferred` | Deduced from evidence; authors SHOULD provide `reasoning`. |
| `reported` | A named voice asserts it; `qualifiers.attribution` is required. |
| `disputed` | A standing correction challenges it. |
| `conflicting` | Independent sources disagree and all evidence is retained. |

Every status is asserted knowledge. Suspicion or conjecture MUST be an interpretation.

Only the confirmed bar, status vocabulary, reported attribution, and disputed/challenge pairing
are mechanically enforced.

A confirmed claim MUST carry at least one `authoritative` evidence entry or evidence from at
least two distinct corpus record hashes. The checker additionally enforces status vocabulary,
reported attribution, and disputed/challenge pairing.

### 5.10 Sources table

Each fact MAY contain:

```json
"sources": {
  "s1": {
    "record": "<64-lowercase-blake3>",
    "verified": {
      "touch": "<latest-touch>",
      "at": "2026-07-26",
      "ops": {"path": "archive-path@1"}
    }
  },
  "s2": {"ref": "dataset/native-id"}
}
```

Source keys MUST match `[a-z][a-z0-9-]{0,31}` and are local to the fact. A source entry MUST
contain exactly one of `record` or `ref`. A `record` target MUST be 64 lowercase hexadecimal
characters. A `ref` target MUST match `<dataset>/<native-id>` and name a registered dataset. The
same target MUST appear at most once in a fact. Every `evidence.source` MUST resolve in its owning
fact. An unused source is a warning.

`verified` is an open implementation-owned object. `ath ledger verify --stamp` writes `touch`,
optional `at`, and optional `ops`; validation does not reject additional binding keys.

### 5.11 Evidence

Claim evidence MUST use:

```json
{
  "source": "s1",
  "anchor": "page=2&bbox=0.1,0.1,0.8,0.2",
  "quote": "verbatim text",
  "note": "artifact note",
  "kind": "direct"
}
```

Allowed kinds are:

| Kind | Contract |
|---|---|
| `authoritative` | The artifact's function is to certify the cited datum. |
| `direct` | A direct first-party or first-hand statement. |
| `incidental` | A passing mention, background fact, or normalizer-authored reading. |

- `source` is required.
- `anchor` is optional and MUST omit a leading `?`.
- `quote` is optional and MUST be verbatim from the resolved textual surface under the
  verifier's normalization.
- Paraphrase MUST be in `note` or claim `reasoning`.
- A non-textual anchor MAY omit `quote`.
- Authors SHOULD classify normalizer-authored descriptions as `incidental`.
- Authors MUST anchor no more precisely than they have verified.

Stored-markdown quote comparison decodes HTML entities, folds typographic quotes, unwraps
markdown links, removes inline markup, converts structural HTML and table separators to spacing,
and collapses whitespace. `...`, Unicode ellipsis (`U+2026`), and `|` split a quote into ordered
fragments. A second comparison removes whitespace and hyphens. Resolver-derived text is compared
without markdown/HTML stripping.

Derived citations are:

```text
corpus://<record>
corpus://<record>?<anchor>
ref://<dataset>/<native-id>
```

### 5.12 Citation surfaces

Citable corpus surfaces are:

- a stored rendering under a named form;
- a mechanical resolver derivation;
- authored body prose carried by text segments;
- section and segment descriptions, entries, and titles;
- derived display title and description;
- string-valued origin fields.

Citability MUST NOT depend on corpus record state.

- A `raw` MIME MAY be cited record-wide when the verifier has a textual record surface. The
  verifier does not load an unsegmented raw artifact for a bare, unanchored quote.
- A `segments` MIME with no persisted segments MUST NOT be used as claim evidence.
- That violation is an error at every claim status.
- An interpretation MAY reference such a record and SHOULD carry an `enqueue` or `promote`
  need.
- Ledger verification does not inspect terminal state. It uses the MIME citation-surface class,
  persisted record text, and resolver fallback.

### 5.13 Evidence verification and binding

Verification MUST resolve registered corpus targets and compare quotes under the verifier's
normalization. Stored integer segment anchors are checked against their addressed span. For a
compound anchor, stored-text verification returns after classifying the first parameter; later
parameters are not independently checked unless resolver fallback runs. Other axes MAY verify a
quote record-wide and are reported as record-scoped when their address cannot be scoped.

Resolver fallback runs only for an unchecked anchor carrying a quote absent from record-wide
stored text. An unchecked unquoted anchor is unverifiable without materialization. If functional
URI parsing fails, verification falls back to full-record text with no parameters and may count a
matching quote as verified without labeling it record-scoped.

Passing corpus sources MAY be bound to current touch and used resolver engine pins. Touch or
engine movement MUST flag the binding for re-verification.

The binding is one per fact/source. A source may be stamped only when every evidence entry using
it passes. Re-stamping MUST NOT rewrite a binding solely because the verification date changed.

Shared tooling has no reference-content adapter registry. Registered `ref://` evidence is
structurally valid and MUST be reported as unverifiable rather than verified.

When the corpus join is incomplete, `ath ledger verify` skips verification, emits a note, and
returns success without stamping.

Evidence verification failures are errors for confirmed claims and warnings for other asserted
statuses, except citation-surface violations, which are always errors.

### 5.14 Sensitivity

- A corpus hash is private iff it resolves only in private corpora.
- A hash resolving in any public corpus is public evidence.
- Registered reference datasets are public.
- A claim is private-backed iff any evidence is private or the claim asserts
  `sensitivity: private`.
- A roster entry inherits the sensitivity of its corpus URI.
- A fact is fully private iff it asserts `sensitivity: private`, or it carries at least one
  claim or roster entry and every carried item is private.
- A mixed-sensitivity fact remains one file.
- A bare stub is not private unless explicitly marked.
- Sensitivity gates nothing inside the ledger.

### 5.15 Interpretations

An interpretation MUST use:

```json
{
  "id": "interpretation-id",
  "kind": "hypothesis",
  "about": ["fact-id"],
  "statement": "...",
  "confidence": "plausible",
  "reasoning": "...",
  "based_on": ["corpus://<hash>"],
  "status": "open",
  "asof": "2026-07-26"
}
```

Kinds are `hypothesis`, `assessment`, and `correction`.

- One interpretation MUST contain one checkable statement.
- `about` ids MUST resolve.
- `based_on` MUST be non-empty and MAY contain corpus URIs, reference URIs, or claim ids.
- Hypothesis confidence is `speculative`, `plausible`, or `likely`.
- A claim-shaped hypothesis MAY carry `proposes`. It uses the claim key set except `status`,
  requires a claim id and predicate, and MAY carry claim-level sensitivity or auto provenance.
  Proposed evidence uses inline `uri` instead of `source` until promotion builds a target sources
  table.
- A correction MAY challenge a claim. An unstamped challenge is a warning.
- `would_resolve`, `proposes`, `challenges`, `needs`, and `resolution` are optional and
  kind-specific.

Allowed needs are:

```json
{"action": "enqueue", "record": "corpus://<hash>", "why": "..."}
```

`action` is one of `enqueue`, `search`, `capture`, `observe`, or `promote`. Every need MUST carry
`why`. `enqueue` MUST carry a syntactically valid corpus URI. The checker accepts `promote` when
the URI has a non-empty query or fragment suffix; promotion may later fail when that suffix does
not resolve member bytes. Other actions MAY omit `record`.

Lifecycle is:

```text
hypothesis: open -> promoted | refuted
assessment: standing -> retired
correction: standing -> retired
```

`promoted` and `refuted` require `resolution`; `retired` does not. Promotion MUST materialize the
proposed claim, convert its source URIs into the fact's sources table, assign supported status,
and record the landed claim id.

Interpretation sensitivity is private when any `based_on` corpus URI is private, any referenced
claim is private-backed, or sensitivity cannot be derived. Non-private codex profiles MUST omit
such interpretations.

### 5.16 Challenge pins

A challenge requires `claim` and MAY contain `state`:

```json
{"claim": "fact-id:claim-id", "state": "blake3:<64-lowercase-hex>"}
```

Missing `state` warns. A present state MUST match the shown grammar.

The state hash MUST be BLAKE3 over canonical claim JSON with sorted keys, minimal separators,
UTF-8 encoding, `status` excluded, evidence source keys replaced by derived citation URIs, and
source verification bindings excluded. Claim changes beyond status MUST flag the correction for
review.

### 5.17 Vocabulary and frontier

`ath ledger regen` generates `facts/VOCAB.md` from every fact type, edge type, predicate,
qualifier key, and roster role in use while preserving definitions and retired-term entries.
Authors MUST NOT use retired vocabulary.

Validation rejects retired predicates and qualifier keys. Retired fact types, edge types, and
roster roles remain reportable in the registry but are not mechanically rejected.

The same command generates a tooling-owned block in `open-questions.md` covering:

- open hypotheses;
- standing assessments and corrections;
- their needs;
- claimless and rosterless stubs;
- expected fields not yet asserted;
- unmet conditional expectations;
- missing required timeboxes.

Frontier findings MUST NOT make fact validation fail.
`check` warns when the vocabulary or work-list output is missing or stale.

### 5.18 Coverage

`ath ledger regen --coverage` generates aggregate represented/total counts for every corpus named
by `ledger.yaml`. A record counts as represented when its
hash appears anywhere in ledger fact or interpretation JSON or in a source entry. Explicit
out-of-scope state and a record-level backlog are not represented. Coverage is independent of
sensitivity and codex scope. `ath ledger check` does not validate coverage presence or currency.

### 5.19 Harvest

Harvest rules under `harvest/` MAY deterministically mint auto-provenance concepts, roster
entries, and provisional claims from mechanical corpus facts.

A harvest rule uses:

```yaml
id: rule-id
description: "..."
match: {}
mint:
  concept: {id: "...{origin.field}...", type: type, name: "..."}
  roster: []
  claims: []
```

The closed top-level keys are `id`, `description`, `match`, and `mint`; mint keys are `concept`,
`roster`, and `claims`. A concept declaration accepts only `id`, `type`, and `name`.

A roster item reads `role`, defaulting to `documents`; additional roster item keys are not
validated. A claim item reads `predicate`, templated `value`, and optional `evidence_kind`.
Harvest does not mint claim `object` fields or `qualifiers`. Before sweeping, harvest deletes
auto-provenance fact files and strips auto roster and claim entries from surviving files. A
concept id template MUST contain an interpolation and every id interpolation key MUST begin with
`origin.`.

Allowed match operators are:

```text
equals
in
glob
matches
exists
all_of
any_of
none_of
```

Harvest MUST NOT inspect authored body content or use an LLM, network, or clock. Eligible facts
are MIME, origin id/subtype, stored origin fields, and decomposed origin URI host, path,
fragment, and query values.

A harvested concept id MUST derive from an interpolated origin fact and MUST NOT derive from a
record hash. Auto output MUST carry `provenance: auto`. Harvested claims MUST NOT exceed
provisional status.

### 5.20 Invariants

An invariant MUST be declared as data under `invariants/` and MUST use one supported constraint:

```yaml
id: invariant-id
description: "..."
applies_to: {type: type, predicate: predicate}
constraint: unique
severity: error
```

Constraint-specific optional keys are `per`, `set`, `requires`, `min`, and `max`.

| Constraint | Contract |
|---|---|
| `unique` | At most one matching claim, optionally per qualifier. |
| `exclusive` | At most one member of a declared predicate/value set. |
| `temporal-no-overlap` | Matching periods do not overlap. |
| `requires` | One claim implies another predicate. |
| `cardinality` | Matching claim count remains within bounds. |

The loader validates top-level keys, id/filename equality, constraint, severity, and that
`applies_to` is a mapping. Constraint-specific option types are not prevalidated and malformed
values may fail during evaluation. `severity` MAY be `error` or `warning` and defaults to
`error`. `unique`, `exclusive`, and `temporal-no-overlap` diagnostics identify exact claims.
`requires` and `cardinality` diagnostics identify the affected fact. Shared tooling emits
findings but does not apply resolutions or waivers.

### 5.21 Ledger URIs

The following ledger identifiers are reserved external syntax:

```text
ledger://<fact-or-interpretation-id>
ledger://<fact-id>:<claim-short-id>
```

Shared tooling does not parse or resolve `ledger://`. `ath ledger worklist` instead
accepts a bare fact id, corpus hash, or invariant id. Generated views and codex notes MUST NOT be
ledger URI targets.

### 5.22 Supersession

`ath ledger supersede <old> <new>` operates only when both records resolve in the same corpus and
MUST rewrite a fact citation only when continuity proves the addressed content is identical or
contained in the successor.

- Preserved anchors remain unchanged.
- A `path=` citation uses the addressed member's continuity verdict. Every other citation tail is
  judged by whole-record containment.
- If all evidence on a source is preserved, the source record may be rewritten in place.
- If preservation is mixed, the source entry MUST split.
- Diverged evidence MUST remain on the old record and be reported.
- Roster entries follow the same preservation rule.
- The command scans `facts/*/*.json`, including claims, sources, and artifact rosters. It does not
  scan interpretations or needs.
- A source rewritten in place retains its existing verification binding.
- `--retire` refuses only when a divergence found in scanned facts remains; otherwise it removes
  the old corpus record and bytes.

### 5.23 Ledger validation

`ath ledger check` MUST validate:

- fact and interpretation JSON parseability and schema/invariant YAML parseability;
- closed shapes and path/id/type equality;
- global identity and claim-id uniqueness;
- concept, edge, redirect, claim, source, evidence, and interpretation grammar;
- graph references, entities, participants, objects, `about`, `based_on`, and challenges;
- status vocabulary, reported attribution, dispute pairing, and the confirmed authentication
  bar;
- sensitivity derivation when corpus access is available;
- schema constraints and frontier generation;
- top-level invariant shape and invariant evaluation;
- retired predicates and qualifier keys;
- generated vocabulary and work-list currency.

`ath ledger verify` is a separate evidence-content gate with the behavior in section 5.13. It
MUST write no durable changes unless `--stamp` is supplied.

The repository operating procedure MUST run both `check` and `verify` for evidence changes.
Shared tooling does not intercept Git commits. Warnings and unverifiable evidence do not change
the process exit status unless an error is also present.

## 6. Codex Contract

### 6.1 Codex root

`ath codex` requires `codex.yaml`. `check` additionally requires `notes/`. `build` creates
`build/<profile>/content/` and `certificates/` as needed. The deployed layout is:

```text
codex-name/
|-- codex.yaml
|-- notes/                    # tracked generated vault
|-- certificates/             # tracked build receipts
|-- build/                    # ignored renderer-ready output
`-- site/                     # optional ignored renderer checkout/output
```

`site/` is optional and unused by shared tooling. A codex MUST NOT contain facts or
interpretations. Codex-specific prose MUST derive from the ledger and MUST NOT become an
independent knowledge store. Shared tooling does not scan the repository for violations of this
content policy.

A registered codex without `codex.yaml` participates in `ath status` and `ath sync`, but every
`ath codex` operation on it MUST fail as a setup error. Such a member does not conform to this
codex contract.

### 6.2 Codex manifest

`codex.yaml` uses:

```yaml
name: codex-name
display_name: "Display Name"
description: "..."

scope:
  types: [type]
  roots: [fact-id]
  traverse_types: [type]
  tags: []
  exclude: [fact-id]

profiles:
  public:
    redact: exclude
```

- `types` and `roots` are additive selectors.
- `types` selects every ledger fact of each listed type globally.
- `roots` seed graph traversal.
- `traverse_types` bounds traversal; if omitted, `types` is the bound.
- `exclude` removes selected facts after traversal.
- `tags` MUST be accepted and ignored by the scope engine.
- `private` is implicit and unrestricted.
- Every non-private profile MUST be declared.
- `redact` is `exclude` or `stub` and defaults to `exclude`.

`name`, `display_name`, and `description` MAY be omitted. They default from the codex directory
and name; description defaults to empty. Unknown manifest, scope, and profile keys are ignored.
Scope selectors MUST be lists and their members are coerced to strings. If `traverse_types` and
`types` are both empty, traversal is unbounded. `profiles` and each profile value are assumed to
be mappings; malformed values may raise an unstructured exception.

### 6.3 Scope materialization

Scope materialization MUST:

1. load live facts and one-hop redirects;
2. select every fact matching `types`;
3. resolve and select every root;
4. traverse transitively in both directions within the traversal bound, following claim objects,
   structured entity values, edge subjects, and edge participants;
5. include incoming facts whose claim references target selected facts and edges intersecting the
   selected scope;
6. apply exclusions;
7. include interpretations whose `about` intersects the resulting fact scope;
8. return the exact facts and interpretations used by note generation.

Redirects MUST be followed. Excludes are applied as literal live ids and are not
redirect-resolved. Unknown excludes are ignored. Scope materialization reports unknown roots and
malformed ledger files as problems. `scope` and `notes` print those problems as warnings and
return success; `check` treats them as errors. `build` retains unknown-root problems and drops
other materialization problems.

Exclusion does not recompute traversal closure. Facts reached through an excluded node remain
selected unless separately excluded.

### 6.4 Generated notes

The default note generator MUST create one Obsidian-flavored markdown note per selected fact at:

```text
notes/<fact-type>/<fact-id>.md
```

Each note MUST carry:

```yaml
---
concept: <fact-id>
generated_from:
  - ledger/facts/<type>/<fact-id>.json
updated: YYYY-MM-DD
---
```

`generated_from` MUST contain the fact path followed by one path for each rendered associated
interpretation; zero interpretation paths are valid.

The generated note MUST:

- identify the fact;
- render selected claims and their epistemic status;
- render qualifiers, the first available value of `period` then `asof`, and reasoning;
- carry evidence as `corpus://` or `ref://` footnotes;
- add an evidence-gallery embed for a citation containing `page=`, `bbox=`, or `frame=`; other
  functional anchors remain footnotes;
- render artifact roster entries;
- visibly distinguish interpretations from asserted claims;
- use vault wikilinks for live in-scope claim `object` references and edge participants;
  redirects and out-of-scope references render as plain text or privacy markers, and structured
  `{"entity": "id"}` values render as plain text;
- list the note's fact file and rendered associated interpretation files in `generated_from`;
- contain no assertion absent from its generated sources.

`ath codex <name> notes` MUST replace the tracked private-profile notes with fresh generated
notes. Hand drift from generated output is invalid.

### 6.5 Profiles

The private profile renders every selected claim, interpretation, roster entry, and fact. Every
non-private profile is publication-filtered and receives the non-private leak check.

A non-private profile MUST:

- remove private-backed roster entries and, under `exclude`, remove private-backed claims;
- remove interpretations derived from private or underivable bases;
- redact private claim-object and edge-member links; structured entity values are not
  independently filtered and the leak scan may catch a private id afterward;
- omit fully private facts under `exclude`;
- under `stub`, replace a private claim's value and evidence with a marker while retaining its
  predicate;
- under `stub`, write a fully private fact marker retaining the fact id in its path and
  frontmatter; the leak check therefore makes that non-private build fail;
- refuse private raster assets;
- fail closed when any registered corpus required for sensitivity is unavailable.

A well-formed unresolved corpus hash is private for filtering purposes. A malformed source or
roster entry may produce no derived corpus URI and is treated as public by profile generation.
`ath codex build` does not invoke `ath ledger check`; the operating gate runs ledger validation
separately.

### 6.6 Build

`ath codex <name> build [--profile <profile>]` defaults to `private` and MUST produce:

```text
build/<profile>/content/
|-- index.md
|-- <fact-type>/<fact-id>.md
`-- assets/<derived-asset>
```

The reference build materializes scope and generates profile notes in memory. It MUST:

1. validate the requested profile;
2. require a complete corpus join;
3. generate the profile's note set;
4. replace the profile content tree;
5. resolve corpus citations to human-readable record titles while retaining the URI;
6. raster supported visual functional-URI evidence into local assets;
7. preserve vault wikilinks for the downstream renderer;
8. write the codex index;
9. run the non-private leak check for non-private profiles;
10. emit a build certificate;
11. return failure when any retained scope-root, resolution, raster, or leak problem exists.

For non-embedded citations, build verifies record existence and derives a title but does not
resolve the functional anchor. Embedded citations pass through the corpus resolver. `ref://`
footnotes pass through unresolved and are not added to certificate snapshots. The shared build
does not validate the complete ledger grammar before generating output.

A build with retained problems still writes generated content and a certificate. A failed
citation or raster substitution remains in its original textual form. The command then returns
nonzero.

The build output is renderer-ready markdown, not the final rendered site. Renderer execution and
deployment are outside the shared build command.

Consumers MUST use process exit status, not certificate presence, to determine build success.

### 6.7 Non-private leak check

The leak check MUST scan every generated `.md` file for lowercase 64-hex substrings and treat each
as a possible corpus hash; unresolved or private-only hashes fail. It also performs substring
matching for every fully private scoped fact id. Profile filtering removes items derived as
private, while the leak scan catches private hashes or ids that remain in otherwise public
content. Under `stub`, section 6.5 applies and the leak check MAY reject the output. The shared
check scans only the renderer-ready content tree and does not inspect downstream renderer output.

### 6.8 Build certificate

A build certificate MUST be written under:

```text
certificates/<profile>-<ledger-commit-first-8>-<codex-commit-first-8>.json
```

It MUST contain:

```json
{
  "codex": "codex-name",
  "profile": "profile",
  "codex_commit": "git-commit",
  "ledger_commit": "git-commit",
  "corpus_touches": {"record-hash": "latest-touch"},
  "reference_snapshots": {},
  "tool": "athenaeum@version",
  "built": "YYYY-MM-DD",
  "notes": 0,
  "rastered": 0
}
```

`corpus_touches` MUST include every cited or rastered corpus record encountered by the build.
`reference_snapshots` MUST be empty. Shared builds MUST NOT claim reference-mirror resolution or
snapshot certification. Certificates are receipts and MUST NOT be used as mutable working state.

Each commit field is the repository's current `HEAD`, or `unversioned` when Git resolution fails.
Certificate filenames use the first eight characters of that value. Working-tree dirtiness is
not recorded or rejected.

### 6.9 Codex validation

`ath codex <name> check` MUST:

- load the codex manifest;
- resolve the ledger and declared corpora;
- materialize scope and report missing roots or malformed ledger inputs;
- require a complete corpus join;
- generate the current private note set;
- report missing, stale, extra, or orphan notes;
- compare generated note content while ignoring every line matching `^updated: .*$`;
- return nonzero for any error.

Shared tooling exposes `check` and non-private `build` as separate commands; it does not implement
a release command. The publication operating gate requires both applicable validations.

## 7. Agents And Operations

### 7.1 Roles

The deployment recognizes these roles:

| Role | Authority |
|---|---|
| Owner | Specification direction, architecture, naming, corpus content and capture decisions, codex topology, taste, publication, destructive action, operating autonomy, and Forge/tailnet infrastructure |
| Orchestrator | Specs, tooling, cross-member coherence, member health, dispatch, review, and commits |
| Normalizer | Faithful corpus form and descriptions for one assigned corpus |
| Overlay author | Web-origin capture overlay authoring and authorized capture verification |
| Ledger scribe | Evidence-backed fact and interpretation authoring |

The deployment MUST have exactly one resident orchestrator persona. Members MUST NOT carry
resident personas. The orchestrator MAY dispatch scoped normalizer, overlay-author, and
ledger-scribe workers. Authored codex synthesis is an optional extension, not a reference worker;
its output MUST pass the deterministic profile, build, and leak gates.

### 7.2 Agent boundaries

- A normalizer dispatch MUST name exactly one corpus root.
- A normalizer MUST NOT read or write a sibling corpus.
- A normalizer MUST NOT run Git or modify queue state.
- A normalizer MUST edit records through decompose/edit/compile rather than direct markdown
  mutation.
- Corpus tooling MUST NOT invoke an agent. For queue-backed work, the external orchestrator MUST
  claim, dispatch, review, and finalize each authored pass. Explicit-set passes bypass queue
  mutation, MUST receive disjoint record sets, and MUST run the same record gates.
- An overlay-author dispatch MUST state whether durable external captures are authorized.
  Without authorization, overlay work MUST NOT perform durable ingest and MUST clean staging
  before stopping.
- A ledger author MUST cite corpus or reference evidence and MUST NOT use model knowledge as
  evidence.
- Parallel ledger investigation MAY produce reports, but durable assertion into one ledger MUST
  use one serialized writer.
- Agent workers MUST NOT commit; the orchestrator reviews and commits.

Deployments requiring process-level isolation SHOULD restrict filesystem and network access
accordingly.

### 7.3 Parse tolerance

Corpus-wide readers skip malformed records rather than abort an entire scan; the shared iterator
does not itself report each skipped path. Strict lint MUST report malformed records as errors.
Schema and local-extension load failures SHOULD be reported and skipped during tolerant reads.

Ledger checking reports malformed fact and interpretation JSON and schema/invariant YAML. Codex
scope materialization reports malformed fact and interpretation JSON. Malformed `ledger.yaml` or
`codex.yaml` may escape structured command error handling.

Assembly and other completeness-critical bundling operations MUST abort on unreadable input.

### 7.4 Concurrency

- Queue claims MUST use atomic same-directory rename or an equivalent atomic primitive.
- Parallel normalizers MUST claim disjoint records or receive explicit disjoint sets.
- A presence check is not a lock.
- A queue drain and an explicit-set pass MUST NOT process the same records concurrently.
- Shared Git-index repositories MUST inspect staged content immediately before commit.
- One commit MUST contain only the intended repository's reviewed changes.

### 7.5 Authorization

The following actions require owner authorization:

- external capture;
- artifact or record deletion;
- forced replacement or irreversible cleanup;
- destructive Git operations;
- publication;
- changes to normative specification content;
- record-format or corpus-contract changes capable of invalidating existing data;
- infrastructure mutation by an operating agent;
- exposure of private-derived content to a public audience.

Tooling capability MUST NOT establish or imply user authorization.

### 7.6 External dependencies

Dependencies apply only to operations that require them:

| Operation | External dependency |
|---|---|
| Required runtime | Python 3.14+ and Git |
| Reference installation and test runner | `uv` |
| Browser capture | Playwright and Chromium |
| Logged-in capture | Chrome-compatible CDP endpoint |
| Self-contained web snapshots | SingleFile bundle |
| Media probe, render, cut, and convert | `ffprobe`, `ffmpeg` |
| yt-dlp JavaScript challenges | Node.js 18+ and the configured remote EJS component |
| Audio fingerprinting | `fpcalc`/Chromaprint |
| Remote session capture | SSH and rsync, with SCP fallback |
| HTTP transcription | Configured Whisper-compatible service |
| Azure or S3 storage | Corresponding optional SDK and provider credentials |

Optional Python installation profiles are `capture`, `media`, `office`, `fingerprint`, `azure`,
`s3`, `crypto`, `claude-session`, and `tokens`. Network access is operation-specific and MAY be
required for member sync, browser or media capture, remote stores, remote sessions, and HTTP
transcription.

### 7.7 Repository gates

Before committing changes, the responsible operator MUST run the applicable gates:

| Repository | Required gate |
|---|---|
| Shared tools | Full pytest suite and Ruff |
| Corpus records or schemas | Full record lint; `--resolve` for authored addresses; health inspection |
| Ledger facts or interpretations | `ath ledger check`; `ath ledger verify` for evidence changes |
| Codex notes or manifest | `ath codex <name> check` |
| Non-private codex release | Successful non-private build and leak check |

Warnings SHOULD be cleared unless their acceptance is documented in durable project state.

### 7.8 Command surface

The reference distribution MUST expose:

```text
ath status
ath sync [--pull]
ath corpus <corpus-command>

ath ledger check [--no-corpus]
ath ledger verify [<fact-id> ...] [--stamp]
ath ledger harvest
ath ledger promote <interpretation-id>
ath ledger stamp <interpretation-id>
ath ledger supersede <old> <new> [--retire]
ath ledger worklist <reference>
ath ledger regen [--coverage]

ath codex <name> scope
ath codex <name> notes
ath codex <name> build [--profile <profile>]
ath codex <name> check
```

Each ledger and codex command accepts `--root` after the command name. Codex build defaults to the
`private` profile.

The `corpus` and `ath corpus` command surfaces MUST expose the same registered verbs:

```text
init
capture session check ingest promote assemble mbox-split mbox-window period-split export-diff
draft resolve re-stub reattest redraft
shape enqueue drain finalize release await queue
crawl links
inspect show diagnose guidance workflow overlay preview view toc body lint health
decompose compile
store
gc rm forget-origin continuity
find atoms hosts schemas
```

`draft` and `redraft` MUST perform no drafting operation; they MUST return status 2 with
replacement guidance. Packaged operating modes MUST be available through `corpus workflow
<name>`.

### 7.9 Exit behavior

- Lint and ledger/codex validation commands MUST return nonzero on errors.
- Warnings alone MAY return zero.
- `corpus drain` MUST return status 1 for an empty or timed-out queue.
- `corpus finalize` MUST leave the claim in `claimed` state when the pass gate fails.
- `corpus health` is a report and MAY return zero despite findings.
- Codex certificate creation does not override build failure.
- `ath status` MUST return status 1 when any repository is missing.
- `ath ledger supersede` MUST return status 1 for surviving divergences and status 2 for failed
  preconditions.
- `corpus check` returns status 0 when captured, 1 when not captured, 2 for usage errors, and 3
  for resolution errors.
- `corpus draft` and `corpus redraft` return status 2.
- Caught setup, manifest, profile, and incomplete-join failures MUST return status 2; content
  validation failures return status 1.

## 8. Change Management

### 8.1 Specification-first changes

- Shared tooling and member contracts MUST conform to the governing specifications.
- A behavior requiring an uncovered contract MUST receive an approved specification amendment
  before implementation begins.
- Every corpus data-contract amendment MUST include a migration or compatibility strategy for
  all existing records.
- An amendment MUST sweep implementation enforcement, tests, schemas, runbooks, workflows,
  agent instructions, and other guidance sites that encode the changed contract.
- A change MUST NOT land a transitional repository state that fails the applicable gate.
- Backward-compatibility behavior MUST have a concrete persisted-data, shipped-behavior, or
  external-consumer requirement.

### 8.2 Repository changes

- Each repository MUST pass its section 7.7 gate before its change is committed.
- Cross-repository changes MUST leave every affected repository on a coherent contract boundary.
- A commit MUST include only reviewed changes intended for that repository.
- Destructive rewrites and incompatible corpus migrations require owner authorization.

## 9. Institutional Memory

- Specifications define data and behavior contracts.
- Runbooks define current operating procedures.
- Packaged `corpus workflow` content defines tooling operating modes.
- `state.md` records the current position, in-progress work, and technical debt.
- `logbook.md` records history, decisions, and rationale.
- `gotchas.md` records recurring operational hazards and fixes.
- `proposals.md` records non-normative parked work and MUST NOT be treated as implemented state.
- None of these references may override a governing specification.
- Session auto-memory MUST NOT override these tracked sources.
- Superseded narrative MUST remain available through Git history or tags rather than in the
  current prescriptive contract.
- A session operating from the orchestrator repository MUST complete the orchestrator skill's
  initialization sequence before system work: read root guidance, anchor specification versions,
  load tracked references, sweep members, and run corpus health when corpus work is in scope.
- Meaningful work MUST update state, logbook, and gotchas at the triggers defined by the
  orchestrator skill.

## 10. Exclusions

This specification does not define:

- OCR generation by the shared package, including automatic PDF OCR selection;
- SQLite row/query addressing;
- PDF page-range syntax such as `page=N-M`;
- a portable corpus-wide member-hash query API;
- general single-record export, whole-corpus export, or non-markdown export;
- semantic types beyond the closed corpus vocabulary;
- recursive dependent capture beyond depth one;
- a network serving protocol;
- multi-corpus capture in one invocation;
- a final static-site renderer or deployment protocol;
- a general non-tenancy codex profile predicate language;
- functional behavior for codex tags without a ledger tag model;
- reference mirror-content resolution, adapter registration, and snapshot verification;
- a standalone external `ledger://` network resolver;
- SVG rasterization.

Unsupported surfaces MUST fail explicitly or remain inert. They MUST NOT be inferred from
similar supported operations.
