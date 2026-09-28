"""The consumer ingest lane's allowlist (spec/athenaeum.md §2.3 `consumer_ingest:`, v49).

`consumer_ingest: {origins: [owner-statement, owner-share]}` in the instance config names the
origin ids `corpus ingest-owned` may mint under. It is a LOCAL reader, like `assets.py`'s
and for the same reason: `corpus` sits below `ath` in the reference graph, so it walks up from
the corpus root to `athenaeum.yaml` itself and parses only this block.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .assets import MANIFEST_NAME, _find_instance_root


class ConsumerLaneError(ValueError):
    """`consumer_ingest:` is present but malformed."""


def load_consumer_origins(corpus_root: Path) -> frozenset[str]:
    """The origin ids the instance opens to consumer ingest — empty when there is no instance
    config above `corpus_root`, or it declares no `consumer_ingest:` (the lane is closed).
    Raises `ConsumerLaneError` when the block is present but malformed."""
    root = _find_instance_root(corpus_root)
    if root is None:
        return frozenset()
    data = yaml.safe_load((root / MANIFEST_NAME).read_text(encoding="utf-8")) or {}
    block = data.get("consumer_ingest") if isinstance(data, dict) else None
    if block is None:
        return frozenset()
    if not isinstance(block, dict) or set(block) - {"origins"}:
        raise ConsumerLaneError(
            "athenaeum.yaml consumer_ingest: expected a mapping with only `origins:`")
    origins = block.get("origins") or []
    if not isinstance(origins, list) or not all(isinstance(o, str) and o for o in origins):
        raise ConsumerLaneError(
            "athenaeum.yaml consumer_ingest.origins: expected a list of origin ids")
    return frozenset(origins)
