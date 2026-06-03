"""Pre-snapshot page interaction.

Drive a rendered page to surface *all displayable* media — lazy-loaded images,
carousels, tabbed panels, accordions — before the self-contained snapshot is
taken. A capture recipe's ``interactions:`` is an ordered list of single-key
steps; absent one, :data:`DEFAULT_STEPS` runs.

Every step is **best-effort**: a step that raises is logged at debug and the run
continues. A bad selector in a recipe must never abort a capture.

Step grammar (each list item is a single-key mapping)::

    - scroll: full              # top-to-bottom, hydrating lazy content
    - expand: all               # open <details>; click [aria-expanded=false]
    - expand: details           # open <details> only
    - click: {selector: "...", repeat: 10, delay_ms: 400}
    - click: ".carousel-next"   # shorthand: selector only, repeat 1
    - carousel: {next: "button[aria-label='Next']", max: 12}
                                # walk a VIRTUALIZED image carousel (e.g. Instagram),
                                # force-inlining each slide as it's reached so all N
                                # survive — not just the 2 left in the DOM at snapshot.
                                # Needs the capture's request API (caller-supplied).
    - wait: {ms: 1500}
    - wait: {selector: "img.loaded", timeout_ms: 8000}
    - hover: {selector: "..."}
    - remove: ['#header', 'footer', '.ad']   # delete chrome before the snapshot
    - eval: "<javascript>"      # escape hatch

``remove`` is the declarative way to strip page chrome (nav/header/footer/ads/
cookie notices) per host: the HTML drafter is mechanical and never guesses what
is chrome, so removing it is a capture-time, per-origin decision made here where
the site's real structure is known. ``arg`` is a CSS selector or list of them;
every matching element is deleted from the live DOM before the snapshot.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger("corpus.capture.interactions")

# The generic all-media pass when a recipe declares no `interactions:`. Kept
# conservative on purpose — scroll + expand are broadly safe; site-specific
# carousel/tab advancing belongs in a per-origin recipe's `click` steps (a
# generic "click anything that looks like next" pass clicks the wrong things).
DEFAULT_STEPS: list[dict[str, Any]] = [
    {"scroll": "full"},
    {"expand": "all"},
    {"scroll": "full"},
]

# Scroll top-to-bottom; stay at the bottom (some sites unmount above-the-fold
# components when scrolled past, so returning to top would lose them).
_SCROLL_JS = """async () => {
    const step = window.innerHeight;
    const total = document.documentElement.scrollHeight;
    for (let y = 0; y <= total; y += step) {
        window.scrollTo(0, y);
        await new Promise(r => setTimeout(r, 300));
    }
}"""

_EXPAND_DETAILS_JS = """() => {
    let n = 0;
    document.querySelectorAll('details:not([open])').forEach(d => { d.open = true; n++; });
    return n;
}"""

_EXPAND_ALL_JS = """() => {
    let n = 0;
    document.querySelectorAll('details:not([open])').forEach(d => { d.open = true; n++; });
    document.querySelectorAll('[aria-expanded="false"]').forEach(el => {
        try { el.click(); n++; } catch (e) {}
    });
    return n;
}"""


def run(
    page: Any,
    steps: list[dict[str, Any]] | None,
    *,
    carousel_handler: Callable[[Any, Any], None] | None = None,
) -> None:
    """Execute an ordered list of interaction `steps` against `page` (best-effort).

    `None` runs :data:`DEFAULT_STEPS`. Settles with a short wait afterward so
    interaction-triggered network/image loads land before the snapshot.

    `carousel_handler`, when given, services the `carousel` step — it needs the
    capture's request API to force-inline each slide as the walk reaches it, so it
    is supplied by the caller (`_capture_via_playwright`) rather than implemented
    here. Absent a handler the step is a no-op.
    """
    for step in steps if steps is not None else DEFAULT_STEPS:
        if not isinstance(step, dict) or len(step) != 1:
            log.debug("skipping malformed interaction step: %r", step)
            continue
        (kind, arg), = step.items()
        try:
            _run_step(page, str(kind), arg, carousel_handler=carousel_handler)
        except Exception as exc:  # best-effort: never abort a capture on a step
            log.debug("interaction %s failed: %s — continuing", kind, exc)
    with contextlib.suppress(Exception):
        page.wait_for_timeout(2000)


def _run_step(
    page: Any,
    kind: str,
    arg: Any,
    *,
    carousel_handler: Callable[[Any, Any], None] | None = None,
) -> None:
    if kind == "scroll":
        page.evaluate(_SCROLL_JS)
    elif kind == "expand":
        page.evaluate(_EXPAND_ALL_JS if arg == "all" else _EXPAND_DETAILS_JS)
    elif kind == "click":
        _click(page, arg)
    elif kind == "carousel":
        if carousel_handler is not None:
            carousel_handler(page, arg)
        else:
            log.debug("carousel step with no handler — skipping")
    elif kind == "wait":
        _wait(page, arg)
    elif kind == "hover":
        selector = arg.get("selector") if isinstance(arg, dict) else arg
        if selector:
            page.locator(str(selector)).first.hover(timeout=5000)
    elif kind == "remove":
        _remove(page, arg)
    elif kind == "eval":
        page.evaluate(str(arg))
    else:
        log.debug("unknown interaction kind: %r", kind)


def _remove(page: Any, arg: Any) -> None:
    """Delete every element matching the given CSS selector(s) from the live DOM
    before the snapshot. `arg` is a selector string or a list of them. The
    selectors are embedded in a self-contained arrow fn (single-arg `evaluate`)
    so they survive serialization without a second `evaluate` argument."""
    selectors = [arg] if isinstance(arg, str) else [str(s) for s in arg or []]
    selectors = [s for s in selectors if s.strip()]
    if not selectors:
        return
    js = (
        "() => { "
        + json.dumps(selectors)
        + ".forEach(s => document.querySelectorAll(s).forEach(e => e.remove())); }"
    )
    page.evaluate(js)


def _click(page: Any, arg: Any) -> None:
    if isinstance(arg, str):
        selector, repeat, delay_ms = arg, 1, 300
    elif isinstance(arg, dict):
        selector = arg.get("selector")
        repeat = int(arg.get("repeat", 1))
        delay_ms = int(arg.get("delay_ms", 300))
    else:
        return
    if not selector:
        return
    loc = page.locator(str(selector))
    for _ in range(max(1, repeat)):
        try:
            loc.first.click(timeout=3000)
        except Exception as exc:
            # Carousel ran out of "next" / element vanished — stop repeating.
            log.debug("click %r: %s — stopping repeats", selector, exc)
            break
        page.wait_for_timeout(delay_ms)


def _wait(page: Any, arg: Any) -> None:
    if isinstance(arg, dict):
        if "ms" in arg:
            page.wait_for_timeout(int(arg["ms"]))
        elif "selector" in arg:
            page.wait_for_selector(str(arg["selector"]), timeout=int(arg.get("timeout_ms", 10000)))
    elif isinstance(arg, int):
        page.wait_for_timeout(arg)
