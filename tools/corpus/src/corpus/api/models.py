"""Request/response models for the corpus API's write surface.

Lives under `corpus.api` (imported only with the `[api]` extra), so pydantic stays out of
the base install. The structural contract is enforced here (atom is one of the four, box
is four numbers); semantic box validity (in-range, positive, inside the unit square) and
overlay/section validity are the library's job (`corpus.regions`), surfaced as a 400.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegionIn(BaseModel):
    """One drawn crop region. `box` is `[x, y, w, h]` in relative [0,1] coordinates;
    `page` is required for paged artifacts (PDFs) and omitted for single images;
    `overlay` is a bare suffix (`data-table`) or full id (`text/data-table`), `""` for a
    bare atom; `entry` is a TOC label honored only for top-level (sectionless) segments."""

    page: int | None = None
    box: tuple[float, float, float, float]
    atom: Literal["text", "image", "audio", "video"]
    overlay: str = ""
    entry: str = ""


class SaveRegionsRequest(BaseModel):
    regions: list[RegionIn] = Field(default_factory=list)


class SaveRegionsResponse(BaseModel):
    record_id: str
    segment_count: int
    bbox_segment_count: int
    addresses: list[str]
    status: str | None
    touch: list[str]


class GraphNode(BaseModel):
    """One connection node. `kind` is origin | embed | record | link; `recId` is set when the
    node opens a corpus record (a classification peer or a captured cross-reference); `url` /
    `host` are present for origin + link nodes."""

    id: str
    kind: Literal["origin", "embed", "record", "link"]
    label: str
    sub: str
    recId: str | None = None
    url: str | None = None
    host: str | None = None


class GraphResponse(BaseModel):
    resolved: list[GraphNode] = Field(default_factory=list)
    uncaptured: list[GraphNode] = Field(default_factory=list)
