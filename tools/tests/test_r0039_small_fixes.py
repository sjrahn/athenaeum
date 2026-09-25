"""The small tooling fixes folded into codex-steven R-0039 (2026-09-25), from the R-0035
photo-library passes:

1. an ffmpeg child never reads the caller's stdin (a `corpus resolve …&frame=` inside a
   shell `while read` loop ate the loop's input);
2. a `path=` refusal points at the raw spelling when the value carries percent escapes the
   URI grammar does not decode (spec §6.1 decodes only %25/%26/%23 — `%20` is literal);
3. the cached `?members` payload is keyed on the record's roster and sidecar declaration,
   so a `corpus reattest` (or an overlay edit) re-derives it;
6. `corpus contact-sheet --glob` matches case-insensitively (`*.mov` finds `IMG_1.MOV`).
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from corpus import contact_sheet as cs
from corpus import paths, records, resolver, tararchive, ziparchive
from corpus.transforms import video
from tests.test_contact_sheet_v45 import _MEMBERS
from tests.test_sidecar_lift import (
    _PHOTO_OVERLAY,
    _PHOTO_SUBTYPE_OVERLAY,
    _container,
    _corpus,
    _write_overlays,
)

# ---------- 1. ffmpeg never reads the caller's stdin ---------- #


def test_the_frame_grab_detaches_ffmpeg_from_stdin(tmp_path, monkeypatch):
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        Path(cmd[-1]).write_bytes(b"")  # no frame written: the op refuses, which is fine here
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(video.subprocess, "run", fake_run)
    with pytest.raises(video.FramePastEnd):
        video.frame(tmp_path / "clip.mp4", "1", {})
    assert seen["stdin"] is subprocess.DEVNULL


# ---------- 2. the %20 pointer ---------- #


def _zip(tmp_path: Path, names: list[str]) -> Path:
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for n in names:
            zf.writestr(n, b"x")
    return z


def _tar(tmp_path: Path, names: list[str]) -> Path:
    t = tmp_path / "a.tar"
    with tarfile.open(t, "w") as tf:
        for n in names:
            info = tarfile.TarInfo(n)
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
    return t


def test_a_url_encoded_member_path_is_pointed_at_its_raw_spelling(tmp_path):
    z = _zip(tmp_path, ["Trip Photos/IMG 1.MOV", "a&b.txt"])
    with pytest.raises(ziparchive.MemberMissing) as exc:
        ziparchive.resolve_member(z, "Trip%20Photos/IMG%201.MOV")
    msg = str(exc.value)
    assert "decodes only %25, %26 and %23" in msg
    assert "the member is `Trip Photos/IMG 1.MOV`" in msg
    assert "path=Trip Photos/IMG 1.MOV" in msg
    # the suggested spelling is itself a lawful value: a decoded `&` is re-escaped (the
    # parser already turned the caller's `%26` into `&`; `%2E` stayed literal)
    with pytest.raises(ziparchive.MemberMissing, match=r"path=a%26b\.txt"):
        ziparchive.resolve_member(z, "a&b%2Etxt")


def test_a_tar_member_gets_the_same_pointer(tmp_path):
    t = _tar(tmp_path, ["IMG 1.MOV"])
    with pytest.raises(tararchive.MemberMissing, match=r"the member is `IMG 1\.MOV`"):
        tararchive.resolve_member(t, "IMG%201.MOV")


def test_no_pointer_without_escapes_or_without_a_raw_match(tmp_path):
    z = _zip(tmp_path, ["IMG_1.MOV"])
    for rel in ("IMG_2.MOV", "IMG%202.MOV"):
        with pytest.raises(ziparchive.MemberMissing) as exc:
            ziparchive.resolve_member(z, rel)
        assert str(exc.value) == f"path={rel}: no such member in archive"


# ---------- 3. the members cache follows the record ---------- #


def test_a_reattested_roster_re_derives_the_members_payload(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    cid = _container(tmp_path, root, dict(_MEMBERS), "photo-export")
    first = resolver.resolve(f"corpus://{cid}?members", root)
    assert resolver.resolve(f"corpus://{cid}?members", root) == first  # unchanged: cached

    # what a reattest does when tooling re-types a member: the stored roster row changes
    rf = paths.record_path(root, cid)
    post = records.load(rf)
    row = next(e for e in records.iter_embed_blocks(post) if e["address"] == "path=notes.txt")
    row["media_type"] = "text/markdown"
    records.dump(post, rf)
    assert resolver.resolve(f"corpus://{cid}?members", root) != first


def test_an_edited_sidecar_declaration_re_derives_the_members_payload(tmp_path):
    root = _corpus(tmp_path, producer="photo")
    cid = _container(tmp_path, root, dict(_MEMBERS), "photo-export")
    first = resolver.resolve(f"corpus://{cid}?members", root)
    edited = _PHOTO_OVERLAY.replace("px_", "py_")
    assert edited != _PHOTO_OVERLAY
    _write_overlays(root, "photo-export", edited, "item", _PHOTO_SUBTYPE_OVERLAY)
    again = resolver.resolve(f"corpus://{cid}?members", root)
    assert again != first
    assert "py_uuid" in again.read_text("utf-8")


# ---------- 6. case-insensitive globs ---------- #


def test_the_glob_matches_whatever_case_the_producer_wrote():
    members = [
        {"address": "path=IMG_1.MOV", "media_type": "video/quicktime"},
        {"address": "path=img_2.mov", "media_type": "video/quicktime"},
        {"address": "path=IMG_3.HEIC", "media_type": "image/heic"},
    ]
    chosen, _ = cs.select(members, globs=["*.mov"])
    assert [m["address"] for m in chosen] == ["path=IMG_1.MOV", "path=img_2.mov"]
    chosen, _ = cs.select(members, globs=["img_[13].*"])
    assert [m["address"] for m in chosen] == ["path=IMG_1.MOV", "path=IMG_3.HEIC"]
