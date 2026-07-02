"""Audio fingerprint strategy: chromaprint acoustic fingerprint (spec §7.7).

Computed via `pyacoustid` (the `[fingerprint]` extra), which shells out to the
`fpcalc` system binary (the `chromaprint` package). Degrades to None when either is
absent — perceptual production is suspended-by-default.

No P5 drafter computes audio fingerprints (video framegrab segments are `image` and
body-empty; transcript segments are `text`); this is the API-complete strategy for
future callers. The raw chromaprint is variable-length, so it is digested to a
128-bit value to fit the §7.6 `<algo>:<hex>` encoding — a stable identifier, not a
hamming-comparable chromaprint. Widening the perceptual encoding to carry the raw
chromaprint is a follow-up.

Encoded `chromaprint:<32-hex>`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ALGO = "chromaprint"
STRATEGY = "chromaprint-v2"


def fingerprint_file(path: Path) -> str | None:
    """Return `chromaprint:<32-hex>` for the audio at `path`, or None when the
    `[fingerprint]` extra / `fpcalc` binary are unavailable or extraction fails."""
    try:
        import acoustid
    except ImportError:
        return None
    try:
        _duration, raw = acoustid.fingerprint_file(str(path))
    except Exception:
        return None
    data = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
    return f"{ALGO}:{hashlib.blake2b(data, digest_size=16).hexdigest()}"


def fingerprint_audio_range(path: Path, *, start: float, end: float) -> str | None:
    """Range-scoped variant (`time_range=` addressing). Not yet implemented — returns
    None. The whole-file `fingerprint_file` is the available strategy."""
    del path, start, end
    return None
