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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import blake3
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from ath._version import SPEC_VERSION
from ath.manifest import Instance, Reference, load_instance, load_references
from ath.serve._project import (
    claim_is_visible,
    fact_is_visible,
    project_fact,
    visible_evidence_uris,
    visible_roster_uris,
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

_PUBLIC_GRANTS = frozenset({"public"})

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


def _schema_overlay_signature(corpus_root: Path) -> tuple[int, int]:
    """A cheap (file count, max mtime_ns) signature over the corpus-local
    schema overlay tree (`<corpus_root>/schema/`) — a per-request-batch
    staleness check, not a filesystem watch. `corpus.schemas`' loaders
    (`load_origin_overlay_by_id` among them) are `@lru_cache`d for the
    process lifetime (its own docstring: "a normal CLI run never mutates
    schemas post-load"), an assumption the long-running server breaks: an
    operator editing `tenancy: public` to `tenancy: private` on a live
    server must see the revocation take effect on the very next request, not
    at the next restart. Any change to the tree — a rewritten file's mtime,
    or an added/removed file's count — moves this signature, so `get_ctx`
    below clears the cache whenever it does."""
    schema_dir = corpus_root / "schema"
    if not schema_dir.is_dir():
        return (0, 0)
    count = 0
    latest = 0
    for p in schema_dir.rglob("*"):
        if p.is_file():
            count += 1
            try:
                latest = max(latest, p.stat().st_mtime_ns)
            except OSError:
                continue
    return (count, latest)


def get_ctx(request: Request) -> Ctx:
    root: Path = request.app.state.root
    instance = load_instance(root)
    sig = _schema_overlay_signature(instance.corpus_root)
    if request.app.state.schema_sig != sig:
        from corpus import schemas as corpus_schemas_mod

        corpus_schemas_mod.cache_clear()
        request.app.state.schema_sig = sig
    registered = [
        RegisteredCorpus(name="corpus", root=instance.corpus_root,
                          private=instance.visibility == "private",
                          floor=instance.visibility)
    ]
    join = CorpusJoin(registered)
    datasets = {r.dataset: r for r in load_references(root)}
    return Ctx(
        root=root, instance=instance, ledger_root=instance.ledger_root,
        corpus_root=instance.corpus_root, join=join, datasets=datasets,
        instance_commit=_git_commit(root),
    )


def get_plane(request: Request) -> str:
    """The bearer token's plane (§5.1: "the planes are the grant sets"):
    `"owner"` iff an owner token is configured AND the request's bearer
    matches it; an audience name iff the bearer matches that audience's
    configured token; `"public"` otherwise — no token, an unrecognized
    token, or no owner/audience tokens configured at all (the owner plane is
    "enabled only explicitly", and an unmatched bearer is the fail-closed
    default). Every comparison is constant-time (`hmac.compare_digest`)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return "public"
    candidate = auth[len("Bearer "):]
    owner_token: str | None = request.app.state.owner_token
    if owner_token and hmac.compare_digest(candidate, owner_token):
        return "owner"
    audience_tokens: dict[str, str] = request.app.state.audience_tokens
    for name, token in audience_tokens.items():
        if hmac.compare_digest(candidate, token):
            return name
    return "public"


def get_grants(
    plane: str = Depends(get_plane), ctx: Ctx = Depends(get_ctx),
) -> frozenset[str]:
    """The grant set the resolved plane reads with (§athenaeum.md §5.1,
    §ledger.md §6.4): `{"public"}` for the public plane, an audience's
    granted tiers plus `public` (`Instance.grants_for`) for an audience
    plane, or the empty set for the owner plane — unused there, since
    `project_fact`/callers bypass grant filtering entirely on `owner=True`."""
    if plane == "owner":
        return frozenset()
    if plane == "public":
        return _PUBLIC_GRANTS
    return ctx.instance.grants_for(plane)


def require_owner(plane: str = Depends(get_plane)) -> None:
    """Gate an owner-only route. 404, never 401/403 — existence itself must
    not leak (§5.1). Interpretations and the other owner-only surfaces stay
    owner-plane-only regardless of an audience token's grants — pre-assertion
    content is never served to any audience, however wide its grants."""
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


def _has_visible_predicate(
    fact: dict, predicate: str, *, owner: bool, grants: frozenset[str],
    declared: frozenset[str] | None, ctx: Ctx,
) -> bool:
    sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
    for c in fact.get("claims") or []:
        if not isinstance(c, dict) or c.get("predicate") != predicate:
            continue
        if owner or claim_is_visible(c, sources, ctx.join, ctx.datasets, grants,
                                     declared=declared):
            return True
    return False


def _record_visible(ctx: Ctx, hash_: str, grants: frozenset[str]) -> bool:
    """A corpus record's derived tier set intersects `grants` (§6.4) — the
    grant-set generalization of the pre-v30 `record_tenancy(...) == "public"`
    check every `/records`, `/resolve/corpus`, `/resolve/ref` gate used."""
    tiers = tenancy_mod.record_tiers(
        ctx.corpus_root, hash_, default=ctx.instance.visibility,
        declared=ctx.instance.declared_tiers,
    )
    return bool(tiers & grants)


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
    grants: frozenset[str] = Depends(get_grants),
) -> dict:
    limit = max(1, min(limit, 500))
    owner = plane == "owner"
    declared = ctx.instance.declared_tiers
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
        if predicate is not None and not _has_visible_predicate(
            fact, predicate, owner=owner, grants=grants, declared=declared, ctx=ctx
        ):
            continue
        if not owner and not fact_is_visible(fact, ctx.join, ctx.datasets, grants,
                                             declared=declared):
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


def _fact_by_id(ledger_root: Path, fact_id: str) -> dict | None:
    """The live fact file whose own `id` is `fact_id`, shape-checked, or
    None — the same load+validate `get_fact`'s primary path applies,
    factored out so the lineage-redirect branch can apply it to the
    successor BEFORE emitting the 307 (finding 6)."""
    fact_path = _find_fact_path(ledger_root, fact_id)
    if fact_path is None:
        return None
    try:
        fact = json.loads(fact_path.read_bytes())
    except json.JSONDecodeError:
        return None
    if not isinstance(fact, dict) or is_redirect(fact) or fact.get("id") != fact_id:
        return None
    return fact


@router.get("/facts/{fact_id}")
def get_fact(
    fact_id: str, request: Request, response: Response,
    ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
    grants: frozenset[str] = Depends(get_grants),
):
    lineage, _ = load_lineage(ctx.ledger_root)
    target_id = lineage.get(fact_id)
    if target_id is not None:
        # The disclosure check applies to the SUCCESSOR before the redirect
        # is ever emitted — a 307 naming an invisible fact is itself the
        # leak, and a 307-vs-404 split distinguishes "retired" from "never
        # existed" exactly the way `require_owner` forbids for existence
        # generally (§5.1). Same fail-closed answer either way: 404.
        target_fact = _fact_by_id(ctx.ledger_root, target_id)
        if target_fact is None or (plane != "owner" and not fact_is_visible(
                target_fact, ctx.join, ctx.datasets, grants,
                declared=ctx.instance.declared_tiers)):
            raise HTTPException(404, "not found")
        # The redirect path gets the same ETag/Vary handling the normal path
        # does (previously applied nowhere on this branch) — a downstream
        # cache must not conflate a redirect served to one plane with
        # another's, any more than it may for a fact body.
        etag = _etag(ctx.instance_commit, plane, f"redirect:{fact_id}:{target_id}".encode())
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Vary": "Authorization"})
        redirect = RedirectResponse(url=f"/facts/{target_id}", status_code=307)
        redirect.headers["ETag"] = etag
        redirect.headers["Vary"] = "Authorization"
        return redirect

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

    projected = project_fact(fact, ctx.join, ctx.datasets, owner=(plane == "owner"),
                             grants=grants, declared=ctx.instance.declared_tiers)
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
    grants: frozenset[str] = Depends(get_grants),
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
        declared = ctx.instance.declared_tiers
        if not fact_is_visible(fact, ctx.join, ctx.datasets, grants, declared=declared):
            raise HTTPException(404, "not found")
        sources = fact.get("sources") if isinstance(fact.get("sources"), dict) else {}
        if not claim_is_visible(claim, sources, ctx.join, ctx.datasets, grants,
                                declared=declared):
            raise HTTPException(404, "not found")
    return claim


# --------------------------------------------------------------------- /scope


@router.get("/scope")
def get_scope(
    spec: str, ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
    grants: frozenset[str] = Depends(get_grants),
) -> dict:
    try:
        parsed = json.loads(spec)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"spec is not valid JSON: {e}") from e
    try:
        result = evaluate_scope(
            ctx.ledger_root, parsed,
            references=list(ctx.datasets.values()),
            corpora_roots=[c.root for c in ctx.join.corpora],
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except NotImplementedError as e:
        # `evidence: "resolved"` is admitted by spec shape (`_validate_spec`)
        # but not yet implemented by `evaluate_scope` (§12) — a documented,
        # not-yet-built feature is 501, never a 500.
        raise HTTPException(501, str(e)) from e

    if plane == "owner":
        return result

    declared = ctx.instance.declared_tiers

    # A whole-fact filter alone is not enough here: a fact visible to
    # `grants` can still carry claims invisible to it, and evaluate_scope's
    # evidence/roster maps are built from every claim/roster entry
    # unconditionally. Recompute both maps from the same per-claim/per-source
    # projection `/facts/{id}` applies (`visible_evidence_uris`/
    # `visible_roster_uris`) rather than merely filtering evaluate_scope's
    # raw output down to visible fact ids — the narrower bug this fixes: a
    # record hash outside `grants` riding a visible fact's evidence list was
    # previously served whole.
    all_members = result.get("members", [])
    kept_facts: dict[str, dict] = {}
    kept_members = []
    for m in all_members:
        path = m.get("path")
        fact = _load_fact_at(ctx.ledger_root, path) if isinstance(path, str) else None
        if fact is not None and fact_is_visible(fact, ctx.join, ctx.datasets, grants,
                                                declared=declared):
            fid = str(m.get("id"))
            kept_facts[fid] = fact
            # `depth` counts hops through the UNFILTERED graph — an
            # invisible intermediary on the shortest path would still shape
            # a visible descendant's depth, revealing that something is
            # there even though it never surfaces as a member (finding 5).
            # Recomputing depth over the visible subgraph would mean
            # re-running the traversal — the exact reimplementation this
            # codebase already flags as tech debt for the operator grammar
            # (§10, "Beyond the finding cap"). Omitting it is the simplest
            # spec-honest option: every other plane-filtered route already
            # drops fields it can't answer safely rather than answer them
            # wrong (`/facts/{id}` strips claims/sources/roster outright).
            kept_members.append({k: v for k, v in m.items() if k != "depth"})

    # A seed id that resolves to a fact invisible to `grants` must be
    # indistinguishable from one that never existed (§5.1: "existence itself
    # can be the leak") — merge it into `unknown_seeds` too. Replicates
    # `scope.make_resolver`'s single lineage hop rather than re-deriving the
    # resolved id from the (already-filtered) member set, so a raw id that
    # resolves through a retired/redirected id can't slip through.
    seed = parsed.get("seed") if isinstance(parsed, dict) else None
    unknown_seeds = set(result.get("unknown_seeds") or ())
    if isinstance(seed, dict) and isinstance(seed.get("ids"), list):
        member_ids = {str(m.get("id")) for m in all_members}
        lineage, _ = load_lineage(ctx.ledger_root)
        for raw in seed["ids"]:
            if not isinstance(raw, str) or raw in unknown_seeds:
                continue
            resolved = raw if raw in member_ids else lineage.get(raw)
            if resolved is not None and resolved not in kept_facts:
                unknown_seeds.add(raw)
    result["unknown_seeds"] = sorted(unknown_seeds)
    result["members"] = kept_members
    if "evidence" in result:
        result["evidence"] = {
            fid: visible_evidence_uris(fact, ctx.join, ctx.datasets, grants, declared=declared)
            for fid, fact in kept_facts.items()
        }
    if "roster" in result:
        result["roster"] = {
            fid: visible_roster_uris(fact, ctx.join, grants, declared=declared)
            for fid, fact in kept_facts.items()
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

_DEMAND_RULES_START = "<!-- vocab:demand-rules:start -->"
_DEMAND_RULES_END = "<!-- vocab:demand-rules:end -->"


def _strip_demand_rules_section(markdown: str) -> str:
    """Strip the "Demand rules" section from a non-owner `/vocab` response.

    `views.fresh_vocab` builds this section straight from the demand rule
    definitions (ids + `description:`) — not from `facts`, so pre-filtering
    the fact dict passed in (below) can't touch it. Rule ids/descriptions
    are owner-only on every other route (`/facts/{id}/demands` gates on
    `require_owner`); `/vocab` must not become the one place that leaks them
    to the public/audience plane."""
    heading_start = markdown.find("\n## Demand rules\n")
    end_marker = markdown.find(_DEMAND_RULES_END)
    if heading_start == -1 or end_marker == -1:
        return markdown
    end = end_marker + len(_DEMAND_RULES_END)
    if markdown[end:end + 1] == "\n":
        end += 1
    return markdown[:heading_start] + markdown[end:]


@router.get("/vocab")
def get_vocab(
    ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
    grants: frozenset[str] = Depends(get_grants),
) -> dict:
    facts, _ = load_json_dir(ctx.ledger_root, "facts/*/*.json")
    owner = plane == "owner"
    if not owner:
        # A non-owner plane must never learn the type/predicate/qualifier/
        # role vocabulary of a fact it cannot read — existence itself can be
        # the leak (finding 4, spec/ledger.md §6.4/§12). The counts and rows
        # `views.collect_vocab` derives from `facts` are filtered here, at
        # the same fact-visibility gate `/facts` and `/scope` apply, rather
        # than inside `views` (which has no plane concept of its own — it
        # only ever sees the fact dict it's handed).
        declared = ctx.instance.declared_tiers
        facts = {
            path: fact for path, fact in facts.items()
            if fact_is_visible(fact, ctx.join, ctx.datasets, grants, declared=declared)
        }
    markdown = views_mod.fresh_vocab(ctx.ledger_root, facts)
    if not owner:
        markdown = _strip_demand_rules_section(markdown)
    return {"generated": True, "markdown": markdown}


# ------------------------------------------------------------------- /records


@router.get("/records/{hash_}")
def get_record(
    hash_: str, ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
    grants: frozenset[str] = Depends(get_grants),
) -> dict:
    if not FULL_HASH_RE.match(hash_):
        raise HTTPException(422, "not a 64-hex blake3 hash")
    record_path = CorpusJoin.record_path(ctx.corpus_root, hash_)
    if not record_path.is_file():
        raise HTTPException(404, "not found")
    if plane != "owner" and not _record_visible(ctx, hash_, grants):
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
    grants: frozenset[str] = Depends(get_grants),
):
    if not FULL_HASH_RE.match(hash_):
        raise HTTPException(422, "not a 64-hex blake3 hash")
    if plane != "owner" and not _record_visible(ctx, hash_, grants):
        raise HTTPException(404, "not found")

    query = request.url.query
    uri = f"corpus://{hash_}" + (f"?{query}" if query else "")

    from corpus import resolver as corpus_resolver
    from corpus.store import ArtifactMissing

    try:
        out_path = corpus_resolver.resolve(uri, ctx.corpus_root, regenerate=False)
    except NotImplementedError as e:
        # Generic details only (finding 7): the pre-fix message echoed the
        # caller's own raw `uri` (query string included) back into the
        # response body — a reflection, not a disclosure of anything new,
        # but still worth denying the habit on an unauthenticated route.
        raise HTTPException(
            501, "not cleanly resolvable over the read surface — try "
                 "`corpus resolve` on the instance host"
        ) from e
    except ValueError as e:
        raise HTTPException(422, "not resolvable") from e
    except (FileNotFoundError, ArtifactMissing) as e:
        # Generic detail only: the resolver's own message embeds the
        # absolute instance-root filesystem path (finding 7) — never
        # servable to a plane that hasn't even cleared the visibility gate
        # above.
        raise HTTPException(404, "not found") from e

    media_type = mimetypes.guess_type(str(out_path))[0] or "application/octet-stream"
    return FileResponse(
        out_path, media_type=media_type,
        headers={
            # The corpus captures untrusted third-party pages by design —
            # `text/html`/`image/svg+xml` bytes served inline, same-origin
            # with the API, would let a captured page's script read every
            # owner-plane route with the credentials of whatever frontend
            # the operator points at this port (finding 7, §5.1). `nosniff`
            # stops content-type sniffing from upgrading a mislabeled body
            # into something executable; `attachment` stops it from
            # rendering/running same-origin at all.
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{hash_}"',
        },
    )


@router.get("/resolve/ref/{dataset}/{id_path:path}")
def resolve_ref(
    dataset: str, id_path: str, tag: str | None = None,
    ctx: Ctx = Depends(get_ctx), plane: str = Depends(get_plane),
    grants: frozenset[str] = Depends(get_grants),
):
    reference = ctx.datasets.get(dataset)
    if reference is None:
        raise HTTPException(404, "unregistered dataset")
    resolved_tag = tag if tag is not None else reference.latest
    snapshot = reference.snapshots.get(resolved_tag)
    if snapshot is None:
        raise HTTPException(404, f"unknown snapshot tag {resolved_tag!r}")

    if plane != "owner" and not _record_visible(ctx, snapshot.artifact, grants):
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
    lineage, _ = load_lineage(ctx.ledger_root)
    return demands_mod.evaluate_demands(
        fact, rules=rules, schemas=schemas, kinds=kinds,
        facts_by_id=facts_by_id, edges=edges, interps=list(interps.values()),
        lineage=lineage,
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


async def _cache_headers_middleware(request: Request, call_next):
    """Response middleware, not a per-route header (finding 8): every route
    on this surface varies by the `Authorization` bearer — a plane-blind
    reverse proxy or CDN in front of the port (§5.1 anticipates exactly this
    deployment posture) must never key a cached response on anything less,
    so every response gets `Vary: Authorization`, not only `/facts/{id}`
    (previously the one route that set it). Owner- and audience-plane
    responses additionally forbid caching outright — a shared cache serving
    an owner-plane `/facts` listing (private fact ids) to the next anonymous
    request under a token-blind key is the finding's own scenario. The
    public plane's responses may stay cacheable (no override): a cache
    serving one public-plane response to another public caller discloses
    nothing beyond what `{public}` already grants."""
    response = await call_next(request)
    response.headers["Vary"] = "Authorization"
    if get_plane(request) != "public":
        response.headers["Cache-Control"] = "private, no-store"
    return response


# ----------------------------------------------------------------- app factory


def create_app(
    instance_root: Path, owner_token: str | None, *,
    audience_tokens: Mapping[str, str] | None = None,
) -> FastAPI:
    """Build the read surface for the instance at *instance_root*.

    *owner_token*, when given, gates the owner plane (`Authorization: Bearer
    <token>`); `None` means the owner plane is not enabled at all — every
    request, bearer or not, reads as public (§5.1).

    *audience_tokens* maps a declared audience name (`athenaeum.yaml`
    `tenancy.audiences`, spec/athenaeum.md §2.3) to its bearer token — each
    name gates its own audience plane, serving the projection for that
    audience's grant set (`Instance.grants_for`, spec/ledger.md §6.4). A name
    not declared on the instance raises `ValueError`.
    """
    instance = load_instance(instance_root)
    audience_tokens = dict(audience_tokens or {})
    unknown = sorted(set(audience_tokens) - set(instance.audiences))
    if unknown:
        declared = sorted(instance.audiences) or ["(none declared)"]
        raise ValueError(
            f"audience token(s) name undeclared audience(s) {unknown} — "
            f"declared audiences: {declared}"
        )
    app = FastAPI(
        title="Athenaeum read surface",
        version=str(SPEC_VERSION),
        description="A read-only HTTP surface over an Athenaeum instance's "
                     "corpus + ledger join (spec/athenaeum.md §5.1). The "
                     "planes are the grant sets: public (default, "
                     "sensitivity-filtered to {public}, fail closed), one "
                     "audience plane per declared audience (bearer-token "
                     "gated, filtered to that audience's granted tiers plus "
                     "public), and owner (bearer-token gated, unfiltered).",
    )
    app.state.root = instance_root
    app.state.owner_token = owner_token
    app.state.audience_tokens = audience_tokens
    app.state.schema_sig = None
    app.include_router(router)
    app.middleware("http")(_cache_headers_middleware)
    return app
