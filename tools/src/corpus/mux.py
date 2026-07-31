"""Single-track container muxing — the pinned identity path (spec §12.20 item 1, 3.12).

A promoted media-container track's identity bytes are **the source container rewritten
with exactly one track**: `mp4(video+audio)` -> `mp4(video)` + `m4a(audio)`. Sample
payloads are copied verbatim in decode order and never re-encoded; what this module does
is put an envelope back around them, so the member is a file a player accepts and — the
part the superseded elementary form could not do — one that carries its own timescale,
duration and sample tables.

**Why an engine lives here at all.** Until 3.12 the rule was that no muxer may sit in the
identity path, on the reasoning that engine output cannot be deterministic. That rule was
measured and found to refuse records rather than guarantee bytes: AAC at
`audioObjectType=29` has no ADTS encoding (2-bit object-type field, AOT<=4), so 84 of 102
public containers had a permanently unpromotable audio track. The replacement is not
trust — it is a pinned invocation plus an attested producer plus an independent check:

- **Pinned invocation.** `-c copy -fflags +bitexact`. Measured: `-c copy` is byte-identical
  across runs at a fixed version, and the entire default-vs-bitexact delta is a 37-byte
  `(c)too` atom carrying the libavformat version string. `mvhd`/`tkhd` creation and
  modification times are written as **zero** with or without the flag, even from a source
  that carries real ones — the muxer neither propagates nor invents a timestamp.
- **Attested producer.** The `framing:` stamp (§7.2.1) carries muxer, version, flags and a
  sample count, so a byte change across an ffmpeg upgrade is explainable rather than
  mysterious.
- **Independent check.** The sample count is computed by `corpus.streams` — this package's
  own engine-free ISOBMFF reader — from the SOURCE container's tables, and then verified
  against the MUXED output by that same reader. A verification that shared the producer's
  implementation would share its failure mode; this one does not. `corpus.streams` stays
  deliberately ffmpeg-free for exactly this reason.

Cross-version stability is `-bitexact`'s designed contract (it is what ffmpeg's own
regression suite depends on) and is **not** independently verified here — the suite canary
in `tests/test_mux.py` is what fails the day a version moves the bytes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import streams

_CHUNK = 1 << 20

#: The producer id written into the `framing:` stamp. Names the tool and its library,
#: not the CLI — what pins the bytes is libavformat's muxer, and its version is what
#: `version` records.
MUXER_ID = "ffmpeg/lavf"

#: The pinned determinism flags, stamped verbatim so a record says which invocation
#: produced it rather than leaving it to be inferred from a version number.
FLAGS = "bitexact"

#: The muxer, named explicitly and never inferred from the output filename.
#:
#: This is not a stylistic preference — letting the extension choose cost a real codec.
#: ffmpeg maps `.m4a` to its `ipod` muxer, which refuses Opus outright ("Could not find
#: tag for codec opus in stream #0"), so an audio track would have been unpromotable for
#: exactly the reason this amendment exists to eliminate: a container that cannot carry a
#: codec that came out of a container. `-f mp4` is the general ISOBMFF muxer and takes
#: all four codecs. The extension below is therefore a *label*, never a decision.
_FORMAT = "mp4"

#: Track kind -> the single-track container extension. Purely a naming convention for
#: humans and file-type sniffing — the muxer is always `_FORMAT` above, exactly as `.mka`
#: labels Matroska audio without being a distinct format.
_EXTENSION_BY_KIND = {
    "video": "mp4",
    "audio": "m4a",
    "subtitle": "mp4",
}


class MuxUnavailable(RuntimeError):
    """ffmpeg is not installed, or is too old to report a libavformat version.

    Distinct from a mux *failure*: this says the identity path cannot run at all on this
    host, which is a host fact and never a fact about the record — the same distinction
    §4.3.2.2's whole-address gate draws when it refuses to decode.
    """


class MuxFailed(RuntimeError):
    """The muxer ran and did not produce the member. Carries ffmpeg's own stderr."""


class SampleCountMismatch(RuntimeError):
    """The muxed output does not hold the sample count the source track declares.

    This is the oracle firing (module docstring): our engine-free reader counted the
    source's samples one way and the muxed output's another, so the producer dropped,
    duplicated or re-framed something. Never repaired automatically — a member whose
    sample count is not the source's is not that track.
    """


@dataclass(frozen=True)
class Framing:
    """The `framing:` stamp's payload (spec §7.2.1)."""

    muxer: str
    version: str
    flags: str
    samples: int

    def as_stamp(self) -> dict[str, object]:
        """The stamp as it lands on the artifact block — key order is the declaration
        order in the spec, so a diff of two records reads top to bottom."""
        return {
            "muxer": self.muxer,
            "version": self.version,
            "flags": self.flags,
            "samples": self.samples,
        }


def extension_for_kind(kind: str) -> str:
    """The single-track container extension for a track kind. Unknown kinds get `mp4`
    rather than an error: an unusual track is still ISOBMFF, and refusing on the
    extension would turn a naming question into a promotion failure."""
    return _EXTENSION_BY_KIND.get(kind, "mp4")


def libavformat_version() -> str:
    """libavformat's version as `MAJOR.MINOR.MICRO`, read from `ffmpeg -version`.

    This is the number the muxer stamps into its own `(c)too` atom when not run
    bitexact, which is why it is the right thing to record: it names precisely the
    component whose output-layout choices the bytes depend on. Raises `MuxUnavailable`
    when ffmpeg is absent or its banner carries no libavformat line.
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        raise MuxUnavailable("ffmpeg not found on PATH")
    try:
        proc = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - host fault
        raise MuxUnavailable(f"could not run ffmpeg -version: {exc}") from exc
    # `libavformat    62. 12.102 / 62. 12.102` — the field is space-padded per component.
    m = re.search(r"^libavformat\s+(\d+)\.\s*(\d+)\.\s*(\d+)", proc.stdout, re.MULTILINE)
    if not m:
        raise MuxUnavailable("ffmpeg -version reported no libavformat version")
    return ".".join(m.groups())


def mux_stream_to(path: Path, stream_id: int, dest: Path) -> Framing:
    """Write track `stream_id` of the ISOBMFF container at `path` to `dest` as a
    single-track container, and return its `framing:` stamp.

    The sample count in the returned stamp comes from `corpus.streams` reading the
    SOURCE container, and is verified against the muxed output by the same reader
    before this returns — so a stamp that exists is a stamp that has been checked.
    """
    src = Path(path)
    expected = streams.sample_count(src, stream_id)  # engine-free, from the source tables
    version = libavformat_version()
    exe = shutil.which("ffmpeg")
    assert exe is not None  # libavformat_version() already raised if it were missing
    cmd = [
        exe,
        "-nostdin",
        "-v", "error",
        "-y",
        "-fflags", "+bitexact",
        "-i", str(src),
        "-map", f"0:{stream_id}",
        "-c", "copy",
        "-fflags", "+bitexact",
        "-f", _FORMAT,
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        raise MuxFailed(
            f"stream_id={stream_id}: mux produced no member "
            f"(rc={proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    produced = streams.sample_count(dest, 0)  # the output holds exactly one track
    if produced != expected:
        raise SampleCountMismatch(
            f"stream_id={stream_id}: source declares {expected} sample(s), muxed member "
            f"holds {produced} — the member is not that track"
        )
    return Framing(muxer=MUXER_ID, version=version, flags=FLAGS, samples=expected)


def framing_for(path: Path, stream_id: int) -> Framing:
    """The `framing:` stamp a promotion of this track would write, computed by actually
    muxing it into a throwaway file. There is no cheaper honest answer: the sample count
    is only *verified* by producing the member, and a stamp that names an unverified
    count is the thing the stamp exists to prevent."""
    kind = _kind_of(path, stream_id)
    with tempfile.TemporaryDirectory(prefix="corpus-mux-") as tmpdir:
        dest = Path(tmpdir) / f"probe.{extension_for_kind(kind)}"
        return mux_stream_to(Path(path), stream_id, dest)


def mux_stream(
    path: Path, stream_id: int, *, workdir: Path | None = None
) -> Iterator[bytes]:
    """Track `stream_id`'s pinned identity bytes as a chunk iterator — the drop-in for
    the superseded `streams.extract_stream`.

    ISOBMFF muxing needs a seekable output (the `moov` index is finalized against real
    file offsets), so this materializes to a temporary file and then streams it. Pass
    `workdir` to place that temporary beside its destination — a multi-GB track should
    not land in a small `/tmp`.
    """
    src = Path(path)
    kind = _kind_of(src, stream_id)
    tmpdir = tempfile.mkdtemp(prefix="corpus-mux-", dir=str(workdir) if workdir else None)
    dest = Path(tmpdir) / f"member.{extension_for_kind(kind)}"
    try:
        mux_stream_to(src, stream_id, dest)
        with dest.open("rb") as fh:
            while chunk := fh.read(_CHUNK):
                yield chunk
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _kind_of(path: Path, stream_id: int) -> str:
    """The track's kind per the engine-free probe — raises `ValueError` naming the
    available tracks when `stream_id` does not exist, the same contract the superseded
    `extract_stream` had."""
    tracks = streams.probe_streams(Path(path))
    for t in tracks:
        if t.index == stream_id:
            return t.kind
    raise ValueError(
        f"stream_id={stream_id}: no such track ({len(tracks)} track(s) in {path})"
    )


__all__ = [
    "FLAGS",
    "MUXER_ID",
    "Framing",
    "MuxFailed",
    "MuxUnavailable",
    "SampleCountMismatch",
    "extension_for_kind",
    "framing_for",
    "libavformat_version",
    "mux_stream",
    "mux_stream_to",
]
