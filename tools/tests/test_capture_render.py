"""The render guarantee for a capture driven through a real browser (spec Part II, R-0062):
a locked display parks a CDP-driven tab's compositor (rAF at 0/s while `visibilityState`
still says "visible"), so the capturer keeps the page compositing with an acknowledged
screencast and probes that the page is drawing — before the interactions and again before
the snapshot — aborting the capture as a failed `assert` does when it is not.
"""

from __future__ import annotations

import pytest

from corpus import capture


class _FakeCDP:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}
        self.fail = fail or set()

    def send(self, method: str, params: dict | None = None):
        self.sent.append((method, params or {}))
        if method in self.fail:
            raise RuntimeError(f"{method} refused")
        return {}

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def remove_listener(self, event: str, handler) -> None:
        self.handlers[event].remove(handler)

    def fire(self, event: str, params: dict) -> None:
        for h in list(self.handlers.get(event, [])):
            h(params)

    def methods(self) -> list[str]:
        return [m for m, _ in self.sent]


class _FakePage:
    """`results` is what each `evaluate` returns in turn (an Exception raises)."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.waits: list[int] = []

    def evaluate(self, expr: str):
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)


def test_keepalive_starts_screencast_and_acks_every_frame() -> None:
    cdp = _FakeCDP()
    capture._start_render_keepalive(cdp)
    assert "Page.startScreencast" in cdp.methods()
    assert cdp.methods().index("Page.enable") < cdp.methods().index("Page.startScreencast")
    cdp.fire("Page.screencastFrame", {"sessionId": 7, "data": "x"})
    cdp.fire("Page.screencastFrame", {"sessionId": 8, "data": "y"})
    acks = [p for m, p in cdp.sent if m == "Page.screencastFrameAck"]
    assert acks == [{"sessionId": 7}, {"sessionId": 8}]


def test_keepalive_tolerates_refused_setup_and_ack_failure() -> None:
    cdp = _FakeCDP(
        fail={"Page.setWebLifecycleState", "Emulation.setFocusEmulationEnabled"}
    )
    capture._start_render_keepalive(cdp)
    assert "Page.startScreencast" in cdp.methods()
    cdp.fail.add("Page.screencastFrameAck")
    cdp.fire("Page.screencastFrame", {"sessionId": 1})  # must not raise


def test_keepalive_start_failure_is_not_fatal() -> None:
    cdp = _FakeCDP(fail={"Page.startScreencast"})
    stop = capture._start_render_keepalive(cdp)
    stop()


def test_keepalive_stop_is_idempotent_and_best_effort() -> None:
    cdp = _FakeCDP()
    stop = capture._start_render_keepalive(cdp)
    cdp.fail.add("Page.stopScreencast")
    stop()
    stop()
    assert cdp.methods().count("Page.stopScreencast") == 1
    assert cdp.handlers["Page.screencastFrame"] == []


def test_probe_counts_frames_over_a_bounded_window() -> None:
    page = _FakePage(None, 60)
    assert capture._probe_rendering(page, window_ms=250) == 60
    assert page.waits == [250]


def test_require_rendering_passes_a_drawing_page() -> None:
    assert capture._require_rendering(_FakePage(None, 60), when="x") == 60


def test_require_rendering_aborts_on_zero_frames() -> None:
    with pytest.raises(capture.CaptureError, match=r"not drawing.*display locked"):
        capture._require_rendering(_FakePage(None, 0), when="before snapshot")


@pytest.mark.parametrize(
    "results",
    [
        (RuntimeError("page closed"),),
        (None, RuntimeError("Execution context was destroyed")),
        (None, None),  # the page navigated and the probe state is gone
    ],
)
def test_probe_that_cannot_run_aborts(results) -> None:
    with pytest.raises(capture.CaptureError, match="render probe"):
        capture._require_rendering(_FakePage(*results), when="x")


# ---- real browser (skipped where Chromium cannot launch) ---- #


@pytest.fixture
def real_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # no browser binary / sandbox
            pytest.skip(f"chromium cannot launch here: {exc}")
        try:
            ctx = browser.new_context()
            page = ctx.new_page()
            yield ctx, page
        finally:
            browser.close()


_ANIMATED = (
    "data:text/html,<div id=a style='width:50px;height:50px;background:red'></div>"
    "<script>setInterval(()=>{a.style.width=(20+Math.random()*100)+'px'},16)</script>"
)


def test_real_browser_probe_and_keepalive(real_page) -> None:
    ctx, page = real_page
    cdp = ctx.new_cdp_session(page)
    stop = capture._start_render_keepalive(cdp)
    try:
        page.goto(_ANIMATED)
        assert capture._probe_rendering(page, window_ms=500) > 0
        assert capture._require_rendering(page, when="test") > 0
    finally:
        stop()
