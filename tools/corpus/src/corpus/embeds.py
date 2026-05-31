"""Functional-URI wiki-link embed extraction from record bodies.

Pure module — no I/O. Records may reference derived views of artifacts inline using
the syntax `![[corpus://<hash>?<params>|<description>]]` (spec §5). This module
locates those references so callers (e.g. the exporter) can resolve and rewrite them.

This is distinct from the `<!--embed-->` metadata-zone block (spec §4.3.1.4 —
defined in `records.py`), which describes an asset captured alongside the artifact.
The wiki-link embed here is an *in-body cross-reference* to a derived view, not a
block declaration.

Bare-hash cross-refs `![[<blake3>]]` (no `corpus://` scheme) are intentionally NOT
matched here; they're a separate concept and any caller that cares about them should
scan for them independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# `\[\[corpus://...\]\]` with optional `|description` suffix.
# - `[^\]|]+` for the URI: forbid `]` and `|` so we don't run past the closing
#   brackets or into the description.
# - `[^\]]*` for the description: forbid `]` so the closing `]]` terminates cleanly.
_EMBED_RE = re.compile(r"!\[\[(corpus://[^\]|]+)(?:\|([^\]]*))?\]\]")


@dataclass(frozen=True)
class WikiEmbed:
    raw: str  # the full `![[...]]` match, used for replacement
    span: tuple[int, int]  # (start, end) offsets in the source body
    uri: str  # the `corpus://...` URI string
    description: str  # text after `|`, or empty string


def find_wiki_embeds(body: str) -> list[WikiEmbed]:
    """Return all `![[corpus://...]]` wiki-link embeds in document order."""
    return [
        WikiEmbed(
            raw=m.group(0),
            span=m.span(),
            uri=m.group(1),
            description=m.group(2) or "",
        )
        for m in _EMBED_RE.finditer(body)
    ]
