"""(3.10 §4.3.2.2, §7.2.1) Whole-address admissibility — the medium decides.

3.8 made a segment's `address` optional, absence naming the whole transport. 3.10 bounds
it: whether a transport HAS a whole to name is a property of the medium, declared by the
mime schema as `whole_address` and enforced here.

The three values, and the case each exists for:
  admissible        a still image — one contained presentation, `bbox=` names only parts
  forbidden         a sequence (pdf pages, video time, mbox messages), or an address
                    space already total (html under 3.6)
  single_unit_only  the bytes decide — a GIF is a still 284 times and a 259-frame
                    animation 417 times across the two hubs, one MIME and both answers
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import lint, records, segments
from corpus.draft.image import _gif_frame_count, _webp_frame_count


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _post(mime: str, fields: dict | None = None) -> frontmatter.Post:
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=mime, fields=fields or {})
    records.append_origin_block(
        post, uri="https://example.com/p", snapshot="2026-05-31T00:00:00Z"
    )
    return post


def _with_addressless_rendering(post: frontmatter.Post) -> frontmatter.Post:
    """A whole-artifact rendering: a text segment with a body and NO address."""
    post.content = segments.emit(
        [segments.Segment(atom="text", overlay="text/data-table", address=None,
                          body="| a | b |\n|---|---|\n| 1 | 2 |")]
    )
    return post


def _findings(post, root) -> list:
    blocks = segments.iter_blocks(post.content or "")
    return [f for f in lint.lint(post, blocks, root)
            if f.rule_id == "whole-address-not-admissible"]


# ---- admissible: the case 3.8 introduced absence for ------------------------------- #

def test_still_image_may_omit_its_address(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(_post("image/png", {"width": 8, "height": 8}))
    assert _findings(post, root) == []


# ---- forbidden: a sequence has no whole to name ------------------------------------ #

def test_pdf_may_not_omit_its_address(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(_post("application/pdf", {"page_count": 12}))
    found = _findings(post, root)
    assert len(found) == 1
    assert found[0].severity == "error"
    assert "forbidden" in found[0].message


def test_one_page_pdf_is_not_an_exception(tmp_path):
    """`page=1` is a true statement about a real unit, so requiring it fabricates
    nothing — unlike `bbox=0,0,1,1` on a still, which claims a measured crop."""
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(_post("application/pdf", {"page_count": 1}))
    assert len(_findings(post, root)) == 1


def test_video_may_not_omit_its_address(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(_post("video/mp4", {}))
    assert len(_findings(post, root)) == 1


def test_html_may_not_omit_its_address(tmp_path):
    """Not because HTML is a sequence — because 3.6 made its address space TOTAL, so the
    whole already has an honest `el=`. Absence here is unnecessary, not untrue."""
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(_post("text/html", {}))
    assert len(_findings(post, root)) == 1


# ---- single_unit_only: the bytes decide -------------------------------------------- #

def test_single_frame_gif_may_omit_its_address(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(
        _post("image/gif", {"width": 8, "height": 8, "frame_count": 1}))
    assert _findings(post, root) == []


def test_animated_gif_may_not_omit_its_address(tmp_path):
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(
        _post("image/gif", {"width": 8, "height": 8, "frame_count": 38}))
    found = _findings(post, root)
    assert len(found) == 1
    assert "38 units" in found[0].message


def test_unstamped_gif_is_unresolved_not_admitted(tmp_path):
    """The whole point of the third value: defaulting an unstamped artifact to
    `admissible` would silently grandfather the entire pre-3.10 population — which is
    exactly the 417 animated GIFs this rule exists to find."""
    root = _make_corpus(tmp_path)
    post = _with_addressless_rendering(_post("image/gif", {"width": 8, "height": 8}))
    found = _findings(post, root)
    assert len(found) == 1
    assert "reattest" in found[0].message


# ---- the rule only judges what it should ------------------------------------------- #

def test_addressed_segment_is_never_judged(tmp_path):
    """A record that addresses its content says nothing about the whole, whatever the
    medium — the rule fires on absence, not on media type."""
    root = _make_corpus(tmp_path)
    post = _post("application/pdf", {"page_count": 12})
    post.content = segments.emit(
        [segments.Segment(atom="text", address="page=3", body="text")])
    assert _findings(post, root) == []


def test_body_empty_marker_cannot_even_be_address_less(tmp_path):
    """A body-empty marker may never be address-less (§4.3.2.2) — and that is enforced
    at the PARSE layer, not by this rule, so such a record cannot be constructed at all.

    Asserted here rather than assumed: this rule keys on `not seg.address`, and if a
    marker could ever reach it the rule would report a rendering defect for a
    positioning one. It cannot, so there is no double-report to guard against."""
    import pytest

    post = _post("application/pdf", {"page_count": 12})
    post.content = segments.emit(
        [segments.Segment(atom="image", address=None, body="")])
    with pytest.raises(ValueError, match="missing required address"):
        list(segments.iter_blocks(post.content))


# ---- the counters, which must not depend on an optional codec ---------------------- #

def _gif(frames: int) -> bytes:
    """A minimal GIF87a with `frames` image descriptors, no global colour table."""
    out = bytearray(b"GIF87a" + bytes([1, 0, 1, 0, 0x00, 0, 0]))
    for _ in range(frames):
        out += bytes([0x2C, 0, 0, 0, 0, 1, 0, 1, 0, 0x00])   # descriptor, no local table
        out += bytes([0x02, 0x02, 0x44, 0x01, 0x00])         # LZW size, one data block
    out += b"\x3b"
    return bytes(out)


def test_gif_frame_count_is_structural():
    assert _gif_frame_count(_gif(1)) == 1
    assert _gif_frame_count(_gif(38)) == 38
    assert _gif_frame_count(b"not a gif") is None


def test_webp_frame_count_counts_anmf_chunks():
    """Structural on purpose. Pillow returns 1 for a still AND for an animation it cannot
    decode — `features.check('webp_anim')` is false in some builds — so the decoder's
    answer is indistinguishable from blindness. The container is not."""
    still = b"RIFF" + b"\x00" * 4 + b"WEBPVP8 " + b"\x00" * 16
    assert _webp_frame_count(still) == 1
    anim = (b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 8 + b"ANIM" + b"\x00" * 6
            + b"ANMF" + b"\x00" * 16 + b"ANMF" + b"\x00" * 16)
    assert _webp_frame_count(anim) == 2
    assert _webp_frame_count(b"GIF89a") is None
