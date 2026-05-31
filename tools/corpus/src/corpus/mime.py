"""Minimal MIME detection.

Strategy: sniff the file's magic bytes for known signatures; otherwise fall back to
extension via `mimetypes`. Returns `unknown` if both fail.

Zip-shaped files (xlsx, docx, pptx, epub, jar, raw zip) all share the `PK\\x03\\x04`
magic. After matching the zip signature we peek inside the central directory for
telltale member paths to refine — `xl/workbook.xml` → xlsx, `word/document.xml` →
docx, etc. Files that don't match any refinement signature stay tagged `application/zip`.
"""

from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path

# Register newline-delimited JSON so extension-based fallback finds it.
# JSONL has no canonical magic-byte signature, so detection relies on the
# `.jsonl` / `.ndjson` filename suffix.
mimetypes.add_type("application/x-ndjson", ".jsonl")
mimetypes.add_type("application/x-ndjson", ".ndjson")

# Magic-byte signatures: (offset, prefix_bytes, mime).
_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"%PDF-", "application/pdf"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"RIFF", "image/webp"),
    # AVIF: ISOBMFF container with the `ftyp` box brand `avif` at offset 4.
    (4, b"ftypavif", "image/avif"),
    # Video ISOBMFF brands.
    (4, b"ftypisom", "video/mp4"),
    (4, b"ftypmp42", "video/mp4"),
    (4, b"ftypmp41", "video/mp4"),
    (4, b"ftypM4V ", "video/mp4"),
    (4, b"ftypdash", "video/mp4"),
    (4, b"ftypqt  ", "video/quicktime"),
    # WebM and Matroska share an EBML header. Distinguishing them needs a deeper
    # sniff (the DocType element); for v1 we report `video/webm` for both.
    (0, b"\x1aE\xdf\xa3", "video/webm"),
    (0, b"PK\x03\x04", "application/zip"),  # refined below
    (0, b"ID3", "audio/mpeg"),
    (0, b"\xff\xfb", "audio/mpeg"),
)


_SNIFF_BYTES = 16


def detect(path: Path) -> str:
    """Return the IANA MIME type, or `unknown`."""
    with path.open("rb") as fh:
        head = fh.read(_SNIFF_BYTES)

    for offset, prefix, mime in _SIGNATURES:
        if head[offset : offset + len(prefix)] == prefix:
            if mime == "application/zip":
                return _refine_zip(path)
            return mime

    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "unknown"


# Telltale central-directory member paths that distinguish a structured zip-shaped
# container from a raw zip. Checked in order; first match wins.
_ZIP_SIGNATURES: tuple[tuple[str, str], ...] = (
    (
        "xl/workbook.xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    (
        "word/document.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    (
        "ppt/presentation.xml",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ("META-INF/container.xml", "application/epub+zip"),
    ("META-INF/MANIFEST.MF", "application/java-archive"),
)


def _refine_zip(path: Path) -> str:
    """A `PK\\x03\\x04` file may be a structured container (xlsx, docx, etc.).
    Open the zip's central directory and check for telltale member paths."""
    try:
        with zipfile.ZipFile(path) as zf:
            members = set(zf.namelist())
    except zipfile.BadZipFile:
        return "application/zip"
    for sig_path, mime in _ZIP_SIGNATURES:
        if sig_path in members:
            return mime
    return "application/zip"


def extension_for(mime: str, *, fallback: str = "bin") -> str:
    """Pick a sensible filename extension for `mime`. The artifact cache stores binaries
    as `{hash}.{ext}` purely for tooling convenience — identity is the hash, not the
    extension."""
    canonical = {
        "application/pdf": "pdf",
        "text/html": "html",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/avif": "avif",
        "audio/mpeg": "mp3",
        "video/mp4": "mp4",
        "video/webm": "webm",
        "video/quicktime": "mov",
        "video/x-matroska": "mkv",
        "application/zip": "zip",
        "application/x-ndjson": "jsonl",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-excel.sheet.macroEnabled.12": "xlsm",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/epub+zip": "epub",
        "application/java-archive": "jar",
    }
    if mime in canonical:
        return canonical[mime]

    guessed = mimetypes.guess_extension(mime) or ""
    return guessed.lstrip(".") or fallback
