"""Text fingerprint strategy: 64-bit simhash over normalized tokens (spec §7.7).

Pure-Python — no third-party dependency. Every `atom: text` segment can carry a
simhash fingerprint computed against its body after Unicode NFKC normalization,
lowercasing, and word-token splitting. Comparable across light textual variations
(formatting, whitespace); not a paraphrase / near-duplicate detector.

Encoded `simhash:<16-hex>` (64-bit) per the §7.6 `<algo>:<hex>` convention.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter

ALGO = "simhash"
STRATEGY = "simhash-64"
_BITS = 64
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


def fingerprint_text(text: str) -> str | None:
    """Return `simhash:<16-hex>` for `text`, or None when it has no tokens.

    Deterministic: token hashes come from blake2b (stdlib), so the same text always
    yields the same fingerprint across runs and machines.
    """
    counts = Counter(_tokens(text))
    if not counts:
        return None
    acc = [0] * _BITS
    for token, weight in counts.items():
        h = _token_hash(token)
        for i in range(_BITS):
            acc[i] += weight if (h >> i) & 1 else -weight
    value = 0
    for i in range(_BITS):
        if acc[i] > 0:
            value |= 1 << i
    return f"{ALGO}:{value:016x}"


def _tokens(text: str) -> list[str]:
    """NFKC-normalize, lowercase, split into `\\w+` tokens. Empty input → []."""
    if not text:
        return []
    return _WORD_RE.findall(unicodedata.normalize("NFKC", text).lower())


def _token_hash(token: str) -> int:
    """Map a token to a 64-bit integer via blake2b (stdlib, deterministic)."""
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")
