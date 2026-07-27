"""`ath ledger remap-el` — the anchor-side §12.28 remap (ledger.remap_el).

The mapping itself is `corpus.remap_el.map_el_value` (pinned in test_el_path_36); what
this file pins is the LEDGER grammar around it: only el-LEADING param strings rewrite
(the EPUB `spine=…&el=…` axis and every other axis stay untouched), chained ops ride
along, and a flat range whose mapping is an address list HOLDS — an anchor is one
string, so that class goes to interpretive re-anchoring, never a guess.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from corpus.remap_el import RemapHold
from corpus.transforms.html import legacy_is_addressable, path_root
from ledger.remap_el import _rewrite_params

_DOC = (
    "<html><body>"
    "<div><h1>T</h1><p>a</p><p>b</p></div>"
    "<div><p>c</p></div>"
    "</body></html>"
)


def _pairing():
    soup = BeautifulSoup(_DOC, "html.parser")
    return list(soup.find_all(legacy_is_addressable)), path_root(soup)


def test_el_leading_anchor_rewrites_and_carries_ops():
    pairing = _pairing()
    # legacy: h1(1), p(2), p(3), p(4)
    assert _rewrite_params("el=4", pairing) == ("el=2.1", "point")
    assert _rewrite_params("el=1&bbox=0,0,1,1", pairing) == ("el=1.1&bbox=0,0,1,1", "point")
    # A contiguous complete sibling run takes the §6.1.1 sibling form.
    assert _rewrite_params("el=2-3", pairing) == ("el=1.[2-3]", "sibling")


def test_non_el_leading_strings_stay_untouched():
    pairing = _pairing()
    assert _rewrite_params("page=3", pairing) is None
    assert _rewrite_params("spine=2&el=3", pairing) is None  # the EPUB axis is not ours
    assert _rewrite_params("turn=5", pairing) is None


def test_cross_subtree_range_holds_for_interpretive_reanchor():
    pairing = _pairing()
    # el=2-4 spans p(a), p(b) in div one and p(c) in div two — an address list, which
    # a single anchor string cannot spell.
    with pytest.raises(RemapHold, match="re-anchor interpretively"):
        _rewrite_params("el=2-4", pairing)
