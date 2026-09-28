"""The fail-closed `assert` interaction step (spec §12.3.6, v48; owner ruling 2026-09-27,
from ath-steven R-0048/R-0049).

Every other interaction step is best-effort, so an overlay had no way to fail a capture
closed. The costco.ca overlay wiped `document.body` to a sentinel and threw, and the sentinel
page was ingested anyway. An `assert` that does not hold, cannot be evaluated, or is
malformed now aborts before the snapshot.
"""

from __future__ import annotations

import pytest

from corpus import capture
from corpus.capture import interactions


class _Locator:
    def __init__(self, n: int) -> None:
        self._n = n

    def count(self) -> int:
        return self._n


class _Page:
    """Just enough page: `selectors` maps a selector to its match count; `js` maps an
    expression to its value (an Exception value raises); every call is recorded."""

    def __init__(self, selectors=None, js=None) -> None:
        self.selectors = selectors or {}
        self.js = js or {}
        self.calls: list[str] = []

    def locator(self, sel: str) -> _Locator:
        self.calls.append(f"locator {sel}")
        return _Locator(self.selectors.get(sel, 0))

    def evaluate(self, expr: str):
        self.calls.append(f"evaluate {expr[:20]}")
        value = self.js.get(expr)
        if isinstance(value, Exception):
            raise value
        return value

    def wait_for_timeout(self, _ms: int) -> None:
        pass


def test_a_holding_assert_lets_the_run_continue():
    page = _Page(selectors={"#receipt": 1}, js={"ok()": True, "later()": None})
    interactions.run(page, [
        {"assert": {"selector": "#receipt"}},
        {"assert": {"js": "ok()"}},
        {"eval": "later()"},
    ])
    assert page.calls[-1] == "evaluate later()"


@pytest.mark.parametrize(("step", "page", "said"), [
    ({"selector": "#receipt", "message": "not logged in"}, _Page(), "not logged in"),
    ({"selector": ".sign-in", "present": False}, _Page(selectors={".sign-in": 1}), "absent"),
    ({"js": "ready()"}, _Page(js={"ready()": 0}), "did not hold"),
    ({"js": "boom()"}, _Page(js={"boom()": RuntimeError("TypeError")}), "could not be evaluated"),
    ({"selector": "#a", "js": "x"}, _Page(), "malformed"),
    ("#receipt", _Page(), "malformed"),
])
def test_an_assert_that_does_not_hold_aborts_and_stops_the_run(step, page, said):
    with pytest.raises(interactions.CaptureAborted, match=said):
        interactions.run(page, [{"assert": step}, {"eval": "after()"}])
    assert "evaluate after()" not in page.calls


def test_other_steps_stay_best_effort():
    page = _Page(js={"boom()": RuntimeError("bad"), "after()": None})
    interactions.run(page, [{"eval": "boom()"}, {"eval": "after()"}])
    assert page.calls[-1] == "evaluate after()"


def test_the_capture_layer_surfaces_an_abort_as_a_capture_error():
    with pytest.raises(capture.CaptureError, match="capture aborted: not logged in"):
        capture._interact(_Page(), [{"assert": {"selector": "#r", "message": "not logged in"}}])
