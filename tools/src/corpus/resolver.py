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

from . import containment, paths, records, transforms
from . import functional_uri as furi
from . import mime as mime_mod
from .store import ArtifactStore, get_store
from .transcription import TranscriptionAdapter, get_transcriber

log = logging.getLogger(__name__)


# Params that don't drive a transform and don't change output bytes. They carry
# addressing or render-config information that the resolver passes through.
# `cut=` is position-independent config for `time_range=` (like `dpi=` for `page=`);
# `stream_id=` is likewise config here — the resolver reads its value into the render
# context (below) for `time_range=`/`format=`/`scenes=` to compose via ffmpeg `-map`,
# rather than registering it as its own working-kind transform (§6.2, §12.20 item 4).
_NOOP_PARAMS: frozenset[str] = frozenset({"dpi", "stream_id", "time", "cut"})

# The muxing contract's ops (§6.2) whose output is engine-versioned (§6.3/§6.4): ffmpeg
# encoder/detector output drifts across versions, so a URI carrying any of these folds the
# ffmpeg engine id into the cache key exactly as `transcribe` folds in its adapter's engine.
_FFMPEG_ENGINE_PARAMS: frozenset[str] = frozenset({"time_range", "format", "scenes"})

# Working kinds whose final cache extension isn't known until the transform chain actually
# runs: `htmlel` resolves polymorphically to image|bytes (§6.2 `el=`); `video`/`audio`/
# `media` are ffmpeg-produced Paths whose extension depends on the source's container
# family (bare `time_range=`) or the `format=` token — neither predictable from the param
# chain alone the way every other op's output kind is.
_DEFERRED_EXTENSION_KINDS: frozenset[str] = frozenset({"htmlel", "video", "audio", "media"})


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

    # Record-level derivation ops (§6.2) — computed from the RECORD (its attested manifest),
    # not from a working-value transform over the artifact bytes, so they need no materialized
    # container. `members` is the container manifest, derived: the member enumeration
    # (`path=`/`msg=`/`part=`/`stream_id=`/… axes, each with its transport hash, size, sniffed
    # type). Single-param only.
    if len(parsed.params) == 1 and parsed.params[0] == ("members", None):
        return _resolve_members(
            corpus_root, canonical_uri, parsed.hash, artifact_record, regenerate=regenerate
        )

    # `body` (§6.2): the record's faithful mechanical body markdown — what the 2.x draft
    # stage stored — derived on demand from the artifact via the shared drafter-run core.
    # A pure function of (artifact x schemas x op version); empty for a manifest record.
    if len(parsed.params) == 1 and parsed.params[0] == ("body", None):
        return _resolve_body(
            corpus_root, canonical_uri, parsed.hash, artifact_record, regenerate=regenerate
        )

    # `turn=<N>` (§6.2): the verbatim N-th unit of the record's declared unit array, located by
    # the origin overlay's form mapping (§7.2). `turn=<N>&att=<M>` materializes unit N's M-th
    # declared attachment through lineage-chained resolution. Record-level ops.
    turn = _turn_index(parsed)
    if turn is not None:
        n, att_m = turn
        return _resolve_turn(
            corpus_root, canonical_uri, parsed.hash, artifact_record, n, att_m,
            regenerate=regenerate,
        )

    if store is None:
        store = get_store(corpus_root)
    if transcriber is None:
        # Per-host transcription config (§7.2): the record's origin-overlay `transcription:`
        # section (`adapter`/`base_url`) overrides the global backend, so a host selects its own
        # transcriber even when the corpus default is NoOp. `resolve_transcription` returns an
        # override adapter when the host declares one, else None (the global default applies).
        from corpus.draft._hostcfg import resolve_transcription
        from corpus.transcription import DisabledTranscriber

        mode, per_host = resolve_transcription(corpus_root, artifact_record.metadata)
        if mode == "disabled":  # transcription.enabled: false — the op skips (§7.2)
            transcriber = DisabledTranscriber()
        elif per_host is not None:
            transcriber = per_host
        else:
            transcriber = get_transcriber(corpus_root)
    # Containment-aware (spec §2/§12.9): a standalone artifact when present, else the bytes
    # streamed out of the promoted record's container via the member index.
    artifact_binary = containment.ensure_local_bytes(
        corpus_root, parsed.hash, mime_mod.extension_for(media_type), store=store
    )

    # Bare URI — no derivation; the caller wants the source binary.
    if parsed.is_bare:
        return artifact_binary.resolve()

    # `stream_id=<n>` ALONE (§12.20 item 4): the bare/terminal identity case. Composed with an
    # engine op (`time_range=`/`format=`/`scenes=`) `stream_id=` stays pure addressing config
    # (handled below via `_NOOP_PARAMS` + `ctx["stream_ids"]`, feeding the phase-1 ffmpeg `-map`
    # path) — but alone, it must resolve to the track's PINNED IDENTITY bytes
    # (`corpus.streams.extract_stream`), never fall through to the raw container the generic
    # no-op branch below would otherwise return. Pure byte-work: no ffmpeg engine version folds
    # into the cache key (§12.20 item 1).
    if parsed.params and all(k == "stream_id" for k, _ in parsed.params):
        return _resolve_stream_identity(
            corpus_root, canonical_uri, parsed.hash, artifact_binary,
            parsed.params, regenerate=regenerate,
        )

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
    # Version-labeled ops (§6.3, §6.4): `transcribe` output drifts across transcription
    # engines; the muxing contract's `time_range=`/`format=`/`scenes=` drift across ffmpeg
    # versions the same way ("cuts, muxes, and conversions are version-labeled ops", §6.2).
    # Either way the cache key includes the engine id and the sidecar records it —
    # determinism holds per engine/version.
    if any(k == "transcribe" for k, _ in parsed.params):
        version_label = getattr(transcriber, "engine", None)
    elif any(k in _FFMPEG_ENGINE_PARAMS for k, _ in parsed.params):
        from .transforms import video as video_tf

        version_label = video_tf.ffmpeg_engine_label()
    else:
        version_label = None
    key_uri = f"{canonical_uri}|engine={version_label}" if version_label else canonical_uri
    urihash_value = furi.urihash(key_uri)
    # A terminal `el=N` on HTML is polymorphic: an `<img>` materializes to a PNG image,
    # a `<video>`/`<audio>`/`<a href="data:…">` carrier to raw bytes. A terminal muxing-
    # contract op (`video`/`audio`/`media`, §6.2) is a Path an ffmpeg command already wrote,
    # whose extension depends on the source's container family or the `format=` token — also
    # not known until the chain runs. Either way the concrete kind — hence the cache
    # extension — isn't known until the transform runs, so the cache hit is a stem glob
    # (cheap: no parse of a possibly-huge HTML, no ffmpeg invocation) and the cache path is
    # deferred until after materialization.
    terminal_deferred = final_kind in _DEFERRED_EXTENSION_KINDS
    cache_p: Path | None
    if terminal_deferred:
        cached = _find_cached_by_stem(corpus_root, urihash_value)
        if cached is not None and not regenerate:
            log.debug("cache hit: %s", cached)
            return cached.resolve()
        cache_p = None
    else:
        if final_kind not in KIND_TO_EXTENSION:
            raise NotImplementedError(
                f"final output kind {final_kind!r} has no cache extension registered"
            )
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
    # `cut=` (§6.2): position-independent config for `time_range=`, like `dpi=` for `page=`.
    cut_raw = furi.get_last(parsed, "cut")
    if cut_raw is not None and cut_raw not in ("precise", "copy"):
        raise ValueError(f"cut= must be 'precise' or 'copy', got {cut_raw!r}")
    ctx["cut_mode"] = cut_raw or "precise"
    # `stream_id=<id>[,<id>…]` (§6.2): read here (not a registered transform, §12.20 item 4)
    # so `time_range=`/`format=`/`scenes=` compose it via ffmpeg `-map` themselves.
    stream_id_values = [v for k, v in parsed.params if k == "stream_id" and v]
    if stream_id_values:
        ctx["stream_ids"] = [s.strip() for s in stream_id_values[-1].split(",") if s.strip()]
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
        # Without init_forms(), AcroForm widget values (form-fill text without baked
        # appearance streams) silently never paint in page renders — the page looks
        # blank exactly where the filled content is.
        pdf_doc.init_forms()
        working = pdf_doc
    elif initial_kind == "html":
        from bs4 import BeautifulSoup

        working = BeautifulSoup(artifact_binary.read_bytes(), "html.parser")
    elif initial_kind == "image":
        # Load + decode into memory so the file handle closes before transforms run.
        with Image.open(artifact_binary) as im:
            im.load()
            working = im.copy()
    elif initial_kind in ("video", "audio", "epub", "zip", "tar", "mbox", "vcard", "message"):
        # The working value is the artifact path itself: ffmpeg and the transcriber stream
        # from disk rather than loading the whole media into memory; the epub `spine`
        # transform opens the zip to select a content document and its image members; the
        # zip / tar `path=` transforms open the archive to extract a member; the mbox `msg=`
        # transform streams a single message out of the mailbox; the vcard `card=` transform
        # extracts one card's exact bytes from the `.vcf`; the message `part=` transform
        # decodes one MIME part of an email.
        working = artifact_binary
    else:
        raise NotImplementedError(f"initial kind {initial_kind!r} not yet supported")

    current_kind = initial_kind
    terminal_mime: str | None = None
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
                # An image-kind op after a `pdfpage` or an HTML `htmlel` (bbox/mark/fit/
                # rotate/…): the page / `<img>` carrier must be rendered to an image first.
                working = _promote_to_image(working, current_kind, ctx)
                current_kind = "image"
            log.debug("apply %s=%r (%s -> %s)", key, value, current_kind, handler.output_kind)
            working = handler.func(working, value, ctx)
            current_kind = handler.output_kind
        # A terminal `pdfpage` (bare `page=N`, or `page=N&dpi=…`) renders to image, so a
        # segment's `address: page=N` image marker resolves to the page bytes as before.
        if current_kind == "pdfpage":
            working = _render_pdfpage(working, ctx)
            current_kind = "image"
        # A terminal `htmlel` (bare `el=N`) materializes to its concrete output: an `<img>`
        # to a PIL image (cache PNG), a media/attachment carrier to raw bytes (cache the
        # media's native extension). The cache path was deferred — set it now.
        if current_kind == "htmlel":
            working, current_kind, terminal_ext, terminal_mime = _materialize_htmlel(
                working, ctx
            )
            cache_p = furi.cache_path(corpus_root, urihash_value, terminal_ext)
        elif cache_p is None and current_kind in ("video", "audio", "media"):
            # A terminal muxing-contract op (§6.2): `working` is a Path an ffmpeg command
            # already wrote — its extension is the source's container family (bare
            # `time_range=`) or the `format=` token's target; either way, only known now.
            terminal_ext = Path(working).suffix.lstrip(".") or KIND_TO_EXTENSION.get(
                current_kind, "bin"
            )
            terminal_mime = _media_mime_for_ext(terminal_ext)
            cache_p = furi.cache_path(corpus_root, urihash_value, terminal_ext)
    finally:
        # pypdfium2's PdfDocument is reference-counted; close explicitly.
        if pdf_doc is not None:
            pdf_doc.close()

    # `htmlel` and the muxing-contract kinds resolve their concrete extension only after the
    # chain runs, so the predicted sentinel legitimately differs from `current_kind` for
    # `htmlel` specifically (image|bytes); the muxing kinds are NOT exempted — `current_kind`
    # must still equal the predicted `video`/`audio`/`media`, a real correctness check.
    if final_kind != "htmlel" and current_kind != final_kind:
        raise RuntimeError(
            f"predicted final kind {final_kind!r} but transform chain produced {current_kind!r}"
        )
    assert cache_p is not None  # set for every non-deferred kind, and by the deferred terminals

    cache_p.parent.mkdir(parents=True, exist_ok=True)
    _write_to_cache(working, current_kind, cache_p)
    _write_sidecar(
        corpus_root, canonical_uri, parsed.hash, cache_p, current_kind,
        mime_override=terminal_mime, version_label=version_label,
    )
    log.debug("cached: %s", cache_p)
    return cache_p.resolve()


# ---------- record-level derivation ops (§6.2) ---------- #


def _resolve_members(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    artifact_record: Any,
    *,
    regenerate: bool,
) -> Path:
    """Materialize the `members` derivation op (§6.2): the container's member manifest as
    JSON, derived from the record's attested embed blocks (each a member transport — its
    address in the container's own axis, its blake3 `transport`, size, and sniffed MIME).
    Cached like any resolver result."""
    urihash_value = furi.urihash(canonical_uri)
    cache_p = furi.cache_path(corpus_root, urihash_value, "json")
    if cache_p.is_file() and not regenerate:
        return cache_p.resolve()

    members: list[dict[str, Any]] = []
    for embed in records.iter_embed_blocks(artifact_record):
        addr = embed.get("address")
        fields = embed.get("fields") or {}
        for one in addr if isinstance(addr, list) else [addr]:
            members.append(
                {
                    "address": one,
                    "transport": embed.get("transport"),
                    "media_type": embed.get("media_type"),
                    "bytes": fields.get("bytes"),
                }
            )
    payload = {"count": len(members), "members": members}

    cache_p.parent.mkdir(parents=True, exist_ok=True)
    cache_p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_sidecar(corpus_root, canonical_uri, source_hash, cache_p, "json")
    return cache_p.resolve()


# Pinned per-codec elementary form's cache extension (spec §12.20.1 / §12.20 item 4) — the
# same four the promoted-track embed's filename hint uses (`draft/_trackmanifest.py`), except
# AAC: `.adts` here names the byte format directly (the resolver cache has no promote-time
# MIME-sniff concern to serve).
_STREAM_IDENTITY_EXTENSIONS: dict[str, str] = {
    "h264": "h264",
    "hevc": "h265",
    "aac": "adts",
    "opus": "opus",
}


def _resolve_stream_identity(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    artifact_binary: Path,
    params: list[tuple[str, str | None]],
    *,
    regenerate: bool,
) -> Path:
    """Materialize the bare `stream_id=<n>` identity op (§12.20 item 4): the track's pinned
    extraction bytes via `corpus.streams.extract_stream` — never the raw container, and never
    an ffmpeg engine version folded into the cache key (this is pure byte-work, §12.20 item 1;
    contrast the engine-versioned muxing-contract ops that COMPOSE `stream_id=` via `-map`,
    §6.2). Single-track only: a comma-list or repeated `stream_id=` has no meaning for pure
    identity extraction (you cannot concatenate two different codecs' elementary bytes) — that
    combination is only valid alongside a muxing-contract op.

    The extension is cheap to predict ahead of the cache check (unlike the muxing contract's
    deferred-extension kinds, §12.20 item 1's engine path): `probe_streams` reads only the
    small `moov` subtree, never sample data."""
    from . import streams

    values = [v for _, v in params if v]
    if len(values) != 1 or "," in values[-1]:
        raise ValueError(
            "bare stream_id= identity resolution takes exactly one track id (compose with "
            "time_range=/format=/scenes= to select or mux multiple streams)"
        )
    try:
        stream_id = int(values[-1])
    except ValueError as exc:
        raise ValueError(f"stream_id= must be an integer, got {values[-1]!r}") from exc

    tracks = streams.probe_streams(artifact_binary)
    track = next((t for t in tracks if t.index == stream_id), None)
    if track is None:
        raise ValueError(f"stream_id={stream_id}: no such track ({len(tracks)} track(s))")
    ext = _STREAM_IDENTITY_EXTENSIONS.get(track.codec)
    if ext is None:
        raise NotImplementedError(
            f"stream_id={stream_id}: identity extraction not implemented for codec "
            f"{track.codec!r}"
        )

    urihash_value = furi.urihash(canonical_uri)
    cache_p = furi.cache_path(corpus_root, urihash_value, ext)
    if cache_p.is_file() and not regenerate:
        return cache_p.resolve()

    cache_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_p.with_name(f"{cache_p.name}.tmp")
    try:
        with tmp.open("wb") as out:
            for chunk in streams.extract_stream(artifact_binary, stream_id):
                out.write(chunk)
        tmp.replace(cache_p)
    finally:
        tmp.unlink(missing_ok=True)
    _write_sidecar(
        corpus_root, canonical_uri, source_hash, cache_p, "bytes",
        mime_override=track.media_type,
    )
    return cache_p.resolve()


def _turn_index(parsed: furi.ParsedURI) -> tuple[int, int | None] | None:
    """Recognize `turn=<N>` (optionally `&att=<M>`) as the whole param chain; return
    `(N, att_M | None)` or None when the URI is not a bare unit op."""
    params = list(parsed.params)
    if not params or params[0][0] != "turn":
        return None
    try:
        n = int(params[0][1] or "")
    except (TypeError, ValueError):
        return None
    if len(params) == 1:
        return n, None
    if len(params) == 2 and params[1][0] == "att":
        try:
            return n, int(params[1][1] or "")
        except (TypeError, ValueError):
            return None
    return None  # a further-composed chain is not a bare unit op


def _resolve_turn(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    artifact_record: Any,
    n: int,
    att_m: int | None,
    *,
    regenerate: bool,
) -> Path:
    """Materialize a `turn=` unit op (§6.2). `turn=<N>` returns the verbatim N-th unit object
    as JSON, located by the origin overlay's form mapping (§7.2). `turn=<N>&att=<M>` resolves
    unit N's M-th declared attachment through **lineage-chained resolution**: the attachment's
    declared path is resolved as a member of the record's blake3-pinned containment parent
    (the promotion-lineage origin, §8.1), never stored — so it cannot rot, and an absent
    member fails loudly."""
    from . import shape
    from .shape import units

    resolved = shape.form_for_record(artifact_record, corpus_root)
    if resolved is None:
        raise ValueError("turn= requires a declared form mapping (origin overlay `form:`, §7.2)")
    _origin_id, _form_id, mapping = resolved
    data = units.load_json_artifact(corpus_root, artifact_record)
    msg = units.unit(data, mapping, n)
    if msg is None:
        raise ValueError(f"turn={n}: out of range (the unit array has fewer messages)")

    if att_m is None:
        urihash_value = furi.urihash(canonical_uri)
        cache_p = furi.cache_path(corpus_root, urihash_value, "json")
        if cache_p.is_file() and not regenerate:
            return cache_p.resolve()
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        cache_p.write_text(json.dumps(msg, indent=2) + "\n", encoding="utf-8")
        _write_sidecar(corpus_root, canonical_uri, source_hash, cache_p, "json")
        return cache_p.resolve()

    # turn=N&att=M — lineage-chained attachment resolution.
    atts = units.attachments(msg, mapping)
    if not 1 <= att_m <= len(atts):
        raise ValueError(f"turn={n}&att={att_m}: unit {n} declares {len(atts)} attachment(s)")
    att = atts[att_m - 1]
    ref = units.field(att, mapping, "attachment_path")
    if ref is None:
        ref = units.field(att, mapping, "attachment_url") if isinstance(att, dict) else att
    ref = str(ref or "").strip()
    if not ref:
        raise ValueError(f"turn={n}&att={att_m}: attachment declares no resolvable reference")

    container = _lineage_container(artifact_record)
    if container is None:
        raise ValueError(
            f"turn={n}&att={att_m}: attachment `{ref}` is not lineage-resolvable "
            f"(the record has no containment-lineage origin, §4.3.1.4)"
        )
    # Resolve the attachment as a member of the container (recursing through the resolver).
    member_uri = f"{furi.SCHEME}://{container}?path={furi.quote_value(ref)}"
    return resolve(member_uri, corpus_root, regenerate=regenerate)


def _lineage_container(artifact_record: Any) -> str | None:
    """The blake3 id of the record's containment-lineage parent — the `corpus://<container>?…`
    an origin block records at promotion (§8.1) — or None when the record is standalone."""
    for uri in records.iter_origin_uris(artifact_record):
        u = str(uri)
        if u.startswith(f"{furi.SCHEME}://"):
            try:
                return furi.parse(u).hash
            except Exception:
                continue
    return None


def _resolve_body(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    artifact_record: Any,
    *,
    regenerate: bool,
) -> Path:
    """Materialize the `body` derivation op (§6.2): the record's faithful mechanical body
    markdown, derived from the artifact via the shared drafter-run core (`corpus.derive`).
    Cached like any resolver result. Requires the artifact bytes (the drafter reads them)."""
    from . import derive

    urihash_value = furi.urihash(canonical_uri)
    cache_p = furi.cache_path(corpus_root, urihash_value, "txt")
    if cache_p.is_file() and not regenerate:
        return cache_p.resolve()
    body = derive.derive_body(artifact_record, corpus_root)
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    cache_p.write_text(body if body.endswith("\n") or not body else body + "\n", encoding="utf-8")
    _write_sidecar(corpus_root, canonical_uri, source_hash, cache_p, "text")
    return cache_p.resolve()


# ---------- internals ---------- #


def _resolve_handler(current_kind: str, key: str):
    """Look up the transform handler for `(current_kind, key)`.

    An intermediate `pdfpage` / `htmlel` auto-promotes to `image` for image-kind ops:
    when no `(<kind>, key)` handler exists but `(image, key)` does, return
    `(image_handler, promote=True)` so the caller renders the page / `<img>` carrier to an
    image first. Otherwise `(handler, False)` or `(None, False)`.
    """
    handler = transforms.lookup(current_kind, key)
    if handler is not None:
        return handler, False
    if current_kind in ("pdfpage", "htmlel"):
        image_handler = transforms.lookup("image", key)
        if image_handler is not None:
            return image_handler, True
    return None, False


def _render_pdfpage(ref: Any, ctx: transforms.RenderContext) -> Any:
    """Render a `pdfpage` selector to a PIL Image (auto-promotion + terminal render)."""
    from .transforms import pdf as pdf_transforms

    return pdf_transforms.render_pdfpage(ref, ctx)


def _promote_to_image(working: Any, current_kind: str, ctx: transforms.RenderContext) -> Any:
    """Render an intermediate selector (`pdfpage` / `htmlel`) to a PIL Image so a following
    image-output op (bbox/mark/fit/…) can apply."""
    if current_kind == "pdfpage":
        return _render_pdfpage(working, ctx)
    if current_kind == "htmlel":
        from .transforms import html as html_transforms

        return html_transforms.render_htmlel_image(working, ctx)
    raise NotImplementedError(f"cannot promote working kind {current_kind!r} to image")


def _materialize_htmlel(
    ref: Any, ctx: transforms.RenderContext
) -> tuple[Any, str, str, str]:
    """Materialize a terminal `htmlel` (`HtmlElRef`) to its concrete output: an `<img>` to
    a PIL image (kind `image`, ext `png`), or a media/attachment carrier to raw bytes (kind
    `bytes`, the media's native extension). Returns `(working, kind, extension, mime)`."""
    from . import mime as mime_mod
    from .transforms import html as html_transforms

    if ref.tag.name == "img":
        return html_transforms.render_htmlel_image(ref, ctx), "image", "png", "image/png"
    media_type, raw = html_transforms.htmlel_bytes(ref)
    return raw, "bytes", mime_mod.extension_for(media_type), media_type


def _find_cached_by_stem(corpus_root: Path, urihash_value: str) -> Path | None:
    """Return an existing cache content file for `urihash_value` under any extension (the
    polymorphic `htmlel` cache hit), or None. Excludes the `.json` sidecar."""
    shard_dir = corpus_root / "cache" / paths.shard(urihash_value)
    if not shard_dir.is_dir():
        return None
    for p in sorted(shard_dir.glob(f"{urihash_value}.*")):
        if p.name.endswith(".json") or not p.is_file():
            continue
        return p
    return None


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
    elif kind in ("audio", "video", "media"):
        # `working` is a Path to ffmpeg's temp output (extract_audio, or a muxing-contract
        # op — `time_range=`/`format=`/`scenes=`'s Path-valued results, §6.2); move it into
        # the cache.
        shutil.move(str(working), cache_p)
    elif kind == "bytes":
        # `working` is the raw member bytes; cache verbatim.
        cache_p.write_bytes(working)
    else:
        raise NotImplementedError(f"no cache writer for kind {kind!r}")


#: Extensions the built-in `mimetypes` table doesn't reliably map on every platform —
#: matched to the `mime.extension_for` canonical choices so a muxing-contract result's
#: sidecar mime agrees with what ingest would have recorded for the same container.
_MEDIA_MIME_OVERRIDES: dict[str, str] = {
    "m4a": "audio/mp4",
    "mkv": "video/x-matroska",
    "mov": "video/quicktime",
    "webm": "video/webm",
}


def _media_mime_for_ext(ext: str) -> str:
    """Best-effort mime for a muxing-contract op's terminal extension (§6.2) — used for the
    sidecar only; identity is the hash, never the extension or the mime."""
    import mimetypes as _mimetypes

    guessed, _ = _mimetypes.guess_type(f"x.{ext}")
    return guessed or _MEDIA_MIME_OVERRIDES.get(ext, "application/octet-stream")


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
    mime_override: str | None = None,
    version_label: str | None = None,
) -> None:
    sidecar_data: dict[str, Any] = {
        "uri": canonical_uri,
        "source_hash": source_hash,
        "mime": mime_override or KIND_TO_MIME.get(kind, "application/octet-stream"),
        "generated_at": (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        ),
    }
    if version_label:  # a version-labeled op (§6.4) — the engine that produced this result
        sidecar_data["engine"] = version_label
    sidecar = furi.cache_sidecar_path(cache_p)
    sidecar.write_text(json.dumps(sidecar_data, indent=2) + "\n", encoding="utf-8")
