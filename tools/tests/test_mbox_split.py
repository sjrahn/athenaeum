"""Closed-year snapshot split — `corpus mbox-split` (spec §12.3.13): year bucketing
(closed-only, undated-never-closes), chrome strip via the schema declaration, the
deterministic container zip, sidecar provenance, and the live-critical integration path:
container ingest → year-member promotion → msg= resolution of stripped bytes.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

import blake3
import yaml

import corpus as corpus_pkg
from corpus import mboxfile, records, schemas
from corpus._cli import ingest as ingest_cli
from corpus._cli import mbox_split
from corpus._cli import promote as promote_cli

CRLF = b"\r\n"

_PACKAGED_MBOX_SCHEMA = (
    Path(corpus_pkg.__file__).parent
    / "schemas_default/mime/application/application_mbox.yaml"
)


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _sep(i: int) -> bytes:
    return f"From {i}@xxx Mon Jan 01 00:00:00 +0000 2024".encode() + CRLF


def _msg(subject: str, date: str | None, labels: str | None = None) -> bytes:
    head = b"From: a@x.com" + CRLF
    if labels is not None:
        head += b"X-Gmail-Labels: " + labels.encode() + CRLF
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


def _stripped(member: bytes) -> bytes:
    lines = member.split(CRLF)
    return CRLF.join(ln for ln in lines if not ln.startswith(b"X-Gmail-Labels:"))


def _corpus(tmp_path: Path, declare_strip: bool = True) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    if declare_strip:
        local = root / "schema/mime/application/application_mbox.yaml"
        local.parent.mkdir(parents=True)
        local.write_text(
            _PACKAGED_MBOX_SCHEMA.read_text() + "\nstrip_headers:\n- X-Gmail-Labels\n"
        )
    schemas.cache_clear()
    return root


M_2023A = _msg("a", "Mon, 06 Mar 2023 10:00:00 +0000", "Inbox,Category Updates")
M_2023B = _msg("b", "Tue, 07 Nov 2023 10:00:00 +0000")
M_2024 = _msg("c", "Wed, 01 May 2024 10:00:00 +0000", "Archived,Opened")
M_CUR = _msg("d", "Sat, 04 Jan 2025 10:00:00 +0000")
M_UNDATED = _msg("e", None, "Inbox")


def _run_split(root: Path, source: Path, current_year: int = 2025) -> int:
    return mbox_split.run(
        argparse.Namespace(
            source=str(source),
            current_year=current_year,
            origin=None,
            strip=None,
            corpus_root=str(root),
        )
    )


def test_split_buckets_closed_years_and_residue(tmp_path):
    root = _corpus(tmp_path)
    source = _mbox(tmp_path, "full.mbox", M_2023A, M_CUR, M_2024, M_UNDATED, M_2023B)
    assert _run_split(root, source) == 0

    container = root / "capture" / "full-years-2023-2024.zip"
    residue = root / "capture" / "full-current-2025.mbox"
    assert container.is_file() and residue.is_file()

    with zipfile.ZipFile(container) as z:
        assert z.namelist() == ["2023.mbox", "2024.mbox"]
        z.extractall(tmp_path / "x")
    scan_2023 = mboxfile.scan(tmp_path / "x/2023.mbox", None)
    assert scan_2023.count == 2
    assert {f.blake3 for f in scan_2023.facts.values()} == {
        _b3(_stripped(M_2023A)),
        _b3(M_2023B),
    }
    scan_2024 = mboxfile.scan(tmp_path / "x/2024.mbox", None)
    assert scan_2024.facts[1].blake3 == _b3(_stripped(M_2024))

    # Residue: the current-year member AND the undated one (never falsely closed).
    scan_res = mboxfile.scan(residue, None)
    assert scan_res.count == 2
    assert {f.blake3 for f in scan_res.facts.values()} == {
        _b3(M_CUR),
        _b3(_stripped(M_UNDATED)),
    }

    sidecar = yaml.safe_load(
        container.with_suffix(container.suffix + ".capture.yaml").read_text()
    )
    fields = sidecar["origin_fields"]
    assert fields["split_by"] == "year"
    assert fields["years"] == {"2023": 2, "2024": 1}
    assert fields["current_year"] == 2025
    assert fields["current_count"] == 2
    assert fields["undated_count"] == 1
    assert fields["stripped_headers"] == ["X-Gmail-Labels"]
    assert fields["source_export"] == "full.mbox"


def test_split_is_deterministic(tmp_path):
    root_a = _corpus(tmp_path / "a")
    root_b = _corpus(tmp_path / "b")
    src_a = _mbox(tmp_path, "one.mbox", M_2023A, M_2024, M_CUR)
    src_b = tmp_path / "two" / "one.mbox"
    src_b.parent.mkdir()
    shutil.copy(src_a, src_b)
    shutil.copystat(src_a, src_b)
    assert _run_split(root_a, src_a) == 0
    assert _run_split(root_b, src_b) == 0
    za = (root_a / "capture/one-years-2023-2024.zip").read_bytes()
    zb = (root_b / "capture/one-years-2023-2024.zip").read_bytes()
    assert za == zb  # same input bytes + mtime → same container bytes


def test_container_ingests_and_year_promotes(tmp_path):
    """The live-critical path: ingest the container → zip-manifest members → promote a
    year member → an application/mbox record whose msg= members are the stripped bytes."""
    root = _corpus(tmp_path)
    source = _mbox(tmp_path, "full.mbox", M_2023A, M_2024, M_CUR, M_2023B)
    assert _run_split(root, source) == 0
    container = root / "capture" / "full-years-2023-2024.zip"
    container_id = None

    # Ingest the container (staged in place).
    from corpus import hashing

    container_id = hashing.hash_file(container)["blake3"]
    assert ingest_cli._ingest_one(root, container) == 0
    post = records.load(root / "records" / container_id[:2] / f"{container_id}.md")
    embeds = {e.get("address"): e for e in records.iter_embed_blocks(post)}
    assert set(embeds) == {"path=2023.mbox", "path=2024.mbox"}
    assert embeds["path=2023.mbox"]["media_type"] == "application/mbox"
    # Container sidecar fields landed on the origin block.
    fields = next(iter(records.iter_origin_blocks(post))).get("fields") or {}
    assert fields["split_by"] == "year"

    # Promote 2023 → a first-class mbox record; bytes resolve through the container.
    assert (
        promote_cli.run(
            argparse.Namespace(
                uri=f"corpus://{container_id}?path=2023.mbox",
                json=False,
                corpus_root=str(root),
            )
        )
        == 0
    )
    year_id = embeds["path=2023.mbox"]["transport"].split(":", 1)[1]
    year_post = records.load(root / "records" / year_id[:2] / f"{year_id}.md")
    assert records.media_type_for(year_post) == "application/mbox"
    # msg= resolution yields the stripped member bytes.
    from corpus import containment

    local = containment.ensure_local_bytes(root, year_id, "mbox")
    assert mboxfile.resolve_member(local, 1) == _stripped(M_2023A)
    assert mboxfile.resolve_member(local, 2) == M_2023B


def test_no_closed_years_exits(tmp_path):
    import pytest

    root = _corpus(tmp_path)
    source = _mbox(tmp_path, "full.mbox", M_CUR)
    with pytest.raises(SystemExit, match="no closed-year"):
        _run_split(root, source)
