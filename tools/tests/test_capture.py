"""Capture tests — the pure helpers + the capture-stage detectors.

Playwright / yt-dlp / network paths are exercised only by the `network`-marked
end-to-end test (skipped by default). Everything here runs offline: URL
dispatch, viewport parsing, meta injection, SingleFile-bundle resolution (env
override, registered-asset resolution, and the disclosed rendered-DOM degrade,
spec §12.3.6), and the detector suite — including a conformance check that every
issue a detector emits is spec §4.3.3.1-shaped and carries a lint-valid touch
identifier.
"""

from __future__ import annotations

import blake3
import pytest
import yaml

from corpus import capture, touches
from corpus.lint import _TOUCH_RE

_VALID_SEVERITIES = {"blocking", "warning", "info"}


# Capturer routing (overlay `capturer:` + `--video`/`--no-video` overrides) is
# covered in test_capture_pluggable.py — there is no hardcoded host dispatch.


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


def test_inject_corpus_metadata_stamps_fidelity():
    out = capture._inject_corpus_metadata(
        "<html><head></head><body>x</body></html>",
        capture_url="https://e.com/p",
        fetched_at="2026-06-03T00:00:00Z",
        fidelity="lean",
    )
    assert '<meta name="corpus-fidelity" content="lean">' in out


# ---------- capture fidelity tiers ---------- #


def test_resolve_fidelity_default_is_balanced():
    # No CLI override, no recipe fidelity → the global default.
    assert capture._resolve_fidelity(None, {}) == "balanced"
    assert capture.DEFAULT_FIDELITY == "balanced"


def test_resolve_fidelity_from_recipe():
    assert capture._resolve_fidelity(None, {"fidelity": "lean"}) == "lean"
    # Case / whitespace tolerant.
    assert capture._resolve_fidelity(None, {"fidelity": " Exact "}) == "exact"


def test_resolve_fidelity_cli_overrides_recipe():
    assert capture._resolve_fidelity("exact", {"fidelity": "lean"}) == "exact"


def test_resolve_fidelity_unknown_falls_back_to_default(caplog):
    assert capture._resolve_fidelity("bogus", {}) == "balanced"
    assert capture._resolve_fidelity(None, {"fidelity": "ultra"}) == "balanced"


def test_singlefile_options_merge_per_tier():
    exact = capture._singlefile_options("exact")
    # exact == the base options, untouched.
    assert exact == capture.SINGLEFILE_OPTIONS
    assert exact is not capture.SINGLEFILE_OPTIONS  # a copy, not the shared dict

    balanced = capture._singlefile_options("balanced")
    assert balanced["removeAlternativeFonts"] is True
    assert balanced["removeAlternativeImages"] is True
    assert balanced["removeAlternativeMedias"] is True
    assert balanced["removeUnusedStyles"] is False  # balanced does NOT prune CSS

    lean = capture._singlefile_options("lean")
    assert lean["removeUnusedStyles"] is True
    assert lean["removeAlternativeFonts"] is True


def test_snapshot_html_passes_resolved_fidelity_to_singlefile(tmp_path):
    """The resolved tier's preset reaches `getPageData`'s options, and the tier is
    stamped into the snapshot for provenance. Closes the integration loop without a
    live browser: a fake page records the opts handed to `page.evaluate`."""
    bundle = tmp_path / "sf.js"
    bundle.write_text("// fake bundle", encoding="utf-8")
    seen: dict = {}

    class _FakePage:
        url = "https://e.com/p"

        def add_script_tag(self, *, content):  # bundle inject is a no-op here
            pass

        def evaluate(self, _js, opts=None):
            seen["opts"] = opts
            return {"content": "<html><head></head><body>x</body></html>", "title": "T"}

    out = capture._snapshot_html(
        page=_FakePage(), fetched_at="2026-06-03T00:00:00Z", bundle=bundle, fidelity="lean"
    )
    # lean preset reached SingleFile...
    assert seen["opts"]["removeUnusedStyles"] is True
    assert seen["opts"]["removeAlternativeImages"] is True
    # ...and the resolved tier is recorded in the artifact.
    assert '<meta name="corpus-fidelity" content="lean">' in out


# ---------- SingleFile bundle resolution (spec §12.3.6) ---------- #


def _write_instance(tmp_path, *, assets_yaml: str = ""):
    """A minimal instance: `athenaeum.yaml` at the root (carrying `assets_yaml`,
    already the full `assets:` block text or empty) + an empty `corpus/` beneath
    it. Returns `(instance_root, corpus_root)`."""
    instance = tmp_path / "instance"
    corpus_root = instance / "corpus"
    corpus_root.mkdir(parents=True)
    (instance / "athenaeum.yaml").write_text(assets_yaml, encoding="utf-8")
    return instance, corpus_root


def test_resolve_singlefile_bundle_env(tmp_path, monkeypatch):
    bundle = tmp_path / "sf.js"
    bundle.write_text("// bundle", encoding="utf-8")
    monkeypatch.setenv("CORPUS_SINGLEFILE_BUNDLE", str(bundle))
    resolved = capture._resolve_singlefile_bundle(tmp_path)
    assert resolved.path == bundle
    assert resolved.engine.startswith("singlefile@env blake3:")


def test_resolve_singlefile_bundle_env_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CORPUS_SINGLEFILE_BUNDLE", str(tmp_path / "nope.js"))
    # A set-but-missing env override is a hard miss — no fallthrough to a registered
    # asset even if one exists.
    assert capture._resolve_singlefile_bundle(tmp_path) is None


def test_resolve_singlefile_bundle_no_instance_or_asset(tmp_path, monkeypatch):
    """No env, no instance config above `corpus_root` → degrade (None)."""
    monkeypatch.delenv("CORPUS_SINGLEFILE_BUNDLE", raising=False)
    corpus_root = tmp_path / "bare-corpus"
    corpus_root.mkdir()
    assert capture._resolve_singlefile_bundle(corpus_root) is None


def test_resolve_singlefile_bundle_no_asset_registered(tmp_path, monkeypatch):
    """An instance config with no `assets:` block (or none named `singlefile`) is
    an ordinary miss, not an error."""
    monkeypatch.delenv("CORPUS_SINGLEFILE_BUNDLE", raising=False)
    _instance, corpus_root = _write_instance(tmp_path, assets_yaml="name: test\n")
    assert capture._resolve_singlefile_bundle(corpus_root) is None


def test_resolve_singlefile_bundle_registered_asset(tmp_path, monkeypatch):
    """The registered `assets.singlefile` `latest` tag resolves to its artifact
    blake3, materialized from the co-located `artifacts/<shard>/` tree."""
    monkeypatch.delenv("CORPUS_SINGLEFILE_BUNDLE", raising=False)
    payload = b"(() => { window.singlefile = {}; })();"
    digest = blake3.blake3(payload).hexdigest()
    _instance, corpus_root = _write_instance(
        tmp_path,
        assets_yaml=yaml.safe_dump(
            {
                "assets": {
                    "singlefile": {
                        "latest": "v1",
                        "snapshots": {"v1": {"artifact": digest}},
                    }
                }
            }
        ),
    )
    shard_dir = corpus_root / "artifacts" / digest[:2]
    shard_dir.mkdir(parents=True)
    (shard_dir / f"{digest}.js").write_bytes(payload)

    resolved = capture._resolve_singlefile_bundle(corpus_root)
    assert resolved is not None
    assert resolved.path == shard_dir / f"{digest}.js"
    assert resolved.engine == f"singlefile@v1 blake3:{digest}"


def test_resolve_singlefile_bundle_registered_asset_not_materialized(tmp_path, monkeypatch):
    """Registered but its bytes aren't on disk anywhere this corpus root resolves —
    a degrade (None), not a crash."""
    monkeypatch.delenv("CORPUS_SINGLEFILE_BUNDLE", raising=False)
    digest = "ab" * 32
    _instance, corpus_root = _write_instance(
        tmp_path,
        assets_yaml=yaml.safe_dump(
            {"assets": {"singlefile": {"latest": "v1", "snapshots": {"v1": {"artifact": digest}}}}}
        ),
    )
    assert capture._resolve_singlefile_bundle(corpus_root) is None


def test_resolve_singlefile_bundle_env_beats_registered_asset(tmp_path, monkeypatch):
    """The env override is checked first, exactly as documented — it wins even
    when a registered asset also resolves."""
    payload = b"(() => {})();"
    digest = blake3.blake3(payload).hexdigest()
    _instance, corpus_root = _write_instance(
        tmp_path,
        assets_yaml=yaml.safe_dump(
            {"assets": {"singlefile": {"latest": "v1", "snapshots": {"v1": {"artifact": digest}}}}}
        ),
    )
    shard_dir = corpus_root / "artifacts" / digest[:2]
    shard_dir.mkdir(parents=True)
    (shard_dir / f"{digest}.js").write_bytes(payload)

    env_bundle = tmp_path / "env-sf.js"
    env_bundle.write_text("// env bundle", encoding="utf-8")
    monkeypatch.setenv("CORPUS_SINGLEFILE_BUNDLE", str(env_bundle))
    resolved = capture._resolve_singlefile_bundle(corpus_root)
    assert resolved.path == env_bundle
    assert resolved.engine.startswith("singlefile@env ")


# ---------- SingleFile bundle format: upstream module form vs. direct IIFE ---------- #


def test_unwrap_bundle_source_module_form():
    """The upstream `single-file-bundle.js` module form (`const script = "...";
    const ...`) is unwrapped to its decoded JS text."""
    raw = 'const script = "console.log(1);"; const foo = 1;'
    assert capture._unwrap_bundle_source(raw) == "console.log(1);"


def test_unwrap_bundle_source_module_form_export():
    raw = 'const script = "console.log(2);"; export { script };'
    assert capture._unwrap_bundle_source(raw) == "console.log(2);"


def test_unwrap_bundle_source_direct_iife_passes_through():
    raw = "(() => { window.singlefile = {}; })();"
    assert capture._unwrap_bundle_source(raw) == raw


# ---------- snapshot-engine degrade disclosure (spec §12.3.6) ---------- #


def test_snapshot_engine_issue_on_degrade():
    issue = capture._snapshot_engine_issue(capture.SNAPSHOT_ENGINE_DEGRADED, detector_id=_DET)
    assert issue is not None
    assert issue["id"] == "snapshot-engine-degraded"
    assert issue["severity"] in _VALID_SEVERITIES
    assert issue["fields"]["snapshot_engine"] == "rendered-dom"


def test_snapshot_engine_issue_none_when_resolved():
    resolved = "singlefile@v1 blake3:" + "ab" * 32
    assert capture._snapshot_engine_issue(resolved, detector_id=_DET) is None
    assert capture._snapshot_engine_issue(None, detector_id=_DET) is None


def test_run_capture_detectors_flags_degraded_snapshot_engine():
    issues = capture._run_capture_detectors(
        snapshot="<html><body>fine</body></html>",
        request_url="https://example.com/a",
        final_url="https://example.com/a",
        response_status=200,
        image_stats=(0, 0),
        snapshot_engine=capture.SNAPSHOT_ENGINE_DEGRADED,
    )
    assert any(i["id"] == "snapshot-engine-degraded" for i in issues)


def test_run_capture_detectors_silent_when_engine_resolved():
    issues = capture._run_capture_detectors(
        snapshot="<html><body>fine</body></html>",
        request_url="https://example.com/a",
        final_url="https://example.com/a",
        response_status=200,
        image_stats=(0, 0),
        snapshot_engine="singlefile@v1 blake3:" + "ab" * 32,
    )
    assert not any(i["id"] == "snapshot-engine-degraded" for i in issues)


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


def test_detect_captcha_css_class_does_not_fire():
    # Regression: a `.g-recaptcha` / `.h-captcha` CSS RULE in an inlined stylesheet (styling a
    # login form's captcha — often chrome that's been removed) is NOT a challenge page. The
    # bare class token must appear in a `class="…"` attribute to count.
    snap = (
        "<html><head><style>.login-form-side .g-recaptcha{margin-top:10px}"
        ".h-captcha{display:none}</style></head><body>real article text</body></html>"
    )
    assert capture._detect_captcha(snapshot=snap, detector_id=_DET) is None


def test_detect_captcha_element_class_fires():
    # A real widget — the class in an actual element attribute — still fires.
    snap = '<html><body><div class="g-recaptcha" data-sitekey="x"></div></body></html>'
    issue = capture._detect_captcha(snapshot=snap, detector_id=_DET)
    assert issue is not None
    assert issue["subtype"] == "captcha"


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


def test_detect_redirect_drift_rewrite_target_is_not_drift():
    # Drift is measured against the rewritten nav target (capture now passes request_url=
    # nav_url), not the pre-rewrite URL. A url_rewrite that changes host (www.reddit ->
    # old.reddit) and lands exactly there is NOT drift. Regression for the wiring fix.
    assert capture._detect_final_url_drift(
        request_url="https://old.reddit.com/r/x/comments/1/t/?sort=top&limit=500",
        final_url="https://old.reddit.com/r/x/comments/1/t/?sort=top&limit=500",
        detector_id=_DET,
    ) is None


def test_detect_inline_image_failure_thresholds():
    assert capture._detect_inline_image_failure(image_stats=(0, 0), detector_id=_DET) is None
    assert capture._detect_inline_image_failure(image_stats=(9, 1), detector_id=_DET) is None  # 10%
    warn = capture._detect_inline_image_failure(image_stats=(1, 9), detector_id=_DET)  # 90%
    assert warn is not None and warn["severity"] == "warning"
    info = capture._detect_inline_image_failure(image_stats=(7, 3), detector_id=_DET)  # 30%
    assert info is not None and info["severity"] == "info"


def test_inline_image_srcs_cross_origin_self_referer():
    """Cross-origin <img> fetches get a same-origin (self) referer so hotlink-protecting
    hosts serve the un-degraded original; same-origin images are fetched unchanged."""
    items = [
        {"idx": 0, "src": "https://forum.example/attachments/a.jpg"},  # same-origin
        {"idx": 1, "src": "http://iX.photobucket.com/albums/u/x.jpg"},  # cross-origin
    ]

    class _FakeResp:
        status = 200

        def __init__(self):
            self.headers = {"content-type": "image/jpeg"}

        def body(self):
            return b"\xff\xd8\xff\xe0jpeg"

    calls: list[tuple] = []

    class _FakeReq:
        def get(self, url, headers=None, timeout=None):
            calls.append((url, dict(headers or {})))
            return _FakeResp()

    class _FakePage:
        url = "https://forum.example/thread/1"

        def __init__(self):
            self._served_items = False

        def evaluate(self, _js, arg=None):
            if not self._served_items:
                self._served_items = True
                return items
            return None  # the set-src evaluate

    inlined, failed = capture._inline_image_srcs(page=_FakePage(), request_api=_FakeReq())
    assert (inlined, failed) == (2, 0)
    by_url = dict(calls)
    # same-origin attachment: no forged referer
    assert "referer" not in by_url["https://forum.example/attachments/a.jpg"]
    # cross-origin image: referer is the image's OWN origin (not the embedding page)
    assert by_url["http://iX.photobucket.com/albums/u/x.jpg"]["referer"] == (
        "http://iX.photobucket.com/"
    )


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
