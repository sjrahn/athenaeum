"""Functional URI parsing, canonicalization, and cache-path construction (spec §6).

Pure module — no I/O.

URI grammar:

    corpus://<hash>[?<params>][#<fragment>]

Where:

- `<hash>` is a 64-char lowercase hex blake3 hash.
- `<params>` is an `&`-separated list of `key=value` pairs and flag-style keys (no
  `=`). Order is significant — transforms compose left-to-right.
- A param VALUE percent-encodes the query-reserved characters `%`/`&`/`#` as
  `%25`/`%26`/`%23` (`quote_value`); the parser decodes (`unquote_value`) and the
  canonical renderer re-encodes, so values may carry any character — member names are
  user-controlled (`?path=…D%26D 5e….json` addresses `…D&D 5e….json`).
- `<fragment>` is a body-anchor name (e.g. `page-4`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import blake3 as _blake3

from . import paths

SCHEME = "corpus"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ParsedURI:
    """Parsed `corpus://` URI.

    `params` preserves the authored order. Flag-style params (no `=`) are stored
    with `value=None`.
    """

    hash: str
    params: tuple[tuple[str, str | None], ...] = ()
    fragment: str = ""

    @property
    def is_bare(self) -> bool:
        """No params, no fragment — refers to the source artifact directly."""
        return not self.params and not self.fragment


def parse(uri: str) -> ParsedURI:
    """Parse a `corpus://` URI. Raises ValueError on malformed input."""
    parts = urlsplit(uri)
    if parts.scheme != SCHEME:
        raise ValueError(f"expected scheme 'corpus://', got {parts.scheme!r}: {uri}")

    if parts.path and parts.path != "":
        raise ValueError(f"unexpected path component in URI: {uri}")

    record_hash = parts.netloc.lower()
    if not _HASH_RE.match(record_hash):
        raise ValueError(f"hash must be 64-char lowercase hex, got {parts.netloc!r}: {uri}")

    params = _parse_query(parts.query)
    return ParsedURI(hash=record_hash, params=params, fragment=parts.fragment)


def _parse_query(query: str) -> tuple[tuple[str, str | None], ...]:
    """Split the query on `&`/first-`=`, then percent-DECODE each value (`unquote_value`) —
    the read side of the `_VALUE_ESCAPES` contract, so a member name carrying a
    query-reserved character (`Direct Messages - D&D 5e […].json`) is addressable as
    `?path=…D%26D 5e….json`. Keys are grammar-controlled names, never decoded."""
    if not query:
        return ()
    out: list[tuple[str, str | None]] = []
    for chunk in query.split("&"):
        if not chunk:
            continue
        if "=" in chunk:
            key, _, value = chunk.partition("=")
            out.append((key, unquote_value(value)))
        else:
            out.append((chunk, None))
    return tuple(out)


def canonical(parsed: ParsedURI) -> str:
    """Render the canonical string form of a parsed URI.

    Canonicalization preserves the authored param order (significant for composition)
    and lowercases the hash. Fragment is preserved.
    """
    base = f"{SCHEME}://{parsed.hash}"
    if parsed.params:
        rendered = "&".join(_render_param(k, v) for k, v in parsed.params)
        base = f"{base}?{rendered}"
    if parsed.fragment:
        base = f"{base}#{parsed.fragment}"
    return base


def _render_param(key: str, value: str | None) -> str:
    # Values re-encode on render (parse stores them DECODED), so parse ∘ canonical is a
    # stable round-trip and the canonical string is always re-parseable.
    return key if value is None else f"{key}={quote_value(value)}"


# Characters that are structural in the query/fragment grammar and so must be
# percent-encoded inside a param VALUE for it to compose unambiguously into a
# `corpus://?…` URI: `%` (the escape char itself), `&` (param separator), and `#`
# (fragment separator). Deliberately NOT encoded: spaces (a literal space parses fine
# and reads cleanly — e.g. `sheet=Example A RP1-RP5`) and `=` (the parser takes the
# value after the FIRST `=` via partition, so a later `=` is safe).
_VALUE_ESCAPES = (("%", "%25"), ("&", "%26"), ("#", "%23"))


def quote_value(value: str) -> str:
    """Percent-encode query-reserved characters (`%`, `&`, `#`) in a param value.
    `%` is escaped first so the decode is unambiguous."""
    for raw, enc in _VALUE_ESCAPES:
        value = value.replace(raw, enc)
    return value


def unquote_value(value: str) -> str:
    """Inverse of `quote_value`."""
    for raw, enc in reversed(_VALUE_ESCAPES):
        value = value.replace(enc, raw)
    return value


def urihash(canonical_uri: str) -> str:
    """blake3 hash of the canonical URI string. 64-char lowercase hex."""
    return _blake3.blake3(canonical_uri.encode("utf-8")).hexdigest()


def cache_path(corpus_root: Path, urihash_value: str, extension: str) -> Path:
    """Return the cache file path for a given urihash + extension."""
    ext = extension.lstrip(".")
    return corpus_root / "cache" / paths.shard(urihash_value) / f"{urihash_value}.{ext}"


def cache_sidecar_path(cache_path: Path) -> Path:
    """The sidecar (`.json`) path for a resolved cache file. Named after the full cache
    filename (`<urihash>.<ext>.json`) so it never collides with a content file whose own
    extension is `.json` (e.g. the PDF `probe`/`words`/`outline` ops)."""
    return cache_path.with_name(cache_path.name + ".json")


# ---------- ergonomics ---------- #


def iter_params(parsed: ParsedURI) -> Iterable[tuple[str, str | None]]:
    """Yield `(key, value)` pairs in authored order."""
    return iter(parsed.params)


def get_last(parsed: ParsedURI, key: str) -> str | None:
    """Return the last value for `key` (last-wins semantics — used for `dpi`)."""
    last: str | None = None
    for k, v in parsed.params:
        if k == key:
            last = v
    return last
