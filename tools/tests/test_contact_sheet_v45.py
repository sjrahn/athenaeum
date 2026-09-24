"""`corpus contact-sheet` — a labelled grid over a container's image members (spec §12.9.3,
v45; codex-steven R-0037). An instrument: selection runs over the `members` descriptors
(which carry a declared sidecar's lifted fields), each tile is the frame's own
`auto_orient&fit` rendering, and the legend names every tile's member address."""

from __future__ import annotations

import argparse
import io
import json

import pytest
from PIL import Image

from corpus import contact_sheet as cs
from corpus import paths
from corpus._cli import contact_sheet as cs_cli
from corpus._cli import reattest as reattest_cli
from tests.test_sidecar_lift import _PHOTO_MEMBERS, _container, _corpus


def _jpeg(size, colour) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="JPEG")
    return buf.getvalue()


_MEMBERS = {
    **_PHOTO_MEMBERS,  # IMG_0001.HEIC is a real (PNG) image; IMG_0002.HEIC is not decodable
    "IMG_0003.JPG": _jpeg((40, 20), (0, 90, 200)),
    "IMG_0003.JPG.json": json.dumps(
        {"uuid": "0003", "date_original": "2024-12-24T20:00:00-07:00", "persons": ["Bob"]}
    ).encode(),
    "clip.mov": b"not really a movie\n",
}


@pytest.fixture
def box(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    cid = _container(tmp_path, root, _MEMBERS, "photo-export")
    rf = paths.record_path(root, cid)
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")
    return root, cid


# ---------- selection ---------- #


@pytest.mark.parametrize(
    ("expr", "want"),
    [
        ("px_persons~ali", ("px_persons", "~", "ali")),
        ("px_kind!~screenshot", ("px_kind", "!~", "screenshot")),
        ("px_taken>=2024-12-24", ("px_taken", ">=", "2024-12-24")),
        ("px_taken<=2025-01-01", ("px_taken", "<=", "2025-01-01")),
        ("bytes!=0", ("bytes", "!=", "0")),
        ("px_uuid=0001-UUID", ("px_uuid", "=", "0001-UUID")),
    ],
)
def test_parse_where(expr, want):
    p = cs.parse_where(expr)
    assert (p.field, p.op, p.value) == want


@pytest.mark.parametrize("expr", ["nooperator", "=value", "~x"])
def test_parse_where_rejects(expr):
    with pytest.raises(cs.SheetError):
        cs.parse_where(expr)


def test_matches_semantics():
    m = {
        "px_persons": ["Alice", "Bob"],
        "px_taken": "2024-12-24T23:30:00-07:00",
        "bytes": 1200,
    }
    assert cs.matches(m, cs.parse_where("px_persons~ALI"))
    assert not cs.matches(m, cs.parse_where("px_persons!~bob"))
    assert cs.matches(m, cs.parse_where("px_kind!~screenshot"))  # absent field lacks it
    assert not cs.matches(m, cs.parse_where("px_kind~screenshot"))
    # a date bound compares on the value's own face: 23:30 local on the 24th is the 24th
    assert cs.matches(m, cs.parse_where("px_taken<=2024-12-24T23:59"))
    assert not cs.matches(m, cs.parse_where("px_taken>=2024-12-25"))
    assert cs.matches(m, cs.parse_where("bytes>=1000"))  # numbers compare as numbers
    assert not cs.matches(m, cs.parse_where("bytes<=999"))


def test_select_discloses_what_it_passes_over_and_sorts_absent_last():
    members = [
        {"address": "path=a.jpg", "media_type": "image/jpeg", "d": "2025-01-02"},
        {"address": "path=b.mov", "media_type": "video/quicktime"},
        {"address": "path=c.jpg", "media_type": "image/jpeg"},
        {"address": "path=d.jpg", "media_type": "image/jpeg", "d": "2024-01-01"},
        {"address": "path=e.txt", "media_type": "text/plain"},
    ]
    chosen, skipped = cs.select(members, sort="d")
    # v46: a video is tiled (by one still), sorted like any member
    assert [m["address"] for m in chosen] == [
        "path=d.jpg", "path=a.jpg", "path=b.mov", "path=c.jpg"
    ]
    assert skipped == {"other": 1}
    chosen, skipped = cs.select(members, sort="d", video=False)
    assert [m["address"] for m in chosen] == ["path=d.jpg", "path=a.jpg", "path=c.jpg"]
    assert skipped == {"video": 1, "other": 1}
    chosen, _ = cs.select(members, globs=["[ab]*"])
    assert [m["address"] for m in chosen] == ["path=a.jpg", "path=b.mov"]


# ---------- the sheet ---------- #


def test_sheet_tiles_every_image_frame_and_marks_the_unreadable(box):
    root, cid = box
    sheet = cs.build(root, cid, labels=["px_uuid"], columns=3, rows=2, tile=64)
    legend = sheet.legend
    addrs = [t["address"] for t in legend["tiles"]]
    # roster order; the sidecars are not members, notes.txt is not a frame, and
    # IMG_0001.mov is IMG_0001.HEIC's live twin (its sidecar names it) — a companion
    assert addrs == [
        "path=IMG_0001.HEIC",
        "path=IMG_0001_edited.jpeg",
        "path=IMG_0002.HEIC",
        "path=IMG_0003.JPG",
        "path=clip.mov",
    ]
    assert legend["pages"] == 1 and legend["selected"] == 5
    assert legend["skipped"] == {"other": 1, "companion": 1}
    clip = legend["tiles"][-1]
    assert clip["video"] is True and "error" in clip  # not a real movie: a marked tile
    assert legend["class"] == "instrument" and legend["engine"] == cs.ENGINE_VERSION
    by = {t["address"]: t for t in legend["tiles"]}
    assert by["path=IMG_0001.HEIC"]["labels"] == {"px_uuid": "0001-UUID"}
    assert "error" in by["path=IMG_0002.HEIC"]  # a marked tile, never a lost sheet
    assert "error" not in by["path=IMG_0003.JPG"]
    with Image.open(sheet.path) as im:
        assert im.size == tuple(legend["size"])
    # cached: the same selection is the same file, served without re-rendering
    again = cs.build(root, cid, labels=["px_uuid"], columns=3, rows=2, tile=64)
    assert again.cached and again.path == sheet.path


def test_sheet_selects_on_the_frames_lifted_sidecar_fields(box):
    root, cid = box
    sheet = cs.build(root, cid, where=[cs.parse_where("px_persons~bob")], tile=64)
    assert [t["address"] for t in sheet.legend["tiles"]] == ["path=IMG_0003.JPG"]
    sheet = cs.build(
        root, cid, where=[cs.parse_where("px_taken>=2025-01-01")], sort="px_taken", tile=64
    )
    assert [t["address"] for t in sheet.legend["tiles"]] == [
        "path=IMG_0002.HEIC",
        "path=IMG_0001.HEIC",
    ]


def test_pages_walk_a_long_sequence(box):
    root, cid = box
    p2 = cs.build(root, cid, columns=1, rows=3, tile=48, page=2)
    assert [t["n"] for t in p2.legend["tiles"]] == [4, 5]
    assert p2.legend["pages"] == 2
    with pytest.raises(cs.SheetError, match="past the end"):
        cs.build(root, cid, columns=1, rows=3, tile=48, page=3)


def test_no_match_is_an_error_not_an_empty_sheet(box):
    root, cid = box
    with pytest.raises(cs.SheetError, match="no image or video member"):
        cs.build(root, cid, globs=["nothing*"], tile=64)


def test_cli_prints_path_summary_and_legend(box, capsys):
    root, cid = box
    ns = argparse.Namespace(
        container=f"corpus://{cid}",
        glob=["IMG_0003*"],
        where=[],
        sort=None,
        label=["px_persons"],
        page=1,
        columns=5,
        rows=4,
        tile=64,
        video_at=cs.DEFAULT_VIDEO_AT,
        no_video=False,
        full=False,
        jobs=1,
        regenerate=False,
        json=False,
        corpus_root=str(root),
    )
    assert cs_cli.run(ns) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].endswith(".png")
    assert out[1].startswith("sheet 1/1 · 1 of 1 selected member(s)")
    assert out[2].split() == ["1", "path=IMG_0003.JPG", "px_persons=Bob"]


def test_cli_refuses_a_uri_with_params(box, capsys):
    root, cid = box
    ns = argparse.Namespace(
        container=f"corpus://{cid}?path=IMG_0003.JPG",
        glob=[],
        where=[],
        sort=None,
        label=[],
        page=1,
        columns=5,
        rows=4,
        tile=64,
        video_at=cs.DEFAULT_VIDEO_AT,
        no_video=False,
        full=False,
        jobs=1,
        regenerate=False,
        json=False,
        corpus_root=str(root),
    )
    assert cs_cli.run(ns) == 2
    assert "give the container itself" in capsys.readouterr().err


# ---------- video tiles (v46) ---------- #


def _mp4(seconds: float = 2.0) -> bytes:
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    with tempfile.TemporaryDirectory() as d:
        out = f"{d}/c.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             f"color=c=red:s=32x24:d={seconds}", "-pix_fmt", "yuv420p", out],
            check=True,
        )
        with open(out, "rb") as fh:
            return fh.read()


def test_a_video_member_is_tiled_by_one_badged_still(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    cid = _container(
        tmp_path, root, {"long.mp4": _mp4(2.0), "short.mp4": _mp4(0.4)}, "photo-export"
    )
    sheet = cs.build(root, cid, tile=64)
    by = {t["address"]: t for t in sheet.legend["tiles"]}
    assert by["path=long.mp4"] == {
        "n": 1, "address": "path=long.mp4", "labels": {}, "video": True, "frame": "1"
    }
    # shorter than the sheet's instant: its first frame, recorded as such
    assert by["path=short.mp4"]["frame"] == "0" and "error" not in by["path=short.mp4"]
    assert sheet.legend["selection"]["video"] == "1"
    at5 = cs.build(root, cid, tile=64, video_at="0.2")
    assert at5.path != sheet.path  # the instant is part of the selection key
    assert {t["frame"] for t in at5.legend["tiles"]} == {"0.2"}
