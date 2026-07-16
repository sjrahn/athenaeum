"""Video transformations: extract_audio, frame, and the muxing contract (§6.2) —
`time_range=`, `cut=`, `format=`, `scenes=`.

All shell out to `ffmpeg` / `ffprobe` (assumed on PATH — a system dependency, not a
Python one). The video/audio working value is a `pathlib.Path` to the source artifact
(or, mid-chain, a Path to a temp file a prior op produced), not an in-memory object:
ffmpeg streams from disk and writes to a temporary path the next pipeline stage
consumes (or the resolver writes through to cache).

The muxing contract's ops (`time_range=`, `format=`, `scenes=`) are **version-labeled**
(§6.3/§6.4) — `ffmpeg_engine_label()` gives the resolver a stable `ffmpeg@<version>` id
to fold into the cache key exactly as the `transcribe` op folds in its adapter's
`engine`.
"""

from __future__ import annotations

import functools
import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
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


# ---------- engine versioning (§6.3/§6.4) ---------- #


@functools.lru_cache(maxsize=1)
def ffmpeg_engine_label() -> str:
    """Stable engine id for the muxing contract's version-labeled ops (`time_range=`,
    `format=`, `scenes=`) — encoder/detector output drifts across ffmpeg versions, so the
    resolver folds this into the op's cache key exactly as `transcribe` folds in its
    adapter's `engine` (§6.3/§6.4). Cached per process (one `ffmpeg -version` shell-out);
    tests that need a fresh read should call `ffmpeg_engine_label.cache_clear()` first.
    """
    version = "unknown"
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, check=False
        )
        first_line = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
        m = re.search(r"ffmpeg version (\S+)", first_line)
        if m:
            version = m.group(1)
    except OSError:
        pass
    return f"ffmpeg@{version}"


def _run_ffmpeg(cmd: list[str], op: str) -> None:
    log.info("ffmpeg %s: %s", op, " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        Path(cmd[-1]).unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg {op} failed: {proc.stderr.strip()}")


# ---------- stream selection (§6.2 `stream_id=`, composed via ffmpeg `-map`) ---------- #
#
# This is the ENGINE path only — playable renderings, ffmpeg-produced (§12.20 item 1).
# It does not import `corpus.streams` (the byte-identity/pinned-extraction path a track
# manifest promotes through): the two paths stand alone by design.


def _probe_stream_kinds(path: Path) -> dict[str, list[int]]:
    """ffprobe stream indices grouped by `codec_type` ('video'/'audio'/'subtitle'/…)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=index,codec_type",
        "-of", "json", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe returned unparseable output: {exc}") from exc
    by_kind: dict[str, list[int]] = {}
    for s in data.get("streams", []):
        by_kind.setdefault(s.get("codec_type", "?"), []).append(s["index"])
    return by_kind


def _default_stream_map_args(path: Path) -> list[str]:
    """Default-member resolution (§6.2 "the muxing contract"): map the container's unique
    video stream and unique audio stream. A kind with zero members is omitted (absence is
    not ambiguity — a silent video cuts video-only). More than one candidate in a present
    kind is a hard error, never guessed — no track-manifest "declared primary" exists at
    this layer yet (§12.20 item 2 is the byte-identity path's job), so >1 is always
    ambiguous here. Subtitle tracks never ride implicitly."""
    by_kind = _probe_stream_kinds(path)
    args: list[str] = []
    for kind, flag in (("video", "v"), ("audio", "a")):
        idxs = by_kind.get(kind, [])
        if len(idxs) > 1:
            raise ValueError(
                f"ambiguous {kind} streams ({len(idxs)}) with no declared primary — "
                f"pass stream_id= to disambiguate"
            )
        if idxs:
            args += ["-map", f"0:{flag}:0"]
    return args


def _stream_map_args(path: Path, ctx: RenderContext) -> list[str]:
    """Stream selection (§6.2 `stream_id=`), applied only at the first ffmpeg-touching step
    of the chain — an intermediate a prior op already produced already carries just the
    wanted streams, so re-mapping there would be a no-op at best and wrong at worst.
    Explicit `stream_id=<id>[,<id>…]` maps exactly those streams (the repeated-`-map`
    analogue, §6.2); otherwise the default per-kind composition applies."""
    artifact_path = ctx.get("artifact_path")
    if artifact_path is None or Path(path) != Path(artifact_path):
        return []
    stream_ids = ctx.get("stream_ids")
    if stream_ids:
        args: list[str] = []
        for sid in stream_ids:
            args += ["-map", f"0:{sid}"]
        return args
    return _default_stream_map_args(path)


def _scene_stream_map_args(path: Path, ctx: RenderContext) -> list[str]:
    """Stream selection for `scenes=` — video-only (scene detection has no audio input)."""
    artifact_path = ctx.get("artifact_path")
    if artifact_path is None or Path(path) != Path(artifact_path):
        return []
    stream_ids = ctx.get("stream_ids")
    if stream_ids:
        if len(stream_ids) != 1:
            raise ValueError("scenes= operates on a single video stream — pass one stream_id=")
        return ["-map", f"0:{stream_ids[0]}"]
    by_kind = _probe_stream_kinds(path)
    idxs = by_kind.get("video", [])
    if len(idxs) > 1:
        raise ValueError(
            f"ambiguous video streams ({len(idxs)}) — pass stream_id= to disambiguate"
        )
    if not idxs:
        raise ValueError("scenes= requires a video stream")
    return []  # the sole video stream is ffmpeg's implicit filter input


# ---------- `time_range=` / `cut=` (§6.2 "the muxing contract") ---------- #


def _parse_time_ranges(value: str) -> list[tuple[float, float]]:
    """Parse `<s>-<e>[,<s>-<e>…]` (§6.2) into an ordered list of (start, end) seconds —
    the address grammar's ordered-list-for-non-contiguous-spans convention (§12.11)."""
    ranges: list[tuple[float, float]] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if "-" not in chunk:
            raise ValueError(f"time_range= expects <start>-<end>, got {chunk!r}")
        start_s, end_s = chunk.split("-", 1)
        start = _parse_timecode_to_seconds(start_s.strip())
        end = _parse_timecode_to_seconds(end_s.strip())
        if end < start:
            raise ValueError(f"time_range={chunk!r}: end precedes start")
        ranges.append((start, end))
    if not ranges:
        raise ValueError("time_range= requires at least one <start>-<end> span")
    return ranges


def _cut_one(
    path: Path, rng: tuple[float, float], cut_mode: str, map_args: list[str], ext: str
) -> Path:
    start, end = rng
    duration = max(end - start, 0.001)
    out = Path(tempfile.mkstemp(suffix=f".{ext}", prefix="corpus-cut-")[1])
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", str(path), "-t", f"{duration:.3f}",
        *map_args,
    ]
    if cut_mode == "copy":
        cmd += ["-c", "copy"]
    elif cut_mode != "precise":
        raise ValueError(f"cut= must be 'precise' or 'copy', got {cut_mode!r}")
    # precise (default): no explicit codec pin — ffmpeg re-encodes to the target
    # extension's default codec. `-ss` before `-i` combined with re-encoding is
    # frame-accurate (ffmpeg decodes forward from the nearest keyframe to the exact
    # timestamp); `-c copy` can only snap to keyframe boundaries — the disclosed
    # fast path (§6.2).
    cmd.append(str(out))
    _run_ffmpeg(cmd, "time_range")
    return out


def _concat(parts: list[Path], ext: str) -> Path:
    """Concatenate same-codec cut parts — "concatenation is safe by construction" (§6.2):
    every cut shares the source's codec parameters, so the ffmpeg concat demuxer stream-
    copies them with no re-encode."""
    out = Path(tempfile.mkstemp(suffix=f".{ext}", prefix="corpus-concat-")[1])
    list_file = Path(tempfile.mkstemp(suffix=".txt", prefix="corpus-concat-list-")[1])
    try:
        list_file.write_text(
            "".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out),
        ]
        _run_ffmpeg(cmd, "time_range (concat)")
    finally:
        list_file.unlink(missing_ok=True)
    return out


def _cut(path: Path, value: str | None, ctx: RenderContext) -> Path:
    if not value or not value.strip():
        raise ValueError("time_range= requires a value (e.g. time_range=12:04-12:09)")
    ranges = _parse_time_ranges(value)
    cut_mode = ctx.get("cut_mode") or "precise"
    map_args = _stream_map_args(path, ctx)
    ext = Path(path).suffix.lstrip(".") or "mp4"

    if len(ranges) == 1:
        return _cut_one(path, ranges[0], cut_mode, map_args, ext)

    parts = [_cut_one(path, r, cut_mode, map_args, ext) for r in ranges]
    try:
        return _concat(parts, ext)
    finally:
        for p in parts:
            p.unlink(missing_ok=True)


@register("video", "time_range", "video")
def time_range_video(path: Path, value: str | None, ctx: RenderContext) -> Path:
    """A cut of the composition (§6.2 "the muxing contract"): default-member resolution
    applied per kind, muxed into the source's container family (bare — same extension as
    the source, matched via the working value's own suffix)."""
    return _cut(path, value, ctx)


@register("audio", "time_range", "audio")
def time_range_audio(path: Path, value: str | None, ctx: RenderContext) -> Path:
    """Same cut semantics as `time_range_video`, for an audio-only container (a silent
    video's composition cuts video-only; an audio-only container cuts audio-only, §6.2)."""
    return _cut(path, value, ctx)


# ---------- `format=` (§6.2 "the muxing contract" — output-format conversion) ---------- #


@dataclass(frozen=True)
class _FormatTarget:
    ext: str
    mime: str
    video_ok: bool
    audio_ok: bool
    video_args: tuple[str, ...] = ()
    audio_args: tuple[str, ...] = ()


#: Implementation-defined token set (the `fit=` precedent, §6.2) — at least the tokens the
#: increment calls for. `png` is deliberately absent here: it's a frame-context target (a
#: single already-selected image), already served by the existing `frame=` → image pipeline
#: rather than a video/audio muxing-contract conversion.
_FORMAT_TARGETS: dict[str, _FormatTarget] = {
    "mp4": _FormatTarget(
        ext="mp4", mime="video/mp4", video_ok=True, audio_ok=True,
        video_args=("-c:v", "libx264", "-pix_fmt", "yuv420p"), audio_args=("-c:a", "aac"),
    ),
    "webm": _FormatTarget(
        ext="webm", mime="video/webm", video_ok=True, audio_ok=True,
        video_args=("-c:v", "libvpx-vp9"), audio_args=("-c:a", "libopus"),
    ),
    "gif": _FormatTarget(ext="gif", mime="image/gif", video_ok=True, audio_ok=False),
    "m4a": _FormatTarget(
        ext="m4a", mime="audio/mp4", video_ok=False, audio_ok=True, audio_args=("-c:a", "aac"),
    ),
    "ogg": _FormatTarget(
        ext="ogg", mime="audio/ogg", video_ok=False, audio_ok=True,
        audio_args=("-c:a", "libvorbis"),
    ),
    "wav": _FormatTarget(
        ext="wav", mime="audio/x-wav", video_ok=False, audio_ok=True,
        audio_args=("-c:a", "pcm_s16le"),
    ),
}


def _convert_format(
    path: Path, value: str | None, ctx: RenderContext, *, source_kind: str
) -> Path:
    if not value or not value.strip():
        raise ValueError("format= requires a value (e.g. format=mp4)")
    token = value.strip().lower()
    spec = _FORMAT_TARGETS.get(token)
    if spec is None:
        raise ValueError(
            f"format={token!r} not supported "
            f"(supported: {', '.join(sorted(_FORMAT_TARGETS))})"
        )
    if source_kind == "audio" and not spec.audio_ok:
        raise ValueError(
            f"format={token!r}: no audio-compatible target for an audio source "
            f"(atom-incompatible, §6.2 muxing contract)"
        )

    map_args = _stream_map_args(path, ctx)
    out = Path(tempfile.mkstemp(suffix=f".{spec.ext}", prefix="corpus-format-")[1])
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), *map_args]
    if spec.video_ok and source_kind == "video":
        cmd += list(spec.video_args)
    else:
        cmd += ["-vn"]  # the target/source carries no video — dropped by the format's nature
    if spec.audio_ok:
        cmd += list(spec.audio_args)
    else:
        cmd += ["-an"]  # gif: audio dropped by the format's nature, not editorial choice
    cmd.append(str(out))
    _run_ffmpeg(cmd, f"format={token}")
    return out


@register("video", "format", "media")
def format_video(path: Path, value: str | None, ctx: RenderContext) -> Path:
    """Output-format conversion, composing after selection and cutting (§6.2): changes
    encoding only, never the addressed content."""
    return _convert_format(path, value, ctx, source_kind="video")


@register("audio", "format", "media")
def format_audio(path: Path, value: str | None, ctx: RenderContext) -> Path:
    return _convert_format(path, value, ctx, source_kind="audio")


# ---------- `scenes=` (§6.2, §12.20 item 5 — normalizer support) ---------- #

_PTS_TIME_RE = re.compile(r"pts_time:(\d+(?:\.\d+)?)")


def _parse_showinfo_timestamps(stderr_text: str) -> list[float]:
    return [float(m.group(1)) for m in _PTS_TIME_RE.finditer(stderr_text)]


@register("video", "scenes", "text")
def scenes(path: Path, value: str | None, ctx: RenderContext) -> str:
    """Scene-cut boundary proposals over the video timeline (§6.2) — a pinned ffmpeg
    scene-detection derivation, engine-versioned like `transcribe`. Normalizer support for
    boundary work (`form/slide-deck`, §12.20 item 5): proposals to be verified against
    rendered stills (`frame=`), never stored marks. Yields one timestamp per line, seconds
    with millisecond precision.
    """
    if not value or not value.strip():
        raise ValueError("scenes= requires a threshold value (e.g. scenes=0.4)")
    try:
        threshold = float(value.strip())
    except ValueError as exc:
        raise ValueError(f"scenes= threshold must be a float, got {value!r}") from exc
    if not 0.0 < threshold < 1.0:
        raise ValueError(f"scenes= threshold must be in (0.0, 1.0), got {threshold}")

    map_args = _scene_stream_map_args(path, ctx)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "info",
        "-i", str(path), *map_args,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    log.info("ffmpeg scenes: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg scenes failed: {proc.stderr.strip()}")
    timestamps = _parse_showinfo_timestamps(proc.stderr)
    return "".join(f"{t:.3f}\n" for t in timestamps)
