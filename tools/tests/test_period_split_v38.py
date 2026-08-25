"""spec v38 — the rendered-local date axis: `render_timezone` on a producer origin
overlay, the `bucket_rendered_local` primitive, and its `period-split` integration
(spec §12.3.14, CHANGELOG v38).

Does not touch `test_period_split.py`/`test_period_split_v36.py` — those suites must
stay green byte-identically: no `render_timezone` declared means no behavior change
(§12.3.14, "an undeclared rendered-local axis" only exists where declared).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from corpus import schemas
from corpus._cli import period_split
from corpus._cli._common import bucket_rendered_local


def _corpus(tmp_path: Path, partition_yaml: str | None, origin_id: str) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    schema_dir = root / "schema" / "origin"
    schema_dir.mkdir(parents=True)
    if partition_yaml is not None:
        (schema_dir / f"{origin_id}.yaml").write_text(f"description: test\n{partition_yaml}")
    schemas.cache_clear()
    return root


def _run(
    root: Path,
    source: Path,
    *,
    origin: str,
    date_from: str,
    current_period: str | None = "2026-02",
    render_timezone: str | None = None,
) -> int:
    return period_split.run(
        argparse.Namespace(
            source=str(source),
            origin=origin,
            date_from=date_from,
            current_period=current_period,
            corpus_root=str(root),
            render_timezone=render_timezone,
        )
    )


def _sidecar_yaml(zip_path: Path) -> dict:
    return yaml.safe_load(zip_path.with_suffix(zip_path.suffix + ".capture.yaml").read_text())


def _mk_member(src_dir: Path, stem: str, sidecar_date: str | None) -> None:
    """A generic file-grain member `<stem>.dat` with an optional `<stem>.dat.json`
    sidecar carrying `{"date": sidecar_date}` — the osxphotos-style pairing convention,
    reused here as a stand-in for any producer since only the pairing lookup cares which
    convention it is."""
    src_dir.mkdir(parents=True, exist_ok=True)
    p = src_dir / f"{stem}.dat"
    p.write_bytes(f"bytes-{stem}".encode())
    if sidecar_date is not None:
        sc = src_dir / f"{stem}.dat.json"
        sc.write_text(json.dumps({"date": sidecar_date}))


# ---------- 1. bucket_rendered_local ---------- #


def test_bucket_rendered_local_ordinary_case():
    edmonton = ZoneInfo("America/Edmonton")
    # A face-value morning read stays in the same UTC month deep inside a month.
    dt = datetime(2023, 6, 15, 9, 0, 0)
    assert bucket_rendered_local(dt, edmonton) == (2023, 6)


def test_bucket_rendered_local_dst_boundary_crosses_utc_month():
    """2023-06-30 18:30 America/Edmonton (MDT, UTC-6) is 2023-07-01 00:30 UTC — the
    rendered face value says June, but the UTC bucket (what boundaries key on) is
    July."""
    edmonton = ZoneInfo("America/Edmonton")
    dt = datetime(2023, 6, 30, 18, 30, 0)
    assert bucket_rendered_local(dt, edmonton) == (2023, 7)


def test_bucket_rendered_local_ambiguous_time_uses_fold_zero():
    """2023-11-05 01:30 America/Edmonton is the repeated hour at the fall-back DST
    transition (MDT->MST). fold=0 (the documented, deterministic choice) reads the
    PRE-transition offset — MDT, UTC-6 — landing at 2023-11-05 07:30 UTC, not the
    fold=1 MST (UTC-7) reading of 08:30 UTC."""
    edmonton = ZoneInfo("America/Edmonton")
    ambiguous = datetime(2023, 11, 5, 1, 30, 0)
    assert ambiguous.fold == 0  # naive construction defaults to fold=0
    fold0_utc = ambiguous.replace(tzinfo=edmonton).astimezone(ZoneInfo("UTC"))
    fold1_utc = ambiguous.replace(tzinfo=edmonton, fold=1).astimezone(ZoneInfo("UTC"))
    assert fold0_utc.hour == 7 and fold1_utc.hour == 8
    assert bucket_rendered_local(ambiguous, edmonton) == (2023, 11)


def test_bucket_rendered_local_rejects_aware_input():
    edmonton = ZoneInfo("America/Edmonton")
    aware = datetime(2023, 6, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
    with pytest.raises(ValueError, match="expects a naive datetime"):
        bucket_rendered_local(aware, edmonton)


# ---------- 2. _sidecar_date_year_month with a declared render_zone ---------- #


def test_sidecar_naive_value_unaffected_when_no_zone_given():
    assert period_split._sidecar_date_year_month(
        json.dumps({"date": "2023-06-30T18:30:00"}).encode(), "date"
    ) == (2023, 6)  # face value, unchanged pre-v38 behavior


def test_sidecar_naive_value_converts_through_declared_zone():
    edmonton = ZoneInfo("America/Edmonton")
    assert period_split._sidecar_date_year_month(
        json.dumps({"date": "2023-06-30T18:30:00"}).encode(), "date", edmonton
    ) == (2023, 7)  # crosses the UTC month boundary


def test_sidecar_aware_value_unaffected_by_declared_zone():
    edmonton = ZoneInfo("America/Edmonton")
    assert period_split._sidecar_date_year_month(
        json.dumps({"date": "2023-06-30T18:30:00+00:00"}).encode(), "date", edmonton
    ) == (2023, 6)  # already carries its own offset — the declared zone never applies


def test_sidecar_epoch_value_unaffected_by_declared_zone():
    edmonton = ZoneInfo("America/Edmonton")
    epoch = int(datetime(2023, 7, 1, 0, 30, 0, tzinfo=ZoneInfo("UTC")).timestamp())
    assert period_split._sidecar_date_year_month(
        json.dumps({"date": epoch}).encode(), "date", edmonton
    ) == (2023, 7)  # UTC by definition — the declared zone never applies


# ---------- 3. end-to-end period-split with a declared render_timezone ---------- #

_MONTH_STANDING_EDMONTON = (
    "partition:\n  grain: month\n  undated: standing\n"
    "render_timezone: America/Edmonton\n"
)
_MONTH_STANDING_NO_ZONE = "partition:\n  grain: month\n  undated: standing\n"
_BAD_ZONE = (
    "partition:\n  grain: month\n  undated: standing\n"
    "render_timezone: Not/AZone\n"
)


def test_end_to_end_declared_zone_buckets_by_utc_and_discloses_zone(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING_EDMONTON, "osxphotos-export")
    src = tmp_path / "export"
    # Face value June 30, 18:30 Edmonton -> July 1, 00:30 UTC: lands in the JULY bucket,
    # not June, straddling the UTC month boundary as the v38 amendment intends.
    _mk_member(src, "straddler", "2023-06-30T18:30:00")

    assert _run(root, src, origin="osxphotos-export", date_from="sidecar:date") == 0

    jul = root / "capture" / "export-2023-07.zip"
    assert jul.is_file()
    assert not (root / "capture" / "export-2023-06.zip").exists()

    sidecar = _sidecar_yaml(jul)
    assert sidecar["origin_fields"]["render_timezone"] == "America/Edmonton"


def test_end_to_end_no_declaration_naive_behavior_unchanged(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING_NO_ZONE, "osxphotos-export")
    src = tmp_path / "export"
    _mk_member(src, "straddler", "2023-06-30T18:30:00")

    assert _run(root, src, origin="osxphotos-export", date_from="sidecar:date") == 0

    jun = root / "capture" / "export-2023-06.zip"
    assert jun.is_file()  # face value, unchanged pre-v38 behavior
    assert not (root / "capture" / "export-2023-07.zip").exists()

    sidecar = _sidecar_yaml(jun)
    assert "render_timezone" not in sidecar["origin_fields"]


def test_end_to_end_unknown_zone_is_a_hard_error(tmp_path):
    root = _corpus(tmp_path, _BAD_ZONE, "osxphotos-export")
    src = tmp_path / "export"
    _mk_member(src, "a", "2023-06-30T18:30:00")
    with pytest.raises(SystemExit, match="not a known IANA zone"):
        _run(root, src, origin="osxphotos-export", date_from="sidecar:date")


# ---------- 4. --render-timezone CLI override (v38 refinement: export-run property) ---- #


def test_cli_override_beats_overlay_declaration(tmp_path):
    """The overlay declares America/Edmonton; --render-timezone Europe/Berlin wins for
    THIS run — different bucketing than the overlay's zone would give, and the
    disclosed field names the OVERRIDE zone, not the overlay's."""
    root = _corpus(tmp_path, _MONTH_STANDING_EDMONTON, "osxphotos-export")
    src = tmp_path / "export"
    # Face value June 30, 23:30. Berlin (+2h summer) -> Jun 30 21:30 UTC (June bucket).
    # Edmonton (-6h summer) -> Jul 1 05:30 UTC (July bucket) — the two zones disagree.
    _mk_member(src, "straddler", "2023-06-30T23:30:00")

    assert (
        _run(
            root,
            src,
            origin="osxphotos-export",
            date_from="sidecar:date",
            render_timezone="Europe/Berlin",
        )
        == 0
    )

    jun = root / "capture" / "export-2023-06.zip"
    assert jun.is_file()
    assert not (root / "capture" / "export-2023-07.zip").exists()

    sidecar = _sidecar_yaml(jun)
    assert sidecar["origin_fields"]["render_timezone"] == "Europe/Berlin"


def test_cli_override_works_with_no_overlay_declaration(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING_NO_ZONE, "osxphotos-export")
    src = tmp_path / "export"
    _mk_member(src, "straddler", "2023-06-30T18:30:00")

    assert (
        _run(
            root,
            src,
            origin="osxphotos-export",
            date_from="sidecar:date",
            render_timezone="America/Edmonton",
        )
        == 0
    )

    jul = root / "capture" / "export-2023-07.zip"
    assert jul.is_file()
    sidecar = _sidecar_yaml(jul)
    assert sidecar["origin_fields"]["render_timezone"] == "America/Edmonton"


def test_cli_override_invalid_zone_exits_cleanly(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING_NO_ZONE, "osxphotos-export")
    src = tmp_path / "export"
    _mk_member(src, "a", "2023-06-30T18:30:00")
    with pytest.raises(SystemExit, match="not a known IANA zone"):
        _run(
            root,
            src,
            origin="osxphotos-export",
            date_from="sidecar:date",
            render_timezone="Not/AZone",
        )
