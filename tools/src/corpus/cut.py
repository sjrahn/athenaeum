"""The cutting pass: a declared strategy → the spans a video stream leaf is addressed by.

`cutting.py` is the pure arithmetic (points → spans, the stamp). This module is the impure
half that stands between it and the corpus: it resolves the strategy, runs the detector,
and reports when the result is degenerate.

**Why detection runs against the CONTAINER, never the leaf.** The addresses land on the
promoted stream leaf (§1.2: "the video-track record owns frame work"), but a bare Annex-B
elementary stream carries no container timing — ffmpeg imputes a frame rate from SPS VUI
timing, or falls back to a default, and reports no duration at all. The container's
timeline is the real one, and it is also the *shared* one: the audio leaf's transcript
spans and the video leaf's scene spans have to mean the same seconds or they cannot be read
together. So every timeline operation for a stream leaf routes through
`corpus://<container>?stream_id=<N>&…` — which is §1.2's own move for chapter marks
("tracks inherit the container's chapter marks at read time through lineage — never copied,
because the track's own bytes do not carry them"), applied to the timeline those marks sit on.

**Why detection goes through the resolver rather than shelling out here.** `scenes=` is an
engine-versioned op (§6.2), so the resolver folds `ffmpeg@<version>` into its cache key and
records it in the sidecar. Routing through it means the cut list is cached once and reused —
which matters because promotion computes it to stamp the count, and the body derivation
computes it again to emit the addresses. Same URI, same cache entry, one decode.

**What is stamped and what is re-derived.** The stamp carries the strategy, its parameters
and the resulting cut COUNT — not the spans. That is `addressing:`'s precedent exactly
(§7.1: the parse's element count is stamped; the `el=` addresses are re-derived every time),
and the reason is the same: a stored derivable can disagree with its derivation. The count
is what makes the disagreement *detectable* (§7.2.1's re-attestation rule).
"""

from __future__ import annotations

import logging
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

from corpus import cutting, records, schemas
from corpus import functional_uri as furi

log = logging.getLogger(__name__)

#: A degenerate cut list is a SIGNAL, never a substitution. Scene detection on a screen
#: recording yields either ~1 cut (a static terminal) or one per frame (a scrolling one), and
#: both mean *the strategy did not fit*. The mechanical stage has to say so — an out-of-band
#: cut count is information the authoring pass acts on, not a result to hand over silently.
#: Both floors below are reporting thresholds only: nothing about the spans changes.
#:
#: 2.0s: a slide, a shot, or a scene the authoring pass would call one thing essentially never
#: lasts under two seconds; the pilot deck's shortest real slide ran far longer (§12.20 OQ1).
_OVER_SEGMENTED_MEDIAN_SECONDS = 2.0
#: …and a median needs a population before it means anything.
_OVER_SEGMENTED_MIN_SPANS = 20


class Unresolved(Exception):
    """The cut could not be attempted, and NOTHING was substituted (§7.2.1).

    Raised when the strategy does not resolve, when the leaf has no containment lineage to
    detect against, or when no duration is attested. Every one of these is a legitimate state
    for a record to be in — an unstamped leaf is *unresolved, not defaulted* — so the caller
    reports it and moves on rather than falling back to a strategy nobody declared.
    """


@dataclass(frozen=True)
class CutSignal:
    """Something the authoring pass needs told about this cut list."""

    id: str
    detail: str


@dataclass(frozen=True)
class CutOutcome:
    """One stream's cut, ready to stamp and to address by."""

    container_id: str
    stream_address: str
    strategy: dict[str, Any]
    spans: list[cutting.Span]
    duration: float
    stamp: dict[str, Any]
    raw_cut_count: int
    signals: list[CutSignal] = field(default_factory=list)

    @property
    def addresses(self) -> list[str]:
        """The `time_range=` address for each span, in timeline order."""
        return [cutting.address_for(s) for s in self.spans]


# ---------- lineage: which container, which stream ---------- #


def stream_lineage(post: frontmatter.Post) -> tuple[str, str] | None:
    """A promoted stream leaf's `(container_id, "stream_id=<N>")`, or None.

    Read from the record's containment-lineage origin (§8.1) — the one place the pairing is
    recorded. This is lineage used as *lineage*: to reach the timeline the leaf's own bytes do
    not carry, exactly as §6.2's lineage-chained resolution reaches a declared reference. It is
    NOT a byte-lookup route (§12.15's rule is untouched — residence still comes from the member
    index), which is why a leaf whose bytes were later ingested standalone still cuts correctly.
    """
    for uri in records.iter_origin_uris(post):
        if not str(uri).startswith("corpus://"):
            continue
        try:
            parsed = furi.parse(str(uri))
        except ValueError:
            continue
        params = [(k, v) for k, v in parsed.params if k == "stream_id" and v]
        if len(params) == 1 and len(parsed.params) == 1:
            return parsed.hash, f"stream_id={params[0][1]}"
    return None


# ---------- duration: the container's, because the leaf has none ---------- #


def container_duration(container_post: frontmatter.Post, container_path: Path | None) -> float:
    """The timeline's length in seconds — attested if it can be, probed if it must be.

    The attested field is preferred and is present on every container the drafter actually
    ran against (`draft/video.py` lifts ffprobe's `format.duration`). A promoted-but-never-
    drafted container has no attested facts at all, and probing is the honest fallback: it is
    the same measurement from the same tool, just taken now instead of at ingest.
    """
    fields = (records.artifact_block(container_post) or {}).get("fields") or {}
    value = fields.get("duration")
    try:
        if value is not None and float(value) > 0:
            return round(float(value), 3)
    except (TypeError, ValueError):
        pass
    if container_path is None:
        raise Unresolved("no attested duration and no artifact to probe")
    probed = _probe_duration(container_path)
    if probed is None:
        raise Unresolved(f"no attested duration, and ffprobe read none from {container_path.name}")
    return probed


def _probe_duration(path: Path) -> float | None:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        seconds = float((proc.stdout or "").strip())
    except ValueError:
        return None
    return round(seconds, 3) if seconds > 0 else None


# ---------- detection ---------- #


def detect_cuts(
    corpus_root: Path,
    container_id: str,
    stream_address: str,
    strategy: dict[str, Any],
    *,
    regenerate: bool = False,
) -> list[float]:
    """Run the strategy's detector over the container's stream → cut points in seconds.

    `fixed-interval@` needs no detector (its boundaries are arithmetic, computed by
    `cutting.fixed_interval_spans`) and returns nothing here. An unimplemented family raises
    rather than degrading to another — falling back would cut the record under a strategy
    nobody declared, and the stamp would then attest a lie.
    """
    family = cutting.strategy_family(str(strategy.get("id") or ""))
    if family == "fixed-interval":
        return []
    if family == "scene-threshold":
        threshold = strategy.get("threshold")
        if threshold is None:
            raise Unresolved(f"strategy {strategy.get('id')!r} declares no threshold")
        uri = f"corpus://{container_id}?{stream_address}&scenes={threshold}"
        return _resolve_cut_list(corpus_root, uri, regenerate=regenerate)
    if family in cutting.KNOWN_STRATEGIES:
        # `keyframe@` is named by the spec and not built. It is byte-work, not an engine
        # judgment — ISOBMFF `stss` sync samples timed through `stts` — so it belongs in
        # `corpus.streams` beside the other pinned parses, not behind ffmpeg. No schema
        # declares it, so nothing is blocked; see the backlog.
        raise NotImplementedError(f"cut strategy family {family!r} is declared but not implemented")
    raise Unresolved(f"unknown cut strategy family {family!r} (known: {cutting.KNOWN_STRATEGIES})")


def _resolve_cut_list(corpus_root: Path, uri: str, *, regenerate: bool) -> list[float]:
    """Resolve a `scenes=` URI and read its timestamps back.

    Tolerant on the parse (a blank or malformed line is skipped, §3) but NOT on the run: a
    detector that failed is an absence of information, and returning an empty cut list for it
    would be indistinguishable from a detector that found no boundaries — the one distinction
    the authoring pass most needs.
    """
    from corpus import resolver

    path = resolver.resolve(uri, corpus_root, regenerate=regenerate)
    cuts: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            cuts.append(float(line))
        except ValueError:
            log.warning("scenes= emitted an unparseable timestamp %r (skipped)", line)
    return cuts


# ---------- the pass ---------- #


def cut_stream(
    corpus_root: Path,
    container_post: frontmatter.Post,
    container_id: str,
    stream_address: str,
    *,
    container_path: Path | None = None,
    strategy: dict[str, Any] | None = None,
    regenerate: bool = False,
) -> CutOutcome:
    """Resolve, detect, and turn one container stream into addressable spans.

    `strategy` overrides resolution — the re-attestation path passes the leaf's ALREADY
    STAMPED strategy, because §7.2.1 resolves once at promotion and a re-resolution years
    later could silently answer differently (an overlay gained a `cut_strategy:`, a default
    moved). Promotion passes nothing and gets the mime-default ← origin-overlay ladder.
    """
    if strategy is None:
        strategy = schemas.resolve_cut_strategy_for_record(corpus_root, container_post)
    if not strategy:
        raise Unresolved(
            f"no cut strategy resolves for container {container_id[:12]} "
            f"({records.media_type_for(container_post) or 'unknown type'})"
        )

    duration = container_duration(container_post, container_path)
    cuts = detect_cuts(
        corpus_root, container_id, stream_address, strategy, regenerate=regenerate
    )

    family = cutting.strategy_family(str(strategy.get("id") or ""))
    if family == "fixed-interval":
        seconds = strategy.get("seconds")
        if not seconds:
            raise Unresolved(f"strategy {strategy.get('id')!r} declares no interval")
        spans = cutting.fixed_interval_spans(duration, float(seconds))
    else:
        spans = cutting.spans_from_cuts(
            cuts, duration, min_seconds=float(strategy.get("min_seconds") or 0.0)
        )

    return CutOutcome(
        container_id=container_id,
        stream_address=stream_address,
        strategy=dict(strategy),
        spans=spans,
        duration=duration,
        stamp=cutting.stamp(strategy, spans, duration),
        raw_cut_count=len(cuts),
        signals=degeneracy_signals(spans, duration, raw_cut_count=len(cuts)),
    )


def degeneracy_signals(
    spans: list[cutting.Span], duration: float, *, raw_cut_count: int
) -> list[CutSignal]:
    """Name the two ways a cut list is useless, without altering it.

    Both conditions are the same underlying fact — the strategy did not fit this content —
    and the authoring pass's response to each is different, which is why they are reported
    separately rather than as one "suspicious" flag.
    """
    signals: list[CutSignal] = []
    if len(spans) <= 1:
        signals.append(
            CutSignal(
                "no-boundaries",
                f"the strategy found no boundaries in {duration:.1f}s — the whole timeline "
                f"is one span, so this record needs a different strategy, not a re-run",
            )
        )
        return signals
    median = statistics.median(e - s for s, e in spans)
    if len(spans) >= _OVER_SEGMENTED_MIN_SPANS and median < _OVER_SEGMENTED_MEDIAN_SECONDS:
        signals.append(
            CutSignal(
                "over-segmented",
                f"{len(spans)} spans over {duration:.1f}s, median {median:.2f}s "
                f"({raw_cut_count} raw cuts) — continuous change (a scrolling screen "
                f"recording) fires the detector per frame; consider fixed-interval@",
            )
        )
    return signals
