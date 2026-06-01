"""Shared transcript → sections splitter for the audio and video drafters.

Both drafters consume a `[Speaker N] (HH:MM:SS)` diarized transcript (produced by the
configured `TranscriptionAdapter`) and turn it into one `Section` per speaker run, each
holding one `text/transcript` `Segment` per checkpoint addressed by time-range. The video
drafter additionally bookends each run with body-empty `image` frame markers; the audio
drafter passes `video_stream_id=None` and gets transcript-only sections.
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
) -> list[Section]:
    """One Section per speaker run. Each holds one `text/transcript` Segment per
    checkpoint (utterance body, speaker on `extra`), optionally bookended by body-empty
    `image` framegrab markers when `video_stream_id` is set (video drafter); audio passes
    None and gets transcript-only sections.

    A speaker change is a section boundary at draft time; the normalizer later merges
    across speaker boundaries into topic-grain sections.
    """
    headers: list[tuple[str, float, int]] = []
    for m in _SEGMENT_HEADER_RE.finditer(transcript):
        ts = m.group("timestamp")
        h, mm, s = (int(p) for p in ts.split(":"))
        headers.append((m.group("speaker"), float(h * 3600 + mm * 60 + s), m.end()))
    if not headers:
        return []

    # Per-header text body slice. Guard the `find`/`rfind` results: a transcript whose
    # body text contains a bracketed token, or a single-line body, can make `find`/`rfind`
    # return -1 — which Python would otherwise reinterpret as a from-end index.
    texts: list[str] = []
    for idx, (_speaker, _start, body_start) in enumerate(headers):
        if idx + 1 < len(headers):
            next_pos = transcript.find(f"[{headers[idx + 1][0]}]", body_start)
            if next_pos == -1:
                next_pos = len(transcript)
            body_end = transcript.rfind("\n", body_start, next_pos)
            if body_end == -1:
                body_end = next_pos
            texts.append(transcript[body_start:body_end].strip())
        else:
            texts.append(transcript[body_start:].strip())

    # Group consecutive headers by speaker into runs.
    runs: list[tuple[str, float, float, list[tuple[float, str]]]] = []
    run_start = 0
    for i in range(1, len(headers) + 1):
        if i < len(headers) and headers[i][0] == headers[run_start][0]:
            continue
        speaker = headers[run_start][0]
        start = headers[run_start][1]
        end = headers[i][1] if i < len(headers) else headers[-1][1] + 0.001
        checkpoints = [(headers[j][1], texts[j]) for j in range(run_start, i) if texts[j]]
        runs.append((speaker, start, end, checkpoints))
        run_start = i

    sections: list[Section] = []
    for speaker, run_begin, run_end, checkpoints in runs:
        if not checkpoints:
            continue
        speaker_idx = speaker_label_to_index(speaker)
        section_address = (
            f"time_range={seconds_to_timecode(run_begin)}-{seconds_to_timecode(run_end)}"
        )
        if multi_audio:
            section_address += f"&stream_id={audio_stream_id}"

        segs: list[Segment] = []
        if video_stream_id:
            segs.append(_frame_segment(run_begin, video_stream_id, multi_video))
        for i, (cp_start, cp_text) in enumerate(checkpoints):
            cp_end = checkpoints[i + 1][0] if i + 1 < len(checkpoints) else run_end
            addr = f"time_range={seconds_to_timecode(cp_start)}-{seconds_to_timecode(cp_end)}"
            if multi_audio:
                addr += f"&stream_id={audio_stream_id}"
            extra: dict[str, Any] = {}
            if speaker_idx is not None:
                extra["speaker"] = speaker_idx
            segs.append(
                Segment(
                    atom="text",
                    overlay="text/transcript",
                    address=addr,
                    body=cp_text,
                    extra=extra,
                )
            )
        if video_stream_id and run_end > run_begin:
            segs.append(_frame_segment(run_end, video_stream_id, multi_video))

        sections.append(Section(address=section_address, entry=None, segments=segs))
    return sections


def _frame_segment(t: float, video_stream_id: str, multi_video: bool) -> Segment:
    """Body-empty image positioning marker at `frame=<t>` (spec §4.3.2.2)."""
    addr = f"frame={seconds_to_timecode(t)}"
    if multi_video:
        addr += f"&stream_id={video_stream_id}"
    return Segment(atom="image", address=addr, body="")
