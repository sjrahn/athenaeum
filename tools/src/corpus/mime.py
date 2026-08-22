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
import re
import zipfile
from pathlib import Path

# Register newline-delimited JSON so extension-based fallback finds it.
# JSONL has no canonical magic-byte signature, so detection relies on the
# `.jsonl` / `.ndjson` filename suffix.
mimetypes.add_type("application/x-ndjson", ".jsonl")
mimetypes.add_type("application/x-ndjson", ".ndjson")
# A single RFC822 email message. Detected by header shape (below); the `.eml` suffix names
# it for the extension fallback (not registered by default on every platform).
mimetypes.add_type("message/rfc822", ".eml")
# vCard address-book export. Some platforms' mimetypes map `.vcf` to the legacy
# `text/x-vcard`; pin it to the RFC 6350 canonical so ingest + the zip member index agree.
mimetypes.add_type("text/vcard", ".vcf")
mimetypes.add_type("text/vcard", ".vcard")
# The codec-derived leaf mimes a promoted media-stream track carries (spec §2, v32): the
# raw codec payload, concatenated sample bytes with NO reframing of any kind — no ADTS
# header, no Annex-B start codes, no corpus-invented framing. A bare payload of any of
# these has no reliable magic-byte signature of its own (that is exactly what "not
# reframed" means), so `corpus promote`'s leaf mime comes from the container's own codec
# probe (`corpus.streams.probe_streams`), never from sniffing the payload bytes — these
# extension registrations exist only for `mime.extension_for`'s cache-file naming and for
# a standalone file dropped in under one of these extensions.
mimetypes.add_type("video/h264", ".h264")
mimetypes.add_type("video/hevc", ".h265")
mimetypes.add_type("video/av1", ".av1")
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/opus", ".opus")

# Magic-byte signatures: (offset, prefix_bytes, mime).
_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"%PDF-", "application/pdf"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    # TIFF, both byte orders. Covers the TIFF-based camera-RAW family too (DNG — Apple
    # ProRAW export attachments among them): DNG IS TIFF, and the codebase already names
    # the family `image/tiff` (epub + html embed tables), so no `x-` type is invented.
    (0, b"II*\x00", "image/tiff"),
    (0, b"MM\x00*", "image/tiff"),
    # NOTE: RIFF containers (WebP / WAV / AVI) all share the `RIFF` magic at offset 0;
    # they are disambiguated by the four-byte form-type at offset 8 — see `_refine_riff`.
    # AVIF: ISOBMFF container with the `ftyp` box brand `avif` at offset 4.
    (4, b"ftypavif", "image/avif"),
    # HEIF stills, same box family: `heic`/`heix` are the HEVC-coded brands (iPhone
    # photos), `mif1` the codec-agnostic structural brand.
    (4, b"ftypheic", "image/heic"),
    (4, b"ftypheix", "image/heic"),
    (4, b"ftypmif1", "image/heif"),
    # Audio ISOBMFF brands (M4A/M4B audiobooks). Checked before the generic video brands
    # so a correctly-branded audio-in-MP4 file routes to the audio pipeline. Generic
    # `isom`/`mp42`-branded audiobooks (most `.m4b` files lie about their brand) are caught
    # by the extension refinement in `detect` — see `_refine_isobmff`.
    (4, b"ftypM4A ", "audio/mp4"),
    (4, b"ftypM4B ", "audio/mp4"),
    # Video ISOBMFF brands.
    # The 7-byte `3gp` prefix covers every 3GPP generation brand (3gp4/3gp5/3gp6…) —
    # MMS-era phone videos in the export captures.
    (4, b"ftyp3gp", "video/3gpp"),
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
    # ADTS AAC sync word + fixed header (12-bit sync `1111 1111 1111`, ID=0/MPEG-4, layer=00,
    # protection_absent=1/no-CRC) — `\xff\xf1` exactly, the standard ADTS "MPEG-4, no CRC"
    # prefix. A promoted media-stream leaf's own bytes (v32, §2) never carry this — the raw
    # payload is deliberately NOT ADTS-framed — so this signature exists solely to recognize an
    # ordinary standalone `.aac` file dropped into the corpus, unrelated to track promotion.
    # Distinct from the MP3 signature above (`\xff\xfb` has layer bits that ADTS never sets).
    (0, b"\xff\xf1", "audio/aac"),
    # Uncompressed tar (POSIX ustar / GNU): the `ustar` magic sits at offset 257 (inside the
    # first member header). A gzip-wrapped tar (`.tgz`) hides this behind gzip magic and is
    # refined by `_refine_gzip`. The tar family drafts as an embed manifest (spec §12.4).
    (257, b"ustar", "application/x-tar"),
    # mbox mailbox: every message begins with a `From ` envelope line, and the archive opens
    # with one. Its messages are declared + promotable per `msg=<N>` (spec §12.11); a message
    # promoted out of it is `message/rfc822` (detected by header shape below).
    (0, b"From ", "application/mbox"),
    # vCard address book: every file opens with the `BEGIN:VCARD` delimiter. Confirms the type
    # for an extension-less drop; a BOM-prefixed file falls through to the `.vcf` extension.
    (0, b"BEGIN:VCARD", "text/vcard"),
    # ZIM archive (Kiwix reference-dataset mirrors, ledger.md §6.5): the openZIM magic
    # number 0x044D495A little-endian — "ZIM\x04" at offset 0. Verified against the
    # deployment's real Kiwix downloads.
    (0, b"ZIM\x04", "application/x-openzim"),
    # OSM PBF extract (Geofabrik mirrors): no formal magic, but the leading BlobHeader is
    # in practice a 4-byte big-endian length followed by protobuf field 1 (`\x0a`), length
    # 9, "OSMHeader" — stable across osmium-produced files, verified against the real
    # Canada extract. The `.pbf` extension alone would also resolve via mimetypes below.
    (4, b"\x0a\x09OSMHeader", "application/x-osm+pbf"),
)


# 512 bytes so the tar `ustar` magic at offset 257 is inside the sniff window.
_SNIFF_BYTES = 512

# message/rfc822 (a single email message, typically a promoted mbox `msg=<N>`) has no magic
# number — it opens with RFC5322 headers. Two tiers keep false positives off ordinary text:
#   • STRONG, distinctively-email header prefixes → confident even with no extension (the
#     path a promoted message takes: its basename is the bare ordinal, so no `.eml` hint).
#   • a WEAK "first two lines are header-shaped" fallback, applied only AFTER the extension
#     hint (so a `.yaml`/`.txt` whose first lines look like `key: value` isn't shadowed).
# The mbox separator `From ` (a SPACE, matched by `_SIGNATURES` at offset 0) always wins
# first — an mbox opens with the separator, an eml never does.
_EML_STRONG_PREFIXES: tuple[bytes, ...] = (
    b"Return-Path:",
    b"Delivered-To:",
    b"Received:",
    b"X-GM-THRID",
    b"DKIM-Signature:",
    b"ARC-Seal:",
    b"Message-ID:",
    b"MIME-Version:",
)
# An RFC5322 header field-name is printable ASCII except space and colon (33-57, 59-126),
# followed by a colon and at least one space/tab.
_EML_HEADER_RE = re.compile(rb"^[\x21-\x39\x3b-\x7e]+:[ \t]")

# SVG's root element and the prologue forms that may precede it — see `_looks_like_svg`.
# The root pattern requires a delimiter after the tag name so `<svgfoo>` is not an `<svg>`.
_SVG_ROOT_RE = re.compile(r"<svg[\s>/]", re.I)
_SVG_PROLOGUE_PREFIXES = ("<?xml", "<!doctype svg", "<!--")
_XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_FIRST_ELEMENT_RE = re.compile(r"<([A-Za-z][A-Za-z0-9-]*)")


def detect(path: Path, corpus_root: Path | None = None) -> str:
    """Return the IANA MIME type, or `unknown`.

    `corpus_root`, when given, lets a zip-shaped artifact be refined against the corpus's
    schema-declared zip signatures (`applies_to.zip_members` / `zip_member_patterns`) — so
    a corpus recognizes its own zip-shaped types (a diagnostics export, a backup bundle)
    without editing this package. Absent it, only the built-in universal signatures apply.
    """
    with path.open("rb") as fh:
        head = fh.read(_SNIFF_BYTES)

    # gzip magic is refined by peeking inside — a gzip wrapping a tar is a `.tgz` (spec §12.4).
    if head[0:2] == b"\x1f\x8b":
        return _refine_gzip(path)

    sig = _scan_signatures(head)
    if sig == "application/zip":
        return _refine_zip(path, corpus_root)
    if sig in ("video/mp4", "video/quicktime"):
        return _refine_isobmff(path, sig)
    if sig:
        return sig

    # Before the extension fallback: bytes evidence outranks a filename heuristic (see
    # `_looks_like_svg`).
    if _looks_like_svg(head):
        return "image/svg+xml"

    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    # Last resort before `unknown`: the weak email-header shape (runs after the extension
    # hint, so it never shadows a recognized suffix).
    if _looks_like_message(head):
        return "message/rfc822"
    return "unknown"


def sniff_head(head: bytes, filename: str | None = None) -> str:
    """MIME from a byte prefix (+ optional filename) alone — the streaming counterpart of
    `detect` for a container member whose bytes arrive as a stream (promote, §8.1), where no
    seekable path is available for the zip central-directory / gzip decompress refinements.
    A zip-magic member refines WITHIN the family by its declared extension
    (`_ZIP_EXT_REFINEMENTS` — the directory sits at the end of a zip, out of a streamed
    head's reach); a bare or unrecognized name stays `application/zip`, and gzip stays
    generic. The magic-byte types the manifest members actually carry (mbox, pdf, images,
    json, …) resolve precisely."""
    if head[0:2] == b"\x1f\x8b":
        return "application/gzip"  # a streaming head can't cheaply confirm a wrapped tar
    sig = _scan_signatures(head)
    if sig in ("video/mp4", "video/quicktime"):
        return _isobmff_by_suffix(Path(filename).suffix if filename else "", sig)
    if sig == "application/zip" and filename:
        refined = _ZIP_EXT_REFINEMENTS.get(Path(filename).suffix.lower())
        if refined:
            return refined
    if sig:
        return sig
    if _looks_like_svg(head):
        return "image/svg+xml"
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    if _looks_like_message(head):
        return "message/rfc822"
    return "unknown"


def _scan_signatures(head: bytes) -> str | None:
    """Return the raw magic-byte type for `head` (before any path-based refinement), or None.
    Shared by `detect` (path available) and `sniff_head` (bytes only)."""
    if head[0:4] == b"RIFF":
        refined = _refine_riff(head)
        if refined:
            return refined
    for offset, prefix, mime in _SIGNATURES:
        if head[offset : offset + len(prefix)] == prefix:
            return mime
    # A distinctively-email header prefix (checked after the magic table, so mbox's `From `
    # separator and every binary magic win first) is a confident message/rfc822 signal.
    if head[:5] != b"From " and head.startswith(_EML_STRONG_PREFIXES):
        return "message/rfc822"
    return None


def _looks_like_message(head: bytes) -> bool:
    """The WEAK email-header test: the first TWO logical lines are header-shaped (or the
    second is a folded continuation). Two consecutive `field: value` lines is a far stronger
    signal than one, so an ordinary `key: value` config/text file doesn't trip it. Never
    fires for an mbox (its first line is the `From ` separator)."""
    if head[:5] == b"From ":
        return False
    lines = head.split(b"\n", 2)
    if len(lines) < 2 or not _EML_HEADER_RE.match(lines[0]):
        return False
    second = lines[1]
    return bool(_EML_HEADER_RE.match(second)) or second[:1] in (b" ", b"\t")


def _looks_like_svg(head: bytes) -> bool:
    """True when the head opens an SVG document.

    SVG cannot join `_SIGNATURES`: it has no magic at a fixed offset. The root element may
    be preceded by a BOM, an XML declaration, a doctype, comments, or plain whitespace, in
    any combination — so the test is a shape test on the decoded head, like
    `_looks_like_message`. Two tiers: the `<svg` root itself, or an XML prologue with the
    root reachable INSIDE the sniff window. A prologue alone is not enough — generic XML is
    not SVG, and a long DTD or comment banner can push the root past `_SNIFF_BYTES`.

    Runs BEFORE the extension fallback in both callers, unlike the weak email test: an
    inline `el=` member's synthesized basename is an element address, and `mimetypes` reads
    its trailing `.1` through `.9` as a man-page section (`application/x-troff-man`), so a
    filename-first order lets a non-name overrule the bytes."""
    text = head.decode("utf-8", errors="replace").lstrip("\ufeff").lstrip()
    if _SVG_ROOT_RE.match(text):
        return True
    if not text[:16].lower().startswith(_SVG_PROLOGUE_PREFIXES):
        return False
    # The FIRST element decides, not `<svg` anywhere in the window: HTML has no byte
    # signature of its own, so a comment-led page ("<!-- saved from url -->") or an
    # `<?xml`-prologue XHTML page with an early inline <svg> would otherwise be claimed
    # here before its extension can answer. Comments are stripped first so a `<` inside
    # a banner is not read as the first element.
    first = _FIRST_ELEMENT_RE.search(_XML_COMMENT_RE.sub("", text))
    return bool(first) and first.group(1).lower() == "svg"


def _refine_gzip(path: Path) -> str:
    """A gzip stream whose decompressed head is a tar (`ustar` magic at offset 257) is a
    `.tgz` → `application/x-tar` (one schema/drafter/transform serves plain and gzipped tar;
    `tarfile` auto-detects the compression). A gzip wrapping anything else stays the generic
    `application/gzip`. Peeks only the leading decompressed bytes, never the whole stream.
    A corrupt/truncated deflate stream raises `zlib.error` (not an `OSError` subclass,
    unlike `gzip.BadGzipFile`) — caught alongside the others so a malformed gzip-magic'd
    file still detects (as the generic type) rather than raising out of detection itself."""
    import gzip
    import zlib

    try:
        with gzip.open(path, "rb") as gz:
            inner = gz.read(_SNIFF_BYTES)
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error):
        return "application/gzip"
    if inner[257:262] == b"ustar":
        return "application/x-tar"
    return "application/gzip"


# Audio-in-MP4 extensions. Most `.m4b` audiobooks (and `.m4a` audio) carry a generic
# `isom`/`mp42` ISOBMFF brand that magic-sniffs as `video/mp4`, even when the file holds
# only an AAC audio stream (+ an optional cover-art `mjpeg`). The extension is the reliable
# signal that the container is audio, so it routes to the audio pipeline (transcription),
# not the video one (which would try to keyframe-section a cover image).
_ISOBMFF_AUDIO_EXTENSIONS = {".m4a", ".m4b"}


def _refine_isobmff(path: Path, video_mime: str) -> str:
    """Refine a generic-brand ISOBMFF `video/mp4` to `audio/mp4` when the filename
    extension marks it as audio (`.m4a`/`.m4b`). Otherwise keep the video MIME."""
    return _isobmff_by_suffix(path.suffix, video_mime)


def _isobmff_by_suffix(suffix: str, video_mime: str) -> str:
    """The suffix-only half of `_refine_isobmff`, shared with `sniff_head`."""
    if video_mime == "video/mp4" and suffix.lower() in _ISOBMFF_AUDIO_EXTENSIONS:
        return "audio/mp4"
    return video_mime


# RIFF form-types at offset 8 (the four bytes following `RIFF<4-byte size>`). WebP, WAV,
# and AVI all carry the `RIFF` magic; only the form-type tells them apart.
_RIFF_FORMS: tuple[tuple[bytes, str], ...] = (
    (b"WEBP", "image/webp"),
    (b"WAVE", "audio/x-wav"),
    (b"AVI ", "video/x-msvideo"),
)


def _refine_riff(head: bytes) -> str | None:
    """Disambiguate a `RIFF` container by its offset-8 form-type. Returns the MIME, or
    None for an unknown form (the caller then falls back to extension-based detection)."""
    form = head[8:12]
    for brand, mime in _RIFF_FORMS:
        if form == brand:
            return mime
    return None


# Telltale central-directory member paths that distinguish a structured zip-shaped
# container from a raw zip. Checked in order; first match wins.
# The zip family's package types by declared extension — `sniff_head`'s streaming stand-in
# for `_refine_zip`'s central-directory check. The magic confirms the FAMILY; the declared
# name refines the package within it. A lying extension surfaces at draft (parse-tolerant,
# the drafter finds no telltale members), never as a wrong byte identity.
_ZIP_EXT_REFINEMENTS: dict[str, str] = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".epub": "application/epub+zip",
    ".jar": "application/java-archive",
}

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


def _refine_zip(path: Path, corpus_root: Path | None = None) -> str:
    """A `PK\\x03\\x04` file may be a structured container (xlsx, docx, etc.).
    Open the zip's central directory and check for telltale member paths.

    Universal formats (OOXML / epub / jar — fixed internal layouts) match the built-in
    exact-path `_ZIP_SIGNATURES` first. When a `corpus_root` is supplied, zips whose
    telltale members sit under a variable wrapper directory are refined against the
    corpus's schema-declared signatures (`applies_to.zip_members` /
    `zip_member_patterns`) — keeping vendor/site-specific recognition in the overlay."""
    try:
        with zipfile.ZipFile(path) as zf:
            members = set(zf.namelist())
    except zipfile.BadZipFile:
        return "application/zip"
    # Exact-path signatures first (OOXML / epub / jar — universal, package-known layouts).
    for sig_path, mime in _ZIP_SIGNATURES:
        if sig_path in members:
            return mime
    # Corpus-declared shape signatures (overlay-driven; first match wins, deterministic).
    if corpus_root is not None:
        from corpus import schemas

        for content_type, exact, patterns in schemas.zip_signatures(corpus_root):
            if _zip_shape_matches(members, exact, patterns):
                return content_type
    return "application/zip"


def _zip_shape_matches(
    members: set[str], exact: tuple[str, ...], patterns: tuple[str, ...]
) -> bool:
    """A schema-declared zip signature matches when ANY declared exact member is present
    AND every declared pattern matches at least one member. (A signature declaring only
    patterns is pure-AND over the patterns; only exacts is pure-ANY over the exacts.)"""
    if exact and not any(m in members for m in exact):
        return False
    for pat in patterns:
        rx = re.compile(pat)  # patterns are pre-validated by schemas.zip_signatures
        if not any(rx.search(m) for m in members):
            return False
    return bool(exact or patterns)


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
        "audio/mp4": "m4a",
        "audio/x-wav": "wav",
        "video/mp4": "mp4",
        "video/webm": "webm",
        "video/quicktime": "mov",
        "video/x-matroska": "mkv",
        "video/x-msvideo": "avi",
        "application/zip": "zip",
        "application/x-tar": "tar",
        "application/mbox": "mbox",
        "application/x-ndjson": "jsonl",
        "message/rfc822": "eml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-excel.sheet.macroEnabled.12": "xlsm",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/epub+zip": "epub",
        "application/java-archive": "jar",
        # Reference-dataset mirror formats (§7.1 ref_adapter): without canonical entries
        # these fall through to the "bin" fallback, and every corpus-root-free
        # `extension_for(media_type)` caller (move, health) would derive a different
        # extension than ingest's source-suffix fallback wrote to disk.
        "application/x-openzim": "zim",
        "application/x-osm+pbf": "pbf",
        # Promoted media-stream leaves (spec §2, v32) — codec-derived raw-payload mimes.
        "video/h264": "h264",
        "video/hevc": "h265",
        "video/av1": "av1",
        "audio/aac": "aac",
        "audio/opus": "opus",
    }
    if mime in canonical:
        return canonical[mime]

    # IANA structured-suffix convention (`application/vnd.<x>+zip`, `…+xml`, `…+json`):
    # the suffix names the underlying serialization, so a corpus-specific zip-shaped type
    # gets a sensible extension without a per-type entry here (keeps this table agnostic).
    if "+" in mime:
        suffix = mime.rsplit("+", 1)[1].split(";", 1)[0].strip()
        suffix_ext = {"zip": "zip", "xml": "xml", "json": "json", "gzip": "gz"}.get(suffix)
        if suffix_ext:
            return suffix_ext

    guessed = mimetypes.guess_extension(mime) or ""
    return guessed.lstrip(".") or fallback


# ------- citation surface (§7.1 `citation_surface:` — ledger.md §6.3 / §13.2) ------- #

_SEGMENTS_SURFACE_MIMES = frozenset({
    "text/html",
    "application/xhtml+xml",
})


def citation_surface(media_type: str, corpus_root: Path | None = None) -> str:
    """The format's honest citation-surface class (§7.1): ``"segments"`` — the raw/derived
    whole-record text is presentation soup (nav chrome, script payloads), so the record is
    citable only once persisted segments exist — or ``"raw"`` (the default) — the derived
    body is faithful line-of-sight content and record-wide verbatim quotes are honest.
    Schema-first (the mime schema's `citation_surface:`), falling back to the built-in
    table: the HTML family is `segments`, every other bundled type `raw`. Consumed by
    ledger evidence verification and `corpus inspect`; governs citability only, never
    readability."""
    if corpus_root is not None:
        from . import schemas

        schema = schemas.load_mime_schema(corpus_root, media_type) or {}
        declared = schema.get("citation_surface")
        if declared in ("segments", "raw"):
            return declared
    return "segments" if media_type in _SEGMENTS_SURFACE_MIMES else "raw"
