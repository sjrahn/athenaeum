"""EPUB draft extraction (deterministic, no LLM).

Reads an EPUB's OPF package via `corpus.epub` and emits one bare `<!--segment text-->`
per spine (reading-order) content document, addressed `spine=<N>` with the document's
own title as the `entry:` TOC label. Each segment body is the spine document's XHTML
mechanically cleaned to structural HTML (headings, prose, lists, tables) — images and
non-rendered infrastructure dropped; the same mechanical philosophy as the HTML drafter
(`draft/html.py`), leaving section grouping and rendering to the normalizer.

This is the EPUB analogue of the outline-less PDF shape: a flat list of top-level
content segments. The normalizer MAY later group them into sections along the book's
nav/TOC structure (see the schema's normalization guidance).

Publication metadata (Dublin Core title/creator/language/publisher/date/identifier)
lands as namespaced `epub_*` artifact fields; `epub_title` is the format's title
candidate (there is no generic artifact `title`). Per spec §1.5 the body is faithful —
no interpretation. An EPUB with no readable spine yields zero segments + a
`partial-content` issue.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from corpus import content_hash, epub, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Section, Segment

_DRAFTER_DETECTOR_ID = touches.script_identifier("draft.application/application_epub")


@register("application/application_epub")
def draft(
    epub_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    pkg = epub.read_package(epub_path)
    text_algos = algos_for_atom("text", fingerprint)

    fields: dict[str, Any] = {}
    md = pkg.metadata
    # Namespaced title candidate + provenance fields (no generic artifact `title`).
    if v := md.get("title"):
        fields["epub_title"] = v
    if v := md.get("creator"):
        fields["epub_creator"] = v
    if v := md.get("language"):
        fields["epub_language"] = v
    if v := md.get("publisher"):
        fields["epub_publisher"] = v
    if v := md.get("date"):
        fields["epub_date"] = v
    if v := md.get("identifier"):
        fields["epub_identifier"] = v
    fields["spine_item_count"] = len(pkg.spine)
    fields["toc_entry_count"] = len(pkg.toc)

    # One cleaned-body text segment per non-empty spine document — spine is the EPUB's
    # transport grain (like a PDF page). Built without `entry` so they can sit inside
    # sections; the flat fallback adds the per-document title as `entry`.
    def _segment(n: int, body: str, *, entry: str | None) -> Segment:
        return Segment(
            atom="text",
            address=f"spine={n}",
            entry=entry,
            perceptual=text_fingerprints(body, text_algos),
            body=body,
        )

    # The EPUB's images are separately-stored zip members → embeds (like an HTML page's
    # inline images), addressed `spine=<N>&el=<K>` and deduped by byte hash across the book.
    resources = epub.read_resources(epub_path)
    embed_by_hash: dict[str, dict[str, Any]] = {}

    docs: list[tuple[int, str, str]] = []  # (spine_index, cleaned_body, document_title)
    for n, doc in enumerate(pkg.spine, start=1):
        body, doc_embeds = epub.clean_xhtml_body(
            doc.data, image_resolver=epub.make_image_resolver(resources, doc.href)
        )
        if not (body.strip() or doc_embeds):
            continue
        docs.append((n, body, epub.document_title(doc.data)))
        for em in doc_embeds:
            slot = embed_by_hash.setdefault(
                em["byte_hash"],
                {k: em[k] for k in ("media_type", "width", "height", "alt")} | {"addresses": []},
            )
            slot["addresses"].extend(f"spine={n}&el={el}" for el in em["els"])

    embeds = [_embed_block(byte_hash, e) for byte_hash, e in embed_by_hash.items()]

    # Group segments into sections along the nav/NCX TOC — the EPUB analogue of the PDF
    # outline → sections (top-level entries only; sub-headings are intra-document prose
    # the normalizer recovers). Sectionless flat list when the book carries no usable TOC.
    blocks: list[Section | Segment] | None = _toc_sections(
        docs, pkg.toc, len(pkg.spine), _segment
    )
    if blocks is None:
        blocks = [_segment(n, body, entry=title or None) for n, body, title in docs]

    issues: list[dict[str, Any]] = []
    if not docs:
        issues.append(
            {
                "id": "partial-content",
                "subtype": "empty-body",
                "severity": "blocking",
                "resolution": "open",
                "detector": _DRAFTER_DETECTOR_ID,
                "fields": {
                    "description": (
                        "EPUB produced no readable spine content (missing/unreadable OPF "
                        "package, empty spine, or all spine documents were non-textual)."
                    ),
                },
            }
        )

    algo = canonical_algo or "blake3-canonical-epub"
    canonical = records.format_hash(
        algo.split("-", 1)[0], content_hash.compute(algo, epub_path)
    )

    recordbuild.add_blocks(build, blocks)
    return {
        "fields": fields,
        "embeds": embeds,
        "issues": issues,
        "canonical": canonical,
    }


def _embed_block(byte_hash: str, e: dict[str, Any]) -> dict[str, Any]:
    """Shape one accumulated image into a `<!--embed-->` block dict. `address` collapses to
    a scalar for a single occurrence, else the list of every `spine=<N>&el=<K>` the bytes
    appear at (the polymorphic str | list[str] convention, spec §4.3)."""
    addresses = e["addresses"]
    fields: dict[str, Any] = {"width": e["width"], "height": e["height"]}
    if e["alt"]:
        fields["alt"] = e["alt"]
    return {
        "media_type": e["media_type"],
        "address": addresses[0] if len(addresses) == 1 else addresses,
        "transport": f"blake3:{byte_hash}",
        "fields": fields,
    }


def _toc_sections(
    docs: list[tuple[int, str, str]],
    toc: list[epub.TocEntry],
    spine_count: int,
    seg_factory: Callable[..., Segment],
) -> list[Section | Segment] | None:
    """Wrap the per-spine-document segments into sections keyed by the TOC entries —
    each entry spans the spine range up to the next entry, exactly as the PDF drafter
    groups pages by outline. Spine documents before the first TOC target become a
    synthetic `Front matter` section (the EPUB analogue of the PDF `Preamble`). Returns
    None (→ sectionless fallback) when the book has no usable TOC."""
    if not toc:
        return None
    body_by_spine = {n: body for n, body, _title in docs}
    sections: list[Section | Segment] = []

    def _children(start: int, end: int) -> list[Segment]:
        return [
            seg_factory(n, body_by_spine[n], entry=None)
            for n in range(start, end + 1)
            if n in body_by_spine
        ]

    first = toc[0].spine_index
    if first > 1 and (front := _children(1, first - 1)):
        sections.append(
            Section(address=_spine_range(1, first - 1), entry="Front matter", segments=front)
        )
    for k, entry in enumerate(toc):
        end = toc[k + 1].spine_index - 1 if k + 1 < len(toc) else spine_count
        children = _children(entry.spine_index, end)
        if children:
            sections.append(
                Section(
                    address=_spine_range(entry.spine_index, end),
                    entry=entry.title,
                    segments=children,
                )
            )
    return sections or None


def _spine_range(start: int, end: int) -> str:
    """Section address spanning spine documents `start..end` (1-based). Uses the plural
    `spines=` param for the grouping range, distinct from a segment's `spine=<N>` point —
    mirroring the PDF schema's `pages=` (section) vs `page=` (segment) convention."""
    return f"spines={start}" if start >= end else f"spines={start}-{end}"
