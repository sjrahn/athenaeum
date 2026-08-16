"""The `ref://` citation grammar (`spec/ledger.md` §6.5, §13.1 — v17's pin extension).

REF_URI_RE / SOURCE_REF_RE both group as (dataset, optional tag, id): a bare
citation resolves at the dataset's `latest`; `@{tag}` pins a registered
snapshot permanently. Grammar-level coverage only — dataset/tag registration
is `check`'s job (see test_ledger_check.py).
"""

from __future__ import annotations

from ledger.model import REF_URI_RE, SOURCE_REF_RE


def test_ref_uri_bare_form() -> None:
    m = REF_URI_RE.match("ref://wikipedia/Gorguts")
    assert m is not None
    assert m.group(1) == "wikipedia"
    assert m.group(2) is None
    assert m.group(3) == "Gorguts"


def test_ref_uri_pinned_form() -> None:
    m = REF_URI_RE.match("ref://wikipedia@2026-06/Gorguts")
    assert m is not None
    assert m.group(1) == "wikipedia"
    assert m.group(2) == "2026-06"
    assert m.group(3) == "Gorguts"


def test_ref_uri_id_may_contain_slashes() -> None:
    """The id tail is greedy — a dataset native id may itself carry `/`
    (an MBID-style compound key), bare and pinned alike."""
    m = REF_URI_RE.match("ref://musicbrainz/artist/deadbeef")
    assert m is not None
    assert m.group(1) == "musicbrainz"
    assert m.group(2) is None
    assert m.group(3) == "artist/deadbeef"
    m = REF_URI_RE.match("ref://musicbrainz@2026-01/artist/deadbeef")
    assert m is not None
    assert m.group(2) == "2026-01"
    assert m.group(3) == "artist/deadbeef"


def test_ref_uri_tag_capture_stops_at_slash() -> None:
    """The tag charset excludes '/' and '@' by construction (they ride in the
    URI as delimiters) — a literal '/' after '@' ends the tag, not extends
    it, so `check`'s tag-registration lookup can never see a slash in a tag."""
    m = REF_URI_RE.match("ref://wikipedia@2026/06/Gorguts")
    assert m is not None
    assert m.group(2) == "2026"
    assert m.group(3) == "06/Gorguts"


def test_source_ref_bare_and_pinned() -> None:
    m = SOURCE_REF_RE.match("wikipedia/Gorguts")
    assert m is not None
    assert (m.group(1), m.group(2), m.group(3)) == ("wikipedia", None, "Gorguts")
    m = SOURCE_REF_RE.match("wikipedia@2026-06/Gorguts")
    assert m is not None
    assert (m.group(1), m.group(2), m.group(3)) == ("wikipedia", "2026-06", "Gorguts")
