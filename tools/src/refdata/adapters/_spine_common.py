"""Shared plumbing for the spine format adapters — `bfo_2020.py` and
`cco_release.py` (spec/ledger.md §15.2). Both mirror an ontology release as a
zip archive and, once parsed, reduce to the same tiny shape: an id-keyed
table of (label, definition, deprecated). This module holds that table and
builds the adapter-contract functions plus the spine-only `iter_terms` extra
(`refdata/adapters/__init__.py`) generically over it — each format module
supplies only its own zip -> `Handle` parse.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ..errors import EntryNotFound
from . import AdapterResult, AdapterSearchHit, SpineTerm


@dataclass(frozen=True)
class Entry:
    """One parsed ontology term, format-agnostic."""

    native_id: str
    label: str | None
    definition: str | None
    deprecated: bool


@dataclass(frozen=True)
class Handle:
    """An open spine mirror: every parsed term, keyed by native id."""

    by_id: dict[str, Entry]


def resolve_entry(handle: Handle, native_id: str) -> AdapterResult:
    """The four-function contract's `resolve_entry`, generic over `Handle`
    (spec/ledger.md §6.5's ordinary `ref://` citation path — independent of
    the spine `extends:` machinery in `refdata.spine`, which uses `iter_terms`
    below instead). `text` is the §6.5 quote-verification surface: label plus
    definition, the "label + definition is fine" rendering."""
    entry = handle.by_id.get(native_id)
    if entry is None:
        raise EntryNotFound(f"no term {native_id!r} in this spine mirror")
    if entry.label and entry.definition:
        text = f"{entry.label}\n\n{entry.definition}"
    else:
        text = entry.label or entry.definition
    return AdapterResult(
        canonical_id=native_id, title=entry.label, text=text, content_type="text/plain"
    )


def search_entries(
    handle: Handle, query: str, limit: int, mode: str = "blend"
) -> list[AdapterSearchHit]:
    """Discovery step ahead of `resolve_entry` (spec/ledger.md §6.5), in the
    same three-mode shape as `zim`/`osm_pbf`: `"suggest"` matches the query
    substring against labels only, `"fulltext"` against definitions only,
    `"blend"` (default) label hits first then definition-only hits appended,
    deduplicated — a term whose label already matched is never repeated for
    also matching on definition. These mirrors are small (tens of MB, at most
    a few thousand terms) so a linear case-insensitive substring scan per
    call is plenty; no index is built or cached beyond the parsed table
    itself."""
    if mode not in ("blend", "suggest", "fulltext"):
        raise ValueError(f"unknown search mode {mode!r} (want 'blend', 'suggest', or 'fulltext')")
    q = query.strip().lower()
    if not q:
        return []
    entries = sorted(handle.by_id.values(), key=lambda e: e.native_id)
    label_hits = (
        [e for e in entries if q in (e.label or "").lower()] if mode in ("blend", "suggest")
        else []
    )
    fulltext_hits = (
        [e for e in entries if q in (e.definition or "").lower()] if mode in ("blend", "fulltext")
        else []
    )
    seen: set[str] = set()
    ordered: list[Entry] = []
    for e in label_hits + fulltext_hits:
        if e.native_id not in seen:
            seen.add(e.native_id)
            ordered.append(e)
    return [AdapterSearchHit(native_id=e.native_id, title=e.label) for e in ordered[:limit]]


def iter_terms(handle: Handle) -> Iterator[SpineTerm]:
    """The spine-only extra (beyond the four-function contract, parallel to
    `osm_pbf`'s `build_index`/`index_state`): every parsed term, sorted by
    native id for determinism. `refdata.spine.resolve_term` uses this for
    both native-id and label lookup and for label-uniqueness checking — the
    generic `resolve_entry` above is never called from that path."""
    for entry in sorted(handle.by_id.values(), key=lambda e: e.native_id):
        yield SpineTerm(
            native_id=entry.native_id,
            label=entry.label or entry.native_id,
            deprecated=entry.deprecated,
        )
