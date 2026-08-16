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
