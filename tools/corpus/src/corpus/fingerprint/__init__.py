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

from __future__ import annotations

import logging
from collections.abc import Callable

from . import audio, image, text

__all__ = [
    "DEFAULT_ALGO_BY_ATOM",
    "algos_for_atom",
    "audio",
    "image",
    "text",
    "text_fingerprints",
]

log = logging.getLogger("corpus.fingerprint")

# The default perceptual algorithm per content atom (spec §7.7). The `fingerprint`
# schema knob (resolved by `schemas.resolve_fingerprint`) may select another.
DEFAULT_ALGO_BY_ATOM: dict[str, str] = {
    "text": "simhash",
    "image": "phash",
    "audio": "chromaprint",
}

# algorithm name -> the atom it fingerprints. Both validates a knob's algorithm
# names and routes per-atom dispatch (mirrors `content_hash._STRATEGIES`).
_ALGO_ATOM: dict[str, str] = {
    "simhash": "text",
    "phash": "image",
    "dhash": "image",
    "ahash": "image",
    "whash": "image",
    "chromaprint": "audio",
}


def algos_for_atom(atom: str, knob: object) -> list[str]:
    """Resolve a `fingerprint` knob to the concrete algorithm names to compute for
    `atom`. `knob`: falsy / None = off; `True` = the atom's default algorithm; a
    string or list = those algorithms — filtered to ones valid for `atom` (unknown
    names warn; algorithms belonging to a different atom are silently skipped).
    Order-preserving and de-duplicated."""
    if not knob:
        return []
    if knob is True:
        default = DEFAULT_ALGO_BY_ATOM.get(atom)
        return [default] if default else []
    names = [knob] if isinstance(knob, str) else list(knob)  # type: ignore[arg-type]
    out: list[str] = []
    for raw in names:
        name = str(raw).strip().lower()
        if not name:
            continue
        owner = _ALGO_ATOM.get(name)
        if owner is None:
            log.warning("unknown fingerprint algorithm %r — skipping", name)
            continue
        if owner != atom:
            continue  # e.g. `phash` requested but this segment is a text atom
        if name not in out:
            out.append(name)
    return out


def text_fingerprints(body: str, algos: list[str]) -> str | list[str] | None:
    """Compute the requested text fingerprints for `body`: a scalar for one algorithm,
    a list for several, None when none are requested or all degrade to None."""
    return _collect(lambda algo: text.fingerprint_text(body, algo=algo), algos)


def _collect(compute: Callable[[str], str | None], algos: list[str]) -> str | list[str] | None:
    out: list[str] = []
    for algo in algos:
        value = compute(algo)
        if value:
            out.append(value)
    if not out:
        return None
    return out[0] if len(out) == 1 else out
