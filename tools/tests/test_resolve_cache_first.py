"""A cached derivation needs no source bytes, and a verify run builds the member index once
(2026-09-26 — `ath ledger verify` spent ~95% of a ~25-minute run rebuilding the member index).

- `resolve` fetched the artifact's bytes (`containment.ensure_local_bytes`) before any
  derivation's cache check. For a promoted member with no standalone file, that fetch
  routes through the member index, which is one parse of every record in the corpus. So a
  cache HIT still paid for a full corpus walk. Now each branch fetches the bytes only when
  it actually reads them.
- Outside a `containment.member_index_scope` every container-routed fetch rebuilds the
  index; inside one, the first build serves the rest. `verify_ledger` runs inside a scope.
"""

from __future__ import annotations

import shutil

import pytest

from corpus import containment, resolver
from corpus.store import ArtifactMissing
from ledger import verify as verify_mod
from tests.test_el_annotated_35 import _html_record
from tests.test_track_manifest import _corpus, _ingest, _make_clip

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg not installed",
)


def _bytes_now_unreachable(monkeypatch) -> None:
    """From here on, fetching any artifact's bytes fails, as it would if the member-index
    route were gone."""

    def refuse(*_a, **_k):
        raise AssertionError("a cache hit fetched the source bytes")

    monkeypatch.setattr(containment, "ensure_local_bytes", refuse)


# ---------- the cache is checked before the bytes are fetched ---------- #


def test_a_cached_transform_is_served_without_the_source_bytes(tmp_path, monkeypatch):
    root, rid = _html_record(tmp_path)
    first = resolver.resolve(f"corpus://{rid}?text", root)  # the transform ladder
    _bytes_now_unreachable(monkeypatch)
    assert resolver.resolve(f"corpus://{rid}?text", root) == first


def test_a_cached_annotated_view_is_served_without_the_source_bytes(tmp_path, monkeypatch):
    root, rid = _html_record(tmp_path)
    first = resolver.resolve(f"corpus://{rid}?annotated", root)
    _bytes_now_unreachable(monkeypatch)
    assert resolver.resolve(f"corpus://{rid}?annotated", root) == first
    assert resolver.resolve(f"corpus://{rid}", root) == first  # the bare route shares it


def test_the_bare_route_still_fetches_the_bytes(tmp_path, monkeypatch):
    root, rid = _html_record(tmp_path)
    _bytes_now_unreachable(monkeypatch)
    with pytest.raises(AssertionError, match="fetched the source bytes"):
        resolver.resolve(f"corpus://{rid}?raw", root)


@needs_ffmpeg
def test_a_cached_track_is_served_without_probing_its_container(tmp_path, monkeypatch):
    clip = _make_clip(tmp_path / "clip.mp4", vcodec="libx264", acodec="aac")
    root = _corpus(tmp_path)
    rid = _ingest(root, clip)
    first = resolver.resolve(f"corpus://{rid}?stream_id=0", root)
    _bytes_now_unreachable(monkeypatch)
    assert resolver.resolve(f"corpus://{rid}?stream_id=0", root) == first


def test_the_stem_lookup_skips_a_concurrent_workers_scratch_file(tmp_path):
    root, _rid = _html_record(tmp_path)
    uh = "ab" * 32
    shard = root / "cache" / uh[:2]
    shard.mkdir(parents=True)
    (shard / f"{uh}.h264.tmp.4242").write_bytes(b"half")
    assert resolver._find_cached_by_stem(root, uh) is None
    (shard / f"{uh}.h264").write_bytes(b"whole")
    assert resolver._find_cached_by_stem(root, uh) == shard / f"{uh}.h264"


# ---------- one member index per scope ---------- #


def _count_builds(monkeypatch) -> list[int]:
    builds = [0]

    def build(_root):
        builds[0] += 1
        return {}

    monkeypatch.setattr(containment, "build_member_index", build)
    return builds


def _route_through_index(root) -> None:
    with pytest.raises(ArtifactMissing):
        containment.ensure_local_bytes(root, "c" * 64, "bin")


def test_outside_a_scope_every_container_route_rebuilds_the_index(tmp_path, monkeypatch):
    root = _corpus(tmp_path)
    builds = _count_builds(monkeypatch)
    _route_through_index(root)
    _route_through_index(root)
    assert builds == [2]


def test_inside_a_scope_the_index_is_built_once_and_only_when_needed(tmp_path, monkeypatch):
    root = _corpus(tmp_path)
    builds = _count_builds(monkeypatch)
    with containment.member_index_scope():
        assert builds == [0]  # lazy: a batch that never routes never builds
        _route_through_index(root)
        _route_through_index(root)
        assert builds == [1]
    _route_through_index(root)  # the scope's copy does not outlive it
    assert builds == [2]


def test_verify_runs_inside_a_member_index_scope(tmp_path, monkeypatch):
    seen = []

    def run(*_a, **_k):
        seen.append(containment._MEMBER_INDEX_SCOPE.get() is not None)
        return verify_mod.VerifyResult()

    monkeypatch.setattr(verify_mod, "_verify_ledger", run)
    verify_mod.verify_ledger(tmp_path, None, {})
    assert seen == [True]
    assert containment._MEMBER_INDEX_SCOPE.get() is None
