"""Record I/O — frontmatter + zone-aware block parse/emit (spec §4).

A record is a markdown file with YAML frontmatter (spec §4.2) plus a body with three
zones (spec §4.3): metadata (artifact + origin + classify + embed), content
(section + segment), and annotations (issue).

This module owns the **metadata** and **annotation** zones — including embeds
(reconciliation #1 vs the reference, which routed `<!--embed--><br>` through `segments.py` as a
content-zone block). The content zone is parsed/emitted by `segments.py`.

Exposes:

- `load(path)` — parse a record into a `frontmatter.Post` with a unified `post.metadata`
  view that merges all block fields into the top-level dict under namespaced keys
  (`_artifact`, `_origins`, `_classifies`, `_embeds`, `_issues`). The remaining
  `post.content` carries the content zone only.
- `dump(post, path)` — write `post` back to disk in canonical layout: frontmatter →
  metadata-zone blocks (artifact, origins, classifies, embeds) → content body →
  annotation-zone blocks (issues).
- Accessors: `media_type_for`, `title_for`, `artifact_block`, `iter_origin_blocks`,
  `iter_classify_blocks`, `iter_embed_blocks`, `iter_issue_blocks`, `primary_origin_uri`.
- Mutators: `set_artifact_block`, `append_origin_block`, `append_classify_block`,
  `append_embed_block`, `append_issue_block`.
- Hash helpers: `parse_hash(s)`, `format_hash(algo, hex_value)`.
- Stub creation: `stub_frontmatter(...)` returns the minimal frontmatter dict; the
  caller emits the artifact + origin blocks via the mutators.

Frontmatter core fields (spec §4.2 — the only fields, in spec order):
    id, description, status, transport, canonical, perceptual, touch, visibility

Block grammar (spec §4.3):
    Metadata zone:    <!--artifact <mime-type>-->     (exactly 1)
                      <!--origin [<id>[/<subtype>]]--> (1..N)
                      <!--classify <namespace>/<id>[/<subtype>]--> (0..N)
                      <!--embed <mime-type>-->         (0..N)
    Content zone:     <!--section [<ns>/<id>]-->       (0..N)  or
                      <!--segment <atom>[/<id>]-->     (0..N) sectionless
    Annotations zone: <!--issue <id>[/<subtype>]-->    (0..N)
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from . import paths

# Spec §4.2 core-fields order.
_CORE_FIELD_ORDER = [
    "id",
    "description",
    "status",
    "transport",
    "canonical",
    "perceptual",
    "touch",
    "visibility",
]

# Block opener prefixes.
_ARTIFACT_OPENER = "<!--artifact"
_ORIGIN_OPENER = "<!--origin"
_CLASSIFY_OPENER = "<!--classify"
_EMBED_OPENER = "<!--embed"
_SECTION_OPENER = "<!--section"
_SEGMENT_OPENER = "<!--segment"
_ISSUE_OPENER = "<!--issue"
_BLOCK_CLOSER = "-->"

# Metadata-zone block openers (the openers that live before the content zone).
# Reconciliation #1: embed is here, NOT in the content zone (spec §4.3 4/2/1).
_METADATA_OPENERS = (_ARTIFACT_OPENER, _ORIGIN_OPENER, _CLASSIFY_OPENER, _EMBED_OPENER)


def _now_iso() -> str:
    """ISO-8601 in the spec's `Z`-suffix style."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------- hash helpers ---------- #


def parse_hash(s: str) -> tuple[str, str]:
    """Parse an `<algo>:<hex>` hash string. Returns `(algo, hex_value)`.

    Raises ValueError if the string has no colon (single-algo form is only valid for
    the bare `id` field which is invariant blake3 per spec §4.2).
    """
    if ":" not in s:
        raise ValueError(f"hash {s!r} missing <algo>:<hex> prefix")
    algo, hex_value = s.split(":", 1)
    return algo, hex_value


def format_hash(algo: str, hex_value: str) -> str:
    """Build an `<algo>:<hex>` hash string."""
    return f"{algo}:{hex_value}"


# ---------- read / write ---------- #


def load(path: Path) -> frontmatter.Post:
    """Read a record from `path` and return a Post with a unified metadata view.

    Parses YAML frontmatter, then walks the body's three zones:

    - Metadata zone (artifact + origin + classify + embed blocks). Block fields are
      merged into `post.metadata` under namespaced keys (`_artifact`, `_origins`,
      `_classifies`, `_embeds`).
    - Content zone (section/segment blocks). Left in `post.content` verbatim for
      `segments.iter_blocks` to consume.
    - Annotations zone (issue blocks). Merged into `post.metadata["_issues"]` as a
      list of dicts.

    After load, `post.content` carries the content zone only.
    """
    post = frontmatter.load(path)
    body = post.content or ""
    metadata_blocks, after_metadata = _extract_metadata_blocks(body)
    content_body, annotations_body = _split_annotations(after_metadata)
    issue_blocks = _extract_issue_blocks(annotations_body)

    post.metadata["_artifact"] = metadata_blocks.get("artifact")
    post.metadata["_origins"] = metadata_blocks.get("origins", [])
    post.metadata["_classifies"] = metadata_blocks.get("classifies", [])
    post.metadata["_embeds"] = metadata_blocks.get("embeds", [])
    post.metadata["_issues"] = issue_blocks

    post.content = content_body
    return post


def dump(post: frontmatter.Post, path: Path) -> None:
    """Write `post` to `path` in canonical zone order.

    Order:
        frontmatter (core fields only, in spec order)
        metadata zone:     <!--artifact-->, <!--origin-->*, <!--classify-->*, <!--embed-->*
        content zone:      post.content verbatim (section/segment)
        annotations zone:  <!--issue-->*
    """
    paths.ensure_parent(path)

    artifact = post.metadata.get("_artifact")
    origins = post.metadata.get("_origins") or []
    classifies = post.metadata.get("_classifies") or []
    embeds = post.metadata.get("_embeds") or []
    issues = post.metadata.get("_issues") or []

    # Build core frontmatter — only spec-defined fields, in spec order.
    core: dict[str, Any] = {}
    for key in _CORE_FIELD_ORDER:
        if key in post.metadata:
            core[key] = post.metadata[key]
    fm_text = _dump_yaml_block(core)

    # Build the metadata zone — artifact, origins, classifies, embeds.
    metadata_parts: list[str] = []
    if artifact:
        metadata_parts.append(_emit_artifact_block(artifact))
    for origin in origins:
        metadata_parts.append(_emit_origin_block(origin))
    for classify in classifies:
        metadata_parts.append(_emit_classify_block(classify))
    for embed in embeds:
        metadata_parts.append(_emit_embed_block(embed))
    metadata_zone = "\n\n".join(metadata_parts)

    # Content zone — verbatim from post.content (segments.py owns this).
    content = (post.content or "").strip("\n")

    # Annotations zone — issues.
    annotation_parts = [_emit_issue_block(issue) for issue in issues]
    annotations_zone = "\n\n".join(annotation_parts)

    body_parts: list[str] = []
    if metadata_zone:
        body_parts.append(metadata_zone)
    if content:
        body_parts.append(content)
    if annotations_zone:
        body_parts.append(annotations_zone)
    body = "\n\n".join(body_parts)

    out = (
        f"---\n{fm_text}---\n\n{body}\n"
        if body
        else f"---\n{fm_text}---\n"
    )
    path.write_text(out, encoding="utf-8")


# ---------- block emit ---------- #


def _emit_artifact_block(artifact: dict[str, Any]) -> str:
    """Emit `<!--artifact <mime-type>\n<yaml>\n-->`.

    `artifact` carries `{mime: <type>, fields: {...}}`.
    """
    mime = artifact.get("mime", "")
    fields = artifact.get("fields") or {}
    body_yaml = _dump_yaml_block(fields).rstrip("\n") if fields else ""
    if body_yaml:
        return f"<!--artifact {mime}\n{body_yaml}\n-->"
    return f"<!--artifact {mime}\n-->"


def _emit_origin_block(origin: dict[str, Any]) -> str:
    """Emit `<!--origin [<id>[/<subtype>]]\n<yaml>\n-->`.

    `origin` carries `{id: <id-or-None>, subtype: <sub-or-None>, fields: {...}}`.
    """
    id_ = origin.get("id")
    subtype = origin.get("subtype")
    fields = origin.get("fields") or {}
    if id_ and subtype:
        opener = f"<!--origin {id_}/{subtype}"
    elif id_:
        opener = f"<!--origin {id_}"
    else:
        opener = "<!--origin"
    body_yaml = _dump_yaml_block(fields).rstrip("\n") if fields else ""
    if body_yaml:
        return f"{opener}\n{body_yaml}\n-->"
    return f"{opener}\n-->"


def _emit_classify_block(classify: dict[str, Any]) -> str:
    """Emit `<!--classify <namespace>[/<id>[/<subtype>]]\n<yaml>\n-->`.

    `classify` carries `{namespace, id, subtype, fields}`. When the id equals the
    namespace, the bare namespace is emitted (`<!--classify youtube-->`) rather than
    the redundant `<!--classify youtube/youtube-->`. The parser accepts both shapes
    and normalizes either to `(namespace, namespace, None)`.
    """
    namespace = classify.get("namespace", "")
    id_ = classify.get("id", "")
    subtype = classify.get("subtype")
    fields = classify.get("fields") or {}
    qualified = namespace if not id_ or id_ == namespace else f"{namespace}/{id_}"
    if subtype:
        qualified = f"{qualified}/{subtype}"
    body_yaml = _dump_yaml_block(fields).rstrip("\n") if fields else ""
    if body_yaml:
        return f"<!--classify {qualified}\n{body_yaml}\n-->"
    return f"<!--classify {qualified}\n-->"


def _emit_embed_block(embed: dict[str, Any]) -> str:
    """Emit `<!--embed <mime-type>\n<yaml>\n-->` (reconciliation #1: metadata zone).

    `embed` carries `{media_type: <mime>, address, transport, fields: {...}}`.
    `address` and `transport` are required; `fields` carries optional per-MIME
    extended fields (alt, description, width/height, etc.).
    """
    media_type = embed.get("media_type", "")
    address = embed.get("address")
    transport = embed.get("transport", "")
    fields = embed.get("fields") or {}
    payload: dict[str, Any] = {"address": address, "transport": transport}
    payload.update(fields)
    body_yaml = _dump_yaml_block(payload).rstrip("\n")
    return f"<!--embed {media_type}\n{body_yaml}\n-->"


def _emit_issue_block(issue: dict[str, Any]) -> str:
    """Emit `<!--issue <id>[/<subtype>]\n<yaml>\n-->`.

    `issue` carries `{id, subtype, fields}`. Per spec §4.3.3.1 the universal required
    fields are `severity`, `resolution`, `detector` (and optional `address` for
    segment-scoped issues); they live on `fields`.
    """
    id_ = issue.get("id", "")
    subtype = issue.get("subtype")
    fields = issue.get("fields") or {}
    qualified = f"{id_}/{subtype}" if subtype else id_
    body_yaml = _dump_yaml_block(fields).rstrip("\n") if fields else ""
    if body_yaml:
        return f"<!--issue {qualified}\n{body_yaml}\n-->"
    return f"<!--issue {qualified}\n-->"


def _dump_yaml_block(block: dict[str, Any]) -> str:
    """Render `block` as YAML using the dump conventions (block-style sequences, no
    key sorting, full-width)."""
    if not block:
        return ""
    return yaml.dump(
        block,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    )


# ---------- block parse ---------- #


def _parse_block(
    lines: list[str], start: int
) -> tuple[str, dict[str, Any] | None, int]:
    """Parse a single HTML-comment block starting at `lines[start]`.

    Returns `(opener_line, body_dict, next_index)`. `opener_line` is the full opener
    (e.g. `<!--artifact application/pdf`); `body_dict` is the parsed YAML payload (or
    None for empty blocks); `next_index` is the line index after the closer.
    """
    opener = lines[start].rstrip()
    j = start + 1
    while j < len(lines) and lines[j].rstrip() != _BLOCK_CLOSER:
        j += 1
    if j >= len(lines):
        raise ValueError(f"unterminated block at line {start + 1}: {opener!r}")
    yaml_text = "\n".join(lines[start + 1 : j]).strip()
    body: dict[str, Any] | None
    if yaml_text:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ValueError(f"malformed YAML in block at line {start + 1}: {e}") from e
        if data is not None and not isinstance(data, dict):
            raise ValueError(f"block at line {start + 1} body is not a mapping")
        body = data or {}
    else:
        body = None
    return opener, body, j + 1


def _extract_metadata_blocks(
    body: str,
) -> tuple[dict[str, Any], str]:
    """Parse leading metadata-zone blocks from `body`.

    Returns:
        ({artifact: {mime, fields} | None,
          origins: [{id, subtype, fields}, ...],
          classifies: [{namespace, id, subtype, fields}, ...],
          embeds: [{media_type, address, transport, fields}, ...]},
         remaining_body)

    Recognizes the four spec-§4.3.1 openers: <!--artifact, <!--origin, <!--classify,
    <!--embed. Within the metadata zone, only blank lines may separate blocks.
    """
    result: dict[str, Any] = {
        "artifact": None,
        "origins": [],
        "classifies": [],
        "embeds": [],
    }
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip()
        if stripped == "":
            i += 1
            continue
        if not _is_metadata_opener(stripped):
            break
        opener, block_body, next_i = _parse_block(lines, i)
        fields = block_body or {}

        if opener.startswith(_ARTIFACT_OPENER):
            mime = opener.removeprefix(_ARTIFACT_OPENER).strip()
            result["artifact"] = {"mime": mime, "fields": fields}
        elif opener.startswith(_ORIGIN_OPENER):
            arg = opener.removeprefix(_ORIGIN_OPENER).strip()
            id_, subtype = _split_qualifier(arg)
            result["origins"].append({"id": id_, "subtype": subtype, "fields": fields})
        elif opener.startswith(_CLASSIFY_OPENER):
            arg = opener.removeprefix(_CLASSIFY_OPENER).strip()
            namespace, id_, subtype = _split_namespaced(arg)
            result["classifies"].append(
                {"namespace": namespace, "id": id_, "subtype": subtype, "fields": fields}
            )
        elif opener.startswith(_EMBED_OPENER):
            media_type = opener.removeprefix(_EMBED_OPENER).strip()
            embed = _structure_embed_fields(media_type, fields, line_no=i + 1)
            result["embeds"].append(embed)
        i = next_i

    while i < len(lines) and lines[i].strip() == "":
        i += 1
    return result, "\n".join(lines[i:])


def _structure_embed_fields(
    media_type: str, fields: dict[str, Any], *, line_no: int
) -> dict[str, Any]:
    """Pop address+transport off the embed YAML payload and return the structured
    dict `{media_type, address, transport, fields}`."""
    if "/" not in media_type:
        raise ValueError(
            f"embed at line {line_no}: media_type {media_type!r} is not a "
            f"`type/subtype` MIME (e.g. `image/png`)"
        )
    body_fields = dict(fields)
    address_raw = body_fields.pop("address", None)
    if address_raw is None:
        raise ValueError(f"embed at line {line_no} missing required address")
    if isinstance(address_raw, list):
        address: str | list[str] = [str(x).strip() for x in address_raw if str(x).strip()]
        if not address:
            raise ValueError(f"embed at line {line_no} has empty address list")
    elif isinstance(address_raw, str):
        address = address_raw.strip()
        if not address:
            raise ValueError(f"embed at line {line_no} missing required address")
    else:
        raise ValueError(
            f"embed at line {line_no} has invalid address type: {type(address_raw).__name__}"
        )
    # Prefer v1.0 `transport:` (str); accept v0.3 `byte_hash:` (dict) for back-compat read.
    transport_raw = body_fields.pop("transport", None)
    byte_hash_raw = body_fields.pop("byte_hash", None)
    if isinstance(transport_raw, str) and transport_raw.strip():
        transport = transport_raw.strip()
        if ":" not in transport:
            raise ValueError(
                f"embed at line {line_no} transport {transport!r} missing `<algo>:` prefix"
            )
    elif isinstance(byte_hash_raw, dict):
        algo = str(byte_hash_raw.get("algo") or "").strip()
        value = str(byte_hash_raw.get("value") or "").strip()
        if not algo or not value:
            raise ValueError(f"embed at line {line_no} byte_hash missing algo or value")
        transport = f"{algo}:{value}"
    else:
        raise ValueError(
            f"embed at line {line_no} missing transport (expected `transport: <algo>:<hex>`)"
        )
    return {
        "media_type": media_type,
        "address": address,
        "transport": transport,
        "fields": body_fields,
    }


def _split_annotations(body: str) -> tuple[str, str]:
    """Split body into (content_zone, annotations_zone).

    Walks blocks from the end. Trailing <!--issue--> blocks form the annotations zone;
    everything before is the content zone.
    """
    lines = body.splitlines()
    n = len(lines)
    i = n
    while i > 0:
        while i > 0 and lines[i - 1].strip() == "":
            i -= 1
        if i > 0 and lines[i - 1].rstrip() == _BLOCK_CLOSER:
            j = i - 2
            while j >= 0 and not lines[j].lstrip().startswith("<!--"):
                j -= 1
            if j >= 0 and lines[j].lstrip().startswith(_ISSUE_OPENER):
                i = j
                continue
        break
    content_body = "\n".join(lines[:i]).rstrip("\n")
    annotations_body = "\n".join(lines[i:]).strip("\n")
    return content_body, annotations_body


def _extract_issue_blocks(annotations_body: str) -> list[dict[str, Any]]:
    """Parse <!--issue--> blocks from the annotations zone."""
    if not annotations_body.strip():
        return []
    issues: list[dict[str, Any]] = []
    lines = annotations_body.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip()
        if stripped == "":
            i += 1
            continue
        if not stripped.startswith(_ISSUE_OPENER):
            i += 1
            continue
        opener, block_body, next_i = _parse_block(lines, i)
        fields = block_body or {}
        arg = opener.removeprefix(_ISSUE_OPENER).strip()
        id_, subtype = _split_qualifier(arg)
        issues.append({"id": id_, "subtype": subtype, "fields": fields})
        i = next_i
    return issues


def _is_metadata_opener(line: str) -> bool:
    """Check if a line opens a metadata-zone block."""
    return any(line.startswith(o) for o in _METADATA_OPENERS)


def _split_qualifier(arg: str) -> tuple[str | None, str | None]:
    """Parse `<id>[/<subtype>]` into `(id, subtype)`. Empty → (None, None)."""
    if not arg:
        return None, None
    if "/" in arg:
        id_, subtype = arg.split("/", 1)
        return id_.strip(), subtype.strip()
    return arg.strip(), None


def _split_namespaced(arg: str) -> tuple[str, str, str | None]:
    """Parse `<namespace>/<id>[/<subtype>]` into `(namespace, id, subtype)`.

    Single-segment input (no slash) becomes `(arg, arg, None)` — used for
    namespace-level class-ids whose namespace = the id (e.g. `youtube`, `document`).
    """
    if "/" not in arg:
        return arg, arg, None
    parts = arg.split("/", 2)
    if len(parts) == 2:
        return parts[0], parts[1], None
    return parts[0], parts[1], parts[2]


class _Dumper(yaml.SafeDumper):
    """SafeDumper with block-style sequences for readable lists."""

    def represent_sequence(self, tag, sequence, flow_style=None):  # type: ignore[override]
        return super().represent_sequence(tag, sequence, flow_style=False)


# ---------- accessors ---------- #


def artifact_block(post: frontmatter.Post) -> dict[str, Any] | None:
    """Return the record's `<!--artifact-->` block as `{mime, fields}`, or None."""
    return post.metadata.get("_artifact")


def media_type_for(post: frontmatter.Post) -> str:
    """Return the record's media-type (MIME). Reads from the artifact block."""
    artifact = artifact_block(post)
    if not artifact:
        return ""
    return str(artifact.get("mime") or "")


def title_for(post: frontmatter.Post) -> str:
    """Return the record's title. Reads from the artifact block's `title` field."""
    artifact = artifact_block(post)
    if not artifact:
        return ""
    fields = artifact.get("fields") or {}
    return str(fields.get("title") or "")


def iter_origin_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `<!--origin-->` block as `{id, subtype, fields}`."""
    yield from (post.metadata.get("_origins") or [])


def iter_classify_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `<!--classify-->` block as `{namespace, id, subtype, fields}`."""
    yield from (post.metadata.get("_classifies") or [])


def iter_embed_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `<!--embed-->` block as `{media_type, address, transport, fields}`.

    Embeds live in the metadata zone (reconciliation #1, spec §4.3.1.4) — they are
    parsed from there by `load()` and emitted in the metadata zone by `dump()`.
    """
    yield from (post.metadata.get("_embeds") or [])


def iter_issue_blocks(post: frontmatter.Post) -> Iterator[dict[str, Any]]:
    """Yield each `<!--issue-->` block as `{id, subtype, fields}`."""
    yield from (post.metadata.get("_issues") or [])


def primary_origin_uri(post: frontmatter.Post) -> str:
    """Return the first URI from the first origin block, or `""`."""
    for origin in iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        if isinstance(uri, list) and uri:
            return str(uri[0])
        if uri:
            return str(uri)
    return ""


def iter_origin_uris(post: frontmatter.Post) -> Iterator[str]:
    """Yield every URI across all origin blocks (string and list forms flattened).

    The corpus-wide complement to `primary_origin_uri`: used to build the
    URI → record-id index that capture/crawl/links consult for dedup.
    """
    for origin in iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        if isinstance(uri, list):
            yield from (str(u) for u in uri if u)
        elif uri:
            yield str(uri)


# ---------- corpus-wide URI index (spec §9.3 `uris` view, consumer side) ---------- #


def build_uri_index(corpus_root: Path) -> dict[str, str]:
    """Map every record's canonical origin URI → that record's id.

    One glob pass over `records/`. Unparseable records are skipped (tolerant
    parse, per the project's parse-tolerantly principle). When two records claim
    the same canonical URI the later one (sorted by path) wins — a corpus-health
    concern surfaced elsewhere, not here.

    This is the lightweight index `corpus links` / `corpus crawl` need; P5's
    `health` module builds a richer `RecordRef`-based variant for diagnostics.
    """
    from . import urls as _urls

    index: dict[str, str] = {}
    for md in sorted((corpus_root / "records").glob("*/*.md")):
        try:
            post = load(md)
        except Exception:
            continue
        record_id = str(post.metadata.get("id") or md.stem)
        for uri in iter_origin_uris(post):
            try:
                key = _urls.normalize(uri)
            except Exception:
                continue
            if key:
                index[key] = record_id
    return index


def find_by_uri(url: str, *, corpus_root: Path) -> str | None:
    """Return the id of the record whose origin URIs include `url`, else None.

    `url` is canonicalized (`urls.normalize`) before lookup so trailing-slash /
    query-order / case differences don't cause a miss. Rebuilds the index per
    call — fine for the handful of seed/frontier checks the crawler makes; a
    caller doing many lookups should `build_uri_index` once and index directly.
    """
    from . import urls as _urls

    try:
        target = _urls.normalize(url)
    except Exception:
        target = url
    return build_uri_index(corpus_root).get(target)


# ---------- mutators ---------- #


def set_artifact_block(
    post: frontmatter.Post, *, mime: str, fields: dict[str, Any] | None = None
) -> None:
    """Set the record's `<!--artifact-->` block."""
    post.metadata["_artifact"] = {"mime": mime, "fields": fields or {}}


def append_origin_block(
    post: frontmatter.Post,
    *,
    uri: str | list[str],
    snapshot: str,
    schema_id: str | None = None,
    subtype: str | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a new `<!--origin-->` block to the record.

    `uri` may be a string or list[string]. `snapshot` is ISO-8601. `schema_id` and
    `subtype` qualify the block opener (None → bare). `fields` carries any additional
    schema-declared extended fields beyond the universal uri:/snapshot:.
    """
    block_fields: dict[str, Any] = {"uri": uri, "snapshot": snapshot}
    if fields:
        block_fields.update(fields)
    origins = post.metadata.setdefault("_origins", [])
    origins.append({"id": schema_id, "subtype": subtype, "fields": block_fields})


def append_classify_block(
    post: frontmatter.Post,
    *,
    namespace: str,
    id: str,
    subtype: str | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a new `<!--classify-->` block to the record."""
    classifies = post.metadata.setdefault("_classifies", [])
    classifies.append(
        {"namespace": namespace, "id": id, "subtype": subtype, "fields": fields or {}}
    )


def append_embed_block(
    post: frontmatter.Post,
    *,
    media_type: str,
    address: str | list[str],
    transport: str,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a new `<!--embed-->` block to the record.

    Per spec §4.3.1.4 the required fields are `address` and `transport`. Extended
    fields (`alt`, `description`, `width`/`height`, etc.) ride on `fields`.
    """
    embeds = post.metadata.setdefault("_embeds", [])
    embeds.append(
        {
            "media_type": media_type,
            "address": address,
            "transport": transport,
            "fields": fields or {},
        }
    )


def append_issue_block(
    post: frontmatter.Post,
    *,
    id: str,
    subtype: str | None = None,
    severity: str,
    resolution: str = "open",
    detector: str,
    address: str | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    """Append a new `<!--issue-->` block to the record (spec §4.3.3.1 shape).

    Universal fields (severity, resolution, detector, optional address) plus any
    id-specific `fields`. If `address` is provided, the issue is segment-scoped;
    otherwise record-scoped.
    """
    block_fields: dict[str, Any] = {
        "severity": severity,
        "resolution": resolution,
        "detector": detector,
    }
    if address:
        block_fields["address"] = address
    if fields:
        block_fields.update(fields)
    issues = post.metadata.setdefault("_issues", [])
    issues.append({"id": id, "subtype": subtype, "fields": block_fields})


# ---------- derived classifications view (spec §9.1) ---------- #


def derived_classifications(post: frontmatter.Post) -> list[str]:
    """Compute the derived `classifications[]` view by walking metadata blocks.

    Per spec §9.1: artifact contributes `mime/<mime-type>`; each qualified origin
    block contributes `origin/<id>[/<subtype>]`; each classify block contributes
    `<namespace>/<id>[/<subtype>]`. Dedupe preserving body order. Embeds and issues
    do not contribute (embeds are assets, issues are problems; separate views).
    """
    result: list[str] = []
    seen: set[str] = set()

    artifact = artifact_block(post)
    if artifact and artifact.get("mime"):
        entry = f"mime/{artifact['mime']}"
        if entry not in seen:
            result.append(entry)
            seen.add(entry)

    for origin in iter_origin_blocks(post):
        id_ = origin.get("id")
        if not id_:
            continue
        subtype = origin.get("subtype")
        entry = f"origin/{id_}/{subtype}" if subtype else f"origin/{id_}"
        if entry not in seen:
            result.append(entry)
            seen.add(entry)

    for classify in iter_classify_blocks(post):
        namespace = classify.get("namespace") or ""
        id_ = classify.get("id") or ""
        subtype = classify.get("subtype")
        if not namespace or not id_:
            continue
        if namespace == id_:
            entry = f"{id_}/{subtype}" if subtype else id_
        else:
            base = f"{namespace}/{id_}"
            entry = f"{base}/{subtype}" if subtype else base
        if entry not in seen:
            result.append(entry)
            seen.add(entry)

    return result


# ---------- stub creation ---------- #


def stub_frontmatter(
    *,
    record_id: str,
    transport: str | list[str] | None = None,
    touch_id: str,
    description: str = "",
) -> dict[str, Any]:
    """Build a fresh stub-record frontmatter dict.

    `record_id` is the bare blake3 hex (becomes `id`). `transport` is alternative
    byte hashes (`<algo>:<hex>` or list); the primary blake3 lives on `id` and is NOT
    duplicated here. `touch_id` bootstraps the touch chain. `description` defaults to
    empty (filled at normalize).

    The caller is responsible for emitting the artifact + first origin blocks via
    `set_artifact_block()` and `append_origin_block()`.
    """
    fm: dict[str, Any] = {
        "id": record_id,
        "description": description,
        "status": "stub",
    }
    if transport:
        fm["transport"] = transport
    fm["touch"] = touch_id
    return fm
