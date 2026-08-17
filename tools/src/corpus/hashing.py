"""Cryptographic hashing + the derived-hash recipe registry (spec §2, §7.6, §7.9).

blake3 is the artifact's identity (spec §2) — computed alongside any auxiliary
`hashlib` digests by `hash_file`/`hash_bytes`, unchanged API other callsites depend on.

*(v20)* The rest of this module is the **recipe registry**: named procedures over an
artifact's bytes, each characterized by a residency class (byte-stable vs
procedure-versioned, §2) and a comparison class (identity vs similarity, §7.9). The
effective recipe set for an artifact resolves as an additive union across three layers
— corpus-wide default, mime schema, matched origin overlay(s) (`resolve_recipes`) — and
`compute_hashes` computes every resolved recipe's value(s) over a staged file in as few
read passes as practical.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import blake3 as _blake3

from . import singlefile

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


# ====================================================================== #
# Recipe registry (spec §7.9)
# ====================================================================== #

Residency = Literal["byte-stable", "procedure-versioned"]
Comparison = Literal["identity", "similarity"]


class RecipeError(ValueError):
    """An unknown recipe id, or a schema-invalid recipe declaration.

    Spec §7.9: declaring `residency: record` semantics for a procedure-versioned
    recipe is a schema error *by construction* — the registry is the sole authority on
    a recipe's class, so this is raised at `Recipe` construction time, not discovered
    later at write time.
    """


@dataclass(frozen=True)
class Recipe:
    """A named derived-hash procedure (spec §7.9).

    `id` is the recipe id as declared in a schema's `derived_hashes:` list — also the
    §7.6 **tag** for a single-value recipe (`sha256`, `html-stampfree@1`). A
    multi-value recipe (`blake3-prefix-ladder`) has its own per-value tags instead
    (`blake3-4k`, `blake3-64k`, `blake3-1m`) — `multivalue=True` marks it so callers
    know not to treat `id` as a tag.

    `record_resident` is the byte-stable-only `residency: record` marker (§2, §7.9):
    ingest writes such a recipe's value to the frontmatter `hash:` field *and* the
    index; every other recipe is index-only (record-flushable on deliberate demand,
    for byte-stable ones; never flushable, for similarity-class ones — no similarity
    recipe ships yet, §7.7's fingerprints are the future population).
    """

    id: str
    residency: Residency
    comparison: Comparison
    record_resident: bool = False
    multivalue: bool = False

    def __post_init__(self) -> None:
        if self.record_resident and self.residency != "byte-stable":
            raise RecipeError(
                f"recipe {self.id!r}: `residency: record` is only valid on a "
                "byte-stable recipe (spec §7.9) — a schema error by construction"
            )


# The three prefix-ladder rungs (spec §7.9's registry table), shortest first.
_LADDER_RUNGS: tuple[tuple[int, str], ...] = (
    (4 * 1024, "blake3-4k"),
    (64 * 1024, "blake3-64k"),
    (1024 * 1024, "blake3-1m"),
)

SHA256 = Recipe(id="sha256", residency="byte-stable", comparison="identity", record_resident=True)
MD5 = Recipe(id="md5", residency="byte-stable", comparison="identity", record_resident=True)
BLAKE3_PREFIX_LADDER = Recipe(
    id="blake3-prefix-ladder", residency="byte-stable", comparison="identity", multivalue=True
)
HTML_STAMPFREE_1 = Recipe(
    id="html-stampfree@1", residency="procedure-versioned", comparison="identity"
)

#: The corpus-wide default set (spec §7.9) — applied with no declaration, every mime.
DEFAULT_SET: tuple[Recipe, ...] = (SHA256, MD5, BLAKE3_PREFIX_LADDER)

#: Open for extension (§7.9's registry is not closed) — `register_recipe` adds to this.
_REGISTRY: dict[str, Recipe] = {
    r.id: r for r in (SHA256, MD5, BLAKE3_PREFIX_LADDER, HTML_STAMPFREE_1)
}


def register_recipe(recipe: Recipe) -> None:
    """Register `recipe`, making it resolvable by id from a schema's `derived_hashes:`
    list. A corpus-local module may call this before `resolve_recipes` runs to add its
    own procedure-versioned recipes (an `eml-stripped@2.1`-shaped canonicalization,
    §7.9) — the four shipped recipes are a starting set, not a closed one."""
    _REGISTRY[recipe.id] = recipe


def get_recipe(recipe_id: str) -> Recipe | None:
    """Return the registered recipe named `recipe_id`, or None."""
    return _REGISTRY.get(recipe_id)


# ---------- tag grammar (spec §7.6) ---------- #

_HEX_RE = re.compile(r"^[0-9a-f]+$")
_BARE_ALGO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class TagInfo:
    """The §7.6 classification of one bare `<tag>` (no `:<hex>` suffix)."""

    tag: str
    residency: Residency
    procedure: str | None = None  # set only for a procedure-versioned tag
    version: str | None = None  # ditto — compared exactly, as an opaque string


def parse_tag(tag: str) -> TagInfo:
    """Classify a bare `<tag>` per spec §7.6.

    A bare algorithm id (`sha256`, `blake3-64k`) is byte-stable; a
    `<procedure>@<version>` tag (`html-stampfree@1`, `eml-stripped@2.1`) is
    procedure-versioned — the version is part of the tag, compared exactly, never
    parsed as a number. Raises `ValueError` on a malformed tag (empty, embeds a `:`,
    or an empty procedure/version half of an `@`-tag).
    """
    tag = (tag or "").strip()
    if not tag or ":" in tag:
        raise ValueError(f"invalid hash tag {tag!r}")
    if "@" in tag:
        procedure, _, version = tag.partition("@")
        if not procedure or not version or not _BARE_ALGO_RE.match(procedure):
            raise ValueError(f"invalid procedure-versioned tag {tag!r}")
        return TagInfo(
            tag=tag, residency="procedure-versioned", procedure=procedure, version=version
        )
    if not _BARE_ALGO_RE.match(tag):
        raise ValueError(f"invalid hash tag {tag!r}")
    return TagInfo(tag=tag, residency="byte-stable")


def parse_value(value: str) -> tuple[TagInfo, str]:
    """Split a `<tag>:<hex>` encoded value (§7.6) into its `TagInfo` and lowercase hex
    digest. Splits on the FIRST `:` (§7.6's parsing rule). Raises `ValueError` on a
    missing `:<hex>` suffix, a malformed tag, or a non-hex/empty digest.
    """
    tag, sep, hexval = value.partition(":")
    if not sep:
        raise ValueError(f"hash value {value!r} missing `<tag>:` prefix")
    info = parse_tag(tag)
    hexval = hexval.strip()
    if not hexval or not _HEX_RE.match(hexval):
        raise ValueError(f"hash value {value!r} has a non-hex digest")
    return info, hexval


# ---------- union resolution (spec §7.9) ---------- #


def _require_recipe(recipe_id: str) -> Recipe:
    recipe = _REGISTRY.get(recipe_id)
    if recipe is None:
        raise RecipeError(
            f"unknown derived-hash recipe {recipe_id!r} — not in the registry (spec "
            "§7.9); register it (`hashing.register_recipe`) before a schema can "
            "declare it"
        )
    return recipe


def _legacy_algo_recipe(algo: str) -> Recipe:
    """A bare `transport_algos:` entry reads as a `residency: record` byte-stable
    recipe — exactly what the old key did (spec §7.1's legacy-compat note). A
    registered byte-stable recipe of the same id is reused; an unregistered-but-valid
    `hashlib` algorithm name gets an ad hoc recipe, since the legacy key was never
    restricted to the four shipped recipe ids."""
    algo = algo.strip().lower()
    existing = _REGISTRY.get(algo)
    if existing is not None and existing.residency == "byte-stable":
        return existing
    try:
        hashlib.new(algo)
    except (ValueError, TypeError) as e:
        raise RecipeError(f"transport_algos: invalid hash algorithm {algo!r}: {e}") from e
    return Recipe(id=algo, residency="byte-stable", comparison="identity", record_resident=True)


def _schema_recipes(schema: dict[str, Any]) -> tuple[Recipe, ...]:
    """The recipes ONE schema layer (a mime schema or an origin overlay) adds (§7.9's
    additive union) — `derived_hashes:` recipe ids, or, absent that key entirely, the
    legacy `transport_algos:` compat read."""
    declared = schema.get("derived_hashes")
    if declared is not None:
        return tuple(_require_recipe(str(rid)) for rid in declared)
    legacy = schema.get("transport_algos")
    if legacy is not None:
        return tuple(_legacy_algo_recipe(str(a)) for a in legacy if str(a).strip())
    return ()


def resolve_recipes(
    mime_schema: dict[str, Any] | None,
    origin_overlays: Iterable[dict[str, Any] | None] = (),
) -> tuple[Recipe, ...]:
    """The effective recipe set for an artifact (spec §7.9): the additive union of the
    corpus-wide default set, the mime schema's `derived_hashes:` (or legacy
    `transport_algos:`), and each matched origin overlay's `derived_hashes:` — a later
    layer adds recipes and never suppresses one an earlier layer contributed.

    Takes already-resolved schema dicts rather than a `corpus_root` + mime string: the
    caller (ingest, reattest) already holds the matched mime schema and origin
    overlay(s) from its own resolution walk (`schemas.load_mime_schema`,
    `schemas.origin_overlays_for_uris` / `records.iter_origin_blocks`), so this stays a
    pure function over what's in hand rather than repeating that walk or importing
    `schemas` (avoiding a hashing↔schemas import cycle).

    Raises `RecipeError` on an unknown recipe id — a schema-authoring mistake,
    surfaced immediately rather than silently dropped.
    """
    seen: dict[str, Recipe] = {r.id: r for r in DEFAULT_SET}
    if mime_schema:
        for r in _schema_recipes(mime_schema):
            seen.setdefault(r.id, r)
    for overlay in origin_overlays:
        if not overlay:
            continue
        for r in _schema_recipes(overlay):
            seen.setdefault(r.id, r)
    return tuple(seen.values())


# ====================================================================== #
# Computation (spec §7.9, §12.3.3)
# ====================================================================== #


@dataclass(frozen=True)
class HashValue:
    """One computed recipe value.

    `tag` is the §7.6 tag (`sha256`, `blake3-64k`, `html-stampfree@1`) — what a
    `hash:` entry or a hash-index row's `algo` column carries. `recipe` is the recipe
    id that produced it (equal to `tag` except for the prefix ladder, whose one recipe
    emits three per-rung tags). `param` is the rung length for the prefix ladder
    (empty string otherwise) — the hash-index row's `param` column, spec §12.9.1.
    `record_resident` marks a byte-stable `residency: record` value — the caller's cue
    to also write it to frontmatter `hash:`.
    """

    recipe: str
    tag: str
    hex: str
    param: str = ""
    record_resident: bool = False

    def encoded(self) -> str:
        """The `<tag>:<hex>` encoded form (spec §7.6)."""
        return f"{self.tag}:{self.hex}"


# The corpus-injected `<meta name="corpus-*" content="...">` tags
# (`capture/__init__.py:_inject_corpus_metadata`), matched however the attribute value
# was escaped. `_attr_escape` only ever turns a literal `&`/`"`/`<` into an entity
# reference inside the value — it never introduces a literal `"` — so `[^"]*` for each
# quoted attribute is an exact match, not an approximation.
_CORPUS_META_RE = re.compile(
    rb'<meta\s+name="corpus-[^"]*"\s+content="[^"]*"\s*/?>',
    re.IGNORECASE,
)

# The SingleFile save banner comment (singlefile.py's `_BANNER_RE` anchor text, reused
# here rather than re-invented) — matched non-greedily so exactly the banner comment is
# removed, not swallowed into some later unrelated `<!-- ... -->`.
_SINGLEFILE_BANNER_RE = re.compile(
    rb"<!--.*?Page saved with SingleFile.*?-->",
    re.IGNORECASE | re.DOTALL,
)


# A corpus-injected meta tag is a few hundred bytes (a URL, a timestamp, a fidelity
# word); the carry only needs to exceed the longest possible match so an
# incomplete-at-buffer-end tag always sits wholly inside the carried tail. 64 KiB is
# orders of magnitude past any real stamp.
_STAMP_CARRY = 1 << 16


def _stampfree_from_stream(fh, *, chunk_size: int = CHUNK) -> str:
    """The one `html-stampfree@1` implementation (spec §7.9), bounded-memory: stream
    `fh`, remove the corpus-injected `corpus-*` meta tags wherever they fall, remove
    the SingleFile banner comment within the first `singlefile.HEAD_BYTES` of the
    *cleaned* stream, and blake3 what remains. Never holds the input in memory — the
    fleet's largest text/html artifact is a 9.68 GB iMessage export member, and the
    whole-file predecessor died on the OOM killer hashing it.

    Chunk-boundary correctness: each round scans `carry + chunk`; a complete tag match
    anywhere in that buffer is removed, and an INCOMPLETE tag can only start within
    one tag-length of the buffer's end, so holding back a `_STAMP_CARRY` tail (far
    longer than any real tag) guarantees the next round sees it whole. Re-scanning the
    carried tail is idempotent — a self-contained match in it would already have been
    removed the round before.
    """
    hasher = _blake3.blake3()
    head_pending = b""  # cleaned bytes awaiting the banner pass, first HEAD_BYTES only
    head_done = False

    def _emit(cleaned: bytes) -> None:
        nonlocal head_pending, head_done
        if head_done:
            hasher.update(cleaned)
            return
        head_pending += cleaned
        if len(head_pending) >= singlefile.HEAD_BYTES:
            head = _SINGLEFILE_BANNER_RE.sub(
                b"", head_pending[: singlefile.HEAD_BYTES], count=1
            )
            hasher.update(head)
            hasher.update(head_pending[singlefile.HEAD_BYTES :])
            head_pending = b""
            head_done = True

    carry = b""
    while chunk := fh.read(chunk_size):
        buf = _CORPUS_META_RE.sub(b"", carry + chunk)
        if len(buf) > _STAMP_CARRY:
            _emit(buf[:-_STAMP_CARRY])
            carry = buf[-_STAMP_CARRY:]
        else:
            carry = buf
    _emit(carry)
    if not head_done:  # input shorter than HEAD_BYTES: banner pass over what there is
        hasher.update(_SINGLEFILE_BANNER_RE.sub(b"", head_pending, count=1))
    return hasher.hexdigest()


def html_stampfree_digest(data: bytes) -> str:
    """Compute the `html-stampfree@1` recipe value (spec §7.9): blake3 of `data` after
    removing ONLY the bytes the corpus's own capture pipeline injected — the three
    `corpus-*` meta tags (wherever they fall) and the SingleFile save banner comment
    (scanned within `singlefile.HEAD_BYTES`, mirroring that module's own bound). Bytes
    the pipeline did not inject are never touched: no reparse, no reserialization, no
    whitespace normalization beyond the removed spans. Delegates to the streaming core
    so bytes-in-hand and file callers can never diverge.
    """
    return _stampfree_from_stream(io.BytesIO(data))


def html_stampfree_digest_file(path: Path, *, chunk_size: int = CHUNK) -> str:
    """`html_stampfree_digest` over a file path, bounded memory — the form
    `compute_hashes` uses so a multi-gigabyte artifact never loads whole."""
    with path.open("rb") as fh:
        return _stampfree_from_stream(fh, chunk_size=chunk_size)


def compute_hashes(path: Path, recipes: Iterable[Recipe]) -> list[HashValue]:
    """Compute every value of `recipes` over the file at `path`.

    Byte-stable `hashlib` algorithms and the blake3 prefix ladder share ONE streaming
    read pass (like `hash_file`); `html-stampfree@1` needs the whole file in memory (a
    second pass — HTML artifacts are not the multi-gigabyte population the streaming
    pass exists for). A recipe not in `recipes` costs nothing: this never computes
    ahead of what the caller resolved.
    """
    recipes = tuple(recipes)
    hashlib_recipes = [r for r in recipes if r.residency == "byte-stable" and not r.multivalue]
    want_ladder = any(r.multivalue for r in recipes)
    want_stampfree = any(r.id == "html-stampfree@1" for r in recipes)

    aux = {r.id: hashlib.new(r.id) for r in hashlib_recipes}
    ladder = {length: _blake3.blake3() for length, _tag in _LADDER_RUNGS} if want_ladder else {}

    bytes_read = 0
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            start, end = bytes_read, bytes_read + len(chunk)
            for h in aux.values():
                h.update(chunk)
            for length, hasher in ladder.items():
                if start >= length:
                    continue
                take = min(length, end) - start
                if take > 0:
                    hasher.update(chunk[:take])
            bytes_read = end
    file_size = bytes_read

    values: list[HashValue] = [
        HashValue(
            recipe=r.id, tag=r.id, hex=aux[r.id].hexdigest(), record_resident=r.record_resident
        )
        for r in hashlib_recipes
    ]
    if want_ladder:
        for length, tag in _LADDER_RUNGS:
            # Only rungs the file actually reaches are emitted (spec §7.9's registry
            # table) — a shorter file simply has fewer rungs, never a padded/short one.
            if file_size >= length:
                values.append(
                    HashValue(
                        recipe="blake3-prefix-ladder",
                        tag=tag,
                        hex=ladder[length].hexdigest(),
                        param=str(length),
                    )
                )
    if want_stampfree:
        digest = html_stampfree_digest_file(path)
        values.append(HashValue(recipe="html-stampfree@1", tag="html-stampfree@1", hex=digest))
    return values
