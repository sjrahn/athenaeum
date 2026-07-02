"""PDF draft extraction (deterministic, uniform image-of-document).

Every PDF drafts to the same shape: one body-empty `image` Segment per page, addressed
`page=<N>`, **sectionless**. The page raster is the faithful transport unit; the drafter
makes **no** born-digital-vs-scanned determination and extracts **no** text.

Deciding a page's shape (born-digital text vs scanned image-of-document), pulling its
embedded text layer, mapping text to regions, and grouping pages into outline sections are
all **normalizer** work — powered by the resolver's PDF introspection ops:

    corpus://<id>?page=<N>&text     the page's embedded text layer
    corpus://<id>?page=<N>&words    per-word boxes (JSON)
    corpus://<id>?page=<N>&probe    per-page structural probe (JSON)
    corpus://<id>?probe             whole-document probe (JSON)
    corpus://<id>?outline           the PDF outline / TOC tree (JSON)
    corpus://<id>?page=<N>[&bbox=…] render the page (or a region) as an image

The page-introspection logic lives in `corpus.pdf_introspect`. The drafter only lifts the
`/Info` metadata (page_count, title, author, producer, dates) — faithful, cheap frontmatter.

Per spec §1.5/§4.3 the body is faithful — no interpretation, no editorial. See the
`application/pdf` schema's `normalization.guidance` for the normalizer playbook.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from corpus import content_hash, pdf_introspect, recordbuild, records
from corpus.draft import DrafterResult, register
from corpus.segments import Segment

log = logging.getLogger(__name__)


@register("application/application_pdf")
def draft(
    pdf_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,  # PDF text isn't fingerprinted (yet)
) -> DrafterResult:
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)

    fields: dict[str, Any] = {"page_count": page_count, **pdf_introspect.document_info(reader)}

    # Uniform image-of-document: one body-empty image-atom positioning marker per page,
    # sectionless. The normalizer reads the text layer / probes / sections via the resolver.
    blocks = [
        Segment(atom="image", address=f"page={i}", body="") for i in range(1, page_count + 1)
    ]

    # Canonical hash per the mime schema's `canonical_strategy.algo` (the strategy id
    # encodes its hash family, e.g. `blake3-canonical-pdf` → `blake3:`); falls back to the
    # PDF default when the schema/caller doesn't override it.
    algo = canonical_algo or "blake3-canonical-pdf"
    canonical = records.format_hash(algo.split("-", 1)[0], content_hash.compute(algo, pdf_path))

    recordbuild.add_blocks(build, blocks)
    return {
        "fields": fields,
        "embeds": [],
        "issues": [],
        "canonical": canonical,
    }
