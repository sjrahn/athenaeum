"""The read surface's app factory — spec/athenaeum.md §5.1.

`create_app` builds a stateless FastAPI application bound to one instance
root and (optionally) one owner-plane bearer token. Every route reads the
instance fresh per request (`get_ctx`) — the same "reload the tree, answer
deterministically" model every `ath`/`ledger` CLI verb already uses; nothing
here watches the filesystem or caches ledger state across requests, so a
concurrent `ath ledger` edit is visible on the very next request.

Framework types stay inside this module (and its sibling `_project.py`) —
nothing outside `ath.serve` imports fastapi/starlette.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import subprocess
from dataclasses import dataclass
from pathlib import Path

import blake3
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from ath.manifest import Instance, Reference, load_instance, load_references
from ath.serve._project import (
    claim_is_public,
    fact_is_public,
    project_fact,
    public_evidence_uris,
    public_roster_uris,
)
from ledger import demands as demands_mod
from ledger import tenancy as tenancy_mod
from ledger import values as values_mod
from ledger import views as views_mod
from ledger import worklist as worklist_mod
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.coverage import render_coverage
from ledger.model import FULL_HASH_RE, is_edge, is_redirect, load_json_dir, load_lineage
from ledger.schemas import load_schemas
from ledger.scope import evaluate_scope

# Bumped with the specification version — the OpenAPI document is stamped
# with it (Part I §5.1).
SPEC_VERSION = 28

router = APIRouter()


# --------------------------------------------------------------------- context


@dataclass
class Ctx:
    root: Path
    instance: Instance
    ledger_root: Path
    corpus_root: Path
    join: CorpusJoin
    datasets: dict[str, Reference]
    instance_commit: str | None


def _git_commit(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def get_ctx(request: Request) -> Ctx:
    root: Path = request.app.state.root
    instance = load_instance(root)
    registered = [
        RegisteredCorpus(name="corpus", root=instance.corpus_root,
                          private=instance.visibility == "private")
    ]
    join = CorpusJoin(registered)
    datasets = {r.dataset: r for r in load_references(root)}
    return Ctx(
        root=root, instance=instance, ledger_root=instance.ledger_root,
        corpus_root=instance.corpus_root, join=join, datasets=datasets,
        instance_commit=_git_commit(root),
    )


def get_plane(request: Request) -> str:
    """`"owner"` iff an owner token is configured AND the request's bearer
    matches it (constant-time compare); `"public"` otherwise — including
    when no token is configured at all (§5.1: the owner plane is "enabled
    only explicitly")."""
    owner_token: str | None = request.app.state.owner_token
    if not owner_token:
        return "public"
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        candidate = auth[len("Bearer "):]
        if hmac.compare_digest(candidate, owner_token):
            return "owner"
    return "public"


def require_owner(plane: str = Depends(get_plane)) -> None:
    """Gate an owner-only route. 404, never 401/403 — existence itself must
    not leak (§5.1)."""
    if plane != "owner":
        raise HTTPException(status_code=404, detail="not found")


def _etag(commit: str | None, plane: str, raw: bytes) -> str:
    # `plane` rides the hash (beyond the letter of "instance commit + file
    # content hash", §5.1) so a shared cache in front of the surface can
    # never conflate the public projection's bytes with the owner plane's
    # under one validator; `Vary: Authorization` on the response says the
    # same thing to any downstream cache.
    payload = f"{commit or 'none'}:{plane}:".encode() + raw
    return '"' + blake3.blake3(payload).hexdigest()[:32] + '"'


def _find_fact_path(ledger_root: Path, fact_id: str) -> Path | None:
    matches = sorted(ledger_root.glob(f"facts/*/{fact_id}.json"))
    return matches[0] if matches else None


def _load_fact_at(ledger_root: Path, relpath: str) -> dict | None:
    try:
        obj = json.loads((ledger_root / relpath).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _has_public_predicate(fact: dict, predicate: str, *, owner: bool, ctx: Ctx) -> bool:
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    for c in fact.get("claims") or []:
        if not isinstance(c, dict) or c.get("predicate") != predicate:
            continue
        if owner or claim_is_public(c, sources, ctx.join, ctx.datasets):
            return True
    return False


# ----------------------------------------------------------------- /instance


@router.get("/instance")
def get_instance_info(ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane)) -> dict:
    return {
        "name": ctx.instance.name,
        "spec_version": SPEC_VERSION,
        "instance_commit": ctx.instance_commit,
        "plane": plane,
    }


# --------------------------------------------------------------------- /facts


@router.get("/facts")
def list_facts(
    type_: str | None = Query(None, alias="type"),
    predicate: str | None = None,
    after: str | None = None,
    limit: int = 100,
    ctx: Ctx = Depends(get_ctx),
    plane: str = Depends(get_plane),
) -> dict:
    limit = max(1, min(limit, 500))
    owner = plane == "owner"
    facts, _ = load_json_dir(ctx.ledger_root, "facts/*/*.json")
    rows: list[dict] = []
    for path, fact in facts.items():
        if is_redirect(fact):
            continue
        fid = fact.get("id")
        if not isinstance(fid, str):
            continue
        if type_ is not None and fact.get("type") != type_:
            continue
        if predicate is not None and not _has_public_predicate(
            fact, predicate, owner=owner, ctx=ctx
        ):
            continue
        if not owner and not fact_is_public(fact, ctx.join, ctx.datasets):
            continue
        rows.append({
            "id": fid,
            "type": fact.get("type"),
            "name": fact.get("name") or fact.get("title") or "",
            "path": str(path.relative_to(ctx.ledger_root)),
        })
    rows.sort(key=lambda r: r["id"])
    if after is not None:
        rows = [r for r in rows if r["id"] > after]
    page = rows[:limit]
    next_cursor = page[-1]["id"] if len(rows) > limit else None
    return {"facts": page, "next": next_cursor}


@router.get("/facts/{fact_id}")
def get_fact(
    fact_id: str, request: Request, response: Response,
    ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
):
    lineage, _ = load_lineage(ctx.ledger_root)
    if fact_id in lineage:
        return RedirectResponse(url=f"/facts/{lineage[fact_id]}", status_code=307)

    fact_path = _find_fact_path(ctx.ledger_root, fact_id)
    if fact_path is None:
        raise HTTPException(404, "not found")
    raw = fact_path.read_bytes()
    try:
        fact = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(404, "not found") from e
    if not isinstance(fact, dict) or is_redirect(fact) or fact.get("id") != fact_id:
        raise HTTPException(404, "not found")

    projected = project_fact(fact, ctx.join, ctx.datasets, owner=(plane == "owner"))
    if projected is None:
        raise HTTPException(404, "not found")

    etag = _etag(ctx.instance_commit, plane, raw)
    response.headers["Vary"] = "Authorization"
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Vary": "Authorization"})
    response.headers["ETag"] = etag
    return projected


@router.get("/facts/{fact_id}/claims/{short}")
def get_claim(
    fact_id: str, short: str, ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
):
    fact_path = _find_fact_path(ctx.ledger_root, fact_id)
    if fact_path is None:
        raise HTTPException(404, "not found")
    try:
        fact = json.loads(fact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(404, "not found") from e
    if not isinstance(fact, dict) or is_redirect(fact):
        raise HTTPException(404, "not found")

    cid = f"{fact_id}:{short}"
    claim = next(
        (c for c in fact.get("claims") or [] if isinstance(c, dict) and c.get("id") == cid),
        None,
    )
    if claim is None:
        raise HTTPException(404, "not found")

    if plane != "owner":
        if not fact_is_public(fact, ctx.join, ctx.datasets):
            raise HTTPException(404, "not found")
        sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        if not claim_is_public(claim, sources, ctx.join, ctx.datasets):
            raise HTTPException(404, "not found")
    return claim


# --------------------------------------------------------------------- /scope


@router.get("/scope")
def get_scope(spec: str, ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane)) -> dict:
    try:
        parsed = json.loads(spec)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"spec is not valid JSON: {e}") from e
    try:
        result = evaluate_scope(ctx.ledger_root, parsed)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    if plane == "owner":
        return result

    # A whole-fact filter alone is not enough here: a PUBLIC fact can still
    # carry private-backed claims, and evaluate_scope's evidence/roster maps
    # are built from every claim/roster entry unconditionally. Recompute both
    # maps from the same per-claim/per-source public projection `/facts/{id}`
    # applies (`public_evidence_uris`/`public_roster_uris`) rather than merely
    # filtering evaluate_scope's raw output down to public fact ids — the
    # narrower bug this fixes: a private record hash riding a public fact's
    # evidence list was previously served whole.
    kept_facts: dict[str, dict] = {}
    kept_members = []
    for m in result.get("members", []):
        path = m.get("path")
        fact = _load_fact_at(ctx.ledger_root, path) if isinstance(path, str) else None
        if fact is not None and fact_is_public(fact, ctx.join, ctx.datasets):
            fid = str(m.get("id"))
            kept_facts[fid] = fact
            kept_members.append(m)
    result["members"] = kept_members
    if "evidence" in result:
        result["evidence"] = {
            fid: public_evidence_uris(fact, ctx.join, ctx.datasets)
            for fid, fact in kept_facts.items()
        }
    if "roster" in result:
        result["roster"] = {
            fid: public_roster_uris(fact, ctx.join) for fid, fact in kept_facts.items()
        }
    return result


# ------------------------------------------------------------------ /schemas


@router.get("/schemas")
def list_schemas(ctx: Ctx = Depends(get_ctx)) -> dict:
    schemas, _ = load_schemas(ctx.ledger_root)
    return schemas


@router.get("/schemas/values")
def get_value_kinds(ctx: Ctx = Depends(get_ctx)) -> dict:
    kinds, _ = values_mod.load_kinds(ctx.ledger_root)
    return kinds


@router.get("/schemas/{type_}")
def get_schema(type_: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    schemas, _ = load_schemas(ctx.ledger_root)
    schema = schemas.get(type_)
    if schema is None:
        raise HTTPException(404, "not found")
    return schema


# --------------------------------------------------------------------- /vocab


@router.get("/vocab")
def get_vocab(ctx: Ctx = Depends(get_ctx)) -> dict:
    facts, _ = load_json_dir(ctx.ledger_root, "facts/*/*.json")
    return {"generated": True, "markdown": views_mod.fresh_vocab(ctx.ledger_root, facts)}


# ------------------------------------------------------------------- /records


@router.get("/records/{hash_}")
def get_record(hash_: str, ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane)) -> dict:
    if not FULL_HASH_RE.match(hash_):
        raise HTTPException(422, "not a 64-hex blake3 hash")
    record_path = CorpusJoin.record_path(ctx.corpus_root, hash_)
    if not record_path.is_file():
        raise HTTPException(404, "not found")
    if plane != "owner":
        tenancy = tenancy_mod.record_tenancy(
            ctx.corpus_root, hash_, default=ctx.instance.visibility
        )
        if tenancy != "public":
            raise HTTPException(404, "not found")

    from corpus import records as corpus_records

    post = corpus_records.load(record_path)
    origins = []
    for o in corpus_records.iter_origin_blocks(post):
        fields = o.get("fields") or {}
        origins.append({"id": o.get("id"), "subtype": o.get("subtype"), "uri": fields.get("uri")})
    return {
        "hash": hash_,
        "mime": corpus_records.media_type_for(post),
        "origins": origins,
        "markdown": post.content,
    }


# ------------------------------------------------------------------- /resolve


@router.get("/resolve/corpus/{hash_}")
def resolve_corpus(
    hash_: str, request: Request, ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
):
    if not FULL_HASH_RE.match(hash_):
        raise HTTPException(422, "not a 64-hex blake3 hash")
    if plane != "owner":
        tenancy = tenancy_mod.record_tenancy(
            ctx.corpus_root, hash_, default=ctx.instance.visibility
        )
        if tenancy != "public":
            raise HTTPException(404, "not found")

    query = request.url.query
    uri = f"corpus://{hash_}" + (f"?{query}" if query else "")

    from corpus import resolver as corpus_resolver
    from corpus.store import ArtifactMissing

    try:
        out_path = corpus_resolver.resolve(uri, ctx.corpus_root, regenerate=False)
    except NotImplementedError as e:
        raise HTTPException(
            501, f"{e} — not cleanly resolvable over the read surface; try "
                 f"`corpus resolve {uri!r}` on the instance host"
        ) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except (FileNotFoundError, ArtifactMissing) as e:
        raise HTTPException(404, str(e)) from e

    media_type = mimetypes.guess_type(str(out_path))[0] or "application/octet-stream"
    return FileResponse(out_path, media_type=media_type)


@router.get("/resolve/ref/{dataset}/{id_path:path}")
def resolve_ref(
    dataset: str, id_path: str, tag: str | None = None,
    ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
):
    reference = ctx.datasets.get(dataset)
    if reference is None:
        raise HTTPException(404, "unregistered dataset")
    resolved_tag = tag if tag is not None else reference.latest
    snapshot = reference.snapshots.get(resolved_tag)
    if snapshot is None:
        raise HTTPException(404, f"unknown snapshot tag {resolved_tag!r}")

    if plane != "owner":
        tenancy = tenancy_mod.record_tenancy(
            ctx.corpus_root, snapshot.artifact, default=ctx.instance.visibility
        )
        if tenancy != "public":
            raise HTTPException(404, "not found")

    from refdata import resolve as refdata_resolve
    from refdata.errors import RefdataError

    try:
        entry = refdata_resolve(reference, id_path, tag=tag, corpora_roots=[ctx.corpus_root])
    except RefdataError as e:
        return JSONResponse(status_code=503, content={"unverifiable": str(e)})

    return {
        "dataset": entry.dataset, "tag": entry.tag, "artifact": entry.artifact,
        "native_id": entry.native_id, "canonical_id": entry.canonical_id,
        "title": entry.title, "text": entry.text, "content_type": entry.content_type,
    }


# --------------------------------------------------------------- owner plane


@router.get("/interpretations", dependencies=[Depends(require_owner)])
def list_interpretations(ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    interps, _ = load_json_dir(ctx.ledger_root, "interpretations/*.json")
    return sorted(interps.values(), key=lambda o: str(o.get("id", "")))


@router.get("/interpretations/{iid}", dependencies=[Depends(require_owner)])
def get_interpretation(iid: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    path = ctx.ledger_root / "interpretations" / f"{iid}.json"
    if not path.is_file():
        raise HTTPException(404, "not found")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(404, "not found") from e
    if not isinstance(obj, dict):
        raise HTTPException(404, "not found")
    return obj


@router.get("/facts/{fact_id}/demands", dependencies=[Depends(require_owner)])
def get_demands(fact_id: str, ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    facts, _ = load_json_dir(ctx.ledger_root, "facts/*/*.json")
    live = [f for f in facts.values() if not is_redirect(f)]
    fact = next((f for f in live if f.get("id") == fact_id), None)
    if fact is None:
        raise HTTPException(404, "not found")
    schemas, _ = load_schemas(ctx.ledger_root)
    kinds, _ = values_mod.load_kinds(ctx.ledger_root)
    rules, _ = demands_mod.load_demand_rules(ctx.ledger_root)
    edges = [f for f in live if is_edge(f)]
    facts_by_id = {str(f.get("id")): f for f in live}
    interps, _ = load_json_dir(ctx.ledger_root, "interpretations/*.json")
    return demands_mod.evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds=kinds,
        facts_by_id=facts_by_id, edges=edges, interps=list(interps.values()),
    )


@router.get("/worklist", dependencies=[Depends(require_owner)])
def get_worklist(ref: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    return {"ref": ref, "dependents": worklist_mod.worklist(ctx.ledger_root, ref)}


@router.get("/coverage", dependencies=[Depends(require_owner)])
def get_coverage(ctx: Ctx = Depends(get_ctx)) -> dict:
    return {"generated": True, "markdown": render_coverage(ctx.ledger_root, ctx.join.corpora)}


@router.get("/open-questions", dependencies=[Depends(require_owner)])
def get_open_questions(ctx: Ctx = Depends(get_ctx)) -> dict:
    facts, _ = load_json_dir(ctx.ledger_root, "facts/*/*.json")
    interps, _ = load_json_dir(ctx.ledger_root, "interpretations/*.json")
    schemas, _ = load_schemas(ctx.ledger_root)
    markdown = views_mod.render_worklist(ctx.ledger_root, facts, interps, schemas)
    return {"generated": True, "markdown": markdown}


# ----------------------------------------------------------------- app factory


def create_app(instance_root: Path, owner_token: str | None) -> FastAPI:
    """Build the read surface for the instance at *instance_root*.

    *owner_token*, when given, gates the owner plane (`Authorization: Bearer
    <token>`); `None` means the owner plane is not enabled at all — every
    request, bearer or not, reads as public (§5.1).
    """
    app = FastAPI(
        title="Athenaeum read surface",
        version=str(SPEC_VERSION),
        description="A read-only HTTP surface over an Athenaeum instance's "
                     "corpus + ledger join (spec/athenaeum.md §5.1). Two "
                     "planes: public (default, sensitivity-filtered, fail "
                     "closed) and owner (bearer-token gated).",
    )
    app.state.root = instance_root
    app.state.owner_token = owner_token
    app.include_router(router)
    return app
