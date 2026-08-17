"""Derived-hash recipe registry, tag grammar, union resolution, and computation
(spec §2, §7.6, §7.9)."""

from __future__ import annotations

import pytest

from corpus import hashing

# ---------- tag grammar (§7.6) ---------- #


def test_parse_tag_bare_algorithm_is_byte_stable():
    info = hashing.parse_tag("sha256")
    assert info.residency == "byte-stable"
    assert info.procedure is None
    assert info.version is None

    info2 = hashing.parse_tag("blake3-64k")
    assert info2.residency == "byte-stable"


def test_parse_tag_procedure_version_is_procedure_versioned():
    info = hashing.parse_tag("html-stampfree@1")
    assert info.residency == "procedure-versioned"
    assert info.procedure == "html-stampfree"
    assert info.version == "1"


def test_parse_tag_version_compared_as_opaque_string():
    # "1" and "1.0" are different tags entirely — the version is never numeric.
    a = hashing.parse_tag("eml-stripped@2.1")
    b = hashing.parse_tag("eml-stripped@2.10")
    assert a.version == "2.1"
    assert b.version == "2.10"
    assert a.version != b.version


@pytest.mark.parametrize(
    "bad_tag",
    ["", "sha256:abc", "@1", "html-stampfree@", "not a tag"],
)
def test_parse_tag_rejects_malformed(bad_tag):
    with pytest.raises(ValueError):
        hashing.parse_tag(bad_tag)


def test_parse_value_splits_on_first_colon():
    info, hexval = hashing.parse_value("sha256:" + "a" * 64)
    assert info.tag == "sha256"
    assert hexval == "a" * 64

    # A procedure-versioned tag's `@` is part of the tag, not a second split point.
    info2, hexval2 = hashing.parse_value("html-stampfree@1:" + "b" * 64)
    assert info2.tag == "html-stampfree@1"
    assert hexval2 == "b" * 64


def test_parse_value_rejects_bad_hex():
    with pytest.raises(ValueError):
        hashing.parse_value("sha256:not-hex")
    with pytest.raises(ValueError):
        hashing.parse_value("sha256:")


def test_parse_value_rejects_missing_prefix():
    with pytest.raises(ValueError):
        hashing.parse_value("just-hex-no-tag")


# ---------- registry construction ---------- #


def test_record_resident_on_procedure_versioned_recipe_is_a_schema_error():
    with pytest.raises(hashing.RecipeError):
        hashing.Recipe(
            id="bogus@1",
            residency="procedure-versioned",
            comparison="identity",
            record_resident=True,
        )


# ---------- union resolution (§7.9) ---------- #


def test_resolve_recipes_default_set_alone():
    recipes = hashing.resolve_recipes(None)
    ids = {r.id for r in recipes}
    assert ids == {"sha256", "md5", "blake3-prefix-ladder"}
    # Default set's residency: record markers match the registry table.
    by_id = {r.id: r for r in recipes}
    assert by_id["sha256"].record_resident is True
    assert by_id["md5"].record_resident is True
    assert by_id["blake3-prefix-ladder"].record_resident is False


def test_resolve_recipes_mime_schema_adds_derived_hashes():
    mime_schema = {"derived_hashes": ["html-stampfree@1"]}
    recipes = hashing.resolve_recipes(mime_schema)
    ids = {r.id for r in recipes}
    assert ids == {"sha256", "md5", "blake3-prefix-ladder", "html-stampfree@1"}


def test_resolve_recipes_origin_overlay_adds():
    hashing.register_recipe(
        hashing.Recipe(
            id="eml-stripped@2.1", residency="procedure-versioned", comparison="identity"
        )
    )
    overlay = {"derived_hashes": ["eml-stripped@2.1"]}
    recipes = hashing.resolve_recipes(None, origin_overlays=[overlay])
    ids = {r.id for r in recipes}
    assert "eml-stripped@2.1" in ids


def test_resolve_recipes_is_additive_never_suppressing():
    mime_schema = {"derived_hashes": ["html-stampfree@1"]}
    overlay = {"derived_hashes": ["md5"]}  # already in default set — no duplication
    recipes = hashing.resolve_recipes(mime_schema, origin_overlays=[overlay, None, {}])
    ids = [r.id for r in recipes]
    assert ids.count("md5") == 1
    assert set(ids) == {"sha256", "md5", "blake3-prefix-ladder", "html-stampfree@1"}


def test_resolve_recipes_legacy_transport_algos_compat():
    mime_schema = {"transport_algos": ["sha256"]}
    recipes = hashing.resolve_recipes(mime_schema)
    by_id = {r.id: r for r in recipes}
    assert by_id["sha256"].residency == "byte-stable"
    assert by_id["sha256"].record_resident is True


def test_resolve_recipes_legacy_transport_algos_ad_hoc_algorithm():
    mime_schema = {"transport_algos": ["sha1"]}
    recipes = hashing.resolve_recipes(mime_schema)
    by_id = {r.id: r for r in recipes}
    assert "sha1" in by_id
    assert by_id["sha1"].residency == "byte-stable"
    assert by_id["sha1"].record_resident is True


def test_resolve_recipes_unknown_recipe_id_errors():
    mime_schema = {"derived_hashes": ["nonexistent-recipe"]}
    with pytest.raises(hashing.RecipeError):
        hashing.resolve_recipes(mime_schema)


def test_resolve_recipes_unknown_recipe_id_on_overlay_errors():
    overlay = {"derived_hashes": ["nonexistent-recipe"]}
    with pytest.raises(hashing.RecipeError):
        hashing.resolve_recipes(None, origin_overlays=[overlay])


# ---------- prefix-ladder rung semantics (§7.9) ---------- #


def test_prefix_ladder_short_file_emits_only_reached_rungs(tmp_path):
    short = tmp_path / "short.bin"
    short.write_bytes(b"x" * 10_000)  # >= 4 KiB, < 64 KiB

    values = hashing.compute_hashes(short, [hashing.BLAKE3_PREFIX_LADDER])
    tags = {v.tag for v in values}
    assert tags == {"blake3-4k"}


def test_prefix_ladder_tiny_file_emits_no_rungs(tmp_path):
    tiny = tmp_path / "tiny.bin"
    tiny.write_bytes(b"x" * 100)  # < 4 KiB

    values = hashing.compute_hashes(tiny, [hashing.BLAKE3_PREFIX_LADDER])
    assert values == []


def test_prefix_ladder_prefix_property_longer_file_matches_shorter_at_reached_rungs(tmp_path):
    import os

    prefix_bytes = os.urandom(10_000)  # reaches only blake3-4k
    short = tmp_path / "short.bin"
    short.write_bytes(prefix_bytes)

    longer = tmp_path / "longer.bin"
    longer.write_bytes(prefix_bytes + os.urandom(70_000))  # reaches blake3-4k + blake3-64k

    short_values = {
        v.tag: v.hex for v in hashing.compute_hashes(short, [hashing.BLAKE3_PREFIX_LADDER])
    }
    longer_values = {
        v.tag: v.hex for v in hashing.compute_hashes(longer, [hashing.BLAKE3_PREFIX_LADDER])
    }
    assert short_values.keys() == {"blake3-4k"}
    assert longer_values.keys() == {"blake3-4k", "blake3-64k"}
    # Prefix property: the rung the shorter file reaches matches exactly.
    assert short_values["blake3-4k"] == longer_values["blake3-4k"]


def test_compute_hashes_byte_stable_and_ladder_share_one_pass(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"hello world" * 1000)

    values = hashing.compute_hashes(f, [hashing.SHA256, hashing.MD5, hashing.BLAKE3_PREFIX_LADDER])
    by_tag = {v.tag: v for v in values}
    assert "sha256" in by_tag
    assert "md5" in by_tag
    assert by_tag["sha256"].record_resident is True
    assert by_tag["md5"].record_resident is True
    # The file is well under 4 KiB * ... actually 11000 bytes >= 4096, < 65536.
    assert "blake3-4k" in by_tag


# ---------- html-stampfree@1 (§7.9) ---------- #


def _banner(date: str, url: str = "https://example.com/page") -> bytes:
    return (
        b"<!--\n"
        b" Page saved with SingleFile\n"
        + f" url: {url}\n".encode()
        + f" saved date: {date}\n".encode()
        + b"-->\n"
    )


def _meta_block(capture_url: str, fetched_at: str, fidelity: str) -> bytes:
    return (
        f'<meta name="corpus-capture-url" content="{capture_url}">'.encode()
        + f'<meta name="corpus-fetched-at" content="{fetched_at}">'.encode()
        + f'<meta name="corpus-fidelity" content="{fidelity}">'.encode()
    )


def test_html_stampfree_ignores_corpus_stamps_and_singlefile_banner():
    body = b"<html><head>" + _meta_block(
        "https://example.com/page", "2026-07-06T19:48:48Z", "balanced"
    ) + b"</head><body>Hello world</body></html>"
    html_a = _banner("Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)") + body

    body2 = b"<html><head>" + _meta_block(
        "https://example.com/page?utm=1", "2026-07-07T09:00:00Z", "exact"
    ) + b"</head><body>Hello world</body></html>"
    html_b = _banner("Tue Jul 07 2026 09:00:00 GMT-0600 (Mountain Daylight Time)") + body2

    assert hashing.html_stampfree_digest(html_a) == hashing.html_stampfree_digest(html_b)


def test_html_stampfree_differs_on_real_content_change():
    meta = _meta_block("https://example.com/page", "2026-07-06T19:48:48Z", "balanced")
    banner = _banner("Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)")

    html_a = banner + b"<html><head>" + meta + b"</head><body>Hello world</body></html>"
    html_b = banner + b"<html><head>" + meta + b"</head><body>Goodbye world</body></html>"

    assert hashing.html_stampfree_digest(html_a) != hashing.html_stampfree_digest(html_b)


def test_html_stampfree_leaves_non_injected_bytes_untouched():
    # A non-corpus meta tag is real content — changing it must change the digest.
    meta = _meta_block("https://example.com/page", "2026-07-06T19:48:48Z", "balanced")
    banner = _banner("Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)")

    html_a = (
        banner
        + b"<html><head>"
        + meta
        + b'<meta name="description" content="A page about apples">'
        + b"</head><body>Hello world</body></html>"
    )
    html_b = (
        banner
        + b"<html><head>"
        + meta
        + b'<meta name="description" content="A page about oranges">'
        + b"</head><body>Hello world</body></html>"
    )
    assert hashing.html_stampfree_digest(html_a) != hashing.html_stampfree_digest(html_b)


def test_html_stampfree_no_stamps_present_is_a_plain_blake3():
    import blake3 as _blake3

    data = b"<html><head></head><body>No stamps here</body></html>"
    assert hashing.html_stampfree_digest(data) == _blake3.blake3(data).hexdigest()


def test_compute_hashes_html_stampfree(tmp_path):
    meta = _meta_block("https://example.com/page", "2026-07-06T19:48:48Z", "balanced")
    banner = _banner("Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)")
    html_bytes = banner + b"<html><head>" + meta + b"</head><body>Hello world</body></html>"

    f = tmp_path / "page.html"
    f.write_bytes(html_bytes)

    values = hashing.compute_hashes(f, [hashing.HTML_STAMPFREE_1])
    assert len(values) == 1
    assert values[0].tag == "html-stampfree@1"
    assert values[0].recipe == "html-stampfree@1"
    assert values[0].record_resident is False
    assert values[0].hex == hashing.html_stampfree_digest(html_bytes)


def test_html_stampfree_streaming_matches_whole_file(tmp_path):
    """The streaming file form must be byte-equivalent to the in-memory form — chunk
    boundaries landing INSIDE a stamp included (the carry-tail contract). The fleet's
    9.68 GB iMessage-export HTML member is why the file form exists at all."""
    import blake3 as _blake3

    meta = _meta_block("https://example.com/deep", "2026-08-16T01:02:03Z", "lean")
    banner = _banner("Sun Aug 16 2026 01:02:03 GMT-0600 (Mountain Daylight Time)")
    filler_a = b"A" * 5000  # pushes past HEAD_BYTES so the head/rest split is exercised
    filler_b = b"B" * 3000
    data = (
        banner
        + b"<html><head>"
        + meta
        + b"</head><body>"
        + filler_a
        + meta  # a stamp deep in the body, far past HEAD_BYTES
        + filler_b
        + b"</body></html>"
    )
    # The in-memory form is the reference (its strip semantics have their own tests
    # above); what THIS test pins is that chunked streaming can never diverge from it.
    reference = hashing.html_stampfree_digest(data)
    assert reference != _blake3.blake3(data).hexdigest()  # the stamps really stripped

    f = tmp_path / "big.html"
    f.write_bytes(data)

    # Tiny chunk sizes force boundaries through every stamp position.
    for chunk_size in (7, 64, 1024, 1 << 20):
        assert hashing.html_stampfree_digest_file(f, chunk_size=chunk_size) == reference


def test_html_stampfree_streaming_short_file(tmp_path):
    """A file shorter than HEAD_BYTES still gets its banner pass (the head_done=False
    EOF path)."""
    banner = _banner("Sun Aug 16 2026 01:02:03 GMT-0600 (Mountain Daylight Time)")
    data = banner + b"<html><body>tiny</body></html>"
    f = tmp_path / "tiny.html"
    f.write_bytes(data)
    assert hashing.html_stampfree_digest_file(f, chunk_size=5) == hashing.html_stampfree_digest(
        data
    )
