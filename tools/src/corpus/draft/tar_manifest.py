"""General `tar` / `tgz` → embed-manifest draft extraction (deterministic, no LLM).

The tar-family sibling of `zip_manifest`: a mime schema opts in with `draft.strategy:
tar-manifest`, and this ONE general drafter records the archive as an embed manifest — every
member an embed (content-sniffed `media_type`, blake3 `transport`, address `path=<rel>`), the
content zone empty (spec §1.2, §12.4). It shares the per-member core (`_manifest`) with the zip
drafter; only the archive access differs. A member becomes its own record only by deliberate
promotion (§8.1).

A `.tgz` is a **solid gzip stream**, so members can't be random-accessed: the drafter streams
the whole archive once (`tararchive.open_archive`, mode `r|*`), digesting each member's bytes as
it goes without holding the archive in RAM. Per-member compression doesn't exist in tar (the
whole stream is compressed, for a tgz), so `compressed_bytes` is the archive file size and
`compression` is `gzip`/`none` — the generic archive facts the artifact block carries.

`draft.manifest` config (optional):
    root_strip   bool — strip the single wrapper dir from member paths + the title.
"""

from __future__ import annotations

import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from corpus import records, tararchive, touches
from corpus.draft import DrafterResult, _manifest, register_strategy

if TYPE_CHECKING:
    from corpus import recordbuild

_DETECTOR = touches.script_identifier("draft.tar-manifest")


@register_strategy("tar-manifest")
def draft(
    tar_path: Path,
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
    root: str | None = None

    try:
        # A streaming pass: `common_root` (for root_strip) needs the member list, but reading
        # it up-front would decompress a tgz twice. Instead collect embeds with un-stripped
        # names, then strip the common root afterward (a pure rename of the recorded address).
        names: list[str] = []
        with tararchive.open_archive(tar_path) as tf:
            for info in tf:
                if not info.isfile():
                    continue
                member_count += 1
                total += info.size
                names.append(info.name)
                fp = tf.extractfile(info)
                if fp is None:  # defensive: isfile() should guarantee a stream
                    continue
                digest, is_text = _manifest.digest_and_text(fp)
                embeds.append(
                    {
                        "name": info.name,
                        "media_type": _manifest.media_type(info.name, is_text),
                        "transport": records.format_hash("blake3", digest),
                        "fields": {"bytes": info.size},
                    }
                )
    except tarfile.TarError:
        return {
            "issues": [
                _manifest.partial_content_issue(
                    _DETECTOR, "unreadable archive (corrupt or not a tar)."
                )
            ]
        }

    if cfg.get("root_strip"):
        root = tararchive.common_root(names)
    # Finalize each embed's address (root-stripped when configured), sorted for stable order.
    for emb in embeds:
        emb["address"] = f"path={tararchive.relpath(emb.pop('name'), root)}"
    embeds.sort(key=lambda e: e["address"])

    # No content zone: members are transports (embeds), not content atoms.

    fields: dict[str, Any] = {
        "member_count": member_count,
        "uncompressed_bytes": total,
        "compressed_bytes": _file_size(tar_path),
        "compression": tararchive.compression(tar_path),
    }
    if root:
        fields["title"] = root.rstrip("/")  # a basic title candidate; the normalizer refines

    issues: list[dict[str, Any]] = []
    if member_count == 0:
        issues.append(_manifest.partial_content_issue(_DETECTOR, "archive contains no files."))

    result: DrafterResult = {"fields": fields, "embeds": embeds, "issues": issues}
    if canonical_algo:
        from corpus import content_hash

        result["canonical"] = records.format_hash(
            canonical_algo.split("-", 1)[0], content_hash.compute(canonical_algo, tar_path)
        )
    return result


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
