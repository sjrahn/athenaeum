"""The `framing:` stamp on a promoted track leaf (spec §7.2.1, 3.12).

3.12 admitted a muxer into the identity path. The stamp is the whole of what makes that
safe to live with: it names the producer, its version, the pinned flags, and a sample count
any consumer can re-derive without an engine. Without it a leaf is bytes with no account of
where they came from — which is exactly the state the superseded elementary rule was trying
to avoid by forbidding engines outright.

So these tests are about the stamp being *written and kept*, not about the mux itself
(`test_mux.py` owns that). The promote pass is the only place it can be written: a produced
file carries no record of its producer, and the containment origin is history rather than a
route back to one.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import pytest

from corpus import derive, hashing, paths, records, schemas, streams
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _container(tmp_path: Path, root: Path) -> tuple[str, Path]:
    """A 2s h264+aac mp4, ingested and attested — so its members roster names both tracks
    under the 3.12 pinned form and `promote` has real transports to verify against."""
    src = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(src),
        ],
        check=True, capture_output=True,
    )
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / src.name
    shutil.copy(src, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    cid = hashing.hash_file(src)["blake3"]
    post = records.load(paths.record_path(root, cid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, cid))
    return cid, src


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


def _leaf_for(root: Path, cid: str, address: str):
    """Promote `address` out of the container and return the minted leaf's post."""
    container = records.load(paths.record_path(root, cid))
    row = next(
        m for m in records.iter_embed_blocks(container)
        if address in (m.get("address") if isinstance(m.get("address"), list)
                       else [m.get("address")])
    )
    assert _promote(root, f"corpus://{cid}?{address}") == 0
    leaf_id = str(row["transport"]).split(":", 1)[1]
    return records.load(paths.record_path(root, leaf_id))


# ---------- the stamp is written ---------- #


def test_a_promoted_video_track_carries_the_framing_stamp(tmp_path):
    root = _corpus(tmp_path)
    cid, src = _container(tmp_path, root)

    stamp = records.framing(_leaf_for(root, cid, "stream_id=0"))

    assert stamp is not None, "a muxed leaf with no stamp is bytes with no account of them"
    assert stamp["muxer"] == "ffmpeg/lavf"
    assert stamp["flags"] == "bitexact"
    assert stamp["version"].count(".") == 2
    # The count is the stamp's whole point: checkable without the producer. `corpus.streams`
    # is the engine-free reader, so this is the consumer's check run at write time.
    assert stamp["samples"] == streams.sample_count(src, 0)


def test_a_promoted_audio_track_carries_it_too(tmp_path):
    """The audio path is a different muxer target (`.m4a`) and a different sample grain, so
    it is checked separately rather than assumed to follow from the video case."""
    root = _corpus(tmp_path)
    cid, src = _container(tmp_path, root)

    stamp = records.framing(_leaf_for(root, cid, "stream_id=1"))

    assert stamp is not None
    assert stamp["samples"] == streams.sample_count(src, 1)


def test_the_stamp_declares_framing_before_cutting(tmp_path):
    """§7.2.1 presents `framing:` (what produced the bytes) ahead of `cutting:` (a resolution
    computed over them). Key order is not cosmetic on a record format read as text: a diff of
    two leaves should line up top to bottom."""
    root = _corpus(tmp_path)
    cid, _ = _container(tmp_path, root)

    fields = (records.artifact_block(_leaf_for(root, cid, "stream_id=0")) or {}).get("fields")
    keys = [k for k in (fields or {}) if k in ("framing", "cutting")]
    assert keys[0] == "framing"


# ---------- the stamp is kept ---------- #


def test_the_stamp_survives_re_attestation(tmp_path):
    """`strip_attested_layer` rebuilds every byte-fact from the artifact — but this one it
    cannot rebuild, because produced bytes carry no record of their producer. Stripping it
    would silently delete the only account of what made the leaf, on a pass whose contract is
    that it changes nothing that re-derives identically."""
    root = _corpus(tmp_path)
    cid, _ = _container(tmp_path, root)
    leaf = _leaf_for(root, cid, "stream_id=0")
    before = records.framing(leaf)

    derive.strip_attested_layer(leaf)

    assert records.framing(leaf) == before


def test_a_re_promote_never_overwrites_an_existing_stamp(tmp_path):
    """Re-promoting folds rather than errors (§5.2), and the fold must not restamp. The
    record is content-addressed, so a re-derived stamp can only agree with the stored one or
    be wrong — and if it disagreed, overwriting is precisely the wrong response."""
    root = _corpus(tmp_path)
    cid, _ = _container(tmp_path, root)
    leaf = _leaf_for(root, cid, "stream_id=0")
    leaf_path = paths.record_path(root, str(leaf.metadata["id"]))

    doctored = dict(records.framing(leaf) or {})
    doctored["version"] = "1.2.3"
    promote_cli._stamp_artifact_field(leaf, "framing", doctored)
    records.dump(leaf, leaf_path)

    assert _promote(root, f"corpus://{cid}?stream_id=0") == 0
    assert records.framing(records.load(leaf_path))["version"] == "1.2.3"


# ---------- and only where it means something ---------- #


def test_a_non_track_member_carries_no_framing_stamp(tmp_path):
    """Absence is the honest answer for bytes no muxer produced. A stamp on a zip member
    would name a producer that never ran — worse than no stamp, because the count would
    invite a check that means nothing."""
    import zipfile

    root = _corpus(tmp_path)
    z = tmp_path / "b.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("note.txt", b"not a track\n")
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    shutil.copy(z, cap / z.name)
    assert ingest_cli._ingest_one(root, cap / z.name) == 0
    cid = hashing.hash_file(z)["blake3"]
    post = records.load(paths.record_path(root, cid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, cid))

    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    leaf_id = hashing.hash_bytes(b"not a track\n")["blake3"]
    assert records.framing(records.load(paths.record_path(root, leaf_id))) is None


# ---------- the stamp is checkable ---------- #
#
# Shape validation lives here rather than in `test_lint.py` because the rule exists only to
# protect the stamp minted above: a stamp that cannot be checked has failed at the one job
# 3.12 gave it.


def _framing_findings(root: Path, fields: dict) -> list:
    import frontmatter

    from corpus import lint, segments

    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "touch": "corpus.promote@0.1.0"})
    records.set_artifact_block(post, mime="video/mp4", fields=fields)
    records.append_origin_block(
        post, uri="corpus://" + "b" * 64 + "?stream_id=0", snapshot="2026-07-31T00:00:00Z"
    )
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root) if f.rule_id == "framing-stamp-malformed"]


_GOOD = {"muxer": "ffmpeg/lavf", "version": "62.12.102", "flags": "bitexact", "samples": 4539}


def test_an_absent_stamp_is_not_a_finding(tmp_path):
    """A leaf promoted before 3.12 is unresolved, not defective — the same rule `cutting:`
    sets. Flagging absence would turn a migration backlog into a fleet of errors.

    The well-formed case is asserted in the SAME test on purpose: a rule that fires on
    nothing passes an absence check trivially, so the two together are what show the rule
    is looking at the stamp rather than never firing at all."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    assert _framing_findings(root, {}) == []
    assert _framing_findings(root, {"framing": _GOOD}) == []


def test_a_stamp_without_a_sample_count_is_an_error(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    fields = {"framing": {k: v for k, v in _GOOD.items() if k != "samples"}}
    assert [f.rule_id for f in _framing_findings(root, fields)] == ["framing-stamp-malformed"]


def test_a_stamp_naming_no_producer_is_an_error(tmp_path):
    """Muxer and version both, because either alone leaves the bytes unexplainable: a version
    with no tool names nothing, and a tool with no version documents the past rather than
    constraining the present."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    for missing in ("muxer", "version"):
        fields = {"framing": {**_GOOD, missing: ""}}
        assert len(_framing_findings(root, fields)) == 1, missing


def test_a_nonsense_sample_count_is_an_error(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    for bad in ("lots", 0, -3):
        fields = {"framing": {**_GOOD, "samples": bad}}
        assert len(_framing_findings(root, fields)) == 1, bad
