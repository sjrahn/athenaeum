"""EPUB draft extraction (deterministic, no LLM).

Reads an EPUB's OPF package via `corpus.epub` and emits one bare `<!--segment text-->`
per spine (reading-order) content document, addressed `spine=<N>`. Each segment body is
the spine document's XHTML mechanically cleaned to structural HTML (headings, prose,
lists, tables) — images and non-rendered infrastructure dropped; the same mechanical
philosophy as the HTML drafter (`draft/html.py`).

A source-declared title becomes a leading STRUCTURAL byte-mark at the labeled position,
carrying that title verbatim (spec §4.3.2.3): a TOC entry's own title marks the spine
position its range starts at (when the book ships a usable nav/NCX TOC); absent a TOC,
each spine document's own `<title>` marks its own position instead — an untitled document
gets no mark either way. Flat throughout: no `Section` is ever asserted (a section binds a
FORM, which is a normalize-pass judgment, never a generic drafter's, §7.8/§4.3.2.1; 3.12
reconciliation #153) and no label is ever fabricated — the old synthetic "Front matter"
section for spine documents before the first TOC target does not survive, and neither
does any other label for that range: those documents were never individually titled by
this drafter and still aren't, exactly preserving what the source actually stated. This
is the EPUB analogue of the outline-less PDF shape: a flat reading order the normalizer
MAY later read and assert real sections along (see the schema's normalization guidance).

Publication metadata (Dublin Core title/creator/language/publisher/date/identifier)
lands as bare artifact fields — the opener's MIME (`application/epub+zip`) names the
format, so fields aren't prefixed; `title` is the title candidate. Per spec §1.5 the
body is faithful — no interpretation. An EPUB with no readable spine yields zero segments + a
`partial-content` issue.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from corpus import content_hash, epub, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import _STRUCTURAL as _STRUCTURAL_ATOM
from corpus.segments import Segment

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
    # Bare title candidate + provenance fields (the opener's MIME names the format).
    if v := md.get("title"):
        fields["title"] = v
    if v := md.get("creator"):
        fields["creator"] = v
    if v := md.get("language"):
        fields["language"] = v
    if v := md.get("publisher"):
        fields["publisher"] = v
    if v := md.get("date"):
        fields["date"] = v
    if v := md.get("identifier"):
        fields["identifier"] = v
    fields["spine_item_count"] = len(pkg.spine)
    fields["toc_entry_count"] = len(pkg.toc)

    # One cleaned-body text segment per non-empty spine document — spine is the EPUB's
    # transport grain (like a PDF page). Carries no label of its own (a content segment's
    # `entry` retired 3.5, §4.3.2.2) — a document's own title, when present, rides a
    # separate leading structural mark instead (§4.3.2.3), built by the callers below.
    def _segment(n: int, body: str) -> Segment:
        return Segment(
            atom="text",
            address=f"spine={n}",
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

    # Group segments by the nav/NCX TOC — the EPUB analogue of the PDF outline (top-level
    # entries only; sub-headings are intra-document prose the normalizer recovers), each
    # entry's title riding a leading structural mark rather than a Section. Flat fallback
    # (each document's own title, if any, marking its own position) when the book carries
    # no usable TOC.
    blocks: list[Segment] | None = _toc_segments(docs, pkg.toc, len(pkg.spine), _segment)
    if blocks is None:
        blocks = []
        for n, body, title in docs:
            if title:
                blocks.append(
                    Segment(atom=_STRUCTURAL_ATOM, address=f"spine={n}", level=1, body=title)
                )
            blocks.append(_segment(n, body))

    issues: list[dict[str, Any]] = []
    if not docs:
        issues.append(
            {
                "id": "partial-content",
                "subtype": "empty-body",
                "severity": "blocking",
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


def _toc_segments(
    docs: list[tuple[int, str, str]],
    toc: list[epub.TocEntry],
    spine_count: int,
    seg_factory: Callable[[int, str], Segment],
) -> list[Segment] | None:
    """A flat structural-mark-then-content segment list keyed by the TOC entries (spec
    §4.3.2.3) — each entry's own title marks the spine position its range starts at,
    exactly as the PDF drafter's outline groups pages, only without a `Section`
    (§7.8/§4.3.2.1; 3.12 reconciliation #153). Spine documents before the first TOC
    target get no mark at all: the old synthetic `Front matter` label was fabricated and
    does not survive, and (unlike the no-TOC fallback) these documents were never
    individually titled by this drafter either — nothing here to mark. Returns None (→
    the no-TOC fallback) when the book has no usable TOC."""
    if not toc:
        return None
    body_by_spine = {n: body for n, body, _title in docs}
    out: list[Segment] = []

    def _children(start: int, end: int) -> list[Segment]:
        return [
            seg_factory(n, body_by_spine[n])
            for n in range(start, end + 1)
            if n in body_by_spine
        ]

    first = toc[0].spine_index
    if first > 1:
        out.extend(_children(1, first - 1))
    for k, entry in enumerate(toc):
        end = toc[k + 1].spine_index - 1 if k + 1 < len(toc) else spine_count
        children = _children(entry.spine_index, end)
        if not children:
            continue
        out.append(
            Segment(
                atom=_STRUCTURAL_ATOM,
                address=f"spine={entry.spine_index}",
                level=1,
                body=entry.title or "",
            )
        )
        out.extend(children)
    return out or None
