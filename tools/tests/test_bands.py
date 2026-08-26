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
    """No numpy import anywhere in the module — Pillow getextrema() only."""
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
