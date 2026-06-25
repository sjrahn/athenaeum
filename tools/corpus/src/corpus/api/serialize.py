"""Serialize the library's `Post` view into the Corpus Console JSON shape.

Pure: stdlib + the `corpus` library. No FastAPI, no HTTP. Mirrors the design's record
object (transport / embeds / origins / classifyBlocks / artifactFields / content /
annotations / touch) so the Angular front end stays close to the prototype, while every
value is sourced from the existing tooling (no re-derivation here).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from corpus import derived_views, records, segments, tokens
from corpus import mime as mime_mod
from corpus.store import ArtifactStore

# Console type vocabulary for typed extended-field refinement filters.
_URI_RE = re.compile(r"^(https?|corpus|file|s3|urn)://", re.I)
_DATE_RE = re.compile(r"^\d{8}$|^\d{4}-\d{2}-\d{2}")
_HASH_RE = re.compile(r"^(sha256|sha512|blake3|phash|dhash|ahash|whash|simhash|chromaprint):")


def host_of(uri: str) -> str:
    """Bare host of a URI (``www.`` stripped). Schemeless-host URIs (``file://``,
    ``urn:``) name themselves by scheme; otherwise the leading path token."""
    try:
        parsed = urlparse(uri)
        if parsed.netloc:
            return parsed.netloc.split("@")[-1].split(":")[0].removeprefix("www.")
        if parsed.scheme:
            return parsed.scheme
    except ValueError:
        pass
    return (uri or "").split("/")[0] or "—"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def infer_type(value: Any) -> str:
    """Value-only type inference (the prototype's ``cxInferType``)."""
    if isinstance(value, list):
        return "list"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    s = str(value)
    if _URI_RE.match(s):
        return "uri"
    if _DATE_RE.match(s):
        return "date"
    if _HASH_RE.match(s):
        return "hash"
    return "string"


def normalize_type(declared: str | None, field_name: str, sample: Any) -> str:
    """Map a schema ``extended_fields.<f>.type`` to the Console vocabulary, refining
    with the field name and a sample value when the declaration is loose/absent."""
    d = (declared or "").lower()
    if d.startswith(("int", "number", "float", "decimal")):
        return "number"
    if d.startswith(("bool",)):
        return "bool"
    if "list" in d or d == "array":
        return "list"
    if "uri" in d or "url" in d or field_name.endswith(("_url", "_uri", "url", "uri")):
        return "uri"
    if "date" in d or "timestamp" in d:
        return "date"
    if "hash" in d:
        return "hash"
    # declared "string"/"string-or-list"/unknown -> refine from the actual value
    return infer_type(sample)


# ---------- content zone (sections + segments) ---------- #


def _segment_node(seg: segments.Segment) -> dict[str, Any]:
    node: dict[str, Any] = {
        "type": "segment",
        "atom": seg.atom,
        "overlay": seg.overlay,
        "address": seg.address,
        "entry": seg.entry,
        "description": seg.description,
        "body": seg.body or "",
        "perceptual": seg.perceptual,
    }
    # Surface header extras (e.g. `speaker`) without clobbering the known keys.
    for k, v in (seg.extra or {}).items():
        node.setdefault(k, v)
    return node


def _section_node(sec: segments.Section) -> dict[str, Any]:
    node: dict[str, Any] = {
        "type": "section",
        "address": sec.address,
        "entry": sec.entry,
        "ns": sec.classification,
        "description": sec.description,
        "children": [_segment_node(s) for s in sec.segments],
    }
    for k, v in (sec.extra or {}).items():
        node.setdefault(k, v)
    return node


def content_nodes(post: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in segments.iter_blocks(post.content or ""):
        if isinstance(block, segments.Section):
            out.append(_section_node(block))
        else:
            out.append(_segment_node(block))
    return out


# ---------- metadata-zone blocks ---------- #


def _origin_node(origin: dict[str, Any]) -> dict[str, Any]:
    fields = dict(origin.get("fields") or {})
    uri = _as_list(fields.pop("uri", None))
    snapshot = fields.pop("snapshot", None)
    return {
        "id": origin.get("id") or "",
        "subtype": origin.get("subtype"),
        "uri": uri,
        "snapshot": snapshot,
        "fields": fields,
    }


def _classify_node(block: dict[str, Any]) -> dict[str, Any]:
    fields = dict(block.get("fields") or {})
    provenance = fields.pop("provenance", None)
    return {
        "ns": block.get("namespace") or "",
        "id": block.get("id") or "",
        "subtype": block.get("subtype"),
        "provenance": provenance,
        "fields": fields,
    }


def _embed_node(block: dict[str, Any]) -> dict[str, Any]:
    fields = dict(block.get("fields") or {})
    return {
        "mime": block.get("media_type") or "",
        "address": block.get("address"),
        "transport": block.get("transport"),
        "width": fields.get("width"),
        "height": fields.get("height"),
        "alt": fields.get("alt"),
        "description": fields.get("description"),
        "fields": fields,
    }


def primary_host(post: Any) -> str:
    uri = records.primary_origin_uri(post)
    return host_of(uri) if uri else ""


def _touch_list(post: Any) -> list[str]:
    touch = post.metadata.get("touch")
    if touch is None:
        return []
    return [str(t) for t in touch] if isinstance(touch, list) else [str(touch)]


# ---------- summary + detail ---------- #


def record_summary(post: Any, corpus_id: str) -> dict[str, Any]:
    """Light list item: enough for rows/cards/table/gallery without a detail fetch."""
    return {
        "id": post.metadata.get("id"),
        "title": records.title_for(post),
        "description": str(post.metadata.get("description") or ""),
        "status": post.metadata.get("status"),
        "visibility": post.metadata.get("visibility"),
        "mime": records.media_type_for(post),
        "corpus": corpus_id,
        "origin_host": primary_host(post),
        "embed_count": len(post.metadata.get("_embeds") or []),
        "classifications": derived_views.classifications(post),
        "captured": _captured(post),
        "normalized": None,
    }


def _captured(post: Any) -> str | None:
    for origin in records.iter_origin_blocks(post):
        snap = (origin.get("fields") or {}).get("snapshot")
        if snap:
            return str(snap)
    return None


def transport_name(record_id: str, mime: str) -> str:
    """The canonical short artifact filename (``<id[:12]>.<ext>``). Single source of
    truth for both the detail's ``transport.name`` and the ledger row's untitled
    placeholder, so the two can't drift."""
    ext = mime_mod.extension_for(mime) if mime else "bin"
    return f"{record_id[:12]}.{ext}" if record_id else f"artifact.{ext}"


def artifact_size(
    corpus_root: Path, record_id: str, mime: str, store: ArtifactStore | None
) -> int | None:
    if not store or not record_id or not mime:
        return None
    ext = mime_mod.extension_for(mime)
    try:
        if store.is_local(record_id, ext):
            return store.local_path(record_id, ext).stat().st_size
    except (OSError, ValueError):
        pass
    return None


def _concepts_detail(post: Any, resolver: Any | None) -> list[dict[str, Any]]:
    """The `concepts` derived view (§9.7), each entry enriched with a **live** gloss from the
    KB/registry when a resolver is configured. The summary is fetched, never stored on the record
    — concept blocks stay lean (§4.3.3.4).

    A `local:` concept resolves by its id; everything else resolves by the block's `label` (the
    article title), since the ZIM KB is keyed by title, not by a bare `wikidata:Q…` id.
    """
    out: list[dict[str, Any]] = []
    for entry in derived_views.concepts(post):
        item = dict(entry)
        if resolver is not None:
            cid = str(item.get("concept") or "").strip()
            ref = cid if cid.startswith("local:") else (str(item.get("label") or "").strip() or cid)
            if ref:
                try:
                    resolved = resolver.get(ref)
                except Exception:
                    resolved = None
                if resolved is not None:
                    if resolved.summary:
                        item["summary"] = resolved.summary
                    if resolved.label and not item.get("label"):
                        item["label"] = resolved.label
                    if resolved.url and not item.get("url"):
                        item["url"] = resolved.url
                    item["source"] = resolved.source
        out.append(item)
    return out


def record_detail(
    corpus_root: Path,
    post: Any,
    corpus_id: str,
    *,
    store: ArtifactStore | None = None,
    concept_resolver: Any | None = None,
) -> dict[str, Any]:
    """Full record JSON for the dual-pane viewer."""
    record_id = str(post.metadata.get("id") or "")
    mime = records.media_type_for(post)
    artifact = records.artifact_block(post) or {}
    artifact_fields = dict(artifact.get("fields") or {})
    size = artifact_size(corpus_root, record_id, mime, store)
    ext = mime_mod.extension_for(mime) if mime else "bin"
    name = transport_name(record_id, mime)

    hashes = {
        k: post.metadata.get(k)
        for k in ("transport", "canonical", "perceptual")
        if post.metadata.get(k)
    }

    return {
        "id": record_id,
        "title": records.title_for(post),
        "description": str(post.metadata.get("description") or ""),
        "status": post.metadata.get("status"),
        "visibility": post.metadata.get("visibility"),
        "mime": mime,
        "corpus": corpus_id,
        "transport": {
            "name": name,
            "mime": mime,
            "size": size,
            "ext": ext,
        },
        "hashes": hashes,
        "touch": _touch_list(post),
        "artifactFields": artifact_fields,
        "origins": [_origin_node(o) for o in records.iter_origin_blocks(post)],
        "classifyBlocks": [_classify_node(c) for c in records.iter_classify_blocks(post)],
        "embeds": [_embed_node(e) for e in records.iter_embed_blocks(post)],
        "content": content_nodes(post),
        "annotations": derived_views.context(post),
        "concepts": _concepts_detail(post, concept_resolver),
        "references": derived_views.references(post),
        "classifications": derived_views.classifications(post),
        "tokens": tokens.token_counts(post, corpus_root=corpus_root),
        "captured": _captured(post),
        "normalized": None,
        # render hints for the artifact pane (present when the drafter recorded them)
        "pages": artifact_fields.get("page_count") or artifact_fields.get("pages"),
        "duration": artifact_fields.get("duration"),
        "imgW": artifact_fields.get("width"),
        "imgH": artifact_fields.get("height"),
        "isImage": mime.startswith("image/"),
    }
