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
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image

from . import containment, paths, records, transforms, ziparchive
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

# The CSV row/col unit op (§6.2 `row=`, `col=`) is deterministic (a pure RFC-4180 parse,
# not an external engine whose output drifts) but still carries a versioned op id
# (`transforms.csv.ENGINE_VERSION`) folded into the cache key and sidecar, so a later
# change to row/col extraction semantics is a new id rather than a silent reinterpretation
# of an already-resolved (and potentially already-cited, `ledger.md` §13.2) result.
_CSV_OP_PARAMS: frozenset[str] = frozenset({"row", "col"})

# The vcard property op (§6.2 `prop=`) is likewise a deterministic pure parse (never an
# external engine), versioned the same way (`transforms.vcard.ENGINE_VERSION`).
_VCARD_OP_PARAMS: frozenset[str] = frozenset({"prop"})

# The vcard card= member-extraction op (§12.11 `card=`) — a materially different derivation
# than `prop=` above (whole-card raw bytes vs one decoded property), so it carries its OWN
# version id (`transforms.vcard.CARD_ENGINE_VERSION`), checked as a separate branch below.
_VCARD_CARD_OP_PARAMS: frozenset[str] = frozenset({"card"})

# The mbox message-extraction op (§12.11 `msg=`) — pinned separator + un-stuffing semantics
# (`transforms.mbox.ENGINE_VERSION`).
_MBOX_OP_PARAMS: frozenset[str] = frozenset({"msg"})

# The archive path= member-extraction op (§12.11 `path=`, §6.2 "Member re-chaining") — pinned
# member-path resolution and the terminal textual decode, shared verbatim by the zip and tar
# transforms (`transforms.zip.ENGINE_VERSION` == `transforms.tar.ENGINE_VERSION`, both
# re-exporting the one canonical `ziparchive.ENGINE_VERSION`). Checked LAST among the per-param
# branches below (right before `else`): when `path=` re-chains into a further op that carries
# its OWN pin (a rechained CSV member's `row=`/`col=`, a rechained vcard's `prop=`, an HTML
# member's `el=`), that op's more-specific id wins — `archive-path@1` folds in only for the
# member-selection/terminal-decode step itself, when nothing more specific also matched.
_ARCHIVE_PATH_OP_PARAMS: frozenset[str] = frozenset({"path"})

# The HTML el= LIVE element-scoping op (§6.2, §12.11 `el=`) — the htmlel working-kind resolver
# path only, never the persisted-segment `address: el=N` read (`transforms.html.ENGINE_VERSION`).
_HTML_EL_OP_PARAMS: frozenset[str] = frozenset({"el"})

# The turn= unit op and its att= companion (§6.2) — the form-mapping unit-array resolution
# (`shape.units.ENGINE_VERSION`). RECORD-LEVEL (resolved by `_resolve_turn`, which recognizes
# a bare `turn=`/`turn=&att=` chain and returns before this function's per-param transform loop
# ever runs) — a `turn=` URI never reaches the generic engine-determination ladder below, so
# `_resolve_turn` folds `shape.units.ENGINE_VERSION` into its OWN cache key directly. This
# frozenset exists only so `_static_engine_version`'s per-param lookup (used by both
# `ops_for_media_type` and any record-level-op caller) recognizes "turn"/"att" too.
_UNITS_TURN_OP_PARAMS: frozenset[str] = frozenset({"turn", "att"})

# Working kinds whose final cache extension isn't known until the transform chain actually
# runs: `htmlel` resolves polymorphically to image|bytes (§6.2 `el=`); `video`/`audio`/
# `media` are ffmpeg-produced Paths whose extension depends on the source's container
# family (bare `time_range=`) or the `format=` token — neither predictable from the param
# chain alone the way every other op's output kind is. `memberchain` is the same problem one
# level down the address axis (§6.2 member re-chaining, defects 3+4): a `path=` member's real
# kind depends on ITS bytes/filename, sniffed only once its bytes are in hand — see
# `_rechain_member`.
_DEFERRED_EXTENSION_KINDS: frozenset[str] = frozenset(
    {"htmlel", "video", "audio", "media", "memberchain"}
)


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

    # `scene` (§6.2, 3.11): the record-level introspection view over this leaf's cut list —
    # the `probe` analogue for a timeline. Reads the STAMPED strategy (never a fresh
    # resolution, §7.2.1) and re-derives the spans under it. Record-level, JSON, single-param.
    if len(parsed.params) == 1 and parsed.params[0] == ("scene", None):
        return _resolve_scene(
            corpus_root, canonical_uri, parsed.hash, artifact_record, regenerate=regenerate
        )

    # Timeline ops on a promoted STREAM LEAF redirect through the container (§6.2's
    # lineage-chained resolution, §1.2's inheritance-through-lineage). An elementary stream
    # carries no container timing of its own — ffmpeg imputes a frame rate and reports no
    # duration — so a second of "leaf time" is not a second of the timeline the leaf's stored
    # addresses were computed in. The container holds the real timeline AND the shared one, so
    # the op runs there with `stream_id=` composed in. Without this, an address stored on a
    # leaf resolves against a timebase nobody measured it in.
    redirected = _stream_timeline_redirect(parsed, artifact_record)
    if redirected is not None:
        log.debug("stream-leaf timeline redirect: %s -> %s", canonical_uri, redirected)
        return resolve(
            redirected, corpus_root, regenerate=regenerate, store=store, transcriber=transcriber
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
    # (`corpus.mux.mux_stream`), never fall through to the raw container the generic
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
        param_names = ", ".join(sorted({k for k, _ in parsed.params}))
        raise NotImplementedError(
            f"param(s) {param_names!r} have no transformation pipeline for media_type "
            f"{media_type!r} (declare `working_kind:` on its mime schema, or add it to the "
            f"resolver table). Record-level ops — `body`, `members`, `turn=<N>`, "
            f"`turn=<N>&att=<M>` — work for every media type and never reach this ladder."
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
    elif any(k in _CSV_OP_PARAMS for k, _ in parsed.params):
        from .transforms import csv as csv_tf

        version_label = csv_tf.ENGINE_VERSION
    elif any(k in _VCARD_OP_PARAMS for k, _ in parsed.params):
        from .transforms import vcard as vcard_tf

        version_label = vcard_tf.ENGINE_VERSION
    elif any(k in _VCARD_CARD_OP_PARAMS for k, _ in parsed.params):
        from .transforms import vcard as vcard_tf

        version_label = vcard_tf.CARD_ENGINE_VERSION
    elif any(k in _MBOX_OP_PARAMS for k, _ in parsed.params):
        from .transforms import mbox as mbox_tf

        version_label = mbox_tf.ENGINE_VERSION
    elif any(k in _HTML_EL_OP_PARAMS for k, _ in parsed.params):
        from .transforms import html as html_tf

        version_label = html_tf.ENGINE_VERSION
    elif any(k in _ARCHIVE_PATH_OP_PARAMS for k, _ in parsed.params):
        from .transforms import zip as zip_tf

        version_label = zip_tf.ENGINE_VERSION
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
    # The record's attested `addressing:` stamp (§7.1): presence dispatches `el=` to the
    # 3.6 path grammar; absence keeps the frozen legacy filtered index (§12.28's
    # transition rule — the bare-integer spelling means different elements under the two
    # grammars, so the RECORD, never the value, decides which one reads it).
    el_addressing = records.el_addressing(artifact_record)
    if el_addressing is not None:
        ctx["el_addressing"] = el_addressing
    # `row=`/`col=` (§6.2, §7.1): the mime schema's declared `csv_dialect:` — the engine's
    # only source of delimiter/quoting/header-presence knowledge (`transforms.csv`).
    if initial_kind == "csv":
        ctx["csv_dialect"] = _csv_dialect_for(corpus_root, media_type)

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
    elif initial_kind in (
        "video", "audio", "epub", "zip", "tar", "mbox", "vcard", "message", "csv",
    ):
        # The working value is the artifact path itself: ffmpeg and the transcriber stream
        # from disk rather than loading the whole media into memory; the epub `spine`
        # transform opens the zip to select a content document and its image members; the
        # zip / tar `path=` transforms open the archive to extract a member; the mbox `msg=`
        # transform streams a single message out of the mailbox; the vcard `card=` transform
        # extracts one card's exact bytes from the `.vcf`; the message `part=` transform
        # decodes one MIME part of an email; the csv `row=` transform streams one data row
        # out of the delimited text (containment-aware — a promoted zip-member CSV streams
        # through `containment.ensure_local_bytes` exactly like any other member).
        working = artifact_binary
    else:
        raise NotImplementedError(f"initial kind {initial_kind!r} not yet supported")

    current_kind = initial_kind
    terminal_mime: str | None = None
    try:
        for param_idx, (key, value) in enumerate(parsed.params):
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
            # Member re-chaining (§6.2, defects 3+4): `path=` on a kept-whole archive
            # (zip/tar) always yields the registry's opaque `bytes` — re-detect the member's
            # real mime and re-enter the working-kind table so the chain can continue past it
            # (a PDF member takes `page=`/`text` same as a top-level artifact; a JSON/text
            # member decodes to plain text; an unrecognized member stays `bytes`, unchanged).
            if key == "path" and current_kind == "bytes":
                working, current_kind, pdf_doc, chain_mime = _rechain_member(
                    corpus_root, parsed, param_idx, working, ctx, pdf_doc
                )
                if chain_mime is not None:
                    terminal_mime = chain_mime
        # A terminal `pdfpage` (bare `page=N`, or `page=N&dpi=…`) renders to image, so a
        # segment's `address: page=N` image marker resolves to the page bytes as before.
        if current_kind == "pdfpage":
            working = _render_pdfpage(working, ctx)
            current_kind = "image"
        # A terminal `csvrow` (bare `row=N`, no trailing `col=`) renders to its exact raw
        # source text — mirroring `pdfpage`'s terminal-render contract, so a segment's
        # `address: row=N` marker resolves to the row's bytes exactly as `page=N` resolves
        # to the page image.
        if current_kind == "csvrow":
            working = working.raw
            current_kind = "text"
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
        elif cache_p is None:
            # A `memberchain`-deferred URI (§6.2, defects 3+4): the member's real final kind
            # was unknowable until `_rechain_member` ran, but it always lands on an ordinary
            # KIND_TO_EXTENSION-registered kind (image/text/json/bytes, or video/audio/media —
            # already handled above) — assign the cache path now that it's known.
            if current_kind not in KIND_TO_EXTENSION:
                raise NotImplementedError(
                    f"final output kind {current_kind!r} has no cache extension registered"
                )
            cache_p = furi.cache_path(corpus_root, urihash_value, KIND_TO_EXTENSION[current_kind])
    finally:
        # pypdfium2's PdfDocument is reference-counted; close explicitly.
        if pdf_doc is not None:
            pdf_doc.close()

    # `htmlel` and `memberchain` resolve their concrete extension only after the chain runs
    # (the latter depends on a member's own sniffed mime, §6.2 defects 3+4), so the predicted
    # sentinel legitimately differs from `current_kind` for those two; the muxing kinds are NOT
    # exempted — `current_kind` must still equal the predicted `video`/`audio`/`media`, a real
    # correctness check.
    if final_kind not in ("htmlel", "memberchain") and current_kind != final_kind:
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


#: Ops whose meaning depends on a TIMELINE the leaf's own bytes cannot supply. `stream_id`/`cut`
#: are addressing/mode config and ride along.
#:
#: Two deliberate absences, both load-bearing:
#:
#: `format=` — an encoding change addresses no timeline, so a leaf's own playable rendering
#: stays a leaf operation.
#:
#: `transcribe` — an AUDIO elementary stream is not in the same position as a video one. ADTS
#: and the Opus pinned framing are self-framing at exact, fixed per-packet durations derived
#: from the sampling rate, so an audio leaf's timeline is well-defined from its own bytes;
#: Annex-B video carries no timing whatsoever. Redirecting would also be actively worse: the
#: container has no `(video, transcribe)` transform, so the chain would have to route through
#: `extract_audio`, which RE-ENCODES to mp3 — transcribing a lossy derivative of the member
#: instead of the member's own pinned identity bytes. Work on the member's bytes when they are
#: self-sufficient; reach for the container only when they are not.
_TIMELINE_OP_PARAMS: frozenset[str] = frozenset({"frame", "time", "time_range", "scenes"})


def _stream_timeline_redirect(parsed: Any, artifact_record: Any) -> str | None:
    """The container URI a timeline op on a stream leaf should run against, or None.

    Returns None — meaning "resolve normally" — unless ALL of: the URI carries a timeline op,
    the record has a containment-lineage origin naming exactly one container stream, and the
    URI does not already select a stream (a leaf that names `stream_id=` itself is asking for
    something else entirely, and guessing at it would be worse than failing).

    The rewritten URI is `corpus://<container>?stream_id=<N>&<the original params>` — the
    canonical order §6.2 pins (select → cut → convert → size) with the selection supplied from
    lineage instead of by the caller.
    """
    from corpus import cut as cut_mod

    if not parsed.params or not any(k in _TIMELINE_OP_PARAMS for k, _ in parsed.params):
        return None
    if any(k == "stream_id" for k, _ in parsed.params):
        return None
    lineage = cut_mod.stream_lineage(artifact_record)
    if lineage is None:
        return None
    container_id, stream_address = lineage
    tail = "&".join(k if v is None else f"{k}={v}" for k, v in parsed.params)
    return f"corpus://{container_id}?{stream_address}&{tail}"


def _resolve_scene(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    artifact_record: Any,
    *,
    regenerate: bool,
) -> Path:
    """Materialize the `scene` derivation op (§6.2, 3.11): this leaf's cut list as JSON.

    The introspection surface the authoring pass reads before deciding anything — `probe`'s
    role for a PDF page, on a timeline. It reports the resolved strategy, each span with its
    address and duration, and the degeneracy signals, so the pass can tell "36 real slide
    changes" from "226 frames of a scrolling terminal" without re-running a detector by hand.

    Two properties are deliberate. It runs the **stamped** strategy, so this op can never be
    the route by which a record gets silently re-cut under a strategy that moved (§7.2.1). And
    it reports `unresolved: true` rather than failing when there is no stamp — an unstamped
    leaf is a legitimate state, and a caller asking "how is this cut?" deserves the answer
    "it isn't yet" instead of an exception.
    """
    import json as _json

    from corpus import cut as cut_mod
    from corpus.draft import video_stream as _vs

    urihash_value = furi.urihash(canonical_uri)
    cache_p = furi.cache_path(corpus_root, urihash_value, "json")
    if cache_p.is_file() and not regenerate:
        return cache_p.resolve()

    stamp = records.cutting(artifact_record)
    payload: dict[str, Any] = {
        "record": source_hash,
        "media_type": records.media_type_for(artifact_record),
        "cutting": stamp,
    }
    try:
        addresses, spans = _vs.addresses_for_stamp(corpus_root, artifact_record)
    except (cut_mod.Unresolved, NotImplementedError) as exc:
        payload.update({"unresolved": True, "reason": str(exc), "spans": []})
    else:
        payload["unresolved"] = False
        payload["spans"] = [
            {
                "index": i,
                "address": address,
                "start": start,
                "end": end,
                "seconds": round(end - start, 3),
            }
            for i, (address, (start, end)) in enumerate(zip(addresses, spans, strict=True), 1)
        ]
        attested = (stamp or {}).get("cuts")
        if isinstance(attested, int) and attested != len(spans):
            payload["drift"] = {"attested_cuts": attested, "derived_cuts": len(spans)}
        payload["signals"] = [
            {"id": s.id, "detail": s.detail}
            for s in cut_mod.degeneracy_signals(
                spans, float((stamp or {}).get("duration") or 0.0) or _span_end(spans),
                raw_cut_count=max(len(spans) - 1, 0),
            )
        ]
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    cache_p.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_sidecar(corpus_root, canonical_uri, source_hash, cache_p, "json")
    return cache_p.resolve()


def _span_end(spans: list[tuple[float, float]]) -> float:
    return spans[-1][1] if spans else 0.0


def _resolve_members(
    corpus_root: Path,
    canonical_uri: str,
    source_hash: str,
    artifact_record: Any,
    *,
    regenerate: bool,
) -> Path:
    """Materialize the `members` derivation op (§6.2): the record's member roster as JSON,
    **with its full descriptors** — the address in the transport's own axis, the member's blake3
    `transport`, its size and MIME, plus every mechanically-readable per-member fact the format
    exposes (pixel dimensions, verbatim `alt`, member filename, an email member's
    `from`/`subject`/`date`, a vCard's display name).

    *(3.4)* This is where those descriptors LIVE now. The stored roster is a four-key index
    (spec §4.3.1.4) precisely so the cross-record questions stay cheap, which leaves this op as
    the surface a normalize pass consults to see what an artifact carries — the block by design
    says less. So the op re-runs the drafter's member extraction over the artifact rather than
    projecting the stored rows: **one extractor, two projections.** Attestation keeps the four
    keys; this keeps everything. Both read the same function, so they cannot drift.

    Falls back to the stored rows when the artifact cannot be read (bytes not resident, no
    drafter for the type). The fallback is lossy — four keys, no descriptors — and says so in
    the payload, because a caller that silently got less than it asked for is worse than one
    told the surface was degraded. Cached like any resolver result."""
    urihash_value = furi.urihash(canonical_uri)
    cache_p = furi.cache_path(corpus_root, urihash_value, "json")
    if cache_p.is_file() and not regenerate:
        return cache_p.resolve()

    rows: list[dict[str, Any]] = []
    derived_from = "artifact"
    try:
        import copy

        from corpus import derive as _derive
        from corpus.draft import mbox_manifest as _mbox

        # Derive on a SCRATCH copy with the roster cleared, and hand the mailbox its declared
        # ordinals. Both halves are needed, and the mbox manifest is why: it is selective AND
        # cumulative (§12.11), so its drafter returns the DELTA over what the record already
        # declares — deriving against the live record yielded an empty roster for a mailbox with
        # 153 declared messages, and deriving from a cleared record without the ordinals yields
        # an empty one too, since nothing asks for any message. Clearing + re-declaring is what
        # makes this op return the FULL roster for every format uniformly. (`derive_body` clears
        # the same way for the same reason.) Caught by the parity battery against the real
        # corpus, not by reading the code.
        scratch = copy.deepcopy(artifact_record)
        declared = _mbox.declared_ordinals(artifact_record) or None
        scratch.metadata["_embeds"] = []
        _build, result, _mt, _bin, _sid = _derive.build_content_zone(
            scratch, corpus_root, messages=declared
        )
        rows = list(result.get("embeds") or [])
    except Exception as exc:  # parse tolerantly (spec §3): report the degradation, never fail
        derived_from = f"stored-roster ({type(exc).__name__})"
        rows = list(records.iter_members(artifact_record))

    members: list[dict[str, Any]] = []
    for row in rows:
        addr = row.get("address")
        fields = dict(row.get("fields") or {})
        size = fields.pop("bytes", None)
        for one in addr if isinstance(addr, list) else [addr]:
            entry = {
                "address": one,
                "transport": row.get("transport"),
                "media_type": row.get("media_type"),
                "bytes": size,
            }
            # Descriptors keep their own names, after the four so the shape a reader already
            # knows stays at the front of every object.
            entry.update({k: v for k, v in fields.items() if v is not None})
            members.append(entry)
    payload = {"count": len(members), "derived_from": derived_from, "members": members}

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
    extraction bytes via `corpus.mux.mux_stream` — never the raw container, and never
    an ffmpeg engine version folded into the cache key (this is pure byte-work, §12.20 item 1;
    contrast the engine-versioned muxing-contract ops that COMPOSE `stream_id=` via `-map`,
    §6.2). Single-track only: a comma-list or repeated `stream_id=` has no meaning for pure
    identity extraction (you cannot concatenate two different codecs' elementary bytes) — that
    combination is only valid alongside a muxing-contract op.

    The extension is cheap to predict ahead of the cache check (unlike the muxing contract's
    deferred-extension kinds, §12.20 item 1's engine path): `probe_streams` reads only the
    small `moov` subtree, never sample data."""
    from . import mux, streams

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
            for chunk in mux.mux_stream(artifact_binary, stream_id, workdir=cache_p.parent):
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
        # `turn=A-B` is segment-envelope notation (§4.3.2.1), not a resolver op — the unit
        # op is single-index by contract (§6.2: "the verbatim N-th unit"). Refuse it here
        # with the real reason; falling through to the mime ladder would misreport it as a
        # missing transformation pipeline (#146's misleading error).
        value = str(params[0][1] or "")
        if re.fullmatch(r"\d+-\d+", value):
            raise ValueError(
                f"turn={value}: the unit op takes a single 1-indexed unit (§6.2) — a range "
                f"is segment-address notation; scope quotes against the record's stored "
                f"segments instead"
            ) from None
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
    # The mapping's declared `text_encoding` repair (§7.2, e.g. Meta's `meta-mojibake` export
    # bug) is shared with the `conversation` shaper's per-turn envelope rendering
    # (`shape/conversation.py`) — applied here too so `turn=N` hands back the SAME repaired
    # text a human reading the formed record's segment sees, not the raw mangled bytes.
    msg = units.repair_json_strings(msg, mapping)

    if att_m is None:
        # `units-turn@1` (§6.4 / `ledger.md` §13.2's op-version pin) folds into the cache key
        # exactly like the generic per-param ladder does for csv/vcard/mbox/zip/tar/html
        # (`resolve()`'s `key_uri = f"{canonical_uri}|engine=..."` above) — `turn=` never
        # reaches that ladder (it short-circuits before the mime-pipeline dispatch, `resolve()`
        # above), so `_resolve_turn` folds its own pin directly. A later change to unit-array
        # indexing auto-invalidates any already-cached `turn=N` result.
        key_uri = f"{canonical_uri}|engine={units.ENGINE_VERSION}"
        urihash_value = furi.urihash(key_uri)
        cache_p = furi.cache_path(corpus_root, urihash_value, "json")
        if cache_p.is_file() and not regenerate:
            return cache_p.resolve()
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        cache_p.write_text(json.dumps(msg, indent=2) + "\n", encoding="utf-8")
        _write_sidecar(
            corpus_root, canonical_uri, source_hash, cache_p, "json",
            version_label=units.ENGINE_VERSION,
        )
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


# ---------- member re-chaining (§6.2, defects 3+4) ---------- #

# JSON-family mimes with no `working_kind:` schema entry (there's no further pipeline op to
# chain into — a JSON payload isn't paginated/cropped/etc.) that should still print/cache as
# text rather than the generic opaque `bytes` a raw member defaults to.
_TEXTUAL_MEMBER_JSON_MIMES: frozenset[str] = frozenset(
    {"application/json", "application/x-ndjson"}
)


def _member_text_kind(sniffed_mime: str) -> str | None:
    """The resolver kind an already-textual member mime decodes to, or None when the mime
    isn't textual (stays opaque `bytes`, today's behavior). `json` (not `text`) for the JSON
    family so the cache extension is `.json` and `corpus resolve --print` streams it as such
    (defect 3); plain `text` for anything else `text/*`-shaped."""
    if sniffed_mime in _TEXTUAL_MEMBER_JSON_MIMES:
        return "json"
    if sniffed_mime.startswith("text/"):
        return "text"
    return None


def _init_member_working_value(kind: str, path: Path) -> Any:
    """Construct the initial working value for a re-chained container member (§6.2) — the
    member-address counterpart of `resolve()`'s own top-level working-value initialization,
    over the member's materialized cache file rather than the record's artifact. Mirrors that
    branch exactly (same kinds, same construction) so a PDF/HTML/image/video/… member behaves
    identically to a standalone record of the same type."""
    if kind == "pdf":
        doc = pdfium.PdfDocument(str(path))
        doc.init_forms()
        return doc
    if kind == "html":
        from bs4 import BeautifulSoup

        return BeautifulSoup(path.read_bytes(), "html.parser")
    if kind == "image":
        with Image.open(path) as im:
            im.load()
            return im.copy()
    if kind in ("video", "audio", "epub", "zip", "tar", "mbox", "vcard", "message", "csv"):
        return path
    raise NotImplementedError(f"member working kind {kind!r} not yet supported")


def _rechain_member(
    corpus_root: Path,
    parsed: furi.ParsedURI,
    param_idx: int,
    data: bytes,
    ctx: transforms.RenderContext,
    pdf_doc: pdfium.PdfDocument | None,
) -> tuple[Any, str, pdfium.PdfDocument | None, str | None]:
    """Re-detect a `path=`-extracted member's real mime (§6.2) and, when a further transform
    param follows in the chain, re-enter the working-kind table (`_working_kind_for`) so
    resolution continues in the member's OWN pipeline — a PDF member takes `page=`/`text` just
    like a top-level artifact would (defect 4). A TERMINAL `path=` (nothing follows) never
    promotes to a full pipeline object: that would risk a silent, unrequested re-encode of a
    member `resolve` never asked to transform (an image member re-saved as PNG, losing its
    original bytes identity) — a zip/tar member is documented to serve raw bytes verbatim
    (`transforms/zip.py`/`transforms/tar.py`) except for the one case defect 3 flags: an
    already-textual member (JSON/text) prints its decoded text rather than a `.bin` path.
    Malformed/unrecognized members are never fatal here — they degrade to the original opaque
    `bytes`, exactly as before this fix.

    Returns `(working, kind, pdf_doc, mime_override)`. `mime_override` is the member's own
    sniffed mime for the resolver's cache sidecar — set only in the terminal-decode case
    (where the member's own mime IS the final result's mime); the full-pipeline case leaves it
    None so a later op in the chain (or the default `KIND_TO_MIME` table) determines it
    normally, exactly as for a top-level artifact.
    """
    ref = str(parsed.params[param_idx][1] or "")
    has_more = any(k not in _NOOP_PARAMS for k, _ in parsed.params[param_idx + 1 :])
    sniffed_mime = mime_mod.sniff_head(data, ref or None)

    if has_more:
        new_kind = _working_kind_for(corpus_root, sniffed_mime)
        if new_kind is not None:
            member_ext = mime_mod.extension_for(sniffed_mime)
            # Cached under the prefix-canonical URI up to and including THIS `path=` step, so
            # a repeat resolve of a different follow-on op over the same member (`path=x.pdf
            # &page=2` after `path=x.pdf&page=1`) never re-extracts from the container, and a
            # distinct member/position never collides (mirrors `containment._member_cache_path`
            # one level below the promoted-record axis).
            partial_uri = furi.canonical(
                furi.ParsedURI(hash=parsed.hash, params=parsed.params[: param_idx + 1])
            )
            # The extraction engine folds into THIS key too, exactly as it does into the
            # addressable outer key in `resolve()`: without it an `archive-path@1` bump
            # would leave this staging file behind to serve pre-bump member bytes into a
            # re-chained continuation (a zip-embedded PDF's `page=`) — stale bytes reached
            # through a fresh outer key, which is the one failure the pin exists to prevent.
            staging_key = f"{partial_uri}|engine={ziparchive.ENGINE_VERSION}"
            member_path = furi.cache_path(corpus_root, furi.urihash(staging_key), member_ext)
            if not member_path.is_file():
                member_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = member_path.with_name(f"{member_path.name}.tmp")
                tmp.write_bytes(data)
                tmp.replace(member_path)
            working = _init_member_working_value(new_kind, member_path)
            if new_kind == "pdf":
                pdf_doc = working
            if new_kind == "csv":
                ctx["csv_dialect"] = _csv_dialect_for(corpus_root, sniffed_mime)
            # PDF text/probe ops read the source from disk via pypdf — point them at the
            # MEMBER's own file, not the container's (mirrors the top-level `resolve()` setup).
            ctx["artifact_path"] = member_path
            return working, new_kind, pdf_doc, None

    text_kind = _member_text_kind(sniffed_mime)
    if text_kind is not None:
        return data.decode("utf-8", errors="replace"), text_kind, pdf_doc, sniffed_mime
    return data, "bytes", pdf_doc, None


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
        # `path=` on a kept-whole archive (zip/tar) always yields opaque `bytes` from the
        # registry's point of view (transforms/zip.py, transforms/tar.py) — but the member it
        # extracts may itself chain further (a PDF member's `page=`/`text`, defect 4), and
        # that depends on the member's own bytes/filename, unknowable from the param chain
        # alone. Defer, like `htmlel`/`video`/`audio`/`media` (`_rechain_member` in `resolve()`
        # does the real work at resolve time).
        if key == "path" and current in ("zip", "tar"):
            return "memberchain"
        handler, _promote = _resolve_handler(current, key)
        if handler is None:
            raise ValueError(f"transform {key!r} not applicable to working kind {current!r}")
        current = handler.output_kind
    # A terminal `pdfpage` renders to an image (see resolve()).
    if current == "pdfpage":
        current = "image"
    # A terminal `csvrow` renders to raw text (see resolve()).
    if current == "csvrow":
        current = "text"
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


# ---------- op introspection (§6.2 — `corpus inspect`'s resolver-ops section) ---------- #


@dataclass(frozen=True)
class ResolverOp:
    """One functional-URI transform reachable for a media type's resolver pipeline —
    surfaced for read-only introspection (`corpus inspect`), never used by `resolve()`
    itself. `engine_version` is the op's STATIC version pin (`engine_version_for_param`,
    below — `transforms.csv.ENGINE_VERSION`, `transforms.vcard.ENGINE_VERSION`/
    `CARD_ENGINE_VERSION`, `transforms.mbox.ENGINE_VERSION`, `transforms.zip.ENGINE_VERSION`,
    `transforms.html.ENGINE_VERSION`) when one applies to this exact param — None for an
    unpinned op and for the runtime-determined engines (`transcribe`'s adapter, the ffmpeg
    muxing family), which inspection deliberately does not resolve (read-only; no shell-out,
    no config lookup)."""

    param: str
    from_kind: str
    output_kind: str
    engine_version: str | None


def working_kind_for(corpus_root: Path, media_type: str) -> str | None:
    """Public alias of `_working_kind_for` — the resolver pipeline's initial working kind
    for a media type, or None when nothing is registered. Exposed so a read-only caller
    (`corpus inspect`) can report it without reaching into the private name."""
    return _working_kind_for(corpus_root, media_type)


def ops_for_media_type(corpus_root: Path, media_type: str) -> list[ResolverOp]:
    """Every functional-URI transform reachable for `media_type`'s resolver pipeline: the
    initial working kind (`_working_kind_for`) plus every follow-on kind the param chain can
    reach — a csv `row=` op's `csvrow` output takes `col=`; a pdf `page=` op's `pdfpage`
    output takes `render`/`text`/`words`/`probe`; an html `el=` op's `htmlel` output takes
    every image-kind op too, through the resolver's own `pdfpage`/`htmlel` auto-promotion
    (`_resolve_handler`, mirrored here as an explicit reachable-kind edge since no registry
    entry names it directly).

    Derived live from `transforms.REGISTRY` — never a hardcoded op table, so a new
    transform module registering itself is picked up with zero changes here. Returns `[]`
    when the mime has no registered pipeline (§7.1 `working_kind:`) — itself the honest
    answer for a mime the resolver has no transform for."""
    initial_kind = _working_kind_for(corpus_root, media_type)
    if initial_kind is None:
        return []

    out: list[ResolverOp] = []
    seen_kinds: set[str] = set()
    queue: list[str] = [initial_kind]
    while queue:
        kind = queue.pop(0)
        if kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        for (in_kind, key), handler in transforms.REGISTRY.items():
            if in_kind != kind:
                continue
            out.append(
                ResolverOp(
                    param=key,
                    from_kind=in_kind,
                    output_kind=handler.output_kind,
                    engine_version=engine_version_for_param(key),
                )
            )
            queue.append(handler.output_kind)
        # The resolver's own auto-promotion (`_resolve_handler`, above): an intermediate
        # `pdfpage`/`htmlel` selector takes every image-kind op too (rendered to an image
        # first) even where — as for `htmlel` — no registry entry makes "image" a directly
        # reachable follow-on kind.
        if kind in ("pdfpage", "htmlel"):
            queue.append("image")
    return out


def engine_version_for_param(key: str) -> str | None:
    """`key`'s (an axis param name, e.g. `"row"`/`"card"`/`"turn"`) statically-declared engine
    pin, or None when the axis carries no pin. Reuses the exact per-param scoping the
    resolver's own cache-key folding uses (`_CSV_OP_PARAMS`, `_VCARD_OP_PARAMS`, `_MBOX_OP_PARAMS`,
    `_ARCHIVE_PATH_OP_PARAMS`, `_HTML_EL_OP_PARAMS`, `_UNITS_TURN_OP_PARAMS`, above) so this can
    never drift from what a real `resolve()` actually keys on.

    Public: `ops_for_media_type` uses it for every mime-pipeline (registry-reachable) op below,
    and a caller needing a pin for a RECORD-LEVEL op that bypasses `transforms.REGISTRY`
    entirely — `turn=`/`att=`, resolved by `_resolve_turn` — can call it directly with `"turn"`
    or `"att"` rather than assuming registry membership (`ops_for_media_type`'s docstring: a
    record-level op is never discoverable through its registry walk, since reachability there
    depends on the record's origin-declared form mapping, not its media type)."""
    if key in _CSV_OP_PARAMS:
        from .transforms import csv as csv_tf

        return csv_tf.ENGINE_VERSION
    if key in _VCARD_OP_PARAMS:
        from .transforms import vcard as vcard_tf

        return vcard_tf.ENGINE_VERSION
    if key in _VCARD_CARD_OP_PARAMS:
        from .transforms import vcard as vcard_tf

        return vcard_tf.CARD_ENGINE_VERSION
    if key in _MBOX_OP_PARAMS:
        from .transforms import mbox as mbox_tf

        return mbox_tf.ENGINE_VERSION
    if key in _ARCHIVE_PATH_OP_PARAMS:
        from .transforms import zip as zip_tf

        return zip_tf.ENGINE_VERSION
    if key in _HTML_EL_OP_PARAMS:
        from .transforms import html as html_tf

        return html_tf.ENGINE_VERSION
    if key in _UNITS_TURN_OP_PARAMS:
        from .shape import units as units_tf

        return units_tf.ENGINE_VERSION
    return None


# `row=`/`col=` (§6.2) never hardcode delimiter/quoting/header-presence — every field here
# is overridden by the mime schema's own `csv_dialect:` (§7.1, `text_csv.yaml`) when declared.
_DEFAULT_CSV_DIALECT: dict[str, Any] = {
    "delimiter": ",",
    "quotechar": '"',
    "doublequote": True,
    "header_row": True,
    "quoting": "minimal",
}


def _csv_dialect_for(corpus_root: Path, media_type: str) -> dict[str, Any]:
    """The CSV dialect config for a media type: the mime schema's declared `csv_dialect:`
    deep-merged over the RFC 4180 / Excel-dialect default, so a schema may override just
    one field (e.g. `delimiter: ";"`) without restating the rest."""
    from . import schemas

    schema = schemas.load_mime_schema(corpus_root, media_type) or {}
    declared = schema.get("csv_dialect")
    merged = dict(_DEFAULT_CSV_DIALECT)
    if isinstance(declared, dict):
        merged.update(declared)
    return merged


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
