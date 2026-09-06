"""tar/tgz manifest drafter + MIME detection + the `path=` member transform (spec §12.4).

The tar family drafts as the same embed manifest as zip: every member is a transport addressed
`path=<relpath>`, its bytes resolved back through `tararchive`/`transforms/tar.py` so a recorded
address round-trips byte-identically (the same assertion the EPUB and zip drafters make). A tgz
is a solid gzip stream, so extraction streams through the decompressor. Detection maps a
gzip-wrapping-a-tar to `application/x-tar`; a plain gzip and an mbox get their own types.
"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import blake3
import frontmatter
import pytest

from corpus import functional_uri as furi
from corpus import (
    hashing,
    mime,
    paths,
    recordbuild,
    records,
    resolver,
    schemas,
    tararchive,
    transforms,
)
from corpus.draft.tar_manifest import draft as tar_draft
from corpus.store import LocalArtifactStore

_MEMBERS = {
    "Takeout/Mail/User Settings/Blocked Addresses.json": b'{"blocked": []}\n',
    "Takeout/Mail/config.cfg": b"[mail]\nkeep=all\n",  # text-by-content, generic ext
    "Takeout/Mail/logo.bin": b"\x00\x01\x02\x03\x00PNGish",  # binary (NUL)
}


def _make_tar(path: Path, members: dict[str, bytes] | None = None, *, compress: bool) -> Path:
    mode = "w:gz" if compress else "w"
    with tarfile.open(path, mode) as tf:
        for name, data in (members if members is not None else _MEMBERS).items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 1_700_000_000
            tf.addfile(info, io.BytesIO(data))
    return path


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults (application/x-tar, mbox)
    schemas.cache_clear()
    return root


# ---------- MIME detection ---------- #


def test_detect_plain_tar(tmp_path):
    tar_path = _make_tar(tmp_path / "a.tar", compress=False)
    assert mime.detect(tar_path) == "application/x-tar"


def test_detect_tgz(tmp_path):
    tgz = _make_tar(tmp_path / "a.tgz", compress=True)
    assert mime.detect(tgz) == "application/x-tar"  # gzip-wrapping-a-tar refines to tar


def test_detect_plain_gzip_is_not_tar(tmp_path):
    import gzip

    gz = tmp_path / "notes.json.gz"
    with gzip.open(gz, "wb") as fh:
        fh.write(b'{"just": "json, not a tar"}\n')
    assert mime.detect(gz) == "application/gzip"


def test_detect_mbox(tmp_path):
    mbox = tmp_path / "mail.mbox"
    mbox.write_bytes(b"From alice@example.com Mon Jan  1 2020\r\nSubject: hi\r\n\r\nbody\r\n")
    assert mime.detect(mbox) == "application/mbox"


def test_extension_for_tar_and_mbox():
    assert mime.extension_for("application/x-tar") == "tar"
    assert mime.extension_for("application/mbox") == "mbox"


def test_sniff_head_magic_types():
    assert mime.sniff_head(b"From bob ...", "x") == "application/mbox"
    assert mime.sniff_head(b"%PDF-1.7 ...", "x.pdf") == "application/pdf"
    # a tar member header (ustar at 257) sniffs from its head
    hdr = bytearray(512)
    hdr[257:262] = b"ustar"
    assert mime.sniff_head(bytes(hdr), "nested.tar") == "application/x-tar"


def test_sniff_head_zip_family_refines_by_extension():
    """Zip magic + a declared package extension refines within the family (the central
    directory a seekable `detect` would check is out of a streamed head's reach)."""
    zip_head = b"PK\x03\x04" + b"\x00" * 26
    assert (
        mime.sniff_head(zip_head, "Volunteer Handbook Winnipeg 2026.docx")
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert (
        mime.sniff_head(zip_head, "schedule.XLSX")
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert mime.sniff_head(zip_head, "book.epub") == "application/epub+zip"
    assert mime.sniff_head(zip_head, "bundle.zip") == "application/zip"
    assert mime.sniff_head(zip_head) == "application/zip"


# ---------- drafter ---------- #


@pytest.mark.parametrize("compress", [False, True])
def test_tar_manifest_is_embeds_only(tmp_path, compress):
    root = _corpus(tmp_path)
    tar_path = _make_tar(tmp_path / "diag.tar", compress=compress)
    schema = schemas.load_mime_schema(root, "application/x-tar")
    build = recordbuild.begin({}, root)
    result = tar_draft(tar_path, build=build, corpus_root=root, mime_schema=schema)

    assert result["fields"]["member_count"] == 3
    assert result["fields"]["compression"] == ("gzip" if compress else "none")
    # NO content zone — members are transports (embeds), not content atoms.
    assert build.blocks == []

    by_addr = {e["address"]: e for e in result["embeds"]}
    assert set(by_addr) == {
        "path=Takeout/Mail/User Settings/Blocked Addresses.json",
        "path=Takeout/Mail/config.cfg",
        "path=Takeout/Mail/logo.bin",
    }
    # content-sniffed media types: a .cfg with text content is text/plain; NUL bytes → binary.
    assert by_addr["path=Takeout/Mail/config.cfg"]["media_type"] == "text/plain"
    assert by_addr["path=Takeout/Mail/logo.bin"]["media_type"] == "application/octet-stream"
    assert all(e["transport"].startswith("blake3:") for e in result["embeds"])
    recordbuild.finish(build)


def test_tar_empty_archive_issue(tmp_path):
    root = _corpus(tmp_path)
    empty = _make_tar(tmp_path / "empty.tar", {}, compress=False)
    schema = schemas.load_mime_schema(root, "application/x-tar")
    build = recordbuild.begin({}, root)
    result = tar_draft(empty, build=build, corpus_root=root, mime_schema=schema)
    assert result["issues"] and result["issues"][0]["id"] == "partial-content"
    assert result["issues"][0]["severity"] == "blocking"


# ---------- transform round-trip ---------- #


def test_tar_path_transform_registered():
    handler = transforms.lookup("tar", "path")
    assert handler is not None
    assert handler.output_kind == "bytes"


def test_resolve_member_matches_embed_transport(tmp_path):
    """The core round-trip: bytes resolved via `path=` blake3 to the embed's recorded
    transport — the same assertion `test_drafters.py` makes for EPUB image members."""
    root = _corpus(tmp_path)
    tgz = _make_tar(tmp_path / "diag.tgz", compress=True)
    schema = schemas.load_mime_schema(root, "application/x-tar")
    build = recordbuild.begin({}, root)
    embeds = tar_draft(tgz, build=build, corpus_root=root, mime_schema=schema)["embeds"]

    for emb in embeds:
        rel = emb["address"].removeprefix("path=")
        resolved = tararchive.resolve_member(tgz, rel)
        assert f"blake3:{blake3.blake3(resolved).hexdigest()}" == emb["transport"]


@pytest.mark.parametrize("compress", [False, True])
def test_path_resolves_member_bytes_end_to_end(tmp_path, compress):
    root = _corpus(tmp_path)
    tar_path = _make_tar(tmp_path / "diag.tar", compress=compress)
    rid = hashing.hash_file(tar_path)["blake3"]
    LocalArtifactStore(root).put(rid, "tar", tar_path)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "status": "draft", "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime="application/x-tar", fields={})
    records.dump(post, paths.record_path(root, rid))

    uri = f"corpus://{rid}?path=Takeout/Mail/config.cfg"
    out = resolver.resolve(uri, root)
    assert out.read_bytes() == b"[mail]\nkeep=all\n"


def test_path_sidecar_records_engine_version(tmp_path):
    root = _corpus(tmp_path)
    tar_path = _make_tar(tmp_path / "diag.tar", compress=False)
    rid = hashing.hash_file(tar_path)["blake3"]
    LocalArtifactStore(root).put(rid, "tar", tar_path)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "status": "draft", "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime="application/x-tar", fields={})
    records.dump(post, paths.record_path(root, rid))

    uri = f"corpus://{rid}?path=Takeout/Mail/config.cfg"
    out = resolver.resolve(uri, root)
    sidecar = furi.cache_sidecar_path(out)
    data = json.loads(sidecar.read_text("utf-8"))
    assert data["engine"] == "archive-path@2"


def test_resolve_member_missing_raises(tmp_path):
    tar_path = _make_tar(tmp_path / "a.tar", compress=False)
    with pytest.raises(ValueError, match="no such member"):
        tararchive.resolve_member(tar_path, "Takeout/Mail/nope.txt")


def test_zip_still_makes_valid_tar_sibling(tmp_path):
    # Guard: the shared _manifest core keeps zip and tar producing the same embed shape.
    zpath = tmp_path / "z.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a/b.txt", b"hello")
    from corpus.draft._manifest import digest_and_text, media_type

    with zipfile.ZipFile(zpath) as zf, zf.open("a/b.txt") as fp:
        digest, is_text = digest_and_text(fp)
    assert is_text
    assert digest == hashing.hash_bytes(b"hello", also=())["blake3"]
    assert media_type("a/b.txt", True) == "text/plain"
