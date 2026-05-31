"""Atom fingerprint strategies (spec §7.7).

Text simhash is pure-Python and always computes; image pHash computes when
`imagehash` is present (in the dev group) and degrades to None otherwise; audio
chromaprint degrades to None without `pyacoustid` / `fpcalc`. All emitted values
must satisfy the lint perceptual-format check (`<algo>:<hex>`, 64-bit floor).
"""

from __future__ import annotations

import pytest

from corpus.fingerprint import audio as afp
from corpus.fingerprint import image as ifp
from corpus.fingerprint import text as tfp
from corpus.lint import _PERCEPTUAL_RE

# ---------- text (pure-Python simhash) ---------- #


def test_text_fingerprint_format_and_lint():
    fp = tfp.fingerprint_text("The quick brown fox jumps over the lazy dog.")
    assert fp is not None
    assert fp.startswith("simhash:")
    assert _PERCEPTUAL_RE.match(fp)
    # 64-bit → 16 hex chars.
    assert len(fp.split(":", 1)[1]) == 16


def test_text_fingerprint_empty_is_none():
    assert tfp.fingerprint_text("") is None
    assert tfp.fingerprint_text("   \n\t ") is None


def test_text_fingerprint_deterministic_and_normalized():
    # NFKC + lowercase + whitespace-insensitive tokenization.
    a = tfp.fingerprint_text("Hello   World")
    b = tfp.fingerprint_text("hello world")
    assert a == b
    # Stable across calls.
    assert tfp.fingerprint_text("repeatable input") == tfp.fingerprint_text("repeatable input")


def test_text_fingerprint_differs_for_different_text():
    assert tfp.fingerprint_text("alpha beta gamma") != tfp.fingerprint_text("x)delta epsilon zeta")


# ---------- image (imagehash; dev group) ---------- #


def test_image_fingerprint_computes_or_degrades():
    pytest.importorskip("imagehash")
    from PIL import Image

    im = Image.new("RGB", (64, 64), (10, 200, 90))
    fp = ifp.fingerprint_image(im)
    assert fp is not None
    assert fp.startswith("phash:")
    assert _PERCEPTUAL_RE.match(fp)
    # Same image → same fingerprint.
    assert ifp.fingerprint_image(im) == fp


# ---------- audio (degrades without acoustid/fpcalc) ---------- #


def test_audio_fingerprint_degrades_without_dep(tmp_path):
    # pyacoustid is not a dev dep, so this exercises the graceful-None path.
    assert afp.fingerprint_file(tmp_path / "nope.mp3") is None
    assert afp.fingerprint_audio_range(tmp_path / "x.mp3", start=0.0, end=1.0) is None
