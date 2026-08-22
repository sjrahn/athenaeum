"""Compressed single-member envelope collapse at ingest (spec §2, the payload-identity
principle, v32): a bare gzip stream, or a zip holding exactly one non-directory
unencrypted member, mints under the PAYLOAD's identity — the record minted is the
payload's, the envelope's own transport hash attests as delivery provenance in
frontmatter `hash:` (the §12.3.13 mbox `source_transport` precedent, pointed at `hash:`
per the v32 spec text). The same content delivered bare or wrapped mints the same
record; a multi-member archive, an encrypted/directory-only zip "member", or a corrupt
stream fall back to today's behavior untouched.
"""

from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path

import blake3
import pytest

from corpus import paths, records, schemas
from corpus._cli import ingest as ingest_cli


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults only
    schemas.cache_clear()
    return root


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _run_ingest(root: Path, name: str, data: bytes) -> None:
    """Stage `data` as `name` under `capture/` and ingest it. Every test below derives
    the expected record id from content (`_b3`) and asserts the record exists at that
    path, rather than parsing it back out of ingest's stdout."""
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / name
    staged.write_bytes(data)
    assert ingest_cli._ingest_one(root, staged) == 0


def _gzip_with_fname(data: bytes, filename: str) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename=filename, mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(data)
    return buf.getvalue()


def _make_zip(members: dict[str, bytes], *, encrypt_first: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    raw = bytearray(buf.getvalue())
    if encrypt_first:
        # zipfile can't WRITE a password-protected archive, so the test fabricates the
        # general-purpose bit-0 (encrypted) flag directly on the local file header AND
        # its central-directory entry — the exact fact `_try_unwrap_single_member_zip`
        # checks (`entry.flag_bits & 0x1`) before ever attempting a read.
        local_idx = raw.find(b"PK\x03\x04")
        assert local_idx != -1
        raw[local_idx + 6] |= 0x01
        central_idx = raw.find(b"PK\x01\x02")
        assert central_idx != -1
        raw[central_idx + 8] |= 0x01
    return bytes(raw)


_JSON = b'{"hello": "envelope", "padding": "' + b"x" * 64 + b'"}'


# ---------- gzip: bare payload identity ---------- #


def test_gzip_mints_payload_identity_equal_to_bare_ingest(tmp_path):
    root = _corpus(tmp_path)
    _run_ingest(root, "plain.json", _JSON)
    expected_id = _b3(_JSON)
    assert paths.record_path(root, expected_id).is_file()

    root2 = _corpus(tmp_path.parent / (tmp_path.name + "-gz"))
    wrapped = _gzip_with_fname(_JSON, "inner.json")
    # No compound-extension hint on the outer name — correct detection depends on the
    # gzip FNAME field being recovered and used to rename the unwrapped payload.
    _run_ingest(root2, "blob.gz", wrapped)
    record_file = paths.record_path(root2, expected_id)
    assert record_file.is_file(), "gzip route must mint the SAME id as the bare route"

    post = records.load(record_file)
    assert records.media_type_for(post) == "application/json"

    entries = records.record_hashes(post)
    assert entries["blake3-envelope"] == _b3(wrapped)

    origins = list(records.iter_origin_blocks(post))
    fields = origins[0].get("fields") or {}
    assert fields.get("envelope_kind") == "gzip"
    assert fields.get("envelope_filename") == "inner.json"


def test_gzip_with_no_fname_falls_back_to_outer_compound_extension(tmp_path):
    root = _corpus(tmp_path)
    wrapped = gzip.compress(_JSON)  # gzip.compress writes no FNAME field
    _run_ingest(root, "export.json.gz", wrapped)
    expected_id = _b3(_JSON)
    record_file = paths.record_path(root, expected_id)
    assert record_file.is_file()
    post = records.load(record_file)
    assert records.media_type_for(post) == "application/json"
    origins = list(records.iter_origin_blocks(post))
    fields = origins[0].get("fields") or {}
    assert fields.get("envelope_kind") == "gzip"
    assert "envelope_filename" not in fields  # no FNAME to recover


# ---------- zip: one-file archive ---------- #


def test_one_file_zip_mints_payload_identity(tmp_path):
    root = _corpus(tmp_path)
    data = _make_zip({"notes/export.json": _JSON})
    _run_ingest(root, "bundle.zip", data)
    expected_id = _b3(_JSON)
    record_file = paths.record_path(root, expected_id)
    assert record_file.is_file()

    post = records.load(record_file)
    assert records.media_type_for(post) == "application/json"
    entries = records.record_hashes(post)
    assert entries["blake3-envelope"] == _b3(data)
    origins = list(records.iter_origin_blocks(post))
    fields = origins[0].get("fields") or {}
    assert fields.get("envelope_kind") == "zip"
    assert fields.get("envelope_filename") == "notes/export.json"


def test_one_file_zip_equals_bare_ingest_id(tmp_path):
    root_bare = _corpus(tmp_path / "bare")
    _run_ingest(root_bare, "plain.json", _JSON)
    root_zip = _corpus(tmp_path / "zip")
    _run_ingest(root_zip, "bundle.zip", _make_zip({"plain.json": _JSON}))
    assert _b3(_JSON) == _b3(_JSON)  # sanity
    assert paths.record_path(root_bare, _b3(_JSON)).is_file()
    assert paths.record_path(root_zip, _b3(_JSON)).is_file()


# ---------- unchanged paths: multi-member, directory-only, encrypted ---------- #


def test_multi_member_zip_stays_manifest(tmp_path):
    root = _corpus(tmp_path)
    data = _make_zip({"a.json": b'{"a": 1}', "b.json": b'{"b": 2}'})
    _run_ingest(root, "multi.zip", data)
    record_file = paths.record_path(root, _b3(data))
    assert record_file.is_file(), "an unchanged zip mints under its OWN archive identity"
    post = records.load(record_file)
    assert records.media_type_for(post) == "application/zip"
    assert "blake3-envelope" not in records.record_hashes(post)


def test_zip_lone_directory_entry_no_collapse(tmp_path):
    root = _corpus(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("onlydir/"), "")
    data = buf.getvalue()
    _run_ingest(root, "emptydir.zip", data)
    record_file = paths.record_path(root, _b3(data))
    assert record_file.is_file()
    post = records.load(record_file)
    assert records.media_type_for(post) == "application/zip"
    assert "blake3-envelope" not in records.record_hashes(post)


def test_encrypted_zip_member_no_collapse(tmp_path):
    root = _corpus(tmp_path)
    data = _make_zip({"secret.json": _JSON}, encrypt_first=True)
    _run_ingest(root, "locked.zip", data)
    record_file = paths.record_path(root, _b3(data))
    assert record_file.is_file(), "an encrypted member falls back to the ARCHIVE's own identity"
    post = records.load(record_file)
    assert records.media_type_for(post) == "application/zip"
    assert "blake3-envelope" not in records.record_hashes(post)


def test_corrupt_gzip_falls_back_to_today(tmp_path, capsys):
    """A truncated/malformed gzip stream never collapses — `_try_unwrap_gzip` catches
    the decode failure, prints a note, and leaves `src` byte-identical, so ingest falls
    through to exactly today's pre-collapse behavior for a bare gzip: no mime schema
    declares `application/gzip`, so it exits cleanly rather than raising out of the
    collapse attempt itself (the regression this test actually guards against)."""
    root = _corpus(tmp_path)
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / "broken.gz"
    staged.write_bytes(b"\x1f\x8b\x08\x00" + b"\x00" * 4 + b"\x00\x00" + b"not really deflate")
    with pytest.raises(SystemExit) as exc:
        ingest_cli._ingest_one(root, staged)
    assert "no mime schema for 'application/gzip'" in str(exc.value)
    assert "not a well-formed gzip stream" in capsys.readouterr().err


# ---------- nested wrapper: gz inside zip-of-one ---------- #


def test_nested_wrapper_gz_inside_zip_collapses_fully(tmp_path):
    root = _corpus(tmp_path)
    inner_gz = gzip.compress(_JSON)  # no FNAME
    data = _make_zip({"payload.json.gz": inner_gz})
    _run_ingest(root, "wrapper.zip", data)
    expected_id = _b3(_JSON)
    record_file = paths.record_path(root, expected_id)
    assert record_file.is_file(), "recursive unwrap must land on the fully-unwrapped payload"

    post = records.load(record_file)
    assert records.media_type_for(post) == "application/json"
    entries = records.record_hashes(post)
    # Only the AS-DELIVERED (outermost) envelope is attested — nested layers are
    # packaging over packaging, not separately attested.
    assert entries["blake3-envelope"] == _b3(data)

    origins = list(records.iter_origin_blocks(post))
    fields = origins[0].get("fields") or {}
    assert fields.get("envelope_kind") == ["zip", "gzip"]
    assert fields.get("envelope_filename") == "payload.json.gz"


# ---------- dedup fold: envelope delivery of an already-ingested payload ---------- #


def test_envelope_ingest_folds_onto_existing_bare_payload(tmp_path, capsys):
    root = _corpus(tmp_path)
    _run_ingest(root, "plain.json", _JSON)
    expected_id = _b3(_JSON)
    record_file = paths.record_path(root, expected_id)
    assert record_file.is_file()

    wrapped = _gzip_with_fname(_JSON, "plain.json")
    cap = root / "capture"
    staged = cap / "wrapped.gz"
    staged.write_bytes(wrapped)
    assert ingest_cli._ingest_one(root, staged) == 0
    out = capsys.readouterr().out
    assert "re-encounter" in out

    # Still exactly one record — the envelope delivery folded, it never minted a
    # second one under the envelope's own (different) bytes.
    assert not paths.record_path(root, _b3(wrapped)).is_file()
    post = records.load(record_file)
    entries = records.record_hashes(post)
    assert entries["blake3-envelope"] == _b3(wrapped)
