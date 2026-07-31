"""The 3.12 pinned identity path: single-track same-family muxing (spec §12.20 item 1).

The suite's job here is narrow and specific. It is not to prove ffmpeg correct — it is to
make the two things the spec *assumes* fail loudly the day they stop being true:

1. the muxer is deterministic under the pinned invocation, and
2. the muxed member holds exactly the source track's samples,

with the second checked by `corpus.streams` — this package's own engine-free reader —
precisely so a verification and the thing it verifies do not share an implementation.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from corpus import mux, streams

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _two_track_clip(out: Path) -> Path:
    """A 2s h264+aac mp4 built from synthetic sources — deterministic content, two tracks,
    so `-map 0:<n>` has something to choose between and a wrong index is visible."""
    src = out / "source.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    return src


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> Path:
    return _two_track_clip(tmp_path_factory.mktemp("mux"))


def test_the_source_has_the_two_tracks_the_rest_of_this_file_assumes(clip: Path) -> None:
    # Guard against a fixture that silently produced one track: every assertion below
    # would still "pass" on a single-track file while testing nothing about track choice.
    tracks = {t.index: t.kind for t in streams.probe_streams(clip)}
    assert tracks == {0: "video", 1: "audio"}


def test_muxing_a_track_yields_a_single_track_container_of_the_same_family(
    clip: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "video.mp4"
    framing = mux.mux_stream_to(clip, 0, dest)

    produced = streams.probe_streams(dest)
    assert len(produced) == 1, "a muxed member holds exactly one track"
    assert produced[0].codec == "h264"
    assert framing.samples == streams.sample_count(clip, 0)


def test_the_audio_track_muxes_to_its_own_container(clip: Path, tmp_path: Path) -> None:
    dest = tmp_path / "audio.m4a"
    framing = mux.mux_stream_to(clip, 1, dest)

    produced = streams.probe_streams(dest)
    assert len(produced) == 1
    assert produced[0].kind == "audio"
    assert framing.samples == streams.sample_count(clip, 1)


def test_the_muxed_member_carries_its_own_timeline(clip: Path, tmp_path: Path) -> None:
    """The whole reason the elementary form was insufficient (§6.2's retired timeline
    inheritance): a bare stream has no duration. A single-track container does."""
    dest = tmp_path / "video.mp4"
    mux.mux_stream_to(clip, 0, dest)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(dest)],
        check=True, capture_output=True, text=True,
    )
    assert float(probe.stdout.strip()) > 0.0


def test_the_pinned_invocation_is_deterministic(clip: Path, tmp_path: Path) -> None:
    """THE CANARY. Same input, same version, twice — byte-identical.

    This is what the spec leans on in place of forbidding an engine. If it ever fails,
    the `framing:` stamp's `version` is what makes the change explainable, and
    continuity-gated supersession (§12.8) is what makes it survivable — but this test
    failing is the signal that either is needed at all.
    """
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    mux.mux_stream_to(clip, 0, a)
    mux.mux_stream_to(clip, 0, b)
    assert a.read_bytes() == b.read_bytes()


def test_the_pinned_invocation_strips_the_muxer_version_string(
    clip: Path, tmp_path: Path
) -> None:
    """`-fflags +bitexact` exists to remove the one version-dependent thing measured in
    the output: the `(c)too` atom carrying `Lavf<version>`. If a future ffmpeg starts
    writing its version somewhere bitexact does not reach, this catches it — the bytes
    would otherwise change on upgrade with nothing pointing at why."""
    dest = tmp_path / "video.mp4"
    mux.mux_stream_to(clip, 0, dest)
    assert b"Lavf" not in dest.read_bytes()


def test_wall_clock_never_enters_the_member(clip: Path, tmp_path: Path) -> None:
    """`mvhd` creation/modification are the obvious determinism hazard — a muxer writing
    "now" would make every re-derivation a new identity. Measured to be zeroed; pinned
    here so a change in that behaviour is a test failure and not a silent fleet
    re-identification."""
    dest = tmp_path / "video.mp4"
    mux.mux_stream_to(clip, 0, dest)
    data = dest.read_bytes()

    i = data.find(b"mvhd")
    assert i > 0, "no mvhd box in the muxed member"
    version = data[i + 4]
    assert version == 0, "version-1 mvhd would need 64-bit field widths here"
    creation = int.from_bytes(data[i + 8 : i + 12], "big")
    modification = int.from_bytes(data[i + 12 : i + 16], "big")
    assert (creation, modification) == (0, 0)


def test_the_stamp_names_the_producer_and_its_version(clip: Path, tmp_path: Path) -> None:
    framing = mux.mux_stream_to(clip, 0, tmp_path / "v.mp4")
    stamp = framing.as_stamp()

    assert stamp["muxer"] == "ffmpeg/lavf"
    assert stamp["flags"] == "bitexact"
    assert stamp["samples"] > 0
    # A version that is not a real version makes the stamp decorative.
    assert stamp["version"].count(".") == 2
    assert all(part.isdigit() for part in str(stamp["version"]).split("."))


def test_the_sample_count_comes_from_our_reader_not_the_muxer(
    clip: Path, tmp_path: Path
) -> None:
    """The oracle property. `sample_count` must be answerable without ffmpeg at all — if
    it ever routes through the engine, the check stops being independent of the thing it
    checks and this test's premise quietly dies.

    Checked structurally (what the module imports) rather than by scanning its prose: the
    docstring necessarily says the word "ffmpeg" in order to promise it does not use it,
    so a text match here would fail on the very sentence that states the guarantee.
    """
    import ast

    import corpus.streams as s

    tree = ast.parse(Path(s.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            if node.level:  # relative: `from . import mux`
                imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level:
            imported.update(a.name for a in node.names)

    assert "subprocess" not in imported, "an engine-free reader spawns no processes"
    assert "mux" not in imported, "the oracle must not depend on the producer"
    assert streams.sample_count(clip, 0) > 0


def test_a_mismatched_sample_count_refuses_rather_than_repairs(
    clip: Path, tmp_path: Path, monkeypatch
) -> None:
    """A member whose sample count is not the source's is not that track. Simulated by
    lying about the source count, which is the only way to force the disagreement
    without a corrupt fixture."""
    real = streams.sample_count

    def _inflated(path, stream_id):
        return real(path, stream_id) + 1 if path == clip else real(path, stream_id)

    monkeypatch.setattr(mux.streams, "sample_count", _inflated)
    with pytest.raises(mux.SampleCountMismatch):
        mux.mux_stream_to(clip, 0, tmp_path / "v.mp4")


def test_an_unknown_track_names_what_is_there(clip: Path) -> None:
    with pytest.raises(ValueError, match="no such track"):
        list(mux.mux_stream(clip, 7))


def test_mux_stream_yields_the_same_bytes_it_writes(clip: Path, tmp_path: Path) -> None:
    """The iterator form is what `containment`/`resolver` consume; it must agree with the
    file form byte for byte, or a cached member and a streamed one would differ."""
    dest = tmp_path / "direct.mp4"
    mux.mux_stream_to(clip, 0, dest)
    streamed = b"".join(mux.mux_stream(clip, 0))
    assert streamed == dest.read_bytes()


def test_the_extension_follows_the_track_kind() -> None:
    assert mux.extension_for_kind("video") == "mp4"
    assert mux.extension_for_kind("audio") == "m4a"
    # An unusual kind is still ISOBMFF — naming must not become a promotion failure.
    assert mux.extension_for_kind("timecode") == "mp4"


def test_the_muxer_is_named_never_inferred_from_the_extension(tmp_path: Path) -> None:
    """Regression for a failure the suite caught and reasoning did not.

    ffmpeg picks its muxer from the output extension unless told otherwise, and `.m4a`
    selects `ipod` — which refuses Opus ("Could not find tag for codec opus"). An audio
    track would have been unpromotable for precisely the reason 3.12 exists to eliminate:
    a container that cannot carry a codec that came out of a container. So the format is
    passed explicitly, and this pins it against an Opus member written to an `.m4a` name.
    """
    src = tmp_path / "opus-source.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-t", "1", "-c:a", "libopus", str(src)],
        check=True, capture_output=True,
    )
    assert streams.probe_streams(src)[0].codec == "opus"

    dest = tmp_path / "member.m4a"          # the extension that selects `ipod`
    framing = mux.mux_stream_to(src, 0, dest)

    assert framing.samples == streams.sample_count(src, 0)
    assert streams.probe_streams(dest)[0].codec == "opus"
