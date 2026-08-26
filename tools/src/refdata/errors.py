"""Typed failures for reference-dataset resolution (spec/ledger.md §6.5).

Callers (the ledger's `ref://` verify path, `ath ref` CLI verbs) branch on
these rather than parsing messages — content resolution is honestly
*unverifiable*, never a crash, when the mirror or its adapter is absent
(§6.5 "Content resolution requires the mirror bytes locally materialized …
where they are absent … content verification reports unverifiable, never
failure").
"""

from __future__ import annotations


class RefdataError(Exception):
    """Base for every reference-dataset resolution failure."""


class UnknownTag(RefdataError):
    """The requested tag (or `reference.latest`) names no registered snapshot."""


class AdapterUnavailable(RefdataError):
    """The dataset's `adapter:` name is unregistered, or its optional
    dependency (e.g. `libzim` for `zim`) is not installed in this
    environment — `adapter_available(name)` reports the same truth
    ahead of a call, for callers that want to check before resolving."""


class MirrorUnavailable(RefdataError):
    """`materialize()` found no local bytes for the snapshot — neither the
    declared `path:` override nor any given corpus root's artifact store."""


class MirrorCorrupt(RefdataError):
    """Bytes were found at the materialized path, but the adapter couldn't
    open them as its format — truncated (still downloading) or corrupted.
    Distinct from `MirrorUnavailable` (no bytes at all): here bytes exist but
    aren't a valid archive, so the underlying adapter error (e.g. libzim's
    raw `RuntimeError` from `Archive()`) is wrapped here rather than left to
    propagate — a bad mirror is honestly unverifiable, never a crash, same
    as every other `RefdataError`."""


class EntryNotFound(RefdataError):
    """The mirror opened and the adapter ran, but `native_id` names no entry
    in it (after redirect-namespace fallback, where the adapter supports one)."""


class MirrorUnindexed(RefdataError):
    """The adapter's format needs a sidecar index to resolve or search — e.g.
    `osm-pbf`'s SQLite index over a PBF's tagged elements (spec/ledger.md
    §6.5): a PBF is a compressed stream with no random access by element id
    and no search index of its own — and none exists yet, or the one on disk
    was built from different mirror bytes or a different index-builder
    version than what's on disk now (stale). Distinct from `MirrorCorrupt`
    (the mirror bytes themselves don't open as the declared format): here the
    mirror is fine, only its optional derived index is missing or stale —
    honestly unverifiable, never a crash, same as every other `RefdataError`
    subclass. Fixed by (re)building the index (`ath ref index <dataset>`)."""


# --- the spine resolution layer (spec/ledger.md §15.2) ----------------------
#
# `refdata.spine.resolve_term` builds on the resolution above — a spine
# dataset is an ordinary registered reference dataset (§6.5) marked
# `spine: true` — so the "honestly unverifiable, never a crash" outcomes for
# an unmaterialized mirror or an unavailable adapter are exactly
# `MirrorUnavailable`/`AdapterUnavailable`/`MirrorCorrupt` above, raised
# unchanged. The classes below are the spine layer's OWN failures: grammar,
# registration, and resolution-uniqueness problems that are errors regardless
# of mirror availability (§15.2 "a reference that does not resolve … is a
# validation error — never a warning").


class SpineError(RefdataError):
    """Base for `refdata.spine`'s own resolution failures — distinct from,
    but a subclass of, the ordinary `RefdataError` family so a caller
    catching either broadly or narrowly gets what it expects."""


class InvalidSpineReference(SpineError):
    """The spec string isn't `{dataset}:{id-or-label}` grammar, or carries an
    `@{tag}` pin — deliberately never admitted in a spine reference form
    (spec/ledger.md §15.2: "Always bare — one spine version per instance")."""


class NotSpineDataset(SpineError):
    """The named dataset names no registered `references:` entry, or is
    registered but not marked `spine: true` (spec/ledger.md §15.2)."""


class SpineIncapableAdapter(SpineError):
    """The dataset's format adapter carries no `iter_terms` — it can serve
    ordinary `ref://` citations but was never built to enumerate a release's
    terms, so it cannot root a spine (spec/ledger.md §15.2)."""


class SpineTermNotFound(SpineError):
    """Neither a native id nor a unique label in the dataset's resolved
    release matched the reference — "an unresolvable reference is an error"
    (spec/ledger.md §15.2)."""


class AmbiguousSpineLabel(SpineError):
    """A label matched more than one term in the dataset's resolved release
    — "a label ambiguous in the resolved release is an error" (spec/ledger.md
    §15.2); cite the native id instead."""
