"""Atom fingerprint strategies (spec §7.7).

Text simhash is pure-Python and always computes; image pHash computes when
`imagehash` is present (in the dev group) and degrades to None otherwise; audio
chromaprint degrades to None without `pyacoustid` / `fpcalc`. All emitted values
must satisfy the lint perceptual-format check (`<algo>:<hex>`, 64-bit floor).
"""

from __future__ import annotations

import pytest

from corpus import fingerprint as fp_pkg
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


def test_text_fingerprint_rejects_unknown_algo():
    with pytest.raises(ValueError, match="simhash"):
        tfp.fingerprint_text("words", algo="minhash")


# ---------- the algorithm registry / knob resolution ---------- #


def test_algos_for_atom_off_default_and_explicit():
    # falsy / None → off.
    assert fp_pkg.algos_for_atom("text", False) == []
    assert fp_pkg.algos_for_atom("text", None) == []
    # True → the atom's default algorithm.
    assert fp_pkg.algos_for_atom("text", True) == ["simhash"]
    assert fp_pkg.algos_for_atom("image", True) == ["phash"]
    # explicit name / list (whitespace + case tolerant), de-duplicated, order-preserving.
    assert fp_pkg.algos_for_atom("text", "simhash") == ["simhash"]
    assert fp_pkg.algos_for_atom("image", ["dhash", "PHASH ", "dhash"]) == ["dhash", "phash"]


def test_algos_for_atom_filters_wrong_atom_and_unknown(caplog):
    # an image algorithm requested on a text atom is silently skipped.
    assert fp_pkg.algos_for_atom("text", "phash") == []
    assert fp_pkg.algos_for_atom("text", ["simhash", "phash"]) == ["simhash"]
    # an unknown algorithm warns and is dropped.
    assert fp_pkg.algos_for_atom("text", "bogus") == []


def test_text_fingerprints_scalar_list_and_none():
    assert fp_pkg.text_fingerprints("some words", []) is None
    one = fp_pkg.text_fingerprints("some words", ["simhash"])
    assert isinstance(one, str) and one.startswith("simhash:")
    # empty body degrades to None even when requested.
    assert fp_pkg.text_fingerprints("", ["simhash"]) is None


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


def test_image_fingerprint_algorithm_selection_and_unknown():
    pytest.importorskip("imagehash")
    from PIL import Image

    im = Image.new("RGB", (64, 64), (10, 200, 90))
    for algo in ("phash", "dhash", "ahash", "whash"):
        fp = ifp.fingerprint_image(im, algo=algo)
        assert fp is not None and fp.startswith(f"{algo}:")
        assert _PERCEPTUAL_RE.match(fp)
    with pytest.raises(ValueError, match="unknown image fingerprint"):
        ifp.fingerprint_image(im, algo="nope")


def test_image_fingerprints_package_scalar_list_none(tmp_path):
    pytest.importorskip("imagehash")
    from PIL import Image

    p = tmp_path / "i.png"
    Image.new("RGB", (32, 32), (5, 5, 200)).save(p)
    one = fp_pkg.image_fingerprints(p, ["dhash"])
    assert isinstance(one, str) and one.startswith("dhash:")
    multi = fp_pkg.image_fingerprints(p, ["phash", "dhash"])
    assert isinstance(multi, list) and len(multi) == 2
    assert fp_pkg.image_fingerprints(p, []) is None


# ---------- audio (degrades without acoustid/fpcalc) ---------- #


def test_audio_fingerprint_degrades_without_dep(tmp_path):
    # pyacoustid is not a dev dep, so this exercises the graceful-None path.
    assert afp.fingerprint_file(tmp_path / "nope.mp3") is None
    assert afp.fingerprint_audio_range(tmp_path / "x.mp3", start=0.0, end=1.0) is None
