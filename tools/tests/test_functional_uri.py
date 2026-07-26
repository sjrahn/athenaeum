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


def test_parse_decodes_percent_escaped_values():
    """A query-reserved character in a param VALUE rides percent-encoded and parses back
    decoded — a zip member named `…D&D 5e….json` is addressable as `?path=…D%26D 5e….json`."""
    p = fu.parse("corpus://" + "a" * 64 + "?path=Direct Messages - D%26D 5e [673].json")
    assert p.params == (("path", "Direct Messages - D&D 5e [673].json"),)


def test_canonical_reencodes_decoded_values():
    """parse ∘ canonical round-trips: the canonical form re-encodes reserved characters, so
    it is always re-parseable to the same params."""
    uri = "corpus://" + "a" * 64 + "?path=a %26 b %2523.json"
    p = fu.parse(uri)
    assert p.params == (("path", "a & b %23.json"),)
    assert fu.canonical(p) == uri
    assert fu.parse(fu.canonical(p)) == p


def test_clean_values_unchanged_by_encoding_round_trip():
    """Values without reserved characters are byte-identical through parse/canonical — no
    cache-key drift for every existing URI in the wild."""
    uri = "corpus://" + "a" * 64 + "?path=Takeout/Mail/a.txt&page=3"
    assert fu.canonical(fu.parse(uri)) == uri


def test_parse_region_rejects_pixels_and_corners():
    """The region grammar is `x,y,WIDTH,HEIGHT` as FRACTIONS in [0,1]. One definition,
    used by the render path AND by lint, so an address cannot be legal to one and
    illegal to the other."""
    assert fu.parse_region("0,0,1,1") == (0.0, 0.0, 1.0, 1.0)
    assert fu.parse_region("0.24,0,0.76,1") == (0.24, 0.0, 0.76, 1.0)

    with pytest.raises(ValueError, match="fractions of the image"):
        fu.parse_region("0,0,2700,1920")  # pixels — the drift this catches
    with pytest.raises(ValueError, match="position plus a size"):
        fu.parse_region("0.5,0.5,0.8,0.2")  # corners x0,y0,x1,y1
    with pytest.raises(ValueError, match="4 comma-separated"):
        fu.parse_region("0,0,1")


def test_region_errors_declines_foreign_grammars():
    """`bbox=` is overloaded: on a spreadsheet it addresses an A1 range. A value whose
    parts are not all numeric is left alone rather than guessed at — the check reports
    only the unambiguous case (numbers where fractions were required)."""
    assert fu.region_errors("bbox", "A1:D20") == []
    assert fu.region_errors("el", "3") == []  # not a region param at all
    assert fu.region_errors("bbox", "0,0,1,1") == []
    assert fu.region_errors("cover", "0.9,0,0.1,0.3;0.2,0.8,0.05,0.2") == []

    assert fu.region_errors("bbox", "0,0,2700,1920")
    # A bad chunk anywhere in a multi-region value is reported.
    assert fu.region_errors("cover", "0.9,0,0.1,0.3;0,0,2700,1920")
    # A region param with no value at all cannot address anything.
    assert fu.region_errors("bbox", None)
