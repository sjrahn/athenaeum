"""Resolve an origin overlay's declared `regions:` against one artifact — spec §7.2, 3.9.

**The rule this module exists to implement:** a byte of the artifact belongs to exactly one
declared region, the **innermost** one containing it.

Without it a declaration set has two defensible readings that differ by tens of thousands of
anchors, because application markup nests: a page's outermost content element contains its
breadcrumb, its header block and its cross-link rail, so reading that element as `subject`
claims all three as the page's subject while the overlay's own next rows say they are not.
(Measured on `my.alldata.com`: `ad-repair-article` wraps `div.article-breadcrumb`,
`div.vehicle-info` and `ad-repair-related-information` on 4,989 records — and
`ad-repair-vehicle-components` wraps the rail on a further 738, which is why the rule is
stated over the declaration SET and not patched into one selector.)

Subject-inside-subject is the same rule doing its other job: `ad-repair-article` contains
`ad-repair-dynamic-content` on 4,208 records, and a reader that unions subject matches counts
that content twice.

**Offsets, not a DOM walk.** Containment is a property of the artifact and is resolved per
record: the same two selectors nest on one template and sit side by side on another, so
declaration order can never imply nesting. Offsets also keep this cheap enough to run over a
whole hub, and — the operational reason — they make the answer independent of whichever HTML
parser a caller happens to hold, so a census and a sweep reading the same declarations get the
same map.

Selector support is deliberately narrow: a bare element name (`ad-repair-article`) and
`tag.class` (`div.article-breadcrumb`). That is what origin overlays declare today, and a
selector this module cannot resolve is REPORTED rather than silently skipped — a region that
quietly fails to match reads exactly like a region that is genuinely absent, which is the
failure mode §7.2's gate exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Region", "RegionMap", "resolve", "selector_pattern"]

_BARE = re.compile(r"[a-z][\w-]*", re.I)
_TAG_CLASS = re.compile(r"(\w+)\.([\w-]+)")


def selector_pattern(selector: str) -> re.Pattern[str] | None:
    """A compiled matcher for the selector forms origin overlays use, else None.

    The class form does NOT assume quoted attributes: the lean capture path emits
    `class=foo` unquoted, and a pattern requiring quotes matches nothing on exactly the
    artifacts this is meant to read.
    """
    selector = (selector or "").strip()
    if _BARE.fullmatch(selector):
        return re.compile(rf"<{selector}\b[^>]*>.*?</{selector}>", re.S | re.I)
    if m := _TAG_CLASS.fullmatch(selector):
        tag, cls = m.groups()
        # NOT `\b` around the class name: CSS class tokens are whitespace-delimited and
        # routinely contain hyphens, and `\b` treats a hyphen as a boundary — so
        # `div.article-breadcrumb` would match `class=article-breadcrumb-legacy`, a
        # DIFFERENT region. Lookarounds that count `-` as part of the token fix it.
        return re.compile(
            rf"<{tag}\b[^>]*\bclass\s*=\s*[\"']?[^\">]*"
            rf"(?<![\w-]){re.escape(cls)}(?![\w-])[^>]*>.*?</{tag}>",
            re.S | re.I,
        )
    return None


@dataclass(frozen=True)
class Region:
    """One matched occurrence of one declared region."""

    role: str
    renders: str  # subject | framing | never
    selector: str
    start: int
    end: int
    declaration_index: int  # position in `regions:`, which orders the trailing span

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass
class RegionMap:
    """Every matched region occurrence in one artifact, plus the declaration errors found.

    `errors` is part of the result rather than an exception: a malformed declaration must be
    reported alongside a usable map, because refusing the whole map would make one bad row
    look like a host that declares nothing.
    """

    regions: list[Region] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def owner(self, offset: int) -> Region | None:
        """The innermost declared region containing *offset*, or None.

        Ties on size cannot happen for genuinely nested markup (two elements cannot span the
        same bytes), but identical selectors declared twice would produce one; the earlier
        declaration wins so the answer is deterministic.
        """
        best: Region | None = None
        for r in self.regions:
            if r.start <= offset < r.end and (
                best is None
                or r.size < best.size
                or (r.size == best.size and r.declaration_index < best.declaration_index)
            ):
                best = r
        return best

    def renders_at(self, offset: int) -> str | None:
        """`subject` / `framing` / `never`, or None where no region covers the offset.

        None is NOT `subject` — §7.2: silence is omission. Callers must treat it as such.
        """
        owner = self.owner(offset)
        return owner.renders if owner else None

    def spans(self, renders: str) -> list[Region]:
        """The MAXIMAL occurrences rendering as *renders*, in document order.

        Maximal = not strictly contained by another region of the **same** `renders`. That is
        what a caller building a span actually wants: each framing region once, not once for
        the rail and again for the rail's own nested declaration. A region of a *different*
        kind containing this one changes nothing here — the inner one still governs its bytes,
        which is `owner`'s job and the point of the amendment.
        """
        out = [
            r
            for r in self.regions
            if r.renders == renders
            and not any(
                o is not r
                and o.renders == renders
                and o.start <= r.start
                and r.end <= o.end
                and (o.start, o.end) != (r.start, r.end)
                for o in self.regions
            )
        ]
        return sorted(out, key=lambda r: r.start)

    def roles_present(self) -> list[str]:
        return sorted({r.role for r in self.regions})


def _overlaps_without_containing(a: Region, b: Region) -> bool:
    """Spans that interleave: each starts inside the other but neither contains the other.

    No DOM produces this, so it means the declaration is wrong — two selectors matching
    across each other's boundaries. Reported, never resolved by picking a winner.
    """
    if a.end <= b.start or b.end <= a.start:
        return False  # disjoint
    contains = (a.start <= b.start and b.end <= a.end) or (b.start <= a.start and a.end <= b.end)
    return not contains


def resolve(html: str, declarations: list[dict[str, Any]]) -> RegionMap:
    """Match every declaration against *html* and return the resolved map.

    *declarations* is `schemas.origin_regions(...)` output — rows already normalized to
    `{role, selector, renders}`.
    """
    out = RegionMap()
    for index, row in enumerate(declarations or []):
        selector = str(row.get("selector") or "").strip()
        renders = str(row.get("renders") or "").strip().lower()
        role = str(row.get("role") or "") or selector
        pattern = selector_pattern(selector)
        if pattern is None:
            out.errors.append(
                f"regions[{index + 1}] ({role}): selector {selector!r} is not a form this "
                f"reader resolves (element name or tag.class)"
            )
            continue
        for m in pattern.finditer(html):
            out.regions.append(
                Region(
                    role=role,
                    renders=renders,
                    selector=selector,
                    start=m.start(),
                    end=m.end(),
                    declaration_index=index,
                )
            )

    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(out.regions):
        for b in out.regions[i + 1 :]:
            if a.role == b.role or not _overlaps_without_containing(a, b):
                continue
            key = tuple(sorted((a.role, b.role)))
            if key in seen:
                continue
            seen.add(key)
            out.errors.append(
                f"regions: {a.role!r} and {b.role!r} match overlapping spans that neither "
                f"contains — no DOM produces this, so one of the selectors is wrong"
            )
    return out
