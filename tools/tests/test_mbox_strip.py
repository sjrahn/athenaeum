"""Mailbox chrome strip (spec §12.3.13): the HeaderStrip filter (folded continuations,
header-zone-only, case-insensitive), scan/extract with strip, the `corpus mbox-strip`
verb, and `corpus mbox-window --strip` crossing a pre-strip (label-full) lineage.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import blake3
import yaml

from corpus import hashing, mboxfile, schemas
from corpus._cli import ingest as ingest_cli
from corpus._cli import mbox_strip, mbox_window

CRLF = b"\r\n"

STRIP = mboxfile.normalize_strip_headers(["X-Gmail-Labels"])


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _sep(i: int) -> bytes:
    return f"From {i}@xxx Mon Jan 01 00:00:00 +0000 2024".encode() + CRLF


def _msg(subject: str, labels: str | None, body: bytes = b"body" + CRLF) -> bytes:
    head = b"From: a@x.com" + CRLF
    if labels is not None:
        head += b"X-Gmail-Labels: " + labels.encode() + CRLF
    head += f"Subject: {subject}".encode() + CRLF
    head += b"Date: Mon, 01 Jan 2024 00:00:00 +0000" + CRLF
    return head + CRLF + body


def _mbox(tmp_path: Path, name: str, *raw_members: bytes) -> Path:
    out = b""
    for i, member in enumerate(raw_members, start=1):
        out += _sep(i) + member
    p = tmp_path / name
    p.write_bytes(out)
    return p


def _stripped(member: bytes) -> bytes:
    """The member with its single-line X-Gmail-Labels header removed (fixture-shaped)."""
    lines = member.split(CRLF)
    return CRLF.join(ln for ln in lines if not ln.startswith(b"X-Gmail-Labels:"))


# ---------- the filter ---------- #


def test_strip_removes_header_and_folded_continuation():
    s = mboxfile.HeaderStrip(STRIP)
    assert s.keep(b"From: a@x.com" + CRLF)
    assert not s.keep(b"X-Gmail-Labels: Inbox," + CRLF)
    assert not s.keep(b" Category Updates,Unread" + CRLF)  # folded continuation goes too
    assert s.keep(b"Subject: hi" + CRLF)
    assert s.dropped == 2


def test_strip_is_case_insensitive_and_header_zone_only():
    s = mboxfile.HeaderStrip(STRIP)
    assert not s.keep(b"x-gmail-labels: Archived" + CRLF)
    assert s.keep(CRLF)  # blank line ends the header zone
    assert s.keep(b"X-Gmail-Labels: in a body line, untouched" + CRLF)
    assert s.dropped == 1


def test_scan_hashes_as_if_stripped():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        labelled = _msg("one", "Inbox,Category Updates,Unread")
        bare = _msg("two", None)
        p = _mbox(Path(d), "m.mbox", labelled, bare)
        scan = mboxfile.scan(p, None, strip=STRIP)
        assert scan.facts[1].blake3 == _b3(_stripped(labelled))
        assert scan.facts[2].blake3 == _b3(bare)
        assert scan.stripped_members == 1


def test_extract_emits_stripped_members(tmp_path):
    labelled = _msg("one", "Archived,Opened")
    p = _mbox(tmp_path, "m.mbox", labelled)
    out = tmp_path / "out.mbox"
    with out.open("wb") as fh:
        assert mboxfile.extract_raw_members(p, {1}, fh, strip=STRIP) == 1
    data = out.read_bytes()
    assert b"X-Gmail-Labels" not in data
    # The emitted bundle re-scans (no strip needed) to the stripped identity.
    rescan = mboxfile.scan(out, None)
    assert rescan.facts[1].blake3 == _b3(_stripped(labelled))


# ---------- the verbs ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
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
    assert ingest_cli._ingest_one(root, staged) == 0
    return rid


def test_mbox_strip_verb_roundtrip(tmp_path):
    root = _corpus(tmp_path)
    m1 = _msg("one", "Inbox,Category Updates,Unread")
    m2 = _msg("two", None)
    source = _mbox(tmp_path, "full.mbox", m1, m2)

    assert (
        mbox_strip.run(
            argparse.Namespace(
                source=str(source),
                strip=["X-Gmail-Labels"],
                origin=None,
                corpus_root=str(root),
            )
        )
        == 0
    )
    out = root / "capture" / "full-stripped.mbox"
    assert out.is_file()
    scan = mboxfile.scan(out, None)
    assert scan.count == 2
    assert {f.blake3 for f in scan.facts.values()} == {_b3(_stripped(m1)), _b3(m2)}

    sidecar = yaml.safe_load(out.with_suffix(out.suffix + ".capture.yaml").read_text())
    fields = sidecar["origin_fields"]
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]
    assert fields["stripped_members"] == 1
    assert fields["source_export"] == "full.mbox"
    assert fields["source_message_count"] == 2


def test_window_strip_crosses_prestrip_lineage(tmp_path):
    """A label-full baseline serves as lineage for a stripped window: the same message
    re-exported with DIFFERENT labels is excluded (identity modulo the stripped header),
    and the emitted delta member is label-free."""
    root = _corpus(tmp_path)
    baseline_id = _ingest(
        root,
        _mbox(
            tmp_path,
            "baseline.mbox",
            _msg("one", "Inbox,Category Updates,Unread"),
            _msg("two", "Inbox"),
        ),
    )
    # New export: same two messages, labels churned by a de-labelling sweep + one new.
    new_msg = _msg("three", "Archived")
    source = _mbox(
        tmp_path,
        "full.mbox",
        _msg("one", "Archived,Opened,Category Personal"),
        _msg("two", "Archived,Opened"),
        new_msg,
    )
    assert (
        mbox_window.run(
            argparse.Namespace(
                source=str(source),
                against=[baseline_id],
                origin=None,
                strip=["X-Gmail-Labels"],
                dry_run=False,
                corpus_root=str(root),
            )
        )
        == 0
    )
    bundles = sorted((root / "capture").glob("*-window-*.mbox"))
    assert len(bundles) == 1
    scan = mboxfile.scan(bundles[0], None)
    assert scan.count == 1
    assert scan.facts[1].blake3 == _b3(_stripped(new_msg))
    assert b"X-Gmail-Labels" not in bundles[0].read_bytes()

    sidecar = yaml.safe_load(
        bundles[0].with_suffix(bundles[0].suffix + ".capture.yaml").read_text()
    )
    fields = sidecar["origin_fields"]
    assert fields["excluded_count"] == 2
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]


def test_window_without_strip_readmits_label_churn(tmp_path):
    """The negative control: same fixture WITHOUT --strip re-admits both churned members."""
    root = _corpus(tmp_path)
    baseline_id = _ingest(
        root, _mbox(tmp_path, "baseline.mbox", _msg("one", "Inbox,Unread"), _msg("two", "Inbox"))
    )
    source = _mbox(
        tmp_path, "full.mbox", _msg("one", "Archived,Opened"), _msg("two", "Archived,Opened")
    )
    assert (
        mbox_window.run(
            argparse.Namespace(
                source=str(source),
                against=[baseline_id],
                origin=None,
                strip=None,
                dry_run=False,
                corpus_root=str(root),
            )
        )
        == 0
    )
    bundles = sorted((root / "capture").glob("*-window-*.mbox"))
    assert len(bundles) == 1
    assert mboxfile.scan(bundles[0], None).count == 2  # label churn re-admitted everything
