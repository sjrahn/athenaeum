"""Single-track container muxing — the DERIVED playable-surface path (spec §6.2, v32).

A promoted media-stream leaf's identity bytes are its raw payload (`corpus.streams`,
§2) — deliberately not playable, since parameter sets and timing live in the container's
tables rather than the payload. What this module produces instead is a **rendering**:
the source container rewritten with exactly one track (`mp4(video+audio)` ->
`mp4(video)` + `m4a(audio)`), sample payloads copied verbatim in decode order and never
re-encoded, so the result is a file a player accepts and one that carries its own
timescale, duration and sample tables. This is version-labeled ephemeral cache output
(§6.2's muxing contract), never a record's identity — `corpus.resolver` derives it on
demand for an op that needs playable input (`transcribe`, a cut, a frame render) and
caches it, the same way any other engine-versioned op is cached.

**Before v32** (3.12 through v31), this WAS the identity path: a muxer sat between "the bytes a
record's id is computed from" and "the source container", on the theory that a pinned
invocation plus an attested producer plus an independent sample-count check was durable
enough — `-c copy -fflags +bitexact`, the retired `framing:` stamp naming muxer/version/
count, `corpus.streams`' own ISOBMFF reader verifying the count independently. That
regime existed to fix a REAL problem (the elementary form it replaced: AAC at
`audioObjectType=29` has no ADTS encoding, 2-bit object-type field, AOT<=4 — 84 of 102
public containers had a permanently unpromotable audio track for exactly this reason),
but it was itself measured insufficient: engine output is not guaranteed byte-stable
across tool versions even pinned, and an identity that keys on wrapped bytes strands its
own records when the wrapping tool moves. The payload-identity principle (§2) removes the
engine from the identity path entirely; this module keeps doing the muxing work, just for
a rendering instead of a record.

- **Pinned invocation.** `-c copy -fflags +bitexact`. Measured: `-c copy` is byte-identical
  across runs at a fixed version, and the entire default-vs-bitexact delta is a 37-byte
  `(c)too` atom carrying the libavformat version string. `mvhd`/`tkhd` creation and
  modification times are written as **zero** with or without the flag, even from a source
  that carries real ones — the muxer neither propagates nor invents a timestamp.
- **Sample-count check.** The sample count is computed by `corpus.streams` — this package's
  own engine-free ISOBMFF reader — from the SOURCE container's tables, and then verified
  against the MUXED output by that same reader, so a rendering that dropped, duplicated or
  re-framed a sample is caught rather than silently cached. `corpus.streams` stays
  deliberately ffmpeg-free so the check and the thing it checks never share a failure mode.

Cross-version stability is `-bitexact`'s designed contract (it is what ffmpeg's own
regression suite depends on) and is **not** independently verified here — the suite canary
in `tests/test_mux.py` is what fails the day a version moves the bytes. It matters less
than it once did: a version-drifted rendering is a fresh cache entry under a new engine
label (§6.2/§6.3), never a record whose identity moved.
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

#: The producer id a `Framing` names. Names the tool and its library, not the CLI — what
#: pins a rendering's bytes is libavformat's muxer, and its version is what `version`
#: records. *(Pre-v32 history: this was written onto a promoted leaf's now-retired
#: `framing:` stamp — the attestation that admitted a muxer into the identity path. v32's
#: payload-identity principle removed the engine from that path entirely, so `Framing` now
#: describes a derived rendering only, never a record's identity.)*
MUXER_ID = "ffmpeg/lavf"

#: The pinned determinism flags — recorded so a rendering says which invocation produced
#: it rather than leaving it to be inferred from a version number.
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
    """A rendering's producer facts: which muxer, which version, which flags, and the
    sample count `corpus.streams` verified it against (§6.2). *(Pre-v32 this was a
    promoted leaf's `framing:` stamp, spec §7.2.1 — retired; kept here only as the shape
    `mux_stream_to` returns for a derived rendering's own bookkeeping.)*"""

    muxer: str
    version: str
    flags: str
    samples: int

    def as_stamp(self) -> dict[str, object]:
        """This producer's facts as a flat dict, in a stable field order."""
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
    single-track playable rendering, and return the `Framing` describing it.

    The sample count in the returned `Framing` comes from `corpus.streams` reading the
    SOURCE container, and is verified against the muxed output by the same reader
    before this returns — so a `Framing` that exists is one that has been checked.
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


def framing_for(path: Path, stream_id: int, *, workdir: Path | None = None) -> Framing:
    """The `Framing` a rendering of this track would carry, computed by actually muxing
    it into a throwaway file. No caller in this package still needs it for identity
    (`promote` mints leaf ids from `streams.payload_blake3` instead, v32) — kept for a
    caller that wants a rendering's producer facts verified ahead of materializing it for
    real.

    Pass `workdir` for the same reason `mux_stream` takes one — a multi-GB track should
    not land in a small `/tmp`.
    """
    kind = _kind_of(path, stream_id)
    with tempfile.TemporaryDirectory(
        prefix="corpus-mux-", dir=str(workdir) if workdir else None
    ) as tmpdir:
        dest = Path(tmpdir) / f"probe.{extension_for_kind(kind)}"
        return mux_stream_to(Path(path), stream_id, dest)


def mux_stream(
    path: Path, stream_id: int, *, workdir: Path | None = None
) -> Iterator[bytes]:
    """Track `stream_id` remuxed into a single-track playable rendering, as a chunk
    iterator — the derived-surface producer `corpus.resolver` calls when an op needs
    playable input from a payload leaf (§6.2), never the identity path (that's
    `streams.extract_stream`, whose raw payload this remuxes back into a container).

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
    available tracks when `stream_id` does not exist."""
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
