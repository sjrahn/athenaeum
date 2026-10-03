"""The `scroll: {until_stable, step_ms, max_seconds}` interaction step (spec §12.3.6, v52):
keep scrolling to the bottom of an infinite list until its height stops growing."""

from __future__ import annotations

import pytest

from corpus.capture import interactions


class _Page:
    """Records every `evaluate(expr, arg)`; nothing else is needed by a scroll step."""

    def __init__(self) -> None:
        self.evals: list[tuple[str, object]] = []

    def evaluate(self, expr: str, arg: object = None):
        self.evals.append((expr, arg))

    def wait_for_timeout(self, _ms: int) -> None:
        pass


def _scroll(arg) -> list[tuple[str, object]]:
    page = _Page()
    interactions.run(page, [{"scroll": arg}])
    return page.evals


def test_scroll_full_is_the_plain_top_to_bottom_pass():
    assert _scroll("full") == [(interactions._SCROLL_JS, None)]


def test_until_stable_passes_its_parameters_with_defaults():
    assert _scroll({"until_stable": 5}) == [
        (interactions._SCROLL_UNTIL_STABLE_JS, {"stable": 5, "step_ms": 1500, "max_ms": 300000}),
    ]


def test_until_stable_takes_explicit_step_and_ceiling():
    [(expr, arg)] = _scroll({"until_stable": 2, "step_ms": 200, "max_seconds": 10})
    assert expr == interactions._SCROLL_UNTIL_STABLE_JS
    assert arg == {"stable": 2, "step_ms": 200, "max_ms": 10000}


@pytest.mark.parametrize("arg", [{"until_stable": 0}, {"until_stable": None}, {"step_ms": 200}, {}])
def test_a_dict_without_a_positive_until_stable_falls_back_to_full_scroll(arg):
    assert _scroll(arg) == [(interactions._SCROLL_JS, None)]


@pytest.mark.parametrize("arg", [
    {"until_stable": "lots"},
    {"until_stable": 3, "step_ms": "slow"},
    {"until_stable": 3, "max_seconds": "forever"},
    {"until_stable": [1]},
])
def test_malformed_values_never_raise_out_of_run(arg):
    page = _Page()
    interactions.run(page, [{"scroll": arg}, {"eval": "after()"}])
    # the bad scroll evaluated nothing; the next step still ran
    assert [e for e, _ in page.evals] == ["after()"]


_INFINITE_LIST = """<body style="margin:0"><div id="list"></div><script>
  let batches = 0, pending = false;
  function more() {
    if (batches >= 6) return;
    batches++;
    for (let i = 0; i < 5; i++) {
      const d = document.createElement('div');
      d.className = 'item'; d.style.height = '300px'; d.textContent = 'item';
      document.getElementById('list').appendChild(d);
    }
  }
  more();
  window.addEventListener('scroll', () => {
    const bottom = document.documentElement.scrollHeight - 2;
    if (window.innerHeight + window.scrollY >= bottom && !pending) {
      pending = true;
      setTimeout(() => { more(); pending = false; }, 50);
    }
  });
</script></body>"""


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # no browser binary / sandbox here
            pytest.skip(f"headless chromium unavailable: {exc}")
        yield b
        b.close()


def _items_after(browser, step) -> int:
    page = browser.new_page(viewport={"width": 800, "height": 600})
    try:
        page.set_content(_INFINITE_LIST)
        interactions.run(page, [{"scroll": step}])
        return page.locator(".item").count()
    finally:
        page.close()


def test_until_stable_loads_every_batch_of_a_real_infinite_list(browser):
    assert _items_after(browser, {"until_stable": 2, "step_ms": 200, "max_seconds": 10}) == 30


def test_full_scroll_does_not_reach_the_end_of_an_infinite_list(browser):
    assert _items_after(browser, "full") < 30
