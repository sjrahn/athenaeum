"""Pre-snapshot page interaction.

Drive a rendered page to surface *all displayable* media — lazy-loaded images,
carousels, tabbed panels, accordions — before the self-contained snapshot is
taken. A capture recipe's ``interactions:`` is an ordered list of single-key
steps; absent one, :data:`DEFAULT_STEPS` runs.

Every step is **best-effort**: a step that raises is logged at debug and the run
continues. A bad selector in a recipe must never abort a capture. The one exception is
``assert`` (spec §12.3.6, v48), the overlay's fail-closed check: when it does not hold,
the capture raises before the snapshot, so nothing is staged or ingested.

Step grammar (each list item is a single-key mapping)::

    - scroll: full              # top-to-bottom, hydrating lazy content
    - scroll: {until_stable: 5, step_ms: 1500, max_seconds: 300}
                                # an infinite list: scroll to the bottom until the height
                                # stops growing for 5 consecutive steps
    - expand: all               # open <details>; click [aria-expanded=false]
    - expand: details           # open <details> only
    - click: {selector: "...", repeat: 10, delay_ms: 400}
    - click: ".carousel-next"   # shorthand: selector only, repeat 1
    - carousel: {next: "button[aria-label='Next']", max: 12}
                                # walk a VIRTUALIZED image carousel (e.g. Instagram),
                                # force-inlining each slide as it's reached so all N
                                # survive — not just the 2 left in the DOM at snapshot.
                                # Needs the capture's request API (caller-supplied).
    - feed: {item: "[aria-posinset]", order: aria-posinset, hover: {...}, ...}
                                # harvest a VIRTUALIZED feed item by item, with a trusted
                                # hover per item — see `capture/feed.py` for the shape
    - wait: {ms: 1500}
    - wait: {selector: "img.loaded", timeout_ms: 8000}
    - hover: {selector: "..."}
    - remove: ['#header', 'footer', '.ad']   # delete chrome before the snapshot
    - eval: "<javascript>"      # escape hatch
    - assert: {selector: "#receipt", present: true, message: "not logged in"}
    - assert: {js: "document.title !== 'Sign In'", message: "..."}
                                # FAIL-CLOSED: false, unevaluable, or malformed aborts
                                # the capture before the snapshot

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


class CaptureAborted(RuntimeError):
    """An `assert` step did not hold — the overlay declared this page unfit to capture
    (spec §12.3.6). Raised through `run`'s best-effort guard; the capture layer turns it
    into a `CaptureError` before any snapshot is written."""

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

# A list that extends itself as it is scrolled (an infinite grid): keep scrolling to the
# bottom until the height has not grown for `stable` consecutive steps, or time runs out.
_SCROLL_UNTIL_STABLE_JS = """async (a) => {
    const t0 = Date.now();
    let last = -1, still = 0;
    while (still < a.stable && Date.now() - t0 < a.max_ms) {
        window.scrollTo(0, document.documentElement.scrollHeight);
        await new Promise(r => setTimeout(r, a.step_ms));
        const h = document.documentElement.scrollHeight;
        still = h === last ? still + 1 : 0;
        last = h;
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
        except CaptureAborted:
            raise  # the one fail-closed step
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
        if isinstance(arg, dict) and arg.get("until_stable"):
            page.evaluate(_SCROLL_UNTIL_STABLE_JS, {
                "stable": max(1, int(arg["until_stable"])),
                "step_ms": int(arg.get("step_ms", 1500)),
                "max_ms": int(float(arg.get("max_seconds", 300)) * 1000),
            })
        else:
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
    elif kind == "feed":
        from . import feed

        feed.walk(page, arg)
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
    elif kind == "assert":
        _assert(page, arg)
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


def _assert(page: Any, arg: Any) -> None:
    """The fail-closed step (spec §12.3.6): `{selector, present?}` holds when the selector
    matches (or, with `present: false`, matches nothing); `{js}` holds when the expression
    (or async function) is truthy. A step that does not hold, cannot be evaluated, or is
    malformed aborts — a check that silently skipped would be no check at all."""
    if not isinstance(arg, dict) or bool(arg.get("selector")) == bool(arg.get("js")):
        raise CaptureAborted(
            f"capture aborted: malformed assert step {arg!r} — it takes exactly one of "
            "`selector` (with optional `present`) or `js`, plus an optional `message`"
        )
    message = str(arg.get("message") or "assert failed")
    if arg.get("selector"):
        want = arg.get("present", True) is not False
        what = f"selector {arg['selector']!r} {'present' if want else 'absent'}"
    else:
        what = f"js {arg['js']!r}"
    try:
        if arg.get("selector"):
            held = (page.locator(str(arg["selector"])).count() > 0) == want
        else:
            held = bool(page.evaluate(str(arg["js"])))
    except Exception as exc:
        raise CaptureAborted(
            f"capture aborted: {message} ({what} could not be evaluated: {exc})"
        ) from exc
    if not held:
        raise CaptureAborted(f"capture aborted: {message} ({what} did not hold)")
