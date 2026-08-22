"""The §12.30 placement migration — `corpus.reseat` (ATH-CORPUS 3.8).

What these pin: the address algebra (a chained crop re-homes with the crop, a whole-frame crop
loses it, an unrecognized suffix refuses); the leaf shape (minted, its rendering at the
whole-transport address, formless on purpose); the parent shape (one placement per position,
marker and transcription collapsing to one); and every refusal, because the refusals are the
part that protects data — a bare `text` body at an image's address is #88's mis-addressed prose
and must never be migrated onto the image as if it were a transcription of the pixels.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from typing import Any

import blake3
import frontmatter
import pytest

from corpus import containment, hashing, paths, records, reseat, schemas, segments
from corpus.store import LocalArtifactStore

_PNG = base64.b64decode(
    # 1x1 transparent PNG
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAABfFcSJAAAADUlEQVR42mNk"
    "+M9QzwAEAAoAAv/lxKUAAAAASUVORK5CYII="
)
_PNG_HASH = blake3.blake3(_PNG).hexdigest()
_DATA_URI = "data:image/png;base64," + base64.b64encode(_PNG).decode()


def _doc(*, positions: int = 1, prose: str = "") -> str:
    imgs = "".join(f'<p><img src="{_DATA_URI}" alt="fig {i}"></p>' for i in range(positions))
    body = f"<div>{imgs}</div>"
    if prose:
        # Prose the DOCUMENT itself carries. What distinguishes the two populations that share
        # a member's address is whether the words are here or only in the pixels.
        body += f"<div>{prose}</div>"
    return f"<html><head><title>Page - SITE</title></head><body>{body}</body></html>"


def _corpus(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _record(tmp_path, blocks, *, positions: int = 1, member_addresses=None, prose: str = ""):
    """A real HTML record whose artifact genuinely inlines the PNG, so the migration's
    blake3 verification is exercised rather than stubbed."""
    root = _corpus(tmp_path)
    src = root / "page.html"
    src.write_text(_doc(positions=positions, prose=prose), encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post,
        mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": _element_count(src)}},
    )
    records.append_origin_block(post, uri="https://x.test/p", snapshot="2026-01-01T00:00:00Z")
    addrs = member_addresses or ["el=1.1.1"]
    records.append_member(
        post,
        media_type="image/png",
        address=addrs if len(addrs) > 1 else addrs[0],
        transport=f"blake3:{_PNG_HASH}",
        fields={"bytes": len(_PNG)},
    )
    post.content = segments.emit(blocks)
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    return root, rf


def _element_count(src):
    from bs4 import BeautifulSoup

    from corpus.transforms import html as html_tf

    soup = BeautifulSoup(src.read_bytes(), html_tf.EL_PARSER_ID)
    return html_tf.total_element_count(soup)


# ---------- the address algebra ---------- #


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("el=3", None),
        ("el=1.2.3", None),
        ("el=3&bbox=0,0,1,1", None),
        ("el=3&bbox=full", None),
        ("el=3&bbox=0.0,0.0,1.0,1.0", None),
        ("el=3&bbox=0,0.84,1,0.16", "bbox=0,0.84,1,0.16"),
        ("el=3&cover=0.9,0,0.1,0.3&bbox=0,0,0.28,1", "cover=0.9,0,0.1,0.3&bbox=0,0,0.28,1"),
        ("path=a/b.png", None),
    ],
)
def test_leaf_address_drops_the_container_prefix_and_the_fabricated_crop(addr, expected):
    """The `el=` prefix names the member inside its container and means nothing on the
    member's own record; the crop is already in fractions of the member's extent, so it
    carries over untouched. A whole-frame crop is not a region at all (§4.3.2.2) and takes
    the whole-transport address — which is no address."""
    assert reseat.leaf_address(addr) == expected


@pytest.mark.parametrize("suffix", ["region=banner", "part=2", "caption=after"])
def test_an_unrecognized_chained_suffix_refuses(suffix):
    """It meant something to whoever wrote it and nothing to the resolver; a migration may
    not guess. 16 public segments wear one."""
    with pytest.raises(reseat.ReseatHold):
        reseat.leaf_address(f"el=3&{suffix}")


# ---------- the happy path ---------- #


def test_a_transcription_moves_to_the_member_and_the_parent_places_it(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            segments.Section(
                form="document",
                segments=[
                    segments.Segment(atom="image", address="el=1.1.1"),
                    segments.Segment(
                        atom="text",
                        overlay="text/data-table",
                        address="el=1.1.1&bbox=0,0,1,1",
                        body="| a | b |\n|---|---|\n| 1 | 2 |",
                    ),
                ],
            )
        ],
    )
    report = reseat.reseat_record(rf, root)
    assert report.hold is None and report.changed, report.hold
    assert dict(report.counts) == {
        "members promoted": 1,
        "renderings re-seated": 1,
        "placements written": 1,
    }

    # The parent: marker AND transcription collapse to ONE placement, at the position.
    parent_blocks = segments.iter_blocks(
        records.loads(report.new_text).content  # type: ignore[arg-type]
    )
    kids = parent_blocks[0].segments
    assert [s.atom for s in kids] == ["placement"]
    assert kids[0].address == "el=1.1.1"

    # The leaf: minted at the member's blake3, formless, rendering at the WHOLE transport.
    (leaf,) = report.leaves
    assert leaf.record_id == _PNG_HASH and leaf.outcome == "minted" and leaf.address is None
    leaf_post = records.loads(leaf.new_text)
    assert records.media_type_for(leaf_post) == "image/png"
    assert f"corpus://{rf.stem}?el=1.1.1" in list(records.iter_origin_uris(leaf_post))
    (seg,) = segments.iter_blocks(leaf_post.content)
    assert seg.overlay == "text/data-table" and seg.address is None
    assert seg.body.strip().startswith("| a | b |")
    # The one-line bare opener is what an address-less segment serializes to (§4.3.2.2).
    assert "<!--segment text/data-table-->" in leaf_post.content


def test_a_marker_only_member_is_promoted_and_placed_with_nothing_moved(tmp_path):
    """Promotion follows PLACEMENT, not transcription: an unread member still gets a record,
    which is what carries its normalization pressure (§8.5)."""
    root, rf = _record(
        tmp_path,
        [segments.Segment(atom="image", address="el=1.1.1")],
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold
    (leaf,) = report.leaves
    assert leaf.outcome == "minted" and leaf.segments_moved == 0
    assert records.loads(leaf.new_text).content.strip() == ""


def test_a_genuine_sub_region_keeps_its_crop_on_the_leaf(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(
                atom="text",
                overlay="text/ocr",
                address="el=1.1.1&bbox=0,0.8,1,0.2",
                body="LEGEND",
            )
        ],
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold
    (seg,) = segments.iter_blocks(records.loads(report.leaves[0].new_text).content)
    assert seg.address == "bbox=0,0.8,1,0.2"


def test_one_member_at_two_positions_gets_two_placements_and_one_rendering(tmp_path):
    """The roster dedupes by transport, so two positions are one member — two placements on
    the parent (both positions are real) and ONE rendering on the leaf, because the two
    parent-side copies are the redundant work the amendment measures."""
    table = "| a |\n|---|\n| 1 |"
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(
                atom="text", overlay="text/data-table", address="el=1.1.1", body=table
            ),
            segments.Segment(
                atom="text", overlay="text/data-table", address="el=1.2.1", body=table
            ),
        ],
        positions=2,
        member_addresses=["el=1.1.1", "el=1.2.1"],
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold
    assert report.counts["placements written"] == 2
    assert report.counts["duplicate renderings collapsed"] == 1
    (seg,) = segments.iter_blocks(records.loads(report.leaves[0].new_text).content)
    assert seg.address is None


# ---------- the refusals ---------- #


_PROCEDURE = "1. Grasp the console trim plate (2) and pull upward."
_LEGEND = "Engine and Transmission Harness 3 of 9 - Engine Control Module 2 Connector A43-X2"


def test_prose_the_document_itself_carries_is_refused(tmp_path):
    """The consequential refusal, and it is now precise. This body's words are IN the page, so
    it is the article's own procedure text sitting on the figure's address because the
    paragraph had no element of its own (#88). Migrating it would move an article's
    instructions onto a PNG and label them a transcription of the pixels."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(atom="image", address="el=1.1.1"),
            segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
        ],
        prose=_PROCEDURE,
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "#88" in (report.hold or "")


def test_a_reading_of_the_pixels_is_re_seated(tmp_path):
    """The other half of the same population, and the one that was deadlocked. These words
    appear NOWHERE in the document — nobody could have written them without looking at the
    figure — so the body is a rendering of the member's bytes and belongs on the member's own
    record. Holding this too is what left 8,421 findings immovable: #88's remainder pointed at
    #101's arc and this verb pointed back at #88."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(atom="image", address="el=1.1.1"),
            segments.Segment(atom="text", address="el=1.1.1", body=_LEGEND),
        ],
        prose="Some unrelated paragraph the page actually prints.",
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold
    assert report.counts["pixel readings re-seated"] == 1
    (seg,) = segments.iter_blocks(records.loads(report.leaves[0].new_text).content)
    assert seg.body.strip() == _LEGEND
    # It renders the WHOLE member, so it carries no sub-address — never an invented crop.
    assert seg.address is None


def test_one_borrowed_body_holds_the_member_even_beside_a_genuine_reading(tmp_path):
    """The bias is deliberate and asymmetric. Wrongly moving prose displaces an article's
    content onto a PNG plausibly and permanently; wrongly leaving a transcription costs only
    that the record stays as it is today. So a single body found in the document refuses the
    member, even though the other body here is a sound reading of the pixels."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(atom="image", address="el=1.1.1"),
            segments.Segment(atom="text", address="el=1.1.1", body=_LEGEND),
            segments.Segment(atom="text", address="el=1.1.1", body=_PROCEDURE),
        ],
        prose=_PROCEDURE,
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "1 of 2" in (report.hold or "")


def test_a_body_too_short_to_judge_is_not_moved(tmp_path):
    """A two-word label is absent from the document for no informative reason. Absence only
    means something once there is enough text for its absence to be evidence, so the test
    declines rather than guessing in the direction that displaces content."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(atom="image", address="el=1.1.1"),
            segments.Segment(atom="text", address="el=1.1.1", body="Fig. 3"),
        ],
        prose="Some unrelated paragraph the page actually prints.",
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "#88" in (report.hold or "")


def test_two_parents_disagreeing_about_one_member_is_held(tmp_path):
    """Two readings of one set of bytes is a judgment, not a merge. Agreement is silent —
    that case is the dedup win, and it is the next test."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(
                atom="text", overlay="text/ocr", address="el=1.1.1", body="ONE READING"
            )
        ],
    )
    leaf = paths.record_path(root, _PNG_HASH)
    leaf.parent.mkdir(parents=True, exist_ok=True)
    other = frontmatter.Post("<!--segment text/ocr-->\n\nA DIFFERENT READING")
    other.metadata.update({"id": _PNG_HASH})
    records.set_artifact_block(other, mime="image/png", fields={})
    records.dump(other, leaf)

    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "DIFFERENT rendering" in (report.hold or "")


def test_two_parents_agreeing_is_the_dedup_win_and_writes_nothing_to_the_leaf(tmp_path):
    body = "ONE READING"
    root, rf = _record(
        tmp_path,
        [segments.Segment(atom="text", overlay="text/ocr", address="el=1.1.1", body=body)],
    )
    leaf = paths.record_path(root, _PNG_HASH)
    leaf.parent.mkdir(parents=True, exist_ok=True)
    other = frontmatter.Post(f"<!--segment text/ocr-->\n\n{body}")
    other.metadata.update({"id": _PNG_HASH})
    records.set_artifact_block(other, mime="image/png", fields={})
    records.dump(other, leaf)

    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold
    (written,) = report.leaves
    assert written.outcome == "already-rendered" and written.new_text is None
    assert report.counts["renderings already on the leaf"] == 1


def test_a_stale_roster_hash_refuses_rather_than_minting_a_wrong_id(tmp_path):
    """A promoted `id` that is not the member's true blake3 is unrecoverable (§8.1), so the
    hash is verified in the DRY RUN, before anything is written."""
    root, rf = _record(
        tmp_path, [segments.Segment(atom="image", address="el=1.1.1")]
    )
    post = records.load(rf)
    rows = post.metadata["_embeds"]
    rows[0]["transport"] = "blake3:" + "f" * 64
    records.dump(post, rf)

    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "refusing to mint a record with a wrong id" in (report.hold or "")


def test_a_record_with_no_placed_member_is_untouched(tmp_path):
    root, rf = _record(
        tmp_path,
        [segments.Segment(atom="text", address="el=1.2", body="prose at its own address")],
    )
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert report.skipped == "no member is marked or rendered on this record"


def test_the_sweep_is_idempotent(tmp_path):
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(
                atom="text", overlay="text/data-table", address="el=1.1.1", body="| a |\n|---|"
            )
        ],
    )
    first = reseat.reseat_record(rf, root)
    assert first.changed, first.hold
    rf.write_text(first.new_text, encoding="utf-8")
    for leaf in first.leaves:
        p = root / leaf.relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(leaf.new_text or "", encoding="utf-8")

    second = reseat.reseat_record(rf, root)
    assert second.changed is False
    assert second.skipped == "no member is marked or rendered on this record"


def test_a_multi_region_segment_naming_both_positions_of_one_member_reseats(tmp_path):
    """Two ADDRESSES are not two members — the roster dedupes by transport. Both positions
    get a placement (both are real occurrences in the document) and the one body lands once
    on the one leaf."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(
                atom="text",
                overlay="text/ocr",
                address=["el=1.1.1", "el=1.2.1"],
                body="spans both",
            )
        ],
        positions=2,
        member_addresses=["el=1.1.1", "el=1.2.1"],
    )
    report = reseat.reseat_record(rf, root)
    # One member at two addresses is not two members — the roster deduped them, so this is
    # the legitimate multi-region case and re-seats cleanly to one leaf.
    assert report.changed, report.hold
    assert report.counts["placements written"] == 2


# ---------- the legacy pre-#131 container-composition rendering ---------- #
#
# A manifest-disposition media container whose own body carries whisper `text/transcript`
# segments addressed on the container's own timeline (`time_range=…`) — not the audio
# member's address — interleaved with `image` frame markers, inside a `form/transcript`
# section carrying a `speakers:` codebook, plus a trailing sweep declaration. Real bytes, real
# streams: the blake3 verification is exercised rather than stubbed, exactly like the ordinary
# fixtures above.

_needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _media_corpus(tmp_path):
    root = tmp_path / "m"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _mp4_container_bytes(tmp_path, name: str = "clip"):
    """A 2s h264+aac mp4 — two streams, real enough for containment's own extraction."""
    src = tmp_path / f"{name}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src),
        ],
        check=True,
        capture_output=True,
    )
    return src


def _legacy_container_record(
    tmp_path,
    *,
    audio_streams: int = 1,
    include_audio: bool = True,
    include_transcript: bool = True,
    include_ocr: bool = False,
):
    root = _media_corpus(tmp_path)
    src = _mp4_container_bytes(tmp_path)
    cid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(cid, "mp4", src)
    artifact_path = paths.artifact_path(root, cid, "mp4")

    post = frontmatter.Post("")
    post.metadata.update({"id": cid, "transport": f"sha256:{'0' * 64}"})
    records.set_artifact_block(post, mime="video/mp4", fields={})
    records.append_origin_block(post, uri="file:///clip.mp4", snapshot="2026-01-01T00:00:00Z")

    with containment.open_member_stream(artifact_path, "video/mp4", "stream_id=0") as fp:
        video_raw = fp.read()
    video_hex = blake3.blake3(video_raw).hexdigest()
    records.append_member(
        post,
        media_type="video/mp4",
        address="stream_id=0",
        transport=f"blake3:{video_hex}",
        fields={"bytes": len(video_raw)},
    )

    audio_hex: str | None = None
    if include_audio:
        for i in range(audio_streams):
            addr = f"stream_id={i + 1}"
            if i == 0:
                with containment.open_member_stream(artifact_path, "video/mp4", addr) as fp:
                    audio_raw = fp.read()
                hexval = blake3.blake3(audio_raw).hexdigest()
                audio_hex = hexval
                nbytes = len(audio_raw)
            else:
                # A second candidate audio stream — the ambiguity holds before any bytes are
                # streamed, so fabricated bytes are fine here.
                hexval = "f" * 64
                nbytes = 1000
            records.append_member(
                post,
                media_type="audio/mp4",
                address=addr,
                transport=f"blake3:{hexval}",
                fields={"bytes": nbytes},
            )

    blocks: list[Any] = []
    if include_transcript:
        section_segments = [
            segments.Segment(atom="image", address="frame=00:00:01"),
            segments.Segment(
                atom="text",
                overlay="text/transcript",
                address="time_range=00:00-00:01",
                body="Hello there and welcome to the stream everyone",
                extra={"speaker": 0},
            ),
            segments.Segment(
                atom="text",
                overlay="text/transcript",
                address="time_range=00:01-00:02",
                body="This is the second utterance of the recording",
                extra={"speaker": 0},
            ),
        ]
        if include_ocr:
            # The shape a real record showed: an on-screen-text reading interleaved into the
            # SAME `form: transcript` section as the audio's own utterances — the section's
            # form belongs to the transcript, not to every kind that happens to sit inside it.
            section_segments.append(
                segments.Segment(
                    atom="text",
                    overlay="text/ocr",
                    address="frame=00:00:01",
                    body="ON SCREEN TEXT HERE",
                )
            )
        blocks.append(
            segments.Section(
                form="transcript",
                extra={"speakers": ["Speaker 1 diarization:1"]},
                segments=section_segments,
            )
        )
    post.content = segments.emit(blocks)
    if include_transcript:
        records.append_sweep_block(
            post,
            kind="text/transcript",
            detector="whisper-test@1",
            address="time_range=00:00-00:02",
        )
        if include_ocr:
            records.append_sweep_block(
                post,
                kind="text/ocr",
                detector="ocr-test@1",
                address="frame=00:00:01",
            )

    rf = paths.record_path(root, cid)
    records.dump(post, rf)
    return root, rf, audio_hex, video_hex


@_needs_ffmpeg
def test_legacy_container_transcript_is_destined_for_the_audio_leaf_not_skipped(tmp_path):
    """The bug: reseat used to report `skipped: "no member is marked or rendered..."` for this
    shape, even though `corpus lint`'s `container-carries-rendering` already names it. The
    default-member resolution the container's own `time_range=` addressing relies on (§6.2)
    picks the one audio stream member, and the dry run reports a real move, not a skip."""
    root, rf, audio_hex, _video_hex = _legacy_container_record(tmp_path)
    report = reseat.reseat_record(rf, root)
    assert report.hold is None, report.hold
    assert report.skipped is None
    assert report.changed is True
    (leaf,) = report.leaves
    assert leaf.record_id == audio_hex
    assert leaf.outcome == "minted"


@_needs_ffmpeg
def test_legacy_container_transcript_apply_moves_transcript_form_and_sweep_to_the_leaf(tmp_path):
    root, rf, audio_hex, _video_hex = _legacy_container_record(tmp_path)
    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold

    rf.write_text(report.new_text, encoding="utf-8")
    for leaf in report.leaves:
        p = root / leaf.relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(leaf.new_text or "", encoding="utf-8")

    # The leaf: the transcript's own form/section, its speakers codebook, both utterances at
    # their ORIGINAL time_range addresses (the leaf shares the container's timeline, §7.1), and
    # the sweep that vouched for their extraction.
    leaf_post = records.load(paths.record_path(root, audio_hex))
    assert records.media_type_for(leaf_post) == "audio/mp4"
    (section,) = segments.iter_blocks(leaf_post.content)
    assert section.form == "transcript"
    assert section.extra["speakers"] == ["Speaker 1 diarization:1"]
    assert [s.address for s in section.segments] == [
        "time_range=00:00-00:01",
        "time_range=00:01-00:02",
    ]
    assert section.segments[0].body.strip() == "Hello there and welcome to the stream everyone"
    assert section.segments[0].extra.get("speaker") == 0
    (sweep,) = records.iter_sweep_blocks(leaf_post)
    assert sweep["fields"]["kind"] == "text/transcript"
    assert sweep["fields"]["address"] == "time_range=00:00-00:02"
    assert sweep["fields"]["detector"] == "whisper-test@1"

    # The container: the image frame marker stays, the transcript collapses to ONE placement
    # at the audio member's own address, the form is dropped (nothing left for it to govern),
    # and its sweep declaration is gone — it moved with the rendering it vouched for.
    container_post = records.load(rf)
    (container_section,) = segments.iter_blocks(container_post.content)
    assert container_section.form is None
    assert [s.atom for s in container_section.segments] == ["image", "placement"]
    assert container_section.segments[1].address == "stream_id=1"
    assert list(records.iter_sweep_blocks(container_post)) == []


@_needs_ffmpeg
def test_ocr_sharing_the_transcript_section_seats_bare_not_wrapped_in_transcript_form(tmp_path):
    """Regression: a container that ALSO carries a `text/ocr` reading inside the same
    `form: transcript` section as the audio's utterances (a real shape — the video track's
    on-screen text interleaved beside the audio's speech) must not stamp `form: transcript`
    on the video leaf. A section's form belongs to the kind it was written to describe, not
    to every kind that happens to share its span — the audio leaf keeps the form (its own),
    the video leaf gets its ocr reading bare, exactly like the ordinary (non-legacy)
    association has always produced a leaf's rendering."""
    root, rf, audio_hex, video_hex = _legacy_container_record(tmp_path, include_ocr=True)
    report = reseat.reseat_record(rf, root)
    assert report.changed, report.hold
    rf.write_text(report.new_text, encoding="utf-8")

    leaves_by_hex = {leaf.record_id: leaf for leaf in report.leaves}

    video_post = records.loads(leaves_by_hex[video_hex].new_text)
    (ocr_seg,) = segments.iter_blocks(video_post.content)
    assert isinstance(ocr_seg, segments.Segment), "the video leaf must NOT gain a Section"
    assert ocr_seg.overlay == "text/ocr"
    assert ocr_seg.address == "frame=00:00:01"
    assert ocr_seg.body.strip() == "ON SCREEN TEXT HERE"

    audio_post = records.loads(leaves_by_hex[audio_hex].new_text)
    (audio_section,) = segments.iter_blocks(audio_post.content)
    assert audio_section.form == "transcript"
    assert audio_section.extra["speakers"] == ["Speaker 1 diarization:1"]
    assert [s.overlay for s in audio_section.segments] == ["text/transcript", "text/transcript"]

    # The ocr sweep travels to the video leaf, the transcript sweep to the audio leaf — each
    # by its own kind, never cross-wired.
    (video_sweep,) = records.iter_sweep_blocks(video_post)
    assert video_sweep["fields"]["kind"] == "text/ocr"
    (audio_sweep,) = records.iter_sweep_blocks(audio_post)
    assert audio_sweep["fields"]["kind"] == "text/transcript"

    container_post = records.load(rf)
    assert list(records.iter_sweep_blocks(container_post)) == []


@_needs_ffmpeg
def test_two_candidate_audio_streams_holds_no_writes(tmp_path):
    root, rf, _audio_hex, _video_hex = _legacy_container_record(tmp_path, audio_streams=2)
    before = rf.read_text(encoding="utf-8")
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "2 audio stream members" in (report.hold or "")
    assert rf.read_text(encoding="utf-8") == before


@_needs_ffmpeg
def test_zero_candidate_audio_streams_holds(tmp_path):
    root, rf, _audio_hex, _video_hex = _legacy_container_record(tmp_path, include_audio=False)
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert "no audio stream member" in (report.hold or "")


@_needs_ffmpeg
def test_a_manifest_container_with_nothing_to_move_still_skips(tmp_path):
    """The old genuinely-nothing-to-do case, unaffected: a manifest container carrying no
    legacy rendering is untouched exactly as before, `disposition: manifest` notwithstanding."""
    root, rf, _audio_hex, _video_hex = _legacy_container_record(tmp_path, include_transcript=False)
    report = reseat.reseat_record(rf, root)
    assert report.changed is False
    assert report.skipped == "no member is marked or rendered on this record"
