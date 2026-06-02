"""Per-host draft-time config resolution.

The drafters are handed the record's parsed frontmatter (`record_metadata`), which
carries the origin block(s). This module resolves the record's origin host and reads
the matching origin-overlay sections at draft time — mirroring the capture-side
`recipes` lookup, but consumed by the audio/video drafters.

Currently: per-host transcription (`transcription:` section). The same `first_origin_uri`
seam is reused by the `.info.json` sidecar wiring (the `metadata:` section).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from corpus import transcription
from corpus.capture import recipes

log = logging.getLogger(__name__)


def first_origin_uri(record_metadata: dict[str, Any] | None) -> str:
    """The first URI of the record's first origin block, or `""` (host lookup seam).

    Operates on the metadata dict the drafter receives (the `records.primary_origin_uri`
    equivalent for `post.metadata` rather than a `frontmatter.Post`)."""
    for origin in (record_metadata or {}).get("_origins") or []:
        uri = (origin.get("fields") or {}).get("uri")
        if isinstance(uri, list) and uri:
            return str(uri[0])
        if uri:
            return str(uri)
    return ""


def resolve_transcription(
    corpus_root: Path, record_metadata: dict[str, Any] | None
) -> tuple[str, transcription.TranscriptionAdapter | None]:
    """Decide how to transcribe this record, per its origin host's overlay.

    Returns `(mode, transcriber)`:
      - `("global", None)`   — no/absent `transcription:` section: use the global adapter
                                (resolver default; pass `transcriber=None`).
      - `("disabled", None)` — `transcription.enabled: false`: skip (caller emits an info issue).
      - `("override", adapter)` — a per-host backend (`adapter`/`base_url`) overrides the global.
    """
    url = first_origin_uri(record_metadata)
    section = recipes.transcription_for_url(corpus_root, url) if url else None
    if not section:
        return ("global", None)
    if section.get("enabled") is False:
        return ("disabled", None)
    overrides = {k: section[k] for k in ("adapter", "base_url") if k in section}
    if overrides:
        return ("override", transcription.get_transcriber(corpus_root, overrides=overrides))
    return ("global", None)
