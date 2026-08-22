"""(3.11 §7.2.1) The cutting pass: lineage, detection dispatch, the drafter, the redirect.

`test_cutting.py` covers the pure span arithmetic. This covers everything the arithmetic sits
inside — which container timeline a leaf's spans are measured in, what happens when a stamp is
missing or disagrees, and the resolver redirect that makes a stored `time_range=` on a leaf
resolve at all.

Most of these need no ffmpeg: `fixed-interval@` has no detector (its boundaries are
arithmetic), so it exercises every path around the detection call without one. The one
end-to-end test that does need ffmpeg is marked.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import frontmatter
import pytest
import yaml

from corpus import cut, derive, paths, recordbuild, records, resolver, segments
from corpus._cli import cut as cut_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus.draft import video_stream

_HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not _HAVE_FFMPEG, reason="ffmpeg not installed")

_CID = "c" * 64
_LID = "1" * 64
_FIXED = {"id": "fixed-interval@0.1.0", "seconds": 10}


# ---------- scaffolding ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema" / "origin" / "web").mkdir(parents=True)
    return root


def _container(root: Path, *, duration: float | None = 100.0, mime: str = "video/mp4") -> Path:
    post = frontmatter.Post("")
    post.metadata.update({"id": _CID, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(
        post, mime=mime, fields={"duration": duration} if duration is not None else {}
    )
    records.append_origin_block(
        post, uri="https://example.com/v.mp4", snapshot="2026-07-29T00:00:00Z"
    )
    path = paths.record_path(root, _CID)
    path.parent.mkdir(parents=True, exist_ok=True)
    records.dump(post, path)
    return path


def _leaf(
    root: Path,
    *,
    lineage: str | None = f"corpus://{_CID}?stream_id=0",
    stamp: dict | None = None,
    body: str = "",
) -> Path:
    post = frontmatter.Post(body)
    post.metadata.update({"id": _LID, "touch": "corpus.promote@0.1.0"})
    records.set_artifact_block(
        post, mime="video/h264", fields={"cutting": stamp} if stamp else {}
    )
    if lineage:
        records.append_origin_block(post, uri=lineage, snapshot="2026-07-29T00:00:00Z")
    path = paths.record_path(root, _LID)
    path.parent.mkdir(parents=True, exist_ok=True)
    records.dump(post, path)
    return path


# ---------- lineage: which container, which stream ---------- #


def test_stream_lineage_reads_the_containment_origin(tmp_path):
    root = _corpus(tmp_path)
    post = records.load(_leaf(root))
    assert cut.stream_lineage(post) == (_CID, "stream_id=0")


def test_a_non_stream_lineage_is_not_a_stream_lineage(tmp_path):
    """An `el=` member (an HTML page's inline `<video>`) is promoted from a container too, but
    its container is not a media timeline — so it must not be mistaken for one."""
    root = _corpus(tmp_path)
    post = records.load(_leaf(root, lineage=f"corpus://{_CID}?el=597.1.3.1.1"))
    assert cut.stream_lineage(post) is None


def test_a_web_origin_is_not_a_stream_lineage(tmp_path):
    root = _corpus(tmp_path)
    post = records.load(_leaf(root, lineage="https://example.com/track.h264"))
    assert cut.stream_lineage(post) is None


def test_a_chained_lineage_address_is_not_a_bare_stream(tmp_path):
    """`?stream_id=0&time_range=…` names a CUT of a stream, not the stream. Reading it as the
    latter would make the leaf's whole timeline the span its lineage happens to name."""
    root = _corpus(tmp_path)
    post = records.load(
        _leaf(root, lineage=f"corpus://{_CID}?stream_id=0&time_range=0-5")
    )
    assert cut.stream_lineage(post) is None


# ---------- duration: the container's, because the leaf has none ---------- #


def test_duration_prefers_the_attested_field(tmp_path):
    root = _corpus(tmp_path)
    post = records.load(_container(root, duration=616.53))
    assert cut.container_duration(post, None) == 616.53


def test_no_duration_and_no_artifact_is_unresolved_not_zero(tmp_path):
    """Substituting 0 would yield an empty span list, which reads identically to "the detector
    found nothing" — the one distinction the authoring pass most needs."""
    root = _corpus(tmp_path)
    post = records.load(_container(root, duration=None))
    with pytest.raises(cut.Unresolved):
        cut.container_duration(post, None)


# ---------- detection dispatch ---------- #


def test_fixed_interval_needs_no_detector(tmp_path):
    root = _corpus(tmp_path)
    assert cut.detect_cuts(root, _CID, "stream_id=0", _FIXED) == []


def test_an_unknown_strategy_family_is_unresolved(tmp_path):
    """Never a silent fallback: cutting under a strategy nobody declared would have the stamp
    attest a lie about how the addresses were produced."""
    root = _corpus(tmp_path)
    with pytest.raises(cut.Unresolved):
        cut.detect_cuts(root, _CID, "stream_id=0", {"id": "vibes@1.0.0"})


def test_a_declared_but_unbuilt_strategy_says_so(tmp_path):
    """`keyframe@` is named by the spec and not implemented. It must not degrade to
    scene-threshold — the two produce different boundaries."""
    root = _corpus(tmp_path)
    with pytest.raises(NotImplementedError, match="keyframe"):
        cut.detect_cuts(root, _CID, "stream_id=0", {"id": "keyframe@0.1.0"})


def test_scene_threshold_without_a_threshold_is_unresolved(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(cut.Unresolved):
        cut.detect_cuts(root, _CID, "stream_id=0", {"id": "scene-threshold@0.1.0"})


# ---------- the pass ---------- #


def test_cut_stream_under_a_fixed_interval(tmp_path):
    root = _corpus(tmp_path)
    post = records.load(_container(root, duration=25.0))
    out = cut.cut_stream(root, post, _CID, "stream_id=0", strategy=_FIXED)
    assert out.spans == [(0.0, 10.0), (10.0, 20.0), (20.0, 25.0)]
    assert out.addresses == [
        "time_range=0-10", "time_range=10-20", "time_range=20-25",
    ]
    assert out.stamp == {"id": "fixed-interval@0.1.0", "seconds": 10, "cuts": 3,
                         "duration": 25.0}


def test_an_explicit_strategy_beats_resolution(tmp_path):
    """The re-attestation path passes the leaf's ALREADY STAMPED strategy: a re-resolution
    years later could answer differently (an overlay gained a `cut_strategy:`), and §7.2.1
    resolves once at promotion."""
    root = _corpus(tmp_path)
    (root / "schema" / "origin" / "web" / "example.com.yaml").write_text(
        yaml.safe_dump({
            "kind": "interpretive",
            "applies_to": {"hosts": ["example.com"]},
            "cut_strategy": {"id": "fixed-interval@0.1.0", "seconds": 2},
        }),
        encoding="utf-8",
    )
    post = records.load(_container(root, duration=25.0))
    records.set_origin_schema_id(post, "example.com")
    out = cut.cut_stream(root, post, _CID, "stream_id=0", strategy=_FIXED)
    assert out.strategy["seconds"] == 10  # the passed strategy, not the overlay's 2


# ---------- the degeneracy report (the ticket's explicit demand) ---------- #


def test_one_span_reports_no_boundaries(tmp_path):
    signals = cut.degeneracy_signals([(0.0, 616.0)], 616.0, raw_cut_count=0)
    assert [s.id for s in signals] == ["no-boundaries"]


def test_a_frame_by_frame_cut_list_reports_over_segmentation(tmp_path):
    """The named trap: a scrolling screen recording fires the detector per frame. 226 spans
    over 30s is not a segmentation, and the mechanical stage has to say so."""
    spans = [(i * 0.13, (i + 1) * 0.13) for i in range(226)]
    signals = cut.degeneracy_signals(spans, 30.0, raw_cut_count=225)
    assert [s.id for s in signals] == ["over-segmented"]
    assert "226 spans" in signals[0].detail


def test_a_healthy_cut_list_reports_nothing(tmp_path):
    spans = [(i * 20.0, (i + 1) * 20.0) for i in range(30)]
    assert cut.degeneracy_signals(spans, 600.0, raw_cut_count=29) == []


def test_a_few_short_spans_are_not_over_segmentation(tmp_path):
    """A median needs a population before it means anything — three quick cuts in a title
    sequence are not a broken strategy."""
    spans = [(0.0, 0.5), (0.5, 1.0), (1.0, 60.0)]
    assert cut.degeneracy_signals(spans, 60.0, raw_cut_count=2) == []


# ---------- the drafter ---------- #


def _draft_leaf(root: Path, leaf_file: Path):
    post = records.load(leaf_file)
    build = recordbuild.begin_from_post(post, root)
    result = video_stream.draft(
        leaf_file,  # any real file: the drafter only stat()s it
        build=build,
        corpus_root=root,
        record_id=_LID,
        record_metadata=post.metadata,
    )
    return build, result


def _issue_ids(result) -> list[str]:
    return [i["id"] for i in result["issues"]]


def test_an_unstamped_leaf_derives_no_markers(tmp_path):
    """Unstamped is unresolved, not defaulted (§7.2.1). Emitting markers under a
    freshly-guessed strategy is the silent re-addressing the stamp exists to prevent."""
    root = _corpus(tmp_path)
    _container(root)
    build, result = _draft_leaf(root, _leaf(root))
    assert build.blocks == []
    assert _issue_ids(result) == ["cut-unresolved"]


def test_a_stamped_leaf_derives_one_marker_per_span(tmp_path):
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    stamp = {**_FIXED, "cuts": 3, "duration": 25.0}
    build, result = _draft_leaf(root, _leaf(root, stamp=stamp))
    assert [b.address for b in build.blocks] == [
        "time_range=0-10", "time_range=10-20", "time_range=20-25",
    ]
    assert all(b.atom == "image" and not b.body for b in build.blocks)
    assert result["issues"] == []


def test_markers_are_sectionless(tmp_path):
    """The PDF's rule: the mechanical stage makes NO shape judgment. Grouping the spans would
    be one."""
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    build, _ = _draft_leaf(root, _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0}))
    assert all(isinstance(b, segments.Segment) for b in build.blocks)


def test_a_drifted_cut_count_holds_the_record(tmp_path):
    """§7.2.1's second rule. The stamp says 3 spans; the strategy now yields 5. Emitting the
    5 would re-point every stored address, so nothing is emitted and both counts are named."""
    root = _corpus(tmp_path)
    _container(root, duration=50.0)  # 50s / 10s = 5 spans, but the stamp attests 3
    build, result = _draft_leaf(root, _leaf(root, stamp={**_FIXED, "cuts": 3,
                                                         "duration": 25.0}))
    assert build.blocks == []
    assert _issue_ids(result) == ["cut-count-drift"]
    issue = result["issues"][0]
    assert issue["severity"] == "error"
    assert issue["fields"]["attested_cuts"] == 3
    assert issue["fields"]["derived_cuts"] == 5


def test_a_stamped_leaf_with_no_lineage_reports_rather_than_guessing(tmp_path):
    root = _corpus(tmp_path)
    _container(root)
    build, result = _draft_leaf(
        root, _leaf(root, lineage=None, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    )
    assert build.blocks == []
    assert _issue_ids(result) == ["cut-unresolved"]


def test_degeneracy_signals_reach_the_record_as_issues(tmp_path):
    """Report it; do not paper over it. The spans still stand — the signal is information."""
    root = _corpus(tmp_path)
    _container(root, duration=8.0)
    build, result = _draft_leaf(root, _leaf(root, stamp={**_FIXED, "cuts": 1,
                                                         "duration": 8.0}))
    assert len(build.blocks) == 1  # the whole timeline, one span
    assert _issue_ids(result) == ["cut-no-boundaries"]


# ---------- the strip (the trap this closes) ---------- #


def test_reattest_strip_preserves_the_cutting_stamp(tmp_path):
    """The stamp records a RESOLUTION, not a byte-fact: the leaf's own bytes cannot regenerate
    it and its lineage is not a lookup route. Stripping it would delete the resolution and
    leave the count check with nothing to compare — the drift it exists to detect, caused by
    the strip that was supposed to be neutral."""
    root = _corpus(tmp_path)
    post = records.load(_leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0}))
    derive.strip_attested_layer(post)
    assert records.cutting(post) == {**_FIXED, "cuts": 3, "duration": 25.0}


def test_the_strip_still_clears_every_other_field(tmp_path):
    root = _corpus(tmp_path)
    path = _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    post = records.load(path)
    art = records.artifact_block(post)
    art["fields"]["size_bytes"] = 4096
    derive.strip_attested_layer(post)
    fields = (records.artifact_block(post) or {}).get("fields") or {}
    assert set(fields) == {"cutting"}


# ---------- the resolver redirect ---------- #


def _parsed(uri: str):
    from corpus import functional_uri as furi

    return furi.parse(uri)


def test_a_timeline_op_on_a_leaf_redirects_through_the_container(tmp_path):
    """An elementary stream carries no container timing, so a second of "leaf time" is not a
    second of the timeline the leaf's stored addresses were measured in."""
    root = _corpus(tmp_path)
    _container(root)
    post = records.load(_leaf(root))
    got = resolver._member_route_redirect(root, _parsed(f"corpus://{_LID}?frame=30"), post)
    assert got == f"corpus://{_CID}?stream_id=0&frame=30"


def test_the_redirect_carries_a_whole_chain(tmp_path):
    root = _corpus(tmp_path)
    _container(root)
    post = records.load(_leaf(root))
    got = resolver._member_route_redirect(
        root, _parsed(f"corpus://{_LID}?time_range=10-20&format=mp4"), post
    )
    assert got == f"corpus://{_CID}?stream_id=0&time_range=10-20&format=mp4"


def test_format_redirects_through_the_container(tmp_path):
    """*(v32)* `format=` addresses no timeline, but it DOES need playable input — a
    payload leaf's own bytes are not playable (§2), so `format=` now redirects through
    the container too, same as the timeline ops. (Pre-v32 a promoted leaf's bytes were
    themselves a playable single-track container, so this redirected nowhere; that
    changed with the payload-identity principle.)"""
    root = _corpus(tmp_path)
    _container(root)
    post = records.load(_leaf(root))
    assert resolver._member_route_redirect(
        root, _parsed(f"corpus://{_LID}?format=mp4"), post
    ) == f"corpus://{_CID}?stream_id=0&format=mp4"


def test_transcribe_redirects_through_the_container(tmp_path):
    """*(v32)* `transcribe` needs playable input too — an audio payload leaf's own bytes
    carry no self-framing at all (no ADTS, no length-prefixed Opus), so it redirects the
    same way. `corpus.transforms.audio.transcribe` isolates the addressed stream via
    `corpus.mux` before handing it to the transcriber, so this is still the leaf's OWN
    bytes reaching the adapter — never a lossy `extract_audio` derivative (module note,
    `corpus.transforms.audio`)."""
    root = _corpus(tmp_path)
    _container(root)
    post = records.load(_leaf(root))
    assert resolver._member_route_redirect(
        root, _parsed(f"corpus://{_LID}?transcribe"), post
    ) == f"corpus://{_CID}?stream_id=0&transcribe"


def test_an_explicit_stream_id_is_never_second_guessed(tmp_path):
    root = _corpus(tmp_path)
    _container(root)
    post = records.load(_leaf(root))
    assert resolver._member_route_redirect(
        root, _parsed(f"corpus://{_LID}?stream_id=0&frame=1"), post
    ) is None


def test_a_container_does_not_redirect_its_own_timeline_ops(tmp_path):
    root = _corpus(tmp_path)
    post = records.load(_container(root))
    assert resolver._member_route_redirect(
        root, _parsed(f"corpus://{_CID}?frame=30"), post
    ) is None


def test_no_redirect_when_the_container_record_is_missing(tmp_path):
    """A promoted record's origin `uri:` is HISTORY (§12.9's byte-lookup independence
    rule) — the container it names at promotion time may since have been removed
    (`corpus rm`) while the same bytes remain resolvable through a different surviving
    container via the member index. Redirecting into a dead container would break that
    fallback, so the redirect stands down and lets ordinary resolution (which consults the
    member index, not lineage) find the live route instead."""
    root = _corpus(tmp_path)
    post = records.load(_leaf(root))  # no _container(root) call — the container is absent
    assert resolver._member_route_redirect(
        root, _parsed(f"corpus://{_LID}?frame=30"), post
    ) is None


# ---------- the `scene` op ---------- #


def test_scene_reports_unresolved_rather_than_failing(tmp_path):
    """A caller asking "how is this cut?" of an unstamped leaf deserves "it isn't yet", not an
    exception — the state is legitimate."""
    root = _corpus(tmp_path)
    _container(root)
    _leaf(root)
    import json

    payload = json.loads(resolver.resolve(f"corpus://{_LID}?scene", root).read_text())
    assert payload["unresolved"] is True and payload["spans"] == []


def test_scene_reports_the_spans_and_the_stamp(tmp_path):
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    import json

    payload = json.loads(resolver.resolve(f"corpus://{_LID}?scene", root).read_text())
    assert payload["unresolved"] is False
    assert [s["address"] for s in payload["spans"]] == [
        "time_range=0-10", "time_range=10-20", "time_range=20-25",
    ]
    assert payload["spans"][0]["seconds"] == 10.0
    assert payload["cutting"]["cuts"] == 3
    assert "drift" not in payload


def test_scene_names_the_drift_when_the_count_moved(tmp_path):
    root = _corpus(tmp_path)
    _container(root, duration=50.0)
    _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    import json

    payload = json.loads(resolver.resolve(f"corpus://{_LID}?scene", root).read_text())
    assert payload["drift"] == {"attested_cuts": 3, "derived_cuts": 5}


# ---------- the CLI verb ---------- #


def _run_cut(root: Path, record: str, **kw) -> int:
    defaults = {
        "record": record, "write": False, "force": False, "regenerate": False,
        "json": False, "corpus_root": str(root),
    }
    return cut_cli.run(argparse.Namespace(**{**defaults, **kw}))


def _declare_fixed_interval(root: Path) -> None:
    """Point the container's origin overlay at `fixed-interval@`, whose boundaries are pure
    arithmetic — so the CLI tests exercise every path around detection without ffmpeg or
    resident artifact bytes."""
    (root / "schema" / "origin" / "web" / "example.com.yaml").write_text(
        yaml.safe_dump({
            "kind": "interpretive",
            "applies_to": {"hosts": ["example.com"]},
            "cut_strategy": _FIXED,
        }),
        encoding="utf-8",
    )
    container_post = records.load(paths.record_path(root, _CID))
    records.set_origin_schema_id(container_post, "example.com")
    records.dump(container_post, paths.record_path(root, _CID))


def test_cut_reports_absent_bytes_rather_than_crashing(tmp_path, capsys):
    """`artifacts/` is gitignored, so a record whose bytes are not resident is an everyday
    state. The mime default (`scene-threshold@`) needs the container's bytes to detect against
    — and must say "unresolved", not raise."""
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    _leaf(root)
    assert _run_cut(root, _LID) == 1
    assert "unresolved" in capsys.readouterr().out


def test_cut_is_dry_run_by_default(tmp_path, capsys):
    """The stamp is what a record's addresses rest on; writing one is not neutral."""
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    leaf_file = _leaf(root)
    _declare_fixed_interval(root)
    assert _run_cut(root, _LID) == 0
    assert "dry run" in capsys.readouterr().out
    assert records.cutting(records.load(leaf_file)) is None


def test_cut_write_stamps_the_leaf(tmp_path, capsys):
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    leaf_file = _leaf(root)
    _declare_fixed_interval(root)
    assert _run_cut(root, _LID, write=True) == 0
    stamp = records.cutting(records.load(leaf_file))
    assert stamp == {**_FIXED, "cuts": 3, "duration": 25.0}


def test_cut_holds_rather_than_rewriting_a_moved_count(tmp_path, capsys):
    root = _corpus(tmp_path)
    _container(root, duration=50.0)
    leaf_file = _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    assert _run_cut(root, _LID, write=True) == 1
    out = capsys.readouterr().out
    assert "HELD" in out
    assert records.cutting(records.load(leaf_file))["cuts"] == 3  # untouched


def test_cut_force_rewrites_a_moved_count(tmp_path):
    root = _corpus(tmp_path)
    _container(root, duration=50.0)
    leaf_file = _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    assert _run_cut(root, _LID, write=True, force=True) == 0
    assert records.cutting(records.load(leaf_file))["cuts"] == 5


def test_cut_refreshes_an_unchanged_stamp_without_a_write(tmp_path):
    root = _corpus(tmp_path)
    _container(root, duration=25.0)
    leaf_file = _leaf(root, stamp={**_FIXED, "cuts": 3, "duration": 25.0})
    before = leaf_file.read_text(encoding="utf-8")
    assert _run_cut(root, _LID, write=True) == 0
    assert leaf_file.read_text(encoding="utf-8") == before  # idempotent, no touch appended


# ---------- (#131) per-host policy reaches a leaf through lineage ---------- #


def test_a_leaf_inherits_its_containers_host(tmp_path):
    """A promoted member's first origin is `corpus://…`, which names no host — so a per-host
    overlay lookup against it silently finds nothing and the leaf falls back to the global
    default. `transcription.enabled: false` declared on a host would apply to the video
    container and be silently ignored on the audio track promoted out of it."""
    from corpus.draft import _hostcfg

    root = _corpus(tmp_path)
    _container(root)
    post = records.load(_leaf(root))
    assert _hostcfg.first_origin_uri(post.metadata) == f"corpus://{_CID}?stream_id=0"
    assert _hostcfg.host_bearing_origin_uri(root, post.metadata) == "https://example.com/v.mp4"


def test_the_walk_survives_a_missing_container(tmp_path):
    from corpus.draft import _hostcfg

    root = _corpus(tmp_path)  # no container record written
    post = records.load(_leaf(root))
    assert _hostcfg.host_bearing_origin_uri(root, post.metadata) == ""


def test_the_walk_terminates_on_a_cycle(tmp_path):
    """A hand-edited record could point its lineage at itself. Report no host rather than
    looping — the fallback is the global default, which is a correct answer."""
    from corpus.draft import _hostcfg

    root = _corpus(tmp_path)
    post = frontmatter.Post("")
    post.metadata.update({"id": _CID, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime="video/mp4", fields={})
    records.append_origin_block(
        post, uri=f"corpus://{_CID}?stream_id=0", snapshot="2026-07-29T00:00:00Z"
    )
    path = paths.record_path(root, _CID)
    path.parent.mkdir(parents=True, exist_ok=True)
    records.dump(post, path)
    assert _hostcfg.host_bearing_origin_uri(root, records.load(path).metadata) == ""


def test_a_direct_web_origin_is_returned_unchanged(tmp_path):
    from corpus.draft import _hostcfg

    root = _corpus(tmp_path)
    post = records.load(_container(root))
    assert _hostcfg.host_bearing_origin_uri(root, post.metadata) == "https://example.com/v.mp4"


# ---------- end to end, with a real container ---------- #


def _three_scene_clip(out: Path) -> Path:
    """Three visually distinct 2-second shots concatenated — hard cuts at exactly 2.0s and
    4.0s, which `scenes=0.3` detects reproducibly.

    The patterns are deliberate. A first attempt used solid `color=red`/`green`/`blue`, and the
    detector found only ONE of the two cuts: a full-frame hue change between uniform fields
    scores *below* 0.3 (red→green did; green→blue did not). Solid fields are a pathological
    input for a frame-difference measure, and testing against one would have measured that
    quirk rather than the pipeline. It is also a small live demonstration of §12.20 OQ1's
    finding that some real transitions are not threshold-fixable.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "smptebars=d=2:s=160x120:r=10",
         "-f", "lavfi", "-i", "testsrc2=d=2:s=160x120:r=10",
         "-f", "lavfi", "-i", "color=c=black:d=2:s=160x120:r=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
         "-map", "[v]", "-map", "3:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
        check=True, capture_output=True, text=True,
    )
    return out


@needs_ffmpeg
def test_promote_resolves_and_stamps_the_cut_strategy(tmp_path):
    """The whole chain: a real mp4 → track manifest → promote the video stream → the leaf is
    born carrying its resolved `cutting:` stamp, and its body derives one marker per span."""
    root = _corpus(tmp_path)
    clip = _three_scene_clip(tmp_path / "clip.mp4")
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    shutil.copy(clip, cap / "clip.mp4")
    assert ingest_cli._ingest_one(root, cap / "clip.mp4") == 0

    from corpus import hashing

    cid = hashing.hash_file(clip)["blake3"]
    container = records.load(paths.record_path(root, cid))
    rows = [r for r in records.iter_members(container)
            if str(r.get("media_type", "")).startswith("video/")]
    assert rows, "the track manifest declared no video stream"
    address = rows[0]["address"]

    assert promote_cli.run(argparse.Namespace(
        uri=f"corpus://{cid}?{address}", json=False, corpus_root=str(root)
    )) == 0

    leaf_id = str(rows[0]["transport"]).split(":", 1)[1]
    leaf = records.load(paths.record_path(root, leaf_id))
    stamp = records.cutting(leaf)
    assert stamp is not None, "promotion did not resolve the cut strategy"
    assert stamp == {"id": "scene-threshold@0.1.0", "threshold": 0.3, "cuts": 3,
                     "duration": 6.0}

    # …and the body derives from the stamp, one marker per span, addresses in the CONTAINER's
    # timeline (the leaf has none of its own), closing on the container's duration.
    body = derive.derive_body(leaf, root)
    blocks = segments.iter_blocks(body)
    assert [b.address for b in blocks] == [
        "time_range=0-2", "time_range=2-4", "time_range=4-6",
    ]
    assert all(b.atom == "image" and not (b.body or "").strip() for b in blocks)


@needs_ffmpeg
def test_a_stored_time_range_on_a_leaf_resolves_through_its_container(tmp_path):
    """The property that makes the markers worth emitting. Before the redirect, a `time_range=`
    on a `video/h264` leaf raised NotImplementedError ("no transformation pipeline") — the
    schema note called elementary streams "not independently seekable ... fail by
    construction". They still are; the resolver now reads the timeline off the container the
    leaf came from, so the address resolves to the frames it names."""
    root = _corpus(tmp_path)
    clip = _three_scene_clip(tmp_path / "clip.mp4")
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    shutil.copy(clip, cap / "clip.mp4")
    assert ingest_cli._ingest_one(root, cap / "clip.mp4") == 0

    from corpus import hashing

    cid = hashing.hash_file(clip)["blake3"]
    container = records.load(paths.record_path(root, cid))
    rows = [r for r in records.iter_members(container)
            if str(r.get("media_type", "")).startswith("video/")]
    assert promote_cli.run(argparse.Namespace(
        uri=f"corpus://{cid}?{rows[0]['address']}", json=False, corpus_root=str(root)
    )) == 0
    leaf_id = str(rows[0]["transport"]).split(":", 1)[1]

    frame = resolver.resolve(f"corpus://{leaf_id}?frame=3", root)
    assert frame.suffix == ".png" and frame.stat().st_size > 0
    span = resolver.resolve(f"corpus://{leaf_id}?time_range=2-4", root)
    assert span.stat().st_size > 0
