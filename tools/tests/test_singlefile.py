"""SingleFile banner provenance — the pure parser (corpus.singlefile) and the
banner tier of ingest's origin derivation (`_derive_capture_origin`, §12.3.4)."""

from __future__ import annotations

from corpus import singlefile
from corpus._cli.ingest import _derive_capture_origin

# A real SingleFile save's opening bytes: the banner comment sits just inside
# `<html …>`, values padded with a trailing space before the newline.
_BANNER_HEAD = (
    "<!DOCTYPE html> <html xmlns=http://www.w3.org/1999/xhtml><!--\n"
    " Page saved with SingleFile \n"
    " url: https://www.albertahealthservices.ca/webapps/labservices/indexAPL.asp"
    "?id=9066&tests=&zoneid=1&details=true \n"
    " saved date: Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)\n"
    "--><meta charset=utf-8>\n"
    "<title>Alberta Precision Laboratories | Lab Services</title>\n"
)
_BANNER_URL = (
    "https://www.albertahealthservices.ca/webapps/labservices/indexAPL.asp"
    "?id=9066&tests=&zoneid=1&details=true"
)


# ---------- the saved-date parse (JS Date.toString → ISO-8601, offset kept) ---------- #


def test_parse_saved_date_preserves_numeric_offset_no_utc_conversion():
    # The instant is NOT converted to UTC; the numeric offset is preserved and the
    # parenthesized zone name is ignored.
    got = singlefile.parse_saved_date("Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)")
    assert got == "2026-07-06T13:48:48-06:00"


def test_parse_saved_date_positive_offset():
    got = singlefile.parse_saved_date("Sun Jan 04 2026 09:05:00 GMT+0530 (India Standard Time)")
    assert got == "2026-01-04T09:05:00+05:30"


def test_parse_saved_date_rejects_junk():
    assert singlefile.parse_saved_date("not a date") is None
    assert singlefile.parse_saved_date("") is None
    # A JS date with no GMT offset is not the toString() shape we accept.
    assert singlefile.parse_saved_date("Mon Jul 06 2026 13:48:48") is None


# ---------- the banner parse ---------- #


def test_parse_banner_extracts_url_and_iso_date():
    got = singlefile.parse_banner(_BANNER_HEAD)
    assert got == (_BANNER_URL, "2026-07-06T13:48:48-06:00")


def test_parse_banner_none_without_banner():
    assert singlefile.parse_banner("<html><head><title>plain</title></head>") is None


def test_parse_banner_requires_parseable_date():
    # A banner whose saved date is malformed is declined (both fields are required).
    head = _BANNER_HEAD.replace(
        "Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)", "sometime yesterday"
    )
    assert singlefile.parse_banner(head) is None


def test_banner_origin_reads_bounded_head(tmp_path):
    src = tmp_path / "save.html"
    # Pad far past the head window to prove the banner is found in the head, not the tail.
    src.write_text(_BANNER_HEAD + "<div>" + "x" * 20000 + "</div>", encoding="utf-8")
    assert singlefile.banner_origin(src) == (_BANNER_URL, "2026-07-06T13:48:48-06:00")


def test_banner_origin_none_for_bannerless(tmp_path):
    src = tmp_path / "plain.html"
    src.write_text("<html><body>no banner here</body></html>", encoding="utf-8")
    assert singlefile.banner_origin(src) is None


# ---------- _derive_capture_origin: the three tiers ---------- #


def test_derive_origin_banner_tier_seeds_retrieval_origin(tmp_path):
    """An HTML SingleFile save with no sidecar → a RETRIEVAL origin from the banner:
    uri = banner url, snapshot = banner saved date (not the ingest observation time)."""
    src = tmp_path / "save.html"
    src.write_text(_BANNER_HEAD, encoding="utf-8")
    uri, snapshot, fields, schema_id = _derive_capture_origin(src, {}, "text/html")
    assert uri == _BANNER_URL
    assert snapshot == "2026-07-06T13:48:48-06:00"
    assert fields == {}  # no local-file metadata on a retrieval origin
    assert schema_id is None


def test_derive_origin_sidecar_source_url_beats_banner(tmp_path):
    """An explicit sidecar `source_url` still wins over the banner (tier 1 > tier 2)."""
    src = tmp_path / "save.html"
    src.write_text(_BANNER_HEAD, encoding="utf-8")
    sidecar = {"source_url": "https://example.com/override", "fetched_at": "2026-06-29T00:00:00Z"}
    uri, snapshot, fields, _schema = _derive_capture_origin(src, sidecar, "text/html")
    assert uri == "https://example.com/override"
    assert snapshot == "2026-06-29T00:00:00Z"
    assert fields == {}


def test_derive_origin_bannerless_html_falls_back_to_local_file(tmp_path):
    """HTML with no banner and no sidecar → the uri-less local-file origin (tier 3)."""
    src = tmp_path / "plain.html"
    src.write_text("<html><body>no banner</body></html>", encoding="utf-8")
    uri, snapshot, fields, schema_id = _derive_capture_origin(src, {}, "text/html")
    assert uri is None
    assert fields["filename"] == "plain.html"
    assert fields["source_modified"].endswith("Z")
    assert snapshot  # ingest observation time
    assert schema_id is None


def test_derive_origin_banner_gated_on_html_media_type(tmp_path):
    """The banner tier fires only for text/html. A file whose bytes happen to carry
    banner-shaped text but is not detected as HTML falls through to the local-file tier."""
    src = tmp_path / "notes.txt"
    src.write_text(_BANNER_HEAD, encoding="utf-8")
    uri, _snap, fields, _schema = _derive_capture_origin(src, {}, "text/plain")
    assert uri is None
    assert fields["filename"] == "notes.txt"
