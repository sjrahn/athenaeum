"""Month-grain temporal stratification — `partition:` schedules on origin overlays and
schedule-driven `corpus mbox-split` (spec §12.3.14): the resolution ladder (mirrors the
chrome strip's), pure-month splits, mixed-era splits (year-grain history alongside a
month-grain current era in ONE container), the undated `standing`/`rolling` policies, the
auto-stamped residue/undated sidecars, and determinism. The no-schedule fallback (byte-
identical to the pre-3.0 year-only split) is covered by the UNTOUCHED tests in
`test_mbox_split.py`.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import yaml

import corpus as corpus_pkg
from corpus import mboxfile, schemas
from corpus._cli import mbox_split

CRLF = b"\r\n"

_PACKAGED_MBOX_SCHEMA = (
    Path(corpus_pkg.__file__).parent
    / "schemas_default/mime/application/application_mbox.yaml"
)


def _sep(i: int) -> bytes:
    return f"From {i}@xxx Mon Jan 01 00:00:00 +0000 2024".encode() + CRLF


def _msg(subject: str, date: str | None) -> bytes:
    head = b"From: a@x.com" + CRLF
    head += f"Subject: {subject}".encode() + CRLF
    if date is not None:
        head += f"Date: {date}".encode() + CRLF
    return head + CRLF + b"body of " + subject.encode() + CRLF


def _mbox(tmp_path: Path, name: str, *raw_members: bytes) -> Path:
    out = b""
    for i, member in enumerate(raw_members, start=1):
        out += _sep(i) + member
    p = tmp_path / name
    p.write_bytes(out)
    return p


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _mime_shadow(root: Path, default_origin: str) -> None:
    local = root / "schema/mime/application/application_mbox.yaml"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(_PACKAGED_MBOX_SCHEMA.read_text() + f"\ndefault_origin: {default_origin}\n")
    schemas.cache_clear()


def _origin_overlay(root: Path, origin_id: str, extra_yaml: str) -> None:
    """Write an origin overlay at `origin/<id>.yaml` (nested namespace dirs created as
    needed) with arbitrary YAML body content (a `partition:` block, typically)."""
    path = root / "schema" / "origin" / f"{origin_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(extra_yaml)
    schemas.cache_clear()


def _run_split(root: Path, source: Path, **kwargs) -> int:
    defaults = dict(
        source=str(source),
        current_year=None,
        current_period=None,
        origin=None,
        strip=None,
        corpus_root=str(root),
    )
    defaults.update(kwargs)
    return mbox_split.run(argparse.Namespace(**defaults))


def _sidecar(path: Path) -> dict:
    return yaml.safe_load(path.with_suffix(path.suffix + ".capture.yaml").read_text())


# ---------- resolve_partition ladder (mirrors resolve_strip_headers's) ---------- #


def test_resolve_partition_subtype_overlay_wins_over_parent(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "google-takeout", "description: parent\npartition:\n  grain: year\n")
    _origin_overlay(
        root,
        "google-takeout/gmail",
        "description: subtype\npartition:\n  grain: month\n",
    )
    resolved = schemas.resolve_partition(root, "application/mbox", origin_id="google-takeout/gmail")
    assert resolved == {"grain": "month"}


def test_resolve_partition_walks_to_parent_when_subtype_silent(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "google-takeout", "description: parent\npartition:\n  grain: year\n")
    # No file at all for the "gmail" subtype — the walk climbs to the parent.
    resolved = schemas.resolve_partition(root, "application/mbox", origin_id="google-takeout/gmail")
    assert resolved == {"grain": "year"}


def test_resolve_partition_falls_back_to_default_origin_binding(tmp_path):
    root = _corpus(tmp_path)
    _mime_shadow(root, "google-takeout/gmail")
    _origin_overlay(
        root, "google-takeout/gmail", "description: subtype\npartition:\n  grain: month\n"
    )
    # No origin_id given at all → resolves via the mime schema's default_origin binding.
    assert schemas.resolve_partition(root, "application/mbox") == {"grain": "month"}


def test_resolve_partition_none_when_nothing_declares(tmp_path):
    root = _corpus(tmp_path)
    assert schemas.resolve_partition(root, "application/mbox") is None
    assert schemas.resolve_partition(root, "application/mbox", origin_id="nothing-here") is None


def test_resolve_partition_stamped_origin_never_falls_to_default_binding(tmp_path):
    """Finality, mirroring the strip: a stamped origin id with no declaration on ITS OWN
    walk never falls through to the corpus's `default_origin` binding, even when that
    binding declares a partition."""
    root = _corpus(tmp_path)
    _mime_shadow(root, "google-takeout/gmail")
    _origin_overlay(
        root, "google-takeout/gmail", "description: subtype\npartition:\n  grain: month\n"
    )
    assert schemas.resolve_partition(root, "application/mbox", origin_id="imessage-export") is None


def test_resolve_partition_invalid_grain_ignored_walk_continues(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(root, "google-takeout", "description: parent\npartition:\n  grain: year\n")
    _origin_overlay(
        root,
        "google-takeout/gmail",
        "description: subtype\npartition:\n  grain: fortnight\n",  # invalid
    )
    resolved = schemas.resolve_partition(root, "application/mbox", origin_id="google-takeout/gmail")
    assert resolved == {"grain": "year"}  # invalid subtype block skipped, parent wins


# ---------- mbox-split: schedule-driven bucketing ---------- #


def test_pure_month_split_closed_months_and_current_residue(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(
        root,
        "mailstream",
        "description: mailstream\npartition:\n  grain: month\n  undated: rolling\n",
    )
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("nov", "Sat, 01 Nov 2025 10:00:00 +0000"),
        _msg("dec", "Mon, 01 Dec 2025 10:00:00 +0000"),
        _msg("jan", "Thu, 01 Jan 2026 10:00:00 +0000"),
        _msg("feb-current", "Sun, 01 Feb 2026 10:00:00 +0000"),
    )
    assert (
        _run_split(
            root, source, origin="mailstream", current_year=2026, current_period="2026-02"
        )
        == 0
    )

    container = root / "capture" / "full-periods-2025-11-2026-01.zip"
    residue = root / "capture" / "full-current-2026-02.mbox"
    assert container.is_file() and residue.is_file()

    with zipfile.ZipFile(container) as z:
        assert z.namelist() == ["2025-11.mbox", "2025-12.mbox", "2026-01.mbox"]

    scan_res = mboxfile.scan(residue, None)
    assert scan_res.count == 1

    sidecar = _sidecar(container)
    fields = sidecar["origin_fields"]
    assert fields["split_by"] == "period"
    assert fields["periods"] == {"2025-11": 1, "2025-12": 1, "2026-01": 1}
    assert fields["periods_start"] == "2025-11"
    assert fields["periods_end"] == "2026-01"
    assert "years" not in fields  # no year-grain buckets in a pure-month split

    residue_sidecar = _sidecar(residue)
    assert residue_sidecar["origin_fields"]["period"] == "2026-02"
    assert residue_sidecar["origin_schema"] == "mailstream"


def test_mixed_era_split_year_history_and_month_current_in_one_container(tmp_path):
    """One export spans a year-grain historical era AND the month-grain current era —
    ONE container holds both `2005.mbox` (year) and `2026-01.mbox` (month); `years*`
    keys sit alongside `periods*` in the sidecar."""
    root = _corpus(tmp_path)
    _origin_overlay(
        root,
        "mailstream",
        "description: mailstream\n"
        "partition:\n"
        "  grain: month\n"
        "  eras:\n"
        "  - until: 2025\n"
        "    grain: year\n"
        "  undated: rolling\n",
    )
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("old", "Tue, 01 Mar 2005 10:00:00 +0000"),
        _msg("boundary", "Wed, 01 Jan 2025 10:00:00 +0000"),
        _msg("jan26", "Thu, 01 Jan 2026 10:00:00 +0000"),
        _msg("feb26-current", "Sun, 01 Feb 2026 10:00:00 +0000"),
    )
    assert (
        _run_split(
            root, source, origin="mailstream", current_year=2027, current_period="2026-02"
        )
        == 0
    )

    container = root / "capture" / "full-periods-2005-2026-01.zip"
    residue = root / "capture" / "full-current-2026-02.mbox"
    assert container.is_file() and residue.is_file()

    with zipfile.ZipFile(container) as z:
        assert z.namelist() == ["2005.mbox", "2025.mbox", "2026-01.mbox"]

    fields = _sidecar(container)["origin_fields"]
    assert fields["periods"] == {"2005": 1, "2025": 1, "2026-01": 1}
    assert fields["periods_start"] == "2005"
    assert fields["periods_end"] == "2026-01"
    assert fields["years"] == {"2005": 1, "2025": 1}
    assert fields["years_start"] == "2005"
    assert fields["years_end"] == "2025"


# ---------- the UTC boundary rule (v34, spec §12.3.14) ---------- #


def test_boundary_offset_dates_bucket_by_utc_not_face_value(tmp_path):
    """A message dated in the FIRST hours of a month at a positive offset crosses BACK
    to the previous month in UTC; one dated in the LAST hours at a negative offset
    crosses FORWARD to the next month — the v34 UTC boundary rule (spec §12.3.14), not
    face-value reading of the Date: header's local calendar date. An unparseable Date:
    still falls through to undated, unaffected by the rule."""
    root = _corpus(tmp_path)
    _origin_overlay(
        root,
        "mailstream",
        "description: mailstream\npartition:\n  grain: month\n  undated: standing\n",
    )
    source = _mbox(
        tmp_path,
        "full.mbox",
        # Face value: Feb 1, 02:00. UTC (-6h): Jan 31, 20:00 -> previous month.
        _msg("early-plus6", "Sun, 01 Feb 2026 02:00:00 +0600"),
        # Face value: Jun 30, 20:00. UTC (+8h): Jul 1, 04:00 -> next month.
        _msg("late-minus8", "Tue, 30 Jun 2026 20:00:00 -0800"),
        _msg("garbage-date", "not a date at all"),
    )
    assert (
        _run_split(
            root, source, origin="mailstream", current_year=2026, current_period="2026-08"
        )
        == 0
    )

    container = root / "capture" / "full-periods-2026-01-2026-07.zip"
    assert container.is_file()
    with zipfile.ZipFile(container) as z:
        assert z.namelist() == ["2026-01.mbox", "2026-07.mbox"]

    fields = _sidecar(container)["origin_fields"]
    assert fields["periods"] == {"2026-01": 1, "2026-07": 1}

    undated_bundle = root / "capture" / "full-undated.mbox"
    assert undated_bundle.is_file()
    assert mboxfile.scan(undated_bundle, None).count == 1


def test_undated_standing_bucket_emitted_and_excluded_from_residue(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(
        root,
        "mailstream",
        "description: mailstream\npartition:\n  grain: month\n  undated: standing\n",
    )
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("jan", "Thu, 01 Jan 2026 10:00:00 +0000"),
        _msg("no-date", None),
    )
    assert (
        _run_split(
            root, source, origin="mailstream", current_year=2026, current_period="2026-02"
        )
        == 0
    )

    undated_bundle = root / "capture" / "full-undated.mbox"
    residue = root / "capture" / "full-current-2026-02.mbox"
    assert undated_bundle.is_file()
    assert mboxfile.scan(undated_bundle, None).count == 1
    # The residue holds ONLY current-period members — undated never rides it here.
    assert mboxfile.scan(residue, None).count == 0

    undated_sidecar = _sidecar(undated_bundle)
    assert "period" not in undated_sidecar["origin_fields"]  # never a period-driven title
    assert undated_sidecar["origin_schema"] == "mailstream"


def test_undated_rolling_rides_residue(tmp_path):
    root = _corpus(tmp_path)
    _origin_overlay(
        root,
        "mailstream",
        "description: mailstream\npartition:\n  grain: month\n  undated: rolling\n",
    )
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("jan", "Thu, 01 Jan 2026 10:00:00 +0000"),
        _msg("no-date", None),
    )
    assert (
        _run_split(
            root, source, origin="mailstream", current_year=2026, current_period="2026-02"
        )
        == 0
    )
    assert not (root / "capture" / "full-undated.mbox").exists()
    residue = root / "capture" / "full-current-2026-02.mbox"
    assert mboxfile.scan(residue, None).count == 1  # the undated member rode the residue


def test_sidecars_auto_stamp_origin_schema_from_default_binding(tmp_path):
    """Residue and (standing) undated sidecars both auto-stamp `origin_schema` from the
    `default_origin` binding when `--origin` is omitted — same as the container's."""
    root = _corpus(tmp_path)
    _mime_shadow(root, "mailstream")
    _origin_overlay(
        root,
        "mailstream",
        "description: mailstream\npartition:\n  grain: month\n  undated: standing\n",
    )
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("jan", "Thu, 01 Jan 2026 10:00:00 +0000"),
        _msg("no-date", None),
    )
    assert _run_split(root, source, current_year=2026, current_period="2026-02") == 0

    container = root / "capture" / "full-periods-2026-01-2026-01.zip"
    residue = root / "capture" / "full-current-2026-02.mbox"
    undated_bundle = root / "capture" / "full-undated.mbox"
    assert _sidecar(container)["origin_schema"] == "mailstream"
    assert _sidecar(residue)["origin_schema"] == "mailstream"
    assert _sidecar(undated_bundle)["origin_schema"] == "mailstream"


def test_split_is_deterministic_under_month_grain(tmp_path):
    root_a = _corpus(tmp_path / "a")
    root_b = _corpus(tmp_path / "b")
    for root in (root_a, root_b):
        _origin_overlay(
            root,
            "mailstream",
            "description: mailstream\npartition:\n  grain: month\n  undated: rolling\n",
        )
    src_a = _mbox(
        tmp_path,
        "one.mbox",
        _msg("nov", "Sat, 01 Nov 2025 10:00:00 +0000"),
        _msg("jan", "Thu, 01 Jan 2026 10:00:00 +0000"),
    )
    import shutil

    src_b = tmp_path / "two" / "one.mbox"
    src_b.parent.mkdir()
    shutil.copy(src_a, src_b)
    shutil.copystat(src_a, src_b)
    assert (
        _run_split(
            root_a, src_a, origin="mailstream", current_year=2026, current_period="2026-02"
        )
        == 0
    )
    assert (
        _run_split(
            root_b, src_b, origin="mailstream", current_year=2026, current_period="2026-02"
        )
        == 0
    )
    za = (root_a / "capture/one-periods-2025-11-2026-01.zip").read_bytes()
    zb = (root_b / "capture/one-periods-2025-11-2026-01.zip").read_bytes()
    assert za == zb
