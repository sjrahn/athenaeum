"""General `self_contained` zip → embed-manifest draft extraction (deterministic, no LLM).

The drafting analogue of overlay-driven capture: instead of a bespoke drafter per archive
format, ONE general drafter records a zip's members, and the *mime schema* opts in with
`draft.strategy: zip-manifest` (see `corpus.draft.register_strategy`); the drafter is
selected by that strategy, not the schema id, so it serves any number of self_contained zip
types (an Unraid diagnostics export, a config backup, a log bundle …).

This is for archives whose *unit of meaning is the whole bundle* — kept as one record
rather than decomposed into one record per member (`artifact_kind: decomposable`).
Genuinely structured zip formats (xlsx/docx/epub) keep their own specialized id-keyed
drafters; they never reach this code.

**A member is a TRANSPORT, not a content atom.** A zip member is a file — its own bytes and
its own MIME type — i.e. an *embedded transport*, which is exactly what an `<!--embed-->` is
(and why an embed carries a `media_type`). So **every member becomes an embed** (content-
sniffed `media_type`, blake3 `transport`, addressed `path=<rel>`) the normalizer describes,
and the **content zone is empty**: a pure container has no content atoms of its own, and a
member's bytes are verbatim + resolvable via `corpus://<id>?path=<rel>`, so nothing is
transcribed. The folder hierarchy lives in the `path=` addresses (a tree is a derived
rendering, not stored blocks).

**Artifact fields are generic-zip only.** The drafter fills facts about the zip bytes —
`member_count`, `uncompressed_bytes`, `compressed_bytes`, `compression`, `encrypted`,
`comment` — for every record (the embed's `media_type` carries each member's type). It does
NOT know about any *vendor* — recognizing a bundle as "an Unraid diagnostics package" and
surfacing its identity (version, hostname, …) is **domain knowledge for the codex layer**: a
classification overlay (`classify_when` on the MIME) + the normalizer, not this drafter.

`draft.manifest` config (optional):
    root_strip   bool — strip the single wrapper dir from member paths + the title.
"""

from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus import hashing, records, touches, ziparchive
from corpus.draft import DrafterResult, register_strategy

if TYPE_CHECKING:
    from corpus import recordbuild

_DETECTOR = touches.script_identifier("draft.zip-manifest")

_COMPRESSION_NAMES = {
    zipfile.ZIP_STORED: "store",
    zipfile.ZIP_DEFLATED: "deflate",
    zipfile.ZIP_BZIP2: "bzip2",
    zipfile.ZIP_LZMA: "lzma",
}


@register_strategy("zip-manifest")
def draft(
    zip_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
    mime_schema: dict[str, Any] | None = None,
) -> DrafterResult:
    cfg = dict(((mime_schema or {}).get("draft") or {}).get("manifest") or {})

    embeds: list[dict[str, Any]] = []
    member_count = 0
    total = 0
    compressed = 0
    methods: set[str] = set()
    encrypted = False
    root: str | None = None
    comment: str | None = None

    try:
        with zipfile.ZipFile(zip_path) as zf:
            comment = (zf.comment or b"").decode("utf-8", "replace").strip() or None
            infos = [i for i in zf.infolist() if not i.is_dir()]
            member_count = len(infos)
            if cfg.get("root_strip"):
                root = ziparchive.common_root([i.filename for i in infos])

            for info in sorted(infos, key=lambda i: ziparchive.relpath(i.filename, root)):
                rel = ziparchive.relpath(info.filename, root)
                total += info.file_size
                compressed += info.compress_size
                methods.add(
                    _COMPRESSION_NAMES.get(info.compress_type, f"method-{info.compress_type}")
                )
                if info.flag_bits & 0x1:
                    encrypted = True
                try:
                    data = zf.read(info.filename)
                except RuntimeError:
                    encrypted = True  # an encrypted member we can't read without a password
                    continue
                digest = hashing.hash_bytes(data, also=())["blake3"]
                embeds.append(
                    {
                        "media_type": _media_type(rel, data),
                        "address": f"path={rel}",
                        "transport": records.format_hash("blake3", digest),
                        "fields": {"bytes": info.file_size},
                    }
                )
    except zipfile.BadZipFile:
        return {"issues": [_issue("unreadable archive (corrupt or not a zip).")]}

    # No content zone: members are transports (embeds), not content atoms.

    fields: dict[str, Any] = {
        "member_count": member_count,
        "uncompressed_bytes": total,
        "compressed_bytes": compressed,
    }
    if methods:
        fields["compression"] = ", ".join(sorted(methods))
    if encrypted:
        fields["encrypted"] = True
    if comment:
        fields["comment"] = comment
    if root:
        fields["title"] = root.rstrip("/")  # a basic title candidate; the normalizer refines

    issues: list[dict[str, Any]] = []
    if member_count == 0:
        issues.append(_issue("archive contains no files."))

    result: DrafterResult = {"fields": fields, "embeds": embeds, "issues": issues}
    if canonical_algo:
        from corpus import content_hash

        result["canonical"] = records.format_hash(
            canonical_algo.split("-", 1)[0], content_hash.compute(canonical_algo, zip_path)
        )
    return result


def _media_type(rel: str, data: bytes) -> str:
    """The member's MIME — and, since the embed carries it, the text-vs-binary distinction.
    Text is decided by **content** (UTF-8, no NULs), not extension, so a `.cfg`/`.conf`/
    extensionless config or log is `text/plain` rather than misclassified binary; a precise
    extension guess (`application/json`, `image/png`) is kept; an opaque binary is
    `application/octet-stream`."""
    guessed = mimetypes.guess_type(rel)[0]
    if _is_text(data):
        return guessed or "text/plain"
    return guessed or "application/octet-stream"


def _is_text(data: bytes) -> bool:
    """A pragmatic text sniff: no NUL byte and decodes as UTF-8. Members are read whole (we
    hash them anyway), so this checks the full bytes — no truncation boundary issues. A
    non-UTF-8 text encoding (rare on the Linux bundles this targets) reads as binary."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _issue(description: str) -> dict[str, Any]:
    return {
        "id": "partial-content",
        "subtype": "empty-body",
        "severity": "blocking",
        "resolution": "open",
        "detector": _DETECTOR,
        "fields": {"description": description},
    }
