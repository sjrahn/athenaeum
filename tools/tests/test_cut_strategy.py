"""(3.11 §7.2.1) The cut strategy: declaration, resolution, and the stamp.

A PDF's `page=7` is a fact in the bytes. A video's `time_range=00:04:12-00:04:31` is the
opinion of a detector at a setting — so the strategy is declared by the mime schema,
overridable by an origin overlay (sensitivity is a property of what was recorded, not the
codec), resolved ONCE at promotion, and stamped on the stream leaf with its resulting cut
count as the drift check.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml

from corpus import lint, records, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema" / "origin" / "web").mkdir(parents=True)
    return root


def _post(mime: str, fields: dict | None = None, *, origin_id: str | None = None,
          uri: str = "https://example.com/v") -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields=fields or {})
    records.append_origin_block(post, uri=uri, snapshot="2026-05-31T00:00:00Z")
    if origin_id:
        # stamps the MOST-RECENT origin block, so no index is passed
        records.set_origin_schema_id(post, origin_id)
    return post


def _findings(post, root) -> list:
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root)
            if f.rule_id == "cutting-stamp-malformed"]


# ---- declaration, and who inherits it ---------------------------------------------- #

def test_video_family_declares_a_default_strategy(tmp_path):
    root = _make_corpus(tmp_path)
    for mime in ("video/mp4", "video/h264", "video/hevc", "video/quicktime"):
        s = schemas.load_mime_schema(root, mime) or {}
        cs = schemas.cut_strategy(s)
        assert cs is not None, mime
        assert cs["id"].startswith("scene-threshold@")
        # 0.3 is the pilot-resolved value (§12.20 OQ1), not a placeholder
        assert cs["threshold"] == 0.3


def test_non_timeline_types_declare_none(tmp_path):
    """A cut strategy is meaningless without a timeline. Audio boundaries come from
    transcription (utterances, diarization), not from scene detection."""
    root = _make_corpus(tmp_path)
    for mime in ("image/png", "application/pdf", "text/html", "audio/opus"):
        assert schemas.cut_strategy(schemas.load_mime_schema(root, mime) or {}) is None


def test_a_versionless_strategy_id_is_not_a_strategy():
    """A cut list is only reproducible against a versioned strategy, so an unversioned id
    is rejected at the source rather than stamped and trusted later."""
    assert schemas.cut_strategy({"cut_strategy": {"id": "scene-threshold"}}) is None
    assert schemas.cut_strategy({"cut_strategy": {"threshold": 0.4}}) is None
    assert schemas.cut_strategy({"cut_strategy": "scene-threshold@0.1.0"}) is None


# ---- resolution: overlay beats mime default ---------------------------------------- #

def test_origin_overlay_overrides_the_mime_default(tmp_path):
    """The point of the amendment: a TikTok and a feature film do not want one sensitivity."""
    root = _make_corpus(tmp_path)
    (root / "schema" / "origin" / "web" / "tiktok.com.yaml").write_text(
        yaml.safe_dump({
            "kind": "interpretive",
            "applies_to": {"hosts": ["www.tiktok.com"]},
            "cut_strategy": {"id": "fixed-interval@0.1.0", "seconds": 2},
        }),
        encoding="utf-8",
    )
    post = _post("video/mp4", origin_id="tiktok.com", uri="https://www.tiktok.com/@x/video/1")
    resolved = schemas.resolve_cut_strategy_for_record(root, post)
    assert resolved == {"id": "fixed-interval@0.1.0", "seconds": 2}


def test_mime_default_applies_with_no_overlay(tmp_path):
    root = _make_corpus(tmp_path)
    post = _post("video/mp4")
    resolved = schemas.resolve_cut_strategy_for_record(root, post)
    assert resolved is not None and resolved["id"].startswith("scene-threshold@")


def test_unresolved_returns_none_not_a_substituted_default(tmp_path):
    """`resolve_...` must not invent a strategy. A caller that gets None has to report
    unresolved, because a substituted default would silently cut a record under a strategy
    nobody declared."""
    root = _make_corpus(tmp_path)
    assert schemas.resolve_cut_strategy_for_record(root, _post("image/png")) is None


# ---- the stamp -------------------------------------------------------------------- #

def test_stamp_reads_back_from_the_artifact_block(tmp_path):
    post = _post("video/h264", {"cutting": {"id": "scene-threshold@0.1.0",
                                            "threshold": 0.4, "cuts": 36}})
    stamp = records.cutting(post)
    assert stamp is not None and stamp["cuts"] == 36


def test_absent_stamp_is_unresolved_not_a_finding(tmp_path):
    """A stream promoted before the strategy existed is awaiting a stamp, not defective —
    the two hand-authored exemplar leaves are exactly this case, and flagging them would
    make correct records look broken."""
    root = _make_corpus(tmp_path)
    post = _post("video/h264")
    assert records.cutting(post) is None
    assert _findings(post, root) == []


def test_stamping_is_a_merge_not_a_translation(tmp_path):
    """The declaration's own keys carry into the stamp unrenamed, so no key-mapping step
    exists in which a parameter could be silently dropped."""
    root = _make_corpus(tmp_path)
    declared = schemas.resolve_cut_strategy_for_record(root, _post("video/mp4"))
    stamp = {**declared, "cuts": 36, "duration": 616.4}
    post = _post("video/h264", {"cutting": stamp})
    assert _findings(post, root) == []
    assert records.cutting(post)["threshold"] == declared["threshold"]


def test_stamp_without_a_cut_count_is_malformed(tmp_path):
    """The count is the drift check — the whole reason the stamp exists."""
    root = _make_corpus(tmp_path)
    post = _post("video/h264", {"cutting": {"id": "scene-threshold@0.1.0", "threshold": 0.4}})
    found = _findings(post, root)
    assert len(found) == 1 and "cuts" in found[0].message


def test_stamp_with_an_unversioned_strategy_is_malformed(tmp_path):
    root = _make_corpus(tmp_path)
    post = _post("video/h264", {"cutting": {"id": "scene-threshold", "cuts": 36}})
    found = _findings(post, root)
    assert len(found) == 1 and "no version" in found[0].message


def test_stamp_with_a_nonsense_count_is_malformed(tmp_path):
    root = _make_corpus(tmp_path)
    for bad in ("many", 0, -3):
        post = _post("video/h264", {"cutting": {"id": "scene-threshold@0.1.0", "cuts": bad}})
        assert len(_findings(post, root)) == 1, bad
