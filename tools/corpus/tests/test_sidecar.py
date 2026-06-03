"""yt-dlp .info.json → `ytdlp_*` origin-block fields (draft/_sidecar + the placement)."""

from __future__ import annotations

import json
from typing import Any

import frontmatter

from corpus import records
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


def test_map_info_lifts_keys_to_flat_ytdlp_fields():
    r = _sidecar._map_info(_INFO, _sidecar._YTDLP_KEYS)
    f = r["origin_fields"]
    # Every present key becomes a flat `ytdlp_<key>` field — incl. title/description.
    assert f["ytdlp_title"].startswith("i'm trying")
    assert f["ytdlp_description"].startswith("i'm trying")
    assert f["ytdlp_uploader"] == "comrade.killjoy"
    assert f["ytdlp_view_count"] == 33000 and f["ytdlp_like_count"] == 6398
    assert f["ytdlp_track"] == "original sound"
    assert "ytdlp_artists" not in f  # absent keys are not emitted
    assert r["origin_aliases"] == [_INFO["webpage_url"]]


def test_map_info_produces_no_body_segments():
    # Nothing from the (non-primary) sidecar goes to the body — origin fields + aliases only.
    r = _sidecar._map_info(_INFO, _sidecar._YTDLP_KEYS)
    assert set(r) == {"origin_fields", "origin_aliases"}


def test_map_info_comments_become_ytdlp_comments_list():
    r = _sidecar._map_info(_INFO, _sidecar._YTDLP_KEYS)
    comments = r["origin_fields"]["ytdlp_comments"]
    assert len(comments) == 2  # the blank-text comment is skipped
    assert comments[0]["text"] == "first comment"
    assert comments[0]["author"] == "alice" and comments[0]["like_count"] == 12
    assert comments[1]["text"] == "no id comment"


def test_map_info_no_comments_omits_field():
    info = {k: v for k, v in _INFO.items() if k != "comments"}
    r = _sidecar._map_info(info, _sidecar._YTDLP_KEYS)
    assert "ytdlp_comments" not in r["origin_fields"]


def test_parse_info_json_for_record_absent_is_empty(tmp_path):
    r = _sidecar.parse_info_json_for_record(tmp_path, "ab" + "0" * 62)
    assert r == _sidecar._empty()


def test_parse_info_json_for_record_reads_sidecar(tmp_path):
    rid = "de" + "0" * 62
    p = _sidecar.info_json_path(tmp_path, rid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_INFO), encoding="utf-8")
    r = _sidecar.parse_info_json_for_record(tmp_path, rid)
    assert r["origin_fields"]["ytdlp_title"].startswith("i'm trying")
    assert r["origin_fields"]["ytdlp_uploader"] == "comrade.killjoy"


def test_info_json_path_is_in_capture_not_artifacts(tmp_path):
    p = _sidecar.info_json_path(tmp_path, "ab" + "0" * 62)
    assert p.parent.name == "capture" and "artifacts" not in p.parts


# ---------- chapters (structural → sectioning, not a flat origin field) ---------- #


def test_chapters_validates_and_shapes():
    raw = [
        {"start_time": 0.0, "end_time": 16.0, "title": "Introduction"},
        {"start_time": 16.0, "end_time": 61.0, "title": "  Compiler ABI  "},  # title trimmed
        {"start_time": 61.0, "title": "No end is fine"},  # end_time optional
        {"title": "no start → dropped"},
        {"start_time": 99.0, "title": "   "},  # blank title → dropped
        "not a dict",
    ]
    assert _sidecar._chapters(raw) == [
        {"start": 0.0, "title": "Introduction", "end": 16.0},
        {"start": 16.0, "title": "Compiler ABI", "end": 61.0},
        {"start": 61.0, "title": "No end is fine"},
    ]


def test_chapters_absent_or_malformed_is_none():
    assert _sidecar._chapters(None) is None
    assert _sidecar._chapters([]) is None
    assert _sidecar._chapters("nope") is None
    assert _sidecar._chapters([{"start_time": 0}]) is None  # no title → all dropped → None


def test_parse_info_json_surfaces_chapters_not_as_origin_field(tmp_path):
    rid = "f0" + "0" * 62
    p = _sidecar.info_json_path(tmp_path, rid)
    p.parent.mkdir(parents=True, exist_ok=True)
    info = dict(_INFO, chapters=[{"start_time": 0.0, "end_time": 5.0, "title": "A"}])
    p.write_text(json.dumps(info), encoding="utf-8")
    r = _sidecar.parse_info_json_for_record(tmp_path, rid)
    assert r["chapters"] == [{"start": 0.0, "title": "A", "end": 5.0}]
    # Chapters are structural (→ section boundaries/entries), never a flat origin field.
    assert "ytdlp_chapters" not in r["origin_fields"]


def test_parse_info_json_no_chapters_is_none(tmp_path):
    rid = "f1" + "0" * 62
    p = _sidecar.info_json_path(tmp_path, rid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_INFO), encoding="utf-8")  # _INFO has no chapters
    assert _sidecar.parse_info_json_for_record(tmp_path, rid)["chapters"] is None


# ---------- schema-driven ytdlp keys ---------- #


def test_map_info_respects_provided_keys():
    # Only the passed keys are lifted — the mapping is the schema's, not hardcoded.
    r = _sidecar._map_info(_INFO, ("uploader", "view_count"))
    assert set(r["origin_fields"]) == {"ytdlp_uploader", "ytdlp_view_count", "ytdlp_comments"}


def test_ytdlp_keys_for_reads_video_schema(tmp_path):
    # The packaged video mime schema declares sidecar.ytdlp_keys.
    keys = _sidecar._ytdlp_keys_for(tmp_path, {"_artifact": {"mime": "video/mp4"}})
    assert "title" in keys and "uploader" in keys and "artists" in keys


def test_ytdlp_keys_for_falls_back_when_no_schema_declaration(tmp_path):
    # No artifact / a mime whose schema declares no sidecar.ytdlp_keys → built-in default.
    assert _sidecar._ytdlp_keys_for(tmp_path, None) == _sidecar._YTDLP_KEYS
    assert _sidecar._ytdlp_keys_for(tmp_path, {"_artifact": {"mime": "text/html"}}) == (
        _sidecar._YTDLP_KEYS
    )


# ---------- placement: origin block, not artifact/body ---------- #


def _post_with_origin() -> frontmatter.Post:
    post = frontmatter.Post(content="")
    records.append_origin_block(post, uri="https://x/v/1", snapshot="2026-06-02T00:00:00Z")
    return post


def test_merge_origin_fields_lands_on_origin_block():
    post = _post_with_origin()
    records.merge_origin_fields(post, {"ytdlp_title": "Cool", "ytdlp_view_count": 9})
    fields = post.metadata["_origins"][-1]["fields"]
    assert fields["ytdlp_title"] == "Cool" and fields["ytdlp_view_count"] == 9
    assert fields["uri"] == "https://x/v/1"  # universal fields preserved


def test_merge_origin_fields_noop_without_fields_or_origin():
    post = _post_with_origin()
    records.merge_origin_fields(post, {})  # empty → no-op, no crash
    assert "ytdlp_title" not in post.metadata["_origins"][-1]["fields"]
    bare = frontmatter.Post(content="")
    records.merge_origin_fields(bare, {"ytdlp_title": "X"})  # no origin → no crash
    assert not bare.metadata.get("_origins")


def test_title_for_priority_frontmatter_then_artifact_then_ytdlp():
    post = _post_with_origin()
    records.merge_origin_fields(post, {"ytdlp_title": "From yt-dlp"})
    # 3) only an origin ytdlp_title → display falls all the way back to it.
    assert records.title_for(post) == "From yt-dlp"
    # 2) a namespaced artifact `*_title` candidate outranks ytdlp_title.
    records.set_artifact_block(post, mime="text/html", fields={"html_title": "Artifact Title"})
    assert records.title_for(post) == "Artifact Title"
    # 1) the normalizer-authored frontmatter title is canonical.
    post.metadata["title"] = "Normalized Title"
    assert records.title_for(post) == "Normalized Title"


def test_stub_frontmatter_carries_empty_title_and_description():
    fm = records.stub_frontmatter(record_id="ab" + "0" * 62, touch_id="t")
    assert fm["title"] == "" and fm["description"] == ""


def test_apply_drafter_result_routes_ytdlp_title_to_origin_and_leaves_frontmatter_empty():
    # A media drafter's title rides on the ORIGIN block as `ytdlp_title` (non-primary-source);
    # the artifact block carries no generic `title`, and the frontmatter `title` is NOT
    # auto-populated (normalizer-owned).
    from corpus._cli.draft import _apply_drafter_result

    fm = records.stub_frontmatter(record_id="ab" + "0" * 62, touch_id="t")
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime="video/mp4", fields={"video_codec": "h264"})
    records.append_origin_block(post, uri="https://x/v/1", snapshot="2026-06-02T00:00:00Z")
    result = {
        "fields": {},
        "origin_fields": {"ytdlp_title": "YT"},
        "origin_uri_aliases": [],
    }
    _apply_drafter_result(post, result, "video/video_mp4")
    assert "title" not in (records.artifact_block(post).get("fields") or {})  # no generic title
    assert post.metadata.get("title") == ""  # frontmatter title untouched (normalizer-owned)
    assert post.metadata["_origins"][-1]["fields"]["ytdlp_title"] == "YT"
    assert records.title_for(post) == "YT"  # frontmatter empty → origin ytdlp_title candidate


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
