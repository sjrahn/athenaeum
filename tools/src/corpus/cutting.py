"""Cut strategies: turning a timeline into the spans a marker can address (§7.2.1, 3.11).

**What this module is, and what it deliberately is not.** The mechanical stage of video
segmentation proposes boundaries; the authoring pass verifies them (§12.20 item 5). This
module is the mechanical half and nothing more: it converts a strategy declaration plus a
detector's output into a list of spans and the `cutting:` stamp that records how. It makes no
judgment about whether a span is a *scene* — that is the authoring pass's, and the pilot
proved why (§12.20 OQ1: `scenes=0.3` recovered 33 of 36 slides, and the three misses are not
threshold-fixable, so no parameter substitutes for the eyeball pass).

**Why points become spans here rather than in the detector.** `scenes=<threshold>` already
exists (§6.2) and yields cut *points* — one timestamp per detected boundary. A segment
address is a *span* (`time_range=<start>-<end>`), and closing the final span requires the
artifact's duration, which the detector does not know. Keeping the conversion separate also
keeps it **pure and testable without ffmpeg**, which matters because the span arithmetic —
not the detection — is where an off-by-one silently re-points every address on a record.
"""

from __future__ import annotations

import itertools
from typing import Any

Span = tuple[float, float]

#: Strategies this module implements. A schema may declare any versioned id (§7.2.1); an
#: unknown one is a hard error at cut time rather than a silent fallback, because falling
#: back would segment a record under a strategy nobody declared.
KNOWN_STRATEGIES = ("scene-threshold", "keyframe", "fixed-interval")


def strategy_family(strategy_id: str) -> str:
    """`scene-threshold@0.1.0` → `scene-threshold`. The version pins reproducibility; the
    family selects the implementation."""
    return str(strategy_id or "").split("@", 1)[0]


def spans_from_cuts(
    cuts: list[float], duration: float, *, min_seconds: float = 0.0
) -> list[Span]:
    """Cut POINTS → addressable SPANS, closing the last one at `duration`.

    A cut at `t` means *a new span starts here*, so N cuts inside the timeline yield N+1
    spans. Empty cuts yield ONE span covering the whole artifact — which is the honest
    representation of "this strategy found no boundaries", and is exactly the signal the
    authoring pass needs to reach for a different strategy rather than accept a useless
    segmentation.

    `min_seconds` enforces a minimum separation by **de-clustering the cut points**, not by
    stretching spans. That distinction is the whole correctness question here. A detector
    firing at 10.0, 10.1 and 10.2 has found *one* transition across three adjacent frames,
    and the true boundary is the **first** of the cluster — so the later ones are dropped and
    the boundary stays at 10.0. Merging short spans into their predecessor instead would move
    the boundary to 10.2, silently mis-addressing the region by the width of the cluster.
    Over-segmentation is the named failure mode (a scrolling screen recording fires hundreds
    of times), so this floor is doing real work rather than guarding a corner.

    Only the **final** span is merged backwards, because the duration bound cannot move.

    Tolerant by construction: cuts are sorted, de-duplicated, and any at or beyond `duration`
    (or at/below zero) are dropped rather than producing an inverted or empty span. A
    boundary list is an *observation*, and an observation that disagrees with the duration is
    the detector's problem to survive, not a reason to raise.
    """
    if duration <= 0:
        return []
    end_bound = round(float(duration), 3)
    inside = sorted({round(float(c), 3) for c in cuts if 0.0 < float(c) < end_bound})
    if min_seconds:
        kept: list[float] = []
        last = 0.0                      # span 0 starts at the origin, so measure from there
        for c in inside:
            if c - last >= min_seconds:
                kept.append(c)
                last = c
        inside = kept
    bounds = [0.0, *inside, end_bound]
    spans: list[Span] = [(s, e) for s, e in itertools.pairwise(bounds) if e > s]
    if not spans:
        return [(0.0, end_bound)]
    # The last span alone cannot be fixed by de-clustering — its end IS the duration — so a
    # short tail folds back into its predecessor.
    if min_seconds and len(spans) > 1 and (spans[-1][1] - spans[-1][0]) < min_seconds:
        spans = [*spans[:-2], (spans[-2][0], spans[-1][1])]
    return spans


def fixed_interval_spans(duration: float, seconds: float) -> list[Span]:
    """Every `seconds` — the fallback that has to exist.

    Scene detection on a screen recording returns either ~1 cut (a static terminal) or
    hundreds (a scrolling one), and both mean *the strategy did not fit*. A record in that
    position needs somewhere conforming to go, and a fixed grid is honest about being
    arbitrary in a way a mis-tuned threshold is not."""
    if duration <= 0 or seconds <= 0:
        return []
    cuts, t = [], seconds
    while t < duration:
        cuts.append(round(t, 3))
        t += seconds
    return spans_from_cuts(cuts, duration)


def address_for(span: Span) -> str:
    """A span as the `time_range=` address value the resolver already accepts (§6.2).

    Not a new grammar: `time_range=` is already a registered video transform and already
    lint-legal as a self-slice address on a `video/*` record, so a marker emitted here needs
    nothing added to the address space."""
    start, end = span
    return f"time_range={_fmt(start)}-{_fmt(end)}"


def _fmt(value: float) -> str:
    """Trailing-zero-free seconds — `12.0` → `12`, `4.25` → `4.25`. The resolver parses
    floats, so the shortest exact spelling keeps stored addresses readable and stable."""
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text or "0"


def stamp(strategy: dict[str, Any], spans: list[Span], duration: float | None) -> dict:
    """The `cutting:` stamp (§7.2.1): the declaration's own keys, unrenamed, plus the result.

    A MERGE, never a translation — the declared parameters carry through verbatim so there is
    no key-mapping step in which one can be silently dropped, and `cuts` is the count a
    consumer compares against its own re-derivation to know whether it disagrees. That count
    is the whole reason the stamp exists; without it a strategy change re-points every
    `time_range=` on the record with nothing to notice."""
    out: dict[str, Any] = {**strategy, "cuts": len(spans)}
    if duration is not None:
        out["duration"] = round(float(duration), 2)
    return out
