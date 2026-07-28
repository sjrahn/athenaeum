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

import blake3
import frontmatter
import pytest

from corpus import hashing, paths, records, reseat, schemas, segments
from corpus.store import LocalArtifactStore

_PNG = base64.b64decode(
    # 1x1 transparent PNG
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAABfFcSJAAAADUlEQVR42mNk"
    "+M9QzwAEAAoAAv/lxKUAAAAASUVORK5CYII="
)
_PNG_HASH = blake3.blake3(_PNG).hexdigest()
_DATA_URI = "data:image/png;base64," + base64.b64encode(_PNG).decode()


def _doc(*, positions: int = 1) -> str:
    imgs = "".join(f'<p><img src="{_DATA_URI}" alt="fig {i}"></p>' for i in range(positions))
    return f"<html><head><title>Page - SITE</title></head><body><div>{imgs}</div></body></html>"


def _corpus(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _record(tmp_path, blocks, *, positions: int = 1, member_addresses=None):
    """A real HTML record whose artifact genuinely inlines the PNG, so the migration's
    blake3 verification is exercised rather than stubbed."""
    root = _corpus(tmp_path)
    src = root / "page.html"
    src.write_text(_doc(positions=positions), encoding="utf-8")
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


def test_a_bare_text_body_at_an_image_address_is_refused(tmp_path):
    """The most consequential refusal. Plain prose is not a rendering of pixels — on this
    fleet it is procedure text printed beside the figure and pinned to the figure's own
    address (#88, ~3,821 segments over 1,054 records). Migrating it would move an article's
    instructions onto a PNG and label them a transcription."""
    root, rf = _record(
        tmp_path,
        [
            segments.Segment(atom="image", address="el=1.1.1"),
            segments.Segment(
                atom="text",
                address="el=1.1.1",
                body="1. Grasp the console trim plate (2) and pull upward.",
            ),
        ],
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
