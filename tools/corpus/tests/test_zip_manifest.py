"""zip-manifest drafter + schema-driven zip detection + the `path=` member transform.

A zip member is a transport (a file with its own bytes + MIME), not a content atom, so the
drafter records each member as an embed (an embedded transport) in the metadata zone and
leaves the content zone empty — bytes resolve via `path=`, the hierarchy lives in the
addresses. The MIME schema is mechanical only (detect + self_contained + drafter); vendor
identity is a `classify_when` classification overlay filled by the normalizer.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import frontmatter
import pytest

from corpus import (
    classify_rules,
    lint,
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

# Mechanical MIME schema only: detect + self_contained + zip-manifest. No vendor identity.
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
"""

# The codex-layer identity overlay: auto-applies on the MIME; fields are normalizer-filled.
_COMPOSITE_BASE = "class_id: unraid\nkind: interpretive\napplies_at: [record]\n"
_COMPOSITE_SUB = """\
class_id: unraid/diagnostic-package
kind: interpretive
applies_at: [record]
classify_when:
  mime: { equals: application/vnd.unraid.diagnostics+zip }
extended_fields:
  unraid_version: {type: string, required: false, source: body, description: OS version.}
"""

_ROOT = "tower-diagnostics-20260622/"
_MEMBERS = {
    f"{_ROOT}unraid-7.0.0.txt": b"Unraid version 7.0.0\n",
    f"{_ROOT}config/disk.cfg": b"[disk]\nspindown=30\n",  # text-by-content (not octet-stream!)
    f"{_ROOT}smart/sdb.txt": b"SMART data for sdb",
    f"{_ROOT}logs/core.dat": b"\x00\x01\x02\x03\x00bin",  # binary (NUL)
}


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    mime_dir = root / "schema" / "mime" / "application"
    mime_dir.mkdir(parents=True)
    (mime_dir / "application_unraid_diagnostics.yaml").write_text(_SCHEMA_YAML, encoding="utf-8")
    comp_dir = root / "schema" / "composite" / "unraid"
    comp_dir.mkdir(parents=True)
    (comp_dir / "unraid.yaml").write_text(_COMPOSITE_BASE, encoding="utf-8")
    (comp_dir / "diagnostic-package.yaml").write_text(_COMPOSITE_SUB, encoding="utf-8")
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
    assert mime.extension_for(_MIME) == "zip"
    assert mime.extension_for("application/vnd.whatever+json") == "json"


def test_detect_is_schema_driven(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = _make_zip(tmp_path)
    assert mime.detect(zip_path, root) == _MIME
    assert mime.detect(zip_path) == "application/zip"


def test_detect_falls_back_when_shape_absent(tmp_path):
    root = _make_corpus(tmp_path)
    plain = _make_zip(tmp_path, {"notes/readme.txt": b"hi"})
    assert mime.detect(plain, root) == "application/zip"


def test_resolve_member_re_derives_wrapper_root(tmp_path):
    zip_path = _make_zip(tmp_path)
    assert ziparchive.resolve_member(zip_path, "smart/sdb.txt") == b"SMART data for sdb"
    assert ziparchive.resolve_member(zip_path, "config/disk.cfg") == b"[disk]\nspindown=30\n"
    with pytest.raises(ValueError, match="no such member"):
        ziparchive.resolve_member(zip_path, "smart/nope.txt")


def test_path_transform_registered():
    handler = transforms.lookup("zip", "path")
    assert handler is not None
    assert handler.output_kind == "bytes"


def test_media_type_content_sniff():
    from corpus.draft.zip_manifest import _is_text, _media_type

    assert _is_text(b"plain config\nkey=value\n")
    assert not _is_text(b"\x00\x01\x02")  # NUL -> binary
    assert _media_type("x.cfg", b"key=value") == "text/plain"  # content beats extension
    assert _media_type("x.json", b'{"a":1}') == "application/json"  # precise guess kept
    assert _media_type("x.dat", b"\x00\xff") == "application/octet-stream"  # opaque binary


def test_drafter_is_embeds_only(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = _make_zip(tmp_path)
    schema = schemas.load_mime_schema(root, _MIME)
    build = recordbuild.begin({}, root)
    result = zip_draft(zip_path, build=build, corpus_root=root, mime_schema=schema)

    assert result["fields"]["title"] == "tower-diagnostics-20260622"  # wrapper-dir fallback
    assert result["fields"]["member_count"] == 4

    # NO content zone — members are transports (embeds), not content atoms.
    assert build.blocks == []

    # EVERY member is an embed; .cfg sniffs to text/plain, only real binary is octet-stream.
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

    # No vendor identity on the artifact block — that's the classification overlay's job.
    assert "unraid_version" not in result["fields"]
    recordbuild.finish(build)


def test_generic_zip_fields(tmp_path):
    root = _make_corpus(tmp_path)
    zip_path = tmp_path / "d.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.comment = b"diag bundle"
        zf.writestr("ecba-diagnostics-20260101-0000/unraid-7.0.0.txt", b"x" * 2000)
        zf.writestr("ecba-diagnostics-20260101-0000/smart/sdb.txt", b"y" * 2000)
    schema = schemas.load_mime_schema(root, _MIME)
    build = recordbuild.begin({}, root)
    fields = zip_draft(zip_path, build=build, corpus_root=root, mime_schema=schema)["fields"]
    assert fields["compression"] == "deflate"
    assert fields["comment"] == "diag bundle"
    assert fields["uncompressed_bytes"] == 4000
    assert 0 < fields["compressed_bytes"] < fields["uncompressed_bytes"]
    assert "encrypted" not in fields  # nothing is encrypted


def test_embed_unreferenced_relaxed_for_manifest():
    # A manifest record (embeds, no content-zone segments) must NOT flag embed-unreferenced.
    post = frontmatter.Post("")
    post.metadata["_embeds"] = [
        {
            "media_type": "text/plain",
            "address": "path=a.txt",
            "transport": "blake3:" + "0" * 64,
            "fields": {},
        }
    ]
    assert list(lint._rule_embed_unreferenced(post, [], None)) == []
    # But with a segment present, an unreferenced embed IS still flagged.
    seg = segments.Segment(atom="text", address="path=other", body="x")
    findings = list(lint._rule_embed_unreferenced(post, [seg], None))
    assert findings and findings[0].rule_id == "embed-unreferenced"


def test_body_empty_normalized_relaxed_for_manifest():
    # A normalized manifest (empty content zone + embeds) must NOT flag body-empty-normalized.
    post = frontmatter.Post("")
    post.metadata["status"] = "normalized"
    post.metadata["_embeds"] = [
        {
            "media_type": "text/plain",
            "address": "path=a.txt",
            "transport": "blake3:" + "0" * 64,
            "fields": {},
        }
    ]
    assert list(lint._rule_body_empty_normalized(post, [], None)) == []
    # But a normalized record empty of BOTH content and embeds is still flagged.
    bare = frontmatter.Post("")
    bare.metadata["status"] = "normalized"
    findings = list(lint._rule_body_empty_normalized(bare, [], None))
    assert findings and findings[0].rule_id == "body-empty-normalized"


def test_vendor_identity_is_a_classify_overlay(tmp_path):
    # The mechanical MIME identifies the type; the codex-layer composite auto-applies on it.
    root = _make_corpus(tmp_path)
    post = frontmatter.Post("")
    post.metadata.update({"id": "a" * 64, "status": "draft"})
    records.set_artifact_block(post, mime=_MIME, fields={})
    classify_rules.apply_auto_classifications(root, post)
    assert "unraid/diagnostic-package" in classify_rules.auto_class_ids(post)


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
