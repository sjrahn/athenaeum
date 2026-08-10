"""Sanity tests for the dependency-free utility modules."""

from __future__ import annotations

import mimetypes

import frontmatter
import pytest

from corpus import containment, hashing, mime, paths, schemas, touches, urls


def test_hash_file_and_bytes_agree(tmp_path):
    data = b"hello, corpus\n"
    f = tmp_path / "blob"
    f.write_bytes(data)
    from_file = hashing.hash_file(f)
    from_bytes = hashing.hash_bytes(data)
    assert from_file["blake3"] == from_bytes["blake3"]
    assert from_file["sha256"] == from_bytes["sha256"]
    assert len(from_file["blake3"]) == 64  # lowercase hex per spec


def test_find_corpus_root(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    (root / "records" / "ab").mkdir()
    nested = root / "records" / "ab"
    assert paths.find_corpus_root(nested) == root.resolve()


def test_find_corpus_root_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        paths.find_corpus_root(tmp_path)


def test_shard_and_record_path(tmp_path):
    rid = "ab" + "0" * 62
    assert paths.shard(rid) == "ab"
    assert paths.record_path(tmp_path, rid).name == f"{rid}.md"
    assert paths.record_path(tmp_path, rid).parent.name == "ab"


def test_mime_detects_pdf_and_png(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert mime.detect(pdf) == "application/pdf"
    png = tmp_path / "a.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert mime.detect(png) == "image/png"


def test_mime_riff_disambiguation(tmp_path):
    # WebP, WAV, and AVI all share the `RIFF` magic at offset 0; only the offset-8
    # form-type distinguishes them. A bare RIFF prefix must NOT default to image/webp.
    size = b"\x00\x00\x00\x00"
    webp = tmp_path / "a.webp"
    webp.write_bytes(b"RIFF" + size + b"WEBP" + b"\x00" * 4)
    assert mime.detect(webp) == "image/webp"
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF" + size + b"WAVE" + b"\x00" * 4)
    assert mime.detect(wav) == "audio/x-wav"
    avi = tmp_path / "a.avi"
    avi.write_bytes(b"RIFF" + size + b"AVI " + b"\x00" * 4)
    assert mime.detect(avi) == "video/x-msvideo"


def test_mime_isobmff_audio_refinement(tmp_path):
    # An ISOBMFF `ftyp` box: 4-byte size + `ftyp` + 4-byte major brand. Most `.m4b`
    # audiobooks carry a generic `isom`/`mp42` brand that magic-sniffs as video/mp4 even
    # though they hold only audio — the extension refines them to audio/mp4 so they route
    # to the audio (transcription) pipeline, not the video one.
    isom = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 4
    m4b = tmp_path / "audiobook.m4b"
    m4b.write_bytes(isom)
    assert mime.detect(m4b) == "audio/mp4"
    m4a = tmp_path / "song.m4a"
    m4a.write_bytes(isom)
    assert mime.detect(m4a) == "audio/mp4"
    # Same generic brand with a video extension stays video/mp4 — the refinement only
    # fires for known audio extensions.
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(isom)
    assert mime.detect(mp4) == "video/mp4"


def test_mime_isobmff_audio_brand(tmp_path):
    # A correctly-branded audio-in-MP4 file routes to audio/mp4 by magic alone, regardless
    # of extension.
    m4a_brand = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 4
    f = tmp_path / "noext"
    f.write_bytes(m4a_brand)
    assert mime.detect(f) == "audio/mp4"


def test_mime_detects_svg_through_its_prologue(tmp_path):
    # SVG has no fixed-offset magic: the root may be preceded by a BOM, an XML declaration,
    # a doctype, comments, or whitespace. Every opening reaches the same answer.
    bare = tmp_path / "bare"
    bare.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>')
    assert mime.detect(bare) == "image/svg+xml"

    declared = tmp_path / "declared"
    declared.write_bytes(
        b"\xef\xbb\xbf<?xml version='1.0' encoding='UTF-8'?>\n<svg viewBox='0 0 1 1'></svg>"
    )
    assert mime.detect(declared) == "image/svg+xml"

    doctyped = tmp_path / "doctyped"
    doctyped.write_bytes(
        b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n'
        b' "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<svg width="8"></svg>'
    )
    assert mime.detect(doctyped) == "image/svg+xml"

    commented = tmp_path / "commented"
    commented.write_bytes(b"<!-- Generator: Adobe Illustrator -->\n<svg></svg>")
    assert mime.detect(commented) == "image/svg+xml"


def test_mime_svg_test_stays_off_non_svg(tmp_path):
    # A prologue alone is not SVG — generic XML must not be claimed.
    xml = tmp_path / "feed"
    xml.write_bytes(b"<?xml version='1.0'?>\n<rss version='2.0'><channel/></rss>")
    assert mime.detect(xml) != "image/svg+xml"
    # An HTML page has no byte signature of its own, so a prologue'd page with an EARLY
    # inline <svg> would be claimed here if presence in the window decided instead of the
    # first element: a comment banner ("<!-- saved from url -->") and an XHTML `<?xml`
    # prologue are both real page openings, not SVG ones.
    banner_html = tmp_path / "page.html"
    banner_html.write_bytes(
        b"<!-- saved from url=(0042)https://example.com -->\n"
        b'<!DOCTYPE html><html><body><svg width="5"><rect/></svg></body></html>'
    )
    assert mime.detect(banner_html) == "text/html"
    xhtml = tmp_path / "page.xhtml"
    xhtml.write_bytes(
        b"<?xml version='1.0'?>\n"
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><svg/></body></html>'
    )
    assert mime.detect(xhtml) != "image/svg+xml"
    # Nor a tag that merely starts with the same letters.
    assert mime.sniff_head(b"<svgmap><node/></svgmap>") != "image/svg+xml"
    # Real troff answers exactly what it answered before: nothing from the bytes, and
    # whatever the platform's extension table says for a genuine man-page suffix (the
    # `.1` → `application/x-troff-man` mapping comes from the system's mime.types, not from
    # Python's built-in table, so the invariant is "unchanged", not a literal type).
    troff = b'.TH FOO 1 "2026-08-10"\n.SH NAME\nfoo \\- do a thing\n'
    assert mime.sniff_head(troff) == "unknown"
    assert mime.sniff_head(troff, "foo.1") == (mimetypes.guess_type("foo.1")[0] or "unknown")


def test_mime_tiff_and_heif_magic(tmp_path):
    # #149's private half: Apple export attachments — ProRAW DNGs (TIFF family, both byte
    # orders) and HEIC photos — sniffed `unknown` and were typed from a pseudo-filename.
    assert mime.sniff_head(b"MM\x00*" + b"\x00" * 40) == "image/tiff"
    assert mime.sniff_head(b"II*\x00" + b"\x00" * 40) == "image/tiff"
    assert mime.sniff_head(b"\x00\x00\x00 ftypheic" + b"\x00" * 40) == "image/heic"
    assert mime.sniff_head(b"\x00\x00\x00 ftypmif1" + b"\x00" * 40) == "image/heif"
    assert mime.sniff_head(b"\x00\x00\x00\x1cftyp3gp5" + b"\x00" * 40) == "video/3gpp"


def test_mime_svg_bytes_outrank_an_element_address(tmp_path):
    # #149: an `el=` member's synthesized pseudo-filename is an element address, and
    # `mimetypes` reads its trailing `.3` as a man-page section. Bytes evidence runs first,
    # so the address can no longer type 304 inline SVGs as troff.
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"></svg>'
    assert mime.sniff_head(svg, "1.2.2.1.3.3") == "image/svg+xml"
    assert mime.sniff_head(svg, None) == "image/svg+xml"
    # And the address never reaches the sniffer as a name in the first place.
    assert containment.member_sniff_name("el=1.2.2.1.3.3") is None


def test_mime_extension_for():
    assert mime.extension_for("application/pdf") == "pdf"
    assert mime.extension_for("image/jpeg") == "jpg"
    assert mime.extension_for("application/x-ndjson") == "jsonl"
    assert mime.extension_for("audio/mp4") == "m4a"
    assert mime.extension_for("application/epub+zip") == "epub"


def test_mime_citation_surface_builtin_defaults():
    # The HTML family is `segments` (presentation soup — nav chrome, script payloads);
    # every other bundled type defaults to `raw` (the derived body IS faithful content).
    assert mime.citation_surface("text/html") == "segments"
    assert mime.citation_surface("application/xhtml+xml") == "segments"
    assert mime.citation_surface("application/json") == "raw"
    assert mime.citation_surface("text/csv") == "raw"
    assert mime.citation_surface("text/plain") == "raw"


def test_mime_citation_surface_schema_override(tmp_path):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()

    # No corpus_root in scope → the built-in default (raw) applies.
    assert mime.citation_surface("application/pdf") == "raw"

    local_pdf = root / "schema" / "mime" / "application" / "application_pdf.yaml"
    local_pdf.parent.mkdir(parents=True, exist_ok=True)
    local_pdf.write_text(
        "applies_to:\n  content_types: [application/pdf]\ncitation_surface: segments\n",
        encoding="utf-8",
    )
    schemas.cache_clear()
    # A corpus-declared `citation_surface:` on the mime schema wins over the built-in.
    assert mime.citation_surface("application/pdf", root) == "segments"


def test_urls_normalize_sorts_query_strips_fragment():
    a = urls.normalize("HTTPS://Example.COM:443/p?b=2&a=1#frag")
    b = urls.normalize("https://example.com/p?a=1&b=2")
    assert a == b
    assert "#" not in a


def test_urls_normalize_preserves_hash_route_fragment():
    # Hash-routed SPA: the fragment IS the route (a distinct resource), so it survives
    # canonicalization — and distinct routes stay distinct.
    one = urls.normalize("https://my.alldata.com/repair/#/vehicle/46076")
    two = urls.normalize("https://my.alldata.com/repair/#/vehicle/99999")
    assert one == "https://my.alldata.com/repair/#/vehicle/46076"
    assert one != two
    # hashbang routes preserved too
    assert urls.normalize("https://x.example/#!/path").endswith("#!/path")
    # plain anchor still dropped
    assert "#" not in urls.normalize("https://x.example/page#section")


def test_urls_is_crawlable_href():
    # Client-side routes are crawlable (the fragment is the route, mirrors normalize).
    assert urls.is_crawlable_href("#/vehicle/46076")
    assert urls.is_crawlable_href("#!/legacy/path")
    # Ordinary relative + absolute links, including absolutes carrying a hash-route.
    assert urls.is_crawlable_href("/rel/path")
    assert urls.is_crawlable_href("https://e.com/x")
    assert urls.is_crawlable_href("https://my.alldata.com/repair/#/vehicle/1")
    # Bare in-page anchors and non-navigational schemes are not crawlable.
    not_crawlable = (
        "", "  ", "#", "#section", "#top", "javascript:void(0)", "mailto:a@b.com", "tel:+1",
    )
    for href in not_crawlable:
        assert not urls.is_crawlable_href(href), href


def test_urls_same_domain_subdomain_match():
    assert urls.same_domain("https://x.example.com/p", "www.example.com", include_subdomains=True)
    assert not urls.same_domain("https://evilexample.com/p", "example.com", include_subdomains=True)


def test_urls_same_domain_apex_www_by_default():
    # apex ↔ www are the same site without --include-subdomains (the common cross-link).
    assert urls.same_domain("https://www.example.com/about", "example.com")
    assert urls.same_domain("https://example.com/about", "www.example.com")
    assert urls.same_domain("https://example.com/a", "example.com")
    # A different registrable name never matches.
    assert not urls.same_domain("https://other.com/x", "example.com")
    assert not urls.same_domain("https://evilexample.com/x", "example.com")
    # Deeper subdomains still require the opt-in flag.
    assert not urls.same_domain("https://api.example.com/p", "example.com")
    assert urls.same_domain("https://api.example.com/p", "example.com", include_subdomains=True)


def test_touches_coalesce_and_list_shape():
    post = frontmatter.Post("body")
    ident = touches.script_identifier("ingest")
    touches.record_touch(post, ident)
    assert post.metadata["touch"] == ident  # bare string when one entry
    touches.record_touch(post, ident)
    assert post.metadata["touch"] == f"{ident}_2"  # coalesced in place; still one entry
    other = touches.script_identifier("draft.mime/text/html")
    touches.record_touch(post, other)
    chain = post.metadata["touch"]
    assert isinstance(chain, list)
    assert chain == [f"{ident}_2", other]
    # Reset of suffix when identifier changes, then re-coalesce on repeat:
    touches.record_touch(post, other)
    assert post.metadata["touch"] == [f"{ident}_2", f"{other}_2"]


def test_touches_script_identifier_keeps_corpus_prefix():
    """Reconciliation #5: lint touch regex hardcodes the `corpus.` prefix; we keep it."""
    assert touches.script_identifier("ingest").startswith("corpus.")
