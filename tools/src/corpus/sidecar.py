"""Container-member sidecar lift — the engine behind the origin overlay's `sidecar:`
declaration (spec/corpus.md §7.2, v41; §8.1 promote row; §12.3.14 pairing; §12.4.6).

A producer whose export pairs each primary member with a companion metadata member beside
it in the same container (a photo library's per-photo JSON, a mail export's per-message
metadata) declares the pairing and the lift on ITS origin overlay. The sidecar member stays
in the container — a roster row, `?path=`-addressable, resolvable, citable — but it is
**consumed**: at `corpus promote` its declared fields project onto the promoted primary's
lineage origin block, and it never becomes a record of its own.

**This module is producer- and format-agnostic by construction** (owner ruling,
2026-08-27). Its whole vocabulary is:

- a **pairing template** (`{member}` / `{stem}` / `{dir}` / `{name}`) expanded against the
  container roster — present-only, never invented;
- a parsed sidecar **tree walked by dotted path**;
- a **lift map** with two generic transforms — `omit` (a value filter) and `flags` (collapse
  boolean keys into one list of the set ones);
- **reference templates** resolved against the roster, stored as member addresses;
- a field **prefix** and an overlay **subtype**.

Nothing here knows what any field means, what producer wrote it, or what the primary member
is. A second producer joins by declaration alone — that is the genericity test, and the
reason no producer name may ever appear in this module, in `promote`, in `period-split`, in
`reattest`, or in `lint`.

Lifted fields are attested facts on the lineage origin block: `refresh_lineage_lift` (the
re-attest path) strips exactly the names the declaration owns and regenerates them from the
sidecar member, leaving every other field on the block — an operator's stamps — untouched.
"""

from __future__ import annotations

import json
import re
from collections.abc import Container, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import frontmatter

from corpus import functional_uri as furi
from corpus import paths, records, schemas

FORMATS = frozenset({"json"})
_PLACEHOLDER_RE = re.compile(r"\{(\w*)\}")
_PLACEHOLDERS = frozenset({"member", "stem", "dir", "name"})
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MISSING = object()


class DeclarationError(ValueError):
    """A malformed `sidecar:` declaration — reported at the point of consumption, never
    silently skipped (a lift that quietly didn't happen is worse than none)."""


# ---------- the declaration ---------- #


@dataclass(frozen=True)
class LiftEntry:
    field: str
    path: str | None = None
    omit: tuple[Any, ...] = ()
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceEntry:
    field: str
    templates: tuple[str, ...]
    when: str | None = None


@dataclass(frozen=True)
class Declaration:
    """One parsed, validated `sidecar:` block. `source_id` is the overlay id (the ladder
    rung) that declared it — what the promoted record's opener is qualified from."""

    source_id: str
    template: str
    export_level: frozenset[str]
    format: str
    prefix: str
    subtype: str | None
    lift: tuple[LiftEntry, ...]
    references: tuple[ReferenceEntry, ...]

    @property
    def qualified_id(self) -> str | None:
        """The `<id>/<subtype>` a promoted record's lineage origin block is qualified with
        (spec §4.3.1's opener grammar), or None when the declaration names no subtype."""
        return f"{self.source_id}/{self.subtype}" if self.subtype else None

    def owns(self, name: str) -> bool:
        """Whether an origin-block field name is this declaration's to strip and
        regenerate (spec §12.4.6): the whole `<prefix>` namespace — the prefix is what
        marks a field as the sidecar's, so a name a prior declaration lifted and the
        current one no longer does retires cleanly instead of lingering as a husk. A
        pairing-only declaration (no prefix) owns nothing."""
        return bool(self.prefix) and str(name).startswith(self.prefix)

    def reference_names(self) -> frozenset[str]:
        return frozenset(f"{self.prefix}{e.field}" for e in self.references)

    def sidecar_for(self, member: str, roster: Container[str]) -> str | None:
        """The roster path of `member`'s paired sidecar, or None when the template's
        expansion names no roster member (present-only; nothing is invented)."""
        candidate = expand_template(self.template, member)
        return candidate if candidate in roster and candidate != member else None

    def primary_of(self, sidecar: str, roster: Iterable[str]) -> str | None:
        """The primary member `sidecar` is the consumed sidecar OF (the refuse check at
        promote, the lint verdict), or None when no roster member pairs to it."""
        for member in roster:
            if member != sidecar and expand_template(self.template, member) == sidecar:
                return member
        return None


def expand_template(template: str, member: str) -> str:
    """Expand a pairing / reference template against one roster path: `{member}` is the
    full path, `{stem}` the path minus its final extension (basename-scoped: `a/b.c/x.HEIC`
    → `a/b.c/x`), `{dir}` the directory prefix (trailing `/` included, or empty), `{name}`
    the basename."""
    dir_, _, name = member.rpartition("/")
    dir_prefix = f"{dir_}/" if dir_ else ""
    stem_name = name.rsplit(".", 1)[0] if "." in name else name
    values = {
        "member": member,
        "stem": f"{dir_prefix}{stem_name}",
        "dir": dir_prefix,
        "name": name,
    }
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def _check_template(template: Any, where: str) -> str:
    if not isinstance(template, str) or not template.strip():
        raise DeclarationError(f"{where}: `template` must be a non-empty string")
    unknown = {m.group(1) for m in _PLACEHOLDER_RE.finditer(template)} - _PLACEHOLDERS
    if unknown:
        raise DeclarationError(
            f"{where}: unknown placeholder(s) {sorted(unknown)} in template {template!r} "
            f"(known: {', '.join(sorted(_PLACEHOLDERS))})"
        )
    if "{" not in template:
        raise DeclarationError(
            f"{where}: template {template!r} carries no placeholder — it would name the "
            f"same member for every primary"
        )
    return template.strip()


def _check_field_name(name: Any, where: str) -> str:
    if not isinstance(name, str) or not _FIELD_NAME_RE.match(name):
        raise DeclarationError(f"{where}: {name!r} is not a valid field name")
    return name


def _check_dotted(path: Any, where: str) -> str:
    if not isinstance(path, str) or not path.strip() or not all(
        seg.strip() for seg in path.split(".")
    ):
        raise DeclarationError(f"{where}: {path!r} is not a dotted sidecar path")
    return path.strip()


def parse_declaration(raw: Any, *, source_id: str) -> Declaration:
    """Validate and normalize one overlay's `sidecar:` value. Raises `DeclarationError`
    naming the offending key — a declaration is either whole or refused."""
    where = f"origin overlay {source_id!r} `sidecar:`"
    if not isinstance(raw, dict):
        raise DeclarationError(f"{where} must be a mapping")

    pairing = raw.get("pairing")
    if not isinstance(pairing, dict):
        raise DeclarationError(f"{where}: `pairing:` mapping with a `template` is required")
    template = _check_template(pairing.get("template"), f"{where} pairing")
    export_raw = pairing.get("export_level") or []
    if not isinstance(export_raw, (list, tuple)) or not all(
        isinstance(n, str) and n.strip() for n in export_raw
    ):
        raise DeclarationError(f"{where} pairing: `export_level` must be a list of member paths")
    export_level = frozenset(str(n).strip() for n in export_raw)

    fmt = str(raw.get("format") or "json").strip().lower()
    if fmt not in FORMATS:
        raise DeclarationError(
            f"{where}: `format: {fmt}` is not one of {', '.join(sorted(FORMATS))}"
        )

    lift_raw = raw.get("lift") or {}
    refs_raw = raw.get("references") or {}
    if not isinstance(lift_raw, dict):
        raise DeclarationError(f"{where}: `lift:` must be a mapping of field → dotted path")
    if not isinstance(refs_raw, dict):
        raise DeclarationError(f"{where}: `references:` must be a mapping of field → template")

    prefix = raw.get("prefix")
    subtype = raw.get("subtype")
    if lift_raw or refs_raw:
        if not isinstance(prefix, str) or not prefix.strip() or any(c.isspace() for c in prefix):
            raise DeclarationError(f"{where}: `prefix:` is required when `lift`/`references` lift")
        if not isinstance(subtype, str) or not subtype.strip() or "/" in subtype:
            raise DeclarationError(
                f"{where}: `subtype:` (one path segment) is required when `lift`/`references` "
                f"lift — the promoted record's lineage block is qualified with it"
            )
    prefix = (prefix or "").strip() if isinstance(prefix, str) else ""
    subtype = subtype.strip() if isinstance(subtype, str) and subtype.strip() else None

    lift: list[LiftEntry] = []
    for field_name, spec in lift_raw.items():
        fw = f"{where} lift.{field_name}"
        fname = _check_field_name(field_name, fw)
        if isinstance(spec, str):
            lift.append(LiftEntry(field=fname, path=_check_dotted(spec, fw)))
            continue
        if not isinstance(spec, dict):
            raise DeclarationError(f"{fw}: expected a dotted path or a mapping, got {spec!r}")
        flags = spec.get("flags")
        path = spec.get("path")
        if flags is not None:
            if path is not None or "omit" in spec:
                raise DeclarationError(f"{fw}: `flags` cannot combine with `path`/`omit`")
            if not isinstance(flags, (list, tuple)) or not flags:
                raise DeclarationError(f"{fw}: `flags` must be a non-empty list of sidecar keys")
            lift.append(
                LiftEntry(field=fname, flags=tuple(_check_dotted(f, fw) for f in flags))
            )
            continue
        omit = spec.get("omit") or []
        if not isinstance(omit, (list, tuple)):
            raise DeclarationError(f"{fw}: `omit` must be a list of values")
        lift.append(LiftEntry(field=fname, path=_check_dotted(path, fw), omit=tuple(omit)))

    references: list[ReferenceEntry] = []
    for field_name, spec in refs_raw.items():
        fw = f"{where} references.{field_name}"
        fname = _check_field_name(field_name, fw)
        if not isinstance(spec, dict):
            raise DeclarationError(f"{fw}: expected a mapping with `template`, got {spec!r}")
        t = spec.get("template")
        templates = tuple(t) if isinstance(t, (list, tuple)) else (t,)
        if not templates:
            raise DeclarationError(f"{fw}: `template` must be a string or a non-empty list")
        templates = tuple(_check_template(x, fw) for x in templates)
        when = spec.get("when")
        when = _check_dotted(when, fw) if when is not None else None
        references.append(ReferenceEntry(field=fname, templates=templates, when=when))

    seen: set[str] = set()
    for entry in (*lift, *references):
        if entry.field in seen:
            raise DeclarationError(f"{where}: field {entry.field!r} declared twice")
        seen.add(entry.field)

    return Declaration(
        source_id=source_id,
        template=template,
        export_level=export_level,
        format=fmt,
        prefix=prefix,
        subtype=subtype,
        lift=tuple(lift),
        references=tuple(references),
    )


# ---------- resolution (the §7.2 id/subtype ladder) ---------- #


def resolve_declaration(
    corpus_root: Path, origin_id: str, subtype: str | None = None
) -> Declaration | None:
    """The `sidecar:` declaration governing an origin id — namespace walk (spec §7.2,
    mirroring `schemas.resolve_partition`): `<id>/<subtype>` first, then `<id>` and each
    id-prefix ancestor; the first overlay that declares the key wins. None when nothing in
    the walk declares one. Raises `DeclarationError` for a malformed declaration."""
    full = f"{origin_id}/{subtype}" if subtype else origin_id
    parts = [p for p in (full or "").split("/") if p]
    for i in range(len(parts), 0, -1):
        rung = "/".join(parts[:i])
        overlay = schemas.load_origin_overlay_by_id(corpus_root, rung)
        if isinstance(overlay, dict) and "sidecar" in overlay:
            return parse_declaration(overlay["sidecar"], source_id=rung)
    return None


def declaration_for_container(
    corpus_root: Path, container_post: frontmatter.Post
) -> Declaration | None:
    """The declaration the CONTAINER's own qualified origin block(s) resolve to — latest
    block first (origin blocks append in capture order). A container with no qualified
    origin declares nothing."""
    for origin in reversed(list(records.iter_origin_blocks(container_post))):
        id_ = origin.get("id")
        if not id_:
            continue
        decl = resolve_declaration(corpus_root, str(id_), origin.get("subtype") or None)
        if decl is not None:
            return decl
    return None


def container_roster(container_post: frontmatter.Post) -> tuple[str, ...]:
    """Every `path=` member the container rosters, as bare roster paths."""
    out: list[str] = []
    for embed in records.iter_embed_blocks(container_post):
        addr = embed.get("address")
        for a in addr if isinstance(addr, list) else [addr]:
            a = str(a or "")
            if a.startswith("path=") and "&" not in a:
                out.append(a[len("path=") :])
    return tuple(out)


# ---------- projection ---------- #


def _walk(doc: Any, dotted: str) -> Any:
    value = doc
    for seg in dotted.split("."):
        if not isinstance(value, dict) or seg not in value:
            return _MISSING
        value = value[seg]
    return value


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _present(value: Any, omit: tuple[Any, ...]) -> Any:
    """Apply the present-only rule (spec §7.2): a missing, `null`, empty, or `false` value
    — or one the entry omits — lifts nothing. Scalars lift as they are; a list keeps only
    its non-omitted scalar items (a nested object is never lifted whole)."""
    if value is _MISSING or value is None or value is False:
        return None
    if isinstance(value, dict):
        return None
    if isinstance(value, list):
        items = [
            v
            for v in value
            if _is_scalar(v) and v not in omit and v is not False and v != ""
        ]
        return items or None
    if not _is_scalar(value) or value in omit:
        return None
    if isinstance(value, str) and value == "":
        return None
    return value


def project(
    decl: Declaration, doc: Any, member: str, roster: Container[str]
) -> dict[str, Any]:
    """Project one parsed sidecar `doc` for `member` into prefixed origin-block fields, in
    declaration order: every `lift` entry, then every `references` entry resolved against
    `roster`. Present-only throughout."""
    out: dict[str, Any] = {}
    for entry in decl.lift:
        if entry.flags:
            set_ = [f for f in entry.flags if _walk(doc, f) is True]
            if set_:
                out[f"{decl.prefix}{entry.field}"] = set_
            continue
        assert entry.path is not None
        value = _present(_walk(doc, entry.path), entry.omit)
        if value is not None:
            out[f"{decl.prefix}{entry.field}"] = value
    for ref in decl.references:
        if ref.when is not None:
            gate = _walk(doc, ref.when)
            if gate is _MISSING or not gate:
                continue
        for template in ref.templates:
            candidate = expand_template(template, member)
            if candidate != member and candidate in roster:
                out[f"{decl.prefix}{ref.field}"] = f"path={candidate}"
                break
    return out


def read_sidecar(
    container_path: Path,
    container_media_type: str,
    sidecar_path: str,
    *,
    el_addressing: dict | None = None,
) -> Any:
    """Stream the sidecar member out of its container and parse it (`format: json`).
    Raises `ValueError` for bytes that are not a JSON document."""
    from corpus import containment

    with containment.open_member_stream(
        container_path, container_media_type, f"path={sidecar_path}", el_addressing=el_addressing
    ) as fp:
        data = fp.read()
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"sidecar {sidecar_path!r} is not JSON: {exc}") from exc


def apply_lift(fields: dict[str, Any], decl: Declaration, projected: dict[str, Any]) -> bool:
    """Strip every declaration-owned name (the `<prefix>` namespace) from an origin
    block's `fields` and write the fresh projection — the strip + regenerate of spec
    §12.4.6, touching nothing else on the block. Returns True when the block changed."""
    before = list(fields.items())
    for name in [k for k in fields if decl.owns(k)]:
        del fields[name]
    fields.update(projected)
    return list(fields.items()) != before


def qualify_block(block: dict[str, Any], decl: Declaration) -> bool:
    """Qualify a lineage origin block's opener with the declaration's `<id>/<subtype>`
    (spec §7.2). A bare block, or one already carrying this producer's id, is qualified; a
    block qualified with some OTHER producer's id is left alone. Returns True on change."""
    if not decl.qualified_id:
        return False
    id_, subtype = records._split_qualifier(decl.qualified_id)
    if block.get("id") not in (None, "", id_):
        return False
    if block.get("id") == id_ and block.get("subtype") == subtype:
        return False
    block["id"] = id_
    block["subtype"] = subtype
    return True


# ---------- lineage (the re-attest path) ---------- #


def lineage_member(block: dict[str, Any]) -> tuple[str, str] | None:
    """`(container id, roster path)` when the origin block's `uri:` is a containment
    lineage `corpus://<container>?path=<member>` (spec §8.1), else None. A multi-uri block
    yields its first such lineage."""
    uri = (block.get("fields") or {}).get("uri")
    for u in uri if isinstance(uri, list) else [uri]:
        u = str(u or "").strip()
        if not u.startswith(f"{furi.SCHEME}://"):
            continue
        try:
            parsed = furi.parse(u)
        except ValueError:
            continue
        if parsed.is_bare or len(parsed.params) != 1:
            continue
        key, value = parsed.params[0]
        if key == "path" and value:
            return parsed.hash, furi.unquote_value(value)
    return None


@lru_cache(maxsize=256)
def _load_cached(record_file: str, _mtime_ns: int, _size: int) -> frontmatter.Post:
    return records.load(Path(record_file))


def load_container(corpus_root: Path, container_id: str) -> frontmatter.Post | None:
    """The container's record, or None when it does not exist. Cached on the file's
    (path, mtime, size) so a lint sweep over thousands of promoted members parses each
    container once rather than once per member."""
    record_file = paths.record_path(corpus_root, container_id)
    try:
        st = record_file.stat()
    except OSError:
        return None
    return _load_cached(str(record_file), st.st_mtime_ns, st.st_size)


def consumed_sidecar_primary(
    corpus_root: Path, container_post: frontmatter.Post, member: str
) -> str | None:
    """The primary `member` is the consumed sidecar of, under the container's declaration
    — None when the container declares no sidecar or `member` pairs to no primary."""
    decl = declaration_for_container(corpus_root, container_post)
    if decl is None:
        return None
    return decl.primary_of(member, container_roster(container_post))


def refresh_lineage_lift(
    post: frontmatter.Post, corpus_root: Path, *, notes: list[str] | None = None
) -> bool:
    """Regenerate the container-member sidecar lift on every lineage origin block of
    `post` (spec §12.4.6, v41): resolve the container from the lineage `uri:`, strip the
    declaration-owned names, project the sidecar afresh, qualify the opener. A block whose
    container declares no sidecar, or whose member pairs to none, keeps every field it has
    (nothing is owned, so nothing is stripped). Returns True when any block changed.
    Raises `DeclarationError` for a malformed declaration and `ArtifactMissing` when the
    container's bytes are unreachable; `notes` collects non-fatal skips."""
    from corpus import containment
    from corpus import mime as mime_mod

    changed = False
    for block in records.iter_origin_blocks(post):
        lineage = lineage_member(block)
        if lineage is None:
            continue
        container_id, member = lineage
        container_post = load_container(corpus_root, container_id)
        if container_post is None:
            if notes is not None:
                notes.append(f"lineage container {container_id[:12]}… has no record")
            continue
        decl = declaration_for_container(corpus_root, container_post)
        if decl is None:
            continue
        roster = container_roster(container_post)
        sidecar_path = decl.sidecar_for(member, roster)
        fields = block.setdefault("fields", {})
        if sidecar_path is None:
            changed |= apply_lift(fields, decl, {})
            continue
        container_media_type = records.media_type_for(container_post)
        container_path = containment.ensure_local_bytes(
            corpus_root, container_id, mime_mod.extension_for(container_media_type)
        )
        try:
            doc = read_sidecar(
                container_path,
                container_media_type,
                sidecar_path,
                el_addressing=records.el_addressing(container_post),
            )
        except (ValueError, OSError) as exc:
            if notes is not None:
                notes.append(f"sidecar {sidecar_path!r} not lifted ({exc})")
            continue
        changed |= apply_lift(fields, decl, project(decl, doc, member, roster))
        changed |= qualify_block(block, decl)
    return changed
