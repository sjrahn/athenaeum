"""Zip transforms — the materialization side of a `path=<rel>` member address.

- `path=<rel>` (zip → bytes) — extract the named member's raw bytes. `<rel>` is the
  rendered (optionally root-stripped) path the `zip-manifest` drafter recorded on the
  member's segment / embed; `corpus.ziparchive.resolve_member` re-derives the wrapper
  root so the recorded address round-trips to byte-identical content.

Unlike the typed image / text / audio transforms, a zip member can be any type, so this
yields the raw `bytes` kind (cached verbatim, served `application/octet-stream`); the
member's real media type lives on its embed block for a consumer that wants to interpret
it.
"""

from __future__ import annotations

from pathlib import Path

from .. import ziparchive
from . import RenderContext, register


@register("zip", "path", "bytes")
def extract_member(path: Path, value: str | None, ctx: RenderContext) -> bytes:
    """`?path=<rel>` — the named member's raw bytes. `path` is the artifact `.zip`."""
    if value is None or not value.strip():
        raise ValueError("path= requires a member path")
    # Pass the value verbatim (no strip): a member name may legitimately carry leading or
    # trailing whitespace, and the recorded `path=` address must round-trip exactly.
    return ziparchive.resolve_member(path, value)
