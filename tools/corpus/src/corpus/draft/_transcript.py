"""Shared transcript → sections splitter for the audio and video drafters.

Both drafters consume a `[Speaker N] (HH:MM:SS)` diarized transcript (produced by the
configured `TranscriptionAdapter`) and turn it into `Section`s, each holding one
`text/transcript` `Segment` per checkpoint addressed by time-range. The default sectioning
is one `Section` per speaker run (`parse_transcript_sections`); a video that ships chapter
markers is instead sectioned by its chapters (`parse_chaptered_sections`), the chapter
title riding as each section's `entry` TOC label (§4.3.2.2). The video drafter additionally
leads each section with a body-empty `image` keyframe marker (and the last section closes
with the video's final frame); the audio drafter passes `video_stream_id=None` and gets
transcript-only sections. A boundary instant is shared by adjacent sections, so each
`frame=<t>` address is emitted at most once (§4.3.2.2).
"""

from __future__ import annotations

import re
from typing import Any

from corpus.segments import Section, Segment

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
) -> list[Section]:
    """One Section per speaker run — the DEFAULT sectioning, used when a video ships no
    chapter markers (chaptered videos go through `parse_chaptered_sections`). Each holds
    one `text/transcript` Segment per checkpoint (utterance body, speaker on `extra`) and
    carries no `entry` (the normalizer writes a TOC label later). When `video_stream_id`
    is set (video drafter) each section LEADS with a body-empty `image` keyframe marker at
    its start and the final section closes with one at the video's last frame; audio
    passes None and gets transcript-only sections. Interior boundary instants are shared
    between adjacent runs, so each `frame=<t>` address is placed at most once (§4.3.2.2).

    `media_duration` (the probed clip length, seconds) bounds the final run's end so a
    short continuous-speech clip that whisper returns as a single segment at start=0
    spans `00:00-<duration>` rather than collapsing to a zero-length `00:00-00:00`.

    A speaker change is a section boundary at draft time; the normalizer later merges
    across speaker boundaries into topic-grain sections.
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
) -> list[Section]:
    """One Section per video chapter — the uploader's outline (yt-dlp `chapters[]`), used
    in preference to speaker runs when a video ships chapter markers. The chapter title
    becomes the section `entry` (the §4.3.2.2 TOC label — section-block metadata
    structure, NOT body content); the section spans the chapter's time-range and holds the
    transcript checkpoints that fall within it (each verbatim, its own speaker on `extra`,
    since one chapter can span several speakers). Frame markers follow the same
    lead-each-section / close-the-last rule as the speaker-run path. Chapters are kept even
    when they contain no speech (a chapter is a structural unit); for video they still
    carry their lead keyframe.
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


# A section "group" feeding `_emit_sections`:
#   (entry|None, begin_seconds, end_seconds, [(start_seconds, text, speaker_idx|None), …]).
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
    """Group consecutive same-speaker checkpoints into runs (entry=None — speaker-run
    sectioning carries no TOC label). A run ends where the next run begins; the last ends
    at the probed media duration (or just past the final checkpoint when unknown)."""
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
    """One group per chapter (entry=the chapter title), tiling the timeline contiguously:
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
) -> list[Section]:
    """Render section groups → `Section`s with the shared frame-marker rule: each section
    LEADS with an `image` keyframe at its start, the final section closes with one at its
    end, and a `frame=<t>` address is emitted at most once (boundary instants are shared
    between adjacent sections — `(opener-id, address)` identity, §4.3.2.2). `drop_empty`
    skips groups with no checkpoints (speaker runs) — chapters keep them (a chapter is a
    structural unit)."""
    emitted = [g for g in groups if g[3]] if drop_empty else groups
    seen_frames: set[str] = set()
    sections: list[Section] = []
    for idx, (entry, begin, end, members) in enumerate(emitted):
        section_address = (
            f"time_range={seconds_to_timecode(begin)}-{seconds_to_timecode(end)}"
        )
        if multi_audio:
            section_address += f"&stream_id={audio_stream_id}"

        segs: list[Segment] = []
        # Each section LEADS with the keyframe at its start. The boundary instant is owned
        # by the section that opens there; the prior section's end equals it and is not
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
            segs.append(
                Segment(
                    atom="text",
                    overlay="text/transcript",
                    address=addr,
                    body=cp_text,
                    extra=extra,
                )
            )
        # Only the final section closes with a trailing frame; every interior section's
        # end coincides with the next section's leading frame, so emitting it would
        # duplicate that address.
        if video_stream_id and idx == len(emitted) - 1 and end > begin:
            _append_frame(segs, seen_frames, end, video_stream_id, multi_video)

        sections.append(Section(address=section_address, entry=entry, segments=segs))
    return sections


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
