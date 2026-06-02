"""Pluggable, origin-routed capture: interaction engine, recipe resolution,
router order, and config default_transport. All deterministic — no browser/network."""

from __future__ import annotations

from pathlib import Path

import pytest

import corpus.capture as capture
from corpus import config
from corpus.capture import interactions, recipes

# ---------- fake Playwright page (records calls) ---------- #


class _FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def click(self, timeout=0):
        self.page.calls.append(("click", self.selector))

    def hover(self, timeout=0):
        self.page.calls.append(("hover", self.selector))


class _FakePage:
    def __init__(self):
        self.calls: list[tuple] = []

    def evaluate(self, js):
        self.calls.append(("evaluate", str(js)[:16]))

    def wait_for_timeout(self, ms):
        self.calls.append(("wait_for_timeout", ms))

    def wait_for_selector(self, selector, timeout=0):
        self.calls.append(("wait_for_selector", selector))

    def locator(self, selector):
        return _FakeLocator(self, selector)


# ---------- interaction engine ---------- #


def test_interactions_default_steps_run():
    page = _FakePage()
    interactions.run(page, None)  # DEFAULT_STEPS = scroll, expand:all, scroll
    assert [c[0] for c in page.calls].count("evaluate") == 3
    assert page.calls[-1] == ("wait_for_timeout", 2000)  # settle


def test_interactions_click_repeats():
    page = _FakePage()
    interactions.run(page, [{"click": {"selector": ".next", "repeat": 3, "delay_ms": 0}}])
    clicks = [c for c in page.calls if c[0] == "click"]
    assert len(clicks) == 3 and clicks[0] == ("click", ".next")


def test_interactions_click_shorthand():
    page = _FakePage()
    interactions.run(page, [{"click": ".more"}])
    assert ("click", ".more") in page.calls


def test_interactions_best_effort_continues_past_failure():
    class Boom(_FakePage):
        def evaluate(self, js):
            raise RuntimeError("boom")

    page = Boom()
    interactions.run(page, [{"scroll": "full"}, {"wait": {"ms": 5}}])
    # scroll's evaluate raised, but the wait step still executed
    assert ("wait_for_timeout", 5) in page.calls


def test_interactions_skips_malformed_step():
    page = _FakePage()
    interactions.run(page, [{"a": 1, "b": 2}, {"wait": {"ms": 7}}])  # first is malformed (2 keys)
    assert ("wait_for_timeout", 7) in page.calls


def test_interactions_remove_step():
    captured: list[str] = []

    class _CapturePage(_FakePage):
        def evaluate(self, js):
            captured.append(str(js))

    page = _CapturePage()
    interactions.run(page, [{"remove": [".side", "#header"]}])
    assert len(captured) == 1
    js = captured[0]
    # selectors embedded into a self-contained arrow fn that deletes matches
    assert ".side" in js and "#header" in js and ".remove()" in js


def test_interactions_remove_string_shorthand():
    captured: list[str] = []

    class _CapturePage(_FakePage):
        def evaluate(self, js):
            captured.append(str(js))

    page = _CapturePage()
    interactions.run(page, [{"remove": ".ad-banner"}])
    assert len(captured) == 1 and ".ad-banner" in captured[0]


def test_interactions_remove_empty_is_noop():
    page = _FakePage()
    interactions.run(page, [{"remove": []}])  # nothing to remove → no evaluate
    assert [c[0] for c in page.calls].count("evaluate") == 0


# ---------- per-host url rewrite ---------- #


def test_apply_url_rewrite():
    base = "https://my.alldata.com/repair/#/vehicle/46076/component/3926/itype/421/nonstandard/1272273/isSelfReferenceLink/false"
    recipe = {
        "url_rewrite": [
            {"pattern": r"#/vehicle/(.+/nonstandard/.+)$", "replacement": r"#/article/\1"}
        ]
    }
    # nonstandard leaf → rewritten vehicle→article
    assert capture._apply_url_rewrite(base, recipe).endswith(
        "#/article/46076/component/3926/itype/421/nonstandard/1272273/isSelfReferenceLink/false"
    )
    # a non-leaf route (no /nonstandard/) is left untouched by the guard
    index = "https://my.alldata.com/repair/#/vehicle/46076"
    assert capture._apply_url_rewrite(index, recipe) == index
    # no rules / no recipe → identity; a bad pattern is skipped, not raised
    assert capture._apply_url_rewrite(base, {}) == base
    assert capture._apply_url_rewrite(base, {"url_rewrite": [{"pattern": "("}]}) == base


# ---------- recipe resolution ---------- #


def _corpus(tmp_path, **overlays):
    """Write per-host origin overlays under schema/origin/ — each `name=body` is the
    overlay YAML (applies_to + optional `capture:` section). Always seeds the universal
    origin.yaml so the overlay loader layers exactly as it does in a real corpus."""
    d = tmp_path / "schema" / "origin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "origin.yaml").write_text("description: test\nextended_fields: {}\n", encoding="utf-8")
    for name, body in overlays.items():
        (d / f"{name}.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_recipe_match_and_miss(tmp_path):
    root = _corpus(
        tmp_path,
        ig="applies_to: {host_pattern: instagram.com, include_subdomains: true}\n"
        "capture: {transport: cdp}\n",
    )
    r = recipes.capture_recipe_for_url(root, "https://www.instagram.com/p/x/")
    assert r and r["transport"] == "cdp"  # subdomain www matched
    assert recipes.capture_recipe_for_url(root, "https://example.com") is None


def test_recipe_specificity_beats_catchall(tmp_path):
    root = _corpus(
        tmp_path,
        star="applies_to: {host_pattern: '*'}\ncapture: {transport: headless}\n",
        ig="applies_to: {host_pattern: instagram.com}\ncapture: {transport: cdp}\n",
    )
    assert recipes.capture_recipe_for_url(root, "https://instagram.com/x")["transport"] == "cdp"
    assert recipes.capture_recipe_for_url(root, "https://other.com")["transport"] == "headless"


# ---------- router order ---------- #


def test_router_recipe_selects_capturer(tmp_path):
    root = _corpus(
        tmp_path, x="applies_to: {host_pattern: example.com}\ncapture: {capturer: video}\n"
    )
    fn, recipe = capture.get_capturer(root, "https://example.com", opts=capture.CaptureOptions())
    assert fn is capture.REGISTRY["video"] and recipe["capturer"] == "video"


def test_router_default_is_browser_no_host_knowledge(tmp_path):
    # No overlay, no flags → browser for ANY host (no hardcoded video-host list).
    root = _corpus(tmp_path)
    opts = capture.CaptureOptions()
    fn_yt, _ = capture.get_capturer(root, "https://youtube.com/watch?v=x", opts=opts)
    fn_ex, _ = capture.get_capturer(root, "https://example.com", opts=opts)
    assert fn_yt is capture.REGISTRY["browser"]
    assert fn_ex is capture.REGISTRY["browser"]


def test_router_video_flag_forces_video(tmp_path):
    # --video routes an un-overlay'd URL to yt-dlp.
    root = _corpus(tmp_path)
    fn, _ = capture.get_capturer(
        root, "https://example.com", opts=capture.CaptureOptions(video=True)
    )
    assert fn is capture.REGISTRY["video"]


def test_router_cli_flags_override_overlay_capturer(tmp_path):
    # --no-video beats an overlay that declares capturer: video.
    root = _corpus(
        tmp_path, x="applies_to: {host_pattern: example.com}\ncapture: {capturer: video}\n"
    )
    fn, _ = capture.get_capturer(
        root, "https://example.com", opts=capture.CaptureOptions(no_video=True)
    )
    assert fn is capture.REGISTRY["browser"]


def test_router_video_and_no_video_mutually_exclusive(tmp_path):
    with pytest.raises(capture.CaptureError):
        capture.get_capturer(
            _corpus(tmp_path),
            "https://example.com",
            opts=capture.CaptureOptions(video=True, no_video=True),
        )


def test_router_unknown_capturer_raises(tmp_path):
    root = _corpus(
        tmp_path, x="applies_to: {host_pattern: example.com}\ncapture: {capturer: bogus}\n"
    )
    with pytest.raises(capture.CaptureError):
        capture.get_capturer(root, "https://example.com", opts=capture.CaptureOptions())


# ---------- video capturer: ytdlp passthrough + cookie scope ---------- #


def test_build_ydl_opts_merges_overlay_over_defaults():
    opts = capture._build_ydl_opts(
        outtmpl="/x/%(ext)s",
        include_comments=True,
        cookiefile=None,
        ytdlp_opts={"format": "b[vcodec^=h264]", "retries": 3},
    )
    assert opts["format"] == "b[vcodec^=h264]"  # overlay overrode the default
    assert opts["retries"] == 3  # passthrough
    assert opts["writeinfojson"] is True  # untouched default survives


def test_build_ydl_opts_normalizes_impersonate_string():
    """The overlay carries `impersonate` as a CLI-style string; the Python API needs
    an ImpersonateTarget. `_build_ydl_opts` must convert it (the way yt-dlp's CLI does)
    — passing the raw string crashes YoutubeDL() with an AssertionError."""
    from yt_dlp.networking.impersonate import ImpersonateTarget

    opts = capture._build_ydl_opts(
        outtmpl="/x/%(ext)s",
        include_comments=True,
        cookiefile=None,
        ytdlp_opts={"impersonate": "chrome-110:windows-10"},
    )
    target = opts["impersonate"]
    assert isinstance(target, ImpersonateTarget)
    assert target.client == "chrome" and target.version == "110"


def test_build_ydl_opts_forces_library_keys():
    opts = capture._build_ydl_opts(
        outtmpl="/real/%(ext)s",
        include_comments=True,
        cookiefile=Path("/tmp/c.txt"),
        ytdlp_opts={"outtmpl": "/evil/%(ext)s", "logger": None},  # both clobber attempts
    )
    assert opts["outtmpl"] == "/real/%(ext)s"  # FORCED wins
    assert opts["logger"] is not None
    assert opts["cookiefile"] == "/tmp/c.txt"


def test_build_ydl_opts_no_comments_forces_off():
    opts = capture._build_ydl_opts(
        outtmpl="/x/%(ext)s",
        include_comments=False,  # CLI --no-comments
        cookiefile=None,
        ytdlp_opts={"getcomments": True},  # overlay asked for comments
    )
    assert opts["getcomments"] is False


def test_cdp_prime_flag_gates_session_priming(monkeypatch, tmp_path):
    """`capture.cdp_prime: true` navigates the CDP browser to warm the cookie jar
    before extraction; absent/false, priming is skipped (no browser navigation)."""
    primed: list[str] = []
    monkeypatch.setattr(capture, "_resolve_cdp_endpoint", lambda _arg: "http://localhost:9222")
    monkeypatch.setattr(
        capture,
        "_prime_cdp_session",
        lambda cdp_url, *, url, timeout_ms: primed.append(url),
    )
    monkeypatch.setattr(capture, "_extract_cdp_cookies_for_ytdlp", lambda *a, **k: None)
    monkeypatch.setattr(capture, "_capture_video", lambda **k: tmp_path / "out.mp4")

    capture._capture_video_with_cookies(
        "https://www.tiktok.com/@a/video/1",
        capture_dir=tmp_path,
        opts=capture.CaptureOptions(),
        recipe={"cdp_prime": True},
    )
    assert primed == ["https://www.tiktok.com/@a/video/1"]

    primed.clear()
    capture._capture_video_with_cookies(
        "https://www.tiktok.com/@a/video/1",
        capture_dir=tmp_path,
        opts=capture.CaptureOptions(),
        recipe={},  # no cdp_prime → no navigation
    )
    assert primed == []


def test_cookie_scope_defaults_to_url_origin():
    assert capture._cookie_scope_urls("https://www.tiktok.com/@a/video/1", {}) == [
        "https://www.tiktok.com/"
    ]


def test_cookie_scope_disabled():
    assert capture._cookie_scope_urls("https://x.com/v", {"cookies_from_host": False}) == []


def test_cookie_scope_extends_with_list():
    scopes = capture._cookie_scope_urls(
        "https://x.com/v", {"cookies_from_host": ["https://login.x.com/"]}
    )
    assert scopes == ["https://x.com/", "https://login.x.com/"]


# ---------- config default_transport ---------- #


def test_config_default_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("CORPUS_CAPTURE_TRANSPORT", raising=False)
    assert "default_transport" not in config.load_config(tmp_path).capture
    (tmp_path / "corpus.toml").write_text(
        '[corpus.capture]\ndefault_transport = "headed"\n', encoding="utf-8"
    )
    assert config.load_config(tmp_path).capture["default_transport"] == "headed"
    monkeypatch.setenv("CORPUS_CAPTURE_TRANSPORT", "cdp")  # env wins
    assert config.load_config(tmp_path).capture["default_transport"] == "cdp"


def test_config_default_transport_invalid(tmp_path, monkeypatch):
    monkeypatch.delenv("CORPUS_CAPTURE_TRANSPORT", raising=False)
    (tmp_path / "corpus.toml").write_text(
        '[corpus.capture]\ndefault_transport = "sideways"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        config.load_config(tmp_path)


# ---------- corpus-local code capturers (Phase C) ---------- #


def test_corpus_local_capturer_loaded_and_selected(tmp_path):
    (tmp_path / "capturers").mkdir()
    (tmp_path / "capturers" / "echo.py").write_text(
        "from corpus.capture import CaptureResult, register\n\n\n"
        "@register('echo')\n"
        "def echo(url, *, corpus_root, capture_dir, opts, recipe):\n"
        "    return CaptureResult(capture_path=capture_dir / 'x', used_video=False, issues=[])\n",
        encoding="utf-8",
    )
    _corpus(tmp_path, e="applies_to: {host_pattern: example.com}\ncapture: {capturer: echo}\n")
    try:
        fn, recipe = capture.get_capturer(
            tmp_path, "https://example.com", opts=capture.CaptureOptions()
        )
        assert fn is capture.REGISTRY["echo"] and recipe["capturer"] == "echo"
    finally:
        # leave the shared REGISTRY / load-guard clean for other tests
        capture.REGISTRY.pop("echo", None)
        capture._loaded_capturer_roots.discard(str(tmp_path.resolve()))
