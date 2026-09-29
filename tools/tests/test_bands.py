"""Tests for corpus.bands — pixel-truth band audit. No numpy anywhere."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from corpus.bands import (
    Row,
    audit_bands,
    ink_rows,
    matches_chrome_profile,
    snap,
    uncovered,
)

HEIGHT = 1000
WIDTH = 50


def _make_page(tmp_path: Path, name: str, bars: list[tuple[int, int]]) -> Path:
    """A white HEIGHT x WIDTH page with black full-width bars at the given
    (y0, y1) pixel ranges — a stand-in for rendered text rows."""
    im = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(im)
    for y0, y1 in bars:
        draw.rectangle([0, y0, WIDTH - 1, y1 - 1], fill=0)
    path = tmp_path / name
    im.save(path)
    return path


# ---------- ink_rows ---------- #


def test_ink_rows_detects_separate_rows(tmp_path):
    path = _make_page(tmp_path, "two_rows.png", [(100, 140), (200, 230)])
    assert ink_rows(path) == [Row(0.1, 0.14), Row(0.2, 0.23)]


def test_ink_rows_merges_small_gap(tmp_path):
    # 3px gap, well under MIN_GAP_PX (6) — one merged row.
    path = _make_page(tmp_path, "close_rows.png", [(300, 310), (313, 323)])
    assert ink_rows(path) == [Row(0.3, 0.323)]


def test_ink_rows_keeps_wide_gap_separate(tmp_path):
    # 10px gap, over MIN_GAP_PX — two rows.
    path = _make_page(tmp_path, "wide_gap.png", [(300, 310), (320, 330)])
    assert ink_rows(path) == [Row(0.3, 0.31), Row(0.32, 0.33)]


def test_ink_rows_blank_page_no_rows(tmp_path):
    assert ink_rows(_make_page(tmp_path, "blank.png", [])) == []


def test_ink_rows_is_pillow_only():
    """No numpy import anywhere in the module — Pillow projections only."""
    import corpus.bands as bands_mod

    src = Path(bands_mod.__file__).read_text(encoding="utf-8")
    assert "import numpy" not in src


# ---------- audit_bands / uncovered / snap, against one measured page ---------- #


def _measured_page(tmp_path: Path) -> list[Row]:
    """One synthetic page carrying five rows exercising every finding kind:
    a heading (for a cutting band), a clean paragraph, an orphan paragraph no
    band covers, a drifted paragraph, and a footer standing in for chrome."""
    path = _make_page(
        tmp_path,
        "audit_page.png",
        [
            (100, 140),  # heading
            (200, 230),  # clean paragraph
            (500, 530),  # orphan paragraph
            (600, 620),  # drifted paragraph
            (950, 970),  # footer (chrome)
        ],
    )
    return ink_rows(path)


def test_audit_bands_cuts_through_heading(tmp_path):
    rows = _measured_page(tmp_path)
    assert rows[0] == Row(0.1, 0.14)
    bands = [(1, 0.0, 0.12, 5)]  # bottom edge at 0.12 slices through the heading
    findings = audit_bands(bands, lambda p: rows)
    assert len(findings) == 1
    assert findings[0].kind == "cuts"
    assert findings[0].line == 5


def test_audit_bands_clean_band_is_silent(tmp_path):
    rows = _measured_page(tmp_path)
    bands = [(1, 0.195, 0.235, 9)]  # tolerant padding around [0.2, 0.23]
    assert audit_bands(bands, lambda p: rows) == []


def test_audit_bands_swallows_chrome(tmp_path):
    rows = _measured_page(tmp_path)
    footer = rows[-1]
    assert footer == Row(0.95, 0.97)
    bands = [(1, 0.945, 0.975, 20)]
    findings = audit_bands(bands, lambda p: rows, chrome=[footer])
    assert len(findings) == 1
    assert findings[0].kind == "chrome"
    assert findings[0].line == 20


def test_audit_bands_detects_drift(tmp_path):
    rows = _measured_page(tmp_path)
    bands = [(1, 0.55, 0.65, 30)]  # padded well beyond the [0.6, 0.62] paragraph
    findings = audit_bands(bands, lambda p: rows)
    assert len(findings) == 1
    assert findings[0].kind == "drift"
    assert findings[0].line == 30


def test_uncovered_finds_orphan_row_between_two_bands(tmp_path):
    rows = _measured_page(tmp_path)
    footer = rows[-1]
    bands = [
        (1, 0.0, 0.12, 5),
        (1, 0.195, 0.235, 9),
        (1, 0.55, 0.65, 30),
        (1, 0.945, 0.975, 20),
    ]
    missing = uncovered(bands, {1: rows}, [footer])
    assert len(missing) == 1
    page, row = missing[0]
    assert page == 1
    assert row == Row(0.5, 0.53)  # the orphan paragraph — no band spans it


def test_matches_chrome_profile_flags_shifted_footer():
    chrome = [Row(0.955, 0.965)]  # a recurring footer cluster, height 0.01
    shifted = Row(0.930, 0.940)  # same height, shifted up to the y_tol boundary
    assert matches_chrome_profile(shifted, chrome)
    unrelated = Row(0.2, 0.21)  # a body row, nowhere near a margin
    assert not matches_chrome_profile(unrelated, chrome)


def test_snap_finds_nearest_gap_midpoint(tmp_path):
    rows = _measured_page(tmp_path)
    # gaps (bottom_i + top_{i+1}) / 2: 0.17, 0.365, 0.565, 0.785
    assert snap(0.55, rows) == 0.565
    assert snap(0.0, rows) == 0.17


def test_snap_no_gap_returns_none():
    assert snap(0.5, [Row(0.1, 0.2)]) is None


# ---------- PageInk: the three false-positive modes (arbre-ath-steven's PDF eval) ---------- #

from corpus.bands import PageInk  # noqa: E402

PW, PH = 800, 1000


def _page(tmp_path: Path, name: str, paint) -> PageInk:
    im = Image.new("L", (PW, PH), color=255)
    paint(ImageDraw.Draw(im))
    path = tmp_path / name
    im.save(path)
    return PageInk(path)


def _lines(draw, x0: int, x1: int, tops: list[int], h: int = 12, fill: int = 0) -> None:
    for t in tops:
        draw.rectangle([x0, t, x1, t + h - 1], fill=fill)


def test_a_full_bleed_picture_is_never_a_cut(tmp_path):
    """e00c8dfa: the whole page inked, so every band edge measured inside one row [0, 1]."""
    def paint(d):
        d.rectangle([0, 0, PW - 1, PH - 1], fill=90)
        for y in range(0, PH, 3):  # photographic texture: no blank scanline anywhere
            d.line([(0, y), (PW - 1, y)], fill=60)
    ink = _page(tmp_path, "bleed.png", paint)
    for edge in (0.1, 0.33, 0.5, 0.77):
        hit = ink.edge_cut(edge, 0.05, 0.95)
        assert hit is None or hit[0] == "opaque"


def test_box_rules_and_show_through_do_not_merge_a_scan_into_one_row(tmp_path):
    """f1452162: a box's vertical rules ink every scanline they cross, and the reverse side's
    show-through lands as sparse specks — together they merged [0.12, 0.65] into one row."""
    def paint(d):
        d.rectangle([0, 0, PW - 1, PH - 1], fill=236)  # scan paper tone
        d.line([(40, 120), (40, 650)], fill=0, width=3)  # box rules
        d.line([(760, 120), (760, 650)], fill=0, width=3)
        _lines(d, 80, 700, [200, 230, 260, 400, 430])
        for y in range(120, 650, 4):  # show-through specks, a pixel or two per scanline
            d.point([(300 + (y * 7) % 300, y)], fill=100)
    ink = _page(tmp_path, "scan.png", paint)
    rows = ink.rows(0.0, 1.0)
    assert all(r.height < 0.1 for r in rows), rows
    assert ink.edge_cut(0.33, 0.04, 0.96) is None  # the gap between two paragraphs
    hit = ink.edge_cut(0.236, 0.04, 0.96)  # through the second line
    assert hit is not None and hit[0] == "cuts"


def test_a_band_is_measured_against_its_own_column(tmp_path):
    """e84ada4d: the right column's lines fill the left column's gaps; a left-column band's
    edge in its own paragraph gap measured as inside a merged row [0.286, 0.49]."""
    def paint(d):
        _lines(d, 40, 370, [300, 320, 340, 400, 420])  # left: paragraph, gap, paragraph
        _lines(d, 430, 760, [300, 320, 340, 360, 380, 400, 420])  # right: unbroken
    ink = _page(tmp_path, "cols.png", paint)
    assert ink.edge_cut(0.37, 0.04, 0.47) is None  # the left column's own gap
    hit = ink.edge_cut(0.37, 0.04, 0.96)  # a full-width band DOES cut the right column
    assert hit is not None and hit[0] == "cuts" and hit[2][0] > 0.5


def test_light_text_on_a_dark_panel_is_measured_under_the_panels_tone(tmp_path):
    """e00c8dfa p2: a dark panel on a white page — under the page's tone the whole panel is
    ink; under its own it is light text with gaps."""
    def paint(d):
        d.rectangle([0, 300, PW - 1, 700], fill=15)
        _lines(d, 60, 700, [400, 420, 500, 520], fill=240)
    ink = _page(tmp_path, "panel.png", paint)
    assert ink.edge_cut(0.46, 0.05, 0.9) is None
    hit = ink.edge_cut(0.405, 0.05, 0.9)
    assert hit is not None and hit[0] == "cuts"


def test_audit_bands_measures_each_band_in_its_own_x_range(tmp_path):
    def paint(d):
        _lines(d, 40, 370, [300, 320, 340, 400, 420])
        _lines(d, 430, 760, [300, 320, 340, 360, 380, 400, 420])
    ink = _page(tmp_path, "cols2.png", paint)
    left = (1, 0.29, 0.37, 7, 0.04, 0.47)
    wide = (1, 0.29, 0.37, 9, 0.04, 0.96)
    found = audit_bands([left, wide], lambda p: ink.rows(), page_ink=lambda p: ink)
    assert [f.line for f in found if f.kind == "cuts"] == [9]


def test_an_edge_along_a_horizontal_rule_cuts_nothing(tmp_path):
    def paint(d):
        _lines(d, 40, 760, [300, 320])
        d.rectangle([40, 400, 760, 401], fill=0)  # a 2px table rule
        _lines(d, 40, 760, [480, 500])
    ink = _page(tmp_path, "rule.png", paint)
    assert ink.edge_cut(0.4005, 0.04, 0.96) is None


# ---------- text-layer confirmation (v50 validation: vector line-art labels) ---------- #

from corpus.bands import confirm_cut  # noqa: E402


def _word(text, x, y, w, h):
    return {"text": text, "bbox": [x, y, w, h]}


def test_a_raster_cut_no_word_spans_is_drawing_ink():
    """An assembly diagram's label band: strokes around the label merge into one tall 'row'
    the edge crosses, but the label's own word sits wholly inside the band."""
    hit = ("cuts", Row(0.11, 0.21), (0.26, 0.32))
    words = [_word("AAA", 0.264, 0.164, 0.055, 0.043)]
    assert confirm_cut(hit, words, 0.162, 0.261, 0.321)[0] == "opaque"


def test_a_raster_cut_a_word_spans_stands():
    hit = ("cuts", Row(0.13, 0.20), (0.585, 0.675))
    words = [_word("4x", 0.595, 0.144, 0.07, 0.055)]
    assert confirm_cut(hit, words, 0.183, 0.585, 0.675) == hit


def test_a_page_with_no_text_layer_keeps_the_rasters_verdict():
    hit = ("cuts", Row(0.1, 0.2), (0.0, 1.0))
    assert confirm_cut(hit, [], 0.15, 0.0, 1.0) == hit
    assert confirm_cut(None, [], 0.15, 0.0, 1.0) is None


def test_an_edge_grazing_a_words_rim_is_a_cut_but_a_clear_label_band_is_not():
    """The two cases that size WORD_GRAZE_FRAC: an edge 0.0002 inside an `A₀` box (math ink
    reaches past the box) confirms; a label band drawn 0.002 clear of its word does not."""
    hit = ("cuts", Row(0.757, 0.781), (0.53, 0.93))
    assert confirm_cut(hit, [_word("A0", 0.60, 0.7698, 0.02, 0.0104)], 0.77, 0.51, 0.93) == hit
    label = ("cuts", Row(0.11, 0.21), (0.26, 0.32))
    words = [_word("AAA", 0.264, 0.164, 0.055, 0.043)]
    assert confirm_cut(label, words, 0.162, 0.261, 0.321)[0] == "opaque"
    assert confirm_cut(label, words, 0.21, 0.261, 0.321)[0] == "opaque"
