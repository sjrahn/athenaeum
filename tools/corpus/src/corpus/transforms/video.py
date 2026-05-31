"""Video transformations: extract_audio, frame.

Both shell out to `ffmpeg` (and assume `ffmpeg` / `ffprobe` are on PATH — a system
dependency, not a Python one). The video working value is a `pathlib.Path` to the
source artifact, not an in-memory object: ffmpeg streams from disk and writes to a
temporary path that the next pipeline stage consumes (or the resolver writes through
to cache).
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from . import RenderContext, register

log = logging.getLogger(__name__)


@register("video", "extract_audio", "audio")
def extract_audio(video_path: Path, value: str | None, ctx: RenderContext) -> Path:
    """Extract mono 16 kHz 64 kbps MP3 — suitable input for speech-to-text.

    Flag-style (no value). Returns a `Path` to a temp file the next transform owns;
    if it's the final output, the resolver moves it to cache.
    """
    if value is not None:
        raise ValueError(f"extract_audio is flag-style and takes no value, got {value!r}")
    out = Path(tempfile.mkstemp(suffix=".mp3", prefix="corpus-audio-")[1])
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-codec:a", "libmp3lame", "-b:a", "64k",
        str(out),
    ]
    log.info("ffmpeg extract_audio: %s -> %s", video_path.name, out)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg extract_audio failed: {proc.stderr.strip()}")
    return out


@register("video", "frame", "image")
def frame(video_path: Path, value: str | None, ctx: RenderContext) -> Image.Image:
    """Grab a single frame at `frame=<seconds-or-timecode>`.

    Accepts integer/float seconds (`frame=120`, `frame=12.5`) or HH:MM:SS / MM:SS
    (`frame=02:00`, `frame=01:30:45`) — all valid `-ss` arguments. Returns a PIL
    Image so it composes with the image transforms (resize, crop, …).

    When the source record carries a duration (the resolver plumbs it through `ctx`
    as `video_duration_seconds`), the timecode is range-checked before ffmpeg runs.
    """
    if value is None or not value.strip():
        raise ValueError("frame= requires a value (seconds or HH:MM:SS)")
    timecode = value.strip()

    seconds = _parse_timecode_to_seconds(timecode)
    if seconds < 0:
        raise ValueError(f"frame= must be non-negative, got {seconds}")
    duration = ctx.get("video_duration_seconds")
    if duration is not None and seconds >= duration:
        raise ValueError(
            f"frame={timecode!r} ({seconds:.2f}s) is past the end of the video "
            f"(duration {duration:.2f}s)"
        )

    out = Path(tempfile.mkstemp(suffix=".png", prefix="corpus-frame-")[1])
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", timecode,
        "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2",
        str(out),
    ]
    log.info("ffmpeg frame: %s @ %s -> %s", video_path.name, timecode, out)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg frame failed: {proc.stderr.strip()}")
    if not out.is_file() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg frame produced no output (timecode {timecode!r} past end?)")

    with Image.open(out) as im:
        im.load()
        result = im.copy()
    out.unlink(missing_ok=True)
    return result


def _parse_timecode_to_seconds(value: str) -> float:
    """Parse 'NNN', 'NNN.N', 'MM:SS', or 'HH:MM:SS' (optional fractional seconds)."""
    parts = value.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    raise ValueError(f"frame= must be seconds or HH:MM:SS / MM:SS, got {value!r}")
