"""Cryptographic hashing helpers.

blake3 is the artifact's identity (spec §1.5). Other hashes the matching mime schema
declares via `transport_algos` (e.g. sha256) are computed alongside in a single read pass.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import blake3 as _blake3

CHUNK = 1 << 20  # 1 MiB


def hash_file(path: Path, *, also: tuple[str, ...] = ("sha256",)) -> dict[str, str]:
    """Stream `path` once; return blake3 plus any auxiliary hashes named in `also`.

    Auxiliary hash names must be valid `hashlib` algorithms.
    """
    b3 = _blake3.blake3()
    aux = {name: hashlib.new(name) for name in also}

    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            b3.update(chunk)
            for h in aux.values():
                h.update(chunk)

    return {"blake3": b3.hexdigest(), **{name: h.hexdigest() for name, h in aux.items()}}


def hash_bytes(data: bytes, *, also: tuple[str, ...] = ("sha256",)) -> dict[str, str]:
    """Hash an in-memory `bytes` blob; same API as `hash_file()`.

    Returns blake3 plus any auxiliary hashes named in `also`. Used when a drafter
    materialises an artifact in memory and needs its content-addressed identity
    before writing it to disk.
    """
    b3 = _blake3.blake3()
    b3.update(data)
    aux = {name: hashlib.new(name) for name in also}
    for h in aux.values():
        h.update(data)
    return {"blake3": b3.hexdigest(), **{name: h.hexdigest() for name, h in aux.items()}}
