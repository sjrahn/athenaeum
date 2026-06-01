"""Per-MIME deterministic body extraction (the `draft` lifecycle step).

Produces a faithful first-pass body from a captured artifact (spec §8.1). The
LLM-driven `normalize` step lives elsewhere — the drafter writes only what it can
extract deterministically from the bytes.

Drafters are dispatched by mime-schema id (e.g. `application/application_pdf`).
The registry lets corpus repos add their own drafters for custom mime schemas
without editing this package.

Interface (per spec §7.1 / §7.4):

    draft(
        binary_path: Path,
        *,
        corpus_root: Path,
        record_id: str,
        record_metadata: dict,
    ) -> DrafterResult

`DrafterResult` is a TypedDict with these keys:

    fields       — artifact-block extended fields (per the mime schema)
    segments     — content-zone blocks (list of Section | Segment) or None
    embeds       — metadata-zone embeds (list of dicts: {media_type, address, transport, fields})
    title        — refined artifact title or None
    issues       — spec §4.3.3.1 issue dicts: {id, severity, resolution, detector, address?, ...}
    canonical    — `<algo>:<hex>` if the mime schema declared a canonical_strategy; else None

Issues emitted by the drafter MUST use our spec's vocabulary (severity ∈ {blocking,
warning, info}; resolution ∈ {open, fixed, wontfix, superseded}; detector as a touch
identifier). Reconciliation #2.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict


class DrafterResult(TypedDict, total=False):
    """Return value of a drafter."""

    fields: dict[str, Any]
    segments: list[Any] | None  # list[segments.Section | segments.Segment]
    embeds: list[dict[str, Any]]
    title: str | None
    issues: list[dict[str, Any]]
    canonical: str | None


DrafterFn = Callable[..., DrafterResult]
REGISTRY: dict[str, DrafterFn] = {}


def register(schema_id: str) -> Callable[[DrafterFn], DrafterFn]:
    """Decorator to register a drafter keyed on its mime-schema id."""

    def decorator(fn: DrafterFn) -> DrafterFn:
        if schema_id in REGISTRY:
            raise ValueError(f"drafter already registered for schema id {schema_id!r}")
        REGISTRY[schema_id] = fn
        return fn

    return decorator


def get_drafter(schema_id: str) -> DrafterFn | None:
    """Look up the drafter for a mime-schema id (e.g. `application/application_pdf`)."""
    return REGISTRY.get(schema_id)


# Importing the per-MIME submodules registers their drafters. The office drafters
# lazy-import their heavy deps (openpyxl / xlrd) inside their functions, so importing
# them here is safe without the `[office]` extra; docx uses only the stdlib.
from . import audio as _audio  # noqa: E402, F401
from . import docx as _docx  # noqa: E402, F401
from . import image as _image  # noqa: E402, F401
from . import pdf as _pdf  # noqa: E402, F401
from . import video as _video  # noqa: E402, F401
from . import xls as _xls  # noqa: E402, F401
from . import xlsx as _xlsx  # noqa: E402, F401

# HTML drafter is a larger lift; lands later.
# from . import html as _html
