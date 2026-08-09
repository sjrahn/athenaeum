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


# ---------- element-path grammar (3.6, spec §6.1.1) ---------- #

# One dotted component: a 1-based child index among ELEMENT siblings. Leading zeros are
# rejected — the space is permanent, so there is exactly one spelling per address.
_EL_COMPONENT_RE = re.compile(r"^[1-9]\d*$")
_EL_SIBLING_RANGE_RE = re.compile(r"^\[([1-9]\d*)-([1-9]\d*)\]$")


@dataclass(frozen=True)
class ElPath:
    """A parsed 3.6 `el=` value (spec §6.1.1): a dotted child-index path walked from the
    artifact's body — `el=1.3.2` is the body's first element child's third element
    child's second — optionally ending in a sibling range (`el=1.3.[2-9]`: children 2
    through 9 of `el=1.3`, inclusive, and their subtrees).

    Components count ELEMENTS only (text nodes, comments, and attributes are invisible
    to the walk). A point path names the element AND its whole subtree — which is why an
    envelope under this grammar cannot over-claim, and why the retired flat `el=<N>-<M>`
    form has no successor spelling: a region crossing subtree boundaries is an ordered
    address LIST (§4.3.2.2), never a single value."""

    components: tuple[int, ...]
    sibling_range: tuple[int, int] | None = None

    @property
    def is_point(self) -> bool:
        return self.sibling_range is None


def parse_el_path(value: str | None) -> ElPath:
    """Parse a 3.6 `el=` value into an `ElPath`. Raises `ValueError` naming the actual
    mistake — including the one live confusion, a retired 3.5 flat range (`el=1-8`),
    which gets its own message because every pre-migration record carried them.

    The single definition of the path grammar: the resolver walks through it, lint
    validates through it, and the section-envelope derivation composes through it, so an
    authored address cannot be legal to one and illegal to another (the `parse_region`
    precedent)."""
    if value is None or not value.strip():
        raise ValueError("el= requires a child-index path (spec §6.1.1), e.g. el=1.3.2")
    raw = value.strip()
    pieces = raw.split(".")
    sibling_range: tuple[int, int] | None = None
    tail = _EL_SIBLING_RANGE_RE.match(pieces[-1])
    if tail:
        a, b = int(tail.group(1)), int(tail.group(2))
        if a >= b:
            raise ValueError(
                f"el={raw}: sibling range [{a}-{b}] must run low-to-high across at "
                f"least two children (a single child is its own point path)"
            )
        sibling_range = (a, b)
        pieces = pieces[:-1]
        if not pieces:
            raise ValueError(
                f"el={raw}: a sibling range needs a parent path before it "
                f"(el=<parent>.[{a}-{b}]) — there is no whole-body range form"
            )
    components: list[int] = []
    for piece in pieces:
        if not _EL_COMPONENT_RE.match(piece):
            if re.match(r"^\d+-\d+$", raw):
                raise ValueError(
                    f"el={raw}: the flat min-max range is the retired 3.5 form "
                    f"(spec §6.1.1) — a subtree is its container's own path, a sibling "
                    f"run is el=<parent>.[<a>-<b>], and a region crossing subtree "
                    f"boundaries is an address list"
                )
            raise ValueError(
                f"el={raw}: path components are dot-separated 1-based child indices "
                f"(got {piece!r})"
            )
        components.append(int(piece))
    if not components:
        raise ValueError(f"el={raw}: empty path")
    return ElPath(components=tuple(components), sibling_range=sibling_range)


def format_el_path(path: ElPath) -> str:
    """Canonical string form of an `ElPath` (the value only, no `el=` key)."""
    base = ".".join(str(c) for c in path.components)
    if path.sibling_range is not None:
        a, b = path.sibling_range
        return f"{base}.[{a}-{b}]"
    return base


def el_path_contains(a: ElPath, b: ElPath) -> bool:
    """Whether `a`'s claim contains `b`'s — the §6.1.1 component-wise prefix test,
    extended over sibling ranges on either side. `el=1.3` contains `el=1.3.2` and does
    NOT contain `el=1.30`; `el=1.3.[2-4]` contains `el=1.3.2.5` and not `el=1.3.5`.
    Containment is inclusive: every path contains itself."""
    ac, bc = a.components, b.components
    if a.sibling_range is None:
        # A point claims its whole subtree; a target point inside it, or a target range
        # over children anywhere inside it, both reduce to the same prefix test.
        return len(ac) <= len(bc) and bc[: len(ac)] == ac
    # `a` is a sibling range: its claim is children a1..a2 of a.components.
    a1, a2 = a.sibling_range
    if b.sibling_range is not None and bc == ac:
        b1, b2 = b.sibling_range
        return a1 <= b1 and b2 <= a2
    if len(bc) <= len(ac) or bc[: len(ac)] != ac:
        return False
    return a1 <= bc[len(ac)] <= a2


def el_path_sort_key(path: ElPath) -> tuple[int, ...]:
    """Document-order sort key: component-wise NUMERIC comparison, so `el=1.10` sorts
    after `el=1.9` — the lexical-string trap §6.1.1 warns about. A sibling range sorts
    at its first child's position."""
    if path.sibling_range is None:
        return path.components
    return (*path.components, path.sibling_range[0])


# ---------- integer index-span grammar ---------- #


def parse_index_span(
    key: str, value: str | None, *, count: int | None = None, noun: str = "the artifact"
) -> tuple[int, int]:
    """Parse a 1-indexed integer address axis — `N` (one unit) or `N-M` (an inclusive
    span) — into `(low, high)`, bounds-checked against `count` when one is given.

    `count=None` checks grammar and the lower bound only, for a caller that reaches the
    upper bound anyway as part of work it must do regardless (the EPUB single-index path
    materializes through `addressable_image_bytes`, which counts elements itself and
    raises the same message). Supplying a count there would mean parsing the spine
    document twice per address — 22,293 of them on one record. A SPAN, by contrast,
    never reaches materialization, so its caller MUST supply the count; that is the
    whole point of this function.

    The single definition of the index-span grammar, for the same reason `parse_region`
    is: the SPAN form was the hole. A span envelope has no single byte surface, so the
    materialization transforms used to short-circuit it to `NotMaterializable` before
    ever looking at the numbers — which meant `el=94-102` on a nine-element artifact
    was waved through as declared coverage while the bare `el=145` beside it errored.
    Eight of the seventeen out-of-range addresses in the corpus were invisible that way.
    Bounds are a property of the ADDRESS, not of whether it happens to materialize, so
    they are checked here, before the caller decides which of the two it is."""
    if value is None or not value.strip():
        raise ValueError(f"{key}= requires an integer index")
    raw = value.strip()
    if "-" in raw:
        start, _, end = raw.partition("-")
        try:
            low, high = int(start), int(end)
        except ValueError as exc:
            raise ValueError(
                f"{key}={raw}: span endpoints must be integers"
            ) from exc
        if high < low:
            raise ValueError(
                f"{key}={raw}: span end {high} precedes its start {low}"
            )
    else:
        try:
            low = high = int(raw)
        except ValueError as exc:
            raise ValueError(f"{key}={raw}: not an integer") from exc
    if low < 1:
        raise ValueError(f"{key}={raw}: indices are 1-based, got {low}")
    if count is not None and high > count:
        # Message shape kept identical to the pre-existing single-index error, so the
        # finding text a reader already knows does not change under the span form.
        raise ValueError(
            f"{key}={high} out of range ({noun} has {count} addressable elements)"
        )
    return low, high


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


def frame_errors(key: str, value: str | None, *, count: int | None = None) -> list[str]:
    """Validate one authored `key=value` param as an image frame index/span, returning
    zero or more human-readable problems. Non-`frame` keys return `[]`.

    The IMAGE side of the polymorphic `frame=` axis (spec §6.2): a 1-based ordinal `N`
    or inclusive span `N-M` over the artifact's own frame sequence — never a timecode,
    which is the VIDEO working kind's reading of the same key and is not judged here
    (the caller gates on mime). The grammar and bounds are `parse_index_span`'s, the
    same definition the materialization transform renders through, for the same
    lint-and-render-cannot-disagree reason as `region_errors` above."""
    if key != "frame":
        return []
    try:
        parse_index_span("frame", value, count=count, noun="the artifact")
    except ValueError as exc:
        return [str(exc)]
    return []


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
