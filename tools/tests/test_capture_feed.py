"""The generic `feed` interaction step (R-0062): harvest a virtualized feed item by item.

`_config` is exercised without a browser. The walk itself is driven against a real headless
Chromium on a fixture page that simulates virtualization (items outside the viewport are
unmounted to empty `aria-posinset` placeholders) and a hover-revealed tooltip that only a
TRUSTED mouse raises. Browser tests skip cleanly where Chromium can't launch.
"""

from __future__ import annotations

import pytest

from corpus.capture import feed

# --- _config (no browser) --------------------------------------------------------------


def test_config_needs_an_item_and_exactly_one_of_order_or_key():
    assert feed._config("nope") is None
    assert feed._config({"order": "aria-posinset"}) is None
    assert feed._config({"item": "x"}) is None
    assert feed._config({"item": "x", "order": "o", "key": "k"}) is None
    assert feed._config({"item": "x", "order": "o"})["order"] == "o"
    assert feed._config({"item": "x", "key": "k"})["order"] is None


def test_config_key_is_an_attribute_name_or_a_js_function():
    attr = feed._config({"item": "x", "key": "data-id"})
    assert (attr["key_attr"], attr["key_js"]) == ("data-id", None)
    fn = feed._config({"item": "x", "key": {"js": "(el) => el.id"}})
    assert (fn["key_attr"], fn["key_js"]) == (None, "(el) => el.id")
    assert feed._config({"item": "x", "key": {"nope": 1}}) is None


def test_config_hover_reads_a_tooltip_xor_an_attribute():
    none = feed._config({"item": "x", "order": "o", "hover": "a"})
    assert (none["target"], none["read"]) == ("a", None)
    tip = feed._config({"item": "x", "order": "o", "hover": {
        "target": "a", "tooltip": "[role=tooltip]", "pattern": "^Mon", "read_href": True}})
    assert (tip["read"], tip["tooltip"], tip["pattern"], tip["read_href"]) == (
        "tooltip", "[role=tooltip]", "^Mon", True)
    attr = feed._config({"item": "x", "order": "o",
                         "hover": {"target": "a", "attribute": "aria-label"}})
    assert (attr["read"], attr["attribute"], attr["tooltip"]) == ("attribute", "aria-label", None)
    both = {"target": "a", "tooltip": "t", "attribute": "title"}
    assert feed._config({"item": "x", "order": "o", "hover": both}) is None
    assert feed._config({"item": "x", "order": "o", "hover": {"tooltip": "t"}}) is None


def test_config_defaults_and_shorthands():
    cfg = feed._config({"item": "x", "order": "o", "drop": "form", "stop": "(e) => 1",
                        "annotate": {"js": "(c) => ({})"}, "assemble": "append"})
    assert cfg["drop"] == ["form"]
    assert (cfg["stop_js"], cfg["stop_after"]) == ("(e) => 1", 1)
    assert cfg["annotate_js"] == "(c) => ({})"
    assert (cfg["mode"], cfg["keep_sel"], cfg["strip_hidden"]) == ("append", [], True)
    assert feed._config({"item": "x", "order": "o", "assemble": "weave"}) is None
    kept = feed._config({"item": "x", "order": "o",
                         "assemble": {"mode": "replace", "keep": "h1"}})
    assert kept["keep_sel"] == ["h1"]


@pytest.mark.parametrize("arg", [
    {"item": "x"},
    {"item": "x", "order": "o", "key": "k"},
    {"item": "x", "order": "o", "hover": {"target": "a", "tooltip": "t", "attribute": "title"}},
    {"item": "x", "order": "o", "assemble": "weave"},
])
def test_walk_returns_none_for_a_malformed_step_without_touching_the_page(arg):
    assert feed.walk(object(), arg) is None


# --- the walk, in a real browser ---------------------------------------------------------

N = 8

# Eight 300px items, each unmounted to an empty placeholder once it is more than half a
# viewport off-screen. A trusted mouseover on `a.ts` raises a decoy tooltip and the date
# tooltip and sets `data-full`; a synthetic one does nothing.
VIRTUAL = """<!doctype html><body><h1>Timeline</h1><div id="feed"></div><script>
const feed = document.getElementById('feed');
for (let i = 1; i <= __N__; i++) {
  const d = document.createElement('div');
  d.className = 'item'; d.setAttribute('aria-posinset', i); d.style.height = '300px';
  feed.appendChild(d);
}
function mount(d) {
  const n = d.getAttribute('aria-posinset');
  d.innerHTML = '<h2>Post ' + n + '</h2><p>Body of post number ' + n + ' in the feed.</p>'
    + '<span class="hid" style="display:none">SECRET' + n + '</span>'
    + '<a class="ts" style="display:inline-block;margin-left:100px"'
    + ' href="https://example.test/posts/' + n + '?tracking=abc">2h</a>';
}
function render() {
  const vh = innerHeight;
  for (const d of feed.children) {
    const r = d.getBoundingClientRect();
    const near = r.bottom > -vh / 2 && r.top < vh * 1.5;
    if (near && !d.childElementCount) mount(d);
    else if (!near && d.childElementCount) d.replaceChildren();
  }
}
addEventListener('scroll', render); render();
document.addEventListener('mouseover', (e) => {
  const a = e.target.closest && e.target.closest('a.ts');
  if (!a || !e.isTrusted) return;
  const n = a.closest('.item').getAttribute('aria-posinset');
  const date = 'Monday, January ' + n + ', 2024 at 9:00 AM';
  a.setAttribute('data-full', date);
  for (const text of ['Reactions', date]) {
    const t = document.createElement('div');
    t.setAttribute('role', 'tooltip'); t.textContent = text; document.body.appendChild(t);
  }
});
document.addEventListener('mouseout', (e) => {
  if (e.target.closest && e.target.closest('a.ts')) {
    document.querySelectorAll('[role=tooltip]').forEach((t) => t.remove());
  }
});
</script></body>""".replace("__N__", str(N))

# An infinite-scroll feed with no position attribute: one keyless ad, then posts keyed
# `data-id`, three more appended each time the page is scrolled to the bottom (up to p9).
KEYED = """<!doctype html><body><h1>Wall</h1><div id="feed"></div><script>
const feed = document.getElementById('feed');
function add(id) {
  const a = document.createElement('article');
  a.className = 'post'; a.style.height = '400px';
  if (id) a.setAttribute('data-id', id);
  a.textContent = id ? 'Post ' + id : 'Sponsored';
  feed.appendChild(a);
}
add(null); add('p1'); add('p2'); add('p3');
let next = 4;
setInterval(() => {
  const atBottom = innerHeight + scrollY >= document.documentElement.scrollHeight - 50;
  if (next <= 9 && atBottom) for (let k = 0; k < 3; k++) add('p' + next++);
}, 100);
</script></body>"""

ORDER = {"item": "[aria-posinset]", "order": "aria-posinset", "load_timeout_ms": 600,
         "ready": {"js": "(el) => el.childElementCount > 0", "timeout_ms": 3000}}
HOVER = {"target": "a.ts", "timeout_ms": 1500}

READ_CLONES = """(els) => els.map((e) => ({
  n: e.getAttribute('data-ath-feed-n'), key: e.getAttribute('data-ath-feed-key'),
  date: e.getAttribute('data-ath-date'), permalink: e.getAttribute('data-ath-permalink'),
  text: e.innerText, html: e.outerHTML,
  ts: e.querySelector('a.ts') && e.querySelector('a.ts').textContent,
  extra: e.getAttributeNames()
    .filter((x) => x.startsWith('data-ath-') && !x.startsWith('data-ath-feed')),
}))"""


@pytest.fixture(scope="module")
def browser():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # no Chromium binary / sandbox in this environment
            pytest.skip(f"chromium cannot launch here: {str(exc)[:80]}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page(viewport={"width": 1280, "height": 720})
    yield pg
    pg.close()


def _load(page, html):
    """A fresh document each time: the fixture scripts declare top-level consts."""
    page.goto("about:blank")
    page.set_content(html)


def _clones(page):
    return page.eval_on_selector_all("main[data-ath-feed] > [data-ath-feed-n]", READ_CLONES)


def _main_attrs(page):
    return page.eval_on_selector("main[data-ath-feed]", """(m) => Object.fromEntries(
        m.getAttributeNames().map((k) => [k, m.getAttribute(k)]))""")


def test_order_mode_harvests_every_item_despite_virtualization(page):
    _load(page, VIRTUAL)
    mounted = page.evaluate("() => [...document.querySelectorAll('.item')]"
                            ".filter((d) => d.childElementCount).length")
    assert mounted < N  # the fixture really does virtualize

    summary = feed.walk(page, ORDER)

    assert (summary["visited"], summary["kept"], summary["end"]) == (str(N), str(N), "end")
    clones = _clones(page)
    assert [c["n"] for c in clones] == [str(i) for i in range(1, N + 1)]
    assert all(f"Post {c['n']}" in c["text"] for c in clones)
    attrs = _main_attrs(page)
    assert (attrs["data-ath-feed-visited"], attrs["data-ath-feed-end"]) == (str(N), "end")
    assert attrs["data-ath-feed-undated"] == "" and attrs["data-ath-feed-gaps"] == ""


def test_tooltip_hover_reads_the_date_matching_the_pattern_and_the_permalink(page):
    _load(page, VIRTUAL)
    hover = {**HOVER, "tooltip": "[role=tooltip]", "pattern": "^\\w+day, ", "read_href": True}

    summary = feed.walk(page, {**ORDER, "hover": hover})

    assert summary["undated"] == ""
    for c in _clones(page):
        assert c["date"] == f"Monday, January {c['n']}, 2024 at 9:00 AM"
        assert c["ts"] == c["date"]  # the anchor's text became the date
        assert c["permalink"] == f"https://example.test/posts/{c['n']}?tracking=abc"


def test_attribute_hover_reads_the_targets_attribute_after_a_trusted_hover(page):
    _load(page, VIRTUAL)
    hover = {**HOVER, "attribute": "data-full", "pattern": "^\\w+day, "}

    summary = feed.walk(page, {**ORDER, "hover": hover})

    assert summary["undated"] == ""
    clones = _clones(page)
    assert len(clones) == N
    assert all(c["date"] == f"Monday, January {c['n']}, 2024 at 9:00 AM" for c in clones)


def test_a_read_that_never_matches_is_disclosed_as_undated(page):
    _load(page, VIRTUAL)
    hover = {**HOVER, "timeout_ms": 300, "attribute": "data-full", "pattern": "^NEVER"}

    summary = feed.walk(page, {**ORDER, "hover": hover, "max_items": 2})

    assert (summary["visited"], summary["undated"], summary["end"]) == ("2", "1,2", "max_items")
    assert all(c["date"] is None for c in _clones(page))


@pytest.mark.parametrize("key", ["data-id", {"js": "(el) => el.dataset.id"}])
def test_key_mode_walks_the_document_in_order_skipping_keyless_items(page, key):
    _load(page, KEYED)

    summary = feed.walk(page, {"item": "article.post", "key": key, "load_timeout_ms": 600})

    assert (summary["visited"], summary["kept"], summary["end"]) == ("9", "9", "end")
    clones = _clones(page)
    assert [c["key"] for c in clones] == [f"p{i}" for i in range(1, 10)]
    assert [c["n"] for c in clones] == [str(i) for i in range(1, 10)]
    assert all("Sponsored" not in c["text"] and "data-ath-feed-cur" not in c["html"]
               for c in clones)


def test_keep_decides_per_item_and_stop_needs_its_consecutive_run(page):
    _load(page, VIRTUAL)
    keep = {"keep": "(el, ctx) => ctx.n % 2 === 0"}
    summary = feed.walk(page, {**ORDER, **keep})
    assert (summary["visited"], summary["kept"]) == (str(N), str(N // 2))
    assert [c["n"] for c in _clones(page)] == ["2", "4", "6", "8"]

    _load(page, VIRTUAL)
    alternating = {"js": "(el, ctx) => ctx.n % 2 === 0", "consecutive": 2}
    assert feed.walk(page, {**ORDER, "stop": alternating})["end"] == "end"

    _load(page, VIRTUAL)
    from_three = {"js": "(el, ctx) => ctx.n >= 3", "consecutive": 2}
    summary = feed.walk(page, {**ORDER, "stop": from_three})
    assert (summary["visited"], summary["end"]) == ("4", "stop")


def test_strip_hidden_removes_a_display_none_child_and_drop_removes_selectors(page):
    _load(page, VIRTUAL)
    feed.walk(page, {**ORDER, "drop": ["p"]})
    html = "".join(c["html"] for c in _clones(page))
    assert "SECRET" not in html and "Body of post" not in html and "Post 1" in html

    _load(page, VIRTUAL)
    feed.walk(page, {**ORDER, "strip_hidden": False})
    assert all(f"SECRET{c['n']}" in c["html"] for c in _clones(page))


def test_annotate_becomes_sanitized_data_attributes_after_transform(page):
    _load(page, VIRTUAL)
    annotate = """(clone, ctx) => ({
      'Kind_Of Post': 'k' + ctx.n, seen: clone.getAttribute('data-x'), nope: null,
      empty: undefined, '!!': 'dropped', zero: 0 })"""
    transform = "(clone, ctx) => clone.setAttribute('data-x', 'by-transform')"

    feed.walk(page, {**ORDER, "annotate": annotate, "transform": transform})

    for c in _clones(page):
        assert sorted(c["extra"]) == ["data-ath-kind-of-post", "data-ath-seen", "data-ath-zero"]
        assert f'data-ath-kind-of-post="k{c["n"]}"' in c["html"]
        assert 'data-ath-seen="by-transform"' in c["html"] and 'data-ath-zero="0"' in c["html"]


def test_a_throwing_hook_costs_only_its_own_effect_on_that_item(page):
    _load(page, VIRTUAL)
    hooks = {
        "keep": "(el, ctx) => { if (ctx.n === 2) throw new Error('keep'); return true; }",
        "stop": "(el, ctx) => { throw new Error('stop'); }",
        "transform": "(c, ctx) => { if (ctx.n === 3) throw new Error('transform'); }",
        "annotate": "(c, ctx) => { if (ctx.n === 4) throw new Error('annotate');"
                    " return {mark: ctx.n}; }",
    }

    summary = feed.walk(page, {**ORDER, **hooks})

    assert (summary["visited"], summary["kept"], summary["end"]) == (str(N), str(N - 1), "end")
    clones = {c["n"]: c for c in _clones(page)}
    assert "2" not in clones and len(clones) == N - 1
    assert clones["4"]["extra"] == [] and clones["3"]["extra"] == ["data-ath-mark"]


def test_assemble_replace_drops_the_page_unless_told_to_keep_a_part(page):
    _load(page, VIRTUAL)
    feed.walk(page, ORDER)
    assert page.locator("h1").count() == 0 and page.locator("#feed").count() == 0

    _load(page, VIRTUAL)
    feed.walk(page, {**ORDER, "assemble": {"mode": "replace", "keep": ["h1"]}})
    assert page.evaluate("() => document.querySelector('main[data-ath-feed]')"
                         ".firstElementChild.outerHTML") == "<h1>Timeline</h1>"
    assert page.locator("#feed").count() == 0

    _load(page, VIRTUAL)
    feed.walk(page, {**ORDER, "assemble": "append"})
    assert page.locator("h1").count() == 1 and page.locator("#feed").count() == 1
    assert page.locator("main[data-ath-feed] > [data-ath-feed-n]").count() == N


def test_a_walk_that_keeps_nothing_leaves_the_page_untouched(page):
    _load(page, VIRTUAL)

    summary = feed.walk(page, {**ORDER, "keep": "() => false"})

    assert (summary["assembled"], summary["kept"], summary["visited"]) == (0, "0", str(N))
    assert page.locator("main[data-ath-feed]").count() == 0
    assert page.locator("h1").count() == 1
    assert page.locator("#feed > .item").count() == N
