"""corpus export-diff (spec §12.3.14 onboarding gate): the mbox member-grain churn
histogram + the directory/zip file-grain structural diff, and the shared reconciliation
math that turns either into a full-strata-candidate vs member-dedup-only verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from corpus._cli import export_diff

CRLF = b"\r\n"


def _sep(sender: str, date: str) -> bytes:
    return f"From {sender} {date}".encode() + CRLF


def _msg(
    message_id: str,
    sender: str,
    subject: str,
    date: str,
    body: bytes,
    extra: str = "",
) -> bytes:
    headers = (
        f"Message-ID: {message_id}".encode() + CRLF
        + f"From: {sender}".encode() + CRLF
        + f"Subject: {subject}".encode() + CRLF
        + f"Date: {date}".encode() + CRLF
    )
    if extra:
        headers += extra.encode() + CRLF
    return headers + CRLF + body


def _mbox(tmp_path: Path, name: str, *raw_members: bytes) -> Path:
    out = b""
    for i, member in enumerate(raw_members, start=1):
        out += _sep(f"{i}@xxx", "Mon Jan 01 00:00:00 +0000 2024") + member
    p = tmp_path / name
    p.write_bytes(out)
    return p


def _run(a: Path, b: Path, *, json_out: Path | None = None) -> int:
    return export_diff.run(
        argparse.Namespace(a=str(a), b=str(b), json_out=str(json_out) if json_out else None)
    )


# ---------- mbox pair ---------- #

_M1 = _msg("<m1@x>", "a@x.com", "one", "Mon, 01 Jan 2024 00:00:00 +0000", b"body one" + CRLF)
_M2_A = _msg(
    "<m2@x>", "b@x.com", "two", "Tue, 02 Jan 2024 00:00:00 +0000",
    b"body two" + CRLF, extra="X-Gmail-Labels: Inbox",
)
_M2_B = _msg(
    "<m2@x>", "b@x.com", "two", "Tue, 02 Jan 2024 00:00:00 +0000",
    b"body two" + CRLF, extra="X-Gmail-Labels: Inbox,Important",
)
_M4_ARRIVAL = _msg(
    "<m4@x>", "d@x.com", "four", "Thu, 04 Jan 2024 00:00:00 +0000", b"body four" + CRLF
)


def test_mbox_pair_histogram_and_modulo_identity(tmp_path):
    a = _mbox(tmp_path, "a.mbox", _M1, _M2_A)
    b = _mbox(tmp_path, "b.mbox", _M1, _M2_B, _M4_ARRIVAL)

    report = export_diff.build_report(a, b)
    assert report["mode"] == "mbox"
    assert report["identical"] == 1  # M1
    assert report["only_a"] == 1  # M2's A-copy
    assert report["only_b"] == 2  # M2's B-copy + the new arrival M4
    assert report["matched_pairs"] == 1  # M2 paired via Message-ID
    assert report["content_divergent"] == 0
    assert report["chrome_eligible"] == 1
    assert report["unmatched_only_a"] == 0
    assert report["unmatched_only_b"] == 1  # M4 — genuinely new, no counterpart

    assert report["histogram"] == [("x-gmail-labels", 1)]

    verdict = report["verdict"]
    assert verdict["kind"] == "full_strata_candidate"
    assert verdict["modulo"] == ["x-gmail-labels"]
    assert verdict["stable"] == 2  # 1 identical + 1 reconciled
    assert verdict["total"] == 2  # identical + matched_pairs
    assert verdict["pct"] == 100.0


def test_mbox_body_divergent_pair_is_content_divergent_not_chrome(tmp_path):
    m2_diff_body = _msg(
        "<m2@x>", "b@x.com", "two", "Tue, 02 Jan 2024 00:00:00 +0000",
        b"body TWO CHANGED" + CRLF, extra="X-Gmail-Labels: Inbox",
    )
    a = _mbox(tmp_path, "a.mbox", _M1, _M2_A)
    b = _mbox(tmp_path, "b.mbox", _M1, m2_diff_body)

    report = export_diff.build_report(a, b)
    assert report["matched_pairs"] == 1
    assert report["content_divergent"] == 1
    assert report["chrome_eligible"] == 0
    # No chrome-eligible pair at all and a content-divergent one exists: never "clean".
    assert report["verdict"]["kind"] == "member_dedup_only"


def test_mbox_cli_run_prints_verdict_line(tmp_path, capsys):
    a = _mbox(tmp_path, "a.mbox", _M1, _M2_A)
    b = _mbox(tmp_path, "b.mbox", _M1, _M2_B)
    assert _run(a, b) == 0
    out = capsys.readouterr().out
    assert "VERDICT: deterministic modulo <x-gmail-labels>: 2/2 (100.0%)" in out
    assert "FULL STRATA CANDIDATE" in out


def test_mbox_json_output_written(tmp_path):
    a = _mbox(tmp_path, "a.mbox", _M1, _M2_A)
    b = _mbox(tmp_path, "b.mbox", _M1, _M2_B)
    out_path = tmp_path / "report.json"
    assert _run(a, b, json_out=out_path) == 0
    loaded = json.loads(out_path.read_text())
    assert loaded["mode"] == "mbox"
    assert loaded["verdict"]["kind"] == "full_strata_candidate"


# ---------- directory / zip pair ---------- #


def _write_tree(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def _zip_dir(src: Path, zip_path: Path) -> Path:
    """Zip `src`, each entry's `ZipInfo.date_time` set from the source file's mtime
    CONVERTED TO UTC (matching `corpus period-split`'s own `_DirSource.mtime` and
    `export_diff`'s `_dir_mtime` — both explicit-UTC) rather than `ZipFile.write()`'s
    default (the LOCAL system timezone via `ZipInfo.from_file`), which would make this
    fixture's zip-vs-directory comparison spuriously timezone-dependent."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                dt = datetime.fromtimestamp(p.stat().st_mtime, UTC)
                zi = zipfile.ZipInfo(
                    p.relative_to(src).as_posix(),
                    date_time=(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second),
                )
                zf.writestr(zi, p.read_bytes())
    return zip_path


def test_directory_pair_json_field_churn(tmp_path):
    common_json_a = json.dumps({"exportedAt": "2026-07-01T00:00:00Z", "value": 1}).encode()
    common_json_b = json.dumps({"exportedAt": "2026-07-02T08:30:00Z", "value": 1}).encode()
    a = _write_tree(
        tmp_path / "a",
        {
            "records/one.json": common_json_a,
            "records/same.json": b'{"k": "v"}',
        },
    )
    b = _write_tree(
        tmp_path / "b",
        {
            "records/one.json": common_json_b,
            "records/same.json": b'{"k": "v"}',
        },
    )

    report = export_diff.build_report(a, b)
    assert report["mode"] == "tree"
    assert report["identical"] == 1  # records/same.json
    assert report["only_a"] == 0
    assert report["only_b"] == 0
    assert report["matched_pairs"] == 1  # records/one.json differs
    assert report["chrome_eligible"] == 1
    assert report["content_divergent"] == 0
    assert report["histogram"] == [("exportedAt", 1)]

    verdict = report["verdict"]
    assert verdict["kind"] == "full_strata_candidate"
    assert verdict["modulo"] == ["exportedAt"]
    assert verdict["stable"] == 2
    assert verdict["total"] == 2


def test_directory_pair_only_a_only_b_accounting(tmp_path):
    a = _write_tree(tmp_path / "a", {"only_in_a.json": b'{"x": 1}', "shared.json": b'{"k": 1}'})
    b = _write_tree(tmp_path / "b", {"only_in_b.json": b'{"y": 2}', "shared.json": b'{"k": 1}'})

    report = export_diff.build_report(a, b)
    assert report["identical"] == 1
    assert report["only_a"] == 1
    assert report["only_b"] == 1
    assert report["matched_pairs"] == 0


def test_directory_pair_non_json_divergent_file_reported_as_such(tmp_path):
    a = _write_tree(tmp_path / "a", {"photo.bin": b"\x00\x01\x02binary-a"})
    b = _write_tree(tmp_path / "b", {"photo.bin": b"\x00\x01\x02binary-B-DIFFERENT"})

    report = export_diff.build_report(a, b)
    assert report["matched_pairs"] == 1
    assert report["content_divergent"] == 1
    assert report["chrome_eligible"] == 0
    assert report["histogram"] == []
    # A byte-divergent, non-JSON file is never chrome — no reconciliation candidate found.
    assert report["verdict"]["kind"] == "member_dedup_only"


def test_zip_vs_directory_equivalence(tmp_path):
    files = {
        "a.json": json.dumps({"exportedAt": "2026-01-01", "v": 1}).encode(),
        "b.json": b'{"same": true}',
    }
    dir_a = _write_tree(tmp_path / "dir_a", files)
    dir_b = _write_tree(
        tmp_path / "dir_b",
        {
            "a.json": json.dumps({"exportedAt": "2026-01-02", "v": 1}).encode(),
            "b.json": b'{"same": true}',
        },
    )
    zip_b = _zip_dir(dir_b, tmp_path / "b.zip")

    report_dir = export_diff.build_report(dir_a, dir_b)
    report_zip = export_diff.build_report(dir_a, zip_b)

    for key in ("mode", "identical", "only_a", "only_b", "matched_pairs", "histogram"):
        assert report_dir[key] == report_zip[key], key
    assert report_zip["verdict"]["kind"] == report_dir["verdict"]["kind"]


def test_mismatched_shapes_exit(tmp_path):
    mbox_path = _mbox(tmp_path, "a.mbox", _M1)
    dir_path = _write_tree(tmp_path / "b", {"f.json": b"{}"})
    with pytest.raises(SystemExit, match="mismatched export shapes"):
        export_diff.build_report(mbox_path, dir_path)


# ---------- v36 follow-up: the mtime axis (tree mode only) ---------- #


def _touch(p: Path, iso: str) -> None:
    ts = datetime.fromisoformat(iso).timestamp()
    os.utime(p, (ts, ts))


def test_mtime_drift_downgrades_a_full_strata_verdict(tmp_path):
    """Byte-identical members whose mtimes were RESTAMPED between exports must never
    read as an unqualified FULL STRATA CANDIDATE — the container-identity axis
    (`corpus period-split`'s per-member `ZipInfo.date_time`) would never re-encounter."""
    a = _write_tree(tmp_path / "a", {"msg1.eml": b"same-bytes", "msg2.eml": b"same-bytes-2"})
    b = _write_tree(tmp_path / "b", {"msg1.eml": b"same-bytes", "msg2.eml": b"same-bytes-2"})
    _touch(a / "msg1.eml", "2025-11-01T10:00:00+00:00")
    _touch(b / "msg1.eml", "2025-11-01T10:00:00+00:00")  # same mtime — no drift
    _touch(a / "msg2.eml", "2025-11-01T10:00:00+00:00")
    _touch(b / "msg2.eml", "2025-12-15T09:00:00+00:00")  # restamped on re-export

    report = export_diff.build_report(a, b)
    assert report["mode"] == "tree"
    assert report["identical"] == 2  # both members are byte-identical
    assert report["mtime_checked"] == 2
    assert report["mtime_drifted"] == 1
    assert report["mtime_drifted_sample"] == ["msg2.eml"]

    verdict = report["verdict"]
    assert verdict["kind"] == "clean_mtime_unstable"  # byte-clean, but mtime-unstable
    assert "1/2" in verdict["text"]
    assert "period-split" in verdict["text"]
    assert "NOT SUPPORTED" in verdict["text"]
    # The byte-axis numbers themselves stay honest and unqualified.
    assert verdict["stable"] == 2 and verdict["total"] == 2 and verdict["pct"] == 100.0

    rendered = export_diff.render_report(report)
    assert "mtime axis: 1/2" in rendered
    assert "msg2.eml" in rendered


def test_mtime_stable_pair_confirms_the_axis_was_measured(tmp_path):
    a = _write_tree(tmp_path / "a", {"msg1.eml": b"same-bytes"})
    b = _write_tree(tmp_path / "b", {"msg1.eml": b"same-bytes"})
    _touch(a / "msg1.eml", "2025-11-01T10:00:00+00:00")
    _touch(b / "msg1.eml", "2025-11-01T10:00:00+00:00")

    report = export_diff.build_report(a, b)
    assert report["mtime_checked"] == 1
    assert report["mtime_drifted"] == 0
    assert report["mtime_drifted_sample"] == []
    assert report["verdict"]["kind"] == "clean"  # NOT downgraded — nothing drifted

    rendered = export_diff.render_report(report)
    assert "mtime axis: 0/1" in rendered
    assert "measured clean" in rendered


def test_mtime_drift_on_full_strata_candidate_downgrades_that_kind_too(tmp_path):
    """The full_strata_candidate (modulo-some-churn) verdict, not just the clean one, must
    also carry the mtime qualification — a mixed byte-churn + mtime-drift export."""
    a = _write_tree(
        tmp_path / "a",
        {
            "one.json": json.dumps({"exportedAt": "2026-01-01", "v": 1}).encode(),
            "stable.json": b'{"k": "v"}',
        },
    )
    b = _write_tree(
        tmp_path / "b",
        {
            "one.json": json.dumps({"exportedAt": "2026-01-02", "v": 1}).encode(),
            "stable.json": b'{"k": "v"}',
        },
    )
    _touch(a / "stable.json", "2025-11-01T10:00:00+00:00")
    _touch(b / "stable.json", "2025-11-05T10:00:00+00:00")  # the byte-identical one drifts

    report = export_diff.build_report(a, b)
    # one.json is chrome-eligible (churns on exportedAt), never counted on the mtime axis —
    # only stable.json (byte-identical) is checked.
    assert report["mtime_checked"] == 1
    assert report["mtime_drifted"] == 1
    assert report["verdict"]["kind"] == "full_strata_candidate_mtime_unstable"
    assert "NOT SUPPORTED" in report["verdict"]["text"]
    # The byte-axis reconciliation numbers are untouched by the mtime qualification.
    assert report["verdict"]["modulo"] == ["exportedAt"]
