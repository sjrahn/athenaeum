"""corpus export-diff (spec §12.3.14 onboarding gate): the mbox member-grain churn
histogram + the directory/zip file-grain structural diff, and the shared reconciliation
math that turns either into a full-strata-candidate vs member-dedup-only verdict.
"""

from __future__ import annotations

import argparse
import json
import zipfile
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
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src).as_posix())
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
