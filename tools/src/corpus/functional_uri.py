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


# ---------- region grammar ---------- #

# The ops whose value is a RELATIVE region — `x,y,WIDTH,HEIGHT` as fractions of the
# image, origin top-left. `mark=`/`cover=` take a `;`-separated list of them.
# Declared here, beside the URI grammar, rather than inside the image transform: the
# grammar is a property of the ADDRESS, so lint must be able to hold an authored
# address to it without importing the render path (which is where the whole
# pixel-vs-fraction drift got in — the op raised correctly and nothing ever asked it).
REGION_PARAMS: frozenset[str] = frozenset({"bbox", "crop", "mark", "cover"})
_MULTI_REGION_PARAMS: frozenset[str] = frozenset({"mark", "cover"})
_REGION_EPS = 1e-9


def parse_region(value: str) -> tuple[float, float, float, float]:
    """Parse ONE `x,y,w,h` region of relative floats in [0, 1], bounds-checked so the
    region stays inside the image. Raises `ValueError` with a message that names the
    actual mistake — the two live ones being pixel values in a fractional grammar and
    corner coordinates in a position+size grammar.

    The single definition of the region grammar: `transforms.image` renders through it
    and `lint` validates through it, so an authored address cannot be legal to one and
    illegal to the other."""
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError(f"region must have 4 comma-separated values, got {value!r}")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"region values must be floats, got {value!r}") from exc
    for label, val in (("x", x), ("y", y), ("w", w), ("h", h)):
        if val < 0.0 or val > 1.0:
            raise ValueError(
                f"region {label}={val} out of [0.0, 1.0] in {value!r} — bbox is "
                "x,y,WIDTH,HEIGHT (fractions of the image), not corners x0,y0,x1,y1"
            )
    if x + w > 1.0 + _REGION_EPS or y + h > 1.0 + _REGION_EPS:
        over = []
        if x + w > 1.0 + _REGION_EPS:
            over.append(f"x+w={x + w:.4g}>1")
        if y + h > 1.0 + _REGION_EPS:
            over.append(f"y+h={y + h:.4g}>1")
        raise ValueError(
            f"region {value!r} extends past the image ({', '.join(over)}). bbox is "
            "x,y,WIDTH,HEIGHT (a position plus a size), NOT corners x0,y0,x1,y1 — the "
            "3rd/4th values are width/height, so x+w and y+h must each be <= 1.0"
        )
    return x, y, w, h


def region_errors(key: str, value: str | None) -> list[str]:
    """Validate one authored `key=value` param as a region, returning zero or more
    human-readable problems. Non-region keys return `[]`.

    Deliberately CONSERVATIVE about which values it judges. `bbox=` is overloaded: on a
    spreadsheet it addresses an A1 range (`sheet=Data&bbox=A1:D20`), which is a different
    grammar entirely — so a chunk whose comma-parts are not all numeric is left alone
    rather than guessed at. What remains — four numbers where fractions were required —
    is unambiguous, and is exactly the drift this exists to catch."""
    if key not in REGION_PARAMS:
        return []
    if value is None or not value.strip():
        return [f"{key}= requires at least one x,y,w,h region (fractions in [0,1])"]
    chunks = value.split(";") if key in _MULTI_REGION_PARAMS else [value]
    out: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not _looks_numeric(chunk):
            continue  # a different grammar under the same key (A1 range) — not ours to judge
        try:
            parse_region(chunk)
        except ValueError as exc:
            out.append(str(exc))
    return out


def _looks_numeric(chunk: str) -> bool:
    """True when every comma-separated part parses as a float — the signal that this
    chunk is meant as a relative region at all."""
    parts = chunk.split(",")
    if len(parts) < 2:
        return False
    for p in parts:
        try:
            float(p)
        except ValueError:
            return False
    return True


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
