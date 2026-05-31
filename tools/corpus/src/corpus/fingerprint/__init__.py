"""Atom-canonical fingerprint strategies (spec §7.7).

A body segment's perceptual fingerprint strategy is determined by its `atom:`, not by
the source media-type:

- `text`  → 64-bit simhash (pure Python — always available).
- `image` → 64-bit pHash via `imagehash` (the `[fingerprint]` extra).
- `audio` → chromaprint via `pyacoustid` + `fpcalc` (the `[fingerprint]` extra).

Image / audio degrade to None when their dependency is absent (perceptual production
is suspended-by-default for those), so a base install computes text fingerprints and
omits the rest rather than failing. Each submodule exposes `ALGO` / `STRATEGY`
constants for inclusion in touch identifiers.
"""

from . import audio, image, text

__all__ = ["audio", "image", "text"]
