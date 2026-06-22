"""Ingest a single file from capture/ → records/<shard>/<hash>.md.

Computes blake3 + auxiliary byte hashes declared by the matching mime schema's
`transport_algos`. MIME detect → `<!--artifact <mime>-->` opener. Honors
`artifact_kind` per spec §1.2 — `decomposable` containers iterate their members
and route each through ingest; the container itself produces no record.

If the file's bytes are already in the corpus, this is an idempotent re-encounter:
the existing record gains a touch entry. If the capture URL differs from any
existing origin's `uri:`, a new origin block is appended.

Capture-time metadata sidecar: a `<file>.capture.yaml` alongside the input carries
capture metadata (`source_url`, `fetched_at`). On fresh ingest these seed the first
origin block; after ingest the sidecar is removed.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import frontmatter
import yaml

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, help="Path to a file in capture/")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    src = args.file.resolve()
    if not src.is_file():
        sys.exit(f"not a file: {src}")
    try:
        corpus_root = resolved_corpus_root(args)
    except SystemExit:
        # Fall back to discovering from the file's parent.
        from corpus import paths

        try:
            corpus_root = paths.find_corpus_root(src.parent)
        except FileNotFoundError as e:
            sys.exit(str(e))
    return _ingest_one(corpus_root, src)


def _ingest_one(corpus_root: Path, src: Path) -> int:
    from corpus import hashing, mime, paths, records, schemas, touches
    from corpus.store import get_store

    media_type = mime.detect(src, corpus_root)
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if mt_schema is None:
        sys.exit(
            f"no mime schema for {media_type!r} (file: {src}). "
            f"Author schema/mime/<axis>/<axis>_<subtype>.yaml first, then re-run."
        )

    # Spec §1.2: artifact_kind is REQUIRED, no default.
    artifact_kind = str(mt_schema.get("artifact_kind", "")).strip().lower()
    if artifact_kind not in ("self_contained", "decomposable"):
        sys.exit(
            f"mime schema for {media_type!r} is missing required `artifact_kind` "
            f"(must be `self_contained` or `decomposable`, spec §1.2)."
        )

    if artifact_kind == "decomposable":
        return _ingest_decomposable(corpus_root, src, mt_schema)

    aux_algos = tuple(str(a) for a in mt_schema.get("transport_algos", []) if a)
    digests = hashing.hash_file(src, also=aux_algos)
    record_id = digests["blake3"]
    transport_hashes = [
        records.format_hash(algo, digests[algo])
        for algo in aux_algos
        if algo in digests and algo.lower() != "blake3"
    ]

    extension = mime.extension_for(media_type, fallback=src.suffix.lstrip(".") or "bin")
    record_file = paths.record_path(corpus_root, record_id)
    store = get_store(corpus_root)

    sidecar = _read_sidecar(src)
    origin_uri, origin_at = _derive_capture_origin(src, sidecar)

    if record_file.is_file():
        post = records.load(record_file)
        appended = _append_origin_if_new(post, origin_uri, origin_at)
        touches.record_touch(post, touches.script_identifier("ingest"))
        records.dump(post, record_file)
        src.unlink()
        _cleanup_sidecar(src)
        _relocate_info_sidecar(src, record_id)
        print(f"re-encounter: {record_file.relative_to(corpus_root)}")
        if appended:
            print(f"  +origin: {origin_uri}")
        return 0

    # Persist bytes via the store, then unlink the staging file.
    store.put(record_id, extension, src)
    src.unlink()

    transport_value: str | list[str] | None
    if not transport_hashes:
        transport_value = None
    elif len(transport_hashes) == 1:
        transport_value = transport_hashes[0]
    else:
        transport_value = transport_hashes

    fm = records.stub_frontmatter(
        record_id=record_id,
        transport=transport_value,
        touch_id=touches.script_identifier("ingest"),
        description="",
    )
    post = frontmatter.Post(content="", **fm)
    # The artifact block carries no generic `title`: a capture-sidecar title (e.g. a yt-dlp
    # title) is non-primary-source metadata whose home is the origin block's `ytdlp_title`,
    # merged at draft. The frontmatter `title` stays empty until the normalizer authors it
    # from the namespaced candidates (an artifact `*_title`, an origin `ytdlp_title`); see
    # `records.title_for`.
    records.set_artifact_block(post, mime=media_type, fields={})
    records.append_origin_block(post, uri=origin_uri, snapshot=origin_at)
    _emit_sidecar_issues(post, sidecar)
    records.dump(post, record_file)

    _cleanup_sidecar(src)
    _relocate_info_sidecar(src, record_id)

    print(f"new stub: {record_file.relative_to(corpus_root)}")
    print(f"  hash:       {record_id}")
    print(f"  media_type: {media_type}")
    print(f"  binary:     {store.local_path(record_id, extension).relative_to(corpus_root)}")
    return 0


def _append_origin_if_new(post, uri: str, snapshot: str) -> bool:
    from corpus import records
    from corpus import urls as urlcanon

    if not uri or not snapshot:
        return False
    try:
        canon_new = urlcanon.normalize(uri)
    except Exception:
        canon_new = uri

    for origin in records.iter_origin_blocks(post):
        existing = (origin.get("fields") or {}).get("uri")
        candidates = existing if isinstance(existing, list) else [existing] if existing else []
        for c in candidates:
            try:
                canon_existing = urlcanon.normalize(str(c))
            except Exception:
                canon_existing = str(c)
            if canon_existing == canon_new:
                return False
    records.append_origin_block(post, uri=uri, snapshot=snapshot)
    return True


def _ingest_decomposable(corpus_root: Path, src: Path, mt_schema: dict) -> int:
    """Decomposable artifact: extract members into capture/, ingest each, remove
    container. Per spec §1.2, the container itself produces no record."""
    capture_dir = src.parent
    member_count = 0
    container_sidecar = _read_sidecar(src)

    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                data = zf.read(member)
                safe_name = member.replace("/", "_").replace("\\", "_")
                staged = capture_dir / f"{src.stem}__{safe_name}"
                staged.write_bytes(data)
                if container_sidecar:
                    _write_sidecar(staged, container_sidecar)
                _ingest_one(corpus_root, staged)
                member_count += 1
    else:
        sys.exit(f"declared decomposable but unsupported container: {src}")

    src.unlink()
    _cleanup_sidecar(src)
    print(f"decomposed {member_count} member(s) from {src.name}")
    return 0


def _write_sidecar(src: Path, payload: dict) -> None:
    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    sidecar_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _read_sidecar(src: Path) -> dict:
    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    if not sidecar_path.is_file():
        return {}
    try:
        with sidecar_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError:
        return {}


def _derive_capture_origin(src: Path, sidecar: dict) -> tuple[str, str]:
    from corpus import touches

    uri = str(sidecar.get("source_url") or "").strip()
    discovered_at = str(sidecar.get("fetched_at") or "").strip()
    if not uri:
        uri = src.resolve().as_uri()
    if not discovered_at:
        discovered_at = touches.now_iso()
    return uri, discovered_at


def _cleanup_sidecar(src: Path) -> None:
    sidecar_path = src.with_suffix(src.suffix + ".capture.yaml")
    if sidecar_path.is_file():
        sidecar_path.unlink()


def _relocate_info_sidecar(src: Path, record_id: str) -> None:
    """Rename a yt-dlp `.info.json` companion of `src` to `capture/<hash>.info.json`.

    It STAYS in the staging dir (`capture/`) — it is draft-time-only enrichment that the
    drafter reads and then deletes. The hash name lets the drafter find it; the artifact
    is the only `<hash>`-named file under `artifacts/`. No-op when absent (most mimes)."""
    info_src = src.with_suffix(".info.json")
    if info_src.is_file():
        info_src.rename(src.parent / f"{record_id}.info.json")


def _emit_sidecar_issues(post: frontmatter.Post, sidecar: dict) -> None:
    """Replay capture-stage issues onto the record as <!--issue--> blocks."""
    from corpus import records

    entries = sidecar.get("capture_issues") or []
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        issue_id = entry.get("id")
        severity = entry.get("severity")
        detector = entry.get("detector")
        if not (issue_id and severity and detector):
            continue
        records.append_issue_block(
            post,
            id=str(issue_id),
            subtype=entry.get("subtype"),
            severity=str(severity),
            resolution=str(entry.get("resolution") or "open"),
            detector=str(detector),
            fields=entry.get("fields") or None,
        )
