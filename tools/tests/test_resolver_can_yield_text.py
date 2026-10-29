"""`corpus.resolver.can_yield_text`: verify skips resolutions that could only end in
media. Before this, `ath ledger verify` parsed a whole captured HTML page per `el=` anchor
just to learn the anchor materializes an image or carrier."""

from __future__ import annotations

from pathlib import Path

from corpus.resolver import can_yield_text


def test_terminal_el_on_html_yields_no_text(tmp_path: Path) -> None:
    assert not can_yield_text(tmp_path, "text/html", [("el", "130")])


def test_text_producing_chains_yield_text(tmp_path: Path) -> None:
    assert can_yield_text(tmp_path, "text/csv", [("row", "3")])
    assert can_yield_text(tmp_path, "application/pdf", [("page", "2"), ("text", "")])


def test_inapplicable_or_unknown_yields_no_text(tmp_path: Path) -> None:
    assert not can_yield_text(tmp_path, "text/csv", [("el", "1")])
    assert not can_yield_text(tmp_path, "application/x-nothing", [("page", "1")])
