"""Body derivation — the 3.0 `body` op (§6.2) and the shared drafter-run core.

The 2.x draft stage's content extraction is now a **derivation op**: a pure function of
(artifact x schemas x op version) that produces the faithful mechanical body markdown the
drafter used to store. `build_content_zone` runs the matching mime drafter into a fresh
`recordbuild.Build` (the SAME construction path draft / compile use), returning both the
Build (whose content zone is the derived body) and the drafter's metadata result (the
attested facts — artifact fields, manifest embeds, issues, sidecar enrichment). Two
consumers split off it:

- **ingest attestation** (§8.1) applies the metadata result to the stub and discards the
  body (derived on demand);
- **the `body` op** (`corpus body` / `corpus://<hash>?body`) emits the Build's content zone;
- **`derive_record`** (the transitional `corpus draft`) applies the metadata AND stores the
  body, as 2.x did.

Keeping one run means all three see byte-identical extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import frontmatter

from corpus import containment, mime, recordbuild, records, schemas
from corpus import draft as draft_pkg
from corpus.draft import DrafterResult


class DeriveError(RuntimeError):
    """A record cannot be derived (no mime schema / no drafter)."""


def _pkg_version() -> str:
    from corpus import __version__

    return __version__


def apply_drafter_result(
    post: frontmatter.Post,
    result: dict[str, Any],
    mime_schema_id: str,
    corpus_root: Path,
) -> None:
    """Merge a drafter's metadata-zone result (the **attested facts**) onto `post`: the
    artifact-block fields, metadata-zone embeds, source-enrichment origin fields, the
    producer-declared overlay id, origin-alias URLs, and the mechanical issues. Does NOT
    touch the content zone (the body is the drafter's Build / the `body` op) — this is the
    attestation half of the split (§12.4)."""
    # Artifact-block fields (merge drafter-supplied fields; refined title overrides).
    artifact = records.artifact_block(post) or {
        "mime": records.media_type_for(post),
        "fields": {},
    }
    artifact_fields = dict(artifact.get("fields") or {})
    for key, value in (result.get("fields") or {}).items():
        artifact_fields[key] = value
    records.set_artifact_block(post, mime=artifact["mime"], fields=artifact_fields)

    # *(3.2)* A drafter's top-level `description` is intentionally DISCARDED — the frontmatter
    # `description` is a deliberate editorial override (spec §4.2.1), never a byte-fact ingest
    # attests; the display description is derived from role-marked fields instead (§4.2.3).
    # No registered drafter currently populates this key (verified at the 3.2 migration), so
    # this is a no-op today; it stays a documented discard rather than a silent no-op so a
    # future drafter's `description` key fails loudly-by-omission instead of quietly writing
    # a birth-time frontmatter field the spec now forbids (§12.3.4).
    _ = result.get("description")  # discarded — see above

    # canonical (from the mime schema's canonical_strategy): intentionally NOT persisted
    # (§7.1 status note — the value corrupts cross-URL dedup on text-empty PDFs; disabled).
    _ = result.get("canonical")  # discarded

    # Metadata-zone embeds (reconciliation #1).
    for emb in result.get("embeds") or []:
        records.append_embed_block(
            post,
            media_type=emb["media_type"],
            address=emb["address"],
            transport=emb["transport"],
            fields=emb.get("fields") or None,
        )

    # Source-provided enrichment fields (e.g. a yt-dlp `ytdlp_*` set) → the origin block, not
    # the artifact block (where-it-came-from metadata, §7.2).
    records.merge_origin_fields(post, result.get("origin_fields") or {})

    # Producer-declared overlay id (an injected `corpus-origin-schema` meta) → stamp the origin
    # block opener (the binding for a uri-less origin, §7.2).
    if schema_id := result.get("origin_schema"):
        records.set_origin_schema_id(post, str(schema_id))

    # Origin-alias URLs the drafter discovered (canonical / post-redirect final) → the origin
    # block's uri: list, not the artifact block (§7.2).
    for alias in result.get("origin_uri_aliases") or []:
        records.add_origin_uri_alias(post, str(alias), corpus_root=corpus_root)

    # Host-pattern / scheme qualification of any still-bare origin block (§7.2's "the
    # ingest pipeline iterates every origin block" upgrade). Runs after the producer-
    # declared stamp above so it never contends with it — `qualify_origin_blocks` skips
    # any block that already carries an id, from either path. The single seam every
    # caller of `attest()` shares (fresh ingest AND `corpus reattest`), so a record born
    # before this fix gets qualified retroactively on its next re-attest.
    records.qualify_origin_blocks(post, corpus_root)

    # Content-zone structural byte-marks (§4.3.2.3) — currently just media-container chapters
    # (`time=<tc>`, §12.20 item 2). Top-level only, prepended ahead of any existing content
    # zone (the "formless segments before the first section" shape, §4.3.2.1) — chapters mark
    # the container's shared timeline, never a form span.
    marks = result.get("structural_segments") or []
    if marks:
        _apply_structural_segments(post, marks)

    # Drafter-detected issues (spec-shaped). Skip a malformed dict missing `severity`.
    for issue in result.get("issues") or []:
        severity = issue.get("severity")
        if not severity:
            print(f"  WARN: drafter issue missing `severity`, skipped: {issue!r}", file=sys.stderr)
            continue
        records.append_issue_block(
            post,
            id=str(issue.get("id") or "unknown"),
            subtype=issue.get("subtype"),
            severity=str(severity),
            resolution=str(issue.get("resolution", "open")),
            detector=str(
                issue.get("detector") or f"corpus.draft.{mime_schema_id}@{_pkg_version()}"
            ),
            address=issue.get("address"),
            fields=issue.get("fields") or None,
        )


def _apply_structural_segments(post: frontmatter.Post, marks: list[dict[str, Any]]) -> None:
    """Merge attested structural byte-marks (§4.3.2.3) onto `post`'s content zone, prepended
    ahead of any existing top-level content. **Additive and idempotent by union, never
    strip-then-regenerate**: unlike embeds (re-derived from the artifact's own bytes on every
    attest), the currently-implemented source is the **one-shot yt-dlp sidecar**
    (`_sidecar.py`) — consumed and deleted right after ingest (`ingest._cleanup_enrichment`),
    exactly like the `ytdlp_*` origin fields it rides alongside. A re-attest therefore sees no
    chapters at all (`chapters=None` → `marks=[]` → this function isn't even called, per its
    caller's `if marks:` guard) and must never strip what ingest already attested — there is
    nothing left to regenerate it from. A mark already present (matched on `(address, mark)`)
    is skipped rather than duplicated, so a future re-derivable source (the mp4 chapter-atom
    path, a named gap — §12.20 item 2) can call this safely too.

    Defensive, not just decorative: a video/audio record's content zone is empty for every
    record in the fleet today (§8.1 — `attest` never stores a body; a stored body is
    normalize's job), so prepending is the common case, but a malformed existing content zone,
    or one already governed by a whole-record form section (which admits no sibling block,
    §4.3.2.2), is left untouched rather than corrupted — logged and skipped."""
    from corpus import segments as segs_mod

    try:
        existing = segs_mod.iter_blocks(post.content or "")
    except ValueError as exc:
        print(
            f"  WARN: structural-mark attestation skipped — existing content zone does not "
            f"parse: {exc}",
            file=sys.stderr,
        )
        return
    # *(3.7)* The whole-record guard retires with the spelling it keyed on (`address is None`,
    # §12.29). A section's extent is now exactly its children's, so prepending a structural
    # mark cannot collide with a span's claim the way it could when one section claimed the
    # entire zone — the mark takes its own address and the spans keep theirs.
    # *(3.8, §12.32)* Keyed on the mark's BODY now that its text lives there — the key has
    # to be what identifies the mark, and that is no longer a header field.
    already = {
        (b.address, (b.body or "").strip())
        for b in existing
        if isinstance(b, segs_mod.Segment) and b.is_structural
    }
    new_blocks = [
        segs_mod.Segment(
            atom=segs_mod._STRUCTURAL,
            address=str(m["address"]),
            level=int(m.get("level") or 1),
            body=(str(m["mark"]).strip() if m.get("mark") else ""),
        )
        for m in marks
        if (str(m["address"]), (str(m["mark"]).strip() if m.get("mark") else "")) not in already
    ]
    if not new_blocks:
        return
    post.content = segs_mod.emit(new_blocks + list(existing))


def _content_zone_has_el(post: frontmatter.Post) -> bool:
    """Whether the record's AUTHORED content zone (sections, segments, structural marks)
    stores any `el=`-leading address. The members roster is deliberately not consulted —
    it is attested, stripped and rebuilt right here, so only the authored layer can carry
    a legacy address across an attest. Parses tolerantly: an unparseable zone reads as
    False (attest will surface the parse problem itself)."""
    from corpus import segments as segs_mod

    try:
        blocks = segs_mod.iter_blocks(post.content or "")
    except ValueError:
        return False
    for blk in blocks:
        if isinstance(blk, segs_mod.Section):
            addressed = ([blk.address] if blk.address is not None else []) + [
                s.address for s in blk.segments
            ]
        else:
            addressed = [blk.address]
        for address in addressed:
            for addr in segs_mod._iter_addr_strings(address):
                if segs_mod._leading_param(addr)[0] == "el":
                    return True
    return False


def _is_drafter_issue(ctx: dict) -> bool:
    """A mechanical drafter-emitted issue — the attested layer's issue half. Identified by
    the `corpus.draft.*` detector family (a capturer's issue detector is preserved)."""
    if (ctx.get("namespace") or "") != "issue":
        return False
    detector = str((ctx.get("fields") or {}).get("detector") or "")
    return detector.startswith("corpus.draft.")


def strip_attested_layer(post: frontmatter.Post) -> None:
    """Clear the attested layer of `post` in place — the members roster, the `corpus.draft.*`
    issues, and the artifact block's extended fields (the opener MIME stays; it is
    byte-intrinsic). Makes re-attestation and the transitional draft idempotent: attesting an
    already-attested record does not double its roster/issues.

    *(3.4)* Nothing is carried across any more. The roster is wholly attested — re-derived from
    the artifact, holding no authored field — so there is nothing to preserve, and the
    description-by-transport-hash carry this used to perform is deleted along with the trap it
    contained. The record is also flipped to the 3.4 form
    here, since what follows rebuilds the roster under the current grammar.

    Content-zone structural byte-marks (§4.3.2.3) are deliberately NOT stripped here: the
    currently-implemented source (media-container chapters) is a one-shot sidecar consumed and
    deleted at ingest (see `_apply_structural_segments`), so there is nothing to regenerate
    them from on re-attest — they persist untouched, exactly as `ytdlp_*` origin fields do.

    *(3.11)* The `cutting:` stamp is preserved for the **same** reason, and it is the one
    artifact field that is not a byte-fact. It records a *resolution* — mime default ← the
    container's origin overlay — performed at promotion, when both records were in hand
    (§7.2.1). A stream leaf's own bytes cannot regenerate it: they carry no strategy and no
    lineage, and the origin `corpus://<container>?stream_id=<N>` is capture history, never a
    lookup route (§12.15). Stripping it would delete the resolution and leave the drafter with
    nothing to compare against — which is precisely the drift §7.2.1's compare-before-write
    rule exists to catch, caused by the strip that was supposed to be neutral. (This is the
    shape of the trap 3.4 removed with `reattach_descriptions`: a non-derivable value living
    inside a strip-and-rebuild layer. The fix there was to stop storing it; here it cannot be
    derived at all, so the fix is to not strip it.)

    *(3.12, retired v32)* The `framing:` stamp was preserved on the same reasoning, arriving
    from the other direction: it IS a byte-fact, and that is exactly why nothing here could
    rebuild it. `muxer`/`version`/`flags` named what *produced* the bytes, and produced bytes
    carry no record of their producer — only the promote pass knew, because only there was
    the muxer running. A surviving pre-v32 `framing:` stamp is kept here for the same reason
    it is kept anywhere: it is honest history, not a defect (§7.1).

    *(v32)* `samples:` is preserved for the SAME reason `cutting:` is, not the reason
    `framing:` was: it is a byte-fact about the CONTAINER's tables, and a v32 leaf's own
    bytes carry no table of their own to re-derive it from (§2 — the payload has no sample
    table, only the container does). The leaf's origin `corpus://<container>?stream_id=<N>`
    is capture history, never a lookup route (§12.9), so only the promote pass — which holds
    both records — can compute it. Stripping it would delete the self-check `cutting:` and
    stored markers compare against, leaving nothing to catch a re-derivation that disagrees."""
    post.metadata["_embeds"] = []
    post.metadata["_members_block"] = True
    post.metadata["_contexts"] = [
        c for c in (post.metadata.get("_contexts") or []) if not _is_drafter_issue(c)
    ]
    art = records.artifact_block(post) or {}
    preserved: dict[str, Any] = {}
    if (stamp := (art.get("fields") or {}).get("framing")) is not None:
        preserved["framing"] = stamp
    if (stamp := (art.get("fields") or {}).get("cutting")) is not None:
        preserved["cutting"] = stamp
    if (n := (art.get("fields") or {}).get("samples")) is not None:
        preserved["samples"] = n
    records.set_artifact_block(post, mime=str(art.get("mime") or ""), fields=preserved)


def attest(
    post: frontmatter.Post,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    strip: bool = False,
    messages: list[int] | None = None,
) -> str:
    """Derive + apply the **attested layer** onto `post` in place (§8.1, §12.4): run the mime
    drafter and apply its metadata result (artifact fields, the members roster, drafter issues),
    NEVER storing the body (the `body` op derives it on demand) and NEVER touching the authored
    layer (title/description, form sections). Returns the mime schema id.

    `strip=True` (re-attest, §12.4.6) first clears the current attested layer — the roster, the
    `corpus.draft.*` issues, and the artifact block's extended fields — and rebuilds it under the
    3.4 grammar. `strip=False` (a fresh ingest stub) applies onto a record that carries none yet.

    A pre-3.4 record's per-asset `description`s are **dropped**, not carried: the old blocks are
    deleted and the members block replaces them (§4.3.1.4, §12.26). Nothing migrates and no
    obligation falls on a member as a result. `records.pending_member_descriptions` reports what
    a given conversion will drop so the caller can say so out loud (`corpus reattest` does).

    `messages` are the mbox selective declaration (§12.11, the re-homed `--messages`): the
    1-indexed ordinals to manifest as `message/rfc822` embeds; None reads the record's already-
    declared set. The mbox manifest is EXEMPT from the strip — it is cumulative by design (its
    result is the delta over the already-declared embeds), so stripping would drop them.
    Raises `DeriveError` / `ArtifactMissing`."""
    from corpus.draft import mbox_manifest

    # *(3.6)* The el= grammar dispatch is the artifact block's `addressing:` stamp (§7.1):
    # stamped records carry child-index PATHS, unstamped ones the pre-3.6 filtered index.
    # Attesting stamps it (the HTML drafter emits it as an attested fact) — which would
    # silently flip the reading of any LEGACY integer address still stored on the
    # authored layer. A bare `el=5` is valid under BOTH grammars with different meanings,
    # so nothing downstream could detect the flip. Refuse loudly instead: the §12.28
    # remap rewrites the authored addresses and stamps the record, THEN re-attests
    # through this same gate (stamped → passes).
    if records.el_addressing(post) is None and _content_zone_has_el(post):
        raise DeriveError(
            "record's authored layer carries pre-3.6 `el=` addresses but no `addressing:` "
            "stamp — attesting would stamp the record and re-read those integers as "
            "child-index paths (spec §6.1.1), silently re-pointing every one. Run the "
            "§12.28 remap (`corpus remap-el`) first; it rewrites the addresses and "
            "re-attests in the same pass."
        )

    media_type = records.media_type_for(post)
    mt = schemas.normalize_pipeline_keys(schemas.load_mime_schema(corpus_root, media_type) or {})
    is_mbox = str((mt.get("draft") or {}).get("strategy") or "") == "mbox-manifest"
    eff_messages = (
        messages if messages is not None else (mbox_manifest.declared_ordinals(post) or None)
    )

    if strip and not is_mbox:
        strip_attested_layer(post)
    _build, result, _mt, _bin, mime_schema_id = build_content_zone(
        post, corpus_root, fingerprint_cli=fingerprint_cli, messages=eff_messages
    )
    apply_drafter_result(post, result, mime_schema_id, corpus_root)
    return mime_schema_id or ""


def resolve_drafter(corpus_root: Path, media_type: str):
    """Return `(drafter, strategy, mime_schema_id, mt_schema)` for `media_type`, loading the
    corpus's own local drafter modules first. Raises `DeriveError` when no schema/drafter
    resolves. A mime schema MAY name a general draft `strategy` (overlay-driven — e.g.
    `zip-manifest`), which decouples drafter choice from the schema id; absent one, dispatch
    by schema id."""
    if not media_type:
        raise DeriveError("record has no `<!--artifact <mime>-->` block (re-stub first?).")
    mt_schema = schemas.load_mime_schema(corpus_root, media_type)
    if not mt_schema:
        raise DeriveError(f"no mime schema for {media_type!r}.")
    mime_schema_id = schemas.mime_schema_id_for(corpus_root, media_type)
    if not mime_schema_id:
        raise DeriveError(f"could not resolve mime schema id for {media_type!r}.")
    # 3.0 pipeline-key aliasing: back-fill the legacy `mode`/`draft.*` view from the documented
    # `disposition`/`derive.*` keys, so a schema declaring either form dispatches identically.
    mt_schema = schemas.normalize_pipeline_keys(mt_schema)
    strategy = str((mt_schema.get("draft") or {}).get("strategy") or "").strip()
    if strategy:
        drafter = draft_pkg.get_strategy_drafter(strategy)
        if drafter is None:
            raise DeriveError(
                f"mime schema {mime_schema_id!r} declares draft strategy {strategy!r}, "
                f"but no drafter is registered for it."
            )
    else:
        drafter = draft_pkg.get_drafter(mime_schema_id)
        if drafter is None:
            raise DeriveError(f"no drafter registered for mime schema id {mime_schema_id!r}.")
    return drafter, strategy, mime_schema_id, mt_schema


def build_content_zone(
    post: frontmatter.Post,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
) -> tuple[recordbuild.Build, DrafterResult, dict[str, Any], Path, str]:
    """Run the matching mime drafter against `post`'s retained artifact into a fresh Build.

    Returns `(build, result, mt_schema, binary_file, mime_schema_id)`:
    - `build` — a `recordbuild.Build` seeded from `post`; its content zone (`build.blocks`)
      is the derived body (empty for a `manifest`/non-`body-draft` schema).
    - `result` — the drafter's metadata-zone `DrafterResult` (the attested facts).

    Pure over the artifact bytes + schemas; does NOT emit, apply, or persist anything.
    Raises `DeriveError` / `ArtifactMissing`."""
    media_type = records.media_type_for(post)
    drafter, strategy, mime_schema_id, mt_schema = resolve_drafter(corpus_root, media_type)
    record_id = str(post.metadata.get("id") or "")

    # Containment-aware byte access (§2/§12.9): a promoted member drafts from the bytes
    # streamed out of its container just as a standalone record drafts from `artifacts/`.
    binary_file = containment.ensure_local_bytes(
        corpus_root, record_id, mime.extension_for(media_type)
    )

    canonical_algo = (mt_schema.get("canonical_strategy") or {}).get("algo")
    build = recordbuild.begin_from_post(post, corpus_root)
    fingerprint = schemas.resolve_fingerprint(corpus_root, media_type, post, fingerprint_cli)
    drafter_kwargs: dict[str, Any] = dict(
        build=build,
        corpus_root=corpus_root,
        record_id=record_id,
        record_metadata=post.metadata,
        canonical_algo=canonical_algo,
        fingerprint=fingerprint,
    )
    if strategy:
        drafter_kwargs["mime_schema"] = mt_schema
        if strategy == "mbox-manifest":
            drafter_kwargs["messages"] = messages
    result = drafter(binary_file, **drafter_kwargs)
    return build, result, mt_schema, binary_file, mime_schema_id


def produces_body(mt_schema: dict[str, Any]) -> bool:
    """Whether this schema's drafter builds a content-zone body (a `body-draft`/`work`
    schema) as opposed to a manifest whose members are embeds (empty content zone)."""
    return str(mt_schema.get("mode", "body-draft")).lower() == "body-draft"


def derive_body(
    post: frontmatter.Post,
    corpus_root: Path,
    *,
    fingerprint_cli: bool | None = None,
    messages: list[int] | None = None,
) -> str:
    """The `body` derivation op (§6.2): the record's faithful mechanical body markdown —
    what the 2.x drafter stored — derived on demand from the artifact. Empty for a manifest
    record (its members are embeds, not a body). Runs on a scratch copy of `post` so the
    live record is never mutated. Raises `DeriveError` / `ArtifactMissing`."""
    from corpus import segments

    scratch = frontmatter.Post(post.content or "", **dict(post.metadata))
    scratch.metadata["_embeds"] = []
    scratch.metadata["_contexts"] = []
    build, _result, mt_schema, _bin, _id = build_content_zone(
        scratch, corpus_root, fingerprint_cli=fingerprint_cli, messages=messages
    )
    if not produces_body(mt_schema):
        return ""
    return segments.emit(build.blocks)
