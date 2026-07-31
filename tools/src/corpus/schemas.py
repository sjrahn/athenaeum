"""Schema loading — corpus-local first, packaged default second (spec §3, §7).

The four reserved top-level namespaces:

- `mime/<type>/<type>_<subtype>.yaml` — media-type schemas. **Format-universal,
  packaged.** Layered universal → type → subtype.
- `atom/<atom>/<atom>_<id>.yaml` — atomic overlays on segments. **Format-universal,
  packaged.** Layered universal-per-atom → overlay.
- `origin/<scheme>/<id>.yaml` — origin overlays, namespaced by URI scheme family
  (spec §7.2): web (http/https) sources at `origin/web/<host>.yaml`, with `otherwise/`
  the catch-all and future families like `urn/`, `file/`, `s3/`. **Per-corpus concern;
  not packaged.** Both the universal `origin/origin.yaml` (uri/snapshot declarations)
  and the per-id overlays live corpus-local; `corpus init` seeds the universal +
  `web/example.com.yaml` at scaffold time. The flat `origin/<id>.yaml` layout is read
  tolerantly for back-compat. The overlay id is the bare `<id>` regardless of sub-namespace.
- `context/<namespace>/<namespace>.yaml` (+ `<id>.yaml`) — annotation-zone overlays (the
  `context` block, spec §4.3.3): `issue`, `reference`, `note`, … `context/issue/<id>.yaml`
  carries issue overlays — the universal `context/issue/issue.yaml` ships in the package;
  per-id overlays may live in either source.

Why the split: `mime` and `atom` describe *format and fidelity* (a PDF is a PDF;
a transcript is a transcript) — universal. `origin` describes *sources of
retrieval* and `context` describes *observations about a record* — both
corpus-specific decisions. (The 1.0 `composite` classification umbrella was removed
in ATH-CORPUS 2.0 — what content means is asserted in the ledger, not the record;
`composite` stays a reserved namespace so the 1.0 layout is never repurposed.)

Resolution model (the keystone):

- **Source fallback** (per file): a single layer-rung resolves to the **first source
  that has it**. Corpus-local override of a packaged universal wins whole-file.
- **Layer merge** (across rungs): the spec §3 4-step chain (universal → axis →
  id → subtype) is deep-merged most-specific-wins, with each rung independently
  source-resolved.

Rule: **whole-file wins at each rung; merge across rungs.** Keeps overrides
removable (a corpus restating the universal can *delete* a packaged field, which
silent deep-merge under a packaged universal would prevent).
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import yaml

from . import urls as urlcanon

log = logging.getLogger(__name__)

# Namespaces reserved by the spec — the top-level directories under `schema/`
# (spec §3). `form` (3.0, §7.8) declares record-scope structural-shape overlays bound on
# section openers; `composite` stays reserved-but-removed (2.0) so the 1.0 layout is never
# repurposed.
_RESERVED_NAMESPACES = {"mime", "origin", "atom", "form", "composite", "context"}

VALID_ATOMS = ("text", "image", "audio", "video")


# ---------- generic merge ---------- #


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict that recursively merges `override` over `base`.

    Lists are replaced, not concatenated — a more-specific layer that wants to extend
    a base list must restate the merged list explicitly. Sub-dicts are merged
    recursively.
    """
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# ---------- schema sources ---------- #


@dataclass(frozen=True)
class _SchemaSource:
    """One source of schemas — either a corpus-local Path or the packaged Traversable.

    Two implementations are folded into one type because the surface we need
    (`exists`/`load_yaml`/`iter_yaml`) is identical and small.
    """

    backend: Path | Traversable
    label: str  # "corpus" or "package", for error messages

    def exists(self, relpath: str) -> bool:
        node = self._traverse(relpath)
        return node is not None and node.is_file()

    def load_yaml(self, relpath: str) -> dict[str, Any] | None:
        node = self._traverse(relpath)
        if node is None or not node.is_file():
            return None
        try:
            text = node.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(
                f"WARN: failed to read schema {self.label}:{relpath}: {e}",
                file=sys.stderr,
            )
            return None
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as e:
            print(
                f"WARN: malformed YAML in {self.label}:{relpath}: {e}",
                file=sys.stderr,
            )
            return None
        if not isinstance(data, dict):
            print(
                f"WARN: schema {self.label}:{relpath} is not a mapping",
                file=sys.stderr,
            )
            return None
        return data

    def iter_yaml(self, dir_relpath: str) -> Iterator[str]:
        """Yield relpaths of every `*.yaml` under `dir_relpath` (recursively).

        Each yielded relpath is relative to the source's root (e.g.
        `"mime/application/application_pdf.yaml"`), so it can be passed back to
        `load_yaml` / `exists`. Returns nothing if the dir is absent.
        """
        node = self._traverse(dir_relpath)
        if node is None or not node.is_dir():
            return
        yield from self._walk_yaml(node, prefix=dir_relpath)

    # ---- backend dispatch ---- #

    def _traverse(self, relpath: str) -> Path | Traversable | None:
        parts = [p for p in relpath.split("/") if p]
        node = self.backend
        for part in parts:
            node = node / part
        return node

    def _walk_yaml(
        self, node: Path | Traversable, *, prefix: str
    ) -> Iterator[str]:
        children = sorted(node.iterdir(), key=lambda c: c.name)
        for child in children:
            child_rel = f"{prefix}/{child.name}" if prefix else child.name
            if child.is_dir():
                yield from self._walk_yaml(child, prefix=child_rel)
            elif child.is_file() and child.name.endswith(".yaml"):
                yield child_rel


@lru_cache(maxsize=64)
def _sources(corpus_root: Path) -> tuple[_SchemaSource, ...]:
    """Return the ordered source list for `corpus_root`: corpus-local first,
    packaged-default second.

    Cached per-root so the importlib.resources lookup happens once.
    """
    corpus_local = _SchemaSource(backend=corpus_root / "schema", label="corpus")
    packaged = _SchemaSource(backend=files("corpus") / "schemas_default", label="package")
    return (corpus_local, packaged)


def cache_clear() -> None:
    """Clear every schema cache. Schemas are immutable for the life of a CLI process, so
    the per-record loaders are `@lru_cache`d (keyed on `(corpus_root, …)`); callers must
    treat the returned dicts as read-only. Call this after writing/modifying schema files
    in the same process — chiefly tests; a normal CLI run never mutates schemas post-load."""
    _sources.cache_clear()
    load_mime_schema.cache_clear()
    mime_schema_id_for.cache_clear()
    load_origin_overlay_by_id.cache_clear()
    load_origin_overlays.cache_clear()
    load_context_schema.cache_clear()
    load_form_overlay.cache_clear()


# ---------- composition primitives ---------- #


def _read_yaml_first(
    sources: Iterable[_SchemaSource], relpath: str
) -> dict[str, Any] | None:
    """Return the YAML at the first source that has `relpath`, else None.

    Per-rung "whole-file wins" rule: a corpus-local override of a single layer is
    not deep-merged with the packaged copy of the same layer — the local file is
    taken whole. Cross-rung merging is the caller's job (`_read_yaml_layered`).
    """
    for source in sources:
        if source.exists(relpath):
            return source.load_yaml(relpath)
    return None


def _read_yaml_layered(
    sources: Iterable[_SchemaSource], *relpaths: str
) -> dict[str, Any]:
    """Deep-merge a chain of `relpaths` (least specific → most specific).

    Each rung independently falls back local-first; the merged result is
    most-specific-wins. Returns `{}` when no rung resolved (caller can decide
    whether absence is meaningful).
    """
    srcs = list(sources)  # iter twice
    merged: dict[str, Any] = {}
    for relpath in relpaths:
        layer = _read_yaml_first(srcs, relpath)
        if layer:
            merged = _deep_merge(merged, layer)
    return merged


def _discover_yaml(
    sources: Iterable[_SchemaSource], dir_relpath: str
) -> list[str]:
    """Discover yaml relpaths under `dir_relpath` across both sources (union).

    Earlier sources (corpus-local) take precedence over later (packaged) for the
    same relpath, but discovery yields every distinct relpath either source has.
    """
    seen: dict[str, None] = {}
    for source in sources:
        for relpath in source.iter_yaml(dir_relpath):
            seen.setdefault(relpath, None)
    return sorted(seen)


# ---------- mime schemas ---------- #


def _is_mime_subtype_path(relpath: str) -> bool:
    """True iff `relpath` is a subtype-specific mime schema (e.g.
    `mime/application/application_pdf.yaml`), excluding the universal
    `mime/mime.yaml` and the per-axis common files (`mime/application/application.yaml`).
    """
    parts = relpath.split("/")
    if parts[0] != "mime" or not relpath.endswith(".yaml"):
        return False
    # Per-id is every rung EXCEPT the universal `mime/mime.yaml` and an axis-common
    # file (e.g. `mime/application/application.yaml`).
    is_universal = len(parts) == 2 and parts[1] == "mime.yaml"
    is_axis_common = len(parts) == 3 and parts[2] == f"{parts[1]}.yaml"
    return not (is_universal or is_axis_common)


def _mime_schema_id(relpath: str) -> str:
    """Extract the schema id (`<axis>/<axis>_<subtype>`) from a mime schema relpath."""
    # mime/application/application_pdf.yaml → application/application_pdf
    return relpath.removeprefix("mime/").removesuffix(".yaml")


def _iter_mime_subtype_paths(corpus_root: Path) -> list[str]:
    """Yield each subtype-specific mime schema relpath available across both sources."""
    return [r for r in _discover_yaml(_sources(corpus_root), "mime") if _is_mime_subtype_path(r)]


@lru_cache(maxsize=256)
def load_mime_schema(corpus_root: Path, mime: str) -> dict[str, Any] | None:
    """Return the layered mime schema dict matching the IANA `mime` (e.g. `application/pdf`).

    Walks both sources for any subtype yaml whose `applies_to.content_types` includes
    `mime`. When a match is found, returns the deep-merged spec §3 chain:
    universal (`mime/mime.yaml`) → axis (`mime/<axis>/<axis>.yaml`) → subtype
    (`mime/<axis>/<axis>_<subtype>.yaml`), each rung independently source-resolved.

    Raises `ValueError` if more than one mime schema claims the same `mime`.
    """
    sources = _sources(corpus_root)
    matches: list[tuple[str, str]] = []  # (schema_id, relpath_of_match)
    for relpath in _iter_mime_subtype_paths(corpus_root):
        data = _read_yaml_first(sources, relpath) or {}
        applies = (data.get("applies_to") or {}).get("content_types") or []
        if mime in applies:
            matches.append((_mime_schema_id(relpath), relpath))
    if not matches:
        return None
    if len({mid for mid, _ in matches}) > 1:
        names = ", ".join(mid for mid, _ in matches)
        raise ValueError(
            f"multiple mime schemas claim MIME {mime!r}: {names}. "
            "Each MIME must map to exactly one mime schema."
        )
    # Same id from both sources is fine — corpus override of packaged subtype.
    schema_id = matches[0][0]
    axis = schema_id.split("/", 1)[0]
    subtype_relpath = matches[0][1]
    return _read_yaml_layered(
        sources,
        "mime/mime.yaml",
        f"mime/{axis}/{axis}.yaml",
        subtype_relpath,
    )


@lru_cache(maxsize=256)
def mime_schema_id_for(corpus_root: Path, mime: str) -> str | None:
    """Return the mime schema id (e.g. `application/application_pdf`) for `mime`, or
    None when no schema claims it."""
    sources = _sources(corpus_root)
    for relpath in _iter_mime_subtype_paths(corpus_root):
        data = _read_yaml_first(sources, relpath) or {}
        applies = (data.get("applies_to") or {}).get("content_types") or []
        if mime in applies:
            return _mime_schema_id(relpath)
    return None


@lru_cache(maxsize=64)
def zip_signatures(corpus_root: Path) -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    """Corpus-declared zip-shape signatures, for `mime._refine_zip`.

    A mime schema for a zip-shaped type whose telltale members sit under a variable
    wrapper dir (so an exact built-in signature can't match) declares its shape in
    `applies_to`: `zip_members` (exact member paths — ANY present matches) and/or
    `zip_member_patterns` (regexes — ALL must each match some member). This keeps
    vendor/site-specific zip recognition in the corpus overlay rather than hardcoded in
    the shared package (the detection analogue of the overlay-driven `draft` strategy).

    Returns `(content_type, exact_members, patterns)` tuples, sorted by content type for
    deterministic first-match order. Universal formats (OOXML / epub / jar) stay in the
    package's exact-path table and are checked first by the caller."""
    sources = _sources(corpus_root)
    out: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for relpath in _iter_mime_subtype_paths(corpus_root):
        applies = (_read_yaml_first(sources, relpath) or {}).get("applies_to") or {}
        exact = tuple(str(x) for x in (applies.get("zip_members") or []))
        patterns = tuple(str(x) for x in (applies.get("zip_member_patterns") or []))
        content_types = applies.get("content_types") or []
        if (exact or patterns) and content_types:
            out.append((str(content_types[0]), exact, _valid_zip_patterns(patterns, relpath)))
    return tuple(sorted(out, key=lambda t: t[0]))


def _valid_zip_patterns(patterns: tuple[str, ...], relpath: object) -> tuple[str, ...]:
    """Drop any `zip_member_pattern` that isn't a compilable regex. Parse-tolerant: a bad
    overlay pattern is logged and skipped here — once, at the cached schema-read boundary —
    rather than raising `re.error` out of `mime.detect` on every ingest of a zip-shaped
    artifact (which would break ingest of unrelated zips too)."""
    valid: list[str] = []
    for pat in patterns:
        try:
            re.compile(pat)
        except re.error as exc:
            log.warning("ignoring invalid zip_member_pattern %r in %s: %s", pat, relpath, exc)
            continue
        valid.append(pat)
    return tuple(valid)


# ---------- atomic-overlay schemas ---------- #


def load_atomic_overlay(
    corpus_root: Path, atom: str, overlay_id: str | None = None
) -> dict[str, Any] | None:
    """Return the layered atomic-overlay schema for `atom` + optional `overlay_id`.

    Spec §3 chain: `atom/<atom>/<atom>.yaml` (universal-per-atom) → overlay
    (`atom/<atom>/<atom>_<id>.yaml`). Each rung independently source-resolved.

    - `atom` is one of `text`, `image`, `audio`, `video`.
    - `overlay_id` is `None` or `<atom>` (returns the universal-per-atom common
      schema), or a full slash id (`text/data-table`, `image/photo`).

    Returns None when no layer exists for the requested overlay.
    """
    if atom not in VALID_ATOMS:
        return None
    sources = _sources(corpus_root)
    common_rel = f"atom/{atom}/{atom}.yaml"
    if overlay_id is None or overlay_id == atom:
        data = _read_yaml_first(sources, common_rel)
        return data
    if "/" in overlay_id:
        prefix, _, suffix = overlay_id.partition("/")
        if prefix != atom:
            return None
    else:
        suffix = overlay_id
    sub_rel = f"atom/{atom}/{atom}_{suffix}.yaml"
    if not any(s.exists(sub_rel) for s in sources):
        return None
    return _read_yaml_layered(sources, common_rel, sub_rel)


def list_atomic_overlays(
    corpus_root: Path, atom: str | None = None
) -> list[str]:
    """Return atomic-overlay ids in slash form (e.g. `text/data-table`) across both sources.

    `atom` restricts to a single atom; None walks all four. Common-guidance files
    (`text/text.yaml`, etc.) are excluded.
    """
    sources = _sources(corpus_root)
    atoms = [atom] if atom is not None else list(VALID_ATOMS)
    out: list[str] = []
    seen: set[str] = set()
    for a in atoms:
        for relpath in _discover_yaml(sources, f"atom/{a}"):
            # atom/text/text_data-table.yaml → "text/data-table"
            parts = relpath.split("/")
            if len(parts) != 3:
                continue
            stem = parts[2].removesuffix(".yaml")
            if stem == a:
                continue
            if not stem.startswith(f"{a}_"):
                continue
            sub_id = stem[len(a) + 1 :]
            slash_id = f"{a}/{sub_id}"
            if slash_id not in seen:
                seen.add(slash_id)
                out.append(slash_id)
    return out


# ---------- 3.0 pipeline-key aliasing (mode/draft.* → disposition/attest/derive) ---------- #
#
# The 3.0 documented mime-schema keys are `disposition:` (manifest|work — the container-vs-
# transport judgment, §7.1), `attest:` (the ingest attestations), and `derive:` (the derivation
# ops + their config). The 2.x keys `mode:`/`draft.*` KEEP WORKING via the aliasing below, so
# every existing member schema drafts UNMODIFIED (the record sweep to the new keys is a later
# migration phase). `normalize_pipeline_keys` back-fills the legacy view a schema doesn't carry,
# so downstream code (drafter dispatch, `produces_body`) reads one shape regardless of which
# keys a schema declares.


def pipeline_disposition(schema: dict[str, Any]) -> str:
    """The resolved `disposition` (§7.1): explicit `disposition:` wins; else a `derive`/`draft`
    strategy ending in `-manifest` implies `manifest`; else `work` (the default)."""
    explicit = str(schema.get("disposition") or "").strip().lower()
    if explicit in ("manifest", "work"):
        return explicit
    strategy = str(
        (schema.get("derive") or {}).get("strategy")
        or (schema.get("draft") or {}).get("strategy")
        or ""
    )
    return "manifest" if strategy.endswith("-manifest") else "work"


def _origin_overlay_ladder(id_: str, subtype: str | None) -> list[str]:
    """The overlay lookup ladder for a qualified origin block (spec §4.3.1, §7.2):
    subtype-qualified id FIRST (`<id>/<subtype>`, e.g. `google-takeout/gmail` — `gmail`
    is a SUBTYPE of the `google-takeout` producer, not a distinct overlay id), then the
    bare producer id as fallback. No subtype → a one-rung ladder. Mirrors
    `records._origin_overlay_ladder` (kept as separate tiny helpers rather than a shared
    import — each operates on this module's own block-field access shape)."""
    if subtype:
        return [f"{id_}/{subtype}", id_]
    return [id_]


def _origin_disposition(corpus_root: Path, post: Any) -> str | None:
    """The most-specific origin-overlay `disposition:` override (§7.2), or None when no
    qualified origin block's overlay ladder sets one. Mirrors `_origin_fingerprint`'s walk
    of qualified origin blocks (each ladder tried subtype-first, id-fallback) — first
    explicit value wins."""
    from corpus import records  # lazy: records imports schemas

    seen: set[tuple[str, str | None]] = set()
    for blk in records.iter_origin_blocks(post):
        id_ = str(blk.get("id") or "")
        if not id_:
            continue
        subtype = blk.get("subtype")
        key = (id_, subtype)
        if key in seen:
            continue
        seen.add(key)
        for overlay_id in _origin_overlay_ladder(id_, subtype):
            sch = load_origin_overlay_by_id(corpus_root, overlay_id)
            value = str((sch or {}).get("disposition") or "").strip().lower()
            if value in ("manifest", "work"):
                return value
    return None


def resolved_disposition_for_record(corpus_root: Path, post: Any) -> str:
    """The record's resolved `disposition` (§7.1, §1.2, 3.3) — the container-vs-transport
    judgment for THIS record: an origin overlay's `disposition:` override (§7.2) wins over
    the mime schema's declared/derived default (`pipeline_disposition`), which wins over the
    `work` fallback. Feeds the terminal-forms derivation (§7.8): a resolved `manifest` with
    no rendering contract declared stands under `form/manifest`, no overlay edit needed.

    **The single-track exception (§1.2, 3.12).** A promoted media track's member bytes are a
    single-track container of the source's own family, so its MIME is the *container* type
    (`video/mp4`, `audio/mp4`) — the same type its parent carries, and the type that declares
    `disposition: manifest`. Inheriting that would be wrong twice over: a roster naming its
    own single track has no member to promote, and the `manifest` disposition strips the
    content zone the track's own work (a transcript, frame markers) has to live in — which is
    the very thing promotion exists to give it. So the judgment resolves on **track count**
    rather than on MIME subtype: a media container rostering fewer than two members is a
    `work`. Before 3.12 the leaf carried an elementary-stream MIME and the subtype alone kept
    the two apart; it no longer can.
    """
    override = _origin_disposition(corpus_root, post)
    if override is not None:
        return override
    from corpus import records  # lazy: records imports schemas

    mime = records.media_type_for(post)
    if not mime:
        return "work"
    schema = load_mime_schema(corpus_root, mime)
    if not isinstance(schema, dict):
        return "work"
    disposition = pipeline_disposition(schema)
    if disposition == "manifest" and _is_single_track_media(mime, post):
        return "work"
    return disposition


#: Container MIMEs whose members are tracks (`stream_id=`), and which a promoted single-track
#: member therefore shares with its own parent — the collision the track-count rule resolves.
_TRACK_CONTAINER_MIMES = frozenset(
    {"video/mp4", "video/quicktime", "audio/mp4", "video/webm", "video/x-matroska"}
)


def _is_single_track_media(mime: str, post: Any) -> bool:
    """True when this record is a promoted track leaf rather than a container.

    **Not** a roster-row count, though that is the rule §1.2 states and it is what a reader
    would reach for first. Counting rows was tried and is wrong on the live fleet: the 102
    public video containers roster exactly ONE row each — not because they hold one track,
    but because their second track was unpromotable under the superseded pinned form and was
    declared as a bare fact instead. A count cannot tell "this holds one track" from "this
    holds two and one of them could not be embedded", so it would silently flip 102 genuine
    containers to `work` and dissolve the `container-carries-rendering` worklist that the
    transcript migration is tracked by.

    So the discriminator is the **positive fact** promotion writes and attestation never
    does: containment lineage through a `stream_id=` address. A record that came out of a
    container's track axis is a leaf; anything else keeps the disposition its mime declares,
    which for a standalone single-track capture is exactly the pre-3.12 behaviour — no
    regression on a population this amendment was not about.
    """
    if mime not in _TRACK_CONTAINER_MIMES:
        return False
    from corpus import records  # lazy: records imports schemas

    return any(
        uri.startswith("corpus://") and "stream_id=" in uri
        for uri in records.iter_origin_uris(post)
    )


_CUT_STRATEGY_IDS = ("scene-threshold@", "keyframe@", "fixed-interval@")


def cut_strategy(schema: dict[str, Any]) -> dict[str, Any] | None:
    """A mime schema's declared default `cut_strategy` (§7.2.1, 3.11), or None.

    `{id: <strategy>@<version>, **params}` — where a *timeline's* segment boundaries fall by
    default. Returned as a plain dict so the caller can stamp it; the `id` is validated for
    shape only (a versioned identifier), never against a fixed list, because the bundled
    strategies are a starting set and a corpus may declare its own."""
    raw = schema.get("cut_strategy")
    if not isinstance(raw, dict):
        return None
    sid = str(raw.get("id") or "").strip()
    if not sid or "@" not in sid:
        return None
    return {k: v for k, v in raw.items() if v is not None}


def _origin_cut_strategy(corpus_root: Path, post: Any) -> dict[str, Any] | None:
    """The most-specific origin-overlay `cut_strategy:` override (§7.2, 3.11), or None.

    Same ladder walk as `_origin_disposition` — first explicit value wins. This is the key
    the amendment exists for: cut sensitivity is a property of *what was recorded*, not of
    the codec, so a feature film, a YouTube upload and a TikTok can each declare their own."""
    from corpus import records  # lazy: records imports schemas

    seen: set[tuple[str, str | None]] = set()
    for blk in records.iter_origin_blocks(post):
        id_ = str(blk.get("id") or "")
        if not id_:
            continue
        subtype = blk.get("subtype")
        key = (id_, subtype)
        if key in seen:
            continue
        seen.add(key)
        for overlay_id in _origin_overlay_ladder(id_, subtype):
            sch = load_origin_overlay_by_id(corpus_root, overlay_id)
            value = cut_strategy(sch or {})
            if value is not None:
                return value
    return None


def resolve_cut_strategy_for_record(corpus_root: Path, post: Any) -> dict[str, Any] | None:
    """The cut strategy for THIS record — origin-overlay override over mime default (§7.2.1).

    **Call this at PROMOTION, against the CONTAINER's post, and stamp the result on the
    stream leaf.** It is deliberately not a reader-side lookup: a stream leaf's own origin is
    `corpus://<container>?stream_id=<N>`, which §12.15 states is capture lineage and never a
    lookup route — so resolving from the leaf would mean walking a containment chain of
    unbounded depth to reach an overlay. `promote` already holds both records, so it resolves
    once and writes the answer down (§7.2.1's `cutting:` stamp).

    Returns None when neither the overlay nor the mime schema declares one — which is
    *unresolved*, and the caller must not substitute a default of its own."""
    override = _origin_cut_strategy(corpus_root, post)
    if override is not None:
        return override
    from corpus import records  # lazy: records imports schemas

    mime = records.media_type_for(post)
    if not mime:
        return None
    schema = load_mime_schema(corpus_root, mime)
    if not isinstance(schema, dict):
        return None
    return cut_strategy(schema)


def normalize_pipeline_keys(schema: dict[str, Any]) -> dict[str, Any]:
    """Return `schema` with the legacy `mode`/`draft.*` view back-filled from the 3.0
    `disposition`/`derive.*` keys when a schema declares only the new form — so the drafter
    dispatch and `produces_body`, which read the legacy shape, work for a new-key schema with
    ZERO other changes. A schema already carrying the legacy keys is returned unchanged. The
    `attest:` key is declarative (the drafters emit the attestations) and needs no back-fill."""
    derive = schema.get("derive")
    disposition = schema.get("disposition")
    if not isinstance(derive, dict) and not disposition:
        return schema  # pure legacy schema — nothing to alias
    out = dict(schema)
    # `derive.strategy` → `draft.strategy`; `derive.members` (op config) → `draft.manifest`.
    if isinstance(derive, dict):
        legacy_draft = dict(out.get("draft") or {})
        if "strategy" in derive and "strategy" not in legacy_draft:
            legacy_draft["strategy"] = derive["strategy"]
        if isinstance(derive.get("members"), dict) and "manifest" not in legacy_draft:
            legacy_draft["manifest"] = derive["members"]
        if legacy_draft:
            out["draft"] = legacy_draft
    # `disposition` → `mode`: a `manifest` has no body-draft; a `work` builds a body.
    if disposition and "mode" not in out:
        out["mode"] = "manifest" if pipeline_disposition(schema) == "manifest" else "body-draft"
    return out


# ---------- form (section-scope) schemas ---------- #
#
# The `form` namespace (3.0, spec §7.8) declares record-scope structural-shape overlays bound
# on a qualified section opener (`<!--section conversation-->`). Layout is flat —
# `form/<id>.yaml` — with an optional universal `form/form.yaml` layering in first, exactly as
# `atom/<atom>/<atom>.yaml` layers under an atom overlay. The bundled forms (conversation,
# statement, receipt) ship in the package; a corpus may add its own or override.


@lru_cache(maxsize=256)
def load_form_overlay(corpus_root: Path, form_id: str) -> dict[str, Any] | None:
    """Return the layered form overlay for `form_id` (e.g. `conversation`), or None.

    Chain: universal `form/form.yaml` (optional) → `form/<id>.yaml`. Each rung
    independently source-resolved (corpus-local first, packaged second)."""
    form_id = (form_id or "").strip()
    if not form_id or "/" in form_id:
        return None
    sources = _sources(corpus_root)
    per_id_rel = f"form/{form_id}.yaml"
    if not any(s.exists(per_id_rel) for s in sources):
        return None
    universal_rel = "form/form.yaml"
    rungs = [universal_rel, per_id_rel] if any(
        s.exists(universal_rel) for s in sources
    ) else [per_id_rel]
    return _read_yaml_layered(sources, *rungs)


def list_form_overlays(corpus_root: Path) -> list[str]:
    """Return every form id declared under `form/` across both sources (the universal
    `form/form.yaml` excluded), sorted."""
    sources = _sources(corpus_root)
    out: list[str] = []
    for relpath in _discover_yaml(sources, "form"):
        stem = relpath.removeprefix("form/").removesuffix(".yaml")
        if "/" in stem or stem == "form":
            continue
        out.append(stem)
    return sorted(dict.fromkeys(out))


# ---------- terminal contracts (§7.8, 3.3) ---------- #
#
# A terminal contract (`form/passthrough`, `form/manifest`) prescribes the ABSENCE of a
# stored rendering rather than a shape (§7.8). The `terminal: true` overlay key is the ONE
# machine-readable marker — every resolution below keys off it, never a hardcoded form id,
# so a corpus registering its own terminal contract (a new overlay carrying the marker)
# works with zero code changes here.


def is_terminal_form(corpus_root: Path, form_id: str) -> bool:
    """True when `form_id` names a TERMINAL contract — its overlay carries `terminal: true`
    (§7.8, 3.3). An unresolvable or malformed overlay reads as non-terminal (parse-tolerant,
    like every other schema read in this module)."""
    overlay = load_form_overlay(corpus_root, form_id)
    return bool(isinstance(overlay, dict) and overlay.get("terminal") is True)


def resolve_mime_terminal_form(corpus_root: Path, mime: str) -> str | None:
    """Resolve the mime schema's `form:` default (§7.1, 3.3) to a TERMINAL form id, or None.

    Mime-level `form:` admits terminal contracts ONLY — a rendering contract is producer
    knowledge and rides the origin overlay's `form:` instead (§7.2), which also overrides
    this default either way. A mime `form:` naming a non-terminal (or unresolvable) form id
    is a schema-authoring mistake: logged as a warning and tolerantly rejected rather than
    raised, so one corpus's bad mime schema can't break ingest/health of an unrelated
    record."""
    schema = load_mime_schema(corpus_root, mime)
    if not isinstance(schema, dict):
        return None
    form = schema.get("form")
    if not isinstance(form, dict) or not form.get("id"):
        return None
    form_id = str(form["id"])
    if is_terminal_form(corpus_root, form_id):
        return form_id
    log.warning(
        "mime schema for %r declares form %r, but it is not a terminal contract — "
        "mime-level `form:` admits terminal contracts only (spec §7.1); ignoring.",
        mime,
        form_id,
    )
    return None


# ---------- fingerprint resolution ---------- #


def resolve_fingerprint(
    corpus_root: Path,
    media_type: str,
    post: Any,
    cli_override: bool | None = None,
) -> bool | str | list[str]:
    """Resolve the `fingerprint` schema knob for a record at draft time. Precedence,
    most-specific first: CLI override (`--fingerprint` / `--no-fingerprint`) >
    origin overlay > mime schema > ``False`` (spec §7.7). Returns the raw knob —
    `False` (off), `True` (on, each atom's default algorithm), or an algorithm
    name / list — which `fingerprint.algos_for_atom` then resolves per atom.
    Default off, so fingerprinting is opt-in (spec §7.2).
    """
    if cli_override is not None:
        return cli_override
    ov = _origin_fingerprint(corpus_root, post)
    if ov is not None:
        return ov
    mime_schema = load_mime_schema(corpus_root, media_type)
    if isinstance(mime_schema, dict) and "fingerprint" in mime_schema:
        return mime_schema["fingerprint"]
    return False


def resolve_default_origin(corpus_root: Path, media_type: str) -> str | None:
    """Return the mime schema's `default_origin` binding (spec §12.3.13): a corpus-local
    presumption — "an unattributed mbox in this corpus is presumed produced by this
    origin" — read from the resolved mime schema's `default_origin` key. `None` when the
    key is absent/blank or no mime schema resolves for `media_type`. The packaged mbox
    schema declares none (no producer knowledge ships with the package); a corpus states
    its own binding on its corpus-local copy of the schema."""
    schema = load_mime_schema(corpus_root, media_type)
    if not isinstance(schema, dict):
        return None
    value = str(schema.get("default_origin") or "").strip()
    return value or None


def _origin_declared_string_list(
    corpus_root: Path, origin_id: str, key: str
) -> list[str] | None:
    """Namespace walk (spec §12.3.13/§12.3.14) for a producer-declared STRING-LIST key
    (`strip_headers`, `strip_fields`): try `origin_id`, then each id-prefix ancestor
    (`a/b/c` → `a/b` → `a`), via `load_origin_overlay_by_id`. Returns the first
    ancestor's normalized declared list the moment one DECLARES `key` (present,
    list/tuple — an explicit empty list means "declared off", and is returned as `[]`,
    ending the walk same as any other declaration). Returns `None` when no overlay in the
    walk declares `key` at all — the caller's cue to fall back (or not, per the finality
    rule) rather than treat silence as an off declaration."""
    parts = [p for p in (origin_id or "").split("/") if p]
    if not parts:
        return None
    for i in range(len(parts), 0, -1):
        candidate_id = "/".join(parts[:i])
        overlay = load_origin_overlay_by_id(corpus_root, candidate_id)
        if not isinstance(overlay, dict):
            continue
        raw = overlay.get(key)
        if isinstance(raw, (list, tuple)):
            return [str(n).strip() for n in raw if str(n).strip()]
    return None


def _origin_strip_declaration(corpus_root: Path, origin_id: str) -> list[str] | None:
    """The `strip_headers` walk (spec §12.3.13) — see `_origin_declared_string_list`."""
    return _origin_declared_string_list(corpus_root, origin_id, "strip_headers")


def _origin_strip_fields_declaration(corpus_root: Path, origin_id: str) -> list[str] | None:
    """The `strip_fields` walk (spec §12.3.14) — see `_origin_declared_string_list`."""
    return _origin_declared_string_list(corpus_root, origin_id, "strip_fields")


def resolve_strip_headers(
    corpus_root: Path,
    media_type: str,
    cli_override: list[str] | None = None,
    *,
    origin_id: str | None = None,
) -> list[str]:
    """Resolve the mailbox chrome-strip header list (spec §12.3.13).

    The strip ACTION is a producer's knowledge, so it is declared on the producer's
    ORIGIN overlay, namespace-walked (`_origin_strip_declaration`); the mime schema
    carries only the corpus-local BINDING (`default_origin`) — "the corpus prescribes
    the behaviour, the tooling executes it."

    Precedence, most specific first:

    - CLI override (`mbox-split`/`mbox-window --strip`) — final, whatever it says.
    - `origin_id` given (a stamped origin: CLI `--origin`, or the ingest sidecar's
      `origin_schema`): walk ITS namespace and take that result as FINAL —
      `[]` when nothing in the walk declares. An origin id was given, so its silence is
      a decision, not an unknown; the walk never falls through to `default_origin`.
    - No `origin_id` given: resolve the mime schema's `default_origin` binding and walk
      ITS namespace the same way, or `[]` when unbound or nothing declares.
    """
    if cli_override is not None:
        return [str(n).strip() for n in cli_override if str(n).strip()]
    if origin_id is not None:
        return _origin_strip_declaration(corpus_root, origin_id) or []
    default_id = resolve_default_origin(corpus_root, media_type)
    if default_id is None:
        return []
    return _origin_strip_declaration(corpus_root, default_id) or []


def resolve_strip_fields(
    corpus_root: Path,
    media_type: str,
    cli_override: list[str] | None = None,
    *,
    origin_id: str | None = None,
) -> list[str]:
    """Resolve the JSON-family field-strip dotted-path list (spec §12.3.14) — the mailbox
    chrome strip's amendment to any JSON-family export. EXACTLY the `resolve_strip_headers`
    chain (`_origin_strip_fields_declaration` in place of the headers' walk):

    - CLI override — final, whatever it says.
    - `origin_id` given (a stamped origin): walk ITS namespace and take that result as
      FINAL — `[]` when nothing in the walk declares. No fallback to `default_origin`
      when an origin id was actually given — same finality as the header strip.
    - No `origin_id`: resolve the mime schema's `default_origin` binding and walk ITS
      namespace the same way, or `[]` when unbound or nothing declares.
    """
    if cli_override is not None:
        return [str(n).strip() for n in cli_override if str(n).strip()]
    if origin_id is not None:
        return _origin_strip_fields_declaration(corpus_root, origin_id) or []
    default_id = resolve_default_origin(corpus_root, media_type)
    if default_id is None:
        return []
    return _origin_strip_fields_declaration(corpus_root, default_id) or []


_VALID_PARTITION_GRAINS = ("month", "year")


def _validate_partition(raw: Any) -> dict[str, Any] | None:
    """Light structural validation of a `partition:` block (spec §12.3.14). Tolerant of
    unknown keys (e.g. `assemble:`, informational-only today) — only `grain` and, when
    present, each `eras` entry's `until`/`grain` are checked. An invalid block is logged
    and treated as NOT a declaration (the namespace walk keeps climbing past it) rather
    than raised — one corpus's bad overlay can't break `mbox-split` for an unrelated
    stream (parse-tolerant, like every other schema read in this module)."""
    if not isinstance(raw, dict):
        return None
    if raw.get("grain") not in _VALID_PARTITION_GRAINS:
        log.warning("partition: block has invalid/missing grain %r — ignoring", raw.get("grain"))
        return None
    eras = raw.get("eras")
    if eras is not None:
        if not isinstance(eras, list):
            log.warning("partition.eras must be a list — ignoring partition block")
            return None
        for era in eras:
            if (
                not isinstance(era, dict)
                or "until" not in era
                or era.get("grain") not in _VALID_PARTITION_GRAINS
            ):
                log.warning(
                    "partition.eras entry %r missing until/grain — ignoring partition block",
                    era,
                )
                return None
    if raw.get("undated", "standing") not in ("standing", "rolling"):
        log.warning(
            "partition.undated must be standing|rolling — ignoring partition block",
        )
        return None
    return raw


def _origin_partition_declaration(corpus_root: Path, origin_id: str) -> dict[str, Any] | None:
    """Namespace walk (mirrors `_origin_strip_declaration`) for the `partition:` block:
    try `origin_id`, then each id-prefix ancestor, first overlay whose `partition:` value
    validates (`_validate_partition`) wins. Unlike the strip's empty-list-is-a-declaration
    rule, there is no "declared off" partition state — an invalid or absent `partition:`
    key simply keeps the walk climbing."""
    parts = [p for p in (origin_id or "").split("/") if p]
    if not parts:
        return None
    for i in range(len(parts), 0, -1):
        candidate_id = "/".join(parts[:i])
        overlay = load_origin_overlay_by_id(corpus_root, candidate_id)
        if not isinstance(overlay, dict) or "partition" not in overlay:
            continue
        validated = _validate_partition(overlay["partition"])
        if validated is not None:
            return validated
    return None


def resolve_partition(
    corpus_root: Path,
    media_type: str,
    *,
    origin_id: str | None = None,
) -> dict[str, Any] | None:
    """Resolve the mailbox PARTITION SCHEDULE (spec §12.3.14) — the month/year temporal
    stratification a producer declares for its exports (`grain`, optional `eras` at their
    own grain, `undated` standing/rolling). Same resolution chain as
    `resolve_strip_headers`, minus the CLI override point (there is no `--partition`
    flag): `origin_id` given (a stamped origin) walks ITS namespace and that is FINAL —
    `None` when nothing in the walk declares, no fallback to the default binding; no
    `origin_id` resolves the mime schema's `default_origin` binding and walks THAT
    namespace instead. Returns the declared (validated) `partition:` dict, or `None` when
    nothing declares one — callers fall back to the pre-schedule year-grain behavior."""
    if origin_id is not None:
        return _origin_partition_declaration(corpus_root, origin_id)
    default_id = resolve_default_origin(corpus_root, media_type)
    if default_id is None:
        return None
    return _origin_partition_declaration(corpus_root, default_id)


def grain_for_year(eras: list[dict[str, Any]], default_grain: str, year: int) -> str:
    """The grain a member's YEAR resolves to under a `partition:` schedule (spec
    §12.3.14): the first era (sorted by `until` ascending) whose boundary the year is
    at-or-before wins; past every era, the schedule's top-level `grain` applies. Shared
    by every schedule-driven splitter (`mbox-split`, `period-split`) — the era-selection
    rule is one mechanism regardless of what's being partitioned (mbox members, files)."""
    for era in sorted(eras, key=lambda e: int(e["until"])):
        if year <= int(era["until"]):
            return str(era["grain"])
    return default_grain


def _origin_fingerprint(
    corpus_root: Path, post: Any
) -> bool | str | list[str] | None:
    """The most-specific origin-overlay `fingerprint` value, or None when no overlay
    sets it. Order: for each of the record's qualified origin blocks, its overlay ladder
    (subtype-qualified overlay first, id overlay fallback — `_origin_overlay_ladder`);
    then overlays whose match predicate matches an origin URI. First explicit value wins
    (so a specific `false` overrides a broader `true`)."""
    from corpus import records  # lazy: records imports schemas

    seen: set[tuple[str, str | None]] = set()
    overlay_ids_seen: set[str] = set()
    for blk in records.iter_origin_blocks(post):
        id_ = str(blk.get("id") or "")
        if not id_:
            continue
        subtype = blk.get("subtype")
        key = (id_, subtype)
        if key in seen:
            continue
        seen.add(key)
        for overlay_id in _origin_overlay_ladder(id_, subtype):
            overlay_ids_seen.add(overlay_id)
            sch = load_origin_overlay_by_id(corpus_root, overlay_id)
            if isinstance(sch, dict) and "fingerprint" in sch:
                return sch["fingerprint"]
    uris = list(records.iter_origin_uris(post))
    for id_, sch in origin_overlays_for_uris(corpus_root, uris):
        if id_ in overlay_ids_seen:
            continue
        if isinstance(sch, dict) and "fingerprint" in sch:
            return sch["fingerprint"]
    return None


# ---------- origin schemas ---------- #


def _iter_origin_overlay_paths(corpus_root: Path) -> list[str]:
    """Discover origin overlays from both sources.

    Flat layout (spec §12.3): `origin/<id>.yaml`. The reference's scheme-family
    `web/<id>.yaml` and `otherwise/<id>.yaml` are also walked as a back-compat read
    path. A producer NAMESPACE dir (any other nested dir under `origin/`, e.g.
    `origin/google-takeout/gmail.yaml`) holds that producer's SUBTYPE overlays (spec
    §4.3.1). The universal `origin/origin.yaml` (and the reference `web/web.yaml` /
    `otherwise/otherwise.yaml` common files) are filtered out — universal layers in via
    `_read_yaml_layered`.
    """
    sources = _sources(corpus_root)
    out: list[str] = []
    for relpath in _discover_yaml(sources, "origin"):
        parts = relpath.split("/")
        if relpath == "origin/origin.yaml":
            continue
        # Skip the reference's per-sub-namespace common files (web/web.yaml,
        # otherwise/otherwise.yaml) on the back-compat read path.
        if len(parts) == 3 and parts[2] == f"{parts[1]}.yaml":
            continue
        out.append(relpath)
    return out


# Scheme-family directories (spec §7.2) whose nested files still resolve to a BARE stem
# id — `web/<host>.yaml`, `otherwise/<id>.yaml` (the reference's back-compat layout). Any
# OTHER nested dir under `origin/` is a PRODUCER namespace whose files are SUBTYPE
# overlays (spec §4.3.1's `<id>/<subtype>` origin-opener grammar) — their overlay id is
# the COMPOUND `<producer>/<subtype>`.
_ORIGIN_SCHEME_FAMILY_DIRS = frozenset({"web", "otherwise"})


def _origin_id_from_relpath(relpath: str) -> str:
    """Map an origin-overlay relpath to its overlay id.

    Flat (`origin/<id>.yaml`) → `<id>`. Scheme-family dirs (`origin/web/<id>.yaml`,
    `origin/otherwise/<id>.yaml`) → the bare `<id>`. Any OTHER nested dir
    (`origin/<producer>/<subtype>.yaml`) → the COMPOUND `<producer>/<subtype>`."""
    parts = relpath.removeprefix("origin/").split("/")
    stem = parts[-1].removesuffix(".yaml")
    if len(parts) >= 2 and parts[0] not in _ORIGIN_SCHEME_FAMILY_DIRS:
        return "/".join([*parts[:-1], stem])
    return stem


@lru_cache(maxsize=64)
def load_origin_overlays(
    corpus_root: Path,
) -> list[tuple[str, dict[str, Any]]]:
    """Return `[(id, merged-schema), ...]` for every origin overlay across both sources.
    `id` is the bare id for a flat or scheme-family-dir overlay, or the COMPOUND
    `<producer>/<subtype>` for a producer-namespace subtype overlay (spec §4.3.1).

    Each overlay is layered: `origin/origin.yaml` (universal) → per-host file. Per-host
    overlays are corpus-local only in normal usage (the package ships only the
    universal), but the reference's nested layout is read tolerantly if present.

    Cached per `corpus_root` (like the other per-record loaders — schemas are immutable
    for the life of a process, `cache_clear()` invalidates); every caller iterates it
    read-only (`best_origin_overlay_for_uris`, `origin_overlays_for_uris`,
    `capture.recipes._overlay_section_for_url`), so this matters on a sweep or crawl that
    resolves the origin match for thousands of URIs in one process — the discovery walk +
    every overlay's YAML re-parse is otherwise redone on EVERY call.
    """
    sources = _sources(corpus_root)
    out: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for relpath in _iter_origin_overlay_paths(corpus_root):
        id_ = _origin_id_from_relpath(relpath)
        if id_ in seen:
            continue
        seen.add(id_)
        merged = _read_yaml_layered(sources, "origin/origin.yaml", relpath)
        out.append((id_, merged))
    return out


@lru_cache(maxsize=256)
def load_origin_overlay_by_id(
    corpus_root: Path, id_: str
) -> dict[str, Any] | None:
    """Return the layered origin overlay for `id_`, or None. `id_` may be a bare id
    (`origin/<id_>.yaml`, or a scheme-family-dir back-compat read) or a COMPOUND
    `<producer>/<subtype>` (`origin/<producer>/<subtype>.yaml`, spec §4.3.1) — the
    path join handles both shapes identically, no special-casing needed here."""
    sources = _sources(corpus_root)
    candidates = [
        f"origin/{id_}.yaml",
        f"origin/web/{id_}.yaml",        # back-compat read of the reference's layout
        f"origin/otherwise/{id_}.yaml",  # ditto
    ]
    for relpath in candidates:
        if any(s.exists(relpath) for s in sources):
            return _read_yaml_layered(sources, "origin/origin.yaml", relpath)
    return None


def origin_overlays_for_uris(
    corpus_root: Path, uris: list[str]
) -> list[tuple[str, dict[str, Any]]]:
    """Return `[(id, schema), ...]` for every origin overlay whose match predicate
    matches at least one URI in `uris`. Each overlay returned at most once.

    Match predicate (spec §7.2): web (http/https) overlays match by host —
    `applies_to.host_pattern` (str) and/or `applies_to.host_patterns` (list), with the
    `applies_to.include_subdomains` (bool) flag. Non-web scheme-family overlays (e.g.
    `imessage:`, a future `urn:`/`s3:`) match by URI scheme — `applies_to.scheme` (str)
    and/or `applies_to.schemes` (list), compared case-insensitively against the URI's
    scheme. An overlay may declare either or both.
    """
    if not uris:
        return []
    overlays = load_origin_overlays(corpus_root)
    matched: dict[str, dict[str, Any]] = {}
    for id_, schema in overlays:
        applies_to = schema.get("applies_to") or {}
        patterns: list[str] = []
        if "host_pattern" in applies_to:
            patterns.append(str(applies_to["host_pattern"]))
        if "host_patterns" in applies_to:
            patterns.extend(str(p) for p in applies_to["host_patterns"])
        schemes: set[str] = set()
        if "scheme" in applies_to:
            schemes.add(str(applies_to["scheme"]).lower())
        if "schemes" in applies_to:
            schemes.update(str(s).lower() for s in applies_to["schemes"])
        if not patterns and not schemes:
            continue
        include_subdomains = bool(applies_to.get("include_subdomains", False))
        for uri in uris:
            if not uri:
                continue
            if schemes and _uri_scheme(uri) in schemes:
                matched.setdefault(id_, schema)
                break
            if any(
                urlcanon.same_domain(uri, p, include_subdomains=include_subdomains)
                for p in patterns
            ):
                matched.setdefault(id_, schema)
                break
    return list(matched.items())


def _uri_scheme(uri: str) -> str:
    """The lowercased URI scheme (`imessage` from `imessage://chat/…`), or '' if none."""
    from urllib.parse import urlsplit

    try:
        return urlsplit(uri.strip()).scheme.lower()
    except Exception:
        return ""


def origin_ids_for_uris(corpus_root: Path, uris: list[str]) -> list[str]:
    return [id_ for id_, _ in origin_overlays_for_uris(corpus_root, uris)]


def best_origin_overlay_for_uris(corpus_root: Path, uris: list[str]) -> str | None:
    """Return the id of the single most-specific origin overlay matching at least one of
    `uris` — the winner-selection an origin-block qualification stamp needs (spec §7.2)
    when more than one overlay's predicate matches. `None` when nothing matches.

    Match predicate mirrors `origin_overlays_for_uris` (same overlay files, same host-
    pattern/`include_subdomains`/scheme cues). Winner selection mirrors
    `capture.recipes._overlay_section_for_url`'s established precedence, generalized to
    also rank scheme matches: the longest matching `host_pattern` string wins (most
    specific — an exact host match is necessarily at least as long as any pattern that
    reaches it only via `include_subdomains`); `host_pattern: "*"` is a lowest-priority
    catch-all (score 0); a scheme match scores by the scheme string's length (schemes bind
    the non-web families — `imessage:`, etc. — which don't carry a host, so they don't
    contend with host-pattern scores on the same uri in practice). Ties (equal score)
    break toward the lexicographically GREATEST id, exactly as the capture-recipe matcher
    does — deterministic, and consistent with the sibling matcher rather than a new rule.
    """
    if not uris:
        return None
    clean_uris = [str(u).strip() for u in uris if u]
    if not clean_uris:
        return None
    matches: list[tuple[int, str]] = []
    for id_, schema in load_origin_overlays(corpus_root):
        applies_to = schema.get("applies_to") or {}
        patterns: list[str] = []
        if "host_pattern" in applies_to:
            patterns.append(str(applies_to["host_pattern"]))
        if "host_patterns" in applies_to:
            patterns.extend(str(p) for p in applies_to["host_patterns"])
        schemes: set[str] = set()
        if "scheme" in applies_to:
            schemes.add(str(applies_to["scheme"]).lower())
        if "schemes" in applies_to:
            schemes.update(str(s).lower() for s in applies_to["schemes"])
        if not patterns and not schemes:
            continue
        include_subdomains = bool(applies_to.get("include_subdomains", False))
        best_for_overlay: int | None = None
        for uri in clean_uris:
            for pattern in patterns:
                if pattern == "*":
                    score = 0
                elif urlcanon.same_domain(uri, pattern, include_subdomains=include_subdomains):
                    score = len(pattern)
                else:
                    continue
                if best_for_overlay is None or score > best_for_overlay:
                    best_for_overlay = score
            if schemes and _uri_scheme(uri) in schemes:
                score = len(_uri_scheme(uri))
                if best_for_overlay is None or score > best_for_overlay:
                    best_for_overlay = score
        if best_for_overlay is not None:
            matches.append((best_for_overlay, id_))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


# ---------- context (annotation-zone) schemas ---------- #
#
# The `context` block (spec §4.3.3) draws its overlays from a reserved top-level `context/`
# umbrella. `issue` is one namespace here (`context/issue/`); `reference`, `aside`,
# `relation` join it.


@lru_cache(maxsize=256)
def load_context_schema(corpus_root: Path, class_id: str) -> dict[str, Any] | None:
    """Return the layered context overlay for `class_id` = `<namespace>/<id...>` (e.g.
    `issue/paywall`, `issue/partial-content/paywall`, `reference`).

    Chain: universal `context/<ns>/<ns>.yaml` → per-id `context/<ns>/<id>.yaml`. The
    universal ships in the package (for `issue`); per-id overlays may live in either source.
    Returns None only if neither rung resolves."""
    parts = [p for p in class_id.split("/") if p]
    if not parts:
        return None
    namespace = parts[0]
    rest = "/".join(parts[1:]) or namespace
    sources = _sources(corpus_root)
    universal_rel = f"context/{namespace}/{namespace}.yaml"
    per_id_rel = f"context/{namespace}/{rest}.yaml"
    have_universal = any(s.exists(universal_rel) for s in sources)
    have_per_id = any(s.exists(per_id_rel) for s in sources)
    if not have_universal and not have_per_id:
        return None
    rungs: list[str] = []
    if have_universal:
        rungs.append(universal_rel)
    if have_per_id and per_id_rel != universal_rel:
        rungs.append(per_id_rel)
    return _read_yaml_layered(sources, *rungs)


def list_context_ids(corpus_root: Path, namespace: str) -> list[str]:
    """Return all ids declared under the `context/<namespace>/` umbrella, sorted. The
    namespace's own universal `<namespace>.yaml` is excluded; nested subtype overlays
    `context/<ns>/<id>/<sub>.yaml` come back as `<id>/<sub>` slash ids."""
    sources = _sources(corpus_root)
    base = f"context/{namespace}"
    seen: dict[str, None] = {}
    for relpath in _discover_yaml(sources, base):
        if relpath == f"{base}/{namespace}.yaml":
            continue
        stem = relpath.removeprefix(f"{base}/").removesuffix(".yaml")
        if "/" in stem:
            head, _, tail = stem.partition("/")
            if tail == head:
                continue
        seen.setdefault(stem, None)
    return sorted(seen)


# Back-compat shims — `issue` is now the `issue` namespace of the context umbrella.


def load_issue_schema(corpus_root: Path, id_: str) -> dict[str, Any] | None:
    """Layered `issue` overlay — `context/issue/issue.yaml` → `context/issue/<id>.yaml`."""
    return load_context_schema(corpus_root, f"issue/{id_}")


def list_issue_ids(corpus_root: Path) -> list[str]:
    """All issue ids under `context/issue/` (the `issue.yaml` universal excluded)."""
    return list_context_ids(corpus_root, "issue")


def list_form_ids(corpus_root: Path) -> list[str]:
    """All rendering/terminal contract ids under `form/`, sorted — the shape-contract
    library's membership (spec §7.8). The universal `form/form.yaml` is excluded.

    These files ARE the registry: the spec deliberately carries no roster of them, so
    this is the discovery surface for what contracts a corpus can actually bind."""
    sources = _sources(corpus_root)
    seen: dict[str, None] = {}
    for relpath in _discover_yaml(sources, "form"):
        stem = relpath.removeprefix("form/").removesuffix(".yaml")
        if not stem or "/" in stem or stem == "form":
            continue
        seen.setdefault(stem, None)
    return sorted(seen)


# ---------------------------------------------------------------------------
# *(3.8)* Origin-overlay REGIONS and EXEMPLARS (spec §7.2)
# ---------------------------------------------------------------------------

#: Where a declared region renders. `subject` is what the page is FOR (the main span);
#: `framing` is the page's own statement about its subject and lands in a trailing span
#: (§4.3.2.1's cross-span significance order); `never` is chrome the body omits.
REGION_RENDERS = ("subject", "framing", "never")


def content_pin(post: Any) -> str:
    """The `blake3:<hex>` pin over a record's CONTENT ZONE (spec §7.2, exemplars).

    Deliberately not the record file. A `touch` entry appends on every pass, so a file hash
    would break on changes that teach nothing — and an exemplar exists to teach a shape, so
    the pin should move when, and only when, the shape does. Trailing whitespace is stripped
    for the same reason: an emitter's newline discipline is not a lesson.
    """
    from corpus import hashing

    body = (getattr(post, "content", "") or "").strip()
    return "blake3:" + hashing.hash_bytes(body.encode("utf-8"), also=())["blake3"]


def origin_regions(corpus_root: Path, origin_id: str) -> list[dict[str, Any]]:
    """The overlay's declared `regions:` (spec §7.2, 3.8), in declaration order — which is
    also the order framing regions take in the trailing span.

    Rows missing a `selector` or carrying an unknown `renders` are DROPPED rather than
    guessed at: a region declaration drives what does and does not enter a body, so a
    malformed row must not silently become `subject`. `origin_declaration_errors` is what
    reports them; this reader hands back only what is usable."""
    overlay = load_origin_overlay_by_id(corpus_root, origin_id) or {}
    out: list[dict[str, Any]] = []
    for raw in overlay.get("regions") or []:
        if not isinstance(raw, dict):
            continue
        selector = str(raw.get("selector") or "").strip()
        renders = str(raw.get("renders") or "").strip().lower()
        if not selector or renders not in REGION_RENDERS:
            continue
        row = {
            "role": str(raw.get("role") or "").strip(),
            "selector": selector,
            "renders": renders,
        }
        if lifts := str(raw.get("lifts_to") or "").strip():
            row["lifts_to"] = lifts
        out.append(row)
    return out


def origin_exemplars(corpus_root: Path, origin_id: str) -> list[dict[str, Any]]:
    """The overlay's declared `exemplars:` (spec §7.2, 3.8) — handcrafted records of THIS
    origin that show a shape rather than describing it.

    Returns rows as declared, normalized; freshness is `exemplar_status`'s job, because a
    stale exemplar must be REPORTED rather than quietly withheld: withholding it would look
    to the caller exactly like an origin that declares none."""
    overlay = load_origin_overlay_by_id(corpus_root, origin_id) or {}
    out: list[dict[str, Any]] = []
    for raw in overlay.get("exemplars") or []:
        if not isinstance(raw, dict):
            continue
        record = str(raw.get("record") or "").strip()
        if not record:
            continue
        row = {
            "record": record,
            "content": str(raw.get("content") or "").strip(),
            "shows": str(raw.get("shows") or "").strip(),
        }
        if address := str(raw.get("address") or "").strip():
            row["address"] = address
        out.append(row)
    return out


def _origin_ids_through_lineage(
    corpus_root: Path, post: Any, *, depth: int = 4, stop_at: str | None = None
) -> set[str]:
    """Every origin id this record carries, **plus its containment lineage's** (§8.1).

    A promoted member carries no host origin at all: its origin `uri:` is the lineage
    `corpus://<container>?<address>` and no host pattern matches it. Taken literally that
    would make a leaf permanently ineligible as an exemplar — and leaves are where the
    host-specific shape judgments actually land, since a member's rendering IS what the two-up
    tables, the captions, and the regions are about. So the walk follows the lineage the same
    way §8.1 says a normalize pass may: the container's origin is legitimate context for what
    the member is.

    **The PRIMARY lineage uri only, never the aliases**, which is the same line §7.2 already
    draws for route-keyed `form:` matching: *aliases are not gate-grade route evidence*. It is
    also what keeps this affordable. A member shared by many records accumulates one lineage
    alias per parent that promoted it — one public PNG is placed by 668 records — and a walk
    over every alias would load 668 records to answer a question the first one answers. The
    primary is the container this record was promoted FROM; the rest are other places the same
    bytes turned up, which is history, not parentage.

    `stop_at` short-circuits the moment that id is seen, because the caller's real question is
    a boolean (*is this record of origin X?*) and a set is just how the answer is spelled when
    it is not.

    Depth-bounded rather than trusting the chain to be acyclic (a member's container is older
    bytes, so it is — but the lineage is history a record could carry wrongly, and a cap is
    cheaper than proving it every time)."""
    from corpus import functional_uri as _furi
    from corpus import paths as _paths
    from corpus import records as _records

    out: set[str] = set()
    seen: set[str] = set()
    current: Any | None = post
    for _ in range(depth):
        if current is None:
            break
        for blk in _records.iter_origin_blocks(current):
            if oid := str(blk.get("id") or "").strip():
                out.add(oid)
        if stop_at and stop_at in out:
            return out
        uri = str(_records.primary_origin_uri(current) or "")
        if not uri.startswith("corpus://"):
            break
        try:
            parent = _furi.parse(uri).hash
        except Exception:
            break
        if not parent or parent in seen:
            break
        seen.add(parent)
        path = _paths.record_path(corpus_root, parent)
        if not path.is_file():
            break
        try:
            current = _records.load(path)
        except Exception:
            break
    return out


def exemplar_status(corpus_root: Path, origin_id: str, row: dict[str, Any]) -> tuple[str, str]:
    """`(state, detail)` for one declared exemplar — `ok` | `missing` | `stale` | `foreign`
    | `unpinned`.

    **Stale is an error, not a warning, and that is the whole design.** An exemplar teaches
    with the authority of a blessed example; one that has drifted teaches a shape the corpus
    has moved off, with the same authority. Clearing it is meant to be a deliberate act —
    re-read the record, confirm it still shows what its `shows` line claims, re-pin — which
    is the same argument §4.3.2.4 makes for the deconstructed import's match constraint: a
    reference that resolves to *something* forever is the dangerous kind.

    `foreign` enforces the same-origin rule. It is not pedantry: shape judgments are
    origin-specific, and same-origin is also what keeps an exemplar inside one hub, so
    tenancy holds with no second mechanism."""
    from corpus import paths as _paths
    from corpus import records as _records

    rid = str(row.get("record") or "")
    path = _paths.record_path(corpus_root, rid)
    if not path.is_file():
        return "missing", f"no record at {rid[:12]}…"
    try:
        post = _records.load(path)
    except Exception as exc:  # unreadable is as good as absent to a reader
        return "missing", f"{rid[:12]}… will not load: {exc}"
    ids = _origin_ids_through_lineage(corpus_root, post, stop_at=origin_id)
    if origin_id not in ids:
        return "foreign", (
            f"{rid[:12]}… carries origin {sorted(i for i in ids if i) or ['(none)']}, "
            f"not `{origin_id}` — an exemplar must be of its own origin"
        )
    declared = str(row.get("content") or "")
    if not declared:
        return "unpinned", f"{rid[:12]}… declares no `content:` pin"
    actual = content_pin(post)
    if actual != declared:
        return "stale", (
            f"{rid[:12]}… content zone is {actual[:19]}…, blessed as {declared[:19]}… — "
            f"re-read it, confirm it still shows what `shows` claims, then re-pin"
        )
    return "ok", ""


def origin_declaration_errors(corpus_root: Path, origin_id: str) -> list[str]:
    """Every malformed `regions:` row and every non-`ok` exemplar, as one list of messages.
    The single surface both `guidance` (at the point of consumption) and `health` (so it is
    visible without asking) report through."""
    overlay = load_origin_overlay_by_id(corpus_root, origin_id) or {}
    out: list[str] = []
    for i, raw in enumerate(overlay.get("regions") or [], 1):
        if not isinstance(raw, dict):
            out.append(f"regions[{i}]: not a mapping")
            continue
        if not str(raw.get("selector") or "").strip():
            out.append(f"regions[{i}] ({raw.get('role') or '?'}): no `selector`")
        renders = str(raw.get("renders") or "").strip().lower()
        if renders not in REGION_RENDERS:
            out.append(
                f"regions[{i}] ({raw.get('role') or '?'}): `renders: {renders or '(absent)'}` "
                f"is not one of {', '.join(REGION_RENDERS)}"
            )
    for row in origin_exemplars(corpus_root, origin_id):
        state, detail = exemplar_status(corpus_root, origin_id, row)
        if state != "ok":
            out.append(f"exemplar {state}: {detail}")
    return out
