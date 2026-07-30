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


#: Lineage hops to follow looking for a host. A promoted member of a promoted member is the
#: real shape (a video inside an HTML capture inside an export bundle), and this is generous
#: enough for it while still terminating on a cycle a hand-edited record could introduce.
_MAX_LINEAGE_HOPS = 6


def host_bearing_origin_uri(
    corpus_root: Path, record_metadata: dict[str, Any] | None
) -> str:
    """The first origin URI that can name a HOST, following containment lineage as needed.

    A promoted member's first origin is `corpus://<container>?<address>`, which names no host —
    so a per-host overlay lookup against it silently finds nothing and the record falls back to
    the global default. That is wrong for a leaf: the host's policy for the container it came
    out of is its policy too. `transcription.enabled: false` on a host would otherwise apply to
    a video container and be silently ignored on the audio track promoted from it, which is the
    reverse of what the declaration says.

    *(3.11)* Lineage is walked at READ time and nothing is stored, so this cannot rot — the
    same property that lets a `cutting:` resolution be stored (it is a policy, and it decides a
    stored address) while this is not (it selects an engine for an ephemeral, version-labeled
    derivation, §6.4). §12.15's rule is untouched: lineage here is consulted for policy, never
    for byte residence.
    """
    from corpus import functional_uri as furi
    from corpus import paths, records

    seen: set[str] = set()
    uri = first_origin_uri(record_metadata)
    for _ in range(_MAX_LINEAGE_HOPS):
        if not uri.startswith("corpus://"):
            return uri
        try:
            container_id = furi.parse(uri).hash
        except ValueError:
            return ""
        if container_id in seen:  # a cycle: report no host rather than looping
            log.warning("containment lineage cycles at %s — no host resolved", container_id[:12])
            return ""
        seen.add(container_id)
        record_file = paths.record_path(corpus_root, container_id)
        if not record_file.is_file():
            return ""
        uri = records.primary_origin_uri(records.load(record_file))
    log.warning("containment lineage deeper than %d hops — no host resolved", _MAX_LINEAGE_HOPS)
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

    *(3.11)* Reads through containment lineage (`host_bearing_origin_uri`), so a promoted audio
    stream leaf inherits the transcription policy of the host its container came from.
    """
    url = host_bearing_origin_uri(corpus_root, record_metadata)
    section = recipes.transcription_for_url(corpus_root, url) if url else None
    if not section:
        return ("global", None)
    if section.get("enabled") is False:
        return ("disabled", None)
    overrides = {k: section[k] for k in ("adapter", "base_url") if k in section}
    if overrides:
        return ("override", transcription.get_transcriber(corpus_root, overrides=overrides))
    return ("global", None)
