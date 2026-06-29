"""Functional URI resolver (spec §6).

Materialize a `corpus://...` URI into a path on disk. Cache-backed; same URI always
produces the same urihash → same cache file.

Pipeline:
  1. Parse the URI.
  2. Load the source artifact (by hash) via the `ArtifactStore`.
  3. Predict the final output kind by walking the param chain (no transforms invoked)
     so the cache lookup picks the right extension.
  4. On cache miss, walk the params left-to-right, dispatching to the transform
     registry based on the current working value's kind.
  5. Persist the final result to the cache and return its path.

Bare `corpus://<hash>` (no params) returns the source artifact's path directly.

Storage is pluggable: a `LocalArtifactStore` (default) reads/writes
`artifacts/<shard>/<id>.<ext>`; cloud adapters (Azure, S3) drop in via the same
Protocol in P3.

P2 ships image / pdf / html transforms. P5 adds video (extract_audio, frame) and
audio (transcribe, via the configured TranscriptionAdapter pulled from the context).
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image

from . import functional_uri as furi
from . import mime as mime_mod
from . import paths, records, transforms
from .store import ArtifactStore, get_store
from .transcription import TranscriptionAdapter, get_transcriber

log = logging.getLogger(__name__)


# Params that don't drive a transform and don't change output bytes. They carry
# addressing or render-config information that the resolver passes through.
_NOOP_PARAMS: frozenset[str] = frozenset({"dpi", "stream_id", "time"})


# Built-in MIME → initial working-value kind. This is now a FALLBACK: the authoritative
# source is the mime schema's `working_kind:` (see `_working_kind_for`), so a new corpus can
# add a media type — schema + drafter + transforms — without editing this table. The table
# keeps the bundled types resolving even if a schema omits the field.
_INITIAL_KIND_FOR_MIME: dict[str, str] = {
    "application/pdf": "pdf",
    "text/html": "html",
    "image/png": "image",
    "image/jpeg": "image",
    "image/gif": "image",
    "image/webp": "image",
    "image/avif": "image",
    "video/mp4": "video",
    "video/webm": "video",
    "video/quicktime": "video",
    "video/x-matroska": "video",
    "audio/mpeg": "audio",
}


# Final-output kind → cache file extension and sidecar MIME. The cache lookup needs
# the extension before any transform runs, so we predict the final kind from the
# URI's param chain (see `_predict_final_kind`).
KIND_TO_EXTENSION: dict[str, str] = {
    "image": "png",
    "text": "txt",
    "json": "json",
    "audio": "mp3",
    "bytes": "bin",
}

KIND_TO_MIME: dict[str, str] = {
    "image": "image/png",
    "text": "text/plain",
    "json": "application/json",
    "audio": "audio/mpeg",
    "bytes": "application/octet-stream",
}


def resolve(
    uri: str,
    corpus_root: Path,
    *,
    regenerate: bool = False,
    store: ArtifactStore | None = None,
    transcriber: TranscriptionAdapter | None = None,
) -> Path:
    """Resolve a functional URI to a file path. Cache-backed.

    `store` defaults to the configured `ArtifactStore` for `corpus_root` (Local /
    Azure / S3 per `corpus.toml` + env). `transcriber` defaults to the configured
    `TranscriptionAdapter` (NoOp / HTTPWhisper). P3 wires the injection seam;
    P5's audio transform consumes it via the RenderContext.

    Returns an absolute path. The caller may read the file, copy it, etc.
    """
    parsed = furi.parse(uri)
    canonical_uri = furi.canonical(parsed)
    artifact_record = _load_record(corpus_root, parsed.hash)
    media_type = records.media_type_for(artifact_record)
    if store is None:
        store = get_store(corpus_root)
    if transcriber is None:
        transcriber = get_transcriber(corpus_root)
    artifact_binary = store.ensure_local(parsed.hash, mime_mod.extension_for(media_type))

    # Bare URI — no derivation; the caller wants the source binary.
    if parsed.is_bare:
        return artifact_binary.resolve()

    # Effectively bare: all params are no-ops (pure addressing). Return source.
    if all(k in _NOOP_PARAMS for k, _ in parsed.params):
        return artifact_binary.resolve()

    # Initial kind (schema-declared `working_kind`, else the built-in table) and final
    # kind (predicted from chain).
    initial_kind = _working_kind_for(corpus_root, media_type)
    if initial_kind is None:
        raise NotImplementedError(
            f"no transformation pipeline registered for media_type {media_type!r} "
            f"(declare `working_kind:` on its mime schema, or add it to the resolver table)"
        )
    final_kind = _predict_final_kind(parsed, initial_kind)
    if final_kind not in KIND_TO_EXTENSION:
        raise NotImplementedError(
            f"final output kind {final_kind!r} has no cache extension registered"
        )

    urihash_value = furi.urihash(canonical_uri)
    cache_p = furi.cache_path(corpus_root, urihash_value, KIND_TO_EXTENSION[final_kind])
    if cache_p.is_file() and not regenerate:
        log.debug("cache hit: %s", cache_p)
        return cache_p.resolve()

    # Build render context.
    ctx: transforms.RenderContext = {}
    dpi_raw = furi.get_last(parsed, "dpi")
    if dpi_raw is not None:
        try:
            dpi_value = int(dpi_raw)
        except ValueError as exc:
            raise ValueError(f"dpi= must be an integer, got {dpi_raw!r}") from exc
        if dpi_value < 1:
            raise ValueError(f"dpi= must be positive, got {dpi_value}")
        ctx["dpi"] = dpi_value
    # Audio transforms pull the transcriber from the context; the video `frame`
    # transform range-checks against the source duration when it's known.
    ctx["transcriber"] = transcriber
    duration = _record_duration(artifact_record)
    if duration is not None:
        ctx["video_duration_seconds"] = duration
    # PDF text/probe ops read the source from disk via pypdf (the working value is a
    # pypdfium2 document); hand them the artifact path.
    ctx["artifact_path"] = artifact_binary

    # Initialize working value.
    working: Any
    pdf_doc: pdfium.PdfDocument | None = None
    if initial_kind == "pdf":
        pdf_doc = pdfium.PdfDocument(str(artifact_binary))
        working = pdf_doc
    elif initial_kind == "html":
        from bs4 import BeautifulSoup

        working = BeautifulSoup(artifact_binary.read_bytes(), "html.parser")
    elif initial_kind == "image":
        # Load + decode into memory so the file handle closes before transforms run.
        with Image.open(artifact_binary) as im:
            im.load()
            working = im.copy()
    elif initial_kind in ("video", "audio", "epub", "zip"):
        # The working value is the artifact path itself: ffmpeg and the transcriber stream
        # from disk rather than loading the whole media into memory; the epub `spine`
        # transform opens the zip to select a content document and its image members; the
        # zip `path=` transform opens the archive to extract a member.
        working = artifact_binary
    else:
        raise NotImplementedError(f"initial kind {initial_kind!r} not yet supported")

    current_kind = initial_kind
    try:
        for key, value in parsed.params:
            if key in _NOOP_PARAMS:
                continue
            handler, promote = _resolve_handler(current_kind, key)
            if handler is None:
                raise ValueError(
                    f"transform {key!r} not applicable to working kind {current_kind!r}"
                )
            if promote:
                # An image-kind op after a `pdfpage` (bbox/mark/fit/rotate/…): the page
                # must be rendered to an image first.
                working = _render_pdfpage(working, ctx)
                current_kind = "image"
            log.debug("apply %s=%r (%s -> %s)", key, value, current_kind, handler.output_kind)
            working = handler.func(working, value, ctx)
            current_kind = handler.output_kind
        # A terminal `pdfpage` (bare `page=N`, or `page=N&dpi=…`) renders to image, so a
        # segment's `address: page=N` image marker resolves to the page bytes as before.
        if current_kind == "pdfpage":
            working = _render_pdfpage(working, ctx)
            current_kind = "image"
    finally:
        # pypdfium2's PdfDocument is reference-counted; close explicitly.
        if pdf_doc is not None:
            pdf_doc.close()

    if current_kind != final_kind:
        raise RuntimeError(
            f"predicted final kind {final_kind!r} but transform chain produced {current_kind!r}"
        )

    cache_p.parent.mkdir(parents=True, exist_ok=True)
    _write_to_cache(working, current_kind, cache_p)
    _write_sidecar(corpus_root, canonical_uri, parsed.hash, cache_p, current_kind)
    log.debug("cached: %s", cache_p)
    return cache_p.resolve()


# ---------- internals ---------- #


def _resolve_handler(current_kind: str, key: str):
    """Look up the transform handler for `(current_kind, key)`.

    A `pdfpage` auto-promotes to `image` for image-kind ops: when no `(pdfpage, key)`
    handler exists but `(image, key)` does, return `(image_handler, promote=True)` so the
    caller renders the page to an image first. Otherwise `(handler, False)` or `(None, False)`.
    """
    handler = transforms.lookup(current_kind, key)
    if handler is not None:
        return handler, False
    if current_kind == "pdfpage":
        image_handler = transforms.lookup("image", key)
        if image_handler is not None:
            return image_handler, True
    return None, False


def _render_pdfpage(ref: Any, ctx: transforms.RenderContext) -> Any:
    """Render a `pdfpage` selector to a PIL Image (auto-promotion + terminal render)."""
    from .transforms import pdf as pdf_transforms

    return pdf_transforms.render_pdfpage(ref, ctx)


def _predict_final_kind(parsed: furi.ParsedURI, initial_kind: str) -> str:
    """Walk the param chain consulting the registry; return the final kind. No
    transforms invoked. Used to determine the cache extension before the cache
    check runs."""
    current = initial_kind
    for key, _ in parsed.params:
        if key in _NOOP_PARAMS:
            continue
        handler, _promote = _resolve_handler(current, key)
        if handler is None:
            raise ValueError(f"transform {key!r} not applicable to working kind {current!r}")
        current = handler.output_kind
    # A terminal `pdfpage` renders to an image (see resolve()).
    if current == "pdfpage":
        current = "image"
    return current


def _write_to_cache(working: Any, kind: str, cache_p: Path) -> None:
    if kind == "image":
        # Convert palette images so saving to PNG is lossless.
        if working.mode == "P":
            working = working.convert("RGBA")
        working.save(cache_p, format="PNG")
    elif kind in ("text", "json"):
        cache_p.write_text(working, encoding="utf-8")
    elif kind == "audio":
        # `working` is a Path to ffmpeg's temp output; move it into the cache.
        shutil.move(str(working), cache_p)
    elif kind == "bytes":
        # `working` is the raw member bytes; cache verbatim.
        cache_p.write_bytes(working)
    else:
        raise NotImplementedError(f"no cache writer for kind {kind!r}")


def _working_kind_for(corpus_root: Path, media_type: str) -> str | None:
    """The resolver's initial working kind for a media type. Schema-first — the mime
    schema's `working_kind:` — falling back to the built-in `_INITIAL_KIND_FOR_MIME` table
    so the bundled types keep resolving even if a schema omits the field."""
    from . import schemas

    schema = schemas.load_mime_schema(corpus_root, media_type) or {}
    kind = schema.get("working_kind")
    if isinstance(kind, str) and kind:
        return kind
    return _INITIAL_KIND_FOR_MIME.get(media_type)


def _load_record(corpus_root: Path, record_hash: str):
    record_file = paths.record_path(corpus_root, record_hash)
    if not record_file.is_file():
        raise FileNotFoundError(f"no record for hash {record_hash}: {record_file}")
    return records.load(record_file)


def _record_duration(artifact_record: Any) -> float | None:
    """Best-effort source duration (seconds) from the artifact block's fields, if a
    prior video draft recorded it. Used to range-check `?frame=` timecodes."""
    artifact = records.artifact_block(artifact_record) or {}
    dur = (artifact.get("fields") or {}).get("duration")
    if isinstance(dur, (int, float)):
        return float(dur)
    return None


def _write_sidecar(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    cache_p: Path,
    kind: str,
) -> None:
    sidecar = furi.cache_sidecar_path(cache_p)
    sidecar.write_text(
        json.dumps(
            {
                "uri": canonical_uri,
                "source_hash": source_hash,
                "mime": KIND_TO_MIME.get(kind, "application/octet-stream"),
                "generated_at": (
                    datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
