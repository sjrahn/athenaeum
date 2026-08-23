"""spec v36 — `partition.onboarding`, producer-declared sidecar pairing, and the
epoch-seconds sidecar date axis (spec §12.3.14, CHANGELOG v36).

Does not touch `test_period_split.py`/`test_mbox_partition.py`/`test_mbox_split.py` —
the pre-v36 osxphotos/mbox-partition suites, which must stay green byte-identically
(absence of `onboarding:` reads as `measured`, and the osxphotos pairing convention is
unchanged, just now reached through the producer registry instead of a hardcoded call).
"""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from corpus import schemas
from corpus._cli import period_split


def _corpus(tmp_path: Path, partition_yaml: str | None, origin_id: str) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    schema_dir = root / "schema" / "origin"
    schema_dir.mkdir(parents=True)
    if partition_yaml is not None:
        (schema_dir / f"{origin_id}.yaml").write_text(f"description: test\n{partition_yaml}")
    schemas.cache_clear()
    return root


def _touch(p: Path, mtime_iso: str) -> None:
    ts = datetime.fromisoformat(mtime_iso).timestamp()
    os.utime(p, (ts, ts))


def _run(
    root: Path,
    source: Path,
    *,
    origin: str,
    date_from: str,
    current_period: str | None = "2026-02",
) -> int:
    return period_split.run(
        argparse.Namespace(
            source=str(source),
            origin=origin,
            date_from=date_from,
            current_period=current_period,
            corpus_root=str(root),
        )
    )


def _sidecar_yaml(zip_path: Path) -> dict:
    return yaml.safe_load(zip_path.with_suffix(zip_path.suffix + ".capture.yaml").read_text())


# ---------- 1. partition.onboarding ---------- #

_MEASURED_EXPLICIT = "partition:\n  grain: month\n  onboarding: measured\n"
_SETTLED_FIRST_CUT = "partition:\n  grain: month\n  onboarding: settled-first-cut\n"
_NO_ONBOARDING_KEY = "partition:\n  grain: month\n"
_BAD_ONBOARDING = "partition:\n  grain: month\n  onboarding: nonsense\n"


def test_onboarding_absent_reads_as_measured(tmp_path):
    root = _corpus(tmp_path, _NO_ONBOARDING_KEY, "some-producer")
    schedule = schemas.resolve_partition(root, "application/zip", origin_id="some-producer")
    assert schedule is not None
    assert schedule.get("onboarding", "measured") == "measured"


def test_onboarding_measured_explicit_validates(tmp_path):
    root = _corpus(tmp_path, _MEASURED_EXPLICIT, "some-producer")
    schedule = schemas.resolve_partition(root, "application/zip", origin_id="some-producer")
    assert schedule is not None and schedule["onboarding"] == "measured"


def test_onboarding_settled_first_cut_admits_without_measurement(tmp_path):
    """The whole point of the mode: a `partition:` block declares successfully with NO
    banked two-export diff anywhere — the ruling replaces it, and nothing in the tooling
    demands measurement text to accept the declaration."""
    root = _corpus(tmp_path, _SETTLED_FIRST_CUT, "proton-mail-export")
    schedule = schemas.resolve_partition(root, "application/zip", origin_id="proton-mail-export")
    assert schedule is not None
    assert schedule["onboarding"] == "settled-first-cut"


def test_onboarding_unknown_value_is_a_hard_error(tmp_path):
    root = _corpus(tmp_path, _BAD_ONBOARDING, "some-producer")
    with pytest.raises(ValueError, match="not a valid mode") as excinfo:
        schemas.resolve_partition(root, "application/zip", origin_id="some-producer")
    assert "measured" in str(excinfo.value) and "settled-first-cut" in str(excinfo.value)


def test_onboarding_unknown_value_exits_cleanly_from_period_split(tmp_path):
    root = _corpus(tmp_path, _BAD_ONBOARDING, "some-producer")
    src = tmp_path / "export"
    src.mkdir()
    (src / "a.eml").write_bytes(b"x")
    with pytest.raises(SystemExit, match="onboarding"):
        _run(root, src, origin="some-producer", date_from="mtime")


# ---------- 2. producer-declared sidecar pairing ---------- #

_MONTH_STANDING = "partition:\n  grain: month\n  undated: standing\n"


def _mk_eml(src_dir: Path, stem: str, mtime_iso: str, epoch_time: int | None = None) -> None:
    """A Proton-shaped message member `<stem>.eml` with an optional
    `<stem>.metadata.json` sidecar carrying `{"Time": epoch_time}`."""
    src_dir.mkdir(parents=True, exist_ok=True)
    p = src_dir / f"{stem}.eml"
    p.write_bytes(f"eml-bytes-{stem}".encode())
    _touch(p, mtime_iso)
    if epoch_time is not None:
        sc = src_dir / f"{stem}.metadata.json"
        sc.write_text(json.dumps({"Time": epoch_time}))
        _touch(sc, mtime_iso)


def _epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def test_proton_eml_pairs_with_metadata_json(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING, "proton-mail-export")
    src = tmp_path / "export"
    _mk_eml(src, "msg1", "2025-11-01T10:00:00", _epoch("2025-11-01T10:00:00+00:00"))

    assert _run(root, src, origin="proton-mail-export", date_from="sidecar:Time") == 0
    nov = root / "capture" / "export-2025-11.zip"
    assert nov.is_file()
    with zipfile.ZipFile(nov) as z:
        names = set(z.namelist())
    assert names == {"msg1.eml", "msg1.metadata.json"}


def test_labels_json_excluded_and_disclosed(tmp_path, capsys):
    root = _corpus(tmp_path, _MONTH_STANDING, "proton-mail-export")
    src = tmp_path / "export"
    _mk_eml(src, "msg1", "2025-11-01T10:00:00", _epoch("2025-11-01T10:00:00+00:00"))
    (src / "labels.json").write_text(json.dumps({"labels": ["Inbox", "Archive"]}))
    _touch(src / "labels.json", "2025-11-01T10:00:00")

    assert _run(root, src, origin="proton-mail-export", date_from="sidecar:Time") == 0

    for zip_path in (root / "capture").glob("*.zip"):
        with zipfile.ZipFile(zip_path) as z:
            assert "labels.json" not in z.namelist()

    nov = root / "capture" / "export-2025-11.zip"
    sidecar = _sidecar_yaml(nov)
    assert sidecar["origin_fields"]["export_level_metadata"] == ["labels.json"]

    out = capsys.readouterr().out
    assert "labels.json" in out and "excluded from bucketing" in out


def test_unregistered_producer_with_sidecar_axis_is_a_hard_error(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING, "mystery-producer")
    src = tmp_path / "export"
    src.mkdir()
    (src / "a.eml").write_bytes(b"x")
    with pytest.raises(SystemExit, match="no registered sidecar-pairing convention"):
        _run(root, src, origin="mystery-producer", date_from="sidecar:Time")
    # The error names the registered producers, never leaves the operator guessing.
    with pytest.raises(SystemExit, match="osxphotos-export"):
        _run(root, src, origin="mystery-producer", date_from="sidecar:Time")


def test_unregistered_producer_with_mtime_axis_still_works(tmp_path):
    """No pairing convention is only fatal for the sidecar axis — `mtime` never needs
    one, so an unregistered/generic producer stays usable for it."""
    root = _corpus(tmp_path, _MONTH_STANDING, "mystery-producer")
    src = tmp_path / "export"
    src.mkdir()
    p = src / "a.eml"
    p.write_bytes(b"x")
    _touch(p, "2025-11-01T10:00:00")
    assert _run(root, src, origin="mystery-producer", date_from="mtime") == 0
    assert (root / "capture" / "export-2025-11.zip").is_file()


# ---------- 3. epoch-seconds sidecar date axis ---------- #


def test_epoch_axis_buckets_to_correct_utc_year_month(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING, "proton-mail-export")
    src = tmp_path / "export"
    _mk_eml(src, "before", "2023-07-31T23:59:59", 1690847999)  # 2023-07-31 23:59:59 UTC
    _mk_eml(src, "after", "2023-08-01T00:00:00", 1690848000)   # 2023-08-01 00:00:00 UTC

    assert _run(root, src, origin="proton-mail-export", date_from="sidecar:Time") == 0
    jul = root / "capture" / "export-2023-07.zip"
    aug = root / "capture" / "export-2023-08.zip"
    assert jul.is_file() and aug.is_file()
    with zipfile.ZipFile(jul) as z:
        assert "before.eml" in z.namelist()
    with zipfile.ZipFile(aug) as z:
        assert "after.eml" in z.namelist()


def test_epoch_axis_rejects_bool():
    assert period_split._sidecar_date_year_month(
        json.dumps({"Time": True}).encode(), "Time"
    ) is None


def test_epoch_axis_string_iso_still_works():
    assert period_split._sidecar_date_year_month(
        json.dumps({"Time": "2025-11-01T10:00:00+00:00"}).encode(), "Time"
    ) == (2025, 11)


def test_epoch_axis_rejects_negative_and_absurd_values():
    assert period_split._sidecar_date_year_month(
        json.dumps({"Time": -100}).encode(), "Time"
    ) is None
    # Far beyond datetime's year-9999 ceiling.
    assert period_split._sidecar_date_year_month(
        json.dumps({"Time": 999999999999999}).encode(), "Time"
    ) is None


# ---------- 4. end to end: a synthetic proton-shaped export ---------- #


def test_end_to_end_proton_shaped_export(tmp_path, capsys):
    root = _corpus(tmp_path, _MONTH_STANDING, "proton-mail-export")
    src = tmp_path / "export"
    _mk_eml(src, "nov-1", "2025-11-01T10:00:00", _epoch("2025-11-01T10:00:00+00:00"))
    _mk_eml(src, "nov-2", "2025-11-15T10:00:00", _epoch("2025-11-15T10:00:00+00:00"))
    _mk_eml(src, "jan-1", "2026-01-05T10:00:00", _epoch("2026-01-05T10:00:00+00:00"))
    (src / "labels.json").write_text(json.dumps({"labels": ["Inbox"]}))
    _touch(src / "labels.json", "2025-11-01T10:00:00")

    assert _run(root, src, origin="proton-mail-export", date_from="sidecar:Time") == 0

    capture = root / "capture"
    nov = capture / "export-2025-11.zip"
    jan = capture / "export-2026-01.zip"
    current = capture / "export-current-2026-02.zip"
    assert nov.is_file() and jan.is_file() and current.is_file()

    with zipfile.ZipFile(nov) as z:
        names = set(z.namelist())
    assert names == {"nov-1.eml", "nov-1.metadata.json", "nov-2.eml", "nov-2.metadata.json"}

    nov_sidecar = _sidecar_yaml(nov)
    assert nov_sidecar["origin_fields"]["member_count"] == 2
    assert nov_sidecar["origin_fields"]["sidecar_count"] == 2
    assert nov_sidecar["origin_fields"]["export_level_metadata"] == ["labels.json"]
    assert nov_sidecar["origin_schema"] == "proton-mail-export"

    for zip_path in (nov, jan, current):
        with zipfile.ZipFile(zip_path) as z:
            assert "labels.json" not in z.namelist()

    out = capsys.readouterr().out
    assert "labels.json" in out
