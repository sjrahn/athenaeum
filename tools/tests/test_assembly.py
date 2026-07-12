"""The export-job bundle assembler — `corpus.assembly` engine + `corpus assemble` CLI (spec
§2.1, §12.4, §12.8).

Covers the byte mechanics (single/multi-part tar+zip union, dedup, conflict, rewrites, additions
at root, verbatim paths + mtimes, stored-vs-zstd routing, determinism) and the whole
capture-side loop through the REAL pipeline: assemble → ingest → draft (zip-manifest) → promote →
resolve, so a method-93 (zstd) member proves it round-trips byte-identically through
`ziparchive.open_member` and the member-index resolve path. Plus the CLI's overlay-driven field
derivation + capture sidecar.
"""

from __future__ import annotations

import argparse
import io
import shutil
import tarfile
import zipfile
from pathlib import Path

import blake3
import pytest

from corpus import assembly, hashing, paths, records, resolver, schemas, ziparchive
from corpus._cli import assemble as assemble_cli
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli

# A fixed member mtime (2026-07-03T16:57:58Z) so the UTC-decomposed DOS tuple is predictable. An
# EVEN second, because a zip DOS timestamp has 2-second resolution (odd seconds floor down).
_MTIME = 1783097878  # int(datetime(2026,7,3,16,57,58, UTC).timestamp()); machine-independent
_MTIME_TUPLE = (2026, 7, 3, 16, 57, 58)


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _tar(path: Path, members: dict[str, bytes], *, gz: bool = False, mtime: int = _MTIME) -> Path:
    with tarfile.open(path, "w:gz" if gz else "w") as tf:
        for name, data in members.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mtime = mtime
            tf.addfile(ti, io.BytesIO(data))
    return path


def _zip(path: Path, members: dict[str, bytes], *, date_time=_MTIME_TUPLE) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zi = zipfile.ZipInfo(name, date_time=date_time)
            zf.writestr(zi, data)
    return path


def _part(path: Path, label: str | None = None) -> assembly.SourcePart:
    return assembly.SourcePart(path, label or path.name)


def _members(zpath: Path) -> dict[str, zipfile.ZipInfo]:
    with zipfile.ZipFile(zpath) as zf:
        return {i.filename: i for i in zf.infolist() if not i.is_dir()}


# ---------- the engine: source families ---------- #


def test_single_part_tar(tmp_path):
    src = _tar(tmp_path / "t.tar", {"Takeout/Mail/a.txt": b"aaa", "Takeout/Mail/b.txt": b"bbb"})
    out = tmp_path / "bundle.zip"
    res = assembly.assemble([_part(src)], [], out)
    assert res.member_count == 2
    assert res.services == ["Mail"]
    ms = _members(out)
    assert _b3(zipfile.ZipFile(out).read("Takeout/Mail/a.txt")) == _b3(b"aaa")
    assert set(ms) == {"Takeout/Mail/a.txt", "Takeout/Mail/b.txt"}


def test_tgz_part(tmp_path):
    src = _tar(tmp_path / "t.tgz", {"Takeout/Drive/x.txt": b"x" * 5000}, gz=True)
    out = tmp_path / "bundle.zip"
    res = assembly.assemble([_part(src)], [], out)
    assert res.services == ["Drive"]
    assert zipfile.ZipFile(out).read("Takeout/Drive/x.txt") == b"x" * 5000


def test_zip_part(tmp_path):
    src = _zip(tmp_path / "s.zip", {"Takeout/Photos/p.txt": b"post"})
    out = tmp_path / "bundle.zip"
    res = assembly.assemble([_part(src)], [], out)
    assert res.services == ["Photos"]  # the dir under the single common wrapper root
    assert zipfile.ZipFile(out).read("Takeout/Photos/p.txt") == b"post"


def test_services_no_common_wrapper(tmp_path):
    """When members share no single wrapper dir (an Instagram-style export), the top-level dirs
    ARE the services — the derivation is `top-level dirs under the common root`, and the root is
    then empty (spec §7.2 services). A root-level FILE (Meta's `start_here.html`) is a member of
    the bundle but never a service — categories are dirs."""
    src = _zip(
        tmp_path / "s.zip",
        {"content/a.txt": b"a", "messages/b.txt": b"b", "start_here.html": b"<html/>"},
    )
    res = assembly.assemble([_part(src)], [], tmp_path / "bundle.zip")
    assert res.services == ["content", "messages"]
    assert "start_here.html" in _members(tmp_path / "bundle.zip")


# ---------- union / dedup / conflict ---------- #


def test_multi_part_union(tmp_path):
    p1 = _tar(tmp_path / "p1.tar", {"Takeout/Mail/a.txt": b"a"})
    p2 = _tar(tmp_path / "p2.tar", {"Takeout/Drive/b.txt": b"b"})
    out = tmp_path / "bundle.zip"
    res = assembly.assemble([_part(p1), _part(p2)], [], out)
    assert res.member_count == 2
    assert res.services == ["Drive", "Mail"]  # sorted
    assert set(_members(out)) == {"Takeout/Mail/a.txt", "Takeout/Drive/b.txt"}
    # Two source tombstones, each the archive's own blake3.
    assert [lbl for lbl, _ in res.source_parts] == ["p1.tar", "p2.tar"]
    assert res.source_parts[0][1] == hashing.hash_file(p1)["blake3"]


def test_identical_duplicate_dedup(tmp_path):
    p1 = _tar(tmp_path / "p1.tar", {"Takeout/Mail/x.txt": b"same"})
    p2 = _tar(tmp_path / "p2.tar", {"Takeout/Mail/x.txt": b"same"})  # same path, same bytes
    out = tmp_path / "bundle.zip"
    res = assembly.assemble([_part(p1), _part(p2)], [], out)
    assert res.member_count == 1  # deduped silently
    assert list(_members(out)) == ["Takeout/Mail/x.txt"]


def test_conflict_same_path_different_bytes_is_hard_error(tmp_path):
    p1 = _tar(tmp_path / "p1.tar", {"Takeout/Mail/x.txt": b"one"})
    p2 = _tar(tmp_path / "p2.tar", {"Takeout/Mail/x.txt": b"two"})  # same path, DIFFERENT bytes
    out = tmp_path / "bundle.zip"
    with pytest.raises(assembly.AssemblyError, match="conflict"):
        assembly.assemble([_part(p1), _part(p2)], [], out)
    assert not out.exists()  # no partial bundle left behind


def test_merge_parts_false_refuses_multiple(tmp_path):
    p1 = _tar(tmp_path / "p1.tar", {"Takeout/Mail/a.txt": b"a"})
    p2 = _tar(tmp_path / "p2.tar", {"Takeout/Mail/b.txt": b"b"})
    with pytest.raises(assembly.AssemblyError, match="merge_parts"):
        assembly.assemble([_part(p1), _part(p2)], [], tmp_path / "b.zip", merge_parts=False)


# ---------- rewrites + additions ---------- #


def test_rewrites_applied_and_recorded(tmp_path):
    src = _tar(tmp_path / "t.tar", {"Takeout/Old/legacy.txt": b"L", "Takeout/Mail/keep.txt": b"K"})
    out = tmp_path / "bundle.zip"
    res = assembly.assemble(
        [_part(src)], [], out, rewrites=[{"from": "Takeout/Old/*", "to": "Takeout/New/"}]
    )
    names = set(_members(out))
    assert "Takeout/New/legacy.txt" in names  # moved
    assert "Takeout/Old/legacy.txt" not in names
    assert "Takeout/Mail/keep.txt" in names  # untouched
    assert ("Takeout/Old/legacy.txt", "Takeout/New/legacy.txt") in res.rewrites_applied
    # Bytes are preserved through the rename.
    assert zipfile.ZipFile(out).read("Takeout/New/legacy.txt") == b"L"


def test_additions_land_at_root(tmp_path):
    src = _tar(tmp_path / "t.tar", {"Takeout/Mail/a.txt": b"a"})
    report = tmp_path / "archive_browser.html"
    report.write_bytes(b"<html>report</html>")
    out = tmp_path / "bundle.zip"
    res = assembly.assemble([_part(src)], [report], out)
    assert res.member_count == 2
    names = set(_members(out))
    assert "archive_browser.html" in names  # ROOT, not under Takeout/
    assert "Takeout/archive_browser.html" not in names
    # The addition never counts toward the original services.
    assert res.services == ["Mail"]


# ---------- faithfulness: verbatim paths + mtimes ---------- #


def test_verbatim_paths_and_mtime_preservation(tmp_path):
    src = _tar(
        tmp_path / "t.tar",
        {"Takeout/Mail/User Settings/Blocked Addresses.json": b"{}"},
        mtime=_MTIME,
    )
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(src)], [], out)
    info = _members(out)["Takeout/Mail/User Settings/Blocked Addresses.json"]
    assert info.date_time == _MTIME_TUPLE  # mtime copied (UTC-decomposed, machine-independent)


def test_zip_source_mtime_copied_verbatim(tmp_path):
    src = _zip(tmp_path / "s.zip", {"a.txt": b"a"}, date_time=(2021, 5, 4, 3, 2, 0))
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(src)], [], out)
    assert _members(out)["a.txt"].date_time == (2021, 5, 4, 3, 2, 0)


# ---------- compression routing ---------- #


def test_stored_vs_zstd_routing_by_extension(tmp_path):
    src = _tar(
        tmp_path / "t.tar",
        {
            "Takeout/Mail/big.txt": b"compress me " * 5000,  # → zstd
            "Takeout/Photos/pic.jpg": b"\xff\xd8\xff\xe0" + b"jpegbytes",  # → stored
            "Takeout/Archives/inner.zip": b"PK\x03\x04rest",  # → stored
        },
    )
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(src)], [], out)
    ms = _members(out)
    assert ms["Takeout/Mail/big.txt"].compress_type == zipfile.ZIP_ZSTANDARD
    assert ms["Takeout/Photos/pic.jpg"].compress_type == zipfile.ZIP_STORED
    assert ms["Takeout/Archives/inner.zip"].compress_type == zipfile.ZIP_STORED


def test_level_recorded_and_compresses(tmp_path):
    payload = b"the quick brown fox " * 20000
    src = _tar(tmp_path / "t.tar", {"Takeout/Mail/a.txt": payload})
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(src)], [], out, level=19)
    info = _members(out)["Takeout/Mail/a.txt"]
    assert info.compress_type == zipfile.ZIP_ZSTANDARD
    assert info.compress_size < info.file_size  # actually compressed


# ---------- determinism ---------- #


def test_deterministic_byte_identical(tmp_path):
    src = _tar(
        tmp_path / "t.tgz",
        {"Takeout/Mail/a.txt": b"a" * 3000, "Takeout/Mail/b.json": b"{}"},
        gz=True,
    )
    report = tmp_path / "archive_browser.html"
    report.write_bytes(b"<html>r</html>")
    out1 = tmp_path / "b1.zip"
    out2 = tmp_path / "b2.zip"
    assembly.assemble([_part(src)], [report], out1, level=19)
    assembly.assemble([_part(src)], [report], out2, level=19)
    assert out1.read_bytes() == out2.read_bytes()


def test_comment_stamped(tmp_path):
    src = _tar(tmp_path / "t.tar", {"Takeout/Mail/a.txt": b"a"})
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(src)], [], out, comment="google-takeout job 123 · me@x · exported now")
    with zipfile.ZipFile(out) as zf:
        assert zf.comment == b"google-takeout job 123 \xc2\xb7 me@x \xc2\xb7 exported now"


# ---------- the reusable writer core (shared with the future `pack` verb) ---------- #


def test_write_bundle_core_is_pure_bytes_in(tmp_path):
    """The writer core takes `BundleMember`s (member path + re-openable stream + mtime + optional
    compression hint) with NO archive/overlay/source assumption — the contract `corpus pack` will
    reuse. Members are sorted by the writer, routed, streamed, and written deterministically."""
    from contextlib import contextmanager

    def opener(data: bytes):
        @contextmanager
        def _open():
            yield io.BytesIO(data)

        return _open

    members = [
        # deliberately UNSORTED input — the writer enforces sorted order.
        assembly.BundleMember(
            "z/last.txt", opener(b"compress me " * 500), (2026, 1, 2, 3, 4, 0), 6000
        ),
        assembly.BundleMember("a/first.jpg", opener(b"\xff\xd8jpeg"), (2020, 6, 6, 6, 6, 6), 6),
        assembly.BundleMember(
            "m/hinted.bin", opener(b"x" * 4000), (2021, 1, 1, 0, 0, 0), 4000, compression="store"
        ),
    ]
    out = tmp_path / "core.zip"
    size = assembly.write_bundle(members, out, level=19, comment="pure core")
    assert size == out.stat().st_size
    with zipfile.ZipFile(out) as zf:
        assert zf.comment == b"pure core"
        infos = zf.infolist()
        assert [i.filename for i in infos] == ["a/first.jpg", "m/hinted.bin", "z/last.txt"]
        by = {i.filename: i for i in infos}
        assert by["a/first.jpg"].compress_type == zipfile.ZIP_STORED  # extension route
        assert by["m/hinted.bin"].compress_type == zipfile.ZIP_STORED  # explicit hint
        assert by["z/last.txt"].compress_type == zipfile.ZIP_ZSTANDARD
        assert by["z/last.txt"].date_time == (2026, 1, 2, 3, 4, 0)
        assert zf.read("z/last.txt") == b"compress me " * 500
    # Atomic: no partial left behind.
    assert not list(tmp_path.glob("*.partial.*"))


def test_epoch_to_dostuple_is_utc_and_public(tmp_path):
    # Public helper a pack caller uses to convert an artifact mtime; UTC, machine-independent.
    assert assembly.epoch_to_dostuple(_MTIME) == _MTIME_TUPLE
    assert assembly.epoch_to_dostuple(0) == (1980, 1, 1, 0, 0, 0)  # floored to the DOS epoch


# ---------- the whole pipeline: zstd member round-trips through resolve ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    (root / "capture").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _ingest(root: Path, archive: Path) -> str:
    """Stage `archive` (+ its sidecar) into capture/ and ingest it. Tolerant of an archive that
    already lives in capture/ (the CLI's default output dir) — no self-copy."""
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / archive.name
    if archive.resolve() != staged.resolve():
        shutil.copy(archive, staged)
    sidecar = archive.with_name(archive.name + ".capture.yaml")
    staged_sidecar = cap / sidecar.name
    if sidecar.is_file() and sidecar.resolve() != staged_sidecar.resolve():
        shutil.copy(sidecar, staged_sidecar)
    rid = hashing.hash_file(staged)["blake3"]  # hash BEFORE ingest unlinks the staged file
    assert ingest_cli._ingest_one(root, staged) == 0
    return rid


def _draft(root: Path, rid: str) -> None:
    post = records.load(paths.record_path(root, rid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, rid))


def test_zstd_member_round_trips_through_ziparchive(tmp_path):
    """A method-93 (zstd) member reads back byte-identically via the shared `ziparchive`
    helpers — the drafter↔transform contract that makes a recorded `path=` address resolvable."""
    payload = b"zstandard member payload " * 4000
    src = _tar(tmp_path / "t.tar", {"Takeout/Mail/big.mbox": payload})
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(src)], [], out, level=19)
    assert _members(out)["Takeout/Mail/big.mbox"].compress_type == zipfile.ZIP_ZSTANDARD
    # streaming open + whole read, through the module the resolver/promote path uses.
    with ziparchive.open_member(out, "Takeout/Mail/big.mbox") as fp:
        assert fp.read() == payload
    assert ziparchive.resolve_member(out, "Takeout/Mail/big.mbox") == payload


def test_pipeline_promote_and_resolve_zstd_member(tmp_path):
    """assemble → ingest → draft (zip-manifest) → promote → resolve: a zstd member's bytes stream
    back out of the bundle by the member index (§12.9), hashing to the promoted id."""
    root = _corpus(tmp_path)
    payload = b"promote me out of a zstd frame\n" * 1000
    src = _tar(tmp_path / "t.tar", {"Takeout/Mail/note.txt": payload}, gz=True)
    out = tmp_path / "bundle.zip"  # assemble outside capture/, then _ingest stages it in
    assembly.assemble([_part(src)], [], out, level=19)

    cid = _ingest(root, out)
    _draft(root, cid)
    # The manifest recorded the member's blake3 as the embed transport.
    post = records.load(paths.record_path(root, cid))
    transports = {e.get("address"): e.get("transport") for e in records.iter_embed_blocks(post)}
    assert transports["path=Takeout/Mail/note.txt"] == records.format_hash("blake3", _b3(payload))

    assert promote_cli.run(argparse.Namespace(
        uri=f"corpus://{cid}?path=Takeout/Mail/note.txt", json=False, corpus_root=str(root)
    )) == 0
    pid = _b3(payload)
    resolved = resolver.resolve(f"corpus://{pid}", root)
    assert resolved.read_bytes() == payload
    assert _b3(resolved.read_bytes()) == pid


# ---------- the CLI: overlay-driven derivation + sidecar ---------- #

_TEST_OVERLAY = """\
description: test export overlay
extended_fields:
  account: {type: string}
  exported_at: {type: string}
  services: {type: string_or_list}
  job: {type: string, semantic_type: identifier}
  source_parts: {type: string_or_list}
capture:
  assembly:
    merge_parts: true
    conflict: error
    additions:
    - archive_browser.html
    rewrites: []
    level: 12
    derive:
      from_source_name: '^takeout-(?P<exported_stamp>\\d{8}T\\d{6}Z)-(?P<part>.+)\\.(?:tgz|tar)$'
      from_additions:
        archive_browser.html:
          account: 'Archive for ([^\\s<]+@[^\\s<]+)'
          job: 'job-id[^>]*>\\s*([0-9a-fA-F-]{36})'
"""

_REPORT = (
    b'<title>Google Data Export Archive Contents</title>'
    b'<div class="job-id hidden">64de2346-c979-4236-8e8b-e05c56c934be</div>'
    b'<h1 class="header_title">Archive for Sample@Example.com</h1>'
)


def _corpus_with_overlay(tmp_path: Path, overlay_id: str = "test-export") -> Path:
    root = _corpus(tmp_path)
    (root / "schema" / "origin").mkdir(parents=True)
    (root / "schema" / "origin" / f"{overlay_id}.yaml").write_text(_TEST_OVERLAY, encoding="utf-8")
    schemas.cache_clear()
    return root


def _run_assemble(root: Path, **kw) -> None:
    ns = argparse.Namespace(
        origin="test-export", additions=[], account=None, job=None, exported_at=None,
        source_name=None, level=None, out=None, json=False, corpus_root=str(root),
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    assert assemble_cli.run(ns) == 0


def test_cli_derivation_and_sidecar(tmp_path):
    root = _corpus_with_overlay(tmp_path)
    src = _tar(
        root / "capture" / "src.tar", {"Takeout/Mail/a.txt": b"a", "Takeout/Mail/b.txt": b"b"}
    )
    report = root / "capture" / "archive_browser.html"
    report.write_bytes(_REPORT)
    out = root / "capture" / "bundle.zip"

    _run_assemble(
        root, sources=[src], additions=[report], out=out,
        source_name="takeout-20260703T165759Z-3-001.tgz",
    )
    assert out.is_file()
    import yaml

    sidecar = yaml.safe_load((out.with_name(out.name + ".capture.yaml")).read_text())
    assert sidecar["origin_schema"] == "test-export"
    fields = sidecar["origin_fields"]
    assert fields["account"] == "Sample@Example.com"  # from the report
    assert fields["job"] == "64de2346-c979-4236-8e8b-e05c56c934be"  # from the report
    assert fields["exported_at"] == "2026-07-03T16:57:59Z"  # from the source-name convention
    assert fields["services"] == "Mail"  # single service → scalar
    # source_parts tombstone: the logical name + the archive's blake3.
    src_b3 = hashing.hash_file(src)["blake3"]
    assert fields["source_parts"] == [f"takeout-20260703T165759Z-3-001.tgz blake3:{src_b3}"]


def test_cli_flags_override_derivation(tmp_path):
    root = _corpus_with_overlay(tmp_path)
    src = _tar(root / "capture" / "src.tar", {"Takeout/Mail/a.txt": b"a"})
    report = root / "capture" / "archive_browser.html"
    report.write_bytes(_REPORT)
    out = root / "capture" / "bundle.zip"
    _run_assemble(
        root, sources=[src], additions=[report], out=out,
        account="override@x.com", job="deadbeef", exported_at="2020-01-01T00:00:00Z",
    )
    import yaml

    doc = yaml.safe_load((out.with_name(out.name + ".capture.yaml")).read_text())
    fields = doc["origin_fields"]
    assert fields["account"] == "override@x.com"
    assert fields["job"] == "deadbeef"
    assert fields["exported_at"] == "2020-01-01T00:00:00Z"


def test_cli_undeclared_addition_refused(tmp_path):
    root = _corpus_with_overlay(tmp_path)
    src = _tar(root / "capture" / "src.tar", {"Takeout/Mail/a.txt": b"a"})
    stray = root / "capture" / "not-declared.txt"
    stray.write_bytes(b"stray")
    with pytest.raises(SystemExit, match="not declared"):
        _run_assemble(root, sources=[src], additions=[stray], out=root / "capture" / "b.zip")


def test_cli_ingest_draft_yields_manifest(tmp_path):
    """End-to-end through the CLI: the bundle ingests as ONE record and drafts to a manifest whose
    embeds carry the members' blake3 transports + the report at root."""
    root = _corpus_with_overlay(tmp_path)
    src = _tar(root / "capture" / "src.tar", {"Takeout/Mail/a.txt": b"aaa"}, gz=True)
    report = root / "capture" / "archive_browser.html"
    report.write_bytes(_REPORT)
    out = root / "capture" / "bundle.zip"
    _run_assemble(
        root, sources=[src], additions=[report], out=out,
        source_name="takeout-20260703T165759Z-3-001.tgz",
    )

    cid = _ingest(root, out)
    _draft(root, cid)
    post = records.load(paths.record_path(root, cid))
    embeds = {e.get("address"): e.get("transport") for e in records.iter_embed_blocks(post)}
    assert embeds["path=Takeout/Mail/a.txt"] == records.format_hash("blake3", _b3(b"aaa"))
    assert embeds["path=archive_browser.html"] == records.format_hash("blake3", _b3(_REPORT))
    # The manifest names the per-member zstd codec (method 93), not a bare "method-93".
    artifact = records.artifact_block(post) or {}
    assert "zstd" in str((artifact.get("fields") or {}).get("compression", ""))
    # The qualified origin block carries the derived field set.
    origins = list(records.iter_origin_blocks(post))
    assert any(o.get("id") == "test-export" for o in origins)
    fields = next(o for o in origins if o.get("id") == "test-export").get("fields") or {}
    assert fields.get("account") == "Sample@Example.com"
    assert fields.get("job") == "64de2346-c979-4236-8e8b-e05c56c934be"


# ---------- directory sources + excludes (2.1: envelope-less deliveries) ---------- #


def _tree(root: Path, members: dict[str, bytes], *, mtime: int = _MTIME) -> Path:
    """A loose export tree on disk (a DiscordChatExporter-style delivery — no envelope)."""
    import os

    for rel, data in members.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.utime(p, (mtime, mtime))
    return root


def test_directory_source_members_verbatim(tmp_path):
    """A directory source's files become members at their tree relpaths, mtimes from disk,
    stored/zstd routing by extension — and NO source_parts tombstone (no envelope)."""
    src = _tree(
        tmp_path / "export",
        {
            "channel.json": b'{"a": 1}' * 64,
            "assets/pic.png": b"\x89PNG fake",
            "assets/clip.mp4": b"mp4",
        },
    )
    out = tmp_path / "bundle.zip"
    result = assembly.assemble([_part(src)], [], out)

    members = _members(out)
    assert set(members) == {"channel.json", "assets/pic.png", "assets/clip.mp4"}
    assert members["channel.json"].date_time == _MTIME_TUPLE
    assert members["channel.json"].compress_type == zipfile.ZIP_ZSTANDARD
    assert members["assets/pic.png"].compress_type == zipfile.ZIP_STORED
    assert members["assets/clip.mp4"].compress_type == zipfile.ZIP_STORED
    assert result.source_parts == []  # a directory delivery has no envelope to tombstone
    assert result.excluded == []
    with zipfile.ZipFile(out) as zf:
        assert zf.read("channel.json") == b'{"a": 1}' * 64


def test_directory_source_deterministic(tmp_path):
    src = _tree(tmp_path / "export", {"a.json": b"x" * 2000, "assets/b.png": b"png"})
    out1, out2 = tmp_path / "b1.zip", tmp_path / "b2.zip"
    assembly.assemble([_part(src)], [], out1)
    assembly.assemble([_part(src)], [], out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_excludes_basename_and_relpath_patterns(tmp_path):
    """A slash-less exclude pattern claims its basename at ANY depth; a slashed pattern
    fnmatches the full relpath. Exclusions are reported, never silent."""
    src = _tree(
        tmp_path / "export",
        {
            "a.json": b"{}",
            ".DS_Store": b"cruft",
            "assets/.DS_Store": b"cruft",
            "assets/pic.png": b"png",
            "tmp/scratch.txt": b"scratch",
        },
    )
    out = tmp_path / "bundle.zip"
    result = assembly.assemble([_part(src)], [], out, excludes=[".DS_Store", "tmp/*"])
    assert set(_members(out)) == {"a.json", "assets/pic.png"}
    assert result.excluded == [".DS_Store", "assets/.DS_Store", "tmp/scratch.txt"]
    assert result.member_count == 2


def test_directory_and_archive_parts_union(tmp_path):
    """A directory part and an archive part union like any multi-part delivery."""
    tree = _tree(tmp_path / "export", {"a.json": b"{}"})
    arch = _zip(tmp_path / "extra.zip", {"assets/b.png": b"png"})
    out = tmp_path / "bundle.zip"
    result = assembly.assemble([_part(tree), _part(arch)], [], out)
    assert set(_members(out)) == {"a.json", "assets/b.png"}
    # Only the archive part leaves a tombstone.
    assert [label for label, _ in result.source_parts] == ["extra.zip"]


# ---------- the CLI: directory delivery + member-head derivation (discord-shaped) ---------- #

_DISCORD_OVERLAY = """\
description: test discord-flavoured export overlay
extended_fields:
  account: {type: string}
  exported_at: {type: string}
  guild: {type: string}
  guild_id: {type: string, semantic_type: identifier}
capture:
  assembly:
    merge_parts: true
    conflict: error
    additions: []
    rewrites: []
    excludes: ['.DS_Store']
    level: 12
    seed_fields: [guild, guild_id]
    name_fields: [guild]
    derive:
      from_member_head:
        glob: '*.json'
        bytes: 4096
        fields:
          guild: '"name":\\s*"([^"]+)"'
          guild_id: '"guild":\\s*\\{\\s*"id":\\s*"(\\d+)"'
          exported_at: '"exportedAt":\\s*"([^"]+)"'
"""

_CHANNEL_A = (
    b'{"guild": {"id": "42", "name": "Test Guild"}, "channel": {"id": "1"},'
    b' "exportedAt": "2026-07-12T15:50:01Z", "messages": []}'
)
_CHANNEL_B = (
    b'{"guild": {"id": "42", "name": "Test Guild"}, "channel": {"id": "2"},'
    b' "exportedAt": "2026-07-12T15:50:09Z", "messages": []}'
)


def _corpus_with_discord_overlay(tmp_path: Path) -> Path:
    root = _corpus(tmp_path)
    (root / "schema" / "origin").mkdir(parents=True)
    (root / "schema" / "origin" / "test-discord.yaml").write_text(
        _DISCORD_OVERLAY, encoding="utf-8"
    )
    schemas.cache_clear()
    return root


def test_cli_directory_source_member_head_derivation(tmp_path):
    """The whole discord shape: a loose tree assembles via overlay config — member-head
    derivation (guild verbatim, exported_at = the max stamp across members), seed_fields into
    the sidecar, name_fields into the bundle filename, excludes honored, and neither
    `services` (undeclared) nor `source_parts` (no envelope) in the sidecar."""
    root = _corpus_with_discord_overlay(tmp_path)
    src = _tree(
        root / "capture" / "test-guild",
        {"chan-a.json": _CHANNEL_A, "chan-b.json": _CHANNEL_B, ".DS_Store": b"cruft",
         "assets/pic.png": b"png"},
    )
    ns = argparse.Namespace(
        origin="test-discord", sources=[src], additions=[], account=None, job=None,
        exported_at=None, source_name=None, level=None, out=None, json=False,
        corpus_root=str(root),
    )
    assert assemble_cli.run(ns) == 0

    out = root / "capture" / "test-discord-Test-Guild-20260712T155009Z.zip"
    assert out.is_file(), sorted(p.name for p in (root / "capture").iterdir())
    assert set(_members(out)) == {"chan-a.json", "chan-b.json", "assets/pic.png"}

    import yaml

    sidecar = yaml.safe_load((out.with_name(out.name + ".capture.yaml")).read_text())
    fields = sidecar["origin_fields"]
    assert fields["guild"] == "Test Guild"
    assert fields["guild_id"] == "42"
    assert fields["exported_at"] == "2026-07-12T15:50:09Z"  # max across members
    assert "services" not in fields
    assert "source_parts" not in fields
    assert "account" not in fields

    # The archive comment carries the name_fields value verbatim.
    with zipfile.ZipFile(out) as zf:
        comment = zf.comment.decode("utf-8")
    assert "Test Guild" in comment and "2026-07-12T15:50:09Z" in comment

    # And the bundle ingests + drafts as an ordinary manifest whose members carry transports.
    cid = _ingest(root, out)
    _draft(root, cid)
    post = records.load(paths.record_path(root, cid))
    embeds = {e.get("address"): e.get("transport") for e in records.iter_embed_blocks(post)}
    assert embeds["path=chan-a.json"] == records.format_hash("blake3", _b3(_CHANNEL_A))
    origins = list(records.iter_origin_blocks(post))
    fields = next(o for o in origins if o.get("id") == "test-discord").get("fields") or {}
    assert fields.get("guild") == "Test Guild"


def test_resolve_member_with_query_reserved_name(tmp_path):
    """A member whose NAME contains `&` (user-controlled discord thread names) resolves via
    the percent-encoded URI form — the parse-side of the quote_value contract."""
    root = _corpus(tmp_path)
    payload = b'{"guild": "dnd"}'
    tree = _tree(tmp_path / "export", {"Direct Messages - D&D 5e [673].json": payload})
    out = tmp_path / "bundle.zip"
    assembly.assemble([_part(tree)], [], out)
    cid = _ingest(root, out)
    _draft(root, cid)
    resolved = resolver.resolve(
        f"corpus://{cid}?path=Direct Messages - D%26D 5e [673].json", root
    )
    assert resolved.read_bytes() == payload
