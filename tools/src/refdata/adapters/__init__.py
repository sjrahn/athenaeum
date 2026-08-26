"""The format-adapter registry — one module per mirror format (`zim`,
eventually `jsonl-index`, …), resolving native ids against an *open* mirror
handle (spec/ledger.md §6.5).

An adapter module exposes three functions:

- `available() -> bool` — the optional dependency this adapter needs is
  importable (guard-imported; `import`ing the adapter module itself must
  never fail even when the dependency is missing).
- `open_archive(mirror_path: Path) -> Any` — open the mirror; may be costly,
  so `refdata.resolve()` caches the returned handle per mirror path
  (module-level, process-lifetime — see `refdata._handles`).
- `resolve_entry(handle: Any, native_id: str) -> AdapterResult` — resolve one
  entry against an already-open handle; raises `refdata.errors.EntryNotFound`
  on a miss.
- `search_entries(handle: Any, query: str, limit: int, mode: str = "blend") ->
  list[AdapterSearchHit]` — the discovery step ahead of `resolve_entry`
  (spec/ledger.md §6.5): words in, candidate native ids out, best match
  first, each optionally carrying a short `context` hint to disambiguate
  same-titled hits (an adapter with nothing to add leaves it None). `mode`
  selects which index tier(s) to draw from — `"blend"`
  (default: title-index hits first, then full-text hits appended and
  deduplicated — an archive missing one index tier degrades gracefully
  within that mode rather than erroring), `"suggest"` (title index only), or
  `"fulltext"` (full-text index only); an unrecognized mode is `ValueError`.
  An empty list is a valid answer (no hits, or the mirror carries no index
  for the requested tier) — never an error; a missing optional dependency is
  `AdapterUnavailable` at the `refdata` layer, raised before this is ever
  called. Archive open failures (truncated/corrupted mirror bytes) are
  `refdata.errors.MirrorCorrupt`, raised by `open_archive` before a handle
  ever reaches this function.

`ADAPTERS` maps adapter name -> module; `adapter_available` is the guarded
lookup `refdata.resolve()` and callers use before assuming a dataset's
content is resolvable in this environment.

**Optional index API.** Some formats have no random access by native id and
no search index of their own — an OSM PBF extract is a compressed stream,
unlike ZIM's indexed archive — so their adapter (`osm_pbf`) additionally
exposes, as ordinary module-level functions beyond the four above:

- `build_index(mirror_path: Path, *, progress: Callable[[int], None] | None
  = None, index_path: Path | None = None) -> dict[str, int]` — scans the
  mirror once and writes a sidecar index, atomically (`<sidecar>.tmp` then
  `os.replace`). Optionally reports cumulative progress as it goes. Returns
  format-specific counts (e.g. `{"elements": n, "named": m}`).
- `index_state(mirror_path: Path, *, index_path: Path | None = None) -> str`
  — `"indexed"` | `"missing"` | `"stale"` (built by an older index-builder
  version, or from different mirror bytes than are on disk now).
- `open_archive(mirror_path: Path, *, index_path: Path | None = None) ->
  Any` — same four-function contract as above; the sidecar-carrying adapters
  additionally accept `index_path` here so the handle they return knows
  where its sidecar lives.

*(21)* All three take a keyword-only **`index_path`**: when given, it IS the
sidecar location (`refdata` computes this as the corpus's
`cache/refidx/<artifact>.sqlite`, spec/ledger.md §6.5) — a mirror-adjacent
sidecar's naming isn't assumed. When `index_path` is omitted, the adapter
falls back to its legacy beside-the-mirror path (`<mirror_path>.<ext>` for
`osm_pbf`) — bare adapter-module usage and existing sidecars keep working
unchanged. When `index_path` is given but nothing exists there yet, the
adapter also checks the legacy beside-the-mirror location (if present and
not stale, it's used — migration grace for a sidecar built before the
canonical path existed); `MirrorUnindexed`/`"missing"` only when neither
location has one. `ath ref index` always **builds** at the canonical path
when the caller can supply one.

`resolve_entry`/`search_entries` on such an adapter raise
`refdata.errors.MirrorUnindexed` — distinct from `MirrorCorrupt` — when the
index is absent or stale; this is not part of the required four-function
contract every adapter carries, only the formats that need a sidecar at all.
The `ath ref index <dataset>` CLI verb is what calls `build_index`.

**Optional spine API.** The two ontology-release adapters — `bfo-2020`,
`cco-release` (spec/ledger.md §15.2) — additionally expose, beyond the four
required functions:

- `iter_terms(handle) -> Iterator[SpineTerm]` — every term the release
  carries, native id + label + deprecated flag. This is `refdata.spine`'s
  entire surface onto an adapter: it never calls `resolve_entry` or
  `search_entries` (those stay the ordinary `ref://` citation path, spec
  §6.5, independent of the extension-chain machinery). A plain reference
  adapter (`zim`, `osm-pbf`) carries no `iter_terms` at all — registering it
  as `spine: true` is a load-time-legal but resolution-time error
  (`refdata.errors.SpineIncapableAdapter`).
- `ontology_payload_paths(archive_path: Path, work_dir: Path) -> list[Path]`
  — extracts the release's reasoner-consumable ontology file(s) (BFO's
  RDF-XML table, CCO's merged Turtle file) out of the mirror archive into
  `work_dir`, for `ledger.export`'s conformance gate (spec/ledger.md §15.7,
  ISO/IEC 21838-1 Annex D.5.1): a standard OWL 2 reasoner needs the spine's
  own axioms as files on disk beside the export, not merely resolvable
  through `iter_terms`. Raises `refdata.errors.MirrorCorrupt` on the same
  terms `open_archive` does; a plain reference adapter carries no
  `ontology_payload_paths` any more than it carries `iter_terms`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True)
class AdapterResult:
    """One adapter's resolution of a native id against an open mirror handle.

    `canonical_id` is the post-redirect entry path — equal to the requested
    native id when the entry wasn't a redirect. `text` is a plain-text
    rendering for quote matching (§13.2), or None when the entry has no text
    projection (e.g. an image).
    """

    canonical_id: str
    title: str | None
    text: str | None
    content_type: str | None


@dataclass(frozen=True)
class AdapterSearchHit:
    """One adapter's search hit against an open mirror handle — a native id
    ready to paste into `resolve_entry` / a sources-table `ref://` citation,
    plus a display title and an optional short `context` hint (e.g. an OSM
    element's classifying tag and coordinates) for telling same-titled hits
    apart without resolving each one. No `content_type`/`text`: search is
    discovery, not resolution — the caller resolves the id it picks."""

    native_id: str
    title: str | None
    context: str | None = None


@dataclass(frozen=True)
class SpineTerm:
    """One entry in a spine dataset's full term enumeration (spec/ledger.md
    §15.2) — the optional spine API's unit, distinct from `AdapterResult`
    (the ordinary `ref://` resolution unit): only spine-capable adapters
    (`bfo-2020`, `cco-release`) expose `iter_terms`, consumed by
    `refdata.spine.resolve_term` for native-id/label lookup, label-uniqueness
    checking, and surfacing a resolved term's deprecation."""

    native_id: str
    label: str
    deprecated: bool


def _load_zim() -> ModuleType:
    from . import zim

    return zim


def _load_osm_pbf() -> ModuleType:
    from . import osm_pbf

    return osm_pbf


def _load_bfo_2020() -> ModuleType:
    from . import bfo_2020

    return bfo_2020


def _load_cco_release() -> ModuleType:
    from . import cco_release

    return cco_release


# Adapter name -> module. Registered by name rather than instantiated so an
# adapter whose optional dependency is missing still imports cleanly (the
# module's own `available()` reports the guarded truth).
ADAPTERS: dict[str, ModuleType] = {
    "zim": _load_zim(),
    "osm-pbf": _load_osm_pbf(),
    "bfo-2020": _load_bfo_2020(),
    "cco-release": _load_cco_release(),
}


def adapter_available(name: str) -> bool:
    """False for an unregistered adapter name AND for a registered one whose
    optional dependency didn't import (spec/ledger.md §6.5: "the dataset's
    adapter is unavailable in the verifying environment" is a distinct,
    honest outcome from an unregistered name — both report False here)."""
    adapter = ADAPTERS.get(name)
    return adapter is not None and adapter.available()
