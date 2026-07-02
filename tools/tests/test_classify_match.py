"""Classification-candidate matcher excludes (`classify_match._excluded`).

An overlay's `cues.excludes` (title_pattern regex / body_contains substring) suppresses the
candidate even when its positive cue matched — so a sibling genre that shares vocabulary
disqualifies the wrong overlay.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import classify_match, records, schemas, segments

_OVERLAY = (
    "kind: interpretive\n"
    "description: a genre\n"
    "applies_at: [record]\n"
    "applies_to:\n"
    "  cues:\n"
    "    body_contains: [report]\n"
    "    excludes:\n"
    "      body_contains: [validation]\n"
    "      title_pattern: 'DRAFT'\n"
)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    d = root / "schema" / "composite" / "genre"
    d.mkdir(parents=True)
    (d / "genre.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def _post(body: str, *, title: str = "") -> frontmatter.Post:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id="a1" * 32, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={"title": title} if title else {})
    records.append_origin_block(post, uri="https://example.com/a", snapshot="2026-06-05T00:00:00Z")
    post.content = segments.emit([segments.Segment(atom="text", address="el=1", body=body)])
    return post


def _ids(post, root):
    return {c.overlay_id for c in classify_match.candidates(post, root)}


def test_positive_cue_surfaces(tmp_path):
    root = _corpus(tmp_path)
    assert "genre" in _ids(_post("the annual report"), root)


def test_body_exclude_suppresses(tmp_path):
    root = _corpus(tmp_path)
    # Body matches the positive cue (`report`) AND the exclude (`validation`) → suppressed.
    assert "genre" not in _ids(_post("the annual report and validation summary"), root)


def test_title_pattern_exclude_suppresses(tmp_path):
    root = _corpus(tmp_path)
    # Positive cue matches, but the title matches the exclude `title_pattern` → suppressed.
    assert "genre" not in _ids(_post("the annual report", title="DRAFT — not final"), root)
