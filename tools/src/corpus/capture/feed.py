"""The `feed` interaction step: harvest a virtualized feed item by item (R-0062).

A virtualized feed (Facebook's profile timeline) keeps only the items near the viewport
mounted, so a snapshot taken after `scroll: full` holds the handful still on screen,
while the rest are placeholders. `carousel` solves the same problem for slides. This step
visits each item in feed order and brings it into view. It waits for the item to render,
then optionally moves a TRUSTED mouse over one anchor in it and reads back what the hover
reveals: a tooltip's text or an attribute of the anchor (a full date), and the anchor's
post-hover `href` (a permalink). It then clones the item, with hidden subtrees stripped,
into a stash that survives the feed's eviction. At the end the stash is assembled into the
page, by default replacing the body, so the ordinary snapshot pass runs over every item.

The hover is driven from Python (`page.mouse`, i.e. CDP `Input.dispatchMouseEvent`)
because synthetic `mouseover` from page JS is untrusted and a site can ignore it.

How the walk finds the next item is the step's one required choice, exactly one of:

- `order`: an attribute carrying each item's 1-based feed position (`aria-posinset`).
  Item n is looked up by position, so a position that never mounts is a recorded gap.
- `key`: for a feed with no position attribute. An attribute name (`data-id`) or
  `{js: "(el) => key"}` giving each item a unique key. The walk takes items in document
  order, the first not yet seen, scrolling to the bottom for more when none is mounted.
  Items with an empty key are skipped. No gaps are possible. No live feed has exercised
  this mode yet.

Step shape::

    - feed:
        item: '[aria-posinset]'      # CSS: one element per feed item
        order: aria-posinset         # XOR key: data-id | {js: "(el) => el.dataset.id"}
        ready: {js: "(el) => el.innerText.length > 40", timeout_ms: 7000}
        hover:
          target: "a[href*='/posts/']"       # first visible match inside the item
          exclude_within: '[data-x="name"]'  # …that is not inside this
          tooltip: '[role="tooltip"]'        # read the tooltip the hover raises
          # …XOR attribute: aria-label       # read the target's attribute after the hover
          pattern: '^\\w+day, '              # only a read value matching this (regex) counts
          read_href: true                    # the anchor's href after the hover
          timeout_ms: 3000
        keep: "(item, ctx) => …"     # stash only items this holds for (default: all)
        stop: {js: "(item, ctx) => …", consecutive: 3}
        expand: {selector: '[role="button"]', text: '^See more$'}
        strip_hidden: true           # drop display:none / visibility:hidden subtrees
        drop: ['form']               # selectors removed from each clone
        transform: "(clone, ctx) => { … }"   # touch-up of each clone
        annotate: "(clone, ctx) => ({kind: 'photo'})"  # → data-ath-kind on the clone
        load_timeout_ms: 30000       # how long to scroll for a missing next item
        max_items: 5000
        max_seconds: 3600
        assemble: replace            # | append | {mode: replace, keep: ['h1']}

`ctx` is `{n, key, date, permalink, text}`. `n` is the 1-based visit counter in either mode
(the feed position in `order` mode), `key` the item's key (null in `order` mode), `date`
the value the hover read, `permalink` the post-hover href, `text` the item's rendered text.
`transform` may rewrite any of it, for example by stripping tracking parameters, and
`annotate` returns a mapping whose entries become `data-ath-<name>` attributes (names
lowercased to `[a-z0-9-]`, null values skipped). A `keep`, `stop`, `transform` or `annotate`
that throws costs only its own effect on that item: a throwing `keep` does not keep it.
The assembled container is
`<main data-ath-feed data-ath-feed-visited=… data-ath-feed-kept=… data-ath-feed-undated=…
data-ath-feed-end=…>`, which discloses in the artifact itself what the walk saw and why it
ended. Each clone carries `data-ath-feed-n` (and `data-ath-feed-key` in `key` mode), plus
`data-ath-date` and `data-ath-permalink` when read. The hovered anchor's text becomes the
date, and its href the permalink, so the mechanical body reads both. `undated` lists the
items whose configured hover read came back empty. A walk that keeps nothing leaves the
page untouched. An overlay that needs the harvest pairs the step with a fail-closed
`assert: {selector: 'main[data-ath-feed]'}`.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("corpus.capture.feed")

_ASSEMBLE_MODES = ("replace", "append")


def _js(arg: Any) -> str | None:
    """A predicate given as a bare string or as `{js: …}`."""
    if isinstance(arg, dict):
        arg = arg.get("js")
    return str(arg).strip() or None if arg else None


def _config(arg: Any) -> dict[str, Any] | None:
    """Normalize the step's mapping, or None (with a warning) when it can't run."""
    if not isinstance(arg, dict) or not arg.get("item"):
        log.warning("feed: step needs `item` — skipping: %r", arg)
        return None
    if bool(arg.get("order")) == bool(arg.get("key")):
        log.warning("feed: step needs exactly one of `order` or `key` — skipping: %r", arg)
        return None
    key = arg.get("key")
    key_attr = key_js = None
    if isinstance(key, str):
        key_attr = key.strip() or None
    elif key:
        key_js = _js(key)
    if key and not (key_attr or key_js):
        log.warning("feed: `key` is an attribute name or {js: …} — skipping: %r", key)
        return None
    hover = arg.get("hover") or {}
    if isinstance(hover, str):
        hover = {"target": hover}
    if hover.get("tooltip") and hover.get("attribute"):
        log.warning("feed: hover takes `tooltip` or `attribute`, not both — skipping")
        return None
    if (hover.get("tooltip") or hover.get("attribute")) and not hover.get("target"):
        log.warning("feed: hover needs a `target` to read from — skipping")
        return None
    expand = arg.get("expand") or {}
    if isinstance(expand, str):
        expand = {"selector": expand}
    stop = arg.get("stop") or {}
    ready = arg.get("ready") or {}
    assemble = arg.get("assemble", "replace")
    if isinstance(assemble, str):
        assemble = {"mode": assemble}
    mode = str(assemble.get("mode") or "replace")
    if mode not in _ASSEMBLE_MODES:
        log.warning("feed: unknown assemble mode %r — skipping", mode)
        return None
    keep_sel = assemble.get("keep") or []
    tooltip = str(hover.get("tooltip") or "") or None
    attribute = str(hover.get("attribute") or "") or None
    return {
        "item": str(arg["item"]),
        "order": str(arg["order"]) if arg.get("order") else None,
        "key_attr": key_attr,
        "key_js": key_js,
        "ready_js": _js(ready),
        "ready_ms": int(ready.get("timeout_ms", 7000)) if isinstance(ready, dict) else 7000,
        "target": str(hover.get("target") or "") or None,
        "exclude_within": str(hover.get("exclude_within") or "") or None,
        "tooltip": tooltip,
        "attribute": attribute,
        "read": "tooltip" if tooltip else "attribute" if attribute else None,
        "pattern": str(hover.get("pattern") or "") or None,
        "read_href": bool(hover.get("read_href", False)),
        "hover_ms": int(hover.get("timeout_ms", 3000)),
        "keep_js": _js(arg.get("keep")),
        "stop_js": _js(stop),
        "stop_after": max(1, int(stop.get("consecutive", 1))) if isinstance(stop, dict) else 1,
        "expand_sel": str(expand.get("selector") or "") or None,
        "expand_text": str(expand.get("text") or "") or None,
        "strip_hidden": arg.get("strip_hidden", True) is not False,
        "drop": [str(s) for s in ([arg["drop"]] if isinstance(arg.get("drop"), str)
                                  else arg.get("drop") or [])],
        "transform_js": _js(arg.get("transform")),
        "annotate_js": _js(arg.get("annotate")),
        "load_ms": int(arg.get("load_timeout_ms", 30000)),
        "max_items": int(arg.get("max_items", 5000)),
        "max_seconds": float(arg.get("max_seconds", 3600)),
        "mode": mode,
        "keep_sel": [keep_sel] if isinstance(keep_sel, str) else [str(s) for s in keep_sel],
    }


# Shared in-page helpers. `byOrder` finds the item whose `order` attribute equals n (order
# mode only). The stash lives on window as a detached container of cloned nodes, so
# assembling it never parses HTML strings (no innerHTML, which a Trusted-Types page refuses).
_PRELUDE = """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const byOrder = (n) => [...document.querySelectorAll(a.item)]
  .find((el) => el.getAttribute(a.order) === String(n)) || null;
const maxOrder = () => Math.max(0, ...[...document.querySelectorAll(a.item)]
  .map((el) => parseInt(el.getAttribute(a.order), 10)).filter((v) => v > 0));
const visible = (el) => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
"""

# Locate the next item (order mode: item n; key mode: the first unseen keyed item in
# document order, marked `data-ath-feed-cur=<key>` for the harvest): scroll for it while
# absent, bring it into view, wait for it to render (and for its hover target to mount),
# mark the target, return its viewport point.
_LOCATE_JS = """async (a) => {
%(prelude)s
  const ready = %(ready)s, keyFn = %(key)s;
  const keyOf = (el) => {
    try {
      const k = keyFn ? keyFn(el) : el.getAttribute(a.key_attr);
      return k == null ? '' : String(k);
    } catch (e) { return ''; }
  };
  const seen = window.__athFeedSeen || (window.__athFeedSeen = new Set());
  let curKey = null;
  const find = () => {
    if (a.order) return byOrder(a.n);
    const all = [...document.querySelectorAll(a.item)];
    let el;
    if (curKey !== null) el = all.find((x) => keyOf(x) === curKey);
    else {
      el = all.find((x) => { const k = keyOf(x); return k && !seen.has(k); });
      if (el) { curKey = keyOf(el); seen.add(curKey); }
    }
    if (el) {
      document.querySelectorAll('[data-ath-feed-cur]')
        .forEach((x) => x.removeAttribute('data-ath-feed-cur'));
      el.setAttribute('data-ath-feed-cur', curKey);
    }
    return el || null;
  };
  let el = find();
  const t0 = Date.now();
  let gap = false;
  while (!el && Date.now() - t0 < a.load_ms) {
    if (a.order && maxOrder() > a.n && Date.now() - t0 > 3000) { gap = true; break; }
    window.scrollTo(0, document.documentElement.scrollHeight);
    await sleep(Math.min(1200, Math.max(100, a.load_ms / 4)));
    el = find();
  }
  if (!el) return gap ? { gap: true } : { end: true };
  el.scrollIntoView({ block: 'center' });
  document.querySelectorAll('[data-ath-feed-hover]')
    .forEach((x) => x.removeAttribute('data-ath-feed-hover'));
  const findTarget = () => {
    if (!a.target) return null;
    const ex = a.exclude_within ? [...el.querySelectorAll(a.exclude_within)] : [];
    return [...el.querySelectorAll(a.target)]
      .find((x) => !ex.some((e) => e.contains(x)) && visible(x)) || null;
  };
  let target = null;
  const w = Date.now();
  while (Date.now() - w < a.ready_ms) {
    el = find() || el;
    target = findTarget();
    let ok = true;
    try { ok = !ready || !!ready(el); } catch (e) { ok = false; }
    if (ok && (!a.target || target)) break;
    await sleep(150);
  }
  if (!target) return { found: true };
  target.setAttribute('data-ath-feed-hover', '1');
  const r = target.getBoundingClientRect();
  return { found: true, x: r.x + Math.min(r.width / 2, 20), y: r.y + r.height / 2 };
}"""

_TOOLTIP_JS = """(a) => {
  const re = a.pattern ? new RegExp(a.pattern) : null;
  return [...document.querySelectorAll(a.tooltip)].map((t) => t.innerText.trim())
    .find((s) => s && (!re || re.test(s))) || null;
}"""

_ATTRIBUTE_JS = """(a) => {
  const t = document.querySelector('[data-ath-feed-hover]');
  const v = t ? (t.getAttribute(a.attribute) || '').trim() : '';
  return v && (!a.pattern || new RegExp(a.pattern).test(v)) ? v : null;
}"""

# Decide (keep / stop) and, when kept, expand, strip, clone, annotate and stash the located
# item. Each overlay hook is guarded: one that throws costs only its own effect on the item.
_HARVEST_JS = """async (a) => {
%(prelude)s
  const keep = %(keep)s, stop = %(stop)s, transform = %(transform)s, annotate = %(annotate)s;
  const guard = (fn) => { try { return fn(); } catch (e) { return undefined; } };
  const el = a.order ? byOrder(a.n) : document.querySelector('[data-ath-feed-cur]');
  if (!el) return { kept: false, stop: false };
  const key = a.order ? null : el.getAttribute('data-ath-feed-cur');
  el.removeAttribute('data-ath-feed-cur');
  const anchor = el.querySelector('[data-ath-feed-hover]');
  const ctx = { n: a.n, key, date: a.date, permalink: a.read_href && anchor ? anchor.href : null,
                text: el.innerText };
  const stopHit = stop ? !!guard(() => stop(el, ctx)) : false;
  if (keep && !guard(() => keep(el, ctx))) return { kept: false, stop: stopHit };
  if (a.expand_sel) {
    const re = a.expand_text ? new RegExp(a.expand_text, 'i') : null;
    for (let round = 0; round < 4; round++) {
      const bs = [...el.querySelectorAll(a.expand_sel)]
        .filter((b) => !re || re.test((b.innerText || '').trim()));
      if (!bs.length) break;
      for (const b of bs) { try { b.click(); } catch (e) {} await sleep(600); }
    }
    ctx.text = el.innerText;
  }
  if (a.strip_hidden) {
    // Hidden = display:none, or visibility:hidden with no visible descendant (a child
    // may set visibility:visible again). Walked bottom-up so each check is O(1).
    const all = [el, ...el.querySelectorAll('*')];
    const shows = new Map();
    for (let i = all.length - 1; i >= 0; i--) {
      const x = all[i], cs = getComputedStyle(x);
      const kid = [...x.children].some((c) => shows.get(c));
      shows.set(x, cs.visibility !== 'hidden' || kid);
      if (cs.display === 'none' || (cs.visibility === 'hidden' && !kid)) {
        x.setAttribute('data-ath-feed-hidden', '1');
      }
    }
  }
  const c = el.cloneNode(true);
  el.querySelectorAll('[data-ath-feed-hidden]')
    .forEach((x) => x.removeAttribute('data-ath-feed-hidden'));
  if (el.hasAttribute('data-ath-feed-hidden')) el.removeAttribute('data-ath-feed-hidden');
  if (c.hasAttribute('data-ath-feed-hidden')) return { kept: false, stop: stopHit, hidden: true };
  c.querySelectorAll('[data-ath-feed-hidden]').forEach((x) => x.remove());
  for (const s of a.drop) c.querySelectorAll(s).forEach((x) => x.remove());
  const ca = c.querySelector('[data-ath-feed-hover]');
  if (ca) {
    if (ctx.date) { ca.textContent = ctx.date; ca.setAttribute('data-ath-date', ctx.date); }
    if (ctx.permalink) ca.setAttribute('href', ctx.permalink);
    ca.removeAttribute('data-ath-feed-hover');
  }
  c.setAttribute('data-ath-feed-n', String(a.n));
  if (key) c.setAttribute('data-ath-feed-key', key);
  if (ctx.date) c.setAttribute('data-ath-date', ctx.date);
  if (ctx.permalink) c.setAttribute('data-ath-permalink', ctx.permalink);
  if (transform) guard(() => transform(c, ctx));
  const extra = annotate ? guard(() => annotate(c, ctx)) : null;
  if (extra && typeof extra === 'object') {
    for (const [k, v] of Object.entries(extra)) {
      const name = k.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '');
      if (name && v != null) c.setAttribute('data-ath-' + name, String(v));
    }
  }
  if (!window.__athFeedStash) window.__athFeedStash = document.createElement('div');
  window.__athFeedStash.appendChild(c);
  return { kept: true, stop: stopHit };
}"""

_ASSEMBLE_JS = """(a) => {
  const stash = window.__athFeedStash;
  const n = stash ? stash.children.length : 0;
  if (!n) return 0;
  const main = document.createElement('main');
  main.setAttribute('data-ath-feed', '');
  for (const [k, v] of Object.entries(a.attrs)) main.setAttribute('data-ath-feed-' + k, v);
  if (a.mode === 'replace') {
    for (const s of a.keep) {
      document.querySelectorAll(s).forEach((x) => main.appendChild(x.cloneNode(true)));
    }
  }
  main.append(...stash.children);
  if (a.mode === 'replace') document.body.replaceChildren(main);
  else document.body.appendChild(main);
  window.__athFeedStash = null;
  return n;
}"""


def _fn(js: str | None) -> str:
    """Embed an overlay-supplied function as a JS expression (or `null`). Compiled with
    the evaluated wrapper (CDP `Runtime.evaluate`), so a page CSP that forbids `eval`
    does not reach it."""
    return f"({js})" if js else "null"


def walk(page: Any, arg: Any) -> dict[str, Any] | None:
    """Service a `feed` interaction (see the module docstring). Returns the walk's
    summary (also logged), or None when the step was malformed."""
    cfg = _config(arg)
    if cfg is None:
        return None
    locate = _LOCATE_JS % {"prelude": _PRELUDE, "ready": _fn(cfg["ready_js"]),
                           "key": _fn(cfg["key_js"])}
    harvest = _HARVEST_JS % {
        "prelude": _PRELUDE,
        "keep": _fn(cfg["keep_js"]),
        "stop": _fn(cfg["stop_js"]),
        "transform": _fn(cfg["transform_js"]),
        "annotate": _fn(cfg["annotate_js"]),
    }
    base = {k: cfg[k] for k in ("item", "order", "key_attr", "target", "exclude_within",
                                "read_href", "expand_sel", "expand_text", "strip_hidden",
                                "drop")}
    base["ready_ms"], base["load_ms"] = cfg["ready_ms"], cfg["load_ms"]
    page.evaluate("() => { window.__athFeedStash = null; window.__athFeedSeen = new Set();"
                  " window.scrollTo(0, 0); }")

    t0 = time.monotonic()
    visited = kept = streak = 0
    undated: list[int] = []
    gaps: list[int] = []
    end = "max_items"
    n = 0
    while n < cfg["max_items"]:
        if time.monotonic() - t0 > cfg["max_seconds"]:
            end = "max_seconds"
            break
        n += 1
        pos = page.evaluate(locate, {**base, "n": n})
        if pos.get("end"):
            end = "end"
            break
        if pos.get("gap"):
            gaps.append(n)
            continue
        visited += 1
        date = None
        if cfg["read"] and pos.get("x") is not None:
            date = _hover_read(page, cfg, float(pos["x"]), float(pos["y"]))
        if cfg["read"] and date is None:
            undated.append(n)
        res = page.evaluate(harvest, {**base, "n": n, "date": date})
        kept += bool(res.get("kept"))
        streak = streak + 1 if res.get("stop") else 0
        if streak >= cfg["stop_after"]:
            end = "stop"
            break

    attrs = {"visited": str(visited), "kept": str(kept), "end": end,
             "undated": ",".join(map(str, undated)), "gaps": ",".join(map(str, gaps))}
    assembled = page.evaluate(_ASSEMBLE_JS, {"mode": cfg["mode"], "keep": cfg["keep_sel"],
                                             "attrs": attrs})
    summary = {**attrs, "assembled": assembled, "seconds": round(time.monotonic() - t0, 1)}
    if not assembled:
        log.warning("feed: kept no items (visited %d, end=%s) — page left as is", visited, end)
    elif undated or gaps:
        log.warning("feed: %s", json.dumps(summary))
    else:
        log.info("feed: %s", json.dumps(summary))
    return summary


def _hover_read(page: Any, cfg: dict[str, Any], x: float, y: float) -> str | None:
    """Move a trusted mouse onto (x, y) and read what the hover reveals: the tooltip it
    raises, or the hovered target's attribute once it holds a matching value. In tooltip
    mode, waits first for any earlier tooltip to clear, or a stale one would be read as
    this item's."""
    deadline = time.monotonic() + cfg["hover_ms"] / 1000
    if cfg["tooltip"]:
        probe = {"tooltip": cfg["tooltip"], "pattern": None}
        while time.monotonic() < deadline and page.evaluate(_TOOLTIP_JS, probe) is not None:
            page.wait_for_timeout(150)
        js, probe = _TOOLTIP_JS, {**probe, "pattern": cfg["pattern"]}
    else:
        js, probe = _ATTRIBUTE_JS, {"attribute": cfg["attribute"], "pattern": cfg["pattern"]}
    page.mouse.move(x - 40, y)
    page.mouse.move(x, y)
    value = None
    deadline = time.monotonic() + cfg["hover_ms"] / 1000
    while value is None and time.monotonic() < deadline:
        value = page.evaluate(js, probe)
        if value is None:
            page.wait_for_timeout(150)
    vp = page.viewport_size or {"height": 600}
    page.mouse.move(5, vp["height"] // 2)
    return value
