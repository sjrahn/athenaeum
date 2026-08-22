"""The `samples:` stamp on a promoted track leaf (spec §7.1, v32) — and the retired
`framing:` stamp it replaces.

Through 3.12 to v31 a promoted leaf's bytes were muxed by an engine, and the `framing:` stamp
was the whole compensating control: it named the producer, its version, and a sample count
any consumer could re-derive without an engine. v32's payload-identity principle (§2)
removed the engine from the identity path entirely — a leaf's bytes are now a table-driven
sample concatenation with no producer to attest — so there is nothing left to name a muxer
or version for. What survives is the count itself: a leaf's artifact block may attest
`samples:` (a bare int, not a stamp-shaped dict), the same self-check `cutting:` and stored
markers compare against, computed by `corpus.streams`'s own engine-free reader.

So these tests are about `samples:` being *written and kept*, plus the retired `framing:`
stamp's new, downgraded lint treatment (pre-v32 history, `info` only — never an error). The
promote pass is the only place `samples:` can be written: the leaf's own bytes carry no
record of a count, and the containment origin is history rather than a route back to one.
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
    and `promote` has real transports to verify against."""
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


def test_a_promoted_video_track_carries_the_samples_stamp(tmp_path):
    root = _corpus(tmp_path)
    cid, src = _container(tmp_path, root)

    n = records.samples(_leaf_for(root, cid, "stream_id=0"))

    assert n is not None, "a promoted leaf with no count is bytes with no self-check"
    # The count is the stamp's whole point: checkable without a producer. `corpus.streams`
    # is the engine-free reader, so this is the consumer's check run at write time.
    assert n == streams.sample_count(src, 0)


def test_a_promoted_audio_track_carries_it_too(tmp_path):
    """The audio track has a different sample grain, so it is checked separately rather
    than assumed to follow from the video case."""
    root = _corpus(tmp_path)
    cid, src = _container(tmp_path, root)

    n = records.samples(_leaf_for(root, cid, "stream_id=1"))

    assert n is not None
    assert n == streams.sample_count(src, 1)


def test_no_framing_stamp_is_written_anymore(tmp_path):
    """The retired stamp's whole reason to exist — a producer to attest — is gone at v32
    (§2): a NEWLY promoted leaf never carries one, even though the field name is still
    read (as pre-v32 history) by `records.framing`/lint."""
    root = _corpus(tmp_path)
    cid, _ = _container(tmp_path, root)

    assert records.framing(_leaf_for(root, cid, "stream_id=0")) is None


# ---------- the stamp is kept ---------- #


def test_the_stamp_survives_re_attestation(tmp_path):
    """`strip_attested_layer` rebuilds every byte-fact from the artifact — but this one it
    cannot rebuild, because a bare payload leaf carries no record of its own count.
    Stripping it would silently delete the only self-check the leaf has, on a pass whose
    contract is that it changes nothing that re-derives identically."""
    root = _corpus(tmp_path)
    cid, _ = _container(tmp_path, root)
    leaf = _leaf_for(root, cid, "stream_id=0")
    before = records.samples(leaf)

    derive.strip_attested_layer(leaf)

    assert records.samples(leaf) == before


def test_a_re_promote_never_overwrites_an_existing_stamp(tmp_path):
    """Re-promoting folds rather than errors (§5.2), and the fold must not restamp. The
    record is content-addressed, so a re-derived count can only agree with the stored one
    or be wrong — and if it disagreed, overwriting is precisely the wrong response."""
    root = _corpus(tmp_path)
    cid, _ = _container(tmp_path, root)
    leaf = _leaf_for(root, cid, "stream_id=0")
    leaf_path = paths.record_path(root, str(leaf.metadata["id"]))

    doctored = (records.samples(leaf) or 0) + 999
    promote_cli._stamp_artifact_field(leaf, "samples", doctored)
    records.dump(leaf, leaf_path)

    assert _promote(root, f"corpus://{cid}?stream_id=0") == 0
    assert records.samples(records.load(leaf_path)) == doctored


# ---------- and only where it means something ---------- #


def test_a_non_track_member_carries_no_samples_stamp(tmp_path):
    """Absence is the honest answer for bytes with no sample table to read. A stamp on a
    zip member would name a count nothing computed — worse than no stamp, because it
    would invite a check that means nothing."""
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
    assert records.samples(records.load(paths.record_path(root, leaf_id))) is None


# ---------- the stamp is checkable (lint) ---------- #
#
# Shape validation lives here rather than in `test_lint.py` because the rule exists only to
# protect the stamp minted above: a stamp that cannot be checked has failed at the one job
# it's given.


def _findings(root: Path, fields: dict, *, mime: str = "video/h264") -> list:
    import frontmatter

    from corpus import lint, segments

    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "touch": "corpus.promote@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields=fields)
    records.append_origin_block(
        post, uri="corpus://" + "b" * 64 + "?stream_id=0", snapshot="2026-07-31T00:00:00Z"
    )
    blocks = segments.iter_blocks(post.content or "")
    return list(lint.lint(post, blocks, root))


def _by_rule(findings: list, rule_id: str) -> list:
    return [f for f in findings if f.rule_id == rule_id]


def test_an_absent_samples_stamp_is_not_a_finding(tmp_path):
    """A leaf whose count could not be resolved at promote time is unresolved, not
    defective — the same rule `cutting:` sets."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    assert _by_rule(_findings(root, {}), "samples-stamp-malformed") == []
    assert _by_rule(_findings(root, {"samples": 4539}), "samples-stamp-malformed") == []


def test_a_nonsense_samples_stamp_is_an_error(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    for bad in ("lots", 0, -3):
        findings = _by_rule(_findings(root, {"samples": bad}), "samples-stamp-malformed")
        assert len(findings) == 1, bad
        assert findings[0].severity == "error"


_OLD_FRAMING = {
    "muxer": "ffmpeg/lavf", "version": "62.12.102", "flags": "bitexact", "samples": 4539,
}


def test_a_surviving_pre_v32_framing_stamp_is_history_not_an_error(tmp_path):
    """A `framing:` stamp on a pre-v32 leaf is honest history of the bytes it described,
    never a defect (spec §7.1) — so even a MALFORMED one (missing its producer) reports
    only at `info`, never `error`. Nothing new writes this field; lint's job on it is
    purely legibility, not enforcement."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    mime = "video/mp4"  # the pre-v32 leaf's own container-kind mime

    well_formed = _by_rule(
        _findings(root, {"framing": _OLD_FRAMING}, mime=mime), "framing-stamp-malformed"
    )
    assert well_formed == []

    malformed = _by_rule(
        _findings(root, {"framing": {**_OLD_FRAMING, "muxer": ""}}, mime=mime),
        "framing-stamp-malformed",
    )
    assert len(malformed) == 1
    assert malformed[0].severity == "info"
