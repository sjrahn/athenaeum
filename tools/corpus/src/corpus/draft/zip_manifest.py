"""General `self_contained` zip → manifest draft extraction (deterministic, no LLM).

The drafting analogue of overlay-driven capture: instead of a bespoke drafter per
archive format, ONE general drafter renders a zip's file tree as a pseudo-ToC, and the
*mime schema* tunes the representation through a `draft.manifest` config block. A schema
opts in with `draft.strategy: zip-manifest` (see `corpus.draft.register_strategy`); the
drafter is selected by that strategy, not by the schema id, so it serves any number of
self_contained zip types (an Unraid diagnostics export, a config backup, a log bundle …)
whose only difference is config.

This is for archives whose *unit of meaning is the whole bundle* — kept as one record
rather than decomposed into one record per member (`artifact_kind: decomposable`).
Genuinely structured zip formats (xlsx/docx/epub) are "more than a zip with stuff in it"
and keep their own specialized id-keyed drafters; they never reach this code.

How a member is represented (the image model — spec §4.3.1.4 / §4.3.2.2):

- A small text member matching an `inline` glob → a `text` segment carrying its decoded
  body (faithful + searchable). No embed: the body IS the content.
- Any other member → an `<!--embed-->` (transport = blake3 of the member bytes,
  `media_type` = its detected type, address `path=<relpath>`) the normalizer later
  describes. A renderable atom (text-too-large, image/audio/video) additionally gets a
  **body-empty positioning marker** segment so it sits in the manifest tree — the
  lossy-positioned-by-description disposition. A member with no renderable atom (an
  opaque binary) is an embed only (no content-zone segment), like an EPUB orphan image.

Every member's bytes resolve via `corpus://<id>?path=<relpath>` (the `transforms/zip.py`
`path=` transform, paired with `working_kind: zip`) whether or not it carries an embed —
`corpus.ziparchive` re-derives the wrapper root so the recorded address round-trips.

`draft.manifest` config (all optional):

    root_strip       bool   — when every member sits under one wrapper dir
                              (`<host>-diagnostics-<ts>/`), strip it from rendered paths.
    sectioning       str    — `top_level_folders` (each top-level dir → a Section, its
                              members → Segments; root-level members → a synthetic
                              "(root)" Section) or `flat` (one flat list of top-level
                              Segments). Default `flat`.
    inline           [glob] — text members whose decoded text becomes the Segment body
                              (fnmatch on the rendered relpath). Default: none inlined.
    max_inline_bytes int    — size ceiling for inlining (default 65536); larger matches
                              become embeds + body-empty markers.

Members are addressed `path=<relpath>`; sections by their folder, `path=<folder>/`. The
body is a manifest/pseudo-ToC — faithful by listing structure and inlining the text the
schema marks, not by mirroring the archive bytes (cf. the EPUB drafter, equally lossy vs
its container). The normalizer MAY later enrich it (embed descriptions, classifications).
"""

from __future__ import annotations

import mimetypes
import zipfile
from collections import OrderedDict
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from corpus import hashing, recordbuild, records, touches, ziparchive
from corpus.draft import DrafterResult, register_strategy
from corpus.segments import Section, Segment

_DETECTOR = touches.script_identifier("draft.zip-manifest")
_DEFAULT_MAX_INLINE = 65536

# Application media types whose bytes are text the corpus can inline / position as the
# `text` atom (the four atoms are text/image/audio/video — spec §1.3).
_TEXT_APPLICATION_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
        "application/x-toml",
        "application/x-sh",
        "application/javascript",
        "application/x-ndjson",
        "application/csv",
    }
)


@register_strategy("zip-manifest")
def draft(
    zip_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
    mime_schema: dict[str, Any] | None = None,
) -> DrafterResult:
    cfg = dict(((mime_schema or {}).get("draft") or {}).get("manifest") or {})
    inline_globs = list(cfg.get("inline") or [])
    max_inline = int(cfg.get("max_inline_bytes", _DEFAULT_MAX_INLINE))
    sectioning = str(cfg.get("sectioning") or "flat").strip().lower()

    seg_items: list[tuple[str, Segment]] = []  # (relpath, content-zone segment)
    embeds: list[dict[str, Any]] = []
    member_count = 0
    total = 0
    root: str | None = None

    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            member_count = len(infos)
            if cfg.get("root_strip"):
                root = ziparchive.common_root([i.filename for i in infos])

            for info in sorted(infos, key=lambda i: ziparchive.relpath(i.filename, root)):
                rel = ziparchive.relpath(info.filename, root)
                size = info.file_size
                total += size
                member_mime = mimetypes.guess_type(rel)[0] or "application/octet-stream"
                atom = _atom_for(member_mime)
                inlined = (
                    atom == "text"
                    and size <= max_inline
                    and any(fnmatch(rel, g) for g in inline_globs)
                )
                data = zf.read(info.filename)
                if inlined:
                    body = data.decode("utf-8", errors="replace").strip()
                    seg_items.append((rel, Segment(atom="text", address=f"path={rel}", body=body)))
                    continue
                # Non-inlined → an embed (whole-member fact + description home) and, when
                # the member has a renderable atom, a body-empty positioning marker.
                digest = hashing.hash_bytes(data, also=())["blake3"]
                embeds.append(
                    {
                        "media_type": member_mime,
                        "address": f"path={rel}",
                        "transport": records.format_hash("blake3", digest),
                        "fields": {"bytes": size},
                    }
                )
                if atom is not None:
                    seg_items.append((rel, Segment(atom=atom, address=f"path={rel}", body="")))
    except zipfile.BadZipFile:
        return {"issues": [_issue("unreadable archive (corrupt or not a zip).")]}

    if sectioning == "top_level_folders":
        blocks: list[Section | Segment] = _folder_sections(seg_items)
    else:
        blocks = []
        for rel, seg in seg_items:
            seg.entry = rel  # top-level segments carry the relpath as their TOC label
            blocks.append(seg)

    recordbuild.add_blocks(build, blocks)

    fields: dict[str, Any] = {"member_count": member_count, "uncompressed_bytes": total}
    if root:
        fields["title"] = root.rstrip("/")

    issues: list[dict[str, Any]] = []
    if member_count == 0:
        issues.append(_issue("archive contains no files."))

    result: DrafterResult = {"fields": fields, "embeds": embeds, "issues": issues}
    if canonical_algo:
        from corpus import content_hash

        result["canonical"] = records.format_hash(
            canonical_algo.split("-", 1)[0], content_hash.compute(canonical_algo, zip_path)
        )
    return result


def _atom_for(media_type: str | None) -> str | None:
    """Map a member's media type to one of the four content atoms, or None for an opaque
    binary that has no renderable atom (it becomes an embed with no positioning segment)."""
    if not media_type:
        return None
    mt = media_type.split(";", 1)[0].strip().lower()
    if mt.startswith("image/"):
        return "image"
    if mt.startswith("audio/"):
        return "audio"
    if mt.startswith("video/"):
        return "video"
    if mt.startswith("text/") or mt in _TEXT_APPLICATION_TYPES:
        return "text"
    if mt.endswith("+json") or mt.endswith("+xml"):
        return "text"
    return None


def _folder_sections(seg_items: list[tuple[str, Segment]]) -> list[Section | Segment]:
    """Group the content-zone segments by their top-level folder (after root-strip) into
    Sections. Root-level members (no `/`) collect into a synthetic `(root)` section so the
    content zone stays homogeneous (all Sections), per the grammar's no-mixed-top-level
    rule. Folders with no renderable segment (e.g. all-binary) simply don't appear."""
    groups: OrderedDict[str | None, list[Segment]] = OrderedDict()
    for rel, seg in seg_items:
        top = rel.split("/", 1)[0] if "/" in rel else None
        groups.setdefault(top, []).append(seg)

    # Root files first, then folders alphabetically.
    keys = sorted(groups, key=lambda k: (k is not None, k or ""))
    sections: list[Section | Segment] = []
    for key in keys:
        segs = groups[key]
        if key is None:
            sections.append(Section(address="path=/", entry="(root)", segments=segs))
        else:
            sections.append(Section(address=f"path={key}/", entry=key, segments=segs))
    return sections


def _issue(description: str) -> dict[str, Any]:
    return {
        "id": "partial-content",
        "subtype": "empty-body",
        "severity": "blocking",
        "resolution": "open",
        "detector": _DETECTOR,
        "fields": {"description": description},
    }
