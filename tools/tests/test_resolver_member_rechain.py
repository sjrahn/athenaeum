"""Container-member re-chaining through `path=` (spec §6.2, defects 3+4).

Defects: (3) `corpus resolve '...?path=<member>.json' --print` emitted a `.bin` cache path for
a JSON container member instead of streaming the JSON text — the extracted member always
resolved to the registry's generic opaque `bytes` kind, no matter what it actually was. (4) a
further op past `path=` on a real PDF member (`path=<member>.pdf&page=1&text`) failed with
`transform "page" not applicable to working kind "bytes"` — an extracted member never
re-entered the working-kind table, so it could never chain further.

Fix: `resolver._rechain_member` re-detects an extracted member's mime (`mime.sniff_head`,
already built for exactly this "bytes arrived as a stream, no seekable central directory"
case) once `path=` yields the registry's opaque `bytes`, and re-enters `_working_kind_for`.
When a further param follows in the chain, the member gets the SAME pipeline a standalone
record of its type would (a PDF member takes `page=`/`text`); a bare (terminal) `path=` never
promotes to a full pipeline object (that would silently re-encode an image member, say) — it
only decodes an already-textual member (JSON/text) to plain text. An unrecognized member (no
registered working kind, not textual) stays raw `bytes`, byte-identical to today.
"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

import frontmatter
import pytest

from corpus import functional_uri as furi
from corpus import hashing, paths, records, resolver, schemas, ziparchive
from corpus import mime as mime_mod
from corpus.store import LocalArtifactStore

_BORN_TEXT_PDF = Path(__file__).parent / "data" / "born_text.pdf"
_PDF_BYTES = _BORN_TEXT_PDF.read_bytes()
_JSON_MEMBER = b'{"caption": "a photo", "n": 3}'
# An unrecognized binary member: no magic signature, no textual extension — stays opaque
# `bytes` (today's behavior, unchanged).
_UNKNOWN_MEMBER = b"\x00\x01\xfe\xfd" + bytes(range(200))


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
    schemas.cache_clear()
    return root


def _stage_record(root: Path, data: bytes, *, mime: str, name: str) -> str:
    """Stage `data` as a standalone record under `mime`, bypassing ingest/draft — the
    resolver only needs the artifact block + bytes (mirrors `test_csv_transform.py`)."""
    src = root.parent / name
    src.write_bytes(data)
    rid = hashing.hash_file(src)["blake3"]
    ext = mime_mod.extension_for(mime)

    LocalArtifactStore(root).put(rid, ext, src)
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(
        post, snapshot="2026-07-18T00:00:00Z", fields={"filename": name, "source_modified": ""}
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


def _zip_with(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _tar_with(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


_ZIP_MEMBERS = {
    "born_text.pdf": _PDF_BYTES,
    "sidecar.json": _JSON_MEMBER,
    "unknown.bin": _UNKNOWN_MEMBER,
}


def _zip_record(root: Path) -> str:
    return _stage_record(root, _zip_with(_ZIP_MEMBERS), mime="application/zip", name="export.zip")


# ---------- defect 4: a PDF member chains page=/text past path= ---------- #


def test_pdf_member_takes_page_and_text_past_path(tmp_path):
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    out = resolver.resolve(f"corpus://{rid}?path=born_text.pdf&page=1&text", root)
    assert out.suffix == ".txt"
    assert "Hello born-digital vector text" in out.read_text("utf-8")


def test_pdf_member_page_render_terminal_still_works(tmp_path):
    """A bare `page=N` after `path=` (no `&text`) still auto-renders to an image, exactly as
    a top-level PDF record's `page=N` does."""
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    out = resolver.resolve(f"corpus://{rid}?path=born_text.pdf&page=1", root)
    assert out.suffix == ".png"
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_pdf_member_extraction_is_cached_and_reused_across_pages(tmp_path):
    """The member's own bytes are materialized once (cached under the prefix URI up to
    `path=`, engine-folded), so a second op over the SAME member never re-extracts from
    the zip — and an `archive-path@1` bump invalidates the staging file rather than
    serving pre-bump bytes into a re-chained continuation."""
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    resolver.resolve(f"corpus://{rid}?path=born_text.pdf&page=1&text", root)
    partial = furi.canonical(furi.parse(f"corpus://{rid}?path=born_text.pdf"))
    staging_key = f"{partial}|engine={ziparchive.ENGINE_VERSION}"
    member_cache = furi.cache_path(root, furi.urihash(staging_key), "pdf")
    assert member_cache.is_file()
    # the un-folded key must NOT be where the bytes live — that was the stale-serve gap
    assert not furi.cache_path(root, furi.urihash(partial), "pdf").is_file()
    assert member_cache.read_bytes() == _PDF_BYTES

    out2 = resolver.resolve(f"corpus://{rid}?path=born_text.pdf&page=2&text", root)
    assert out2.suffix == ".txt"  # page 2 resolves fine too, from the SAME cached member


def test_pdf_member_sidecar_mime_is_the_default_text_mime(tmp_path):
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    out = resolver.resolve(f"corpus://{rid}?path=born_text.pdf&page=1&text", root)
    sidecar = furi.cache_sidecar_path(out)
    assert json.loads(sidecar.read_text("utf-8"))["mime"] == "text/plain"


# ---------- defect 3: a JSON member prints as text instead of a `.bin` path ---------- #


def test_json_member_resolves_as_json_not_bin(tmp_path):
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    out = resolver.resolve(f"corpus://{rid}?path=sidecar.json", root)
    assert out.suffix == ".json"
    assert json.loads(out.read_text("utf-8")) == json.loads(_JSON_MEMBER)


def test_json_member_sidecar_mime_is_application_json(tmp_path):
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    out = resolver.resolve(f"corpus://{rid}?path=sidecar.json", root)
    sidecar = furi.cache_sidecar_path(out)
    assert json.loads(sidecar.read_text("utf-8"))["mime"] == "application/json"


# ---------- unrecognized members stay opaque bytes, byte-identical (unchanged) ---------- #


def test_unrecognized_member_stays_bytes_byte_identical(tmp_path):
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    out = resolver.resolve(f"corpus://{rid}?path=unknown.bin", root)
    assert out.suffix == ".bin"
    assert out.read_bytes() == _UNKNOWN_MEMBER


def test_unrecognized_member_with_a_following_op_raises_clear_error(tmp_path):
    """A member with no registered working kind can't chain further — a clear error, never a
    crash (parse-tolerant, spec house doctrine)."""
    root = _corpus(tmp_path)
    rid = _zip_record(root)
    with pytest.raises(ValueError, match="not applicable to working kind 'bytes'"):
        resolver.resolve(f"corpus://{rid}?path=unknown.bin&bbox=0,0,1,1", root)


# ---------- an image member alone is NEVER silently re-encoded (stays raw bytes) ---------- #


def test_image_member_alone_stays_raw_bytes_never_reencoded(tmp_path):
    """A bare (terminal) `path=` on an image member must NOT promote to a full image pipeline
    object — that would silently re-encode the member's bytes (e.g. JPEG -> PNG), which
    `resolve` was never asked to do. `transforms/zip.py`'s documented contract (raw bytes,
    verbatim) holds for a terminal `path=` regardless of the member's real mime — the cache
    extension carries the member's own sniffed type (the extension-asymmetry fix, §6.2), but
    the BYTES are untouched, never re-encoded through an image pipeline."""
    root = _corpus(tmp_path)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"FAKEPNGDATA" * 4
    rid = _stage_record(
        root, _zip_with({"photo.png": png_bytes}), mime="application/zip", name="photos.zip"
    )
    out = resolver.resolve(f"corpus://{rid}?path=photo.png", root)
    assert out.suffix == ".png"  # sniffed extension, not the generic bytes-kind `.bin`
    assert out.read_bytes() == png_bytes  # byte-identical — never PNG-re-encoded


# ---------- the same mechanism applies to tar/tgz (the other kept-whole archive family) ---#


def test_json_member_in_tar_resolves_as_json_too(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_record(
        root, _tar_with({"data.json": _JSON_MEMBER}), mime="application/x-tar", name="export.tar"
    )
    out = resolver.resolve(f"corpus://{rid}?path=data.json", root)
    assert out.suffix == ".json"
    assert json.loads(out.read_text("utf-8")) == json.loads(_JSON_MEMBER)


def test_pdf_member_in_tar_takes_page_and_text(tmp_path):
    root = _corpus(tmp_path)
    rid = _stage_record(
        root, _tar_with({"doc.pdf": _PDF_BYTES}), mime="application/x-tar", name="export2.tar"
    )
    out = resolver.resolve(f"corpus://{rid}?path=doc.pdf&page=1&text", root)
    assert "Hello born-digital vector text" in out.read_text("utf-8")


# ---------- functional-URI grammar / predicted-kind plumbing ---------- #


def test_bare_path_on_zip_predicts_memberchain_sentinel_internally(tmp_path):
    """Not a public contract, but pins the internal deferred-kind mechanism (mirrors the
    `htmlel`/`video`/`audio`/`media` precedent) so a regression here fails loudly here rather
    than as a confusing downstream RuntimeError."""
    parsed = furi.parse("corpus://" + "a" * 64 + "?path=x.pdf&page=1&text")
    assert resolver._predict_final_kind(parsed, "zip") == "memberchain"
