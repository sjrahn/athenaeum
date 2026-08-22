"""`corpus.continuity` — the content-continuity supersession check.

Builds real zip-manifest session records in a temp corpus and asserts the four member
verdicts (identical / contained / diverged / absent) and the `contains_a` bottom line that
gates `B supersedes A` and citation rewrites, plus the whole-artifact fallback for records
that are not container manifests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import frontmatter
import pytest

from corpus import ccsession, continuity, hashing, paths, records, schemas, streams
from corpus._cli import dispatch
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli


def _session_record(root: Path, projects: Path, sid: str, lines, *, subagents=None) -> str:
    proj = projects / "-p"
    proj.mkdir(parents=True, exist_ok=True)
    tr = proj / f"{sid}.jsonl"
    tr.write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    for name, recs in (subagents or {}).items():
        sub = proj / sid / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8"
        )
    sp = ccsession.find_session(str(tr))
    stats = ccsession.session_stats(sp)
    zip_path = root / "capture" / f"{sid}.zip"
    ccsession.build_bundle(
        ccsession.collect_members(sp), zip_path, comment=ccsession.bundle_comment(sp, stats)
    )
    rid = hashing.hash_file(zip_path, also=())["blake3"]
    ccsession.write_sidecar(
        zip_path,
        ccsession.origin_fields(sp, stats, captured_at="2026-01-01T00:00:00Z"),
        snapshot=stats.activity_end or "2026-01-01T00:00:00Z",
    )
    dispatch(["ingest", str(zip_path), "--corpus-root", str(root)])
    from tests._draftlib import draft_for_test
    draft_for_test(root, rid)
    return rid


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def test_identical_same_record(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    rid = _session_record(root, projects, "s", [{"type": "user", "i": 1}])
    cont = continuity.continuity(root, rid, rid)
    assert cont.contains_a
    assert cont.members[0].status == continuity.IDENTICAL


def test_contained_when_appended(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    base = [{"type": "user", "i": 1}, {"type": "assistant", "i": 2}]
    a = _session_record(root, projects, "s", base, subagents={"agent-x": [{"z": 1}]})
    grown = [*base, {"type": "user", "i": 3}]  # append-only growth
    b = _session_record(root, projects, "s", grown, subagents={"agent-x": [{"z": 1}]})
    cont = continuity.continuity(root, a, b)
    assert cont.contains_a
    statuses = {m.address: m.status for m in cont.members}
    assert statuses["path=s.jsonl"] == continuity.CONTAINED  # grew by append
    assert statuses["path=s/subagents/agent-x.jsonl"] == continuity.IDENTICAL  # unchanged


def test_diverged_when_rewritten(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    a = _session_record(root, projects, "s", [{"type": "user", "i": 1}])
    b = _session_record(root, projects, "s", [{"type": "user", "i": 999}])  # first line differs
    cont = continuity.continuity(root, a, b)
    assert not cont.contains_a
    assert cont.status_for("path=s.jsonl") == continuity.DIVERGED


def test_absent_when_member_dropped(tmp_path):
    root = _corpus(tmp_path)
    projects = tmp_path / "projects"
    line = [{"type": "user", "i": 1}]
    a = _session_record(root, projects, "s", line, subagents={"agent-x": [{"z": 1}]})
    # remove the subagent, keep the transcript identical
    import shutil

    shutil.rmtree(projects / "-p" / "s")
    b = _session_record(root, projects, "s", line)
    cont = continuity.continuity(root, a, b)
    assert not cont.contains_a
    assert cont.status_for("path=s/subagents/agent-x.jsonl") == continuity.ABSENT
    assert cont.status_for("path=s.jsonl") == continuity.IDENTICAL


def test_non_container_fallback(tmp_path):
    """Two records with no `path=` embeds never continue into each other unless identical —
    their whole-artifact identity is their id, which already differs."""
    import frontmatter

    from corpus import records

    root = _corpus(tmp_path)
    ids = ["aa" * 32, "bb" * 32]
    for rid in ids:
        post = frontmatter.Post(
            "", **records.stub_frontmatter(record_id=rid, touch_id="t@0.1.0")
        )
        rp = paths.record_path(root, rid)
        rp.parent.mkdir(parents=True, exist_ok=True)
        records.dump(post, rp)
    cont = continuity.continuity(root, ids[0], ids[1])
    assert not cont.contains_a
    assert cont.members and cont.members[0].status == continuity.DIVERGED


# ---------- (3.12) the media pair: continuity by SAMPLE SEQUENCE ---------- #
#
# The reason this branch exists: a record's identity is its artifact's blake3, so a track
# re-framed under a changed pinned form has a different id BY CONSTRUCTION. Comparing ids
# reports "diverged" for a supersession that is in fact exact — a gate that is always red,
# which is worse than none. What survives a reframe is the sample sequence.

_needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _media_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "m"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _mp4_container(
    tmp_path: Path, root: Path, name: str = "clip", *, freq: int = 440
) -> str:
    """A 2s h264+aac mp4, ingested and attested — two tracks, so a wrong pairing is visible.
    `freq` (the sine tone's frequency) exists so two calls can produce DISTINCT content —
    `testsrc2`/`sine` are otherwise fully deterministic (no wall-clock seed), so two
    same-params invocations hash identically regardless of filename."""
    src = tmp_path / f"{name}.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=15",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=44100",
         "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
        check=True, capture_output=True,
    )
    staged = root / "capture" / src.name
    staged.parent.mkdir(exist_ok=True)
    shutil.copy(src, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    cid = hashing.hash_file(src)["blake3"]
    post = records.load(paths.record_path(root, cid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, cid))
    return cid


def _promote(root: Path, cid: str, address: str) -> str:
    import argparse

    container = records.load(paths.record_path(root, cid))
    row = next(
        m for m in records.iter_embed_blocks(container)
        if address in (m.get("address") if isinstance(m.get("address"), list)
                       else [m.get("address")])
    )
    assert promote_cli.run(
        argparse.Namespace(uri=f"corpus://{cid}?{address}", json=False, corpus_root=str(root))
    ) == 0
    return str(row["transport"]).split(":", 1)[1]


@_needs_ffmpeg
def test_old_muxed_leaf_and_new_payload_leaf_are_sample_identical(tmp_path):
    """The v32 migration's own exactness proof (spec §12.8): re-running promote after v32
    mints a DIFFERENT leaf id for the same track (the identity basis changed from muxed
    envelope to raw payload), but the two leaves are two framings of the exact same
    samples — verified here as byte-different, sample-identical, exactly as the spec's
    migration narrative describes.

    The "old muxed leaf" is built directly with `corpus.mux` (rather than by running a
    pre-v32 checkout) — `mux_stream_to` IS the 3.12-through-v31 promoted-leaf producer,
    unchanged by v32 (it only lost its role as the identity path, not its behavior) — and
    planted as a STANDALONE artifact file under its own (muxed-bytes) id, simulating a
    leaf record minted before the migration whose bytes are still resident."""
    from corpus import mux

    root = _media_corpus(tmp_path)
    cid = _mp4_container(tmp_path, root)
    container_path = paths.artifact_path(root, cid, "mp4")

    old_dest = tmp_path / "old-leaf.mp4"
    mux.mux_stream_to(container_path, 0, old_dest)
    old_leaf_id = hashing.hash_file(old_dest)["blake3"]
    old_leaf_artifact = paths.artifact_path(root, old_leaf_id, "mp4")
    old_leaf_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(old_dest, old_leaf_artifact)
    old_post = frontmatter.Post("", **records.stub_frontmatter(
        record_id=old_leaf_id, touch_id="corpus.promote@0.1.0"
    ))
    records.set_artifact_block(old_post, mime="video/mp4", fields={})
    records.append_origin_block(
        old_post, uri=f"corpus://{cid}?stream_id=0", snapshot="2026-07-31T00:00:00Z"
    )
    records.dump(old_post, paths.record_path(root, old_leaf_id))

    new_leaf_id = _promote(root, cid, "stream_id=0")
    assert new_leaf_id != old_leaf_id, "same id proves nothing about the branch under test"

    result = continuity.continuity(root, old_leaf_id, new_leaf_id)

    assert [(m.address, m.status) for m in result.members] == [
        ("stream_id=0", continuity.IDENTICAL)
    ]
    assert result.contains_a


@_needs_ffmpeg
def test_a_promoted_leaf_preserves_its_container_track(tmp_path):
    """The check the 3.12 migration needed and did not have. The leaf's bytes differ from the
    container's entirely — different envelope, different id — and its SAMPLES are the same."""
    root = _media_corpus(tmp_path)
    cid = _mp4_container(tmp_path, root)
    leaf = _promote(root, cid, "stream_id=0")

    result = continuity.continuity(root, cid, leaf)

    assert result.contains_a
    assert [(m.address, m.status) for m in result.members] == [
        ("stream_id=0", continuity.IDENTICAL)
    ]


@_needs_ffmpeg
def test_the_track_compared_is_chosen_by_LINEAGE_not_by_position(tmp_path):
    """A leaf's own track 0 is its container's track 1 when the audio track is promoted.
    Pairing by index would compare the container's VIDEO against the leaf's AUDIO and report a
    sound migration as diverged — so the address must come from the containment origin."""
    root = _media_corpus(tmp_path)
    cid = _mp4_container(tmp_path, root)
    leaf = _promote(root, cid, "stream_id=1")

    result = continuity.continuity(root, cid, leaf)

    assert [m.address for m in result.members] == ["stream_id=1"], "paired by position"
    assert result.contains_a


@_needs_ffmpeg
def test_two_unrelated_tracks_diverge(tmp_path):
    """The negative control. Without it, every assertion above passes on a checker that
    returns IDENTICAL unconditionally."""
    root = _media_corpus(tmp_path)
    cid = _mp4_container(tmp_path, root)
    video = _promote(root, cid, "stream_id=0")
    audio = _promote(root, cid, "stream_id=1")

    result = continuity.continuity(root, video, audio)

    assert not result.contains_a
    assert result.diverged


@_needs_ffmpeg
def test_the_sample_sequence_is_what_survives_the_reframe(tmp_path):
    """The property the whole branch rests on, asserted directly rather than inferred from a
    verdict: re-enveloping a track moves every sample's file offset and changes no sample's
    size. If this ever stops holding, the verdicts above become meaningless while still
    passing.

    *(v32)* A promoted leaf's own bytes are the raw payload now — no envelope, no sample
    table of its own (§2) — so this asserts the property against `corpus.mux`'s DERIVED
    rendering instead (a single-track re-envelope of the same track), which is the
    reframe this branch actually has to survive when comparing a pre-v32 muxed leaf
    against its v32 payload successor."""
    from corpus import mux

    root = _media_corpus(tmp_path)
    cid = _mp4_container(tmp_path, root)
    container_bytes = paths.artifact_path(root, cid, "mp4")
    reframed = tmp_path / "reframed.mp4"
    mux.mux_stream_to(container_bytes, 0, reframed)

    assert reframed.read_bytes() != container_bytes.read_bytes(), "same bytes proves nothing"
    assert streams.sample_sizes(container_bytes, 0) == streams.sample_sizes(reframed, 0)


@_needs_ffmpeg
def test_growth_is_CONTAINED_not_diverged(monkeypatch, tmp_path):
    """A longer re-capture of the same recording extends the sequence rather than breaking it —
    the same meaning `CONTAINED` already carries for byte prefixes.

    B's sequence is lengthened at the seam rather than by building a second encode: provoking
    it for real would mean coaxing x264 into emitting an identical prefix for a longer input,
    which would test its lookahead rather than this comparison. Everything else — the record
    pair, the lineage pairing, the branch under test — is real.

    *(v32)* A and B are each a promoted leaf of a SEPARATE container (two independent
    captures), not container-vs-its-own-leaf: under the payload-identity principle a
    leaf's sample sequence is read straight from ITS OWN container's tables (§2 — the
    leaf carries none of its own), so a leaf promoted from A's own container and A itself
    would resolve to the identical (path, index) pair, leaving no separate "B" path to
    grow. Two distinct source containers keep that pair distinct, which is what the
    monkeypatch below needs to discriminate on. The AUDIO track (`stream_id=1`), not the
    video one: `testsrc2` is a fully deterministic pattern, so both clips' video payload
    is byte-identical regardless of `freq` and would mint the SAME leaf id either way —
    the varied sine tone is what actually makes the two captures distinct content.
    """
    root = _media_corpus(tmp_path)
    cid_a = _mp4_container(tmp_path, root, name="clip-a", freq=440)
    cid_b = _mp4_container(tmp_path, root, name="clip-b", freq=880)
    leaf_a = _promote(root, cid_a, "stream_id=1")
    leaf_b = _promote(root, cid_b, "stream_id=1")

    path_b = paths.artifact_path(root, cid_b, "mp4")
    seen: list[Path] = []

    # Fully fabricated, keyed on path identity — real() is deliberately NOT the baseline
    # here (unlike the pre-v32 version of this test): two genuinely different real audio
    # encodes (the only way to mint two DISTINCT leaf ids off two DISTINCT containers,
    # v32 §2) do not produce a real prefix relationship in their own sample sizes, so
    # asserting on real()-derived values would make this a test of x264/aac's internals
    # rather than of the continuity branch under test. B's sequence is A's, extended.
    def _sizes(path, stream_id):
        seen.append(Path(path))
        return [10, 20, 30, 5, 6, 7] if Path(path) == path_b else [10, 20, 30]

    monkeypatch.setattr(continuity.streams, "sample_sizes", _sizes)
    result = continuity.continuity(root, leaf_a, leaf_b)

    assert len(seen) == 2, "both sides must be read, or the verdict is about one sequence"
    assert path_b in seen, "B's sequence was never the one grown — the test proves nothing"
    assert [m.status for m in result.members] == [continuity.CONTAINED]
    assert result.contains_a, "growth preserves A — supersession stays safe"
