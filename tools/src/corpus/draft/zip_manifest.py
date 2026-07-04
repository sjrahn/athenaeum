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
surfacing its identity (version, hostname, …) is **ledger knowledge**: a harvest rule keyed
on the kept-whole MIME (`ledger.md` §10) + the normalizer, not this drafter.

`draft.manifest` config (optional):
    root_strip   bool — strip the single wrapper dir from member paths + the title.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus import records, touches, ziparchive
from corpus.draft import DrafterResult, _manifest, register_strategy

if TYPE_CHECKING:
    from corpus import recordbuild

_DETECTOR = touches.script_identifier("draft.zip-manifest")

_COMPRESSION_NAMES = {
    zipfile.ZIP_STORED: "store",
    zipfile.ZIP_DEFLATED: "deflate",
    zipfile.ZIP_BZIP2: "bzip2",
    zipfile.ZIP_LZMA: "lzma",
    # Method 93 — the per-member codec `corpus assemble` writes (Python 3.14+; `corpus.assembly`).
    getattr(zipfile, "ZIP_ZSTANDARD", 93): "zstd",
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
                    digest, is_text = _digest_and_text(zf, info)
                except RuntimeError:
                    encrypted = True  # an encrypted member we can't read without a password
                    continue
                embeds.append(
                    {
                        "media_type": _media_type(rel, is_text),
                        "address": f"path={rel}",
                        "transport": records.format_hash("blake3", digest),
                        "fields": {"bytes": info.file_size},
                    }
                )
    except zipfile.BadZipFile:
        return {
            "issues": [
                _manifest.partial_content_issue(
                    _DETECTOR, "unreadable archive (corrupt or not a zip)."
                )
            ]
        }

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
        issues.append(_manifest.partial_content_issue(_DETECTOR, "archive contains no files."))

    result: DrafterResult = {"fields": fields, "embeds": embeds, "issues": issues}
    if canonical_algo:
        from corpus import content_hash

        result["canonical"] = records.format_hash(
            canonical_algo.split("-", 1)[0], content_hash.compute(canonical_algo, zip_path)
        )
    return result


def _media_type(rel: str, is_text: bool) -> str:
    """Thin wrapper over the shared `_manifest.media_type` (see there)."""
    return _manifest.media_type(rel, is_text)


def _digest_and_text(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[str, bool]:
    """Stream a member once — blake3 transport digest + a text/binary sniff — via the shared
    `_manifest.digest_and_text`, opening the member without materializing it whole (a
    diagnostics bundle can hold multi-GB logs). Raises `RuntimeError` for an encrypted member
    (no password), like `zipfile.read` — `zf.open` raises before the stream is consumed."""
    with zf.open(info) as fp:
        return _manifest.digest_and_text(fp)
