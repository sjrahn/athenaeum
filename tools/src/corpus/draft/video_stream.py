"""Promoted video-stream leaf drafter (§1.2, §7.2.1) — the scene-cut marker sequence.

**The PDF's page markers, on a timeline.** `draft/pdf.py` emits one body-empty
`<!--segment image-->` per page at `page=<N>`, sectionless, making no shape judgment; the
authoring pass then probes each page and re-segments. A video stream leaf gets the identical
treatment with scene cuts in place of pages: one marker per span at
`time_range=<start>-<end>`, sectionless, and the span's **first frame** is what materializes
— the stand-in still that makes OCR and description possible without decoding the stream.

Three things make this different from the PDF, and each one is a rule rather than a detail:

**A page count is a fact in the bytes; a scene boundary is a detector's opinion at a
setting.** So the strategy is *resolved once at promotion* and stamped (`cutting:`, §7.2.1),
and this drafter runs the STAMPED strategy — never a fresh resolution. A leaf with no stamp
emits **no markers at all**: unstamped is unresolved, not defaulted, and re-cutting on sight
is the exact silent re-addressing the stamp exists to prevent.

**The timeline belongs to the container, not to this leaf.** A bare payload (h264/hevc/av1,
§2) carries no container timing at all — so detection runs against
`corpus://<container>?stream_id=<N>` reached through the leaf's own containment lineage. That
is §1.2's move for chapter marks ("tracks inherit the container's chapter marks at read time
through lineage — never copied, because the track's own bytes do not carry them"), applied to
the timeline the marks sit on. It also keeps one shared timeline across the container's
tracks, which is what lets the video leaf's spans and the audio leaf's transcript spans be
read against each other at all.

**A cut count that changed HOLDS the record.** If re-derivation finds a different number of
spans than the stamp attests, the strategy that produced this record's authored segments is
not the strategy that would produce them now. Emitting the new markers would re-point every
`time_range=` out from under whatever cites it, so nothing is emitted and the disagreement is
filed as an error (§7.2.1's second rule).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import frontmatter

from corpus import cut as cut_mod
from corpus import cutting, recordbuild, records, touches
from corpus.draft import DrafterResult, register
from corpus.segments import Segment

log = logging.getLogger(__name__)

_STREAM_SCHEMA_IDS = ("video/video_h264", "video/video_hevc", "video/video_av1")

#: Result keys the stamp carries alongside the declaration (`cutting.stamp` merges them in).
#: Stripping them recovers the DECLARATION — what the strategy was resolved to — which is what
#: re-derivation must run under.
_STAMP_RESULT_KEYS = ("cuts", "duration")


def draft(
    stream_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path,
    record_id: str,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,  # frame markers are body-empty
) -> DrafterResult:
    fields: dict[str, Any] = {"size_bytes": stream_path.stat().st_size}
    issues: list[dict[str, Any]] = []

    post = frontmatter.Post("", **dict(record_metadata or {}))
    stamp = records.cutting(post)
    if stamp is None:
        # Not a defect: a leaf promoted before 3.11 existed, or one whose container declares no
        # strategy. Reported, never guessed at (§7.2.1's third rule).
        issues.append(
            _issue(
                "cut-unresolved",
                "info",
                "no `cutting:` stamp — the cut strategy has not been resolved for this "
                "leaf, so no scene markers are derived (spec §7.2.1: unstamped is "
                "unresolved, not defaulted). `corpus cut <id>` resolves and stamps it.",
            )
        )
        return {"fields": fields, "embeds": [], "issues": issues}

    lineage = cut_mod.stream_lineage(post)
    if lineage is None:
        issues.append(
            _issue(
                "cut-unresolved",
                "warning",
                "carries a `cutting:` stamp but no containment-lineage origin naming a "
                "container stream — an elementary stream has no timeline of its own, so "
                "there is nothing to detect against.",
            )
        )
        return {"fields": fields, "embeds": [], "issues": issues}

    from corpus.store import ArtifactMissing

    container_id, stream_address = lineage
    declaration = {k: v for k, v in stamp.items() if k not in _STAMP_RESULT_KEYS}
    try:
        container_post = records.load(_container_path(corpus_root, container_id))
        outcome = cut_mod.cut_stream(
            corpus_root,
            container_post,
            container_id,
            stream_address,
            strategy=declaration,
        )
    except (
        cut_mod.Unresolved, NotImplementedError, ArtifactMissing, OSError, RuntimeError
    ) as exc:
        issues.append(
            _issue(
                "cut-unresolved",
                "warning",
                f"could not re-derive the cut list from container "
                f"{container_id[:12]}?{stream_address}: {exc}",
            )
        )
        return {"fields": fields, "embeds": [], "issues": issues}

    attested = stamp.get("cuts")
    if isinstance(attested, int) and attested != len(outcome.spans):
        # Held (§7.2.1). Report both counts: the whole value of the stamp is that the
        # disagreement is legible, and a bare "mismatch" would leave the authoring pass to
        # re-run the detector by hand to find out which way it moved.
        issues.append(
            _issue(
                "cut-count-drift",
                "error",
                f"the stamped strategy now yields {len(outcome.spans)} spans, but the "
                f"`cutting:` stamp attests {attested} — the segmentation this record's "
                f"authored addresses rest on is not the one the strategy produces now. No "
                f"markers derived; re-segmentation is a deliberate authoring act "
                f"(spec §7.2.1).",
                fields={"attested_cuts": attested, "derived_cuts": len(outcome.spans)},
            )
        )
        return {"fields": fields, "embeds": [], "issues": issues}

    for signal in outcome.signals:
        # The spans stand; the signal is information the authoring pass acts on. A strategy
        # that did not fit is a fact about this content, not an error in the record.
        issues.append(_issue(f"cut-{signal.id}", "warning", signal.detail))

    recordbuild.add_blocks(
        build,
        [Segment(atom="image", address=address, body="") for address in outcome.addresses],
    )
    return {"fields": fields, "embeds": [], "issues": issues}


for _sid in _STREAM_SCHEMA_IDS:
    register(_sid)(draft)


# ---------- helpers ---------- #


def _container_path(corpus_root: Path, container_id: str) -> Path:
    from corpus import paths

    return paths.record_path(corpus_root, container_id)


def _issue(
    issue_id: str, severity: str, reason: str, *, fields: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A §4.3.3.1-shaped mechanical issue from this drafter."""
    return {
        "id": issue_id,
        "severity": severity,
        "detector": touches.script_identifier("draft.video_stream"),
        "fields": {"reason": reason, **(fields or {})},
    }


def addresses_for_stamp(
    corpus_root: Path, post: frontmatter.Post
) -> tuple[list[str], list[cutting.Span]]:
    """The marker addresses this leaf's stamp implies — the same derivation `draft` performs,
    without the Build. For callers that want the spans (the `scene` op, `corpus cut --check`)
    rather than a body. Raises `cut.Unresolved` where `draft` would file an issue."""
    stamp = records.cutting(post)
    if stamp is None:
        raise cut_mod.Unresolved("no `cutting:` stamp — the strategy is unresolved")
    lineage = cut_mod.stream_lineage(post)
    if lineage is None:
        raise cut_mod.Unresolved("no containment-lineage origin naming a container stream")
    container_id, stream_address = lineage
    container_post = records.load(_container_path(corpus_root, container_id))
    outcome = cut_mod.cut_stream(
        corpus_root,
        container_post,
        container_id,
        stream_address,
        strategy={k: v for k, v in stamp.items() if k not in _STAMP_RESULT_KEYS},
    )
    return outcome.addresses, outcome.spans
