"""§7.2 (3.9) — the innermost declared region owns the byte.

The properties pinned here are the ones whose absence produced two defensible readings of the
same declaration set, differing by ~9,000 anchors on one host.
"""

from __future__ import annotations

import pytest

from corpus.regionmap import resolve, selector_pattern

# The shape that motivated the amendment: a subject envelope wrapping framing and never.
ALLDATA = (
    "<html><body>"
    "<ad-repair-article>"
    '<div class=article-breadcrumb><a href=/x>Vehicle</a></div>'
    '<div class="vehicle-info">2008 Pontiac G8</div>'
    "<p>The subject prose.</p>"
    "<ad-repair-related-information><a href=/y>Related</a></ad-repair-related-information>"
    "</ad-repair-article>"
    "</body></html>"
)

DECL = [
    {"role": "breadcrumb", "selector": "div.article-breadcrumb", "renders": "framing"},
    {"role": "related-information", "selector": "ad-repair-related-information",
     "renders": "framing"},
    {"role": "vehicle", "selector": "div.vehicle-info", "renders": "never"},
    {"role": "article", "selector": "ad-repair-article", "renders": "subject"},
]


def _at(html: str, needle: str) -> int:
    i = html.index(needle)
    assert i >= 0
    return i


def test_the_inner_declaration_wins_over_the_wrapper():
    """The whole amendment in one assertion."""
    m = resolve(ALLDATA, DECL)
    assert m.renders_at(_at(ALLDATA, "Vehicle</a>")) == "framing"
    assert m.renders_at(_at(ALLDATA, "2008 Pontiac")) == "never"
    assert m.renders_at(_at(ALLDATA, "Related</a>")) == "framing"
    # ...while the envelope still governs the bytes that are only its own
    assert m.renders_at(_at(ALLDATA, "The subject prose")) == "subject"


def test_reading_the_wrapper_as_subject_is_what_this_prevents():
    """Guards the specific regression: without innermost-wins every anchor scores subject."""
    m = resolve(ALLDATA, DECL)
    anchors = [_at(ALLDATA, "Vehicle</a>"), _at(ALLDATA, "Related</a>")]
    assert [m.renders_at(o) for o in anchors] == ["framing", "framing"]
    assert not any(m.renders_at(o) == "subject" for o in anchors)


def test_subject_inside_subject_resolves_to_the_inner_one():
    """The rule's other job — a union of subject matches would count this content twice."""
    html = ("<ad-repair-article><ad-repair-dynamic-content>x"
            "</ad-repair-dynamic-content></ad-repair-article>")
    decl = [
        {"role": "article", "selector": "ad-repair-article", "renders": "subject"},
        {"role": "dynamic-content", "selector": "ad-repair-dynamic-content", "renders": "subject"},
    ]
    m = resolve(html, decl)
    assert m.owner(_at(html, "x")).role == "dynamic-content"
    # the outer envelope is no longer counted as owning its inner region's bytes
    assert [r.role for r in m.spans("subject")] == ["article"]


def test_an_uncovered_byte_is_none_and_none_is_not_subject():
    """§7.2: silence is omission. A caller that defaults None to subject re-creates the bug."""
    html = "<div>outside</div><ad-repair-article>in</ad-repair-article>"
    m = resolve(html, [{"role": "article", "selector": "ad-repair-article", "renders": "subject"}])
    assert m.renders_at(_at(html, "outside")) is None
    assert m.renders_at(_at(html, "in</")) == "subject"


def test_containment_is_read_per_artifact_not_from_declaration_order():
    """Same declarations, two templates: nested on one, siblings on the other."""
    nested = "<ad-outer><ad-inner>t</ad-inner></ad-outer>"
    siblings = "<ad-outer>t</ad-outer><ad-inner>u</ad-inner>"
    decl = [
        {"role": "outer", "selector": "ad-outer", "renders": "subject"},
        {"role": "inner", "selector": "ad-inner", "renders": "framing"},
    ]
    assert resolve(nested, decl).renders_at(_at(nested, "t</")) == "framing"
    assert resolve(siblings, decl).renders_at(_at(siblings, "t</")) == "subject"
    assert resolve(siblings, decl).renders_at(_at(siblings, "u</")) == "framing"


def test_unquoted_class_attributes_still_match():
    """The lean capture path emits `class=foo`; a quote-requiring pattern matches nothing."""
    html = "<div class=article-breadcrumb>crumb</div>"
    m = resolve(html, [{"role": "b", "selector": "div.article-breadcrumb", "renders": "framing"}])
    assert m.renders_at(_at(html, "crumb")) == "framing"


def test_a_class_match_is_not_a_prefix_match():
    html = "<div class=article-breadcrumb-legacy>x</div>"
    m = resolve(html, [{"role": "b", "selector": "div.article-breadcrumb", "renders": "framing"}])
    assert m.regions == []


def test_repeated_occurrences_each_get_their_own_span():
    html = "<ad-x>one</ad-x><ad-x>two</ad-x>"
    m = resolve(html, [{"role": "x", "selector": "ad-x", "renders": "framing"}])
    assert len(m.regions) == 2
    assert m.renders_at(_at(html, "two")) == "framing"


def test_an_unresolvable_selector_is_reported_not_silently_skipped():
    """A region that quietly fails to match reads exactly like one that is genuinely absent."""
    m = resolve("<div>x</div>", [{"role": "r", "selector": "div > p:first-child",
                                  "renders": "subject"}])
    assert m.regions == []
    assert len(m.errors) == 1
    assert "not a form this reader resolves" in m.errors[0]


def test_interleaving_spans_are_an_error_not_a_tie_to_break():
    """Neither contains the other — no DOM produces it, so a selector is wrong."""
    html = "<ad-a>start<ad-b>mid</ad-a>tail</ad-b>"
    m = resolve(html, [
        {"role": "a", "selector": "ad-a", "renders": "subject"},
        {"role": "b", "selector": "ad-b", "renders": "framing"},
    ])
    assert len(m.errors) == 1
    assert "neither contains" in m.errors[0]
    assert "'a'" in m.errors[0] and "'b'" in m.errors[0]


def test_clean_nesting_reports_no_error():
    assert resolve(ALLDATA, DECL).errors == []


def test_ties_break_on_declaration_order_so_the_answer_is_deterministic():
    html = "<ad-x>t</ad-x>"
    decl = [
        {"role": "first", "selector": "ad-x", "renders": "subject"},
        {"role": "second", "selector": "ad-x", "renders": "never"},
    ]
    assert resolve(html, decl).owner(_at(html, "t</")).role == "first"


@pytest.mark.parametrize(
    "selector, ok",
    [("ad-repair-article", True), ("div.article-breadcrumb", True), ("p-breadcrumb", True),
     ("div > p", False), (".bare-class", False), ("", False)],
)
def test_selector_support_is_narrow_and_explicit(selector, ok):
    assert (selector_pattern(selector) is not None) is ok
