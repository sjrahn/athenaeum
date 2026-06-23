"""zip-manifest drafter + schema-driven zip detection + the `path=` member transform.

The drafter renders a self_contained zip as a *description manifest* — it inlines nothing
(members are verbatim, content-addressed, resolvable via `path=`), so every member is an
embed plus a body-empty positioning marker (atom decided by content, not extension), and
opaque binaries are embed-only.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import frontmatter
import pytest

from corpus import (
    mime,
    paths,
    recordbuild,
    records,
    resolver,
    schemas,
    segments,
    transforms,
    ziparchive,
)
from corpus.draft.zip_manifest import draft as zip_draft
from corpus.store import LocalArtifactStore

_MIME = "application/vnd.unraid.diagnostics+zip"

# A minimal schema standing in for corpus-private's: shape signature in `applies_to`,
# self_contained disposition, the zip-manifest draft strategy (manifest = layout only).
_SCHEMA_YAML = """\
description: Unraid diagnostics export (test fixture).
applies_to:
  content_types:
  - application/vnd.unraid.diagnostics+zip
  zip_member_patterns:
  - '^[^/]+/unraid-[^/]*\\.txt$'
  - '^[^/]+/smart/'
artifact_kind: self_contained
working_kind: zip
transport_algos:
- sha256
draft:
  strategy: zip-manifest
  manifest:
    root_strip: true
    sectioning: top_level_folders
"""

# Members under a varying `<host>-diagnostics-<ts>/` wrapper dir. `disk.cfg` exercises the
# content sniff (`.cfg` is unknown to mimetypes but is text); `core.dat` is real binary.
_ROOT = "tower-diagnostics-20260622/"
_MEMBERS = {
    f"{_ROOT}unraid-7.0.0.txt": b"Unraid version 7.0.0\n",  # text marker + text/plain embed
    f"{_ROOT}config/disk.cfg": b"[disk]\nspindown=30\n",  # text-by-content (not octet-stream!)
    f"{_ROOT}smart/sdb.txt": b"SMART data for sdb",  # text marker
    f"{_ROOT}logs/core.dat": b"\x00\x01\x02\x03\x00bin",  # binary (NUL) -> embed only
}


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    schema_dir = root / "schema" / "mime" / "application"
    schema_dir.mkdir(parents=True)
    (schema_dir / "application_unraid_diagnostics.yaml").write_text(_SCHEMA_YAML, encoding="utf-8")
    schemas._sources.cache_clear()
    schemas.zip_signatures.cache_clear()
    schemas.load_mime_schema.cache_clear()
    schemas.mime_schema_id_for.cache_clear()
    return root


def _make_zip(tmp_path: Path, members: dict[str, bytes] | None = None) -> Path:
    zip_path = tmp_path / "diag.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in (members if members is not None else _MEMBERS).items():
            zf.writestr(name, data)
    return zip_path


def test_extension_for_plus_zip_suffix_is_agnostic():
    # No per-type entry in the shared table; the IANA `+zip` suffix drives the extension.
    assert mime.extension_for(_MIME) == "zip"
    assert mime.extension_for("application/vnd.whatever+json") == "json"


def test_detect_is_schema_driven(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = _make_zip(tmp_path)
    # With a corpus the schema-declared shape signature refines it; without one it's a raw zip.
    assert mime.detect(zip_path, root) == _MIME
    assert mime.detect(zip_path) == "application/zip"


def test_detect_falls_back_when_shape_absent(tmp_path):
    root = _make_corpus(tmp_path)
    # A zip lacking the telltale members stays a raw zip even with the schema present.
    plain = _make_zip(tmp_path, {"notes/readme.txt": b"hi"})
    assert mime.detect(plain, root) == "application/zip"


def test_resolve_member_re_derives_wrapper_root(tmp_path):
    zip_path = _make_zip(tmp_path)
    # The address is root-stripped; the helper finds the actual member under the wrapper.
    assert ziparchive.resolve_member(zip_path, "smart/sdb.txt") == b"SMART data for sdb"
    assert ziparchive.resolve_member(zip_path, "config/disk.cfg") == b"[disk]\nspindown=30\n"
    with pytest.raises(ValueError, match="no such member"):
        ziparchive.resolve_member(zip_path, "smart/nope.txt")


def test_path_transform_registered():
    handler = transforms.lookup("zip", "path")
    assert handler is not None
    assert handler.output_kind == "bytes"


def test_drafter_manifest_model(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = _make_zip(tmp_path)
    schema = schemas.load_mime_schema(root, _MIME)
    assert schema and schema.get("draft", {}).get("strategy") == "zip-manifest"

    build = recordbuild.begin({}, root)
    result = zip_draft(zip_path, build=build, corpus_root=root, mime_schema=schema)

    # Artifact fields: root becomes the title; member count covers ALL members.
    assert result["fields"]["title"] == "tower-diagnostics-20260622"
    assert result["fields"]["member_count"] == 4

    # EVERY member is an embed. Text is sniffed by content: .cfg is text/plain, not
    # octet-stream (the extension-detection bug this fixes). Only real binary is octet-stream.
    by_addr = {e["address"]: e for e in result["embeds"]}
    assert set(by_addr) == {
        "path=unraid-7.0.0.txt",
        "path=config/disk.cfg",
        "path=smart/sdb.txt",
        "path=logs/core.dat",
    }
    assert by_addr["path=config/disk.cfg"]["media_type"] == "text/plain"
    assert by_addr["path=logs/core.dat"]["media_type"] == "application/octet-stream"
    assert all(e["transport"].startswith("blake3:") for e in result["embeds"])

    # Content zone: marker segments for the atom'd (text) members; the binary core.dat has
    # NO segment (embed-only), so the binary-only `logs/` folder produces no section.
    blocks = build.blocks
    assert all(isinstance(b, segments.Section) for b in blocks)
    by_entry = {b.entry: b for b in blocks}
    assert set(by_entry) == {"(root)", "config", "smart"}

    # NOTHING is inlined — every marker is a body-empty `text` segment.
    all_segs = [s for b in blocks for s in b.segments]
    assert {s.address for s in all_segs} == {
        "path=unraid-7.0.0.txt",
        "path=config/disk.cfg",
        "path=smart/sdb.txt",
    }
    assert all(s.atom == "text" and s.body == "" for s in all_segs)

    # The built content zone re-parses cleanly (grammar-valid).
    recordbuild.finish(build)


def test_drafter_flat_sectioning(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = _make_zip(tmp_path)
    schema = schemas.load_mime_schema(root, _MIME)
    manifest = {**schema["draft"]["manifest"], "sectioning": "flat"}
    schema = {**schema, "draft": {**schema["draft"], "manifest": manifest}}

    build = recordbuild.begin({}, root)
    zip_draft(zip_path, build=build, corpus_root=root, mime_schema=schema)

    # Flat: top-level marker Segments, each labelled by its relpath.
    assert all(isinstance(b, segments.Segment) for b in build.blocks)
    entries = {b.entry for b in build.blocks}
    assert entries == {"unraid-7.0.0.txt", "config/disk.cfg", "smart/sdb.txt"}


def test_path_resolves_member_bytes_end_to_end(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = _make_zip(tmp_path)
    from corpus import hashing

    rid = hashing.hash_file(zip_path)["blake3"]
    LocalArtifactStore(root).put(rid, "zip", zip_path)
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "status": "draft", "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(post, mime=_MIME, fields={})
    records.dump(post, paths.record_path(root, rid))

    # working_kind: zip (schema) + the path= transform materialize the member bytes.
    out = resolver.resolve(f"corpus://{rid}?path=config/disk.cfg", root)
    assert out.read_bytes() == b"[disk]\nspindown=30\n"
    assert out.read_bytes() == ziparchive.resolve_member(zip_path, "config/disk.cfg")


def test_drafter_empty_archive_issue(tmp_path):
    root = _make_corpus(tmp_path)
    empty = _make_zip(tmp_path, {})
    schema = schemas.load_mime_schema(root, _MIME)
    build = recordbuild.begin({}, root)
    result = zip_draft(empty, build=build, corpus_root=root, mime_schema=schema)
    assert result["issues"] and result["issues"][0]["id"] == "partial-content"
    assert result["issues"][0]["severity"] == "blocking"


def test_is_text_and_media_atom_helpers():
    from corpus.draft.zip_manifest import _classify, _is_text

    assert _is_text(b"plain config\nkey=value\n")
    assert not _is_text(b"\x00\x01\x02")  # NUL -> binary
    assert _classify("x.cfg", b"key=value")[1] == "text"  # content sniff beats extension
    assert _classify("x.png", b"\x89PNG\r\n\x1a\n\x00")[1] == "image"
    assert _classify("x.bin", b"\x00\xff")[1] is None  # opaque binary -> no atom
