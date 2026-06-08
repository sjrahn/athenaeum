"""Corpus configuration — optional `<corpus-root>/corpus.toml` + env-var overrides.

A corpus may be deployed entirely with **no configuration** — the package's defaults
are `LocalArtifactStore` for byte storage and `NoOpTranscriber` for audio transcription.
A `corpus.toml` at the corpus root, plus a small set of environment variables, override
those defaults.

File schema (all keys optional):

    [corpus]
    # nothing required here

    [corpus.store]
    backend = "local"            # "local" (default) | "azure" | "s3"
    # backend-specific:
    account   = "..."            # azure: storage account name
    container = "..."            # azure: container name
    bucket    = "..."            # s3: bucket name
    region    = "..."            # s3: AWS region
    prefix    = "..."            # azure/s3: optional key prefix

    [corpus.transcription]
    adapter  = "noop"            # "noop" (default) | "http-whisper"
    base_url = "..."             # http-whisper: server base URL

    [corpus.capture]
    default_transport = "headless"   # browser transport when overlay + --transport unset

    [corpus.wiki]
    zim = "/path/to/wikipedia_en_all.zim"   # local Wikipedia ZIM for the concept KB (corpus.wiki)

Env vars override the file (later wins):

    CORPUS_STORE          → store.backend
    CORPUS_AZURE_ACCOUNT  → store.account
    CORPUS_AZURE_CONTAINER→ store.container
    CORPUS_AZURE_PREFIX   → store.prefix
    CORPUS_S3_BUCKET      → store.bucket
    CORPUS_S3_REGION      → store.region
    CORPUS_S3_PREFIX      → store.prefix
    CORPUS_TRANSCRIBE     → transcription.adapter
    WHISPER_BASE_URL      → transcription.base_url (back-compat)
    CORPUS_CAPTURE_TRANSPORT → capture.default_transport
    ATH_WIKI_ZIM          → wiki.zim

`load_config(corpus_root)` returns a frozen `CorpusConfig` with sub-dicts
(`store`, `transcription`, `capture`, `wiki`) carrying the merged settings. The ZIM is
shared across corpora, so `ATH_WIKI_ZIM` (or a server flag) is the usual source;
`[corpus.wiki].zim` is an optional per-corpus override.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CorpusConfig:
    """Merged file + env configuration for a corpus.

    `store` always carries at least `{"backend": "local"|"azure"|"s3"}`; backend-
    specific keys are present only when configured.
    `transcription` always carries at least `{"adapter": "noop"|"http-whisper"}`.
    """

    store: dict[str, Any] = field(default_factory=dict)
    transcription: dict[str, Any] = field(default_factory=dict)
    capture: dict[str, Any] = field(default_factory=dict)
    wiki: dict[str, Any] = field(default_factory=dict)


def load_config(corpus_root: Path) -> CorpusConfig:
    """Load `<corpus_root>/corpus.toml` (if present) and apply env overrides.

    Returns a fully-defaulted `CorpusConfig` so callers can dispatch on
    `cfg.store["backend"]` and `cfg.transcription["adapter"]` without
    KeyError handling.
    """
    file_data: dict[str, Any] = {}
    cfg_file = corpus_root / "corpus.toml"
    if cfg_file.is_file():
        try:
            file_data = tomllib.loads(cfg_file.read_text("utf-8")).get("corpus", {}) or {}
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
            file_data = {}

    file_store = dict(file_data.get("store") or {})
    file_transcription = dict(file_data.get("transcription") or {})
    file_capture = dict(file_data.get("capture") or {})
    file_wiki = dict(file_data.get("wiki") or {})

    store = _resolve_store_section(file_store)
    transcription = _resolve_transcription_section(file_transcription)
    capture = _resolve_capture_section(file_capture)
    wiki = _resolve_wiki_section(file_wiki)

    return CorpusConfig(store=store, transcription=transcription, capture=capture, wiki=wiki)


def _resolve_store_section(file_store: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(file_store)
    if "backend" not in out:
        out["backend"] = "local"

    # Env-var overrides (later wins).
    if v := os.environ.get("CORPUS_STORE"):
        out["backend"] = v
    for env_key, cfg_key in (
        ("CORPUS_AZURE_ACCOUNT", "account"),
        ("CORPUS_AZURE_CONTAINER", "container"),
        ("CORPUS_AZURE_PREFIX", "prefix"),
        ("CORPUS_S3_BUCKET", "bucket"),
        ("CORPUS_S3_REGION", "region"),
        ("CORPUS_S3_PREFIX", "prefix"),
    ):
        if v := os.environ.get(env_key):
            out[cfg_key] = v

    backend = str(out["backend"]).strip().lower()
    if backend not in ("local", "azure", "s3"):
        raise ValueError(
            f"unknown store backend {backend!r}; must be local | azure | s3."
        )
    out["backend"] = backend
    return out


def _resolve_transcription_section(file_t: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(file_t)
    if "adapter" not in out:
        out["adapter"] = "noop"

    if v := os.environ.get("CORPUS_TRANSCRIBE"):
        out["adapter"] = v
    # Back-compat: the reference's whisper.py read WHISPER_BASE_URL.
    if v := os.environ.get("WHISPER_BASE_URL"):
        out.setdefault("base_url", v)

    adapter = str(out["adapter"]).strip().lower()
    if adapter not in ("noop", "http-whisper"):
        raise ValueError(
            f"unknown transcription adapter {adapter!r}; must be noop | http-whisper."
        )
    out["adapter"] = adapter
    return out


def _resolve_capture_section(file_c: dict[str, Any]) -> dict[str, Any]:
    """Resolve the `[corpus.capture]` section. Video-host routing is no longer a
    config concern — it is declared per host in the origin overlay's
    `capture.capturer:` field (no hardcoded host list)."""
    out: dict[str, Any] = dict(file_c)

    # default_transport: the browser transport applied when a capture recipe (and
    # the CLI `--transport`) leave it unset. File `default_transport` + env
    # `CORPUS_CAPTURE_TRANSPORT` (env wins). Absent → key omitted (browser default).
    transport = str(file_c.get("default_transport") or "").strip().lower()
    if env := os.environ.get("CORPUS_CAPTURE_TRANSPORT"):
        transport = env.strip().lower()
    if transport:
        if transport not in ("headless", "headed", "cdp"):
            raise ValueError(
                f"unknown default_transport {transport!r}; use headless | headed | cdp."
            )
        out["default_transport"] = transport
    return out


def _resolve_wiki_section(file_w: dict[str, Any]) -> dict[str, Any]:
    """Resolve the `[corpus.wiki]` section — the local Wikipedia ZIM for the concept KB.

    `zim` is a filesystem path to a Kiwix ZIM. The ZIM is shared across corpora, so the
    `ATH_WIKI_ZIM` env var (or a server flag) is the usual source; the file key is a
    per-corpus override. Absent → key omitted (the KB is simply unavailable)."""
    out: dict[str, Any] = dict(file_w)
    if env := os.environ.get("ATH_WIKI_ZIM"):
        out["zim"] = env
    return out
