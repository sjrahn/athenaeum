"""Functional URI parse / canonicalize / urihash tests (spec §6)."""

from __future__ import annotations

import pytest

from corpus import functional_uri as fu


def test_parse_bare_uri():
    p = fu.parse("corpus://" + "a" * 64)
    assert p.hash == "a" * 64
    assert p.params == ()
    assert p.is_bare


def test_parse_with_params_preserves_order():
    p = fu.parse("corpus://" + "a" * 64 + "?page=1&bbox=0.1,0.1,0.5,0.5&grayscale")
    assert p.params == (("page", "1"), ("bbox", "0.1,0.1,0.5,0.5"), ("grayscale", None))
    assert not p.is_bare


def test_parse_rejects_wrong_scheme():
    with pytest.raises(ValueError, match="expected scheme"):
        fu.parse("http://" + "a" * 64)


def test_parse_rejects_malformed_hash():
    with pytest.raises(ValueError, match="hash must be 64-char lowercase hex"):
        fu.parse("corpus://nothex")
    with pytest.raises(ValueError):
        fu.parse("corpus://" + "X" * 64)  # uppercase rejected


def test_canonical_roundtrip():
    original = "corpus://" + "a" * 64 + "?page=1&bbox=0.1,0.1,0.5,0.5&grayscale"
    canon = fu.canonical(fu.parse(original))
    assert canon == original


def test_urihash_is_stable():
    """Spec §6.3: same URI → same urihash; cacheable."""
    uri = "corpus://" + "a" * 64 + "?page=1"
    h1 = fu.urihash(uri)
    h2 = fu.urihash(uri)
    assert h1 == h2
    assert len(h1) == 64


def test_urihash_differs_for_different_params():
    """Param order is significant; the urihash reflects it."""
    h_a = fu.urihash("corpus://" + "a" * 64 + "?page=1&bbox=0.0,0.0,1.0,1.0")
    h_b = fu.urihash("corpus://" + "a" * 64 + "?bbox=0.0,0.0,1.0,1.0&page=1")
    assert h_a != h_b


def test_quote_and_unquote_value():
    raw = "Overview & Results / Q1#draft"
    enc = fu.quote_value(raw)
    assert "&" not in enc
    assert "#" not in enc
    assert fu.unquote_value(enc) == raw
    # Round-trip a literal `%26` (encoded form) too:
    literal = "look %26 see"
    enc2 = fu.quote_value(literal)
    assert fu.unquote_value(enc2) == literal


def test_cache_path_uses_sharded_layout(tmp_path):
    uh = "f" * 64
    p = fu.cache_path(tmp_path, uh, "png")
    assert p == tmp_path / "cache" / "ff" / f"{uh}.png"
    sc = fu.cache_sidecar_path(p)
    assert sc == tmp_path / "cache" / "ff" / f"{uh}.png.json"


def test_get_last_returns_last_value_for_key():
    p = fu.parse("corpus://" + "a" * 64 + "?dpi=200&page=1&dpi=300")
    assert fu.get_last(p, "dpi") == "300"
    assert fu.get_last(p, "page") == "1"
    assert fu.get_last(p, "absent") is None


def test_fragment_preserved():
    p = fu.parse("corpus://" + "a" * 64 + "?page=1#anchor-name")
    assert p.fragment == "anchor-name"
    assert fu.canonical(p).endswith("#anchor-name")
