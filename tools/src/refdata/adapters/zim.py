"""The `zim` format adapter — resolves native ids against a ZIM archive
(Wikipedia, ArchWiki, … mirrors; spec/ledger.md §6.5). Optional dependency:
`libzim` (the `zim` extra, `pyproject.toml`). Guard-imported so this module
— and `refdata.adapters` importing it — loads cleanly without the extra;
`available()` reports the guarded truth.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from ..errors import EntryNotFound
from . import AdapterResult

try:
    from libzim.reader import Archive as _Archive  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised by the no-extra environment
    _Archive = None

_WS_RE = re.compile(r"\s+")


def available() -> bool:
    return _Archive is not None


def open_archive(mirror_path: Path) -> Any:
    """Open the ZIM at `mirror_path`. Caller (refdata's handle cache) owns
    not re-opening the same path twice; libzim's `Archive` is otherwise a
    plain read handle with no explicit close."""
    assert _Archive is not None, "zim adapter unavailable — check available() first"
    return _Archive(str(mirror_path))


def resolve_entry(handle: Any, native_id: str) -> AdapterResult:
    """Resolve `native_id` to an entry: exact path first, then the `A/`
    namespace-prefixed form older (pre-new-namespace-scheme) ZIMs use.
    Follows redirects to the target entry — `canonical_id` names it."""
    entry = _get_entry(handle, native_id)
    if entry.is_redirect:
        entry = entry.get_redirect_entry()
    item = entry.get_item()
    content_type = item.mimetype or None
    return AdapterResult(
        canonical_id=entry.path,
        title=entry.title or None,
        text=_render_text(item, content_type),
        content_type=content_type,
    )


def _get_entry(archive: Any, native_id: str) -> Any:
    try:
        return archive.get_entry_by_path(native_id)
    except KeyError:
        pass
    try:
        return archive.get_entry_by_path(f"A/{native_id}")
    except KeyError:
        raise EntryNotFound(f"no entry {native_id!r} (tried A/{native_id!r} too)") from None


def _render_text(item: Any, content_type: str | None) -> str | None:
    """HTML -> plain text via BeautifulSoup (space-separated, whitespace
    collapsed — the ledger's quote matcher normalizes whitespace, so no
    finer rendering is warranted). Other `text/*` -> decoded as-is. Anything
    else (image, binary) -> None; there is no text projection to quote."""
    raw = bytes(item.content)
    if content_type and content_type.startswith("text/html"):
        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(separator=" ")
        return _WS_RE.sub(" ", text).strip()
    if content_type and content_type.startswith("text/"):
        return raw.decode("utf-8", errors="replace")
    return None
