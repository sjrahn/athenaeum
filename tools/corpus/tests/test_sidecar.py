"""yt-dlp .info.json → record fields + caption/comment segments (draft/_sidecar)."""

from __future__ import annotations

import json
from typing import Any

from corpus.draft import _sidecar

_INFO: dict[str, Any] = {
    "title": "i'm trying to keep my cool #fyp #politics",
    "description": "i'm trying to keep my cool. but sometimes y'all make it hard. #fyp",
    "uploader": "comrade.killjoy",
    "channel": "comrade-killjoy",
    "upload_date": "20260402",
    "view_count": 33000,
    "like_count": 6398,
    "comment_count": 356,
    "repost_count": 361,
    "track": "original sound",
    "webpage_url": "https://www.tiktok.com/@comrade.killjoy/video/7624305653791739149",
    "comments": [
        {"id": "c1", "text": "first comment", "author": "alice", "like_count": 12},
        {"id": "c2", "text": "   ", "author": "spam"},  # blank → skipped
        {"text": "no id comment", "author": "bob"},
    ],
}


def test_map_info_fields_title_description_social():
    r = _sidecar._map_info(_INFO, _sidecar._SOCIAL_KEYS)
    assert r["title"].startswith("i'm trying")
    assert r["description"].startswith("i'm trying")
    social = r["fields"]["social"]
    assert social["uploader"] == "comrade.killjoy"
    assert social["view_count"] == 33000 and social["like_count"] == 6398
    assert social["track"] == "original sound"
    assert "artists" not in social  # absent keys are not emitted
    assert r["origin_aliases"] == [_INFO["webpage_url"]]


def test_map_info_caption_section_is_text_segment():
    r = _sidecar._map_info(_INFO, _sidecar._SOCIAL_KEYS)
    caps = r["caption_sections"]
    assert len(caps) == 1
    seg = caps[0].segments[0]
    assert seg.atom == "text" and seg.address == "sidecar=description"
    assert "keep my cool" in seg.body


def test_map_info_comment_segments_skip_blank_and_stay_unique():
    r = _sidecar._map_info(_INFO, _sidecar._SOCIAL_KEYS)
    comments = r["comment_sections"]
    assert len(comments) == 1
    segs = comments[0].segments
    assert len(segs) == 2  # the blank-text comment is skipped
    assert segs[0].body == "first comment"
    assert segs[0].extra["author"] == "alice" and segs[0].extra["like_count"] == 12
    assert segs[0].address != segs[1].address  # lint: (opener-id, address) unique


def test_parse_info_json_for_record_absent_is_empty(tmp_path):
    r = _sidecar.parse_info_json_for_record(tmp_path, "ab" + "0" * 62)
    assert r == _sidecar._empty()


def test_parse_info_json_for_record_reads_sidecar(tmp_path):
    rid = "de" + "0" * 62
    p = _sidecar.info_json_path(tmp_path, rid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_INFO), encoding="utf-8")
    r = _sidecar.parse_info_json_for_record(tmp_path, rid)
    assert r["title"].startswith("i'm trying")
    assert r["fields"]["social"]["uploader"] == "comrade.killjoy"


def test_info_json_path_is_in_capture_not_artifacts(tmp_path):
    p = _sidecar.info_json_path(tmp_path, "ab" + "0" * 62)
    assert p.parent.name == "capture" and "artifacts" not in p.parts


# ---------- schema-driven social keys ---------- #


def test_map_info_respects_provided_social_keys():
    # Only the passed keys land in `social:` — the mapping is the schema's, not hardcoded.
    r = _sidecar._map_info(_INFO, ("uploader", "view_count"))
    assert set(r["fields"]["social"]) == {"uploader", "view_count"}


def test_social_keys_for_reads_video_schema(tmp_path):
    # The packaged video mime schema declares extended_fields.social.sidecar_keys.
    keys = _sidecar._social_keys_for(tmp_path, {"_artifact": {"mime": "video/mp4"}})
    assert "uploader" in keys and "view_count" in keys and "artists" in keys


def test_social_keys_for_falls_back_when_no_schema_declaration(tmp_path):
    # No artifact / a mime whose schema declares no social.sidecar_keys → built-in default.
    assert _sidecar._social_keys_for(tmp_path, None) == _sidecar._SOCIAL_KEYS
    assert _sidecar._social_keys_for(tmp_path, {"_artifact": {"mime": "text/html"}}) == (
        _sidecar._SOCIAL_KEYS
    )


# ---------- enrichment-sidecar lifecycle ---------- #


def test_relocate_info_sidecar_renames_in_capture(tmp_path):
    from corpus._cli.ingest import _relocate_info_sidecar

    rid = "cd" + "0" * 62
    cap = tmp_path / "capture"
    cap.mkdir()
    (cap / "www.x.com-vid.info.json").write_text("{}", encoding="utf-8")
    _relocate_info_sidecar(cap / "www.x.com-vid.mp4", rid)
    assert (cap / f"{rid}.info.json").is_file()  # renamed, in capture/
    assert not (cap / "www.x.com-vid.info.json").exists()


def test_cleanup_enrichment_deletes_only_matching(tmp_path):
    from corpus._cli.draft import _cleanup_enrichment

    rid = "ef" + "0" * 62
    cap = tmp_path / "capture"
    cap.mkdir()
    (cap / f"{rid}.info.json").write_text("{}", encoding="utf-8")
    (cap / f"{rid}.comments.html").write_text("<x>", encoding="utf-8")
    keep = cap / "other-capture.mp4"
    keep.write_bytes(b"\x00")
    _cleanup_enrichment(tmp_path, rid)
    assert not (cap / f"{rid}.info.json").exists()
    assert not (cap / f"{rid}.comments.html").exists()
    assert keep.is_file()  # unrelated staging file untouched
