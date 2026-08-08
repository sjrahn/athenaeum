"""Shared transcript → flat-segment splitter for the audio and video drafters.

Both drafters consume a `[Speaker N] (HH:MM:SS)` diarized transcript (produced by the
configured `TranscriptionAdapter`) and turn it into a FLAT list of `Segment`s in reading
order — one `text/transcript` `Segment` per checkpoint addressed by time-range
(checkpoints whose start+end round to one already-used whole-second address are merged so
no two segments share a `(opener-id, address)` identity).

*(3.12 reconciliation, #153)* No `Section` is ever asserted here: a section binds a FORM,
which is a normalize-pass judgment (or a declared shaper's mapping), never a generic
drafter's (§7.8, §4.3.2.1). Grouping is now purely internal — `_emit_sections` still
groups checkpoints by speaker run or by chapter to compute addresses and boundaries, but
the grouping never reaches the record as a stored span. The default grouping is one run
per speaker (`parse_transcript_sections`), which carries no label the source ever stated
(a speaker change is a machine inference, not a byte-fact) and so contributes no
structural mark at all. A video that ships chapter markers groups by its chapters instead
(`parse_chaptered_sections`); the uploader's own chapter title IS a byte-fact, so each
chapter's start gets a leading STRUCTURAL byte-mark carrying that title verbatim
(§4.3.2.3) — never a fabricated label, and never a Section's `entry`. The video drafter
additionally leads each group with a body-empty `image` keyframe marker (and the last
group closes with the video's final frame); the audio drafter passes
`video_stream_id=None` and gets transcript-only segments. A boundary instant is shared by
adjacent groups, so each `frame=<t>` address is emitted at most once (§4.3.2.2).
"""

from __future__ import annotations

import re
from typing import Any

from corpus.segments import _STRUCTURAL as _STRUCTURAL_ATOM
from corpus.segments import Segment

# Transcript segment header: `[Speaker N] (HH:MM:SS)` (or bare `(HH:MM:SS)`).
_SEGMENT_HEADER_RE = re.compile(
    r"^\[(?P<speaker>[^\]]+)\]\s+\((?P<timestamp>\d+:\d{2}:\d{2})\)\s*$",
    flags=re.MULTILINE,
)
_SPEAKER_LABEL_RE = re.compile(r"Speaker\s+(\d+)", re.IGNORECASE)


def seconds_to_timecode(s: float) -> str:
    """Render seconds as `HH:MM:SS` (or `MM:SS` when hours are zero) — the form the
    transcript headers use, so segment addresses read consistently with the source."""
    total = int(s)
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h > 0 else f"{m:02d}:{sec:02d}"


def speaker_label_to_index(label: str) -> int | None:
    """`Speaker 2` → 2; None for unlabeled segments."""
    if not label:
        return None
    m = _SPEAKER_LABEL_RE.search(label)
    return int(m.group(1)) if m else None


def parse_transcript_sections(
    transcript: str,
    *,
    audio_stream_id: str,
    video_stream_id: str | None,
    multi_audio: bool,
    multi_video: bool,
    media_duration: float | None = None,
) -> list[Segment]:
    """A flat list of segments grouped by speaker run — the DEFAULT grouping, used when a
    video ships no chapter markers (chaptered videos go through
    `parse_chaptered_sections`). One `text/transcript` Segment per checkpoint (utterance
    body, speaker on `extra`); a speaker run carries no label the source ever stated (a
    speaker change is a machine inference, not a byte-fact) and so contributes no
    structural mark — just its transcript (and, for video, frame) segments, in reading
    order. When `video_stream_id` is set (video drafter) each run LEADS with a body-empty
    `image` keyframe marker at its start and the final run closes with one at the video's
    last frame; audio passes None and gets transcript-only segments. Interior boundary
    instants are shared between adjacent runs, so each `frame=<t>` address is placed at
    most once (§4.3.2.2).

    `media_duration` (the probed clip length, seconds) bounds the final run's end so a
    short continuous-speech clip that whisper returns as a single segment at start=0
    spans `00:00-<duration>` rather than collapsing to a zero-length `00:00-00:00`.

    A speaker change is a grouping boundary at draft time, internal to how addresses are
    computed; the normalizer later reads the transcript and asserts topic-grain sections.
    """
    checkpoints = _parse_checkpoints(transcript)
    if not checkpoints:
        return []
    return _emit_sections(
        _speaker_run_groups(checkpoints, media_duration),
        drop_empty=True,
        audio_stream_id=audio_stream_id,
        video_stream_id=video_stream_id,
        multi_audio=multi_audio,
        multi_video=multi_video,
    )


def parse_chaptered_sections(
    transcript: str,
    chapters: list[dict[str, Any]],
    *,
    audio_stream_id: str,
    video_stream_id: str | None,
    multi_audio: bool,
    multi_video: bool,
    media_duration: float | None = None,
) -> list[Segment]:
    """A flat list of segments grouped by video chapter — the uploader's own outline
    (yt-dlp `chapters[]`), used in preference to speaker runs when a video ships chapter
    markers. Each chapter's title is a source-declared byte-fact, so its start gets a
    leading STRUCTURAL byte-mark carrying that title verbatim (§4.3.2.3) — never a
    Section's `entry` — followed by the transcript checkpoints that fall within it (each
    verbatim, its own speaker on `extra`, since one chapter can span several speakers).
    Frame markers follow the same lead-each-group / close-the-last rule as the speaker-run
    path. Chapters are kept even when they contain no speech (a chapter is a structural
    unit): the mark is emitted regardless, and for video it still carries its lead
    keyframe.
    """
    checkpoints = _parse_checkpoints(transcript)
    return _emit_sections(
        _chapter_groups(checkpoints, chapters, media_duration),
        drop_empty=False,
        audio_stream_id=audio_stream_id,
        video_stream_id=video_stream_id,
        multi_audio=multi_audio,
        multi_video=multi_video,
    )


# A grouping "group" feeding `_emit_sections` — internal only, never stored as a Section:
#   (label|None, begin_seconds, end_seconds, [(start_seconds, text, speaker_idx|None), …]).
# `label` is a source-declared byte-fact (a chapter title) or None (a speaker run, which
# the source never labeled) — it becomes a structural mark's body, never a Section's entry.
_Group = tuple[str | None, float, float, list[tuple[float, str, int | None]]]


def _parse_checkpoints(transcript: str) -> list[tuple[float, str, str]]:
    """Flat `[(start_seconds, speaker_label, text), …]` from the diarized transcript's
    `[Speaker N] (HH:MM:SS)` headers, in reading order; empty-body checkpoints dropped.
    Shared by the speaker-run and chapter sectioning paths."""
    headers: list[tuple[str, float, int]] = []
    for m in _SEGMENT_HEADER_RE.finditer(transcript):
        h, mm, s = (int(p) for p in m.group("timestamp").split(":"))
        headers.append((m.group("speaker"), float(h * 3600 + mm * 60 + s), m.end()))

    # Per-header text body slice. Guard `find`/`rfind` against -1 (a bracketed token in
    # the body, or a single-line body) — Python would otherwise read -1 as a from-end idx.
    checkpoints: list[tuple[float, str, str]] = []
    for idx, (speaker, start, body_start) in enumerate(headers):
        if idx + 1 < len(headers):
            next_pos = transcript.find(f"[{headers[idx + 1][0]}]", body_start)
            if next_pos == -1:
                next_pos = len(transcript)
            body_end = transcript.rfind("\n", body_start, next_pos)
            if body_end == -1:
                body_end = next_pos
            text = transcript[body_start:body_end].strip()
        else:
            text = transcript[body_start:].strip()
        if text:
            checkpoints.append((start, speaker, text))
    return checkpoints


def _final_end(last_cp: float, media_duration: float | None) -> float:
    """End bound for the LAST section/checkpoint. Prefer the probed media duration (the
    true clip length) when it runs past the final transcript checkpoint — a short
    continuous-speech clip can come back from whisper as a single segment at start=0,
    which would otherwise collapse to a zero-length `00:00-00:00` range. Falls back to
    `last_cp + 0.001` when no duration is known or the checkpoint already runs past it."""
    if media_duration is not None and media_duration > last_cp:
        return media_duration
    return last_cp + 0.001


def _speaker_run_groups(
    checkpoints: list[tuple[float, str, str]], media_duration: float | None = None
) -> list[_Group]:
    """Group consecutive same-speaker checkpoints into runs (label=None — a speaker run
    carries no source-stated label, so it gets no structural mark). A run ends where the
    next run begins; the last ends at the probed media duration (or just past the final
    checkpoint when unknown)."""
    groups: list[_Group] = []
    i, n = 0, len(checkpoints)
    while i < n:
        speaker = checkpoints[i][1]
        j = i
        while j < n and checkpoints[j][1] == speaker:
            j += 1
        begin = checkpoints[i][0]
        end = checkpoints[j][0] if j < n else _final_end(checkpoints[-1][0], media_duration)
        speaker_idx = speaker_label_to_index(speaker)
        members = [(cp[0], cp[2], speaker_idx) for cp in checkpoints[i:j]]
        groups.append((None, begin, end, members))
        i = j
    return groups


def _chapter_groups(
    checkpoints: list[tuple[float, str, str]],
    chapters: list[dict[str, Any]],
    media_duration: float | None = None,
) -> list[_Group]:
    """One group per chapter (label=the chapter's own title, a byte-fact), tiling the
    timeline contiguously:
    a chapter runs to the next chapter's start, and the last to the probed media duration
    (or just past the final checkpoint when unknown — kept in-range, like the speaker-run
    path, rather than at a declared `end_time` that can round past the real duration).
    Each checkpoint joins the chapter containing its start; any checkpoint before the
    first chapter folds into it."""
    ordered = sorted(chapters, key=lambda c: c.get("start") or 0.0)
    n = len(ordered)
    last_cp = checkpoints[-1][0] if checkpoints else 0.0
    groups: list[_Group] = []
    for i, ch in enumerate(ordered):
        begin = float(ch.get("start") or 0.0)
        end = (
            float(ordered[i + 1].get("start") or begin)
            if i + 1 < n
            else _final_end(last_cp, media_duration)
        )
        if end <= begin:  # degenerate (e.g. a final chapter past the last speech)
            end = begin + 0.001
        lo = float("-inf") if i == 0 else begin
        members = [
            (cp[0], cp[2], speaker_label_to_index(cp[1]))
            for cp in checkpoints
            if lo <= cp[0] < end
        ]
        groups.append((str(ch.get("title") or "") or None, begin, end, members))
    return groups


def _emit_sections(
    groups: list[_Group],
    *,
    drop_empty: bool,
    audio_stream_id: str,
    video_stream_id: str | None,
    multi_audio: bool,
    multi_video: bool,
) -> list[Segment]:
    """Render grouping groups → a FLAT list of `Segment`s (spec §4.3.2.1/§7.8: no Section
    is asserted here — grouping is internal bookkeeping, not a stored span, §153). A group
    with a `label` (only the chapter path ever sets one — a byte-fact, the uploader's own
    title) gets a leading STRUCTURAL byte-mark at its start instant, carrying that label
    verbatim (§4.3.2.3); a speaker run (`label=None`) gets no mark at all. Every group
    additionally shares the frame-marker rule: each LEADS with an `image` keyframe at its
    start, the final group closes with one at its end, and a `frame=<t>` address is
    emitted at most once (boundary instants are shared between adjacent groups —
    `(opener-id, address)` identity, §4.3.2.2). `drop_empty` skips groups with no
    checkpoints (speaker runs) — chapters keep them (a chapter is a structural unit; its
    mark is emitted regardless of whether it has any speech)."""
    emitted = [g for g in groups if g[3]] if drop_empty else groups
    seen_frames: set[str] = set()
    # Record-global ledger of every `text/transcript` address emitted so far, mapped to its
    # Segment, so a zero-width collision is folded even across a group boundary (a
    # speaker-run flip at the same rounded instant lands the two segments in adjacent
    # groups — within-group dedup alone wouldn't catch that).
    seen_transcripts: dict[str, Segment] = {}
    out: list[Segment] = []
    for idx, (label, begin, end, members) in enumerate(emitted):
        segs: list[Segment] = []
        # Each group LEADS with the keyframe at its start. The boundary instant is owned
        # by the group that opens there; the prior group's end equals it and is not
        # re-emitted as a trailing marker (that was the duplicate-address bug).
        if video_stream_id:
            _append_frame(segs, seen_frames, begin, video_stream_id, multi_video)
        for i, (cp_start, cp_text, cp_speaker) in enumerate(members):
            cp_end = members[i + 1][0] if i + 1 < len(members) else end
            addr = f"time_range={seconds_to_timecode(cp_start)}-{seconds_to_timecode(cp_end)}"
            if multi_audio:
                addr += f"&stream_id={audio_stream_id}"
            extra: dict[str, Any] = {}
            if cp_speaker is not None:
                extra["speaker"] = cp_speaker
            # Merge-on-collision (§4.3.2.2 — `(opener-id, address)` is segment identity).
            # Whisper occasionally returns consecutive segments whose start and end both
            # round to the SAME whole second (zero-width, `S-S`); two of those round to an
            # identical `time_range=` address and would claim one identity, failing lint.
            # Fold the colliding checkpoint into the segment that already owns the address —
            # concatenate the verbatim text (the body stays a lossless rendering of the
            # shared time-range; earliest start / latest end are already encoded by the
            # shared `S-S` value). 3+ in a row fold one-by-one into the running segment.
            # When the two carry different speakers (a diarization flip at one instant) the
            # merged span genuinely covers more than one speaker, so its `speaker` is
            # dropped — mirroring a multi-speaker chapter group, which carries no single
            # speaker either.
            prior = seen_transcripts.get(addr)
            if prior is not None:
                prior.body = f"{prior.body} {cp_text}".strip() if cp_text else prior.body
                if prior.extra.get("speaker") != extra.get("speaker"):
                    prior.extra.pop("speaker", None)
                continue
            seg = Segment(
                atom="text",
                overlay="text/transcript",
                address=addr,
                body=cp_text,
                extra=extra,
            )
            seen_transcripts[addr] = seg
            segs.append(seg)
        # Only the final group closes with a trailing frame; every interior group's end
        # coincides with the next group's leading frame, so emitting it would duplicate
        # that address.
        if video_stream_id and idx == len(emitted) - 1 and end > begin:
            _append_frame(segs, seen_frames, end, video_stream_id, multi_video)

        # `drop_empty` (speaker-run path) skips groups with no checkpoints up front; a
        # cross-group zero-width collision can ALSO empty a group after the fact (its lone
        # checkpoint folded into the prior group, and its lead frame was the shared
        # boundary instant already placed). Drop such a now-empty group so it leaves no
        # phantom marker at a duplicate address. Chapter groups (`drop_empty=False`) are
        # kept — a chapter is a structural unit either way, and (unlike a dropped speaker
        # run) it still gets its mark below even with zero segments.
        if drop_empty and not segs:
            continue
        if label:
            out.append(
                Segment(
                    atom=_STRUCTURAL_ATOM,
                    address=f"time={seconds_to_timecode(begin)}",
                    level=1,
                    body=label,
                )
            )
        out.extend(segs)
    return out


def _append_frame(
    segs: list[Segment],
    seen: set[str],
    t: float,
    video_stream_id: str,
    multi_video: bool,
) -> None:
    """Append a body-empty `image` frame marker at `frame=<t>`, skipping addresses
    already placed — a frame instant shared by adjacent speaker runs may appear at most
    once (`(opener-id, address)` identity, §4.3.2.2)."""
    seg = _frame_segment(t, video_stream_id, multi_video)
    if seg.address in seen:
        return
    seen.add(seg.address)
    segs.append(seg)


def _frame_segment(t: float, video_stream_id: str, multi_video: bool) -> Segment:
    """Body-empty image positioning marker at `frame=<t>` (spec §4.3.2.2)."""
    addr = f"frame={seconds_to_timecode(t)}"
    if multi_video:
        addr += f"&stream_id={video_stream_id}"
    return Segment(atom="image", address=addr, body="")
