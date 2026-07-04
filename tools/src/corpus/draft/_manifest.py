"""Shared core for the archive embed-manifest drafters (`zip_manifest`, `tar_manifest`).

A raw archive drafts as an **embed manifest** (spec §1.2, §12.4): every member is a
transport (its own bytes + MIME), so every member becomes an embed (`transport` = blake3
of the member bytes, `media_type` content-sniffed, address `path=<relpath>`) and the
content zone stays empty. The two archive families (zip and tar/tgz) differ only in how a
member is opened; the per-member modeling — the streaming digest+text sniff, the
content-over-extension media-type verdict, the empty-archive issue — is identical and
lives here so both drafters (and the promote/containment streaming path) share one core.
"""

from __future__ import annotations

import codecs
import mimetypes
from typing import IO, Any

import blake3

# Stream members in 1 MiB chunks so a multi-GB member is never held in RAM all at once.
_CHUNK = 1 << 20


def digest_and_text(fp: IO[bytes]) -> tuple[str, bool]:
    """Stream a member's bytes once through `fp` — blake3 transport digest + a text/binary
    sniff — without materializing it whole (an archive can hold multi-GB members). Text is
    decided over the full bytes (no NUL byte, valid UTF-8), the same verdict as a whole-member
    read, using an incremental decoder so a multibyte char split across a chunk boundary isn't
    misread. A non-UTF-8 text encoding (rare on the Linux bundles this targets) reads as binary.
    The caller owns opening/closing `fp` (and any encrypted-member `RuntimeError` it raises)."""
    b3 = blake3.blake3()
    decoder = codecs.getincrementaldecoder("utf-8")()
    is_text = True
    while chunk := fp.read(_CHUNK):
        b3.update(chunk)
        if is_text:
            if b"\x00" in chunk:
                is_text = False
            else:
                try:
                    decoder.decode(chunk)
                except UnicodeDecodeError:
                    is_text = False
    if is_text:
        try:
            decoder.decode(b"", final=True)  # a truncated trailing multibyte → not text
        except UnicodeDecodeError:
            is_text = False
    return b3.hexdigest(), is_text


def media_type(rel: str, is_text: bool) -> str:
    """The member's MIME — and, since the embed carries it, the text-vs-binary distinction.
    Text is decided by **content** (UTF-8, no NULs — see `digest_and_text`), not extension,
    so a `.cfg`/`.conf`/extensionless config or log is `text/plain` rather than misclassified
    binary; a precise extension guess (`application/json`, `image/png`) is kept; an opaque
    binary is `application/octet-stream`."""
    guessed = mimetypes.guess_type(rel)[0]
    if is_text:
        return guessed or "text/plain"
    return guessed or "application/octet-stream"


def partial_content_issue(detector: str, description: str) -> dict[str, Any]:
    """A blocking `partial-content` issue — an unreadable archive, or one with no files. A
    manifest record with no members has no content zone AND no embeds, so surface it rather
    than shipping a silently-empty record (spec §12.4)."""
    return {
        "id": "partial-content",
        "subtype": "empty-body",
        "severity": "blocking",
        "resolution": "open",
        "detector": detector,
        "fields": {"description": description},
    }
