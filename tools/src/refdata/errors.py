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


class EntryNotFound(RefdataError):
    """The mirror opened and the adapter ran, but `native_id` names no entry
    in it (after redirect-namespace fallback, where the adapter supports one)."""
