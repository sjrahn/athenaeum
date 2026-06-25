"""FastAPI app — read-only HTTP surface for the Corpus Console.

Imports FastAPI at module top, which is fine: this module is only imported by the
`corpus-api` console script / `python -m corpus.api`, never by the base library, so the
base install stays importable without the `[api]` extra (gotcha #24).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from corpus import mime as mime_mod
from corpus import paths, records, resolver
from corpus import regions as corpus_regions
from corpus.api import serialize
from corpus.api.config import ApiConfig, CorpusEntry, load_config
from corpus.api.index import get_index, parse_cond, parse_range
from corpus.api.models import (
    GraphResponse,
    SaveRegionsRequest,
    SaveRegionsResponse,
)
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

    def concept_kb():
        """The shared Wikipedia KB (or None when no ZIM is configured)."""
        zim = cfg.wiki_zim or os.environ.get("ATH_WIKI_ZIM")
        if not zim:
            return None
        from corpus import wiki

        try:
            return wiki.open_kb(zim=zim)
        except wiki.WikiUnavailable:
            return None

    def concept_resolver(entry: CorpusEntry):
        from corpus import concepts

        return concepts.ConceptResolver(corpus_root=entry.root, kb=concept_kb())

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

    # ---- concept KB (Wikipedia; corpus-independent — registered before {corpus} routes) ----

    @app.get("/v1/wiki/search")
    def wiki_search(q: str = Query(...), limit: int = 10) -> list[dict]:
        kb = concept_kb()
        if kb is None:
            raise HTTPException(503, "no Wikipedia KB configured (set --wiki-zim / ATH_WIKI_ZIM)")
        from corpus import wiki

        try:
            hits = kb.search(q, limit=limit)
        except wiki.WikiUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        return [{"id": h.id, "title": h.title, "url": h.url, "path": h.path} for h in hits]

    @app.get("/v1/wiki/article")
    def wiki_article(id: str = Query(...)) -> dict:
        kb = concept_kb()
        if kb is None:
            raise HTTPException(503, "no Wikipedia KB configured (set --wiki-zim / ATH_WIKI_ZIM)")
        from corpus import wiki

        try:
            art = kb.get(id)
        except wiki.WikiUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        if art is None:
            raise HTTPException(404, f"no article for {id!r}")
        return {
            "id": art.id,
            "title": art.title,
            "url": art.url,
            "qid": art.qid,
            "summary": art.summary,
        }

    # ---- records / facets / schema ----

    @app.get("/v1/{corpus}/facets")
    def facets(corpus: str, q: str = "", view: str = "all") -> list[dict]:
        idx = get_index(corpus_or_404(corpus))
        return idx.facets(q=q, saved_view=view)

    @app.get("/v1/{corpus}/schema")
    def schema(corpus: str) -> dict:
        idx = get_index(corpus_or_404(corpus))
        return idx.schema_registry()

    @app.get("/v1/{corpus}/fields")
    def fields(corpus: str) -> list[dict]:
        """The whole-corpus typed field registry (core + overlay extended fields) with
        global per-type stats — the workbench's field controls + ⌘K palette read this."""
        idx = get_index(corpus_or_404(corpus))
        return idx.fields()

    @app.get("/v1/{corpus}/workbench")
    def workbench(
        corpus: str,
        q: str = "",
        view: str = "all",
        sort: str = "recent",
        offset: int = 0,
        limit: int = 200,
        facet: list[str] = Query(default=[]),
        cond: list[str] = Query(default=[]),
        range: str = "",
    ) -> dict:
        """One combined query driving every workbench pane (records · drill-down facet
        stack · timeline bins · available fields · overview) over the narrowed set."""
        idx = get_index(corpus_or_404(corpus))
        facets_sel: dict[str, set[str]] = {}
        for spec in facet:
            key, sep, value = spec.partition("=")
            if sep:
                facets_sel.setdefault(key, set()).add(value)
        conds = [c for c in (parse_cond(spec) for spec in cond) if c is not None]
        return idx.workbench(
            q=q,
            saved_view=view,
            facets=facets_sel,
            conds=conds,
            rng=parse_range(range),
            sort=sort,
            offset=offset,
            limit=limit,
        )

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
        return serialize.record_detail(
            entry.root,
            post,
            entry.id,
            store=store,
            concept_resolver=concept_resolver(entry),
            uri_index=get_index(entry).uri_index(),
        )

    @app.get("/v1/{corpus}/records/{record_id}/graph", response_model=GraphResponse)
    def record_graph(corpus: str, record_id: str) -> GraphResponse:
        """The record's connections (graph mode): resolved origins/embeds/classification
        peers/captured cross-refs + uncaptured outbound links extracted from its body."""
        entry = corpus_or_404(corpus)
        require_hex(record_id)
        path = paths.record_path(entry.root, record_id)
        if not path.is_file():
            raise HTTPException(404, f"record {record_id} not found")
        post = records.load(path)
        return GraphResponse(**get_index(entry).graph(post))

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

    # ---- write surface: crop-region save (the crop editor's persist) ----

    @app.post("/v1/{corpus}/records/{record_id}/regions", response_model=SaveRegionsResponse)
    def save_regions(corpus: str, record_id: str, body: SaveRegionsRequest) -> SaveRegionsResponse:
        entry = corpus_or_404(corpus)
        require_hex(record_id)
        path = paths.record_path(entry.root, record_id)
        if not path.is_file():
            raise HTTPException(404, f"record {record_id} not found")
        try:
            result = corpus_regions.save_regions(
                entry.root, record_id, [r.model_dump() for r in body.regions]
            )
        except corpus_regions.RegionSaveError as exc:
            raise HTTPException(400, str(exc)) from exc
        get_index(entry, fresh=True)  # the per-corpus index is now stale; rebuild it
        return SaveRegionsResponse(**result)

    # ---- next-phase write surfaces (stubbed; see plan) ----

    @app.post("/v1/{corpus}/check")
    def check(corpus: str, request: Request) -> dict:
        corpus_or_404(corpus)
        raise HTTPException(501, "check (dedup probe) lands in the submit phase")

    @app.post("/v1/{corpus}/submit")
    def submit(corpus: str, request: Request) -> dict:
        corpus_or_404(corpus)
        raise HTTPException(501, "submit (capture/ingest pipeline) lands in the submit phase")

    return app
