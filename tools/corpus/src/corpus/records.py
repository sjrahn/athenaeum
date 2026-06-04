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
- Hash helpers: `format_hash(algo, hex_value)`.
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
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from . import paths

# Spec §4.2 core-fields order.
_CORE_FIELD_ORDER = [
    "id",
    "title",
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


# ---------- hash helpers ---------- #


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
    """Write `post` to `path` in canonical zone order (see `dumps`)."""
    paths.ensure_parent(path)
    path.write_text(dumps(post), encoding="utf-8")


def dumps(post: frontmatter.Post) -> str:
    """Serialize `post` to the canonical record text — the exact bytes `dump` writes.

    Order:
        frontmatter (core fields only, in spec order)
        metadata zone:     <!--artifact-->, <!--origin-->*, <!--classify-->*, <!--embed-->*
        content zone:      post.content verbatim (section/segment)
        annotations zone:  <!--issue-->*

    Returned (not written) so callers like `corpus redraft` can compare a re-derived
    record against disk and write only when it changed.
    """
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

    return (
        f"---\n{fm_text}---\n\n{body}\n"
        if body
        else f"---\n{fm_text}---\n"
    )


# ---------- block emit ---------- #


def _emit_block(opener: str, fields: dict[str, Any]) -> str:
    """Render a header-only block (artifact / origin / classify / issue): the opener line,
    the optional YAML body, and the closing `-->`. The single home for the block-tail
    serialization convention. (Embed differs — it always carries a payload — and emits its
    own form.)"""
    body_yaml = _dump_yaml_block(fields).rstrip("\n") if fields else ""
    if body_yaml:
        return f"{opener}\n{body_yaml}\n-->"
    return f"{opener}\n-->"


def _emit_artifact_block(artifact: dict[str, Any]) -> str:
    """Emit `<!--artifact <mime-type>\n<yaml>\n-->`.

    `artifact` carries `{mime: <type>, fields: {...}}`.
    """
    mime = artifact.get("mime", "")
    fields = artifact.get("fields") or {}
    return _emit_block(f"<!--artifact {mime}", fields)


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
    return _emit_block(opener, fields)


def _emit_classify_block(classify: dict[str, Any]) -> str:
    """Emit `<!--classify <namespace>[/<id>[/<subtype>]]\n<yaml>\n-->`.

    `classify` carries `{namespace, id, subtype, fields}`. When the id equals the
    namespace AND there is no subtype, the bare namespace is emitted
    (`<!--classify youtube-->`) rather than the redundant `<!--classify youtube/youtube-->`;
    the parser normalizes that to `(namespace, namespace, None)`. When a subtype IS present
    the redundant id is kept (`<!--classify ns/ns/subtype-->`) so the three-part identity
    survives the round-trip through `_split_namespaced` (collapsing to `ns/subtype` would
    re-parse the subtype as the id).
    """
    namespace = classify.get("namespace", "")
    id_ = classify.get("id", "")
    subtype = classify.get("subtype")
    fields = classify.get("fields") or {}
    qualified = (
        namespace if (not id_ or (id_ == namespace and not subtype)) else f"{namespace}/{id_}"
    )
    if subtype:
        qualified = f"{qualified}/{subtype}"
    return _emit_block(f"<!--classify {qualified}", fields)


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
    return _emit_block(f"<!--issue {qualified}", fields)


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
    """Return the record's display title.

    The normalizer-authored frontmatter `title` is canonical. Before normalization it is
    empty, so fall back to a **block-level title candidate**: the artifact block's bare
    `title` field (the opener's MIME already names the format, so the candidate isn't
    namespaced — spec §4.3.1.1), then an origin block's `ytdlp_title` (whose `ytdlp_`
    prefix survives because the origin opener names the source record, not the extraction
    tool). The normalizer ultimately chooses among these candidates (or writes its own) to
    fill the frontmatter `title` (spec §4.2.1)."""
    if title := str(post.metadata.get("title") or "").strip():
        return title
    artifact = artifact_block(post)
    if artifact and (t := (artifact.get("fields") or {}).get("title")):
        return str(t)
    for origin in iter_origin_blocks(post):
        if t := (origin.get("fields") or {}).get("ytdlp_title"):
            return str(t)
    return ""


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


def iter_record_paths(corpus_root: Path) -> Iterator[Path]:
    """Yield every record markdown path under `records/<shard>/*.md`, sorted. The single
    source of the on-disk record layout — every command + health iterates through here, so
    the shard convention lives in one place."""
    yield from sorted((corpus_root / "records").glob("*/*.md"))


def load_all(corpus_root: Path) -> Iterator[tuple[Path, frontmatter.Post]]:
    """Yield `(path, post)` for every parseable record; unparseable records are silently
    skipped (parse-tolerant, per the project principle), never crashing the whole sweep.
    A caller that needs to report load failures should iterate `iter_record_paths` and
    `load` each itself."""
    for md in iter_record_paths(corpus_root):
        try:
            yield md, load(md)
        except Exception:  # tolerant parse — skip unloadable records
            continue


def build_uri_index(corpus_root: Path) -> dict[str, str]:
    """Map every record's origin URI → that record's id, keyed by **identity key**.

    One pass over `records/` via `load_all`. Each URI's key is `urls.identity_key` — the
    conservative `normalize` plus the URI host's opt-in `url_equivalent` rules (spec §7.2),
    so equivalent spellings (e.g. `…/page-1` ≡ `…/` , `?nested_view=1` noise) collapse to one
    key and an inbound variant matches the record. The host's `capture` recipe is resolved
    once per host (memoized) — the overlay lookup is not repeated per URI. Absent any
    `url_equivalent`, the key is exactly `normalize(uri)` (today's behavior). When two records
    claim the same key the later one (sorted by path) wins — a corpus-health concern surfaced
    elsewhere. The lightweight index `corpus links` / `corpus crawl` need.
    """
    from . import urls as _urls
    from .capture import recipes as _recipes

    recipe_by_host: dict[str, dict] = {}

    def _key(uri: str) -> str:
        host = _urls.host_of(uri)
        if host not in recipe_by_host:
            recipe_by_host[host] = _recipes.capture_recipe_for_url(corpus_root, uri) or {}
        recipe = recipe_by_host[host]
        return _urls.identity_key(
            uri, recipe.get("url_equivalent"), url_rewrite=recipe.get("url_rewrite")
        )

    index: dict[str, str] = {}
    for md, post in load_all(corpus_root):
        record_id = str(post.metadata.get("id") or md.stem)
        for uri in iter_origin_uris(post):
            try:
                key = _key(uri)
            except Exception:
                continue
            if key:
                index[key] = record_id
    return index


def find_by_uri(
    url: str, *, corpus_root: Path, index: dict[str, str] | None = None
) -> str | None:
    """Return the id of the record whose origin URIs include `url`, else None.

    `url` is reduced to its **identity key** (`urls.identity_key` via the host's
    `url_equivalent` rules — spec §7.2) before lookup, so trailing-slash / query-order / case
    differences and host-declared equivalences (`/page-1` ≡ bare, query noise) don't cause a
    miss. The key matches `build_uri_index`'s keying. Pass a prebuilt `index`
    (`build_uri_index`) when making many lookups — e.g. a crawl frontier — to avoid rebuilding
    it per call.
    """
    from .capture import recipes as _recipes

    try:
        target = _recipes.identity_key_for_url(corpus_root, url)
    except Exception:
        target = url
    if index is None:
        index = build_uri_index(corpus_root)
    return index.get(target)


# ---------- content-identity dedup (cross-URL) ---------- #


def content_key(post: frontmatter.Post) -> tuple[str, tuple[str, ...]] | None:
    """Content-identity key for cross-URL dedup: the `canonical:` content hash PLUS
    the sorted set of embed transport hashes. Returns None when the record has no
    `canonical:` yet (an undrafted stub can't be content-deduped).

    The embed set guards against a false merge: `blake3-canonical-html` hashes the
    page's *visible text* only (it ignores `<img>` bytes), so two genuinely different
    image pages with identical sparse captions would share a canonical hash but not the
    same images. Requiring the embed set to match too keeps distinct diagrams distinct
    while still collapsing true duplicates (the same article reached by two URLs).

    NB: meaningful only when capture strips page chrome — otherwise per-page chrome
    text (breadcrumbs, personalized headers) perturbs the canonical hash so two
    same-content pages never match. See the `remove:` capture interaction.
    """
    canonical = str(post.metadata.get("canonical") or "").strip()
    if not canonical:
        return None
    transports = tuple(
        sorted(str(e.get("transport") or "") for e in (post.metadata.get("_embeds") or []))
    )
    return (canonical, transports)


def find_content_duplicate(
    post: frontmatter.Post, *, record_id: str, corpus_root: Path
) -> tuple[str, Path] | None:
    """Return `(id, path)` of an existing OTHER record whose `content_key` equals
    `post`'s, else None. Lets the draft step fold a same-content / different-URL capture
    into the record that already holds that content (the original keeps its id; the
    duplicate's URL is appended to the original's origin uri list). O(N) over the corpus
    — fine at draft cadence; build an index if it ever needs to scale."""
    key = content_key(post)
    if key is None:
        return None
    for md, other in load_all(corpus_root):
        if str(other.metadata.get("id") or md.stem) == record_id:
            continue
        if content_key(other) == key:
            return str(other.metadata.get("id") or md.stem), md
    return None


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


def _alias_already_present(alias: str, existing: list[str], corpus_root: Path | None) -> bool:
    """True when `alias` is already among `existing` origin URIs. Exact-string when
    `corpus_root` is None; by identity key (host `url_equivalent`) otherwise — degrading to
    exact-string if identity resolution raises."""
    if corpus_root is None:
        return alias in existing
    from .capture import recipes as _recipes

    try:
        alias_key = _recipes.identity_key_for_url(corpus_root, alias)
        return any(_recipes.identity_key_for_url(corpus_root, u) == alias_key for u in existing)
    except Exception:
        return alias in existing


def add_origin_uri_alias(
    post: frontmatter.Post, alias: str, *, corpus_root: Path | None = None
) -> bool:
    """Fold `alias` into the most-recent origin block's `uri:` list, unless it already
    appears on some origin block. Returns True when added.

    Drafters that discover a canonical (`<link rel=canonical>`) or post-redirect URL of
    the captured page use this to collapse those forms into the origin's uri list (spec
    §7.2 — canonical / shortlink / final URLs are one logical origin), rather than
    stranding them on the artifact block. The most-recent origin block is the one the
    current capture seeded, so its uri list is where the current page's aliases belong.

    With `corpus_root`, the already-present check is by **identity key** (`urls.identity_key`
    via the host's `url_equivalent` rules — spec §7.2): an `alias` that denotes the same
    resource as an existing uri (a query-noise / `/page-1` variant) is **not** appended,
    keeping the origin block minimal. Without `corpus_root`, the check is exact-string
    (back-compat).
    """
    alias = (alias or "").strip()
    if not alias:
        return False
    origins = post.metadata.get("_origins") or []
    if not origins:
        return False
    existing: list[str] = []
    for origin in origins:
        uri = (origin.get("fields") or {}).get("uri")
        existing.extend(str(u).strip() for u in (uri if isinstance(uri, list) else [uri]) if u)
    if _alias_already_present(alias, existing, corpus_root):
        return False
    target = origins[-1].setdefault("fields", {})
    uri = target.get("uri")
    if isinstance(uri, list):
        uri.append(alias)
    elif uri:
        target["uri"] = [str(uri).strip(), alias]
    else:
        target["uri"] = alias
    return True


def merge_origin_fields(post: frontmatter.Post, fields: dict[str, Any]) -> None:
    """Merge extra fields into the most-recent origin block (the one the current capture
    seeded), beside `uri:`/`snapshot:`.

    Drafters attach source-provided enrichment here — e.g. a yt-dlp capture's `ytdlp_*`
    fields (title/description/uploader/counts/`ytdlp_comments`). This is where-it-came-from
    metadata, NOT facts about the artifact bytes, so it belongs on the origin block, never
    the artifact block or the body (spec §7.2)."""
    if not fields:
        return
    origins = post.metadata.get("_origins") or []
    if not origins:
        return
    target = origins[-1].setdefault("fields", {})
    for key, value in fields.items():
        target[key] = value


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
    duplicated here. `touch_id` bootstraps the touch chain. `title` and `description`
    default to empty (both filled at normalize — `title` from the namespaced block-level
    candidates: an artifact `*_title`, an origin `ytdlp_title`).

    The caller is responsible for emitting the artifact + first origin blocks via
    `set_artifact_block()` and `append_origin_block()`.
    """
    fm: dict[str, Any] = {
        "id": record_id,
        "title": "",
        "description": description,
        "status": "stub",
    }
    if transport:
        fm["transport"] = transport
    fm["touch"] = touch_id
    return fm
