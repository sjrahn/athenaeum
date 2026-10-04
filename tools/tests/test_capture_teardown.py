"""A failed capture cleans up after itself and says where it died (R-0065).

A CDP capture runs in the owner's own browser, so the tab it opened must close on every
exit path — including a renderer crash or a CDP connection dropped under an oversized
snapshot, where `page.close()` itself fails — and never a tab it did not open. And a
crash must name its stage, page, DOM size and last interaction step, not surface as a
bare `TargetClosed`.
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from corpus import capture
from corpus.capture import interactions


class _Page:
    def __init__(self, *, close_fails: bool = False, size: dict | None = None) -> None:
        self.close_fails = close_fails
        self.size = size
        self.closed = False

    def close(self) -> None:
        if self.close_fails:
            raise RuntimeError("Target page, context or browser has been closed")
        self.closed = True

    def evaluate(self, js, *args):
        if self.size is None:
            raise RuntimeError("Target closed")
        return self.size


class _Conn:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected

    def is_connected(self) -> bool:
        return self.connected


class _BrowserSession:
    def __init__(self, sent: list) -> None:
        self.sent = sent

    def send(self, method, params=None):
        self.sent.append((method, params))
        return {}


class _Browser:
    def __init__(self, sent: list) -> None:
        self.sent = sent
        self.closed = False

    def new_browser_cdp_session(self):
        return _BrowserSession(self.sent)

    def close(self) -> None:
        self.closed = True


class _Chromium:
    def __init__(self) -> None:
        self.sent: list = []
        self.connects: list[str] = []
        self.browsers: list[_Browser] = []

    def connect_over_cdp(self, url):
        self.connects.append(url)
        b = _Browser(self.sent)
        self.browsers.append(b)
        return b


class _P:
    def __init__(self) -> None:
        self.chromium = _Chromium()


def test_close_own_tab_uses_page_close_when_it_works():
    p, page = _P(), _Page()
    capture._close_own_tab(p, _Conn(), page, cdp_url="http://x:9222", target_id="T1")
    assert page.closed and p.chromium.connects == []


def test_close_own_tab_falls_back_to_its_own_target_over_a_fresh_connection():
    p, page = _P(), _Page(close_fails=True)
    capture._close_own_tab(p, _Conn(), page, cdp_url="http://x:9222", target_id="T1")
    assert p.chromium.connects == ["http://x:9222"]
    assert p.chromium.sent == [("Target.closeTarget", {"targetId": "T1"})]
    assert p.chromium.browsers[0].closed  # the fresh connection is released


def test_close_own_tab_does_not_trust_a_close_on_a_dropped_connection():
    p, page = _P(), _Page()
    capture._close_own_tab(p, _Conn(False), page, cdp_url="http://x:9222", target_id="T1")
    assert p.chromium.sent == [("Target.closeTarget", {"targetId": "T1"})]


@pytest.mark.parametrize(("cdp_url", "target_id"), [(None, "T1"), ("http://x:9222", None)])
def test_close_own_tab_never_guesses_a_target(cdp_url, target_id):
    p = _P()
    capture._close_own_tab(p, _Conn(False), _Page(close_fails=True), cdp_url=cdp_url,
                           target_id=target_id)
    assert p.chromium.connects == [] and p.chromium.sent == []


def test_capture_stage_names_stage_page_dom_and_last_step():
    where = {"page_url": "https://e.x/a", "dom": "9 elements, 2 <video>",
             "steps": ["scroll", "feed"]}
    with pytest.raises(capture.CaptureError) as ei, capture._capture_stage("snapshot", **where):
        raise RuntimeError("Target closed")
    msg = str(ei.value)
    for part in ("snapshot stage", "RuntimeError: Target closed", "https://e.x/a",
                 "9 elements, 2 <video>", "last interaction step: feed"):
        assert part in msg


def test_capture_stage_passes_a_capture_error_through_untouched():
    with (
        pytest.raises(capture.CaptureError, match=r"^not drawing$"),
        capture._capture_stage("snapshot", page_url="u", dom="d", steps=[]),
    ):
        raise capture.CaptureError("not drawing")


def test_dom_size_is_best_effort():
    assert capture._dom_size(_Page(size={"elements": 5, "videos": 1})) == "5 elements, 1 <video>"
    assert capture._dom_size(_Page()) == "unknown"


def test_interactions_report_progress():
    class _P2:
        def evaluate(self, *a):
            return None

        def wait_for_timeout(self, ms):
            pass

    seen: list[str] = []
    interactions.run(_P2(), [{"scroll": "full"}, {"eval": "1"}], progress=seen)
    assert seen == ["scroll", "eval"]


# --- real browser over CDP --------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def cdp_chrome(tmp_path):
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
    except Exception as exc:
        pytest.skip(f"playwright chromium unavailable: {exc}")
    if not Path(exe).exists():
        pytest.skip("chromium not installed")
    port = _free_port()
    proc = subprocess.Popen(
        [exe, "--headless=new", f"--remote-debugging-port={port}", "--no-first-run",
         f"--user-data-dir={tmp_path / 'profile'}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("chromium did not open its debugging port")
    yield url
    proc.kill()
    proc.wait()


def _tabs(url: str) -> list[str]:
    with urllib.request.urlopen(url + "/json/list", timeout=2) as r:
        return sorted(t["id"] for t in json.load(r) if t["type"] == "page")


def test_a_failed_cdp_capture_closes_its_tab_and_names_the_stage(
    cdp_chrome, tmp_path, monkeypatch
):
    page_file = tmp_path / "p.html"
    page_file.write_text("<html><body><p>hello</p><video></video></body></html>")
    before = _tabs(cdp_chrome)

    def crash(**kwargs):
        raise RuntimeError("Target closed")

    monkeypatch.setattr(capture, "_snapshot_html", crash)
    monkeypatch.setattr(capture, "_require_rendering", lambda page, when: 60)
    monkeypatch.setattr(capture, "NETWORKIDLE_BUDGET_MS", 500)
    with pytest.raises(capture.CaptureError) as ei:
        capture._capture_via_playwright(
            url=page_file.as_uri(),
            capture_dir=tmp_path,
            opts=capture.CaptureOptions(timeout_s=20),
            cdp_url=cdp_chrome,
            recipe={"transport": "cdp", "interactions": [{"eval": "1"}]},
            corpus_root=tmp_path,
        )
    msg = str(ei.value)
    assert "snapshot stage" in msg and "last interaction step: eval" in msg
    assert "<video>" in msg and page_file.as_uri() in msg
    assert _tabs(cdp_chrome) == before  # its own tab gone; the pre-existing one kept


def test_a_dropped_cdp_connection_still_closes_the_captures_tab(cdp_chrome, tmp_path, monkeypatch):
    """The connection dies mid-snapshot (as under an oversized SingleFile payload):
    `page.close()` can no longer reach the browser, so the tab is closed by its own id
    over a fresh connection — and the error still names the stage."""
    page_file = tmp_path / "p.html"
    page_file.write_text("<html><body><p>hello</p></body></html>")
    before = _tabs(cdp_chrome)

    def drop(**kwargs):
        kwargs["page"].context.browser.close()  # over CDP: disconnects, leaves the tab
        raise RuntimeError("Target closed")

    monkeypatch.setattr(capture, "_snapshot_html", drop)
    monkeypatch.setattr(capture, "_require_rendering", lambda page, when: 60)
    monkeypatch.setattr(capture, "NETWORKIDLE_BUDGET_MS", 500)
    with pytest.raises(capture.CaptureError, match="snapshot stage"):
        capture._capture_via_playwright(
            url=page_file.as_uri(),
            capture_dir=tmp_path,
            opts=capture.CaptureOptions(timeout_s=20),
            cdp_url=cdp_chrome,
            recipe={"transport": "cdp"},
            corpus_root=tmp_path,
        )
    assert _tabs(cdp_chrome) == before
