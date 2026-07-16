"""yt-dlp .info.json → `ytdlp_*` origin-block fields (draft/_sidecar + the placement)."""

from __future__ import annotations

import json
from typing import Any

import frontmatter

from corpus import records, schemas
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


def test_title_for_priority_frontmatter_then_artifact_then_qualified_origin(tmp_path):
    """*(3.2 phase 2, §12.21 step 2)* The transitional `records._legacy_title_fallback` is
    retired — title resolution now runs entirely through role-marked schema fields
    (spec §4.2.3). `text/html`'s artifact-block `title` carries `role: title` in the
    PACKAGED schema (task 1 of the role-marking sweep), so it resolves with no
    corpus-local schema at all. The origin layer's `ytdlp_title` (role-marked on the
    universal `origin/origin.yaml`) only resolves through a QUALIFIED origin block
    (`schema_id` set) — this test declares a synthetic per-host overlay to exercise that
    path; see `test_ytdlp_title_on_unqualified_origin_does_not_resolve` below for what a
    BARE origin now does instead (the gap the legacy fallback used to paper over). The
    frontmatter override still wins over everything, per spec §4.2.1."""
    origin_dir = tmp_path / "schema" / "origin" / "web"
    origin_dir.mkdir(parents=True)
    (origin_dir / "video.example.yaml").write_text(
        "applies_to:\n  host_patterns: [video.example]\n"
        "extended_fields:\n  ytdlp_title:\n    type: string\n    role: title\n",
        encoding="utf-8",
    )
    schemas.cache_clear()

    post = frontmatter.Post(content="")
    records.append_origin_block(
        post,
        uri="https://video.example/v/1",
        snapshot="2026-06-02T00:00:00Z",
        schema_id="video.example",
    )
    records.merge_origin_fields(post, {"ytdlp_title": "From yt-dlp"})
    # no artifact candidate yet → the qualified origin's role-marked ytdlp_title.
    assert records.title_for(post, tmp_path) == "From yt-dlp"
    # the form/origin/artifact precedence (§4.2.3) has origin outrank artifact... but here
    # the ARTIFACT layer is what we're adding, so re-verify origin still wins while both
    # are present (origin > artifact, per precedence — form strongest, then origin, then
    # artifact weakest).
    records.set_artifact_block(post, mime="text/html", fields={"title": "Artifact Title"})
    assert records.title_for(post, tmp_path) == "From yt-dlp"
    # remove the origin candidate → falls through to the artifact layer.
    post.metadata["_origins"][-1]["fields"].pop("ytdlp_title")
    assert records.title_for(post, tmp_path) == "Artifact Title"
    # the frontmatter override is strongest of all, regardless of layer.
    post.metadata["title"] = "Normalized Title"
    assert records.title_for(post, tmp_path) == "Normalized Title"


def test_ytdlp_title_on_never_qualified_origin_does_not_resolve(tmp_path):
    """*(qualify-32)* Re-keyed now that origin-block host qualification is real (wired into
    ingest + `corpus reattest` via `derive.apply_drafter_result` →
    `records.qualify_origin_blocks`, spec §7.2). This test's intent was never "qualification
    never happens" — it is "the origin layer never blindly reads an unqualified block,
    qualified or not": `_origin_editorial_candidate` requires a `schema_id`, and here none
    is ever set (no `records.qualify_origin_blocks` call, and the origin's host — `x` — has
    no overlay declared in `tmp_path`'s empty schema tree, so even running qualification
    would find nothing to stamp). `ytdlp_title`'s `role: title` mark therefore stays
    unreachable — correct: no overlay, no id, no derived title (§7.2's "no overlay, no id"
    rule). See `test_title_for_resolves_ytdlp_title_once_origin_qualification_runs` below for
    the now-real path where a matching overlay DOES qualify the block and the title
    resolves."""
    post = _post_with_origin()  # bare — no schema_id
    records.merge_origin_fields(post, {"ytdlp_title": "From yt-dlp"})
    assert records.title_for(post, tmp_path) == ""


def test_title_for_resolves_ytdlp_title_once_origin_qualification_runs(tmp_path):
    """*(qualify-32)* The gap `test_ytdlp_title_on_never_qualified_origin_does_not_resolve`
    used to document end-to-end: with a matching per-host overlay declared (`ytdlp_title`
    role-marked `title`, mirroring `test_title_for_priority_frontmatter_then_artifact_then_
    qualified_origin`'s synthetic overlay), running the real qualification helper stamps
    the origin block's opener, and the role-marked field now resolves through it."""
    origin_dir = tmp_path / "schema" / "origin" / "web"
    origin_dir.mkdir(parents=True)
    (origin_dir / "video.example.yaml").write_text(
        "applies_to:\n  host_patterns: [video.example]\n"
        "extended_fields:\n  ytdlp_title:\n    type: string\n    role: title\n",
        encoding="utf-8",
    )
    schemas.cache_clear()

    post = _post_with_origin()  # bare — the fixture's uri is https://x/v/1, no host match here
    post.metadata["_origins"][-1]["fields"]["uri"] = "https://video.example/v/1"
    records.merge_origin_fields(post, {"ytdlp_title": "From yt-dlp"})
    assert records.title_for(post, tmp_path) == ""  # still bare — qualification hasn't run yet

    stamped = records.qualify_origin_blocks(post, tmp_path)
    assert stamped == ["video.example"]
    assert post.metadata["_origins"][-1]["id"] == "video.example"
    assert records.title_for(post, tmp_path) == "From yt-dlp"


def test_stub_frontmatter_carries_no_editorial_keys():
    """*(3.2, spec §12.3.4)* Birth frontmatter carries no `title`/`description` at all —
    the display pair is derived, not stored blank placeholders."""
    fm = records.stub_frontmatter(record_id="ab" + "0" * 62, touch_id="t")
    assert "title" not in fm and "description" not in fm


def test_apply_drafter_result_routes_ytdlp_title_to_origin_and_leaves_frontmatter_empty(tmp_path):
    # A media drafter's title rides on the ORIGIN block as `ytdlp_title` (non-primary-source);
    # the artifact block carries no generic `title`, and the frontmatter carries no `title`
    # key at all (normalizer-owned override, spec §12.3.4).
    from corpus._cli.draft import _apply_drafter_result

    fm = records.stub_frontmatter(record_id="ab" + "0" * 62, touch_id="t")
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime="video/mp4", fields={"codec": "h264"})
    records.append_origin_block(post, uri="https://x/v/1", snapshot="2026-06-02T00:00:00Z")
    result = {
        "fields": {},
        "origin_fields": {"ytdlp_title": "YT"},
        "origin_uri_aliases": [],
    }
    _apply_drafter_result(post, result, "video/video_mp4", tmp_path)
    assert "title" not in (records.artifact_block(post).get("fields") or {})  # no generic title
    assert post.metadata.get("title") is None  # no frontmatter override (normalizer-owned)
    assert post.metadata["_origins"][-1]["fields"]["ytdlp_title"] == "YT"
    # *(3.2 phase 2)* The routed `ytdlp_title` sits on a BARE origin block (this test never
    # qualifies it with a `schema_id`), so it does not resolve as a derived title — the
    # role-marked origin layer only reads a QUALIFIED block (§4.2.3). This is the routing
    # test, not the resolution test; see `test_ytdlp_title_on_unqualified_origin_does_not_resolve`
    # for that gap, and `test_title_for_priority_frontmatter_then_artifact_then_qualified_origin`
    # for the qualified-origin resolution path.
    assert records.title_for(post, tmp_path) == ""


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
