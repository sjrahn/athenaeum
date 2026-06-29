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
- `composite/<namespace>/<namespace>.yaml` (+ `<sub_id>.yaml`) — user-defined
  classification namespaces (the `classify` block). **Per-corpus concern; not packaged.**
- `context/<namespace>/<namespace>.yaml` (+ `<id>.yaml`) — annotation-zone overlays (the
  `context` block, spec §4.3.3): `issue`, `reference`, `note`, … `context/issue/<id>.yaml`
  carries issue overlays — the universal `context/issue/issue.yaml` ships in the package;
  per-id overlays may live in either source.

Why the split: `mime` and `atom` describe *format and fidelity* (a PDF is a PDF;
a transcript is a transcript) — universal. `origin` describes *sources of
retrieval*, `composite` describes *classification axes*, and `context` describes
*observations about a record* — all corpus-specific decisions.

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

# Namespaces reserved by the spec — the four top-level directories under `schema/`
# (spec §3).
_RESERVED_NAMESPACES = {"mime", "origin", "atom", "composite", "context"}

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
    load_classification_schema.cache_clear()
    load_origin_overlay_by_id.cache_clear()
    load_context_schema.cache_clear()


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


# ---------- composite classification schemas (corpus-local only) ---------- #


def _classification_namespaces(corpus_root: Path) -> list[str]:
    """Return ids of user-defined classification namespaces under
    `schema/composite/` (corpus-local only — composite namespaces are never bundled).
    The `issue` subdirectory is excluded — issue overlays have their own loader.
    """
    schema_dir = corpus_root / "schema" / "composite"
    if not schema_dir.is_dir():
        return []
    out: list[str] = []
    for path in sorted(schema_dir.iterdir()):
        if not path.is_dir() or path.name == "issue":
            continue
        if (path / f"{path.name}.yaml").is_file():
            out.append(path.name)
    return out


def list_classifications(corpus_root: Path) -> list[str]:
    """Return the names of composite namespaces the corpus declares (sorted)."""
    return _classification_namespaces(corpus_root)


@lru_cache(maxsize=256)
def load_classification_schema(
    corpus_root: Path, class_id: str
) -> dict[str, Any] | None:
    """Return the composite classification overlay for `class_id`, or None.

    `class_id` accepts either `<ns>` (the namespace base) or `<ns>/<sub_id>`
    (a subclass). Composite schemas live corpus-local only — no packaged fallback.
    The namespace base is NOT deep-merged under a subclass; callers compose as
    needed (mostly because composite namespaces compose flatly, not hierarchically).
    """
    parts = [p for p in class_id.split("/") if p]
    if not parts:
        return None
    namespace = parts[0]
    target = parts[1] if len(parts) >= 2 else namespace
    path = corpus_root / "schema" / "composite" / namespace / f"{target}.yaml"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_classification_subclasses(
    corpus_root: Path, namespace: str
) -> list[str]:
    """Return subclass ids under `namespace`, sorted. The namespace base is excluded."""
    d = corpus_root / "schema" / "composite" / namespace
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.yaml") if p.stem != namespace)


def load_classification_subclass(
    corpus_root: Path, namespace: str, sub_id: str
) -> dict[str, Any] | None:
    return load_classification_schema(corpus_root, f"{namespace}/{sub_id}")


def iter_classification_subclasses(
    corpus_root: Path, namespace: str
) -> list[tuple[str, dict[str, Any]]]:
    """Return `[(sub_id, schema), ...]` for every subclass under `namespace`."""
    out: list[tuple[str, dict[str, Any]]] = []
    for sub_id in list_classification_subclasses(corpus_root, namespace):
        sub_schema = load_classification_subclass(corpus_root, namespace, sub_id)
        if sub_schema is None:
            continue
        out.append((sub_id, sub_schema))
    return out


def _load_all_classification_schemas(
    corpus_root: Path,
) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for class_id in list_classifications(corpus_root):
        schema = load_classification_schema(corpus_root, class_id)
        if schema is None:
            continue
        out.append((class_id, schema))
    return out


def classifications_by_kind(
    corpus_root: Path, kind: str, *, media_type: str | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """Return `[(class_id, schema)]` for every composite whose `kind:` matches.

    `media_type` is honored only for `kind: mechanical`.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    kind_l = kind.lower()
    for class_id, schema in _load_all_classification_schemas(corpus_root):
        if str(schema.get("kind", "")).lower() != kind_l:
            continue
        if kind_l == "mechanical" and media_type is not None:
            applies = (schema.get("applies_to") or {}).get("content_types") or []
            if media_type not in applies:
                continue
        out.append((class_id, schema))
    return out


def mechanical_classifications_for(
    corpus_root: Path, media_type: str
) -> list[tuple[str, dict[str, Any]]]:
    """Return mechanical composites (including their subclasses, merged) whose
    `applies_to.content_types` includes `media_type`. The namespace base's `kind`
    propagates to each subclass via deep-merge."""
    out: list[tuple[str, dict[str, Any]]] = []
    for ns_id, ns_schema in _load_all_classification_schemas(corpus_root):
        if str(ns_schema.get("kind", "")).lower() != "mechanical":
            continue
        ns_applies = (ns_schema.get("applies_to") or {}).get("content_types") or []
        if not ns_applies or media_type in ns_applies:
            out.append((ns_id, ns_schema))
        for sub_id, sub_schema in iter_classification_subclasses(corpus_root, ns_id):
            merged = _deep_merge(ns_schema, sub_schema)
            sub_applies = (merged.get("applies_to") or {}).get("content_types") or []
            if not sub_applies or media_type in sub_applies:
                out.append((f"{ns_id}/{sub_id}", merged))
    return out


def iter_all_classifications(
    corpus_root: Path,
) -> list[tuple[str, dict[str, Any]]]:
    """Return `[(class_id, merged_schema)]` for **every** composite overlay — each namespace
    base AND every subclass (the base deep-merged under the subclass) — regardless of `kind`.

    The base+subclass walk `mechanical_classifications_for` does, minus the MIME gate, so a
    caller that keys on any field (e.g. `classify_when`, spec §7.4) sees the subclass overlays
    the kind-filtered loaders skip — `interpretive_classifications_for` walks namespace **bases
    only**, which would miss `source/majority-report`-style subclasses."""
    out: list[tuple[str, dict[str, Any]]] = []
    for ns_id, ns_schema in _load_all_classification_schemas(corpus_root):
        out.append((ns_id, ns_schema))
        for sub_id, sub_schema in iter_classification_subclasses(corpus_root, ns_id):
            out.append((f"{ns_id}/{sub_id}", _deep_merge(ns_schema, sub_schema)))
    return out


def resolve_fingerprint(
    corpus_root: Path,
    media_type: str,
    post: Any,
    cli_override: bool | None = None,
) -> bool | str | list[str]:
    """Resolve the `fingerprint` schema knob for a record at draft time. Precedence,
    most-specific first: CLI override (`--fingerprint` / `--no-fingerprint`) >
    composite classification > mime schema > ``False``. Returns the raw knob — `False`
    (off), `True` (on, each atom's default algorithm), or an algorithm name / list —
    which `fingerprint.algos_for_atom` then resolves per atom. Default off, so
    fingerprinting is opt-in (spec §7.2).

    Only what is knowable AT DRAFT is consulted: the mime default, **mechanical**
    composites (deterministic from the MIME), and any `<!--classify-->` blocks already
    on the record. Interpretive composites (e.g. `composite/document`) are assigned by
    the normalizer *after* draft, so their override takes effect on a later recompile
    (`corpus redraft`) once the classify block is present."""
    if cli_override is not None:
        return cli_override
    comp = _composite_fingerprint(corpus_root, media_type, post)
    if comp is not None:
        return comp
    mime_schema = load_mime_schema(corpus_root, media_type)
    if isinstance(mime_schema, dict) and "fingerprint" in mime_schema:
        return mime_schema["fingerprint"]
    return False


def _composite_fingerprint(
    corpus_root: Path, media_type: str, post: Any
) -> bool | str | list[str] | None:
    """The most-specific composite `fingerprint` value, or None when no composite sets
    it. Order: already-assigned classify blocks (subclass then namespace base), then
    mechanical composites applicable to `media_type`. First explicit value wins (so a
    specific `false` overrides a broader `true`)."""
    from corpus import records  # lazy: records imports schemas

    for blk in records.iter_classify_blocks(post):
        ns = str(blk.get("namespace") or "")
        cid = str(blk.get("id") or ns)
        class_ids = ([f"{ns}/{cid}"] if cid and cid != ns else []) + ([ns] if ns else [])
        for class_id in class_ids:
            sch = load_classification_schema(corpus_root, class_id)
            if isinstance(sch, dict) and "fingerprint" in sch:
                return sch["fingerprint"]
    for _class_id, sch in mechanical_classifications_for(corpus_root, media_type):
        if isinstance(sch, dict) and "fingerprint" in sch:
            return sch["fingerprint"]
    return None


def interpretive_classifications_for(
    corpus_root: Path, media_type: str | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """Interpretive composites do not gate by MIME; `media_type` is accepted for
    signature parity but ignored."""
    return classifications_by_kind(corpus_root, "interpretive", media_type=media_type)


# ---------- origin schemas ---------- #


def _iter_origin_overlay_paths(corpus_root: Path) -> list[str]:
    """Discover origin per-host overlays from both sources.

    Flat layout (spec §12.3): `origin/<id>.yaml`. The reference's `web/<id>.yaml` and
    `otherwise/<id>.yaml` are also walked as a back-compat read path. The universal
    `origin/origin.yaml` (and the reference `web/web.yaml` / `otherwise/otherwise.yaml`
    common files) are filtered out — universal layers in via `_read_yaml_layered`.
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


def _origin_id_from_relpath(relpath: str) -> str:
    """Map `origin/<id>.yaml` or `origin/web/<id>.yaml` → `<id>`."""
    stem = relpath.rsplit("/", 1)[-1].removesuffix(".yaml")
    return stem


def load_origin_overlays(
    corpus_root: Path,
) -> list[tuple[str, dict[str, Any]]]:
    """Return `[(id, merged-schema), ...]` for every origin overlay across both sources.

    Each overlay is layered: `origin/origin.yaml` (universal) → per-host file. Per-host
    overlays are corpus-local only in normal usage (the package ships only the
    universal), but the reference's nested layout is read tolerantly if present.
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
    """Return the layered origin overlay for `id_`, or None."""
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


# ---------- context (annotation-zone) schemas ---------- #
#
# The `context` block (spec §4.3.3) draws its overlays from a reserved top-level `context/`
# umbrella — separate from `composite/` (which is classifications only). `issue` is one
# namespace here (`context/issue/`); `reference`, `note`, `aside`, `relation` join it.


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
