"""File-grain temporal stratification — `corpus period-split` (spec §12.3.14): the
osxphotos-convention sidecar pairing (`<member>.json`, recon'd against `corpus-private`'s
real `osxphotos-export` containers), closed-period/rolling/undated bucketing over both a
directory tree and an equivalent zip source, the `sidecar:<path>` and `mtime` date axes,
year-grain eras, determinism, and the CLI contract (`--origin` required, no schedule →
hard exit, refuse-to-overwrite).
"""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from corpus import schemas
from corpus._cli import period_split

# *(v41, spec §7.2)* The member↔sidecar pairing the v36 code registry used to hard-code
# per producer is now the producer's own `sidecar.pairing` declaration — the fixtures
# declare exactly what the registry did, so every bucketing assertion below holds
# byte-identically under the declaration (the registry's retirement is parity-tested).
_PAIRING_YAML = {
    "osxphotos-export": "sidecar:\n  pairing: {template: '{member}.json'}\n",
    "proton-mail-export": (
        "sidecar:\n  pairing: {template: '{stem}.metadata.json', "
        "export_level: [labels.json]}\n"
    ),
}


def _corpus(
    tmp_path: Path, partition_yaml: str | None, origin_id: str = "osxphotos-export"
) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    schema_dir = root / "schema" / "origin"
    schema_dir.mkdir(parents=True)
    if partition_yaml is not None:
        (schema_dir / f"{origin_id}.yaml").write_text(
            f"description: test\n{partition_yaml}{_PAIRING_YAML.get(origin_id, '')}"
        )
    schemas.cache_clear()
    return root


_MONTH_STANDING = "partition:\n  grain: month\n  undated: standing\n"
_MONTH_ROLLING = "partition:\n  grain: month\n  undated: rolling\n"
_YEAR_ERA = (
    "partition:\n  grain: month\n  eras:\n  - until: 2024\n    grain: year\n"
    "  undated: standing\n"
)


def _touch(p: Path, mtime_iso: str) -> None:
    ts = datetime.fromisoformat(mtime_iso).timestamp()
    os.utime(p, (ts, ts))


def _mk_member(
    src_dir: Path, name: str, mtime_iso: str, sidecar_date: str | None = None
) -> None:
    """A media file (osxphotos naming) at `name`, its mtime set to `mtime_iso`, with an
    optional PhotoInfo-shaped sidecar (`<name>.json`, `{"date": sidecar_date}`) sharing
    the same mtime."""
    p = src_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(f"bytes-of-{name}".encode())
    _touch(p, mtime_iso)
    if sidecar_date is not None:
        sc = src_dir / f"{name}.json"
        sc.write_text(json.dumps({"date": sidecar_date}))
        _touch(sc, mtime_iso)


def _build_standard_tree(src_dir: Path) -> None:
    """Nov 2025 (closed), Jan 2026 (closed) + a sidecar-less `_edited.jpeg` derivative
    dated the same month, Feb 2026 (current, with `--current-period 2026-02`)."""
    src_dir.mkdir(parents=True)
    _mk_member(src_dir, "IMG_0001.HEIC", "2025-11-01T10:00:00", "2025-11-01T10:00:00-06:00")
    _mk_member(src_dir, "IMG_0002.HEIC", "2026-01-15T10:00:00", "2026-01-15T10:00:00-06:00")
    _mk_member(src_dir, "IMG_0002_edited.jpeg", "2026-01-15T10:05:00")  # NO sidecar
    _mk_member(src_dir, "IMG_0003.HEIC", "2026-02-10T10:00:00", "2026-02-10T10:00:00-06:00")


def _zip_tree(src_dir: Path, target: Path) -> None:
    """Zip `src_dir`'s files, preserving each member's own mtime in its ZipInfo — the
    equivalent-zip-source fixture (mirrors what a real osxphotos export zip carries)."""
    with zipfile.ZipFile(target, "w") as z:
        for p in sorted(f for f in src_dir.rglob("*") if f.is_file()):
            rel = p.relative_to(src_dir).as_posix()
            dt = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            zi = zipfile.ZipInfo(
                rel, date_time=(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
            )
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, p.read_bytes())


def _run(
    root: Path,
    source: Path,
    *,
    origin: str = "osxphotos-export",
    date_from: str = "sidecar:date",
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


def _sidecar(zip_path: Path) -> dict:
    return yaml.safe_load(zip_path.with_suffix(zip_path.suffix + ".capture.yaml").read_text())


# ---------- closed/rolling/undated bucketing + sidecar pairing ---------- #


def test_directory_source_buckets_closed_rolling_undated(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING)
    src = tmp_path / "export"
    _build_standard_tree(src)

    assert _run(root, src) == 0

    capture = root / "capture"
    nov = capture / "export-2025-11.zip"
    jan = capture / "export-2026-01.zip"
    current = capture / "export-current-2026-02.zip"
    undated = capture / "export-undated.zip"
    assert nov.is_file() and jan.is_file() and current.is_file() and undated.is_file()

    with zipfile.ZipFile(nov) as z:
        assert z.namelist() == ["IMG_0001.HEIC", "IMG_0001.HEIC.json"]
    with zipfile.ZipFile(jan) as z:
        assert z.namelist() == ["IMG_0002.HEIC", "IMG_0002.HEIC.json"]
    with zipfile.ZipFile(current) as z:
        assert z.namelist() == ["IMG_0003.HEIC", "IMG_0003.HEIC.json"]
    with zipfile.ZipFile(undated) as z:
        # The sidecar-less `_edited.jpeg` derivative: nothing to read a date from under
        # the sidecar axis, so it falls to undated (disclosed limitation, not a bug).
        assert z.namelist() == ["IMG_0002_edited.jpeg"]

    nov_fields = _sidecar(nov)["origin_fields"]
    assert nov_fields["period"] == "2025-11"
    assert nov_fields["member_count"] == 1
    assert nov_fields["sidecar_count"] == 1
    assert nov_fields["date_axis"] == "sidecar:date"
    assert _sidecar(nov)["origin_schema"] == "osxphotos-export"

    undated_fields = _sidecar(undated)["origin_fields"]
    assert "period" not in undated_fields
    assert undated_fields["member_count"] == 1
    assert undated_fields["sidecar_count"] == 0


def test_undated_rolling_rides_current_bucket(tmp_path):
    root = _corpus(tmp_path, _MONTH_ROLLING)
    src = tmp_path / "export"
    _build_standard_tree(src)

    assert _run(root, src) == 0
    capture = root / "capture"
    assert not (capture / "export-undated.zip").exists()
    current = capture / "export-current-2026-02.zip"
    with zipfile.ZipFile(current) as z:
        assert set(z.namelist()) == {
            "IMG_0003.HEIC",
            "IMG_0003.HEIC.json",
            "IMG_0002_edited.jpeg",
        }
    fields = _sidecar(current)["origin_fields"]
    assert fields["undated_count"] == 1


# ---------- date axes ---------- #


def test_mtime_axis_buckets_the_edited_derivative_too(tmp_path):
    """Under `mtime`, the sidecar-less `_edited.jpeg` derivative DOES get a bucket (its
    own file mtime), unlike the sidecar axis."""
    root = _corpus(tmp_path, _MONTH_STANDING)
    src = tmp_path / "export"
    _build_standard_tree(src)

    assert _run(root, src, date_from="mtime") == 0
    capture = root / "capture"
    assert not (capture / "export-undated.zip").exists()
    with zipfile.ZipFile(capture / "export-2026-01.zip") as z:
        assert set(z.namelist()) == {
            "IMG_0002.HEIC",
            "IMG_0002.HEIC.json",
            "IMG_0002_edited.jpeg",
        }
    fields = _sidecar(capture / "export-2026-01.zip")["origin_fields"]
    assert fields["date_axis"] == "mtime"


def test_sidecar_axis_dotted_path_nested(tmp_path):
    """A `sidecar:<dotted.path>` axis reads a NESTED key, not just a bare top-level one."""
    root = _corpus(tmp_path, _MONTH_STANDING)
    src = tmp_path / "export"
    src.mkdir()
    p = src / "clip.mp4"
    p.write_bytes(b"video")
    _touch(p, "2025-11-01T00:00:00")
    (src / "clip.mp4.json").write_text(
        json.dumps({"meta": {"captured": "2025-11-05T00:00:00-06:00"}})
    )
    _touch(src / "clip.mp4.json", "2025-11-01T00:00:00")

    assert _run(root, src, date_from="sidecar:meta.captured") == 0
    assert (root / "capture" / "export-2025-11.zip").is_file()


def test_sidecar_axis_utc_boundary_offset_vs_naive(tmp_path):
    """The v34 UTC boundary rule (spec §12.3.14): an offset-bearing sidecar date
    converts to UTC before bucketing — here crossing BACK a month from its face value —
    while a naive sidecar date (no offset in the bytes) buckets at face value."""
    root = _corpus(tmp_path, _MONTH_STANDING)
    src = tmp_path / "export"
    src.mkdir()
    # Face value: Feb 1, 02:00+06:00. UTC: Jan 31, 20:00 -> previous month.
    _mk_member(src, "offset.HEIC", "2026-02-01T00:00:00", "2026-02-01T02:00:00+06:00")
    # No offset in the bytes: buckets at face value, Feb.
    _mk_member(src, "naive.HEIC", "2026-02-01T00:00:00", "2026-02-01T02:00:00")

    assert _run(root, src, current_period="2026-03") == 0

    capture = root / "capture"
    with zipfile.ZipFile(capture / "export-2026-01.zip") as z:
        assert z.namelist() == ["offset.HEIC", "offset.HEIC.json"]
    with zipfile.ZipFile(capture / "export-2026-02.zip") as z:
        assert z.namelist() == ["naive.HEIC", "naive.HEIC.json"]


# ---------- zip-source equivalence ---------- #


def test_zip_source_equivalent_to_directory_source(tmp_path):
    root_dir = _corpus(tmp_path / "dir", _MONTH_STANDING)
    root_zip = _corpus(tmp_path / "zip", _MONTH_STANDING)
    src_dir = tmp_path / "export"
    _build_standard_tree(src_dir)
    src_zip = tmp_path / "export.zip"
    _zip_tree(src_dir, src_zip)

    assert _run(root_dir, src_dir) == 0
    assert _run(root_zip, src_zip) == 0

    for stem, root in (("export", root_dir), ("export", root_zip)):
        capture = root / "capture"
        with zipfile.ZipFile(capture / f"{stem}-2025-11.zip") as z:
            assert z.namelist() == ["IMG_0001.HEIC", "IMG_0001.HEIC.json"]
        with zipfile.ZipFile(capture / f"{stem}-2026-01.zip") as z:
            assert z.namelist() == ["IMG_0002.HEIC", "IMG_0002.HEIC.json"]

    # The zip source's sidecar carries source_transport; the directory source's doesn't.
    zip_fields = _sidecar(root_zip / "capture" / "export-2025-11.zip")["origin_fields"]
    dir_fields = _sidecar(root_dir / "capture" / "export-2025-11.zip")["origin_fields"]
    assert "source_transport" in zip_fields
    assert "source_transport" not in dir_fields


# ---------- year-grain eras ---------- #


def test_year_era_bucket_alongside_month_buckets(tmp_path):
    root = _corpus(tmp_path, _YEAR_ERA)
    src = tmp_path / "export"
    src.mkdir()
    _mk_member(src, "old.HEIC", "2020-06-01T00:00:00", "2020-06-01T00:00:00-06:00")
    _mk_member(src, "IMG_0001.HEIC", "2025-11-01T00:00:00", "2025-11-01T00:00:00-06:00")
    _mk_member(src, "IMG_0003.HEIC", "2026-02-10T00:00:00", "2026-02-10T00:00:00-06:00")

    assert _run(root, src) == 0
    capture = root / "capture"
    assert (capture / "export-2020.zip").is_file()
    assert (capture / "export-2025-11.zip").is_file()
    assert (capture / "export-current-2026-02.zip").is_file()
    with zipfile.ZipFile(capture / "export-2020.zip") as z:
        assert z.namelist() == ["old.HEIC", "old.HEIC.json"]
    assert _sidecar(capture / "export-2020.zip")["origin_fields"]["period"] == "2020"


# ---------- determinism ---------- #


def test_determinism_two_runs_byte_identical(tmp_path):
    root_a = _corpus(tmp_path / "a", _MONTH_STANDING)
    root_b = _corpus(tmp_path / "b", _MONTH_STANDING)
    src_a = tmp_path / "export_a"
    _build_standard_tree(src_a)
    src_b = tmp_path / "export_b"
    _build_standard_tree(src_b)  # independently built, same names/mtimes/content

    assert _run(root_a, src_a) == 0
    assert _run(root_b, src_b) == 0

    for suffix in ("2025-11.zip", "2026-01.zip"):
        a_bytes = (root_a / "capture" / f"export_a-{suffix}").read_bytes()
        b_bytes = (root_b / "capture" / f"export_b-{suffix}").read_bytes()
        assert a_bytes == b_bytes


# ---------- CLI contract ---------- #


def test_origin_is_required():
    parser = argparse.ArgumentParser()
    period_split.configure(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["somepath", "--date-from", "mtime"])


def test_date_from_is_required():
    parser = argparse.ArgumentParser()
    period_split.configure(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["somepath", "--origin", "osxphotos-export"])


def test_no_schedule_declared_exits(tmp_path):
    root = _corpus(tmp_path, None)  # overlay exists but declares no partition
    src = tmp_path / "export"
    _build_standard_tree(src)
    with pytest.raises(SystemExit, match="partition schedule"):
        _run(root, src)


def test_refuse_to_overwrite(tmp_path):
    root = _corpus(tmp_path, _MONTH_STANDING)
    src = tmp_path / "export"
    _build_standard_tree(src)
    assert _run(root, src) == 0
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        _run(root, src)
