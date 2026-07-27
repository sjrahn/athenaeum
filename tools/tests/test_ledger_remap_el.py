"""`ath ledger remap-el` — the anchor-side §12.28 remap (ledger.remap_el).

The mapping itself is `corpus.remap_el.map_el_value` (pinned in test_el_path_36); what
this file pins is the LEDGER grammar around it: only el-LEADING param strings rewrite
(the EPUB `spine=…&el=…` axis and every other axis stay untouched), chained ops ride
along, a flat range becomes the tightest §6.1.1 envelope CONTAINING it — including when
its endpoints sit in different subtrees, which is the ordinary case and not a hold — and
the one interval with no §6.1.1 spelling (its endpoints' nearest common ancestor is the
path root itself) HOLDS for a deliberate re-scope rather than being guessed at.
"""

from __future__ import annotations

import json

import pytest
from bs4 import BeautifulSoup

from corpus.remap_el import RemapHold
from corpus.transforms.html import legacy_is_addressable, path_root
from ledger.remap_el import _Pairing, _rewrite_params, load_migrated_ids

_DOC = (
    "<html><body><main>"
    "<div><h1>T</h1><p>a</p><p>b</p></div>"
    "<div><p>c</p></div>"
    "<div><p>d</p></div>"
    "</main></body></html>"
)

#: The endpoints' nearest common ancestor is <body> itself — no `el=<parent>.[a-b]`.
_ROOT_LEVEL_DOC = (
    "<html><body>"
    "<div><h1>T</h1><p>a</p><p>b</p></div>"
    "<div><p>c</p></div>"
    "</body></html>"
)


def _pairing(doc: str = _DOC):
    soup = BeautifulSoup(doc, "html.parser")
    return list(soup.find_all(legacy_is_addressable)), path_root(soup)


def test_el_leading_anchor_rewrites_and_carries_ops():
    pairing = _pairing()
    # legacy: h1(1), p a(2), p b(3), p c(4)
    assert _rewrite_params("el=4", pairing) == ("el=1.2.1", "point")
    assert _rewrite_params("el=1&bbox=0,0,1,1", pairing) == ("el=1.1.1&bbox=0,0,1,1", "point")
    # Two siblings of one parent take the sibling form over their own slots.
    assert _rewrite_params("el=2-3", pairing) == ("el=1.1.[2-3]", "sibling")


def test_cross_subtree_range_takes_the_containing_envelope():
    """An interval crossing subtree boundaries is NOT held and NOT a list of its
    endpoints: it is the sibling range over their slots in the nearest common ancestor,
    which is the tightest address that contains what the flat form claimed."""
    pairing = _pairing()
    # el=2-4 runs from p(a) inside div one to p(c) inside div two; both hang under
    # <main>, at slots 1 and 2 of its three.
    assert _rewrite_params("el=2-4", pairing) == ("el=1.[1-2]", "sibling")


def test_range_nested_inside_one_element_collapses_to_its_subtree():
    pairing = _pairing()
    # h1(1) through p(b)(3) all sit inside div one — one address, its subtree.
    assert _rewrite_params("el=1-3", pairing) == ("el=1.1", "subtree")


def test_interval_covering_every_child_is_spelled_as_the_subtree():
    """§6.1.1: a span that IS a subtree is spelled as that subtree, never as a range
    over its full child list — one extent, one spelling."""
    pairing = _pairing()
    # el=1-5 runs from the first h1 to the last p: every child of <main>.
    assert _rewrite_params("el=1-5", pairing) == ("el=1", "subtree")


def test_root_level_interval_holds_for_deliberate_rescope():
    pairing = _pairing(_ROOT_LEVEL_DOC)
    with pytest.raises(RemapHold, match=r"no .*sibling\-range spelling"):
        _rewrite_params("el=2-4", pairing)


class _StubJoin:
    """A join that resolves every hash, so eligibility is the only thing under test."""

    def holders(self, record_hash):
        return [object()]


def test_manifest_is_the_eligibility_set(tmp_path):
    """Only records the corpus remap actually REWROTE may have their anchors rewritten.
    A record it held keeps the legacy grammar (no `addressing:` stamp), so its anchors
    must keep the legacy spelling — rewriting them would aim a §6.1.1 path at a record
    that still reads integers, which is the one silent break this migration can cause."""
    m = tmp_path / "remap.jsonl"
    m.write_text(
        "\n".join([
            json.dumps({"record": "aaa", "changed": True}),
            json.dumps({"record": "bbb", "changed": False, "hold": "addresses alias"}),
            json.dumps({"record": "ccc", "changed": False, "skipped": "no el= addresses"}),
            "",
        ]),
        encoding="utf-8",
    )
    assert load_migrated_ids([m]) == {"aaa"}

    pairings = _Pairing(_StubJoin(), load_migrated_ids([m]))
    assert pairings.get("bbb") == "NOT-MIGRATED"
    assert pairings.get("ccc") == "NOT-MIGRATED"
    assert pairings.get("never-seen") == "NOT-MIGRATED"


def test_non_el_leading_strings_stay_untouched():
    pairing = _pairing()
    assert _rewrite_params("page=3", pairing) is None
    assert _rewrite_params("spine=2&el=3", pairing) is None  # the EPUB axis is not ours
    assert _rewrite_params("turn=5", pairing) is None
