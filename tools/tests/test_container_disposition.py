"""(§65, declared 3.11) Video containers are `disposition: manifest`; streams are `work`.

Not an amendment — a conformance fix. §65 has said since 3.0 that a multi-track media
container is a raw archive whose members are elementary streams at `stream_id=`, whose
audio-track record owns the transcript and whose video-track record owns frame work. The
schemas never declared it, so `pipeline_disposition` fell back to `work` and every container
was a transport with a body to write a transcript into.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import lint, records, schemas, segments


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _post(mime: str, *, rendering: bool = False) -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(post, uri="file:///v.mp4",
                                snapshot="2026-05-31T00:00:00Z")
    if rendering:
        post.content = segments.emit([
            segments.Segment(atom="text", overlay="text/transcript",
                             address="time_range=0-6", body="spoken words")
        ])
    return post


def _findings(post, root, rule: str) -> list:
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root) if f.rule_id == rule]


# ---- the declaration ---------------------------------------------------------------- #

def test_multitrack_containers_are_manifest(tmp_path):
    root = _make_corpus(tmp_path)
    for mime in ("video/mp4", "video/quicktime", "video/webm", "video/x-matroska"):
        s = schemas.load_mime_schema(root, mime) or {}
        assert schemas.pipeline_disposition(s) == "manifest", mime


def test_elementary_streams_stay_work(tmp_path):
    """A stream is a transport, not a container of transports. Declaring the disposition at
    the `video.yaml` family rung would have swept these in and said their content is other
    transports — exactly backwards, and it would have made the promoted leaves that carry
    the actual renderings into containers."""
    root = _make_corpus(tmp_path)
    for mime in ("video/h264", "video/hevc"):
        s = schemas.load_mime_schema(root, mime) or {}
        assert schemas.pipeline_disposition(s) == "work", mime


def test_audio_is_untouched(tmp_path):
    """§65: a bare MP3 is a single-stream artifact and "stays a single `work`". Every audio
    record in either hub is that or a promoted stream leaf."""
    root = _make_corpus(tmp_path)
    for mime in ("audio/mpeg", "audio/opus", "audio/aac", "audio/x-wav"):
        s = schemas.load_mime_schema(root, mime) or {}
        assert schemas.pipeline_disposition(s) == "work", mime


# ---- the obligation the flip exposes ------------------------------------------------ #

def test_container_with_a_rendering_is_flagged(tmp_path):
    root = _make_corpus(tmp_path)
    post = _post("video/mp4", rendering=True)
    found = _findings(post, root, "container-carries-rendering")
    assert len(found) == 1
    assert found[0].severity == "warning"


def test_container_without_a_rendering_is_clean(tmp_path):
    root = _make_corpus(tmp_path)
    assert _findings(_post("video/mp4"), root, "container-carries-rendering") == []


def test_a_stream_may_carry_a_rendering(tmp_path):
    """The whole point of the arc: the rendering belongs HERE, on the promoted stream."""
    root = _make_corpus(tmp_path)
    post = _post("video/h264", rendering=True)
    assert _findings(post, root, "container-carries-rendering") == []


def test_the_flip_does_not_make_a_rendered_container_an_error(tmp_path):
    """`shape.governing_form` deliberately refuses a class-level terminal default to a record
    that already carries a rendering, so a container mid-migration stands `rendered`, not
    `terminal`, and `terminal-stored-rendering` must NOT fire. That guard is what lets the
    disposition be declared before the content is migrated instead of reddening 102 records
    on a schema edit — which is why the obligation is a warning on its own rule instead."""
    root = _make_corpus(tmp_path)
    post = _post("video/mp4", rendering=True)
    assert _findings(post, root, "terminal-stored-rendering") == []
    assert len(_findings(post, root, "container-carries-rendering")) == 1


def test_a_reseated_container_with_only_placements_and_marks_is_clean(tmp_path):
    """The shape §12.30's reseat migration leaves behind on a cleaned container: a body-empty
    `image` marker for a region of the container's own transport (a `frame=` self-slice,
    §4.3.2.4 Scope — legitimate, untouched by the migration) and a placement for each promoted
    member. Neither is a rendering. `has_stored_rendering` counts the marker as "a content
    atom present" regardless of body, which used to fire this rule with a self-contradicting
    "carries 0 stored rendering segment(s)" — the gate and the reported count must agree."""
    root = _make_corpus(tmp_path)
    post = _post("video/mp4")
    post.content = segments.emit(
        [
            segments.Segment(atom="image", address="frame=00:00:01"),
            segments.Segment(atom="placement", address="stream_id=0"),
            segments.Segment(atom="placement", address="stream_id=1"),
        ]
    )
    assert _findings(post, root, "container-carries-rendering") == []
