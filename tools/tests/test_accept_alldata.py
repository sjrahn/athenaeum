import runpy
from pathlib import Path

from corpus import segments

CHECK_ORDER = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "accept_alldata.py")
)["check_order"]


def _segment(address: str) -> segments.Segment:
    return segments.Segment(atom="text", address=address, body="text")


def test_order_check_still_detects_subject_content_inversions():
    article = segments.Section(
        form="article",
        segments=[_segment("el=2"), _segment("el=1")],
    )

    result = CHECK_ORDER([article])

    assert result["inversions"] == 1
    assert result["pass"] is False


def test_order_check_defers_to_nav_region_declaration_order():
    nav = segments.Section(
        form="nav",
        segments=[_segment("el=2"), _segment("el=1")],
    )

    result = CHECK_ORDER([nav])

    assert result["inversions"] == 0
    assert result["pass"] is True
