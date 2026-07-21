"""Mailbox chrome strip (spec §12.3.13), config-driven: the HeaderStrip filter (folded
continuations, header-zone-only, case-insensitive), schema-declared auto-strip at ingest
(identity over stripped bytes + delivered-hash provenance), and `corpus mbox-window`
resolving the same declaration — including a pre-strip (label-full) lineage crossed
as-if-stripped, and the no-declaration negative control.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import blake3
import yaml

import corpus as corpus_pkg
from corpus import hashing, mboxfile, records, schemas
from corpus._cli import ingest as ingest_cli
from corpus._cli import mbox_window

CRLF = b"\r\n"

STRIP = mboxfile.normalize_strip_headers(["X-Gmail-Labels"])

_PACKAGED_MBOX_SCHEMA = (
    Path(corpus_pkg.__file__).parent
    / "schemas_default/mime/application/application_mbox.yaml"
)


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


def _corpus(tmp_path: Path, declare_strip: bool = False) -> Path:
    """A test corpus; with `declare_strip`, a corpus-local shadow of the packaged
    application/mbox schema declares `strip_headers: [X-Gmail-Labels]` — the whole-file-
    wins rung rule (§3) means the shadow must carry the full packaged content."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    if declare_strip:
        local = root / "schema/mime/application/application_mbox.yaml"
        local.parent.mkdir(parents=True)
        local.write_text(
            _PACKAGED_MBOX_SCHEMA.read_text()
            + "\nstrip_headers:\n- X-Gmail-Labels\n"
        )
    schemas.cache_clear()
    return root


def _ingest(root: Path, artifact: Path) -> str:
    """Stage + ingest; returns the RESULTING record id (post-canonicalization)."""
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / artifact.name
    if staged != artifact:
        shutil.copy(artifact, staged)
        sidecar = artifact.with_suffix(artifact.suffix + ".capture.yaml")
        if sidecar.is_file():
            shutil.copy(sidecar, cap / sidecar.name)
    assert ingest_cli._ingest_one(root, staged) == 0
    recs = sorted((root / "records").rglob("*.md"))
    by_mtime = max(recs, key=lambda p: p.stat().st_mtime)
    return by_mtime.stem


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


def test_scan_hashes_as_if_stripped(tmp_path):
    labelled = _msg("one", "Inbox,Category Updates,Unread")
    bare = _msg("two", None)
    p = _mbox(tmp_path, "m.mbox", labelled, bare)
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
    rescan = mboxfile.scan(out, None)
    assert rescan.facts[1].blake3 == _b3(_stripped(labelled))


# ---------- schema resolution ---------- #


def test_resolve_strip_headers_precedence(tmp_path):
    declared = _corpus(tmp_path / "a", declare_strip=True)
    assert schemas.resolve_strip_headers(declared, "application/mbox") == ["X-Gmail-Labels"]
    assert schemas.resolve_strip_headers(declared, "application/mbox", ["X-Other"]) == ["X-Other"]
    bare = _corpus(tmp_path / "b")
    assert schemas.resolve_strip_headers(bare, "application/mbox") == []


# ---------- ingest auto-strip ---------- #


def test_ingest_auto_strips_when_schema_declares(tmp_path):
    root = _corpus(tmp_path, declare_strip=True)
    m1 = _msg("one", "Inbox,Category Updates,Unread")
    m2 = _msg("two", None)
    source = _mbox(tmp_path, "full.mbox", m1, m2)
    delivered_b3 = hashing.hash_file(source)["blake3"]

    rid = _ingest(root, source)
    assert rid != delivered_b3  # identity is over the CANONICALIZED bytes

    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    data = stored.read_bytes()
    assert b"X-Gmail-Labels" not in data
    assert hashing.hash_file(stored)["blake3"] == rid
    scan = mboxfile.scan(stored, None)
    assert {f.blake3 for f in scan.facts.values()} == {_b3(_stripped(m1)), _b3(m2)}

    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]
    assert fields["stripped_members"] == 1
    assert fields["source_transport"] == f"blake3:{delivered_b3}"


def test_ingest_untouched_without_declaration(tmp_path):
    root = _corpus(tmp_path)
    source = _mbox(tmp_path, "full.mbox", _msg("one", "Inbox,Unread"))
    delivered_b3 = hashing.hash_file(source)["blake3"]
    rid = _ingest(root, source)
    assert rid == delivered_b3  # hash-what-staged holds when nothing is declared
    stored = root / "artifacts" / rid[:2] / f"{rid}.mbox"
    assert b"X-Gmail-Labels" in stored.read_bytes()


def test_ingest_already_canonical_passes_through(tmp_path):
    root = _corpus(tmp_path, declare_strip=True)
    source = _mbox(tmp_path, "clean.mbox", _msg("one", None))
    delivered_b3 = hashing.hash_file(source)["blake3"]
    rid = _ingest(root, source)
    assert rid == delivered_b3  # nothing to strip → no rewrite, no provenance
    post = records.load(root / "records" / rid[:2] / f"{rid}.md")
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert "stripped_headers" not in fields


# ---------- mbox-window resolves the same config ---------- #


def test_window_config_strip_crosses_prestrip_lineage(tmp_path):
    """The lineage baseline is ingested LABEL-FULL in a corpus with no declaration; the
    declaration is then added (the corpus adopts the strip), and a window run with NO
    --strip flag resolves it from config: churned members are excluded as-if-stripped and
    the emitted delta member is label-free."""
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
    # The corpus adopts the strip AFTER the label-full baseline landed.
    local = root / "schema/mime/application/application_mbox.yaml"
    local.parent.mkdir(parents=True)
    local.write_text(_PACKAGED_MBOX_SCHEMA.read_text() + "\nstrip_headers:\n- X-Gmail-Labels\n")
    schemas.cache_clear()

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
                strip=None,  # ← resolved from the schema declaration, not the CLI
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


def test_window_without_declaration_readmits_label_churn(tmp_path):
    """The negative control: no schema declaration, no --strip → label churn re-admits."""
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
