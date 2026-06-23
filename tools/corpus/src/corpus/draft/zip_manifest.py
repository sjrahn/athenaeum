"""General `self_contained` zip → manifest draft extraction (deterministic, no LLM).

The drafting analogue of overlay-driven capture: instead of a bespoke drafter per
archive format, ONE general drafter renders a zip's file tree as a description manifest,
and the *mime schema* tunes it through a `draft.manifest` config block. A schema opts in
with `draft.strategy: zip-manifest` (see `corpus.draft.register_strategy`); the drafter is
selected by that strategy, not the schema id, so it serves any number of self_contained
zip types (an Unraid diagnostics export, a config backup, a log bundle …) that differ
only by config.

This is for archives whose *unit of meaning is the whole bundle* — kept as one record
rather than decomposed into one record per member (`artifact_kind: decomposable`).
Genuinely structured zip formats (xlsx/docx/epub) are "more than a zip with stuff in it"
and keep their own specialized id-keyed drafters; they never reach this code.

**The record is a manifest, not a copy.** Unlike the PDF / HTML / EPUB drafters — which
*transform* their source (rasterize, OCR, clean markup) and so must materialize a body —
a zip member is already verbatim, content-addressed bytes that resolve on demand via
`corpus://<id>?path=<rel>` (the `transforms/zip.py` `path=` transform + `working_kind:
zip`). Copying that text into the record body would only duplicate the immutable artifact,
and the drafter does no transformation that would justify a body. So it inlines nothing:

- Every member → a metadata-zone `<!--embed-->` (blake3 `transport`, content-sniffed
  `media_type`, address `path=<rel>`) that the normalizer later describes.
- A member with a renderable **atom** (text / image / audio / video — text decided by
  content, not extension, so a `.cfg`/`.conf`/extensionless log is correctly text) is
  additionally positioned in the content zone by a **body-empty marker** segment at the
  same address (spec §4.3.2.2 — case (a) for media, case (c) for a verbatim text member).
- An opaque binary (no renderable atom) is an embed only, no content-zone segment (the
  EPUB orphan-image pattern; it draws the soft `embed-unreferenced` lint warning).

`draft.manifest` config (all optional):

    root_strip   bool — when every member sits under one wrapper dir
                        (`<host>-diagnostics-<ts>/`), strip it from rendered paths.
    sectioning   str  — `top_level_folders` (each top-level dir → a Section, its members →
                        marker Segments; root-level members → a synthetic "(root)" Section)
                        or `flat` (one flat list of top-level marker Segments). Default `flat`.

Members are addressed `path=<relpath>`; sections by their folder, `path=<folder>/`.
"""

from __future__ import annotations

import mimetypes
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

from corpus import hashing, recordbuild, records, touches, ziparchive
from corpus.draft import DrafterResult, register_strategy
from corpus.segments import Section, Segment

_DETECTOR = touches.script_identifier("draft.zip-manifest")


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
    sectioning = str(cfg.get("sectioning") or "flat").strip().lower()

    seg_items: list[tuple[str, Segment]] = []  # (relpath, body-empty marker segment)
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
                total += info.file_size
                data = zf.read(info.filename)
                media_type, atom = _classify(rel, data)
                digest = hashing.hash_bytes(data, also=())["blake3"]
                embeds.append(
                    {
                        "media_type": media_type,
                        "address": f"path={rel}",
                        "transport": records.format_hash("blake3", digest),
                        "fields": {"bytes": info.file_size},
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
            seg.entry = rel  # top-level markers carry the relpath as their TOC label
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


def _classify(rel: str, data: bytes) -> tuple[str, str | None]:
    """Return `(media_type, atom)` for a member. Text is decided by **content** (UTF-8, no
    NULs), not extension, so a `.cfg`/`.conf`/extensionless config or log is correctly text;
    a precise extension-guessed type (`application/json`, `image/png`) is preserved on the
    embed. `atom` is the content atom for the positioning marker — None for an opaque binary
    (no renderable atom → embed only)."""
    guessed = mimetypes.guess_type(rel)[0]
    if _is_text(data):
        return (guessed or "text/plain", "text")
    media_type = guessed or "application/octet-stream"
    return (media_type, _media_atom(media_type))


def _is_text(data: bytes) -> bool:
    """A pragmatic text sniff: no NUL byte and decodes as UTF-8. Members are read whole
    (we hash them anyway), so this checks the full bytes — no truncation boundary issues.
    A non-UTF-8 text encoding (rare on the Linux bundles this targets) reads as binary."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _media_atom(media_type: str) -> str | None:
    """The content atom for a non-text member, or None for an opaque binary."""
    mt = media_type.split(";", 1)[0].strip().lower()
    if mt.startswith("image/"):
        return "image"
    if mt.startswith("audio/"):
        return "audio"
    if mt.startswith("video/"):
        return "video"
    return None


def _folder_sections(seg_items: list[tuple[str, Segment]]) -> list[Section | Segment]:
    """Group the marker segments by their top-level folder (after root-strip) into Sections.
    Root-level members (no `/`) collect into a synthetic `(root)` section so the content
    zone stays homogeneous (all Sections), per the grammar's no-mixed-top-level rule.
    Folders whose members are all opaque binaries (no marker) simply don't appear."""
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
