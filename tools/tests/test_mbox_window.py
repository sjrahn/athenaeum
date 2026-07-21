"""Mailbox window reduction — `corpus mbox-window` (spec §12.3.13): blake3-keyed dedup
against a lineage, transitive `window_against` expansion, the declared-embed fallback,
standalone rfc822 exclusion, raw-copy member identity, and the sidecar contract.

Fixture mailboxes are built in-test (CRLF mboxrd, one member carrying a `>From ` stuffed
body line so raw copy vs un-stuffed identity is exercised).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import blake3
import yaml

from corpus import hashing, mboxfile, paths, records, schemas
from corpus._cli import ingest as ingest_cli
from corpus._cli import mbox_window
from tests._draftlib import draft_for_test

CRLF = b"\r\n"


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _sep(sender: str, date: str) -> bytes:
    return f"From {sender} {date}".encode() + CRLF


def _msg(sender: str, subject: str, date: str, body: bytes) -> bytes:
    return (
        f"From: {sender}".encode() + CRLF
        + f"Subject: {subject}".encode() + CRLF
        + f"Date: {date}".encode() + CRLF
        + CRLF
        + body
    )


_M1 = _msg("a@x.com", "one", "Mon, 01 Jan 2024 00:00:00 +0000", b"body one" + CRLF)
_M2 = _msg("b@x.com", "two", "Tue, 02 Jan 2024 00:00:00 +0000", b"body two" + CRLF)
# Member whose body carries a stuffed line: raw copy must preserve the `>From `, while the
# member identity (blake3) is over the un-stuffed bytes.
_M3_RAW = _msg(
    "c@x.com", "three", "Wed, 03 Jan 2024 00:00:00 +0000",
    b">From here: stuffed line" + CRLF + b"tail" + CRLF,
)
_M3_MEMBER = _M3_RAW.replace(b">From here", b"From here", 1)
_M4 = _msg("d@x.com", "four", "Thu, 04 Jan 2024 00:00:00 +0000", b"body four" + CRLF)
_M5 = _msg("e@x.com", "five", "Fri, 05 Jan 2024 00:00:00 +0000", b"body five" + CRLF)
_M6 = _msg("f@x.com", "six", "Sat, 06 Jan 2024 00:00:00 +0000", b"body six" + CRLF)


def _mbox(tmp_path: Path, name: str, *raw_members: bytes) -> Path:
    out = b""
    for i, member in enumerate(raw_members, start=1):
        out += _sep(f"{i}@xxx", "Mon Jan 01 00:00:00 +0000 2024") + member
    p = tmp_path / name
    p.write_bytes(out)
    return p


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _ingest(root: Path, artifact: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    if staged != artifact:
        shutil.copy(artifact, staged)
        sidecar = artifact.with_suffix(artifact.suffix + ".capture.yaml")
        if sidecar.is_file():
            shutil.copy(sidecar, cap / sidecar.name)
    rid = hashing.hash_file(staged)["blake3"]
    assert ingest_cli._ingest_one(root, staged) == 0  # consumes staged file + sidecar
    return rid


def _run(root: Path, source: Path, *against: str, dry_run: bool = False) -> int:
    return mbox_window.run(
        argparse.Namespace(
            source=str(source),
            against=list(against),
            origin=None,
            dry_run=dry_run,
            corpus_root=str(root),
        )
    )


def _bundle_and_sidecar(root: Path) -> tuple[Path, dict]:
    bundles = sorted((root / "capture").glob("*-window-*.mbox"))
    assert len(bundles) == 1, bundles
    sidecar = bundles[0].with_suffix(bundles[0].suffix + ".capture.yaml")
    assert sidecar.is_file()
    return bundles[0], yaml.safe_load(sidecar.read_text())


def test_window_reduces_against_baseline_artifact(tmp_path):
    root = _corpus(tmp_path)
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _M1, _M2))

    # New export: m1 re-delivered, m3 (stuffed) + m4 new, m3 delivered twice.
    source = _mbox(tmp_path, "full.mbox", _M1, _M3_RAW, _M4, _M3_RAW)
    assert _run(root, source, baseline_id) == 0

    bundle, sidecar = _bundle_and_sidecar(root)
    # Window bounds from the new members' Date headers (Jan 03 / Jan 04).
    assert bundle.name == "full-window-20240103-20240104.mbox"

    scan = mboxfile.scan(bundle, None)
    assert scan.count == 2
    assert {f.blake3 for f in scan.facts.values()} == {_b3(_M3_MEMBER), _b3(_M4)}
    # Raw copy: the stuffed line survives in the bundle bytes; the member identity is
    # un-stuffed (resolve reproduces the true RFC822 bytes).
    assert b">From here" in bundle.read_bytes()
    assert mboxfile.resolve_member(bundle, 1) == _M3_MEMBER

    fields = sidecar["origin_fields"]
    assert fields["source_export"] == "full.mbox"
    assert fields["source_message_count"] == 4
    assert fields["window_count"] == 2
    assert fields["excluded_count"] == 1
    assert fields["duplicate_count"] == 1
    assert fields["window_against"] == [baseline_id]
    assert fields["window_start"].startswith("2024-01-03")
    assert fields["window_end"].startswith("2024-01-04")


def test_transitive_lineage_reaches_baseline(tmp_path):
    root = _corpus(tmp_path)
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _M1, _M2))

    # Window 1: m3 new against the baseline; ingest it (sidecar consumed → origin fields).
    src1 = _mbox(tmp_path, "exp1.mbox", _M1, _M3_RAW)
    assert _run(root, src1, baseline_id) == 0
    bundle1, _ = _bundle_and_sidecar(root)
    w1_id = _ingest(root, bundle1)  # ingest consumes the staged bundle + sidecar
    w1_post = records.load(paths.record_path(root, w1_id))
    assert any(
        (b.get("fields") or {}).get("window_against") == [baseline_id]
        for b in records.iter_origin_blocks(w1_post)
    )

    # Window 2 names ONLY window 1 — the baseline is reached transitively, so m1 (baseline)
    # and m3 (window 1) are both excluded and only m5 survives.
    src2 = _mbox(tmp_path, "exp2.mbox", _M1, _M3_RAW, _M5)
    assert _run(root, src2, w1_id) == 0
    bundle2, sidecar2 = _bundle_and_sidecar(root)
    scan = mboxfile.scan(bundle2, None)
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(_M5)
    assert sidecar2["origin_fields"]["window_against"] == [w1_id, baseline_id]


def test_declared_fallback_when_artifact_bytes_gone(tmp_path, capsys):
    root = _corpus(tmp_path)
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _M1, _M2))
    # Declare only m1, then retire the artifact bytes — the fallback exclusion is the
    # declared SUBSET, so m2 is re-admitted (and warned about).
    assert draft_for_test(root, baseline_id, messages="1") == 0
    (root / "artifacts" / baseline_id[:2] / f"{baseline_id}.mbox").unlink()

    source = _mbox(tmp_path, "full.mbox", _M1, _M2, _M6)
    assert _run(root, source, baseline_id) == 0
    bundle, sidecar = _bundle_and_sidecar(root)
    scan = mboxfile.scan(bundle, None)
    assert {f.blake3 for f in scan.facts.values()} == {_b3(_M2), _b3(_M6)}
    assert sidecar["origin_fields"]["excluded_count"] == 1
    assert "falling back" in capsys.readouterr().err


def test_standalone_rfc822_records_are_excluded(tmp_path):
    root = _corpus(tmp_path)
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _M1))
    # m2 exists only as a standalone message record (an independently-ingested .eml whose
    # bytes equal the would-be member bytes) — exclusion branch (iii).
    eml = tmp_path / "two.eml"
    eml.write_bytes(_M2)
    m2_id = _ingest(root, eml)
    assert m2_id == _b3(_M2)
    assert records.media_type_for(records.load(paths.record_path(root, m2_id))) == "message/rfc822"

    source = _mbox(tmp_path, "full.mbox", _M1, _M2, _M4)
    assert _run(root, source, baseline_id) == 0
    bundle, sidecar = _bundle_and_sidecar(root)
    scan = mboxfile.scan(bundle, None)
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(_M4)
    assert sidecar["origin_fields"]["excluded_count"] == 2


def test_empty_delta_emits_nothing(tmp_path, capsys):
    root = _corpus(tmp_path)
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _M1, _M2))
    source = _mbox(tmp_path, "full.mbox", _M1, _M2)
    assert _run(root, source, baseline_id) == 0
    assert not list((root / "capture").glob("*-window-*.mbox"))
    assert "empty delta" in capsys.readouterr().out


def test_dry_run_writes_nothing(tmp_path, capsys):
    root = _corpus(tmp_path)
    baseline_id = _ingest(root, _mbox(tmp_path, "baseline.mbox", _M1))
    source = _mbox(tmp_path, "full.mbox", _M1, _M4)
    assert _run(root, source, baseline_id, dry_run=True) == 0
    assert not list((root / "capture").glob("*-window-*.mbox"))
    assert "would write full-window-20240104-20240104.mbox" in capsys.readouterr().out
