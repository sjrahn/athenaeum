"""FastAPI app — read-only HTTP surface for the Corpus Console.

Imports FastAPI at module top, which is fine: this module is only imported by the
`corpus-api` console script / `python -m corpus.api`, never by the base library, so the
base install stays importable without the `[api]` extra (gotcha #24).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from corpus import mime as mime_mod
from corpus import paths, records, resolver
from corpus.api import serialize
from corpus.api.config import ApiConfig, CorpusEntry, load_config
from corpus.api.index import get_index
from corpus.store import ArtifactMissing, get_store

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def create_app(config: ApiConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    app = FastAPI(title="Athenaeum Corpus API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.config = cfg

    def corpus_or_404(corpus_id: str) -> CorpusEntry:
        entry = cfg.by_id(corpus_id)
        if entry is None:
            raise HTTPException(404, f"unknown corpus {corpus_id!r}")
        return entry

    def require_hex(record_id: str) -> str:
        if not _HEX64.match(record_id):
            raise HTTPException(400, "record id must be a 64-char blake3 hex")
        return record_id

    # ---- health + corpora ----

    @app.get("/v1/health", response_class=PlainTextResponse)
    def health() -> str:
        return "ok"

    @app.get("/v1/corpora")
    def corpora() -> list[dict]:
        out = []
        for entry in cfg.corpora:
            out.append(
                {
                    "id": entry.id,
                    "name": entry.name,
                    "color": entry.color,
                    "desc": entry.desc,
                    "record_count": len(get_index(entry).items),
                    "online": True,
                }
            )
        return out

    # ---- records / facets / schema ----

    @app.get("/v1/{corpus}/facets")
    def facets(corpus: str, q: str = "", view: str = "all") -> list[dict]:
        idx = get_index(corpus_or_404(corpus))
        return idx.facets(q=q, saved_view=view)

    @app.get("/v1/{corpus}/schema")
    def schema(corpus: str) -> dict:
        idx = get_index(corpus_or_404(corpus))
        return idx.schema_registry()

    @app.get("/v1/{corpus}/records")
    def list_records(
        corpus: str,
        q: str = "",
        view: str = "all",
        sort: str = "recent",
        offset: int = 0,
        limit: int = 200,
        facet: list[str] = Query(default=[]),
        field: list[str] = Query(default=[]),
    ) -> dict:
        idx = get_index(corpus_or_404(corpus))
        facets_sel: dict[str, set[str]] = {}
        for spec in facet:
            key, sep, value = spec.partition("=")
            if sep:
                facets_sel.setdefault(key, set()).add(value)
        fields_sel: dict[str, set[str]] = {}
        for spec in field:
            compound, sep, value = spec.partition("=")
            if sep:
                fields_sel.setdefault(compound, set()).add(value)
        return idx.query(
            q=q,
            saved_view=view,
            facets=facets_sel,
            fields_sel=fields_sel,
            sort=sort,
            offset=offset,
            limit=limit,
        )

    @app.get("/v1/{corpus}/records/{record_id}")
    def record_detail(corpus: str, record_id: str) -> dict:
        entry = corpus_or_404(corpus)
        require_hex(record_id)
        path = paths.record_path(entry.root, record_id)
        if not path.is_file():
            raise HTTPException(404, f"record {record_id} not found")
        post = records.load(path)
        store = get_store(entry.root)
        return serialize.record_detail(entry.root, post, entry.id, store=store)

    # ---- artifact bytes + functional-URI resolution ----

    @app.api_route("/v1/{corpus}/artifacts/{record_id}", methods=["GET", "HEAD"])
    def artifact_bytes(corpus: str, record_id: str) -> FileResponse:
        entry = corpus_or_404(corpus)
        require_hex(record_id)
        path = paths.record_path(entry.root, record_id)
        if not path.is_file():
            raise HTTPException(404, f"record {record_id} not found")
        post = records.load(path)
        media_type = records.media_type_for(post)
        ext = mime_mod.extension_for(media_type) if media_type else "bin"
        store = get_store(entry.root)
        try:
            artifact = store.ensure_local(record_id, ext)
        except ArtifactMissing as exc:
            raise HTTPException(404, f"artifact bytes unavailable: {exc}") from exc
        return FileResponse(artifact, media_type=media_type or "application/octet-stream")

    @app.api_route("/v1/{corpus}/resolve", methods=["GET", "HEAD"])
    def resolve_uri(corpus: str, uri: str = Query(...)) -> FileResponse:
        entry = corpus_or_404(corpus)
        if not uri.startswith("corpus://"):
            raise HTTPException(400, "uri must be a corpus:// functional URI")
        try:
            resolved: Path = resolver.resolve(uri, entry.root)
        except (ArtifactMissing, FileNotFoundError) as exc:
            raise HTTPException(404, f"cannot resolve: {exc}") from exc
        except NotImplementedError as exc:
            raise HTTPException(501, f"no transform pipeline: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, f"bad functional URI: {exc}") from exc
        return FileResponse(resolved)

    # ---- next-phase write surfaces (stubbed; see plan Part B4) ----

    @app.post("/v1/{corpus}/check")
    def check(corpus: str, request: Request) -> dict:
        corpus_or_404(corpus)
        raise HTTPException(501, "check (dedup probe) lands in the submit phase")

    @app.post("/v1/{corpus}/submit")
    def submit(corpus: str, request: Request) -> dict:
        corpus_or_404(corpus)
        raise HTTPException(501, "submit (capture/ingest pipeline) lands in the submit phase")

    @app.post("/v1/{corpus}/records/{record_id}/regions")
    def save_regions(corpus: str, record_id: str, request: Request) -> dict:
        corpus_or_404(corpus)
        raise HTTPException(501, "region save lands in the crop-editor phase")

    return app
