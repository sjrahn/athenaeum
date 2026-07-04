"""Tar transforms — the materialization side of a `path=<rel>` member address (spec §12.4).

- `path=<rel>` (tar → bytes) — extract the named member's raw bytes. `<rel>` is the rendered
  member path the `tar-manifest` drafter recorded on the member's embed; `corpus.tararchive`
  re-derives any wrapper root so the recorded address round-trips to byte-identical content.

The tar sibling of `transforms/zip.py`: a tar member can be any type, so this yields the raw
`bytes` kind (cached verbatim, served `application/octet-stream`); the member's real media type
lives on its embed block. `tarfile` auto-detects gzip, so this serves both `.tar` and `.tgz`.
"""

from __future__ import annotations

from pathlib import Path

from .. import tararchive
from . import RenderContext, register


@register("tar", "path", "bytes")
def extract_member(path: Path, value: str | None, ctx: RenderContext) -> bytes:
    """`?path=<rel>` — the named member's raw bytes. `path` is the artifact `.tar`/`.tgz`."""
    if value is None or not value.strip():
        raise ValueError("path= requires a member path")
    # Pass the value verbatim (no strip): a member name may legitimately carry leading or
    # trailing whitespace, and the recorded `path=` address must round-trip exactly.
    return tararchive.resolve_member(path, value)
