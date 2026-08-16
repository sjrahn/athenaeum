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

`ADAPTERS` maps adapter name -> module; `adapter_available` is the guarded
lookup `refdata.resolve()` and callers use before assuming a dataset's
content is resolvable in this environment.
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


def _load_zim() -> ModuleType:
    from . import zim

    return zim


# Adapter name -> module. Registered by name rather than instantiated so an
# adapter whose optional dependency is missing still imports cleanly (the
# module's own `available()` reports the guarded truth).
ADAPTERS: dict[str, ModuleType] = {"zim": _load_zim()}


def adapter_available(name: str) -> bool:
    """False for an unregistered adapter name AND for a registered one whose
    optional dependency didn't import (spec/ledger.md §6.5: "the dataset's
    adapter is unavailable in the verifying environment" is a distinct,
    honest outcome from an unregistered name — both report False here)."""
    adapter = ADAPTERS.get(name)
    return adapter is not None and adapter.available()
