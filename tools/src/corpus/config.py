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

    [[corpus.location]]              # additional byte roots (spec §12.1.1, v21/v22)
    name = "..."                     # required, unique
    kind = "store"                   # required: "attached" | "store"
    path = "/abs/path"               # required, must be absolute (local only — a
                                      # "remote" key is accepted syntactically but
                                      # rejected at load: rclone transport is ticket
                                      # #204, not yet implemented)
    ingest = ["application/x-openzim"]   # store only, optional: format list claims
                                          # these media types as ingest destinations
    # ingest = true                  # store only, optional: this location is the
                                      # DEFAULT ingest destination (at most one
                                      # location may declare it) — mutually exclusive
                                      # with the list form above
    ingest_origins = ["download.geofabrik.de"]   # store only, optional (v23): origin
                                      # overlay ids claiming this location as ingest
                                      # destination for artifacts whose minting origin
                                      # matched one — beats `ingest` format claims;
                                      # composes freely with `ingest`
    manifest = true                  # attached only, optional (v24): the tree presents
                                      # its own manifest — a residence scanner on the
                                      # remote host publishes
                                      # `<path>/.athenaeum/manifest.sqlite`, and attest
                                      # reads it instead of walking
    cost = 20                        # both kinds, optional (v25): route-preference —
                                      # any non-negative integer, lower is nearer;
                                      # undeclared defaults preserve today's class
                                      # order (store nearer than attached)

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

`load_config(corpus_root)` returns a frozen `CorpusConfig` with sub-dicts
(`store`, `transcription`, `capture`) carrying the merged settings.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocationConfig:
    """One `[[corpus.location]]` table (spec §12.1.1, v21/v22) — an additional byte
    root beyond the co-located `artifacts/` tree. `kind` is `"attached"` (operator-
    managed, files stay in place) or `"store"` (content-addressed `<shard>/<hash>.<ext>`
    tree the corpus writes — local path only this wave; a `remote =` key is rejected at
    load, ticket #204).

    `ingest_types` / `ingest_default` / `ingest_origins` are meaningful only on
    `kind == "store"` — the placement policy (`corpus.placement`, v22/v23): a non-empty
    `ingest_types` claims those media types as this location's ingest destination;
    `ingest_default` (at most one location corpus-wide) makes this the destination for
    everything no format list claims; `ingest_origins` (v23) claims a list of origin
    overlay ids (spec §7.2) — an artifact whose minting origin resolved to one of them
    lands here, outranking a format claim. All empty/False is the common case — a store
    location with no placement role, resolved only, never a write destination.
    `ingest_origins` composes freely with `ingest_types`/`ingest_default` — a location
    may declare either, both, or neither axis.

    `manifest` (spec §12.1.1, v24) is meaningful only on `kind == "attached"`: `true`
    declares that the tree **presents its own manifest** — a residence scanner running
    on the remote host publishes `<path>/.athenaeum/manifest.sqlite` — so `corpus
    location attest` reads that manifest instead of walking the tree itself.

    `cost` (spec §12.1.1, v25 "Route preference" amendment) is meaningful on BOTH
    kinds: an optional non-negative integer, lower is nearer. Undeclared (`None`), the
    class default applies — see `effective_cost` — which preserves today's resolution
    order for a zero-config deployment. A declaration only ever reorders WITHIN a route
    class (§12.1.1); it never promotes an attached location ahead of a store location."""

    name: str
    kind: str
    path: Path
    ingest_types: tuple[str, ...] = ()
    ingest_default: bool = False
    ingest_origins: tuple[str, ...] = ()
    manifest: bool = False
    cost: int | None = None


#: Class-default costs applied by `effective_cost` when a location declares no `cost`
#: (spec §12.1.1, v25): preserves today's resolution order — the co-located tree
#: (implicitly cost 0, never a `LocationConfig` at all) nearest, then store locations,
#: then attached — for a zero-config deployment.
_DEFAULT_COST_STORE = 10
_DEFAULT_COST_ATTACHED = 20


def effective_cost(loc: LocationConfig) -> int:
    """A location's resolver-preference cost (spec §12.1.1, v25 "Route preference"):
    the declared `cost` if any, else a class default — `10` for `kind == "store"`,
    `20` for `kind == "attached"`. These defaults exist only to preserve today's
    resolution order when nothing is declared; a declaration reorders WITHIN a route
    class (a remote store costlier than a local one), it never promotes a route class
    past another — cross-class comparison never actually happens because each caller
    (`placement.find_in_stores`, `locationindex.route_for`) only ever orders locations
    of one kind at a time, per the resolver's own route-class sequence."""
    if loc.cost is not None:
        return loc.cost
    return _DEFAULT_COST_STORE if loc.kind == "store" else _DEFAULT_COST_ATTACHED


@dataclass(frozen=True)
class CorpusConfig:
    """Merged file + env configuration for a corpus.

    `store` always carries at least `{"backend": "local"|"azure"|"s3"}`; backend-
    specific keys are present only when configured.
    `transcription` always carries at least `{"adapter": "noop"|"http-whisper"}`.
    `locations` is empty when no `[[corpus.location]]` tables are declared — every
    existing behavior is unchanged for a corpus that declares none.
    """

    store: dict[str, Any] = field(default_factory=dict)
    transcription: dict[str, Any] = field(default_factory=dict)
    capture: dict[str, Any] = field(default_factory=dict)
    locations: tuple[LocationConfig, ...] = field(default_factory=tuple)


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
    file_locations = file_data.get("location") or []

    store = _resolve_store_section(file_store)
    transcription = _resolve_transcription_section(file_transcription)
    capture = _resolve_capture_section(file_capture)
    locations = _resolve_locations_section(file_locations)

    return CorpusConfig(
        store=store, transcription=transcription, capture=capture, locations=locations
    )


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


def _resolve_ingest_key(name: str, entry: dict[str, Any]) -> tuple[tuple[str, ...], bool]:
    """Resolve a store location's optional `ingest` key (spec §12.1.1, v22) to
    `(ingest_types, ingest_default)`. `true` → the default destination; a non-empty
    list of content-type strings → a format claim; absent → neither (a plain store
    location, resolved only). Any other shape is an operator error."""
    if "ingest" not in entry:
        return (), False
    value = entry["ingest"]
    if value is True:
        return (), True
    if isinstance(value, list) and value and all(isinstance(v, str) and v.strip() for v in value):
        return tuple(str(v).strip() for v in value), False
    raise ValueError(
        f"corpus.toml [[corpus.location]] {name!r}: 'ingest' must be `true` (default "
        f"destination) or a non-empty list of content-type strings, got {value!r}."
    )


def _resolve_ingest_origins_key(name: str, entry: dict[str, Any]) -> tuple[str, ...]:
    """Resolve a store location's optional `ingest_origins` key (spec §12.1.1, v23) to
    a tuple of origin overlay ids. Absent → `()` (no origin claim). Present → must be a
    non-empty list of non-empty strings — any other shape is an operator error. Composes
    freely with `ingest` (a location may declare both, either, or neither key)."""
    if "ingest_origins" not in entry:
        return ()
    value = entry["ingest_origins"]
    if isinstance(value, list) and value and all(isinstance(v, str) and v.strip() for v in value):
        return tuple(str(v).strip() for v in value)
    raise ValueError(
        f"corpus.toml [[corpus.location]] {name!r}: 'ingest_origins' must be a "
        f"non-empty list of origin overlay id strings, got {value!r}."
    )


def _resolve_manifest_key(name: str, entry: dict[str, Any]) -> bool:
    """Resolve an attached location's optional `manifest` key (spec §12.1.1, v24): `true`
    declares that the tree presents its own manifest — a residence scanner publishes
    `<path>/.athenaeum/manifest.sqlite`, and attest reads it instead of walking. Absent →
    `False` (an ordinary walked location). Any non-bool value is an operator error."""
    if "manifest" not in entry:
        return False
    value = entry["manifest"]
    if isinstance(value, bool):
        return value
    raise ValueError(
        f"corpus.toml [[corpus.location]] {name!r}: 'manifest' must be a bool "
        f"(true or false), got {value!r}."
    )


def _resolve_cost_key(name: str, entry: dict[str, Any]) -> int | None:
    """Resolve a location's optional `cost` key (spec §12.1.1, v25 "Route preference"
    amendment) — any non-negative integer, lower is nearer; valid on BOTH `kind`s.
    Absent → `None` (the class default applies, `effective_cost`). `bool` is rejected
    even though Python's `bool` is an `int` subclass — `true`/`false` is never a
    sensible cost. Any other shape is an operator error."""
    if "cost" not in entry:
        return None
    value = entry["cost"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"corpus.toml [[corpus.location]] {name!r}: 'cost' must be a non-negative "
            f"integer, got {value!r}."
        )
    return value


def _resolve_locations_section(raw: Any) -> tuple[LocationConfig, ...]:
    """Resolve `[[corpus.location]]` array-of-tables (spec §12.1.1, v21/v22). No
    env-var overrides — locations are deployment topology, not secrets or transport
    tuning."""
    if not isinstance(raw, list):
        raise ValueError(
            "corpus.toml [corpus.location] must be an array of tables "
            "(use [[corpus.location]], not [corpus.location])."
        )
    out: list[LocationConfig] = []
    seen: set[str] = set()
    default_name: str | None = None
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"corpus.toml [[corpus.location]] entry {i}: expected a table.")
        name = str(entry.get("name") or "").strip()
        if not name:
            raise ValueError(f"corpus.toml [[corpus.location]] entry {i}: missing required 'name'.")
        if name in seen:
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: duplicate name — "
                f"location names must be unique."
            )
        kind = str(entry.get("kind") or "").strip().lower()
        if not kind:
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: missing required 'kind' "
                f"(attached | store)."
            )
        if kind not in ("attached", "store"):
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: unknown kind {kind!r}; "
                f"must be 'attached' or 'store'."
            )
        if entry.get("remote"):
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: 'remote' transport is not "
                f"implemented yet (spec §12.1.1, ticket #204) — declare a local 'path' "
                f"instead."
            )
        if kind == "attached" and "ingest" in entry:
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: 'ingest' is only valid on "
                f"kind = \"store\" — an attached location is operator-managed and "
                f"never an ingest destination."
            )
        if kind == "attached" and "ingest_origins" in entry:
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: 'ingest_origins' is only "
                f"valid on kind = \"store\" — an attached location is operator-managed "
                f"and never an ingest destination."
            )
        if kind == "store" and "manifest" in entry:
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: 'manifest' is only valid "
                f"on kind = \"attached\" — a store location is corpus-managed "
                f"content-addressed storage, never a presenting tree."
            )
        raw_path = entry.get("path")
        if not raw_path:
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: kind = {kind!r} requires a "
                f"'path'."
            )
        path = Path(str(raw_path))
        if not path.is_absolute():
            raise ValueError(
                f"corpus.toml [[corpus.location]] {name!r}: 'path' must be an "
                f"absolute path, got {raw_path!r}."
            )
        ingest_types, ingest_default = (
            _resolve_ingest_key(name, entry) if kind == "store" else ((), False)
        )
        ingest_origins = _resolve_ingest_origins_key(name, entry) if kind == "store" else ()
        manifest = _resolve_manifest_key(name, entry) if kind == "attached" else False
        cost = _resolve_cost_key(name, entry)
        if ingest_default:
            if default_name is not None:
                raise ValueError(
                    f"corpus.toml [[corpus.location]] {name!r}: 'ingest = true' — but "
                    f"{default_name!r} already declares the default ingest "
                    f"destination; at most one location may (spec §12.1.1, v22)."
                )
            default_name = name
        seen.add(name)
        out.append(
            LocationConfig(
                name=name,
                kind=kind,
                path=path,
                ingest_types=ingest_types,
                ingest_default=ingest_default,
                ingest_origins=ingest_origins,
                manifest=manifest,
                cost=cost,
            )
        )
    return tuple(out)
