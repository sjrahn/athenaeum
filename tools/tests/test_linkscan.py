"""`corpus.linkscan.scan_flattened` — the #118/#52 link-flattening detector, pinned against
the false-positive classes the original census paid to find (module docstring)."""

from __future__ import annotations

from corpus.linkscan import scan_flattened
from corpus.regionmap import resolve as resolve_regions
from corpus.segments import Section, Segment

_DECL = [
    {"role": "article", "selector": "div.article", "renders": "subject"},
    {"role": "rail", "selector": "div.rail", "renders": "framing"},
]


def test_flattened_anchor_detected():
    html = '<div class="article"><a href="/torque">Torque Spec</a></div>'
    blocks = [Segment(atom="text", body="See the Torque Spec for details.")]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 1
    assert result["flattened"] == 1
    assert result["sample"] == ["Torque Spec"]
    assert result["pass"] is False


def test_omission_is_not_flattening():
    """An anchor whose text never made it into the body at all is an OMISSION, not a
    flattening — the census-inflating conflation the module docstring warns about."""
    html = '<div class="article"><a href="/torque">Ghost Widget</a></div>'
    blocks = [Segment(atom="text", body="Nothing about that anchor appears in this body.")]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 1
    assert result["flattened"] == 0
    assert result["pass"] is True


def test_markdown_linked_anchor_passes():
    html = '<div class="article"><a href="/torque">Torque Spec</a></div>'
    blocks = [Segment(atom="text", body="See the [Torque Spec](/torque) for details.")]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 1
    assert result["flattened"] == 0
    assert result["pass"] is True


def test_chrome_text_and_empty_href_anchors_ignored():
    html = (
        '<div class="article">'
        '<a href="#">Print</a>'
        "<a>No Href Widget</a>"
        "</div>"
    )
    blocks = [Segment(atom="text", body="Print. No Href Widget.")]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 0
    assert result["flattened"] == 0


def test_framing_region_anchor_ignored_innermost_wins():
    """A rail anchor nested inside the subject wrapper scores as framing, not subject —
    §7.2's innermost-wins (#120's own correction to an earlier over-count)."""
    html = (
        '<div class="article">Article prose mentions Torque Spec.'
        '<div class="rail"><a href="/torque">Torque Spec</a></div>'
        "</div>"
    )
    blocks = [Segment(atom="text", body="Article prose mentions Torque Spec.")]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 0
    assert result["flattened"] == 0


def test_sample_capped_at_five():
    anchors = "".join(f'<a href="/x{i}">Widget {i}</a>' for i in range(8))
    html = f'<div class="article">{anchors}</div>'
    blocks = [Segment(atom="text", body=" ".join(f"Widget {i}" for i in range(8)))]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 8
    assert result["flattened"] == 8
    assert len(result["sample"]) == 5


def test_nav_span_text_excluded_from_presence_test():
    """#89's restoration renders the page's own breadcrumb as plain text inside a trailing
    `form/nav` span, and a crumb label routinely repeats a subject anchor's own text. An
    anchor whose text appears ONLY inside that nav span — never actually placed in the
    body's own content — is an omission, not a flattening; the presence test must not
    credit the nav span's rendering as if it were the anchor's placement."""
    html = '<div class="article"><a href="/evap">Evaporator Core</a></div>'
    blocks = [
        Segment(atom="text", body="Unrelated prose about a different repair entirely."),
        Section(form="nav", segments=[Segment(atom="text", body="Vehicle > Evaporator Core")]),
    ]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 1
    assert result["flattened"] == 0
    assert result["pass"] is True


def test_markdown_link_inside_nav_span_still_counts_as_linked():
    """The link-collection pass reads the WHOLE body regardless of the nav exclusion — a
    markdown link is a link wherever it renders (module docstring)."""
    html = '<div class="article"><a href="/torque">Torque Spec</a></div>'
    blocks = [
        Segment(atom="text", body="Unrelated prose."),
        Section(form="nav", segments=[Segment(atom="text", body="[Torque Spec](/torque)")]),
    ]
    rmap = resolve_regions(html, _DECL)
    result = scan_flattened(html, blocks, rmap)
    assert result["subject_anchors"] == 1
    assert result["flattened"] == 0


def test_raw_html_anchor_in_body_counts_as_linked():
    """The guidance mandates raw `<a href>` inside merged-cell tables — a raw anchor in
    the body satisfies the link rule exactly as a markdown link does (#52 wave 6)."""
    html = (
        '<div class="subject"><a href="/x">Interface</a></div>'
    )
    from corpus import segments as _segments
    from corpus.linkscan import scan_flattened

    class _Rmap:
        def renders_at(self, pos):
            return "subject"

    blocks = [
        _segments.Segment(
            atom="text",
            address="el=1",
            body='<table><tr><td rowspan="2"><a href="/x">Interface</a></td></tr></table>',
        )
    ]
    result = scan_flattened(html, blocks, _Rmap())
    assert result["flattened"] == 0 and result["subject_anchors"] == 1


def test_self_edge_anchor_excluded_from_candidacy():
    """A self-edge anchor's mandated rendering is omission (form/nav, #89), so its dropped
    link is never a flattening — even when its label collides with unrelated body text
    (#52 wave 7: a "Service Procedure" rail entry vs. a same-text body heading)."""
    html = (
        '<div class="article">'
        '<a href="#/vehicle/1/component/2">Service Procedure</a>'
        "</div>"
    )
    blocks = [Segment(atom="text", body="**Service Procedure** — do the steps below.")]
    rmap = resolve_regions(html, _DECL)
    own = ("https://host.example/repair/#/vehicle/1/component/2",)
    result = scan_flattened(html, blocks, rmap, self_urls=own)
    assert result["subject_anchors"] == 0
    assert result["flattened"] == 0
    assert result["pass"] is True
    # Without self_urls the same anchor still scores — the exclusion is caller-opt-in,
    # preserving the detector's historical behavior for callers without origin URIs.
    result = scan_flattened(html, blocks, rmap)
    assert result["flattened"] == 1


def test_self_edge_requires_route_not_bare_fragment():
    """A bare `#` href names no route and never matches a self URL; a non-self route
    stays a candidate even when other anchors on the page are self-edges."""
    html = (
        '<div class="article">'
        '<a href="#/vehicle/1/component/OTHER">Elsewhere Page</a>'
        "</div>"
    )
    blocks = [Segment(atom="text", body="Elsewhere Page is discussed here.")]
    rmap = resolve_regions(html, _DECL)
    own = ("https://host.example/repair/#/vehicle/1/component/2",)
    result = scan_flattened(html, blocks, rmap, self_urls=own)
    assert result["subject_anchors"] == 1
    assert result["flattened"] == 1
