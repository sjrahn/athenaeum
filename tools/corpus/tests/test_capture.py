"""Capture tests — the pure helpers + the capture-stage detectors.

Playwright / yt-dlp / network paths are exercised only by the `network`-marked
end-to-end test (skipped by default). Everything here runs offline: URL
dispatch, viewport parsing, meta injection, SingleFile-bundle resolution, and
the detector suite — including a conformance check that every issue a detector
emits is spec §4.3.3.1-shaped and carries a lint-valid touch identifier.
"""

from __future__ import annotations

import pytest

from corpus import capture, touches
from corpus.lint import _TOUCH_RE

_VALID_SEVERITIES = {"blocking", "warning", "info"}


# ---------- video dispatch ---------- #


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc", True),
        ("https://youtu.be/abc", True),
        ("https://vimeo.com/123", True),
        ("https://music.youtube.com/watch?v=x", True),
        ("https://example.com/video.html", False),
        ("https://notyoutube.com/x", False),
    ],
)
def test_should_use_video_host_match(url, expected):
    assert capture._should_use_video(url, force=False, skip=False) is expected


def test_should_use_video_force_and_skip_override():
    assert capture._should_use_video("https://example.com/x", force=True, skip=False) is True
    assert capture._should_use_video("https://youtu.be/x", force=False, skip=True) is False


def test_should_use_video_mutually_exclusive():
    with pytest.raises(capture.CaptureError):
        capture._should_use_video("https://x.com", force=True, skip=True)


def test_should_use_video_extra_hosts():
    # #15: a corpus-configured host routes to yt-dlp without editing the packaged set.
    url = "https://peertube.example/w/abc"
    assert capture._should_use_video(url, force=False, skip=False) is False
    assert (
        capture._should_use_video(
            url, force=False, skip=False, extra_hosts=frozenset({"peertube.example"})
        )
        is True
    )
    # Packaged defaults still match with no extra hosts.
    assert capture._should_use_video("https://youtube.com/watch?v=x", force=False, skip=False)


# ---------- small pure helpers ---------- #


def test_parse_viewport_valid():
    assert capture.parse_viewport("1280x900") == (1280, 900)
    assert capture.parse_viewport("  800 x 600 ") == (800, 600)


def test_parse_viewport_invalid():
    with pytest.raises(ValueError):
        capture.parse_viewport("not-a-viewport")


def test_sanitize_filename():
    # netloc + path only — the query string is not part of the staged filename.
    assert capture._sanitize_filename("https://example.com/a/b?c=d") == "example.com-a-b"
    assert capture._sanitize_filename("https://example.com/") == "example.com"
    # Truncates long names.
    long = "https://example.com/" + "x" * 300
    assert len(capture._sanitize_filename(long)) <= 120


def test_inject_corpus_metadata_with_head():
    html = "<html><head><title>T</title></head><body>x</body></html>"
    out = capture._inject_corpus_metadata(
        html, capture_url="https://e.com/p", fetched_at="2026-05-31T00:00:00Z"
    )
    assert '<meta name="corpus-capture-url" content="https://e.com/p">' in out
    assert '<meta name="corpus-fetched-at" content="2026-05-31T00:00:00Z">' in out
    # Injected right after the existing <head>, not in a synthetic one.
    assert out.count("<head>") == 1


def test_inject_corpus_metadata_without_head():
    html = "<html><body>x</body></html>"
    out = capture._inject_corpus_metadata(
        html, capture_url="https://e.com/p", fetched_at="2026-05-31T00:00:00Z"
    )
    assert out.startswith("<head>")
    assert "corpus-capture-url" in out


def test_attr_escape():
    assert capture._attr_escape('a&b"c<d') == "a&amp;b&quot;c&lt;d"


# ---------- SingleFile bundle resolution ---------- #


def test_resolve_singlefile_bundle_env(tmp_path, monkeypatch):
    bundle = tmp_path / "sf.js"
    bundle.write_text("// bundle", encoding="utf-8")
    monkeypatch.setenv("CORPUS_SINGLEFILE_BUNDLE", str(bundle))
    assert capture._resolve_singlefile_bundle() == bundle


def test_resolve_singlefile_bundle_env_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_SINGLEFILE_BUNDLE", str(tmp_path / "nope.js"))
    assert capture._resolve_singlefile_bundle() is None


def test_resolve_singlefile_bundle_absent_default(monkeypatch):
    """No env + no vendored bundle committed → None (capture degrades gracefully)."""
    monkeypatch.delenv("CORPUS_SINGLEFILE_BUNDLE", raising=False)
    # The packaged bundle is gitignored / not committed, so this is None in CI.
    # If a developer has dropped one in locally, it's a Path — accept both.
    result = capture._resolve_singlefile_bundle()
    assert result is None or result.name == "single-file.js"


# ---------- capture-stage detectors ---------- #

_DET = "corpus.capture@test"


def test_detect_login_wall():
    snap = "<html><head><title>Sign in</title></head><body>please sign in</body></html>"
    issue = capture._detect_login_wall(snapshot=snap, detector_id=_DET)
    assert issue is not None
    assert issue["id"] == "partial-content"
    assert issue["subtype"] == "login-wall"
    assert issue["severity"] == "warning"


def test_detect_paywall():
    snap = "<html><body><p>Subscribe to read the rest of this article.</p></body></html>"
    issue = capture._detect_paywall(snapshot=snap, detector_id=_DET)
    assert issue is not None
    assert issue["subtype"] == "paywall"
    assert issue["severity"] == "warning"


def test_detect_paywall_marker():
    snap = '<html><body><div class="paywall-overlay">x</div></body></html>'
    issue = capture._detect_paywall(snapshot=snap, detector_id=_DET)
    assert issue is not None
    assert issue["fields"]["signature"] == "paywall-marker"
    # #17: the HTML-class marker alone is informational, not a warning.
    assert issue["severity"] == "info"
    assert issue["resolution"] == "open"


def test_detect_login_wall_partial_title_does_not_fire():
    # #16: an article whose title merely STARTS with "Sign in" is not a login wall; the
    # title regex is end-anchored, and the body carries no login-prose.
    snap = (
        "<html><head><title>Sign in sheets for events: a complete guide</title></head>"
        "<body>Here is how to make printable attendance sheets for your event.</body></html>"
    )
    issue = capture._detect_login_wall(snapshot=snap, detector_id=_DET)
    assert issue is None


def test_detect_captcha_recaptcha():
    snap = '<html><head><script src="https://www.google.com/recaptcha/api.js"></script></head><body>x</body></html>'
    issue = capture._detect_captcha(snapshot=snap, detector_id=_DET)
    assert issue is not None
    assert issue["subtype"] == "captcha"
    assert issue["severity"] == "blocking"


def test_detect_http_error_with_200_body():
    snap = (
        "<html><head><title>404 Not Found</title></head>"
        "<body>The requested URL was not found on this server.</body></html>"
    )
    issue = capture._detect_http_error_with_200_body(
        snapshot=snap, response_status=200, detector_id=_DET
    )
    assert issue is not None
    assert issue["subtype"] == "http-error"
    assert issue["severity"] == "blocking"
    assert issue["fields"]["http_status"] == 200


def test_detect_http_error_only_on_200():
    snap = (
        "<html><head><title>404 Not Found</title></head>"
        "<body>was not found on this server</body></html>"
    )
    result = capture._detect_http_error_with_200_body(
        snapshot=snap, response_status=404, detector_id=_DET
    )
    assert result is None


def test_detect_redirect_drift_path():
    issue = capture._detect_final_url_drift(
        request_url="https://example.com/articles/the-thing",
        final_url="https://example.com/login",
        detector_id=_DET,
    )
    assert issue is not None
    assert issue["subtype"] == "redirect-drift"
    assert issue["fields"]["drift"] == "login-redirect"


def test_detect_redirect_drift_hostname():
    issue = capture._detect_final_url_drift(
        request_url="https://example.com/a",
        final_url="https://elsewhere.com/a",
        detector_id=_DET,
    )
    assert issue is not None
    assert issue["fields"]["drift"] == "hostname-change"


def test_detect_redirect_drift_canonical_noop():
    # www <-> apex + trailing slash is canonical, not drift.
    assert capture._detect_final_url_drift(
        request_url="https://example.com/page",
        final_url="https://www.example.com/page",
        detector_id=_DET,
    ) is None


def test_detect_inline_image_failure_thresholds():
    assert capture._detect_inline_image_failure(image_stats=(0, 0), detector_id=_DET) is None
    assert capture._detect_inline_image_failure(image_stats=(9, 1), detector_id=_DET) is None  # 10%
    warn = capture._detect_inline_image_failure(image_stats=(1, 9), detector_id=_DET)  # 90%
    assert warn is not None and warn["severity"] == "warning"
    info = capture._detect_inline_image_failure(image_stats=(7, 3), detector_id=_DET)  # 30%
    assert info is not None and info["severity"] == "info"


def test_run_capture_detectors_multiple_fire():
    # A page that both redirected to a paywall surface AND carries paywall prose.
    snap = "<html><body><p>Subscribe to continue reading this story.</p></body></html>"
    issues = capture._run_capture_detectors(
        snapshot=snap,
        request_url="https://example.com/news/story",
        final_url="https://example.com/subscribe",
        response_status=200,
        image_stats=(0, 0),
    )
    subtypes = {i.get("subtype") for i in issues}
    assert "paywall" in subtypes
    assert "redirect-drift" in subtypes


# ---------- conformance: detectors emit spec §4.3.3.1-shaped issues ---------- #


def test_detector_issues_are_spec_shaped_and_lint_valid():
    """Every issue any detector emits must be record-/segment-shapeable: a
    non-empty id, a valid severity, and a detector that passes the lint touch
    regex. `corpus.capture@<version>` is the real id used in production."""
    snapshots = [
        # kwargs for _run_capture_detectors — each trips at least one detector.
        dict(
            snapshot="<title>Sign in</title>",
            request_url="https://e.com/a",
            final_url="https://e.com/login",
            response_status=200,
            image_stats=(1, 9),
        ),
        dict(
            snapshot='<script src="https://hcaptcha.com/1/api.js"></script>',
            request_url="https://e.com/a",
            final_url="https://other.com/a",
            response_status=200,
            image_stats=(0, 0),
        ),
        dict(
            snapshot="<title>404 Not Found</title> was not found on this server",
            request_url="https://e.com/a",
            final_url="https://e.com/a",
            response_status=200,
            image_stats=(0, 0),
        ),
    ]
    real_detector = touches.script_identifier("capture")
    assert _TOUCH_RE.match(real_detector), (
        f"production detector id {real_detector!r} must lint-validate"
    )

    total = 0
    for kw in snapshots:
        for issue in capture._run_capture_detectors(**kw):
            total += 1
            assert isinstance(issue["id"], str) and issue["id"]
            assert issue["severity"] in _VALID_SEVERITIES
            assert _TOUCH_RE.match(issue["detector"]), issue["detector"]
            assert isinstance(issue.get("fields", {}), dict)
    assert total >= 3  # each snapshot trips at least one detector


# ---------- capture → ingest seam (offline via the short-circuit) ---------- #


def test_capture_and_ingest_shortcircuits_existing_url(tmp_path):
    """A URL already in some record's origin URIs returns that record without
    launching a browser — so this exercises the capture→ingest wiring offline
    (a real fetch would need Playwright + network)."""
    import frontmatter

    from corpus import paths, records

    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    rid = "f0" * 32
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html")
    records.append_origin_block(
        post, uri="https://example.com/seen", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))

    out = capture.capture_and_ingest(
        "https://example.com/seen", corpus_root=root, opts=capture.CaptureOptions(force=False)
    )
    assert out == paths.record_path(root, rid)


# ---------- network end-to-end (skipped by default) ---------- #


@pytest.mark.network
def test_capture_end_to_end_html(tmp_path):
    """Requires [capture] + network. Captures a real page → stub with origin."""
    from corpus import paths, records, scaffold

    root = scaffold.scaffold(tmp_path / "c", namespace="document")
    rec = capture.capture_and_ingest("https://example.com/", corpus_root=root)
    assert rec is not None and rec.is_file()
    post = records.load(rec)
    assert records.media_type_for(post) == "text/html"
    assert records.primary_origin_uri(post).startswith("https://example.com")
    del paths  # silence unused in the skipped path
