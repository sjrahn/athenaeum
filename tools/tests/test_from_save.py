"""From-save capture — replay a manual SingleFile save (§12.3.12).

The provenance resolution is pure (offline). The browser replay round-trip needs
the `[capture]` extra (Playwright + chromium) but no network; it is marked
`network` to match the convention for browser-dependent capture tests (the marker
is skipped by default; run with `--run-network`).
"""

from __future__ import annotations

import pytest

from corpus import capture as capture_lib

_BANNER_HTML = (
    "<!DOCTYPE html> <html><!--\n"
    " Page saved with SingleFile \n"
    " url: https://example.com/lab?id=42 \n"
    " saved date: Mon Jul 06 2026 13:48:48 GMT-0600 (Mountain Daylight Time)\n"
    "--><head><meta charset=utf-8><title>Lab 42</title></head>"
    "<body><div id=chrome>NAVIGATION CHROME</div>"
    "<main>THE LAB CONTENT</main></body></html>"
)


# ---------- provenance resolution (offline) ---------- #


def test_provenance_from_banner(tmp_path):
    src = tmp_path / "save.html"
    src.write_text(_BANNER_HTML, encoding="utf-8")
    prov = capture_lib.resolve_from_save_provenance(src)
    assert prov.url == "https://example.com/lab?id=42"
    assert prov.saved_at == "2026-07-06T13:48:48-06:00"
    assert prov.source == "banner"


def test_provenance_banner_beats_sidecar(tmp_path):
    """A SingleFile banner is the primary provenance even when a sidecar also exists."""
    src = tmp_path / "save.html"
    src.write_text(_BANNER_HTML, encoding="utf-8")
    (tmp_path / "save.html.capture.yaml").write_text(
        "source_url: https://example.com/OTHER\nfetched_at: 2020-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    prov = capture_lib.resolve_from_save_provenance(src)
    assert prov.url == "https://example.com/lab?id=42"
    assert prov.source == "banner"


def test_provenance_sidecar_fallback(tmp_path):
    """No banner → the `.capture.yaml` sidecar's source_url / fetched_at."""
    src = tmp_path / "plain.html"
    src.write_text("<html><body>no banner</body></html>", encoding="utf-8")
    (tmp_path / "plain.html.capture.yaml").write_text(
        "source_url: https://example.com/from-sidecar\nfetched_at: 2026-05-01T12:00:00-06:00\n",
        encoding="utf-8",
    )
    prov = capture_lib.resolve_from_save_provenance(src)
    assert prov.url == "https://example.com/from-sidecar"
    assert prov.saved_at == "2026-05-01T12:00:00-06:00"
    assert prov.source == "sidecar"


def test_provenance_neither_raises_clean_error(tmp_path):
    src = tmp_path / "mystery.html"
    src.write_text("<html><body>who knows</body></html>", encoding="utf-8")
    with pytest.raises(capture_lib.CaptureError, match="no SingleFile banner"):
        capture_lib.resolve_from_save_provenance(src)


# ---------- full browser replay round-trip (needs [capture]; no network) ---------- #


@pytest.mark.network
def test_from_save_round_trip_replays_interactions_and_stamps_saved_date(tmp_path):
    from corpus import records
    from corpus._cli import dispatch

    root = tmp_path / "scratch"
    assert dispatch(["init", str(root)]) == 0

    # A host overlay whose interactions strip the page chrome (#chrome) — the same
    # remove-vocabulary live capture uses; from-save must replay it.
    overlay = root / "schema" / "origin" / "web" / "example.com.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        "applies_to:\n"
        "  host_pattern: example.com\n"
        "  include_subdomains: true\n"
        "capture:\n"
        "  interactions:\n"
        "    - remove: ['#chrome']\n",
        encoding="utf-8",
    )

    save = root / "capture" / "manual-save.html"
    save.parent.mkdir(parents=True, exist_ok=True)
    save.write_text(_BANNER_HTML, encoding="utf-8")

    record_path = capture_lib.capture_from_save_and_ingest(save, corpus_root=root)
    assert record_path is not None and record_path.is_file()

    # The source manual save is RETAINED (never unlinked).
    assert save.is_file()

    # The first origin is a retrieval origin from the banner: uri + saved-date snapshot.
    post = records.load(record_path)
    origin = next(records.iter_origin_blocks(post))
    fields = origin["fields"]
    assert fields["uri"] == "https://example.com/lab?id=42"
    assert fields["snapshot"] == "2026-07-06T13:48:48-06:00"  # saved date, not now

    # The re-snapshot artifact ran the overlay's interactions: chrome removed, content kept.
    rid = post.metadata["id"]
    artifact = root / "artifacts" / rid[:2] / f"{rid}.html"
    html = artifact.read_text(encoding="utf-8")
    assert "THE LAB CONTENT" in html
    assert "NAVIGATION CHROME" not in html
