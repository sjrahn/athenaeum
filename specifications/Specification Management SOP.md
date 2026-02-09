---
spec_id: ATH-SOP-SPECMGMT
title: "Specification Management SOP"
version: 1.0
status: draft
author: Steven Rahn
date_created: 2026-02-09
date_modified: 2026-02-09
changelog:
  - version: 1.0
    date: 2026-02-09
    summary: "Initial SOP"
---

## 1. Purpose

This Standard Operating Procedure governs how specifications within the Athenaeum project are created, versioned, amended, and retired. It ensures that architectural decisions and system designs remain traceable, reviewable, and authoritative over time.

All specifications live under `specifications/` and follow the conventions described here.

## 2. Specification Lifecycle

Every specification progresses through a defined lifecycle:

```
draft ──▶ final ──▶ (addenda) ──▶ new version (draft → final)
                 └──▶ superseded (if replaced by a different spec)
```

### 2.1 Draft

The specification is actively being written or revised. It is **not authoritative** — content may change at any time. Edits are made directly to the document.

A draft spec should not be referenced as a source of truth by other documents or implementations.

### 2.2 Final

The specification's content is **frozen**. It represents an authoritative, point-in-time decision record. Direct edits are no longer permitted — all changes must go through the addendum process (see §6).

Finalizing a spec is an explicit action (see §5) that includes setting the status, committing, and tagging the commit.

### 2.3 Superseded

A specification is marked `superseded` only when it is **replaced by a different specification** — for example, when a spec is split into two separate specs, or when the scope changes so fundamentally that a new spec ID is warranted. Normal version increments (1.0 → 2.0) do **not** use `superseded`.

## 3. Versioning

Specifications use a **Major.Minor** versioning scheme.

### 3.1 Minor Version (e.g., 1.0 → 1.1)

A minor bump indicates:
- Incorporation of one or more addenda
- Clarifications or refinements that don't change the fundamental architecture
- Corrections of errors in the spec text

### 3.2 Major Version (e.g., 1.x → 2.0)

A major bump indicates:
- Significant structural or architectural changes
- New architectural decisions that alter the system's design
- Removal or replacement of major components
- Changes to fundamental invariants or guarantees

### 3.3 What Doesn't Bump Versions

Typo fixes, grammar corrections, and formatting changes do not warrant a version bump. These are tracked through git commits alone.

## 4. Creating a New Specification

1. Choose a **spec ID**: `ATH-` prefix followed by a short mnemonic slug (e.g., `ATH-ARCH`, `ATH-INGEST`, `ATH-SOP-SPECMGMT`).
2. Create the file under `specifications/` with the title as the filename.
3. Add YAML frontmatter using the template in §10.1.
4. Set `status: draft` and `version: 1.0`.
5. Write the specification body below the frontmatter.
6. Commit with a message like: `Add draft spec ATH-XXXX: <title>`

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec_id` | string | yes | Short stable ID (`ATH-` prefix + mnemonic slug) |
| `title` | string | yes | Human-readable title |
| `version` | Major.Minor | yes | Current version number |
| `status` | enum | yes | `draft`, `final`, or `superseded` |
| `author` | string | yes | Primary author |
| `date_created` | date | yes | When the spec was first written |
| `date_modified` | date | yes | When this version was last touched |
| `supersedes` | version | no | Previous version, if this spec replaces another |
| `addenda_incorporated` | string[] | no | Addendum IDs merged into this version |
| `changelog` | array | yes | Entries with `version`, `date`, `summary` |

**File naming convention:** The file is named by its title. Versions are **not** encoded in the filename — the file always represents the current version, and git tracks history.

## 5. Finalizing a Specification

When a draft is ready to become authoritative:

1. Set `status: final` in the frontmatter.
2. Update `date_modified` to the current date.
3. Commit with a message like: `Finalize spec ATH-XXXX v1.0`
4. Tag the commit:
   ```
   git tag spec/{spec_id}/v{Major.Minor}
   ```
   Example: `git tag spec/ATH-ARCH/v1.0`

From this point forward, the spec's content is frozen. Changes require an addendum.

## 6. Filing an Addendum

Addenda are the mechanism for proposing changes to finalized specifications. Each addendum is a standalone document that describes a specific change.

### 6.1 When to File an Addendum

File an addendum when:
- A finalized spec needs a correction, clarification, or addition
- A component or pattern described in a spec is being deprecated
- Implementation experience reveals the spec needs updating

Do **not** file an addendum for:
- Draft specs (edit them directly)
- Typo/grammar fixes (commit directly with a note in the commit message)

### 6.2 Naming Convention

Addenda are stored in `specifications/addenda/` and named:

```
{spec_id}-A{NNN}.md
```

The sequence number `{NNN}` is zero-padded to three digits and increments per parent spec. Examples:
- `ATH-ARCH-A001.md` — first addendum to ATH-ARCH
- `ATH-ARCH-A002.md` — second addendum to ATH-ARCH
- `ATH-INGEST-A001.md` — first addendum to ATH-INGEST

### 6.3 Addendum Frontmatter

```yaml
---
addendum_id: ATH-ARCH-A001
parent_spec: ATH-ARCH
parent_version: 1.0
title: "Clarify tag inheritance behavior"
type: clarification
status: pending
author: Steven Rahn
date_created: 2026-02-10
sections_affected:
  - "3.2.2 Tags"
incorporation_target: ~
---
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `addendum_id` | string | yes | Unique ID: `{spec_id}-A{NNN}` |
| `parent_spec` | string | yes | The `spec_id` this addendum applies to |
| `parent_version` | Major.Minor | yes | The spec version this addendum was written against |
| `title` | string | yes | Brief description of the change |
| `type` | enum | yes | `correction`, `addition`, `clarification`, or `deprecation` |
| `status` | enum | yes | `pending`, `incorporated`, or `withdrawn` |
| `author` | string | yes | Who wrote the addendum |
| `date_created` | date | yes | When the addendum was filed |
| `sections_affected` | string[] | yes | Which spec sections are impacted |
| `incorporation_target` | version/null | no | The spec version that will include this change (`~` until known) |

**Addendum types:**
- **correction** — Fixes an error in the spec
- **addition** — Adds new content (a new section, new component, new behavior)
- **clarification** — Makes existing content clearer without changing its meaning
- **deprecation** — Marks a component, pattern, or section as deprecated

### 6.4 Addendum Body Structure

The body of an addendum follows this structure:

**Context** — Why this addendum is needed. Reference the specific section(s) of the parent spec.

**Change** — The precise change being proposed. For text changes, include the current wording and the proposed replacement. For additions, include the full text to be added and where it should go.

**Impact** *(optional)* — Any downstream effects: other specs affected, implementation changes required, migration considerations.

### 6.5 Committing an Addendum

Commit with a message like: `Add addendum ATH-ARCH-A001: <title>`

## 7. Incorporating Addenda

When one or more pending addenda are ready to be merged into a new spec version:

1. **Determine the version bump.** Review all pending addenda and decide whether the changes warrant a minor or major version bump (see §3).
2. **Update the spec body.** Apply each pending addendum's changes to the specification text.
3. **Update the spec frontmatter:**
   - Bump `version`
   - Set `status: draft` (the new version starts as a draft for review)
   - Update `date_modified`
   - Add each addendum ID to `addenda_incorporated`
   - Add a `changelog` entry summarizing what was incorporated
4. **Update each incorporated addendum's frontmatter:**
   - Set `status: incorporated`
   - Set `incorporation_target` to the new spec version
5. **Review the updated spec** as a coherent whole — ensure the incorporated changes read naturally in context.
6. **Finalize** the new version per §5 when the draft is ready.

## 8. Retrieving Old Versions

Since versions are tracked via git tags (not filenames), previous versions can be retrieved with:

```bash
# View the spec at a specific version
git show spec/ATH-ARCH/v1.0:specifications/Athenaeum\ —\ Architecture\ Specification.md

# Check out a specific version to a temporary file
git show spec/ATH-ARCH/v1.0:specifications/Athenaeum\ —\ Architecture\ Specification.md > /tmp/ATH-ARCH-v1.0.md

# List all spec tags
git tag -l 'spec/*'
```

## 9. Conventions

### 9.1 Changelog Entries

Changelog entries should be concise and focus on *what changed*, not *why*. The "why" belongs in the addendum or commit message. Entries are listed in reverse chronological order (newest first).

Good: `"Incorporate ATH-ARCH-A001, ATH-ARCH-A002: clarify tag inheritance, add batch processing spec"`
Bad: `"Updated some sections based on feedback"`

### 9.2 Cross-References

When one spec references another, use the spec ID: "See ATH-ARCH §3.2 for the tag model." Do not reference specific versions unless the distinction matters — the reader should consult the current version by default.

### 9.3 When in Doubt

- If unsure whether a change is major or minor, prefer minor.
- If unsure whether to file an addendum or edit directly, file an addendum — it's easier to incorporate an unnecessary addendum than to reconstruct a lost change.
- If a spec is growing unwieldy, consider splitting it into focused specs rather than continuing to extend it.

## 10. Frontmatter Templates

### 10.1 Specification Template

```yaml
---
spec_id: ATH-XXXX
title: "Specification Title"
version: 1.0
status: draft
author: Steven Rahn
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
changelog:
  - version: 1.0
    date: YYYY-MM-DD
    summary: "Initial specification"
---
```

### 10.2 Addendum Template

```yaml
---
addendum_id: ATH-XXXX-A001
parent_spec: ATH-XXXX
parent_version: 1.0
title: "Brief description of the change"
type: clarification
status: pending
author: Steven Rahn
date_created: YYYY-MM-DD
sections_affected:
  - "Section Number and Title"
incorporation_target: ~
---
```
