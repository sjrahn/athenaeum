"""(3.13 §6.2, §4.3.2.2 — #124) The frame axis on animated raster images.

`frame=<N>` is a 1-based ordinal selecting one frame; `frame=<A>-<B>` is the
whole-sequence ASSERTION (a rendering that holds across every frame — checkable, never
an omission). The image reading of the polymorphic axis; video's timecode reading is
untouched and not judged by the image grammar. Stored values are gated by
`address-frame-invalid` against the attested `frame_count` — compare, never decode.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
from PIL import Image

from corpus import functional_uri as furi
from corpus import lint, records, segments
from corpus.transforms import NotMaterializable
from corpus.transforms import image as image_transforms


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _gif(tmp_path: Path, colors=((255, 0, 0), (0, 255, 0), (0, 0, 255))) -> Path:
    """A tiny animated GIF, one solid color per frame."""
    frames = [Image.new("RGB", (4, 4), c) for c in colors]
    out = tmp_path / "anim.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return out


# ---- the shared grammar ------------------------------------------------------------ #

def test_frame_errors_accepts_index_and_span():
    assert furi.frame_errors("frame", "3", count=8) == []
    assert furi.frame_errors("frame", "1-8", count=8) == []


def test_frame_errors_rejects_bad_values():
    assert furi.frame_errors("frame", "0", count=8)          # 1-based
    assert furi.frame_errors("frame", "9", count=8)          # past the count
    assert furi.frame_errors("frame", "2-9", count=8)        # span end past the count
    assert furi.frame_errors("frame", "x", count=8)          # not an integer
    assert furi.frame_errors("frame", None, count=8)         # no value


def test_frame_errors_judges_only_its_key():
    assert furi.frame_errors("bbox", "0,0,1,1", count=8) == []
    assert furi.frame_errors("page", "3", count=8) == []


# ---- the materialization ----------------------------------------------------------- #

def test_frame_op_selects_the_named_frame(tmp_path):
    src = _gif(tmp_path)
    ctx = {"artifact_path": src}
    working = Image.new("RGB", (1, 1))  # discarded — frame= reads the artifact
    out = image_transforms.frame(working, "2", ctx)
    assert out.convert("RGB").getpixel((0, 0)) == (0, 255, 0)


def test_frame_op_bounds_check_uses_the_real_sequence(tmp_path):
    src = _gif(tmp_path)
    with pytest.raises(ValueError, match="out of range"):
        image_transforms.frame(Image.new("RGB", (1, 1)), "4", {"artifact_path": src})


def test_frame_span_is_an_address_not_a_render(tmp_path):
    """`frame=1-3` names the whole sequence deliberately (§4.3.2.2); it has no single
    byte surface, so it does not materialize — but its bounds are still checked first."""
    src = _gif(tmp_path)
    with pytest.raises(NotMaterializable):
        image_transforms.frame(Image.new("RGB", (1, 1)), "1-3", {"artifact_path": src})
    with pytest.raises(ValueError, match="out of range"):
        image_transforms.frame(Image.new("RGB", (1, 1)), "1-9", {"artifact_path": src})


# ---- the lint gate ----------------------------------------------------------------- #

def _post(mime: str, fields: dict | None = None) -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields=fields or {})
    records.append_origin_block(
        post, uri="https://example.com/p", snapshot="2026-05-31T00:00:00Z"
    )
    return post


def _with_segment(post: frontmatter.Post, address: str) -> frontmatter.Post:
    post.content = segments.emit(
        [segments.Segment(atom="text", overlay="text/ocr", address=address, body="CAPTION")]
    )
    return post


def _findings(post, root) -> list:
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root)
            if f.rule_id == "address-frame-invalid"]


def test_a_valid_frame_address_is_clean(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/gif", {"frame_count": 8}), "frame=2")
    assert _findings(post, root) == []


def test_the_whole_sequence_assertion_is_clean(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/gif", {"frame_count": 8}), "frame=1-8")
    assert _findings(post, root) == []


def test_a_frame_address_satisfies_the_whole_address_gate(tmp_path):
    """The road to conformance: the 3.10 gate fires on ADDRESSLESS renderings, so a
    sequence whose rendering now carries its frame axis passes both rules."""
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/gif", {"frame_count": 8}), "frame=1-8")
    blocks = segments.iter_blocks(post.content or "")
    hit = [f for f in lint.lint(post, blocks, root)
           if f.rule_id in ("whole-address-not-admissible", "address-frame-invalid")]
    assert hit == []


def test_out_of_range_and_bad_grammar_error(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/gif", {"frame_count": 8}), "frame=9")
    found = _findings(post, root)
    assert len(found) == 1 and found[0].severity == "error"
    assert "out of range" in found[0].message


def test_region_param_before_frame_errors(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/gif", {"frame_count": 8}), "bbox=0,0,1,1&frame=2")
    found = _findings(post, root)
    assert any("must lead" in f.message for f in found)
    # the conforming order is clean
    post = _with_segment(_post("image/gif", {"frame_count": 8}), "frame=2&bbox=0,0,1,1")
    assert _findings(post, root) == []


def test_frame_on_a_still_medium_is_undeclared(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/png", {"width": 8, "height": 8}), "frame=2")
    found = _findings(post, root)
    assert len(found) == 1
    assert "declares no `frame` axis" in found[0].message


def test_frame_on_an_unstamped_gif_is_unresolved_not_admitted(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("image/gif"), "frame=2")
    found = _findings(post, root)
    assert len(found) == 1
    assert "reattest" in found[0].message


def test_video_timecodes_are_not_judged(tmp_path):
    """`frame=` on a video is a timecode — the other half of the polymorphic axis;
    the image ordinal grammar must not touch it."""
    root = _make_corpus(tmp_path)
    post = _with_segment(_post("video/mp4", {"duration": 20.0}), "frame=00:00:03")
    assert _findings(post, root) == []
