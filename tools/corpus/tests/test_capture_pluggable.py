"""Pluggable, origin-routed capture: interaction engine, recipe resolution,
router order, and config default_transport. All deterministic — no browser/network."""

from __future__ import annotations

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


# ---------- recipe resolution ---------- #


def _corpus(tmp_path, **files):
    d = tmp_path / "schema" / "capture"
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (d / f"{name}.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_recipe_match_and_miss(tmp_path):
    root = _corpus(
        tmp_path,
        ig="applies_to: {host_pattern: instagram.com, include_subdomains: true}\ntransport: cdp\n",
    )
    r = recipes.capture_recipe_for_url(root, "https://www.instagram.com/p/x/")
    assert r and r["transport"] == "cdp"  # subdomain www matched
    assert recipes.capture_recipe_for_url(root, "https://example.com") is None


def test_recipe_specificity_beats_catchall(tmp_path):
    root = _corpus(
        tmp_path,
        star="applies_to: {host_pattern: '*'}\ntransport: headless\n",
        ig="applies_to: {host_pattern: instagram.com}\ntransport: cdp\n",
    )
    assert recipes.capture_recipe_for_url(root, "https://instagram.com/x")["transport"] == "cdp"
    assert recipes.capture_recipe_for_url(root, "https://other.com")["transport"] == "headless"


# ---------- router order ---------- #


def test_router_recipe_selects_capturer(tmp_path):
    root = _corpus(tmp_path, x="applies_to: {host_pattern: example.com}\ncapturer: video\n")
    fn, recipe = capture.get_capturer(root, "https://example.com", opts=capture.CaptureOptions())
    assert fn is capture.REGISTRY["video"] and recipe["capturer"] == "video"


def test_router_default_dispatch_when_no_recipe(tmp_path):
    root = _corpus(tmp_path)  # empty schema/capture/
    opts = capture.CaptureOptions()
    fn_v, _ = capture.get_capturer(root, "https://youtube.com/watch?v=x", opts=opts)
    fn_b, _ = capture.get_capturer(root, "https://example.com", opts=opts)
    assert fn_v is capture.REGISTRY["video"]
    assert fn_b is capture.REGISTRY["browser"]


def test_router_unknown_capturer_raises(tmp_path):
    root = _corpus(tmp_path, x="applies_to: {host_pattern: example.com}\ncapturer: bogus\n")
    with pytest.raises(capture.CaptureError):
        capture.get_capturer(root, "https://example.com", opts=capture.CaptureOptions())


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
    _corpus(tmp_path, e="applies_to: {host_pattern: example.com}\ncapturer: echo\n")
    try:
        fn, recipe = capture.get_capturer(
            tmp_path, "https://example.com", opts=capture.CaptureOptions()
        )
        assert fn is capture.REGISTRY["echo"] and recipe["capturer"] == "echo"
    finally:
        # leave the shared REGISTRY / load-guard clean for other tests
        capture.REGISTRY.pop("echo", None)
        capture._loaded_capturer_roots.discard(str(tmp_path.resolve()))
